# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Common GUI Sim components.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import webbrowser
from enum import IntEnum
from pathlib import Path

# [2. third-party]
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QDialog, QWidget, QFileDialog, QMessageBox, QTableWidgetItem, QGroupBox
from PyQt5.Qt import Qt

# [3. local]
from ...core import override_required, override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario import MIN_REPLIC_ID, MIN_VARIANT_ID, SimSteps, SimController, SimControllerSettings
from ...batch_sim import SeedTable, BatchSimManager, BatchSimSettings

from ..safe_slot import safe_slot
from ..gui_utils import exec_modal_dialog, set_default_dialog_frame_flags
from ..conversions import convert_seconds_to_string, convert_float_days_to_string

from .Ui_seed_options import Ui_SeedOptionsWidget
from .Ui_sim_steps import Ui_SimStepsWidget

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'SimSettingsDialog',
    'SimStepsWidget',
    'SeedOptionsWidget',
    'SimDialog'
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

class SettingsPanelType(IntEnum):
    """Enumeration of Settings panel types"""
    main, batch = range(2)


class SimDialog(QDialog):
    """
    The base class for sim dialogs used to set Window's flags so that the context help '?' is hidden.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        set_default_dialog_frame_flags(self)


class SimSettingsDialog(SimDialog):
    """
    A base dialog class for constructing Simulation Settings Dialogs.
    """

    SETTINGS_FILE_LOCATION = "settings_file_location"
    SETTINGS_FILE_EXT = None
    SETTINGS_CLASS = None

    def __init__(self, panel_type: int, ui: Any, parent: QWidget = None):
        """
        Initialize the base sim settings dialog class.
        :param panel_type: The int value of the SettingsPanelType: either 'Main' or 'Batch'.
        :param ui: The UI components.
        :param parent: Optional parent widget.
        """
        super().__init__(parent)

        self.ui = ui
        self.ui.setupUi(self)

        self.sim_steps = SimStepsWidget(panel_type)
        self.seed_options = SeedOptionsWidget(panel_type, ui)
        self.settings = None
        self.help_file_link = None
        self.__panel_type = SettingsPanelType(panel_type)

        if panel_type == SettingsPanelType.main:
            self.SETTINGS_FILE_EXT = SimController.SETTINGS_FILE_EXT
            self.SETTINGS_CLASS = SimControllerSettings
        else:
            self.SETTINGS_FILE_EXT = BatchSimManager.SETTINGS_FILE_EXT
            self.SETTINGS_CLASS = BatchSimSettings

        self.ui.help_button.clicked.connect(self.slot_on_help_button_clicked)
        self.ui.load_button.clicked.connect(self.slot_on_load_button_clicked)
        self.ui.save_button.clicked.connect(self.slot_on_save_button_clicked)

    @override(QDialog)
    def accept(self):
        """
        Override to apply settings before closing dialog.
        """
        success = self.apply_settings()
        if success:
            super().accept()

    @override_required
    def apply_settings(self) -> bool:
        """
        Apply the simulation settings to the backend.
        :returns: a boolean indicating if settings were applied.
        """
        NotImplementedError

    @override_required
    def set_panel_settings(self):
        """Set the settings into the panel."""
        NotImplementedError

    @override_required
    def get_panel_settings(self):
        """Get the settings from the panel."""
        NotImplementedError

    def on_help_button_clicked(self):
        """
        Open the relevant User Manual page.
        """
        import origame
        user_manual = str(Path(origame.__file__).parent.joinpath("docs", "user_manual_html"))
        destination = "file:///" + user_manual + self.help_file_link
        webbrowser.open_new_tab(destination)

    def on_load_button_clicked(self):
        """
        Load the simulation settings.
        """
        if self.__panel_type.value == SettingsPanelType.main:
            load_type = "Main"
        else:
            load_type = "Batch"

        (filepath, ok) = QFileDialog.getOpenFileName(self, "Load {} Simulation Settings File".format(load_type),
                                                     QSettings().value(self.SETTINGS_FILE_LOCATION),
                                                     "Settings files (*{})".format(self.SETTINGS_FILE_EXT))

        assert filepath is not None

        if not filepath:
            return

        QSettings().setValue(self.SETTINGS_FILE_LOCATION, filepath)

        try:
            self.settings = self.SETTINGS_CLASS.load(filepath)
        except Exception as exc:
            msg_title = 'Load {} Simulation Settings File Error'.format(load_type)
            error_msg = str(exc) + '\nAn error occurred while loading the simulation settings.'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)

        self.set_panel_settings()

    def on_save_button_clicked(self):
        """
        Save the simulation settings.
        """
        if self.__panel_type.value == SettingsPanelType.main:
            load_type = "Main"
        else:
            load_type = "Batch"

        (filepath, suffix) = QFileDialog.getSaveFileName(self, "Save {} Simulation Settings File".format(load_type),
                                                         QSettings().value(self.SETTINGS_FILE_LOCATION),
                                                         "Settings files (*{})".format(self.SETTINGS_FILE_EXT))
        if not filepath:
            return

        # Updates QSettings with filepath
        QSettings().setValue(self.SETTINGS_FILE_LOCATION, filepath)

        # Save the current panel settings config to file
        # Note: this does not save the current backend settings, only what's in the panel
        settings = self.get_panel_settings()
        if settings:
            settings_object = self.SETTINGS_CLASS(**settings)
            settings_object.save(Path(filepath))

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_help_button_clicked = safe_slot(on_help_button_clicked)
    slot_on_load_button_clicked = safe_slot(on_load_button_clicked)
    slot_on_save_button_clicked = safe_slot(on_save_button_clicked)


class SimStepsWidget(QWidget):
    """
    Provides management of simulation steps dialog.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, panel_type: int):
        """
        Initialize the sim steps widget.
        :param panel_type: The int value of the SettingsPanelType: either 'Main' or 'Batch'.
        """
        super().__init__()

        # Add in the Simulation Options section to the panel
        self.ui = Ui_SimStepsWidget()
        self.ui.setupUi(self)
        self.__panel_type = SettingsPanelType(panel_type)

    def set_step_settings(self, sim_steps: SimSteps):
        """
        Set step settings into the panel.
        :param sim_steps: The simulation step options.
        """
        if sim_steps is None:
            return

        zero_sim_time = sim_steps.reset.zero_sim_time
        zero_wall_clock_time = sim_steps.reset.zero_wall_clock
        clear_event_queue = sim_steps.reset.clear_event_queue
        apply_reset_seed = sim_steps.reset.apply_reset_seed
        run_reset_parts = sim_steps.reset.run_reset_parts
        run_startup_parts = sim_steps.start.run_startup_parts
        max_sim_time_days = sim_steps.end.max_sim_time_days
        max_wall_clock_sec = sim_steps.end.max_wall_clock_sec
        stop_when_queue_empty = sim_steps.end.stop_when_queue_empty
        run_finish_parts = sim_steps.end.run_finish_parts

        self.ui.zero_sim_time_checkbox.setChecked(zero_sim_time)
        self.ui.zero_wall_clock_checkbox.setChecked(zero_wall_clock_time)
        self.ui.clear_event_queue_checkbox.setChecked(clear_event_queue)
        self.ui.apply_reset_seed_checkbox.setChecked(apply_reset_seed)
        self.ui.run_reset_parts_checkbox.setChecked(run_reset_parts)
        self.ui.run_startup_parts_checkbox.setChecked(run_startup_parts)

        if max_sim_time_days is None:
            self.ui.max_sim_time_linedit.setText('')
        else:
            self.ui.max_sim_time_linedit.setText(
                convert_float_days_to_string(float(max_sim_time_days)))

        if max_wall_clock_sec is None:
            self.ui.max_wall_clock_time_linedit.setText('')
        else:
            self.ui.max_wall_clock_time_linedit.setText(
                convert_seconds_to_string(int(max_wall_clock_sec)))

        self.ui.zero_events_checkbox.setChecked(stop_when_queue_empty)
        self.ui.run_finish_funcs_checkbox.setChecked(run_finish_parts)

    def enable_step_settings(self, enable: bool):
        """
        Enable or disable step setting fields.
        :param enable: The flag indicating whether to enable or disable.
        """
        self.ui.reset_sim_steps_groupbox.setEnabled(enable)
        self.ui.start_sim_steps_groupbox.setEnabled(enable)
        self.ui.end_sim_steps_groupbox.setEnabled(enable)

    def get_sim_step_components(self) -> Tuple[QGroupBox]:
        """
        Returns the 'sim steps' groupbox widgets.
        """
        reset_sim_steps = self.ui.reset_sim_steps_groupbox
        start_sim_steps = self.ui.start_sim_steps_groupbox
        end_sim_steps = self.ui.end_sim_steps_groupbox
        return reset_sim_steps, start_sim_steps, end_sim_steps

    sim_step_components = property(get_sim_step_components)


