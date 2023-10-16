# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Origame GUI Application
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from logging.handlers import MemoryHandler as LogMemHandler
import sys
import os
from pathlib import Path
import shutil
import traceback
from platform import python_version
from argparse import ArgumentParser
from textwrap import indent, dedent

# [2. third-party]
from PyQt5.QtCore import QThread, QSettings, QObject, Qt, qInstallMessageHandler, QTimer
from PyQt5.QtWidgets import QMessageBox, QApplication
from PyQt5.QtGui import QIcon, QFontDatabase

import appdirs

# [3. local]
# substitution magic for signaling backend must happen before the first backend import
class GuiLogCacher(LogMemHandler):
    """
    This class captures all log messages until the GUI's app panel is ready to show them.
    It must be instantiated, and hence defined, before any Origame code is imported or used,
    so that all Origame log messages are captured.
    """

    def __init__(self):
        CAPACITY = 5
        LogMemHandler.__init__(self, CAPACITY)
        self.__log = logging.getLogger('system')
        self.__log.addHandler(self)
        # don't know yet (only once command line parsed) what log level to be at, so keep all:
        self.__log.setLevel(logging.DEBUG)

    def send_all(self, target: logging.Handler):
        self.setTarget(target)
        target.addFilter(self.__filter)
        self.flush()
        target.removeFilter(self.__filter)
        self.__log.removeHandler(self)

    def __filter(self, record: logging.LogRecord):
        return record.levelno >= self.__log.getEffectiveLevel()


log_cacher = GuiLogCacher()

import origame.gui

from origame.core import LoggingCmdLineArgs, BaseCmdLineArgsParser
from origame.core import LogManager, override_optional, override
from origame.core.typing import Callable

from origame.gui.constants import BACKEND_THREAD_OBJECT_NAME
from origame.gui import MainWindow, about
from origame.gui.async_methods import AsyncRequest, IAsyncErrorHandler, AsyncErrorInfo
from origame.gui.gui_utils import exec_modal_dialog, qt_log_catcher, DEFAULT_FONT_MONO_PATH, install_default_fonts
from origame.gui.gui_utils import get_icon_path
from origame.gui.safe_slot import set_safe_slot_exception_handler, safe_slot
from origame.gui.slow_tasks import shutdown_slow_tasks
from origame.gui.backend_bridge import init_ext_sig_engine

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

# each module has its own "global" instance of log for logging messages:
log = logging.getLogger('system')

AnySlot = Callable[..., None]


# -- Function definitions -----------------------------------------------------------------------

def load_font_defaults():
    """Load the fonts that will be used by the application"""
    assert QApplication.instance() is not None  # VERY important!

    font_loading_result = QFontDatabase.addApplicationFont(DEFAULT_FONT_MONO_PATH)
    if font_loading_result == -1:
        log.warning("Cannot load the font {}", DEFAULT_FONT_MONO_PATH)
    else:
        fdb = QFontDatabase()
        install_default_fonts(fdb.font('Consolas', 'Normal', 10), fdb.font('DejaVu Sans Mono', 'Normal', 10))


# -- Class Definitions --------------------------------------------------------------------------

class SafeSlotExcHandler:
    """Functor class to handle exceptions raised in methods used as PyQt slots"""

    def __call__(self, slot: AnySlot, traceback_str: str):
        log.error("Error in 'safe' slot {}", slot)
        log.error(traceback_str)

        msg_template = '''\
            BUG: a slot raised an exception:

                Slot: {}

            {}
            Continue with caution!'''
        msg = dedent(msg_template).format(slot.__qualname__, indent(traceback_str, 4 * ' '))

        exec_modal_dialog("SafeSlot Error", msg, QMessageBox.Critical)


