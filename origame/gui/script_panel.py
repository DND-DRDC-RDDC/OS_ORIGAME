# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Common components related to presenting a script to the user

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import inspect
import logging
import pydoc
import re
import traceback
from textwrap import dedent, indent
from importlib import import_module

# [2. third-party]
import jedi
from jedi.api.classes import Name as JediName

from PyQt5.Qsci import QsciLexer, QsciLexerPython, QsciScintilla
from PyQt5.QtCore import QObject, Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont, QFontMetrics, QColor, QKeySequence, QKeyEvent, QMouseEvent
from PyQt5.QtWidgets import QWidget, QShortcut, QMessageBox

# [3. local]
from ..core import override, override_optional
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..scenario.defn_parts import BasePart
from ..scenario.part_execs import get_params_from_str, check_link_name_is_frame

from .actions_utils import create_action
from .gui_utils import get_scenario_font, exec_modal_dialog
from .safe_slot import safe_slot
from .async_methods import AsyncRequest

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ScriptPanel',
    'CodingAssistant',
    'TextBlock',
    'LangMonitor',
    'PyCodingAssistant'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def get_jedi_docstring(jediName: JediName) -> str:
    """
    Returns a string that represents the docstring of a Python object as determined by Jedi.
    :param defn: the Jedi Definition object that represents a Python object
    """
    if jediName.type == 'module':
        # jedi only provides object docstring, whereas really we want members similar to help(object)
        try:
            module = import_module(jediName.name)
            return get_docstring(module)

        except (ImportError, ValueError):
            # return default docstring, which won't have as much but no choice because jedi definition could
            # not be resolved to an actual module (this is the case of random module, which jedi says is random.p)
            pass

    return '{} {}:\n{}'.format(jediName.type, jediName.name, jediName.docstring(raw=True))


def get_docstring(obj: Any) -> str:
    """
    Try to get the docstring of an object by editor and interpreter context.
    :param obj: Any from which to get documentation
    :return: doc string, or None
    """

    class PlainTextDoc(pydoc.TextDoc):
        def bold(self, text):
            return text

    # if object is instance, make it a class:
    if inspect.isclass(obj) or inspect.isroutine(obj) or inspect.isfunction(obj):
        name = getattr(obj, '__name__', None)
        docstring = PlainTextDoc().document(obj, name)

    else:
        # obj is either a module, an instance of a class, or a more esoteric object like a generator, etc.
        # if instance of BasePart, it must be treated specially since only want scripting API, and some parts
        # define attributes dynamically (like Library)
        obj_class = obj.__class__
        name = getattr(obj_class, '__name__', None)
        docstring = PlainTextDoc().document(obj, name)
        if isinstance(obj, BasePart):
            # NOTE: dir() must be on obj not on obj_class, because only want scripting API;
            members = {}
            for member_name in dir(obj):
                # some attributes may not be defined on class so provide default so don't get exception;
                # need to get on class in case it is a property, we want the descriptor not the value:
                attr_val = getattr(obj_class, member_name, None)
                if attr_val is None:
                    # the attribute might be a runtime one like a symbol defined by a LibraryPart script:
                    attr_val = getattr(obj, member_name)

                members[member_name] = attr_val

        else:
            # it is a non-part instance, or a module, etc
            if obj_class == 'class':
                members = dict(inspect.getmembers(obj_class))
            else:
                # for every other type of obj, we don't want the dunder methods
                all_members = inspect.getmembers(obj_class)

                def is_special(member_name: str):
                    return member_name.startswith('__') and member_name.endswith('__')

                members = {name: member for name, member in all_members if not is_special(name)}

        if members:
            docstring += '\n\nMembers:\n\n'
            indent_desc = ' ' * 4  # description of each member will be indented by spaces

            def format_member(member_name):
                # inspect.getdoc() can return None
                member_doc = indent(inspect.getdoc(members[member_name]) or '<no docs>', indent_desc)
                return '{}:\n{}'.format(member_name, member_doc)

            docstring += '\n\n'.join(format_member(member_name) for member_name in sorted(members))

    # cleanup messy info provided by inspect module:
    docstring = re.sub(r"<class '(\w+)'>", r'\1', docstring)
    docstring = re.sub(r"origame\.(\w+\.)*(?P<name>\w+)", r'\g<name>', docstring, flags=re.IGNORECASE)
    docstring = re.sub(r' method of (.*)', ':\n    (Method of \\1)\n', docstring)

    return docstring


# -- Class Definitions --------------------------------------------------------------------------

