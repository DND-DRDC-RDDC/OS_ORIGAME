# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Log Window shows all messages sent to logging Loggers and to stdout & stderr

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import sys
import logging
from collections import namedtuple
from itertools import accumulate
from pathlib import Path, PureWindowsPath
import csv
from bisect import bisect_left

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QFileDialog, QPlainTextEdit, QMessageBox, QTextEdit, QPushButton
from PyQt5.QtCore import QObject, QSettings, pyqtSignal, Qt
from PyQt5.QtGui import QKeyEvent, QKeySequence, QTextCharFormat, QTextCursor, QColor, QFont

# [3. local]
from ..core import override, log_level_int
from ..core.utils import GuardFlag
from ..core.typing import Optional, AnnotationDeclarations
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO, AnnotationDeclarations
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from .Ui_log_panel import Ui_LogPanel
from .gui_utils import exec_modal_dialog
from .gui_utils import get_scenario_font
from .safe_slot import safe_slot

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # defines module members that are public; one line per string
    'LogPanel',
]

log = logging.getLogger('system')

MAP_LOGGER_LEVELS_TO_FILTER_SETTINGS = {
    'system': {
        'DEBUG': True,
        'INFO': True,
        'WARNING': True,
        'ERROR': True,
        'CRITICAL': True,
    },
    'user': {
        'PRINT': True,
        'INFO': True,
        'WARNING': True,
        'ERROR': True,
        'CRITICAL': True,
    },
}

MAP_LOGGER_LEVELS_TO_KEYS = {
    'system': {
        'DEBUG': 0,
        'INFO': 1,
        'WARNING': 2,
        'ERROR': 3,
        'CRITICAL': 4,
    },
    'user': {
        'PRINT': 5,
        'INFO': 6,
        'WARNING': 7,
        'ERROR': 8,
        'CRITICAL': 9,
    }
}


class Decl(AnnotationDeclarations):
    GuiLogCacher = 'GuiLogCacher'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class LogStream:
    """
    The LogStream class to capture stdout and stderr streams.
    :param stream_name: 'stdout' or 'stderr'
    """

    def __init__(self, stream_name):

        # Send all standard messages to the system logger
        logger = logging.getLogger('system')
        if stream_name == 'stdout':
            # Set stdout msgs to DEBUG level
            self.__log = logger.debug
            sys.stdout = self

            # Tag msg to indicate msg source
            self.__tag = '***stdout*** '
        else:
            # Set stderr msgs to ERROR level
            self.__log = logger.error
            sys.stderr = self

            # Tag msg to indicate msg source
            self.__tag = '***stderr*** '

    def write(self, msg: str):
        """
        Forward msg to log
        :param string msg: A message to write to our logger/level
        """
        if msg.strip():
            self.__log(self.__tag + msg.rstrip())

    def flush(self):
        """ Implements a require flush method
        """
        pass


LogMsgInfo = namedtuple('LogMsgInfo', [
    'msg_id',   # number of the message (starts at 0 -- basically the index into log history)
    'level_key', # key corresponding to the logger (system, user, etc) and message level (debug, info etc)
    'msg',       # the actual message to be shown user
    'num_lines'  # number of lines of log message
])


