# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Module containing 2d related items and their behaviour.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import webbrowser

# [2. third-party]
from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QSizeF, QSize, QPointF, QMarginsF, QVariant, QObject
from PyQt5.QtGui import QCursor, QBrush, QPainter, QPen, QPainterPath, QPolygonF, QKeyEvent
from PyQt5.QtWidgets import QAction, QMenu, QWidget, QGraphicsProxyWidget, QGraphicsItem
from PyQt5.QtWidgets import QGraphicsObject, QStyleOptionGraphicsItem, QGraphicsSceneContextMenuEvent
from PyQt5.QtWidgets import QGraphicsSceneMouseEvent, QGraphicsSceneHoverEvent, QMessageBox

# [3. local]
from ...core import override, override_optional, override_required
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...scenario.defn_parts import Position, PartLink, BasePart, DetailLevelEnum

from ..async_methods import AsyncRequest
from ..gui_utils import PART_ICON_COLORS, QTBUG_55918_OPACITY
from ..gui_utils import PART_ITEM_BORDER_WIDTH, ITEM_SPACE, LINK_CREATION_SHORTCUT_SPACE, try_disconnect
from ..gui_utils import PROXIMITY_MARGIN_LEFT, PROXIMITY_MARGIN_RIGHT, PROXIMITY_MARGIN_TOP, PROXIMITY_MARGIN_BOTTOM
from ..gui_utils import exec_modal_dialog, LINK_CREATION_ACTION_ITEM_WIDTH, LINK_CREATION_ACTION_ITEM_HEIGHT
from ..conversions import map_from_scenario, SCALE_FACTOR
from ..safe_slot import safe_slot, ext_safe_slot
from ..actions_utils import create_action
from ..undo_manager import RemovePartCommand, scene_undo_stack
from ..part_editors.common_part_help import PartHelp
from ..part_editors import get_part_editor_class

from .common import ZLevelsEnum, get_part_item_class, DetailLevelOverrideEnum, CustomItemEnum, IInteractiveItem
from .common import ICustomItem, EventStr, disconnect_all_slots_children
from .linking import LinkAnchorItem
from .part_box_side_items import TopSideTrayItem, BottomSideTrayItem, LeftSideTrayItem, RightSideTrayItem
from .part_box_side_items import IfxBarTrayItem
from .part_box_side_items import PartProximityBorderItem, LinkCreationActionItem, PartSelectionBorderItem
from .base_part_widgets import IPartWidget
from .indicators import AlertIndicator

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'PartBoxItem',
    'WidgetProxyPartItem',
    'FramelessPartItem'
]

log = logging.getLogger('system')

MenuActions = List[Either[QAction, QMenu]]  # menus can contain submenus


