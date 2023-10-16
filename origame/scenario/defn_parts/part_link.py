# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Components related to linking scenario parts

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...core import BridgeEmitter, BridgeSignal, override, validate_python_name
from ...core import UniqueIdGenerator
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriBaselineEnum, OriContextEnum, OriScenData, JsonObj
from ..ori import OriPartLinkKeys as PwKeys, OriWaypointKeys as WpKeys, OriPositionKeys as PosKeys
from ..animation import SharedAnimationModeReader

from .scenario_object import ScenarioObject, ScenarioObjectType
from .common import Position, Vector


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'PartLink',
    'PARENT_ACTOR_PATH',
    'LINK_PATH_DELIM',
    'MissingLinkEndpointPathError',
    'InvalidLinkPathSegmentError',
    'InvalidPartLinkArgumentsError',
    'UnresolvedLinkPathError',
    'UnresolvedPartRefError',
    'RestoreLinkInfo',
    'LinkWaypoint',
    'LinkSet',
    'UnrestorableLinks',
    'LinkTip',
    'get_patterns_by_link_item',
    'get_link_find_replace_info',
    'get_frame_repr',
    'TypeReferencingParts',
    'TypeRefTraversalHistory',
    'TypeLinkChainNameAndLink',
    'TypeMissingLinkInfo',

]

"""
Link path-specific constants.
"""
PARENT_ACTOR_PATH = ".."
LINK_PATH_DELIM = '/'

log = logging.getLogger('system')

# All the link references in a script
LINK_PATTERN = r'\b(link)(\.[a-zA-Z_][a-zA-Z0-9_]*)+'

# A specific part link reference.
# For example, do this to construct a pattern for "my_function" part link:
# pattern = PART_LINK_PATTERN.format("my_function")
PART_LINK_PATTERN = r'\b(link)(\.{}\b)'

# The pattern and the replacement are in the Tuple.
TypeLinkFindReplaceInfo = List[Tuple[str, str]]

TypeMissingLinkInfo = List[Tuple[str, int, int, int]]


class Decl(AnnotationDeclarations):
    BasePart = 'BasePart'
    PartLink = 'PartLink'
    LinkSet = 'LinkSet'
    PartFrame = 'PartFrame'
    RestoreIfxLevelInfo = 'RestoreIfxLevelInfo'
    ActorPart = 'ActorPart'


# -- Function definitions -----------------------------------------------------------------------


def get_frame_repr(part_repr: str, sep: str = "\\.") -> str:
    """
    Given a link chain to a part, returns the link chain to the frame.

    Examples:
    "hub1\\.hub2\\._linked_from_hub_" from "hub1\\.hub2\\.linked_from_hub"
    "hub1.hub2._linked_from_hub_" from "hub1.hub2.linked_from_hub"
    "_linked_from_hub_" from something like this: "linked_from_hub"

    :param part_repr: A string that represents a part link in a script
    :param sep: The separator
    :return: A string that represents a frame link in a script
    """
    elements = part_repr.split(sep)
    last = elements[-1]
    elements = elements[:-1]
    elements.append('_{}_'.format(last))
    return sep.join(elements)


def get_patterns_by_link_item(partial_link_pattern: str) -> List[str]:
    """
    Builds a list of patterns based on a given link item.

    Examples:
    partial_link_pattern = 'data'
    return value = ['\\b(link)(\\.data\\b)',
                    '\\b(link)(\\._data_\\b)']

    partial_link_pattern = 'hub1\\.hub2\\.linked_from_hub'
    return value = ['\\b(link)(\\.hub1\\.hub2\\.linked_from_hub\\b)',
                    '\\b(link)(\\.hub1\\.hub2\\._linked_from_hub_\\b)']

    :param partial_link_pattern: The partial pattern based on the link name that is accessed by a script
    :return: All the patterns that Origame allows to access a link
    """
    # Patterns for linking to a part and its frame
    patterns = list()
    patterns.append(PART_LINK_PATTERN.format(partial_link_pattern))
    patterns.append(PART_LINK_PATTERN.format(get_frame_repr(partial_link_pattern)))

    return patterns


def get_link_find_replace_info(partial_link_pattern: str, new_referenced_link_name) -> TypeLinkFindReplaceInfo:
    """
    Builds a list of patterns to search on and the replacement for the text hit by each pattern.

    Note:
    Both partial_link_pattern and new_referenced_link_name must follow the link referencing conventions.

    Examples:
    See the get_patterns_by_link_item() for the description of the search patterns.

    The replacement for the text hit by each pattern is already prefixed with "link.".

    If new_referenced_link_name = 'new_name", the replacement for the hit text will be:
        'link.new_name'
        'link._new_name_'

    or

    If new_referenced_link_name = 'hub1.hub2.new_name", the replacement for the hit text will be:

    'link.hub1.hub2.new_name'
    'link.hub1.hub2._new_name_'

    :param partial_link_pattern: The partial pattern based on the link name that is accessed by a script
    :param new_referenced_link_name: Used to construct a replacement
    :return: The patterns and the replacement for the text hit by each pattern
    """
    # Patterns for linking to a part and its frame
    find_rep_info = list()
    fri = (PART_LINK_PATTERN.format(partial_link_pattern), "link.{}".format(new_referenced_link_name))
    find_rep_info.append(fri)

    fri = (PART_LINK_PATTERN.format(get_frame_repr(partial_link_pattern)),
           "link.{}".format(get_frame_repr(new_referenced_link_name, sep=".")))
    find_rep_info.append(fri)

    return find_rep_info


def get_cca(source_part: Decl.BasePart, target_part: Decl.BasePart) -> Decl.ActorPart:
    """
    Get the Closest Common Ancestor of parts. If this link is not elevated (is_elevated() is False), this is
    the parent of source part (which is also parent of target part). Otherwise (is_elevated() is True),
    it is the actor part that is the closest common ancestor of source and target. Note that the CCA is the
    actor in which a link is visible.
    :return: the closest common ancestor of the source and target parts.
    """
    path_source = source_part.get_parts_path(with_root=True)
    path_target = target_part.get_parts_path(with_root=True)

    # the root is always a common ancestor, just not necessarily the closest; the only way root could not be
    # common is if the source and target are in different scenarios!
    if path_source[0] is not path_target[0]:
        return None

    # find the first ancestor that is not common:
    for src_part, targ_part in zip(path_source, path_target):
        if src_part is not targ_part:
            return src_part.parent_actor_part
    else:
        # no common ancestor found, so one path must be a subset of the other (link is to/from an ancestor)
        return path_target[-1] if len(path_source) > len(path_target) else path_source[-1]
        # NOTE: if actors cannot be linked to, then following 2 lines should be used instead of above:
        # assert len(path_source) > len(path_target)
        # return path_target[-1]


# -- Class Definitions --------------------------------------------------------------------------

"""
This structure serves multiple purposes. It describes a list of relationships between a part and its script.
1. A part and the script lines that reference a given link name
2. A part and the script itself.
"""
TypeReferencingParts = List[Tuple[Decl.BasePart, Either[List[str], str]]]

