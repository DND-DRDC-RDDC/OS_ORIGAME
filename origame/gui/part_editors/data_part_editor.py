# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Data Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum
from collections import OrderedDict
from copy import deepcopy

# [2. third-party]
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QItemSelection, QItemSelectionModel
from PyQt5.QtCore import Qt, QCoreApplication, QVariant
from PyQt5.QtWidgets import QAbstractItemView, QMessageBox, QHeaderView, QWidget
from PyQt5.QtGui import QIcon

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core import override, utils
from ...scenario.defn_parts import DataPart, DisplayOrderEnum
from ...scenario import ori

from .. import gui_utils
from ..gui_utils import PyExpr, get_scenario_font
from ..safe_slot import safe_slot

from .scenario_part_editor import BaseContentEditor, DataSubmissionValidationError, SortFilterProxyModelByColumns
from .Ui_data_part_editor import Ui_DataPartEditorWidget
from .part_editors_registry import register_part_editor_class
from .special_value_editor import SpecialValueDisplay

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'DataPartEditorPanel',
    'DataPartTableModelForEditing'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

class FieldIndexEnum(IntEnum):
    """
    Enumerate field indices in a data record.
    """
    idx_key, idx_value = range(2)


# PyMethodOverriding,PyUnresolvedReferences
class DataPartTableModelForEditing(QAbstractTableModel):
    """
    Implements a Table Model for getting and setting data part data.
    """

    # The first column at index 0 is used to select the row, the second and third columns (index 1 and 2) are used
    # to display the data key and value.
    COL_KEY_INDEX = 1
    COL_VALUE_INDEX = COL_KEY_INDEX + 1
    NUM_COLUMN = 3
    SORTED_ON = [COL_KEY_INDEX]

    def __init__(self, parent: QWidget = None):
        """
        Initializes this model with a parent QWidget. Note the data are populated with the init_model().

        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(parent)
        self.__records = list()
        self.__records_copied = list()
        self.__display_order = DisplayOrderEnum.of_creation
        self.__header = [QVariant(''), QVariant('Key'), QVariant('Value')]

    def init_model(self, data: Dict[str, Any]):
        self.beginResetModel()
        self.__records = list()
        self.__records_copied = list()
        self.__display_order = data['display_order']
        ordered_dict = data['_data']
        for x in ordered_dict:
            self.__records.append((x, PyExpr(ordered_dict[x])))
        self.endResetModel()

    def get_cell(self, index: QModelIndex) -> PyExpr:
        """
        Gets the PyExpr object from the internal data table.
        :param index: Note the index.column() will not be used because the column must be
        FieldIndexEnum.idx_value.value.
        :return: The PyExpr object.
        """
        return self.__records[index.row()][FieldIndexEnum.idx_value.value]

    def set_cell(self, index: QModelIndex, val: PyExpr):
        """
        Sets the PyExpr object to the internal data table.
        :param index: Note the index.column() will not be used because the column must be
        FieldIndexEnum.idx_key.value.
        :param val: The PyExpr object
        """
        self.__records[index.row()] = (self.__records[index.row()][FieldIndexEnum.idx_key.value], val)

    def fill_data_for_submission(self, data_dict: Dict[str, Any]):
        part_data = OrderedDict()
        for x in self.__records:
            part_data[x[FieldIndexEnum.idx_key.value]] = x[FieldIndexEnum.idx_value.value].obj
        data_dict['display_order'] = self.__display_order
        data_dict['_data'] = part_data

    @override(QAbstractTableModel)
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> QVariant:
        """
        Returns the data for the given role and section in the header with the specified orientation.
        :param section: the row number
        :param orientation: horizontal
        :param role: the role of the data - display in this instance
        :return: a QVariant containing the header data item requested
        """
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section in range(DataPartTableModelForEditing.NUM_COLUMN):
                return self.__header[section]

    @override(QAbstractTableModel)
    def setHeaderData(self, section: int, orientation: Qt.Orientation, value: QVariant, role=Qt.EditRole) -> bool:
        """
        Sets the data for the given role and section in the header with the specified orientation to the value supplied.
        :param section: the row number
        :param orientation: horizontal
        :param value: a QVariant containing the new header data
        :param role: the role of the data - display in this instance
        :return: returns true if the header's data was updated; otherwise returns false.
        """
        if role != Qt.EditRole or orientation != Qt.Horizontal:
            return False

        if section in range(DataPartTableModelForEditing.NUM_COLUMN):
            self.__header[section] = value
            self.headerDataChanged.emit(orientation, section, section)
            return True
        else:
            return False

    @override(QAbstractTableModel)
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of rows under the given parent table object.

        Since the table model has only a single parent index (the root index), then this method will return the total
        number of rows only if QModelIndex is invalid (i.e. the parent index). Otherwise, if a child index has been
        provided (a valid index) zero will be returned.
        :param parent: the QModelIndex of the root table object (all other indexes are children -> table elements)
        :return: the number of rows
        """
        if parent.isValid():
            return 0

        return len(self.__records)

    @override(QAbstractTableModel)
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of columns under the given parent table object.

        Since the table model has only a single parent index (the root index), then this method will return the total
        number of columns (always 2) only if QModelIndex is invalid (i.e. the parent index). Otherwise, if a child
        index has been provided (a valid index) zero will be returned.
        :param parent: the QModelIndex of the root table object (all other indexes are children -> table elements)
        :return: the number of columns
        """
        if parent.isValid():
            return 0
        return DataPartTableModelForEditing.NUM_COLUMN

    @override(QAbstractTableModel)
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> str:
        """
        Returns the data identified by the index from the back-end data part.

        The indexes row value is assumed to correspond to the values position in the data parts dictionary of values
        in the back-end.
        Note: If you do not have a value to return, return an invalid QVariant instead of returning 0.
        :param index: an data item to display in the table view
        :param role: the data role (default Qt.DisplayRole)
        :return: The indexed data from the back-end part
        """
        if not index.isValid():
            return QVariant()

        col = index.column()
        row = index.row()

        if col > (DataPartTableModelForEditing.NUM_COLUMN - 1):
            return QVariant()

        if role == Qt.DisplayRole or role == Qt.EditRole:
            try:
                if col == DataPartTableModelForEditing.COL_KEY_INDEX:
                    return QVariant(self.__records[row][FieldIndexEnum.idx_key.value])
                elif col == DataPartTableModelForEditing.COL_VALUE_INDEX:
                    return str(self.__records[row][FieldIndexEnum.idx_value.value])
                else:
                    return QVariant()
            except IndexError:
                return QVariant()

        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.ToolTipRole:
            if col == DataPartTableModelForEditing.COL_VALUE_INDEX:
                return self.__records[row][FieldIndexEnum.idx_value.value].get_edit_tooltip()

        return QVariant()

    @override(QAbstractTableModel)
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Returns the item flags for the given index.
        This method returns Qt.ItemIsEnabled if the column is the 'Value' column and Qt.NoItemFlags,
        otherwise. This set-up causes data part to display the data in a similar way to the Prototype. The keys listed
        in the 'Key' column to appear greyed out while the values in the 'Value' column appear in normal black text.
        :param index: the index corresponding to the table item
        :return: a Qt item flag (integer value)
        """
        if not index.isValid():
            return Qt.NoItemFlags

        col = index.column()

        if col == 0:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled
        elif col == DataPartTableModelForEditing.COL_KEY_INDEX:
            return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled

        assert col == DataPartTableModelForEditing.COL_VALUE_INDEX
        # This must be the value column

        val_wrapper = self.__records[index.row()][FieldIndexEnum.idx_value]
        if val_wrapper.is_representable():
            return Qt.ItemIsSelectable | Qt.ItemIsEditable | Qt.ItemIsEnabled
        else:
            return Qt.ItemIsSelectable | Qt.ItemIsEnabled

    @override(QAbstractTableModel)
    def insertColumns(self, insert_at_col: int, num_columns: int, parent=QModelIndex()) -> bool:
        """No column insertion"""
        return False

    @override(QAbstractTableModel)
    def removeColumns(self, remove_at_col: int, num_columns: int, parent=QModelIndex()) -> bool:
        """No column removal"""
        return False

    @override(QAbstractTableModel)
    def insertRows(self, insert_at_row: int, num_rows: int = 1, parent=QModelIndex()) -> bool:
        """
        Inserts num_rows rows into the model before the given row, insert_at_row.

        Items in the new row will be children of the item represented by the parent model index.
        If insert_at_row is 0, the rows are prepended to any existing rows in the parent.
        If insert_at_row is rowCount(), the rows are appended to any existing rows in the parent.
        If parent has no children, a single column with num_rows rows is inserted.

        :param insert_at_row: first row to insert
        :param num_rows: total rows to insert (default set to one row)
        :param parent: parent index
        :return: returns true if the rows were successfully inserted; otherwise returns false.
        """
        self.beginInsertRows(parent, insert_at_row, insert_at_row + num_rows - 1)
        for i in range(insert_at_row, insert_at_row + num_rows):
            self.__records.insert(i, ('', PyExpr()))
        self.endInsertRows()
        return True

    @override(QAbstractTableModel)
    def removeRows(self, remove_at_row: int, num_rows: int = 1, parent=QModelIndex()) -> bool:
        """
        Removes num_rows rows starting with the given row, remove_at_row, under parent index from the model.
        :param remove_at_row: first row to remove
        :param num_rows: total rows to remove (default set to one row)
        :param parent: parent index
        :return: returns true if the rows were successfully removed; otherwise returns false.
        """
        if remove_at_row < 0:
            return False
        first = remove_at_row
        last = remove_at_row + num_rows - 1
        self.beginRemoveRows(parent, first, last)

        del self.__records[remove_at_row:remove_at_row + num_rows]

        self.endRemoveRows()
        return True

    @override(QAbstractTableModel)
    def moveRows(self,
                 source_parent: QModelIndex, source_row: int,
                 num_rows: int,
                 destination_parent: QModelIndex, destination_child: int) -> bool:
        """
        :param source_parent: See the QAbstractTableModel.
        :param source_row: See the QAbstractTableModel.
        :param num_rows: See the QAbstractTableModel.
        :param destination_parent: See the QAbstractTableModel.
        :param destination_child: See the QAbstractTableModel.
        :return: returns true if the rows were successfully moved; otherwise returns false.
        """
        first = source_row
        last = source_row + num_rows - 1

        self.beginMoveRows(source_parent, first, last, destination_parent, destination_child)

        # The objective is to swap the part2 and part3
        if destination_child < source_row:
            # Up
            part1 = self.__records[0: destination_child]
            part2 = self.__records[destination_child: source_row]
            part3 = self.__records[source_row: source_row + num_rows]
            part4 = self.__records[source_row + num_rows:]
        else:
            # Down
            part1 = self.__records[0: source_row]
            part2 = self.__records[source_row: source_row + num_rows]
            part3 = self.__records[source_row + num_rows: destination_child]
            part4 = self.__records[destination_child:]
        self.__records = part1 + part3 + part2 + part4

        self.endMoveRows()
        return True

    @override(QAbstractTableModel)
    def setData(self, model_index: QModelIndex, value: QVariant, role: int = Qt.EditRole):
        """
        Sets data from the data part editor.

        Sets the role data for the item at index to value.
        Returns true if successful; otherwise returns false.
        The dataChanged() signal should be emitted if the data was successfully set.
        The base class implementation returns false. This function and data() must be reimplemented for editable models.
        :param model_index: a QModelIndex for the item being changed.
        :param value: the new value to set.
        :param role: the data role (default Qt.EditRole)
        :return: returns true if successful; otherwise returns false.
        """
        row = model_index.row()
        col = model_index.column()

        if col == DataPartTableModelForEditing.COL_KEY_INDEX:
            # The user wants to change the key
            self.__records[row] = (str(value), self.__records[row][FieldIndexEnum.idx_value.value])
        elif col == DataPartTableModelForEditing.COL_VALUE_INDEX:
            # The user wants to change the value.
            try:
                obj_value = eval(value)
            except:
                # Do nothing: the string object 'value' cannot be evaluated as a Python expression -> leave as string
                obj_value = value
            self.__records[row] = (self.__records[row][FieldIndexEnum.idx_key.value], PyExpr(obj_value))

        self.dataChanged.emit(model_index, model_index, [role])
        return True

    def cut_selection(self, start_row: int, num_rows: int = 1):
        """
        Cut the contiguously selected rows.

        :param start_row: The row where the selection starts.
        :param num_rows: The number of contiguously selected rows.
        """
        self.copy_selection(start_row, num_rows)
        self.removeRows(start_row, num_rows)

    def copy_selection(self, start_row: int, num_rows: int = 1):
        """
        Keep a copy of the contiguously selected rows.

        :param start_row: The row where the selection starts.
        :param num_rows: The number of contiguously selected rows.
        """
        self.__records_copied = self.__records[start_row:start_row + num_rows]

    def paste_selection(self, insert_at_row: int):
        """
        Paste the previously cut or copied selection before the row specified by the "at_this_row". If the
        "at_this_row" is negative - no rows being selected, past the selection at the bottom.

        :param insert_at_row: The row where the paste happens.
        """
        first = insert_at_row
        last = first + len(self.__records_copied) - 1

        self.beginInsertRows(QModelIndex(), first, last)
        self.__records = self.__records[0:first] + self.__records_copied + self.__records[first:]
        self.endInsertRows()

    def get_display_order(self):
        """

        """
        return self.__display_order

    def set_display_order(self, display_order: DisplayOrderEnum):
        """

        :param display_order: The display order currently selected by the user
        """
        # During the editing, the display order can be converted back and forth between int and DisplayOrderEnum.
        # But the back end data part requires DisplayOrderEnum type. So, we make sure it has the right type here.
        self.__display_order = DisplayOrderEnum(display_order)

    def get_problem_keys(self) -> List[str]:
        """
        Retrieve the duplicated keys, invalid keys or both.
        :returns a list of the duplicated keys, invalid keys or both. It shall be empty if nothing is wrong.
        """
        # If the keys are not unique, we will not save the changes. Instead, we will prompt the user to correct the
        # data
        already_used = set()
        invalid_names = list()
        for x in self.__records:
            raw_key = str(x[FieldIndexEnum.idx_key.value])
            if len(raw_key) > 0:
                correct_key = utils.get_valid_python_name(raw_key)
                if raw_key == correct_key:
                    if raw_key in already_used:
                        invalid_names.append(raw_key)
                    else:
                        already_used.add(raw_key)
                else:
                    invalid_names.append(raw_key)
            else:
                invalid_names.append(raw_key)

        return invalid_names

    display_order = property(get_display_order, set_display_order)


