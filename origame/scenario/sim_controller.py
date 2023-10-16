# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provides the scenario simulation functionality

This consists mainly of the SimController class and its state classes. The SimController has a finite state
machine (FSM) consisting of three classes that control what operations are available in each state.
These classes are intimately related to the SimController, their FSM owner; they directly modify its
private data. This is by design.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import json
import logging
from enum import IntEnum, Enum
from json import JSONDecodeError
import random
from copy import deepcopy
from pathlib import Path
from textwrap import dedent, indent
from inspect import signature
import inspect

# [2. third-party]

# [3. local]
from ..core import BridgeEmitter, BridgeSignal, BaseFsmState, IFsmOwner, SECONDS_PER_DAY, internal, override_required
from ..core import override, ClockTimer
from ..core.utils import IJsonable, get_enum_val_name
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ..core.typing import AnnotationDeclarations

from .alerts import IScenAlertSource, ScenAlertInfo, ScenAlertLevelEnum
from .part_execs import IExecutablePart
from .defn_parts import RunRolesEnum, BasePart
from .ori import IOriSerializable, OriSimConfigKeys as ScKeys, OriContextEnum, OriScenData, JsonObj, OriSchemaEnum
from .event_queue import EventQueue, EventInfo, CallInfo
from .animation import AnimationMode
from .part_execs import IPyDebuggingListener, PyDebugger

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SimController',
    'SimControllerScriptingProxy',
    'SimControllerSettings',
    'SimSteps',
    'SimStatesEnum',

    'RunRolePartsError',
    'NoScenarioFolderError',

    'MIN_VARIANT_ID',
    'MIN_REPLIC_ID',

    'new_seed',
    'check_seed',
]

log = logging.getLogger('system')

# the following min and max values support random seeds with 21 - 24 bits and in the range of 7 digits;
# boundary values are valid:
MIN_RAND_SEED, MAX_RAND_SEED = 2 ** 20, 2 ** 23
MIN_REPLIC_ID = 1  # no replication shall have an ID smaller than this
MIN_VARIANT_ID = 1  # no variant shall have an ID smaller than this


class Decl(AnnotationDeclarations):
    SimControllerSettings = 'SimControllerSettings'
    PulsePart = 'PulsePart'


# -- Function definitions -----------------------------------------------------------------------

def new_seed() -> int:
    """
    Get a new random seed in the range of [MIN_RAND_SEED, MAX_RAND_SEED]. This does not affect the random
    number generator of the Simulation Controller.
    """
    rng = random.Random()
    return rng.randint(MIN_RAND_SEED, MAX_RAND_SEED)
    # the following is not adequate because it will change the sequence of random numbers used by the
    # scenario parts during simulation (because it uses the default instance of random.Random() created
    # by the random module on import):
    # from random import randint
    # return randint(MIN_RAND_SEED, MAX_RAND_SEED)


def check_seed(random_seed: int) -> bool:
    """Check that the random_seed is in valid range: raises ValueError if not, else returns True"""
    if not (MIN_RAND_SEED <= random_seed <= MAX_RAND_SEED):
        raise ValueError("Invalid random seed {} (must be in [{},{}])".format(
            random_seed, MIN_RAND_SEED, MAX_RAND_SEED))

    return True


# -- Class Definitions --------------------------------------------------------------------------

class ErrorCatEnum(Enum):
    sim_step = range(1)


class SimSettingsFormatError(RuntimeError):
    pass


class SimResetSettings(IJsonable):
    """Main Simulation Settings for when the simulation is reset"""

    def __init__(self,
                 zero_sim_time: bool = True,
                 zero_wall_clock: bool = True,
                 clear_event_queue: bool = True,
                 apply_reset_seed: bool = True,
                 run_reset_parts: bool = True,
                 **unknown):
        """
        Set Reset run conditions.

        :param zero_sim_time: Zero the simulation time on reset.
        :param zero_wall_clock: Zero the wall clock time on reset.
        :param clear_event_queue: Clear the event queue on reset.
        :param apply_reset_seed: Initialize a random seed on reset.
        :param run_reset_parts: Run all 'reset' parts on reset.
        """
        IJsonable.__init__(self, unknown)
        self.zero_sim_time = zero_sim_time
        self.zero_wall_clock = zero_wall_clock
        self.clear_event_queue = clear_event_queue
        self.apply_reset_seed = apply_reset_seed
        self.run_reset_parts = run_reset_parts


class SimStartSettings(IJsonable):
    """Main Simulation Settings for when the simulation starts"""

    def __init__(self, run_startup_parts: bool = True, **unknown):
        """
        Set Start run conditions.
        :param run_startup_parts: Run the startup parts when the simulation is started.
        """
        IJsonable.__init__(self, unknown)
        self.run_startup_parts = run_startup_parts


class SimEndSettings(IJsonable):
    """Main Simulation Conditions for when the simulation ends"""

    def __init__(self,
                 max_sim_time_days: float = None,
                 max_wall_clock_sec: int = None,
                 stop_when_queue_empty: bool = True,
                 run_finish_parts: bool = True,
                 **unknown):
        """
        Set End run conditions.
        :param max_sim_time_days: The simulation time to stop the simulation in days.
        :param max_wall_clock_sec: The wall clock time to stop the simulation in seconds.
        :param stop_when_queue_empty: Stop the simulation when the event queue is empty if True.
        :param run_finish_parts: Run the parts that have Finish role before returning to Paused state.
        """
        IJsonable.__init__(self, unknown, 'max_sim_time_days', 'max_wall_clock_sec')
        self.__max_sim_time_days = max_sim_time_days
        self.__max_wall_clock_sec = max_wall_clock_sec
        self.stop_when_queue_empty = stop_when_queue_empty
        self.run_finish_parts = run_finish_parts

    def get_max_sim_time_days(self) -> float:
        return self.__max_sim_time_days

    def set_max_sim_time_days(self, time_days: float):
        if time_days is not None:
            if time_days <= 0:
                raise ValueError("Max sim time {} must be > 0".format(time_days))
            else:
                log.info('Will revert to PAUSED state as soon as sim time reaches {} days', time_days)

        self.__max_sim_time_days = time_days

    def get_max_wall_clock_sec(self) -> float:
        return self.__max_wall_clock_sec

    def set_max_wall_clock_sec(self, time_sec: float):
        if time_sec is not None:
            if time_sec <= 0:
                raise ValueError("Max real-time {} must be > 0".format(time_sec))
            else:
                log.info('Will exit as soon as real-time reaches {} seconds', time_sec)

        self.__max_wall_clock_sec = time_sec

    max_sim_time_days = property(get_max_sim_time_days, set_max_sim_time_days)
    max_wall_clock_sec = property(get_max_wall_clock_sec, set_max_wall_clock_sec)


class SimSteps:
    """Class to encapsulate the simulation step settings"""

    JSON_ATTR_RESET = 'reset'
    JSON_ATTR_START = 'start'
    JSON_ATTR_END = 'end'

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, reset: Dict[str, Any] = None, start: Dict[str, Any] = None, end: Dict[str, Any] = None):
        """
        :param reset: a dict with keys that match SimResetSettings initializer parameters
        :param start: a dict with keys that match SimStartSettings initializer parameters
        :param init: a dict with keys that match SimEndSettings initializer parameters

        Ex: SimSteps(
                reset=dict(zero_wall_clock=True),
                start=dict(run_startup_parts=True), 
                end=dict(max_sim_time_days=123, run_finish_parts=True)
            )
        """
        self.from_json(reset=reset or {}, start=start or {}, end=end or {})

    # --------------------------- instance __PRIVATE members-------------------------------------

    def to_json(self) -> Dict[str, Any]:
        """Get the sim step settings and return in a dictionary."""
        return {
            self.JSON_ATTR_RESET: self.reset.to_json(),
            self.JSON_ATTR_START: self.start.to_json(),
            self.JSON_ATTR_END: self.end.to_json(),
        }

    def from_json(self, reset: Dict[str, Any], start: Dict[str, Any], end: Dict[str, Any]):
        """Set the sim step settings from the given dictionary. The dict can be empty."""
        self.reset = SimResetSettings(**reset)
        self.start = SimStartSettings(**start)
        self.end = SimEndSettings(**end)

    def __str__(self):
        prefix = ' ' * 4
        return dedent("""\
            Reset: {}{}
            Start: {}{}
            End: {}{}""").format(
            # the CR is necessary because of how dedent and indent work across multiple lines
            '\n', indent(str(self.reset), prefix),
            '\n', indent(str(self.start), prefix),
            '\n', indent(str(self.end), prefix))


