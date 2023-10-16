# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module is used to represent the state and behaviour of the Batch Simulation
                       Settings dialog.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path

# [2. third-party]
from PyQt5.Qt import Qt
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QDialog, QFileDialog, QSpinBox, QMessageBox, QWidget

# [3. local]
from ....scenario import SimSteps
from ....core import override
from ....core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ....core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ....batch_sim import BatchSimManager, BatchSimSettings

from ...safe_slot import safe_slot
from ...gui_utils import exec_modal_dialog
from ...conversions import convert_string_to_float, convert_string_into_seconds

from ..common import SimSettingsDialog, SettingsPanelType

from .Ui_batch_simulation_settings import Ui_BatchSimulationSettingsDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    'BatchSimulationSettingsDialog'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------


class BatchSimulationSettingsDialog(SimSettingsDialog):
    """
    This class is used to display and/or change Batch Simulation settings.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    BATCH_RUNS_FOLDER = "settings_batch_runs_folder"

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, batch_sim_manager: BatchSimManager, parent: QWidget = None):
        """
        Initialize the batch sim settings dialog.
        :param batch_sim_manager: The batch sim manager.
        :param parent: The optional parent widget.
        """
        super().__init__(SettingsPanelType.batch, Ui_BatchSimulationSettingsDialog(), parent)

        self.help_file_link = r"/using origame.html#batch-run"

        # Customizations for batch settings
        self.seed_options.ui.reset_seed_spinbox.setVisible(False)
        self.seed_options.ui.reset_seed_label.setVisible(False)
        self.seed_options.ui.seed_options_groupbox.setTitle('Random seeds')
        self.sim_steps.ui.pause_if_running_image_label.setVisible(False)
        self.sim_steps.ui.pause_if_running_label.setVisible(False)
        self.sim_steps.ui.run_if_paused_image_label.setVisible(False)
        self.sim_steps.ui.run_if_paused_label.setVisible(False)
        self.sim_steps.ui.pause_if_running_image_label_2.setVisible(False)
        self.sim_steps.ui.pause_if_running_label_2.setVisible(False)

        # Add the three UI panels into single settings panel
        reset_sim_steps, start_sim_steps, end_sim_steps = self.sim_steps.sim_step_components
        seed_options = self.seed_options.seed_components
        self.ui.replic_config_groupbox.layout().addWidget(reset_sim_steps)
        self.ui.replic_config_groupbox.layout().addWidget(start_sim_steps)
        self.ui.replic_config_groupbox.layout().addWidget(end_sim_steps)
        self.ui.batch_config_groupbox.layout().addWidget(seed_options)

        # Connect UI elements to value/state changed slots
        self.ui.cores_spinbox.valueChanged.connect(self.__slot_on_num_cores_changed)
        self.ui.use_scen_sim_settings_checkbox.stateChanged.connect(self.__slot_use_scen_sim_settings_checked)
        self.ui.results_folder_button.pressed.connect(self.__slot_select_batch_results_folder_button)
        self.ui.results_folder_linedit.editingFinished.connect(self.__slot_select_batch_results_folder_linedit)

        # Get settings from Batch Simulation Manger and set them in the panel
        self.__batch_sim_manager = batch_sim_manager
        self.settings = self.__batch_sim_manager.get_settings(copy=True)
        self.set_panel_settings()

    @override(QFileDialog)
    def accept(self):
        success = self.apply_settings()
        if success:
            # editingFinished gets emitted on focus loss so disconnect from it, else the slot connected to it will get
            # called after the dialog closes
            self.ui.results_folder_linedit.editingFinished.disconnect()
            super().accept()

    @override(QDialog)
    def reject(self):
        # editingFinished gets emitted on focus loss so disconnect from it, else the slot connected to it will get
        # called after the dialog closes
        self.ui.results_folder_linedit.editingFinished.disconnect()
        super().reject()

    @override(QSpinBox)
    def keyReleaseEvent(self, *args, **kwargs):
        """
        Regenerate the table size after entering variant and replics_per_variant fields.
        """
        self.seed_options.create_table_rows()

    @override(SimSettingsDialog)
    def apply_settings(self) -> bool:
        """
        Apply the settings to the Batch Simulation Manger.
        :returns: A boolean indicating if the settings were applied successfully.
        """
        settings = self.get_panel_settings()
        if settings:
            assert len(settings) > 0
            self.__batch_sim_manager.set_settings(BatchSimSettings(**settings))

        return len(settings) > 0  # evaluates to True if settings are populated

    @override(SimSettingsDialog)
    def set_panel_settings(self):
        """
        Set the Batch Simulation setting values into the panel UI.
        """
        # General setting config
        batch_runs_path = self.settings.batch_runs_path
        num_variants = self.settings.num_variants
        num_replics_per_variant = self.settings.num_replics_per_variant
        num_cores_wanted = self.settings.num_cores_wanted
        save_scen_on_exit = self.settings.save_scen_on_exit
        use_scen_sim_settings = self.settings.use_scen_sim_settings
        general_settings = dict(batch_runs_path=batch_runs_path,
                                num_variants=num_variants,
                                num_replics_per_variant=num_replics_per_variant,
                                num_cores_wanted=num_cores_wanted,
                                save_scen_on_exit=save_scen_on_exit,
                                use_scen_sim_settings=use_scen_sim_settings)

        # Seed setting config
        auto_seed_checked = self.settings.auto_seed
        seed_table = self.settings.seed_table
        seed_settings = dict(auto_seed_checked=auto_seed_checked, seed_table=seed_table)

        # Set config...
        self.__set_general_settings(**general_settings)
        self.seed_options.set_seed_settings(**seed_settings)
        self.sim_steps.set_step_settings(self.settings.replic_steps)

    @override(SimSettingsDialog)
    def get_panel_settings(self) -> Dict[str, Any]:
        """
        Get all settings configured in the panel.
        :returns: A dict object containing the settings values.
        """
        batch_runs_path = self.ui.results_folder_linedit.text()
        if not batch_runs_path:
            batch_runs_path = None

        num_variants = self.ui.variants_spinbox.value()
        num_replics_per_variant = self.ui.replics_per_variant_spinbox.value()
        num_cores_wanted = self.ui.cores_spinbox.value()
        save_replic_scenarios = self.ui.save_scenario_before_exit_checkbox.isChecked()
        use_scen_sim_settings = self.ui.use_scen_sim_settings_checkbox.isChecked()

        auto_seed_checked = self.seed_options.ui.auto_seed_checkbox.isChecked()
        if auto_seed_checked:
            seed_table = None
        else:
            try:
                seed_table = self.seed_options.get_seeds_from_table_widget(num_variants, num_replics_per_variant)
            except ValueError as error:
                error_message = "Invalid seed data in table\n{}.".format(error)
                exec_modal_dialog("Seed Table Error", error_message, QMessageBox.Critical)
                return dict()

        zero_sim_time = self.sim_steps.ui.zero_sim_time_checkbox.isChecked()
        zero_wall_clock_time = self.sim_steps.ui.zero_wall_clock_checkbox.isChecked()
        clear_event_queue = self.sim_steps.ui.clear_event_queue_checkbox.isChecked()
        apply_reset_seed = self.sim_steps.ui.apply_reset_seed_checkbox.isChecked()
        run_reset_parts = self.sim_steps.ui.run_reset_parts_checkbox.isChecked()
        run_startup_parts = self.sim_steps.ui.run_startup_parts_checkbox.isChecked()

        max_sim_time_days = convert_string_to_float(self.sim_steps.ui.max_sim_time_linedit.text())
        max_wall_clock_sec = convert_string_into_seconds(self.sim_steps.ui.max_wall_clock_time_linedit.text())

        stop_when_queue_empty = self.sim_steps.ui.zero_events_checkbox.isChecked()
        run_finish_parts = self.sim_steps.ui.run_finish_funcs_checkbox.isChecked()

        settings = {
            'batch_runs_path': batch_runs_path,
            'num_variants': num_variants,
            'num_replics_per_variant': num_replics_per_variant,
            'num_cores_wanted': num_cores_wanted,
            'auto_seed': auto_seed_checked,
            'seed_table': seed_table,
            'save_scen_on_exit': save_replic_scenarios,
            'replic_steps': None
        }

        if not use_scen_sim_settings:
            replic_step_settings = dict(
                reset=dict(
                    zero_sim_time=zero_sim_time,
                    zero_wall_clock=zero_wall_clock_time,
                    clear_event_queue=clear_event_queue,
                    apply_reset_seed=apply_reset_seed,
                    run_reset_parts=run_reset_parts
                ),
                start=dict(
                    run_startup_parts=run_startup_parts
                ),
                end=dict(
                    max_sim_time_days=max_sim_time_days,
                    max_wall_clock_sec=max_wall_clock_sec,
                    stop_when_queue_empty=stop_when_queue_empty,
                    run_finish_parts=run_finish_parts
                ),
            )

            settings['replic_steps'] = SimSteps(**replic_step_settings)

        return settings

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    # ---------------------------- instance __PRIVATE methods ----------------------------

    def __set_general_settings(self, batch_runs_path: str,
                               num_variants: int,
                               num_replics_per_variant: int,
                               num_cores_wanted: int,
                               save_scen_on_exit: bool,
                               use_scen_sim_settings: bool):
        """
        Set general batch sim settings.
        """
        if batch_runs_path is None:
            batch_runs_path = ''

        self.ui.results_folder_linedit.setText(batch_runs_path)
        self.ui.replics_per_variant_spinbox.setValue(num_replics_per_variant)
        self.ui.variants_spinbox.setValue(num_variants)
        num_cores_available = self.__batch_sim_manager.num_cores_available
        self.ui.num_cores_label.setText('/ {}'.format(num_cores_available))
        self.ui.cores_spinbox.setValue(num_cores_wanted)
        self.ui.save_scenario_before_exit_checkbox.setChecked(save_scen_on_exit)
        self.ui.use_scen_sim_settings_checkbox.setChecked(use_scen_sim_settings)

    def __on_num_cores_changed(self, num_cores_set: int):
        """
        Overrides the user-set number of cores if the value specified exceeds the actual number available.
        There is no need to protect against values that are less than 0 since the spinbox has been configured
        with a minimum value of 0.
        :param num_cores_set: The number of cores specified by the user.
        """
        num_cores_available = self.__batch_sim_manager.num_cores_available
        if num_cores_set > num_cores_available:
            log.warning('The number of cores specified exceeds the number available. Setting to {}',
                        num_cores_available)
            self.ui.cores_spinbox.setValue(num_cores_available)

    def __use_scen_sim_settings_checked(self, checked: int):
        """
        Use main sim settings checked/unchecked.
        :param checked: The Qt.CheckState that is 'Unchecked', 'PartiallyChecked', or 'Checked'.
        """
        if checked == Qt.Checked:
            self.sim_steps.set_step_settings(self.__batch_sim_manager.get_scen_sim_steps())
            self.sim_steps.enable_step_settings(False)  # no user config allowed since using main scenario settings
        else:
            # enable editing of step settings
            self.sim_steps.enable_step_settings(True)

    def __select_batch_results_folder_button(self):
        """
        Select a top-level folder to hold the batch results for the run from the file browser.
        """
        batch_runs_path = QFileDialog.getExistingDirectory(self, "Select a Batch Simulation Runs Folder",
                                                           QSettings().value(self.BATCH_RUNS_FOLDER),
                                                           options=QFileDialog.ShowDirsOnly)

        if not batch_runs_path:
            return

        QSettings().setValue(self.BATCH_RUNS_FOLDER, batch_runs_path)
        self.ui.results_folder_linedit.setText(batch_runs_path)

    def __select_batch_results_folder_linedit(self):
        """
        Select a top-level folder to hold the batch results for the run by entering the directory path.
        """
        batch_runs_path = self.ui.results_folder_linedit.text()
        if not batch_runs_path:
            return

        batch_runs_path = Path(batch_runs_path)
        # print a warning if the batch runs folder specified does not exist and has not previously been set
        current_batch_results_folder = self.__batch_sim_manager.batch_runs_path
        if not batch_runs_path.exists() and batch_runs_path != current_batch_results_folder:
            log.warning("The batch runs folder specified does not exist but will be created when the batch is run.")

        QSettings().setValue(self.BATCH_RUNS_FOLDER, batch_runs_path)

    __slot_on_num_cores_changed = safe_slot(__on_num_cores_changed)
    __slot_use_scen_sim_settings_checked = safe_slot(__use_scen_sim_settings_checked)
    __slot_select_batch_results_folder_button = safe_slot(__select_batch_results_folder_button)
    __slot_select_batch_results_folder_linedit = safe_slot(__select_batch_results_folder_linedit)