class DataPartEditorPanel(BaseContentEditor, SpecialValueDisplay):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    NO_SORT = -1

    # The initial size to make this editor look nice.
    INIT_WIDTH = 400
    INIT_HEIGHT = 600

    def __init__(self, part: DataPart, parent: QWidget = None):
        """
        Initializes this panel with a back end Data Part and a parent QWidget.

        :param part: The Data Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_DataPartEditorWidget()
        self.ui.setupUi(self)

        self._sort_order = DataPartEditorPanel.NO_SORT
        self.ui.tableView.setFont(get_scenario_font())
        self.ui.tableView.horizontalHeader().sectionClicked.connect(self._slot_section_clicked)
        self._data_model = DataPartTableModelForEditing(parent)
        self._data_model.modelReset.connect(self._slot_model_reset)

        self.ui.tableView.setSelectionMode(QAbstractItemView.ContiguousSelection)

        self.ui.insert_before_button.setText("")
        self.ui.insert_after_button.setText("")
        self.ui.select_all_button.setText("")
        self.ui.cut_button.setText("")
        self.ui.copy_button.setText("")
        self.ui.paste_button.setText("")
        self.ui.del_button.setText("")
        self.ui.move_up_button.setText("")
        self.ui.move_down_button.setText("")

        self.ui.insert_before_button.setIcon(QIcon(str(gui_utils.get_icon_path("insert_row_before.png"))))
        self.ui.insert_after_button.setIcon(QIcon(str(gui_utils.get_icon_path("insert_row_after.png"))))
        self.ui.select_all_button.setIcon(QIcon(str(gui_utils.get_icon_path("select_all.png"))))
        self.ui.cut_button.setIcon(QIcon(str(gui_utils.get_icon_path("cut.png"))))
        self.ui.copy_button.setIcon(QIcon(str(gui_utils.get_icon_path("copy.png"))))
        self.ui.paste_button.setIcon(QIcon(str(gui_utils.get_icon_path("paste.png"))))
        self.ui.del_button.setIcon(QIcon(str(gui_utils.get_icon_path("delete.png"))))
        self.ui.move_up_button.setIcon(QIcon(str(gui_utils.get_icon_path("arrow_up.png"))))
        self.ui.move_down_button.setIcon(QIcon(str(gui_utils.get_icon_path("arrow_down.png"))))

        _translate = QCoreApplication.translate
        self.ui.insert_before_button.setToolTip(_translate("DataPartEditorPanel", "Insert Before"))
        self.ui.insert_after_button.setToolTip(_translate("DataPartEditorPanel", "Insert After"))
        self.ui.select_all_button.setToolTip(_translate("DataPartEditorPanel", "Select All"))
        self.ui.cut_button.setToolTip(_translate("DataPartEditorPanel", "Cut"))
        self.ui.copy_button.setToolTip(_translate("DataPartEditorPanel", "Copy"))
        self.ui.paste_button.setToolTip(_translate("DataPartEditorPanel", "Paste"))
        self.ui.del_button.setToolTip(_translate("DataPartEditorPanel", "Delete"))
        self.ui.move_up_button.setToolTip(_translate("DataPartEditorPanel", "Move Up"))
        self.ui.move_down_button.setToolTip(_translate("DataPartEditorPanel", "Move Down"))

        self.ui.insert_before_button.clicked.connect(self._slot_insert_before)
        self.ui.insert_after_button.clicked.connect(self._slot_insert_after)
        self.ui.select_all_button.clicked.connect(self._slot_select_all)
        self.ui.cut_button.clicked.connect(self._slot_cut)
        self.ui.copy_button.clicked.connect(self._slot_copy)
        self.ui.paste_button.clicked.connect(self._slot_paste)
        self.ui.del_button.clicked.connect(self._slot_delete)
        self.ui.move_up_button.clicked.connect(self._slot_move_up)
        self.ui.move_down_button.clicked.connect(self._slot_move_down)
        self.ui.tableView.clicked.connect(self._slot_table_clicked)
        self.ui.tableView.doubleClicked.connect(self.__slot_prepare_for_cell_editing)

        self.__special_cell_index = QModelIndex()

        self._current_rows = list()

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.insert_before_button,
                     self.ui.insert_after_button,
                     self.ui.select_all_button,
                     self.ui.cut_button,
                     self.ui.copy_button,
                     self.ui.paste_button,
                     self.ui.del_button,
                     self.ui.move_up_button,
                     self.ui.move_down_button]
        return tab_order

    @override(BaseContentEditor)
    def _complete_data_submission_validation(self):
        """
        Validates if the keys are unique.
        :raises DataSubmissionValidationError: When the keys are not unique.
        """
        bad_keys = self._data_model.get_problem_keys()
        if bad_keys:
            if len(bad_keys) > 1:
                details = ['- {}'.format(repr(bk)) for bk in bad_keys]
                details = '\n'.join(details)
                detailed_msg = "Invalid keys:\n" + details
            else:
                detailed_msg = "Invalid key: " + repr(bad_keys[0])

            raise DataSubmissionValidationError(
                title="Edit Error",
                message="Some keys are invalid or duplicate.",
                detailed_message=detailed_msg
            )

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        If the data to be submitted cannot pass the validation, for example, duplicated keys being used, it throws
        an exception.
        :returns: The data for submission
        """
        self._data_model.display_order = self._sort_order + 1

        data_dict = dict()
        self._data_model.fill_data_for_submission(data_dict)
        return self._get_deepcopy(data_dict)

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        self._data_model.init_model(data)

    def _control_buttons(self, enable: bool):
        """
        If the table is sorted, disable those buttons that can affect the order. Otherwise, enable them.

        :param enable: True to enable the "insert after", "insert before", "paste", "move up", and "move down" buttons;
        otherwise, disable them.
        """
        self.ui.insert_after_button.setEnabled(enable)
        self.ui.insert_before_button.setEnabled(enable)
        self.ui.paste_button.setEnabled(enable)
        self.ui.move_up_button.setEnabled(enable)
        self.ui.move_down_button.setEnabled(enable)

    def _table_clicked(self, index: QModelIndex):
        """
        Called when a cell is clicked. The purpose is to highlight a row when the first column of that row is clicked.

        :param index: the index of the clicked cell.
        """
        if self.ui.tableView.isSortingEnabled():
            sel_model_in_effect = self._sel_proxy_model
        else:
            sel_model_in_effect = self._sel_model
        sel_row = index.row()
        # Highlight the entire row if the first column of that row is selected
        if index.column() == 0 and not sel_model_in_effect.isRowSelected(sel_row, QModelIndex()):
            self.ui.tableView.selectRow(sel_row)

    def _insert_before(self):
        """
        If no selection is made or the table is empty, insert the entry at the top. If the table is sorted, the
        function does nothing.
        """
        if self.ui.tableView.isSortingEnabled():
            return

        num = len(self._current_rows)
        if num == 0:
            self._current_rows.append(0)
            num = 1
        this_row_now = self._current_rows[0]
        self._data_model.insertRows(this_row_now, num)

        self._current_rows = [x + num for x in self._current_rows]

    def _insert_after(self):
        """
        If no selection is made or the table is empty, insert the entry at the bottom. If the table is sorted, the
        function does nothing.
        """
        if self.ui.tableView.isSortingEnabled():
            return

        num = len(self._current_rows)
        if num == 0:
            if self._data_model.rowCount() == 0:
                this_row_now = 0
            else:
                this_row_now = self._data_model.rowCount()
            num = 1
        else:
            this_row_now = self._current_rows[num - 1] + 1
        self._data_model.insertRows(this_row_now, num)

    def _select_all(self):
        """
        Selects all rows, if any.
        """
        self.ui.tableView.selectAll()

    def _cut(self):
        """
        Cuts the selected row(s). If nothing is selected, this function does nothing.
        """
        num_selected = len(self._current_rows)
        if num_selected < 1:
            return

        # if self.ui.tableView.isSortingEnabled():
        #     # Map the selected index from unsorted source model to the sorted proxy model
        #     src_index = self._data_model.index(self._current_rows[0], self._data_model.COL_VALUE_INDEX)
        #     proxy_index = self._proxy_model.mapFromSource(src_index)
        #     selected_row = proxy_index.row()
        # else:
        #     selected_row = self._current_rows[0]

        self._data_model.cut_selection(self._current_rows[0], num_selected)
        del self._current_rows
        self._current_rows = list()

    def _copy(self):
        """
        Copies the selected row(s). If nothing is selected, this function does nothing.
        """
        num_selected = len(self._current_rows)
        if num_selected < 1:
            return
        self._data_model.copy_selection(self._current_rows[0], num_selected)

    def _paste(self):
        """
        Pastes the previsouly copied data. If the table is sorted, the function does nothing.
        """
        if self.ui.tableView.isSortingEnabled():
            return

        num = len(self._current_rows)
        if num == 0:
            if self._data_model.rowCount() == 0:
                this_row_now = 0
            else:
                this_row_now = self._data_model.rowCount()
        else:
            this_row_now = self._current_rows[0]

        self._data_model.paste_selection(this_row_now)

    def _delete(self):
        """
        Deletes the selected row(s). If nothing is selected, this function does nothing.
        """
        num_selected = len(self._current_rows)
        if num_selected < 1:
            return

        # if self.ui.tableView.isSortingEnabled():
        #     # Map the selected index from unsorted source model to the sorted proxy model
        #     src_index = self._data_model.index(self._current_rows[0], self._data_model.COL_VALUE_INDEX)
        #     proxy_index = self._proxy_model.mapFromSource(src_index)
        #     selected_row = proxy_index.row()
        # else:
        #     selected_row = self._current_rows[0]

        self._data_model.removeRows(self._current_rows[0], num_selected)
        del self._current_rows
        self._current_rows = list()

    def _move_up(self):
        """
        Moves the selected row(s) up. If the table is sorted, the function does nothing.
        """
        if self.ui.tableView.isSortingEnabled():
            return
        num_selected = len(self._current_rows)
        if num_selected < 1:
            return
        first_row = self._current_rows[0]
        if first_row < 1:
            return
        self._data_model.moveRows(QModelIndex(), first_row, num_selected, QModelIndex(), first_row - 1)
        self._current_rows = [r - 1 for r in self._current_rows]

    def _move_down(self):
        """
        Moves the selected row(s) down. If the table is sorted, the function does nothing.
        """
        if self.ui.tableView.isSortingEnabled():
            return
        num_selected = len(self._current_rows)
        if num_selected < 1:
            return
        last_row = self._current_rows[num_selected - 1]
        if last_row >= (self._data_model.rowCount() - 1):
            return
        else:
            self._data_model.moveRows(QModelIndex(), self._current_rows[0], num_selected, QModelIndex(), last_row + 2)
            self._current_rows = [r + 1 for r in self._current_rows]

    def _selection_changed(self, selected: QItemSelection, des: QItemSelection):
        """
        Called when a user selects or de-selects anything on the table.

        :param selected: unused but present to satisfy the Qt signature
        :param des: unused but present to satisfy the Qt signature
        """
        if self.ui.tableView.isSortingEnabled():
            sel_model_in_effect = self._sel_proxy_model
        else:
            sel_model_in_effect = self._sel_model

        del self._current_rows
        self._current_rows = list()
        sel_idx = sel_model_in_effect.selectedIndexes()

        for x in sel_idx:
            sel_row = x.row()

            # Map row selection to sorted model if sorting enabled
            if self.ui.tableView.isSortingEnabled():
                sel_row = self.__map_rows_to_sorted_model([sel_row])[0]

            if sel_row not in self._current_rows:
                self._current_rows.append(sel_row)

        # If sorted reverse-alphabetical, reverse order of selection so table model operations work correctly
        if self._sort_order == Qt.DescendingOrder:
            self._current_rows.reverse()

    def _section_clicked(self, logical_index: int):
        """
        Processes the user actions of changing the display order of the key column.

        :param logical_index: unused but present to satisfy the Qt signature.
        """
        if logical_index not in DataPartTableModelForEditing.SORTED_ON:
            self.ui.tableView.horizontalHeader().setSortIndicatorShown(False)
            return

        if self._sort_order == DataPartEditorPanel.NO_SORT:
            self.ui.tableView.setModel(self._proxy_model)
            self.ui.tableView.setSortingEnabled(True)
            self.ui.tableView.sortByColumn(DataPartTableModelForEditing.COL_KEY_INDEX, Qt.AscendingOrder)
            self._sort_order = Qt.AscendingOrder
            self._sel_proxy_model = QItemSelectionModel(self._proxy_model)
            self.ui.tableView.setSelectionModel(self._sel_proxy_model)
            self._sel_proxy_model.clearSelection()
            self._sel_proxy_model.selectionChanged.connect(self._slot_selection_changed)
            self._control_buttons(False)
        elif self._sort_order == Qt.AscendingOrder:
            self.ui.tableView.setModel(self._proxy_model)
            self.ui.tableView.setSortingEnabled(True)
            self.ui.tableView.sortByColumn(DataPartTableModelForEditing.COL_KEY_INDEX, Qt.DescendingOrder)
            self._sort_order = Qt.DescendingOrder
            self._sel_proxy_model = QItemSelectionModel(self._proxy_model)
            self.ui.tableView.setSelectionModel(self._sel_proxy_model)
            self._sel_proxy_model.clearSelection()
            self._sel_proxy_model.selectionChanged.connect(self._slot_selection_changed)
            self._control_buttons(False)
        elif self._sort_order == Qt.DescendingOrder:
            self.ui.tableView.setModel(self._data_model)
            self.ui.tableView.setSortingEnabled(False)
            self._sort_order = DataPartEditorPanel.NO_SORT
            self._sel_model = QItemSelectionModel(self._data_model)
            self.ui.tableView.setSelectionModel(self._sel_model)
            self._sel_model.clearSelection()
            self._sel_model.selectionChanged.connect(self._slot_selection_changed)
            self._control_buttons(True)

            del self._current_rows
            self._current_rows = list()

    def _model_reset(self):
        """
        If the table is sorted, the QSortFilterProxyModel will be used. If the table is of the of_creation order,
        the DataPartTableModelForEditing(QAbstractTableModel) will be used.
        """
        self._proxy_model = SortFilterProxyModelByColumns(self.parent(), DataPartTableModelForEditing.SORTED_ON)
        self._proxy_model.setSourceModel(self._data_model)

        self._sel_proxy_model = QItemSelectionModel(self._proxy_model)
        self._sel_model = QItemSelectionModel(self._data_model)

        self._sort_order = self._data_model.display_order - 1
        if self._data_model.display_order == DisplayOrderEnum.alphabetical:
            self.ui.tableView.setModel(self._proxy_model)
            self.ui.tableView.setSortingEnabled(True)
            self.ui.tableView.sortByColumn(DataPartTableModelForEditing.COL_KEY_INDEX, Qt.AscendingOrder)
            self.ui.tableView.setSelectionModel(self._sel_proxy_model)
            self._sel_proxy_model.selectionChanged.connect(self._slot_selection_changed)
            self._control_buttons(False)
        elif self._data_model.display_order == DisplayOrderEnum.reverse_alphabetical:
            self.ui.tableView.setModel(self._proxy_model)
            self.ui.tableView.setSortingEnabled(True)
            self.ui.tableView.sortByColumn(DataPartTableModelForEditing.COL_KEY_INDEX, Qt.DescendingOrder)
            self.ui.tableView.setSelectionModel(self._sel_proxy_model)
            self._sel_proxy_model.selectionChanged.connect(self._slot_selection_changed)
            self._control_buttons(False)
        else:
            # This must be DisplayOrderEnum.of_creation
            self.ui.tableView.setModel(self._data_model)
            self.ui.tableView.setSortingEnabled(False)
            self.ui.tableView.setSelectionModel(self._sel_model)
            self._sel_model.selectionChanged.connect(self._slot_selection_changed)
            self._control_buttons(True)

        self.__adjust_col_width()

    @override(SpecialValueDisplay)
    def _get_special_value(self) -> object:
        return self._data_model.get_cell(self.__special_cell_index)

    @override(SpecialValueDisplay)
    def _set_special_value(self, val: Any):
        return self._data_model.set_cell(self.__special_cell_index, val)

    @override(BaseContentEditor)
    def _get_custom_deepcopy(self, src_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep-copy the data from the source dictionary to the destination dictionary. If the data has "bad"
        values such as the return value of open(), the values will be added to the destination dictionary without
        deep-copy.

        :param src_data: The source dictionary to be copied from.
        :return The deep-copied data
        """
        destination_data = dict()
        for key, val in src_data.items():
            try:
                # Tests this value. If it can be copied, we leave it intact
                destination_data[key] = deepcopy(val)
            except:
                destination_data[key] = val

        return destination_data

    def __adjust_col_width(self):
        """
        Used only when the table is displayed upon opening. It may be used after a table data change. But that could
        produce a width jitter, which is undesirable to some users.
        """
        self.ui.tableView.resizeColumnsToContents()
        self.ui.tableView.horizontalHeader().setSectionResizeMode(DataPartTableModelForEditing.COL_VALUE_INDEX,
                                                                  QHeaderView.Stretch)

    def __map_rows_to_sorted_model(self, src_row_indexes: List[QModelIndex]) -> List[QModelIndex]:
        """
        Maps the (unsorted) source-model row indexes to sorted proxy-model row indexes.
        :param src_row_indexes: A list of source model indexes to map.
        :return: A list of sorted model indexes.
        """

        mapped_row_indexes = []

        for row_idx in src_row_indexes:
            src_index = self._data_model.index(row_idx, 0)
            proxy_index = self._proxy_model.mapFromSource(src_index)
            mapped_row_indexes.append(proxy_index.row())

        return mapped_row_indexes

    _slot_table_clicked = safe_slot(_table_clicked)
    _slot_insert_before = safe_slot(_insert_before)
    _slot_insert_after = safe_slot(_insert_after)
    _slot_select_all = safe_slot(_select_all)
    _slot_cut = safe_slot(_cut)
    _slot_copy = safe_slot(_copy)
    _slot_paste = safe_slot(_paste)
    _slot_delete = safe_slot(_delete)
    _slot_move_up = safe_slot(_move_up)
    _slot_move_down = safe_slot(_move_down)
    _slot_selection_changed = safe_slot(_selection_changed)
    _slot_section_clicked = safe_slot(_section_clicked)
    _slot_model_reset = safe_slot(_model_reset)

    def __prepare_for_cell_editing(self, index: QModelIndex):
        """
        Opens the Special Value Editor in response to a double-click at the given index if the value at the index is
        not representable.
        :param index: The index of the cell
        """
        self.__special_cell_index = index
        self._open_special_value_editor()

    __slot_prepare_for_cell_editing = safe_slot(__prepare_for_cell_editing)


register_part_editor_class(ori.OriDataPartKeys.PART_TYPE_DATA, DataPartEditorPanel)
