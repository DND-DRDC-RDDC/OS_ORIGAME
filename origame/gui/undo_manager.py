# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Undo/Redo functionality for user initiated actions from the GUI.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from copy import deepcopy
from enum import IntEnum

# [2. third-party]
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QUndoCommand, QUndoStack, QMessageBox, QAction, qApp
from PyQt5.QtGui import QCursor

# [3. local]
from ..core import override, override_optional, override_required
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream, Callable
from ..core.typing import AnnotationDeclarations
from ..scenario.defn_parts import BasePart, Position, Vector, PartFrame, Size, FrameStyleEnum, RestoreIfxLevelInfo
from ..scenario.defn_parts import ActorPart, RestorePartInfo, FunctionPart, RunRolesEnum, RestoreIfxPortInfo
from ..scenario.defn_parts import PartLink, RestoreLinkInfo, LinkWaypoint, UnrestorableLinks, RestoreReparentInfo
from ..scenario.defn_parts import DetailLevelEnum, parts_to_str
from ..scenario.defn_parts import TypeReferencingParts

from .async_methods import AsyncRequest, AsyncErrorInfo
from .safe_slot import safe_slot
from .gui_utils import exec_modal_dialog
from .actions_utils import config_action

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'scene_undo_stack',
    'UndoCommandBase',

    # individual part commands:
    'RemovePartCommand',
    'AddPartCommand',
    'RenamePartCommand',
    'SavePartEditorCommand',
    'SetPartPropertyCommand',
    'FunctionPartToggleRoleCommand',
    'PartsPositionsCommand',
    'ResizeCommand',
    'ParentProxyPositionCommand',
    'ChangeIfxLevelCommand',

    # multipart commands:
    'RemovePartsCommand',
    'CutPartsCommand',
    'PasteCutPartsCommand',
    'PasteCopiedPartsCommand',

    # link-related commands:
    'CreateLinkCommand',
    'RetargetLinkCommand',
    'RemoveLinkCommand',
    'RenameLinkCommand',
    'DeclutterLinkCommand',

    # waypoint commands
    'AddWaypointCommand',
    'RemoveWaypointCommand',
    'RemoveWaypointsCommand',
    'RemoveAllWaypointsCommand',
    'WaypointPositionCommand',

    # ifx port commands
    'SwitchIfxPortSideCommand',
    'VerticalMoveIfxCommand'
]

log = logging.getLogger('system')
_scene_undo_stack = None


class Decl(AnnotationDeclarations):
    Actor2dPanel = 'Actor2dPanel'
    UndoCommandBase = 'UndoCommandBase'
    UndoEventEnum = 'UndoEventEnum'
    ViewClipboard = 'ViewClipboard'


BackendCallable = Callable[..., None]
PushCmdCallable = Callable[[QUndoCommand], None]
OnAsyncCmdDoneCallable = Callable[[Decl.UndoCommandBase, Decl.UndoEventEnum], None]


# -- Function definitions -----------------------------------------------------------------------

def scene_undo_stack():
    """
    :return: The QUndoStack used by the Actor2d Scene
    """
    global _scene_undo_stack
    if _scene_undo_stack is None:
        _scene_undo_stack = UndoStackExt()
        _scene_undo_stack.setObjectName("SceneUndoStack")
    return _scene_undo_stack


# -- Class Definitions --------------------------------------------------------------------------

class UndoEventEnum(IntEnum):
    """Each undo command will notify the stack of certain 'events'"""
    try_do_failed, try_do_success, redo_failed, redo_success, undo_failed, undo_success = range(6)


