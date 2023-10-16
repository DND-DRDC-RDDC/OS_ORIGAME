# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Bridge between user interface (UI) and backend (scenario).

This creates a bridge between the UI (main thread) and the scenario (backend thread), by monkey-patching
the backend to use this module's bridge_signal function and BridgeEmitter class.

Note that if it weren't for a Qt
bug found in build 1 of Origame, this module would have almost nothing to do: it could just replace
core.BridgeEmitter by QObject and core.BridgeSignal by pyqtSignal! Since the bug prevents the use of
pyqtSignal() to emit anything but base types like int and str (see _SIG_TYPES_ALLOWED), this module
defines an "extended" signal system via BridgeSignalExt and ancillary classes and functions, as well as
the ext_safe_slot() defined in the safe_slot module. These are designed so that the same signaling API can
be used regardless of types of objects emitted with the signal, but when the objects are not base types,
the actually way of transporting the objects to the UI (main thread) slots is different: they are put in a
queue, and a pyqtSignal() that doesn't emit any data is used to signal the UI that complex data (non-int,
str etc) is available on the queue. This means that the extended signal system shares the thread safety,
auto-disconnection on deletion, asynchronicity across threads, chronocity of emission and reception,
and lossless transport that are built into Qt's signal system. Another advantage is that there is only
one API to remember for signaling, and if the Qt bug ever gets fixed, there will be no code to change in
the UI source base except a little bit of code in this module to use pyqtSignal() instead of
BridgeSignalExt(). This "extended" signal system involves some overhead,
so this is an important goal.

Once the monkey-patching is in place, the process is as follows:

- Every backend class that defines signals based on BridgeSignal actually gets either a pyqtSignal() or a
  BridgeSignalExt(), thanks to bridgeEmitter() (note: every such class must derive from core.BridgeEmitter
  originally).
- Using this module's metaclass for BridgeEmitter, every class that derives from BridgeEmitter locates
  all class attributes that refer to an instance of BridgeSignalExt, and creates a corresponding
  hidden pyqtSignal (unbound).
- Every instance of BridgeEmitter creates one instance of _BridgeSignalExtBound, i.e. an extended signal,
  for every instance of BridgeSignalExt defined for the class; these created objects are specific to the
  BridgeEmitter instance.
- When an extended signal connects to an extended slot (see the safe_slot module), the connection is in
  fact established from the corresponding hidden pyqtSignal to the extended slot.
- When an extended signal emits data, the data is put on a queue, and the hidden pyqtSignal (that does not
  carry any "complex" data) is fired.
- When the extended slot gets notified, it retrieves the complex data from a queue, and calls the
  original slot (wrapped by the extended slot), thus completing the signaling.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from queue import Queue
from inspect import Parameter

# [2. third-party]
from PyQt5.QtCore import QObject, pyqtSignal, QThread, Qt, pyqtBoundSignal
from PyQt5.QtWidgets import QApplication
from sip import wrappertype as pyqtWrapperType

# [3. local]
from ..core.typing import AnnotationDeclarations
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'BridgeEmitter',
    'bridge_signal',
    'init_ext_sig_engine',
    'check_sig_data_requires_ext',
    'create_ext_slot',
]

log = logging.getLogger('system')

# Only the following types are allowed in signals from the backend:
_SIG_TYPES_ALLOWED = (bool, int, float, str, bytes, Parameter.empty)

QObjectMethod = Callable[..., None]
ExtSlot = Callable[[QObject], None]

# Set this to True so that the app uses extended signal-slot system (nothing else to do, just one setting):
USE_EXT_SIGNAL_SLOT_SYS = True


# -- Function definitions -----------------------------------------------------------------------

def init_ext_sig_engine(backend_thread: QThread):
    """
    Set the QThread in which backend is "living" (per Qt). This is used by the extended signals, which are
    only necessary to get around a nebulous PyQt bug that causes the app to crash (intermittently, a small
    percentage of time) when non-basic data types are used in signals across threads.
    """
    _ext_sig_data.set_thread(backend_thread)


def check_sig_data_requires_ext(sig_args: Tuple) -> List[type]:
    """
    Check if a tuple of types, assumed to be those of a signal or slot, would require extended bridge signal/slot
    to get around the PyQt bug that causes intermittent app crash when mutable objects are transfered via
    signal from backend to frontend.
    :param sig_args: tuple of types to check
    :return: a list of types that are not supported by native PyQt cross-thread pyqtSignal
        (so returns an emtpy list if pyqtSignal/pyqtSlot adequate).
    """

    def is_ext_type(type_obj):
        return type_obj not in _SIG_TYPES_ALLOWED

    return [type_obj for type_obj in sig_args if is_ext_type(type_obj)]


