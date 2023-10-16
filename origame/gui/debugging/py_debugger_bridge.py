# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Gui debugger related.
Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QWidget

# [3. local]
from ...core import override
from ...scenario.part_execs import PyDebugger
from ...scenario import ScenarioManager, Scenario
from ..gui_utils import IScenarioMonitor
from ..safe_slot import safe_slot
from ..slow_tasks import get_progress_bar
from .debug_code_viewer import DebugCodeViewer

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PyDebuggerBridge'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class PyDebuggerBridge(IScenarioMonitor, QObject):
    """
    This class manages opening and closing the debugger window, and setting other debug-related
    state of the GUI window, based on debug state of backend.
    """

    def __init__(self, scenario_manager: ScenarioManager, debug_win_parent: QWidget = None):
        """
        :param scenario_manager: scenario manager to monitor for scenario instances
        :param debug_win_parent: parent of debug window
        """
        QObject.__init__(self)
        IScenarioMonitor.__init__(self, scenario_manager, auto_monitor=True)

        PyDebugger.get_singleton().signals.sig_start_debugging.connect(self.__slot_on_start_debugging)
        PyDebugger.get_singleton().signals.sig_exit_debugging.connect(self.__slot_on_exit_debugging)
        self.__dialog = None
        self.__debug_win_parent = debug_win_parent

    def force_close(self):
        """
        Close the debug window without asking for confirmation from the user. Only use when exiting the
        application.
        """
        self.__debug_win_parent = None
        if self.__dialog is not None:
            self.__dialog.reject(confirm=False)
            self.__dialog.close()
            self.__dialog = None

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        """Need to close obsolete dialog, if there is one"""
        if self.__dialog is not None:
            self.__dialog.set_debugging(False)
            self.__dialog.reject()
            self.__dialog = None

    def __on_start_debugging(self):
        """
        Called when a breakpoint has been hit and debugging begins.
        """
        self.__progress_resume = get_progress_bar().pause_progress()

        if self.__dialog is None:
            self.__dialog = DebugCodeViewer(parent=self.__debug_win_parent)

        self.__dialog.set_debugging(True)
        self.__dialog.raise_()
        self.__dialog.focus()
        self.__dialog.show()

    def __on_exit_debugging(self):
        """
        Called when debugging is finished.
        """
        get_progress_bar().resume_progress(self.__progress_resume)
        # if dialog still exists (there is a small chance that the dialog has already been closed), configure it
        # for not-debugging:
        if self.__dialog is not None:
            self.__dialog.set_debugging(False)

    __slot_on_exit_debugging = safe_slot(__on_exit_debugging)
    __slot_on_start_debugging = safe_slot(__on_start_debugging)
