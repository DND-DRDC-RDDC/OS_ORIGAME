# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the TablePart class and the functionality that supports the part as
a building block for the Origame application.


"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import re
import sched
from pathlib import Path
from copy import deepcopy
from collections import OrderedDict

# [2. third-party]
import pypyodbc

# [3. local]
from ...core import override, BridgeEmitter, BridgeSignal
from ...core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriTablePartKeys as TpKeys
from ..embedded_db import SQLiteMsAccessColumnMapper, SqlDataSet, normalize_name, TableCellData, EmbeddedDatabase
from ..proto_compat_warn import prototype_compat_method_alias

from .base_part import BasePart, check_diff_val
from .common import Position
from .part_types_info import register_new_part_type
from .actor_part import ActorPart
from .data_part import DisplayOrderEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'TablePart',
    'TablePartIndexEmptyError',
    'TablePartSQLiteTableNotFoundError',
    'TablePartIndexExistsError',
    'get_db_tables'
]

log = logging.getLogger('system')

MS_ACCESS_DRIVER_STR = 'Driver={Microsoft Access Driver (*.mdb, *.accdb)};DBQ='

# Some databases such as Microsoft Access do not have concurrency control. This part will wait for its turn to
# access the databases during data import and export.
DATABASE_MAX_ATTEMPTS = 50
DATABASE_ACCESS_ATTEMPT_INTERVAL = 3  # in seconds

DbRawRecord = Tuple[TableCellData]
DbRawRecords = List[DbRawRecord]
ColumnInfo = List[Tuple[str, str, int]]


# -- Function definitions -----------------------------------------------------------------------

def get_db_tables(path: PathType) -> Dict[str, List[str]]:
    """
    This method is used to get the names of the tables and corresponding columns in the MS Access database.
    :param path: The path to the access database file.
    :return: A dictionary of tables and their corresponding column names.
    """
    path = Path(path)
    if not path.exists():
        return OrderedDict()  # no tables since file does not exist

    tables_and_columns = OrderedDict()
    database = connect_ms_access_db(path)
    cursor = database.cursor()

    try:
        tables = [table for _, _, table, name, _ in cursor.tables() if name == 'TABLE']
        for table in tables:
            tables_and_columns[table] = []  # init list of columns for this table
            for col_info in cursor.columns(table=table):
                tables_and_columns[table].append(col_info[3])

    except Exception as exc:
        log.debug("Import failed: path={}", path)
        raise

    return tables_and_columns


def import_from_msaccess(path: PathType,
                         from_table: str,
                         selected_cols: List[str] = None,
                         filter: str = None) -> Tuple[ColumnInfo, DbRawRecords]:
    """
    This method is used to import an MS Access database into a SQLite table.
    :param path: The path to the access database file.
    :param from_table: The table within the access database to import from.
    :param selected_cols: A list of columns to import from the table.
    :param filter: A SQL 'WHERE' clause to filter the data imported.
    :return: a pair where first item is a list of column info, and the second item is the data array; each column
        info is a triplet (column name, column type, column size)
    """
    path = Path(path)
    if not path or not path.exists():
        raise FileNotFoundError("The path to the access database file does not exist.")

    # Make a list of all of the columns and their types in the Access database.
    columns = []
    data_array = []

    # There was a problem during build 1 that required that connecting to a database be attempted multiple times:

    database = connect_ms_access_db(path)
    cursor = database.cursor()
    try:
        type_converter = SQLiteMsAccessColumnMapper()
        name_index = 3
        type_index = 5
        size_index = 6
        for col_info in cursor.columns(table=from_table):
            col_name, col_type, col_size = col_info[name_index], col_info[type_index], col_info[size_index]
            if selected_cols is not None:
                # only import columns the user has selected to import
                if col_name in selected_cols:
                    if col_type.upper() == "COUNTER":
                        # Counter columns in Microsoft Access Database tables are columns whose values are unique and
                        # are automatically incremented when there is a new record inserted into the table.  There is
                        # only one counter column allowed per table.  Although column 'positioning' is not relevant in
                        # sql, it is during design of a table using Microsoft Access (or via sql).  Any column can be
                        # specified as an AutoNumber column and this column can appear in any position during table
                        # creation. The Prototype moves counter columns to the first position, so ORIGAME does the same.
                        # NOTE: on export, counter columns will become Number since COUNTER loses meaning on import
                        columns.insert(0, (col_name, type_converter.get_sqlite_type(col_type), col_size))
                    else:
                        columns.append((col_name, type_converter.get_sqlite_type(col_type), col_size))

            else:  # import all columns
                if col_type.upper() == "COUNTER":
                    # insert COUNTER as first column - see more detailed description in nested 'if' above
                    columns.insert(0, (col_name, type_converter.get_sqlite_type(col_type), col_size))
                else:
                    columns.append((col_name, type_converter.get_sqlite_type(col_type), col_size))

        # copy the data from array:
        selected_columns = [name for name, _, _ in columns]
        selected_columns = ', '.join(normalize_name(col_name) for col_name in selected_columns)
        sql = "SELECT {} FROM {}".format(selected_columns, from_table)
        if filter is not None:
            sql += " WHERE {}".format(filter)

        cursor.execute(sql)

        row = cursor.fetchone()
        while row is not None:
            # row could be appended to the data_array, but the sqlite3 will be 10 times faster if the fields
            # in the row are re-formatted to a tuple.
            data_array.append(tuple(row))
            row = cursor.fetchone()

        # Just to be sure that the connection is released. Otherwise, other callers cannot access the db.
        cursor.close()
        database.close()
        del database

    except Exception:
        log.debug("Import failed: path={}", path)
        raise

    return columns, data_array


def connect_ms_access_db(path: PathType) -> pypyodbc.Connection:
    """Connect to an MS Access database. Tries multiple times until gives up. """
    path = Path(path)

    def attempt_import(num_attempt):
        try:
            return pypyodbc.connect(MS_ACCESS_DRIVER_STR + str(path))

        except Exception as exc:
            log.debug("Import failed: path={}, num_attempt={}", path, num_attempt)
            return None

    for attempt in range(DATABASE_MAX_ATTEMPTS):
        database = attempt_import(attempt)
        if database is not None:
            message = "Successfully imported data from '{}' into table part".format(path)
            log.info(message)
            break

    else:
        err_msg = "Import failed after {} attempts. File: {}".format(DATABASE_MAX_ATTEMPTS, path)
        log.error(err_msg)
        raise ConnectionError(err_msg)

    return database


