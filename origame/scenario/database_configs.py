# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains code related to external databases configurations.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
from enum import Enum

# [2. third-party]

# [3. local]
from ..core.typing import Dict

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

class DatabaseTypeEnum(Enum):
    """Supported Database types"""    
    MS_ACCESS = 0
    MS_SQL = 1
    MYSQL = 2
    POSTGRESQL = 3
    SQLITE = 4
    GENERIC = 5
     
class DatabaseConfig():
    def __init__(self, db_type: int, connection_config: Dict[int, str], external_db_enabled: bool):
        """Initialize an instance of DatabaseConfig.

        Args:
            db_type (int): selected Database type for this part.
            connection_config (Dict[int, str]): database connection string configurations.
            external_db_enabled (bool): indicates whether use of external database is enabled.
        """
        self.__db_type = db_type;
        self.__connection_config = connection_config
        self.__external_db_enabled = external_db_enabled
        
    def get_connection_config(self) -> Dict[DatabaseTypeEnum, str]:
        """Get the database connection configurations.

        Returns:
            Dict[DatabaseTypeEnum, str]: the database connection configurations.
        """
        return self.__connection_config
    
    def get_db_type(self) -> int:
        """Get the database type.

        Returns:
            int: the database type.
        """
        return self.__db_type
    
    def is_external_db_enabled(self) -> bool:
        """Get the flag that indicated whether external databases is enabled.

        Returns:
            bool: flag that indicated whether external databases is enabled.
        """
        return self.__external_db_enabled
        