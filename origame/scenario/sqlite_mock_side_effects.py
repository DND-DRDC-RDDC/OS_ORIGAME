# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provides mock data for a mock Sqlite database

Almost all calls to EmbeddedDatabase result in call to cursor's fetchall. In the debugger, it is easy to copy
the list that each fetchall returns, and put it in the fetchall_calls list defined in this module. Then
set USE_MOCK_SQLITE to True in embedded_db.py and when run, the mock sqlite db will be instantiated by
EmbeddedDatabase and each call to fetchall will return the next item in the fetchall_calls (so this list
is always a list of lists, since each fetchall() returns a list).

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
    'fetchall_calls'
]

# fetchall_calls = [
#     [(1,)]
# ]
