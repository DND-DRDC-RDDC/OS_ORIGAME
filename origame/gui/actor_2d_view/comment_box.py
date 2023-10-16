# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Comment box for 2d view

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QFont

# [3. local]
from ..gui_utils import get_scenario_font
from .Ui_comment_box import Ui_CommentBox

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'CommentBoxWidget',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class CommentBoxWidget(QWidget):
    """
    The comment box that shows comment text. The box is only visible under some circumstances
    determined by the parent part box item.
    """

    BUTTON_FONT_FAMILY = '"Bell MT", Georgia, Serif;'
    BUTTON_FONT_SIZE = 14
    BUTTON_FONT_WEIGHT = -1

    def __init__(self, parent=None):
        super().__init__()
        self.ui = Ui_CommentBox()
        self.ui.setupUi(self)
        self.ui.cue.setFont(QFont(self.BUTTON_FONT_FAMILY, self.BUTTON_FONT_SIZE, self.BUTTON_FONT_WEIGHT, True))
        self.ui.comment_text.setFont(get_scenario_font())