class GlobalAsyncErrorHandler(IAsyncErrorHandler):
    """
    Used whenever there is an error in the async call (typically ok) or response callback (the latter
    indicates a bug).
    """

    def __init__(self, main_win: MainWindow):
        self._main_win = main_win

    @override(IAsyncErrorHandler)
    def on_call_error(self, exc: AsyncErrorInfo):
        log_msg = 'Error in async request function {}: {}'.format(exc.call_obj, exc.msg)
        log.error(log_msg)
        log.error(exc.traceback)

        ui_msg = 'Error in async operation: {} (the log view may have more info).'.format(exc.msg)
        exec_modal_dialog("Async Call Error (global)", ui_msg, QMessageBox.Critical, parent=self._main_win)

    @override(IAsyncErrorHandler)
    def on_response_cb_error(self, exc: AsyncErrorInfo):
        msg = 'BUG: Error in async response callback {}: {}'.format(exc.response_cb, exc.msg)
        log.error(msg)
        log.error(exc.traceback)
        exec_modal_dialog("Async Response Callback Error", msg, QMessageBox.Critical, parent=self._main_win)


class GuiCmdLineArgs(BaseCmdLineArgsParser):
    def __init__(self):
        # NOTE: each argument must have a default so that ArgumentParser automatically creates the
        # attribute in the Namespace object returned from parse_args()
        log_clap = LoggingCmdLineArgs()
        super().__init__(parents=[log_clap])

        self.add_argument("-f", "--scenario-path", default=None, type=str, help="Which scenario to load")
        self.add_argument("--dev-check-safe-slot-overrides", default=False, action='store_true',
                          help="Which scenario to load")
        self.add_argument("-s", "--clear-settings", default=False, action='store_true',
                          help="Clear GUI settings on startup")


def exception_hook(*exc_info):
    """
    Exceptions that are not caught by application get caught by PyQt and printed to stderr. In some
    cases, PyQt just exits (this is documented behavior). This hook prevents exit and shows
    error message box.
    """
    tb_lines = traceback.format_exception(*exc_info)
    msg = "Oh no! Report this error immediately by saving the log " \
          "file after pressing OK and emailing it to Origame admin!!!\n\n{}"
    tb_msg = ''.join(tb_lines)
    print('uncaught error:', msg.format(tb_msg))
    gui_app = QApplication.instance()
    if gui_app is None:
        gui_app = QApplication(sys.argv)
    exec_modal_dialog("Origame Application Error",
                      msg.format(tb_msg),
                      QMessageBox.Critical)


