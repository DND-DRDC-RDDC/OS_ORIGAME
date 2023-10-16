# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The command line argument parsing capability for the Origame application.

This module contains the following classes:
cmd_line_args_parser: A wrapper class for the argparse module that customizes commandline parsing for the Origame
                      application.
SimConfig: A helper class defined within the cmd_line_args_parser class. Used to store commandline arguments parsed by
           the parent class.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
from argparse import ArgumentParser, Namespace

# [2. third-party]

# [3. local]
from .typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from .typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from .decorators import override

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'RunScenCmdLineArgs',
    'LoggingCmdLineArgs',
    'ConsoleCmdLineArgs',
    'BaseCmdLineArgsParser',
]


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class LoggingCmdLineArgs(ArgumentParser):
    """
    Common command-line args functionality for all Origame variants.
    """

    def __init__(self):
        super().__init__(add_help=False)

        # NOTE: each argument must have a default!
        self.add_argument("--dev-log-level",
                          dest='log_level', type=str, default=None,  # default so we know if user wants custom
                          help="Log level for application (does not propagate to batch replications): "
                               "DEBUG, INFO, WARNING, ERROR, CRITICAL.")
        self.add_argument("--dev-no-save-log",
                          dest='save_log', default=True, action='store_false',
                          help="Do not save log to a file")
        self.add_argument("--dev-no-dep-warn",
                          dest='log_deprecated', default=True, action='store_false',
                          help="Turn off logging of prototype API deprecation warnings")
        self.add_argument("--dev-log-raw-events",
                          dest='log_raw_events', default=False, action='store_true',
                          help="Turn on logging of sim event push/pops raw data (at warn level)")
        self.add_argument("--dev-no-linking-fixes-on-load",
                          dest='fix_linking_on_load', default=True, action='store_false',
                          help="Turn off fixing of invalid links on scenario load")


class RunScenCmdLineArgs(ArgumentParser):
    """
    Command-line arguments related to running a scenario.
    """

    def __init__(self):
        super().__init__(add_help=False)

        self.add_argument("scenario_path", type=str,
                          help="Scenario definition file pathname. Mandatory. Can be relative path.")

        # NOTE: each remaining argument must have a default!

        # common to batch and non-batch:
        self.add_argument("--loop-log-level",
                          type=str, default=None,  # this is how we know whether user overrides the app default
                          help="Log level for each replication's sim loop: DEBUG, INFO, WARNING, ERROR, CRITICAL.")
        self.add_argument("-t", "--max-sim-time-days",
                          type=float, default=None,
                          help="Simulation cut-off time in days. Optional. Default runs till no events (or max "
                               "real-time reached, if set; whichever occurs first).")
        self.add_argument("-x", "--max-wall-clock-sec",
                          type=float, default=None,
                          help="Real-time cut-off time in seconds. Optional. Default runs till no events (or "
                               "max sim time reached, if set; whichever occurs first).")

        # only in non-batch mode:
        self.add_argument("-f", "--realtime-scale",
                          type=float, default=None,
                          help="Turn on real-time mode, using the given scale factor. Default is "
                               "as-fast-as-possible.")

        # only in batch mode:
        self.add_argument("-b", "--batch-replic-save",
                          default=True, action='store_false',
                          help="Turn off saving of final scenario state by each batch replication")
        self.add_argument("-s", "--seed-file-path",
                          type=str, default=None,
                          help="Seed file pathname. Optional. Can be relative path. Default causes seeds to be "
                               "randomly generated.")
        self.add_argument("-v", "--num-variants",
                          type=int, default=1,
                          help="The number of scenario variants to be run. Optional. Default runs a single "
                               "variant.")
        self.add_argument("-r", "--num-replics-per-variant",
                          type=int, default=1,
                          help="The number of scenario replications to be run for a scenario variant. "
                               "Optional. Default runs a single replication for a variant.")
        self.add_argument("-c", "--num-cores",
                          type=int, default=0,
                          help="The maximum number of cores to utilize for the configured scenario run. "
                               "Optional. Zero distributes batch replications across all available cores.")


class BaseCmdLineArgsParser(ArgumentParser):
    @classmethod
    def get_defaults(cls, *required: List[str], dest: Namespace = None) -> Namespace:
        """
        Get the default settings.
        :param required: values for command line args that are required (don't have defaults)
        :param dest: If dest given, attributes are created in dest, else a new namespace is returned
        """
        return cls().parse_args(args=required, namespace=dest)

    def parse_args(self, args=None, namespace=None):
        """Once the namespace is populated, protect it against changing settings directly"""
        if namespace is None:
            namespace = AppSettings()
        result = ArgumentParser.parse_args(self, args=args, namespace=namespace)
        result.protected = True
        return result


class ConsoleCmdLineArgs(BaseCmdLineArgsParser):
    def __init__(self):
        log_clap = LoggingCmdLineArgs()
        run_scen_clap = RunScenCmdLineArgs()
        super().__init__(parents=[log_clap, run_scen_clap])

        self.add_argument("-l", "--dev-no-stdout-log",
                          dest='console_logging', default=True, action='store_false',
                          help="Log system debug messages (assuming logging is ON)")


class AppSettings:
    """
    Application settings object created from command line arguments. Which settings it contains
    depends on the command line args parser; the parser will populate it with all the command
    line argument values as well as the default values (for command line args not used).

    Since an instance is basically a data structure, it is very easy to change settings (say for
    testing) but this also means that typos will go unnoticed and the default value will be used
    (which will typically be difficult bug to figure out as it will appear as though the setting
    has no effect). For this reason, once the command line args parser is done creating the
    settings object, it sets it in protected mode: the only way to further change settings after
    this is via the override() method, which accepts a setting only if it exists already in the
    instance.
    """

    def override(self, **kwargs):
        """
        Override existing settings. The settings MUST have been obtained from one of the command
        line args parsers
        """
        if not set(kwargs.keys()).issubset(self.__dict__):
            unknown_keys = [repr(s) for s in set(kwargs.keys()).difference(self.__dict__)]
            raise ValueError('Invalid kwarg names: {} (valid are {})'.format(
                ', '.join(unknown_keys), ', '.join(sorted(self.__dict__))))

        self.__dict__.update(kwargs)

    def __setattr__(self, key, value):
        """Prevent directly settings attributes when protected so that override() MUST be used"""
        if key != 'protected' and hasattr(self, 'protected'):
            raise RuntimeError('Settings protected, use override(**settings) method')

        object.__setattr__(self, key, value)