class CodingAssistant:
    # override this to True if the assistant can provide code completion
    CAN_COMPLETE = False

    # Override this to identify which class derived from QSciLexer should be used for syntax highlighting
    LEXER_CLASS = None

    # Override this to one of QsciScintilla.Ai* constants
    AUTO_INDENT_STYLE = None

    # Label for the group of useful symbols and keywords (USEFUL_WORDS)
    LABEL_USEFUL_WORDS = "Useful Symbols"
    # Override this to be a list of useful words for the language
    USEFUL_WORDS = []

    def __init__(self):
        self.__useful_keywords_change_cb = None

    @override_optional
    def on_part_params_edited(self, params_text: str = None):
        """
        This gets called automatically if the script editor has a parameters field, whenever the field is edited.
        Override this, for example, so that code completion can cover call parameters to a scenario part.
        :param params_text: the text string representing the signature of a Python function's parameters

        Example: 'a: int, b: str, c: [str]' for a function that would have 3 parameters, with given annotated types
        """
        pass

    @override_optional
    def check_show_completions(self, keystroke: str) -> bool:
        """
        This gets called automatically whenever the user has pressed a key.
        Override to return True when the given keystroke should cause code completions to become visible.
        :param keystroke: the key the user pressed in the editor
        """
        return False

    @override_optional
    def get_docs(self, text: str, line: int, col: int, context_words: List[str]) -> str:
        """
        This gets called automatically whenever the cursor has moved or the text has changed.
        Override this to provide documentation for the "object" at cursor (line, col) in text.
        :param text: text of editor
        :param line: line # (starting at 0)
        :param col: column # (starting at 0)
        :param context_words: if given, the list can be used as an aid to determine the language "context", i.e.
            the language object under the cursor, so that its docs can be returned. Example: if text is
            "a123.b456.c789" and cursor is before the first dot, the context words will be ["a123"]; between
            the first and second dots, it will be ["a123", "b456"], and after the second dot, it will
            be ["a123", "b456", "c789"].
        :return: documentation string
        """
        return None

    @override_optional
    def get_useful_keyword_docstring(self, obj_name: str) -> Optional[str]:
        """Get the docstring for one of the keywords in self.USEFUL_KEYWORDS"""
        return None

    @override_optional
    def get_useful_keyword_suffix_for_pasting(self, obj_name: str) -> str:
        """Get the suffix to insert for the given useful keyword (present in self.USEFUL_KEYWORDS)"""
        return ''

    @override_optional
    def get_completions(self, text: str, line: int, col: int) -> List[str]:
        """
        This gets called automatically when check_show_completions() returned True.
        Override to provide list of completions strings to user.
        :param text: text of editor
        :param line: line # (starting at 0)
        :param col: column # (starting at 0)
        :return: list of (complete) names to present to user (i.e. not just the missing piece)
        """
        return []

    @override_optional
    def get_completion(self, name: str) -> str:
        """
        This gets called automatically when user has chosen a completion to insert in the editor.
        Override this to provide the completion needed.
        :param name: one of the items in the list returned by get_completions()
        :return: the corresponding completion (missing portion)

        Example: if get_completions() returned ["abc123", "abc456"] and user selected the first item, then
        name will be "abc123" and this function would return "123" (if the cursor is after the "c").
        """
        return None

    @override_optional
    def get_completion_start(self, name: str) -> str:
        """
        This gets called automatically when user has chosen a completion to insert in the editor.
        Override this to provide the completion *prefix* needed.
        :param name: one of the items in the list returned by get_completions()
        :return: the corresponding completion prefix, i.e. the piece that user typed

        Example: if get_completions() returned ["abc123", "abc456"] and user selected the first item, then
        name will be "abc123" and this function would return "abc" (if the cursor is after the "c").
        """
        return None

    def set_useful_keywords_change_cb(self, cb: Callable):
        """Set a callback for when the list of useful keywords of this instance has changed"""
        self.__useful_keywords_change_cb = cb

    def _on_useful_keywords_changed(self):
        """Derived class must call this when its list of useful keywords changes"""
        if self.__useful_keywords_change_cb is not None:
            self.__useful_keywords_change_cb()


"""Callable that converts a position to a line index + column number pair"""
ConvertPosToLineColCallable = Callable[[int], Tuple[int, int]]


