# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains the class definitions required to define a Base Part object and
                       its attributes, including a Part Frame object.


Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import re
from datetime import datetime
from numbers import Number
from enum import IntEnum

# [2. third-party]

# [3. local]
from ...core import UniqueIdGenerator, BridgeSignal, BridgeEmitter, AttributeAggregator
from ...core import override, override_optional, override_required, get_enum_val_name
from ...core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ...core.constants import SECONDS_PER_DAY
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriBaselineEnum, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys, OriActorPartKeys as ApKeys
from ..alerts import IScenAlertSource

from .common import Vector, Position
from .part_types_info import default_name_for_part, get_type_name
from .part_frame import PartFrame, RestoreIfxLevelInfo
from .part_link import UnrestorableLinks, PartLinksRestoreMap, PartLink, TypeRefTraversalHistory, TypeReferencingParts
from .part_link import TypeMissingLinkInfo, TypeLinkChainNameAndLink
from .scenario_object import ScenarioObject, ScenarioObjectType

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'PartFrame',
    'BasePart',
    'PastablePartOri',
    'check_diff_val',
    'InScenarioState',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    BasePart = 'BasePart'
    ActorPart = 'ActorPart'
    PartLink = 'PartLink'
    RestoreLinkInfo = 'RestoreLinkInfo'
    SharedScenarioState = 'SharedScenarioState'


# -- Function definitions -----------------------------------------------------------------------

def check_diff_val(val1: Any, val2: Any, tol_value: float = 0.00001) -> Optional[Tuple[object, object]]:
    """
    Check the difference between the two values.
    :param val1: first value
    :param val2: second value
    :param tol_value: the tolerance for floating point value differences
    :return: if no difference, None; else, a pair consisting of (val1, val2). If values are numbers,
        their difference must be larger than tol_value; if they are datetime objects, their difference
        must be larger than 1 second.
    """
    if isinstance(val1, datetime):
        delta = val2 - val1
        max_delta_secs = tol_value * SECONDS_PER_DAY
        if delta.total_seconds() > max_delta_secs:
            return str(val1), str(delta)

    elif isinstance(val1, Number) and isinstance(val2, Number):
        if abs(val2 - val1) > tol_value:
            return val1, val2

    elif val1 != val2:
        return str(val1), str(val2)

    return None


def get_first_parent_in_scenario(part: Decl.ActorPart) -> Decl.ActorPart:
    """
    Get the nearest ancestor that has in_scenario True.
    :param part: the part for which to find nearest in-scenario parent
    :return: the ancestor; it can never be None, because (this function assumes that) the scenario root
        can never be removed
    """
    assert part is not None  # ASSUMPTION: the root actor can never be removed
    if part.in_scenario_state == InScenarioState.active:
        return part
    else:
        return get_first_parent_in_scenario(part.parent_actor_part)


# -- Class Definitions --------------------------------------------------------------------------

# session ID is an integer, create alias for clearer annotations
SessionId = int


class InScenarioState(IntEnum):
    """
    A part is active by default, deleted once it has been permanently removed from a scenario, and suspended
    when it has been removed but could be resotred (as a result of undeletion, for example)
    """
    active, deleted, suspended = range(3)


class RestorePartInfo:
    def __init__(self, parent: Decl.ActorPart, position: Position, outgoing_links_info: PartLinksRestoreMap,
                 incoming_links_info: PartLinksRestoreMap, restore_ifx_level: RestoreIfxLevelInfo):
        """
        :param parent: The parent part of the part to be restored.
        :param position: part position to restore to.
        :param outgoing_links_info: A dict mapping link objects to RestoreLinkInfo objects. The link objects represent
            outgoing links deleted from this part. The RestoreLinkInfo objects contain info sufficient for restoring
            the deleted link object from its deleted state.
        :param incoming_links_info: A dict mapping link objects to RestoreLinkInfo objects. The link objects represent
            incoming links deleted from this part. The RestoreLinkInfo objects contain info sufficient for restoring
            the deleted link object from its deleted state.
        :param restore_ifx_level: restoration info for the ifx level of the part
        """
        self.parent_part = parent
        self.position = position
        self.outgoing_links_info = outgoing_links_info
        self.incoming_links_info = incoming_links_info
        # every part that is exposed to high levels of hierarchy will get port restoration info put in here after init:
        self.restore_ifx_level = restore_ifx_level

        # info to be set later

        self.part_scen_data = None  # {BasePart: Any}
        # specifically for actors, they have ports representing children below them, these have to be removed and
        # restored as part of un/deletion:
        self.actor_domain_ifx_ports = []  # List[(PartFrame, RestoreIfxLevelInfo)]


