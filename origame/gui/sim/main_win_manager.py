# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Uil classes for MainSimulationManager and BatchSimulationManager

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import weakref

# [2. third-party]
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QMessageBox, QAction
from PyQt5.QtGui import QIcon, QPixmap

# [3. local]
from ...core import override
from ...scenario import ScenarioManager, Scenario, SimStatesEnum as MainSimStatesEnum, SimController
from ...batch_sim import BatchSimManager

from ..gui_utils import exec_modal_dialog, IScenarioMonitor
from ..safe_slot import safe_slot
from ..async_methods import AsyncRequest
from ..animation import RuntimeAnimationSettingMonitor
from .main import MainSimSharedButtonStates
from ..Ui_mainwindow import Ui_MainWindow

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # defines module members that are public; one line per string
    'MainSimBridge',
    'BatchSimManagerBridge'
]

log = logging.getLogger('system')

# Number of milliseconds between updates of the sim engine; 0 => whenever Qt thread idle
DEFAULT_AUTO_UPDATE_MAIN_SIM_ANIM_INTERVAL_MSEC = 100  # smaller than 100 can lead to freezes
DEFAULT_AUTO_UPDATE_MAIN_SIM_NO_ANIM_INTERVAL_MSEC = 1


# -- Class Definitions --------------------------------------------------------------------------

class BatchSimManagerBridge(QObject):
    """
    This class is the bridge between the GUI and the Batch Simulation Manager.
    Signals between the GUI and the Batch Simulation Manager are caught as slots
    in this class and re-emitted.
    """

    def __init__(self, batch_sim_manager: BatchSimManager):
        """
        :param batch_status_bar: the label object in which to put batch sim state
        """
        super().__init__()
        self._batch_sim_manager = batch_sim_manager

    def run_batch(self, _: bool = None):
        """
        This is the method that will be invoked when the Simulation - Run Batch Simulation context
        menu is clicked from the GUI.
        """
        try:
            self._batch_sim_manager.start_sim()

        except Exception as exc:
            message = "Could not start the batch simulation, please check configuration."
            exec_modal_dialog('Batch Simulation Error', message, QMessageBox.Critical)
            log.error(message)

    slot_run_batch = safe_slot(run_batch)


class AutoUpdaterMainSim:
    """
    Auto-updater to call the current sim controller's update() method in the backend thread,
    when requested.
    """

    def __init__(self, sim_controller: SimController):
        """
        :param sim_controller: the SimController instance on which to call update()
        """
        self.__sim_controller = sim_controller
        self.__sim_state = MainSimStatesEnum.paused

    def start_loop(self):
        """Start calling the sim controller's update() method"""
        self.__sim_state = MainSimStatesEnum.running
        self.__request_update()

    def pause_loop(self):
        """Stop calling the sim controller's update() method"""
        self.__sim_state = MainSimStatesEnum.paused

    def __request_update(self, _: int = None):
        """
        Calls the sim_controller's update() method in a loop while simulation state is set to 'running'.
        :param _: ignored parameter required to received response callbacks from the sim controller.
        """
        if self.__sim_state == MainSimStatesEnum.paused:
            return

        AsyncRequest.call(self.__sim_controller.sim_update, response_cb=self.__request_update)


