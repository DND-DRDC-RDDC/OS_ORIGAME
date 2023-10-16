# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Common logging functionality for Origami application variants.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path

# [2. third-party]

# [3. local]
from .typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from .typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # defines module members that are public; one line per string
    'LogManager',
    'LogRecord',
    'LogCsvFormatter',
    'log_level_name',
    'log_level_int',
]

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def log_level_name(level: Either[int, str]) -> str:
    """
    Returns the log level name for a given level. There is no equivalent in logging module:
    logging.getLevelName(obj) returns the level value if obj is name, but the level name if obj is value.

    :param level: int like logging.DEBUG, or string like 'DEBUG'
    :returns: the corresponding string like 'DEBUG'

    WARNING: uses instance, so do not call in compute intensive sections of code (e.g., loops).
    """
    return level if isinstance(level, str) else logging.getLevelName(level)


def log_level_int(level: Either[int, str]) -> int:
    """
    Returns the log level integer value for a given level. There is no equivalent in logging module:
    logging.getLevelName(obj) returns the level value if obj is name, but the level name if obj is integer value.

    :param level: int like logging.DEBUG, or string like 'DEBUG'
    :returns: the corresponding integer value like 10 for logging.DEBUG

    WARNING: uses instance, so do not call in compute intensive sections of code (e.g., loops).
    """
    return level if isinstance(level, int) else logging.getLevelName(level)


# -- Class Definitions --------------------------------------------------------------------------

class LogRecord(logging.LogRecord):
    """Override logging.LogRecord's getMessage so that both .format and % are supported in log messages"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.csv_format = False

    def getMessage(self):
        """
        Return the message for this LogRecord.

        Return the message for this LogRecord after merging any user-supplied
        arguments with the message.
        """
        msg = str(self.msg)  # required per LogRecord docs
        if self.args:
            try:
                msg = super().getMessage()
            except:
                msg = msg.format(*self.args)

        if self.csv_format:
            msg = msg.replace('"', '""')
        return msg


class LogManager:
    """
    Manages all log setup for a process. This should be instantiated once in the main process of both
    Origame variants, and once by each background replication process.
    """

    def __init__(self, stream=None, log_level: Either[int, str] = None):
        self._logfile = None

        self._syslog = logging.getLogger('system')
        self._usrlog = logging.getLogger('user')

        # create new level
        if not hasattr(logging, 'PRINT'):
            self.setup_print_logger()

        # set log levels for each logger:
        if log_level is None:
            log_level = logging.INFO
        self._syslog.setLevel(log_level)
        self._usrlog.setLevel(logging.PRINT)

        # setup the logging to a stream if requested:
        self._stream = None
        if stream is not None:
            # create a stream handler to stream to stream
            self._stream = logging.StreamHandler(stream)
            self._stream.setLevel(logging.DEBUG)
            # Logs to the GUI log panel
            formatter = logging.Formatter('%(asctime)s.%(msecs)03d:\t%(name)s:\t%(levelname)s:\t%(message)s',
                                          datefmt='%m/%d/%Y %H:%M:%S')
            self._stream.setFormatter(formatter)
            self._syslog.addHandler(self._stream)
            self._usrlog.addHandler(self._stream)

        assert self.is_ready  # post-condition

    @staticmethod
    def setup_print_logger():
        logging.PRINT = 15
        logging.addLevelName(logging.PRINT, 'PRINT')
        userlog = logging.getLogger('user')

        def userlog_print(msg, *args, **kwargs):
            return userlog.log(logging.PRINT, msg, *args, **kwargs)

        userlog.print = userlog_print

    def log_to_file(self, path='.', filename='log.csv', create_path=False, write_mode='w'):
        """
        Call this when logging to file is desired. Can only be called once. Output format is CSV.
        :param path: override default location of log file
        :param filename: override default file name of log file
        :param write_mode: specify the mode to open the file (for writing, reading, appending, etc.)
        :raises: RuntimeError if called previously
        :raises: OSError for problems encountered opening log file
        """

        assert self.is_ready  # verify that we have not been closed already

        if self._logfile is not None:
            raise RuntimeError('Can only call this once per LogManager instance')

        path = Path(path)
        if create_path and not path.exists():
            Path(path).mkdir(parents=True)
        filepath = path / filename

        # Clear previous contents and set up header in log file
        header_line = 'Time [MM/DD/YYYY HH:MM:SS.mmm],Log Name,Log-Level,Message\n'
        with filepath.open(write_mode) as f:
            f.write(header_line)
        f.close()

        # Open the logfile using 'filepath' for 'appending' logs
        self._logfile = logging.FileHandler(str(filepath))  # <- Note: this defaults to append mode
        self._logfile.setLevel(logging.DEBUG)

        formatter = LogCsvFormatter('{asctime},{name},{levelname},"{message}"', style='{')

        formatter.default_time_format = '%m/%d/%Y %H:%M:%S'
        formatter.default_msec_format = '%s.%03d'

        self._logfile.setFormatter(formatter)

        self._syslog.addHandler(self._logfile)
        self._usrlog.addHandler(self._logfile)

    def cleanup_files(self, glob_pattern: str, path: str = '.', keep: int = 5):
        """
        Cleanup existing log files that match glob_pattern. Folder containing log files is current working
        director if not specified.
        :param glob_pattern: pattern that will be given to glob.glob() function
        :param path: folder in which to look for log files
        :param keep: number of files to keep.
        """
        from pathlib import Path
        file_list = Path(path).glob(glob_pattern)
        file_list = sorted(file_list, key=lambda f: f.stat().st_mtime)
        for file in file_list[:-keep]:
            try:
                file.unlink()
            except IOError:
                # file might be locked by other Origame, leave it alone
                pass

    def get_is_ready(self) -> bool:
        """
        Return true if this LogManager can be used: all loggers exist. This is the only method that can
        be called after close().
        """
        return (self._syslog is not None) and (self._usrlog is not None)

    def get_logfile_path(self) -> Path:
        """Get the log file path, if any (None otherwise)"""
        return self._logfile.baseFilename if self._logfile else None

    def get_log_stream(self):
        """Get the stream that was given at initialization, if any (None otherwise)"""
        return self._stream.stream if self._stream else None

    def close(self):
        """
        Shutdown this logging manager. In a multithreaded process (such as for testing batch_sim.Replication), need
        to disconnect self from logging system without waiting for gc. Note: once called, only is_ready can be used.
        """

        if self._logfile is not None:
            self._syslog.removeHandler(self._logfile)
            self._usrlog.removeHandler(self._logfile)
            self._logfile.close()
            self._logfile = None

        if self._stream is not None:
            self._syslog.removeHandler(self._stream)
            self._usrlog.removeHandler(self._stream)
            self._stream = None

        self._syslog = None
        self._usrlog = None

    def __del__(self):
        self.close()

    is_ready = property(get_is_ready)
    logfile_path = property(get_logfile_path)
    log_stream = property(get_log_stream)


logging.setLogRecordFactory(LogRecord)


class LogCsvFormatter(logging.Formatter):
    """Formats log messages in CSV format for files, properly escaping messages that have commas"""

    def format(self, record):
        old_record_format = record.csv_format
        record.csv_format = True
        try:
            return super().format(record)
        finally:
            record.csv_format = old_record_format
