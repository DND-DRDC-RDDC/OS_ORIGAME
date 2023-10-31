# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Background Replication module

The bg_replication module provides classes that implement the functionality required to run one
scenario replication. This includes starting, monitoring pause & stop commands from parent
process (GUI or Console), logging configuration, creation of replication's folder, error handling,
etc. The module is used primarily by the BatchSimManager class, which uses multiprocessing.Pool to
start multiple replications in separate child background processes.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import traceback
import logging
from enum import IntEnum, unique
from pathlib import Path
import multiprocessing as mp
import sys

# [2. third-party]

# [3. local]
from ..core import LogManager, log_level_int, log_level_name
from ..core.utils import ori_profile, ClockTimer
from ..core.signaling import setup_bridge_for_console
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ..core.typing import AnnotationDeclarations

from ..scenario import SimController, SimStatesEnum, SimSteps, SimControllerSettings, RunRolePartsError
from ..scenario import proto_compat_warn, DataPathTypesEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'run_bg_replic',
    'get_replic_path',

    'ReplicationError',
    'ReplicStatusEnum',
    'ReplicSimState',
    'ReplicSimConfig',
    'Replication',
    'BatchSetup',
]

log = logging.getLogger('system')

# set this to True if profile data should be generated for each replication (each one gets its own .pstats file)
PROFILE_BATCH_REPLICATIONS = False


class Decl(AnnotationDeclarations):
    BatchSetup = 'BatchSetup'
    ReplicSimConfig = 'ReplicSimConfig'
    ReplicSimState = 'ReplicSimState'
    ReplicStatusEnum = 'ReplicStatusEnum'


# -- Function definitions -----------------------------------------------------------------------

def setup_variant(bridged_ui: bool):
    """
    When run from the GUI, the multiprocessing module will load the same modules, same configuration, so the
    replication ends up with Qt QObject as BridgeEmitter base class to the Scenario signals. Here, we check if
    this is the case and if so, reload the scenario modules. WARNING: this can cause unexpected behavior because
    for example enum classes get reloaded; so the same enum member before and after this function is called
    will have different id() and hence they will not compare equal!
    """
    if bridged_ui:
        log.info('Running batch replication from GUI, patching the signaling module')

        for mod in list(sys.modules.keys()):
            if mod.startswith('origame.scenario'):
                del sys.modules[mod]

        setup_bridge_for_console()

    else:
        # save some time: for console run, no need to re-configure
        log.info('Running batch replication from Console')


def run_bg_replic(batch_setup: Decl.BatchSetup,
                  sim_config: Decl.ReplicSimConfig,
                  shared_sim_state: Decl.ReplicSimState) -> Tuple[int, int, Decl.ReplicStatusEnum]:
    """
    Start a replication. This is called by multiprocessing.Pool *in separate process* to start a replication.

    First checks if have an EXIT signal already; only if NOT will a Replication be created and evolved until
    either STOPPED, no more events, or max sim time reached.

    :param batch_setup: setup parameters common to all replications of a batch
    :param sim_config: ReplicSimConfig instance containing run parameters specific to sim (random seed etc)
    :param shared_sim_state: the shared sim state, instance of ReplicSimState

    :returns: (variant_id, replic_id, status), where status is one of ReplicStatusEnum constants
    :raises ReplicationError: when something went wrong in replication process; this exception got
        pickled in process and carried over to parent process.
    """

    # if there has been a batch stop then we want to know before we even create the Replication
    variant_id, replic_id = sim_config.variant_id, sim_config.replic_id

    log_mgr = LogManager()

    try:
        shared_sim_state.start(variant_id, replic_id)
        shared_sim_state.update_exit()
        if shared_sim_state.need_exit():
            log.warning("Replication ({},{}) will NOT be created", variant_id, replic_id)
            return variant_id, replic_id, ReplicExitReasonEnum.stopped

        # ok, replication needed, create its folder; user-facing IDs start at 1 instead of 0
        replic_path = get_replic_path(batch_setup.batch_folder, variant_id, replic_id)
        replic_path.mkdir(parents=True)
        sim_config.replic_path = str(replic_path)
        if batch_setup.save_log:
            # and log to log.csv in that folder
            log_mgr.log_to_file(path=replic_path)

        # start and run it:
        replication = Replication(batch_setup, sim_config)
        if PROFILE_BATCH_REPLICATIONS:
            replication.run = ori_profile(replication.run, batch_setup.scen_path, v=variant_id, r=replic_id)
        result = replication.run(shared_sim_state)

        return result

    except Exception as exc:
        log.error('Exception in Replication ({},{}):', variant_id, replic_id)
        log.exception('Traceback:')
        # This is tricky because this function gets called in a separate process, so the exception actually
        # gets pickled by multiprocessing and copied to the host process. It seems that this puts some limitations
        # on what can be done because after many tries the following was the only reliable way of passing variant
        # and replication id and relevant info about trackeback
        exc_tb = traceback.format_exc()
        raise ReplicationError(variant_id, replic_id, str(exc), exc_tb)

    finally:
        log_mgr.close()


