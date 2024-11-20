# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains code to support accessing external databases.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from typing import List, Tuple
import pandas
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import text

# [2. third-party]

# [3. local]
from ..defn_parts import DatabaseConfig

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------
class DatabaseException(Exception):
    """
    This class represents a custom error raised on errors when accessing external databases.
    """
    pass

class Database():
    """Represents Generic database class to setup connection and send queries to different database types.
    """ 
    # Connection pool size
    POOL_SIZE = 5
    
    # --------------------------- instance (self) PUBLIC methods --------------------------------    
    def __init__(self, database_config: DatabaseConfig):
        """Initialize an instance of this class with a given connection string.

        Args:
            connection_string (str): connection string.
        
        Raises:
            DatabaseException: if connection string is invalid.
        """
        self.__db_type = database_config.__db_type
        self.__connection_srting = database_config.__connection_config.get(self.__db_type)
        
        if not self.validate_connection_string(self.__connection_string):
            raise DatabaseException("Invalid connection string {}.".format(self.__connection_string))
        
        self.__engine = None
   
    def validate_connection_string(self, connection_string: str) -> bool:
        """Verfy if a valid connection could be made to a database using given connection string.

        Args:
            connection_string (str): connection string to be verified.

        Returns:
            bool: true if a valid connection could be made to a database using given connection string, false otherwise. 
        """
        if connection_string is None or connection_string.isspace():
            return False
               
        try:
            engine = create_engine(connection_string) 
            engine.connect()
            log.info("The connection string '{}' is valid.")            
            return True
        except Exception as exc:
            log.error("Could not connect to the database specified by the connection string '{}' due to '{}'", connection_string, exc)
            return False       
    
    def execute(self, sql_statement: str) -> List[Tuple[any]]:
        """Execute the given sql statement.

        Args:
            sql_statement (str): A valid sql statement to execute.   

        Raises:
            DatabaseException: if any error executing the SQL statement.

        Returns:
            List[Tuple[any]]: data as a List of Tuples.
        """
        
        if sql_statement is None or sql_statement.isspace():
            raise DatabaseException("Invalid SQL statement {}.".format(sql_statement))
          
        engine = self.__get_engine(self.__connection_string)
        
        try:
            # Establish a connection and execute the SQL query
            connection = engine.connect()
        except Exception as exc:
            log.error("Could not connect to the database specified by the connection string '{}' due to '{}'", self.__connection_string, exc)
            
            raise DatabaseException("Could not connect to the database specified by the connection string '{}' due to '{}'", self.__connection_string, exc)
        else:
            with connection:
                result = connection.execute(text(sql_statement))
                
            # commits and closes automatically
            
            # Convert the result to a Pandas DataFrame
            df = pandas.DataFrame(result.fetchall(), columns=result.keys())
                
            # Convert DataFrame to list of tuples
            return list(df.itertuples(index=False, name=None)) 
   
    def execute_script(self, sql_scripts: str):
        """Execute the given sql script. Nothing is returned.

        Args:
            sql_scripts (str): A valid sql script to execute.   

        Raises:
            DatabaseException: if any error executing the SQL script.
        """
        if sql_scripts is None or sql_scripts.isspace():
            raise DatabaseException("Invalid SQL script {}.".format(sql_scripts))
          
        engine = self.__get_engine(self.__connection_string)
        
        try:
            # Establish a connection and start a transaction
            connection = engine.begin()
        except Exception as exc:
            log.error("Could not connect to the database specified by the connection string '{}' due to '{}'", self.__connection_string, exc)
            
            raise DatabaseException("Could not connect to the database specified by the connection string '{}' due to '{}'", self.__connection_string, exc)
        else:
            with connection:
                # Run statements of the script
                for sql_statement in sql_scripts.split('\n'):
                    connection.execute(text(sql_statement))
            # commits and closes automatically
               
    # --------------------------- instance __PRIVATE members-------------------------------------
    
    def __get_engine(self, connection_string: str) -> Engine:
        """Create an engine, if not already created. The engines is used to connect to the database represented by the given connection string.

        Args:
            connection_string: str (str): connection string used to create an engine.
        
        Returns:
            _type_: _description_
        """
        if (self.__engine is None):
            self.__engine = create_engine(connection_string, pool_size = self.POOL_SIZE)            
        
        return self.__engine        