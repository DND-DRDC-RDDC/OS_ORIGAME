# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the ClockPart class and supporting functionality or the Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import calendar
from datetime import datetime, timedelta

# [2. third-party]
from dateutil.relativedelta import relativedelta

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter, SECONDS_TO_DAYS
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys, OriClockPartKeys as ClkKeys
from ..proto_compat_warn import prototype_compat_method_alias, prototype_compat_property_alias

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
    'ClockPart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    ClockPart = 'ClockPart'


class ClockPart(BasePart):
    """
    This class defines the functionality supported by the Clock Part.

    The clock part supports two independent concepts of time: tick time and calendar time.
    Tick time is computed as tick value * tick period. It starts at 0 and progresses at the same rate as the simulation
    time (provided by the Sim Controller).
    Calendar time is initialized to the local PC's date/time at ClockPart instantiation. It progresses at the same rate
    as the simulation time.

    A ClockPart instance subscribes to Sim Controller sim time update events in order to keep itself in sync.
    """

    class Signals(BridgeEmitter):
        sig_tick_value_changed = BridgeSignal(float)  # number of ticks
        sig_tick_period_days_changed = BridgeSignal(float)  # period(days)
        # year, month, day, hour, minute, second, microsecond
        sig_date_time_changed = BridgeSignal(int, int, int, int, int, int, int)

    DEFAULT_TICK_PERIOD_DAYS = 1.0
    DEFAULT_TICK_VALUE_TICKS = 0.0

    # NOTE: If this value is modified, the clock_part_editor.ui tick spin
    # box sig figs must also be changed
    TICK_SIG_FIGS = 11

    DEFAULT_VISUAL_SIZE = dict(width=7.2, height=4.65)

    USER_CREATABLE = False
    PART_TYPE_NAME = "clock"
    DESCRIPTION = """\
        Use this part to define when delayed signals should be sent.  The code that creates the signal should be linked
        to a clock and to the target function.

        Double-click to set the clock time and date.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: The name assigned to this part instance.
        :param position: A position to be assigned to the newly instantiated default ClockPart. This argument
        is None when the part will be initialized from .ori data using the set_from_ori() function.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = ClockPart.Signals()

        self._tick_period_days = self.DEFAULT_TICK_PERIOD_DAYS
        self._tick_value_ticks = self.DEFAULT_TICK_VALUE_TICKS
        self._date_time = datetime.now()
        self._current_sim_time_days = 0.0
        if parent:
            sim_controller = self.shared_scenario_state.sim_controller
            self._current_sim_time_days = sim_controller.get_sim_time_days()
            sim_controller.signals.sig_sim_time_days_changed.connect(self.__sim_time_days_changed)

        log.warning('Part {} is of deprecated type Clock.', self)

    def get_date_time(self) -> datetime:
        """
        Get the current data/time setting for the clock part.
        """
        return self._date_time

    def set_date_time(self, date_time: datetime):
        """
        Set the current date/time value for the clock part.
        Note: Calling the setter does not cause the associated signal to be raised.
        """
        if self._date_time != date_time:
            self._date_time = date_time
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

    def get_year(self) -> int:
        """
        Get the year portion of the clock's calender date/time.
        Note: This function is consistent with the original prototype's Clock Part API.
        """
        return self._date_time.year

    def set_year(self, new_year: int) -> Decl.ClockPart:
        """
        This function updates the year value in the clock's date/time attribute. If the current day value of the
        current month is out of range as a result of the change, the day value is capped at the maximum day value
        permitted for the year/month combination.
        The sig_date_time_changed signal is emitted if the new date is different from the original.
        Note: This function is consistent with the original prototype's Clock Part API.
        :param new_year: The new year value for the clock part's date/time attribute.
        :return: The updated clock part instance.
        """
        if new_year != self._date_time.year:
            _, max_days = calendar.monthrange(new_year, self.month)
            if self.day > max_days:
                self._date_time = self._date_time.replace(day=max_days)
            self._date_time = self._date_time.replace(year=new_year)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

        return self

    def get_month(self) -> int:
        """
        Get the month portion of the clock's calender date/time.
        Note: This function is consistent with the original prototype's Clock Part API.
        """
        return self._date_time.month

    def set_month(self, new_month: int) -> Decl.ClockPart:
        """
        This function updates the month value in the clock's date/time attribute. If the current day value of the
        current month is out of range as a result of the change, the day value is capped at the maximum day value
        permitted for the year/month combination.
        The sig_date_time_changed signal is emitted if the new date is different from the original.
        Note: This function is consistent with the original prototype's Clock Part API.
        :param new_month: The new month value for the clock part's date/time attribute.
        :return: The updated clock part instance.
        """
        if new_month != self._date_time.month:
            _, max_days = calendar.monthrange(self.year, new_month)
            if self.day > max_days:
                self._date_time = self._date_time.replace(day=max_days)
            self._date_time = self._date_time.replace(month=new_month)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

        return self

    def get_day(self) -> int:
        """
        Get the days portion of the clock's calender date/time.
        Note: This function is consistent with the original prototype's Clock Part API.
        """
        return self._date_time.day

    def set_day(self, new_day: int) -> Decl.ClockPart:
        """
        This function updates the day value in the clock's date/time attribute. If the new day value is out of range
        as a result of the change, the day value is capped at the maximum day value permitted for the year/month
        combination.
        The sig_date_time_changed signal is emitted if the new date is different from the original.
        Note: This function is consistent with the original prototype's Clock Part API.
        :param new_day: The new month value for the clock part's date/time attribute.
        :return: The updated clock part instance.
        """
        if new_day != self._date_time.day:
            _, max_days = calendar.monthrange(self.year, self.month)
            if new_day > max_days:
                log.warning("Attempted to set an invalid day: {}. Corrected: {}. Original value: {}.",
                            new_day, max_days, self._date_time.day)
                new_day = max_days
            self._date_time = self._date_time.replace(day=new_day)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

        return self

    def get_hour(self) -> int:
        """
        Get the hours portion of the clock's calender date/time.
        Note: This function is consistent with the original prototype's Clock Part API.
        """
        return self._date_time.hour

    def set_hour(self, new_hour: int) -> Decl.ClockPart:
        """
        This function updates the hour value of the clock's date/time attribute.
        The sig_date_time_changed signal is emitted if the new date is different from the original.
        Note: This function is consistent with the original prototype's Clock Part API.
        :param new_hour: The new hour value to be set.
        :return: The updated instance of the clock part.
        """
        if new_hour != self._date_time.hour:
            self._date_time = self._date_time.replace(hour=new_hour)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

        return self

    def get_minute(self) -> int:
        """
        Get the minutes portion of the clock's calender date/time.
        Note: This function is consistent with the original prototype's Clock Part API.
        """
        return self._date_time.minute

    def set_minute(self, new_minute: int) -> Decl.ClockPart:
        """
        This function updates the minutes value of the clock's date/time attribute.
        The sig_date_time_changed signal is emitted if the new date is different from the original.
        Note: This function is consistent with the original prototype's Clock Part API.
        :param new_minute: The new minute value to be set.
        :return: The updated instance of the clock part.
        """
        if new_minute != self._date_time.minute:
            self._date_time = self._date_time.replace(minute=new_minute)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

        return self

    def get_second(self) -> int:
        """
        Get the seconds portion of the clock's calender date/time.
        Note: This function is consistent with the original prototype's Clock Part API.
        """
        return self._date_time.second

    def set_second(self, new_second: int) -> Decl.ClockPart:
        """
        This function updates the second value of the clock's date/time attribute.
        The sig_date_time_changed signal is emitted if the new date is different from the original.
        Note: This function is consistent with the original prototype's Clock Part API.
        :param new_second: The new seconds value to be set.
        :return: The updated instance of the clock part.
        """
        if new_second != self._date_time.second:
            self._date_time = self._date_time.replace(second=new_second)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

        return self

    def delay(self, ticks: float = None, years: float = 0, months: float = 0, days: float = 0, hours: float = 0,
              minutes: float = 0,
              seconds: float = 0) -> float:
        """
        This function calculates the simulation time corresponding to the current clock part time adjusted by the
        specified delay and returns the simulation time (in days).
        The time delay should be expressed as either "ticks" or time units (y/m/d/h/m/s).
        :param ticks: A time delay represented as clock "ticks". This value is multiplied by a tick period to establish
            a duration. If 'ticks' is not None, the remaining time values are ignored.
        :param years: The years component of a time delay.
        :param months: The months component of a time delay.
        :param days: The days component of a time delay.
        :param hours: The hours component of a time delay.
        :param minutes: The minutes component of a time delay.
        :param seconds: The seconds component of a time delay.
        :return: The simulation time corresponding to this instance's current time plus the specified time delta.
        """

        if ticks is not None:
            return self.__get_sim_time_after_tick_value_delay(ticks)
        else:  # time delay
            return self.__get_sim_time_after_datetime_delay(years=years, months=months, days=days,
                                                            hours=hours, minutes=minutes, seconds=seconds)

    def set_tick_period_days(self, tick_period_days: float):
        """
        Set the tick period for this instance's tick timer. Modifying the tick period affects the tick value in order
        to maintain the tick time.
        :param tick_period_days: The new period duration in days for a time tick.
        """
        # tt1 = tv1 * tp1
        # tv2 = tv1 * tp1 / tp2

        if self._tick_period_days != tick_period_days:
            tv2 = self._tick_value_ticks * self._tick_period_days / tick_period_days
            self._tick_value_ticks = tv2
            self._tick_period_days = tick_period_days
            if self._anim_mode_shared:
                self.signals.sig_tick_period_days_changed.emit(self._tick_period_days)
                self.signals.sig_tick_value_changed.emit(self._tick_value_ticks)

    def get_tick_period_days(self) -> float:
        """
        This function returns the tick period in days for this instance's tick timer.
        """
        return self._tick_period_days

    def set_tick_value(self, tick_value: float):
        """
        Set the tick value (in # of ticks) for this instance's tick timer. Modification of the tick value does not
        effect the tick period but does affect tick time.
        :param tick_value: The new number of ticks.
        """
        if self._tick_value_ticks != tick_value:
            self._tick_value_ticks = tick_value
            if self._anim_mode_shared:
                self.signals.sig_tick_value_changed.emit(self._tick_value_ticks)

    def get_tick_value(self) -> float:
        """
        This function returns the tick value (the number of "ticks" measured in tick time units (the period)).
        :return: The current tick value of the clock.
        """
        return self._tick_value_ticks

    def __call__(self, ticks_or_year: float,
                 month: float = None, day: float = None, hour: float = None, minute: float = None,
                 second: float = None):
        """
        Returns a simulation time corresponding to the input arguments. The inputs can represent either a
        tick value, or a date/time value.

        :param ticks_or_year: either a tick value (case 1), or a year (case 2; 0 <= year <= 9999).
        :param month: The month component of a date/time value. Range (1-12) inclusive.
        :param day: The day component of a date/time value. Range (1 <= # days <= days in the given month)
        :param hour: The hour component of a date/time value. Range (0 <= hour < 24)
        :param minute: The minute component of a date/time value. Range (0 <= minute < 60)
        :param second: The second component of a date/time value. Range (0 <= minute < 60)

        :return: A simulation time corresponding to the input date/time value.
        :raises ValueError: Raised if one of the input time components is out of range.
        :raises OverflowError: Raised if a time calculation results in a datetime value that is out of range.

        :return: A simulation time corresponding to the input argument(s).
        """
        if month is None:  # tick time provided
            if not (day is None and hour is None and minute is None and second is None):
                raise ValueError("If month is None, then all subsequent args must be None too")
            ticks = ticks_or_year
            return self.__get_sim_time_from_tick_value(ticks)

        else:  # multi-argument date/time - y, m, d, h, m, s provided
            year = ticks_or_year
            return self.__get_sim_time_from_datetime(year=year, month=month, day=day,
                                                     hour=hour, minute=minute, second=second)

    # --------------------------- instance PUBLIC properties ----------------------------

    # Calendar:
    date_time = property(get_date_time, set_date_time)
    year = property(get_year, set_year)
    month = property(get_month, set_month)
    day = property(get_day, set_day)
    hour = property(get_hour, set_hour)
    minute = property(get_minute, set_minute)
    second = property(get_second, set_second)

    # Ticks:
    tick_period_days = property(get_tick_period_days, set_tick_period_days)
    tick_value = property(get_tick_value, set_tick_value)

    # prototype compatibility adjustments:
    get_speed = prototype_compat_method_alias(get_tick_period_days, 'get_speed')
    set_speed = prototype_compat_method_alias(set_tick_period_days, 'set_speed')
    get_time = prototype_compat_method_alias(get_tick_value, 'get_time')
    set_time = prototype_compat_method_alias(set_tick_value, 'set_time')

    Year = prototype_compat_property_alias(year, 'Year')
    Month = prototype_compat_property_alias(month, 'Month')
    Day = prototype_compat_property_alias(day, 'Day')
    Hour = prototype_compat_property_alias(hour, 'Hour')
    Minute = prototype_compat_property_alias(minute, 'Minute')
    Second = prototype_compat_property_alias(second, 'Second')

    Period = prototype_compat_property_alias(tick_period_days, 'Period')
    Time = prototype_compat_property_alias(tick_value, 'Time')

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (date_time, tick_period_days, tick_value)
    META_AUTO_SCRIPTING_API_EXTEND = (
        # calendar:
        date_time, get_date_time, set_date_time,
        year, get_year, set_year,
        month, get_month, set_month,
        day, get_day, set_day,
        hour, get_hour, set_hour,
        minute, get_minute, set_minute,
        second, get_second, set_second,

        # Ticks:
        tick_period_days, get_tick_period_days, set_tick_period_days,
        tick_value, get_tick_value, set_tick_value,

        # both:
        delay,
    )

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        date_time = part_content[ClkKeys.DATE_TIME]
        # Per BasePart._set_from_ori_impl() docstring, set via property.
        self.date_time = datetime(year=date_time[ClkKeys.YEAR],
                                  month=date_time[ClkKeys.MONTH],
                                  day=date_time[ClkKeys.DAY],
                                  hour=date_time[ClkKeys.HOUR],
                                  minute=date_time[ClkKeys.MINUTE],
                                  second=date_time[ClkKeys.SECOND])
        self.tick_period_days = part_content[ClkKeys.PERIOD_DAYS]
        self.tick_value = part_content[ClkKeys.TICKS]

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        clock_ori_def = {
            ClkKeys.DATE_TIME: {
                ClkKeys.YEAR: self._date_time.year,
                ClkKeys.MONTH: self._date_time.month,
                ClkKeys.DAY: self._date_time.day,
                ClkKeys.HOUR: self._date_time.hour,
                ClkKeys.MINUTE: self._date_time.minute,
                ClkKeys.SECOND: self._date_time.second
            },
            ClkKeys.TICKS: self._tick_value_ticks,
            ClkKeys.PERIOD_DAYS: self._tick_period_days
        }

        ori_def[CpKeys.CONTENT].update(clock_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        snapshot.update({
            ClkKeys.YEAR: self._date_time.year,
            ClkKeys.MONTH: self._date_time.month,
            ClkKeys.DAY: self._date_time.day,
            ClkKeys.HOUR: self._date_time.hour,
            ClkKeys.MINUTE: self._date_time.minute,
            ClkKeys.SECOND: self._date_time.second,
            ClkKeys.TICKS: round(self._tick_value_ticks, ClockPart.TICK_SIG_FIGS),
            ClkKeys.PERIOD_DAYS: self._tick_period_days
        })

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __sim_time_days_changed(self, new_sim_time_days: float, sim_time_delta_days: float):
        """
        This function is the signal handler for the SimController sig_sim_time_days_changed event. It computes the
        new tick time parameter (tick value) for this instance based on the simulation time delta announced by the
        Sim Controller and advances the instance's date/time setting accordingly.
        :param new_sim_time_days: The new absolute simulation time according to the Sim Controller.
        :param sim_time_delta_days: The time delta between the new simulation time and the
            previously reported simulation time.
        """

        self._current_sim_time_days = new_sim_time_days

        # Only update the time values if the simulation time 'delta' passed in is greater than zero. A negative
        # delta would indicate a simulation reset and the clock part times don't reset for a sim reset.
        if sim_time_delta_days > 0:
            # Update tick time
            # tt1 = tv1 * tp1
            # tv2 = (tv1 * tp1 + dT) / tp1
            tv1 = self._tick_value_ticks
            tp1 = self._tick_period_days
            tv2 = (tv1 * tp1 + sim_time_delta_days) / tp1
            self._tick_value_ticks = tv2

            # Update date/time
            self._date_time = self._date_time + timedelta(days=sim_time_delta_days)

            if self._anim_mode_shared:
                self.signals.sig_tick_value_changed.emit(self._tick_value_ticks)
                self.signals.sig_date_time_changed.emit(self._date_time.year,
                                                        self._date_time.month,
                                                        self._date_time.day,
                                                        self._date_time.hour,
                                                        self._date_time.minute,
                                                        self._date_time.second,
                                                        self._date_time.microsecond
                                                        )

    def __get_sim_time_after_tick_value_delay(self, tick_value_delay: float):
        """
        This function returns a simulation time corresponding to this instance's tick time adjusted by the specified
        tick value delay.
        :param tick_value_delay:
        :return: The simulation time corresponding to this instance's tick time adjusted by the specified
        tick value delay.
        """
        delay_in_days = tick_value_delay * self._tick_period_days
        return self._current_sim_time_days + delay_in_days

    def __get_sim_time_after_datetime_delay(self, years: float = 0, months: float = 0, days: float = 0,
                                            hours: float = 0, minutes: float = 0, seconds: float = 0):
        """
        This function calculates the simulation time corresponding to this instance's date/time value adjusted by the
        specified time delay.

        The specified delay object's components are converted to a relative delta time, which, when added to the
        clock's datetime value, produce a new time in the future that factors in leap years etc. The clock's current
        datetime value is then subtracted from the new time to yield an absolute time delta (timedelta object), which
        is added (as a value in total days) to the current simulation time to produce the desired result of this
        function.
        :param years: The number of years comprising a delay time.
        :param months: The number of months comprising a delay time.
        :param days: The number of days comprising a delay time.
        :param hours: The number of hours comprising a delay time.
        :param minutes: The number of minutes comprising a delay time.
        :param seconds: The number of seconds comprising a delay time.
        :return: The simulation time that corresponds to the current clock part date/time plus the specified
            delay.
        """
        relative_delta_time = relativedelta(years=years, months=months, days=days,
                                            hours=hours, minutes=minutes, seconds=seconds)
        new_time = self._date_time + relative_delta_time
        absolute_delta = new_time - self._date_time
        return self._current_sim_time_days + absolute_delta.total_seconds() * SECONDS_TO_DAYS

    def __get_sim_time_from_tick_value(self, tick_value: float):
        """
        This function returns the simulation time corresponding to the input tick value.

        The function computes the tick time delta (in days) between this instance's current tick time and that
        calculated using the specified tick value and adds the delta to the current simulation time to produce the
        desired result.
        :param tick_value: The tick value at which the corresponding simulation time is to be calculated.
        :return: The simulation time corresponding to the input tick time.
        """
        tick_time_delta = self._tick_period_days * (tick_value - self._tick_value_ticks)
        return self._current_sim_time_days + tick_time_delta

    def __get_sim_time_from_datetime(self, year: float = 0, month: float = 0, day: float = 0, hour: float = 0,
                                     minute: float = 0,
                                     second: float = 0):
        """
        This function returns the simulation time corresponding to the input date/time value.

        The function computes a date/time delta (in days) between the input time and the instance's current datetime
        value and computes the corresponding simulation time.
        :param year: The year component of a date/time value. Range (1 <= year <= 9999)
        :param month: The month component of a date/time value. Range (1-12) inclusive.
        :param day: The day component of a date/time value. Range (1 <= # days <= days in the given month)
        :param hour: The hour component of a date/time value. Range (0 <= hour < 24)
        :param minute: The minute component of a date/time value. Range (0 <= minute < 60)
        :param second: The second component of a date/time value. Range (0 <= minute < 60)
        :return: A simulation time corresponding to the input date/time value.
        :raises ValueError: Raised if one of the input time components is out of range.
        :raises OverflowError: Raised if a time calculation results in a datetime value that is out of range.
        """
        try:
            new_time = datetime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)
            time_delta = new_time - self._date_time
        except (ValueError, OverflowError) as err:
            log.exception("ClockPart datetime calculation error. Inputs: y({}), m({}), d({}), h({}), m({}), s({}). \
                Error: {}", year, month, day, hour, minute, second, str(err))
            raise err
        return self._current_sim_time_days + (time_delta.total_seconds() * SECONDS_TO_DAYS)


# Add this part to the global part type/class lookup dictionary
register_new_part_type(ClockPart, ClkKeys.PART_TYPE_CLOCK)
