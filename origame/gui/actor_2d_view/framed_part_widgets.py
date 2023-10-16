# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Concrete PartWidgets that are meant to be shown in a 2d Graphics Scene

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from datetime import datetime, timedelta
from inspect import signature
from pathlib import Path

# [2. third-party]
from PyQt5.QtCore import Qt, QMarginsF
from PyQt5.QtGui import QPalette, QResizeEvent, QPixmap, QMouseEvent
from PyQt5.QtSvg import QGraphicsSvgItem
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QMessageBox, QTableView, QGraphicsObject, QAction, QHBoxLayout
from PyQt5.QtWidgets import QWidget, QScrollArea, QHeaderView, QPlainTextEdit, QMenu

from dateutil.relativedelta import relativedelta

import matplotlib

if matplotlib.get_backend() != 'Qt5Agg':
    matplotlib.use('Qt5Agg')
from matplotlib import pyplot

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...core.utils import timedelta_to_rel

from ...scenario import ori
from ...scenario.defn_parts import BasePart, FunctionPart, ActorPart, PartFrame, RunRolesEnum, ActorIfxPortSide
from ...scenario.defn_parts import ButtonStateEnum, ButtonActionEnum, DisplayOrderEnum
from ...scenario.defn_parts import ClockPart, DataPart, PlotPart, SheetPart, TablePart, VariablePart, LibraryPart
from ...scenario.defn_parts import DateTimePart, TimePart, FilePart
from ...scenario.defn_parts import SqlPart, ButtonPart, PulsePart, PulsePartState
from ...scenario.defn_parts.plot_part import DEFAULT_FIG_SIZE
from ...scenario.defn_parts import DetailLevelEnum

from ..actions_utils import create_action
from ..async_methods import AsyncRequest, AsyncErrorInfo
from ..gui_utils import DEFAULT_ACTOR_IMAGE, ACTOR_IMAGE_NOT_FOUND, BUTTON_IMAGE_NOT_FOUND
from ..gui_utils import DEFAULT_BUTTON_DOWN, DEFAULT_BUTTON_UP, DEFAULT_BUTTON_ON, DEFAULT_BUTTON_OFF
from ..gui_utils import EVENT_COUNTER_RECT_HEIGHT, try_disconnect
from ..gui_utils import PLOT_UPDATE, PyExpr
from ..gui_utils import exec_modal_dialog, get_scenario_font, get_icon_path, PART_ICON_COLORS
from ..gui_utils import part_image, ITEM_SPACE, HORIZONTAL_ELLIPSIS
from ..svg_utils import SvgFromImageWidget
from ..conversions import convert_float_days_to_tick_period, SCALE_FACTOR
from ..safe_slot import safe_slot, ext_safe_slot
from ..part_editors import SortFilterProxyModelByColumns, ExportDataDialog
from ..part_editors import ExportImageDialog, ImgEditorWidget, on_database_error, on_excel_error
from ..part_editors import ImportDatabaseDialog, ExportDatabaseDialog, ImportExcelDialog, ExportExcelDialog
from ..sim import CreateEventDialog
from ..slow_tasks import get_progress_bar
from ..undo_manager import FunctionPartToggleRoleCommand, scene_undo_stack

from .Ui_actor_part import Ui_ActorPartWidget
from .Ui_button_part import Ui_ButtonPartWidget
from .Ui_clock_part import Ui_ClockPartWidget
from .Ui_datetime_part import Ui_DateTimePartWidget
from .Ui_parent_actor_proxy import Ui_ParentActorProxyWidget
from .Ui_pulse_part import Ui_PulsePartWidget
from .Ui_sql_part import Ui_SqlPartWidget
from .Ui_time_part import Ui_TimePartWidget
from .Ui_variable_part import Ui_VariablePartWidget
from .Ui_file_part import Ui_FilePartWidget

from .base_part_widgets import FramedPartWidget, IPartWidget, FramedPartHeaderObjTypeEnum, IExecPartWidget
from .common import register_part_item_class
from .custom_widgets import CallParameters, ScriptEditBox, SMALL_ICON_SIZE_WIDTH, SMALL_ICON_SIZE_HEIGHT
from .custom_items import SizeGripCornerItem, SizeGripRightItem, SizeGripBottomItem
from .custom_widgets import PlotFigureCanvas, SvgToolButton, ListAndFirePopup
from .data_part_table_model import DataPartTableView, DataPartTableModel
from .event_counter_manager import EventCounterManager
from .iexec_indicators import BreakpointIndicator
from .part_box_item import PartBoxItem
from .part_box_side_items import IfxPortItem, VerticalSideTrayItem
from .part_box_side_item_base import TopSideTrayItemTypeEnum
from .sheet_part_table_model import SheetPartTableView, SheetPartTableModel
from .table_part_table_model import TablePartTableView, TablePartTableModel

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # defines module members that are public; one line per string
    'ChildActorWidget',
    'FunctionPartWidget',
    'ClockPartWidget',
    'VariablePartWidget',
    'DataPartWidget',
    'SheetPartWidget',
    'ButtonPartWidget',
    'TablePartWidget',
    'PlotPartWidget',
    'SqlPartWidget'
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

class ParentActorProxyWidget(QWidget):
    """
    A special ActorPart widget that only shows the icon and name, and serves to allow the users to see
    links to parent item of the other actors in the 2D View. Has no content/minimize button.
    """

    def __init__(self, part: ActorPart):
        super().__init__()
        self.ui_parent_actor_proxy = Ui_ParentActorProxyWidget()
        self.ui_parent_actor_proxy.setupUi(self)
        self.ui_parent_actor_proxy.small_icon.load(str(part_image('actor_proxy')))
        self.ui_parent_actor_proxy.small_icon.setFixedSize(int(SMALL_ICON_SIZE_WIDTH), int(SMALL_ICON_SIZE_HEIGHT))

        self.ui_parent_actor_proxy.name_label.setFont(get_scenario_font(point_size=12))

        # Create the 'go to parent' button and add to UI layout
        self.go_to_parent_button = SvgToolButton(get_icon_path("shortcut_gotoparent.svg"), parent=self)
        layout = self.ui_parent_actor_proxy.horizontalLayout
        num_widgets = layout.count()
        layout.insertWidget(num_widgets, self.go_to_parent_button)

        # Toggle button visibility off when there is no parent, otherwise connect to 'go to parent' slot
        if part.parent_actor_part is None:
            self.go_to_parent_button.setVisible(False)
        else:
            self.go_to_parent_button.clicked.connect(self.__slot_on_go_to_parent)

        self._palette = QPalette()
        self._palette.setColor(QPalette.Window, PART_ICON_COLORS['actor_proxy'])
        self._palette.setColor(QPalette.Text, Qt.white)
        self.setPalette(self._palette)
        self.setAutoFillBackground(True)

        self._part = None
        self.__set_actor_part(part)

    def set_name(self, name: str):
        """
        Method called when backend name changes.
        """
        self.ui_parent_actor_proxy.name_label.setText(name)
        self.adjustSize()

    def get_actor_part(self) -> BasePart:
        """
        Get the part associated with the parent proxy widget.
        :return: Actor part.
        """
        return self._part

    def get_child_items(self) -> List[QGraphicsObject]:
        """Returns the list of child items"""
        return []

    part = property(get_actor_part)

    slot_set_name = safe_slot(set_name)

    def __set_actor_part(self, part: ActorPart):
        """
        Method used to set the Actor part associated with the proxy widget.
        :param part: An actor part.
        """
        assert self._part is None
        self._part = part
        part.part_frame.signals.sig_name_changed.connect(self.slot_set_name)

        self.set_name(part.part_frame.name)
        self.resize(self.sizeHint())

    def __on_go_to_parent(self):
        """
        Forwards the call to the scene. Note: cannot be done in the __init__ because graphicsProxyWidget is not ready
        yet.
        """
        self.graphicsProxyWidget().scene().sig_nav_to_actor.emit(self._part.parent_actor_part)

    __slot_on_go_to_parent = safe_slot(__on_go_to_parent)


class ChildActor2dContent(QWidget):
    """
    The content panel of a ChildActorPartWidget
    """

    # To make the image smaller than the container.
    MAKE_IMG_SMALLER = 0.7

    def __init__(self, logical_owner: QWidget):
        """
        The Actor Part GUI.
        :param logical_owner: The widget that holds this widget - the logical owner of this widget in
            Origame, not the Qt parent, which is the QStackedWidget.
        """
        super().__init__()
        self.__logical_owner = logical_owner
        self.ui_actor_part = Ui_ActorPartWidget()
        self.ui_actor_part.setupUi(self)

        self.__svg = SvgFromImageWidget(None, DEFAULT_ACTOR_IMAGE)
        self.ui_actor_part.horizontalLayout.addWidget(self.__svg)

    def manage_size(self):
        """
        Makes the image fit in the container - centered and with aspect ratio.
        """
        fit_in = self.__svg.actual_image_size.scaled(self.__logical_owner.size(), Qt.KeepAspectRatio)
        self.__svg.setFixedSize(fit_in * ChildActor2dContent.MAKE_IMG_SMALLER)

    def set_image(self, new_path: str = None):
        """
        Changes the image.
        :param new_path: The new path of the image.
        """
        self.__svg.load(new_path)

    def set_rotation_2d(self, rotation_in_angle: float):
        """
        Changes the rotation angle.
        :param rotation_in_angle: The new rotation angle of the image.
        """
        self.__svg.rotate(rotation_in_angle)