def get_replic_path(batch_folder: str, variant_id: int, replic_id: int) -> Path:
    """Get the path name to a replication in batch folder with given id's"""
    return Path(batch_folder) / 'v_{}_r_{}'.format(variant_id, replic_id)


# -- Class Definitions --------------------------------------------------------------------------

class ReplicationError(Exception):
    """
    Raised when a replication cannot continue. This may happen during initialization of the replication,
    during the simulation loop, or (unlikely but possible) during shutdown (when the final scenario state
    gets saved).
    """

    def __init__(self, variant_id: int, replic_id: int, message: str, traceback: str):
        """
        :param variant_id: id of variant for this replication
        :param replic_id: id of this replication
        :param traceback: stack traceback
        """
        Exception.__init__(self, variant_id, replic_id, message, traceback)


class SimEventExecError(Exception):
    """
    Raised when sim controller of a replication has failed processing an event (ie executing the
    associated IExecutablePart)
    """
    pass


class ReplicStatusEnum(IntEnum):
    """
    Enumeration of the possible status of a scenario replication simulation. Before a Replication instance is
    created, the replication status is NOT_STARTED. Once it is created, it becomes CREATED, and one the
    replication starts simulating the scenario, it becomes NOT_DONE. The status will transition to either
    STOPPED if sim stopped externally, ELAPSED if sim time reached set limit, or NO_MORE_EVENTS if ran out of events.
    """
    not_started, initialized, processing_events, exited = range(4)


@unique
class ReplicExitReasonEnum(IntEnum):
    # normal exits:
    max_sim_time_elapsed, max_wall_clock_elapsed, no_more_events, paused_by_script = range(4)
    # abnormal exits (did not end properly):
    stopped, event_failed, startup_failure, finish_failure = range(20, 24)
    # general failure:
    failure = 100

    def set_exc_traceback(self, exc_traceback: str):
        self.__exc_traceback = exc_traceback

    def get_exc_traceback(self) -> str:
        return self.__exc_traceback


