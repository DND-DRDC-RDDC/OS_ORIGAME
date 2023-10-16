# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module is used to set up the Main Simulation Control and Status module and its
related behaviour.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import weakref
import random
from enum import IntEnum, unique
from inspect import signature

# [2. third-party]
from PyQt5.QtCore import pyqtSignal, QSize, QObject
from PyQt5.QtWidgets import QWidget, QMessageBox, QDialog, QDialogButtonBox
from PyQt5.Qt import Qt
from PyQt5.QtGui import QIcon

# [3. local]
from ....core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ....core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ....core import override
from ....scenario import Scenario, ScenarioManager, SimStatesEnum as MainSimStatesEnum, SimController
from ....scenario.sim_controller import MIN_RAND_SEED, MAX_RAND_SEED
from ....scenario import check_seed, new_seed
from ....scenario.defn_parts import RunRolesEnum

from ...slow_tasks import get_progress_bar
from ...gui_utils import exec_modal_dialog, IScenarioMonitor, set_button_image, get_icon_path
from ...call_params import CallArgs
from ...safe_slot import safe_slot
from ...async_methods import AsyncRequest, AsyncErrorInfo
from ...conversions import convert_string_to_float, convert_time_components_to_days, SECONDS_PER_DAY
from ...conversions import convert_seconds_to_string, convert_float_days_to_string, convert_days_to_time_components
from ...Ui_mainwindow import Ui_MainWindow

from ..common import SimDialog

from .main_simulation_settings import MainSimulationSettingsDialog
from .Ui_main_sim_control_status import Ui_MainSimulationControlWidget
from .Ui_edit_time_dialog import Ui_EditTimeDialog
from .Ui_edit_seed_dialog import Ui_EditSeedDialog
from .run_setup_parts import RunSetupPartsDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'MainSimulationControlPanel',
    'MainSimSharedButtonStates'
]

log = logging.getLogger('system')

VALID_COLOR = "rgba(0, 255, 0, 160)"
INVALID_COLOR = "rgba(255, 0, 0, 160)"
PLAY_PAUSE_BUTTON_SIZE = QSize(40, 50)

# A list of function part's id, path, and signature
SignatureInfo = List[Tuple[int, str, signature]]


# -- Class Definitions --------------------------------------------------------------------------


class EditTimeDialog(SimDialog):
    """Implements a dialog for editing time parameters"""

    @unique
    class TimeDialogTypeEnum(IntEnum):
        """Enumeration of time dialog types"""
        edit_max_sim_time_dialog, edit_max_wall_clock_time_dialog = range(2)

    def __init__(self, sim_controller: SimController, time_dialog_type: TimeDialogTypeEnum, parent: QWidget = None):
        super().__init__(parent)
        self.ui = Ui_EditTimeDialog()
        self.ui.setupUi(self)
        self.__sim_controller = sim_controller
        self.__time_dialog_type = time_dialog_type

        def get_max_sim_time_backend() -> float:
            """Get the max sim time from the sim controller."""
            return self.__sim_controller.max_sim_time_days

        def get_max_wall_clock_time_backend() -> float:
            """Get the max wall clock time from the sim controller."""
            return self.__sim_controller.max_wall_clock_sec

        def init_ui_dialog(time: float):
            """
            Init the time dialog with 'time' value from sim controller.
            If time is None, time is reset to zero.
            """
            if time is not None:
                if self.__time_dialog_type == self.TimeDialogTypeEnum.edit_max_wall_clock_time_dialog:
                    # If time is seconds, conver to days
                    time /= SECONDS_PER_DAY  # [sec] -> [days]

                days, hours, minutes, seconds = convert_days_to_time_components(time)
            else:
                days, hours, minutes, seconds = (0, 0, 0, 0)

            self.ui.days_spinbox.setValue(days)
            self.ui.hours_spinbox.setValue(hours)
            self.ui.minutes_spinbox.setValue(minutes)
            self.ui.seconds_spinbox.setValue(seconds)

        if self.__time_dialog_type.value == self.TimeDialogTypeEnum.edit_max_sim_time_dialog:
            self.setWindowTitle("Edit Simulation Stop Time")
            AsyncRequest.call(get_max_sim_time_backend, response_cb=init_ui_dialog)
        else:
            self.setWindowTitle("Edit Wall Clock Stop Time")
            AsyncRequest.call(get_max_wall_clock_time_backend, response_cb=init_ui_dialog)

    @override(QDialog)
    def accept(self):
        """Override to get the dialog values and set them in the backend before closing the dialog"""

        days = self.ui.days_spinbox.value()
        hours = self.ui.hours_spinbox.value()
        minutes = self.ui.minutes_spinbox.value()
        seconds = self.ui.seconds_spinbox.value()

        # Generate single floating point time value
        if (days, hours, minutes, seconds) == (0, 0, 0, 0):
            time_in_days = None  # Remove the stop time
        else:
            time_in_days = convert_time_components_to_days(days, hours, minutes, seconds)

        def set_max_sim_time_backend(time_days: float):
            """Set the max_sim_time_days value in the sim controller."""
            self.__sim_controller.set_max_sim_time_days(time_days)

        def set_max_wall_clock_time_backend(time_secs: float):
            """Set the max_wall_clock_sec value in the sim controller."""
            self.__sim_controller.set_max_wall_clock_sec(time_secs)

        # Convert time value (if required) and set in backend
        if self.__time_dialog_type.value == self.TimeDialogTypeEnum.edit_max_sim_time_dialog:
            AsyncRequest.call(set_max_sim_time_backend, time_in_days)
        else:
            time_in_secs = time_in_days * SECONDS_PER_DAY if time_in_days is not None else None  # [days] -> [secs]
            AsyncRequest.call(set_max_wall_clock_time_backend, time_in_secs)

        super().accept()


