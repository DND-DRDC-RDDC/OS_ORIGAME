# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Call parameter and argument management module is used to analyze the call signature and collect
input data to satisfy the signature.


Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from inspect import signature, Parameter

# [2. third-party]
from PyQt5.QtCore import QObject, QCoreApplication
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QValidator
from PyQt5.QtWidgets import QMessageBox, QDialog, QLineEdit
from PyQt5.QtWidgets import QFormLayout, QDialogButtonBox

# [3. local]
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ..core import override
from ..core.utils import get_verified_eval

from ..scenario.part_execs import get_params_from_str

from .Ui_input_parameters import Ui_InputParametersDialog
from .safe_slot import safe_slot
from .gui_utils import set_default_dialog_frame_flags, get_scenario_font
from .gui_utils import exec_modal_dialog, exec_modal_input_error_dialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "Revision"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"


# -- Module-level objects -----------------------------------------------------------------------

__all__ = [  
    # public API of module: one line per string
    'ParameterInputDialog',
    'PyExprValidator',
    'CallParamsValidator',
    'CallKwArgsValidator',
    'OK_DISABLED_TOOLTIP',
    'REQUIRED_ARG_ABSENT',
    'TOOLTIP_PARAMETERS',
    'CallArgs',
]

log = logging.getLogger('system')

OK_DISABLED_TOOLTIP = 'The argument "{}" has an invalid value or is empty.'
REQUIRED_ARG_ABSENT = "At least one of the required arguments does not have a value."

TOOLTIP_PARAMETERS = """
Parameters can be annotated such as "a: str, b: int" (no quotes of course)
"""