def export_to_msaccess(column_names: List[str], column_types: List[str], array: DbRawRecords,
                       db_file_path: PathType, to_table_name: str):
    """
    Export the data contained within a table part to MS Access database.
    :param column_names: list of column names
    :param column_types: list of SQLite column types
    :param array: list of records; each record is a tuple of strings
    :param db_file_path: Path to the access database file to export to.
    :param to_table_name: Name of the access database table.
    """
    default_column_type = "TEXT"
    db_file_path, db_file_path_str = Path(db_file_path), str(db_file_path)
    to_table_name = normalize_name(to_table_name)
    if db_file_path.exists():
        database = pypyodbc.connect(MS_ACCESS_DRIVER_STR + db_file_path_str)
        cursor = database.cursor()

        # drop the table if it already exists in the database
        for _, _, table, _, _ in cursor.tables():
            if normalize_name(table) == to_table_name:
                try:
                    cursor.execute("DROP TABLE {}".format(to_table_name))
                    break
                except pypyodbc.ProgrammingError as exc:
                    log.warning("DROP Error during export: {}", exc)
                    break

    else:
        if db_file_path_str.endswith('.accdb'):
            msg = "Database '{}' does not exist and cannot be created (ODBC can only create .MDB database for Access)"
            raise ValueError(msg.format(db_file_path))

        pypyodbc.win_create_mdb(db_file_path_str)
        database = pypyodbc.connect(MS_ACCESS_DRIVER_STR + db_file_path_str)
        cursor = database.cursor()

    converter = SQLiteMsAccessColumnMapper()

    # Fill the col_types_list with the various types of columns.  May have to strip out the the size
    # of the columns if applicable.
    msaccess_col_types = []
    for column_type in column_types:
        if column_type:
            column_type_in_access = column_type

            if "(" in column_type:
                temp_col_type = column_type
                column_type = column_type[:column_type.find("(")]
                column_size = temp_col_type[temp_col_type.find("(") + 1: -1]
                column_type_in_access = converter.get_access_type(column_type.upper())

                if (converter.get_access_type(column_type.upper())) != "INTEGER":
                    column_type_in_access += "(" + column_size + ")"

            msaccess_col_types.append(column_type_in_access)
        else:
            # If for whatever reason there is no column type, set the type to TEXT
            # This is a preventative measure to ensure that the export doesn't fail
            # when this case is encountered.
            msaccess_col_types.append(converter.get_access_type(default_column_type))

    normalized_col_names = [normalize_name(col_name) for col_name in column_names]
    sql = "CREATE TABLE {} ".format(to_table_name)
    cols_with_type = ', '.join('%s %s' % t for t in zip(normalized_col_names, msaccess_col_types))
    if cols_with_type:
        sql = sql + " ({})".format(cols_with_type) + ";"

    try:
        cursor.execute(sql)
        wild_card = "({})".format(', '.join(['?' for _ in normalized_col_names]))
        for row in array:
            sql = "INSERT INTO {} ({}) VALUES {}".format(to_table_name, ','.join(normalized_col_names), wild_card)
            cursor.execute(sql, row)
        cursor.commit()

    except pypyodbc.Error as exc:
        log.warning("Error during export: {}", exc)
        raise

    else:
        message = "Successfully exported data from table part to table '{}' in '{}'".format(to_table_name, db_file_path)
        log.info(message)

    finally:
        # Just to be sure that the connection is released. Otherwise, other callers cannot access the db.
        cursor.close()
        database.close()
        del database


