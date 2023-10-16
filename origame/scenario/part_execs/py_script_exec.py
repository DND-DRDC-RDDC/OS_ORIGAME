# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Support usage of python scripts in scenario parts

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import math
import random
import sys
import tempfile
from bdb import BdbQuit
from enum import IntEnum
from importlib import import_module
from pathlib import Path
from textwrap import dedent
from traceback import extract_tb
import re

# [2. third-party]

# [3. local]
from ...core import override_optional, BridgeEmitter, BridgeSignal, override
from ...core.utils import BlockProfiler
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..ori import OriFunctionPartKeys as FpKeys
from ..defn_parts import BasePart

from .py_debugger import PyDebugger
from .scripting_utils import LinkedPartsScriptingProxy

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'PyScriptExec',

    'PyScriptFuncCallError',
    'PyScriptCompileError',
    'PyScriptFuncRunError',

    'PyScenarioImportsManager',
    'PyScriptAutoImports',
]

log = logging.getLogger('system')

# name of the object in scripts that provides access to self.frame outgoing links:
LINKS_SCRIPT_OBJ_NAME = 'link'

ImportSources = Either[str, Tuple[str, str]]
ImportSource = Tuple[str, str]


class Decl(AnnotationDeclarations):
    PartLink = 'PartLink'


# -- Function definitions -----------------------------------------------------------------------


def get_sym_import_info(source_info: ImportSources, alias: str=None) -> Tuple[str, str, str]:
    """
    Convert a symbol source info object into a triplet suitable to define a symbol name. This covers 4 use-cases:
    - import module (as a symbol of that name)
    - import attribute from module (as a symbol of that name)
    - import module as a differently-named symbol
    - import attribute from a module as a differently-named symbol

    :return: symbol name, module name, attribute name. 
    """
    if isinstance(source_info, str):
        # the symbol is the  module, same name as module
        module_name, obj_name = source_info, None
        sym_name = alias or module_name
    else:
        # symbol is an attribute in the module, same name as attribute
        module_name, obj_name = source_info
        sym_name = alias or obj_name

    return sym_name, module_name, obj_name


# -- Class Definitions --------------------------------------------------------------------------

class PyScriptCompileError(Exception):
    """
    Raised when a script fails to compile (SyntaxError due to syntax, or TypeError due to invalid bytes).

    Note that compilation is different from execution of script, and that execution of a script is separate
    from execution of a function defined within the script.
    """

    def __init__(self, exc_obj: Either[SyntaxError, TypeError], part: BasePart):
        """
        :param exc_obj: the object that was raised as exception
        :param part: part which has script that caused the error
        """
        if isinstance(exc_obj, SyntaxError):
            line_num = exc_obj.lineno - part.get_debug_line_offset()
            py_statement = exc_obj.text.strip()
            line_msg = ' at line {}, statement "{}"'.format(line_num, py_statement)
            msg = 'Python script compilation error in part "{}"{}: {}'
            super().__init__(msg.format(part.path, line_msg, exc_obj.msg))

        else:
            msg = 'Python script compilation error in part "{}": {}'
            super().__init__(msg.format(part.path, exc_obj.msg))


class PyScriptFuncCallError(TypeError):
    """
    Raised when the call to a function defined from a part script is invalid: typically missing positional
    arguments and unrecognized keyword arguments.
    """

    def __init__(self, exc_obj: Exception = None, exc_message: str = None):
        """
        :param exc_obj: which exception was raised when Python called the function
        :param exc_message: the message to show if exc_obj is None
        """
        super().__init__(exc_message if exc_obj is None else exc_obj.args[0])


