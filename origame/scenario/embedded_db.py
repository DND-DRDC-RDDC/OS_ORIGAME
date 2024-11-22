# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module provides capability to interface with SQLite database engine.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import sqlite3
from sqlite3 import OperationalError as SqlOperationalError
import re

from origame.core.utils import get_valid_python_name

# [2. third-party]

# [3. local]
from .base_db import BaseDatabase, DbInvalidArrangeFieldError, DbInvalidParameterError, DbInvalidSqlError, DbSqlExecError, DbSqlNotStatementError, create_select_statement, normalize_name
from ..core.typing import Any, Either
from ..core.typing import List, Tuple
from .sql_dataset import SqlDataSet

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'EmbeddedDatabase']

log = logging.getLogger('system')

# During development, it may be useful to mock some of the SQLite engine behavior set the following to True and
# change the return value for fetchall. If fetchall is going to be called multiple times on the DB cursor (many
# methods on EmbeddedDatabase results in multiple calls to fetchall), then the sequence of return values can be
# put in a list called 'fetchall_data' in sqlite_mock_side_effects.py
USE_MOCK_SQLITE = False

TableCellData = Either[str, int, float]


# -- Function definitions -----------------------------------------------------------------------

def mock_sqlite_connect():
    from unittest.mock import patch
    patcher = patch.object(sqlite3, 'connect')
    mock_sqlite_connect = patcher.start()
    mock_sqlite_connect().cursor().fetchall.return_value = ['a', 'b', 'c']
    try:
        from .sqlite_mock_side_effects import fetchall_calls
        mock_sqlite_connect().cursor().fetchall.side_effect = fetchall_calls
    except ImportError:
        # module doesn't exist, or it does but doesn't define fetchall_calls: don't want to use side effects
        pass


if USE_MOCK_SQLITE:
    mock_sqlite_connect()


