# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The modal dialog used to run Setup parts and its supporting business logic.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging, json
from inspect import signature, Parameter
from enum import IntEnum

# [2. third-party]
from PyQt5.QtWidgets import QDialog, QWidget, QTreeWidgetItem, QFileDialog, QMessageBox, QStyledItemDelegate, QLineEdit
from PyQt5.QtWidgets import QStyleOptionViewItem, QDialogButtonBox
from PyQt5.QtGui import QPixmap, QIcon, QBrush, QColor, QValidator
from PyQt5.Qt import Qt, QSettings
from PyQt5.QtCore import QModelIndex

# [3. local]
from ....core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ....core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream, AnnotationDeclarations

from ....core import override
from ....core.utils import get_verified_eval
from ...safe_slot import safe_slot
from ...gui_utils import set_default_dialog_frame_flags
from ...gui_utils import get_icon_path, get_scenario_font
from ...gui_utils import exec_modal_dialog, exec_modal_input_error_dialog
from ...call_params import PyExprValidator, CallKwArgsValidator, CallArgs, OK_DISABLED_TOOLTIP, REQUIRED_ARG_ABSENT
from .Ui_run_setup_parts import Ui_RunSetupPartsDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "Revision"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'RunSetupPartsDialog',
]

log = logging.getLogger('system')

# The Dict has the part id and CallArgs entries
RunSetupPartsDialogCB = Callable[[Dict[int, CallArgs]], None]

# Part id or path to argument dict mapping parameters to arguments:
ArgSpec = Dict[int or str, Dict[str, str]]

# A list of function part's id, path, and signature:
SignatureInfo = List[Tuple[int, str, signature]]

NUM_COLUMNS = 4
INDEX_COLUMN_PATH, INDEX_COLUMN_ARG_NAME, INDEX_COLUMN_VALUE, INDEX_COLUMN_RESULTS = range(NUM_COLUMNS)
USER_ROLE_DEFAULT_VAL = Qt.UserRole + 2
USER_ROLE_VALIDATOR_NAME = Qt.UserRole + 3
USER_ROLE_EDITOR_TYPE = Qt.UserRole + 4
USER_ROLE_ARG_REQUIRED = Qt.UserRole + 5


# -- Function definitions -----------------------------------------------------------------------
# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    RunSetupPartsDialog = 'RunSetupPartsDialog'


class EditorTypeEnum(IntEnum):
    py_expr = 0
    kwargs = 1