class PyScriptFuncRunError(Exception):
    """
    Raised when a script fails to execute. Note: execution of the script is not the same as execution of functions
    defined in the script, this exception can be raised in either case. This class when instantiated attempts
    to create a message that indicates the chain of scenario parts that were involved in the error. It supports
    being instantiated when the scripts are only in memory (not on filesystem) in which case the information
    is minimal (this is the way Python works), vs when scripts are on filesystem (PyDebugger active) the information
    is much more detailed.
    """

    FrameInfo = Tuple[str, int, str, str]  # filename, line no, func name, text

    # Indices of items in tuple returned by traceback.extract_tb()
    FILENAME_IDX, LINE_NUMBER_IDX, FUNC_IDX, TEXT_IDX = range(4)

    def __init__(self, exc_obj: Exception, raising_part: BasePart = None):
        """
        :param exc_obj: the object that was raised as exception; if a string, assume this object is being
            constructed from another instance of PyScriptFuncRunError, so raising_part must be None
        :param raising_part: part which has script that caused the error; must be None if exc_obj is a string
        """
        # first check if created from a string: then this is an exception "copy" (likely pytest) so save msg and return
        if isinstance(exc_obj, str):
            assert raising_part is None
            super().__init__(exc_obj)
            return

        # extract from the traceback stack only those entries that correspond to a scenario part:
        tb = extract_tb(sys.exc_info()[2])

        self.message_stack = []

        if isinstance(exc_obj, PyScriptCompileError):
            # Func run exception from part script compile error
            self.message_stack.append(str(exc_obj))
            msg = '-> Required by '

        elif isinstance(exc_obj, PyScriptFuncCallError):
            # Func run exception from invalid part script func call
            self.message_stack.append(str(exc_obj))
            msg = '-> From invalid call into part script callable at '

        elif isinstance(exc_obj, PyScriptFuncRunError):
            # Func run exception from nested part script func run error
            self.message_stack.extend(exc_obj.message_stack)
            msg = '-> Nested call from '

        else:
            # Func run exception from non-part error
            self.message_stack.append(str(exc_obj))
            msg = '-> Called from '

        self.message_stack.append(msg + self.__find_tb_info(tb, raising_part))

        msg = 'Python script execution error: {}\n{}'.format(
            self.message_stack[0], '\n'.join(self.message_stack[1:]))
        # if an error is at script level, Python interpreter says location is "<module>", which won't mean much to user
        # so replace it by "<script>"
        msg = msg.replace('<module>', '<script>')

        super().__init__(msg)

    def __find_tb_info(self, tb: List[FrameInfo], raising_part: BasePart) -> str:
        debugger = PyDebugger.get_singleton()
        for frame_info in reversed(tb):
            if debugger is None:
                return self.__get_basic_stack_message(raising_part, frame_info)
            else:
                part_at_frame = debugger.get_registered_part(frame_info[self.FILENAME_IDX])
                if part_at_frame is not None:
                    return self.__get_stack_message(part_at_frame, frame_info)

    def __get_stack_message(self, part_at_frame: BasePart, part_frame_info: FrameInfo) -> str:
        """
        Get the stack trace message for a given part and its call frame.
        :param part_at_frame: the part associated with call frame
        :param part_frame_info: the call frame associated with part
        :return: string describing the stack info
        """
        assert part_at_frame is not None

        # we have a scenario part, now create the part/line/statement/func_name message for it:
        line_num = part_frame_info[self.LINE_NUMBER_IDX] - part_at_frame.get_debug_line_offset()
        py_statement = part_frame_info[self.TEXT_IDX].strip()
        line_msg = 'line {} of part "{}"'.format(line_num, part_at_frame.path)
        if py_statement:
            line_msg += ', statement "{}"'.format(py_statement)
        if part_at_frame.PART_TYPE_NAME not in [FpKeys.PART_TYPE_FUNCTION]:
            func_name = part_frame_info[self.FUNC_IDX]
            line_msg += ", in {}".format(func_name)
            if func_name != '<module>':
                line_msg += '()'

        return line_msg

    def __get_basic_stack_message(self, raising_part: BasePart, frame_info: FrameInfo) -> str:
        """
        Get the basic stack trace message for a frame. Because debugger not available, only basic info available.
        :param frame_info: the frame info, as obtained from traceback via __gen_basic_part_frame_info
        :return:  the message describing where the call was made at given stack level
        """
        # create the part/line/statement/func_name message for it:
        line_num = frame_info[self.LINE_NUMBER_IDX]
        func_name = frame_info[self.FUNC_IDX]
        file_name = frame_info[self.FILENAME_IDX]
        if raising_part.debug_file_path == file_name:
            line_num = line_num - raising_part.get_debug_line_offset()
            line_msg = 'line {} of part "{}"'.format(line_num, raising_part.path)
            if raising_part.PART_TYPE_NAME != FpKeys.PART_TYPE_FUNCTION:
                line_msg = "{} in {}".format(line_msg, func_name)

        else:
            line_msg = 'line {} of {}, in {}'.format(line_num, file_name, func_name)

        if func_name != '<module>':
            line_msg += '()'

        return line_msg


