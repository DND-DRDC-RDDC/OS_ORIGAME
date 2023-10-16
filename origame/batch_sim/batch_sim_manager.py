# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Batch simulation management

The BatchSimManager has a state machine which uses a simple pattern: the BSM has a *state* data member which
gets initialized to a new instance of one of the state classes every time there is a state transition.
Each state class knows when to transition out, and what state to transition to, but does not know if the
target state is allowed. So the target state is first created, and if succesful, the "from" state
sets the BSM to point to the new state, and gets discarded. Otherwise, the from state remains the current
state. The state classes only implement the behavior that is supported in the given state; since the BSM
simply forwards state-dependent calls to the current state object, an exception will get raised if the
current state does not support the required operation.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import functools
import logging
import multiprocessing as mp
import shutil
import time
import json
from datetime import datetime, timedelta
from enum import IntEnum
from pathlib import Path
from copy import deepcopy
from textwrap import dedent
from threading import current_thread

# [2. third-party]

# [3. local]
from ..core import BridgeEmitter, BridgeSignal, safe_slot, BaseFsmState, IFsmOwner, LogCsvFormatter
from ..core import internal, override, get_enum_val_name, AppSettings
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ..core.typing import AnnotationDeclarations
from ..scenario import ScenarioManager, Scenario, SimSteps
from ..scenario import create_batch_data_file, get_db_path, BatchDataMgr, DataPathTypesEnum, BATCH_TIMESTAMP_FMT
from ..scenario.defn_parts import RunRolesEnum

from .bg_replication import ReplicSimState, BatchSetup, ReplicSimConfig, ReplicStatusEnum, ReplicationError
from .bg_replication import run_bg_replic, get_replic_path, ReplicExitReasonEnum
from .seed_table import SeedTable, MIN_VARIANT_ID, MIN_REPLIC_ID

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'BatchSimManager',
    'BatchSimSettings',
    'BsmStatesEnum'
    'BatchDoneStatusEnum',
    'get_num_cores_actual',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    BatchSimSettings = 'BatchSimSettings'


# -- Function definitions -----------------------------------------------------------------------

def get_num_cores_actual(cores_wanted: int, total_num_replics: int) -> int:
    """
    Get the actual number of cores that will be used at the beginning of the batch sim run.
    :param cores_wanted: number of cores the user wants
    :param total_num_replics: total number of replications that will be run
    """
    num_cores_avail = mp.cpu_count()
    if cores_wanted == 0:
        # if cores=0, will use all available:
        return min(num_cores_avail, total_num_replics)
    else:
        # if specified, can only use as many as are available, or the total replications, whichever is smaller:
        return min(num_cores_avail, total_num_replics, cores_wanted)


# -- Class Definitions --------------------------------------------------------------------------

class BatchDoneStatusEnum(IntEnum):
    not_started, in_progress, paused, aborted, completed = range(5)


class BsmStatesEnum(IntEnum):
    """
    Enumerate the various states available to the Batch Sim Manager
    """
    ready, running, paused, done = range(4)


# noinspection PyProtectedMember
class _BsmStateReady(BaseFsmState):
    """
    The only thing that can be done while in READY state is to set the scenario path, load seeds from another
    file, and start the batch sim.

    plantuml
    """

    state_id = BsmStatesEnum.ready

    def __init__(self, prev_state: BaseFsmState = None, fsm_owner: IFsmOwner = None):
        super().__init__(prev_state, fsm_owner=fsm_owner)

        bsm = self._fsm_owner
        bsm._reset_run_time()

        if prev_state is not None:
            new_path = prev_state.scen_path_when_ready
            if new_path is not None:
                self.set_scen_path(new_path)
            bsm.signals.sig_replication_done.emit(0, 0)

    def get_completion_status(self) -> BatchDoneStatusEnum:
        return BatchDoneStatusEnum.not_started

    def start(self):
        """Start the sim: transitions to RUNNING"""
        self._set_state(BsmStateClasses.RUNNING)

    def set_scen_path(self, new_path: str):
        """
        Set the scenario file path that will be used by each replication of a batch.
        :param value: scenario file path
        """
        log.info("BSM (ready) switching to scenario path '{}'", new_path)
        self._fsm_owner._scen_path = None if new_path is None else Path(new_path)

    def set_cores_wanted(self, num_cores: int):
        """
        It only makes sense to change the cores wanted in READY state. The actual number of cores that will be used
        depends on how many available, and whether the user wants "all" or a specific #.
        """
        # Oliver TODO build 3: add test for this
        self._fsm_owner._settings.num_cores_wanted = num_cores


class CapturesNextReadyScenPath:
    """
    The path of a loaded scenario can change at any time, but the path used by a running batch sim cannot
    change. I.e., the scenario path as seen by the batch sim manager can only change while in the Ready state.
    So all non-ready BSM states derive from this class to capture any scenario path change, so that it can be
    "applied" later when BSM returns to its Ready state.
    """

    def __init__(self):
        self.__scen_path_when_ready = None

    def set_scen_path(self, new_path: str):
        """Scenario Path cannot change outside of ready state, but capture so next ready state can use it."""
        log.info("BSM ({}) save new scenario path '{}' for next Ready state", self._fsm_owner.state_name, new_path)
        self.__scen_path_when_ready = new_path

    @property
    def scen_path_when_ready(self) -> Either[str, None]:
        """If the scenario path changed outside of the READY state, this will contain its value"""
        return self.__scen_path_when_ready