class BasePart(IOriSerializable, IScenAlertSource, ScenarioObject, metaclass=AttributeAggregator):
    """
    This class represents the common part behavior and properties. All parts contain a frame.

    To create a new type of part, the following actions are required:

    - create a module which defines a new class that derives from BasePart
    - define necessary overrides from IOriSerializable (these must call the BasePart overrides)
      and from BasePart (include the META_*_EXTEND class members)
    - add the registration of the new class type at bottom of module
    - add the necessary instantiation code to scenario file readers and writers
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # derived class must override this
    PART_TYPE_NAME = None

    DEFAULT_PATH_SEPARATOR = '/'
    SCENARIO_OBJECT_TYPE = ScenarioObjectType.part

    # By default, all part types show their frame; derived classes should override this to False for those that don't
    SHOW_FRAME = True
    RESIZABLE_FRAME = True
    USER_CREATABLE = True
    CAN_BE_LINK_SOURCE = False

    # Min size for the widget. The default numbers are based on the observations of the prototype framed widgets.
    # The width can go as low as 4 when the widget is at the minimal detail level.
    # Derived classes that have different min size must override this. For example, the hub would have to do it.
    MIN_CONTENT_SIZE = dict(width=4.0, height=1.5)

    # Default size for the widget.
    # Derived classes should override this
    DEFAULT_VISUAL_SIZE = MIN_CONTENT_SIZE

    # All parts have PartFrame as child ORI serializable
    _ORI_HAS_CHILDREN = True

    # Each scenario part has a unique ID, valid for this scenario load only:
    __id_generator = UniqueIdGenerator()

    class BaseSignals(BridgeEmitter):
        sig_bulk_edit_done = BridgeSignal(int)
        sig_in_scenario = BridgeSignal(bool)
        sig_parent_path_change = BridgeSignal()
        sig_unapplied_edits_changed = BridgeSignal(bool)

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: Optional[Decl.ActorPart], name: str = None, position: Position = None):
        """
        :param parent: The scenario Actor Part to which this Part belongs
        :param name: a string identifying the name for this part. If not given, will be set from part type
        """
        IOriSerializable.__init__(self)
        IScenAlertSource.__init__(self)
        self.base_part_signals = BasePart.BaseSignals()

        assert self.DEFAULT_VISUAL_SIZE['width'] >= self.MIN_CONTENT_SIZE['width']
        assert self.DEFAULT_VISUAL_SIZE['height'] >= self.MIN_CONTENT_SIZE['height']

        # two loads of same scenario may produce same or different session ID, but the ID are unique within a session
        self.SESSION_ID = self.__id_generator.get_new_id()  # must never change

        # set parent:
        parent_is_actor = hasattr(parent, 'PART_TYPE_NAME') and parent.PART_TYPE_NAME == ApKeys.PART_TYPE_ACTOR
        self._parent_actor_part = parent if parent_is_actor else None

        # assume that if a parent is given at init, it is in a scenario:
        self.__in_scenario_parent = self._parent_actor_part
        self.__in_scenario_state = InScenarioState.active
        assert (self.__in_scenario_parent is None or
                self.__in_scenario_parent.in_scenario_state == InScenarioState.active)

        # get shared scenario state from parent, and animation mode reader
        if parent is None or parent.shared_scenario_state is None:
            # No animation, default to True
            self._shared_scenario_state = None
            self._anim_mode_shared = True
        else:
            self._shared_scenario_state = parent.shared_scenario_state
            self._anim_mode_shared = self._shared_scenario_state.animation_mode_reader

        # frame:
        name = name or default_name_for_part(self)
        self._part_frame = PartFrame(self, name, self._anim_mode_shared)
        if position is not None:
            self._part_frame.set_position(position.x, position.y)

        if self._parent_actor_part is None:
            log.debug('Scenario part {} is a root part', self)

        # Used to facilitate the editing activities such as link management.
        self.__has_unapplied_edits = False

    @override_optional
    def get_snapshot_for_edit(self) -> Dict[str, Any]:
        """
        Get a snapshot of the state of this part in the form of a dictionary, for purpose of later submitting a bulk
        edit via receive_edited_snapshot(). Each key is an entry from the list returned by the static
        AUTO_EDITING_API_CUMUL, which includes properties common to all part types. Most classes must
        override AUTO_EDITING_API_CUMUL to add properties specific to derived class. Then
        get_snapshot_for_edit() will put the value of each one in the returned
        dictionary.

        If a subclass has compound properties such as dict objects, it must do a deep copy. Those properties
        should not be included in ().

        NOTE: If some editable "data" does not have a corresponding property on the instance (for example, only a getter
        method is available), override get_snapshot_for_edit() too: call its base class version, then add key-value
        pairs as appropriate. Do the same in receive_edited_snapshot(): override it to call the base class version,
        then call appropriate methods to make use of keys added by overridden get_snapshot_for_edit().

        :return: the dictionary of property names and corresponding part state value
        """
        log.debug("Taking part content state snapshot for edit")
        data = dict(name=self._part_frame.name)

        map_link_id_to_name = dict()

        for link in self.part_frame.outgoing_links:
            map_link_id_to_name[link.SESSION_ID] = link.name

        data['link_names'] = map_link_id_to_name

        for member_name in self.AUTO_EDITING_API_CUMUL:
            try:
                attr = getattr(self, member_name)
                data[member_name] = attr

            except Exception:
                temp = 'Submitted data has the key "{}" that has no corresponding property or setter on "{}".'
                raise ValueError(temp.format(member_name, self.path))

        return data

    def receive_edited_snapshot(self, submitted_data: Dict[str, Any], order: List[str] = None, initiator_id: int = 0):
        """
        Change the state of this part with what is stored in submitted_data. Since the order of iteration through
        a dictionary is not known in advance, but some parts have properties that must be set in a particular
        order, the order list can be given for such properties.

        :param submitted_data: map for which keys are property names that should be set to corresponding value
        :param order: if given, list of key names from submitted_data that should be set in order listed
        :param initiator_id: The id of the component that initiates this function.

        Example: assuming submitted_data = {'radius': 123, 'length': 456, 'time': 789}, then
        - with order=None, the properties of radius, length and time will be set to the corresponding values, in
          undefined order
        - with order=['time', 'length'], the time property will be set, then length, and finally all remaining
          properties (radius, in this case) in undefined order

        NOTE: The keys in submitted_data must match those returned by get_snapshot_for_edit(), which includes the
        entries in AUTO_EDITING_API_CUMUL.
        """
        log.debug("Receiving submitted data")
        self._receive_edited_snapshot(submitted_data, order)
        self.base_part_signals.sig_bulk_edit_done.emit(initiator_id)

    @override_optional
    def get_as_link_target_part(self) -> Either[Decl.BasePart, object]:
        """
        If self is a link's target part in a script, then "getting" self may in fact result in getting an
        object linked to this part's frame. By default, getting self as a link target resolves to self.
        Derived classes that have different behavior (such as Node and Hub) must override this.
        :return: target part, which is self unless overridden by the derived class
        """
        return self

    @override_optional
    def get_as_link_target_value(self) -> object:
        """
        If self is a link's target part in a script, then "getting" self as a value may in fact result in getting an
        object inside this part. By default, getting self as a link target value resolves to self.
        Derived classes that have different behavior (such as Variable) must override this.
        :return: value of part, which is self unless overridden by the derived class
        """
        return self

    @override_optional
    def assign_from_object(self, rhs_part: Any):
        """
        Assigns the content of an object to that of this part. Unless a derived class overrides this, the default
        behavior is to copy the RHS content state into the content of this part. This requires that the RHS be a
        scenario part of the same type. Part types that have different assignment behavior (such as Variable,
        Node and Hub) must override this.

        :param rhs_part: part, of same type as self, to copy the content state from
        """
        if not hasattr(rhs_part, 'PART_TYPE_NAME'):
            raise TypeError("Parts of type {} only support re-assignment to another scenario part"
                            .format(self.PART_TYPE_NAME))

        if self.PART_TYPE_NAME != rhs_part.PART_TYPE_NAME:
            raise ValueError('Part types must be same ({} is {}, {} is {})'
                             .format(self, self.PART_TYPE_NAME, rhs_part, rhs_part.PART_TYPE_NAME))

        self.copy_from(rhs_part, OriContextEnum.assign)

    @override_optional
    def copy_from(self, part: Decl.BasePart, context: OriContextEnum) -> int:
        """
        This function copies a part's state into the current instance. The ORI data is retrieved
        from the input part and set into the current instance (slightly differently depending on the
        'context' of the copy operation). If self is a part that contains other parts, and self is
        the top level object (refs_map None), then self's implementation of _set_from_ori_impl() must
        regenerate the links.

        :param part: The origame part to be copied into the current instance.
        :param context: The context of the copy operation: part copy, part export, and scenario load.
        :return: ORI reference key for this part (to be used by caller to extend refs_map if necessary)
        """
        assert context != OriContextEnum.save_load
        part_ori_data = part.get_ori_def(context=context)
        self.set_from_ori(part_ori_data, context=context)
        return part_ori_data[CpKeys.REF_KEY]

    def remove_self(self, restorable: bool = False) -> RestorePartInfo:
        """
        Delete this part from its parent and notify parent to detach from child.
        This function can be called directly by all parts.
        NOTE: This function also deletes all incoming and outgoing links and interface ports.

        :param restorable: True if the delete operation must be restorable (undoable), False if permanent.
        :returns: When restorable=True, returns a RestorePartInfo that can be given to restore_by_parent() method.
            Else, returns None.
        """
        parent = self._parent_actor_part
        return parent.remove_child_part(self, restorable=restorable)

    def restore_self(self, restoration: RestorePartInfo):
        """
        Restore this part in the parent mentioned in restoration.
        This function can be called directly by all parts.
        :param restoration: restoration info for this part, obtained from remove_self().
        """
        restoration.parent_part.restore_child_part(self, restoration)

    @override_optional
    def remove_by_parent(self, part_restore: RestorePartInfo = None):
        """
        WARNING: MUST ONLY BE CALLED BY THE PARENT ACTOR, after the parent has removed
        the part from its children's list, to complete the deletion "transaction".

        Detaches this part from parent actor, and calls the on_removing_from_scenario() (which,
        for actors, recurses down the tree to leaves).
        """
        # let the part know that it is being removed: it may need to interact with parent actor
        # Note: this traverses the actor's subtree of parts
        scen_data_restore = {}
        restorable = (part_restore is not None)
        self.on_removing_from_scenario(scen_data_restore, restorable=restorable)

        # Inform the parent Actor Part to detach this child part.
        assert self.__in_scenario_parent.in_scenario_state == InScenarioState.active
        self._parent_actor_part = None

        if restorable:
            part_restore.part_scen_data = scen_data_restore

    @override_optional
    def restore_by_parent(self, restore_part_info: RestorePartInfo, parent: Decl.ActorPart):
        """
        WARNING: MUST ONLY BE CALLED BY THE PARENT ACTOR, after having re-introduced the child into
        its list of children, to complete the restore "transaction".

        Re-attach this part to its parent actor. Position is restored, and the
        recursive on_restored_to_scenario() is called.

        Note: incoming and outgoing links are not restored here: they must be restored only after
        all parts of a restore operation have been restored, via restore_links().

        :param restore_part_info: the restoration info for this part
        :param parent: if None, the parent stored in restore_part_info is used
        :raise: ValueError if check_parent is True but restore_part_info.parent_part is not self
        """

        self._part_frame.set_pos_from_vec(restore_part_info.position)
        assert parent is not None
        parent = parent or restore_part_info.parent_part
        assert self in parent.children
        self._parent_actor_part = parent

        self.on_restored_to_scenario(restore_part_info.part_scen_data)
        assert self.__in_scenario_parent is self._parent_actor_part

    @override_optional
    def restore_links(self, restore_part_info: RestorePartInfo, dropped_links: UnrestorableLinks,
                      waypoint_offset: Vector = None, no_waypoints: List[Decl.BasePart] = None):
        """
        Restore the linking on this part.

        :param restore_part_info: the restoration info for the part
        :param dropped_links: links that could not be restored are put in this container
        :param waypoint_offset: an x,y offset for the link waypoints
        :param no_waypoints: parts for which links to or from self should be restored without waypoints

        When any of the optional parameters are given, the restoration is "impure" i.e. it is assumed
        to be the result of a move of self (or any ancestor) to another actor. In such case, two things
        happen: 1. links to parts in no_waypoints, or from parts in no_waypoints, get re-created
        (instead of restored) without waypoints; 2. links to other parts get re-created (instead of restored)
        with the original waypoints shifted by waypoint_offset.
        """
        log.debug("Restoring links for part {}", self)

        dropped = self._part_frame.restore_outgoing_links(restore_part_info.outgoing_links_info,
                                                          waypoint_offset=waypoint_offset,
                                                          no_waypoints=no_waypoints)
        dropped_links.outgoing.update(dropped)

        dropped = self._part_frame.restore_incoming_links(restore_part_info.incoming_links_info,
                                                          waypoint_offset=waypoint_offset,
                                                          no_waypoints=no_waypoints)
        dropped_links.incoming.update(dropped)

    def get_name(self) -> str:
        """
        Get the name of this part. This name is in fact a property of its frame, so it is not constant (since
        frame can be moved to a different part).
        """
        return self._part_frame.name

    def set_name(self, new_name: str):
        """
        Slot that is called when an actor is renamed from the front end.
        """
        self._part_frame.name = new_name

    def get_in_scenario_parent(self) -> Decl.BasePart:
        """
        Get the nearest ancestor that is still in the scenario. The returned part is guaranteed to have
        is_in_scenario=True. Note: Until part is removed from scenario, this is the same part as parent part.
        """
        return self.__in_scenario_parent

    def get_part_frame(self) -> PartFrame:
        """
        :return: Returns the part's PartFrame object describing the frame info for the Part.
        """
        return self._part_frame

    def get_has_unapplied_edits(self) -> bool:
        """
        :return: True, if the part has at least one edited piece that is not applied.
        """
        return self.__has_unapplied_edits

    def set_has_unapplied_edits(self, edited: bool):
        """
        Sets it to True if the part has at least one edited piece that is not applied.
        :param edited: The new state of being edited
        """
        self.__has_unapplied_edits = edited
        if self._anim_mode_shared:
            self.base_part_signals.sig_unapplied_edits_changed.emit(edited)

    def get_parent_actor_part(self) -> Decl.ActorPart:
        """
        :return: Returns the part's parent actor part.
        """
        return self._parent_actor_part

    def iter_parents(self):
        """
        Get an iterator to iterate over the chain of parents, starting from the closest 
        to the furthest (ie root actor). Ex: "for parent in self.iter_parents():".
        """
        parent = self._parent_actor_part
        while parent is not None:
            yield parent
            parent = parent.parent_actor_part

    def get_is_root(self) -> bool:
        """
        Determine if this part is at the root of a scenario part hierarchy. Returns True if this part has no parent,
        false otherwise.
        """
        return self._parent_actor_part is None

    @override_optional
    def get_all_descendants_by_id(self, id_map: Dict[SessionId, Decl.BasePart]):
        """
        Add every descendant of this part to the ID map. By default, parts don't have descendants.
        The keys of the ID map are part session IDs.
        """
        return

    def get_shared_scenario_state(self) -> Decl.SharedScenarioState:
        """Get the share scenario state"""
        return self._shared_scenario_state

    def get_anim_mode(self) -> bool:
        """
        Get the current animation mode for this part. This is always same as that of its frame. When true,
        signals are emitted when state changes.
        """
        assert bool(self._anim_mode_shared) == self._part_frame.anim_mode
        return bool(self._anim_mode_shared)

    def get_ori_ref_key(self) -> int:
        """Get the ORI reference key to use for this part"""
        return self.SESSION_ID

    def get_parts_path(self, with_root: bool = False, with_part: bool = True) -> List[Decl.BasePart]:
        """
        Get the list of parts from root actor to this part. By default, root is not included in list,
        and the part itself is in the list.
        :param with_root: Set to True if the root actor should be in the returned list
        :param with_part: Set to False if self part should not be in the returned list

        NOTE: if self is a root part (no parent), then the only call that will produce a non-empty
        list is root.get_parts_path(with_root=True).

        Example: given root, part1, part2 hierarchy, then

        - root.get_parts_path() returns []
        - root.get_parts_path(with_root=True) returns [root]
        - root.get_parts_path(with_root=True, with_part=False) returns []
        - root.get_parts_path(with_part=False) returns []

        - part1.get_parts_path() returns [part1]
        - part1.get_parts_path(with_root=True) returns [root, part1]
        - part1.get_parts_path(with_root=True, with_part=False) returns [root]
        - part1.get_parts_path(with_part=False) returns []

        - part2.get_parts_path() returns [part1, part2]
        - part2.get_parts_path(with_root=True) returns [root, part1, part2]
        - part2.get_parts_path(with_root=True, with_part=False) returns [root, part1]
        - part2.get_parts_path(with_part=False) returns [part1]

        NOTE: because of this, do not use this method to determine if a part is root; instead, use part.is_root
        property or associated getter.

        NOTE: a new list is generated at every call, so this is somewhat expensive call. This is in case self is
        moved to another actor, although it would now be quite straightforward to cache this thanks to
        on_removed/restored_from/to_scenario() methods.
        """
        if self._parent_actor_part is None:
            return [self] if with_root and with_part else []

        path = []
        part = self if with_part else self._parent_actor_part
        while part is not None:
            if part.is_root and not with_root:
                break
            path.insert(0, part)
            part = part._parent_actor_part

        return path

    def get_path_list(self, with_root: bool = False, with_name=True) -> List[str]:
        """
        Get the list of part names from root actor to this part; a new list is generated at every call. See
        self.get_parts_path() for details on root parameter.
        """
        return [part.name for part in self.get_parts_path(with_root=with_root, with_part=with_name)]

    def get_path(self, with_root: Either[bool, str] = DEFAULT_PATH_SEPARATOR, with_name: bool = True) -> str:
        """
        Get string version of part's path, using '/' as path element separator. By default, the root
        actor is represented by the separator and the part's name is included.
        :param with_root: True to show the root actor name; False to not show it; any other character to represent
            root actor name using that character.
        :param with_name: False to omit the name of this part from path

        Example: if the root actor is named 'root' and has a child actor named 'part1', which has child
        named 'part2', then:

        - part2.get_path() returns 'part1/part2'
        - part2.get_path(with_root=False) returns '/part1/part2'
        - part2.get_path(with_root=True) returns 'root/part1/part2'

        Root is special:
        - root.get_path() returns '/'
        - root.get_path(with_root=False) returns ''
        - root.get_path(with_root=True) returns 'root'
        """
        if with_root == self.DEFAULT_PATH_SEPARATOR:
            return with_root + self.DEFAULT_PATH_SEPARATOR.join(self.get_path_list(with_name=with_name))
        else:
            return self.DEFAULT_PATH_SEPARATOR.join(self.get_path_list(with_root=with_root, with_name=with_name))

    @override_optional
    def get_matching_properties(self, re_pattern: str) -> List[str]:
        """
        Get the names of all properties of this frame that have a string representation that matches a pattern (case insensitive).

        :param re_pattern: the regular expression pattern to match on

        Example: self.get_matching_properties('hel.*') will return ['part_frame.comment', 'script'] if comment
            of part's frame is 'hello' and the derived part has a property named "script" that equal to "print('hell')"
        """
        regexp = re.compile(re.escape(re_pattern), re.IGNORECASE)
        matches = self._part_frame.get_matching_properties(re_pattern)
        matches = [('part_frame.' + match) for match in matches]

        # look through all properties used for editing, and capture any matches:
        #
        for prop_name in self.AUTO_SEARCHING_API_CUMUL:
            prop_val_as_str = str(getattr(self, prop_name))
            result = regexp.search(prop_val_as_str)
            if result:
                MAX_LEN_MATCHED_PROP_VAL = 100
                log.debug('Part {} property "{}" matches "{}" on "{}"',
                          self, prop_name, re_pattern, prop_val_as_str[:MAX_LEN_MATCHED_PROP_VAL])
                matches.append(prop_name)

        # no other place to look for matches:
        return matches

    @override_optional
    def can_add_outgoing_link(self, part_type_str: str=None) -> bool:
        """
        By default, if a part can be a link source, it can have any number of links from its frame. Override
        this if the number of links allowed can change in other ways.
        :param part_type_str: part type name of target part
        """
        return self.CAN_BE_LINK_SOURCE

    @override_optional
    def on_outgoing_link_added(self, link: PartLink):
        """
        This is automatically called when our frame has an outgoing link added. Derived classes that need
        to take special action when this happens must override this.
        """
        pass

    @override_optional
    def on_outgoing_link_removed(self, link: PartLink):
        """
        This is automatically called when our frame has an outgoing link removed. Derived classes that need
        to take special action when this happens must override this.
        """
        pass

    @override_optional
    def on_outgoing_link_renamed(self, old_name: str, new_name: str):
        """
        This is automatically called when our frame has an outgoing link renamed. Derived classes that need
        to take special action when this happens must override this.
        """
        pass

    @override_optional
    def on_link_target_part_changed(self, link: PartLink):
        """
        This is automatically called by a part that we are linked to, when the part has a non-self link target (ie
        when the result of get_as_link_target_part() has changed). Derived classes that need
        to take special action when this happens must override this. Typically, this means classes that override
        get_as_link_target_part().

        :param link: the link for which link.target_part_frame.part.get_as_link_target_part() has changed.
        """
        pass

    @override_optional
    def update_temp_link_name(self, new_temp_name: str, link: PartLink):
        """
        The names of outgoing links can be temporary. For example, a name is being edited and is not applied yet.
        We need to know the relationship between a temporary name and its real name. 
        
        This function does nothing by default
        
        :param new_temp_name: A temporary link name for the real link name
        :param link: The real link
        """
        pass

    @override_optional
    def clear_temp_link_names(self):
        """
        Cleans up the relationship established by update_temp_link_name
        """
        pass

    @override_optional
    def on_frame_name_changed(self):
        """
        This is automatically called by the Part Frame when its name is changed.
        """
        pass

    @override_optional
    def on_parent_path_changed(self):
        """
        This function must be called by the parent part when the parent part's path (path/get_path())
        within the scenario has changed. It emits the sig_parent_path_change signal.
        Note: changing self's frame name does not cause the signal to be emitted because although this
        changes self's path, it does not affect the parent's path.
        """
        if self._anim_mode_shared:
            self.base_part_signals.sig_parent_path_change.emit()

    @override_optional
    def on_exec_done(self):
        """
        This gets called by the GUI after an IExecutablePart has been called. The default is to ignore the message,
        but parts that contain objects that can be modified via scripting without the part being aware can override
        this and emit the appropriate signals if there have been changes.

        Example of such part is Variable Part:
        the object it contains, such as a list, can be changed without knowledge from the part, because the object
        can be obtained from the part then its state modified. In the on_exec_done() for that type of part,
        a check can be made to see if it was accessed since the last time on_exec_done() called (or part created).
        """
        pass

    @override_optional
    def on_removing_from_scenario(self, scen_data: Dict[Decl.BasePart, Any], restorable: bool = False):
        """
        Notify this part that it is no longer in the scenario, although it may still have a parent: one of its
        ancestors might have been removed. Derived classes should call base method and handle any cleanup
        cleanup is necessary, such as removing themselves from the simulation event queue, remove imagery,
        close database table, etc.

        Note: this is called on the part being removed, and due to the override on ActorPart, on all parts
        below it, recursively. It is called before the parent is actually set to None.

        :param restorable: if True, then derived class should return the scenario-level data, in case the part
            is later restored as a result of undo operation.
        :param scen_data: a mapping of part to dict of data
        """
        assert self.__in_scenario_state == InScenarioState.active
        assert self._parent_actor_part is not None

        self.__in_scenario_state = InScenarioState.suspended if restorable else InScenarioState.deleted
        self.__in_scenario_parent = get_first_parent_in_scenario(self)
        if self._anim_mode_shared:
            # Signal that the part's path has potentially changed with the restoration action.
            self.base_part_signals.sig_in_scenario.emit(False)

        if self not in scen_data:
            scen_data[self] = {}

    @override_optional
    def on_restored_to_scenario(self, scen_data: Dict[Decl.BasePart, Any]):
        """
        This gets called upon restoration of the part into scenario, in order to give a chance to derived classes
        to re-instate associated scenario data (such as events on simulation queue, imagery, database table, etc).
        NOTE: If overridden, this base version of the function must be called by the override.
        NOTE: Elevated links cannot be restored here, as other parts may have to be restored first
        :param scen_data: a dictionary of scenario data to restore for this part
        """
        assert self.__in_scenario_state == InScenarioState.suspended
        assert self._parent_actor_part.in_scenario_state == InScenarioState.active

        self.__in_scenario_state = InScenarioState.active
        self.__in_scenario_parent = self._parent_actor_part

        if self._anim_mode_shared:
            # Signal that the part's path has potentially changed with the restoration action.
            self.base_part_signals.sig_in_scenario.emit(True)
            self.base_part_signals.sig_parent_path_change.emit()

    @override_optional
    def on_scenario_shutdown(self):
        """
        Called automatically when the whole scenario is discarded. Derived classes that need to release
        resources should override this.
        """
        pass

    def get_in_scenario_state(self) -> InScenarioState:
        """
        Determine if this part is active, suspended, or deleted. It is active if it can reach the root actor of
        scenario, and if the root actor could reach it. It is deleted if it has been removed and can never be
        restored (because the removal had restorable=False). It is suspended if it has been removed with
        restorable=True, ie it could be re-introduced into the scenario (as a result of undelete or paste).

        Note: must not be called while a removal/restoration is in progress, as the state may be incorrect
        """
        return self.__in_scenario_state

    def get_in_scenario(self) -> bool:
        """Return true if in scenario, false if not (ie deleted or suspended)"""
        return self.__in_scenario_state == InScenarioState.active

    def get_is_ifx_part(self) -> bool:
        """Returns True if this part's frame has an interface level setting different from 0; False otherwise"""
        return self._part_frame.get_ifx_level() != 0

    def get_link_chain_sources(self,
                               referencing_parts: TypeReferencingParts,
                               traversal_history: TypeRefTraversalHistory,
                               referenced_link_name: str):
        """
        Along the part's incoming links, this function finds the unique routes to all the leaf parts (non-hub parts)

        :param referencing_parts: User-defined data related to this part
        :param traversal_history: Used to avoid recursions
        :param referenced_link_name: The link name referenced by the parts
        """
        traversal_history.append(self.SESSION_ID)
        self._handle_link_chain_sources(referencing_parts, referenced_link_name)
        self._fwd_link_chain_sources(referencing_parts,
                                     traversal_history,
                                     referenced_link_name)

        del traversal_history[-1]

    def on_link_renamed(self,
                        referencing_parts: TypeReferencingParts,
                        traversal_history: TypeRefTraversalHistory,
                        referenced_link_name: str,
                        new_referenced_link_name: str):
        """
        Along the part's incoming links, this function finds the unique routes to all the leaf parts (non-hub parts)
        to attempt to do a link name refactoring on each part it finds.

        :param referencing_parts: User-defined data related to this part
        :param traversal_history: Used to avoid recursions
        :param referenced_link_name: The link name referenced by the parts
        :param new_referenced_link_name: The new name to replace the old name
        """
        traversal_history.append(self.SESSION_ID)
        self._handle_link_chain_rename(referencing_parts, referenced_link_name, new_referenced_link_name)
        self._fwd_link_chain_rename(referencing_parts,
                                    traversal_history,
                                    referenced_link_name,
                                    new_referenced_link_name)

        del traversal_history[-1]

    @override_optional
    def get_link_chains(self, traversal_history: TypeRefTraversalHistory) -> List[List[PartLink]]:
        """
        Gets unique link chains. The typical use case is to pass traversal_history as [] to start the traversal.
        :param traversal_history: Used to avoid recursions. [] to start the traversal.
        After that it is updated automatically.
        :return: All the unique link chains that can be reached from this part.
        """
        ret_list = list()
        if not traversal_history:
            traversal_history.append(self.SESSION_ID)
            for link in self.part_frame.outgoing_links:
                out_chains = link.get_link_chains(traversal_history)
                chain_type = len(out_chains)
                if chain_type > 1:
                    ret_list.append([link])
                elif chain_type == 1:
                    if len(out_chains[0]) > 1:
                        ret_list.append([link])

                for out_chain in out_chains:
                    ret_list.append(out_chain)

        return ret_list

    def get_formatted_link_chains(self) -> Tuple[List[PartLink], TypeLinkChainNameAndLink]:
        """
        Constructs two lists from the given part. The first is a list of all the outgoing links; the second all the
        chained link name and the last part link tuples, i.e., the link names beyond a target hub part and the part
        link before the leaf target. For example, if this part has a link pointing to a hub that links to a function
        part and another hub part that links to another function part. The chained names would look like this:
    
        hub.a_function_part
        hub.another_hub.another_function_part
    
        :return: The outgoing list and the list of the chained names
        """
        part_links = []
        chained_name_and_links = []
        traversal_history = []

        link_chains = self.get_link_chains(traversal_history)
        for link_chain in link_chains:
            if len(link_chain) > 1:
                # hub and beyond
                chained_name = '.'.join(link.name for link in link_chain)
                chained_name_and_links.append((chained_name, link_chain[-1]))
            else:
                # direct link
                part_links.append(link_chain[0])

        return part_links, chained_name_and_links

    def get_unused_link_info(self, script: str = None) -> List[str]:
        """
        Finds the unused links in the script of the part. Returns the each link's name.
        :param script: If it is None, the existing script of the part is investigated; otherwise, the given script.
        :return: The unused link info
        """
        return self._get_unused_link_info(script)

    def get_missing_link_info(self, script: str = None) -> TypeMissingLinkInfo:
        """
        Finds the missing links in the script of the part. Returns the each link's name, line number, start and end 
        cursor positions.
        :param script: If it is None, the existing script of the part is investigated; otherwise, the given script.
        :return: The missing link info (link name, line number, start, end)
        """
        return self._get_missing_link_info(script)

    def get_unique_missing_link_names(self, script: str = None) -> List[str]:
        """
        Gets the unique names of all the missing links of this part.
        :param script: If it is None, the existing script of the part is investigated; otherwise, the given script.
        :return: The unique link names.
        """
        missing_link_info = self.get_missing_link_info(script)
        if missing_link_info is None:
            return None

        return sorted(set([link_info[0] for link_info in missing_link_info]))

    def __str__(self) -> str:
        """Return a string that has path and session ID of part"""
        if self.__in_scenario_state == InScenarioState.active:
            return "'{}' (ID {})".format(self.get_path(), self.SESSION_ID)
        else:
            return "'{}' (ID {}, {})".format(self._part_frame.name, self.SESSION_ID,
                                             get_enum_val_name(self.__in_scenario_state))

    def __dir__(self) -> List[str]:
        """For code auto-completion, jedi uses dir(part), which should only return the cumulated scripting API"""
        return list(self.AUTO_SCRIPTING_API_CUMUL)

    # --------------------------- instance PUBLIC properties ----------------------------

    path = property(get_path)
    name = property(get_name, set_name)
    ori_ref_key = property(get_ori_ref_key)
    part_frame = property(get_part_frame)
    parent_actor_part = property(get_parent_actor_part)
    is_root = property(get_is_root)
    is_ifx_part = property(get_is_ifx_part)
    anim_mode = property(get_anim_mode)
    in_scenario = property(get_in_scenario)
    in_scenario_state = property(get_in_scenario_state)
    in_scenario_parent = property(get_in_scenario_parent)
    # Do not publish the set_has_unapplied_edits as a property because that will tempt people to use
    # part.has_unapplied_edits = bool_value. If that part happens to be a Data part. The property will be
    # used as a user data item.
    has_unapplied_edits = property(get_has_unapplied_edits)

    shared_scenario_state = property(get_shared_scenario_state)

    # --------------------------- CLASS META data for public API ------------------------

    # Derived classes must shadow these variables with the attributes (member data, functions and properties)
    # that should be automatically supported for various tasks: editing, searching, ORI diffs, and scripting.
    # They must refer to actual members so they must appear at the end of the public section of a Part's class.
    # At class definition time, the metaclass will combine it with that of the superclass and put in this
    # class's corresponding AUTO_*_API_CUMUL data member.

    """
    List the members (properties, mostly) that will be *automatically* read by BasePart.get_snapshot_for_edit()
    and set by BasePart.receive_edited_snapshot(). Customization can be done by overriding those two methods
    specifically for those edits.
    """
    META_AUTO_EDITING_API_EXTEND = ()

    """
    List the members (properties, mostly) that will be automatically searched by BasePart.get_matching_properties().
    For searching portions of an object without a corresponding property, override this method() for the additional
    search coverage.
    """
    META_AUTO_SEARCHING_API_EXTEND = META_AUTO_EDITING_API_EXTEND

    """
    List names of properties that will be automatically compared by get_ori_diffs().
    """
    META_AUTO_ORI_DIFFING_API_EXTEND = META_AUTO_SEARCHING_API_EXTEND

    """
    List the names of properties and methods that will be automatically made available to the scripting API.
    """
    META_AUTO_SCRIPTING_API_EXTEND = ()

    """
    List the constants defined in this module, that should be made available to Part scripts
    """
    META_SCRIPTING_CONSTANTS = ()

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_optional
    def _get_unused_link_info(self, script: str = None) -> List[str]:
        """
        Those derived classes that have a script should override this function.
        :param script: If it is None, the existing script of the part is investigated; otherwise, the given script.
        :return: The missing link info (link name, line number, start, end)
        """
        return None

    @override_optional
    def _get_missing_link_info(self, script: str = None) -> TypeMissingLinkInfo:
        """
        Those derived classes that have a script should override this function.
        :param script: If it is None, the existing script of the part is investigated; otherwise, the given script.
        :return: The missing link info (link name, line number, start, end)
        """
        return None

    @override(IScenAlertSource)
    def _get_source_name(self) -> str:
        """
        Returns the same value as the get_path()
        :return: The source name
        """
        return self.get_path()

    @override_optional
    def _fwd_link_chain_sources(self,
                                referencing_parts: TypeReferencingParts,
                                traversal_history: TypeRefTraversalHistory,
                                referenced_link_name: str):
        """
        If the part needs to forward business to its incoming parts , it must implement this function. By default, this
        function does nothing. The Hub part is the example that implements this function.

        :param referencing_parts: User-defined data related to this part
        :param traversal_history: Used to avoid recursions
        :param referenced_link_name: The link name referenced by the parts
        """
        pass

    @override_optional
    def _fwd_link_chain_rename(self,
                               referencing_parts: TypeReferencingParts,
                               traversal_history: TypeRefTraversalHistory,
                               referenced_link_name: str,
                               new_referenced_link_name: str):
        """
        If the part needs to forward business to its incoming parts , it must implement this function. By default, this
        function does nothing. The Hub part is the example that implements this function.

        :param referencing_parts: User-defined data related to this part
        :param traversal_history: Used to avoid recursions
        :param referenced_link_name: The link name referenced by the parts
        :param new_referenced_link_name: The new name to replace the old name
        """
        pass

    @override_optional
    def _handle_link_chain_sources(self,
                                   referencing_parts: TypeReferencingParts,
                                   referenced_link_name: str):
        """
        The derived class implements any link chain source related features, e.g., finding a script referencing a link.
        By default, this function does nothing.

        :param referencing_parts: User-defined data related to this part
        :param referenced_link_name: The existing link name
        """
        pass

    @override_optional
    def _handle_link_chain_rename(self,
                                  referencing_parts: TypeReferencingParts,
                                  referenced_link_name: str,
                                  new_referenced_link_name: str):
        """
        The derived class uses to implement any link name change related features, e.g., name refactoring in a script.
        By default, this function does nothing.

        :param referencing_parts: User-defined data related to this part
        :param referenced_link_name: The existing link name
        :param new_referenced_link_name: The new link name
        """
        pass

    @override_optional
    def _resolve_ori_link_paths(self, refs_map: Dict[int, Decl.BasePart], drop_dangling: bool, **kwargs):
        """
        Make the frame resolve the string link paths for all its outgoing links. It should only be called
        by the parent actor after set_from_ori() has been called.
        :param refs_map: the parts references map so link endpoints (which are part ID at this stage)
            can be resolved to actual part references
        :param drop_dangling: True if links that can't be resolved should be dropped; if False, will
            raise InvalidLinkPath on first link that cannot be resolved
        :param **kwargs: extra required and optional args ignored by base but allow derived class
            to pass them through to other derived classes without knowing class
        """
        self._part_frame.resolve_ori_link_paths(self._parent_actor_part, refs_map, drop_dangling, **kwargs)

    @override_optional
    def _remove_ori_temp_sockets(self):
        """
        Any class that uses temporary Socket parts should implement this to discard them (the ORI load has completed
        and they are no longer needed).
        """
        pass

    @override_optional
    def _on_frame_position_changed(self):
        """
        Called by the part's frame when the frame is moved. A part that needs to take special action when its
        frame is moved should override this.
        """
        pass

    @override_optional
    def _on_frame_size_changed(self):
        """
        Called by the part's frame when the size is changed. A part that needs to take special action when its
        frame size changes should override this.
        """
        pass

    @override_optional
    def _receive_edited_snapshot(self, submitted_data: Dict[str, Any], order: List[str] = None):
        """
        Same docs as receive_edited_snapshot(), except that parameters are slightly different:

        :param submitted_data: map for which keys are property names that should be set to corresponding value
        :param order: if given, list of key names from submitted_data that should be set in order listed

        NOTE: if get_editable_snapshot() is overridden, this method must be overridden too: should call the base class
        version, and only use those keys from submitted_data that are added by overridden get_editable_snapshot().
        """
        if "name" in submitted_data:
            self._part_frame.name = submitted_data['name']
            log.debug("New frame name is '{}'", self._part_frame.name)

        if 'link_names' in submitted_data:
            for link_id, new_name in submitted_data['link_names'].items():
                part_link = self._part_frame.get_outgoing_link_by_id(link_id)
                # Note: The front end submits the unchanged link name too because it wants to benefit from the
                # editing infrastructure for the change detection edited_data == self._initial_data
                # During undo, part_link.temp_name is always None, we must accept the new name
                if part_link.temp_name is not None:
                    assert new_name == part_link.temp_name
                    part_link.temp_name = None

                part_link.set_unique_name(new_name)

            self.clear_temp_link_names()

        accumulated_key_set = set(self.AUTO_EDITING_API_CUMUL)
        submitted_key_set = set(submitted_data.keys())
        inter_key_set = accumulated_key_set.intersection(submitted_key_set)

        # check that all items in order are also in submitted_data
        order = order or []
        order_set = set(order)
        if not order_set.issubset(submitted_data):
            missing = order_set - set(submitted_data)
            raise ValueError("Items {} of order are not in submitted_data".format(missing))

        # create a list of property keys with the ordered ones first, and all remaining ones after:
        property_keys = order + list(inter_key_set - order_set)
        for member in property_keys:
            value = submitted_data[member]

            try:
                # only set properties that have a getter, else could inadvertently create attributes
                old_value = getattr(self, member)

            except Exception:
                temp = 'Part "{}" of type "{}" does not have a property called "{}"'
                raise ValueError(temp.format(self.PART_TYPE_NAME, self.path, member))

            # ok, we can set it:
            setattr(self, member, value)
            new_value = str(getattr(self, member))
            # only keep first line
            if '\n' in new_value:
                new_value = new_value.splitlines()[0] + '...<multiple lines>...'
            log.debug("Part '{}' has new value {}='{}'", self.path, member, new_value)

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        """
        When the context is "assign", this function has nothing to do because the frame is not covered by assignment;
        otherwise, it populates the part frame.
        NOTE: any setting of object state from the ORI data must emit the signal associated with the object state
            changed, since when this object is being assigned to, there are already other objects connect to
            state change signals. Recommended approach is to set the state via the setter method or property.
        """
        # we only set the frame from ORI when context is not assignment:
        if context != OriContextEnum.assign:
            self._part_frame.set_from_ori(ori_data.get_sub_ori(CpKeys.PART_FRAME), context=context, **kwargs)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        part_type = default_name_for_part(self)
        assert part_type is not None
        return {
            CpKeys.TYPE: part_type,
            CpKeys.REF_KEY: self.get_ori_ref_key(),
            CpKeys.PART_FRAME: self._part_frame.get_ori_def(context=context, **kwargs),
            CpKeys.CONTENT: {},
        }

    @override(IOriSerializable)
    def _has_ori_changes_children(self) -> bool:
        return self._part_frame.has_ori_changes()

    @override(IOriSerializable)
    def _set_ori_snapshot_baseline_children(self, baseline_id: OriBaselineEnum):
        self._part_frame.set_ori_snapshot_baseline(baseline_id)

    @override(IOriSerializable)
    def _check_ori_diffs(self, other_ori: Decl.BasePart, diffs: Dict[str, Any], tol_float: float):
        diffs_frame = self._part_frame.get_ori_diffs(other_ori.part_frame)
        if diffs_frame:
            diffs['frame'] = diffs_frame

        # auto portion:
        for prop_name in self.AUTO_ORI_DIFFING_CUMUL:
            self.__check_ori_diff_prop(prop_name, other_ori, diffs)

    @override(IScenAlertSource)
    def _get_alert_parent(self) -> IScenAlertSource:
        """If alerts should be propagated up to a "parent" alert source, override this method to return it"""
        return self._parent_actor_part

    @override(IScenAlertSource)
    def _notify_alert_changes(self) -> bool:
        return bool(self._anim_mode_shared) and super()._notify_alert_changes()

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __check_ori_diff_prop(self, prop_name: str, other_ori: Decl.BasePart, diffs: Dict[str, Any], tol_value=0.00001):
        """
        Check whether a property of ours has different value as same property in another instance. Any differences
        are put in diffs dict.

        :param prop_name: name of property to check
        :param other_ori: the other object with which to compare same property
        :param diffs: where to put the difference, if any; the key is prop_name
        :param tol_value: maximum tolerance for floating point value differences
        """
        assert isinstance(self, type(other_ori))
        prop_val = getattr(self, prop_name)
        other_val = getattr(other_ori, prop_name)
        if prop_val != other_val:
            diff = check_diff_val(prop_val, other_val, tol_value)
            if diff is not None:
                diffs[prop_name] = diff