class EditSeedDialog(SimDialog):
    """Implements a dialog for setting the seed"""

    # --------------------------- class-wide data and signals -----------------------------------

    VALID_STYLE_SHEET = "QLineEdit { background-color: " + VALID_COLOR + "; }"
    INVALID_STYLE_SHEET = "QLineEdit { background-color: " + INVALID_COLOR + "; }"

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, sim_controller: SimController, seed: int = None, use_reset_seed: bool = False,
                 parent: QWidget = None):
        """
        Initialize the edit seed dialog.
        :param sim_controller: The backend sim controller.
        :param seed: The seed last set by the user (None if not previously set).
        :param use_reset_seed: The 'use reset seed' option last selected by the user (False if not previously set).
        :param parent: The parent widget of the dialog.
        """
        super().__init__(parent)
        self.ui = Ui_EditSeedDialog()
        self.ui.setupUi(self)

        instructions = ("Enter a seed value in the range {} <= integer <= {} for the scenario's random number "
                        "generator.\n\nClick OK to apply it, or Cancel to abondon this operation."
                        .format(MIN_RAND_SEED, MAX_RAND_SEED))

        self.ui.instructions_label.setText(instructions)
        self.ui.seed_linedit.textChanged.connect(self.__slot_check_seed_value)
        self.ui.use_reset_seed_checkbox.clicked.connect(self.__slot_on_use_reset_seed_checked)
        self.ui.generate_button.clicked.connect(self.__slot_on_generate_button_clicked)

        self.__sim_controller = sim_controller
        self.__seed = None
        self.__use_reset_seed = False

        # Disable OK until a verified seed has been entered
        ok_button = self.ui.buttonBox.button(QDialogButtonBox.Ok)
        ok_button.setEnabled(False)

        if use_reset_seed:
            # Configure dialog with the reset seed
            self.ui.use_reset_seed_checkbox.setChecked(True)
            self.__on_use_reset_seed_checked()
        elif seed is not None:
            # Non-reset seed was specified
            self.ui.seed_linedit.setText(str(seed))
        else:
            # no seed previously set
            pass

        if sim_controller.settings.reset_seed is None:
            self.ui.use_reset_seed_checkbox.setEnabled(False)

    @override(QDialog)
    def accept(self):
        """Override to get the dialog values and set them in the backend before closing the dialog"""

        self.__use_reset_seed = self.ui.use_reset_seed_checkbox.isChecked()
        self.__seed = int(self.ui.seed_linedit.text())
        random.seed(self.__seed)
        log.info("Setting random seed {}.", self.__seed)
        super().accept()

    def get_user_input(self) -> Tuple[int, bool]:
        """
        OGet the input from the dialog.
        :return: A tuple of user input.
        """
        assert self.__seed is not None
        return self.__seed, self.__use_reset_seed

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __check_seed_value(self, seed: str):
        """
        Check that the seed value has been defined correctly.
        :param seed: A string from the dialog's line edit containing the user-specified seed.
        """

        ok_button = self.ui.buttonBox.button(QDialogButtonBox.Ok)

        try:
            seed = int(seed)
            if check_seed(seed):
                ok_button.setEnabled(True)
                self.ui.seed_linedit.setStyleSheet(self.VALID_STYLE_SHEET)

        except ValueError:
            # Prevent dialog from setting the random seed
            ok_button.setEnabled(False)
            self.ui.seed_linedit.setStyleSheet(self.INVALID_STYLE_SHEET)

        if seed == '' or self.ui.use_reset_seed_checkbox.isChecked():
            # Clear the background color
            self.ui.seed_linedit.setStyleSheet('')

    def __on_use_reset_seed_checked(self):
        """Called when the Use Reset Seed checkbox is checked"""

        if self.ui.use_reset_seed_checkbox.isChecked():

            def get_reset_seed_backend() -> int:
                return self.__sim_controller.settings.reset_seed

            def on_receive_reset_seed(seed: int):
                self.ui.seed_linedit.setText(str(seed or ''))  # seed can be None
                self.ui.seed_linedit.setEnabled(False)
                self.ui.generate_button.setEnabled(False)

            AsyncRequest.call(get_reset_seed_backend, response_cb=on_receive_reset_seed)

        else:
            self.ui.seed_linedit.setEnabled(True)
            self.ui.generate_button.setEnabled(True)
            self.ui.seed_linedit.setStyleSheet(self.VALID_STYLE_SHEET)

    def __on_generate_button_clicked(self):
        """Called when the Generate button is clicked"""
        self.ui.seed_linedit.setText(str(new_seed()))

    __slot_check_seed_value = safe_slot(__check_seed_value)
    __slot_on_use_reset_seed_checked = safe_slot(__on_use_reset_seed_checked)
    __slot_on_generate_button_clicked = safe_slot(__on_generate_button_clicked)


