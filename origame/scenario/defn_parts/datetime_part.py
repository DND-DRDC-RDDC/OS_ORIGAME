# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the DateTimePart class that represents date and time.

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

from ..ori import OriCommonPartKeys as CpKeys, OriScenData, JsonObj
from ..ori import OriDateTimePartKeys as DtKeys
from ..ori import IOriSerializable, OriContextEnum

from .base_part import BasePart
from .common import Position
from .actor_part import ActorPart
from .part_types_info import register_new_part_type

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'DateTimePart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class DateTimePart(BasePart):
    """
    The DateTimePart contains date and time information. They are kept in sync with the Event Queue.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    class Signals(BridgeEmitter):
        # year, month, day, hour, minute, second, microsecond
        sig_date_time_changed = BridgeSignal(int, int, int, int, int, int, int)

    DEFAULT_VISUAL_SIZE = dict(width=6.2, height=3.1)

    PART_TYPE_NAME = "datetime"
    DESCRIPTION = """\
        Use this part to define when delayed signals should be sent.  The code that creates the signal should be linked
        to a datetime part and to the target function.

        Double-click to set the part's time and date.
    """

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: The name assigned to this part instance.
        :param position: A position to be assigned to the newly instantiated default DateTimePart. This argument
        is None when the part will be initialized from .ori data using the set_from_ori() function.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = DateTimePart.Signals()

        self.__date_time = datetime.now()
        self.__current_sim_time_days = 0.0
        if parent:
            sim_controller = self.shared_scenario_state.sim_controller
            sim_controller.signals.sig_sim_time_days_changed.connect(self.__sim_time_days_changed)

    def get_date_time(self) -> datetime:
        """
        Get the current data/time setting for the part.
        """
        return self.__date_time

    def set_date_time(self, date_time: datetime):
        """
        Set the current date/time value for the part.
        Note: Calling the setter does not cause the associated signal to be raised.
        """
        if self.__date_time != date_time:
            self.__date_time = date_time
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )

    def get_year(self) -> int:
        """
        Get the year portion of the date/time.
        """
        return self.__date_time.year

    def set_year(self, new_year: int):
        """
        This function updates the year value in the date/time attribute. If the current day value of the
        current month is out of range as a result of the change, the day value is capped at the maximum day value
        permitted for the year/month combination.
        The sig_date_time_changed signal is emitted if the new date is different from the original.

        :param new_year: The new year value for the part's date/time attribute.
        """
        if new_year != self.__date_time.year:
            _, max_days = calendar.monthrange(new_year, self.month)
            if self.day > max_days:
                self.__date_time = self.__date_time.replace(day=max_days)
            self.__date_time = self.__date_time.replace(year=new_year)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )

    def get_month(self) -> int:
        """
        Get the month portion of the date/time.
        """
        return self.__date_time.month

    def set_month(self, new_month: int):
        """
        This function updates the month value in the date/time attribute. If the current day value of the
        current month is out of range as a result of the change, the day value is capped at the maximum day value
        permitted for the year/month combination.
        The sig_date_time_changed signal is emitted if the new date is different from the original.

        :param new_month: The new month value for the part's date/time attribute.
        """
        if new_month != self.__date_time.month:
            _, max_days = calendar.monthrange(self.year, new_month)
            if self.day > max_days:
                self.__date_time = self.__date_time.replace(day=max_days)
            self.__date_time = self.__date_time.replace(month=new_month)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )

    def get_day(self) -> int:
        """
        Get the days portion of the date/time.
        """
        return self.__date_time.day

    def set_day(self, new_day: int):
        """
        This function updates the day value in the date/time attribute. If the new day value is out of range
        as a result of the change, the day value is capped at the maximum day value permitted for the year/month
        combination.
        The sig_date_time_changed signal is emitted if the new date is different from the original.

        :param new_day: The new month value for the date/time attribute.
        """
        if new_day != self.__date_time.day:
            _, max_days = calendar.monthrange(self.year, self.month)
            if new_day > max_days:
                log.warning("Attempted to set an invalid day: {}. Corrected: {}. Original value: {}.",
                            new_day, max_days, self.__date_time.day)
                new_day = max_days
            self.__date_time = self.__date_time.replace(day=new_day)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )

    def get_hour(self) -> int:
        """
        Get the hours portion of the date/time.
        """
        return self.__date_time.hour

    def set_hour(self, new_hour: int):
        """
        This function updates the hour value of the date/time attribute.
        The sig_date_time_changed signal is emitted if the new date is different from the original.

        :param new_hour: The new hour value to be set.
        """
        if new_hour != self.__date_time.hour:
            self.__date_time = self.__date_time.replace(hour=new_hour)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )

    def get_minute(self) -> int:
        """
        Get the minutes portion of the date/time.
        """
        return self.__date_time.minute

    def set_minute(self, new_minute: int):
        """
        This function updates the minutes value of the date/time attribute.
        The sig_date_time_changed signal is emitted if the new date is different from the original.

        :param new_minute: The new minute value to be set.
        """
        if new_minute != self.__date_time.minute:
            self.__date_time = self.__date_time.replace(minute=new_minute)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )

    def get_second(self) -> int:
        """
        Get the seconds portion of the date/time.
        """
        return self.__date_time.second

    def set_second(self, new_second: int):
        """
        This function updates the second value of the date/time attribute.
        The sig_date_time_changed signal is emitted if the new date is different from the original.

        :param new_second: The new seconds value to be set.
        """
        if new_second != self.__date_time.second:
            self.__date_time = self.__date_time.replace(second=new_second)
            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )

    def delay(self,
              years: float = 0,
              months: float = 0,
              days: float = 0,
              hours: float = 0,
              minutes: float = 0,
              seconds: float = 0) -> float:
        """
        This function calculates the simulation time corresponding to the current datetime part time adjusted by the
        specified delay and returns the simulation time (in days).

        :param years: The years component of a time delay.
        :param months: The months component of a time delay.
        :param days: The days component of a time delay.
        :param hours: The hours component of a time delay.
        :param minutes: The minutes component of a time delay.
        :param seconds: The seconds component of a time delay.
        :return: The simulation time corresponding to this instance's current time plus the specified time delta.
        """
        relative_delta_time = relativedelta(years=years, months=months, days=days,
                                            hours=hours, minutes=minutes, seconds=seconds)
        # A technique to convert a delta to days. The relativedelta is handy when we want to pass all the date time
        # components, but it does not have total_seconds() or total_days() information. The timedelta cannot take
        # all the date time components but it has total_seconds(). So, we do this:
        new_time = self.__date_time + relative_delta_time
        duration_in_timedelta = new_time - self.__date_time
        return self.__current_sim_time_days + duration_in_timedelta.total_seconds() * SECONDS_TO_DAYS

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    date_time = property(get_date_time, set_date_time)
    year = property(get_year, set_year)
    month = property(get_month, set_month)
    day = property(get_day, set_day)
    hour = property(get_hour, set_hour)
    minute = property(get_minute, set_minute)
    second = property(get_second, set_second)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (date_time,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        date_time, get_date_time, set_date_time,
        year, get_year, set_year,
        month, get_month, set_month,
        day, get_day, set_day,
        hour, get_hour, set_hour,
        minute, get_minute, set_minute,
        second, get_second, set_second,

        delay,
    )

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    def __call__(self, year: float = 0, month: float = 0, day: float = 0, hour: float = 0, minute: float = 0,
                 second: float = 0):
        """
        Returns a simulation time corresponding to the input arguments.

        :param year: The year (0 <= year <= 9999).
        :param month: The month component of a date/time value. Range (1-12) inclusive.
        :param day: The day component of a date/time value. Range (1 <= # days <= days in the given month)
        :param hour: The hour component of a date/time value. Range (0 <= hour < 24)
        :param minute: The minute component of a date/time value. Range (0 <= minute < 60)
        :param second: The second component of a date/time value. Range (0 <= second < 60)

        :raises ValueError: Raised if one of the input time components is out of range.
        :raises OverflowError: Raised if a time calculation results in a datetime value that is out of range.

        :return: A simulation time corresponding to the input argument(s).
        """
        try:
            new_time = datetime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)
            time_delta = new_time - self.__date_time
        except (ValueError, OverflowError) as err:
            log.exception("DateTimePart datetime calculation error. Inputs: y({}), m({}), d({}), h({}), m({}), s({}). \
                Error: {}", year, month, day, hour, minute, second, str(err))
            raise err
        return self.__current_sim_time_days + (time_delta.total_seconds() * SECONDS_TO_DAYS)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        date_time = part_content[DtKeys.DATE_TIME]
        # Per BasePart._set_from_ori_impl() docstring, set via property.
        self.date_time = datetime(year=date_time[DtKeys.YEAR],
                                  month=date_time[DtKeys.MONTH],
                                  day=date_time[DtKeys.DAY],
                                  hour=date_time[DtKeys.HOUR],
                                  minute=date_time[DtKeys.MINUTE],
                                  second=date_time[DtKeys.SECOND])

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:

        #2017-10-31 DRWA BUG FIX
        #Fix issue where loaded datetime part has different time than when saved

        delta = self.__date_time - timedelta(days = self.__current_sim_time_days)

        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        datetime_ori_def = {
            DtKeys.DATE_TIME: {
                DtKeys.YEAR: delta .year,
                DtKeys.MONTH: delta .month,
                DtKeys.DAY: delta .day,
                DtKeys.HOUR: delta .hour,
                DtKeys.MINUTE: delta .minute,
                DtKeys.SECOND: delta .second
            }
        }

        ori_def[CpKeys.CONTENT].update(datetime_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        snapshot.update({
            DtKeys.YEAR: self.__date_time.year,
            DtKeys.MONTH: self.__date_time.month,
            DtKeys.DAY: self.__date_time.day,
            DtKeys.HOUR: self.__date_time.hour,
            DtKeys.MINUTE: self.__date_time.minute,
            DtKeys.SECOND: self.__date_time.second
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

        # Only update the time values if the simulation time 'delta' passed in is greater than zero. A negative
        # delta would indicate a simulation reset and the part times don't reset for a sim reset.
        if sim_time_delta_days > 0:
            # Update date/time
            self.__date_time = self.__date_time + timedelta(days=sim_time_delta_days)

            if self._anim_mode_shared:
                self.signals.sig_date_time_changed.emit(self.__date_time.year,
                                                        self.__date_time.month,
                                                        self.__date_time.day,
                                                        self.__date_time.hour,
                                                        self.__date_time.minute,
                                                        self.__date_time.second,
                                                        self.__date_time.microsecond
                                                        )


# Add this part to the global part type/class lookup dictionary
register_new_part_type(DateTimePart, DtKeys.PART_TYPE_DATETIME)
