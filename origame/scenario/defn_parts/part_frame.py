# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Functionality related to scenario part frame

The frame of a part contains its position, size, name, comment, etc.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import unique, IntEnum
import re

# [2. third-party]

# [3. local]
from ...core import BridgeEmitter, BridgeSignal, validate_python_name, get_valid_python_name, InvalidPythonNameError
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriBaselineEnum, OriContextEnum, OriScenData, JsonObj, OriSchemaEnum
from ..ori import OriSizeKeys as SzKeys
from ..ori import OriPositionKeys as PosKeys
from ..ori import OriPartFrameKeys as PfKeys
from ..animation import SharedAnimationModeReader
from ..proto_compat_warn import prototype_compat_property_alias, prototype_compat_method

from .part_link import PartLink, UnresolvedPartRefError, UnresolvedLinkPathError
from .part_link import RestoreLinkInfo, PartLinksRestoreMap, LinkSet, LinkTip
from .common import Position, Size, Vector

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PartFrame',
    'DetailLevelEnum',
    'LinkRestorationEnum',
    'FrameStyleEnum',
    'RestoreIfxLevelInfo',
]

log = logging.getLogger('system')

MAX_IFX_LEVEL = 100


class Decl(AnnotationDeclarations):
    BasePart = 'BasePart'
    PartFrame = 'PartFrame'
    ActorPart = 'ActorPart'
    RestoreIfxLevelInfo = 'RestoreIfxLevelInfo'


# -- Function definitions -----------------------------------------------------------------------

def init_auto_scripting_api(cls):
    # init the scripting API for this class:
    api = []
    for item in cls.META_AUTO_SCRIPTING_API_EXTEND:
        found = False
        for attrib_name, attrib in vars(cls).items():
            if attrib is item:
                api.append(attrib_name)
                found = True
                break

        if not found:
            raise RuntimeError('BUG: attrib "{}" could not be matched to an object in class {}'
                               .format(attrib_name, cls.__name__))

    cls.AUTO_SCRIPTING_API = tuple(api)
    del cls.META_AUTO_SCRIPTING_API_EXTEND


# -- Class Definitions --------------------------------------------------------------------------

class DuplicateLinkError(Exception):
    """
    Raised when an attempt is made to repeat an existing link connection between two parts.
    """
    pass


class LinkNameConflictError(Exception):
    """
    Raised when a link name conflict has been created between a part's outgoing links.
    This conflict is only expected to occur if the backend automatically creates an outgoing link that uses the
    name of an outgoing link that was deleted but then subsequently un-deleted sometime after the backend created the
    new link that used the deleted link's name. (When an outgoing link is deleted, its name becomes available per proto-
    type behaviour to subsequent outgoing links created by a part.
    """
    pass


@unique
class FrameStyleEnum(IntEnum):
    """
    This class represents the frame style possibilities for a Part frame.
    """
    normal = 0
    bold = 1


@unique
class DetailLevelEnum(IntEnum):
    """
    This class represents the detail level possibilities for the Part frame.
    """
    full = 0
    minimal = 1


class RestoreIfxLevelInfo:
    """
    Data needed to restore the interface level of a part frame: the original and new levels, a list of
    RestoreIfxPortInfo so the ports can be restored along the hierarchy to root actor, and links which
    had to be broken (if any) in order to decrease the ifx level.
    """

    def __init__(self, from_level: int, to_level: int):
        assert from_level != to_level
        self.from_level = from_level  # original level (the one to restore to eventually)
        self.to_level = to_level  # new level (the one to undo upon restoration)
        self.ports = {}  # type: RestoreIfxPortsInfo
        self.broken_links_in = {}  # type: PartLinksRestoreMap
        self.broken_links_out = {}  # type: PartLinksRestoreMap

    def level_increased(self) -> bool:
        """Return True if the original level was smaller than the final level"""
        return self.to_level > self.from_level

    def level_decreased(self) -> bool:
        """Return True if the original level was larger than the final level"""
        return self.to_level < self.from_level

    def merge_previous(self, previous: Decl.RestoreIfxLevelInfo):
        """
        Merge the info from a previous restoration.
        :param previous: the previous restoration
        """
        if previous.to_level >= self.to_level:
            raise NotImplementedError

        self.from_level = previous.from_level
        self.ports = previous.ports + self.ports  # order of ports matters!!
        self.broken_links_in.update(previous.broken_links_in)
        self.broken_links_out.update(previous.broken_links_out)


