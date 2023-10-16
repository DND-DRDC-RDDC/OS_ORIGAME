# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Module for encapsulating debug behaviour.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from textwrap import dedent

# [2. third-party]
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialogButtonBox, QPushButton, QMessageBox, QDialog, QWidget, QAbstractButton

# [3. local]
from ...core import override
from ...scenario.part_execs import PyDebugger, PyDebugInfo

from ..gui_utils import get_scenario_font, exec_modal_dialog
from ..safe_slot import safe_slot
from ..async_methods import AsyncRequest
from ..script_panel import PyCodingAssistant

from .Ui_debugger_panel import Ui_DebugCodeViewerPanel

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'DebugCodeViewer'
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

class DebugCodeViewer(QDialog):
    """
    Class that provides functioanlity for debugging code in scenario part scripts
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent,
                         (Qt.Dialog | Qt.WindowCloseButtonHint | Qt.WindowMinMaxButtonsHint | Qt.WindowTitleHint))

        self.ui = Ui_DebugCodeViewerPanel()
        self.ui.setupUi(self)
        self.ui.text_parameters.setFont(get_scenario_font())
        self.setWindowTitle("Python Code Debugger")
        self.ui.code_viewer.sig_breakpoint_toggled.connect(self.slot_on_toggle_breakpoint)
        self.ui.code_viewer.setReadOnly(True)
        self.ui.code_viewer.enable_breakpoint_marking()

        self.ui.button_close.clicked.connect(self.slot_on_button_close_clicked)
        self.ui.ops_panel.ui.breakpoint_on_off_button.setVisible(False)
        self.ui.part_name.setEnabled(False)
        self.ui.part_name.setFont(get_scenario_font())
        self.ui.part_path.setFont(get_scenario_font())

        self.__part = None
        self.set_debugging(None)

    @override(QDialog)
    def reject(self, confirm: bool = True):
        """Called automatically when close dialog or cancel it."""
        if self.__part is not None:
            # in the middle of debugging a part, have to stop the debugger; but if confirm True, ask first!
            if confirm:
                msg = """\
                    Do you want to stop debugging?
                    - Click Yes to abort the current execution of code. (If this code was reached
                      by running a simulation, clicking Yes PAUSES the simulation.)
                    - Click No to return to the Debug View.
                    """
                answer = exec_modal_dialog("Abort Run", dedent(msg), QMessageBox.Question)
                if answer == QMessageBox.No:
                    return

            PyDebugger.get_singleton().next_command_stop()

        QDialog.reject(self)

    def set_debugging(self, value: bool = True):
        """
        Enter or exit debugging.
        :param value: True for start debugging, false to end debugging session
        """
        if value:
            debug_info = PyDebugger.get_singleton().current_debug_info

            self.__part = debug_info.py_part
            self.__fill_content()
            self.__set_cursor_position(debug_info)

            self.ui.code_viewer.set_coding_assistant(PyCodingAssistant(self.__part))
            self.ui.code_viewer.set_debug_mode(True)
            self.ui.code_viewer.set_breakpoints(self.__part.get_breakpoints())
            self.ui.code_viewer.setEnabled(True)
            self.ui.code_viewer.setReadOnly(True)

            self.ui.ops_panel.set_local_variables(debug_info.local_vars)
            self.ui.ops_panel.enable_widgets(True)

        else:
            self.__part = None

            self.ui.code_viewer.set_debug_mode(False)
            self.ui.ops_panel.enable_widgets(False)
            self.ui.code_viewer.setEnabled(False)

    def focus(self):
        """
        Set the focus to the code viewer.
        """
        self.ui.code_viewer.setFocus()

    def on_close_dialog(self, button: QPushButton):
        """
        Method called when a button is clicked .
        :param button:  The button that was clicked.
        """
        button_role = self.ui.button_close.buttonRole(button)
        if button_role == QDialogButtonBox.RejectRole:
            self.reject()

    def on_toggle_breakpoint(self):
        """
        This method is called when a click occurs on the left margin.
        :param line_number: The line number at which a margin clicked ocurred.
        """
        breakpoints_in_editor = self.ui.code_viewer.get_breakpoints()

        def attempt_save():
            self.__part.clear_all_breakpoints()
            for line_number in breakpoints_in_editor:
                self.__part.set_breakpoint(line_number)

        AsyncRequest.call(attempt_save)

    slot_on_button_close_clicked = safe_slot(on_close_dialog, arg_types=[QAbstractButton])
    slot_on_toggle_breakpoint = safe_slot(on_toggle_breakpoint)

    def __set_cursor_position(self, debug_info: PyDebugInfo):
        """
        When debugging starts, this method is used to set the cursor position on line which is being debugged
        within the code viewer.

        Note: The PyDebugger provides this information but count line numbers from 1, whereas the code viewer
        is zero based, so DEBUGGER_TO_EDITOR_LINE_OFFSET is needed
        :param debug_info: Any that contains filename, line # etc
        """
        line_no = (debug_info.line_no -
                   self.__part.get_debug_line_offset() -
                   self.ui.code_viewer.DEBUGGER_TO_EDITOR_LINE_OFFSET)
        self.ui.code_viewer.setCursorPosition(line_no, 0)

    def __fill_content(self):
        """
        Helper method used to fill the contents of the code viewer with information from the part.
        """
        assert self.__part is not None
        self.ui.part_name.setText(self.__part.name)
        self.ui.part_path.setText(self.__part.get_path(with_name=False))
        self.ui.part_type.setText(self.__part.PART_TYPE_NAME)
        self.ui.code_viewer.setText(self.__part.script)

        # some types of parts might have parameters:
        try:
            self.ui.text_parameters.setText(self.__part.parameters)
        except Exception:
            self.ui.label_parameters.hide()
            self.ui.text_parameters.hide()
        else:
            self.ui.label_parameters.show()
            self.ui.text_parameters.show()
