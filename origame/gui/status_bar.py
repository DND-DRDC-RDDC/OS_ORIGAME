# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The status_bar module provides customization and functionality to the Application, Simulation,
and Batch Status Bars.

This module consists of the SimulationStatusBar, BatchSimulationStatusBar, ApplicationStatusBar class.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import weakref

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QMessageBox, QStatusBar

# [3. local]
from ..core import get_enum_val_name, override
from ..batch_sim import BatchSimManager, BsmStatesEnum
from ..scenario import ScenarioManager, Scenario, SimStatesEnum as MainSimStatesEnum

from .gui_utils import IScenarioMonitor, exec_modal_dialog
from .conversions import convert_float_days_to_string
from .safe_slot import safe_slot
from .slow_tasks import init_progress_bar, shutdown_slow_tasks
from .Ui_status_bar_batch_sim import Ui_BatchSimStatusBar
from .Ui_status_bar_main_sim import Ui_MainSimStatus

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'OriStatusBar'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class MainSimulationStatusSubBar(IScenarioMonitor, QWidget):
    def __init__(self, scen_man: ScenarioManager, parent: QWidget = None):
        QWidget.__init__(self)
        IScenarioMonitor.__init__(self, scen_man)

        self.ui = Ui_MainSimStatus()
        self.ui.setupUi(self)

        alert_str = "<b><font color='red' size='4'> !!! </b></font>"
        self.ui.label_alert_indicator.setText(alert_str)
        # only show the alert when there is one:
        self.ui.label_alert_indicator.setVisible(False)
        self.ui.label_alert.setVisible(False)

        self.__scenario_weak = None
        self._monitor_scenario_replacement()

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        if self.__scenario_weak is not None:
            old_scenario = self.__scenario_weak()
            if old_scenario is not None:
                sim_con_sigs = old_scenario.sim_controller.signals
                sim_con_sigs.sig_state_changed.disconnect(self.__slot_on_state_changed)
                sim_con_sigs.sig_sim_time_days_changed.disconnect(self.__slot_on_time_elapsed)
                alert_signals = old_scenario.sim_controller.alert_signals
                alert_signals.sig_alert_status_changed.disconnect(self.__slot_on_sim_alert_status_changed)
                old_scenario.event_queue.signals.sig_queue_totals_changed.disconnect(self.__slot_on_event_queue_changed)
            self.__scenario_weak = None

        self.__scenario_weak = weakref.ref(scenario)
        sim_con_sig = scenario.sim_controller.signals
        sim_con_sig.sig_state_changed.connect(self.__slot_on_state_changed)
        sim_con_sig.sig_sim_time_days_changed.connect(self.__slot_on_time_elapsed)
        alert_signals = scenario.sim_controller.alert_signals
        alert_signals.sig_alert_status_changed.connect(self.__slot_on_sim_alert_status_changed)
        scenario.event_queue.signals.sig_queue_totals_changed.connect(self.__slot_on_event_queue_changed)

        self.__init_sim_status()

    def __init_sim_status(self):
        """
        Set up initial labels.
        """
        # Init status objects
        scenario = self.__scenario_weak()
        if scenario is not None:
            sim_controller = scenario.sim_controller
            self.__on_state_changed(sim_controller.state_id)
            self.__on_time_elapsed(sim_controller.sim_time_days, None)
            self.__on_sim_alert_status_changed()
            self.ui.label_events_value.setText(str(sim_controller.num_events))

    def __on_sim_alert_status_changed(self):
        """
        Whenever the sim controller flags an error, show it.
        """
        scenario = self.__scenario_weak()
        if scenario is not None:
            scenario = self.__scenario_weak()
            last_step_error_info = scenario.sim_controller.last_step_error_info
            if last_step_error_info is None:
                self.ui.label_alert_indicator.hide()
                self.ui.label_alert.hide()
            else:
                self.ui.label_alert_indicator.setToolTip(last_step_error_info.msg)
                self.ui.label_alert_indicator.show()
                self.ui.label_alert.show()
                exec_modal_dialog("Sim Step Error", last_step_error_info.msg, QMessageBox.Critical)

    def __on_state_changed(self, state_id: int):
        state_str = get_enum_val_name(MainSimStatesEnum(state_id)).capitalize()
        self.ui.label_state_value.setText(state_str)

    def __on_time_elapsed(self, elapsed_time_in_days: float, delta: float):
        """
        This slot is invoked whenever the Simulation Controller emits the sig_time_update signal.
        :param elapsed_time_in_days: the main simulation elapsed time (days).
        """
        time_str = convert_float_days_to_string(elapsed_time_in_days)
        self.ui.label_time_value.setText(time_str)

    def __on_event_queue_changed(self, num_scheduled_events: int, num_asap_events: int):
        """
        This slot is invoked whenever the Event Queue emits the sig_queue_totals_changed signal.
        :param num_scheduled_events: number of scheduled (non-ASAP) events in the Event Queue.
        :param num_asap_events: number of ASAP events.
        """
        num_events = num_scheduled_events + num_asap_events
        self.ui.label_events_value.setText(str(num_events))

    __slot_on_state_changed = safe_slot(__on_state_changed)
    __slot_on_time_elapsed = safe_slot(__on_time_elapsed)
    __slot_on_event_queue_changed = safe_slot(__on_event_queue_changed)
    __slot_on_sim_alert_status_changed = safe_slot(__on_sim_alert_status_changed)