class LogCapture(QObject, logging.Handler):
    """
    Implements the Logging Handler and Log Stream slot-connections.
    """

    new_log_record = pyqtSignal(LogMsgInfo)  # log info of the new record
    filtering_changed = pyqtSignal()

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)

        # Set up Handler configuration
        msg_format = logging.Formatter('%(asctime)-25s\t%(name)7s\t%(levelname)8s\t%(message)s')

        msg_format.default_time_format = '%m/%d/%Y %H:%M:%S'
        msg_format.default_msec_format = '%s.%03d'

        self.setFormatter(msg_format)

        # NOTE: DO NOT set the minimum logger log-level -> managed by LogManager
        log_system = logging.getLogger('system')
        log_user = logging.getLogger('user')
        log_system.addHandler(self)
        log_user.addHandler(self)
        # logging.getLogger('system.proto').addHandler(self)

        self.__log_filter_settings = MAP_LOGGER_LEVELS_TO_FILTER_SETTINGS.copy()

        # Restore filter settings (above) from last run
        settings = QSettings()
        for log_name, log_levels in self.__log_filter_settings.items():
            for log_level in log_levels:
                settings_key = 'settings.log_filter.{}.{}'.format(log_name, log_level)
                log_levels[log_level] = settings.value(settings_key, True, bool)

        # Log filter parameters
        self.__log_history = []
        self.__log_history_filtered = []

        # Log stdout and stderr streams
        self.__log_stdout = LogStream('stdout')
        self.__log_stderr = LogStream('stderr')

    def clear_logs(self):
        """Clear the contents of the log cache"""
        self.__log_history = []
        self.__log_history_filtered = []
        self.filtering_changed.emit()

    def get_log_filter_settings(self, log_name: str, log_level: str):
        """
        Getter method for log filter user-settings
        :param log_name: the logger name: 'system' or 'print'
        :param log_level: the log-level: e.g. 'INFO' and others
        :return: the filter setting for the specified logger and log-level: True or False
        """
        return self.__log_filter_settings[log_name][log_level]

    @override(logging.Handler)
    def emit(self, log_record: logging.LogRecord):
        """
        Sends the log record to the logging system.
        :param LogMsgInfo log_record: A logging record
        """

        # Emit only if there is a log
        if not log_record or self.signalsBlocked():
            return

        # Info to check filter settings
        msg_id = len(self.__log_history)
        log_name = log_record.name  # e.g.: 'system' or 'user' or 'print'
        log_level = log_record.levelname  # e.g.: 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'
        log_level_key = MAP_LOGGER_LEVELS_TO_KEYS[log_name][log_level]
        log_msg = self.format(log_record)
        num_lines = len(log_msg.splitlines())
        log_msg_info = LogMsgInfo(msg_id, log_level_key, log_msg, num_lines)

        # Update log history list
        self.__log_history.append(log_msg_info)

        # If the filter settings allow...
        if self.__log_filter_settings[log_name][log_level]:
            # Display the log and update the filtered list
            self.__log_history_filtered.append(log_msg_info)
            self.new_log_record.emit(log_msg_info)

    def set_log_level(self, log_name: str, level: str, filter_set_to_view: bool):
        """
        Set the log level of a given log to be visible or not.
        :param log_name: log level to configure.
        :param level: level to show or not.
        :param filter_set_to_view: True to make visible.
        """
        self.__log_filter_settings[log_name][level] = filter_set_to_view
        self.__save_setting(log_name, level, filter_set_to_view)
        self.__filter_log_history(log_name, level, filter_set_to_view)

    def set_log_level_system_critical(self, filter_set_to_view: bool):
        self.set_log_level('system', 'CRITICAL', filter_set_to_view)

    def set_log_level_system_error(self, filter_set_to_view: bool):
        self.set_log_level('system', 'ERROR', filter_set_to_view)

    def set_log_level_system_warning(self, filter_set_to_view: bool):
        self.set_log_level('system', 'WARNING', filter_set_to_view)

    def set_log_level_system_info(self, filter_set_to_view: bool):
        self.set_log_level('system', 'INFO', filter_set_to_view)

    def set_log_level_system_debug(self, filter_set_to_view: bool):
        self.set_log_level('system', 'DEBUG', filter_set_to_view)

    def set_log_level_user_critical(self, filter_set_to_view: bool):
        self.set_log_level('user', 'CRITICAL', filter_set_to_view)

    def set_log_level_user_error(self, filter_set_to_view: bool):
        self.set_log_level('user', 'ERROR', filter_set_to_view)

    def set_log_level_user_warning(self, filter_set_to_view: bool):
        self.set_log_level('user', 'WARNING', filter_set_to_view)

    def set_log_level_user_info(self, filter_set_to_view: bool):
        self.set_log_level('user', 'INFO', filter_set_to_view)

    def set_log_level_user_print(self, filter_set_to_view: bool):
        self.set_log_level('user', 'PRINT', filter_set_to_view)

    def get_filtered_log_history(self, index_range: Tuple[int, int] = None) -> List[LogMsgInfo]:
        """
        Retrieve the log records as filtered according to the log capture settings.

        :param index_range: if specified, a tuple indicating the index of first and last items of the
            *filtered* log. The starting index >=0. The end record in included in the returned list.
            Note: the index is not the same as the unfiltered log index!
        :returns: A list of log indices into the unfiltered log, and a list of log messages (the two lists
            have the same number of items and the
            the second item is the log record.
        """
        start, end = index_range or (0, None)
        if end is None:
            if start > 0:
                records = self.__log_history_filtered[start:]
            else:
                assert start == 0
                records = self.__log_history_filtered[:]
        else:
            if start > 0:
                records = self.__log_history_filtered[start:end + 1]
            else:
                assert start == 0
                records = self.__log_history_filtered[:end + 1]

        return records

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_set_log_level_system_critical = safe_slot(set_log_level_system_critical)
    slot_set_log_level_system_error = safe_slot(set_log_level_system_error)
    slot_set_log_level_system_warning = safe_slot(set_log_level_system_warning)
    slot_set_log_level_system_info = safe_slot(set_log_level_system_info)
    slot_set_log_level_system_debug = safe_slot(set_log_level_system_debug)
    
    slot_set_log_level_user_critical = safe_slot(set_log_level_user_critical)
    slot_set_log_level_user_error = safe_slot(set_log_level_user_error)
    slot_set_log_level_user_warning = safe_slot(set_log_level_user_warning)
    slot_set_log_level_user_info = safe_slot(set_log_level_user_info)
    slot_set_log_level_user_print = safe_slot(set_log_level_user_print)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __filter_log_history(self, log_name: str, log_level: str, filter_set_to_view: bool):
        """
        Filters the log-history in order to show only the log message types the user wants to see.

        This algorithm uses two log message lists that are maintained for the duration of the application instance:

            1. self.__log_history: a list that tracks all log messages - a complete log history -  regardless
               of the user-applied filter currently selected. This list is not displayed in the Log Window.
               It contains a key identifying which combination of logger and level (the system logger has
               4 levels, the user logger has 5), and the log message.
               Log history key corresponds to the log filter applied (e.g. system-INFO key = 3, print-INFO key = 9)
            2. self.__log_history_filtered: a filtered log history list that contains only the subset of log messages
               as filtered by the log-filter settings. It is this list which is displayed in the Log Window.
               It contains an index into the self.__log_history, the corresponding log key, and the log message.

        The log history keys are necessary to associate each log message stored in the lists with a specific
        filter-setting, i.e. system-INFO log messages (key = 3) vs. user-INFO log messages (key = 8). This enables the
        algorithm to quickly search through either list to add to, or remove logs from, the Log Window based on the
        user-selected log-filter settings.

        Finally and intuitively, the log message stored in the list is used to recover the log for display in the
        Log Window as determined by the log-filter settings currently applied. Since all log messages are stored, any
        log message, whether displayed in the Log Window previously or not, can be added to or removed from the Log
        Window at any time.

        Emits sig_filtering_changed at end.

        :param log_name: the logger name: e.g. 'system' or 'user'
        :param log_level: the log-level: e.g. 'INFO' and others
        :param filter_set_to_view: the filter setting: e.g. True (view message) or False (hide message)
        """

        # Assign the key corresponding to the logger and log-level selected
        log_key = MAP_LOGGER_LEVELS_TO_KEYS[log_name][log_level]

        if filter_set_to_view:
            # Add logs from the log history list to the filtered list
            add_entries = [log_info for log_info in self.__log_history
                           if log_info.level_key == log_key]
            self.__log_history_filtered.extend(add_entries)
            self.__log_history_filtered.sort()

        else:
            # Remove logs from the existing filtered list
            self.__log_history_filtered = [log_info for log_info in self.__log_history_filtered
                                           if log_info.level_key != log_key]

        self.filtering_changed.emit()

    def __save_setting(self, log_name, log_level, filter_set_to_view: bool):
        """Save the Log Window log-level config when the filter setting has changed"""
        settings_key = 'settings.log_filter.{}.{}'.format(log_name, log_level)
        QSettings().setValue(settings_key, filter_set_to_view)


