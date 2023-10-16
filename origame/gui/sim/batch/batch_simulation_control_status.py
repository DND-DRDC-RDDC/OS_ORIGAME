# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module is used to set up the Batch Simulation Control and Status panel and its related
 behaviour.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import weakref
import os
from datetime import timedelta
from pathlib import Path
import subprocess
import sys

# [2. third-party]
from PyQt5.QtCore import QCoreApplication, QSize
from PyQt5.QtWidgets import QWidget, QMessageBox
from PyQt5.Qt import Qt

# [3. local]
from ....core import override
from ....core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ....core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ....scenario import ScenarioManager, Scenario
from ....batch_sim import BatchSimManager, BsmStatesEnum, BatchDoneStatusEnum, BatchSimSettings
from ....gui.menu_commands import SaveAsCallable

from ...gui_utils import show_modal_dialog, exec_modal_dialog, get_icon_path, set_button_image
from ...actions_utils import get_batch_folders
from ...safe_slot import safe_slot, ext_safe_slot
from ...gui_utils import IScenarioMonitor
from ...async_methods import AsyncRequest

from .Ui_batch_simulation_control_status import Ui_BatchSimulationControlWidget
from .batch_simulation_settings import BatchSimulationSettingsDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'BatchSimulationControlPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------


class BatchSimulationControlPanel(IScenarioMonitor, QWidget):
    """
    This class contains the logic related to displaying the contents of the Batch Simulation Control Panel.
    It also contains logic that determines the behaviour of the controls within the panel.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    BLACK_STYLE_SHEET = "QLabel { color: black; }"
    GREEN_STYLE_SHEET = "QLabel { color: green; }"
    AMBER_STYLE_SHEET = "QLabel { color: rgb(235, 181, 18); }"
    BLUE_STYLE_SHEET = "QLabel { color: blue; }"
    RED_STYLE_SHEET = "QLabel { color: red; }"

    # The selected batch folder if self.__batch_sim_manager.scen_path is not None and,
    # there are batch folders in the location of self.__batch_sim_manager.scen_path
    selected_batch_folder = None

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, batch_sim_manager: BatchSimManager,
                 scenario_manager: ScenarioManager,
                 save_scen_callback: SaveAsCallable,
                 parent=None):
        """
        Initialize the batch simulation control panel.
        :param batch_sim_manager:  The batch simulation manager.
        :param scenario_manager: The scenario manager.
        :param save_scen_callback: A callback used to save the scenario if the scenario folder does not exist.
        :param parent: The parent widget of the panel.
        """
        QWidget.__init__(self, parent)
        IScenarioMonitor.__init__(self, scenario_manager)
        self.ui = Ui_BatchSimulationControlWidget()
        self.ui.setupUi(self)

        self.__batch_sim_manager = batch_sim_manager
        self.__save_scen_callback = save_scen_callback
        self.__scenario_weak = None

        self.ui.batch_settings_toolbutton.clicked.connect(self.slot_on_action_open_settings)
        self.ui.run_abort_new_toolbutton.clicked.connect(self.__slot_on_action_run_abort_new)
        self.ui.play_pause_toolbutton.clicked.connect(self.__slot_on_action_play_pause)
        self.ui.variants_spinbox.valueChanged.connect(self.__slot_on_action_variant_changed)
        self.ui.reps_per_variant_spinbox.valueChanged.connect(self.__slot_on_action_replics_changed)
        self.ui.use_cores_spindbox.valueChanged.connect(self.__slot_on_action_num_cores_changed)
        self.ui.open_batch_folder_button.clicked.connect(self.__slot_on_action_open_batch_folder)
        self.ui.batch_folder_combobox.activated.connect(self.__slot_on_update_batch_combobox_display)

        self.__batch_sim_manager.signals.sig_scen_path_changed.connect(self.__slot_on_scen_path_changed)
        self.__batch_sim_manager.signals.sig_state_changed.connect(self.__slot_on_batch_state_changed)
        self.__batch_sim_manager.signals.sig_replication_done.connect(self.__slot_on_replication_done)
        self.__batch_sim_manager.signals.sig_replication_error.connect(self.__slot_on_replication_error)
        self.__batch_sim_manager.signals.sig_batch_folder_changed.connect(self.__slot_on_batch_folder_changed)
        self.__batch_sim_manager.signals.sig_time_stats_changed.connect(self.__slot_on_batch_time_stats_changed)

        self.__display_batch_settings()
        self._monitor_scenario_replacement()
        self.__on_update_batch_combobox(None)

    def on_action_open_settings(self):
        """
        Open the Batch Settings dialog.
        """
        batch_settings = BatchSimulationSettingsDialog(self.__batch_sim_manager)
        batch_settings.finished.connect(self.__slot_display_batch_sim_settings)
        batch_settings.exec()

    def apply_settings(self) -> bool:
        """
        Apply the changed settings from the Batch Simulation Control Panel to the Batch Simulation Manager.
        :returns: A boolean indicating if the settings were applied successfully.
        """
        settings = self.__batch_sim_manager.settings.get_settings_dict()
        if settings:
            assert len(settings) > 0
            # Update only the variables that can be changed from the Batch Simulation Control Panel
            settings.update({
                'num_variants': self.__batch_sim_manager.num_variants,
                'num_replics_per_variant': self.__batch_sim_manager.num_replics_per_variant,
                'num_cores_wanted': self.__batch_sim_manager.num_cores_wanted
            })
            self.__batch_sim_manager.set_settings(BatchSimSettings(**settings))

        return len(settings) > 0  # evaluates to True if settings are populated

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_action_open_settings = safe_slot(on_action_open_settings)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        if self.__batch_sim_manager.state_id == BsmStatesEnum.done:
            self.__batch_sim_manager.new_batch()
        self.__scenario_weak = weakref.ref(scenario)
        self.__update_panel_batch_ready()
        self.__display_batch_settings()

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __display_batch_settings(self):
        """
        Show the batch settings in the status section of the control panel.
        """
        variants = self.__batch_sim_manager.settings.num_variants
        reps_per_variant = self.__batch_sim_manager.settings.num_replics_per_variant
        cores = self.__batch_sim_manager.settings.num_cores_wanted

        self.ui.variants_spinbox.setValue(variants)
        self.ui.reps_per_variant_spinbox.setValue(reps_per_variant)
        self.ui.use_cores_spindbox.setValue(cores)
        num_cores_available = self.__batch_sim_manager.num_cores_available
        self.ui.cores_available_label.setText('/ {}'.format(num_cores_available))

        # enable or disable panel variant/replication spin boxes to correspond with auto-seed:
        # if auto-seed is disabled, shortcut fields are disabled so user must use settings dialog to
        # generate corresponding seeds to fit dims of seed table
        auto_seed_enabled = self.__batch_sim_manager.settings.auto_seed
        self.ui.variants_spinbox.setEnabled(auto_seed_enabled)
        self.ui.reps_per_variant_spinbox.setEnabled(auto_seed_enabled)

    def __on_scen_saved_run_batch(self, save_success: bool):
        """
        Run a batch simulation if the scenario was saved successfully.
        :param save_success: A flag indicating if the save was successful.
        """
        if save_success:
            self.__run_batch(has_changes=False)

    def __on_update_batch_combobox(self, combo_index: int):
        batch_combobox = self.ui.batch_folder_combobox
        open_button = self.ui.open_batch_folder_button

        batch_combobox.clear()
        open_button.setEnabled(False)
        self.selected_batch_folder = None

        if self.__batch_sim_manager.scen_path:
            batch_folders = get_batch_folders(os.path.dirname(str(self.__batch_sim_manager.scen_path)))

            for folder in batch_folders:
                batch_combobox.addItem(os.path.basename(folder))

            # Combo index is set by selecting an item from the drop-down menu in the GUI
            if combo_index is not None:
                batch_combobox.setCurrentIndex(combo_index)
                self.selected_batch_folder = batch_folders[combo_index]
                open_button.setEnabled(True)

            # When loading a scenario or after running a new batch simulation, select the latest batch folder
            elif len(batch_folders) != 0:
                batch_combobox.setCurrentIndex(len(batch_folders)-1)
                self.selected_batch_folder = batch_folders[-1]
                open_button.setEnabled(True)

    # --------------------
    # Button-clicked slots

    def __on_action_run_abort_new(self):
        """
        User action to either Run, Abort, or set a New Batch Simulation.
        """

        scenario = self.__scenario_weak()
        if scenario is None:
            return

        batch_state = self.__batch_sim_manager.state_id

        if batch_state == BsmStatesEnum.ready:
            if self.__batch_sim_manager.scen_path is None:
                # Scenario folder has not been created -> prompt to save and then run
                msg_title = 'New Scenario'
                msg = 'Click Yes to save the scenario before running the batch, or Cancel to abandon the batch run.'
                if exec_modal_dialog(msg_title, msg, QMessageBox.Question,
                                     buttons=[QMessageBox.Ok, QMessageBox.Cancel]) == QMessageBox.Cancel:
                    return

                self.__save_scen_callback(self.__on_scen_saved_run_batch)
            else:
                # Scenario exits -> check for changes and then run
                AsyncRequest.call(scenario.has_ori_changes, response_cb=self.__run_batch)

        elif batch_state in (BsmStatesEnum.running, BsmStatesEnum.paused):
            self.__abort_batch()

        else:
            # New state
            assert batch_state == BsmStatesEnum.done
            self.__new_batch()

    def __run_batch(self, has_changes: bool):
        """
        Run the batch simulation.
        :param has_changes: A flag that indicates if the scenario has changes.
        """
        run = True
        if has_changes:
            msg = "Scenario has un-saved changes. Are you sure you wish to start a batch simulation?"
            if exec_modal_dialog("Run Batch Simulation", msg, QMessageBox.Question) == QMessageBox.No:
                run = False

        if run:
            self.setEnabled(False)  # Prevent the user from clicking buttons while starting batch...
            message = show_modal_dialog("Starting batch simulation, one moment...", "")
            QCoreApplication.processEvents()
            self.__batch_sim_manager.start_sim()
            message.close()
            self.setEnabled(True)

    def __abort_batch(self):
        """
        Abort the batch simulation.
        """
        abort = True
        msg = "Are you sure you want to abort the batch simulation?"
        if exec_modal_dialog("Abort Batch Simulation", msg, QMessageBox.Question) == QMessageBox.No:
            abort = False

        if abort and self.__batch_sim_manager.state_id == BsmStatesEnum.running:
            self.__batch_sim_manager.stop_sim()

    def __new_batch(self):
        """
        Configure a new batch simulation.
        """
        new = True
        msg = "Are you sure you want to configure a new batch simulation?"
        if exec_modal_dialog("New Batch Simulation", msg, QMessageBox.Question) == QMessageBox.No:
            new = False

        if new:
            self.__batch_sim_manager.new_batch()

    def __on_action_play_pause(self):
        """
        User action to Run/Pause the simulation.
        """
        if self.__batch_sim_manager.is_running():
            self.__batch_sim_manager.pause_sim()
        else:
            self.__batch_sim_manager.resume_sim()

    def __on_action_variant_changed(self, variants: int):
        """
        Update variant value in Batch Sim Settings when user edits spinbox value.
        """
        if variants != self.__batch_sim_manager.settings.num_variants:
            self.__batch_sim_manager.settings.num_variants = variants
            self.apply_settings()

    def __on_action_replics_changed(self, reps_per_variant: int):
        """
        Update replications per variant value in Batch Sim Settings when user edits spinbox value.
        """
        if reps_per_variant != self.__batch_sim_manager.settings.num_replics_per_variant:
            self.__batch_sim_manager.settings.num_replics_per_variant = reps_per_variant
            self.apply_settings()

    def __on_action_num_cores_changed(self, cores_wanted: int):
        """
        Update 'cores wanted' value in Batch Sim Settings when user edits spinbox value.
        """
        if cores_wanted != self.__batch_sim_manager.settings.num_cores_wanted:
            num_cores_available = self.__batch_sim_manager.num_cores_available
            if cores_wanted > num_cores_available:
                log.warning('The number of cores specified exceeds the number available. Setting to {}',
                            num_cores_available)
                self.ui.use_cores_spindbox.setValue(num_cores_available)
                self.__batch_sim_manager.settings.num_cores_wanted = num_cores_available
            else:
                self.__batch_sim_manager.settings.num_cores_wanted = cores_wanted
                self.apply_settings()

    # -----------------------
    # Batch Sim Manager slots

    def __on_scen_path_changed(self, path: str):
        """
        Called when the scenario path changes.
        Disable the panel if the path is None, otherwise, update it to the current batch state.
        """
        if path is None or path == '':
            self.ui.batch_state_label.setStyleSheet('')
            self.ui.percent_complete_label.setStyleSheet('')
            self.ui.complete_label.setStyleSheet('')
        else:
            self.__on_batch_state_changed(self.__batch_sim_manager.state_id.value)

        self.__on_update_batch_combobox(None)

    def __on_batch_state_changed(self, state: int):
        """
        Update the panel when the Batch State changes in the backend.
        """
        batch_state = BsmStatesEnum(state)

        if batch_state == BsmStatesEnum.ready:
            self.__update_panel_batch_ready()

        elif batch_state in (BsmStatesEnum.running, BsmStatesEnum.paused):

            if batch_state == BsmStatesEnum.running:
                self.__update_panel_running_state()
            else:
                self.__update_panel_paused_state()

        elif batch_state == BsmStatesEnum.done:
            completion_status = self.__batch_sim_manager.get_completion_status()

            if completion_status == BatchDoneStatusEnum.completed:
                self.__update_panel_complete_state()
            elif completion_status == BatchDoneStatusEnum.aborted:
                self.__update_panel_aborted_state()
            else:
                # not a handled completion status
                raise RuntimeError("An unhandled batch completion state was detected: {}"
                                   .format(completion_status.value))
        else:
            # State not handled -> should never get here
            raise RuntimeError("An unhandled batch state was detected: {}".format(batch_state.value))

    def __update_panel_batch_ready(self):
        """
        Sets panel buttons and labels to the 'ready' state.
        """
        self.ui.batch_state_label.setText("Ready")
        self.ui.batch_state_label.setStyleSheet(self.BLACK_STYLE_SHEET)
        self.ui.percent_complete_label.setText('0%')
        self.ui.percent_complete_label.setVisible(False)
        self.ui.complete_label.setVisible(False)

        path_to_image = get_icon_path("button_runbatch.svg")
        set_button_image(self.ui.run_abort_new_toolbutton, str(path_to_image), size=QSize(40, 50),
                         text='Run Batch\nSimulation', style=Qt.ToolButtonTextUnderIcon)

        path_to_image = get_icon_path("button_pausebatch.svg")
        set_button_image(self.ui.play_pause_toolbutton, str(path_to_image), size=QSize(40, 50),
                         text='Pause', style=Qt.ToolButtonTextUnderIcon)
        self.ui.play_pause_toolbutton.setEnabled(False)

        self.ui.batch_settings_toolbutton.setEnabled(True)

        self.ui.variants_spinbox.setEnabled(True)
        self.ui.reps_per_variant_spinbox.setEnabled(True)
        self.ui.use_cores_spindbox.setEnabled(True)

        self.ui.ave_time_per_rep_label.setText('-')
        self.ui.est_time_remaining_label.setText('-')
        self.ui.finished_reps_label.setText('-')
        self.ui.running_reps_label.setText('-')
        self.ui.failed_reps_label.setText('-')
        self.ui.finished_variants_label.setText('-')
        self.ui.failed_variants_label.setText('-')

        self.__display_batch_settings()

    def __update_panel_running_state(self):
        """
        Sets panel buttons and labels to the 'running' state.
        """
        self.ui.batch_state_label.setText("Running")
        style_sheet = self.GREEN_STYLE_SHEET
        path_to_pause_resume_image = get_icon_path("button_pausebatch.svg")
        button_text = 'Pause'
        self.__update_panel_running_paused_common(style_sheet, path_to_pause_resume_image, button_text)

    def __update_panel_paused_state(self):
        """
        Sets panel buttons and labels to the 'paused' state.
        """
        self.ui.batch_state_label.setText("Paused")
        style_sheet = self.AMBER_STYLE_SHEET
        path_to_pause_resume_image = get_icon_path("button_playbatch.svg")
        button_text = 'Resume'
        self.__update_panel_running_paused_common(style_sheet, path_to_pause_resume_image, button_text)

    def __update_panel_running_paused_common(self, style_sheet: str, path_to_pause_resume_image: str, button_text: str):
        """
        Common panel settings for the Running or Paused state.
        :param style_sheet: A style sheet for labels in the UI.
        :param path_to_pause_resume_image: A path to the image file for 'Resume' and 'Pause' icons.
        :param button_text: The text to set in the button: either 'Resume' or 'Pause'.
        """
        self.ui.batch_state_label.setStyleSheet(style_sheet)
        self.ui.percent_complete_label.setStyleSheet(style_sheet)
        self.ui.complete_label.setStyleSheet(style_sheet)
        self.ui.percent_complete_label.setVisible(True)
        self.ui.complete_label.setVisible(True)

        path_to_image = get_icon_path("button_abortbatch.svg")
        set_button_image(self.ui.run_abort_new_toolbutton, str(path_to_image), size=QSize(40, 50),
                         text='Abort', style=Qt.ToolButtonTextUnderIcon)

        set_button_image(self.ui.play_pause_toolbutton, str(path_to_pause_resume_image), size=QSize(40, 50),
                         text=button_text, style=Qt.ToolButtonTextUnderIcon)
        self.ui.play_pause_toolbutton.setEnabled(True)

        self.ui.batch_settings_toolbutton.setEnabled(False)

        self.ui.variants_spinbox.setEnabled(False)
        self.ui.reps_per_variant_spinbox.setEnabled(False)
        self.ui.use_cores_spindbox.setEnabled(False)

        self.ui.open_batch_folder_button.setEnabled(True)

    def __update_panel_complete_state(self):
        """
        Sets panel buttons and labels to the 'complete' state.
        """
        self.ui.batch_state_label.setText("Completed")
        style_sheet = self.BLUE_STYLE_SHEET
        self.__update_panel_done_state_common(style_sheet)

    def __update_panel_aborted_state(self):
        """
        Sets panel buttons and labels to the 'aborted' state.
        """
        self.ui.batch_state_label.setText("Aborted")
        style_sheet = self.RED_STYLE_SHEET
        self.__update_panel_done_state_common(style_sheet)

    def __update_panel_done_state_common(self, style_sheet: str):
        """
        Common panel settings for the Complete or Aborted 'done' states.
        :param style_sheet: A style sheet for labels in the UI.
        """
        self.ui.batch_state_label.setStyleSheet(style_sheet)
        self.ui.percent_complete_label.setStyleSheet(style_sheet)
        self.ui.complete_label.setStyleSheet(style_sheet)

        path_to_image = get_icon_path("button_newbatch.svg")
        set_button_image(self.ui.run_abort_new_toolbutton, str(path_to_image), size=QSize(40, 50),
                         text='New', style=Qt.ToolButtonTextUnderIcon)

        path_to_image = get_icon_path("button_pausebatch.svg")
        set_button_image(self.ui.play_pause_toolbutton, str(path_to_image), size=QSize(40, 50),
                         text='Pause', style=Qt.ToolButtonTextUnderIcon)
        self.ui.play_pause_toolbutton.setEnabled(False)

        self.ui.batch_settings_toolbutton.setEnabled(False)

    def __on_replication_done(self, num_reps_done: int, num_total_reps: int):
        """
        Slot called when a replication is done.
        :param num_reps_done: The number of completed replications.
        :param num_total_reps: The total number of replications.
        """
        self.__update_batch_status(num_reps_done, num_total_reps)

    def __on_replication_error(self, num_reps_done: int, num_total_reps: int, _3: str):
        """
        Slot called when an error occurs in a replication.
        :param num_reps_done: The number of completed replications.
        :param num_total_reps: The total number of replications.
        :param _3: Unused parameter.
        """
        self.__update_batch_status(num_reps_done, num_total_reps)

    def __update_batch_status(self, num_reps_done: int, num_total_reps: int):
        """
        Updates the batch status labels
        :param num_reps_done: The number of completed replications.
        :param num_total_reps: The total number of replications.
        """
        num_variants_done = self.__batch_sim_manager.get_num_variants_done()
        num_reps_failed = self.__batch_sim_manager.get_num_replics_failed()
        num_reps_succeeded = num_reps_done - num_reps_failed
        num_reps_running = self.__batch_sim_manager.num_replics_in_progress
        num_variants_failed = self.__batch_sim_manager.get_num_variants_failed()

        if num_total_reps == 0:
            reps_completed_percentage = 0
        else:
            reps_completed_percentage = (num_reps_failed + num_reps_succeeded) / num_total_reps
        self.ui.percent_complete_label.setText('{0:.0%}'.format(reps_completed_percentage))

        self.ui.finished_reps_label.setText(str(num_reps_done))
        self.ui.running_reps_label.setText(str(num_reps_running))
        self.ui.failed_reps_label.setText(str(num_reps_failed))
        self.ui.finished_variants_label.setText(str(num_variants_done))
        self.ui.failed_variants_label.setText(str(num_variants_failed))

    def __on_batch_folder_changed(self):
        """
        Slot called when batch folder changed.
        """
        self.__on_update_batch_combobox(None)

    def __on_action_open_batch_folder(self):
        """
        Open a Windows Explorer window for the current batch folder.
        """
        folder = self.selected_batch_folder
        if folder is None:
            raise RuntimeError("No batch folder exists yet!")

        os.startfile(str(folder))

    def __on_batch_time_stats_changed(self, _1: timedelta, _2: int, _3: int,
                                      ave_time_per_rep: timedelta, est_time_remaining: timedelta):
        """
        Update the average time per replication and estimated time remaining labels.
        # time since last start (stops increasing when Done), number of replics done, number of replics pending,
        # average ms per replic, estimate to completion (in seconds) from now:
        :param _1: Unused paramater.
        :param _2: Unused paramater.
        :param _3: Unused paramater.
        :param ave_time_per_rep: Average time (in ms) per replication.
        :param est_time_remaining: Estimate time to completion (in seconds) from now.
        """
        self.ui.ave_time_per_rep_label.setText(str(ave_time_per_rep))
        self.ui.est_time_remaining_label.setText(str(est_time_remaining))

    __slot_display_batch_sim_settings = safe_slot(__display_batch_settings)

    __slot_on_action_run_abort_new = safe_slot(__on_action_run_abort_new)
    __slot_on_action_play_pause = safe_slot(__on_action_play_pause)
    __slot_on_action_variant_changed = safe_slot(__on_action_variant_changed)
    __slot_on_action_replics_changed = safe_slot(__on_action_replics_changed)
    __slot_on_action_num_cores_changed = safe_slot(__on_action_num_cores_changed)

    __slot_on_scen_path_changed = safe_slot(__on_scen_path_changed)
    __slot_on_batch_state_changed = safe_slot(__on_batch_state_changed)
    __slot_on_replication_done = safe_slot(__on_replication_done)
    __slot_on_replication_error = safe_slot(__on_replication_error)
    __slot_on_batch_folder_changed = safe_slot(__on_batch_folder_changed)
    __slot_on_action_open_batch_folder = safe_slot(__on_action_open_batch_folder)
    __slot_on_update_batch_combobox_display = safe_slot(__on_update_batch_combobox)
    __slot_on_batch_time_stats_changed = ext_safe_slot(__on_batch_time_stats_changed)
