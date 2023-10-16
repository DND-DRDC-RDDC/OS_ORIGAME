# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Dialog to import new symbol object.

[EDIT:]PEP 8 defers to PEP 257 for docstrings: Multi-line docstrings consist of a summary line just like a 
[EDIT:]one-line docstring, followed by a blank line, followed by a more elaborate description. The 
[EDIT:]docstring for a module should generally list the classes, exceptions and functions (and any other 
[EDIT:]objects) that are exported by the module, with a one-line summary of each.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import importlib
from importlib import import_module

# [2. third-party]
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QDialog, QFileDialog, QSpinBox, QMessageBox, QWidget
from PyQt5.QtGui import QValidator

# [3. local]
from ..gui_utils import get_input_error_description, PyExpr, DETAILED_PARAMETER_SYNTAX_DESCRIPTION, get_scenario_font
from .Ui_import_object_dialog import Ui_ImportObjectDialog
from ...scenario.part_execs  import PyScriptExec
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..safe_slot import safe_slot
from ..gui_utils import ImportSourceModuleExprValidator, PythonNameValidator
from .common import EditorDialog
from ...core import override

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"


# -- Module-level objects -----------------------------------------------------------------------

__all__ = [  
    # public API of module: one line per string
    '[EDIT:]'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

class ImportObjectDialog(EditorDialog):
    """
    Represents the import symbol object dialog.
    """

    # def __init__(self, source_module: str, use_attr_name: bool, attr_name: str, as_sym_name: bool, sym_name: str,
    #              parent: QWidget = None):
    def __init__(self, parent: QWidget = None):
        """
        Initializes this panel with a back end File Part and a parent QWidget.

        :param part: The File Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(parent)
        self.ui = Ui_ImportObjectDialog()
        self.ui.setupUi(self)
        self.__val_wrapper = PyExpr()
        self.__source_module_str = None
        self.__use_attr_name = False
        self.__attr_name = None
        self.__sym_name = None

        self.ui.module_location_edit.setFont(get_scenario_font())
        self.ui.symbol_list.setFont(get_scenario_font())
        self.ui.symbol_name_edit.setFont(get_scenario_font())

        self.ui.select_button.pressed.connect(self.__slot_select_module_path)
        self.ui.module_location_edit.textChanged.connect(self.__slot_input_module_path)

        self.__source_module_validator = ImportSourceModuleExprValidator(self.ui.module_location_edit)
        self.__source_module_validator.validate('', 0)

        self.__as_symbol_validator = PythonNameValidator(self.ui.symbol_name_edit)

        self.ui.symbol_list.setDisabled(True)
        self.ui.symbol_name_edit.setDisabled(True)
        self.ui.attr_name.setDisabled(True)
        self.ui.as_symbol_name_label.setDisabled(True)

        # Hide the select_button (button with "...") for this release
        self.ui.select_button.hide()

    @override(QDialog)
    def accept(self):
        """Override to get the dialog values and set them in the backend before closing the dialog"""

        self.__source_module_str = self.ui.module_location_edit.text()
        self.__use_attr_name = self.ui.attr_name.isChecked()
        self.__attr_name = self.ui.symbol_list.currentText()
        self.__sym_name = self.ui.symbol_name_edit.text()

        super().accept()

    def get_user_input(self) -> Tuple[int, bool]:
        """
        OGet the input from the dialog.
        :return: A tuple of user input.
        """
        assert self.__source_module_str is not None
        return self.__source_module_str, self.__use_attr_name, self.__attr_name, self.__sym_name

    def __select_module_path(self):
        """
        Select a file to hold module object.
        """
        pass

    def __input_module_path(self):
        """
        Get user input module object path.
        """
        self.ui.symbol_list.clear()
        self.ui.symbol_list.update()
        self.ui.symbol_list.setDisabled(True)
        self.ui.symbol_name_edit.setDisabled(True)
        self.ui.attr_name.setDisabled(True)
        self.ui.as_symbol_name_label.setDisabled(True)

        source_module_text = self.ui.module_location_edit.text()

        if not source_module_text:
            return

        try:
            importlib.util.find_spec(source_module_text)
        except Exception:
            # Exeception when 'xxx.' entered, and 'xxx' is not a package
            pass
        else:
            if importlib.util.find_spec(source_module_text) is not None:
                self.__populate_attr_name(source_module_text)
                self.ui.symbol_list.setEnabled(True)
                self.ui.symbol_name_edit.setEnabled(True)
                self.ui.attr_name.setEnabled(True)
                self.ui.as_symbol_name_label.setEnabled(True)

    def __populate_attr_name(self, module_text: str):
        """
        Populate the attribute name in combo box list.
        """
        symbol_attri_list = self.ui.symbol_list
        symbol_attri_list.clear()
        module_dict = import_module(module_text).__dict__

        for name in sorted(module_dict, key=str.lower):
            if not name.startswith('_'):
                symbol_attri_list.addItem(name)

        self.ui.symbol_list.update()

    __slot_select_module_path = safe_slot(__select_module_path)
    __slot_input_module_path = safe_slot(__input_module_path)

