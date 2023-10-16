# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Scenario Animation functionality

There are two separate flags for animation:

- the runtime animation setting is what the user or the scenario wants during simulation *run* of the scenario.
- the animation mode is whether the GUI should reflect the backend Scenario state as it changes. The mode is affected
  by the setting only while in Running state: in that state, the mode = setting.

Synchronization of the setting between the GUI and SimController is provided by RuntimeAnimationSettingMonitor class,
which should be instantiated by the main window of the application. GUI components that must monitor the animation
*mode* (like the 2D View and the Sim Event Queue Panel) must derive from IHasAnimationMode.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import QObject
from PyQt5.QtWidgets import QAction

# [3. local]
from ..core import override_optional, override
from ..scenario import SimController, ScenarioManager, Scenario
from .gui_utils import IScenarioMonitor
from .safe_slot import safe_slot
from .async_methods import AsyncRequest

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'IHasAnimationMode',
    'RuntimeAnimationSettingMonitor',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class IHasAnimationMode:
    """
    Any GUI object that needs to know when Animation mode is ON/OFF should derive from this class and override
    _on_animation_mode_enabled() and  _on_animation_mode_disabled(). The __init__ of this class must be called,
    and monitor_animation_changes(SimController) must be called as soon as the sim controller (which controls
    animation for a given scenario) is available.
    """

    def __init__(self):
        self._is_animated = True
        self._sim_controller = None

    def monitor_animation_changes(self, sim_controller: SimController, init: bool = False):
        """
        Make this object connect to sim_controller's sig_animation_mode_changed which will lead to automatic calls to
        _on_animation_mode_enabled and _on_animation_mode_disabled when animation toggles on and off.

        :param sim_controller: the sim controller to monitor
        :param init: if True, also call self.__notify_animation_changed() with the sim_controller's current animation
            state, so the appropriate _on_animation_mode_*() method will get called.

        Note that this method needs to be called whenever the Scenario gets replaced so that its sim controller can
        be monitored.
        """
        if self._sim_controller is not None:
            self._sim_controller.signals.sig_animation_mode_changed.disconnect(self.__slot_notify_animation_changed)
        self._sim_controller = sim_controller
        if init:
            self.__notify_animation_changed(sim_controller.is_animated)
        sim_controller.signals.sig_animation_mode_changed.connect(self.__slot_notify_animation_changed)

    def get_is_animated(self):
        """Return True if this object is animated. Animation depends on the setting and the sim run state."""
        return self._is_animated

    is_animated = property(get_is_animated)

    @override_optional
    def _on_animation_mode_enabled(self):
        """Called when animation has been enabled."""
        # 1. connect to signals from backend so get updates
        # 2. refresh visuals: get data from backend (mostly async requests)
        # 3. (if necessary) call __notify_animation_changed(True) on children
        # 3. (preferably) provide visual cue that self is in sync with backend
        pass

    @override_optional
    def _on_animation_mode_disabled(self):
        """Called when animation has been disabled"""
        # 1. disconnect from backend signals so we don't get updates
        # 2. (if done in enabled) call __notify_animation_changed(False) on children
        # 3. (if done in enabled) provide visual cue that self is no longer in sync with backend
        pass

    def __notify_animation_changed(self, enabled: bool):
        """
        Notify this object whether it should reflect (enabled True) or not (enabled False) backend
        state changes dispatch to the appropriate protected method.
        """
        if enabled:
            self._is_animated = True
            self._on_animation_mode_enabled()
        else:
            self._is_animated = False
            self._on_animation_mode_disabled()

    __slot_notify_animation_changed = safe_slot(__notify_animation_changed)


class RuntimeAnimationSettingMonitor(IScenarioMonitor, QObject):
    """
    This class is the link between the GUI animation setting in menu/toolbar and the SimController
    where animation mode is stored. It also configures the sim controller of current scenario to have
    animation on.
    """

    def __init__(self, scenario_manager: ScenarioManager, anim_action: QAction = None):
        IScenarioMonitor.__init__(self, scenario_manager)
        QObject.__init__(self)

        self._sim_controller = None
        self._anim_action = anim_action
        anim_action.toggled.connect(self._slot_on_user_toggled_animation)

        self._monitor_scenario_replacement()

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        """Whenever the scenario is replaced, we need to drop previous and bind to new"""
        if self._sim_controller is not None:
            sig_rt_anim_changed = self._sim_controller.signals.sig_anim_while_run_dyn_setting_changed
            sig_rt_anim_changed.disconnect(self._slot_on_animation_setting_changed_by_sim)

        self._sim_controller = scenario.sim_controller
        sig_rt_anim_changed = self._sim_controller.signals.sig_anim_while_run_dyn_setting_changed
        sig_rt_anim_changed.connect(self._slot_on_animation_setting_changed_by_sim)

    def _on_user_toggled_animation(self, value: bool):
        """
        Command the sim controller to change its setting. The controller will emit a signal which we are
        connected to, this will update the menu item to reflect new state.
        """
        if self._sim_controller is not None:
            AsyncRequest.call(self._sim_controller.set_anim_while_run_dyn_setting, value)

    def _on_animation_setting_changed_by_sim(self, enabled: bool):
        """
        Notify this object whether it should reflect (enabled True) or not (enabled False) backend
        state changes dispatch to the appropriate protected method.
        """
        self._anim_action.setChecked(enabled)

    _slot_on_user_toggled_animation = safe_slot(_on_user_toggled_animation)
    _slot_on_animation_setting_changed_by_sim = safe_slot(_on_animation_setting_changed_by_sim)