class Decl(AnnotationDeclarations):
    IBoxedPartItem = 'IBoxedPartItem'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class PartBoxItem(IInteractiveItem, LinkAnchorItem):
    """
    A graphics item in the 2D scene that serves as a container for either a framed part (widget) or frameless part item.

    Two margins are adjusted to cover the part box item and its side items.

    By design, the selection area is inside the proximity area. Both margins are evaluated dynamically, depending on
    the types of the parts, and the states of the parts.
    """

    MULTI_SELECTABLE = True
    DRAGGABLE = True

    IEXPLORER_EXE_LOCATION = "C:\Program Files\Internet Explorer\iexplore.exe"

    sig_part_item_activated = pyqtSignal(bool)  # True - activated; False - inactivated

    def __init__(self, the_part: BasePart, parent: QGraphicsItem = None):
        """
        :param the_part: the part to set in this graphics item.
        """
        IInteractiveItem.__init__(self)
        LinkAnchorItem.__init__(self, parent=parent)
        self.set_frame(the_part.part_frame)
        self.__part = the_part
        self.__part_item = None  # The frontend part - either a framed (widget) part item or 'frameless' part item

        # Flags
        self._set_flags_item_change_interactive()
        self._set_flags_item_change_link_anchor()
        assert self.flags() & (QGraphicsItem.ItemIsFocusable | QGraphicsItem.ItemIsSelectable | self.ItemIsMovable)
        assert self.flags() & QGraphicsItem.ItemSendsScenePositionChanges
        self.setAcceptHoverEvents(True)

        self.__has_editor = get_part_editor_class(the_part.PART_TYPE_NAME) is not None

        self.__header_frame_height = None  # A value will be assigned if the inner item has a header frame.
        self.__ifx_level = 0

        self.__ifx_bar_item = IfxBarTrayItem(self, self)

        self.__size_grip_corner_item = None
        self.__top_side_tray_item = TopSideTrayItem(self, self)
        self.__bottom_side_tray_item = BottomSideTrayItem(self, self)
        self.__left_side_tray_item = LeftSideTrayItem(self, self)
        self.__right_side_tray_item = RightSideTrayItem(self, self)
        self.__top_side_tray_item.setZValue(ZLevelsEnum.trays)
        self.__bottom_side_tray_item.setZValue(ZLevelsEnum.trays)
        self.__left_side_tray_item.setZValue(ZLevelsEnum.trays)
        self.__right_side_tray_item.setZValue(ZLevelsEnum.trays)

        self.__ifx_level = the_part.part_frame.ifx_level
        the_part.part_frame.signals.sig_ifx_level_changed.connect(self.__slot_ifx_level_changed)

        self.__part_selection_border_item = PartSelectionBorderItem(self)
        self.__part_selection_border_item.setVisible(self._highlighted)

        self.__proximity_border_item = PartProximityBorderItem(self)
        self.prepareGeometryChange()

        # A thin border for the actual part item.
        # Note: this item used to be a QGraphicsRectItem but is now a QPainterPath. There was an issue
        # when zooming in the View where the QGraphicsRectItem line would not be rendered at high zoom levels.
        # A appropriate fix could not be found using this item so the QPainterPath was implemented to draw the
        # boundary since it does not experience the rendering issue when zooming.
        self.__part_border_path = QPainterPath()

        # Create context menu actions common to all parts
        self.__toggle_icon_action = create_action(
            self, "Toggle Contents", "Toggle the part between showing the full and the minimal detail level")
        self.__create_link_action = create_action(self, "Create Link", tooltip="Create link from part")
        self.__edit_part_action = create_action(self, "Edit...", tooltip="Edit part")
        self.__cut_part_action = create_action(self, "Cut", tooltip="Cut part")
        self.__copy_part_action = create_action(self, "Copy", tooltip="Copy part")
        self.__delete_action = create_action(self, "Delete", tooltip="Delete part")
        self.__help_action = create_action(self, "Help", tooltip="Help on part")

        self.__create_link_action.triggered.connect(self.slot_on_create_link_action)
        self.__edit_part_action.triggered.connect(self.slot_on_edit_part_action)
        self.__cut_part_action.triggered.connect(self.slot_on_cut_part_action)
        self.__copy_part_action.triggered.connect(self.slot_on_copy_part_action)
        self.__delete_action.triggered.connect(self.slot_on_delete_part_action)
        self.__help_action.triggered.connect(self.slot_on_help_action)

        self.__link_creation_action_item = LinkCreationActionItem(
            self, action=self.__create_link_action, parent=self, scale=3.0)
        self.__size_grip_end_action = None  # create it for the framed widgets only later.
        self.__part_help = PartHelp()

        self.setObjectName(the_part.part_frame.name)

        inner_item_class = get_part_item_class(the_part.PART_TYPE_NAME)
        new_inner_item = inner_item_class(the_part, self)
        self.__part_item = new_inner_item.init_boxed_part_item(WidgetProxyPartItem)
        assert isinstance(self.__part_item, IBoxedPartItem)

        # Connect part size change signals to link anchor size change signal for linked connections
        self.__part_item.sig_boxed_item_size_changed.connect(self.sig_link_anchor_size_changed)

        self.__highlight_rect = QRectF()

        # Set the z-value relative to other part-2D-items
        self.setZValue(ZLevelsEnum.child_part)

        self._setup_positioning()
        self.on_size_changed()

    def set_header_frame_height(self, val):
        """
        Sets a header frame height if the item wants to hold a framed widget.
        :param val:
        """
        self.__header_frame_height = val

    def get_ifx_bar_item(self):
        return self.__ifx_bar_item

    def get_link_creation_action_item(self):
        return self.__link_creation_action_item

    def get_top_side_tray_item(self):
        return self.__top_side_tray_item

    def get_bottom_side_tray_item(self):
        return self.__bottom_side_tray_item

    def get_left_side_tray_item(self):
        return self.__left_side_tray_item

    def get_right_side_tray_item(self):
        return self.__right_side_tray_item

    def get_proximity_border_item(self):
        return self.__proximity_border_item

    def get_part_selection_border_item(self):
        return self.__part_selection_border_item

    @override(QGraphicsItem)
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, new_value: QVariant) -> QVariant:
        """Call 'itemChange' from every base class"""
        LinkAnchorItem.itemChange(self, change, new_value)
        return IInteractiveItem.itemChange(self, change, new_value)

    @override(QGraphicsObject)
    def paint(self, painter: QPainter, style: QStyleOptionGraphicsItem, widget: QWidget = None):
        """
        An abstract methods that must be overridden.
        """
        if self.__part.SHOW_FRAME:
            # Paint the part's frame
            painter.setRenderHints(QPainter.Antialiasing | QPainter.HighQualityAntialiasing)
            #DRWA
            painter.setPen(QPen(QBrush(PART_ICON_COLORS[self.__part.PART_TYPE_NAME]), PART_ITEM_BORDER_WIDTH, join = Qt.MiterJoin))
            painter.setBrush(QBrush(PART_ICON_COLORS[self.__part.PART_TYPE_NAME]))
            painter.drawPath(self.__part_border_path)
        else:
            # Do not paint the part's frame
            pass

    @override(QGraphicsItem)
    def shape(self):
        """
        The shape is the base item rectangle plus the attached link short cut. When the mouse hovers over the shape, you
        can drag the item. Without this function, when the mouse is close enough to the item, you can
        already drag the item. That is not intuitive because you are supposed to drag the canvas when the mouser is
        not directly over the item.
        """
        the_shape = QPainterPath()
        base_w = max(self.__part_item.boundingRect().width(), IfxBarTrayItem.IFX_BAR_WIDTH_MIN)

        if self.__header_frame_height is None:
            link_short_cut_area_height = LINK_CREATION_ACTION_ITEM_HEIGHT
        else:
            link_short_cut_area_height = self.__header_frame_height

        if self.__ifx_level > 0:
            ifx_bar_height = TopSideTrayItem.TOP_SIDE_TRAY_HEIGHT
        else:
            ifx_bar_height = 0

        polygon = QPolygonF(
            [QPointF(0, -ifx_bar_height),
             QPointF(base_w + ITEM_SPACE + LINK_CREATION_ACTION_ITEM_WIDTH, -ifx_bar_height),
             QPointF(base_w + ITEM_SPACE + LINK_CREATION_ACTION_ITEM_WIDTH, link_short_cut_area_height),
             QPointF(base_w, link_short_cut_area_height),
             QPointF(base_w, self.__part_item.boundingRect().height()),
             QPointF(0, self.__part_item.boundingRect().height()),
             ])
        the_shape.addPolygon(polygon)
        return the_shape

    @override(QGraphicsObject)
    def boundingRect(self) -> QRectF:
        """
        An abstract methods that must be overridden. Defines the outer bounds of the item as a rectangle;
        all painting must be restricted to inside an item's bounding rect.
        :return: a simple rectangle that defines the item boundaries.
        """
        return self.__proximity_border_item.rect()

    @override(QGraphicsObject)
    def type(self) -> int:
        return CustomItemEnum.part.value

    @override(QGraphicsObject)
    def mouseDoubleClickEvent(self, evt: QGraphicsSceneMouseEvent):
        if not self.scene().has_multipart_selection() and self.__has_editor:
            self.on_open_editor()
            evt.accept()

    @override(QGraphicsObject)
    def mousePressEvent(self, evt: QGraphicsSceneMouseEvent):
        log.debug("Part box item for {} got mouse press: {}", self.__part, EventStr(evt))
        assert self.parentItem() is None
        self.__resize_to_cover_side_items()
        super().mousePressEvent(evt)

    @override(QGraphicsObject)
    def mouseReleaseEvent(self, evt: QGraphicsSceneMouseEvent):
        log.debug("Part box item for {} got mouse release", self.__part)
        super().mouseReleaseEvent(evt)

    @override(QGraphicsObject)
    def keyPressEvent(self, event: QKeyEvent):
        """
        Handles the deletion of parts by pressing the Delete key
        :param event: a key press event
        """
        key_pressed = event.key()
        if key_pressed == Qt.Key_Delete:
            if self.__part.parent_actor_part:
                self.on_delete_part_request()
            else:
                log.warning("Can not delete root actor with name: '{}'", self.__part.name)

    @override(QGraphicsObject)
    def contextMenuEvent(self, evt: QGraphicsSceneContextMenuEvent):
        """
        Show the context menu on this item.
        """
        if self.__part_item is None:
            return  # no context menu!

        self.scene().set_selection(self)

        item = self.__part_item
        context_menu = QMenu()
        # FIXME build 3: the next line should show part type name as menu "header" but it doesn't work.
        # This is occurs because 'windows' style does not support separators with text. None of the other styles worked.
        # http://www.qtcentre.org/threads/12161-QMenu-addSeparator%28%29-and-setText%28%29?p=64440#post64440
        context_menu.addSection(self.__part.PART_TYPE_NAME.capitalize())
        item.put_menu_actions(context_menu)

        if self.__part.SHOW_FRAME:
            context_menu.addSeparator()
            context_menu.addAction(self.__toggle_icon_action)

        context_menu.addSeparator()

        if self.__part.CAN_BE_LINK_SOURCE:
            context_menu.addAction(self.__create_link_action)
            self.__create_link_action.setEnabled(self.can_start_link())

        def populate_more_menu_items():
            if self.__has_editor:
                context_menu.addAction(self.__edit_part_action)

            context_menu.addAction(self.__top_side_tray_item.comment_visibility_action)

            context_menu.addSeparator()

            context_menu.addAction(self.__cut_part_action)
            self.__cut_part_action.setEnabled(self.__part_item.can_be_pasted())
            context_menu.addAction(self.__copy_part_action)
            self.__copy_part_action.setEnabled(self.__part_item.can_be_pasted())
            context_menu.addAction(self.__delete_action)

            context_menu.addSeparator()
            context_menu.addAction(self.__help_action)

            if context_menu.actions():
                # QCursor.pos() is important. All other mapToGlobal functions cannot serve the purpose.
                # noinspection PyArgumentList
                context_menu.exec(QCursor.pos())
            else:
                evt.ignore()

        self._populate_create_missing_link_menu(context_menu, end_callback=populate_more_menu_items)

    @override(QGraphicsObject)
    def deleteLater(self):
        """
        This object does manage other QObjects however, so we must clean them up.
        """
        log.debug('DeleteLater of PartBoxItem for part {}', self.__part)
        super().deleteLater()
        self._disconnect_all_slots()
        self.__part_item._disconnect_all_slots()
        disconnect_all_slots_children(self)

    @override(QGraphicsObject)
    def hoverEnterEvent(self, _: QGraphicsSceneHoverEvent):
        """
        When hovering over a part frame within the Actor 2D View, this overridden method gets invoked.  When this method
        is invoked, a call to the scene will allow a signal to be sent that will change the text in the Context Help,
        """
        self.scene().sig_update_context_help.emit(self.__part)

    @override(IInteractiveItem)
    def get_scenario_object(self) -> BasePart:
        """Get the scenario object that corresponds to this item"""
        return self.__part

    @override(IInteractiveItem)
    def get_highlight_rect(self, outer: bool = False) -> QRectF:
        """Get the highlighted rect (inner or outer). Only inner part is defined present time.
        The method can be expanded in future if required.
        :param outer: indicate if want to return outer rect. by default, inner rect is returned
        :returns: the highlighted rect
        """
        if outer:
            raise NotImplementedError
        else:
            return self.get_inner_item().boundingRect()

    @override(LinkAnchorItem)
    def get_part_id(self) -> int:
        return self.__part.SESSION_ID

    @override(LinkAnchorItem)
    def get_link_boundary_rect(self) -> QRectF:
        """
        Gets the rectangle that a link intersects at one of its sides.
        :return: The rect that may or may not include the area of the ifx bar, depending on the ifx value.
        """
        # Tells the linking manager the rect of this item includes the ifx bar area if the ifx level is larger than 0;
        # otherwise, the rect is just that of the item.
        if self.__ifx_level > 0:
            # Combines the part item's scene bounding rect with
            # the interface bar's to get the attachment boundary for links.
            ifx_rect = self.__ifx_bar_item.sceneBoundingRect()
            part_item_rect = self.__part_item.sceneBoundingRect()
            top_left = ifx_rect.topLeft()
            bottom_right = part_item_rect.bottomRight()
            return QRectF(top_left, bottom_right)
        else:
            return self.__part_item.sceneBoundingRect()

    @override(LinkAnchorItem)
    def can_start_link(self) -> bool:
        return self.__part.can_add_outgoing_link()

    def get_size(self) -> QSizeF:
        """
        Accessor for the framed part (proxy-widget).
        :return: the framed-widget.
        """
        return self.__part_item.get_size()

    def get_inner_item(self) -> Decl.IBoxedPartItem:
        """
        Accessor for the item in this PartBoxItem
        :return: the item
        """
        return self.__part_item

    @override(LinkAnchorItem)
    def get_children_anchor_items(self) -> List[LinkAnchorItem]:
        """Return a list of LinkAnchorItem objects that have this part as parent"""
        inner_item_children = [item for item in self.__part_item.childItems() if isinstance(item, LinkAnchorItem)]
        part_box_item_children = [item for item in self.childItems() if isinstance(item, LinkAnchorItem)]
        return inner_item_children + part_box_item_children

    def get_part(self) -> BasePart:
        """Retrieves the part associated with this link anchor."""
        return self.__part

    @override(IInteractiveItem)
    def set_scene_pos_from_scenario(self, x: float, y: float):
        scene_pos = map_from_scenario(Position(x, y))
        assert self.parentItem() is None
        log.debug("Scene pos for part box item {} (part {}) will be ({:.5}, {:.5})",
                  self.ITEM_ID, self.__part, scene_pos.x(), scene_pos.y())
        self.setPos(scene_pos)

    def on_create_link(self):
        """
        Start the creation of a link from this part. Delegates to the scene, allowing the user to select the
        target part or ESC to cancel.
        """
        # Forcing selection is necessary because the link creation shortcut doesn't select this automatically.
        self.scene().set_selection(self)
        self.proposed_link_name = None
        self.scene().start_link_creation_from(self)

    def on_open_editor(self):
        """Open the editor for this scenario part"""
        assert self.__has_editor
        self.scene().open_part_editor(self.__part)

    def on_cut_part_request(self):
        """Cut this and other selected parts from the scene"""
        assert self.part.parent_actor_part is not None
        assert self.parentItem() is None
        self.scene().get_main_view().cut_selected_parts()

    def on_copy_part_request(self):
        """Copy this and other selected parts in the scene"""
        assert self.part.parent_actor_part is not None
        assert self.parentItem() is None
        assert self.isSelected()
        assert self.scene().get_selected_objects() == [self.part]
        self.scene().get_main_view().copy_selected_parts()

    def on_delete_part_request(self):
        """
        Request scenario to delete this part, once user confirms;
        async signal from scenario will eventually tell the scene that contains this PartBoxItem to delete us.
        """
        if self.scene().has_multipart_selection():
            self.scene().delete_selected_parts()
            return

        assert self.part.parent_actor_part is not None

        if not self.scene().is_item_visible(self):
            msg = 'Some waypoints are not in view: "{}". Click Yes to delete them anyways, ' \
                  'or No to go back without deletion.'.format(self.part_frame.name)
            if exec_modal_dialog("Delete Part", msg, QMessageBox.Question) != QMessageBox.Yes:
                return

        assert self.parentItem() is None
        # No parent PartBoxItem, item can delete itself
        cmd = RemovePartCommand(self.__part)
        scene_undo_stack().push(cmd)

    def on_part_help_request(self):
        """
        Method called when the 'Help' context menu is clicked.
        """
        path = self.__part_help.get_part_help_path(self.__part.PART_TYPE_NAME)
        webbrowser.open_new_tab(path)

    @override(LinkAnchorItem)
    def on_link_added(self, link: PartLink):
        """Create a graphics link item in scene for the given link ID, created by backend."""
        self.scene().on_part_link_added(self, link)

    def change_proximity_state(self, activated: bool):
        """
        When it is activated, the link creation shortcut is made visible; otherwise, invisible.
        :param activated: True - the part proximity border is activated.
        """
        self.sig_part_item_activated.emit(activated)
        self.__link_creation_action_item.setVisible(activated and self.can_start_link())

    def get_toggle_icon_action(self) -> QAction:
        """
        Helper method to access the toggle icon action.
        :return: The toggle icon action.
        """
        return self.__toggle_icon_action

    def on_size_changed(self):
        """
        Slot called when the framed item changes its size or frameless is_highlighted attribute changes
        """
        self.prepareGeometryChange()

        inner_rect = QRectF(self.__part_item.boundingRect())
        self.__part_border_path = QPainterPath()
        self.__part_border_path.addRect(inner_rect)

        self.__bottom_side_tray_item.setY(inner_rect.height() + PART_ITEM_BORDER_WIDTH)

        self.__right_side_tray_item.setX(self.size.width())

        self.__bottom_side_tray_item.update_item()
        self.__left_side_tray_item.update_item()
        self.__right_side_tray_item.update_item()
        self.__resize_to_cover_side_items()

    def on_detail_level_changed(self, detail_level: DetailLevelEnum, current_override: DetailLevelOverrideEnum):
        """
        Updates the various attributes with the new detail level setting.
        :param detail_level: What the detail level is (regardless of override).
        :param current_override: The current override status.
        """
        self.left_side_tray_item.on_detail_level_changed(detail_level)
        self.right_side_tray_item.on_detail_level_changed(detail_level)
        self.part_selection_border_item.on_detail_level_changed(detail_level)

        if detail_level == DetailLevelEnum.minimal:
            self.link_creation_action_item.setVisible(False)

        if current_override == DetailLevelOverrideEnum.none:
            self.__toggle_icon_action.setEnabled(True)
        else:
            self.__toggle_icon_action.setEnabled(False)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_set_scene_pos_from_scenario = safe_slot(set_scene_pos_from_scenario)
    slot_on_create_link_action = safe_slot(on_create_link)
    slot_on_edit_part_action = safe_slot(on_open_editor)
    slot_on_cut_part_action = safe_slot(on_cut_part_request)
    slot_on_copy_part_action = safe_slot(on_copy_part_request)
    slot_on_delete_part_action = safe_slot(on_delete_part_request)
    slot_on_help_action = safe_slot(on_part_help_request)
    slot_on_link_added = ext_safe_slot(on_link_added)
    slot_on_size_changed = safe_slot(on_size_changed)

    part = property(get_part)
    ifx_bar_item = property(get_ifx_bar_item)
    link_creation_action_item = property(get_link_creation_action_item)
    top_side_tray_item = property(get_top_side_tray_item)
    bottom_side_tray_item = property(get_bottom_side_tray_item)
    left_side_tray_item = property(get_left_side_tray_item)
    right_side_tray_item = property(get_right_side_tray_item)
    proximity_border_item = property(get_proximity_border_item)
    part_selection_border_item = property(get_part_selection_border_item)
    size = property(get_size)
    inner_item = property(get_inner_item)
    children_anchor_items = property(get_children_anchor_items)
    toggle_icon_action = property(get_toggle_icon_action)
    link_boundary_rect = property(get_link_boundary_rect)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IInteractiveItem)
    def _highlighting_changed(self):
        assert self.__part_item is not None
        self.__part_selection_border_item.setVisible(self._highlighted)
        if self._highlighted:
            self.setZValue(ZLevelsEnum.child_part_selected)
        else:
            self.setZValue(ZLevelsEnum.child_part)

        self.on_size_changed()

    @override_optional
    def _setup_positioning(self):
        """Derived class can override this if position is not obtained from part frame"""
        part_frame = self.__part.part_frame
        part_frame.signals.sig_position_changed.connect(self.slot_set_scene_pos_from_scenario)
        pos_x, pos_y = part_frame.get_position()
        self.set_scene_pos_from_scenario(pos_x, pos_y)

    @override(LinkAnchorItem)
    def _disconnect_all_slots(self):
        super()._disconnect_all_slots()

        try_disconnect(self.__create_link_action.triggered, self.slot_on_create_link_action)
        try_disconnect(self.__edit_part_action.triggered, self.slot_on_edit_part_action)
        try_disconnect(self.__cut_part_action.triggered, self.slot_on_cut_part_action)
        try_disconnect(self.__copy_part_action.triggered, self.slot_on_copy_part_action)
        try_disconnect(self.__delete_action.triggered, self.slot_on_delete_part_action)
        try_disconnect(self.__help_action.triggered, self.slot_on_help_action)
        try_disconnect(self.__part_item.sig_boxed_item_size_changed, self.sig_link_anchor_size_changed)

        frame_signals = self.__part.part_frame.signals
        try_disconnect(frame_signals.sig_ifx_level_changed, self.__slot_ifx_level_changed)
        try_disconnect(frame_signals.sig_position_changed, self.slot_set_scene_pos_from_scenario)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __resize_to_cover_side_items(self):
        """
        Adjusts the selection and proximity borders depending on the side items such as the interface bar
        """
        self.prepareGeometryChange()

        ifx_bar_space = 0
        if self.__ifx_level > 0:
            ifx_bar_space = (IfxBarTrayItem.IFX_BAR_HEIGHT +
                             PART_ITEM_BORDER_WIDTH +
                             ITEM_SPACE)

            self.__ifx_bar_item.setY(-ifx_bar_space)
            self.__ifx_bar_item.update_item()

        selection_rect = self.__part_item.boundingRect()
        selection_rect_edge_adjustment = PART_ITEM_BORDER_WIDTH * 2
        selection_rect = selection_rect.marginsAdded(
            QMarginsF(
                selection_rect_edge_adjustment,
                ifx_bar_space + selection_rect_edge_adjustment,
                selection_rect_edge_adjustment,
                selection_rect_edge_adjustment
            )
        )

        selection_rect = selection_rect.marginsAdded(self.__part_item.get_selection_margins())
        self.__part_selection_border_item.setRect(selection_rect)

        outer_rect = self.__part_item.boundingRect()
        outer_rect = outer_rect.marginsAdded(
            QMarginsF(
                0,
                ifx_bar_space + TopSideTrayItem.TOP_SIDE_TRAY_HEIGHT,
                ITEM_SPACE + self.__link_creation_action_item.childrenBoundingRect().width(),
                BottomSideTrayItem.BOTTOM_SIDE_TRAY_HEIGHT
            )
        )
        outer_rect = outer_rect.marginsAdded(self.__part_item.get_proximity_margins())
        self.__proximity_border_item.setRect(outer_rect)

        self.__top_side_tray_item.setY(-(ifx_bar_space +
                                         self.__top_side_tray_item.TOP_SIDE_TRAY_HEIGHT +
                                         ITEM_SPACE))
        self.__top_side_tray_item.update_item()

        adjusted_width = self.__part_item.get_display_width()
        self.__link_creation_action_item.setX((adjusted_width + self.size.width()) / 2 + LINK_CREATION_SHORTCUT_SPACE)
        self.__link_creation_action_item.update_item()

    def __ifx_level_changed(self, ifx_level: int):
        """
        Persists the ifx_level and adjusts the size.
        :param ifx_level: The ifx level to be persisted.
        """
        self.__ifx_level = ifx_level
        self.__resize_to_cover_side_items()
        self.sig_link_anchor_size_changed.emit()

    __slot_ifx_level_changed = safe_slot(__ifx_level_changed)


