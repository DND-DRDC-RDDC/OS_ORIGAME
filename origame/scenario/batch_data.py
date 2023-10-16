# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provides batch data management functionality for batch simulations

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import Enum
from pathlib import Path
import pickle
import sqlite3
from datetime import datetime
import re

# [2. third-party]
import numpy

# [3. local]
from origame.core import internal
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO, AnnotationDeclarations
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "Revision"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'get_db_path',
    'get_batch_data_file_path',
    'get_data_path_type',
    'get_latest_batch_folder',
    'DataPathTypesEnum',
    'BATCH_FOLDER_RE',
    'BATCH_TIMESTAMP_FMT',
    'is_batch_folder',
    'create_batch_data_file',

]

log = logging.getLogger('system')

DEFAULT_DATA_FILE_NAME = 'batch_results.sqlite.db'
BATCH_TIMESTAMP_FMT = '%Y-%m-%d_%H-%M-%S'
# batch run folders have following pattern:
BATCH_FOLDER_RE = re.compile(r"batch_(.+)_\d+x\d+")

#SQLite3 connection timeout (seconds)
TO = 600

class Decl(AnnotationDeclarations):
    SimController = 'SimController'


# -- Function definitions -----------------------------------------------------------------------

def get_batch_data_file_path(batch_data_folder: PathType) -> Path:
    """Given a hypothetical batch folder path, returns what the path would be to its batch-data file"""
    path = Path(batch_data_folder) / DEFAULT_DATA_FILE_NAME
    try:
        return path.resolve()
    except FileNotFoundError:
        return path.absolute()


class DataPathTypesEnum(Enum):
    batch_folder, scen_folder, batch_runs, db, unspecified = range(5)


def get_data_path_type(path: PathType) -> DataPathTypesEnum:
    """
    Return an enumeration member that identifies what the path references. The inference is as
    follows:
    - a batch data results file if its name ends in .sqlite.db
    - else, a batch folder if path matches "batch_datetimestamp_NxM"
    - else, a scenario folder if path has at least *.ori|b file
    - else, assume it is a batch runs folder that will contain one or more batch folders
    """
    path = Path(path)
    if path.name.endswith('.sqlite.db'):
        return DataPathTypesEnum.db

    if is_batch_folder(path):
        return DataPathTypesEnum.batch_folder

    if path.glob('*.ori') or path.glob('*.orib'):
        return DataPathTypesEnum.scen_folder

    return DataPathTypesEnum.batch_runs


def get_latest_batch_folder(runs_folder: PathType) -> Optional[Path]:
    """
    Get the most recent batch run folder.
    :param runs_folder: the folder in which to look for most recent batch run folder
    :return: the path, or None if no batch run folders found under runs_folder
    """
    GLOB_PATTERN = "batch_*_*x*"
    batch_folders = list(Path(runs_folder).glob(GLOB_PATTERN))
    latest_folder = None
    latest_stamp = None
    same_timestamp_folder = None
    for batch_folder in batch_folders:
        timestamp = datetime.strptime(BATCH_FOLDER_RE.match(batch_folder.name).group(1), BATCH_TIMESTAMP_FMT)
        if latest_stamp is None or timestamp >= latest_stamp:
            if timestamp == latest_stamp:
                same_timestamp_folder.append(batch_folder)
            else:
                latest_stamp = timestamp
                same_timestamp_folder = []
            latest_folder = batch_folder

    if same_timestamp_folder:
        log.warning('Several batch runs have same time stamp, will use {}', latest_folder)

    return latest_folder


def is_batch_folder(path: PathType) -> bool:
    """Return True if the given path is a batch folder, False otherwise"""
    return BATCH_FOLDER_RE.match(Path(path).name) is not None