class ReplicSimState:
    """
    Represent the simulation state that is shared between background replications and the master process
    (Origame GUI or Console variant). The master process instantiates only one instance for a batch run,
    and gives this one instance to each replication. The master does not call any of the methods, but the
    master writes to self.exit and self.paused when replications should exit or un/pause.

    Each replication runs in a separate process via multiprocessing.Pool and gets its own process-local
    instance of the ReplicSimState, with initialization state copied across processes by the
    multiprocessing.Manager, except for self.exit and self.pause which actually reflect the state set
    by the master process (they are not copies, they dynamically update when master changes).

    Hence each replication calls start() when it starts, and then calls other methods until the replication
    is eventually done, but it does not change self.exit or self.paused. The
    multiprocessing module (specifically, its Manager and Pool classes) take care of all the behind-the-scenes
    communication necessary to transfer self.exit and self.pause across all processes.
    """

    # calls to update_*() methods are expensive as they communicate with master process; only update every so often:
    UPDATE_INTERVAL_SEC = 0.1

    def __init__(self, mp_manager: mp.Manager):
        """
        :param mp_manager: The multiprocess.Manager instance to use to share exit and pause states between
            master and replication processes
        """
        # shared by all children and parent
        self.exit = mp_manager.Value('b', False)
        self.paused = mp_manager.Value('b', False)

        # local to the child receiving self: the instance in master will never see those change; each replication
        # has its own copy of those data members, but init can only be called in master so can't set here. Use
        # reasonable defaults:
        self._need_exit = False
        self._current_paused = None
        self._variant_id = None
        self._replic_id = None
        self._update_pause_timer = None
        self._update_exit_timer = None

    def start(self, variant_id: int, replic_id: int):
        """
        Signify the start of a replication for the given ID. This is called by the Replication itself,
        when it starts doing its work, so it is in a separate process!
        :param variant_id: ID of scenario variant, starts at 0
        :param replic_id: ID of scenario variant replication, starts at 1
        """
        assert variant_id >= 1
        assert replic_id >= 1
        self._need_exit = self.exit.value
        self._current_paused = self.paused.value
        self._variant_id = variant_id
        self._replic_id = replic_id
        self._update_pause_timer = ClockTimer()
        self._update_exit_timer = ClockTimer()

    def update_paused(self) -> bool:
        """
        Update the pause flag based on master setting. This flag state is copied locally (to replication)
        to ensure it does not change when queried multiple times in one replication step.
        :return: True if transitioned (previous state different from new), False otherwise
        """
        if self._update_pause_timer.total_time_sec < self.UPDATE_INTERVAL_SEC:
            return False

        self._update_pause_timer.reset()
        new_paused = self.paused.value
        if self._current_paused != new_paused:
            if new_paused:
                log.info('Replication ({},{}) entering PAUSED state', self._variant_id, self._replic_id)
            else:
                log.info('Replication ({},{}) entering RUN state', self._variant_id, self._replic_id)
            self._current_paused = new_paused
            return True

        return False

    def need_pause(self) -> bool:
        """Return True if the Replication should pause. Only call this after update_paused()."""
        return self._current_paused

    def update_exit(self):
        """
        Update the exit flag based on master setting. This flag state is copied locally (to replication)
        to ensure it does not change when queried multiple times in one replication step.
        """
        if self._update_exit_timer.total_time_sec >= self.UPDATE_INTERVAL_SEC:
            self._update_exit_timer.reset()
            new_exit = self.exit.value
            self._need_exit = new_exit

    def need_exit(self) -> bool:
        """Return True if replication should exit ASAP. Only call this after update_exit()."""
        return self._need_exit


class ReplicSimConfig:
    """
    POD structure that aggregates configuration parameters specific to each individual replication
    of a batch (each replication will have a different instance of this class):
    its variant and replication ID, its seed, etc.
    """

    def __init__(self, variant_id: int, replic_id: int, reset_seed: int, replic_path: PathType = None):
        """
        :param variant_id: variant id of this replication, starts at 1
        :param replic_id: replication id of this variant replication, starts at 1
        :param reset_seed: the seed for the random number generator
        :param replic_path: path to the replication's folder where log etc stored; if not set now, must be set
            before the Replication is instantiated
        """
        self.variant_id = variant_id
        self.replic_id = replic_id
        self.reset_seed = reset_seed
        self.replic_path = str(replic_path)