def verify_table_exists(path: PathType, check_table: str) -> bool:
    """
    This method is used to check that a table exists in an MS Access database.
    :param path: The path to the access database file.
    :param check_table: The table within the access database to check.
    :return: a boolean indicating if the table exists.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("The path to the access database file does not exist.")

    con_scheduler = sched.scheduler()
    tables = []
    exist_check_failed = True

    def attempt_to_check(num_attempt=0):
        nonlocal tables
        nonlocal exist_check_failed
        if num_attempt < DATABASE_MAX_ATTEMPTS:
            try:
                data_base = pypyodbc.connect(MS_ACCESS_DRIVER_STR + str(path))
                cursor = data_base.cursor()

                # get MS Access tables from DB:
                tables = [x[2] for x in cursor.tables()]

                # Just to be sure that the connection is released. Otherwise, other callers cannot access the db.
                cursor.close()
                data_base.close()
                del data_base
                exist_check_failed = False

            except:
                log.debug("Existence check failed: path={}, num_attempt={}", path, num_attempt)
                nxt = num_attempt + 1
                con_scheduler.enter(DATABASE_ACCESS_ATTEMPT_INTERVAL, 1, attempt_to_check, argument=(nxt,))

    con_scheduler.enter(0, 1, attempt_to_check)
    con_scheduler.run()

    if exist_check_failed:
        err_msg = "Existence check failed after {} attempts on file: {}".format(DATABASE_MAX_ATTEMPTS, path)
        log.error(err_msg)
        raise ConnectionError(err_msg)

    if check_table in tables:
        return True
    else:
        return False


# -- Class Definitions --------------------------------------------------------------------------

class TablePartIndexExistsError(KeyError):
    """
    Custom error class used for raising Table Part exceptions. This exception represents an error condition where
    an index creation was attempted on one or more columns which already have been indexed.
    """
    pass


class TablePartIndexEmptyError(KeyError):
    """
    Custom error class used for raising Table Part exceptions. This exception represents an error condition where
    an index drop was attempted on a column that had not been indexed.
    """
    pass


class TablePartSQLiteTableNotFoundError(Exception):
    """
    Custom error class used for raising Table Part exceptions. This exception represents an error condition where
    the SQLite database table for this table part has not been created yet.  The Table gets created when adding a
    column.
    """
    pass


class TablePart(BasePart):
    """
    This class defines the functionality required to support an Origame Table Part.
    The Table Part data can be saved to, or loaded from, an Microsoft Access database.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    ColumnSchema = Tuple[int, str, str, bool, Any, bool]

    class Signals(BridgeEmitter):
        sig_full_table_changed = BridgeSignal()
        sig_col_added = BridgeSignal(str, str, int)  # (col_name, col_type, col_size)
        sig_col_dropped = BridgeSignal(str)  # name of dropped column
        sig_col_name_changed = BridgeSignal(str, str)  # (col_original_name, col_new_name)
        sig_index_added = BridgeSignal(list)  # [column names]
        sig_index_dropped = BridgeSignal(list)  # [column names]
        sig_record_added = BridgeSignal(int, tuple)  # id of new record, tuple of field values
        sig_record_removed = BridgeSignal(int)  # id of removed record
        sig_field_changed = BridgeSignal(int, str, str)  # (row_id, column_name, new_value)
        sig_filter_changed = BridgeSignal()

    RE_COL_NAME_FIRST_CHAR = "[a-zA-Z0-9\_]"
    RE_COL_NAME_REST_CHAR = "[a-zA-Z0-9\_\-\.\!\@\#\$\%\^\&\*\(\)\+\=\{\}\|\\\\/\:\;\<\>\,\?\~\s]"
    INDEX_COL_NAMES_SEP = ","

    DEFAULT_VISUAL_SIZE = dict(width=10.0, height=5.1)
    PART_TYPE_NAME = "table"
    DESCRIPTION = """\
        Use this part to create and access a relational database table.

        An SQL part can be linked to this table to execute SQL queries on the table.
    """

    _ORI_HAS_SLOW_DATA = True

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart,
                 name: str = None,
                 position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: The name assigned to this part instance.
        :param position: A position to be assigned to the newly instantiated default Table Part. This argument
        """
        BasePart.__init__(self, parent, name=name, position=position)

        self.signals = TablePart.Signals()
        state = self.shared_scenario_state
        self.__embedded_db = state.embedded_db
        self.__db_table_name = "{}_{}".format(self.PART_TYPE_NAME, self.SESSION_ID)
        self.__indices = {}
        self.__index_counter = 0
        self.__filter = str()
        self.__display_order = DisplayOrderEnum.of_creation
        self.__sorted_column = [0]
        self.__flag_notify_gui = True

        # As soon as a Table Part is created, a database containing a 'default' column is created.
        # This column is dropped as soon as a user intentionally creates a column.
        # The self.__first_column_created member is used to determine whether or not a user has
        # added a column.
        self.__embedded_db.create_table(self.__db_table_name, "'Col 0' 'TEXT'")
        self.__first_column_created = False
        self.__arranged_columns = None

    @override(BasePart)
    def get_snapshot_for_edit(self) -> {}:
        data = super().get_snapshot_for_edit()
        data['records'] = self.get_all_data(flag_omit_rec_id=True)
        data['col_names'] = self.get_column_names()
        data['col_types'] = [self.get_column_type(col_name)[0] for col_name in data['col_names']]
        data['col_sizes'] = [self.get_column_type(col_name)[1] for col_name in data['col_names']]
        data['col_indexes'] = deepcopy(list(self.get_indices().values()))
        data['filter'] = self.get_filter_string()
        data['display_order'] = deepcopy(self.get_display_order())
        data['sorted_column'] = deepcopy(self.get_sorted_column())
        return data

    @override(BasePart)
    def _receive_edited_snapshot(self, submitted_data: Dict[str, Any], order: List[str] = None):
        super()._receive_edited_snapshot(submitted_data, order=order)

        try:
            # suppress intermediate methods of signalling GUI before full update
            self.__flag_notify_gui = False

            # Apply edits to back-end table data
            try:
                # Remove the old table if it exists
                self.__drop_table(emit_signal=False)
            except TablePartSQLiteTableNotFoundError:
                # If table does not exist, then one will be created when columns are added below
                pass

            # Create new table and add columns
            col_names = submitted_data['col_names']
            col_types = submitted_data['col_types']
            col_sizes = submitted_data['col_sizes']
            for col, col_name in enumerate(col_names):

                col_type = col_types[col].upper()
                col_size = col_sizes[col]
                if len(col_type) != 0 and col_size != 0:
                    self.add_column(col_name, col_type, col_size)
                elif len(col_type) != 0:
                    self.add_column(col_name, col_type)
                else:
                    self.add_column(col_name)

            # Add the data
            self.insert_many(submitted_data['records'])

            # Index the columns
            column_indices = {str(temp_index): col_index
                              for temp_index, col_index in enumerate(submitted_data['col_indexes'])}
            self.set_indices(column_indices)

            # Apply the filter
            sql_filter_command = submitted_data['filter']
            self.set_filter_string(sql_filter_command)

            # Store the display order for the GUI
            self.__display_order = submitted_data['display_order']
            self.__sorted_column = submitted_data['sorted_column']

            # Update the front-end table widget
            self.signals.sig_full_table_changed.emit()

        finally:
            self.__flag_notify_gui = True

    @override(BasePart)
    def get_matching_properties(self, re_pattern: str) -> List[str]:
        """
        Extend basic search to add first column name that has data that matches pattern, if any,
        and to check if search has been interrupted after every N rows.
        """
        matches = BasePart.get_matching_properties(self, re_pattern)

        num_rows_to_search = 100
        for first_row_to_search in range(0, self.get_number_of_records(), num_rows_to_search):
            matching_column_name = self.__embedded_db.table_data_matches(self.__db_table_name,
                                                                         re_pattern,
                                                                         first_row=first_row_to_search,
                                                                         num_rows=num_rows_to_search)
            if matching_column_name is not None:
                matches.append("column[{}]".format(matching_column_name))
                break

            if self._shared_scenario_state.is_search_cancelled():
                break

        return matches

    def get_display_order(self) -> DisplayOrderEnum:
        """
        Gets the current display order for the GUI table data.
        :return: the display order of the selected column.
        """
        return self.__display_order

    def get_sorted_column(self) -> List[int]:
        """
        Gets the current sorted column.
        :return: the display order of the selected column.
        """
        return self.__sorted_column

    def does_internal_sql_lite_table_exist(self):
        """
        This method is used to determine whether or not a SQLite database table exists for this instance of the Table
        Part.
        :return:  Boolean indicating whether or not a SQLite database table exists for this instance of the Table Part.
        """
        return self.__embedded_db.does_table_exist(self.__db_table_name)

    def get_embedded_db(self) -> EmbeddedDatabase:
        """
        Get the embedded database.
        :return: The embedded database.
        """
        return self.__embedded_db

    def get_database_table_name(self) -> str:
        """
        Get the name of the table of this instance in the SQLite database.
        :return:  The name of the database.
        """
        return self.__db_table_name

    def get_field_names(self) -> List[str]:
        """
        This method is used to get the columns of this table.
        This method is for Prototype compatibility.
        :return: A list of column names.
        """
        return self.get_column_names()

    def get_column_names(self) -> List[str]:
        """
        Get the names of the columns in this Table Part.
        :return: A list of column names.
        """
        index_of_column_name = 1

        if self.__arranged_columns:
            return self.__arranged_columns
        else:
            return [column[index_of_column_name] for column in self.get_cols_schema()]

    def get_column_types(self, col_subset: List[str] = None) -> List[str]:
        """
        Get the data types of columns in this Table Part.
        :param col_subset: An optional list of column names to specify which specific column types to return.
        :return: A list containing the data types in this Table Part.
        """
        index_name = 1
        index_type = 2
        if col_subset is None:
            types_list = [col[index_type] for col in self.get_cols_schema()]
        else:
            types_list = [col[index_type] for col in self.get_cols_schema() if col[index_name] in col_subset]

        return types_list

    def get_column_names_and_types(self) -> List[str]:
        """
        This method is used to get the columns and types in a list ie ["Col1 varchar(200)", "Col2 real(100)", "Col3"]
        :return: A list containing this instance of the table parts column and type.
        """
        columns_name_and_type = []
        column_names = self.get_column_names()
        column_types = self.get_column_types()
        assert len(column_names) == len(column_types)

        num_cols = len(column_names)

        for index in range(num_cols):
            if column_types[index]:
                columns_name_and_type.append(column_names[index] + " " + column_types[index])
            else:
                columns_name_and_type.append(column_names[index])

        return columns_name_and_type

    def get_num_columns(self) -> int:
        """
        This function returns the number of columns in the Table Part.
        :return: The number of columns.
        """
        return self.__embedded_db.get_num_columns(self.__db_table_name)

    def add_column(self, column_name: str, column_type: str = None, column_size: int = None):
        """
        Method used to add a column to this Table Part.
        :param column_name: Name of column to add.
        :param column_type: The type of this new column.
        :param column_size: Size of the column, if it is varchar.
        """
        if not self.__first_column_created:
            # Because self.__first_column_created is False, the user has not intentionally added a column to the
            # instance of this Table Part yet.
            # When the instance of this Table Part was created, a SQLite database table with a
            # 'default' column was created.  That table (with the default column) can now be dropped.  A SQLite table
            # for this instance of the Table Part can then be created with a user defined column.
            self.__embedded_db.drop_table(self.__db_table_name)
            self.__first_column_created = True

            if self._anim_mode_shared:
                self.signals.sig_full_table_changed.emit()

        pattern_name = "({}{}*)".format(self.RE_COL_NAME_FIRST_CHAR, self.RE_COL_NAME_REST_CHAR)

        if re.search(pattern_name, column_name) is not None:
            col_name = re.search(pattern_name, column_name).group(1)
        else:
            col_name = column_name

        col_name = col_name.strip()
        if column_type is not None:
            column_type = column_type.upper()

        if not self.__embedded_db.does_table_exist(self.__db_table_name):
            size_type = None
            if column_type is not None and column_size is not None:
                size_type = "{}({})".format(column_type, column_size)
            elif column_type is not None and column_size is None:
                size_type = "{}".format(column_type)

            if size_type:
                self.__embedded_db.create_table(self.__db_table_name, "'{}' {}".format(col_name, size_type))
            else:
                self.__embedded_db.create_table(self.__db_table_name, "'{}'".format(col_name))
        else:
            self.__embedded_db.add_column(self.__db_table_name, col_name, column_type=column_type,
                                          column_size=column_size)

        if self._anim_mode_shared and self.__flag_notify_gui:
            self.signals.sig_col_added.emit(col_name, column_type, column_size)

    add_field = prototype_compat_method_alias(add_column, 'add_field')

    def set_columns(self, fields: str):
        """
        This method is used add columns to this Table Part. The fields must be valid specifications accepted by the
        SQLite "CREATE TABLE" statement.
        :param fields: A list of tuples in the form "ID INTEGER, Name TEXT, Age REAL..."]
        """
        if fields:
            if not self.__embedded_db.does_table_exist(self.__db_table_name):
                self.__embedded_db.create_table(self.__db_table_name)
            else:
                # first remove all data...
                self.delete_data()

                # ...then drop all of the existing columns
                # note when all columns are removed, table is dropped!
                columns = self.get_column_names()
                for column in columns:
                    self.drop_column(column)

            re_col_type = "[a-zA-Z]"
            re_col_size = "[0-9]"
            re_pattern_name_type_size = "({}{}*)\s({}+)\(({}+)\)".format(self.RE_COL_NAME_FIRST_CHAR,
                                                                         self.RE_COL_NAME_REST_CHAR,
                                                                         re_col_type, re_col_size)

            # Pattern to match a declaration of a column that contains the name and type, but not size.
            # For example, "ID varchar" will match, but "ID varchar(200)" will not.  Neither will just "ID"
            pattern_name_type = "({}{}*)\s({}+)".format(self.RE_COL_NAME_FIRST_CHAR, self.RE_COL_NAME_REST_CHAR
                                                        , re_col_type)

            columns = fields.split(",")

            # Now add all of the new columns.
            for column in columns:
                column_name = None
                column_type = None
                column_size = None

                if re.search(re_pattern_name_type_size, column) is not None:
                    column_name, column_type, column_size = re.search(re_pattern_name_type_size, column).groups()
                elif re.search(pattern_name_type, column) is not None:
                    column_name, column_type = re.search(pattern_name_type, column).groups()
                else:
                    # If the regex did not match either one of the first two patterns, then there is nothing
                    # to do to figure out what the column is.
                    column_name = column

                self.add_column(column_name.strip(), column_type, column_size)

    set_fields = prototype_compat_method_alias(set_columns, 'set_fields')

    def set_column_names_and_types(self, columns: List[str]):
        """
        This method is the counter part of get_column_names_and_types. See its docstring for the syntax of
        the column specification. For example, both 'last_name varchar(100)' and 'last_name' are valid column
        specifications.
        :param columns: A list containing comma delimited column specifications.
        """
        self.set_columns(",".join(columns))

    def arrange_columns(self, column_names: str = None):
        """
        This method is used to re-arrange the fields in this Table Part.
        If a column does not appear in column_names but is part of the current table schema,
        then the column and data is not fetched from this table.
        :param column_names:  Comma delimited column names.
        """
        self.__arranged_columns = self.__embedded_db.arrange_columns(self.__db_table_name, column_names)
        if self._anim_mode_shared:
            self.signals.sig_full_table_changed.emit()

    arrange_fields = prototype_compat_method_alias(arrange_columns, 'arrange_fields')

    def drop_column(self, column_name: str):
        """
        Method used to remove a column from this Table Part.
        :param column_name: Name of column to remove from this Table Part.
        """
        self.__embedded_db.drop_column(self.__db_table_name, column_name)
        self.__alter_index_container(column_name)

        if self._anim_mode_shared:
            self.signals.sig_col_dropped.emit(column_name)

    remove_field = prototype_compat_method_alias(drop_column, 'remove_field')

    def get_column_type(self, column_name: str) -> str:
        """
        Method used to get the type of a column in this Table Part.
        :param column_name: Name of the column to the type of.
        :return: The date type of the column.
        """
        return self.__embedded_db.get_column_type(self.__db_table_name, column_name)

    get_field_type = prototype_compat_method_alias(get_column_type, 'get_field_type')

    def get_cols_schema(self) -> List[ColumnSchema]:
        """
        This method is used to get all of the columns (with their full column schema) for this Table Part.
        :return:  A list of tuples where each tuple represents a single column.  A tuple contains the
            column id, name, type, whether or not it can be null, the columns default value, and whether
            or not the column is a primary key.
        """
        return self.__embedded_db.get_columns_schema(self.__db_table_name)

    def rename_column(self, current_column_name: str, new_column_name: str):
        """
        This method is used to change a columns name from current_column_name to new_column_name
        :param current_column_name: The name of the column to change.
        :param new_column_name: The columns new name.
        """
        self.__embedded_db.rename_column(self.__db_table_name, current_column_name, new_column_name)
        has_index_changed = self.__alter_index_container(current_column_name,
                                                         rename=True,
                                                         new_column_name=new_column_name)

        if self._anim_mode_shared:
            self.signals.sig_col_name_changed.emit(current_column_name, new_column_name)
            if has_index_changed:
                self.signals.sig_index_added.emit([new_column_name])

        # If a rename occurs of the 'default' column, then need to indicate that the first column has been created.
        self.__first_column_created = True

    rename_field = prototype_compat_method_alias(rename_column, 'rename_field')

    def column_exists(self, column_name: str) -> bool:
        """
        This method is used to determine whether or not a column with the given name exists within this Table Part.
        :param column_name: The column to find.
        :return: Boolean indicating whether or not the given column exists within this Table Part.
        """
        return self.__embedded_db.column_exists(self.__db_table_name, column_name)

    def exists(self, where: str):
        """
        This method is used to determine whether or not a record exists satisfying the given where clause.
        :param where: A where clause used to restrict the record to find.
        :return:  Boolean indicating whether or not a record exists restricted by the where clause.
        """
        return self.__embedded_db.record_exists(self.__db_table_name, where)

    def insert_many(self, records: List[DbRawRecord]):
        """
        This method is used to insert many records at once.
        :param records: A list of tuples containing the values to insert.
        """
        # TODO build 3: this should use parametrized SQL statement on the list of records
        for record in records:
            self.insert(*record)

    def insert(self, *record: DbRawRecord):
        """
        This method is used to insert a record into this Table Part.
        :param record: The record to insert.
        """
        self.__embedded_db.insert(self.__db_table_name, record)
        if self._anim_mode_shared and self.__flag_notify_gui:
            last_record_id = self.__embedded_db.get_last_record_id(self.__db_table_name)
            self.signals.sig_record_added.emit(last_record_id, record)

    def insert_all(self, columns: List[str], records: List[DbRawRecord]):
        """
        This method is used to insert records into particular columns in this Table Part.
        :param columns: The columns to be affected.
        :param records: The records to write into the table.
        """
        self.__embedded_db.insert_all(self.__db_table_name, columns, records)
        if self._anim_mode_shared:
            self.signals.sig_full_table_changed.emit()

    def select(self, fields: str = "*", where: str = None, limit: int = None,
               select_raw: bool = False) -> Either[SqlDataSet, DbRawRecords]:
        """
        Query the table for data.

        :param fields: A set of fields to select on. Fields that have spaces must be square-bracketed. By default,
            all fields of the table are selected.
        :param where: (optional) A SQL "where" clause restricting the data retrieved.
        :param limit: (optional) The maximum number of record to be returned.
        :param select_raw: True to return a list of tuples instead of a SqlDataSet instance (the default).

        :return the result data set.

        Example: table.select('age, [new rank]', where='age > 25 and [new rank] ~ "mcp"')
        """
        # If where parameter is not supplied, then the entire Table (ie all of the rows within the Table part) will
        # be selected.  Otherwise, the selected rows will be limited to the rows that match the where clause.
        # If limit parameter is not supplied, then all of the rows that match the where clause will be returned (if
        # a where clause was supplied).  If a limit parameter is supplied, then the number of records selected will
        # be limited to the supplied limit ceiling.
        return self.__embedded_db.select(table_name=self.__db_table_name,
                                         fields=fields,
                                         where=where,
                                         limit=limit,
                                         select_raw=select_raw)

    def update(self, new_field_value_pairs: str, where: str = None):
        """
        This method is used to update particular field(s) in a given row.  Note that it is up to the user to ensure
        that the where clause is correctly constructed.
        :param new_field_value_pairs: Field-value pair(s) in the form "field1=value1,field2=value2..."
        :param where: An optional where clause.

        ID   Country  Population  CapitalCity
         --   -------  ----------  ----------
         1   Canada   32,000,000  Ottawa
         2   US      320,000,000  Washington
         3   Germany      10,000  Berlin

        For example, in the above table, if one were to update Germany's population to 80,000,000
        the call would be table_part.update("Population='8000000'", where="ID='3'").
        """
        self.__embedded_db.update(self.__db_table_name, new_field_value_pairs, where=where)
        if self._anim_mode_shared:
            self.signals.sig_full_table_changed.emit()

    def update_field(self, record_id: int, col_name: str, new_field_value: Any):
        """
        This method is used to update a particular field in given row.
        :param record_id: The id of the row to update a particular column's field value.
        :param col_name: The name of the column in which the field update is to occur.
        :param new_field_value: The new value of the field, depending on the type of the field, this could be a string
        or a integer or a datetime etc.

         ID   Country  Population  CapitalCity
         --   -------  ----------  ----------
         1   Canada   32,000,000  Ottawa
         2   US      320,000,000  Washington
         3   Germany      10,000  Berlin

        For example, in the above table, if one were to update Germany's population to 80,000,000
        the call would be table_part.update_field(3, 'Population', '80,000,000').
        """

        self.__embedded_db.update_field(self.__db_table_name, record_id, col_name, new_field_value)
        if self._anim_mode_shared:
            if col_name.startswith('[') and col_name.endswith(']'):
                col_name = col_name.strip('[]')

            self.signals.sig_field_changed.emit(record_id, col_name, str(new_field_value))

    def get_unique_ids(self) -> List[int]:
        """
        Gets a list of all of the unique ids in this Table Part.
        :return: A list of unique ids.
        """
        return self.__embedded_db.get_unique_ids(self.__db_table_name)

    def count(self, where: str = None) -> int:
        """
        This method is used to count the number of records that match a specific where clause.
        This method is for Prototype compatibility.
        :param where: A where clause restricting the records.
        :return: The number of records that match the where clause.
        """
        return self.__embedded_db.count(self.__db_table_name, where)

    def get_number_of_records(self) -> int:
        """
        Get the number of records in this Table Part.
        :return: The number of records.
        """
        return self.__embedded_db.count(self.__db_table_name, "")

    def get_all_data(self, flag_omit_rec_id: bool = False, flag_apply_filter: bool = False) -> List[DbRawRecord]:
        """
        Get all of the data (records) in this Table Part.
        :param flag_omit_rec_id: flag to specify whether the record ID should not be included.
        :param flag_apply_filter: flag to specify whether the current filter should be applied on the data.
        :return: A list of data, each data record is a tuple.
        """
        # Special case for prototype compatibility.  If the prototype Scenario contains an empty Table Part, the
        # database for this empty Table Part must be created before the GUI can try to access the data.
        if not self.__embedded_db.does_table_exist(self.__db_table_name):
            self.__embedded_db.create_table(self.__db_table_name)

            if self._anim_mode_shared:
                self.signals.sig_full_table_changed.emit()

        if flag_apply_filter:
            data = self.__embedded_db.get_all_data(self.__db_table_name, table_filter=self.__filter,
                                                   arranged_columns=self.__arranged_columns)
        else:
            data = self.__embedded_db.get_all_data(self.__db_table_name, arranged_columns=self.__arranged_columns)

        if flag_omit_rec_id:
            for idx, rec in enumerate(data):
                rec_no_id = rec[1:]
                data[idx] = rec_no_id

        return data

    def set_all_data(self, data_rows: List[DbRawRecord]):
        """
        Set all of the data (records) in this Table Part.
        Removes all data from this instance of the table part and insert the new passed in 'data_rows'.
        :param data_rows: The new data to insert into the table.
        """
        self.remove_all_data()

        if data_rows:
            for data_row in data_rows:
                self.insert(*data_row)

    def get_table_subset(self, col_subset: List[str]) -> List[DbRawRecord]:
        """
        Get the set of table data corresponding to the selected columns and table filter.
        :param col_subset: A subset of columns to select from the database.
        :return: A list of data, each data record is a tuple.
        """
        assert self.__embedded_db.does_table_exist(self.__db_table_name)

        sql_filter = self.__filter if self.__filter else None

        if sql_filter is None:
            data = self.__embedded_db.get_table_subset(self.__db_table_name, col_subset)
        else:
            data = self.__embedded_db.get_table_subset(self.__db_table_name, col_subset, sql_filter)

        return data

    def get_last_record_id(self) -> int:
        """
        Get the record with the max unique id.
        :return: The unique of the record with the max id.
        """
        return self.__embedded_db.get_last_record_id(self.__db_table_name)

    def get_record_item(self, record_id: int, column: str) -> str:
        """
        Method used to get the field for a particular record for a given column within a given table.
        :param record_id: The id of the record to retrieve data for.
        :param column: The column to retrieve the data for.
        :return: The data for the intersection of the row and column.
        """
        return self.__embedded_db.get_record_item(self.__db_table_name, record_id, column)

    def get_record_subset(self, start_row_id: int = 1, limit: int = 100, flag_apply_filter=False) -> List[DbRawRecord]:
        """
        Gets a subset of records from the database starting at the provided record ID.
        :param start_row_id: the first row to retrieve (default is the first row in the table).
        :param limit: the maximum number of rows to return.
        :param flag_apply_filter: flag to specify whether the current filter should be applied on the data.
        :return: a list of records.
        """
        if not self.__embedded_db.does_table_exist(self.__db_table_name):
            self.__embedded_db.create_table(self.__db_table_name)

        if flag_apply_filter:
            records = self.__embedded_db.get_record_subset(self.__db_table_name, start_row_id, limit,
                                                           table_filter=self.__filter,
                                                           arranged_columns=self.__arranged_columns)
        else:
            records = self.__embedded_db.get_record_subset(self.__db_table_name, start_row_id, limit,
                                                           arranged_columns=self.__arranged_columns)

        return [list(rec) for rec in records]

    def get_row_ids(self) -> List[int]:
        """
        Gets the list of row IDs for the records in the database. Apply filter if set.
        :return: the list of row IDs.
        """
        if self.__embedded_db.does_table_exist(self.__db_table_name):
            ids = self.__embedded_db.get_row_ids(self.__db_table_name, table_filter=self.__filter)
            return [i[0] for i in ids]  # Converts the list of tuples to a list of ints and returns

    def remove_all_data(self):
        """
        Method used to clear the contents of this Table Part.
        """
        self.__embedded_db.remove_all_data(self.__db_table_name)

        if self._anim_mode_shared:
            self.signals.sig_full_table_changed.emit()

    def delete_data(self, where: str = None):
        """
        This method is used to delete records given a certain where clause.  If a where clause is not supplied, then
        this method would effectively be the same as remove_all_data().  Otherwise, this method will only delete
        rows that match the specified where criteria.
        :param where: A where clause restricting the records to delete.
        """
        if self.__embedded_db.does_table_exist(self.__db_table_name):
            self.__embedded_db.delete_data(self.__db_table_name, where=where)
            if self._anim_mode_shared:
                self.signals.sig_full_table_changed.emit()

    def remove_record(self, unique_id: int):
        """
        Method used to remove a single record based on its unique_id.
        :param unique_id: The unique id of the record to remove.
        """
        self.__embedded_db.remove_record(self.__db_table_name, unique_id)
        if self._anim_mode_shared:
            self.signals.sig_record_removed.emit(unique_id)

    def create_index(self, column_name: str):
        """
        This method is used to create an index on a given column.
        This method is used for Prototype compatibility.
        :param column_name: The name of one or more column(s) to create an index for.
        :raises TablePartIndexExistsError: Exception raised when an attempt is made to create an index on a column that
            has already been indexed.
        """
        # In the prototype, create_index and drop_index simply take a list of columns.
        # In the embedded database, the index name that is generated is in the form table__indexname, where
        # indexname (if not supplied) is 'Index_?' where ? is the current self.__index_counter.  The problem
        # arises when the user wishes to drop an index that had already been created, they won't know what
        # the generated index name was.  As a result, Table Parts keep a key-value dictionary with the
        # generated database index name and the columns that were indexed on using the self.__indices dictionary.
        if self.INDEX_COL_NAMES_SEP in column_name:
            columns_list = [col.strip() for col in column_name.split(self.INDEX_COL_NAMES_SEP)]
        else:
            columns_list = [column_name]

        try:
            return self.__create_index(columns_list)
        except Exception as exc:
            log.error(exc)

    def drop_index(self, list_of_columns: str, pop: bool = True):
        """
        This method is used to drop an index from this Table Part.
        :param list_of_columns: A string of comma separated column name(s) to drop.
        :param pop: This optional switch allows the caller to pop the index_key out of the self.__indices,
            instead of doing it here.  This is useful when wanting to remove an item while looping over a container - ie
            instead of removing the item during the loop, first loop through the container to identify the item to
            remove, then once exited from the loop, remove the item from the container.
        """
        if self.__indices:
            if self.INDEX_COL_NAMES_SEP in list_of_columns:
                list_of_columns = [column.strip() for column in list_of_columns.split(self.INDEX_COL_NAMES_SEP)]
            else:
                list_of_columns = [list_of_columns]

            try:
                self.__drop_index(list_of_columns, pop)
            except Exception as exc:
                log.error(exc)

    def index_exists(self, index_name: str) -> bool:
        """
        This method is used to check if an index with the given name already exists within this Table Part.
        :param index_name: Name of index to check if it already exists.
        :return: Boolean indicating whether or not a an index exists with the given name within this Table Part.
        """
        if index_name in self.__indices:
            return True
        else:
            return False

    def index_exists_on_columns(self, columns: str) -> bool:
        """
        This method is used to check whether or not an index exists for the provided column(s).
        :param columns: List of comma separated columns.
        :return: Boolean indicating whether or not an index exists for the provided columns within this Table Part.
        """

        found = False
        columns_in_list = [column.strip() for column in columns.split(self.INDEX_COL_NAMES_SEP)]
        for index in self.__indices:
            if self.__indices[index] == columns_in_list:
                found = True
                break

        return found

    def get_indices(self) -> Dict[str, List[str]]:
        """
        Get the list of indexes and the associated columns.
        :return: A dictionary containing key value pairs where the key is the index name and value is a list
            of columns.
        """
        return self.__indices

    def set_indices(self, col_indices: Dict[str, List[str]], is_new_index: bool = True):
        """
        Set the indices on this table. Drops any previous indices.
        :param col_indices: A dictionary of indexed columns.
        :param is_new_index: A flag to indicate if index created is new.
        """
        # first remove any previous indices:
        for index in self.__indices:
            self.__drop_index(self.__indices[index], False)

        # create new ones:
        self.__indices = {}

        bad_indices = []
        for index_name, index_cols in col_indices.items():
            if self.__check_index_valid(index_cols):
                self.__create_index(index_cols, index_name, is_new_index)
            else:
                bad_indices.append(index_name)

        if bad_indices:
            max_show = 10
            msg = ["The following indices on table {} could not be created because some of their referenced columns "
                   "do not match any column names:  ".format(self.name)]
            bad_index_msg_list = ['- Index name "' + bad_index + '": column(s) "' + str(col_indices[bad_index]) + '"'
                                  for bad_index in bad_indices[:max_show]]
            bad_index_msg_list.sort()
            msg.extend(bad_index_msg_list)
            if len(bad_indices) > max_show:  # cap the list at 10 for practicality
                msg.append(' plus {} more...'.format(len(bad_indices) - max_show))

            raise ValueError('\n'.join(msg))

    def __check_index_valid(self, indexed_cols: List[str]) -> bool:
        """
        Check if the index is valid by comparing the column names in the index to the list of column names in the table.
        :param indexed_cols: The set of indexed columns to check.
        :return: True if indices are valid and False otherwise.
        """
        for col_name in indexed_cols:
            if col_name not in self.get_column_names():
                return False  # at least one 'bad' column invalidates whole index

        return True

    def report_fields_and_data(self) -> str:
        """
        This method is used to get the columns and data for this Table Part.
        :return:  A new line separated tuple that contains the columns and data of this part.
        """
        columns = self.get_column_names()
        all_data = self.get_all_data()

        report = "({})".format(" ,".join(columns))
        for data in all_data:
            items_joined = "({})".format(" ,".join(str(item) if len(str(item)) > 0 else "None" for item in data[1:]))
            report += "\n ({})".format(items_joined)

        return report

    def export_to_msaccess(self, file_name: PathType, to_table_name: str, selected_cols: List[str] = None):
        """
        Method used to export a table to an access database file.
        :param file_name: Name of file into which the contents of this Table Part will be exported to in the given
        to_table_name.
        :param to_table_name: Name of the table to export to in the access database.
        :param selected_cols: An optional list of specified columns to import from the table, otherwise, exports ALL.
        """
        if selected_cols is None:
            # export everything
            export_to_msaccess(self.get_column_names(), self.get_column_types(),
                               self.get_all_data(flag_omit_rec_id=True), file_name, to_table_name)
        else:
            # export only the selected columns
            export_to_msaccess(selected_cols, self.get_column_types(selected_cols),
                               self.get_table_subset(selected_cols), file_name, to_table_name)

    def import_from_msaccess(self,
                             path: PathType,
                             from_table_name: str,
                             selected_cols: List[str] = None,
                             sql_filter: str = None):
        """
        Method used to import an access database file into a SQLite database.
        :param path: The path to the access database file.
        :param from_table_name: The from_table_name of the table to import.
        :param selected_cols: A list of columns to import from the table.
        :param sql_filter: A SQL 'WHERE' clause to filter the data imported.
        """
        columns_schema, data = import_from_msaccess(path, from_table_name, selected_cols, sql_filter)

        # create new set of columns:
        self.__embedded_db.drop_table(self.__db_table_name)
        for column_info in columns_schema:
            self.add_column(*column_info)

        # add data:
        self.set_filter_string('')  # reset the filter
        self.insert_all(self.get_column_names(), data)

        if self._anim_mode_shared:
            self.signals.sig_full_table_changed.emit()

    @override(BasePart)
    def on_removing_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        super().on_removing_from_scenario(scen_data, restorable=restorable)
        if not restorable:
            self.__drop_table()

    @override(BasePart)
    def on_scenario_shutdown(self):
        self.__embedded_db.drop_table(self.__db_table_name)

    def filter(self, table_filter: str):
        """
        Method to be able to set the filter through scripts.
        :param table_filter: A valid sql filter string.
        """
        self.set_filter_string(table_filter)
        self.signals.sig_full_table_changed.emit()

    def get_filter_string(self) -> str:
        """
        Gets the filter string for filter requests.
        :return: a string that represents the filter that will be applied in other calls such as get_all_data().
        """
        return self.__filter

    def set_filter_string(self, table_filter: str):
        """
        Sets the filter string to apply on the data.
        :param table_filter: a string that represents the filter that will be applied in other calls such as
        get_all_data().
        """
        if table_filter != self.__filter:
            self.__filter = table_filter
            if self._anim_mode_shared:
                self.signals.sig_filter_changed.emit()

    def dump_schema(self):
        """
        Dumps the schema of this database. Used for debugging purposes only.
        """
        self.__embedded_db.dump_schema()

    import_from_access = prototype_compat_method_alias(import_from_msaccess, 'import_from_access')
    export_to_access = prototype_compat_method_alias(export_to_msaccess, 'export_to_access')
    delete = prototype_compat_method_alias(delete_data, 'delete')

    # --------------------------- instance PUBLIC properties ----------------------------

    embedded_db = property(get_embedded_db)
    database_table_name = property(get_database_table_name)
    indices = property(get_indices, set_indices)
    data = property(get_all_data, set_all_data)
    column_types = property(get_column_types)
    column_names = property(get_column_names)
    column_names_and_types = property(get_column_names_and_types, set_column_names_and_types)
    filter_string = property(get_filter_string, set_filter_string)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SEARCHING_API_EXTEND = (column_names,)
    META_AUTO_ORI_DIFFING_API_EXTEND = ()
    META_AUTO_SCRIPTING_API_EXTEND = (
        database_table_name, get_database_table_name,
        indices, get_indices, set_indices,
        data, get_all_data, set_all_data, delete_data,
        column_types, get_column_types,
        column_names, get_column_names, set_column_names_and_types, get_column_names_and_types, arrange_columns,
        add_column, drop_column, rename_column, set_columns,
        filter_string, get_filter_string, set_filter_string,
        update, select, insert, count,
        import_from_msaccess, export_to_msaccess,
        create_index, drop_index,
        filter,
    )

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        column_names = part_content[TpKeys.COLUMN_NAMES]
        column_types = part_content[TpKeys.COLUMN_TYPES]

        # The following for loop is basically to guard against Scenario's that may contain
        # tables with one or more columns with empty names.  In this case we replace
        # those columns with our default column name.
        default_index = 0
        for col in column_names:
            if '' in column_names:
                index = column_names.index(col)
                column_names[index] = "Col {}".format(default_index)
                column_types[index] = "TEXT"
                default_index += 1

        if not self.__embedded_db.does_table_exist(self.__db_table_name):
            if (len(column_names)) > 0:
                # Only create the table if table doesn't exist and has columns.
                # (Otherwise table and column get created when a new column is added after the ORI has been loaded)
                column_and_type = column_names[0]
                if column_types:
                    column_and_type += " " + column_types[0]
                self.__embedded_db.create_table(self.__db_table_name, columns=column_and_type)
        else:
            self.__drop_table()

        # table data columns:
        # The column could be defined in either one of two forms: with or without column size.
        # If the column is defined without a column size, then the pattern to match is simply
        # the data type of the column (ie varchar, real).  If the column has been defined with
        # a size, then the data type of the column will look like - as an example - varchar(200).
        pattern = r"([a-zA-Z]+)\(([0-9]+)\)"
        for column, column_type in zip(column_names, column_types):
            if re.search(pattern, column_type) is not None:
                type_name, type_size = re.search(pattern, column_type).groups()
                self.add_column(column, type_name.upper(), type_size)
            else:
                self.add_column(column, column_type.upper(), None)

        # table data:
        if part_content[TpKeys.DATA]:
            if len(column_names) == 0:
                raise RuntimeError("Data in table '{}', but no column names! Corrupt scenario?".format(self.path))

            self.insert_all(column_names, part_content[TpKeys.DATA])

        try:
            # table indices:
            ori_indices = part_content[TpKeys.INDICES]
            if ori_indices:
                self.set_indices(ori_indices, is_new_index=True)
        except ValueError as index_error:
            log.warning(index_error)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:

        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)

        data = [record for record in self.get_all_data(flag_omit_rec_id=True)]
        table_ori_def = {
            TpKeys.COLUMN_NAMES: self.get_column_names(),
            TpKeys.COLUMN_TYPES: self.get_column_types(),
            TpKeys.DATA: data,
            TpKeys.INDICES: self.get_indices(),
        }

        ori_def[CpKeys.CONTENT].update(table_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        if self.__embedded_db.does_table_exist(self.__db_table_name):
            if snapshot_slow is not None:
                # data may be huge, so create an MD5 digest of it:
                md5_table_data = self.__embedded_db.get_hash_md5(self.__db_table_name)
                # md5_table_data = md5(pickle.dumps(self.get_all_data())).hexdigest()
                snapshot_slow.update({
                    TpKeys.DATA: md5_table_data,
                })

            column_names = self.get_column_names()
            column_types = self.get_column_types()

            snapshot.update({
                TpKeys.COLUMN_NAMES: column_names,
                TpKeys.COLUMN_TYPES: column_types,
                'row_count': self.get_number_of_records(),
                TpKeys.INDICES: self.get_indices()
            })

    @override(BasePart)
    def _has_ori_changes_slow(self, baseline: JsonObj, last_get: JsonObj) -> bool:
        return baseline[TpKeys.DATA] != last_get[TpKeys.DATA]

    @override(IOriSerializable)
    def _check_ori_diffs(self, other_ori: BasePart, diffs: Dict[str, Any], tol_float: float):
        BasePart._check_ori_diffs(self, other_ori, diffs, tol_float)
        data_comparable = True

        # cell values of common cells
        col_names1 = set(self.get_column_names())
        col_names2 = set(other_ori.get_column_names())
        if col_names1 - col_names2:
            diffs['missing_columns'] = col_names1 - col_names2
            data_comparable = False
        if col_names2 - col_names1:
            diffs['added_columns'] = col_names2 - col_names1
            data_comparable = False

        if not data_comparable:
            return

        # get column names, handling those that have spaces and other illegal SQL chars, so that we can compare the
        # actual data in table:
        assert col_names1 == col_names2
        common_columns = []
        for col_name in self.get_column_names():
            common_columns.append(normalize_name(col_name))

        columns_str = ','.join(common_columns)

        log.info("Table '{}' diff: ", self.path)
        log.info("    common columns: {}", columns_str)

        # assume that first column is primary; if first N columns form a compound key, then temporarily edit the
        # primary_keys_maps as per example comment
        # TODO build 3: for proper scenario comparison, allow more config options in a setting dictionary that would contain
        #    float tol, pk_num_cols values for tables expected in the scenario that use compound keys, etc.
        primary_keys_maps = {}  # {'ACME/tablesGlobal/yearlyTotalStrengthTable': N}
        pk_num_cols = primary_keys_maps.get(self.path, 1)
        log.info("    # cols in prim key: {}", pk_num_cols)

        def get_records(seq: Either[SqlDataSet, DbRawRecords], pk_num_cols: int):
            if not seq:
                return {}

            # assumes primary keys are integers or strings; support compound keys
            first_record = seq[0]
            pk_types = []
            for key in first_record[:pk_num_cols]:
                try:
                    int(key)
                    pk_types.append(int)
                except ValueError:
                    pk_types.append(str)

            # create the dict where key is (compound) primary key and value is the remainder of the record fields
            return {tuple(sanitize_keys(x[:pk_num_cols], pk_types)): x[pk_num_cols:] for x in seq}

        def sanitize_keys(record_keys, pk_types):
            return [pk_type(key) for (pk_type, key) in zip(pk_types, record_keys)]

        # loop over all our records, finding the one of matching primary key in the other set of records
        records1 = get_records(self.select(columns_str, select_raw=True), pk_num_cols)
        records2 = get_records(other_ori.select(columns_str, select_raw=True), pk_num_cols)
        for primary_key, data1 in records1.items():
            if primary_key in records2:
                data2 = records2[primary_key]
                for col_index, (d1, d2) in enumerate(zip(data1, data2)):
                    diff = check_diff_val(d1, d2, tol_value=tol_float)
                    if diff is not None:
                        diffs['data[{}][{}]'.format(primary_key, common_columns[col_index + pk_num_cols])] = diff
            else:
                diffs['data[{}]'.format(primary_key)] = 'missing'

        keys1 = set(records1.keys())
        keys2 = set(records2.keys())
        missing_other = keys2 - keys1
        for key in missing_other:
            diffs['data[{}]'.format(key)] = 'added record'

    def __create_index(self, columns: List[str],
                       index_name: str = None,
                       is_new_index: bool = True) -> str:
        """
        This method is used to create an index on the given columns.
        :param index_name: The name of the new index (automatically generated, if not given)
        :param columns: A list of columns.
        :param is_new_index: A flag to indicate if index created is new.
        :return: name of index (same as index_name if given, else the name automatically generated)
        """
        # Parametrized execution of SQL would prevent the need to do the below clean up of single quotes.
        sanitized_columns = [col.replace("'", "") if "'" in col else col for col in columns]

        index_name = self.__embedded_db.create_index(self.__db_table_name, index_name, columns=sanitized_columns,
                                                     new_index=is_new_index)
        self.__indices[index_name] = columns

        if self._anim_mode_shared and self.__flag_notify_gui:
            self.signals.sig_index_added.emit(columns[:])

        return index_name

    def __drop_index(self, columns: List[str], pop: bool):
        """
        This method is used to drop an index from this Table Part.
        :param columns: A list of column name(s) strings to drop.
        :param pop: This switch allows the caller to pop the index_key out of the self.__indices,
            instead of doing it here.  This is useful when wanting to remove an item while looping over a container - ie
            instead of removing the item during the loop, first loop through the container to identify the item to
            remove, then once exited from the loop, remove the item from the container.
        """
        if self.__indices:

            for index_key in self.__indices:
                if self.__indices[index_key] == columns:
                    self.__embedded_db.drop_index(index_key)
                    log.info("Index dropped for columns '{}' on table '{}'.", columns, self.name)
                    if self._anim_mode_shared:
                        self.signals.sig_index_dropped.emit(columns[:])
                    break

            if pop:
                self.__indices.pop(index_key)
        else:
            message = "There are no indices for this table part. "
            message += "Can't drop index for '{}'.".format(columns)
            log.info(message)
            return

    def __drop_table(self, emit_signal: bool = True):
        """
        Private helper method to clear all data and columns from this Table Part.  The emit_signal flag is used
        to tell/signal the front end whether or not to update itself.  Any existing indices on columns will be
        automatically dropped when the table (that the column exists in) is dropped.
        """
        self.__embedded_db.drop_table(self.__db_table_name)
        self.__indices = {}
        self.__index_counter = 0
        self.__filter = str()
        self.__display_order = DisplayOrderEnum.of_creation
        self.__sorted_column = [0]

        if emit_signal and self._anim_mode_shared:
            self.signals.sig_full_table_changed.emit()

    def __alter_index_container(self, column_affected, rename: bool = False, new_column_name: str = None) -> bool:
        """
        Helper method to remove a column from the container that holds a list of indices.
        :param column_affected The name of the column that is being dropped or renamed.
        :param rename Boolean indicating whether or not a rename operation is happening.
        :param new_column_name If a rename is occurring, this will hold the new name of the column.
        :returns a flag that indicates if a column name in an index has been renamed.
        """
        index_to_pop = []
        has_index_changed = False
        for index_name in self.__indices:
            column_index = self.__indices[index_name]
            if column_affected in column_index:
                if rename:
                    column_index[column_index.index(column_affected)] = new_column_name
                    self.__indices[index_name] = column_index
                    has_index_changed = True
                else:
                    index_to_pop.append(index_name)

        # since a single column name may be in multiple indices,
        # construct a list to ensure front-end only gets a dropped
        # column index once
        columns = set()
        for index_name in index_to_pop:
            columns.update(self.__indices[index_name])
            self.__indices.pop(index_name)

        if self._anim_mode_shared and columns:
            self.signals.sig_index_dropped.emit(columns)

        return has_index_changed

    def __do_all_columns_exist(self, columns_list: List[str]):
        """
        Helper method used determine whether or not one or more columns exist within this instance of the table part.
        :param columns_list: A list of one or more columns.
        :return: Boolean indicating whether or not one or more columns exist in this instance of the table part.  If
            multiple columns are supplied to this method and if any one of them are not found in this instance of
            the table part, then return will be False.
        """
        current_columns = self.get_column_names()
        for col in columns_list:
            if col not in current_columns:
                return False

        return True


""" Add this part to the global part type/class lookup dictionary. """
register_new_part_type(TablePart, TpKeys.PART_TYPE_TABLE)
