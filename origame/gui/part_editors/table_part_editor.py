# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Table Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import webbrowser
from copy import deepcopy
from datetime import datetime
from enum import Enum
from pathlib import Path
from random import random

# [2. third-party]
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QVariant, Qt
from PyQt5.QtCore import QSettings
from PyQt5.QtCore import pyqtSignal, QItemSelectionModel, QItemSelection
from PyQt5.QtGui import QIcon, QBrush
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QMessageBox, QDialog
from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QFileDialog, QDialogButtonBox, QListWidgetItem

# [3. local]
from ...core import override, override_optional, override_required
from ...core.typing import Any, Either, Optional, Callable
from ...core.typing import List, Tuple, Dict, Iterable
from ...scenario import ori
from ...scenario.defn_parts import TablePart, DisplayOrderEnum, get_db_tables
from ...scenario.defn_parts.table_part import import_from_msaccess, export_to_msaccess

from ..gui_utils import exec_modal_dialog, get_icon_path, get_scenario_font
from ..safe_slot import safe_slot
from ..async_methods import AsyncRequest, AsyncErrorInfo

from .common import EditorDialog, DialogHelp
from .part_editors_registry import register_part_editor_class
from .scenario_part_editor import BaseContentEditor, SortFilterProxyModelByColumns
from .Ui_table_column_param_editor import Ui_edit_column_parameters
from .Ui_table_filter_dialog import Ui_TableFilterDialog
from .Ui_table_import_dialog import Ui_TableImportDialog
from .Ui_table_index_dialog import Ui_TableIndexDialog
from .Ui_table_part_editor import Ui_TablePartEditor

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'TablePartEditorPanel',
    'ImportDatabaseDialog',
    'ExportDatabaseDialog'
]

log = logging.getLogger('system')

ImportCallable = Callable[[str, str], None]
ExportCallable = Callable[[str], None]

TableCellData = Either[str, int, float]
DbRawRecord = Tuple[TableCellData]
DbRawRecords = List[DbRawRecord]

SQLITE_DATETIME_FORMAT = '%Y-%m-%d %H:%M:%S'


# -- Function definitions -----------------------------------------------------------------------

def on_database_error(title, db_error: str, optional_msg: str = None):
    """
    Display a modal error dialog when there is a database error.
    :param title: The dialog title.
    :param db_error: The error message returned from the database.
    :param optional_msg: An optional message to display.
    """
    error_msg = "The following error was raised: {}".format(db_error)
    if optional_msg is not None:
        error_msg += "\n\n{}".format(optional_msg)

    exec_modal_dialog(title, error_msg, QMessageBox.Critical)
    log.error('{}: {}', title, error_msg)


# -- Class Definitions --------------------------------------------------------------------------

class DbRecord(list):
    """
    A database record consists of a list of items displayed as a row in the table.
    """
    ID_GENERATION_ATTEMPTS = 50

    def __init__(self, iterable: Iterable[Any] = [], taken_ids: List[int] = [], is_filtered: bool = False):
        """
        Initialize the database record.
        :param iterable: a list of items to set into this record.
        :param taken_ids: a list of record IDs that have already been assigned to other records.
        :param is_filtered: a flag that indicates if a filter has been applied to the table.
        """
        super().__init__(iterable)
        self.id = None  # temp set to None to signify a new record added while filtered
        if not is_filtered:
            self.generate_id(taken_ids)  # set an ID to identify this record in the frontend

    def generate_id(self, taken_ids: List[int]):
        """
        Generate an id for this record if not already set.
        :param taken_ids: the list of all IDs currently assigned to other records.
        """
        if self.id is None:
            for attempts in range(self.ID_GENERATION_ATTEMPTS):
                unique_id = random()
                # check the new ID for uniqueness agains list of take IDs
                if unique_id not in taken_ids:
                    self.id = unique_id
                    break
            else:
                raise RuntimeWarning("A unique ID could not be generated.")


# Oliver TODO: move this class to the backend which currently uses strings to specify column type. This will omit the
# need to convert when the editor opens and when its changes are applied.
class SqliteDataTypesEnum(Enum):
    """
    Enumerate SQL data types that table columns can be set too.
    """
    DATETIME, INTEGER, REAL, TEXT, DOUBLE, FLOAT = range(6)


REAL_TYPES = (SqliteDataTypesEnum.REAL, SqliteDataTypesEnum.DOUBLE, SqliteDataTypesEnum.FLOAT)


class TableEditorDialog(EditorDialog):
    """
    The base class for Table Editor dialogs sets up the UI features and interface with the table editor.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------  

    def __init__(self, table_part: TablePart, ui: Any, parent: QWidget = None):
        super().__init__(parent)

        self.ui = ui
        self.ui.setupUi(self)
        self.table_editor = parent
        self._part = table_part

    @override(QDialog)
    def done(self, result: int):

        if result != QDialog.Rejected:
            isvalid = self._validate_user_input()
            if not isvalid:
                # For invalid results, return the user to the orignal dialog to correct mistakes
                return
        else:
            self.reject_changes()
        super().done(result)

    @override_optional
    def reject_changes(self):
        """
        Optionally implement this function to clear any changes that have been made the dialog if 'Cancel' is pressed.
        """
        pass

    @override_optional
    def get_user_input(self) -> Any:
        """
        Optionally implement this function to get the input from the dialog.
        :return: A tuple of user input.
        """
        pass

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------    

    @override_optional
    def _validate_user_input(self) -> bool:
        """
        Optionally implement this function to validate user input.
        :return: a boolean indicating if the result is valid.
        """
        return True


class TableColumnParamEditorDialog(TableEditorDialog):
    """
    Dialog to handle editing of column name and type parameters.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, col_name: str, col_type: str, table_part: TablePart, parent: QWidget = None):
        """
        Initialize the column parameter editor dialog.
        :param col_name: The current column name.
        :param col_type: The current column type.
        :param table_part: The table part.
        :param parent: The parent widget of this dialog.
        """
        ui = Ui_edit_column_parameters()
        super().__init__(table_part, ui, parent)
        self.ui.col_name_linedit.setText(col_name)
        for idx in range(self.ui.col_type_combobox.count()):
            if col_type == self.ui.col_type_combobox.itemText(idx):
                self.ui.col_type_combobox.setCurrentIndex(idx)
                break

    @override(TableEditorDialog)
    def get_user_input(self) -> Tuple[str, str]:
        column_name = self.ui.col_name_linedit.text()
        column_type = self.ui.col_type_combobox.currentText()
        return column_name, column_type


class TableImportExportDialog(TableEditorDialog):
    """
    Base class for the table import and export dialog.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------  

    def __init__(self, table_part: TablePart, ui: Any, parent: QWidget = None):
        super().__init__(table_part, ui, parent)
        self._tables = {}
        self._on_accept_callback = None
        self.__dialog_help = DialogHelp()
        self.ui.help_button.clicked.connect(self.__slot_on_help_button_pressed)

    def set_tables(self, tables: dict):
        """Set the dict of table names and corresponding columns."""
        self._tables = tables

    def set_accept_callback(self, accept_cb: Either[ImportCallable, ExportCallable]):
        """Set the callable to invoke on dialog acceptance."""
        self._on_accept_callback = accept_cb

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_required
    def _on_browse_files(self, _: bool):
        """
        Optionally implement this function to open a file browser to select files for import or export.
        """
        pass

    @override_required
    def _on_filepath_changed(self):
        """
        Optionally implement this function to respond to filepath changes.
        """
        pass

    @override_required
    def _on_table_list_requested(self, _: bool):
        """
        Optionally implement this function to generate a list of tables and populate the combobox.
        """
        pass

    def _enable_file_selection(self, enabled: bool):
        """
        Enable or disable the file selection components of the dialog.
        :param enabled: The enable status to set.
        """
        self.ui.file_label.setEnabled(enabled)
        self.ui.filepath_linedit.setEnabled(enabled)
        self.ui.browse_files_button.setEnabled(enabled)

    def _enable_list_tables_button(self, enabled: bool):
        """
        Enable or disable the button that retrieves the list of tables.
        :param enabled: The enable status to set.
        """
        self.ui.table_combobox.clear()  # remove all previous entries
        self.ui.list_tables_button.setEnabled(enabled)

    def _enable_table_selection(self, enabled: bool):
        """
        Enable or disable the table and fields selection and filter components.
        :param enabled: The enable status to set.
        """
        self.ui.table_label.setEnabled(enabled)
        self.ui.table_combobox.setEnabled(enabled)
        self.ui.fields_label.setEnabled(enabled)
        self.ui.fields_listwidget.setEnabled(enabled)
        self.ui.filter_label.setEnabled(enabled)
        self.ui.filter_linedit.setEnabled(enabled)

    def _enable_ok(self, enabled: bool):
        """
        Enable or disable the OK button.
        :param enabled: The enable status to set.
        """
        self.ui.button_box.button(QDialogButtonBox.Ok).setEnabled(enabled)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_help_button_pressed(self):
        """
        Method called when the 'Help' button is clicked from the table dialog.
        """
        path = self.__dialog_help.get_dialog_help_path(self._part.PART_TYPE_NAME)
        webbrowser.open_new_tab(path)

    __slot_on_help_button_pressed = safe_slot(__on_help_button_pressed)


class ImportDatabaseDialog(TableImportExportDialog):
    """
    Dialog to import database data from an Access database file.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    DB_SUFFIX = ['.mdb', '.accdb']
    LAST_IMPORT_DIR = 'part_editors.table_part_editor.LAST_IMPORT_DIR'

    # --------------------------- instance (self) PUBLIC methods --------------------------------    

    def __init__(self, table_part: TablePart,
                 last_db_import_path: str = None,
                 db_filter: str = None,
                 table_editor: QWidget = None):
        """
        Initialize the table database import dialog.
        :param table_part: The backend table part.
        :param last_db_import_path: The path to the Access database being imported.
        :param db_filter: A SQL 'WHERE' clause to filter the data imported.
        :param table_editor: The parent table part editor of this dialog (if any).
        """
        ui = Ui_TableImportDialog()
        super().__init__(table_part, ui, parent=table_editor)

        # Set the dialog title
        self.setWindowTitle('Import from Access')
        self.ui.instructions_label.setText("Click OK to replace the table data with the imported data or Cancel "
                                           "to go back.")

        self.__db_selected_fields = []

        # disable all components except file selection
        self._enable_list_tables_button(False)
        self._enable_table_selection(False)
        self._enable_ok(False)

        self.ui.browse_files_button.clicked.connect(self._slot_on_browse_files)
        self.ui.filepath_linedit.editingFinished.connect(self._slot_on_filepath_changed)
        self.ui.list_tables_button.clicked.connect(self._slot_on_table_list_requested)
        self.ui.table_combobox.currentIndexChanged[str].connect(self.__slot_on_table_selected)

        if last_db_import_path is not None:
            self.ui.filepath_linedit.setText(last_db_import_path)
            self._on_filepath_changed()
            self._on_table_list_requested(True)
            # put focus here so user doesn't have to click out of filepath_linedit
            # which triggers editingFinished signal that resets dialog elements
            self.ui.table_combobox.setFocus(Qt.OtherFocusReason)

        if db_filter is not None:
            self.ui.filter_linedit.setText(db_filter)

    @override(TableEditorDialog)
    def get_user_input(self) -> Tuple[str, str, list, str]:
        db_path = self.ui.filepath_linedit.text()
        db_table = self.ui.table_combobox.currentText()
        db_selected_fields = self.__db_selected_fields
        db_filter = self.ui.filter_linedit.text()
        return db_path, db_table, db_selected_fields, db_filter

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------    

    @override(TableEditorDialog)
    def _validate_user_input(self) -> bool:
        """
        The database path and table list are already validated. Currently, the filter is not validated
        but will show an error dialog if there is a problem. So here, just check that there are column
        field names selected.
        """
        # create a list of the selected table fields
        num_fields = self.ui.fields_listwidget.count()
        self.__db_selected_fields = []
        for idx in range(num_fields):
            field_item = self.ui.fields_listwidget.item(idx)
            if field_item.checkState() == Qt.Checked:
                self.__db_selected_fields.append(field_item.text())

        if not self.__db_selected_fields:
            msg = "There is nothing to import since no fields were selected."
            exec_modal_dialog("No Fields Selected", msg, QMessageBox.Information)
            return False

        return True

    @override(TableImportExportDialog)
    def _on_browse_files(self, _: bool):
        """
        Opens a file browser to select the Access file to import.
        """
        db_path, ext = QFileDialog.getOpenFileName(self, "Select Access File",
                                                   QSettings().value(self.LAST_IMPORT_DIR),
                                                   "Access (*.mdb *.accdb)")
        if not db_path:
            return

        self.ui.filepath_linedit.setText(db_path)
        self._on_filepath_changed()

    @override(TableImportExportDialog)
    def _on_filepath_changed(self):
        """
        Update the path to the selected Access file.
        """
        self._enable_ok(False)
        self._enable_table_selection(False)

        # disable until we know a valid file path was entered
        self._enable_list_tables_button(False)
        db_path = self.ui.filepath_linedit.text()
        if not db_path:
            return

        db_path = Path(db_path)

        # if only file name entered without full path, prepend cwd
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path

        # reset the path with the updated info
        self.ui.filepath_linedit.setText(str(db_path))

        if db_path.suffix not in self.DB_SUFFIX:
            msg = 'The file must be specified with an ".accdb" or ".mdb" extension.'
            exec_modal_dialog("Invalid File Extension", msg, QMessageBox.Critical)
            return

        if not db_path.exists():
            exec_modal_dialog("File Not Found", "The file path entered does not exist.", QMessageBox.Critical)
            return

        QSettings().setValue(self.LAST_IMPORT_DIR, str(db_path.parent))
        self._enable_list_tables_button(True)

    @override(TableImportExportDialog)
    def _on_table_list_requested(self, _: bool):
        """
        Request the list of tables from the selected Access file and populate the combobox.
        """
        self.ui.table_combobox.clear()  # remove all previous entries
        db_path = self.ui.filepath_linedit.text()

        try:
            self.set_tables(get_db_tables(db_path))
        except Exception as exc:
            msg_title = 'Table List Error'
            error_msg = 'The list of tables could not be retrieved from database \'{}\'.\n{}'.format(db_path, exc)
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            return

        tables = [table for table in self._tables.keys()]
        if tables:
            self.ui.table_combobox.insertItems(0, tables)
            self._enable_table_selection(True)
            self._enable_ok(True)

        else:
            exec_modal_dialog('No Tables Found', "No tables were found in the database.", QMessageBox.Information)

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    _slot_on_browse_files = safe_slot(_on_browse_files)
    _slot_on_filepath_changed = safe_slot(_on_filepath_changed)
    _slot_on_table_list_requested = safe_slot(_on_table_list_requested)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_table_selected(self, table_name: str):
        """
        When a table is selected, populate the list widget with the table's field names.
        :param table_name: The selected table.
        """
        self.ui.fields_listwidget.clear()  # remove all previous entries

        if self.ui.table_combobox.count() == 0:
            # the tables combo box was cleared
            return

        fields = self._tables[table_name]
        for field in fields:
            field_item = QListWidgetItem(field)
            field_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            field_item.setCheckState(Qt.Checked)
            self.ui.fields_listwidget.addItem(field_item)

    __slot_on_table_selected = safe_slot(__on_table_selected)


