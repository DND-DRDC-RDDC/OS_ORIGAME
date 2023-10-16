# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Common constants, functions etc specific to 2d view

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum, unique

# [2. third-party]
from PyQt5.QtCore import QVariant, Qt, QEvent, QObject, pyqtSlot, pyqtSignal, QRectF
from PyQt5.QtWidgets import QGraphicsObject, QGraphicsItem, QGraphicsSceneMouseEvent
from PyQt5.QtGui import QKeyEvent, QMouseEvent

# [3. local]
from ...core import override_required, override_optional, override
from ...scenario.defn_parts import Position, BasePart
from ..conversions import map_from_scenario, map_to_scenario

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ZLevelsEnum',
    'register_part_item_class',
    'get_part_item_class',
    'DetailLevelOverrideEnum',
    'CustomItemEnum',
    'ICustomItem',
    'IInteractiveItem',
    'EventStr',
    'disconnect_all_slots_children'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def disconnect_all_slots_children(obj: QObject):
    qobjects = obj.findChildren(QObject)
    for qobj in qobjects:
        try:
            qobj._disconnect_all_slots()
        except AttributeError:
            pass


def disconnect_all_slots(emitter: QObject, receiver: QObject):
    def methods(obj: QObject, meth_type: int):
        meta_object = obj.metaObject()
        for i in range(meta_object.methodCount()):
            method = meta_object.method(i)
            if method.methodType() == meth_type:
                meth_name = bytes(method.name()).decode()
                yield getattr(obj, meth_name)

    from PyQt5.QtCore import QMetaMethod
    disconnections = {}
    for signal in methods(emitter, QMetaMethod.Signal):
        for slot in methods(receiver, QMetaMethod.Slot):
            try:
                signal.disconnect(slot)
                disconnections.setdefault(signal, []).append(slot)
            except:
                # there was no connection, move on to next slot
                pass

    print('disconnected', disconnections)


# -- Class Definitions --------------------------------------------------------------------------

class ZLevelsEnum(IntEnum):
    link_creation_target_marker = 20
    waypoint_selected = 20
    link_creation_source_item = 19  # raise level of part so can't see out-going link while linking
    waypoint = 19
    link_creation_line = 18
    link_selected = 18
    link_decluttered = 0   #18
    link = 0               #18

    indicator = 10  # for event counters, run roles, etc
    trays = 4

    child_part_selected = 3

    child_part = 1
    parent_proxy = 1  # same as other child parts
    part_colliding = 0  # TODO: replace with child_part_selected
    proximity_boundary = -1
    part_item_border = -3

    bubble_comment = -11  # bubble comment is supposed to be under links


__map_part_types_to_item_class = {}


def register_part_item_class(part_type_str: str, PartItemClass: type):
    """
    Register a new part graphics item class.
    :param part_type_str: name of part type
    :param PartItemClass: class to be instantiated for given part_type_str
    :raise: ValueError if a class already registered for same part_type_str
    """
    if part_type_str in __map_part_types_to_item_class:
        raise ValueError("Type '{}' already has item class registered, fatal error".format(part_type_str))

    msg = "Class '{}' will be instantiated for part type '{}' 2d actor view"
    log.debug(msg.format(PartItemClass.__name__, part_type_str))
    __map_part_types_to_item_class[part_type_str] = PartItemClass


def get_part_item_class(part_type_str: str):
    """Return the class for given part type name, or None if none registered"""
    return __map_part_types_to_item_class.get(part_type_str)


@unique
class DetailLevelOverrideEnum(IntEnum):
    """
    This is the mechanism for the view to override the detail level preferences that come from the backend.

    When it is "full" or "minimal", the view will ignore the values from the back end and will use the "full" or
    "minimal" defined here.

    When it is "none", the view must honour the values from the back end.
    """
    full = 0
    minimal = 1
    none = 2


