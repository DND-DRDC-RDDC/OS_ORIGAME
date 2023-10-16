# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains code to support the handling and serialization of Origame scenario data.

The module includes key name definitions to assist scenario data handling and to aid in
serialization and deserialization of origame scenario data, as well as a serialization interface
for the serialization of origame scenarios to/from .ori file.


Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import json
from enum import IntEnum, unique, Enum
import logging
import functools
import pickle, base64

# [2. third-party]

# [3. local]
from ..core import override_required, override_optional
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..core.typing import AnnotationDeclarations

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # defines module members that are public; one line per string
    'IOriSerializable',
    'OriSchemaEnum',
    'OriBaselineEnum',
    'OriContextEnum',
    'OriScenarioKeys',
    'OriScenData',
    'JsonObj',
    'OriScenarioDefKeys',

    'OriCommonPartKeys',
    'OriPartFrameKeys',
    'OriActorPartKeys',
    'OriButtonPartKeys',
    'OriClockPartKeys',
    'OriDateTimePartKeys',
    'OriDataPartKeys',
    'OriFunctionPartKeys',
    'OriImageDictionaryKeys',
    'OriInfoPartKeys',
    'OriPlotPartKeys',
    'OriPulsePartKeys',
    'OriHubPartKeys',
    'OriMultiplierPartKeys',
    'OriNodePartKeys',
    'OriLibraryPartKeys',
    'OriSheetPartKeys',
    'OriSocketPartKeys',
    'OriSqlPartKeys',
    'OriTablePartKeys',
    'OriTimePartKeys',
    'OriVariablePartKeys',
    'OriFilePartKeys',

    'OriSimConfigKeys',
    'OriSimEventKeys',

    'OriPositionKeys',
    'OriSizeKeys',
    'OriRotation3dKeys',
    'OriPartLinkKeys',
    'OriWaypointKeys',
    'SaveError'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def pickle_to_str(pickle: bytes) -> str:
    """Package the pickle representation of a Python object into a string"""
    return base64.b64encode(pickle).decode("utf-8")


def pickle_from_str(data: str) -> bytes:
    """Unpackage a string returned by pickle_to_str() into the original object (new instance)"""
    return base64.b64decode(str.encode(data))


def check_needs_pickling(value: Any) -> Tuple[bool, Any]:
    """Check if a python object needs pickling in order to be saved in ORI json"""
    try:
        json_repr = json.dumps(value)
        unjsoned = json.loads(json_repr)
        if unjsoned != value:
            return True, unjsoned

    except TypeError:
        assert value is not None
        return True, None

    return False, None


def get_pickled_str(value: Any, location: Enum) -> Tuple[str, bool]:
    """
    Get a "nice" string representation of a pickle of a value.

    :param value: Python object to pickle and "stringify"
    :return: The "nice" string and a flag indicating if the pickling succeeded (True) or not (False)
    """
    try:
        pickled_val = pickle.dumps(value)
        return pickle_to_str(pickled_val), True

    except Exception as ex:
        return SaveError(value, location).to_json(), False


# -- Class Definitions --------------------------------------------------------------------------

class SaveError():
    """ This class represents an object that will replace any non-serializble object in the save model """

    def __init__(self, obj: Any, location_enum: Enum):
        self.type = type(obj).__name__
        self.location = location_enum.name

    def to_json(self) -> str:
        """ Converts this class to a JSON serializble format """
        return f'SaveError: {json.dumps(self.__dict__)}'

    def get_type_from_json(jsond_str: str) -> str:
        """Returns type of the given JSON-formatted SaveError object"""
        jsond = jsond_str.split('SaveError: ')[-1]
        return json.loads(jsond)['type']

    def get_location_from_json(jsond_str: str) -> str:
        """Returns location of the given JSON-formatted SaveError object"""
        jsond = jsond_str.split('SaveError: ')[-1]
        return json.loads(jsond)['location']


