# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Various core utility functions and classes

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import re
import keyword
from datetime import timedelta
from time import time
from cProfile import Profile
from enum import Enum
from pathlib import Path
import sched

# [2. third-party]
from dateutil.relativedelta import relativedelta

# [3. local]
from .typing import Any, Either, Optional, Callable, TypeVar, PathType, TextIO, BinaryIO
from .typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'validate_python_name',
    'get_valid_python_name',
    'InvalidPythonNameError',
    'get_enum_val_name',
    'UniqueIdGenerator',
    'BlockProfiler',
    'ori_profile',
    'ClockTimer',
    'plural_if',
    'bool_to_not',
    'GuardFlag',
    'rel_to_timedelta',
    'timedelta_to_rel',
]

log = logging.getLogger('system')

TAny = TypeVar('TAny')
TCallable = Callable[[Any], Any]  # any callable is accepted


# -- Function definitions -----------------------------------------------------------------------

def get_verified_eval(value_in_str: str):
    """
    Checks if a string can pass eval(). If it can, the eval() value will be returned; otherwise a SyntaxError will be
    thrown.
    :param value_in_str: The string to be checked
    :return: The return value of the eval(value_in_str)
    :raises: whatever exception is raised by eval(); an additional field 'text' is created, holding value_in_str
    """
    try:
        obj_verified = eval(value_in_str)
    except Exception as e:
        e.text = value_in_str
        raise

    return obj_verified


def get_verified_repr(val: Any) -> str:
    """
    Getting a verified repr from val means eval(repr(val)) == val is true.
    :param val: The object from which the repr is derived
    :return: The repr on the val
    :raise: Exception if repr() or eval() fails.
    :raise: RuntimeError if eval(repr(val)) == val is false.
    """
    cell_repr = repr(val)
    cell_eval = eval(cell_repr)

    if val != cell_eval:
        raise RuntimeError("The string representation of the given value cannot pass eval()")

    return cell_repr


def validate_python_name(name: str):
    """
    This function validates whether or not the input name is a valid Python name. If the name is valid, the function
    returns; however, if the input name is invalid, an InvalidPythonNameError is raised describing the format error
    contains a proposal for a corrected version of the name.

    Invalid names are names that: (Note: Corresponding auto-corrections applied are shown in brackets.)
        - Are reserved keywords (prepend 'Obj_' to name)
        - Start with a number (prepend underscore '_' to name)
        - Contain any non-alpha-numeric character except the underscore (replace invalid character with underscore '_')

    :param name: The name to be validated.
    :raises: InvalidPythonNameError - An exception containing a description of the error and a proposed corrected
        name.
    """
    # No name case
    if name is None:
        raise InvalidPythonNameError(msg='Name cannot be None', invalid_name=name, proposed_name='unnamed')

    # This case covers a valid name
    regex_py_lex = '[_A-Za-z][_a-zA-Z0-9]*'
    if re.fullmatch(regex_py_lex, name) and not keyword.iskeyword(name):
        return

    # For invalid names, the following apply

    # Invalid case: keyword used (prepend 'Obj_')
    if keyword.iskeyword(name):
        new_name = 'Obj_{}'.format(name)
        raise InvalidPythonNameError(
            msg="Name cannot be a Python keyword.", invalid_name=name, proposed_name=new_name)

    # Invalid case: invalid characters used
    # - numeric character is the first character (prepend '_')
    # - non-alpha-numeric character(s) used (replace with '_')

    bad_format = False
    orig_name = name
    regex_num_first = '[0-9]'
    if re.fullmatch(regex_num_first, name[0]):
        name = '_{}'.format(name)
        bad_format = True

    regex_valid_char = '[_a-zA-Z0-9]'
    name = list(name)  # str -> list[char]: allows assignment at index
    for index, char in enumerate(name):
        if not re.fullmatch(regex_valid_char, char):
            name[index] = '_'
            bad_format = True
    name = "".join(name)  # list -> str

    if bad_format:
        raise InvalidPythonNameError(
            msg="Name can only contain letters and underscores and must not commence with a numeral.",
            invalid_name=orig_name, proposed_name=name)