class UndoCommandBase(QUndoCommand):
    """
    All undoable scenario changes must be implemented in classes that derive from this class. Each one must implement
    the _get_redo_cb() and _get_undo_cb() methods to return a function that will be run in the backend thread to
    either do/redo or undo the action. Each class can optionally override the _on_redo_success() and
    _on_undo_success() if action is needed upon success of do/redo or undo (such as saving the result of the
    function run in the backend).

    This class is designed to support saving the 2d view zoom/center at the moment the action was created, so that
    the view can be restored before the command is undone.

    This class is also designed so that the extended undo/redo stack, UndoStackExt, can try the command, and push
    it only if succeeded, dropping it otherwise. This is supported by the try_do() method which takes a callback
    to be called when the command has completed: UndoStackExt can then be notified of the result. If successfull,
    the command will be pushed onto Qt's undo stack, which will call the command's redo(). Therefore this class
    overrides redo() to do the action only if undo has been called at least once.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # This must match the same value defined in Actor2dView. We define a value because we cannot import that.
    DEFAULT_ZOOM_SLIDER_VALUE = 250.0

    # ---------------------------- instance PUBLIC methods -------------------------------

    def __init__(self, view_is_parent: bool = False,
                 clipboard_after_undo: Decl.ViewClipboard = None,
                 clipboard_after_redo: Decl.ViewClipboard = None):
        """

        :param view_is_parent: set to True if the View context is the parent of actor
        :param clipboard_after_undo: clipboard to restore after undo() of this command
        :param clipboard_after_redo: clipboard to restore after redo() (but not try-do) of this command
        """
        super().__init__()
        self.__view_actor = None
        self.__view_position = Position(0.0, 0.0)
        self.__view_zoom_factor = UndoCommandBase.DEFAULT_ZOOM_SLIDER_VALUE
        self.__view_is_parent = view_is_parent
        self.__undone_at_least_once = False
        self.__on_async_cmd_done_cb = None
        self.__clipboard_after_undo = clipboard_after_undo
        self.__clipboard_after_redo = clipboard_after_redo

    def save_view_context(self, viewed_actor: ActorPart, viewport: Tuple[Position, float]):
        """
        Save the given viewport information as the view context of this action (the 2d view current actor
        and the center/zoom of 2d view at moment command created).
        :param viewed_actor: 2d view current actor at time command created
        :param viewport: pair, first item is center Position, second is zoom factor, of 2d view at time command created
        """
        if self.__view_is_parent:
            self.__view_actor = viewed_actor.parent_actor_part
            position, zoom_factor_2d = None, None
        else:
            self.__view_actor = viewed_actor
            position, zoom_factor_2d = viewport

        if position is not None:
            self.__view_position = position
        if zoom_factor_2d is not None:
            self.__view_zoom_factor = zoom_factor_2d

    def get_view_actor(self) -> ActorPart:
        """
        Gets the actor part where the command is executed.
        """
        return self.__view_actor

    def get_view_position(self) -> Position:
        """
        Gets the view center.
        """
        return self.__view_position

    def get_view_zoom_factor(self) -> float:
        """
        Gets the view zoom factor.
        """
        return self.__view_zoom_factor

    def try_do(self):
        """
        Try doing the action represented by this command.
        Details: set the cursor to indicate busy, and make the async request on the callback returned by
        self._get_redo_cb() (the callback will be called in the backend thread). When the callback is done,
        the cursor will be restored, and self._on_redo_success() will be called if no exception raised,
        or self._on_redo_fail() if an exception was raised by the callback. The push_callback will be
        called with no arguments.

        :param push_callback: callback to call if the action was successful (recipient can push self onto undo stack)
        """
        assert not self.__undone_at_least_once

        def error_cb(*args):
            if self.__on_async_cmd_done_cb is not None:
                self.__on_async_cmd_done_cb(self, UndoEventEnum.try_do_failed)
            self.__async_redo_fail(*args)

        def response_cb(*args):
            if self.__on_async_cmd_done_cb is not None:
                self.__on_async_cmd_done_cb(self, UndoEventEnum.try_do_success)
            self.__async_redo_success(*args)

        log.info('DO: {}', self._get_description_try_do())
        qApp.setOverrideCursor(QCursor(Qt.WaitCursor))
        AsyncRequest.call(self._get_redo_cb(), response_cb=response_cb, error_cb=error_cb)

    @override(QUndoCommand)
    def redo(self):
        """
        Redo the action represented by this command. This only does anything if the action was undone at least
        once.
        Details: set the cursor to indicate busy, and make the async request on the callback returned by
        self._get_redo_cb() (the callback will be called in the backend thread). When the callback is done,
        the cursor will be restored, and self._on_redo_success() will be called if no exception raised,
        or self._on_redo_fail() if an exception was raised by the callback.
        """

        if self.__undone_at_least_once:
            log.info('REDO: {}', self._get_description_redo())
            qApp.setOverrideCursor(QCursor(Qt.WaitCursor))

            def error_cb(*args):
                if self.__on_async_cmd_done_cb is not None:
                    self.__on_async_cmd_done_cb(self, UndoEventEnum.redo_failed)
                self.__async_redo_fail(*args)

            def response_cb(*args):
                if self.__on_async_cmd_done_cb is not None:
                    self.__on_async_cmd_done_cb(self, UndoEventEnum.redo_success)
                self.__async_redo_success(*args)

            AsyncRequest.call(self._get_redo_cb(), response_cb=response_cb, error_cb=error_cb)

    @override(QUndoCommand)
    def undo(self):
        """
        Undo the action represented by this command.
        Details: set the cursor to indicate busy, and make the async request on the callback returned by
        self._get_undo_cb() (the callback will be called in the backend thread). When the callback is done,
        the cursor will be restored, and self._on_undo_success() will be called if no exception raised,
        or self._on_undo_fail() if an exception was raised by the callback.
        """
        log.info('UNDO: {}', self._get_description_undo())
        qApp.setOverrideCursor(QCursor(Qt.WaitCursor))

        def error_cb(*args):
            if self.__on_async_cmd_done_cb is not None:
                self.__on_async_cmd_done_cb(self, UndoEventEnum.undo_failed)
            self.__async_undo_fail(*args)

        def response_cb(*args):
            if self.__on_async_cmd_done_cb is not None:
                self.__on_async_cmd_done_cb(self, UndoEventEnum.undo_success)
            self.__async_undo_success(*args)

        AsyncRequest.call(self._get_undo_cb(), response_cb=response_cb, error_cb=error_cb)
        self.__undone_at_least_once = True

    @override(QUndoCommand)
    def actionText(self) -> str:
        return self._get_description_try_do()

    def set_on_async_done_notify(self, on_async_cmd_done: OnAsyncCmdDoneCallable):
        self.__on_async_cmd_done_cb = on_async_cmd_done

    @property
    def clipboard_after_undo(self) -> Decl.ViewClipboard:
        """
        The clipboard that was given to instance, and that must be restored when this command is undone.
        """
        return self.__clipboard_after_undo

    @property
    def clipboard_after_redo(self) -> Decl.ViewClipboard:
        """
        The clipboard that was given to instance, and that must be restored when this command is redone.
        """
        return self.__clipboard_after_redo

    @property
    def has_clipboards(self) -> bool:
        """True if either clipboard exists"""
        return self.__clipboard_after_undo is not None or self.__clipboard_after_redo is not None

    # ---------------------------- instance PUBLIC properties ----------------------------

    view_actor = property(get_view_actor)
    view_position = property(get_view_position)
    view_zoom_factor = property(get_view_zoom_factor)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_optional
    def _get_description_try_do(self) -> str:
        """Get the description for try-do. By default, returns self._get_description_redo"""
        return self._get_description_redo()

    @override_required
    def _get_description_redo(self) -> str:
        """Must return a string that describes the do/redo action. Used when the action is done or redone."""
        raise NotImplementedError

    @override_required
    def _get_description_undo(self) -> str:
        """Must return a string that describes the undo action. Used when the action is undone."""
        raise NotImplementedError

    @override_required
    def _get_redo_cb(self) -> BackendCallable:
        """
        Derived class must override this to return a callable that implements the do/redo action and will
        be run in the backend thread. The return values of the callable will be given to self._on_redo_success().
        :return: the callable, to be run in backend by UndoCommandBase, implementing the reverse action
        """
        raise NotImplementedError

    @override_required
    def _get_undo_cb(self) -> BackendCallable:
        """
        Derived class must override this to return a callable that implements the undo action and will
        be run in the backend thread. The return values of the callable will be given to self._on_undo_success().
        :return: the callable, to be run in backend by UndoCommandBase, implementing the reverse action
        """
        raise NotImplementedError

    @override_optional
    def _on_redo_success(self, *args):
        """
        If special action needs to be taken on return value of redo callback, override this
        :param args: the values returned by the redo callback
        """
        pass

    @override_optional
    def _on_undo_success(self, *args):
        """
        If special action needs to be taken on return value of undo callback, override this.
        :param args: the values returned by the undo callback
        """
        pass

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __async_redo_success(self, *args):
        """
        Method called when the redo operation succeeds.
        :param args: the values returned by the redo callback
        """
        qApp.restoreOverrideCursor()
        self._on_redo_success(*args)

    def __async_undo_success(self, *args):
        """
        Method called when the undo operation succeeds.
        :param args: the values returned by the undo callback
        """
        qApp.restoreOverrideCursor()
        self._on_undo_success(*args)

    def __async_redo_fail(self, exc: AsyncErrorInfo):
        """
        Method called when the redo operation fails.
        :param exc: Object containing information as to why the asynchronous redo call failed.
        """
        qApp.restoreOverrideCursor()
        msg = "Action failed ({}), nothing changed".format(exc.msg)
        exec_modal_dialog("Async Redo Call Error", msg, QMessageBox.Critical)
        log.error(exc.msg)
        log.debug(exc.traceback)

    def __async_undo_fail(self, exc: AsyncErrorInfo):
        """
        Method called when the undo operation fails.
        :param exc: Object containing information as to why the asynchronous undo call failed.
        """
        qApp.restoreOverrideCursor()
        exec_modal_dialog("Async Undo Call Error", "Undo action failed ({}), nothing undone".format(exc.msg),
                          QMessageBox.Critical)
        log.error(exc.msg)
        log.debug(exc.traceback)


class UndoStackExt(QUndoStack):
    """
    This class extends the base Undo/Redo functionality of Qt with the following:
    - before an action is undone, change to the actor 2d panel actor/viewport that was in place at the time
      an undo/redo command was pushed onto the stack (if the viewport was changed); the user has to control-Z
      a second time for the command to be undo/redone; some commands activate a different viewport from default
    - handle failed action: it does not get put on the stack
    - manage two QActions: one for undo, and the other for redo, so the GUI always knows whether the stack has
      actions that can be done or undone.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    CENTRE_TOLERANCE_PIX = 20

    # ---------------------------- instance PUBLIC methods -------------------------------

    def __init__(self):
        super().__init__()
        self.__actor_2d_panel = None

        self.__action_redo = self.createRedoAction(self.__actor_2d_panel)
        config_action(self.__action_redo,
                      tooltip='Redo the previous action',
                      pix_path=":/icons/redo.png",
                      shortcut='Ctrl+Y',
                      )

        self.__action_undo = self.createUndoAction(self.__actor_2d_panel)
        config_action(self.__action_undo,
                      tooltip='Undo the previous action',
                      pix_path=":/icons/undo.png",
                      shortcut='Ctrl+Z',
                      )

        self.__action_redo.triggered.disconnect()
        self.__action_undo.triggered.disconnect()
        self.__action_redo.triggered.connect(self.__slot_on_action_redo)
        self.__action_undo.triggered.connect(self.__slot_on_action_undo)

        self.setActive(False)

    @override(QUndoStack)
    def setActive(self, state: bool) -> str:
        super().setActive(state)
        if state:
            self.__action_redo.setEnabled(self.canRedo())
            self.__action_undo.setEnabled(self.canUndo())
        else:
            self.__action_redo.setEnabled(False)
            self.__action_undo.setEnabled(False)

    def get_action_undo(self) -> QAction:
        """
        Get the undo QAction. Menus and toolbars that use this action will automatically show the correct
        enabled/disabled state. The action state must not be modified by the caller.
        """
        return self.__action_undo

    def get_action_redo(self) -> QAction:
        """
        Get the redo QAction. Menus and toolbars that use this action will automatically show the correct
        enabled/disabled state. The action state must not be modified by the caller.
        """
        return self.__action_redo

    def get_actor_2d_panel(self):
        """
        Get the Actor 2d Panel.
        :return:  The 2d panel.
        """
        return self.__actor_2d_panel

    def set_actor_2d_panel(self, value: Decl.Actor2dPanel):
        """
        Get the Actor 2d Panel.
        """
        self.clear()
        self.__actor_2d_panel = value

    @override(QUndoStack)
    def push(self, command: UndoCommandBase):
        """
        Pushes the command to the stack if the command executes successfully and tracks ViewportObjects in the stack.

        Calls the commands redo() method with a result callback argument, defined herein, which is called by the command
        with a success flag argument. Success is either True if the commanded executed successfully or False otherwise
        (command raised exceptions). If success is True, the command will be pushed to the stack. Otherwise, the command
        is not added if the callback is called with a False argument.

        Regarding viewport objects, the stack is used to determine whether or not the Actor 2d View needs to pan
        during a redo/undo operation.
        """
        assert self.isActive()
        if self.__actor_2d_panel is not None:
            command.save_view_context(self.__actor_2d_panel.current_actor,
                                      self.__actor_2d_panel.view.get_current_viewport())

        # Try the command; it will be pushed to the stack only if successful
        command.set_on_async_done_notify(self.__on_async_cmd_done)
        self.setActive(False)
        command.try_do()

    @override(QUndoStack)
    def redo(self):
        """
        Overridden redo method solely for the purposes of panning prior to a redo operation
        (in case user has panned within the Actor 2d Scene).  The default is None in the case
        where no Viewport changes have happened (so it is a straight call to the redo() in the base class).
        """
        if self.__actor_2d_panel is None:
            return

        # if the viewport is different, then that is when we want to pan.
        if self.index() == self.count():
            command = self.command(self.index() - 1)
        else:
            command = self.command(self.index())

        if self.__check_same_viewport(command):
            self.setActive(False)
            super().redo()
            self.__actor_2d_panel.on_command_redone(command)
        else:
            log.info("REDO: Restoring view for next redo command (will be: {})", command._get_description_redo())
            # Design decision note:
            # This is caused by automatic view change driven by the redo of a regular command, which
            # belongs to the UndoStackExt. We do not call self.__actor_2d_panel.nav_to_actor here because
            # that function is intended to manage the view navigation driven by a direct user action, such as a mouse
            # drag on the canvas.
            self.__actor_2d_panel.set_content_actor(command.view_actor,
                                                    center=command.view_position,
                                                    zoom_factor=command.view_zoom_factor)

    @override(QUndoStack)
    def undo(self):
        """
        Overridden undo method solely for the purposes of panning prior to an undo operation
        (in case user has panned within the Actor 2d Scene).
        """
        if self.__actor_2d_panel is None:
            return

        if self.index() == 0:
            return

        # if the viewport is different, then that is when we want to pan.
        idx = self.index() - 1  # because for undo, it's the command previous to index that will be undone
        command = self.command(idx)
        if self.__check_same_viewport(command):
            self.setActive(False)
            super().undo()
            self.__actor_2d_panel.on_command_undone(command)
        else:
            log.info("UNDO: Restoring view for next undo command: {}", command._get_description_undo())
            # Design decision note:
            # This is caused by automatic view change driven by the undo of a regular command, which
            # belongs to the UndoStackExt. We do not call self.__actor_2d_panel.nav_to_actor here because
            # that function is intended to manage the view navigation driven by a direct user action, such as a mouse
            # drag on the canvas.
            self.__actor_2d_panel.set_content_actor(command.view_actor,
                                                    center=command.view_position,
                                                    zoom_factor=command.view_zoom_factor)

    def find_previous_command(self, *cls: UndoCommandBase) -> UndoCommandBase:
        """
        Get the most recent command *older* than current undo stack index.
        :param cls: list of classes to find
        :return: the command object, or None if none found (i.e. if cls empty, or if no command object found
            that matches any of the given classes)
        """
        # we want a command that has not been undone yet (see self.index() in Qt docs):
        start_index = self.index() - 1
        # go down the stack till reach bottom
        for cmd_index in range(start_index, -1, -1):
            command = self.command(cmd_index)
            if isinstance(command, cls):
                return command

        # have not found any:
        return None

    # ---------------------------- instance PUBLIC properties ----------------------------

    actor_2d_panel = property(get_actor_2d_panel, set_actor_2d_panel)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_async_cmd_done(self, cmd: QUndoCommand, event: UndoEventEnum):
        """
        Try-do on cmd has succeeded, so push it onto the stack, knowing that its redo() will do nothing
        until its undo() has been called at least once (because that's how UndoCommandBase is designed).
        """
        self.setActive(True)
        if event == UndoEventEnum.try_do_success:
            # DO NOT call self.push(), infinite recursion because it calls this method
            super().push(cmd)

    def __check_same_viewport(self, command: UndoCommandBase) -> bool:
        """
        This method is used to determine whether not we are looking at the viewport prior to doing
        a redo/undo operation (ie the viewport is the same as that when the redo or undo operation occurred).
        If a user has panned away from a point in the Actor 2d Scene after performing
        a command (ie add part), then this method will tell us whether or not we need to pan back to the
        point in the Actor 2d Scene where the command (ie add part) occurred.
        :param command: The command for the undo/redo
        :return: True if current viewport matches current stack viewport
        """
        actual_position, actual_zoom_factor = self.__actor_2d_panel.view.get_current_viewport()
        same_viewport = (self.__is_part_same(command.view_actor, self.__actor_2d_panel.current_actor) and
                         self.__is_scale_same(command.view_zoom_factor, actual_zoom_factor) and
                         self.__are_positions_same(command.view_position, actual_position))

        return same_viewport

    def __is_part_same(self, part1: ActorPart, part2: ActorPart) -> bool:
        """
        Accessory method to determine if two parts are the same.
        :param part1: First part to compare.
        :param part2: Second part to compare.
        :return: Boolean indicating whether or not the two parts are the same.
        """
        if part1 == part2:
            return True
        else:
            return False

    def __is_scale_same(self, scale1: float, scale2: float) -> bool:
        """
        Accessory method to determine if two scales are the same.
        :param scale1: First scale to compare.
        :param scale2: The scale value from the part to compare.
        :return: Boolean indicating whether or not the two scales are the same.
        """
        if scale2 is None:
            normalized_value = self.actor_2d_panel.view.DEFAULT_ZOOM_SLIDER_VALUE
        else:
            normalized_value = scale2

        if scale1 == normalized_value:
            return True
        else:
            return False

    def __are_positions_same(self, pos1: Position, pos2: Position) -> bool:
        """
        Accessory method to determine if two positions have equivalent x, y, and z coordinates.
        :param pos1: First position to compare.
        :param pos2: The position from the part to compare.
        :return: Boolean indicating whether or not the two positions are the same.
        """
        if pos2 is None:
            normalized_value = Position(0.0, 0.0)
        else:
            normalized_value = pos2
        # Qt's centerOn and reading back the viewport center have a small discrepancy. We use this mechanism
        # to deal with it.
        delta = QPointF(pos1.x, pos1.y) - QPointF(normalized_value.x, normalized_value.y)
        if delta.manhattanLength() < UndoStackExt.CENTRE_TOLERANCE_PIX:
            return True
        else:
            return False

    def __on_action_undo(self):
        scene_undo_stack().undo()

    def __on_action_redo(self):
        scene_undo_stack().redo()

    __slot_on_action_undo = safe_slot(__on_action_undo)
    __slot_on_action_redo = safe_slot(__on_action_redo)


