# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Main Window and related classes module.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path
import argparse

# [2. third-party]
from PyQt5.QtCore import QCoreApplication, QSettings, QRect, QByteArray, QPoint, QSize, pyqtSignal, QThread
from PyQt5.QtWidgets import QMainWindow, qApp, QApplication, QMessageBox, QAction
from PyQt5.QtWidgets import QFileDialog, QWidget, QDockWidget, QStyle
from PyQt5.QtGui import QMoveEvent, QResizeEvent, QCloseEvent, QCursor
from PyQt5.Qt import Qt

# [3. local]
from ..core import override
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO, AnnotationDeclarations
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..scenario import ScenarioManager
from ..scenario.defn_parts import BasePart
from ..scenario.part_execs import PyDebugger
from ..scenario.alerts import IScenAlertSource
from ..batch_sim import BatchSimManager

from .part_editors import ScenarioPartEditorDlg
from .Ui_mainwindow import Ui_MainWindow
from .scenario_browser import ScenarioBrowserPanel
from .log_panel import LogPanel
from .object_properties.object_properties import ObjectPropertiesPanel
from .sim import SimEventQueuePanel, BatchSimManagerBridge, MainSimBridge
from .alerts_display import AlertsPanel
from .sim.main import MainSimulationControlPanel
from .sim.batch import BatchSimulationControlPanel
from .status_bar import OriStatusBar
from .actor_2d_view import Actor2dPanel, ExpansionStatusEnum
from .menu_commands import ScenarioManagerBridge, HelpManager
from .debugging import PyDebuggerBridge
from .safe_slot import safe_slot
from .async_methods import AsyncRequest
from .undo_manager import scene_undo_stack
from .gui_utils import get_scenario_font, exec_modal_dialog, try_disconnect

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # defines module members that are public; one line per string
    'MainWindow',
]

log = logging.getLogger("system")

AfterCheckCB = Callable[[], None]

try:
    from ctypes import windll  # Only exists on Windows.
    app_id = 'Canada.DRDC.ORIGAME'
    windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
except ImportError:
    pass

class Decl(AnnotationDeclarations):
    GuiLogCacher = 'GuiLogCacher'

# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """
    Main Window for origame application

    Most overrides are from QWidget. For full API Documentation, see
    http://qt-project.org/doc/qt-5/qwidget.html
    """

    # --------------------------- class-wide data and signals -----------------------------------

    sig_exit = pyqtSignal()  # emitted when the application controller must shutdown
    sig_expansion_changed = pyqtSignal(int, int)  # dock area, and ExpansionStatusEnum

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, backend_thread: QThread, settings: argparse.Namespace, settings_dir: str = None,
                 log_cacher: Decl.GuiLogCacher = None):
        QMainWindow.__init__(self)
        self.__check_unsaved_changes = True
        self.__settings_dir = settings_dir

        # designer ui file integration:
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)

        self.ui.help_view.ui.label_part_name.setFont(get_scenario_font())

        # multithread:
        PyDebugger.set_user_action_callback(QCoreApplication.processEvents, backend_thread)

        # replace mockup widgets with working ones:
        self.__scenario_manager = ScenarioManager(backend_thread)
        self.__scenario_manager.config_logging(settings)
        self.__scenario_manager.set_future_anim_mode_dynamic()

        if PyDebugger.get_singleton():
            self.__uil_debugger = PyDebuggerBridge(self.__scenario_manager, debug_win_parent=self)

        self.__2d_panel = Actor2dPanel(self.__scenario_manager)
        scene_undo_stack().actor_2d_panel = self.__2d_panel

        self.__uil_file_commands = ScenarioManagerBridge(scenario_manager=self.__scenario_manager,
                                                         on_close_editors_callback=self.close_part_editors,
                                                         changed_part_editors=self.get_changed_part_editors,
                                                         ui=self.ui)
        self.__uil_file_commands.sig_exit.connect(self.sig_exit)

        self.__uil_help_commands = HelpManager()

        self.__scenario_browser = ScenarioBrowserPanel(self.__scenario_manager)
        self.ui.scenario_browser_dock.setWidget(self.__scenario_browser)

        self.ui.log_panel_dock.setWidget(LogPanel(log_cacher=log_cacher))

        # Object Properties Panel
        self.__object_properties_panel = ObjectPropertiesPanel()
        self.ui.object_properties_dock.setWidget(self.__object_properties_panel)

        self.__sim_event_queue_panel = SimEventQueuePanel(self.__scenario_manager)
        self.ui.event_queue_dock.setWidget(self.__sim_event_queue_panel)
        self.__2d_panel.sig_filter_events_for_part.connect(self.__sim_event_queue_panel.slot_on_filter_events_for_part)
        self.__2d_panel.sig_open_part_editor.connect(self.slot_on_open_part_editor)

        # Alerts Panel
        self.__alerts_panel = AlertsPanel(self.__scenario_manager)
        self.ui.alerts_dock.setWidget(self.__alerts_panel)
        self.__alerts_panel.sig_go_to_part.connect(self.__2d_panel.slot_show_part_in_parent_actor)

        # scenario part editors:
        self.__open_editors = dict()

        # set some standard icons on the actions:
        self.ui.action_open.setIcon(qApp.style().standardIcon(QStyle.SP_DialogOpenButton))
        self.ui.action_save.setIcon(qApp.style().standardIcon(QStyle.SP_DialogSaveButton))

        # Connect some actions to our own slots
        self.ui.action_save_settings.triggered.connect(self.slot_save_settings)
        self.ui.action_new.triggered.connect(self.__slot_new_scenario)
        self.ui.action_open.triggered.connect(self.__slot_load_scenario)
        self.ui.action_save.triggered.connect(self.__uil_file_commands.slot_save_scenario)
        self.ui.action_save_as.triggered.connect(self.__uil_file_commands.slot_save_scenario_as)
        self.ui.action_import.triggered.connect(self.__uil_file_commands.slot_import_scenario)
        self.ui.action_export.triggered.connect(self.__uil_file_commands.slot_export_scenario)
        self.ui.action_quit.triggered.connect(self.__slot_on_close_requested)

        # Populate the Edit menu with actions from 2D panel
        for action in self.__2d_panel.get_edit_actions():
            self.ui.menu_edit.addAction(action)

        # Connect the 'Content View' actions
        self.ui.menu_part_view_mode.addAction(self.__2d_panel.view_actions.action_override_none)
        self.ui.menu_part_view_mode.addAction(self.__2d_panel.view_actions.action_override_full)
        self.ui.menu_part_view_mode.addAction(self.__2d_panel.view_actions.action_override_minimal)
        self.ui.menu_part_view_mode.addAction(self.__2d_panel.view_actions.action_zoom_to_fit_all)
        self.ui.menu_part_view_mode.addAction(self.__2d_panel.view_actions.action_zoom_to_selection)

        # Connect Help actions
        self.ui.action_python_tutorials.triggered.connect(self.__uil_help_commands.slot_on_action_python_tutorials)
        self.ui.action_python_reference.triggered.connect(self.__uil_help_commands.slot_on_action_python_reference)
        self.ui.action_user_manual.triggered.connect(self.__uil_help_commands.slot_on_action_user_manual)
        self.ui.action_show_examples.triggered.connect(self.__uil_help_commands.slot_on_action_examples)
        self.ui.action_parts_reference.triggered.connect(self.__uil_help_commands.slot_on_action_parts_reference)
        self.ui.actionAbout_2.triggered.connect(self.__uil_help_commands.slot_on_action_about)

        # Connect to Scenario Manger to update MainWindow title
        self.on_scenario_filepath_changed('')  # No file loaded at start up
        self.__scenario_manager.signals.sig_scenario_filepath_changed.connect(
            self.slot_on_scenario_filepath_changed)  # Update on Load

        # Simulation related
        batch_sim_manager = BatchSimManager(self.__scenario_manager, app_settings=settings, bridged_ui=True)

        main_control_status_panel = MainSimulationControlPanel(self.__scenario_manager)
        batch_control_status_panel = BatchSimulationControlPanel(batch_sim_manager,
                                                                 self.__scenario_manager,
                                                                 self.__uil_file_commands.save_scenario_as_cb)
        self.ui.main_simulation_control_dock.setWidget(main_control_status_panel)
        self.ui.batch_simulation_control_dock.setWidget(batch_control_status_panel)

        # Add a menu item for each dock widget to the view menu
        # Note: this must be done AFTER all dock widgets are set
        for dock_wid in self.findChildren(QDockWidget):
            self.ui.menu_view.addAction(dock_wid.toggleViewAction())

        self.__uil_batch_sim = BatchSimManagerBridge(batch_sim_manager)
        self.ui.action_start_batch_simulation.setEnabled(False)
        self.ui.action_start_batch_simulation.triggered.connect(self.__uil_batch_sim.slot_run_batch)
        batch_sim_settings = self.ui.action_batch_simulation_settings
        batch_sim_settings.triggered.connect(batch_control_status_panel.slot_on_action_open_settings)

        main_sim_settings = self.ui.action_main_sim_settings
        main_sim_settings.triggered.connect(main_control_status_panel.slot_on_settings_button_clicked)

        self.__uil_main_sim = MainSimBridge(self.__scenario_manager,
                                            self.ui,
                                            main_control_status_panel.main_sim_shared_button_states)

        # Attach 'clear event queue' buttons from various locations to single slot on the Main Sim Manager
        self.__sim_event_queue_panel.sig_clear_event_queue.connect(self.__uil_main_sim.slot_on_clear_queue)
        main_control_status_panel.sig_clear_event_queue.connect(self.__uil_main_sim.slot_on_clear_queue)
        self.__sim_event_queue_panel.sig_enable_event_queue.connect(
            main_control_status_panel.main_sim_shared_button_states.slot_on_enable_clear_event_queue)

        # Status bar
        self.ui.status_bar = OriStatusBar(self.__scenario_manager, batch_sim_manager, parent=self)
        self.setStatusBar(self.ui.status_bar)

        # central widget:
        self.ui.dummy_label.deleteLater()
        self.setCentralWidget(self.__2d_panel)

        # GUI inter-component connections:
        if self.__scenario_browser is not None:
            hierarchy_panel = self.__scenario_browser.actor_hierarchy_panel
            hierarchy_panel.sig_user_selected_part.connect(self.__2d_panel.slot_nav_to_actor)
            hierarchy_panel.sig_context_help_changed.connect(self.__slot_update_context_help)
            self.__2d_panel.sig_part_opened.connect(hierarchy_panel.slot_on_actor_part_opened)
            self.__scenario_browser.sig_search_hit_selected.connect(self.__2d_panel.slot_show_part_in_parent_actor)

        self.__2d_panel.sig_part_selection_changed.connect(
            self.__object_properties_panel.slot_on_object_selection_changed)

        self.__2d_panel.sig_alert_source_selected.connect(self.__alerts_panel.slot_on_alert_source_selected)
        self.__2d_panel.sig_alert_source_selected.connect(self.__slot_on_alert_source_selected)
        self.__2d_panel.sig_part_selection_changed.connect(self.__uil_file_commands.slot_on_part_selection_changed)
        self.__2d_panel.sig_update_context_help.connect(self.__slot_update_context_help)
        self.__2d_panel.sig_reset_context_help.connect(self.__slot_reset_context_help)
        self.__2d_panel.sig_part_opened.connect(self.__uil_file_commands.slot_on_actor_part_selected)
        self.__scenario_manager.signals.sig_save_enabled.connect(self.__slot_enable_save)

        self.set_window_configuration()
        self.__init_dock_buttons()

        # Give initial focus to the central panel:
        self.__2d_panel.view.setFocus()
        self.__current_edit_context_panel = self.__2d_panel

        # Attach focus changed signal to manage context-based Edit menu
        qApp.focusChanged.connect(self.__slot_on_edit_context_changed)

        def init_scen():
            if settings.scenario_path:
                self.__scenario_manager.load(settings.scenario_path)
            else:
                self.__scenario_manager.new_scenario()

        AsyncRequest.call(init_scen)

    @override(QWidget)
    def close(self, safeguard_changes: bool = True):
        """
        Close the main window. This will cause closeEvent() to be called and go through regular checks.
        """
        self.__check_unsaved_changes = safeguard_changes
        if safeguard_changes:
            self.save_dockable_state()
        QMainWindow.close(self)  # NOTE: will generate a QCloseEvent
        self.__check_unsaved_changes = False

    @override(QWidget)
    def moveEvent(self, evt: QMoveEvent):
        """  override from QWidget, called whenever the widget is moved. """
        super().moveEvent(evt)
        self.save_dockable_state()

    @override(QWidget)
    def resizeEvent(self, evt: QResizeEvent):
        """
        override from QWidget, called whenever the widget is resized.
        :param evt:  QResizeEvent
        :return:
        """
        super().resizeEvent(evt)
        self.save_dockable_state()

    @override(QWidget)
    def closeEvent(self, evt: QCloseEvent):
        """
        Called when the main window's X button in title bar is clicked, or when the close() method is called.
        """
        # If this gets called by close(True), then this method will initiate an asynchronous
        # check for unsaved changes and return before the result is known (basically, delaying the actual
        # close until the result is known; the check can also involve aborting the close if the user
        # decides to cancel the exit to not loose changes).
        #
        # After all the checks are done, the app instance will get main window sig_exit signal, which will call
        # close(False) which in turn will call this closeEvent() *a second time* but this time, without
        # checking for unsaved changes.

        if self.__check_unsaved_changes:
            self.__on_close_requested()
            evt.ignore()

        else:
            evt.accept()
            if self.__uil_debugger is not None:
                self.__uil_debugger.force_close()
            QMainWindow.closeEvent(self, evt)

    def set_window_configuration(self, set_window_state: bool = True, set_window_geometry: bool = True):
        """
        Sets the Main Window configuration: dock-widget configuration and window geometry.
        Settings are retrieved from the applications QSettings.
        :param set_window_state: boolean flag indicates if window dock configuration should be set.
        :param set_window_geometry: boolean flag indicates if the geometry should be set.
        """

        # Restore previous settings
        s = QSettings()

        if set_window_state:
            window_state = s.value("window_state", QByteArray(), type=QByteArray)
            if not window_state.isEmpty():
                self.restoreState(window_state)

        if set_window_geometry:
            self.setGeometry(s.value("geometry", QRect(QPoint(100, 100), QSize(1200, 900))))

    @property
    def scenario_manager(self) -> ScenarioManager:
        """Get the Scenario Manager instance used by the main window"""
        return self.__scenario_manager

    @property
    def actor_2d_panel(self) -> Actor2dPanel:
        """Get the Actor2dPanel instance used by the main window"""
        return self.__2d_panel

    @property
    def scenario_browser(self) -> ScenarioBrowserPanel:
        """Get the Actor2dPanel instance used by the main window"""
        return self.__scenario_browser

    @property
    def object_properties_panel(self) -> ObjectPropertiesPanel:
        """Get the ObjectPropertiesPanel instance used by the main window"""
        return self.__object_properties_panel

    def on_scenario_filepath_changed(self, new_path: str):
        """Updates the MainWindow title for New and Open actions"""

        # Show the scenario file ahead of the path so that the file name is always visible as per requirements (SRS-103)
        if new_path != '':
            scenario_file = Path(new_path).parts[-1]
        else:
            scenario_file = 'new_scenario.ori'

        main_window_title = 'Scenario: {} [{}]'.format(scenario_file, new_path)
        self.setWindowTitle(main_window_title)
        self.ui.action_start_batch_simulation.setEnabled(True)
        self.__2d_panel.view.setEnabled(True)

    def on_open_part_editor(self, part: BasePart):
        """
        Pop up the editor for the part.
        """
        part_editor = self.__open_editors.get(part.SESSION_ID)
        if part_editor is None:
            log.info("Opening new editor for {}", part)
            part_editor = ScenarioPartEditorDlg(part)
            part_editor.sig_editor_dialog_closed.connect(self.__slot_on_editor_closed)
            part_editor.sig_go_to_part.connect(self.__2d_panel.slot_show_part_in_parent_actor)
            self.__open_editors[part.SESSION_ID] = part_editor
        else:
            log.info("Activating existing editor for {}", part)

        # The following calculations are performed in order to be able to move part editors into the main monitor
        # when going from a two monitor setup to a single monitor setup.  Otherwise, the part editor(s) will open in
        # non-existent monitor.
        desk_rect = QApplication.desktop().screenGeometry(QApplication.desktop().screenNumber(QCursor().pos()))
        desk_width = desk_rect.width()
        desk_height = desk_rect.height()
        editor_width = part_editor.width()
        editor_height = part_editor.height()

        part_editor.move(int(desk_width / 2 - editor_width / 2 + desk_rect.left()),
                         int(desk_height / 2 - editor_height / 2 + desk_rect.top()))

        part_editor.show()
        part_editor.activateWindow()

    def close_part_editors(self, check_for_changes: bool = False) -> bool:
        """
        Force closes open part editor panels without applying changes.

        When the check_for_changes argument is set to True, this method only checks if editor panels are open but does
        not close them. Called when the scenario is about to change (new scenario, load, or exit) or save.
        :return: a boolean indicating if open editors have changes.
        """

        if not self.__open_editors:
            return False  # No editors open, so no changes

        # Search editors for changes OR just close them
        for part_id in self.__open_editors.copy().keys():
            editor = self.__open_editors[part_id]
            if check_for_changes:
                # Check for changes and return when found
                if editor.check_unapplied_changes():
                    return True  # Some or all open editors have changes
            else:
                # Just force close
                editor.disable_checks_on_close()
                editor.close()
                # editor.close() will lead to deletion of the editor from self.__open_editors.

        return False  # No changes present in open editors

    def get_changed_part_editors(self) -> list[ScenarioPartEditorDlg]:
        if not self.__open_editors:
            return []  # No editors open, so no changes

        changed_opened_editors = []

        # Search editors for changes
        for part_id in self.__open_editors.copy().keys():
            editor = self.__open_editors[part_id]
            if editor.check_unapplied_changes():
                changed_opened_editors.append(editor)

        return changed_opened_editors

    def save_settings(self):
        """
        Opens dialog, asks user for save file, and writes settings to file.

        """
        if self.__settings_dir is None:
            return

        (file_name, ok) = QFileDialog.getSaveFileName(self, "Save Settings as...",
                                                      str(Path(self.__settings_dir) / "default.ini"),
                                                      filter="INI files (*.ini)")
        if not ok:
            return
        self.save_dockable_state()
        settings_file = QSettings(file_name, QSettings.IniFormat)
        settings_file.clear()
        s = QSettings()
        for key in s.allKeys():
            settings_file.setValue(key, s.value(key))
        log.info("Saved settings file to: " + file_name)

    def save_dockable_state(self):
        """
        Stores windowState and geometry to QSettings
        """
        s = QSettings()
        s.setValue("geometry", self.geometry())
        s.setValue("window_state", self.saveState())

    def set_busy(self, status: bool = True):
        """Configure the main window to be in "busy" mode, ie no user input except in Log panel and a few others"""
        enabled = not status
        for dock_wid in self.findChildren(QDockWidget):
            if not isinstance(dock_wid.widget(), LogPanel):
                dock_wid.setEnabled(enabled)

        self.ui.menu_edit.setEnabled(enabled)
        self.ui.menu_view.setEnabled(enabled)
        self.ui.menu_simulation.setEnabled(enabled)
        self.ui.menu_help.setEnabled(enabled)

        self.ui.tool_bar.setEnabled(enabled)

    def get_editor_by_part_id(self, part_id: int) -> Either[ScenarioPartEditorDlg, None]:
        """
        Gets the specific editor that is associated with the id of the part that is being edited.

        Note: The original motive of doing this is to facilitate the editor testing.

        :param part_id: The id of the part being edited
        :return The editor or None if the editor cannot be found
        """
        return self.__open_editors.get(part_id)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_scenario_filepath_changed = safe_slot(on_scenario_filepath_changed)
    slot_on_open_part_editor = safe_slot(on_open_part_editor)
    slot_save_settings = safe_slot(save_settings)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_editor_closed(self, part_id: int):
        """
        Removes editors from the list of opened editors.
        :param part_id: The ID of the associated part.
        """
        try_disconnect(self.__open_editors[part_id].sig_go_to_part, self.__2d_panel.slot_show_part_in_parent_actor)
        del self.__open_editors[part_id]

    def __on_close_requested(self):
        """
        Regardless of how the application is closed, this method MUST be called: it asynchronously calls on
        functionality in ScenarioManagerBridge to check if saving changes is required, ask user for confirmation, etc.
        The sig_exit signal will be emitted later but only if the application must shutdown (i.e. if
        close request is dropped in any way, sig_exit is not emitted and application continues).
        """
        self.save_dockable_state()
        self.__uil_file_commands.exit_application()

    def __update_context_help(self, part: BasePart):
        """
        Method used to update the Context Help html when hovering over different part frames within the Actor 2D View.
        :param part: The part within the part frame that a user is hovering over.
        """
        HTML_PARAGRAPH = "<p>"
        TEXT_NEW_LINE = "\n\n"

        part_type = part.PART_TYPE_NAME.capitalize()
        part_name = part.name
        part_description = part.DESCRIPTION.replace(TEXT_NEW_LINE, HTML_PARAGRAPH)

        self.__set_context_help(part_type, part_name, part_description)

    def __reset_context_help(self):

        part_type = '<type of part>'
        part_name = '<name of part>'
        part_description = str()
        self.__set_context_help(part_type, part_name, part_description)

    def __set_context_help(self, part_type: str, part_name: str, part_description: str):

        self.ui.help_view.ui.label_part_type.setText(part_type)
        self.ui.help_view.ui.label_part_name.setText(part_name)
        self.ui.help_view.ui.text_help.setHtml(part_description)

    def __enable_save(self, enable: bool):
        """
        Method used to enable/disable 'Save' action from main menu depending the type of Scenario that has been loaded.
        If a prototype Scenario has been loaded, 'Save' is disabled.  If an Origame Scenario has been loaded, 'Save'
        action is enabled.
        :param enable: Boolean indicating whether or not the 'Save' menu action is enabled or disabled.
        """
        self.ui.action_save.setEnabled(enable)

    def __on_edit_context_changed(self, previous_widget: QWidget, current_widget: QWidget):
        """
        Implements context-based Edit menu actions to switch between scenario-context and text-context edit actions.

        Enables scenario-context editing (i.e. part copy, cut, paste) when either the 2D, Scenario Browser, or Event
        Queue panels have focus. The Edit menu is enabled under this context with the actions pulled from the respective
        panel. Text-context editing is active when any other panel has focus. Under the text-based context, the Edit
        menu actions are disabled which allows for text-based copy and paste operations to proceed without inadvertently
        operating on selected parts or events.
        :param previous_widget: the widget that has lost focus.
        :param current_widget: the widget that currently has focus.
        """

        is_scenario_context, panel = self.__get_panel(current_widget)

        if is_scenario_context:
            # Scenario-context: enable Edit menu options and shortcuts for part-based editing

            # Check if this is the same edit context-based panel from before
            if panel is self.__current_edit_context_panel:
                # Enable edit options that have already been added to the Edit menu
                self.__current_edit_context_panel.update_actions()
                return

            else:
                # This is a new panel with edit context, remove previous actions
                self.__current_edit_context_panel.disable_actions()
                for action in self.__current_edit_context_panel.get_edit_actions():
                    self.ui.menu_edit.removeAction(action)

            # Populate the Edit menu with actions from new panel
            panel.update_actions()
            for action in panel.get_edit_actions():
                self.ui.menu_edit.addAction(action)
            self.__current_edit_context_panel = panel

        else:
            # Text-context: disable part-based editing and Edit menu
            # Allows selected text to be copied (using shortcut keys) without copying selected parts
            self.__current_edit_context_panel.disable_actions()

    def __get_panel(self, current_widget: QWidget) -> Tuple[bool, Optional[QWidget]]:
        """
        Gets the panel with current focus if it has an 'edit' context.
        :param current_widget: the widget that currently has focus.
        :return: a boolean flag that indicates that there are 'scenario'-based editing options for this panel, and the
            panel associated with the current widget of focus.
        """

        if self.__2d_panel.isAncestorOf(current_widget):
            panel = self.__2d_panel

        elif self.__scenario_browser.isAncestorOf(current_widget):
            panel = self.__scenario_browser

        # Mark TODO build 3: add this panel as a 'context' for editing when there are Event Queue Edit menu actions
        # elif self.__sim_event_queue_panel.isAncestorOf(current_widget):
        #     panel = self.__sim_event_queue_panel

        else:
            # No edit context for the current widget/panel
            return False, None

        return True, panel

    def __new_scenario(self):
        """
        Creates a new scenario after checking the parts clipboard for parts to retain in the next scenario.
        """
        self.__check_clipboard_before_next_scenario(menu_cb=self.__uil_file_commands.new_scenario)

    def __load_scenario(self):
        """
        Loads a scenario after checking the parts clipboard for parts to retain in the next scenario.
        """
        self.__check_clipboard_before_next_scenario(menu_cb=self.__uil_file_commands.load_scenario)

    def __check_clipboard_before_next_scenario(self, menu_cb: AfterCheckCB):
        """
        Checks the clipboard for parts, asks the user to keep or discard them, and then executes the menu command.
        :param menu_cb: A menu command to execute. Either a New scenario command or a Load scenario command.
        """

        if not self.__2d_panel.view.is_clipboard_empty():
            # Parts are on the clipboard. Ask user to keep or discard.
            user_input = self.__open_parts_clipboard_dialog()

            if user_input == QMessageBox.Yes:
                self.__2d_panel.view.replace_clipboard_by_ori(menu_cb)

            elif user_input == QMessageBox.No:
                self.__2d_panel.view.clear_parts_clipboard()
                menu_cb()

            else:
                # User cancelled
                return

        else:
            # No parts on the clipboard: run command
            menu_cb()

    def __open_parts_clipboard_dialog(self) -> int:
        """
        Opens a dialog listing all parts on the clipboard and asking if parts should be retained in next scenario.
        **Assumes parts are on the clipboard**
        :return:  A QMessageBox standard button response (Yes, No, or Cancel).
        """
        assert not self.__2d_panel.view.is_clipboard_empty()
        title = 'Parts Clipboard'
        msg = ['The following parts are on the application clipboard:  ']

        parts_on_clipboard = self.__2d_panel.view.parts_clipboard
        MAX_SHOW = 10  # cap the list at 10 to keep dialog short
        parts_list = ['- ' + part.get_path(with_root=True) for part in parts_on_clipboard[:MAX_SHOW]]
        parts_list.sort()
        msg.extend(parts_list)
        if len(parts_on_clipboard) > MAX_SHOW:  # cap the list at 10 for practicality
            msg.append(' plus {} more...'.format(len(parts_on_clipboard) - MAX_SHOW))

        msg.append('')
        msg.append('Click Yes to make them available in the next scenario loaded;')
        msg.append('Click No to empty the clipboard before loading the next scenario;')
        msg.append('Click Cancel to go back to existing scenario without doing anything.')

        return exec_modal_dialog(title, '\n'.join(msg), QMessageBox.Question,
                                 buttons=[QMessageBox.Yes, QMessageBox.No, QMessageBox.Cancel])

    def __init_dock_buttons(self):
        """
        Sets up the signal connection between the panel and the main window. Sends the sig_expansion_changed.
        """
        self.__2d_panel.sig_expansion_change.connect(self.__slot_on_toggle_dock_widgets)
        self.sig_expansion_changed.connect(self.__2d_panel.slot_on_expansion_changed)

        self.__map_dock_widget_to_managed = dict()
        self.__map_dock_widget_to_visibility = dict()
        self.__map_dock_widget_to_selected = dict()

        for dock_wid in self.findChildren(QDockWidget):
            dock_wid.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
            dock_wid.visibilityChanged.connect(self.__slot_on_dock_widget_visibility_changed)
            self.__update_dock_widget_management_status(dock_wid)
            self.__map_dock_widget_to_visibility[dock_wid] = dock_wid.isVisible() and not dock_wid.isFloating()

            self.__update_dock_widget_selection_status(dock_wid)

        for dock_area in [Qt.LeftDockWidgetArea, Qt.RightDockWidgetArea, Qt.BottomDockWidgetArea]:
            dock_area_status, _ = self.__get_dock_status_by_area(dock_area)
            self.sig_expansion_changed.emit(dock_area, dock_area_status)

    def __update_dock_widget_management_status(self, dock_widget: QDockWidget):
        """
        The expansion change operation should act on only those visible components that are inside dock areas before 
        they are collapsed. This function tracks if the given dock widget is managed.
        :param dock_widget: The dock widget whose management status is tracked. 
        """
        self.__map_dock_widget_to_managed[dock_widget] = dock_widget.isVisible() and not dock_widget.isFloating()

    def __update_dock_widget_selection_status(self, dock_widget: QDockWidget):
        """
        Tracks if the given dock widget is really visible in a dock area. If the dock widgets are tabbed in a dock area,
        all of them are visible from Qt's point of view. But we want to know which tab is selected, thus really 
        visible.
        :param dock_widget: The dock widget whose real visibility is tracked.
        """

        # The special technique to check if the particular dock widget is selected. No out-of-the-box Qt
        # mechanism available.
        self.__map_dock_widget_to_selected[dock_widget] = (not dock_widget.visibleRegion().isEmpty()
                                                           and not dock_widget.isFloating())

    def __is_dock_widget_selected(self, dock_widget: QDockWidget) -> bool:
        """
        Since Qt does not offer the mechanism, this function returns True if the given dock widget is selected.
        :param dock_widget: The widget whose selection status is returned.
        :return: True - selected
        """
        return self.__map_dock_widget_to_selected[dock_widget]

    def __trigger_docking(self, visible: bool, actions: Dict[QDockWidget, QAction]):
        """
        Iterates the actions to trigger each action, depending on the "visible".
        :param visible: True - trigger the action with False; False - trigger the action if the the dock widget was
        visible in the dock before it is collapsed.
        :param actions: The actions are from QDockWidget.toggleViewAction of a dock area
        """
        for dock_widget, action in actions.items():
            if visible:
                # "Docking Action" is used to distinguish programmatic docking from manual docking
                dock_widget.toggleViewAction().setData("Docking Action")
                self.__update_dock_widget_management_status(dock_widget)
                self.__update_dock_widget_selection_status(dock_widget)

                action.triggered.emit(not visible)
            else:
                if self.__map_dock_widget_to_managed.get(dock_widget):
                    action.triggered.emit(not visible)

                    if self.__is_dock_widget_selected(dock_widget):
                        dock_widget.raise_()

    def __on_toggle_dock_widgets(self, dock_area: int):
        """
        Slot of the sig_expansion_change.
        
        Toggles the given dock area. Does nothing if the dock area is empty.
        :param dock_area: The area where the dock widgets are toggled. The dock_area is defined in 
        enum Qt::DockWidgetArea in C++, but in PyQt, it is just one of the plain int definitions in the Qt class.
        """
        dock_area_status, actions = self.__get_dock_status_by_area(dock_area)

        if dock_area_status == ExpansionStatusEnum.empty:
            return

        self.__trigger_docking(dock_area_status == ExpansionStatusEnum.visible, actions)

    def __get_dock_status_by_area(self, req_dock_area: int) -> Tuple[ExpansionStatusEnum, Dict[QDockWidget, QAction]]:
        """
        Evaluates the given dock area to determine if the area is empty and visible.
        :param req_dock_area: The area to be evaluated
        :return: True - the dock area is empty, True - the dock area is visible, and the list of the view actions of
        the dock widgets in the given area
        """
        map_dock_widget_to_action = dict()
        num_in_dock = 0
        dock_area_status = ExpansionStatusEnum.invisible
        for dock_wid in self.findChildren(QDockWidget):
            if dock_wid.isFloating():
                # Floating one has to be skipped because floating does not change the area affiliation.
                continue

            dock_area = self.dockWidgetArea(dock_wid)
            if dock_area == req_dock_area:
                if self.__map_dock_widget_to_managed.get(dock_wid):
                    map_dock_widget_to_action[dock_wid] = dock_wid.toggleViewAction()

                    num_in_dock += 1
                if self.__map_dock_widget_to_visibility[dock_wid] and self.__map_dock_widget_to_managed.get(dock_wid):
                    dock_area_status = ExpansionStatusEnum.visible

        if num_in_dock == 0:
            dock_area_status = ExpansionStatusEnum.empty

        return dock_area_status, map_dock_widget_to_action

    def __on_dock_widget_visibility_changed(self, visible: bool):
        """
        Slot of the QDockWidget.visibilityChanged(bool visible)
        Records the visibility of the changed dock widget. Evaluates the docking status (area empty, area visible).
        Sends the sig_expansion_changed.
        :param visible: See the Qt QDockWidget.visibilityChanged(bool visible)
        """
        dock_widget = self.sender()
        if dock_widget.toggleViewAction().data() is None:
            self.__update_dock_widget_management_status(dock_widget)
        else:
            dock_widget.toggleViewAction().setData(None)

        self.__map_dock_widget_to_visibility[dock_widget] = visible and not dock_widget.isFloating()

        intended_dock_area = self.dockWidgetArea(dock_widget)

        dock_area_status, _ = self.__get_dock_status_by_area(intended_dock_area)

        self.sig_expansion_changed.emit(intended_dock_area, dock_area_status)

    def __on_alert_source_selected(self, _: IScenAlertSource):
        """
        Shows the Alerts panel in the dock.
        """
        alerts_dock_area = self.dockWidgetArea(self.ui.alerts_dock)
        if alerts_dock_area == Qt.NoDockWidgetArea:
            return

        dock_area_status, _ = self.__get_dock_status_by_area(alerts_dock_area)
        if dock_area_status == ExpansionStatusEnum.invisible:
            self.__on_toggle_dock_widgets(alerts_dock_area)

        self.ui.alerts_dock.raise_()

    __slot_on_alert_source_selected = safe_slot(__on_alert_source_selected)
    __slot_on_close_requested = safe_slot(__on_close_requested)
    __slot_on_editor_closed = safe_slot(__on_editor_closed)
    __slot_update_context_help = safe_slot(__update_context_help)
    __slot_reset_context_help = safe_slot(__reset_context_help)
    __slot_enable_save = safe_slot(__enable_save)
    __slot_on_edit_context_changed = safe_slot(__on_edit_context_changed, arg_types=['QWidget*', 'QWidget*'])
    __slot_new_scenario = safe_slot(__new_scenario)
    __slot_load_scenario = safe_slot(__load_scenario)
    __slot_on_toggle_dock_widgets = safe_slot(__on_toggle_dock_widgets)
    __slot_on_dock_widget_visibility_changed = safe_slot(__on_dock_widget_visibility_changed)
