# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Support debugging of python scripts in Origame scenario parts

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from bdb import Bdb, BdbQuit
from linecache import checkcache
from types import FrameType
from weakref import WeakValueDictionary, WeakSet
import sys

# [2. third-party]

# [3. local]
from ...core import BridgeEmitter, BridgeSignal
from ...core import override, override_optional
from ...core.typing import Callable
from ...core.typing import AnnotationDeclarations

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'PyDebugger',
    'PyDebugInfo',
    'IPyDebuggingListener',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    PyScriptExec = 'PyScriptExec'
    PyDebugger = 'PyDebugger'


"""Signature for callable that can be registered via PyDebugger.set_user_action_callback()"""
UiProcEventsCallable = Callable[[], None]


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class PyDebugInfo:
    """
    Debug info for when debugger has stopped execution of a function at a line of code: line number, local and global
    variables, and the scenario part. .
    """

    def __init__(self, py_part: Decl.PyScriptExec, exec_frame: FrameType):
        self.py_part = py_part
        self.line_no = exec_frame.f_lineno
        self.local_vars = exec_frame.f_locals
        self.global_vars = exec_frame.f_globals


class IPyDebuggingListener:
    """API that must be supported by every object given to PyDebugger.register_debugging()."""

    @override_optional
    def debugger_hit_breakpoint(self):
        """Called when a breakpoint is hit"""
        pass

    @override_optional
    def debugging_done(self):
        """Called when normal execution resumes"""
        pass

    @override_optional
    def debugging_aborted(self):
        """Called when debug execution has been aborted by user"""
        pass


