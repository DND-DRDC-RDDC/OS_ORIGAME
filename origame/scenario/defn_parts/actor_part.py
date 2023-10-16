# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains the ActorPart class definition and supporting code.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum
from itertools import chain

# [2. third-party]

# [3. local]
from ...core import override, BridgeEmitter, BridgeSignal, internal
from ...core.utils import plural_if
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriBaselineEnum, OriContextEnum, OriScenData, JsonObj
from ..ori import OriRotation3dKeys as R3dKeys, OriPositionKeys as PosKeys, OriCommonPartKeys as CpKeys
from ..ori import OriActorPartKeys as ApKeys, OriSocketPartKeys as SpKeys, OriNodePartKeys as NpKeys
from ..proto_compat_warn import prototype_compat_method_alias, prototype_compat_property_alias
from ..alerts import IScenAlertSource

from .common import Vector, Position
from .base_part import BasePart, RestorePartInfo
from .part_frame import PartFrame, RestoreIfxLevelInfo
from .part_link import PartLink, PARENT_ACTOR_PATH, LINK_PATH_DELIM, InvalidLinkPathSegmentError
from .part_link import RestoreLinkInfo, UnrestorableLinks, LinkTip, LinkWaypoint
from .part_types_info import register_new_part_type, get_part_class_by_name
from .socket_part import SocketPartConverter

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'Rotation3D',
    'ActorPart',
    'RestoreIfxPortInfo',
    'ActorIfxPortSide',
    'RestoreReparentInfo',
    'get_parents_map',
    'check_same_parent',
]

log = logging.getLogger('system')

QUEUE_COUNTS_INTERVAL_SEC = 0.5


class Decl(AnnotationDeclarations):
    ActorPart = 'ActorPart'
    NodePart = 'NodePart'
    Panda3dNodePath = 'Panda3dNodePath'


DescendantFilterCallable = Callable[[BasePart], bool]


# -- Function definitions -----------------------------------------------------------------------

def get_parents_map(parts: List[BasePart]) -> Dict[Decl.ActorPart, Set[BasePart]]:
    """
    Get a mapping of parents to parts.
    :param parts: (non-empty) list of parts to map
    """
    map_parents_to_parts = {}
    for orig_part in parts:
        map_parents_to_parts.setdefault(orig_part.parent_actor_part, set()).add(orig_part)
    return map_parents_to_parts


def check_same_parent(parts: List[BasePart]):
    """
    Checks that all parts have the same parent. If not, raises ValueError, else returns without any side
    effect.
    """
    if not parts:
        raise ValueError("No parts in list, parent cannot be obtained")

    map_parents_to_parts = get_parents_map(parts)
    assert bool(map_parents_to_parts)
    if len(map_parents_to_parts) >= 2:
        raise ValueError("More than one parent actor part", map_parents_to_parts)


def parts_to_str(parts: List[BasePart]) -> str:
    """Convert a list of parts to a comma-separated string of part identifiers"""
    return ', '.join(str(p) for p in parts)


# -- Class Definitions --------------------------------------------------------------------------

PartLinksRestoreMap = Dict[PartLink, RestoreLinkInfo]
ParentType = Either[Decl.ActorPart, IScenAlertSource]


class UnsupportedPartTypeError(Exception):
    """
    Raised when the ORI specifies a part type that is known to the application.
    """

    def __init__(self, msg: str):
        super().__init__(msg)


class Rotation3D:
    """
    This class represents 3-D rotation information.
    """

    def __init__(self, roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0):
        self._roll = roll
        self._pitch = pitch
        self._yaw = yaw

    def get_roll(self) -> float:
        """
        Get the 3D rotational roll angle.
        """
        return self._roll

    def set_roll(self, value: float):
        """
        Set the 3D rotational roll angle.
        :param value: The new roll angle, in degrees.
        """
        self._roll = value

    def get_pitch(self) -> float:
        """
        Get the 3D rotational pitch angle, in degrees.
        """
        return self._pitch

    def set_pitch(self, value: float):
        """
        Set the 3D rotational pitch angle.
        :param value: The new pitch angle, in degrees.
        """
        self._pitch = value

    def get_yaw(self) -> float:
        """
        Get the 3D rotational yaw angle, in degrees.
        """
        return self._yaw

    def set_yaw(self, value: float):
        """
        Set the 3D rotational yaw angle.
        :param value: The new yaw angle, in degrees.
        """
        self._yaw = value

    def get_rpy_deg(self) -> Tuple[float, float, float]:
        """Get 3D rotation as a triplet Roll, Pitch, Yaw, in degrees"""
        return self._roll, self._pitch, self._yaw

    roll = property(get_roll, set_roll)
    pitch = property(get_pitch, set_pitch)
    yaw = property(get_yaw, set_yaw)
    rpy_deg = property(get_rpy_deg)


class ActorIfxPortSide(IntEnum):
    left, right, both = range(3)


class RestoreIfxPortInfo:
    def __init__(self, index: int, left_side: bool):
        self.left_side = left_side
        self.index = index


# for annotations:
RestoreIfxPortsInfo = Dict[Decl.ActorPart, RestoreIfxPortInfo]


class RestoreIfxPortIndexInfo:
    def __init__(self, from_index: int, left_side: bool, to_index: int):
        self.left_side = left_side
        self.from_index = from_index
        self.to_index = to_index


class RestoreReparentInfo:
    """
    When reparenting parts, scenario may change in the following manner, and this must be reversed when
    un-reparenting the parts:

    - the parts may get moved
    - the interface level of some parts may be increased if the reparenting had maintain-links = True

    Other aspects of the unreparenting (such as removing the parts and all associated links) are handled
    in the part's deletion restore info kept separately.
    """

    def __init__(self, ifx_levels: Dict[PartFrame, RestoreIfxLevelInfo],
                 paste_offset: Vector,
                 parts_restore_infos: List[RestorePartInfo]):
        self.ifx_levels = ifx_levels
        self.paste_offset = paste_offset
        self.parts_pos = [pri.position for pri in parts_restore_infos]


