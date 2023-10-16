# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Sheet Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import webbrowser
from enum import IntEnum
from pathlib import Path, WindowsPath
from copy import deepcopy

# [2. third-party]
from PyQt5.QtCore import pyqtSignal, QItemSelectionModel, QItemSelection, Qt, QAbstractTableModel, QVariant, QModelIndex
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QAbstractItemView, QWidget, QHeaderView, QMessageBox, QInputDialog, QLineEdit, QDialog
from PyQt5.QtWidgets import QFileDialog, QDialogButtonBox
from PyQt5.QtGui import QIcon

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core import override, override_required, override_optional, validate_python_name
from ...scenario import ori
from ...scenario.defn_parts import SheetPart, excel_column_letter, get_col_header, SheetIndexStyleEnum
from ...scenario.defn_parts.sheet_part import read_from_excel, write_to_excel, get_excel_sheets

from ..gui_utils import exec_modal_dialog, PyExpr, get_icon_path, get_scenario_font, retrieve_cached_py_expr
from ..safe_slot import safe_slot

from .special_value_editor import SpecialValueDisplay
from .scenario_part_editor import BaseContentEditor
from .Ui_sheet_part_editor import Ui_SheetPartEditor
from .Ui_sheet_import_dialog import Ui_SheetImportDialog
from .part_editors_registry import register_part_editor_class
from .common import EditorDialog, DialogHelp

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SheetPartEditorPanel',
    'ImportExcelDialog',
    'ExportExcelDialog'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def on_excel_error(title, excel_error: str, optional_msg: str = None):
    """
    Display a modal error dialog when there is an Excel error.
    :param title: The dialog title.
    :param excel_error: The error message returned from Excel.
    :param optional_msg: An optional message to display.
    """
    error_msg = "The following error was raised: {}".format(excel_error)
    if optional_msg is not None:
        error_msg += "\n\n{}".format(optional_msg)

    exec_modal_dialog(title, error_msg, QMessageBox.Critical)
    log.error('{}: {}', title, error_msg)


# -- Class Definitions --------------------------------------------------------------------------

class InsertBeforeOrAfterEnum(IntEnum):
    """
    Enumerate where to insert a new row or column (before or after the index supplied).
    """
    before, after = range(2)


# noinspection PyUnresolvedReferences
class SheetEditorDialog(EditorDialog):
    """
    The base class for Sheet Editor dialogs sets up the UI features and interface with the Sheet Editor.
    """

    def __init__(self, sheet_part: SheetPart, ui: Any, parent: QWidget = None):
        super().__init__(parent)

        self.ui = ui
        self.ui.setupUi(self)
        self.ui.button_box.accepted.connect(self.accept)
        self.ui.button_box.rejected.connect(self.reject)

        self.sheet_editor = parent
        self._part = sheet_part

        self.__dialog_help = DialogHelp()
        self.ui.help_button.clicked.connect(self.__slot_on_help_button_pressed)

    @override(QDialog)
    def done(self, result: int):
        if result != QDialog.Rejected:
            isvalid = self._validate_user_input()
            if not isvalid:
                # For invalid results, return the user to the original dialog to correct mistakes
                return

        super().done(result)

    @override_optional
    def get_user_input(self) -> Tuple[Any]:
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

    @override_required
    def _on_browse_files(self, _: bool):
        """
        Each specific dialog must implement this function to open a file browser to select files for import or export.
        """
        raise NotImplementedError('Implementation needed.')

    @override_required
    def _on_filepath_changed(self):
        """
        Each specific dialog must implement this function to respond to filepath changes.
        """
        raise NotImplementedError('Implementation needed.')

    @override_required
    def _on_sheet_list_requested(self, _: bool):
        """
        Each specific dialog must implement this function to generate a list of sheets and populate the combobox.
        """
        raise NotImplementedError('Implementation needed.')

    def _enable_file_selection(self, enabled: bool):
        """
        Enable or disable the file selection components of the dialog.
        :param enabled: The enable status to set.
        """
        self.ui.file_label.setEnabled(enabled)
        self.ui.filepath_linedit.setEnabled(enabled)
        self.ui.browse_files_button.setEnabled(enabled)

    def _enable_list_sheets_button(self, enabled: bool):
        """
        Enable or disable the button that retrieves the list of sheets.
        :param enabled: The enable status to set.
        """
        self.ui.sheet_combobox.clear()  # remove all previous entries
        self.ui.list_sheets_button.setEnabled(enabled)

    def _enable_sheet_selection(self, enabled: bool):
        """
        Enable or disable the sheet and range selection selection components.
        :param enabled: The enable status to set.
        """
        self.ui.sheet_label.setEnabled(enabled)
        self.ui.sheet_combobox.setEnabled(enabled)
        self.ui.range_label.setEnabled(enabled)
        self.ui.range_linedit.setEnabled(enabled)

    def _enable_ok(self, enabled: bool):
        """
        Enable or disable the OK button.
        :param enabled: The enable status to set.
        """
        self.ui.button_box.button(QDialogButtonBox.Ok).setEnabled(enabled)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_help_button_pressed(self):
        """
        Method called when the 'Help' button is clicked from the sheet dialog.
        """
        path = self.__dialog_help.get_dialog_help_path(self._part.PART_TYPE_NAME)
        webbrowser.open_new_tab(path)

    __slot_on_help_button_pressed = safe_slot(__on_help_button_pressed)


# noinspection PyUnresolvedReferences
class ImportExcelDialog(SheetEditorDialog):
    """
    Dialog to import Excel data into the sheet.
    """
    # --------------------------- class-wide data and signals -----------------------------------

    LAST_IMPORT_DIR = 'part_editors.sheet_part_editor.LAST_IMPORT_DIR'

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, sheet_part: SheetPart,
                 last_sheet_import_path: str = None,
                 sheet_editor: QWidget = None):
        """
        Initialize the sheet import dialog.
        :param sheet_part: The backend sheet part.
        :param last_sheet_import_path: The path to the Excel file being imported.
        :param sheet_editor: The parent sheet part editor of this dialog (if any).
        """
        ui = Ui_SheetImportDialog()
        super().__init__(sheet_part, ui, sheet_editor)

        # Set the dialog title
        self.setWindowTitle('Import from Excel')
        self.ui.instructions_label.setText("Click OK to replace the sheet data with the imported data or Cancel "
                                           "to go back.")

        # disable all components except file selection
        self._enable_list_sheets_button(False)
        self._enable_sheet_selection(False)
        self._enable_ok(False)

        self.ui.browse_files_button.clicked.connect(self._slot_on_browse_files)
        self.ui.filepath_linedit.editingFinished.connect(self._slot_on_filepath_changed)
        self.ui.list_sheets_button.clicked.connect(self._slot_on_sheet_list_requested)

        if last_sheet_import_path is not None:
            self.ui.filepath_linedit.setText(last_sheet_import_path)
            self._on_filepath_changed()
            self._on_sheet_list_requested(True)
            self.ui.sheet_combobox.setFocus(Qt.OtherFocusReason)

    @override(SheetEditorDialog)
    def get_user_input(self) -> Tuple[str, str, str]:
        """
        Optionally implement this function to get the input from the dialog.
        :return: A tuple of user input.
        """
        excel_path = self.ui.filepath_linedit.text()
        excel_sheet = self.ui.sheet_combobox.currentText()
        excel_range = self.ui.range_linedit.text()
        return excel_path, excel_sheet, excel_range

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(SheetEditorDialog)
    def _on_browse_files(self, _: bool):
        """
        Opens a file browser to select the Excel file to import.
        """
        excel_path, ext = QFileDialog.getOpenFileName(self, "Select Excel File to Import",
                                                      QSettings().value(self.LAST_IMPORT_DIR),
                                                      "Excel (*.xls *.xlsx)")

        if not excel_path:
            return

        self.ui.filepath_linedit.setText(excel_path)
        self._on_filepath_changed()

    @override(SheetEditorDialog)
    def _on_filepath_changed(self):
        """
        Update the path to the selected Excel file.
        """
        self._enable_ok(False)
        self._enable_sheet_selection(False)

        # disable until we know a valid file path was entered
        self._enable_list_sheets_button(False)
        excel_path = self.ui.filepath_linedit.text()
        if not excel_path:
            return

        excel_path = Path(excel_path)

        # if only file name entered without full path, prepend cwd
        if not excel_path.is_absolute():
            excel_path = Path.cwd() / excel_path

        # add extension if missing
        if excel_path.suffix == '':
            excel_path = excel_path.with_suffix('.xls')

        # reset the path with the updated info
        self.ui.filepath_linedit.setText(str(excel_path))

        # if the file does not exist, can't import
        if not excel_path.exists():
            exec_modal_dialog("File Not Found", "The file path entered does not exist.", QMessageBox.Information)
            return

        QSettings().setValue(self.LAST_IMPORT_DIR, str(excel_path.parent))
        self._enable_list_sheets_button(True)

    @override(SheetEditorDialog)
    def _on_sheet_list_requested(self, _: bool):
        """
        Request the list of sheets from the selected Excel file and populate the combobox.
        """
        self.ui.sheet_combobox.clear()  # remove all previous entries
        excel_path = self.ui.filepath_linedit.text()

        try:
            sheets = get_excel_sheets(excel_path)
        except Exception as exc:
            msg_title = 'Sheet List Error'
            error_msg = 'The list of sheets could not be retrieved from Excel file \'{}\'.\n{}'.format(excel_path, exc)
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            return

        self.ui.sheet_combobox.insertItems(0, sheets)
        self._enable_sheet_selection(True)
        self._enable_ok(True)

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    _slot_on_browse_files = safe_slot(_on_browse_files)
    _slot_on_filepath_changed = safe_slot(_on_filepath_changed)
    _slot_on_sheet_list_requested = safe_slot(_on_sheet_list_requested)