# noinspection PyProtectedMember
class _BsmStateRunning(BaseFsmState, CapturesNextReadyScenPath):
    """
    When entering the RUNNING state from READY, the batch folder is created, and
    replications are queued and executed in parallel on a specified number of cores.
    The final exit condition of each replicatoin is recorded by the BatchMonitor. Once
    all replications have ended, the BSM automatically transitions to DONE.

    NOTE: the init will raise an exception if some preconditions for entering the state
    are not satisfied, such as the scenario never having been saved (where would the batch sim
    results go?).

    When entering the RUNNING state from PAUSED, there is no much to do except get a reference
    to BatchMonitor from the previous state.
    """

    state_id = BsmStatesEnum.running

    def __init__(self, prev_state: BaseFsmState,
                 fsm_owner: IFsmOwner = None,
                 batch_log_file_handler: logging.Handler = None):
        """Creates the shared memory manager and pool and initializes replications array and results.
        :param fsm_owner: owning object of this state machine state
        :param prev_state: the state object from which BSM transitioning"""
        BaseFsmState.__init__(self, prev_state, fsm_owner=fsm_owner)
        CapturesNextReadyScenPath.__init__(self)
        self.__log_file_handler = batch_log_file_handler
        self._results_scen_path = None

        # check any pre-conditions else
        if self._fsm_owner.scen_path is None:
            raise RuntimeError('Must save scenario before RUNNING')

        settings = self._fsm_owner._settings
        if settings.auto_seed:
            assert settings.seed_table is None
            self.__seed_table = SeedTable(settings.num_variants, settings.num_replics_per_variant)
        else:
            self.__seed_table = settings.seed_table

        # ok, init:
        if prev_state.state_id == BsmStatesEnum.ready:
            # if previously ready, setup for running
            self._batch_mon = None

            self._mp_manager = mp.Manager()
            self._sim_state = ReplicSimState(self._mp_manager)
            self._worker_pool = None

            self._batch_scen_path = None
            self._batch_data = None

        elif prev_state.state_id == BsmStatesEnum.paused:
            # if previously paused, copy state's data
            self._batch_mon = prev_state._batch_mon

            self._mp_manager = prev_state._mp_manager
            self._sim_state = prev_state._sim_state
            self._worker_pool = prev_state._worker_pool

            self._batch_scen_path = prev_state._batch_scen_path
            self._batch_data = prev_state._batch_data

        else:
            raise NotImplementedError('Invalid previous state specified for _BsmStateRunning initialization.')

        self._sim_state.paused.value = False

    @override(BaseFsmState)
    def enter_state(self, prev_state: BaseFsmState):
        """
        Entering the RUNNING state must be done separately from object init, because when the state is entered,
        it queues (if entered from READY) concurrent processes to be run for this batch.
        Without this separation, replications could complete before the BSM has the new state object as state.
        """
        if prev_state.state_id != BsmStatesEnum.ready:
            # nothing else to do:
            return

        # so the previous state was ready, setup the batch environment
        assert self._sim_state.paused.value is False

        bsm = self._fsm_owner
        settings = bsm._settings
        total_num_replics = settings.num_variants * settings.num_replics_per_variant
        num_cores_actual = get_num_cores_actual(settings.num_cores_wanted, total_num_replics)

        assert self.__log_file_handler is None
        batch_folder = self.__create_batch_folder(settings.num_variants, settings.num_replics_per_variant)
        self.__save_seed_file(batch_folder)
        self.__copy_scenario_snapshot(batch_folder)

        # create the monitor of replication processes
        self._batch_mon = BatchMonitor(bsm, batch_folder, num_cores_actual)
        create_batch_data_file(batch_folder)

        # create the settings dict that is common to all replications:
        sim_steps = settings.replic_steps
        if sim_steps is None:
            sim_steps = bsm.get_scen_sim_steps()
        batch_setup = BatchSetup(bsm.scen_path, batch_folder, sim_steps, settings.save_scen_on_exit,
                                 **bsm._app_settings)

        # queue a work item for each replication (NxM replications)
        self._worker_pool = mp.Pool(num_cores_actual, maxtasksperchild=1)
        for variant_id in range(settings.num_variants):
            variant_id += MIN_VARIANT_ID
            for replic_id in range(settings.num_replics_per_variant):
                replic_id += MIN_REPLIC_ID
                self._batch_mon.on_replic_queued(variant_id, replic_id)
                seed = self.__seed_table.get_seed(variant_id, replic_id)
                replic_sim_config = ReplicSimConfig(variant_id, replic_id, seed)
                args = (batch_setup, replic_sim_config, self._sim_state,)

                self._worker_pool.apply_async(run_bg_replic, args,
                                              callback=self._batch_mon._on_background_replic_done,
                                              error_callback=self._batch_mon._on_background_replic_error)

        assert self._batch_mon.get_num_replics_pending() != 0  # no way should get this far with no replics queued!
        self._worker_pool.close()

        log.info('Queued {} variants, {} replications/variant, to be run among {} cores',
                 settings.num_variants, settings.num_replics_per_variant, num_cores_actual)
        sim_config = ['{}: {}'.format(key, val) for key, val in bsm._app_settings.items()]
        log.info('Application config (None value implies default/not-applicable):')
        for line in sorted(sim_config):
            log.info('    {}', line)

    @override(BaseFsmState)
    def exit_state(self, new_state: BaseFsmState):
        if new_state.state_id == BsmStatesEnum.done:
            self.__gen_and_save_batch_data()

    def get_completion_status(self) -> BatchDoneStatusEnum:
        return BatchDoneStatusEnum.in_progress

    def pause(self):
        """
        Pause the batch. This affects running replications only: they will each pause. The BSM
        transitions to PAUSED.
        """
        self._set_state(BsmStateClasses.PAUSED, batch_log_file_handler=self.__log_file_handler)

    def stop(self):
        """Stop the batch. This just sets a flag that each replication not yet run reads. """
        log.warning('Aborting the batch')
        self._sim_state.exit.value = True
        self._worker_pool.terminate()
        self._set_state(BsmStateClasses.DONE,
                        completion_status=BatchDoneStatusEnum.aborted,
                        batch_log_file_handler=self.__log_file_handler)

    def on_background_replic_done(self):
        """When a replication is done, check if there are more; if not, transition to DONE state."""
        if self._batch_mon.get_num_replics_pending() == 0:
            log.info("Batch sim completed, no more replications left to run")
            self._set_state(BsmStateClasses.DONE, batch_log_file_handler=self.__log_file_handler)

    def __create_batch_folder(self, num_variants: int, num_replics_per_variant: int) -> Path:
        """Create a folder to hold all the replication folders, batch log, etc."""
        fsm_owner = self._fsm_owner
        assert fsm_owner.scen_path is not None  # if None, should have trapped this earlier

        datetime_now = datetime.today().strftime(BATCH_TIMESTAMP_FMT)
        batch_name = "batch_{}_{}x{}".format(datetime_now, num_variants, num_replics_per_variant)
        batch_folder = fsm_owner.batch_runs_path / batch_name

        batch_folder.mkdir(parents=True)
        self.__create_batch_log(batch_folder)

        fsm_owner.signals.sig_batch_folder_changed.emit(str(batch_folder))
        log.info("Batch sim folder is {}", batch_folder)

        return batch_folder

    def __create_batch_log(self, batch_folder: Path):
        batch_log = (batch_folder / 'log.csv').absolute()
        self.__log_file_handler = logging.FileHandler(str(batch_log))
        self.__log_file_handler.setFormatter(LogCsvFormatter('{asctime},{name},{levelname},"{message}"', style='{'))
        logging.getLogger('system').addHandler(self.__log_file_handler)

    def __save_seed_file(self, batch_folder: Path):
        """Save the random-seeds file to the batch folder"""
        save_path = batch_folder / 'seeds.csv'
        self.__seed_table.save_as(save_path)

    def __copy_scenario_snapshot(self, batch_folder: Path):
        """Copy the scenario (last saved version on filesystem) to batch folder"""
        save_path = batch_folder / Path(self._fsm_owner.scen_path).name
        log.info("Copying scenario (as last saved) to '{}'", save_path.parent, save_path.name)
        shutil.copy(str(self._fsm_owner.scen_path), str(save_path))
        self._batch_scen_path = save_path

    def __gen_and_save_batch_data(self):
        """Generate batch data per the original batch scenario and save it"""
        if not BatchDataMgr(self._batch_scen_path.parent).has_data():
            log.info("No batch data generated by this batch run")
            return

        scen_mgr = ScenarioManager()
        try:
            scen = scen_mgr.load(self._batch_scen_path)
        except Exception as exc:
            log.error("Could not load scenario to process batch data: {}", exc)
            return

        if not scen.sim_controller.has_role_parts(RunRolesEnum.batch):
            # nothing else to do
            return

        try:
            scen.sim_controller.run_parts(RunRolesEnum.batch)
        except Exception as exc:
            log.warning('One or more exceptions while trying to run batch-role function parts, see above for details')
            # TBD FIXME ASAP: remove the dead code below
            #     Reason: need to some time ensure it is not necessary (parts show their errors)
            # for failed_part, exc_msg in exc.map_part_to_exc_str.items():
            #     log.error('    - {}: {}', failed_part, exc_msg)

        # try to save final state, even if there was an error processing the batch parts:
        results_scen_path = Path(scen.filepath).with_name('batch_results.orib')
        try:
            log.info("Saving batch post-processed state of scenario to {}:", results_scen_path)
            scen_mgr.save(results_scen_path)
        except Exception:
            log.error('Batch post-processed version of scenario could not be saved')
        else:
            log.info('Batch post-processed version of scenario saved to {}:', results_scen_path)
            self._results_scen_path = results_scen_path


