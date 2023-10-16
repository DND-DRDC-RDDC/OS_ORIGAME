# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the PulsePart class.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum, unique

# [2. third-party]

# [3. local]
from ...core import override, BridgeEmitter, BridgeSignal
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ..part_execs.iexecutable_part import IExecutablePart
from ..sim_controller import SimStatesEnum
from ..event_queue import EventQueue
from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriPulsePartKeys as PpKeys

from .base_part import BasePart
from .common import Position
from .part_link import PartLink
from .part_types_info import register_new_part_type
from .actor_part import ActorPart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PulsePart',
    'PulsePartState'
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

@unique
class PulsePartState(IntEnum):
    """
    This class represents the state of the pulse part.
    """
    inactive, active = range(2)


class PulsePart(BasePart, IExecutablePart):
    """
    This class defines the functionality supported by the Pulse Part.

    Pulse parts can be used to place events on the event queue at regular periods. The pulse part
    defines a pulse period, state, and priority. When a scenario is started, the sim controller
    adds all 'active' pulse parts to the Event Queue at time zero and with the priority defined
    in the pulse part. When the pulse event executes, an event corresponding to each part linked
    to the pulse will be added to the queue at ASAP priority. Each of those events then trigger
    execution of their respective parts. The pulse also adds a new event to the queue
    corresponding to the next pulse.

    A PulsePart instance subscribes to Sim Controller sim time update events in order to keep
    itself in sync.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    class PulseSignals(BridgeEmitter):
        sig_pulse_period_days_changed = BridgeSignal(float)
        sig_state_changed = BridgeSignal(int)
        sig_priority_changed = BridgeSignal(float)

    DEFAULT_PULSE_PERIOD_DAYS = 1.0
    DEFAULT_STATE = PulsePartState.active
    DEFAULT_PRIORITY = EventQueue.MAX_SCHED_PRIORITY

    CAN_BE_LINK_SOURCE = True
    DEFAULT_VISUAL_SIZE = dict(width=7.2, height=4.0)
    PART_TYPE_NAME = "pulse"
    DESCRIPTION = """\
        Use the Pulse Part to cause events to execute at regular intervals.

        Double-click to set the pulse period, state, and priority.
        """

    # --------------------------- class-wide methods --------------------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: The name assigned to this part instance.
        :param position: A position to be assigned to the newly instantiated default Pulse Part. This argument
            is None when the part will be initialized from .ori data using the set_from_ori() function.
        """
        IExecutablePart.__init__(self)
        BasePart.__init__(self, parent, name=name, position=position)

        self.signals = self.PulseSignals()

        # Default attributes
        self.__pulse_period_days = self.DEFAULT_PULSE_PERIOD_DAYS
        self.__state = self.DEFAULT_STATE
        self.__priority = self.DEFAULT_PRIORITY

        # Link attributes
        self.__linking_changed = False
        self.__sorted_outgoing_links = []

        # Event Queue parameters
        self.__time_on_queue_days = None
        self.__call_info = None

        # Sim controller
        if self._shared_scenario_state:
            self.__sim_controller = self._shared_scenario_state.sim_controller
            self.__sim_controller.register_pulse_part(self)
        else:
            self.__sim_controller = None

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    @override(BasePart)
    def on_removing_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        BasePart.on_removing_from_scenario(self, scen_data, restorable=restorable)
        self.__sim_controller.unregister_pulse_part(self)
        IExecutablePart.on_removed_from_scenario(self, scen_data, restorable=restorable)

    @override(BasePart)
    def on_restored_to_scenario(self, scen_data: Dict[BasePart, Any]):
        BasePart.on_restored_to_scenario(self, scen_data)
        self.__sim_controller.register_pulse_part(self)
        IExecutablePart.on_restored_to_scenario(self, scen_data)

    @override(BasePart)
    def on_outgoing_link_added(self, link: PartLink):
        """
        This type of part calls target part of each link, but order of links is not guaranteed by the part frame
        *across separate application runs* (see discussions about PYTHONHASHSEED). The trick is to sort the
        links by name; this works because the names are guaranteed unique. This method allows the sorting to
        occur only the first time called and when linking has changed.
        """
        self.__linking_changed = True

    @override(BasePart)
    def on_outgoing_link_removed(self, link: PartLink):
        """See docstring for PulsePart.on_outgoing_link_added()."""
        self.__linking_changed = True

    def set_pulse_period_days(self, pulse_period_days: float):
        """
        Set the pulse period for this instance's tick timer.
        :param pulse_period_days: The new period duration in days.
        """
        if self.__pulse_period_days != pulse_period_days:
            self.__pulse_period_days = pulse_period_days
            if self._anim_mode_shared:
                self.signals.sig_pulse_period_days_changed.emit(pulse_period_days)

    def get_pulse_period_days(self) -> float:
        """
        This function returns the pulse period in days.
        """
        return self.__pulse_period_days

    def set_state(self, state: PulsePartState):
        """
        Sets the pulse part to a new state.
        """
        if state != self.__state:
            self.__state = state
            self.init_pulse_event()

            if self._anim_mode_shared:
                self.signals.sig_state_changed.emit(state.value)

    def get_state(self) -> PulsePartState:
        """
        Gets the current pulse part state.
        """
        return self.__state

    def set_priority(self, priority: float):
        """
        Sets the pulse part to a new priority.
        """
        if priority != self.__priority:
            self.__priority = priority
            if self._anim_mode_shared:
                self.signals.sig_priority_changed.emit(priority)

    def get_priority(self) -> float:
        """
        Gets the current pulse part priority.
        """
        return self.__priority

    def init_pulse_event(self, use_pulse_period: bool = False):
        """
        Add or remove this pulse part to/from the event queue.

        :param use_pulse_period: a flag that indicates if the next pulse event should occur at sim time + pulse period.
        """

        # Can add an event if running or paused (i.e. during a 'step' while paused)
        if self.__sim_controller.state_id in (SimStatesEnum.running, SimStatesEnum.paused):
            if not self.is_queued and self.__state == PulsePartState.active:

                self.__time_on_queue_days = self.__sim_controller.sim_time_days
                if use_pulse_period:
                    self.__time_on_queue_days += self.pulse_period_days

                self.__call_info = self.__sim_controller.add_event(self,
                                                                   time=self.__time_on_queue_days,
                                                                   priority=self.priority)
                assert self.is_queued

            elif self.is_queued and self.__state == PulsePartState.inactive:

                self.__sim_controller.remove_event(time=self.__time_on_queue_days,
                                                   priority=self.priority,
                                                   call_info=self.__call_info,
                                                   restorable=True)
                assert not self.is_queued

            else:
                # Do nothing: pulse is either already on the queue and 'active',
                # or off the queue and 'inactive'
                pass

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    pulse_period_days = property(get_pulse_period_days, set_pulse_period_days)
    state = property(get_state, set_state)
    priority = property(get_priority, set_priority)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (
        pulse_period_days,
        state,
        priority
    )
    META_AUTO_SCRIPTING_API_EXTEND = (
        pulse_period_days, get_pulse_period_days, set_pulse_period_days,
        state, get_state, set_state,
        priority, get_priority, set_priority
    )
    META_SCRIPTING_CONSTANTS = (PulsePartState,)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        self.pulse_period_days = part_content[PpKeys.PERIOD]
        self.state = PulsePartState(part_content[PpKeys.STATE])
        self.priority = part_content[PpKeys.PRIORITY]

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:

        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        pulse_ori_def = {
            PpKeys.PERIOD: self.__pulse_period_days,
            PpKeys.STATE: self.__state,
            PpKeys.PRIORITY: self.__priority
        }

        ori_def[CpKeys.CONTENT].update(pulse_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)

        snapshot.update({
            PpKeys.PERIOD: self.__pulse_period_days,
            PpKeys.STATE: self.__state,
            PpKeys.PRIORITY: self.__priority,
        })

    @override(IExecutablePart)
    def _exec(self, _debug_mode: bool, _as_signal: bool, *args, **kwargs):
        """
        Define how to "execute" this pulse part.

        :param args: the required (positional) arguments to give to _exec()
        :param kwargs: the optional (named) arguments to give to _exec()
        :param _debug_mode: an "internal" flag that is set by the caller to indicate debug mode (True
            if want to stop at next breakpoint)
        :param _as_signal: an "internal" flag that is set by the caller to indicate whether called normal or as signal
        """

        if self.__linking_changed:
            # need to re-sort the links; use name since this is the only repeatable keys (session IDs are not)
            self.__sorted_outgoing_links = list(self.part_frame.get_outgoing_links())
            self.__sorted_outgoing_links.sort(key=lambda x: x.name)
            self.__linking_changed = False

        if _as_signal:

            # Pulse event popped
            assert not self.is_queued

            # Signal all parts pointed at by outgoing links.
            for link in self.__sorted_outgoing_links:
                part = link.target_part_frame.part.get_as_link_target_part()
                if part is not None:
                    self.__sim_controller.add_event(iexec_part=part, args=args,
                                                    priority=EventQueue.ASAP_PRIORITY_VALUE)
                else:
                    log.warning("Resolved link target from {} is None, used by pulse {}: can't signal",
                                link.target_part_frame.part, self)

            # Put pulse event back on queue at next pulse
            self.init_pulse_event(use_pulse_period=True)

        else:
            # Do not respond to calls - prevents users from putting pulse on event queue more than once.
            pass


# Add this part to the global part type/class lookup dictionary
register_new_part_type(PulsePart, PpKeys.PART_TYPE_PULSE)
