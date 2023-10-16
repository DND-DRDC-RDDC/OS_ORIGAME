# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*:

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path

# [2. third-party]
from PyQt5.Qt import Qt
from PyQt5.QtCore import QSettings
from PyQt5.QtWidgets import QDialog, QFileDialog, QSpinBox, QMessageBox, QWidget, QDialogButtonBox

# [3. local]
from ...core import override
from ...core.typing import List
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import FilePart
from ...scenario import ori, ScenarioManager

from ..gui_utils import get_input_error_description, PyExpr, get_scenario_font, exec_modal_dialog
from ..gui_utils import get_scenario_font, PathExprValidator
from ..constants import DETAILED_PARAMETER_SYNTAX_DESCRIPTION
from ..slow_tasks import get_progress_bar
from ..safe_slot import safe_slot
from ..async_methods import AsyncRequest, AsyncErrorInfo

from .scenario_part_editor import BaseContentEditor, DataSubmissionValidationError
from .Ui_file_part_editor import Ui_FilePartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"


# -- Module-level objects -----------------------------------------------------------------------

__all__ = [  
    # public API of module: one line per string
    'FilePartEditorPanel'
]

log = logging.getLogger('system')

SCENARIO_PATH = Path(__file__).parent / "scenario"


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class FilePartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """
    # The initial size to make this editor look nice.
    INIT_WIDTH = 665
    INIT_HEIGHT = 200
    FILE_PATH = 'part_editors.file_part_editor.FilePartEditorPanel.file_path'

    def __init__(self, part: FilePart, parent: QWidget = None):
        """
        Initializes this panel with a back end File Part and a parent QWidget.

        :param part: The File Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_FilePartEditorWidget()
        self.ui.setupUi(self)
        self.__val_wrapper = PyExpr()
        self.__path_str = ''
        self.ui.file_path_linedit.setFont(get_scenario_font())
        self.__relative_to_folder = False

        self.ui.file_path_button.pressed.connect(self.__slot_select_file_path_button)
        self.ui.folder_path_button.pressed.connect(self.__slot_select_folder_path_button)
        self.ui.file_part_relative_to_scenario_folder_checkbox.stateChanged.connect(
            self.__slot_relative_to_scenario_folder_checked)
        self.ui.file_path_linedit.editingFinished.connect(self.__slot_select_file_path_linedit)
        self.__scen_path = ''
        if part.get_shared_scenario_state().scen_filepath:
            self.__scen_path = str(part.get_shared_scenario_state().scen_filepath.parent)
        else:
            self.ui.file_part_relative_to_scenario_folder_checkbox.setDisabled(True)

        part.get_shared_scenario_state().signals.sig_scenario_path_changed.connect(self.__slot_on_scen_path_changed)

        self.__file_part = part
        self.__path_validator = PathExprValidator(self.ui.file_path_linedit,
                                                  self.ui.file_part_relative_to_scenario_folder_checkbox,
                                                  self.__scen_path)
        self.__path_validator.validate(self.__path_str, 0)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        return [self.ui.file_path_linedit]

    @override(BaseContentEditor)
    def _snapshot_initial_data(self, data: Dict[str, Any]):
        """
        Converts the Path object to string
        :param data: The data to be preserved.
        """
        BaseContentEditor._snapshot_initial_data(self, data)
        if self._initial_data['filepath']:
            self._initial_data['filepath'] = str(self._initial_data['filepath'])
        else:
            self._initial_data['filepath'] = ''

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        return dict(filepath=self.ui.file_path_linedit.text(), is_relative_to_scen_folder=self.__relative_to_folder)

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        if data['filepath']:
            self.__path_str = str(data['filepath'])
        else:
            self.__path_str = ''

        self.__relative_to_folder = data['is_relative_to_scen_folder']
        self.ui.file_path_linedit.setText(self.__path_str)
        self.ui.file_part_relative_to_scenario_folder_checkbox.setChecked(self.__relative_to_folder)

    def __select_file_path_button(self):
        """
        Select a top-level folder to hold the file path from the file browser.
        """
        if not QSettings().value(self.FILE_PATH):
            QSettings().setValue(self.FILE_PATH, self.__scen_path)
        (file_path, ok) = QFileDialog.getOpenFileName(self, "Select a File Part file",
                                                              QSettings().value(self.FILE_PATH))

        if not file_path:
            return

        QSettings().setValue(self.FILE_PATH, file_path)
        self.ui.file_path_linedit.setText(file_path)

    def __select_folder_path_button(self):
        """
        Select a top-level folder to hold the file part folder (directory only) from the file browser.
        """
        file_path_folder = QFileDialog.getExistingDirectory(self, "Select a file part folder",
                                                            self.__scen_path,
                                                            options=QFileDialog.ShowDirsOnly)

        if not file_path_folder:
            return

        self.ui.file_path_linedit.setText(file_path_folder)

    def __relative_to_scenario_folder_checked(self, checked: int):
        """
        Relative to scenario folder checked/unchecked.
        :param checked: The Qt.CheckState that is 'Unchecked', 'PartiallyChecked', or 'Checked'.
        """
        # Need to notify the validator to re-evaluate the path string
        self.__path_validator.set_relative_to_folder(checked)

        if checked == Qt.Checked:
            self.__relative_to_folder = True
        else:
            self.__relative_to_folder = False

    def __select_file_path_linedit(self):
        """
        Select a top-level folder to hold the file path by entering the directory path.
        """
        file_path = self.ui.file_path_linedit.text()

        if not file_path:
            return

        file_path_result = Path(file_path)
        # print a warning if the file path folder specified does not exist and has not previously been set
        if not file_path_result.exists():
            log.warning("The file path specified does not exist.")

        if Path(file_path).is_absolute():
            QSettings().setValue(self.FILE_PATH, file_path)

    def __on_scen_path_changed(self, scen_path: str):
        """
        Updates the path to the scenario folder.
        :param filepath: the scenario filepath (path\filename)
        """
        self.__scen_path = str(scen_path)
        if scen_path is None:
            self.ui.file_part_relative_to_scenario_folder_checkbox.setDisabled(True)
        else:
            self.ui.file_part_relative_to_scenario_folder_checkbox.setEnabled(True)

    __slot_select_file_path_button = safe_slot(__select_file_path_button)
    __slot_select_folder_path_button = safe_slot(__select_folder_path_button)
    __slot_relative_to_scenario_folder_checked = safe_slot(__relative_to_scenario_folder_checked)
    __slot_select_file_path_linedit = safe_slot(__select_file_path_linedit)
    __slot_on_scen_path_changed = safe_slot(__on_scen_path_changed)


register_part_editor_class(ori.OriFilePartKeys.PART_TYPE_FILE, FilePartEditorPanel)