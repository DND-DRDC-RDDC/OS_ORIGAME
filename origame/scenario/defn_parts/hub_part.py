# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the HubPart class and the functionality that supports the part as
a building block for the Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ...core import override
from ...core.typing import AnnotationDeclarations

from ..ori import OriHubPartKeys as HpKeys
from ..part_execs import check_link_name_is_frame

from .actor_part import ActorPart
from .base_part import BasePart
from .common import Position
from .part_types_info import register_new_part_type
from .part_link import TypeReferencingParts, TypeRefTraversalHistory, PartLink

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'HubPart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    HubPartScriptingProxy = 'HubPartScriptingProxy'


class HubPart(BasePart):
    """
    This class defines the functionality required to support an Origame Hub Part.
    """

    SHOW_FRAME = False
    RESIZABLE_FRAME = False
    CAN_BE_LINK_SOURCE = True
    DEFAULT_VISUAL_SIZE = dict(width=1.5, height=1.5)
    MIN_CONTENT_SIZE = DEFAULT_VISUAL_SIZE
    PART_TYPE_NAME = "hub"
    DESCRIPTION = """\
        Use this part to group together collections of parts for easy access.

        For example, if many parts in a model need access to a group of variables, create a hub and link
        it to each variable.  Then any parts needing access to the variables need only link to the hub.
    """

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The parent Actor Part to which this instance belongs.
        :param name: The name to be assigned to this instance.
        :param position: The coordinates of this instance within the parent Actor Part view.
        """

        BasePart.__init__(self, parent, name=name, position=position)

    def get_attribute(self, key: str) -> Either[BasePart, object]:
        """
        This function returns the Part instance that is pointed at by this instance's outgoing link that has a name
        matching the 'key' parameter.
        :param key: The name of an outgoing link from this instance.
        :return: The Part instance pointed to by the identified outgoing link.
        """
        is_frame, link_name = check_link_name_is_frame(key)

        out_link = self.part_frame.get_outgoing_link(link_name)
        if out_link is not None:
            target_frame = out_link.target_part_frame
            return target_frame if is_frame else target_frame.part

        return None

    @override(BasePart)
    def get_as_link_target_part(self) -> Decl.HubPartScriptingProxy:
        """
        Get a proxy that represents hub as a link target so that setattr etc can be provided outside of hub
        :return: HubPartScriptingProxy(self) which provides setattr and getattr methods
        """
        return HubPartScriptingProxy(self)

    @override(BasePart)
    def _fwd_link_chain_sources(self,
                                referencing_parts: TypeReferencingParts,
                                traversal_history: TypeRefTraversalHistory,
                                referenced_link_name: str):
        """
        Traverses further along its own incoming links. If the source part of a link has already been traversed, it
        will be skipped.

        When it traverses further, new values of the "referenced_link_name" will be passed to the source
        part's get_link_chain_sources.
        """
        for incoming_link in self.part_frame.incoming_links:
            src_part = incoming_link.source_part_frame.part
            if src_part.SESSION_ID in traversal_history:
                continue

            src_part.get_link_chain_sources(referencing_parts,
                                            traversal_history,
                                            incoming_link.name + "\\." + referenced_link_name)

    @override(BasePart)
    def _fwd_link_chain_rename(self,
                               referencing_parts: TypeReferencingParts,
                               traversal_history: TypeRefTraversalHistory,
                               referenced_link_name: str,
                               new_referenced_link_name: str):
        """
        Traverses further along its own incoming links. If the source part of a link has already been traversed, it
        will be skipped.

        When it traverses further, new values of the "referenced_link_name" and "new_referenced_link_name" will be
        passed to the source part's on_link_renamed.
        """
        for incoming_link in self.part_frame.incoming_links:
            src_part = incoming_link.source_part_frame.part
            if src_part.SESSION_ID in traversal_history:
                continue

            src_part.on_link_renamed(referencing_parts,
                                     traversal_history,
                                     incoming_link.name + "\\." + referenced_link_name,
                                     incoming_link.name + "." + new_referenced_link_name
                                     )

    @override(BasePart)
    def get_link_chains(self, traversal_history: TypeRefTraversalHistory) -> List[List[PartLink]]:
        """
        Gets unique link chains.
        :param traversal_history: Used to avoid recursions.
        :return: All the unique link chains that can be reached from this part.
        """
        ret_list = list()
        traversal_history.append(self.SESSION_ID)
        for link in self.part_frame.outgoing_links:
            if link.target_part_frame.part.SESSION_ID in traversal_history:
                continue

            for out_chain in link.get_link_chains(traversal_history):
                ret_list.append(out_chain)

        del traversal_history[-1]
        return ret_list

    def __dir__(self):
        """For code completion, need to return link names"""
        # Includes both the part references and their frame references
        link_dir = list()
        for link in self._part_frame.outgoing_links:
            link_dir.append(link.name)
            link_dir.append('_{}_'.format(link.name))

        return super().__dir__() + list(link_dir)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SCRIPTING_API_EXTEND = ()


class HubPartScriptingProxy:
    """
    This class provides a thin wrapper for the HubPart class to support the dot-notation reference and assignment
    requirements for HubParts in Origame script notation. It isolates implementations of the Python special
    methods __setattr__() and __getattr__() from the HubPart class to simplify their implementation and to exploit
    common functionality required in those methods and other similar methods defined in this module.
    """

    def __init__(self, hub_part: HubPart):
        """
        :param hub_part: The HubPart instance being wrapped by this class.
        """
        self._hub_part = hub_part

    def get_as_link_target_value(self) -> Decl.HubPartScriptingProxy:
        """Do not want to forward this to proxied hub, because the value is the proxy"""
        return self

    def __getattr__(self, attr: Any) -> Either[BasePart, object]:
        """
        This function returns the attribute requested of the HubPart or the resolved target of a HubPart link.
        It first checks if the specified attribute is an immediate attribute of the class, then checks to see if
        the specified attribute is the name of an outgoing link from the instance.
        This function supports Origame script dot-notation.
        :param attr: The attribute being request of this instance. It will likely be a function or a link name.
        :return: The attribute of the HubPart class or the resolved target of a HubPart link.
        """
        if hasattr(self._hub_part, attr):
            return getattr(self._hub_part, attr, None)
        else:
            # TODO build 3: apply same caching strategy as LinkedPartsScriptingProxy
            is_frame, _ = check_link_name_is_frame(attr)
            if is_frame:
                part_frame = self._hub_part.get_attribute(attr)
                return part_frame
            else:
                part = self._hub_part.get_attribute(attr)
                target_part = part.get_as_link_target_part()
                return target_part.get_as_link_target_value()

    def __setattr__(self, link_name: str, value: Either[BasePart, object]):
        """
        Set the part pointed at by the specified link to the specified value. The part pointed at by the link
        is resolved, as necessary (for example, for node parts, the resolved part is the one
        at the end of the node chain).

        :param link_name: The name of the outgoing link pointing at the (resolved) part to re-assign.
        :param value: The value to be assigned to the resolved target part. The value can be another scenario part
            in which case the resolved target frame will have the other scenario part as parent. If the value is not
            a scenario part, then resolved target frame will have a new Variable part as parent. Either way,
            the frame's previous parent part will be removed from the scenario.

        Example: hub H linked to a node N, linked to a part P. Each one has a frame Hf, Nf, Pf respectively.
            H.N = 'string' will cause H.N.P to be a Variable Part, with frame Pf. The old parent of Pf will be
            destroyed.
        """
        if link_name in self.__dict__:
            super().__setattr__(link_name, value)
        else:
            if "_hub_part" in self.__dict__:
                link = self._hub_part.part_frame.get_outgoing_link(link_name)
                if link is None:
                    raise ValueError("Part '{}' does not have a link named '{}'".format(self._hub_part.name, link_name))
                part = link.target_part_frame.part
                part.assign_from_object(value)

            else:
                super().__setattr__(link_name, value)

    def __str__(self) -> str:
        return "(proxy of) " + str(self._hub_part)

    def __dir__(self):
        """For code completion"""
        return dir(self._hub_part)


# Add this part to the global part type/class lookup dictionary
register_new_part_type(HubPart, HpKeys.PART_TYPE_HUB)
