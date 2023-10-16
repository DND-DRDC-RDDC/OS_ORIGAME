# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*:  This module is used to encapsulate Scenario Part Editor presentation and behaviour.
                        The ScenarioPartEditorDlg will be the container for all editors.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from copy import deepcopy
import webbrowser

# [2. third-party]
from PyQt5.QtWidgets import QMessageBox, QDialogButtonBox, QPushButton, QAbstractButton, QWidget, QDialog, qApp
from PyQt5.QtGui import QKeyEvent, QIcon, QCursor
from PyQt5.QtCore import QSortFilterProxyModel, QSize, pyqtSignal, Qt

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core import override_required, override, override_optional
from ...scenario.defn_parts import BasePart
from ...scenario.defn_parts import get_pretty_type_name

from ..actions_utils import create_action
from ..gui_utils import part_image, get_scenario_font
from ..safe_slot import safe_slot
from ..gui_utils import exec_modal_dialog
from ..async_methods import AsyncRequest, AsyncErrorInfo
from ..undo_manager import PartEditorApplyChangesCommand
from ..undo_manager import scene_undo_stack
from .part_editors_registry import get_part_editor_class

from .Ui_scenario_part_editor_panel import Ui_ScenarioPartEditorPanel
from .common_part_help import PartHelp
from .common import EditorDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ScenarioPartEditorDlg',
    'BaseContentEditor',
    'SortFilterProxyModelByColumns',
    'DataSubmissionValidationError'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------
class DataSubmissionValidationError(Exception):
    """
    Describes what goes wrong for the data submission validation with three attributes, i.e., the title, message and
    detailed_message.
    """

    def __init__(self, title: str, message: str, detailed_message: str = ""):
        """
        Constructs the exception with the three attributes.
        :param title: The title that is to be displayed later on a dialog.
        :param message: The message that is to be displayed in the dialog.
        :param detailed_message: The detailed message that is to be displayed in the dialog.
        """
        Exception.__init__(self, title, message, detailed_message)
        self.title = title
        self.message = message
        self.detailed_message = detailed_message