class ChildActorWidget(EventCounterManager, FramedPartWidget):
    """
    A child actor part2dwidget
    """

    def __init__(self, part: ActorPart, parent_part_box_item: PartBoxItem = None):
        FramedPartWidget.__init__(self, part, parent_part_box_item)
        EventCounterManager.__init__(self, part, parent_part_box_item)
        self._update_size_from_part()
        self._set_content_widget(ChildActor2dContent(self))

        self.__parent_part_box_item = parent_part_box_item

        self._load_icon_action = create_action(self, "Load Icon...", tooltip="Open dialog to choose Icon...")
        self.open_action = create_action(self, 'Open', tooltip="Go Into Actor")
        self.open_action.triggered.connect(self.slot_on_open_triggered)
        self.open_button = SvgToolButton(get_icon_path("shortcut_openactor.svg"), parent=self)
        self.open_button.setDefaultAction(self.open_action)
        self.open_button.setText(None)  # Must manually remove since setDefaultAction changes text property
        self.__part = part
        self.__img_path = DEFAULT_ACTOR_IMAGE
        self.__rotation_2d = 0

        self.__selection_margins = QMarginsF()

        layout = self.ui.header_frame.layout()
        num_widgets = layout.count()
        layout.insertWidget(num_widgets - 1, self.open_button)

        self._update_queue_indicators_actor()

        self._part.signals.sig_image_changed.connect(self.__slot__on_image_path_changed)
        self._part.signals.sig_rotation_2d_changed.connect(self.__slot__on_rotation_2d_changed)
        self._part.signals.sig_ifx_port_added.connect(self.__slot_on_ifx_port_added)
        self._part.signals.sig_ifx_port_removed.connect(self.__slot_on_ifx_port_removed)
        self._part.signals.sig_ifx_port_side_changed.connect(self.__slot_on_ifx_port_side_changed)
        self._part.signals.sig_ifx_port_index_changed.connect(self.__slot_on_ifx_port_index_changed)
        self._load_icon_action.triggered.connect(self.slot_on_action_load_icon)

        def __parse_ifx_ports(side):
            ports = part.get_ifx_ports(side)
            port_elements = []
            for port in ports:
                port_elements.append((port,
                                      port.name,
                                      port.part.PART_TYPE_NAME,
                                      port.ifx_level))

            return port_elements

        def __get_initial_state():
            return (part.image_path,
                    part.rotation_2d,
                    __parse_ifx_ports(ActorIfxPortSide.left),
                    __parse_ifx_ports(ActorIfxPortSide.right))

        def __init_values_from_part(image_path: str, rotation_2d: float,
                                    left_port_elements: List[Tuple[PartFrame, str, str, bool, int]],
                                    right_port_elements: List[Tuple[PartFrame, str, str, bool, int]]):
            self.__on_image_path_changed(image_path)
            self.__on_rotation_2d_changed(rotation_2d)
            left_side_tray_item = parent_part_box_item.left_side_tray_item
            for i, (part_frame, part_name, part_type_str, ifx_level) in enumerate(left_port_elements):
                left_side_tray_item.add_ifx_port(part_frame, part_name, part_type_str, ifx_level,
                                                 self._detail_level, i)

            right_side_tray_item = parent_part_box_item.right_side_tray_item
            for i, (part_frame, part_name, part_type_str, ifx_level) in enumerate(right_port_elements):
                right_side_tray_item.add_ifx_port(part_frame, part_name, part_type_str, ifx_level,
                                                  self._detail_level, i)

            self.__adjust_selection_margins(left_side_tray_item, right_side_tray_item)

            left_side_tray_item.update_item()
            right_side_tray_item.update_item()

        AsyncRequest.call(__get_initial_state, response_cb=__init_values_from_part)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        FramedPartWidget._disconnect_all_slots(self)
        EventCounterManager._disconnect_all_slots(self)
        try_disconnect(self.open_action.triggered, self.slot_on_open_triggered)
        signals = self._part.signals
        try_disconnect(signals.sig_image_changed, self.__slot__on_image_path_changed)
        try_disconnect(signals.sig_rotation_2d_changed, self.__slot__on_rotation_2d_changed)
        try_disconnect(signals.sig_ifx_port_added, self.__slot_on_ifx_port_added)
        try_disconnect(signals.sig_ifx_port_removed, self.__slot_on_ifx_port_removed)
        try_disconnect(signals.sig_ifx_port_side_changed, self.__slot_on_ifx_port_side_changed)
        try_disconnect(signals.sig_ifx_port_index_changed, self.__slot_on_ifx_port_index_changed)
        try_disconnect(self._load_icon_action.triggered, self.slot_on_action_load_icon)

    @override(IPartWidget)
    def get_proximity_margins(self) -> QMarginsF:
        """
        The margins include the space required by the ifx ports.
        :return: The margins to be added to the base proximity area.
        """
        margins = QMarginsF(FramedPartWidget.get_proximity_margins(self))
        # The base proximity area always includes the space required by the link short cut on the right, but not
        # on the left. So, we add the space here on the left.
        margins.setLeft(margins.left() +
                        IfxPortItem.PART_TYPE_ICON_WIDTH + ITEM_SPACE +
                        self.__parent_part_box_item.link_creation_action_item.childrenBoundingRect().width())
        margins.setRight(margins.right() + IfxPortItem.PART_TYPE_ICON_WIDTH)
        return margins

    @override(IPartWidget)
    def get_selection_margins(self) -> QMarginsF:
        """
        When this item has ifx ports, the selection area must be bigger; otherwise, smaller. This functions returns
        suitable margins, depending on whether the underlying part has any ifx ports.
        :return: The margins that reflect the presence or absence of ifx ports.
        """
        return self.__selection_margins

    @override(QWidget)
    def resizeEvent(self, event: QResizeEvent):
        self._content_widget.manage_size()
        super(ChildActorWidget, self).resizeEvent(event)

    def set_parent_part_box_item(self, parent: QGraphicsObject):
        """
        Sets the parent PartBoxItem for this actor widget.
        :param parent: a PartBoxItem container for this actor part widget.
        """
        self.__parent_part_box_item = parent

    def get_parent_part_box_item(self) -> QGraphicsObject:
        """
        Returns the parent PartBoxItem.
        :return: the parent.
        """
        return self.__parent_part_box_item

    def on_open_triggered(self, _: bool = False):
        """
        Triggers the actor to open.
        :param _: A boolean signal not used by this method.
        """
        self.graphicsProxyWidget().scene().sig_nav_to_actor.emit(self._part)

    def on_action_load_icon(self):
        """
        Method called when a user clicks on the 'Load Icon...' context menu.
        """
        image_editor = ImgEditorWidget()
        image_editor.ui.select.click()
        path = image_editor.img_path
        if path is not None:
            AsyncRequest.call(self.__part.set_image_path, path)

    parent_part_box_item = property(get_parent_part_box_item, set_parent_part_box_item)

    slot_on_open_triggered = safe_slot(on_open_triggered)
    slot_on_action_load_icon = safe_slot(on_action_load_icon)

    @override(FramedPartWidget)
    def _set_size(self, width: float, height: float):
        if self._content_widget is not None:
            self._content_widget.manage_size()
        FramedPartWidget._set_size(self, width, height)

    _slot_set_size = safe_slot(_set_size)

    def __on_image_path_changed(self, new_path: str):
        """
        Changes the image.
        :param new_path: The new path of the image.
        """
        if self.__img_path == new_path:
            return

        self.__img_path = new_path
        self.__render()

    def __on_rotation_2d_changed(self, new_rotation_2d: float):
        """
        Changes the rotation 2d.
        :param new_rotation_2d: The new rotation 2d of the image.
        """
        if self.__rotation_2d == new_rotation_2d:
            return

        self.__rotation_2d = new_rotation_2d
        self.__render()

    def __tray_by_side(self, is_left_side: bool):
        """
        Gets the left or right side tray.
        :param is_left_side:
        :return: The left side tray if is_left_side is True.
        """
        if is_left_side:
            return self.__parent_part_box_item.left_side_tray_item
        else:
            return self.__parent_part_box_item.right_side_tray_item

    def __adjust_selection_margins(self,
                                   vertical_tray_item1: VerticalSideTrayItem,
                                   vertical_tray_item2: VerticalSideTrayItem = None):
        """
        If the actor part has at least one ifx port on either side, this function makes the selection area wider to
        cover the port(s); otherwise, narrower just to cover the base part box item.

        :param vertical_tray_item1: One of the vertical side bars
        :param vertical_tray_item2: The other of the vertical side bars
        """
        if vertical_tray_item1.num_ifx_ports > 0 or vertical_tray_item2.num_ifx_ports > 0:
            self.__selection_margins = QMarginsF(IfxPortItem.PART_TYPE_ICON_WIDTH,
                                                 0,
                                                 IfxPortItem.PART_TYPE_ICON_WIDTH,
                                                 0)
        else:
            self.__selection_margins = QMarginsF()

    def __on_ifx_port_added(self, port: PartFrame, is_left_side: bool, ifx_port_index: int):
        tray = self.__tray_by_side(is_left_side)
        tray.add_ifx_port(port,
                          port.name,
                          port.part.PART_TYPE_NAME,
                          port.ifx_level,
                          self._detail_level,
                          ifx_port_index)
        self.__selection_margins = QMarginsF(IfxPortItem.PART_TYPE_ICON_WIDTH,
                                             0,
                                             IfxPortItem.PART_TYPE_ICON_WIDTH,
                                             0)
        tray.update_item()

    def __on_ifx_port_removed(self, port: PartFrame, is_left_side: bool):
        tray = self.__tray_by_side(is_left_side)
        tray.remove_ifx_port(port)
        self.__adjust_selection_margins(tray, self.__tray_by_side(not is_left_side))
        tray.update_item()

    def __on_ifx_port_side_changed(self, port: PartFrame, is_left_side: bool, ifx_port_index_to_bin: int):
        from_tray = self.__tray_by_side(is_left_side)
        popped_item = from_tray.pop_ifx_port_item(port)

        assert popped_item is not None

        to_tray = self.__tray_by_side(not is_left_side)
        to_tray.insert_ifx_port_item(ifx_port_index_to_bin, popped_item)
        from_tray.update_item()
        to_tray.update_item()

    def __on_ifx_port_index_changed(self, from_idx: int, is_left_side: bool, to_idx: int):
        """
        Updates the ports' vertical locations when a port is moved up or down the side.
        :param from_idx: The original port index.
        :param is_left_side: Indicates if the port is on the left or right.
        :param to_idx: The new port index.
        """
        tray = self.__tray_by_side(is_left_side)
        tray.update_ifx_port_vertical_indices(from_idx, to_idx)
        tray.update_item()

    def __render(self):
        """
        Renders the image with correct rotation on the part. If the image is invalid, a place holder image will be
        used.
        """
        if not self.__img_path:
            self._content_widget.set_image(DEFAULT_ACTOR_IMAGE)
        else:
            if QPixmap(self.__img_path).isNull():
                self._content_widget.set_image(ACTOR_IMAGE_NOT_FOUND)
            else:
                self._content_widget.set_image(self.__img_path)

        self._content_widget.set_rotation_2d(self.__rotation_2d)

        self._content_widget.manage_size()

    __slot__on_image_path_changed = safe_slot(__on_image_path_changed)
    __slot__on_rotation_2d_changed = safe_slot(__on_rotation_2d_changed)
    __slot_on_ifx_port_added = ext_safe_slot(__on_ifx_port_added)
    __slot_on_ifx_port_removed = ext_safe_slot(__on_ifx_port_removed)
    __slot_on_ifx_port_side_changed = ext_safe_slot(__on_ifx_port_side_changed)
    __slot_on_ifx_port_index_changed = safe_slot(__on_ifx_port_index_changed)


class FunctionPart2dContent(QWidget):
    """
    The content panel of a FunctionPartWidget.
    """

    def __init__(self):
        super().__init__()
        self.params_label = QLabel("Parameters:")
        self.params_value = CallParameters()
        self.params_value.setReadOnly(True)
        self.params_value.setObjectName("parameters")

        horizontal_layout = QHBoxLayout()
        horizontal_layout.addWidget(self.params_label)
        horizontal_layout.addWidget(self.params_value)

        vertical_layout = QVBoxLayout(self)
        vertical_layout.setContentsMargins(4, 4, 4, 4)
        vertical_layout.setSpacing(2)
        self.params_label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        vertical_layout.addLayout(horizontal_layout)
        self.function_listing = ScriptEditBox()
        self.function_listing.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.function_listing.setReadOnly(True)
        vertical_layout.addWidget(self.function_listing)


