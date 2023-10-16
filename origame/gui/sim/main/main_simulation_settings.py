# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module is used to represent the state and behaviour of the Main Simulation
                       Settings dialog.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from fractions import Fraction

# [2. third-party]
from PyQt5.QtWidgets import QWidget

# [3. local]
from ....scenario import SimController, SimControllerSettings, SimSteps
from ....core import override
from ....core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ....core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ...safe_slot import safe_slot
from ...conversions import convert_string_to_float, convert_string_into_seconds

from ..common import SimSettingsDialog, SettingsPanelType
from .Ui_main_simulation_settings import Ui_MainSimulationSettingsDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'MainSimulationSettingsDialog'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------


class MainSimulationSettingsDialog(SimSettingsDialog):
    """
    This class is used to display and/or change Main Simulation settings.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    REAL_TIME_INDEX = 0
    IMMEDIATE_INDEX = 1

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, sim_controller: SimController, parent: QWidget = None):
        """
        Initialize the main sim settings dialog.
        :param sim_controller: The sim controller.
        :param parent: The optional parent widget.
        """
        super().__init__(SettingsPanelType.main, Ui_MainSimulationSettingsDialog(), parent)

        self.help_file_link = r"/using origame.html#main-run"

        # Customizations for main settings
        self.seed_options.ui.seed_options_groupbox.setTitle('Reset seed')
        self.seed_options.ui.seed_table_widget.setVisible(False)

        # Add the three UI panels into single settings panel
        reset_sim_steps, start_sim_steps, end_sim_steps = self.sim_steps.sim_step_components
        seed_options = self.seed_options.seed_components
        self.ui.right_vertical_layout.layout().addWidget(reset_sim_steps)
        self.ui.right_vertical_layout.layout().addWidget(start_sim_steps)
        self.ui.right_vertical_layout.layout().addWidget(end_sim_steps)
        self.ui.reset_seed_layout.addWidget(seed_options)

        # Connect UI elements to value/state changed slots
        self.ui.apply_button.clicked.connect(self.slot_on_apply_button_clicked)
        self.ui.time_mode_combobox.currentIndexChanged.connect(self.__slot_on_time_mode_changed)

        # Get settings from Main Simulation Manger and set them in the panel
        self.__sim_controller = sim_controller
        # remove the next line if a widget is added to the panel for Animation
        self.__anim_while_run_dyn = None
        self.settings = self.__sim_controller.get_settings(copy=True)
        self.set_panel_settings()

    @override(SimSettingsDialog)
    def apply_settings(self) -> bool:
        """
        Apply the settings to the Sim Controller.
        :returns: A boolean indicating if the settings were applied successfully.
        """
        settings = self.get_panel_settings()
        self.__sim_controller.set_settings(SimControllerSettings(**settings))
        return len(settings) > 0  # evaluates to True if settings are populated

    @override(SimSettingsDialog)
    def set_panel_settings(self):
        """
        Set the Main Simulation setting values into the panel UI".
        """
        # General setting config
        variant_id = self.settings.variant_id
        replic_id = self.settings.replic_id
        realtime_mode = self.settings.realtime_mode
        realtime_scale = self.settings.realtime_scale
        anim_while_run_dyn = self.settings.anim_while_run_dyn
        general_settings = dict(variant_id=variant_id, replic_id=replic_id,
                                realtime_mode=realtime_mode, realtime_scale=realtime_scale,
                                anim_while_run_dyn=anim_while_run_dyn)

        # Seed setting config
        auto_seed_checked = self.settings.auto_seed
        reset_seed = self.settings.reset_seed
        seed_settings = dict(auto_seed_checked=auto_seed_checked, reset_seed=reset_seed)

        # Set config...
        self.__set_general_settings(**general_settings)
        self.seed_options.set_seed_settings(**seed_settings)
        self.sim_steps.set_step_settings(self.settings.sim_steps)

    @override(SimSettingsDialog)
    def get_panel_settings(self) -> Dict[str, Any]:
        """
        Get all settings configured in the panel.
        :returns: A dict object containing the settings values.
        """
        variant_id = self.ui.variant_num_spinbox.value()
        replic_id = self.ui.replic_num_spinbox.value()

        auto_seed_checked = self.seed_options.ui.auto_seed_checkbox.isChecked()
        reset_seed = None
        if not auto_seed_checked:
            reset_seed = self.seed_options.ui.reset_seed_spinbox.value()

        realtime_mode = False if self.ui.time_mode_combobox.currentIndex() == self.IMMEDIATE_INDEX else True
        numerator = self.ui.real_time_ratio_spinbox.value()
        denominator = self.ui.sim_time_ratio_spinbox.value()
        realtime_scale = numerator / denominator

        zero_sim_time = self.sim_steps.ui.zero_sim_time_checkbox.isChecked()
        zero_wall_clock_time = self.sim_steps.ui.zero_wall_clock_checkbox.isChecked()
        clear_event_queue = self.sim_steps.ui.clear_event_queue_checkbox.isChecked()
        apply_reset_seed = self.sim_steps.ui.apply_reset_seed_checkbox.isChecked()
        run_reset_parts = self.sim_steps.ui.run_reset_parts_checkbox.isChecked()
        run_startup_parts = self.sim_steps.ui.run_startup_parts_checkbox.isChecked()

        max_sim_time_days = convert_string_to_float(
            self.sim_steps.ui.max_sim_time_linedit.text())
        max_wall_clock_sec = convert_string_into_seconds(
            self.sim_steps.ui.max_wall_clock_time_linedit.text())

        stop_when_queue_empty = self.sim_steps.ui.zero_events_checkbox.isChecked()
        run_finish_parts = self.sim_steps.ui.run_finish_funcs_checkbox.isChecked()

        settings = {
            'variant_id': variant_id,
            'replic_id': replic_id,
            'auto_seed': auto_seed_checked,
            'reset_seed': reset_seed,
            'realtime_mode': realtime_mode,
            'realtime_scale': realtime_scale,
            'anim_while_run_dyn': self.__anim_while_run_dyn
        }

        step_settings = dict(
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

        settings['sim_steps'] = SimSteps(**step_settings)

        return settings

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_apply_button_clicked = safe_slot(apply_settings)

    # ---------------------------- instance __PRIVATE methods ----------------------------

    def __set_general_settings(self, variant_id: int, replic_id: int,
                               realtime_mode: bool, realtime_scale: float,
                               anim_while_run_dyn: bool):
        """
        Set general Main sim settings.
        :param variant_id: The variant number.
        :param replic_id: The replication number.
        :param realtime_mode: The real-time mode settings (immediate or real-time).
        :param realtime_scale: The ratio of sim time-to-real time.
        :param anim_while_run_dyn: whether animation should be On (True) or Off (False) while running sim.
        """
        self.ui.variant_num_spinbox.setValue(variant_id)
        self.ui.replic_num_spinbox.setValue(replic_id)

        index = self.REAL_TIME_INDEX
        if not realtime_mode:
            index = self.IMMEDIATE_INDEX
            self.ui.scale_realtime_groupbox.setEnabled(False)

        self.ui.time_mode_combobox.setCurrentIndex(index)
        scale = Fraction(realtime_scale).limit_denominator()
        self.ui.real_time_ratio_spinbox.setValue(scale.numerator)
        self.ui.sim_time_ratio_spinbox.setValue(scale.denominator)

        # NOTE: there is currently no widget in panel displaying this setting, so save it so it can be pushed
        # to the back when user commits
        self.__anim_while_run_dyn = anim_while_run_dyn

    def __on_time_mode_changed(self, index: int):
        """
        Slot called when the the selection in the Time Mode drop down changes.
        :param index: The index of the drop-down box user selection.
        """
        if index == self.IMMEDIATE_INDEX:
            self.ui.scale_realtime_groupbox.setEnabled(False)
        else:
            self.ui.scale_realtime_groupbox.setEnabled(True)

    __slot_on_time_mode_changed = safe_slot(__on_time_mode_changed)
