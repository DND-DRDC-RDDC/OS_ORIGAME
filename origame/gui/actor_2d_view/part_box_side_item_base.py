# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Type names for the side box items.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import unique, IntEnum

# [2. third-party]
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QGraphicsWidget, QGraphicsItem, QSizePolicy

# [3. local]
from ...core import override_optional
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO, AnnotationDeclarations
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..gui_utils import QTBUG_55918_OPACITY
from .common import ICustomItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "Revision"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"


# -- Module-level objects -----------------------------------------------------------------------

__all__ = [  
    'TopSideTrayItemTypeEnum',
    'BottomSideTrayItemTypeEnum',
    'BaseSideTrayItem',
]

log = logging.getLogger('system')

class Decl(AnnotationDeclarations):
    PartBoxItem = 'PartBoxItem'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

@unique
class TopSideTrayItemTypeEnum(IntEnum):
    """
    This class represents the keys of the objects that are allowed to go to the TopSideTrayItem.
    """
    setup, reset, startup, finish, batch, breakpoint_marker, comment_bubble = range(7)


@unique
class BottomSideTrayItemTypeEnum(IntEnum):
    """
    This class represents the keys of the objects that are allowed to go to the BottomSideTrayItem.
    """
    exec_warning, missing_links = range(2)


class BaseSideTrayItem(ICustomItem, QGraphicsWidget):
    """
    Common features of the trays. Note: it is more convenient to derive from QGraphicsWidget than QGraphicsItem
    """

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: QGraphicsItem = None):
        """
        Most side items should derive from this class
        :param parent: The parent item
        :param part_box_item: This is not necessarily the same as the parent.
        """
        ICustomItem.__init__(self)
        QGraphicsWidget.__init__(self, parent)
        self.setSizePolicy(QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed))
        self._part_box_item = part_box_item
        self.setCursor(QCursor(Qt.ArrowCursor))
        self.setOpacity(QTBUG_55918_OPACITY)  # QTBUG-55918

    @override_optional
    def update_item(self):
        """
        The framework will call this after any changes. The default implementation does nothing. The derived classes
        should implement sizing, positioning and coloring business logic here.
        """
        pass