class GetSymbolValueError(ImportError):
    pass


class ReasonMissingEnum(IntEnum):
    missing_module, missing_sym = range(2)


class PyScenarioImportsManager:
    """
    Manages the import dependencies of a scenario. All scripted parts use the same imports registry.
    """

    def __init__(self):
        self.__mod_attrs_not_found = set()
        self.__modules_not_found = set()
        self.__map_imports_to_objects = {}

    def add_import(self, module_name: str, mod_attr_name: Optional[str]):
        """
        Register an import.
        :param module_name: the module to import
        :param mod_attr_name: if given, the (module variable) name of object to import from module
        """
        if (module_name, mod_attr_name) in self.__map_imports_to_objects:
            return

        if (module_name, mod_attr_name) in self.__mod_attrs_not_found or module_name in self.__modules_not_found:
            return

        try:
            module = import_module(module_name)

        except ImportError:
            err_msg = 'Module "{}" not found'.format(module_name)
            if module_name not in self.__modules_not_found:
                log.warning(err_msg)
            self.__modules_not_found.add(module_name)
            raise GetSymbolValueError(err_msg)

        if mod_attr_name is None:
            self.__map_imports_to_objects[(module_name, mod_attr_name)] = module

        elif hasattr(module, mod_attr_name):
            self.__map_imports_to_objects[(module_name, mod_attr_name)] = getattr(module, mod_attr_name)

        else:
            err_msg = 'Object named "{}" not found in module "{}"'.format(mod_attr_name, module_name)
            if (module_name, mod_attr_name) not in self.__mod_attrs_not_found:
                log.warning(err_msg)
            self.__mod_attrs_not_found.add((module_name, mod_attr_name))
            raise GetSymbolValueError(err_msg)

    def get_resolved_imports(self, syms: Dict[str, ImportSource]) -> Dict[str, ImportSource]:
        """
        Filter a map of import sources to get only those that can be resolved to a Python object.
        :param syms: the map of keys to ImportSource to filter
        :return: map of keys to ImportSource for which the import source could be resolved to a Python object
        """
        return {sym_name: source_info for sym_name, source_info in syms.items()
                if source_info in self.__map_imports_to_objects}

    def get_missing_imports(self, syms: Dict[str, ImportSource]) -> Dict[str, ReasonMissingEnum]:
        """
        Get symbols that cannot be resolved to a Python object from an import source.
        :return: map of symbols not found to the reason not found. If all symbols could be resolved, the returned
            map will be empty.
        """
        missing = dict()
        for sym_name, (module_name, mod_attr_name) in syms.items():
            if module_name in self.__modules_not_found:
                missing[sym_name] = ReasonMissingEnum.missing_module
            elif (module_name, mod_attr_name) in self.__mod_attrs_not_found:
                missing[sym_name] = ReasonMissingEnum.missing_sym
            else:
                assert (module_name, mod_attr_name) in self.__map_imports_to_objects

        return missing

    def get_symbol_values(self, syms: Dict[str, ImportSource]) -> Dict[str, Any]:
        """
        Get the value for each symbol based on the import source. Symbols that don't have values (because of
        missing module or symbol not defined in module) are not in the returned mapping.
        """
        return {sym_name: self.__map_imports_to_objects[source]
                for sym_name, source in syms.items()
                if source in self.__map_imports_to_objects}


class PyScriptAutoImports:
    """
    Provides a script with a means to define symbol imports that are automatically added to the script's
    namespace before it is executed.
    """

    def __init__(self, scen_sym_manager: PyScenarioImportsManager):
        self.__scen_sym_manager = scen_sym_manager
        self.__symbols = dict()  # Dict[str, ImportSource]

    def add_symbol(self, source_info: ImportSources, alias: str=None):
        sym_name, module_name, obj_name = get_sym_import_info(source_info, alias)
        try:
            self.__scen_sym_manager.add_import(module_name, obj_name)
        except GetSymbolValueError as exc:
            log.warning('Could not resolve symbol {}: {}', sym_name, exc)
        self.__symbols[sym_name] = (module_name, obj_name)

    def remove_symbol(self, sym_name: str):
        del self.__symbols[sym_name]

    def replace_symbol(self, source_info: ImportSources, alias: Optional[str]):
        self.add_symbol(source_info, alias=alias)

    def clear_all_symbols(self):
        self.__symbols = dict()

    def get_resolved_symbols(self) -> Dict[str, ImportSource]:
        return self.__scen_sym_manager.get_resolved_imports(self.__symbols)

    def get_missing_symbols(self) -> Dict[str, ReasonMissingEnum]:
        return self.__scen_sym_manager.get_missing_imports(self.__symbols)

    def get_all_symbols(self) -> Dict[str, ImportSource]:
        return self.__symbols.copy()

    def get_symbol_values(self) -> Dict[str, Any]:
        """
        Get a mapping of symbols to their values. Symbols that were added but could not be resolved are absent
        from the returned map.
        """
        return self.__scen_sym_manager.get_symbol_values(self.__symbols)