def get_db_path(path: Optional[PathType], file_type: DataPathTypesEnum = None) -> Optional[Path]:
    """
    Get the path to a batch data file path.
    :param path: the path to start from
    :param file_type: the type of object that the path refers to; if unspecified, the function will
        attempt to guess it
    :return: the path to .sqlite.db file, or None if could not be resolved; if resolved, it will be either
        - the Path(path) given as argument
        - the batch data file that is under path, assuming path is a batch folder
        - the batch data file that is in scenario folder, assuming path is a scenario folder (but not a batch folder)
        - the batch data file of the latest batch run that is found under path, assuming path is a batch runs folder
    """
    if path is None:
        return None

    if file_type is None or file_type == DataPathTypesEnum.unspecified:
        file_type = get_data_path_type(path)

    if file_type == DataPathTypesEnum.db:
        return Path(path)

    if file_type == DataPathTypesEnum.batch_folder:
        # if caller specified that path is a batch batch but it is not, then return None
        if not is_batch_folder(path):
            raise ValueError('Path {} is not of type batch_folder'.format(path))
        return get_batch_data_file_path(path)

    if file_type == DataPathTypesEnum.scen_folder:
        return get_batch_data_file_path(path)

    assert file_type == DataPathTypesEnum.batch_runs
    batch_folder = get_latest_batch_folder(path)
    return None if batch_folder is None else get_batch_data_file_path(batch_folder)


def create_batch_data_file(path: PathType, file_type: DataPathTypesEnum = None):
    """
    Create the batch data file. Useful for BatchSimManager to ensure that there is no race by batch replications
    to create this file.
    """
    results_db_path = get_db_path(path, file_type=file_type)
    sqlite3.connect(str(results_db_path), timeout=TO)


def erase_batch_data_file(path: PathType):
    data_path = get_batch_data_file_path(path)
    log.warning("Erasing batch replication data file {}", data_path)
    data_path.unlink()


# -- Class Definitions --------------------------------------------------------------------------

class BatchReplicData:
    """Batch data for *one* replication"""

    def __init__(self):
        """The folder must contain the SQLite3 database used for batch data."""
        self.__results = None
        self.__allowed_data_keys = None

    def add_allowed_keys(self, key_names: List[str]):
        """
        Add the allowed keys for setting replication data. This method can be called many times (such as, by
        a startup part in each submodel of a scenario), but keys can only be added once, or an error is raised.
        If this method is never called, all keys are allowed.
        :param key_names: list of key names that will be allowed in calls to set()
        """
        if self.__allowed_data_keys is None:
            self.__allowed_data_keys = set(key_names)
            return

        already_keys = self.__allowed_data_keys.intersection(key_names)
        if already_keys:
            msg_tmpl = 'Batch data keys {} already added, keys can only be added once'
            raise ValueError(msg_tmpl.format(', '.join(sorted(already_keys))))

        self.__allowed_data_keys.update(key_names)

    def get_allowed_keys(self) -> Optional[List[str]]:
        """Return a list of allowed key names, or None if all key names allowed"""
        return None if self.__allowed_data_keys is None else sorted(self.__allowed_data_keys)

    def clear_allowed_keys(self):
        """Allow any key names to be given in calls to set(). This is the default."""
        self.__allowed_data_keys = None

    def set(self, **data: Any):
        """
        Set data for this replication. This method can be called multiple times. If common keys are used,
        the corresponding data is overwritten.
        """
        if self.__allowed_data_keys is not None:
            unknown_keys = set(data).difference(self.__allowed_data_keys)
            if unknown_keys:
                msg_tmpl = 'Batch data keys {} not allowed (use add_allowed_data_keys() to allow them)'
                raise ValueError(msg_tmpl.format(', '.join(sorted(unknown_keys))))

        if self.__results is None:
            self.__results = data
        else:
            self.__results.update(data)

    def get(self) -> Optional[Dict[str, Any]]:
        """Get the data set so far on this replication. If set() was never called, this returns None."""
        return self.__results

    def reset(self):
        """Restore to init state: clear data and allowed keys"""
        self.clear()
        self.clear_allowed_keys()

    def clear(self):
        """Clear all set data"""
        self.__results = None