# SESSION_ID of the part that has been visited is added to this list.
TypeRefTraversalHistory = List[int]


class InvalidLinkPathSegmentError(SyntaxError):
    """
    Raised when an invalid link path segment is referenced.
    """
    pass


class InvalidPartLinkArgumentsError(Exception):
    """
    Raised when an invalid link path segment is referenced.
    """
    pass


class MissingLinkEndpointPathError(Exception):
    """
    Raised when the link ORI does not have its endpoint path specified. This indicates a missing part in the scenario,
    and an invalid scenario (because no scenario should have missing parts).
    """

    def __init__(self, part_frame: Decl.PartFrame):
        super().__init__("Corrupt scenario: part {} has a dangling link (target path missing)"
                         .format(part_frame.part))


class UnresolvedLinkPathError(Exception):
    """
    Raised when the link target path string could not be resolved to a BasePart. This indicates an
    invalid linking or linking unsupported by Origame.
    """

    def __init__(self, from_part: Decl.BasePart, link_name: str, path_str: str, err_msg: str):
        super().__init__("Unable to resolve link path from {}, link {}, path={}, base error msg:{}"
                         .format(from_part, link_name, path_str, err_msg))
        self.target_path = path_str


class UnresolvedPartRefError(Exception):
    """
    Raised when the link target reference could not be resolved to a BasePart. This indicates an
    invalid linking or linking unsupported by Origame.
    """

    def __init__(self, from_part: Decl.BasePart, link_name: str, target_ref: int):
        super().__init__("Unable to resolve link '{}' from {} to part ID {}"
                         .format(link_name, from_part, target_ref))
        self.target_ref = target_ref


class InvalidLinkError(Exception):
    CAUSE = None  # derived class overrides

    def __init__(self, source_frame: Decl.PartFrame, target_frame: Decl.PartFrame):
        msg = "Link source {} not linkable to {} ({})'".format(source_frame, target_frame, self.CAUSE)
        super().__init__(msg)


class LinkIfxLevelsTooLowError(InvalidLinkError):
    """
    Raised when an attempt is made to create/restore a link that would be invalid because the interface level is
    insufficient.
    """

    CAUSE = 'At least one link frame has insufficient interface level: {}'

    def __init__(self,
                 source_frame: Decl.PartFrame, min_source_ifx_level: int,
                 target_frame: Decl.PartFrame, min_target_ifx_level: int):
        too_small = "{} level={} should be >= {}"

        causes = []
        if source_frame.ifx_level < min_source_ifx_level:
            causes.append(too_small.format('source', source_frame.ifx_level, min_source_ifx_level))
        if target_frame.ifx_level < min_target_ifx_level:
            causes.append(too_small.format('target', target_frame.ifx_level, min_target_ifx_level))
        self.CAUSE = self.CAUSE.format(', '.join(causes))

        super().__init__(source_frame, target_frame)


class LinkMissingEndpointError(InvalidLinkError):
    """
    Raised when an attempt is made to create/restore a link that would be invalid because at least one endpoint
    (source or target frame) is None.
    """

    CAUSE = 'Link source or target frame missing'


class LinkEndpointsNotInScenarioError(InvalidLinkError):
    """
    Raised when an attempt is made to create/restore a link that would be invalid because at least one endpoint
    (source or target frame) has in_scenario False.
    """

    CAUSE = 'Link source or target frame have been removed from scenario'


class RestoreLinkInfo:
    """
    Encapsulate information required to restore a deleted or 'cut' link part.
    """

    def __init__(self, source_frame: Decl.PartFrame, target_frame: Decl.PartFrame):
        """
        :param source_frame: The source_frame PartFrame of the link.
        :param target_frame: The target_frame PartFrame of the link.
        :param elevated_source: the actor part from which link was emerging
        """
        self.source_frame = source_frame
        self.target_frame = target_frame
        self.elevated_source = PartLink.get_elevated_source(source_frame, target_frame)
        self.cca = get_cca(source_frame.part, target_frame.part)
        assert self.cca is not None  # this would imply parts are in different scenarios!

    def check_remove_waypoints(self) -> bool:
        new_elevated_source = PartLink.get_elevated_source(self.source_frame, self.target_frame)
        if new_elevated_source is not self.elevated_source:
            return True
        return get_cca(self.source_frame.part, self.target_frame.part) is not self.cca

    def __str__(self):
        return "{} -> {}".format(self.source_frame.part, self.target_frame.part)


