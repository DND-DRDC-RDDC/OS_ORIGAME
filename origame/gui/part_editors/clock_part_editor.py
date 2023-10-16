# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Clock Part Editor and related widgets

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
from ...scenario.defn_parts import ClockPart
from ...scenario import ori

from ..conversions import SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE
from ..conversions import convert_float_days_to_tick_period_tuple

from .scenario_part_editor import BaseContentEditor
from .Ui_clock_part_editor import Ui_ClockPartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ClockPartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ClockPartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    _SUBMIT_ORDER = BaseContentEditor._SUBMIT_ORDER + ['tick_period_days', 'tick_value']

    # The initial size to make this editor look nice.
    INIT_WIDTH = 300
    INIT_HEIGHT = 310

    def __init__(self, part: ClockPart, parent: QWidget = None):
        """
        Initializes this panel with a back end Clock Part and a parent QWidget.

        :param part: The Clock Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_ClockPartEditorWidget()
        self.ui.setupUi(self)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.dateEdit,
                     self.ui.timeEdit,
                     self.ui.ticksEdit,
                     self.ui.daysEdit,
                     self.ui.hoursEdit,
                     self.ui.minutesEdit,
                     self.ui.secondsEdit]
        return tab_order

    @override(BaseContentEditor)
    def check_unapplied_changes(self) -> Either[Dict[str, Any], None]:
        """
        Override the base content editor to accommodate the following:
        1. The calendar part internal time and the time displayed may have a slight difference.
        This function checks if the two time values are close enough to be deemed same.
        2. Since the clock editor limits the presentation of the number of ticks to 11 significant
        figures, the value in legacy scenarios that permitted more than 11 significant digits
        is rounded to 11 sig figs before comparison here so that closing the panel without modifying
        tick value does not result in 'True'.
        """
        # Lower resolution of initial time data to correspond with what the editor displays
        init_data_copy = deepcopy(self._initial_data)
        date_time = init_data_copy['date_time']
        tick_value = init_data_copy['tick_value']

        # Do a round trip to the GUI: set it to the GUI and get it back
        time = QTimeEdit()
        time.setTime(date_time.time())
        time_portion = time.dateTime().toPyDateTime()
        time.setDate(date_time.date())
        date_portion = time.dateTime().toPyDateTime()

        tick_value = round(tick_value, ClockPart.TICK_SIG_FIGS)

        init_data_copy['date_time'] = datetime.datetime.combine(date_portion.date(), time_portion.time())
        init_data_copy['tick_value'] = tick_value

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
        Collects the data from the Clock Part GUI in order to submit them to the back end. The fields presented on
        the GUI do not match exactly the properties available in the Clock Part. So, we format them before sending
        them to the backend.

        :returns: the data collected from the Clock Part GUI.
        """
        date_portion = self.ui.dateEdit.dateTime().toPyDateTime()
        time_portion = self.ui.timeEdit.dateTime().toPyDateTime()
        days = self.ui.daysEdit.value()
        hours = self.ui.hoursEdit.value()
        minutes = self.ui.minutesEdit.value()
        seconds = self.ui.secondsEdit.value()

        normalized_in_secs = 0.0

        if days:
            normalized_in_secs += float(days) * SECONDS_PER_DAY
        if hours:
            normalized_in_secs += float(hours) * SECONDS_PER_HOUR
        if minutes:
            normalized_in_secs += float(minutes) * SECONDS_PER_MINUTE
        if seconds:
            normalized_in_secs += float(seconds)

        ticks = self.ui.ticksEdit.value()
        ticks_in_effect = 0.0
        if ticks:
            ticks_in_effect = float(ticks)

        data_dict = dict(date_time=datetime.datetime.combine(date_portion.date(), time_portion.time()),
                         tick_period_days=normalized_in_secs / SECONDS_PER_DAY,
                         tick_value=ticks_in_effect)
        return data_dict

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        date_time = data['date_time']
        tick_period_days = data['tick_period_days']
        tick_value = data['tick_value']
        self.ui.dateEdit.setDate(date_time.date())
        self.ui.timeEdit.setTime(date_time.time())
        self.ui.ticksEdit.setValue(tick_value)
        days, hours, minutes, seconds = convert_float_days_to_tick_period_tuple(tick_period_days)
        self.ui.daysEdit.setValue(days)
        self.ui.hoursEdit.setValue(hours)
        self.ui.minutesEdit.setValue(minutes)
        self.ui.secondsEdit.setValue(seconds)


register_part_editor_class(ori.OriClockPartKeys.PART_TYPE_CLOCK, ClockPartEditorPanel)