class MainSimulationControlPanel(IScenarioMonitor, QWidget):
    """
    This class contains the logic related to displaying the contents of the Main Simulation Control Panel.
    It also contains logic that determines the behaviour of the controls within the panel.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    BLACK_STYLE_SHEET = "QLabel { color: black; }"
    GREEN_STYLE_SHEET = "QLabel { color: green; }"
    AMBER_STYLE_SHEET = "QLabel { color: rgb(235, 181, 18); }"

    sig_clear_event_queue = pyqtSignal()

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, scenario_manager: ScenarioManager, parent=None):
        QWidget.__init__(self, parent)
        IScenarioMonitor.__init__(self, scenario_manager)

        self.ui = Ui_MainSimulationControlWidget()
        self.ui.setupUi(self)
        self.ui.max_sim_time_label.setText('')
        self.ui.max_wall_clock_time_label.setText('')

        self.ui.main_sim_settings_toolbutton.clicked.connect(self.slot_on_settings_button_clicked)
        self.ui.edit_sim_stop_time_toolbutton.clicked.connect(self.__slot_on_edit_sim_stop_time_clicked)
        self.ui.edit_wall_clock_stop_time_toolbutton.clicked.connect(self.__slot_on_edit_wall_clock_stop_time_clicked)
        self.ui.set_seed_button.clicked.connect(self.__slot_on_set_seed_button_clicked)
        self.ui.reset_sim_time_toolbutton.clicked.connect(self.__slot_on_reset_sim_time_clicked)
        self.ui.reset_wall_clock_time_toolbutton.clicked.connect(self.__slot_on_reset_wall_clock_time_clicked)

        self.ui.animation_checkbox.clicked.connect(self.__slot_on_animation_checkbox_clicked)
        self.ui.debug_checkbox.clicked.connect(self.__slot_on_debug_checkbox_clicked)
        self.ui.clear_events_toolbutton.clicked.connect(self.__slot_on_clear_queue_button_clicked)
        self.ui.run_sim_toolbutton.clicked.connect(self.__slot_on_run_sim_button_clicked)
        self.ui.reset_sim_toolbutton.clicked.connect(self.__slot_on_reset_button_clicked)
        self.ui.start_sim_toolbutton.clicked.connect(self.__slot_on_start_sim_button_clicked)
        self.ui.end_sim_toolbutton.clicked.connect(self.__slot_on_end_sim_button_clicked)
        self.ui.play_pause_sim_toolbutton.clicked.connect(self.__slot_on_pause_resume_button_clicked)
        self.ui.step_sim_toolbutton.clicked.connect(self.__slot_on_step_button_clicked)
        self.ui.run_setup_parts_toolbutton.clicked.connect(self.__slot_on_run_setup_parts_clicked)
        self.ui.run_reset_parts_toolbutton.clicked.connect(self.__slot_on_run_reset_parts_clicked)
        self.ui.run_startup_parts_toolbutton.clicked.connect(self.__slot_on_run_startup_parts_clicked)
        self.ui.run_finish_parts_toolbutton.clicked.connect(self.__slot_on_run_finish_parts_clicked)

        self.__dialog_seed = None
        self.__dialog_use_reset_seed = None

        self.__sim_controller = None
        self.__scenario_weak = None

        self.__main_sim_shared_button_states = MainSimSharedButtonStates(self.ui)

        self.__enable_setup_parts_button = False
        self.__enable_reset_parts_button = False
        self.__enable_startup_parts_button = False
        self.__enable_finish_parts_button = False

        self._monitor_scenario_replacement()

        self.__run_setup_parts_dialog = RunSetupPartsDialog(data_ready=self.__on_setup_input_ready)

    @property
    def main_sim_shared_button_states(self):
        return self.__main_sim_shared_button_states

    def on_settings_button_clicked(self):
        """
        Method called when the Settings button is clicked.
        """
        main_settings = MainSimulationSettingsDialog(self.__sim_controller)
        main_settings.exec()

    def on_edit_seed_dialog_closed(self, seed: int, use_reset_seed: bool):
        """Save values from the Edit Seed dialog"""
        self.__dialog_seed = seed
        self.__dialog_use_reset_seed = use_reset_seed

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_settings_button_clicked = safe_slot(on_settings_button_clicked)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        """
        Method called when the scenario is replaced.
        """

        if self.__scenario_weak is not None:
            old_scen = self.__scenario_weak()
            if old_scen is not None:
                old_scen.event_queue.signals.sig_queue_totals_changed.disconnect(self.__slot_update_panel_num_events)

        if self.__sim_controller is not None:
            sc_signals = self.__sim_controller.signals
            sc_signals.sig_state_changed.disconnect(self.__slot_update_panel_sim_state)
            sc_signals.sig_completion_percentage.disconnect(self.__slot_update_panel_percent_complete)
            sc_signals.sig_sim_time_days_changed.disconnect(self.__slot_update_panel_sim_time)
            sc_signals.sig_wall_clock_time_sec_changed.disconnect(self.__slot_update_panel_wall_clock_time)
            sc_signals.sig_max_sim_time_days_changed.disconnect(self.__slot_update_panel_sim_stop_time)
            sc_signals.sig_max_wall_clock_time_sec_changed.disconnect(self.__slot_update_panel_wall_clock_stop_time)
            sc_signals.sig_anim_while_run_dyn_setting_changed.disconnect(self.__slot_update_panel_animation)
            sc_signals.sig_debug_mode_changed.disconnect(self.__slot_update_panel_debug_mode)
            sc_signals.sig_has_role_parts.disconnect(self.__slot_enable_run_parts_with_role_buttons)
            sc_signals.sig_settings_changed.disconnect(self.__slot_update_settings_displayed)

        self.__scenario_weak = weakref.ref(scenario)
        scenario.event_queue.signals.sig_queue_totals_changed.connect(self.__slot_update_panel_num_events)

        self.__sim_controller = scenario.sim_controller
        sc_signals = self.__sim_controller.signals
        sc_signals.sig_state_changed.connect(self.__slot_update_panel_sim_state)
        sc_signals.sig_completion_percentage.connect(self.__slot_update_panel_percent_complete)
        sc_signals.sig_sim_time_days_changed.connect(self.__slot_update_panel_sim_time)
        sc_signals.sig_wall_clock_time_sec_changed.connect(self.__slot_update_panel_wall_clock_time)
        sc_signals.sig_max_sim_time_days_changed.connect(self.__slot_update_panel_sim_stop_time)
        sc_signals.sig_max_wall_clock_time_sec_changed.connect(self.__slot_update_panel_wall_clock_stop_time)
        sc_signals.sig_anim_while_run_dyn_setting_changed.connect(self.__slot_update_panel_animation)
        sc_signals.sig_debug_mode_changed.connect(self.__slot_update_panel_debug_mode)
        sc_signals.sig_has_role_parts.connect(self.__slot_enable_run_parts_with_role_buttons)
        sc_signals.sig_settings_changed.connect(self.__slot_update_settings_displayed)

        self.__init_sim_status()
        self.__update_buttons(self.__sim_controller.state_id)

    def __init_sim_status(self):
        """
        Set up initial labels.
        """
        assert self.__scenario_weak() is not None
        self.__update_panel_sim_state(self.__sim_controller.state_id)
        self.__update_panel_sim_time(self.__sim_controller.sim_time_days, None)
        self.__update_panel_animation(self.__sim_controller.settings.anim_while_run_dyn)
        self.__update_panel_debug_mode(self.__sim_controller.debug_mode)
        self.__update_panel_num_events(self.__sim_controller.num_events, 0)
        self.__update_panel_sim_stop_time(self.__sim_controller.max_sim_time_days)
        self.__update_panel_wall_clock_stop_time(self.__sim_controller.max_wall_clock_sec)

        self.__sim_controller.signals.sig_has_role_parts.connect(self.__slot_enable_run_parts_with_role_buttons)
        self.__enable_run_parts_with_role_buttons(RunRolesEnum.setup,
                                                  self.__sim_controller.has_role_parts(RunRolesEnum.setup))
        self.__enable_run_parts_with_role_buttons(RunRolesEnum.reset,
                                                  self.__sim_controller.has_role_parts(RunRolesEnum.reset))
        self.__enable_run_parts_with_role_buttons(RunRolesEnum.startup,
                                                  self.__sim_controller.has_role_parts(RunRolesEnum.startup))
        self.__enable_run_parts_with_role_buttons(RunRolesEnum.finish,
                                                  self.__sim_controller.has_role_parts(RunRolesEnum.finish))

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __update_buttons(self, sim_state: MainSimStatesEnum):
        """
        Enables or disables sim control related buttons when the sim state is changed.
        """
        self.__main_sim_shared_button_states.update_buttons(sim_state)
        if sim_state != MainSimStatesEnum.debugging:
            # Recover panel control after exiting debug mode
            self.__enable_all_controls(True)

        if sim_state == MainSimStatesEnum.running:

            self.ui.sim_state_label.setStyleSheet(self.GREEN_STYLE_SHEET)
            self.ui.percent_complete_label.setStyleSheet(self.GREEN_STYLE_SHEET)
            self.ui.complete_label.setStyleSheet(self.GREEN_STYLE_SHEET)

            self.ui.start_sim_toolbutton.setEnabled(False)
            self.ui.end_sim_toolbutton.setEnabled(True)
            self.ui.step_sim_toolbutton.setEnabled(False)

            self.ui.run_setup_parts_toolbutton.setEnabled(False)
            self.ui.run_reset_parts_toolbutton.setEnabled(False)
            self.ui.run_startup_parts_toolbutton.setEnabled(False)
            self.ui.run_finish_parts_toolbutton.setEnabled(False)

            self.ui.main_sim_settings_toolbutton.setEnabled(False)

        elif sim_state == MainSimStatesEnum.paused:

            self.ui.sim_state_label.setStyleSheet(self.AMBER_STYLE_SHEET)
            self.ui.percent_complete_label.setStyleSheet(self.AMBER_STYLE_SHEET)
            self.ui.complete_label.setStyleSheet(self.AMBER_STYLE_SHEET)

            self.ui.start_sim_toolbutton.setEnabled(True)
            self.ui.end_sim_toolbutton.setEnabled(False)
            self.ui.step_sim_toolbutton.setEnabled(True)

            self.ui.main_sim_settings_toolbutton.setEnabled(True)

            self.__enable_parts_with_roles()

        else:
            # Debugging
            self.__enable_all_controls(False)

    def __enable_all_controls(self, enable: bool):
        """Enable or disable all panel controls."""
        self.ui.edit_sim_stop_time_toolbutton.setEnabled(enable)
        self.ui.edit_wall_clock_stop_time_toolbutton.setEnabled(enable)
        self.ui.set_seed_button.setEnabled(enable)
        self.ui.animation_checkbox.setEnabled(enable)
        self.ui.debug_checkbox.setEnabled(enable)
        self.ui.reset_sim_time_toolbutton.setEnabled(enable)
        self.ui.reset_wall_clock_time_toolbutton.setEnabled(enable)
        self.ui.start_sim_toolbutton.setEnabled(enable)
        self.ui.end_sim_toolbutton.setEnabled(enable)
        self.ui.run_setup_parts_toolbutton.setEnabled(enable)
        self.ui.run_reset_parts_toolbutton.setEnabled(enable)
        self.ui.run_startup_parts_toolbutton.setEnabled(enable)
        self.ui.run_finish_parts_toolbutton.setEnabled(enable)

    def __update_panel_sim_state(self, state: MainSimStatesEnum):
        """
        Update the panel state when signalled by the Sim Controller.
        :param state: The state of the Main Simulation (running, paused, debugging)
        """
        state_name = MainSimStatesEnum(state).name.capitalize()
        self.ui.sim_state_label.setText(state_name)
        self.__update_buttons(state)

    def __update_panel_percent_complete(self, percent: int):
        """
        Update the panel percent complete when signalled by the Sim Controller.
        :param percent: The percentage of completion of the main simulation.
        """
        if percent == SimController.PERCENT_COMPLETE_UNDEFINED:
            # Do not display percent complete
            if self.ui.percent_complete_label.isVisible():
                self.ui.percent_complete_label.setVisible(False)
                self.ui.complete_label.setVisible(False)
        else:
            # Show the percent complete
            if not self.ui.percent_complete_label.isVisible():
                self.ui.percent_complete_label.setVisible(True)
                self.ui.complete_label.setVisible(True)

            self.ui.percent_complete_label.setText(str(percent) + '%')

    def __update_panel_sim_time(self, absolute_time: float, _: float):
        """
        Slot called when the sim time changes.
        :param absolute_time: The elapsed simulation time.
        """
        elapsed_time_as_string = convert_float_days_to_string(absolute_time)
        self.ui.sim_time_label.setText(elapsed_time_as_string)
        sim_stop_time = convert_string_to_float(self.ui.max_sim_time_label.text())
        self.__set_sim_stop_time_color(sim_stop_time)

    def __on_reset_sim_time_clicked(self):
        """Requests the Sim Controller to zero the elapsed simulation time."""
        msg = "The elapsed simulation time will be set to 0000 00:00:00.  Are you sure you wish to proceed?"
        if exec_modal_dialog("Zero Simulation Time", msg, icon=QMessageBox.Question) == QMessageBox.Yes:
            AsyncRequest.call(self.__sim_controller.reset_sim_time)

    def __update_panel_wall_clock_time(self, wall_clock_time: float):
        """
        Slot called when the wall clock time changes.
        :param wall_clock_time: The elapsed wall clock time.
        """
        elapsed_time_as_string = convert_seconds_to_string(int(wall_clock_time))
        self.ui.wall_clock_time_label.setText(elapsed_time_as_string)
        wall_clock_stop_time_days = convert_string_to_float(self.ui.max_sim_time_label.text())
        self.__set_wall_clock_stop_time_color(wall_clock_stop_time_days)

    def __on_reset_wall_clock_time_clicked(self):
        """Requests the Sim Controller to zero the elapsed wall clock time."""
        msg = "The elapsed wall clock time will be set to 0000 00:00:00.  Are you sure you wish to proceed?"
        if exec_modal_dialog("Zero Wall Clock Time", msg, icon=QMessageBox.Question) == QMessageBox.Yes:
            AsyncRequest.call(self.__sim_controller.reset_wall_clock_time)

    def __update_panel_num_events(self, num_scheduled: int, num_asap: int):
        """
        Slot called when the contents of the event queue changes.
        :param num_scheduled: The number of events scheduled to be processed ie non ASAP.
        :param num_asap: The number of ASAP events to be processed.
        """
        self.ui.number_of_events_label.setText(str(num_scheduled + num_asap))

    def __update_panel_sim_stop_time(self, max_sim_time_days: float):
        """
        Update the sim stop time when signalled by the Sim Controller.
        :param max_sim_time_days: The maximum simulation time in days to run the simulation.
        """
        if max_sim_time_days is not None and max_sim_time_days != 0.0:
            self.ui.max_sim_time_label.setText(convert_float_days_to_string(float(max_sim_time_days)))
        else:
            self.ui.max_sim_time_label.setText('')

        self.__set_sim_stop_time_color(max_sim_time_days)

    def __update_panel_wall_clock_stop_time(self, max_wall_clock_sec: float):
        """
        Update the wall clock stop time when signalled by the Sim Controller.
        :param max_wall_clock_sec: The maximum wall clock time in seconds to run the simulation.
        """
        if max_wall_clock_sec is not None and max_wall_clock_sec != 0.0:
            self.ui.max_wall_clock_time_label.setText(convert_seconds_to_string(int(max_wall_clock_sec)))
            wall_clock_stop_time_days = max_wall_clock_sec / SECONDS_PER_DAY
        else:
            self.ui.max_wall_clock_time_label.setText('')
            wall_clock_stop_time_days = None

        self.__set_wall_clock_stop_time_color(wall_clock_stop_time_days)

    def __on_animation_checkbox_clicked(self):
        """
        Method called when the Animation checkbox is clicked.
        """
        is_checked = self.ui.animation_checkbox.isChecked()
        AsyncRequest.call(self.__sim_controller.set_anim_while_run_dyn_setting, is_checked)

    def __update_panel_animation(self, is_animation_on: bool):
        """
        Update the Animation checkbox when signalled by the Sim Controller.
        :param is_animation_on: Boolean indicating whether or not animation is on.
        """
        self.ui.animation_checkbox.setChecked(is_animation_on)

    def __on_debug_checkbox_clicked(self):
        """
        Method called when the Debug checkbox is clicked.
        """
        is_checked = self.ui.debug_checkbox.isChecked()
        AsyncRequest.call(self.__sim_controller.set_debug_mode, is_checked)

    def __update_panel_debug_mode(self, state: bool):
        """
        Update the Debug mode checkbox when signalled by the Sim Controller.
        """
        self.ui.debug_checkbox.setChecked(state)

    def __on_clear_queue_button_clicked(self):
        """
        Method called when the Clear Queue button is clicked.
        """
        self.sig_clear_event_queue.emit()

    def __on_run_sim_button_clicked(self):
        """
        Method called when Run Simulation button is clicked.
        """
        scenario = self.__scenario_weak()
        if scenario is None:
            return

        def sim_run(has_changes: bool):
            if has_changes:
                msg = "Scenario has unsaved changes.  Are you sure you wish to start the simulation?"
                if exec_modal_dialog("Modified Scenario", msg, icon=QMessageBox.Question) == QMessageBox.No:
                    return

            AsyncRequest.call(self.__sim_controller.sim_run)

        AsyncRequest.call(scenario.has_ori_changes, response_cb=sim_run)

    def __on_reset_button_clicked(self):
        """
        Method called when the Reset button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.do_reset_steps)

    def __on_start_sim_button_clicked(self):
        """
        Method called when the Start button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.do_start_steps)

    def __on_end_sim_button_clicked(self):
        """
        Method called when End Simulation button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.do_end_steps)

    def __on_pause_resume_button_clicked(self):
        """
        Method called when the Pause/Resume button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.sim_pause_resume)

    def __on_step_button_clicked(self):
        """
        Method called when the Step button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.sim_step)

    def __prepare_run_setup_parts(self, signature_info: SignatureInfo):
        """
        Pops up a RunSetupPartsDialog to collect the user input. 
        :param signature_info: The info of part id, part path and its signature
        """
        self.__run_setup_parts_dialog.initialize_gui(signature_info)
        self.__run_setup_parts_dialog.exec()

    def __on_run_setup_parts_clicked(self):
        """
        Method called when the Run Setup Parts... button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.get_setup_parts_signature_info,
                          response_cb=self.__prepare_run_setup_parts)

    def __on_run_reset_parts_clicked(self):
        """
        Method called when the Run Reset Parts... button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.run_parts, RunRolesEnum.reset)

    def __on_run_startup_parts_clicked(self):
        """
        Method called when the Run Startup Parts... button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.run_parts, RunRolesEnum.startup)

    def __on_run_finish_parts_clicked(self):
        """
        Method called when the Run Finish Parts... button is clicked.
        """
        AsyncRequest.call(self.__sim_controller.run_parts, RunRolesEnum.finish)

    def __on_edit_sim_stop_time_clicked(self):
        """Opens a dialog to edit the simulation stop time"""
        dialog_type = EditTimeDialog.TimeDialogTypeEnum.edit_max_sim_time_dialog
        edit_sim_stop_time_dialog = EditTimeDialog(self.__sim_controller, dialog_type, parent=self)
        edit_sim_stop_time_dialog.exec()

    def __on_edit_wall_clock_stop_time_clicked(self):
        """Opens a dialog to edit the wall clock stop time"""
        dialog_type = EditTimeDialog.TimeDialogTypeEnum.edit_max_wall_clock_time_dialog
        edit_wall_clock_stop_time_dialog = EditTimeDialog(self.__sim_controller, dialog_type, parent=self)
        edit_wall_clock_stop_time_dialog.exec()

    def __on_set_seed_button_clicked(self):
        """Opens a dialog to set the seed value"""
        edit_seed_dialog = EditSeedDialog(self.__sim_controller, self.__dialog_seed, self.__dialog_use_reset_seed, self)
        answer = edit_seed_dialog.exec()
        if answer:
            seed, use_reset_seed = edit_seed_dialog.get_user_input()
            self.on_edit_seed_dialog_closed(seed, use_reset_seed)

    def __set_sim_stop_time_color(self, sim_stop_time_days: float):
        """Set the color of the Sim Stop Time in the panel: amber if sim time > stop time else black"""

        if sim_stop_time_days is None:
            return

        sim_time_days = convert_string_to_float(self.ui.sim_time_label.text())
        if sim_time_days >= sim_stop_time_days:
            self.ui.max_sim_time_label.setStyleSheet(self.AMBER_STYLE_SHEET)
        else:
            self.ui.max_sim_time_label.setStyleSheet(self.BLACK_STYLE_SHEET)

    def __set_wall_clock_stop_time_color(self, wall_clock_stop_time_days: float):
        """Set the color of the Wall Clock Stop Time in the panel: amber if wall clock time > stop time else black"""

        if wall_clock_stop_time_days is None:
            return

        wall_clock_time_days = convert_string_to_float(self.ui.wall_clock_time_label.text())
        if wall_clock_time_days >= wall_clock_stop_time_days:
            self.ui.wall_clock_time_label.setStyleSheet(self.AMBER_STYLE_SHEET)
        else:
            self.ui.wall_clock_time_label.setStyleSheet(self.BLACK_STYLE_SHEET)

    def __enable_run_parts_with_role_buttons(self, run_role: int, has_parts: bool):
        """
        Set a flag that will enable or disable the "Run 'role' Parts..." button when the simulation is Paused.
        :param run_role: The run role to enable/disable.
        :param has_parts: A boolean indicating if there are any parts in the scenario of type run_role..
        """
        run_role = RunRolesEnum(run_role)

        if run_role == RunRolesEnum.setup:
            self.__enable_setup_parts_button = has_parts

        elif run_role == RunRolesEnum.reset:
            self.__enable_reset_parts_button = has_parts

        elif run_role == RunRolesEnum.startup:
            self.__enable_startup_parts_button = has_parts

        elif run_role == RunRolesEnum.finish:
            self.__enable_finish_parts_button = has_parts

        else:
            assert run_role == RunRolesEnum.batch

        if self.__sim_controller.state_id == MainSimStatesEnum.paused:
            self.__enable_parts_with_roles()

    def __enable_parts_with_roles(self):
        """
        Enable buttons to run parts with roles if the corresponding flag is True.
        """

        if self.__enable_setup_parts_button:
            self.ui.run_setup_parts_toolbutton.setEnabled(True)
        else:
            self.ui.run_setup_parts_toolbutton.setEnabled(False)

        if self.__enable_reset_parts_button:
            self.ui.run_reset_parts_toolbutton.setEnabled(True)
        else:
            self.ui.run_reset_parts_toolbutton.setEnabled(False)

        if self.__enable_startup_parts_button:
            self.ui.run_startup_parts_toolbutton.setEnabled(True)
        else:
            self.ui.run_startup_parts_toolbutton.setEnabled(False)

        if self.__enable_finish_parts_button:
            self.ui.run_finish_parts_toolbutton.setEnabled(True)
        else:
            self.ui.run_finish_parts_toolbutton.setEnabled(False)

    def __update_settings_displayed(self):
        """Update the settings displayed in the Status Panel"""

        max_sim_time_days = self.__sim_controller.settings.sim_steps.end.max_sim_time_days
        max_wall_clock_sec = self.__sim_controller.settings.sim_steps.end.max_wall_clock_sec

        self.__update_panel_sim_stop_time(max_sim_time_days)
        self.__update_panel_wall_clock_stop_time(max_wall_clock_sec)

    def __on_setup_input_ready(self, call_args_dict: CallArgs):
        """
        This is a call-back function for the RunSetupPartsDialog.
        
        After the user clicks OK button, this function sends the collected information from the dialog to
        the backend to run the parts. 

        If the execution has errors, the RunSetupPartsDialog will stay open until the user cancels it or re-runs
        succeed eventually.
        :param call_args_dict: The user input on the dialog
        """
        def __on_run_setup_parts_completed():
            get_progress_bar().stop_progress()
            exec_modal_dialog("Success", "All Setup parts have been run successfully.", QMessageBox.Information)
            self.__run_setup_parts_dialog.done(QDialog.Accepted)

        def __on_run_setup_parts_failed(error_info: AsyncErrorInfo):
            get_progress_bar().stop_progress()
            # The GUI (RunSetupPartsDialog) does not need to know the BasePart concept. The int (part id) is
            # enough.
            map_id_to_error = {part.SESSION_ID: error for part, error in error_info.exc.map_part_to_exc_str.items()}
            self.__run_setup_parts_dialog.set_exec_errors(map_id_to_error)
            exec_modal_dialog("Failure",
                              ("At least one Setup part failed to run successfully. "
                               "Click OK to try again (fix the argument values) or click Cancel to abort the run."),
                              QMessageBox.Critical,
                              detailed_message=error_info.traceback)

        get_progress_bar().start_busy_progress("Run Setup Parts...")
        AsyncRequest.call(self.__sim_controller.run_parts,
                          RunRolesEnum.setup,
                          call_args_dict,
                          response_cb=__on_run_setup_parts_completed,
                          error_cb=__on_run_setup_parts_failed)

    __slot_update_panel_sim_state = safe_slot(__update_panel_sim_state)
    __slot_update_panel_percent_complete = safe_slot(__update_panel_percent_complete)
    __slot_update_panel_sim_time = safe_slot(__update_panel_sim_time)
    __slot_update_panel_wall_clock_time = safe_slot(__update_panel_wall_clock_time)
    __slot_update_panel_num_events = safe_slot(__update_panel_num_events)

    __slot_update_panel_sim_stop_time = safe_slot(__update_panel_sim_stop_time)
    __slot_update_panel_wall_clock_stop_time = safe_slot(__update_panel_wall_clock_stop_time)

    __slot_on_animation_checkbox_clicked = safe_slot(__on_animation_checkbox_clicked)
    __slot_update_panel_animation = safe_slot(__update_panel_animation)
    __slot_on_debug_checkbox_clicked = safe_slot(__on_debug_checkbox_clicked)
    __slot_update_panel_debug_mode = safe_slot(__update_panel_debug_mode)

    __slot_on_clear_queue_button_clicked = safe_slot(__on_clear_queue_button_clicked)

    __slot_on_run_sim_button_clicked = safe_slot(__on_run_sim_button_clicked)
    __slot_on_reset_button_clicked = safe_slot(__on_reset_button_clicked)
    __slot_on_start_sim_button_clicked = safe_slot(__on_start_sim_button_clicked)
    __slot_on_end_sim_button_clicked = safe_slot(__on_end_sim_button_clicked)
    __slot_on_pause_resume_button_clicked = safe_slot(__on_pause_resume_button_clicked)
    __slot_on_step_button_clicked = safe_slot(__on_step_button_clicked)

    __slot_on_run_setup_parts_clicked = safe_slot(__on_run_setup_parts_clicked)
    __slot_on_run_reset_parts_clicked = safe_slot(__on_run_reset_parts_clicked)
    __slot_on_run_startup_parts_clicked = safe_slot(__on_run_startup_parts_clicked)
    __slot_on_run_finish_parts_clicked = safe_slot(__on_run_finish_parts_clicked)

    __slot_on_edit_sim_stop_time_clicked = safe_slot(__on_edit_sim_stop_time_clicked)
    __slot_on_edit_wall_clock_stop_time_clicked = safe_slot(__on_edit_wall_clock_stop_time_clicked)
    __slot_on_set_seed_button_clicked = safe_slot(__on_set_seed_button_clicked)
    __slot_on_reset_sim_time_clicked = safe_slot(__on_reset_sim_time_clicked)
    __slot_on_reset_wall_clock_time_clicked = safe_slot(__on_reset_wall_clock_time_clicked)
    __slot_enable_run_parts_with_role_buttons = safe_slot(__enable_run_parts_with_role_buttons)
    __slot_update_settings_displayed = safe_slot(__update_settings_displayed)


class MainSimSharedButtonStates(QObject):
    """
    Convenience class encapsulates the shared states of the buttons that belong to loosely coupled ui components,
    i.e., those on the main win and those on the Main Sim Control Panel.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, ui_main_sim_control: Ui_MainSimulationControlWidget):
        """
        The states of the controls on the ui_main_sim_control are managed in this class.
        :param ui_main_sim_control: The ui class of the main sim control panel.
        """
        QObject.__init__(self)
        self.__ui_main_sim_control = ui_main_sim_control
        self.__ui_main_win = None
        self.__enable_clear_queue = False
        self.__sim_state = None

    def set_ui_main_win(self, ui_main_win: Ui_MainWindow):
        """
        Sets ui_main_win to this class so that its states are managed to be consistent with the ui_main_sim_control
        passed to this class in the constructor.
        :param ui_main_win: The ui class of the main window.
        """
        self.__ui_main_win = ui_main_win

    def on_enable_clear_event_queue(self, enable: bool):
        """
        The slot to enable or disable Clear Queue buttons.
        """
        self.__enable_clear_queue = enable
        is_enabled = enable and self.__sim_state != MainSimStatesEnum.debugging
        self.__ui_main_sim_control.clear_events_toolbutton.setEnabled(is_enabled)
        self.__ui_main_win.action_clear_events.setEnabled(is_enabled)

    def update_buttons(self, sim_state: MainSimStatesEnum):
        """
        Enables or disables buttons when the sim state is changed.
        """
        self.__sim_state = sim_state
        if sim_state != MainSimStatesEnum.debugging:
            # Recover panel control after exiting debug mode
            self.__enable_all_controls(True)

        if sim_state == MainSimStatesEnum.running:
            path_to_image = get_icon_path("button_pausesim.svg")
            set_button_image(self.__ui_main_sim_control.play_pause_sim_toolbutton,
                             str(path_to_image), size=PLAY_PAUSE_BUTTON_SIZE,
                             text='Pause', style=Qt.ToolButtonTextUnderIcon)
            self.__ui_main_win.action_play_pause_sim.setText('Pause')
            self.__ui_main_win.action_play_pause_sim.setIcon(QIcon(get_icon_path("pause.png")))

            self.__ui_main_sim_control.run_sim_toolbutton.setEnabled(False)
            self.__ui_main_win.action_run_sim.setEnabled(False)

            self.__ui_main_sim_control.step_sim_toolbutton.setEnabled(False)
            self.__ui_main_win.action_step_sim.setEnabled(False)

            self.__ui_main_sim_control.main_sim_settings_toolbutton.setEnabled(False)
            self.__ui_main_win.action_main_sim_settings.setEnabled(False)

        elif sim_state == MainSimStatesEnum.paused:
            path_to_image = get_icon_path("button_playsim.svg")
            set_button_image(self.__ui_main_sim_control.play_pause_sim_toolbutton,
                             str(path_to_image), size=PLAY_PAUSE_BUTTON_SIZE,
                             text='Play', style=Qt.ToolButtonTextUnderIcon)
            self.__ui_main_win.action_play_pause_sim.setText('Play')
            self.__ui_main_win.action_play_pause_sim.setIcon(QIcon(get_icon_path("play.png")))

        else:
            # Debugging
            assert sim_state == MainSimStatesEnum.debugging
            self.__enable_all_controls(False)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_enable_clear_event_queue = safe_slot(on_enable_clear_event_queue)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __enable_all_controls(self, enable: bool):
        """
        Enable or disable all controls on the sim control panel and the main window menu.
        :param enable: True to enable them; otherwise, to disable them.
        """
        self.__ui_main_sim_control.clear_events_toolbutton.setEnabled(enable and self.__enable_clear_queue)
        self.__ui_main_win.action_clear_events.setEnabled(enable and self.__enable_clear_queue)

        self.__ui_main_sim_control.run_sim_toolbutton.setEnabled(enable)
        self.__ui_main_win.action_run_sim.setEnabled(enable)

        self.__ui_main_sim_control.reset_sim_toolbutton.setEnabled(enable)
        self.__ui_main_win.action_reset_sim.setEnabled(enable)

        self.__ui_main_sim_control.play_pause_sim_toolbutton.setEnabled(enable)
        self.__ui_main_win.action_play_pause_sim.setEnabled(enable)

        self.__ui_main_sim_control.step_sim_toolbutton.setEnabled(enable)
        self.__ui_main_win.action_step_sim.setEnabled(enable)

        self.__ui_main_sim_control.main_sim_settings_toolbutton.setEnabled(enable)
        self.__ui_main_win.action_main_sim_settings.setEnabled(enable)