class PartFrame(IOriSerializable):
    """
    This class represents the frame of an Origame Scenario Part. The attributes are deliberately
    left public for easy access by the parent.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    class Signals(BridgeEmitter):
        sig_name_changed = BridgeSignal(str)  # new name
        sig_ifx_level_changed = BridgeSignal(int)  # new level
        sig_frame_style_changed = BridgeSignal(int)  # FrameStyleEnum
        sig_visible_changed = BridgeSignal(bool)  # new state
        sig_detail_level_changed = BridgeSignal(int)  # int value of the DetailLevelEnum
        sig_part_frame_size_changed = BridgeSignal(float, float)  # width, height
        sig_position_changed = BridgeSignal(float, float)  # x, y
        sig_comment_changed = BridgeSignal(str)  # new comment

        sig_incoming_link_added = BridgeSignal(PartLink)
        sig_incoming_link_removed = BridgeSignal(int, str)  # link ID, name (because name unavailable to recipient)
        sig_outgoing_link_added = BridgeSignal(PartLink)
        sig_outgoing_link_removed = BridgeSignal(int, str)  # link ID, name (because name unavailable to recipient)

        sig_link_chain_changed = BridgeSignal()

    # This number is obtained by observation, 140 is the minimum size to cover the interface bar nicely.
    DETAIL_LEVEL_MINIMIZED_LEN = 140 / 33.6

    AUTO_SCRIPTING_API = None

    # we have 0 or more PartLink children that are ORI serializable
    _ORI_HAS_CHILDREN = True

    # properties that can be edited on a frame
    __property_names_for_edit = ['pos_x', 'pos_y', 'name', 'visible', 'comment']

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: Decl.BasePart, name: str, shared_anim_mode: SharedAnimationModeReader = None):
        """
        Represent the frame for given part. The frame will have the given name. The shared animation mode
        if given is a reader of the mode. Otherwise (for testing), it can be set to either True or False,
        depending on desired animation mode.
        :param part: The Part object owning this frame
        :param name: The name of the part associated with this part frame.
        """
        IOriSerializable.__init__(self)
        self.signals = PartFrame.Signals()

        if self.AUTO_SCRIPTING_API is None:
            init_auto_scripting_api(self.__class__)

        self.__part = part  # The part this PartFrame instance belongs to
        self.__name = None
        self.__ifx_level = 0
        self.__frame_style = FrameStyleEnum.normal
        self.__visible = True
        self.__detail_level = DetailLevelEnum.full
        self.__size = None
        width, height = part.DEFAULT_VISUAL_SIZE['width'], part.DEFAULT_VISUAL_SIZE['height']
        self.__set_size(width, height)
        self.__position = Position()
        self.__comment = ""

        # For outgoing links, we use a map link.SESSION_ID -> PartLink; the Key is SESSION_ID because that is
        # the only thing that never changes; link name would be easier to deal with when getting a link by name,
        # link name can change so the bookkeeping is significantly more compllex; using SESSION_ID is simplest:
        self.__outgoing_links = {}
        self.__incoming_links = []  # A list of links pointing to this instance.

        # only used when loading ORI data (_set_from_ori_impl() and resolve_ori_link_paths())
        self.__unresolved_ori_links = []

        # use self._anim_mode_shared as boolean: "if self._anim_mode_shared:"
        self.__anim_mode_shared = True if shared_anim_mode is None else shared_anim_mode
        self.set_name(name)  # Can't set name before self._anim_mode_shared is declared.

    def get_unique_link_name(self, target_part_frame: Decl.PartFrame):
        """
        Get a unique name for a link, based on the target part frame.
        """
        unique_link_base_name = get_valid_python_name(target_part_frame.name)

        # Need to append an extra char, p for part, to the start of a link if it starts with '_'
        # otherwise jedi autocomplete flags it as a private member and hides it.
        if unique_link_base_name.startswith('_'):
            unique_link_name = 'p' + unique_link_base_name
        else:
            unique_link_name = unique_link_base_name

        unique_suffix = 1
        while self.is_link_name_taken(unique_link_name) or self.is_link_temp_name_taken(unique_link_name):
            unique_suffix += 1
            unique_link_name = unique_link_base_name + str(unique_suffix)

        return unique_link_name

    def create_link(self, target_part_frame: Decl.PartFrame,
                    link_name: str = None,
                    waypoint_positions: List[Position] = None) -> PartLink:
        """
        Creates a new PartLink instance with self as source (part) and given target frame as endpoint. If link_name is
        not given, it is assigned a default name based on the target_part_frame name and that name will be unique
        among all PartLink objects managed by this instance.

        :param target_part_frame: The part frame that the new link points to.
        :param link_name: The name of the link.
        :param waypoint_positions: A list of waypoint 'Positions' in scenario coordinates.
        :return: The newly created PartLink object if it was successfully created.
        :raises DuplicateLinkError: A similar link already exists between the parts.
        """

        if not self.__part.CAN_BE_LINK_SOURCE:
            raise RuntimeError('Invalid link creation request: {} parts cannot create links.'
                               .format(self.__part.PART_TYPE_NAME))

        if not self.__part.can_add_outgoing_link():
            raise RuntimeError("This part ({}) does not accept more links".format(self.__part))

        # Must not have a link already pointing to the specified target; or if it is and link_name is same, return.
        for link in self.__outgoing_links.values():
            if link.target_part_frame is target_part_frame:
                # Only one link allowed between this PartFrame and the target PartFrame!
                # Raise an exception to prevent the UndoStack from adding the command
                raise ValueError('Link not created: {} already linked to {}'.format(self, target_part_frame))

        PartLink.check_linkable(LinkTip(self), LinkTip(target_part_frame), raise_on_fail=True)

        # All okay. Create new link (with unique name) to the target.
        link_name = link_name or self.get_unique_link_name(target_part_frame)
        new_link = PartLink(self, to_part_frame=target_part_frame, name=link_name, shared_anim=self.__anim_mode_shared)

        self.__outgoing_links[new_link.SESSION_ID] = new_link
        self.__part.on_outgoing_link_added(new_link)
        if self.__anim_mode_shared:
            self.signals.sig_outgoing_link_added.emit(new_link)
            propagation_history = list()
            self.propagate_up_link_chain_change_signal(propagation_history)

        # Add waypoints if any
        if waypoint_positions is not None:
            for index, position in enumerate(waypoint_positions):
                new_link.add_waypoint(position, index)

        return new_link

    @prototype_compat_method
    def link(self, link_name: str, target_part_frame: Decl.PartFrame) -> PartLink:
        """
        Create a link with given name to given target frame, for use from scripts. This is the same as
        create_link() but with the order of params different, and the link name is not optional. Need for
        compatibility with Prototype.
        """
        return self.create_link(target_part_frame, link_name)

    @prototype_compat_method
    def unlink(self, link_name_or_target_frame: Either[str, Decl.PartFrame]):
        """
        Remove the link of given name (if str) or linked to given part frame (if PartFrame), for use from scripts.
        Does nothing if no link.
        """
        link = self.get_outgoing_link(link_name_or_target_frame)
        if link:
            link.remove_self()

    def is_link_name_taken(self, link_name: str) -> bool:
        """
        This function returns True if the input link name is already associated with one of the outgoing links
        managed by this instance; False otherwise.
        :param link_name: The name to search for in the list of managed links.
        :return: True if the input link name is already associated with one of the outgoing links
            managed by this instance; False otherwise.
        """
        for link in self.__outgoing_links.values():
            if link.name == link_name:
                return True

        for link in self.__unresolved_ori_links:
            if link.name == link_name:
                return True

        return False

    def is_link_temp_name_taken(self, temp_name: str) -> bool:
        """
        During editing, temporary link names are updated. This function checks if the given name is duplicated among
        the existing names.
        :param temp_name: The temp name to search for in the list of managed links.
        :return: True if the input link name is already associated with one of the outgoing links
            managed by this instance; False otherwise.
        """
        for link in self.__outgoing_links.values():
            if link.temp_name == temp_name:
                return True

        return False

    def get_outgoing_links(self) -> Iterable[PartLink]:
        """
        Get a list of outgoing links for this frame.
        """
        return self.__outgoing_links.values()

    def get_incoming_links(self) -> List[PartLink]:
        """
        Get a list of incoming links for this frame. The list must not be modified.
        """
        return self.__incoming_links

    def get_outgoing_link(self, link_name_or_target_frame: Either[str, Decl.PartFrame]) -> Optional[PartLink]:
        """
        Get the outgoing PartLink of given name, or for which target has given PartFrame. If a name is used and
        the specified name is not that of an outgoing link, None is returned.

        :param link_name_or_target_frame: The link name to search for in the list of managed links.
        :return: The corresponding PartLink object; None if a link doesn't exist with the specified name.
        :raise ValueError: if link_name_or_target_frame has unsupported type
        """
        if isinstance(link_name_or_target_frame, str):
            link_name = link_name_or_target_frame
            # search for a link by given name
            for link in self.__outgoing_links.values():
                if link_name == link.name:
                    return link

        elif isinstance(link_name_or_target_frame, PartFrame):
            target_part_frame = link_name_or_target_frame
            # search for a link that has given target part frame
            return self.get_outgoing_link_to_part(target_part_frame)

        else:
            raise ValueError(
                "PartFrame.get_outgoing_link(): first arg must be link name or a PartFrame object (it is {})"
                    .format(link_name_or_target_frame.__class__.__name__))

        return None

    def get_outgoing_link_to_part(self, part_frame: Decl.PartFrame) -> Optional[PartLink]:
        """
        Get the PartLink that connects self to the given part frame, or None if not connected to it.
        """
        for link in self.__outgoing_links.values():
            if link.target_part_frame is part_frame:
                return link

        return None

    def get_outgoing_link_by_id(self, link_id: int) -> PartLink:
        """
        Return the PartLink for given ID. This is useful to fetch the PartLink when ID received via
        sig_outgoing_link_added/removed.
        """
        return self.__outgoing_links[link_id]

    def get_unresolved_ori_links(self) -> List[PartLink]:
        """Get the set of links loaded from ORI data that have yet to have their target path resolved"""
        return self.__unresolved_ori_links

    def get_linked_parts(self) -> List[Decl.BasePart]:
        """Get a list of parts currently linked from this frame"""
        return [link.target_part_frame.part for link in self.__outgoing_links.values()]

    def is_linked(self, part_frame: Decl.PartFrame) -> bool:
        """
        Returns True if this frame has a link to the given frame, else False.
        """
        return self.get_outgoing_link_to_part(part_frame) is not None

    def outgoing_link_clutter_changed(self, target_frame: Decl.PartFrame, new_status: bool):
        """
        Notify this part frame that a link has changed its clutter flag. It will find any other links incoming
        links that have target_frame as parent and set their clutter flag to match this one.

        :param target_frame: the part frame at end of link that changed its clutter flag
        :param new_status: the new status of clutter flag
        """
        for link in self.__incoming_links:
            if link.source_part_frame is target_frame:
                link.set_declutter(new_status)
                break  # there should only be one!

    def replace_outgoing_link_by_inverted(self, link: PartLink, restorable=False) -> Tuple[PartLink, RestoreLinkInfo]:
        """
        Replace an outgoing link by one that is in opposite direction, with same properties (declutter, bold etc).

        :param link: the link to replace
        :param restorable: if the operation can be undone (True) or is final (False)
        :return: a pair consisting of the new link which is now incoming to this frame, and (if restorable was True),
            the restoration info to give to restore_outgoing_link() when undo the replacement
        """
        if link not in self.__outgoing_links.values():
            raise ValueError("Link {} cannot be inverted: it is not an outgoing link of {}", link, self.__part)

        if link.waypoints:
            raise NotImplementedError("Need to implement reversing the order of waypoints")

        parent_frame = link.target_part_frame
        link_name = link.name
        link_id = str(link)
        restore_info = self.remove_outgoing_link(link, restorable)
        new_link = parent_frame.create_link(self, link_name=link_name)
        assert link not in self.__outgoing_links.values()
        assert new_link in self.__incoming_links
        new_link.bold, new_link.declutter, new_link.visible = link.bold, link.declutter, link.visible

        log.warning("Replaced link {} by inverted link (#{})", link_id, new_link.SESSION_ID)
        return new_link, restore_info

    def remove_incoming_links(self, restorable: bool = False, links: List[PartLink] = None) -> PartLinksRestoreMap:
        """
        Delete incoming links. Detaches them from their source.

        :param restorable: True if the delete operation is to be restorable (undoable via restore_incoming_links);
            False otherwise.
        :param links: subset of incoming links to remove; if None, remove all incoming links; otherwise,
            only links with target=self are removed (others are ignored)
        :returns: None if restorable=False; otherwise, a dict (mapping deleted PartLink objects to their
            RestoreLinkInfo) that can be given to restore_incoming_links.
        """
        restore_links_info = {}

        if links is None:
            links = self.__incoming_links.copy()
        for link in links:
            if link.target_part_frame is not self:
                continue
            restore_link_info = link.remove_self(restorable=restorable)
            if restorable:
                restore_links_info[link] = restore_link_info

        assert set(self.__incoming_links).intersection(links) == set([])
        if restorable:
            return restore_links_info
        else:
            return None

    def remove_outgoing_links(self, restorable: bool = False, links: List[PartLink] = None) -> PartLinksRestoreMap:
        """
        Remove outgoing links.

        :param restorable: True if the delete operation is to be restorable (undoable); False otherwise.
        :param links: subset of outgoing links to remove; only links with source=self are removed, others are ignored
        :returns: None if restorable=False; otherwise, a dict mapping deleted PartLink objects to RestoreLinkInfo
            objects that contain info sufficient for restoring the deleted links.
        """
        restore_links_info = {}
        clear_all = False
        if links is None:
            links = self.__outgoing_links.values()
            clear_all = True

        for link in links:
            if link.source_part_frame is not self:
                continue
            link_name = str(link)
            restore_link_info = link.remove_by_source(restorable=restorable)
            self.__part.on_outgoing_link_removed(link)
            if self.__anim_mode_shared:
                self.signals.sig_outgoing_link_removed.emit(link.SESSION_ID, link_name)
                propagation_history = list()
                self.propagate_up_link_chain_change_signal(propagation_history)
            if restorable:
                restore_links_info[link] = restore_link_info

        if clear_all:
            self.__outgoing_links.clear()
        else:
            for link in links:
                del self.__outgoing_links[link.SESSION_ID]

        if restorable:
            return restore_links_info
        else:
            return None

    def remove_outgoing_link(self, outgoing_link: PartLink, restorable=False) -> Dict[type, RestoreLinkInfo]:
        """
        Delete given outgong PartLink, and return (if restorable=True), the restoration info. Does nothing if
        PartLink does not belong to self.
        NOTE: This function was designed to be called by the PartLink's delete method in order
        to achieve a complete cleanup of references from link to frame and vice-versa.

        :param outgoing_link: The link held by this instance, that is to be detached.
        :param restorable: False if the deletion is final, True if it may be restored later
        """
        for link in self.__outgoing_links.values():
            if link is outgoing_link:
                link_name = str(link)
                restore_link_info = link.remove_by_source(restorable=restorable)
                del self.__outgoing_links[link.SESSION_ID]
                self.__part.on_outgoing_link_removed(link)
                if self.__anim_mode_shared:
                    self.signals.sig_outgoing_link_removed.emit(link.SESSION_ID, link_name)
                    propagation_history = list()
                    self.propagate_up_link_chain_change_signal(propagation_history)
                return restore_link_info

        return None

    def restore_outgoing_link(self, link: PartLink, link_restore_info: RestoreLinkInfo,
                              waypoint_offset: Vector = None):
        """
        Restore the outgoing links previously deleted from this part.

        :param link_restore_info: the restoration information for restoring the associated link
            to its original state.
        :param waypoint_offset: an x,y offset for the link waypoints (e.g. paste operation at new position)
        :raises InvalidLinkError: if linkage not possible (see exception class doc)

        If a waypoint_offset is given, it is assumed that this is an "impure" restore, i.e. a result of
        moving a part to a different actor. In this case, a new link is created, with waypoints that are
        the original waypoints shifted by waypoint_offset.
        """
        info = link_restore_info
        assert info.source_frame is self
        PartLink.check_linkable(LinkTip(info.source_frame), LinkTip(info.target_frame), raise_on_fail=True)
        if waypoint_offset:
            moved_waypoints = link.moved_waypoints(waypoint_offset)
            link = PartLink(None, waypoints=moved_waypoints, copy_unattached=link)
        self.__outgoing_links[link.SESSION_ID] = link
        # the restore_by_source will signal existence of link to observers of target, so must come last:
        link.restore_by_source(link_info=info)

        self.__part.on_outgoing_link_added(link)
        if self.__anim_mode_shared:
            self.signals.sig_outgoing_link_added.emit(link)
            propagation_history = list()
            self.propagate_up_link_chain_change_signal(propagation_history)

    def restore_outgoing_links(self, links_restore_info: PartLinksRestoreMap,
                               waypoint_offset: Vector = None,
                               no_waypoints: List[Decl.BasePart] = None) -> PartLinksRestoreMap:
        """
        This function restores the outgoing links previously deleted from this instance.

        :param links_restore_info: A dict mapping PartLink objects to RestoreLinkInfo objects. The latter
            contains sufficient restore_info for restoring the associated link to its original state.
        :param waypoint_offset: an x,y offset for the link waypoints
        :param no_waypoints: parts for which links FROM self should be restored without waypoints
        :return: mapping of dropped PartLink objects to their restoration restore_info; these are links that
            would be invalid once restored (because ifx levels on source and/or target are insufficient).

        When any of the optional parameters are given, the restoration is "impure" i.e. it is assumed
        to be the result of a move of self.part (or any ancestor) to another actor. In such case, two things
        happen: 1. links TO parts in no_waypoints get re-created (instead of restored) without waypoints;
        2. links to other parts get re-created (instead of restored) with the original waypoints shifted
        by waypoint_offset.
        """
        if no_waypoints:
            def target_in_restored(restore_info: RestoreLinkInfo) -> bool:
                _, target = PartLink.get_ifx_parts(restore_info.source_frame, restore_info.target_frame)
                return target not in no_waypoints

            no_wp_links = {link for link, restore_info in links_restore_info.items()
                           if target_in_restored(restore_info)}
        else:
            no_wp_links = []

        return self.__restore_links(links_restore_info, waypoint_offset, no_wp_links)

    def restore_incoming_links(self, links_restore_info: PartLinksRestoreMap,
                               waypoint_offset: Vector = None,
                               no_waypoints: List[Decl.BasePart] = None) -> PartLinksRestoreMap:
        """
        This function restores the outgoing links previously deleted from this instance.

        :param links_restore_info: A dict mapping PartLink objects to RestoreLinkInfo objects. The latter
            contains sufficient restore_info for restoring the associated link to its original state.
        :param waypoint_offset: an x,y offset for the link waypoints
        :param no_waypoints: parts for which links TO self should be restored without waypoints
        :return: mapping of dropped PartLink objects to their restoration restore_info; these are links that
            would be invalid once restored (because ifx levels on source and/or target are insufficient).

        When any of the optional parameters are given, the restoration is "impure" i.e. it is assumed
        to be the result of a move of self.part (or any ancestor) to another actor. In such case, two things
        happen: 1. links FROM parts in no_waypoints get re-created (instead of restored) without waypoints;
        2. links to other parts get re-created (instead of restored) with the original waypoints shifted
        by waypoint_offset.
        """
        if no_waypoints:
            def source_in_restored(restore_info: RestoreLinkInfo) -> bool:
                source, _ = PartLink.get_ifx_parts(restore_info.source_frame, restore_info.target_frame)
                return source not in no_waypoints

            no_wp_links = {link for link, restore_info in links_restore_info.items()
                           if source_in_restored(restore_info)}
        else:
            no_wp_links = []

        return self.__restore_links(links_restore_info, waypoint_offset, no_wp_links)

    def get_part(self) -> Decl.BasePart:
        """
        Get the part the frame belongs to.
        """
        return self.__part

    def get_name(self) -> str:
        """
        Get the name of the part.
        """
        return self.__name

    def set_name(self, value: str):
        """
        Set the name of the part.
        :param value: New part name.
        :raises InvalidPythonNameError: Raised by validate_python_name() if the input value is not a valid Python name.
        """
        # validate_python_name(value)
        if self.__name != value:
            self.__name = value
            if self.__anim_mode_shared:
                self.signals.sig_name_changed.emit(self.__name)
            self.__part.on_frame_name_changed()

    def get_highest_ifx_actor(self) -> Decl.ActorPart:
        """
        Get the "highest" actor on which this part frame is exposed
        """
        part_path = self.__part.get_parts_path(with_root=True)
        return part_path[self.__ifx_level]

    def get_ifx_level(self) -> int:
        """Get the interface level for this part frame"""
        return self.__ifx_level

    def set_ifx_level(self, new_level: int, break_bad: bool = False,
                      restorable: bool = False) -> Either[RestoreIfxLevelInfo, List[PartLink]]:
        """
        Set the ifx (interface) new_level of this part frame.

        :param new_level: new new_level of interface; the actual level will be set to the maximum allowed (i.e. enough
            to be exposed on root actor, i.e. 1 for a child of root part)
        :param break_bad: True removes links that are invalid with new new_level; False to raise exception if any link
            would be invalidated
        :param restorable: True to be able to restore the ifx setting and corresponding deleted links to current new_level

        :return: if break_bad=False, returns []; else, returns the list of removed links if restorable = False, or
            an instance of RestoreIfxLevelInfo if restorable = True

        :except ValueError: if break_bad=False and some links would be invalidated; the exception contains the minimum
            ifx new_level allowed at time of this call
        """
        max_ifx_level = self.get_max_ifx_level()
        if new_level > max_ifx_level:
            log.warning('Part {} interface level setting to max={} (requested was {})', self, max_ifx_level, new_level)
            new_level = max_ifx_level

        if self.__ifx_level == new_level:
            return None if restorable else []

        old_level = self.__ifx_level

        # handle notification of ancestors, and possibly breaking links that are now invalid
        result = RestoreIfxLevelInfo(old_level, new_level) if restorable else []
        if new_level < old_level:
            assert result == [] or result.level_decreased()
            invalid_links = self.get_invalid_links(ifx_level=new_level)
            if invalid_links:
                if break_bad:
                    restore_out = self.remove_outgoing_links(restorable=restorable, links=invalid_links.outgoing)
                    restore_in = self.remove_incoming_links(restorable=restorable, links=invalid_links.incoming)
                    if restorable:
                        result.broken_links_out = restore_out
                        result.broken_links_in = restore_in
                    else:
                        result = invalid_links.get_all()
                else:
                    self.__ifx_level = old_level
                    msg = 'Interface new_level must be at least {}, following links would become invalid: {}'
                    raise ValueError(msg.format(self.get_min_ifx_level(), invalid_links.get_all()))

            # only need to notify levels *above* the new level:
            if restorable:
                self.__part.parent_actor_part._remove_ifx_ports(self, new_level + 1, old_level,
                                                                restoration=result.ports)
            else:
                self.__part.parent_actor_part._remove_ifx_ports(self, new_level + 1, old_level)

        else:
            # when increasing level, there is no additional restoration info, but need to add ifx ports on actor chain
            assert result == [] or result.level_increased()
            # only need to notify levels *above* the old level:
            self.__part.parent_actor_part._add_ifx_port(self, old_level + 1, new_level)

        self.__ifx_level = new_level
        self.signals.sig_ifx_level_changed.emit(self.__ifx_level)

        return result

    def set_ifx_boundary(self, actor: Decl.ActorPart,
                         restorable: bool = False) -> Either[RestoreIfxLevelInfo, List[PartLink]]:
        """
        Set the interface level to be such that actor is the boundary actor of this frame.
        :param actor: part which should become the boundary actor of the frame
        :param restorable: True if should be a restorable operation
        :return: a list of links deleted if restorable=False, else a RestoreIfxLevelInfo
        """
        level = 0
        for parent in self.__part.iter_parents():
            if parent is actor:
                break
            else:
                level += 1
        else:
            raise ValueError("Actor {} is not an ancestor of part {}".format(actor, self.__part))

        return self.set_ifx_level(level, restorable=restorable, break_bad=True)

    def restore_ifx_level(self, restore_info: RestoreIfxLevelInfo, links: bool = True):
        """
        Restore the interface level to the level prior to last set_ifx_level().
        :param restore_info: the restoration info received from set_ifx_level()
        :param links: True if links should be restored too; set to False if links will be restored separately
        """
        # first set the ifx level so that ports can be restored to the appropriate level; however, this
        # ifx level restoration might be in support of a reparenting, in which case the ifx level may
        # not be restorable to full level (could even be 0)
        max_ifx_level = self.get_max_ifx_level()
        self.__ifx_level = min(restore_info.from_level, max_ifx_level)

        parent_part = self.__part.parent_actor_part
        assert parent_part is not None

        if restore_info.level_decreased():
            # restoring causes increase in ifx level back to original: from_level (in restore_info) is
            # higher than to_level, and ports and any broken links need to be restored
            assert restore_info.to_level + 1 <= restore_info.from_level
            parent_part._restore_ifx_ports(self, restore_info.ports,
                                           from_to=(restore_info.to_level + 1, self.__ifx_level))

            if links:
                if restore_info.broken_links_out:
                    self.restore_outgoing_links(restore_info.broken_links_out)
                if restore_info.broken_links_in:
                    self.restore_incoming_links(restore_info.broken_links_in)

        else:
            # if level was increased, then restoring decreases ifx level, so remove interface ports above original
            # (from_level + 1) up to (the larger) to_level; the original state was a lower ifx level, so there are
            # no links to restore
            assert self.get_invalid_links() == LinkSet()
            assert restore_info.from_level + 1 <= restore_info.to_level
            assert restore_info.from_level == self.__ifx_level
            parent_part._remove_ifx_ports(self, restore_info.from_level + 1, restore_info.to_level)

        self.signals.sig_ifx_level_changed.emit(self.__ifx_level)

    def get_num_elev_links_incoming(self) -> int:
        """
        Calculates the total number of incoming elevated interface links.
        Caution: it is more expensive than usual getters.
        :return: The number of the incoming interface links.
        """
        return sum(1 for link in self.__incoming_links if link.has_elevated_target())

    def get_num_elev_links_outgoing(self) -> int:
        """
        Calculates the total number of outgoing elevated interface links.
        Caution: it is more expensive than usual getters.
        :return: The number of the outgoing interface links.
        """
        return sum(1 for link in self.__outgoing_links.values() if link.has_elevated_source())

    def get_min_ifx_level(self) -> int:
        """
        Get the smallest interface level for this part frame; smaller interface levels would invalidate one
        ore more links. This changes based on current links (in and out) and the locations of target part
        frames in scenario relative to this part frame.
        """
        path = self.__part.get_parts_path(with_root=False, with_part=False)
        remote_links = [link for link in self.__outgoing_links.values() if link.is_elevated()]
        count_hops = 0
        min_level = 0  # if no links, can be as small as desired
        max_level = max(self.get_max_ifx_level() - 1, 0)  # - 1 because min can never be exposure on root actor
        for link in remote_links:
            level = max_level
            link_target_path = link.target_part_frame.part.get_parts_path(with_root=False, with_part=False)
            for source_path_part, target_path_part in zip(path, link_target_path):
                count_hops += 1
                if source_path_part is not target_path_part:
                    if level > min_level:
                        min_level = level
                    break
                level -= 1
            else:
                assert not path or not link_target_path
                min_level = max_level

            if min_level >= max_level:
                break

        return min_level

    def get_max_ifx_level(self) -> int:
        """
        Returns the largest interface level setting for this part frame; larger values would go above the root
        actor of the scenario. This changes based on the hierarchical location of part frame in scenario.
        """
        return len(self.__part.get_parts_path(with_root=True, with_part=False))

    def get_invalid_links(self, ifx_level: int = None, when_parent: Decl.ActorPart = None) -> LinkSet:
        """
        Get invalid links of this frame.
        :param ifx_level: the interface level to assume; by default, will use the current level
        :param when_parent: the actor to assume as parent; by default, will use current parent
        :returns: a pair, first is list of invalid outgoing links, second is list of invalid incoming links
        """
        invalid = LinkSet()
        source_tip = LinkTip(self, ifx_level=ifx_level)

        for link in self.__outgoing_links.values():
            if not PartLink.check_linkable(source_tip, LinkTip(link.target_part_frame)):
                invalid.outgoing.append(link)

        for link in self.__incoming_links:
            if not PartLink.check_linkable(source_tip, LinkTip(link.source_part_frame)):
                invalid.incoming.append(link)

        return invalid

    def get_ifx_boundary_actor(self, ifx_level: int = None, when_parent: Decl.ActorPart = None) -> Decl.ActorPart:
        """
        Get the actor that defines the interface boundary of this part frame. This part frame is not visible (linkable)
        from outside of the returned actor (hence the name "boundary").

        :param ifx_level: the interface level to assume; if None, use the current level
        :param when_parent: the actor to assume as parent; by default, use current parent
        :return: actor that is ifx_level+1 levels up from this part; if current ifx_level is 0, this is parent actor
            (or when_parent, if not None); if self is part_frame of root actor, returns None
        """
        parent = self.__part.parent_actor_part if when_parent is None else when_parent
        if ifx_level is None:
            ifx_level = self.__ifx_level
        for level in range(ifx_level):
            parent = parent.parent_actor_part
        return parent

    def get_ifx_level_ancestor(self, actor: Decl.ActorPart) -> int:
        """Get the ifx level that would be required for a part to have an ifx port on the given actor."""
        for count, parent in enumerate(self.__part.iter_parents()):
            if parent is actor:
                return count + 1

        raise ValueError("Actor {} is not an ancestor of {}".format(actor, self.__part))

    def get_frame_style(self) -> FrameStyleEnum:
        """
        Get the frame style indicator.
        """
        return self.__frame_style

    def set_frame_style(self, value: FrameStyleEnum):
        """
        Set the frame style.
        :param value: New frame style.
        """
        if self.__frame_style != value:
            self.__frame_style = FrameStyleEnum(value)
            if self.__anim_mode_shared:
                self.signals.sig_frame_style_changed.emit(self.__frame_style.value)

    def get_is_framed(self) -> bool:
        """
        Get the framed property.
        """
        return self.__part.SHOW_FRAME

    def get_visible(self) -> bool:
        """
        Get the visible property.
        """
        return self.__visible

    def set_visible(self, value: bool):
        """
        Set the visible property.
        :param value:  New visible property.
        """
        if self.__visible != value:
            self.__visible = value
            if self.__anim_mode_shared:
                self.signals.sig_visible_changed.emit(self.__visible)

    def get_detail_level(self) -> DetailLevelEnum:
        """
        Get the detail level property (minimal or full). Note: the return value has taken the override into
        consideration.
        """
        return self.__detail_level

    def set_detail_level(self, value: DetailLevelEnum):
        """
        Set the detail level property (minimal or full)
        :param value: New detail level
        """
        if self.__detail_level != value:
            self.__detail_level = value

            if self.__anim_mode_shared:
                self.signals.sig_detail_level_changed.emit(value)

    def get_size(self) -> Size:
        """
        Returns a size based on get_width() and get_height(). See get_width() and get_height()
        """
        return Size(self.get_width(), self.get_height(), scale_3d=self.get_scale_3d())

    def get_width(self) -> float:
        """
        Get the width of this frame, in scenario units.

        :return The regular (i.e., at the full detail level) width of the frame.
        """
        return self.__size.width

    def get_height(self) -> float:
        """
        Get the height of this frame, in scenario units. Height including the frame header.

        :return The regular (i.e., "full detail") height (including the height of the header) of the frame.
        """
        return self.__size.height

    def get_min_width(self) -> float:
        """Get the minimum width that instances of this class can have as frame content of a PartFrame"""
        return self.__part.MIN_CONTENT_SIZE['width']

    def get_min_height(self) -> float:
        """Get the minimum height that instances of this class can have as frame content of a PartFrame"""
        return self.__part.MIN_CONTENT_SIZE['height']

    def set_size(self, width: float, height: float, scale_3d: float = None):
        """
        Set the size of this frame. The height must not include the frame header, i.e. it is the height of the
        body portion of the frame; frame header height is automatically added, so the size from get_size() will
        include the frame height.

        Note: if size is smaller than minimum of part, the size is set to minimum.
        Note: if size changes, emits sig_part_frame_size_changed and notifies part that size has changed.
        """
        orig_width, orig_height, orig_scale_3d = self.__size.width, self.__size.height, self.__size.scale_3d
        self.__set_size(width, height, scale_3d)
        if (orig_width, orig_height, orig_scale_3d) != (self.__size.width, self.__size.height, self.__size.scale_3d):
            self.__part._on_frame_size_changed()
            if self.__anim_mode_shared:
                self.signals.sig_part_frame_size_changed.emit(self.get_width(), self.get_height())

    def set_height(self, height: float):
        """
        Set the height. Does nothing if height is smaller than the part`s minimum. Height is that of body portion of
        frame; the frame header height will be added automatically, and will be included in the return value from
        get_height().
        :param height: New height value.
        """
        self.set_size(self.__size.width, height)

    def set_width(self, width: float):
        """
        Set the width.
        :param width: New width value.
        """
        self.set_size(width, self.__size.height)

    def get_scale_3d(self) -> float:
        """Get the 3d scale of this frame, in scenario units (shortcut for self.get_size().scale_3d)."""
        return self.__size.scale_3d

    def set_scale_3d(self, value: float):
        """
        Set the scale_3d.
        :param value: New scale_3d property.
        """
        self.set_size(self.__size.width, self.__size.height, scale_3d=value)

    def get_pos_x(self) -> float:
        """Get the x position of the frame, in global scenario coordinates"""
        return self.__position.x

    def get_pos_y(self) -> float:
        """Get the y position of the frame, in global scenario coordinates"""
        return self.__position.y

    def set_pos_x(self, x: float):
        """Set the x position of the frame, in global scenario coordinates"""
        if x != self.__position.x:
            self.__position = Position(x, self.__position.y)
            if self.__anim_mode_shared:
                self.signals.sig_position_changed.emit(*self.__position.to_tuple())
            self.__part._on_frame_position_changed()

    def set_pos_y(self, y: float):
        """Set the y position of the frame, in global scenario coordinates"""
        if y != self.__position.y:
            self.__position = Position(self.__position.x, y)
            if self.__anim_mode_shared:
                self.signals.sig_position_changed.emit(*self.__position.to_tuple())
            self.__part._on_frame_position_changed()

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
            self.__part._on_frame_position_changed()

    def get_pos_vec(self) -> Position:
        """Get the frame's position as a vector"""
        return self.__position

    def set_pos_from_vec(self, pos: Position):
        """Set the frame's position from a vector"""
        self.__position = pos

    def get_comment(self) -> str:
        """
        Get the comment.
        """
        return self.__comment

    def set_comment(self, value: str):
        """
        Set the comment
        :param value:  New comment.
        """
        if self.__comment != value:
            self.__comment = value
            if self.__anim_mode_shared:
                self.signals.sig_comment_changed.emit(self.__comment)

    def get_anim_mode(self) -> bool:
        """
        Get the current animation mode for this part. When True, this frame emits signals when state changes.
        """
        return bool(self.__anim_mode_shared)

    def get_matching_properties(self, re_pattern: str) -> List[str]:
        """
        Get the names of all properties of this frame that have a string representation that matches a pattern (case insensitive).

        :param re_pattern: the regular expression pattern to match on

        Example: self.get_matching_properties('hel.*') will return ['comment', 'name'] if comment is 'hello'
            and name is 'hell'
        """
        regexp = re.compile(re.escape(re_pattern), re.IGNORECASE)
        matches = []

        # local properties
        for prop_name in self.__property_names_for_edit:
            prop_val_as_str = str(getattr(self, prop_name))
            if regexp.search(prop_val_as_str):
                matches.append(prop_name)

        # outgoing links:
        for out_link in self.__outgoing_links.values():
            if regexp.search(out_link.name):
                matches.append('outgoing_links[{}]'.format(out_link.name))

        return matches

    def propagate_up_link_chain_change_signal(self, propagation_history: List[int]):
        """
        This function is called if the outgoing links of this part frame are added, removed, their
        names are changed, or they are re-targeted. If it is called already (by checking the propagation_history),
        it will be skipped.

        This function emits the sig_link_chain_changed, then calls this function of the part frames
        of the incoming links. In other words, it propagates the outgoing link changes to the incoming
        part frames.

        :param propagation_history: history of part session ID traversed so far (to prevent infinite cycles)
        """
        if self.__anim_mode_shared:
            self.signals.sig_link_chain_changed.emit()

            if self.__part.SESSION_ID in propagation_history:
                return
            else:
                propagation_history.append(self.__part.SESSION_ID)

            for link in self.__incoming_links:
                link.source_part_frame.propagate_up_link_chain_change_signal(propagation_history)

    def on_outgoing_link_renamed(self, old_name: str, new_name: str):
        """Get notified when link has been renamed"""
        self.__part.on_outgoing_link_renamed(old_name, new_name)
        if self.__anim_mode_shared:
            propagation_history = list()
            self.propagate_up_link_chain_change_signal(propagation_history)

    def resolve_ori_link_paths(self, parent_actor_part: Decl.ActorPart,
                               refs_map: Dict[int, Decl.BasePart],
                               drop_dangling: bool,
                               pos_offset: Tuple[float, float] = None,
                               moved_parts: List[Decl.BasePart] = ()):
        """
        This function iterates over the list of unresolved ORI links. These links exist in an incomplete state:
        the do not yet refer to source and target parts. Rather, they either have two relative path strings
        that will be followed to reach an existing part, or they have two references that will be resolved
        to a part using the provided refs_map. Once the link endpoints are resolved, the link is added to the
        frame's list of outgoing links.

        NOTE: Link paths must only be resolved once the full scenario hierarchy to which this instance belongs
        has been created in memory. That is to say, this function must only be called by an ancestor Actor Part's
        set_from_ori() function.

        :param parent_actor_part: The parent Actor Part in which this part frame instance (and part) resides.
        :param refs_map: map of part ID to BasePart objects for purpose of link target path resolution
        :param drop_dangling: if True, any links that fail to resolve to another part will be removed
        :param pos_offset: offset for outgoing links from moved_parts, or None if no offset
        :param moved_parts: if offset given, this must contain a list of parts that were moved;
            if this frame or its elevated source is one of those parts, the waypoints will be moved

        :raise: UnresolvedPartRefError if part ref cannot be resolved from given refs_map, and drop_dangling=False
        :raise: UnresolvedLinkPathError if link path cannot be resolved, and drop_dangling=False
        """
        ori_undef_links = self.__unresolved_ori_links
        self.__unresolved_ori_links = []
        self_moved = (self.__part in moved_parts)
        for link in ori_undef_links:
            if link.target_needs_resolving():
                try:
                    link.resolve_path(parent_actor_part, refs_map)

                    # if the source ifx part for the link has moved in space, move its waypoints
                    src_ifx, _ = PartLink.get_ifx_parts(link.source_part_frame, link.target_part_frame)
                    if src_ifx in moved_parts:
                        link.move_waypoints(pos_offset)

                    self.__outgoing_links[link.SESSION_ID] = link
                    self.__part.on_outgoing_link_added(link)
                    if self.__anim_mode_shared:
                        self.signals.sig_outgoing_link_added.emit(link)
                        propagation_history = list()
                        self.propagate_up_link_chain_change_signal(propagation_history)

                except (UnresolvedPartRefError, UnresolvedLinkPathError) as exc:
                    log.warning("Dropping link: {}", exc)
                    if not drop_dangling:
                        log.warning("Aborting ORI link target resolution on {}", self)
                        assert self.__unresolved_ori_links == []
                        raise

    def attach_incoming_link(self, link: PartLink):
        """
        This function informs this instance that a link is pointing to it. This frame keeps track of incoming links.
        It also changes the incoming link's declutter flag to match that of an existing outgoing link.
        :param link: A link pointing to this instance.
        """
        PartLink.check_linkable(LinkTip(link.source_part_frame), LinkTip(self), raise_on_fail=True)
        assert link not in self.__incoming_links
        self.__incoming_links.append(link)

        if self.__anim_mode_shared:
            self.signals.sig_incoming_link_added.emit(link)

    def detach_incoming_link(self, incoming_link: PartLink):
        """
        Remove the given PartLink from this instance's list of incoming links. Assumes the caller detaches
        the PartLink from its target (self) *after* this call.
        NOTE: This function was designed to be called by the PartLink's delete method in order
        to achieve a complete cleanup of references from frame to link and vice-versa.
        :param incoming_link: A PartLink that points to this frame, but is in the process of being deleted.
        """
        for link in self.__incoming_links:
            if link is incoming_link:
                self.__incoming_links.remove(link)
                if self.__anim_mode_shared:
                    assert link.source_part_frame is not None
                    assert link.target_part_frame is not None
                    self.signals.sig_incoming_link_removed.emit(link.SESSION_ID, str(link))
                return

    def __dir__(self):
        return self.AUTO_SCRIPTING_API

    def __str__(self):
        return '{} FRAME'.format(self.__part)

    # --------------------------- instance PUBLIC properties ----------------------------

    name = property(get_name, set_name)
    ifx_level = property(get_ifx_level, set_ifx_level)
    part = property(get_part)
    frame_style = property(get_frame_style, set_frame_style)
    visible = property(get_visible, set_visible)
    detail_level = property(get_detail_level, set_detail_level)
    position = property(get_position)
    pos_x = property(get_pos_x, set_pos_x)
    pos_y = property(get_pos_y, set_pos_y)
    size = property(get_size)
    width = property(get_width)
    height = property(get_height)
    scale_3d = property(get_scale_3d)
    comment = property(get_comment, set_comment)
    anim_mode = property(get_anim_mode)
    outgoing_links = property(get_outgoing_links)
    incoming_links = property(get_incoming_links)
    is_framed = property(get_is_framed)

    # prototype compatibility:
    PosX = prototype_compat_property_alias(pos_x, 'PosX')
    PosY = prototype_compat_property_alias(pos_y, 'PosY')

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_SCRIPTING_API_EXTEND = (
        name, get_name, set_name,
        ifx_level, get_ifx_level, set_ifx_level,
        frame_style, get_frame_style, set_frame_style,
        detail_level, get_detail_level, set_detail_level,
        position, get_position,
        pos_x, get_pos_x, set_pos_x,
        pos_y, get_pos_y, set_pos_y,
        size, get_size,
        width, get_width,
        height, get_height,
        comment, get_comment, set_comment,
        outgoing_links, get_outgoing_links,
        incoming_links, get_incoming_links,
    )

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, max_ifx_level: int = None, **kwargs):
        """
        Beyond the base class method, params are:
        :param max_ifx_level: the maximum value for the interface level, or None if no limit (in practice, the
            limit is the distance from the root actor)

        :raises InvalidPythonNameError: Raised if an invalid part name is detected.
        """
        assert ori_data

        if ori_data.get(PfKeys.NAME):
            try:
                self.set_name(ori_data[PfKeys.NAME])
            except InvalidPythonNameError as exc:
                log.error("Invalid part name loaded from scenario file. Name:{}, Scenario location:{}, Error:{}, "
                          "Propose renaming to:{}", ori_data[PfKeys.NAME], self.__part.path, exc, exc.proposed_name)
                err = "Invalid part name loaded from scenario file. Error: {}".format(exc)
                raise InvalidPythonNameError(msg=err, invalid_name=exc.invalid_name,
                                             proposed_name=exc.proposed_name, scenario_location=self.__part.path)

        # ifx level will be 0 if not set in ORI
        DEFAULT_IFX_LEVEL = 0
        ori_ifx_level = ori_data.get(PfKeys.IFX_LEVEL, DEFAULT_IFX_LEVEL)
        # but it must not be larger than max_ifx_level if max was given:
        if max_ifx_level is not None and ori_ifx_level > max_ifx_level:
            log.warning("Capping ifx level of {} at {} (from {})", self, max_ifx_level, ori_ifx_level)
            ori_ifx_level = max_ifx_level
        self.set_ifx_level(ori_ifx_level)  # creates ports at higher levels

        self.__frame_style = FrameStyleEnum[ori_data[PfKeys.FRAME_STYLE].lower()]
        self.__visible = bool(ori_data[PfKeys.VISIBLE])

        # Deal with the backward compatibility.
        # 'content_presentation' is deprecated.
        # 'icon' is deprecated.
        if 'content_presentation' in ori_data:
            detail_level_from_disk = ori_data['content_presentation']
        else:
            detail_level_from_disk = ori_data[PfKeys.DETAIL_LEVEL]

        detail_level_value = detail_level_from_disk.lower()
        if detail_level_value == 'icon':
            self.__detail_level = DetailLevelEnum.minimal
        else:
            self.__detail_level = DetailLevelEnum[detail_level_value]

        if self.__part.RESIZABLE_FRAME:
            size = ori_data[PfKeys.SIZE]
            width = size[SzKeys.WIDTH]
            height = size[SzKeys.HEIGHT]
            if ori_data.schema_version <= OriSchemaEnum.prototype:
                # The prototype specification of "height" does not include the header frame, but Origame spec does.
                # So, we add the compensation "2" when the schema is prototype.
                height += 2
            elif ori_data.schema_version < OriSchemaEnum.version_2_1:
                # Origame schema from 0 to 2.1 deals with the height differently. The 1.13 maintains the aspect ratio.
                # For example, a square button part will be displayed as a square before and after 2.1
                height += 1.13

            self.__set_size(width, height)

        x = ori_data[PfKeys.POSITION][PosKeys.X]
        y = ori_data[PfKeys.POSITION][PosKeys.Y]
        self.__position = Position(x, y)
        self.__part._on_frame_position_changed()
        self.__part._on_frame_size_changed()

        self.__comment = ori_data.get(PfKeys.COMMENT, '') or ''  # some old scenarios have None comment

        # Build a TEMPORARY list of PartLink objects that don't have their target resolved to an actual PartFrame yet:
        # they will get resolved to a PartFrame later by parent ActorPart once all parts have been instantiated
        outgoing_links = ori_data.get_sub_ori(PfKeys.OUTGOING_LINKS, default={})
        if not outgoing_links:
            outgoing_links = ori_data.get_sub_ori(PfKeys.OUTGOING_LINKS_ALIAS, default={})

        # Legacy scenario links from parts that can't create links: allow outgoing links from parts that can't create
        # links to be loaded, but warn about the limitation.
        if outgoing_links and not self.__part.CAN_BE_LINK_SOURCE:
            log.warning('Links from parts of type {} are no longer supported. They will be instantiated for part {} '
                        'for backwards compatibility.', self.__part.PART_TYPE_NAME, self.__part)

        for link in self.__outgoing_links.values():
            self.__part.on_outgoing_link_removed(link)
        # Will get deleted in self.resolve_ori_link_paths() when called by parent:
        self.__unresolved_ori_links = self.__build_links_from(outgoing_links)

        return self

    def __build_links_from(self, ori_links_def: OriScenData) -> List[PartLink]:
        """
        This function creates PartLink objects from the given .ORI data structure (describing the links associated
        with the current part frame) and returns a dictionary that maps link session ID to those PartLink objects.
        :raises InvalidPythonNameError: Raised by validate_python_name() if the link name is not a valid Python name.
        """
        part_links = []
        link_names = set()

        if ori_links_def is None:
            return part_links

        for link_name, ori_link_def in ori_links_def.iter_sub_ori():
            try:
                validate_python_name(link_name)

            except InvalidPythonNameError as exc:
                log.error("Invalid link name loaded from scenario file. Name:{}, Scenario location:{}, Error:{}, \
                    Propose renaming to:{}", link_name, self.part.path, exc, exc.proposed_name)
                err = "Invalid link name loaded from scenario file.\rError: {}".format(exc)
                raise InvalidPythonNameError(msg=err, invalid_name=exc.invalid_name,
                                             proposed_name=exc.proposed_name, scenario_location=self.part.path)

            if link_name in link_names:
                raise KeyError(
                    "Duplicate link names associated with PartFrame instance. PartFrame: " + self.__name +
                    " link name: " + link_name)

            part_link = PartLink(self, name=link_name, shared_anim=self.__anim_mode_shared)
            part_link.set_from_ori(ori_link_def)
            part_links.append(part_link)
            link_names.add(link_name)

        return part_links

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = self.__get_ori_def_local()

        ori_links = {}
        ori_def[PfKeys.OUTGOING_LINKS] = ori_links

        # if context in (OriContextEnum.save_load, OriContextEnum.export, OriContextEnum.copy):
        for link in self.__outgoing_links.values():
            ori_links[link.name] = link.get_ori_def(**kwargs)

        return ori_def

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update(
            self.__get_ori_def_local(),
            outgoing_links_names=set(link.name for link in self.__outgoing_links.values()),
        )

    @override(IOriSerializable)
    def _has_ori_changes_children(self) -> bool:
        # we got this far so no local changes, and same # links;
        # but maybe some links have changed, or some links replaced by new:
        for link in self.__outgoing_links.values():
            if link.has_ori_changes():  # new links automatically have changes
                return True

        return False

    @override(IOriSerializable)
    def _set_ori_snapshot_baseline_children(self, baseline_id: OriBaselineEnum):
        for link in self.__outgoing_links.values():
            link.set_ori_snapshot_baseline(baseline_id)

    @override(IOriSerializable)
    def _check_ori_diffs(self, other_ori: Decl.ActorPart, diffs: Dict[str, Any], tol_float: float):
        if self.__name != other_ori.name:
            diffs['part_frame.name'] = (self.__name, other_ori.name)
        if self.__ifx_level != other_ori.ifx_level:
            diffs['part_frame.ifx_level'] = (self.__ifx_level, other_ori.ifx_level)
        if abs(self.size.height - other_ori.size.height) > tol_float:
            # WARNING: self.size != self.__size because the former includes the header height
            diffs['part_frame.height'] = (self.size.height, other_ori.size.height)
        if abs(self.__size.width - other_ori.size.width) > tol_float:
            diffs['part_frame.width'] = (self.__size.width, other_ori.size.width)
        if abs(self.__position.x - other_ori.pos_x) > tol_float:
            diffs['part_frame.x'] = (self.__position.x, other_ori.pos_x)
        if abs(self.__position.y - other_ori.pos_y) > tol_float:
            diffs['part_frame.y'] = (self.__position.y, other_ori.pos_y)
        if self.__comment != other_ori.comment:
            diffs['part_frame.comment'] = (self.__comment, other_ori.comment)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __restore_links(self, links_restore_info: PartLinksRestoreMap,
                        waypoint_offset: Vector,
                        no_waypoints: Set[PartLink]) -> PartLinksRestoreMap:
        """
        :param links_restore_info: see restore_outgoing_links()
        :param waypoint_offset: an x,y offset for the link waypoints
        :param no_waypoints: links for which waypoints should not be restored
        :return: a map of links to their restoration info; these links could not be restored as the
            source and/or target frames have insufficient ifx levels
        """
        dropped_links = {}
        for link, restore_info in links_restore_info.items():
            source_frame = restore_info.source_frame
            try:
                if link in no_waypoints:
                    link = PartLink(None, copy_unattached=link)
                source_frame.restore_outgoing_link(link, restore_info, waypoint_offset=waypoint_offset)
            except Exception as exc:
                dropped_links[link] = restore_info
                log.warning('Dropping link {} ({}): {}', link.name, restore_info, exc)

        return dropped_links

    def __get_ori_def_local(self) -> Dict[str, Any]:
        """
        Returns a dictionary of ORI data local to this object, ie. not including any info about data members
        that are themselves ORI components.
        """
        return {
            PfKeys.NAME: self.__name,
            PfKeys.IFX_LEVEL: self.__ifx_level,
            PfKeys.FRAME_STYLE: self.__frame_style.name,
            PfKeys.VISIBLE: self.__visible,
            PfKeys.DETAIL_LEVEL: self.__detail_level.name,
            PfKeys.SIZE: {
                SzKeys.HEIGHT: self.__size.height,  # must not include the header
                SzKeys.WIDTH: self.__size.width,
                SzKeys.SCALE_3D: self.__size.scale_3d
            },
            PfKeys.POSITION: {
                PosKeys.X: self.__position.x,
                PosKeys.Y: self.__position.y
            },
            PfKeys.COMMENT: self.__comment,
        }

    def __set_size(self, width: float, height: float, scale_3d: float = None):
        """
        Set the size of the content portion of this object.
        :param width: new width; if smaller than the part's minimum, value is capped and a warning is logged
        :param height: new height; if smaller than the part's minimum, value is capped and a warning is logged
        :param scale_3d: new scale; if is None, the scale is not changed
        """
        min_width, min_height = self.get_min_width(), self.get_min_height()

        if width < min_width:
            log.warning("Attempt to set width of the part {} to {}, smaller than min ({}), setting to min",
                        self.__part.SESSION_ID, width, min_width)
            width = min_width

        if height < min_height:
            log.warning("Attempt to set height of the part {} to {}, smaller than min ({}), setting to min",
                        self.__part.SESSION_ID, height, min_height)
            height = min_height

        if scale_3d is None and self.__size is not None:
            scale_3d = self.__size.scale_3d

        self.__size = Size(width, height, scale_3d=scale_3d)