class LinkWaypoint(IOriSerializable, ScenarioObject):
    """
    This class represents a waypoint on a scenario part link.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    SCENARIO_OBJECT_TYPE = ScenarioObjectType.waypoint

    class Signals(BridgeEmitter):
        sig_position_changed = BridgeSignal(float, float)  # x, y

    # Each waypoint has a unique ID, valid for this scenario load only:
    __id_generator = UniqueIdGenerator()

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, link: Decl.PartLink,
                 position: Position = Position(),
                 shared_anim: SharedAnimationModeReader = None):
        """
        :param link: The Link to which this waypoint belongs.
        :param position: The waypoints x-y coordinates.
        """
        IOriSerializable.__init__(self)

        self.signals = LinkWaypoint.Signals()
        self.__anim_mode_shared = shared_anim
        self.__id = self.__id_generator.get_new_id()  # must never change
        self.__link = link
        self.__position = position

        #DRWA
        self.part_type_name = link.part_type_name
        

    def get_ori_ref_key(self) -> int:
        """Get the ORI reference key to use for this part"""
        return self.__id

    def get_position(self) -> Tuple[float, float]:
        """
        Get the position as a set of global scenario coordinates.
        :return: a pair of float values, (x, y)
        """
        return self.__position.to_tuple()

    def set_position(self, x: float, y: float):
        """
        Set the position, in global scenario coordinates.
        :param x: New x position
        :param y: New y position
        """
        if x != self.__position.x or y != self.__position.y:
            self.__position = Position(x, y)
            if self.__anim_mode_shared:
                self.signals.sig_position_changed.emit(x, y)

    def get_pos_vec(self) -> Position:
        """Get position as a vector"""
        return self.__position

    def set_pos_from_vec(self, pos: Position):
        """Set position from a vector"""
        self.__position = pos
        if self.__anim_mode_shared:
            self.signals.sig_position_changed.emit(pos.x, pos.y)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    wp_id = property(get_ori_ref_key)
    position = property(get_position)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    def __str__(self):
        return 'ID {} on link {}'.format(self.__id, self.__link)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):

        if ori_data.get(WpKeys.WAYPOINT_POS) is not None:
            xy = ori_data.get(WpKeys.WAYPOINT_POS)
            x = xy[PosKeys.X]
            y = xy[PosKeys.Y]
            self.set_position(x, y)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:

        waypoint_ori_def = {
            WpKeys.WAYPOINT_POS: {
                PosKeys.X: self.__position.x,
                PosKeys.Y: self.__position.y,
            },
        }

        return waypoint_ori_def

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update(
            {
                WpKeys.WAYPOINT_POS: {
                    PosKeys.X: self.__position.x,
                    PosKeys.Y: self.__position.y,
                },
            }
        )

        # --------------------------- instance _PROTECTED properties and safe slots -----------------


        # --------------------------- instance __PRIVATE members-------------------------------------


class LinkTip:
    """
    This class supports defining the part that is at one of the tips of a link, with overriding of the frame's
    interface level, parent part, or root actor. These overrides facilitate determining whether a link would
    be valid if
    - the ifx level changed
    - the parent changed (i.e., reparenting a part)
    - an ancestor changed (i.e., reprenting an ancestor of the part)
    """

    def __init__(self, part_frame: Decl.PartFrame, ifx_level: int = None,
                 root_part: Decl.ActorPart = None, parent_part: Decl.ActorPart = None):
        """
        :param part_frame: frame of part that is an endpoint of link
        :param parent: assumed parent of endpoint; if None, actual parent
        :param root: assumed root of endpoint; if None, actual root actor
        :param ifx_level: assume ifx level of endpoint; if None, actual ifx level
        """
        self.part_frame = part_frame

        self.ifx_level = ifx_level
        if ifx_level is None:
            self.ifx_level = self.part_frame.ifx_level

        self.root_part = root_part
        self.parent_part = parent_part

    def get_actor_path(self) -> List[Decl.ActorPart]:
        """
        Get the path list of actors of self.part_frame, taking into account the possible overrides of
        parent via self.parent_part and root via self.root_part:

        - if self.parent_part is not None, then it is used instead of self.part_frame.part's actual parent
        - if self.root_part is not None, its path list is prepended to that of self.part_frame

        Examples:
            if part_frame is for a part /part1/part2, and parent override is /part3/part4, and root override is
            /part5/part6, then get_actor_path() returns
            - [part1, part2] if no root or parent override
            - [part3, part4, part2] if no root override
            - [part5, part6, part1, part2] if no parent override
            - [part5, part6, part3, part4, part2] if both overrides
        """
        if self.parent_part is None:
            path = self.part_frame.part.get_parts_path(with_root=True)
        else:
            path = self.parent_part.get_parts_path(with_root=True) + [self.part_frame.part]

        if self.root_part is not None:
            return self.root_part.get_parts_path(with_root=True) + path

        return path

    def check_ifx_level(self, min_level: int) -> bool:
        """Check that current level is greater or equal to given level: True if yes, False otherwise"""
        return self.ifx_level >= min_level

    def need_in_scenario(self) -> bool:
        """
        If either parent_part or root_part were specified for tip, then it is because the part is not in the
        scenario; return False. Otherwise (i.e. both are None), return True.
        """
        return self.parent_part is None and self.root_part is None


class PartLink(IOriSerializable, ScenarioObject):
    """
    Represent a link from one scenario part (the "source") to another (the "target").

    Note: a link's Closest Common Ancestor (CCA) is the actor part that is common to the path of source and target
    and is closest to them (further from root). The root actor is always a common ancestor, but it is the CCA
    of a link only if both source and target parts are children of the root actor.
    """

    SCENARIO_OBJECT_TYPE = ScenarioObjectType.link

    class Signals(BridgeEmitter):
        sig_name_changed = BridgeSignal(str)

        # Used during the in-editor link name editing
        sig_temp_name_changed = BridgeSignal(str)

        sig_link_decluttering_changed = BridgeSignal(bool)
        sig_link_bold_changed = BridgeSignal(bool)
        sig_link_visibility_changed = BridgeSignal(bool)
        sig_waypoint_added = BridgeSignal(int)
        sig_waypoint_removed = BridgeSignal(int)
        sig_target_changed = BridgeSignal()

    @staticmethod
    def check_linkable(source: LinkTip, target: LinkTip, raise_on_fail: bool = False) -> type:
        """
        Test if link is valid. Validity is defined as each endpoint being non-None, having suitable
        interface level, and being in the scenario. Returns True or False.
        :param raise_on_fail: if True, raise exception if not linkable; if False, returns result
        :return: if raise_on_fail is False, returns True if linkable, False otherwise
        """
        try:
            if source.part_frame is None or target.part_frame is None:
                raise LinkMissingEndpointError(source.part_frame, target.part_frame)

            if source.need_in_scenario() is None and not source.part_frame.part.in_scenario:
                raise LinkEndpointsNotInScenarioError(source.part_frame, target.part_frame)

            if target.need_in_scenario() is None and not target.part_frame.part.in_scenario:
                raise LinkEndpointsNotInScenarioError(source.part_frame, target.part_frame)

            min_ifx_level_source, min_ifx_level_target = PartLink.get_min_ifx_levels(source, target)
            if not source.check_ifx_level(min_ifx_level_source):
                raise LinkIfxLevelsTooLowError(source.part_frame, min_ifx_level_source,
                                               target.part_frame, min_ifx_level_target)
            if not target.check_ifx_level(min_ifx_level_target):
                raise LinkIfxLevelsTooLowError(source.part_frame, min_ifx_level_source,
                                               target.part_frame, min_ifx_level_target)

        except InvalidLinkError:
            if raise_on_fail:
                raise
            else:
                return False

        return True

    @staticmethod
    def get_min_ifx_levels(source_tip: LinkTip, target_tip: LinkTip) -> Tuple[int, int]:
        """
        Get the minimum interface levels that a source_tip frame and target_tip frame need to have in order for a link
        between the two to be valid. 

        :return: a pair of integers, first being for source_tip, second being for target_tip
        """
        source_path = source_tip.get_actor_path()
        target_path = target_tip.get_actor_path()

        # they have to be in same scenario!:
        if source_tip.part_frame.part.in_scenario and target_tip.part_frame.part.in_scenario:
            assert source_path[0] is target_path[0]
        assert source_path != target_path  # assumes with_part=True in get_parts_path

        # find the first ancestor that is not common:
        len_cca_path = 0
        for src_part, target_part in zip(source_path, target_path):
            if src_part is target_part:
                len_cca_path += 1
            else:
                min_ifx_level_source = len(source_path) - 1 - len_cca_path
                min_ifx_level_target = len(target_path) - 1 - len_cca_path
                return min_ifx_level_source, min_ifx_level_target

        # if we get this far, it's because one path is a subset of the other; this can only happen when the
        # link is between a part and one of its ancestors
        len_diff = len(source_path) - len(target_path)
        if len_diff < 0:
            return 0, -len_diff - 1
        else:
            return len_diff - 1, 0

    @staticmethod
    def get_elevated_source(source_frame: Decl.PartFrame, target_frame: Decl.PartFrame) -> Decl.ActorPart:
        """
        Get the actor that has ifx port from which this link emerges. It does not depend on the actual ifx level
        of source and target frames, but it does require that they be "in" the scenario (i.e. not suspended
        or removed).
        :return: the actor part that has ifx port from which this link emerges, or None if no elevated source
            (which happens if the link is local, or if it is non-local to a part that is descendant of
            the source's parent).
        """
        return PartLink.get_elevated_actors(source_frame, target_frame)[0]

    @staticmethod
    def get_elevated_actors(source_frame: Decl.PartFrame,
                            target_frame: Decl.PartFrame) -> Tuple[Decl.ActorPart, Decl.ActorPart]:
        """
        Get the actors that have ports connected by this link.
        :return: (source actor, target actor); either (or both) can be None, if has_elevated_source/target() is False.
        """
        path_source = source_frame.part.get_parts_path(with_root=True)
        path_target = target_frame.part.get_parts_path(with_root=True)

        # the root is always a common ancestor, just not necessarily the closest; the only way root could not be
        # common is if the source and target are in different scenarios!
        if path_source[0] is not path_target[0]:
            raise InvalidLinkError(source_frame, target_frame)

        # find the first ancestor that is not common:
        for src_part, targ_part in zip(path_source, path_target):
            if src_part is not targ_part:
                break
        else:
            # no common ancestor found, so one path must be a subset of the other (link is to/from an ancestor)
            if len(path_source) > len(path_target):
                src_part, targ_part = path_source[len(path_target)], None
            else:
                assert len(path_source) < len(path_target)
                src_part, targ_part = None, path_target[len(path_source)]

        if src_part is source_frame.part:
            src_part = None
        if targ_part is target_frame.part:
            targ_part = None
        # assert self.has_elevated_source() == (src_part is not None)
        # assert self.has_elevated_target() == (targ_part is not None)
        return src_part, targ_part

    @staticmethod
    def get_ifx_parts(source_frame: Decl.PartFrame,
                      target_frame: Decl.PartFrame) -> Tuple[Decl.BasePart, Decl.BasePart]:
        """
        Returns the source and target ifx parts of a link assumed to be between a source and target frame.
        The frames must be for parts that are in scenario (not suspended or removed parts), and does not
        depend on the actual ifx levels of source and frame.
        :return: a pair of parts, never None. Local links (that join two parts that have
            same parent) have source part and target part as returns. Link that has an elevated source
            has the first item as that actor; link that has an elevated target has second item as that
            actor.
        """
        elev_src_actor, elev_targ_actor = PartLink.get_elevated_actors(source_frame, target_frame)
        return elev_src_actor or source_frame.part, elev_targ_actor or target_frame.part

    # we have 0 or more BasePart children ORI serializable
    _ORI_HAS_CHILDREN = True

    # All links have a unique ID. It is however specific to the session (does not get saved/loaded with scenario,
    # because pieces of one scenario can be imported into other scenarios)
    __id_generator = UniqueIdGenerator()

    def __init__(self, from_part_frame: Optional[Decl.PartFrame],
                 to_part_frame: Decl.PartFrame = None,
                 name: str = None,
                 shared_anim: SharedAnimationModeReader = None,
                 waypoints: List[Position] = None,
                 copy_unattached: Decl.PartLink = None):
        """
        Create a link that connects from_part_frame to to_part_frame. The to_part_frame can be None if the link
        is being created from loading an Origame file; the target will be resolved to a part frame later (see
        set_from_ori()).

        :param from_part_frame: The source part frame. If None, the source must be set later via a restore_*() method.
        :param to_part_frame: The target part frame. If None, the target must be set later via set_from_ori() or
            via a restore_*() method.
        :param name: The link name. If None, the name must be set later via set_name() otherwise likely to break.
        :param shared_anim: the shared animation state, so the link knows when to signal state changes.
        :param waypoints: an initial list of waypoints, in the source ifx part parent coordinate system.
        :param copy_unattached: if given, assumed to be another link from which to copy name, shared_anim, and
            other attributes of link. Does not copy the source or target part frames (since there can only be one
            link between any two frames), nor does it copy the waypoints (if those are desired in the copy, they
            can be provided via the waypoints parameter).
        """
        IOriSerializable.__init__(self)

        self.signals = PartLink.Signals()
        self.SESSION_ID = self.__id_generator.get_new_id()  # must never change during session

        if copy_unattached is None:
            validate_python_name(name)
            self.__name = name
            # The name used during editing, before it is applied:
            self.__temp_name = None

            self.__anim_mode_shared = shared_anim
            self.__declutter = False
            self.__bold = False
            self.__visible = True

        else:
            self.__name = copy_unattached.__name
            # The name used during editing, before it is applied:
            self.__temp_name = copy_unattached.__temp_name

            self.__anim_mode_shared = copy_unattached.__anim_mode_shared
            self.__declutter = copy_unattached.__declutter
            self.__bold = copy_unattached.__bold
            self.__visible = copy_unattached.__visible

        self.__source_part_frame = from_part_frame
        self.__target_part_frame = to_part_frame
        if waypoints is None:
            self.__link_waypoints = []
        else:
            self.__link_waypoints = [LinkWaypoint(self, wp, shared_anim=self.__anim_mode_shared)
                                     for wp in waypoints]

        if to_part_frame is not None:
            to_part_frame.attach_incoming_link(self)  # Tell the target its being pointed at by this instance.


        #DRWA
        self.part_type_name = from_part_frame.get_part().PART_TYPE_NAME


        log.debug("Created link {}", self)

    def get_link_chains(self, traversal_history: TypeRefTraversalHistory) -> List[List[Decl.PartLink]]:
        """
        Gets all the reachable link chains. Note: When a chain has only one element, it is a direct link. All the
        chains are unique. In other words, recursions are avoided.

        :param traversal_history: Used to avoid recursions.
        :return: All the reachable non-recursive link chains.
        """
        out_chains = self.target_part_frame.part.get_link_chains(traversal_history)

        if not out_chains:
            # Empty - no outgoing chains, meaning the target is a leaf
            return [[self]]

        return [[self] + out_chain for out_chain in out_chains]

    def target_needs_resolving(self) -> bool:
        """
        Check if this link has a target that points to another object (return False), or does it just have a
        path/reference that needs resolving to another object (returns True).
        """
        try:
            self.__target_path
        except AttributeError:
            # if there is no target path then there MUST be a target part!
            assert self.__target_part_frame is not None
            return False

        return True

    def resolve_path(self, parent_actor_part: Decl.ActorPart, refs_map: Dict[int, Decl.BasePart]):
        """
        This function resolves the temporary __target_path attribute created by _get_ori_def_impl() to an
        actual PartFrame object that is the target of this link.

        Note: This function must be called after ALL Parts in the Origame scenario have been instantiated.

        :param parent_actor_part: The parent Actor Part of the source Part of this link.
        :param refs_map: the parts reference map that maps part key BasePart instance
        :raises UnresolvedPartRefError, UnresolvedLinkPathError: Raised if target path could not be resolved

        When the target path is a number it is assumed to be the key in the refs_map. The resolution of the
        link is then straightforward: the target key is either in the map, or it is not. If it is not, an
        exception is raised. If it is, the link is ready to be used.

        When the target path of this instance is a string, it is assumed to be a build 1 style path through
        the actor hierarchy, relative to the source part. THIS FORMAT IS DEPRECATED. It remains readable on load
        in order to support loading build 1 scenarios. Details:

            The path string consists of a combination of the following elements:

            - '/': which is a path segment delimiter
            - '..': which is the notation for parent part (going up one level in actor hierarchy)
            - '[integer]': a number which denotes the index of a child Part in the list of children of the parent

            Examples:

            - '..' is the parent: the target is the parent of the current source part
            - '../2' is child part at index 2 in the list of children of the *parent*
            - '../../2/3' is child part at index 3 of the child part at index 2 of the grandparent of current source

            The following cases are supported by link paths:

            1. path = '2' or '../2': link is pointing to a sibling part of the link's source (part). The
                sibling part belongs to the same parent ActorPart and has index = 2 in the Actor Part's
                list of child parts. Example: actor A contains child parts B and C, then link from B to C
                is '2' or '../2' if C is at index 2 in A's list of children.
            2. path = '..': link is pointing to the parent Actor Part of the link source (part).
                Example: actor A contains child part B, then link from B to A (its source) is '..'
            3. path = '../..': link is pointing to the grandparent Actor Part of the link source (part).
                In other words, the parent Actor Part of the the parent Actor Part of the link's source
                (part). Currently, this is defined only for boundary socket part nodes. Example: if actor A contains
                actor B, and B contains socket C referencing B's node D, then link going from D to A is ../..
            4. path = '../../2': link is pointing to a child part of its grandparent Actor Part. The child has
                index = 2 in the grandparent Actor Part's list of child parts. Currently, this is defined only for boundary
                socket part nodes. Example: if actor A contains part F and actor B, and B contains socket C referencing B's
                node D, then link going from D to F would be ../../2 if F is at index 2 of A's list of children parts.
            5. path = '../../2/1': link is pointing to the grandparent Actor Part's child's child. In this case, the
                child part denoted by index '2' would be a child Actor Part of the grandparent Actor part,
                and the target part is the child of the child Actor Part and has index = 1 in the child Actor
                Part's list of child parts. Currently, this is defined only between boundary socket nodes. Example:
                actor A contains child actors B and C; B has boundary socket BS that references a child node BN; simiarly,
                C has boundary socket CS that references a child node CN; then a link from BN to CN would have path
                ../../2/1 if C is child 2 in A's list of children, and CN is child 1 in C's list of children.
            6. path = '2/1': link is pointing to a child part in a child actor. Currently this is possible only to
                boundary socket node parts. Example: if actor A contains a part B and an actor part C, and C contains a
                boundary socket CS that references C's node CN, then B linked to CN would be 2/1 if C is child 2 in the
                list of A's children parts, and CN is child 1 in C's list of children.

            Essentially,

            A. any part can be linked to a sibling part (case 1), its parent (case 2), or a node that is in a sibling actor
                (if the node is in a boundary socket of the sibling actor -- the socket does not appear in the path) (case 6).
            B. any boundary socket node can be linked, in addition to cases covered by B, to its grandparent (case 3),
                a child of its grandparent (case 4), or to a boundary socket node of another actor part, if the other
                actor part is sibling of the parent of the first node (case 5).
        """
        if PARENT_ACTOR_PATH == self.__target_path:
            self.__target_part_frame = parent_actor_part.part_frame

        elif type(self.__target_path) == int:
            try:
                self.__target_part_frame = refs_map[self.__target_path].part_frame
            except KeyError:
                raise UnresolvedPartRefError(self.__source_part_frame.part, self.__name, self.__target_path)

        else:
            # Pre-process the path segments in case sibling notation has been used (Ex. '../2' or '2') and only
            # pass the parent what it needs to know.
            path_to_resolve = self.__target_path
            if LINK_PATH_DELIM in self.__target_path:
                path_root, path_remainder = self.__target_path.split(LINK_PATH_DELIM, 1)

                if path_root == PARENT_ACTOR_PATH:
                    # Ignore the first part of the path. # case: "../[digit]"
                    path_to_resolve = path_remainder

            # Resolve the target path
            try:
                self.__target_part_frame = parent_actor_part.resolve_link_path(path_to_resolve)
            except InvalidLinkPathSegmentError as error:
                # likely caused because unsupported part was specified in ORI def
                raise UnresolvedLinkPathError(self.__source_part_frame.part, self.__name, self.__target_path, error.msg)

        # Inform the target object that it is being pointed at by this instance.
        # Note: __target_part_frame is valid by this point (otherwise an exception was thrown)
        self.__target_part_frame.attach_incoming_link(self)

        del self.__target_path  # Once resolved, must be removed.

        log.debug("Resolved path of link: {}", self)

    def remove_by_source(self, restorable=False) -> RestoreLinkInfo:
        """
        Detach this link from its source and target parts. This function MUST only be called by the source PartFrame.

        :param restorable: True if the delete operation is to be restorable (undoable). When True, the function returns
            information sufficient for restoring the deleted instance. The flag is False if the delete operation is to
            be permanent. If False, the function simply returns the None object.
        :returns Conditionally, an information object with sufficient info for restoring the deleted link, or None.
            (See description of 'restorable' argument.)
        """
        self.__target_part_frame.detach_incoming_link(self)
        source_frame = self.__source_part_frame
        target_frame = self.__target_part_frame
        self.__source_part_frame = None
        self.__target_part_frame = None

        if restorable:
            return RestoreLinkInfo(source_frame, target_frame)
        else:
            return None

    def replace_by_inverted(self, restorable: bool = False) -> RestoreLinkInfo:
        """Replace this link in the source frame by one that has same properties but is inverted"""
        return self.__source_part_frame.replace_outgoing_link_by_inverted(self, restorable)

    def remove_self(self, restorable: bool = False) -> RestoreLinkInfo:
        """
        This function provides a mechanism for directly deleting this link instance without going through its
        source PartFrame. It delegates the call to the source and is provided for convenience.

        :param restorable: True if the delete operation is to be restorable (undoable). When True, the function returns
            information sufficient for restoring the deleted instance. The flag is False if the delete operation is to
            be permanent. If False, the function simply returns the None object.
        :returns Conditionally, an information object with sufficient info for restoring the deleted link, or None.
            (See description of 'reversible' argument.)
        """
        return self.__source_part_frame.remove_outgoing_link(self, restorable=restorable)

    def restore_by_source(self, link_info: RestoreLinkInfo):
        """
        Restore this link to pre-removal state, using provided restoration info. This must only be called by the
        source frame: its purpose is to re-attach the link to the source and target frames. Note: this does not
        signal the existence of new outgoing link on source frame, but does signal existence of new incoming link
        on target frame, so link must be ready for use when this method is called.

        :param link_info: restoration data obtained from remove_self() or
        """
        assert link_info.source_frame
        assert link_info.target_frame
        assert PartLink.check_linkable(LinkTip(link_info.source_frame), LinkTip(link_info.target_frame))
        self.__source_part_frame = link_info.source_frame
        self.__target_part_frame = link_info.target_frame  # A reference to the object pointed at by the link.
        self.__target_part_frame.attach_incoming_link(self)

    def restore_self(self, link_info: RestoreLinkInfo):
        """
        Restore the link, without having to determine the source and target. It is provided for convenience,
        as it is the same as self.source_frame.restore_outgoing_link(self, link_info).

        :param link_info: A data object containing sufficient info to restore the instance to a pre-deleted state.
        :except: any exception raised by PartFrame.restore_outgoing_link()
        """
        source_frame = link_info.source_frame
        source_frame.restore_outgoing_link(self, link_info)

    def restore_valid(self, link_info: RestoreLinkInfo) -> Dict[Decl.PartFrame, Decl.RestoreIfxLevelInfo]:
        """
        Restore this link to a valid state: adjust source_tip and target_tip frame ifx levels as necessary so that once
        restored, the link will be valid. Waypoints are dropped. A new PartLink instance is actually used to minimize
        how much state is changed on existing link (self).

        :param link_info: restoration info for the link
        :param with_source_parent: the parent of source_tip frame; if None, the parent specified in the link_info
        :param with_target_parent: the parent of target_tip frame; if None, the parent specified in the link_info
        :return: a mapping of part frames to ifx level restoration info
        """
        # Oliver TODO: test case for two links to same frame but first link needs to increase ifx level
        #     of frame to N, whereas second link needs to increase it to M<N: verify that second adjustment
        #     does not occur!!!
        source_frame, target_frame = link_info.source_frame, link_info.target_frame
        source_tip, target_tip = LinkTip(source_frame), LinkTip(target_frame)

        # adjust levels: 
        min_ifx_level_source, min_ifx_level_target = PartLink.get_min_ifx_levels(source_tip, target_tip)
        restore_ifxs = {}

        if not source_tip.check_ifx_level(min_ifx_level_source):
            restore_ifx = source_frame.set_ifx_level(min_ifx_level_source, restorable=True)
            assert not restore_ifx.broken_links_out
            assert not restore_ifx.broken_links_in
            restore_ifxs[source_frame] = restore_ifx

        if not target_tip.check_ifx_level(min_ifx_level_target):
            restore_ifx = target_frame.set_ifx_level(min_ifx_level_target, restorable=True)
            assert not restore_ifx.broken_links_out
            assert not restore_ifx.broken_links_in
            restore_ifxs[target_frame] = restore_ifx

        source_frame.restore_outgoing_link(PartLink(None, copy_unattached=self), link_info)

        return restore_ifxs

    def check_valid(self) -> bool:
        """
        Test if link is valid. Calls PartLink.check_linkable()
        """
        return PartLink.check_linkable(LinkTip(self.__source_part_frame), LinkTip(self.__target_part_frame))

    def is_local(self) -> bool:
        """Return True if source and parent in same actor, False otherwise"""
        return not self.is_elevated()

    def is_elevated(self) -> bool:
        """Return True if source and target are in different actors, False if in same (parent) actor"""
        return self.__source_part_frame.part.parent_actor_part is not self.__target_part_frame.part.parent_actor_part

    def has_elevated_source(self) -> bool:
        """Return True if the source's parent is not the boundary actor (CCA), False otherwise"""
        return self.__has_elevated_endpoint(self.__source_part_frame.part)

    def has_elevated_target(self) -> bool:
        """Return True if the target's parent is not the boundary actor (CCA), False otherwise"""
        return self.__has_elevated_endpoint(self.__target_part_frame.part)

    def get_cca(self) -> Decl.ActorPart:
        """
        Get the Closest Common Ancestor of this link. If this link is not elevated (is_elevated() is False), this is
        the parent of source part (which is also parent of target part). Otherwise (is_elevated() is True),
        it is the actor part that is the closest common ancestor of source and target. Note that the CCA is the
        actor in which a link is visible.
        :return: the closest common ancestor of the source and target parts.
        """
        return get_cca(self.__source_part_frame.part, self.__target_part_frame.part)

    def get_name(self) -> str:
        """
        :return: Returns the name of the link.
        """
        return self.__name

    def set_name(self, new_name: str) -> bool:
        """
        This function sets the name of the link to the specified string if the new name is deemed valid. This function
        is called for a link renaming operation.
        The link checks the new_name with the source PartFrame to ensure the name is unique among the outgoing
        links managed by the parent, if not, the name is not set and the function returns False.

        :param new_name: The (proposed) new name for the instance.
        :return: True if the specified name was successfully set; False otherwise.
        :raises InvalidPythonNameError: Raised by validate_python_name() if the new name is not a valid Python name.
        """
        validate_python_name(new_name)

        if (self.__name != new_name
            and not self.__source_part_frame.is_link_name_taken(new_name)
            and not self.__source_part_frame.is_link_temp_name_taken(new_name)):
            old_name = self.__name
            self.__name = new_name
            self.__source_part_frame.on_outgoing_link_renamed(old_name, new_name)
            if self.__anim_mode_shared:
                self.signals.sig_name_changed.emit(new_name)
            return True
        else:
            return False

    def set_unique_name(self, new_name: str):
        """
        Sets the link name that is unique among those of its outgoing neighbours on the part frame.
        :param new_name: A unique name. It is the user's responsibility to make sure it is unique.
        """
        if self.__name == new_name:
            return

        old_name = self.__name
        self.__name = new_name
        self.__source_part_frame.on_outgoing_link_renamed(old_name, new_name)

        if self.__anim_mode_shared:
            self.signals.sig_name_changed.emit(new_name)

    def get_temp_name(self) -> str:
        """
        Gets the temporal name used during editing before it is applied.
        :return: The temporal name
        """
        return self.__temp_name

    def set_temp_name(self, new_name: str):
        """
        Sets the temporal name used during editing before it is applied.
        :param new_name: The temporal name
        """
        if self.__temp_name == new_name:
            return

        self.__temp_name = new_name
        if self.__anim_mode_shared:
            self.signals.sig_temp_name_changed.emit(new_name)

    def get_declutter(self) -> bool:
        """
        :return: The value of the declutter flag. When true, the link should be represented in a simplified
            form that decreases clutter.
        """
        return self.__declutter

    def set_declutter(self, value: bool):
        """
        Set the value of the declutter flag.
        :param value: The declutter flag value.
        """
        if self.__declutter != value:
            self.__declutter = value
            if self.__anim_mode_shared:
                self.signals.sig_link_decluttering_changed.emit(value)

    def get_bold(self) -> bool:
        """
        :return: The value of the bold flag.
        """
        return self.__bold

    def set_bold(self, value: bool):
        """
        Set the value of the bold flag.
        :param value: The bold flag value.
        """
        if self.__bold != value:
            self.__bold = value
            if self.__anim_mode_shared:
                self.signals.sig_link_bold_changed.emit(value)

    def get_visible(self) -> bool:
        """
        :return: The value of the visible flag.
        """
        return self.__visible

    def set_visible(self, value: bool):
        """
        Set the value of the visible flag.
        :param value: The visible flag value.
        """
        if self.__visible != value:
            self.__visible = value
            if self.__anim_mode_shared:
                self.signals.sig_link_visibility_changed.emit(value)

    def get_source_part_frame(self) -> Decl.PartFrame:
        """
        :return: Returns a reference to the part frame the link belongs to.
        """
        return self.__source_part_frame

    def get_target_part_frame(self) -> Decl.PartFrame:
        """
        :return: Return the reference to the part frame pointed to by this instance.
        """
        return self.__target_part_frame

    def retarget_link(self, new_target_frame) -> RestoreLinkInfo:
        """
        Changes the target link anchor.
        :param new_target_frame: The new part frame to set as link target.
        :return: Information to restore the original link target.
        """
        restore_info = RestoreLinkInfo(self.__source_part_frame, self.__target_part_frame)
        self.__target_part_frame.detach_incoming_link(self)
        self.__target_part_frame = new_target_frame
        self.__target_part_frame.attach_incoming_link(self)
        self.__source_part_frame.part.on_link_target_part_changed(self)
        if self.__anim_mode_shared:
            self.signals.sig_target_changed.emit()
        return restore_info

    def restore_retargeted_link(self, orig_target_info: RestoreLinkInfo):
        """
        Restores the original target link anchor.
        :param orig_target_info: Information abour the original links source and target frames.
        """
        orig_target_frame = orig_target_info.target_frame
        self.__target_part_frame.detach_incoming_link(self)
        self.__target_part_frame = orig_target_frame
        self.__target_part_frame.attach_incoming_link(self)
        if self.__anim_mode_shared:
            self.signals.sig_target_changed.emit()

    def add_waypoint(self, position: Position, index: int = None) -> LinkWaypoint:
        """
        Adds a waypoint to this link.
        :param: position: the position of the waypoint in scenario coordinates.
        :param: index: the ordered index of the waypoint starting closest to the source part frame.
        :returns: the new waypoint.
        """
        waypoint = LinkWaypoint(self, position, shared_anim=self.__anim_mode_shared)
        if index is None:
            index = len(self.__link_waypoints)
        self.__link_waypoints.insert(index, waypoint)
        if self.__anim_mode_shared:
            self.signals.sig_waypoint_added.emit(index)
        return waypoint

    def remove_waypoint(self, waypoint: LinkWaypoint) -> int:
        """
        Removes the waypoint.
        :param waypoint: the waypoint to remove.
        :returns: the index of the waypoint.
        """
        index = self.__link_waypoints.index(waypoint)
        self.__link_waypoints.remove(waypoint)
        if self.__anim_mode_shared:
            self.signals.sig_waypoint_removed.emit(index)
        return index

    def restore_waypoint(self, waypoint: LinkWaypoint, index: int):
        """
        Restores a previously removed waypoint.
        :param waypoint: the waypoint to restore.
        :param index: the index of teh waypoint to restore.
        """
        self.__link_waypoints.insert(index, waypoint)
        if self.__anim_mode_shared:
            self.signals.sig_waypoint_added.emit(index)

    def remove_waypoints(self, waypoint_selection: List[LinkWaypoint]) -> Tuple[List[int], List[LinkWaypoint]]:
        """
        Removes the waypoints.
        :param waypoint_selection: the list of selected waypoints to remove (random order).
        :returns: a tuple containing a list removed waypoints in source-to-target order and corresponding indices.
        """

        # Create a record of the waypoints removed in order from source-to-target and corresponding index
        # This record is returned to the calling undo stack command for waypoint restore purposes
        wps_indices_in_order = []
        wps_removed_in_order = []
        for waypoint in self.__link_waypoints:
            if waypoint in waypoint_selection:
                wps_indices_in_order.append(self.__link_waypoints.index(waypoint))
                wps_removed_in_order.append(waypoint)

        # Remove the waypoints
        for waypoint in waypoint_selection:
            self.remove_waypoint(waypoint)

        assert len(wps_indices_in_order) > 0
        assert len(wps_removed_in_order) > 0
        return wps_indices_in_order, wps_removed_in_order

    def restore_waypoints(self, waypoints: List[LinkWaypoint], indeces: List[int]):
        """
        Restores a previously removed waypoints.
        :param waypoint: the list of waypoints to restore.
        :param index: the indeces of the waypoints to restore.
        """
        for index, waypoint in zip(indeces, waypoints):
            self.__link_waypoints.insert(index, waypoint)
            if self.__anim_mode_shared:
                self.signals.sig_waypoint_added.emit(index)

    def remove_all_waypoints(self) -> List[LinkWaypoint]:
        """
        Removes all waypoints from the link and returns them.
        """
        waypoints = self.__link_waypoints[:]
        for waypoint in waypoints:
            self.remove_waypoint(waypoint)
        return waypoints

    def restore_all_waypoints(self, waypoints: List[LinkWaypoint]):
        """
        Restores all waypoints to the link.
        :param waypoints: A list of waypoints to restore (typically obtained from remove_all_waypoints())
        """
        for index, waypoint in enumerate(waypoints):
            self.restore_waypoint(waypoint, index)

    def move_waypoints(self, waypoint_offset: Vector):
        """
        Updates the position of the link's waypoints with the given offset.
        :param waypoint_offset: A tuple with an x and y offset in the zeroth and first indices respectively.
        """
        for waypoint in self.__link_waypoints:
            waypoint.set_pos_from_vec(waypoint.get_pos_vec() + waypoint_offset)

    def moved_waypoints(self, waypoint_offset: Vector) -> List[Position]:
        """
        Return a list of shifted waypoint positions.
        :param waypoint_offset: the shift to add to all waypoints of this link
        """
        return [waypoint.get_pos_vec() + waypoint_offset
                for waypoint in self.__link_waypoints]

    def get_waypoint(self, index: int) -> Optional[LinkWaypoint]:
        """
        Get the indexed waypoint.
        :param index: the index corresponding to the waypoint.
        :return: the waypoint if any.
        """
        try:
            return self.__link_waypoints[index]
        except IndexError:
            return None

    def get_waypoints(self) -> List[LinkWaypoint]:
        """
        Get all the waypoints for this PartLink.
        :return: a list of waypoints.
        """
        return self.__link_waypoints

    def get_link_chain_sources(self,
                               referencing_parts: TypeReferencingParts,
                               traversal_history: TypeRefTraversalHistory):
        """
        This is the starting point of the traversal to find out all the parts that reference this link.
        :param referencing_parts: User-defined data related to this part.
        To be populated with the referencing parts, if any
        :param traversal_history: Used to avoid traversing more than once on the same part
        """
        self.__source_part_frame.part.get_link_chain_sources(referencing_parts,
                                                             traversal_history,
                                                             self.__name)

    def on_link_renamed(self,
                        referencing_parts: TypeReferencingParts,
                        traversal_history: TypeRefTraversalHistory,
                        new_name: str):
        """
        This is the starting point of the traversal to find out all the parts that reference this link.
        :param referencing_parts: User-defined data related to this part.
        To be populated with the referencing parts, if any
        :param traversal_history: Used to avoid traversing more than once on the same part
        :param new_name: The new link name that is used to replace the old name in the script
        """
        self.__source_part_frame.part.on_link_renamed(referencing_parts,
                                                      traversal_history,
                                                      self.__name,
                                                      new_name)

    def check_rename_allowed(self) -> bool:
        """
        Traverse along the incoming links to find all the parts that reference this link. If none of the parts
        hsa unapplied changes, it returns True.
        :return: True - allowed (None of the parts has unapplied changes)
        """
        referencing_parts = list()
        traversal_history = list()
        self.__source_part_frame.part.get_link_chain_sources(referencing_parts,
                                                             traversal_history,
                                                             self.__name)
        for part, _ in referencing_parts:
            if part.has_unapplied_edits:
                return False

        return True

    def __str__(self) -> str:
        """Return a string representation of link object"""
        spf = self.__source_part_frame
        tpf = self.__target_part_frame
        return '{} -> {} (ID {})'.format(spf.part if spf else '<??>', tpf.part if tpf else '<??>', self.SESSION_ID)

    name = property(get_name, set_name)
    temp_name = property(get_temp_name, set_temp_name)
    source_part_frame = property(get_source_part_frame)
    target_part_frame = property(get_target_part_frame)
    declutter = property(get_declutter, set_declutter)
    bold = property(get_bold, set_bold)
    visible = property(get_visible, set_visible)
    waypoints = property(get_waypoints)

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        """
        Note: The link name is not part of the info contained in ori_data object. The name is passed in separately
        via the constructor. Links can be created from ORI data, from the GUI, or from a script. The common way
        to set the link name is via constructor. In the .ORI file, the dicts containing the link data keyed
        by link name.
        """
        self.__declutter = ori_data.get(PwKeys.DECLUTTER, self.__declutter)  # True to declutter link; False otherwise
        self.__bold = ori_data.get(PwKeys.BOLD, self.__bold)
        self.__visible = ori_data.get(PwKeys.VISIBLE, self.__visible)
        if PwKeys.TARGET_PATH not in ori_data and PwKeys.TARGET_PATH_OLD not in ori_data:
            raise MissingLinkEndpointPathError(self.__source_part_frame)
        # Create a TEMPORARY attribute that will be discarded later once all scenario parts have been created
        try:
            self.__target_path = ori_data[PwKeys.TARGET_PATH]
        except KeyError:
            self.__target_path = ori_data[PwKeys.TARGET_PATH_OLD]

        # Remove existing waypoints
        self.remove_all_waypoints()
        assert self.__link_waypoints == []

        waypoint_context = context
        if context == OriContextEnum.assign:
            waypoint_context = OriContextEnum.copy

        # Create the waypoints:
        waypoints_ori = ori_data.get_sub_ori_list(PwKeys.WAYPOINTS)
        for index, waypoint_ori in enumerate(waypoints_ori):
            self.__create_waypoint_from_ori(waypoint_ori, waypoint_context)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = {
            PwKeys.DECLUTTER: self.__declutter,
            PwKeys.BOLD: self.__bold,
            PwKeys.VISIBLE: self.__visible,
            PwKeys.TARGET_PATH: self.__get_target_ref_id(),
            PwKeys.WAYPOINTS: [],
        }

        waypoint_context = context
        if context == OriContextEnum.assign:
            waypoint_context = OriContextEnum.copy

        # Append waypoint ORI data
        waypoints = ori_def[PwKeys.WAYPOINTS]
        for waypoint in self.__link_waypoints:
            ori_waypoint = waypoint.get_ori_def(context=waypoint_context)
            waypoints.append(ori_waypoint)

        return ori_def

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update(
            {
                PwKeys.DECLUTTER: self.__declutter,
                PwKeys.BOLD: self.__bold,
                PwKeys.VISIBLE: self.__visible,
            },
        )

    @override(IOriSerializable)
    def _has_ori_changes_children(self) -> bool:
        # Check waypoints for changes
        for waypoint in self.__link_waypoints:
            if waypoint.has_ori_changes():
                return True

        return False

    @override(IOriSerializable)
    def _set_ori_snapshot_baseline_children(self, baseline_id: OriBaselineEnum):
        for waypoint in self.__link_waypoints:
            waypoint.set_ori_snapshot_baseline(baseline_id)

    def __has_elevated_endpoint(self, part: Decl.BasePart):
        cca = get_cca(self.__source_part_frame.part, self.__target_part_frame.part)
        if cca is part:
            # source or target is an ancestor
            return False
        return cca is not part.parent_actor_part

    def __get_target_ref_id(self) -> int:
        return self.__target_part_frame.part.SESSION_ID

    def __create_waypoint_from_ori(self, ori_data: OriScenData, context: OriContextEnum) -> LinkWaypoint:
        """
        Create a new waypoint for this link from an ori data dictionary.
        :param ori_data: The data dictionary describing the part to create.
        :param context: The context of the current create operation.
        :returns: The link waypoint.
        """
        waypoint = LinkWaypoint(self, shared_anim=self.__anim_mode_shared)
        waypoint.set_from_ori(ori_data, context=context)
        self.__link_waypoints.append(waypoint)
        index = self.__link_waypoints.index(waypoint)
        self.signals.sig_waypoint_added.emit(index)
        return waypoint


# type used in annotations
PartLinksRestoreMap = Dict[PartLink, RestoreLinkInfo]
TypeLinkChainNameAndLink = List[Tuple[str, PartLink]]


class LinkSet:
    """
    Utility class that makes it easy to hold a set of links and group them by incoming vs outgoing
    """

    def __init__(self, incoming: PartLinksRestoreMap = None, outgoing: PartLinksRestoreMap = None):
        self.incoming = [] if incoming is None else incoming
        self.outgoing = [] if outgoing is None else outgoing

    def get_all(self) -> PartLinksRestoreMap:
        all = self.incoming.copy()
        all.extend(self.outgoing)
        return all

    def __bool__(self):
        """Returns True if either incoming or outgoing contain something; False only if both are empty"""
        return bool(self.incoming or self.outgoing)

    def __eq__(self, other: Decl.LinkSet):
        return self.incoming == other.incoming and self.outgoing == other.outgoing

    def __ne__(self, other: Decl.LinkSet):
        return not (self == other)


class UnrestorableLinks:
    """
    Utility class that makes it easy to hold a set of links and group them by incoming vs outgoing
    """

    def __init__(self, incoming: PartLinksRestoreMap = None, outgoing: PartLinksRestoreMap = None):
        self.incoming = {} if incoming is None else incoming
        self.outgoing = {} if outgoing is None else outgoing

    def empty(self) -> bool:
        """Return True if both incoming and outgoing are empty"""
        return not self.incoming and not self.outgoing
