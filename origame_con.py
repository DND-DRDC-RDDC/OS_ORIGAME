# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Run the Console variant of Origame (R4 HR Application)

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import sys
import signal as os_signal
import logging
from pathlib import Path

# [2. third-party]
import appdirs

# [3. local]
from origame.core import LogManager, ConsoleCmdLineArgs
from origame.batch_sim import BatchSimManager
from origame.scenario import ScenarioManager

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def sig_break_trap(signal, frame):
    """Trap control-c.
    :param signal: not used.
    :param frame: not used.
    """
    main.exit_console = True


# -- Class Definitions --------------------------------------------------------------------------

class ConsoleMain:
    """
    Main for Console variant.

    Uses instance of BatchSimMgr, and LogMgr.
    """

    def __init__(self):
        """
        Construct the console's main driver: parse command line args, instantiate the
        batch sim manager, setup signal trapping.
        """
        clap = ConsoleCmdLineArgs()
        settings = clap.parse_args()
        stream = sys.stdout if settings.console_logging else None
        self._log_mgr = LogManager(stream=stream, log_level=settings.log_level)

        folder = appdirs.user_log_dir(appauthor='DRDC', appname='Origame')
        if settings.save_log:
            self._log_mgr.log_to_file(path=folder, create_path=True)

        log.info('Starting console variant of Origame')

        self._scen_manager = ScenarioManager()
        self._scen_manager.load(settings.scenario_path)
        self._batch_sim_mgr = BatchSimManager(self._scen_manager, settings)

        # setup for trapping ctrl-c etc to cleanly exit
        self.exit_console = False
        os_signal.signal(os_signal.SIGINT, sig_break_trap)
        os_signal.signal(os_signal.SIGABRT, sig_break_trap)
        os_signal.signal(os_signal.SIGTERM, sig_break_trap)

    def run(self) -> Path:
        """
        Step the batch sim manager until it is done or user breaks, whichever comes first. Return the
        path that was created for this batch run.
        """
        log.info('Starting batch sim')
        self._batch_sim_mgr.start_sim()
        while (not self.exit_console) and (self._batch_sim_mgr.is_running()):
            self._batch_sim_mgr.update_sim()

        if self.exit_console:
            self._batch_sim_mgr.stop_sim()
            log.warning('Batch sim aborted')

        bsm = self._batch_sim_mgr
        log.info('Status for variants: {} planned, {} completed, {} failed',
                 bsm.num_variants, bsm.num_variants_done, bsm.num_variants_failed)
        log.info('Status for replications: {} planned, {} completed, {} failed',
                 bsm.num_replics_per_variant * bsm.num_variants, bsm.num_replics_done, bsm.num_replics_failed)
        log.info('Exiting console variant of Origame')

        return bsm.batch_folder


if __name__ == '__main__':
    try:
        main = ConsoleMain()
        main.run()
    except Exception as exc:
        log.error(exc)
        print(exc, file=sys.stderr)