def get_valid_python_name(name: str) -> str:
    """
    This function validates whether the input name is a valid Python name. If the name is valid it is returned as-is.
    If the input name is not valid, a corrected version of the name is returned.

    Invalid names are names that: (Note: Corresponding auto-corrections applied are shown in brackets.)
        - Are reserved keywords (prepend 'Obj_' to name)
        - Start with a number (prepend underscore '_' to name)
        - Contain any non-alpha-numeric character except the underscore (replace invalid character with underscore '_')

    :param name: the name to be verified and augmented if required.
    :returns: The original ìnput 'name', if valid, or a corrected version of the input 'name' if invalid.
    """
    invalid = True
    while invalid:
        try:
            validate_python_name(name)
            invalid = False
        except InvalidPythonNameError as e:
            log.warning('Invalid part or link name: {}. {} Changing to: {}.', name, str(e), e.proposed_name)
            name = e.proposed_name
    return name


# -- Class Definitions --------------------------------------------------------------------------


class InvalidPythonNameError(ValueError):
    """
    This class provides a class-specific implementation of the built-in ValueError exception.
    It is raised when a string is determined to be an invalid Python name.
    """

    def __init__(self, msg: str, invalid_name: str = None, proposed_name: str = None, scenario_location: str = None):
        """
        :param msg: A message describing why the Python name is invalid.
        :param invalid_name: The name that is the subject of the Error.
        :param proposed_name: A proposed correction for the invalid name.
        :param scenario_location: The scenario hierarchy location of the invalid name.
        """
        super(InvalidPythonNameError, self).__init__(msg)
        self.invalid_name = invalid_name
        self.proposed_name = proposed_name
        self.scenario_location = scenario_location


def get_enum_val_name(enum_obj: Enum) -> str:
    """Get the name for an enumeration value. MyEnum.some_val returns "some_val"."""
    return enum_obj.name


def rel_to_timedelta(delta: relativedelta) -> timedelta:
    """Convert a dateutil.relativedelta to a datetime.timedelta"""
    return timedelta(days=delta.days, hours=delta.hours, minutes=delta.minutes,
                     seconds=delta.seconds, microseconds=delta.microseconds)


def timedelta_to_rel(delta: timedelta) -> relativedelta:
    """Convert a datetime.timedelta to a dateutil.relativedelta"""
    # the normalized() distributes the days/seconds/micro so hours and minutes attributes have integer values
    return relativedelta(days=delta.days, seconds=delta.seconds, microseconds=delta.microseconds).normalized()


class UniqueIdGenerator:
    """
    Generates a unique id every time the static method get_new_id() is called.
    This class is *not* multi-thread safe (there is a possibility that two threads
    would get the same id). The start ID can be configured.
    """

    __registry = []

    def __init__(self):
        self.__next_id = 0
        self.__registry.append(self)

    def __del__(self):
        self.__registry.remove(self)

    def get_new_id(self) -> int:
        """
        This function returns an application-unique ID each time it is called.
        """
        part_id = self.__next_id
        self.__next_id += 1
        return part_id

    @classmethod
    def reset(cls):
        """Reset the ID counter. This should only be used in unit tests."""
        for gen in cls.__registry:
            gen.__next_id = 0


def select_object(objects: List[TAny], attr_path: str, val: TAny) -> TAny:
    """
    Find the object that has the given attribute equal to the given value.

    :param objects: set of objects to look through
    :param attr_path: the attribute path, in dot notation
    :param val: the value to match
    :return: the object, or None if none found

    Example:

        >>> objects = [part1, part2, part3, part4]
        >>> obj = select_object(objects, "part_frame.name", "foo")
        >>> assert obj.part_frame.name == "foo"  # passes if there is such an object
        >>> obj = select_object(objects, "part_frame.size", 123)
        >>> assert obj.part_frame.width == 123  # passes if there is such an object
    """
    path = attr_path.split('.')
    for obj in objects:
        orig_obj = obj
        for p in path:
            obj = getattr(obj, p)
        if obj == val:
            return orig_obj
    return None


class BlockProfiler(Profile):
    """
    This can be used to profile various portions of Origame. Use like this:

    with BlockProfiler(scenario_path):
        ...stuff to profile...

    If scenario_path is c:\\folder\path.ori, then when the "with" clauses is done, the profiling data is
    automatically saved to c:\\folder\path.pstats and can be opened with any pstats-compatible tool
    (PyCharm, gprof2d, etc). If out_info data was given, like this:

    with BlockProfiler(scenario_path, v=1, r=2):
        ...stuff to profile...

    then the output file will be c:\\folder\path_v_1_r_2.pstats so it is easy to use the profile in multiple
    places in one run (out_data can be an identifier for section of code).
    """

    def __init__(self, scen_path: PathType, **out_info):
        """If out_info is not empty, appends their string rep to the stats file path name"""
        Profile.__init__(self)
        scen_path = Path(scen_path)
        if out_info:
            extra = ['{}_{}'.format(name[0], val) for name, val in out_info.items()]
            extra_str = '_'.join(extra)
            scen_path = scen_path.with_name(scen_path.stem + '_' + extra_str)
        self.out_path = scen_path.with_suffix('.pstats')

    def __enter__(self):
        log.warning("Profiling starting")
        self.enable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disable()
        self.dump_stats(str(self.out_path))
        log.warning("Profiling data saved to {}", self.out_path)
        return False