# ------------- Implemented actions ------------------------


class RemovePartCommand(UndoCommandBase):
    """
    This class represents a single Remove part action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' a Remove part action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part: BasePart, view_is_parent: bool = False):
        super().__init__(view_is_parent=view_is_parent)
        self._parent_part = part.parent_actor_part
        self._part = part

        # The first successful try_do() will set these as result of the async request:
        self._restore_part_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting removal of part {} from {}'.format(self._part, self._parent_part)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting unremoval of {} in {}'.format(self._part, self._parent_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        log.debug("Do or redo part removal for part {}", self._part)
        return lambda: self._parent_part.remove_child_part(self._part, restorable=True)

    @override(UndoCommandBase)
    def _on_redo_success(self, restore_part_info: RestorePartInfo):
        log.debug("Scene successfully removed part {}", self._part)
        self._restore_part_info = restore_part_info

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        log.debug("Undo part removal for part {}", self._part)
        restore_info = self._restore_part_info
        return lambda: self._parent_part.restore_child_part(self._part, restore_info)

    @override(UndoCommandBase)
    def _on_undo_success(self, *args):
        log.debug("Scene successfully undid removal of part {}", self._part)


class AddPartCommand(UndoCommandBase):
    """
    This class represents a single Add part action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' an Add part action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.

    NOTE: Adding a part such that it is undoable is actually tricky because a link is created based on two endpoint
    references to other actors. So if you add part A, add part B, create link from A to B, then undo link creation,
    then undo part B creation, then redo B creation, and finally try to redo the link creation, then if B is totally
    new part (rather than a "restored" part that was deleted), the link will reference the "old" B rather than the
    re-created B. If we were using unique ID's for these operations, instead of references to parts, this undoable
    command would not need restorable=True, as long as the unique ID counting also backtracked when a part was
    uncreated so that when it is recreated it gets the same ID.
    """

    def __init__(self, parent_part: ActorPart, part_type: str, position: Position = None):
        """
        :param parent_part:  The parent actor part into which a new part is being added.
        :param part_type:  The type of part to add to the parent_part.
        """
        super().__init__()
        self._part_type = part_type
        self._parent_part = parent_part
        self._position = Position() if position is None else position.copy()

        # The first successful try_do() will set these as result of the async request: 
        self._part = None

        # The undo() will set these as a result of async request:
        self._restore_part_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting creation of part of type {} in {} at pos={:.5}'.format(
            self._part_type, self._parent_part, self._position)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting uncreation of {} (type {}) in {}'.format(self._part, self._part_type, self._parent_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        position = self._position

        if self._part is None:
            log.debug("Do part creation, type {}", self._part_type)
            return lambda: self._parent_part.create_child_part(self._part_type, pos=position)

        log.debug("Re-do part creation for part {}", self._part)
        part = self._part
        restore_part_info = self._restore_part_info
        return lambda: self._parent_part.restore_child_part(part, restore_part_info)

    @override(UndoCommandBase)
    def _on_redo_success(self, result):
        if self._part is None:
            self._part = result
            log.debug("Part creation succeeded, part {}", self._part)

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        log.debug("Undoing part creation of part {}", self._part)
        part = self._part
        return lambda: self._parent_part.remove_child_part(part, restorable=True)

    @override(UndoCommandBase)
    def _on_undo_success(self, restore_part_info: RestorePartInfo):
        log.debug("Undo of part {} creation succeeded", self._part)
        self._restore_part_info = restore_part_info


class RenamePartCommand(UndoCommandBase):
    """
    This class represents a single Rename part action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' a Rename-Part action.
    """

    def __init__(self, part: BasePart, name: str):
        """
        :param part:  The part that is being renamed.
        :param name:  The part's new name.
        """
        super().__init__()
        self._part = part
        self._previous_name = part.part_frame.name
        self._new_name = name

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting part rename {} -> {}'.format(self._previous_name, self._new_name)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting part (un)rename {} -> {}'.format(self._new_name, self._previous_name)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        return lambda: self._part.part_frame.set_name(self._new_name)

    @override(UndoCommandBase)
    def _get_undo_cb(self):
        return lambda: self._part.part_frame.set_name(self._previous_name)


class CreateLinkCommand(UndoCommandBase):
    """
    This class represents a single Create link action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' the action of creating a link from one part frame
    to another part frame.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self,
                 from_part_frame: PartFrame,
                 to_part_frame: PartFrame,
                 link_name: str = None,
                 waypoint_positions: List[Position] = None):
        """
        :param from_part_frame:  The part frame from which to create a link from.
        :param to_part_frame:  The part fame from which to create a link to (ie target part frame).
        :param link_name: The name of the link to be created. None: the system will generate a name.
        :param waypoint_positions: A list of waypoint 'Positions' in scenario coordinates.
        """
        super().__init__()
        self.__from_part_frame = from_part_frame
        self.__to_part_frame = to_part_frame
        self.__link_name = link_name
        self.__waypoints_pos = waypoint_positions

        # The first successful try_do() will set these as result of the async request:
        self._link = None
        # The undo will set these as a result of async request:
        self._restore_link_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting new link from {} -> {}'.format(self.__from_part_frame, self.__to_part_frame)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting unlink from {} -> {}'.format(self.__from_part_frame, self.__to_part_frame)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        if self._link is None:
            to_part_frame = self.__to_part_frame
            waypoint_pos = self.__waypoints_pos
            return lambda: self.__from_part_frame.create_link(to_part_frame,
                                                              link_name=self.__link_name,
                                                              waypoint_positions=waypoint_pos)
        link = self._link
        restore_link_info = self._restore_link_info
        return lambda: self.__from_part_frame.restore_outgoing_link(link, restore_link_info)

    @override(UndoCommandBase)
    def _on_redo_success(self, new_link: PartLink):
        if self._link is None:
            self._link = new_link

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        link = self._link
        return lambda: link.remove_self(restorable=True)

    @override(UndoCommandBase)
    def _on_undo_success(self, restore_link_info: RestoreLinkInfo):
        self._restore_link_info = restore_link_info


