# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Trays and the ifx bar for the part box graphics item.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum, unique

# [2. third-party]
from PyQt5.QtCore import Qt, QRectF, QPointF, QVariant
from PyQt5.QtGui import QColor, QBrush, QPen, QPalette, QFont, QPolygonF, QCursor, QPainter, QPainterPath
from PyQt5.QtWidgets import QGraphicsTextItem, QLabel, QGraphicsItem, QGraphicsObject, QGraphicsRectItem
from PyQt5.QtWidgets import QGraphicsSceneMouseEvent, QAction, QGraphicsPolygonItem
from PyQt5.QtWidgets import QGraphicsWidget, QGraphicsProxyWidget, QGraphicsSceneContextMenuEvent, QMenu
from PyQt5.QtSvg import QGraphicsSvgItem

# [3. local]
from origame.gui.actor_2d_view.part_box_side_item_base import BottomSideTrayItemTypeEnum, BaseSideTrayItem
from ...core import override, override_required
from ...core.typing import Either
from ...core.typing import Tuple
from ...core.typing import AnnotationDeclarations
from ...scenario.defn_parts import PartFrame, PartLink, BasePart, DetailLevelEnum
from ..part_editors import get_part_editor_class
from ..undo_manager import SwitchIfxPortSideCommand, ChangeIfxLevelCommand, VerticalMoveIfxCommand, scene_undo_stack
from ..actions_utils import verify_ifx_level_change_ok, get_labels_ifx_levels, get_labels_ifx_ports
from ..gui_utils import ITEM_SPACE, get_icon_path, part_image, OBJECT_NAME
from ..gui_utils import IFX_TEXT_COLOR, PART_ITEM_BORDER_WIDTH, HIGHLIGHTED_BORDER_COLOR, IFX_BAR_TEXT_SIZE
from ..gui_utils import IFX_BACKGROUND_COLOR, IFX_TEXT_SIZE
from ..gui_utils import EVENT_COUNTER_RECT_HEIGHT, EVENT_COUNTER_ARROW_WIDTH, MARGIN_OF_SELECTED_PART
from ..gui_utils import LINK_CREATION_ACTION_ITEM_WIDTH, LINK_CREATION_ACTION_ITEM_HEIGHT, HORIZONTAL_ELLIPSIS
from ..gui_utils import LINK_CREATION_SHORTCUT_SPACE, get_scenario_font, get_ifx_port_name_width
from ..safe_slot import safe_slot, ext_safe_slot
from ..actions_utils import create_action
from ..async_methods import AsyncRequest
from .part_box_side_item_base import TopSideTrayItemTypeEnum
from .common import ZLevelsEnum, CustomItemEnum, IInteractiveItem, ICustomItem, EventStr
from .custom_items import SvgFromImageItem
from .indicators import CommentBoxItem
from .linking import LinkAnchorItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'IfxBarTrayItem',
    'LinkCreationActionItem',
    'TopSideTrayItem',
    'BottomSideTrayItem',
    'LeftSideTrayItem',
    'RightSideTrayItem',
    'PartProximityBorderItem',
    'PartSelectionBorderItem',
    'IfxPortItem',
    'EventCounterItem'
]

log = logging.getLogger('system')

PORT_BORDER_ALIGNMENT = 1
IFX_BAR_BACKGROUND_COLOR = QColor(225, 175, 0, 175)    #233, 156, 0
IFX_INDICATOR_HEIGHT = 4
VERTICAL_TRAY_SCALE_ADJUSTMENT = 0.98  # Shrink a little further to produce a padding around it.
IFX_PORT_HIGHLIGHT_MARGIN = 4


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------


class Decl(AnnotationDeclarations):
    PartBoxItem = 'PartBoxItem'
    IfxPortItem = 'IfxPortItem'


@unique
class IfxVerticalMoveDirectionEnum(IntEnum):
    """
    This class represents the direction to move an ifx port.
    """
    down, up = range(2)