def ori_profile(func: TCallable, scen_path: PathType, **out_info) -> TCallable:
    """
    Decorator that can be used to cause every call to given function to get profiled to a .pstats file.

    :param func: the function to be profiled when called
    :param scen_path: the scenario file path
    :param out_info: additional optional info to insert in output file path
    :return: the callable that calls func such that it can be profiled

    Note: scen_path and out_info are the same as for BlockProfiler (see class docs and its __init__ docs).
    """
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with BlockProfiler(scen_path, **out_info):
            result = func(*args, **kwargs)
        return result

    return wrapper


class ClockTimer:
    """
    Track wall-clock time. The time stops increasing after pause(), resumes increasing
    after resume(). The get_total_time_sec() (and associated property) only update on read.
    """

    def __init__(self, pause: bool = False):
        """
        Start a timer. By default, start advancing time immediately
        :param pause: if True, do not start timing immediately, will start at next resume()
        """
        self._start_time_sec = time()
        self._total_time_sec = 0
        self._paused = pause

    def reset(self, seconds: float = 0.0, pause: bool = False):
        """
        Reset the timer.
        :param seconds: reset the total_time_sec to this value and, if pause=True, pause (don't track time until
            next resume()); if pause=False, immediately resume (next call to total_time_sec is almost certain to be
            larger than seconds)
        :param pause: if true, pause the timer, otherwise resume (starts timing) immediately
        """
        self._start_time_sec = time()
        self._total_time_sec = seconds
        self._paused = pause

    def pause(self):
        """Pause timer. The total_time_sec() will return constant value until resume() called again."""
        if not self._paused:
            self._total_time_sec += (time() - self._start_time_sec)
            self._paused = True

    def resume(self):
        """Resume the timer. The time starts counting time again."""
        if self._paused:
            self._start_time_sec = time()
            self._paused = False

    def get_is_paused(self) -> bool:
        return self._paused

    def get_total_time_sec(self) -> float:
        """Get time in seconds since __init__(), not including pause periods."""
        if self._paused:
            return self._total_time_sec

        new_time = time()
        self._total_time_sec += (new_time - self._start_time_sec)
        self._start_time_sec = new_time
        return self._total_time_sec

    total_time_sec = property(get_total_time_sec)
    is_paused = property(get_is_paused)


def plural_if(condition: Either[List[Any], bool], plural: str = 's', singular: str = '') -> str:
    """
    Choose between plural and singular based on a condition.

    :param condition: if a boolean, True indicates pluralize, False do not. If container, pluralize if more than 1 item
    :param plural: the letter to return if plural
    :param singular: when singular, what to return
    :return: plural if condition is True else return singular

    Example:
        "Found {} item{}".format(num_items, plural_if(num_items > 1))
        "Found {} item{}".format(len(found), plural_if(found)))
        "Found {} {}".format(len(found), plural_if(found, 'geese', 'goose')))
    """
    try:
        num_nodes = len(condition)
        condition = (num_nodes > 1)
    except TypeError:
        # not a container, use condition as boolean
        condition = bool(condition)

    return plural if condition else singular


def bool_to_not(flag: bool) -> str:
    """
    Returns empty string if flag is False, or "not " otherwise. Example:

        log.info("This flag is {}true", bool_to_not(your_flag))

    will log "This flag is true" if your_flag is True, but "This flag is not true" otherwise. Note the
    missing space between the placeholder and what will follow the "not"
    """
    return "" if flag else "not "