class FunctionPartWidget(BreakpointIndicator, EventCounterManager, FramedPartWidget, IExecPartWidget):
    """
    A function part 2d widget.
    """

    def __init__(self, part: FunctionPart, parent_part_box_item: PartBoxItem = None):
        FramedPartWidget.__init__(self, part, parent_part_box_item)
        BreakpointIndicator.__init__(self, parent_part_box_item)
        EventCounterManager.__init__(self, part, parent_part_box_item)
        IExecPartWidget.__init__(self)

        # Since we treat IExecPartWidget as an interface or an abstract class, we should not perhaps use its
        # constructor, which emphasizes a concrete class.
        self._initialize_run()

        self._set_content_widget(FunctionPart2dContent())
        self._part = part

        add_event_action = create_action(self,
                                         "Add Event" + HORIZONTAL_ELLIPSIS,
                                         tooltip="Add event for this part to Main Sim event queue")
        add_event_action.triggered.connect(self.slot_on_add_event)
        separator = QAction(self)
        separator.setSeparator(True)

        roles = create_action(self, "Roles" + HORIZONTAL_ELLIPSIS)
        roles.setMenu(QMenu())

        self.__toggle_startup_action = create_action(None, "Startup", tooltip="Toggle Startup role",
                                                     connect=self.__slot_toggle_startup)
        self.__toggle_reset_action = create_action(None, "Reset", tooltip="Toggle Reset role",
                                                   connect=self.__slot_toggle_reset)
        self.__toggle_finish_action = create_action(None, "Finish", tooltip="Toggle Finish role",
                                                    connect=self.__slot_toggle_finish)
        self.__toggle_setup_action = create_action(None, "Setup", tooltip="Toggle Setup role",
                                                   connect=self.__slot_toggle_setup)
        self.__toggle_batch_action = create_action(None, "Batch", tooltip="Toggle Batch role",
                                                   connect=self.__slot_toggle_batch)
        roles.menu().addAction(self.__toggle_setup_action)
        roles.menu().addAction(self.__toggle_reset_action)
        roles.menu().addAction(self.__toggle_startup_action)
        roles.menu().addAction(self.__toggle_finish_action)
        roles.menu().addAction(self.__toggle_batch_action)

        self.__startup_marker = QGraphicsSvgItem(str(get_icon_path("role_startup.svg")))
        self.__startup_marker.setVisible(False)
        self.__reset_marker = QGraphicsSvgItem(str(get_icon_path("role_reset.svg")))
        self.__reset_marker.setVisible(False)
        self.__finish_marker = QGraphicsSvgItem(str(get_icon_path("role_finish.svg")))
        self.__finish_marker.setVisible(False)
        self.__setup_marker = QGraphicsSvgItem(str(get_icon_path("role_setup.svg")))
        self.__setup_marker.setVisible(False)
        self.__batch_marker = QGraphicsSvgItem(str(get_icon_path("role_batch.svg")))
        self.__batch_marker.setVisible(False)

        self.__map_role_to_marker = {RunRolesEnum.startup: self.__startup_marker,
                                     RunRolesEnum.reset: self.__reset_marker,
                                     RunRolesEnum.finish: self.__finish_marker,
                                     RunRolesEnum.setup: self.__setup_marker,
                                     RunRolesEnum.batch: self.__batch_marker}

        parent_part_box_item.top_side_tray_item.add_obj(TopSideTrayItemTypeEnum.startup, self.__startup_marker)
        parent_part_box_item.top_side_tray_item.add_obj(TopSideTrayItemTypeEnum.reset, self.__reset_marker)
        parent_part_box_item.top_side_tray_item.add_obj(TopSideTrayItemTypeEnum.finish, self.__finish_marker)
        parent_part_box_item.top_side_tray_item.add_obj(TopSideTrayItemTypeEnum.setup, self.__setup_marker)
        parent_part_box_item.top_side_tray_item.add_obj(TopSideTrayItemTypeEnum.batch, self.__batch_marker)

        separator = QAction(self)
        separator.setSeparator(True)

        def __get_init_data():
            return part.script, part.parameters, part.run_roles, parent_part_box_item.part.get_queue_counts()

        def __set_init_data(script, parameters, run_roles, queue_counts):
            self._content_widget.function_listing.setPlainText(script)
            self._content_widget.params_value.setText(parameters)
            for role in run_roles:
                self.__on_run_role_added(role)
            is_next, count_concur, count_after = queue_counts
            self._queue_counters_changed(is_next, count_concur, count_after)

        AsyncRequest.call(__get_init_data, response_cb=__set_init_data)

        # Connections to 'backend' thread signals
        part.exec_signals.sig_params_changed.connect(self.__slot_on_set_call_parameters)
        part.scripting_signals.sig_script_changed.connect(self.__slot_on_script_changed)
        part.func_signals.sig_run_role_added.connect(self.__slot_on_run_role_added)
        part.func_signals.sig_run_role_removed.connect(self.__slot_on_run_role_removed)

        part.exec_signals.sig_exec_done.connect(self.__slot_on_exec_done)

        self._update_size_from_part()

    def get_part(self):
        """
        Method used to get the part associated with this Function part widget.
        :return:  The part associated with the widget.
        """
        return self._part

    def on_add_event(self):
        """
        Method called when an Add Event is selected by the user.
        """
        create_event_dialog = CreateEventDialog(self._part)
        create_event_dialog.exec()

    slot_on_add_event = safe_slot(on_add_event)

    part = property(get_part)

    @override(IExecPartWidget)
    def _run_part(self):
        self._complete_execution(part_call=self._part.call, sig_getter=self._part.get_signature)

    @override(IExecPartWidget)
    def _debug_part(self):
        self._complete_execution(part_call=self._part.call, sig_getter=self._part.get_signature, debug=True)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        FramedPartWidget._disconnect_all_slots(self)
        IExecPartWidget._disconnect_all_slots(self)
        EventCounterManager._disconnect_all_slots(self)
        exec_signals = self._part.exec_signals
        try_disconnect(exec_signals.sig_params_changed, self.__slot_on_set_call_parameters)
        try_disconnect(exec_signals.sig_exec_done, self.__slot_on_exec_done)

        scripting_signals = self._part.scripting_signals
        try_disconnect(scripting_signals.sig_script_changed, self.__slot_on_script_changed)

        func_signals = self._part.func_signals
        try_disconnect(func_signals.sig_run_role_added, self.__slot_on_run_role_added)
        try_disconnect(func_signals.sig_run_role_removed, self.__slot_on_run_role_removed)

        try_disconnect(self.__toggle_reset_action.triggered, self.__slot_toggle_reset)
        try_disconnect(self.__toggle_startup_action.triggered, self.__slot_toggle_startup)
        try_disconnect(self.__toggle_finish_action.triggered, self.__slot_toggle_finish)
        try_disconnect(self.__toggle_setup_action.triggered, self.__slot_toggle_setup)
        try_disconnect(self.__toggle_batch_action.triggered, self.__slot_toggle_batch)

    def __on_set_call_parameters(self, param_str: str):
        self._content_widget.params_value.setText(param_str)  # or None)

    def __on_script_changed(self, new_text: str):
        self._content_widget.function_listing.setPlainText(new_text)

    def __on_exec_done(self):
        """
        This notification is used to instruct all the linked widgets to update themselves.
        """

        def notify_linked_parts():
            linked_parts = self._part.part_frame.get_linked_parts()
            for linked_part in linked_parts:
                linked_part.on_exec_done()

        AsyncRequest.call(notify_linked_parts)

    def __on_run_role_added(self, run_role: int):
        """
        updates GUI based on backend data
        :param run_role: backend data, one of the values of RunRolesEnum
        """
        self.__map_role_to_marker[run_role].setVisible(True)
        self._parent_part_box_item.top_side_tray_item.update_item()

    def __on_run_role_removed(self, run_role: int):
        """
        updates GUI based on backend data
        :param run_role: backend data, one of the values of RunRolesEnum
        """
        self.__map_role_to_marker[run_role].setVisible(False)
        self._parent_part_box_item.top_side_tray_item.update_item()

    def __toggle_startup(self, _: bool):
        cmd = FunctionPartToggleRoleCommand(self._part, RunRolesEnum.startup, not self.__startup_marker.isVisible())
        scene_undo_stack().push(cmd)

    def __toggle_reset(self, _: bool):
        cmd = FunctionPartToggleRoleCommand(self._part, RunRolesEnum.reset, not self.__reset_marker.isVisible())
        scene_undo_stack().push(cmd)

    def __toggle_finish(self, _: bool):
        cmd = FunctionPartToggleRoleCommand(self._part, RunRolesEnum.finish, not self.__finish_marker.isVisible())
        scene_undo_stack().push(cmd)

    def __toggle_setup(self, _: bool):
        cmd = FunctionPartToggleRoleCommand(self._part, RunRolesEnum.setup, not self.__setup_marker.isVisible())
        scene_undo_stack().push(cmd)

    def __toggle_batch(self, _: bool):
        cmd = FunctionPartToggleRoleCommand(self._part, RunRolesEnum.batch, not self.__batch_marker.isVisible())
        scene_undo_stack().push(cmd)

    __slot_toggle_startup = safe_slot(__toggle_startup)
    __slot_toggle_reset = safe_slot(__toggle_reset)
    __slot_toggle_finish = safe_slot(__toggle_finish)
    __slot_toggle_setup = safe_slot(__toggle_setup)
    __slot_toggle_batch = safe_slot(__toggle_batch)
    __slot_on_run_role_added = safe_slot(__on_run_role_added)
    __slot_on_run_role_removed = safe_slot(__on_run_role_removed)
    __slot_on_set_call_parameters = safe_slot(__on_set_call_parameters)
    __slot_on_script_changed = safe_slot(__on_script_changed)
    __slot_on_exec_done = safe_slot(__on_exec_done)