class HorizontalSideTrayItem(BaseSideTrayItem):
    """
    Common features for the top and bottom side items.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: QGraphicsItem = None):
        super().__init__(part_box_item, parent)
        self.__type_to_obj = {}

    def add_obj(self, tray_item_type_enum: Either[TopSideTrayItemTypeEnum, BottomSideTrayItemTypeEnum],
                obj: QGraphicsItem):
        """
        If the derived class is TopSideTrayItem, use the TopSideTrayItemTypeEnum to add the obj; otherwise
        the BottomSideTrayItemTypeEnum.
        :param tray_item_type_enum: The type of the object.
        :param obj: The object to be added.
        """
        if tray_item_type_enum in self.__type_to_obj:
            log.warning("Type {} has already been added to the top side tray.", tray_item_type_enum)
            return

        self.__type_to_obj[tray_item_type_enum] = obj
        obj.setParentItem(self)

    def get_obj(self,
                tray_item_type_enum: Either[TopSideTrayItemTypeEnum, BottomSideTrayItemTypeEnum]) -> QGraphicsItem:
        """
        Gets the object by the type. The object must be added earlier by the add_obj()
        :param tray_item_type_enum:
        :return: The object added earlier
        """
        return self.__type_to_obj[tray_item_type_enum]

    @override(BaseSideTrayItem)
    def update_item(self):
        """
        Puts the added objects in right places.
        """
        pos_x = 0
        order = sorted(self.__type_to_obj)
        for tray_item_type_enum in order:
            child = self.__type_to_obj[tray_item_type_enum]
            child.setX(pos_x)
            if child.isVisible():
                pos_x += child.boundingRect().width() + ITEM_SPACE


class VerticalSideTrayItem(BaseSideTrayItem):
    """
    Common features for the left and right side items.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: QGraphicsItem = None):
        super().__init__(part_box_item, parent)
        self.__ifx_port_items_seq = list()

    def add_ifx_port(self,
                     port: PartFrame,
                     part_name: str,
                     part_type_str: str,
                     ifx_level: int,
                     detail_level: DetailLevelEnum,
                     ifx_port_index: int):
        """
        Create a new IfxPortItem for the given ifx part.

        Note: The reason why we keep a long list of params is that the initial async call gets everything needed
        for the ifx port. So, we can save an additional async call here.

        :param port: The part frame used to construct the ifx port.
        :param part_name: The part name from the backend part.
        :param part_type_str: The part type string from the backend.
        :param ifx_level: The current level
        :param detail_level: The initial detail level
        :param ifx_port_index: it specifies the order of this ifx port in its bin.
        """
        self.prepareGeometryChange()
        port_item = IfxPortItem(port, part_name, part_type_str, ifx_level,
                                detail_level, self._get_is_left_side(), self, self._part_box_item)
        self.__ifx_port_items_seq.insert(ifx_port_index, port_item)
        self.scene().on_ifx_port_added(port_item)
        self.__update_enabled_port_options()

    def remove_ifx_port(self, port: PartFrame):
        """
        Removes the port item from this tray and discards it.
        :param port: The part frame for the ifx port to be removed.
        """
        self.prepareGeometryChange()
        for ifx_port_item in self.__ifx_port_items_seq:
            if ifx_port_item.part_frame is port:
                self.__ifx_port_items_seq.remove(ifx_port_item)
                ifx_port_item.dispose()
                break

    def pop_ifx_port_item(self, port: PartFrame) -> Decl.IfxPortItem:
        """
        Removes the port item from this tray for insertion (via insert_ifx_port_item()) into another tray.
        Do NOT use this method to dispose of the port item permanently: use scene.dispose_item(port) instead!
        :param port: The part frame for the ifx port to be removed.
        :return: the IfxPortItem removed from this tray
        """
        self.prepareGeometryChange()
        for i, ifx_port_item in enumerate(self.__ifx_port_items_seq):
            if ifx_port_item.part_frame is port:
                port_item = self.__ifx_port_items_seq.pop(i)
                self.__update_enabled_port_options()
                return port_item

        return None

    def insert_ifx_port_item(self, index: int, ifx_port_item: Decl.IfxPortItem):
        """
        Insert given IfxPortItem at given index. This item MUST have been removed from another tray via
        pop_ifx_port_item().
        """
        self.prepareGeometryChange()
        self.__ifx_port_items_seq.insert(index, ifx_port_item)
        ifx_port_item.setParentItem(self)
        ifx_port_item.set_left_side(self._get_is_left_side())
        self.__update_enabled_port_options()

    def update_ifx_port_vertical_indices(self, from_idx: int, to_idx: int):
        """
        Refreshes the ports by moving the port at from_idx to the new position at to_idx.
        :param from_idx: The original index of the port.
        :param to_idx: The new index of the port.
        """
        self.__ifx_port_items_seq.insert(to_idx, self.__ifx_port_items_seq.pop(from_idx))
        self.__update_enabled_port_options()

    @override(BaseSideTrayItem)
    def update_item(self):
        if len(self.__ifx_port_items_seq) == 0:
            return

        self.prepareGeometryChange()
        pos_y = IFX_INDICATOR_HEIGHT + ITEM_SPACE * 2 + IFX_PORT_HIGHLIGHT_MARGIN * 2
        for child in self.__ifx_port_items_seq:
            if self._get_is_left_side():
                child.setX(-IfxPortItem.PART_TYPE_ICON_WIDTH)
            else:
                child.setX(-get_ifx_port_name_width())
            child.setY(pos_y)
            pos_y += child.boundingRect().height() + ITEM_SPACE * 2

        demand = self.childrenBoundingRect().height()
        supply = self._part_box_item.size.height() - self.y()
        demand_over_supply = demand - supply
        if demand_over_supply > 0:
            # Scale to fit
            self.setScale((supply / demand) * VERTICAL_TRAY_SCALE_ADJUSTMENT)
        else:
            self.setScale(1.0)

    def on_detail_level_changed(self, detail_level: DetailLevelEnum):
        """
        Updates the ports when the detail level is changed.
        :param detail_level: The detail level.
        """
        for ifx_port_item in self.__ifx_port_items_seq:
            ifx_port_item.on_detail_level_changed(detail_level)

    def get_num_ifx_ports(self):
        return len(self.__ifx_port_items_seq)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    num_ifx_ports = property(get_num_ifx_ports)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    @override_required
    def _get_is_left_side(self) -> bool:
        """
        The derived class must declare on which side of its parent it is located.
        :return: True - the left side.
        """
        raise NotImplementedError

    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __update_enabled_port_options(self):
        """
        Enable or disable port item context menu options.
        Use this method to reset port item options when a port item has changed position.
        """
        for idx, port_item in enumerate(self.__ifx_port_items_seq):
            # Enable moving up and down for all ports
            port_item.enable_move_up()
            port_item.enable_move_down()

            if idx == 0:
                # Disable 'up' moves for the top port
                port_item.enable_move_up(False)

            if port_item is self.__ifx_port_items_seq[-1]:
                # Disable 'down' moves for the bottom port
                port_item.enable_move_down(False)


