# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Function Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import inspect
import logging, re
from importlib import import_module
from textwrap import dedent

# [2. third-party]
from PyQt5.QtCore import Qt, QCoreApplication
from PyQt5.QtGui import QIcon, QGuiApplication
from PyQt5.QtWidgets import QWidget, qApp, QListWidgetItem, QAbstractItemView, QListWidget, QMessageBox
from PyQt5.QtWidgets import QTableWidgetItem, QSizePolicy

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ...core import override
from ...core.utils import validate_python_name

from ...scenario.defn_parts import LINK_PATTERN, get_patterns_by_link_item, get_link_find_replace_info, get_frame_repr
from ...scenario.defn_parts import BasePart
from ...scenario.part_execs import LINKS_SCRIPT_OBJ_NAME
from ...scenario.defn_parts import PartLink
from ...scenario.defn_parts import TypeLinkChainNameAndLink

from ..script_panel import CodingAssistant, PyCodingAssistant
from ..async_methods import AsyncRequest
from ..gui_utils import get_icon_path, get_scenario_font, try_disconnect, CustomListWidgetItemEnum
from ..gui_utils import exec_modal_dialog, TEXT_LINK_PRESENT_COLOR, UNUSED_LINK_HIGHLIGHTING_BRUSH, LIST_REGULAR_BRUSH
from ..gui_utils import TEXT_LINK_MISSING_COLOR, NEW_LINK_HIGHLIGHTING_BRUSH
from ..call_params import TOOLTIP_PARAMETERS, CallParamsValidator
from ..safe_slot import safe_slot