class ClockPart2dContent(QWidget):
    """
    The content panel of a ClockPartWidget
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui_clock_part = Ui_ClockPartWidget()
        self.ui_clock_part.setupUi(self)


class ClockPartWidget(FramedPartWidget):
    """
    A Clock Part 2d widget
    """

    def __init__(self, part: ClockPart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)

        self._set_content_widget(ClockPart2dContent())
        self._part.signals.sig_tick_value_changed.connect(self._slot_on_tick_value_changed)
        self._part.signals.sig_tick_period_days_changed.connect(self._slot_on_tick_period_changed)
        self._part.signals.sig_date_time_changed.connect(self._slot_on_datetime_changed)

        def _get_init_data():
            return part.get_tick_value(), part.get_tick_period_days(), part.get_date_time()

        def _init_values_from_part(tick_value: float, tick_period_days: float, date_time: datetime):
            self._on_tick_value_changed(tick_value)
            self._on_tick_period_changed(tick_period_days)
            self._on_datetime_changed(date_time.year,
                                      date_time.month,
                                      date_time.day,
                                      date_time.hour,
                                      date_time.minute,
                                      date_time.second,
                                      date_time.microsecond
                                      )

        AsyncRequest.call(_get_init_data, response_cb=_init_values_from_part)

        self._update_size_from_part()

    def _on_tick_value_changed(self, tick_value: float):
        """
        Set the tick value to the Ticks on the GUI
        Convert it to a string first before setting it to the GUI.
        :param tick_value: The tick value
        """
        self._content_widget.ui_clock_part.ticksEdit.setText('{:f}'.format(tick_value))

    def _on_tick_period_changed(self, tick_period_in_days: float):
        """
        Set the formatted string to the Tick Period on the GUI.
        Since the string  must be formatted, we use this method to get the signal from the backend.
        :param tick_period_in_days: The tick period in days.
        """
        self._content_widget.ui_clock_part.tickPeriodEdit.setText(
            convert_float_days_to_tick_period(tick_period_in_days))

    def _on_datetime_changed(self, year: int, month: int, day: int,
                             hour: int, minute: int, second: int, microsecond: int):
        """
        Sets the value to the Date/Time on the GUI
        :param year:
        :param month:
        :param day:
        :param hour:
        :param minute:
        :param second:
        :param microsecond:
        """
        date_time = datetime(year=year, month=month, day=day,
                             hour=hour, minute=minute, second=second, microsecond=microsecond)
        self._content_widget.ui_clock_part.dateTimeEdit.setText(date_time.strftime("%Y/%m/%d    %H:%M:%S"))

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        signals = self._part.signals
        try_disconnect(signals.sig_tick_value_changed, self._slot_on_tick_value_changed)
        try_disconnect(signals.sig_tick_period_days_changed, self._slot_on_tick_period_changed)
        try_disconnect(signals.sig_date_time_changed, self._slot_on_datetime_changed)

    _slot_on_tick_value_changed = safe_slot(_on_tick_value_changed)
    _slot_on_tick_period_changed = safe_slot(_on_tick_period_changed)
    _slot_on_datetime_changed = safe_slot(_on_datetime_changed)


class DateTimePart2dContent(QWidget):
    """
    The content panel of a DateTimePartWidget
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui_datetime_part = Ui_DateTimePartWidget()
        self.ui_datetime_part.setupUi(self)


class DateTimePartWidget(FramedPartWidget):
    """
    A DateTime Part 2d widget
    """

    def __init__(self, part: DateTimePart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)

        self._set_content_widget(DateTimePart2dContent())
        self._part.signals.sig_date_time_changed.connect(self.__slot_on_datetime_changed)

        def _init_values_from_part(date_time: datetime):
            self.__on_datetime_changed(date_time.year,
                                       date_time.month,
                                       date_time.day,
                                       date_time.hour,
                                       date_time.minute,
                                       date_time.second,
                                       date_time.microsecond
                                       )

        AsyncRequest.call(part.get_date_time, response_cb=_init_values_from_part)

        self._update_size_from_part()

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        signals = self._part.signals
        try_disconnect(signals.sig_date_time_changed, self.__slot_on_datetime_changed)

    def __on_datetime_changed(self, year: int, month: int, day: int,
                              hour: int, minute: int, second: int, microsecond: int):
        """
        Sets the value to the Date/Time on the GUI
        :param year:
        :param month:
        :param day:
        :param hour:
        :param minute:
        :param second:
        :param microsecond:
        """
        date_time = datetime(year=year, month=month, day=day,
                             hour=hour, minute=minute, second=second, microsecond=microsecond)
        self._content_widget.ui_datetime_part.date_edit.setText(date_time.strftime("%Y/%m/%d"))
        self._content_widget.ui_datetime_part.time_edit.setText(date_time.strftime("%H:%M:%S"))

    __slot_on_datetime_changed = safe_slot(__on_datetime_changed)


