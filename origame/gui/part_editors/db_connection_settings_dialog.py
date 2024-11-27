# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Dialog to configure databases connections.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from PyQt5.QtWidgets import QWidget,  QDialog

# [2. third-party]

# [3. local]
from ..gui_utils import PyExpr
from .Ui_db_connection_settings_dialog import Ui_DbConnectionSettingsDialog
from ...core.typing import Dict
from .common import EditorDialog
from ...core import override
from ...scenario.database_configs import DatabaseTypeEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"


# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------
    
class DbConnectionSettingsDialog(EditorDialog):
    """
    Represents the database connection settings dialog.
    """

    def __init__(self, db_connection_settings: Dict[int, str], db_type: int, parent: QWidget = None):
        """
        Initializes this panel using the given connection string settings and database type..

        Args:
            db_connection_settings (Dict[int, str]): database connection settings.
            db_type (int): database type.
            parent (QWidget, optional): The Sql Part Editor parent.
        """
                
        super().__init__(parent)
        self.ui = Ui_DbConnectionSettingsDialog()
        self.ui.setupUi(self)  
        
        # Initialize database connection settings
        self.__db_connection_settings = db_connection_settings
        
        self.ui.access_filepath.setText(self.__db_connection_settings.get(DatabaseTypeEnum.MS_SQL.value, ''))
        self.ui.ms_sql_connection.setText(self.__db_connection_settings.get(DatabaseTypeEnum.MS_ACCESS.value, ''))
        self.ui.my_sql_connection.setText(self.__db_connection_settings.get(DatabaseTypeEnum.MYSQL.value, ''))
        self.ui.postgresql_connection.setText(self.__db_connection_settings.get(DatabaseTypeEnum.POSTGRESQL.value, ''))
        self.ui.sqliteFilePath.setText(self.__db_connection_settings.get(DatabaseTypeEnum.SQLITE.value, ''))
        self.ui.generic_connection.setText(self.__db_connection_settings.get(DatabaseTypeEnum.GENERIC.value, ''))
        
        # Set current tab based on the value of type selector
        self.__set_db_type_tab(db_type)

    def __set_db_type_tab(self, db_type: int):
        """Selects the tab based on the value of database type selector.
        
        Args:
            db_type (int): database type.
        """
        selected_type = db_type
        
        tab_name = None
        match selected_type:
            case 0:
                tab_name = 'ms_access_tab'
            case 1:
                tab_name = 'ms_sql'
            case 2:
                tab_name = 'my_sql_tab'
            case 3:
                tab_name = 'postgresql'
            case 4:
                tab_name = 'sqlite'
            case 5:
                tab_name = 'generic'
        
        tab_widget = self.ui.tabWidget
        tab_widget.setCurrentWidget(tab_widget.findChild(QWidget, tab_name))
                      
    @override(QDialog)
    def accept(self):
        """Override to get the database connections configuration values and set them in the backend before closing the dialog"""
        self.__db_connection_settings[DatabaseTypeEnum.MS_ACCESS.value] = self.ui.access_filepath.text()
        self.__db_connection_settings[DatabaseTypeEnum.MS_SQL.value] = self.ui.ms_sql_connection.text()
        self.__db_connection_settings[DatabaseTypeEnum.MYSQL.value] = self.ui.my_sql_connection.text()
        self.__db_connection_settings[DatabaseTypeEnum.POSTGRESQL.value] = self.ui.postgresql_connection.text()
        self.__db_connection_settings[DatabaseTypeEnum.SQLITE.value] = self.ui.sqliteFilePath.text()
        self.__db_connection_settings[DatabaseTypeEnum.GENERIC.value] = self.ui.generic_connection.text()
        
        super().accept()

    def get_db_connection_settings(self) -> Dict[int, str]:
        """
        Get database connection settings from the dialog.
        :return: the database connection settings Dictinary
        """
        return self.__db_connection_settings

  
    #__slot_select_module_path = safe_slot(__select_module_path)
    #__slot_input_module_path = safe_slot(__input_module_path)