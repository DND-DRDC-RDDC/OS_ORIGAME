# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module provides capability to interface with ODBC databases.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
import pypyodbc

# [3. local]
from .base_db import BaseDatabase, DbSqlExecError, DbSqlNotStatementError, create_select_statement, normalize_name
from ..core.typing import Either
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
    'OdbcDatabase'
]

log = logging.getLogger('system')

# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------
class OdbcDatabase(BaseDatabase):
    """A generic database class to setup connection and send queries to different database types.
    """ 

    # --------------------------- class-wide data and signals -----------------------------------
    __conn: pypyodbc.Connection
    __cursor: pypyodbc.Cursor

    # --------------------------- instance (self) PUBLIC methods --------------------------------
    def __init__(self, odbc_connection):
        """Initialise the object"""
        self.__conn = odbc_connection
        self.__cursor = self.__conn.cursor()

    # @override(BaseDatabase)
    def shutdown(self):
        """Close the connection, cleanup"""
        if self.__conn is not None:
            self.__conn.close()
            self.__conn = None
            self.__cursor = None

    # @override(BaseDatabase)
    def execute(self, sql_statement: str, params: Tuple = ()):
        """
        Execute the given sql statement.
        :param sql_statement: A valid sql statement to execute.
        :param params: Optional tuple of parameters.
        """
        try:
            self.__cursor.execute(sql_statement, params)
        except pypyodbc.OperationalError as exc:
            err_msg = "ODBC SQL statement '{}' (with params={}) exec error: {}".format(sql_statement, params, exc)
            log.error(err_msg)
            raise DbSqlExecError(err_msg)
        except pypyodbc.Warning as warn:
            raise DbSqlNotStatementError(str(warn))

    # @override(BaseDatabase)
    def execute_script(self, multiple_statements: str):
        """
        Uses the forward pattern to delegate the statements to the private __conn to run.
        :param multiple_statements: Multiple SQL statements.
        :returns: Forward the return from the executescript.
        """
        try:
            return self.__cursor.execute(multiple_statements)

        except pypyodbc.SqlOperationalError as exc:
            statements = multiple_statements.splitlines()
            first_line = statements[0] if statements else '<empty>'
            err_msg = "ODBC SQL script (starting with '{}') exec error: {}".format(first_line, exc)
            log.error(err_msg)
            raise DbSqlExecError(err_msg)

    # @override(BaseDatabase)
    def fetch_all(self) -> List[BaseDatabase.DbRawRecord]:
        """
        Get the rows matched from the last execution of the cursor.
        :return: Rows from a result set.
        """
        data = self.__cursor.fetchall()
        return data

    def __convertToTuple(self, records: List[BaseDatabase.DbRawRecord]) -> List[Tuple]:
        convertedRecords = list[Tuple]()
        for record in records:
            convertedRecords.append(tuple(col for col in record))
        return convertedRecords

    def __convertToSqlDataSet(self, table_name: str, sql_statement: str, records: List[BaseDatabase.DbRawRecord]) -> SqlDataSet:
        name2index = dict()
        index2name = dict()
        convertedRecords = list()
        if (len(records) > 0):
            # get the colum names
            record = records[0]
            index = 0
            for col in record.cursor_description:
                name = col[0]
                name2index[name]=index
                index2name[index]=name
                index = index + 1
            #populate the records
            convertedRecords = self.__convertToTuple(records)

        return SqlDataSet(table_name, sql_statement, convertedRecords, name2index, index2name)

    # @override(BaseDatabase)
    def select_as_sql_data_set(self, table_name: str, sql_statement: str) -> SqlDataSet:
        """
        Get a SqlDataSet instance.
        :param table_name: The table name
        :param sql_statement: The execution of this SQL statement returns the data that is the underlying data for the
            SqlDataSet instance.
        :returns: SqlDataSet.
        """
        self.execute(sql_statement)
        affected_rows = self.fetch_all()
        return self.__convertToSqlDataSet(table_name, sql_statement, affected_rows)   