class TimePart2dContent(QWidget):
    """
    The content panel of a TimePartWidget
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui_time_part = Ui_TimePartWidget()
        self.ui_time_part.setupUi(self)


class TimePartWidget(FramedPartWidget):
    """
    A Time Part 2d widget
    """
    ELAPSED_TIME_FORMAT = '{DDDD:04d} {HH:02d}:{MM:02d}:{SS:02d}'

    def __init__(self, part: TimePart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)

        self._set_content_widget(TimePart2dContent())
        self._part.signals.sig_elapsed_time_changed.connect(self.__slot_on_elapsed_time_changed)

        def init_values():
            elapsed_time = timedelta_to_rel(part.elapsed_time)
            return elapsed_time.days, elapsed_time.hours, elapsed_time.minutes, elapsed_time.seconds

        AsyncRequest.call(init_values, response_cb=self.__on_elapsed_time_changed)

        self._update_size_from_part()

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        signals = self._part.signals
        try_disconnect(signals.sig_elapsed_time_changed, self.__slot_on_elapsed_time_changed)

    def __on_elapsed_time_changed(self, days: float, hours: float, minutes: float, seconds: int):
        """
        Sets the value to the Elapsed Time field on the GUI
        :param days:
        :param hours:
        :param minutes:
        :param seconds: It is an int because the requirement indicates the resolution is only up to seconds.
        """
        normalized = relativedelta(days=days, hours=hours, minutes=minutes, seconds=seconds).normalized()
        et = TimePartWidget.ELAPSED_TIME_FORMAT.format(DDDD=normalized.days,
                                                       HH=normalized.hours,
                                                       MM=normalized.minutes,
                                                       SS=normalized.seconds)
        self._content_widget.ui_time_part.elapsed_time.setText(et)

    __slot_on_elapsed_time_changed = safe_slot(__on_elapsed_time_changed)


class VariablePart2dContent(QWidget):
    """
    The content panel of a VariablePartWidget.
    """

    def __init__(self):
        super().__init__()

        self.ui_variable_part = Ui_VariablePartWidget()
        self.ui_variable_part.setupUi(self)
        self.ui_variable_part.variable_data.setFont(get_scenario_font())


class VariablePartWidget(FramedPartWidget):
    """
    A Variable Part 2D Widget
    """

    def __init__(self, part: VariablePart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)
        self._part = part

        self._set_content_widget(VariablePart2dContent())
        self._part.signals.sig_obj_changed.connect(self.slot_set_obj)
        self._update_size_from_part()

    @override(IPartWidget)
    def populate_data(self):
        """
        Sets the data to the GUI.
        """
        AsyncRequest.call(self._part.get_obj, response_cb=self.set_obj, unpack_response=False)

    def set_obj(self, obj: Any):
        """
        Set the object.
        The repr of the object is displayed on the GUI.
        :param obj: Any object is acceptable.
        """
        def __populate_data(val_wrapper):
            data_label = self._content_widget.ui_variable_part.variable_data
            data_label.setText(str(val_wrapper))
            data_label.setToolTip(val_wrapper.get_display_tooltip().value())

        __populate_data(PyExpr(pending=True))

        def __construct_py_expr():
            return PyExpr(obj)

        AsyncRequest.call(__construct_py_expr, response_cb=__populate_data)

    slot_set_obj = ext_safe_slot(set_obj, arg_types=[object])

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        signals = self._part.signals
        try_disconnect(signals.sig_obj_changed, self.slot_set_obj)


class FilePart2dContent(QWidget):
    """
    The content panel of a FilePartWidget.
    """

    def __init__(self):
        super().__init__()

        self.ui_file_part = Ui_FilePartWidget()
        self.ui_file_part.setupUi(self)
        self.ui_file_part.filepath.setFont(get_scenario_font())


class FilePartWidget(FramedPartWidget):
    """
    A File Part 2D Widget
    """

    def __init__(self, part: FilePart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)
        self._part = part

        self._set_content_widget(FilePart2dContent())
        self._part.signals.sig_path_changed.connect(self.__slot_on_path_changed)
        self._part.signals.sig_is_relative_to_scen_folder_changed.connect(
            self.__slot_on_is_relative_to_scen_folder_changed)

        def _get_init_data():
            return (part.get_filepath(),
                    part.get_is_relative_to_scen_folder())

        def path_changed_wrapper(filepath: Optional[Path], relative: bool):
            if filepath is None:
                path_str = ''
            else:
                path_str = str(filepath)

            self.__on_path_changed(path_str)
            self.__on_is_relative_to_scen_folder_changed(relative)

        AsyncRequest.call(_get_init_data, response_cb=path_changed_wrapper)
        self._update_size_from_part()

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        signals = self._part.signals
        try_disconnect(signals.sig_path_changed, self.__slot_on_path_changed)
        try_disconnect(signals.sig_path_changed, self.__slot_on_is_relative_to_scen_folder_changed)

    def __on_path_changed(self, value: str):
        """
        Set the value to the file path browser on the GUI
        :param value: The file path.
        """
        self._content_widget.ui_file_part.filepath.setText(value)

    def __on_is_relative_to_scen_folder_changed(self, value: bool):
        """
        Set the value to the relative to scenario folder on the GUI
        :param value: relative to scenario path.
        """
        self._content_widget.ui_file_part.relative_to_scen_folder.setChecked(value)

    __slot_on_path_changed = safe_slot(__on_path_changed)
    __slot_on_is_relative_to_scen_folder_changed = safe_slot(__on_is_relative_to_scen_folder_changed)


class DataPartHeaderView(QHeaderView):
    """
    Subclass to override mousePressEvent so that selecting the header selects the part.
    """

    @override(QHeaderView)
    def mousePressEvent(self, event: QMouseEvent):
        event.ignore()


class DataPart2dContent(QWidget):
    """
    The content panel of a DataPartWidget
    """

    def __init__(self):
        super().__init__()
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        self._data_view = DataPartTableView()
        l.addWidget(self._data_view)

        self._data_view.setShowGrid(False)
        header = DataPartHeaderView(Qt.Horizontal)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        self._data_view.setHorizontalHeader(header)

    def get_data_view(self) -> QTableView:
        """
        Method used to get the table view for a Data part.
        :returns: The view.
        """
        return self._data_view


class DataPartWidget(FramedPartWidget):
    """
    A data part 2d widget
    """

    def __init__(self, part: DataPart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)

        self._set_content_widget(DataPart2dContent())
        self._data_model = DataPartTableModel(part)
        self._update_size_from_part()
        self.__proxy_model = None

        # Connect slot to sort widget table based on editor settings
        self._data_model.signals.sig_change_data_widget_display_order.connect(self.slot_on_display_order_changed)

    @override(IPartWidget)
    def populate_data(self):
        """
        Sets the data model to the data view, thus populates the data.
        """
        self._content_widget.get_data_view().setModel(self._data_model)

    def on_display_order_changed(self, display_order: DisplayOrderEnum):
        """
        Update the display order to correspond with user-selected sort setting.
        :param display_order: the display order enum set to alphabetical, reverse-alphabetical, or no order.
        """
        key_col = self._data_model.COL_KEY_INDEX
        if display_order == DisplayOrderEnum.alphabetical:
            self.__proxy_model = SortFilterProxyModelByColumns(self, [key_col])
            self.__proxy_model.setSourceModel(self._data_model)
            self._content_widget.get_data_view().setModel(self.__proxy_model)
            self._content_widget.get_data_view().sortByColumn(key_col, Qt.AscendingOrder)
            self._content_widget.get_data_view().setSortingEnabled(True)

        elif display_order == DisplayOrderEnum.reverse_alphabetical:
            self.__proxy_model = SortFilterProxyModelByColumns(self, [key_col])
            self.__proxy_model.setSourceModel(self._data_model)
            self._content_widget.get_data_view().setModel(self.__proxy_model)
            self._content_widget.get_data_view().sortByColumn(key_col, Qt.DescendingOrder)
            self._content_widget.get_data_view().setSortingEnabled(True)

        else:
            # This must be DisplayOrderEnum.of_creation
            self._content_widget.get_data_view().setModel(self._data_model)
            self._content_widget.get_data_view().setSortingEnabled(False)

    slot_on_display_order_changed = safe_slot(on_display_order_changed)


class SheetPart2dContent(QWidget):
    """
    The content panel of a SheetPartWidget
    """

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        self.sheet_view = SheetPartTableView()
        layout.addWidget(self.sheet_view)

        self.sheet_view.setShowGrid(False)
        header = QHeaderView(Qt.Horizontal)
        header.setSectionResizeMode(QHeaderView.Stretch)
        self.sheet_view.setHorizontalHeader(header)


class SheetPartWidget(FramedPartWidget):
    """
    This class encapsulates the functionality of the Sheet Part widget in the 2D view.

    The Sheet Part presents spreadsheet-like capability and can be populated from or saved to Excel spreadsheets,
    or edited manually.
    """

    def __init__(self, part: SheetPart, parent_part_box_item: PartBoxItem = None):
        """
        Initialize the sheet part frontend using the backend part.
        :param part: The backend sheet part that this frontend class represents.
        """
        super().__init__(part, parent_part_box_item)
        self.__part = part
        self._set_content_widget(SheetPart2dContent())
        self._sheet_model = SheetPartTableModel(part)
        self._update_size_from_part()

        self.__import_excel_dialog = None
        self.__export_excel_dialog = None
        self.__last_sheet_import_path = None
        self.__last_sheet_export_path = None
        self.__set_custom_context_menu_options()

        part.signals.sig_col_width_changed.connect(self.__slot_update_col_width)

    @override(IPartWidget)
    def populate_data(self):
        """
        Sets the data model to the data view, thus populates the data.
        """
        self._content_widget.sheet_view.setModel(self._sheet_model)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        signals = self._part.signals
        try_disconnect(signals.sig_col_width_changed, self.__slot_update_col_width)
        try_disconnect(self.__import_from_excel_action.triggered, self.__slot_on_import_from_excel_action)
        try_disconnect(self.__export_to_excel_action.triggered, self.__slot_on_export_to_excel_action)

    def __update_col_width(self, col_index: int, width: int):
        """
        Update the sheet's column width when signalled by the backend part.
        :param col_index: the column index
        :param width: the column width to set
        """
        self._content_widget.sheet_view.setColumnWidth(col_index, width)

    def __set_custom_context_menu_options(self):
        """
        Defines a set of context menu options unique to this part.
        """

        separator = QAction(self)
        separator.setSeparator(True)

        self.__import_from_excel_action = create_action(self, "Import from Excel...")
        self.__import_from_excel_action.triggered.connect(self.__slot_on_import_from_excel_action)
        self.__export_to_excel_action = create_action(self, "Export to Excel...")
        self.__export_to_excel_action.triggered.connect(self.__slot_on_export_to_excel_action)

    def __on_import_from_excel_action(self):
        """
        Method called when the 'Import from Excel...' action is selected.
        """
        if self.__import_excel_dialog is None:
            self.__import_excel_dialog = ImportExcelDialog(self.__part,
                                                           last_sheet_import_path=self.__last_sheet_import_path)

        answer = self.__import_excel_dialog.exec()
        if answer:
            get_progress_bar().start_busy_progress('Importing from Excel')
            excel_path, excel_sheet, excel_range = self.__import_excel_dialog.get_user_input()
            self.__save_import_params(excel_path)

            def on_import_success():
                # reset for fresh dialog on next launch
                get_progress_bar().stop_progress()
                self.__import_excel_dialog = None

            def on_import_error(excel_error: AsyncErrorInfo):
                get_progress_bar().stop_progress()
                on_excel_error("Sheet Import Error", excel_error.msg)
                self.__on_import_from_excel_action()  # relaunch this method (note: not recursive since async)

            AsyncRequest.call(self._part.read_excel, excel_path, excel_sheet, excel_range,
                              response_cb=on_import_success, error_cb=on_import_error)
        else:
            # cancelled: reset for fresh dialog on next launch
            self.__import_excel_dialog = None

    def __on_export_to_excel_action(self):
        """
        Method called when the 'Export to Excel...' action is selected.
        """
        if self.__export_excel_dialog is None:
            self.__export_excel_dialog = ExportExcelDialog(self.__part,
                                                           last_sheet_export_path=self.__last_sheet_export_path)

        answer = self.__export_excel_dialog.exec()
        if answer:
            get_progress_bar().start_busy_progress('Exporting to Excel')
            excel_path, excel_sheet, excel_range = self.__export_excel_dialog.get_user_input()
            self.__save_export_params(excel_path)

            def on_export_success():
                # reset for fresh dialog on next launch
                get_progress_bar().stop_progress()
                self.__export_excel_dialog = None

            def on_export_error(excel_error: AsyncErrorInfo):
                get_progress_bar().stop_progress()
                on_excel_error("Sheet Export Error", excel_error.msg)
                self.__on_export_to_excel_action()  # relaunch this method (note: not recursive since async)

            AsyncRequest.call(self._part.write_excel, excel_path, excel_sheet, excel_range,
                              response_cb=on_export_success, error_cb=on_export_error)
        else:
            # cancelled: reset for fresh dialog on next launch
            self.__export_excel_dialog = None

    def __save_import_params(self, excel_path: str):
        """
        Save the Excel file path for the next time the import dialog is used.
        :param excel_path: the path to the Excel file.
        """
        self.__last_sheet_import_path = excel_path

    def __save_export_params(self, excel_path: str):
        """
        Save the Excel file path for the next time the import dialog is used.
        :param excel_path: the path to the Excel file.
        """
        self.__last_sheet_export_path = excel_path

    __slot_on_import_from_excel_action = safe_slot(__on_import_from_excel_action)
    __slot_on_export_to_excel_action = safe_slot(__on_export_to_excel_action)
    __slot_update_col_width = safe_slot(__update_col_width)


class TablePart2dContent(QWidget):
    """
    The content panel of a TablePart2dContent
    """

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.table_view = TablePartTableView()
        self.table_view.setShowGrid(False)
        layout.addWidget(self.table_view)

        h_header = QHeaderView(Qt.Horizontal)
        h_header.setSectionsClickable(False)
        h_header.setSectionsMovable(False)
        h_header.setSectionResizeMode(QHeaderView.Interactive)
        v_header = QHeaderView(Qt.Vertical)
        v_header.setSectionsClickable(False)
        v_header.setSectionsMovable(False)
        self.table_view.setHorizontalHeader(h_header)
        self.table_view.setVerticalHeader(v_header)


class TablePartWidget(FramedPartWidget):
    """
    A table part 2d widget
    """

    def __init__(self, part: TablePart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)
        self.__part = part
        self._set_content_widget(TablePart2dContent())
        self._table_model = TablePartTableModel(part)
        self._content_widget.table_view.setModel(self._table_model)

        self._update_size_from_part()
        self.__proxy_model = None

        self.__import_table_dialog = None
        self.__export_table_dialog = None
        self.__last_db_import_path = None
        self.__last_db_export_path = None
        self.__last_db_filter = None
        self.__set_custom_context_menu_options()

        # Connect slot to sort widget table based on editor settings
        self._table_model.sig_change_table_widget_display_order.connect(self.slot_on_display_order_changed)
        self._table_model.sig_rows_changed.connect(self.__slot_on_table_model_rows_changed)
        self._table_model.sig_cols_changed.connect(self.__slot_on_table_model_cols_changed)

    def on_display_order_changed(self, display_order: DisplayOrderEnum, sorted_column: List[str]):
        """
        Update the display order to correspond with user-selected sort setting.
        :param display_order: the display order enum set to alphabetical, reverse-alphabetical, or no order.
        :param sorted_column: the list of sorted columns (for now, it's just one column).
        """
        all_col_idxs = [col for col in range(self._table_model.cols)]

        if display_order == DisplayOrderEnum.alphabetical:
            self.__proxy_model = SortFilterProxyModelByColumns(self, all_col_idxs)
            self.__proxy_model.setSourceModel(self._table_model)
            self._content_widget.table_view.setModel(self.__proxy_model)
            self._content_widget.table_view.setSortingEnabled(True)
            self._content_widget.table_view.sortByColumn(sorted_column[0], Qt.AscendingOrder)

        elif display_order == DisplayOrderEnum.reverse_alphabetical:
            self.__proxy_model = SortFilterProxyModelByColumns(self, all_col_idxs)
            self.__proxy_model.setSourceModel(self._table_model)
            self._content_widget.table_view.setModel(self.__proxy_model)
            self._content_widget.table_view.setSortingEnabled(True)
            self._content_widget.table_view.sortByColumn(sorted_column[0], Qt.DescendingOrder)

        else:
            # This must be DisplayOrderEnum.of_creation
            self._content_widget.table_view.setModel(self._table_model)
            self._content_widget.table_view.setSortingEnabled(False)

    slot_on_display_order_changed = safe_slot(on_display_order_changed)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        try_disconnect(self._table_model.sig_change_table_widget_display_order, self.slot_on_display_order_changed)
        try_disconnect(self.__import_from_access_action.triggered, self.__slot_on_import_from_access_action)
        try_disconnect(self.__export_to_access_action.triggered, self.__slot_on_export_to_access_action)

    def __set_custom_context_menu_options(self):
        """
        Defines a set of context menu options unique to this part.
        """

        separator = QAction(self)
        separator.setSeparator(True)

        self.__import_from_access_action = create_action(self, "Import from Access...")
        self.__import_from_access_action.triggered.connect(self.__slot_on_import_from_access_action)
        self.__export_to_access_action = create_action(self, "Export to Access...")
        self.__export_to_access_action.triggered.connect(self.__slot_on_export_to_access_action)

    def __on_import_from_access_action(self):
        """
        Method called when the 'Import from Access' action is selected.
        """
        if self.__part.filter_string:
            # if there is a 'backend filter' use it
            filter_in_use = self.__part.filter_string
        else:
            # else, use the filter defined in the import dialog, if any
            filter_in_use = self.__last_db_filter

        if self.__import_table_dialog is None:
            self.__import_table_dialog = ImportDatabaseDialog(self.__part,
                                                              last_db_import_path=self.__last_db_import_path,
                                                              db_filter=filter_in_use)

        answer = self.__import_table_dialog.exec()
        if answer:
            get_progress_bar().start_busy_progress('Importing from Access')
            db_path, db_table, db_selected_fields, db_filter = self.__import_table_dialog.get_user_input()
            self.__save_import_params(db_path, db_table, db_filter)

            if not db_filter:
                db_filter = None  # change '' to None

            def on_import_success():
                # reset for fresh dialog on next launch
                get_progress_bar().stop_progress()
                self.__import_table_dialog = None

            def on_import_error(db_error: AsyncErrorInfo):
                get_progress_bar().stop_progress()
                title = "Database Import Error"
                msg = "If a table filter is applied, verify that SQLite syntax and column names are correct."
                on_database_error(title, db_error.msg, optional_msg=msg)
                self.__on_import_from_access_action()  # relaunch this method (note: not recursive since async)

            AsyncRequest.call(self.__part.import_from_msaccess, db_path, db_table, db_selected_fields, db_filter,
                              response_cb=on_import_success, error_cb=on_import_error)

        else:
            # cancelled: reset for fresh dialog on next launch
            self.__import_table_dialog = None

    def __on_export_to_access_action(self):
        """
        Method called when the 'Export to Access' action is selected.
        """

        def run_export_dialog(col_names: List[str]):
            """
            Run the export dialog.
            :param col_names: Current column names from the backend table part.
            """
            if self.__export_table_dialog is None:
                self.__export_table_dialog = ExportDatabaseDialog(self.__part,
                                                                  fields=col_names,
                                                                  last_db_export_path=self.__last_db_export_path)

            answer = self.__export_table_dialog.exec()
            if answer:
                get_progress_bar().start_busy_progress('Exporting to Access')
                db_path, db_table, db_selected_fields = self.__export_table_dialog.get_user_input()
                self.__save_export_params(db_path)

                def on_export_success():
                    # reset for fresh dialog on next launch
                    get_progress_bar().stop_progress()
                    self.__export_table_dialog = None

                def on_export_error(db_error: AsyncErrorInfo):
                    get_progress_bar().stop_progress()
                    title = "Database Export Error"
                    on_database_error(title, db_error.msg)
                    self.__on_export_to_access_action()  # relaunch this method (note: not recursive since async)

                AsyncRequest.call(self.__part.export_to_msaccess, db_path, db_table, db_selected_fields,
                                  response_cb=on_export_success, error_cb=on_export_error)
            else:
                # cancelled: reset for fresh dialog on next launch
                self.__export_table_dialog = None

        # get the column names from backend table part
        AsyncRequest.call(self.__part.get_column_names, response_cb=run_export_dialog)

    def __save_import_params(self, db_path: str, _: str, db_filter: str):
        """
        Save the database path and filter for the next time the import dialog is used.
        :param db_path: the path to the database.
        :param _: unused parameter.
        :param db_filter: the SQL "WHERE" clause to get only specific data that matches the filter.
        """
        if not db_filter:
            # change '' to None
            db_filter = None

        self.__last_db_import_path = db_path
        self.__last_db_filter = db_filter

    def __save_export_params(self, db_path: str):
        """
        Save the database path and filter for the next time the import dialog is used.
        :param db_path: the path to the database.
        """
        self.__last_db_export_path = db_path

    def __on_table_model_rows_changed(self, _: int):
        """
        React to changes in the number of rows in the table model.
        :param _: unused parameter.
        """
        self.__enabled_database_options()

    def __on_table_model_cols_changed(self, _: int):
        """
        React to changes in the number of columns in the table model.
        :param _: unused parameter.
        """
        self.__enabled_database_options()

    def __enabled_database_options(self):
        """
        Enables or disable the export database option based on number of rows and columns in the table.
        """
        rows = self._table_model.rows
        columns = self._table_model.cols
        if rows > 0 and columns > 0:
            self.__export_to_access_action.setEnabled(True)
        else:
            self.__export_to_access_action.setEnabled(False)

    __slot_on_import_from_access_action = safe_slot(__on_import_from_access_action)
    __slot_on_export_to_access_action = safe_slot(__on_export_to_access_action)
    __slot_on_table_model_rows_changed = safe_slot(__on_table_model_rows_changed)
    __slot_on_table_model_cols_changed = safe_slot(__on_table_model_cols_changed)


class LibraryPart2dContent(QWidget):
    """
    The content panel of a LibraryPartWidget.
    """

    def __init__(self):
        """
        The Library Part GUI.
        """
        super().__init__()
        vertical_layout = QVBoxLayout(self)
        vertical_layout.setContentsMargins(4, 4, 4, 4)
        vertical_layout.setSpacing(2)
        self.function_listing = ScriptEditBox()
        self.function_listing.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.function_listing.setReadOnly(True)
        vertical_layout.addWidget(self.function_listing)


class LibraryPartWidget(BreakpointIndicator, FramedPartWidget, IExecPartWidget):
    def __init__(self, part: LibraryPart, parent_part_box_item: PartBoxItem = None):
        """
        The Library Part GUI is initialized with the backend Library Part data.

        :param part: The backend of this GUI.
        """
        FramedPartWidget.__init__(self, part, parent_part_box_item)
        BreakpointIndicator.__init__(self, parent_part_box_item)
        self._initialize_run()

        self.__debug_mode = False
        self.__list_and_fire = None

        self._set_content_widget(LibraryPart2dContent())

        separator = QAction(self)
        separator.setSeparator(True)

        self._update_size_from_part()

        def _init_values_from_part(script: str):
            """
            Method used to initialize value of script text.
            :param script: The script as text to place into the code viewer.
            """
            self._content_widget.function_listing.setPlainText(script)

        AsyncRequest.call(part.get_script, response_cb=_init_values_from_part)

        self._part.scripting_signals.sig_script_changed.connect(self.__slot_on_script_changed)

    @override(IExecPartWidget)
    def _run_part(self):
        """
        Lists all the callable objects, if any, in this part as running candidates.
        """
        self.__debug_mode = False
        self.__list_candidates_to_run()

    @override(IExecPartWidget)
    def _debug_part(self):
        """
        Lists all the callable objects, if any, in this part as debugging candidates.
        """
        self.__debug_mode = True
        self.__list_candidates_to_run()

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        FramedPartWidget._disconnect_all_slots(self)
        IExecPartWidget._disconnect_all_slots(self)
        scripting_signals = self._part.scripting_signals
        try_disconnect(scripting_signals.sig_script_changed, self.__slot_on_script_changed)

    def __list_candidates_to_run(self):
        """
        Lists all the callable objects, if any, in this part.
        """

        def on_response(name_list: List[str], sig_list: List[signature]):
            if len(name_list) == 0:
                exec_modal_dialog("Runable Functions", "There are no functions defined in the library.",
                                  QMessageBox.Information)
                return

            self.__list_and_fire = ListAndFirePopup(name_list, sig_list)
            answer = self.__list_and_fire.exec()
            if answer:
                self.__run_selected_function(self.__list_and_fire.get_run_function_name())

        def on_error(_: AsyncErrorInfo):
            self.show_alerts_message()

        AsyncRequest.call(self._part.get_script_function_defs,
                          response_cb=on_response,
                          error_cb=on_error)

    def __run_selected_function(self, func_name: str):
        """
        Runs or debugs the function selected by the func_name depending on the run or debug mode previously selected.

        If a function needs arguments to run or debug, a popup dialog will be opened to collect them.

        :param func_name: The name of the function selected.
        """
        self._complete_execution(self._part.call_script_func, self._part.get_script_func_signature,
                                 debug=self.__debug_mode, func_name=func_name)

    def __on_script_changed(self, new_script: str):
        """
        Method called when the script changes.
        :param new_script: The new script to put into the editor.
        """
        self._content_widget.function_listing.setPlainText(new_script)

    __slot_on_script_changed = safe_slot(__on_script_changed)
    __slot_run_selected_function = safe_slot(__run_selected_function)


class ButtonPart2dContent(QWidget):
    """
    The content panel of a ButtonPartWidget
    """

    def __init__(self, logical_owner: QWidget, button_pressed: bool = False):
        """
        The Button Part GUI is initialized with the momentary image by default.
        :param logical_owner: The widget that holds this widget - the logical owner of this widget in
        Origame, not the Qt parent, which is the QStackedWidget.
        """
        super().__init__()
        self.ui_button_part = Ui_ButtonPartWidget()
        self.ui_button_part.setupUi(self, button_pressed)
        self.ui_button_part.push_button.set_logical_owner(logical_owner)

    def set_image_pressed(self, new_path: str = None):
        """
        Changes the pressed image.

        :param new_path: The new path of the pressed image.
        """
        self.ui_button_part.push_button.on_image_load(new_path)

    def set_image_released(self, new_path: str = None):
        """
        Changes the released image.

        :param new_path: The new path of the released image.
        """
        self.ui_button_part.push_button.off_image_load(new_path)

    def set_rotation_2d_pressed(self, rotation_in_angle: float):
        self.ui_button_part.push_button.on_image_rotate(rotation_in_angle)

    def set_rotation_2d_released(self, rotation_in_angle: float):
        self.ui_button_part.push_button.off_image_rotate(rotation_in_angle)

    def manage_size(self):
        """
        Makes the image fit in the container - centered and with aspect ratio.
        """
        self.ui_button_part.push_button.manage_size()


class ButtonPartWidget(FramedPartWidget):
    """
    A Button Part 2d widget
    """

    def __init__(self, part: ButtonPart, parent_part_box_item: PartBoxItem = None):
        """
        The Button Part GUI is initialized with the backend Button Part data.

        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)
        self.__button_action = ButtonActionEnum.momentary
        self.__img_pressed = DEFAULT_BUTTON_DOWN
        self.__img_released = DEFAULT_BUTTON_UP
        self.__rotation_2d_pressed = 0
        self.__rotation_2d_released = 0

        self._update_size_from_part()
        if part.button_action == ButtonActionEnum.toggle and part.state == ButtonStateEnum.pressed:
            self._set_content_widget(ButtonPart2dContent(self, button_pressed=True))
        else:
            self._set_content_widget(ButtonPart2dContent(self))

        def _get_init_data():
            return (part.button_action, part.state,
                    part.rotation_2d_pressed, part.rotation_2d_released,
                    part.image_path_pressed, part.image_path_released)

        def _init_values_from_part(button_action, state,
                                   rotation_2d_pressed, rotation_2d_released,
                                   image_path_pressed, image_path_released):
            self.__on_button_action_changed(button_action)
            self.__on_button_state_changed(state)
            self.__on_rotation_2d_pressed_changed(rotation_2d_pressed)
            self.__on_rotation_2d_released_changed(rotation_2d_released)
            self.__on_image_pressed_path_changed(image_path_pressed)
            self.__on_image_released_path_changed(image_path_released)

        AsyncRequest.call(_get_init_data, response_cb=_init_values_from_part)

        self._content_widget.ui_button_part.push_button.pressed.connect(self.__slot_on_pressed)
        self._content_widget.ui_button_part.push_button.released.connect(self.__slot_on_released)
        self._part.signals.sig_button_action_changed.connect(self.__slot_on_button_action_changed)
        self._part.signals.sig_button_state_changed.connect(self.__slot_on_button_state_changed)
        self._part.signals.sig_rotation_2d_pressed_changed.connect(self.__slot_on_rotation_2d_pressed_changed)
        self._part.signals.sig_rotation_2d_released_changed.connect(self.__slot_on_rotation_2d_released_changed)
        self._part.signals.sig_image_pressed_path_changed.connect(self.__slot_on_image_pressed_path_changed)
        self._part.signals.sig_image_released_path_changed.connect(self.__slot_on_image_released_path_changed)

    @override(QWidget)
    def resizeEvent(self, event: QResizeEvent):
        self.__render()
        super(ButtonPartWidget, self).resizeEvent(event)

    @override(FramedPartWidget)
    def _set_size(self, width: float, height: float):
        if self._content_widget is not None:
            self.__render()
        super()._set_size(width, height)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        signals = self._part.signals
        try_disconnect(signals.sig_button_action_changed, self.__slot_on_button_action_changed)
        try_disconnect(signals.sig_button_state_changed, self.__slot_on_button_state_changed)
        try_disconnect(signals.sig_rotation_2d_pressed_changed, self.__slot_on_rotation_2d_pressed_changed)
        try_disconnect(signals.sig_rotation_2d_released_changed, self.__slot_on_rotation_2d_released_changed)
        try_disconnect(signals.sig_image_pressed_path_changed, self.__slot_on_image_pressed_path_changed)
        try_disconnect(signals.sig_image_released_path_changed, self.__slot_on_image_released_path_changed)
        try_disconnect(self._content_widget.ui_button_part.push_button.pressed, self.__slot_on_pressed)
        try_disconnect(self._content_widget.ui_button_part.push_button.released, self.__slot_on_released)

    _slot_set_size = safe_slot(_set_size)

    def __on_button_state_changed(self, button_state: int):
        """
        Sets the button checked(on) or unchecked(off) upon the backend request.

        :param button_state: one of the values of ButtonStateEnum
        """
        button_state = ButtonStateEnum(button_state)
        if self.__button_action == ButtonActionEnum.momentary:
            if button_state == ButtonStateEnum.pressed:
                self._content_widget.ui_button_part.push_button.setChecked(True)
            else:
                self._content_widget.ui_button_part.push_button.setChecked(False)
        elif self.__button_action == ButtonActionEnum.toggle:
            if button_state == ButtonStateEnum.pressed:
                self._content_widget.ui_button_part.push_button.setChecked(False)
            else:
                self._content_widget.ui_button_part.push_button.setChecked(True)

    def __on_button_action_changed(self, button_action: int):
        """
        This function re-initializes the button following a button Action type change.

        :param button_action: one of the values of ButtonActionEnum
        """
        button_action = ButtonActionEnum(button_action)
        if self.__button_action == button_action:
            return

        self.__button_action = button_action
        if self._content_widget.ui_button_part.push_button.isChecked():
            self._content_widget.ui_button_part.push_button.click()
        self.__render()

    def __on_rotation_2d_pressed_changed(self, rotation_in_angle: float):
        if self.__rotation_2d_pressed == rotation_in_angle:
            return

        self.__rotation_2d_pressed = rotation_in_angle
        self.__render()

    def __on_rotation_2d_released_changed(self, rotation_in_angle: float):
        if self.__rotation_2d_released == rotation_in_angle:
            return

        self.__rotation_2d_released = rotation_in_angle
        self.__render()

    def __on_image_pressed_path_changed(self, new_path: str):
        """
        Change the button pressed image.

        :param new_path: The new path of the pressed image.
        """
        if self.__img_pressed == new_path:
            return

        self.__img_pressed = new_path
        self.__render()

    def __on_image_released_path_changed(self, new_path: str):
        """
        Change the button released image.

        :param new_path: The new path of the released image.
        """
        if self.__img_released == new_path:
            return

        self.__img_released = new_path
        self.__render()

    def __on_pressed(self):
        """
        This is similar to how a Function Part would call a function. This is a regular async call on the button part's
        on_user_press function, which calls further the linked callable parts, if any.
        """

        def on_error(error_info: AsyncErrorInfo):
            exec_modal_dialog("Button Press Error", error_info.msg, QMessageBox.Critical)
            self.__on_released()

        AsyncRequest.call(self._part.on_user_press, error_cb=on_error)

    def __on_released(self):
        """
        This is similar to how a Function Part would call a function. This is a regular async call on the button part's
        on_user_release function, which calls further the linked callable parts, if any.
        """

        def on_error(error_info: AsyncErrorInfo):
            exec_modal_dialog("Button Release Error", error_info.msg, QMessageBox.Critical)

        AsyncRequest.call(self._part.on_user_release, error_cb=on_error)

    def __img_with_fallback(self, img_path: str) -> str:
        """
        If the img_path points to an invalid image, this function returns a pre-defined image pointed by
        BUTTON_IMAGE_NOT_FOUND.

        :param img_path: The intended image path the function calls
        :return the image path if it points to a valid image or the path pointed by BUTTON_IMAGE_NOT_FOUND
        """
        if QPixmap(img_path).isNull():
            return BUTTON_IMAGE_NOT_FOUND
        else:
            return img_path

    def __render(self):
        """
        After we change the button action or images, we need to refresh the button.
        """
        if self.__button_action == ButtonActionEnum.momentary:
            if not self.__img_pressed:
                self._content_widget.set_image_pressed(DEFAULT_BUTTON_DOWN)
                self._content_widget.set_rotation_2d_pressed(self.__rotation_2d_pressed)
            else:
                self._content_widget.set_image_pressed(self.__img_with_fallback(self.__img_pressed))
                self._content_widget.set_rotation_2d_pressed(self.__rotation_2d_pressed)
            if not self.__img_released:
                self._content_widget.set_image_released(DEFAULT_BUTTON_UP)
                self._content_widget.set_rotation_2d_released(self.__rotation_2d_released)
            else:
                self._content_widget.set_image_released(self.__img_with_fallback(self.__img_released))
                self._content_widget.set_rotation_2d_released(self.__rotation_2d_released)
        else:
            if not self.__img_pressed:
                self._content_widget.set_image_pressed(DEFAULT_BUTTON_ON)
                self._content_widget.set_rotation_2d_pressed(self.__rotation_2d_pressed)
            else:
                self._content_widget.set_image_pressed(self.__img_with_fallback(self.__img_pressed))
                self._content_widget.set_rotation_2d_pressed(self.__rotation_2d_pressed)
            if not self.__img_released:
                self._content_widget.set_image_released(DEFAULT_BUTTON_OFF)
                self._content_widget.set_rotation_2d_released(self.__rotation_2d_released)
            else:
                self._content_widget.set_image_released(self.__img_with_fallback(self.__img_released))
                self._content_widget.set_rotation_2d_released(self.__rotation_2d_released)

        self._content_widget.manage_size()

    __slot_on_button_state_changed = safe_slot(__on_button_state_changed)
    __slot_on_button_action_changed = safe_slot(__on_button_action_changed)
    __slot_on_rotation_2d_pressed_changed = safe_slot(__on_rotation_2d_pressed_changed)
    __slot_on_rotation_2d_released_changed = safe_slot(__on_rotation_2d_released_changed)
    __slot_on_image_pressed_path_changed = safe_slot(__on_image_pressed_path_changed)
    __slot_on_image_released_path_changed = safe_slot(__on_image_released_path_changed)
    __slot_on_pressed = safe_slot(__on_pressed)
    __slot_on_released = safe_slot(__on_released)