# Call arguments for a function(*args, **kwargs):
CallArgs = Tuple[Sequence[Any], Dict[str, Any]]
ParameterInputCB = Callable[[CallArgs], None]


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ParameterInputDialog(QDialog):
    """
    When running a script that needs parameters, we pop up this dialog to collect parameters and call the part
    with the collected parameters.
    """
    MAX_HEIGHT = 320
    VERTICAL_MARGIN = 3
    DIALOG_TEXT_MARGIN = 100

    def __init__(self, param_signature: signature, data_ready: ParameterInputCB):
        """
        Constructs a dialog to collect arguments in order to run an executable part.
        :param param_signature: The signature this part needs
        :param data_ready: The callback when the user clicks the OK button.
        """
        super().__init__()
        set_default_dialog_frame_flags(self)

        self.__data_ready = data_ready
        self.ui = Ui_InputParametersDialog()
        self.ui.setupUi(self)

        # Populate the dialog with a list of fields to enter values into
        total_height_needed = 0
        self.__params = param_signature.parameters
        required_values_present = list()
        for param_val in self.__params.values():
            # create the parameter field
            param_value_edit = QLineEdit(self.ui.scrollAreaWidgetContents)
            param_value_edit.setFont(get_scenario_font())

            # get parameter label
            annotation_label = param_val.name
            if param_val.annotation is not Parameter.empty:
                full_or_partial_anno = param_val.annotation
                annotation_label += ": {}".format(full_or_partial_anno.__name__)

            # add * or ** for args and kwargs
            if param_val.kind == Parameter.VAR_POSITIONAL:
                annotation_label = "*" + annotation_label
                validator = PyExprValidator(param_value_edit)
            elif param_val.kind == Parameter.VAR_KEYWORD:
                annotation_label = "**" + annotation_label
                validator = CallKwArgsValidator(param_value_edit)
            else:
                validator = PyExprValidator(param_value_edit, arg_required=param_val.default is Parameter.empty)
                required_values_present.append(param_val.default is not Parameter.empty)
                # Highlight the argument that is mandatory
                if param_val.default is Parameter.empty:
                    param_value_edit.setStyleSheet("QLineEdit {background: rgb(255, 0, 0);}")

            validator.sig_params_valid.connect(self.__slot_on_params_valid)
            validator.setObjectName(annotation_label)

            # add the field to the dialog
            self.ui.formLayout.addRow(
                QCoreApplication.translate("InputParametersDialog", annotation_label), param_value_edit)
            self.ui.formLayout.labelForField(param_value_edit).setFont(get_scenario_font())

            # set default value in field, if any
            if param_val.default is not Parameter.empty:
                default_val = repr(param_val.default)
                param_value_edit.setText(default_val)
                param_value_edit.setPlaceholderText(default_val)

            # increment the height value for each field added
            total_height_needed += param_value_edit.height() - ParameterInputDialog.VERTICAL_MARGIN

        # set the size of the dialog
        new_height = min(ParameterInputDialog.MAX_HEIGHT, total_height_needed + ParameterInputDialog.DIALOG_TEXT_MARGIN)
        self.resize(int(self.size().width()), int(new_height))

        # set the focus/cursor in the top parameter field
        index_of_first_qline_edit = 1
        first_line_edit_widget = self.ui.formLayout.itemAt(index_of_first_qline_edit).widget()
        first_line_edit_widget.setFocus()

        ok_button = self.ui.buttonBox.button(QDialogButtonBox.Ok)
        all_present = all(required_values_present)
        ok_button.setEnabled(all_present)
        tooltip = "" if all_present else REQUIRED_ARG_ABSENT
        ok_button.setToolTip(tooltip)

    @override(QDialog)
    def accept(self):
        """
        We want to control the show-and-hide of the dialog. But the Qt Designer generated code connects OK to accept()
        automatically. 
        """
        # 1. Check the mandatory input fields
        try:
            self.__get_call_args_dict()
        except ValueError as exc:
            exec_modal_dialog("Missing Data", str(exc), QMessageBox.Critical)
            return

        # 2. Check other validity of the input
        try:
            call_args_dict = self.__get_call_args_dict()
        except Exception as exc:
            exec_modal_input_error_dialog(exc)
            return

        self.__data_ready(call_args_dict)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_call_args_dict(self) -> Dict[int, CallArgs]:
        """
        Gets the argument values from the GUI.
        :raises ValueError: if mandatory input is missing
        :raises Exception: any exception raised by get_verified_eval(param)
        """
        param_list = list()
        param_kwargs = dict()
        var_args_used = False
        for idx, param_info in enumerate(self.__params.values()):
            form_layout = self.ui.formLayout
            user_input = form_layout.itemAt(idx, QFormLayout.FieldRole).widget().text()
            have_anything = user_input.strip()
            if param_info.kind == Parameter.VAR_POSITIONAL:
                var_args_used = True
                if not have_anything:
                    continue

                param_split = user_input.split(',')
                for param in param_split:
                    param_list.append(get_verified_eval(param))

            elif param_info.kind == Parameter.VAR_KEYWORD:
                if not have_anything:
                    continue

                param_value_list = user_input.split(',')
                for param_value in param_value_list:
                    param_name_value_pair = param_value.split("=")
                    if len(param_name_value_pair) == 2:
                        param_kwargs[param_name_value_pair[0].strip()] = get_verified_eval(param_name_value_pair[1])

            else:
                if not have_anything:
                    # Disabled OK on invalid input should have guaranteed existence of a default value here.
                    assert param_info.default is not Parameter.empty, ('The required argument "{}" '
                                                                       'does not have a value.'.format(param_info.name))
                    user_input = repr(param_info.default)

                if var_args_used:
                    var_name = form_layout.itemAt(idx, QFormLayout.LabelRole).widget().text()
                    param_kwargs[var_name] = get_verified_eval(user_input)
                else:
                    param_list.append(get_verified_eval(user_input))

        param_args = tuple(param_list)
        return param_args, param_kwargs

    def __check_each_arg_expr(self):
        """
        Checks the validity of all the fields. As soon as the first invalid field is detected, disables the OK button
        and sets a tooltip. If all of the fields are valid, enables the button and clears the tooltip.
        """
        ok_button = self.ui.buttonBox.button(QDialogButtonBox.Ok)
        for idx, param_info in enumerate(self.__params.values()):
            form_layout = self.ui.formLayout
            user_input = form_layout.itemAt(idx, QFormLayout.FieldRole).widget().text()
            have_anything = user_input.strip()
            if param_info.kind == Parameter.VAR_POSITIONAL:
                if not have_anything:
                    continue

                validator = PyExprValidator()

            elif param_info.kind == Parameter.VAR_KEYWORD:
                if not have_anything:
                    continue

                validator = CallKwArgsValidator()

            else:
                if not have_anything and param_info.default is not Parameter.empty:
                    continue

                validator = PyExprValidator(arg_required=param_info.default is Parameter.empty)

            val_acceptable, _, _ = validator.validate(have_anything, 0)
            if val_acceptable != QValidator.Acceptable:
                ok_button.setEnabled(False)
                ok_button.setToolTip(OK_DISABLED_TOOLTIP.format(param_info.name))
                return

        ok_button.setEnabled(True)
        ok_button.setToolTip('')

    def __on_params_valid(self, validator_name: str, valid: bool):
        """
        OK button is enabled only when all the arguments are valid.
        :param validator_name: The name previously set for the validator. It is usually the field name.
        :param valid: True - if one of them is valid
        """
        ok_button = self.ui.buttonBox.button(QDialogButtonBox.Ok)
        if valid:
            self.__check_each_arg_expr()
        else:
            ok_button.setEnabled(False)
            ok_button.setToolTip(OK_DISABLED_TOOLTIP.format(validator_name))

    __slot_on_params_valid = safe_slot(__on_params_valid)