# noinspection PyProtectedMember
class _BsmStatePaused(BaseFsmState, CapturesNextReadyScenPath):
    """
    Implement the Paused state of the BSM. From this state, the BSM can stop or resume. In order to minimize
    duplication of behavior, a stop actually causes a transition to RUNNING rather than READY; the RUNNING state
    knows how to stop (it waits for all replications queued and in-progress to exit). Note that PAUSED must allow
    for some replications to notify completion since some might have completed their sim loop just before the
    transition to PAUSED occurred, but before they had completed (hence the on_background_replic_done() needed
    in PAUSED).
    """

    state_id = BsmStatesEnum.paused

    def __init__(self, prev_state: BaseFsmState, batch_log_file_handler: logging.Handler, fsm_owner: IFsmOwner = None):
        BaseFsmState.__init__(self, prev_state, fsm_owner=fsm_owner)
        CapturesNextReadyScenPath.__init__(self)
        assert (prev_state.state_id == BsmStatesEnum.running)

        self._batch_mon = prev_state._batch_mon

        self._mp_manager = prev_state._mp_manager
        self._sim_state = prev_state._sim_state
        self._worker_pool = prev_state._worker_pool

        self._batch_scen_path = prev_state._batch_scen_path
        self._batch_data = prev_state._batch_data

        log.info('Pausing running replications')
        self._sim_state.paused.value = True
        self.__batch_log_file_handler = batch_log_file_handler

    def get_completion_status(self) -> BatchDoneStatusEnum:
        return BatchDoneStatusEnum.paused

    def resume(self):
        """Resume the batch sim; transitions to RUNNING."""
        log.info('Resuming running replications')
        self._set_state(BsmStateClasses.RUNNING,
                        batch_log_file_handler=self.__batch_log_file_handler)

    def stop(self):
        """Flag the replications to exit ASAP, and transition to RUNNING (see class docs for details)."""
        log.info('Aborting batch sim')
        self._sim_state.exit.value = True
        self._worker_pool.terminate()
        self._set_state(BsmStateClasses.DONE,
                        completion_status=BatchDoneStatusEnum.aborted,
                        batch_log_file_handler=self.__batch_log_file_handler)

    def on_background_replic_done(self):
        """
        There is a small chance that a replication could complete after the batch has been paused, if it was
        already about to exit its sim loop. If there are no more replications left, transition to DONE state.
        """
        # Oliver TODO build 3: add test for this: directly call a few times and check via signals
        if self._batch_mon.get_num_replics_pending() == 0:
            log.info("Batch sim completed, no more replications left to run")
            self._set_state(BsmStateClasses.DONE,
                            batch_log_file_handler=self.__batch_log_file_handler)


# noinspection PyProtectedMember
class _BsmStateDone(BaseFsmState, CapturesNextReadyScenPath):
    """
    The batch simulation is done, there are no more replications to monitor.
    The results are kept available, until a transition to READY is requested.
    """

    state_id = BsmStatesEnum.done

    def __init__(self, prev_state: BaseFsmState,
                 batch_log_file_handler: logging.Handler,
                 completion_status: BatchDoneStatusEnum = BatchDoneStatusEnum.completed,
                 fsm_owner: IFsmOwner = None):
        BaseFsmState.__init__(self, prev_state, fsm_owner=fsm_owner)
        CapturesNextReadyScenPath.__init__(self)
        assert prev_state.state_id in (BsmStatesEnum.running, BsmStatesEnum.paused)

        self._batch_mon = prev_state._batch_mon
        self._completion_status = completion_status
        self.__results_scen_path = None

        log.info('Batch {}', completion_status.name)
        log.info('Summary:')
        for line in self._batch_mon.get_summary().splitlines():
            log.info('    {}', line)

        if batch_log_file_handler is not None:
            logging.getLogger('system').removeHandler(batch_log_file_handler)
            batch_log_file_handler.close()
            self.__batch_log_file_path = Path(batch_log_file_handler.baseFilename)

    def enter_state(self, prev_state: BaseFsmState):
        if prev_state.state_id == BsmStatesEnum.running:
            self.__results_scen_path = prev_state._results_scen_path

    def get_completion_status(self) -> BatchDoneStatusEnum:
        return self._completion_status

    def get_batch_log_file_path(self) -> Path:
        return self.__batch_log_file_path

    def get_batch_results_scen_path(self) -> Path:
        return self.__results_scen_path

    def new_batch(self):
        self._set_state(BsmStateClasses.READY)

    def on_background_replic_done(self):
        """
        If the batch was stopped before all in-progress replications could end, there is a small chance that
        multiprocessing could flag them as exited after the DONE state has been entered. However, there is
        nothing special to do, just need the method to be available.
        """
        pass


