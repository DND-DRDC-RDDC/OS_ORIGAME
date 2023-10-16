# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*:  Python Code debug operations panel.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QListWidgetItem

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.part_execs import PyDebugger
from ..gui_utils import get_scenario_font
from ..safe_slot import safe_slot
from ..async_methods import AsyncRequest, AsyncErrorInfo
from .Ui_ops_panel import Ui_DebugWidget

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'DebugOpsPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class DebugOpsPanel(QWidget):
    def __init__(self, parent):
        """
        :param part:  The Function part that is being debugged.
        """
        super().__init__(parent)
        self.setObjectName('DebugOpsPanel')
        self.ui = Ui_DebugWidget()
        self.ui.setupUi(self)
        self.ui.continue_button.clicked.connect(self._slot_on_continue_button_clicked)
        self.ui.step_button.clicked.connect(self._slot_on_step_button_clicked)
        self.ui.step_into_button.clicked.connect(self._slot_on_step_into_button_clicked)
        self.ui.stop_button.clicked.connect(self._slot_on_stop_button_clicked)
        self.ui.evaluate_button.clicked.connect(self._slot_on_eval_pyexpr)
        self.ui.python_expression.returnPressed.connect(self._slot_on_eval_pyexpr)
        self.ui.breakpoint_on_off_button.clicked.connect(self._slot_on_breakpoint_on_off_button_clicked)
        self.ui.local_variables_list.itemActivated.connect(self._slot_on_local_var_clicked)
        self.ui.local_variables_list.setFont(get_scenario_font(mono=True))
        self.__local_debug_vars = list()

    def set_local_variables(self, variables: List[str]):
        """
        Accessory method to fill local variables list widget.
        """
        self.ui.local_variables_list.clear()
        # self.ui.python_expression.clear()
        self.ui.expression_result_list.clear()

        num_total_items = 0
        for var_name in variables:
            # if not var_name.startswith('__'):
            if var_name != '__builtins__':
                self.ui.local_variables_list.addItem(var_name)
                num_total_items += 1

        self.ui.local_variables_list.sortItems()
        self.__local_debug_vars = variables

    def enable_widgets(self, enable: bool):
        """
        Helper method to enable/disable widgets within the panel.
        :param enable: Parameter indicating whether or not to enable or disable widgets within the panel.
        """
        self.ui.step_button.setEnabled(enable)
        self.ui.continue_button.setEnabled(enable)
        self.ui.step_into_button.setEnabled(enable)
        self.ui.evaluate_button.setEnabled(enable)
        self.ui.stop_button.setEnabled(enable)
        self.ui.python_expression.setEnabled(enable)
        self.ui.local_variables_list.setEnabled(enable)
        self.ui.expression_result_list.setEnabled(enable)

    def _on_continue_button_clicked(self):
        """
        Called when the Continue button is clicked. Direct call (not async) because backend thread event loop
        is stuck at breakpoint.
        """
        PyDebugger.get_singleton().next_command_continue()

    def _on_step_button_clicked(self):
        """
        Called when the Step button is clicked. Direct call (not async) because backend thread event loop
        is stuck at breakpoint.
        """
        PyDebugger.get_singleton().next_command_step_over()

    def _on_step_into_button_clicked(self):
        """
        Called when the Start button is clicked. Direct call (not async) because backend thread event loop
        is stuck at breakpoint.
        """
        PyDebugger.get_singleton().next_command_step_in()

    def _on_stop_button_clicked(self):
        """
        Called when the Stop button is clicked. Direct call (not async) because backend thread event loop
        is stuck at breakpoint.
        """
        PyDebugger.get_singleton().next_command_stop()

    def _on_eval_pyexpr(self):
        """
        Called when the Evaluate button is clicked.
        """

        def evaluate(expr_str: str) -> str:
            return str(eval(expr_str, self.__local_debug_vars))

        def on_result(*result):
            self._fill_expression_result(result)

        def on_error(error_info: AsyncErrorInfo):
            if isinstance(error_info.exc, SyntaxError):
                msg = "Syntax error at {} ({})".format(error_info.exc.offset, error_info.exc.msg)
            else:
                msg = error_info.msg
            self._fill_expression_result([msg])

        AsyncRequest.call(evaluate, self.ui.python_expression.text(), response_cb=on_result, error_cb=on_error)

    def _on_breakpoint_on_off_button_clicked(self):
        """
        Called when the Breakpoint On/Off button is clicked.
        """
        pass

    def _on_local_var_clicked(self, item: QListWidgetItem):
        self.ui.python_expression.insert(item.text())

    def _fill_expression_result(self, expression_results: Any):
        """
        Accessory method to fill expression result list widget.
        """
        self.ui.expression_result_list.clear()
        for result_str in expression_results:
            self.ui.expression_result_list.addItem(str(result_str))

    _slot_on_continue_button_clicked = safe_slot(_on_continue_button_clicked)
    _slot_on_step_button_clicked = safe_slot(_on_step_button_clicked)
    _slot_on_step_into_button_clicked = safe_slot(_on_step_into_button_clicked)
    _slot_on_stop_button_clicked = safe_slot(_on_stop_button_clicked)
    _slot_on_eval_pyexpr = safe_slot(_on_eval_pyexpr)
    _slot_on_breakpoint_on_off_button_clicked = safe_slot(_on_breakpoint_on_off_button_clicked)
    _slot_on_local_var_clicked = safe_slot(_on_local_var_clicked)
