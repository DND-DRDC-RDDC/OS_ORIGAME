# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: FunctionPartEditor class.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QCheckBox
from PyQt5.QtCore import Qt

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ...core import override
from ...scenario import ori
from ...scenario.defn_parts import BasePart, RunRolesEnum

from ..gui_utils import try_disconnect
from ..undo_manager import FunctionPartToggleRoleCommand, scene_undo_stack
from ..async_methods import AsyncRequest
from ..safe_slot import safe_slot
from .script_editing import PythonScriptEditor
from .scenario_part_editor import BaseContentEditor
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'FunctionPartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

class FunctionPartEditorPanel(PythonScriptEditor):
    """
    Function Part Editor class.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    USE_CALL_PARAMS = True

    # The initial size to make this editor look nice.
    INIT_WIDTH = 800
    INIT_HEIGHT = 640

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: BasePart, parent: QWidget = None):
        super().__init__(part, parent=parent)
        self.ui.role_group_box.setVisible(True)
        # A map to make the lookup easier
        self.__map_role_to_role_items = {RunRolesEnum.startup: (self.ui.startup_checkbox, self.ui.startup_spinbox),
                                         RunRolesEnum.reset: (self.ui.reset_checkbox, self.ui.reset_spinbox),
                                         RunRolesEnum.finish: (self.ui.finish_checkbox, self.ui.finish_spinbox),
                                         RunRolesEnum.setup: (self.ui.setup_checkbox, self.ui.setup_spinbox),
                                         RunRolesEnum.batch: (self.ui.batch_checkbox, self.ui.batch_spinbox)}

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        super()._on_data_arrived(data)
        self.ui.code_editor.set_breakpoints(data['breakpoints'])
        self.ui.part_params.setText(data['parameters'])
        # When the editor is opened, all the check boxes are off, and their numbers are 0.
        # The check boxes are set to True only for those roles available in the dict.
        for role, num in data['roles_and_prioritizing'].items():
            role_checkbox, role_spinbox = self.__map_role_to_role_items[role]
            role_checkbox.setChecked(True)
            role_spinbox.setValue(num)

        self.ui.code_editor.setFocus()

    @override(PythonScriptEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Collects the addition info - run_roles
        :returns: the data that has the additional info - run_roles
        """
        data_dict = super()._get_data_for_submission()
        roles = dict()
        for role, (checkbox, spinbox) in self.__map_role_to_role_items.items():
            if checkbox.isChecked():
                roles[role] = spinbox.value()

        data_dict['roles_and_prioritizing'] = roles

        return data_dict


register_part_editor_class(ori.OriFunctionPartKeys.PART_TYPE_FUNCTION, FunctionPartEditorPanel)
