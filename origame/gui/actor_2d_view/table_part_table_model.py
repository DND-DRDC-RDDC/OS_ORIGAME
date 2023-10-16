# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module implements the GUI ('front-end') table part functionality

A QAbstractTableModel/View is used for displaying data in each back-end table part in the 2D view.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from math import fmod

# [2. third-party]
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QTableView

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import TablePart, DisplayOrderEnum
from ..async_methods import AsyncRequest
from ..safe_slot import safe_slot, ext_safe_slot

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'TablePartTableView',
    'TablePartTableModel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class TablePartTableView(QTableView):
    """
    Implements a Table View for viewing the data in the Table Part.
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
class TablePartTableModel(QAbstractTableModel):
    """
    Implements a Table Model for getting and setting Table part data.

    The table loads the data in 100 record increments, loading the next set of 100 as the table is scrolled and reaches
    the bottom of the current set. If the editor is opened, all records will be loaded. However, once changes made in
    the editor are applied to the table, the table widget will refresh and again load only the first 100 records.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    NUM_RECORDS_LIMIT = 100

    sig_change_table_widget_display_order = pyqtSignal(int, list)  # DisplayOrderEnum, list of columns
    sig_rows_changed = pyqtSignal(int)  # number or rows
    sig_cols_changed = pyqtSignal(int)  # number of columns

    Record = Tuple[Any]
    TableCellData = Either[str, int, float]

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, table_part: TablePart, parent: QWidget = None):
        super().__init__(parent)

        # The backend part to view
        self.__table_part = table_part

        # Init row and column count values
        self.__rows = 0
        self.__cols = 0

        # Store the previous row and column counts for tracking purposes
        self.__orig_rows = 0
        self.__orig_cols = 0

        # Sort attributes
        self.__display_order = DisplayOrderEnum.of_creation
        self.__sorted_column = [0]

        # Cache back-end database data for quick front-end updates
        self.__record_cache = []  # cache of incrementally loaded records (contains a subset of all records)
        self.__row_ids = []  # listing of ALL row IDs (every row in the back-end DB)
        self.__col_name_cache = []  # ache of ALL column headers/labels
        self.__next_record_id = 1  # the ID or the next record to load (if any) (IDs start at 1)
        self.__is_done_last_fetch = True  # flag indicates if done fetching more data before it fetches again
        self.__last_row_index_in_cache = 0
        self.__col_indexes = []  # cached of indexed columns

        # Load all backend table part data into the table
        self.__init_table_cache()

        # Records are cached incrementally so track the current max number of records to cache
        # This max will grow as the user scrolls down IF there are more records to load from the back-end.
        self.__times_fetched = 1
        self.__max_records_before_next_fetch = self.__times_fetched * self.NUM_RECORDS_LIMIT

        table_part.signals.sig_full_table_changed.connect(self.__slot_reinitialize_table)
        table_part.signals.sig_filter_changed.connect(self.__slot_reinitialize_table)
        table_part.signals.sig_record_added.connect(self.__slot_add_record)
        table_part.signals.sig_record_removed.connect(self.__slot_remove_record)
        table_part.signals.sig_field_changed.connect(self.__slot_update_field)
        table_part.signals.sig_col_added.connect(self.__slot_add_column)
        table_part.signals.sig_col_dropped.connect(self.__slot_remove_column)
        table_part.signals.sig_col_name_changed.connect(self.__slot_trigger_header_changed)
        table_part.signals.sig_index_added.connect(self.__slot_add_indexed_columns)
        table_part.signals.sig_index_dropped.connect(self.__slot_remove_indexed_columns)

    @override(QAbstractTableModel)
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> Either[str, None]:
        """
        Gets the current horizontal (column) and vertical (row) header data from the table part at the index 'section'.
        See the Qt documentation for method parameter definitions.
        """
        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal:
            try:
                col_name = self.__get_displayed_col_name(self.__col_name_cache[section])
                return str(col_name)
            except IndexError:
                # Need to handle case where View asks for header data while column name cache is empty due to
                # a refresh of the table data.
                return None

        if orientation == Qt.Vertical and section < self.__rows:
            return str(section + 1)  # The first row is row '1'

        return None

    @override(QAbstractTableModel)
    def rowCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of rows in the table part cache (parent_index invalid), or 0 if parent_index is valid.

        To understand the following docstring it is important to understand that Qt view for a table assumes
        a "root" model index in which there is one child index for each cell of the table, and that
        the "root" index corresponds to an "invalid" Qt index object whereas the children indices of
        root index are themselves valid. This method does get called for children of the "root"
        index, in which case must return 0.
        """
        # Return zero rows if child index (i.e. valid index)
        if parent_index.isValid():
            return 0

        # Get the current record count
        record_count = len(self.__row_ids)

        # Check that a change has occurred
        if self.__rows != record_count:
            self.__orig_rows = self.__rows
            self.__rows = record_count

        return self.__rows

    @override(QAbstractTableModel)
    def columnCount(self, parent_index: QModelIndex = QModelIndex()) -> int:
        """
        Returns the number of columns in the table part cache (if parent_index invalid), or 0 if parent_index is valid.

        To understand the following docstring it is important to understand that Qt view for a table assumes
        a "root" model index in which there is one child index for each cell of the table, and that
        the "root" index corresponds to an "invalid" Qt index object whereas the children indices of
        root index are themselves valid. This method does get called for children of the "root"
        index, in which case must return 0.
        """
        # Return zero cols if child index (i.e. valid index)
        if parent_index.isValid():
            return 0

        # Get current column count
        col_count = len(self.__col_name_cache)

        # Check that a change has occurred
        if self.__cols != col_count:
            self.__orig_cols = self.__cols
            self.__cols = col_count

        return self.__cols

    @override(QAbstractTableModel)
    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Optional[TableCellData]:
        """
        This method returns the table part data located at 'index' to the table part's View (class TablePart2dContent).

        View requests an update when the signal 'dataChanged' is emitted by one of this class' slots. Each slot is set
        to receive a specific signal from the backend table part when data in the table has changed. For example, a row
        update across a subset of rows would cause the slot 'slot_update_rows' to be called with the affected row index
        range. The dataChanged signal is called in turn, causing the View to update the contents of the specified rows.

        See the Qt documentation for method parameter definitions.
        """
        if not index.isValid():
            # the index is the "root" of table, which has no data
            return None

        if role == Qt.DisplayRole:
            row_index = index.row()
            col_index = index.column()

            if row_index >= self.__last_row_index_in_cache and self.canFetchMore(QModelIndex()):
                # When the last row of the current cache is requested, load the next set of rows
                self.fetchMore(QModelIndex())

            try:
                record = self.__record_cache[row_index]
                return record[col_index]
            except IndexError:
                # Need to handle case where View asks for header data while record cache is empty due to
                # a refresh of the table data.
                return None

        if role == Qt.TextAlignmentRole:
            return Qt.AlignHCenter | Qt.AlignVCenter

        return None

    @override(QAbstractTableModel)
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """
        Sets all items in the Table's view to be 'disabled'. This prevents the user from interacting with all values
        in the table (selecting or editing values directly outside of the Table Editor).

        See the Qt documentation for method parameter definitions.
        """
        return Qt.NoItemFlags

    @override(QAbstractTableModel)
    def insertColumns(self, insert_index: int, num_columns: int, parent=QModelIndex()) -> bool:
        """
        Inserts columns into the model before the given column index, insert_index.
        See the Qt documentation for method parameter definitions.
        """
        # Notify other components the table has changed
        self.beginInsertColumns(parent, insert_index, insert_index + num_columns - 1)
        self.sig_cols_changed.emit(self.columnCount())
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
        self.sig_cols_changed.emit(self.columnCount())
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
        self.sig_rows_changed.emit(self.rowCount())
        self.endInsertRows()

        return self.__orig_rows < self.__rows

    @override(QAbstractTableModel)
    def removeRows(self, remove_index: int, num_rows: int, parent=QModelIndex()) -> bool:
        """
        Removes rows of number num_rows starting with the given row index, remove_index.
        See the Qt documentation for method parameter definitions.
        """
        # Notify other components the table has changed
        self.beginRemoveRows(parent, remove_index, remove_index + num_rows - 1)
        self.sig_rows_changed.emit(self.rowCount())
        self.endRemoveRows()

        # Check that a rows have been removed
        return self.__orig_rows > self.__rows

    @override(QAbstractTableModel)
    def canFetchMore(self, index: QModelIndex) -> bool:
        """
        Implement to populate the table model incrementally. This method is called automatically when:
        - the table model initializes,
        - whenever the scroll bar hits the last row of the currently loaded table, or
        - when the table is resized to show the last row.
        It is called programatically when the back-end signals that records have been added or removed.
        If it returns True, the fetchMore() method may be automatically called.

        See the Qt documentation for method parameter definitions.
        """
        num_total_records = self.rowCount()
        num_cached_records = len(self.__record_cache)

        if num_cached_records < num_total_records and self.__is_done_last_fetch:
            return True
        else:
            return False

    @override(QAbstractTableModel)
    def fetchMore(self, index: QModelIndex):
        """
        Implement to populate model incrementally. This method can only be called if:
        - canFetchMore() returned True, AND if...
        - the scroll bar hits the last row of the currently loaded table, OR...
        - when the table is resized to show the last row.

        See the Qt documentation for method parameter definitions.
        """
        self.__is_done_last_fetch = False  # Prevent canFetchMore returning True before this current fetch is done

        table_part = self.__table_part
        next_row_id = self.__row_ids[len(self.__record_cache)]  # <- use length of cache as index: smart!

        def async_get_next_page() -> [[]]:
            records_next_page = table_part.get_record_subset(start_row_id=next_row_id,
                                                             limit=self.NUM_RECORDS_LIMIT,
                                                             flag_apply_filter=True)
            return records_next_page

        def on_page_received(records: List[List[Any]]):
            if len(records) > 0:
                self.__update_table_record_cache(records)

                # Increase the number of records to show if we are at the current limit
                if fmod(len(self.__record_cache), self.__max_records_before_next_fetch) == 0.0:
                    self.__times_fetched += 1
                    self.__max_records_before_next_fetch = self.__times_fetched * self.NUM_RECORDS_LIMIT

                self.__is_done_last_fetch = True  # Done: allow more fetching

        AsyncRequest.call(async_get_next_page, response_cb=on_page_received)

    def get_rows(self) -> int:
        """
        Get the current number of rows.
        :returns the number of rows.
        """
        return self.__rows

    def get_cols(self) -> int:
        """
        Get the current number of columns.
        :returns the number of columns.
        """
        return self.__cols

    def get_col_names(self) -> List[str]:
        """
        Returns the column names in a list.
        """
        return self.__col_name_cache

    def get_record_cache(self) -> List[Record]:
        """
        Gets the current cache of records.
        :return: the record cache.
        """
        return self.__record_cache

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    rows = property(get_rows)
    cols = property(get_cols)
    col_names = property(get_col_names)
    record_cache = property(get_record_cache)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_init_col_names(self, col_names: List[str]):
        """
        Populate the column headers cache. If this is called as a result of an update, the caller must call
        headerDataChanged().
        :param col_names: name of each column
        """
        self.__col_name_cache = col_names
        self.__cols = len(self.__col_name_cache)
        self.headerDataChanged.emit(Qt.Horizontal, 0, len(col_names) - 1)

    def __init_table_cache(self, is_update: bool = True):
        """
        Initializes or updates the entire table with the table row/col index to record ID/col name lookup.
        Default is to assume view has already used this model (begin/end/changed notification will occur).
        :param is_update: set to False if the view has not yet used this model
        """
        table_part = self.__table_part

        def async_get_table() -> Tuple[List[str], List[List[str]], List[Tuple[Any]],
                                       List[int], DisplayOrderEnum, List[int]]:
            # column name info
            col_names = table_part.get_column_names()
            idx_col_dict = table_part.get_indices()
            idx_col_names = [idx_col for idx_col in idx_col_dict.values()]

            # first 100 records
            records = table_part.get_record_subset(limit=self.NUM_RECORDS_LIMIT, flag_apply_filter=True)
            all_row_ids = table_part.get_row_ids()  # IDs for ALL rows incl. first 100

            # Display order and sort info
            display_order = table_part.get_display_order()
            sorted_column = table_part.get_sorted_column()

            return col_names, idx_col_names, records, all_row_ids, display_order, sorted_column

        def on_table_received(col_names: List[str], idx_col_names: List[List[str]], records: List[Tuple[Any]],
                              all_row_ids: List[int], display_order: DisplayOrderEnum, sorted_column: List[int]):
            # set the table widget's display order
            self.__display_order = display_order
            self.__sorted_column = sorted_column
            self.sig_change_table_widget_display_order.emit(display_order, sorted_column)

            # init column names and indeces
            self.__on_init_col_names(col_names)
            for idx_columns in idx_col_names:
                self.__add_indexed_columns(idx_columns)

            self.sig_cols_changed.emit(self.columnCount())

            # init table records
            self.__update_table_record_cache(records, all_row_ids=all_row_ids)

        AsyncRequest.call(async_get_table, response_cb=on_table_received)

    def __update_table_record_cache(self, records: List[Tuple[Any]], all_row_ids: List[int] = None):
        """
        Populate the table data cache.
        :param records: the first subset of table records.
        :param all_row_ids: a list of all row IDs in the database.
        """
        self.beginResetModel()

        if all_row_ids is not None:
            # Initializing cache
            self.__record_cache = records
            self.__row_ids = all_row_ids
            self.sig_rows_changed.emit(self.rowCount())
        else:
            # Add records to the cache from existing
            self.__record_cache = self.__record_cache + records

        # Update the index for the last cached record
        num_cached_records = len(self.__record_cache)
        if num_cached_records > 0:
            self.__last_row_index_in_cache = num_cached_records - 1

        self.endResetModel()

    def __reinitialize_table(self):
        """
        Re-initializes the table data by triggering a refresh from the back-end table part.
        """
        self.__last_row_index_in_cache = 0
        self.__times_fetched = 1
        self.__max_records_before_next_fetch = self.__times_fetched * self.NUM_RECORDS_LIMIT
        self.__col_indexes = []
        self.__init_table_cache()

    def __update_field(self, row_id: int, col_name: str, record_item: str):
        """
        Updates the field in the table view when the value changes.
        :param row_id: the affected row (1, 2, ... , N)
        :param col_name: the column name for this field of the record item
        :param record_item: the new record item to insert
        """
        if row_id not in self.__row_ids:
            return

        row_index = self.__row_ids.index(row_id)

        # Update this record in the cached records if it's within the current limit
        if row_index + 1 <= self.__max_records_before_next_fetch:
            col_index = self.__col_name_cache.index(col_name)
            record = self.__record_cache[row_index]
            record[col_index] = record_item

            field_index = self.index(row_index, col_index)
            self.dataChanged.emit(field_index, field_index)

    def __add_record(self, record_id: int, record: Tuple[Any]):
        """
        Adds a record to the end of the table.
        :param record_id: the unique record ID of the added record
        :param record: the field values of the record
        """
        if record_id in self.__row_ids:
            return

        # Add the record to the cache
        self.__row_ids.append(record_id)

        # Add this record to the cached records if it's within the current limit
        new_row_index = self.__row_ids.index(record_id)
        if new_row_index + 1 <= self.__max_records_before_next_fetch:
            self.__record_cache.append(list(record))
            self.__last_row_index_in_cache = len(self.__record_cache) - 1

            # Inform the Table View of the change
            num_rows_to_add = 1
            self.insertRows(new_row_index, num_rows_to_add)
            top_left_index = self.index(new_row_index, 0)
            bottom_right_index = self.index(new_row_index, self.__cols - 1)
            self.dataChanged.emit(top_left_index, bottom_right_index)

    def __remove_record(self, record_id: int):
        """
        Removes a record.
        :param record_id: the unique record ID of the removed record
        """
        if record_id not in self.__row_ids:
            return

        # Remove record from the cache
        remove_row_index = self.__row_ids.index(record_id)
        self.__row_ids.remove(record_id)
        del self.__record_cache[remove_row_index]
        self.__last_row_index_in_cache = len(self.__record_cache) - 1

        # Inform the Table View of the change
        num_rows_to_remove = 1
        self.removeRows(remove_row_index, num_rows_to_remove)
        top_left_index = self.index(remove_row_index, 0)
        bottom_right_index = self.index(remove_row_index, self.__cols - 1)

        self.dataChanged.emit(top_left_index, bottom_right_index)

    def __add_column(self, col_name: str, col_type: str, col_size: int):
        """
        Adds a column.
        :param col_info: a tuple of column info (col_name, col_type, col_size)
        """
        # Check that the name is not already in the dictionary
        if col_name in self.__col_name_cache:
            return

        # Generate a new col index - append to end of current columns
        new_col_index = len(self.__col_name_cache)

        # Update the cache
        self.__col_name_cache.append(col_name)

        # Inform the Table View of the change
        num_cols_to_add = 1
        self.insertColumns(new_col_index, num_cols_to_add)
        self.headerDataChanged.emit(Qt.Horizontal, new_col_index, new_col_index)

    def __remove_column(self, col_name: str):
        """
        Removes a column.
        :param col_name: the name of the column to remove
        """
        # Check if the header name is in the index lookup
        if col_name not in self.__col_name_cache:
            return

        remove_col_index = self.__col_name_cache.index(col_name)
        self.__col_name_cache.remove(col_name)

        # Remove from data cache
        for row_index, record in enumerate(self.__record_cache):
            # Delete only if there is field data under the removed column
            if len(record) > remove_col_index:
                record.pop(remove_col_index)
            self.__record_cache[row_index] = record

        # Inform the Table View of the change
        num_cols_to_remove = 1
        self.removeColumns(remove_col_index, num_cols_to_remove)
        self.headerDataChanged.emit(Qt.Horizontal, remove_col_index, remove_col_index)
        top_left_index = self.index(0, 0)
        bottom_right_index = self.index(self.__rows - 1, self.__cols - 1)
        self.dataChanged.emit(top_left_index, bottom_right_index)

    def __trigger_header_changed(self, orig_name: str, new_name: str):
        """
        Updates the column headers when triggered by the backend
        :param orig_name: original column name
        :param new_name: new column name
        """
        if orig_name not in self.__col_name_cache:
            return

        # Change name in the cache
        col_index = self.__col_name_cache.index(orig_name)
        self.__col_name_cache[col_index] = new_name

        # Inform the Table View of the change
        self.headerDataChanged.emit(Qt.Horizontal, col_index, col_index)

    def __add_indexed_columns(self, indexed_columns: List[str]):
        """
        Adds an asterisk to each column header to indicate the column is indexed.
        :param indexed_columns: a list of indexed column names
        """
        for col_name in indexed_columns:
            if col_name not in self.__col_indexes:
                self.__col_indexes.append(col_name)
            col_idx = self.__col_name_cache.index(col_name)
            self.headerDataChanged.emit(Qt.Horizontal, col_idx, col_idx)

    def __remove_indexed_columns(self, unindexed_columns: List[str]):
        """
        Removes the asterisk from each column header to indicate the column is not indexed.
        :param unindexed_columns: a list of column names that are no longer indexed
        """
        for col_name in unindexed_columns:
            self.__col_indexes.remove(col_name)
            col_idx = self.__col_name_cache.index(col_name)
            self.headerDataChanged.emit(Qt.Horizontal, col_idx, col_idx)

    def __get_displayed_col_name(self, col_name: str) -> str:
        """
        Returns the column name to display including any decorators or markers to show.
        :param col_name: The name to decorate.
        :return: The column name to display.
        """
        if col_name in self.__col_indexes:
            col_name += '*'

        return col_name

    # Private slots
    __slot_reinitialize_table = safe_slot(__reinitialize_table)
    __slot_update_field = safe_slot(__update_field)
    __slot_add_record = ext_safe_slot(__add_record, arg_types=[int, tuple])
    __slot_remove_record = safe_slot(__remove_record)
    __slot_add_column = safe_slot(__add_column)
    __slot_remove_column = safe_slot(__remove_column)
    __slot_trigger_header_changed = safe_slot(__trigger_header_changed)
    __slot_add_indexed_columns = ext_safe_slot(__add_indexed_columns, arg_types=[list])
    __slot_remove_indexed_columns = ext_safe_slot(__remove_indexed_columns, arg_types=[list])
