"""Main Path Selection GUI
"""

import sys
from typing import Optional, Union
import pyqtgraph as pg
import pyqtgraph.opengl as gl
from pyqtgraph.Qt import QtCore, QtGui, QtWidgets
import numpy as np
from util.nifti import load_nifti


class PathSelection(QtWidgets.QWidget):

    def __init__(self, app, paths, all_trajectories):
        """Main window initialization"""
        super().__init__()

        # Load paths and trajectories
        self.app = app
        self.paths = paths
        self.all_trajectories = all_trajectories

        # Setup main window
        self.initScreen()
        # Setup data
        self.initData()
        # Setup subplots widget
        self.initSubplots()
        # Setup side bar
        self.initSide()

        # Setup main layout
        self.initWindow()

    def initScreen(self):
        """Screen initialization"""
        self.setWindowTitle('Target Selection')

        self.screen = QtGui.QDesktopWidget().screenGeometry()
        self.resize(1000, 800)
        self.setWindowState(QtCore.Qt.WindowMaximized)

    def initWindow(self):
        """Main window initialization"""

        # Layout of main window
        layout = QtGui.QGridLayout()

        layout.addWidget(self.sideBar, 0, 5, 1, 1)
        layout.addWidget(self.subplots, 0, 0, 1, 5)

        self.setLayout(layout)

    def initData(self):
        """Data initialization"""
        # Load basic images (T1W, T1W-GADO, CT)
        scan1_arr, scan1_aff, _ = load_nifti(self.paths["T1w"])
        scan1_name = "T1w"
        scan2_arr, scan2_aff, _ = load_nifti(self.paths["T1w_gado"])
        scan2_name = "T1w_gado"
        scan3_arr, scan3_aff, _ = load_nifti(self.paths["CT"])
        scan3_name = "CT"

        # Load distance map
        self.distance_map, dist_aff, _ = \
            load_nifti(self.paths["distance_map_combined"])

        # Load masks
        self.ventricleMask, _, _ = \
            load_nifti(self.paths["ventricle_mask"])
        self.sulcusMask, _, _ = \
            load_nifti(self.paths["sulcus_mask"])
        self.vesselMask, _, _ = \
            load_nifti(self.paths["vessel_mask"])

        # Load scans in dict
        self.scans = {
            scan1_name: scan1_arr,
            scan2_name: scan2_arr,
            scan3_name: scan3_arr,
        }

        # Add optional scans in dict
        if "T2w" in self.paths:
            scan4_arr, scan4_aff, _ = load_nifti(self.paths["T2w"])
            scan4_name = "T2w"
            self.scans[scan4_name] = scan4_arr
        if "IR" in self.paths:
            scan5_arr, scan5_aff, _ = load_nifti(self.paths["IR"])
            scan5_name = "IR"
            self.scans[scan5_name] = scan5_arr
        if "FLAIR" in self.paths:
            scan6_arr, scan6_aff, _ = load_nifti(self.paths["FLAIR"])
            scan6_name = "FLAIR"
            self.scans[scan6_name] = scan6_arr

        # Set starting data and shape
        self.data = scan1_arr
        self.aff = scan1_aff
        self.shape = np.shape(self.data)

        self.vox_dims = np.diag(self.aff)[:-1]

        # Setup initial trajectory
        self.n_targets = np.shape(self.all_trajectories)[0]

        self.sortTrajectories()

        self.updateTrajectory(initial_pass=True)

    def initSubplots(self):
        """Subplot initialization"""

        # Create PyQtGraph graphics widget
        # pg.mkQApp()
        self.subplots = pg.GraphicsLayoutWidget(parent=self)
        self.subplots.ci.setBorder((50, 50, 100))

        # Setup top
        self.subplots.sub_text = self.subplots.addLayout(
            col=0, row=0, colspan=2, rowspan=1)

        # Setup image plots
        self.subplots.sub1 = self.subplots.addLayout(
            col=0, row=1, colspan=1, rowspan=1)
        self.subplots.sub2 = self.subplots.addLayout(
            col=1, row=1, colspan=1, rowspan=1)
        self.subplots.sub3 = self.subplots.addLayout(
            col=0, row=2, colspan=2, rowspan=1)

        # Constrain top + graph
        self.subplots.sub_text.setMaximumHeight(30)
        self.subplots.sub3.setMaximumHeight(150)

        # Make sure image columns are the same size
        qGraphicsGridLayout = self.subplots.ci.layout
        qGraphicsGridLayout.setColumnStretchFactor(0, 2)
        qGraphicsGridLayout.setColumnStretchFactor(1, 1)

        # Add viewboxes / proxys
        self.subplots.v_probe = self.subplots.sub1.addViewBox()

        self.subplots.proxy_3d = QtGui.QGraphicsProxyWidget()
        self.subplots.v_3d = gl.GLViewWidget()
        self.subplots.proxy_3d.setWidget(self.subplots.v_3d)
        self.subplots.sub2.addItem(self.subplots.proxy_3d)

        self.subplots.v_graph = pg.PlotItem(
            labels={'left': "Margin [mm]", 'bottom': "Distance to target [mm]"}
        )
        self.subplots.sub3.addItem(self.subplots.v_graph)

        # Init probe-eye view
        self.updateProbeView()

        # Add probe-eye slice
        self.subplots.img_probe = pg.ImageItem(self.current_slice)
        self.subplots.v_probe.addItem(
            self.subplots.img_probe
        )

        # Add probe marker
        self.subplots.probe_marker = pg.ScatterPlotItem(
            pos=[(max(self.shape) // 2, max(self.shape) // 2)],
            symbol="o", brush="r", pen="r", size=3
        )
        self.subplots.markerH = pg.InfiniteLine(
            pos=max(self.shape) // 2, angle=0)
        self.subplots.markerV = pg.InfiniteLine(
            pos=max(self.shape) // 2, angle=90)
        self.subplots.v_probe.addItem(self.subplots.probe_marker)
        self.subplots.v_probe.addItem(self.subplots.markerH)
        self.subplots.v_probe.addItem(self.subplots.markerV)

        # Add probe margin plot
        self.margin_pen = QtGui.QPen(QtCore.Qt.darkRed)
        self.margin_pen.setWidth(0.5)

        self.margin = 3
        self.margin_pix = self.margin / self.aspect_x

        self.subplots.probe_margin = QtWidgets.QGraphicsEllipseItem(
            max(self.shape) // 2 - self.margin_pix,
            max(self.shape) // 2 - self.margin_pix,
            2 * self.margin_pix, 2 * self.margin_pix
        )
        self.subplots.probe_margin.setPen(self.margin_pen)
        self.subplots.v_probe.addItem(self.subplots.probe_margin)

        # Setup viewbox limits + disable default mouse commands
        for v in [self.subplots.v_probe]:
            v.setMouseEnabled(x=False, y=False)
            v.setLimits(
                xMin=-1.0 * max(self.shape), xMax=max(self.shape) * 2.0,
                minXRange=20, maxXRange=max(self.shape) * 4.,
                yMin=-1.0 * max(self.shape), yMax=max(self.shape) * 2.0,
                minYRange=20, maxYRange=max(self.shape) * 4.
            )
            v.setAspectLocked(self.aspect_y / self.aspect_x)

        self.subplots.v_graph.autoRange()

        # Setup distance plot
        self.subplots.v_graph.plot(
            x=self.trajectory_dist2targetList, y=self.trajectory_distances)
        self.subplots.v_graph.setMouseEnabled(x=False, y=False)

        # Setup vertical line marker
        self.subplots.v_line = pg.InfiniteLine(
            pos=self.trajectory_dist2targetList[self.checkpoint_i],
            angle=90, movable=True,
            bounds=[
                self.trajectory_dist2targetList[0],
                self.trajectory_dist2targetList[-1]
            ]
        )
        self.subplots.v_graph.addItem(self.subplots.v_line)

        # Setup horizontal line marker
        self.subplots.h_line = pg.InfiniteLine(
            pos=self.margin,
            angle=0, movable=True,
            bounds=[0, 10]
        )
        self.subplots.v_graph.addItem(self.subplots.h_line)

        # Setup appropriate graph range
        self.subplots.v_graph.setYRange(
            0.0, 10.0, padding=0
        )
        self.subplots.v_graph.setXRange(
            self.trajectory_dist2targetList[0],
            self.trajectory_dist2targetList[-1], padding=0
        )
        self.subplots.v_graph.setLimits(
            xMin=self.trajectory_dist2targetList[0],
            xMax=self.trajectory_dist2targetList[-1],
            yMin=0
        )

        # Setup 3D render
        self.init3DRender()

        # Disable right click menus
        self.subplots.v_probe.setMenuEnabled(False)
        self.subplots.v_graph.setMenuEnabled(False)

        # Fix scaling
        self.subplots.v_probe.autoRange()

        # Setup events
        self.subplots.sub2.hoverEvent = self.update_3d
        self.subplots.sub2.wheelEvent = self.imageWheelEvent_3d

        self.subplots.v_line.sigDragged.connect(self.vLineDragged)
        self.subplots.h_line.sigDragged.connect(self.hLineDragged)

        self.subplots.keyPressEvent = self.keyPressEvent

        self.subplots.img_probe.wheelEvent = self.imageWheelEvent_probe

    def init3DRender(self):
        """Ïnitializes the 3D render"""

        # Setup transform (anisotropic voxel size)
        self.render_transform = QtGui.QMatrix4x4([
            self.vox_dims[0], 0., 0., 0.,
            0., self.vox_dims[1], 0., 0.,
            0., 0., self.vox_dims[2], 0.,
            0., 0., 0., 1.
        ])

        # Setup data
        volData = self.convert_volume_to_opengl(
            self.data,
            [self.ventricleMask, self.vesselMask],
            ["blue", (255, 0, 0)],
            [1.0, 0.005]
        )

        # Plot volume
        self.subplots.vol = \
            gl.GLVolumeItem(volData, sliceDensity=1, smooth=True)
        self.subplots.vol.translate(
            dx=-self.shape[0] / 2,
            dy=-self.shape[1] / 2,
            dz=-self.shape[2] / 2
        )
        self.subplots.vol.applyTransform(self.render_transform, False)
        self.subplots.v_3d.setCameraPosition(
            distance=300, elevation=50, azimuth=0
        )
        self.subplots.v_3d.addItem(self.subplots.vol)

        # Plot trajectories
        self.trajectoryPlots = {}
        for target_i in range(self.n_targets):
            for i in range(len(self.sorted_trajectories[target_i])):
                # Set id
                identifyer = f"{str(target_i)}_{str(i)}"
                # Set color
                if target_i == self.target_i and i == self.trajectory_i:
                    color = (1., 0., 0., 1.0)
                    width = 5
                else:
                    color = (1., 1., 0., 0.5)
                    width = 1
                # Define points
                pts = np.array([
                    self.sorted_trajectories[target_i][i][1] -
                    self.sorted_trajectories[target_i][i][0] * 50,
                    self.sorted_trajectories[target_i][i][2]
                ])
                # Plot line
                self.trajectoryPlots[identifyer] = gl.GLLinePlotItem(
                    pos=pts, width=width, color=color)
                self.trajectoryPlots[identifyer].translate(
                    dx=-self.shape[0] / 2,
                    dy=-self.shape[1] / 2,
                    dz=-self.shape[2] / 2
                )
                self.trajectoryPlots[identifyer].applyTransform(
                    self.render_transform, False)
                self.subplots.v_3d.addItem(self.trajectoryPlots[identifyer])

    def ignore(self, event):
        """Ignores events"""
        pass

    def initSide(self):
        """Initializes the sidebar"""

        # Init label font
        self.labelFont = QtGui.QFont()
        self.labelFont.setBold(True)

        # Initialize widget
        self.sideBar = QtWidgets.QWidget()

        # Setup layout
        layout = QtWidgets.QVBoxLayout()
        self.sideBar.setLayout(layout)
        self.sideBar.setMaximumWidth(200)

        # Add labels
        self.targetLabel = QtWidgets.QLabel("Targets")
        self.trajectoryLabel = QtWidgets.QLabel("Trajectories")
        self.scanLabel = QtWidgets.QLabel("Scans")
        self.settingsLabel = QtWidgets.QLabel("Margin settings")

        self.targetLabel.setFont(self.labelFont)
        self.trajectoryLabel.setFont(self.labelFont)
        self.scanLabel.setFont(self.labelFont)
        self.settingsLabel.setFont(self.labelFont)

        # Add target point list
        self.targetList = QtWidgets.QListWidget()
        self.targetList.currentItemChanged.connect(self.selectTarget)

        row = 0
        for target_i in range(self.n_targets):
            self.targetList.insertItem(row, f"Target {target_i + 1}")
            row += 1

        self.targetList.setCurrentRow(0)

        # Add trajectory list
        self.trajectoryList = QtWidgets.QListWidget()
        self.trajectoryList.currentItemChanged.connect(self.selectTrajectory)

        row = 0
        for trajectory_i in range(
            len(self.sorted_trajectories[self.target_i])
        ):
            margin = \
                self.sorted_trajectories[self.target_i][trajectory_i][-1][0]
            label = (
                f"Path {trajectory_i + 1:2d} "
                f"- Margin: {margin:.2f}"
            )
            self.trajectoryList.insertItem(row, label)
            row += 1

        self.trajectoryList.setCurrentRow(0)

        # Add scans list
        self.scanList = QtWidgets.QListWidget()
        self.scanList.currentItemChanged.connect(self.selectScan)

        row = 0
        for scan_name in self.scans.keys():
            self.scanList.insertItem(row, scan_name)
            row += 1

        self.scanList.setCurrentRow(0)

        # Add settings box
        self.settingsBox = QtWidgets.QWidget()
        settings_layout = QtWidgets.QFormLayout()

        self.marginSetting = QtWidgets.QLineEdit(text=f"{self.margin:.2f}")
        self.marginSetting.setValidator = QtGui.QDoubleValidator(0.01, 9.99, 2)
        self.marginSetting.setInputMask('9.99')
        self.marginSetting.textChanged.connect(self.editMargin)
        settings_layout.addRow("Margin [mm]:", self.marginSetting)

        self.enforceMarginSetting = QtWidgets.QCheckBox()
        self.enforceMarginSetting.setChecked(False)

        settings_layout.addRow(
            "Enforce:", self.enforceMarginSetting)

        self.settingsBox.setLayout(settings_layout)

        # Add lists and labels to layout
        layout.addWidget(self.targetLabel)
        layout.addWidget(self.targetList)
        layout.addWidget(self.trajectoryLabel)
        layout.addWidget(self.trajectoryList)
        layout.addWidget(self.scanLabel)
        layout.addWidget(self.scanList)
        layout.addWidget(self.settingsLabel)
        layout.addWidget(self.settingsBox)

    def convert_volume_to_opengl(
            self,
            data: np.ndarray,
            masks: Optional[list[np.ndarray]] = None,
            colors: Optional[list[Union[str, tuple]]] = None,
            alphas: Optional[list[float]] = None) -> np.ndarray:
        """Converts numpy arrays to single opengl array"""

        # Create empty array
        d = np.zeros(data.shape + (4,))

        # Fill array with greyscale image
        d[..., 3] = data * 255 / (100 * np.percentile(data, 99.))  # alpha
        d[..., 0] = d[..., 3]                                      # red
        d[..., 1] = d[..., 3]                                      # green
        d[..., 2] = d[..., 3]                                      # blue

        if masks or colors:
            if not (masks and colors) and (len(masks) == len(colors)):
                raise UserWarning(
                    "Both masks and colors should be defined "
                    "and should have the same length"
                )
            else:
                # Iteratively add masks to volume
                for mask_i in range(len(masks)):
                    # Extract mask, color and alpha (if applicable)
                    mask = masks[mask_i]
                    color = colors[mask_i]

                    if alphas:
                        if len(alphas) == len(masks):
                            alpha = 255 * alphas[mask_i]
                        else:
                            raise ValueError(
                                "length of alphas should match masks"
                            )
                    else:
                        alpha = 255

                    # Colors: RGBA
                    if color == "red":
                        d[..., 3][mask > 1e-2] = alpha  # alpha
                        d[..., 0][mask > 1e-2] = 255    # red
                        d[..., 1][mask > 1e-2] = 0      # green
                        d[..., 2][mask > 1e-2] = 0      # blue
                    elif color == "green":
                        d[..., 3][mask > 1e-2] = alpha  # alpha
                        d[..., 0][mask > 1e-2] = 0      # red
                        d[..., 1][mask > 1e-2] = 255    # green
                        d[..., 2][mask > 1e-2] = 0      # blue
                    elif color == "blue":
                        d[..., 3][mask > 1e-2] = alpha  # alpha
                        d[..., 0][mask > 1e-2] = 0      # red
                        d[..., 1][mask > 1e-2] = 0      # green
                        d[..., 2][mask > 1e-2] = 255    # blue
                    elif type(color) == tuple and len(color) == 3:
                        d[..., 3][mask > 1e-2] = alpha     # alpha
                        d[..., 0][mask > 1e-2] = color[0]  # red
                        d[..., 1][mask > 1e-2] = color[1]  # green
                        d[..., 2][mask > 1e-2] = color[2]  # blue
                    else:
                        raise ValueError(
                            "Only the colors 'red', 'green' and 'blue' "
                            "or RGB tuples are supported"
                        )

        return d

    def sortTrajectories(self):
        """Organises and sorts trajectories"""

        # Create new empty sorted array
        sorted_trajectories = [
            np.zeros(np.shape(array)) for array in self.all_trajectories
        ]

        # Loop over trajectories and insert them in the sorted array
        for target_i in range(len(sorted_trajectories)):
            margin_list = []
            for trajectory_i in range(len(sorted_trajectories[target_i])):
                margin_list.append(float(
                    self.all_trajectories[target_i][trajectory_i][3][0]
                ))

            idx_list = np.argsort(margin_list)[::-1]

            for id_i in range(len(idx_list)):
                idx = idx_list[id_i]
                sorted_trajectories[target_i][id_i] = \
                    self.all_trajectories[target_i][idx]

        self.sorted_trajectories = np.array(sorted_trajectories, dtype=object)
        self.target_i = 0
        self.trajectory_i = 0

    def updateImages(self):
        """Updates images on event"""

        # Update slice
        self.updateProbeView()
        # Update image
        self.subplots.img_probe.setImage(self.current_slice)

    def update_3d(self, event):
        """Updates 3D render"""

        if not event.isExit():
            if event.buttons():
                self.subplots.v_3d.update()
                self.subplots.proxy_3d.update()

    def updateProbeView(self):
        """Updates the probe eye view and performs data slicing"""

        # Update current position
        self.current_pos = self.trajectory_checkpoints[self.checkpoint_i]
        # Update current slice
        self.current_slice = self.trajectory_slices[self.checkpoint_i]
        # Update vertical line pos
        if "v_line" in dir(self.subplots):
            self.subplots.v_line.setValue(
                self.trajectory_dist2targetList[self.checkpoint_i])

    def define_checkpoints(self):
        """Define checkpoints along current trajectory"""

        # Define start/stop points
        # Start some distance before entry and end 3mm after target
        start = (
            np.array(self.current_entry) - (
                np.array(self.current_direction) / np.sqrt(
                    self.current_direction[0] ** 2 +
                    self.current_direction[1] ** 2 +
                    self.current_direction[2] ** 2
                ) * 10
            )
        )
        stop = np.array(self.current_target)

        target = stop - (
            np.array(self.current_direction) / np.sqrt(
                self.current_direction[0] ** 2 +
                self.current_direction[1] ** 2 +
                self.current_direction[2] ** 2
            ) * 3
        )

        # Determine trajectory vector
        trajectory_vector = stop - start

        # Calculate distance entry-target
        start2target = np.sqrt(np.sum(
            [(self.vox_dims[j] * (target - start)) ** 2
                for j in range(3)]
        ))

        # Setup arrays
        self.trajectory_checkpoints = np.zeros((100, 3))
        self.trajectory_dist2targetList = np.zeros(100)
        self.trajectory_distances = np.zeros(100)

        # Loop over checkpoints and fill arrays
        first_pass = True
        for i in range(100):
            # Define checkpoint coordinates
            checkpoint = start + trajectory_vector * (i / 99)
            # Define distance to target (mm)
            dist2target = np.sqrt(np.sum(
                [(self.vox_dims[j] * (target - checkpoint)) ** 2
                    for j in range(3)]
            ))
            # Check whether we've passed the target
            dist2start = np.sqrt(np.sum(
                [(self.vox_dims[j] * (start - checkpoint)) ** 2
                    for j in range(3)]
            ))
            if dist2start > start2target:
                if first_pass:
                    first_pass = False
            else:
                dist2target = -dist2target
            # Define distance to critical structure
            checkpoint_idx = np.round(checkpoint)
            distance = self.distance_map[
                int(checkpoint_idx[0]),
                int(checkpoint_idx[1]),
                int(checkpoint_idx[2])
            ]
            # Store found results
            self.trajectory_checkpoints[i] = checkpoint
            self.trajectory_dist2targetList[i] = dist2target
            self.trajectory_distances[i] = distance

    def updateTrajectory(self, initial_pass: bool = False):
        """Handles selection of new trajectory"""

        # Select new current trajectory
        self.current_trajectory = \
            self.sorted_trajectories[self.target_i][self.trajectory_i]

        # Store direction, entry, target
        self.current_direction = tuple(self.current_trajectory[0])
        self.current_entry = tuple(self.current_trajectory[1])
        self.current_target = tuple(self.current_trajectory[2])

        # Define checkpoints
        self.define_checkpoints()

        # Define proper vectors. These vectors should both be
        # perpendicular to the trajectory direction vector and
        # to each other. We set vector1 to (1, 0, v3)
        n = np.array(object=self.current_direction)
        n = n / np.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2)

        vector1 = (
            np.array([1, 0, -(n[0] / n[2])]) /
            np.sqrt(1 ** 2 + 1 ** 2 + (-(n[0] / n[2])) ** 2)
        )
        vector2 = np.cross(n, vector1)

        # Define shape
        self.slice_shape = (max(self.shape), max(self.shape))

        # Determine proper aspect ratios
        self.aspect_y = np.sqrt(sum(
            [(vector1[i] * self.vox_dims[i]) ** 2 for i in range(3)]
        ))
        self.aspect_x = np.sqrt(sum(
            [(vector2[i] * self.vox_dims[i]) ** 2 for i in range(3)]
        ))

        # Setup vectors in appropriate format
        self.vectors = tuple((tuple(vector1), tuple(vector2)))

        # Loop over checkpoints and slice data
        self.trajectory_slices = np.zeros((
            len(self.trajectory_checkpoints),
            self.slice_shape[0],
            self.slice_shape[1]
        ))

        for checkpoint_i in range(len(self.trajectory_checkpoints)):
            slice_origin = tuple(
                np.array(self.trajectory_checkpoints[checkpoint_i]) -
                (max(self.shape) // 2) * (vector1 + vector2)
            )

            self.trajectory_slices[checkpoint_i] = pg.functions.affineSlice(
                self.data, self.slice_shape, slice_origin, self.vectors,
                axes=(0, 1, 2), order=0
            )

        # Setup current position to target checkpoint
        if initial_pass:
            self.checkpoint_i = len(self.trajectory_checkpoints) - 1
        self.current_pos = \
            tuple(self.trajectory_checkpoints[self.checkpoint_i])

        # Setup appropriate graph range
        if not initial_pass:
            # Clear plot
            self.subplots.v_graph.clear()
            # Plot new trajectory data
            self.subplots.v_graph.plot(
                x=self.trajectory_dist2targetList,
                y=self.trajectory_distances
            )
            # Re-add lines
            self.subplots.v_graph.addItem(self.subplots.h_line)
            self.subplots.v_graph.addItem(self.subplots.v_line)

            # Adjust limits
            self.subplots.v_graph.setXRange(
                self.trajectory_dist2targetList[0],
                self.trajectory_dist2targetList[-1], padding=0
            )
            self.subplots.v_graph.setYRange(
                0.0, 10.0, padding=0
            )
            self.subplots.v_graph.setLimits(
                xMin=self.trajectory_dist2targetList[0],
                xMax=self.trajectory_dist2targetList[-1],
                yMin=0
            )

            # Update vertical line bounds
            self.subplots.v_line.setBounds((
                self.trajectory_dist2targetList[0],
                self.trajectory_dist2targetList[-1]
            ))

            self.updateImages()
            self.update3dLineColors()

    def zoomImage(self, delta, img_str):
        """Zooms in/out on a certain image"""
        scale_factor = 1.0 + delta * 0.1

        if img_str == "probe":
            x_scale = self.slice_shape[0] // 2
            y_scale = self.slice_shape[1] // 2
            self.subplots.v_probe.scaleBy(
                s=[scale_factor, scale_factor],
                center=(x_scale, y_scale))
        elif img_str == "3d":
            current_distance = self.subplots.v_3d.opts['distance']
            current_elevation = self.subplots.v_3d.opts['elevation']
            current_azimuth = self.subplots.v_3d.opts['azimuth']

            self.subplots.v_3d.setCameraPosition(
                distance=current_distance / scale_factor,
                elevation=current_elevation, azimuth=current_azimuth)

            self.subplots.proxy_3d.update()

    def update3dLineColors(self):
        """Updates the 3D plot line colors"""

        for trajectory_id, plot_item in self.trajectoryPlots.items():
            id_split = trajectory_id.split("_")
            target_i = int(id_split[0])
            trajectory_i = int(id_split[1])

            if (
                target_i == self.target_i and
                trajectory_i == self.trajectory_i
            ):
                color = (1., 0., 0., 1.0)
                width = 5
            else:
                color = (1., 1., 0., 0.5)
                width = 1

            plot_item.setData(color=color, width=width)
            plot_item.update()

        self.subplots.v_3d.update()
        self.subplots.proxy_3d.update()

    def selectTarget(self):
        """Updates the target currently looked at"""

        # Set new target / trajectory number
        self.target_i = self.targetList.currentRow()
        self.trajectory_i = 0

        # Update trajectoryList (if applicable)
        if 'trajectoryList' in dir(self):
            self.trajectoryList.clear()

            row = 0
            for trajectory_i in range(
                len(self.sorted_trajectories[self.target_i])
            ):
                margin = self.sorted_trajectories[
                    self.target_i][trajectory_i][-1][0]
                label = (
                    f"Path {trajectory_i + 1:2d} "
                    f"- Margin: {margin:.2f}"
                )
                self.trajectoryList.insertItem(row, label)
                row += 1

            self.trajectoryList.setCurrentRow(0)

        # Update views
        self.updateTrajectory()

    def selectTrajectory(self):
        """Updates the trajectory currently in view"""

        # Set new trajectory number
        self.trajectory_i = self.trajectoryList.currentRow()

        # Update views
        self.updateTrajectory()

    def selectScan(self):
        """Updates the scan currently in view"""

        # Obtain scan name
        scan_name = self.scanList.currentItem().text()

        # Update view data field
        self.data = self.scans[scan_name]
        self.shape = np.shape(self.data)

        # Update slicing
        self.updateTrajectory()
        # Update image/text
        self.updateImages()
        # self.updateText()

    def imageMouseDragEvent_3d(self, event):
        """Handles drag event on 3D render"""
        view = "3d"
        self.imageMouseDragEvent(event, view)

    def imageMouseDragEvent(self, event, view):
        """ Implementation of right drag panning"""

        # Manually accept event
        event.accept()

        # Check for right-click drag
        if event.button() == QtCore.Qt.LeftButton:
            # Extract start position + update is this is a start
            if event.isStart():
                self.drag_startpos = event.buttonDownPos()
                self.drag_startElevation = self.subplots.v_3d.opts['elevation']
                self.drag_startAzimuth = self.subplots.v_3d.opts['azimuth']
            # Reset if this is the end
            elif event.isFinish():
                self.drag_startpos = None
                self.drag_startElevation = None
                self.drag_startAzimuth = None
            # Translate image upon dragging
            else:
                start_x = self.drag_startpos.x()
                start_y = self.drag_startpos.y()

                current_x = event.pos().x()
                current_y = event.pos().y()

                # Update view
                current_distance = self.subplots.v_3d.opts['distance']
                current_elevation = \
                    self.drag_startElevation + (current_y - start_y)
                current_azimuth = \
                    self.drag_startAzimuth + (current_x - start_x)

                self.subplots.v_3d.setCameraPosition(
                    distance=current_distance,
                    elevation=current_elevation,
                    azimuth=current_azimuth
                )

                self.subplots.proxy_3d.update()

    def keyPressEvent(self, event):
        """Handles general keypress events"""

        self.imageKeyPressEvent(event)

    def imageKeyPressEvent(self, event):
        """ Handles key presses
        - Up/down -> scrolling
        """

        # Checks for up/down key presses (scroll)
        if event.key() in (QtCore.Qt.Key_Up, QtCore.Qt.Key_Down):
            # Define direction
            if event.key() == QtCore.Qt.Key_Up:
                scroll = 1
            elif event.key() == QtCore.Qt.Key_Down:
                scroll = -1

            # Setup new checkpoint (if not on edge)
            if ((
                scroll > 0 and
                self.checkpoint_i >= len(self.trajectory_checkpoints) - 1
            ) or (
                scroll < 0 and self.checkpoint_i == 0
            )):
                pass
            else:
                self.checkpoint_i += scroll

            # Update probe view            # self.updateProbeView()
            self.updateImages()

    def imageWheelEvent_probe(self, event):
        """Handles mousewheel event on probe view"""
        view = "probe"
        self.imageWheelEvent(event, view)

    def imageWheelEvent_3d(self, event):
        """Handles mousewheel event on 3d view"""
        view = "3d"
        self.imageWheelEvent(event, view)

    def imageWheelEvent(self, event, view):
        """ Zoom using mouse wheel"""

        # Check for mouse wheel movement direction
        if event.delta() > 0:
            # Wheel away from user -> zoom in
            delta = 1
        else:
            # Wheel towards user -> zoom out
            delta = -1

        # Zoom appropriate image
        self.zoomImage(delta, view)

    def vLineDragged(self):
        """Handles dragging of vertical line"""

        # Extract position
        dist2target = self.subplots.v_line.value()

        # Loop over checkpoints and check for the best fit
        opt_checkpoint_i = 0
        min_diff = 100

        for checkpoint_i in range(len(self.trajectory_checkpoints)):
            actual_dist = self.trajectory_dist2targetList[checkpoint_i]
            diff = abs(dist2target - actual_dist)

            if diff < min_diff:
                opt_checkpoint_i = checkpoint_i
                min_diff = diff

        # Update checkpoint and images
        self.checkpoint_i = int(opt_checkpoint_i)
        self.updateImages()

    def hLineDragged(self):
        """Handles dragging of horizontal line"""

        # Extract position
        new_margin = self.subplots.h_line.value()
        # Set new margin
        self.margin = new_margin
        self.margin_pix = self.margin / self.aspect_x
        # Remove old plot
        self.subplots.v_probe.removeItem(self.subplots.probe_margin)
        # Set new plot
        self.subplots.probe_margin = QtWidgets.QGraphicsEllipseItem(
            max(self.shape) // 2 - self.margin_pix,
            max(self.shape) // 2 - self.margin_pix,
            2 * self.margin_pix, 2 * self.margin_pix
        )
        self.subplots.probe_margin.setPen(self.margin_pen)
        # Replace plot
        self.subplots.v_probe.addItem(self.subplots.probe_margin)

        # Set margin editline
        self.marginSetting.setText(f"{self.margin:.2f}")

    def editMargin(self):
        """Handles margin changing via editline widget"""

        margin_str = self.marginSetting.text()

        try:
            self.margin = float(margin_str)
        except ValueError:
            return

        self.margin_pix = float(margin_str) / self.aspect_x

        # Set new h_line value
        self.subplots.h_line.setValue(self.margin)

        # Remove old plot
        self.subplots.v_probe.removeItem(self.subplots.probe_margin)
        # Set new plot
        self.subplots.probe_margin = QtWidgets.QGraphicsEllipseItem(
            max(self.shape) // 2 - self.margin_pix,
            max(self.shape) // 2 - self.margin_pix,
            2 * self.margin_pix, 2 * self.margin_pix
        )
        self.subplots.probe_margin.setPen(self.margin_pen)
        # Replace plot
        self.subplots.v_probe.addItem(self.subplots.probe_margin)


def main(subject_paths, suggested_trajectories):
    """Main function for path selection GUI"""

    app = QtGui.QApplication(sys.argv)

    path_selection = PathSelection(
        app, subject_paths, suggested_trajectories)
    path_selection.show()

    QtGui.QApplication.exec_()

    path_selection = None

    return None

    # return path_selection.all_trajectories

    # if len(path_selection.target_points) > 0:
    #     return path_selection.target_points
    # else:
    #     raise UserWarning("No target points were selected!"
    #                       " Exiting...")


if __name__ == '__main__':
    main({})