class LogLineMarker:
    """
    Manage marking of a log message in the log view. Keeps track of number of lines of log messages so that if the 
    line marked is within a multi-line log message, the proper log id is obtained. 
    """
    
    def __init__(self):
        # track the starting line # of each log received
        self.__log_line_starts = []
        self.__next_line_start = 0
        self.__marker_offset = None
        self.__marked_log_id = None

    def mark_line(self, line_num: int, log_infos: List[LogMsgInfo]) -> int:
        """
        Set a line as marked. Returns the log id that contains that line.
        """
        self.__update_marked_log(line_num, log_infos)
        assert self.__marked_log_id is not None
        return self.__marked_log_id
    
    def on_logs_changed(self, new_log_infos: List[LogMsgInfo], marked_log_id: int) -> Optional[int]:
        """
        Must be called whenever the logs change. A new text cursor is returned, such that the next closest 
        log is marked. If the log marked is marked_log_id and it is a multi-line line, the cursor is on the 
        original line.
        :param new_log_infos: list of log messages
        :param marked_log_id: the marked log id
        :return: the line to mark now that logs have changed
        """
        self.__log_line_starts = [0]
        self.__log_line_starts.extend(line for line in accumulate(nli.num_lines for nli in new_log_infos))
        self.__next_line_start = self.__log_line_starts.pop()
        return self.__get_marker_line_num(marked_log_id, new_log_infos)

    def on_log_added(self, log_info: LogMsgInfo):
        """
        Must be called whenever a new log message has been appended to the log view.
        :param log_info: log message
        """
        self.__log_line_starts.append(self.__next_line_start)
        self.__next_line_start += log_info.num_lines

    def get_marked_log_id(self) -> Optional[None]:
        """Return the currently marked log id. None if no log currently marked."""
        return self.__marked_log_id

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_marker_line_num(self, log_id: int, log_infos: List[LogMsgInfo]) -> Optional[int]:
        """Get the line number of marker line for given log id and list of log messages"""
        if log_id is None:
            return None

        for log_num, log_info in enumerate(log_infos):
            if log_info.msg_id >= log_id:
                line_start = self.__log_line_starts[log_num]
                if self.__marked_log_id is not None and log_info.msg_id == self.__marked_log_id:
                    line_start += self.__marker_offset
                return line_start

        return None

    def __update_marked_log(self, line_clicked: int, log_infos: List[LogMsgInfo]):
        """
        Find which log message is being marked, given a line was clicked.
        :param line_clicked: number of line clicked (>= 0)
        :param log_infos: list of log messages
        """
        log_id = bisect_left(self.__log_line_starts, line_clicked)
        if log_id >= len(self.__log_line_starts) or self.__log_line_starts[log_id] != line_clicked:
            log_id -= 1

        assert len(log_infos) == len(self.__log_line_starts)
        self.__marked_log_id = log_infos[log_id].msg_id
        self.__marker_offset = line_clicked - self.__log_line_starts[log_id]


