# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Pulse Part Editor and related widgets.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import PulsePart, PulsePartState
from ...scenario import ori

from ..conversions import SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE
from ..conversions import convert_float_days_to_tick_period_tuple

from .scenario_part_editor import BaseContentEditor
from .Ui_pulse_part_editor import Ui_PulsePartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PulsePartEditorPanel'
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

class PulsePartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    _SUBMIT_ORDER = BaseContentEditor._SUBMIT_ORDER + ['pulse_period_days', 'state', 'priority']

    # The initial size to make this editor look nice.
    INIT_WIDTH = 300
    INIT_HEIGHT = 310

    # --------------------------- class-wide methods --------------------------------------------

    def __init__(self, part: PulsePart, parent: QWidget = None):
        """
        Initializes this panel with a back end Pulse Part and a parent QWidget.

        :param part: The Pulse Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_PulsePartEditorWidget()
        self.ui.setupUi(self)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.days_edit,
                     self.ui.hours_edit,
                     self.ui.minutes_edit,
                     self.ui.seconds_edit,
                     self.ui.active_state_radio,
                     self.ui.inactive_state_radio,
                     self.ui.priority_edit]
        return tab_order

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Collects the data from the Pulse Part GUI in order to submit them to the back end.

        :returns: the pulse part data dict.
        """
        days = self.ui.days_edit.value()
        hours = self.ui.hours_edit.value()
        minutes = self.ui.minutes_edit.value()
        seconds = self.ui.seconds_edit.value()

        normalized_in_secs = 0.0

        if days:
            normalized_in_secs += float(days) * SECONDS_PER_DAY
        if hours:
            normalized_in_secs += float(hours) * SECONDS_PER_HOUR
        if minutes:
            normalized_in_secs += float(minutes) * SECONDS_PER_MINUTE
        if seconds:
            normalized_in_secs += float(seconds)

        if self.ui.inactive_state_radio.isChecked():
            pulse_state = PulsePartState.inactive
        else:
            pulse_state = PulsePartState.active

        pulse_priority = float(self.ui.priority_edit.value())

        # Even if the pulse does not use "parameters", we add it into the return dict to satisfy the
        # IExecutablePart contract. The empty parameters will facilitate the editing change detection.
        data_dict = dict(pulse_period_days=normalized_in_secs / SECONDS_PER_DAY,
                         state=pulse_state,
                         priority=pulse_priority,
                         parameters='')
        return data_dict

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        pulse_period = data['pulse_period_days']
        pulse_state = data['state']
        pulse_priority = data['priority']

        days, hours, minutes, seconds = convert_float_days_to_tick_period_tuple(pulse_period)
        self.ui.days_edit.setValue(days)
        self.ui.hours_edit.setValue(hours)
        self.ui.minutes_edit.setValue(minutes)
        self.ui.seconds_edit.setValue(seconds)

        if pulse_state == PulsePartState.inactive:
            self.ui.inactive_state_radio.setChecked(True)
        else:
            self.ui.active_state_radio.setChecked(True)

        self.ui.priority_edit.setValue(pulse_priority)


register_part_editor_class(ori.OriPulsePartKeys.PART_TYPE_PULSE, PulsePartEditorPanel)
