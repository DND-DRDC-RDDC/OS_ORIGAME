# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module is used to do conversions such as hours per day, etc.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import datetime, math, re

# [2. third-party]
from PyQt5.QtGui import QColor
from PyQt5.QtCore import QPointF

# [3. local]
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..scenario.defn_parts import Position

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 7146 $"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

# It is pointless to have an _all_ for this module since everything is public
# Prefix non-public things with _


log = logging.getLogger('system')

HOURS_PER_DAY = 24
MINUTES_PER_DAY = 1440
SECONDS_PER_WEEK = 604800
SECONDS_PER_DAY = 86400
SECONDS_PER_HOUR = 3600
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60

# To convert between scenario coordinates and scene coordinates
# For now, by observations, the prototype width = 10 is displayed in 336 px, the height = 10 in 359 px.
# That means an object (10 x 10) in the prototype database is not displayed as a square. In the Origame, we
# display it as a square. Thus,
SCALE_FACTOR = 33.6


# -- Function definitions -----------------------------------------------------------------------


def convert_qcolor_to_hex(q_color: QColor) -> str:
    """
    Accessory helper to convert a QColor to hexadecimal.

    This can be used in setting colors inside stylesheets.

    :param q_color: The color to convert into hexadecimal.
    :return: A hexadecimal representation of q_color.
    """
    return '#%02x%02x%02x' % (q_color.red(), q_color.green(), q_color.blue())


def convert_float_days_to_string(days_as_float: float) -> str:
    """
    :param days_as_float:  A floating point number in days.
    :return: A string representation in days in the format dddd hh:mm:ss.
    """
    if days_as_float is None:
        return ""

    time_delta = datetime.timedelta(days=days_as_float)
    hours, minutes = divmod(time_delta.seconds / MINUTES_PER_HOUR, SECONDS_PER_MINUTE)
    seconds = (minutes - math.floor(minutes)) * SECONDS_PER_MINUTE

    time_str = '{:04} {:02}:{:02}:{:02}'.format(time_delta.days, int(hours), math.floor(minutes), round(seconds))

    return time_str


def convert_days_to_time_components(days_as_float: float) -> Tuple[int, int, int, int]:
    """
    :param days_as_float:  A floating point number in days.
    :return: integer days, hours, minutes, seconds.
    """
    if days_as_float is None:
        return ""

    time_delta = datetime.timedelta(days=days_as_float)
    hours, minutes = divmod(time_delta.seconds / MINUTES_PER_HOUR, SECONDS_PER_MINUTE)
    seconds = (minutes - math.floor(minutes)) * SECONDS_PER_MINUTE

    return time_delta.days, int(hours), math.floor(minutes), round(seconds)


def convert_seconds_to_string(seconds: int) -> str:
    """
    :param seconds:  An integer number in seconds.
    :return: A string representation in days in the format dddd hh:mm:ss.
    """
    if seconds is None:
        return ""

    days, _ = divmod(seconds, SECONDS_PER_DAY)
    hours, remainder = divmod(seconds, SECONDS_PER_HOUR)
    minutes, seconds = divmod(remainder, SECONDS_PER_MINUTE)

    time_str = '{:04} {:02}:{:02}:{:02}'.format(days, hours % HOURS_PER_DAY, minutes % MINUTES_PER_HOUR,
                                                seconds % SECONDS_PER_MINUTE)

    return time_str


def get_time_components_as_float(time: str) -> float:
    """
    This method is used to get individual time components given a string in the
    format 'dddd hh:mm:ss'.  Here are some examples of inputs and outputs:

     Input                          Output

    12 15:32:02  -> days=12.0, hours=15.0, minutes=35.0, seconds=2.0
    11           -> days=11.0, hours=0.0, minutes=0.0, seconds=0.0
    11 05        -> days=11.0, hours=5.0, minutes=0.0, seconds=0.0
    11 05:02     -> days=11.0, hours=5.0, minutes=2.0, seconds=0.0
    11 05:02:09  -> days=11.0, hours=5.0, minutes=2.0, seconds=9.0

    :param time: The time to get the components for.  Supported formats include dddd hh:mm:ss,
        dddd, dddd hh, and dddd hh:mm
    :return: Individual time components as days, hours, minutes and seconds.
    """

    pattern = re.compile(r'^(\d{0,4})\s?(\d{0,2}):?(\d{0,2}):?(\d{0,2})')
    matcher = pattern.match(time)

    days = 0.0
    hours = 0.0
    minutes = 0.0
    seconds = 0.0

    if matcher.groups()[0] != "":
        days = float(matcher.groups()[0])
    if matcher.groups()[1] != "":
        hours = float(matcher.groups()[1])
    if matcher.groups()[2] != "":
        minutes = float(matcher.groups()[2])
    if matcher.groups()[3] != "":
        seconds = float(matcher.groups()[3])

    return days, hours, minutes, seconds