class LogMessagesHider:
    """
    Hides all log messages earlier than a certain log message. Also manages the Hide button
    of the log panel to be disabled or enabled.
    """

    LOG_INDEX_OF_UNHIDABLE_LINE = -1

    def __init__(self, hide_button: QPushButton):
        """
        :param hide_button: the Hide button to manage
        """
        self.__hide_button = hide_button
        self.__hide_prev_label = hide_button.text()

        self.__hiding_logs = False
        self.__next_earliest_log_index = None
        self.__earliest_log_index = None
        self.__hide_button.setEnabled(False)

    def is_line_markable(self, line_num: int):
        """Return true if the given line number can be marked for hiding previous log messages"""
        return line_num != 0 if self.__hiding_logs else True

    def on_log_marked(self, log_id: int, log_infos: List[LogMsgInfo]):
        """
        Must be called whenever a log has been marked
        :param log_id: the id of the log that was marked
        :param log_infos: the list of log messages displayed
        """
        self.__update_hide_button(log_infos, log_id)

    def toggle_hiding(self, log_infos: List[LogMsgInfo], marked_log_id: int) -> Tuple[List[LogMsgInfo], int]:
        """
        Toggle the hiding: if currently hiding, unhide; if showing all, hide based on most recent
        call to set_earliest_line_log_index().

        :param log_infos: the list of log messages displayed
        :param marked_log_id: the id of the log that was marked
        :return: first item is the list of log messages to display in new state; the second item is the log 
            message to mark in the new state.
        """
        if self.__hiding_logs:
            self.__hiding_logs = False
            self.__hide_button.setText(self.__hide_prev_label)

        else:
            self.__hiding_logs = True
            self.__hide_button.setText("Show Hidden")
            log_infos = self.__get_partial_logs(log_infos, marked_log_id)

        # the marked log could be invisible (because of change of filter)
        marked_log_id = self.__get_next_closest_log(log_infos, marked_log_id)
        self.__update_hide_button(log_infos, marked_log_id)
        return log_infos, marked_log_id

    def on_logs_changed(self, log_infos: List[LogMsgInfo], 
                        marked_log_id: Optional[int]) -> Tuple[List[LogMsgInfo], Optional[int]]:
        """
        Refresh the current list of hidden logs (presumably because the filtering has changed).
        If currently hiding, hides based on most recent toggling. Parameters and return are the
        same as toggle_hiding.
        
        :param log_infos: the list of log messages displayed
        :param marked_log_id: the id of the log that was marked; can be None only if *not* currently hiding
        :return: first item is the list of log messages to display in new state; the second item is the log 
            message to mark. The marked log may not be 
        """
        if self.__hiding_logs:
            assert marked_log_id is not None
            log_infos = self.__get_partial_logs(log_infos, marked_log_id)

        marked_log_id = self.__get_next_closest_log(log_infos, marked_log_id)
        self.__update_hide_button(log_infos, marked_log_id)
        return log_infos, marked_log_id

    @property
    def is_hiding(self) -> bool:
        """True if self is hiding logs, False if showing all logs"""
        return self.__hiding_logs

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __update_hide_button(self, log_infos: List[LogMsgInfo], marked_log_id: int):
        """
        Update the state of the Hide/Unhide button. The button is always enabled when showing all logs. 
        While hiding, the button is enabled only if there is a log message marked, and if it is not the first 
        log message (there is nothing to hide if log marked is first message). 

        :param log_infos: the list of log messages displayed
        :param marked_log_id: the id of the log that was marked
        """
        if self.__hiding_logs:
            self.__hide_button.setEnabled(True)
        else:
            self.__hide_button.setEnabled(marked_log_id is not None and
                                          log_infos and
                                          log_infos[0].msg_id != marked_log_id)

    def __get_partial_logs(self, log_infos: List[LogMsgInfo], marked_log_id: int) -> List[LogMsgInfo]:
        """
        Get a new list of log indices and log messages, such that all of them are for log entries at or after
        the entry corresponding to current value of marked_log_id.

        :param log_infos: the list of log messages displayed
        :param marked_log_id: the id of the log that was marked
        """
        new_log_infos = None
        for log_index, log_info in enumerate(log_infos):
            log_id = log_info.msg_id
            if log_id >= marked_log_id:
                msg = '....{} messages hidden....'.format(log_index)
                new_log_infos = [LogMsgInfo(self.LOG_INDEX_OF_UNHIDABLE_LINE, -1, msg, 1)]
                new_log_infos.extend(log_infos[log_index:])
                break

        if new_log_infos is None:
            # this can happen if the marked line has been filtered out and there are no log messages left
            # that are after marked line:
            msg = '....{} messages hidden....'.format(len(log_infos))
            new_log_infos = [LogMsgInfo(self.LOG_INDEX_OF_UNHIDABLE_LINE, -1, msg, 1)]

        return new_log_infos

    def __get_next_closest_log(self, log_infos: List[LogMsgInfo], log_id: Optional[int]) -> Optional[int]:
        """
        Get the log ID for the log item that is closest to the entry specified by log_id.
        
        :param log_infos: the list of log messages displayed
        :param log_id: the id of the log that was marked
        :return: the next closest log id
        """
        if log_id is None:
            return None

        for log_info in log_infos:
            if log_info.msg_id >= log_id:
                return log_info.msg_id

        return None


