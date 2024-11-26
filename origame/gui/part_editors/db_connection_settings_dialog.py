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

    def __init__(self, parent: QWidget = None):
        """
        Initializes this panel with a back end Sql Part Editor and a parent QWidget.

        :param part: The Sql Part Editor parent.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(parent)
        self.ui = Ui_DbConnectionSettingsDialog()
        self.ui.setupUi(self)        
        self.__val_wrapper = PyExpr()
        
        # Initialize database connection settings
        self.__db_connection_settings = {}
              
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