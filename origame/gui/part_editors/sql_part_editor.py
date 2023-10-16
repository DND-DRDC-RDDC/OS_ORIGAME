# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: SQL Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from textwrap import dedent

# [2. third-party]
from PyQt5.Qsci import QsciScintilla, QsciLexerSQL
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QWidget, QTableWidget, QTableWidgetItem, QMessageBox, QDialog
from PyQt5.Qt import Qt

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ...core import override
from ...scenario import ori
from ...scenario.defn_parts import SqlPart
from ...scenario.sqlite_dataset import SqlDataSet
from ...scenario.part_execs.scripting_utils import get_signature_from_str
from ...scenario.part_execs import get_params_from_str

from ..async_methods import AsyncRequest, AsyncErrorInfo
from ..script_panel import CodingAssistant, PyCodingAssistant, LangMonitor, TextBlock
from ..safe_slot import safe_slot
from ..gui_utils import exec_modal_dialog
from ..call_params import ParameterInputDialog, CallArgs
from ..slow_tasks import get_progress_bar

from .part_editors_registry import register_part_editor_class
from .script_editing import ScriptEditor
from .common import IPreviewWidget

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SqlPartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class SqlCodingAssistant(CodingAssistant):
    """Specialization for SQL coding."""

    CAN_COMPLETE = True
    LEXER_CLASS = QsciLexerSQL
    USEFUL_WORDS = ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'WHERE', 'FROM', 'ORDER BY', 'GROUP BY', 'NULL',
                    'CREATE', 'PRAGMA', 'JOIN', 'DROP', 'INDEX', 'LIMIT', 'OFFSET']
    AUTO_INDENT_STYLE = QsciScintilla.AiOpening

    @override(CodingAssistant)
    def on_part_params_edited(self, params_text: str = None):
        try:
            get_params_from_str(params_text)

        except SyntaxError:
            msg = dedent("""
                        Parameters string could not be parsed. Valid examples are (without quotes):

                        - "a, b, c": 3 parameters, each one has built-in type 'object'
                        - "a: int, b: [], c: bool=True": 3 parameters, 'a' has type int, 'b' list, and
                            'c' boolean that defaults to True
                        """)
            exec_modal_dialog("Parse Error", msg, QMessageBox.Critical)

    @override(CodingAssistant)
    def check_show_completions(self, keystroke: str, word_at_cursor: str) -> bool:
        assert keystroke.isprintable()
        if not (keystroke.isidentifier() or keystroke.isdecimal()):
            return False

        return word_at_cursor.isidentifier()

    @override(CodingAssistant)
    def get_docs(self, text: str, line: int, col: int, context_words: List[str]) -> str:
        if not context_words or not context_words[0].strip():
            return

        # for more detailed docs, see http://www.w3schools.com/sql/default.asp; if these pages are to be used
        # for docs, the following dict should be moved into a file and loaded at the same time as the module
        # is loaded
        docs = dict(SELECT='Get data from a table',
                    INSERT='Add a record to a table',
                    UPDATE='Update records that are in a table',
                    DELETE='Delete records from a table',
                    FROM='From which table or nested query to get data',
                    WHERE='Filter records that match condition',
                    ORDER='Order the data selected',
                    GROUP='Group the data selected',
                    NULL='nothing',
                    CREATE='Create a table',
                    PRAGMA='Command for the database engine',
                    JOIN='Join two tables',
                    DROP='Destroy a table or an index',
                    INDEX='Create an index for a table',
                    LIMIT='Limit',
                    OFFSET='Offset',
                    USING='Which foreign key to use to join two tables in SELECT FROM'
                    )

        doc_word = context_words[0]
        return '{}: {}'.format(doc_word, docs.get(doc_word))

    @override(CodingAssistant)
    def get_completions(self, text: str, line: int, col: int) -> List[str]:
        abs_pos = sum(len(line) for line in text.splitlines(True)[:line]) + col
        if abs_pos == 0:
            return []

        pos = abs_pos - 1
        while pos >= 0 and text[pos].isidentifier():
            pos -= 1
        pos += 1
        prefix = text[pos:abs_pos].lower()
        self.__prefix = prefix
        return [word for word in self.USEFUL_WORDS if word.lower().startswith(prefix)]

    @override(CodingAssistant)
    def get_completion(self, name: str) -> str:
        return name[len(self.__prefix):]

    @override(CodingAssistant)
    def get_completion_start(self, name: str) -> str:
        return name[:len(self.__prefix)]


