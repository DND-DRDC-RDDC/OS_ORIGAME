# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Framed 2D widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum, unique

# [2. third-party]
from PyQt5.QtCore import Qt, QSize, QMarginsF
from PyQt5.QtGui import QPalette
from PyQt5.QtWidgets import QWidget, QAction, QHBoxLayout, QLabel, QMessageBox, QDialog
from PyQt5.QtSvg import QSvgWidget

# [3. local]
from ...core import override, override_optional, override_required
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...scenario.defn_parts import BasePart, DetailLevelEnum, Size

from ..call_params import CallArgs
from ..gui_utils import exec_modal_dialog
from ..gui_utils import part_image, get_scenario_font, get_icon_path, try_disconnect
from ..gui_utils import PROXIMITY_MARGIN_LEFT, PROXIMITY_MARGIN_TOP, PROXIMITY_MARGIN_RIGHT, PROXIMITY_MARGIN_BOTTOM
from ..gui_utils import LINK_CREATION_ACTION_ITEM_HEIGHT, QWIDGETSIZE_MAX, PART_ICON_COLORS
from ..call_params import ParameterInputDialog
from ..conversions import SCALE_FACTOR
from ..safe_slot import safe_slot
from ..actions_utils import create_action
from ..undo_manager import scene_undo_stack, ChangeDetailLevelCommand, ResizeCommand
from ..slow_tasks import get_progress_bar
from ..async_methods import AsyncRequest, AsyncErrorInfo

from .indicators import AlertIndicator
from .custom_items import SizeGripCornerItem, SizeGripRightItem, SizeGripBottomItem
from .custom_widgets import SMALL_ICON_SIZE_WIDTH, SMALL_ICON_SIZE_HEIGHT, SvgToolButton, DetailLevelChangeButton
from .common import DetailLevelOverrideEnum
from .Ui_framed_widget import Ui_FramedPartWidget
from .Ui_frameless_widget import Ui_FramelessPartWidget

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # defines module members that are public; one line per string
    'FramedPartWidget'
    'FramelessPartWidget',
    'FramedPartHeaderObjTypeEnum',
    'IExecPartWidget'
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    PartBoxItem = 'PartBoxItem'
    WidgetProxyPartItem = 'WidgetProxyPartItem'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

@unique
class FramedPartHeaderObjTypeEnum(IntEnum):
    """
    This class represents the keys of the objects that are allowed to go to the header frame of the FramedPartWidget.
    """
    small_icon, part_name, spacer, run_button, plot_update, detail_level_change = range(6)