class BatchSimSettings:
    """
    Enables saving and loading the configured batch simulation settings with the scenario.
    """

    # --------------------------- class-wide methods --------------------------------------------

    @staticmethod
    def load(pathname: PathType) -> Decl.BatchSimSettings:
        """
        Load and set the batch simulation settings from the given file. Overrides previous settings if any.
        :param pathname: path to settings file
        :returns: The dictionary of batch simulation settings.
        :raises: ValueError. This error is raised by the JSON interpreter if a parsing error occurs while the file
            is being loaded.
        """

        with Path(pathname).open("r") as f:
            settings = json.load(f)

            # backwards compat:
            if 'results_root_path' in settings:
                settings['batch_runs_path'] = settings['results_root_path']
                del settings['results_root_path']

            seed_list = settings['seed_table']
            if seed_list is not None:
                settings['seed_table'] = SeedTable.from_list(seed_list)

            replic_step_settings = settings['replic_steps']
            if replic_step_settings is not None:
                settings['replic_steps'] = SimSteps(**replic_step_settings)

            return BatchSimSettings(**settings)

    # --------------------------- instance (self) PUBLIC methods ----------------

    def __init__(self,
                 batch_runs_path: str = None,
                 num_variants: int = 1,
                 num_replics_per_variant: int = 1,
                 num_cores_wanted: int = 0,
                 auto_seed: bool = True,
                 seed_table: SeedTable = None,
                 save_scen_on_exit: bool = True,
                 replic_steps: SimSteps = None,
                 ):
        """
        Initialize the batch simulation settings.
        :param batch_runs_path: The parent folder of all batch run folders.
        :param num_variants: The number of variants.
        :param num_replics_per_variant: The number of replications per variant.
        :param num_cores_wanted: Number of computer cores to use.
        :param auto_seed: Set True to use automatic seeding.
        :param seed_table: Instance of the seed table (None is used if auto_seed is True).
        :param save_scen_on_exit: Set True to save the scenarios.
        :param replic_steps: Instance of the sim step settings from the scenario's simulation controller.
        """

        self.batch_runs_path = batch_runs_path
        self.num_variants = num_variants
        self.num_replics_per_variant = num_replics_per_variant
        self.num_cores_wanted = num_cores_wanted
        self.auto_seed = auto_seed
        self.seed_table = seed_table
        self.__check_auto_seeding()

        self.save_scen_on_exit = save_scen_on_exit
        self.replic_steps = replic_steps

    def save(self, pathname: Path):
        """
        Save the batch settings to the given file.
        :param pathname: The save file path.
        """
        settings = self.get_settings_dict()
        with pathname.open("w") as f:
            json.dump(settings, f, indent=4, sort_keys=True)
            log.info('Batch settings saved to {}', pathname)

    def get_use_scen_sim_settings(self) -> bool:
        """Returns __use_scen_sim_settings boolean based on whether replic_steps is set to None"""
        return self.replic_steps is None

    def get_settings_dict(self) -> Dict[str, Any]:
        """Returns a dictionary containing the current batch sim settings"""
        settings = {
            'batch_runs_path': self.batch_runs_path,
            'num_variants': self.num_variants,
            'num_replics_per_variant': self.num_replics_per_variant,
            'num_cores_wanted': self.num_cores_wanted,
            'auto_seed': self.auto_seed,
            'seed_table': None if self.auto_seed else self.seed_table.get_seeds_list(),
            'save_scen_on_exit': self.save_scen_on_exit,
            'replic_steps': None if self.replic_steps is None else self.replic_steps.to_json(),
        }

        return settings

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    use_scen_sim_settings = property(get_use_scen_sim_settings)

    # --------------------------- instance _PROTECTED methods ----------------------------

    def __check_auto_seeding(self):
        """Check that auto-seeding and seed table settings are consistent, fix as necessary."""
        if self.auto_seed:
            if self.seed_table is not None:
                log.warning("Auto-seeding is enabled. Seed Table {} will not be used.", self.seed_table)

        elif self.seed_table is None:
            self.seed_table = SeedTable(self.num_variants, self.num_replics_per_variant)

        assert self.auto_seed or self.seed_table is not None


class BsmStateClasses:
    READY = _BsmStateReady
    RUNNING = _BsmStateRunning
    PAUSED = _BsmStatePaused
    DONE = _BsmStateDone


def ret_val_on_attrib_except(ret_val):
    """Decorator that will automatically return a specified value if the decorated method raises AttributeError."""

    def decorator(unbound_meth):
        @functools.wraps(unbound_meth)
        def wrapper(self, *args, **kwargs):
            try:
                return unbound_meth(self, *args, **kwargs)
            except AttributeError:
                return ret_val

        return wrapper

    return decorator


