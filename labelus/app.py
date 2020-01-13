import functools
import os
import os.path as osp
import re
import webbrowser

from qtpy import QtCore
from qtpy.QtCore import Qt
from qtpy import QtGui
from qtpy import QtWidgets

from labelus import __appname__
from labelus import PY2
from labelus import QT5

from . import utils
from labelus.config import get_config
from labelus.label_file import LabelFile
from labelus.label_file import LabelFileError
from labelus.logger import logger
from labelus.shape import DEFAULT_FILL_COLOR
from labelus.shape import DEFAULT_LINE_COLOR
from labelus.shape import Shape
from labelus.widgets import Canvas
from labelus.widgets import ColorDialog
from labelus.widgets import EscapableQListWidget
from labelus.widgets import LabelDialog
from labelus.widgets import LabelQListWidget
from labelus.widgets import ToolBar
from labelus.widgets import ZoomWidget



class MainWindow(QtWidgets.QMainWindow):

    FIT_WINDOW, FIT_WIDTH, MANUAL_ZOOM = 0, 1, 2

    def __init__(
        self,
        config=None,
        #filename=None,
        filename_date1 = None, #date1
        filename_date2 = None, #date2
        output=None,
        output_file=None,
        output_dir=None,
    ):
        if output is not None:
            logger.warning(
                'argument output is deprecated, use output_file instead'
            )
            if output_file is None:
                output_file = output

        # see labelus/config/default_config.yaml for valid configuration
        if config is None:
            config = get_config()
        self._config = config

        super(MainWindow, self).__init__()
        self.setWindowTitle(__appname__)

        # Whether we need to save or not.
        self.dirty = False

        self._noSelectionSlot = False


        self.labelList = LabelQListWidget()
        self.lastOpenDir = None

        self.labelList.itemActivated.connect(self.labelSelectionChanged)
        self.labelList.itemSelectionChanged.connect(self.labelSelectionChanged)
        # Connect to itemChanged to detect checkbox changes.
        self.labelList.itemChanged.connect(self.labelItemChanged)
        self.labelList.setDragDropMode(
            QtWidgets.QAbstractItemView.InternalMove)
        self.labelList.setParent(self)
        self.shape_dock = QtWidgets.QDockWidget('Polygon Labels', self)
        self.shape_dock.setObjectName('Labels')
        self.shape_dock.setWidget(self.labelList)


        #fileSearch --> bbSearch
        self.locationSearch = QtWidgets.QLineEdit()
        self.locationSearch.setPlaceholderText('Search Location')
        self.locationSearch.textChanged.connect(self.locationSearchChanged)
        self.locationListWidget = QtWidgets.QListWidget()
        self.locationListWidget.itemSelectionChanged.connect(
            self.locationSelectionChanged
        )
        locationListLayout = QtWidgets.QVBoxLayout()
        locationListLayout.setContentsMargins(0, 0, 0, 0)
        locationListLayout.setSpacing(0)
        locationListLayout.addWidget(self.locationSearch)
        locationListLayout.addWidget(self.locationListWidget)
        self.location_dock = QtWidgets.QDockWidget(u'Location List', self)
        self.location_dock.setObjectName(u'Location')
        locationListWidget = QtWidgets.QWidget()
        locationListWidget.setLayout(locationListLayout)
        self.location_dock.setWidget(locationListWidget)

        self.zoomWidget = ZoomWidget()
        self.colorDialog = ColorDialog(parent=self)

        self.canvas = self.labelList.canvas = Canvas(
            epsilon=self._config['epsilon'],
        )
        self.canvas.zoomRequest.connect(self.zoomRequest)

        scrollArea = QtWidgets.QScrollArea()
        scrollArea.setWidget(self.canvas)
        scrollArea.setWidgetResizable(True)
        self.scrollBars = {
            Qt.Vertical: scrollArea.verticalScrollBar(),
            Qt.Horizontal: scrollArea.horizontalScrollBar(),
        }
        self.canvas.scrollRequest.connect(self.scrollRequest)

        self.canvas.newShape.connect(self.newShape)
        self.canvas.shapeMoved.connect(self.setDirty)
        self.canvas.selectionChanged.connect(self.shapeSelectionChanged)
        self.canvas.drawingPolygon.connect(self.toggleDrawingSensitive)

        self.setCentralWidget(scrollArea)

        features = QtWidgets.QDockWidget.DockWidgetFeatures()
        for dock in ['shape_dock', 'location_dock']:
            if self._config[dock]['closable']:
                features = features | QtWidgets.QDockWidget.DockWidgetClosable
            if self._config[dock]['floatable']:
                features = features | QtWidgets.QDockWidget.DockWidgetFloatable
            if self._config[dock]['movable']:
                features = features | QtWidgets.QDockWidget.DockWidgetMovable
            getattr(self, dock).setFeatures(features)
            if self._config[dock]['show'] is False:
                getattr(self, dock).setVisible(False)

        self.addDockWidget(Qt.RightDockWidgetArea, self.shape_dock)
        self.addDockWidget(Qt.RightDockWidgetArea, self.location_dock)

        # Actions
        action = functools.partial(utils.newAction, self)
        shortcuts = self._config['shortcuts']
        quit = action('&Quit', self.close, shortcuts['quit'], 'quit',
                      'Quit application')
        # open_ = action('&Open', self.openFile, shortcuts['open'], 'open',
        #                'Open image or label file')
        openpair_ = action('&OpenPair', self.openPair, shortcuts['openpair'], 'open',
                          'Open Image Pairs')
        opendir = action('&Open Dir', self.openDirDialog,
                         shortcuts['open_dir'], 'open', u'Open Dir')
        openNextPair = action(
            '&Next Pair',
            self.openNextPair,
            shortcuts['open_next'],
            'next',
            u'Open next (hold Ctl+Shift to copy labels)',
            enabled=False,
        )
        openPrevPair = action(
            '&Prev Pair',
            self.openPrevPair,
            shortcuts['open_prev'],
            'prev',
            u'Open prev (hold Ctl+Shift to copy labels)',
            enabled=False,
        )
        save = action('&Save', self.saveFile, shortcuts['save'], 'save',
                      'Save labels to file', enabled=False)
        saveAs = action('&Save As', self.saveFileAs, shortcuts['save_as'],
                        'save-as', 'Save labels to a different file',
                        enabled=False)

        deleteFile = action(
            '&Delete File',
            self.deleteFile,
            shortcuts['delete_file'],
            'delete',
            'Delete current label file',
            enabled=False)

        changeOutputDir = action(
            '&Change Output Dir',
            slot=self.changeOutputDirDialog,
            shortcut=shortcuts['save_to'],
            icon='open',
            tip=u'Change where annotations are loaded/saved'
        )

        saveAuto = action(
            text='Save &Automatically',
            slot=lambda x: self.actions.saveAuto.setChecked(x),
            icon='save',
            tip='Save automatically',
            checkable=True,
            enabled=True,
        )
        saveAuto.setChecked(self._config['auto_save'])

        close = action('&Close', self.closeFile, shortcuts['close'], 'close',
                       'Close current file')
        color1 = action('Polygon &Line Color', self.chooseColor1,
                        shortcuts['edit_line_color'], 'color_line',
                        'Choose polygon line color')
        color2 = action('Polygon &Fill Color', self.chooseColor2,
                        shortcuts['edit_fill_color'], 'color',
                        'Choose polygon fill color')

        toggle_keep_prev_mode = action(
            'Keep Previous Annotation',
            self.toggleKeepPrevMode,
            shortcuts['toggle_keep_prev_mode'], None,
            'Toggle "keep pevious annotation" mode',
            checkable=True)
        toggle_keep_prev_mode.setChecked(self._config['keep_prev'])

        toggleDate = action('Toggle date pair images', self.toggleDatePair,
                            shortcuts['toggle_date'], None, 'Toogle "date image" mode',
                            checkable=True)

        createMode = action(
            'Create Polygons',
            lambda: self.toggleDrawMode(False, createMode='polygon'),
            shortcuts['create_polygon'],
            'objects',
            'Start drawing polygons',
            enabled=False,
        )
        createRectangleMode = action(
            'Create Rectangle',
            lambda: self.toggleDrawMode(False, createMode='rectangle'),
            shortcuts['create_rectangle'],
            'objects',
            'Start drawing rectangles',
            enabled=False,
        )
        createCircleMode = action(
            'Create Circle',
            lambda: self.toggleDrawMode(False, createMode='circle'),
            shortcuts['create_circle'],
            'objects',
            'Start drawing circles',
            enabled=False,
        )
        createLineMode = action(
            'Create Line',
            lambda: self.toggleDrawMode(False, createMode='line'),
            shortcuts['create_line'],
            'objects',
            'Start drawing lines',
            enabled=False,
        )
        createPointMode = action(
            'Create Point',
            lambda: self.toggleDrawMode(False, createMode='point'),
            shortcuts['create_point'],
            'objects',
            'Start drawing points',
            enabled=False,
        )
        createLineStripMode = action(
            'Create LineStrip',
            lambda: self.toggleDrawMode(False, createMode='linestrip'),
            shortcuts['create_linestrip'],
            'objects',
            'Start drawing linestrip. Ctrl+LeftClick ends creation.',
            enabled=False,
        )
        editMode = action('Edit Polygons', self.setEditMode,
                          shortcuts['edit_polygon'], 'edit',
                          'Move and edit the selected polygons', enabled=False)

        delete = action('Delete Polygons', self.deleteSelectedShape,
                        shortcuts['delete_polygon'], 'cancel',
                        'Delete the selected polygons', enabled=False)
        copy = action('Duplicate Polygons', self.copySelectedShape,
                      shortcuts['duplicate_polygon'], 'copy',
                      'Create a duplicate of the selected polygons',
                      enabled=False)
        undoLastPoint = action('Undo last point', self.canvas.undoLastPoint,
                               shortcuts['undo_last_point'], 'undo',
                               'Undo last drawn point', enabled=False)
        addPointToEdge = action(
            'Add Point to Edge',
            self.canvas.addPointToEdge,
            shortcuts['add_point_to_edge'],
            'edit',
            'Add point to the nearest edge',
            enabled=False,
        )

        undo = action('Undo', self.undoShapeEdit, shortcuts['undo'], 'undo',
                      'Undo last add and edit of shape', enabled=False)

        hideAll = action('&Hide\nPolygons',
                         functools.partial(self.togglePolygons, False),
                         icon='eye', tip='Hide all polygons', enabled=False)
        showAll = action('&Show\nPolygons',
                         functools.partial(self.togglePolygons, True),
                         icon='eye', tip='Show all polygons', enabled=False)

        help = action('&Tutorial', self.tutorial, icon='help',
                      tip='Show tutorial page')

        zoom = QtWidgets.QWidgetAction(self)
        zoom.setDefaultWidget(self.zoomWidget)
        self.zoomWidget.setWhatsThis(
            'Zoom in or out of the image. Also accessible with '
            '{} and {} from the canvas.'
            .format(
                utils.fmtShortcut(
                    '{},{}'.format(
                        shortcuts['zoom_in'], shortcuts['zoom_out']
                    )
                ),
                utils.fmtShortcut("Ctrl+Wheel"),
            )
        )
        self.zoomWidget.setEnabled(False)

        zoomIn = action('Zoom &In', functools.partial(self.addZoom, 1.1),
                        shortcuts['zoom_in'], 'zoom-in',
                        'Increase zoom level', enabled=False)
        zoomOut = action('&Zoom Out', functools.partial(self.addZoom, 0.9),
                         shortcuts['zoom_out'], 'zoom-out',
                         'Decrease zoom level', enabled=False)
        zoomOrg = action('&Original size',
                         functools.partial(self.setZoom, 100),
                         shortcuts['zoom_to_original'], 'zoom',
                         'Zoom to original size', enabled=False)
        fitWindow = action('&Fit Window', self.setFitWindow,
                           shortcuts['fit_window'], 'fit-window',
                           'Zoom follows window size', checkable=True,
                           enabled=False)
        fitWidth = action('Fit &Width', self.setFitWidth,
                          shortcuts['fit_width'], 'fit-width',
                          'Zoom follows window width',
                          checkable=True, enabled=False)
        # Group zoom controls into a list for easier toggling.
        zoomActions = (self.zoomWidget, zoomIn, zoomOut, zoomOrg,
                       fitWindow, fitWidth)
        self.zoomMode = self.FIT_WINDOW
        fitWindow.setChecked(Qt.Checked)
        self.scalers = {
            self.FIT_WINDOW: self.scaleFitWindow,
            self.FIT_WIDTH: self.scaleFitWidth,
            # Set to one to scale to 100% when loading files.
            self.MANUAL_ZOOM: lambda: 1,
        }

        shapeLineColor = action(
            'Shape &Line Color', self.chshapeLineColor, icon='color-line',
            tip='Change the line color for this specific shape', enabled=False)
        shapeFillColor = action(
            'Shape &Fill Color', self.chshapeFillColor, icon='color',
            tip='Change the fill color for this specific shape', enabled=False)
        fill_drawing = action(
            'Fill Drawing Polygon',
            lambda x: self.canvas.setFillDrawing(x),
            None,
            'color',
            'Fill polygon while drawing',
            checkable=True,
            enabled=True,
        )
        fill_drawing.setChecked(True)

        # Lavel list context menu.
        labelMenu = QtWidgets.QMenu()
        utils.addActions(labelMenu, (delete,))
        self.labelList.setContextMenuPolicy(Qt.CustomContextMenu)
        self.labelList.customContextMenuRequested.connect(
            self.popLabelListMenu)

        # Store actions for further handling.
        self.actions = utils.struct(
            saveAuto=saveAuto,
            changeOutputDir=changeOutputDir,
            save=save, saveAs=saveAs, openpair=openpair_, close=close,
            deleteFile=deleteFile,
            lineColor=color1, fillColor=color2,
            toggleKeepPrevMode=toggle_keep_prev_mode,
            toggleDate=toggleDate,
            delete=delete, copy=copy,
            undoLastPoint=undoLastPoint, undo=undo,
            addPointToEdge=addPointToEdge,
            createMode=createMode, editMode=editMode,
            createRectangleMode=createRectangleMode,
            createCircleMode=createCircleMode,
            createLineMode=createLineMode,
            createPointMode=createPointMode,
            createLineStripMode=createLineStripMode,
            shapeLineColor=shapeLineColor, shapeFillColor=shapeFillColor,
            zoom=zoom, zoomIn=zoomIn, zoomOut=zoomOut, zoomOrg=zoomOrg,
            fitWindow=fitWindow, fitWidth=fitWidth,
            zoomActions=zoomActions,
            openNextPair=openNextPair, openPrevPair=openPrevPair,
            fileMenuActions=(openpair_, opendir, save, saveAs, close, quit),
            tool=(),
            # XXX: need to add some actions here to activate the shortcut
            editMenu=(
                copy,
                delete,
                None,
                undo,
                undoLastPoint,
                None,
                addPointToEdge,
                None,
                color1,
                color2,
                None,
                toggle_keep_prev_mode,
                toggleDate,
            ),
            # menu shown at right click
            menu=(
                createMode,
                createRectangleMode,
                createCircleMode,
                createLineMode,
                createPointMode,
                createLineStripMode,
                editMode,
                copy,
                delete,
                shapeLineColor,
                shapeFillColor,
                undo,
                undoLastPoint,
                addPointToEdge,
            ),
            onLoadActive=(
                close,
                createMode,
                createRectangleMode,
                createCircleMode,
                createLineMode,
                createPointMode,
                createLineStripMode,
                editMode,
            ),
            onShapesPresent=(saveAs, hideAll, showAll),
        )

        self.canvas.edgeSelected.connect(
            self.actions.addPointToEdge.setEnabled
        )

        self.menus = utils.struct(
            file=self.menu('&File'),
            edit=self.menu('&Edit'),
            view=self.menu('&View'),
            help=self.menu('&Help'),
            recentPairs=QtWidgets.QMenu('Open Pair &Recent'),
            labelList=labelMenu,
        )

        utils.addActions(
            self.menus.file,
            (
                # open_,
                openpair_,
                openNextPair,
                openPrevPair,
                opendir,
                # self.menus.recentFiles,
                self.menus.recentPairs,
                save,
                saveAs,
                saveAuto,
                changeOutputDir,
                close,
                deleteFile,
                None,
                quit,
            ),
        )
        utils.addActions(self.menus.help, (help,))
        utils.addActions(
            self.menus.view,
            (
                self.shape_dock.toggleViewAction(),
                self.location_dock.toggleViewAction(),
                None,
                fill_drawing,
                None,
                hideAll,
                showAll,
                None,
                zoomIn,
                zoomOut,
                zoomOrg,
                None,
                fitWindow,
                fitWidth,
                None,
            ),
        )

        self.menus.file.aboutToShow.connect(self.updateFileMenu)

        # Custom context menu for the canvas widget:
        utils.addActions(self.canvas.menus[0], self.actions.menu)
        utils.addActions(
            self.canvas.menus[1],
            (
                action('&Copy here', self.copyShape),
                action('&Move here', self.moveShape),
            ),
        )

        self.tools = self.toolbar('Tools')
        # Menu buttons on Left
        self.actions.tool = (
            # open_,
            openpair_,
            opendir,
            openNextPair,
            openPrevPair,
            save,
            deleteFile,
            None,
            createMode,
            editMode,
            copy,
            delete,
            undo,
            None,
            zoomIn,
            zoom,
            zoomOut,
            fitWindow,
            fitWidth,
        )

        self.statusBar().showMessage('%s started.' % __appname__)
        self.statusBar().show()

        if output_file is not None and self._config['auto_save']:
            logger.warn(
                'If `auto_save` argument is True, `output_file` argument '
                'is ignored and output filename is automatically '
                'set as IMAGE_BASENAME.json.'
            )
        self.output_file = output_file
        self.output_dir = output_dir

        # Application state.
        self.image_date1 = QtGui.QImage()
        self.image_date2 = QtGui.QImage()
        self.image_date1Path = None
        self.image_date2Path = None
        self.recentPairs = []
        self.maxRecent = 7
        self.lineColor = None
        self.fillColor = None
        self.otherData = None
        self.zoom_level = 100
        self.fit_window = False

        if filename_date1 is not None and filename_date2 is not None and osp.isdir(filename_date1):
            #Only filenames allowed, no directory
            self.importDirPairs(filename_date1, load=False)
        else:
            self.filename_date1 = filename_date1
            self.filename_date2 = filename_date2

        if config['location_search']:
            self.locationSearch.setText(config['location_search'])
            self.locationSearchChanged()

        # XXX: Could be completely declarative.
        # Restore application settings.
        self.settings = QtCore.QSettings('labelus', 'labelus')
        # FIXME: QSettings.value can return None on PyQt4
        self.recentPairs = self.settings.value('recentPairs', []) or []
        size = self.settings.value('window/size', QtCore.QSize(600, 500))
        position = self.settings.value('window/position', QtCore.QPoint(0, 0))
        self.resize(size)
        self.move(position)
        # or simply:
        # self.restoreGeometry(settings['window/geometry']
        self.restoreState(
            self.settings.value('window/state', QtCore.QByteArray()))
        self.lineColor = QtGui.QColor(
            self.settings.value('line/color', Shape.line_color))
        self.fillColor = QtGui.QColor(
            self.settings.value('fill/color', Shape.fill_color))
        Shape.line_color = self.lineColor
        Shape.fill_color = self.fillColor

        # Populate the File menu dynamically.
        self.updateFileMenu()
        # Since loading the file may take some time,
        # make sure it runs in the background.
        if self.filename_date1 is not None and self.filename_date2 is not None:
            self.queueEvent(functools.partial(self.loadFilePairs, self.filename_date1, self.filename_date2))

        # Callbacks:
        self.zoomWidget.valueChanged.connect(self.paintCanvas)

        self.populateModeActions()

        # self.firstStart = True
        # if self.firstStart:
        #    QWhatsThis.enterWhatsThisMode()

    def menu(self, title, actions=None):
        menu = self.menuBar().addMenu(title)
        if actions:
            utils.addActions(menu, actions)
        return menu

    def toolbar(self, title, actions=None):
        toolbar = ToolBar(title)
        toolbar.setObjectName('%sToolBar' % title)
        # toolbar.setOrientation(Qt.Vertical)
        toolbar.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        if actions:
            utils.addActions(toolbar, actions)
        self.addToolBar(Qt.LeftToolBarArea, toolbar)
        return toolbar

    # Support Functions

    def noShapes(self):
        return not self.labelList.itemsToShapes

    def populateModeActions(self):
        tool, menu = self.actions.tool, self.actions.menu
        self.tools.clear()
        utils.addActions(self.tools, tool)
        self.canvas.menus[0].clear()
        utils.addActions(self.canvas.menus[0], menu)
        self.menus.edit.clear()
        actions = (
            self.actions.createMode,
            self.actions.createRectangleMode,
            self.actions.createCircleMode,
            self.actions.createLineMode,
            self.actions.createPointMode,
            self.actions.createLineStripMode,
            self.actions.editMode,
        )
        utils.addActions(self.menus.edit, actions + self.actions.editMenu)

    def setDirty(self):
        if self._config['auto_save'] or self.actions.saveAuto.isChecked():
            # label_file = osp.splitext(self.imagePath)[0] + '.json'
            label_file = osp.splitext(self.image_date1Path)[0].split('.')[0] + '.json'
            if self.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = osp.join(self.output_dir, label_file_without_path)
            self.saveLabels(label_file)
            return
        self.dirty = True
        self.actions.save.setEnabled(True)
        self.actions.undo.setEnabled(self.canvas.isShapeRestorable)
        title = __appname__
        # if self.filename is not None:
        #     title = '{} - {}*'.format(title, self.filename)
        if self.filename_date1 is not None and self.filename_date2 is not None:
            title = '{} - {}*'.format(title, osp.splitext(self.filename_date1)[0])
        self.setWindowTitle(title)

    def setClean(self):
        self.dirty = False
        self.actions.save.setEnabled(False)
        self.actions.createMode.setEnabled(True)
        self.actions.createRectangleMode.setEnabled(True)
        self.actions.createCircleMode.setEnabled(True)
        self.actions.createLineMode.setEnabled(True)
        self.actions.createPointMode.setEnabled(True)
        self.actions.createLineStripMode.setEnabled(True)
        title = __appname__
        # if self.filename is not None:
        #     title = '{} - {}'.format(title, self.filename)
        if self.filename_date1 is not None and self.filename_date2 is not None:
            title = '{} - {}'.format(title, osp.splitext(self.filename_date1)[0])
        self.setWindowTitle(title)

        if self.hasLabelFile():
            self.actions.deleteFile.setEnabled(True)
        else:
            self.actions.deleteFile.setEnabled(False)

    def toggleActions(self, value=True):
        """Enable/Disable widgets which depend on an opened image."""
        for z in self.actions.zoomActions:
            z.setEnabled(value)
        for action in self.actions.onLoadActive:
            action.setEnabled(value)

    def queueEvent(self, function):
        QtCore.QTimer.singleShot(0, function)

    def status(self, message, delay=5000):
        self.statusBar().showMessage(message, delay)

    def resetState(self):
        self.labelList.clear()
        # self.filename = None
        self.filename_date1 = None
        self.filename_date2 = None
        # self.imagePath = None
        self.image_date1Path = None
        self.image_date2Path = None
        # self.imageData = None
        self.image_date1Data = None
        self.image_date2Data = None
        self.labelFile = None
        self.otherData = None
        self.canvas.resetState()

    def currentItem(self):
        items = self.labelList.selectedItems()
        if items:
            return items[0]
        return None

    # def addRecentFile(self, filename):
    #     if filename in self.recentFiles:
    #         self.recentFiles.remove(filename)
    #     elif len(self.recentFiles) >= self.maxRecent:
    #         self.recentFiles.pop()
    #     self.recentFiles.insert(0, filename)
    def addRecentPair(self, filename_date1, filename_date2):
        if (filename_date1, filename_date2) in self.recentPairs:
            self.recentPairs.remove((filename_date1, filename_date2))
        elif len(self.recentPairs) >= self.maxRecent:
            self.recentPairs.pop()
        self.recentPairs.insert(0, (filename_date1, filename_date2))

    # Callbacks

    def undoShapeEdit(self):
        self.canvas.restoreShape()
        self.labelList.clear()
        self.loadShapes(self.canvas.shapes)
        self.actions.undo.setEnabled(self.canvas.isShapeRestorable)

    def tutorial(self):
        url = 'https://github.com/granularai/labelus/tree/labelus/examples/tutorial'  # NOQA
        webbrowser.open(url)

    def toggleDrawingSensitive(self, drawing=True):
        """Toggle drawing sensitive.

        In the middle of drawing, toggling between modes should be disabled.
        """
        self.actions.editMode.setEnabled(not drawing)
        self.actions.undoLastPoint.setEnabled(drawing)
        self.actions.undo.setEnabled(not drawing)
        self.actions.delete.setEnabled(not drawing)

    def toggleDrawMode(self, edit=True, createMode='polygon'):
        self.canvas.setEditing(edit)
        self.canvas.createMode = createMode
        if edit:
            self.actions.createMode.setEnabled(True)
            self.actions.createRectangleMode.setEnabled(True)
            self.actions.createCircleMode.setEnabled(True)
            self.actions.createLineMode.setEnabled(True)
            self.actions.createPointMode.setEnabled(True)
            self.actions.createLineStripMode.setEnabled(True)
        else:
            if createMode == 'polygon':
                self.actions.createMode.setEnabled(False)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == 'rectangle':
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(False)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == 'line':
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(False)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == 'point':
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(False)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "circle":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(False)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(True)
            elif createMode == "linestrip":
                self.actions.createMode.setEnabled(True)
                self.actions.createRectangleMode.setEnabled(True)
                self.actions.createCircleMode.setEnabled(True)
                self.actions.createLineMode.setEnabled(True)
                self.actions.createPointMode.setEnabled(True)
                self.actions.createLineStripMode.setEnabled(False)
            else:
                raise ValueError('Unsupported createMode: %s' % createMode)
        self.actions.editMode.setEnabled(not edit)

    def setEditMode(self):
        self.toggleDrawMode(True)

    def updateFileMenu(self):
        # current = self.filename
        current_date1 = self.filename_date1
        current_date2 = self.filename_date2

        def exists(filename_date1, filename_date2):
            return osp.exists(str(filename_date1)) and osp.exists(str(filename_date2))

        menu = self.menus.recentPairs
        menu.clear()
        pairs = [f for f in self.recentPairs if f[0] != current_date1 and f[1] != current_date2 and exists(f[0], f[1])]
        for i, f in enumerate(pairs):
            icon = utils.newIcon('labels')
            action = QtWidgets.QAction(
                icon, '&%d %s %s' % (i + 1, QtCore.QFileInfo(f[0]).fileName(), QtCore.QFileInfo(f[1]).fileName()), self)
            action.triggered.connect(functools.partial(self.loadRecentPair, f[0], f[1]))
            menu.addAction(action)

    def popLabelListMenu(self, point):
        self.menus.labelList.exec_(self.labelList.mapToGlobal(point))

    def validateLabel(self, label):
        # no validation
        if self._config['validate_label'] is None:
            return True

        for i in range(self.uniqLabelList.count()):
            label_i = self.uniqLabelList.item(i).text()
            if self._config['validate_label'] in ['exact', 'instance']:
                if label_i == label:
                    return True
            if self._config['validate_label'] == 'instance':
                m = re.match(r'^{}-[0-9]*$'.format(label_i), label)
                if m:
                    return True
        return False

    def locationSearchChanged(self):
        self.importDirPairs(
            self.lastOpenDir,
            pattern=self.locationSearch.text(),
            load=False,
        )

    def locationSelectionChanged(self):
        items = self.locationListWidget.selectedItems()
        if not items:
            return
        item = items[0]

        if not self.mayContinue():
            return

        currIndex = self.pairImageList.index((str(item.text()) + '.d1.jpg', str(item.text()) + '.d2.jpg'))
        if currIndex < len(self.pairImageList):
            filename_date1, filename_date2 = self.pairImageList[currIndex]
            if filename_date1 and filename_date2:
                self.loadPair(filename_date1, filename_date2)

    # React to canvas signals.
    def shapeSelectionChanged(self, selected_shapes):
        self._noSelectionSlot = True
        for shape in self.canvas.selectedShapes:
            shape.selected = False
        self.labelList.clearSelection()
        self.canvas.selectedShapes = selected_shapes
        for shape in self.canvas.selectedShapes:
            shape.selected = True
            item = self.labelList.get_item_from_shape(shape)
            item.setSelected(True)
        self._noSelectionSlot = False
        n_selected = len(selected_shapes)
        self.actions.delete.setEnabled(n_selected)
        self.actions.copy.setEnabled(n_selected)
        self.actions.shapeLineColor.setEnabled(n_selected)
        self.actions.shapeFillColor.setEnabled(n_selected)

    def addLabel(self, shape):
        item = QtWidgets.QListWidgetItem(shape.label)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self.labelList.itemsToShapes.append((item, shape))
        self.labelList.addItem(item)
        for action in self.actions.onShapesPresent:
            action.setEnabled(True)

    def remLabels(self, shapes):
        for shape in shapes:
            item = self.labelList.get_item_from_shape(shape)
            self.labelList.takeItem(self.labelList.row(item))

    def loadShapes(self, shapes, replace=True):
        self._noSelectionSlot = True
        for shape in shapes:
            self.addLabel(shape)
        self.labelList.clearSelection()
        self._noSelectionSlot = False
        self.canvas.loadShapes(shapes, replace=replace)

    def loadLabels(self, shapes):
        s = []
        for label, points, line_color, fill_color, shape_type, flags in shapes:
            shape = Shape(label=label, shape_type=shape_type)
            for x, y in points:
                shape.addPoint(QtCore.QPointF(x, y))
            shape.close()

            if line_color:
                shape.line_color = QtGui.QColor(*line_color)

            if fill_color:
                shape.fill_color = QtGui.QColor(*fill_color)

            default_flags = {}
            if self._config['label_flags']:
                for pattern, keys in self._config['label_flags'].items():
                    if re.match(pattern, label):
                        for key in keys:
                            default_flags[key] = False
            shape.flags = default_flags
            shape.flags.update(flags)

            s.append(shape)
        self.loadShapes(s)

    def saveLabels(self, filename):
        lf = LabelFile()

        def format_shape(s):
            return dict(
                label=s.label.encode('utf-8') if PY2 else s.label,
                line_color=s.line_color.getRgb()
                if s.line_color != self.lineColor else None,
                fill_color=s.fill_color.getRgb()
                if s.fill_color != self.fillColor else None,
                points=[(p.x(), p.y()) for p in s.points],
                shape_type=s.shape_type,
                flags=s.flags
            )

        shapes = [format_shape(shape) for shape in self.labelList.shapes]
        try:
            image_date1Path = osp.relpath(
                self.image_date1Path, osp.dirname(filename))
            image_date2Path = osp.relpath(
                self.image_date2Path, osp.dirname(filename))
            image_date1Data = self.image_date1Data if self._config['store_data'] else None
            image_date2Data = self.image_date2Data if self._config['store_data'] else None
            if osp.dirname(filename) and not osp.exists(osp.dirname(filename)):
                os.makedirs(osp.dirname(filename))
            lf.save(
                filename=filename,
                shapes=shapes,
                image_date1Path=image_date1Path,
                image_date2Path=image_date2Path,
                image_date1Data=image_date1Data,
                image_date2Data=image_date2Data,
                imageHeight=self.image_date1.height(),
                imageWidth=self.image_date1.width(),
                lineColor=self.lineColor.getRgb(),
                fillColor=self.fillColor.getRgb(),
                otherData=self.otherData,
                flags={},
            )
            self.labelFile = lf
            items = self.locationListWidget.findItems(
                osp.splitext(self.image_date1Path)[0].split('.')[0], Qt.MatchExactly
            )
            if len(items) > 0:
                if len(items) != 1:
                    raise RuntimeError('There are duplicate files.')
                items[0].setCheckState(Qt.Checked)
            # disable allows next and previous image to proceed
            # self.filename = filename
            return True
        except LabelFileError as e:
            self.errorMessage('Error saving label data', '<b>%s</b>' % e)
            return False

    def copySelectedShape(self):
        added_shapes = self.canvas.copySelectedShapes()
        self.labelList.clearSelection()
        for shape in added_shapes:
            self.addLabel(shape)
        self.setDirty()

    def labelSelectionChanged(self):
        if self._noSelectionSlot:
            return
        if self.canvas.editing():
            selected_shapes = []
            for item in self.labelList.selectedItems():
                shape = self.labelList.get_shape_from_item(item)
                selected_shapes.append(shape)
            if selected_shapes:
                self.canvas.selectShapes(selected_shapes)

    def labelItemChanged(self, item):
        shape = self.labelList.get_shape_from_item(item)
        label = str(item.text())
        if label != shape.label:
            shape.label = str(item.text())
            self.setDirty()
        else:  # User probably changed item visibility
            self.canvas.setShapeVisible(shape, item.checkState() == Qt.Checked)

    # Callback functions:

    def newShape(self):
        """Pop-up and give focus to the label editor.

        position MUST be in global coordinates.
        """
        text = str(self.labelList.count() + 1)
        if text:
            self.labelList.clearSelection()
            self.addLabel(self.canvas.setLastLabel(text, {}))
            self.actions.editMode.setEnabled(True)
            self.actions.undoLastPoint.setEnabled(False)
            self.actions.undo.setEnabled(True)
            self.setDirty()
        else:
            self.canvas.undoLastLine()
            self.canvas.shapesBackups.pop()

    def scrollRequest(self, delta, orientation):
        units = - delta * 0.1  # natural scroll
        bar = self.scrollBars[orientation]
        bar.setValue(bar.value() + bar.singleStep() * units)

    def setZoom(self, value):
        self.actions.fitWidth.setChecked(False)
        self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.MANUAL_ZOOM
        self.zoomWidget.setValue(value)

    def addZoom(self, increment=1.1):
        self.setZoom(self.zoomWidget.value() * increment)

    def zoomRequest(self, delta, pos):
        canvas_width_old = self.canvas.width()
        units = 1.1
        if delta < 0:
            units = 0.9
        self.addZoom(units)

        canvas_width_new = self.canvas.width()
        if canvas_width_old != canvas_width_new:
            canvas_scale_factor = canvas_width_new / canvas_width_old

            x_shift = round(pos.x() * canvas_scale_factor) - pos.x()
            y_shift = round(pos.y() * canvas_scale_factor) - pos.y()

            self.scrollBars[Qt.Horizontal].setValue(
                self.scrollBars[Qt.Horizontal].value() + x_shift)
            self.scrollBars[Qt.Vertical].setValue(
                self.scrollBars[Qt.Vertical].value() + y_shift)

    def setFitWindow(self, value=True):
        if value:
            self.actions.fitWidth.setChecked(False)
        self.zoomMode = self.FIT_WINDOW if value else self.MANUAL_ZOOM
        self.adjustScale()

    def setFitWidth(self, value=True):
        if value:
            self.actions.fitWindow.setChecked(False)
        self.zoomMode = self.FIT_WIDTH if value else self.MANUAL_ZOOM
        self.adjustScale()

    def togglePolygons(self, value):
        for item, shape in self.labelList.itemsToShapes:
            item.setCheckState(Qt.Checked if value else Qt.Unchecked)

    def loadPair(self, filename_date1=None, filename_date2=None):
        """Load the specified pair, or the last opened file if None."""
        # changing filePairListWidget loads file
        if ((filename_date1, filename_date2) in self.pairImageList and
                self.locationListWidget.currentRow() !=
                self.pairImageList.index((filename_date1, filename_date2))):
            self.locationListWidget.setCurrentRow(self.pairImageList.index((filename_date1, filename_date2)))
            self.locationListWidget.repaint()
            return

        self.resetState()
        self.canvas.setEnabled(False)
        if filename_date1 is None and filename_date2 is None:
            filename_date1 = self.settings.value('filename_date1', '')
            filename_date2 = self.settings.value('filename_date2', '')
        filename_date1 = str(filename_date1)
        filename_date2 = str(filename_date2)
        if not QtCore.QFile.exists(filename_date1) and not QtCore.QFile.exists(filename_date2):
            self.errorMessage(
                'Error opening pairs', 'No such pair: <b>%s %s</b>' % filename_date1, filename_date2)
            return False
        # assumes same name, but json extension
        self.status("Loading %s %s..." % (osp.basename(str(filename_date1)), osp.basename(str(filename_date2))))
        label_file = osp.splitext(filename_date1)[0].split('.')[0] + '.json'
        if self.output_dir:
            label_file_without_path = osp.basename(label_file)
            label_file = osp.join(self.output_dir, label_file_without_path)
        if QtCore.QFile.exists(label_file) and \
                LabelFile.is_label_file(label_file):
            try:
                self.labelFile = LabelFile(label_file)
            except LabelFileError as e:
                self.errorMessage(
                    'Error opening file',
                    "<p><b>%s</b></p>"
                    "<p>Make sure <i>%s</i> is a valid label file."
                    % (e, label_file))
                self.status("Error reading %s" % label_file)
                return False
            self.image_date1Data = self.labelFile.image_date1Data
            self.image_date2Data = self.labelFile.image_date2Data
            self.image_date1Path = osp.join(
                osp.dirname(label_file),
                self.labelFile.image_date1Path,
            )
            self.image_date2Path = osp.join(
                osp.dirname(label_file),
                self.labelFile.image_date2Path
            )
            if self.labelFile.lineColor is not None:
                self.lineColor = QtGui.QColor(*self.labelFile.lineColor)
            if self.labelFile.fillColor is not None:
                self.fillColor = QtGui.QColor(*self.labelFile.fillColor)
            self.otherData = self.labelFile.otherData
        else:
            self.image_date1Data, self.image_date2Data = LabelFile.load_image_pair(filename_date1, filename_date2)
            if self.image_date1Data and self.image_date2Data:
                self.image_date1Path = filename_date1
                self.image_date2Path = filename_date2
            self.labelFile = None
        image_date1 = QtGui.QImage.fromData(self.image_date1Data)
        image_date2 = QtGui.QImage.fromData(self.image_date2Data)

        if image_date1.isNull() or image_date2.isNull():
            formats = ['*.{}'.format(fmt.data().decode())
                       for fmt in QtGui.QImageReader.supportedImageFormats()]
            self.errorMessage(
                'Error opening pair',
                '<p>Make sure <i>{0}{1}</i> are valid image files.<br/>'
                'Supported image formats: {2}</p>'
                .format(filename_date1, filename_date2, ','.join(formats)))
            self.status("Error reading %s and/or %s" % filename_date1, filename_date2)
            return False
        self.image_date1 = image_date1
        self.image_date2 = image_date2

        self.filename_date1 = filename_date1
        self.filename_date2 = filename_date2
        if self._config['keep_prev']:
            prev_shapes = self.canvas.shapes
        self.canvas.loadPixmap(QtGui.QPixmap.fromImage(image_date1), 'date1') #Paint date1 on the canvas
        if self.labelFile:
            self.loadLabels(self.labelFile.shapes)
        if self._config['keep_prev'] and not self.labelList.shapes:
            self.loadShapes(prev_shapes, replace=False)
        self.setClean()
        self.canvas.setEnabled(True)
        self.adjustScale(initial=True)
        self.paintCanvas()
        self.addRecentPair(self.filename_date1, self.filename_date2)
        self.toggleActions(True)
        self.status("Loaded %s and %s" % (osp.basename(str(filename_date1)), osp.basename(str(filename_date2))))
        return True

    def resizeEvent(self, event):
        if self.canvas and not self.image_date1.isNull()\
           and not self.image_date2.isNull\
           and self.zoomMode != self.MANUAL_ZOOM:
            self.adjustScale()
        super(MainWindow, self).resizeEvent(event)

    def paintCanvas(self):
        assert not self.image_date1.isNull(), "cannot paint null image"
        self.canvas.scale = 0.01 * self.zoomWidget.value()
        self.canvas.adjustSize()
        self.canvas.update()

    def adjustScale(self, initial=False):
        value = self.scalers[self.FIT_WINDOW if initial else self.zoomMode]()
        self.zoomWidget.setValue(int(100 * value))

    def scaleFitWindow(self):
        """Figure out the size of the pixmap to fit the main widget."""
        e = 2.0  # So that no scrollbars are generated.
        w1 = self.centralWidget().width() - e
        h1 = self.centralWidget().height() - e
        a1 = w1 / h1
        # Calculate a new scale value based on the pixmap's aspect ratio.
        w2 = self.canvas.pixmap.width() - 0.0
        h2 = self.canvas.pixmap.height() - 0.0
        a2 = w2 / h2
        return w1 / w2 if a2 >= a1 else h1 / h2

    def scaleFitWidth(self):
        # The epsilon does not seem to work too well here.
        w = self.centralWidget().width() - 2.0
        return w / self.canvas.pixmap.width()

    def closeEvent(self, event):
        if not self.mayContinue():
            event.ignore()
        self.settings.setValue(
            'filename_date1', self.filename_date1 if self.filename_date1 else '')
        self.settings.setValue(
            'filename_date2', self.filename_date2 if self.filename_date2 else '')
        self.settings.setValue('window/size', self.size())
        self.settings.setValue('window/position', self.pos())
        self.settings.setValue('window/state', self.saveState())
        self.settings.setValue('line/color', self.lineColor)
        self.settings.setValue('fill/color', self.fillColor)
        self.settings.setValue('recentPairs', self.recentPairs)
        # ask the use for where to save the labels
        # self.settings.setValue('window/geometry', self.saveGeometry())

    # User Dialogs #

    def loadRecentPair(self, filename_date1, filename_date2):
        if self.mayContinue():
            self.loadPair(filename_date1, filename_date2)

    def openPrevPair(self, _value=False):
        keep_prev = self._config['keep_prev']
        if QtGui.QGuiApplication.keyboardModifiers() == \
                (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            self._config['keep_prev'] = True

        if not self.mayContinue():
            return

        if len(self.pairImageList) <= 0:
            return

        if self.filename_date1 is None or self.filename_date2 is None:
            return

        currIndex = self.pairImageList.index((self.filename_date1, self.filename_date2))
        if currIndex - 1 >= 0:
            filename_date1, filename_date2 = self.pairImageList[currIndex - 1]
            if filename_date1 and filename_date2:
                self.loadPair(filename_date1, filename_date2)

        self._config['keep_prev'] = keep_prev

    def openNextPair(self, _value=False, load=True):
        keep_prev = self._config['keep_prev']
        if QtGui.QGuiApplication.keyboardModifiers() == \
                (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier):
            self._config['keep_prev'] = True

        if not self.mayContinue():
            return

        if len(self.pairImageList) <= 0:
            return

        filename = None
        if self.filename_date1 is None and self.filename_date2 is None:
            filename_date1, filename_date2 = self.pairImageList[0]
        else:
            currIndex = self.pairImageList.index((self.filename_date1, self.filename_date2))
            if currIndex + 1 < len(self.pairImageList):
                filename_date1, filename_date2 = self.pairImageList[currIndex + 1]
            else:
                filename_date1, filename_date2 = self.pairImageList[-1]
        self.filename_date1 = filename_date1
        self.filename_date2 = filename_date2

        if self.filename_date1 and self.filename_date2 and load:
            self.loadPair(self.filename_date1, self.filename_date2)

        self._config['keep_prev'] = keep_prev

    def openPair(self, _value=False):
        if not self.mayContinue():
            return
        date1_path = osp.dirname(str(self.filename_date1)) if self.filename_date1 else '.'
        formats = ['*.{}'.format(fmt.data().decode())
                   for fmt in QtGui.QImageReader.supportedImageFormats()]
        filters = "Image & Label files (%s)" % ' '.join(
            formats + ['*%s' % LabelFile.suffix])
        filenames = QtWidgets.QFileDialog.getOpenFileNames(
            self, '%s - Choose Image or Label file' % __appname__,
            date1_path, filters)
        if QT5:
            filenames, _ = filenames
        filenames.sort()

        def match_dates(filename_date1, filename_date2):
            if filename_date1.split('.')[0] == filename_date2.split('.')[0]:
                return True
            else:
                self.status("Image pairs incorrect %s %s" % (filename_date1, filename_date2))
                return False

        if filenames and len(filenames) == 2:
            filename_date1, filename_date2 = filenames
            if filename_date1 and filename_date2 and match_dates(filename_date1, filename_date2):
                self.loadPair(filename_date1, filename_date2)

    def changeOutputDirDialog(self, _value=False):
        default_output_dir = self.output_dir
        if default_output_dir is None and self.filename_date1 and self.filename_date2:
            default_output_dir = osp.dirname(self.filename_date1)
        if default_output_dir is None:
            default_output_dir = self.currentPath()

        output_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, '%s - Save/Load Annotations in Directory' % __appname__,
            default_output_dir,
            QtWidgets.QFileDialog.ShowDirsOnly |
            QtWidgets.QFileDialog.DontResolveSymlinks,
        )
        output_dir = str(output_dir)

        if not output_dir:
            return

        self.output_dir = output_dir

        self.statusBar().showMessage(
            '%s . Annotations will be saved/loaded in %s' %
            ('Change Annotations Dir', self.output_dir))
        self.statusBar().show()

        current_filename_date1 = self.filename_date1
        current_filename_date2 = self.filename_date2
        self.importDirPairs(self.lastOpenDir, load=False)

        if (current_filename_date1, current_filename_date2) in self.pairImageList:
            # retain currently selected file
            self.filePairListWidget.setCurrentRow(
                self.pairImageList.index((current_filename_date1, current_filename_date2)))
            self.filePairListWidget.repaint()

    def saveFile(self, _value=False):
        assert not self.image_date1.isNull(), "cannot save empty image date1"
        assert not self.image_date2.isNull(), "cannot save empty image date2"
        if self._config['flags'] or self.hasLabels():
            if self.labelFile:
                # DL20180323 - overwrite when in directory
                self._saveFile(self.labelFile.filename)
            elif self.output_file:
                self._saveFile(self.output_file)
                self.close()
            else:
                self._saveFile(self.saveFileDialog())

    def saveFileAs(self, _value=False):
        assert not self.image_date1.isNull(), "cannot save empty image date1"
        assert not self.image_date2.isNull(), "cannot save empty image date2"
        if self.hasLabels():
            self._saveFile(self.saveFileDialog())

    def saveFileDialog(self):
        caption = '%s - Choose File' % __appname__
        filters = 'Label files (*%s)' % LabelFile.suffix
        if self.output_dir:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.output_dir, filters
            )
        else:
            dlg = QtWidgets.QFileDialog(
                self, caption, self.currentPath(), filters
            )
        dlg.setDefaultSuffix(LabelFile.suffix[1:])
        dlg.setAcceptMode(QtWidgets.QFileDialog.AcceptSave)
        dlg.setOption(QtWidgets.QFileDialog.DontConfirmOverwrite, False)
        dlg.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, False)
        basename = osp.basename(osp.splitext(self.filename_date1)[0].split('.')[0])
        if self.output_dir:
            default_labelfile_name = osp.join(
                self.output_dir, basename + LabelFile.suffix
            )
        else:
            default_labelfile_name = osp.join(
                self.currentPath(), basename + LabelFile.suffix
            )
        filename = dlg.getSaveFileName(
            self, 'Choose File', default_labelfile_name,
            'Label files (*%s)' % LabelFile.suffix)
        if QT5:
            filename, _ = filename
        filename = str(filename)
        return filename

    def _saveFile(self, filename):
        if filename and self.saveLabels(filename):
            self.addRecentPair(self.filename_date1, self.filename_date2)
            self.setClean()

    def closeFile(self, _value=False):
        if not self.mayContinue():
            return
        self.resetState()
        self.setClean()
        self.toggleActions(False)
        self.canvas.setEnabled(False)
        self.actions.saveAs.setEnabled(False)

    def getLabelFile(self):
        if self.filename_date1.lower().endswith('.json'):
            label_file = self.filename_date1
        else:
            label_file = osp.splitext(self.filename_date1)[0] + '.json'

        return label_file

    def deleteFile(self):
        mb = QtWidgets.QMessageBox
        msg = 'You are about to permanently delete this label file, ' \
              'proceed anyway?'
        answer = mb.warning(self, 'Attention', msg, mb.Yes | mb.No)
        if answer != mb.Yes:
            return

        label_file = self.getLabelFile()
        if osp.exists(label_file):
            os.remove(label_file)
            logger.info('Label file is removed: {}'.format(label_file))

            item = self.filePairListWidget.currentItem()
            item.setCheckState(Qt.Unchecked)

            self.resetState()

    # Message Dialogs. #
    def hasLabels(self):
        if not self.labelList.itemsToShapes:
            self.errorMessage(
                'No objects labeled',
                'You must label at least one object to save the file.')
            return False
        return True

    def hasLabelFile(self):
        if self.filename_date1 is None and self.filename_date2:
            return False

        label_file = self.getLabelFile()
        return osp.exists(label_file)

    def mayContinue(self):
        if not self.dirty:
            return True
        mb = QtWidgets.QMessageBox
        msg = 'Save annotations to "{}" before closing?'.format(self.filename_date1)
        answer = mb.question(self,
                             'Save annotations?',
                             msg,
                             mb.Save | mb.Discard | mb.Cancel,
                             mb.Save)
        if answer == mb.Discard:
            return True
        elif answer == mb.Save:
            self.saveFile()
            return True
        else:  # answer == mb.Cancel
            return False

    def errorMessage(self, title, message):
        return QtWidgets.QMessageBox.critical(
            self, title, '<p><b>%s</b></p>%s' % (title, message))

    def currentPath(self):
        return osp.dirname(str(self.filename_date1)) if self.filename_date1 else '.'

    def chooseColor1(self):
        color = self.colorDialog.getColor(
            self.lineColor, 'Choose line color', default=DEFAULT_LINE_COLOR)
        if color:
            self.lineColor = color
            # Change the color for all shape lines:
            Shape.line_color = self.lineColor
            self.canvas.update()
            self.setDirty()

    def chooseColor2(self):
        color = self.colorDialog.getColor(
            self.fillColor, 'Choose fill color', default=DEFAULT_FILL_COLOR)
        if color:
            self.fillColor = color
            Shape.fill_color = self.fillColor
            self.canvas.update()
            self.setDirty()

    def toggleKeepPrevMode(self):
        self._config['keep_prev'] = not self._config['keep_prev']

    def toggleDatePair(self):
        title = __appname__
        if self.canvas.date == 'date1':
            self.canvas.loadOtherDate(QtGui.QPixmap.fromImage(self.image_date2), 'date2')
            title = '{} - {}'.format(title, osp.splitext(self.filename_date2)[0])
            self.setWindowTitle(title)
        elif self.canvas.date == 'date2':
            self.canvas.loadOtherDate(QtGui.QPixmap.fromImage(self.image_date1), 'date1')
            title = '{} - {}'.format(title, osp.splitext(self.filename_date1)[0])
            self.setWindowTitle(title)

    def deleteSelectedShape(self):
        yes, no = QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No
        msg = 'You are about to permanently delete {} polygons, ' \
              'proceed anyway?'.format(len(self.canvas.selectedShapes))
        if yes == QtWidgets.QMessageBox.warning(self, 'Attention', msg,
                                                yes | no):
            self.remLabels(self.canvas.deleteSelected())
            self.setDirty()
            if self.noShapes():
                for action in self.actions.onShapesPresent:
                    action.setEnabled(False)

    def chshapeLineColor(self):
        color = self.colorDialog.getColor(
            self.lineColor, 'Choose line color', default=DEFAULT_LINE_COLOR)
        if color:
            for shape in self.canvas.selectedShapes:
                shape.line_color = color
            self.canvas.update()
            self.setDirty()

    def chshapeFillColor(self):
        color = self.colorDialog.getColor(
            self.fillColor, 'Choose fill color', default=DEFAULT_FILL_COLOR)
        if color:
            for shape in self.canvas.selectedShapes:
                shape.fill_color = color
            self.canvas.update()
            self.setDirty()

    def copyShape(self):
        self.canvas.endMove(copy=True)
        self.labelList.clearSelection()
        for shape in self.canvas.selectedShapes:
            self.addLabel(shape)
        self.setDirty()

    def moveShape(self):
        self.canvas.endMove(copy=False)
        self.setDirty()

    def openDirDialog(self, _value=False, dirpath=None):
        if not self.mayContinue():
            return

        defaultOpenDirPath = dirpath if dirpath else '.'
        if self.lastOpenDir and osp.exists(self.lastOpenDir):
            defaultOpenDirPath = self.lastOpenDir
        else:
            defaultOpenDirPath = osp.dirname(self.filename_date1) \
                if self.filename_date1 else '.'

        targetDirPath = str(QtWidgets.QFileDialog.getExistingDirectory(
            self, '%s - Open Directory' % __appname__, defaultOpenDirPath,
            QtWidgets.QFileDialog.ShowDirsOnly |
            QtWidgets.QFileDialog.DontResolveSymlinks))
        self.importDirPairs(targetDirPath)

    @property
    def pairImageList(self):
        lst = []
        for i in range(self.locationListWidget.count()):
            item = self.locationListWidget.item(i)
            lst.append((item.text() + '.d1.jpg', item.text() + '.d2.jpg'))
        return lst

    def importDirPairs(self, dirpath, pattern=None, load=True):
        self.actions.openNextPair.setEnabled(True)
        self.actions.openPrevPair.setEnabled(True)

        if not self.mayContinue() or not dirpath:
            return

        self.lastOpenDir = dirpath
        self.filename_date1 = None
        self.filename_date2 = None
        self.locationListWidget.clear()
        for filename_date1, filename_date2 in self.scanAllPairs(dirpath):
            if pattern and pattern not in filename_date1 and pattern and pattern not in filename_date2:
                continue
            label_file = osp.splitext(filename_date1)[0].split('.')[0] + '.json'
            if self.output_dir:
                label_file_without_path = osp.basename(label_file)
                label_file = osp.join(self.output_dir, label_file_without_path)
            item = QtWidgets.QListWidgetItem(osp.splitext(filename_date1)[0].split('.')[0])
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            if QtCore.QFile.exists(label_file) and \
                    LabelFile.is_label_file(label_file):
                item.setCheckState(Qt.Checked)
            else:
                item.setCheckState(Qt.Unchecked)
            self.locationListWidget.addItem(item)
        self.openNextPair(load=load)

    def scanAllPairs(self, folderPath):
        extensions = ['.%s' % fmt.data().decode("ascii").lower()
                      for fmt in QtGui.QImageReader.supportedImageFormats()]
        bb_pairs = {}
        for root, dirs, files in os.walk(folderPath):
            for file in files:
                if file.lower().endswith(tuple(extensions)):
                    relativePath = osp.join(root, file)
                    if file.split('.')[0] not in bb_pairs and ('.d1.' in file or '.d2.' in file):
                        bb_pairs[file.split('.')[0]] = [relativePath]
                    elif '.d1.' in file or '.d2.' in file:
                        bb_pairs[file.split('.')[0]] += [relativePath]
                        bb_pairs[file.split('.')[0]].sort()
        pairs = bb_pairs.values()
        pairs = sorted(pairs, key=lambda item: item[0])
        return pairs
