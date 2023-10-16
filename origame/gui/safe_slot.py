# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Everything related to safe-slotting.

Safe-slotting refers to PyQt slots that don't leak exceptions and that automatically gather
signal parameter types. However, this module also provides an "extended" safe slot to work around the Qt
bug described in backend_bridge.py: extended safe slots can only be connect to extended signals.
However, whereas the backend bridge can easily determine if a signal should be "regular" or "extended" so
that the developer need not worry about deciding this explicitely,
such determination is not possible with slots (because there are many data types that do not require
extended slots but would appear to, such as slots that will be connected to UI signals instead of
backend signals).

So two types of safe slotting functions are defined here:

- safe_slot: regular safe slot for any methods in the GUI that will be connected to signals from the GUI,
  or to signals from the backend that emit only base types like int, str, bool, etc.
- ext_safe_slot: extended safe slots for any GUI methods that will be connected to signals from the backend
  that will emit complex data (like lists, user defined classes, etc)

Both introspect the method that they wrap as safe-slot to extract slot argument types. They also support
argument types being given, since sometimes the argument types are base classes of those given in the signal,
and other times Qt complains at startup that some arg types are invalid. For this reason, arg types when
given must be a sequence of types and/or type names: the two types of safe slot verify that each arg type is
the same or a base class of the actual type inferred for the wrapped method, or for an arg type that is a
type name, that it matches the name of the inferred type name. Qt will verify
at connection time that the list is compatible with the signal.

Exceptions raised in safe-slotted methods are sent for output to an error handler. The error handler is by
default default_handle_safe_slot_exception(), but this can be changed via set_safe_slot_exception_handler().

Example:

    class Foo(QWidget):
        def meth(self, name: str, opt_arg: bool=None):
            pass
        def meth2(self, button: QPushButton):
            pass
        def meth3(self, widget: QWidget, widget: QWidget):
            pass

        safe_meth = safe_slot(meth)  # requires that connected signals are pyqtSignal(str, bool)
        safe_meth = safe_slot(meth, str)  # requires that connected signals are pyqtSignal(str)
        safe_meth = safe_slot(meth2, QAbstractButton)  # button.clicked.emit() has QAbstractButton as first arg type
        safe_meth = safe_slot(meth3, 'QWidget*', 'QWidget*')  # focusChanged.emit() takes two pointers to
                    # QWidget objects according to Qt, these strings are the only way to satisfy PyQt/Qt bridge

WARNING: It is forbidden to use this function as decorator on a method in application code, because this makes the
wrapped method unavailable for direct call: directly calling it will in fact call the safe-slot (wrapper), which
traps exceptions; whereas code that directly calls a method usually expects to be handling its exceptions.
The design should always be:

- define a regular method
- define the slot for the method via slot_method = safe_slot(method): the safe slot name must start with "slot_",
  and the rest must be the method name
- ensure calls to connect() use the slot_method, not the method
- ensure direct method calls use the method version, not the slot_method version
- if a derived class overrides the regular method, re-declare the slot_method in the derived class (otherwise
  there are some situations in which the base class method will get called when a signal is emitted,
  instead of the derived class method)

Adapted from:
http://stackoverflow.com/questions/18740884/preventing-pyqt-to-silence-exceptions-occurring-in-slots

Discussion re overridden safe-slotted methods:

Python wrappers in general work as expected even when method wrapped is overridden in a derived class:

- given a class A that defines method M, and a wrapper WM = wrapper(M), calling A().WM()
  will operate using A.M;
- given a class B that derives from A and overrides method M, but does *not* redefine WM = wrapper(M),
  calling B().WM() operates on B.M rather than A.M: this is usually the desired behavior.

However, if self.WM is used by an *A* method, A.M instead of B.M! This is not specific to safe_slot; every
wrapper operates this way (unless it specifically takes measures to get around this, but it is not easy).

For example, if A.__init__() connects a signal to self.safe_M, then signal.emit() will reach A.M instead
of reaching B.M, even though B.M overrides A.M. This can lead to very tricky bug!

The manual way of getting around this wrapper limitation is to repeat the safe slot declaration in the derived
class via slot_M = safe_slot(M). Since it is easy to forget to do this, and the consequence can be tricky bug
to figure out, safe_slot() has a function attribute CHECK_OVERRIDES_MISSING which, when True, will cause
the method wrapper to ensure that B redefines the slot of A. Unfortunately, it can only do this
when the slot is actually called, because in Python an unbound method does not have access to the class in
which it is defined. This means that even if the GUI is run with CHECK_OVERRIDES_MISSING=True, the action that
triggers the slot must be executed in order for the check to occur. This is still better than no check but
would occur at every signal emission, so it is turned on in the test suite only.

A base class would be a good way to automate this check, but the check would occur on every instantiation of
the class. A better way would be a metaclass that derives from the pyqtWrapperType metaclass. Either way,
There would be no need for CHECK_OVERRIDES_MISSING: the check could be done even in production code, whereas
currently the check is active only in test code. To ensure that safe_slot() is only called on a class that
uses such metaclass, have safe_slot init a flag to False on the wrapper it returns, and the metaclass set it
to True when class defined, and have the wrapper check the flag: if not True, it means the metaclass was not
used. This technique means the check could only happen if the slot is actually called.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import inspect
import logging
import traceback
import typing

