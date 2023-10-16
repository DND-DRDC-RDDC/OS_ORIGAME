# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Implements a base class for any class that implements a scenario object.

Scenario objects currently include BasePart, PartLink, and LinkWaypoint.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum, unique

# [2. third-party]

# [3. local]


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ScenarioObject'
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

@unique
class ScenarioObjectType(IntEnum):
    """
    This class represents the scenario object types.
    """
    part, link, waypoint = range(3)


class ScenarioObject:
    """
    Implements an object that can be created inside a scenario. Derived classes must override the
    object type ID with one of the ScenarioObjectType enum values.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # Must be set by the child class
    SCENARIO_OBJECT_TYPE = None