class BatchSetup:
    """
    POD structure that aggregates configuration parameters that are GLOBAL TO THE BATCH, i.e. pertain
    identically to ALL REPLICATIONS: batch folder, scenario path, whether to log, whether to save on exit,
    etc.
    """

    def __init__(self,
                 scen_path: str,
                 batch_folder: str,
                 sim_steps: SimSteps,
                 save_scen_on_exit: bool = True,

                 save_log: bool = True,
                 loop_log_level: Either[int, str] = logging.WARNING,
                 log_deprecated: bool = False,
                 log_raw_events: bool = False,
                 fix_linking_on_load: bool = True,

                 bridged_ui: bool = False):
        """
        :param scen_path: path to scenario file for scenario to run
        :param batch_folder: the folder in which to save replication folders

        :param save_log: if False, replications will not save their log to a file
        :param loop_log_level: log level (int or str) for each replication's sim loop
        :param log_deprecated: if True, use of deprecated functions will be logged
        :param log_raw_events: if True, simulation events will be logged to a separate file; WARNING:
            each replication uses the same file, so this option really only makes sense for 1x1 batch!
        :param fix_linking_on_load: if True, linking will be verified on load and fixed (should only be
            required for prototype scenarios)

        :param max_sim_time_days: sim time (days) at which replication should exit
        :param max_wall_clock_sec: real-time (seconds) at which replication should exit
        :param realtime_scale: scale factor for real-time; if as-fast-as-possible, then None, else must be > 0

        :param save_scen_on_exit: If False, the replication final state (scenario) will not be saved on exit
        :param bridged_ui: if True, indicates this batch is being run from an application that uses UI bridging; in
            such case, the replication will re-configure itself without bridging
        """

        self.scen_path = scen_path
        self.batch_folder = batch_folder
        self.sim_steps = sim_steps

        self.save_log = save_log
        self.loop_log_level = log_level_int(loop_log_level)  # always a number
        self.log_deprecated = log_deprecated
        self.log_raw_events = log_raw_events
        self.fix_linking_on_load = fix_linking_on_load

        self.save_scen_on_exit = save_scen_on_exit
        self.bridged_ui = bridged_ui


class SimStartupError(Exception):
    pass