@unique
class CustomItemEnum(IntEnum):
    """
    It is mandatory for the QGraphicsItem to implement the type(). This class defines the unique type for all items
    derived from QGraphicsItem for Origame.
    """
    (undefined,
     any,
     part,
     link,
     waypoint,
     ifx_port,
     parent_proxy,
     hub,
     multiplier,
     node,
     proximity,
     link_creation,
     top_side_tray,
     bottom_side_tray,
     left_side_tray,
     right_side_tray,
     ifx_bar,
     event_counter,
     widget_proxy,
     missing_link_indicator,
     size_grip,
     size_grip_corner,
     size_grip_right,
     size_grip_bottom,
     selection_border) = range(QGraphicsItem.UserType, QGraphicsItem.UserType + 25)


class ICustomItem:
    """
    Super class for all the graphics items that are implemented for this project.
    """

    def __init__(self):
        self.__disposed = False

    @property
    def disposed(self) -> bool:
        """Returns True if this custom item has had dispose called on it at least once"""
        return self.__disposed

    def dispose(self):
        """
        Dispose of the graphics item. This will operate differently on pure QGraphicsItem vs QGraphicsObject:

        - on QGraphicsItem: remove it from the scene
        - on QGraphicsObject: deleteLater it and hide it so that it can no longer take part in scene activities
          between disposal and destruction.

        Note that the item should no longer be used after this method has been called. It will have a
        disposed property that can be checked where necessary. In particular, even if it is a pure QGraphicsItem,
        it CANNOT be re-added to the scene, ever.
        """
        if self.__disposed:
            return

        self.__disposed = True

        try:
            # if self derives from QObject, it must be deleteLater'd so that pending signals are properly cleaned up:
            self.deleteLater()

            # BUT we do not remove it from scene, because some of its slots could get called between now and when
            # it gets destroyed (due to how deleteLater() works): those slots would then have item.scene() = None.
            # We don't want to require that every slot check for that! QGraphicsQObject::destructor automatically
            # removes item from its scene.

            # HOWEVER, we need to disable the item otherwise, there seems to be a Qt bug that *can* cause a
            # crash later. The crash may happen for a simple scenario deleting just a part without links, but
            # not happen for a much more complex scenario where deleting several PartBoxItem linked to stuff!
            self.setEnabled(False)
            self.setVisible(False)

            # notify scene:
            self.scene().on_grobj_item_disposed(self)

        except TypeError:
            # self does not derive from QObject
            super().removeItem(self)

    def get_ancestor_item(self, graphics_item_class: type) -> QGraphicsItem:
        """
        Get the nearest ancestor graphics item that is of a certain type.
        :param graphics_item_class: the type to look for
        :return: the found item, or None if no ancestor or no ancestor of requested type
        """
        parent = self.parentItem()
        while parent is not None:
            if isinstance(parent, graphics_item_class):
                return parent
            parent = parent.parentItem()

        # did not find a parent of type graphics_item_class
        return None


