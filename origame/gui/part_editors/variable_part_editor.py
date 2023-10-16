# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Variable Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import VariablePart
from ...scenario import ori

from ..gui_utils import get_input_error_description, PyExpr, get_scenario_font
from ..constants import DETAILED_PARAMETER_SYNTAX_DESCRIPTION

from .scenario_part_editor import BaseContentEditor, DataSubmissionValidationError
from .Ui_variable_part_editor import Ui_VariablePartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'VariablePartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class VariablePartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 600
    INIT_HEIGHT = 100

    def __init__(self, part: VariablePart, parent: QWidget = None):
        """
        Initializes this panel with a back end Variable Part and a parent QWidget.

        :param part: The Variable Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_VariablePartEditorWidget()
        self.ui.setupUi(self)
        self.__val_wrapper = PyExpr()
        self.__editable_str = ""
        self.ui.variable_data.setFont(get_scenario_font())

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        return [self.ui.variable_data]

    @override(BaseContentEditor)
    def _complete_data_submission_validation(self):
        """
        Validates if the value is a valid Python expression.
        :raises DataSubmissionValidationError: When the value is not a valid Python expression.
        """
        try:
            if self.__editable_str != self.ui.variable_data.toPlainText():
                self.__val_wrapper.str_repr = self.ui.variable_data.toPlainText()

        except Exception as exc:
            raise DataSubmissionValidationError(
                title="Edit Error",
                message=get_input_error_description(exc),
                detailed_message=DETAILED_PARAMETER_SYNTAX_DESCRIPTION
            )

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        return dict(editable_str=self.ui.variable_data.toPlainText())

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        self.__editable_str = data['editable_str']
        self.ui.variable_data.setPlainText(data['editable_str'])


register_part_editor_class(ori.OriVariablePartKeys.PART_TYPE_VARIABLE, VariablePartEditorPanel)
