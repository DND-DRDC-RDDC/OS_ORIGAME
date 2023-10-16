# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provides custom widgets to the Object Properties Panel.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QTextEdit, QLineEdit
from PyQt5.QtGui import QKeyEvent, QFocusEvent

# [3. local]
from ...core import override

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PartNameLineEdit',
    'CommentTextBox',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class PartNameLineEdit(QLineEdit):
    """
    Implements a QLineEdit widget but with a new 'sig_editing_finished' signal that is emitted only for new edits.

    The class checks if the field is still being edited and only allows the editing finished signal to be issued
    via an Enter, Return or loss-of-focus if there are new edits. This improves over the original class which fires
    off the editingFinished signal each time regardless of whether there are new edits.
    """
    sig_editing_finished = pyqtSignal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self._editing_mode = True
        self.setFocusPolicy(Qt.StrongFocus)
        self.valid_keys = (int(Qt.Key_Tab), int(Qt.Key_Return), int(Qt.Key_Enter))

    @override(QLineEdit)
    def keyPressEvent(self, key_event: QKeyEvent):
        super().keyPressEvent(key_event)

        key = key_event.key()

        if key in self.valid_keys:
            if self._editing_mode:
                self._editing_mode = False
                self.sig_editing_finished.emit()

        if key not in self.valid_keys:
            self._editing_mode = True

    @override(QLineEdit)
    def focusOutEvent(self, focus_out_event: QFocusEvent):
        super().focusOutEvent(focus_out_event)

        if self._editing_mode:
            self._editing_mode = False
            self.sig_editing_finished.emit()


class CommentTextBox(QTextEdit):
    """
    Implements a QTextEdit widget but with a new 'sig_editing_finished' signal that is emitted only for new edits.

    In addition to implementing an editing finished type signal that is not present in the base class, this  class
    checks if the field is still being edited and only allows the editing finished signal to be issued
    via an Enter, Return or loss-of-focus if there are new edits.
    """
    sig_editing_finished = pyqtSignal()

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self._editing_mode = True
        self.setFocusPolicy(Qt.StrongFocus)
        self.valid_keys = (int(Qt.Key_Tab), int(Qt.Key_Enter))

    @override(QTextEdit)
    def keyPressEvent(self, key_event: QKeyEvent):
        super().keyPressEvent(key_event)

        key = key_event.key()

        if key in self.valid_keys:
            if self._editing_mode:
                self.sig_editing_finished.emit()
                self._editing_mode = False

        if key not in self.valid_keys:
            self._editing_mode = True

    @override(QTextEdit)
    def focusOutEvent(self, focus_out_event: QFocusEvent):
        super().focusOutEvent(focus_out_event)

        if self._editing_mode:
            self.sig_editing_finished.emit()
            self._editing_mode = False