class VariantData:
    """
    Data for all replications of a specific batch run variant. The keys set by replications are available as
    keys, the associated value being a numpy array. Example: if replications ran a scenario that calls
    batch.set_replication_data(...) one or more times such that keys a, b, c are defined, then
    batch.load(variant_id=1) will return a map with keys a, b, and c, and the associated value in each case
    is a numpy array of values saved by the replications.
    """

    def __init__(self, variant_id: int, db_data: Dict[str, Dict[int, Any]]):
        self.__variant_id = variant_id
        self.__data = db_data

    @property
    def variant_id(self) -> int:
        return self.__variant_id

    def __getitem__(self, item: str) -> numpy.array:
        return numpy.array(list(self.__data[item].values()))

    def __len__(self):
        """Returns the number of data keys"""
        return len(self.__data)

    def keys(self) -> Set[str]:
        return set(self.__data.keys())

    def get_raw_data(self, key: str) -> Dict[int, Any]:
        return self.__data[key]


class BatchDataMgr:
    """
    Manages access to batch data for several use-cases:

    1. for replications: they must tell their scenario that the batch folder is location for saving replication data
    2. for the batch sim manager: the bsm must tell the scenario that the batch folder is location for
        loading batch data, so it can run the batch function parts of the scenario after all replications have
        completed; it does this on a separately loaded scenario, so as not to affect any already loaded scenario
        (relevant in gui)
    4. for a Python script: it must be able to point directly to a data file, or point to a scenario folder,
        batch folder, or batch runs folder from which the data file can be inferred.

    For this reason, the batch data manager can be given a data path and what type of path it is: scenario path,
    batch folder, etc. If the type is not given, the BDM will attempt to guess it.

    If configured with a batch runs path, then whenever the load_data() or write_replication_data() methods
    are called, the instance attempts to find the latest batch run in the batch runs path and uses the
    batch data file found there. **NOTE**: This config option is now OBSOLETE. It was added to support the
    user running a batch from the GUI, so that they could see results in GUI by running a batch part. However
    this interferes with the testability of the user's scenario: while preparing their scenario to generate
    replication data and post-process the data, the user needs an easy way to run the associated parts from
    the GUI, i.e. the parts should assume the scenario folder as the location of data storage.
    Running batch parts within the GUI scenario also has the disadvantage that the scenario ends up modified,
    merely to show batch data which has nothing to do with the scenario model itself.
    Therefore the recommendation is to have instead a "batch data display" panel in the GUI and some batch functions
    like "plot_data()" or "tabulate_data()" that can be called from batch part scripts: these functions send data
    to the panel. The panel is disabled if no batch is running or has completed; the panel shows current batch
    folder otherwise; or the panel can be configured to point to a specific batch folder (via File browser);
    and sending data to it does not modify the scenario. When called from a console batch, these functions
    have no effect.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, data_path: PathType = None, file_type: DataPathTypesEnum = None):
        self.__sim_controller = None
        self.__replic_data = None

        self.__data_path = None
        self.__file_type = None
        if data_path is not None:
            self.set_data_path(data_path, file_type=file_type)

        self.replic_data_buffer = []

    def set_data_path(self, data_path: Optional[PathType], file_type: DataPathTypesEnum = None):
        """
        Set or change the data path to use when loading batch data or writing replication data.
        The caller may provide None; in this case, the file type is ignored and load_data() and
        write_replication_data() will fail until data path is set to something that those methods
        can resolve at call time.
        """
        if data_path is None:
            self.__data_path = None
            self.__file_type = None
            return

        if file_type is None:
            file_type = get_data_path_type(data_path)

        if file_type == DataPathTypesEnum.batch_runs:
            self.__data_path = data_path
            self.__file_type = file_type
        else:
            # it may be resolvable immediately:
            self.__data_path = get_db_path(data_path, file_type=file_type)
            self.__file_type = None if self.__data_path is None else file_type

    @property
    def is_data_file_path_resolved(self) -> bool:
        """Is true only if data path defined and is not of type DataPathTypesEnum.batch_runs"""
        return self.__data_path is not None and self.__file_type != DataPathTypesEnum.batch_runs

    def get_data_file_path(self, data_path: PathType = None, file_type: DataPathTypesEnum = None) -> Path:
        """
        Get the path to the actual batch data file that will be used if load_data() or write_replication_data()
        are called.
        """
        if data_path is not None:
            return get_db_path(data_path, file_type=file_type)

        if self.__file_type == DataPathTypesEnum.batch_runs:
            return get_db_path(self.__data_path, DataPathTypesEnum.batch_runs)

        # if it is not a batch-runs path, it has already been resolved:
        return self.__data_path

    def has_data(self, data_path: PathType = None, file_type: DataPathTypesEnum = None) -> bool:
        """Return True if the data file for the given path/type exists and contains data; False otherwise."""
        results_db_path = self.get_data_file_path(data_path=data_path, file_type=file_type)
        if results_db_path is None or not results_db_path.exists():
            return False

        conn = sqlite3.connect(str(results_db_path), timeout=TO)
        with conn:
            table_names = self.get_key_names(data_path=results_db_path, file_type=DataPathTypesEnum.db)
            return bool(table_names)

    def load_data(self, variant_id: int,
                  data_path: PathType = None, file_type: DataPathTypesEnum = None) -> VariantData:
        """
        Load batch data and return it.

        :param variant_id: the variant ID for which to load data
        :param data_path: the path to the data; if None, the path already set (at init time or via
            set_data_path()) will be used
        :param file_type: the type of path given; if None, the type will be inferred via get_data_path_type(), ie:
            - a batch data results file, if its name ends in .sqlite.db
            - else, a batch folder, if path matches "batch_W+_D+xD+" where + means at least once, D means digit,
                and ? means any word character
            - else, a scenario folder if path has at least one *.ori|b file
            - else, assume it is a batch runs folder that will contain one or more batch folders

        :return: the data loaded
        :raise RuntimeError: if no path set and no path given as argument
        """
        results_db_path = self.get_data_file_path(data_path=data_path, file_type=file_type)
        if results_db_path is None or not results_db_path.exists():
            raise RuntimeError('Could not load data from {}, file does not exist'.format(results_db_path))

        conn = sqlite3.connect(str(results_db_path), timeout=TO)
        data = {}
        with conn:
            table_names = self.get_key_names(data_path=results_db_path, file_type=DataPathTypesEnum.db)
            for table_name in table_names:
                sql_cmd = 'SELECT replic_id, py_pickled_obj FROM {} WHERE variant_id=?'
                cursor = conn.execute(sql_cmd.format(table_name), (variant_id,))
                data[table_name] = {replic_id: pickle.loads(obj) for replic_id, obj in cursor.fetchall()}

        return VariantData(variant_id, data)

    def get_key_names(self, data_path: PathType = None, file_type: DataPathTypesEnum = None) -> List[str]:
        """
        Get the list of data keys for a batch data file. The call parameters have the same meaning as for
        load_data().
        :return: the list of key names
        """
        results_db_path = self.get_data_file_path(data_path=data_path, file_type=file_type)
        if results_db_path is None or not results_db_path.exists():
            raise RuntimeError('Could not get data keys from {}, file does not exist', results_db_path)

        sql_cmd = "SELECT name FROM sqlite_master WHERE type='table'"
        conn = sqlite3.connect(str(results_db_path), timeout=TO)
        with conn:
            result = conn.execute(sql_cmd).fetchall()
            return [r[0] for r in result]

    # ---------------------------------------- REPLICATION layer --------------------------------

    def add_allowed_data_keys(self, *key_names):
        """
        Add the allowed keys for setting replication data. This method can be called many times (such as, by
        a startup part in each submodel of a scenario), but keys can only be added once, or an error is raised.
        If this method is never called, all keys are allowed.
        :param key_names: list of key names that will be allowed in calls to set()
        """
        self.__replic_data.add_allowed_keys(key_names)

    def get_allowed_data_keys(self) -> List[str]:
        """Return a list of allowed key names, or None if all key names allowed"""
        return self.__replic_data.get_allowed_keys()

    def set_replication_data(self, **data):
        """
        Set the key-value pairs for the *currently running* replication. This should only be called by a
        function part executing as part of a scenario simulation (replication). The data is automatically
        associated with the variant and replication ID currently being used by the simulation. It can be
        called multiple times during a run. Existing data for a given key gets overwritten. See
        get_replication_data() for an example.
        """
        self.__replic_data.set(**data)

    def get_replication_data(self) -> Dict[str, Any]:
        """
        Get all the replication data set so far for the currently running scenario simulation (replication).
        This is the data set via all the calls done so far to set_replication_data(). For example, given

        set_replication_data(a=1, b=2)
        set_replication_data(a=4, c=3)

        then get_replication_data() will return dict(a=4, b=2 and c=3).
        """
        return self.__replic_data.get()

    def write_replication_data(self):
        """
        Commit the data set to a file, for current values of variant and replication ID. *Does nothing* if there is
        no data saved. The file will be created if it doesn't exist. Raises exception if a path to a data file
        could not be determined. This method is automatically called when a scenario is shutdown, but it may be
        called by a script if early write is required (say, because a part causes exception that causes replication
        to end before data written).
        """
        data = self.__replic_data.get()
        if not data:
            # no data, nothing to do, don't even try to connect
            return

        variant_id = self.__sim_controller.variant_id
        replic_id = self.__sim_controller.replic_id
        self.__write_batch_data(variant_id, replic_id, data)

    def write_test_replication_data(self, variant_id: int, replic_id: int, **data: Any):
        """
        Save batch TEST data to the database. Calls to this method should be disabled (commented out in scripts)
        before running a batch unless testing batch processing.
        :param variant_id: variant ID for which TEST data is being defined
        :param replic_id: replication ID for which TEST data is being defined
        :param data: the data
        """
        self.__write_batch_data(variant_id, replic_id, data)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    data_file_path = property(get_data_file_path)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    @internal
    def _create_replic_data_store(self, sim_controller: Decl.SimController):
        self.__sim_controller = sim_controller
        self.__replic_data = BatchReplicData()

    @internal
    def _reset(self):
        self.__replic_data.reset()

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __write_batch_data(self, variant_id: int, replic_id: int, data: Dict[str, Any]):
        """
        Write data to the batch data database.
        :param variant_id: variant ID for which TEST data is being defined
        :param replic_id: replication ID for which TEST data is being defined
        :param data: the data
        """
        self.replic_data_buffer.append({"variant_id": variant_id, "replic_id": replic_id, "data": data})
        self.__write_batch_data_to_db()

    def __write_batch_data_to_db(self):
        data_file = self.get_data_file_path()
        if data_file is None:
            raise RuntimeError("No data file could be identified, cannot write replication data to file")

        try:
            with sqlite3.connect(str(data_file), timeout=TO) as conn:
                replic_data = self.replic_data_buffer[-1] # Write data to database on first-in-first-out basis
                variant_id = replic_data["variant_id"]
                replic_id = replic_data["replic_id"]
                data = replic_data["data"]
                log.info("Saving batch replication data to {}", data_file)
                for data_key in data:
                    table_name = data_key
                    if re.match(r'\w+$', table_name) is None:
                        raise RuntimeError("DANGER! the key name is somehow not a word!")

                    sql_cmd = 'CREATE TABLE IF NOT EXISTS {} (replic_id INTEGER, variant_id INTEGER, py_pickled_obj BLOB)'
                    conn.execute(sql_cmd.format(table_name))
                    data_pickle = pickle.dumps(data[data_key])
                    conn.execute('INSERT INTO {} VALUES (?, ?, ?)'.format(table_name),
                                (replic_id, variant_id, data_pickle))
                conn.commit()
                self.replic_data_buffer.pop() # Once the data is written to the database, remove it from the buffer

        except sqlite3.OperationalError:
            log.info("Saving batch replication data to {} failed, trying again ...", data_file)

        else:
            log.debug('Data for keys {} saved', ', '.join(sorted(data)))

        finally:
            if (len(self.replic_data_buffer)):
                self.__write_batch_data_to_db()