class IBoxedPartItem(ICustomItem):
    sig_boxed_item_size_changed = pyqtSignal()

    @override_optional
    def populate_data(self):
        """
        Some boxed items may have data that slow down the __init__. That will block the boxing process, such as 
        QGraphicsWidget.setWidget().
        
        The derived class may override this function to populate data after the __init__ so that it can be completed
        and added to the scene as soon as possible.
        """
        pass

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
    def get_display_width(self) -> int:
        """
        We display the physical width for most items. Sometimes, the physical width of an item is different from its
        desired display width. For example, a node has a very small physical width, but when it has an interface
        bar, we want to display a wider area that covers both the bar and the node itself.

        The derived class implements this function to return a width that covers a wider area. By default, this function
        returns the physical width of the item.
        :return: the base width to be displayed for the item
        """
        return self.get_size().width()

    @override_required
    def get_size(self) -> QSize:
        """Return the size of this item, in pixels"""
        raise NotImplementedError

    @override_optional
    def override_detail_level(self, detail_level_override: DetailLevelOverrideEnum):
        """
        By default, boxed part items do no support overriding the detail level, hence this method does nothing
        when called. Derived classes that support it must override this method to take appropriate action based
        on the given arguments.
        :param detail_level_override: the enum indicating the override mode

        Note: "overriding" the detail level refers to the feature that allows all content part items to be
        shown as minimal or full detail level regardless of their individual settings.
        """
        pass

    def can_be_pasted(self) -> bool:
        """
        By default, every type can be cut/copy/pasted. Override this to return False for parts where this is not
        always the case.
        """
        return True

    @override_optional
    def open_editor(self):
        """Open the editor for this type of part. Only override if an editor is registered for this item."""
        raise NotImplementedError

    def put_menu_actions(self, menu: QMenu):
        """Put the actions for this object in the given menu"""
        actions = self._get_menu_actions()

        # Add all other actions in reverse order to the main context menu
        for action in reversed(actions):
            if isinstance(action, QMenu):
                menu.addMenu(action)
            else:
                menu.addAction(action)

    @override_optional
    def _disconnect_all_slots(self):
        pass

    @override_required
    def _get_menu_actions(self) -> MenuActions:
        """
        Derived class must provide a list of actions specific to this item (not include actions from children items).
        Several actions may be grouped into a QMenu. Example:

            [action1, action2, menu1, action3, menu2]
        """
        raise NotImplementedError