class RetargetLinkCommand(UndoCommandBase):
    """
    This class represents a single Retarget link action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' the action of changing a link's target from one part frame
    to another part frame.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_link: PartLink, new_target_frame: PartFrame):
        """
        :param part_link:  The part link to to retarget.
        :param new_target_frame:  The new part fame to connect.
        """
        super().__init__()
        self.__part_link = part_link
        self.__new_target_frame = new_target_frame

        # The first successful try_do() will set these as result of the async request:
        self.__restore_link_info = None  # RestoreLinkInfo

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting retargeting of link {} to new target {}'.format(
            self.__part_link, self.__new_target_frame)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting unretargeting of link {} to original target {}'.format(
            self.__part_link, self.__restore_link_info.target_frame)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        new_target_frame = self.__new_target_frame
        return lambda: self.__part_link.retarget_link(new_target_frame)

    @override(UndoCommandBase)
    def _on_redo_success(self, restore_link_info: RestoreLinkInfo):
        self.__restore_link_info = restore_link_info

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        restore_link_info = self.__restore_link_info
        return lambda: self.__part_link.restore_retargeted_link(restore_link_info)


class RemoveLinkCommand(UndoCommandBase):
    """
    This class represents a single Remove link action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' a remove link action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, link_to_remove: PartLink):
        """
        :param link_to_remove:  The actual link to remove.
        """
        super().__init__()
        self._link = link_to_remove

        # The first successful try_do() will set these as result of the async request:
        self._restore_link_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting removal of link {}'.format(self._link)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting unremoval of link {}'.format(self._restore_link_info)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        return lambda: self._link.remove_self(restorable=True)

    @override(UndoCommandBase)
    def _on_redo_success(self, restore_link_info: RestoreLinkInfo):
        self._restore_link_info = restore_link_info

    @override(UndoCommandBase)
    def _get_undo_cb(self):
        restore_link_info = self._restore_link_info
        source_part_frame = restore_link_info.source_frame
        return lambda: source_part_frame.restore_outgoing_link(self._link, restore_link_info)


