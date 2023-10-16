# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provide raw signaling class that mimics PyQt's QObject class

Backend objects that do not interface with UI can derive from BackendEmitter and define BackendSignals.
Those that do should derive from BridgeEmitter and define BridgeSignal. Those objects will automatically
get the correct signaling baseclass as determined by the UI.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from .decorators import override_optional
from .typing import Any, Either, Optional, TypeVar, Callable, PathType, TextIO, BinaryIO
from .typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from .typing import AnnotationDeclarations

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    'BackendEmitter',
    'BackendSignal',
    'BridgeEmitter',
    'BridgeSignal',
    'safe_slot',
]

log = logging.getLogger('system')

TCallable = Callable[[Any], Any]  # any callable is accepted


class Decl(AnnotationDeclarations):
    BackendEmitter = 'BackendEmitter'


# -- Function definitions -----------------------------------------------------------------------

def safe_slot(fn: TCallable) -> TCallable:
    """
    Return a "safetied" wrapper of fn, suitable for connecting to signals. This is needed only to match
    the API of signaling systems used in GUI, since core and scenario use Qt signals and slots when imported
    in GUI variant.
    """
    return fn


# -- Class Definitions --------------------------------------------------------------------------

class _BackendSignalBound:
    """
    This should never be instantiated directly: bound signals can only be created by object that derive
    from BackendEmitter, which does this automatically. The methods are documented in the unbound version of
    this class.
    """

    def __init__(self, types: List[type]):
        self.__slots = []
        self.__types = types

    def connect(self, slot: Callable):
        if slot not in self.__slots:
            self.__slots.append(slot)

    def emit(self, *data: List[Any]):
        """Call each slot with the provided data"""
        for slot in self.__slots:
            slot(*data)

    def disconnect(self, slot: Callable = None):
        """Disconnect provided slot. If no slot provided, disconnect all slots from this signal."""
        if slot is None:
            self.__slots = []
        elif slot in self.__slots:
            self.__slots.remove(slot)

    def __call__(self, *args):
        """Support chaining of signals (using a signal as a slot for another signal)"""
        self.emit(*args)


class BackendSignal:
    """
    Represent a (unbound) Backend Signal object. This class is designed to be a drop-in replacement for
    pyqtSignal when the class that emits the signal must work with PyQt QObject.

    As with PyQt signals, define an *instance* of this class in a class that
    emits pure backend signals (i.e., signals that never connect to GUI objects). The emitting instance
    must derive from BackendEmitter.

    Note: The BackendEmitter creates a bound signal for the instance, from the class-wide
    unbound signal, whenever the signal is accessed on the instance. Example:

    class Foo(BackendEmitter):
        sig_something = BackendSignal() # unbound

        def update():
            self.sig_something.emit() # bound signal, created at runtime

    A "Foo.sig_something" refers to class-wide unbound signal object. But as soon as code uses "foo.sig_something",
    where foo is an instance of Foo, BackendEmitter intercepts this to create a BridgeSignalBound instance on foo.
    This is same strategy as used by PyQt for pyQtSignal's), with which BackendSignal must be compatible. Unbound
    signals do not have implementations for emit, connect or disconnect. However,
    in order to provide for code completion from IDE, stub methods are provided for these.
    """

    def __init__(self, *types: List[type]):
        """
        :param types: array of types accepted as payload when emitted
        """
        self.__types = types
        self.__bound_signals = {}

    def __get__(self, obj: Any, obj_type: type) -> _BackendSignalBound:
        """
        Intercept access to unbound signal on an object and create a signal bound to the object.
        Note: NO LONGER USED. A different technique is used that requires BackendEmitter initialization
        but is faster. It is kept here because it is too early to tell if the other technique
        has limitations.

        :param obj: the object derived from BackendEmitter
        :param obj_type: should be BackendEmitter
        :return: the new bound signal
        """
        if obj is None:
            # we are being called on a class, nothing to do:
            return self

        if obj in self.__bound_signals:
            # we have already been called on this instance, return the cached signal
            return self.__bound_signals[obj]

        # return new bound signal, after caching
        obj_signal = _BackendSignalBound(self.__types)
        self.__bound_signals[obj] = obj_signal
        return obj_signal

    def new_bound(self) -> _BackendSignalBound:
        return _BackendSignalBound(self.__types)

    def connect(self, slot: Callable):
        """Connect this signal to given slot, which an be any callable. The callable will be called
        with the arguments given to emit(). """
        raise NotImplementedError('BackendSignal.connect() not implemented by bound signal')

    def emit(self, *args: List[Any]):
        """Emit the signal, with given arguments. The arguments should have the same types as the sequence
        given to initializer of this class. """
        raise NotImplementedError('BackendSignal.emit() not implemented by bound signal')

    def disconnect(self, slot: Callable = None):
        """Disconnect this signal from given slot, or from all slots if none given. """
        raise NotImplementedError('BackendSignal.disconnect() not implemented by bound signal')


class BackendEmitter:
    """
    Base class for any signal-emitting object in the backend of Origame. Derive from this class and
    define signals as class-wide BackendSignal instances. Notes:
    - some methods on this class are provided strictly so BackendEmitter can be a drop-in replacement for
      QObject when application does not have a GUI.
    -
    """

    __signals = {}  # will hold a reference to each unbound signal defined on derived classes

    def __init__(self, emitter_parent: Decl.BackendEmitter = None, thread: Any = None, thread_is_main: bool = None):
        """
        Derived class must initialize base: this will find all class-wide BackendSignal instances and
        create instance-specific BackendSignalBound objects that can be used to connect to, emit, and disconnect
        from slots.
        """
        assert thread is None, "The caller is probably expecting to be using BridgeEmitter, not BackendEmitter"
        assert thread_is_main in (None, False, True)
        self._emitter_parent = emitter_parent

        if BackendEmitter.__signals:
            for (attr, value) in self.__signals.items():
                setattr(self, attr, value.new_bound())

        else:
            for (attr, value) in vars(self.__class__).items():
                if isinstance(value, BackendSignal):
                    BackendEmitter.__signals[attr] = value
                    setattr(self, attr, value.new_bound())

    def getParent(self) -> Decl.BackendEmitter:
        return self._emitter_parent

    def moveToThread(self, thread):
        raise NotImplementedError('BackendEmitter.moveToThread() override function has not been implemented.')

    def thread(self):
        raise NotImplementedError('BackendEmitter.thread() override function has not been implemented.')

    def deleteLater(self):
        raise NotImplementedError('BackendEmitter.deleteLater() override function has not been implemented.')

    def startTimer(self, event: Any) -> int:
        raise RuntimeError("This should never be called in console variant")

    @override_optional
    def timerEvent(self, event: Any):
        """This method will only be called if startTimer() was called from GUI. Never called in Console."""
        raise NotImplementedError('BackendEmitter.timerEvent() override function has not been implemented.')

    def killTimer(self, id: int):
        raise RuntimeError("This should never be called in console variant")


"""Class to use for signals that *could* interface with UI objects when a module is imported in the GUI variant. """
BridgeSignal = BackendSignal

"""Base class to use for classes that use BridgeSignal."""
BridgeEmitter = BackendEmitter


def setup_bridge_for_console():
    """Used only during testing: switch back to using backend classes for bridge."""
    global BridgeSignal, BridgeEmitter
    BridgeSignal = BackendSignal
    BridgeEmitter = BackendEmitter

    from .. import core
    core.BridgeSignal = BackendSignal
    core.BridgeEmitter = BackendEmitter
