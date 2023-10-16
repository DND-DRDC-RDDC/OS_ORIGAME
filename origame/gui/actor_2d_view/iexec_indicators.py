# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Indicators shared by all IExecutablePart part types

Version History: See SVN log.
"""
# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtSvg import QGraphicsSvgItem

# [3. local]
from ..gui_utils import get_icon_path
from ..safe_slot import safe_slot
from .part_box_item import PartBoxItem
from .part_box_side_item_base import TopSideTrayItemTypeEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'BreakpointIndicator',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class BreakpointIndicator:
    """
    The parent class for the part widgets that have breakpoint features
    """

    def __init__(self, part_box_item: PartBoxItem):
        self.__part_box_item = part_box_item
        self.__bp_marker = QGraphicsSvgItem(str(get_icon_path("marker_breakpoint.svg")))
        self.__bp_marker.setVisible(False)
        part_box_item.top_side_tray_item.add_obj(TopSideTrayItemTypeEnum.breakpoint_marker, self.__bp_marker)
        part_box_item.part.py_script_exec_signals.sig_breakpoints_set.connect(self.__slot_on_breakpoints_set)

    def __on_breakpoints_set(self, breakpoint_present: bool):
        """
        :param breakpoint_present: True if there is at least one break point.
        """
        self.__bp_marker.setVisible(breakpoint_present)
        self.__part_box_item.top_side_tray_item.update_item()

    __slot_on_breakpoints_set = safe_slot(__on_breakpoints_set)