class ExportDatabaseDialog(TableImportExportDialog):
    """
    Dialog to export database data into a new or existing Access database file.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    LAST_EXPORT_DIR = 'part_editors.table_part_editor.LAST_EXPORT_DIR'
    NEW_STR = ' (New)'

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, table_part: TablePart,
                 fields: List[str],
                 last_db_export_path: str = None,
                 table_editor: QWidget = None):
        """
        Initialize the table database export dialog.
        :param table_part: The backend table part.
        :param fields: A list of column headers shown in the table part.
        :param last_db_export_path: The path to the Access database being exported.
        :param table_editor: The parent table part editor of this dialog (if any).
        """
        ui = Ui_TableImportDialog()
        super().__init__(table_part, ui, parent=table_editor)

        # Set the dialog title
        self.setWindowTitle('Export to Access')
        self.ui.instructions_label.setText("Click OK to export the Table Part's data to the selected table of the "
                                           "chosen MS Access file. A subset of fields can be specified. "
                                           "Click Cancel to abandon exporting.")

        # move the fields selection list to the top
        current_pos = 4
        top_pos = 1
        dialog_layout = self.layout()
        fields_layout = dialog_layout.itemAt(current_pos)
        dialog_layout.removeItem(fields_layout)
        dialog_layout.insertLayout(top_pos, fields_layout)

        self.ui.filter_linedit.setReadOnly(True)
        self.ui.filter_label.setEnabled(False)

        self.__populate_field_names(fields)
        self.__db_selected_fields = []

        # disable all components except file selection
        self._enable_list_tables_button(False)
        self._enable_table_selection(False)
        self._enable_ok(False)

        self.__unique_table_id = 0  # for creating unique new table name during export
        self.__default_table_name = None

        self.ui.browse_files_button.clicked.connect(self._slot_on_browse_files)
        self.ui.filepath_linedit.textChanged.connect(self._slot_on_filepath_changed)
        self.ui.filepath_linedit.editingFinished.connect(self.__slot_on_file_path_entered)
        self.ui.list_tables_button.clicked.connect(self._slot_on_table_list_requested)
        self.ui.table_combobox.currentIndexChanged['int'].connect(self._slot_on_table_selected)

        if last_db_export_path is not None:
            self.ui.filepath_linedit.setText(last_db_export_path)
            self._on_filepath_changed()
            self._on_table_list_requested(True)
            # put focus here so user doesn't have to click out of filepath_linedit
            # which triggers editingFinished signal that resets dialog elements
            self.ui.table_combobox.setFocus(Qt.OtherFocusReason)

        if table_part.filter_string:
            self.ui.filter_linedit.setText(table_part.filter_string)
        else:
            self.ui.filter_linedit.setVisible(False)
            self.ui.filter_label.setVisible(False)

    @override(TableEditorDialog)
    def get_user_input(self) -> Tuple[str, str, list]:
        db_path = self.ui.filepath_linedit.text()
        db_table = self.ui.table_combobox.currentText()
        db_selected_fields = self.__db_selected_fields
        return db_path, db_table, db_selected_fields

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(TableEditorDialog)
    def _validate_user_input(self) -> bool:
        """
        The database path and table are already validated. Currently, the filter is not validated
        but will show an error dialog if there is a problem. So here, just check that there are column
        field names selected.
        """
        # create a list of the selected table fields
        num_fields = self.ui.fields_listwidget.count()
        self.__db_selected_fields = []
        for idx in range(num_fields):
            field_item = self.ui.fields_listwidget.item(idx)
            if field_item.checkState() == Qt.Checked:
                self.__db_selected_fields.append(field_item.text())

        if not self.__db_selected_fields:
            msg = "There is nothing to export since no fields were selected."
            exec_modal_dialog("No Fields Selected", msg, QMessageBox.Information)
            return False

        # make required modifications to the selected table name
        if self.ui.table_combobox.currentText() == self.__default_table_name + self.NEW_STR:
            self.__unique_table_id += 1  # increment for next export
            self.ui.table_combobox.setItemText(0, self.__default_table_name)  # remove '(New)' on default table name

        elif self.ui.table_combobox.findText(self.ui.table_combobox.currentText()) == -1:
            # the user edited the default name, add it to the combo box
            new_table_name = self.ui.table_combobox.currentText()
            self.ui.table_combobox.insertItem(0, new_table_name)  # add the user-entered name
            self.ui.table_combobox.setCurrentText(new_table_name)

        else:
            pass  # no other entries require modification

        return True

    @override(TableImportExportDialog)
    def _on_browse_files(self, _: bool):
        """
        Opens a file browser to select the Access file to export.
        """
        select_file_dialog = QFileDialog(self, "Export to Access: select or create file",
                                         QSettings().value(self.LAST_EXPORT_DIR),
                                         "Access (*.mdb *.accdb)")
        select_file_dialog.setFileMode(QFileDialog.AnyFile)
        path_selected = select_file_dialog.exec()
        if not path_selected:
            return

        self.ui.filepath_linedit.setText(select_file_dialog.selectedFiles()[0])
        self._on_filepath_changed()
        self.__on_filepath_entered()

    @override(TableImportExportDialog)
    def _on_filepath_changed(self, _: str = None):
        """
        Update the path to the selected Access file.
        """
        self._enable_ok(False)
        self._enable_table_selection(False)

        # disable until we know a valid file path was entered
        self._enable_list_tables_button(False)
        db_path = self.ui.filepath_linedit.text()
        if not db_path:
            return

        QSettings().setValue(self.LAST_EXPORT_DIR, str(Path(db_path).parent))
        self._enable_list_tables_button(True)

    @override(TableImportExportDialog)
    def _on_table_list_requested(self, _: bool):
        """
        Request the list of tables from the selected Access file and populate the combobox.
        """
        self.ui.table_combobox.clear()  # remove all previous entries
        db_path = self.ui.filepath_linedit.text()

        try:
            self.set_tables(get_db_tables(db_path))
        except Exception as exc:
            msg_title = 'Table List Error'
            error_msg = 'The list of tables could not be retrieved from database \'{}\'.\n{}'.format(db_path, exc)
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            return

        # Pull out the table names (do not need associated fields already in the db)
        tables = [table for table in self._tables.keys()]

        # create a new blank default table - ensure its name is not in the current list of tables
        while True:
            default_table = '{}_{}'.format(self._part.name, self.__unique_table_id)
            if self.__is_table_name_used(default_table):
                self.__unique_table_id += 1
            else:
                break

        tables.insert(0, default_table + self.NEW_STR)
        self.__default_table_name = default_table
        self.ui.table_combobox.insertItems(0, tables)
        self._enable_table_selection(True)
        self._enable_ok(True)

    def _on_table_selected(self, index: int):
        """
        Responds to table selection via the dialog's combo box. Sets the dialog to editable when the "new" table in the
            first entry is selected, and not-editable otherwise.
        :param index: The index currently selected.
        """
        if index == 0:
            self.ui.table_combobox.setEditable(True)
        else:
            self.ui.table_combobox.setEditable(False)

    @override(TableImportExportDialog)
    def _enable_table_selection(self, enabled: bool):
        """
        Override to remove field list disabling.
        """
        self.ui.table_label.setEnabled(enabled)
        self.ui.table_combobox.setEnabled(enabled)
        self.ui.table_combobox.setCurrentIndex(0)  # show the first entry

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    _slot_on_browse_files = safe_slot(_on_browse_files)
    _slot_on_filepath_changed = safe_slot(_on_filepath_changed)
    _slot_on_table_list_requested = safe_slot(_on_table_list_requested)
    _slot_on_table_selected = safe_slot(_on_table_selected)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __populate_field_names(self, fields: List[str]):
        """
        When a table is selected, populate the list widget with the table's field names.
        :param fields: A list of column header names.
        """
        self.ui.fields_listwidget.clear()  # remove all previous entries
        for field in fields:
            field_item = QListWidgetItem(field)
            field_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            field_item.setCheckState(Qt.Checked)
            self.ui.fields_listwidget.addItem(field_item)

    def __is_table_name_used(self, new_table_name: str) -> bool:
        """
        Use to check if the new table name generated is already in the Access database.
        :param new_table_name: The new table to insert into the Access database.
        :return: A flag that is True if the table name is already used and False, otherwise.
        """
        for table in self._tables.keys():
            # Use case insensitive comparison: MS Access will
            # replace existing tables with the new default table
            # even if the new table name is a different case.
            if new_table_name.lower() == table.lower():
                return True

        return False

    def __on_filepath_entered(self):
        """
        Updates the file path displayed and verifies the directory exists when editing is finished.
        """
        db_path = self.ui.filepath_linedit.text()
        if not db_path:
            return

        db_path = Path(db_path)

        # if only file name entered without full path, prepend cwd
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path

        # add extension if missing
        if db_path.suffix == '':
            db_path = db_path.with_suffix('.mdb')  # only one supported for export

        # for manually entered paths, check that the parent directory exists
        if not db_path.parent.exists():
            title = 'Directory Does Not Exist'
            msg = 'The specified directory does not exist. Press OK to create the directory or Cancel to go back.'
            ok = exec_modal_dialog(title, msg, QMessageBox.Information,
                                   buttons=[QMessageBox.Ok, QMessageBox.Cancel])
            if ok == QMessageBox.Ok:
                log.info('Creating export directory: {}', db_path.parent)
                Path.mkdir(db_path.parent, parents=True)
            else:
                self._enable_list_tables_button(False)
                return

        # reset the path with the updated info
        self.ui.filepath_linedit.setText(str(db_path))

    __slot_on_file_path_entered = safe_slot(__on_filepath_entered)


class FilterColumnDialog(TableEditorDialog):
    """
    Filter dialog to apply a filter via SQL command to the table data.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, table_part: TablePart, table_model: QAbstractTableModel, table_editor: QWidget):
        ui = Ui_TableFilterDialog()
        super().__init__(table_part, ui, parent=table_editor)

        self.__table_model = table_model
        self.setWindowTitle('Filter')
        self.__filter = table_model.filter
        self.ui.sql_filter_line_edit.setText(self.__filter)
        self.__current_columns = [name.rstrip('*') for name in self.__table_model.col_name_cache]

    @override(TableEditorDialog)
    def reject_changes(self):
        """
        Remove any filter changes that were not accepted by reinitializing the dialog table with original filter.
        """
        self.ui.sql_filter_line_edit.setText(self.__table_model.filter)

    @override(TableEditorDialog)
    def get_user_input(self) -> str:
        return self.__filter

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(TableEditorDialog)
    def _validate_user_input(self) -> bool:
        """Set the filter. Validation will occur when the filter is executed."""
        self.__filter = self.ui.sql_filter_line_edit.text()
        return True


