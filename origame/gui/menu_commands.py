# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Classes related to the UI File menu commands

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import webbrowser
from pathlib import Path, PureWindowsPath
import urllib
import subprocess
from enum import IntEnum
import sys

# [2. third-party]
from PyQt5.QtCore import QObject, QSettings, QTimer, pyqtSignal
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QDialogButtonBox

# [3. local]
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..core.typing import AnnotationDeclarations
from ..scenario import ScenarioManager, SaveError, Scenario
from ..scenario.defn_parts import ActorPart, BasePart

from .async_methods import AsyncRequest, AsyncErrorInfo
from .undo_manager import scene_undo_stack
from .gui_utils import exec_modal_dialog
from .safe_slot import safe_slot, ext_safe_slot
from .about import AboutDialog
from .slow_tasks import get_progress_bar, ProgressBusy
from .part_editors import ScenarioPartEditorDlg

import origame  # to find package path since help stored there

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    'ScenarioManagerBridge',
    'HelpManager',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def get_dialog_filter(dialog_type: str):
    """
    Gets the filter string for open and save dialogs.
    :param dialog_type: 'open' or 'save' file operations.
    :return: a string that tells a QFileDialog object what file types to show.
    """

    if dialog_type == 'open':
        dot_ext_list = ['*{}'.format(ext) for ext in ScenarioManager.FILE_EXTENSION_LIST]
        return "Scenarios ({})".format(' '.join(dot_ext_list))
    elif dialog_type == 'save':
        dot_ext_list = ['*{}'.format(ext) for ext in ScenarioManager.FILE_EXTENSION_LIST if
                        ext != ScenarioManager.PROTOTYPE_EXTENSION]
        return "{}".format(';;'.join(dot_ext_list))
    else:
        log.error('file_commands.get_dialog_filter(dialog_type): unrecognized dialog type.')


"""
Signature of callback to be given to ScenarioManagerBridge to close all currently open editors,
potentially asking for confirmation.
:return: True if continue with save, False if cancelled
"""
CloseEditorsCallable = Callable[[], Optional[bool]]

ChangedPartEditors = Callable[[], list[ScenarioPartEditorDlg]]

# -- Class Definitions --------------------------------------------------------------------------

"""
Signature of callback to be given to __check_save_success() to execute when a scenario save operation is
determined to have completed. When a save operation completes, __check_save_success() will call the
'callable' to complete a new, load or exit operation that is underway.
"""
NewLoadExitCallable = Callable[[], bool]

""""
Signature of callback to be given to save_as() to execute when the save operation succeeds or fails.
:param flag: True if save was successfuel and False otherwise.
    """
SaveAsStatusCallable = Callable[[bool], None]

"""
Signature of callback to be given to __on_save_save_as() to execute when a scenario save operation or save-as
is instigated.
:param callback: A callback method to run after the 'save as' operation completes.
:return: True if save executed, False if cancelled by user
"""
SaveAsCallable = Callable[[SaveAsStatusCallable], bool]


class NewLoadExitTypeEnum(IntEnum):
    """
    An enumeration to specify an option for creating a new scenario, loading an existing one, or exiting the
    application.
    """
    new_scenario, load_scenario, exit_application = range(3)