# [2. third-party]
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import pyqtSlot

# [3. local]
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from .backend_bridge import create_ext_slot, check_sig_data_requires_ext, USE_EXT_SIGNAL_SLOT_SYS

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 7018 $"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'set_safe_slot_exception_handler',
    'SafeSlotExcHandlerCallable',
    'safe_slot',
    'ext_safe_slot',
]

log = logging.getLogger('system')

"""All handlers for safe slot exceptions must accept a slot and traceback message"""
SlotFunc = Callable[..., None]
SafeSlotExcHandlerCallable = Callable[[SlotFunc, str], None]
SafeSlot = Callable[..., None]


# -- Function definitions -----------------------------------------------------------------------

def default_handle_safe_slot_exception(slot: SlotFunc, tb_msg: str):
    """Default handler for safe_slot exceptions."""
    log.error("Uncaught Exception in slot {}", slot)
    log.error(traceback.format_exc())
    print("Uncaught Exception in slot {}".format(slot))
    print(tb_msg)


__handle_safe_slot_exception = default_handle_safe_slot_exception


def set_safe_slot_exception_handler(func: SafeSlotExcHandlerCallable):
    """
    Set the handler to use for safe-slot exceptions. This can be any callable object that takes a callable
    as first param (the slot that raised), and a string as second param. If None, reset to using the default
    handler (useful for unit tests).
    """
    global __handle_safe_slot_exception
    if func is None:
        __handle_safe_slot_exception = default_handle_safe_slot_exception
    else:
        __handle_safe_slot_exception = func


def safe_slot(func: SlotFunc, arg_types=None, __allow_decorator: bool = False) -> pyqtSignal:
    """
    :param func: the callable to wrap; if arg_types is None, func's parameters must be annotated
    :param arg_types: the argument types of the slot; if not specified, these are inferred from func's
        signature, which is usually adequate.
    :param __allow_decorator: used ONLY by the testing package's safe_slot_decorator, to enable decorating test
        methods as slots (purely for convenience)
    """
    # Oliver TODO build 3: implement a metaclass that is required in order for safe_slot to be used (note:
    # the metaclass can add a property to the wrapper; the wrapper checks for this the first time called; if not
    # there, exception, which indicates the developer has forgotten to set metaclass; the metaclass can also
    # search for wrapper instances and check if derived class has forgotten to redefine slot

    # define the wrapper that traps exceptions; don't use functools.wraps, not what we want;
    slot_wrapper = __get_safe_slot_wrapper(func, __allow_decorator)

    # finally ready to return pyqtSlotted wrapper:
    # WARNING: decorating the wrapper with pyqtSlot() does not work! Need to do it after defined.
    # pyqtSlot()(func) returns func when func is free func; if func is a method, it must be of a class derived
    # from QObject because pyqtSlot adds an entry to the QObject instance's metaobject()
    arg_types = __get_checked_arg_types(func, arg_types)
    try:
        pyqt_slot = pyqtSlot(*arg_types)(slot_wrapper)
    except TypeError: # TypeError: bytes or ASCII string expected not '_GenericAlias'
        for x in range(len(arg_types)):
            if typing.get_origin(arg_types[x]) != None:
                arg_types[x] = typing.get_origin(arg_types[x])

        pyqt_slot = pyqtSlot(*arg_types)(slot_wrapper)

    assert pyqt_slot is slot_wrapper  # wrapper gets spit out but pyqtSlot still got to do its job, as tests prove

    return pyqt_slot


def ext_safe_slot(func: SlotFunc, arg_types: List[type] = None, __allow_decorator: bool = False) -> pyqtSignal:
    """
    Same API as safe_slot(). However the return value is a slot that takes NO data: the data will be passed
    using the queued data channel.
    """
    slot = create_ext_slot(func)
    slot_wrapper = __get_safe_slot_wrapper(slot, __allow_decorator)

    arg_types = __get_checked_arg_types(func, arg_types)
    slot_wrapper.ext_arg_types = check_sig_data_requires_ext(arg_types)
    slot_wrapper.__wrapped__ = slot

    return pyqtSlot()(slot_wrapper)


if not USE_EXT_SIGNAL_SLOT_SYS:
    ext_safe_slot = safe_slot


# for performance, do not check by default:
safe_slot.CHECK_OVERRIDES_MISSING = False