def convert_string_into_seconds(time: str) -> int:
    """
    Convert a string in the format 'dddd hh:mm:ss' to an int in seconds.
    :param time: The string to convert.
    :return: Total number of strings represented in the 'time' variable.
    """
    if not time:
        return None

    days, hours, minutes, seconds = get_time_components_as_float(time)
    total = days * SECONDS_PER_DAY + hours * MINUTES_PER_HOUR * SECONDS_PER_MINUTE + minutes * SECONDS_PER_MINUTE + seconds

    return int(total)


def convert_string_to_float(time: str) -> float:
    """
    :param time:  A string time represented as dddd hh:mm:ss.
    :return: A floating point integer of the string in days.
    """
    if not time:
        return None

    days, hours, minutes, seconds = get_time_components_as_float(time)

    total_days = convert_time_components_to_days(days, hours, minutes, seconds)

    return total_days


def convert_time_components_to_days(days: float, hours: float, minutes: float, seconds: float) -> float:
    """
    Calculates the total time in days form the inputs.
    :param days: floating point number of days.
    :param hours: floating point number of hours
    :param minutes: floating point number of minutes
    :param seconds: floating point number of seconds
    :return: floating point number of total days.
    """

    total_days = (days +
                  float(hours / HOURS_PER_DAY) +
                  float(minutes / MINUTES_PER_DAY) +
                  float(seconds / SECONDS_PER_DAY))

    return total_days


def convert_float_days_to_tick_period(days_as_float: float) -> str:
    """
    Convert days to a string whose format satisfies the requirements of the Clock Part.

    The returned string shall have the format as follows:

    [x Day(s), ][y Hour(s), ][a Minute(s), ][b Second(s)]

    :param float days_as_float: A positive float number representing days.
    :returns: A format string of the days.
    """

    total_sec = datetime.timedelta(days=days_as_float).total_seconds()

    period_str = ""

    # Day(s)
    day, total_sec = divmod(total_sec, SECONDS_PER_DAY)
    if 0 < day < 2:
        period_str += str(int(day)) + " Day"
        comma = ", "
    elif day >= 2:
        period_str += str(int(day)) + " Days"
        comma = ", "
    else:
        comma = ""

    # Hour(s)
    hour, total_sec = divmod(total_sec, SECONDS_PER_HOUR)
    if 0 < hour < 2:
        period_str += comma + str(int(hour)) + " Hour"
        comma = ", "
    elif hour >= 2:
        period_str += comma + str(int(hour)) + " Hours"
        comma = ", "

    # Minute(s)
    minute, total_sec = divmod(total_sec, SECONDS_PER_MINUTE)
    if 0 < minute < 2:
        period_str += comma + str(int(minute)) + " Minute"
        comma = ", "
    elif minute >= 2:
        period_str += comma + str(int(minute)) + " Minutes"
        comma = ", "

    # Second(s)
    total_sec = round(total_sec)
    if 0 < total_sec < 2:
        period_str += comma + str(int(total_sec)) + " Second"
    elif total_sec >= 2:
        period_str += comma + str(int(total_sec)) + " Seconds"

    return period_str


def convert_float_days_to_tick_period_tuple(days_as_float: float) -> Tuple[int, int, int, int]:
    """
    Convert days to a tuple of days, hours, minutes, and seconds.

    The returned tuple has five values: days, hours, minutes, and seconds.

    :param float days_as_float: A positive float number representing days.
    :returns: A tuple of days, hours, minutes, and seconds.
    """

    total_sec = datetime.timedelta(days=days_as_float).total_seconds()

    returned_values = list()

    # Day(s)
    day, total_sec = divmod(total_sec, SECONDS_PER_DAY)
    returned_values.append(int(day))

    # Hour(s)
    hour, total_sec = divmod(total_sec, SECONDS_PER_HOUR)
    returned_values.append(int(hour))

    # Minute(s)
    minute, total_sec = divmod(total_sec, SECONDS_PER_MINUTE)
    returned_values.append(int(minute))

    # Second(s)
    total_sec = round(total_sec)
    returned_values.append(int(total_sec))

    return tuple(returned_values)


# QGraphicsScene coordinates have an X-Y plane with y-positive down.
# Map QGraphicsScene minus-y-coordinates to ORIGMAE

def map_to_scenario(pointf: QPointF) -> Position:
    """
    :param pointf: a QPointF in 2D Scene coordinates,
    :return: a Position in scenario coordinates with Y positive up (Qt scene default is Y positive down).
    """
    global SCALE_FACTOR
    return Position(pointf.x() / SCALE_FACTOR, -1.0 * pointf.y() / SCALE_FACTOR)


def map_from_scenario(position: Position) -> QPointF:
    """
    :param position: A position in scenario coordinates
    :return: a 2-D QPointF in scene coordinates, ignoring the z value.
    """
    global SCALE_FACTOR
    return QPointF(position.x * SCALE_FACTOR, -1.0 * position.y * SCALE_FACTOR)  # invert Y to positive up

# -- Class Definitions --------------------------------------------------------------------------