class TextHighlighter:
    """
    Manages text highlighting in the log view. Currently there are two types of highlighting:

    - all occurrences of currently selected text
    - the marked line
    """

    def __init__(self):
        self.__all_sel_highlights = []
        self.__user_selected_text = None
        self.__marked_line_paint = None

    def on_selection_changed(self, log_view: QPlainTextEdit):
        current_cursor = log_view.textCursor()
        if current_cursor.hasSelection():
            # Oliver FIXME TBD: Only loop over the lines that are visible, ie from firstVisibleBlock to
            #     the next block that has isVisible() False; only highlight if 2 or more chars in selection
            #     Call this when text scrolled
            #     Reason: Not critical, but when log is large, this can slow down selection considerably
            self.__user_selected_text = current_cursor.selectedText()
            self.__all_sel_highlights = self.__get_sel_highlights(log_view)
            self.__show_highlights(log_view)
            log_view.setTextCursor(current_cursor)

        else:
            self.__user_selected_text = None
            self.__all_sel_highlights = []
            self.__show_highlights(log_view)

    def on_logs_changed(self, log_view: QPlainTextEdit, marked_line_num: Optional[int]):
        """
        Highlight the marked line and all occurrences of given text string.
        :param marked_line: text cursor for line to mark; None if no line should be marked
        """
        if marked_line_num is None:
            marked_cursor = None
            self.__marked_line_paint = None
            self.__show_highlights(log_view)

        else:
            marked_cursor = log_view.textCursor()
            marked_cursor.movePosition(QTextCursor.Start)
            marked_cursor.movePosition(QTextCursor.Down, n=marked_line_num)
            self.__marked_line_paint = self.__make_line_marker(marked_cursor)

        self.__all_sel_highlights = self.__get_sel_highlights(log_view)
        self.__show_highlights(log_view)

        # ensure marked line is visible:
        if marked_cursor is not None:
            marked_cursor.clearSelection()
            log_view.setTextCursor(marked_cursor)
            log_view.centerCursor()

    def on_log_added(self, log_view: QPlainTextEdit, log_msg: str):
        """
        Notify this component that a log message has been added. If there is currently user selection,
        any occurrences of the selection will be highlighted in the new log message. 
        :param log_view: the text box containing text to which message was added
        :param log_msg: the message that was added (can be multiline)
        """
        if self.__user_selected_text is not None and self.__user_selected_text in log_msg:
            self.__all_sel_highlights = self.__get_sel_highlights(log_view)
            self.__show_highlights(log_view)
            # always need to clear selection:
            text_cursor = log_view.textCursor()
            if text_cursor.hasSelection():
                text_cursor.clearSelection()
                log_view.setTextCursor(text_cursor)

    def mark_line(self, log_view: QPlainTextEdit, cursor: QTextCursor):
        """
        Mark or unmark the line containing the cursor.
        :param log_view: the text box that contains the line
        :param cursor: the text cursor indicating which line to mark, or None if should unmark all lines
        """
        if cursor is None:
            self.__marked_line_paint = None
        else:
            self.__marked_line_paint = self.__make_line_marker(cursor)
        self.__show_highlights(log_view)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_sel_highlights(self, log_view: QPlainTextEdit) -> List[QTextEdit.ExtraSelection]:
        """
        Get highlighters for all occurrences of the given text string in the log window.
        """
        if self.__user_selected_text is None:
            return []

        current_scroll_h = log_view.horizontalScrollBar().value()
        current_scroll_v = log_view.verticalScrollBar().value()
        line_color = QColor(Qt.red).lighter(160)
        all_sel_highlights = []

        log_view.moveCursor(QTextCursor.Start)
        while log_view.find(self.__user_selected_text):
            extra_sel = QTextEdit.ExtraSelection()
            extra_sel.cursor = log_view.textCursor()
            format = QTextCharFormat()
            format.setBackground(line_color)
            extra_sel.format = format
            all_sel_highlights.append(extra_sel)

        log_view.horizontalScrollBar().setValue(current_scroll_h)
        log_view.verticalScrollBar().setValue(current_scroll_v)

        return all_sel_highlights

    def __show_highlights(self, log_view: QPlainTextEdit):
        if self.__marked_line_paint is None:
            log_view.setExtraSelections(self.__all_sel_highlights)
        else:
            log_view.setExtraSelections(self.__all_sel_highlights + [self.__marked_line_paint])

    def __make_line_marker(self, cursor: QTextCursor) -> QTextEdit.ExtraSelection:
        """
        Highlight the line that contains the cursor (after unhighlighting the previous highlighted line
        if there was one).
        :param cursor: the text cursor for the line to highlight
        """
        cursor.select(QTextCursor.LineUnderCursor)

        # format the line
        format = QTextCharFormat()
        line_color = QColor(Qt.darkCyan)
        format.setBackground(line_color)
        format.setForeground(QColor(Qt.white))
        ext_sel = QTextEdit.ExtraSelection()
        ext_sel.format = format
        ext_sel.cursor = cursor

        return ext_sel


