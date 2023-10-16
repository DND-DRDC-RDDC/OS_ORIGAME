# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module implements the sheet part's GUI-to-backend table model interface

A QAbstractTableModel/View is used for displaying data from each back-end sheet part in the 2D view.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QVariant, Qt
from PyQt5.QtWidgets import QWidget, QTableView

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import SheetPart
from ..gui_utils import retrieve_cached_py_expr
from ..safe_slot import safe_slot

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SheetPartTableView',
    'SheetPartTableModel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class SheetPartTableView(QTableView):
    """
    Implements a Table View for viewing the data in the Sheet Part.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

    @override(QWidget)
    def mousePressEvent(self, evt):
        """
        Prevent mouse selection of the view. Enables entire widget to be selected when the View is clicked.
        """
        evt.ignore()


# noinspection PyMethodOverriding,PyUnresolvedReferences
class SheetPartTableModel(QAbstractTableModel):
    """
    Implements a Table Model for getting and setting sheet part data.
    """

    def __init__(self, sheet_part: SheetPart):
        """
        :param sheet_part: the backend sheet part
        """
        super().__init__()

        self._sheet_part = sheet_part

        # Set row and column count values
        self._rows = sheet_part.get_rows()
        self._cols = sheet_part.get_cols()

        # Store the previous row and column counts for tracking purposes
        self._orig_rows = self._rows
        self._orig_cols = self._cols
        # A grid cache: PyExprGridCache
        self.__py_expr_cache = dict()

        # Set up connections to backend sheet part
        sheet_part.signals.sig_row_subset_changed.connect(self._slot_update_rows)
        sheet_part.signals.sig_col_subset_changed.connect(self._slot_update_cols)
        sheet_part.signals.sig_sheet_subset_changed.connect(self._slot_update_sheet_subset)
        sheet_part.signals.sig_cell_changed.connect(self._slot_update_cell)
        sheet_part.signals.sig_rows_added.connect(self._slot_add_or_remove_rows)
        sheet_part.signals.sig_cols_added.connect(self._slot_add_or_remove_cols)
        sheet_part.signals.sig_col_name_changed.connect(self._slot_trigger_header_changed)
        sheet_part.signals.sig_col_idx_style_changed.connect(self._slot_trigger_index_style_changed)
        sheet_part.signals.sig_full_sheet_changed.connect(self._slot_update_sheet)

    @override(QAbstractTableModel)
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> Either[str, None]:
        """
        Gets the current horizontal (column) and vertical (row) header data from the sheet part at the index 'section'.
        See the Qt documentation for method parameter definitions.
        """

        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal and section < self._cols:
            try:
                return self._sheet_part.get_col_header(section)
            except IndexError:
                # If the back-end sheet modifies the headers before it signals the front-end sheet, we get here
                return None

        # Section is row index
        if orientation == Qt.Vertical and section < self._rows:
            return self._sheet_part.get_row_header(section)

        return None

    @override(QAbstractTableModel)
    def setHeaderData(self, section: int, orientation: Qt.Orientation, value: QVariant, role=Qt.EditRole) -> bool:
        """
        Sets the horizontal (column) header data into the sheet part at index 'section'. Only column headers can be set.
        See the Qt documentation for method parameter definitions.
        """

        if role == Qt.EditRole and orientation == Qt.Horizontal:

            try:
                col_idx = section
                self._sheet_part.set_col_name(col_idx, value.value())
                self.headerDataChanged.emit(orientation, col_idx, col_idx)
                return True
            except ValueError:
                return False
            except IndexError:
                return False

        return False

    @override(QAbstractTableModel)
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of rows in the sheet part.

        To understand the following docstring it is important to understand that Qt only returns a 'valid' QModelIndex
        for children of a parent. The parent itself has an invalid (or empty) QModelIndex.

        This method returns the number of rows for the children of the given parent_index. When implementing a table
        based model, rowCount() should return 0 when the parent_index is valid. This is because, if 'parent_index'
        (the QModelIndex) is valid, it is not THE PARENT item in the model but a CHILD.

        For table models, the child represents a cell of the table and can't have rows or columns. Thus, only an
        invalid QModelIndex that contains all the cells can provide a row count.

        See the Qt documentation for method parameter definitions.
        """

        # Return zero rows if child index (i.e. valid index)
        if parent_index.isValid():
            return 0

        # Get current backend row count
        row_count = self._sheet_part.get_rows()

        # Check that a change has occurred
        if self._rows != row_count:
            self._orig_rows = self._rows
            self._rows = row_count

        return self._rows

    @override(QAbstractTableModel)
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of columns in the sheet part.

        To understand the following docstring it is important to understand that Qt only returns a 'valid' QModelIndex
        for children of a parent. The parent itself has an invalid (or empty) QModelIndex.

        This method returns the number of columns for the children of the given parent_index. In most subclasses,
        the number of columns is independent of the parent. When implementing a table based model, columnCount() should
        return 0 when the parent_index is valid. This is because, if 'parent_index' (the QModelIndex) is valid, it is
        not THE PARENT item in the model but a CHILD. For table models, the child represents a cell of the table and
        can't have rows or columns. Thus, only an invalid QModelIndex that contains all the cells can provide a column
        count.

        See the Qt documentation for method parameter definitions.
        """

        # Return zero cols if child index (i.e. valid index)
        if parent_index.isValid():
            return 0

        # Get current backend column count
        col_count = self._sheet_part.get_cols()

        # Check that a change has occurred
        if self._cols != col_count:
            self._orig_cols = self._cols
            self._cols = col_count

        return self._cols

    @override(QAbstractTableModel)
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> str:
        """
        This method returns the sheet part data located at 'index' to the sheet part's View (class SheetPart2dContent).

        View requests an update when the signal 'dataChanged' is emitted by one of this class' slots. Each slot is set
        to receive a specific signal from the backend sheet part when data in the sheet has changed. For example, a row
        update across a subset of rows would cause the slot 'slot_update_rows' to be called with the affected row index
        range. The dataChanged signal is called in turn, causing the View to update the contents of the specified rows.

        See the Qt documentation for method parameter definitions.
        """
        if not index.isValid():
            return None

        col = index.column()
        row = index.row()

        if role == Qt.DisplayRole:
            try:
                return str(retrieve_cached_py_expr(self,
                                                   self.__py_expr_cache,
                                                   index,
                                                   self._sheet_part.get_cell_data(row, col)))
            except IndexError:
                return QVariant()

        if role == Qt.TextAlignmentRole:
            return Qt.AlignHCenter | Qt.AlignVCenter

        if role == Qt.ToolTipRole:
            try:
                return retrieve_cached_py_expr(self,
                                               self.__py_expr_cache,
                                               index,
                                               self._sheet_part.get_cell_data(row, col)).get_display_tooltip()
            except IndexError:
                return QVariant()

        return QVariant()

    @override(QAbstractTableModel)
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        This method returns Qt.ItemIsEnabled for all rows and columns. This allows the user to interact with all values
        in the sheet.
        See the Qt documentation for method parameter definitions.
        """
        if not index.isValid():
            return Qt.NoItemFlags

        return Qt.ItemIsEnabled

    @override(QAbstractTableModel)
    def insertColumns(self, insert_index: int, num_columns: int, parent=QModelIndex()) -> bool:
        """
        Inserts columns into the model before the given column index, insert_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the table has changed
        self.beginInsertColumns(parent, insert_index, insert_index + num_columns - 1)
        self.endInsertColumns()

        # Check that a columns have been added
        return self._orig_cols < self._cols

    @override(QAbstractTableModel)
    def removeColumns(self, remove_index: int, num_columns: int, parent=QModelIndex()) -> bool:
        """
        Removes columns of number num_columns starting with the given column index, remove_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the table has changed
        self.beginRemoveColumns(parent, remove_index, remove_index + num_columns - 1)
        self.endRemoveColumns()

        # Check that a columns have been removed
        return self._orig_cols > self._cols

    @override(QAbstractTableModel)
    def insertRows(self, insert_index: int, num_rows: int, parent=QModelIndex()) -> bool:
        """
        Inserts rows of number num_rows into the model before the given row index, insert_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the table has changed
        self.beginInsertRows(parent, insert_index, insert_index + num_rows - 1)
        self.endInsertRows()

        # Check that a rows have been added
        return self._orig_rows < self._rows

    @override(QAbstractTableModel)
    def removeRows(self, remove_index: int, num_rows: int, parent=QModelIndex()) -> bool:
        """
        Removes rows of number num_rows starting with the given row index, remove_index.
        See the Qt documentation for method parameter definitions.
        """

        # Notify other components the table has changed
        self.beginRemoveRows(parent, remove_index, remove_index + num_rows - 1)
        self.endRemoveRows()

        # Check that a rows have been removed
        return self._orig_rows > self._rows

    def get_rows(self):
        """
        Get the current number of rows.
        :returns the number of rows.
        """
        return self._rows

    def get_cols(self):
        """
        Get the current number of columns.
        :returns the number of columns.
        """
        return self._cols

    rows = property(get_rows)
    cols = property(get_cols)

    def _update_rows(self, row_index: int, start_col: int, end_col: int):
        """
        Signals the 'view' to update the row values at the indices provided by the backend sheet part.

        When signalled by the backend sheet part that a row subset has changed, this slot emits the 'dataChanged' signal
        that triggers the sheet parts 'view' to update itself over the row indices provided. The view uses the
        provided row indices along with this class' 'data' method to access the backend sheet part data.

        :param row_index: the index of the row to update
        :param start_col: index of the first column to update
        :param end_col: index of the last column to update
        """
        left_index = self.index(row_index, start_col)
        right_index = self.index(row_index, end_col)
        self.dataChanged.emit(left_index, right_index)

    def _update_cols(self, start_row: int, end_row: int, col_index: int):
        """
        Signals the 'view' to update the column values at the indices provided by the backend sheet part.

        When signalled by the backend sheet part that a column subset has changed, this slot emits the 'dataChanged'
        signal that triggers the sheet parts 'view' to update itself over the column indices provided. The view uses the
        provided column indices along with this class' 'data' method to access the backend sheet part data.

        :param start_row: index of the first row to update
        :param end_row: index of the last row to update
        :param col_index: the index of the column to update
        """
        top_index = self.index(start_row, col_index)
        bottom_index = self.index(end_row, col_index)
        self.dataChanged.emit(top_index, bottom_index)

    def _update_sheet_subset(self, start_row: int, end_row: int, start_col: int, end_col: int):
        """
        Signals the 'view' to update values across a subset (range) of rows and columns.

        When signalled by the backend sheet part that a row/column subset has changed, this slot emits the 'dataChanged'
        signal that triggers the sheet parts 'view' to update itself over the index range provided. The view uses the
        provided index range along with this class' 'data' method to access the backend sheet part data.

        Updates the sheet
        :param start_row: index of the first row to update
        :param end_row: index of the last row to update
        :param start_col: index of the first column to update
        :param end_col: index of the last column to update
        """
        top_left_index = self.index(start_row, start_col)
        bottom_right_index = self.index(end_row, end_col)
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def _update_sheet(self):
        """
        Signals the 'view' to update all values in frontend sheet part.

        When signaled by the backend sheet part that the entire set of sheet values has changed, this slot emits the
        'dataChanged' signal that triggers the sheet parts 'view' to update the values. The indices to change are
        constructed from the current size of the sheet (total number of rows and columns). Thus, the index range is
        from the top left cell at (0, 0) to the lower right cell at (num_rows, num_cols). When triggered by the
        'dataChanged' signal, the view uses the constructed index range along with this class' 'data' method to access
        the backend sheet part data.
        """
        self.beginResetModel()
        row_count = self.rowCount()
        col_count = self.columnCount()
        last_row_index = row_count - 1 if row_count > 0 else 0
        last_col_index = col_count - 1 if col_count > 0 else 0
        top_left_index = self.index(0, 0)
        bottom_right_index = self.index(last_row_index, last_col_index)
        self.dataChanged.emit(top_left_index, bottom_right_index)
        self.endResetModel()

    def _update_cell(self, row_index: int, col_index: int):
        """
        Signals the 'view' to update an individual sheet cell by emitting the dataChanged signal. The view accesses the
        backend sheet part data via the class' 'data' method.

        :param row_index: the index of the row to be updated
        :param col_index: the index of the column to be updated
        """
        cell_index = self.index(row_index, col_index)
        self.dataChanged.emit(cell_index, cell_index)

    def _add_or_remove_rows(self, row_start_index: int, num_rows: int):
        """
        Adds/removes rows.
        :param row_start_index: the row index insertion/removal point
        :param num_rows: the number of rows to insert/remove
        """
        if num_rows > 0:
            # Add rows
            top_left_index = self.index(row_start_index, 0)
            row_last_index = row_start_index + num_rows - 1
            bottom_right_index = self.index(row_last_index, self._cols - 1)
            self.insertRows(row_start_index, num_rows)
            self.dataChanged.emit(top_left_index, bottom_right_index)
        elif num_rows < 0:
            # Remove rows
            num_rows *= -1  # Reverse sign back to positive value in order to process row removal
            top_left_index = self.index(row_start_index, 0)
            row_last_index = row_start_index + num_rows - 1
            bottom_right_index = self.index(row_last_index, self._cols - 1)
            self.removeRows(row_start_index, num_rows)
            self.dataChanged.emit(top_left_index, bottom_right_index)

    def _add_or_remove_cols(self, col_start_index: int, num_cols: int):
        """
        Adds/removes rows.
        :param col_start_index: the column index insertion/removal point
        :param num_cols: the number of columns to insert/remove
        """
        if num_cols > 0:
            # Add columns
            top_left_index = self.index(0, col_start_index)
            col_last_index = col_start_index + num_cols - 1
            bottom_right_index = self.index(self._rows - 1, col_last_index)
            self.insertColumns(col_start_index, num_cols)
            self.dataChanged.emit(top_left_index, bottom_right_index)
        else:
            # Remove columns
            num_cols *= -1  # Reverse sign back to positive value in order to process column removal
            top_left_index = self.index(0, col_start_index)
            col_last_index = col_start_index + num_cols - 1
            bottom_right_index = self.index(self._rows - 1, col_last_index)
            self.removeColumns(col_start_index, num_cols)
            self.dataChanged.emit(top_left_index, bottom_right_index)

    # noinspection PyUnusedLocal
    def _trigger_header_changed(self, col_index: int, col_header: str):
        """
        Forwards back-end sheet part header updates to the front-end
        :param col_index: column index to update
        :param col_header: the new header data (not used since the table model gets the name from the back-end directly)
        """
        del col_header
        self.headerDataChanged.emit(Qt.Horizontal, col_index, col_index)

    def _trigger_index_style_changed(self):
        """
        Forwards back-end sheet part header updates (ALL header names) to the front-end
        """
        last_col_index = self.columnCount() - 1
        self.headerDataChanged.emit(Qt.Horizontal, 0, last_col_index)

    # Protected slots
    _slot_update_rows = safe_slot(_update_rows)
    _slot_update_cols = safe_slot(_update_cols)
    _slot_update_sheet_subset = safe_slot(_update_sheet_subset)
    _slot_update_sheet = safe_slot(_update_sheet)
    _slot_update_cell = safe_slot(_update_cell)
    _slot_add_or_remove_rows = safe_slot(_add_or_remove_rows)
    _slot_add_or_remove_cols = safe_slot(_add_or_remove_cols)
    _slot_trigger_header_changed = safe_slot(_trigger_header_changed)
    _slot_trigger_index_style_changed = safe_slot(_trigger_index_style_changed)