class ArgumentsDelegate(QStyledItemDelegate):
    """
    Qt out-of-the-box editor does not fit column width and it changes automatically its width even beyond the column
    width when the user types a lot of text. That seems undesirable.
    
    The purpose of this class is to replace the out-of-the-box editor with a standard QLineEdit. The editor is needed
    only for the column indexed as INDEX_COLUMN_VALUE.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, delegate_client: Decl.RunSetupPartsDialog):
        """
        Constructs a delegate for the client to create editors for its cell.
        
        Note: This is to satisfy the Qt contract. The actual editors are actually maintained in the delegate client.
        :param delegate_client: The client that gets the editors from this delegate
        """
        super().__init__(delegate_client)
        self.__delegate_client = delegate_client

    def createEditor(self, parent: QWidget, option: QStyleOptionViewItem, idx: QModelIndex):
        editor = super().createEditor(parent, option, idx)
        if idx.column() == INDEX_COLUMN_VALUE:
            editor = QLineEdit(editor.parent())
            top_level_item = self.__delegate_client.ui.arguments.topLevelItem(idx.parent().row())
            child_item = top_level_item.child(idx.row())
            arg_default = child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_DEFAULT_VAL)
            if arg_default is not None:
                editor.setPlaceholderText(arg_default)

            if child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_EDITOR_TYPE) == EditorTypeEnum.py_expr:
                validator = PyExprValidator(editor,
                                            arg_required=child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_ARG_REQUIRED))
                validator.sig_params_valid.connect(self.__delegate_client.slot_on_params_valid)
                validator.setObjectName(child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_VALIDATOR_NAME))
            else:
                assert child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_EDITOR_TYPE) == EditorTypeEnum.kwargs
                validator = CallKwArgsValidator(editor)
                validator.sig_params_valid.connect(self.__delegate_client.slot_on_params_valid)
                validator.setObjectName(child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_VALIDATOR_NAME))

        return editor


class RunSetupPartsDialog(QDialog):
    """
    The dialog used to run the Setup parts.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # Design decisions:
    #
    # During the initialisation of the dialog, if the total required height is between the min and max,
    # use the height. If it is smaller than the min, use the min. If it is larger than max, use the max.
    #
    #  After the initialisation, no restrictions except those imposed by the Qt.
    DIALOG_HEIGHT_MIN = 200  # pixels
    DIALOG_HEIGHT_MAX = 800  # pixels
    DIALOG_TOP_MARGIN = 80  # pixels, for the instructions, etc.
    DIALOG_BOTTOM_MARGIN = 50  # pixels, for the OK, Cancel buttons, etc.

    USER_ROLE_PART_ID = Qt.UserRole
    USER_ROLE_PARAMS = Qt.UserRole + 1

    MANDATORY_INPUT_BRUSH = QBrush(QColor(255, 0, 0))

    ARGUMENTS_FILE_LOCATION = "sim.main.run_setup_parts.RunSetupPartsDialog.ARGUMENTS_FILE_LOCATION"

    NOT_FOUND_WARNING_TEMPLATE = ('The part (path: {}, id: {}) expects "{}", '
                                  'but cannot find it. Have you changed either '
                                  'the Setup parts or the associated '
                                  'Part Call Arguments file?')

    REQUIRED_ARG_NO_VAL_TEMPLATE = 'The required argument "{}" of "{}" does not have a value.'

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------
    def __init__(self, data_ready: RunSetupPartsDialogCB, parent: QWidget = None):
        """
        Sets up the dialog and its fields without any data, which will be populated by initialize_gui() later.
        :param data_ready: The call-back function that is called after OK is clicked.
        :param parent: The Qt contract
        """
        super().__init__(parent)
        self.__data_ready = data_ready
        set_default_dialog_frame_flags(self)
        self.setWindowIcon(QIcon(QPixmap(str(get_icon_path("role_setup.svg")))))
        self.ui = Ui_RunSetupPartsDialog()
        self.ui.setupUi(self)
        self.ui.arguments.setHeaderLabels(['Path', 'Arg Name', 'Value', 'Results'])
        self.ui.arguments.header().setSectionsMovable(False)
        self.ui.arguments.itemClicked.connect(self.__slot_on_item_clicked)
        self.ui.arguments.itemSelectionChanged.connect(self.__slot_on_item_selection_changed)
        self.ui.arguments.setItemDelegateForColumn(INDEX_COLUMN_VALUE, ArgumentsDelegate(self))
        self.ui.load_button.clicked.connect(self.__slot_on_load_arguments)
        self.ui.save_button.clicked.connect(self.__slot_on_save_arguments)

        self.__errors_exist = False
        self.__signature_info = None

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

    def set_exec_errors(self, error_info: Dict[int, str]):
        """
        Sets the execution error information to this dialog and re-populates the dialog with the error info.
        :param error_info: The map of part id and the error messages.
        """
        self.__errors_exist = True
        self.__update_exec_results(error_info)

    def initialize_gui(self, signature_info: SignatureInfo):
        """
        Populates the path, parameters and arguments for each part.
        :param signature_info: The info of the part id, parameters, and signature.
        """
        self.__errors_exist = False
        self.__signature_info = signature_info
        self.ui.arguments.clear()
        required_values_present = list()
        for part_id, path, sig in signature_info:
            top_level_item = QTreeWidgetItem([path, '', '', 'Not run yet'])
            params = sig.parameters
            top_level_item.setData(INDEX_COLUMN_PATH, self.USER_ROLE_PART_ID, part_id)
            top_level_item.setData(INDEX_COLUMN_PATH, self.USER_ROLE_PARAMS, params)

            for param_val in params.values():
                annotation_label = param_val.name
                if param_val.annotation is not Parameter.empty:
                    full_or_partial_anno = param_val.annotation
                    annotation_label += ": {}".format(full_or_partial_anno.__name__)

                arg_param_item = QTreeWidgetItem(['', '', ''])

                if param_val.kind == Parameter.VAR_POSITIONAL:
                    annotation_label = "*" + annotation_label
                    arg_param_item.setData(INDEX_COLUMN_VALUE, USER_ROLE_EDITOR_TYPE, EditorTypeEnum.py_expr)
                    arg_param_item.setData(INDEX_COLUMN_VALUE, USER_ROLE_ARG_REQUIRED, False)
                elif param_val.kind == Parameter.VAR_KEYWORD:
                    annotation_label = "**" + annotation_label
                    arg_param_item.setData(INDEX_COLUMN_VALUE, USER_ROLE_EDITOR_TYPE, EditorTypeEnum.kwargs)
                else:
                    arg_param_item.setData(INDEX_COLUMN_VALUE, USER_ROLE_EDITOR_TYPE, EditorTypeEnum.py_expr)
                    arg_param_item.setData(INDEX_COLUMN_VALUE,
                                           USER_ROLE_ARG_REQUIRED,
                                           param_val.default is Parameter.empty)
                    required_values_present.append(param_val.default is not Parameter.empty)

                arg_param_item.setData(INDEX_COLUMN_VALUE, USER_ROLE_VALIDATOR_NAME, annotation_label)

                arg_param_item.setData(INDEX_COLUMN_ARG_NAME, self.USER_ROLE_PARAMS, annotation_label)
                # If this param has a default value, append it to the param label.
                if param_val.default is not Parameter.empty:
                    arg_default = repr(param_val.default)
                    arg_param_item.setData(INDEX_COLUMN_VALUE, USER_ROLE_DEFAULT_VAL, arg_default)
                    arg_param_item.setText(INDEX_COLUMN_VALUE, arg_default)

                arg_param_item.setText(INDEX_COLUMN_ARG_NAME, annotation_label)

                arg_param_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                for i in range(NUM_COLUMNS):
                    arg_param_item.setFont(i, get_scenario_font())

                    # Highlight the argument that is mandatory
                    if (i == INDEX_COLUMN_VALUE and
                                param_val.default is Parameter.empty and
                                param_val.kind not in [Parameter.VAR_POSITIONAL,
                                                       Parameter.VAR_KEYWORD]):
                        arg_param_item.setBackground(i, self.MANDATORY_INPUT_BRUSH)

                top_level_item.addChild(arg_param_item)

            top_level_item.setFont(0, get_scenario_font())
            self.ui.arguments.addTopLevelItem(top_level_item)

        self.__make_pretty_presentation(keep_dialog_intact=False)

        ok_button = self.ui.button_box_ok_cancel.button(QDialogButtonBox.Ok)
        all_present = all(required_values_present)
        ok_button.setEnabled(all_present)
        tooltip = "" if all_present else REQUIRED_ARG_ABSENT
        ok_button.setToolTip(tooltip)

    def on_params_valid(self, validator_name: str = None, valid: bool = True):
        """
        Disables the OK button if any one of the arguments is invalid or any one of the required arguments 
        does not have a value. 
        """
        ok_button = self.ui.button_box_ok_cancel.button(QDialogButtonBox.Ok)
        if valid:
            self.__check_each_mandatory_arg_expr(validator_name)
        else:
            ok_button.setEnabled(False)
            ok_button.setToolTip(OK_DISABLED_TOOLTIP.format(validator_name))

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_params_valid = safe_slot(on_params_valid)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __check_each_mandatory_arg_expr(self, validator_name: str = None):
        """
        Checks if all the required fields are filled in. If the current field that is being validated requires a value
        but it is blank and if the editor of the field has passed the validation, we consider that field has been 
        filled, even though the field is still blank until the editing is finished. The reason to do that is to make
        the user experiences more pleasant - when the user fills in a required blank field, he can now move the cursor
        over the OK button to click it.
        :param validator_name: The validator name used by the editor for the current field.
        """
        ok_button = self.ui.button_box_ok_cancel.button(QDialogButtonBox.Ok)
        for top_level_idx in range(self.ui.arguments.topLevelItemCount()):
            top_level_item = self.ui.arguments.topLevelItem(top_level_idx)
            params = top_level_item.data(INDEX_COLUMN_PATH, self.USER_ROLE_PARAMS)

            for idx, param_info in enumerate(params.values()):
                child_item = top_level_item.child(idx)
                user_input = child_item.text(INDEX_COLUMN_VALUE)
                have_anything = user_input.strip()
                if param_info.kind == Parameter.VAR_POSITIONAL:
                    if not have_anything:
                        continue

                elif param_info.kind == Parameter.VAR_KEYWORD:
                    if not have_anything:
                        continue

                else:
                    if not have_anything:
                        user_input = child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_DEFAULT_VAL)
                        invalid_field = child_item.data(INDEX_COLUMN_ARG_NAME, self.USER_ROLE_PARAMS)
                        if user_input is None:
                            if invalid_field == validator_name:
                                continue

                            part_path = top_level_item.text(INDEX_COLUMN_PATH)
                            ok_button.setEnabled(False)
                            ok_button.setToolTip(self.REQUIRED_ARG_NO_VAL_TEMPLATE.format(invalid_field, part_path))

                            return

        ok_button.setEnabled(True)
        ok_button.setToolTip('')

    def __get_call_args_dict(self) -> Dict[int, CallArgs]:
        """
        Gets the argument values from the GUI.
        :raises ValueError: if mandatory input is missing
        :raises Exception: any exception raised by get_verified_eval(param)
        """
        results = dict()
        for top_level_idx in range(self.ui.arguments.topLevelItemCount()):
            top_level_item = self.ui.arguments.topLevelItem(top_level_idx)
            params = top_level_item.data(INDEX_COLUMN_PATH, self.USER_ROLE_PARAMS)

            param_list = list()
            param_kwargs = dict()
            var_args_used = False
            for idx, param_info in enumerate(params.values()):
                child_item = top_level_item.child(idx)
                user_input = child_item.text(INDEX_COLUMN_VALUE)
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
                        user_input = child_item.data(INDEX_COLUMN_VALUE, USER_ROLE_DEFAULT_VAL)
                        if user_input is None:
                            # This exception is just an insurance. Disabled OK on invalid input should have
                            # prevented the execution from reaching this point.
                            raise ValueError(
                                self.REQUIRED_ARG_NO_VAL_TEMPLATE.format(
                                    child_item.text(INDEX_COLUMN_ARG_NAME),
                                    top_level_item.text(INDEX_COLUMN_PATH)))

                    if var_args_used:
                        var_name = child_item.data(INDEX_COLUMN_ARG_NAME, self.USER_ROLE_PARAMS)
                        param_kwargs[var_name] = get_verified_eval(user_input)
                    else:
                        param_list.append(get_verified_eval(user_input))

            param_args = tuple(param_list)
            results[top_level_item.data(INDEX_COLUMN_PATH, self.USER_ROLE_PART_ID)] = (param_args, param_kwargs)

        return results

    def __get_arguments_snapshot(self, by_part_id: bool = True) -> ArgSpec:
        """
        Scans the GUI components to harvest the user input in order to construct an ArgSpec. The key of the ArgSpec
        depends on the flag by_part_id.
        :param by_part_id: True - to use the part id as the key of the ArgSpec; otherwise the part path.
        :return: The ArgSpec based on the data from the user input
        """
        map_part_info_to_args = dict()
        for top_level_idx in range(self.ui.arguments.topLevelItemCount()):
            # This is each row that has the part path
            top_level_item = self.ui.arguments.topLevelItem(top_level_idx)
            if by_part_id:
                key = top_level_item.data(INDEX_COLUMN_PATH, self.USER_ROLE_PART_ID)
            else:
                key = top_level_item.text(INDEX_COLUMN_PATH)

            map_param_to_arg = dict()
            for idx in range(top_level_item.childCount()):
                # This is each row that has the parameter - argument pair
                child_item = top_level_item.child(idx)
                param = child_item.text(INDEX_COLUMN_ARG_NAME)
                arg = child_item.text(INDEX_COLUMN_VALUE)
                map_param_to_arg[param] = arg

            map_part_info_to_args[key] = map_param_to_arg

        return map_part_info_to_args

    def __update_gui(self, arguments: ArgSpec):
        """
        Populates the path, parameters and arguments for each part.
        :param arguments: The data used to populate the "Arguments" fields
        """
        # Check what kind of keys are in the arguments
        use_part_id = False
        for key in arguments:
            if type(key) == int:
                use_part_id = True

            break

        for idx, (part_id, path, sig) in enumerate(self.__signature_info):
            top_level_item = self.ui.arguments.topLevelItem(idx)
            params = sig.parameters

            for param_idx, param_val in enumerate(params.values()):
                child_item = top_level_item.child(param_idx)
                annotation_label = param_val.name
                if param_val.annotation is not Parameter.empty:
                    full_or_partial_anno = param_val.annotation
                    annotation_label += ": {}".format(full_or_partial_anno.__name__)

                if param_val.kind == Parameter.VAR_POSITIONAL:
                    annotation_label = "*" + annotation_label
                    validator = PyExprValidator()
                elif param_val.kind == Parameter.VAR_KEYWORD:
                    annotation_label = "**" + annotation_label
                    validator = CallKwArgsValidator()
                else:
                    validator = PyExprValidator(arg_required=child_item.data(INDEX_COLUMN_VALUE,
                                                                             USER_ROLE_ARG_REQUIRED))

                # Update only those fields that have values in the given arguments.
                args_key = part_id if use_part_id else path
                if args_key in arguments:
                    map_parameters_to_arguments = arguments.get(args_key)
                    if annotation_label in map_parameters_to_arguments:
                        val = map_parameters_to_arguments.get(annotation_label)
                        val_acceptable, _, _ = validator.validate(val, 0)
                        if val_acceptable == QValidator.Acceptable:
                            child_item.setText(INDEX_COLUMN_VALUE, val)
                        else:
                            log.warning("The loaded value {} for {} of {} is invalid; thus discarded.",
                                        val,
                                        annotation_label,
                                        args_key)
                    else:
                        log.warning(self.NOT_FOUND_WARNING_TEMPLATE.format(path, part_id, annotation_label))
                else:
                    log.warning(self.NOT_FOUND_WARNING_TEMPLATE.format(path, part_id, annotation_label))

        self.__make_pretty_presentation()
        self.__check_each_mandatory_arg_expr()

    def __update_exec_results(self, error_info: Dict[int, str]):
        """
        Populates the path, parameters and arguments for each part.
        :param error_info: The info of the part id and the execution error message of the part
        """
        for idx, (part_id, _, _) in enumerate(self.__signature_info):
            top_level_item = self.ui.arguments.topLevelItem(idx)

            # Populate errors if applicable
            if error_info is None:
                top_level_item.setText(INDEX_COLUMN_RESULTS, 'Not run yet')
            else:
                if part_id in error_info:
                    top_level_item.setText(INDEX_COLUMN_RESULTS, error_info[part_id])
                else:
                    top_level_item.setText(INDEX_COLUMN_RESULTS, 'OK')

        self.__make_pretty_presentation()

    def __make_pretty_presentation(self, keep_dialog_intact: bool = True):
        """
        Makes all tree item expand and sizes fit column contents.
        :param keep_dialog_intact: True - to resize the dialog properly, i.e., 300 < height < 600
        """
        self.ui.arguments.expandAll()

        for i in range(self.ui.arguments.columnCount()):
            self.ui.arguments.resizeColumnToContents(i)

        if keep_dialog_intact:
            return

        total_height = self.DIALOG_TOP_MARGIN + self.DIALOG_BOTTOM_MARGIN
        for i in range(self.ui.arguments.topLevelItemCount()):
            top = self.ui.arguments.topLevelItem(i)
            top.setTextAlignment(INDEX_COLUMN_PATH, Qt.AlignTop)
            total_height += self.ui.arguments.visualItemRect(top).height()
            for j in range(top.childCount()):
                child = top.child(j)
                total_height += self.ui.arguments.visualItemRect(child).height()

        if total_height <= self.DIALOG_HEIGHT_MIN:
            total_height = self.DIALOG_HEIGHT_MIN
        elif total_height >= self.DIALOG_HEIGHT_MAX:
            total_height = self.DIALOG_HEIGHT_MAX
        else:
            # No changes
            pass

        self.resize(int(self.width()), int(total_height))

    def __edit_item(self, item: QTreeWidgetItem, edit: bool):
        """
        Edits the item or makes it not editable but enabled and selectable
        :param edit: True - edit it; otherwise, make it not editable but enabled and selectable 
        """
        if edit:
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable)
            self.ui.arguments.editItem(item, INDEX_COLUMN_VALUE)
        else:
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    def __on_item_clicked(self, item: QTreeWidgetItem, col: int):
        """
        This function makes only the "Arguments" fields editable.
        """
        # Editable for the "Value" field, but not on the top level item, which represents the part path.
        self.__edit_item(item, col == INDEX_COLUMN_VALUE and item.parent() is not None)

    def __on_item_selection_changed(self):
        """
        Serves the similar purpose of __on_item_clicked. But this function intends to respond to the key navigation.
        """
        for item in self.ui.arguments.selectedItems():
            self.__edit_item(item, item.parent() is not None)

    def __on_load_arguments(self):
        """
        Pops up a file chooser to load a Part Call Arguments file. If the loading succeeds, the GUI
        components will be populated with the data from the file.

        If any errors occur in this operation, an error dialog will display the exception.
        """
        (file_path, ok) = QFileDialog.getOpenFileName(self, "Load Arguments",
                                                      QSettings().value(self.ARGUMENTS_FILE_LOCATION),
                                                      "Part Call Arguments files (*.pca)")
        assert file_path is not None
        if not file_path:
            return

        QSettings().setValue(self.ARGUMENTS_FILE_LOCATION, file_path)

        try:
            with open(file_path) as the_args_file:
                map_part_info_to_args = json.load(the_args_file)
                self.__update_gui(arguments=map_part_info_to_args)

        except Exception as exc:
            msg_title = 'Failed to Load Arguments'
            error_msg = str(exc) + '\nAn error occurred while loading the arguments.'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)

    def __on_save_arguments(self):
        """
        Pops up a file chooser to select a file where the arguments from the GUI components will be saved.

        If any errors occur in this operation, an error dialog will display the exception.
        """
        (file_path, ok) = QFileDialog.getSaveFileName(self, "Save Arguments",
                                                      QSettings().value(self.ARGUMENTS_FILE_LOCATION),
                                                      "Part Call Arguments files (*.pca)")

        assert file_path is not None

        if not file_path:
            return

        QSettings().setValue(self.ARGUMENTS_FILE_LOCATION, file_path)
        arguments_snapshot = self.__get_arguments_snapshot(by_part_id=False)

        try:
            with open(file_path, 'w') as the_args_file:
                json.dump(arguments_snapshot, the_args_file, indent=4)

        except Exception as exc:
            msg_title = 'Failed to Save Arguments'
            error_msg = str(exc) + '\nAn error occurred while saving the arguments.'
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            log.error('{}: {}', msg_title, error_msg)

    __slot_on_item_clicked = safe_slot(__on_item_clicked)
    __slot_on_item_selection_changed = safe_slot(__on_item_selection_changed)
    __slot_on_load_arguments = safe_slot(__on_load_arguments)
    __slot_on_save_arguments = safe_slot(__on_save_arguments)
