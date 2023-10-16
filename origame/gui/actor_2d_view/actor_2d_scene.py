# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Actor 2D scene components

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from weakref import WeakKeyDictionary
from enum import IntEnum, unique

# [2. third-party]
from PyQt5.QtCore import Qt, pyqtSignal, QPointF, QRectF, QTimer
from PyQt5.QtWidgets import QGraphicsObject, QGraphicsView
from PyQt5.QtWidgets import QMessageBox, QGraphicsScene, QGraphicsSceneMouseEvent, QGraphicsItem, qApp
from PyQt5.QtGui import QKeyEvent, QCursor, QTransform, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer

# [3. local]
from ...core import override, BaseFsmState, IFsmOwner, plural_if, override_optional
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...scenario.defn_parts import BasePart, ActorPart, PartLink, LinkWaypoint, Position
from ...scenario.alerts import IScenAlertSource

from ..async_methods import AsyncRequest
from ..gui_utils import exec_modal_dialog, get_icon_path
from ..conversions import map_to_scenario
from ..safe_slot import safe_slot, ext_safe_slot
from ..undo_manager import scene_undo_stack, AddPartCommand, RemovePartsCommand, RemoveWaypointsCommand
from ..undo_manager import PartsPositionsCommand, ParentProxyPositionCommand, WaypointPositionCommand
from ..undo_manager import CreateLinkCommand, RetargetLinkCommand
from ..slow_tasks import ProgressRange

# WARNING: frameless_parts_items and part_widgets modules need to register inner part item types before
# first PartBoxItem is created:
from .frameless_parts_items import register_part_item_class  # DO NOT REMOVE
from .framed_part_widgets import register_part_item_class  # DO NOT REMOVE
from .frameless_part_widgets import register_part_item_class  # DO NOT REMOVE

from .part_box_item import PartBoxItem
from .part_box_side_items import IfxPortItem
from .linking import LinkAnchorItem, LinkSceneObject, LinkCreationStatusEnum, LinkSegmentItem
from .linking import PartLinkTargetSelLineItem, PartLinkTargetMarkerItem, WaypointMarkerItem
from .common import DetailLevelOverrideEnum, CustomItemEnum, IInteractiveItem, ZLevelsEnum, EventStr
from .parent_actor_proxy_item import ParentActorProxyItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # defines module members that are public; one line per string
    'Actor2dPanel'
]

log = logging.getLogger('system')

# The intent is to have consistent height for all the title bars.
DEFAULT_TITLE_BAR_HEIGHT = 20


class Decl(AnnotationDeclarations):
    Actor2dScene = 'Actor2dScene'


# -- Function definitions -----------------------------------------------------------------------

def check_items_type(items: List[QGraphicsItem], item_type: CustomItemEnum) -> bool:
    """Returns True if all items in given list are of type item_type, False otherwise"""
    return [1 for item in items if item.type() != item_type] == []


def handle_mouse_move_event(event: QGraphicsSceneMouseEvent) -> bool:
    """
    Determine if should handle a mouse move event.
    :param event: the event to check
    :return: True if should handle the event, False otherwise
    """
    if event.modifiers() != Qt.NoModifier:
        # there is a modifier, so doesn't matter what mouse button (if any) is pressed, we will not handle it.
        # HOWEVER before return False: the scene's View seems to treat Ctrl and Alt modifiers specially, so
        # when these are pressed during mouse motion, we need to gobble them up so they are not used by the scene:
        event.accept()
        return False

    # warning: event.button() always returns 0! only event.buttons() works
    left_button = bool(event.buttons() & Qt.LeftButton)
    if left_button:
        event.accept()
        return True

    # no modifiers, non-left (or no) button so we do NOT accept the event: we want the scene to handle the
    # event according to its default (super()) handler:
    return False


def check_item_has_selectability_flag(item: QGraphicsItem) -> QGraphicsItem:
    """
    Check that item has its selectability flag set. If yes, returns the item, else returns the closest
    ancestor item that its selectability flag set, or None if none found. Note "selectability" is not the
    same as "selectable":

    - "selectability" refers to whether an item could ever be selectable. If False, the item can never be
      selected, regardless of scene state. If True, the item could be selectable in some scene states.
      For example the event indicator on a part does not have its
      selectability flag set to true, so it can never be selectable (and hence selected).
    - "selectable" refers to whether the user can select an item. This is affected by both the scene state and
      the selectability flag of the item. For example, a waypoint is selectable while there are no other
      types of items selected.

    :param item: the item to check for selectability
    :return: item if item has its selectability flag set; otherwise, the nearest ancestor item of item that
        has its selectability flag set
    """

    def has_selectability_flag(item):
        return bool(item.flags() & QGraphicsItem.ItemIsSelectable)

    while item is not None and not has_selectability_flag(item):
        item = item.parentItem()

    return item


def new_cursor_from_svg_path(svg_image_path: str, width: int, height: int) -> QCursor:
    """
    Create a new QCursor from a path to an SVG file. Can only be called after the QApplication has been created.
    :param svg_image_path: path to an SVG file holder image for cursor
    :return: QCursor instance
    """
    assert qApp.instance() is not None
    cursor_pixmap = QPixmap(width, height)
    cursor_painter = QPainter(cursor_pixmap)
    svg_renderer = QSvgRenderer(svg_image_path)
    svg_renderer.render(cursor_painter)
    return QCursor(cursor_pixmap)


# -- Class Definitions --------------------------------------------------------------------------

@unique
class SceneStatesEnum(IntEnum):
    idle = 0
    item_selected, many_parts_selected, many_waypoints_selected = range(1, 4)
    interact_scene_obj, default_scene_interact = range(5, 7)
    creating_link, retargeting_link = range(10, 12)
    moving_parts, moving_proxy, moving_waypoints, rubber_banding, click_delete = range(20, 25)


class IfxPortItemsTracker:
    """
    Track the ifx port items that get added to the scene, so that they can be navigated to.
    In some circumstances, the ifx port item does not yet exist when the request arrives to
    navigate to it. This can happen when the request is initiated from another actor, and the
    actor that must show the ifx port has never been visited: the ifx port item to be selected
    does not yet exist at the time the scene is created (because the scene creates all the
    part items immediately, but each child actor that has ports to show must make an async
    request to get the ports).
    """
    RETRY_SEL_ITEM_INTERVAL_MSEC = 100

    def __init__(self):
        self.__selection_timer = QTimer()
        self.__selection_timer.timeout.connect(self.__try_select_pending)
        # Map ID of each interface port of content actor to its associated graphics item
        self.__map_ifx_ports_to_items = {}
        self.__pending_selection_id = None

    def add_port_item(self, port_item: IfxPortItem):
        """Track given ifx port item for given part session ID"""
        port_id = port_item.get_part_id()
        self.__map_ifx_ports_to_items[port_id] = port_item

    def get_existing_item(self, part: BasePart) -> Optional[IfxPortItem]:
        """Get ifx port item for given part. Returns None if no ifx port item being tracked for given part."""
        return self.__map_ifx_ports_to_items.get(part.SESSION_ID)

    def request_selection(self, ifx_port: BasePart):
        """
        Request that the ifx port item for the given part be selected. If there is no such item already
        in existence, the selection will be repeatedly attempted until it becomes available, or the request
        is cancelled, whichever comes first.
        """
        ifx_port_session_id = ifx_port.SESSION_ID
        assert ifx_port_session_id is not None
        if not self.__try_select(ifx_port_session_id):
            log.debug("Selection request for ifx port {} will be tried again in {} ms",
                      ifx_port, self.RETRY_SEL_ITEM_INTERVAL_MSEC)
            self.__pending_selection_id = ifx_port_session_id
            self.__selection_timer.start(self.RETRY_SEL_ITEM_INTERVAL_MSEC)

    def abandon_selection_request(self):
        """Cancel any pending selection request"""
        self.__selection_timer.stop()
        if self.__pending_selection_id is not None:
            log.debug("Pending selection of ifx port item for part ID={} abandoned", self.__pending_selection_id)
            self.__pending_selection_id = None

    def has_pending_selection_request(self) -> bool:
        """Returns True if this tracker has a pending selection request"""
        return self.__pending_selection_id is not None

    def reset(self):
        """Abandon any existing pending selection and clear the tracking map"""
        self.abandon_selection_request()
        self.__map_ifx_ports_to_items.clear()
        assert self.__pending_selection_id is None

    def cleanup_item(self, item: IfxPortItem):
        """Stop tracking ifx port item; if item already not tracked, do nothing."""
        part_id = item.get_part_id()
        if self.__pending_selection_id == part_id:
            self.abandon_selection_request()
        self.__map_ifx_ports_to_items.pop(part_id, None)

    def __try_select(self, ifx_port_id: int) -> bool:
        if ifx_port_id not in self.__map_ifx_ports_to_items:
            log.debug("Selection of ifx port item for part ID={} not possible YET", ifx_port_id)
            return False

        log.debug("Selecting ifx port item for part ID={}", ifx_port_id)
        self.abandon_selection_request()
        ifx_port_item = self.__map_ifx_ports_to_items[ifx_port_id]
        ifx_port_item.scene().set_selection(ifx_port_item)
        return True

    def __try_select_pending(self):
        assert self.__pending_selection_id is not None  # because the timer should have been cancelled when pending ID removed
        if self.__pending_selection_id not in self.__map_ifx_ports_to_items:
            log.debug("Selection of ifx port item for part ID={} STILL not possible", self.__pending_selection_id)
            return

        log.debug("Selecting ifx port item for part ID={} (FINALLY)", self.__pending_selection_id)
        # the setSelected(True) line will cause immediate change of selection, which will cause
        # abandon_selection_request() to be called, at which point we want the pending selection ID to be None,
        # so save it and set it to None BEFORE changing selection:
        key_id = self.__pending_selection_id
        self.__pending_selection_id = None
        self.__selection_timer.stop()
        ifx_port_item = self.__map_ifx_ports_to_items[key_id]
        ifx_port_item.scene().set_selection(ifx_port_item)


