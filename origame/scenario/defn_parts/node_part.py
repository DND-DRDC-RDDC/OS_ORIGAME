# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provides Node scenario part functionality

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...core import BridgeEmitter, BridgeSignal, override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..ori import OriNodePartKeys as NpKeys

from .part_types_info import register_new_part_type
from .base_part import BasePart
from .common import Position
from .part_link import PartLink

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'NodePart',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    ActorPart = 'ActorPart'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class NodePart(BasePart):
    """
    A node provides a many-to-one link between parts. The node can have many incoming links, but it only uses the
    first outgoing link. The node is intended to be used in a function part: when the script uses a link that
    ties to a node, the returned part is not the node, but the part at the end of the node chain:

        FunctionPart -> link_name -> node 1 -> some_link -> node 2 -> some_link -> Part
        # in F script:
        p = link.link_name

    then p is the Part at end of node chain.
    """

    NODE_WIDTH = 0.5
    NODE_HEIGHT = 0.5

    SHOW_FRAME = False
    RESIZABLE_FRAME = False
    CAN_BE_LINK_SOURCE = True
    DEFAULT_VISUAL_SIZE = dict(width=NODE_WIDTH, height=NODE_HEIGHT)
    MIN_CONTENT_SIZE = DEFAULT_VISUAL_SIZE
    PART_TYPE_NAME = "node"
    DESCRIPTION = """\
        Use this part to break a link into segments.

        A link that connects to a node and then from the node to a destination part can be treated exactly
        the same as a link that connects directly to the destination part. This holds for multiple nodes
        connected in series.

        A node can only have 1 outgoing link.
    """

    # -------------------------------- instance (self) PUBLIC properties -------------------------

    def __init__(self, parent: Decl.ActorPart, name: str = None, position: Position = None):
        BasePart.__init__(self, parent, name=name, position=position)

    def get_endpoint_part(self) -> BasePart:
        """
        If this node is linked to any part except another node, return that part. Else, follow the chain of
        nodes to the first non-node part, and return that. This uses get_next_part_frame(). Note: follows the
        chain of nodes every time the method is called, and this search is somewhat expensive.
        """
        # TODO build 3: optimize this by having nodes cache the found part, and have a "cache dirty" flag that
        #    gets set to true when any node link gets changed, and true gets propagated to all incoming links that
        #    originate at another node
        found_part = None
        node = self
        while node and not found_part:
            part_frame = node.get_next_part_frame()
            if not part_frame:  # node not connected to any part
                break

            if part_frame.part.PART_TYPE_NAME == self.PART_TYPE_NAME:
                node = part_frame.part
            else:
                found_part = part_frame.part

        return found_part

    def get_next_part_frame(self):
        """
        Get the part that our frame's first outgoing link is attached to. Returns None if no outgoing links.
        """
        links = self._part_frame.get_outgoing_links()
        return list(links)[0].target_part_frame if links else None

    @override(BasePart)
    def get_as_link_target_part(self) -> Either[BasePart, Any]:
        """
        Get the Part pointed at by the final node in a node chain, as a link target
        :return: resolved part
        """
        part = self.get_endpoint_part()
        return None if part is None else part.get_as_link_target_part()

    @override(BasePart)
    def on_outgoing_link_removed(self, link: PartLink):
        for link in self._part_frame.incoming_links:
            origin_part = link.source_part_frame.part
            origin_part.on_link_target_part_changed(link)

    @override(BasePart)
    def on_link_target_part_changed(self, link: PartLink):
        for link in self._part_frame.incoming_links:
            origin_part = link.source_part_frame.part
            origin_part.on_link_target_part_changed(link)

    @override(BasePart)
    def can_add_outgoing_link(self, part_type_str: str=None) -> bool:
        """Nodes can only have one outgoing link, so returns True only if there are no outgoing links already"""
        return not self._part_frame.outgoing_links

    @override(BasePart)
    def assign_from_object(self, value: Either[BasePart, object]):
        """
        If this part is a link target, then setting the target replaces self in parent actor by a Variable part
        that has the value.
        :param value: The value to be 'assigned' to self.
        """
        part = self.get_endpoint_part()
        if part is None:
            raise ValueError('The target of the destination node is None, which cannot be assigned to with a value.')

        part.assign_from_object(value)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SCRIPTING_API_EXTEND = ()

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------


# Add this part to the global part type/class lookup dictionary.
register_new_part_type(NodePart, NpKeys.PART_TYPE_NODE)
