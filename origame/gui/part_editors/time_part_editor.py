# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Time Part Editor and related widgets.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from datetime import timedelta

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QDialogButtonBox

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.utils import timedelta_to_rel
from ...scenario.defn_parts import TimePart
from ...scenario import ori
from ..safe_slot import safe_slot

from .scenario_part_editor import BaseContentEditor
from .Ui_time_part_editor import Ui_TimePartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'TimePartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

class TimePartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # The initial size to make this editor look nice.
    INIT_WIDTH = 300
    INIT_HEIGHT = 310

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------
    def __init__(self, part: TimePart, parent: QWidget = None):
        """
        Initializes this panel with a back end Time Part and a parent QWidget.

        :param part: The Time Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_TimePartEditorWidget()
        self.ui.setupUi(self)
        self.ui.reset.clicked.connect(self.__slot_on_reset)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.days_edit,
                     self.ui.hours_edit,
                     self.ui.minutes_edit,
                     self.ui.seconds_edit]
        return tab_order

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Collects the data from the Time Part GUI in order to submit them to the back end. The fields presented on
        the GUI do not match exactly the properties available in the Time Part. So, we format them before sending
        them to the backend.

        :returns: the data collected from the Time Part GUI.
        """
        days = float(self.ui.days_edit.value())
        hours = float(self.ui.hours_edit.value())
        minutes = float(self.ui.minutes_edit.value())
        seconds = float(self.ui.seconds_edit.value())
        elapsed_time = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

        data_dict = dict(elapsed_time=elapsed_time)
        return data_dict

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        elapsed_time = timedelta_to_rel(data['elapsed_time']).normalized()
        self.ui.days_edit.setValue(elapsed_time.days)
        self.ui.hours_edit.setValue(elapsed_time.hours)
        self.ui.minutes_edit.setValue(elapsed_time.minutes)
        self.ui.seconds_edit.setValue(elapsed_time.seconds)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    # --------------------------- instance __PRIVATE members-------------------------------------
    def __on_reset(self):
        """
        Sets all fields to 0 and clicks "Apply".
        """
        self.ui.days_edit.setValue(0)
        self.ui.hours_edit.setValue(0)
        self.ui.minutes_edit.setValue(0)
        self.ui.seconds_edit.setValue(0)
        self.parent().ui.button_box.button(QDialogButtonBox.Apply).click()

    __slot_on_reset = safe_slot(__on_reset)


register_part_editor_class(ori.OriTimePartKeys.PART_TYPE_TIME, TimePartEditorPanel)