# noinspection PyUnresolvedReferences
class MainSimBridge(IScenarioMonitor, QObject):
    """Bridge to the sim controller of the loaded scenario"""

    def __init__(self,
                 scen_man: ScenarioManager,
                 ui: Ui_MainWindow,
                 main_sim_shared_button_states: MainSimSharedButtonStates):
        QObject.__init__(self)
        IScenarioMonitor.__init__(self, scen_man)
        self.__main_sim_shared_button_states = main_sim_shared_button_states
        self.__main_sim_shared_button_states.set_ui_main_win(ui)

        self.__debug_action = ui.action_debug
        self.__anim_action = ui.action_toggle_animation

        # Connect event queue
        self.__scenario_weak = None
        self._monitor_scenario_replacement()
        # timer to stimulate the sim controller at high freq
        self.__sim_auto_updater = None

        if self.__anim_action is None:
            self.__rasm = None
        else:
            self.__rasm = RuntimeAnimationSettingMonitor(scen_man, self.__anim_action)

        ui.action_run_sim.triggered.connect(self.__slot_start_simulation)
        ui.action_play_pause_sim.triggered.connect(self.__slot_pause_resume)
        ui.action_step_sim.triggered.connect(self.__slot_on_step)
        ui.action_reset_sim.triggered.connect(self.__slot_on_reset)
        ui.action_clear_events.triggered.connect(self.slot_on_clear_queue)
        ui.action_debug.triggered.connect(self.__slot_on_user_toggled_debug_mode)
        ui.action_toggle_animation.triggered.connect(self.__slot_on_runtime_anim_changed)

    def on_clear_queue(self):
        """
        Slot called when the Clear Queue menu item is selected.
        """
        msg = 'Are you sure you want to delete ALL events from the Event Queue? Click Yes to proceed, or ' \
              'No to go back.'
        user_confirmation = exec_modal_dialog('Clear Event Queue', msg, QMessageBox.Question)

        scenario = self.__scenario_weak()
        if scenario is not None and user_confirmation == QMessageBox.Yes:
            AsyncRequest.call(scenario.sim_controller.clear_event_queue)

    slot_on_clear_queue = safe_slot(on_clear_queue)

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        if self.__scenario_weak is not None:
            old_scenario = self.__scenario_weak()
            if old_scenario is not None:
                log.debug('Disconnecting from previous sim controller')
                sim_con_sigs = old_scenario.sim_controller.signals
                sim_con_sigs.sig_state_changed.disconnect(self.__slot_on_state_changed)
                sim_con_sigs.sig_debug_mode_changed.disconnect(self.__slot_on_debug_mode_changed)
                sim_con_sigs.sig_anim_while_run_dyn_setting_changed.disconnect(self.__slot_set_animation)
            self.__sim_auto_updater.pause_loop()
            self.__scenario_weak = None

        log.debug('Main win connecting to new sim controller')
        self.__scenario_weak = weakref.ref(scenario)
        sim_con_sig = scenario.sim_controller.signals
        sim_con_sig.sig_state_changed.connect(self.__slot_on_state_changed)
        sim_con_sig.sig_debug_mode_changed.connect(self.__slot_on_debug_mode_changed)
        sim_con_sig.sig_anim_while_run_dyn_setting_changed.connect(self.__slot_set_animation)
        self.__sim_auto_updater = AutoUpdaterMainSim(scenario.sim_controller)

        self.__anim_action.setChecked(scenario.sim_controller.settings.anim_while_run_dyn)
        self.__debug_action.setChecked(scenario.sim_controller.debug_mode)

    def __on_state_changed(self, sim_state: MainSimStatesEnum):
        """
        This slot is invoked whenever the Simulation Controller changes its state and emits the
        sig_state_changed signal.
        :param sim_state: the new state simulation is in: 'Running' or 'Paused'
        """
        self.__main_sim_shared_button_states.update_buttons(sim_state)
        if sim_state == MainSimStatesEnum.running:
            self.__sim_auto_updater.start_loop()

        elif sim_state == MainSimStatesEnum.paused:
            self.__sim_auto_updater.pause_loop()

        else:
            assert sim_state == MainSimStatesEnum.debugging
            self.__sim_auto_updater.pause_loop()

    def __start_simulation(self):
        """Start the simulation"""
        scenario = self.__scenario_weak()
        if scenario is not None:
            AsyncRequest.call(scenario.sim_controller.sim_run)

    def __pause_resume(self):
        """Pause or resume event processing"""
        scenario = self.__scenario_weak()
        if scenario is not None:
            AsyncRequest.call(scenario.sim_controller.sim_pause_resume)

    def __on_step(self):
        """
        Slot called when the Step menu item is selected.
        """
        scenario = self.__scenario_weak()
        if scenario is not None:
            AsyncRequest.call(scenario.sim_controller.sim_step)

    def __on_reset(self):
        """
        Slot called when the Reset menu item is selected.
        """
        scenario = self.__scenario_weak()
        if scenario is not None:
            AsyncRequest.call(scenario.sim_controller.do_reset_steps)

    def __on_debug_mode_changed(self, state: bool):
        """
        Slot called when debug mode is changed by the backend.
        :param state: The new debug mode.
        """
        self.__debug_action.setChecked(state)

    def __on_user_toggled_debug_mode(self):
        """
        Slot called when user toggled debug mode.
        """
        scenario = self.__scenario_weak()
        if scenario is not None:
            AsyncRequest.call(scenario.sim_controller.set_debug_mode, self.__debug_action.isChecked())

    def __on_runtime_anim_changed(self):
        """
        Slot called when use clicks Animition on/off in main menu.
        """
        scenario = self.__scenario_weak()
        if scenario is not None:
            is_checked = self.__anim_action.isChecked()
            scenario.sim_controller.set_anim_while_run_dyn_setting(is_checked)

    def __set_animation(self, is_animation_on: bool):
        """
        Slot called when run time animation is changed by user outside main menu.
        :param is_animation_on: Boolean indicating whether or not animation is on.
        """
        self.__anim_action.setChecked(is_animation_on)

    __slot_on_state_changed = safe_slot(__on_state_changed)
    __slot_start_simulation = safe_slot(__start_simulation)
    __slot_pause_resume = safe_slot(__pause_resume)
    __slot_on_step = safe_slot(__on_step)
    __slot_on_reset = safe_slot(__on_reset)
    __slot_on_debug_mode_changed = safe_slot(__on_debug_mode_changed)
    __slot_on_user_toggled_debug_mode = safe_slot(__on_user_toggled_debug_mode)
    __slot_on_runtime_anim_changed = safe_slot(__on_runtime_anim_changed)
    __slot_set_animation = safe_slot(__set_animation)