class IInteractiveItem(ICustomItem):
    """
    Mixin for graphics items that can be interacted with in the 2d view.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    MULTI_SELECTABLE = False  # Derived overrides this to True if this type of item supports multi-selection
    DRAGGABLE = False  # Derived overrides this to True if this type of item can be dragged

    # ---------------------------- instance PUBLIC methods -------------------------------

    def __init__(self):
        super().__init__()
        assert self.type() != CustomItemEnum.undefined
        self.__part_position_on_press = None
        self._highlighted = False

    @override(QGraphicsObject)
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, new_value: QVariant) -> QVariant:
        """
        Intercept attempt to change selection state of this item: only allow if scene says item is selectable.
        :param change: the change that occurred
        :param new_value: the new value of attribute associated with change
        :returns: False if attempted disallowed selection, or superclass itemChange() otherwise
        """
        if change == QGraphicsItem.ItemSelectedChange and new_value:
            if not self.scene().check_item_selectable(self):
                log.debug('Item of type {} cannot be in current extended selection', self.__class__.__name__)
                return False

        elif change == QGraphicsItem.ItemSelectedHasChanged:
            # log.debug('Setting highlight to {}', new_value)
            self.set_highlighted(new_value)

        return super().itemChange(change, new_value)

    @override_optional
    def get_highlight_rect(self, outer: bool = False) -> QRectF:
        """Get the highlighted rect (inner or outer)
        :param outer: indicate if want outer rect
        :returns: the highlighted rect
        """
        if outer:
            raise NotImplementedError
        else:
            return self.boundingRect()

    @override_required
    def get_scenario_object(self) -> BasePart:  # or LinkWaypoint:
        """Get the scenario object that corresponds to this item"""
        # Mark FIXME ASAP: return annotation is incomplete
        #     Reason: only Mark knows for sure why part of annotation was commented out
        raise NotImplementedError

    @override_optional
    def set_scene_pos_from_scenario(self, x: float, y: float):
        """
        Set position of this PartBoxItem.
        :param x: x-coordinate in Scenario coordinates
        :param y: y-coordinate in Scenario coordinates
        """
        scene_pos = map_from_scenario(Position(x, y))
        self.setPos(scene_pos)

    def get_scenario_position_from_scene(self) -> Position:
        """
        :return: The Position of this item in scenario coordinates
        """
        scenario_position = map_to_scenario(self.pos())
        assert scenario_position is not None
        return scenario_position

    def save_scenario_position(self):
        """Remembers the position when the moving started."""
        self.__part_position_on_press = self.get_scenario_position_from_scene()

    def get_saved_position(self) -> Position:
        """Gets the position when the moving started, in scenario coordinates."""
        return self.__part_position_on_press

    def set_highlighted(self, state: bool):
        """Change the highlight state of this object. Does nothing if state already correct."""
        if self._highlighted != state:
            # Benefits from Python. We are able to do self.prepareGeometryChange() even if this class does not
            # have this function. The derived classes do.
            self.prepareGeometryChange()
            self._highlighted = state
            self._highlighting_changed()

    def get_highlighted(self) -> bool:
        """Get the current highlight state of this item."""
        return self._highlighted

    # ---------------------------- instance PUBLIC properties ----------------------------

    is_highlighted = property(get_highlighted)
    scenario_position_from_scene = property(get_scenario_position_from_scene)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def _set_flags_item_change_interactive(self):
        """Must be called by derived class (during init, but after QGraphicsItem.__init__() called)"""
        self.setFlag(QGraphicsItem.ItemIsFocusable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        if self.DRAGGABLE:
            self.setFlag(QGraphicsItem.ItemIsMovable)

    @override_optional
    def _highlighting_changed(self):
        """Update visuals based on new highlight state (in self._highlighted)."""
        pass


assert CustomItemEnum.undefined == QGraphicsItem.UserType


class EventStr:
    """
    This class provides a way of delaying the very complex formatting of events until we know that it
    really is needed. The alternative of using a function would be very expensive: in the statement
    log.debug("format", func(event)), func(event) is executed even if the log level is larger than
    debug. By using this class instead, the overhead is minimal (creating an instance); only when the
    log formats its message is the event converted to a string.
    """

    def __init__(self, event: QEvent):
        self.event = event

    def __str__(self):
        event = self.event
        event_mods = event.modifiers()

        mods = []
        if bool(event_mods & Qt.ControlModifier):
            mods.append("ctrl")
        if bool(event_mods & Qt.AltModifier):
            mods.append("alt")
        if bool(event_mods & Qt.ShiftModifier):
            mods.append("shift")
        mods = '-'.join(mods)

        def get_buttons(event):
            buttons = []
            if bool(self.event.buttons() & Qt.LeftButton):
                buttons.append('LEFT')
            if bool(self.event.buttons() & Qt.RightButton):
                buttons.append('RIGHT')
            return ', '.join(buttons)

        if isinstance(event, QKeyEvent):
            text = self.event.text()
        elif isinstance(event, QMouseEvent):
            pos = self.event.pos()
            buttons = get_buttons(event)
            text = '{} at ({}, {})'.format(buttons, pos.x(), pos.y())
        elif isinstance(event, QGraphicsSceneMouseEvent):
            pos = self.event.pos()
            scene_pos = self.event.scenePos()
            buttons = get_buttons(event)
            text = '{} at ({:.5}, {:.5}) (in scene at {:.5}, {:.5})'.format(
                buttons, pos.x(), pos.y(), scene_pos.x(), scene_pos.y())
        else:
            text = 'UNKNOWN type {}'.format(event)

        if mods:
            return mods + ' ' + text
        else:
            return text