def create_ext_slot(func: QObjectMethod) -> ExtSlot:
    """Create an "extended" slot for the given function, assumed to be a method of a class derived from QObject."""

    def ext_slot_wrapper(self):
        args = _ext_sig_data.latest_data
        func(self, *args)

    suffix = '_ext'
    ext_slot_wrapper.__name__ = func.__name__ + suffix
    ext_slot_wrapper.__qualname__ = func.__qualname__ + suffix
    ext_slot_wrapper.__doc__ = "Ext-safe-slot wrapper for {}. Method docs:\n{}".format(func.__name__, func.__doc__)
    ext_slot_wrapper.__wrapped__ = func

    return ext_slot_wrapper


def get_type_name(type_obj: type) -> str:
    """
    Get the qualified name of a type given by type_obj. The type_obj typically comes from annotations so it
    can be not only a type, but an instance (such as a list of strings).
    """
    if hasattr(type_obj, '__qualname__'):
        # user-defined class:
        return type_obj.__qualname__
    elif hasattr(type_obj, '__name__'):
        # builtin class:
        return type_obj.__name__
    else:
        # instance of builtin-class:
        return type_obj.__class__.__name__


def get_type_names(ext_types):
    """Get the get_type_name(type_obj) for every type_obj in ext_types. Returns a list."""
    type_names = []
    for ext_type in ext_types:
        type_names.append(get_type_name(ext_type))
    return type_names


class Decl(AnnotationDeclarations):
    BridgeSignalExt = 'BridgeSignalExt'
    BridgeEmitter = 'BridgeEmitter'


def bridge_signal(*arg_types: List[type]) -> Either[pyqtSignal, Decl.BridgeSignalExt]:
    """
    Create the correct kind of signal: a regular pyqtSignal or an extended bridge signal.
    :param arg_types: argument types for signal payload
    """
    if USE_EXT_SIGNAL_SLOT_SYS and check_sig_data_requires_ext(arg_types):
        return BridgeSignalExt(arg_types)
    else:
        # normal pyqtSignal is ok:
        return pyqtSignal(arg_types)


# -- Class Definitions --------------------------------------------------------------------------

class ExtSigQueue(Queue, QObject):
    """
    A queue used to store objects for later retrieval by the front-end thread. It derives from QObject
    so it can emit an asynchronous signal from backend, sig_ext_data_added, indicating that backend data
    was added to the queue. When the front-end eventually gets this signal, the front-end can pop the data,
    to be used by the all the slots handling a BridgeSignalExt. The sig_ext_data_added allows for queue
    data to be discarded once it is no longer useful (ie. after a bridge signal has been handled by all
    connected slots).
    """
    sig_ext_data_added = pyqtSignal()

    def __init__(self, thread: QThread):
        """
        :param thread: the thread in which the Queue "lives" (per Qt)
        """
        Queue.__init__(self)
        QObject.__init__(self)
        if thread is not None:
            self.moveToThread(thread)

    def reset(self):
        """Empty the queue."""
        while not self.empty():
            self.get_nowait()


class ExtSigData:
    """
    Represents the portal in backend thread through which complex data can be sent to main thread. Instance
    lives in main thread, whereas queue that holds data is in backend thread. When the slot of instance
    is called, it means new extended signal data has been sent. It can be popped from the queue and made
    available to all slots created by create_ext_slot(func).
    """

    def __init__(self):
        super().__init__()
        # NOTE: this class is private to this module and all attributes have same visibility so we leave them public;
        # if this every changes they would be replaced by public properties for private attribute.
        self.queue = None
        self.latest_data = None

    def set_thread(self, backend_thread: QThread):
        # assert self.queue is None
        if self.queue is not None:
            self.queue.sig_ext_data_added.disconnect(self.__ext_data_added)
        self.queue = ExtSigQueue(backend_thread)
        self.queue.sig_ext_data_added.connect(self.__ext_data_added)

    def __ext_data_added(self):
        self.latest_data = self.queue.get_nowait()


_ext_sig_data = ExtSigData()


