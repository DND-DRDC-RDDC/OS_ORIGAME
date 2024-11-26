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
import pandas
from sqlalchemy import CursorResult, create_engine, text
from sqlalchemy.engine import Engine

# [3. local]
from .base_db import BaseDatabase, DbSqlExecError, DbSqlNotStatementError, DbInvalidParameterError
from ..core.typing import List, Tuple
from .sql_dataset import SqlDataSet
from .database_configs import DatabaseConfig

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
    
    # Connection pool size
    POOL_SIZE = 5
    
    # Database engine 
    __engine: Engine
    
    # Database Configurations
    __db_config: DatabaseConfig
    
    # CursorResult object
    __cursor: CursorResult
    
    # --------------------------- instance __PRIVATE members-------------------------------------
   
    def __init__(self, database_config: DatabaseConfig):
        """Initialize an instance of this class using given database configurations.

        Args:
            database_config (DatabaseConfig): Database configurations.
        
        Raises:
            DbInvalidParameterError: if connection string of the database configuration is invalid.
        """        
        self.__db_config = database_config
        db_type = database_config.get_db_type()        
        self.__connection_string = self.__db_config.get_connection_config().get(db_type)
        
        if not self.__validate_connection_string():
            raise DbInvalidParameterError("Invalid connection string {}.".format(self.__connection_string))
        
        self.__engine = None      
        self.__cursor = None  

    def __get_engine(self) -> Engine:
        """Create an engine, if not already created. The engines is used to connect to the database represented by the given connection string.
        
        Returns:
            Engine: Database Engine instance
        """
        if self.__engine is None:
            self.__engine = create_engine(self.__connection_string, pool_size = self.POOL_SIZE)            
        
        return self.__engine    
    
    def __validate_connection_string(self) -> bool:
        """Verfy if a valid connection could be made to a database using given connection string.

        Args:
            connection_string (str): connection string to be verified.

        Returns:
            bool: true if a valid connection could be made to a database using given connection string, false otherwise. 
        """
        if self.__connection_string is None or self.__connection_string.isspace():
            return False
               
        try:
            engine = create_engine(self.__connection_string) 
            engine.connect()
            log.info("The connection string '{}' is valid.", self.__connection_string)            
            return True
        except Exception as exc:
            log.error("Could not connect to the database specified by the connection string '{}' due to '{}'".format(self.__connection_string, exc))
            return False    

    def __fetch_all(self) -> pandas.DataFrame:
        """Fetch all records from the cursor object. If cursor is None, it executes the SQL string.

        Returns:
            List[BaseDatabase.DbRawRecord]: results of execution as list of Tuples.
        """
        if (self.__cursor is None):                        
            self.execute(self.__connection_string)
                        
        result = self.__cursor.fetchall()   
        
        # Convert the result to a Pandas DataFrame
        return pandas.DataFrame(result)                  
   
    def __convertToSqlDataSet(self, table_name: str, sql_statement: str, records: pandas.DataFrame) -> SqlDataSet:
        """Creates an instance of SqlDataSet using given parameters.

        Args:
            table_name (str): table name.
            sql_statement (str): SQL statement.
            records (List[BaseDatabase.DbRawRecord]): result of query execution.

        Returns:
            SqlDataSet: a SqlDataSet object.
        """
        
        # Convert DataFrame to list of tuples
        data = list(records.itertuples(index=False, name=None))  
               
        col_name_index = dict()
        col_index_name = dict()
        if (len(records) > 0):
            # get the colum names
            column_names = list(records.columns)
                        
            index = 0
            for col in column_names:
                name = col[0]
                col_name_index[name]=index
                col_index_name[index]=name
                index = index + 1

        return SqlDataSet(table_name, sql_statement, data, col_name_index, col_index_name)
    
    # --------------------------- instance (self) PUBLIC methods --------------------------------
    # @override(BaseDatabase)
    def execute(self, sql_statement: str, params: Tuple = ()):
        if sql_statement is None or sql_statement.isspace():
            raise DbInvalidParameterError("Invalid SQL statement {}.".format(sql_statement))
          
        engine:Engine = self.__get_engine()
        
        try:
            # Establish a connection and execute the SQL query
            with engine.connect() as connection:
                 # commits and closes automatically
                self.__cursor = connection.execute(text(sql_statement))   
        except Exception as exc:
            error_message = "Could not connect to the database specified by the connection string '{}' due to '{}'".format(self.__connection_string, exc)
            log.error(error_message)
            raise DbSqlExecError(error_message)
                
    # @override(BaseDatabase)
    def execute_script(self, multiple_statements: str):
        if multiple_statements is None or multiple_statements.isspace():
            raise DbInvalidParameterError("Invalid SQL statement {}.".format(multiple_statements))
        
        engine:Engine = self.__get_engine()
        
        try:
            # Establish a connection and start a transaction        
            with engine.begin() as connection:
                # Run statements of the script
                for sql_statement in multiple_statements.split('\n'):
                    self.__cursor = connection.execute(text(sql_statement))
            # commits and closes automatically
        except Exception as exc:
            error_message = "Could not connect to the database specified by the connection string '{}' due to '{}'".format(self.__connection_string, exc)
            log.error(error_message)
            raise DbSqlExecError(error_message)

    # @override(BaseDatabase)
    def execute_and_fetch(self, sql_statement) -> pandas.DataFrame:
        self.execute(sql_statement)
        return self.__fetch_all()

    # @override(BaseDatabase)
    def datafrane_to_sql(self, dataframe: pandas.DataFrame, tabe_name: str):
        dataframe.to_sql(tabe_name, self.__get_engine(), if_exists='fail')
        
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
        affected_rows = self.__fetch_all()
        return self.__convertToSqlDataSet(table_name, sql_statement, affected_rows)   
    
      
    # @override(BaseDatabase)
    def shutdown(self):
        """Dispose the engine and close all the connections."""
        if self.__engine is not None:
            self.__engine.dispose(close= True)
        self.__cursor.close()