class GuiMain(QObject):
    """
    Main driver for GUI variant: sets up (from cmd line args, fonts, etc), creates application, creates backend
    thread, main window, etc.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, config_from_cmdline: bool = True):
        """
        Create all objects needed for running.
        """
        QObject.__init__(self)
        log.info('Origame {} (Python {}, PyQt {}, Qt {}, SIP {})',
            about.RELEASE_VERSION, python_version(),
            about.PYQT_VERSION_STR, about.QT_VERSION_STR, about.SIP_VERSION_STR)

        qInstallMessageHandler(qt_log_catcher)
        set_safe_slot_exception_handler(SafeSlotExcHandler())

        self.__settings = None
        self.__setup_from_cmdline(config_from_cmdline)

        self.__setup_logging()
        self.__setup_safe_signaling()

        self._gui_app = None
        self.__get_app_instance()
        self._show_splash_screen()

        self.__setup_from_saved_settings()

        self.__backend_thread = QThread()
        self.__backend_thread.setObjectName(BACKEND_THREAD_OBJECT_NAME)
        init_ext_sig_engine(self.__backend_thread)
        AsyncRequest.set_target_thread(self.__backend_thread)

        self.__main_window = None
        self._setup_main_window()

    def settings_dir(self) -> str:
        """Get the folder in which settings can be saved, for restoring at later session"""
        return self.user_app_dir()

    def user_app_dir(self) -> str:
        """Return the user's APPDATA folder for the GUI variant of this app"""
        user_app_data_dir = Path(appdirs.user_data_dir(appauthor='DRDC', appname='OrigameGui'))
        if not user_app_data_dir.exists():
            user_app_data_dir.mkdir(parents=True)  # should raise if cannot create
        assert user_app_data_dir.exists()
        return str(user_app_data_dir)

    @property
    def main_window(self) -> MainWindow:
        """Get the app's main window (useful for unit tests)"""
        return self.__main_window

    def exec(self) -> int:
        """
        Create the GUI visuals, logger, and logic, and enter event loop.
        :return: the QApplication.exec() return value.
        """
        log.info('GUI started and entering (GUI) event loop')
        self.__backend_thread.start()

        # enter event loop (blocks until app quit)
        exit_code = self._gui_app.exec()
        shutdown_slow_tasks()

        log.info('(GUI) Event loop done: exiting GUI')
        return exit_code

    def exit(self):
        """
        Force exit of the application without checking for unsaved changes. Used for tests.
        """
        self.__shutdown()

    @property
    def backend_thread(self):
        """Get the backend thread object. Move Scenario manager etc to this thread."""
        return self.__backend_thread

    def get_app_log(self) -> Path:
        """Get the path to the application's log file (None if --save-log was given)"""
        path = self.__log_mgr.logfile_path
        return Path(path) if path else None

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_optional
    def _setup_app_info(self):
        """
        Called automatically during initialization. The lines marked REQUIRED for QSettings() methods MUST
        be executed in order for a QSettings() (i.e. a QSettings without init args) to work properly. When
        they are not set, attempting to set a property on the QSettings() instance will return False.

        Derived classes should set this as appropriate (for example, so test suite uses its own registry settings).
        """
        self._gui_app.setApplicationDisplayName("Origame")
        self._gui_app.setApplicationName("Origame")
        self._gui_app.setOrganizationDomain("ca")
        self._gui_app.setOrganizationName("cae")

    @override_optional
    def _show_splash_screen(self):
        """Derived class should set this as appropriate (for example, so no splash"""
        self.__splash = about.get_splash_screen()
        self.__splash.show()
        self._gui_app.processEvents()

        # make splash screen disappear after a short time if user hasn't clicked it:
        SPLASH_MAX_DISPLAY_TIME = 5000
        QTimer.singleShot(SPLASH_MAX_DISPLAY_TIME, self.__splash.close)

    @override_optional
    def _setup_main_window(self):
        """Derived class can override if a different main window (or no main window, for testing) is required"""
        try:
            self.__main_window = MainWindow(self.__backend_thread, self.__settings,
                                            settings_dir=self.settings_dir(), log_cacher=log_cacher)
            self.__main_window.ui.action_restore_default_view.triggered.connect(self.__slot_on_restore_default_view)
            self.__main_window.sig_exit.connect(self.__slot_on_shutdown, Qt.QueuedConnection)
            AsyncRequest.set_global_error_handler(GlobalAsyncErrorHandler(self.__main_window))

        except Exception as exc:
            from traceback import format_exc
            exec_modal_dialog('Startup Failed', 'Exception on GUI creation: {}'.format(format_exc()),
                              QMessageBox.Critical)
            raise

        # Moves the application window to the main monitor when switching from dual to single monitors.
        desktop = QApplication.desktop()
        desktop_width = desktop.screenGeometry().width()
        desktop_height = desktop.screenGeometry().height()
        desktop_top_left = desktop.screenGeometry().topLeft()
        main_win_width = self.__main_window.width()
        main_win_height = self.__main_window.height()
        self.__main_window.move(int((desktop_width - main_win_width) / 2), int((desktop_height - main_win_height) / 2))

        # set size of main window:
        top_margin = 50  # Prevents the application top bar from disappearing above the screen when minimized
        side_margin = 100  # Ensures that the app width and height values do not exceed the desktop size
        self.__main_window.setGeometry(desktop_top_left.x(), desktop_top_left.y() + top_margin,
                                       desktop_width - side_margin, desktop_height - side_margin)

        # next line is a hack so that the GUI is visible on the main monitor when origame is re-opened and the
        # last monitor that was used is not available (such as laptop undocked):
        self.__main_window.showMaximized()

        self.__main_window.show()

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __setup_from_cmdline(self, config_from_cmdline):
        self.__settings = GuiCmdLineArgs().parse_args() if config_from_cmdline else GuiCmdLineArgs.get_defaults()

    def __setup_app_styles(self):
        # set global stylesheet for application:
        stylesheet_path = Path(origame.gui.__file__).with_name("stylesheet.qss")
        self._gui_app.setStyleSheet(stylesheet_path.read_text())

    def __setup_from_saved_settings(self):
        s = QSettings()  # singleton
        if self.__settings.clear_settings:
            log.warning('GUI settings will be cleared')
        if self.__settings.clear_settings or s.value("needs_setup", True, type=bool):
            self.__restore_default_settings()

    def __setup_safe_signaling(self):
        if self.__settings.dev_check_safe_slot_overrides:
            safe_slot.CHECK_OVERRIDES_MISSING = True

        # warn user if checking; outside of previous "if settings" in case already set programmatically:
        if safe_slot.CHECK_OVERRIDES_MISSING:
            log.debug("WARNING: Will check for missing overrides in classes that have overridden safe_slot methods")

    def __setup_logging(self):
        self.__log_mgr = LogManager(log_level=self.__settings.log_level)
        if self.__settings.save_log:
            folder = Path(self.user_app_dir()) / "Logs"
            self.__log_mgr.log_to_file(path=str(folder), filename='log-{}.csv'.format(os.getpid()),
                                       create_path=True)
            self.__log_mgr.cleanup_files('log-*.csv', path=str(folder))

    def __get_app_instance(self):
        if self._gui_app is not None:
            assert QApplication.instance() is self._gui_app
        self._gui_app = QApplication.instance()
        if self._gui_app is None:
            log.debug("Creating new QApplication instance")
            self._gui_app = QApplication(sys.argv)

            # Set initial properties of the QApplication (required before using QSettings)
            self._setup_app_info()

            window_icon = QIcon(get_icon_path('ori_application.ico'))
            self._gui_app.setWindowIcon(window_icon)

            load_font_defaults()
            self.__setup_app_styles()

        else:
            log.warning("QApplication instance already exists")
            # WARNING: the previous QApplication instance may have had a different application name etc
            self._setup_app_info()

    def __shutdown(self):
        """Exit the application: close main window, quit the backend thread, quit the GUI event loop"""
        if self.__main_window is not None:
            self.__main_window.close(safeguard_changes=False)

        log.info("Waiting for backend thread to exit")
        self.__backend_thread.quit()
        self.__backend_thread.wait()
        self._gui_app.processEvents()
        self._gui_app.sendPostedEvents()

        log.info("Quitting main event loop")
        self._gui_app.quit()

    def __restore_default_settings(self):
        """
        Clears settings, and loads them back from original "default.ini", and overwrite current default.ini.
        Performed the first time the program is run, or after a clear settings, and when user asks to reset to
        default view.
        """
        user_settings_filename = Path(self.settings_dir(), "default.ini")
        try:
            import origame.gui
            app_defaults_filename = Path(origame.gui.__file__).with_name("default.ini")
            shutil.copyfile(str(app_defaults_filename), str(user_settings_filename))
            log.info("GuiMain: Created user-settings file {}", user_settings_filename)
        except:
            log.error("GUI unable to create user-settings file: {}", user_settings_filename)
            log.warning("GUI will start without settings, may look ugly!")
            raise

        # load settings from INI file into non-singleton QSettings
        default_settings = QSettings(str(user_settings_filename), QSettings.IniFormat)

        # blank out all previous app settings and copy settings into QSettings singleton so available everywhere in GUI
        current_settings = QSettings()
        current_settings.clear()
        for key in default_settings.allKeys():
            current_settings.setValue(key, default_settings.value(key))
        if current_settings.allKeys():
            log.info("Restored default settings from: {}", user_settings_filename)
        else:
            log.error("No default.ini file found. Starting with clean settings.")

        current_settings.setValue("needs_setup", False)

    def __restore_default_view(self):
        """
        Method used to restore Orgiame to a default view state.
        """
        self.__restore_default_settings()
        if self.__main_window is not None:
            self.__main_window.set_window_configuration(set_window_geometry=False)

    __slot_on_restore_default_view = safe_slot(__restore_default_view)
    __slot_on_shutdown = safe_slot(__shutdown)


if __name__ == '__main__':
    sys.excepthook = exception_hook
    gui = GuiMain()
    exit_code = gui.exec()
    # Oliver FIXME build 3: next line causes a crash on exit (see RH-343), intermittent, for certain types of parts
    #     perhaps because the SystemExit exception raised by sys.exit causes cleanup of objects in a different order
    #     than if just run off the end of the script
    # sys.exit(exit_code)
