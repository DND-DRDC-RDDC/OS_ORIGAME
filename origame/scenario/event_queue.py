# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Event Queue functionality of Origame scenario execution

There are ASAP events and timed events. The EventQueue is implemented in terms of Concurrency sub-queues (aka
bins): an ASAP sub-queue and 0 or more timed-events sub-queues; each one manages events for a given time.

EventQueue uses a bisection search to identify which timed-events queue a timed event should be inserted
into (or create a new timed-events queue); this provides very good performance for large # events. In turn,
a timed-events queue uses bisection to find which priority bin in which to insert event.

Note: lists are used for storing times and priorities; deques could have been used since they are much faster
for pop at either end; but lists are much faster for insertion. Since every event that goes onto the queue must
be popped once, both containers are equivalent in terms of the overal performance: deques would make the queue faster
on get, but slower on put.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import json
import logging
from bisect import bisect_left
from collections import namedtuple
from datetime import datetime
from pathlib import Path

# [2. third-party]

# [3. local]
from ..core import BridgeEmitter, BridgeSignal, override, override_required
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from .ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj, SaveError, SaveErrorLocationEnum, OriSimEventKeys as EqKeys
from .ori import get_pickled_str
from .part_execs import IExecutablePart
from .defn_parts import BasePart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'EventQueue',
    'CallInfo',
    'EventInfo',
]

log = logging.getLogger('system')

