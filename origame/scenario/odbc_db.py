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
import pandas as pd

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# [3. local]
from origame.core.decorators import override
from .base_db import BaseDatabase, DbSqlExecError, DbInvalidParameterError
from .sql_dataset import SqlDataSet
from .database_configs import DatabaseConfig, DatabaseTypeEnum

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
        
        success, message = self.__validate_connection_string()
        if not success:
            raise DbInvalidParameterError("Invalid connection string {}. Reason: {}".format(self.__connection_string, message))
        
        self.__engine = None      
        
    def __get_engine(self) -> Engine:
        """Create an engine, if not already created. The engines is used to connect to the database represented by the given connection string.
        
        Returns:
            Engine: Database Engine instance
        """
        if self.__engine is None:
            if self.__db_config.get_db_type() == DatabaseTypeEnum.MS_ACCESS.value:
                # Microsoft access does not accept pool size parameter
                self.__engine = create_engine(self.__connection_string)
            else:
                self.__engine = create_engine(self.__connection_string, pool_size = self.POOL_SIZE)            
        
        return self.__engine    
    
    def __validate_connection_string(self) -> tuple[bool, str]:
        """Verfy if a valid connection could be made to a database using given connection string.

        Args:
            connection_string (str): connection string to be verified.

        Returns:
            tuple[bool, str]: true if a valid connection could be made to a database using given connection string, error/success message. 
        """
        if self.__connection_string is None or self.__connection_string.isspace():
            return False, 'Invalid or empty connection string.'
               
        try:
            engine = create_engine(self.__connection_string) 
            engine.connect()
            return True, "Valid connection string."
        except Exception as exc:
            msg = "Cannot connect to the database specified by the connection string '{}'. Reason: '{}'".format(self.__connection_string, exc)
            log.error(msg)
            return False, msg     

    def __convertToSqlDataSet(self, table_name: str, sql_statement: str, records: pd.DataFrame) -> SqlDataSet:
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

    def __execute_queries(self, queries: list) -> pd.DataFrame:                
        df = pd.DataFrame()
        
        try:
            # Start a transaction and execute all queries
            with self.__get_engine().begin() as connection:
                # Execute each query
                for query in queries:                
                    connection.execute(text(query))
        
                # Fetch the result of the last statement if it is a SELECT statement
                is_select_statement = queries[-1].strip().lower()[:7] == "select "  
                if is_select_statement:                     
                    result = connection.execute(text(queries[-1]))
                    columns = result.keys()
                    data = result.fetchall()
    
                    # Convert the result to a Pandas DataFrame
                    df = pd.DataFrame(data, columns=columns)
        except Exception as exc:
                error_message = "Failed to execute query script on the database. Reason: '{}'".format(exc)
                log.error(error_message)
                raise DbSqlExecError(error_message)            
    
        return df

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    @override(BaseDatabase)
    def execute_and_fetch(self, sql_statement) -> pd.DataFrame:   
        if sql_statement is None or sql_statement.isspace():
            raise DbInvalidParameterError("Invalid SQL statement or script {}.".format(sql_statement))     

        result = pd.DataFrame()
        
        # Split if it contains multiple statements. Ignore empty lines.
        split_queries = sql_statement.split(';')        
        queries = []
        for query in split_queries:
            if query != '':
                queries.append(query)            
        try:
            result = self.__execute_queries(queries)            
        except Exception as ex:
            # Return and empty Dataframe if for any reason no results is fetched.
            log.info("No results fetched. Reason: {}", ex)
        
        return result

    @override(BaseDatabase)
    def dataframe_to_sql(self, dataframe: pd.DataFrame, tabe_name: str):
        dataframe.to_sql(tabe_name, self.__get_engine(), if_exists='fail')
        
    @override(BaseDatabase)
    def select_as_sql_data_set(self, table_name: str, sql_statement: str) -> SqlDataSet:
        """
        Get a SqlDataSet instance.
        :param table_name: The table name
        :param sql_statement: The execution of this SQL statement returns the data that is the underlying data for the
            SqlDataSet instance.
        :returns: SqlDataSet.
        """    
        results = self.execute_and_fetch(sql_statement)
        
        return self.__convertToSqlDataSet(table_name, sql_statement, results)    
      
    @override(BaseDatabase)
    def shutdown(self):
        """Dispose the engine and close all the connections."""
        if self.__engine is not None:
            self.__engine.dispose(close= True)