class BaseContentEditor(QWidget):
    """
    This is the base class for all content editors.  Common behaviours (ie behaviour for providing Part Help)
    can be implemented here.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # This class attribute is given to receive_submit() when called. If data returned from _get_data_for_submission()
    # must be set in a particular order by the scenario part that receives the data, then the derived class
    # must override this attribute like so:
    #    _SUBMIT_ORDER = ParentClass._SUBMIT_ORDER + [ordered list of keys]
    _SUBMIT_ORDER = []

    # True - all the data are valid. This does not suggest all the data must be validated. If they are, this is the
    # mechanism to notify the outside world.
    sig_data_valid = pyqtSignal(str, bool)

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: BasePart, parent: EditorDialog = None):
        super().__init__(parent)
        self._part = part
        self._initial_data = None

        self.__fetch_snapshot_for_edit()
        self._part.base_part_signals.sig_bulk_edit_done.connect(self.__slot_bulk_edit_done)

    @override_optional
    def get_tab_order(self) -> List[QWidget]:
        """
        If the editor content wants to have a tab order between the editor header and the footer, it can
        return a list, which will be inserted between the header and the footer.

        :returns The tab order.
        """
        return []

    def on_close_requested(self) -> bool:
        """
        Checks for changes and asks the user for confirmation on the close operation.
        Can be overridden to allow part editors to tailor the change checking algorithm.
        :return: A boolean confirmation to close the editor (True) or not (False).
        """
        # Check for unsaved changes
        try:
            if self.check_unapplied_changes():
                # Changes were found, so ask the user to confirm since changes will be lost
                part_type = self._part.PART_TYPE_NAME
                title = "Cancel {} Editor".format(part_type.title())
                msg = "All changes will be lost. Are you sure you want to cancel?"
                if exec_modal_dialog(title, msg, QMessageBox.Question) != QMessageBox.Yes:
                    return False
                else:
                    self.parent().set_dirty(False)

                    AsyncRequest.call(self._part.clear_temp_link_names)
                    return True
            else:
                # If no changes found, no user confirmation is required
                return True

        except ValueError:
            # If a ValueError is raised, then the user has entered invalid information into the part and then closed
            # the editor before Applying the changes. When checking for changes, _get_data_for_submission will return
            # the ValueError bringing us here. At this point, we know there are changes since invalid information must
            # have been entered. However, since a ValueError was encountered, there is no point to verify with the user
            # that they want to close the editor before applying the changes since their changes are invalid.
            return True

    @override_optional
    def check_unapplied_changes(self) -> Either[Dict[str, Any], None]:
        """
        Checks if the editor has unapplied changes in its data.
        :return: A non-empty dict indicating the editor has changes. The dict contains the changed data.  None
        if no changes at all.
        """
        # 1. Collect part specific attributes
        edited_data = self._get_data_for_submission()

        # 2. Collect the name, which is common to all the editable parts
        edited_data['name'] = self.parent().ui.part_name.text()

        # 3. Collect the edited link names, if the part has outgoing links and their names have been changed.
        map_link_id_to_edited_name = dict()

        for link in self._part.part_frame.outgoing_links:
            edited_link_name = link.temp_name
            # Note: We submit the link map back to the backend even if the names are unchanged because we
            # want to benefit from the editing infrastructure for the change detection edited_data == self._initial_data
            map_link_id_to_edited_name[link.SESSION_ID] = link.name if edited_link_name is None else edited_link_name

        edited_data['link_names'] = map_link_id_to_edited_name

        # All data collected
        if edited_data == self._initial_data:
            return None
        else:
            return edited_data

    @override(QWidget)
    def sizeHint(self):
        return QSize(int(self.INIT_WIDTH), int(self.INIT_HEIGHT))

    def submit_data(self, box_role: QDialogButtonBox):
        """
        Used to submit the data from the GUI to the backend, which can handle the data any way it wants, e.g.,
        validates it, saves it, etc..

        :param box_role: If it is the AcceptRole, the editor dialog will be closed after the saving. If it is the
        ApplyRole, the dialog will remain open.
        """
        def _on_submit_success():
            self.set_wait_mode(False)
            if box_role == QDialogButtonBox.AcceptRole or box_role == QDialogButtonBox.ApplyRole:
                self.parent().set_dirty(False)
                if box_role == QDialogButtonBox.AcceptRole:
                    self.parent().accept()
                submit_order = self._SUBMIT_ORDER  # need to use "self" instead of class to get the most derived list
                cmd = PartEditorApplyChangesCommand(self._part, self._initial_data, new_data, submit_order)
                scene_undo_stack().push(cmd)
                if box_role == QDialogButtonBox.ApplyRole:
                    self._snapshot_initial_data(new_data)

        def _on_submit_error(exc_info: AsyncErrorInfo):
            self.set_wait_mode(False)
            exec_modal_dialog("Edit Error",
                              "One or more of the edits are not valid (specifically: '{}'). "
                              "Please try again.".format(exc_info.msg), QMessageBox.Critical)

        try:
            self.__validate_data_for_submission()
        except ValueError:
            # We return because it is used for the data validation on the submission.
            return

        new_data = self.check_unapplied_changes()
        if not new_data:
            if box_role == QDialogButtonBox.AcceptRole:
                self.parent().accept()
            elif box_role == QDialogButtonBox.ApplyRole:
                # Remove the star from the title bar
                self.parent().set_dirty(False)

            return

        self.set_wait_mode(True)
        AsyncRequest.call(self._part.receive_edited_snapshot,
                          new_data,
                          order=self._SUBMIT_ORDER,
                          initiator_id=id(self),
                          response_cb=_on_submit_success, error_cb=_on_submit_error)

    @override_optional
    def disconnect_all_slots(self):
        """
        Called when the editor is destroyed.
        """
        pass

    def set_wait_mode(self, wait: bool):
        """
        Enable or diable the button box based on the 'wait' mode of the panel.
        :param wait: The mode of the panel.
        """
        if wait:
            self.setCursor(QCursor(Qt.WaitCursor))
        else:
            self.unsetCursor()

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_optional
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        Method used to set the GUI's fields based on data received from the backend.  This method can be used
        to populate a part editors field during initial load of the editor.

        This method must be run in the front end thread. So, the data from the backend is passed as a parameter.
        :param data: The data from the backend
        """
        pass

    @override_optional
    def _complete_data_submission_validation(self):
        """
        If a specific editor has data submission validation needs, it must implement this function. By default, this
        functions does nothing.
        :raise: DataSubmissionValidationError
        """
        pass

    @override_optional
    def _snapshot_initial_data(self, data: Dict[str, Any]):
        """
        Preserves a copy of the initial data. After editing, the copy will be used to compare with the edited data to
        determine any changes. By default, the copy is a deep copy of the data.

        The derived class must override it if some data cannot be deep-copied.

        :param data: The data to be preserved.
        """
        self._initial_data = self._get_deepcopy(data)

    def _get_deepcopy(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempts to do deepcopy() on the data_dict. If it fails, it calls _get_custom_deepcopy()
        :param data_dict: The data to be copied
        :return: The copied data that do not contain "bad" values.
        """
        try:
            copied_data = deepcopy(data_dict)
        except:
            # The "bad" values such as the return value of open() can cause this.
            copied_data = self._get_custom_deepcopy(data_dict)

        return copied_data

    @override_optional
    def _get_custom_deepcopy(self, _: Dict[str, Any]) -> Dict[str, Any]:
        """
        Although override is optional, parts that can have non-deep-copyable data MUST override this.
        :return The deep copied data that do not contain the "bad" values such as open():
        """
        msg = ("This function must be overridden because this part type "
               "can have non-deep-copyable data : {}", self._part.PART_TYPE_NAME)

        raise NotImplementedError(msg)

    @override_required
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Each specific editor must implement this function to collect the data elements from the GUI and return them
        in a dict.

        This function and the part (the backend) the editor works for must have the mutual understanding of how
        the dict is populated. In other words, the part must be able to interpret the data elements in the dict in
        order to set them to the properties of the part.

        If a subclass has compound properties such as dict objects, it must do a deep copy.
        """
        raise NotImplementedError('Implementation needed.')

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __validate_data_for_submission(self):
        """
        The subclass should call this function first before overriding it to validate the business data.
        """
        new_name = self.parent().ui.part_name.text()

        # The new_name text field is doing the validation for None, empty and all spaces so we don't have to
        # validate again here. Assert is added just in case the text validation is removed for some reason.
        assert new_name
        assert not new_name.isspace()

        try:
            self._complete_data_submission_validation()
        except DataSubmissionValidationError as ex:
            exec_modal_dialog(ex.title,
                              ex.message,
                              QMessageBox.Critical,
                              detailed_message=ex.detailed_message,
                              buttons=[QMessageBox.Cancel],
                              default_button=QMessageBox.Cancel)

            # Raise a ValueError for any exception to trigger the handling logic in the super class
            raise ValueError()

    def __on_bulk_edit_done(self, initiator_id: int):
        """
        Gets all the data from the part in order to populate its editor.
        :param initiator_id: The id of the component that initiates this function.
        """
        if id(self) != initiator_id:
            self.__fetch_snapshot_for_edit()

    def __fetch_snapshot_for_edit(self):
        def frontend_receives_snapshot_for_edit(data: Dict[str, Any]):
            # The _initial_data dictionary is manipulated here to ensure that there is a snapshot of the data as it was
            # during initial load of the editor (prior to the data - potentially - being manipulated by a user).
            self._snapshot_initial_data(data)
            self._on_data_arrived(data)
            self.set_wait_mode(False)

        self.set_wait_mode(True)
        AsyncRequest.call(self._part.get_snapshot_for_edit, response_cb=frontend_receives_snapshot_for_edit)

    __slot_bulk_edit_done = safe_slot(__on_bulk_edit_done)


class ScenarioPartEditorDlg(EditorDialog):
    """
    This class is used by all part editors.  It provides common look and feel as well as behaviour.
    """
    sig_editor_dialog_closed = pyqtSignal(int)

    # Going to model means to show the part. That business logic already exists, but it is in the panel. We
    # use the signal routing to reach that, just as the scene does in some cases
    sig_go_to_part = pyqtSignal(BasePart)

    IEXPLORER_EXE_LOCATION = "C:\Program Files\Internet Explorer\iexplore.exe"

    TITLE_PATTERN = "[*] {} - {} Editor"

    def __init__(self, part: BasePart = None):
        """
        :param editor:  The editor content panel.
        :param part: The part that is associated with this editor dialog.
        """
        super().__init__()

        PartContentEditorClass = get_part_editor_class(part.PART_TYPE_NAME)
        self.content_editor = PartContentEditorClass(part, self)
        self.ui = Ui_ScenarioPartEditorPanel()
        self.ui.setupUi(self)
        self.ui.part_path.setFont(get_scenario_font())
        self.ui.part_path.setText(part.get_path(with_name=False))
        self.ui.part_name.setFont(get_scenario_font())
        self.ui.part_name.setText(part.name)
        self.ui.part_name.textChanged.connect(self.__slot_check_name)
        self.ui.content_placeholder.addWidget(self.content_editor)
        self.ui.button_box.clicked.connect(self.__slot_on_button_clicked)

        self.__part = part
        part.base_part_signals.sig_in_scenario.connect(self.__slot_on_part_in_scenario_changed)
        self.setWindowTitle(self.TITLE_PATTERN.format(part.name, get_pretty_type_name(part.PART_TYPE_NAME)))
        icon = QIcon(str(part_image(part.PART_TYPE_NAME)))
        self.setWindowIcon(icon)
        self.__action_go_to_part = create_action(self,
                                                 "Go to Part",
                                                 tooltip="Show part in its parent actor",
                                                 button=self.ui.go_to_part,
                                                 connect=self.__slot_on_go_to_part)

        part.part_frame.signals.sig_name_changed.connect(self.__slot_on_part_name_changed)
        self.ui.part_name.textEdited.connect(self.__slot_on_part_name_text_edited)

        self.__set_tab_order()
        self.__force_close = False  # Flag to indicate if panel can close without user confirmation

        self.__part_help = PartHelp()
        self.ui.part_help_button.clicked.connect(self.__slot_on_part_help_clicked)

        self.resize(self.content_editor.sizeHint())

        self.content_editor.sig_data_valid.connect(self.__slot_on_data_valid)

    @override(QDialog)
    def keyPressEvent(self, evt: QKeyEvent):
        # Override the keyPressEvent so that pressing Enter or Return does not close the editor panel
        # but accepts the changes made during editing of part values in the editor.
        if evt.key() == int(Qt.Key_Enter) or evt.key() == int(Qt.Key_Return):
            return
        super().keyPressEvent(evt)

    @override(QDialog)
    def done(self, result: int):
        if result == QDialog.Rejected:
            if not self.__force_close:
                confirmed = self.content_editor.on_close_requested()
                if not confirmed:
                    return
            self.__force_close = False  # reset force-close flag

        self.content_editor.disconnect_all_slots()
        self.sig_editor_dialog_closed.emit(self.__part.SESSION_ID)
        super().done(result)

    def disable_checks_on_close(self):
        """Disable checking for unsaved data when closing dialog."""
        self.__force_close = True  # Force editor panel to close without user confirmation

    def check_unapplied_changes(self) -> Either[Dict[str, Any], None]:
        """
        Calls the editors' check for unapplied changes method and returns the result.
        :return: A non-empty dict indicating the editor has changes. The dict contains the changed data.  None
        if no changes at all.
        """
        return self.content_editor.check_unapplied_changes()

    def set_dirty(self, dirty: bool):
        """
        The sub class calls this function to inform the framework that an editing operation has happened.
        This function sets the value to the backend. This function also shows a "*" on the editor dialog
        title bar if the "dirty" is True; hides the "*" if the "dirty" is False.
        :param dirty: True - if at least one editing activity happens.
        """
        self.setWindowModified(dirty)

        def update_dirty_status():
            self.__part.set_has_unapplied_edits(dirty)

        AsyncRequest.call(update_dirty_status)

    def handle_go_to_part_action(self, part: BasePart):
        """
        Design pattern notice: The owner of the signal emits it. So, the public sig_go_to_part will not be emitted by
        outsiders directly.
        :param part: The part to be displayed.
        """
        self.sig_go_to_part.emit(part)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_button_clicked(self, button: QPushButton):
        """
        Slot called when one of the 3 generic buttons (Ok, Apply, Cancel) are clicked.
        The derived classes will override the Ok and Apply.
        :param button:  The button that was clicked.
        """
        button_role = self.ui.button_box.buttonRole(button)
        if button_role == QDialogButtonBox.RejectRole:
            self.reject()
        elif button_role == QDialogButtonBox.AcceptRole or button_role == QDialogButtonBox.ApplyRole:
            if button_role == QDialogButtonBox.AcceptRole:
                self.content_editor.disconnect_all_slots()
            self.content_editor.submit_data(button_role)

    def __on_part_in_scenario_changed(self, status: bool):
        if status is False:
            log.warning("Part {} removed from scenario, closing editor (abandoning any changes)", self.__part)
            self.content_editor.disconnect_all_slots()
            self.sig_editor_dialog_closed.emit(self.__part.SESSION_ID)
            super().done(QDialog.Rejected)

    def __check_name(self):
        """
        Function used to enforce function name field to be non-empty.
        """
        if len(self.ui.part_name.text().strip()) == 0:
            self.ui.part_name.setStyleSheet('QLineEdit { background-color: red }')
            self.ui.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
            self.ui.button_box.button(QDialogButtonBox.Apply).setEnabled(False)
        else:
            self.ui.part_name.setStyleSheet('QLineEdit { background-color: white }')
            self.ui.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
            self.ui.button_box.button(QDialogButtonBox.Apply).setEnabled(True)

    def __set_tab_order(self):
        """
        Method used to set the tab order of a Part editor.
        """
        tab_order = [self.ui.part_name] + self.content_editor.get_tab_order() + \
                    [self.ui.part_help_button,
                     self.ui.button_box.button(QDialogButtonBox.Ok),
                     self.ui.button_box.button(QDialogButtonBox.Cancel),
                     self.ui.button_box.button(QDialogButtonBox.Apply)]

        total_len = len(tab_order)
        for idx, obj in enumerate(tab_order):
            next_idx = idx + 1
            if next_idx < total_len:
                QWidget.setTabOrder(obj, tab_order[next_idx])

    def __on_part_help_clicked(self):
        """
        Method called when the 'Part Help' button is clicked from within a part editor.
        """
        path = self.__part_help.get_part_help_path(self.__part.PART_TYPE_NAME)
        webbrowser.open_new_tab(path)

    def __on_go_to_part(self):
        self.sig_go_to_part.emit(self.__part)

    def __on_part_name_changed(self, new_name: str):
        """
        The changed name is used to update the editor dialog title.
        :param new_name: The name from the backend
        """
        self.setWindowTitle(self.TITLE_PATTERN.format(new_name, get_pretty_type_name(self.__part.PART_TYPE_NAME)))

    def __on_part_name_text_edited(self, _: str):
        """
        Displays a "*" on the editor title bar and flags the backend.
        """
        self.set_dirty(bool(self.check_unapplied_changes()))

    def __on_data_valid(self, validator_name: str, valid: bool):
        """
        Notified by the content editor of the validity of its data
        :param valid: True - valid
        """
        self.ui.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)
        self.ui.button_box.button(QDialogButtonBox.Apply).setEnabled(valid)

    __slot_on_part_help_clicked = safe_slot(__on_part_help_clicked)
    __slot_check_name = safe_slot(__check_name)
    __slot_on_part_in_scenario_changed = safe_slot(__on_part_in_scenario_changed)
    __slot_on_button_clicked = safe_slot(__on_button_clicked, arg_types=[QAbstractButton])
    __slot_on_go_to_part = safe_slot(__on_go_to_part)
    __slot_on_part_name_changed = safe_slot(__on_part_name_changed)
    __slot_on_part_name_text_edited = safe_slot(__on_part_name_text_edited)
    __slot_on_data_valid = safe_slot(__on_data_valid)


class SortFilterProxyModelByColumns(QSortFilterProxyModel):
    """
    The out-of-the-box QSortFilterProxyModel sorts the table by all the columns. We use this class if we sort only on
    selected columns.
    """
    sig_column_sorted = pyqtSignal(int, int)  # sorted column, sort order

    def __init__(self, parent, columns_sorted: List[int] = None):
        """
        During the construction, the user specifies which columns should be sorted.
        :param parent: The parent from the Qt framework
        :param columns_sorted: The list of the columns that are sorted.
        """
        super().__init__(parent)
        self.__columns_sorted = columns_sorted

    @override(QSortFilterProxyModel)
    def sort(self, column: int, order: int):
        if column in self.__columns_sorted:
            super().sort(column, order)
            self.sig_column_sorted.emit(column, order)
