# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Holds constants related to the GUI. Note: The constants related to the core has its own
constants.py

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "Revision"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'BACKEND_THREAD_OBJECT_NAME',
    'DETAILED_PARAMETER_SYNTAX_DESCRIPTION'
]

log = logging.getLogger('system')

BACKEND_THREAD_OBJECT_NAME = 'backend-thread'

DETAILED_PARAMETER_SYNTAX_DESCRIPTION = """
Common causes:
- Forgetting to put quotes around a string: An expression my_string will
  attempt to evaluate a global variable (called my_string); whereas the
  expression "my_string" (note quotes) evaluates to a Python string object;
- Forgetting to prepend string with r when a raw string is desired;
- Forgetting to escape backslashes and other special characters that have
  special meaning in Python strings (see section 2.4.1 of the Python manual).
"""

# -- Function definitions -----------------------------------------------------------------------
# -- Class Definitions --------------------------------------------------------------------------
