# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This package provides core functionality used by various Origame components.

In particular it defines BridgeEmitter and BridgeSignal: these default to being aliases for BackendEmitter
and BackendSignal, respectively. Any component that uses those will automatically get a signal base class that
is determined by the host application.

Version History: See SVN log.
"""

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5788$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- PUBLIC API ---------------------------------------------------------------------------------
# import *public* symbols (classes/functions/constants) from contained modules:

from .constants import *
from .cmd_line_args_parser import RunScenCmdLineArgs, LoggingCmdLineArgs, ConsoleCmdLineArgs, BaseCmdLineArgsParser
from .cmd_line_args_parser import AppSettings
from .singleton import Singleton
from .decorators import *
from .base_fsm import BaseFsmState, IFsmOwner
from .signaling import BackendEmitter, BackendSignal, BridgeEmitter, BridgeSignal, safe_slot
from .utils import validate_python_name, get_valid_python_name, InvalidPythonNameError
from .utils import UniqueIdGenerator, get_enum_val_name, select_object, ClockTimer, plural_if
from ._logging import LogManager, LogRecord, LogCsvFormatter, log_level_int, log_level_name
from .meta import AttributeAggregator