# -- Class Definitions --------------------------------------------------------------------------
class EmbeddedDatabase(BaseDatabase):
    """One instance of this class is shared by all scenario parts that need a SQL database engine."""    
    # TODO build 3 performance: convert the many sql statements used to prepared statements

    # --------------------------- class-wide data and signals -----------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        """Create the integrated database"""
        self.__conn: sqlite3.Connection = sqlite3.connect(":memory:")
        self.__cursor: sqlite3.Cursor = self.__conn.cursor()

    # @override(BaseDatabase)
    def shutdown(self):
        if self.__conn is not None:
            self.__conn.close()
            self.__conn = None
            self.__cursor = None

    # @override(BaseDatabase)
    def execute(self, sql_statement: str, params: Tuple = ()):
        try:
            self.__cursor.execute(sql_statement, params)
        except SqlOperationalError as exc:
            err_msg = "Embedded SQL statement '{}' (with params={}) exec error: {}".format(sql_statement, params, exc)
            log.error(err_msg)
            raise DbSqlExecError(err_msg)
        except sqlite3.Warning as warn:
            raise DbSqlNotStatementError(str(warn))

    # @override(BaseDatabase)
    def execute_script(self, multiple_statements: str):
        try:
            return self.__conn.executescript(multiple_statements)

        except SqlOperationalError as exc:
            statements = multiple_statements.splitlines()
            first_line = statements[0] if statements else '<empty>'
            err_msg = "Embedded SQL script (starting with '{}') exec error: {}".format(first_line, exc)
            log.error(err_msg)
            raise DbSqlExecError(err_msg)

    def __fetch_all(self) -> Tuple[List[BaseDatabase.DbRawRecord], Any]:
        data = self.__cursor.fetchall()
        description = self.__cursor.description
        return data, description

    # @override(BaseDatabase)
    def fetch_all(self) -> List[BaseDatabase.DbRawRecord]:
        data, description = self.__fetch_all()
        return data

    # @override(BaseDatabase)
    def table_data_matches(self, table_name: str, re_pattern: str, first_row: int = 0, num_rows: int = 100) -> str:
        # register the REGEXP function that SQLITE3 supports (must be user-defined)
        # note that we pre-compile the regexp for efficiency; this means the first arg to REGEXP is not needed
        import re
        regexp = re.compile(re.escape(re_pattern), re.IGNORECASE)

        def regexp_func(expr, item):
            return regexp.search(str(item)) is not None

        self.__conn.create_function("REGEXP", 2, regexp_func)

        # search all columns, return at first hit
        for column_name in [item[self.COLUMN_NAME] for item in self.get_columns_schema(table_name)]:
            safe_col_name = normalize_name(column_name)
            # in case the column name has spaces:
            where = '{} REGEXP "" AND rowid>={} AND rowid<={}'.format(safe_col_name, first_row, first_row + num_rows)
            raw_data_set = self.select(table_name, fields=safe_col_name, where=where, limit=1, select_raw=True)
            if len(raw_data_set) > 0:
                return column_name

        return None
    
    # @override(BaseDatabase)
    def add_column(self, table_name: str, column_name: str, column_type: str = None, column_size: int = None):
        # SIZEABLE_TYPES is a list of columns in a database that can have a size attribute to them.
        SIZEABLE_TYPES = ["BLOB_TEXT", "CHAR", "DATETEXT", "MEMO", "NCHAR", "INTEGER",
                          "NTEXT", "NVARCHAR", "NVARCHAR2", "REAL", "TEXT", "VARCHAR", "VARCHAR2", "WORD", "BOOLEAN"]

        sql = ""

        if not column_name:
            raise DbInvalidParameterError("Column name can not be empty/null.")

        assert not column_name.startswith(" ")
        assert not column_name.endswith(" ")

        safe_col_name = normalize_name(column_name)
        if not self.does_table_exist(table_name):
            # If a column is added via the TablePart API, it always checks to make sure that the table exists
            # prior to inserting a column.  However, we need to ensure that the table exists here in case
            # a column is attempted to be added directly via the Odbc Db.
            self.create_table(table_name, "{} {}".format(safe_col_name, column_type))
            return

        if column_type:
            assert not column_type.startswith(" ")
            assert not column_type.endswith(" ")

        if all((safe_col_name, column_type, column_size)):
            if column_type.upper() in SIZEABLE_TYPES:
                sql = "ALTER TABLE [{}] ADD {} {}({})".format(table_name, safe_col_name, column_type, column_size)
            else:
                # A type that is not sizeable (ie datetime)
                sql = "ALTER TABLE [{}] ADD {} {}".format(table_name, safe_col_name, column_type)
        elif column_type is None and column_size is None:
            sql = "ALTER TABLE [{}] ADD {}".format(table_name, safe_col_name)
        elif column_type is not None and column_size is None:
            sql = "ALTER TABLE [{}] ADD {} {}".format(table_name, safe_col_name, column_type)

        if sql == "":
            raise DbInvalidSqlError

        self.execute(sql)

    # @override(BaseDatabase)
    def add_columns(self, table_name: str, columns: List[Tuple[str, str, int]]):
        for col_name, col_type, col_size in columns:
            self.add_column(table_name, col_name, col_type, col_size)

    # @override(BaseDatabase)
    def create_table(self, table_name: str, columns: str = None):
        if columns:
            sql = "CREATE TABLE {} ({})".format(table_name, columns)
        else:
            sql = "CREATE TABLE {} ('')".format(table_name)

        self.execute(sql)

    # @override(BaseDatabase)
    def drop_table(self, table_name: str):
        sql = "DROP TABLE IF EXISTS {}".format(table_name)
        self.execute(sql)

    # @override(BaseDatabase)
    def set_table_fields(self, table_name, columns: str):
        sql = "CREATE TABLE temp ({})".format(columns)
        self.execute(sql)

        sql = "DROP TABLE {}".format(table_name)
        self.execute(sql)

        sql = "ALTER TABLE temp RENAME TO {}".format(table_name)
        self.execute(sql)

    # @override(BaseDatabase)
    def arrange_columns(self, table_name, columns: str = None):
        current_columns = [column[1] for column in self.get_columns_schema(table_name)]

        if columns is None:
            return current_columns

        arranged_columns = [column.strip() for column in columns.split(",")]

        if not set(arranged_columns).issubset(current_columns):
            msg = "One or more column(s) in the arrange_field method do not exist in this table."
            raise DbInvalidArrangeFieldError(msg)

        return arranged_columns

    # @override(BaseDatabase)
    def drop_column(self, table_name: str, column_to_drop: str):
        columns_with_schema = self.get_columns_schema(table_name)
        columns_remaining = [(col_id, col_name, col_type, not_null, default_value, primary_key)
                             for col_id, col_name, col_type, not_null, default_value, primary_key in columns_with_schema
                             if col_name != column_to_drop]

        self.__generate_table_with_data(table_name, columns_remaining, dropped_column=column_to_drop)

    # @override(BaseDatabase)
    def rename_column(self, table_name: str, column_to_rename: str, new_name: str):
        columns_with_schema = self.get_columns_schema(table_name)
        col_id_index = 0
        col_name_index = 1
        col_type_index = 2

        columns_new_table_tuple = [(cols[col_id_index], new_name) + cols[col_type_index:]
                                   if column_to_rename == cols[col_name_index] else cols
                                   for cols in columns_with_schema]

        self.__generate_table_with_data(table_name, columns_new_table_tuple, rename=True,
                                        column_to_rename=column_to_rename, new_name=new_name)

    # @override(BaseDatabase)
    def column_exists(self, table_name: str, column_to_find: str) -> bool:
        columns_with_schema = self.get_columns_schema(table_name)
        return column_to_find in [column[1] for column in columns_with_schema]

    # @override(BaseDatabase)
    def record_exists(self, table_name: str, where: str) -> bool:
        count = self.count(table_name, where)
        if count:
            return True
        else:
            return False

    # @override(BaseDatabase)
    def get_column_type(self, table_name: str, column_name: str) -> Tuple[str, str]:
        default_col_type = 'TEXT'
        column_type = None
        column_size = None
        columns = self.get_columns_schema(table_name)

        for col in columns:
            if col[self.COLUMN_NAME] == column_name:
                column_type = None
                column_size = None

                pattern_type_size = r"([a-zA-Z]+)\(([0-9]+)*"

                if not col[self.COLUMN_TYPE]:
                    # no column type or size for this column_name
                    break
                elif re.search(pattern_type_size, col[self.COLUMN_TYPE]) is not None:
                    column_type, column_size = re.search(pattern_type_size, col[self.COLUMN_TYPE]).groups()
                else:
                    column_type = col[self.COLUMN_TYPE]
                break

        if column_type is None:
            # set default type
            column_type = default_col_type

        return column_type, column_size

    # @override(BaseDatabase)
    def get_columns_schema(self, table_name: str) -> List[BaseDatabase.ColumnSchema]:
        sql = "PRAGMA table_info({})".format(table_name)
        self.execute(sql)

        return self.fetch_all()

    # @override(BaseDatabase)
    def get_num_columns(self, table_name: str) -> int:
        return len(self.get_columns_schema(table_name))

    # @override(BaseDatabase)
    def get_last_record_id(self, table_name: str) -> int:
        sql = "select max(rowid) from {}".format(table_name)
        self.execute(sql)
        # sqlite's fetchall always returns a list tuple, that is why it is necessary to index it like below to get
        # the value we need. Also, it is always the first element (in this case) because there is only single record
        # with the maximum unique id.
        return self.fetch_all()[0][0]
    
    # @override(BaseDatabase)
    def get_hash_md5(self, table_name: str) -> int:
        cols = ['"' + ci[1] + '"' for ci in self.get_columns_schema(table_name)]
        sql = 'SELECT {} from {}'.format(','.join(cols), table_name)
        self.execute(sql)

        md5 = self.MyMd5Sum()

        for values in self.__cursor.fetchall():
            md5.step(values)

        return md5.finalize()

    def __convertToSqlDataSet(self, table_name: str, sql_statement: str, cursor_description, records: List[BaseDatabase.DbRawRecord]) -> SqlDataSet:
        name2index = dict()
        index2name = dict()
        for col_idx, col_info in enumerate(cursor_description):
            name2index[col_info[0]] = col_idx
            index2name[col_idx] = col_info[0]

        return SqlDataSet(table_name, sql_statement, records, name2index, index2name)

    # @override(BaseDatabase)
    def select(self,
               table_name: str,
               fields: str = "*",
               where: str = None,
               limit: int = None,
               select_raw: bool = False) -> Either[SqlDataSet, List[BaseDatabase.DbRawRecord]]:
        sel_stmt = create_select_statement(table_name=table_name, fields=fields, where=where, limit=limit)
        self.execute(sel_stmt)
        affected_rows, description = self.__fetch_all()
        if select_raw:
            return affected_rows
        else:
            return self.__convertToSqlDataSet(table_name, sel_stmt, description, affected_rows)
    
    # @override(BaseDatabase)
    def get_all_data(self, table_name: str, table_filter: str = None, arranged_columns=None) -> List[BaseDatabase.DbRawRecord]:
        if arranged_columns:
            # In case column names contain spaces, the names must be enclosed in quotes.
            sanitized_arranged_columns = "\",\"".join(arranged_columns)
            sql = "SELECT rowid, \"{}\" FROM {}".format(sanitized_arranged_columns, table_name)
        else:
            sql = "SELECT rowid, * FROM {}".format(table_name)

        if table_filter:
            sql += " where {}".format(table_filter)

        self.execute(sql)
        return self.fetch_all()

    # @override(BaseDatabase)
    def remove_all_data(self, table_name: str):
        sql = "DELETE FROM {}".format(table_name)
        self.execute(sql)
    
    # @override(BaseDatabase)
    def get_table_subset(self, table_name: str, col_subset: List[str], table_filter: str = None) -> List[BaseDatabase.DbRawRecord]:
        selected_columns = ', '.join(normalize_name(col_name) for col_name in col_subset)
        sql = "SELECT {} FROM {}".format(selected_columns, table_name)

        if table_filter is not None:
            sql += " WHERE {}".format(table_filter)

        self.execute(sql)
        return self.fetch_all()

    # @override(BaseDatabase)
    def filter_raw_data(self, raw_data: List[BaseDatabase.DbRawRecord],
                        raw_cols: List[str],
                        col_names_types_sizes: List[Tuple[str, str, int]],
                        select_cols: List[str],
                        sql_filter: str = None) -> Tuple[List[BaseDatabase.DbRawRecord], List[str]]:
        temp_table = 'temp_filter_raw_data_table'

        if self.does_table_exist(temp_table):
            self.drop_table(temp_table)

        # create a new temp table containing ALL columns and data
        self.create_table(temp_table)
        self.add_columns(temp_table, col_names_types_sizes)
        self.insert_all(temp_table, raw_cols, raw_data)

        # select only the columns and data requested from the new table using SQL
        selected_columns = "[" + "], [".join(select_cols) + "]"
        sql = "SELECT {} FROM {}".format(selected_columns, temp_table)
        if sql_filter is not None:
            sql += " WHERE {}".format(sql_filter)

        self.execute(sql)
        filtered_data = self.fetch_all()

        # get column type and size in string format for each selected column
        col_types_and_sizes = []
        for col_name in select_cols:
            col_type, col_size = self.get_column_type(temp_table, col_name)
            if col_size is not None:
                col_types_and_sizes.append(col_type + '(' + str(col_size) + ')')
            else:
                col_types_and_sizes.append(col_type)

        return filtered_data, col_types_and_sizes

    # @override(BaseDatabase)
    def count(self, table_name: str, where: str = None) -> int:
        sql = "SELECT COUNT(*) FROM {}".format(table_name)

        if where:
            sql = sql + " WHERE {}".format(where)

        self.execute(sql)

        return self.fetch_all()[0][0]

    # @override(BaseDatabase)
    def delete_data(self, table_name: str, where: str = None) -> List[BaseDatabase.DbRawRecord]:
        sql = "DELETE from {} ".format(table_name)

        if where:
            sql = sql + "WHERE {}".format(where)

        self.execute(sql)

        return self.fetch_all()

    # @override(BaseDatabase)
    def create_index(self, table_name: str, index_name: str, columns: List[str] = None, unique: bool = False,
                     new_index: bool = True) -> str:
        if new_index:
            normalized_name = '_'.join(columns)
        else:
            # We used to allow many indices to be created on the same column(s). That was bad for performance and
            # memory. Since the old scenarios have already saved redundant indices to the scenarios, we have to
            # remove them.
            #
            # The solution is to use a new naming convention to allow only one index for a given column or a set of
            # columns - Index_on_(table_name_column names). For example, Index_on_table1_RankID,
            # Index_on_table1_RankID_StreamID. The indices that do not match the new naming convention will be
            # removed and re-created according to the new naming convention.
            if index_name.startswith(self.INDEX_NAME_PREFIX):
                normalized_name = index_name
            else:
                self.drop_index(index_name)
                normalized_name = '_'.join(columns)

        normalized_name = get_valid_python_name(normalized_name)

        index_name_in_db = '{}{}_{}'.format(self.INDEX_NAME_PREFIX, table_name, normalized_name)

        sql = "CREATE"

        if unique:
            sql += " {}".format("UNIQUE")

        sql += " INDEX {} ON {}".format(index_name_in_db, table_name)

        # NO square brackets necessary:
        sql_columns = ', '.join("'{}'".format(c) for c in columns)
        column_spec = "({})".format(sql_columns)

        # Prevent duplicate indices by checking if the index already exists.
        if self.__has_index(table_name, column_spec):
            return index_name_in_db

        sql += column_spec

        self.execute(sql)
        log.info("Index created for '{}' on table '{}'.", columns, table_name)

        return index_name_in_db

    # @override(BaseDatabase)
    def drop_index(self, index_name: str):
        sql = "DROP INDEX [{}]".format(index_name)
        self.execute(sql)

    # @override(BaseDatabase)
    def remove_record(self, table_name: str, unique_id: int):
        sql = "DELETE FROM {} WHERE rowid={}".format(table_name, unique_id)
        self.execute(sql)

    # @override(BaseDatabase)
    def insert(self, table_name: str, record: Tuple[TableCellData]):
        num_of_user_fields = len(record)
        sql = 'INSERT INTO %s VALUES(%s)' % (table_name, ', '.join(['?' for _ in range(num_of_user_fields)]))
        self.execute(sql, record)

    # @override(BaseDatabase)
    def insert_all(self, table_name: str, column_names: List[str], records: List[BaseDatabase.DbRawRecord]):
        formatted_col_names = ','.join(normalize_name(col_name) for col_name in column_names)
        wild_card = ', '.join(['?'] * len(column_names))
        sql = "INSERT INTO {} ({}) VALUES ({})".format(table_name, formatted_col_names, wild_card)
        try:
            self.__cursor.executemany(sql, records)
        except SqlOperationalError as exc:
            err_msg = "SQL statement '{}' exec error: {}".format(sql, exc)
            log.error(err_msg)
            raise DbSqlExecError(err_msg, statement=sql, sqlite_err=str(exc))

    # @override(BaseDatabase)
    def update(self, table_name: str, new_key_value_pair: str, where: str = None):
        if where:
            sql = "UPDATE {} SET {} WHERE {}".format(table_name, new_key_value_pair, where)
        else:
            sql = "UPDATE {} SET {}".format(table_name, new_key_value_pair)

        self.execute(sql)

    # @override(BaseDatabase)
    def update_field(self, table_name, unique_id: int, column: str, new_value: Any):
        safe_col_name = normalize_name(column)
        sql = "UPDATE {} SET {}='{}' WHERE rowid={}".format(table_name, safe_col_name, new_value, unique_id)
        self.execute(sql)

    # @override(BaseDatabase)
    def index_exists(self, index_name: str) -> bool:
        sql = "PRAGMA index_info({})".format(index_name)

        self.execute(sql)

        if self.fetch_all():
            return True
        else:
            return False

    # @override(BaseDatabase)
    def does_table_exist(self, table_name: str) -> bool:
        self.execute("PRAGMA table_info({})".format(table_name))
        if self.fetch_all():
            return True
        else:
            return False

    # @override(BaseDatabase)
    def get_all_indices(self, table_name: str) -> List[Tuple]:
        sql = "SELECT * FROM sqlite_master WHERE type=='index' and tbl_name='{}'".format(table_name)
        self.execute(sql)

        return self.fetch_all()
    
    # @override(BaseDatabase)
    def get_unique_ids(self, table_name) -> List[int]:
        sql = "SELECT {} from {}".format("rowid", table_name)
        self.execute(sql)
        return self.fetch_all()
    
    # @override(BaseDatabase)
    def get_last_record_id(self, table_name: str) -> int:
        sql = "select max(rowid) from {}".format(table_name)
        self.execute(sql)
        # sqlite's fetchall always returns a list tuple, that is why it is necessary to index it like below to get
        # the value we need. Also, it is always the first element (in this case) because there is only single record
        # with the maximum unique id.
        return self.fetch_all()[0][0]

    # @override(BaseDatabase)
    def get_record_item(self, table_name: str, unique_id: int, column: str) -> object:
        sql = "SELECT {} FROM {} WHERE rowid={}".format(column, table_name, unique_id)
        self.execute(sql)
        return self.fetch_all()[0][0]

    # @override(BaseDatabase)
    def get_record_subset(self, table_name: str, row_id: int, limit: int,
                          table_filter: str = None, arranged_columns: List[str] = None) -> List[BaseDatabase.DbRawRecord]:
        sql = "SELECT"

        if arranged_columns:
            # In case column names contain spaces, the names must be enclosed in quotes.
            sanitized_arranged_columns = "\",\"".join(arranged_columns)
            sql += " \"{}\"".format(sanitized_arranged_columns)
        else:
            sql += " *"  # Select all columns in the order created

        # Specify the table name and starting row
        sql += " FROM {} WHERE rowid>={}".format(table_name, row_id)

        # Add the filter if specified
        if table_filter:
            sql += " AND {}".format(table_filter)

        # Limit the number of records returned
        sql += " LIMIT {}".format(limit)

        self.execute(sql)
        return self.fetch_all()
    
    # @override(BaseDatabase)
    def get_row_ids(self, table_name: str, table_filter: str = None) -> List[int]:
        sql = "SELECT rowid FROM {}".format(table_name)

        if table_filter:
            sql += ' WHERE {}'.format(table_filter)

        self.execute(sql)
        return self.fetch_all()

    # @override(BaseDatabase)
    def select_as_sql_data_set(self, table_name: str, sql_statement: str) -> SqlDataSet:
        return SqlDataSet(table_name, sql_statement, self.__conn)
    
    # @override(BaseDatabase)
    def dump_schema(self):
        # Right now, we dump the basic info. When needed, add more info in this function.
        print("Start: dump_schema")
        for row in self.__conn.execute("SELECT * FROM sqlite_master"):
            print(row)
        print("End:   dump_schema")
        
    # @override(BaseDatabase)
    def select_as_sql_data_set(self, table_name: str, sql_statement: str) -> SqlDataSet:
        self.execute(sql_statement)
        affected_rows, description = self.__fetch_all()
        return self.__convertToSqlDataSet(table_name, sql_statement, description, affected_rows)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __generate_table_with_data(self, table_name: str, columns_remaining: List[str], rename: bool = False,
                                   column_to_rename: str = None, new_name: str = None, dropped_column: str = None):
        """
        SQLite provides only a limited subset of the generic ALTER command in SQL.  As such, it is not possible
        to drop a column or modify a column using its native api.  To get around this, we must copy the data
        into a temporary table and then only copy the data over that we need (if it is a column drop) or copy
        everything (if it is a column rename).
        :param table_name: Name of table onto which a type of ALTER is being performed upon.
        :param columns_remaining: A list of columns which will be in the new (final) table.
        for a rename as column that is to be selected does not exist in the new table (with the renamed column)
        :param rename: Whether or not this method is being called as a result of a rename on a column.
        :param column_to_rename: The column to be renamed.
        :param new_name: The new name of the column to be renamed.
        :param dropped_column:  A column that was dropped.  Indices for this column need not be re-created.
        """
        if columns_remaining:
            existing_indices_in_old_table = self.get_all_indices(table_name)
            index_of_sql_statement = 4

            if rename:
                index_creation_sql = ""
                for index_info in existing_indices_in_old_table:
                    index_creation_sql = index_info[index_of_sql_statement]

                    if column_to_rename in index_creation_sql:
                        index_creation_sql = index_creation_sql.replace(column_to_rename, new_name)

            name_types = [(column_name, column_type) for _, column_name, column_type, _, _, _ in columns_remaining]

            sanitized_name_types = []
            index_of_name = 0
            index_of_type = 1
            default_column_type = "TEXT"

            # It is a sql standard that columns can not be created without a type.  However, as witnessed during
            # integration, it is possible to end up having empty column types.  The following loop/check is to
            # ensure that table re-generation will occur correctly despite incorrect initial table schema/state.
            for name_type in name_types:
                if not name_type[index_of_type]:
                    sanitized_name_type = list()
                    sanitized_name_type.append(name_type[index_of_name])
                    sanitized_name_type.append(default_column_type)
                    sanitized_name_types.append(tuple(sanitized_name_type))
                else:
                    sanitized_name_types.append(name_type)

            # Can't create a table without a column.  No sense in creating a dummy column and then removing it later.
            # So use the first column.
            first = 0
            col_name_index = 0
            col_type_index = 1
            first_column_name = sanitized_name_types[first][col_name_index]
            first_column_type = sanitized_name_types[first][col_type_index]
            self.create_table("temp", "\"{}\" {}".format(first_column_name, first_column_type))

            # Since the first column was used to create the table, must start adding columns beginning
            # from the second column.
            for name_type in sanitized_name_types[1:]:
                self.add_column("temp", name_type[col_name_index], name_type[col_type_index])

            columns = [column_name for _, column_name, _, _, _, _ in columns_remaining]
            columns = ["\"{}\"".format(column) for column in columns]
            columns = ", ".join(columns)

            if rename:
                # It is possible to figure out the old columns here, but less work involved by just selecting all of the
                # columns from the original table.
                sql = "INSERT INTO temp ({}) SELECT * FROM {}".format(columns, table_name)
            else:
                sql = "INSERT INTO temp ({}) SELECT {} FROM {}".format(columns, columns, table_name)

            self.execute(sql)

            # Now that the temp table has been created with the new columns and data, the original table can be dropped.
            sql = "DROP TABLE {}".format(table_name)
            self.execute(sql)

            # The temp table effectively becomes the "original table" after execution of the following sql.
            sql = "ALTER TABLE temp RENAME TO {}".format(table_name)
            self.execute(sql)

            if rename:
                if index_creation_sql:
                    # If the operation was a column rename that resulted in the table being regenerated, then at this
                    # point the index can be recreated, if the column that was indexed had been renamed.
                    self.execute(index_creation_sql)
            else:
                # Got here because of a column that was dropped.  In this case all indices of the original table
                # must be recreated.  We cannot just keep the existing indices because after a drop/rename of the table,
                # the indices are pointing to the new non-existent/dropped table - not the temp table that was created.
                for index_info in existing_indices_in_old_table:
                    index_creation_sql = index_info[index_of_sql_statement]
                    # Only create indices if necessary - if the table is being re-generated as a result of a dropped
                    # column and if an index existed for that column, there is no need to create an index for it.
                    if dropped_column not in index_creation_sql:
                        self.execute(index_creation_sql)
        else:
            # In this case the column being dropped is the last column in the table.
            # Once this column is dropped, there will be no remaining data nor columns.
            # So that means we can simply drop the table and then when a new column is added, we must recreate
            # the table - as there is no way to create a Table without at least one defined column.
            sql = "DROP TABLE {}".format(table_name)
            self.execute(sql)

