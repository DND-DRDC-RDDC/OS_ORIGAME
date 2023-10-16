# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines constants and conversion factors common to the entire Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

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
    'SECONDS_PER_DAY',
    'MINUTES_PER_DAYS',
    'HOURS_PER_DAYS',
    'SECONDS_TO_DAYS',
    'MINUTES_TO_DAYS',
    'HOURS_TO_DAYS',
]

# Time conversion factors
SECONDS_PER_DAY = 86400.0
MINUTES_PER_DAYS = 1440.0
HOURS_PER_DAYS = 24.0
SECONDS_TO_DAYS = 1.0 / SECONDS_PER_DAY
MINUTES_TO_DAYS = 1.0 / MINUTES_PER_DAYS
HOURS_TO_DAYS = 1.0 / HOURS_PER_DAYS

# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------
