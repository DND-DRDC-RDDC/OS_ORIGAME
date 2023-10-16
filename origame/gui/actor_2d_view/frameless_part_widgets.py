# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: All 2d model view scenario part representations based on frameless widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import QWidget

# [3. local]
from ...scenario.defn_parts import InfoPart
from ...scenario import ori

from ..async_methods import AsyncRequest
from ..safe_slot import safe_slot

from .part_box_item import PartBoxItem
from .Ui_info_part import Ui_InfoPartWidget
from .base_part_widgets import FramelessPartWidget
from .common import register_part_item_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def function_example(a: int, b: float = 0) -> bool:
    """
    [EDIT:]Docstring summary line is a short one-line description of the function.
    [EDIT:]
    [EDIT:]Detailed description of function. Do not repeat what is in param/returns/raises, where these 
    [EDIT:]are described individually. In this paragraph, focus on what is not obvious from param/returns/
    [EDIT:]raises: when is it valid to call this function; is it an optional function, or it must be 
    [EDIT:]called; in the case of a method, what does it do to the object state; etc. 
    [EDIT:]
    [EDIT:]:param ARG1: Describe ARG1 function call argument, including conditions for validity. 
    [EDIT:]:param ARG2: Describe ARG2 function call argument... ....... ......... ........ .......... ........ ....
    [EDIT:]    Indent long lines by usual 4 spaces. 
    [EDIT:]:returns: Describe what the function returns (remove if not return value)
    [EDIT:]:raises EXCEPTION_TYPE_1: Describe under what conditions this exception is raised
    [EDIT:]:raises EXCEPTION_TYPE_2: Describe under what conditions this exception is raised
    """
    raise NotImplementedError


# -- Class Definitions --------------------------------------------------------------------------

class SomeClass:
    """
    [EDIT:] Docs (NOTE: below, only delete the 'section' separators not used)
    """

    # --------------------------- class-wide data and signals -----------------------------------


    # --------------------------- class-wide methods --------------------------------------------


    # --------------------------- instance (self) PUBLIC methods --------------------------------


    # --------------------------- instance PUBLIC properties and safe_slots ---------------------


    # --------------------------- instance __SPECIAL__ method overrides -------------------------


    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------


    # --------------------------- instance _PROTECTED properties and safe slots -----------------


    # --------------------------- instance __PRIVATE members-------------------------------------


class InfoPart2dContent(QWidget):
    """
    The content panel of an InfoPart2DWidget
    """

    def __init__(self):
        super().__init__()

        self.ui_info_part = Ui_InfoPartWidget()
        self.ui_info_part.setupUi(self)

        p = self.ui_info_part.textBrowser.palette()
        p.setColor(QPalette.Base, QColor(231, 222, 209))
        self.ui_info_part.textBrowser.setPalette(p)
        self.ui_info_part.textBrowser.setAutoFillBackground(True)


class InfoPartWidget(FramelessPartWidget):
    """
    An Info Part 2d widget
    """

    def __init__(self, part: InfoPart, parent_part_box_item: PartBoxItem = None):
        """
        :param part: The backend of this GUI.
        """
        super().__init__(part, parent_part_box_item)

        self._set_content_widget(InfoPart2dContent())
        self._part.signals.sig_text_changed.connect(self.__slot_on_text_changed)
        AsyncRequest.call(part.get_text, response_cb=self.__on_text_changed)
        self._update_size_from_part()

    def __on_text_changed(self, value: str):
        """
        Set the value to the text browser on the GUI
        :param value: The info text.
        """
        self._content_widget.ui_info_part.textBrowser.setText(value)

    __slot_on_text_changed = safe_slot(__on_text_changed)


register_part_item_class(ori.OriInfoPartKeys.PART_TYPE_INFO, InfoPartWidget)