class RenameLinkCommand(UndoCommandBase):
    def __init__(self, link_to_rename: PartLink,
                 new_link_name: str,
                 ref_parts: TypeReferencingParts = None):
        """
        :param link_to_rename: Link to rename.
        :param new_link_name: New name of link.
        :param ref_parts: The structure that contains both the original scripts and the new scripts
        """
        super().__init__()
        self._original_link_name = link_to_rename.name
        self._link = link_to_rename
        self._new_link_name = new_link_name
        self.__map_parts_to_scripts = None

        if ref_parts is None:
            return

        # part -> (old script, new script)
        self.__map_parts_to_scripts = dict()
        for part, new_script in ref_parts:
            self.__map_parts_to_scripts[part] = (part.get_canonical_script(), new_script)

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting renaming of link {} from {} to {}'.format(
            self._link, self._original_link_name, self._new_link_name)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting unrenaming of link {} from {} back to {}'.format(
            self._link, self._new_link_name, self._original_link_name)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        return self.__change

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        def change():
            return self.__change(False)

        return change

    def __change(self, is_redo: bool = True):
        if is_redo:
            link_name = self._new_link_name
        else:
            link_name = self._original_link_name

        self._link.set_name(link_name)

        if self.__map_parts_to_scripts is None:
            return

        for part, (old_script, new_script) in self.__map_parts_to_scripts.items():
            if is_redo:
                part.set_canonical_script(new_script)
            else:
                part.set_canonical_script(old_script)


class DeclutterLinkCommand(UndoCommandBase):
    def __init__(self, link_to_declutter: PartLink, declutter: bool):
        """
        :param link_to_declutter: Link to change the declutter flag on.
        :param declutter: Declutter flag.
        """
        super().__init__()
        self.__link = link_to_declutter
        self.__declutter = declutter
        self.__original_declutter = not declutter

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting set declutter {} on link {}'.format(self.__declutter, self.__link)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting set declutter {} on link {}'.format(self.__original_declutter, self.__link)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        return lambda: self.__link.set_declutter(self.__declutter)

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        return lambda: self.__link.set_declutter(self.__original_declutter)


class AddWaypointCommand(UndoCommandBase):
    """
    This class represents a single add Waypoint action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' an add Waypoint action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_link: PartLink, position: Position, index: int):
        """
        :param: part_link:  the link to which the waypoint is being added.
        :param: position: the position of the waypoint in scenario coordinates.
        :param: index: the ordered index of the waypoint starting closest to the source part frame.
        """
        super().__init__()
        self.__part_link = part_link
        self.__position = position
        self.__index = index

        # The first successful try_do() will set these as result of the async request:
        self.__waypoint = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting creation of waypoint after #{} on link {}, pos={:.5}'.format(
            self.__index, self.__part_link, self.__position)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting uncreation of waypoint after #{} on link {}'.format(self.__index, self.__part_link)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:

        if self.__waypoint is None:
            # Create a new waypoint
            position = self.__position
            index = self.__index
            return lambda: self.__part_link.add_waypoint(position, index)
        else:
            # The waypoint was created previously, restore it
            waypoint = self.__waypoint
            index = self.__index
            return lambda: self.__part_link.restore_waypoint(waypoint, index)

    @override(UndoCommandBase)
    def _on_redo_success(self, new_waypoint: LinkWaypoint):
        # Save new waypoint for undo
        if self.__waypoint is None:
            self.__waypoint = new_waypoint

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        # Remove the waypoint
        waypoint = self.__waypoint
        return lambda: self.__part_link.remove_waypoint(waypoint)


class RemoveWaypointCommand(UndoCommandBase):
    """
    This class represents a single remove Waypoint action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' a remove Waypoint action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_link: PartLink, waypoint: LinkWaypoint):
        """
        :param: part_link:  the link to which the waypoint is being removed.
        :param: waypoint: the waypoint to remove.
        """
        super().__init__()
        self.__part_link = part_link
        self.__waypoint = waypoint
        self.__index = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting removal of waypoint #{} on link {}'.format(self.__waypoint.wp_id, self.__part_link)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting restore of waypoint #{} on link {}'.format(self.__waypoint.wp_id, self.__part_link)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        waypoint = self.__waypoint
        return lambda: self.__part_link.remove_waypoint(waypoint)

    @override(UndoCommandBase)
    def _on_redo_success(self, waypoint_index: int):
        self.__index = waypoint_index

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        assert self.__index is not None
        waypoint = self.__waypoint
        index = self.__index
        return lambda: self.__part_link.restore_waypoint(waypoint, index)


class RemoveWaypointsCommand(UndoCommandBase):
    """
    This class represents a single remove Waypoint action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' a remove Waypoint action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, parent_actor: ActorPart, map_links_to_waypoints: Dict[PartLink, List[LinkWaypoint]]):
        """
        :param map_links_to_waypoints: A dictionary that contains a map of part links to associated list of waypoints
        """
        super().__init__()
        self.__map_links_to_waypoints = map_links_to_waypoints
        self.parent_actor = parent_actor
        self.__indices = []
        self.__description_string = ''
        self.set_description_string()

        # Sort the links before removing in order to ensure they get re-added in correct order on a undo
        for link in self.__map_links_to_waypoints.keys():
            self.__map_links_to_waypoints[link].sort(key=lambda waypoint: waypoint.wp_id)

    def set_description_string(self):
        """
        Sets the description string for the command
        """
        description = ''
        map_links_to_waypoints = self.__map_links_to_waypoints

        for link, waypoints in map_links_to_waypoints.items():
            description += 'Link: {}; waypoint IDs: '.format(link.name)
            description += ', '.join(str(wp.wp_id) for wp in waypoints)
            description += ' '

        self.__description_string = description

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        redo_description = 'Requesting removal of waypoints: ' + self.__description_string
        return redo_description

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        undo_description = 'Requesting unremoval of waypoints: ' + self.__description_string
        return undo_description

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        map_links_to_waypoints = self.__map_links_to_waypoints
        return lambda: [link.remove_waypoints(waypoints) for link, waypoints in map_links_to_waypoints.items()]

    @override(UndoCommandBase)
    def _on_redo_success(self, waypoint_indices: List[int]):
        if not self.__indices:
            self.__indices.extend(wp_indices for wp_indices, _ in waypoint_indices)

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        assert self.__indices is not None
        map_links_to_waypoints = self.__map_links_to_waypoints
        indices = self.__indices

        return lambda: self.parent_actor.restore_waypoints(map_links_to_waypoints, indices)


class RemoveAllWaypointsCommand(UndoCommandBase):
    """
    This class represents a single action to remove all waypoints from a link and initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' a 'remove all' waypoints action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_link: PartLink):
        """
        :param: part_link:  the link to which the waypoint is being removed.
        """
        super().__init__()
        self.__part_link = part_link
        self.__waypoints = part_link.waypoints[:]

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting removal of all waypoints on link {}'.format(self.__part_link)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting unremoval of all waypoints on link {}'.format(self.__part_link)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        link = self.__part_link
        return lambda: link.remove_all_waypoints()

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        link = self.__part_link
        waypoints = self.__waypoints
        return lambda: link.restore_all_waypoints(waypoints)


class WaypointPositionCommand(UndoCommandBase):
    """
    This class represents a single positioning action on one or more scenario waypoints.
    """

    def __init__(self, waypoints: List[LinkWaypoint], old_pos: List[Position], new_pos: List[Position]):
        """
        :param waypoint: List of waypoints to be positioned.
        :param old_pos: List of old positions of the waypoints to be positioned.
        :param new_pos: List of new positions of the waypoints to be positioned.
        """
        super().__init__()
        self.__waypoints = waypoints
        self.__old_pos = deepcopy(old_pos)  # want clones of Position objects too
        self.__new_pos = deepcopy(new_pos)

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        changes_str = self.__get_change_str(self.__old_pos, self.__new_pos)
        return 'Requesting position changes of: {}'.format(changes_str)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        changes_str = self.__get_change_str(self.__new_pos, self.__old_pos)
        return 'Requesting position restores of: {}'.format(changes_str)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:

        def update_backend_position():
            for waypoint, new_pos in zip(self.__waypoints, self.__new_pos):
                waypoint.set_position(new_pos.x, new_pos.y)

        return update_backend_position

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:

        def update_backend_position():
            for waypoint, old_pos in zip(self.__waypoints, self.__old_pos):
                waypoint.set_position(old_pos.x, old_pos.y)

        return update_backend_position

    def __get_change_str(self, old_pos: List[Position], new_pos: List[Position]) -> str:
        return ', '.join('waypoint {} from {:.5} to {:.5}'.format(w, op, np)
                         for (w, op, np) in zip(self.__waypoints, old_pos, new_pos))