class SeedOptionsWidget(QWidget):
    """
    Provides management of simulation dialog seed options.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    SEED_FILE_LOCATION = "seed_file_location"

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, panel_type: int, parent_ui: Any):
        """
        Initialize the seed options widget.
        :param panel_type: The int value of the SettingsPanelType: either 'Main' or 'Batch'.
        :param parent_ui: An optional parent UI object.
        """
        super().__init__()

        # Add in the Seed Options section to the panel
        self.parent_ui = parent_ui
        self.ui = Ui_SeedOptionsWidget()
        self.ui.setupUi(self)

        self.__panel_type = SettingsPanelType(panel_type)
        self.__seed_table = None

        self.ui.auto_seed_checkbox.stateChanged.connect(self.__slot_on_auto_seed_checkbox_checked)
        self.ui.load_seeds_button.clicked.connect(self.__slot_on_load_seeds_button_clicked)
        self.ui.save_seeds_button.clicked.connect(self.__slot_on_save_seeds_button_clicked)
        self.ui.generate_seeds_button.clicked.connect(self.__slot_on_regenerate_button_clicked)

    def set_seed_settings(self, auto_seed_checked: bool, reset_seed: int = None, seed_table: SeedTable = None):
        """
        Set seed simulation options.
        :param auto_seed_checked: A boolean indicating if the checkbox is checked.
        :param reset_seed: [Only if panel_type==main] An integer seed value.
        :param seed_table: [Only if panel_type==batch] A table of integer seed values.
        """
        self.ui.auto_seed_checkbox.setChecked(auto_seed_checked)
        if self.__panel_type.value == SettingsPanelType.main:
            if reset_seed is not None:
                self.ui.reset_seed_spinbox.setValue(reset_seed)
        else:
            self.create_table_rows()
            if seed_table is not None:
                self.fill_table(seed_table)

    def create_table_rows(self, num_rows: int = None):
        """
        Helper method to create a specific number of rows in the table widget.
        :param num_rows: The number of rows to insert.
        """
        if num_rows is None:
            self.ui.seed_table_widget.setRowCount(
                self.parent_ui.replics_per_variant_spinbox.value() * self.parent_ui.variants_spinbox.value())
        else:
            self.ui.seed_table_widget.setRowCount(num_rows)

    def fill_table(self, seed_table: SeedTable):
        """
        This method is used to populate the UI table widget with seeds from given SeedTable object.
        :param seed_table: The seed table object to use to fill the table widget.
        """
        for row, (variant_id, replic_id, seed) in enumerate(seed_table.get_seeds_list_iter()):
            self.__fill_row(variant_id, replic_id, seed, row)

    def get_seeds_from_table_widget(self, num_variants: int, num_reps_per_variant: int) -> SeedTable:
        """
        This method is used to create a seeds list based on the items in the table widget.
        :param num_variants: The number of variants dimension of the seed table.
        :param num_reps_per_variant: The number of replications per variant dimension of the seed table.
        :returns: A SeedTable object filled with seeds from the table widget.
        """
        COLUMN_VARIANT = 0
        COLUMN_SEED = 2
        seeds = SeedTable(num_variants, num_reps_per_variant)

        prev_variant = MIN_VARIANT_ID - 1
        for row in range(0, self.ui.seed_table_widget.rowCount()):
            table_widget_item = self.ui.seed_table_widget.item(row, COLUMN_VARIANT)
            if table_widget_item is None:
                continue

            variant_id = int(table_widget_item.text())
            if prev_variant != variant_id:
                replic_id = MIN_REPLIC_ID
                prev_variant = variant_id
            seed = int(self.ui.seed_table_widget.item(row, COLUMN_SEED).text())
            seeds.set_seed(variant_id, replic_id, seed)
            replic_id += 1

        return seeds

    def enable_seed_settings(self, enable: bool):
        """
        Enable or disable seed setting fields.
        :param enable: The flag indicating whether to enable or disable.
        """
        self.ui.load_seeds_button.setEnabled(enable)
        self.ui.save_seeds_button.setEnabled(enable)
        self.ui.generate_seeds_button.setEnabled(enable)
        self.ui.reset_seed_spinbox.setEnabled(enable)
        self.ui.seed_table_widget.setEnabled(enable)

    def get_seed_components(self) -> QWidget:
        """
        Returns the 'seed options' groupbox widget.
        """
        return self.ui.seed_options_groupbox

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    seed_components = property(get_seed_components)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_auto_seed_checkbox_checked(self, checked: int):
        """
        Autogenerate seeds checked/unchecked.
        :param checked: The Qt.CheckState that is 'Unchecked', 'PartiallyChecked', or 'Checked'.
        """
        if checked == Qt.Checked:
            self.enable_seed_settings(False)
        else:
            self.enable_seed_settings(True)

    def __on_regenerate_button_clicked(self):
        """
        Slot called when teh Regenerate button is clicked.
        """
        if self.__panel_type.value == SettingsPanelType.main:
            seed_table = SeedTable(1, 1)
            self.__seed_table = seed_table
            self.ui.reset_seed_spinbox.setValue(seed_table.get_seed(1, 1))
        else:
            self.ui.seed_table_widget.setRowCount(0)
            reps_per_var = self.parent_ui.replics_per_variant_spinbox.value()
            variants = self.parent_ui.variants_spinbox.value()
            self.ui.seed_table_widget.setRowCount(reps_per_var * variants)
            seed_table = SeedTable(variants, reps_per_var)
            self.__seed_table = seed_table
            self.fill_table(seed_table)

    def __on_save_seeds_button_clicked(self):
        """
        Save seeds to file.
        This will load a seed file and fill the table.
        """
        (filepath, suffix) = QFileDialog.getSaveFileName(self, "Save seed file",
                                                         QSettings().value(self.SEED_FILE_LOCATION),
                                                         "Seed files (*.csv)")
        if not filepath:
            return

        # Updates QSettings with filepath
        QSettings().setValue(self.SEED_FILE_LOCATION, filepath)

        # Save the seeds to file
        if self.__seed_table is None and self.__panel_type.value == SettingsPanelType.main:
            # The seed was entered manually or generated by the backend -> create a seed table using this value
            seed_table = SeedTable(1, 1)
            try:
                seed_table.set_seed(1, 1, self.ui.reset_seed_spinbox.value())
            except Exception as exc:
                msg_title = 'Seed Table Creation Error'
                error_msg = str(exc) + '\nAn error occurred while creating the seed table for saving.'
                exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
                log.error('{}: {}', msg_title, error_msg)

            self.__seed_table = seed_table

        try:
            self.__seed_table.save_as(filepath)
        except Exception as exc:
            msg_title = 'Seed Table Save Error'
            error_msg = str(exc) + '\nAn error occurred while saving the seed table.'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)

    def __on_load_seeds_button_clicked(self):
        """
        Load seeds from file.
        This will load a seed file and fill the table.
        """
        (filepath, ok) = QFileDialog.getOpenFileName(self, "Load seed file",
                                                     QSettings().value(self.SEED_FILE_LOCATION),
                                                     "Seed files (*.csv)")
        if not filepath:
            return

        if self.__panel_type.value == SettingsPanelType.main:
            variants = 1
            replics = 1
        else:
            variants = self.parent_ui.variants_spinbox.value()
            replics = self.parent_ui.replics_per_variant_spinbox.value()

        try:
            seed_table = SeedTable(variants, replics, csv_path=filepath)
            seed_table.load()
        except Exception as exc:
            msg_title = 'Load Seed Table Error'
            error_msg = str(exc) + '\nAn error occurred while loading the seed table.'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)

        QSettings().setValue(self.SEED_FILE_LOCATION, filepath)

        if self.__panel_type.value == SettingsPanelType.main:
            self.ui.reset_seed_spinbox.setValue(seed_table.get_seed(1, 1))
        else:
            assert seed_table is not None
            self.__seed_table = seed_table
            self.fill_table(seed_table)

    def __fill_row(self, var_index: int, rep_index: int, seed: int, row: int):
        """
        This method is used to fill a single row of the table widget.  This row
        corresponds to a single row within a seed file.
        :param var_index: The variant number.
        :param rep_index: The replication number.
        :param seed: The seed to insert.
        :param row: The row to insert into the table.
        """
        self.ui.seed_table_widget.setItem(row, 0, QTableWidgetItem(str(var_index)))
        self.ui.seed_table_widget.setItem(row, 1, QTableWidgetItem(str(rep_index)))
        self.ui.seed_table_widget.setItem(row, 2, QTableWidgetItem(str(seed)))

    __slot_on_auto_seed_checkbox_checked = safe_slot(__on_auto_seed_checkbox_checked)
    __slot_on_regenerate_button_clicked = safe_slot(__on_regenerate_button_clicked)
    __slot_on_load_seeds_button_clicked = safe_slot(__on_load_seeds_button_clicked)
    __slot_on_save_seeds_button_clicked = safe_slot(__on_save_seeds_button_clicked)