class IPartWidget(AlertIndicator, QWidget):
    """
    This is the base class for all Parts that are represented in the QGraphicsScene by a proxied QWidget.
    The derived class must override those methods marked "override_required", optionally override those that
    are marked "override_optional", and leave untouched other methods.

    All IPartWidget are also alert indicators, monitor the alert status of the corresponding backend scenario
    part to show or hide the indicator as appropriate.
    """

    def __init__(self, part: BasePart, parent_part_box_item: Decl.PartBoxItem):
        """
        :param part: the part that this part widget represents in 2d view
        :param parent_part_box_item: the part box graphics item that wraps this part widget
        """
        QWidget.__init__(self)
        AlertIndicator.__init__(self, part, parent_part_box_item)
        self._part = part
        self.__size_grip_end_action = None
        self.__initialized = False

    @override_optional
    def get_selection_margins(self) -> QMarginsF:
        """
        An item on the screen has a base selection area. Sometimes, one size cannot fit all. For example, an item
        such as an actor may have ifx ports, thus requires a bigger selection area.

        The derived class implements this function to return margins that will be added to the selection area. By
        default, this function returns all-zero margins.

        :return: The margins to be added to the base selection area.
        """
        return QMarginsF()

    @override_optional
    def get_proximity_margins(self) -> QMarginsF:
        """
        An item on the screen has a base proximity area. Sometimes, one size cannot fit all. For example, an item
        such as an actor may have ifx ports, thus requires a bigger proximity area.

        The derived class implements this function to return margins that will be added to the proximity area. By
        default, this function returns constant margins defined by PROXIMITY_MARGIN_*.

        :return: The margins to be added to the base proximity area.
        """
        return QMarginsF(PROXIMITY_MARGIN_LEFT, PROXIMITY_MARGIN_TOP, PROXIMITY_MARGIN_RIGHT, PROXIMITY_MARGIN_BOTTOM)

    @override_optional
    def populate_data(self):
        """
        Those widgets that could slow down __init_ may override this function to populate data after the
        __init__(). Two of the examples are data part and sheet part widgets.
        
        The background:
        If the construction of a part widget cannot be completed in a timely manner in the __init__, the 
        QGraphicsWidget.setWidget() will be blocked. So, the item cannot be added to the scene. That would be an
        annoying user experience because the user cannot see the frame of the part while it is preparing the data.
        """
        pass

    def init_boxed_part_item(self, widget_proxy_part_item_class):
        """
        Wraps this instance with a widget proxy.
        :param widget_proxy_part_item_class: The class WidgetProxyPartItem. Note: We pass it as a class because
        importing it would cause circular references.
        :return: the wrapped self
        """
        assert self.__initialized is False

        part_item = widget_proxy_part_item_class(self._parent_part_box_item, self)
        part_item.geometryChanged.connect(self._parent_part_box_item.slot_on_size_changed)
        # Install the three size grips
        self.__size_grip_end_action = create_action(self._parent_part_box_item,
                                                    text='Resize',
                                                    connect=self.__slot_sizing_action_ended)
        min_width = self._part.part_frame.get_min_width() * SCALE_FACTOR
        min_height = self._part.part_frame.get_min_height() * SCALE_FACTOR
        self.size_grip_corner = SizeGripCornerItem(widget_to_resize=self,
                               min_width=min_width,
                               min_height=min_height,
                               parent=self._parent_part_box_item.part_selection_border_item,
                               end_action=self.__size_grip_end_action)
        self.size_grip_right = SizeGripRightItem(widget_to_resize=self,
                              min_width=min_width,
                              min_height=min_height,
                              parent=self._parent_part_box_item.part_selection_border_item,
                              end_action=self.__size_grip_end_action)
        self.size_grip_bottom = SizeGripBottomItem(widget_to_resize=self,
                               min_width=min_width,
                               min_height=min_height,
                               parent=self._parent_part_box_item.part_selection_border_item,
                               end_action=self.__size_grip_end_action)

        self.__initialized = True
        return part_item

    @override_required
    def set_name(self, name: str):
        """Every derived class must override this to present the part name to the user"""
        raise NotImplementedError

    @override_optional
    def notify_proxied(self):
        """
        Derived class can override this if action is needed right after the widget has been put in a proxy
        """
        pass

    @override_optional
    def override_detail_level(self, detail_level_override: DetailLevelOverrideEnum):
        """
        Derived class can override this if it has a different representation based on DetailLevelOverrideEnum
        """
        pass

    @override_optional
    def set_sub_menu(self, actions: List[QAction]) -> List[QAction]:
        """
        Adds a sub-menu to the part context menu and sets the QActions within it.
        :param actions: a list of all QActions in this part.
        :return: an list of QActions with the ones added to the sub-menu removed. Default returns the original list.
        """
        return actions

    def size_from_scenario(self, width: float, height: float) -> QSize:
        """
        Should this become a member function of Size?
        :param size: a Size (of a FunctionPart)
        :return: a QSize in widget pixels.
        """
        return QSize(int(width * SCALE_FACTOR), int(height * SCALE_FACTOR))

    def size_to_scenario(self, size: QSize) -> Size:
        """
        Performs the reverse of size_from_scenario
        :param size: a QSize in pixels
        :return: a Size in scenario coordinates
        """
        ret = Size(0, 0)
        ret.width = size.width() / SCALE_FACTOR
        ret.height = size.height() / SCALE_FACTOR
        return ret

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def _dispose_widget(self, widget: QWidget):
        widget.setEnabled(False)
        widget.setVisible(False)
        widget.deleteLater()

    @override_optional
    def _disconnect_all_slots(self):
        # self.__part_item.geometryChanged.connect(self._parent_part_box_item.slot_on_size_changed)
        AlertIndicator._disconnect_all_slots(self)

    @override_optional
    def _on_widget_closed(self):
        """
        Derived class must override this if action is needed when the widget closes (such as close editor).
        """
        pass

    def _update_size_from_part(self):
        """Fetch the backend size and update our widget size."""

        # Usually we use the AsyncRequest to grab the back end data to update the front. But we access the back end
        # directly because it should be safe to access the size property. The direct access will avoid the size
        # induced flickering during the initial loading.
        # get_size() used to have an argument to specify the detail level. That has been removed to avoid
        # redundancy. The detail level view is determined at the front end.
        size = self._part.part_frame.get_size()
        self._set_size(size.width, size.height)

    @override_optional
    def _set_size(self, width: float, height: float):
        """Set size based on received values."""
        self._setup_qt_resizing()
        self._size_hint = self.size_from_scenario(width, height)
        self.setFixedSize(self.sizeHint())

    @override_optional
    def _setup_qt_resizing(self):
        """
        This is the technique to restore the layout mechanism after the setFixedWidth and
        the setFixedHeight are invoked.
        """
        self.setMaximumSize(QWIDGETSIZE_MAX, QWIDGETSIZE_MAX)
        self.setMinimumSize(0, 0)

    _slot_on_widget_closed = safe_slot(_on_widget_closed)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __sizing_action_ended(self):
        old_size = Size(self.__size_grip_end_action.data().width() / SCALE_FACTOR,
                        self.__size_grip_end_action.data().height() / SCALE_FACTOR)

        new_size = Size(self._parent_part_box_item.size.width() / SCALE_FACTOR,
                        self._parent_part_box_item.size.height() / SCALE_FACTOR)

        cmd = ResizeCommand(self._part.part_frame, old_size, new_size)
        scene_undo_stack().push(cmd)

    __slot_sizing_action_ended = safe_slot(__sizing_action_ended)