# noinspection PyUnresolvedReferences
class ExportExcelDialog(SheetEditorDialog):
    """
    Dialog to export Excel data into the sheet.
    """
    # --------------------------- class-wide data and signals -----------------------------------

    LAST_EXPORT_DIR = 'part_editors.sheet_part_editor.LAST_EXPORT_DIR'
    NEW_STR = ' (New)'

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, sheet_part: SheetPart,
                 last_sheet_export_path: str = None,
                 sheet_editor: QWidget = None):
        """
        Initialize the sheet export dialog.
        :param sheet_part: The backend sheet part.
        :param last_sheet_export_path: The path to the Excel file being exported.
        :param sheet_editor: The parent sheet part editor of this dialog (if any).
        """
        ui = Ui_SheetImportDialog()
        super().__init__(sheet_part, ui, sheet_editor)

        # Set the dialog title
        self.setWindowTitle('Export to Excel')
        self.ui.instructions_label.setText("Click OK to export the Sheet Part's data to the selected sheet of the "
                                           "chosen Excel file. A destination range can be specified. "
                                           "Click Cancel to abandon exporting.")

        # disable all components except file selection
        self._enable_list_sheets_button(False)
        self._enable_sheet_selection(False)
        self._enable_ok(False)

        self.__unique_sheet_id = 0  # create unique new sheet names during export
        self.__default_sheet_name = None

        self.ui.browse_files_button.clicked.connect(self._slot_on_browse_files)
        self.ui.filepath_linedit.textChanged.connect(self._slot_on_filepath_changed)
        self.ui.filepath_linedit.editingFinished.connect(self.__slot_on_filepath_entered)
        self.ui.list_sheets_button.clicked.connect(self._slot_on_sheet_list_requested)
        self.ui.sheet_combobox.currentIndexChanged['int'].connect(self._slot_on_sheet_selected)

        if last_sheet_export_path is not None:
            self.ui.filepath_linedit.setText(last_sheet_export_path)
            self._on_filepath_changed()
            self._on_sheet_list_requested(True)
            self.ui.sheet_combobox.setFocus(Qt.OtherFocusReason)

    @override(SheetEditorDialog)
    def get_user_input(self) -> Tuple[str, str, str]:
        excel_path = self.ui.filepath_linedit.text()
        excel_sheet = self.ui.sheet_combobox.currentText()
        excel_range = self.ui.range_linedit.text()
        return excel_path, excel_sheet, excel_range

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(SheetEditorDialog)
    def _validate_user_input(self) -> bool:
        """
        Gets the export Excel file path, sheet name, and cell range and sends them to the sheet editor.
        """
        # make required modifications to the selected sheet name
        if self.ui.sheet_combobox.currentText() == self.__default_sheet_name + self.NEW_STR:
            self.__unique_sheet_id += 1  # increment for next export
            self.ui.sheet_combobox.setItemText(0, self.__default_sheet_name)  # remove '(New)' on default sheet name

        elif self.ui.sheet_combobox.findText(self.ui.sheet_combobox.currentText()) == -1:
            # the user edited the default name, add it to the combo box
            new_sheet_name = self.ui.sheet_combobox.currentText()
            self.ui.sheet_combobox.insertItem(0, new_sheet_name)  # add the user-entered name
            self.ui.sheet_combobox.setCurrentText(new_sheet_name)

        else:
            pass  # no other entries require modification

        return super()._validate_user_input()

    @override(SheetEditorDialog)
    def _on_browse_files(self, _: bool):
        """
        Opens a file browser to select or create the Excel file to export.
        """
        select_file_dialog = QFileDialog(self, "Export to Excel: select or create file",
                                         QSettings().value(self.LAST_EXPORT_DIR),
                                         "Excel (*.xls)")
        select_file_dialog.setFileMode(QFileDialog.AnyFile)
        path_selected = select_file_dialog.exec()
        if not path_selected:
            return

        self.ui.filepath_linedit.setText(select_file_dialog.selectedFiles()[0])
        self._on_filepath_changed()
        self.__on_filepath_entered()

    @override(SheetEditorDialog)
    def _on_filepath_changed(self, _: str = None):
        """
        Update the path to the selected Excel file.
        """
        self._enable_ok(False)
        self._enable_sheet_selection(False)

        # disable until we know a valid file path was entered
        self._enable_list_sheets_button(False)
        excel_path = self.ui.filepath_linedit.text()
        if not excel_path:
            return

        QSettings().setValue(self.LAST_EXPORT_DIR, str(Path(excel_path).parent))
        self._enable_list_sheets_button(True)

    @override(SheetEditorDialog)
    def _on_sheet_list_requested(self, _: bool):
        """
        Request the list of sheets from the selected Excel file and populate the combobox.
        """
        excel_path = self.ui.filepath_linedit.text()

        try:
            sheets = get_excel_sheets(excel_path)
        except Exception as exc:
            msg_title = 'Sheet List Error'
            error_msg = 'The list of sheets could not be retrieved from Excel file \'{}\'.\n{}'.format(excel_path, exc)
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            return

        # create a new blank default sheet - ensure its name is not in the current list of sheets
        while True:
            default_sheet = '{}_{}'.format(self._part.name, self.__unique_sheet_id)
            if default_sheet in sheets:
                self.__unique_sheet_id += 1
            else:
                break

        sheets.insert(0, default_sheet + self.NEW_STR)
        self.__default_sheet_name = default_sheet
        # self.ui.sheet_combobox.clear()  # remove all previous entries
        self.ui.sheet_combobox.insertItems(0, sheets)
        self._enable_sheet_selection(True)
        self._enable_ok(True)

    def _on_sheet_selected(self, index: int):
        """
        Responds to sheet selection via the dialog's combo box. Sets the dialog to editable when the "new" sheet in the
            first entry is selected, and not-editable otherwise.
        :param index: The index currently selected.
        """
        if index == 0:
            self.ui.sheet_combobox.setEditable(True)

        else:
            self.ui.sheet_combobox.setEditable(False)

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    _slot_on_browse_files = safe_slot(_on_browse_files)
    _slot_on_filepath_changed = safe_slot(_on_filepath_changed)
    _slot_on_sheet_list_requested = safe_slot(_on_sheet_list_requested)
    _slot_on_sheet_selected = safe_slot(_on_sheet_selected)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_filepath_entered(self):
        """
        Updates the file path displayed and verifies the directory exists when editing is finished.
        """
        excel_path = self.ui.filepath_linedit.text()
        if not excel_path:
            return

        excel_path = Path(excel_path)

        # if only file name entered without full path, prepend cwd
        if not excel_path.is_absolute():
            excel_path = Path.cwd() / excel_path

        # add extension if missing
        if excel_path.suffix == '':
            excel_path = excel_path.with_suffix('.xls')

        # for manually entered paths, check that the parent directory exists
        if not excel_path.parent.exists():
            title = 'Directory Does Not Exist'
            msg = 'The specified directory does not exist. Press OK to create the directory or Cancel to go back.'
            ok = exec_modal_dialog(title, msg, QMessageBox.Information, buttons=[QMessageBox.Ok, QMessageBox.Cancel])
            if ok == QMessageBox.Ok:
                log.info('Creating export directory: {}', Path(excel_path).parent)
                Path.mkdir(excel_path.parent, parents=True)
            else:
                self._enable_list_sheets_button(False)
                return

        # reset the path with the updated info
        self.ui.filepath_linedit.setText(str(excel_path))

    __slot_on_filepath_entered = safe_slot(__on_filepath_entered)