class BatchSimManager(IFsmOwner):
    """
    Manages a batch simulation of scenario replications of scenario variants. Its Signals instance derives from
    BridgeEmitter so it can emit backend signals when imported in console variant, but emit PyQt signals when
    imported in the GUI. It forwards several operations to its current
    state object; if the state does not support the operation, an exception gets raised.

    The manager supports two modes of operation, descirbed in the init.
    """

    SETTINGS_FILE_EXT = '.bssj'
    SETTINGS_FILE_NAME = 'batch_sim_settings'

    class Signals(BridgeEmitter):
        sig_state_changed = BridgeSignal(int)  # BsmStatesEnum, but used by BaseFsm which emits as int
        sig_replication_done = BridgeSignal(int, int)  # number of replics done, total number of replics
        sig_replication_error = BridgeSignal(int, int, str)  # num replics done, total num replics, error string
        sig_num_cores_actual_changed = BridgeSignal(int)  # actual number of cores
        sig_scen_path_changed = BridgeSignal(str)  # new path
        sig_batch_folder_changed = BridgeSignal(str)  # new folder for batch
        # time since last start (stops increasing when Done), number of replics done, number of replics pending,
        # average ms per replic, estimate to completion (in seconds) from now:
        sig_time_stats_changed = BridgeSignal(timedelta, int, int, timedelta, timedelta)

    # --------------------------- class-wide methods --------------------------------------------

    @staticmethod
    def remove_all_batch_folders(path: PathType, max_try_time_sec: int = 10):
        """
        Remove all folders in given path.
        Note: if some folders are currently not removable, will try every 10 ms until max_try_time_sec elapsed.
        :return: list of folders not deleted within max time
        """
        GLOB_PATTERN = "batch_*_*x*"
        batch_folders = list(Path(path).parent.glob(GLOB_PATTERN))
        failure_wait_sec = 0.01
        for batch_folder in batch_folders:
            fail_removal = True
            start_time = time.clock()
            while fail_removal and time.clock() - start_time < max_try_time_sec:
                try:
                    shutil.rmtree(str(batch_folder))
                    log.debug('Removed {} after {} sec', batch_folder, time.clock() - start_time)
                    fail_removal = False
                except OSError:
                    time.sleep(failure_wait_sec)

            if fail_removal:
                log.warning('Could not remove {} in less than {} sec', batch_folder, max_try_time_sec)

        # return list of remaining folders that could not be deleted within max time
        return list(Path(path).parent.glob(GLOB_PATTERN))

    @classmethod
    def get_settings_path(cls, scen_path: PathType) -> Path:
        """Get path to batch sim settings file based on given scenario .ORI(B) file"""
        return Path(scen_path).with_name(cls.SETTINGS_FILE_NAME).with_suffix(cls.SETTINGS_FILE_EXT)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, scenario_manager: ScenarioManager, app_settings: AppSettings = None, bridged_ui: bool = False):
        """
        BSM is initialized to a READY state. The presence or absence of a Scenario instance in scenario_manager
        determines the mode of operation:

            - single scenario mode: this mode is used when the scenario is already avialable from the scenario
              manager at init time; the manager will not be monitored for scenario replacements, etc, and BSM
              assumes that app settings will define simulation parameters; the settings from batch sim
              settings file are loaded; if the sim steps are None but overridden from app settings, they
              are copied from the scenario's sim controller sim steps and the relevant overrides are applied.

            - multi scenario mode: this mode is used when the scenario is None at init time; then the BSM will
              monitor the scenario manager for replacement scenario, and will automatically load their settings.
        """
        IFsmOwner.__init__(self)
        self.signals = BatchSimManager.Signals(thread_is_main=True)

        self._app_settings = dict()
        if app_settings:  # use it:
            self._app_settings.update(
                save_log=app_settings.save_log,
                log_deprecated=app_settings.log_deprecated,
                log_raw_events=app_settings.log_raw_events,
                fix_linking_on_load=app_settings.fix_linking_on_load,

                bridged_ui=bridged_ui,
            )

            if hasattr(app_settings, 'loop_log_level') and app_settings.loop_log_level is not None:
                self._app_settings['loop_log_level'] = app_settings.loop_log_level

        self.__scen_sim_step_settings = None
        self.__auto_load_settings = True
        self.__scen_manager = scenario_manager
        self._scen_path = None
        self._settings = None

        if scenario_manager.scenario is None:
            self.__monitor_scen_mgr(scenario_manager)
        else:
            # assume this is command line driven and only one scenario will ever be used
            self.__setup_for_unique_scen(app_settings)

        self._state = _BsmStateReady(fsm_owner=self)
        assert self._settings.auto_seed is True or self._settings.seed_table is not None

    def get_settings(self, copy: bool = False) -> BatchSimSettings:
        """
        By default get a reference to the manager's settings.
        :param copy: set to True to get a copy of the settings
        """
        return deepcopy(self._settings) if copy else self._settings

    def set_settings(self, settings: BatchSimSettings, copy: bool = False):
        """
        By default store a reference to the provided settings, which will be used at the next batch run. This
        method should only be called in the Ready state, otherwise an exception will be raised.
        :param copy: set to True to make a copy of the settings
        """
        self._settings = deepcopy(settings) if copy else settings
        if self._scen_path is not None:
            try:
                self.save_settings()
            except IOError:
                log.warning('Failed to save the new settings of BatchSimManager, will try again at next save or set')

    def save_settings(self):
        """
        Save the current batch sim manager settings for the loaded scenario. Will fail if no scenario loaded
        or new scenario never saved.
        """
        self._settings.save(self.get_settings_path(self._scen_path))

    def load_settings(self):
        """
        Load the batch sim settings for the loaded scenario. Will fail if no scenario loaded
        or new scenario never saved.
        """
        if self._scen_path is None:
            raise FileNotFoundError('Cannot load batch sim settings (no scenario path yet)')

        self._settings = BatchSimSettings.load(self.get_settings_path(self._scen_path))

    def set_auto_load_settings(self, value: bool = True):
        """By default, settings are automatically loaded upon scenario change. Set to False to change this."""
        self.__auto_load_settings = value
        if self.__auto_load_settings:
            try:
                self.load_settings()
            except FileNotFoundError:
                log.warning('Auto-loading of settings now True, but no settings file exists (no scenario folder)')

    def get_scen_sim_steps(self, copy: bool = True) -> SimSteps:
        """
        Get the scenario simulation step settings, i.e. the simulation steps that are specific to the
        scenario's simulation controller.
        :param copy: True if get a copy of settings. Only change
        :return: the scenario's sim step settings, or a new instance of SimSteps if no scenario loaded/new-not-saved
        """
        if self.__scen_sim_step_settings is not None:
            return SimSteps(**json.loads(self.__scen_sim_step_settings))

        return SimSteps()

    def set_replic_sim_steps(self, **step_settings):
        """
        Set the replication sim steps. This causes self.settings.use_scen_sim_settings to become False.
        :param step_settings: same args as sim_controller.SimSteps.__init__
        """
        self._settings.replic_steps = SimSteps(**step_settings)
        assert self._settings.use_scen_sim_settings is False

    def get_num_cores_wanted(self) -> int:
        """Get number of cores set for this or next batch"""
        return self._settings.num_cores_wanted

    def get_num_cores_available(self) -> int:
        """Get how many cores are available on this machine"""
        return mp.cpu_count()

    def get_num_variants(self) -> int:
        """Get number of scenario variants set for this or next batch"""
        return self._settings.num_variants

    def get_num_replics_per_variant(self) -> int:
        """Get number of replications per variant set for this or next batch"""
        return self._settings.num_replics_per_variant

    def get_scen_path(self) -> Path:
        """Get scenario file path for next batch sim run."""
        return self._scen_path

    def get_seed_table(self) -> SeedTable:
        """Get the seed table. If settings.auto_seed is True, returns None"""
        return self._settings.seed_table

    # In the non-ready states, the following methods will work:

    def is_running(self) -> bool:
        """Return true if currently in RUNNING state, false otherwise. """
        return self.is_state(BsmStatesEnum.running)

    def start_sim(self):
        """Attempt to start a batch sim."""
        self._state.start()

    def pause_sim(self):
        """Attempt to pause a batch sim."""
        # Oliver FIXME ASAP: enable pausing when simualtion does not have events/startup parts
        self._state.pause()

    def resume_sim(self):
        """Attempt to resume a batch sim."""
        self._state.resume()

    def stop_sim(self):
        """Attempt to stop a batch sim."""
        self._state.stop()

    def update_sim(self):
        """
        Process any state changes that may have resulted from worker threads.
        Note: this currently doesn't do anything because state is updated by the process thread
        """
        pass

    @ret_val_on_attrib_except(0)
    def get_num_cores_actual(self) -> int:
        """Get number of cores set for this or next batch"""
        return self._state._batch_mon.get_num_cores_actual()

    @ret_val_on_attrib_except(0)
    def get_num_replics_done(self) -> int:
        """Get number of replications that have started and ended (regardless of success)."""
        return self._state._batch_mon.get_num_replics_done()

    @ret_val_on_attrib_except(0)
    def get_num_replics_failed(self) -> int:
        """Get number of replications that have completed with a failure."""
        return self._state._batch_mon.get_num_replics_failed()

    @ret_val_on_attrib_except(0)
    def get_num_variants_done(self) -> int:
        """Get number of variants that have all their replications completed (regardless of success/fail)."""
        return self._state._batch_mon.get_num_variants_done()

    @ret_val_on_attrib_except(0)
    def get_num_variants_failed(self) -> int:
        """Get number of variants that have all their replications completed but at least one replication failed."""
        return self._state._batch_mon.get_num_variants_failed()

    @ret_val_on_attrib_except(0)
    def get_num_replics_in_progress(self) -> int:
        return self._state._batch_mon.get_num_replics_in_progress()

    @ret_val_on_attrib_except(None)
    def get_batch_folder(self) -> Optional[Path]:
        """Get the batch folder of currently running batch sim (or, currently completed batch sim)."""
        return self._state._batch_mon.get_batch_folder()

    @ret_val_on_attrib_except(None)
    def get_batch_results_scen_path(self) -> Optional[Path]:
        """
        Get the path to the batch results scenario available upon completion of a batch run. Returns None if the
        file does not exist (because the batch did not complete, or no batch data was generated by any replication).
        """
        return self._state.get_batch_results_scen_path()

    @ret_val_on_attrib_except(None)
    def get_replic_path(self, variant_id: int, replic_id: int) -> Path:
        """Get the path for the replication from last/current batch"""
        return self._state._batch_mon.get_replic_path(variant_id, replic_id)

    def wait_till_done(self, max_time_sec=None):
        """
        Wait till the BSM is back in ready state, or at most max_time_sec if given. Returns whether the BSM is
        still in running state. Note: The BSM state may change between the time the return value is created and
        it is tested by the caller.
        """
        # Oliver TODO build 3: add test for this
        if max_time_sec:
            start_time = time.clock()
            while self.is_running() and time.clock() - start_time < max_time_sec:
                self.update_sim()
                time.sleep(0.01)

        else:
            while self.is_running():
                self.update_sim()
                time.sleep(0.01)

        return self.is_running()

    def is_state(self, state_id: BsmStatesEnum) -> bool:
        """Return true if our state object has class state_class"""
        return state_id == self._state.state_id

    def get_completion_status(self) -> BatchDoneStatusEnum:
        """Returns the completion status. In ready state, returns not_started"""
        return self._state.get_completion_status()

    def get_batch_log_file_path(self) -> Path:
        """When state=DONE, the log file can be obtained"""
        return self._state.get_batch_log_file_path()

    def get_batch_runs_path(self) -> Path:
        """
        Get the path to folder in which a batch folder will be created when a batch is run. If
        self.settings.batch_runs_path is None then this returns folder containing the scenario file.
        """
        if self._settings.batch_runs_path is None:
            return self.scen_path.parent
        else:
            return Path(self._settings.batch_runs_path)

    def new_batch(self):
        """
        Abandon any "done" batch and return to Ready state from where a new batch can be configured
        and started. Can only be called in DONE state.
        """
        self._state.new_batch()

    # --------------------------- instance PUBLIC properties ----------------------------

    num_cores_wanted = property(get_num_cores_wanted)
    num_cores_available = property(get_num_cores_available)
    num_variants = property(get_num_variants)
    num_replics_per_variant = property(get_num_replics_per_variant)

    seed_table = property(get_seed_table)
    scen_path = property(get_scen_path)
    batch_runs_path = property(get_batch_runs_path)
    batch_folder = property(get_batch_folder)
    batch_results_scen_path = property(get_batch_results_scen_path)

    num_cores_actual = property(get_num_cores_actual)
    num_replics_in_progress = property(get_num_replics_in_progress)
    num_replics_done = property(get_num_replics_done)
    num_replics_failed = property(get_num_replics_failed)
    num_variants_done = property(get_num_variants_done)
    num_variants_failed = property(get_num_variants_failed)

    settings = property(get_settings)

    # --------------------------- instance __SPECIAL__ method overrides ----------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IFsmOwner)
    def _on_state_changed(self, prev_state: BaseFsmState):
        """Signal connected slots that our state has changed"""
        self.signals.sig_state_changed.emit(int(self._state.state_id))

    @internal(BsmStateClasses)
    def _reset_run_time(self):
        self.signals.sig_time_stats_changed.emit(timedelta(0), 0, 0, timedelta(0), timedelta(0))

    @internal(BsmStateClasses)
    def _update_run_time(self, time: timedelta, num_replics_done: int, num_replics_pending: int):
        avg_ms_per_replic = time / num_replics_done if num_replics_done else 0
        etc_sec = avg_ms_per_replic * num_replics_pending
        self.signals.sig_time_stats_changed.emit(time, num_replics_done, num_replics_pending,
                                                 avg_ms_per_replic, etc_sec)

    # --------------------------- instance _PROTECTED and _INTERNAL properties --------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __setup_for_unique_scen(self, app_settings):
        log.debug("WARNING: using single-scenario mode (scenario available at init time), scen mgr NOT monitored")

        # load the scenario batch settings
        self.__on_scen_replaced()

        if app_settings:
            self._settings.num_variants = app_settings.num_variants
            self._settings.num_replics_per_variant = app_settings.num_replics_per_variant
            self._settings.num_cores_wanted = app_settings.num_cores
            self._settings.save_scen_on_exit = app_settings.batch_replic_save

            if app_settings.realtime_scale != 1.0:
                log.warning('Realtime scale not used during batch, settings ({}) ignored',
                            app_settings.realtime_scale)

            if app_settings.seed_file_path is not None:
                self._settings.seed_table = SeedTable(
                    self._settings.num_variants,
                    self._settings.num_replics_per_variant,
                    app_settings.seed_file_path)
                self._settings.seed_table.load()
                self._settings.auto_seed = False

            if app_settings.max_sim_time_days is not None or app_settings.max_wall_clock_sec is not None:
                # if using the scen sim steps, get them, because we have to override a portion: when user does
                # this it is as though they had copied all the other settings over
                if self._settings.replic_steps is None:
                    assert self.__scen_sim_step_settings is not None
                    self._settings.replic_steps = self.get_scen_sim_steps()

                end_settings = self._settings.replic_steps.end
                if app_settings.max_sim_time_days is not None:
                    end_settings.max_sim_time_days = app_settings.max_sim_time_days
                if app_settings.max_wall_clock_sec is not None:
                    end_settings.max_wall_clock_sec = app_settings.max_wall_clock_sec

    def __monitor_scen_mgr(self, scen_mgr: ScenarioManager):
        """
        Setup the BSM assuming that the scenario will be delivered later. For now create a default settings
        obj and connect to scenario manager.
        """
        log.debug("WARNING: BSM does not have a scenario yet, assumes will be delivered later")
        self._settings = BatchSimSettings()
        assert self._settings.auto_seed is True
        assert self._settings.seed_table is None
        assert self._settings.use_scen_sim_settings is True

        scen_mgr_signals = scen_mgr.signals
        scen_mgr_signals.sig_scenario_replaced.connect(self.__slot_on_scen_replaced)
        scen_mgr_signals.sig_scenario_saved.connect(self.__slot_on_scen_saved)
        scen_mgr_signals.sig_scenario_filepath_changed.connect(self.__slot_on_scen_path_changed)
        # forward signal for scen file path changed:
        scen_mgr_signals.sig_scenario_filepath_changed.connect(self.signals.sig_scen_path_changed)

    def __on_scen_path_changed(self, filepath: str):
        log.debug('BSM received signal that scenario file path has changed to {}', filepath)
        self._state.set_scen_path(filepath or None)
        if self._scen_path is not None:
            try:
                self.load_settings()
            except FileNotFoundError as exc:
                log.warning('Could not load scenario {} batch sim settings: {} (like legacy scenario)',
                            self._scen_path, exc)

    def __on_scen_saved(self):
        if self._scen_path is not None:
            settings_path = self.get_settings_path(self._scen_path)
            self._settings.save(settings_path)

    def __on_scen_sim_step_settings_changed(self, json_str: str):
        self.__scen_sim_step_settings = json_str
        # scen_sim_step_settings = json.loads(json_str)
        # self._settings.replic_steps = SimSteps(**scen_sim_step_settings)

    def __on_scen_replaced(self):
        # Oliver TODO build 3.3: change sig_scen_replaced to carry scenario to slots
        #     Reason: no time before interim release, will need to modify IScenarioMonitor
        scenario = self.__scen_manager.scenario
        self._scen_path = scenario.filepath
        self._settings = BatchSimSettings()
        if self.__auto_load_settings and self._scen_path is not None:
            try:
                self.load_settings()
            except IOError as exc:
                log.warning('New scenario loaded, but no batch sim settings file found (likely legacy scenario): {}',
                            exc)

        json_settings = scenario.sim_controller.settings.get_sim_steps(copy=True).to_json()
        self.__scen_sim_step_settings = json.dumps(json_settings)
        assert self.__scen_sim_step_settings is not None

        sig_step_settings_changed = scenario.sim_controller.signals.sig_step_settings_changed
        sig_step_settings_changed.connect(self.__slot_on_scen_sim_step_settings_changed)

    # Oliver FIXME ASAP: define safe_slot slots
    #     Reason: tried this and could not get connections to work, presumably derivations from BridgeEmitter missing
    __slot_on_scen_path_changed = __on_scen_path_changed
    __slot_on_scen_saved = __on_scen_saved
    __slot_on_scen_sim_step_settings_changed = __on_scen_sim_step_settings_changed
    __slot_on_scen_replaced = __on_scen_replaced