class FileLock:
    """
    Context manager to lock a scenario input or output file to synchronize access by simultaneously
    executing replications. The file name of the lock is the file to be locked suffixed with "_lock_indicator".
    """

    def __init__(self, file_name: str, max_attempts: int = 50, attempt_interval: int = 3):
        """
        :param file_name: The name of the file that is to be locked.
        :param max_attempts: The max number of the attempts of acquiring a lock.
        :param attempt_interval: The interval between two consecutive attempts. In seconds.
        """
        self.__path = Path(file_name + "_lock_indicator")
        self.__max_attempts = max_attempts
        self.__attempt_interval = attempt_interval
        self.__file = None

    def __enter__(self):
        """
        Locks the file given in the constructor.
        """
        con_scheduler = sched.scheduler()
        locking_failed = True

        def attempt_to_lock(num_attempt=0):
            nonlocal locking_failed
            if num_attempt < self.__max_attempts:
                try:
                    self.__file = self.__path.open('x+')
                    locking_failed = False
                except:
                    log.debug("Unable to lock: path={}, num_attempt={}", str(self.__path), num_attempt)
                    nxt = num_attempt + 1
                    con_scheduler.enter(self.__attempt_interval, 1, attempt_to_lock, argument=(nxt,))

        con_scheduler.enter(0, 1, attempt_to_lock)
        con_scheduler.run()

        if locking_failed:
            err_msg = "Unable to lock the file after {} attempt{}. The file: {}".format(
                self.__max_attempts, plural_if(self.__max_attempts > 1), self.__path)
            log.error(err_msg)
            raise TimeoutError(err_msg)

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Unlocks the file given in the constructor.
        :param exc_type: (unused)
        :param exc_val: (unused)
        :param exc_tb: (unused)
        """
        try:
            self.__file.close()
            self.__path.unlink()
        except:
            log.debug("Unable to delete: path={}", str(self.__path))

    def __del__(self):
        try:
            self.__file.close()
            self.__path.unlink()
        except:
            log.debug("Unable to delete: path={}", str(self.__path))


class IJsonable:
    """
    Classes that represent data structures that must be output to a JSON-compatible format can derive
    from this class. The class provides two methods to generate a JSON-compatible representation of self,
    and the other to set self attributes from a JSON-compatible representation of self.
    """

    def __init__(self, _unknown: Dict[str, Any], *prop_names: List[str]):
        """
        :param prop_names: optional, list of property names to package into and out of JSON-compatible representations
        :param _unknown: dict of parameters not recognized (create via **unknown)
        """
        if _unknown:
            msg = "These JSON fields are not recognized (likely an obsolete schema): {}"
            fields = ', '.join(_unknown)
            log.error(msg, fields)
            raise ValueError(msg.format(fields))

        self.__json_prop_names = prop_names

    def to_json(self) -> Dict[str, Any]:
        """
        Return a JSON-compatible map of public attributes of self. Note: properties are not
        considered public attributes. To include public properties, define their names in the initializer.
        """
        return {key: getattr(self, key) for key in self.__get_valid_keys_derived()}

    def from_json(self, data: Dict[str, Any]):
        """
        Set the state of the derived class from the JSON data provided. Each key MUST be the name of an attribute
        that already exists in self, either as a pure data member or as a property. A ValueError will be raised
        otherwise.
        """
        valid_keys = self.__get_valid_keys_derived()
        for key in data:
            if key in valid_keys:
                setattr(self, key, data[key])
            else:
                raise ValueError('Invalid key "{}" in JSON data', key)

    def __str__(self):
        def attr_val(key):
            return key.capitalize().replace('_', ' '), getattr(self, key)

        return '\n'.join('{}: {}'.format(*attr_val(key)) for key in sorted(self.__get_valid_keys_derived()))

    def __get_valid_keys_derived(self) -> List[str]:
        valid_keys = {attr_name for attr_name in vars(self) if not attr_name.startswith('_')}
        valid_keys.update(self.__json_prop_names)
        return valid_keys


class GuardFlag:
    """
    Facilitates the use of "guard flags" by making them exception-safe and automatically restored, even
    across nested calls. Guard flags are flags that are set before calling a method, so that some nested
    action will not occur; the flag must be set back to default when method done. Without this class,

    - it is a pain to ensure the flag is reset despite exception being raised by method;
    - it is a pain to determine what value the flag should be reset to (normally, the value on entry)

    Example:
        class Foo:
            def __init__(self):
                self.__nested = GuardFlag(False)
            def doABC(self):
                # called when user clicks button, or by doAC
                ...do A...
                self.__doC()
                ...do B...
            def doAC(self):
                # called when user selects text
                with self.__nested(True):
                    self.doABC()
            def __doC(self):
                if not self.__nested:
                    do C
    """

    def __init__(self, init: bool):
        self.__flag_value = init
        self.__flag_on_enter = []

    def set(self, value: bool):
        self.__flag_value = value

    def __call__(self, on_entry: bool):
        self.__on_entry_value = on_entry
        return self

    def __bool__(self):
        return self.__flag_value

    def __enter__(self):
        self.__flag_on_enter.append(self.__flag_value)
        self.__flag_value = self.__on_entry_value
        return self.__flag_value

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__flag_value = self.__flag_on_enter.pop()
        return False