class LogPanel(QWidget):
    """
    Log Window panel for placing inside a QDockWidget
    """

    # --------------------------- class-wide data and signals -----------------------------------

    LOG_PATH_KEY = "log_path"  # Key for QSettings

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QWidget = None, log_cacher: Decl.GuiLogCacher = None):
        super().__init__(parent)
        self.ui = Ui_LogPanel()
        self.ui.setupUi(self)

        # Text View
        log_view = self.ui.log_record_display
        log_view.clear()  # Clear the dummy text from Designer
        log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        # many of the log messages will be related to scenario, so the scenario font is used.
        log_view.document().setDefaultFont(get_scenario_font(stretch=QFont.SemiCondensed))
        log_view.setTabStopWidth(20)

        # Buttons
        self.ui.toggle_options_button.clicked.connect(self.slot_toggle_log_options)
        self.ui.save_button.clicked.connect(self.slot_save_log_snapshot)

        # Log Capture
        self.__log_capture = LogCapture()
        self.__log_capture.filtering_changed.connect(self.__slot_on_filtering_changed)
        self.__log_capture.new_log_record.connect(self.__slot_on_new_log_record)
        self.__filtered_logs = []

        # System Logger: set initial Log Filter check-marks from QSettings
        get_log_filter_settings = self.__log_capture.get_log_filter_settings
        for log_name, log_levels in MAP_LOGGER_LEVELS_TO_KEYS.items():
            sys_log_level = logging.getLogger(log_name).getEffectiveLevel()
            for log_level in log_levels:
                # Set initial state of button:
                button_name = 'checkbox_{}_{}_logs'.format(log_name, log_level.lower())
                button = getattr(self.ui, button_name)
                is_checked = get_log_filter_settings(log_name, log_level)
                button.setChecked(is_checked)

                # Connect to its signal:
                slot_name = 'slot_set_log_level_{}_{}'.format(log_name, log_level.lower())
                button.toggled.connect(getattr(self.__log_capture, slot_name))

                # Disable any system log button that is for log level lower than system log level (since
                # changing the checkbox will have no effect). The system log level can be changed for the
                # application via the --dev-log-level command line arg of GUI.
                if log_name == 'system':
                    enabled = (log_level_int(log_level) >= sys_log_level)
                    button.setEnabled(enabled)

        # selection highlighting:
        self.__text_highlighter = TextHighlighter()
        log_view.selectionChanged.connect(self.__slot_highlight_selection)
        self.__sel_changed_by_self = GuardFlag(False)
        log_view.horizontalScrollBar().sliderMoved.connect(self.__slot_on_text_horiz_slider_moved)
        self.__text_horiz_slider_moved = False

        # line marking:
        self.__line_marker = LogLineMarker()
        self.__marked_line_paint = None
        self.ui.log_record_display.cursorPositionChanged.connect(self.__slot_cursor_pos_changed)
        self.__cursor_pos_changed_by_self = GuardFlag(False)  # because changing text causes cursorPositionChanged

        # log hiding:
        self.__logs_hider = LogMessagesHider(self.ui.hide_prev_button)
        self.ui.hide_prev_button.clicked.connect(self.slot_toggle_hiding_prev_logs)

        # ensure the options panel is hidden initially:
        if not self.ui.options_panel.isHidden():
            self.toggle_log_options()

        # send all log messages that were generated before this log view was created to our capturer:
        if log_cacher is not None:
            log_cacher.send_all(self.__log_capture)

    @override(QPlainTextEdit)
    def keyReleaseEvent(self, key_event: QKeyEvent):
        """
        Qt deliberately disables the Ctrl+C key binding when this widget is ready-only.
        See this for more information: http://doc.qt.io/qt-5/qplaintextedit.html

        So, we handle the Ctrl+C ourselves.

        :param key_event: The key event. We only want to process Ctrl+C
        """
        super().keyPressEvent(key_event)
        if key_event.matches(QKeySequence.Copy):
            self.ui.log_record_display.copy()

    def set_system_filtering(self, log_level: str, status: bool):
        """Change the visibility of system log to log_level"""
        self.__log_capture.set_log_level('system', log_level, status)

    def save_log_snapshot(self):
        """
        Save all the filtered logs or a selected section of them to a file.

        If the user does not select (highlight) the log messages in the "Application Log" dialog, all the current
        messages in that dialog will be saved. If the user selects a section of the messages, only the selected
        section of the messages will be saved. If the staring line of the selected section is partially selected, the
        whole line will be included for saving; the same rule applies to the ending line.
        """

        # noinspection PyTypeChecker
        (filename, ok) = QFileDialog.getSaveFileName(None,
                                                     "Save As...",
                                                     QSettings().value(self.LOG_PATH_KEY, str(Path.cwd())),
                                                     "Text files (*.csv)")
        if not filename:
            # The user has cancelled the save operation
            return

        # Check .csv extension and set to .csv if incorrect
        filename_suffix = Path(filename).suffix
        csv_extension = ".csv"
        if filename_suffix != csv_extension:
            filename_suffix = csv_extension
            p = PureWindowsPath(filename)
            filename = str(p.with_suffix(filename_suffix))

        QSettings().setValue(self.LOG_PATH_KEY, filename)

        # Design decisions: the builtin enumerate(iterable, start=0) would help reduce the cost of the slicing, but
        # the "enumerate" always starts from the first element and that would cost more if the logs are huge.
        log_infos = self.__log_capture.get_filtered_log_history(index_range=self.__get_selection_line_numbers())
        header_record = ['Time [MM/DD/YYYY HH:MM:SS.mmm]', 'Log Name', 'Log-Level', 'Message']
        list_by_range_stripped = [header_record]
        for log_info in log_infos:
            # Each log message is of the form '02/25/2015 03:37:34:\tsystem:\tINFO:\tSystem log message...'
            list_by_range_stripped.append(log_info.msg.split("\t"))

        try:
            with Path(filename).open('w', newline='') as f:
                writer = csv.writer(f)
                writer.writerows(list_by_range_stripped)
        except IOError as exc:
            exec_modal_dialog("File Save Error",
                              "This file is set to read only. Try again with a different name.", QMessageBox.Critical)

    def clear_logs(self):
        """Clear the logs"""
        self.__log_capture.clear_logs()

    def toggle_hiding_prev_logs(self):
        """Toggle the hiding and unhiding of logs earlier than the last mouse click"""
        # toggle hiding and update log view text
        self.__filtered_logs, marked_log_id = self.__logs_hider.toggle_hiding(
            self.__log_capture.get_filtered_log_history(), self.__line_marker.get_marked_log_id())
        log_view = self.ui.log_record_display
        with self.__sel_changed_by_self(True):
            with self.__cursor_pos_changed_by_self(True):
                log_view.setPlainText('\n'.join(log_info.msg for log_info in self.__filtered_logs))
                # update highlights
                marked_line_num = self.__line_marker.on_logs_changed(self.__filtered_logs, marked_log_id)
                self.__text_highlighter.on_logs_changed(log_view, marked_line_num)

    def toggle_log_options(self):
        """Toggles the display of the log options panel"""
        if self.ui.options_panel.isHidden():
            self.ui.options_panel.show()
            self.ui.toggle_options_button.setArrowType(Qt.RightArrow)
        else:
            self.ui.options_panel.hide()
            self.ui.toggle_options_button.setArrowType(Qt.LeftArrow)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_save_log_snapshot = safe_slot(save_log_snapshot)
    slot_toggle_hiding_prev_logs = safe_slot(toggle_hiding_prev_logs)
    slot_toggle_log_options = safe_slot(toggle_log_options)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_selection_line_numbers(self) -> Tuple[int, int]:
        """
        Convert the positions of a selection in the "Application Log" to the starting line number and the ending
        line number of the selection.

        If the starting line of the selected section is partially selected, the whole line will be considered
        selected; the same rule applies to the ending line.

        :returns: The tuple that contains two elements: the first is the starting index; the second the ending index.
        The indexing is based on the zero-based numbering, i.e., [start_index, end_index).
        """

        cursor = self.ui.log_record_display.textCursor()
        start = cursor.selectionStart()
        end = cursor.selectionEnd()

        if cursor.hasSelection():
            # The user has made a selection. So, we just use it.
            cursor.setPosition(start)
            line_start = cursor.blockNumber()
            cursor.setPosition(end)
            line_end = cursor.blockNumber()
            return line_start, line_end

        # The user didn't select anything. Our design decision is to save everything.
        return 0, self.ui.log_record_display.blockCount() - 1

    def __on_new_log_record(self, log_info: LogMsgInfo):
        """Append a message to the log view, and scrolls to it."""
        log_view = self.ui.log_record_display
        if self.__text_horiz_slider_moved:
            current_scroll_h = log_view.horizontalScrollBar().value()
        else:
            current_scroll_h = 0

        log_msg = log_info.msg
        with self.__sel_changed_by_self(True):
            with self.__cursor_pos_changed_by_self(True):
                log_view.appendPlainText(log_msg)
                self.__filtered_logs.append(log_info)
                self.__line_marker.on_log_added(log_info)
                self.__text_highlighter.on_log_added(log_view, log_msg)

        vsb = log_view.verticalScrollBar()
        vsb.setValue(vsb.maximum())
        log_view.horizontalScrollBar().setValue(current_scroll_h)

    def __on_filtering_changed(self):
        """
        When filtering changed, we have to display the new list of filtered log messages, and store
        the log index of each line. We also attempt to highlight the line that was highlighted
        before filtering changed, and highlight the text that was highlighted, if any.
        """
        self.__filtered_logs, marked_log_id = self.__logs_hider.on_logs_changed(
            self.__log_capture.get_filtered_log_history(), self.__line_marker.get_marked_log_id())
        log_view = self.ui.log_record_display
        with self.__sel_changed_by_self(True):
            with self.__cursor_pos_changed_by_self(True):
                log_view.setPlainText('\n'.join(log_info.msg for log_info in self.__filtered_logs))
                # update highlights
                marked_line_num = self.__line_marker.on_logs_changed(self.__filtered_logs, marked_log_id)
                self.__text_highlighter.on_logs_changed(log_view, marked_line_num)

    def __on_text_horiz_slider_moved(self):
        """When slider moves horizontally, need to restore it when log added later"""
        self.__text_horiz_slider_moved = True

    def __on_selection_changed(self):
        """Highlight all occurrences of the currently selected item, if any."""
        if self.__sel_changed_by_self:
            return

        log_view = self.ui.log_record_display
        with self.__sel_changed_by_self(True):
            with self.__cursor_pos_changed_by_self(True):
                self.__text_highlighter.on_selection_changed(log_view)

    def __on_cursor_pos_changed(self):
        """Handle changing of cursor position by user (do not handle if changed by self)."""
        if self.__cursor_pos_changed_by_self:
            return

        log_view = self.ui.log_record_display
        cursor = log_view.textCursor()
        if cursor.hasSelection():
            return

        if log_view.blockCount() == 0:
            return

        cursor = log_view.textCursor()
        line_clicked = cursor.blockNumber()  # first line is 0
        if self.__logs_hider.is_line_markable(line_clicked):
            log_id = self.__line_marker.mark_line(line_clicked, self.__filtered_logs)
            self.__logs_hider.on_log_marked(log_id, self.__filtered_logs)
            self.__text_highlighter.mark_line(log_view, cursor)

    __slot_on_new_log_record = safe_slot(__on_new_log_record)
    __slot_on_filtering_changed = safe_slot(__on_filtering_changed)
    __slot_on_text_horiz_slider_moved = safe_slot(__on_text_horiz_slider_moved)
    __slot_highlight_selection = safe_slot(__on_selection_changed)
    __slot_cursor_pos_changed = safe_slot(__on_cursor_pos_changed)
