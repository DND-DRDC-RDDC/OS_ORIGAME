# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: DateTime Part Editor and related widgets.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import datetime
from copy import deepcopy

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QTimeEdit

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core import override
from ...scenario.defn_parts import DateTimePart
from ...scenario import ori

from .scenario_part_editor import BaseContentEditor
from .Ui_datetime_part_editor import Ui_DateTimePartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'DateTimePartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

class DateTimePartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # The initial size to make this editor look nice.
    INIT_WIDTH = 300
    INIT_HEIGHT = 60

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------
    def __init__(self, part: DateTimePart, parent: QWidget = None):
        """
        Initializes this panel with a back end DateTime Part and a parent QWidget.

        :param part: The DateTime Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_DateTimePartEditorWidget()
        self.ui.setupUi(self)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.date_edit,
                     self.ui.time_edit]
        return tab_order

    @override(BaseContentEditor)
    def check_unapplied_changes(self) -> Either[Dict[str, Any], None]:
        """
        The datetime part internal time and the time displayed may have a slight difference. This function checks
        if the two time values are close enough to be deemed same.
        """
        # Lower resolution of initial time data to correspond with what the editor displays
        init_data_copy = deepcopy(self._initial_data)
        date_time = init_data_copy['date_time']

        # Do a round trip to the GUI: set it to the GUI and get it back
        time = QTimeEdit()
        time.setTime(date_time.time())
        time_portion = time.dateTime().toPyDateTime()
        time.setDate(date_time.date())
        date_portion = time.dateTime().toPyDateTime()

        init_data_copy['date_time'] = datetime.datetime.combine(date_portion.date(), time_portion.time())

        edited_data = self._get_data_for_submission()
        edited_data['name'] = self.parent().ui.part_name.text()
        edited_data['link_names'] = dict()
        if init_data_copy == edited_data:
            return None
        else:
            return edited_data

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Collects the data from the DateTime Part GUI in order to submit them to the back end. The fields presented on
        the GUI do not match exactly the properties available in the DateTime Part. So, we format them before sending
        them to the backend.

        :returns: the data collected from the DateTime Part GUI.
        """
        date_portion = self.ui.date_edit.dateTime().toPyDateTime()
        time_portion = self.ui.time_edit.dateTime().toPyDateTime()

        data_dict = dict(date_time=datetime.datetime.combine(date_portion.date(), time_portion.time()))
        return data_dict

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        date_time = data['date_time']
        self.ui.date_edit.setDate(date_time.date())
        self.ui.time_edit.setTime(date_time.time())


register_part_editor_class(ori.OriDateTimePartKeys.PART_TYPE_DATETIME, DateTimePartEditorPanel)
