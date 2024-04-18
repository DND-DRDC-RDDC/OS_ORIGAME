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
from PyQt5.QtWidgets import QWidget, QLineEdit, QLabel, QHeaderView
from PyQt5.QtGui import QMouseEvent, QIcon
from PyQt5.Qt import Qt

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.part_execs import PyDebugger, LinkedPartsScriptingProxy, LINKS_SCRIPT_OBJ_NAME
from ...scenario.defn_parts import BasePart
from ..gui_utils import get_scenario_font, get_icon_path
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

LOCAL_VARIABLES_TABLE_HEADER_NAMES = ['Name', 'Value']

# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------
class PythonExpression(QLineEdit):
    """
    Extends QLineEdit so that everything in the textbox gets highlighted when the user clicks on it.
    """

    def __init__(self, parent):
        """
        :param part: The widget this python expression box is being added to.
        """
        super().__init__(parent)

    @override(QLineEdit)
    def mousePressEvent(self, mouse_press_event: QMouseEvent):
        super().mousePressEvent(mouse_press_event)
        self.selectAll()

class DebugOpsPanel(QWidget):
    def __init__(self, parent):
        """
        :param parent:  The Function part that is being debugged.
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
        self.ui.clear_button.clicked.connect(self._slot_on_clear_pyexpr)
        self.python_expression = PythonExpression(self.ui.groupBox)
        self.ui.horizontalLayout_4.insertWidget(0, self.python_expression)
        self.python_expression.returnPressed.connect(self._slot_on_eval_pyexpr)
        self.ui.breakpoint_on_off_button.clicked.connect(self._slot_on_breakpoint_on_off_button_clicked)
        self.ui.local_variables_table.setHorizontalHeaderLabels(LOCAL_VARIABLES_TABLE_HEADER_NAMES)
        self.ui.local_variables_table.verticalHeader().setVisible(False)
        self.ui.local_variables_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.ui.local_variables_table.cellDoubleClicked.connect(self._slot_on_local_var_clicked)
        self.ui.local_variables_table.setFont(get_scenario_font(mono=True))
        self.__local_debug_vars = dict()
        _variable_refresh_button_icon = QIcon(str(get_icon_path("shortcut_refresh.svg")))
        self.ui.variable_refresh_button.setIcon(_variable_refresh_button_icon)
        self.ui.variable_refresh_button.setFixedHeight(self.ui.label.size().height())
        self.ui.variable_refresh_button.setFixedWidth(self.ui.label.size().height())
        self.ui.variable_refresh_button.clicked.connect(self._slot_on_variable_refresh_button_clicked)

    def set_local_variables(self, variables: Dict[str, str]):
        """
        Accessory method to fill local variables table widget.
        """
        self.ui.local_variables_table.clear()
        self.ui.local_variables_table.setRowCount(0)
        self.ui.local_variables_table.setHorizontalHeaderLabels(LOCAL_VARIABLES_TABLE_HEADER_NAMES)
        self.ui.expression_result_list.clear()

        __part = self._get_debugged_part()
        _parts_proxy = LinkedPartsScriptingProxy(__part)

        num_total_items = 0
        var_name_col = 0
        var_value_col = 1

        for row, var in enumerate(variables.items()):
            # "var" is a list of two elements:
            #       the first element (i.e. var[var_name_col]) is the name of the local variable, and
            #       the second element (i.e. var[var_value_col]) is the value of the corresponding local variable
            # Don't add built-in variables and "_parts_proxy" to the table of local variables
            if var[var_name_col] != '__builtins__' and not isinstance(var[var_value_col], LinkedPartsScriptingProxy):
                self.ui.local_variables_table.insertRow(row)

                _var_name = QLabel(var[var_name_col])
                _var_name.setAlignment(Qt.AlignHCenter)
                self.ui.local_variables_table.setCellWidget(row, var_name_col, _var_name)

                _var_value = QLabel(str(var[var_value_col]))
                _var_value.setAlignment(Qt.AlignHCenter)
                self.ui.local_variables_table.setCellWidget(row, var_value_col, _var_value)

                num_total_items += 1

        # Add the names of parts accessible through the link object to the table of local variables.
        # Add links to parts only but not to part frames (i.e. names starting and ending with _)
        for item in _parts_proxy.__dir__():
            if item.startswith("_") and item.endswith("_"):
                continue

            self.ui.local_variables_table.insertRow(num_total_items)

            _var_name = QLabel(f"link.{item}")
            _var_name.setAlignment(Qt.AlignHCenter)
            self.ui.local_variables_table.setCellWidget(num_total_items, var_name_col, _var_name)

            _var_value = QLabel(str(_parts_proxy.__getattr__(item)))
            _var_value.setAlignment(Qt.AlignHCenter)
            self.ui.local_variables_table.setCellWidget(num_total_items, var_value_col, _var_value)    

            num_total_items += 1

        self.__local_debug_vars = variables
        self.__local_debug_vars[LINKS_SCRIPT_OBJ_NAME] = _parts_proxy

    def enable_widgets(self, enable: bool):
        """
        Helper method to enable/disable widgets within the panel.
        :param enable: Parameter indicating whether or not to enable or disable widgets within the panel.
        """
        self.ui.step_button.setEnabled(enable)
        self.ui.continue_button.setEnabled(enable)
        self.ui.step_into_button.setEnabled(enable)
        self.ui.evaluate_button.setEnabled(enable)
        self.ui.clear_button.setEnabled(enable)
        self.ui.stop_button.setEnabled(enable)
        self.python_expression.setEnabled(enable)
        self.ui.local_variables_table.setEnabled(enable)
        self.ui.expression_result_list.setEnabled(enable)

    def _get_debugged_part(self) -> BasePart:
        """
        Get the part being debugged
        """
        return PyDebugger.get_singleton().current_debug_info.py_part

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

        AsyncRequest.call(evaluate, self.python_expression.text(), response_cb=on_result, error_cb=on_error)

    def _on_clear_pyexpr(self):
        """
        Clears the python expression field and expression result.
        Called when the Clear button is clicked
        """
        self.ui.expression_result_list.clear()
        self.python_expression.setText("")

    def _on_breakpoint_on_off_button_clicked(self):
        """
        Called when the Breakpoint On/Off button is clicked.
        """
        pass

    def _on_local_var_clicked(self, row: int, col: int):
        """
        Called when a cell in the local variables table is clicked.
        """
        # Always get the name of the variable (i.e. column 0) of the clicked row
        # regardless if the user clicked on the variable name or value of that row.
        _var = self.ui.local_variables_table.cellWidget(row, 0).text()
        self.python_expression.insert(_var)
        self.python_expression.setFocus(Qt.OtherFocusReason)

    def _fill_expression_result(self, expression_results: Any):
        """
        Accessory method to fill expression result list widget.
        """
        self.ui.expression_result_list.clear()
        for result_str in expression_results:
            self.ui.expression_result_list.addItem(str(result_str))

    def _on_variable_refresh_button_clicked(self):
        """
        Clicked when the local variables refresh button is clicked.
        """
        debug_info = PyDebugger.get_singleton().current_debug_info
        self.set_local_variables(debug_info.local_vars)

    _slot_on_continue_button_clicked = safe_slot(_on_continue_button_clicked)
    _slot_on_step_button_clicked = safe_slot(_on_step_button_clicked)
    _slot_on_step_into_button_clicked = safe_slot(_on_step_into_button_clicked)
    _slot_on_stop_button_clicked = safe_slot(_on_stop_button_clicked)
    _slot_on_eval_pyexpr = safe_slot(_on_eval_pyexpr)
    _slot_on_clear_pyexpr = safe_slot(_on_clear_pyexpr)
    _slot_on_breakpoint_on_off_button_clicked = safe_slot(_on_breakpoint_on_off_button_clicked)
    _slot_on_local_var_clicked = safe_slot(_on_local_var_clicked)
    _slot_on_variable_refresh_button_clicked = safe_slot(_on_variable_refresh_button_clicked)