class PlotPart2dContent(QWidget):
    """
    Provides the plot canvas to show the figure in the content view.
    """

    def __init__(self, logical_owner: QWidget):
        super().__init__()
        self.__layout = QVBoxLayout(self)
        self.__logical_owner = logical_owner
        self.canvas = None
        self.current_figure_dpi = None
        self.draw_unrefreshed_plot("Unrefreshed Plot")

    def add_display_widget(self, widget: QWidget):
        """
        Add the widget used to display the plot to the UI of the content widget.
        :param display_widget: The widget component used to display the plot.
        """
        self.canvas = widget
        self.__layout.setContentsMargins(1,1,1,1)
        self.__layout.addWidget(self.canvas)

    def remove_display_widget(self):
        """
        Remove the widget used to display the plot from the UI of the content widget.
        :return: The display widget.
        """
        if self.canvas is not None:
            self.canvas.setParent(None)
            self.canvas = None

    def draw_unrefreshed_plot(self, display_text: str):
        """
        On initial load of the Plot Editor, always show the unrefreshed plot figure until the user deliberately clicks
        on the refresh button.
        :param display_text: The text to show in the unrefreshed plot.
        """
        self.remove_display_widget()
        figure = pyplot.Figure(figsize=DEFAULT_FIG_SIZE, facecolor=PlotPart.DEFAULT_FACE_COLOR)
        figure.text(0.5, 0.5, display_text, horizontalalignment='center', verticalalignment='center')
        figure.add_subplot(1, 1, 1)
        self.add_display_widget(PlotFigureCanvas(figure))
        self.manage_size()
        self.refreshed = False

    def manage_size(self):
        """
        Makes the plot fit in the container - with aspect ratio.
        """
        fit_in = self.canvas.size().scaled(self.__logical_owner.size(), Qt.KeepAspectRatio)
        self.canvas.setFixedSize(fit_in * 0.9)

