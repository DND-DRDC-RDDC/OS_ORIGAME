# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The Special Value Editor is used to edit an object that does not have a string representation
that fully represents the object, or whose string representation is too long.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QDialog
from PyQt5.QtCore import Qt

# [3. local]
from ...core import override_required
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..gui_utils import PyExpr, exec_modal_input_error_dialog, set_default_dialog_frame_flags
from ..safe_slot import safe_slot
from .Ui_special_value_editor import Ui_SpecialValueEditor

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SpecialValueDisplay',
    'SpecialValueEditor'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------


class SpecialValueDisplay:
    """
    Used to manage common features of the part editors that need to pop up a SpecialValueEditor.
    """

    def __init__(self):
        self.__special_value_editor = SpecialValueEditor()

    @override_required
    def _get_special_value(self) -> object:
        """
        The derived class must specifies an object to be edited.
        :return: The object to be edited
        """
        raise NotImplementedError

    @override_required
    def _set_special_value(self, val: Any):
        """
        The derived class consumes the edited value.
        :param val: The edited value
        """
        raise NotImplementedError

    def _open_special_value_editor(self):
        """
        Opens the Special Value Editor if the cell presented by the derived class in _get_special_cell() is not
        representable.
        """
        the_cell = self._get_special_value()
        if the_cell.is_representable():
            return

        self.__special_value_editor.special_value = the_cell
        if self.__special_value_editor.exec() == QDialog.Accepted:
            self._set_special_value(self.__special_value_editor.special_value)


class SpecialValueEditor(QDialog):
    """
    """

    def __init__(self, parent: QWidget = None):
        """

        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(parent)
        self.ui = Ui_SpecialValueEditor()
        self.ui.setupUi(self)
        self.ui.button_box.accepted.connect(self.__slot_accepted)
        self.ui.button_box.rejected.connect(self.__rejected)
        set_default_dialog_frame_flags(self)
        self.__special_value = PyExpr()

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------
    def get_special_value(self):
        return self.__special_value

    def set_special_value(self, val: PyExpr):
        self.__special_value = val
        self.ui.value_edit.setPlainText(val.str_repr)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    special_value = property(get_special_value, set_special_value)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __accepted(self):
        try:
            self.__special_value.str_repr = self.ui.value_edit.toPlainText()
        except Exception as exc:
            exec_modal_input_error_dialog(exc)
            return

        self.accept()

    def __rejected(self):
        self.reject()

    __slot_accepted = safe_slot(__accepted)
    __slot_rejected = safe_slot(__rejected)