class SimControllerSettings:
    """The Simulation Controller Settings"""

    SETTINGS_FILE_EXT = '.mssj'
    SETTINGS_FILE_NAME = 'main_sim_settings'

    @staticmethod
    def load(file_path: PathType) -> Decl.SimControllerSettings:
        """Note: the map of unique ID to executable parts is in ori_data"""
        file_path = Path(file_path)
        with file_path.open() as json_file:
            try:
                json_root_obj = json.load(json_file)
                log.info('Scenario sim settings loaded from {}', file_path)
            except JSONDecodeError as exc:
                log.error("Could not load sim controller settings from {}: {}", file_path.absolute(), exc)
                raise

            try:
                return SimControllerSettings(**json_root_obj)
            except TypeError as exc:
                if str(exc).startswith('__init__() got an unexpected keyword argument'):
                    args = inspect.signature(SimControllerSettings.__init__).parameters
                    unknown = set(json_root_obj).difference(args)
                    raise SimSettingsFormatError('Unknown keys in {}: {}'.format(file_path, ', '.join(unknown)))
                else:
                    raise

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self,
                 variant_id: int = MIN_VARIANT_ID, replic_id: int = MIN_REPLIC_ID,
                 auto_seed: bool = True, reset_seed: int = None,
                 realtime_mode: bool = False, realtime_scale: float = 1.0,
                 sim_steps: Either[SimSteps, Dict[str, IJsonable]] = None,
                 anim_while_run_dyn: bool = True):
        """
        :param variant_id: integer ID for variant
        :param replic_id: integer ID for replication
        :param auto_seed: True to automatically select a seed (will be different at every Run)
        :param reset_seed: seed used; ignored if auto_seed is True
        :param realtime_mode: if an integer is not provided, one will be chosen in range [MIN_RAND_SEED, MAX_RAND_SEED]
        :param realtime_scale: ratio of simulation time to real-time (hence > 1 means faster than realtime)
        :param sim_steps: a SimSteps instance, or dict with keys and values that will be used as SimSteps(**sim_steps)
        :param anim_while_run_dyn: set to False if signals should not be emitted while in Running state;
            not used if animation *mode* is a constant
        """
        self.__variant_id = None
        self.__replic_id = None
        # use the properties to set the values from input so that bounds checking occurs:
        self.variant_id = variant_id
        self.replic_id = replic_id
        # if we get this far then the variant_id and replic_id args were acceptable, so we expect to have
        # them as data member values:
        assert self.__variant_id == variant_id
        assert self.__replic_id == replic_id

        if reset_seed is None and auto_seed is False:
            raise ValueError('Random seed cannot be None when auto_seed is False')

        self.auto_seed = auto_seed
        if auto_seed is True and reset_seed is not None:
            # keep the seed even if it will be ignored
            log.warning('Random seed is not None ({}), will be ignored since auto_seed is True', reset_seed)

        if reset_seed is not None:
            check_seed(reset_seed)
        self.__reset_seed = reset_seed
        self.__realtime_scale = None
        self.realtime_scale = realtime_scale
        self.realtime_mode = realtime_mode
        self.anim_while_run_dyn = anim_while_run_dyn
        assert anim_while_run_dyn in (True, False)

        if sim_steps is None:
            self.__sim_steps = SimSteps()
        else:
            if isinstance(sim_steps, SimSteps):
                self.__sim_steps = sim_steps
            else:
                # assume it is a dict:
                self.__sim_steps = SimSteps(**sim_steps)

    def get_variant_id(self) -> float:
        return self.__variant_id

    def set_variant_id(self, value: int):
        if value <= 0:
            raise ValueError("Variant ID {} must be >= 1".format(value))
        self.__variant_id = value

    def get_replic_id(self) -> float:
        return self.__replic_id

    def set_replic_id(self, value: int):
        if value <= 0:
            raise ValueError("Replication ID {} must be >= 1".format(value))
        self.__replic_id = value

    def get_realtime_scale(self) -> float:
        return self.__realtime_scale

    def set_realtime_scale(self, value: float):
        if value <= 0:
            raise ValueError("Real-time scale {} must be > 0".format(value))
        self.__realtime_scale = value

    def get_reset_seed(self) -> int:
        return self.__reset_seed

    def set_reset_seed(self, new_value: int):
        if self.auto_seed:
            raise RuntimeError("Cannot set the random seed: Auto-seeding is True")
        if check_seed(new_value):
            self.__reset_seed = new_value

    def get_sim_steps(self, copy: bool = False) -> SimSteps:
        """Get the simulation step settings. If copy=True, returns a copy of the object stored."""
        return deepcopy(self.__sim_steps) if copy else self.__sim_steps

    def set_sim_steps(self, steps: SimSteps, copy: bool = False):
        """Set the simulation step settings. If copy=True, stores a copy of steps (else ref to steps)."""
        self.__sim_steps = deepcopy(steps) if copy else steps

    def save(self, file_path: Path):
        """Gets the current sim controller settings definition."""
        with file_path.open('w') as output:
            log.info('Saving scenario sim settings to {}', file_path.absolute())
            data = dict(
                variant_id=self.variant_id,
                replic_id=self.replic_id,
                reset_seed=self.__reset_seed,
                auto_seed=self.auto_seed,
                realtime_scale=self.realtime_scale,
                realtime_mode=self.realtime_mode,
                # for animation, it doesn't make sense to save None, must either be True or False; if None,
                # save True since this is the typical value for when will be loaded next time in GUI
                anim_while_run_dyn=self.anim_while_run_dyn,
                sim_steps=self.__sim_steps.to_json(),
            )
            assert data['anim_while_run_dyn'] in (True, False)
            json.dump(data, output, sort_keys=True, indent=2)

    def __str__(self):
        rt_info = 'True, scale={}'.format(self.__realtime_scale) if self.realtime_mode else 'False'
        return dedent("""\
            Animate while running (if mode is dynamic): {}
            Realtime: {}
            Replication #: {}
                Variant #: {}
                Seed (if applied): {} (auto generated: {})
            Sim steps: {}{}""").format(self.anim_while_run_dyn,
                                       rt_info,
                                       self.__replic_id,
                                       self.__variant_id,
                                       self.__reset_seed, self.auto_seed,
                                       # the CR is necessary because of how dedent and indent work across multiple lines
                                       '\n', indent(str(self.sim_steps), ' ' * 4),
                                       )

    variant_id = property(get_variant_id, set_variant_id)
    replic_id = property(get_replic_id, set_replic_id)
    realtime_scale = property(get_realtime_scale, set_realtime_scale)
    reset_seed = property(get_reset_seed, set_reset_seed)
    sim_steps = property(get_sim_steps, set_sim_steps)


class MasterClock:
    """
    This class represents the Master Clock of an Origame scenario.
    """

    def __init__(self):
        # Initialize the master clock from the ori python data structure describing it.
        IOriSerializable.__init__(self)
        self._time_days = 0

    def reset(self):
        """Reset the simulation time of this master clock to 0"""
        self._time_days = 0

    def get_time_days(self) -> float:
        """Get the current simulation time in days since start of simulation"""
        return self._time_days

    def set_time_days(self, value: float):
        """Set the simulation time to given number of days"""
        self._time_days = value

    time_days = property(get_time_days, set_time_days)


class EventStepperMixin:
    """
    Simulation states that can step one event at a time can derive from this mixin class: they simply call
    _step_one_event() to process one event off the queue. Assumes the derived class also
    derives from BaseFsm (specifically, defines self._fsm_owner and self._set_state).
    """

    def _step_one_event(self):
        """
        Process one event off the simulation queue. Does nothing if no events left. Reverts to PAUSED
        state if the event processing raises any exception.
        """
        sim_con = self._fsm_owner
        event_queue = sim_con._event_queue
        if event_queue.get_num_events() <= 0:
            return

        time_days, priority, call_info = event_queue.pop_next()
        if time_days is not None:
            sim_con._set_sim_time_days(time_days)

        is_anim = sim_con.is_animated

        # emit wall clock before event starts, then once again after
        if is_anim:
            wall_clock_start_sec = sim_con._run_timer_wall_clock.total_time_sec
            signals = sim_con.signals
            signals.sig_wall_clock_time_sec_changed.emit(wall_clock_start_sec)

        try:
            call_info.iexec.signal(*call_info.args, _debug_mode=sim_con._debug_mode)

        except Exception as exc:
            log.error("Simulation controller reverting to PAUSED state due to error in signalled part {}",
                      call_info.iexec)
            sim_con._set_last_step_error(exc)
            self._set_state(SimStateClasses.PAUSED)

        if is_anim:
            wall_clock_end_sec = sim_con._run_timer_wall_clock.total_time_sec
            signals.sig_wall_clock_time_sec_changed.emit(wall_clock_end_sec)
            # how long did event take to execute, in user space (wall clock time):
            signals.sig_event_user_time_sec.emit(wall_clock_end_sec - wall_clock_start_sec)
            signals.sig_completion_percentage.emit(sim_con._get_percent_complete(none_allowed=False))