class TextBlock:
    """Represents a portion of text"""

    def __init__(self, start_pos: int, end_pos: int):
        """
        :param start_pos: absolute position (from 0) of start of block
        :param end_pos: absolute position (from 0) of end of block
        """
        self.__start_pos = start_pos
        self.__end_pos = end_pos

    def extract(self, text: str, cursor_line: int, cursor_col: int,
                get_line_col_from_pos: ConvertPosToLineColCallable) -> Tuple[str, int, int]:
        """
        Convert a text and cursor position to a new text with equivalent cursor position
        :param text: text to get portion of
        :param cursor_line: line number of cursor in text (starts at 0)
        :param cursor_col: column of cursor in text (starts at 0)
        :param get_line_col_from_pos: callable to convert absolute positions (given at construction) to line, col
        :return: the new text, line and col #
        """
        start_line, start_col = get_line_col_from_pos(self.__start_pos)
        cursor_line -= start_line
        if cursor_line == 0:  # for first cursor_line, column needs adjusting
            cursor_col -= start_col
        assert cursor_line >= 0 and cursor_col >= 0

        text = text[self.__start_pos: self.__end_pos]
        return text, cursor_line, cursor_col


class LangMonitor(QObject):
    sig_lang_changed = pyqtSignal(str)  # language

    @override_optional
    def check_lang(self, text: str, abs_pos: int) -> TextBlock:
        """
        Called automatically when editor needs to determine which language block the cursor is in.
        :param text: the editor text
        :param abs_pos: the absolute position of cursor in text, with 0 being to the left of first character,
            and N being to the right of the Nth character.
        :return: a TextBlock representing the block of text; the language used in that block is not
            the responsiblity of this method

        Derived class can override this for an editor that supports several languages simultaneously
        in the edited text, such as SQL with blocks of Python code.
        """
        return None