# noinspection PyTypeChecker
class ScenarioManagerBridge(QObject):
    """
    Ui Logic Class that implement File menu commands New, Load, Save, Save As, Import, and Export.

    These commands are actually executed by the Simulation Manager running in a separate ("back-end") thread. This
    class issues asynchronous requests to the back-end Simulation Manager to execute the File menu commands. For most
    commands, only one asynchronous request is required, such as in processing a Save, Save As, Import, or Export
    File command. In the case of processing a New or Load file command, two asynchronous requests are issued in order
    to first check for unsaved changes to the scenario file before clearing it from the application. To work correctly,
    the second request must wait for the a response from the first request, and this is handled via a callback method
    that executes only once the first asynchronous request has returned a confirmation as to the saved status of the
    active scenario. This design results in "loop-closure" for objects that execute asynchronously in different threads.

    All information regarding the scenario file, including its file path and extension(s) are handled by the back-end
    Scenario Manager as well. This additional information is obtained either by accessing the attributes of the
    Scenario Manager class directly (e.g. the file extensions), or by connecting to the object signals that are emitted
    during certain events, such Save operations. The file path to the current scenario is obtained and updated in this
    way.
    """

    DIRPATH_KEY = "dirpath"  # QSettings key
    CHECK_SAVE_DELAY_MSEC = 100  # delay between intermittent checks to confirm a save operation has completed.

    sig_exit = pyqtSignal()

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, scenario_manager: ScenarioManager,
                 on_close_editors_callback: CloseEditorsCallable = None,
                 changed_part_editors: ChangedPartEditors = None, ui: Any = None):
        super().__init__()

        self.__scenario_manager = scenario_manager

        # Connect: Back-End Signals to Front-End Slots
        scenario_manager.signals.sig_scenario_filepath_changed.connect(self.slot_on_file_path_changed)

        # File menu state changes: data required to execute back-end commands
        self.__last_used_scen_filepath = None
        self.__last_used_dir_path = QSettings().value(self.DIRPATH_KEY, str(Path.cwd()))
        self.__actor_part_selected = None  # Current actor part viewed
        self.__parts_selected_list = list()  # Current list of selected parts
        self.__ui = ui
        self.__close_part_editors = on_close_editors_callback
        self.__save_was_successful = None  # None => reset, True => save succeeded, False => save failed
        self.__is_saving_scenario = False  # True when app is in process of saving scenario; False otherwise.
        self.__changed_part_editors = changed_part_editors

    @property
    def last_used_scen_filepath(self) -> str:
        return self.__last_used_scen_filepath

    def on_file_path_changed(self, filepath: str):
        """
        Updates the path to the scenario file and stores the last accessed directory for use between application runs.

        When invoked, this method updates the name of the currently loaded file in the attribute
        '__last_used_scen_filepath' as returned by the back-end Scenario Manager. This value is used by the 'Save'
        command to perform save operations using the current filepath value. If 'filepath' is None, as when a new
        scenario is created, the 'Save As' dialog will launch if 'Save' is invoked to save the new scenario.

        The directory to the filename is also maintained in '__last_used_dir_path' and also copied to the applications
        QSettings in order to recall the previous directory between application runs for loading, importing, and
        exporting to and from the directory.
        If 'filepath' is None, this attribute is not updated and the application will continue to access the previous
        directory.

        :param filepath: the scenario filepath (path\filename)
        """
        self.__last_used_scen_filepath = filepath

        if filepath:
            self.__last_used_dir_path = str(Path(filepath).parent)
            QSettings().setValue(self.DIRPATH_KEY, self.__last_used_dir_path)

    def on_actor_part_selected(self, actor: ActorPart):
        """
        Gets the currently viewed actor when clicked from the Scenario Browser
        Note: this slot is connected to the Scenario Browser in the mainwindow.
        :param actor: The actor that is the current selection within the Scenario Browser.
        """
        self.__actor_part_selected = actor

    def on_part_selection_changed(self, parts: List[BasePart]):
        """
        Method called when part selection changes in the 2d View.
        :param parts: The currently selected part(s).
        """
        self.__parts_selected_list = parts
        enabled = bool(parts)
        if self.__ui is not None:
            self.__ui.action_export.setEnabled(enabled)

    def new_scenario(self):
        """
        Called when the user creates a new scenario.
        """
        self.__on_new_load_exit(self.__new_scenario, NewLoadExitTypeEnum.new_scenario)

    def load_scenario(self):
        """
        Called when the user wants to load a scenario.
        """
        self.__on_new_load_exit(self.__load_scenario, NewLoadExitTypeEnum.load_scenario)

    def exit_application(self):
        """
        Exits the application after the user is prompted to save any changes.
        """
        self.__on_new_load_exit(self.__exit_application, NewLoadExitTypeEnum.exit_application)

    def save_scenario(self) -> bool:
        """
        Called when the user wants to save the scenario using the current filename.
        :return: True if save executed, False if cancelled by user
        """
        return self.__on_save_save_as(self.__save_scenario)

    def save_scenario_as(self) -> bool:
        """
        Called when the user wants to save the scenario using a new filename.
        :return: True if save executed, False if cancelled by user
        """
        return self.__on_save_save_as(self.__save_scenario_as)

    def save_scenario_as_cb(self, save_status_callback: SaveAsStatusCallable) -> bool:
        """
        Called when the user wants to save the scenario using a new filename.

        Note: this second version of the above method was created because of a bug that arises when attempting to
        connect a QAction.triggered signal to the corresponding ext_safe_slot where a Callable argument has been
        defined. When triggered, an error dialog is generated that indicates that six arguments are passed but that the
        slot only takes 1 to 2 arguments. The six arguments include self, and five additional arguments of types
        integer and datetime.

        :param save_status_callback: An optional callback method given by the calling object to provide save status.
        :return: True if save executed, False if cancelled by user
        """
        return self.__on_save_save_as(self.__save_scenario_as, save_status_callback)

    def import_scenario(self):
        """
        Called when the user wants to import a scenario into the current actor.
        """

        # Open load dialogue and select the file to import
        open_dialog_filter = get_dialog_filter('open')
        (filename, ok) = QFileDialog.getOpenFileName(None, "Import Scenario",
                                                     self.__last_used_dir_path, open_dialog_filter)

        # Check for user cancel
        if not filename:
            return

        stop_progress = get_progress_bar().stop_progress

        def on_error(err_info: AsyncErrorInfo):
            stop_progress()
            exec_modal_dialog("Import Error", err_info.msg, QMessageBox.Critical)

        get_progress_bar().start_busy_progress('Importing')
        AsyncRequest.call(self.__scenario_manager.import_scenario, filename, self.__actor_part_selected,
                          response_cb=stop_progress, error_cb=on_error)

    def export_scenario(self):
        """
        Called when the user wants to export a scenario. Must only be called when there are parts selected.
        """

        # Open save dialogue and select the export filename
        save_dialog_filter = get_dialog_filter('save')
        (filename, ok) = QFileDialog.getSaveFileName(None, "Export Scenario...",
                                                     self.__last_used_dir_path, save_dialog_filter)

        # Check for user cancel
        if not filename:
            return

        # need to copy list in case it changes when by the time the scenario manager gets it in backend thread
        stop_progress = get_progress_bar().stop_progress

        def on_error(err_info: AsyncErrorInfo):
            stop_progress()
            exec_modal_dialog("Export Error", err_info.msg, QMessageBox.Critical)

        parts = self.__parts_selected_list[:]
        get_progress_bar().start_busy_progress('Exporting')
        AsyncRequest.call(self.__scenario_manager.export_scenario, parts, filename,
                          response_cb=stop_progress, error_cb=on_error)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_file_path_changed = safe_slot(on_file_path_changed)
    slot_on_actor_part_selected = safe_slot(on_actor_part_selected)
    slot_on_part_selection_changed = safe_slot(on_part_selection_changed, arg_types=[list])
    slot_new_scenario = safe_slot(new_scenario)
    slot_load_scenario = safe_slot(load_scenario)
    slot_save_scenario = safe_slot(save_scenario)
    slot_save_scenario_as = safe_slot(save_scenario_as)
    slot_import_scenario = safe_slot(import_scenario)
    slot_export_scenario = safe_slot(export_scenario)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_new_load_exit(self, action: NewLoadExitCallable, action_type: NewLoadExitTypeEnum):
        """
        This function provides the common execution pattern for the new, load and exit commands handled by this
        class. The input 'action' callable provides the functionality specific to the new, load or exit commands.
        :param action: A callable that provides the action to be taken by this function.
        :param action_type: A enumeration that specifies if this is a creating a new scenario, loading a scenario, or
        exiting the application.
        """

        # Check if part editor panels are open with changes
        if self.__close_part_editors is not None:
            editors_have_unsaved_changes = self.__close_part_editors(check_for_changes=True)

        # Check for unsaved changes
        def on_checked_changes(scenario_has_unsaved_changes: bool):
            get_progress_bar().stop_progress()
            if scenario_has_unsaved_changes or editors_have_unsaved_changes:

                # Set up the prompt

                # Dialog title
                if action_type == NewLoadExitTypeEnum.new_scenario:
                    title = 'New Scenario'
                elif action_type == NewLoadExitTypeEnum.load_scenario:
                    title = 'Open Scenario'
                else:
                    title = 'Exit Application'

                # Dialog Message
                if scenario_has_unsaved_changes and not editors_have_unsaved_changes:
                    msg = 'The scenario has unsaved changes. ' \
                          '\n\nClick Save to save all changes, Don\'t Save to abandon all unsaved changes, or Cancel to go back.'

                    user_input = exec_modal_dialog(title, msg, QMessageBox.Question,
                                               buttons=[QMessageBox.Save, QMessageBox.Cancel],
                                               buttons_str_role=[("Don't Save", QMessageBox.DestructiveRole)])

                elif editors_have_unsaved_changes and not scenario_has_unsaved_changes:
                    msg = 'There are part editors with unapplied changes.' \
                          '\n\nClick Save to save all changes, Don\'t Save to abandon all unapplied changes, or Cancel to go back.'

                    user_input = exec_modal_dialog(title, msg, QMessageBox.Question,
                                                buttons=[QMessageBox.Save, QMessageBox.Cancel],
                                                buttons_str_role=[("Don't Save", QMessageBox.DestructiveRole)])

                else:
                    msg = 'The scenario has unsaved changes, and there are part editors with unapplied changes. ' \
                          '\n\nClick Save to save all changes, Don\'t Save to abandon all unapplied and unsaved changes, or Cancel to go back.'

                    user_input = exec_modal_dialog(title, msg, QMessageBox.Question,
                                                buttons=[QMessageBox.Save, QMessageBox.Cancel],
                                                buttons_str_role=[("Don't Save", QMessageBox.DestructiveRole)])

                if user_input == QMessageBox.Cancel:
                    # user cancelled the operation
                    return

                if user_input == QMessageBox.Save:
                    # save opened editors first (if any) then save the scenario
                    for part in self.__changed_part_editors():
                        part.content_editor.submit_data(QDialogButtonBox.ApplyRole)
                    self.__save_scenario()

            # Start the action
            is_action_started = action()
            if is_action_started and self.__close_part_editors is not None:
                # Close editors only if action was started and has panels open
                self.__close_part_editors()

        # Check for unsaved changes in the current scenario
        get_progress_bar().start_busy_progress('Checking for unsaved changes')
        AsyncRequest.call(self.__scenario_manager.check_for_changes, response_cb=on_checked_changes)

    def __new_scenario(self) -> bool:
        """
        This function provides the 'new scenario' action for the __on_new_load_exit() function. It instigates the
        load of a new default scenario.
        :returns a boolean flag indicating that the new scenario request was sent.
        """
        AsyncRequest.call(self.__scenario_manager.new_scenario)
        scene_undo_stack().clear()
        return True

    def __load_scenario(self) -> bool:
        """
        This function provides the 'load scenario' action for the __on_new_load_exit() function. It instigates the
        load of a new scenario.
        :returns a boolean flag indicating that the load scenario request was sent.
        """
        # Open load dialog and select filename
        open_dialog_filter = get_dialog_filter('open')
        (filename, ok) = QFileDialog.getOpenFileName(None, "Open Scenario",
                                                     self.__last_used_dir_path, open_dialog_filter)

        # Check for user cancel
        if not filename:
            return False

        def on_load_error(err_info: AsyncErrorInfo):
            get_progress_bar().stop_progress()
            exec_modal_dialog("Load Error", err_info.msg, QMessageBox.Critical)

        def on_load_completed(scenario: Scenario, non_serialized_obj: list[str]):
            get_progress_bar().stop_progress()
            scene_undo_stack().clear()

            if non_serialized_obj:
                msg = "The following objects were not loaded: \n"
                for count, item in enumerate(non_serialized_obj):
                    msg += f"{count+1}. {SaveError.get_type_from_json(item)} in {SaveError.get_location_from_json(item)} \n"

                exec_modal_dialog("Unsaved Objects", "There are non-serializable objects in the loaded file. These objects were not loaded.",
                            QMessageBox.Warning, buttons=[QMessageBox.Ok], detailed_message=msg)

        get_progress_bar().start_busy_progress('Loading')
        AsyncRequest.call(self.__scenario_manager.load, filename,
                          response_cb=on_load_completed, error_cb=on_load_error)
        return True

    def __exit_application(self) -> bool:
        """
        This function provides the "exit application" action for the __on_new_load_exit() function. It instigates the
        exit procedure for the application.
        :returns: a boolean flag indicating that the exit application request was sent.
        """

        def on_scen_mgr_shutdown_done():
            self.sig_exit.emit()

        AsyncRequest.call(self.__scenario_manager.shutdown, response_cb=on_scen_mgr_shutdown_done)

        return True

    def __on_save_save_as(self, save_as_callback: SaveAsCallable,
                          save_status_callback: SaveAsStatusCallable = None) -> bool:
        """
        The function provides the common logic for the save and save-as functions. The input 'action' callable
        decides governs which of the two save behaviours gets exectuted.
        :param save_as_callback: The callback that performs the "save as" operation.
        :param save_status_callback: An optional callback method given by the calling object to provide save status.
        :return: True if save executed, False if cancelled by user or already underway.
        """
        if not self.__is_saving_scenario:

            self.__is_saving_scenario = True

            # Check if part editor panels are open with changes
            editors_have_unsaved_changes = False
            if self.__close_part_editors is not None:
                editors_have_unsaved_changes = self.__close_part_editors(check_for_changes=True)

            if editors_have_unsaved_changes:
                title = 'Unsaved Edits'
                msg = 'There are part editors with unsaved changes. ' \
                      '\n\nClick OK to save scenario without applying editor changes, or Cancel to go back.'
                user_input = exec_modal_dialog(title, msg, QMessageBox.Warning,
                                               buttons=[QMessageBox.Ok, QMessageBox.Cancel])

                if user_input == QMessageBox.Cancel:
                    self.__is_saving_scenario = False
                    return False  # user cancelled

            # Continue save even with unapplied editor changes
            if save_status_callback is not None:
                save_result = save_as_callback(save_status_callback)
            else:
                save_result = save_as_callback()

            if save_result:
                QTimer.singleShot(self.CHECK_SAVE_DELAY_MSEC, lambda: self.__check_save_success(None))
            else:
                self.__is_saving_scenario = False
            return save_result

        else:
            return False

    def __save_scenario(self) -> bool:
        """
        Saves the scenario to the current filename. Save success or failure callbacks are called as part of the
        save confirmation process.
        :return: True if save executed, False if cancelled by user
        """

        # If a filename has not been set, launch Save As..
        if self.__last_used_scen_filepath:
            get_progress_bar().start_busy_progress('Saving')
            AsyncRequest.call(self.__scenario_manager.save, self.__last_used_scen_filepath,
                              response_cb=self.__save_successful, error_cb=self.__save_failed)
            return True
        else:
            return self.__save_scenario_as()

    def __save_scenario_as(self, save_status_callback: SaveAsStatusCallable = None) -> bool:
        """
        Prompts the user for a new scenario pathname and saves the current scenario with that pathname. Save success
        or failure callbacks are called as part of the save confirmation process.
        :param save_status_callback: An optional callback method given by the calling object to provide save status.
        :return: True if save executed, False if cancelled by user
        """
        filepath = None
        save_approved = False
        while not save_approved:

            # Assume save operation is approved
            save_approved = True

            # Open save dialogue and select a new filename
            save_dialog_filter = get_dialog_filter('save')
            file_name = Path(self.__last_used_dir_path) / Path(self.__last_used_scen_filepath).stem
            filepath, suffix = QFileDialog.getSaveFileName(None, "Save Scenario As...",
                                                           str(file_name), save_dialog_filter)

            if not filepath:
                # This is True only if Close or Cancel were selected in the Save As dialog.
                # The dialog does not allow an OK button press to return if no filename was entered.
                return False

            # The static QFileDialog above does not check if the file exists if the name is entered without
            # a suffix. Here we check if a suffix was entered and if not, the one selected in the QFileDialog's filter
            # is appended to the entered filename and the file checked if it exists.
            # If it does, it prompts the user to confirm file overwrite, or to cancel and return to the Save As dialog.
            path_suffix = Path(filepath).suffix
            if path_suffix == "":
                p = PureWindowsPath(filepath)
                suffix = suffix.split(sep='*')[1]
                filepath = str(p.with_suffix(suffix))

                if Path(filepath).exists():
                    # The path exists, ask user to confirm overwrite
                    title = 'Confirm Save As'
                    message = '{} already exists.\nDo you want to replace it?'.format(Path(filepath).name)
                    user_input = exec_modal_dialog(title, message, QMessageBox.Question)

                    if user_input == QMessageBox.No:
                        save_approved = False

        def on_save_successful(_):
            self.__save_successful(_)
            if save_status_callback is not None:
                save_status_callback(True)

        def on_save_failed(err_info: AsyncErrorInfo):
            self.__save_failed(err_info)
            if save_status_callback is not None:
                save_status_callback(False)

        assert filepath is not None
        get_progress_bar().start_busy_progress('Saving as')
        AsyncRequest.call(self.__scenario_manager.save, filepath, response_cb=on_save_successful,
                          error_cb=on_save_failed)
        return True

    def __check_save_success(self, on_save_complete: NewLoadExitCallable):
        """
        This function monitors the current save operation that is underway and takes the appropriate action. If the
        save is complete the function executes the input on_save_complete callable. If the save is not yet complete
        this function signals itself for a re-check in 100 millisecs. If the save fails, the function displays an
        error and then stops monitoring and resets all relevant flags.
        :param on_save_complete: The callable to be called when the current save operation is deemed complete.
        """
        if self.__save_was_successful:
            self.__save_was_successful = None
            self.__is_saving_scenario = False
            if on_save_complete:
                on_save_complete()

        elif self.__save_was_successful is not None:
            # reset flags, return, error will get displayed to the user now
            self.__is_saving_scenario = False
            title = 'Save Error'
            message = 'The save operation failed: {}'.format(self.__save_was_successful.exc)
            exec_modal_dialog(title, str(self.__save_was_successful.exc), QMessageBox.Critical)
            self.__save_was_successful = None

        else:
            # Save operation still incomplete, check back in a 100 millisecs
            QTimer.singleShot(100, lambda: self.__check_save_success(on_save_complete))

    def __save_successful(self, non_serialized_obj: list[str]):
        """
        This function is an response callback for the asynchronous save call made to the backend. It sets a flag that
        function __check_save_success() depends on for monitoring save status.
        """
        self.__save_was_successful = True
        get_progress_bar().stop_progress()

        if non_serialized_obj:
            msg = "The following objects were not saved: \n"
            for count, item in enumerate(non_serialized_obj):
                msg += f"{count+1}. {SaveError.get_type_from_json(item)} in {SaveError.get_location_from_json(item)} \n"

            exec_modal_dialog("Unsaved Objects", "There are non-serializable objects in the saved file. These objects were not saved.",
                            QMessageBox.Warning, buttons=[QMessageBox.Ok], detailed_message=msg)

    def __save_failed(self, err_info: AsyncErrorInfo):
        """
        This function is an error callback for the asynchronous save call made to the backend. It sets a flag that
        function __check_save_success() depends on for monitoring save status.
        """
        self.__save_was_successful = err_info
        get_progress_bar().stop_progress()