class _BridgeSignalExtBound:
    """
    An extended pyqtSignal bound to a specific instance of a BridgeEmitter: it can handle moving any type of
    object from the thread the BridgeEmitter was moved to, to the GUI thread. A bound signal
    can be connected, can emit, and can be disconnected. At connection, it expects the slot to be the
    return value of ext_safe_slot(some_method). The emit() puts data on the _ext_sig_data.queue and emits
    the raw asynchronous pyqtSignal() that is connected to _ext_sig_data. This notifies the front-end
    that new data is available on the storage queue, so the data can be removed and made available to the
    frontend slots connected to the bridge signal.

    In essence, the use of a queue allows to bypass Qt's
    transport of objects with signals; the signal data is stored, a simple signal is emitted, and when
    the front-end receives the signal, the data can be retrieved, ie the data was never transported.

    Note: instances of this class must have same API as instances of pyqtBoundSignal (at very least,
    connect, emit, disconnect methods).
    """

    def __init__(self, qt_sig: pyqtBoundSignal, unbound_ext_sig: Decl.BridgeSignalExt):
        """
        :param qt_signal: the pyqtSignal that this is extending
        """
        self.__qt_signal = qt_sig

        self.__cls_name = unbound_ext_sig.cls_name
        self.__user_sig_name = unbound_ext_sig.user_sig_name
        self.__ext_types = check_sig_data_requires_ext(unbound_ext_sig.sig_arg_types)
        self.__ext_typenames = get_type_names(self.__ext_types)

    def connect(self, safe_slot: ExtSlot, con_type: Qt.ConnectionType = None):
        """
        Connect this extended signal to given slot, which must be the return value of a call to ext_safe_slot(method).
        :param safe_slot: the callable to connect to
        :param con_type: type of Qt connection
        """
        # log.debug("WARNING: Connecting extended bridge signal {} to extended safe-slot {}",
        #           self.__user_sig_name, safe_slot.__qualname__)

        if not hasattr(safe_slot, 'ext_arg_types'):
            raise ValueError("Slot {} is not an extended safe slot; did you use ext_safe_slot(func)?"
                             .format(safe_slot.__qualname__))

        if safe_slot.ext_arg_types != self.__ext_types:
            msg = 'Slot-signal mismatch: slot {} has ext-args={}, signal {} in {} has {}'.format(
                safe_slot.__qualname__, safe_slot.ext_arg_types,
                self.__user_sig_name, self.__cls_name, self.__ext_typenames)
            raise ValueError(msg)

        # we don't want to risk having a different default connection type than Qt:
        if con_type is None:
            self.__qt_signal.connect(safe_slot)
        else:
            self.__qt_signal.connect(safe_slot, con_type)

    def emit(self, *args):
        """
        Emit the extended signal, with given arguments. The arguments should have the same types as the sequence
        given to initializer of this class. Note: this puts the complex data on the backend queue, signals the
        frontend global data tunnel that data is available, and emits a hidden pure-Qt signal. The latter
        is connected to any number of extended slots in the frontend, and these slots will retrieve the data
        emitted and call the wrapped slot (a method on a QObject).
        """
        _ext_sig_data.queue.put_nowait(args)
        _ext_sig_data.queue.sig_ext_data_added.emit()
        self.__qt_signal.emit()

    def disconnect(self, safe_slot: ExtSlot = None):
        """
        Disconnect this extended signal from given slot.
        :param slot: return value of ext_safe_slot(); if None, disconnect from all slots connected to signal.
        """
        if safe_slot is None:
            self.__qt_signal.disconnect()
        else:
            self.__qt_signal.disconnect(safe_slot)


class BridgeSignalExt:
    """
    This represents an unbound extended signal. Each instance of BridgeEmitter will convert an instance of
    BridgeSignalExt to BridgeSignalExtBound at init time.
    """

    def __init__(self, sig_arg_types: List[type]):
        """
        :param sig_arg_types: array of types accepted as payload when emitted
        """
        self.sig_arg_types = sig_arg_types
        self.cls_name = None
        self.user_sig_name = None
        self.qt_sig_name = None

    def set_sig_info(self, cls_name: str, user_sig_name: str, qt_sig_name: str):
        """
        :param user_sig_name: name of extended signal (replacment attribute name in emitter object)
        :param cls_name: name of BridgeEmitter-derived class
        :param qt_sig_name: name of hidden pyqtSignal
        """
        self.cls_name = cls_name
        self.user_sig_name = user_sig_name
        self.qt_sig_name = qt_sig_name

    def new_bound(self, qt_sig: pyqtBoundSignal) -> _BridgeSignalExtBound:
        """Create an extended signal bound to a BridgeEmitter instance"""
        return _BridgeSignalExtBound(qt_sig, self)

    def connect(self, slot: ExtSlot):
        # Provided so IDE can support code completion on extended signals (which are not bound when seen by IDE)
        raise NotImplementedError

    def emit(self, *args):
        # Provided so IDE can support code completion on extended signals (which are not bound when seen by IDE)
        raise NotImplementedError

    def disconnect(self, slot: ExtSlot = None):
        # Provided so IDE can support code completion on extended signals (which are not bound when seen by IDE)
        raise NotImplementedError