class ActorPart(BasePart):
    """
    This class represents a scenario part that aggregates other parts, called children parts. It allows
    those children to be linked to and from other parts via their interface (aka ifx) level property.
    """

    class Signals(BridgeEmitter):
        sig_proxy_pos_changed = BridgeSignal(float, float)  # x, y
        sig_geom_path_changed = BridgeSignal(str)  # new path
        sig_image_changed = BridgeSignal(str or None)  # new path of custom image, or None for default image.
        sig_rotation_2d_changed = BridgeSignal(float)  # new rotation 2d.

        sig_child_added = BridgeSignal(BasePart)  # part added
        sig_child_deleted = BridgeSignal(int)  # unique ID
        sig_parts_copied = BridgeSignal(list)  # BasePart
        sig_parts_restored = BridgeSignal(list)  # BasePart
        sig_waypoints_restored = BridgeSignal(dict)  # Dict[PartLink, List[LinkWaypoint]]

        sig_queue_actor_counters_changed = BridgeSignal()

        sig_ifx_port_added = BridgeSignal(PartFrame, bool, int)  # port, left side, index
        sig_ifx_port_removed = BridgeSignal(PartFrame, bool)  # port, left side
        sig_ifx_port_side_changed = BridgeSignal(PartFrame, bool, int)  # port, to left side, to index
        sig_ifx_port_index_changed = BridgeSignal(int, bool, int)  # from index, side, to index (same side)

    PART_TYPE_NAME = 'actor'
    DESCRIPTION = """\
        Actors are containers for model logic.  They can be used to hide low-level
        details from a higher level view.

        Use the interface setting on any descendant's part frame to make it visible on the interface of
        ancestor parts. For example given root -> actor1 -> actor2 -> part, and part interface level is 2,
        then part is on the interface of actor1, so it is accessible by any part in root, including descendants
        of root that are visible by root.

        Double-click to edit.
    """

    DEFAULT_VISUAL_SIZE = dict(width=6.2, height=5.6)

    # we have 0 or more BasePart children ORI serializable
    _ORI_HAS_CHILDREN = True

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: Optional[ParentType], name: str = None, position: Position = None):
        """
        :param parent: The Actor part to which this Part belongs, or, in the case of the root Actor Part, the
            object that owns this Part.
        :param name: The name to be associated with the newly instantiated Actor Part.
        :param position: A position to be assigned to the newly instantiated Actor Part.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        assert (self._parent_actor_part is not None) or (not isinstance(parent, ActorPart))

        self.signals = ActorPart.Signals()

        # Root actor of a scenario has self._parent_actor_part = None and cannot be moved within a scenario.
        # For non-root actor, parent can change dynamically (parts can be moved within actor hierarchy)
        # so we set alert-parent to None so that the actual parent will always be used. For root actor, we set
        # alert-parent only if parent is an instance of IScenAlertSource.
        if self._parent_actor_part is None and isinstance(parent, IScenAlertSource):
            self.__alert_parent = parent
        else:
            self.__alert_parent = None

        # Set the defaults

        if self._parent_actor_part is None and name is None:
            self._part_frame.name = "root_actor"
        self.__proxy_position = Position()
        self.__image_id = None
        self.__rotation_2d = 0.0
        self.__rotation_3d = Rotation3D()

        self.__children = []
        self.__children_index_from_id = {}
        self.__ifx_ports_left = []
        self.__ifx_ports_right = []

        # event queuing counters:
        self.__children_queue_props_refresh = True
        self.__children_queue_props = (False, 0, 0)

    def resolve_link_path(self, remaining_link_path: str) -> PartFrame:
        """
        This function recursively iterates through the input link path (that leads to the link's target Part)
        until the Part object referenced by the last segment of the link path is determined, at which point, a
        reference to the target object's PartFrame is returned.
        :param remaining_link_path: The link path that remains to be processed.
        :return: A reference to the object frame pointed to by the link path.
        :raises: InvalidLinkPathSegmentError Error results from an unresolvable link path segment ie. a segment
        which is not ".." or "[integer]
        """

        if LINK_PATH_DELIM in remaining_link_path:
            # Path still has multiple segments to consider...
            path_root, path_remainder = remaining_link_path.split(LINK_PATH_DELIM, 1)

            if path_root == PARENT_ACTOR_PATH:
                return self._parent_actor_part.resolve_link_path(path_remainder)

            elif path_root.isdigit():
                if (0 <= int(path_root)) and (int(path_root) < len(self.__children)):
                    return self.__children[int(path_root)].resolve_link_path(path_remainder)
                else:
                    raise InvalidLinkPathSegmentError("Invalid link path segment: " + path_root +
                                                      " in ActorPart:" + self._part_frame.name)
            else:
                raise InvalidLinkPathSegmentError("Invalid link path segment: " + path_root +
                                                  " in ActorPart:" + self._part_frame.name)

        else:
            # We're processing the last segment of the path...
            path_root = remaining_link_path
            if path_root.isdigit():
                if (0 <= int(path_root)) and (int(path_root) < len(self.__children)):
                    return self.__children[int(path_root)].part_frame
                else:
                    raise InvalidLinkPathSegmentError("Invalid link path segment: " + path_root +
                                                      " in ActorPart:" + self._part_frame.name)
            elif path_root == PARENT_ACTOR_PATH:
                return self._parent_actor_part.part_frame
            else:
                raise InvalidLinkPathSegmentError("Invalid link path segment: " + path_root +
                                                  " in ActorPart:" + self._part_frame.name)

    def get_proxy_pos(self) -> Tuple[float, float]:
        """Get the actor part's proxy position"""
        return self.__proxy_position.to_tuple()

    def set_proxy_pos(self, x: float, y: float):
        """
        Set the actor part's proxy position.
        :param x: New x position
        :param y: New y position
        """
        if x != self.__proxy_position.x or y != self.__proxy_position.y:
            self.__proxy_position = Position(x, y)
            if self._anim_mode_shared:
                self.signals.sig_proxy_pos_changed.emit(x, y)

    def get_geometry_path(self) -> str:
        """
        :return: Returns the geometry path of the part, which in human-speak means the path to the image or model file.
        """
        return self.get_image_path()

    def set_geometry_path(self, rhs: str):
        """
        Set the geometry path of the part (the image or model file path).
        :param rhs: The geometry path.
        """
        self.set_image_path(rhs)

    def get_rotation_2d(self) -> float:
        """
        :return: Returns the 2D rotation angle of the part. Positive is clockwise.
        """
        return self.__rotation_2d

    def set_rotation_2d(self, rotation_2d: float):
        """
        :param rotation_2d: The new value.
        """
        if self.__rotation_2d == rotation_2d:
            return

        self.__rotation_2d = rotation_2d
        if self._anim_mode_shared:
            self.signals.sig_rotation_2d_changed.emit(rotation_2d)

    def get_rotation_3d(self) -> Rotation3D:
        """
        :return: Returns the 3D rotation angle of the part.
        """
        return self.__rotation_3d

    def get_children(self) -> List[BasePart]:
        """
        :return: Returns the list of child Parts belonging to this Actor Part instance.
        """
        return self.__children

    def get_num_children(self) -> int:
        """Number of children parts of this Actor"""
        return len(self.__children)

    def get_child(self, unique_id: int) -> BasePart:
        """
        Get a child by unique ID.
        :param unique_id: value obtained from one of the emitted signals (sig_child_added etc)
        :return: part with given ID
        :raise IndexError: if no child has given ID
        """
        return self.__children[self.__children_index_from_id[unique_id]]

    def get_child_by_name(self, name: str) -> BasePart:
        """
        Get a child by part name.
        :param name: name of part to get
        :return: first part found that has frame with given name
        """
        for child in self.__children:
            if child.name == name:
                return child

        raise ValueError("Actor '{}' has no child named '{}'".format(self.get_path(with_root=True), name))

    def get_first_descendant(self, filter: DescendantFilterCallable = None, name: str = None) -> BasePart:
        """
        Get the first descendant that matches a condition.
        :param filter: a function that gets called with each part of the scenario as argument, and returns True
            only when a desired condition is met; if filter is None, the name must be given as argument
        :param name: if filter is None, a filter will be created to filter on a name
        :return: the first part found that had filter(part) == True, or None if no part found
        """
        if filter is None:
            filter = lambda part: part.part_frame.name == name

        for part in self.__children:
            if filter(part):
                return part

            # if the part has descendants, try them:
            try:
                result = part.get_first_descendant(filter)
                if result is not None:
                    return result
            except:
                pass

        return None

    @override(BasePart)
    def get_all_descendants_by_id(self, id_map: Dict[int, BasePart]):
        """Put all the descendants of this actor into the given ID map"""
        for child in self.__children:
            id_map[child.SESSION_ID] = child
            child.get_all_descendants_by_id(id_map)

    def get_all_descendants(self, filter_func: DescendantFilterCallable = None, name: str = None) -> List[BasePart]:
        """
        Get all descendants that match a condition. The condition can be a filter function, or a part name
        (but not both).

        :param filter_func: a function that gets called with each part of the scenario as argument, and returns True
            only when a desired condition is met; if filter is None, the name must be given as argument
        :param name: filter on a part name (filter_func must be None else ignored)
        :return: list of all parts found that have filter(part) == True (empty list if no parts found meeting condition)
        """
        if filter_func is None:
            filter_func = lambda part: part.part_frame.name == name

        results = []
        for part in self._children:
            if filter_func(part):
                results.append(part)

            # get results from any descendants:
            try:
                more_results = part.get_all_descendants(filter_func)
            except:
                pass
            else:
                results.extend(more_results)

        return results

    def create_child_part(self, new_part_type: str, name: str = None, pos: Position = None,
                          **child_init_kwargs: Dict[str, Any]) -> BasePart:
        """
        Create a new part in this actor.
        :param new_part_type: The type of part that is to be added to the actor.
        :param name: optional, name for the part
        :param pos: optional, a set of xy position part coordinates
        :return: the created part
        """
        PartClass = get_part_class_by_name(new_part_type)
        if PartClass is None:
            raise ValueError('Part type "{}" is not recognized'.format(new_part_type))
        elif not PartClass.USER_CREATABLE:
            raise ValueError('Part type "{}" is not creatable (only copyable and movable)'.format(new_part_type))

        log.debug("Actor {} creating child part of type '{}'", self, new_part_type)
        new_part = PartClass(self, name=name, **child_init_kwargs)
        frame = new_part.part_frame
        if pos:
            frame.set_pos_from_vec(pos)
        self.__accept_child(new_part)
        log.debug("Actor {} done creating child part {}", self, new_part)
        return new_part

    def create_child_part_from_ori(self,
                                   ori_data: OriScenData,
                                   context: OriContextEnum,
                                   refs_map: Dict[int, BasePart],
                                   resolve_links: bool = False,
                                   paste_offset: Tuple[float, float] = None,
                                   max_ifx_level: int = None) -> BasePart:
        """
        Create a new part in this actor from an ori data dictionary.
        :param ori_data: The data dictionary describing the part to create.
        :param context: The context of the current create operation.
        :param refs_map: map of ORI data "parts" (by key) to created scenario part (for each part created)
        :param resolve_links: True to attempt to resolve ORI links to real links
        :param paste_offset: by how much to move parts along x and y
        :param max_ifx_level: if an integer (must be >= 0), the ifx level of the child will be capped at this value,
            and that of each grand-child will be capped at this value + 1 (and so recursively for grand-children that 
            are actors)
        :raise: UnsupportedPartTypeError A part type specified in the loaded scenario file is unrecognized by the
            software.
        """
        part_type_str = ori_data[CpKeys.TYPE]
        PartClass = get_part_class_by_name(part_type_str)
        if PartClass is None:
            msg = "Unsupported part type ({}) loaded from scenario file."
            log.error(msg, part_type_str)
            raise UnsupportedPartTypeError(msg.format(part_type_str))

        child = PartClass(self)
        child.set_from_ori(ori_data, context=context, resolve_links=False, refs_map=refs_map,
                           max_ifx_level=max_ifx_level)
        if paste_offset is not None:
            child.part_frame.pos_x += paste_offset[0]
            child.part_frame.pos_y += paste_offset[1]
        if CpKeys.REF_KEY in ori_data:
            refs_map[ori_data[CpKeys.REF_KEY]] = child

        self.__accept_child(child)  # NOTE: signals existence of new child

        if resolve_links:
            drop_dangling = False if context == OriContextEnum.save_load else True
            self._resolve_ori_link_paths(refs_map, drop_dangling, pos_offset=paste_offset, moved_parts=[child])

        log.debug("Done creating child part {} from ORI def", child)
        return child

    def remove_child_part(self, part: BasePart, restorable: bool = False) -> RestorePartInfo:
        """
        Remove a child part from this actor:
        - remove its links
        - set its ifx level to 0 (since don't know where it will be restored, and need to remove all ports); this
            - removes elevated source links
            - removes its ports above
            - if the part has children, the ifx level of every descendant that is exposed on part is lowered
              to just below this part thus maintaining any "internal" links but breaking links that go beyond
              this part's domain
        - remove it from self's list of children
        - notify it that self is no longer its parent
        - if the part itself has children, these are notified that they are no longer in the scenario (recursively
          down the tree of descendants), but they are not removed from their parent part (this minimizes how
          much work has to be done on the scenario to restore it)
        - emits sig_child_deleted signal

        :param part: The child part to be deleted from the list of children.
        :param restorable: True if the part being deleted should be restorable following a delete; False otherwise.

        :return: None if restorable=False; otherwise, returns restoration info for restoring the current
            instance
        """
        log.debug('Removing incoming and outgoing links for {}', self)
        restore_out_links_info = part.part_frame.remove_outgoing_links(restorable=restorable)
        restore_in_links_info = part.part_frame.remove_incoming_links(restorable=restorable)

        restore_ifx_level = part.part_frame.set_ifx_level(0, break_bad=True, restorable=restorable)

        log.debug("Abandoning child {}", part)
        self.__children.remove(part)

        if restorable:
            # position must be saved because a paste can move it to a different position; for example,
            # cut -> paste at diff pos -> undo paste (removes again) -> undo cut (needs to restore pos
            # modified by paste)
            position = part.part_frame.get_pos_vec()
            restore_part_info = RestorePartInfo(self, position, restore_out_links_info,
                                                restore_in_links_info, restore_ifx_level)
            part.remove_by_parent(part_restore=restore_part_info)
        else:
            restore_part_info = None
            part.remove_by_parent()

        # TODO build 3: for now, always regenerate the children indices, but should do this only when necessary:
        self.__regen_children_indices()

        # After child has been deleted, notify any listeners.
        if self._anim_mode_shared:
            self.signals.sig_child_deleted.emit(part.SESSION_ID)

        return restore_part_info

    def remove_child_parts(self, parts: List[BasePart], restorable: bool = False) -> Optional[List[RestorePartInfo]]:
        """
        Delete multiple parts. This calls remove_child_part() on each part and returns a list of restoration
        info. The ordering in the list matters.

        :param parts: the list of parts to delete
        :param restorable: whether the removal can be restored
        :return: if restorable=True, the list of restoration info to provide to restore_child_parts; else, None
        """
        # verify that all parts to be removed are our children; assertion adequate assuming this is not in the
        # scripting API, else it should be a proper check with ValueError exception:
        assert set(parts).issubset(self.__children)

        if restorable:
            restore_parts_info = []
            for part in parts:
                restore_part_info = self.remove_child_part(part, restorable=True)  # , broken_elevated=False)
                restore_parts_info.append(restore_part_info)
                assert not part.in_scenario

            return restore_parts_info

        else:
            for part in parts:
                self.remove_child_part(part)

            return None

    def restore_child_part(self, part: BasePart, restore_info: RestorePartInfo,
                           paste_offset: Vector = None,
                           single_op: bool = True) -> UnrestorableLinks:
        """
        Restore a part into this actor instance. By default, links are also restored, and if part is an actor,
        the ifx level of every descendant of that actor, exposed on that actor's interface, is restored too.

        If self was the original parent of part, then after adding
        the part, any ifx ports representing it at higher levels are restored in the order/side they had originally
        (assuming, as usual, that restore_child_part() and other restoration methods are called in the reverse
        order in which they were removed.

        If self was not the original parent of part, then restoring it into self corresponds to moving it into
        this actor, after having been cut via a remove_child_part/s on another actor. If links are restored,
        only links that are valid once the part is moved into this actor are restored; dropped links are returned.

        :param part:  the part object to be restored to this actor, after having been deleted from this or
            another actor
        :param restore_info: Information sufficient for restoring the specified part to its pre-deleted state
            within this instance.
        :param paste_offset: An x,y offset (in scenario units) to move the part by, once restored
        :param single_op: if True, this is a single restoration so restore the links and emit the sig_parts_restored;
            if False, it is one of a set of restorations so do not restore links (since all parts need to exist
            first) and do not emit the sig_parts_restored (since the signal will be emitted for the set).

        :return: None if links=False; otherwise, an instance of UnrestorableLinks which holds links that could not be
            restored (usually because the interface levels are insufficient, which occurs when self is not the
            original parent of part). When self is original parent, there should be no dropped links
        """
        log.debug("Restoring child {}", part)

        assert part.parent_actor_part is None
        self.__children.append(part)
        self.__children_index_from_id[part.SESSION_ID] = len(self.__children) - 1
        part.restore_by_parent(restore_info, self)

        if paste_offset is not None:
            current_pos = part.part_frame.get_pos_vec()
            part.part_frame.set_pos_from_vec(current_pos + paste_offset)

        if restore_info.restore_ifx_level is not None:
            part.part_frame.restore_ifx_level(restore_info.restore_ifx_level, links=single_op)

        if single_op:
            dropped_links = UnrestorableLinks()
            part.restore_links(restore_info, dropped_links, waypoint_offset=paste_offset)
            assert dropped_links.empty() or restore_info.parent_part is not self
        else:
            dropped_links = None

        log.debug("Restored child {}", part)

        # Notify any listeners of the event.
        if self._anim_mode_shared:
            self.signals.sig_child_added.emit(part)
            if single_op:
                self.signals.sig_parts_restored.emit([part.SESSION_ID])

        return dropped_links

    def restore_child_parts(self, parts: List[BasePart], restore_infos: List[RestorePartInfo],
                            paste_offset: Vector = None) -> UnrestorableLinks:
        """
        Restore multiple parts. The order of parts does not matter as the parts are first restored, then their links.

        :param parts: the list of parts to restore, that were deleted via delete_child_parts
        :param restore_infos: the list of restoration infos, as returned by delete_child_parts
        :param paste_offset: position offset along x and y for pasting
        :return: list of links that could not be restored (because their source and/or target had
            insufficient ifx level)
        """
        log.debug("Pasting parts {} into {}", parts_to_str(parts), self)

        # First restore all the parts, without linkages:
        for part, restore_info in zip(parts, restore_infos):
            self.restore_child_part(part, restore_info, paste_offset=paste_offset, single_op=False)

        # With all the parts in place, can now restore all the links that remain valid;
        # links that would be invalid because ifx levels are insufficient are dropped:
        dropped_links = UnrestorableLinks()
        for part, restore_info in zip(parts, restore_infos):
            no_waypoints = None if paste_offset is None else parts
            part.restore_links(restore_info, dropped_links, waypoint_offset=paste_offset, no_waypoints=no_waypoints)

        if self._anim_mode_shared:
            self.signals.sig_parts_restored.emit([p.SESSION_ID for p in parts])

        return dropped_links

    def unrestore_child_parts(self, parts: List[BasePart],
                              restore_infos: List[RestorePartInfo],
                              paste_offset: Vector = None):
        """
        Undo the work done by restore_child_parts(). This removes the parts and links. Parameters
        are the same as those of restore_child_parts().

        :param parts: list of parts to unrestore
        :param restore_infos: list of restoration info (same order as parts)
        :param paste_offset: offset to unmove from
        """
        self.remove_child_parts(parts, restorable=True)

    def restore_waypoints(self, map_links_to_waypoints: Dict[PartLink, List[LinkWaypoint]], indices: List[int]):
        """
        Restores waypoints that have been previously deleted.
        :param map_links_to_waypoints:  A mapping of links and their associated waypoints
        :param indices:  The indices of the waypoints on the links, necessary so that links are restored
            in their correct order
        """
        for index, (link, waypoints) in enumerate(map_links_to_waypoints.items()):
            link.restore_waypoints(waypoints, sorted(indices[index]))

        self.signals.sig_waypoints_restored.emit(map_links_to_waypoints)

    def check_links_restoration(self, parts: List[BasePart],
                                restore_infos: List[RestorePartInfo]) -> Dict[PartLink, RestoreLinkInfo]:
        """
        Check whether restoring a set of parts within this actor would require breaking links. The returned
        object contains the links that would be broken by reparent_child_parts(parts, restore_infos,
        maintain_links=False).

        :param parts: parts to check
        :param restore_infos: the restoration info for the parts
        :return: map of links that would not be valid after a restore; the value is the restoration info
            for the link, obtained from the restore_infos
        """
        invalid = {}
        for part, restore_info in zip(parts, restore_infos):
            # note that each one of those parts is currently in_scenario=False
            assert not part.in_scenario

            # check if each part's outgoing links, when their source parent is self, are linkable:
            for link, info in restore_info.outgoing_links_info.items():
                link_source = LinkTip(info.source_frame, parent_part=self)
                if not PartLink.check_linkable(link_source, LinkTip(info.target_frame)):
                    invalid[link] = info

            # check if each part's incoming links, when their target parent is self, are linkable:
            for link, info in restore_info.incoming_links_info.items():
                link_target = LinkTip(info.target_frame, parent_part=self)
                if not PartLink.check_linkable(LinkTip(info.source_frame), link_target):
                    invalid[link] = info

            # if the part is an actor that had exposed children (because of their interface level), they may have
            # links that had to be broken too:
            for port_frame, restore in restore_info.actor_domain_ifx_ports:
                assert not port_frame.part.in_scenario

                # for each outgoing link broken, could it be restored, if self is actual root of its source's branch:
                for link, info in restore.broken_links_out.items():
                    link_source = LinkTip(info.source_frame, root_part=self)
                    if not PartLink.check_linkable(link_source, LinkTip(info.target_frame)):
                        invalid[link] = info

                # for each incoming link broken, could it be restored, if self is actual root of its target's branch:
                for link, info in restore.broken_links_in.items():
                    link_target = LinkTip(info.target_frame, root_part=self)
                    if not PartLink.check_linkable(LinkTip(info.source_frame), link_target):
                        invalid[link] = info

        return invalid

    def reparent_child_parts(self, parts: List[BasePart],
                             restore_infos: List[RestorePartInfo],
                             maintain_links: bool = True,
                             paste_offset: Vector = None) -> RestoreReparentInfo:
        """
        Restore parts into this actor.

        :param parts: Parts to restore
        :param restore_infos: the restoration info for each part, assumed to be in same order as parts, and
            obtained from the latest call to remove_child_parts().
        :param maintain_links: if False, links to and from parts not in "parts" argument will not be restored;
            if True, the parts that would become unlinked will have their ifx level adjusted so the link can
            be restored.
        :param paste_offset: x,y offset in scenario coordinates
        :return: restoration info that can be given to unreparent_child_parts() to undo reparenting
        """
        # now restore child parts with us as new parent:
        dropped_links = self.restore_child_parts(parts, restore_infos, paste_offset=paste_offset)

        # if maintaining links, they have to be restored to a valid state:
        restore_ifxs = {}
        if maintain_links:
            for link, restore in chain(dropped_links.outgoing.items(), dropped_links.incoming.items()):
                revert_ifx_changes = link.restore_valid(restore)
                restore_ifxs.update(revert_ifx_changes)

        return RestoreReparentInfo(restore_ifxs, paste_offset, restore_infos)

    def unreparent_child_parts(self, child_parts: List[BasePart], restore: RestoreReparentInfo):
        """
        Remove a set of parts previously reparented, such that their state is same as prior to the reparenting.
        :param child_parts: the parts to remove
        :param restore: restoration data so the reparenting can be reversed
        """
        # First restore the ifx level of each part that was further exposed by the reparenting (this
        # happened only if maintain_links was True). This will break any links that were created to maintain links
        # at those higher interface levels. These links may have been given waypoints after the reparenting,
        # so their restoration info must be returned to caller in case of a re-reparent later:
        for part_frame, restore_ifx in restore.ifx_levels.items():
            assert not restore_ifx.broken_links_out
            assert not restore_ifx.broken_links_in
            assert restore_ifx.level_increased()
            # break all links created to maintain connections:
            part_frame.set_ifx_level(restore_ifx.from_level, break_bad=True, restorable=True)

        # now removing child_parts will hide those descendant parts again, restoring them to what they were before
        # reparenting child_parts.
        # Also, although we don't need the restoration data, the parts may be restored using the another
        # reparent_child_parts() call, so restorable must be True:
        self.remove_child_parts(child_parts, restorable=True)
        for part, pos in zip(child_parts, restore.parts_pos):
            part.part_frame.set_pos_from_vec(pos)

    @override(BasePart)
    def remove_by_parent(self, part_restore: RestorePartInfo = None):
        """
        WARNING: MUST ONLY BE CALLED BY PARENT ACTOR.

        When self is an actor being removed by its parent, it lowers the interface level of all parts
        exposed on its boundary so that their are no ports left on it, which breaks any links to/from those parts
        that go outside of this actor. (Note: parts exposed on self boundary are different from the ports that
        expose self on boundary of parents -- removing those is via self._remove_ifx_ports()).

        :param part_restore: restoration info for this actor part
        """
        # first decrease the interface level so that self is boundary actor for each ifx port
        restorable = (part_restore is not None)
        restore_ifxs = part_restore.actor_domain_ifx_ports if restorable else None
        ifx_ports = self.__ifx_ports_left + self.__ifx_ports_right
        for part_frame in ifx_ports:
            restore_ifx = part_frame.set_ifx_boundary(self, restorable=restorable)
            if restorable:
                restore_ifxs.append((part_frame, restore_ifx))  # order must be preserved

        # the above loop should have deleted all ports:
        assert not self.__ifx_ports_left and not self.__ifx_ports_right

        # NOW we can detach from parent:
        super().remove_by_parent(part_restore=part_restore)

    @override(BasePart)
    def restore_by_parent(self, restore_part_info: RestorePartInfo, parent: Decl.ActorPart):
        """
        When restoring actor by its parent, the ifx level of each part that was on its ifx boundary
        must be restored too.
        """
        # need to first restore reference to parent so that self's children can reach up past self:
        super().restore_by_parent(restore_part_info, parent)

        # restore all originally exposed parts to their original ifx level; this will also restore
        # each one's interface ports and links that were broken as a result of lowering the
        for part_frame, restore_ifx_level in reversed(restore_part_info.actor_domain_ifx_ports):
            part_frame.restore_ifx_level(restore_ifx_level, links=False)

    @override(BasePart)
    def restore_links(self, restore_part_info: RestorePartInfo, dropped_links: UnrestorableLinks,
                      waypoint_offset: Vector = None, no_waypoints: List[BasePart] = None):
        """
        When restoring links on an actor, the links to and from parts on the actor's ifx boundary
        must be restored too.
        """
        super().restore_links(restore_part_info, dropped_links, waypoint_offset=waypoint_offset,
                              no_waypoints=no_waypoints)

        # now the links for ports can be recreated:
        for part_frame, restore_port_info in restore_part_info.actor_domain_ifx_ports:
            if restore_port_info.broken_links_out:
                assert restore_port_info.level_decreased()
                dropped_out = part_frame.restore_outgoing_links(restore_port_info.broken_links_out,
                                                                waypoint_offset=waypoint_offset,
                                                                no_waypoints=no_waypoints)
                dropped_links.outgoing.update(dropped_out)

            if restore_port_info.broken_links_in:
                assert restore_port_info.level_decreased()
                dropped_in = part_frame.restore_incoming_links(restore_port_info.broken_links_in,
                                                               waypoint_offset=waypoint_offset,
                                                               no_waypoints=no_waypoints)
                dropped_links.incoming.update(dropped_in)

    def copy_parts(self, parts_to_copy: List[BasePart], context: OriContextEnum = OriContextEnum.copy,
                   paste_offset: Vector = None) -> List[BasePart]:
        """
        This function creates deep copies of the input parts and adds them as child parts to this instance. The linking
        of the copies is resolved after the copies have been added as children.

        :param parts_to_copy: The parts to be copied into this instance.
        :param context: The context under which the parts are being copied. The context can be either a copy
            operation where parts are copied into this Actor within the current scenario, or the context can be an
            export operation where the parts are copied into this Actor as part of the creation of a new scenario
            that will contain 'exported' parts and be saved to file.
        :param paste_offset: the relative position offset from the original copied part.
        :return: The list of newly created children.
        """
        log.debug("Copying parts {}", parts_to_str(parts_to_copy))
        if paste_offset is not None:
            log.debug("Copy offset is {:.5}", paste_offset)
        assert context in (OriContextEnum.export, OriContextEnum.copy)
        new_children = []

        # clone all input parts and create mappings between original parts and copies
        refs_map = {}  # {int: BasePart}
        for orig_part in parts_to_copy:
            ori_def = orig_part.get_ori_def(context)
            new_part = self.create_child_part_from_ori(ori_def, context, refs_map,
                                                       paste_offset=paste_offset, max_ifx_level=0)
            new_children.append(new_part)

            if context != OriContextEnum.copy:
                # in case original part linked to its parent, need to add self (parent of new part) to refs_map
                # for original parent ORI ref key; don't want this for pure copy (context), since in copy, links to
                # parent are not preserved:
                refs_map[orig_part.parent_actor_part.ori_ref_key] = self

        # Create the copied links
        self._resolve_ori_link_paths(refs_map, True, pos_offset=paste_offset, moved_parts=new_children)

        if context == OriContextEnum.copy:
            self.signals.sig_parts_copied.emit([child.SESSION_ID for child in new_children])

        return new_children

    def search_parts(self, re_pattern: str, new_search: bool = True) -> Dict[BasePart, List[str]]:
        """
        Recursively search this part and all children for properties with string value that matches a pattern.

        :param re_pattern: pattern to match
        :param new_search: if True, indicates that this actor is the start and end of a search; else,
            it is a child being searched as a result of a search started further up the actor hierarchy
        :return: dictionary where each key is a part that matched pattern in some property, and value is
            a list of property names on the part

        Example: actor.search_parts('ct.*1$') returns {'a1': ['part_frame.name'], 'a1/f1': ['script']}
            if actor has a child actor named actor1 and actor1 has a child function with a script "print('actor1')"
        """
        parts_found = {}

        if new_search:
            self._shared_scenario_state.start_search()
        else:
            if self._shared_scenario_state.is_search_cancelled():
                return parts_found
            assert self._shared_scenario_state.is_search_in_progress()

        # search this specific actor:
        # Cindy TODO: only if self.PART_CATEG matches filter; add flag to exclude frame (True if frame=False)
        actor_matches = self.get_matching_properties(re_pattern)
        if actor_matches:
            parts_found[self] = actor_matches
            self._shared_scenario_state.add_search_result(self, actor_matches)

        # search each child:
        for child in self.__children:
            self._shared_scenario_state.update_search_progress(child.path)
            if child.PART_TYPE_NAME == self.PART_TYPE_NAME:
                # child is an actor, recurse:
                results = child.search_parts(re_pattern, new_search=False)
                parts_found.update(results)

            else:
                # Cindy TODO: only if child.PART_CATEG matches filter; add flag to exclude frame (True if frame=False)
                child_matches = child.get_matching_properties(re_pattern)
                if child_matches:
                    parts_found[child] = child_matches
                    self._shared_scenario_state.add_search_result(child, child_matches)

            if self._shared_scenario_state.is_search_cancelled():
                break

        if new_search:
            self._shared_scenario_state.end_search()

        return parts_found

    def set_child_queueing_changed(self):
        """
        Sets flag indicating that direct executable children have been added or removed from the sim event queue
        and emit signal. Propagates this to ancestor parents. Each ancestor parent will therefore emit a signal
        that event counts have changed. The recipient can ask for the queue count; only the first request bears
        a higher cost, since the data is cached and the cached flagged as dirty only when this method is called.
        """
        self.__children_queue_props_refresh = True

        if self._anim_mode_shared:
            if self._parent_actor_part is not None:
                self._parent_actor_part.set_child_queueing_changed()

            # indicate that get_queue_counts() should be called:
            log.debug("Actor {} emitting for counters changed", self.path)
            self.signals.sig_queue_actor_counters_changed.emit()

    def get_queue_counts(self) -> Tuple[bool, int, int]:
        """
        Returns a triplet (is_next, count_concurrent_next, count_after_next). This is an expensive function
        as it must traverse the tree, cumulating the counts. Therefore, the counts are cached: the tree will
        only be traversed if necessary (ie if self.set_child_queueing_changed() called)
        """
        if not self.__children_queue_props_refresh:
            return self.__children_queue_props

        count_concur_next, count_after_next = 0, 0
        is_child_next = False
        for child in self.__children:
            try:
                counts = child.get_queue_counts()
            except Exception:
                # Then part does not have queue counters
                pass
            else:
                is_child_next |= counts[0]
                count_concur_next += counts[1]
                count_after_next += counts[2]

        self.__children_queue_props_refresh = False
        self.__children_queue_props = (is_child_next, count_concur_next, count_after_next)
        return self.__children_queue_props

    def get_image_id(self) -> int:
        """
        This function returns the id of the image associated with this Actor part instance.

        This function has primarily been implemented to support the scripting API offered by the prototype.

        :return: This instance's image ID.
        """
        return self.__image_id

    def set_image_id(self, image_id: int):
        """
        This function sets the Actor's image ID. The ID corresponds to an already loaded image file. The image
        dictionary's reference count is updated for the image.

        This function has primarily been implemented to support the scripting API offered by the prototype.

        :param image_id: The ID of the image to be associated with this Actor part instance.
        """

        if image_id is None and self.__image_id is not None:
            self.remove_image()

        elif image_id != self.__image_id:
            orig_image_id = self.__image_id

            image_dict = self.shared_scenario_state.image_dictionary
            try:
                image_dict.add_image_reference(image_id)
                self.__image_id = image_id
            except KeyError as e:
                self.__image_id = None
                log.error("Part: {} unable to set part image. Error: {}", str(self), str(e))

            if orig_image_id is not None:
                try:
                    image_dict.subtract_image_reference(image_id=orig_image_id)
                except KeyError as e:
                    log.error("Part: {} unable to remove its reference to an image from the Image Dictionary. "
                              "Error: {}", str(self), str(e))

            if self._anim_mode_shared:
                self.signals.sig_image_changed.emit(self.get_image_path())

    def set_image_path(self, image_path: str):
        """
        This function sets the image that is to be associated with the current Actor part instance. The path
        is translated into an image ID by the image dictionary and the image ID is stored by this instance.
        :param image_path: The image file path of the image to be associated with this instance.
        """
        if image_path is None:
            if self.__image_id is not None:
                self.remove_image()
            else:  # nothing to do
                pass

        else:
            image_dict = self._shared_scenario_state.image_dictionary
            self.__image_id = image_dict.new_image(image_path)

        if self._anim_mode_shared:
            self.signals.sig_image_changed.emit(self.get_image_path())

    def get_image_path(self) -> Either[str, None]:
        """
        This function returns the image path corresponding to the image ID stored by this part or None to indicate
        default image.
        :return: The path to the associated image file.
        """

        if self.image_id is None:
            return None

        image_dict = self._shared_scenario_state.image_dictionary
        try:
            image_path = image_dict.get_image_path(self.__image_id)
        except Exception as e:
            log.error("Part: {} is unable to retrieve the pathname of its associated image from the Image Dictionary. "
                      "Error: {} Part will assume its 'error' image. Image should be reset.", str(self), str(e))
            return "Unresolved image path"

        return image_path

    def remove_image(self):
        """
        This function clears the image id value associated with this Actor part instance causing the image
        associated with this Actor part instance to be reverted to the default image.
        """
        if self.__image_id is not None:
            image_dict = self._shared_scenario_state.image_dictionary
            try:
                image_dict.subtract_image_reference(image_id=self.__image_id)
            except KeyError as e:
                log.error("Part: {} unable to remove its reference to an image from the Image Dictionary. "
                          "Error: {}", str(self), str(e))

            self.__image_id = None

            if self._anim_mode_shared:
                self.signals.sig_image_changed.emit(None)

    def load_image_file(self, node_path: Decl.Panda3dNodePath):
        """
        This function raises a NotImplemented error. It is part of the prototype API, but it cannot be implemented
        because it takes a Panda3d NodePath object as input, and Panda3d is not supported by Origame.
        :param node_path: A Panda3d NodePath object describing the 2-D image to be associated with this Actor part
            instance.
        :raises NotImplementedError: Raised if this function is called.
        """
        raise NotImplementedError("The load_image() function is a prototype API function, but is not suppported by"
                                  "Origame. Consider the set_image_path() function on the Actor part API instead.")

    def get_ifx_ports(self, side: ActorIfxPortSide = ActorIfxPortSide.both) -> List[PartFrame]:
        """
        Get the interface parts for this actor.
        :param side: which side of interest, or leave to default for both
        :return: a list of PartFrame instances, representing the part frames exposed on this actor's interface
        """
        if side == ActorIfxPortSide.both:
            return self.__ifx_ports_left + self.__ifx_ports_right
        elif side == ActorIfxPortSide.left:
            return self.__ifx_ports_left
        else:
            assert side == ActorIfxPortSide.right
            return self.__ifx_ports_right

    def switch_ifx_port_side(self, descendant_frame: PartFrame, restorable: bool = True) -> RestoreIfxPortInfo:
        """
        Switch the interface port associated with a part frame to the other side of this actor.
        :param descendant_frame: the part frame for which interface port must switch sides
        :param restorable: if True, return restoration info so port side can be restored
        :return: restoration info to give to restore_ifx_port_side() for restoring side
        """
        if descendant_frame in self.__ifx_ports_left:
            from_bin = self.__ifx_ports_left
            to_bin = self.__ifx_ports_right
            from_left = True
        else:
            from_bin = self.__ifx_ports_right
            to_bin = self.__ifx_ports_left
            from_left = False

        from_index = from_bin.index(descendant_frame)
        if restorable:
            result = RestoreIfxPortInfo(from_index, from_left)
        else:
            result = None
        to_bin.append(from_bin.pop(from_index))

        self.signals.sig_ifx_port_side_changed.emit(descendant_frame, from_left, len(to_bin) - 1)
        return result

    def restore_ifx_port_side(self, descendant_frame: PartFrame, restore_info: RestoreIfxPortInfo):
        """
        Restore the interface port associated with a part frame to the original side.
        :param descendant_frame: part frame for which port side should be restored
        :param restore_info: the restoration info obtained from switch_ifx_port_side
        """
        if restore_info.left_side:
            from_bin = self.__ifx_ports_right
            to_bin = self.__ifx_ports_left
            from_left = False
        else:
            from_bin = self.__ifx_ports_left
            to_bin = self.__ifx_ports_right
            from_left = True

        from_index = from_bin.index(descendant_frame)
        to_bin.insert(restore_info.index, from_bin.pop(from_index))

        self.signals.sig_ifx_port_side_changed.emit(descendant_frame, from_left, restore_info.index)

    def move_ifx_port_index(self, descendant_frame: PartFrame,
                            steps: int,
                            restorable: bool = True) -> RestoreIfxPortIndexInfo:
        """
        Move a descendant part's interface port up or down along the side it is currently on.
        :param descendant_frame: the part frame that is child or grand-child etc
        :param steps: how many steps to move up (negative) or down (positive)
        :param restorable: True to create the restoration info so the port can be moved back to where it was
        :return: restoration info if restorable=True, else None
        """
        if descendant_frame in self.__ifx_ports_left:
            bin = self.__ifx_ports_left
            left = True
        else:
            bin = self.__ifx_ports_right
            left = False

        result = None

        from_index = bin.index(descendant_frame)
        to_index = from_index + steps
        if to_index < 0:
            to_index = 0
        if to_index >= len(bin):
            to_index = len(bin) - 1
        if to_index != from_index:
            bin.insert(to_index, bin.pop(from_index))
            if restorable:
                result = RestoreIfxPortIndexInfo(from_index, left, to_index)
            self.signals.sig_ifx_port_index_changed.emit(from_index, left, to_index)

        return result

    def restore_ifx_port_index(self, descendant_frame: PartFrame, restore: RestoreIfxPortIndexInfo):
        """
        Restore the port to its previous location up or down the side that it is currently on
        :param descendant_frame: part frame for which to restore interface port index
        :param restore: restoration info obtained from move_ifx_port_index() (if restorable was True)
        """
        bin = self.__ifx_ports_left if restore.left_side else self.__ifx_ports_right
        assert bin[restore.to_index] is descendant_frame
        bin.insert(restore.from_index, bin.pop(restore.to_index))
        self.signals.sig_ifx_port_index_changed.emit(restore.from_index, restore.left_side, restore.to_index)

    def has_ifx_port(self, part_frame: PartFrame) -> bool:
        """Return True if this actor has an ifx port for the given part frame"""
        return part_frame in self.__ifx_ports_left or part_frame in self.__ifx_ports_right

    @override(BasePart)
    def on_frame_name_changed(self):
        """
        This function notifies the Actor that it's Part Frame name has changed. In turn, the Actor Part notifies
        each child that its parent's path (within the scenario) has changed.
        """
        try:
            for child in self.__children:
                child.on_parent_path_changed()

        except AttributeError:
            # This exception only occurs during ActorPart instantiation when the base class (BasePart) instantiates a
            # PartFrame object and sets its default name prior to the Actor Part's constructor having been run and
            # therefore prior to the creation of the self.__children attribute.
            pass

    @override(BasePart)
    def on_parent_path_changed(self):
        super().on_parent_path_changed()
        # forward the notification to children, since path of their parent (us) has changed too:
        for child in self.__children:
            child.on_parent_path_changed()

    @override(BasePart)
    def on_scenario_shutdown(self):
        exceptions = []
        for child in self.__children:
            try:
                child.on_scenario_shutdown()
            except Exception as exc:
                exceptions.append(str(exc))

        if exceptions:
            log.warning("Some exceptions occurred while shutdown of actor {}:", self)
            for exc_msg in exceptions:
                log.warning("    {}", exc_msg)
            log.warning("Send this information to tech support")

    @override(BasePart)
    def on_removing_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        super().on_removing_from_scenario(scen_data, restorable=restorable)

        # first notify children:
        for child in self.__children:
            child.on_removing_from_scenario(scen_data, restorable)

        # remove image and save it for later (if restorable=True)
        image_path = self.get_image_path()
        self.remove_image()
        if restorable:
            scen_data[self].update(image_path=image_path)

    @override(BasePart)
    def on_restored_to_scenario(self, scen_data: Dict[BasePart, Any]):
        BasePart.on_restored_to_scenario(self, scen_data)

        # first restore image path:
        restoration_info = scen_data[self]
        self.set_image_path(restoration_info['image_path'])

        # then notify children
        for child in self.__children:
            child.on_restored_to_scenario(scen_data)

        # the counters probably need to be updated at least once:
        self.set_child_queueing_changed()

    def fix_invalid_linking(self):
        """
        Find node linking that might be wrong. This is only necessary when importing prototype scenarios.
        """
        fixable_links, alt_fixable_links, unknown_fix_nodes = self.check_node_linking()
        fixes_required = bool(fixable_links or alt_fixable_links or unknown_fix_nodes)
        if not fixes_required:
            return

        # fix nodes that have more than one outgoing link
        if fixable_links:
            log.warning("Some nodes have more than one outgoing link; inverting them:")
            for link in fixable_links:
                link.replace_by_inverted()

        # warn about nodes that need fixing, but are only linked to nodes that don't have any outgoing links,
        # so could not be fixed:
        if alt_fixable_links:
            log.warning("Found {} link{} that could have been flipped instead of the previous ones",
                        len(alt_fixable_links), plural_if(alt_fixable_links))
            link_names = ', '.join(str(link) for link in alt_fixable_links)
            log.warning("    Links are: {}", link_names)
            log.warning("    Check whether any/all of these links should have been flipped instead")

        if unknown_fix_nodes:
            log.error("Found {} node{} with more than 1 outgoing link, but no way of knowing which link(s) to fix:",
                      len(unknown_fix_nodes), plural_if(unknown_fix_nodes))
            node_names = ', '.join(str(node) for node in unknown_fix_nodes)
            log.error("    Nodes are: {}", node_names)
            log.error("    Flip outgoing links of these nodes so each one has only one outgoing link")

        # ensure all fixable ones were fixed without breaking any other ones, and get remaining bad ones:
        fixable_links, alt_fixable_links, bad_nodes = self.check_node_linking()
        assert not fixable_links
        assert not alt_fixable_links  # this can't be non-empty if there are no fixable links
        assert set(bad_nodes) == set(unknown_fix_nodes)

        log.info("All possible inter-node linking fixes done")

    def check_node_linking(self) -> Tuple[List[PartLink], List[PartLink], List[Decl.NodePart]]:
        """
        Check each node in the actor and all children actors recursively for nodes that have more than one
        outgoing link and no outgoing link. This is used to "sanitize" Prototype scenarios.

        :return: a triplet consisting of a list of links that can be fixed by flipping; another list of links that
            could be flipped, instead of links from first list; and a list of nodes that break node invariant (1
            outgoing link) but no way of knowing how to fix

        A non-empty second list indicates that there are multiple ways of flipping links that originate from some
        nodes. A non-empty third list indicates that some nodes did not have an obvious fix.
        """
        fixable_links = []
        alt_fixable_links = []
        unknown_fix_nodes = []
        for child in self.__children:
            if child.PART_TYPE_NAME == NpKeys.PART_TYPE_NODE:
                out_links = child.part_frame.outgoing_links
                if len(out_links) > 1:
                    # nodes that have more than one link are bad:
                    invertible_links, alternate_fix_links = self.__get_invertible_links(out_links)
                    if invertible_links or alternate_fix_links:
                        fixable_links.extend(invertible_links)
                        alt_fixable_links.extend(alternate_fix_links)
                    else:
                        # no way of knowing how to fix it
                        unknown_fix_nodes.append(child)

            elif child.PART_TYPE_NAME == ApKeys.PART_TYPE_ACTOR:
                # recurse into children actors
                fw, wtno, un = child.check_node_linking()
                fixable_links.extend(fw)
                alt_fixable_links.extend(wtno)
                unknown_fix_nodes.extend(un)

        return fixable_links, alt_fixable_links, unknown_fix_nodes

    # prototype compatibility adjustments:
    get_icon = prototype_compat_method_alias(get_image_id, 'get_icon')
    set_icon = prototype_compat_method_alias(set_image_id, 'set_icon')
    load_image = prototype_compat_method_alias(load_image_file, 'load_image')

    # --------------------------- instance PUBLIC properties ----------------------------

    proxy_pos = property(get_proxy_pos)
    image_id = property(get_image_id, set_image_id)
    image_path = property(get_image_path, set_image_path)
    rotation_2d = property(get_rotation_2d, set_rotation_2d)
    rotation_3d = property(get_rotation_3d)
    children = property(get_children)
    num_children = property(get_num_children)

    # prototype compatibility adjustments:

    geometry_path = prototype_compat_property_alias(image_path, 'geometry_path')
    IconFilename = prototype_compat_property_alias(image_path, 'IconFilename')

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (image_path, rotation_2d)
    META_AUTO_SCRIPTING_API_EXTEND = (image_path, get_image_path, set_image_path, image_id, get_image_id,
                                      rotation_2d, get_rotation_2d, set_rotation_2d,
                                      num_children)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenAlertSource)
    def _get_alert_parent(self):
        # Override so also works when self is root actor (which does not have a parent actor, the default
        # returned by BasePart)
        return self.__alert_parent or BasePart._get_alert_parent(self)

    @override(IScenAlertSource)
    def _get_children_alert_sources(self) -> List[IScenAlertSource]:
        return self.__children

    @internal(PartFrame)
    def _add_ifx_port(self, descendant_frame: PartFrame, bottom_level: int, top_level: int):
        """
        Add an interface port to this actor and parents (recursively). Only call from a part frame.
        :param descendant_frame: the part frame to expose
        :param bottom_level: the lowest level from which to start adding; must be >= 1 when called
            from the part frame
        :param top_level: the top most level at which to add port

        Example: _add_ifx_port(part_frame, 1, 3) will add the port on actor that is parent of part frame's part,
        and on the two actors above that, but not beyond.
        """
        assert top_level >= bottom_level

        # find the first actor at which to remove ports
        parent = self
        for level in range(bottom_level - 1):
            parent = parent.parent_actor_part

        level = bottom_level
        while level <= top_level:
            parent.__add_ifx_port_solo(descendant_frame)
            parent = parent.parent_actor_part
            level += 1

    @internal(PartFrame)
    def _remove_ifx_ports(self, descendant_frame: PartFrame, bottom_level: int, top_level: int,
                          restoration: RestoreIfxPortsInfo = None):
        """
        Remove an interface port from this actor and parents (recursively). Only call from a part frame.

        :param descendant_frame: the part frame to un-expose
        :param bottom_level: the lowest level from which to start removing; must be >= 1 when called
            from the part frame
        :param top_level: the top most level from which to remove port
        :param restoration: the map in which to store the placement of each removed port on descendant_frame's
            ancestor actors

        Example: _remove_ifx_ports(part, 1, 3) will remove the port on actor that is parent of part frame's part,
        and on the two actors above that, but not beyond.
        """
        assert top_level >= bottom_level

        # find the first actor at which to remove ports
        parent = self
        for level in range(bottom_level - 1):
            parent = parent.parent_actor_part

        # now iterate, removing ports from that actor and all above, up to top_level - bottom_level time
        restorable = (restoration is not None)
        level = bottom_level
        while level <= top_level:
            try:
                index = parent.__ifx_ports_left.index(descendant_frame)
                removed_from_left = True
                del parent.__ifx_ports_left[index]
            except:
                index = parent.__ifx_ports_right.index(descendant_frame)
                removed_from_left = False
                del parent.__ifx_ports_right[index]

            if restorable:
                # order does not matter:
                restoration[parent] = RestoreIfxPortInfo(index, removed_from_left)

            parent.signals.sig_ifx_port_removed.emit(descendant_frame, removed_from_left)
            parent = parent.parent_actor_part
            level += 1

    @internal(PartFrame)
    def _restore_ifx_ports(self, descendant_frame: PartFrame,
                           restore_infos: RestoreIfxPortsInfo, from_to: Tuple[int, int] = None):
        """
        Restore interface ports that were removed, for a given descendant. Does nothing if restore_info is empty
        or None.
        :param descendant_frame: the part frame for which to restore ifx port
        :param restore_infos: the port restoration info for that part's hierarchy of actors

        Note that this method must handle the case where descendant_frame has been moved up or down the hierarchy,
        across the hierarchy, or has been moved indirectly up or down because one of its ancestors is being
        reparented.
        """

        max_level = descendant_frame.ifx_level
        if max_level < 1:
            # none of the ports can be restored!
            return

        if from_to is None:
            # whole hierarchy:
            from_level, to_level = 1, max_level
        else:
            from_level, to_level = from_to
            assert max_level >= 0
            if to_level > max_level:
                raise ValueError("to_level={} must be smaller than max_level={}".format(to_level, max_level))

        # starting from self, add a new port if there is no restoration info for it, or create a new port otherwise;
        # but only create/restore if the levels are between from_level and to_level and the root isn't reached first:
        parent = self
        level = 1
        while level <= to_level and parent is not None:
            if level >= from_level:
                if parent in restore_infos:
                    parent.__restore_ifx_port(descendant_frame, restore_infos[parent])
                else:
                    parent.__add_ifx_port_solo(descendant_frame)

            parent = parent.parent_actor_part
            level += 1

    @override(BasePart)
    def _resolve_ori_link_paths(self, refs_map: Dict[int, BasePart], drop_dangling: bool, **kwargs):
        """
        This function causes all link paths that exist below this instance in the scenario hierarchy to be resolved
        so that the link instances have references to their respective target objects.

        This function overrides the base class implementation so that it can first iterate through its children
        commanding them to resolve their link paths before calling the base class implementation to resolve this
        instance's own paths.

        Note: This function should NOT be called until all Parts comprising the current scenario have been
        instantiated.
        """
        BasePart._resolve_ori_link_paths(self, refs_map, drop_dangling, **kwargs)
        for child in self.__children:
            child._resolve_ori_link_paths(refs_map, drop_dangling, **kwargs)

    @override(BasePart)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum,
                           resolve_links: bool = True, refs_map: Dict[int, BasePart] = None,
                           max_ifx_level: int = None, **kwargs):
        """
        When setting state from ORI data, several steps needed:

        1. Set local state such as frame, geometry path etc
        2. Remove existing children
        3. Create all the children, including child actors
        4. Enable children to get references to each other
        5. Create outgoing links from children

        Note that this function calls self.create_child_part_from_ori() which in turn calls _set_from_ori_impl()
        on each child. Once all children have been instantiated, the parent Actor part can resolve the unresolved
        links of all its children.

        :param resolve_links: only resolve links between parts if this is True; otherwise assumes that link
            resolution will be done at some higher level of the actor hierarchy
        :param refs_map: add created children to map by ori_data[COMMON].REF_KEY; if empty, resolve links
            of all parts in and below this actor
        :param max_ifx_level: if an integer (must be > 0), the ifx level of the part will be capped at this value,
            and that of each child will be capped at this value + 1 (and so recursively for children that are actors)

        For other params, see set_from_ori() documentation in the base class.
        """

        # 1. Step 1: Set local state such as frame, geometry path etc

        BasePart._set_from_ori_impl(self, ori_data, context, max_ifx_level=max_ifx_level, **kwargs)

        part_content_ori = ori_data.get_sub_ori(CpKeys.CONTENT)

        if part_content_ori.get(ApKeys.PROXY_POS) is not None:
            xy = part_content_ori[ApKeys.PROXY_POS]
            x = xy[PosKeys.X]
            y = xy[PosKeys.Y]
            self.set_proxy_pos(x, y)

        if part_content_ori.get(ApKeys.ROTATION_2D):
            self.rotation_2d = part_content_ori[ApKeys.ROTATION_2D]

        if part_content_ori.get(ApKeys.ROTATION_3D) is not None:
            ori_rot = part_content_ori[ApKeys.ROTATION_3D]
            self.__rotation_3d = Rotation3D(
                roll=ori_rot[R3dKeys.ROLL],
                pitch=ori_rot[R3dKeys.PITCH],
                yaw=ori_rot[R3dKeys.YAW]
            )

        if part_content_ori.get(ApKeys.IMAGE_ID) is not None:
            if context == OriContextEnum.export:
                # During export operation, image pathname was stored in place of image ID in ORI data to facilitate
                # replication of image dictionary (which is necessary during export).
                self.image_path = part_content_ori[ApKeys.IMAGE_ID]  # this call updates image dictionary.
            else:
                self.image_id = part_content_ori[ApKeys.IMAGE_ID]
                image_dict = self._shared_scenario_state.image_dictionary
                self.image_id += image_dict.get_image_id_offset()
                # Verify that image id exists in image dict, then increase image ref count.
                try:
                    image_path = image_dict.get_image_path(self.__image_id)
                    image_dict.add_image_reference(self.__image_id)
                except Exception as exc:
                    log.error("Part: {} is unable to retrieve the pathname of its associated image from the "
                              "Image Dictionary. Error: {}", self, exc)

        # 2. Remove existing children

        self.remove_child_parts(self.__children.copy())
        assert self.__children == []

        # 3. Create all the children (recursively down actor hierarchy)

        if refs_map is None:
            refs_map = {}

        if resolve_links:
            # without a map, we are the "root" actor of the (load/copy/export/assign) operation: create map;
            # for all ops except copying, add self to it in case children linked to root (for copy, don't want
            # to link to copy of root parent)
            assert refs_map == {}
            root_linkage_key = ori_data.get(CpKeys.REF_KEY)
            if root_linkage_key is not None:
                # any type of copy operation (pure copy, export, etc) will have a refs map so would not go here:
                assert context in (OriContextEnum.save_load, OriContextEnum.assign)
                if root_linkage_key in refs_map:
                    assert refs_map[root_linkage_key] is self
                else:
                    refs_map[root_linkage_key] = self

            resolve_links = True

        # the context is same as for parent, except if context of parent is assign: then children context is copy,
        # because the children are new and hence copied not assigned.
        children_context = context
        if context == OriContextEnum.assign:
            log.debug("Assignment to actor {}: children being created from copied ORI (rather than assigned)", self)
            children_context = OriContextEnum.copy

        # may need to convert some socket nodes to free nodes:
        self.__socket_converter = SocketPartConverter()
        children_ori = part_content_ori.get_sub_ori_list(ApKeys.CHILDREN)

        # create each child, including temporary sockets which will be converted to free nodes in a later step:
        for index, child_ori in enumerate(children_ori):
            if max_ifx_level is not None:
                # max level of children is one higher than self
                max_ifx_level += 1
            part = self.create_child_part_from_ori(child_ori, children_context, refs_map, max_ifx_level=max_ifx_level)

            if part.PART_TYPE_NAME == SpKeys.PART_TYPE_SOCKET:
                self.__socket_converter.add_temp_socket(index, part)
            elif part.PART_TYPE_NAME == NpKeys.PART_TYPE_NODE:
                self.__socket_converter.add_node_ref(index, part)

        # 4. Enable converted sockets to get references to their nodes for positioning, and fix ifx port sides

        self.__socket_converter.resolve_ori_refs()
        # legacy scenario don't state which side ports are on, but when they do, the sides have to be honored:
        if ApKeys.IFX_PORTS_LEFT in part_content_ori:
            assert ApKeys.IFX_PORTS_RIGHT in part_content_ori
            self.__fix_sides_ori_ifx_ports(part_content_ori, refs_map)
        else:
            assert ApKeys.IFX_PORTS_RIGHT not in part_content_ori

        # 5. Create outgoing links from children

        if resolve_links:
            drop_dangling = False if context == OriContextEnum.save_load else True
            # resolve all links everywhere in the hierarchy
            self._resolve_ori_link_paths(refs_map, drop_dangling)
            # now that this is done, any temp sockets as a result of legacy scenarios can be cleaned up
            self._remove_ori_temp_sockets()

    @override(BasePart)
    def _remove_ori_temp_sockets(self):
        # Remove temporary sockets that were necessary for resolving links from indices
        for temp_socket in self.__socket_converter.get_temp_sockets():
            self.remove_child_part(temp_socket)
        del self.__socket_converter

        # allow all children to do the same
        for child in self.__children:
            child._remove_ori_temp_sockets()

    @override(BasePart)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        """
        Similar to _set_from_ori_impl(), getting the state of actor is done in several steps:
        1. Get local state (frame, geometry file name, etc)
        2. Get ORI data of each child

        Step 2 includes the outgoing links for each each: each link is represented as a path from a child to another
        part, in the form of a string that represents navigation through the scenario via the index of the part
        in the corresponding parent's list of children.
        :param context: See get_ori_def() documentation in the base class.
        """

        # 1. Get local state (frame, geometry file name, etc)

        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)

        actor_ori_def = {
            ApKeys.PROXY_POS: {
                PosKeys.X: self.__proxy_position.x,
                PosKeys.Y: self.__proxy_position.y
            },
            ApKeys.ROTATION_2D: self.__rotation_2d,
            ApKeys.ROTATION_3D: {
                R3dKeys.ROLL: self.__rotation_3d.roll,
                R3dKeys.PITCH: self.__rotation_3d.pitch,
                R3dKeys.YAW: self.__rotation_3d.yaw
            },
            ApKeys.CHILDREN: [],
            ApKeys.IFX_PORTS_LEFT: [frame.part.SESSION_ID for frame in self.get_ifx_ports(ActorIfxPortSide.left)],
            ApKeys.IFX_PORTS_RIGHT: [frame.part.SESSION_ID for frame in self.get_ifx_ports(ActorIfxPortSide.right)]
        }

        # no special action for ifx port on export, even if ports exist beyond exported actor: will
        # ignore ports for parts that don't exist on load

        if context == OriContextEnum.export:
            # If export operation is underway, set this instance's ORI data with image pathname instead of image ID -
            # this will allow for creation of a new Image Dictionary sufficient for the exported scenario.
            if self.__image_id is not None:
                try:
                    actor_ori_def[ApKeys.IMAGE_ID] = \
                        self._shared_scenario_state.image_dictionary.get_image_path(self.__image_id)
                except Exception as e:
                    log.error("Part: {} is unable to retrieve the path of its associated custom image from the Image "
                              "Dictionary. Error: {}", str(self), str(e))
                    actor_ori_def[ApKeys.IMAGE_ID] = None

        else:
            actor_ori_def[ApKeys.IMAGE_ID] = self.__image_id

        ori_def[CpKeys.CONTENT].update(actor_ori_def)

        # 2. Get ORI data of each child

        # the context is same as for parent, except if context of parent is assign: then children context is copy,
        # because the children are new and hence copied not assigned.
        children_context = context
        if context == OriContextEnum.assign:
            children_context = OriContextEnum.copy
        ori_children = actor_ori_def[ApKeys.CHILDREN]
        for child in self.__children:
            ori_child = child.get_ori_def(context=children_context)
            ori_children.append(ori_child)

        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)

        if self.__image_id:
            try:
                image_path = self._shared_scenario_state.image_dictionary.get_image_path(self.__image_id)
            except Exception as e:
                image_path = "Unresolved image path"
        else:
            image_path = None

        snapshot.update(
            num_children=len(self.__children),
            image_path=image_path,
            rotation_2d=self.__rotation_2d,
            rotation_3d=self.__rotation_3d.rpy_deg,
            proxy_pos=self.__proxy_position.to_tuple(),
            ifx_ports_left=[pf.part.SESSION_ID for pf in self.__ifx_ports_left],
            ifx_ports_right=[pf.part.SESSION_ID for pf in self.__ifx_ports_right],
        )

    @override(BasePart)
    def _has_ori_changes_children(self) -> bool:
        if BasePart._has_ori_changes_children(self):
            return True

        # first check the non-actor children, so will only go deeper in tree if none of them have changed:
        actor_children = []
        for child in self.__children:
            if child.PART_TYPE_NAME == self.PART_TYPE_NAME:
                actor_children.append(child)
            elif child.has_ori_changes():
                return True

        # now check actor children, this will cause traversal deeper into tree so done last
        for child in actor_children:
            if child.has_ori_changes():
                return True

        return False

    @override(BasePart)
    def _set_ori_snapshot_baseline_children(self, baseline_id: OriBaselineEnum):
        BasePart._set_ori_snapshot_baseline_children(self, baseline_id)
        for child in self.__children:
            child.set_ori_snapshot_baseline(baseline_id)

    @override(IOriSerializable)
    def _check_ori_diffs(self, other_ori: Decl.ActorPart, diffs: Dict[str, Any], tol_float: float):
        BasePart._check_ori_diffs(self, other_ori, diffs, tol_float)

        # differences in children (by name; assumes same order, else no way of knowing)
        self_names = [p.name for p in self.__children]
        other_names = [p.name for p in other_ori.children]
        if self_names != other_names:
            diffs['children_names'] = (self_names, other_names)

        # differences in children ORI state
        for child, other_child in zip(self.__children, other_ori.children):
            child_diffs = child.get_ori_diffs(other_child, tol_float=tol_float)
            if child_diffs:
                diffs.setdefault('children', {})[child.part_frame.name] = child_diffs

        # differences in ports:
        self.__check_ori_ifx_ports_diffs(ActorIfxPortSide.left, other_ori, diffs)
        self.__check_ori_ifx_ports_diffs(ActorIfxPortSide.right, other_ori, diffs)

    @override(BasePart)
    def _on_frame_size_changed(self):
        """
        When the actor size changes, update interface part proxy positions
        """
        pass

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __add_ifx_port_solo(self, descendant_frame: PartFrame):
        """Add just one port for descendant frame on self, i.e. no propagation up hierarchy"""
        put_left = len(self.__ifx_ports_left) <= len(self.__ifx_ports_right)
        ports_bin = self.__ifx_ports_left if put_left else self.__ifx_ports_right
        ports_bin.append(descendant_frame)
        self.signals.sig_ifx_port_added.emit(descendant_frame, put_left, ports_bin.index(descendant_frame))

    def __restore_ifx_port(self, descendant_frame: PartFrame, restore_port: RestoreIfxPortInfo):
        """Restore just one port for descendant frame on self, i.e. no propagation up hierarchy"""
        ports_bin = self.__ifx_ports_left if restore_port.left_side else self.__ifx_ports_right
        ports_bin.insert(restore_port.index, descendant_frame)
        self.signals.sig_ifx_port_added.emit(descendant_frame, restore_port.left_side, restore_port.index)

    def __fix_sides_ori_ifx_ports(self, content_ori: OriScenData, refs_map: Dict[int, BasePart]):
        """
        As part of configuring this actor from ORI data, the ports are created in load order of descendant
        parts, hence the current set of left and right ports may not be per ORI data (IFX_PORTS_LEFT and
        IFX_PORTS_RIGHT keys). This method uses the ORI ref keys of the ports to re-assign ports to the
        correct side.

        :param content_ori: the ORI data for this part
        :param refs_map: maps each key to a port
        """
        assert ApKeys.IFX_PORTS_LEFT in content_ori
        assert ApKeys.IFX_PORTS_RIGHT in content_ori

        children_ports = self.__ifx_ports_left + self.__ifx_ports_right
        left_ifx_ports_keys = content_ori[ApKeys.IFX_PORTS_LEFT]
        right_ifx_ports_keys = content_ori[ApKeys.IFX_PORTS_RIGHT]
        self.__ifx_ports_left = []
        self.__ifx_ports_right = []

        for part_id in left_ifx_ports_keys:
            child_frame = refs_map[part_id].part_frame
            self.__ifx_ports_left.append(child_frame)

        for part_id in right_ifx_ports_keys:
            child_frame = refs_map[part_id].part_frame
            self.__ifx_ports_right.append(child_frame)

        assert set(children_ports) == set(self.__ifx_ports_left).union(self.__ifx_ports_right)

    def __check_ori_ifx_ports_diffs(self, side: ActorIfxPortSide, other_ori: BasePart, diffs: Dict[str, Any]):
        """
        Check if two ifx ports are the same part; this can't be done with 100% confidence because there is no
        way to insure that two different parts represent the same entity. So only the frames are checked
        """
        if side == ActorIfxPortSide.left:
            ports = self.__ifx_ports_left
            diff_key = 'ifx_ports_left'
        else:
            ports = self.__ifx_ports_right
            diff_key = 'ifx_ports_right'

        port_idx = 0
        other_ports = other_ori.get_ifx_ports(side)
        for self_port, other_port in zip(ports, other_ports):
            frame_diffs = self_port.get_ori_diffs(other_port)
            if frame_diffs:
                diffs.setdefault(diff_key, {})[port_idx] = frame_diffs
            port_idx += 1

        if len(ports) > len(other_ports):
            missing = len(ports) - len(other_ports)
            diffs[diff_key + '_missing'] = [str(p) for p in ports[-missing:]]
        if len(ports) < len(other_ports):
            extra = len(other_ports) - len(ports)
            diffs[diff_key + '_extra'] = [str(p) for p in other_ports[-extra:]]

    def __get_invertible_links(self, out_links: List[PartLink]) -> Tuple[List[PartLink], List[PartLink]]:
        """
        Find all links in given out_links that are bad and need inverting.
        :param out_links: list of links to analyse
        :return: list of links that are fixable, and list of other links that could be fixed
            instead of those from first list
        """
        fix_links = []
        alternate_fix_link = []
        max_num__fix_links = len(out_links) - 1
        assert max_num__fix_links >= 1
        sorted_links = sorted(out_links, key=lambda x: x.name)  # to guarantee order across app runs
        for link in sorted_links:
            target_frame = link.target_part_frame
            # if target is a node without outgoing links, then might be able to flip it:
            if (target_frame.part.PART_TYPE_NAME == NpKeys.PART_TYPE_NODE
                and len(target_frame.outgoing_links) == 0):
                if len(fix_links) < max_num__fix_links:
                    fix_links.append(link)
                else:
                    alternate_fix_link.append(link)

        return fix_links, alternate_fix_link

    def __accept_child(self, part: BasePart):
        """
        Accept the given part as new child and emits signal. Assumes the part already has self as parent.
        """
        assert part.parent_actor_part is self
        self.__children.append(part)
        self.__children_index_from_id[part.SESSION_ID] = len(self.__children) - 1

        # Notify any listeners of the event.
        if self._anim_mode_shared:
            self.signals.sig_child_added.emit(part)

    def __regen_children_indices(self):
        # TODO build 3: this is rather costly when many children abandonned; the order matters only to support build 1
        # legacy scenarios where the string path for link endpoints relied on index within array; therefore, the
        # children list could be replaced by a dictionary, and the __children_index_from_id could be populated only
        # during load of a scenario. One area that could be affected is ORI diffs: the order is used there too, since
        # the name is not unique; the save would have to guarantee a fixed order for children, and the load could
        # then rely on that order.
        self.__children_index_from_id = {}
        for index, child in enumerate(self.__children):
            self.__children_index_from_id[child.SESSION_ID] = index

    def find_all_parts(self, type_name: str, parts: List[BasePart]):
        """
        Put all children parts that have the given type into parts container, and propagate the search down the tree.
        """
        for child_part in self.__children:
            if child_part.PART_TYPE_NAME == type_name:
                parts.append(child_part)

            # propagate down the tree:
            if child_part.PART_TYPE_NAME == self.PART_TYPE_NAME:
                child_part.find_all_parts(type_name, parts)


# Add this part to the global part type/class lookup dictionary
register_new_part_type(ActorPart, ApKeys.PART_TYPE_ACTOR)
