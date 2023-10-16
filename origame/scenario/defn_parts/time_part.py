# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the TimePart class that represents the elapsed time since the part
is last reset.

Note: the elapsed_time API for time part cannot use relativedelta because this object is not hashable, thus
preventing the creation of "timestamp" maps. Since relativedelta is also pure-python it is much slower than
timedelta, and its API is significantly broader than necessary, even prone to errors (e.g. it has both a year
and a years attribute, with very different impact on the object). In the future, a custom class ElapsedTime
should be created, deriving from timedelta, and providing weeks/hours/minutes properties while retaining
the nice features of timedelta.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from datetime import timedelta

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter, HOURS_TO_DAYS, MINUTES_TO_DAYS, SECONDS_TO_DAYS
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.utils import timedelta_to_rel

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriTimePartKeys as TiKeys

from .base_part import BasePart
from .actor_part import ActorPart
from .common import Position
from .part_types_info import register_new_part_type

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'TimePart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class TimePart(BasePart):
    """
    The TimePart represents the elapsed time since the part is last reset. The elapsed time is adjusted only when
    the state of the part is active.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    class Signals(BridgeEmitter):
        sig_elapsed_time_changed = BridgeSignal(float, float, float, int)  # days, hours, minutes and seconds

    DEFAULT_VISUAL_SIZE = dict(width=6.2, height=3.4)
    PART_TYPE_NAME = "time"
    DESCRIPTION = """\
        Use this part to track the elapsed time.

        Double-click to edit the part.
    """

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: The name assigned to this part instance.
        :param position: A position to be assigned to the newly instantiated default TimePart. This argument
        is None when the part will be initialized from .ori data using the set_from_ori() function.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = TimePart.Signals()

        self.__elapsed_time = timedelta()
        self.__current_sim_time_days = 0.0

        if parent:
            sim_controller = self.shared_scenario_state.sim_controller
            sim_controller.signals.sig_sim_time_days_changed.connect(self.__sim_time_days_changed)

    def get_elapsed_time(self) -> timedelta:
        """
        Get how much time has elapsed (in days) since this part was created or last reset (whichever is
        most recent event). The return value is a timedelta, which expresses elapsed time in terms of days, seconds
        and micro-seconds. In order to get hours, minutes, weeks etc, the caller can use relativedelta,
        or one of the timedelta <-> relativedelta conversion functions.
        """
        return self.__elapsed_time

    def set_elapsed_time(self, elapsed_time: timedelta):
        """
        Sets the elapsed time of the time part. Sends the sig_elapsed_time_changed signal if the set value is different
        from the current value.
        :param elapsed_time:
        """
        if self.__elapsed_time != elapsed_time:
            delta = timedelta_to_rel(elapsed_time)
            self.__elapsed_time = timedelta(days=delta.days, hours=delta.hours, minutes=delta.minutes,
                                            seconds=delta.seconds, microseconds=delta.microseconds)
            if self._anim_mode_shared:
                self.signals.sig_elapsed_time_changed.emit(delta.days,
                                                           delta.hours,
                                                           delta.minutes,
                                                           delta.seconds)

    def reset(self):
        """
        Sets the elapsed time to zero. It is equivalent to self.set_elapsed_time(timedelta()).
        """
        zero_val = timedelta()
        if self.__elapsed_time != zero_val:
            self.__elapsed_time = zero_val
            if self._anim_mode_shared:
                self.signals.sig_elapsed_time_changed.emit(0, 0, 0, 0)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    elapsed_time = property(get_elapsed_time, set_elapsed_time)

    # --------------------------- CLASS META data for public API ------------------------
    META_AUTO_EDITING_API_EXTEND = (elapsed_time,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        elapsed_time, reset,
    )

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    def __call__(self, weeks: float = 0, days: float = 0, hours: float = 0, minutes: float = 0, seconds: float = 0):
        """
        Returns a simulation time corresponding to the input arguments.

        :param weeks: The week component of an elapsed time
        :param days: The day component of an elapsed time
        :param hours: The hour component of an elapsed time
        :param minutes: The minute component of an elapsed time
        :param seconds: The second component of an elapsed time

        :return: A simulation time corresponding to the input argument(s).
        """
        delta = (timedelta(weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds) -
                 self.__elapsed_time)
        delta_in_days = delta.total_seconds() * SECONDS_TO_DAYS

        return self.__current_sim_time_days + delta_in_days

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        days = part_content.get(TiKeys.DAYS, 0)
        hours = part_content.get(TiKeys.HOURS, 0)
        minutes = part_content.get(TiKeys.MINUTES, 0)
        seconds = part_content.get(TiKeys.SECONDS, 0)

        self.elapsed_time = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:

        #2017-10-31 DRWA BUG FIX
        #Fix issue where loaded time part has different time than when saved

        delta = timedelta_to_rel(self.__elapsed_time)

        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        time_ori_def = {
            TiKeys.DAYS: delta.days - self.__current_sim_time_days,
            TiKeys.HOURS: delta.hours,
            TiKeys.MINUTES: delta.minutes,
            TiKeys.SECONDS: delta.seconds
        }

        ori_def[CpKeys.CONTENT].update(time_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        delta = timedelta_to_rel(self.__elapsed_time)
        snapshot.update({
            TiKeys.DAYS: delta.days,
            TiKeys.HOURS: delta.hours,
            TiKeys.MINUTES: delta.minutes,
            TiKeys.SECONDS: delta.seconds
        })

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __sim_time_days_changed(self, new_sim_time_days: float, sim_time_delta_days: float):
        """
        This function is the signal handler for the SimController sig_sim_time_days_changed event.
        :param new_sim_time_days: The new absolute simulation time according to the Sim Controller.
        :param sim_time_delta_days: The time delta between the new simulation time and the
            previously reported simulation time.
        """

        self.__current_sim_time_days = new_sim_time_days


        # Only update the value if the simulation time 'delta' passed in is greater than zero. A negative
        # delta would indicate a simulation reset and the part doesn't reset for a sim reset.
        if sim_time_delta_days > 0:
            self.__elapsed_time += timedelta(days=sim_time_delta_days)

            if self._anim_mode_shared:
                delta = timedelta_to_rel(self.__elapsed_time)
                self.signals.sig_elapsed_time_changed.emit(delta.days,
                                                           delta.hours,
                                                           delta.minutes,
                                                           delta.seconds)


# Add this part to the global part type/class lookup dictionary
register_new_part_type(TimePart, TiKeys.PART_TYPE_TIME)