class MetaBridgeEmitterExt(pyqtWrapperType):
    """
    This meta class for BridgeEmitter creates an unbound ghost signal for every unbound extended signal.
    When a bridge emitter is later instantiated, signals bound to that instance will be created so that
    complex data can be safely transmitted asynchronously across the Qt thread boundary. This shim is
    only needed because of a weird Qt bug that causes intermittent crashes when complex objects are
    transmitted via regular pyqtSignal.
    For this reason, all signals that are based on pyqtSignal must only have non-mutable types as
    parameters such as int, str, etc. Enum, list, dict, etc are not in this category. Tuple is non-mutable
    but because it is a sequence, it is not allowed either. When it is necessary to carry mutable or
    sequence types across thread boundary from backend to front-end, BridgeSignalExt must be used on the
    emitter side, and ext_safe_slot_ext on the receiving side.
    """

    def __new__(cls, name, bases, namespace, **kwds):
        # only need to take action for classes *derived* from BridgeEmitter:
        if name == 'BridgeEmitter':
            return type.__new__(cls, name, bases, dict(namespace))

        # find unbound extended signals:
        ext_signals_unbound = {attr: obj for attr, obj in namespace.items() if isinstance(obj, BridgeSignalExt)}
        ext_map_name = '_ext_signals_unbound'
        assert hasattr(BridgeEmitter, ext_map_name)
        namespace[ext_map_name] = ext_signals_unbound

        # for each one found, create a simple pyqtSignal that will do the actual asynchronous communication
        # to frontend thread, but without the complex data; the latter will be transfered via a separate
        # data channel (see create_ext_slot).
        cls_name = '{__module__}.{__qualname__}'.format(**namespace)
        for (user_sig_name, ext_sig_unbound) in ext_signals_unbound.items():
            log.debug("WARNING: Extending signal {} in class {}", user_sig_name, cls_name)

            # create the unbound pyqtSignal that is safe to use across threads
            qt_sig_name = '_xbridge_' + user_sig_name
            qt_sig = pyqtSignal()
            namespace[qt_sig_name] = qt_sig

            ext_sig_unbound.set_sig_info(cls_name, user_sig_name, qt_sig_name)

        return type.__new__(cls, name, bases, dict(namespace))


class BridgeEmitter(QObject, metaclass=MetaBridgeEmitterExt):
    """
    Any Origame backend component that emits signals in both the Console variant and GUI variant, and may be
    connected (via signals) to GUI components when in GUI variant, must define a Signals object that derives
    from this class. When imported in the GUI variant, this makes the Signals instance derive from PyQt's
    QObject; when in Console, it is independent of PyQt. This class also automates some thread-related
    setup of instances.
    """

    # It is necessary for GUI to have ability to instantiate bridge emitters in main thread, but have them
    # "owned" by the backend thread; when so,
    # the GUI main script should set this class data member to True. It is used in the constructor to
    # verify that the bridge object is being instantiated in the correct thread.
    DEFAULT_THREAD_MAIN = False

    _ext_signals_unbound = None

    def __init__(self, bridge_parent: Decl.BridgeEmitter = None, thread: QThread = None, thread_is_main: bool = None):
        """
        A BridgeEmitter instance can be created in the main thread and given a non-main QThread object
        representing the thread in which to "operate" (in the PyQt sense of the term). In this case, it
        will automatically move itself to that thread. This is the case of "top level" objects created
        directly or indirectly by main thread: scenario manager, debugger, and batch sim manager. Once
        moved to the other thread, any new bridge emitters they create will automatically be in the other
        thread so they do not need to be moved to the thread, and the thread argument should be None.

        :param bridge_parent: the parent of this bridge emitter (usually None)
        :param thread: which thread to move to; leave None if created in correct thread
        :param thread_is_main: only used if thread None, this can be set to True, False or None: if True,
            ensure called from main thread; if False, ensure called from non-main thread; if None, set
            thread_is_main to DEFAULT_THREAD_MAIN (which must be True or False).

        Examples:

        class Signals(BridgeEmitter):
            sig_some_signal = BridgeSignal()

        signals = Signals()                     # creator must be main or non-main thread, based on DEFAULT_THREAD_MAIN
        signals = Signals(thread=backend_thread)# created in main thread, move to given QThread instance
        signals = Signals(thread_is_main=True)  # must be created in main thread, stays in main thread
        signals = Signals(thread_is_main=False) # must be created in non-main thread, stays in that thread
        """

        super().__init__(bridge_parent)
        assert self.thread() is not None

        # each BridgeEmitter instance needs its own instances of bound extended signals
        for user_sig_name, ext_sig_obj in self._ext_signals_unbound.items():
            qt_sig = getattr(self, ext_sig_obj.qt_sig_name)
            setattr(self, user_sig_name, ext_sig_obj.new_bound(qt_sig))

        # automatically move to thread if thread specified:
        if thread is None:
            if thread_is_main is None:
                thread_is_main = BridgeEmitter.DEFAULT_THREAD_MAIN
            if thread_is_main:
                assert QApplication.instance().thread() == self.thread()
            else:
                assert QApplication.instance().thread() != self.thread()

        else:
            self.moveToThread(thread)
            assert QApplication.instance().thread() != self.thread()
            self.thread().finished.connect(self.deleteLater)
