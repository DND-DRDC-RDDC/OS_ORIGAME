# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: components related to slow tasks in GUI i.e busy cursor and progress indicator

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum

# [2. third-party]
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QWidget, qApp
from PyQt5.QtGui import QCursor

# [3. local]
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from .Ui_progress_indicator import Ui_ProgressIndicator

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'init_progress_bar',
    'get_progress_bar',
    'ProgressRange',
    'ProgressBusy',
]

log = logging.getLogger('system')

_prog_indicator = None


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ProgressStatusEnum(IntEnum):
    idle, waiting_to_show, visible, visible_after_stop = range(4)


class ProgressBarTypeEnum(IntEnum):
    range, busy = range(2)


class ProgressBar(QWidget):
    """
    Wraps the Qt QProgressBar (created in the setupUi()) to provide one widget which can show either a
    numerical progress (start_progress) to indicate progress from 0 to some maximum, or a business
    (start_busy_progress) which is a progress bar where the bar just goes back and forth. The class
    also manages showing and hiding the bar (when there is a task being monitored, vs no task in progress),
    as well as leaving the bar visible for a short period after the task has completed.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    VISIBLE_AFTER_START_MSEC = 500  # number of milli-seconds to wait before showing progress bar
    VISIBLE_AFTER_STOP_MSEC = 1000  # number of milli-seconds to keep visible after progress stopped

    StartParams = List[Any]  # opaque type (the precise data is not part of public API)

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QWidget, main: QWidget):
        super().__init__(parent)
        self.ui = Ui_ProgressIndicator()
        self.ui.setupUi(self)
        self.hide()

        self.__main_win = main

        self.__wait_after_start_timer = None
        self.__linger_after_stop_timer = None
        self.__start_params = None
        self.__state = ProgressStatusEnum.idle

    def start_busy_progress(self, op_label: str):
        """
        Start progress tracking in "busy" mode, ie where progress values are not available, so the bar just
        goes back and forth, showing application is not hung. Schedules showing of progression, main window
        busy True, etc. Can be called in any state.
        :param op_label: a title for the operation which is being monitored for progress
        """
        self.__start_params = [ProgressBarTypeEnum.busy, op_label]
        self.__wait_user_need_progress(op_label, 0, 0, False, None)

    def start_progress(self, op_label: str, min_value: int = 0, max_value: int = 100, start_value: int = None):
        """
        Start progress tracking. Schedules showing of progression, main window busy True, etc.
        Can be called in any state.

        :param op_label: a title for the operation which is being monitored for progress
        :param min_value: smallest value that will be set via set_progress_value()
        :param max_value: largest value that will be set via set_progress_value()
        :param start_value: value at which to start progression; will be capped by min and max;
            if None, defaults to min_value
        """
        self.__start_params = [ProgressBarTypeEnum.range, op_label, min_value, max_value, start_value]
        self.__wait_user_need_progress(op_label, min_value, max_value, True, start_value)

    def set_progress_value(self, value: int):
        """Set bar at given value"""
        assert self.__start_params[0] is ProgressBarTypeEnum.range
        self.ui.progress_bar.setValue(value)

    def get_progress_value(self) -> int:
        return self.ui.progress_bar.value()

    def pause_progress(self) -> Optional[StartParams]:
        """
        Stop the progress and returns state to idle.
        :returns: an opaque state object that must be given to resume_progress() when ready to resume.
        """
        if self.__start_params is None:
            log.debug('No task in progress, ignoring "pause progress" command')
            return None

        restart_params = self.__start_params
        if restart_params[0] is ProgressBarTypeEnum.range:
            restart_params[-1] = self.ui.progress_bar.value()
        self.stop_progress()
        return restart_params

    def resume_progress(self, start_params: StartParams):
        """
        Resume progress tracking from idle.
        """
        if self.__state is ProgressStatusEnum.idle:
            if start_params is None:
                log.debug('No task was in progress at pause time, ignoring "resume progress" command')
                return

            progress_type, start_params = start_params[0], start_params[1:]
            if progress_type == ProgressBarTypeEnum.range:
                self.start_progress(*start_params)
            else:
                assert progress_type == ProgressBarTypeEnum.busy
                self.start_busy_progress(*start_params)

        else:
            log.debug("Resume ignored: progress tracking already on")

    def stop_progress(self):
        """
        If in progress, indicate that progress has completed. This will schedule the widget for hiding, restoring
        of main window to non-busy etc, after VISIBLE_AFTER_STOP_MSEC have elapsed. Does nothing in other states.
        """
        if self.__state == ProgressStatusEnum.idle:
            assert self.__start_params is None
            return

        if self.__state == ProgressStatusEnum.waiting_to_show:
            log.debug('Stopping progress tracking before wait-to-show elapsed')
            assert self.__wait_after_start_timer is not None
            self.__wait_after_start_timer.stop()
            self.__wait_after_start_timer = None
            self.__state = ProgressStatusEnum.idle
            self.__start_params = None
            return

        if self.__state == ProgressStatusEnum.visible:
            log.debug('Stopping progress tracking, scheduling hiding of bar')
            self.__state = ProgressStatusEnum.visible_after_stop
            self.__start_params = None

            qApp.restoreOverrideCursor()

            if self.__linger_after_stop_timer is not None:
                self.__linger_after_stop_timer.stop()
            self.__linger_after_stop_timer = QTimer()
            self.__linger_after_stop_timer.setSingleShot(True)
            self.__linger_after_stop_timer.timeout.connect(self.__hide)
            self.__linger_after_stop_timer.start(self.VISIBLE_AFTER_STOP_MSEC)

            return

        assert self.__state == ProgressStatusEnum.visible_after_stop
        assert self.__start_params is None
        log.debug('Hiding of progress bar already scheduled')

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __wait_user_need_progress(self, *progress_args):
        """
        Wait until user needs to see the progress cues, unless already showing, then restart the show timer.
        :param progress_args: given verbatim to __start_show_progress
        """
        if self.__state == ProgressStatusEnum.idle:
            log.debug('Scheduling showing of bar')
            self.__state = ProgressStatusEnum.waiting_to_show

            self.__wait_after_start_timer = QTimer()
            self.__wait_after_start_timer.setSingleShot(True)
            self.__wait_after_start_timer.timeout.connect(lambda: self.__start_show_progress(*progress_args))
            self.__wait_after_start_timer.start(self.VISIBLE_AFTER_START_MSEC)
            return

        if self.__state == ProgressStatusEnum.waiting_to_show:
            log.debug('Showing of bar already scheduled')
            return

        assert self.__state in (ProgressStatusEnum.visible, ProgressStatusEnum.visible_after_stop)
        self.__start_show_progress(*progress_args)

    def __start_show_progress(self, op_label: str, min_value: int, max_value: int, show_percent: bool,
                              start_value: int):
        """
        Make the progress cues visible to the user
        :param op_label: a label representing the operation in progress (used if show_text True and in log messages
        :param min_value: min value for progress bar
        :param max_value: max value for progress bar
        :param show_percent: whether or not to show the percentage completion
        :param start_value: starting value for progress
        """
        if start_value is None:
            start_value = min_value

        if max_value == min_value:
            log.debug("Showing progress bar for busy-ness")
        else:
            log.debug("Showing progress bar for range {} to {}, starting at {}", min_value, max_value, start_value)

        self.__wait_after_start_timer = None

        if self.__linger_after_stop_timer is not None:
            self.__linger_after_stop_timer.stop()
            self.__linger_after_stop_timer = None

        self.__set_op_label(op_label)

        progress_bar = self.ui.progress_bar
        progress_bar.setMinimum(min_value)
        progress_bar.setMaximum(max_value)
        progress_bar.reset()
        progress_bar.setValue(start_value)
        progress_bar.setTextVisible(show_percent)

        self.show()

        if self.__state != ProgressStatusEnum.visible:
            self.__state = ProgressStatusEnum.visible
            # only override the cursor while visible:
            qApp.setOverrideCursor(QCursor(Qt.WaitCursor))

        if self.__main_win is not None:
            self.__main_win.set_busy(True)

    def __hide(self):
        """Only hide if another progression hasn't already started"""
        assert self.__state is ProgressStatusEnum.visible_after_stop

        if self.__main_win is not None:
            self.__main_win.set_busy(False)

        log.debug("Hiding progress bar (returning to idle)")

        self.hide()
        self.__state = ProgressStatusEnum.idle

    def __set_op_label(self, title: str):
        self.ui.label_operation.setText(title + ":")


class ProgressStarterBase:
    """
    Base class for task progress context managers: derived classes are context managers during which a progress
    bar will be active, and hidden once the task is over.
    """

    # derived must override with string
    progress_start_method_name = None

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        prog_indicator = get_progress_bar()
        assert prog_indicator is not None
        progress_start_method = getattr(prog_indicator, self.progress_start_method_name)
        self.__init__.__func__.__doc__ = progress_start_method.__doc__

    def __enter__(self) -> ProgressBar:
        args, kwargs = self.args, self.kwargs
        prog_indicator = get_progress_bar()
        progress_start_method = getattr(prog_indicator, self.progress_start_method_name)
        progress_start_method(*args, **kwargs)
        return prog_indicator

    def __exit__(self, exc_type, exc_val, exc_tb):
        get_progress_bar().stop_progress()


class ProgressRange(ProgressStarterBase):
    """
    Context manager for progress bar updates from min to max. Example:

        with ProgressRange('Rendering', max_value=300) as progress:
            for count, something in enumerate(loop):
                do stuff
                progress.set_progress_value(count + 1)
    """

    progress_start_method_name = 'start_progress'

    def __init__(self, op_label: str, min_value: int = 0, max_value: int = 100):
        super().__init__(op_label, min_value, max_value)


class ProgressBusy(ProgressStarterBase):
    """
    Context manager for progress bar with "busy" bar. Example:

        with ProgressBusy('Waiting') as progress:
            do stuff
    """

    progress_start_method_name = 'start_busy_progress'

    def __init__(self, op_label: str):
        super().__init__(op_label)


# define the singleton getter function after class definition, so that code completion on its return value is
# available in IDE:

def init_progress_bar(main: QWidget, parent: QWidget = None, reinit: bool = False) -> ProgressBar:
    """
    Create the singleton progress bar.
    :param main: the main window that hosts the bar (must have a set_busy(bool) method)
    :param parent: the parent widget of the progress bar
    :return: singleton instance
    """
    assert main is not None
    global _prog_indicator
    if _prog_indicator is not None and reinit is False:
        raise RuntimeError('Not allowed to re-init the progress bar!')
    _prog_indicator = ProgressBar(parent, main)
    return _prog_indicator


def get_progress_bar() -> ProgressBar:
    """
    Get the progress bar singleton for status bar. Creates it if it doesn't already exist. Use this method
    to display the bar, but use one of the two ProgressRange/ProgressBusy context managers when
    actually starting a task that requires showing progress to user.
    """
    global _prog_indicator
    if _prog_indicator is None:
        raise RuntimeError("No progress bar has been initialized yet")
    return _prog_indicator


def shutdown_slow_tasks():
    global _prog_indicator
    _prog_indicator = None