class ColumnIndexDialog(TableEditorDialog):
    """
    Index dialog to create or remove indexed columns in the table.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, table_part: TablePart, table_model: QAbstractTableModel, table_editor: QWidget):

        ui = Ui_TableIndexDialog()
        super().__init__(table_part, ui, parent=table_editor)

        # Set the dialog title
        self.setWindowTitle('Table Index')

        # Init index table widget
        self.ui.table_widget.setRowCount(0)
        self.ui.table_widget.setSelectionBehavior(QAbstractItemView.SelectItems)

        self.__table_model = table_model
        self.__col_indices = None
        self.__current_columns = [name.rstrip('*') for name in table_model.col_name_cache]
        self.__init_index_table(table_model.indexed_columns)

        # Connect add/remove
        self.ui.add_button.clicked.connect(self.__slot_add_index)
        self.ui.delete_button.clicked.connect(self.__slot_delete_index)

    @override(TableEditorDialog)
    def reject_changes(self):
        """
        Remove any index changes that were not accepted by reinitializing the dialog table with original indexes.
        """
        self.ui.table_widget.setRowCount(0)
        self.__init_index_table(self.__table_model.indexed_columns)

    @override(TableEditorDialog)
    def get_user_input(self) -> List[Tuple[str]] or None:
        return self.__col_indices

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(TableEditorDialog)
    def _validate_user_input(self) -> bool:
        self.__col_indices = self.__create_index_dict()
        if self.__col_indices is None:
            return False

        return True

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __add_index(self, _: bool):
        """
        Appends a new row to the index table.
        """
        new_row_index = self.ui.table_widget.rowCount()
        self.ui.table_widget.insertRow(new_row_index)
        indexed_columns_widget = QTableWidgetItem()
        indexed_columns_widget.setText('')
        self.ui.table_widget.setItem(new_row_index, 0, indexed_columns_widget)

    def __delete_index(self, _: bool):
        """
        Removes a row from the index table.
        """
        selected_row = self.ui.table_widget.currentRow()
        if selected_row != -1:
            # Remove the selected row
            self.ui.table_widget.removeRow(selected_row)

    def __init_index_table(self, indices: List[List[str]]):
        """
        Set up the index table using current indexes, if any.
        :param indices: the current indexed columns.
        """
        row = 0
        for index_cols in indices:
            indexed_columns = ', '.join(index_cols)
            new_row_index = self.ui.table_widget.rowCount()
            self.ui.table_widget.insertRow(new_row_index)
            indexed_columns_widget = QTableWidgetItem()
            indexed_columns_widget.setText(indexed_columns)
            self.ui.table_widget.setItem(row, 0, indexed_columns_widget)
            row += 1

    def __create_index_dict(self) -> List[Tuple[str]] or None:
        """
        Constructs the dictionary of indexes from the table widget to send to the back-end.
        :returns: a list of column indexes.
        """
        col_indices = {}  # init the dict to track new indices

        # loop through the dialog's table and validate each row of user-entered info
        # skip blank rows
        # duplicate entries are tracked and reported to user if found and excluded from returned index list
        rows = self.ui.table_widget.rowCount()
        for row in range(rows):
            indexed_columns = self.ui.table_widget.item(row, 0).text()
            if len(indexed_columns) == 0:
                # blank row, skip to next row
                continue

            # create a list of columns
            indexed_col_names = [col_name.strip() for col_name in indexed_columns.split(sep=',')]

            # check names exists in table
            for col_name in indexed_col_names:
                if col_name not in self.__current_columns:
                    # if any column is not found in the index list, prompt the user and return to the Index dialog
                    msg_title = 'Column Name Error'
                    error_msg = 'Column name "{}" not found in the table. Index at row #{} could not be created.'
                    error_msg = error_msg.format(col_name, row + 1)
                    exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
                    log.error('{}: {}', msg_title, error_msg)
                    return None

            # track the indices as keys in the dict, values are a list of rows where the index appears
            # 'setdefault' will determine if the index already exists or not, adding a new key and empty list
            # if it doesn't
            # append is the list method that adds the row value to the end of the list
            col_indices.setdefault(tuple(indexed_col_names), []).append(row)

        dupl_list = ['- Index for column(s) {} appears in rows {}'.format(
            ', '.join(repr(c) for c in index), ', '.join(str(r + 1) for r in rows))
            for index, rows in col_indices.items() if len(rows) > 1]

        if dupl_list:
            MAX_SHOW = 10  # cap the list at 10 to keep dialog short
            msg_title = 'Duplicate Indices Found'
            msg = ['The following duplicate indices were found:  ']
            msg.extend(dupl_list[:MAX_SHOW])
            if len(dupl_list) > MAX_SHOW:  # cap the list at 10 for practicality
                msg.append(' plus {} more...'.format(len(dupl_list) - MAX_SHOW))

            msg.append('')
            msg.append('Do you wish to continue with only a single index for each set of duplicates?')
            msg.append('Click Yes to proceed or No to go back.')

            answer = exec_modal_dialog(msg_title, '\n'.join(msg), QMessageBox.Question)
            if answer == QMessageBox.No:
                return None

        return list(col_indices.keys())

    __slot_add_index = safe_slot(__add_index)
    __slot_delete_index = safe_slot(__delete_index)


class InsertBeforeOrAfterEnum(Enum):
    """
    Enumerate where to insert a new row or column (before or after the index supplied).
    """
    before, after = range(2)


class PasteTypeEnum(Enum):
    """
    Enumerate the type of paste operation being performed. Types are specified by the shape of the data being pasted
    (e.g. row, column, or general range) and the preceeding operation which is either copy or cut.
    """
    any_from_copy, col_from_cut, row_from_cut, cell_from_cut = range(4)


class TablePartTableModelForEditing(QAbstractTableModel):
    """
    Implements a table Model for getting and setting Table Part data.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    sig_rows_changed = pyqtSignal(int)  # number of rows
    sig_cols_changed = pyqtSignal(int)  # number of columns
    sig_filter_changed = pyqtSignal(bool)  # True if filter applied

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, table_part: TablePart, parent: QWidget = None):
        super().__init__(parent)

        # The backend part to view
        self.__table_part = table_part

        # a set of all unique record ids in this table
        self.__all_record_ids = []

        # Init row and column count values
        self.__rows = 0
        self.__cols = 1

        # Store the previous row and column counts for tracking purposes
        self.__orig_rows = 0
        self.__orig_cols = 1

        # Cache back-end database data for quick front-end updates
        self.__col_name_cache = []
        self.__record_cache = []
        self.__record_cache_filtered = []
        self.__cells_copied = None
        self.__display_order = DisplayOrderEnum.of_creation
        self.__sorted_column = [0]
        self.__col_types = []
        self.__col_sizes = []
        self.__col_indexes = []
        self.__filter = str()
        self.__map_recid_to_rowidx = {}
        self.__ids_filtered_recs_removed = []

        # Front-end data copies
        self.__records_copied = []
        self.__columns_copied = []
        self.__rec_data_in_column_copied = {}
        self.__rec_filtered_data_in_column_copied = {}

    @override(QAbstractTableModel)
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> Either[str, None]:
        """
        Gets the current horizontal (column) and vertical (row) header data from the Table Part at the index 'section'.
        See the Qt documentation for method parameter definitions.
        """
        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal:
            try:
                col_name = self.__get_displayed_col_name(self.__col_name_cache[section])
                col_type = self.__col_types[section]
                return self.__create_column_label(col_name, col_type)

            except IndexError:
                # Need to handle case where View asks for header data while column name cache is empty due to
                # a refresh of the table data.
                return None

        if orientation == Qt.Vertical and section < self.__rows:
            return str(section + 1)  # The first row is row '1'

        return None

    @override(QAbstractTableModel)
    def setHeaderData(self, section: int, orientation: Qt.Orientation, header: QVariant, role=Qt.EditRole) -> bool:
        """
        Sets the horizontal (column) header data into the Table Part at index 'section'. Only column headers can be set.
        See the Qt documentation for method parameter definitions.
        """
        if role == Qt.EditRole and orientation == Qt.Horizontal:
            col_index = section
            header_label = header.value()
            col_name, col_type = self.__parse_column_label(header_label)

            try:
                # update column name and type values
                self.__col_name_cache[col_index] = col_name
                self.__set_column_type(col_index, col_type)
                self.headerDataChanged.emit(orientation, section, section)
                return True

            except IndexError:
                # Need to handle case where View asks for header data while column name cache is empty due to
                # a refresh of the table data.
                pass

        return False

    @override(QAbstractTableModel)
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of rows in the Table Part cache (parent_index invalid), or 0 if parent_index is valid.

        To understand the following docstring it is important to understand that Qt view for a table assumes
        a "root" model index in which there is one child index for each cell of the table, and that
        the "root" index corresponds to an "invalid" Qt index object whereas the children indices of
        root index are themselves valid. This method does get called for children of the "root"
        index, in which case must return 0.
        """
        # Return zero rows if child index (i.e. valid index)
        if parent_index.isValid():
            return 0

        return self.__rows

    @override(QAbstractTableModel)
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of columns in the Table Part cache (if parent_index invalid), or 0 if parent_index is valid.

        To understand the following docstring it is important to understand that Qt view for a table assumes
        a "root" model index in which there is one child index for each cell of the table, and that
        the "root" index corresponds to an "invalid" Qt index object whereas the children indices of
        root index are themselves valid. This method does get called for children of the "root"
        index, in which case must return 0.
        """
        # Return zero cols if child index (i.e. valid index)
        if parent_index.isValid():
            return 0

        return self.__cols

    @override(QAbstractTableModel)
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Optional[TableCellData]:
        """
        This method returns the Table Part data located at 'index' to the Table Part's View (class TablePart2dContent).

        View requests an update when the signal 'dataChanged' is emitted by one of this class' slots. Each slot is set
        to receive a specific signal from the backend Table Part when data in the table has changed. For example, a row
        update across a subset of rows would cause the slot 'slot_update_rows' to be called with the affected row index
        range. The dataChanged signal is called in turn, causing the View to update the contents of the specified rows.

        See the Qt documentation for method parameter definitions.
        """
        if not index.isValid():
            # the index is the "root" of table, which has no data
            return None

        # Return a value if either DisplayRole or EditRole is obtained...
        # This ensures that while editing, the original value is preserved until setData() is called to update to the
        # new value (otherwise this method will return None during editing which clears the original cell value even
        # when the user does not edit the value).
        if role == Qt.DisplayRole or role == Qt.EditRole:

            # Access the record ID and column name from the dictionary
            row_index = index.row()
            col_index = index.column()

            # Check if there is something in the cache to return
            try:
                if self.__filter:
                    record = self.__record_cache_filtered[row_index]
                else:
                    record = self.__record_cache[row_index]

                if role == Qt.DisplayRole:
                    # For display purposes show the value as a string to prevent auto-formatting by Qt display delegate
                    return str(record[col_index])
                elif role == Qt.EditRole:
                    # Otherwise, return the value formatted to the correct type for editing
                    return record[col_index]

            except IndexError:
                # Need to handle case where View asks for header data while record cache is empty due to
                # a refresh of the table data.
                return None

        if role == Qt.TextAlignmentRole:
            return Qt.AlignHCenter | Qt.AlignVCenter

        if role == Qt.BackgroundRole:
            row_index = index.row()
            col_index = index.column()

            return self.__validate_data_matches_col_type(row_index, col_index)

        return None

    @override(QAbstractTableModel)
    def setData(self, index: QModelIndex, value: QVariant, role: int = Qt.EditRole):
        """
        Sets data from the Table Part editor.

        Sets the role data for the item at index to value.
        Returns true if successful; otherwise returns false.
        The dataChanged() signal should be emitted if the data was successfully set.
        The base class implementation returns false. This function and data() must be reimplemented for editable models.
        :param index: a QModelIndex for the item being changed.
        :param value: the new value to set.
        :param role: the data role (default Qt.EditRole)
        :return: returns true if successful; otherwise returns false.
        """
        if not index.isValid():
            # the index is the "root" of table, which has no data
            return False

        if role == Qt.EditRole:
            # Access the record ID and column name from the dictionary
            row_index = index.row()
            col_index = index.column()

            value = self.__data_type(value, col_index)

            try:
                # update the record cache
                if self.__filter:
                    self.__record_cache_filtered[row_index][col_index] = value
                else:
                    self.__record_cache[row_index][col_index] = value

                cell_index = self.index(row_index, col_index)
                self.dataChanged.emit(cell_index, cell_index)
                return True

            except IndexError:
                # Need to handle case where View asks for header data while record cache is empty due to
                # a refresh of the table data.
                pass

        return False

    @override(QAbstractTableModel)
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Sets all items in the Table's view to be 'selectable', 'editable', and 'enabled'.
        See the Qt documentation for method parameter definitions.
        """
        if not index.isValid():
            return Qt.NoItemFlags

        return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled

    @override(QAbstractTableModel)
    def insertColumns(self, insert_index: int, num_columns: int, parent=QModelIndex()) -> bool:
        """
        Inserts columns into the model before the given column index, insert_index.
        See the Qt documentation for method parameter definitions.
        """
        # Notify other components the table has changed
        self.beginInsertColumns(parent, insert_index, insert_index + num_columns - 1)
        self.sig_cols_changed.emit(self.cols)
        self.endInsertColumns()

        # Check that a columns have been added
        return self.__orig_cols < self.__cols

    @override(QAbstractTableModel)
    def removeColumns(self, remove_index: int, num_columns: int, parent=QModelIndex()) -> bool:
        """
        Removes columns of number num_columns starting with the given column index, remove_index.
        See the Qt documentation for method parameter definitions.
        """
        # Notify other components the table has changed
        self.beginRemoveColumns(parent, remove_index, remove_index + num_columns - 1)
        self.sig_cols_changed.emit(self.cols)
        self.endRemoveColumns()

        # Check that a columns have been removed
        return self.__orig_cols > self.__cols

    @override(QAbstractTableModel)
    def insertRows(self, insert_index: int, num_rows: int, parent=QModelIndex()) -> bool:
        """
        Inserts rows of number num_rows into the model before the given row index, insert_index.
        See the Qt documentation for method parameter definitions.
        """
        # Notify other components the table has changed
        self.beginInsertRows(parent, insert_index, insert_index + num_rows - 1)
        self.sig_rows_changed.emit(self.rows)
        self.endInsertRows()

        # Check that a rows have been added
        return self.__orig_rows < self.__rows

    @override(QAbstractTableModel)
    def removeRows(self, remove_index: int, num_rows: int, parent=QModelIndex()) -> bool:
        """
        Removes rows of number num_rows starting with the given row index, remove_index.
        See the Qt documentation for method parameter definitions.
        """
        # Notify other components the table has changed
        self.beginRemoveRows(parent, remove_index, remove_index + num_rows - 1)
        self.sig_rows_changed.emit(self.rows)
        self.endRemoveRows()

        # Check that a rows have been removed
        return self.__orig_rows > self.__rows

    def init_model(self, data: dict):
        """
        Initializes the table editor data content and attributes.
        :param data: the back-end table data.
        """
        self.beginResetModel()

        self.__on_init_col_names(data['col_names'])
        self.__on_init_table_records(data['records'])
        self.__col_types = [SqliteDataTypesEnum[type] for type in data['col_types']]
        self.__col_sizes = data['col_sizes']
        self.set_indexed_columns(data['col_indexes'])
        self.set_filter(data['filter'])
        self.set_display_order(data['display_order'])
        self.set_sorted_column(data['sorted_column'])

        self.endResetModel()

    def fill_data_for_submission(self, data: dict):
        """
        Fills the the data dictionary with the edited table data for submission to the back-end Table Part.
        :param data: the data to submit.
        """
        data['records'] = [tuple(rec) for rec in self.get_rec_cache()]
        data['col_names'] = self.__col_name_cache
        data['col_types'] = [type.name for type in self.__col_types]
        data['col_sizes'] = self.__col_sizes
        data['col_indexes'] = self.__col_indexes
        data['filter'] = self.__filter
        data['display_order'] = self.display_order
        data['sorted_column'] = self.sorted_column

    def insert_rows(self, row_indexes_to_insert: List[int], where: InsertBeforeOrAfterEnum,
                    records: DbRawRecords = None, insert_after_selection: bool = True):
        """
        Inserts rows into the table before or after the given row index.
        :param row_indexes_to_insert: a list of row indexes to insert.
        :param where: indicates whether to insert before or after the row_index provided.
        :param records: a list of records insert. Inserts an empty record if None.
        :param insert_after_selection: indicates if the new rows should be inserted after or at the selected row.
        """
        if self.__filter:
            cache = self.__record_cache_filtered
            is_filtered = True
        else:
            cache = self.__record_cache
            is_filtered = False

        if where == InsertBeforeOrAfterEnum.before:
            if records is None:
                # Insert a contiguous selection via the Insert button (empty records)
                for row in row_indexes_to_insert:
                    rec = self.__create_empty_row(is_filtered)
                    cache.insert(row, rec)

                num_rows_to_add = len(row_indexes_to_insert)

            else:
                # Insert a copied selection at the selected point
                insert_row = row_indexes_to_insert[0]
                for rec in records:
                    rec = DbRecord(rec[:], taken_ids=self.__all_record_ids, is_filtered=is_filtered)
                    if rec.id is not None:
                        self.__all_record_ids.append(rec.id)

                    cache.insert(insert_row, rec)
                    insert_row += 1

                num_rows_to_add = len(records)

            # Inform the Table View of the change
            row_start_index = row_indexes_to_insert[0]
            self.__rows += num_rows_to_add
            self.insertRows(row_start_index, num_rows_to_add)
            top_left_index = self.index(row_start_index, 0)
            bottom_right_index = self.index(row_start_index + num_rows_to_add, self.__cols - 1)
            self.dataChanged.emit(top_left_index, bottom_right_index)

        else:
            # Shift the indexes to the end of the selection
            shift = len(row_indexes_to_insert)
            if insert_after_selection:
                for idx, _ in enumerate(row_indexes_to_insert):
                    row_indexes_to_insert[idx] += shift

            # Add records to the cache
            for row in row_indexes_to_insert:
                rec = self.__create_empty_row(is_filtered)
                cache.insert(row, rec)

            # Inform the Table View of the change
            row_start_index = row_indexes_to_insert[0]
            num_rows_to_add = shift
            self.__rows += num_rows_to_add
            self.insertRows(row_start_index, num_rows_to_add)
            top_left_index = self.index(row_start_index, 0)
            bottom_right_index = self.index(row_start_index + num_rows_to_add, self.__cols - 1)
            self.dataChanged.emit(top_left_index, bottom_right_index)

        # need to regenerate record id map
        if not self.__filter:
            self.__regenerate_recid_map()

    def remove_rows(self, row_start_index: int, num_rows: int = 1):
        """
        Removes the selected rows.
        :param row_start_index: the row where the selection starts.
        :param num_rows: the number of contiguously selected rows.
        """
        if self.__filter:
            # if filter is on, track removed records so they can also be removed from unfiltered
            # cache on commit to backend
            cache = self.__record_cache_filtered
            for row in range(row_start_index, row_start_index + num_rows):
                rec = self.__record_cache_filtered[row]
                if rec.id is not None:  # ids that are None have not been added to unfiltered cache so no need to track
                    self.__ids_filtered_recs_removed.append(rec.id)

        else:
            cache = self.__record_cache

        del cache[row_start_index:row_start_index + num_rows]

        # need to regenerate record id map
        if not self.__filter:
            self.__regenerate_recid_map()

        # Inform the Table View of the change
        self.__rows -= num_rows
        top_left_index = self.index(row_start_index, 0)
        bottom_right_index = self.index(row_start_index + num_rows, self.__cols - 1)
        self.removeRows(row_start_index, num_rows)
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def insert_columns(self, col_indexes_to_insert: List[int],
                       where: InsertBeforeOrAfterEnum,
                       columns_copied: List[Tuple[str, str, int]] = None,
                       insert_after_selection: bool = True):
        """
        Inserts columns into the table before or after the given column index.
        :param col_indexes_to_insert: a list of column indexes to insert.
        :param where: indicates whether to insert before or after the col_index provided.
        :param columns_copied: a list of copied column names, types and sizes.
        :param insert_after_selection: indicates if the new columns should be inserted after or at the selected column.
        """
        if where == InsertBeforeOrAfterEnum.before:
            if columns_copied is None:
                # insert a contiguous selection via the Insert button (empty column names)
                for col in col_indexes_to_insert:
                    # auto-generate a name (backend name cannot be empty or a number)
                    set_name = self.__get_unique_column_name(col)
                    self.__col_name_cache.insert(col, set_name)
                    self.__col_types.insert(col, SqliteDataTypesEnum.TEXT)  # default
                    self.__col_sizes.insert(col, None)  # default

                    # add a new column to each un-filtered record
                    for record in self.__record_cache:
                        record.insert(col, str())

                    # if filtered, add a new column to each filtered record
                    if self.__filter:
                        for record in self.__record_cache_filtered:
                            record.insert(col, str())

                num_cols_to_add = len(col_indexes_to_insert)

            else:
                # insert a copied selection at the selected point
                col = col_indexes_to_insert[0]
                for col_name, col_type, col_size in columns_copied:
                    # ensure the name is unique (required by back-end embedded DB)
                    if col_name in self.__col_name_cache:
                        set_name = col_name + str(len(self.__col_name_cache))
                    else:
                        set_name = col_name

                    self.__col_name_cache.insert(col, set_name)
                    self.__col_types.insert(col, col_type)
                    self.__col_sizes.insert(col, col_size)

                    # add a new column to each un-filtered record
                    for row, record in enumerate(self.__record_cache):
                        record.insert(col, self.__rec_data_in_column_copied[col_name][row])

                    # if filtered, add a new column to each filtered record
                    if self.__filter:
                        for row, record in enumerate(self.__record_cache_filtered):
                            record.insert(col, self.__rec_filtered_data_in_column_copied[col_name][row])

                    col += 1

                num_cols_to_add = len(columns_copied)

            # inform the Table View of the change
            col_start_index = col_indexes_to_insert[0]
            self.__cols += num_cols_to_add
            self.insertColumns(col_start_index, num_cols_to_add)
            self.headerDataChanged.emit(Qt.Horizontal, col_start_index, col_start_index + num_cols_to_add - 1)

        else:
            # Shift the indexes to the end of the selection
            shift = len(col_indexes_to_insert)
            if insert_after_selection:
                for idx, _ in enumerate(col_indexes_to_insert):
                    col_indexes_to_insert[idx] += shift

            # Add column header to the cache - use index as column name (backend name cannot be empty)
            for col in col_indexes_to_insert:
                # Auto-generate a name (backend name cannot be empty or a number)
                set_name = self.__get_unique_column_name(col)
                self.__col_name_cache.insert(col, set_name)
                self.__col_types.insert(col, SqliteDataTypesEnum.TEXT)  # default
                self.__col_sizes.insert(col, None)  # default

                # add a new column to each un-filtered record
                for record in self.__record_cache:
                    record.insert(col, str())

                # if filtered, add a new column to each filtered record
                if self.__filter:
                    for record in self.__record_cache_filtered:
                        record.insert(col, str())

            # Inform the Table View of the change
            col_start_index = col_indexes_to_insert[0]
            num_cols_to_add = shift
            self.__cols += num_cols_to_add
            self.insertColumns(col_start_index, num_cols_to_add)
            self.headerDataChanged.emit(Qt.Horizontal, col_start_index, col_start_index + num_cols_to_add - 1)

    def remove_columns(self, col_start_index: int, num_cols: int = 1):
        """
        Cut the contiguously selected columns.
        :param col_start_index: the column where the selection starts.
        :param num_cols: the number of contiguously selected columns.
        """
        # update the indexed columns if they are to be removed
        names_to_remove = self.__col_name_cache[col_start_index:col_start_index + num_cols]
        self.__augment_indexed_columns(names_to_remove)

        del self.__col_name_cache[col_start_index:col_start_index + num_cols]
        del self.__col_types[col_start_index:col_start_index + num_cols]
        del self.__col_sizes[col_start_index:col_start_index + num_cols]

        # remove from data under each removed column from the un-filtered data cache
        for record in self.__record_cache:
            del record[col_start_index:col_start_index + num_cols]

        # if filtered, remove from data under each removed column from the filtered data cache
        if self.__filter:
            for record in self.__record_cache_filtered:
                del record[col_start_index:col_start_index + num_cols]

        # inform the Table View of the change
        self.__cols -= num_cols
        self.removeColumns(col_start_index, num_cols)
        self.headerDataChanged.emit(Qt.Horizontal, col_start_index, col_start_index + num_cols)

        # refresh table
        top_left_index = self.index(0, 0)
        bottom_right_index = self.index(self.__rows - 1, self.__cols - 1)
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def update_cells(self, selected_cells: list, values: List[List[Any]] = None):
        """
        Updates the selected cells to the specified values. If values is None, the cell value is cleared.
        :param selected_cells: the cell selection as a list of indexes: [[top-left], [bottom-right]
        :param values: new values to assign to the selected cells.
        """
        if self.__filter:
            cache = self.__record_cache_filtered
        else:
            cache = self.__record_cache

        row_start = selected_cells[0][0]
        col_start = selected_cells[0][1]
        row_end = selected_cells[1][0]
        col_end = selected_cells[1][1]

        if values is None:
            # Iterate over the selected range and clear the current value
            for rec in range(row_start, row_end + 1):
                for col in range(col_start, col_end + 1):
                    col_type = self.__col_types[col]
                    if col_type == SqliteDataTypesEnum.DATETIME:
                        cache[rec][col] = datetime.now().strftime(SQLITE_DATETIME_FORMAT)
                    elif col_type == SqliteDataTypesEnum.INTEGER:
                        cache[rec][col] = 0
                    elif col_type in REAL_TYPES:
                        cache[rec][col] = 0.0
                    else:  # TEXT
                        cache[rec][col] = str()

        else:
            # Iterate over the values and update the cells starting from the currently selected cell.
            # Values are used to iterate rather than the selection since the user may copy a selection and then
            # click elsewhere to paste it.
            # Augment start and end indexes in case values are updated after user selects a single cell
            row_end = row_start + len(values) - 1
            col_end = col_start + len(values[0]) - 1
            row_idx = row_start
            for cells in values:
                col_idx = col_start
                for cell in cells:
                    cache[row_idx][col_idx] = cell
                    col_idx += 1

                row_idx += 1

        # Inform the Table View of the change
        top_left_index = self.index(row_start, col_start)
        bottom_right_index = self.index(row_end, col_end)
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def cut_rows(self, row_start_index: int, num_rows: int = 1):
        """
        Cut the contiguously selected rows.
        :param row_start_index: the row where the selection starts.
        :param num_rows: the number of contiguously selected rows.
        """
        self.copy_rows(row_start_index, num_rows)
        self.remove_rows(row_start_index, num_rows)

    def copy_rows(self, row_start_index: int, num_rows: int = 1):
        """
        Copy of the contiguously selected rows.
        :param row_start_index: the row where the selection starts.
        :param num_rows: the number of contiguously selected rows.
        """
        if self.__filter:
            cache = deepcopy(self.__record_cache_filtered)
        else:
            cache = deepcopy(self.__record_cache)

        self.__records_copied = cache[row_start_index:row_start_index + num_rows]

    def paste_rows(self, selected_rows: List[int]):
        """
        Paste the previously cut or copied selection at the first index in 'selected_rows'.
        :param selected_rows: a list of row indexes corresponding to the selected rows.
        """
        if self.__records_copied is None:
            return

        # Copy the copy before paste, otherwise all copies will be the original copy
        copy = deepcopy(self.__records_copied)
        self.insert_rows(selected_rows, InsertBeforeOrAfterEnum.before, records=copy)

    def cut_columns(self, col_start_index: int, num_cols: int = 1):
        """
        Cut the contiguously selected columns.
        :param col_start_index: the column where the selection starts.
        :param num_cols: the number of contiguously selected columns.
        """
        self.copy_columns(col_start_index, num_cols)
        self.remove_columns(col_start_index, num_cols)

    def copy_columns(self, col_start_index: int, num_cols: int = 1):
        """
        Copy of the contiguously selected columns.
        :param col_start_index: the row where the selection starts.
        :param num_cols: the number of contiguously selected rows.
        """
        col_names = self.__col_name_cache[col_start_index:col_start_index + num_cols]
        col_types = self.__col_types[col_start_index:col_start_index + num_cols]
        col_sizes = self.__col_sizes[col_start_index:col_start_index + num_cols]
        self.__columns_copied = [(col_name, col_type, col_size)
                                 for col_name, col_type, col_size in zip(col_names, col_types, col_sizes)]

        # for each copied column, capture the data for all rows in that column
        # create a dictionary of column data for the unfiltered and filtered record caches
        self.__rec_data_in_column_copied = self.__create_column_data_dict(self.__record_cache, col_start_index,
                                                                          num_cols)

        if self.__filter:
            self.__rec_filtered_data_in_column_copied = self.__create_column_data_dict(self.__record_cache_filtered,
                                                                                       col_start_index,
                                                                                       num_cols)

    def paste_columns(self, selected_cols: List[int]):
        """
        Paste the previously cut or copied selection at the first index in 'selected_cols'.
        :param selected_cols: a list of column indexes corresponding to the selected columns.
        """
        if self.__columns_copied is None:
            return

        # Copy the copy before paste, otherwise all copies will be the original copy
        self.insert_columns(selected_cols, InsertBeforeOrAfterEnum.before, columns_copied=self.__columns_copied[:])

    def cut_cells(self, selected_cells: list):
        """
        Cut the contiguously selected cells. Cells are cleared but not removed from the table.
        :param selected_cells: the cell selection as a list of indexes: [[top-left], [bottom-right].
        """
        self.copy_cells(selected_cells)
        self.update_cells(selected_cells)

    def copy_cells(self, selected_cells: list):
        """
        Copy of the contiguously selected cells.
        :param selected_cells: the cell selection as a list of indexes: [[top-left], [bottom-right].
        """
        if self.__filter:
            cache = deepcopy(self.__record_cache_filtered)
        else:
            cache = deepcopy(self.__record_cache)

        self.__cells_copied = []
        row_start = selected_cells[0][0]
        row_end = selected_cells[1][0]
        col_start = selected_cells[0][1]
        col_end = selected_cells[1][1]

        # Python omits the last index so must + 1
        records_copied = [rec[:] for rec in cache[row_start:row_end + 1]]

        for rec in records_copied:
            rec_subset = rec[col_start:col_end + 1]  # Python omits the last index so must + 1
            self.__cells_copied.append(rec_subset)

    def paste_cells(self, selected_cells: List[int]):
        """
        Paste the previously cut or copied selection at the first index in 'selected_cells'.
        :param selected_cells: a list of cell indexes corresponding to the selected cells.
        """
        if self.__cells_copied is None:
            return

        # Check for sufficient dimensions to paste the copied cells
        num_rows_copied = len(self.__cells_copied)
        num_cols_copied = len(self.__cells_copied[0])
        top_row_selected_idx = selected_cells[0][0]
        left_col_selected_idx = selected_cells[0][1]
        num_rows_can_paste = self.rows - top_row_selected_idx
        num_cols_can_paste = self.cols - left_col_selected_idx

        if num_rows_copied > num_rows_can_paste or num_cols_copied > num_cols_can_paste:
            msg_title = 'Table Dimensions Error'
            error_msg = 'Attempting to update sheet values beyond current sheet dimensions.'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)
            return

        # Copy the copy before paste, otherwise all copies will be the original copy
        copy = [cell[:] for cell in self.__cells_copied]
        self.update_cells(selected_cells, values=copy)

        # for each pasted cell, covert the data to the type associated with the column
        columns = range(left_col_selected_idx, left_col_selected_idx + len(self.__cells_copied[0]))
        for col in columns:
            self.__set_data_to_column_type(col)

    def update_column_properties(self, col_index: int, new_name: str, new_col_type: str):
        """
        Updates the column name and type to the new name and type provided.
        :param col_index: the column index of the column.
        :param new_name: the new name to set.
        :param new_col_type: the new column type.
        """
        # if the name changed, remove the index on the column
        if self.__col_name_cache[col_index] != new_name:
            self.__augment_indexed_columns([self.__col_name_cache[col_index]])

        column_label = self.__create_column_label(new_name, SqliteDataTypesEnum[new_col_type])
        is_name_changed = self.setHeaderData(col_index, Qt.Horizontal, QVariant(column_label))
        if not is_name_changed:
            log.error('Column name did not update successfully.')

    def get_column_properties(self, col_index: int) -> Tuple[str, str]:
        """
        Returns the column name and type components that make up the header label of the given column.
        :param col_index: the index of the column.
        """
        header_data = self.headerData(col_index, Qt.Horizontal)
        return self.__parse_column_label(header_data)

    def move_column(self, init_col_index: int, dest_col_index: int):
        """
        Moves the selected column to a new location.
        :param init_col_index: the initial index of the moved column.
        :param dest_col_index: the destination index of the moved column.
        """
        num_cols = 1
        self.cut_columns(init_col_index, num_cols)
        self.paste_columns([dest_col_index])

    def get_part(self) -> TablePart:
        """
        Gets the Table Part of this table.
        :returns: the back-end Table Part.
        """
        return self.__table_part

    def get_rows(self) -> int:
        """
        Get the current number of rows.
        :returns the number of rows.
        """
        return self.__rows

    def get_cols(self) -> int:
        """
        Get the current number of columns.
        :returns: the number of columns.
        """
        return self.__cols

    def get_rec_cache(self) -> List[DbRecord]:
        """
        Returns the cache of ALL records in the editor, including edits, regardless of filter applied.
        """
        if self.__record_cache_filtered:
            # any records removed from the filtered cache should be removed from the unfiltered cache
            if self.__ids_filtered_recs_removed:
                # get a list of row indices to remove from the unfiltered cache
                row_idxs = []
                for rec_id in self.__ids_filtered_recs_removed:
                    row_idx = self.__map_recid_to_rowidx[rec_id]
                    row_idxs.append(row_idx)

                self.__ids_filtered_recs_removed = []  # clear list of rec ids to remove

                # sort and loop through in reverse order so that
                # row indices do not become invalid as rows are removed
                row_idxs = sorted(row_idxs, reverse=True)
                for row_idx in row_idxs:
                    del self.__record_cache[row_idx]

                # regenerate map since cache has been altered
                self.__regenerate_recid_map()

            # update the unfiltered records with changes made to the filtered cache
            # including adding rows and updating edited rows
            for filtered_rec in self.__record_cache_filtered:
                if filtered_rec.id is None:
                    # a new record was added while filtered: generate an ID, add it to unfiltered cache
                    filtered_rec.generate_id(self.__all_record_ids)
                    self.__all_record_ids.append(filtered_rec.id)
                    self.__record_cache.append(deepcopy(filtered_rec))
                    new_row_idx = len(self.__record_cache) - 1
                    self.__map_recid_to_rowidx[filtered_rec.id] = new_row_idx
                    continue

                # update changed records
                row_idx = self.__map_recid_to_rowidx[filtered_rec.id]  # get the row index for unfiltered record
                self.__record_cache[row_idx] = deepcopy(filtered_rec)

        return deepcopy(self.__record_cache)

    def get_rec_cache_filtered(self) -> List[DbRecord]:
        """Returns the cache of filtered records."""
        return self.__record_cache_filtered

    def get_col_name_cache(self) -> List[str]:
        """
        Returns the list of column names.
        :return:
        """
        return self.__col_name_cache

    def get_col_types(self) -> List[str]:
        """Returns the list of column types."""
        return self.__col_types

    def get_col_sizes(self) -> List[int]:
        """Returns the list of column sizes."""
        return self.__col_sizes

    def get_indexed_columns(self) -> List[Tuple[str]]:
        """
        Gets the list of indexed columns.
        :return: the indexed columns.
        """
        return self.__col_indexes

    def set_indexed_columns(self, indexed_columns: List[Tuple[str]]):
        """
        Sets the list of column indices where each index is a tuple of column names.
        :param indexed_columns: the indexed columns.
        """
        self.__col_indexes = indexed_columns
        for col_index in indexed_columns:
            for col_name in col_index:
                col_idx = self.__col_name_cache.index(col_name)
                self.headerDataChanged.emit(Qt.Horizontal, col_idx, col_idx)

    def get_display_order(self) -> DisplayOrderEnum:
        """
        Gets the current display order.
        :return: the sort order of the selected column.
        """
        return self.__display_order

    def set_display_order(self, display_order: DisplayOrderEnum):
        """
        Sets the display order.
        :param display_order: the sort order currently selected by the user.
        """
        self.__display_order = DisplayOrderEnum(display_order)

    def get_sorted_column(self) -> List[int]:
        """
        The column selected for sorting.
        :return: the column number in list format.
        """
        return self.__sorted_column

    def set_sorted_column(self, column: List[int]):
        """
        Sets the sorted column.
        """
        self.__sorted_column = column

    def get_filter(self) -> str:
        """
        Gets the current filter.
        :return: A string that will execute an SQL 'where' command.
        """
        return self.__filter

    def set_filter(self, sql_filter: str, is_refresh: bool = False):
        """
        Sets the current filter.
        :param sql_filter: A string that will execute an SQL 'where' command.
        :param is_refresh: A flag that indicates if the filter should be reset, regardless of whether it has changed.
        """
        if self.__filter == sql_filter and not is_refresh:
            return

        self.__filter = sql_filter

        # get copy of ALL current editted data
        recs = self.get_rec_cache()

        # insert the record ids into the data before filtering otherwise the id info will be lost
        for rec in recs:
            rec.insert(0, rec.id)

        # add a temp column for the ids
        col_names = ['TEMP_ID_COL'] + self.get_col_name_cache()
        col_types = ['INTEGER'] + [col_type.name for col_type in self.get_col_types()]
        col_sizes = [None] + self.get_col_sizes()

        def get_filtered_data(sql_filter):
            """
            This method is passed to the backend thread in order to apply the current SQL filter on the data in the
            editor panel. Note that the data in the editor, and not the backend table part, is filtered by the table
            part's embedded database. This must occur in the backend thread.

            :param sql_filter: The SQL statement that will select the specific data, effectively filtering it.
            """
            col_names_types_sizes = []
            for idx, col_name in enumerate(col_names):
                col_type = col_types[idx]
                col_size = col_sizes[idx]
                if col_size is not None:
                    col_names_types_sizes.append((col_name, col_type, int(col_size)))
                else:
                    col_names_types_sizes.append((col_name, col_type, col_size))

            filtered_data, _ = self.__table_part.embedded_db.filter_raw_data(recs,
                                                                             col_names,
                                                                             col_names_types_sizes,
                                                                             col_names,
                                                                             sql_filter)

            return filtered_data

        if sql_filter:
            def on_filtered_data_received(records: DbRawRecords):
                self.__set_filtered_records(records)

            def on_filtered_error(exc: AsyncErrorInfo):
                msg = 'The following error occurred while filtering the data: {}.'.format(exc.msg)
                exec_modal_dialog('Filter Error', msg, QMessageBox.Critical)

            AsyncRequest.call(get_filtered_data, sql_filter=sql_filter,
                              response_cb=on_filtered_data_received, error_cb=on_filtered_error)

        else:
            def on_unfiltered_data_receieved(records: DbRawRecords):
                self.__restore_unfiltered_records(records)

            AsyncRequest.call(get_filtered_data, sql_filter=None, response_cb=on_unfiltered_data_receieved)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    rows = property(get_rows)
    cols = property(get_cols)
    rec_cache = property(get_rec_cache)
    rec_cache_filtered = property(get_rec_cache_filtered)
    col_name_cache = property(get_col_name_cache)
    col_types = property(get_col_types)
    col_sizes = property(get_col_sizes)
    display_order = property(get_display_order, set_display_order)
    sorted_column = property(get_sorted_column, set_sorted_column)
    indexed_columns = property(get_indexed_columns, set_indexed_columns)
    filter = property(get_filter, set_filter)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __create_column_data_dict(self, record_cache: List[DbRecord],
                                  col_start_index: int,
                                  num_cols: int) -> Dict[str, DbRecord]:
        """
        Creates a dictionary of column data where each key is a column name and each value is the column data.
        :param record_cache: A record cache of data composed of several columns of data.
        :param col_start_index: The first column index to extract data from the cache and put into the dictionary.
        :param num_cols: The total number of columns to put into the dictionary.
        :return: The dictionary of column data.
        """
        col_data = {}
        for col_idx in range(col_start_index, col_start_index + num_cols):
            name = self.__col_name_cache[col_idx]
            col_data_list = []
            for rec_copy in record_cache:
                rec = rec_copy[:]
                col_data_list.append(rec[col_idx])

            col_data[name] = col_data_list

        return col_data

    def __on_init_col_names(self, col_names: List[str]):
        """
        Populate the column headers cache. If this is called as a result of an update, the caller must call
        headerDataChanged().
        :param col_names: name of each column
        """
        self.__col_name_cache = col_names
        self.__cols = len(col_names)
        self.sig_cols_changed.emit(self.__cols)

    def __on_init_table_records(self, all_records: DbRawRecords, is_restore: bool = False):
        """
        Populate the table data cache. If this is called as a result of an update, the caller must call
        beginModelReset() first, and call endModelReset() after.
        :param all_records: the records delivered from the back-end Table Part
        :param is_restore: flag indicates if this init is to retore records to previous unfiltered state.
        """
        # Make records editable/mutable by changing from tuple to list
        self.__record_cache = []
        self.__map_recid_to_rowidx = {}
        if not is_restore:
            self.__all_record_ids = []  # reset the list

        for row_index, rec in enumerate(all_records):
            if is_restore:
                # retore the record by removing the column of ids and assigning the previous id value
                db_record = DbRecord(rec[1:])
                db_record.id = rec[0]

            else:
                # editor just opened so set records provided by backend
                db_record = DbRecord(rec, taken_ids=self.__all_record_ids)
                self.__all_record_ids.append(db_record.id)

            self.__record_cache.insert(row_index, db_record)
            self.__map_recid_to_rowidx[db_record.id] = row_index

        self.__rows = len(all_records)
        self.sig_rows_changed.emit(self.__rows)

    def __regenerate_recid_map(self):
        """
        Used to regenerate the record ID to row index map after changes are made to the unfiltered record cache.
        """
        self.__map_recid_to_rowidx = {}
        for row_index, rec in enumerate(self.__record_cache):
            self.__map_recid_to_rowidx[rec.id] = row_index

    def __on_init_filtered_table_records(self, filtered_records: DbRawRecords):
        """
        Populate the filtered table data cache. If this is called as a result of an update, the caller must call
        beginModelReset() first, and call endModelReset() after.
        :param filtered_records: the filtered records delivered from the back-end Table Part
        """
        # Make records editable/mutable by changing from tuple to list
        self.__record_cache_filtered = []
        self.__ids_filtered_recs_removed = []
        for row_index, rec in enumerate(filtered_records):
            # need to strip out the first column of IDs added during filtering
            db_record = DbRecord(rec[1:], is_filtered=True)
            db_record.id = rec[0]  # reset the id with the one previously generated
            self.__record_cache_filtered.insert(row_index, db_record)

        self.__rows = len(filtered_records)
        self.sig_rows_changed.emit(self.__rows)

    def __set_filtered_records(self, filtered_records: DbRawRecords):
        """
        Set the table records with the given filtered list.
        :param filtered_records: A list of filtered records to set into the model.
        """
        self.beginResetModel()
        self.__on_init_filtered_table_records(filtered_records)
        self.sig_filter_changed.emit(True)
        self.endResetModel()

    def __restore_unfiltered_records(self, records: DbRawRecords):
        """
        Called to restore the set of unfiltered table records with the given list.
        :param records: A list of records to set into the model.
        """
        self.beginResetModel()

        # remove all filtered records
        del self.__record_cache_filtered
        self.__record_cache_filtered = []

        # initialize the unfiltered records
        self.__on_init_table_records(records, is_restore=True)
        self.sig_filter_changed.emit(False)
        self.endResetModel()

    def __get_unique_column_name(self, col_idx: int) -> str:
        """
        Searches until a unique column name is generated.
        :param col_idx: The column index to generate a name for.
        :return: A unique column name.
        """
        set_name = str()
        name_in_cache = True
        inc = 0
        # Search until a unique name is generated
        while name_in_cache:
            set_name = 'Col {}'.format(repr(col_idx + inc))
            if set_name in self.__col_name_cache:
                # Name already in use, try next increment
                inc += 1
            else:
                # Found a unique name, exit loop
                name_in_cache = False

        return set_name

    def __augment_indexed_columns(self, cols_to_remove: List[str]):
        """
        Remove the column indices associated with any columns to be removed.
        :param cols_to_remove: a list of removed column names.
        """
        ctr = [col.rstrip('*') for col in cols_to_remove]
        orig_col_indices = self.__col_indexes
        self.__col_indexes = []
        for col_index in orig_col_indices:
            # update index by removing deleted columns
            new_col_index = tuple([keep_col for keep_col in col_index if keep_col not in ctr])
            if new_col_index and new_col_index not in self.__col_indexes:
                self.__col_indexes.append(new_col_index)

    def __create_empty_row(self, is_filtered: bool = False) -> DbRecord:
        """
        Generates an empty row filled with data corresponding to the column data type, if set.
        :param is_filtered: flag indicates if empty row is being created while a filter is applied.
        :return: a row (list) of empty data.
        """
        rec = DbRecord(taken_ids=self.__all_record_ids, is_filtered=is_filtered)
        if rec.id is not None:
            self.__all_record_ids.append(rec.id)

        for col, col_type in enumerate(self.__col_types):
            if col_type == SqliteDataTypesEnum.DATETIME:
                rec.insert(col, datetime.now().strftime(SQLITE_DATETIME_FORMAT))
            elif col_type == SqliteDataTypesEnum.INTEGER:
                rec.insert(col, 0)
            elif col_type in REAL_TYPES:
                rec.insert(col, 0.0)
            else:  # TEXT
                rec.insert(col, '')

        return rec

    def __data_type(self, value: TableCellData, col_index: int) -> TableCellData:
        """
        Converts the data entered into a table cell based on the column type.
        :param value: the information entered into a cell of the table part.
        :param col_index: the index of the column corresponding to value.
        :return: the value formatted to it's type.
        """
        col_type = self.__col_types[col_index]

        try:
            if col_type == SqliteDataTypesEnum.DATETIME:
                time_obj = datetime.strptime(str(value), SQLITE_DATETIME_FORMAT)  # convert value to a datetime object
                value = time_obj.strftime(SQLITE_DATETIME_FORMAT)  # convert time object to formatted time string
            elif col_type == SqliteDataTypesEnum.INTEGER:
                value = int(value)
            elif col_type in REAL_TYPES:
                value = float(value)
            else:  # TEXT
                value = str(value)

        except ValueError:
            self.__open_column_type_warning_dialog(col_type, self.__col_name_cache[col_index])

        return value

    def __set_column_type(self, col_index: int, col_type: str):
        """
        Sets the column type and hence the type of data that can be entered into the column.

        Column types can be set to TEXT, INTEGER, or REAL_TYPES (Access/SQL types) which correspond to Python's str,
        int, or float types.

        If data from one column is pasted into another of a different data type, that data will be
        converted to the column's data type. In the case where the data cannot be converted, it is pasted anyways, but a
        dialog will pop-up informing the user of the discrepancy and highlight the offending cells in red. These cells
        can then be manually changed. Once, changed, if the new value matches the columns type, the red highlight will
        be removed, otherwise, it will remain and the same dialog will be invoked again.

        It is important to note that, even with data entered into columns with a different type, the table will continue
        to function, allowing data entry and editing options to be employed. However, the table export will mostly
        likely fail with a message indicating a column type mismatch.

        :param col_index: the index of the column 'value' was entered into.
        :param col_type: the new column type to set.
        """
        self.__col_types[col_index] = SqliteDataTypesEnum[col_type]
        self.__set_data_to_column_type(col_index)

    def __set_data_to_column_type(self, col_index: int):
        """
        Converts data in a given column to the type associated with the column.
        :param col_index: the index of the column.
        """
        col_type = self.__col_types[col_index]

        if col_type == SqliteDataTypesEnum.DATETIME:
            all_cells_filled = self.__convert_column_cells(datetime.strptime,
                                                           datetime.now().strftime(SQLITE_DATETIME_FORMAT), col_index)
        elif col_type == SqliteDataTypesEnum.INTEGER:
            all_cells_filled = self.__convert_column_cells(int, 0, col_index)
        elif col_type in REAL_TYPES:
            all_cells_filled = self.__convert_column_cells(float, 0.0, col_index)
        else:  # TEXT
            all_cells_filled = self.__convert_column_cells(str, '', col_index)

        if not all_cells_filled:
            self.__open_column_type_warning_dialog(col_type, self.__col_name_cache[col_index])

    def __convert_column_cells(self, convert: classmethod, zero: TableCellData, col_index: int) -> bool:
        """
        Converts the cells of the column to the new column type.
        :param convert: a method to convert non-empty cells to the new column type.
        :param zero: an int(0) or float(0.0) or empty str or datetime.now() to insert into empty cells.
        :param col_index: the index of the affected column.
        :return a flag that indicates if all items were converted or not.
        """
        all_cells_filled = True
        col_type = self.__col_types[col_index]
        for cache in (self.__record_cache, self.__record_cache_filtered):
            for rec in cache:
                if rec[col_index] in (str(), 0, 0.0):
                    # insert a placeholder value into empty cells
                    rec[col_index] = zero
                else:
                    # cell not empty, try to convert
                    try:
                        if col_type == SqliteDataTypesEnum.DATETIME:
                            # convert value to a datetime object -> then to a formatted time string
                            rec[col_index] = convert(str(rec[col_index]),
                                                     SQLITE_DATETIME_FORMAT).strftime(SQLITE_DATETIME_FORMAT)
                        else:
                            rec[col_index] = convert(rec[col_index])
                    except ValueError:
                        # some or all contents could not be converted
                        all_cells_filled = False

        return all_cells_filled

    def __map_python_types_to_sql_type(self, record_item: Any) -> SqliteDataTypesEnum:
        """
        Maps python types (str, int, float, datetime) to column types (TEXT, INTEGER, REAL_TYPES, DATETIME).
        :param record_item: the item whose type is being deterined.
        :return: the column type.
        """
        python_type = type(record_item)

        if python_type == str:
            # could be either TEXT or DATETIME
            try:
                # attempt to convert to datetime, if success, it's datetime
                time_obj = datetime.strptime(record_item, SQLITE_DATETIME_FORMAT)
                return SqliteDataTypesEnum.DATETIME
            except ValueError:
                # ...must be TEXT
                return SqliteDataTypesEnum.TEXT
        elif python_type == int:
            return SqliteDataTypesEnum.INTEGER
        elif python_type == float:
            return SqliteDataTypesEnum.REAL
        else:
            return SqliteDataTypesEnum.TEXT  # catch all

    def __validate_data_matches_col_type(self, row_index: int, col_index: int) -> Optional[Any]:
        """
        Validate that the type of data in the table at the given indices matches the column type.
        :param row_index: the row index of the data under inspection.
        :param col_index: the column index of the data under inspection.
        :return: a red brush to color the column if data type and column type don't match, and None otherwise.
        """
        # get the expected SQL type that matches the data
        try:
            if self.__filter:
                record_item = self.__record_cache_filtered[row_index][col_index]
            else:
                record_item = self.__record_cache[row_index][col_index]

            expected_sql_type = self.__map_python_types_to_sql_type(record_item)

        except IndexError:
            # cache has not yet been populated
            expected_sql_type = SqliteDataTypesEnum.TEXT  # assign a default

        # REAL or DOUBLE or FLOAT are all valid. Here, replace with REAL
        if expected_sql_type == SqliteDataTypesEnum.REAL and self.__col_types[col_index] in REAL_TYPES:
            self.__col_types[col_index] = SqliteDataTypesEnum.REAL

        # for the case where the expected type is DATETIME and the column type is TEXT, do not highlight the column:
        # this is becuase, the mapping to expected SQL type assumes if an object can be converted to datetime then
        # its column type must be DATETIME, however, it is possible a user may want to have text objects that satisfy
        # the SQLITE_DATETIME_FORMAT remain as text and not be converted to datetime
        if (expected_sql_type == SqliteDataTypesEnum.DATETIME and
                    self.__col_types[col_index] == SqliteDataTypesEnum.TEXT):
            return None

        # validate that the type of data in the column matches the column type
        if expected_sql_type != self.__col_types[col_index]:
            return QBrush(Qt.red)

        return None

    def __open_column_type_warning_dialog(self, col_type: str, col_name: str):
        """
        Opens a dialog to inform the user that some values entered could not be changed to the type associated with
        this column.
        :param col_type: the type associated of the column.
        :param col_name: the name of the column.
        """
        msg = 'The value(s) entered does not match the {} type of column {}. ' \
              'The table cells with incorrect type are highlighted in red.'.format(col_type, col_name)
        exec_modal_dialog('Data Type Error', msg, QMessageBox.Critical)

    def __get_displayed_col_name(self, col_name: str) -> str:
        """
        Returns the column name to display including any decorators or markers to show.
        :param col_name: The name to decorate.
        :return: The column name to display.
        """
        # check if this column is indexed
        for col_index in self.__col_indexes:
            if col_name in col_index:
                # break at first index found with this col name
                col_name += '*'
                break

        return col_name

    def __create_column_label(self, col_name: str, col_type: SqliteDataTypesEnum) -> str:
        """
        Combine the column parameters into a single column label.
        :param col_name: The column name.
        :param col_type: The column data type.
        :return: The column label.
        """
        return col_name + ' (' + col_type.name + ')'

    def __parse_column_label(self, label: str) -> Tuple[str, str]:
        """
        Return the column name and column type as separate strings.
        :param label: The column label to separate.
        :return: A column name and type.
        """
        current_name, col_type = label.split(sep='(')
        current_name = current_name.strip()
        return current_name.strip('*'), col_type.strip(')')


class TablePartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # No sort contant is set rather than using DisplayOrderEnum in order to work with Qt's SortOrder class where
    # 0 == AscendingOrder and 1 == DescendingOrder
    NO_SORT = -1

    # The initial size to make this editor look nice.
    INIT_WIDTH = 400
    INIT_HEIGHT = 600

    ZERO_IDX = 0

    def __init__(self, part: TablePart, parent: QWidget = None):
        """
        Initializes this panel with a back end Table Part and a parent QWidget.

        :param part: The Table Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_TablePartEditor()
        self.ui.setupUi(self)
        self.__table_part = part
        self.ui.table_view.setFont(get_scenario_font())

        self.__import_dialog = None
        self.__export_dialog = None
        self.__index_dialog = None
        self.__filter_dialog = None
        self.__last_db_import_path = None
        self.__last_db_export_path = None
        self.__last_db_import_filter = None

        self.__item_selected = None
        self.__is_row_selected = False
        self.__is_col_selected = False
        self.__is_general_selection = False
        self.__selected_rows = []
        self.__selected_cols = []
        self.__general_selection = []
        self.__sorted_column = [self.ZERO_IDX]
        self.__sort_order = TablePartEditorPanel.NO_SORT
        self.__paste_type = None

        # Proxy models for sorting
        self.__proxy_model = None
        self.__selection_proxy_model = None

        # Set table model and initialize sort, proxy, and selection models
        self.__table_model = TablePartTableModelForEditing(part, parent)
        self.__selection_model = QItemSelectionModel(self.__table_model)
        self.__table_model.modelReset.connect(self.__slot_init_model_sort_order)
        self.ui.table_view.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.__table_model.sig_rows_changed.connect(self.__slot_on_row_number_changed_by_model)
        self.__table_model.sig_cols_changed.connect(self.__slot_on_column_number_changed_by_model)
        self.__table_model.sig_filter_changed.connect(self.__slot_on_filter_changed_by_model)

        # Set table header options and slots
        horizontal_header = QHeaderView(Qt.Horizontal)
        horizontal_header.setSectionsClickable(True)
        horizontal_header.setSectionsMovable(True)
        horizontal_header.setSectionResizeMode(QHeaderView.Interactive)
        self.ui.table_view.setHorizontalHeader(horizontal_header)
        horizontal_header.sectionMoved.connect(self.__slot_on_column_moved)
        horizontal_header.sectionDoubleClicked.connect(self.__slot_on_change_column_properties)
        horizontal_header.sectionPressed.connect(self.__slot_on_column_header_clicked)

        vertical_header = QHeaderView(Qt.Vertical)
        vertical_header.setSectionsClickable(True)
        vertical_header.setSectionResizeMode(QHeaderView.Interactive)
        self.ui.table_view.setVerticalHeader(vertical_header)
        vertical_header.sectionClicked.connect(self.__slot_on_row_header_clicked)

        # Set button icons
        self.ui.insert_before_button.setIcon(QIcon(str(get_icon_path("insert_before.png"))))
        self.ui.insert_after_button.setIcon(QIcon(str(get_icon_path("insert_after.png"))))
        self.ui.select_all_button.setIcon(QIcon(str(get_icon_path("select_all.png"))))
        self.ui.cut_button.setIcon(QIcon(str(get_icon_path("cut.png"))))
        self.ui.copy_button.setIcon(QIcon(str(get_icon_path("copy.png"))))
        self.ui.paste_button.setIcon(QIcon(str(get_icon_path("paste.png"))))
        self.ui.del_button.setIcon(QIcon(str(get_icon_path("delete.png"))))
        self.ui.sort_button.setIcon(QIcon(str(get_icon_path("sort.png"))))
        self.ui.filter_button.setIcon(QIcon(str(get_icon_path("filter.png"))))
        self.ui.filter_refresh_button.setIcon(QIcon(str(get_icon_path("filter_refresh.png"))))
        self.ui.import_db_button.setIcon(QIcon(str(get_icon_path("import.png"))))
        self.ui.export_db_button.setIcon(QIcon(str(get_icon_path("export.png"))))
        self.ui.index_button.setIcon(QIcon(str(get_icon_path("index.png"))))

        # Disabled buttons
        self.__toggle_enabled_edit_buttons(False, enable_insert=True)
        self.ui.sort_button.setEnabled(False)
        self.ui.filter_refresh_button.setEnabled(False)

        # Connect button slots
        self.ui.insert_before_button.clicked.connect(self.__slot_insert_before)
        self.ui.insert_after_button.clicked.connect(self.__slot_insert_after)
        self.ui.select_all_button.clicked.connect(self.__slot_select_all)
        self.ui.cut_button.clicked.connect(self.__slot_cut)
        self.ui.copy_button.clicked.connect(self.__slot_copy)
        self.ui.paste_button.clicked.connect(self.__slot_paste)
        self.ui.del_button.clicked.connect(self.__slot_delete)
        self.ui.sort_button.clicked.connect(self.__slot_toggle_sort)
        self.ui.filter_button.clicked.connect(self.__slot_set_column_filter)
        self.ui.filter_refresh_button.clicked.connect(self.__slot_refresh_column_filter)
        self.ui.import_db_button.clicked.connect(self.__slot_import_database)
        self.ui.export_db_button.clicked.connect(self.__slot_export_database)
        self.ui.index_button.clicked.connect(self.__slot_set_column_indexes)
        self.ui.change_row_count_spin_box.editingFinished.connect(self.__slot_on_row_spinbox_edit)
        self.ui.change_column_count_spin_box.editingFinished.connect(self.__slot_on_column_spinbox_edit)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.insert_before_button,
                     self.ui.insert_after_button,
                     self.ui.select_all_button,
                     self.ui.cut_button,
                     self.ui.copy_button,
                     self.ui.paste_button,
                     self.ui.del_button,
                     self.ui.sort_button,
                     self.ui.filter_button,
                     self.ui.import_db_button,
                     self.ui.export_db_button,
                     self.ui.index_button,
                     self.ui.change_row_count_spin_box,
                     self.ui.change_column_count_spin_box]
        return tab_order

    def set_indexed_columns(self, column_indexes: List[Tuple[str]]):
        """
        Sets the table indexes to be passed to the back-end when table editing is complete.
        :param column_indexes: a list of tuples where each index is a tuple of columns to index.
        """
        self.__table_model.indexed_columns = column_indexes

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Gets the GUI table data for submission to the back-end when changes in the editor have been completed.
        :returns: The data for submission
        """
        # Store for the next time the editor opens
        self.__table_model.display_order = self.__sort_order + 1
        self.__table_model.sorted_column = self.__sorted_column

        data_dict = dict()
        self.__table_model.fill_data_for_submission(data_dict)
        return deepcopy(data_dict)

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        self.__table_model.init_model(data)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __toggle_enabled_edit_buttons(self, enable: bool = True, enable_insert: bool = True):
        """
        Enables or disables the edit buttons on the table widget.
        :param enable: True to enable, False to disable. Flag for all edit buttons but 'insert'.
        :param enable_insert: True to enable, False to disable. Flag for 'insert' edit buttons.
        """
        self.ui.insert_before_button.setEnabled(enable_insert)
        self.ui.insert_after_button.setEnabled(enable_insert)
        self.ui.cut_button.setEnabled(enable)
        self.ui.copy_button.setEnabled(enable)
        self.ui.paste_button.setEnabled(enable)
        self.ui.del_button.setEnabled(enable)

    def __toggle_enabled_database_buttons(self):
        """
        Enables or disables the database option buttons depending on the current row or column number.
        """
        rows = self.__table_model.rows
        columns = self.__table_model.cols

        # Filter and export
        if rows > 0 and columns > 0:
            self.ui.export_db_button.setEnabled(True)
        else:
            self.ui.export_db_button.setEnabled(False)

        # Index
        if columns > 0:
            self.ui.index_button.setEnabled(True)
        else:
            self.ui.index_button.setEnabled(False)

    def __on_item_changed(self, current_item: QModelIndex, unused: QModelIndex):
        """
        Triggered when the selected item in the table changes.
        :param current_item: the model index of the selected item.
        :param unused: the model index of the deselected item (not used).
        """
        del unused
        self.__item_selected = current_item

    def __on_selection_changed(self, unused1: QItemSelection, unused2: QItemSelection):
        """
        Triggered when the selection in the table changes.
        :param unused1: a selection object that contains a list of selected model indexes that have changed.
        :param unused2: a selection object that contains a list of deselected model indexes (not used).
        """
        del unused1
        del unused2

        self.__selected_rows = []
        self.__selected_cols = []
        self.__general_selection = []
        self.__is_row_selected = False
        self.__is_col_selected = False
        self.__is_general_selection = False

        selection_range = self.__find_selection_range()
        if selection_range is not None:
            top_row, bottom_row, left_col, right_col = selection_range
        self.__toggle_enabled_edit_buttons()

        # If whole rows or columns are selected, act on those;
        # otherwise, act on the general selection of highlight cells if one has been made
        if len(self.__selected_rows) == 1 and len(self.__selected_cols) > 0:
            # Row selection: case where whole row is selected in a table with one row (so all columns are selected too)
            self.__is_row_selected = True
        elif len(self.__selected_rows) > 0 and len(self.__selected_cols) == 0:
            # Row selection: case where multiple rows are selected in a table with more than one row
            self.__is_row_selected = True
        elif len(self.__selected_cols) == 1 and len(self.__selected_rows) > 0:
            # Column selection: case where whole column is selected in a table with one column (so all rows are
            # selected too)
            self.__is_col_selected = True
            self.__sorted_column = [self.__selected_cols[0]]
        elif len(self.__selected_cols) > 0 and len(self.__selected_rows) == 0:
            # Column selection: case where multiple columns are selected in a table with more than one column
            self.__is_col_selected = True
            self.__sorted_column = [self.__selected_cols[0]]
        else:
            # No complete row or column selected -> check for valid general selection in next code block
            pass

        # Check for any general selection: full or partial row or column selections
        if self.__selection_model.hasSelection() and selection_range is not None:
            # General selection
            self.__general_selection = [[top_row, left_col], [bottom_row, right_col]]
            self.__is_general_selection = True
        else:
            # No valid selection
            if self.__table_model.rows == 0:
                self.__toggle_enabled_edit_buttons(False, enable_insert=True)
            else:
                self.__toggle_enabled_edit_buttons(False, enable_insert=False)

        # Enable or disable the sort button
        if self.__is_col_selected or self.ui.table_view.isSortingEnabled():
            self.ui.sort_button.setEnabled(True)
        else:
            self.ui.sort_button.setEnabled(False)

    def __find_selection_range(self) -> Optional[List[int]]:
        """
        Finds the top, bottom, left, and right indexes of the selection and determines if whole rows or columns are
        selected.
        :return: a list of indexes that define the selected range.
        """
        # Temporary values
        top_row = None
        left_col = None
        bottom_row = None
        right_col = None
        loop_count = 0

        if self.ui.table_view.isSortingEnabled():
            selection_model_in_effect = self.__selection_proxy_model
        else:
            selection_model_in_effect = self.__selection_model

        # Find the top-left and bottom-right of the selection
        # Also determine if a complete row or column is selected
        for index in selection_model_in_effect.selectedIndexes():
            row = index.row()
            col = index.column()
            parent = index.parent()

            if loop_count == 0:
                top_row = row
                bottom_row = row
                left_col = col
                right_col = col
                loop_count += 1

            else:
                if row < top_row:
                    top_row = row
                elif row > bottom_row:
                    bottom_row = row

                if col < left_col:
                    left_col = col
                elif col > right_col:
                    right_col = col

            # Check for complete row selection
            if selection_model_in_effect.isRowSelected(row, parent):

                # Map row selection to sorted model if sorting enabled
                if self.ui.table_view.isSortingEnabled():
                    row = self.__map_rows_to_sorted_model([row])[self.ZERO_IDX]

                if row not in self.__selected_rows:
                    self.__selected_rows.append(row)

            # Check for complete column selection
            if selection_model_in_effect.isColumnSelected(col, parent):
                if col not in self.__selected_cols:
                    self.__selected_cols.append(col)

        # If sorted reverse-alphabetical, reverse order of selection so table model operations work correctly
        if self.__sort_order == Qt.DescendingOrder:
            self.__selected_rows.reverse()

        # General selection -> no need to go further if these are None
        if top_row is None or bottom_row is None:
            return None

        # Map general selection to sorted model if sorting enabled
        if self.ui.table_view.isSortingEnabled():
            rows = [top_row, bottom_row]
            rows = self.__map_rows_to_sorted_model(rows)

            # If sorted reverse-alphabetical, reverse order of selection so table model operations work correctly
            if self.__sort_order == Qt.DescendingOrder:
                rows.reverse()

            top_row, bottom_row = rows

        return [top_row, bottom_row, left_col, right_col]

    def __insert_before(self):
        """
        Inserts a row or column before the selected row or column.
        """
        shift_selection = True
        if not self.__is_row_selected and not self.__is_col_selected:
            # Insert rows if no row or column is selected. This was implemented primarily for new tables
            # to simplify adding an initial set of rows.
            self.__table_model.insert_rows([self.ZERO_IDX], InsertBeforeOrAfterEnum.after, insert_after_selection=False)
            self.__selected_rows = [self.ZERO_IDX]
            shift_selection = False

        elif self.__is_row_selected:
            # Insert the row before the selected row and update the selection
            self.__table_model.insert_rows(self.__selected_rows, InsertBeforeOrAfterEnum.before)
            moved_index = self.__table_model.index(self.__selected_rows[self.ZERO_IDX] + 1, self.ZERO_IDX)
            orig_index = self.__table_model.index(self.__selected_rows[self.ZERO_IDX], self.ZERO_IDX)

        elif self.__is_col_selected:
            # Insert the column before the selected column and update the selection
            self.__table_model.insert_columns(self.__selected_cols, InsertBeforeOrAfterEnum.before)
            moved_index = self.__table_model.index(self.ZERO_IDX, self.__selected_cols[self.ZERO_IDX] + 1)
            orig_index = self.__table_model.index(self.ZERO_IDX, self.__selected_cols[self.ZERO_IDX])

        else:
            # Either both a row and a column are selected (a block or rows and columns) or neither are selected. In the
            # former case, insert before cannot determine what to insert (row or column?) before the block of selected
            # rows and columns. In the latter case, insert before is not valid since no row or column is selected.
            shift_selection = False

        if shift_selection:
            self.__selection_model.currentChanged.emit(moved_index, orig_index)
            self.__selection_model.selectionChanged.emit(self.__selection_model.selection(),
                                                         self.__selection_model.selection())

    def __insert_after(self):
        """
        Inserts a row or column after the selected row or column.
        """
        shift_selection = True
        if not self.__is_row_selected and not self.__is_col_selected:
            # Insert rows if no row or column is selected. This was implemented primarily for new tables
            # to simplify adding an initial set of rows.
            self.__table_model.insert_rows([self.ZERO_IDX],
                                           InsertBeforeOrAfterEnum.after,
                                           insert_after_selection=False)
            self.__selected_rows = [self.ZERO_IDX]
            shift_selection = False

        elif self.__is_row_selected:
            # Insert the row after the selected row and update the selection
            self.__table_model.insert_rows(self.__selected_rows, InsertBeforeOrAfterEnum.after)
            moved_index = self.__table_model.index(self.__selected_rows[self.ZERO_IDX], self.ZERO_IDX)
            orig_index = self.__table_model.index(self.__selected_rows[self.ZERO_IDX], self.ZERO_IDX)

        elif self.__is_col_selected:
            # Insert the column after the selected column and update the selection
            self.__table_model.insert_columns(self.__selected_cols, InsertBeforeOrAfterEnum.after)
            moved_index = self.__table_model.index(self.ZERO_IDX, self.__selected_cols[self.ZERO_IDX])
            orig_index = self.__table_model.index(self.ZERO_IDX, self.__selected_cols[self.ZERO_IDX])

        else:
            # Either both a row and a column are selected (a block or rows and columns) or neither are selected. In the
            # former case, insert after cannot determine what to insert (row or column?) after the block of selected
            # rows and columns. In the latter case, insert after is not valid since no row or column is selected.
            shift_selection = False

        if shift_selection:
            self.__selection_model.currentChanged.emit(moved_index, orig_index)
            self.__selection_model.selectionChanged.emit(self.__selection_model.selection(),
                                                         self.__selection_model.selection())

    def __select_all(self):
        """
        Selects all rows, if any.
        """
        self.ui.table_view.selectAll()

    def __cut(self):
        """
        Cuts the selected row(s). If nothing is selected, this function does nothing.
        """
        if self.__is_row_selected:
            self.__table_model.cut_rows(self.__selected_rows[self.ZERO_IDX], len(self.__selected_rows))
            self.__paste_type = PasteTypeEnum.row_from_cut

        elif self.__is_col_selected:
            self.__table_model.cut_columns(self.__selected_cols[self.ZERO_IDX], len(self.__selected_cols))
            self.__paste_type = PasteTypeEnum.col_from_cut

        elif self.__is_general_selection:
            self.__table_model.cut_cells(self.__general_selection)
            self.__paste_type = PasteTypeEnum.cell_from_cut

        else:
            pass  # undefined selection type

    def __copy(self):
        """
        Copies the selected row(s) or column(s). If nothing is selected, this function does nothing.
        """
        if self.__is_general_selection:
            self.__table_model.copy_cells(self.__general_selection)
            self.__paste_type = PasteTypeEnum.any_from_copy
        else:
            pass  # undefined selection type

    def __paste(self):
        """
        Pastes the previously copied or cut data. A "general selection" is used to define the paste position for each
        case regardless of row, column, or general shape of contents to paste since user can click a single cell to
        paste a row, column, or general selection.
        """
        shift_selection = True

        # general selection cell indices
        top_left = 0
        bottom_right = 1
        top_row = 0
        left_col = 1
        bottom_row = 0
        right_col = 1

        if self.__paste_type in (PasteTypeEnum.any_from_copy, PasteTypeEnum.cell_from_cut):
            # Use paste_cells for any copy operation (row, column, general cell selection) and for cuts on cells
            self.__table_model.paste_cells(self.__general_selection)
            shift_selection = False

        elif self.__paste_type == PasteTypeEnum.row_from_cut:
            first_row = self.__general_selection[top_left][top_row]
            last_row = self.__general_selection[bottom_right][bottom_row]
            selected_rows = [row for row in range(first_row, last_row + 1)]
            self.__table_model.paste_rows(selected_rows)
            moved_index = self.__table_model.index(self.__selected_rows[self.ZERO_IDX], self.ZERO_IDX)
            orig_index = self.__table_model.index(self.__selected_rows[self.ZERO_IDX], self.ZERO_IDX)

        elif self.__paste_type == PasteTypeEnum.col_from_cut:
            first_col = self.__general_selection[top_left][left_col]
            last_col = self.__general_selection[bottom_right][right_col]
            selected_cols = [col for col in range(first_col, last_col + 1)]
            self.__table_model.paste_columns(selected_cols)
            moved_index = self.__table_model.index(self.ZERO_IDX, self.__selected_cols[self.ZERO_IDX])
            orig_index = self.__table_model.index(self.ZERO_IDX, self.__selected_cols[self.ZERO_IDX])

        else:
            shift_selection = False  # not a valid selection to paste

        if shift_selection:
            self.__selection_model.currentChanged.emit(moved_index, orig_index)
            self.__selection_model.selectionChanged.emit(self.__selection_model.selection(),
                                                         self.__selection_model.selection())

    def __delete(self):
        """
        Deletes the selected row(s) or column(s). If nothing is selected, this function does nothing.
        """
        if self.__is_row_selected:
            self.__table_model.remove_rows(self.__selected_rows[self.ZERO_IDX], len(self.__selected_rows))
        elif self.__is_col_selected and len(self.__selected_cols) < self.__table_model.cols:
            self.__table_model.remove_columns(self.__selected_cols[self.ZERO_IDX], len(self.__selected_cols))
        elif self.__is_col_selected and (self.__table_model.cols == 1 or
                                                 len(self.__selected_cols) == self.__table_model.cols):
            # The only column or all columns were selected for deletion
            self.__delete_entire_table()
        elif self.__is_general_selection:
            if self.__table_model.cols == 1 or len(self.__selected_cols) == self.__table_model.cols:
                # Select All was clicked before delete
                self.__delete_entire_table()
            else:
                self.__table_model.update_cells(self.__general_selection)

    def __delete_entire_table(self):
        """
        Deletes all rows and columns from the table and resets the default column.
        """
        self.__table_model.remove_columns(self.ZERO_IDX, self.__table_model.cols)
        self.__table_model.remove_rows(self.ZERO_IDX, self.__table_model.rows)

        # Restore default column
        self.__is_col_selected = True
        self.__selected_cols = [self.ZERO_IDX]
        self.__insert_before()

    def __on_column_header_clicked(self, _: int):
        """
        Set the column selected flag to true.
        """
        if self.__table_model.rows == 0:
            # Can't sort if no rows
            return

        self.__is_col_selected = True
        self.__is_row_selected = False
        if self.__selected_cols:
            # set sorted column only if col selected when header clicked
            self.__sorted_column = [self.__selected_cols[self.ZERO_IDX]]

    def __on_row_header_clicked(self, row_index: int):
        """
        Set the row selected flag to true
        :param row_index:
        :return:
        """
        self.__is_row_selected = True
        self.__is_col_selected = False

    def __on_change_column_properties(self, col_index: int):
        """
        Launches the field name update dialog when the column is double-clicked.
        :param col_index: the index of the column to update.
        """
        col_name, col_type = self.__table_model.get_column_properties(col_index)
        col_param_editor = TableColumnParamEditorDialog(col_name, col_type, self.__table_part)
        answer = col_param_editor.exec()
        if answer:
            new_name, new_type = col_param_editor.get_user_input()
            self.__table_model.update_column_properties(col_index, new_name, new_type)

    def __on_column_moved(self, _: int, init_index: int, dest_index: int):
        """
        Moves the column from its initial location to the selected location.
        :param init_index: the initial index of the moved column.
        :param dest_index: the destination index of the moved column.
        """
        self.__table_model.move_column(init_index, dest_index)

    def __on_row_number_changed_by_model(self, new_number_of_rows: int):
        """
        Changes the value in the row setting spin-box to the number of current rows in the table editor.
        :param new_number_of_rows: the changed number of rows.
        """
        self.ui.change_row_count_spin_box.setValue(new_number_of_rows)
        self.__toggle_enabled_database_buttons()

    def __on_column_number_changed_by_model(self, new_number_of_cols: int):
        """
        Changes the value in the column setting spin-box to the number of current columns in the table editor.
        :param new_number_of_cols: the changed number of columns.
        """
        self.ui.change_column_count_spin_box.setValue(new_number_of_cols)
        self.__toggle_enabled_database_buttons()

    def __on_row_spinbox_edit(self, new_number_of_rows: int = None):
        """
        Updates the number of rows in the table when the user edits the spinbox value by typing.
        This method is connected to the spinbox's editingFinished signal that updates the model only when the spinbox
        loses focus or enter is pressed.
        :param new_number_of_rows: The number of rows typed or incremented into the spinbox.
        """
        if new_number_of_rows is None:
            new_number_of_rows = self.ui.change_row_count_spin_box.value()

        current_number_of_rows = self.__table_model.rows

        if new_number_of_rows < current_number_of_rows:
            num_to_remove = current_number_of_rows - new_number_of_rows
            start_index = current_number_of_rows - num_to_remove
            self.__table_model.remove_rows(start_index, num_to_remove)

        elif new_number_of_rows > current_number_of_rows:
            # Add a column before adding a row if there are none
            if self.__table_model.cols == 0:
                self.__on_column_number_update(1)

            num_to_add = new_number_of_rows - current_number_of_rows
            start_index = current_number_of_rows
            row_insert_indexes = []
            for index in range(start_index, start_index + num_to_add):
                row_insert_indexes.append(index)

            self.__table_model.insert_rows(row_insert_indexes, InsertBeforeOrAfterEnum.after,
                                           insert_after_selection=False)

    def __on_column_spinbox_edit(self, new_number_of_columns: int = None):
        """
        Updates the number of columns in the table when the user edits the spinbox value by typing.
        This method is connected to the spinbox's editingFinished signal that updates the model only when the spinbox
        loses focus or enter is pressed.
        :param new_number_of_columns: The number of columns typed or incremented into the spinbox.
        """
        if new_number_of_columns is None:
            new_number_of_columns = self.ui.change_column_count_spin_box.value()

        current_number_of_cols = self.__table_model.cols

        if new_number_of_columns < current_number_of_cols:
            num_to_remove = current_number_of_cols - new_number_of_columns
            start_index = current_number_of_cols - num_to_remove
            self.__table_model.remove_columns(start_index, num_to_remove)

        elif new_number_of_columns > current_number_of_cols:
            num_to_add = new_number_of_columns - current_number_of_cols
            start_index = current_number_of_cols
            col_insert_indexes = []
            for index in range(start_index, start_index + num_to_add):
                col_insert_indexes.append(index)

            self.__table_model.insert_columns(col_insert_indexes, InsertBeforeOrAfterEnum.after,
                                              insert_after_selection=False)

    def __on_filter_changed_by_model(self, filter_applied: bool):
        """
        Respond to filter changes from the table model.
        :param filter_applied: True if filter applied, and False otherwise.
        """
        tab_index = 1
        tab_label = 'Database'
        tab_bar = self.ui.tool_ribbon.tabBar()
        enabled = False

        # self.ui.tool_ribbon.setStyleSheet('')
        tab_bar.setTabTextColor(tab_index, Qt.black)

        if filter_applied:
            # self.ui.tool_ribbon.setStyleSheet('QTabBar{font: bold;}')
            tab_bar.setTabTextColor(tab_index, Qt.red)
            tab_label += ' (filtered)'
            enabled = True

        self.ui.tool_ribbon.setTabText(tab_index, tab_label)
        self.ui.filter_refresh_button.setEnabled(enabled)

    def __launch_filter_dialog(self):
        """
        Launches the table filter dialog to filter the table columns.
        Note: the filter is applied to the table widget contents, not the table editor contents.
        """
        self.__filter_dialog = FilterColumnDialog(self.__table_part, self.__table_model, table_editor=self)
        answer = self.__filter_dialog.exec()
        if answer:
            self.__table_model.filter = self.__filter_dialog.get_user_input()

    def __refresh_column_filter(self):
        """
        Re-apply the filter to the table data.
        """
        self.__table_model.set_filter(self.__table_model.filter, is_refresh=True)

    def __launch_import_dialog(self):
        """
        Launches the table import dialog to import data from an access database.
        """
        if self.__table_model.filter:
            # if there is a 'backend filter' use it
            filter_in_use = self.__table_model.filter
        else:
            # else, use the filter defined in the import dialog, if any
            filter_in_use = self.__last_db_import_filter

        self.__import_dialog = ImportDatabaseDialog(self.__table_part,
                                                    last_db_import_path=self.__last_db_import_path,
                                                    db_filter=filter_in_use,
                                                    table_editor=self)

        import_in_progress = True
        while import_in_progress:
            answer = self.__import_dialog.exec()
            if answer:
                db_path, db_table, db_selected_fields, db_filter = self.__import_dialog.get_user_input()
                success = self.__process_sql_import(db_path, db_table, db_selected_fields, db_filter)
                import_in_progress = not success  # stay 'in progress' if import not successful
            else:
                # cancelled
                import_in_progress = False

    def __process_sql_import(self, db_path: str, table_name: str, selected_cols: List[str], db_filter: str) -> bool:
        """
        Imports the selected database into the this table editor's table data for editing. Data is pushed to
        the back-end when OK | Apply are pressed.
        :param db_path: the path to the database.
        :param table_name: the name of the table.
        :param selected_cols: A list of columns to import from the table.
        :param db_filter: the SQL "WHERE" clause to get only specific data that matches the filter.
        :returns: a boolean flag indicating if the import was successful.
        """
        if not db_filter:
            # change '' to None
            db_filter = None

        self.__last_db_import_path = db_path
        self.__last_db_import_filter = db_filter

        try:
            table_import = import_from_msaccess(db_path, table_name, selected_cols, db_filter)
        except Exception as db_error:
            title = "Database Import Error"
            msg = "If a table filter is applied, verify that SQLite syntax and column names are correct."
            on_database_error(title, str(db_error), optional_msg=msg)
            return False

        col_info, records = table_import

        # the indices of col_info
        names_idx = 0
        types_idx = 1
        sizes_idx = 2

        data = dict(name=self.__table_part.part_frame.name)
        data['col_names'] = [info[names_idx] for info in col_info]
        data['col_types'] = [info[types_idx] for info in col_info]
        data['col_sizes'] = [info[sizes_idx] for info in col_info]
        data['col_indexes'] = {}
        data['filter'] = str()
        data['display_order'] = DisplayOrderEnum.of_creation
        data['sorted_column'] = [self.ZERO_IDX]

        # process records to format datetime objects as strings
        if 'DATETIME' in data['col_types']:
            date_idx = data['col_types'].index('DATETIME')
            for idx, rec in enumerate(records):
                rec = list(rec)
                dt_rec = rec[date_idx]
                str_rec = dt_rec.strftime(SQLITE_DATETIME_FORMAT)
                rec[date_idx] = str_rec
                records[idx] = rec

        data['records'] = records

        self._on_data_arrived(data)
        return True

    def __launch_export_dialog(self):
        """
        Launches the table export dialog to export data to an access database.
        """
        self.__export_dialog = ExportDatabaseDialog(self.__table_part,
                                                    fields=self.__table_model.col_name_cache,
                                                    last_db_export_path=self.__last_db_export_path,
                                                    table_editor=self)

        answer = self.__export_dialog.exec()
        if answer:
            db_path, db_table, db_selected_fields = self.__export_dialog.get_user_input()
            self.__process_sql_export(db_path, db_table, db_selected_fields)

    def __process_sql_export(self, db_path: str, table_name: str, selected_cols: List[str]):
        """
        Exports the table data from the editor to the selected database. Since a SQL filter may be applied, the
        backend table part's embedded database is used to apply the filter to the editor data first, before the data
        is exported.
        :param db_path: the path to the database.
        :param table_name: the name of the table.
        :param selected_cols: A list of columns to import from the table.
        """
        self.__last_db_export_path = db_path
        data = self._get_data_for_submission()

        col_names_types_sizes = []
        for idx, col_name in enumerate(data['col_names']):
            col_type = data['col_types'][idx]
            col_size = data['col_sizes'][idx]
            if col_size is not None:
                col_names_types_sizes.append((col_name, col_type, int(col_size)))
            else:
                col_names_types_sizes.append((col_name, col_type, col_size))

        def get_filtered_data():
            """
            This method is passed to the backend thread in order to apply the current SQL filter on the data in the
            editor panel. Note that the data in the editor, and not the backend table part, is filtered by the table
            part's embedded database. This must occur in the backend thread.
            """
            sql_filter = self.__table_model.filter if self.__table_model.filter != '' else None
            filtered_data, col_types_and_sizes = self.__table_part.embedded_db.filter_raw_data(data['records'],
                                                                                               data['col_names'],
                                                                                               col_names_types_sizes,
                                                                                               selected_cols,
                                                                                               sql_filter)

            return filtered_data, col_types_and_sizes

        def on_filtered_data_received(filtered_data, col_types_and_sizes):
            """
            Export the filtered editor data.
            :param filtered_data: Editor data that has been filtered by the applied SQL filter.
            :param col_types_and_sizes: The corresponding column names and sizes to the filtered data.
            """
            try:
                export_to_msaccess(selected_cols, col_types_and_sizes, filtered_data, db_path, table_name)
            except Exception as db_error:
                title = "Database Export Error"
                on_database_error(title, str(db_error))
                self.__launch_export_dialog()

            self.__export_dialog = None  # reset for fresh dialog on next launch

        AsyncRequest.call(get_filtered_data, response_cb=on_filtered_data_received)

    def __launch_index_dialog(self):
        """
        Launches the table index dialog to create indexes between table columns.
        """
        self.__index_dialog = ColumnIndexDialog(self.__table_part, self.__table_model, table_editor=self)
        answer = self.__index_dialog.exec()
        if answer:
            self.set_indexed_columns(self.__index_dialog.get_user_input())

    def __toggle_sort(self):
        """
        Toggles sort on and off when the sort button is pressed.
        """
        if self.ui.table_view.isSortingEnabled():
            # Disable sorting
            self.__set_default_model()
            self.__proxy_model.sig_column_sorted.disconnect(self.__slot_sort)
            self.ui.change_row_count_spin_box.setEnabled(True)
            self.ui.change_column_count_spin_box.setEnabled(True)

        else:
            # Enable sorting
            self.__set_proxy_model(sorted_column=self.__sorted_column[self.ZERO_IDX], sort_order=Qt.AscendingOrder)
            self.ui.change_row_count_spin_box.setEnabled(False)
            self.ui.change_column_count_spin_box.setEnabled(False)

    def __sort(self, sorted_column: int, sort_order: int):
        """
        Changes the sort order of the selected column. If no column is currently selected, sorts the previous selected
        column.
        :param sorted_column: The selected column to sort.
        :param sort_order: The direction of the sort operation (ascending or descending).
        """
        self.__sorted_column = [sorted_column]
        self.__sort_order = sort_order

    def __init_model_sort_order(self):
        """
        Initializes sort order of the editor table data from the setting used the last time the editor was open.
        - initialize the sort order from form the table model's 'display order'
        - conversion factor of -1 required to work with Qt's SortOrder enum (0 == AscendingOrder, 1 == DescendingOrder)
        - sorting options are: no sort, sort ascending, sort descending.
        """
        if self.__table_model.display_order in [DisplayOrderEnum.alphabetical, DisplayOrderEnum.reverse_alphabetical]:
            self.__set_proxy_model(self.__table_model.sorted_column[self.ZERO_IDX],
                                   self.__table_model.display_order - 1)
            self.ui.table_view.selectColumn(self.__table_model.sorted_column[self.ZERO_IDX])
        else:
            self.__set_default_model()

    def __set_default_model(self):
        """
        Sets the table view to use the default model when sorting is disabled.
        """
        self.__sort_order = TablePartEditorPanel.NO_SORT

        self.ui.table_view.setModel(self.__table_model)
        self.ui.table_view.setSelectionModel(self.__selection_model)
        self.ui.table_view.setSortingEnabled(False)

        self.__selection_model.clearSelection()
        self.__selection_model.currentChanged.connect(self.__slot_on_item_changed)
        self.__selection_model.selectionChanged.connect(self.__slot_on_selection_changed)

        # Enable row/column count spin-boxes once sorting is disabled
        self.ui.change_row_count_spin_box.setEnabled(True)
        self.ui.change_column_count_spin_box.setEnabled(True)

    def __set_proxy_model(self, sorted_column: int, sort_order: int):
        """
        Sets the table view to use the proxy model to enable column sorting.
        :param sorted_column: The selected column to sort.
        :param sort_order: The alphabetical direction of the sort: ascending, descending, or none.
        """
        self.__sorted_column = [sorted_column]
        self.__sort_order = sort_order

        all_col_idxs = [col for col in range(self.__table_model.cols)]
        self.__proxy_model = SortFilterProxyModelByColumns(self.parent(), all_col_idxs)  # self.__sorted_column
        self.__proxy_model.setSourceModel(self.__table_model)
        self.__proxy_model.sig_column_sorted.connect(self.__slot_sort)
        self.__selection_proxy_model = QItemSelectionModel(self.__proxy_model)

        self.ui.table_view.setModel(self.__proxy_model)
        self.ui.table_view.setSelectionModel(self.__selection_proxy_model)
        self.ui.table_view.setSortingEnabled(True)
        self.ui.table_view.sortByColumn(sorted_column, sort_order)

        self.__selection_proxy_model.clearSelection()
        self.__selection_proxy_model.currentChanged.connect(self.__slot_on_item_changed)
        self.__selection_proxy_model.selectionChanged.connect(self.__slot_on_selection_changed)

        # Disable row/column count spin-boxes (causes issues while sort is enabled)
        self.ui.change_row_count_spin_box.setEnabled(False)
        self.ui.change_column_count_spin_box.setEnabled(False)

    def __map_rows_to_sorted_model(self, src_row_indexes: List[int]) -> List[QModelIndex]:
        """
        Maps the (unsorted) source-model row indexes to sorted proxy-model row indexes.
        :param src_row_indexes: A list of source model indexes to map.
        :return: A list of sorted model indexes.
        """
        mapped_row_indexes = []

        for row_idx in src_row_indexes:
            src_index = self.__table_model.index(row_idx, self.ZERO_IDX)
            proxy_index = self.__proxy_model.mapFromSource(src_index)
            mapped_row_indexes.append(proxy_index.row())

        return mapped_row_indexes

    __slot_init_model_sort_order = safe_slot(__init_model_sort_order)
    __slot_on_item_changed = safe_slot(__on_item_changed)
    __slot_on_selection_changed = safe_slot(__on_selection_changed)

    __slot_on_column_moved = safe_slot(__on_column_moved)
    __slot_on_change_column_properties = safe_slot(__on_change_column_properties)
    __slot_toggle_sort = safe_slot(__toggle_sort)
    __slot_sort = safe_slot(__sort)

    __slot_insert_before = safe_slot(__insert_before)
    __slot_insert_after = safe_slot(__insert_after)
    __slot_select_all = safe_slot(__select_all)
    __slot_cut = safe_slot(__cut)
    __slot_copy = safe_slot(__copy)
    __slot_paste = safe_slot(__paste)
    __slot_delete = safe_slot(__delete)

    __slot_set_column_filter = safe_slot(__launch_filter_dialog)
    __slot_refresh_column_filter = safe_slot(__refresh_column_filter)
    __slot_import_database = safe_slot(__launch_import_dialog)
    __slot_export_database = safe_slot(__launch_export_dialog)
    __slot_set_column_indexes = safe_slot(__launch_index_dialog)

    __slot_on_row_number_changed_by_model = safe_slot(__on_row_number_changed_by_model)
    __slot_on_column_number_changed_by_model = safe_slot(__on_column_number_changed_by_model)
    __slot_on_filter_changed_by_model = safe_slot(__on_filter_changed_by_model)
    __slot_on_row_spinbox_edit = safe_slot(__on_row_spinbox_edit, arg_types=())
    __slot_on_column_spinbox_edit = safe_slot(__on_column_spinbox_edit, arg_types=())

    __slot_on_column_header_clicked = safe_slot(__on_column_header_clicked)
    __slot_on_row_header_clicked = safe_slot(__on_row_header_clicked)


register_part_editor_class(ori.OriTablePartKeys.PART_TYPE_TABLE, TablePartEditorPanel)