class BatchMonitor:
    """
    Monitor a batch of replications that will be queued (outside of this class) for multi-processing.
    The BatchMonitor is useful to keep track of state between the Running, Paused and Done states of
    the BatchSimManager.
    """

    def __init__(self, bsm: BatchSimManager, batch_folder: Path, num_cores_start: int):
        self.__bsm = bsm
        self.__batch_folder = batch_folder
        assert batch_folder is not None
        self.__num_variants = bsm.num_variants
        self.__num_replics_per_variant = bsm.num_replics_per_variant
        self.__pool_mutex = mp.RLock()  # synchro access to data members accessed by Pool threads AND main thread

        self.__num_cores_actual = num_cores_start
        self.__replics_in_queue = []
        self.__replic_results = {}  # each replication has a status as result (indicating its completion status)

        self.__start_time = datetime.now()
        self.__done_time = None

    def on_replic_queued(self, variant_id: int, replic_id: int):
        """Whenever the BatchSimManager queues a replication for execution, it must notify the monitor."""
        with self.__pool_mutex:
            self.__replics_in_queue.append((variant_id, replic_id))

    def get_batch_folder(self) -> Path:
        """Get the batch folder of currently running batch sim (or, currently completed batch sim)."""
        return self.__batch_folder

    def get_replic_path(self, variant_id: int, replic_id: int) -> Path:
        """Get the path for the replication from last/current batch. Raises RuntimeError if batch"""
        return get_replic_path(self.__batch_folder, variant_id, replic_id)

    def get_num_cores_actual(self) -> int:
        """
        Get the number of actual cores in use. This will be less than the original number (num_cores_start)
        when there are fewer replications left than that number.
        """
        with self.__pool_mutex:
            return self.__num_cores_actual

    def get_num_replics_pending(self) -> int:
        """Get the number of replications that are not done yet. Note: Some of them might be in progress."""
        with self.__pool_mutex:
            return len(self.__replics_in_queue)

    def get_num_replics_in_progress(self) -> int:
        """
        Get the number of replication currently executing. This method assumes that it is the number of
        actual cores in use.
        """
        with self.__pool_mutex:
            return self.__num_cores_actual

    def get_num_replics_done(self) -> int:
        """
        Get number of replications that have started and ended, *regardless* of success. So
        num done - num failed = num completed successfully.
        """
        with self.__pool_mutex:
            num_pending = len(self.__replics_in_queue)
            num_done = self.__num_variants * self.__num_replics_per_variant - num_pending
            assert num_done == sum(len(variant_results) for variant_results in self.__replic_results.values())
            return num_done

    def get_num_replics_failed(self) -> int:
        """Get number of replications that have failed."""
        failed = 0
        with self.__pool_mutex:
            for variant_replics in self.__replic_results.values():
                for status in variant_replics.values():
                    if status == ReplicExitReasonEnum.failure:
                        failed += 1
        return failed

    def get_replics_failed(self) -> List[int]:
        """Get number of replications that have failed."""
        failed = []
        with self.__pool_mutex:
            for variant_replics in self.__replic_results.values():
                for replic_id, status in variant_replics.items():
                    if status == ReplicExitReasonEnum.failure:
                        failed.append(replic_id)
        return sorted(failed)

    def get_num_variants_done(self) -> int:
        """Get number of variants that have all their replications completed (regardless of success/fail)."""
        done = 0
        with self.__pool_mutex:
            for variant_replics in self.__replic_results.values():
                if len(variant_replics) == self.__num_replics_per_variant:
                    done += 1
        return done

    def get_variants_failed(self) -> List[int]:
        """Get list of variants that have at least one replication failed."""
        failed_variants = []
        with self.__pool_mutex:
            for variant_id, variant_replics in self.__replic_results.items():
                for status in variant_replics.values():
                    if status == ReplicExitReasonEnum.failure:
                        failed_variants.append(variant_id)
                        break  # stop in this variant at first replic failed

        return sorted(failed_variants)

    def get_num_variants_failed(self) -> int:
        """Get number of variants that have all their replications completed but at least one replication failed."""
        return len(self.get_variants_failed())

    def get_exec_time(self) -> timedelta:
        """Return the amount of time used to run a batch simulation"""
        if self.__done_time is None:
            return datetime.now() - self.__start_time
        return self.__done_time - self.__start_time

    def get_summary(self) -> str:
        num_replics_queued = self.__num_variants * self.__num_replics_per_variant
        num_variants_failed = self.get_num_variants_failed()
        num_replics_failed = self.get_num_replics_failed()
        if num_variants_failed == 0:
            variants_failed = ''
        else:
            variants_failed = '(variant IDs: {})'.format(', '.join(str(id) for id in self.get_variants_failed()))
        if num_replics_failed == 0:
            replics_failed = ''
        else:
            replics_failed = '(replic IDs: {})'.format(', '.join(str(id) for id in self.get_replics_failed()))

        return dedent("""\
            Queued at start: {} replications ({} variants)
            Variants with failures: {} of {} {}
            Replications failed: {} of {} {}
            Execution time (days HH:MM:SS.ss): {}
        """).format(num_replics_queued, self.__num_variants,
                    num_variants_failed, self.get_num_variants_done(), variants_failed,
                    num_replics_failed, self.get_num_replics_done(), replics_failed,
                    self.get_exec_time(),
                    )

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED and _INTERNAL properties --------

    @internal(_BsmStateRunning)
    def _on_background_replic_done(self, result: Tuple[int, int, ReplicStatusEnum]):
        """
        Called when a replication has completed (returned) successfully
        :param result: the tuple returned by self._child_replication
        """
        variant_id, replic_id, status = result
        log.info('Got status "{}" for replication ({},{})', get_enum_val_name(status), variant_id, replic_id)
        with self.__pool_mutex:
            self.__update_state(variant_id, replic_id, status)
            # Notify the GUI that replications have been completed.
            total_replics = self.__num_variants * self.__num_replics_per_variant
            self.__bsm.signals.sig_replication_done.emit(self.get_num_replics_done(), total_replics)

    @internal(_BsmStateRunning)
    def _on_background_replic_error(self, exc: ReplicationError):
        """
        Called when a replication has raised an exception
        :param exc: the ReplicationError that was raised
        """
        if len(exc.args) < 4:
            log.error("Unexpected format for ReplicationError! Type {}, args={}: {}", type(exc), exc.args, exc)
            return

        variant_id, replic_id, err_msg, exc_traceback = exc.args
        log.error('Replication ({}, {}) raised exception, see its log file for details', variant_id, replic_id)
        with self.__pool_mutex:
            status = ReplicExitReasonEnum.failure
            status.set_exc_traceback(err_msg)

            self.__update_state(variant_id, replic_id, status)
            total_replics = self.__num_variants * self.__num_replics_per_variant
            self.__bsm.signals.sig_replication_error.emit(self.get_num_replics_done(), total_replics, err_msg)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __update_state(self, variant_id: int, replic_id: int, status: ReplicExitReasonEnum):
        """Update the state of the monitor. Needs to be called whenever the a replication finishes"""
        self.__done_time = datetime.now()

        variant_results = self.__replic_results.setdefault(variant_id, {})
        variant_results[replic_id] = status

        self.__replics_in_queue.remove((variant_id, replic_id))
        self.__update_cores_actual()

        num_pending = len(self.__replics_in_queue)
        num_done = self.__num_variants * self.__num_replics_per_variant - num_pending
        self.__bsm._update_run_time(self.get_exec_time(), num_done, num_pending)

        self.__bsm._state.on_background_replic_done()

    def __update_cores_actual(self):
        """The number of replications left will eventually < num actual cores"""
        replics_left = len(self.__replics_in_queue)
        if replics_left < self.__num_cores_actual:
            self.__num_cores_actual = replics_left
            if replics_left:
                log.debug('Batch now using {} cores (1 replication process/core)', self.__num_cores_actual)