class SQLiteMsAccessColumnMapper:
    """
    This class is used to map SQLite column types to Access column types and vice-versa.
    """
    ACCESS_TO_SQLITE_TYPES = {
        'BINARY': 'BIT',
        'BIT': 'BIT,',
        'COUNTER': 'INTEGER',
        'CURRENCY': 'CURRENCY',
        'DATETIME': 'DATETIME',
        'DECIMAL': 'REAL',
        'DOUBLE': 'DOUBLE',
        'GUID': 'GUID',
        'INTEGER': 'INTEGER',
        'LONG': 'INTEGER',
        'LONGINT': 'INTEGER',
        'LONGBINARY': '',
        'LONGTEXT': 'TEXT',
        'NUMBER': 'INTEGER',
        'REAL': 'REAL',
        'SINGLE': 'REAL',
        'SHORT': 'INTEGER',
        'SMALLINT': 'INTEGER',
        'NUMERIC': 'REAL',
        'VARBINARY': 'BLOB',
        'UNSIGNED BYTE': 'INTEGER',
        'VARCHAR': 'TEXT'
    }

    SQLITE_TO_ACCESS_TYPES = {
        'BIGINT': 'INTEGER',
        'BINARY': 'BIT',
        'BLOB': '',
        'BLOB_TEXT': 'TEXT',
        'BOOL': 'BIT',
        'BOOLEAN': 'BIT',
        'CHAR': 'TEXT',
        'CLOB': '',
        'CURRENCY': 'CURRENCY',
        'DATE': 'DATETIME',
        'DATETEXT': 'TEXT',
        'DATETIME': 'DATETIME',
        'DEC': 'DOUBLE',
        'DECIMAL': 'DOUBLE',
        'DOUBLE': 'DOUBLE',
        'DOUBLE PRECISION': 'DOUBLE',
        'FLOAT': 'DOUBLE',
        'GRAPHIC': '',
        'GUID': 'GUID',
        'IMAGE': 'BINARY',
        'INT': 'INTEGER',
        'INT64': 'INTEGER',
        'INTEGER': 'INTEGER',
        'LARGEINT': 'INTEGER',
        'LONGTEXT': 'MEMO',
        'MEMO': 'MEMO',
        'MONEY': 'CURRENCY',
        'NCHAR': '',
        'NTEXT': '',
        'NUMBER': 'NUMBER',
        'NUMERIC': 'REAL',
        'NVARCHAR': '',
        'NVARCHR2': '',
        'PHOTO': 'BINARY',
        'PICTURE': 'BINARY',
        'RAW': '',
        'REAL': 'REAL',
        'SMALLINT': 'INTEGER',
        'SMALLMONEY': 'INTEGER',
        'TEXT': 'TEXT',
        'TIME': 'DATE/TIME',
        'TIMESTAMP': 'DATE/TIME',
        'TINYINT': '',
        'UNIQUEIDENTIFIER': '',
        'VARBINARY': 'BLOB',
        'VARCHAR': 'TEXT',
        'VARCHAR2': 'TEXT',
        'WORD': 'TEXT',
    }

    def get_sqlite_type(self, access_col_type: str):
        """
        Given an MS Access column type, this method returns its corresponding type in SQLite.
        :param access_col_type: The access field type to find the corresponding SQLite column type.
        :return: SQLite column type.
        """
        if not access_col_type:
            return ""

        return self.ACCESS_TO_SQLITE_TYPES[access_col_type]

    def get_access_type(self, sql_col_type: str):
        """
        Given a SQLite column type, this method returns its corresponding type in MS Access.
        :param sql_col_type: The SQLite column type to find the corresponding Access column type.
        :return: Access column type.
        """
        return self.SQLITE_TO_ACCESS_TYPES[sql_col_type]