class PyInSqlLangMonitor(LangMonitor):
    """Monitor language for SQL scripts that can embed Python code via {{...}} blocks"""

    @override(LangMonitor)
    def check_lang(self, text: str, abs_pos: int) -> TextBlock:
        # if we are inside a boundary marker, no language:
        if text[abs_pos - 1:abs_pos + 1] in ('{{', '}}'):
            self.sig_lang_changed.emit('between')
            return None

        # is there a start-Python-block marker somewhere to the left? if not, then we are in SQL:
        start_py = text.rfind('{{', 0, abs_pos)
        if start_py < 0:
            self.sig_lang_changed.emit('sql')
            return None

        # there is a start-Python-block; now is there a close-Python-block between start and cursor? if
        # not, then we are in Python:
        end_py = text.find('}}', start_py, abs_pos)
        if end_py < 0:
            end_py = text.find('}}', abs_pos)
            if end_py < 0:
                # there is no close-Python-block between cursor and end of string, so end_py must point to end:
                end_py = len(text)
            self.sig_lang_changed.emit('python')
            return TextBlock(start_py + 2, end_py)

        # the Python region was closed to our left so we are in SQL:
        self.sig_lang_changed.emit('sql')
        return None


class SqlPreviewWidget(IPreviewWidget):
    """
    Creates the preview panel for the SQL part editor.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: SqlPart):
        super().__init__()
        self.__part = part
        self.__table = None
        self.params = None  # params in the editor (not necessarily the backend)
        self.script = None  # script in the editor (not necessarily the backend)
        self.__param_dialog = None
        self.init_preview_table()

    @override(IPreviewWidget)
    def update(self):
        """
        Update the table based on the data received from the backend.
        """
        assert self.params is not None
        assert self.script is not None

        # -------------------------------------
        def on_preview_ready(data: SqlDataSet):
            """
            Preview the data retrieved using the SQL statement in the preview table.
            :param data: The data to preview.
            """
            get_progress_bar().stop_progress()
            if self.__param_dialog is not None:
                # Unlike the function part, it does not pop up a completion message because the preview will confirm
                # the result of the execution.
                self.__param_dialog.done(QDialog.Accepted)

            self.init_preview_table()

            if not data:
                msg = "The SQL statement did not return any data."
                exec_modal_dialog("No Data", msg, QMessageBox.Information)
                return

            records = data.get_records()
            num_rows = len(records)
            num_cols = data.get_num_columns()
            self.__table.setRowCount(num_rows)
            self.__table.setColumnCount(num_cols)

            for row, rec in enumerate(records):
                for col in range(num_cols):
                    item = QTableWidgetItem(str(rec[col]))
                    item.setFlags(Qt.ItemIsEnabled)
                    self.__table.setItem(row, col, item)

            self.__table.setHorizontalHeaderLabels(data.get_column_names())

        # -----------------------------------------------
        def on_preview_error(error_info: AsyncErrorInfo):
            get_progress_bar().stop_progress()
            self.init_preview_table()
            self.show_error_message(error_info.msg)

        try:
            inspected_signature = get_signature_from_str(self.params)
        except Exception as exc:
            # catch all errors from 'inspect.signature'...probably SyntaxError mostly
            self.show_error_message(str(exc))
            return

        prog_msg = 'Running {} to fetch records'.format(str(self.__part))

        def on_input_ready(call_args_dict: CallArgs):
            """
            This is a call-back function for the ParameterInputDialog.
            
            After the user clicks OK button, this function sends the collected information from the dialog to
            the backend to run the part. 
    
            If the execution has errors, the ParameterInputDialog will stay open until the user cancels it or re-runs
            succeed eventually.
            :param call_args_dict: The user input on the dialog
            """
            run_args, run_kwargs = call_args_dict
            get_progress_bar().start_busy_progress(prog_msg)
            AsyncRequest.call(self.__part.get_preview_data, self.params, self.script, *run_args, **run_kwargs,
                              response_cb=on_preview_ready, error_cb=on_preview_error)

        if len(inspected_signature.parameters) == 0:
            empty_args, empty_kwargs = [], {}
            get_progress_bar().start_busy_progress(prog_msg)
            AsyncRequest.call(self.__part.get_preview_data, self.params, self.script, *empty_args, **empty_kwargs,
                              response_cb=on_preview_ready, error_cb=on_preview_error)
        else:
            # request argument values
            self.__param_dialog = ParameterInputDialog(param_signature=inspected_signature,
                                                       data_ready=on_input_ready)
            self.__param_dialog.exec()

    def init_preview_table(self):
        """
        Replace old table (if any) and install a new one.
        """
        self.remove_display_widget()
        self.__table = QTableWidget(self)
        self.add_display_widget(self.__table)

    def show_error_message(self, msg: str):
        """
        Display the error message in a dialog.
        :param msg: The message to show.
        """
        log.error(msg)
        exec_modal_dialog("SQL Preview Error", msg, QMessageBox.Critical)

    def get_preview_table(self) -> QTableWidget:
        """Get the table widget."""
        return self.__table

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    preview_table = property(get_preview_table)


class SqlPartEditorPanel(ScriptEditor):
    """
    Sql Part Editor class. Like the Function Part Editor, it contains the edit buttons like Cut, Copy, etc., a
    ScriptPanel panel and a "Parameters" field. But the Sql Part Editor does not allow breakpoints and it
    does not have the "Modules" section in the "Info" tab.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    USE_CALL_PARAMS = True

    # The initial size to make this editor look nice.
    INIT_WIDTH = 1068
    INIT_HEIGHT = 640

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: SqlPart, parent: QWidget = None):
        super().__init__(part, parent=parent)

        self.__lang = 'sql'
        self.set_coding_assistant(SqlCodingAssistant())
        lang_monitor = PyInSqlLangMonitor()
        lang_monitor.sig_lang_changed.connect(self.__slot_on_lang_changed)
        self.code_editor.set_lang_monitor(lang_monitor)

        # Add the preview panel
        self.sql_preview_panel = SqlPreviewWidget(part)
        self.sql_preview_panel.ui.update_button.clicked.connect(self.__slot_on_update_button_clicked)
        self.ui.main_code_editor_layout.layout().addWidget(self.sql_preview_panel)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(ScriptEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        data_dict = dict()
        data_dict['parameters'] = self.ui.part_params.text()
        data_dict['sql_script'] = self.ui.code_editor.text()

        return data_dict

    @override(ScriptEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        super()._on_data_arrived(data)
        parameters = data['parameters']
        self.ui.part_params.setText(parameters)
        self.sql_preview_panel.init_preview_table()

    # --------------------------- instance __PRIVATE members-------------------------------------

    @pyqtSlot(str)
    def __on_lang_changed(self, new_lang_key: str):
        if new_lang_key == self.__lang:
            return

        log.info("Changing code assistant to {}", new_lang_key)
        self.__lang = new_lang_key
        if new_lang_key == 'python':
            pca = PyCodingAssistant(self._part)
            pca.on_part_params_edited(self._part.parameters)
            self.set_coding_assistant(pca)

        elif new_lang_key == 'sql':
            self.set_coding_assistant(SqlCodingAssistant())

        else:
            self.set_coding_assistant(None)

    def __on_update_button_clicked(self):
        """
        Method called with the update button is clicked within the SQL Part Editor.
        """
        self.sql_preview_panel.script = self.ui.code_editor.text()
        self.sql_preview_panel.params = self.ui.part_params.text()
        self.sql_preview_panel.update()

    __slot_on_lang_changed = safe_slot(__on_lang_changed)
    __slot_on_update_button_clicked = safe_slot(__on_update_button_clicked)


register_part_editor_class(ori.OriSqlPartKeys.PART_TYPE_SQL, SqlPartEditorPanel)