class Actor2dScene(IFsmOwner, QGraphicsScene):
    """
    Populates its scene based on the UiScenarioDefn or the UIActorScene - TBD.
    """
    sig_part_selection_changed = pyqtSignal(list)  # list of BasePart
    sig_nav_to_actor = pyqtSignal(ActorPart)
    sig_update_context_help = pyqtSignal(BasePart)
    sig_reset_context_help = pyqtSignal()
    sig_filter_events_for_part = pyqtSignal(BasePart)
    # sig_part_added is needed because the view(s) must adjust the scene extents after the scene has successfully
    # added a part. The view(s) connecting to the backend actor.signals.sig_child_added won't work because the
    # slot execution order is important and we don't want to rely on the Qt's execution order.
    sig_part_added = pyqtSignal(BasePart)  # part added
    sig_child_part_moved = pyqtSignal()
    sig_open_part_editor = pyqtSignal(BasePart)  # part to edit
    sig_show_child_part = pyqtSignal(BasePart)  # child part to show (in its parent)
    # child actor to show (in its parent), and ifx port (of descendant) to show
    sig_show_ifx_port = pyqtSignal(ActorPart, BasePart)
    sig_alert_source_selected = pyqtSignal(IScenAlertSource)

    def __init__(self, content_actor: ActorPart, children: List[BasePart], center: Position = None,
                 zoom_factor: float = None):
        """
        :param content_actor: which actor to represent the contents of
        :param children: children of the actor
        :param center: initial center position (or None if View will determine)
        :param zoom_factor: initial zoom factor (or None if View will determine)
        :return:
        """
        IFsmOwner.__init__(self)
        QGraphicsScene.__init__(self)

        self.__content_actor = content_actor
        content_actor.signals.sig_child_added.connect(self.slot_on_part_added)
        content_actor.signals.sig_child_deleted.connect(self.slot_on_part_removed)
        content_actor.signals.sig_parts_copied.connect(self.__slot_on_parts_copied)
        content_actor.signals.sig_parts_restored.connect(self.__slot_on_parts_restored)
        content_actor.signals.sig_waypoints_restored.connect(self.__slot_on_waypoints_restored)

        # Create the default item - the parent proxy
        self.__parent_proxy_item = ParentActorProxyItem(content_actor)
        self.addItem(self.__parent_proxy_item)

        # Map ID of each child part of content actor to its associated graphics item
        self.__map_child_parts_to_items = {}
        self.__ifx_port_items_tracker = IfxPortItemsTracker()

        self.__detail_level_override = DetailLevelOverrideEnum.none
        self.__view_rect = None
        self.selectionChanged.connect(self.__slot_on_selection_changed)
        #  Set by view so view can be restored when re-activate scene:
        self.__view_center = center  # Position object
        self.__zoom_factor = zoom_factor  # Float

        # first create all the part items:
        self.__link_objs = WeakKeyDictionary()
        self.__create_scenario_items(children)

        # We need to maintain this state because it is needed when a new part is created.
        self._state = SceneStateIdle(None, fsm_owner=self)

    @override(QGraphicsScene)
    def keyPressEvent(self, event: QKeyEvent):
        """Handle key press events depending on the scene's state"""
        if log.isEnabledFor(logging.DEBUG):
            log.debug("Scene for {} got key press: {}", self.__content_actor, EventStr(event))
        event.setAccepted(False)  # Init event acceptance before state processing
        self._state.key_pressed(event)
        if not event.isAccepted():
            super().keyPressEvent(event)

    @override(QGraphicsScene)
    def keyReleaseEvent(self, event: QKeyEvent):
        """Handle key release events depending on scene's state"""
        if log.isEnabledFor(logging.DEBUG):
            log.debug("Scene for {} got key release: {}", self.__content_actor, EventStr(event))
        event.setAccepted(False)  # Init event acceptance before state processing
        self._state.key_released(event)
        if not event.isAccepted():
            super().keyReleaseEvent(event)

    @override(QGraphicsScene)
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse press depending on the scene's state"""
        log.debug("Scene for {} got mouse press: {}", self.__content_actor, EventStr(event))
        item_under_mouse = self.itemAt(event.scenePos(), QTransform())
        if item_under_mouse is not None:
            log.debug("   Item under mouse click is: {}", item_under_mouse)

        self._state.mouse_pressed(event)
        if not event.isAccepted():
            log.debug("Letting scene base deal with mouse press event")
            super().mousePressEvent(event)

    @override(QGraphicsScene)
    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        """
        Handle mouse motion depending on the scene's state. NOTE: this method does not get called when the
        mouse is over the canvas and the view is in "grab" mode.
        """
        self._state.mouse_moved(event)
        if not event.isAccepted():
            # log.debug("Letting scene base deal with mouse move event")
            super().mouseMoveEvent(event)

    @override(QGraphicsScene)
    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        """Handle mouse release depending on the scene's state"""
        log.debug("Scene for {} got mouse release", self.__content_actor)
        self._state.mouse_released(event)
        if not event.isAccepted():
            log.debug("Letting scene base deal with mouse release event")
            super().mouseReleaseEvent(event)

    @override(QGraphicsScene)
    def addItem(self, item: QGraphicsItem):
        """Add the item to the scene. Raises ValueError if it was disposed of via dispose_item(item)."""
        if item.disposed:
            raise ValueError('Item {} has been disposed, cannot add!'.format(item))
        super().addItem(item)

    @override(QGraphicsScene)
    def removeItem(self, item: QGraphicsItem):
        """Remove the item from the scene. It can be re-added later."""
        self.__cleanup_maps(item)
        super().removeItem(item)

    @override(QGraphicsScene)
    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Overwrite this function so we can get and reuse the visible rect without compute manually every time"""
        self.__view_rect = rect

    def on_grobj_item_disposed(self, grobj_item: QGraphicsObject):
        """
        Anytime an item that derives from QGraphicsObject is disposed of, it must notify the scene so proper
        cleanup can be done, such as removing it from maps.
        """
        grobj_item.destroyed.connect(self.__on_destroyed_grobj)
        self.__cleanup_maps(grobj_item)

    def notify_viewing_change(self, state: bool):
        """
        Allow the scene to take action when it has been attached to a view or is about to be detached from a view.
        There is no builtin signal for this by QGraphicsView.
        :param state: True if Scene is about to be attached to a view; False if it is about to be detached.
        """
        if not state:
            # it can happen that we get a mouse release event after we have been detached from
            # a view; in this case, we have to set view back to correct state:
            view = self.get_main_view()
            if view and (view.is_cursor_overridden() or view.is_rubberband_mode()):
                view.set_cursor_default()

    def shutdown(self):
        """
        Completely clear everything from the scene: link items, part items, all child items (event indicators etc).
        """
        self.view.on_scene_cleared()

        for part_link, link_item in self.__link_objs.items():
            link_item.on_part_link_removed()
        self.__link_objs = WeakKeyDictionary()

        # WARNING: super().clear() deletes the items, which is not good: must let Python GC decide when
        child_part_items = list(self.__map_child_parts_to_items.values())
        for item in child_part_items:
            # remove it, if still in scene (might have been removed as result of previous steps)
            if item.scene() is not None:
                self.__remove_child_part_item(item.part.SESSION_ID)

        self.__map_child_parts_to_items = {}
        self.__ifx_port_items_tracker.reset()

        self.__parent_proxy_item = None
        self.__content_actor = None

    def override_detail_level(self, detail_level_override: DetailLevelOverrideEnum):
        """
        Override the detail level of each part in the scene.
        :param detail_level_override: The detail level override to be applied to each inner item.
        """
        assert detail_level_override in DetailLevelOverrideEnum

        for item in self.get_child_part_items():
            assert item.inner_item.isVisible()
            item.inner_item.override_detail_level(detail_level_override)

        self.__detail_level_override = detail_level_override

    def get_view_center_2d(self) -> Position:
        """
        Get the actor part view's current center position. This value is set to None by default, but is
        updated at runtime to reflect the current view center associated with the Actor Part.
        """
        return self.__view_center

    def set_view_center_2d(self, pos: Position):
        """
        Set the actor part view's current center position. This value is set to None by default, but is
        updated at runtime to reflect the current view center associated with the Actor Part.
        """
        self.__view_center = pos

    def get_zoom_factor_2d(self) -> float:
        """
        Get the current zoom factor for the actor part's view. This value is set to None by default, but is
        updated at runtime to reflect the current zoom factor associated with the Actor Part.
        """
        return self.__zoom_factor

    def set_zoom_factor_2d(self, zoom: float):
        """
        Set the current zoom factor for the actor part's view. This value is set to None by default, but is
        updated at runtime to reflect the current zoom state associated with the Actor Part.
        """
        if self.__zoom_factor != zoom:
            self.__zoom_factor = zoom

    # ---------- P A R T   S E L E C T I O N -------------------------------------------------

    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        """
        Check if an item is selectable. If not selectable, the caller must refuse the selection request.
        :param item: the item to check
        :return: True if selectable, False otherwise
        """
        result = self._state.check_item_selectable(item)
        log.debug("Checked if item ({} for {}) is selectable: {} (scene state {})",
                  item, item.get_scenario_object(), result, self._state.state_id.name)
        return result

    def set_selection(self, item: QGraphicsItem):
        """Unselect all and select given part item."""
        selectable_item = check_item_has_selectability_flag(item)
        if selectable_item is None:
            raise ValueError("Item {} is not selectable, nor is any of its ancestor items", item)

        if selectable_item is not item:
            log.debug('Selecting ancestor {} instead of {}', selectable_item, item)

        if self.selectedItems() != [selectable_item]:
            self.clearSelection()
            selectable_item.setSelected(True)  # results in __on_selection_change() being called.

    def set_multi_selection(self, items: List[PartBoxItem] = None):
        """Unselect all and select given part items."""
        log.debug("Setting scene selection to {}", items)
        self.clearSelection()
        for item in items:
            item.setSelected(True)  # results in __on_selection_change() being called.

    def select_ifx_port_item(self, ifx_port: BasePart):
        """
        Select the ifx port item corresponding to a part.
        :param ifx_port: the scenario part that is assumed to be a descendant of an actor child of current scene`s
            actor. If the part does not yet exist, the request for selection will be postponed until the part
            item becomes visible, or a new selection is requested, whichever comes first.
        """
        self.__ifx_port_items_tracker.request_selection(ifx_port)

    def extend_selection(self, part_item: PartBoxItem):
        """
        Add the given part to current selection. If current selection is not parts, this call will be equivalent
        to unselecting everything and calling set_selection(), which may cause a state transition.
        """
        assert check_items_type(self.selectedItems(), CustomItemEnum.part)
        part_item.setSelected(True)
        assert check_items_type(self.selectedItems(), CustomItemEnum.part)

    def has_multipart_selection(self) -> bool:
        """Return True only if there are 2 or more parts selected"""
        return len(self.selectedItems()) > 1 and check_items_type(self.selectedItems(), CustomItemEnum.part)

    def has_part_selection(self) -> bool:
        """Return True only if there are 1 or more parts selected"""
        return bool(self.selectedItems()) and check_items_type(self.selectedItems(), CustomItemEnum.part)

    def has_waypoint_selection(self) -> bool:
        """Return True only if there is a waypoint selected"""
        return bool(self.selectedItems()) and check_items_type(self.selectedItems(), CustomItemEnum.waypoint)

    def has_link_selection(self) -> bool:
        """Return True only if there is a link selected"""
        return bool(self.selectedItems()) and check_items_type(self.selectedItems(), CustomItemEnum.link)

    def has_ifx_port_selection(self) -> bool:
        """
        Checks if ports are selected.
        :return: True if a port is selected.
        """
        return bool(self.selectedItems()) and check_items_type(self.selectedItems(),
                                                               CustomItemEnum.ifx_port)

    def has_selection(self) -> bool:
        """Return True if anything is selected"""
        return bool(self.selectedItems())

    def get_selected_objects(self) -> Either[List[BasePart], List[LinkWaypoint], List[PartLink]]:
        """
        Get the list of parts or waypoint currently selected.
        """
        if self.has_part_selection():

            assert check_items_type(self.selectedItems(), CustomItemEnum.part)
            selected_parts = [part_item.part for part_item in self.selectedItems()]
            # check no duplicate parts:
            assert len(set(selected_parts)) == len(selected_parts)
            return selected_parts

        elif self.has_waypoint_selection():

            assert check_items_type(self.selectedItems(), CustomItemEnum.waypoint)
            selected_waypoint = [waypoint_item.waypoint for waypoint_item in self.selectedItems()]
            return selected_waypoint

        elif self.has_link_selection():

            assert check_items_type(self.selectedItems(), CustomItemEnum.link)
            selected_link = [link_item.part_link for link_item in self.selectedItems()]
            return selected_link

        elif self.has_ifx_port_selection():

            assert check_items_type(self.selectedItems(), CustomItemEnum.ifx_port)
            selected_parts = [port_item.part_frame.part for port_item in self.selectedItems()]
            return selected_parts

        else:
            return []

    def get_part_selection_center_scenario(self) -> Position:
        """Convenience method for self.get_bounding_rect_center_scenario(self.selectedItems())"""
        assert self.has_part_selection()
        return self.get_bounding_rect_center_scenario(self.selectedItems())

    def check_any_selected_under_mouse(self) -> bool:
        """
        Return True if any of the currently selected items is under the mouse, False otherwise.
        """
        for item in self.selectedItems():
            if item.isUnderMouse():
                return True

        return False

    # ------------- C O N T E N T -------------------------------------------------------------

    def get_root_items(self) -> List[QGraphicsItem]:
        """Return True if anything is selected"""
        return [obj for obj in self.items() if obj.parentItem() is None]

    def get_bounding_rect_center_scenario(self, items: List[QGraphicsItem]) -> Position:
        """
        Get the center point of the bounding rectangle surrounding a group of graphics items.
        :param items: the items for which to get center point
        :return: the center point
        """

        # Construct a bounding rectangle around all selected items
        part_item = items[0]
        selection_rect = part_item.mapRectToScene(part_item.boundingRect())  # Init boundingRect with first item
        for part_item in items:
            # Add/group together the boundingRects of all selected items iteratively
            selection_rect = selection_rect.united(part_item.mapRectToScene(part_item.boundingRect()))

        selection_center = map_to_scenario(selection_rect.center())
        return selection_center

    def get_content_actor(self):
        """Returns the actor whose contents are currently visible in the scene"""
        return self.__content_actor

    def get_content_actor_proxy_item(self) -> ParentActorProxyItem:
        """Get the ParentActorProxyItem that represents the content actor"""
        return self.__parent_proxy_item

    def get_child_part_item(self, part: BasePart) -> PartBoxItem:
        """Get graphics item for given scenario part; raises KeyError if part not in scene."""
        return self.__map_child_parts_to_items[part.SESSION_ID]

    def get_child_part_items(self, subset: List[BasePart] = None) -> List[PartBoxItem]:
        """
        Get the list of all items of scene that are instances of PartBoxItem AND child of content actor. This does
        not include the content actor proxy item (see get_content_actor_proxy_item()).
        """
        if subset is None:
            return list(self.__map_child_parts_to_items.values())
        else:
            return [self.__map_child_parts_to_items[part.SESSION_ID] for part in subset]

    def get_link_obj(self, link: PartLink) -> LinkSceneObject:
        """
        Get the scene link object that represents the given PartLink.
        """
        return self.__link_objs[link]

    def get_num_link_objs(self) -> int:
        """
        Get the number of link objects in the scene (one link object manages multiple link segments and
        represents one PartLink).
        """
        return len(self.__link_objs)

    def get_link_segment_item(self, link_num: int, segment_num: int) -> LinkSegmentItem:
        """
        Get a specific segment of a specific link.
        """
        # Colin FIXME ASAP: Change this method so it takes a part and link name instead of link number
        #     Reason: no time to do this before Apr 26th release
        return list(self.__link_objs.values())[link_num].segment_items[segment_num]

    def request_part_creation(self, part_type: str, pos: Position):
        """
        Request that the scenario create a new part.
        :param part_type: type of part to create
        :param pos: position of new part
        """
        log.debug("Creation of new part of type '{}', as pos={:.5}, requested on graphics scene", part_type, pos)
        actor = self.__content_actor
        add_command = AddPartCommand(actor, part_type, pos)
        scene_undo_stack().push(add_command)

    def on_child_part_added(self, child_part: BasePart):
        """
        When the content actor has created a new child part, create a PartBoxItem for, and a LinkSceneObject for each of
        its outgoing links.

        :param child_part: the part that was added as child of this scene's actor part
        """
        assert child_part.SESSION_ID not in self.__map_child_parts_to_items
        item = self.__create_child_part_item(child_part)
        if item is not None:
            self.__create_outgoing_links(item)
            self.__create_incoming_links(item)
            item.inner_item.override_detail_level(self.__detail_level_override)

            self.sig_part_added.emit(child_part)

        # This single shot allows the Qt to show the item before its content is populated.
        # Note: this approach does not work if the time consuming content population is GIL-related.
        QTimer.singleShot(0, item.inner_item.populate_data)

    def on_child_part_removed(self, part_id: int):
        """
        When the scenario has removed a part, remove the associated part's item from scene. This only handles the
        case where the part's item is represented as a child item.
        """
        if self._state.state_id == SceneStatesEnum.creating_link:
            self._state.cancel_link_creation()

        if self._state.state_id == SceneStatesEnum.retargeting_link:
            self._state.cancel_link_retarget()

        self.__remove_child_part_item(part_id)
        self.sig_reset_context_help.emit()

    def on_part_link_added(self, from_item: PartBoxItem, link: PartLink):
        """
        When a link is added to scenario by backend, add a visual representation of it in the scene.
        :param from_item: QGraphicsItem for the source part of the link
        :param link: the PartLink instance that was added to the scenario
        """
        target_anchor_item = self.__get_link_target_item(link)
        # target_anchor_item may be None if link removed (by backend, in separate thread) or target frame
        # is in another actor
        if target_anchor_item is not None:
            self.__create_new_link_item(link, from_item, target_anchor_item)

    def on_part_link_removed(self, link_id: int, link_name: str):
        """
        When a link is removed from scenario by backend, remove the corresponding scene item for it.
        :param link_id: the session ID of the link that was removed.
        :param link_name: the name of the link that was removed.
        """
        for part_link, link_item in self.__link_objs.items():
            if part_link.SESSION_ID == link_id:
                assert link_item.part_link is part_link
                log.debug("Scene removing link {} (named '{}')", link_id, link_name)
                self.__link_objs.pop(part_link)
                link_item.on_part_link_removed()
                break

    def is_item_visible(self, item: IInteractiveItem) -> bool:
        """This function check if this item is visible on 2d view"""
        rect_item = item.get_highlight_rect()
        scene_item = item.mapRectToScene(rect_item)

        if self.__view_rect.intersects(scene_item):
            return True
        else:
            return False

    def on_ifx_port_added(self, port_item: IfxPortItem):
        """Let scene take action when an ifx port item has been added to it"""
        self.__ifx_port_items_tracker.add_port_item(port_item)
        self.__create_outgoing_links(port_item)
        self.__create_incoming_links(port_item)

    def delete_selected_parts(self):
        """Command the backend to delete the set of currently selected items, if the user confirms."""
        assert self.has_part_selection()

        items_invisible = False
        for part_item in self.selectedItems():
            if not self.is_item_visible(part_item):
                items_invisible = True
                break

        if items_invisible:
            part_names = ['"{}"'.format(part_item.part.name) for part_item in self.selectedItems()]
            msg = "Some items are not in view: {} part{} ({}). Click Yes to delete them anyways, " \
                  "or No to go back without deletion.".format(
                len(part_names), plural_if(self.selectedItems()), ', '.join(part_names))

            if exec_modal_dialog("Delete", msg, QMessageBox.Question) != QMessageBox.Yes:
                return

        cmd = RemovePartsCommand([part_item.part for part_item in self.selectedItems()])
        scene_undo_stack().push(cmd)

    def delete_selected_waypoints(self):
        """Command the backend to delete the set of currently selected waypoints, if the user confirms."""
        assert self.has_waypoint_selection()

        wpts_invisible = False
        for waypoint_item in self.selectedItems():
            if not self.is_item_visible(waypoint_item):
                wpts_invisible = True
                break

        if wpts_invisible:
            waypoint_names = ['"{}"'.format(waypoint_item.waypoint.wp_id) for waypoint_item in self.selectedItems()]
            msg = "Some waypoints are not in view: {} waypoint{} ({}). Click Yes to delete them anyways, " \
                  "or No to go back without deletion.".format(
                len(waypoint_names), plural_if(self.selectedItems()), ', '.join(waypoint_names))

            if exec_modal_dialog("Delete", msg, QMessageBox.Question) != QMessageBox.Yes:
                return

        map_links_to_waypoints = dict()

        for waypoint in self.selectedItems():
            selected_waypoints = map_links_to_waypoints.setdefault(waypoint.link_obj.part_link, [])
            selected_waypoints.append(waypoint.waypoint)

        cmd = RemoveWaypointsCommand(self.content_actor, map_links_to_waypoints)
        scene_undo_stack().push(cmd)

    def start_link_creation_from(self, link_anchor_item: LinkAnchorItem):
        """Start link creation from given item, assuming the state allows it"""
        self._state.start_link_creation(link_anchor_item)

    def get_is_creating_link(self) -> bool:
        """Returns true if currently creating a link, ie user is in process of selecting_one link target endpoint"""
        return self._state.state_id == SceneStatesEnum.creating_link

    def get_part_box_item(self, part: BasePart) -> Either[PartBoxItem, None]:
        """
        This function returns the PartBoxItem in the current scene that corresponds to the input
        part.
        :param part: A part to be associated with a PartBoxItem in the current scene.
        :return: The PartBoxItem associated with the input part, or None.
        """
        items = self.get_child_part_items()
        for item in items:
            if item.part is part:
                return item
        return None

    # ------------------ O T H E R ------------------------------------------------

    def start_link_retarget(self, part_link: PartLink,
                            from_item: LinkAnchorItem,
                            orig_source_item: LinkAnchorItem,
                            orig_target_item: LinkAnchorItem):
        self._state.start_link_retarget(part_link, from_item, orig_source_item, orig_target_item)

    def start_object_interaction(self, item: QGraphicsItem):
        """
        Must be called by a graphics item to tell scene to ignore all further mouse and key events, until
        next call to end_object_interaction(). Not all states support this.
        :param item: the item that user is going to interact with
        """
        self.set_selection(item)
        self._state.start_object_interaction()

    def end_object_interaction(self):
        """
        Must be called by a graphics item to tell scene to resume handling mouse and keyboard events.
        Only the SceneStateObjInteraction state support this.
        """
        self._state.end_object_interaction()

    def show_filtered_events(self, filter_part: BasePart):
        """
        Method called when the events in the Simulation Event Queue Panel are to be filtered on a given filter_part.
        :param filter_part: The part to filter the events on.  only events related to the filter_part will be shown in
        the Simulation Event Queue Panel.
        """
        self.sig_filter_events_for_part.emit(filter_part)

    def open_part_editor(self, part: BasePart):
        """Called by children part items when the part editor should be opened"""
        self.sig_open_part_editor.emit(part)

    def find_link_endpoint_item(self, part: BasePart) -> PartBoxItem:
        """
        Find the PartBoxItem for a given part, a child of self.__content_actor
        :param part: the part to look for in the cache
        """
        item = None

        # First see if the part is the root actor
        if part is self.content_actor:
            item = self.__parent_proxy_item

        # else consult the cache for all part items of this scene for given part:
        if item is None:
            item = self.__map_child_parts_to_items.get(part.SESSION_ID)

        # else look in the cache for all interface port items
        if item is None:
            item = self.__ifx_port_items_tracker.get_existing_item(part)

        return item

    def get_main_view(self) -> Optional[QGraphicsView]:
        """
        Return the main view of the application.
        :return: The View object that is showing this scene. None if scene not currently visible in any view.
        """
        views = self.views()
        return views[0] if views else None  # zero index since only one view in the app

    slot_on_part_added = ext_safe_slot(on_child_part_added)
    slot_on_part_removed = safe_slot(on_child_part_removed)

    is_creating_link = property(get_is_creating_link)
    content_actor = property(get_content_actor)
    view_center_2d = property(get_view_center_2d, set_view_center_2d)
    zoom_factor_2d = property(get_zoom_factor_2d, set_zoom_factor_2d)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __cleanup_maps(self, item: QGraphicsItem):
        # remove from maps, but do nothing if not in any map:
        try:
            self.__map_child_parts_to_items.pop(item.get_part_id(), None)
            self.__ifx_port_items_tracker.cleanup_item(item)
        except AttributeError:
            # it is not an item that has a scenario part id, nothing to do
            pass

    def __create_scenario_items(self, children: List[BasePart]):
        """
        Create scenario items to represent the actor contents. This will show a progress bar
        if the operation takes more than a split second.
        :param children: a list of children BaseParts of parent_actor.
        """
        with ProgressRange('Rendering', max_value=len(children)) as progress:
            child_items = []
            for count, child in enumerate(children):
                child_item = self.__create_child_part_item(child)
                child_items.append(child_item)
                progress.set_progress_value(count + 1)

            # now link them:
            for count, child_item in enumerate(child_items):
                if child_item is not None:
                    self.__create_outgoing_links(child_item)
                    progress.set_progress_value(count + 1)

            def __populate_data():
                for item in child_items:
                    item.inner_item.populate_data()

            # This single shot is needed to make the Qt render the items as soon as possible.
            QTimer.singleShot(0, __populate_data)

    def __create_outgoing_links(self, from_item: LinkAnchorItem):
        """
        Create PartLink2dItems for each outgoing link that has its origin at from_item. Note that this method is
        recursive because an item may have children items that also have outgoing links.
        :param from_item: origin item for which to create outgoing link items
        """
        from_frame_part = from_item.part_frame

        # NOTE that the from_item might might have been disposed, or the from_frame_part might have been suspended
        # and the from_item doesn't know yet, but just continue as if all was good and deal with the
        # situation when the links are obtained by checking from_item.disposed()

        def create_link_items(part_links: List[PartLink]):
            if from_item.disposed:
                return

            for part_link in part_links:
                target_item = self.__get_link_target_item(part_link)
                if target_item is not None:
                    self.__create_new_link_item(part_link, from_item, target_item)

        AsyncRequest.call(lambda: list(from_frame_part.outgoing_links), response_cb=create_link_items)
        for child_item in from_item.get_children_anchor_items():
            self.__create_outgoing_links(child_item)

    def __create_incoming_links(self, target_item: LinkAnchorItem):
        """
        Create the incoming links to a part. This is only needed because some link endpoint items (like
        interface ports) get created later, after part item that they are associated with.
        :param target_item: the item for which incoming links should be created.
        """
        # assert target_item.part.parent_actor_part is not self.__content_actor
        target_part_frame = target_item.part_frame

        def create_link_items(part_links: List[PartLink]):
            for part_link in part_links:
                from_item = self.__get_link_origin_item(part_link)
                if from_item is not None:
                    self.__create_new_link_item(part_link, from_item, target_item, outgoing=False)

        AsyncRequest.call(lambda: list(target_part_frame.incoming_links), response_cb=create_link_items)

    def __get_link_target_item(self, part_link: PartLink) -> Either[PartBoxItem, ParentActorProxyItem]:
        """
        Get the part item that is target of a part link. Returns None if not found.
        """
        if part_link.target_part_frame is None:
            return None

        target_part = part_link.target_part_frame.part
        if target_part is self.__content_actor:
            # target is parent proxy:
            return self.__parent_proxy_item

        return self.find_link_endpoint_item(target_part)

    def __get_link_origin_item(self, part_link: PartLink) -> PartBoxItem:
        """
        Get the part item that is origin of a part link. Returns None if not found.
        """
        if part_link.source_part_frame is None:
            return None

        from_part = part_link.source_part_frame.part
        return self.find_link_endpoint_item(from_part)

    def __create_child_part_item(self, part: BasePart) -> PartBoxItem:
        """
        Creates a PartBoxItem for this part.
        :return: the PartBoxItem corresponding to the part, or None if nothing created
        """
        assert part.SESSION_ID not in self.__map_child_parts_to_items

        if not part.in_scenario:
            # this is possible because backend is in separate thread, might have removed part between time it
            # added it and time this signal was received; but to keep things simple, we continue to process
            # the part as though it was still in scenario:
            log.warning('Scene adding child part {} that is no longer in scenario', part)

        if part.parent_actor_part is not self.__content_actor:
            log.warning('Scene adding child part {} that is no longer child of {}', part, self.__content_actor)

        item = PartBoxItem(part)
        assert item.part is part

        self.__map_child_parts_to_items[part.SESSION_ID] = item
        self.addItem(item)

        item.xChanged.connect(self.sig_child_part_moved)
        item.yChanged.connect(self.sig_child_part_moved)
        item.zChanged.connect(self.sig_child_part_moved)

        log.debug("Scene adding child part item #{} for part {}", item.ITEM_ID, part)
        return item

    def __remove_child_part_item(self, part_id: int):
        """
        Removes the graphics item for given child part.
        :param part_id: the session ID of the part being removed
        """
        assert part_id in self.__map_child_parts_to_items
        part_box_item = self.__map_child_parts_to_items.pop(part_id)
        child_part = part_box_item.part
        log.debug("Scene removing child part item #{} for part {}", part_box_item.ITEM_ID, child_part)

        assert part_box_item.scene() is not None
        part_box_item.xChanged.disconnect()
        part_box_item.yChanged.disconnect()
        part_box_item.zChanged.disconnect()
        part_box_item.dispose()

    def __on_destroyed_grobj(self, qobject: QGraphicsObject):
        log.debug("Qt destroying QGraphicsObject with id={} called '{}'", id(qobject), qobject.objectName())

    def __create_new_link_item(self, link: PartLink, from_item: LinkAnchorItem,
                               target_item: LinkAnchorItem, outgoing: bool = True):
        """
        Create a link item in the scene.
        :param link: link for which to create item
        :param from_item: the origin link anchor *item* from which link is outgoing
        :param target_item: the target link anchor *item* to which link should link
        :param outgoing: used in the log message for which direction is this link (incoming or outgoing)
        """
        if link in self.__link_objs:
            # link has already been added, ignore
            return

        if from_item.disposed or target_item.disposed:
            # no longer relevant
            return

        if link.get_cca() is self.content_actor:
            link_dir = 'outgoing' if outgoing else 'incoming'
            log.debug("Scene adding {} link item for {}", link_dir, link)
            link_obj = LinkSceneObject(self, link, from_item, target_item)
            self.__link_objs[link] = link_obj
        else:
            log.debug("Link {} has a CCA that is not the current content actor; link not rendered.", link)

    def __on_selection_changed(self):
        """
        Emits a signal containing the part frames selected in the view when the selection changes.
        Augments the QGraphicsScene signal 'selectionChanged' to send the selected part frames.
        """
        self.__ifx_port_items_tracker.abandon_selection_request()
        self._state.selection_changed(self.selectedItems())
        self.sig_part_selection_changed.emit(self.get_selected_objects())
        log.debug("Selection updated: {}", ', '.join(str(item.get_scenario_object()) for item in self.selectedItems()))

    def __on_parts_copied(self, id_list: List[int]):
        """
        Highlights a list of the parts that have just been copied.
        :param id_list: The list of part ids just copied.
        """
        self.__highlight_parts(id_list)

    def __on_parts_restored(self, id_list: List[int]):
        """
        Highlights a list of the parts that have just been restored.
        :param id_list: The list of part ids just restored.
        """
        self.__highlight_parts(id_list)

    def __on_waypoints_restored(self, map_links_to_waypoints: Dict[PartLink, List[LinkWaypoint]]):
        """
        Highlights recently restored waypoints
        :param map_links_to_waypoints: A map containing a map of links and their associated waypoints
        """
        self.clearSelection()

        for link, waypoints in map_links_to_waypoints.items():
            link_item = self.__link_objs[link]
            for wp_item in link_item.waypoint_items:
                if wp_item.get_waypoint() in waypoints:
                    wp_item.setSelected(True)

    def __highlight_parts(self, ids: List[int]):
        """
        Highlights a list of the parts.

        :param ids: the list of part ids
        """
        for i, part_id in enumerate(ids):
            item = self.__map_child_parts_to_items.get(part_id)
            if i == 0:
                #  Start fresh when selecting the first element
                self.set_selection(item)
            else:
                #  Extend selection for the rest of the elements
                self.extend_selection(item)

    __slot_on_selection_changed = safe_slot(__on_selection_changed)
    __slot_on_parts_copied = ext_safe_slot(__on_parts_copied, arg_types=(list,))
    __slot_on_parts_restored = ext_safe_slot(__on_parts_restored, arg_types=(list,))
    __slot_on_waypoints_restored = ext_safe_slot(__on_waypoints_restored, arg_types=(dict,))


class SceneStateBase(BaseFsmState):
    """By default, states ignore mouse down/up/move"""

    @override_optional
    def key_pressed(self, event: QKeyEvent):
        """
        Called by FSM owner when keyPressEvent: ignore event by default.
        NOTE: Overrides must call event.accept() if they process the key press event.
        """
        pass

    @override_optional
    def key_released(self, event: QKeyEvent):
        """
        Called by FSM owner when keyReleaseEvent: ignore event by default.
        NOTE: Overrides must call event.accept() if they process the key release event.
        """
        pass

    @override_optional
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        """Called by FSM owner when mousePressEvent: ignore event by default"""
        pass

    @override_optional
    def mouse_moved(self, event: QGraphicsSceneMouseEvent):
        """Called by FSM owner when mouseMoveEvent: ignore event by default"""
        pass

    @override_optional
    def mouse_released(self, event: QGraphicsSceneMouseEvent):
        """Called by FSM owner when mouseReleaseEvent: ignore event by default"""
        pass

    @override_optional
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        """
        Called by FSM owner to verify if given item is selectable: must return True only if
        it is valid to select the item in the current state, False otherwise. Returns False by default.
        """
        self._unsupported_op('check_item_selectable')
        return False

    @override_optional
    def selection_changed(self, items: List[QGraphicsItem]):
        """Called by FSM owner whenever it detects a change in which items selected. Does nothing by default."""
        self._unsupported_op('selection_changed')

    @override_optional
    def start_link_creation(self, from_item: LinkAnchorItem):
        """Called by FSM owner to start link creation. Does nothing by default."""
        self._unsupported_op('start_link_creation')

    @override_optional
    def cancel_link_creation(self):
        """Called by FSM owner to cancel link creation. Does nothing by default."""
        self._unsupported_op('cancel_link_creation')

    @override_optional
    def cancel_link_retarget(self):
        """Called by FSM owner to cancel link retarget. Does nothing by default."""
        self._unsupported_op('cancel_link_retarget')

    @override_optional
    def start_link_retarget(self, part_link: PartLink,
                            from_item: QGraphicsItem,
                            orig_source_item: LinkAnchorItem,
                            orig_target_item: LinkAnchorItem):
        """Called by FSM owner to start link retargeting. Does nothing by default."""
        self._unsupported_op('start_link_retarget')

    @override_optional
    def start_object_interaction(self):
        """Called by FSM owner to indicate that interaction is with a scene object. Does nothing by default."""
        self._unsupported_op('start_object_interaction')

    def _check_click_delete(self, event: QKeyEvent, disallowed: str = None) -> bool:
        """
        Check if quick-deletion keys activated; if so, transition and return True; else, just return False.
        """
        if event.modifiers() != (Qt.ControlModifier | Qt.ShiftModifier):
            return False

        if disallowed is not None:
            assert disallowed  # reason cannot be empty string!
            log.warning('Click-delete is not supported: {}', disallowed)
            return False

        event.accept()
        self._set_state(SceneStateClickDelete)
        return True

    def _check_rubber_sel(self, event: QGraphicsSceneMouseEvent) -> bool:
        """
        Check if rubber-band selection has been activated; if so, transition and return True; else, just return False.
        """
        if event.modifiers() == Qt.ShiftModifier:
            # event.accept()
            self._set_state(SceneStateRubberBandSel)
            return True

        return False


class SceneStateIdle(SceneStateBase):
    """
    Nothing is selected, nothing is happening in scene (being moved by user, rubber banding, etc).
    """
    state_id = SceneStatesEnum.idle

    @override(SceneStateBase)
    def key_pressed(self, event: QKeyEvent):
        if self._check_click_delete(event):
            return

    @override(SceneStateBase)
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        if self._check_rubber_sel(event):
            return

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        # True for any item, regardless of mouse modifiers
        return True

    @override(SceneStateBase)
    def selection_changed(self, items: List[QGraphicsItem]):
        num_items = len(items)
        if num_items > 1:
            raise ValueError("Multi-selection not a valid operation in IDLE state")

        elif num_items == 1:
            self._set_state(SceneStateItemSelected)

        else:
            # nothing to do
            pass


class SceneStateItemSelected(SceneStateBase):
    """
    State active while only one item is selected. The item type does not matter. However, transitions
    to other states are affected by the type: currently, only parts can be multi-selected, and single-
    selections of a part, parent proxy, waypoint or link are enabled.
    """
    state_id = SceneStatesEnum.item_selected

    def __init__(self, prev_state: BaseFsmState, fsm_owner: IFsmOwner = None):
        super().__init__(prev_state, fsm_owner)
        self.__sel_kb_modifiers = Qt.NoModifier

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        # Ensure entering this state is valid: useful when returning to this state from SceneStateClickDelete where
        # the item previously selected was removed
        if len(self._fsm_owner.selectedItems()) == 0:
            self._set_state(SceneStateIdle)  # No item selected -> transition to idle

    @override(SceneStateBase)
    def key_pressed(self, event: QKeyEvent):
        # technically in this state there is always one item selected, but it seems like some key-press events
        # can reach us after item unselected and before state exited, perhaps the event sequence is
        # such that key press arrives first and mouse release (which would cause transition out of state) after:
        if not self._fsm_owner.selectedItems():
            return

        selected_item = self._fsm_owner.selectedItems()[0]

        # NOTE: an "if self._check_click_delete(event)" is adequate only if waypoints do NOT get highlighted
        # as part of link selection. This is because of the following:
        #
        # - currently, click-delete highlights item hovered over, which uses the same "indicator" as selection;
        # - so if you have a waypoint *selected*, and enter click-delete mode, and hover over a link, the link
        #   gets highlighted, and when hover away from link, the link get unhighlighted; this causes all its
        #   waypoints to get unhighlighted, yet the waypoint is still selected;
        # - the same situation occurs if multiple waypoints are selected (which is the SceneStateManyWaypointsSelected
        #   state).
        #
        # Until IInteractiveItem highlighting is separated between "normal" and "selection" highlighting,
        # transition to click-delete cannot be supported if selection is waypoint:
        if selected_item.type() == CustomItemEnum.waypoint:
            self._check_click_delete(event, disallowed='waypoint selected')
        elif self._check_click_delete(event):
            return

    @override(SceneStateBase)
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        # capture modifiers for next selectability check:
        if self._check_rubber_sel(event):
            return
        self.__sel_kb_modifiers = int(event.modifiers())

    @override(SceneStateBase)
    def mouse_moved(self, event: QGraphicsSceneMouseEvent):
        if not handle_mouse_move_event(event):
            return

        selected_item = self._fsm_owner.selectedItems()[0]
        if selected_item.isUnderMouse():
            selection_type = selected_item.type()
            if selection_type == CustomItemEnum.part:
                self._set_state(SceneStateMovingParts)
            elif selection_type == CustomItemEnum.parent_proxy:
                self._set_state(SceneStateMovingParentProxy)
            elif selection_type == CustomItemEnum.waypoint:
                self._set_state(SceneStateMovingWaypoints)
            else:
                # ignore mouse move, not a movable part
                pass

        else:
            item_under_mouse = self._fsm_owner.itemAt(event.scenePos(), QTransform())
            if item_under_mouse is not None:
                log.debug("Dragging over non-selected item {} while item {} is selected",
                          item_under_mouse, selected_item)
                self._set_state(SceneStateDefaultSceneInteract)

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        """
        When Ctrl-click a new item, the calling sequence is as follow:
        mouse_pressed->mouse_released->check_item_selectable
        :param item: the item to check
        :return: True if there are no modifiers, False otherwise
        """

        if self.__sel_kb_modifiers == Qt.NoModifier:
            log.debug("No modifier: true regardless of item type")
            return True

        if self.__sel_kb_modifiers == Qt.ControlModifier:
            current_selection = self._fsm_owner.selectedItems()
            assert len(current_selection) == 1
            # the item is only selectable if it is multi-selectable AND it matches the type of current selection:
            sel_type = current_selection[0].type()
            return sel_type in (CustomItemEnum.part, CustomItemEnum.waypoint) and item.type() == sel_type

        return False

    @override(SceneStateBase)
    def selection_changed(self, items: List[QGraphicsItem]):
        num_sel = len(items)
        if num_sel == 0:
            self._set_state(SceneStateIdle)
        elif num_sel > 1:
            item = items[0]
            if item.type() == CustomItemEnum.part:
                assert all(item.type() == CustomItemEnum.part for item in items)
                self._set_state(SceneStateManyPartsSelected)
            elif item.type() == CustomItemEnum.waypoint:
                assert all(item.type() == CustomItemEnum.waypoint for item in items)
                self._set_state(SceneStateManyWaypointsSelected)
            else:
                log.warning('Multi-selection of items of type {} is not supported.'.format(item.type()))
        else:
            # nothing to do
            assert num_sel == 1

    @override(SceneStateBase)
    def start_link_creation(self, from_item: LinkAnchorItem):
        self._set_state(SceneStateCreatingLink, from_item=from_item)

    @override(SceneStateBase)
    def start_link_retarget(self, part_link: PartLink,
                            from_item: LinkAnchorItem,
                            orig_source_item: LinkAnchorItem,
                            orig_target_item: LinkAnchorItem):
        self._set_state(SceneStateRetargetLink,
                        part_link=part_link,
                        from_item=from_item,
                        orig_source_item=orig_source_item,
                        orig_target_item=orig_target_item)

    @override(SceneStateBase)
    def start_object_interaction(self):
        self._set_state(SceneStateObjInteraction)


class SceneStateObjInteraction(SceneStateBase):
    """
    State while user is interacting with an object in the scene. The object must call the scene's
    start_object_interation() to enter this state from scene's state at the time of call, if allowed;
    and call end_object_interation() when done. This forces the scene to ignore all mouse proximity.
    """
    state_id = SceneStatesEnum.interact_scene_obj

    def end_object_interaction(self):
        self._set_state(self._prev_state_class)


class SceneStateRubberBandSel(SceneStateBase):
    """
    State active while the user is dragging a rubber band selection rectangle around objects of the scene.
    The first item selected determines what can be selected.
    """
    state_id = SceneStatesEnum.rubber_banding
    ALLOWED_TYPES = (CustomItemEnum.part, CustomItemEnum.waypoint)

    def __init__(self, prev_state: SceneStateBase, fsm_owner: Actor2dScene):
        super().__init__(prev_state, fsm_owner=fsm_owner)
        self.__selection_type = None

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        self._fsm_owner.get_main_view().set_rubberband_mode()

    @override(SceneStateBase)
    def exit_state(self, new_state: SceneStateBase):
        view = self._fsm_owner.get_main_view()
        if view is not None and view.is_rubberband_mode():
            view.set_cursor_default()

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        if item.type() not in self.ALLOWED_TYPES:
            return False

        # NOTE: GraphicsScene can emit selectionChanged for several objects at a time. This is a problem
        # when wanting to rubber band select items of one type determined by the first type of item hit.
        # For example if a waypoint and a part are both in selectionChanged, they will both check True
        # yet only one of the two should be selected. To get around this, when nothing is selected the
        # self.__selection_type is set to the type of first item checked:
        if self.__selection_type is None:
            self.__selection_type = item.type()
            return True

        # if we're here then only return True if item has same type as first check AND is multi-selectable.
        return item.MULTI_SELECTABLE and item.type() == self.__selection_type

    @override(SceneStateBase)
    def selection_changed(self, items: List[QGraphicsItem]):
        # log.debug('Rubber band selection type before selection change: {}', self.__selection_type.name)
        num_items = len(items)
        if num_items == 0:
            self.__selection_type = None

        else:
            item = items[0]
            if num_items == 1:
                assert self.__selection_type == item.type()
            else:
                assert num_items > 1
                check_items_type(items, self.__selection_type)
                # log.debug('Rubber band selection type after selection change: {}', self.__selection_type.name)

    @override(SceneStateBase)
    def mouse_released(self, event: QGraphicsSceneMouseEvent):
        self.end_area_selection()

    def end_area_selection(self):
        num_sel = len(self._fsm_owner.selectedItems())
        if num_sel == 0:
            self._set_state(SceneStateIdle)
        elif num_sel == 1:
            self._set_state(SceneStateItemSelected)
        else:
            assert num_sel > 1

            item = self._fsm_owner.selectedItems()[0]
            if item.type() == CustomItemEnum.part:
                self._set_state(SceneStateManyPartsSelected)
            elif item.type() == CustomItemEnum.waypoint:
                self._set_state(SceneStateManyWaypointsSelected)
            else:
                log.warning('Multi-selection of items of type {} is not supported.'.format(item.type()))


class SceneStateDefaultSceneInteract(SceneStateBase):
    """
    The canvas is grabbed by user. The default behavior of QGraphicsScene is adequate, just need to
    transition back to idle state on mouse release.
    """

    state_id = SceneStatesEnum.default_scene_interact

    @override(SceneStateBase)
    def mouse_released(self, event: QGraphicsSceneMouseEvent):
        # event.accept()
        self._set_state(self._prev_state_class)


class SceneStateManyPartsSelected(SceneStateBase):
    """
    State active while more than one scenario part is selected. Used because different item selection
    rules apply (only other parts can be selected, for instance).
    """
    state_id = SceneStatesEnum.many_parts_selected

    def __init__(self, prev_state: BaseFsmState, fsm_owner: IFsmOwner = None):
        super().__init__(prev_state, fsm_owner)
        self.__sel_kb_modifiers = Qt.NoModifier

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        self.__sel_kb_modifiers = Qt.NoModifier

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        """
        When Ctrl-click a new item, the calling sequence is as follow:
        mouse_pressed->mouse_released->check_item_selectable
        :param item: the item to check
        :return:  True if there are no modifiers, False otherwise
        """

        # Without mouse modifier, selection will be one, so anything goes:
        if self.__sel_kb_modifiers == Qt.NoModifier:
            return True

        # if extending selection, only parts can be added:
        if self.__sel_kb_modifiers == Qt.ControlModifier:
            return item.type() == CustomItemEnum.part

        return False

    @override(SceneStateBase)
    def key_pressed(self, event: QKeyEvent):
        if self._check_click_delete(event):
            return

    @override(SceneStateBase)
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        if self._check_rubber_sel(event):
            return

        self.__sel_kb_modifiers = event.modifiers()

    @override(SceneStateBase)
    def mouse_moved(self, event: QGraphicsSceneMouseEvent):
        if handle_mouse_move_event(event):
            if self._fsm_owner.check_any_selected_under_mouse():
                self._set_state(SceneStateMovingParts)
            else:
                self._set_state(SceneStateDefaultSceneInteract)

    @override(SceneStateBase)
    def selection_changed(self, items: List[QGraphicsItem]):
        if len(items) == 1:
            self._set_state(SceneStateItemSelected)
        elif not items:
            self._set_state(SceneStateIdle)

    @override(SceneStateBase)
    def start_object_interaction(self):
        self._set_state(SceneStateObjInteraction)


class SceneStateManyWaypointsSelected(SceneStateBase):
    """
    State active while more than one scenario waypoint is selected. Used because different item selection
    rules apply (only other waypoints can be selected, for instance).
    """
    state_id = SceneStatesEnum.many_waypoints_selected

    def __init__(self, prev_state: BaseFsmState, fsm_owner: IFsmOwner = None):
        super().__init__(prev_state, fsm_owner)
        self.__sel_kb_modifiers = Qt.NoModifier

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        # Ensure entering this state is valid: useful when returning to this state from SceneStateClickDelete where
        # the item previously selected was removed
        if len(self._fsm_owner.selectedItems()) == 0:
            self._set_state(SceneStateIdle)  # No item selected -> transition to idle
        elif len(self._fsm_owner.selectedItems()) == 1:
            self._set_state(SceneStateItemSelected)  # One item selected -> transition to item selected
        else:
            # This state is valid
            self.__sel_kb_modifiers = Qt.NoModifier

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        """
        When Ctrl-click a new item, the calling sequence is as follow:
        mouse_pressed->mouse_released->check_item_selectable
        :param item: the item to check
        :return: True if there are no modifiers, False otherwise
        """

        # Without mouse modifier, selection will be one, so anything goes:
        if self.__sel_kb_modifiers == Qt.NoModifier:
            return True

        # if extending selection, only waypoints can be added:
        if self.__sel_kb_modifiers == Qt.ControlModifier:
            return item.type() == CustomItemEnum.waypoint

        return False

    @override(SceneStateBase)
    def key_pressed(self, event: QKeyEvent):
        # NOTE: Until IInteractiveItem highlighting is separated into "normal" highlighting and "selection"
        # highlighting, there can be no transition to click-delete. See the note in SceneStateItemSelected.key_pressed.
        if self._check_click_delete(event, disallowed='at least one waypoint selected'):
            return

        # Cancel link creation if Esc pressed
        if event.key() == Qt.Key_Delete:
            if self._fsm_owner.has_waypoint_selection():
                event.accept()
                self._fsm_owner.delete_selected_waypoints()

    @override(SceneStateBase)
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        if self._check_rubber_sel(event):
            return

        self.__sel_kb_modifiers = event.modifiers()

    @override(SceneStateBase)
    def mouse_moved(self, event: QGraphicsSceneMouseEvent):
        if handle_mouse_move_event(event):
            if self._fsm_owner.check_any_selected_under_mouse():
                self._set_state(SceneStateMovingWaypoints)
            else:
                self._set_state(SceneStateDefaultSceneInteract)

    @override(SceneStateBase)
    def selection_changed(self, items: List[QGraphicsItem]):
        if len(items) == 1:
            self._set_state(SceneStateItemSelected)
        elif not items:
            self._set_state(SceneStateIdle)

    @override(SceneStateBase)
    def start_object_interaction(self):
        self._set_state(SceneStateObjInteraction)


class SceneStateMovingParts(SceneStateBase):
    """
    State active while user is moving scenario parts.
    """
    state_id = SceneStatesEnum.moving_parts

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        # Remember the position of each of the selected parts
        for selected_item in self._fsm_owner.selectedItems():
            assert selected_item.type() in (CustomItemEnum.part, CustomItemEnum.parent_proxy)
            selected_item.save_scenario_position()

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        return item.type() == CustomItemEnum.part

    @override(SceneStateBase)
    def mouse_released(self, event: QGraphicsSceneMouseEvent):
        # Pushes the PartsPositionsCommand to the undo stack. This requires the save_selected_objects_positions() to
        # have been called when the motion started, otherwise the get_saved_position() of each selected item will
        # be incorrect.
        # event.accept()

        parts = list()
        old_pos = list()
        new_pos = list()
        for selected_item in self._fsm_owner.selectedItems():
            assert selected_item.type() == CustomItemEnum.part
            parts.append(selected_item.part)
            start_position = selected_item.get_saved_position()
            # it is possible for motion to occur
            if start_position is None:
                start_position = selected_item.scenario_position_from_scene
            old_pos.append(start_position)
            new_pos.append(selected_item.scenario_position_from_scene)

        log.debug("Parts repositioning request sent for {} of actor {}",
                  [p.name for p in parts], self._fsm_owner.content_actor.path)
        scene_undo_stack().push(PartsPositionsCommand(parts, old_pos, new_pos))

        self._set_state(self._prev_state_class)


class SceneStateMovingWaypoints(SceneStateBase):
    """
    State active while user is moving scenario waypoints.
    """
    state_id = SceneStatesEnum.moving_waypoints

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        # Remember the position of each of the selected parts
        for selected_item in self._fsm_owner.selectedItems():
            assert selected_item.type() == CustomItemEnum.waypoint
            selected_item.save_scenario_position()

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        return item.type() == CustomItemEnum.waypoint

    @override(SceneStateBase)
    def mouse_released(self, event: QGraphicsSceneMouseEvent):
        # Pushes the WaypointPositionCommand to the undo stack. This requires the save_selected_objects_positions() to
        # have been called when the motion started, otherwise the get_saved_position() of each selected item will
        # be incorrect.
        # event.accept()

        waypoints = list()
        old_pos = list()
        new_pos = list()
        for selected_item in self._fsm_owner.selectedItems():
            assert selected_item.type() == CustomItemEnum.waypoint
            waypoints.append(selected_item.waypoint)
            start_position = selected_item.get_saved_position()
            # it is possible for motion to occur
            if start_position is None:
                start_position = selected_item.scenario_position_from_scene
            old_pos.append(start_position)
            new_pos.append(selected_item.scenario_position_from_scene)

        log.debug("Waypoints repositioning request sent for {} of actor {}",
                  [w.wp_id for w in waypoints], self._fsm_owner.content_actor.path)
        scene_undo_stack().push(WaypointPositionCommand(waypoints, old_pos, new_pos))

        self._set_state(self._prev_state_class)


class SceneStateMovingParentProxy(SceneStateBase):
    """
    State active while the parent proxy is being moved by user.
    """
    state_id = SceneStatesEnum.moving_proxy

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        # Remember the position of each of the selected parts
        self.__proxy = self._fsm_owner.selectedItems()[0]
        assert self.__proxy.type() == CustomItemEnum.parent_proxy
        self.__proxy.save_scenario_position()

    @override(SceneStateBase)
    def mouse_released(self, event: QGraphicsSceneMouseEvent):
        # Pushes the PartsPositionsCommand to the undo stack. This requires the save_selected_objects_positions() to
        # have been called when the motion started, otherwise the get_saved_position() of each selected item will
        # be incorrect.
        # event.accept()

        assert self.__proxy is self._fsm_owner.selectedItems()[0]
        old_pos = self.__proxy.get_saved_position()
        if old_pos is None:
            old_pos = self.__proxy.scenario_position_from_scene
        new_pos = self.__proxy.scenario_position_from_scene

        actor = self._fsm_owner.content_actor
        log.debug("Parent proxy repositioning request sent for actor {}", actor.path)
        scene_undo_stack().push(ParentProxyPositionCommand(actor, old_pos, new_pos))

        self._set_state(self._prev_state_class)


class SceneStateCreatingLink(SceneStateBase):
    """
    State active while user is in process of creating a link from one part to another.
    """
    state_id = SceneStatesEnum.creating_link

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, prev_state: SceneStateBase, fsm_owner: Actor2dScene, from_item: LinkAnchorItem):
        """
        Start creating a link from a part. Until the user chooses a target part or abandons, the scene will
        be in the "is_creating_link" state.
        :param from_item: the link anchor item from which the link should originate
        """
        super().__init__(prev_state, fsm_owner=fsm_owner)
        self.__cursor_orig = self._fsm_owner.get_main_view().cursor()

        # Create the first target selection line and add to list
        self._link_target_sel_line = PartLinkTargetSelLineItem()
        self._link_target_sel_line.set_source_anchor_item(from_item)
        self._fsm_owner.addItem(self._link_target_sel_line)
        self.__proposed_link_name = from_item.proposed_link_name

        # Lists for holding the set of link line and waypoint markers
        self.__link_line_markers = []
        self.__link_waypoint_markers = []

        # Target marker
        self._link_target_marker_item = PartLinkTargetMarkerItem()
        self._fsm_owner.addItem(self._link_target_marker_item)

        # position target marker in the graphics view so it is right under cursor
        view = self._fsm_owner.get_main_view()
        scene_origin = view.mapToScene(view.mapFromGlobal(QCursor.pos()))
        self._link_target_marker_item.setPos(scene_origin)

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        # Mark FIXME: the View code does not override and restore the view's cursor as they do in ClickDelete. Need to
        #   figure out why. Once working, qApp.setOverrideCursor can be removed.
        # view = self._fsm_owner.get_main_view()
        # view.set_cursor_override()
        # view.setCursor(QCursor(Qt.BlankCursor))
        qApp.setOverrideCursor(QCursor(Qt.BlankCursor))

    @override(SceneStateBase)
    def exit_state(self, new_state: SceneStateBase):
        # Mark FIXME: the View code does not override and restore the view's cursor as they do in ClickDelete. Need to
        #   figure out why. Once working, qApp.restoreOverrideCursor() can be removed.
        # view = self._fsm_owner.get_main_view()
        # if view is not None and view.is_cursor_overridden():
        #     view.setCursor(self.__cursor_orig)
        #     view.set_cursor_default()
        qApp.restoreOverrideCursor()

    @override(SceneStateBase)
    def key_pressed(self, event: QKeyEvent):
        """Cancel link creation if Esc pressed."""
        if event.key() == Qt.Key_Escape:
            event.accept()
            self.cancel_link_creation()

    @override(SceneStateBase)
    def mouse_moved(self, event: QGraphicsSceneMouseEvent):
        """
        Check if there are any items under it and if so, draw the line that indicates where the link will be. Otherwise,
        draws the line to the mouse cursor position.
        """
        # Accept the event so the caller knows to completely gobble up mouse move events
        event.accept()

        # see if we are hitting any target:
        scene_pos = event.scenePos()
        self._link_target_marker_item.setPos(scene_pos)

        if self.__link_line_markers:
            source = self.__link_line_markers[0].source_anchor_item
        else:
            source = self._link_target_sel_line.source_anchor_item

        # remove highlighting from items the cursor has hovered over previously
        self._remove_target_highlight()

        # Set default end-point selector to the 'target marker' and set the mark to display an invalid link
        self._link_target_sel_line.target_anchor_item = self._link_target_marker_item
        self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.waypoint_added)

        # determine if cursor is hovering over a target
        target = self._get_hovered_target(self._link_target_marker_item.collidingItems())

        # no target -> hovering over blank canvas can drop waypoints
        if target is None:
            self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.waypoint_added)
            return

        # have target -> check validity
        if self._is_valid_link_connection(source, target):
            # valid link
            target.set_highlighted(True)
            self._link_target_sel_line.target_anchor_item = target
            self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.valid_target)
        else:
            # invalid link
            self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.invalid_target)

    @override(SceneStateBase)
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        """Done link creation, action an undoable CreateLinkCommand which will make part create a link."""

        # remove highlighting from items the cursor has hovered over previously
        self._remove_target_highlight()

        # Cancel link creation if right mouse button pressed
        if event.button() == Qt.RightButton:
            event.accept()
            self.cancel_link_creation()
            return

        # Clicked on invalid target: do nothing
        if self._link_target_marker_item.linkable == LinkCreationStatusEnum.invalid_target:
            return

        # Clicked on blank canvas: add waypoint marker
        if self._link_target_sel_line.target_anchor_item in (self._link_target_marker_item, None):
            log.debug("Waypoint marker added as part of link target selection")
            waypoint_marker = WaypointMarkerItem(event.scenePos())
            self.__link_waypoint_markers.append(waypoint_marker)
            self._fsm_owner.addItem(waypoint_marker)

            # Fix the current link target line to the waypoint marker
            self._link_target_sel_line.target_anchor_item = waypoint_marker

            # Store the link line marker
            self.__link_line_markers.append(self._link_target_sel_line)

            # Start a new link line marker from the waypoint to the cursor
            self._link_target_sel_line = PartLinkTargetSelLineItem()
            self._link_target_sel_line.set_source_anchor_item(waypoint_marker)
            self._link_target_sel_line.target_anchor_item = self._link_target_marker_item
            self._fsm_owner.addItem(self._link_target_sel_line)
            return

        # Clicked on valid target: create link
        log.debug("Link creation requested")
        if self.__link_line_markers:
            source_link_sel_line = self.__link_line_markers[0]
            origin_frame = source_link_sel_line.source_anchor_item.part_frame
        else:
            origin_frame = self._link_target_sel_line.source_anchor_item.part_frame

        dest_frame = self._link_target_sel_line.target_anchor_item.part_frame
        waypoints_pos = [waypoint.position for waypoint in self.__link_waypoint_markers]
        create_link_command = CreateLinkCommand(origin_frame, dest_frame, self.__proposed_link_name, waypoints_pos)
        scene_undo_stack().push(create_link_command)

        # Restore source link anchor to unselected part z-level
        self._link_target_sel_line.source_anchor_item.setZValue(ZLevelsEnum.child_part)

        self._remove_markers()
        self._set_state(self._prev_state_class)

    @override(SceneStateBase)
    def cancel_link_creation(self):
        """Removes all markers and returns to previous state."""
        self._remove_markers()
        self._set_state(self._prev_state_class)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def _get_hovered_target(self, all_targets: List[QGraphicsItem]) -> None or LinkAnchorItem:
        """
        Determines which item that is a LinkAnchorItem in the list that the cursor is 'mostly' hovering over by
            calculating and comparing the area of each item covered by the target marker (cursor).
        :param all_targets: A list of all colliding items with the cursor.
        :return: The LinkAnchorItem hovered over by the cursor (item with the most area covered by the cursor).
        """
        if not all_targets:
            return None

        valid_target_types = (CustomItemEnum.part, CustomItemEnum.parent_proxy, CustomItemEnum.ifx_port)
        target_marker_rect = self._link_target_marker_item.sceneBoundingRect()

        max_area = 0
        valid_target_index = None
        for idx, target in enumerate(all_targets):
            if target.type() in valid_target_types:
                target_rect = target.sceneBoundingRect()
                intersect_rect = target_rect.intersected(target_marker_rect)
                target_area = intersect_rect.height() * intersect_rect.width()

                # if the target area is > last computed max, we have a new max
                if target_area > max_area:
                    max_area = target_area
                    valid_target_index = idx

        if valid_target_index is not None:
            # the item hovered over is the one with the maximum intersection area
            return all_targets[valid_target_index]
        else:
            return None

    def _is_valid_link_connection(self, source: LinkAnchorItem, target: LinkAnchorItem) -> bool:
        """
        Checks for a valid connections from or to source or target items (parts or ports).
        An invalid connection occurs if a part is being connected to one of its own ports or vice versa. Non-ifx ports
        return True (valid) by default.
        :param source: The source item being connected.
        :param target: The potential target item being connected.
        :return: A boolean flag indicating if the connection is valid (True) or invalid (False).
        """
        return (target is not source and target.is_link_allowed(source) and source.is_link_allowed(target) and
                not self.__is_target_already_connected(source, target))

    def _remove_markers(self):
        """
        Removes the link line and waypoint markers.
        """
        self._link_target_sel_line.dispose()
        self._link_target_sel_line = None
        self._link_target_marker_item.dispose()
        self._link_target_marker_item = None

        for line in self.__link_line_markers:
            line.dispose()

        for marker in self.__link_waypoint_markers:
            marker.dispose()

        self.__link_line_markers = None
        self.__link_waypoint_markers = None

    def _remove_target_highlight(self):
        """Remove highlight from the previous target hovered over by the cursor."""
        if self._link_target_sel_line.target_anchor_item not in (None, self._link_target_marker_item):
            self._link_target_sel_line.target_anchor_item.set_highlighted(False)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __is_target_already_connected(self, source: LinkAnchorItem, target: LinkAnchorItem) -> bool:
        """
        Check if target is already connected to the source.
        :param source: The source item.
        :param target: The target item.
        :return: A boolean flag indicating the source and target are already connected.
        """
        # search all incoming links to the target for a source that is the 'source'.
        for link in target.part_frame.incoming_links:
            if link.source_part_frame is source.part_frame:
                return True

        return False


class SceneStateRetargetLink(SceneStateCreatingLink):
    """
    State active while user is in process of setting a link to another target.
    """
    state_id = SceneStatesEnum.retargeting_link

    def __init__(self, prev_state: SceneStateBase,
                 fsm_owner: Actor2dScene,
                 part_link: PartLink,
                 from_item: LinkAnchorItem,
                 orig_source_item: LinkAnchorItem,
                 orig_target_item: LinkAnchorItem):
        """
        Start selecting a new target for the provided part link. Until the user chooses a new target or abandons, the
        scene will be in the "is_retargeting_link" state.
        :param part_link: The link whose target is being changed.
        :param from_item: The link anchor from which the link should originate (not necessarily the links source).
        :param orig_source_item: The original source link anchor of this link.
        :param orig_target_item: The original target link anchor of this link.
        """
        super().__init__(prev_state, fsm_owner=fsm_owner, from_item=from_item)

        self.__part_link = part_link
        self.__from_item = from_item
        self.__orig_source_item = orig_source_item
        self.__orig_target_Item = orig_target_item

    @override(SceneStateCreatingLink)
    def mouse_moved(self, event: QGraphicsSceneMouseEvent):
        """
        Check if there are any items under it and if so, draw the line that indicates where the link will be. Otherwise,
        draws the line to the mouse cursor position.
        """
        # Accept the event so the caller knows to completely gobble up mouse move events
        event.accept()

        # Elevate the source anchor of the link so link connections 'inside' the part are hidden
        self._link_target_sel_line.source_anchor_item.setZValue(ZLevelsEnum.link_creation_source_item)

        # see if we are hitting any target:
        scene_pos = event.scenePos()
        self._link_target_marker_item.setPos(scene_pos)

        # remove highlighting from items the cursor has hovered over previously
        self._remove_target_highlight()

        # Set default end-point selector to the 'target marker' and set the mark to display an invalid link
        self._link_target_sel_line.target_anchor_item = self._link_target_marker_item
        self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.invalid_target)

        # determine if cursor is hovering over a target
        target = self._get_hovered_target(self._link_target_marker_item.collidingItems())

        # no target -> hovering over blank canvas is invalid re-target
        if target is None:
            self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.invalid_target)
            return

        # have target -> check validity
        if self._is_valid_link_connection(self.__orig_source_item, target):
            # valid link
            target.set_highlighted(True)
            self._link_target_sel_line.target_anchor_item = target
            self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.valid_target)
        else:
            # invalid link
            self._link_target_marker_item.set_linkable(LinkCreationStatusEnum.invalid_target)

    @override(SceneStateCreatingLink)
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        """Done link retargeting, action an undoable RetargetLinkCommand which will change the link's target part."""

        # remove highlighting from items the cursor has hovered over previously
        self._remove_target_highlight()

        if self._link_target_sel_line.target_anchor_item in (self._link_target_marker_item, None):
            log.info("Link retarget cancelled")
        else:
            log.info("Link retarget requested")
            new_target_frame = self._link_target_sel_line.target_anchor_item.part_frame
            retarget_link_command = RetargetLinkCommand(self.__part_link, new_target_frame)
            scene_undo_stack().push(retarget_link_command)

        # Restore source link anchor to unselected part z-level
        self._link_target_sel_line.source_anchor_item.setZValue(ZLevelsEnum.child_part)

        # cleanup and hide Link indicator:
        self._link_target_sel_line.dispose()
        self._link_target_sel_line = None
        self._link_target_marker_item.dispose()
        self._link_target_marker_item = None

        self._set_state(self._prev_state_class)

    @override(SceneStateBase)
    def cancel_link_retarget(self):
        """Removes all markers and returns to previous state."""
        self._remove_markers()
        self._set_state(self._prev_state_class)


class SceneStateClickDelete(SceneStateBase):
    """
    State active while the user holds down the keyboard modifier keys to click on links and waypoints to delete.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    CURSOR_WIDTH = 25
    CURSOR_HEIGHT = 8
    CURSOR_NO_DELETABLE_ITEM = None
    CURSOR_DELETABLE_ITEM = None

    ALLOWED_TYPES = (CustomItemEnum.link, CustomItemEnum.waypoint)

    state_id = SceneStatesEnum.click_delete

    # --------------------------- class-wide methods --------------------------------------------

    @classmethod
    def __init_cursors(cls):
        """Create the cursors; these can only be created after QApplication exists, hence this classwide method."""
        assert cls.CURSOR_DELETABLE_ITEM is None
        assert cls.CURSOR_NO_DELETABLE_ITEM is None
        cls.CURSOR_DELETABLE_ITEM = new_cursor_from_svg_path(
            get_icon_path("delete_item.svg"), cls.CURSOR_WIDTH, cls.CURSOR_HEIGHT)
        cls.CURSOR_NO_DELETABLE_ITEM = new_cursor_from_svg_path(
            get_icon_path("click_deletion_mode.svg"), cls.CURSOR_WIDTH, cls.CURSOR_HEIGHT)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, prev_state: SceneStateBase, fsm_owner: Actor2dScene):
        super().__init__(prev_state, fsm_owner=fsm_owner)
        self.__cursor_orig = self._fsm_owner.get_main_view().cursor()
        if self.CURSOR_DELETABLE_ITEM is None:
            self.__init_cursors()
        # Check whether tracked deletable item has been removed from scene:
        self._fsm_owner.changed.connect(self.__on_scene_changed)
        self.__deletable_item = None
        self.__item_needs_unhighlight = False

    @override(SceneStateBase)
    def enter_state(self, prev_state: SceneStateBase):
        view = self._fsm_owner.get_main_view()
        view.set_cursor_override()
        view.setCursor(self.CURSOR_NO_DELETABLE_ITEM)
        self.__update_deletability()

    @override(SceneStateBase)
    def exit_state(self, new_state: SceneStateBase):
        self._fsm_owner.changed.disconnect(self.__on_scene_changed)
        view = self._fsm_owner.get_main_view()
        if view is not None and view.is_cursor_overridden():
            view.setCursor(self.__cursor_orig)
            view.set_cursor_default()

    @override(SceneStateBase)
    def selection_changed(self, items: List[QGraphicsItem]):
        pass  # Overridden to avoid log warning

    @override(SceneStateBase)
    def check_item_selectable(self, item: IInteractiveItem) -> bool:
        return item.type() in self.ALLOWED_TYPES

    @override(SceneStateBase)
    def key_released(self, event: QKeyEvent):
        """Return to the previous Scene state when releasing the keyboard modifier keys."""
        # event.accept()
        self.__unhighlight_deletable_item()
        self._set_state(self._prev_state_class)

    @override(SceneStateBase)
    def mouse_moved(self, event: QGraphicsSceneMouseEvent):
        """Check if graphics item under the cursor can be deleted when user clicks it."""
        # Accept the event so the caller knows to completely gobble up mouse move events
        event.accept()
        scene_pos = event.scenePos()
        self.__update_deletability(scene_pos)

    @override(SceneStateBase)
    def mouse_pressed(self, event: QGraphicsSceneMouseEvent):
        """Delete latest graphics item that was found to be deletable."""
        if self.__deletable_item is None:
            return

        assert self.__deletable_item.type() in (CustomItemEnum.waypoint, CustomItemEnum.link)

        if self.__deletable_item.type() == CustomItemEnum.waypoint:
            self.__deletable_item.link_obj.remove_waypoint(self.__deletable_item)

        else:
            assert self.__deletable_item.type() == CustomItemEnum.link
            self.__deletable_item.remove_link()

        # The command to delete scenario object is on its way, but item still under the cursor, so nothing
        # more to do here; selection will eventually change when corresponding scene item deleted, and the
        # deletion cursor will be updated (so no point in calling self.__update_deletability()).
        pass  # so Code -> Reformat leaves previous comment alone

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_scene_changed(self, rects: List[QRectF]):
        """
        Whenever the scene content changes (added or removed graphics item; not sure if other types of
        changes qualify, for example move does not, and visibility likely not).
        :param rects: list of rectangles in which scene has changed
        """
        self.__update_deletability()

    def __get_item_under_mouse(self, scene_pos: QPointF) -> QGraphicsItem:
        """
        Get the graphics item under the mouse.
        :param scene_pos: The scene position of mouse.
        :return: The item found, or None.
        """
        return self._fsm_owner.itemAt(scene_pos, QTransform())  # Identity transform provided since no mapping required

    def __update_deletability(self, scene_pos: QPointF = None):
        """
        Change the cursor to reflect whether item at scene position can be deleted on mouse press.
        :param scene_pos: The current item under the mouse.
        """
        if scene_pos is None:
            view = self._fsm_owner.get_main_view()
            scene_pos = view.mapToScene(view.mapFromGlobal(QCursor.pos()))

        item_under_mouse = self.__get_item_under_mouse(scene_pos)
        if item_under_mouse is None:
            log.debug("Click-delete: No item under mouse")
            self.__set_deletable_item(None)

        elif item_under_mouse is self.__deletable_item:
            log.debug("Click-delete: already up-to-date")
            assert self.__deletable_item is not None

        elif item_under_mouse.type() in self.ALLOWED_TYPES:
            log.debug("Click-delete: new item under mouse click-deletable")
            self.__set_deletable_item(item_under_mouse)

        else:
            # Item cannot be deleted in this scene state
            log.debug("Click-delete: item under mouse NOT click-deletable")
            self.__set_deletable_item(None)

    def __set_deletable_item(self, item: Optional[QGraphicsItem]):
        """
        Overrides the cursor with an SVG image based on presence of click-deletable item under cursor.
        """
        if self.__deletable_item is item:
            # both are None, or still over same item as last, so nothing else to do:
            return

        self.__unhighlight_deletable_item()

        self.__deletable_item = item
        self.__item_needs_unhighlight = False
        if item is None:
            self._fsm_owner.get_main_view().setCursor(self.CURSOR_NO_DELETABLE_ITEM)
        else:
            self._fsm_owner.get_main_view().setCursor(self.CURSOR_DELETABLE_ITEM)
            if not item.is_highlighted:
                self.__item_needs_unhighlight = True
                item.set_highlighted(True)

    def __unhighlight_deletable_item(self):
        """
        Remove the highlight on the last deletable item, if any.
        """
        if self.__deletable_item is not None:
            try:
                if self.__item_needs_unhighlight:
                    self.__deletable_item.set_highlighted(False)
                    self.__item_needs_unhighlight = False
            except Exception:
                pass  # item was deleted
