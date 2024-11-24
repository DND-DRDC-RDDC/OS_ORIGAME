# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module provides capability to interface with databases.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import hashlib
import pickle
import re

import pandas

# [2. third-party]

# [3. local]
from ..core.decorators import override_required, override_optional
from ..core import get_valid_python_name
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
    'BaseDatabase',
    'DbInvalidParameterError',
    'DbInvalidArrangeFieldError'
    'DbInvalidSqlError',
    'DbSqlExecError',
    'DbSqlNotStatementError',
    'create_select_statement',
    'normalize_name'
]

log = logging.getLogger('system')

TableCellData = Either[str, int, float]

# -- Function definitions -----------------------------------------------------------------------
def normalize_name(name: str) -> str:
    """
    This function will surround the given name with [] if name doesn't already have []
    :param name: The name of the column or table.
    :return: A normalized string representation of the column name
    """
    if not name.startswith('[') and not name.endswith(']'):
        name = '[' + name + ']'

    return name


def create_select_statement(table_name: str, fields: str = "*", where: str = None, limit: int = None):
    """
    This method is used to construct a select statement in string.
    :param table_name: Name of the table to get rows from.
    :param fields: Optional specification of the fields to select: a string consisting of a comma-separate list of
        column names.  If no fields are specified, then all fields of the table are returned.
    :param where: Optional SQL where statement restricting the matched results.
    :param limit: Optional limit on the number of records returned.
    """
    select_stmt = ""

    if fields is None or fields == "*":
        select_stmt = "SELECT * FROM {}".format(table_name)
    else:
        # need to escape fields that have space in their name
        select_stmt = "SELECT {} FROM {}".format(fields, table_name)

    if where:
        select_stmt += " WHERE {}".format(where)

    if limit:
        select_stmt += " LIMIT {}".format(limit)

    return select_stmt

# -- Class Definitions --------------------------------------------------------------------------
class DbInvalidParameterError(Exception):
    """
    Custom error class used for raising BaseDatabase exceptions. This exception represents an error condition where
    an invalid parameter was passed to an BaseDatabase method.
    """
    pass


class DbInvalidArrangeFieldError(Exception):
    """
    Custom error class used for raising BaseDatabase exceptions. This exception represents an error condition where
    an invalid field name (ie doesn't exist in the table) was passed to the arrange_fields method.
    """
    pass


class DbInvalidSqlError(Exception):
    """
    Custom error class used for raising BaseDatabase exceptions. This exception represents an error condition where
    an invalid sql is about to be passed the the BaseDatabase's executed method.
    """
    pass


class DbSqlExecError(Exception):
    """
    Custom error class used when executing a SQL statement in the Database failed
    """

    def __init__(self, msg: str, **kwargs):
        super().__init__(msg)
        self.sql_info = kwargs


class DbSqlNotStatementError(Exception):
    pass