class PyDebugger(Bdb):
    """
    The Python script debugger to debug Parts that have Python script. The debugger is a singleton that gets
    created only if there is a "user action callback" (ie a callback function that returns the next user
    action once debugger has stopped at a line of code). This callback would be the GUI event processor in
    the case of a GUI, or an action "feeder" in the case of a unit test. Additionally, the class supports
    registration of objects that need to know when the debugger has blocked at a line of code, and when
    execution continues.

    The debugger requires scenario parts that support debugger to register themselves via register_part.
    Then a function that should be called "in debug mode" should call debug_call(); this will call
    the user_line() to automatically get called when the function is entered, a breakpoint is hit, or
    requested next line (step over, in, or out of) is reached. The user_line() method determines if the line of
    code is in a scenario part's script (rather than in library or application code); if so, it repeatedly
    calls the "user action callback" until an action is obtained, then resumes execution, and the process
    repeats.

    This class currently supports:
    - step over: execute the line of code hit, without entering it
    - step into part: execute the line of code by entering the next call frame that is in a scenario part script
    - continue: continue till next breakpoint, or until called function returns
    - stop: abort the execution, which uses BdbQuit exception to cause premature exit from the scenario
      part script function being called

    Not supported yet:
    - raw step into: would step into next deeper call frame if it is not in origame
    - step out to calling part: would continue until the next frame is in a scenario part
    """

    # --------------------------- class-wide data and signals -----------------------------------

    class Signals(BridgeEmitter):
        sig_start_debugging = BridgeSignal()
        sig_exit_debugging = BridgeSignal()

    __singleton = None

    # --------------------------- class-wide methods --------------------------------------------

    @classmethod
    def set_user_action_callback(cls, ui_obj_cb: UiProcEventsCallable, thread=None):
        """
        Set the callback to use whenever blocked on a line of code; this callback must call one of the
        next_command_*() methods otherwise the debugger will be blocked indefinitely. Example of callback:
        QApplication.processEvents(). If ui_obj_cb is not None, this method creates the singleton debugger.
        If this method is never called, or called with ui_obj_cb None, script parts will not be debuggable.

        Notes:
        - This only needs to be called *once* for the whole application, but should be called before the
          first Scenario is created so that all scripted parts can get the instance at initialization.
        - The ui_obj_cb can be set to None during testing to remove the debugger; all future instances
          of scripted parts will not be debuggable.
        """
        if ui_obj_cb is None:
            cls.__singleton = None
        else:
            cls.__singleton = PyDebugger(ui_obj_cb, thread)

    @classmethod
    def get_singleton(cls) -> Decl.PyDebugger:
        """This will return the singleton debugger, or none if set_user_action_callback() never called."""
        return cls.__singleton

    @classmethod
    def register_for_debug_events(cls, listener: IPyDebuggingListener):
        """
        Register an object as listener for debug events such as breakpoint hit, debugging done and debugging
        aborted (i.e. while blocked waiting for next debug action). The appropriate IPyDebuggingListener method
        on listener will be called.
        """
        if cls.__singleton:
            cls.__singleton.__blockage_listeners.add(listener)

    @classmethod
    def clear_debug_events_registry(cls):
        """
        Remove all listeners registered via register_for_debug_events()
        """
        if cls.__singleton:
            cls.__singleton.__blockage_listeners.clear()

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, get_user_action_cb: UiProcEventsCallable, thread: BridgeEmitter):
        """
        Instantiate the debugger. Should only be called by PyDebugger.set_user_action_callback().
        :param get_user_action_cb: a callback function that gets called when a line of code is reached,
            it is assumed this callback calls one of the next_command_*() methods
        :param thread: which thread to run in
        """

        Bdb.__init__(self)
        self.signals = PyDebugger.Signals(thread=thread)
        self.__current_debug_info = None  # when breakpoint hit, this contains stack info (line #, locals, etc)
        self.__get_user_action_cb = get_user_action_cb
        assert self.__get_user_action_cb

        # if there is code coverage in place, then we will want to forward to it:
        self.__chain_tracer = sys.gettrace()

        # the following will flag when we have received user's desired action as a result of calling
        # the self.__get_user_action_cb(); user_line() blocks until this becomes True
        self.__have_next_command = False

        # so we can reach the first breakpoint without first stopping on first line of function to debug
        self.__entered_func = False
        self.__stop_exec = False  # becomes true when user aborts
        self.__frame = None  # which execution frame are we in when user_line() gets called
        self.__step_into_part_frame = None  # from which part are we trying to "step into frame in part"

        # associate filenames to parts (debuggable code must be in a file); but we dont' want to keep the parts
        # alive, so use weak ref value dict
        self.__map_filenames_to_parts = WeakValueDictionary()
        # list of listeners interested in debug start/stop events, but we don't want to keep the listeners
        # alive, so use weak ref set
        self.__blockage_listeners = WeakSet()

        # prevent inadvertent use of Bdb's runcall, which we will use internally
        self.__runcall = self.runcall

    def get_current_debug_info(self) -> PyDebugInfo:
        """
        Get the debug info for the line that user_line() is currently blocked on. Returns None if not at a breakpoint.
        """
        return self.__current_debug_info

    @override(Bdb)
    def trace_dispatch(self, frame, event, arg):
        """Intercept Bdb's trace_dispatch so we can forward to the code coverage tracer, if any"""
        if self.__chain_tracer:
            self.__chain_tracer(frame, event, arg)

        # done with chaining, resume normal tracing:
        return super().trace_dispatch(frame, event, arg)

    def register_part(self, part: Decl.PyScriptExec):
        """Register the given part so that debugger can determine in what part script the user_line() is blocked"""
        self.__map_filenames_to_parts[part.debug_file_path] = part

    def unregister_part(self, part: Decl.PyScriptExec):
        """Unregister the given part. Leave breakpoints active in case part re-registered later"""
        del self.__map_filenames_to_parts[part.debug_file_path]

    def get_registered_part(self, debug_file_path: str) -> Decl.PyScriptExec:
        """
        Get the scenario part that is associated with a Python file. Useful to find the part for a particular
        traceback frame.
        """
        return self.__map_filenames_to_parts.get(debug_file_path)

    def debug_call(self, func: Callable, *args, **kwargs) -> object:
        """
        Call the given function so breakpoints will be hit and stepping can be used.
        """
        log.debug("PyDb: starting debug call of func {}", func)
        self.__step_into_part_frame = None
        self.__entered_func = False
        self.__current_debug_info = None
        self.__stop_exec = False
        orig_tracer = sys.gettrace()
        try:
            return self.__runcall(func, *args, **kwargs)

        except BdbQuit:
            log.error("BUG: PyDb should never get here, please report this")
            raise RuntimeError("BUG: should never get here, please report this")

        finally:
            log.debug("PyDb: returning from debug call of func {}", func)
            self.__step_into_part_frame = None
            self.__entered_func = False
            self.__current_debug_info = None
            if orig_tracer is not None and sys.gettrace() is None:
                sys.settrace(orig_tracer)
                log.debug("Original tracer restored at end of debug call")
            assert not self.__stop_exec

    def user_call(self, frame, args):
        """
        Called automatically upon stepping into (and only then) a new function. It is not currently used, but
        should be if there is a need to track entry/exit (user_return).
        """
        log.debug('debugger: user call', frame, args)

    def user_line(self, frame: FrameType):
        """
        The Bdb thinks we have hit a line of code that user wants to investigate. This method determines if this
        is really the case (line of code must be in a scenario part script, not in header, etc) and, if so,
        calls the registered "user action callback" to allow the user to choose what to do next via one of the
        next_command_*() methods.

        Note: A couple tricky aspects to Bdb:
        - it stops on the first Python statement inside the function that was given to debug_call(),
          even if there was no breakpoint there.
        - the set_step() and set_next() docstrings suggests that the first one is to step over, and the latter is
          to step into, but in fact it is the opposite
        """
        name = frame.f_code.co_name or "<unknownn>"
        filename = self.canonic(frame.f_code.co_filename)
        line_no = frame.f_lineno

        # only debug parts that derive from PyScriptExec; but, we might have arrived here because user did a
        # "step into part script" and there is Origame code between the frame where they did the step into,
        # and the part's script
        # log.debug("PyDb.user_line() at frame ({}, {}, {})", name, filename, line_no)
        if filename not in self.__map_filenames_to_parts:
            if self.__step_into_part_frame is None:
                # we have somehow reached code that is not in a part's script, without a step-into
                log.debug("PyDb: exec frame not in a scenario part, skipping to next upper frame")
                self.set_return(frame)
            else:
                # log.debug("PyDb: code not in a scenario part, but is result of step into, continuing step-into")
                self.set_step()
            return

        obj = self.__map_filenames_to_parts[filename]  # weak reference to the scenario part

        # so we know we are in a scenario part script, but if we're in the "header" section, skip:
        if line_no <= obj.get_debug_line_offset():
            log.debug("PyDb: exec code in header of script, skipping")
            self.set_step()
            return

        # for some reason, run_call() calls this method on entry to function, even if there is no breakpoint;
        # so skip this user_line() if no breakpoint:
        if not self.__entered_func:
            if not self.get_break(filename, line_no):
                log.debug("PyDb: exec code is in scripted part, but continuing since not breakpoint")
                self.set_continue()
                return
            self.__entered_func = True

        # enter debugging state
        log.debug("PyDb: breaking at line {} of {}, in func {}", line_no, filename, name)
        for listener in self.__blockage_listeners:
            listener.debugger_hit_breakpoint()

        self.__current_debug_info = PyDebugInfo(obj, frame)
        self.signals.sig_start_debugging.emit()

        # wait for next debug command: step in, out, over, continue, stop
        self.__frame = frame
        self.__have_next_command = False
        self.__step_into_part_frame = None  # if we did a step-into-part, we have reached it
        log.info("PyDb: waiting for next debug command")
        try:
            while not self.__have_next_command:
                # the next line allows the UI to process user actions, which ultimately will cause one of the other
                # methods of self to be called; these tell the debugger what to do next, and set the command flag.
                try:
                    self.__get_user_action_cb()
                except:
                    log.error("PyDb: UI event processing raised exception, aborting function call")
                    self.next_command_stop()
                    raise

        finally:
            # exit debugging state
            if self.__stop_exec:
                for listener in self.__blockage_listeners:
                    listener.debugging_aborted()
            else:
                for listener in self.__blockage_listeners:
                    listener.debugging_done()

            self.__have_next_command = False
            self.__frame = None
            self.__stop_exec = False

            self.signals.sig_exit_debugging.emit()

    def user_return(self, frame, return_value):
        log.debug('user return', frame, return_value)

    def next_command_step_over(self):
        """Execute the current line, stopping at next line in same frame"""
        log.debug("PyDb: will step to next line")
        # WARNING: Bdb docs are misleading but set_next(frame) is "step to next line in frame"
        self.set_next(self.__frame)
        self.__have_next_command = True

    def next_command_step_in(self):
        """Stop at next entry into a sub-frame that is in a scenario part script"""
        log.debug("PyDb: will step into next frame (further from caller)")
        # WARNING: Bdb docs are misleading but set_step() is "step into"
        self.set_step()
        self.__step_into_part_frame = self.__frame
        self.__have_next_command = True

    def next_command_step_out(self):
        """Stop at next return from a frame"""
        # Oliver TODO build 3: adjust this class to the next return frame is in a part script
        log.debug("PyDb: will step out of current frame")
        self.set_return(self.__frame)
        self.__have_next_command = True

    def next_command_continue(self):
        """Continue execution until next breakpoint or until debug_call() returns"""
        log.debug("PyDb: will continue till next breakpoint or finish")
        self.set_continue()
        self.__have_next_command = True

    def next_command_stop(self):
        """Abort the execution; causes runcall() to return prematurely via the Bdb exception"""
        log.debug("PyDb: will interrupt execution")
        self.set_quit()
        self.__stop_exec = True
        self.__have_next_command = True

    @override(Bdb)
    def set_break(self, filename: str, lineno: int, temporary: bool = False, cond: str = None, funcname: str = None):
        """
        Set a breakpoint in a Python file.
        :param filename: filename containing code in which to set breakpoint
        :param lineno: line # for breakpoint
        :param temporary: is the breakpoint temporary (gets unset as soon as hit)
        :param cond: a Python expression that will get evaluated with the frame's locals and globals and exec
            will block at breakpoint only if condition evaluates to true
        :param funcname: the name of function in which breakpoint is being set; Bdb docs are not clear, but it
            appears that funcname can be set to a string to break when the function is defined
        """
        if filename not in self.__map_filenames_to_parts:
            raise ValueError(
                "PyDb: Given filename '{}' not registered yet (see register_part() method)".format(filename))

        # invalidate the "file-lines" cache in case breakpoints set beyond previous end of file:
        checkcache(filename)
        err = super().set_break(filename, lineno, temporary=temporary, cond=cond, funcname=funcname)
        if self.get_break(filename, lineno):
            log.debug("Breakpoint set on line #{} of {}", lineno, filename)
        else:
            err_msg = "Could not set breakpoint on line #{} of {}: {}".format(lineno, filename, err)
            log.debug(err_msg)
            raise ValueError(err_msg)

    # --------------------------- instance PUBLIC properties ----------------------------

    current_debug_info = property(get_current_debug_info)