class SheetPartTableModelForEditing(QAbstractTableModel):
    """
    Implements a table model for getting and setting Sheet Part data.

    A note on PyExpr: PyExpr is used as a data wrapper on all values in the sheet part. However, since using eval() on
    EVERY value in large sheets is costly, the PyExpr wrapper is only used in certain instances, such as when the value
    is double-clicked for editing. This 'lazy' evaluation is necessary to ensure the editor opens quickly for large
    sheets.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    IndexPair = Tuple[int, int]
    CellRangeIndices = Tuple[IndexPair, IndexPair]

    sig_rows_changed = pyqtSignal(int)  # number or rows
    sig_cols_changed = pyqtSignal(int)  # number of columns

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, sheet_part: SheetPart, parent: QWidget = None):
        super().__init__(parent)

        # The backend part to view
        self.__sheet_part = sheet_part

        # Init row and column count values
        self.__rows = 0
        self.__cols = 0

        # Store the previous row and column counts for tracking purposes
        self.__orig_rows = 0
        self.__orig_cols = 0
        # A grid cache: PyExprGridCache
        self.__py_expr_cache = dict()

        # Cache back-end sheet data for quick front-end updates
        self.__col_name_cache = []
        self.__custom_name_cache = {}
        self.__data_cache = []  # [] within [] to represent a sheet (table)
        self.__cells_copied = None

        self.__index_style = SheetIndexStyleEnum[self.__sheet_part.index_style]
        self.__sheet_part.signals.sig_col_idx_style_changed.connect(self.__slot_on_index_style_changed)

    def get_cell(self, index: QModelIndex) -> PyExpr:
        """
        Gets the cell data, converted to a PyExpr object, from the cache .
        :param index: The index of the cell to get.
        :return: The PyExpr object.
        """
        row_index = index.row()
        col_index = index.column()
        return retrieve_cached_py_expr(self, self.__py_expr_cache, index, self.__data_cache[row_index][col_index])

    def set_cell(self, index: QModelIndex, val: PyExpr):
        """
        Sets the data, converted from a PyExpr object, to a cell in the cache.
        :param index: The index of the cell to set.
        :param val: The PyExpr object
        """
        self.__data_cache[index.row()][index.column()] = val.obj

    # noinspection PyUnresolvedReferences
    @override(QAbstractTableModel)
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> Either[str, None]:
        """
        Gets the current horizontal (column) and vertical (row) header data from the Sheet Part at the index 'section'.
        See the Qt documentation for method parameter definitions.
        """
        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal and section < self.__cols:
            try:
                return str(self.__col_name_cache[section])
            except IndexError:
                return None

        if orientation == Qt.Vertical and section < self.__rows:
            return str(section + 1)

        return None

    # noinspection PyUnresolvedReferences
    @override(QAbstractTableModel)
    def setHeaderData(self, section: int, orientation: Qt.Orientation, header: QVariant, role=Qt.EditRole) -> bool:
        """
        Sets the horizontal (column) header data into the Sheet Part at index 'section'. Only column headers can be set.
        See the Qt documentation for method parameter definitions.
        """

        if role == Qt.EditRole and orientation == Qt.Horizontal:

            col_index = section
            new_name = header.value()

            try:
                self.__col_name_cache[col_index] = new_name  # Over-write existing value
                self.headerDataChanged.emit(orientation, section, section)
                return True
            except IndexError:
                # For some reason the view is trying to access header data that is not in the cache
                pass

        return False

    # noinspection PyMethodOverriding
    @override(QAbstractTableModel)
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of rows in the Sheet Part cache (parent_index invalid), or 0 if parent_index is valid.

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

    # noinspection PyMethodOverriding
    @override(QAbstractTableModel)
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of columns in the Sheet Part cache (if parent_index invalid), or 0 if parent_index is valid.

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
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> str:
        """
        This method returns the Sheet Part data located at 'index' to the Sheet Part's View (class SheetPart2dContent).

        View requests an update when the signal 'dataChanged' is emitted by one of this class' slots. Each slot is set
        to receive a specific signal from the backend Sheet Part when data in the sheet has changed. For example, a row
        update across a subset of rows would cause the slot 'slot_update_rows' to be called with the affected row index
        range. The dataChanged signal is called in turn, causing the View to update the contents of the specified rows.

        See the Qt documentation for method parameter definitions.
        """
        if not index.isValid():
            # the index is the "root" of sheet, which has no data
            return None

        # Return a value if either DisplayRole or EditRole is obtained...
        # This ensures that while editing, the original value is preserved until setData() is called to update to the
        # new value (otherwise this method will return None during editing which clears the original cell value even
        # when the user does not edit the value).
        row_index = index.row()
        col_index = index.column()

        if role == Qt.DisplayRole or role == Qt.EditRole:

            # Check if there is something in the cache to return
            try:
                val_wrapper = retrieve_cached_py_expr(self,
                                                      self.__py_expr_cache,
                                                      index,
                                                      self.__data_cache[row_index][col_index])
                return str(val_wrapper)
            except (KeyError, IndexError):
                # somehow the view is asking for data not in the cache, so nothing to return:
                return QVariant()

        if role == Qt.TextAlignmentRole:
            return Qt.AlignHCenter | Qt.AlignVCenter

        if role == Qt.ToolTipRole:
            val_wrapper = retrieve_cached_py_expr(self,
                                                  self.__py_expr_cache,
                                                  index,
                                                  self.__data_cache[row_index][col_index])
            return val_wrapper.get_edit_tooltip()

        return QVariant()

    @override(QAbstractTableModel)
    def setData(self, index: QModelIndex, value: QVariant, role: int = Qt.EditRole):
        """
        Sets data from the Sheet Part editor.

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
            # the index is the "root" of sheet, which has no data
            return False

        if role == Qt.EditRole:

            row_index = index.row()
            col_index = index.column()

            try:
                if value == '':
                    value = 0
                obj_value = eval(value)
            except:
                # Do nothing: the string object 'value' cannot be evaluated as a Python expression -> leave as string
                obj_value = value

            try:
                self.__data_cache[row_index][col_index] = obj_value  # Override existing value
                field_index = self.index(row_index, col_index)
                # noinspection PyUnresolvedReferences
                self.dataChanged.emit(field_index, field_index)
                return True
            except IndexError:
                # For some reason the View tried to set data to an index that doesn't exist
                pass

        return False

    # noinspection PyUnresolvedReferences
    @override(QAbstractTableModel)
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Sets all items in the sheet's view to be 'selectable', 'editable', and 'enabled'.

        See the Qt documentation for method parameter definitions.
        """
        if not index.isValid():
            return Qt.NoItemFlags

        row_index = index.row()
        col_index = index.column()
        val_wrapper = retrieve_cached_py_expr(self,
                                              self.__py_expr_cache,
                                              index,
                                              self.__data_cache[row_index][col_index])

        if val_wrapper.is_representable():
            return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled
        else:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    # noinspection PyMethodOverriding
    @override(QAbstractTableModel)
    def insertColumns(self, insert_index: int, num_columns: int, parent=QModelIndex()) -> bool:
        """
        Inserts columns into the model before the given column index, insert_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the sheet has changed
        self.beginInsertColumns(parent, insert_index, insert_index + num_columns - 1)
        self.sig_cols_changed.emit(self.cols)
        self.endInsertColumns()

        # Check that a columns have been added
        return self.__orig_cols < self.__cols

    # noinspection PyMethodOverriding
    @override(QAbstractTableModel)
    def removeColumns(self, remove_index: int, num_columns: int, parent=QModelIndex()) -> bool:
        """
        Removes columns of number num_columns starting with the given column index, remove_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the sheet has changed
        self.beginRemoveColumns(parent, remove_index, remove_index + num_columns - 1)
        self.sig_cols_changed.emit(self.cols)
        self.endRemoveColumns()

        # Check that a columns have been removed
        return self.__orig_cols > self.__cols

    # noinspection PyMethodOverriding
    @override(QAbstractTableModel)
    def insertRows(self, insert_index: int, num_rows: int, parent=QModelIndex()) -> bool:
        """
        Inserts rows of number num_rows into the model before the given row index, insert_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the sheet has changed
        self.beginInsertRows(parent, insert_index, insert_index + num_rows - 1)
        self.sig_rows_changed.emit(self.rows)
        self.endInsertRows()

        # Check that a rows have been added
        return self.__orig_rows < self.__rows

    # noinspection PyMethodOverriding
    @override(QAbstractTableModel)
    def removeRows(self, remove_index: int, num_rows: int, parent=QModelIndex()) -> bool:
        """
        Removes rows of number num_rows starting with the given row index, remove_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the sheet has changed
        self.beginRemoveRows(parent, remove_index, remove_index + num_rows - 1)
        self.sig_rows_changed.emit(self.rows)
        self.endRemoveRows()

        # Check that a rows have been removed
        return self.__orig_rows > self.__rows

    def get_part(self) -> SheetPart:
        """
        Gets the Sheet Part of this sheet.
        :returns: the back-end Sheet Part.
        """
        return self.__sheet_part

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

    def get_col_names(self) -> List[str]:
        """
        Returns the list of column names.
        :return:
        """
        return self.__col_name_cache

    def init_model(self, data: Dict[str, Any]):
        # Colin FIXME ASAP: convert data to a named tuple instead of dict
        #     Reason: type will be clearer and faster/smaller
        """
        Initializes the sheet editor data content and attributes.
        :param data: the back-end sheet data.
        """
        self.beginResetModel()
        self.__on_init_col_names(data['all_col_names'], data['custom_col_names'])
        self.__on_init_sheet_data(data['sheet_data'])
        self.endResetModel()

    def fill_data_for_submission(self, data: Dict[str, Any]):
        # Colin FIXME ASAP: convert data to a named tuple instead of dict
        #     Reason: type will be clearer and faster/smaller
        """
        Fills the the data dictionary with the edited sheet data for submission to the back-end Sheet Part.
        :param data: the data to submit.
        """
        data['sheet_data'] = self.__data_cache
        data['all_col_names'] = self.__col_name_cache
        data['custom_col_names'] = self.__custom_name_cache

    def insert_rows(self, row_indexes_to_insert: List[int], where: InsertBeforeOrAfterEnum,
                    insert_after_selection: bool = True):
        """
        Inserts rows into the sheet before or after the given row index.
        :param row_indexes_to_insert: a list of row indexes to insert.
        :param where: indicates whether to insert before or after the row_index provided.
        :param insert_after_selection: indicates if the new rows should be inserted after or at the selected row.
        """

        if where == InsertBeforeOrAfterEnum.before:

            # Insert a contiguous selection via the Insert button (empty data)
            for row in row_indexes_to_insert:
                row_data = [0] * self.cols
                self.__data_cache.insert(row, row_data)

            num_rows_to_add = len(row_indexes_to_insert)

            # Inform the sheet view of the change
            row_start_index = row_indexes_to_insert[0]
            self.__rows += num_rows_to_add
            self.insertRows(row_start_index, num_rows_to_add)
            top_left_index = self.index(row_start_index, 0)
            bottom_right_index = self.index(row_start_index + num_rows_to_add, self.__cols - 1)
            # noinspection PyUnresolvedReferences
            self.dataChanged.emit(top_left_index, bottom_right_index)

        else:

            # Shift the indexes to the end of the selection
            shift = len(row_indexes_to_insert)
            if insert_after_selection:
                for idx, _ in enumerate(row_indexes_to_insert):
                    row_indexes_to_insert[idx] += shift

            # Add data to the cache
            for row in row_indexes_to_insert:
                row_data = [0] * self.cols
                self.__data_cache.insert(row, row_data)

            # Inform the sheet view of the change
            row_start_index = row_indexes_to_insert[0]
            num_rows_to_add = shift
            self.__rows += num_rows_to_add
            self.insertRows(row_start_index, num_rows_to_add)
            top_left_index = self.index(row_start_index, 0)
            bottom_right_index = self.index(row_start_index + num_rows_to_add, self.__cols - 1)
            # noinspection PyUnresolvedReferences
            self.dataChanged.emit(top_left_index, bottom_right_index)

    def remove_rows(self, row_start_index: int, num_rows: int = 1):
        """
        Removes the selected rows.

        :param row_start_index: the row where the selection starts.
        :param num_rows: the number of contiguously selected rows.
        """

        del self.__data_cache[row_start_index:row_start_index + num_rows]

        # Inform the sheet view of the change
        self.__rows -= num_rows
        top_left_index = self.index(row_start_index, 0)
        bottom_right_index = self.index(row_start_index + num_rows, self.__cols - 1)
        self.removeRows(row_start_index, num_rows)
        # noinspection PyUnresolvedReferences
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def insert_columns(self, col_indexes_to_insert: List[int], where: InsertBeforeOrAfterEnum,
                       insert_after_selection: bool = True):
        """
        Inserts columns into the sheet before or after the given column index.
        :param col_indexes_to_insert: a list of column indexes to insert.
        :param where: indicates whether to insert before or after the col_index provided.
        :param insert_after_selection: indicates if the new columns should be inserted after or at the selected column.
        """

        # Handle 'Insert Before' button presses and 'Paste' Operations
        if where == InsertBeforeOrAfterEnum.before:

            # Re-generate all column headers from the insertion point forward
            num_cols_to_add = len(col_indexes_to_insert)
            start_idx = col_indexes_to_insert[0]
            end_idx = self.__cols + num_cols_to_add
            del self.__col_name_cache[start_idx:]

            # Shift the index of any custom-column name
            current_custom_cols = self.__custom_name_cache.copy().values()
            for col_to_shift in range(start_idx, end_idx):
                if col_to_shift in current_custom_cols:
                    for name, col_idx in self.__custom_name_cache.copy().items():
                        if col_idx == col_to_shift:
                            self.__custom_name_cache[name] = col_to_shift + num_cols_to_add

            # Insert the new column headers into the column header cache and data into the data cache
            for col in range(start_idx, end_idx):

                # Generate a new header
                set_name = get_col_header(col, self.__custom_name_cache, self.__index_style)
                self.__col_name_cache.insert(col, set_name)

                # Add row data to the sheet for the inserted column
                if col in range(start_idx, start_idx + num_cols_to_add):

                    # Enter '0' into new cells
                    for row in range(0, self.__rows):
                        row_data = self.__data_cache[row]
                        row_data.insert(col, 0)

            # Inform the sheet view of the change
            col_start_index = col_indexes_to_insert[0]
            self.__cols += num_cols_to_add
            self.insertColumns(col_start_index, num_cols_to_add)
            # noinspection PyUnresolvedReferences
            self.headerDataChanged.emit(Qt.Horizontal, col_start_index, col_start_index + num_cols_to_add - 1)

        else:  # Handle 'Insert After' button presses

            # Shift the indexes to the end of the selection
            shift = len(col_indexes_to_insert)
            if insert_after_selection:
                for idx, _ in enumerate(col_indexes_to_insert):
                    col_indexes_to_insert[idx] += shift

            # Re-generate all column headers from the insertion point forward
            num_cols_to_add = len(col_indexes_to_insert)
            start_idx = col_indexes_to_insert[0]
            end_idx = self.__cols + num_cols_to_add
            del self.__col_name_cache[start_idx:]

            # Regenerate the column headers into the column header cache
            for col in range(start_idx, end_idx):
                # Generate a new header
                set_name = get_col_header(col, self.__custom_name_cache, self.__index_style)
                self.__col_name_cache.insert(col, set_name)

            # Insert the new columns
            for col in col_indexes_to_insert:

                # Enter '0' into new cells
                for row in range(0, self.__rows):
                    row_data = self.__data_cache[row]
                    row_data.insert(col, 0)

            # Inform the sheet view of the change
            col_start_index = col_indexes_to_insert[0]
            num_cols_to_add = shift
            self.__cols += num_cols_to_add
            self.insertColumns(col_start_index, num_cols_to_add)
            # noinspection PyUnresolvedReferences
            self.headerDataChanged.emit(Qt.Horizontal, col_start_index, col_start_index + num_cols_to_add - 1)

    def remove_columns(self, col_start_index: int, num_cols: int = 1):
        """
        Cut the contiguously selected columns.

        :param col_start_index: the column where the selection starts.
        :param num_cols: the number of contiguously selected columns.
        """

        # Clear the header name from the cache
        del self.__col_name_cache[col_start_index:col_start_index + num_cols]

        # Clear the custom name from the cache and adjust indexes of affected custom columns
        for name, col_idx in self.__custom_name_cache.copy().items():
            if col_idx in range(col_start_index, col_start_index + num_cols):
                # Remove the custom-header
                del self.__custom_name_cache[name]
            elif col_idx >= col_start_index + num_cols:
                # If the custom-header is located at a higher index, adjust it to compensate for the removed columns
                self.__custom_name_cache[name] = col_idx - num_cols

        # Remove from data under each removed column from the data cache
        for row_index, record in enumerate(self.__data_cache):
            row_data = self.__data_cache[row_index]
            del row_data[col_start_index:col_start_index + num_cols]

        # Update the number of columns
        self.__cols -= num_cols

        # Re-generate column headers from the first column removed to the last header
        for col in range(col_start_index, self.__cols):
            set_name = get_col_header(col, self.__custom_name_cache, self.__index_style)
            self.__col_name_cache.insert(col, set_name)

        # Inform the sheet view of the change
        self.removeColumns(col_start_index, num_cols)
        # noinspection PyUnresolvedReferences
        self.headerDataChanged.emit(Qt.Horizontal, col_start_index, col_start_index + num_cols)

        # Refresh sheet
        top_left_index = self.index(0, 0)
        bottom_right_index = self.index(self.__rows - 1, self.__cols - 1)
        # noinspection PyUnresolvedReferences
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def update_cells(self, selected_cells: CellRangeIndices, values: List[List[Any]] = None):
        """
        Updates the selected cells to the specified values. If values is None, the cell value is cleared.

        :param selected_cells: the cell selection as a list of indexes: [[top-left], [bottom-right]
        :param values: new values to assign to the selected cells.
        """
        row_start = selected_cells[0][0]
        col_start = selected_cells[0][1]
        row_end = selected_cells[1][0]
        col_end = selected_cells[1][1]

        if values is None:
            # Iterate over the selected range and clear the current value
            for row_idx in range(row_start, row_end + 1):
                for col_idx in range(col_start, col_end + 1):
                    self.__data_cache[row_idx][col_idx] = 0

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
                    self.__data_cache[row_idx][col_idx] = cell
                    col_idx += 1
                row_idx += 1

        # Inform the sheet view of the change
        top_left_index = self.index(row_start, col_start)
        bottom_right_index = self.index(row_end, col_end)
        # noinspection PyUnresolvedReferences
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def cut_cells(self, selected_cells: CellRangeIndices):
        """
        Cut the contiguously selected cells. Cells are cleared but not removed from the sheet.

        :param selected_cells: the cell selection as a list of indexes: [[top-left], [bottom-right].
        """
        self.copy_cells(selected_cells)
        self.update_cells(selected_cells)

    def copy_cells(self, selected_cells: CellRangeIndices):
        """
        Copy of the contiguously selected cells.

        :param selected_cells: the cell selection as a list of indexes: [[top-left], [bottom-right].
        """
        self.__cells_copied = []

        row_start = selected_cells[0][0]
        row_end = selected_cells[1][0]
        col_start = selected_cells[0][1]
        col_end = selected_cells[1][1]

        # Python omits the last index so must + 1
        data_copied = [data_row[:] for data_row in self.__data_cache[row_start:row_end + 1]]

        for data_row in data_copied:
            data_subset = data_row[col_start:col_end + 1]  # Python omits the last index so must + 1
            self.__cells_copied.append(data_subset)

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

    def update_column_name(self, col_index: int, new_name: str):
        """
        Updates the column name to the new name provided.

        :param col_index: the column index of the column.
        :param new_name: the new name to set.
        """
        set_name = None
        set_custom_name = True
        default_col_header = excel_column_letter(col_index)

        if col_index in self.__custom_name_cache.values():
            # The name in the custom name cache has changed, delete it
            self.__delete_custom_name(col_index)

            # Check if it has been reset to the default Excel name
            name_comp = new_name.split(sep='-')
            if len(name_comp) == 1 and name_comp[0] == default_col_header:
                # The name has been restored to the default Excel column letter
                set_custom_name = False
                set_name = new_name[:self.__sheet_part.col_widths[col_index]]
            else:
                # A new custom name has been created, it will be added below
                pass

        elif new_name == default_col_header:
            # The new name is not in the custom names cache and it is the default, do nothing
            return

        if set_custom_name:
            # Add new name to cache
            self.__custom_name_cache[new_name] = col_index
            set_name = get_col_header(col_index, self.__custom_name_cache, self.__index_style)
            set_name = set_name[:self.__sheet_part.col_widths[col_index]]

        is_name_changed = self.setHeaderData(col_index, Qt.Horizontal, QVariant(set_name))

        if not is_name_changed:
            log.error('Column name did not update successfully.')

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    rows = property(get_rows)
    cols = property(get_cols)
    col_names = property(get_col_names)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __delete_custom_name(self, col_index):
        """
        Deletes the custom name from the cache of names given the column index.
        :param col_index: The column index corresponding to the name.
        """
        for name, index in self.__custom_name_cache.items():
            if col_index == index:
                del self.__custom_name_cache[name]
                return

    def __on_init_col_names(self, all_col_names: List[str], custom_names: {}):
        """
        Populate the column headers cache. If this is called as a result of an update, the caller must call
        headerDataChanged().
        :param all_col_names: name of each column
        :param custom_names: a dictionary of the column indexes with user-defined column names (keys)
        """
        self.__col_name_cache = all_col_names
        self.__custom_name_cache = custom_names
        self.__cols = len(all_col_names)
        self.sig_cols_changed.emit(self.__cols)

    def __on_init_sheet_data(self, sheet_data: List[List[Any]]):
        """
        Populate the sheet data cache. If this is called as a result of an update, the caller must call
        beginModelReset() first, and call endModelReset() after.
        :param sheet_data: the data delivered from the back-end Sheet Part
        """
        self.__data_cache = sheet_data
        self.__rows = len(sheet_data)
        self.sig_rows_changed.emit(self.__rows)

    def __on_index_style_changed(self, index_style: int):
        """
        Updates the index style attribute to correspond with the back-end sheet part.
        :param index_style: the sheet's column index style (excel or array)
        """
        self.__index_style = SheetIndexStyleEnum(index_style)

    __slot_on_index_style_changed = safe_slot(__on_index_style_changed)


class SheetPartEditorPanel(BaseContentEditor, SpecialValueDisplay):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 400
    INIT_HEIGHT = 600

    # noinspection PyUnresolvedReferences
    def __init__(self, part: SheetPart, parent: QWidget = None):
        """
        Initializes this panel with a back end Sheet Part and a parent QWidget.

        :param part: The Sheet Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        BaseContentEditor.__init__(self, part, parent)
        self.ui = Ui_SheetPartEditor()
        self.ui.setupUi(self)
        self.__sheet_part = part
        self.ui.sheet_view.setFont(get_scenario_font())

        self.__item_selected = None
        self.__is_row_selected = False
        self.__is_col_selected = False
        self.__is_general_selection = False
        self.__selected_rows = []
        self.__selected_cols = []
        self.__general_selection = []

        # Set table model and initialize sort, proxy, and selection models
        self.__sheet_model = SheetPartTableModelForEditing(part, parent)
        self.__selection_model = QItemSelectionModel(self.__sheet_model)
        self.ui.sheet_view.setModel(self.__sheet_model)
        self.ui.sheet_view.setSelectionModel(self.__selection_model)
        self.ui.sheet_view.setSelectionMode(QAbstractItemView.ContiguousSelection)
        self.__sheet_model.sig_rows_changed.connect(self.__slot_on_row_number_model_update)
        self.__sheet_model.sig_cols_changed.connect(self.__slot_on_column_number_model_update)
        self.__selection_model.currentChanged.connect(self.__slot_on_item_changed)
        self.__selection_model.selectionChanged.connect(self.__slot_on_selection_changed)

        # Set table header options and slots
        header = QHeaderView(Qt.Horizontal)
        header.setSectionsClickable(True)
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.ui.sheet_view.setHorizontalHeader(header)
        header.sectionDoubleClicked.connect(self.__slot_on_change_column_name)

        # Import/Export dialogs
        self.__import_dialog = None
        self.__export_dialog = None
        self.__last_sheet_import_path = None
        self.__last_sheet_export_path = None

        # Set button icons
        self.ui.insert_before_button.setIcon(QIcon(str(get_icon_path("insert_before.png"))))
        self.ui.insert_after_button.setIcon(QIcon(str(get_icon_path("insert_after.png"))))
        self.ui.select_all_button.setIcon(QIcon(str(get_icon_path("select_all.png"))))
        self.ui.cut_button.setIcon(QIcon(str(get_icon_path("cut.png"))))
        self.ui.copy_button.setIcon(QIcon(str(get_icon_path("copy.png"))))
        self.ui.paste_button.setIcon(QIcon(str(get_icon_path("paste.png"))))
        self.ui.del_button.setIcon(QIcon(str(get_icon_path("delete.png"))))
        self.ui.import_sheet_button.setIcon(QIcon(str(get_icon_path("import.png"))))
        self.ui.export_sheet_button.setIcon(QIcon(str(get_icon_path("export.png"))))

        # Disabled buttons
        self.__toggle_enabled_edit_buttons(False, False)

        # Connect button slots
        self.ui.insert_before_button.clicked.connect(self.__slot_insert_before)
        self.ui.insert_after_button.clicked.connect(self.__slot_insert_after)
        self.ui.select_all_button.clicked.connect(self.__slot_select_all)
        self.ui.cut_button.clicked.connect(self.__slot_cut)
        self.ui.copy_button.clicked.connect(self.__slot_copy)
        self.ui.paste_button.clicked.connect(self.__slot_paste)
        self.ui.del_button.clicked.connect(self.__slot_delete)
        self.ui.import_sheet_button.clicked.connect(self.__slot_import_sheet)
        self.ui.export_sheet_button.clicked.connect(self.__slot_export_sheet)
        self.ui.change_row_count_spin_box.editingFinished.connect(self.__slot_on_row_spinbox_edit)
        self.ui.change_column_count_spin_box.editingFinished.connect(self.__slot_on_column_spinbox_edit)

        self.ui.sheet_view.doubleClicked.connect(self.__slot_prepare_for_cell_editing)

        self.__special_cell_index = QModelIndex()

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.insert_before_button,
                     self.ui.insert_after_button,
                     self.ui.select_all_button,
                     self.ui.cut_button,
                     self.ui.copy_button,
                     self.ui.paste_button,
                     self.ui.del_button,
                     self.ui.import_sheet_button,
                     self.ui.export_sheet_button,
                     self.ui.change_row_count_spin_box,
                     self.ui.change_column_count_spin_box]
        return tab_order

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Gets the GUI sheet data for submission to the back-end when changes in the editor have been completed.

        :returns: The data for submission
        """
        data_dict = dict()
        self.__sheet_model.fill_data_for_submission(data_dict)
        return self._get_deepcopy(data_dict)

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        self.__sheet_model.init_model(data)

    @override(SpecialValueDisplay)
    def _get_special_value(self) -> object:
        return self.__sheet_model.get_cell(self.__special_cell_index)

    @override(SpecialValueDisplay)
    def _set_special_value(self, val: Any):
        return self.__sheet_model.set_cell(self.__special_cell_index, val)

    @override(BaseContentEditor)
    def _get_custom_deepcopy(self, src_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep-copy the data from the source dictionary to the destination dictionary. If the sheet data has "bad"
        values such as the return value of open(), the values will be added to the destination dictionary without
        deep-copy.

        :param src_data: The source dictionary to be copied from.
        :return The deep-copied data
        """
        destination_data = dict()
        for key, val in src_data.items():
            if key == "sheet_data":
                new_grid_data = list()
                for row_index, row in enumerate(val):
                    a_row = list()
                    for col_index, value in enumerate(row):
                        try:
                            # Tests this value. If it can be copied, we leave it intact
                            a_row.append(deepcopy(value))
                        except:
                            a_row.append(value)

                    new_grid_data.append(a_row)

            else:
                destination_data[key] = deepcopy(val)

        destination_data['sheet_data'] = new_grid_data
        return destination_data

    def __toggle_enabled_edit_buttons(self, enable: bool = True, enable_insert: bool = True):
        """
        Enables or disables the edit buttons on the sheet widget.

        :param enable: True enable to False to disable. Flag for all edit buttons but 'insert'.
        :param enable_insert: True enable to False to disable. Flag for 'insert' edit buttons.
        """
        self.ui.insert_before_button.setEnabled(enable_insert)
        self.ui.insert_after_button.setEnabled(enable_insert)
        self.ui.cut_button.setEnabled(enable)
        self.ui.copy_button.setEnabled(enable)
        self.ui.paste_button.setEnabled(enable)
        self.ui.del_button.setEnabled(enable)

    def __on_item_changed(self, current_item: QModelIndex, unused: QModelIndex):
        """
        Triggered when the selected item in the sheet changes.

        :param current_item: the model index of the selected item.
        :param unused: the model index of the deselected item (not used).
        """
        del unused
        self.__item_selected = current_item

    def __on_selection_changed(self, unused1: QItemSelection, unused2: QItemSelection):
        """
        Triggered when the selection in the sheet changes.

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

        top_row, bottom_row, left_col, right_col = self.__find_selection_range()
        self.__toggle_enabled_edit_buttons()

        # If whole rows or columns are selected, act on those;
        # otherwise, act on the general selection of highlight cells if one has been made
        if len(self.__selected_rows) == 1 and len(self.__selected_cols) > 1:
            # Row selection: case where whole row is selected in a table with one row (so all columns are selected too)
            self.__is_row_selected = True

        elif len(self.__selected_rows) > 0 and len(self.__selected_cols) == 0:
            # Row selection: case where multiple rows are selected in a table with more than one row
            self.__is_row_selected = True

        elif len(self.__selected_cols) == 1 and len(self.__selected_rows) > 1:
            # Column selection: case where whole column is selected in a table with one column (so all rows are
            # selected too)
            self.__is_col_selected = True
            self.__sorted_column = [self.__selected_cols[0]]

        elif len(self.__selected_cols) > 0 and len(self.__selected_rows) == 0:
            # Column selection: case where multiple columns are selected in a table with more than one column
            self.__is_col_selected = True
            self.__sorted_column = [self.__selected_cols[0]]
            self.__sorted_column_changed = True
        else:
            # No complete row or column selected
            self.__toggle_enabled_edit_buttons(enable_insert=False)

        # Check for any general selection: full or partial row or column selections
        if self.__selection_model.hasSelection():
            # General selection
            self.__general_selection = [[top_row, left_col], [bottom_row, right_col]]
            self.__is_general_selection = True
        else:
            # No valid selection
            self.__toggle_enabled_edit_buttons(False, False)

    def __find_selection_range(self) -> List[int]:
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

        # Find the top-left and bottom-right of the selection
        # Also determine if a complete row or column is selected
        for index in self.__selection_model.selectedIndexes():
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
            if self.__selection_model.isRowSelected(row, parent):
                if row not in self.__selected_rows:
                    self.__selected_rows.append(row)

            # Check for complete column selection
            if self.__selection_model.isColumnSelected(col, parent):
                if col not in self.__selected_cols:
                    self.__selected_cols.append(col)

        return [top_row, bottom_row, left_col, right_col]

    # noinspection PyUnresolvedReferences
    def __insert_before(self):
        """
        Inserts a row or column before the selected row or column.
        """

        if self.__is_row_selected and not self.__is_col_selected:

            # Insert the row before the selected row and update the selection
            self.__sheet_model.insert_rows(self.__selected_rows, InsertBeforeOrAfterEnum.before)
            moved_index = self.__sheet_model.index(self.__selected_rows[0] + 1, 0)
            orig_index = self.__sheet_model.index(self.__selected_rows[0], 0)

        elif self.__is_col_selected and not self.__is_row_selected:

            # Insert the column before the selected column and update the selection
            self.__sheet_model.insert_columns(self.__selected_cols, InsertBeforeOrAfterEnum.before)
            moved_index = self.__sheet_model.index(0, self.__selected_cols[0] + 1)
            orig_index = self.__sheet_model.index(0, self.__selected_cols[0])

        else:
            # Either both a row and a column are selected (a block or rows and columns) or neither are selected. In the
            # former case, insert before cannot determine what to insert (row or column?) before the block of selected
            # rows and columns. In the latter case, insert before is not valid since no row or column is selected.
            return

        self.__selection_model.currentChanged.emit(moved_index, orig_index)
        self.__selection_model.selectionChanged.emit(self.__selection_model.selection(),
                                                     self.__selection_model.selection())

    # noinspection PyUnresolvedReferences
    def __insert_after(self):
        """
        Inserts a row or column after the selected row or column.
        """

        if self.__is_row_selected:

            # Insert the row after the selected row and update the selection
            self.__sheet_model.insert_rows(self.__selected_rows, InsertBeforeOrAfterEnum.after)
            moved_index = self.__sheet_model.index(self.__selected_rows[0], 0)
            orig_index = self.__sheet_model.index(self.__selected_rows[0], 0)

        elif self.__is_col_selected:
            # Insert the column after the selected column and update the selection
            self.__sheet_model.insert_columns(self.__selected_cols, InsertBeforeOrAfterEnum.after)
            moved_index = self.__sheet_model.index(0, self.__selected_cols[0])
            orig_index = self.__sheet_model.index(0, self.__selected_cols[0])

        else:
            # Either both a row and a column are selected (a block or rows and columns) or neither are selected. In the
            # former case, insert after cannot determine what to insert (row or column?) after the block of selected
            # rows and columns. In the latter case, insert after is not valid since no row or column is selected.
            return

        self.__selection_model.currentChanged.emit(moved_index, orig_index)
        self.__selection_model.selectionChanged.emit(self.__selection_model.selection(),
                                                     self.__selection_model.selection())

    def __select_all(self):
        """
        Selects all rows, if any.
        """
        self.ui.sheet_view.selectAll()

    def __cut(self):
        """
        Cuts the contents of the selected cells. If nothing is selected, this function does nothing.
        """
        if self.__is_general_selection:
            self.__sheet_model.cut_cells(self.__general_selection)

    def __copy(self):
        """
        Copies the contents of the selected cells. If nothing is selected, this function does nothing.
        """
        if self.__is_general_selection:
            self.__sheet_model.copy_cells(self.__general_selection)

    def __paste(self):
        """
        Pastes the previously copied data.
        """
        if self.__is_general_selection:
            self.__sheet_model.paste_cells(self.__general_selection)

    def __delete(self):
        """
        Deletes the contents of the selected cells. If nothing is selected, this function does nothing.
        """

        if self.__is_row_selected:
            self.__sheet_model.remove_rows(self.__selected_rows[0], len(self.__selected_rows))

        elif self.__is_col_selected:
            self.__sheet_model.remove_columns(self.__selected_cols[0], len(self.__selected_cols))

        elif self.__is_general_selection:
            self.__sheet_model.update_cells(self.__general_selection)

    def __on_change_column_name(self, col_index: int):
        """
        Launches the field name update dialog when the column is double-clicked.

        :param col_index: the index of the column to update.
        """
        current_name = self.__sheet_model.headerData(col_index, Qt.Horizontal)
        new_name, ok = QInputDialog.getText(self.parent(), 'Edit Field Name', 'Name:', QLineEdit.Normal, current_name)

        if ok:
            try:
                validate_python_name(new_name)
                self.__sheet_model.update_column_name(col_index, new_name)
            except Exception as exc:
                msg_title = 'Python Name Error'
                error_msg = str(exc)
                exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
                log.error('{}: {}', msg_title, error_msg)

    def __on_row_number_changed_by_model(self, new_number_of_rows: int):
        """
        Changes the value in the row setting spin-box to the number of current rows in the sheet editor.
        :param new_number_of_rows: the changed number of rows.
        """
        self.ui.change_row_count_spin_box.setValue(new_number_of_rows)

    def __on_column_number_changed_by_model(self, new_number_of_cols: int):
        """
        Changes the value in the column setting spin-box to the number of current columns in the sheet editor.
        :param new_number_of_cols: the changed number of columns.
        """
        self.ui.change_column_count_spin_box.setValue(new_number_of_cols)

    def __on_row_spinbox_edit(self, new_number_of_rows: int = None):
        """
        Updates the number of rows by either appending rows to, or removing rows from, the end of the sheet.
        This method is connected to the spinbox's editingFinished signal that updates the model only when the spinbox
        loses focus or enter is pressed.
        :param new_number_of_rows: The number of rows typed or incremented into the spinbox.
        """
        if new_number_of_rows is None:
            new_number_of_rows = self.ui.change_row_count_spin_box.value()

        current_number_of_rows = self.__sheet_model.rows

        if new_number_of_rows < current_number_of_rows:

            num_to_remove = current_number_of_rows - new_number_of_rows
            start_index = current_number_of_rows - num_to_remove
            self.__sheet_model.remove_rows(start_index, num_to_remove)

        elif new_number_of_rows > current_number_of_rows:

            # Add a column before adding a row if there are none
            if self.__sheet_model.cols == 0:
                self.__on_column_spinbox_edit(1)

            num_to_add = new_number_of_rows - current_number_of_rows
            start_index = current_number_of_rows
            row_insert_indexes = []
            for index in range(start_index, start_index + num_to_add):
                row_insert_indexes.append(index)
            self.__sheet_model.insert_rows(row_insert_indexes, InsertBeforeOrAfterEnum.after,
                                           insert_after_selection=False)

    def __on_column_spinbox_edit(self, new_number_of_columns: int = None):
        """
        Updates the number of columns by either appending columns to, or removing columns from, the end of the sheet.
        This method is connected to the spinbox's editingFinished signal that updates the model only when the spinbox
        loses focus or enter is pressed.
        :param new_number_of_columns: The number of columns typed or incremented into the spinbox.
        """
        if new_number_of_columns is None:
            new_number_of_columns = self.ui.change_column_count_spin_box.value()

        current_number_of_cols = self.__sheet_model.cols

        if new_number_of_columns < current_number_of_cols:

            num_to_remove = current_number_of_cols - new_number_of_columns
            start_index = current_number_of_cols - num_to_remove
            self.__sheet_model.remove_columns(start_index, num_to_remove)

        elif new_number_of_columns > current_number_of_cols:

            num_to_add = new_number_of_columns - current_number_of_cols
            start_index = current_number_of_cols
            col_insert_indexes = []
            col_names = []
            for index in range(start_index, start_index + num_to_add):
                col_insert_indexes.append(index)
                col_names.append('NewCol{}'.format(index))
            self.__sheet_model.insert_columns(col_insert_indexes, InsertBeforeOrAfterEnum.after,
                                              insert_after_selection=False)

    def __launch_import_dialog(self):
        """
        Launches the sheet import dialog to import data from an Excel spreadsheet.
        """
        if self.__import_dialog is None:
            self.__import_dialog = ImportExcelDialog(self.__sheet_part,
                                                     last_sheet_import_path=self.__last_sheet_import_path,
                                                     sheet_editor=self)

        import_in_progress = True
        while import_in_progress:
            answer = self.__import_dialog.exec()
            if answer:
                excel_path, excel_sheet, excel_range = self.__import_dialog.get_user_input()
                success = self.__process_excel_import(excel_path, excel_sheet, excel_range)
                import_in_progress = not success  # stay 'in progress' if import not successful
            else:
                # cancelled
                import_in_progress = False

        self.__import_dialog = None  # reset for fresh dialog on next launch

    def __process_excel_import(self, excel_path: str, excel_sheet: str, excel_range: str) -> bool:
        """
        Imports the selected Excel spreadsheet into the this sheet editor's table data for editing. Data is pushed to
        the back-end when OK | Apply are pressed.
        :param excel_path: the path to the Excel file.
        :param excel_sheet: the name of the sheet in the spreadsheet.
        :param excel_range: the range of cells to import: e.g. "B1:E5".
        :returns: a boolean flag indicating if the import was successful.
        """
        self.__last_sheet_import_path = excel_path

        try:
            sheet_data = read_from_excel(excel_path, excel_sheet, excel_range)
        except Exception as excel_error:
            on_excel_error("Sheet Import Error", excel_error)
            return False

        custom_headers = {}
        data = dict(name=self.__sheet_part.part_frame.name)
        data['sheet_data'] = sheet_data
        data['custom_col_names'] = custom_headers
        data['all_col_names'] = [get_col_header(col, custom_headers, SheetIndexStyleEnum.excel)
                                 for col in range(0, len(sheet_data[0]))]
        self._on_data_arrived(data)
        return True

    def __launch_export_dialog(self):
        """
        Launches the sheet export dialog to export data to an Excel spreadsheet.
        """
        if self.__export_dialog is None:
            self.__export_dialog = ExportExcelDialog(self.__sheet_part,
                                                     last_sheet_export_path=self.__last_sheet_export_path,
                                                     sheet_editor=self)

        export_in_progress = True
        while export_in_progress:
            answer = self.__export_dialog.exec()
            if answer:
                excel_path, excel_sheet, excel_range = self.__export_dialog.get_user_input()
                success = self.__process_excel_export(excel_path, excel_sheet, excel_range)
                export_in_progress = not success  # stay 'in progress' if export not successful
            else:
                # cancelled
                export_in_progress = False

        self.__export_dialog = None  # reset for fresh dialog on next launch

    def __process_excel_export(self, excel_path: str, excel_sheet: str, excel_range: str) -> bool:
        """
        Exports the sheet data from the editor to the selected Excel spreadsheet.
        :param excel_path: the path to the Excel file.
        :param excel_sheet: the name of the sheet in the spreadsheet.
        :param excel_range: the range of cells to import: e.g. "B1:E5".
        :returns: a boolean flag indicating if the export was successful.
        """
        self.__last_sheet_export_path = excel_path
        data = self._get_data_for_submission()

        try:
            write_to_excel(data['sheet_data'], excel_path, excel_sheet, excel_range)
        except Exception as excel_error:
            on_excel_error("Sheet Export Error", excel_error)
            return False

        return True

    def __prepare_for_cell_editing(self, index: QModelIndex):
        """
        Opens the Special Value Editor in response to a double-click at the given index if the value at the index is
        not representable.
        :param index: The index of the cell
        """
        self.__special_cell_index = index
        self._open_special_value_editor()

    __slot_prepare_for_cell_editing = safe_slot(__prepare_for_cell_editing)
    __slot_on_item_changed = safe_slot(__on_item_changed)
    __slot_on_selection_changed = safe_slot(__on_selection_changed)

    __slot_on_change_column_name = safe_slot(__on_change_column_name)

    __slot_insert_before = safe_slot(__insert_before)
    __slot_insert_after = safe_slot(__insert_after)
    __slot_select_all = safe_slot(__select_all)
    __slot_cut = safe_slot(__cut)
    __slot_copy = safe_slot(__copy)
    __slot_paste = safe_slot(__paste)
    __slot_delete = safe_slot(__delete)

    __slot_import_sheet = safe_slot(__launch_import_dialog)
    __slot_export_sheet = safe_slot(__launch_export_dialog)

    __slot_on_row_number_model_update = safe_slot(__on_row_number_changed_by_model)
    __slot_on_column_number_model_update = safe_slot(__on_column_number_changed_by_model)
    __slot_on_row_spinbox_edit = safe_slot(__on_row_spinbox_edit, arg_types=())
    __slot_on_column_spinbox_edit = safe_slot(__on_column_spinbox_edit, arg_types=())


register_part_editor_class(ori.OriSheetPartKeys.PART_TYPE_SHEET, SheetPartEditorPanel)