class ScriptPanel(QsciScintilla):
    """
    A QsciScintilla widget configured for editing scripts in Origame: smart indentation, auto completion,
    syntax coloring, folding, brace matching. Note that by default, the first 3 are off: the derived class
    must enable them by calling the associated methods.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    sig_docstring_changed = pyqtSignal(str)
    sig_breakpoint_toggled = pyqtSignal()

    # Wait for 267 milliseconds before triggering the doc string
    DOC_STRING_TIMEOUT = 267

    DEBUGGER_TO_EDITOR_LINE_OFFSET = 1
    MARKER_BREAKPOINT = 1
    MARKER_BREAKPOINT_BACKGROUND = 2
    MARKER_STOPPED_AT = 3
    AUTO_COMPLETIONS_LIST_ID = 1

    MARGIN_COLOR = QColor("#cccccc")
    DEFAULT_LINE_COLOR = QColor("#fff5e3")
    BREAKPOINT_MARKER_COLOR = QColor("#ee1111")
    BREAKPOINT_BACKGROUND_COLOR = QColor("#ffe4e4")
    BREAKPOINT_STEP_COLOR = QColor("#a6a9ff")

    # The line numbers of the script source code are displayed at the left margin of the panel. We assume the lines
    # are fewer than MAX_LINE_NUMBER_DIGITS. If they are more than that, the source code itself will be fine but
    # the most significant digits of the line numbers will be hidden.
    MAX_LINE_NUMBER_DIGITS = 6

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QWidget = None):
        """
        :param parent: parent widget
        """
        super().__init__(parent)

        self.setObjectName("ScriptPanel")

        self.__from_default_mono = QFont(get_scenario_font(mono=True))
        self.setFont(self.__from_default_mono)

        # Code folding:
        self.setFolding(QsciScintilla.BoxedFoldStyle)

        # Margin for line numbers and markers:
        self.setMarginLineNumbers(0, True)
        self.setMarginSensitivity(1, True)
        self.setMarginsFont(self.__from_default_mono)
        self.setMarginWidth(0, QFontMetrics(self.__from_default_mono).width("0" * self.MAX_LINE_NUMBER_DIGITS))
        self.setMarginsBackgroundColor(self.MARGIN_COLOR)

        # Auto-indentation:
        self.setAutoIndent(True)
        self.setTabWidth(4)
        self.setIndentationWidth(4)
        self.setTabIndents(True)
        self.setIndentationsUseTabs(False)
        self.setIndentationGuides(True)

        # margin markers (breakpoints):
        self.__enable_breakpoint_marking = False

        # Auto-completion:
        self.__code_helper = None
        self.__lang_monitor = None
        self.__last_update_docstring = None
        self.__setup_code_completion()

        # cursor:
        self.setCaretLineVisible(True)
        self.setCaretLineBackgroundColor(self.DEFAULT_LINE_COLOR)

        # Debug
        self.__current_debug_line = None
        self.__is_debug_mode = False

        # Scrolling
        self.__scroll_bar = None
        self.__scroll_value = None

        # Local actions (shortcuts that only work when the ScriptPanel has focus)
        self.setBraceMatching(QsciScintilla.StrictBraceMatch)
        self.setMatchedBraceIndicator(1)
        go_to_matching_brace_action = create_action(self, "Go To Matching Brace")
        go_to_matching_brace_action.setShortcut(QKeySequence("Ctrl+0"))
        go_to_matching_brace_action.triggered.connect(self.__slot_go_to_matching_brace)
        self.addAction(go_to_matching_brace_action)

        self.cursorPositionChanged.connect(self.__slot_on_cursor_moved)
        self.textChanged.connect(self.__slot_on_text_changed)

        # Improve the doc string performance
        # Every keystroke triggers the doc string lookup, which is slow. Use a timer to show the doc string when
        # typing is "settled"
        self.__doc_string_timer = QTimer()
        self.__doc_string_timer.timeout.connect(self.__slot_on_update_doc_string)

    def set_coding_assistant(self, coding_helper: CodingAssistant):
        self.__code_helper = coding_helper
        if coding_helper is None:
            # NOTE: removing the lexer causes weird font effect which moves cursor which itself causes
            # additional transitions between lexers. For now, make the text read-only.
            # self.setLexer(None)
            self.setCaretLineVisible(False)
            self.setCaretLineBackgroundColor(QColor(Qt.lightGray))
            self.lexer().setPaper(QColor(Qt.lightGray))

        elif coding_helper.LEXER_CLASS is not None:
            self.setCaretLineVisible(True)
            self.setCaretLineBackgroundColor(self.DEFAULT_LINE_COLOR)

            # enable syntax highlighting
            lexer = coding_helper.LEXER_CLASS(self)
            lexer.setFont(self.__from_default_mono)
            lexer.setDefaultFont(self.__from_default_mono)
            self.setLexer(lexer)

            if coding_helper.AUTO_INDENT_STYLE is not None:
                lexer.setAutoIndentStyle(coding_helper.AUTO_INDENT_STYLE)

    def set_lang_monitor(self, monitor: LangMonitor):
        self.__lang_monitor = monitor

    def enable_breakpoint_marking(self, enable: bool = True):
        """
        Some editors have breakpoints and others don't. This is used to enable or disable the breakpoint feature.
        :param enable: True to enable it, False to disable it.
        """
        self.marginClicked.connect(self.__slot_on_margin_clicked)
        self.markerDefine(QsciScintilla.RightArrow, self.MARKER_BREAKPOINT)
        self.setMarkerBackgroundColor(self.BREAKPOINT_MARKER_COLOR, self.MARKER_BREAKPOINT)
        self.markerDefine(QsciScintilla.Background, self.MARKER_BREAKPOINT_BACKGROUND)
        self.setMarkerBackgroundColor(self.BREAKPOINT_BACKGROUND_COLOR, self.MARKER_BREAKPOINT_BACKGROUND)
        self.markerDefine(QsciScintilla.Background, self.MARKER_STOPPED_AT)
        self.setMarkerBackgroundColor(self.BREAKPOINT_STEP_COLOR, self.MARKER_STOPPED_AT)
        self.__enable_breakpoint_marking = enable

    @override(QsciScintilla)
    def keyPressEvent(self, kpevent: QKeyEvent):
        """
        Handle keys that should update completions
        :param kpevent: The keyEvent from Qt
        """
        # first accept the character so it gets added to the text in editor
        super().keyPressEvent(kpevent)

        if self.__code_helper is not None and self.__code_helper.CAN_COMPLETE and not self.isReadOnly():
            char = kpevent.text()
            if char and char.isprintable():
                word_at_line_index = self.wordAtLineIndex(*self.getCursorPosition())
                if self.__code_helper.check_show_completions(char, word_at_line_index):
                    self.__show_auto_completions()

    @override(QsciScintilla)
    def mousePressEvent(self, mouse_press_event: QMouseEvent):
        """
        Evaluates if there is word under the mouse. If so, it shows the doc string, if there is one.
        :param mouse_press_event: The event from the Qt
        """
        super().mousePressEvent(mouse_press_event)

    def get_breakpoints(self) -> Set[int]:
        """
        Get a set of breakpoints.
        :return: Return a set containing the line numbers at which a break point can be set.
        """
        breakpoints = set()
        for line_no in range(0, self.lines()):
            if self.is_breakpoint_at_line(line_no + 1):
                breakpoints.add(line_no + self.DEBUGGER_TO_EDITOR_LINE_OFFSET)
        return breakpoints

    def set_breakpoints(self, breakpoints: set([int])):
        """
        Method used to initialize the editor with the correct breakpoints.
        :param breakpoints: A list containing all of the breakpoints to set for this part.
        """
        assert self.__enable_breakpoint_marking
        for line_number in breakpoints:
            self.markerAdd(line_number - self.DEBUGGER_TO_EDITOR_LINE_OFFSET, self.MARKER_BREAKPOINT)
            self.markerAdd(line_number - self.DEBUGGER_TO_EDITOR_LINE_OFFSET, self.MARKER_BREAKPOINT_BACKGROUND)

    def get_debug_mode(self) -> bool:
        """
        Gets the current mode of the script panel.
        :return: the boolean which indicates if the panel is in debug mode or not.
        """
        return self.__is_debug_mode

    def set_debug_mode(self, value: bool = False):
        """
        Sets the mode of the script panel to debug or normal.
        :param value: True for debug mode and False for normal mode.
        """
        if value != self.__is_debug_mode:
            self.__is_debug_mode = value

        if value:
            # Add a background marker (line color) to the current line stepped to
            self.__current_debug_line = self.getCursorPosition()[0]
            self.markerAdd(self.__current_debug_line, self.MARKER_STOPPED_AT)

            # Ensure scroll bar position is the last one set, otherwise ensure cursor is always visible
            self.__scroll_bar = self.verticalScrollBar()
            if self.__scroll_value is not None:
                self.__scroll_bar.setSliderPosition(self.__scroll_value)
                self.ensureCursorVisible()
        else:
            self.__current_debug_line = None

            if self.__scroll_bar is not None:
                # Save value for next step
                self.__scroll_value = self.__scroll_bar.sliderPosition()

    def is_breakpoint_at_line(self, line_no: int) -> bool:
        """
        Checks if a breakpoint is present on the line provided.
        :param line_no: The script line to check.
        :return: True if a breakpoint is present and False otherwise.
        """
        return bool(self.markersAtLine(line_no - 1) & (1 << self.MARKER_BREAKPOINT))

    def check_marker_at(self, line_no: int, marker: int) -> bool:
        """
        Check if a line has a certain marker.
        :param line_no: line number (starts at 1)
        :param marker: number of the marker (one of the self.MARKER_ constants)
        :return: True if given marker is there
        """
        return bool(self.markersAtLine(line_no - 1) & (1 << marker))

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    @property
    def current_break_line(self):
        return self.__current_debug_line

    breakpoints = property(get_breakpoints, set_breakpoints)
    is_debug_mode = property(get_debug_mode, set_debug_mode)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __setup_code_completion(self):
        """
        Enables the code completion features. This function is supposed to be invoked only once when this class is
        instantiated.
        """
        self.userListActivated.connect(self.__slot_user_list_choice)
        shortcut_ctrl_space = QShortcut(QKeySequence("Ctrl+Space"), self)
        shortcut_ctrl_space.activated.connect(self.__slot_show_auto_completions)

    def __on_margin_clicked(self, _1: int, line_number: int, _2: Qt.KeyboardModifiers):
        """
        This method is called when a click occurs on the left margin.
        :param line_number: The line number at which a margin clicked occurred.
        """
        # Toggle marker for the line the margin was clicked on
        assert self.__enable_breakpoint_marking
        if self.markersAtLine(line_number) != 0:
            self.markerDelete(line_number, self.MARKER_BREAKPOINT)
            self.markerDelete(line_number, self.MARKER_BREAKPOINT_BACKGROUND)
        else:
            self.markerAdd(line_number, self.MARKER_BREAKPOINT)
            self.markerAdd(line_number, self.MARKER_BREAKPOINT_BACKGROUND)
            assert self.markersAtLine(line_number) > 0

        self.sig_breakpoint_toggled.emit()

    def __go_to_matching_brace(self):
        """
        Method used to go to a matching brace.
        """
        self.moveToMatchingBrace()

    def __update_docstring(self):
        """
        Extracts the doc string from the current definitions and sets it to the doc string panel.
        """
        self.__doc_string_timer.stop()
        # if there is a language monitor, it could change the coding assistant assigned so first updated it:
        line, col = self.getCursorPosition()
        abs_pos = self.positionFromLineIndex(line, col)
        text = self.text()
        current_word = self.wordAtLineIndex(line, col)
        if (text, abs_pos) == self.__last_update_docstring:
            return

        self.__last_update_docstring = (text, abs_pos)
        if self.__lang_monitor is not None:
            lang_block = self.__lang_monitor.check_lang(text, abs_pos)
            if lang_block is not None:
                text, line, col = lang_block.extract(text, line, col, self.lineIndexFromPosition)

        if self.__code_helper is None or not self.__code_helper.CAN_COMPLETE:
            # if no code assistance available, don't waste resources getting doc string
            return

        # context is an easy way to get Qt to do some work: aaa.bbb.ccc if cursor is on one of the 'b'
        # yields a context = ['aaa', 'b']
        context, start, end = self.apiContext(abs_pos)
        # Qt provides incomplete context, fix it (we would want ['aaa', 'bbb'] in previous example):
        if context:
            context[-1] = current_word
        else:
            context = [current_word]

        docstring = self.__code_helper.get_docs(text, line, col, context)
        if docstring:
            # log.debug("Docs at line={}, col={} is:\n{}", line, col, docstring)
            self.sig_docstring_changed.emit(docstring)

    def __show_auto_completions(self):
        """
        Open the user list of completions and wait for user to choose. If user chooses, the self.__auto_complete()
        will get called with the info about choice and what portion of doc has to be changed.
        """
        if self.__code_helper is None or not self.__code_helper.CAN_COMPLETE:
            return

        text = self.text()
        line, col = self.getCursorPosition()
        if self.__lang_monitor is not None:
            lang_block = self.__lang_monitor.check_lang(text, self.positionFromLineIndex(line, col))
            if lang_block is not None:
                text, line, col = lang_block.extract(text, line, col, self.lineIndexFromPosition)

        name_completions = self.__code_helper.get_completions(text, line, col)
        if name_completions:
            self.showUserList(self.AUTO_COMPLETIONS_LIST_ID, name_completions)
        else:
            self.cancelList()

    def __user_list_choice(self, list_id: int, selection: str):
        """
        Every user list choice by user ends up here. Process based on list_id.
        :param list_id: the ID for the list from which the selection was made
        :param selection: text of the selection from list
        """
        assert list_id == self.AUTO_COMPLETIONS_LIST_ID
        if list_id == self.AUTO_COMPLETIONS_LIST_ID:
            self.__auto_complete(selection)

    def __auto_complete(self, selection: str):
        """
        Execute an auto-completion: complete the word described by self.__auto_completion_info (saved by a
        previous call to self.__show_auto_completions()) with the selection. The whole completion is inserted in place
        of any typed characters to ensure proper capitalization.
        :param selection: the word to replace the document word described by self.__auto_completion_info
        """
        assert self.__code_helper.CAN_COMPLETE

        line, pos = self.getCursorPosition()

        # if the selection and the last typed word are the same, no need to go any further
        last_typed_word = self.wordAtLineIndex(line, pos)
        if last_typed_word == selection:
            return

        # complete_name = self.__code_assist.get_completion(selection)
        start_name = self.__code_helper.get_completion_start(selection)

        # Determine how many characters need to be removed
        if last_typed_word.lower() == selection.lower():
            # if the fully-typed word contained uppercase chars we need to replace it
            num_to_remove = len(selection)
        else:
            num_to_remove = len(start_name)

        # Removed the typed characters and insert the selected auto-completed text
        start_pos = pos - num_to_remove
        self.setSelection(line, start_pos, line, pos)
        self.removeSelectedText()
        self.insert(selection)

        # Reset the cursor to the end of the auto-completed text
        self.setCursorPosition(line, pos - num_to_remove + len(selection))

    def __on_cursor_moved(self):
        """
        Toggles the default line coloring OFF to show the current 'stepped-to' debug line marker color.
        This allows the special debug marker for that line to be shown. Default line color is toggled back on if
        any other line is clicked.

        Also, need to update the doc string for object under cursor.
        """
        if self.__current_debug_line is not None and self.getCursorPosition()[0] == self.__current_debug_line:
            self.setCaretLineVisible(False)  # Show the special debug marker
        else:
            self.setCaretLineVisible(True)  # Display default line color

        self.__doc_string_timer.start(self.DOC_STRING_TIMEOUT)

    def __on_text_changed(self):
        """
        The text can change without cursor moving, e.g. via delete char. Need to update doc string for object
        under cursor.
        """
        self.__doc_string_timer.start(self.DOC_STRING_TIMEOUT)

    __slot_on_margin_clicked = safe_slot(__on_margin_clicked)
    __slot_go_to_matching_brace = safe_slot(__go_to_matching_brace)
    __slot_show_auto_completions = safe_slot(__show_auto_completions)
    __slot_user_list_choice = safe_slot(__user_list_choice)
    __slot_on_cursor_moved = safe_slot(__on_cursor_moved)
    __slot_on_text_changed = safe_slot(__on_text_changed)
    __slot_on_update_doc_string = safe_slot(__update_docstring)


class PyCodingAssistant(CodingAssistant):
    """Specialization for Python coding."""

    CAN_COMPLETE = True
    USEFUL_WORDS = []
    LEXER_CLASS = QsciLexerPython

    def __init__(self, part: BasePart):
        """
        :param completion_namespaces: list of dictionaries to search for code completion; for example if one
            of the dictionaries has a key 'abc' with value 123, then when the user types 'a', the auto-completions
            list will include 'abc', and if the user accepts abc, then the int's methods will be shown. These
            dictionaries, and the list itself, can be modified outside of this scripting panel; the list is
            traversed and its dictionaries queried for matches every time the user types a printable character.
        """
        super().__init__()
        self.__params_namespace = {}
        self.__completion_namespaces = [self.__params_namespace, {}]

        def on_have_py_namespace(namespace: Dict[str, Any]):
            self.__completion_namespaces = [self.__params_namespace, namespace]
            self.USEFUL_WORDS = list(namespace)
            self._on_useful_keywords_changed()

        AsyncRequest.call(part.get_py_namespace, response_cb=on_have_py_namespace)

        self.__map_name_to_completion = None
        self.__completion_names = None
        self.__call_params = None
        self.__call_signature = None

    @override(CodingAssistant)
    def on_part_params_edited(self, params_text: str = None):
        try:
            new_params = get_params_from_str(params_text)

        except Exception:
            msg = dedent("""
                Parameters string could not be parsed. Valid examples are (without quotes):

                - "a, b, c": 3 parameters, each one has built-in type 'object'
                - "a: int, b: [], c: bool=True": 3 parameters, 'a' has type int, 'b' list, and
                    'c' boolean that defaults to True
                """)
            details = traceback.format_exc()
            exec_modal_dialog('Error Parsing Parameters', msg, QMessageBox.Critical, detailed_message=details)

        else:
            # don't reassign namespace so that ScriptPanel sees changes on next auto-completion action
            self.__params_namespace.clear()
            self.__params_namespace.update(new_params)

    @override(CodingAssistant)
    def check_show_completions(self, keystroke: str, word_at_cursor: str) -> bool:
        """
        Check if the keystroke, at the current line and position of cursor, indicates that auto
        completion should be shown.
        :param keystroke: string containing the key pressed by user
        :return: True if should show auto-completion, False otherwise
        """
        if keystroke == '.':
            # for methods, don't need any further chars:
            return True

        assert keystroke.isprintable()

        if not (keystroke.isidentifier() or keystroke.isdecimal()):
            return False

        return word_at_cursor.isidentifier()

    @override(CodingAssistant)
    def get_docs(self, text: str, line: int, col: int, context_words: List[str]) -> str:
        try:
            # in jedi, first line is 1, but in Scintilla it is 0
            jedi_scripter1, jedi_scripter2 = self.__get_jedies(text)
            definitions = jedi_scripter2.infer(line=line + 1, column=col)
            # call_signatures = jedi_scripter2.call_signatures()
            # definitions = jedi_scripter1.goto_definitions()  # doesn't work

        except Exception as exc:
            log.error(exc)
            return

        # first try with jedi;
        # if jedi could give us the actual object, we could use pydoc.Helper; alas, jedi is designed to work
        # without an interpreter available *in* the application and return only meta-data
        defn_docstrings = [get_jedi_docstring(defn) for defn in definitions]
        # call_docs = [get_jedi_docstring(defn) for defn in call_signatures]
        if not defn_docstrings:
            # jedi failed, best we can do is eval the context and hope inspect module is sufficient
            obj_expr = '.'.join(context_words)
            if obj_expr:
                try:
                    obj = eval(obj_expr, *self.__completion_namespaces)
                    docstring = get_docstring(obj)
                    defn_docstrings = [docstring] if docstring else []
                except Exception as exc:
                    # if there was *any* problem, we give up:
                    log.debug('WARNING: In attempting to get docstring on obj "{}", got exception: {}', obj_expr, exc)
                    defn_docstrings = []

        return "\n------------------------------------\n".join(defn_docstrings)

    @override(CodingAssistant)
    def get_useful_keyword_docstring(self, obj_name: str) -> Optional[str]:
        params_ns, py_ns = self.__completion_namespaces
        return inspect.getdoc(py_ns[obj_name])

    @override(CodingAssistant)
    def get_useful_keyword_suffix_for_pasting(self, obj_name: str) -> str:
        params_ns, py_ns = self.__completion_namespaces
        obj = py_ns[obj_name]
        if inspect.isfunction(obj) or inspect.ismethod(obj):
            return '()'
        else:
            return ''

    @override(CodingAssistant)
    def get_completions(self, text: str, line: int, col: int) -> List[str]:
        try:
            self.__update_completions(text, line, col)
            return self.__completion_names

        except Exception as exc:
            log.error(exc)

    @override(CodingAssistant)
    def get_completion(self, name: str) -> str:
        completion = self.__map_name_to_completion.get(name)
        return None if completion is None else completion.complete

    @override(CodingAssistant)
    def get_completion_start(self, name: str) -> str:
        completion = self.__map_name_to_completion.get(name)
        return None if completion is None else completion.name_with_symbols[:-len(completion.complete)]

    def __update_completions(self, text: str, line: int, line_pos: int):
        """
        Update the completions and call signature completion info for the current context (at cursor).
        """
        assert self.CAN_COMPLETE
        self.__map_name_to_completion = dict()
        self.__completion_names = list()
        self.__call_signature = None

        jedi_scripter1, jedi_scripter2 = self.__get_jedies(text)
        try:
            # in jedi, first line is 1, but in Scintilla it is 0
            completions1 = jedi_scripter1.complete(line=line + 1, column=line_pos)
            completions2 = jedi_scripter2.complete(line=line + 1, column=line_pos)

            # signatures1 = jedi_scripter1.call_signatures()
            signatures2 = jedi_scripter2.get_signatures(line=line + 1, column=line_pos)
            assert len(signatures2) <= 1  # how can there be more than one call signature possible (no overloads)
            if signatures2:
                self.__call_signature = signatures2[0]

        except Exception:
            # jedi is quite buggy, so it easily raises exceptions; when this happens, have to give up:
            assert not self.__map_name_to_completion
            return

        # join the two lists, removing duplicates (completions with same name):
        names1_not_in_2 = set(entry1.name for entry1 in completions1).difference(entry2.name for entry2 in completions2)
        entries = completions2.copy()
        for entry1 in completions1:
            if entry1.name in names1_not_in_2:
                entries.append(entry1)

        # filter out non-public items:
        for completion in entries:
            cname = completion.name
            # Do not show special functions and private functions
            if cname.startswith('__'):
                continue
            is_part_frame, _ = check_link_name_is_frame(cname)
            public = not cname.startswith('_') or is_part_frame
            if public:
                # normal public method member or hits the part frame naming convention: _name_
                self.__map_name_to_completion[completion.name] = completion
                self.__completion_names.append(completion.name)

        def public_first(name: str) -> str:
            # sort alphabetically, but all public first followed by frames/protected and frames and
            # finally private
            assert not name.startswith('__')
            if name.startswith('__'):
                return '3_' + name.lower()
            if name.startswith('_'):
                return '2_' + name.lower()
            return '1_' + name.lower()

        self.__completion_names.sort(key=public_first)

        # if the completion is on a call parameter, add '=' sign to it and *move* it to the top
        self.__call_params = {}
        CALL_PARAM_APPEND = '='
        if self.__call_signature is not None:
            params = self.__call_signature.params
            if params and self.__call_signature.index is not None:
                param = params[self.__call_signature.index]
                if param and param.name:  # sometimes jedi can't determine param name(!)
                    choice = param.name + CALL_PARAM_APPEND
                    self.__completion_names.insert(0, choice)
                    self.__completion_names.remove(param.name)
                    completion = self.__map_name_to_completion.pop(param.name)
                    self.__map_name_to_completion[choice] = completion

    def __get_jedies(self, text: str) -> Tuple[jedi.api.Script, jedi.api.Interpreter]:
        # Note: Script is able to match local vars created (like defining a class and accessing its methods),
        # whereas Interpreter is not. This is surely a bug, because Interpreter derives from Script. For
        # now, combine the two:
        text = text.replace('\r', '')
        jedi_scripter1 = jedi.api.Script(code=text)
        jedi_scripter2 = jedi.api.Interpreter(code=text, namespaces=self.__completion_namespaces)
        return jedi_scripter1, jedi_scripter2