class WidgetProxyPartItem(IBoxedPartItem, QGraphicsProxyWidget):
    """
    Every PartWidget gets put in a proxy that satisfies the IBoxedPartItem API.
    """

    def __init__(self, parent: QGraphicsItem, widget: IPartWidget):
        IBoxedPartItem.__init__(self)
        QGraphicsProxyWidget.__init__(self, parent)
        assert isinstance(widget, IPartWidget)
        self.setWidget(widget)
        self.geometryChanged.connect(self.sig_boxed_item_size_changed)
        self.setOpacity(QTBUG_55918_OPACITY)  # QTBUG-55918

    @override(IBoxedPartItem)
    def populate_data(self):
        """
        Forwards the call to the contained widget.
        """
        self.widget().populate_data()

    @override(QGraphicsProxyWidget)
    def type(self) -> int:
        return CustomItemEnum.widget_proxy.value

    @override(IBoxedPartItem)
    def override_detail_level(self, detail_level_override: DetailLevelOverrideEnum):
        self.widget().override_detail_level(detail_level_override)

    @override(IBoxedPartItem)
    def get_size(self):
        return self.widget().size()

    @override(IBoxedPartItem)
    def _get_menu_actions(self) -> MenuActions:
        actions = [action for action in self.widget().findChildren(QAction) if action.parent() is self.widget()]
        return actions

    @override(IBoxedPartItem)
    def get_selection_margins(self) -> QMarginsF:
        """
        Delegates the call to the inner widget.
        :return: The return value from the inner widget which must honour the get_selection_margins()
        """
        return self.widget().get_selection_margins()

    @override(IBoxedPartItem)
    def get_proximity_margins(self) -> QMarginsF:
        """
        Delegates the call to the inner widget.
        :return: The return value from the inner widget which must honour the get_proximity_margins()
        """
        return self.widget().get_proximity_margins()

    @override(IBoxedPartItem)
    def _disconnect_all_slots(self):
        self.widget()._disconnect_all_slots()
        disconnect_all_slots_children(self.widget())