class SaveErrorLocationEnum(IntEnum):
    """
    Enumerate the various locations of the non-serializable objects
    """
    data_part, variable_part, sheet_part, event_queue, other = range(5)


@functools.total_ordering
@unique
class OriSchemaEnum(Enum):
    """
    This class represents the scenario schema versions supported by the application. The less-than operator
    is defined so that, together with functools.total_ordering, schema versions can be order-compared.
    The comparison makes sense only if enumeration values increase with time.
    """

    prototype = 0  # schema used at end of build 1 to indicate DRDC Prototype scenario
    version_1 = 1  # schema used at end of build 1 to indicate Origame build 1 scenario
    # in practice there were no differences between the prototype and version_1 schema, both in Origame

    # schema used at end of build 2: during build 2, references to scenario parts (as needed for actor children,
    # part links, etc) implemented via object ID rather than relative paths through actor hierarchy;
    # some aliases were added;
    version_2 = 2

    # between end of build 2 and build 3 iteration 1 release:
    # - only use pickling when cannot json-ify values (Variable, Data, and Sheet parts);
    # - part size now includes header;
    version_2_1 = 2.1

    # moved sim settings out of scenario
    version_2_2 = 2.2

    # use repr in Variable, Data and Sheet parts (last few weeks of build 4)
    version_3 = 3

    # use json/unjson strategy in Variable, Data and Sheet parts (end of build 4)
    version_4 = 4  # end of build 4

    def __lt__(self, other):
        return self.value < other.value


class OriBaselineEnum(IntEnum):
    """Each ORI serializable object has a baseline that can be set via IOriSerializable.set_ori_snapshot_baseline()"""
    existing = 1  # use the existing baseline already saved
    current = 2  # create a new baseline based on current state
    last_get = 3  # use the baseline that was saved as part of the last get_ori_def() (and discard existing)


@unique
class OriContextEnum(IntEnum):
    """
    This class represents the ORI transaction types for the IOriSerializable interface.
    Note: the difference between "copy" and "assign" is that the latter copies the content only.
    """
    save_load, export, copy, assign = range(4)


class Decl(AnnotationDeclarations):
    IOriSerializable = 'IOriSerializable'
    OriScenData = 'OriScenData'


class JsonObj(dict):
    """
    A JSON object. A JSON object is represented in Python by a Dict[str, Any] i.e. a dict
    where every key is a string, and every value is an object as supported by json.JSONEncoder
    (as of Python 3.11, these are dict, list, typle, str, int, float, int-derived Enums, float-derived Enums,
    True, False, and None; dict is a JsonObj!).
    """
    pass


class OriScenData(JsonObj):
    """Extends JsonObj to support schema version of the JSON data"""

    DEFAULT_SCHEMA_VERSION = OriSchemaEnum.version_4

    @staticmethod
    def get_schema(data: JsonObj) -> Optional[float]:
        """Return the schema version for this JsonObj"""
        data_version = data.get(OriScenarioKeys.SCHEMA_VERSION) or data.get(OriScenarioKeys.SCHEMA_VERSION_ALIAS)
        return data_version

    def __init__(self, data: JsonObj, schema_version: OriSchemaEnum = None):
        """
        Extends a JsonObj so that schema versioning information can be propagated to "sub" JsonObj, so that
        IOriSerializable objects can take action based on the scenario's schema version.

        :param data: the JSON-compatible dictionary of data representing the scenario (or a portion of it)
        :param schema_version: if given, it will be stored, and can be retrieved by IOriSerializable._set_from_ori()
        via the schema_version property. If the data contains a key for the schema version, it must agree with
        schema_version. If schema_version is None, then it will be taken from the data or, if data does not
        define it, from DEFAULT_SCHEMA_VERSION.
        """
        super().__init__(data)

        data_version = self.get_schema(data)
        if schema_version is None:
            # use whatever is in the data:
            if data_version is None:
                # it is not in the data either, use default:
                schema_version = self.DEFAULT_SCHEMA_VERSION
            else:
                schema_version = OriSchemaEnum(data_version)

        elif data_version is not None:
            # it better agree with the schema_version given:
            if OriSchemaEnum(data_version) != schema_version:
                msg = "Schema version {} does not equal data's schema_version value {}"
                raise ValueError(msg.format(schema_version, data_version))

        assert schema_version is not None
        self.__schema_version = schema_version

    def get_schema_version(self) -> OriSchemaEnum:
        """Get the scenario ORI schema version of this OriScenData"""
        return self.__schema_version

    def get_sub_ori(self, key: str, default: Any = None) -> Decl.OriScenData:
        """Get the sub OriScenData for the given key of self"""
        child_ori = self.get(key, default) or default  # support None child instead of dict child
        return OriScenData(child_ori, schema_version=self.__schema_version)

    def get_sub_ori_list(self, list_key: str) -> List[Decl.OriScenData]:
        """Get the value for given key, transformed from a list of JsonObj to a list of OriScenData"""
        return [OriScenData(child_ori, schema_version=self.__schema_version)
                for child_ori in self.get(list_key, [])]

    def iter_sub_ori(self) -> Stream:
        """Get an iterator over the key-value pairs of this OriScenData"""
        for key, value in self.items():
            yield key, OriScenData(value, schema_version=self.__schema_version)

    schema_version = property(get_schema_version)