class RemovePartsCommand(UndoCommandBase):
    """
    This class represents removal of multiple parts action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' removing parts action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, parts: List[BasePart], **clipboards):
        """
        :param parts:  The parts that are to be deleted.
        """
        super().__init__(**clipboards)
        self._parent_part = parts[0].parent_actor_part  # All parts in the list will have the same parent part.
        self._parts = parts

        # The first successful try_do() will set these as result of the async request:
        self._restore_parts_info = []

    def get_parts_restore_info(self) -> Tuple[List[BasePart], List[RestorePartInfo]]:
        return self._parts, self._restore_parts_info

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting removal of parts {} from {}'.format(parts_to_str(self._parts), self._parent_part)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting unremoval of parts {} from {}'.format(parts_to_str(self._parts), self._parent_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        parts_to_remove = self._parts
        parent_part = self._parent_part
        return lambda: parent_part.remove_child_parts(parts_to_remove, restorable=True)

    @override(UndoCommandBase)
    def _on_redo_success(self, restore_parts_info: List[RestorePartInfo]):
        self._restore_parts_info = restore_parts_info

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        parent_part = self._parent_part
        restore_parts_info = self._restore_parts_info
        parts = self._parts

        return lambda: parent_part.restore_child_parts(parts, restore_parts_info)


class CutPartsCommand(RemovePartsCommand):
    """
    Cut parts is no different from removing parts, because the clipboard is managed by the view.
    However, it is different from point of view of user, so descriptions different.
    """

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting cutting of parts {} from {}'.format(parts_to_str(self._parts), self._parent_part)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting uncutting of parts {} from {}'.format(parts_to_str(self._parts), self._parent_part)


class PastePartsCommand(UndoCommandBase):
    """
    There are multiple ways to paste parts, but they all must provide for a paste offset,
    so they must all derive from this class instead of directly from UndoCommandBase.
    """

    def __init__(self, paste_offset: Vector, **clipboards):
        super().__init__(**clipboards)
        self._paste_offset = paste_offset

    def get_paste_offset(self) -> Vector:
        return self._paste_offset

    def get_offset_str(self) -> str:
        dx, dy = self._paste_offset.x, self._paste_offset.y
        return '({:.5}, {:.5})'.format(dx, dy)


class IPasteFromCut:
    """
    Paste-from-cut commands must derive from this interface class so they all provide the same services.
    """

    @staticmethod
    def is_reparent(new_parent: ActorPart, parts: List[BasePart], restore_parts_info: List[RestorePartInfo]) -> bool:
        """
        Return True if the new_parent is the same as the original parent of all the parts
        :param new_parent: new parent to assume
        :param parts: parts to restore
        :param restore_parts_info: their restoration info
        :return: True if the paste is a reparent
        """
        first_orig_parent = restore_parts_info[0].parent_part
        reparent = (first_orig_parent is not new_parent)

        # do check on all parts, by checking that they all have the same original parent:
        for part, restore in zip(parts, restore_parts_info):
            assert restore.parent_part is first_orig_parent

        return reparent


class PasteCutPartsCommand(PastePartsCommand, IPasteFromCut):
    """
    This class represents a single 'Paste' of one or more CUT parts when they remain in their
    original actor (see ReparentCutPartsCommand to handle pasting into a different actor).
    """

    def __init__(self, new_parent: BasePart, parts: List[BasePart], restore_infos: List[RestorePartInfo],
                 paste_offset: Vector = Vector(), **clipboards):
        """
        :param new_parent:  The actor into which the 'parts' are to be pasted into.  This actor becomes the
            parent of the 'parts' that are being pasted.
        :param parts:  The part(s) that are to be pasted.
        :param restore_infos: restoration info for each part to be paste (same order as parts)
        :param paste_offset: The position offset (x, y) in scenario coordinates to apply when pasting each part relative
            to the copied part.
        """
        PastePartsCommand.__init__(self, paste_offset, **clipboards)
        self._parts_being_pasted = parts
        self._parent_part = new_parent
        self._restore_parts_info = restore_infos

        assert not self.is_reparent(new_parent, parts, restore_infos)

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting paste of CUT parts {} into SAME parent {} with offset {}'.format(
            parts_to_str(self._parts_being_pasted), self._parent_part, self.get_offset_str())

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting UNpaste of CUT parts {} (ie removal) from {}'.format(
            parts_to_str(self._parts_being_pasted), self._parent_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        parts = self._parts_being_pasted
        new_parent_part = self._parent_part
        restore_infos = self._restore_parts_info
        paste_offset = self._paste_offset

        return lambda: new_parent_part.restore_child_parts(parts, restore_infos, paste_offset=paste_offset)

    @override(UndoCommandBase)
    def _on_redo_success(self, result: UnrestorableLinks):
        assert not result.incoming
        assert not result.outgoing

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        parts = self._parts_being_pasted
        new_parent_part = self._parent_part
        restore_infos = self._restore_parts_info
        paste_offset = self._paste_offset

        def undo_cut_and_paste():
            new_parent_part.unrestore_child_parts(parts, restore_infos, paste_offset)

        return undo_cut_and_paste


class ReparentCutPartsCommand(PastePartsCommand, IPasteFromCut):
    """
    This class represents a single 'Paste' of one or more CUT parts, i.e. a reparenting of
    the parts to a different actor.
    """

    def __init__(self, new_parent: BasePart, parts: List[BasePart], restore_infos: List[RestorePartInfo],
                 maintain_links: bool, paste_offset: Vector = Vector(), **clipboards):
        """
        :param new_parent:  The actor into which the 'parts' are to be pasted into.  This actor becomes the
            parent of the 'parts' that are being pasted.
        :param parts:  The part(s) that are to be pasted.
        :param restore_infos: restoration info for each part to be paste (same order as parts)
        :param maintain_links: True to adjust links, False to break them
        :param paste_offset: The position offset (x, y) in scenario coordinates to apply when pasting each part relative
            to the copied part.
        """
        PastePartsCommand.__init__(self, paste_offset, **clipboards)
        self._parts_being_pasted = parts
        self._parent_part = new_parent
        self._restore_parts_info = restore_infos
        self._maintain_links = maintain_links

        # The first successful try_do() will set these as result of the async request:
        self._restore_noparent = None

        # check that they all had the same parent before they were cut, and that this parent is not the destination: 
        assert self.is_reparent(new_parent, parts, restore_infos)

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        msg = 'Requesting paste of CUT parts {} into NEW parent {}, maintain links={}, with offset {}'
        return msg.format(parts_to_str(self._parts_being_pasted), self._parent_part,
                          self._maintain_links, self.get_offset_str())

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting UNpaste of CUT parts {} (ie removal) from new parent {}'.format(
            parts_to_str(self._parts_being_pasted), self._parent_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        parts = self._parts_being_pasted
        new_parent_part = self._parent_part
        restore_infos = self._restore_parts_info
        paste_offset = self._paste_offset
        maintain_links = self._maintain_links
        return lambda: new_parent_part.reparent_child_parts(parts, restore_infos,
                                                            maintain_links=maintain_links,
                                                            paste_offset=paste_offset)

    @override(UndoCommandBase)
    def _on_redo_success(self, result: RestoreReparentInfo):
        if self._restore_noparent is None:
            # first time through, save the result
            self._restore_noparent = result
        else:
            # on subsequent redos, the result ought to be the same! at least check the keys:
            assert set(result.ifx_levels.keys()) == set(self._restore_noparent.ifx_levels.keys())

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        parts = self._parts_being_pasted
        new_parent_part = self._parent_part
        restore_noparent = self._restore_noparent
        assert self._restore_noparent is not None

        def undo_reparent_cut_parts():
            new_parent_part.unreparent_child_parts(parts, restore_noparent)

        return undo_reparent_cut_parts


class PasteCopiedPartsCommand(PastePartsCommand):
    """
    This class represents a single 'Paste' of one or more copied parts, initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' a Paste operation.
    """

    def __init__(self, actor_to_paste_into: BasePart, parts: List[BasePart],
                 paste_offset: Vector = Vector(), **clipboards):
        """
        :param actor_to_paste_into:  The actor into which the 'parts' are to be pasted into.  This actor becomes the
            parent of the 'parts' that are being pasted.
        :param parts:  The part(s) that are to be pasted.
        :param paste_offset: the position offset (x, y) in scenario coordinates to apply when pasting each part relative
            to the copied part.
        """
        PastePartsCommand.__init__(self, paste_offset, **clipboards)
        self._parts_being_pasted = parts
        self._parent_part = actor_to_paste_into

        # The first successful try_do() will set these as result of the async request:
        self._parts_created_from_paste_operation = None
        self._restore_parts_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting paste of COPIED parts {} into {} with offset {}'.format(
            parts_to_str(self._parts_being_pasted), self._parent_part, self.get_offset_str())

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting UNpaste of COPIED parts {} (ie removal) from {}'.format(
            parts_to_str(self._parts_created_from_paste_operation), self._parent_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        parts = self._parts_being_pasted
        parent_part = self._parent_part
        paste_offset = self._paste_offset

        if self._restore_parts_info is None:
            # first time, paste parts; the callback returns created parts:
            def paste_parts() -> List[BasePart]:
                return parent_part.copy_parts(parts, paste_offset=paste_offset)

            return paste_parts

        else:
            # after first time, restore the "unpasted" parts:
            parent_part = self._parent_part
            parts = self._parts_created_from_paste_operation
            info = self._restore_parts_info

            def restore_parts():
                parent_part.restore_child_parts(list(reversed(parts)), list(reversed(info)))

            return restore_parts

    @override(UndoCommandBase)
    def _on_redo_success(self, parts_created_from_paste_operation: List[BasePart]):
        if parts_created_from_paste_operation is not None:
            # then this is the first redo: parts created needs to be stored
            self._parts_created_from_paste_operation = parts_created_from_paste_operation

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        parts = self._parts_created_from_paste_operation

        def remove_parts() -> List[RestorePartInfo]:
            return [part.remove_self(restorable=True) for part in parts]

        return remove_parts

    @override(UndoCommandBase)
    def _on_undo_success(self, restore_part_info_list: List[RestorePartInfo]):
        self._restore_parts_info = restore_part_info_list


class PartEditorApplyChangesCommand(UndoCommandBase):
    """
    This class represents a single save action that can be initiated by a user from the GUI on a part editor.
    It contains logic that supports 'doing' and 'undoing' the action of saving a part editor.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    EditorData = Dict[str, Any]

    def __init__(self, part: BasePart, initial_data: EditorData, new_data: EditorData, order: List[str] = None):
        """
        :param part: The part to save the data for.
        :param initial_data: The initial set of data.
        :param new_data:  The data in the part editor after (potential) changes have been made in a part editor.
        """
        super().__init__()
        self.__undone_at_least_once = False
        self.__part = part
        self.__initial_data = initial_data
        self.__new_data = new_data
        self.__order = order

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting save of part {} edits'.format(self.__part)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting restore of part {} to state prior to last edits'.format(self.__part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        def receive_submitted_data():
            if self.__undone_at_least_once:
                self.__part.receive_edited_snapshot(self.__new_data, self.__order)

        return receive_submitted_data

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        def receive_submitted_data():
            self.__part.receive_edited_snapshot(self.__initial_data, self.__order)
            self.__undone_at_least_once = True

        return receive_submitted_data


class ResizeCommand(UndoCommandBase):
    """
    This class represents a single resize action that can be initiated by a user from the 2D view.
    It contains logic that supports 'doing' and 'undoing' the action of resizing.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_frame: PartFrame, old_size: Size, new_size: Size):
        """
        :param part_frame: The part frame to be re-sized.
        :param old_size: The old size.
        :param new_size:  The new size.
        """
        super().__init__()
        self.__part_frame = part_frame
        self.__old_size = old_size
        self.__new_size = new_size

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting size change of part {} from {:.5} to {:.5}'.format(
            self.__part_frame, self.__old_size, self.__new_size)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting size restore of part {} from {:.5} back to {:.5}'.format(
            self.__part_frame, self.__new_size, self.__old_size)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        def update_backend_part_frame_size():
            self.__part_frame.set_size(self.__new_size.width, self.__new_size.height)

        return update_backend_part_frame_size

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        def update_backend_part_frame_size():
            self.__part_frame.set_size(self.__old_size.width, self.__old_size.height)

        return update_backend_part_frame_size


class ChangeDetailLevelCommand(UndoCommandBase):
    """
    This class represents a single minimize action that can be initiated by a user from the 2D view.
    It contains logic that supports 'doing' and 'undoing' the action of "minimize".
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_frame: PartFrame, detail_level: DetailLevelEnum):
        """
        :param part_frame: The part frame to show minimal or full detail level.
        :param detail_level: The detail level to be.
        """
        super().__init__()
        self.__part_frame = part_frame
        self.__detail_level = detail_level

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting detail level change of part {} to {}'.format(
            self.__part_frame, str(self.__detail_level))

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        if self.__detail_level == DetailLevelEnum.minimal:
            detail_level = DetailLevelEnum.full
        else:
            detail_level = DetailLevelEnum.minimal

        return 'Requesting detail level restore of part {} back to {}'.format(
            self.__part_frame, str(detail_level))

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        def change_detail_level():
            self.__part_frame.set_detail_level(self.__detail_level)

        return change_detail_level

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        def change_detail_level():
            if self.__detail_level == DetailLevelEnum.minimal:
                detail_level = DetailLevelEnum.full
            else:
                detail_level = DetailLevelEnum.minimal

            self.__part_frame.set_detail_level(detail_level)

        return change_detail_level