class PastablePartOri(IOriSerializable):
    """
    This class defines an object that is used to store part ORI data for paste operations between scenarios.

    The class implements API methods similar to BasePart in order to facilitate the paste operation of the part. This
    class does not contain the BasePart, only some of it's attributes including name, parent, and parent path. It stores
    the content of the part (OriScenData) in the attribute __ori_data that is set and retrieved using analogous methods
    to BasePart's _set_from_ori_impl and _get_from_ori_impl, respectively. A part_frame attribute provides the API for
    the part's position (used to compute a paste offset in the front-end) which is generically set to (0, 0) since the
    values do not matter when pasting the part into a new scenario; they must simply be provided.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # Used to provide the 'PartFrame' API during paste operations
    class PartFrame:
        pos_x = 0
        pos_y = 0

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: BasePart):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: The part's name.
        """
        IOriSerializable.__init__(self)
        self.SESSION_ID = part.SESSION_ID
        self.part_frame = self.PartFrame()
        self.__parent_actor_part = part.parent_actor_part
        self.__path = part.get_path(with_root=True)
        self.__name = part.name
        self.__ori_data = None  # Ori data storage will be set as a result of call to self.set_from_ori()

    def get_parent_actor_part(self) -> Decl.ActorPart:
        """Required for pasting, see BasePart.get_parent_actor_part for docs."""
        return self.__parent_actor_part

    def get_name(self) -> str:
        """Required for pasting, see BasePart.get_name for docs."""
        return self.__name

    def get_path(self, *args, **kwargs) -> str:
        """Required to show user which part this is (see BasePart.get_path() for docs)."""
        return self.__path

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    parent_actor_part = property(get_parent_actor_part)
    name = property(get_name)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        """Set the Ori data of the given part."""
        self.__ori_data = ori_data

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        """Get the Ori data of the given part."""
        return self.__ori_data