class PlotPartWidget(BreakpointIndicator, FramedPartWidget):
    """
    A plot part 2d widget
    """

    def __init__(self, part: PlotPart, parent_part_box_item: PartBoxItem = None):
        """
        Sets up the plot part widget to display figures from the backend part
        :param part: The backend plot part.
        """
        self.__plot_specific_buttons_ready = False
        FramedPartWidget.__init__(self, part, parent_part_box_item)
        BreakpointIndicator.__init__(self, parent_part_box_item)
        self.__set_custom_context_menu_options()
        self._update_size_from_part()
        self._set_content_widget(PlotPart2dContent(self))
        self.__export_image_dialog = ExportImageDialog(part)
        self.__export_data_dialog = ExportDataDialog(part)
        self.__set_canvas_management_buttons()
        part.signals.sig_axes_changed.connect(self.__slot_on_backend_plot_update)

        if not self._content_widget.refreshed:
            self.export_image_action.setEnabled(False)
            self.export_data_action.setEnabled(False)
        else:
            self._content_widget.refreshed = True

    @override(QWidget)
    def resizeEvent(self, event: QResizeEvent):
        self._content_widget.manage_size()
        super(PlotPartWidget, self).resizeEvent(event)

    @override(FramedPartWidget)
    def _update_detail_level_view(self):
        """
        Updates the GUI according to the detail level state. Manages the plot part specific buttons.
        """
        super(PlotPartWidget, self)._update_detail_level_view()
        if self._detail_level_in_effect() == DetailLevelEnum.minimal:
            self.export_image_action.setEnabled(False)
            self.export_data_action.setEnabled(False)
            if self.__plot_specific_buttons_ready:
                self.__plot_update_button.setVisible(False)
        else:
            if self._content_widget.refreshed:
                self.export_image_action.setEnabled(True)
                self.export_data_action.setEnabled(True)
            if self.__plot_specific_buttons_ready:
                self.__plot_update_button.setVisible(True)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        FramedPartWidget._disconnect_all_slots(self)
        signals = self._part.signals
        try_disconnect(signals.sig_axes_changed, self.__slot_on_backend_plot_update)
        try_disconnect(self.__plot_update_button.clicked, self.__slot_on_frontend_plot_update)
        try_disconnect(self.export_image_action.triggered, self.__slot_launch_export_image_dialog)
        try_disconnect(self.export_data_action.triggered, self.__slot_launch_export_data_dialog)

    def __set_canvas_management_buttons(self):
        """
        Adds buttons to the part frame which updates and zooms the plot.
        """
        # Update button
        detail_level_in_effect = self._detail_level_in_effect()
        self.__plot_update_button = SvgToolButton(PLOT_UPDATE, self.ui.header_frame)
        self._add_header_frame_obj(FramedPartHeaderObjTypeEnum.plot_update, self.__plot_update_button)
        self.__plot_update_button.setVisible(detail_level_in_effect == DetailLevelEnum.full)
        self.__plot_update_button.setToolTip("Update the plot")
        self.__plot_update_button.clicked.connect(self.__slot_on_frontend_plot_update)

        self.__plot_specific_buttons_ready = True

        self._update_detail_level_view()

    def __set_custom_context_menu_options(self):
        """
        Defines a set of context menu options unique to this part.
        """
        separator = QAction(self)
        separator.setSeparator(True)

        # Plot export options
        self.export_image_action = create_action(self, "Export Image...", tooltip="Export snapshot of this plot...")
        self.export_image_action.triggered.connect(self.__slot_launch_export_image_dialog)
        self.export_data_action = create_action(self, "Export Data...", tooltip="Export data from this plot...")
        self.export_data_action.triggered.connect(self.__slot_launch_export_data_dialog)

        # Trigger the backend to update the plot part
        self.update_plot_action = create_action(self, "Update Plot", tooltip="Update plot (rerun its script)")
        self.update_plot_action.triggered.connect(self.__slot_on_frontend_plot_update)

    def __on_backend_plot_update(self):
        """
        Updates the plot when the backend figure is changed.
        """
        self._content_widget.remove_display_widget()
        self._content_widget.add_display_widget(PlotFigureCanvas(self._part.figure))
        self._content_widget.refreshed = True

        # If the dpi has been updated since the last time the plot was updated, resize the plot part frame to accommodate the new dpi
        if self._content_widget.current_figure_dpi != self._part.figure.dpi:
            self._content_widget.current_figure_dpi = self._part.figure.dpi
            min_width = self._part.MIN_CONTENT_SIZE['width']  * SCALE_FACTOR
            min_height = self._part.MIN_CONTENT_SIZE['height'] * SCALE_FACTOR
            self.size_grip_corner.set_min_size(min_width, min_height)
            self.size_grip_right.set_min_size(min_width, min_height)
            self.size_grip_bottom.set_min_size(min_width, min_height)
            self.setFixedSize(int(min_width), int(min_height))

        self._content_widget.manage_size()

        if self._detail_level_in_effect() == DetailLevelEnum.full:
            self.export_image_action.setEnabled(True)
            self.export_data_action.setEnabled(True)

    def __on_frontend_plot_update(self):
        """
        Requests the backend to update itself when the widget "Update" button is pressed.
        """
        stop_progress = get_progress_bar().stop_progress

        def on_error(err: AsyncErrorInfo):
            stop_progress()
            self.show_alerts_message()

        get_progress_bar().start_busy_progress('Plot ' + str(self._part))
        self._content_widget.draw_unrefreshed_plot("Update pending...")
        AsyncRequest.call(self._part.update_fig, response_cb=stop_progress, error_cb=on_error)

    def __launch_export_image_dialog(self):
        """
        Launches the image export dialog.
        """
        assert self._content_widget.refreshed is True
        self.__export_image_dialog.ui.image_path_line_edit.clear()
        self.__export_image_dialog.exec()

    def __launch_export_data_dialog(self):
        """
        Launches the image data dialog.
        """
        assert self._content_widget.refreshed is True
        self.__export_data_dialog.ui.file_path_line_edit.clear()
        self.__export_data_dialog.exec()

    __slot_on_backend_plot_update = safe_slot(__on_backend_plot_update)
    __slot_on_frontend_plot_update = safe_slot(__on_frontend_plot_update)
    __slot_launch_export_image_dialog = safe_slot(__launch_export_image_dialog)
    __slot_launch_export_data_dialog = safe_slot(__launch_export_data_dialog)