class PyScriptExec:
    """
    Provides for compilation and execution of scripts of scenario parts, and debuggable execution of callables defined
    in the scripts. This class defines an "execution sandbox" for the script: it provides a namespace that defines
    certain objects that can be accessed by the script (like a print function, some modules, objects to access
    linked parts and frames, etc). Derived classes can add their own items to this namespace.

    Debugging of scripts requires that they be in a file, so this class creates a text file that
    contains the script, if the PyDebugger singleton has already been instantiated.

    A scenario part class that uses python script should derive from this class, call _update_debuggable_script()
    when the script changes, call _check_compile_and_exec() when the script should be compiled and executed, and
    call _py_exec() to execute a function available in the script namespace (the function may have been defined
    by the script or added to its execution namespace via add_to_namespace()).
    """

    # --------------------------- class-wide data and signals -----------------------------------

    class PyScriptExecSignals(BridgeEmitter):
        # True - if there is at least one break point. The slot is not interested in the actual number of
        #  break points for now.
        sig_breakpoints_set = BridgeSignal(bool)

    def __init__(self, py_script_imports_mgr: PyScenarioImportsManager):
        """
        Initialize the logging system so scripts can use PRINT log level; the script namespace, the
        debugging functionality and the script exec functionality.
        """
        # provide parts and frames proxies
        self._parts_proxy = LinkedPartsScriptingProxy(self)
        self.__script_namespace = {}
        self.__script_auto_names = set()
        self.__script_imports_mgr = PyScriptAutoImports(py_script_imports_mgr)
        self.__need_compile = True
        self._setup_namespace()

        # the singleton exists only if the UI event processor was configured (see PyDebugger.set_user_action_callback)
        self.__debugger = PyDebugger.get_singleton()
        if self.__debugger is None:
            # still need unique name so that profiler (when used) can distinguish from other function parts
            self.__src_file_path = "{}_{}".format(self.name, id(self))
        else:
            temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w')
            self.__src_file_path = self.__debugger.canonic(temp_file.name)
            self.__debugger.register_part(self)

        self.__whole_script = None
        self.py_script_exec_signals = PyScriptExec.PyScriptExecSignals()

    # @override(BasePart)
    def on_outgoing_link_removed(self, link: Decl.PartLink):
        link_name = link.name
        self._parts_proxy.invalidate_link_cache(link_name)

    # @override(BasePart)
    def on_outgoing_link_renamed(self, old_name: str, _: str):
        self._parts_proxy.invalidate_link_cache(old_name)

    # @override(BasePart)
    def on_link_target_part_changed(self, link: Decl.PartLink):
        self._parts_proxy.invalidate_target_cache(link)

    # --- DEBUGGING -------------------------------------

    @override_optional
    def get_debug_line_offset(self) -> int:
        """
        Some scenario parts have scripts with additional lines to be inserted at top, that user must not see.
        These classes should override this method to return this number of lines, which otherwise defaults to 0.
        """
        return 0

    def get_debug_file_path(self):
        """
        Get the file path where script was saved to support debugging. If no debugger is available, this
        name is a unique name that identifes the part in memory for traceback messages.
        """
        return self.__src_file_path

    # --- Breakpoints -------------------------------------

    def set_breakpoint(self, line_num: int):
        """Set a breakpoint in script. First line would be line_num=1."""
        if self.__debugger is None:
            raise RuntimeError("No debugger available, can't set breakpoints")
        # add debug_line_offset to account for "header" lines added to script by derived class
        line_num = line_num + self.get_debug_line_offset()
        self.__debugger.set_break(self.__debugger.canonic(self.__src_file_path), line_num)

    def unset_breakpoint(self, line_num: int):
        if self.__debugger is None:
            raise RuntimeError("No debugger available, can't unset breakpoints")
        self.__debugger.clear_break(self.__src_file_path, line_num + self.get_debug_line_offset())

    def clear_all_breakpoints(self):
        if self.__debugger is None:
            return
        self.__debugger.clear_all_file_breaks(self.__src_file_path)

    def get_breakpoints(self) -> Set[int]:
        """Get the list of breakpoint lines of this function part's script. First line is 1."""
        if self.__debugger is None:
            return set([])
        return set(line_num - self.get_debug_line_offset()
                   for line_num in self.__debugger.get_file_breaks(self.__src_file_path))

    def set_breakpoints(self, breakpoints: Set[int]):
        """Set a list of breakpoints. This clears any current breakpoints set. First line is 1."""
        log.debug('PyScriptExec setting breakpoints {}', sorted(list(breakpoints)))

        self.clear_all_breakpoints()
        for line_number in breakpoints:
            self.set_breakpoint(line_number)

        if self.get_breakpoints() != set(breakpoints):
            log.debug('PyScriptExec breakpoints set: {}', sorted(list(self.get_breakpoints())))
            # check all set, although order does not matter:
            raise RuntimeError(self.get_breakpoints(), breakpoints)

        if self._anim_mode_shared:
            self.py_script_exec_signals.sig_breakpoints_set.emit(len(breakpoints) > 0)

    # --- Commands for when debugger blocked at a line of code -------------------------------------

    def debug_step_over(self):
        """Execute the current line"""
        if self.__debugger is None:
            raise RuntimeError("No debugger available, can't get step over")
        self.__debugger.next_command_step_over()

    def debug_step_in(self):
        """Step into the next frame called"""
        if self.__debugger is None:
            raise RuntimeError("No debugger available, can't get step in")
        self.__debugger.next_command_step_in()

    def debug_step_out(self):
        """Complete the current frame until return, then break"""
        if self.__debugger is None:
            raise RuntimeError("No debugger available, can't get step out")
        self.__debugger.next_command_step_out()

    def debug_continue(self):
        """Continue to next breakpoint or end of function"""
        if self.__debugger is None:
            raise RuntimeError("No debugger available, can't continue exec")
        self.__debugger.next_command_continue()

    def debug_stop(self):
        """Abort function call"""
        if self.__debugger is None:
            raise RuntimeError("No debugger available, can't get stop exec")
        self.__debugger.next_command_stop()

    # --- Script execution namespace --------------------------------------------

    def add_to_namespace(self, name: str, obj: Any, auto: bool=False):
        """
        Add the given object to this script's execution namespace, with given name. If auto=True,
         the symbol is treated as one automatically
        """
        self.__script_namespace[name] = obj
        if auto:
            self.__script_auto_names.push(name)

    def get_from_namespace(self, name: str) -> object:
        """
        Get object of given name in script's execution namespace.
        :raise: Value if no such name
        """
        try:
            return self.__script_namespace[name]
        except KeyError:
            raise ValueError('Part script "{}" does not define a variable named "{}"'.format(self.path, name))

    def namespace_has(self, name: str) -> bool:
        """Return true if the script namespace has variable of given name, at this moment"""
        if self.__need_compile:
            log.debug('WARNING: namespace_has() called on out-of-date namespace')
        return name in self.__script_namespace

    def get_py_namespace(self, with_auto: bool = True) -> Dict[str, Any]:
        """Get the dictionary of names to objects available when the script executes"""
        if not with_auto:
            return {k: v for k, v in self.__script_namespace.items() if k not in self.__script_auto_names}

        return self.__script_namespace

    def add_imports(self, *imports: ImportSources, **imports_as: ImportSources):
        """
        Add imports for this Python-scripted part.
        :param imports: a list of source info; the symbol name will be automatically set from the source info
        :param imports_as: a list of source info, where the symbol name is given
        
        add_imports(
            'module',                      # import module as-is
            ('module', 'attrib'),          # from module, import symbol named attrib
            module_as=module,              # import module as something
            attrib_as=('module', 'attrib') # from module, import symbol name attrib, as attrib_as
        )
        """
        for source_info in imports:
            self.__script_imports_mgr.add_symbol(source_info)

        for sym_name, source_info in imports_as.items():
            self.__script_imports_mgr.add_symbol(source_info, alias=sym_name)
        
        self._setup_namespace()

    def get_resolved_imports(self) -> Dict[str, ImportSource]:
        """Get all symbols that could be resolved to an object (even those that could not be imported)"""
        return self.__script_imports_mgr.get_resolved_symbols()

    def get_missing_imports(self) -> Dict[str, ReasonMissingEnum]:
        """Get a mapping of symbol names to reasons why symbol could not be imported"""
        return self.__script_imports_mgr.get_missing_symbols()

    def get_all_imports(self) -> Dict[str, ImportSource]:
        """
        Get all symbols defined (even those that could not be imported). The keys are the symbols, whereas the
        import source is a string if the
        """
        return self.__script_imports_mgr.get_all_symbols()

    def set_all_imports(self, imports: Dict[str, ImportSource]):
        """
        Replace the existing imports for this Python-scripted part by a new set of imports.
        :param imports: a list of source info; the symbol name will be automatically set from the source info
        """
        self.__script_imports_mgr.clear_all_symbols()
        self.add_imports(** imports)

    def get_imported_values(self) -> Dict[str, Any]:
        """Get a map from symbols to Python objects; only symbols that could be resolved to values are returned."""
        return self.__script_imports_mgr.get_symbol_values()

    def get_unreferenced_imports(self) -> Set[str]:
        unreferenced = set()
        for sym_name in self.__script_imports_mgr.get_resolved_symbols():
            if re.search(r'\b{}\b'.format(sym_name), self.__whole_script) is None:
                unreferenced.add(sym_name)

        return unreferenced

    # --------------------------- instance PUBLIC properties ----------------------------

    debug_file_path = property(get_debug_file_path)
    breakpoints = property(get_breakpoints, set_breakpoints)
    imports = property(get_all_imports, set_all_imports)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (breakpoints, imports)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def _update_debuggable_script(self, whole_script: str):
        """
        Set the script that will be compiled and executed. After this is called, the next call to
        _check_compile_and_exec() (which must be done by the derived class) will cause re-compilation and
        execution of the script.
        :param whole_script: the complete script, assumed to have get_debug_lines_offset() lines at start of script
        """
        self.__need_compile = True

        whole_script = whole_script.replace('\r', '')
        if self.__debugger is not None:
            with Path(self.__src_file_path).open('w') as temp_file:
                # WARNING: must not have \r in the text saved, else debugger gets confused
                temp_file.write(whole_script)

        self.__whole_script = dedent(whole_script)

    def _check_compile_and_exec(self) -> bool:
        """
        Compile and execute the script set via _update_debuggable_script().
        Upon return, the caller can explore the execution namespace (using get_from_namespace())
        for values of interest (such as functions, constants, variables defined by the script).

        :return: True if was compiled and executed, False if it had already been compiled and executed successfully
        :raise: SyntaxError if could not be compiled
        :raise: any other exception raised by executing the script
        """
        if self.__need_compile:
            self.__compile_and_exec()
            return True

        return False

    def _py_exec(self, func_obj: Callable, *call_args, _debug_mode: bool = False, **call_kwargs):
        """
        Execute a function defined in the script.

        :param func_obj: the function to execute
        :param call_args: positional arguments to give to function called
        :param call_kwargs: optional arguments to give to function called
        :param _debug_mode: True to call using debugger, False for normal call

        :raise PyScriptCompileError: if the call involving compilation of a  failed (typically syntax error)
        :raise PyScriptFuncCallError: if could not call (typically missing positional arguments)
        :raise PyScriptFuncRunError: if call ok but execution failed (any other issue, such as division by zero,
            undefined variable, etc)
        """
        if _debug_mode and self.__debugger is None:
            raise RuntimeError("No debugger available, can't run in debug mode")

        try:
            if _debug_mode:
                return self.__debugger.debug_call(func_obj, *call_args, **call_kwargs)
            else:
                return func_obj(*call_args, **call_kwargs)

        except BdbQuit:
            # If we get here it is because a function part was run in debug mode and called us and the user
            # has aborted the run (Bdb will catch the exception at the top level, where function part script
            # was called). So we have nothing to do for now
            log.debug('PyScriptExec "{}": execution aborted', self.path)

        except TypeError as exc:
            self.__check_call_error('return func_obj(*call_args, **call_kwargs)')
            raise PyScriptFuncRunError(exc, self)

        except Exception as exc:
            raise PyScriptFuncRunError(exc, self)

    @override_optional
    def _setup_namespace(self):
        """
        Builds the script's namespace from scratch. The namespace contains objects that the script will have
        access to, such as print(), signal(), etc. The base method creates a NEW namespace and adds objects
        that all scripts share, such as print() and scenario path.

        If the derived class wishes to add more objects into the namespace
        (such as signal()), it must override this method. WARNING: it must call the super method, THEN make
        calls to add_to_namespace().
        """
        self.__need_compile = True

        # provide a print() function that uses the application's USER log
        user_logger = logging.getLogger('user')
        logging.PRINT = 15
        logging.addLevelName(logging.PRINT, 'PRINT')

        def script_print(*objects, sep=','):
            """Print given objects separated by sep to the PRINT log"""
            user_logger.log(logging.PRINT, '{}', sep.join(map(str, objects)))

        def get_scenario_path() -> str:
            """Get path to folder containing the scenario .ORI file, or None if not saved yet"""
            scen_path = self._shared_scenario_state.scen_filepath
            return None if scen_path is None else (str(scen_path.parent) + Path('/').root)

        def get_scenario_name() -> str:
            """Get name of the scenario .ORI file, or None if not saved yet"""
            scen_path = self._shared_scenario_state.scen_filepath
            return None if scen_path is None else scen_path.name

        def profiler(**out_info):
            return ScenProfiler(self, **out_info)

        profiler.__doc__ = ScenProfiler.__doc__

        self.__script_namespace = {
            'self': self,
            '_self_': self.part_frame,

            'log': user_logger,
            'print': script_print,
            'math': math,
            'random': random,
            'Path': Path,

            LINKS_SCRIPT_OBJ_NAME: self._parts_proxy,

            'get_scenario_name': get_scenario_name,
            'get_scenario_path': get_scenario_path,
            'profiler': profiler
        }

        self.__script_auto_names = list(self.__script_namespace.keys())
        self.__script_namespace.update(self.__script_imports_mgr.get_symbol_values())

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __check_call_error(self, marker: str):
        """
        Determine if there is a Call error on the exception stack. Does nothing if no call error.
        :param marker: which string marker to check for in the last traceback object
        :raise: PyScriptFuncCallError if marker string found in the last traceback object
        """
        exc_type, exc_obj, traceback = sys.exc_info()
        last_line_info = extract_tb(traceback)[-1]
        filename, line_num, func_name, src_text = last_line_info
        if src_text == marker:
            raise PyScriptFuncCallError(exc_obj=exc_obj)

    def __compile_and_exec(self):
        # compile and associate with a filename, necessary in order to use with Python's debugger
        try:
            # NOTE that traceback[0] for error in this part's script will use second arg of compile() as filename
            code_obj = compile(self.__whole_script, self.__src_file_path, "exec")
        except Exception as exc:
            raise PyScriptCompileError(exc, self)

        try:
            exec(code_obj, self.__script_namespace)
        except Exception as exc:
            raise PyScriptFuncRunError(exc, self)

        # now that we know exec has succeeded we can save the info:
        self.__need_compile = False


class ScenProfiler(BlockProfiler):
    """
    This can be used to profile various portions of a scenario. Use like this:

    with profiler():
        ...stuff to profile...

    If scenario_path is c:\\folder\path.ori, then when the "with" clauses is done, the profiling data is
    automatically saved to c:\\folder\path.pstats and can be opened with any pstats-compatible tool
    (PyCharm, gprof2d, etc). If out_info data was given, like this:

    with profiler(v=1, r=2):
        ...stuff to profile...

    then the output file will be c:\\folder\path_v_1_r_2.pstats so it is easy to use the profile in multiple
    places in one scenario run (out_info can contain a unique identifier for each section of code being
    profiled).
    """

    def __init__(self, py_part: PyScriptExec, **out_info):
        scen_path = str(py_part.shared_scenario_state.scen_filepath) or str(Path.cwd() / 'unsaved.ori')
        BlockProfiler.__init__(self, scen_path, **out_info)