class IOriSerializable:
    """
    Provide serialization and deserialization functionality for Origame scenarios. Classes that derive from
    this class are serializable to the ORI format, which can be saved to JSON file, and loaded from a JSON file
    that follows the ORI schema. Also, this class is designed such that an instance can be queried to
    indicate whether it has unsaved ORI data.

    Serialization is based on the following strategy:

    1. a caller calls get_ori_def() on a top-level instance of IOriSerializable. This returns a data structure
       that can be saved directly to a JSON file via the json module. Note: the top-level instance must call
       get_ori_def() on its children, thus resulting in a hierarchical data structure which the json module
       will map to a JSON object hierarchy.
    2. the caller then calls the instance's set_ori_snapshot_baseline(status of save) to indicate what to do with the
       temporary baseline created by get_ori_def(). If save succeeded, temp baseline becomes the new baseline,
       else the temp baseline must be dropped.

    Deserialization is based on a similar strategy:

    1. a JSON file that adheres to ORI schema is loaded into memory, producing a dict tree data structure
    2. a caller instantiates the top-level instance of IOriSerializable with some default settings
    3. the caller calls set_from_ori() on the top-level instance, with the data structure. The instance must
       call set_from_ori() on its children using the correct subset of the data structure.

    Checking whether ORI data has changed since last deserialization or last save uses the following strategy:

    - Upon deserialization, a baseline "snapshot" is created; every IOriSerializable must override
      _get_ori_snapshot_local(fast_dict, slow_dict) to provide a "snapshot" of ORI data of the instance at call time;
      memory-heavy data should be hashed
    - Upon serialization, a temporary baseline "snapshot" is created, by using the same
      update_ori_cmp_locals(fast_dict, slow_dict), based on the state at call time
    - The has_ori_changes() can be called at any time to determine if there are any changes anywhere in the
      hierarchy of IOriSerializable rooted at that instance; this uses the following strategy:
      - first compare "fast" local data to baseline, i.e. data that consists of simple objects like
          strings, numbers, tuples, and small lists (this uses _get_ori_snapshot_local(dict, None))
      - if no changes, check "slow" local data, i.e. data that is costly to compare (this uses _has_ori_changes_slow())
      - if no changes, check children data (this uses _has_ori_changes_children())
    - By default, a new instance of an IOriSerializable returns has_ori_changes() = True. The one situation where
      this is not desirable is when creating a new Scenario that has yet to be altered in any way. In this case,
      has_ori_changes() should return False so that the user is not prompted to save a default, unaltered scenario
      format. The scenario manager should establish the loaded scenario as baseline after it is loaded, by calling
      set_ori_snapshot_baseline(OriBaselineEnum.existing).

    This comparison strategy is pull-based since traversing a tree of objects is a costly operation. The strategy
    supports changes occurring via scripting and GUI, and changes being reverted. Some breakdown of has_ori_changes()
    into several steps decreases the likelihood that user will have to wait more than a split second to know if
    there are unsaved changes, even for a rather large scenario.
    """

    # Any derived class that uses _has_ori_changes_children() must have this set to true
    _ORI_HAS_CHILDREN = False

    # Any derived class that uses _has_ori_changes_slow() must have this set to true
    _ORI_HAS_SLOW_DATA = False

    __ORI_FAST_DATA_INDEX, __ORI_SLOW_DATA_INDEX = 0, 1

    def __init__(self):
        """By default, an IOriSerializable does not have any baseline so it will default to "has changes"."""
        self._ori_snapshot_locals_baseline = None
        self._ori_snapshot_locals_last_get = None

    def set_from_ori(self,
                     ori_data: OriScenData,
                     context: OriContextEnum = OriContextEnum.save_load,
                     **kwargs):
        """
        Configure the current instance with ORI data, the serialization format used for Origame scenarios.
        This calls the _set_from_ori_impl() where derived class should set its state from ori_data and kwargs.
        It then takes a snapshot of the new state as new baseline for future has_ori_changes() calls.

        :param ori_data: data from which to set the state of this instance (and its children); if it is not an
            OriScenData, an OriScenData(ori_data) will be used
        :param context: the call context (load, copy, or export)
        :param kwargs: settings that will be passed as-is to _set_from_ori_impl(..., **kwargs)
        """
        # need to support creation from a raw dict-like object:
        if not isinstance(ori_data, OriScenData):
            ori_data = OriScenData(ori_data)
        self._set_from_ori_impl(ori_data, context, **kwargs)
        self.set_ori_snapshot_baseline(OriBaselineEnum.current)

    def has_ori_changes(self) -> bool:
        """
        Determine if any of the ORI-related state data has changed since the last baselining (most recent of
        set_from_ori() and set_ori_snapshot_baseline(True)). First checks fast data only, via
        _get_ori_snapshot_local(fast_dict, None). If _ORI_HAS_SLOW_DATA is true, calls
        _has_ori_changes_slow() to derived class can compare costly data to baseline.
        If _ORI_HAS_CHILDREN is true, calls _has_ori_changes_children() so derived class can call
        has_ori_changes() on all its children.
        """
        if self._ori_snapshot_locals_baseline is None:
            return True

        # Oliver FIXME: should only get slow data if fast_changed False
        self._ori_snapshot_locals_last_get = (JsonObj(), JsonObj())
        self._get_ori_snapshot_local(*self._ori_snapshot_locals_last_get)
        # first check fast data:
        fast_data = self._ori_snapshot_locals_last_get[self.__ORI_FAST_DATA_INDEX]
        fast_changed = (fast_data != self._ori_snapshot_locals_baseline[self.__ORI_FAST_DATA_INDEX])
        if fast_changed:
            self.__log_ori_change()
            return True

        # no fast changes, get slow and check it:
        if self._ORI_HAS_SLOW_DATA:
            last_get = self._ori_snapshot_locals_last_get[self.__ORI_SLOW_DATA_INDEX]
            baseline = self._ori_snapshot_locals_baseline[self.__ORI_SLOW_DATA_INDEX]
            has_slow_change = self._has_ori_changes_slow(baseline, last_get)
            if has_slow_change:
                self.__log_ori_change('"slow"')
            return has_slow_change

        if self._ORI_HAS_CHILDREN:
            has_child_change = self._has_ori_changes_children()
            if has_child_change:
                self.__log_ori_change('child')
            return has_child_change

        # no slow data changed either, done:
        return False

    def get_ori_def(self, context: OriContextEnum = OriContextEnum.save_load) -> JsonObj:
        """
        Get a data structure that represents the current state of this instance, according to the ORI schema.
        Also creates a temporary baseline from this state by calling derived _get_ori_snapshot_local(fast, slow).
        The temp baseline should be "committed" or dropped via a suitable call to set_ori_snapshot_baseline().
        :param context: The context under which the function is being called (save, copy, or export).
        """
        if self._ori_snapshot_locals_last_get is None:
            self._ori_snapshot_locals_last_get = ({}, {})
            self._get_ori_snapshot_local(*self._ori_snapshot_locals_last_get)

        return self._get_ori_def_impl(context)

    def set_ori_snapshot_baseline(self, baseline_id: OriBaselineEnum):
        """
        Adjust the baseline. Call after calling get_ori_def() to indicate if the temporary baseline it created
        should become the new baseline, or should be dropped, or call at anytime to make the current state of the
        IOriSerializable the new baseline.

        :param baseline_id: value to indicate which baseline to keep: current to create a new one based on current
            state; last_get to keep the one created by get_ori_def(); existing to drop the one created by
            get_ori_def().
        """
        if baseline_id == OriBaselineEnum.current:
            self._ori_snapshot_locals_baseline = ({}, {})
            self._get_ori_snapshot_local(*self._ori_snapshot_locals_baseline)
            self._ori_snapshot_locals_last_get = None

        if baseline_id == OriBaselineEnum.last_get:
            self._ori_snapshot_locals_baseline = self._ori_snapshot_locals_last_get
            self._ori_snapshot_locals_last_get = None

        if baseline_id == OriBaselineEnum.existing:
            self._ori_snapshot_locals_last_get = None
            # assert self._ori_snapshot_locals_baseline is not None

        if self._ORI_HAS_CHILDREN:
            self._set_ori_snapshot_baseline_children(baseline_id)

    def get_ori_diffs(self, other_ori: Decl.IOriSerializable, tol_float=0.00001) -> Dict[str, Any]:
        """
        Get the ORI differences between this object and another. This delegates to the overridable _check_ori_diffs()
        method to compute the diff based on derived class behavior.

        :param other_ori: the other ORI serializable of same class as this one
        :param tol_float: maximum tolerance for floating point value differences; values that differ by more than
            this value should be flagged as different, else accept as identical.
        :return: a dictionary that indicates the differences; key names identify the difference relative to self,
            description, the value is the actual difference. Example: if the return value is
            {'missing_children': ('abc', 'fgh')} then it is because other_ori is missing those children found in
            self.
        """
        assert type(self) == type(other_ori)
        diffs = {}
        self._check_ori_diffs(other_ori, diffs, tol_float)
        return diffs

    @override_required
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        """
        Set the state of this instance from ORI data structure. Every derived class must override this
        to set its state. This base class version must not be called.

        Note: The derived class is responsible for calling set_from_ori() on its children
        ORI object(s) if it has any. Typically it will get the subset of ori_data specific to each
        child using OriScenData.get_sub_ori().

        :param ori_data: OriScenData from which to configure self.
        :param context: The context of this operation.
        :param **kwargs: additional args passed from set_from_ori()

        :raises NotImplementedError if derived class does not override
        :raises KeyError: Raised if ori_data is missing an expected dictionary key value.
        """
        raise NotImplementedError

    @override_required
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        """
        Get the ORI representation of this instance. It is a dictionary whose keys and values adhere to the
        ORI JSON schema. Every derived class must override this to set its state, and must call incorporate
        the returns of get_from_ori() on its IOriSerializable children if it has any. This base class version
        must not be called.
        """
        raise NotImplementedError

    @override_optional
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        """
        Update the given dictionaries with a set of keys and values that represent a snapshot of the state local
        to this instance, i.e. not including ORI data *of* any ORI children (although data *about* the children
        is ok as it is technically local state data, such as number of children, whereas children names and links
        etc are non-local to self.

        :param snapshot: dictionary in which to put simple data (strings, numbers, tuples, short lists, etc)
        :param snapshot_slow: dictionary in which to snapshot complex data such as arrays

        The snapshot_slow is intended to contain data that is computationally intensive to compare. Therefore,
        the has_ori_changes only looks at slow-data comparisons when the fast data shows no changes.
        An example would be a large array (list of lists): the array should be put in snapshot_slow. Even
        better, an md5 of the array should be put there.

        Example:

            snapshot.update(key1=self.value1, key2=self.value2)
            snapshot_slow.update(key3=hash(complex_dict), ...)

        NOTE: This base class method MUST NOT be called by derived class overrides. If not overridden, it will
        amount to the instance being constant (unchanged, ever) from ORI perspective.
        """
        assert not self._ORI_HAS_SLOW_DATA

    @override_optional
    def _has_ori_changes_slow(self, baseline: JsonObj, last_get: JsonObj) -> bool:
        """
        If a derived class has ORI data that is slow to compare for change, it should do 3 things: 1) override
        self._ORI_HAS_SLOW_DATA to True (note: this hides the base class value); 2) override current
        method to compare baseline vs last_get. Both are the second argument of a call to _get_ori_snapshot_local(),
        taken at different times: once just after the IOriSerializable was saved (the "baseline"), and once
        when the last get_ori_def() was called. How this comparison occurs is implementation detail.

        Example: if the derived class has a large array of data, so iterating over every cell to compare for
        change would be slow, it could define _ORI_HAS_SLOW_DATA to be True, define _get_ori_snapshot_local()
        to compute an md5 digest of the array (which is very fast) and store it in the cmp_ori_slow dict arg.
        Finally, it would override _has_ori_changes_slow() to compare the value
        in _ori_snapshot_locals_last_get to that in the baseline.

        """
        raise NotImplementedError('Derived class that has _ORI_HAS_SLOW_DATA=True must override this')

    @override_optional
    def _has_ori_changes_children(self) -> bool:
        """
        If a derived class has children IOriSerializable objects, it should set _ORI_HAS_CHILDREN at
        class level and override this method to call has_ori_changes() on each of its children.
        """
        raise NotImplementedError('Derived class that has _ORI_HAS_CHILDREN=True must override this')

    @override_optional
    def _set_ori_snapshot_baseline_children(self, baseline_id: OriBaselineEnum):
        """
        This needs to be overridden only if the instance has IOriSerializable children: it should call each child's
        set_ori_snapshot_baseline(baseline_id). Param is same as for set_ori_snapshot_baseline().
        """
        raise NotImplementedError('Derived class that has _ORI_HAS_CHILDREN=True must override this')

    @override_optional
    def _ori_id(self) -> str:
        """
        Returns the string to use for identifying this object in error messages. Default is to use the string
        representation of the object.
        """
        return str(self)

    @override_optional
    def _check_ori_diffs(self, other_ori: Decl.IOriSerializable, diffs: Dict[str, Any], tol_float: float):
        """
        Override this put differences between other_ori and self into diffs. By default, no diffs are added.

        :param other_ori: the ORI serializable to compare to.
        :param diffs: the container in which to put diffs; each key is one diff according to derived method.
        :param tol_float: floating point value tolerance for "equality"
        """
        return

    def __log_ori_change(self, change_type=None):
        """
        Log a message about the type of ORI change found. Since many different classes can derive from
        IOriSerializable and don't necessarily have a human-friendly name, we try a couple things (will
        work on parts, part frames and links).
        """
        if change_type is None:
            msg = '"{}" has some ORI changes'.format(self._ori_id())
        else:
            msg = '"{}" has some ORI {} changes'.format(self._ori_id(), change_type)
        log.info(msg)


class OriScenarioKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame Scenario class.
    """

    SCHEMA_VERSION = "schema_version"
    SCHEMA_VERSION_ALIAS = "version"
    EVENT_QUEUE = "event_queue"
    SCENARIO_DEF = "scenario_def"
    SIM_CONFIG = "sim_config"
    IMAGE_DICT = "image_dictionary"
    RNG_STATE = "rng_state"


class OriScenarioDefKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame ScenarioDefinition
    class.
    """

    NAME = "name"
    ROOT_ACTOR = "root_actor_part"


class OriCommonPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame Parts.
    """

    TYPE = "type"
    PART_FRAME = "part_frame"
    CONTENT = "content"
    REF_KEY = "key"


class OriActorPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame ActorPart classes.
    """
    PART_TYPE_ACTOR = "actor"
    PROXY_POS = "proxy_position"
    GEOM_PATH = "geometry_path"
    IMAGE_ID = "image_id"
    ROTATION_2D = "rotation_2d"
    ROTATION_3D = "rotation_3d"
    CHILDREN = "children"
    IFX_PORTS_LEFT = "ifx_ports_left"
    IFX_PORTS_RIGHT = "ifx_ports_right"


class OriButtonPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame Button Part classes.
    """
    PART_TYPE_BUTTON = "button"
    BUTTON_ACTION = "button_action"
    BUTTON_TRIGGER_STYLE = "trigger_style"
    ROTATION_2D_PRESSED = "rotation_2d_pressed"
    ROTATION_2D_RELEASED = "rotation_2d_released"
    IMAGE_ID_PRESSED = "image_id_pressed"
    IMAGE_ID_RELEASED = "image_id_released"
    BUTTON_STATE = "state"


class OriClockPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame ClockPart classes.
    """
    PART_TYPE_CLOCK = "clock"
    DATE_TIME = "date_time"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"
    TICKS = "ticks"
    PERIOD_DAYS = "period_days"


class OriDataPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame DataPart classes.
    """
    PART_TYPE_DATA = "data"
    DICT = "dict"
    DISPLAY_ORDER = "display_order"
    PICKLED_KEYS = "pickled_keys"


class OriDateTimePartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame DateTimePart objects.
    """
    PART_TYPE_DATETIME = "datetime"
    DATE_TIME = "date_time"
    YEAR = "year"
    MONTH = "month"
    DAY = "day"
    HOUR = "hour"
    MINUTE = "minute"
    SECOND = "second"


class OriFunctionPartKeys:
    """
    String constants representing ori data object keys relevant to all Origame FunctionPart classes.
    """
    PART_TYPE_FUNCTION = "function"
    RUN_ROLES = "run_roles"
    ROLES_AND_PRIORITIZING = "roles_and_prioritizing"
    PARAMETERS = "parameters"
    SCRIPT = "script_lines"
    STARTUP = "startup"
    RESET = "reset"
    ROLES_AND_PRIORITIZING_ALIASES = "roles_and_ordering"


class OriPyScriptExecKeys:
    """
    String constants representing ori data object keys relevant to all Origame FunctionPart classes.
    """
    SCRIPT_IMPORTS = "script_imports"


class OriHubPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame HubPart classes.
    """
    PART_TYPE_HUB = "hub"


class OriImageDictionaryKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame ImageDictionary
    class.
    """
    PATH = "path"
    COUNT = "count"


class OriInfoPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame Info Part classes.
    """
    PART_TYPE_INFO = "info"
    TEXT = "text"


class OriLibraryPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame Library Part classes.
    """
    PART_TYPE_LIBRARY = "library"
    SCRIPT = "script_lines"
    PART_TYPE_LIBRARY_ALIASES = ["script"]


class OriMultiplierPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame Multiplier Part
    classes.
    """
    PART_TYPE_MULTIPLIER = "multiplier"


class OriNodePartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame NodePart classes.
    """
    PART_TYPE_NODE = "node"


class OriPlotPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame NodePart classes.
    """
    PART_TYPE_PLOT = "plot"
    SCRIPT = "script_lines"
    DPI = "dpi"


class OriPulsePartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame PulsePart classes.
    """
    PART_TYPE_PULSE = "pulse"
    PERIOD = "period"
    STATE = "state"
    PRIORITY = "priority"


class OriSheetPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame SheetPart class.
    """
    PART_TYPE_SHEET = "sheet"
    NUM_COLS = "num_columns"
    NUM_ROWS = "num_rows"
    COL_WIDTHS = "column_widths"
    INDEX_STYLE = "index_style"
    NAMED_COLS = "named_columns"
    DATA = "data"
    PICKLED_CELLS = "pickled_cells"


class OriSocketPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame NodePart classes.
    """
    PART_TYPE_SOCKET = "socket"
    NODE_REFS = "nodes"
    SIDE = "side_name"  # can be nil if not assigned to a side
    ORIENTATION = "orientation"  # defaults to vertical


class OriSqlPartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame Sql Part classes.
    """
    PART_TYPE_SQL = "sql"
    PARAMETERS = "parameters"
    SQL_SCRIPT = "sql_script"


class OriTablePartKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame TablePart class.
    """
    PART_TYPE_TABLE = "table"
    TABLE_NAME = "table_name"
    COLUMN_NAMES = "column_names"
    COLUMN_TYPES = "column_types"
    INDICES = "indices"
    SCHEMA = "schema"
    DATA = "data"


class OriTimePartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame TimePart objects.
    """
    PART_TYPE_TIME = "time"
    DAYS = "days"
    HOURS = "hours"
    MINUTES = "minutes"
    SECONDS = "seconds"


class OriVariablePartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame Variable Part classes.
    """
    PART_TYPE_VARIABLE = "variable"
    EDITABLE_STR = "editable_str"
    VALUE_OBJ = "value_obj"
    IS_PICKLED = "is_pickled"


class OriFilePartKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame File Part classes.
    """
    PART_TYPE_FILE = "file"
    PATH_STR = "filepath"
    RELATIVE_TO_SCEN_FOLDER = "relative_to_scen_folder"


class OriPartFrameKeys:
    """
    This class defines string constants representing ori data object keys relevant to all Origame PartsFrame objects.
    """

    NAME = "name"
    IFX_LEVEL = "ifx_level"
    VISIBLE = "visible"
    FRAME_STYLE = "frame_style"
    DETAIL_LEVEL = "detail_level"
    POSITION = "position"
    SIZE = "size"
    COMMENT = "comment"
    OUTGOING_LINKS = "outgoing_links"
    OUTGOING_LINKS_ALIAS = "outgoing_wires"


class OriPositionKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame Position class.
    """

    X = "x"
    Y = "y"


class OriSizeKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame Size class.
    """

    WIDTH = "width"
    HEIGHT = "height"
    SCALE_3D = "scale_3d"


class OriRotation3dKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame Rotation_3d class.
    """

    ROLL = "roll"
    PITCH = "pitch"
    YAW = "yaw"


class OriPartLinkKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame PartLink class.
    """

    NAME = "name"
    DECLUTTER = "declutter"
    TARGET_PATH = "target_path"
    TARGET_PATH_OLD = 'endpoint_part_path'
    BOLD = "bold"
    VISIBLE = "visible"
    WAYPOINTS = "waypoints"


class OriWaypointKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame LinkWaypoint class.
    """

    WAYPOINT_POS = "waypoint_pos"


class OriSimConfigKeys:
    """
    This class defines string constants representing ori data object keys relevant to the Origame SimConfig class.
    """

    REALTIME_SCALE = "realtime_scale"
    RANDOM_SEED = "random_seed"
    REALTIME_MODE = "realtime_mode"
    MASTER_CLK = "master_clock"
    SIM_TIME_DAYS = "sim_time_days"
    WALL_CLOCK_SEC = "wall_clock_sec"
    REPLIC_ID = "replication_id"
    VARIANT_ID = "variant_id"
    ANIM_WHILE_RUN_DYN = "runtime_animation"
    MAX_SIM_TIME_DAYS = "max_sim_time_days"
    MAX_WALL_CLOCK_SEC = "max_wall_clock_sec"


class OriSimEventKeys:
    """Keys for one event on sim events queue"""

    TIME_DAYS = "time_days"
    PRIORITY = "priority"
    PART_ID = "part_id"
    CALL_ARGS = "call_args"