def __check_safe_slot_derivation(func: SlotFunc, cls: type, slot_wrapper: SafeSlot, allow_decorator: bool):
    """
    Check overrides, to see if func that we have is not the most derived one; if that is true, raise.

    :param func: the method that was safe-slotted
    :param cls: the class that owns the method
    :param slot_wrapper: the safe-slot wrapper of the method
    :param allow_decorator: True if allowing use as @safe_slot (only used in tests)
    :raises TypeError: if cls omits to re-safe-slot func
    """
    # hasattr will be false on private slots, which can't be overridden so want to ignore them
    wrapped_meth = inspect.unwrap(slot_wrapper)
    meth_name = wrapped_meth.__name__
    if hasattr(cls, meth_name):

        # check no decorator used:
        if not allow_decorator:
            meth = getattr(cls, meth_name)
            if meth is slot_wrapper:
                msg = "BUG: method '{}' likely safe-slotted using decorator, this is not allowed"
                raise TypeError(msg.format(wrapped_meth.__qualname__))

        # check that this slot_wrapper is for the associated method that has not been overridden
        derived_meth = getattr(cls, meth_name)
        if derived_meth not in (wrapped_meth, slot_wrapper):
            # then func is a public or protected method that has been overridden in cls
            msg = "BUG: safe-slotted method '{}' is overridden in class '{}' but not re-safe-slotted"
            raise TypeError(msg.format(wrapped_meth.__qualname__, cls.__name__))


def __get_slot_arg_types(func: SlotFunc) -> List[type]:
    """Return tuple of parameter types based on func's annotations; raise ValueError if any arg not annotated"""

    # introspect to get arg types
    params = inspect.signature(func).parameters
    arg_types = [param.annotation for param in params.values()]
    # the arg types for pyqtSlot must not include func's first arg if it is 'self'
    if len(params) > 0 and list(params.values())[0].name == 'self':
        arg_types = arg_types[1:]
    if inspect.Parameter.empty in arg_types:
        raise ValueError('Slot parameters (except self, for methods) MUST BE annotated!')

    # in PyQt 5.7, pyqtSignal().connect() checks types; enums are always sent across thread boundary as ints
    for index, arg in enumerate(arg_types):
        from enum import EnumMeta
        if isinstance(arg, EnumMeta):
            arg_types[index] = int

    return arg_types


def __validate_arg_types(arg_types: List[type], func: Callable):
    """Validate that the given arg_types are in fact compatible with those infered from func introspection"""

    # verify that arg_types is subset of actual signature of func
    inferred_types = __get_slot_arg_types(func)
    if len(arg_types) > len(inferred_types):
        msg = "Too many types in annotation ({}), signature only has ({})".format(arg_types, inferred_types)
        raise RuntimeError(msg)

    # verify that each item in arg_types is either a string that matches the class name of each inferred type,
    # or a class that is superclass of inferred (inferred will always be the most derived type)
    mismatches = []
    for annotated, inferred in zip(arg_types, inferred_types):
        if isinstance(annotated, str):
            if not inferred.__name__.endswith(annotated.strip('*')):
                mismatches.append((annotated, inferred))
        else:
            try:
                if not issubclass(inferred, annotated):
                    mismatches.append((annotated, inferred))

            # If inferred is typing.*, a TypeError will be raised because first parameter of issubclass has to be a class
            except TypeError:
                try:
                    if not issubclass(typing.get_origin(inferred), annotated):
                        mismatches.append((annotated, inferred))

                # If inferred is typing.Unionlist, a TypeError will be raised again.
                except TypeError:
                    subclass = False
                    for i, x in enumerate(typing.get_args(inferred)):
                        if issubclass(typing.get_origin(x), annotated):
                            subclass = True

                    if not subclass:
                        mismatches.append((annotated, inferred))

    if mismatches:
        log.debug("WARNING: safe_slot' {} arg_types {} don't match arg types {}",
                  func.__qualname__, [m[0] for m in mismatches], [m[1] for m in mismatches])


def __get_checked_arg_types(func: Callable, arg_types: List[type]) -> List[type]:
    """
    If arg_types is None, returned the inferred arg types, else returns the given arg_types AFTER checking
    that they are compatible with the inferred arg types of func.
    """
    if arg_types is None:
        return __get_slot_arg_types(func)
    else:
        __validate_arg_types(arg_types, func)
        return arg_types


def __get_safe_slot_wrapper(func: SlotFunc, allow_decorator: bool) -> SafeSlot:
    """
    Get a safe slot wrapper for func. Normally func is a method, but it could also be another wrapper
    for a method (to any depth, as long as __wrapped__ is used.
    """

    def slot_wrapper(*args):
        try:
            if safe_slot.CHECK_OVERRIDES_MISSING:
                __check_safe_slot_derivation(func, args[0].__class__, slot_wrapper, allow_decorator)
            func(*args)

        except Exception as exc:
            ignore = isinstance(exc, RuntimeError) and str(exc).startswith('wrapped C/C++')
            if not ignore:
                __handle_safe_slot_exception(func, traceback.format_exc())

    # instead of functools.wraps, we need the following:
    suffix = '_safe_slot'
    slot_wrapper.__name__ = func.__name__ + suffix
    slot_wrapper.__qualname__ = func.__qualname__ + suffix
    slot_wrapper.__doc__ = "Safe-slot wrapper for {}. Method docs:\n{}".format(func.__name__, func.__doc__)
    slot_wrapper.__wrapped__ = func

    return slot_wrapper


# -- Class Definitions --------------------------------------------------------------------------