class PyExprValidator(QValidator):
    """
    Validates the string in the given QLineEdit according to the syntax of the Python expressions. The
    validation happens while the text is changed. When it is invalid, the QLineEdit will be highlighted as yellow.
    
    The validation result is also emitted as a signal.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # True - the text in the QLineEdit is valid; otherwise, invalid
    sig_params_valid = pyqtSignal(str, bool)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, validation_target: QLineEdit = None, parent: QObject = None, arg_required: bool = False):
        super().__init__(parent)
        self.__validation_target = validation_target
        self._arg_required = arg_required
        if validation_target is not None:
            validation_target.textChanged.connect(self.__slot_on_text_changed)

            # It is not needed, but set just in case the Qt expects something.
            validation_target.setValidator(self)

    @override(QValidator)
    def validate(self, params_str: str, pos: int) -> QValidator.State:
        """
        Validates the string in the given QLineEdit according to the syntax of the Python function parameters.  
        """
        if not params_str:
            if self._arg_required:
                return QValidator.Intermediate, params_str, pos
            else:
                return QValidator.Acceptable, params_str, pos

        try:
            get_verified_eval(params_str)
        except:
            return QValidator.Intermediate, params_str, pos
        else:
            return QValidator.Acceptable, params_str, pos

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_text_changed(self):
        """
        Changes colors ane emits the sig_params_valid, based on the validation.
        This is called while the user is typing.
        """
        validity, _, _ = self.validate(self.__validation_target.text(), 0)
        colors = {QValidator.Invalid: 'red', QValidator.Intermediate: 'yellow'}
        if validity in colors:
            self.__validation_target.setStyleSheet('QLineEdit {{ background-color: {} }}'.format(colors[validity]))
            self.sig_params_valid.emit(self.objectName(), False)
        else:
            self.__validation_target.setStyleSheet(None)
            self.sig_params_valid.emit(self.objectName(), True)

    __slot_on_text_changed = safe_slot(__on_text_changed)


class CallParamsValidator(PyExprValidator):
    """
    Validates the string in the given QLineEdit according to the syntax of the Python function parameters. The
    validation happens while the text is changed. When it is invalid, the QLineEdit will be highlighted as yellow.
    
    The validation result is also emitted as a signal.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    @override(PyExprValidator)
    def validate(self, params_str: str, pos: int) -> QValidator.State:
        """
        Validates the string in the given QLineEdit according to the syntax of the Python function parameters.  
        """
        if not params_str:
            if self._arg_required:
                return QValidator.Intermediate, params_str, pos
            else:
                return QValidator.Acceptable, params_str, pos

        try:
            get_params_from_str(params_str)
        except:
            return QValidator.Intermediate, params_str, pos
        else:
            return QValidator.Acceptable, params_str, pos


class CallKwArgsValidator(PyExprValidator):
    """
    Validates the string in the given QLineEdit according to the syntax of the Python **kwargs. The
    validation happens while the text is changed. When it is invalid, the QLineEdit will be highlighted as yellow.
    
    The validation result is also emitted as a signal.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    @override(PyExprValidator)
    def validate(self, kwargs_str: str, pos: int) -> QValidator.State:
        """
        Validates the string in the given QLineEdit according to the syntax of the Python **kwargs.  
        """
        if not kwargs_str:
            return QValidator.Acceptable, kwargs_str, pos

        try:
            kwargs_value_list = kwargs_str.split(',')
            for kwargs_value in kwargs_value_list:
                kwargs_name_value_pair = kwargs_value.split("=")
                if len(kwargs_name_value_pair) == 2:
                    get_verified_eval(kwargs_name_value_pair[1])
                else:
                    return QValidator.Intermediate, kwargs_str, pos
        except:
            return QValidator.Intermediate, kwargs_str, pos
        else:
            return QValidator.Acceptable, kwargs_str, pos