class FramelessPartItem(IBoxedPartItem, AlertIndicator, QGraphicsObject):
    """
    All scenario parts that do now show their part frame derive from this class: they are QGraphicsObjects
    that satisfy the IBoxedPartItem API so they can be put in the PartBoxItem.
    """

    icon_size_pix = 50

    # noinspection PyUnresolvedReferences
    def __init__(self, part: BasePart, parent_part_box_item: PartBoxItem = None):
        """
        :param part the BasePart of this graphics object.
        :param parent: the parent graphics object.
        """
        IBoxedPartItem.__init__(self)
        QGraphicsObject.__init__(self, parent_part_box_item)
        AlertIndicator.__init__(self, part, parent_part_box_item)
        self.__initialized = False

        self._part = part
        self._parent_part_box_item = parent_part_box_item
        part_frame = part.part_frame
        self.setObjectName(part_frame.name)
        self._icon_size = QSize(FramelessPartItem.icon_size_pix, FramelessPartItem.icon_size_pix)
        self.prepareGeometryChange()

        def __get_initial_state() -> Tuple[float, float]:
            size = part.part_frame.get_size()
            return size.width, size.height

        def __init_values_from_part(width: float, height: float):
            self._icon_size = QSize(int(width * SCALE_FACTOR), int(height * SCALE_FACTOR))
            self.prepareGeometryChange()

        AsyncRequest.call(__get_initial_state, response_cb=self.set_size)

        # Connect to back-end signals
        part_frame.signals.sig_part_frame_size_changed.connect(self.slot_set_size)

    @override(IBoxedPartItem)
    def get_selection_margins(self) -> QMarginsF:
        """
        When this item has an ifx bar, the selection area must be bigger; otherwise, smaller. This functions returns
        suitable margins, depending on whether the underlying part is an ifx part or not.
        :return: The margins that reflect the presence or absence of the ifx bar.
        """
        margins = QMarginsF(IBoxedPartItem.get_selection_margins(self))
        if self._part.is_ifx_part:
            # The width of frameless widgets tends to be smaller than that of the interface bar. So, we make
            # some adjustments to make them look better.
            adjusted_width = max(self._icon_size.width(), IfxBarTrayItem.IFX_BAR_WIDTH_MIN)
            extra = (adjusted_width - self._icon_size.width()) / 2

            margins.setLeft(margins.left() + extra)
            margins.setRight(margins.right() + extra)

        return margins

    @override(IBoxedPartItem)
    def get_proximity_margins(self) -> QMarginsF:
        """
        When this item has an ifx bar, the proximity area must be bigger; otherwise, smaller. This functions returns
        suitable margins, depending on whether the underlying part is an ifx part or not.
        :return: The margins that reflect the presence or absence of the ifx bar.
        """
        margins = QMarginsF(IBoxedPartItem.get_proximity_margins(self))
        if self._part.is_ifx_part:
            # The width of frameless widgets tends to be smaller than that of the interface bar. So, we make
            # some adjustments to make them look better.
            adjusted_width = max(self._icon_size.width(), IfxBarTrayItem.IFX_BAR_WIDTH_MIN)
            extra = (adjusted_width - self._icon_size.width()) / 2

            margins.setLeft(margins.left() + extra)
            margins.setRight(margins.right() + extra)

        return margins

    @override(IBoxedPartItem)
    def get_display_width(self) -> int:
        adjusted_width = IBoxedPartItem.get_display_width(self)
        if self._part.is_ifx_part:
            adjusted_width = max(adjusted_width, IfxBarTrayItem.IFX_BAR_WIDTH_MIN)

        return adjusted_width

    def init_boxed_part_item(self, _):
        """
        Connects sig_boxed_item_size_changed and returns self. Note: This function is introduced to satisfy the
        duck typing techniques - the init_boxed_part_item is also defined in the IPartWidget.
        :return: the self
        """
        assert self.__initialized is False
        self.sig_boxed_item_size_changed.connect(self._parent_part_box_item.slot_on_size_changed)
        self.__initialized = True
        return self

    @override(QGraphicsItem)
    def boundingRect(self) -> QRectF:
        """
        Defines the outer bounds of the item as a rectangle; all painting must be restricted to inside an item's
        bounding rect.
        :return: a simple rectangle that defines the item boundaries.
        """
        return QRectF(0, 0, self._icon_size.width(), self._icon_size.height())

    def highlight(self, is_selected: bool):
        """
        Sets the highlight attribute on the parent (part item) of this object when selected.
        :param is_selected: a flag that indicates this item has been selected.
        """
        raise RuntimeError('why is this called')
        parent = self.parentObject()
        parent.highlight(is_selected)

    @override(IBoxedPartItem)
    def get_size(self):
        return self.boundingRect().size()

    def set_size(self, width: float, height: float):
        """
        Set size based on backend value .
        :param width: the 2D part's horizontal dimension.
        :param height: the 2D part's vertical dimension.
        """
        self.prepareGeometryChange()
        self._icon_size = QSize(int(width * SCALE_FACTOR), int(height * SCALE_FACTOR))
        self.prepareGeometryChange()
        self.sig_boxed_item_size_changed.emit()

    slot_set_size = safe_slot(set_size)

    @override(IBoxedPartItem)
    def _get_menu_actions(self) -> MenuActions:
        actions = [action for action in self.findChildren(QAction) if action.parent() is self]
        return actions

    @override(IBoxedPartItem)
    def _disconnect_all_slots(self):
        try_disconnect(self.sig_boxed_item_size_changed, self._parent_part_box_item.slot_on_size_changed)
        try_disconnect(self._part.part_frame.signals.sig_part_frame_size_changed, self.slot_set_size)