class SimStatesEnum(IntEnum):
    """Enumerate the various states available to the Batch Sim Manager"""
    running, paused, debugging = range(3)


# noinspection PyProtectedMember
class SimStatePaused(BaseFsmState, EventStepperMixin):
    """
    In the paused state, the event queue is not processed. However, stepping through the queue is
    possible, processing the queue can be resumed, and the sim can be restarted
    (which causes a reset and then starts processing events). However, processing of the queue
    is always step-wise: the sim only does one step, then returns, so that the host process can
    control the sim (tell it to start etc).
    """

    state_id = SimStatesEnum.paused

    @override(BaseFsmState)
    def enter_state(self, prev_state):
        self._start_required = None
        self._fsm_owner._run_timer_wall_clock.pause()
        self._fsm_owner._rt_event_delay_timer.pause()
        self.update_anim_mode()

    def sim_update(self):
        """This gets called at high-frequency, but there is nothing to do while paused."""
        pass

    def sim_run(self):
        """
        Start a simulation: executes a reset (see self.reset()), runs the the startup functions, then
        transitions to the running state.
        """
        self._start_required = True
        self._set_state(SimStateClasses.RUNNING)

    def do_reset_steps(self):
        """Reset the scenario simulation state"""
        self._fsm_owner._do_reset(is_sim_paused=True)

    def do_start_steps(self):
        """Run startup parts and transition to running state"""
        self._fsm_owner.run_parts(RunRolesEnum.startup)
        self._set_state(SimStateClasses.RUNNING)

    def sim_step(self):
        """One step of simulation: take next event off queue and execute."""
        self._step_one_event()

    def sim_resume(self):
        """Resume processing event queue, without resetting anything. This just transitions to Running."""
        self._start_required = False
        self._set_state(SimStateClasses.RUNNING)

    def update_anim_mode(self):
        """Animated state is always True when in PAUSED state"""
        self._fsm_owner._set_animation_mode(True)

    def reset_wall_clock_time_no_signal(self, seconds: float = 0.0):
        """Reset the wall clock timer without emitting a signal (the caller takes responsibility for emitting signal)"""
        self._fsm_owner._run_timer_wall_clock.reset(seconds=seconds, pause=True)  # must PAUSE the timer!


# noinspection PyProtectedMember
class SimStateRunning(BaseFsmState, EventStepperMixin):
    """
    In the running state, the SimController must process events from event queue at a rate
    determined by time scale.
    """

    state_id = SimStatesEnum.running

    @override(BaseFsmState)
    def enter_state(self, prev_state: BaseFsmState):
        sim_con = self._fsm_owner
        settings = sim_con._settings
        self.update_anim_mode()
        if prev_state.state_id == SimStatesEnum.paused and prev_state._start_required:
            log.info("Starting sim run of scenario:")
            anim_const_str = 'const={}'.format(sim_con.is_animated) if sim_con.is_anim_mode_const else 'dynamic'
            log.info("    Animation mode: {}", anim_const_str)
            settings_str = str(settings)
            for setting_str in settings_str.split('\n'):
                log.info("    {}", setting_str)
            sim_con._do_reset()
            if settings.sim_steps.start.run_startup_parts:
                sim_con.run_parts(RunRolesEnum.startup)
            else:
                log.info('NOT running Startup parts')

        sim_con._init_pulse_events()
        sim_con._run_timer_wall_clock.resume()
        sim_con._rt_event_delay_timer.resume()
        self.__stop_when_queue_empty = settings.sim_steps.end.stop_when_queue_empty

    def sim_update(self):
        """
        Should be called at high-frequency. It calls the step() at the correct times. It could raise
        an exception if an event raises, or a Finish function raises.
        """
        sim_con = self._fsm_owner
        if sim_con._check_need_stop():
            if sim_con.is_animated:
                sim_con.signals.sig_wall_clock_time_sec_changed.emit(sim_con.realtime_sec)
                sim_con.signals.sig_completion_percentage.emit(sim_con._get_percent_complete(none_allowed=False))

            self.do_end_steps()
            return

        if sim_con._check_do_step():
            self._step_one_event()

            # maybe it's time to pause now:
            should_pause = (sim_con.num_events <= 0 and self.__stop_when_queue_empty)
            # might have already been paused by the script, or by aborting debugging:
            is_paused = (sim_con.state_id == SimStatesEnum.paused)
            if should_pause:
                if is_paused:
                    log.info('Update step done: paused during step')
                else:
                    log.info('Update step done, no more events and STOP-on-EMPTY=True so going to PAUSED state from {}',
                             sim_con.state_name)
                    self.do_end_steps()

    def sim_pause(self):
        """Pause the simulation; just transition to paused"""
        self._set_state(SimStateClasses.PAUSED)

    def do_reset_steps(self):
        """Pause then execute the Reset steps (clear event queue, run parts with Reset role, etc)"""
        self.sim_pause()
        self._fsm_owner._do_reset()

    def do_start_steps(self):
        """Run startup parts"""
        self._fsm_owner.run_parts(RunRolesEnum.startup)

    def do_end_steps(self):
        """Execute the End steps per this state and transition to PAUSED"""
        if self._fsm_owner._settings.sim_steps.end.run_finish_parts:
            self._fsm_owner._run_finish_parts()
        else:
            log.info('NOT running Finish parts')

        self.sim_pause()

    def update_anim_mode(self):
        """Animation status is the setting value while in RUNNING state"""
        enabled = self._fsm_owner._settings.anim_while_run_dyn
        self._fsm_owner._set_animation_mode(enabled)

    def reset_wall_clock_time_no_signal(self, seconds: float = 0.0):
        """Reset the wall clock timer without emitting a signal (the caller takes responsibility for emitting signal)"""
        self._fsm_owner._run_timer_wall_clock.reset(seconds=seconds)  # don't pause the timer!


# noinspection PyProtectedMember
class SimStateDebugging(BaseFsmState):
    """
    In the debugging state, there is no continuous processing of event queue or execution of function parts.
    However, it can resume: if the previous state was running, this will return to running, else it will
    return to paused. Note that this state can be entered from either Paused or Running because both of those
    support running individual parts.
    """

    state_id = SimStatesEnum.debugging

    @override(BaseFsmState)
    def enter_state(self, prev_state):
        self._fsm_owner._run_timer_wall_clock.pause()
        self._fsm_owner._rt_event_delay_timer.pause()
        self.update_anim_mode()
        # self._fsm_owner.stop_auto_loop()

    def sim_update(self):
        """While debugging, nothing to do"""
        pass

    def do_reset_steps(self):
        """Pause then execute the Reset steps"""
        self.debugging_aborted()
        self._fsm_owner._do_reset()

    def update_anim_mode(self):
        """Animated is always True when in Debugging state"""
        self._fsm_owner._set_animation_mode(True)

    def debugging_done(self):
        """Return to the previous state when the user does 'continue'"""
        self._set_state(self._prev_state_class)

    def debugging_aborted(self):
        """Go to the PAUSED state when the user aborts debugging"""
        self._set_state(SimStateClasses.PAUSED)

    def reset_wall_clock_time_no_signal(self, seconds: float = 0.0):
        """Reset the wall clock timer without emitting a signal (the caller takes responsibility for emitting signal)"""
        self._fsm_owner._run_timer_wall_clock.reset(seconds=seconds)  # don't pause the timer!


class SimStateClasses:
    """
    Represents various constants used to decouple the states (from each other and from the state owner (FSM)).
    """
    RUNNING = SimStateRunning
    PAUSED = SimStatePaused
    DEBUGGING = SimStateDebugging