class Replication:
    """
    Represent an Origame scenario replication executing the scenario logic. Each replication has its
    own folder and log file.
    """

    def __init__(self, batch_config: BatchSetup, sim_config: ReplicSimConfig):
        """
        :param batch_config: batch-level configuration parameters (scenario path, batch folder, etc)
        :param sim_config: replication-specific settings (variant and replication ID, replication folder etc)
        """

        variant_id = sim_config.variant_id
        replic_id = sim_config.replic_id

        setup_variant(batch_config.bridged_ui)

        # Signaling-related functionality must be imported here due to how multiprocessing imports modules in processes;
        # for example, if the batch is started from GUI, we still want Replication's ScenarioManager to use
        # BackendEmitter not BridgeEmitter
        from ..core.signaling import BackendEmitter
        from ..scenario import ScenarioManager, MIN_REPLIC_ID, MIN_VARIANT_ID
        assert issubclass(ScenarioManager.Signals, BackendEmitter)

        # Each replication has its own folder
        # create folder for this replication, inside batch folder:
        log.info('Creating Replication ({},{})', variant_id, replic_id)

        if variant_id < MIN_VARIANT_ID:
            raise ValueError("invalid variant id", variant_id)
        if replic_id < MIN_REPLIC_ID:
            raise ValueError("invalid replication id", replic_id)

        self.__v_id = variant_id
        self.__r_id = replic_id
        self.__replic_folder = sim_config.replic_path
        self.__save_scen_on_exit = batch_config.save_scen_on_exit
        self.__sim_loop_log_level = batch_config.loop_log_level

        self.__replic_status = ReplicStatusEnum.initialized

        # load scenario
        self.__scenario_mgr = ScenarioManager()
        # assert Path(replic_folder).parent.parent == Path(scen_path).parent
        self.__scenario_mgr.config_logging(batch_config)
        self.__scenario_mgr.set_future_anim_mode_constness(False)
        scen, _ = self.__scenario_mgr.load(batch_config.scen_path)
        assert scen.scenario_def.root_actor.anim_mode is False
        # WARNING: due to setup_variant() re-importing modules, we cannot provide the file_type here, it will not
        # compare equal. Instead we let batch_data module infer it.
        scen.shared_state.batch_data_mgr.set_data_path(batch_config.batch_folder)
        # scen.shared_state.batch_data_mgr.set_data_path(batch_config.batch_folder,
        #                                                file_type=DataPathTypesEnum.batch_folder)  # FAILS, see above

        # config sim controller of that scenario
        sim_settings = SimControllerSettings(variant_id=variant_id,
                                             replic_id=replic_id,
                                             auto_seed=False,  # batch manager always picks seed for replication
                                             reset_seed=sim_config.reset_seed,
                                             sim_steps=batch_config.sim_steps)
        self.__sim_controller = self.__scenario_mgr.scenario.sim_controller
        self.__sim_controller.replic_folder = sim_config.replic_path
        self.__sim_controller.set_settings(sim_settings)
        assert self.__sim_controller.get_anim_while_run_dyn_setting() is True
        assert self.__sim_controller.is_animated is False

    @property
    def status(self) -> ReplicStatusEnum:
        """Obtain run status of the replication."""
        return self.__replic_status

    @property
    def replic_folder(self):
        """Get the folder for this replication"""
        return self.__replic_folder

    @property
    def sim_controller(self) -> SimController:
        """Get the sim controller for this replication"""
        return self.__sim_controller

    @property
    def variant_id(self) -> int:
        """Get the sim controller for this replication"""
        return self.__v_id

    @property
    def replic_id(self) -> int:
        """Get the sim controller for this replication"""
        return self.__r_id

    def run(self, shared_sim_state: ReplicSimState) -> Tuple[int, int, ReplicStatusEnum]:
        """
        Start a replication, with given shared sim state. Will be evolved in a loop until either STOPPED
        (via shared sim state), no more events, or max sim time reached.

        :param shared_sim_state: the shared sim state, instance of ReplicSimState
        :returns: (variant_id, replic_id, status), where status is one of ReplicStatusEnum constants
        :raises ReplicationError: when something went wrong in replication process; this exception got
        pickled in process and carried over to parent process.
        """
        shared_sim_state.update_exit()
        if shared_sim_state.need_exit():
            replic_exit_reason = ReplicExitReasonEnum.stopped
            self.__replic_status = ReplicStatusEnum.exited
            log.warning('Replication ({},{}) run stopped before start (STOPPED)', self.__v_id, self.__r_id)
            return self.__v_id, self.__r_id, replic_exit_reason

        try:
            self.__startup(shared_sim_state)
            replic_exit_reason = self.__loop_till_stopped(shared_sim_state)

            # process exit condition:
            if replic_exit_reason == ReplicExitReasonEnum.stopped:
                assert shared_sim_state.need_exit()
                log.warning('Unsuccessful completion for Replication ({},{}) (STOPPED)', self.__v_id, self.__r_id)

            elif replic_exit_reason == ReplicExitReasonEnum.event_failed:
                last_step_error_info = self.__sim_controller.last_step_error_info
                assert self.__sim_controller.last_step_was_error
                error_msg = last_step_error_info.msg
                log.error(error_msg)
                log.error('Unsuccessful completion for Replication ({},{}) (FAILED event)', self.__v_id, self.__r_id)
                raise SimEventExecError(error_msg)

            else:
                assert not self.__sim_controller.last_step_was_error
                log.info('Successful completion for Replication ({},{})', self.__v_id, self.__r_id)

            # done:
            return self.__v_id, self.__r_id, replic_exit_reason

        finally:
            self.__replic_status = ReplicStatusEnum.exited
            # After scenario saved-as, scenario path will be in the replication folder, and on scenario shutdown,
            # batch replication data automatically gets saved if there is any. *So* we have to save the batch
            # replication data *first* AND clear it, so it doesn't get saved in the wrong place on scenario shutdown.
            self.__scenario_mgr.scenario.save_batch_replic_data(clear_after=True)
            # regardless of success, attempt to save scenario in case final state useful for debugging
            if self.__save_scen_on_exit:
                self.__scenario_mgr.save(Path(self.__replic_folder, 'final_scenario.ori'))

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __startup(self, shared_sim_state: ReplicSimState):
        try:
            log.info('Starting Replication ({},{})', self.__v_id, self.__r_id)
            self.__replic_status = ReplicStatusEnum.processing_events
            # even if this replic has been paused already, we need to start the sim then check for pause, else too
            # much logic repeated:
            self.__sim_controller.sim_run()
            # now check if should be in pause state before entering the loop :
            shared_sim_state.update_paused()
            if shared_sim_state.need_pause():
                self.__sim_controller.sim_pause()

        except Exception as exc:
            # log.error('Failed startup: {}', exc)
            raise SimStartupError('Failed startup: {}'.format(exc))

    def __loop_till_stopped(self, shared_sim_state: ReplicSimState) -> ReplicExitReasonEnum:
        prev_level = log.getEffectiveLevel()
        if prev_level != self.__sim_loop_log_level:
            log.warning("Changing log level to {} for sim loop", log_level_name(self.__sim_loop_log_level))
            log.setLevel(self.__sim_loop_log_level)

        try:
            shared_sim_state.update_exit()
            replic_exit_reason = None
            while replic_exit_reason is None:
                if shared_sim_state.update_paused():
                    if shared_sim_state.need_pause():
                        self.__sim_controller.sim_pause()
                    else:
                        self.__sim_controller.sim_resume()

                replic_exit_reason = self.__step(shared_sim_state)

            return replic_exit_reason

        except RunRolePartsError as exc:
            log.error(str(exc))
            raise

        finally:
            if prev_level != self.__sim_loop_log_level:
                log.warning("Sim loop done, restoring log level to {}", logging.getLevelName(prev_level))
                log.setLevel(prev_level)

    def __scen_transitioned_to_paused(self, before_state: SimStatesEnum):
        return before_state != SimStatesEnum.paused and self.__sim_controller.state_id == SimStatesEnum.paused

    def __step(self, shared_sim_state: ReplicSimState) -> ReplicExitReasonEnum:
        """
        Execute one step of evolution of the scenario replication. This steps the simulation engine.
        """
        assert self.__replic_status == ReplicStatusEnum.processing_events
        replic_exit_reason = None

        sim_con_state_before = self.__sim_controller.state_id
        self.__sim_controller.sim_update()

        if self.__sim_controller.last_step_was_error:
            log.error('Replication {},{} failed to process an event', self.__v_id, self.__r_id)
            replic_exit_reason = ReplicExitReasonEnum.event_failed

        elif self.__sim_controller.max_sim_time_elapsed:
            # assert self.__sim_controller.is_state(SimStatesEnum.paused)
            log.warning('Replication {},{} reached max sim date-time {}',
                        self.__v_id, self.__r_id, self.__sim_controller.sim_time_days)
            replic_exit_reason = ReplicExitReasonEnum.max_sim_time_elapsed

        elif self.__sim_controller.max_wall_clock_elapsed:
            log.warning('Replication {},{} reached max real time {} (excluding pause times)',
                        self.__v_id, self.__r_id, self.__sim_controller.realtime_sec)
            replic_exit_reason = ReplicExitReasonEnum.max_wall_clock_elapsed

        elif self.__sim_controller.num_events == 0:
            # WARN level otherwise risk not seeing since part of event loop
            log.warning('Replication {},{} consumed all events', self.__v_id, self.__r_id)
            replic_exit_reason = ReplicExitReasonEnum.no_more_events

        elif self.__scen_transitioned_to_paused(sim_con_state_before):
            log.warning('Replication {},{} paused by scenario, cannot continue', self.__v_id, self.__r_id)
            replic_exit_reason = ReplicExitReasonEnum.paused_by_script

        else:
            # might have been stopped externally:
            shared_sim_state.update_exit()
            if shared_sim_state.need_exit():
                self.__sim_controller.sim_pause()
                replic_exit_reason = ReplicExitReasonEnum.stopped

        return replic_exit_reason