class HelpManager(QObject):
    """
    This class is used to handle file menu Help commands from main menu of Origame.
    """

    PYTHON_REFERENCE_URL = "https://docs.python.org/3"
    PYTHON_TUTORIALS_URL = PYTHON_REFERENCE_URL + "/tutorial/index.html"
    PYTHON_LOCAL_REF = Path(sys.executable).parent / "Doc"
    FILE_URL_FORMAT = "file:///{}"
    DOCS_PATH = Path(origame.__file__).with_name("docs")
    PARTS_REFERENCE = DOCS_PATH / "user_manual_html" / "using parts.html"

    def on_action_python_tutorials(self, _: bool):
        """
        Method called when 'Help - Python Tutorials' is selected from the main menu of Origame.
        :param _: Boolean indicating whether or not the action item is currently checked.  Not used.
        """
        help_path = list(self.PYTHON_LOCAL_REF.glob("python3*.chm"))[0]
        self.__try_open_url(self.PYTHON_TUTORIALS_URL, help_path, "tutorial/index.html")

    def on_action_python_reference(self, _: bool):
        """
        Method called when 'Help - Python Reference' is selected from the main menu of Origame.
        :param _: Boolean indicating whether or not the action item is currently checked.  Not used.
        """
        help_path = list(self.PYTHON_LOCAL_REF.glob("python3*.chm"))[0]
        self.__try_open_url(self.PYTHON_REFERENCE_URL, help_path)

    def on_action_user_manual(self, _: bool):
        """
        Method called when 'Help - User Manual' is selected from the main menu of Origame.
        :param _: Boolean indicating whether or not the action item is currently checked.  Not used.
        """
        webbrowser.open_new_tab(self.FILE_URL_FORMAT.format(self.DOCS_PATH / "user_manual_html/index.html"))

    def on_action_examples(self, _: bool):
        """
        Method called when 'Help - Examples' is selected from the main menu of Origame.
        :param _: Boolean indicating whether or not the action item is currently checked.  Not used.
        """
        webbrowser.open_new_tab(self.FILE_URL_FORMAT.format(self.DOCS_PATH / "examples_html/index.html"))

    def on_action_parts_reference(self, _: bool):
        """
        Method called when 'Parts Reference' is selected from the main menu of Origame.
        :param _: Boolean indicating whether or not the action item is currently checked.  Not used.
        """
        webbrowser.open_new_tab(self.FILE_URL_FORMAT.format(self.PARTS_REFERENCE))

    def on_action_about(self, _: bool):
        """
        Method called when 'About' is selected from the main menu of Origame.
        """
        dialog = AboutDialog()
        dialog.exec()

    slot_on_action_python_tutorials = safe_slot(on_action_python_tutorials)
    slot_on_action_python_reference = safe_slot(on_action_python_reference)
    slot_on_action_user_manual = safe_slot(on_action_user_manual)
    slot_on_action_examples = safe_slot(on_action_examples)
    slot_on_action_parts_reference = safe_slot(on_action_parts_reference)
    slot_on_action_about = safe_slot(on_action_about)

    def __try_open_url(self, url: str, local_reference: str, section: str = None):
        """
        Helper method to attempt to open a web page specified by the url in a browser.  If the url is unreachable or
        does not exist, a local copy of Python's reference material or Python's tutorials is opened as a Windows help
        file.
        :param url: The url to open in a browser window, if connected to the internet.
        :param local_reference: If the url cannot be opened in a browser window, this parameter specifies where on the
        local file system that the associated Windows help file can be found.
        :param section: Optional parameter that is used to navigate to a specific section within the local reference.
        """
        with ProgressBusy('Opening Help Viewer'):
            reachable = self.__url_reachable(url)

            if reachable:
                webbrowser.open_new_tab(url)
            else:
                if section:
                    # hh.exe is the Windows program used to open Compiled HTML (CHM) files.  It is automatically installed
                    # with Windows and is in the Windows Path.
                    path = "hh.exe {}::{}".format(local_reference, section)
                    subprocess.Popen(path)
                else:
                    path = "hh.exe {}".format(local_reference)
                    subprocess.Popen(path)

    def __url_reachable(self, url: str) -> bool:
        """
        Helper method to test whether or not the provided url is reachable from the host that is running Origame.
        :param url: The url to test the reachability for.
        :return: A boolean indicating whether or not that the url is reachable.  Unreachable may indicate that internet
        connection is unavailable or that the url may be invalid.
        """
        try:
            urllib.request.urlopen(url)
            return True
        except Exception as e:  # Generic exception here as the cause of the exception is irrelevant.
            log.warning("The web URL '{}' could not be opened: {}", url, e)
            return False