class TopSideTrayItem(HorizontalSideTrayItem):
    """
    Manages the comment bubble, function role, and breakpoint marker
    """

    # --------------------------- class-wide data and signals -----------------------------------

    TOP_SIDE_TRAY_HEIGHT = 30

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: HorizontalSideTrayItem = None):
        super().__init__(part_box_item, parent)
        comment_toggle_item = SvgFromImageItem(str(get_icon_path("marker_comment.svg")))
        comment_toggle_item.setVisible(False)
        self.add_obj(TopSideTrayItemTypeEnum.comment_bubble, comment_toggle_item)
        comment_toggle_item.sig_mouse_pressed.connect(self.__slot_on_comment_bubble_item_pressed)
        self.__comment_display_item = CommentBoxItem(part_box_item, parent=comment_toggle_item)
        self.__comment_display_item.setX(comment_toggle_item.boundingRect().width())
        self.__comment_visibility_action = create_action(
            self, "Comment", "Toggle comment visibility (if comment not empty)")
        self.__comment_visibility_action.triggered.connect(self.__slot_on_toggle_comment_visibility)

    @override(HorizontalSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.top_side_tray.value

    def get_comment_visibility_action(self):
        comment = self.__comment_display_item.widget().ui.comment_text.toPlainText().strip()
        self.__comment_visibility_action.setEnabled(bool(comment))
        return self.__comment_visibility_action

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    comment_visibility_action = property(get_comment_visibility_action)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_comment_bubble_item_pressed(self):
        self.__comment_visibility_action.triggered.emit()

    def __on_toggle_comment_visibility(self, checked: bool):
        self.__comment_display_item.setVisible(not self.__comment_display_item.isVisible())

    __slot_on_comment_bubble_item_pressed = safe_slot(__on_comment_bubble_item_pressed)
    __slot_on_toggle_comment_visibility = safe_slot(__on_toggle_comment_visibility)


class BottomSideTrayItem(HorizontalSideTrayItem):
    """
    Manages the execution warning indicator and missing links indicator.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    BOTTOM_SIDE_TRAY_HEIGHT = 24

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: HorizontalSideTrayItem = None):
        super().__init__(part_box_item, parent)

    @override(HorizontalSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.bottom_side_tray.value


class LeftSideTrayItem(VerticalSideTrayItem):
    """
    Manages the child actor interface ports
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: VerticalSideTrayItem = None):
        super().__init__(part_box_item, parent)

    @override(VerticalSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.left_side_tray.value

    @override(VerticalSideTrayItem)
    def _get_is_left_side(self):
        return True


class RightSideTrayItem(VerticalSideTrayItem):
    """
    Manages the child actor interface ports
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: VerticalSideTrayItem = None):
        super().__init__(part_box_item, parent)

    @override(VerticalSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.right_side_tray.value

    @override(VerticalSideTrayItem)
    def _get_is_left_side(self):
        return False


class IfxBarTrayItem(BaseSideTrayItem):
    """
    Manages the items of the interface.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # Usually, the width follows the part width, but we have to enforce a min size when the part is too small.
    IFX_BAR_WIDTH_MIN = 125
    IFX_BAR_HEIGHT = 16
    ITEM_PAIR_SPACE = 0  # It may need space in the future.
    ITEM_INIT_MARGIN = 2
    # It seems hard to align a QGraphicsTextItem with a neighbouring SVG graphics item automatically by Qt.
    # So, the simplest way to do it by hand is to use an offset to adjust it.
    TEXT_Y_OFFSET = 6

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: QGraphicsItem = None):
        super().__init__(part_box_item, parent)
        self.__background = QGraphicsRectItem(self)

        self.__icon_ifx_level = QGraphicsSvgItem(str(get_icon_path("ifx_level.svg")), self)
        self.__level_value_item = QGraphicsTextItem("  ", self)
        self.__level_value_item.setDefaultTextColor(IFX_TEXT_COLOR)
        self.__level_value_item.setFont(get_scenario_font(point_size=IFX_BAR_TEXT_SIZE))

        self.__icon_incoming_elevated_links = QGraphicsSvgItem(
            str(get_icon_path("incoming_elevated_links.svg")), self)
        self.__num_incoming_elevated_links_item = QGraphicsTextItem("  ", self)
        self.__num_incoming_elevated_links_item.setDefaultTextColor(IFX_TEXT_COLOR)
        self.__num_incoming_elevated_links_item.setFont(get_scenario_font(point_size=IFX_BAR_TEXT_SIZE))

        self.__icon_outgoing_elevated_links = QGraphicsSvgItem(
            str(get_icon_path("outgoing_elevated_links.svg")), self)
        self.__num_outgoing_elevated_links_item = QGraphicsTextItem("  ", self)
        self.__num_outgoing_elevated_links_item.setDefaultTextColor(IFX_TEXT_COLOR)
        self.__num_outgoing_elevated_links_item.setFont(get_scenario_font(point_size=IFX_BAR_TEXT_SIZE))

        part_box_item.part_frame.signals.sig_ifx_level_changed.connect(self.__slot_ifx_level_changed)
        part_box_item.part_frame.signals.sig_incoming_link_added.connect(self.__slot_incoming_link_added)
        part_box_item.part_frame.signals.sig_incoming_link_removed.connect(self.__slot_incoming_link_removed)
        part_box_item.part_frame.signals.sig_outgoing_link_added.connect(self.__slot_outgoing_link_added)
        part_box_item.part_frame.signals.sig_outgoing_link_removed.connect(self.__slot_outgoing_link_removed)

        def __get_ifx_state() -> Tuple[int, int, int]:
            part_frame = part_box_item.part_frame
            return (part_frame.ifx_level, part_frame.get_num_elev_links_incoming(),
                    part_frame.get_num_elev_links_outgoing())

        def __ifx_state_from_part(ifx_level: int, incoming: int, outgoing: int):
            self.__level_value_item.setPlainText(str(ifx_level))
            self.__num_incoming_elevated_links_item.setPlainText(str(incoming))
            self.__num_outgoing_elevated_links_item.setPlainText(str(outgoing))
            self.setVisible(ifx_level > 0)

            self.update_item()

        AsyncRequest.call(__get_ifx_state, response_cb=__ifx_state_from_part)

    @override(BaseSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.ifx_bar.value

    @override(BaseSideTrayItem)
    def update_item(self):
        parent_width = self._part_box_item.size.width()
        adjusted_width = max(parent_width, self.IFX_BAR_WIDTH_MIN)
        # Background
        d = PART_ITEM_BORDER_WIDTH
        self.__background.setRect(QRectF(-d/2, -d/2, adjusted_width + d, self.IFX_BAR_HEIGHT + d))
        self.__background.setBrush(QBrush(IFX_BAR_BACKGROUND_COLOR))
        self.__background.setPen(QPen(Qt.NoPen))
        #self.__background.setPen(QPen(QBrush(IFX_BAR_BACKGROUND_COLOR),
        #                              PART_ITEM_BORDER_WIDTH))

        

        # Centers the interface bar over frameless items
        x_offset_adjustment = 0
        if parent_width < self.IFX_BAR_WIDTH_MIN:
            x_offset_adjustment = -(self.IFX_BAR_WIDTH_MIN - parent_width) / 2

        self.__background.setX(x_offset_adjustment)

        # Set X-coordinate for ifx-level indicator - left-aligned
        x_offset = self.ITEM_INIT_MARGIN + x_offset_adjustment
        for val_pair in [(self.__icon_ifx_level, self.__level_value_item)]:

            for item in val_pair:
                item.setX(x_offset)  # Set item at current position
                x_offset += item.boundingRect().width()  # Set next position to be current + item width

            x_offset += self.ITEM_PAIR_SPACE

        # Set X-coordinate for incoming and outgoing elevated link indicators - right-aligned
        x_offset = adjusted_width - self.ITEM_INIT_MARGIN + x_offset_adjustment
        for val_pair in [(self.__num_outgoing_elevated_links_item, self.__icon_outgoing_elevated_links),
                         (self.__num_incoming_elevated_links_item, self.__icon_incoming_elevated_links)]:

            for item in val_pair:
                x_offset -= item.boundingRect().width()  # Set current position to be current - item width
                item.setX(x_offset)  # Set item at current position

            x_offset -= self.ITEM_PAIR_SPACE

        # Set Y-coordinate for all ifx bar items
        for item in [self.__level_value_item,
                     self.__num_incoming_elevated_links_item,
                     self.__num_outgoing_elevated_links_item]:
            item.setY(-self.TEXT_Y_OFFSET)

    def get_level_value_item(self):
        return self.__level_value_item

    def get_num_outgoing_elevated_links_item(self):
        return self.__num_outgoing_elevated_links_item

    def get_num_incoming_elevated_links_item(self):
        return self.__num_incoming_elevated_links_item

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    level_value_item = property(get_level_value_item)
    num_outgoing_elevated_links_item = property(get_num_outgoing_elevated_links_item)
    num_incoming_elevated_links_item = property(get_num_incoming_elevated_links_item)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __ifx_level_changed(self, ifx_level: int):
        """
        Controls the level info visibility on this bar.
        :param ifx_level: if it is greater than zero, displays the level level; otherwise hides it.
        """
        self.__level_value_item.setPlainText(str(ifx_level))
        self.setVisible(ifx_level > 0)

        self.update_item()

    def __incoming_link_added(self, _: PartLink):
        AsyncRequest.call(self._part_box_item.part_frame.get_num_elev_links_incoming,
                          response_cb=self.__update_ifx_incoming)

    def __incoming_link_removed(self, _1: int, _2: str):
        AsyncRequest.call(self._part_box_item.part_frame.get_num_elev_links_incoming,
                          response_cb=self.__update_ifx_incoming)

    def __outgoing_link_added(self, _: PartLink):
        AsyncRequest.call(self._part_box_item.part_frame.get_num_elev_links_outgoing,
                          response_cb=self.__update_ifx_outgoing)

    def __outgoing_link_removed(self, _1: int, _2: str):
        AsyncRequest.call(self._part_box_item.part_frame.get_num_elev_links_outgoing,
                          response_cb=self.__update_ifx_outgoing)

    def __update_ifx_incoming(self, num: int):
        self.__num_incoming_elevated_links_item.setPlainText(str(num))
        self.update_item()

    def __update_ifx_outgoing(self, num: int):
        self.__num_outgoing_elevated_links_item.setPlainText(str(num))
        self.update_item()

    __slot_ifx_level_changed = safe_slot(__ifx_level_changed)
    __slot_incoming_link_added = ext_safe_slot(__incoming_link_added)
    __slot_incoming_link_removed = safe_slot(__incoming_link_removed)
    __slot_outgoing_link_added = ext_safe_slot(__outgoing_link_added)
    __slot_outgoing_link_removed = safe_slot(__outgoing_link_removed)


class PartProximityBorderItem(ICustomItem, QGraphicsRectItem):
    """
    Manages the user activities when the mouse is close to the base item.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QGraphicsRectItem = None):
        ICustomItem.__init__(self)
        QGraphicsRectItem.__init__(self, parent)
        self.setZValue(ZLevelsEnum.proximity_boundary)
        self.setPen(QPen(Qt.NoPen))

    @override(QGraphicsRectItem)
    def type(self) -> int:
        return CustomItemEnum.proximity.value

    def activate(self):
        """
        Makes this item visible and emits sig_part_item_activated(True)
        """
        self.parentItem().change_proximity_state(True)

    def deactivate(self):
        """
        Makes this item invisible and emits sig_part_item_activated(False)
        """
        self.parentItem().change_proximity_state(False)


class PartSelectionBorderItem(ICustomItem, QGraphicsRectItem):
    """
    A color-edged rect item is to indicate a part is selected.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QGraphicsRectItem = None):
        ICustomItem.__init__(self)
        QGraphicsRectItem.__init__(self, parent)
        self.setPen(QPen(QBrush(HIGHLIGHTED_BORDER_COLOR), MARGIN_OF_SELECTED_PART))
        self.__detail_level = DetailLevelEnum.full

    @override(QGraphicsRectItem)
    def setRect(self, rect: QRectF):
        QGraphicsRectItem.setRect(self, rect)
        for child in self.childItems():
            if child.type() in [CustomItemEnum.size_grip_corner,
                                CustomItemEnum.size_grip_right,
                                CustomItemEnum.size_grip_bottom]:
                child.parent_rect_changed(rect)

    @override(QGraphicsRectItem)
    def setVisible(self, visible: bool):
        QGraphicsRectItem.setVisible(self, visible)
        self.__evaluate_size_grip_visibility()

    @override(QGraphicsRectItem)
    def type(self) -> int:
        return CustomItemEnum.selection_border.value

    def on_detail_level_changed(self, detail_level: DetailLevelEnum):
        """
        Updates the size grip items.
        :param detail_level: The detail level
        """
        self.__detail_level = detail_level
        self.__evaluate_size_grip_visibility()

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __evaluate_size_grip_visibility(self):
        for child in self.childItems():
            if child.type() in [CustomItemEnum.size_grip_corner,
                                CustomItemEnum.size_grip_right,
                                CustomItemEnum.size_grip_bottom]:
                child.setVisible(self.isVisible() and self.__detail_level == DetailLevelEnum.full)