class BatchSimulationStatusSubBar(QWidget):
    """A QLabel that is customized for display in the QStatusBar"""

    def __init__(self, batch_sim_manager: BatchSimManager, parent: QWidget = None):
        super().__init__(parent)

        self.ui = Ui_BatchSimStatusBar()
        self.ui.setupUi(self)

        batch_sim_manager.signals.sig_state_changed.connect(self.__slot_bsm_state_changed)
        batch_sim_manager.signals.sig_replication_done.connect(self.__slot_bsm_replication_done)
        batch_sim_manager.signals.sig_replication_error.connect(self.__slot_bsm_replication_error)

    def __bsm_state_changed(self, state_id: int):
        """
        This slot is invoked whenever the Batch Simulation Manager changes its state and emits the
        sig_state_changed signal.
        :param state_id: This is the new state_id that the Batch Simulation Manager is in.
        """
        state_str = get_enum_val_name(BsmStatesEnum(state_id)).capitalize()
        self.ui.label_state_value.setText(state_str)

    def __bsm_replication_done(self, num_replics_done: int, total_replics: int):
        """
        This slot is invoked whenever the Batch Simulation Manager finishes a replication and emits
        the sig_replication_done signal.
        :param num_replics_done: the number of replications
        :param total_replics: the total number of replications.
        """
        self.ui.label_compl_actual_value.setText(str(num_replics_done))
        self.ui.label_compl_total_value.setText(str(total_replics))

    def __bsm_replication_error(self, reps_done: int, total_reps: int, error: str):
        """
        This slot is invoked whenever a replication encounters an error during batch simulation and the Batc
        Simulation Manager emits the sig_replication_error signal.
        :param reps_done: The number of replications that have been completed.
        :param total_reps: The total number of reps to complete.
        :param error: Error information.
        """
        pass

    __slot_bsm_state_changed = safe_slot(__bsm_state_changed)
    __slot_bsm_replication_done = safe_slot(__bsm_replication_done)
    __slot_bsm_replication_error = safe_slot(__bsm_replication_error)


class OriStatusBar(QStatusBar):
    """
    Origame status bar for main window.

    Note: Would have been nice to be able to intercept status message changes to put the message in label with
    same style as other widgets that are in status bar, but could not get this to work such that when leave a
    widget, the current temp message disappears from widget
    """

    def __init__(self, scen_man: ScenarioManager, batch_sim_man: BatchSimManager, parent: QWidget = None):
        super().__init__(parent)
        sim_status = MainSimulationStatusSubBar(scen_man)
        batch_status = BatchSimulationStatusSubBar(batch_sim_man)
        progress_bar = init_progress_bar(main=parent, parent=self)

        self.addPermanentWidget(progress_bar)
        self.addPermanentWidget(sim_status)
        self.addPermanentWidget(batch_status)