class SqlPart2dContent(QWidget):
    """
    The content panel of a SqlPartWidget.
    """

    def __init__(self):
        super().__init__()

        self.ui_sql_part = Ui_SqlPartWidget()
        self.ui_sql_part.setupUi(self)


class SqlPartWidget(EventCounterManager, FramedPartWidget, IExecPartWidget):
    """
    A Sql Part 2D Widget
    """

    def __init__(self, part: SqlPart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        FramedPartWidget.__init__(self, part, parent_part_box_item)
        EventCounterManager.__init__(self, part, parent_part_box_item)
        self._initialize_run(allow_debug=False)

        self._part = part

        QAction(self).setSeparator(True)

        self._set_content_widget(SqlPart2dContent())

        def _get_init_data():
            return part.get_sql_script(), part.get_parameters()

        def _init_values_from_part(script: str, parameters: str):
            self.__on_sql_script_changed(script)
            self.__on_parameters_changed(parameters)

        AsyncRequest.call(_get_init_data, response_cb=_init_values_from_part)

        self._update_size_from_part()

        self._part.signals.sig_sql_script_changed.connect(self.__slot_on_sql_script_changed)
        self._part.exec_signals.sig_params_changed.connect(self.__slot_on_on_parameters_changed)

    @override(IExecPartWidget)
    def _run_part(self):
        self._complete_execution(part_call=self._part.call, sig_getter=self._part.get_signature)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        FramedPartWidget._disconnect_all_slots(self)
        IExecPartWidget._disconnect_all_slots(self)
        EventCounterManager._disconnect_all_slots(self)
        signals = self._part.signals
        exec_signals = self._part.exec_signals
        try_disconnect(signals.sig_sql_script_changed, self.__slot_on_sql_script_changed)
        try_disconnect(exec_signals.sig_params_changed, self.__slot_on_on_parameters_changed)

    def __on_sql_script_changed(self, script: str):
        """
        Set the script, which is allowed to contain multiple statements.

        :param script: The SQL script.
        """
        self._content_widget.ui_sql_part.script.setPlainText(script)

    def __on_parameters_changed(self, parameters: str):
        """
        Set the parameters. Multiple parameters must be comma delimited.

        :param parameters: The parameter list.
        """
        self._content_widget.ui_sql_part.parameters.setText(parameters)

    __slot_on_sql_script_changed = safe_slot(__on_sql_script_changed)
    __slot_on_on_parameters_changed = safe_slot(__on_parameters_changed)


class PulsePart2dContent(QWidget):
    """
    The content panel of a pulse part 2d widget.
    """

    def __init__(self):
        super().__init__()

        self.ui_pulse_part = Ui_PulsePartWidget()
        self.ui_pulse_part.setupUi(self)


class PulsePartWidget(EventCounterManager, FramedPartWidget):
    """
    A pulse part 2d widget
    """

    def __init__(self, part: PulsePart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        FramedPartWidget.__init__(self, part, parent_part_box_item)
        EventCounterManager.__init__(self, part, parent_part_box_item)
        self._set_content_widget(PulsePart2dContent())

        part.signals.sig_pulse_period_days_changed.connect(self.__slot_on_pulse_period_changed)
        part.signals.sig_state_changed.connect(self.__slot_on_state_changed)
        part.signals.sig_priority_changed.connect(self.__slot_on_priority_changed)

        self._update_size_from_part()

        def _get_init_data():
            return (part.get_pulse_period_days(),
                    part.get_state(),
                    part.get_priority(),
                    parent_part_box_item.part.get_queue_counts())

        def _init_values_from_part(period: float, state: PulsePartState, priority: float,
                                   queue_counts: Tuple[bool, int, int]):
            self.__on_pulse_period_changed(period)
            self.__on_state_changed(state)
            self.__on_priority_changed(priority)
            is_next, count_concur, count_after = queue_counts
            self._queue_counters_changed(is_next, count_concur, count_after)

        AsyncRequest.call(_get_init_data, response_cb=_init_values_from_part)

    @override(FramedPartWidget)
    def _disconnect_all_slots(self):
        FramedPartWidget._disconnect_all_slots(self)
        EventCounterManager._disconnect_all_slots(self)
        signals = self._part.signals
        try_disconnect(signals.sig_pulse_period_days_changed, self.__slot_on_pulse_period_changed)
        try_disconnect(signals.sig_state_changed, self.__slot_on_state_changed)
        try_disconnect(signals.sig_priority_changed, self.__slot_on_priority_changed)

    def __on_pulse_period_changed(self, pulse_period_days: float):
        """Updates the widget with new pulse period (days)."""
        self._content_widget.ui_pulse_part.period_edit.setText(
            convert_float_days_to_tick_period(pulse_period_days))

    def __on_state_changed(self, value: int):
        """
        Updates the widget with new state.
        :param value: the value of the new state.
        """
        state = PulsePartState(value)
        if state == PulsePartState.inactive:
            pulse_state = 'Inactive'
        else:
            pulse_state = 'Active'

        self._content_widget.ui_pulse_part.state_edit.setText(pulse_state)

    def __on_priority_changed(self, priority: float):
        """Updates the widget with the new priority."""
        self._content_widget.ui_pulse_part.priority_edit.setText(str(priority))

    __slot_on_pulse_period_changed = safe_slot(__on_pulse_period_changed)
    __slot_on_state_changed = safe_slot(__on_state_changed)
    __slot_on_priority_changed = safe_slot(__on_priority_changed)


register_part_item_class(ori.OriActorPartKeys.PART_TYPE_ACTOR, ChildActorWidget)
register_part_item_class(ori.OriFunctionPartKeys.PART_TYPE_FUNCTION, FunctionPartWidget)
register_part_item_class(ori.OriClockPartKeys.PART_TYPE_CLOCK, ClockPartWidget)
register_part_item_class(ori.OriDateTimePartKeys.PART_TYPE_DATETIME, DateTimePartWidget)
register_part_item_class(ori.OriTimePartKeys.PART_TYPE_TIME, TimePartWidget)
register_part_item_class(ori.OriVariablePartKeys.PART_TYPE_VARIABLE, VariablePartWidget)
register_part_item_class(ori.OriFilePartKeys.PART_TYPE_FILE, FilePartWidget)
register_part_item_class(ori.OriDataPartKeys.PART_TYPE_DATA, DataPartWidget)
register_part_item_class(ori.OriSheetPartKeys.PART_TYPE_SHEET, SheetPartWidget)
register_part_item_class(ori.OriTablePartKeys.PART_TYPE_TABLE, TablePartWidget)
register_part_item_class(ori.OriLibraryPartKeys.PART_TYPE_LIBRARY, LibraryPartWidget)
register_part_item_class(ori.OriButtonPartKeys.PART_TYPE_BUTTON, ButtonPartWidget)
register_part_item_class(ori.OriPlotPartKeys.PART_TYPE_PLOT, PlotPartWidget)
register_part_item_class(ori.OriSqlPartKeys.PART_TYPE_SQL, SqlPartWidget)
register_part_item_class(ori.OriPulsePartKeys.PART_TYPE_PULSE, PulsePartWidget)
register_part_item_class('parent_proxy', ParentActorProxyWidget)