class BaseDatabase:
    """This is a base database class, mean to provide an api layer"""
    
    # --------------------------- class-wide data and signals -----------------------------------

    ColumnSchema = Tuple[int, str, str, bool, Any, bool]
    DbRawRecord = Tuple  # size and contents will vary based on SQL query

    COLUMN_ID = 0
    COLUMN_NAME = 1
    COLUMN_TYPE = 2
    COLUMN_NULL = 3
    COLUMN_DEFAULT = 4

    INDEX_NAME_PREFIX = "Index_on_"

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        """Initialise the object"""

    @override_optional
    def reset(self):
        """
        This method is used to reset the connection that allows one to quickly determine whether or not
        changes have occurred since an initial connection is made.
        """
        # TODO build 3: Once we go file based db, augment this method.        
        raise NotImplementedError

    @override_required
    def shutdown(self):
        """Close the connection, cleanup"""
        raise NotImplementedError

    @override_required
    def execute(self, sql_statement: str, params: Tuple = ()):
        """Execute the given SQL statement and return the result as Dataframe.

        Args:
            sql_statement (string): a valid SQL statement to execute.
            param params (Tuple): Optional tuple of parameters. 
        """
        raise NotImplementedError

    @override_optional
    def execute_and_fetch(self, sql_statement:str) -> pandas.DataFrame:
        
        """Execute the given SQL statement and return the result as Dataframe.

        Args:
            sql_statement (string): SQL statement to execute.

        Raises:
            DbSqlExecError: if any error when executing the statement.
            DbInvalidParameterError: if SQL statment is invalid.

        Returns:
            pandas.DataFrame: result as Dataframe.
        """
        raise NotImplementedError
    
    @override_required
    def datafrane_to_sql(self, dataframe: pandas.DataFrame, tabe_name: str):
        """Write records stored in a DataFrame to a SQL database.

        Args:
            dataframe (pandas.DataFrame): dataframe to be stored.
            tabe_name (str): database table name.
        """
        raise NotImplementedError
    
    @override_required
    def execute_script(self, multiple_statements: str):
        """
        Executes the given multiple statements SQL script.
        :param multiple_statements: Multiple SQL statements.
        :returns: Forward the return from the executescript.
        """
        raise NotImplementedError

    @override_required
    def fetch_all(self) -> List[DbRawRecord]:
        """
        Get the rows matched from the last execution of the cursor.
        :return: Rows from a result set.
        """
        raise NotImplementedError

    @override_optional
    def table_data_matches(self, table_name: str, re_pattern: str, first_row: int = 0, num_rows: int = 100) -> str:
        """
        Return true if any data in the table matches a regular expression pattern (case insensitive)
        :param table_name: name of table
        :param re_pattern: the regular expression pattern to match
        :param first_row: the first row to search.
        :param num_rows: the number of rows to search.
        :return: name of column in which match was found, or None if not match
        """
        raise NotImplementedError

    @override_optional
    def add_column(self, table_name: str, column_name: str, column_type: str = None, column_size: int = None):
        """
        This method is used to add a new column to a table.
        :param table_name: The name of the table to add a new column to.
        :param column_name: The name of the new column.
        :param column_type: The type of the new column.
        :param column_size: The size of the column, if it is a varchar.
        """
        raise NotImplementedError

    @override_optional
    def add_columns(self, table_name: str, columns: List[Tuple[str, str, int]]):
        """
        This method is used to add more than one column into a given table.
        :param table_name: The name of the table to add columns to.
        :param columns: A dictionary containing key-value pairs of column_name-column_type.
        """
        raise NotImplementedError

    @override_optional
    def create_table(self, table_name: str, columns: str = None):
        """
        Create a table with the with the given table_name and columns.
        :param table_name: The name of the table to create.
        :param columns: The new columns to add to the table. This will be in the format
        "col col_type, col2 col2_type..."
        :return:
        """
        raise NotImplementedError

    @override_optional
    def drop_table(self, table_name: str):
        """
        Drop a table from the database.
        :param table_name:  Name of table to reset.
        """
        raise NotImplementedError

    @override_optional
    def set_table_fields(self, table_name, columns: str):
        """
        This method is used to remove all of the rows of a given table and re-create the table with the
        given columns.
        :param table_name: The table to remove all rows from.
        :param columns: The new columns to add to the table. This will be in the format
        "col col_type, col2 col2_type..."
        """
        raise NotImplementedError

    @override_optional
    def arrange_columns(self, table_name, columns: str = None):
        """
        This method is used to arrange the given table in the order provided by columns.
        :param table_name: The name of the table to arrange.
        :param columns:  The order of the columns to arrange the table in.  The format will be "col1, col3, col5..."
        """
        raise NotImplementedError

    @override_optional
    def drop_column(self, table_name: str, column_to_drop: str):
        """
        This method is used to remove a column from the given table.
        to be consistent with EmbeddedDatabase, a temporary table is created with
        all of the data, minus the column to be removed.
        :param table_name: Table to remove a column from.
        :param column_to_drop: Name of column to remove from table.
        """
        raise NotImplementedError

    @override_optional
    def rename_column(self, table_name: str, column_to_rename: str, new_name: str):
        """
        This method is used to rename a column in a given table.
        :param table_name: Table containing the column to rename.
        :param column_to_rename: Name of the column to be renamed.
        :param new_name: New name of the column.
        """
        raise NotImplementedError

    @override_optional
    def column_exists(self, table_name: str, column_to_find: str) -> bool:
        """
        This method is used determine whether or not a column already exists within a given table.
        :param table_name: The name of the table to find a column in.
        :param column_to_find: The name of the column to find in the given table.
        :return: Boolean indicating whether or not a column exists within a given table.
        """
        raise NotImplementedError

    @override_optional
    def record_exists(self, table_name: str, where: str) -> bool:
        """
        This method is used to determine whether or not a record exists given the where clause.
        :param table_name: The name of the table to search a record for.
        :param where: The clause restricting the record to find.
        :return: Boolean indicating whether or not a record exists given the where restriction.
        """
        raise NotImplementedError

    @override_optional
    def get_column_type(self, table_name: str, column_name: str) -> Tuple[str, str]:
        """
        This method is used to obtain the type (and size if applicable) of a column in a given table.
        :param table_name: The name of the table to look up the column information.
        :param column_name: The name of the column.
        :return: A string representation of the type of a column, and size of a column
        """
        raise NotImplementedError

    @override_optional
    def get_columns_schema(self, table_name: str) -> List[ColumnSchema]:
        """
        Get a list of all of the columns.  Each item in the list will be a tuple which represents
        the cid, column_name, column_type, not_null, default_value, primary_key.
        :param table_name:  The table to get the columns for.
        :return:  A list of tuples.
        """
        raise NotImplementedError

    @override_optional
    def get_num_columns(self, table_name: str) -> int:
        """
        This this method is used to get the number of columns in a given table.
        :param table_name: Table name to get the number of columns.
        :return: The number of columns.
        """
        raise NotImplementedError

    class MyMd5Sum:

        def __init__(self):
            # self.data = []
            self.md5 = hashlib.md5()

        def step(self, values):
            # self.data.append(values)
            # self.md5.update(b''.join(bytes(str(v), 'utf-8') for v in values))
            self.md5.update(pickle.dumps(values))

        def finalize(self):
            # return hashlib.md5(pickle.dumps(self.data)).digest()
            return self.md5.hexdigest()

    @override_optional
    def get_last_record_id(self, table_name: str) -> int:
        """
        Get the id of the last record in the given table.
        :param table_name: Name of the table to get the max record id for.
        :return: The highest id in this table.
        """
        raise NotImplementedError
        
    @override_optional
    def get_hash_md5(self, table_name: str) -> int:
        raise NotImplementedError

    @override_optional
    def select(self,
               table_name: str,
               fields: str = "*",
               where: str = None,
               limit: int = None,
               select_raw: bool = False) -> Either[SqlDataSet, List[DbRawRecord]]:
        """
        This method is used to execute a select statement.
        :param table_name: Name of the table to get rows from.
        :param fields: Optional specification of the fields to select: a string consisting of a comma-separate list of
            column names.  If no fields are specified, then all fields of the table are returned.
        :param where: Optional SQL where statement restricting the matched results.
        :param limit: Optional limit on the number of records returned.
        :param select_raw: True to return a list of tuples; otherwise a SqlDataSet.
        :return the result data set.
        """
        raise NotImplementedError

    @override_optional
    def get_all_data(self, table_name: str, table_filter: str = None, arranged_columns=None) -> List[DbRawRecord]:
        """
        Get all of the data (records) in the given table.
        :param table_name: The name of the table to get all data.
        :param table_filter: A filter to be applied on the table.
        :param arranged_columns: A list of columns to arrange on.  Note that if a column exists in
        get_all_cols_schema() but doesn't exist in the arranged_columns, then that column will not be returned
        in the data set.
        :return: A list of data.  The data is a tuple.  For example, [("a", "b"), ("c", "d")].
        """
        raise NotImplementedError

    @override_optional
    def remove_all_data(self, table_name: str):
        """
        Method used to clear the data (ie all records).
        :param table_name: The name of the table to remove all of teh records from.
        """
        raise NotImplementedError
    
    @override_optional
    def get_table_subset(self, table_name: str, col_subset: List[str], table_filter: str = None) -> List[DbRawRecord]:
        """
        Get the set of table data corresponding to the selected columns and table filter.
        :param table_name: The name of the table to get all data.
        :param col_subset: A subset of columns to select from the database.
        :param table_filter: A filter to be applied on the table.
        :return: A list of data.  The data is a tuple.  For example, [("a", "b"), ("c", "d")].
        """
        raise NotImplementedError
    
    @override_optional
    def filter_raw_data(self, raw_data: List[DbRawRecord],
                        raw_cols: List[str],
                        col_names_types_sizes: List[Tuple[str, str, int]],
                        select_cols: List[str],
                        sql_filter: str = None) -> Tuple[List[DbRawRecord], List[str]]:
        """
        Filter the given data to include only the given columns and row values satisfying the SQL filter string.
        :param raw_data: The raw table data to filter.
        :param raw_cols: The raw table columns to filter.
        :param col_names_types_sizes: A list of tuples containing the column name, type, and size for each column.
        :param select_cols: The columns to keep.
        :param sql_filter: The SQL filter to apply against the raw data.
        :return: A filtered list of data where each row is a tuple, and a list of strings, each one encodes a column's
            type and size.
        """
        raise NotImplementedError    

    @override_optional
    def count(self, table_name: str, where: str = None) -> int:
        """
        This method is used to get the number of records that satisfy a select clause.
        :param table_name: The name of the table to get count information.
        :param where: A SQL select statement.
        :return: The number of rows that matched the given where clause.
        """
        raise NotImplementedError    

    @override_optional
    def delete_data(self, table_name: str, where: str = None) -> List[DbRawRecord]:
        """
        This method is used to delete rows that match the given select clause.
        :param table_name: The table from which to delete record(s).
        :param where: Optional where condition.
        :return: A list of data remaining after the delete operation.
        The data is a tuple.  For example, [("a", "b"), ("c", "d")].
        """
        raise NotImplementedError    

    @override_optional
    def create_index(self, table_name: str, index_name: str, columns: List[str] = None, unique: bool = False,
                     new_index: bool = True) -> str:
        """
        This method is used to created an index on a table.
        :param table_name: Table to create an index on.
        :param index_name: The name of the index.
        :param columns: The columns to create an index.
        :param unique: This flag determine whether or not a column can contain duplicated/identical values.  The default
        here is set to False deliberately.  The responsibility is on the user to ensure that columns don't contain
        duplicated data prior to creating an index using unique=True via the scripting API.
        :param new_index: A flag to indicate if index created is new.
        """
        raise NotImplementedError

    @override_optional
    def drop_index(self, index_name: str):
        """
        This method is used to drop an index from a given table.
        :param index_name: The name of the index to drop from the table.
        """
        raise NotImplementedError

    @override_optional
    def remove_record(self, table_name: str, unique_id: int):
        """
        This method is used to remove a single record from the given table that has the given id.
        :param table_name:  Name of table to remove a record from.
        :param unique_id: The unique id of the record to remove.
        """
        raise NotImplementedError

    @override_optional
    def insert(self, table_name: str, record: Tuple[TableCellData]):
        """
        This method is used to insert a record into a table.
        :param table_name: The name of the table to insert a record into.
        :param record: The record to insert.
        """
        raise NotImplementedError

    @override_optional
    def insert_all(self, table_name: str, column_names: List[str], records: List[DbRawRecord]):
        """
        Accessory method to insert a list of records for specific column_names.
        :param table_name: The table to insert the record into.
        :param column_names: The column_names being affected.
        :param records: The records written into the column_names.
        """
        raise NotImplementedError

    @override_optional
    def update(self, table_name: str, new_key_value_pair: str, where: str = None):
        """
        Update a particular record given a where clause.
        :param table_name: The name of the table to perform the update on.
        :param new_key_value_pair: Key value in the form key1=value1.
        :param where: A where clause restricting the number of records affected.
        """
        raise NotImplementedError

    @override_optional
    def update_field(self, table_name, unique_id: int, column: str, new_value: Any):
        """
        Update a particular record's column field value in a given table.
        :param table_name: The table to perform the update on.
        :param unique_id: The unique id of the row being updated.
        :param column: The column who's field is being updated.
        :param new_value: The new value for the intersection of row/column.
        """
        raise NotImplementedError

    @override_optional
    def index_exists(self, index_name: str) -> bool:
        """
        Determine whether or not a given index exists.
        :param index_name: Index name.
        :return: Boolean indicating whether or not a given index exists.
        """
        raise NotImplementedError

    @override_optional
    def does_table_exist(self, table_name: str) -> bool:
        """
        This method is used to determine whether or not a table with the give name exists within the
        Embedded Database Engine.
        :param table_name: Name of table to find.
        :return: Boolean indicating whether or not a table exists within the Embedded Database Engine.
        """
        raise NotImplementedError

    @override_optional
    def get_unique_ids(self, table_name) -> List[int]:
        """
        Get a list of the unique ids in a given table.
        :param table_name: The name of the table to get the unique ids' for.
        :return: A list of unique ids.
        """
        raise NotImplementedError

    @override_optional
    def get_record_item(self, table_name: str, unique_id: int, column: str) -> object:
        """
        Get the field value of a particular record in a given column and table.
        :param table_name: The name of the table to retrieve the field value for.
        :param unique_id: The id of the record to retrieve the field value for.
        :param column: The column of the record to retrieve the field value for.
        :return: The field at the intersection of the row and column.  Could be any type.
        """
        raise NotImplementedError

    @override_optional
    def get_record_subset(self, table_name: str, row_id: int, limit: int,
                          table_filter: str = None, arranged_columns: List[str] = None) -> List[DbRawRecord]:
        """
        Get the contiguous subset of records starting at the record ID from the table.
        :param table_name: The name of the table to retrieve the record from.
        :param row_id: The id of the first record to retrieve in the subset.
        :param limit: the maximum number of records to return.
        :param table_filter: A filter to be applied on the table.
        :param arranged_columns: A list of columns (by name) to arrange on.  Note that if a column exists in
            get_all_cols_schema() but doesn't exist in the arranged_columns, then that column will not be
            returned in the data set.
        :return: The record subset (a list of tuples).
        """
        raise NotImplementedError

    @override_optional
    def get_row_ids(self, table_name: str, table_filter: str = None) -> List[int]:
        """
        Gets the list of row IDs for records in the database. Apply filter if set.
        :param table_name: The name of the table to retrieve the record from.
        :param table_filter: A filter to be applied on the table.
        :return: the list of record IDs.
        """
        raise NotImplementedError

    @override_required
    def select_as_sql_data_set(self, table_name: str, sql_statement: str) -> SqlDataSet:
        """
        Get a SqlDataSet instance.
        :param table_name: The table name
        :param sql_statement: The execution of this SQL statement returns the data that is the underlying data for the
            SqlDataSet instance.
        :returns: SqlDataSet.
        """
        raise NotImplementedError

    @override_optional
    def dump_schema(self):
        """
        Dumps the schema of this database. Used for debugging purposes only.
        """
        raise NotImplementedError    

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __has_index(self, table_name: str, column_spec: str) -> bool:
        """
        Queries the database to determine if an index on the columns specified by the column_spec in the table
        identified by the table_name already exists.
        :param table_name: The name of the table to be checked for existence of an index
        :param column_spec: The column specification of the table to be checked for existence of an index, e.g.,
        ('First Name', 'Last Name')
        :return: True - an index exists.
        """
        for _, _, _, _, idx_stmt in self.get_all_indices(table_name):
            # An index record looks like this:
            # (
            # 'index',
            # 'Index_on_table1_RankID_StreamID',
            # 'table_2',
            # 3,
            # "CREATE INDEX Index_on_table1_RankID_StreamID ON table_1('RankID', 'StreamID')"
            # )"
            #
            # The column_spec looks like this: ('RankID', 'StreamID'), which uniquely identifies an existing index.

            if idx_stmt.endswith(column_spec):
                log.warning("The index on the column(s) {} will not be created because it already exists.", column_spec)
                return True

        return False
