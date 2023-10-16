# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module implements the GUI ('front-end') data part functionality

A QAbstractTableModel/View is used for displaying data in each back-end data part in the 2D view.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from collections import OrderedDict

# [2. third-party]
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QVariant, QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QTableView

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts.data_part import DataPart, DisplayOrderEnum
from ..gui_utils import PyExpr, get_scenario_font, retrieve_cached_py_expr
from ..safe_slot import safe_slot

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'DataPartTableView',
    'DataPartTableModel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class DataPartTableView(QTableView):
    """
    Implements a Table View for viewing the data in the Data Part.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setFont(get_scenario_font())

    @override(QWidget)
    def mousePressEvent(self, evt):
        """
        Prevent mouse selection of the view. Enables entire widget to be selected when the View is clicked.
        """
        evt.ignore()


# noinspection PyMethodOverriding,PyUnresolvedReferences
class DataPartTableModel(QAbstractTableModel):
    """
    Implements a Table Model for getting and setting data part data.
    """

    class Signals(QObject):
        sig_change_data_widget_display_order = pyqtSignal(int)  # DisplayOrderEnum

    # The first column is special. It is used to select a row.
    COL_KEY_INDEX = 0
    COL_VALUE_INDEX = COL_KEY_INDEX + 1
    NUM_COLUMN = 2

    def __init__(self, part: DataPart, parent: QWidget = None):
        super().__init__(parent)

        self.signals = DataPartTableModel.Signals()
        self._part = part
        self._header = [QVariant('Key'), QVariant('Value')]

        self.__rows = 0
        self.__orig_rows = 0
        # key: row; value: the evaluated PyExpr obj
        self.__py_expr_cache = dict()

        part.signals.sig_data_changed.connect(self.__slot_change_data)
        part.signals.sig_data_added.connect(self.__slot_add_data)
        part.signals.sig_data_deleted.connect(self.__slot_delete_data)
        part.signals.sig_data_cleared.connect(self.__slot_clear_data)
        part.signals.sig_data_reset.connect(self.__slot_reset_data)

    @override(QAbstractTableModel)
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> Either[str, None]:
        """
        Returns the data for the given role and section in the header with the specified orientation.
        :param section: the row number
        :param orientation: horizontal
        :param role: the role of the data - display in this instance
        :return: a QVariant containing the header data item requested
        """
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section in range(DataPartTableModel.NUM_COLUMN):
                return self._header[section]

        return None

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

        row_count = len(self._part.keys())

        # Check that a change has occurred
        if self.__rows != row_count:
            self.__orig_rows = self.__rows
            self.__rows = row_count

        return self.__rows

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
        return DataPartTableModel.NUM_COLUMN

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

        if role == Qt.DisplayRole:
            if col > (DataPartTableModel.NUM_COLUMN - 1):
                return QVariant()

            try:
                if col == DataPartTableModel.COL_KEY_INDEX:
                    return QVariant(self._part.get_key_at_row(row))

                if col == DataPartTableModel.COL_VALUE_INDEX:
                    return str(retrieve_cached_py_expr(self,
                                                       self.__py_expr_cache,
                                                       index,
                                                       self._part.get_value_at_row(row)))
            except IndexError:
                return QVariant()

        if role == Qt.TextAlignmentRole:
            return Qt.AlignLeft | Qt.AlignVCenter

        if role == Qt.ToolTipRole:
            if col == DataPartTableModel.COL_VALUE_INDEX:
                return retrieve_cached_py_expr(self,
                                               self.__py_expr_cache,
                                               index,
                                               self._part.get_value_at_row(row)).get_display_tooltip()

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
        col = index.column()
        if col == DataPartTableModel.COL_VALUE_INDEX:
            return Qt.ItemIsEnabled

        return Qt.NoItemFlags

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
        self.endInsertRows()

        # Check that a rows have been added
        if self.__orig_rows < self.__rows:
            return True
        else:
            return False

    @override(QAbstractTableModel)
    def removeRows(self, remove_at_row: int, num_rows: int = 1, parent=QModelIndex()) -> bool:
        """
        Removes num_rows rows starting with the given row, remove_at_row, under parent index from the model.
        :param remove_at_row: first row to remove
        :param num_rows: total rows to remove (default set to one row)
        :param parent: parent index
        :return: returns true if the rows were successfully removed; otherwise returns false.
        """

        self.beginRemoveRows(parent, remove_at_row, remove_at_row + num_rows - 1)
        self.endRemoveRows()

        # Check that a rows have been removed
        if self.__orig_rows > self.__rows:
            return True
        else:
            return False

    def __change_data(self, row: int):
        """
        Updates the data in the table view when the value changes.
        :param row: the affected row number (0, 1, ... , n-1)
        """
        key_index = self.index(row, DataPartTableModel.COL_KEY_INDEX)
        value_index = self.index(row, DataPartTableModel.COL_VALUE_INDEX)
        self.dataChanged.emit(key_index, value_index)

    def __add_data(self, row: int):
        """
        Adds new data to the table view.
        :param row: the affected row number (0, 1, ... , n-1)
        """
        key_index = self.index(row, DataPartTableModel.COL_KEY_INDEX)
        value_index = self.index(row, DataPartTableModel.COL_VALUE_INDEX)
        self.insertRows(row)
        self.dataChanged.emit(key_index, value_index)

    def __delete_data(self, row: int):
        """
        Deletes data from the table view.
        :param row: the affected row number (0, 1, ... , n-1)
        """
        key_index = self.index(row, DataPartTableModel.COL_KEY_INDEX)
        value_index = self.index(row, DataPartTableModel.COL_VALUE_INDEX)
        self.removeRows(row)
        self.dataChanged.emit(key_index, value_index)

    def __clear_data(self):
        """
        After the underlying part data is cleared, use the Qt framework functions to clear the GUI.
        """
        self.beginResetModel()
        self.endResetModel()

    def __reset_data(self):
        """
        This is triggered when the script changes the contained object(s) of the data part.
        """
        self.beginResetModel()
        self.endResetModel()
        self.signals.sig_change_data_widget_display_order.emit(self._part.get_display_order().value)

    # __slot_data_reset = safe_slot(__update_all_data)
    __slot_change_data = safe_slot(__change_data)
    __slot_add_data = safe_slot(__add_data)
    __slot_delete_data = safe_slot(__delete_data)
    __slot_clear_data = safe_slot(__clear_data)
    __slot_reset_data = safe_slot(__reset_data)