class FramedPartWidget(IPartWidget):
    """Abstract Base class for 2d PartWidgets with support for the detail level view."""

    # A number is used to calculate the center icon width when the part widget is at the minimal detail level.
    ICON_FRAME_WIDTH = 65


    CENTER_ICON_MARGIN_ADJUSTMENT = 5

    # The prototype shows only maximum 8 characters when the widget is at the minimal detail level.
    MAX_CHARS_AT_MINIMAL_DETAIL_LEVEL = 8

    NAME_FONT_POINT_SIZE_FULL = 18
    NAME_FONT_POINT_SIZE_MINIMAL = 12

    # Widget positions in the header frame
    INDEX_SMALL_ICON = 0
    INDEX_PART_NAME = 1
    # 2 is reserved for the spacer.
    INDEX_CUSTOM_BUTTON = 3  # <- use this index to insert a part-specific button

    RUN_BUTTON_POSITION_OFFSET = 1

    # noinspection PyUnresolvedReferences
    def __init__(self, part: BasePart, parent_part_box_item: Decl.PartBoxItem = None):
        """
        :param part the BasePart we are creating a widget for
        :param parent_part_box_item: the parent PartBoxItem that will contain a proxied wrapper of this widget
        """
        super().__init__(part, parent_part_box_item)
        self._detail_level = DetailLevelEnum.full
        self.__type_to_obj = {}
        # The default empty label just works perfectly as a spacer. The actual QSpacerItem is not easy to use and has
        # no advantage over the QLabel in this context.
        self.__header_frame_spacer = QLabel("")

        self.ui = Ui_FramedPartWidget()
        self.ui.setupUi(self)
        self._parent_part_box_item = parent_part_box_item

        part_type = part.PART_TYPE_NAME
        color = PART_ICON_COLORS[part_type]
        self.color = color
        icon_path = part_image(part_type)
        assert icon_path.exists()
        self.__detail_level_change_button = DetailLevelChangeButton(parent=self)
        self.__detail_level_override = DetailLevelOverrideEnum.none

        self._small_icon = QSvgWidget(str(icon_path))
        self._small_icon.setFixedSize(int(SMALL_ICON_SIZE_WIDTH),
                                      int(SMALL_ICON_SIZE_HEIGHT))
        self.__detail_level_change_button.clicked.connect(self.__slot_on_detail_level_change_button_clicked)

        self._content_widget = None
        self._bottom_layout = self.ui.bottom_widget.layout()

        self._palette = QPalette()
        self._palette.setColor(QPalette.Window, color)
        self._palette.setColor(QPalette.Text, Qt.white)
        self._palette.setColor(QPalette.WindowText, Qt.white)
        self.ui.part_name_label.setStyleSheet("QLabel {color: white; font: bold; padding-right: 1px};")
        self._white_palette = QPalette()
        self._white_palette.setColor(QPalette.Window, Qt.white)

        self.ui.header_frame.setAutoFillBackground(True)
        self.ui.header_frame.setPalette(self._palette)

        self.__type_to_obj[FramedPartHeaderObjTypeEnum.small_icon] = self._small_icon
        self.__type_to_obj[FramedPartHeaderObjTypeEnum.part_name] = self.ui.part_name_label
        self.__type_to_obj[FramedPartHeaderObjTypeEnum.spacer] = self.__header_frame_spacer
        self.__type_to_obj[FramedPartHeaderObjTypeEnum.detail_level_change] = self.__detail_level_change_button

        self.__minimized_detail_size = part.part_frame.DETAIL_LEVEL_MINIMIZED_LEN * SCALE_FACTOR
        minimized_detail_size_width = self.__minimized_detail_size - FramedPartWidget.ICON_FRAME_WIDTH
        center_icon = QSvgWidget(str(icon_path))
        center_icon.setFixedSize(int(minimized_detail_size_width), int(minimized_detail_size_width))

        self._icon_label = QWidget()
        # The force_to_center_layout is a technique used to make a widget go to the center of a stacked widget.
        force_to_center_layout = QHBoxLayout(self._icon_label)
        force_to_center_layout.setContentsMargins(0, 0, 0, FramedPartWidget.CENTER_ICON_MARGIN_ADJUSTMENT)
        force_to_center_layout.addWidget(center_icon, Qt.AlignCenter)

        self.ui.stacked_widget.addWidget(self._icon_label)
        self._size_hint = QSize(0, 0)
        self._update_size_from_part()

        # Context menu
        part.part_frame.signals.sig_part_frame_size_changed.connect(self._slot_set_size)
        part.part_frame.signals.sig_detail_level_changed.connect(self.__slot_on_detail_level_changed)
        part.part_frame.signals.sig_name_changed.connect(self.slot_set_name)

        # "Dirty" detection
        part.base_part_signals.sig_unapplied_edits_changed.connect(self.__slot_on_unapplied_edits_changed)
        self.__is_dirty = False
        self.__displayed_part_name = None

        if self._parent_part_box_item is not None:
            self._parent_part_box_item.toggle_icon_action.triggered.connect(self.__detail_level_change_button.click)

        if parent_part_box_item is not None:
            parent_part_box_item.left_side_tray_item.setY(self.ui.header_frame.height())
            parent_part_box_item.right_side_tray_item.setY(self.ui.header_frame.height())

            # Attempt to place the link creation item co-centered with the header frame in terms of y
            parent_part_box_item.link_creation_action_item.setY((self.ui.header_frame.height() -
                                                                 LINK_CREATION_ACTION_ITEM_HEIGHT) / 2)
            parent_part_box_item.set_header_frame_height(self.ui.header_frame.height())

    @override(IPartWidget)
    def override_detail_level(self, detail_level_override: DetailLevelOverrideEnum):
        """
        Overrides the view preferences of the back end. See the declaration of DetailLevelOverrideEnum for details.

        :param detail_level_override: The detail level view the front end prefers.
        """
        assert detail_level_override in DetailLevelOverrideEnum

        self.__detail_level_override = detail_level_override
        self.__detail_level_change_button.setEnabled(True)
        self.__detail_level_change_button.setVisible(True)
        self.__detail_level_change_button.override_tooltip()

        if detail_level_override == DetailLevelOverrideEnum.full:
            self.__detail_level_change_button.setEnabled(False)
            self.__detail_level_change_button.setVisible(False)
        elif detail_level_override == DetailLevelOverrideEnum.minimal:
            self.__detail_level_change_button.setEnabled(False)
            self.__detail_level_change_button.setVisible(False)

        self._update_detail_level_view()

    @override(IPartWidget)
    def set_name(self, name: str):
        self.setObjectName(name)
        self.setWindowTitle(name)

        if self._detail_level_in_effect() == DetailLevelEnum.minimal:
            self.ui.part_name_label.setFont(get_scenario_font(point_size=self.NAME_FONT_POINT_SIZE_MINIMAL))
            self.__displayed_part_name = name[:FramedPartWidget.MAX_CHARS_AT_MINIMAL_DETAIL_LEVEL]
        else:
            self.ui.part_name_label.setFont(get_scenario_font(point_size=self.NAME_FONT_POINT_SIZE_FULL))
            self.setFixedSize(self._size_hint)
            self.__displayed_part_name = name

        self.ui.part_name_label.setText(self.__get_name_prefix() + self.__displayed_part_name)

        if self._parent_part_box_item is not None:
            self._parent_part_box_item.on_size_changed()
            self._parent_part_box_item.scene().sig_update_context_help.emit(self._part)

    @override(QWidget)
    def sizeHint(self) -> QSize:
        return self._size_hint

    def get_part(self) -> BasePart:
        """ Method to get the instance of the part that is in this framed widget.
        :return: An instance of the part.
        """
        return self._part

    part = property(get_part)

    slot_set_name = safe_slot(set_name)

    @override(IPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        try_disconnect(self.__detail_level_change_button.clicked, self.__slot_on_detail_level_change_button_clicked)
        frame_signals = self._part.part_frame.signals
        try_disconnect(frame_signals.sig_part_frame_size_changed, self._slot_set_size)
        try_disconnect(frame_signals.sig_detail_level_changed, self.__slot_on_detail_level_changed)
        try_disconnect(frame_signals.sig_name_changed, self.slot_set_name)
        try_disconnect(self._parent_part_box_item.toggle_icon_action.triggered, self.__detail_level_change_button.click)

    def _add_header_frame_obj(self, obj_type: FramedPartHeaderObjTypeEnum, obj: QWidget):
        """
        The objects will be displayed with the same order as they are added.
        :param obj_type: The type of the object.
        :param obj: The object to be added.
        """
        if obj_type in self.__type_to_obj:
            log.warning("Type {} has already been added to the top side tray.", obj_type)
            return

        self.__type_to_obj[obj_type] = obj

    @override_optional
    def _update_detail_level_view(self):
        """
        Updates the GUI according to the detail level state
        """
        for x in self.__type_to_obj:
            self.ui.header_frame.layout().insertWidget(x.value, self.__type_to_obj[x.value])

        detail_level_in_effect = self._detail_level_in_effect()
        if detail_level_in_effect == DetailLevelEnum.minimal:
            self.ui.part_name_label.setFont(get_scenario_font(point_size=self.NAME_FONT_POINT_SIZE_MINIMAL))
            # These two lines are used to force this widget to have the correct size. The layout mechanism must be
            # restored when it at the full detail level. Incidentally, the setFixedSize cannot achieve the same effect,
            # contrary to what the documentation suggests.
            self.setFixedWidth(int(self.__minimized_detail_size))
            self.setFixedHeight(int(self.__minimized_detail_size))

            if not self.__detail_level_change_button.is_minimized:
                self.__detail_level_change_button.toggle_detail_level()

            self.__displayed_part_name = self._part.name[:FramedPartWidget.MAX_CHARS_AT_MINIMAL_DETAIL_LEVEL]
            self.setPalette(self._palette)
            self.ui.stacked_widget.setCurrentWidget(self._icon_label)
            self._bottom_layout.insertWidget(FramedPartWidget.INDEX_PART_NAME, self.ui.part_name_label)
        else:
            self.ui.part_name_label.setFont(get_scenario_font(point_size=self.NAME_FONT_POINT_SIZE_FULL))
            self._setup_qt_resizing()

            if self.__detail_level_change_button.is_minimized:
                self.__detail_level_change_button.toggle_detail_level()

            # Reset the widget size to its backend size
            self._update_size_from_part()

            self.__displayed_part_name = self._part.name
            self.setPalette(self._white_palette)
            if self._content_widget is not None:
                self.ui.stacked_widget.setCurrentWidget(self._content_widget)

        self.ui.part_name_label.setText(self.__get_name_prefix() + self.__displayed_part_name)

        self.ui.bottom_widget.setVisible(detail_level_in_effect == DetailLevelEnum.minimal)
        self._small_icon.setHidden(detail_level_in_effect == DetailLevelEnum.minimal)

        # Update the parent part box
        self._parent_part_box_item.on_detail_level_changed(detail_level_in_effect, self.__detail_level_override)

    def _set_content_widget(self, widget: QWidget):
        """
        :param widget: The widget that is shown when self is at the full detail level
        """
        if self._content_widget is not None:
            self._dispose_widget(self._content_widget)
        self._content_widget = widget
        self.ui.stacked_widget.insertWidget(0, self._content_widget)

        self.__set_detail_level(self._part.part_frame.detail_level)
        if self._part.part_frame.detail_level == self._detail_level:
            self._update_detail_level_view()

    def _detail_level_in_effect(self):
        """
        The detail level evaluation based on the actual detail and the current overridden status. If the
        overriding is in effect, its detail level will be returned instead of the actual detail level.
        :return: The detail level after taking the overridden status into consideration
        """
        assert self.__detail_level_override in DetailLevelOverrideEnum

        if self.__detail_level_override == DetailLevelOverrideEnum.full:
            return DetailLevelEnum.full
        elif self.__detail_level_override == DetailLevelOverrideEnum.minimal:
            return DetailLevelEnum.minimal
        else:
            return self._detail_level

    @override(IPartWidget)
    def _set_size(self, width: float, height: float):
        """
        Overrides the super class in order to maintain the size if a widget is in at the minimal detail level.
        :param width: The width to be displayed if the widget is at the full detail level.
        :param height: The height to be displayed if the widget is at the full detail level.
        """
        if self._detail_level_in_effect() == DetailLevelEnum.minimal:
            return

        super(FramedPartWidget, self)._set_size(width, height)

    _slot_set_size = safe_slot(_set_size)

    def __set_detail_level(self, detail_level: DetailLevelEnum):
        """
        Changes the detail level state if it does not match the current state. If the state is changed, the GUI will be
        updated.
        :param detail_level: The new detail level.
        """
        if self._detail_level != detail_level:
            self._detail_level = detail_level
            self._update_detail_level_view()

    def __on_detail_level_changed(self, detail_level: DetailLevelEnum):
        """
        Slot called when backend detail_level property changes. The front end detail level view preferences may
        override the detail level from the back end. See the DetailLevelOverrideEnum for details.
        :param detail_level: The detail level from the back end.
        """
        if self.__detail_level_override == DetailLevelOverrideEnum.full \
                or self.__detail_level_override == DetailLevelOverrideEnum.minimal:
            return

        self.__set_detail_level(detail_level)

    def __on_comment_bubble_button_clicked(self):
        """ Toggles the visibility of the comment on the part that the button belongs to. """
        self._parent_part_box_item.toggle_comment_bubble()

    def __on_detail_level_change_button_clicked(self):
        """
        Slot called when user clicks the detail level change button from GUI. Sets value on the backend if the current
        detail level view is "none"
        """
        if self.__detail_level_override == DetailLevelOverrideEnum.full \
                or self.__detail_level_override == DetailLevelOverrideEnum.minimal:
            # The button is disabled. The code should not reach here. Checking it anyway just for precaution.
            return

        if self._detail_level == DetailLevelEnum.full:
            detail_level = DetailLevelEnum.minimal
        else:
            detail_level = DetailLevelEnum.full

        scene_undo_stack().push(ChangeDetailLevelCommand(self._part.part_frame, detail_level))

    def __get_name_prefix(self) -> str:
        """
        Convenience method to format a dirty name prefix
        :return: The dirty prefix
        """
        return "* " if self.__is_dirty else ""

    def __on_unapplied_edits_changed(self, dirty: bool):
        """
        Prefixes a "*" at front of the displayed part name.
        :param dirty: True - the part is dirty.
        """
        self.__is_dirty = dirty
        self.ui.part_name_label.setText(self.__get_name_prefix() + self.__displayed_part_name)

    __slot_on_detail_level_changed = safe_slot(__on_detail_level_changed)
    __slot_on_comment_bubble_button_clicked = safe_slot(__on_comment_bubble_button_clicked)
    __slot_on_detail_level_change_button_clicked = safe_slot(__on_detail_level_change_button_clicked)
    __slot_on_unapplied_edits_changed = safe_slot(__on_unapplied_edits_changed)


class FramelessPartWidget(IPartWidget):
    """  Abstract Base class for 2d PartWidgets without a frame.    """

    # sig_mouse_press_event = pyqtSignal(QMouseEvent)

    # noinspection PyUnresolvedReferences
    def __init__(self, part: BasePart, parent_part_box_item: Decl.PartBoxItem = None):
        """
        :param part the BasePart we are creating a widget for
        :param parent: the parent widget
        """
        super().__init__(part, parent_part_box_item)

        self.ui = Ui_FramelessPartWidget()
        self.ui.setupUi(self)
        self._parent_part_box_item = parent_part_box_item

        self._content_widget = None
        self._size_hint = QSize(20, 20)

        part.part_frame.signals.sig_part_frame_size_changed.connect(self._slot_set_size)

    @override(IPartWidget)
    def set_name(self, name: str):
        self.setObjectName(name)

    @override(QWidget)
    def sizeHint(self) -> QSize:
        return self._size_hint

    @override(IPartWidget)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()
        try_disconnect(self._part.part_frame.signals.sig_part_frame_size_changed, self._slot_set_size)

    @override(IPartWidget)
    def _set_size(self, width: float, height: float):
        """Override to create slot."""
        super()._set_size(width, height)

    def _set_content_widget(self, widget: QWidget):
        """
        :param widget: The widget that is shown when self is at the full detail level
        """
        if self._content_widget is not None:
            self._dispose_widget(self._content_widget)
        self._content_widget = widget
        self.ui.verticalLayout.addWidget(self._content_widget)

    _slot_set_size = safe_slot(_set_size)


class IExecPartWidget:
    """
    If a part is callable, its widget must derive from this class.
    """

    def _initialize_run(self, allow_debug: bool = True):
        """
        The derived class should call this function once. It builds the infrastructure for the part to run, e.g.,
        the run button, actions, signals, etc.
        :param allow_debug: True - if the part needs debugging,
        """
        self.__param_dialog = None
        self.__allow_debug = allow_debug
        self.__run_action = create_action(self, 'Run', tooltip="Run (execute) this part")
        self.__run_action.triggered.connect(self.__slot_on_run)
        run_button = SvgToolButton(get_icon_path("shortcut_run.svg"), parent=self)
        run_button.setDefaultAction(self.__run_action)
        run_button.setText(None)  # Must manually remove since setDefaultAction changes text property
        self._add_header_frame_obj(FramedPartHeaderObjTypeEnum.run_button, run_button)

        if allow_debug:
            self.__run_debug_action = create_action(self, "Run Debug", tooltip="Run (execute) this part in debug mode")
            self.__run_debug_action.triggered.connect(self.__slot_on_run_debug)

    def _complete_execution(self, part_call: callable, sig_getter: callable, debug: bool = False,
                            func_name: str = None):
        def on_run_error(err_info: AsyncErrorInfo):
            get_progress_bar().stop_progress()
            self.show_alerts_message()

        def on_run_done():
            get_progress_bar().stop_progress()
            if self.__param_dialog is None:
                return

            exec_modal_dialog('Success', 'The part "{}" has been run successfully.'.format(str(self._part)),
                              QMessageBox.Information)
            self.__param_dialog.done(QDialog.Accepted)

        def on_input_ready(call_args_dict: CallArgs):
            """
            This is a call-back function for the ParameterInputDialog.
            
            After the user clicks OK button, this function sends the collected information from the dialog to
            the backend to run the part. 
    
            If the execution has errors, the ParameterInputDialog will stay open until the user cancels it or re-runs
            succeed eventually.
            :param call_args_dict: The user input on the dialog
            """
            call_spec = (part_call,)
            prog_msg = 'Running ' + str(self._part)
            if func_name is not None:
                call_spec += (func_name,)
                prog_msg = 'Running {}() from {}'.format(func_name, self._part)

            run_args, run_kwargs = call_args_dict
            call_spec += run_args

            # any errors can be ignored because the __on_alert_status_changed will be called instead
            get_progress_bar().start_busy_progress(prog_msg)
            AsyncRequest.call(*call_spec,
                              _debug_mode=debug,
                              response_cb=on_run_done,
                              error_cb=on_run_error,
                              **run_kwargs)

        def on_signature(inspected_signature):
            call_spec = (part_call,)
            prog_msg = 'Running ' + str(self._part)
            if func_name is not None:
                call_spec += (func_name,)
                prog_msg = 'Running {}() from {}'.format(func_name, self._part)

            if not inspected_signature.parameters:
                # any errors can be ignored because the __on_alert_status_changed will be called instead
                get_progress_bar().start_busy_progress(prog_msg)
                AsyncRequest.call(*call_spec,
                                  _debug_mode=debug,
                                  response_cb=on_run_done,
                                  error_cb=on_run_error)
            else:
                self.__param_dialog = ParameterInputDialog(param_signature=inspected_signature,
                                                           data_ready=on_input_ready)
                self.__param_dialog.exec()

        def on_signature_error(_: AsyncErrorInfo):
            self.show_alerts_message()

        sig_spec = (sig_getter,)
        if func_name is not None:
            sig_spec += (func_name,)

        AsyncRequest.call(*sig_spec, response_cb=on_signature, error_cb=on_signature_error)

    @override_required
    def _run_part(self):
        """
        The derived class must implement this function.
        """
        raise NotImplementedError("How to run this part must be implemented")

    @override_optional
    def _debug_part(self):
        """
        If the derived class initializes the part with debug option, i.e.,  _initialize_run(True),
        it should implement this function.
        """
        pass

    def _disconnect_all_slots(self):
        try_disconnect(self.__run_action.triggered, self.__slot_on_run)

        if self.__allow_debug:
            try_disconnect(self.__run_debug_action.triggered, self.__slot_on_run_debug)

    def __on_run(self):
        """
        Used to satisfy the safe_slot pattern to forward the call to the derived class.
        """
        self._run_part()

    def __on_debug(self):
        """
        Used to satisfy the safe_slot pattern to forward the call to the derived class.
        """
        self._debug_part()

    __slot_on_run = safe_slot(__on_run)
    __slot_on_run_debug = safe_slot(__on_debug)