class LinkCreationActionItem(BaseSideTrayItem):
    """
    Manages the shortcut item to create a link.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    LINK_CREATION_ACTION_ITEM_COLOR = QColor(70, 70, 70)
    LINK_CREATION_SHORTCUT = get_icon_path("link_creation_shortcut.svg")

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, action: QAction, parent: QGraphicsItem = None,
                 scale: float = None):
        super().__init__(part_box_item, parent)
        self.setData(OBJECT_NAME, "link_short_cut")
        self.__image = QGraphicsSvgItem(self.LINK_CREATION_SHORTCUT, self)
        if scale is not None:
            self.__image.setScale(scale)
        self.setVisible(False)
        self.__action = action
        self.resize(int(LINK_CREATION_ACTION_ITEM_WIDTH), int(LINK_CREATION_ACTION_ITEM_HEIGHT))

    @override(BaseSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.link_creation.value

    @override(BaseSideTrayItem)
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        log.debug("Link creation shortcut item got mouse press: {}", EventStr(event))
        if event.button() == Qt.LeftButton and self.__action is not None:
            # event.accept()
            self.__action.triggered.emit()

        super().mousePressEvent(event)


class EventCounterItem(BaseSideTrayItem):
    """
    Manages the three event counters. It offers background colors, depending on which show_* function is called.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    ITEM_COLOR_LATER_THAN_NEXT = QColor(0, 0, 0)
    ITEM_COLOR_CONCURRENT = QColor(233, 156, 0)
    ITEM_COLOR_NEXT = QColor(0, 160, 0)

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: QGraphicsItem = None):
        """
        A string over a polygon to represent the event count indicator.
        """
        super().__init__(part_box_item, parent)
        self.setData(OBJECT_NAME, 'event_counter')

        # Indicator shape
        self.setVisible(False)
        self.__icon = QGraphicsPolygonItem(self)
        self.__icon.setBrush(QBrush(self.ITEM_COLOR_NEXT))
        self.__icon.setPen(QPen(Qt.NoPen))

        # Text
        self.__counter_text = QGraphicsTextItem("", self)
        self.__counter_text.setData(OBJECT_NAME, 'event_counter_text')
        self.__counter_text.setDefaultTextColor(IFX_TEXT_COLOR)

        # The part
        self.__part = part_box_item.part

        self.update_item()

    @override(QGraphicsWidget)
    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent):
        """Filter the events in the Event Queue associated with this part."""
        self.scene().show_filtered_events(self.__part)

    @override(QGraphicsWidget)
    def boundingRect(self) -> QRectF:
        """An abstract methods that must be overridden. Defines the outer bounds of the item as a rectangle."""
        return self.__icon.boundingRect().adjusted(-5, -5, 5, 5)  # add adjustment to help 'clickability'

    @override(QGraphicsItem)
    def shape(self):
        """Must be implemented to allow mouse clicks on the indicator."""
        ind_path = QPainterPath()
        ind_path.addRect(self.boundingRect())
        return ind_path

    @override(BaseSideTrayItem)
    def update_item(self):
        """
        Updates the background polygon.
        """
        text_width = self.__counter_text.boundingRect().width()
        self.__counter_text.setX(-(text_width + EVENT_COUNTER_ARROW_WIDTH))

        p0 = QPointF(0, EVENT_COUNTER_RECT_HEIGHT / 2)
        p1 = QPointF(-EVENT_COUNTER_ARROW_WIDTH, EVENT_COUNTER_RECT_HEIGHT)
        p2 = QPointF(-(text_width + EVENT_COUNTER_ARROW_WIDTH), EVENT_COUNTER_RECT_HEIGHT)
        p3 = QPointF(-(text_width + EVENT_COUNTER_ARROW_WIDTH), 0)
        p4 = QPointF(-EVENT_COUNTER_ARROW_WIDTH, 0)
        self.__icon.setPolygon(QPolygonF([p0, p1, p2, p3, p4]))

    @override(BaseSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.event_counter.value

    def show_next(self, count: int):
        """
        Shows the next count on the background color of ITEM_COLOR_NEXT
        :param count: The next count number.
        """
        self.__icon.setBrush(QBrush(self.ITEM_COLOR_NEXT))
        self.__counter_text.setPlainText(str(count))
        self.update_item()

    def show_concurrent_next(self, count: int):
        """
        Shows the concurrent next count on the background color of ITEM_COLOR_CONCURRENT
        :param count: The concurrent next count number.
        """
        self.__icon.setBrush(QBrush(self.ITEM_COLOR_CONCURRENT))
        self.__counter_text.setPlainText(str(count))
        self.update_item()

    def show_later_than_next(self, count: int):
        """
        Shows the later than next count on the background color of ITEM_COLOR_LATER_THAN_NEXT
        :param count: The later than next count number.
        """
        self.__icon.setBrush(QBrush(self.ITEM_COLOR_LATER_THAN_NEXT))
        self.__counter_text.setPlainText(str(count))
        self.update_item()


class IfxPortItem(IInteractiveItem, LinkAnchorItem):
    """
    Represents an interface port.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    PART_TYPE_ICON_WIDTH = 20
    PART_TYPE_ICON_HEIGHT = 20

    NAME_HEIGHT = PART_TYPE_ICON_HEIGHT
    IFX_PORT_HEIGHT = PART_TYPE_ICON_HEIGHT

    NAME_MAX_LEN = 8

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, port: PartFrame, part_name: str, part_type: str,
                 ifx_level: int, detail_level: DetailLevelEnum, is_left_side: bool,
                 parent: VerticalSideTrayItem, part_box_item: Decl.PartBoxItem):
        """
        Constructs an ifx port. Usually done in the response call in an async call.

        :param port: The part frame used to construct the ifx port.
        :param part_name: The part name from the backend part.
        :param part_type: The part type string from the backend.
        :param ifx_level: The current level.
        :param detail_level: The detail level of the part.
        :param is_left_side: True - if the port is on the left side of the actor item that hosts this ifx port.
        :param parent: The tray that hosts this ifx port.
        :param part_box_item: The actor item that hosts this ifx port
        """
        IInteractiveItem.__init__(self)
        LinkAnchorItem.__init__(self, parent=parent, parent_part_box_item=part_box_item)
        self.set_frame(port)
        self.__part_frame = port
        self.__part = port.part
        self.__part_type = part_type

        self.__is_left_side = is_left_side

        parent_actor_part = part_box_item.part.parent_actor_part
        self.__parent_actor_has_port = parent_actor_part.has_ifx_port(port) if parent_actor_part else False

        self.__ifx_level = ifx_level
        self.__detail_level = detail_level

        self._set_flags_item_change_link_anchor()
        self._set_flags_item_change_interactive()
        assert self.flags() & (QGraphicsItem.ItemIsFocusable | QGraphicsItem.ItemIsSelectable)
        assert self.flags() & QGraphicsItem.ItemSendsScenePositionChanges
        assert not (self.flags() & self.ItemIsMovable)

        self.setToolTip(port.name)

        # Highlight
        self.__highlight_border = QGraphicsRectItem(self)
        self.__highlight_border.setData(OBJECT_NAME, "highlight_border")
        self.__highlight_border.setVisible(False)
        self.__highlight_border.setPen(QPen(Qt.NoPen))
        self.__highlight_border.setPen(QPen(QBrush(HIGHLIGHTED_BORDER_COLOR), IFX_PORT_HIGHLIGHT_MARGIN))

        # Port background.
        self.__port_background = QGraphicsRectItem(self)
        self.__port_background.setData(OBJECT_NAME, "port_background")
        self.__port_background.setRect(
            QRectF(0, 0,
                   self.PART_TYPE_ICON_WIDTH + PORT_BORDER_ALIGNMENT + get_ifx_port_name_width(),
                   self.PART_TYPE_ICON_HEIGHT))

        self.__port_background.setBrush(QBrush(IFX_BACKGROUND_COLOR[part_type]))
        self.__port_background.setPen(QPen(Qt.NoPen))

        self.__icon = QGraphicsSvgItem(str(part_image(part_type)), self)
        self.__icon.setData(OBJECT_NAME, "icon")
        self.__icon.setScale(self.PART_TYPE_ICON_WIDTH / self.__icon.boundingRect().width())

        self.__action_go_to_part = create_action(self, "Go to Part", tooltip="Go to associated part")

        if get_part_editor_class(part_type) is not None:
            self.__action_edit_port = create_action(self, "Edit", tooltip="Edit associated part")
            self.__action_edit_port.triggered.connect(self.__slot_on_edit_ifx_port)

        self.__action_create_link = create_action(self, "Create Link", tooltip="Create Link from associated part")
        self.__link_creation_action_item = LinkCreationActionItem(
            part_box_item, action=self.__action_create_link, parent=self, scale=2)

        # Switch port side
        def __switch_sides(_: bool):
            scene_undo_stack().push(SwitchIfxPortSideCommand(self.__part_frame, self.parent_part_box_item.part))

        self.__action_switch_sides = create_action(parent=self, text="Switch Side", connect=__switch_sides)

        # Move port up
        def __move_up(_: bool):
            scene_undo_stack().push(VerticalMoveIfxCommand(self.__part_frame,
                                                           self.parent_part_box_item.part,
                                                           IfxVerticalMoveDirectionEnum.up.value))

        self.__action_move_up = create_action(parent=self, text="Move Up", connect=__move_up)

        # Move port down
        def __move_down(_: bool):
            scene_undo_stack().push(VerticalMoveIfxCommand(self.__part_frame,
                                                           self.parent_part_box_item.part,
                                                           IfxVerticalMoveDirectionEnum.down.value))

        self.__action_move_down = create_action(parent=self, text="Move Down", connect=__move_down)

        # Name
        self.__part_name = part_name  # the real name in full
        self.__name = QLabel()  # will be abridged
        self.__name.setFont(get_scenario_font(point_size=IFX_TEXT_SIZE, mono=True, stretch=QFont.SemiCondensed))
        self.__name.resize(int(get_ifx_port_name_width()), int(self.NAME_HEIGHT))
        pal = QPalette()
        pal.setColor(QPalette.Window, IFX_BACKGROUND_COLOR[part_type])
        pal.setColor(QPalette.Text, IFX_TEXT_COLOR)
        pal.setColor(QPalette.WindowText, IFX_TEXT_COLOR)
        self.__name.setPalette(pal)
        self.__name_proxy = QGraphicsProxyWidget(self)
        self.__name_proxy.setData(OBJECT_NAME, "part_name")
        self.__name_proxy.setWidget(self.__name)

        self.__ifx_ind_long = QGraphicsRectItem(self)
        self.__ifx_ind_long.setData(OBJECT_NAME, "indicator_long")
        self.__ifx_ind_long.setRect(
            QRectF(0, 0,
                   self.PART_TYPE_ICON_WIDTH + PORT_BORDER_ALIGNMENT + get_ifx_port_name_width(),
                   IFX_INDICATOR_HEIGHT))
        self.__ifx_ind_long.setBrush(QBrush(IFX_BAR_BACKGROUND_COLOR))
        self.__ifx_ind_long.setPen(QPen(Qt.NoPen))
        self.__ifx_ind_long.setY(-IFX_INDICATOR_HEIGHT)
        self.__ifx_ind_long.setVisible(self.__parent_actor_has_port)

        self.__ifx_ind_short = QGraphicsRectItem(self)
        self.__ifx_ind_short.setData(OBJECT_NAME, "indicator_short")
        self.__ifx_ind_short.setRect(QRectF(0, 0,
                                            self.PART_TYPE_ICON_WIDTH,
                                            IFX_INDICATOR_HEIGHT))
        self.__ifx_ind_short.setBrush(QBrush(IFX_BAR_BACKGROUND_COLOR))
        self.__ifx_ind_short.setPen(QPen(Qt.NoPen))
        self.__ifx_ind_short.setY(-IFX_INDICATOR_HEIGHT)
        self.__ifx_ind_short.setVisible(self.__parent_actor_has_port)

        self.set_left_side(is_left_side)

        self.on_detail_level_changed(detail_level)

        self.__action_create_link.triggered.connect(self.__slot_on_create_link)
        self.__action_go_to_part.triggered.connect(self.__slot_on_go_to_part)

        part_box_item.sig_part_item_activated.connect(self.__slot_on_part_item_activated)
        port.signals.sig_name_changed.connect(self.__slot_on_name_changed)
        port.signals.sig_ifx_level_changed.connect(self.__slot_ifx_level_changed)

    def set_left_side(self, is_left_side: bool):
        """
        The ifx port looks different, depending on which side it resides. This function adjusts the ifx port's position,
        background, name and border. It also enables its movement.
        :param is_left_side: True - to place it on the left.
        """
        self.prepareGeometryChange()
        self.__is_left_side = is_left_side
        self.__determine_selection_area()
        if self.__detail_level == DetailLevelEnum.minimal:
            self.__highlight_border.setRect(self.__highlight_rect_minimized)
        else:
            self.__highlight_border.setRect(self.__highlight_rect)

        if is_left_side:
            # The order: link, icon, name
            self.__port_background.setX(-PORT_BORDER_ALIGNMENT)
            self.__link_creation_action_item.setRotation(180)
            self.__link_creation_action_item.setX(-LINK_CREATION_SHORTCUT_SPACE - ITEM_SPACE)
            self.__link_creation_action_item.setY(self.PART_TYPE_ICON_HEIGHT)
            self.__ifx_ind_long.setX(-PORT_BORDER_ALIGNMENT)
            self.__ifx_ind_short.setX(-PORT_BORDER_ALIGNMENT)
            self.__icon.setX(-PORT_BORDER_ALIGNMENT)
            self.__name_proxy.setX(self.PART_TYPE_ICON_WIDTH)
            self.__name.setText(" " + self.__name_abridged(self.__part_name))
            self.__name.setAlignment(Qt.AlignVCenter)
            self.__highlight_border.setX(-ITEM_SPACE)
        else:
            # The order: name, icon, link
            self.__port_background.setX(0)
            self.__link_creation_action_item.setRotation(0)
            self.__link_creation_action_item.setX(get_ifx_port_name_width() + self.PART_TYPE_ICON_WIDTH +
                                                  LINK_CREATION_SHORTCUT_SPACE + ITEM_SPACE)
            self.__link_creation_action_item.setY(0)
            self.__ifx_ind_long.setX(0)
            self.__ifx_ind_short.setX(get_ifx_port_name_width() + PORT_BORDER_ALIGNMENT)
            self.__icon.setX(get_ifx_port_name_width() + PORT_BORDER_ALIGNMENT)
            self.__name_proxy.setX(0)
            self.__name.setText(self.__name_abridged(self.__part_name) + " ")
            self.__name.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.__highlight_border.setX(0)

        self.enable_move_up()
        self.enable_move_down()

    @override(QGraphicsItem)
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, new_value: QVariant) -> QVariant:
        """Call 'itemChange' from every base class"""
        LinkAnchorItem.itemChange(self, change, new_value)
        return IInteractiveItem.itemChange(self, change, new_value)

    @override(LinkAnchorItem)
    def can_start_link(self) -> bool:
        return self.__part.can_add_outgoing_link()

    @override(LinkAnchorItem)
    def is_link_allowed(self, link_anchor: LinkAnchorItem) -> bool:
        """
        Connecting this port to it's parent box item -> not allowed
        Connecting this port to another port on the same parent box item -> not allowed
        """
        return self.parent_part_box_item not in (link_anchor, link_anchor.parent_part_box_item)

    @override(QGraphicsItem)
    def contextMenuEvent(self, evt: QGraphicsSceneContextMenuEvent):
        """
        Shows the context menu on this item
        :param evt:
        """

        self.scene().set_selection(self)

        context_menu = QMenu()
        # FIXME build 3: the next line should show part type name as menu "header" but it doesn't work:
        # This is occurs because 'windows' style does not support separators with text. None of the other styles worked.
        # http://www.qtcentre.org/threads/12161-QMenu-addSeparator%28%29-and-setText%28%29?p=64440#post64440
        context_menu.addSection(self.__part_type.capitalize())

        # Set Ifx Level
        menu_ifx_level = QMenu("Set Interface Level", parent=context_menu)
        menu_ifx_ports = QMenu("Go to Ifx Port", parent=context_menu)
        context_menu.addMenu(menu_ifx_level)
        context_menu.addMenu(menu_ifx_ports)

        part = self.__part_frame.part

        def __level_change(_: bool):
            ifx_level_from_sender = self.sender().data()
            if verify_ifx_level_change_ok(part, ifx_level_from_sender):
                scene_undo_stack().push(ChangeIfxLevelCommand(part, ifx_level_from_sender))

        def __fill_level_change_menu(ifx_labels):
            for ifx_level, level_displayed in ifx_labels:
                action_level_change = create_action(parent=menu_ifx_level,
                                                    text=level_displayed,
                                                    name=menu_ifx_level.title() + level_displayed)
                if ifx_level == self.__ifx_level:
                    action_level_change.setEnabled(False)
                    action_level_change.setFont(get_scenario_font(bold=True))
                else:
                    action_level_change.triggered.connect(__level_change)
                    action_level_change.setData(ifx_level)
                    action_level_change.setFont(get_scenario_font())

                menu_ifx_level.addAction(action_level_change)

        AsyncRequest.call(get_labels_ifx_levels, part, response_cb=__fill_level_change_menu)

        def __goto_ifx_port(_: bool):
            """
            Go to the interface port selected from the context menu.
            """
            ifx_port_selected = self.sender().data()
            parts_path = part.get_parts_path(with_part=False)
            actor = parts_path[len(parts_path) - ifx_port_selected]  # Convert index from ifx-to-list
            self.scene().sig_show_ifx_port.emit(actor, part)

        def __fill_goto_ifx_port_menu(ifx_port_labels, view_ifx_level):
            """
            Populates the context menu with actions for navigating from the current interface port at view_ifx_level to
            the other associated interface ports.
            :param ifx_port_labels: The interface port labels corresponding to the ifx level of the port to go to.
            :param view_ifx_level: The current ifx level of the ifx port the context menu was invoked on.
            """
            for ifx_level, port_displayed in ifx_port_labels:
                action_go_to_port = create_action(parent=menu_ifx_ports,
                                                  text=port_displayed,
                                                  name=menu_ifx_ports.title() + port_displayed)
                if ifx_level == view_ifx_level:
                    action_go_to_port.setEnabled(False)
                    action_go_to_port.setFont(get_scenario_font(bold=True))
                else:
                    action_go_to_port.triggered.connect(__goto_ifx_port)
                    action_go_to_port.setData(ifx_level)
                    action_go_to_port.setFont(get_scenario_font())

                menu_ifx_ports.addAction(action_go_to_port)

        AsyncRequest.call(get_labels_ifx_ports,
                          part,
                          self.parent_part_box_item.part,
                          response_cb=__fill_goto_ifx_port_menu)

        context_menu.addAction(self.__action_go_to_part)

        if get_part_editor_class(self.__part_type) is not None:
            context_menu.addAction(self.__action_edit_port)

        # Create Link
        if self.__part.CAN_BE_LINK_SOURCE:
            context_menu.addAction(self.__action_create_link)
            self.__action_create_link.setEnabled(self.can_start_link())

        def populate_more_menu_items():
            # Switch
            context_menu.addAction(self.__action_switch_sides)

            # Move
            context_menu.addAction(self.__action_move_up)
            context_menu.addAction(self.__action_move_down)

            if context_menu.actions():
                # QCursor.pos() is important. All other mapToGlobal functions cannot serve the purpose.
                context_menu.exec(QCursor.pos())
            else:
                evt.ignore()

        self._populate_create_missing_link_menu(context_menu, end_callback=populate_more_menu_items)

    @override(QGraphicsItem)
    def boundingRect(self):
        return self.childrenBoundingRect()

    @override(QGraphicsItem)
    def shape(self) -> QPainterPath:
        ifx_port_path = QPainterPath()
        ifx_port_path.addRect(self.boundingRect())
        return ifx_port_path

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, *args):
        pass

    @override(QGraphicsObject)
    def type(self) -> int:
        return CustomItemEnum.ifx_port.value

    @override(IInteractiveItem)
    def get_scenario_object(self) -> BasePart:
        return self.__part_frame.part

    @override(LinkAnchorItem)
    def get_link_boundary_rect(self) -> QRectF:
        return self.__icon.sceneBoundingRect()

    @override(LinkAnchorItem)
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        log.debug("Ifx port item for {} got mouse press: {}", self.__part_frame, EventStr(event))
        super().mousePressEvent(event)

    @override(LinkAnchorItem)
    def mouseDoubleClickEvent(self, evt: QGraphicsSceneMouseEvent):
        if get_part_editor_class(self.__part_type) is not None:
            self.__on_edit_ifx_port()

    @override(LinkAnchorItem)
    def get_part_id(self) -> int:
        return self.__part_frame.part.SESSION_ID

    @property
    def part(self):
        return self.__part

    @property
    def part_frame(self):
        return self.__part_frame

    def on_detail_level_changed(self, detail_level: DetailLevelEnum):
        """
        Maintains the state for this port and changes the GUI.
        :param detail_level: The detail level
        """
        self.prepareGeometryChange()
        self.__name_proxy.setVisible(detail_level == DetailLevelEnum.full)
        self.__port_background.setVisible(detail_level == DetailLevelEnum.full)
        if detail_level == DetailLevelEnum.minimal:
            self.__highlight_border.setRect(self.__highlight_rect_minimized)
            self.__link_creation_action_item.setVisible(False)
            self.__ifx_ind_long.setVisible(False)
        else:
            self.__highlight_border.setRect(self.__highlight_rect)
            self.__ifx_ind_long.setVisible(self.__parent_actor_has_port)

    def enable_move_up(self, enable: bool = True):
        """
        Enable or disable the context menu port option for moving the port up.

        :param enable: Flag to enable or disable the option.
        """
        self.__action_move_up.setEnabled(enable)

    def enable_move_down(self, enable: bool = True):
        """
        Enable or disable the context menu port option for moving the port down.

        :param enable: Flag to enable or disable the option.
        """
        self.__action_move_down.setEnabled(enable)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    link_boundary_rect = property(get_link_boundary_rect)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    @override(IInteractiveItem)
    def _highlighting_changed(self):
        self.__highlight_border.setVisible(self._highlighted)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __determine_selection_area(self):
        """
        The selection size and position depend on the ifx levels.
        """
        height_adj = 0
        if self.__parent_actor_has_port:
            self.__highlight_border.setY(-IFX_INDICATOR_HEIGHT)
            height_adj = IFX_INDICATOR_HEIGHT
        else:
            self.__highlight_border.setY(0)

        self.__highlight_rect = QRectF(0, 0,
                                       self.PART_TYPE_ICON_WIDTH + get_ifx_port_name_width() + ITEM_SPACE,
                                       self.IFX_PORT_HEIGHT + height_adj)

        self.__highlight_rect = self.__highlight_rect.adjusted(-IFX_PORT_HIGHLIGHT_MARGIN,
                                                               -IFX_PORT_HIGHLIGHT_MARGIN,
                                                               IFX_PORT_HIGHLIGHT_MARGIN,
                                                               IFX_PORT_HIGHLIGHT_MARGIN)

        self.__highlight_rect_minimized = QRectF(0, 0,
                                                 self.PART_TYPE_ICON_WIDTH + ITEM_SPACE,
                                                 self.IFX_PORT_HEIGHT + height_adj)
        self.__highlight_rect_minimized = self.__highlight_rect_minimized.adjusted(
            -IFX_PORT_HIGHLIGHT_MARGIN,
            -IFX_PORT_HIGHLIGHT_MARGIN,
            IFX_PORT_HIGHLIGHT_MARGIN,
            IFX_PORT_HIGHLIGHT_MARGIN)

        if not self.__is_left_side:
            self.__highlight_rect_minimized.moveLeft(get_ifx_port_name_width())

    def __name_abridged(self, name) -> str:
        """
        Returns the first (NAME_MAX_LEN - 1) characters plus "..." if the original name is longer than NAME_MAX_LEN.
        :param name: The original name
        :return: The abridged name
        """
        length = len(name)
        return (name[:(self.NAME_MAX_LEN - 1)] + HORIZONTAL_ELLIPSIS) if length > self.NAME_MAX_LEN else name

    def __on_create_link(self):
        self.scene().set_selection(self)
        self.scene().start_link_creation_from(self)

    def __on_part_item_activated(self, activated: bool):
        """
        When it is activated, the link creation shortcut is made visible; otherwise, invisible.
        :param activated: True - the part proximity border is activated.
        """
        self.__link_creation_action_item.setVisible(activated and self.can_start_link())

    def __on_name_changed(self, new_name: str):
        self.__part_name = new_name
        self.__name.setText(self.__name_abridged(new_name))
        self.setToolTip(new_name)
        if self.__is_left_side:
            self.__name.setText(" " + self.__name_abridged(new_name))
        else:
            self.__name.setText(self.__name_abridged(new_name) + " ")

    def __on_go_to_part(self):
        """
        Shows the part represented by this port in the center of the view.
        """
        self.scene().sig_show_child_part.emit(self.__part_frame.part)

    def __on_edit_ifx_port(self):
        self.scene().sig_open_part_editor.emit(self.__part_frame.part)

    def __ifx_level_changed(self, ifx_level: int):
        """
        Persists the ifx_level and adjusts the look and feel of the selection area. It will re-evaluate the
        exposure of this port on the parent actor.
        :param ifx_level: the level to be persisted.
        """
        self.prepareGeometryChange()
        self.__ifx_level = ifx_level
        parent_actor_part = self.parent_part_box_item.part.parent_actor_part
        if parent_actor_part is None:
            # The parent actor has been removed. This can happen when child port ifx levels
            # have been triggered to reset to 0 in response to the parent actor being deleted. The
            # port item itself has also been set for deletion via deleteLater but is still alive
            # temporarily until Qt decides it's safe to disconnect and delete.
            return

        self.__parent_actor_has_port = parent_actor_part.has_ifx_port(self.__part_frame)

        self.__determine_selection_area()

        if self.__detail_level == DetailLevelEnum.minimal:
            self.__ifx_ind_long.setVisible(False)
            self.__highlight_border.setRect(self.__highlight_rect_minimized)
        else:
            self.__ifx_ind_long.setVisible(self.__parent_actor_has_port)
            self.__highlight_border.setRect(self.__highlight_rect)

        self.__ifx_ind_short.setVisible(self.__parent_actor_has_port)

    __slot_ifx_level_changed = safe_slot(__ifx_level_changed)
    __slot_on_edit_ifx_port = safe_slot(__on_edit_ifx_port)
    __slot_on_go_to_part = safe_slot(__on_go_to_part)
    __slot_on_create_link = safe_slot(__on_create_link)
    __slot_on_part_item_activated = safe_slot(__on_part_item_activated)
    __slot_on_name_changed = safe_slot(__on_name_changed)
