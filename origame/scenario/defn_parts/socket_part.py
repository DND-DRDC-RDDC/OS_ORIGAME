# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Functionality to handle legacy Socket parts

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum

# [2. third-party]

# [3. local]
from ...core import BridgeEmitter, BridgeSignal, override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriBaselineEnum, OriContextEnum, OriScenData
from ..ori import OriCommonPartKeys as CpKeys, OriSocketPartKeys as SpKeys, OriNodePartKeys as NpKeys
from ..proto_compat_warn import prototype_compat_method_alias, prototype_compat_property_alias

from .part_types_info import register_new_part_type
from .base_part import BasePart
from .node_part import NodePart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SocketPartConverter',
    'SocketSideEnum',
    'SocketOrientationEnum',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    ActorPart = 'ActorPart'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class SocketSideEnum(IntEnum):
    """Identifies to which side, on parent actor's boundary, a Socket part is assigned"""
    no_side, left_side, right_side, top_side, bottom_side = range(5)


class SocketOrientationEnum(IntEnum):
    """Identifies the orientation of a Socket part, when it is not assigned to its parent actor's boundary"""
    horizontal, vertical = range(2)


class TempSocketPart(BasePart):
    """
    Convert a socket part's nodes to free nodes. This class is instantiated temporarily whenever ORI data is
    read from a file that defines a legacy (build 1) Socket part. In such case, a socket part is temporarily
    created to

    - position the nodes that it manages: Prototype guarantees that node parts are instantiated after their
      manager socket, but build 1 Origame does not. Hence, resolving node references from ORI to actual node
      parts requires that all children of the socket have been created. Also, build 1 used indices into socket's
      parent actor children list (so if parent had children list {part1, node1, part2, node2, part3, socket),
      the socket node list would be (1, 3) (indexing starts at 0)). Hence, the socket part exists until the
      socket has been given a chance to resolve its node list to a list of node parts, and this can only
      occur after all children parts have been created. At resolution time, the node positions are re-established
      (this is not strictly necessary since the node positions in the ORI should be correct; but just in case).
    - act as source or target of links that to/from the socket so the links can be created without additional
      complicated logic

    Once the above is complete, the socket can be removed from the scenario. This removes temporary links to/from
    socket (leaving links to/from the nodes that it was managing untouched).

    Note that since it possible to import a legacy scenario into a scenario, the part must remain available
    for creation by the actor at all times. However, the part must not be available for creation to the user.
    For this reason, it uses the USER_CREATABLE attribute to "hide" itself from the GUI.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    SOCKET_WIDTH_ONE_NODE = 1.0
    SOCKET_HEIGHT_ONE_NODE = 1.0

    SHOW_FRAME = False
    USER_CREATABLE = False
    DEFAULT_VISUAL_SIZE = dict(width=SOCKET_WIDTH_ONE_NODE, height=SOCKET_HEIGHT_ONE_NODE)
    MIN_CONTENT_SIZE = DEFAULT_VISUAL_SIZE
    PART_TYPE_NAME = "socket"

    # Offset used to center the node (possibly due to graphics pen thickness?)
    X_OFFSET = 0.03
    Y_OFFSET = -0.03

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: Decl.ActorPart):
        """
        """
        BasePart.__init__(self, parent)
        self.__side = SocketSideEnum.no_side
        self.__orientation = SocketOrientationEnum.vertical
        self.__node_indices = []

    def resolve_ori_refs(self, nodes_map: Dict[int, NodePart]):
        """
        Resolve the nodes specified in _set_from_ori_impl from indices to actual references to NodePart objects, using
        the parent's children. Should only be called by parent actor after all nodes created.
        """
        nodes = []
        for node_part_ref in self.__node_indices:
            node_part = nodes_map[node_part_ref]
            assert node_part.PART_TYPE_NAME == NpKeys.PART_TYPE_NODE
            assert not node_part.get_is_ifx_part()

            nodes.append(node_part)
            if self.__side != SocketSideEnum.no_side:
                # this node is exposed to next level up!
                node_frame = node_part.part_frame
                node_frame.set_ifx_level(1)
                node_frame.name = '{}_{}_{}'.format(self.__side.name, self._part_frame.name, node_frame.name)
                log.warning("Created standalone node {} from deprecated socket {}", node_part, self)

        for node, node_pos in self.__iter_node_positions(nodes):
            node.part_frame.set_position(*node_pos)

    def get_num_nodes(self) -> int:
        return len(self.__node_indices)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    num_nodes = property(get_num_nodes)

    # not usable in editing or scripting:
    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SCRIPTING_API_EXTEND = ()

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        """
        The nodes key is assumed to be a list of indices which can be resolved after the parent has created
        all sibling nodes (via self.resolve_nodes() that parent actor will call).
        """
        BasePart._set_from_ori_impl(self, ori_data, context=context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        side_name = part_content[SpKeys.SIDE] or 'no_side'
        self.__side = SocketSideEnum[side_name.lower()]

        if part_content.get(SpKeys.ORIENTATION) is not None:
            self.__orientation = SocketOrientationEnum[part_content[SpKeys.ORIENTATION].lower()]

        self.__node_indices = part_content[SpKeys.NODE_REFS]

    def _on_frame_position_changed(self):
        pass

    def _on_frame_size_changed(self):
        pass

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __check_vertical(self) -> bool:
        """
        Determine if this socket is vertical or horizontal, depending on side setting or (if no side), orientation
        setting.
        :return: True if vertical, False if horizontal
        """
        if self.__side in (SocketSideEnum.left_side, SocketSideEnum.right_side):
            return True
        if self.__side in (SocketSideEnum.bottom_side, SocketSideEnum.top_side):
            return False
        assert self.__side == SocketSideEnum.no_side
        return self.__orientation == SocketOrientationEnum.vertical

    def __iter_node_positions(self, nodes: List[NodePart], offset_x: float = None, offset_y: float = None) \
            -> Tuple[NodePart, Tuple[float, float]]:
        """
        Iterator for node positions. It computes node positions based on whether the Socket is horizontal or
        vertical. If the offset is not given, the socket's frame top-left is used, ie position is in parent actor
        frame (same as the socket itself). Otherwise, the offset should be a coordinate indicating where the
        top left corner of socket is in desired frame of reference (useful for showing boundary socket on parent).

        :param offset_x: the X offset to add to position; socket's part frame X if None
        :param offset_y: the Y offset to add to position; socket's part frame Y if None
        :return: pair consisting of node and a tuple (x,y) for position
        """
        # Center of the socket:
        offset_x = offset_x or self._part_frame.pos_x
        offset_y = offset_y or self._part_frame.pos_y
        xc = offset_x + self.SOCKET_WIDTH_ONE_NODE / 2 + self.X_OFFSET - NodePart.NODE_WIDTH / 2
        yc = offset_y - self.SOCKET_HEIGHT_ONE_NODE / 2 + self.Y_OFFSET + NodePart.NODE_HEIGHT / 2

        # compute actual x, y for each node, yield:
        if self.__check_vertical():
            x0 = xc
            start_y = yc
            y0 = start_y
            for node in nodes:
                # node.part_frame.set_position(x=x0, y=y0)
                yield node, (x0, y0)
                y0 -= self.SOCKET_HEIGHT_ONE_NODE

        else:
            start_x = xc
            x0 = start_x
            y0 = yc
            for node in nodes:
                # node.part_frame.set_position(x=x0, y=y0)
                yield node, (x0, y0)
                x0 += self.SOCKET_WIDTH_ONE_NODE


class SocketPartConverter:
    """
    Manages temporary sockets created. This is only used while loading ORI data that defines sockets. Such
    sockets use indices to reference nodes; such nodes are in fact siblings of the socket.
    """

    def __init__(self):
        self.__sockets = {}
        self.__nodes_map = {}

    def add_temp_socket(self, index: int, part: TempSocketPart):
        """
        Register a temporary socket.
        :param index: the index of socket into parent's list of children
        :param part: the temporary socket instance
        """
        log.warning("Legacy socket part {} will be converted to {} free nodes", part, part.num_nodes)
        log.warning("    (links to and from its nodes will be intact, but links to and from socket will be dropped")
        self.__sockets[index] = part

    def add_node_ref(self, index: int, node: NodePart):
        """
        Register a node that until now belonged to a socket.
        :param index: the index of node into parent's list of children
        :param part: the node part
        """
        self.__nodes_map[index] = node

    def resolve_ori_refs(self):
        """
        Resolve ORI references for nodes that were in sockets: once each socket has access to actual
        node part instance, it can position them.
        """
        for temp_socket in self.__sockets.values():
            temp_socket.resolve_ori_refs(self.__nodes_map)

    def get_temp_sockets(self) -> List[TempSocketPart]:
        """Get the list of registered temporary sockets."""
        return self.__sockets.values()


# Add this part to the global part type/class lookup dictionary:
register_new_part_type(TempSocketPart, SpKeys.PART_TYPE_SOCKET)