class NoScenarioFolderError(IOError):
    """Exception raised when an operation is only valid with a scenario folder"""
    pass


# call arguments for a function(*args, **kwargs):
CallArgs = Tuple[Sequence[Any], Dict[str, Any]]

# A list of function part's id, path, and signature
SignatureInfo = List[Tuple[int, str, signature]]

# all the following are sim settings types:
SimSettings = Either[SimResetSettings, SimEndSettings, SimStartSettings, SimControllerSettings]


class RunRolePartsError(RuntimeError):
    """Raised when at least one part with a given role fails to run"""

    def __init__(self, role: RunRolesEnum, map_part_to_exc_str: Dict[BasePart, str]):
        """
        :param role: the role common to the parts that were run
        :param map_part_to_exc_str: a mapping of part paths to exception messages
        """
        self.map_part_to_exc_str = map_part_to_exc_str
        # part_errors = ['- {}: {}'.format(part, msg) for part, msg in map_part_to_exc_str.items()]
        part_ids = ', '.join(str(part) for part in map_part_to_exc_str)
        msg = 'Some parts with role "{}" could not be run: {}'.format(role.name, part_ids)
        super().__init__(msg)


class SimController(IOriSerializable, IPyDebuggingListener, IScenAlertSource, IFsmOwner):
    """
    Controls the simulation of the scenario by managing its event queue, and master clock.
    The controller is a finite state machine, implemented via the classes derived from BaseFsmState.

    Animation:
    - Anim while run dyn setting: the setting true/false indicating whether animation should be on/off in Running state
    - Animation mode: whether a GUI should reflect the current state of the Scenario as it evolves; it is always True
      while in Paused and Debugging state; it is "Runtime Animation Setting" while in Running state.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    SETTINGS_FILE_EXT = '.ssj'
    SETTINGS_FILE_NAME = 'scen_sim_settings'
    # value emitted when there is no percent completion available (because there are no stop time conditions):
    PERCENT_COMPLETE_UNDEFINED = -1

    class Signals(BridgeEmitter):
        sig_state_changed = BridgeSignal(int)  # SimStatesEnum value
        sig_replic_info_changed = BridgeSignal(int, int)  # variant ID, replication ID
        sig_animation_mode_changed = BridgeSignal(bool)  # new value of animation mode
        sig_anim_while_run_dyn_setting_changed = BridgeSignal(bool)  # new value of setting
        sig_debug_mode_changed = BridgeSignal(bool)  # new value of debug mode
        sig_sim_time_days_changed = BridgeSignal(float, float)  # absolute time (days), delta time (days)
        sig_wall_clock_time_sec_changed = BridgeSignal(float)  # wall clock value in seconds, since last event popped
        sig_event_user_time_sec = BridgeSignal(float)  # wall clock seconds between start and end of part execution
        sig_step_settings_changed = BridgeSignal(str)  # string dump of a JSON structure for settings
        sig_has_role_parts = BridgeSignal(int, bool)  # (run role enum, True if has at least one part with role
        sig_max_sim_time_days_changed = BridgeSignal(float)
        sig_max_wall_clock_time_sec_changed = BridgeSignal(float)
        sig_completion_percentage = BridgeSignal(int)  # 0-100, or < 0 if no % available (no max times set)
        sig_settings_changed = BridgeSignal()

    # --------------------------- class-wide methods --------------------------------------------

    @classmethod
    def get_settings_path(cls, prefix: Optional[Path]) -> Path:
        """Get the path to the scenario's sim settings (.ssj) file. """
        sim_settings_name = Path(cls.SETTINGS_FILE_NAME).with_suffix(cls.SETTINGS_FILE_EXT)
        return sim_settings_name if prefix is None else prefix / sim_settings_name

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, event_queue: EventQueue, anim_mode: Either[AnimationMode, bool] = True,
                 alert_parent: IScenAlertSource = None):
        """
        :param event_queue: the simulation event queue to manage
        :param anim_mode: the animation mode to use; can be an instance of AnimationMode, or a pure boolean
        """
        IOriSerializable.__init__(self)
        IScenAlertSource.__init__(self)
        IFsmOwner.__init__(self)
        self.signals = SimController.Signals()

        # internal attributes (non-public, but can't be private as need access by state classes):
        self._settings = SimControllerSettings()
        self.__alert_parent = alert_parent
        # next attrib is used to optimize checking whether we need to stop; using bool(get_alerts()) is too expensive!
        self.__last_sim_step_was_error = False

        self._run_timer_wall_clock = ClockTimer(pause=True)
        self._rt_event_delay_timer = ClockTimer()  # while in realtime mode

        self._event_queue = event_queue

        # private attributes
        self.__replic_folder = None
        self.__master_clock = MasterClock()
        self.__animation_mode = anim_mode
        self.__anim_mode_dyn = not isinstance(anim_mode, bool)
        self.__pulse_parts = []

        # animation mode can be static or dynamic: if dynamic, it has the set_state; if static, need different config
        assert self._settings.anim_while_run_dyn is True
        assert isinstance(anim_mode, (bool, AnimationMode))

        self._event_queue.set_anim_mode(bool(self.__animation_mode))

        self.__parts_with_roles = {}
        for role in RunRolesEnum:
            self.__parts_with_roles[role] = []

        self._debug_mode = False
        PyDebugger.register_for_debug_events(self)
        self._state = SimStatePaused(None, fsm_owner=self)

    @override(IPyDebuggingListener)
    def debugger_hit_breakpoint(self):
        self._state._set_state(SimStateClasses.DEBUGGING)

    @override(IPyDebuggingListener)
    def debugging_done(self):
        self._state.debugging_done()

    @override(IPyDebuggingListener)
    def debugging_aborted(self):
        self._state.debugging_aborted()

    def register_part_with_role(self, part: BasePart, role: RunRolesEnum):
        """
        This function registers the specified part/role with this instance.
        :param part: The part being registered. Should be a function part only.
        :param role: The role the part is being registered as supporting.
        """
        if part not in self.__parts_with_roles[role]:
            self.__parts_with_roles[role].append(part)
            self.signals.sig_has_role_parts.emit(role.value, True)

    def unregister_part_with_role(self, part: BasePart, role: RunRolesEnum):
        """
        Un-registers the given part/role from the simulation. Does not update the part itself. Does nothing if the
        part was never registered.
        :param part: The part to un-register.
        :param role: The role the part is being un-registered from
        """
        if part in self.__parts_with_roles[role]:
            self.__parts_with_roles[role].remove(part)
            has_parts = (self.__parts_with_roles[role] != [])
            self.signals.sig_has_role_parts.emit(role.value, has_parts)

    def has_role_parts(self, role: RunRolesEnum) -> bool:
        """Check if there are parts of given role registered with the sim controller"""
        return self.__parts_with_roles[role] != []

    def register_pulse_part(self, pulse: Decl.PulsePart):
        """
        This function registers the specified pulse part with this instance.
        :param pulse: The pulse part being registered.
        """
        if pulse not in self.__pulse_parts:
            self.__pulse_parts.append(pulse)

    def unregister_pulse_part(self, pulse: Decl.PulsePart):
        """
        Un-registers the given pulse part from the simulation. Does not update the part itself. Does nothing if the
        part was never registered.
        :param pulse: The pulse part to un-register.
        """
        if pulse in self.__pulse_parts:
            self.__pulse_parts.remove(pulse)

    def add_event(self, iexec_part: IExecutablePart, args: Tuple = None, time: float = None,
                  priority: float = 0) -> CallInfo:
        """
        Add the given executable part to the simulation event queue at given time and priority level, and
        with the given call arguments.
        :param iexec_part: executable part to add to event queue
        :param args: arguments that will be passed to executable part when this event gets processed
        :param time: simulation time at which event should be processed
        :param priority: priority, within given time bin, of event
        :return: the created CallInfo object
        """
        return self._event_queue.add_event(time, priority, iexec_part, args)

    def remove_event(self, time: float, priority: float, call_info: CallInfo, restorable: bool = False):
        """
        Remove an event from the queue.

        :param time: the simulation time (in days) of event to be removed
        :param priority: numerical valu of priority of event to be removed (can be ASAP_PRIORITY_VALUE if ASAP)
        :raise KeyError: if invalid time or priority
        :raise ValueError if invalid call_info.
        """
        self._event_queue.remove_event(time, priority, call_info, restorable=restorable)

    def get_all_events(self, filter_part: IExecutablePart = None) -> List[EventInfo]:
        """
        Return the event queue's events, possibly filtered on a particular part.
        :param filter_part: A part to filter the list of events on.
        """
        return self._event_queue.get_all_as_list(filter_part=filter_part)

    def remove_all_events(self, iexec: IExecutablePart, restorable: bool) -> Optional[List[Tuple[EventInfo, int]]]:
        """
        Remove all events pertaining to a specific part.
        :param iexec: the executable part for which events should be removed
        :param restorable: set to True if the removed events might be restored at a later time
        :return: if restorable removal, returns a list of pairs, each pair consisting of an event info and associated
            predecessor ID needed if/when event gets restored; the list should not be changed, and should be given
            as-is to restore_all_events()
        """
        events = self._event_queue.get_all_as_list(filter_part=iexec)
        # events are in chronological order, so to remove them, do inverse order so that the predecessor is always
        # present
        events_data = []
        for event in reversed(events):
            pred_id = self._event_queue.remove_event(event.time_days, event.priority, event.call_info,
                                                     restorable=restorable)
            events_data.insert(0, (event, pred_id))

        if restorable:
            return events_data
        else:
            return None

    def restore_all_events(self, events_data: List[Tuple[EventInfo, int]]):
        """Restore a list of events, obtained from an earlier call to remove_all_events."""
        for (event, pred_id) in events_data:
            self._event_queue.restore_event(event.time_days, event.priority, event.call_info, pred_id)

    def get_last_step_error_info(self) -> ScenAlertInfo:
        """Get the error information for the last sim event executed. None if no error."""
        step_sim_errs = self.get_alerts(level=ScenAlertLevelEnum.error, category=ErrorCatEnum.sim_step)
        return step_sim_errs.pop() if step_sim_errs else None

    def get_num_events(self) -> int:
        """Number of events on the queue."""
        return self._event_queue.get_num_events()

    def get_is_animated(self) -> bool:
        """
        Whether parts that change their state should emit signals to indicate state changes. If animation
        mode is constant, this returns the constant (True or False). If dynamic, then while paused,
        this method always returns True, whereas while running, it returns the same value as
        self.settings.anim_while_run_dyn. See set_anim_while_run_dyn_setting() docstring.
        """
        return bool(self.__animation_mode)

    def get_is_anim_mode_const(self) -> bool:
        """
        Is the animation mode constant? True if it is constant (regardless of whether the constant is
        True or False), and False if it is dynamic.
        """
        return not self.__anim_mode_dyn

    def get_is_anim_mode_dynamic(self) -> bool:
        """
        Is the animation mode dynamic? This is the same as "not self.get_is_anim_mode_const()".
        """
        return self.__anim_mode_dyn

    def on_scenario_saved(self):
        """
        When scenario saved to a file, attempt to save the associated sim settings file. If not possible (locked
        etc), log a warning.
        """
        try:
            self.save_settings()
        except IOError as exc:
            log.warning('Could not save scenario\'s simulation settings: {}', exc)
            log.warning('    Will try again at next scenario save')

    def on_scenario_loaded(self):
        """
        When scenario file has been loaded, attempt to load the associated sim settings file. If not found,
        log a warning but continue.
        """
        try:
            self.load_settings()
        except FileNotFoundError:
            log.warning('Could not load the sim settings for this scenario')

    def on_scenario_unlinked(self):
        """
        When scenario file has been unlinked from filesystem, remove the associated settings file.
        Log a warning if the file could not be removed (locked, etc).
        """
        try:
            assert self.__replic_folder is not None
            settings_path = self.get_settings_path(self.__replic_folder)
            log.info('Removing scenario sim settings file {}', settings_path)
            settings_path.unlink()

        except IOError:
            log.warning('Could not unlink the sim settings file {}', settings_path)

    # runtime state of the controller:
    is_anim_mode_const = property(get_is_anim_mode_const)
    is_anim_mode_dynamic = property(get_is_anim_mode_dynamic)
    is_animated = property(get_is_animated)
    num_events = property(get_num_events)
    last_step_error_info = property(get_last_step_error_info)

    # ------------ misc settings ------------------------------------------------

    def get_settings(self, copy: bool = False) -> SimControllerSettings:
        """Get the simulation controller settings"""
        return deepcopy(self._settings) if copy else self._settings

    def set_settings(self, settings: SimControllerSettings, copy: bool = False):
        """Set the simulation controller settings"""
        self._settings = deepcopy(settings) if copy else settings
        self.signals.sig_settings_changed.emit()
        if self.__replic_folder is not None:
            try:
                self.save_settings()
                # Oliver FIXME ASAP: transmit object rather than jsonified object
                self.signals.sig_step_settings_changed.emit(self.get_step_settings_as_json_str())
            except IOError:
                log.warning('Failed to save the new settings of BatchSimManager, will try again at next save or set')

    def change_settings(self, _save: bool = True, **settings):
        """
        Change some sim settings. For changing individual settings.sim_steps, use change_step_settings().
        :param _save: if False, the settings will not be saved to file system
        """
        self.__change_settings(self._settings, _save, **settings)

    def change_step_settings(self, _save: bool = True,
                             reset: Dict[str, Any]=None, start: Dict[str, Any]=None, end: Dict[str, Any]=None):
        """
        Change some settings of self.settings.sim_steps.end, reset, and/or start.
        Example: sim.change_step_settings(reset=dict(clear_queue=False), end=dict(run_finish_parts=False))
        :param _save: if False, the settings will not be saved to file system
        :param reset: a dictionary of settings where keys match attributes of SimResetSettings
        :param start: a dictionary of settings where keys match attributes of SimStartettings
        :param end: a dictionary of settings where keys match attributes of SimEndSettings
        """
        if reset:
            self.__change_settings(self._settings.sim_steps.reset, False, **reset)
        if start:
            self.__change_settings(self._settings.sim_steps.start, False, **start)
        if end:
            self.__change_settings(self._settings.sim_steps.end, False, **end)
        if _save:
            self.save_settings(fail_ok=True)

    def get_step_settings_as_json_str(self) -> str:
        """Get the sim settings as a string that represents a JSON object (can be given to json.loads())"""
        return json.dumps(self._settings.sim_steps.to_json())

    def save_settings(self, fail_ok: bool = False):
        """Save the simulation settings to the scenario's folder."""
        if self.__replic_folder is None:
            if fail_ok:
                return
            raise NoScenarioFolderError

        try:
            self._settings.save(self.get_settings_path(self.__replic_folder))
        except:
            if not fail_ok:
                raise

    def load_settings(self):
        """Load the simulation settings from the scenario's folder."""
        if self.__replic_folder is None:
            raise NoScenarioFolderError

        try:
            new_settings = SimControllerSettings.load(self.get_settings_path(self.__replic_folder))
            self._settings = new_settings
            self.signals.sig_step_settings_changed.emit(self.get_step_settings_as_json_str())

        except FileNotFoundError:
            # if it doesn't exist, it must be an old scenario folder, try saving it; don't fail if can't save,
            # because it is not critical that it be there, a save attempt will every time the settings are saved
            log.warning('Scenario sim settings file {} not found in {}, cannot load; try again later.',
                        self.SETTINGS_FILE_NAME, self.__replic_folder)
            raise

    def get_reset_seed(self) -> int:
        """Random seed that gets used whenever a reset is performed."""
        return self._settings.reset_seed

    def set_auto_seeding(self, auto: bool, seed: int = None, _save: bool = True):
        """
        Change the auto-seeding mode.
        :param auto: when True, a new random seed will be used at every simulation run
        :param seed: when auto=False, this is the seed to use
        """
        if auto:
            self.__change_settings(self._settings, _save, auto_seed=True)
        else:
            # need to set auto-seed False first because can't change seed when auto-seed True
            self.__change_settings(self._settings, False, auto_seed=False)
            self.__change_settings(self._settings, _save, reset_seed=seed)

    def get_replic_id(self) -> int:
        """The replication ID used in this/next simulation RUNNING state. Starts at 1."""
        return self._settings.replic_id

    def set_replic_id(self, value: int, _save: bool = True):
        """Set the replication ID to be used in this/next simulation RUNNING state. Must be >= 1."""
        if value != self._settings.replic_id:
            self.__change_settings(self._settings, _save, replic_id=value)
            self.signals.sig_replic_info_changed.emit(self._settings.variant_id, self._settings.replic_id)

    def get_variant_id(self) -> int:
        """The variant ID used in this/next simulation RUNNING state. Starts at 1."""
        return self._settings.variant_id

    def set_variant_id(self, value: int, _save: bool = True):
        """Set the variant ID to be used in this/next simulation RUNNING state. Must be >= 1."""
        if value != self._settings.variant_id:
            self.__change_settings(self._settings, _save, variant_id=value)
            self.signals.sig_replic_info_changed.emit(self._settings.variant_id, self._settings.replic_id)

    def get_replic_folder(self) -> Path:
        """Get the folder used by this simulation. Unless this simulation is batch run, this is the scenario folder."""
        return self.__replic_folder

    def set_replic_folder(self, folder_path: PathType):
        """Set the folder used by this simulation. Should be called only by the Scenario or Replication."""
        self.__replic_folder = Path(folder_path)

    def get_anim_while_run_dyn_setting(self) -> bool:
        """
        Return True if any UI showing this simulation should be animated while sim controller is in RUNNING state.
        This will be None if animation *mode* is constant (i.e., if animation mode cannot be changed, then there
        is no runtime animation setting).
        """
        return self._settings.anim_while_run_dyn

    def set_anim_while_run_dyn_setting(self, enabled: bool, _save: bool = True):
        """
        Enable a GUI or a scenario part script to change whether the UI showing this simulation should be
        animated while simulation *runs*. This changes self.settings.anim_while_run_dyn based on 'enabled',
        and emits a signal, but this setting is only *used* by the controller to manage animation while
        in the *running* state:

        - while sim paused:

          - changes self.settings.anim_while_run_dyn based on 'enabled', and emits a signal
          - does nothing to actual shared animation mode (leaves it True since while paused, any changes
            made to the scenario, such as resulting from an edit, must always be visible in the UI immediately)
          - self.is_animated remains True.

        - while sim running:

          - changes self.settings.anim_while_run_dyn based on 'enabled', and emits a signal
          - the shared animation mode that all parts can see is immediately changed to match 'enabled'
          - self.is_animated matches 'enabled'.

        NOTE: This method exists only so the user can toggle runtime animation from a GUI or from a Function
        Part (or other scripted part). Additionally it enables the GUI to show the correct state of the setting
        regardless of where it was set from (GUI or script). BUT animation is a GUI-centric concept that
        involves some overhead; so when animation is not needed (Console variant, some tests), the
        test/application/process should call set_future_anim_mode_constness(False) (defined in the scenario module)
        before the scenario is loaded, so that some optimizations are possible. Moreover, this will cause
        self.set_anim_while_run_dyn_setting() to do nothing, thus making a script that changes animation mode
        runnable unmodified with and without GUI.

        :param enabled: if True, then the scenario components will emit signals to notify of scenario state
            changes, regardless of state (paused or running); if False, then then the scenario components will
            emit signals to notify of scenario state changes ONLY WHILE sim is PAUSED.
        :param _save: internal parameter so that saving can be skipped
        """
        assert self._settings.anim_while_run_dyn in (True, False)
        if enabled != self._settings.anim_while_run_dyn:
            _save = _save and self.is_anim_mode_dynamic
            self.__change_settings(self._settings, _save, anim_while_run_dyn=enabled)
            self._state.update_anim_mode()
            self.signals.sig_anim_while_run_dyn_setting_changed.emit(self._settings.anim_while_run_dyn)

    def get_debug_mode(self) -> bool:
        return self._debug_mode

    def set_debug_mode(self, enabled: bool = True):
        """
        Set debug mode. When true, will cause every executable popped from the event queue to be run in debug
        mode, and hence to stop at breakpoints.
        """
        self._debug_mode = enabled
        self.signals.sig_debug_mode_changed.emit(enabled)

    # static configuration of the controller:
    replic_folder = property(get_replic_folder, set_replic_folder)

    debug_mode = property(get_debug_mode)
    settings = property(get_settings)
    # read-only shortcuts to legacy items within settings:
    replic_id = property(get_replic_id)
    variant_id = property(get_variant_id)
    reset_seed = property(get_reset_seed)

    # -------------- TIME-related settings and state -----------------------------

    def reset_sim_time(self, days: float = 0.0, adjust_queue_times: bool = False):
        """Resets the elapsed sim time to zero"""
        if adjust_queue_times:
            delta = self.sim_time_days - days
            log.info("Sim controller setting all event time stamps back by {} days", delta)
            self._event_queue.move_times(-delta)
        log.info("Resetting sim time to {} days", days)
        self._set_sim_time_days(days)

    def reset_wall_clock_time(self, seconds: float = 0.0):
        """Resets the elapsed wall clock time to zero"""
        log.info('Resetting wall clock time to {} seconds', seconds)
        self._state.reset_wall_clock_time_no_signal(seconds=seconds)
        self.signals.sig_wall_clock_time_sec_changed.emit(seconds)
        self.signals.sig_completion_percentage.emit(self._get_percent_complete(none_allowed=False))

    def get_sim_time_days(self) -> float:
        """Current sim time according to the master clock."""
        return self.__master_clock.time_days

    def get_realtime_sec(self) -> float:
        """Get number of seconds since the start of the sim of scenario"""
        return self._run_timer_wall_clock.total_time_sec

    def is_realtime(self) -> bool:
        return self._settings.realtime_mode

    def set_realtime_mode(self, status: bool = True, _save: bool = True):
        """
        When True, the events are processed according to (scaled) realtime clock, else immediately. 
        :param _save: internal parameter so that saving can be skipped
        """
        assert status in (True, False)
        if status != self._settings.realtime_mode:
            self.__change_settings(self._settings, _save, realtime_mode=status)
            if status:
                self._rt_event_delay_timer.reset()

    def get_realtime_scale(self) -> float:
        """Time scale currently in use for real-time mode"""
        return self._settings.realtime_scale

    def set_realtime_scale(self, factor: float, _save: bool = True):
        """
        A time scale > 1 increases the real-time, < 1 decreases it. So to run a real-time sim 4 times faster,
        use factor = 4; to run it 4 times slower, use factor = 1/4.
        """
        self.__change_settings(self._settings, _save, realtime_scale=factor)

    def get_max_wall_clock_sec(self) -> float:
        return self._settings.sim_steps.end.max_wall_clock_sec

    def set_max_wall_clock_sec(self, time_sec: float, _save: bool = True):
        """
        Make the sim auto-transition from run to paused when wall clock time since Run exceeds a threshold.
        :param time_sec: the time in seconds at which to transition to paused; a value of 0 will be treated
            as None, causing the setting to be removed
        :param _save: internal parameter so that saving can be skipped
        """
        time_sec = time_sec or None  # remove setting if 0.0
        self.__change_settings(self._settings.sim_steps.end, _save, max_wall_clock_sec=time_sec)

        self.signals.sig_step_settings_changed.emit(self.get_step_settings_as_json_str())
        # Qt does not like emitting None, so emit 0.0 instead; 0 is interpreted as "no time set" in front-end
        self.signals.sig_max_wall_clock_time_sec_changed.emit(time_sec or 0.0)  # cannot emit None
        self.signals.sig_completion_percentage.emit(self._get_percent_complete(none_allowed=False))

    def is_max_wall_clock_elapsed(self) -> bool:
        """True if the real time since last start/reset has exceeded the max configured"""
        end_settings = self._settings.sim_steps.end
        return (end_settings.max_wall_clock_sec
                and (self._run_timer_wall_clock.total_time_sec > end_settings.max_wall_clock_sec))

    def get_max_sim_time_days(self) -> float:
        """Get the max sim time (in days) that was set; None if no max was set"""
        return self._settings.sim_steps.end.max_sim_time_days

    def set_max_sim_time_days(self, time_days: float, _save: bool = True):
        """
        Make the sim auto-transition from run to paused when sim time exceeds a threshold.
        :param time_days: the time at which to transition to paused; the sim time will be automatically
            advanced to this time; a value of 0 will be treated as None, causing the setting to be removed
        :param _save: internal parameter so that saving can be skipped
        """
        time_days = time_days or None
        self.__change_settings(self._settings.sim_steps.end, _save, max_sim_time_days=time_days)

        self.signals.sig_step_settings_changed.emit(self.get_step_settings_as_json_str())
        # Qt does not like emitting None, so emit 0.0 instead; 0 is interpreted as "no time set" in front-end
        self.signals.sig_max_sim_time_days_changed.emit(time_days or 0.0)  # cannot emit None

    def is_max_sim_time_elapsed(self) -> bool:
        """
        Returns true if the last event popped had a sim time larger than max set; false otherwise (including if
        no max set)
        """
        max_sim_time_days = self._settings.sim_steps.end.max_sim_time_days
        return max_sim_time_days and (self.sim_time_days >= max_sim_time_days)

    max_wall_clock_sec = property(get_max_wall_clock_sec)
    max_sim_time_days = property(get_max_sim_time_days)
    realtime_scale = property(get_realtime_scale)
    realtime_mode = property(is_realtime)

    max_wall_clock_elapsed = property(is_max_wall_clock_elapsed)
    max_sim_time_elapsed = property(is_max_sim_time_elapsed)
    sim_time_days = property(get_sim_time_days)
    realtime_sec = property(get_realtime_sec)

    # ------------ everything else but TIME -----------------------------

    def sim_run(self):
        """Start simulating the scenario. Only works if paused."""
        try:
            self._state.sim_run()
        except RunRolePartsError:
            prev_state = None
            self._state = SimStatePaused(prev_state, fsm_owner=self)
            self._on_state_changed(prev_state)
            raise

    def sim_update(self):
        """
        This should be called at high-frequency so the controller has a chance to update itself.
        This just delegates to the current state. All states support this.
        """
        self._state.sim_update()

    def sim_step(self):
        """Advance simulation of the scenario by one step. Not all states support this."""
        if self.__last_sim_step_was_error:
            raise RuntimeError('Last step failed, cannot step again (reset the sim first)')
        self._state.sim_step()

    def sim_pause(self):
        """Step simulating the scenario. Not all states support this."""
        self._state.sim_pause()

    def sim_resume(self):
        """Resume simulating the scenario. Not all states support this."""
        if self.__last_sim_step_was_error:
            raise RuntimeError('Last step failed, cannot resume (reset the sim first)')
        self._state.sim_resume()

    def sim_pause_resume(self):
        """If paused, resume; if running, pause."""
        if self.is_state(SimStatesEnum.paused):
            self.sim_resume()
        else:
            self.sim_pause()

    def do_reset_steps(self):
        """Execute the configured Reset steps of the scenario. If not paused, pauses first."""
        self._state.do_reset_steps()

    def do_start_steps(self):
        """Execute the configured Start steps of the scenario, including transitioning to running."""
        self._state.do_start_steps()

    def do_end_steps(self):
        """Execute the configured End steps of the scenario, including transitioning to paused."""
        self._state.do_end_steps()

    def run_parts(self, role: RunRolesEnum, map_part_id_to_call_args: Dict[int, CallArgs] = None):
        """
        Run all the parts that have given role. The parts are run according to their role priority, from
        highest to smallest.
        :param map_part_id_to_call_args: the key is the part session ID, the CallArgs will be unpacked into
            args and kwargs and given as call args as part(*args, **kwargs).
        :raise RunRolePartsError: if one or more parts raised an error
        """
        parts_with_role = self.__parts_with_roles[role]
        parts_with_role.sort(key=lambda p: p.get_role_priority(role), reverse=True)
        log.info('Running {} parts: {} found', get_enum_val_name(role).capitalize(), len(parts_with_role))
        if parts_with_role and len(parts_with_role) > 1:
            log.debug('    Run-role prioritizing: {}', ', '.join(p.name for p in parts_with_role))
        map_part_id_to_call_args = map_part_id_to_call_args or {}
        excepts = {}
        for part in parts_with_role:
            args, kwargs = map_part_id_to_call_args.get(part.SESSION_ID, ([], {}))
            try:
                part.call(*args, _debug_mode=self._debug_mode, **kwargs)
            except Exception as exc:
                log.error('Part {} raised exception during call: {}', part, exc)
                excepts[part] = str(exc)

        if excepts:
            raise RunRolePartsError(role, excepts)

    def clear_event_queue(self):
        """
        Clear event queue.
        """
        self._event_queue.clear()

    def get_setup_parts_signature_info(self) -> SignatureInfo:
        """
        Gets a list of tuples, each of which contains the part session id, path, and signature of each of
        the Setup parts. The parts are run according to their role priority, from highest to smallest.
        :return: The part session id, path, and signature info.
        """
        parts_with_role = self.__parts_with_roles[RunRolesEnum.setup]
        parts_with_role.sort(key=lambda p: p.get_role_priority(RunRolesEnum.setup), reverse=True)
        return [(setup_part.SESSION_ID, setup_part.get_path(), setup_part.get_signature())
                for setup_part in parts_with_role]

    def check_last_step_was_error(self) -> bool:
        """
        Return True if last sim step (via sim_update or sim_step) failed. Further attempts to sim_update(),
        sim_resume() or sim_step() will cause an exception until the do_reset_steps() has been called.
        """
        return self.__last_sim_step_was_error

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    last_step_was_error = property(check_last_step_was_error)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenAlertSource)
    def _get_source_name(self) -> str:
        """
        Returns "SimController"
        :return: The source name
        """
        return "SimController"

    @override(IScenAlertSource)
    def _get_alert_parent(self) -> IScenAlertSource:
        """If alerts should be propagated up to a "parent" alert source, override this method to return it"""
        return self.__alert_parent

    @override(IScenAlertSource)
    def _notify_alert_changes(self) -> bool:
        return bool(self.__animation_mode)

    @internal(SimStateRunning)
    def _check_need_stop(self) -> bool:
        """Returns True if sim should stop (run End steps and go to paused state), False otherwise"""
        next_time_days = self._event_queue.get_next_time_days()
        if next_time_days is None:
            # if no more events, stop only if setting True:
            pause = self._event_queue.num_events <= 0 and self._settings.sim_steps.end.stop_when_queue_empty
            if pause:
                log.info('Transition to paused: no more events!')
            return pause

        end_settings = self._settings.sim_steps.end
        if end_settings.max_wall_clock_sec is not None:
            if self._run_timer_wall_clock.total_time_sec > end_settings.max_wall_clock_sec:
                log.info("Transition to paused: max wall clock time {} sec will be exceeded at next event (t={} sec)",
                         end_settings.max_wall_clock_sec, next_time_days)
                return True

        if self._settings.realtime_mode:
            scaled_realtime_sec = (self.sim_time_days * SECONDS_PER_DAY
                                   + self._rt_event_delay_timer.total_time_sec * self._settings.realtime_scale)
            # log.debug("Sim time vs real time: {} {} {}", sim_time_sec, scaled_realtime_sec)
            if (end_settings.max_sim_time_days
                and scaled_realtime_sec >= end_settings.max_sim_time_days * SECONDS_PER_DAY):
                log.info("Transition to paused: max sim time {} days reached in realtime mode",
                         end_settings.max_sim_time_days)
                self._set_sim_time_days(end_settings.max_sim_time_days)
                return True

            return False

        # immediate mode:
        assert not self._settings.realtime_mode
        if end_settings.max_sim_time_days and next_time_days >= end_settings.max_sim_time_days:
            log.info("Transition to paused: max sim time {} days will be exceeded at next event (t={} days)",
                     end_settings.max_sim_time_days, next_time_days)
            self._set_sim_time_days(end_settings.max_sim_time_days)
            return True

        return False

    @internal(SimStateRunning)
    def _check_do_step(self) -> bool:
        """Return True if a sim step should be executed, False if event should not be processed"""
        if self.__last_sim_step_was_error:
            return False

        next_time_days = self._event_queue.get_next_time_days()
        if next_time_days is None:
            # there are no more events, nothing to do:
            return False

        if self._settings.realtime_mode:
            scaled_realtime_sec = (self.sim_time_days * SECONDS_PER_DAY
                                   + self._rt_event_delay_timer.total_time_sec * self._settings.realtime_scale)
            sim_time_sec = next_time_days * SECONDS_PER_DAY
            # log.debug("Sim time vs real time: {} {} {}", sim_time_sec, scaled_realtime_sec)
            if scaled_realtime_sec < sim_time_sec:
                return False

            # it's time for the next event to be processed:
            self._rt_event_delay_timer.reset()
            return True

        return True

    @override(IFsmOwner)
    def _on_state_changed(self, prev_state: BaseFsmState):
        self.signals.sig_state_changed.emit(self._state.state_id.value)

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):

        assert self.state_id == SimStatesEnum.paused

        if ori_data.schema_version <= OriSchemaEnum.version_2_1:
            if ori_data.get(ScKeys.MASTER_CLK):
                self._set_sim_time_days(ori_data[ScKeys.MASTER_CLK])

            # runtime animation, if dynamic (for legacy scenarios: defaults to True if missing or None):
            anim_while_run_dyn = ori_data.get(ScKeys.ANIM_WHILE_RUN_DYN, True)
            if anim_while_run_dyn is None:
                anim_while_run_dyn = True
            self.set_anim_while_run_dyn_setting(anim_while_run_dyn, _save=False)

            # sim time settings
            if ScKeys.REALTIME_MODE in ori_data:
                self.set_realtime_mode(ori_data[ScKeys.REALTIME_MODE], _save=False)
            if ScKeys.REALTIME_SCALE in ori_data:
                self.set_realtime_scale(ori_data[ScKeys.REALTIME_SCALE], _save=False)

            # replication info
            if ScKeys.REPLIC_ID in ori_data:
                self.set_replic_id(ori_data[ScKeys.REPLIC_ID], _save=False)
            if ScKeys.VARIANT_ID in ori_data:
                self.set_variant_id(ori_data[ScKeys.VARIANT_ID], _save=False)
            if ScKeys.RANDOM_SEED in ori_data:
                self.set_auto_seeding(False, seed=ori_data[ScKeys.RANDOM_SEED], _save=False)

            # max run times
            if ScKeys.MAX_SIM_TIME_DAYS in ori_data:
                self.set_max_sim_time_days(ori_data[ScKeys.MAX_SIM_TIME_DAYS], _save=False)
            if ScKeys.MAX_WALL_CLOCK_SEC in ori_data:
                self.set_max_wall_clock_sec(ori_data[ScKeys.MAX_WALL_CLOCK_SEC], _save=False)

        else:
            if ori_data.get(ScKeys.SIM_TIME_DAYS):
                self.reset_sim_time(ori_data[ScKeys.SIM_TIME_DAYS])

            if ori_data.get(ScKeys.WALL_CLOCK_SEC):
                self.reset_wall_clock_time(ori_data[ScKeys.WALL_CLOCK_SEC])

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        # NOTE: it would be nice to allow this call only while paused, but replications call this after sim
        # done yet the sim isn't always in Paused (because
        # if self._state.state_id != SimStatesEnum.paused:
        #     raise RuntimeError('Getting the ORI defn of Sim Controller is only allowed while paused')
        return self.__get_ori_def_local()

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update(self.__get_ori_def_local())

    @internal(BaseFsmState)
    def _set_animation_mode(self, value: bool = True):
        """
        Control whether animation is actually on. This should be called by state object only. For example, if
        runtime animation is False, but we're in paused state, then is_animated is actually True, because
        the runtime setting does not affect the paused state.
        """
        if self.__anim_mode_dyn and self.__animation_mode != value:
            self.__animation_mode.set_state(value)
            log.info('Sim run animation mode is now {}', self.__animation_mode)
            self._event_queue.set_anim_mode(value)
            self.signals.sig_animation_mode_changed.emit(bool(self.__animation_mode))

    @internal(BaseFsmState)
    def _get_parts(self, role: RunRolesEnum) -> List[BasePart]:
        """
        This function returns a list of all parts registered with this instance that support the specified role.
        """
        return self.__parts_with_roles[role]

    @internal(SimStateRunning, SimStatePaused)
    def _set_sim_time_days(self, time_days: float, signal: bool = True):
        """Should only be called internally to set the sim time"""
        if time_days != self.__master_clock.time_days:
            delta = time_days - self.__master_clock.time_days
            self.__master_clock.time_days = time_days
            if signal:
                self.signals.sig_sim_time_days_changed.emit(time_days, delta)

    @internal(SimStateRunning, SimStatePaused)
    def _set_last_step_error(self, exc: Exception):
        self._add_alert(ScenAlertLevelEnum.error, ErrorCatEnum.sim_step, str(exc))
        log.error("Sim step error: {}", exc)
        self.__last_sim_step_was_error = True

    @internal(SimStateRunning, SimStatePaused)
    def _do_reset(self, is_sim_paused: bool = False):
        """
        Reset the scenario simulation state: reset run timer, event queue times (optional), simulation time,
        and seed of the random # generator, then runs the reset functions. This method must only be called from
        one of the FSM state objects.
        """
        if self._settings.realtime_mode:
            # if state is paused, we want to pause the realtime event timer
            self._rt_event_delay_timer.reset(pause=is_sim_paused)

        self._clear_own_alerts(ScenAlertLevelEnum.error, ErrorCatEnum.sim_step)
        self.__last_sim_step_was_error = False
        reset_settings = self._settings.sim_steps.reset

        if reset_settings.clear_event_queue:
            log.info('Clearing sim event queue')
            self.clear_event_queue()
        else:
            log.info('NOT clearing sim event queue')

        if reset_settings.zero_wall_clock:
            self.reset_wall_clock_time()
        else:
            log.info('NOT resetting wall clock time to 0')

        if reset_settings.zero_sim_time:
            self.reset_sim_time()
        else:
            log.info("NOT resetting sim time to 0")

        if reset_settings.apply_reset_seed:
            if self._settings.auto_seed:
                if self._settings.reset_seed is not None:
                    log.debug("WARNING: Auto-seed True but Reset-Seed is not None")
                reset_seed = new_seed()
                log.info("Auto-generated new random number generator seed: {}", reset_seed)
            else:
                reset_seed = self._settings.reset_seed

            log.info("Applying seed {} to builtin random number generator", reset_seed)
            random.seed(reset_seed)

        else:
            log.info("NOT re-applying seed to builtin random number generator")

        if reset_settings.run_reset_parts:
            self.run_parts(RunRolesEnum.reset)
        else:
            log.info('NOT running Reset parts')

    @internal(SimStateRunning)
    def _init_pulse_events(self):
        """
        Refreshes pulse part events that may have been toggled between 'active' and 'inactive' state.
        """
        log.info('Initializing sim events queue with Pulse parts: {} found', len(self.__pulse_parts))
        for pulse in self.__pulse_parts:
            pulse.init_pulse_event()

    @internal(SimStateRunning)
    def _run_finish_parts(self):
        finish_parts = self._get_parts(RunRolesEnum.finish)
        self.run_parts(RunRolesEnum.finish)

    @internal(BaseFsmState)
    def _get_percent_complete(self, none_allowed: bool = True) -> Either[None, int]:
        """
        Update the percentage complete (which uses the max times), and emit sig_completion_percentage.
        If no max times, then percentage emitted is < 0.
        """
        max_sim_time_days = self._settings.sim_steps.end.max_sim_time_days
        sim_perc = round(self.sim_time_days / max_sim_time_days * 100) if max_sim_time_days else None

        max_wall_clock_time_sec = self._settings.sim_steps.end.max_wall_clock_sec
        wall_clock_now_sec = self._run_timer_wall_clock.total_time_sec
        wall_perc = (round(wall_clock_now_sec / max_wall_clock_time_sec * 100) if max_wall_clock_time_sec
                     else None)

        if sim_perc is None and wall_perc is None:
            return None if none_allowed else self.PERCENT_COMPLETE_UNDEFINED
        else:
            return max(sim_perc or 0, wall_perc or 0)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_ori_def_local(self) -> Dict[str, Any]:
        return {
            ScKeys.SIM_TIME_DAYS: self.__master_clock.time_days,
            ScKeys.WALL_CLOCK_SEC: self._run_timer_wall_clock.total_time_sec,
        }

    def __change_settings(self, obj: SimSettings, _save: bool, **settings):
        """
        Change some settings on the given object. 
        :param obj: one of the sim settings objects
        :param _save: set to False if saving to filesystem should not be attempted
        :param settings: dictionary of attribute name -> value to set
        :raise: ValueError if some settings don't exist on obj
        """
        unknowns = []
        for name, value in settings.items():
            if hasattr(obj, name):
                setattr(obj, name, value)
            else:
                unknowns.append(name)

        if unknowns:
            raise ValueError('Following settings are unknown: {}'.format(unknowns))

        if _save:
            self.save_settings(fail_ok=True)
