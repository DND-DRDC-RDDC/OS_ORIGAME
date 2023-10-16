# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Docstring summary line is a short one-line description of the module.

PEP 8 defers to PEP 257 for docstrings: Multi-line docstrings consist of a summary line just like a
one-line docstring, followed by a blank line, followed by a more elaborate description. The
docstring for a module should generally list the classes, exceptions and functions (and any other
objects) that are exported by the module, with a one-line summary of each.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import Enum
from inspect import signature

# [2. third-party]

# [3. local]
from ...core import override_required, override_optional, BridgeSignal, BridgeEmitter
from ...core import AttributeAggregator
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..alerts import ScenAlertInfo, ScenAlertLevelEnum
from ..defn_parts import BasePart

from .scripting_utils import get_signature_from_str, get_func_proxy_from_str
from .py_script_exec import PyScriptCompileError

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'IExecutablePart'
    'QueuePosEnum',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    IExecutablePart = 'IExecutablePart'
    EventInfo = 'EventInfo'


class ErrorCatEnum(Enum):
    call = range(1)


class IExecutablePart(metaclass=AttributeAggregator):
    """
    All executable scenario parts must derive from this class. The derived class must define the following signals:
    - sig_queue_counters_changed(bool, int, int): event counters for this part have changed, they are "next on queue",
        count of concurrent with next time bin, count after next time bin
    """

    class ExecSignals(BridgeEmitter):
        sig_queue_counters_changed = BridgeSignal(bool, int, int)  # concurrent with next, after next
        sig_exec_done = BridgeSignal()
        sig_params_changed = BridgeSignal(str)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        self.exec_signals = IExecutablePart.ExecSignals()

        self._count_queued = 0  # how many times on event queue
        self._queue_asap = 0  # number of times on ASAP queue
        self._queue_timed = 0  # number of times on timed queue
        self._queue_next = False  # is it next on the queue
        self._queue_concur_next = 0  # number of time in the same bin as next iexec on queue
        self._param_str = ""
        self._signature = self.get_signature()
        self._param_validator = None

    @override_required
    def get_name(self) -> str:
        """Get the name of this part."""
        raise NotImplementedError

    @override_optional
    def get_parameters(self) -> str:
        """
        Get the part parameters. Those parts that must traverse the outgoing links can override this function.
        """
        return self._param_str

    def set_parameters(self, value: str):
        """
        Set the Function parameters.
        :param value: The new parameters.
        """
        if self._param_str != value:
            self._param_str = value or ''  # if None, set to ''
            self._signature = self.get_signature()
            self._param_validator = get_func_proxy_from_str(value)
            self._on_parameters_changed()
            if self._anim_mode_shared:
                self.exec_signals.sig_params_changed.emit(self._param_str)

    def get_signature(self) -> signature:
        """Get the signature object for the function defined by this function part's parameters"""
        try:
            return get_signature_from_str(self._param_str)
        except SyntaxError as exc:
            self.__set_last_exec_error_info(PyScriptCompileError(exc, self))
            raise

    parameters = property(get_parameters, set_parameters)
    signature = property(get_signature)
    name = property(get_name)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (parameters,)
    META_AUTO_SEARCHING_API_EXTEND = (parameters,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        parameters, get_parameters, set_parameters,
    )

    # --- execution methods ----------------------------

    def call(self, *args, _debug_mode: bool = False, **kwargs):
        """
        Execute this part as a function. This should be called directly to execute the behavior of the object.
        Some scenario parts behave differently when called normally vs as signal. The return value and exceptions
        raised are those of _exec and should be documented in the derived class itself.

        Note: Ultimately, this calls the overridden _exec() method with the same arguments, plus _as_signal=False.

        :param args: the required (positional) arguments to give to _exec()
        :param kwargs: the optional (named) arguments to give to _exec()
        :param _debug_mode: an "internal" flag that is set by the caller to indicate debug mode (True
            if want to stop at next breakpoint)
        """
        return self.__call(*args, _debug_mode=_debug_mode, **kwargs)

    def signal(self, *args, _debug_mode: bool = False, **kwargs):
        """
        Execute this part as a signal. This is called by the simulation controller after an event
        for this instance is removed from the simulation event queue. Some scenario parts behave differently
        when called normally vs as signal. Same param docs as call(). No return value. Exceptions are those
        of _exec and should be documented in derived class.
        """
        self.__call(*args, _debug_mode=_debug_mode, _as_signal=True, **kwargs)

    # --- queue properties ----------------------------

    def get_queued(self) -> bool:
        return self._count_queued > 0

    def get_queued_next(self) -> bool:
        """Return true if next in event queue"""
        return self._queue_next

    def get_queued_asap(self) -> bool:
        """Return true if on ASAP queue at least once"""
        return self._queue_asap > 0

    def get_queued_timed(self) -> bool:
        """Return true if on a time queue at least once"""
        return self._queue_timed > 0

    def get_queued_concur_next(self) -> bool:
        """Return true if on next concurrency queue at least once"""
        return self._queue_concur_next > 0

    def get_queued_after_next(self) -> bool:
        """Return true if on next concurrency queue at least once"""
        return (self._count_queued - self._queue_concur_next) > 0

    def get_count_queued(self) -> int:
        """Get how many times this executable is on the scenario's event queue"""
        return self._count_queued

    def get_count_queued_asap(self) -> int:
        """Count how many times this part is queued ASAP."""
        return self._queue_asap

    def get_count_queued_timed(self) -> int:
        """Count how many times this part is queued non-ASAP"""
        return self._queue_timed

    def get_count_queued_concur_next(self) -> int:
        """Count how many times this part is queued concurrent with next event. An event is concurrent with itself."""
        return self._queue_concur_next

    def get_count_queued_after_next(self) -> int:
        """Get how many times this part appears on the event queue, at a time later than next iexec on queue."""
        return self._count_queued - self._queue_concur_next

    def get_queue_counts(self) -> Tuple[bool, int, int]:
        return self._queue_next, self._queue_concur_next, self.get_count_queued_after_next()

    # Oliver FIXNE iter 4: move these out (talk to Mark why added)
    def add_event(self, iexec_part: Decl.IExecutablePart, args: Tuple = None, time: float = None, priority: float = 0):
        self._shared_scenario_state.sim_controller.add_event(iexec_part, args=args, time=time, priority=priority)

    def get_part_specific_events(self) -> List[Decl.EventInfo]:
        """
        Get the events that are specific to this part.
        :return: A list of EventInfo objects.
        """
        return self._shared_scenario_state.sim_controller.get_all_events(self)

    def on_removed_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        """
        Called by derived class when the executable is removed from scenario: notifies the simulation controller
        to remove all associated events.
        :param restorable: if True, then the events can be later restored via a call to on_restored_to_scenario()
        """
        events_data = self._shared_scenario_state.sim_controller.remove_all_events(self, restorable)
        if restorable:
            scen_data[self].update(events_data=events_data)

    def on_restored_to_scenario(self, scen_data: Dict[BasePart, Any]):
        """
        Called by derived class when the executable is restored into scenario: notifies the simulation controller
        to re-instate all associated events.
        """
        events = scen_data[self]['events_data']
        self._shared_scenario_state.sim_controller.restore_all_events(events)

    is_queued_next = property(get_queued_next)

    is_queued = property(get_queued)
    is_queued_asap = property(get_queued_asap)
    is_queued_timed = property(get_queued_timed)
    is_queued_concur_next = property(get_queued_concur_next)
    is_queued_after_next = property(get_queued_after_next)

    count_queued = property(get_count_queued)
    count_queued_asap = property(get_count_queued_asap)
    count_queued_timed = property(get_count_queued_timed)
    count_queued_concur_next = property(get_count_queued_concur_next)
    count_queued_after_next = property(get_count_queued_after_next)

    # ----------------------------------------------------------------------
    # WARNING: the methods below should ONLY be called by the EventQueue
    # ----------------------------------------------------------------------

    def set_queued_next(self, status: bool):
        """
        Indicate whether this executable is next on the scenario event queue. If status is False, then
        asap_empty is used to determine concurrency status.
        """
        self._queue_next = status
        if self._anim_mode_shared:
            self.__notify_observers()

    def change_count_asap_signals(self, delta: int):
        """Change the count of how many times this executable is ASAP event."""
        self._queue_asap += delta
        self._count_queued += delta
        if self._anim_mode_shared:
            self.__notify_observers()

    def change_count_time_signals(self, delta: int):
        """Change the count of how many times this executable is timed event."""
        self._queue_timed += delta
        self._count_queued += delta
        if self._anim_mode_shared:
            self.__notify_observers()

    def change_count_concurrent_next(self, delta: int):
        """Change the count of how many times this executable is concurrent with next event."""
        assert delta != 0
        self._queue_concur_next += delta
        if self._anim_mode_shared:
            self.__notify_observers()

    def reset_queued_concur_next(self, new_count: int = 0):
        """Reset the count of how many times this executable is concurrent with next event to given new_count."""
        if self._queue_concur_next != new_count:
            self._queue_concur_next = new_count
            if self._anim_mode_shared:
                self.__notify_observers()

    def get_last_exec_error_info(self) -> ScenAlertInfo:
        """Returns true only if the last call or signaling succeeded; false if raised exception"""
        call_errs = self.get_alerts(level=ScenAlertLevelEnum.error, category=ErrorCatEnum.call)
        return call_errs.pop() if call_errs else None

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    last_exec_error_info = property(get_last_exec_error_info)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    def __call__(self, *args, **kwargs):
        """Calls this part's script, but via call operator. Same docs as call()."""
        return self.__call(*args, **kwargs)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_optional
    def _on_parameters_changed(self):
        """
        If the change of the parameters leads to other activities, the derived class can override this function. The
        default implementation does nothing.
        """
        pass

    @override_required
    def _exec(self, _debug_mode: bool, _as_signal: bool, *args, **kwargs):
        """
        Execute this scenario part. This must be overridden by derived classes to implementate the "execution"
        behavior of the part.

        :param args: the required (positional) arguments to give to _exec()
        :param kwargs: the optional (named) arguments to give to _exec()
        :param _debug_mode: an "internal" flag that is set by the caller to indicate debug mode (True
            if want to stop at next breakpoint)
        :param _as_signal: an "internal" flag that is set by the caller to indicate whether called normal or as signal
        """
        raise NotImplementedError('IExecutablePart._exec() function mandatory override not implemented.')

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __set_last_exec_error_info(self, exc: Exception):
        self._clear_own_alerts(ScenAlertLevelEnum.error, ErrorCatEnum.call)
        if exc is not None:
            self._add_alert(ScenAlertLevelEnum.error, ErrorCatEnum.call, str(exc), path=self.path)

    def __notify_observers(self):
        """
        Notify any objects interested in the queue counts: those connected to sig_queue_counters_changed and
        the parent. This must only be called if animation is on because it is rather expensive: all actors
        up the chain of ancestry will be notified.
        """
        assert self._anim_mode_shared
        self.exec_signals.sig_queue_counters_changed.emit(*self.get_queue_counts())
        if self._parent_actor_part:
            self._parent_actor_part.set_child_queueing_changed()

    def __call(self, *args, _debug_mode: bool = False, _as_signal: bool = False, **kwargs):
        """
        Execute a scenario part, with given args and kwargs. Returns whatever the derived class implements,
        or propagates whatever exception it raises. The self.last_exec_error_info property is updated to capture
        error information for last execution. The sig_alert_status_changed() is emitted only if a change has 
        occurred (there was an error, and now there isn't; there wasn't one, now there is; new error)

        Note: dunder prefix on debug_mode and as_signal to avoid clashes with call arg names from function
        part script parameters.
        """
        log.info('Executable part {} executing via {}{}',
                 self, ('debug ' if _debug_mode else ''), ('signal' if _as_signal else 'call'))

        try:
            self.__set_last_exec_error_info(None)
            result = self._exec(_debug_mode, _as_signal, *args, **kwargs)

            if self._anim_mode_shared:
                self.exec_signals.sig_exec_done.emit()

            return result

        except Exception as exc:
            self.__set_last_exec_error_info(exc)
            raise