class PartsPositionsCommand(UndoCommandBase):
    """
    This class represents a single positioning action on one or more scenario parts.
    """

    def __init__(self, parts: List[BasePart], old_pos: List[Position], new_pos: List[Position]):
        """
        :param parts: The parts to be positioned.
        :param old_pos: The old positions of the parts to be positioned.
        :param new_pos: The new positions of the parts to be positioned.
        """
        super().__init__()
        self.__parts = parts
        self.__old_pos = deepcopy(old_pos)  # want clones of Position objects too
        self.__new_pos = deepcopy(new_pos)

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        changes_str = self.__get_change_str(self.__old_pos, self.__new_pos)
        return 'Requesting position changes of: {}'.format(changes_str)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        changes_str = self.__get_change_str(self.__new_pos, self.__old_pos)
        return 'Requesting position restores of: {}'.format(changes_str)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        def update_backend_position():
            for part, new_pos in zip(self.__parts, self.__new_pos):
                part.part_frame.set_position(new_pos.x, new_pos.y)

        return update_backend_position

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        def update_backend_position():
            for part, old_pos in zip(self.__parts, self.__old_pos):
                part.part_frame.set_position(old_pos.x, old_pos.y)

        return update_backend_position

    def __get_change_str(self, old_pos: List[Position], new_pos: List[Position]) -> str:
        return ', '.join('part {} from {:.5} to {:.5}'.format(p, op, np)
                         for (p, op, np) in zip(self.__parts, old_pos, new_pos))


class ParentProxyPositionCommand(UndoCommandBase):
    """
    This class represents a positioning action on the parent actor proxy of the 2d view. The part
    is the actor itself.
    """

    def __init__(self, part: ActorPart, old_proxy_pos: Position, new_proxy_pos: Position):
        """
        :param part: The actor for which proxy is to be moved
        :param old_proxy_pos: The old position of proxy of the actor
        :param new_proxy_pos: The new position of proxy of the actor
        """
        super().__init__()
        self.__actor_part = part
        self.__old_proxy_pos = deepcopy(old_proxy_pos)
        self.__new_proxy_pos = deepcopy(new_proxy_pos)

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting position change of parent {} proxy from {:.5} to {:.5}'.format(
            self.__actor_part, self.__old_proxy_pos, self.__new_proxy_pos)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting position restore of parent {} proxy from {:.5} back to {:.5}'.format(
            self.__actor_part, self.__new_proxy_pos, self.__old_proxy_pos)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        new_proxy_pos = self.__new_proxy_pos
        return lambda: self.__actor_part.set_proxy_pos(new_proxy_pos.x, new_proxy_pos.y)

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        old_proxy_pos = self.__old_proxy_pos
        return lambda: self.__actor_part.set_proxy_pos(old_proxy_pos.x, old_proxy_pos.y)