from .Ui_code_editor import Ui_CodeEditorWidget
from .scenario_part_editor import BaseContentEditor, log
from .import_object_dialog import ImportObjectDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [  # defines module members that are public; one line per string
    "PythonScriptEditor"
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def no_applicable_links_found(msg: str):
    """
    Logs an info message and pops up an info dialog if no applicable links are found for a given operation.
    For example, if the user wants to highlight a link in the script but that link is not referenced, this function
    will be called.
    :param msg: A detailed message describing why the links are not applicable
    """
    log.info(msg)
    exec_modal_dialog('Info - no applicable links', msg, QMessageBox.Information)


# -- Class Definitions --------------------------------------------------------------------------


class LinkListWidgetItem(QListWidgetItem):
    """
    Represents an item inside the link list in a script editor.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, link_id: int, text: str, is_direct_link: bool = True, parent: QListWidget = None):
        """
        Constructs a QListWidgetItem with one extra parameter - link_id.

        :param link_id: The SESSION_ID of a PartLink object
        :param text: Same as that in the QListWidgetItem
        :param is_direct_link: Direct (not linked to a hub) vs. link chain (linked to a hub). True - direct.
        :param parent: Same as that in the QListWidgetItem
        """
        QListWidgetItem.__init__(self, text, parent)
        self.__link_id = link_id
        self.__is_direct_link = is_direct_link

    def get_link_id(self):
        return self.__link_id

    def get_is_direct_link(self) -> bool:
        """
        Returns the flag set during the construction of the object.
        :return: True if this object is constructed as a link chain. For example, link.hub0.hub1.function
        """
        return self.__is_direct_link

    def type(self) -> int:
        return CustomListWidgetItemEnum.editor_link_item

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    link_id = property(get_link_id)
    is_direct_link = property(get_is_direct_link)


class ScriptEditor(BaseContentEditor):
    """
    This class is used to provide a common look and feel for several part editors that contain a script,
    such as Function Part Editor, Library Part Editor, Query Part Editor, etc. Derived classes can configure
    and extend for specific needs (Python scripts, SQL scripts, etc).
    """

    # --------------------------- class-wide data and signals -----------------------------------
    USE_MODULE_LIST = False
    USE_CALL_PARAMS = False
    USE_IMPORTS_TAB = False
    HUB_LINK_NAME_WARNING = 'Cannot change the name(s) linked from a hub. '
    INDICATOR_NUM_HIGHLIGHTING = 31
    SYMBOLS_COL_INDEX = 0
    OBJECT_COL_INDEX = 1

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: BasePart, parent: QWidget = None):
        """
        :param part: The part that the script interface is associated to.
        :param parent:  Parent widget for the script interface.
        """
        super().__init__(part, parent)
        self.ui = Ui_CodeEditorWidget()
        self.ui.setupUi(self)
        # Cannot set it invisible by default in the Qt Designer. So, we do it here.
        self.ui.role_group_box.setVisible(False)
        self.ui.docstring_display.setVisible(False)

        self.ui.paste_button.setText("")
        self.ui.copy_button.setText("")
        self.ui.cut_button.setText("")
        self.ui.undo_button.setText("")
        self.ui.redo_button.setText("")
        self.ui.del_button.setText("")

        self.ui.undo_button.clicked.connect(self.__slot_undo_clicked)
        self.ui.redo_button.clicked.connect(self.__slot_redo_clicked)
        self.ui.paste_button.setIcon(QIcon(str(get_icon_path("paste.png"))))
        self.ui.copy_button.setIcon(QIcon(str(get_icon_path("copy.png"))))
        self.ui.cut_button.setIcon(QIcon(str(get_icon_path("cut.png"))))
        self.ui.undo_button.setIcon(QIcon(str(get_icon_path("undo.png"))))
        self.ui.redo_button.setIcon(QIcon(str(get_icon_path("redo.png"))))
        self.ui.del_button.setIcon(QIcon(str(get_icon_path("delete.png"))))

        _translate = QCoreApplication.translate
        self.ui.paste_button.setToolTip(_translate("CodeEditorWidget", "Paste"))
        self.ui.copy_button.setToolTip(_translate("CodeEditorWidget", "Copy"))
        self.ui.cut_button.setToolTip(_translate("CodeEditorWidget", "Cut"))
        self.ui.undo_button.setToolTip(_translate("CodeEditorWidget", "Undo"))
        self.ui.redo_button.setToolTip(_translate("CodeEditorWidget", "Redo"))
        self.ui.del_button.setToolTip(_translate("CodeEditorWidget", "Delete"))

        tool_tip_text = "Double-click to insert in editor"
        self.ui.links_list.setToolTip(tool_tip_text)
        self.ui.links_list.itemDoubleClicked.connect(self.__slot_add_symbol_to_code)

        self.__code_assist = None
        self.ui.code_editor.sig_docstring_changed.connect(self.__slot_on_docstring_changed)

        self.ui.useful_keywords.setToolTip(tool_tip_text)
        self.ui.useful_keywords.itemDoubleClicked.connect(self.__slot_add_symbol_to_code)
        self.ui.useful_keywords.itemClicked.connect(self.__slot_symbol_selected)

        self.__done_params_editing = True
        self.ui.parameters_label.setVisible(self.USE_CALL_PARAMS)
        self.ui.part_params.setFont(get_scenario_font())
        self.ui.part_params.setVisible(self.USE_CALL_PARAMS)
        self.ui.part_params.setToolTip(TOOLTIP_PARAMETERS)
        self.__call_params_validator = CallParamsValidator(self.ui.part_params)
        self.__call_params_validator.sig_params_valid.connect(self.sig_data_valid)
        # WARNING: editingFinished is emitted twice when user presses ENTER: once for enter, once for loss of focus
        # BUT it is NOT EMITTED AT ALL if the validator does indicates unacceptable input
        self.ui.part_params.editingFinished.connect(self.__slot_on_part_params_done_editing)
        self.ui.part_params.textEdited.connect(self.__slot_on_part_params_text_edited)
        self.ui.code_editor.textChanged.connect(self.__slot_on_code_editor_text_changed)

        self.ui.modules_label.setVisible(self.USE_MODULE_LIST)
        self.ui.modules_list.setVisible(self.USE_MODULE_LIST)
        if self.USE_MODULE_LIST:
            self.ui.modules_list.setToolTip(tool_tip_text)
            self.ui.modules_list.itemDoubleClicked.connect(self.__slot_add_symbol_to_code)

        self.ui.paste_button.clicked.connect(self.__slot_paste)
        self.ui.cut_button.clicked.connect(self.__slot_cut)
        self.ui.copy_button.clicked.connect(self.__slot_copy)
        self.ui.del_button.clicked.connect(self.__slot_remove_selected_text)
        self.ui.code_editor.copyAvailable.connect(self._slot_enable_clipboard_buttons)
        # Make the main editing panel 3 times taller than the doc string display area
        self.ui.splitter.setSizes([3, 1])

        # Set Undo/Redo to False until the script changes
        self.ui.undo_button.setEnabled(False)
        self.ui.redo_button.setEnabled(False)
        self.ui.code_editor.textChanged.connect(self._slot_update_undo_redo_button_status)

        # Link management
        self.ui.code_editor.indicatorDefine(self.ui.code_editor.FullBoxIndicator, self.INDICATOR_NUM_HIGHLIGHTING)
        self.ui.code_editor.setIndicatorDrawUnder(True, self.INDICATOR_NUM_HIGHLIGHTING)
        self.ui.unhighlight_button.clicked.connect(self.__slot_on_unhighlight)
        self.ui.highlight_missing_button.clicked.connect(self.__slot_on_highlight_missing)
        self.ui.check_unused_button.clicked.connect(self.__slot_on_check_unused)
        self.ui.highlight_button.clicked.connect(self.__slot_on_highlight_link)
        self.ui.go_to_target_button.clicked.connect(self.__slot_on_go_to_target)
        self.ui.rename_button.clicked.connect(self.__slot_on_rename_link)
        self.ui.links_list.itemChanged.connect(self.__slot_on_item_changed)
        self.ui.links_list.itemSelectionChanged.connect(self.__slot_on_item_selection_changed)
        self.ui.links_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        part.part_frame.signals.sig_link_chain_changed.connect(self.__slot_on_link_chain_changed)

        # Used to track the differences between the links before addition and those after addition
        self.__links_list = list()
        self.__map_id_to_link = dict()

        # Modules
        if self.USE_MODULE_LIST:
            # This is not a class variable as this is only for Functions and not other part editors.
            modules = ["random", "math"]
            for module in sorted(modules, key=str.lower):
                self.ui.modules_list.addItem(module)

            for idx in range(len(modules)):
                self.ui.modules_list.item(idx).setFont(get_scenario_font())

        def get_link_info_from_backend() -> Tuple[List[PartLink], TypeLinkChainNameAndLink, bool]:
            link_info, link_chain_info = self._part.get_formatted_link_chains()
            is_initialization = True
            return link_info, link_chain_info, is_initialization

        AsyncRequest.call(get_link_info_from_backend, response_cb=self.__populate_link_list)

        if self.USE_IMPORTS_TAB:
            self.ui.symbol_table.itemDoubleClicked.connect(self.__slot_add_imported_symbol_to_code)
        else:
            self.ui.available_tabs.removeTab(2)

        self.code_editor.enable_breakpoint_marking(True)

        button_icon = QIcon()
        button_icon.addFile(str(get_icon_path("arrow_left.png")), state=QIcon.Off)
        button_icon.addFile(str(get_icon_path("arrow_right.png")), state=QIcon.On)

        self.ui.toggle_button.setCheckable(True)
        self.ui.toggle_button.setChecked(True)
        self.ui.toggle_button.setIcon(button_icon)
        self.ui.toggle_button.toggled.connect(self.__slot_handle_toggle)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.undo_button,
                     self.ui.redo_button,
                     self.ui.cut_button,
                     self.ui.copy_button,
                     self.ui.paste_button,
                     self.ui.del_button,
                     self.ui.code_editor,
                     self.ui.available_tabs]
        if self.USE_CALL_PARAMS:
            tab_order = [self.ui.part_params] + tab_order

        return tab_order

    def set_coding_assistant(self, code_helper: CodingAssistant):
        """
        Assign a coding assistant to this script panel. The assistant provides code completion, helpful
        keywords specific to a coding language, etc. It can be assigned as many times as required,
        for example if the script editor supports more than one language in the same script.
        """
        log.debug('Setting code assistant on ScriptEditor panel to {}', code_helper)
        if self.__code_assist is not None:
            self.__code_assist.set_useful_keywords_change_cb(None)
        self.__code_assist = code_helper
        self.ui.code_editor.set_coding_assistant(code_helper)

        if code_helper is None:
            self.ui.label_for_useful_keywords.clear()
            self.ui.useful_keywords.clear()
            self.ui.docstring_display.setVisible(False)

        else:
            self.__code_assist.set_useful_keywords_change_cb(self.__on_useful_keywords_changed)
            self.ui.label_for_useful_keywords.setText(code_helper.LABEL_USEFUL_WORDS)
            self.__on_useful_keywords_changed()

            if code_helper.CAN_COMPLETE:
                self.ui.docstring_display.clear()
                self.ui.docstring_display.setVisible(True)

    def get_code_assistant(self) -> CodingAssistant:
        """Get the coding assistant currently assigned to this script editor"""
        return self.__code_assist

    def get_code_editor(self):
        """
        Get the code editor.
        :return: A QsciScintilla code editor.
        """
        return self.ui.code_editor

    @override(BaseContentEditor)
    def disconnect_all_slots(self):
        try_disconnect(self._part.part_frame.signals.sig_link_chain_changed, self.__slot_on_link_chain_changed)
        try_disconnect(self.ui.code_editor.sig_docstring_changed, self.__slot_on_docstring_changed)
        try_disconnect(self.ui.undo_button.clicked, self.__slot_undo_clicked)
        try_disconnect(self.ui.redo_button.clicked, self.__slot_redo_clicked)
        try_disconnect(self.ui.links_list.itemDoubleClicked, self.__slot_add_symbol_to_code)
        try_disconnect(self.ui.useful_keywords.itemDoubleClicked, self.__slot_add_symbol_to_code)
        try_disconnect(self.__call_params_validator.sig_params_valid, self.sig_data_valid)
        try_disconnect(self.ui.part_params.editingFinished, self.__slot_on_part_params_done_editing)
        try_disconnect(self.ui.part_params.textEdited, self.__slot_on_part_params_text_edited)
        try_disconnect(self.ui.code_editor.textChanged, self.__slot_on_code_editor_text_changed)
        try_disconnect(self.ui.modules_list.itemDoubleClicked, self.__slot_add_symbol_to_code)
        try_disconnect(self.ui.symbol_table.itemDoubleClicked, self.__slot_add_imported_symbol_to_code)
        try_disconnect(self.ui.paste_button.clicked, self.__slot_paste)
        try_disconnect(self.ui.cut_button.clicked, self.__slot_cut)
        try_disconnect(self.ui.copy_button.clicked, self.__slot_copy)
        try_disconnect(self.ui.del_button.clicked, self.__slot_remove_selected_text)
        try_disconnect(self.ui.code_editor.copyAvailable, self._slot_enable_clipboard_buttons)
        try_disconnect(self.ui.code_editor.textChanged, self._slot_update_undo_redo_button_status)
        try_disconnect(self.ui.unhighlight_button.clicked, self.__slot_on_unhighlight)
        try_disconnect(self.ui.highlight_missing_button.clicked, self.__slot_on_highlight_missing)
        try_disconnect(self.ui.check_unused_button.clicked, self.__slot_on_check_unused)
        try_disconnect(self.ui.highlight_button.clicked, self.__slot_on_highlight_link)
        try_disconnect(self.ui.go_to_target_button.clicked, self.__slot_on_go_to_target)
        try_disconnect(self.ui.rename_button.clicked, self.__slot_on_rename_link)
        try_disconnect(self.ui.links_list.itemChanged, self.__slot_on_item_changed)
        try_disconnect(self.ui.links_list.itemSelectionChanged, self.__slot_on_item_selection_changed)

        self.__map_id_to_link.clear()

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    code_editor = property(get_code_editor)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    
    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        # no data needs submitting NOW but could change in future yet derived classes call this
        return dict()

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        super()._on_data_arrived(data)

        if 'parameters' in data.keys():
            self.__code_assist.on_part_params_edited(data['parameters'])
        if 'script' in data.keys():
            self.ui.code_editor.setText(data['script'])
        if 'sql_script' in data.keys():
            self.ui.code_editor.setText(data['sql_script'])

        self._update_undo_redo_button_status()  # Disable the Undo button

    def _enable_clipboard_buttons(self, enable: bool):
        """
        Method used to enable buttons depending on whether or not text is selected.
        :param enable: Parameter indicating whether or not the buttons within the script interface should be enabled.
        """
        self.ui.del_button.setEnabled(enable)
        self.ui.cut_button.setEnabled(enable)
        self.ui.copy_button.setEnabled(enable)
        mime_data = qApp.clipboard().mimeData()
        self.ui.paste_button.setEnabled(mime_data.hasText())

    def _update_undo_redo_button_status(self):
        """
        Enables or disables the Undo and Redo buttons depending on what's in the Scintilla undo stack.
        """
        if self.ui.code_editor.isUndoAvailable():
            self.ui.undo_button.setEnabled(True)
        else:
            self.ui.undo_button.setEnabled(False)

        if self.ui.code_editor.isRedoAvailable():
            self.ui.redo_button.setEnabled(True)
        else:
            self.ui.redo_button.setEnabled(False)

    _slot_enable_clipboard_buttons = safe_slot(_enable_clipboard_buttons)
    _slot_update_undo_redo_button_status = safe_slot(_update_undo_redo_button_status)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_useful_keywords_changed(self):
        useful_words = sorted(self.__code_assist.USEFUL_WORDS, key=str.lower)
        self.ui.useful_keywords.clear()
        for index, function in enumerate(useful_words):
            self.ui.useful_keywords.addItem(function)
            self.ui.useful_keywords.item(index).setFont(get_scenario_font())

    def __set_symbol_table_item(self, content: str, row: int, col: int):
        """
        Creates a table widget item from 'content' and sets it into the symbols table.
        :param content: A string specifying the content to display.
        :param row: The row index in the table.
        :param col: The column index in the table.
        """
        item = QTableWidgetItem(content)
        # item.setFlags(Qt.ItemIsEnabled)
        item.setFont(get_scenario_font())
        self.ui.symbol_table.setItem(row, col, item)

    def __on_docstring_changed(self, new_docstring: str):
        """Doc string has changed, update the display"""
        self.ui.docstring_display.setPlainText(new_docstring)

    def __undo_clicked(self):
        """
        Slot called when undo button is clicked.
        """
        self.parent().content_editor.ui.code_editor.undo()

    def __redo_clicked(self):
        """
        Slot called when redo button is clicked.
        """
        self.parent().content_editor.ui.code_editor.redo()

    def __add_symbol_to_code(self, item: QListWidgetItem):
        """
        Get text associated with the specified list 'item', format and insert it at the cursor position.
        :param item: The list item that was double-clicked.
        """
        text = item.data(Qt.DisplayRole)

        self.ui.code_editor.setFocus()
        line, index = self.ui.code_editor.getCursorPosition()

        if item.listWidget() is self.ui.useful_keywords:
            insert_text = text + self.__code_assist.get_useful_keyword_suffix_for_pasting(text)
            offset = 0

        elif item.listWidget() is self.ui.links_list:
            link_ref = text
            if QGuiApplication.keyboardModifiers() == Qt.ControlModifier:
                link_ref = get_frame_repr(text, sep=".")

            insert_text = "{0}.{1}".format(LINKS_SCRIPT_OBJ_NAME, link_ref)
            offset = 0

        elif item.listWidget() == self.ui.modules_list:
            insert_text = text + "."
            offset = 0

        if self.ui.code_editor.hasSelectedText():
            self.ui.code_editor.replaceSelectedText(insert_text)
        else:
            self.ui.code_editor.insertAt(insert_text, line, index)
            self.ui.code_editor.setCursorPosition(line, (index + len(insert_text) + offset))

    def __add_imported_symbol_to_code(self, item: QTableWidgetItem):
        """
        Get symbol text associated with the specified table 'item', format and insert it at the cursor position.
        :param item: The table item that was double-clicked.
        """
        # No matter which column is clicked, we are interested in only the first column (Symbol)
        row = item.row()
        symbol_item = self.ui.symbol_table.item(row, self.SYMBOLS_COL_INDEX)
        text = symbol_item.data(Qt.DisplayRole)
        self.__replace_or_insert_text(text)

    def __replace_or_insert_text(self, text: str):
        """
        Replaces or inserts the given text at the current cursor position. Replacement happens when there is a
        selected text.
        :param text: The text that goes into the script editor.
        """
        line, index = self.ui.code_editor.getCursorPosition()
        if self.ui.code_editor.hasSelectedText():
            self.ui.code_editor.replaceSelectedText(text)
        else:
            self.ui.code_editor.insertAt(text, line, index)
            self.ui.code_editor.setCursorPosition(line, (index + len(text)))

    def __symbol_selected(self, list_item: QListWidgetItem):
        if self.__code_assist is not None:
            text = list_item.data(Qt.DisplayRole)
            new_docstring = self.__code_assist.get_useful_keyword_docstring(text)
            if new_docstring:
                self.ui.docstring_display.setPlainText(dedent(new_docstring).strip())

    def __paste(self):
        """
        Forwards the call to QsciScintilla
        """
        self.ui.code_editor.paste()

    def __cut(self):
        """
        Forwards the call to QsciScintilla
        """
        self.ui.code_editor.cut()

    def __copy(self):
        """
        Forwards the call to QsciScintilla
        """
        self.ui.code_editor.copy()

    def __remove_selected_text(self):
        """
        Forwards the call to QsciScintilla
        """
        self.ui.code_editor.removeSelectedText()

    def __on_part_params_done_editing(self):
        """
        Parameters field has been edited, notify the code assistant in case it needs these for code completion etc.
        """
        # WARNING: when this is called as a slot, it can be called twice if user pressed ENTER (once
        # for pressing ENTER, and once for the loss of focus)
        if not self.__done_params_editing:
            self.__code_assist.on_part_params_edited(self.ui.part_params.text())
            self.__done_params_editing = True

    def __on_part_params_text_edited(self, _: str):
        """
        Called only when user makes an edit to the parameters field. Displays a "*" on the editor title bar.
        """
        self.__done_params_editing = False
        self.parent().set_dirty(bool(self.check_unapplied_changes()))

    def __on_link_chain_changed(self):
        self.__links_list.clear()
        for row in range(self.ui.links_list.count()):
            self.__links_list.append(self.ui.links_list.item(row).text())

        AsyncRequest.call(self._part.get_formatted_link_chains, response_cb=self.__populate_link_list)

    def __populate_link_list(self, part_links: List[PartLink],
                             chained_name_and_links: TypeLinkChainNameAndLink,
                             is_initialization: bool = False):
        """
        Convenience function used when the link list is initially populated and refreshed. When it is refreshed,
        newly added links are colored. When is_initialization is True, the newly added links are not highlighted in
        the list because all the links are new during initialization.

        :param part_links: Direct links (not linked to hubs)
        :param chained_name_and_links: Links that are linked to hubs
        :param is_initialization: Use True to indicate the links_list is to be initialized
        """
        item_list = []
        self.__map_id_to_link.clear()
        for link in part_links:
            displayed_name = link.name if link.temp_name is None else link.temp_name
            item_list.append(LinkListWidgetItem(link.SESSION_ID, displayed_name))
            self.__map_id_to_link[link.SESSION_ID] = link

        for chained_name, link in chained_name_and_links:
            link_list_widget_item = LinkListWidgetItem(link.SESSION_ID, chained_name, is_direct_link=False)
            self.__map_id_to_link[link.SESSION_ID] = link
            link_list_widget_item.setToolTip(self.HUB_LINK_NAME_WARNING + "Double-click to insert in editor.")
            item_list.append(link_list_widget_item)

        # The following code is trying to keep the actual links, which could be added or removed outside the editor,
        # in sync with the change detection mechanism, i.e., the self._initial_data
        self.ui.links_list.clear()
        for item in sorted(item_list, key=self.__link_sorter):
            if item.text() not in self.__links_list and not is_initialization:
                item.setForeground(NEW_LINK_HIGHLIGHTING_BRUSH)
                # new link added outside, so add a record to the self._initial_data
                self._initial_data['link_names'][item.link_id] = self.__map_id_to_link[item.link_id].name

            self.ui.links_list.addItem(item)

        self.ui.links_list.setFont(get_scenario_font())

        # Discard those that are found in self._initial_data but not in self.__map_id_to_link
        self._initial_data['link_names'] = {link_id: link_name
                                            for link_id, link_name in self._initial_data['link_names'].items()
                                            if link_id in self.__map_id_to_link}
        self.parent().set_dirty(bool(self.check_unapplied_changes()))

    def __link_sorter(self, link_item):
        """
        A smaller helper class to sort the link names in lower case
        :param link_item: See sorted() in Python
        :return: See sorted() in Python
        """
        return str.lower(link_item.text())

    def __on_code_editor_text_changed(self):
        """
        Displays a "*" on the editor title bar and flags the backend.
        """
        self.parent().set_dirty(bool(self.check_unapplied_changes()))

    def __on_rename_link(self):
        current_link_item = self.ui.links_list.currentItem()
        if current_link_item is None:
            return

        assert current_link_item.is_direct_link

        current_link_item.setFlags(current_link_item.flags() | Qt.ItemIsEditable)
        self.ui.links_list.editItem(current_link_item)

    def __on_item_changed(self, item: QListWidgetItem):
        """
        If the link name has been changed, send out a command; otherwise, do nothing.
        :param item: The item that is being edited in the link list
        """
        if not item.is_direct_link:
            # Chained names after a hub. Cannot change them.
            return

        part_link = self.__map_id_to_link[item.link_id]
        new_name = item.text()
        temp_name = part_link.temp_name
        old_name = part_link.name if temp_name is None else temp_name
        if old_name == new_name:
            return

        try:
            validate_python_name(new_name)
        except Exception as exc:
            msg_title = 'Python Name Error'
            error_msg = str(exc)
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Critical)
            item.setText(old_name)
            return

        if self._part.part_frame.is_link_temp_name_taken(new_name):
            msg_title = 'Link Name Error'
            error_msg = "The link name has already been taken. Please choose another name."
            exec_modal_dialog(msg_title, error_msg, QMessageBox.Warning)
            item.setText(old_name)
            return

        def __update_temp_real_map():
            self._part.update_temp_link_name(new_name, part_link)

        def __update_script():
            # Change the script
            fri = get_link_find_replace_info(old_name, new_name)
            new_script = self.ui.code_editor.text()
            for pattern, replacement in fri:
                new_script = re.sub(pattern, replacement, new_script)

            self.ui.code_editor.setText(new_script)
            # Maybe a QsciScintilla design issue. When new_script is '', it won't trigger the text change signal.
            # The unusual thing is that it will even if the new_script is same as the existing text.
            # So we have to do the set_dirty here
            if new_script == '':
                self.parent().set_dirty(bool(self.check_unapplied_changes()))

        AsyncRequest.call(__update_temp_real_map, response_cb=__update_script)

    def __highlighting(self, num_line: int, pattern: str, line_text: str) -> bool:
        """
        Highlights the matches in the line whose line number is specified in the num_line
        :param num_line: The line number of the line this function works on
        :param pattern: The regular expression to find matches in the line
        :param line_text: The text of the line
        :return True if at least one part of the line is highlighted
        """
        highlighted = False
        match_objects = re.finditer(pattern, line_text)
        for match_obj in match_objects:
            highlighted = True
            self.ui.code_editor.fillIndicatorRange(num_line, match_obj.start(),
                                                   num_line, match_obj.end(),
                                                   self.INDICATOR_NUM_HIGHLIGHTING)

        return highlighted

    def __on_highlight_link(self):
        """
        Prepares the link patterns for both parts and frames. Iterates the script line by line to highlight the text
        if there are matches.
        """
        self.__clear_highlighting()
        self.ui.code_editor.setIndicatorForegroundColor(TEXT_LINK_PRESENT_COLOR)
        current_item = self.ui.links_list.currentItem()
        text = current_item.text()
        partial_link_pattern = text.replace(".", r"\.")
        patterns = get_patterns_by_link_item(partial_link_pattern)

        highlighted = False
        for num_line in range(self.ui.code_editor.lines()):
            line_text = self.ui.code_editor.text(num_line)
            for pattern in patterns:
                ret = self.__highlighting(num_line, pattern, line_text)
                if ret:
                    highlighted = True

        if not highlighted:
            no_applicable_links_found('The link "{}" was not found in the script.'.format(text))

        self.ui.code_editor.selectAll(False)

    def __on_go_to_target(self):
        """
        Displays the target part of the currently selected link.
        """
        current_link_item = self.ui.links_list.currentItem()
        if current_link_item is None:
            return

        part_to_go = self.__map_id_to_link[current_link_item.link_id].target_part_frame.part
        self.parent().handle_go_to_part_action(part_to_go)

    def __on_item_selection_changed(self):
        """
        Enables the buttons above the link list. If the current item is a link chain, the "Rename" button is disabled.
        """
        self.ui.highlight_button.setEnabled(True)
        self.ui.go_to_target_button.setEnabled(True)
        self.ui.rename_button.setEnabled(self.ui.links_list.currentItem().is_direct_link)

    def __on_unhighlight_clicked(self):
        self.__clear_highlighting()

    def __clear_highlighting(self):
        """
        After this function is called, the highlighted texts will be displayed as normal ones, both in the script
        and in the link list
        """
        for line in range(self.ui.code_editor.lines()):
            self.ui.code_editor.clearIndicatorRange(line, 0,
                                                    line, self.ui.code_editor.lineLength(line),
                                                    self.INDICATOR_NUM_HIGHLIGHTING)

        for row in range(self.ui.links_list.count()):
            self.ui.links_list.item(row).setForeground(LIST_REGULAR_BRUSH)

    def __on_highlight_missing(self):
        """
        Highlights the link references that are found in the script but not in the link list
        """
        self.__clear_highlighting()
        self.ui.code_editor.setIndicatorForegroundColor(TEXT_LINK_MISSING_COLOR)

        all_links_available = True
        for num_line, line_text in enumerate(self.ui.code_editor.text().split('\n')):
            match_objects = re.finditer(LINK_PATTERN, line_text)
            for match_obj in match_objects:
                if self.ui.links_list.count() == 0:
                    all_links_available = False
                    self.ui.code_editor.fillIndicatorRange(num_line, match_obj.start(),
                                                           num_line, match_obj.end(),
                                                           self.INDICATOR_NUM_HIGHLIGHTING)
                    continue

                matched_line_text = line_text[match_obj.start():match_obj.end()]
                missing = True
                for row in range(self.ui.links_list.count()):
                    current_item = self.ui.links_list.item(row)
                    item_text = current_item.text()
                    partial_link_pattern = item_text.replace(".", r"\.")
                    patterns = get_patterns_by_link_item(partial_link_pattern)
                    for pattern in patterns:
                        item_match_obj = re.match(pattern, matched_line_text)
                        if item_match_obj is not None:
                            missing = False
                            break

                    if not missing:
                        break

                if missing:
                    all_links_available = False
                    self.ui.code_editor.fillIndicatorRange(num_line, match_obj.start(),
                                                           num_line, match_obj.end(),
                                                           self.INDICATOR_NUM_HIGHLIGHTING)

        if all_links_available:
            no_applicable_links_found("No missing links were found in the script.")

    def __on_check_unused(self):
        """
        Highlights the link references that are found in the link list but not in the script
        """
        all_used = True

        if self.ui.links_list.count() == 0:
            all_used = False

        for row in range(self.ui.links_list.count()):
            current_item = self.ui.links_list.item(row)
            text = current_item.text()
            partial_link_pattern = text.replace(".", r"\.")
            patterns = get_patterns_by_link_item(partial_link_pattern)

            match_object = None
            for pattern in patterns:
                match_object = re.search(pattern, self.ui.code_editor.text())
                if match_object is not None:
                    break

            if match_object is None:
                # Unused
                all_used = False
                current_item.setForeground(UNUSED_LINK_HIGHLIGHTING_BRUSH)
            else:
                # Used
                current_item.setForeground(LIST_REGULAR_BRUSH)

        if all_used:
            no_applicable_links_found("All the links are used in the script.")

    def __on_toggle_button_click(self, is_checked: bool):
        """
        Shows or hide the Tabs panel from the editor based on the 'checked' value
        :param is_checked: if the button is checked or not
        """
        self.ui.available_tabs.setVisible(is_checked)

    __slot_handle_toggle = safe_slot(__on_toggle_button_click)
    __slot_paste = safe_slot(__paste)
    __slot_cut = safe_slot(__cut)
    __slot_copy = safe_slot(__copy)
    __slot_remove_selected_text = safe_slot(__remove_selected_text)
    __slot_undo_clicked = safe_slot(__undo_clicked)
    __slot_redo_clicked = safe_slot(__redo_clicked)
    __slot_symbol_selected = safe_slot(__symbol_selected)
    __slot_add_symbol_to_code = safe_slot(__add_symbol_to_code)
    __slot_add_imported_symbol_to_code = safe_slot(__add_imported_symbol_to_code)
    __slot_on_part_params_done_editing = safe_slot(__on_part_params_done_editing, arg_types=())
    __slot_on_part_params_text_edited = safe_slot(__on_part_params_text_edited)
    __slot_on_code_editor_text_changed = safe_slot(__on_code_editor_text_changed)
    __slot_on_docstring_changed = safe_slot(__on_docstring_changed)
    __slot_on_link_chain_changed = safe_slot(__on_link_chain_changed)
    __slot_on_highlight_link = safe_slot(__on_highlight_link)
    __slot_on_go_to_target = safe_slot(__on_go_to_target)
    __slot_on_rename_link = safe_slot(__on_rename_link)
    __slot_on_item_changed = safe_slot(__on_item_changed)
    __slot_on_item_selection_changed = safe_slot(__on_item_selection_changed)
    __slot_on_unhighlight = safe_slot(__on_unhighlight_clicked)
    __slot_on_highlight_missing = safe_slot(__on_highlight_missing)
    __slot_on_check_unused = safe_slot(__on_check_unused)


class PythonScriptEditor(ScriptEditor):
    """
    Extends ScriptEditor for Python scripts: add breakpoint management and supports call parameters
    for the script (can be enabled/disabled as appropriate for the script). All part types that have
    Python scripts editable by user should derive from this class and configure/extend as appropriate.
    """

    USE_IMPORTS_TAB = True

    # For all classes that involve python code, the script must be set before the breakpoints in case some
    # breakpoints are at lines larger than the previous script. So redefine the submission order to be
    # base order plus this:
    _SUBMIT_ORDER = ScriptEditor._SUBMIT_ORDER + ['script', 'breakpoints']

    def __init__(self, part: BasePart, parent: QWidget = None):
        super().__init__(part, parent=parent)
        self.__init_import_tab()
        self.set_coding_assistant(PyCodingAssistant(part))

    @override(ScriptEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        super()._on_data_arrived(data)

        if 'imports' in data.keys():
            all_imports = data['imports']
            for sym_name, (module_name, obj_name) in all_imports.items():
                self.__symbol_name_list.append(sym_name)
                obj_str = '{}.{}'.format(module_name, obj_name) if obj_name else module_name
                self.__symbol_object_list.append(obj_str)

            self.__populate_symbol_list()

    @override(ScriptEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        data_dict = super()._get_data_for_submission()

        if self.USE_CALL_PARAMS:
            data_dict['parameters'] = self.ui.part_params.text()
        data_dict['script'] = self.ui.code_editor.text()
        data_dict['breakpoints'] = self.ui.code_editor.breakpoints

        # imports:
        all_imports = dict()
        for num, syn_str in enumerate(self.__symbol_name_list):
            module_str, dot, attr_str = self.__symbol_object_list[num].partition('.')
            all_imports[syn_str] = (module_str, attr_str or None)
        data_dict['imports'] = all_imports

        return data_dict

    def __init_import_tab(self):
        self.__new_symbol = None
        self.ui.symbol_table.setColumnWidth(self.SYMBOLS_COL_INDEX, 88)
        self.ui.symbol_table.setColumnWidth(self.OBJECT_COL_INDEX, 170)

        # hide the Hightlight and delete all undefined button and module doctring group box
        sp_retain = self.ui.highlight_symbol.sizePolicy();
        sp_retain.setRetainSizeWhenHidden(True);
        self.ui.highlight_symbol.setSizePolicy(sp_retain);
        self.ui.highlight_symbol.hide()
        sp_retain = self.ui.delete_all_undefined.sizePolicy();
        sp_retain.setRetainSizeWhenHidden(True);
        self.ui.delete_all_undefined.setSizePolicy(sp_retain);
        self.ui.delete_all_undefined.hide()
        self.ui.module_docstring_groupbox.hide()

        self.ui.delete_symbol.setEnabled(False)
        self.ui.symbol_table.itemClicked.connect(self.__slot_selection_changed)

        self.__selected_row = -1

        self.ui.add_symbol.pressed.connect(self.__slot_add_symbol)
        self.ui.delete_symbol.pressed.connect(self.__slot_delete_symbol)

        self.__symbol_name_list = []
        self.__symbol_object_list = []

    def __set_symbol_table_item(self, content: str, row: int, col: int):
        """
        Creates a table widget item from 'content' and sets it into the symbols table.
        :param content: A string specifying the content to display.
        :param row: The row index in the table.
        :param col: The column index in the table.
        """
        item = QTableWidgetItem(content)
        # item.setFlags(Qt.ItemIsEnabled)
        item.setFont(get_scenario_font())
        self.ui.symbol_table.setItem(row, col, item)

    def __populate_symbol_list(self):
        useful_words = []
        useful_objects = []
        useful_objects += self.__symbol_object_list
        useful_words += self.__symbol_name_list
        self.ui.symbol_table.setRowCount(len(useful_words))
        for row, symbols in enumerate(zip(useful_words, useful_objects)):
            sym, obj = symbols
            self.__set_symbol_table_item(sym, row, self.SYMBOLS_COL_INDEX)
            self.__set_symbol_table_item(obj, row, self.OBJECT_COL_INDEX)

    def __on_add_symbol(self):
        """
        Open the add symbol dialog.
        """
        import_object_dialog = ImportObjectDialog()
        answer = import_object_dialog.exec()
        if answer:
            self.__new_module, self.__use_attr, self.__attr_name, self.__new_symbol = (
                import_object_dialog.get_user_input())

            if self.__new_module:
                if self.__new_symbol:
                    sym_name = self.__new_symbol
                else:
                    if self.__use_attr:
                        sym_name = self.__attr_name
                    else:
                        sym_name = self.__new_module
                self.__symbol_name_list.append(sym_name)

                attr_name = ''
                if self.__use_attr:
                    attr_name = '.'+ self.__attr_name
                obj_name = str(self.__new_module + attr_name)
                self.__symbol_object_list.append(obj_name)

                self.__populate_symbol_list()

    def __on_delete_symbol(self):
        """
        delete the selected symbol entry.
        """
        del_row = self.ui.symbol_table.currentRow()
        self.ui.symbol_table.removeRow(del_row)
        self.__symbol_name_list.pop(del_row)
        self.__symbol_object_list.pop(del_row)
        self.ui.object_docstring_display.setText('')
        if self.ui.symbol_table.rowCount() == 0:
            self.ui.delete_symbol.setEnabled(False)

    def __on_selection_changed(self):
        """
        when row selection changed.
        """
        selected_row = self.ui.symbol_table.currentRow()
        if selected_row >= 0:
            self.ui.delete_symbol.setEnabled(True)
            obj_str = self.__symbol_object_list[selected_row]
            module_str, dot, attr_str = obj_str.rpartition('.')
            if module_str:
                obj = getattr(import_module(module_str), attr_str)
            else:
                obj = import_module(attr_str)
            docstring = inspect.getdoc(obj)
            self.ui.object_docstring_display.setText(docstring)
        else:
            self.ui.delete_symbol.setEnabled(False)

    __slot_add_symbol = safe_slot(__on_add_symbol)
    __slot_delete_symbol = safe_slot(__on_delete_symbol)
    __slot_selection_changed = safe_slot(__on_selection_changed)