LAST_OF_PREVIOUS_BIN = -1
LOG_RAW_EVENT_PUSH_POP = False
MIN_EVENT_TIME = 0.0


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class CallInfo:
    """
    Aggregate the call information for an event to be put on the event queue: function part and call arguments.
    It also facilitates representing the call arguments as a string and editing the call arguments from a string that
    represents a valid Python expression.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------

    @staticmethod
    def repr_evaluatable(arg_str: str) -> bool:
        """
        Return True if the supplied string will produce a tuple of Python objects when given to get_args_from_string().
        :param arg_str: the Python expression to test
        """
        try:
            CallInfo.get_args_from_string(arg_str)
            return True
        except:
            return False

    @staticmethod
    def get_args_from_string(args_str: str) -> Tuple:
        """
        Evaluate args_str and return the result.
        :param args_str: valid python expression that represents a tuple of arguments to give to a function call
        :raise ValueError: if the expression does not evaluate to a tuple
        """
        expr = eval(args_str) if args_str else ()
        if not isinstance(expr, tuple):
            expr = eval('({},)'.format(args_str))
        assert isinstance(expr, tuple)
        return expr

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, event_id: int, iexec: IExecutablePart, args=tuple):
        """
        :param event_id: Unique ID for this call info
        :param iexec: the executable part to call (execute)
        :param args: the call arguments that will be given to the part when executed
        """
        assert isinstance(iexec, IExecutablePart)
        self._iexec = iexec
        if args is None:
            args = ()
        elif not isinstance(args, tuple):
            args = (args,)
        self._args = args
        self._unique_id = event_id
        self.__args_string_repr = None
        self.__args_has_string_repr = None

    def get_iexec(self):
        """Get the executable to be called"""
        return self._iexec

    def get_args(self):
        """Get the arguments to be passed to the executable part being signaled"""
        return self._args

    def set_args(self, new_args: Tuple):
        """
        When the executable part gets called at event processing time, it will receive *new_args as arguments.
        :param new_args: the arguments to be passed to the executable part being signaled
        """
        if self._args is not new_args:
            self._args = new_args
            self.__args_has_string_repr = None
            self.__args_string_repr = None

    def get_unique_id(self):
        """Get the unique ID for this call info"""
        return self._unique_id

    def get_args_as_string(self) -> str:
        """
        Get the arguments object as a string. The string is either empty, one object, a tuple of 2 or more objects but
        without the outer parentheses, or a one-tuple with outer parentheses:

        - () -> ''
        - (1,) -> '1'
        - (1,2) -> '2, 2'
        - ([1,2,3],) -> '([1,2,3],)'

        The last case is to help user in the rare circumstance, as Python requires special syntax for that case only.
        All other cases resolve to one of the above.

        Note: The string can be edited only if self.args_repr_evaluatable is True.
        """
        if self.__args_string_repr is None:
            if not self._args:
                self.__args_string_repr = ''
            elif len(self._args) == 1:
                if isinstance(self._args[0], (list, tuple)):
                    self.__args_string_repr = repr(self._args)
                else:
                    # don't want outer parentheses and trailing comma
                    self.__args_string_repr = repr(self._args[0])
            else:
                # don't want outer parentheses
                self.__args_string_repr = repr(self._args)[1:-1]

        return self.__args_string_repr

    def args_repr_evaluatable(self) -> bool:
        """Does self.args have a string representation?"""
        if self.__args_has_string_repr is None:
            self.__args_has_string_repr = CallInfo.repr_evaluatable(self.get_args_as_string())

        return self.__args_has_string_repr

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    iexec = property(get_iexec)
    args = property(get_args, set_args)
    unique_id = property(get_unique_id)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    def __call__(self):
        """Call the executable part with args set at construction (or reset later via set_args/args)"""
        self.iexec(*self.args)

    def __repr__(self):
        return "CallInfo({}, {}, {})".format(self._unique_id, self._iexec, self._args)


# Class to aggregate the information for one event
EventInfo = namedtuple('EventInfo', ('time_days', 'priority', 'call_info'))


class ConcurrentEventsSubQueue:
    """
    Represent a portion of the Event Queue that corresponds to the "same simulation time".
    """

    def set_is_next_bin(self, status: bool):
        """
        Set whether the next event to be popped from the Event Queue will be taken from this sub-queue.
        Separate sub-queues (aka bins) don't "know" about each other, so the Event Queue must tell each
        one if it holds the next event to be popped. If it does, then each executable part it contains must
        be updated with how many times it is in the sub-queue (the so-called concurrent-with-next counter).
        When the sub-queue no longer holds the next event, all its executable parts must have their counter
        reset to 0.
        """
        if status:
            # count how many times each executable is in sub-queue:
            iexecs = dict()
            for call_info in self:
                iexec = call_info.iexec
                iexecs.setdefault(iexec, 0)
                iexecs[iexec] += 1

            # change each executable info:
            for iexec, count in iexecs.items():
                iexec.reset_queued_concur_next(count)

        else:
            # no longer next bin, reset all CallInfo to have 0 for concurrency with next
            for call_info in self:
                call_info.iexec.reset_queued_concur_next()

    @override_required
    def clear(self):
        """Remove all events from event queue"""
        raise NotImplementedError

    @override_required
    def __iter__(self) -> CallInfo:
        """Every subqueue must provide a means to iterate over its events"""
        raise NotImplementedError


class TimedEventsQueue(ConcurrentEventsSubQueue):
    """
    Represents a FIFO queue of events that occur at the same simulation time. Each event has a priority, which
    can be any floating point value up to ASAP_PRIORITY_VALUE, with higher values having higher priority.
    They are popped from highest to lower priority, and within a priority bin, first in first out (FIFO).
    """

    def __init__(self, priority: float, call_info: CallInfo):
        """
        A timed queue always has at least one event (when last event popped, the queue must be deleted).
        :param priority: numerical value for priority (0 to MAX) of first event in sub-queue
        :param call_info: call information for this first event
        """
        self._priority_queues = {priority: [call_info]}
        self._sorted_priorities_keys = [priority]

        # by default, all bins are "later" in position; caller will also call set_is_next_bin if next
        # self._is_next_bin = False
        call_info.iexec.change_count_time_signals(+1)

    def insert(self, priority: float, call_info: CallInfo, pred_id: int = None):
        """
        Insert an event in sub-queue.
        :param priority: numerical priority value. Log(N) operation.
        :param call_info: call information for the event
        :param pred_id: if given, then the call info is inserted such that it would be popped right after the call
            info of given ID
        """

        assert len(self._sorted_priorities_keys) == len(self._priority_queues)
        assert self._priority_queues  # always at least one call_info since bin only created when an call_info exists
        assert priority <= EventQueue.MAX_SCHED_PRIORITY

        prio_key_index = bisect_left(self._sorted_priorities_keys, priority)
        if prio_key_index >= len(self._sorted_priorities_keys):
            # larger than largest priority, so append new priority bin and put as first event
            self._sorted_priorities_keys.append(priority)
            self._priority_queues[priority] = [call_info]

        elif self._sorted_priorities_keys[prio_key_index] == priority:  # add to an existing bin:
            if pred_id is None:
                # first in, first out: append at back has highest perf, then will have to remove from back
                self._priority_queues[priority].append(call_info)
            elif pred_id == LAST_OF_PREVIOUS_BIN:
                self._priority_queues[priority].insert(0, call_info)
            else:
                prio_queue = self._priority_queues[priority]
                inserted = False
                for index, ci in enumerate(prio_queue):
                    if ci.unique_id == pred_id:
                        prio_queue.insert(index + 1, call_info)  # index+1 will work as append if last index
                        inserted = True
                        break
                assert inserted

        else:  # create new bin
            self._sorted_priorities_keys.insert(prio_key_index, priority)
            self._priority_queues[priority] = [call_info]

        call_info.iexec.change_count_time_signals(+1)

    def change_priority(self, priority: float, call_info: CallInfo, new_priority: float):
        """
        Change the priority of an event. Note: if new_priority=priority, the event will effectively get moved
        to the end of the priority bin it was in.

        :param priority: current priority value
        :param call_info: call info object affected
        :param new_priority: new priority value
        """
        if priority != new_priority:  # the following should never fail
            self.remove_event(priority, call_info)
            self.insert(new_priority, call_info)

    def pop_next(self) -> Tuple[float, CallInfo]:
        """
        Pop the next event off the queue: the one with highest priority, that was added before all
        other events with same priority.
        :return: a pair containing priority value and CallInfo for the event
        """
        assert self._sorted_priorities_keys  # because self automatically gets deleted once empty

        priority = self._sorted_priorities_keys[-1]  # top priority
        events = self._priority_queues[priority]
        assert events  # automatically gets removed when queue empty, so should never happen

        call_info = events.pop(0)  # FIFO
        call_info.iexec.change_count_time_signals(-1)

        # cleanup if the given priority bin is empty
        if not events:
            del self._sorted_priorities_keys[-1]
            del self._priority_queues[priority]

        return priority, call_info

    def remove_event(self, priority: float, call_info: CallInfo, restorable: bool = False) -> Either[int, None]:
        """
        Remove an event from the queue.
        :param priority: priority value of event
        :param call_info: CallIInfo object to remove
        """
        pred_id = self.get_predecessor_id(priority, call_info) if restorable else None
        events = self._priority_queues[priority]

        events.remove(call_info)
        call_info.iexec.change_count_time_signals(-1)

        if not events:
            self._sorted_priorities_keys.remove(priority)
            del self._priority_queues[priority]

        return pred_id

    def is_empty(self) -> bool:
        """Returns true if there are no events queued here."""
        return not bool(self._sorted_priorities_keys)

    def get_next(self) -> Tuple[float, CallInfo]:
        """
        Return next event (i.e., the one that will be received by pop_next()): a pair, containing priority
        value and CallInfo. Note: this must only be called if is_empty() returns False.
        """
        # EventQueue deletes this instance immediately once empty, so should never get here if no events left:
        assert self._sorted_priorities_keys

        priority = self._sorted_priorities_keys[-1]
        call_infos = self._priority_queues[priority]
        assert call_infos  # priority bin deleted once empty, so should always have at least one call info

        # first out is first in for all but ASAP priority, then first out is last in
        return priority, call_infos[0]

    def get_predecessor_id(self, priority: float, call_info: CallInfo, same_iexec: bool = False) -> Either[int, None]:
        """
        Get the unique ID of the predecessor of an event. Return None if don't have event for given call_info.
        This method is costly to execute so should only be called if animation is on.
        :param priority: priority value of event; if None, use highest priority of this bin
        :param call_info: CallInfo for the event
        """
        try:
            events = self._priority_queues[priority]
            call_index = events.index(call_info)
        except (KeyError, ValueError):
            # we don't have a bin with given priority
            return None

        if same_iexec:
            return self.__get_pred_id_same(priority, call_index, call_info.iexec)

        else:
            # find predecessor if it is in same priority bin:
            if call_index > 0:
                return events[call_index - 1].unique_id
            return self.__get_pred_id_higher_prio(priority)

    def get_last(self, iexec: IExecutablePart = None) -> Tuple[float, CallInfo]:
        """
        Get the event that is currently scheduled to execute last. This is the one with lowest priority, added
        last with that priority.
        :param iexec: if given, the event returned has iexec as executable
        :return: a pair, the priority value and the CallInfo object for event that should be executed last
            (or (None, None) if iexec given and no match for it)
        """
        assert self._sorted_priorities_keys  # must be non-empty because self gets deleted automatically once empty

        for priority in self._sorted_priorities_keys:
            call_infos = self._priority_queues[priority]
            assert call_infos  # must be non-empty because self gets deleted automatically once empty
            for call_info in reversed(call_infos):
                assert call_info.iexec is not None
                if iexec is None or call_info.iexec is iexec:
                    return priority, call_info

        return None, None

    def put_all(self, time_stamp: float, container: List[EventInfo], filter_part: IExecutablePart = None):
        """
        Extend container with list of EventInfo for each event in bin, ordered from highest to lowest priority.
        :param time_stamp: the simulation time that is associated with this concurrency bin
        :param container: the list in which to put the EventInfo instances
        :param filter_part: the part to filter the events on ie, only return events that are for this part
        """
        for priority in reversed(self._sorted_priorities_keys):
            if filter_part is None:
                container.extend(
                    EventInfo(time_stamp, priority, call_info) for call_info in self._priority_queues[priority])
            else:
                container.extend(
                    EventInfo(time_stamp, priority, call_info) for call_info in self._priority_queues[priority]
                    if call_info.iexec is filter_part)

    @override(ConcurrentEventsSubQueue)
    def clear(self):
        """Clear all events from this timed events queue. This is not performance critical."""
        for queue in self._priority_queues.values():
            for call_info in queue:
                call_info.iexec.change_count_time_signals(-1)
                call_info.iexec.reset_queued_concur_next()

        self._sorted_priorities_keys = []
        self._priority_queues = {}

    @override(ConcurrentEventsSubQueue)
    def __iter__(self) -> CallInfo:
        """Returns a generator that supports iterations over all events in the queue, from highest to lowest priority"""
        for priority in reversed(self._sorted_priorities_keys):
            for call_info in self._priority_queues[priority]:
                (yield call_info)

    def __get_pred_id_same(self, start_priority: float, call_index: int, iexec: IExecutablePart) -> Either[int, None]:
        """
        Get the event ID of predecessor to event at call_index, for given priority, for executable iexec
        :param start_priority: the starting value of priority; if event not found at that priority, higher priorities
            will be searched, in order of increasing priority
        :param call_index: the index of CallInfo into start_priority queue
        :param iexec: the iexec to look for
        :return: unique ID of predecessor event, or None if none found that matches iexec
        """
        priority_index = self._sorted_priorities_keys.index(start_priority)
        for higher_priority in self._sorted_priorities_keys[priority_index:]:
            events = self._priority_queues[higher_priority]
            if higher_priority == start_priority:
                # for starting priority, only need subset of events, ending at call_index
                events = events[:call_index]
            for timed_call_info in reversed(events):
                if timed_call_info.iexec is iexec:
                    return timed_call_info.unique_id

        return None

    def __get_pred_id_higher_prio(self, priority: float) -> Either[int, None]:
        """
        Get the event ID of "latest" event that has higher priority than priority
        :param priority: the starting value of priority; if event not found at that priority, higher priorities
            will be searched, in order of increasing priority
        :return: unique ID of predecessor event, or None if no higher priority queue exists
        """
        try:
            priority_index = self._sorted_priorities_keys.index(priority)
            higher_priority = self._sorted_priorities_keys[priority_index + 1]
            events = self._priority_queues[higher_priority]
            return events[-1].unique_id  # last event of higher prio bin

        except IndexError:
            return None  # there is no higher priority bin


class AsapQueue(ConcurrentEventsSubQueue):
    """A LIFO queue of CallInfo instances for ASAP scenario events. """

    def __init__(self):
        """Start as an empty queue"""
        self._asap_queue = []

    def add_event(self, call_info: CallInfo, pred_id: int = None):
        """
        Add given call_info to this queue.
        :param pred_id: if given, then the call info is inserted such that it would be popped right after the call
            info of given ID
        """
        if pred_id is None:
            self._asap_queue.append(call_info)

        elif pred_id == LAST_OF_PREVIOUS_BIN:
            self._asap_queue.insert(0, call_info)

        else:
            inserted = False
            for index, ci in enumerate(self._asap_queue):
                if ci.unique_id == pred_id:
                    self._asap_queue.insert(index, call_info)
                    inserted = True
                    break
            assert inserted

        call_info.iexec.change_count_asap_signals(+1)

    def pop_next(self) -> CallInfo:
        """Remove next event from this queue. Raises IndexError if no events."""
        assert self._asap_queue
        call_info = self._asap_queue.pop(-1)  # LIFO
        call_info.iexec.change_count_asap_signals(-1)
        return call_info

    def remove_event(self, call_info: CallInfo, restorable: bool = False) -> Either[int, None]:
        """
        Remove the given CallInfo from ASAP queue.
        :param restorable: if True, returns the predecessor ID that will be given to restore_event()
        """
        pred_id = self.get_predecessor_id(call_info) if restorable else None
        self._asap_queue.remove(call_info)

        call_info.iexec.change_count_asap_signals(-1)
        return pred_id

    def get_num_events(self) -> int:
        """Number of events on this queue."""
        return len(self._asap_queue)

    def has_events(self) -> bool:
        """True only if this queue has any events."""
        return bool(self._asap_queue)

    def get_next(self) -> CallInfo:
        """Get the next event that will be popped by pop_next if called. Returns None if not has_events()."""
        return self._asap_queue[-1] if self._asap_queue else None

    def get_all_as_list(self, filter_part: IExecutablePart = None) -> List[CallInfo]:
        """
        Get list of all ASAP events (each item in list is CallInfo instance)
        :param filter_part: Only asap events that belong to the optional filter_part will be returned when this
        filter is supplied.
        """
        if filter_part is None:
            return list(reversed(self._asap_queue))
        else:
            return [call_info for call_info in reversed(self._asap_queue) if call_info.iexec is filter_part]

    def get_predecessor_id(self, call_info: CallInfo, same_iexec: bool = False) -> Either[int, None]:
        """Get the unique ID of the predecessor to call_info. Returns None if self does not contain call_info."""
        try:
            call_index = self._asap_queue.index(call_info)
            if same_iexec:
                for asap_call_info in self._asap_queue[call_index + 1:]:
                    if asap_call_info.iexec is call_info.iexec:
                        return asap_call_info.unique_id
            else:
                return self._asap_queue[call_index + 1].unique_id

        except (IndexError, ValueError):
            # we don't have it
            return None

    def get_last(self, iexec: IExecutablePart = None) -> CallInfo:
        """
        Get the last ASAP event that would be popped (this is the first one added since LIFO queue).
        :param iexec: if given, the event returned has iexec as executable
        """
        if iexec is None:
            return self._asap_queue[0] if self._asap_queue else None

        for call_info in self._asap_queue:
            if call_info.iexec is iexec:
                return call_info
        return None

    @override(ConcurrentEventsSubQueue)
    def clear(self):
        """Clear all events from this ASAP queue."""
        for call_info in self._asap_queue:
            call_info.iexec.change_count_asap_signals(-1)
        for call_info in set(self._asap_queue):
            call_info.iexec.reset_queued_concur_next()
        # assert sum([call_info.iexec.is_queued_asap for call_info in self.__asap_queue]) == 0

        self._asap_queue.clear()

    @override(ConcurrentEventsSubQueue)
    def __iter__(self):
        """Iterate over all events in this queue"""
        return self._asap_queue.__iter__()

    def __bool__(self):
        return bool(self._asap_queue)

    num_events = property(get_num_events)


class EventQueue(IOriSerializable):
    """
    Represent a scenario's Events Queue. All events with same time stamp are in same concurrency slot.
    Timed events have a priority from 0 to MAX_SCHED_PRIORITY_VALUE, and ASAP events have a priority equal to
    ASAP_PRIORITY_VALUE. ASAP events get popped before all other queued events. Additionally, ASAP events are
    popped last-in-first-out, whereas all other events are popped first-in-first-out (within their
    time-priority bin).

    The two main gotchas with the EventQueue are related to signaling and queue properties on events:

    - signaling: whenever the event queue changes, signals are emitted to indicate the nature of the change.
        Note that sig_queue_totals_changed is always emitted when total # of scheduled or ASAP changed, whereas
        other signals are only emitted if bool(anim_reader) is True.
    - executable parts have various properties related to their presence on the event queue: how many times a part is
        on the queue, how many times it an ASAP event, whether it is next on queue, how many times it is concurrent to
        the next event (ie. same time), etc. When an event is added or removed from Event Queue, these properties
        are updated regardless of animation state (because there is little overhead to doing this). However, when
        the "next bin" flag changes on a concurrency sub-queue, the executable parts in that sub-queue are only
        updated if animation is on, or when animation is turned on (via set_anim_mode()).
    """

    class Signals(BridgeEmitter):
        # following signal is emitted regardless of animation state
        sig_queue_totals_changed = BridgeSignal(int, int)  # number scheduled, number ASAP

        # following signals are emitted only when animation on
        sig_queue_cleared = BridgeSignal()
        sig_time_stamps_changed = BridgeSignal(float)  # number of days
        sig_event_added = BridgeSignal(int, EventInfo)  # predecessor ID (CallInfo.unique_id), EventInfo added
        sig_event_removed = BridgeSignal(int)  # CallInfo.unique_id
        sig_args_changed = BridgeSignal(CallInfo)

    MIN_SCHED_PRIORITY = 0  # min value of priority for scheduled events
    MAX_SCHED_PRIORITY = 1000000  # max value of priority for scheduled events
    ASAP_PRIORITY_VALUE = 1 + MAX_SCHED_PRIORITY  # ASAP has a higher priority than all scheduled events
    MAX_PRIORITY = ASAP_PRIORITY_VALUE  # highest value of priority accepted

    def __init__(self, thread=None):
        """
        Initialize to an empty event queue. By default, the animation mode is constant True. Use set_anim_mode()
        to change the default behavior.
        """
        IOriSerializable.__init__(self)
        self.signals = EventQueue.Signals(thread=thread)

        self.__asap_queue = AsapQueue()  # all events that are ASAP; LIFO
        self.__scheduled_queue = {}  # all events that are schedule; FIFO
        self.__sorted_times_keys = []  # use this to find where to insert event using bisection

        self.__num_scheduled_events = 0  # ie non-ASAP events
        self.__next_event_id = 0  # every event is given a unique ID, useful for editing
        self.__starttime = None

        self.__animation_on = None
        self.__next_bin = None  # while anim is True, this is next bin (either ASAP or Timed or None)
        self.__next_call_info = None  # while anim is True, this is next event (either ASAP or Timed or None)
        self.set_anim_mode(True)

        self.__last_pop_time = None  # time_stamp of last event popped
        self.__event_log = "event_log.csv"
        if LOG_RAW_EVENT_PUSH_POP:
            event_log = Path(self.__event_log)
            log.warning("Creating event file {}", event_log.absolute())
            with event_log.open('w') as f:
                f.write("")
                f.close()

    def add_asap(self, iexec: IExecutablePart, args: Tuple = ()) -> CallInfo:
        """
        Add an ASAP event to the quueue.
        :param iexec: executable part to add
        :param args: call arguments when ASAP event eventually gets processed
        :return: the created CallInfo
        """
        if not isinstance(iexec, IExecutablePart):
            raise ValueError("ASAP event can only be created for callable part (part '{}' of type {} is not callable)"
                             .format(iexec.path, iexec.PART_TYPE_NAME))
        call_info = CallInfo(self.__gen_next_event_id(), iexec, args)
        self.__add_event(None, self.ASAP_PRIORITY_VALUE, call_info)
        return call_info

    # noinspection PyUnboundLocalVariable
    def add_event(self, time_days: float, priority: float, iexec: IExecutablePart, args: Tuple = ()) -> CallInfo:
        """
        Add an event to the queue. If priority == ASAP_PRIORITY_VALUE, the event is an ASAP event, in which case
        the time_days is not used.

        :param time_days: the simulation time (in days) at which event should be processed; if None, the last pop
            time will be used, or MIN_EVENT_TIME if no time events ever popped
        :param priority: numerical valu of priority, or ASAP_PRIORITY_VALUE if ASAP
        :param iexec: executable part to add
        :param args: call arguments when event eventually gets processed
        :return: the created CallInfo object
        :raise ValueError: if iexec does not derive from IExecutablePart
        """
        if not isinstance(iexec, IExecutablePart):
            raise ValueError("Event can only be created for callable part (part '{}' of type {} is not callable)"
                             .format(iexec.path, iexec.PART_TYPE_NAME))

        call_info = CallInfo(self.__gen_next_event_id(), iexec, args)
        if time_days is None:
            time_days = self.__last_pop_time or MIN_EVENT_TIME
        self.__add_event(time_days, priority, call_info)
        return call_info

    def edit_event(self, event_info: EventInfo, new_time_days: float, new_priority: float, new_call_args_str: str):
        """
        Edit an event that is on this queue. Note: if none of the new_ arguments change the event, the event will
        be moved to be last in its concurrency bin (if ASAP) or priority bin (if timed).

        :param event_info: the EventInfo instance containing the information identifying the event to edit
        :param new_time_days: new simulation time (in days) for event
        :param new_priority: new numerical priority value for event
        :param new_call_args_str: new call arguments (string representation of a Python expression)
        """
        if self.__last_pop_time is not None and new_time_days < self.__last_pop_time:
            raise ValueError("Event edit error.\n\nNew time cannot less than last event's pop time")

        # conversion from string to Python obj could fail so try it first:
        call_info = event_info.call_info
        if call_info.get_args_as_string() != new_call_args_str:
            call_info.args = CallInfo.get_args_from_string(new_call_args_str)
            self.signals.sig_args_changed.emit(call_info)

        if event_info.time_days != new_time_days or event_info.priority != new_priority:
            # need full remove + add since will change bins:
            try:
                self.remove_event(event_info.time_days, event_info.priority, call_info)
            except Exception:
                raise RuntimeError("Event edit error. Edited event not found on the queue.")
            self.__add_event(new_time_days, new_priority, call_info)

    def pop_next(self) -> Tuple[float, float, CallInfo]:
        """
        Pop the next call_info: ASAP call_info if there is one, then if not, the one with earliest time stamp,
        highest priority, and added before all others with same time/priority.
        :return: triplet containing time stamp, priority, and CallInfo
        """
        # first any ASAP events:
        if self.__asap_queue.has_events():
            time_days = self.__get_asap_time()
            priority = self.ASAP_PRIORITY_VALUE
            call_info = self.__asap_queue.pop_next()
            from_bin = self.__asap_queue

        else:  # scheduled events:
            if not self.__sorted_times_keys:
                raise RuntimeError('nothing left to pop')

            # then get next call_info from scheduled time_days bin:
            time_days = self.__sorted_times_keys[0]
            time_bin = self.__scheduled_queue[time_days]
            from_bin = time_bin
            assert not time_bin.is_empty(), "BUG: the time_days bin should have been removed once emptied"

            # have the bin with our call_info, pop it off
            priority, call_info = time_bin.pop_next()
            self.__num_scheduled_events -= 1
            if time_bin.is_empty():
                del self.__sorted_times_keys[0]
                del self.__scheduled_queue[time_days]

            assert len(self.__sorted_times_keys) == len(self.__scheduled_queue)
            assert time_days is not None

        self.__last_pop_time = time_days

        if from_bin is self.__next_bin:
            # event removed from next-bin, need to update its next-bin counter:
            call_info.iexec.change_count_concurrent_next(-1)

        # Notifications of new state:
        log.info("Event {} popped ({} events left)",
                 call_info.unique_id, self.__num_scheduled_events + self.__asap_queue.num_events)
        if LOG_RAW_EVENT_PUSH_POP:
            el = "{0}|||{1}|||{2}|||{3}|||{4}|||{5}".format("___pop____",
                                                            time_days,
                                                            priority,
                                                            "root" + call_info.iexec.path,
                                                            call_info.args,
                                                            self.__num_scheduled_events +
                                                            self.__asap_queue.num_events)
            with Path(self.__event_log).open("a") as f:
                f.write(el)
                f.write("\n")
                f.close()

        self.signals.sig_queue_totals_changed.emit(self.__num_scheduled_events, self.__asap_queue.num_events)
        if self.__animation_on:
            self.__update_next_info()
            self.signals.sig_event_removed.emit(call_info.unique_id)

        return time_days, priority, call_info

    def remove_event(self, time_days: float, priority: float, call_info: CallInfo, restorable: bool = False) -> int:
        """
        Remove an event from this queue.

        :param time_days: the simulation time (in days) of event to be removed
        :param priority: numerical valu of priority of event to be removed (can be ASAP_PRIORITY_VALUE if ASAP)
        :return: if restorable is True, returns the predecessor event callinfo ID *in same time bin*; returns None
            if not restorable, or if the predecessor event is not in same time bin
        :raise KeyError: if invalid time or priority
        :raise ValueError if invalid call_info.
        """
        if priority == EventQueue.ASAP_PRIORITY_VALUE:
            pred_id = self.__asap_queue.remove_event(call_info, restorable)
            assert self.__next_bin is self.__asap_queue
            from_bin = self.__asap_queue

        else:
            concurrency_bin = self.__scheduled_queue[time_days]
            pred_id = concurrency_bin.remove_event(priority, call_info, restorable)
            self.__num_scheduled_events -= 1
            from_bin = concurrency_bin
            if concurrency_bin.is_empty():
                self.__sorted_times_keys.remove(time_days)
                del self.__scheduled_queue[time_days]

        if from_bin is self.__next_bin:
            # event removed from next-bin, need to update its next-bin counter:
            call_info.iexec.change_count_concurrent_next(-1)

        # Notifications of new state:
        log.info("Event {} removed (restorable={})", call_info.unique_id, restorable)
        self.signals.sig_queue_totals_changed.emit(self.__num_scheduled_events, self.__asap_queue.num_events)
        if self.__animation_on:
            self.__update_next_info()
            self.signals.sig_event_removed.emit(call_info.unique_id)

        return pred_id

    def restore_event(self, time_days: float, priority: float, call_info: CallInfo, pred_id: int):
        """
        Restore an event that was removed from the queue.
        :param time_days:
        :param priority:
        :param call_info:
        """
        if self.__last_pop_time is not None and time_days < self.__last_pop_time:
            raise ValueError("Restoration time cannot be before last pop time")

        if pred_id is None:
            pred_id = LAST_OF_PREVIOUS_BIN
        self.__add_event(time_days, priority, call_info, predecessor_id=pred_id)

    def clear(self):
        """
        Drop all events from the queue. This deliberately ignores animation mode; it will never be called
        while animation is off.
        """
        if self.num_events > 0:
            log.info("Sim event queue being cleared")

        # clear:
        self.__asap_queue.clear()
        for queue in self.__scheduled_queue.values():
            queue.clear()

        # reset:
        self.__scheduled_queue = {}
        self.__sorted_times_keys = []
        self.__num_scheduled_events = 0
        self.__last_pop_time = None
        self.__next_bin = None
        if self.__next_call_info is not None:
            self.__next_call_info.iexec.set_queued_next(False)
            self.__next_call_info = None

        # Notifications of new state:
        self.signals.sig_queue_totals_changed.emit(0, 0)
        if self.__animation_on:
            self.signals.sig_queue_cleared.emit()

    def set_anim_mode(self, value: bool):
        """Set the animation mode to given value. When True, state changes will cause signals to be emitted. """
        self.__animation_on = value
        if self.__animation_on:
            self.__update_next_info()

    def get_all_as_list(self, filter_part: IExecutablePart = None) -> List[EventInfo]:
        """
        Get all events of queue as a list of EventInfo instances. This method is costly to call if queue has a
        large # of events (10k or 100k).
        :param filter_part: An executable part that is used to filter the events out i.e. only events belonging to this
            part will be returned.
        """
        asap_time = self.__get_asap_time()
        events = [EventInfo(asap_time, EventQueue.ASAP_PRIORITY_VALUE, event)
                  for event in self.__asap_queue.get_all_as_list(filter_part=filter_part)]

        for time in self.__sorted_times_keys:
            self.__scheduled_queue[time].put_all(time, events, filter_part=filter_part)

        return events

    def get_all_as_parts_list(self, filter_part: IExecutablePart = None) -> List[IExecutablePart]:
        """Get the list of events as a list of parts. Same params as get_all_as_list()."""
        return [ev.call_info.iexec for ev in self.get_all_as_list(filter_part=filter_part)]

    def move_times(self, delta_days: float):
        """Change the time of each event by the given delta sim time"""
        log.info("Sim Event Queue shifting event times by {:f} days", delta_days)
        new_schedule = {}
        for index, time in enumerate(self.__sorted_times_keys):
            new_time = time + delta_days
            self.__sorted_times_keys[index] = new_time
            new_schedule[new_time] = self.__scheduled_queue[time]
        self.__scheduled_queue = new_schedule

        if self.__last_pop_time is not None:
            self.__last_pop_time += delta_days

        if self.__animation_on:
            self.signals.sig_time_stamps_changed.emit(delta_days)

    def get_num_events(self) -> int:
        """Get number of events on queue, including ASAP"""
        return self.__num_scheduled_events + self.__asap_queue.num_events

    def has_asap(self) -> bool:
        """True if there are any ASAP events"""
        return self.__asap_queue.has_events()

    def get_next(self) -> EventInfo:
        """
        Get next event on queue (i.e. the one that would be returned by pop_next()), in the form of an EventInfo.
        Returns None if no events left.
        """
        if self.__asap_queue.has_events():
            asap_time = self.__get_asap_time()
            return EventInfo(asap_time, self.ASAP_PRIORITY_VALUE, self.__asap_queue.get_next())

        if self.__sorted_times_keys:
            time = self.__sorted_times_keys[0]
            time_bin = self.__scheduled_queue[time]
            priority, call_info = time_bin.get_next()
            return EventInfo(time, priority, call_info)

        return None

    def get_next_time_days(self) -> float:
        """
        Return time of next event that will be poppsed: if ASAP events are queued, return the current sim time;
        else return the time of the next timed bin, or None if no timed events (so this function returns None
        if the queue is empty).
        """
        if self.__asap_queue:
            return self.__get_asap_time()
        else:
            return self.__sorted_times_keys[0] if self.__sorted_times_keys else None

    def get_last_pop_time_days(self) -> float:
        """
        Get time stamp of last event that was popped from queue, or 0 if no event popped since queue
        created or cleared.
        """
        return self.__last_pop_time

    def is_empty(self) -> bool:
        """Return true only if there are no ASAP events and no scheduled events."""
        return (not self.__asap_queue.has_events()) and self.__num_scheduled_events == 0

    def check_is_next(self, iexec: IExecutablePart) -> bool:
        """Is given part the next one on queue?"""
        next_call_info = self.__get_next_call_info()
        if next_call_info:
            return next_call_info.iexec is iexec
        return False

    def get_predecessor_id(self, event_info: EventInfo, same_iexec: bool = False) -> Either[int, None]:
        """
        Get the unique ID of the predecessor of an event (the event that will be popped before the given event).
        :raises: IndexError if timed event with event_info.time_days not in self
        """
        if event_info.priority == self.ASAP_PRIORITY_VALUE:
            return self.__asap_queue.get_predecessor_id(event_info.call_info, same_iexec)

        # not in ASAP, has to be in a time bin:
        assert event_info.time_days in self.__sorted_times_keys

        scheduled_queue = self.__scheduled_queue[event_info.time_days]
        call_id = scheduled_queue.get_predecessor_id(event_info.priority, event_info.call_info, same_iexec)
        if call_id is not None:
            return call_id

        # if we get here, then predecessor is not in same time bin as the event (ie. the event is the first in
        # the timed-events bin that has it):

        # if event time is first bin, then predecessor is an ASAP event, else it is previous time bin:
        index = self.__sorted_times_keys.index(event_info.time_days)
        assert call_id is None
        if same_iexec:
            for pred_time in reversed(self.__sorted_times_keys[:index]):
                pred_scheduled_queued = self.__scheduled_queue[pred_time]
                call_info = pred_scheduled_queued.get_last(iexec=event_info.call_info.iexec)[1]
                if call_info is not None:
                    return call_info.unique_id

            call_info = self.__asap_queue.get_last(iexec=event_info.call_info.iexec)
            if call_info is not None:
                return call_info.unique_id

        else:
            if index == 0:
                call_info = self.__asap_queue.get_last()
                if call_info is not None:
                    return call_info.unique_id

            else:
                pred_time = self.__sorted_times_keys[index - 1]
                pred_scheduled_queued = self.__scheduled_queue[pred_time]
                return pred_scheduled_queued.get_last()[1].unique_id

        assert call_id is None
        return call_id

    num_events = property(get_num_events)
    last_pop_time_days = property(get_last_pop_time_days)

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum,
                           refs_map: Dict[int, BasePart] = None, **kwargs):
        for event_info in ori_data['events']:
            self.add_event(event_info[EqKeys.TIME_DAYS], event_info[EqKeys.PRIORITY],
                           refs_map[event_info[EqKeys.PART_ID]], args=tuple(event_info[EqKeys.CALL_ARGS]))

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        event_infos = self.get_all_as_list()
        events_ori = []
        for event_info in event_infos:
            call_info = event_info.call_info
            for arg in call_info.args:
                if isinstance(arg, dict):
                    for k, v in arg.items():
                        safe_val, is_pickle_successful = get_pickled_str(v, SaveErrorLocationEnum.event_queue)
                        if not is_pickle_successful:
                            arg[k] = safe_val
                else:
                    safe_val, is_pickle_successful = get_pickled_str(arg, SaveErrorLocationEnum.event_queue)
                    if not is_pickle_successful:
                        arg = safe_val

            events_ori.append({
                EqKeys.TIME_DAYS: event_info.time_days,
                EqKeys.PRIORITY: event_info.priority,
                EqKeys.PART_ID: call_info.iexec.SESSION_ID,
                EqKeys.CALL_ARGS: call_info.args
            })
        return dict(events=events_ori)

    def __get_asap_time(self) -> float:
        """Get the "effective" time stamp of ASAP events: time of last pop, or MIN_EVENT_TIME if nothing ever popped"""
        return self.__last_pop_time or MIN_EVENT_TIME

    def __add_event(self, time_days: float, priority: float, call_info: CallInfo, predecessor_id: int = None):
        """
        Queue a CallInfo for given time and priority. When priority=ASAP, time is automatically
        self.__last_pop_time.
        """
        assert len(self.__sorted_times_keys) == len(self.__scheduled_queue)
        if LOG_RAW_EVENT_PUSH_POP and self.__starttime is None:
            self.__starttime = datetime.now()

        # ASAP event:
        if priority >= self.ASAP_PRIORITY_VALUE:
            time_days = self.__get_asap_time()
            self.__asap_queue.add_event(call_info, predecessor_id)
            to_bin = self.__asap_queue
            log.info("ASAP event (ID {}) added for part {} of type {}: args={}",
                     call_info.unique_id, call_info.iexec, call_info.iexec.PART_TYPE_NAME, call_info.args)

        # scheduled event:
        else:
            if self.__last_pop_time is None:
                if time_days < MIN_EVENT_TIME:
                    log.warning("Event time {0} must be >= {1}, using {1} instead", time_days, MIN_EVENT_TIME)
                    time_days = MIN_EVENT_TIME

            elif time_days < self.__last_pop_time:
                log.warning("Event at time {} days is before last pop time; using {} days instead",
                            time_days, self.__last_pop_time)
                time_days = self.__last_pop_time

            if type(time_days) is not float:
                time_days = float(time_days)

            to_bin = self.__add_scheduled_event(time_days, priority, call_info, predecessor_id)
            log.info("Scheduled event (ID {}) added for part {} of type {}: t={:.5}, p={}, args={}",
                     call_info.unique_id, call_info.iexec, call_info.iexec.PART_TYPE_NAME, time_days, priority,
                     call_info.args)

        log.info('Now {} events on queue', self.__num_scheduled_events + self.__asap_queue.num_events)

        if to_bin is self.__next_bin:
            # event put in next bin, need to update its next-bin counter:
            call_info.iexec.change_count_concurrent_next(+1)

        # Notifications of new state:
        if LOG_RAW_EVENT_PUSH_POP:
            el = "{0}|||{1}|||{2}|||{3}|||{4}|||{5}".format("___push___", time_days, priority,
                                                            "root" + call_info.iexec.path, call_info.args,
                                                            self.__num_scheduled_events + self.__asap_queue.num_events)
            with Path(self.__event_log).open("a") as f:
                f.write(el)
                f.write("\n")
                f.close()

        self.signals.sig_queue_totals_changed.emit(self.__num_scheduled_events, self.__asap_queue.num_events)
        if self.__animation_on:
            self.__update_next_info()
            event_info = EventInfo(time_days, priority, call_info)
            predecessor_id = self.get_predecessor_id(event_info)
            self.signals.sig_event_added.emit(predecessor_id, event_info)

    def __add_scheduled_event(self, time_days: float, priority: float, call_info: CallInfo,
                              predecessor_id: int) -> TimedEventsQueue:
        if self.__scheduled_queue:
            # there are events already, need to find where to insert
            time_key_index = bisect_left(self.__sorted_times_keys, time_days)
            if time_key_index >= len(self.__sorted_times_keys):
                # larger than largest time, so append new bin
                self.__sorted_times_keys.append(time_days)
                new_queue = TimedEventsQueue(priority, call_info)
                self.__scheduled_queue[time_days] = new_queue
                to_bin = new_queue

            elif self.__sorted_times_keys[time_key_index] == time_days:
                # add to an existing bin
                to_bin = self.__scheduled_queue[time_days]
                to_bin.insert(priority, call_info, predecessor_id)

            else:  # insert new bin at specified index
                self.__sorted_times_keys.insert(time_key_index, time_days)
                new_queue = TimedEventsQueue(priority, call_info)
                self.__scheduled_queue[time_days] = new_queue
                to_bin = new_queue

        else:  # no timed bins yet, just add new event
            assert (not self.__sorted_times_keys)
            self.__sorted_times_keys.append(time_days)
            new_queue = TimedEventsQueue(priority, call_info)
            to_bin = new_queue
            self.__scheduled_queue[time_days] = new_queue

        self.__num_scheduled_events += 1
        return to_bin

    def __update_next_info(self):
        """Update next-ness info for all events affected by latest add/remove."""
        assert self.__animation_on

        # next-bin-ness:
        next_bin = self.__get_next_bin()
        if next_bin is not self.__next_bin:
            if self.__next_bin is not None:
                self.__next_bin.set_is_next_bin(False)
            if next_bin:
                next_bin.set_is_next_bin(True)
            self.__next_bin = next_bin

        # next-ness:
        new_next_call_info = self.__get_next_call_info()
        if new_next_call_info is not self.__next_call_info:
            if self.__next_call_info:
                self.__next_call_info.iexec.set_queued_next(False)
            if new_next_call_info:
                new_next_call_info.iexec.set_queued_next(True)
            self.__next_call_info = new_next_call_info

    def __get_next_bin(self) -> Tuple[Either[AsapQueue, TimedEventsQueue]]:
        """Get the next bin (queue) from which pop_next() will get an event. Returns None if no more events."""
        if self.__asap_queue.has_events():
            return self.__asap_queue

        if self.__sorted_times_keys:
            time = self.__sorted_times_keys[0]
            return self.__scheduled_queue[time]

        return None

    def __get_last_id_prev_bin(self, time_days: float) -> Either[int, None]:
        """Get the id of last event of timed bin previous to that of time_days"""
        index = self.__sorted_times_keys.index(time_days)
        if index > 0:
            prev_time = self.__sorted_times_keys[index - 1]
            timed_bin = self.__scheduled_queue[prev_time]
            return timed_bin.get_last()[1].unique_id

        # this is earliest time bin, so get last from ASAP:
        last = self.__asap_queue.get_last()
        return None if last is None else last.unique_id

    def __get_next_call_info(self) -> CallInfo:
        """
        Get next event on queue (i.e. the one that would be returned by pop_next()).
        :return: tuple (event object (added via add_event()), time, priority) or (None, None, None)
        """
        if self.__asap_queue.has_events():
            return self.__asap_queue.get_next()

        if self.__sorted_times_keys:
            time = self.__sorted_times_keys[0]
            time_bin = self.__scheduled_queue[time]
            return time_bin.get_next()[1]

        return None

    def __gen_next_event_id(self) -> int:
        """Generate and return the next event's ID."""
        next_id = self.__next_event_id
        self.__next_event_id += 1
        return next_id