class ChangeIfxLevelCommand(UndoCommandBase):
    """
    This class represents a command to change the interface level of a part.
    Note: this command assumes that the user has elected to break links due to the ifx level change.
    """

    def __init__(self, part: BasePart, ifx_level: int):
        """
        :param part:  The interface level is being changed for this part.
        :param ifx_level:  The new interface level to set.
        """
        super().__init__()
        self.__part = part
        self.__ifx_level = ifx_level

        # The first successful try_do() will set these as result of the async request:
        self.__restore_ifx_level_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting interface level change of part {} frame from {} to {}'.format(
            self.__part, self.__part.part_frame.ifx_level, self.__ifx_level)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting interface level restore of part {} frame from {} back to {}'.format(
            self.__part, self.__ifx_level, self.__restore_ifx_level_info.from_level)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        part = self.__part
        ifx_level = self.__ifx_level

        def set_ifx_level() -> RestoreIfxLevelInfo:
            return part.part_frame.set_ifx_level(ifx_level, break_bad=True, restorable=True)

        return set_ifx_level

    @override(UndoCommandBase)
    def _on_redo_success(self, restore_ifx_level_info: RestoreIfxLevelInfo):
        self.__restore_ifx_level_info = restore_ifx_level_info

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        part = self.__part
        info = self.__restore_ifx_level_info

        def restore_ifx_level():
            return part.part_frame.restore_ifx_level(info)

        return restore_ifx_level


class SetPartPropertyCommand(UndoCommandBase):
    """
    The same undo'able command can be used for several part properties.
    """

    def __init__(self, part: BasePart, property_name: str,
                 property_value: bool or FrameStyleEnum or str or int or float):
        """
        :param part:  The part whose properties are being set.
        :param property_name:  The name of the property being set.
        :param property_value:  The value of the property being set.
        """
        super().__init__()
        self._part = part
        self._property_name = property_name
        self._new_value = property_value

        if self._property_name == 'frame_style':
            self._previous_value = part.part_frame.frame_style
        elif self._property_name == 'comment':
            self._previous_value = part.part_frame.comment
        else:
            raise ValueError('SetPartPropertyCommand Init Error: Invalid property value.')

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting property "{}" change on part {} from {} to {}'.format(
            self._property_name, self._part, self._previous_value, self._new_value)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting property "{}" restore on part {} from {} back to {}'.format(
            self._property_name, self._part, self._new_value, self._previous_value)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        if self._property_name == 'frame_style':
            return lambda: self._part.part_frame.set_frame_style(self._new_value)
        elif self._property_name == 'comment':
            return lambda: self._part.part_frame.set_comment(self._new_value)
        else:
            raise RuntimeError("BUG: should never get here because init should have caught issue")

    @override(UndoCommandBase)
    def _get_undo_cb(self):
        if self._property_name == 'frame_style':
            return lambda: self._part.part_frame.set_frame_style(self._previous_value)
        elif self._property_name == 'comment':
            return lambda: self._part.part_frame.set_comment(self._previous_value)
        else:
            raise RuntimeError("BUG: should never get here because init should have caught issue")


class FunctionPartToggleRoleCommand(UndoCommandBase):
    """
    This class represents a single action to set the role for a Function part as being either a startup/reset
    part (initiated by the user from the GUI).  It contains logic that supports 'doing' and 'undoing' the role that is
    set on a Function Part.
    QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, function_part: FunctionPart, role: RunRolesEnum, state: bool):
        """
        :param function_part: The function part to set a role for.
        :param role: The type of role to set (ie start-up, reset).
        :param state: Boolean indicating whether or not the state is to be assigned or removed.
        """
        super().__init__()
        self.__part = function_part
        self.__role = role
        self.__state = state
        self.__role_string = self.__role.name

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting role {} change on part {} to {}'.format(self.__role, self.__part, self.__state)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting role {} restore on part {} back to {}'.format(self.__role, self.__part, self.__state)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        log.debug("Setting {} role as '{}' for part '{}' (ID {})", self.__role_string, self.__state,
                  self.__part.name, self.__part.SESSION_ID)
        return lambda: self.__part.set_run_role(self.__role, self.__state)

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        log.debug("Setting {} role as '{}' for part '{}' (ID {})", self.__role_string, not self.__state,
                  self.__part.name, self.__part.SESSION_ID)
        return lambda: self.__part.set_run_role(self.__role, not self.__state)


class SwitchIfxPortSideCommand(UndoCommandBase):
    """
    This class represents a single port side switch action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' the action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_frame: PartFrame, actor_part: ActorPart):
        """
        :param part:  The part (port) that is switched from one side to the other.
        :param actor_part: The actor port that hosts the part.
        """
        super().__init__()
        self.__actor_part = actor_part
        self.__part_frame = part_frame

        # The first successful try_do() will set these as result of the async request:
        self.__restore_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting ifx port side switch for part {} on actor {}'.format(self.__part_frame, self.__actor_part)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting ifx port side restore for part {} on actor {}'.format(self.__part_frame, self.__actor_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        log.debug("Do or redo port switch for part {}", self.__part_frame)

        def __switch_ifx_port_side() -> RestoreIfxPortInfo:
            return self.__actor_part.switch_ifx_port_side(self.__part_frame)

        return __switch_ifx_port_side

    @override(UndoCommandBase)
    def _on_redo_success(self, restore_info: RestoreIfxPortInfo):
        self.__restore_info = restore_info

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        def __restore_ifx_port_side():
            return self.__actor_part.restore_ifx_port_side(self.__part_frame, self.__restore_info)

        return __restore_ifx_port_side


class VerticalMoveIfxCommand(UndoCommandBase):
    """
    This class represents a single port side switch action that can be initiated by a user from the GUI.
    It contains logic that supports 'doing' and 'undoing' the action.
    The QUndoCommand that this class derives from is the base class of all commands that are stored on a QUndoStack.
    """

    def __init__(self, part_frame: PartFrame, actor_part: ActorPart, move_direction: int):
        """
        :param part:  The part (port) that is switched from one side to the other.
        :param actor_part: The actor port that hosts the part.
        :param move_direction: The direction to move the port.
        """
        super().__init__()
        self.__actor_part = actor_part
        self.__part_frame = part_frame
        self.__direction = move_direction

        # The first successful try_do() will set these as result of the async request:
        self.__restore_info = None

    @override(UndoCommandBase)
    def _get_description_redo(self) -> str:
        return 'Requesting ifx port vertical move for part {} on actor {}'.format(self.__part_frame, self.__actor_part)

    @override(UndoCommandBase)
    def _get_description_undo(self) -> str:
        return 'Requesting ifx port vertical move restore for part {} on actor {}'.format(self.__part_frame,
                                                                                          self.__actor_part)

    @override(UndoCommandBase)
    def _get_redo_cb(self) -> BackendCallable:
        log.debug("Do or redo vertical port move for part {}", self.__part_frame)

        if self.__direction:
            def __vertical_move_ifx_port() -> RestoreIfxPortInfo:
                move_up_one = -1  # Moving up decreases index
                return self.__actor_part.move_ifx_port_index(self.__part_frame, move_up_one)
        else:
            def __vertical_move_ifx_port() -> RestoreIfxPortInfo:
                move_down_one = 1  # Moving down increases index
                return self.__actor_part.move_ifx_port_index(self.__part_frame, move_down_one)

        return __vertical_move_ifx_port

    @override(UndoCommandBase)
    def _on_redo_success(self, restore_info: RestoreIfxPortInfo):
        self.__restore_info = restore_info

    @override(UndoCommandBase)
    def _get_undo_cb(self) -> BackendCallable:
        def __restore_ifx_port_vertical_pos():
            return self.__actor_part.restore_ifx_port_index(self.__part_frame, self.__restore_info)

        return __restore_ifx_port_vertical_pos
