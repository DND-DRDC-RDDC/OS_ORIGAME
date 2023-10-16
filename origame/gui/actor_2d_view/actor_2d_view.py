# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Actor 2D View components

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import math
from collections import namedtuple
from enum import IntEnum, unique
from textwrap import dedent

# [2. third-party]
from PyQt5.QtCore import Qt, QMarginsF, QRect, QPointF, QRectF
from PyQt5.QtCore import pyqtSignal, QEvent
from PyQt5.QtGui import QMouseEvent, QWheelEvent, QContextMenuEvent, QKeyEvent, QPaintEvent, QPainter, QCursor
from PyQt5.QtWidgets import QMenu, QMessageBox, QGraphicsView, QAbstractSlider, QGraphicsItem
from PyQt5.QtWidgets import QScrollBar

# [3. local]
from ...core import override
from ...core.typing import Callable, AnnotationDeclarations
from ...core.typing import List, Tuple, Dict
from ...core.utils import plural_if, get_enum_val_name
from ...scenario.defn_parts import BasePart, ActorPart, PastablePartOri, Position, Vector, PartLink, RestoreLinkInfo
from ...scenario.defn_parts import get_registered_type_names, get_parents_map
from ...scenario.ori import OriContextEnum

from ..async_methods import AsyncRequest
from ..conversions import map_to_scenario, map_from_scenario
from ..gui_utils import exec_modal_dialog, PartAction
from ..safe_slot import safe_slot
from ..undo_manager import CutPartsCommand, PasteCopiedPartsCommand, PasteCutPartsCommand, ReparentCutPartsCommand
from ..undo_manager import scene_undo_stack, UndoCommandBase, IPasteFromCut

from .actor_2d_scene import Actor2dScene
from .common import CustomItemEnum, EventStr
from .part_box_item import PartBoxItem
from .view_nav_manager import NavToViewCmdTypeEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # defines module members that are public; one line per string
    'Actor2dView',
    'ViewActions',
    'EditActions',
    'ClipboardActionEnum'
]

log = logging.getLogger('system')

# The intent is to have consistent height for all the title bars.
DEFAULT_TITLE_BAR_HEIGHT = 20


class ButtonActionOnReparentEnum(IntEnum):
    """The index of each button shown in the Reparenting dialog when links need to be broken or endpoints adjusted"""
    break_ = 0
    adjust = 1
    cancel = 2


EditActions = namedtuple('EditActions', ['cut_action', 'copy_action', 'paste_action', 'delete_action', 'undo_action',
                                         'redo_action'])

ViewActions = namedtuple('ViewActions', ['action_override_full', 'action_override_minimal', 'action_override_none',
                                         'action_zoom_to_fit_all', 'action_zoom_to_selection'])

_bare = ButtonActionOnReparentEnum
BUTTONS_ADJUST_BAD_LINKS_ON_MOVE = [(), (), ()]
BUTTONS_ADJUST_BAD_LINKS_ON_MOVE[_bare.break_] = ("Break", QMessageBox.AcceptRole)
BUTTONS_ADJUST_BAD_LINKS_ON_MOVE[_bare.adjust] = ("Adjust", QMessageBox.AcceptRole)
BUTTONS_ADJUST_BAD_LINKS_ON_MOVE[_bare.cancel] = ("Cancel", QMessageBox.RejectRole)


class Decl(AnnotationDeclarations):
    ViewClipboard = 'ViewClipboard'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------


@unique
class ClipboardActionEnum(IntEnum):
    """The first paste after a cut is a move, whereas subsequent pastes are copy operations"""
    copy, cut = range(2)
    paste_from_copy, paste_from_cut, paste_from_pasted_cut = range(3, 6)


class ViewClipboard:
    """
    Represents a parts clipboard of the Actor 2d View. The clipboard should never be modified once
    created**; rather, a new clipboard instance should be created. This is important so that undo/redo
    can work properly with paste offsets.

    ** Note: The only exception is when the clipboard is used to transfer parts from one scenario to another
       (see replace_by_ori()).
    """

    PASTE_OFFSET_DELTA = Vector(1.0, -1.0)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, action: ClipboardActionEnum, parts: List[BasePart], center: Position,
                 paste_pos: Position = None):
        """
        :param action: which action is this clipboard being created for
        :param parts: the parts to put in this clipboard
        :param center: the center of the group of parts
        :param paste_pos: (if action is one of the paste actions) the paste position
        """
        assert parts
        self.__parts = parts
        self.__prev_paste_pos = paste_pos
        self.__center_pos = center
        if action in (ClipboardActionEnum.copy, ClipboardActionEnum.paste_from_copy):
            self.__next_paste_action = ClipboardActionEnum.paste_from_copy

        elif action is ClipboardActionEnum.cut:
            self.__next_paste_action = ClipboardActionEnum.paste_from_cut

        elif action is ClipboardActionEnum.paste_from_cut:
            self.__next_paste_action = ClipboardActionEnum.paste_from_pasted_cut

        else:
            assert action is ClipboardActionEnum.paste_from_pasted_cut
            self.__next_paste_action = ClipboardActionEnum.paste_from_copy

        log.debug("Clipboard action {}: next paste action will be {}",
                  get_enum_val_name(action).capitalize(),
                  get_enum_val_name(self.__next_paste_action).capitalize())
        self.show_next_paste_action()

    def show_next_paste_action(self):
        """Show what will happen the next time a paste occurs from this clipboard"""
        if self.__next_paste_action is ClipboardActionEnum.paste_from_cut:
            log.info("Next paste action will be a parts MOVE")
        else:
            log.info("Next paste action will be a parts COPY")

    @property
    def parts(self) -> List[BasePart]:
        """Get the parts on the clipboard"""
        return self.__parts

    @property
    def next_paste_action(self) -> ClipboardActionEnum:
        """Get the enum object representing the action that will be taken on paste"""
        return self.__next_paste_action

    def paste_parts(self, paste_pos: Position, new_parent: ActorPart) -> Decl.ViewClipboard:
        """
        Paste parts at a certain position in new parent.
        :param paste_pos: position at which to paste the group of parts in the clipboard
        :param new_parent: the parent in which to paste the parts
        :return: a new instance of clipboard that represents clipboard after pasting
        """
        if self.__next_paste_action == ClipboardActionEnum.paste_from_cut:
            return self.__paste_cut_parts(paste_pos, new_parent)
        else:
            assert self.__next_paste_action in (
                ClipboardActionEnum.paste_from_copy, ClipboardActionEnum.paste_from_pasted_cut)
            return self.__paste_copied_parts(paste_pos, new_parent)

    def replace_by_ori(self, on_replacement_done_cb: Callable[[], None]):
        """
        Replace the parts in this clipboard by their PastablePartOri representation so they can be copied to
        another scenario. This is an asynchronous method (it will complete only once the backend has provided
        the PastablePartOri instances).
        :param on_replacement_done_cb: callback to call once the asynchronous replacement is done.
        """
        old_clipboard = self.__parts
        clipboard_empty = not old_clipboard
        if clipboard_empty or isinstance(old_clipboard[0], PastablePartOri):
            # If clipboard not empty, assume this means clipboard contents already replaced in a previous call
            # to this method (as would happen if copy from scenario, new scenario, paste, save, new scenario
            # again, then paste again). Either way (empty or already converted), so nothing else to do except
            # the done callback:
            if on_replacement_done_cb:
                on_replacement_done_cb()
            return

        def get_new_clipboard_ori(clipboard) -> List[PastablePartOri]:
            new_ori_clipboard = []
            for orig_part in clipboard:
                ori_part = PastablePartOri(orig_part)
                ori_def = orig_part.get_ori_def(context=OriContextEnum.copy)
                ori_part.set_from_ori(ori_def, context=OriContextEnum.copy)
                new_ori_clipboard.append(ori_part)

            return new_ori_clipboard

        def on_new_clipboard(new_ori_clipboard: List[PastablePartOri]):
            log.debug('Parts clipboard replaced by pastable ORI for new scenario')
            # WARNING: this is the only acceptable mutation of this clipboard
            self.__prev_paste_pos = None
            self.__parts = new_ori_clipboard
            self.__next_paste_action = ClipboardActionEnum.paste_from_copy
            self.show_next_paste_action()
            if on_replacement_done_cb:
                on_replacement_done_cb()

        if self.__next_paste_action != ClipboardActionEnum.paste_from_cut:
            assert self.__next_paste_action in (
                ClipboardActionEnum.paste_from_copy, ClipboardActionEnum.paste_from_pasted_cut)
            AsyncRequest.call(get_new_clipboard_ori, old_clipboard, response_cb=on_new_clipboard)
            return

        # the clipboard has parts that have been removed (cut) the from the scenario, so links and ifx info missing
        # and must be restored first; we do this by creating a temporary scenario:

        # the link and ifx level restoration info is in the last cut command:
        prev_cut_cmd = scene_undo_stack().find_previous_command(CutPartsCommand)
        parts_to_reparent, parts_restore_info = prev_cut_cmd.get_parts_restore_info()

        # restore the cut parts, which don't have links any more, into a temporary actor that just *appears*
        # to be in a scenario; this actor will resolve all linkages and ifx info to all depths
        def copy_cut_parts() -> List[PastablePartOri]:
            class MockScenario:
                def __init__(self, shared_scen_state):
                    self.shared_scenario_state = shared_scen_state

            shared_scenario_state = parts_to_reparent[0].shared_scenario_state
            ghost_root = ActorPart(MockScenario(shared_scenario_state))
            ghost_root.reparent_child_parts(parts_to_reparent, parts_restore_info, maintain_links=False)
            return get_new_clipboard_ori(ghost_root.children)

        AsyncRequest.call(copy_cut_parts, response_cb=on_new_clipboard)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __paste_cut_parts(self, paste_pos: Position, new_parent: ActorPart) -> Decl.ViewClipboard:
        log.debug("Pasting from cut parts (i.e., move; subsequent pastes will be copies)")
        assert self.__next_paste_action == ClipboardActionEnum.paste_from_cut

        prev_cut_cmd = scene_undo_stack().find_previous_command(CutPartsCommand)
        if prev_cut_cmd is None:
            # the only way this is possible is that the parts were cut from the previous scenario;
            # Try pasting parts from the clipboard as copies
            assert self.__prev_paste_pos is None
            assert self.__next_paste_action is ClipboardActionEnum.paste_from_copy
            return self.__paste_copied_parts(paste_pos)

        parts_to_paste, restore_parts_info = prev_cut_cmd.get_parts_restore_info()
        assert self.__prev_paste_pos is None
        paste_offset = self.__calculate_paste_offset(paste_pos)
        moved_center_pos = self.__center_pos + paste_offset

        if not PasteCutPartsCommand.is_reparent(new_parent, parts_to_paste, restore_parts_info):
            clipboard_after_redo = ViewClipboard(ClipboardActionEnum.paste_from_cut,
                                                 self.__parts, moved_center_pos, paste_pos=paste_pos)
            cmd = PasteCutPartsCommand(new_parent, parts_to_paste, restore_parts_info,
                                       paste_offset=paste_offset,
                                       clipboard_after_redo=clipboard_after_redo,
                                       clipboard_after_undo=self)
            scene_undo_stack().push(cmd)
            return clipboard_after_redo

        # reparenting requires asking user for instructions, deal with it:
        bad_links = new_parent.check_links_restoration(parts_to_paste, restore_parts_info)
        proceed = True
        maintain_links = True
        if bad_links:
            answer = self.__check_break_adjust_ifx(bad_links)
            if answer == ButtonActionOnReparentEnum.cancel:
                proceed = False
            elif answer == ButtonActionOnReparentEnum.break_:
                maintain_links = False
            else:
                assert answer == ButtonActionOnReparentEnum.adjust

        if proceed:
            clipboard_after_redo = ViewClipboard(ClipboardActionEnum.paste_from_cut,
                                                 parts_to_paste, moved_center_pos, paste_pos=paste_pos)
            cmd = ReparentCutPartsCommand(new_parent, parts_to_paste, restore_parts_info, maintain_links,
                                          paste_offset=paste_offset,
                                          clipboard_after_redo=clipboard_after_redo,
                                          clipboard_after_undo=self)
            scene_undo_stack().push(cmd)
            return clipboard_after_redo

        return self

    def __paste_copied_parts(self, paste_pos: Position, new_parent: ActorPart) -> Decl.ViewClipboard:
        if self.__next_paste_action == ClipboardActionEnum.paste_from_copy:
            log.debug("Pasting copy of parts from clipboard")
            paste_offset = self.__calculate_paste_offset(paste_pos, undo_copy_cmd=PasteCopiedPartsCommand)
            clipboard_after_redo = ViewClipboard(ClipboardActionEnum.paste_from_copy,
                                                 self.__parts, self.__center_pos, paste_pos=paste_pos)

        else:
            assert self.__next_paste_action is ClipboardActionEnum.paste_from_pasted_cut
            log.debug("Pasting *copy* of moved (i.e. cut then pasted) parts")
            paste_offset = self.__calculate_paste_offset(paste_pos)
            clipboard_after_redo = ViewClipboard(ClipboardActionEnum.paste_from_pasted_cut,
                                                 self.__parts, self.__center_pos, paste_pos=paste_pos)

        cmd = PasteCopiedPartsCommand(new_parent, self.__parts,
                                      paste_offset=paste_offset,
                                      clipboard_after_redo=clipboard_after_redo,
                                      clipboard_after_undo=self)
        scene_undo_stack().push(cmd)
        return clipboard_after_redo

    def __calculate_paste_offset(self, paste_pos: Position, undo_copy_cmd: UndoCommandBase = None) -> Vector:
        """
        Calculates the relative position (paste offset) from the original part or previous paste.
        :param paste_pos: the absolute position to paste the copied or cut part. Typically this is the mouse
            position in scenario coordinates
        :param undo_copy_cmd: the Undo Copy Command to find on the Undo Stack.
        :returns the paste offset.
        """
        fresh_paste = self.__prev_paste_pos is None
        mouse_moved = None if fresh_paste else (self.__prev_paste_pos != paste_pos)
        if fresh_paste or mouse_moved:
            # fresh paste (no previous paste position to offset from) OR mouse moved since last paste:
            # regardless of pasting from copy or cut operation, a NEW position offset is required.
            if fresh_paste:
                assert self.__next_paste_action in (
                    ClipboardActionEnum.paste_from_copy, ClipboardActionEnum.paste_from_cut)
            new_offset = self.__new_paste_offset(paste_pos)
            log.debug('NEW paste offset: {:.5}', new_offset)
            return new_offset

        # not a fresh paste, and mouse has not moved: need to offset from previous paste so pasted parts do
        # not overlap the previous set of pasted parts

        if self.__next_paste_action == ClipboardActionEnum.paste_from_copy:
            assert undo_copy_cmd is not None
            cmd = scene_undo_stack().find_previous_command(undo_copy_cmd)
            assert cmd is not None
            prev_paste_offset = cmd.get_paste_offset()
            cascade_offset = self.__cascade_paste_offset(prev_paste_offset)
            log.debug('CASCADE paste offset: {:.5}, {:.5}', prev_paste_offset, cascade_offset)
            return cascade_offset

        # the only way we can get this far is if this paste is the one right after having pasted cut parts once:
        assert self.__next_paste_action is ClipboardActionEnum.paste_from_pasted_cut

        # the first paste of the cut parts moved them to a new position in the receiving actor, and since the
        # mouse has not moved since that paste, it means the new offset is simply PASTE_OFFSET_DELTA
        reparent_offset = self.PASTE_OFFSET_DELTA
        log.debug('REPARENTED paste offset: {:.5}', reparent_offset)
        return reparent_offset

    def __new_paste_offset(self, paste_pos: Position) -> Vector:
        """
        Calculate the paste offset for parts that are being moved within same actor, or parts that are
        being reparented. Either way, the geometrical center of the set of parts on the clipboard is being
        moved to where the mouse is (paste_pos): each part must be moved by the same offset vector.
        :param paste_pos: the desired position where center of all parts on clipboard should be located
        :return: a new offset from this position
        """
        return paste_pos - self.__center_pos

    def __cascade_paste_offset(self, paste_offset: Vector) -> Vector:
        """
        Cascades the offset to prevent copies or cuts from being pasted directly over each other.
        :param paste_offset: the calculated offset position of the paste from the original part.
        :return: a new offset that is paste_offset + PASTE_OFFSET_DELTA.
        """
        return paste_offset + self.PASTE_OFFSET_DELTA

    def __check_break_adjust_ifx(self, non_restorable: Dict[PartLink, RestoreLinkInfo]) -> ButtonActionOnReparentEnum:
        message = "The move would produce invalid links:\n"
        sorted_links = sorted(non_restorable, key=lambda link: str(non_restorable[link]))
        message += ''.join('- {}\n'.format(non_restorable[link]) for link in sorted_links)
        message += dedent("""
                  Choose one of the three options:
                  1. Break the invalid links
                  2. Adjust the interface levels of link sources/targets to make them valid
                  3. Cancel""")
        answer = exec_modal_dialog(dialog_title="Move Part",
                                   message=message,
                                   icon=QMessageBox.Question,
                                   buttons_str_role=BUTTONS_ADJUST_BAD_LINKS_ON_MOVE)
        return ButtonActionOnReparentEnum(answer)


class Actor2dView(QGraphicsView):
    """
    Shows Parts and Actors in a 2D View. Context Menus allow for different action lists for each part type.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # According to the Qt sceneRect documentation, the scroll bars will never exceed the range of an integer
    # (INT_MIN, INT_MAX). Note: It is very likely a documentation error; it actually means
    # (LONG_MIN, LONG_MAX) = (-2147483648, 2147483647). Experiments show the properties "minimum" and "maximum" of the
    # QAbstractSlider could reach LONG_MIN and LONG_MAX when the sceneRect is big.
    SCROLL_BAR_MIN = -2147483648
    SCROLL_BAR_MAX = 2147483647

    # If the slider is just one pixel away from the ends, it is deemed to have touched the end.
    SINGLE_STEP_TOL = 2

    MAX_ZOOM_VALUE = 500.0
    DEFAULT_ZOOM_SLIDER_VALUE = MAX_ZOOM_VALUE / 2
    ZOOM_SENSITIVITY = MAX_ZOOM_VALUE / 10
    SCALE_BASE = 2.0
    ACTUAL_SIZE_SCALE = 1.0

    MAX_SCALE = pow(SCALE_BASE, (MAX_ZOOM_VALUE - DEFAULT_ZOOM_SLIDER_VALUE) / ZOOM_SENSITIVITY)
    MIN_SCALE = pow(SCALE_BASE, (-DEFAULT_ZOOM_SLIDER_VALUE) / ZOOM_SENSITIVITY)

    # Most mouse types work in steps of 15 degrees, in which case the delta value is a multiple of 120;
    # i.e., 120 units * 1/8 = 15 degrees.
    WHEEL_RESOLUTION_ADJUSTMENT_FACTOR = 8
    TYPICAL_MOUSE_WHEEL_STEP = 15

    # Extra margin factor to make the scene bigger after all the calculations. For example, 0.2 means 20% bigger on
    # each side of the scene rectangle.
    EXTRA_MARGIN_FACTOR = 0.2
    # Scale a little more to make sure
    SCALE_ADJUSTMENT = 0.99

    # Increment position offset when pasting copied parts (X-Offset, Y-Offset)

    # The OFFSET_X is the parent procy location x offset. 0 means the parent proxy's top left corner in the middle of
    # viewport x axis. increase the offset x will move the parent proxy to the left.
    EMPTY_ACTOR_PARENT_PROXY_POS_OFFSET_X = 0.1
    # The OFFSET_Y is the parent procy location y offset. 0 means the parent proxy's top left corner in the middle of
    # viewport y axis. increase the offset y will move the parent proxy upward.
    EMPTY_ACTOR_PARENT_PROXY_POS_OFFSET_Y = 1.05

    EMPTY_ACTOR_SCALE_ADJUSTMENT = 0.9

    # During the view navigation, the user experience would be better if we ignore position and zoom jitters caused
    # by hand or calculation.
    # If the view center change is smaller than 3 pixels or the zoom factor change is smaller than 0.01,
    # we do not push the ViewNavTo command
    VIEW_CENTER_CHANGE_TOL = 3
    ZOOM_CHANGE_TOL = 0.01

    # previous view center, previous zoom factor, current view center, current zoom factor, command type
    sig_view_nav = pyqtSignal(tuple, float, tuple, float, int)

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, edit_actions: EditActions, view_actions: ViewActions):
        """
        Initializes the 2D View.
        :param edit_actions: a list of scenario-based editing actions (cut, copy, paste, etc.).
        :param view_actions: a list of scenario-based view actions (zoom to fit all, zoom to selection, etc.).
        """
        super().__init__()

        self.__top_most_proximity_border_item = None
        self.__command_type = None
        # Value ranges from 0 to 500, where 250 means no zoom at all.
        self.__zoom_slider_value = Actor2dView.DEFAULT_ZOOM_SLIDER_VALUE

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setRenderHint(QPainter.SmoothPixmapTransform, True)

        self.__cursor_override = False
        self.__rubberband_mode = False
        self.set_cursor_default()

        # Oliver Aug 2015: the following is only necessary because without it, navigating from one actor to
        #    another leaves various links partially visible, although the scene has been cleared; this is likely
        #    due to the part link items not computing their bounding rect/shape properly, which causes the View
        #    to have a hard time figuring out which portions of the viewport to update. By using Full, there is no
        #    such effects, but the View likely does more work than necessary (Smart has less of a problem but not
        #    as good as Full).
        #
        # Mark Oct 2015: While the issue for links has been resolved through a better part link bounding rect
        # definition, the 'Full' view update is still required as the other update modes leave some graphic artifacts
        # behind when switching views between actors. These artifacts include highlighted part boundaries and actor
        # proxies that remain in the new scene even though they pertain to the previous scene and will disappear only
        # if the user drags a part over top of the area. Since 'Full' update mode forces the entire view to be redrawn,
        # there are no lingering parts from previous scenes, but manipulating parts in a scene where there are a large
        # number of items will usually result in a perceptible lag.

        # Colin July 11, 2017: Tested all the options. It seems the default MinimalViewportUpdate and
        # SmartViewportUpdate are OK. But it breaks the test_scene.py. More investigation needed.
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

        self.context_menu = QMenu(self)

        # create new-part sub-menu:
        new_part_menu = QMenu(self)
        new_part_menu.setTitle("New Part")
        supported_types = get_registered_type_names(non_creatable=False)
        for part_type in supported_types:
            action = PartAction(part_type, self)
            new_part_menu.addAction(action)
            action.triggered.connect(self.slot_on_request_add_part)
        self.context_menu.addMenu(new_part_menu)
        self.__new_part_menu = new_part_menu

        # create paste menu:
        self.__cut_action = edit_actions.cut_action
        self.__copy_action = edit_actions.copy_action
        self.__paste_action = edit_actions.paste_action
        self.__delete_action = edit_actions.delete_action

        self.context_menu.addAction(self.__cut_action)
        self.context_menu.addAction(self.__copy_action)
        self.context_menu.addAction(self.__paste_action)
        self.context_menu.addAction(self.__delete_action)

        # create zoom to selection menu:
        self.__zoom_to_selection_action = view_actions.action_zoom_to_selection
        self.__action_scen_pos = None
        self.__mouse_right_click_scene_pos = QPointF()

        self.horizontalScrollBar().actionTriggered.connect(self.__slot_on_horizontal_scrollbar_triggered)
        self.verticalScrollBar().actionTriggered.connect(self.__slot_on_vertical_scrollbar_triggered)
        self.horizontalScrollBar().sliderReleased.connect(self.__slot_on_horizontal_scrollbar_released)
        self.verticalScrollBar().sliderReleased.connect(self.__slot_on_vertical_scrollbar_released)

        self.__last_view_nav_center = self.__center_truncated()
        self.__last_view_nav_zoom_slider_value = self.__zoom_slider_value

        self.__mouse_dragged_since_press = False
        self.__clipboard = None
        self.__update_clipboard_view()

    @override(QGraphicsView)
    def viewportEvent(self, event: QEvent) -> bool:
        """
        After handling the view navigation, it simply forwards the execution to the super.

        This is best location to handle the viewport because the viewport position on the scene will
        become final at this point after a user action, for example, clicking on a scroll bar.

        :param event: Qt controls the event delivery
        :return: The return value of the super().viewportEvent(event)
        """
        if self.__command_type is not None:
            self.__check_view_changed()

        return super().viewportEvent(event)

    @override(QGraphicsView)
    def setScene(self, new_scene: Actor2dScene):
        """
        Set the scene for this view. If the scene is already current, just sets up the viewport.
        :param new_scene: the scene to activate
        """
        current_scene = self.scene()
        if current_scene is not new_scene:
            if current_scene is not None:
                # save current view so can restore it when return to same actor:
                self.save_current_viewport()
                # disconnect:
                current_scene.sig_part_added.disconnect(self.slot_on_child_part_added)
                current_scene.sig_child_part_moved.disconnect(self.slot_on_child_part_moved)
                current_scene.sig_part_selection_changed.disconnect(self.slot_on_part_selection_changed)
                current_scene.notify_viewing_change(False)

            new_scene.sig_part_added.connect(self.slot_on_child_part_added)
            new_scene.sig_child_part_moved.connect(self.slot_on_child_part_moved)
            new_scene.sig_part_selection_changed.connect(self.slot_on_part_selection_changed)

            super().setScene(new_scene)
            new_scene.notify_viewing_change(True)

        self.setup_viewport(new_scene.view_center_2d, new_scene.zoom_factor_2d)
        self.update_edit_actions()

    @override(QGraphicsView)
    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Plus:
            self.__command_type = NavToViewCmdTypeEnum.zoom
            self.__zoom_slider_value += Actor2dView.TYPICAL_MOUSE_WHEEL_STEP
            self.__set_zoom(self.__zoom_slider_value)
        elif event.key() == Qt.Key_Minus:
            self.__command_type = NavToViewCmdTypeEnum.zoom
            self.__zoom_slider_value -= Actor2dView.TYPICAL_MOUSE_WHEEL_STEP
            self.__set_zoom(self.__zoom_slider_value)

        super().keyPressEvent(event)

    @override(QGraphicsView)
    def mousePressEvent(self, event: QMouseEvent):
        # For right-clicks that open the context menu, record the mouse position for paste operations
        # since the view.viewport().underMouse() condition fails when the context menu is open
        log.debug("View got mouse press: {}", EventStr(event))

        if event.button() == Qt.RightButton:
            super().mousePressEvent(event)
            self.__mouse_right_click_scene_pos = self.mapToScene(event.pos())
            return

        super().mousePressEvent(event)

    @override(QGraphicsView)
    def mouseMoveEvent(self, event: QMouseEvent):
        """
        Handles item highlighting. Note: the hoverEnterEvent and hoverLeaveEvent on the item are not reliable.
        Responds to mouse-left dragging if there is no item under mouse; assumes drag mode=ScrollHandDrag.
        :param event: From the Qt platform.
        """
        super().mouseMoveEvent(event)

        # Locate the topmost proximity border item and activate it
        for item in self.items(event.pos()):
            if item.type() == CustomItemEnum.proximity:
                item.activate()
                top_most_proximity_border_item = item
                break
        else:
            top_most_proximity_border_item = None

        if top_most_proximity_border_item is not self.__top_most_proximity_border_item:
            self.__top_most_proximity_border_item = top_most_proximity_border_item
            # Deactivate all the other proximity border items in the current
            for item in self.items(self.viewport().rect()):
                if item.type() == CustomItemEnum.proximity:
                    if item is not self.__top_most_proximity_border_item:
                        item.deactivate()

        # If the view is being moved over the scene, scene might need to have
        # its extents extended otherwise the view will not actually move:
        if self.__check_moving_view(event):
            self.__set_unlimited_scene()
            self.__mouse_dragged_since_press = True

    @override(QGraphicsView)
    def mouseReleaseEvent(self, event: QMouseEvent):
        # first handle the event in base class, then change the drag mode back if necessary:
        log.debug("View got mouse release")
        # The __command_type must be set here instead of at the end of the function because the viewportEvent
        # handler expects it right away in the super() call. Otherwise, it would miss the first shot.
        if self.__mouse_dragged_since_press:
            self.__command_type = NavToViewCmdTypeEnum.mouse_dragged
            self.__mouse_dragged_since_press = False

        super().mouseReleaseEvent(event)

    @override(QGraphicsView)
    def contextMenuEvent(self, evt: QContextMenuEvent):
        """
        If user asks for context menu, which one to show depends on whether the click is on an item: if it is,
        and there is no item selected or just one item selected, let the item handle it; otherwise, update
        the canvas menu, and if there is only one item selected, unselect it; if more than one item, leave
        it selected, so that we don't force user to ask for context on a selected part.
        """
        scene_pos = self.mapToScene(evt.pos())
        self.__action_scen_pos = map_to_scenario(scene_pos)

        # show canvas menu, or let scene handle context menu event:
        item = self.itemAt(evt.pos())
        if item is None:
            # nothing under mouse, clear any selection and show canvas menu:
            self.scene().clearSelection()
            self.context_menu.exec(evt.globalPos())

        elif len(self.scene().selectedItems()) > 1:
            # item under mouse, and multiple items selected: show canvas menu, but clear selection first if no
            # item selected is under mouse cursor; if there is item under mouse, disable paste while showing
            # menu since it does not apply to multiselection context menu
            if self.scene().check_any_selected_under_mouse():
                self.__update_paste_action(item_context=True)
            else:
                self.scene().clearSelection()  # this will update paste action too

            self.context_menu.exec(evt.globalPos())
            self.__update_paste_action(item_context=False)

        else:
            # item under mouse, and no or single selection so let scene deal with it:
            super().contextMenuEvent(evt)

    @override(QGraphicsView)
    def wheelEvent(self, event: QWheelEvent):
        """
        Scroll the view left-right or up-down. When the scroll bars hit the limits, we extend the
        scene so that the scrolling can continue.
        """
        if event.modifiers() == Qt.ControlModifier:
            self.__handle_zoom_event(event)
            self.__command_type = NavToViewCmdTypeEnum.zoom

        elif event.modifiers() == Qt.ShiftModifier:
            # the SHIFT key modifier will by default cause the horizontal scroll bar to take a page
            # step instead of a single (line) step, so need to remove the modifier before forwarding
            # to the horizontal scroll bar (but Qt does not have event cloning functions so have to
            # clone manually, without the SHIFT modifier)
            event_without_shift = QWheelEvent(event.posF(),
                                              event.globalPosF(),
                                              event.pixelDelta(),
                                              event.angleDelta(),
                                              event.angleDelta().y(),  # qt4delta is the y coomponent (undocumented)
                                              Qt.Horizontal,  # we want horizontal scroll
                                              Qt.MidButton,
                                              Qt.NoModifier)  # and no SHIFT modifier
            self.horizontalScrollBar().event(event_without_shift)
            self.__on_horizontal_mouse_wheel()

        else:
            super().wheelEvent(event)
            self.__on_vertical_mouse_wheel()

    @override(QGraphicsView)
    def paintEvent(self, event: QPaintEvent):
        import time
        start = time.perf_counter()
        QGraphicsView.paintEvent(self, event)
        total = time.perf_counter() - start
        # log.debug("Render time for 2d view: {} sec", total)

    @override(QGraphicsView)
    def enterEvent(self, event: QEvent):
        log.debug('--- Mouse entering 2d View')
        super().enterEvent(event)

    @override(QGraphicsView)
    def leaveEvent(self, event: QEvent):
        log.debug('--- Mouse leaving 2d View')
        super().leaveEvent(event)

    def get_last_view_nav_center(self) -> Tuple[float, float]:
        """
        The view center that has remained intact since the last change.

        The purpose of this value is to construct the undo portion of the view nav command. Suppose the initial value
        is at (0, 0). The user starts to drag the canvas and the view center would change many times immediately,
        depending on how fast and how far the mouse moves. As long as the user does not release the left button of
        the mouse, all those view center values are transient - no view nav commands will be pushed to the stack.
        As soon as the button is released eventually, the position under the mouse, say, (3, 5) will be used to
        construct the redo portion of the command. Then it will be pushed to the stack. Meanwhile, the (3, 5) is
        recorded to be used to construct the undo portion of the next view nav command.
        :return: The view center on the scene.
        """
        return self.__last_view_nav_center

    def get_last_view_nav_zoom_slider_value(self) -> float:
        """
        See the docstring of the get_last_view_nav_center. The concept is similar to that described in the
        get_last_view_nav_center.
        """
        return self.__last_view_nav_zoom_slider_value

    def fit_selection_in_view(self):
        """
        Fits all the selected objects to the view so that the viewport center and the content center are the same point
        in the scene coordinate system.
        """
        item_list = [obj for obj in self.scene().selectedItems()]
        # Special case: if link is selected, the items only contain the source segment, we need to add all link
        # segments to the list. The list of selected items will be replaced by segment list

        if item_list[0].type() == CustomItemEnum.link:
            assert len(item_list) == 1  # only one link can be selected
            item_list = item_list[0].link_obj.get_segment_items()

        assert len(item_list) > 0
        self.fit_content_in_view(items=item_list)

    def fit_content_in_view(self, items: List[QGraphicsItem] = None):
        """
        This function fits the given items to the view so that the viewport center and the content center are the 
        same point in the scene coordinate system. If items are not given, it applies to all the items.
        :param items: The items to be fit in the view
        """
        self.centerOn(QPointF(0.0, 0.0))
        self.resetTransform()
        rect_needed = QRectF()
        item_list = items
        if items is None:
            item_list = self.scene().get_root_items()

        for item in item_list:
            # Use rectangles to unite consistently. Polygons unite problematically sometimes.
            rect_needed = rect_needed.united(item.mapToScene(item.boundingRect()).boundingRect())

        if len(self.scene().get_child_part_items()) <= 0:
            scale = self.EMPTY_ACTOR_SCALE_ADJUSTMENT
        else:
            vp_rect = QRectF(self.viewport().rect())
            vp_polygon = self.mapToScene(QRect(int(vp_rect.x()), int(vp_rect.y()), int(vp_rect.width()), int(vp_rect.height())))
            if rect_needed.width() > 0.0:
                width_ratio = vp_polygon.boundingRect().width() / rect_needed.width()
            else:
                width_ratio = Actor2dView.ACTUAL_SIZE_SCALE
            if rect_needed.height() > 0.0:
                height_ratio = vp_polygon.boundingRect().height() / rect_needed.height()
            else:
                height_ratio = Actor2dView.ACTUAL_SIZE_SCALE

            scale = min(width_ratio, height_ratio, Actor2dView.ACTUAL_SIZE_SCALE)

        # set zoom slider value
        self.__zoom_slider_value = Actor2dView.DEFAULT_ZOOM_SLIDER_VALUE
        if scale != Actor2dView.ACTUAL_SIZE_SCALE:
            scale *= Actor2dView.SCALE_ADJUSTMENT
            self.__zoom_slider_value = (Actor2dView.ZOOM_SENSITIVITY * math.log(scale, Actor2dView.SCALE_BASE)
                                        + Actor2dView.DEFAULT_ZOOM_SLIDER_VALUE)

        obj_list = None
        if items is not None:
            obj_list = items

        content_center = self.__update_scene_extents(scale=scale, item_list=obj_list)
        log.debug("View center set to content center ({:.5}, {:.5})", content_center.x(), content_center.y())
        self.centerOn(content_center)
        self.__command_type = NavToViewCmdTypeEnum.fit_content_in_view

    def on_scene_cleared(self, scene: Actor2dScene):
        """When the scene gets cleared, need to clear the clipboard, etc."""
        self.clear_parts_clipboard()

    def get_next_paste_action(self) -> ClipboardActionEnum:
        """
        Get the action ID for action that will occur as a result of next paste action. For example, if the last
        clipboard was created as a result of a cut, then the next paste action is paste_from_cut, whereas if
        the last action was copy or paste_from_copy, the next paste action is paste_from_copy.
        """
        return None if self.__clipboard is None else self.__clipboard.next_paste_action

    def delete_selected_items(self):
        """Command the backend to delete currently selected items"""
        if self.scene().has_part_selection():
            self.scene().delete_selected_parts()
        elif self.scene().has_waypoint_selection():
            self.scene().delete_selected_waypoints()
        else:
            pass  # No other option

    def cut_selected_parts(self):
        """
        Put selected parts in scenario clipboard and command the backend to remove them.
        """
        parts = self.scene().get_selected_objects()
        if not parts:
            log.debug('WARNING: cut_selected_parts() called but there are no selected objects')
            return

        part_names = ['"{}"'.format(selectedPart.name) for selectedPart in parts]
        msg = "Cut (will delete) {} part{} ({}). Are you sure?".format(
            len(part_names), plural_if(parts), ', '.join(part_names))
        if exec_modal_dialog("Cut Part", msg, QMessageBox.Question) != QMessageBox.Yes:
            return

        new_clipboard = ViewClipboard(ClipboardActionEnum.cut, parts, self.scene().get_part_selection_center_scenario())
        command = CutPartsCommand(parts[:],
                                  clipboard_after_undo=self.__clipboard,
                                  clipboard_after_redo=new_clipboard)
        scene_undo_stack().push(command)
        self.__replace_clipboard(new_clipboard)
        self.__update_paste_action()

    def copy_selected_parts(self):
        """
        Put selected parts in scenario clipboard
        """
        parts = self.scene().get_selected_objects()
        if not parts:
            return

        new_clipboard = ViewClipboard(ClipboardActionEnum.copy, parts,
                                      self.scene().get_part_selection_center_scenario())
        self.__replace_clipboard(new_clipboard)
        self.__update_paste_action()

    def paste_clipboard(self):
        """
        Paste the parts in the clipboard (a previous copy or cut, possibly when a different scene as active)
        into our scene.
        :param paste_at_mouse_hover_pos: a flag that indicates if the paste position is where the mouse is currently
            hovering over the view. This flag is False by default and assumes the paste is via the context menu, in
            which case the paste occurs at the last position the mouse right-clicked the invoke the context menu. For
            paste operations invoked by Ctrl+V and panel-based buttons, this parameter must be set to True in order to
            paste at the mouse. If the mouse is not currently over the View, the paste position then defaults to the
            center of the View.
        """

        if self.__clipboard is None:
            msg = "There are no items on the clipboard to paste."
            exec_modal_dialog("Paste Error", msg, QMessageBox.Information)
            return

        log.info("Paste parts requested in scene")

        if self.viewport().underMouse():
            # Use the mouse position if it is over the View ('underMouse()' returns False if in a context-menu)
            mouse_scene_pos = self.mapToScene(self.mapFromGlobal(QCursor.pos()))
            paste_pos = map_to_scenario(mouse_scene_pos)

        elif self.viewport().rect().contains(self.mapFromGlobal(QCursor.pos())):
            # If not underMouse, but inside the viewport, context-menu paste was invoked
            paste_pos = map_to_scenario(self.__mouse_right_click_scene_pos)

        else:
            # Otherwise, mouse not under viewport or context-menu: use the center of the View
            view_rect = self.viewport().rect()
            center_view_pos = self.mapToScene(view_rect.center())
            paste_pos = map_to_scenario(center_view_pos)

        new_clipboard = self.__clipboard.paste_parts(paste_pos, self.content_actor)
        self.__replace_clipboard(new_clipboard)

    def on_command_undone(self, command: UndoCommandBase):
        """When certain commands are undone, the clipboard needs to be adjusted"""
        if command.has_clipboards:
            self.__replace_clipboard(command.clipboard_after_undo)

    def on_command_redone(self, command: UndoCommandBase):
        """When certain commands are re/done, the clipboard needs to be adjusted"""
        if command.has_clipboards:
            self.__replace_clipboard(command.clipboard_after_redo)

    def on_request_add_part(self):
        """
        Request (via the scene) that a part of a certain type be created. This assumes it is called as a
        result of a signal (because self.sender() is used).
        """
        part_type_str = self.sender().data()
        self.scene().request_part_creation(part_type_str, self.__action_scen_pos or Position())

    def set_animated(self, state: bool = True):
        """Configure view according to animation state"""
        self.setEnabled(state)

    def setup_viewport(self, center: Position, zoom_factor: float,
                       command_type: NavToViewCmdTypeEnum = None):
        """
        Setup the viewport.

        :param center: The center where the undo/redo needs to go.
        :param zoom_factor: The zoom factor that undo/redo needs to use.
        :param command_type: The command that drives the view change.

        If either is None, then the current scene is queried for stored value.

        If the zoom factor is None, then the entire scene will be fit into the view. Otherwise, if the
        center is None, only the zoom is set, else both the zoom and center are set.
        """
        if command_type in [NavToViewCmdTypeEnum.horizontal_slider_move,
                            NavToViewCmdTypeEnum.vertical_slider_move,
                            NavToViewCmdTypeEnum.slider_step]:
            self.centerOn(QPointF(center.x, center.y))
        elif command_type == NavToViewCmdTypeEnum.mouse_dragged:
            self.__set_view_center(QPointF(center.x, center.y))
        else:
            self.__zoom_slider_value = Actor2dView.DEFAULT_ZOOM_SLIDER_VALUE
            # Scenario position for newly created parts:
            self.__action_scen_pos = None

            if zoom_factor is None:
                zoom_factor = self.scene().zoom_factor_2d
            if center is None:
                center = self.scene().view_center_2d

            if zoom_factor is None:
                self.fit_content_in_view()
            else:
                if center is None:
                    self.__set_zoom(zoom_factor)
                else:
                    self.__set_viewport(center, zoom_factor)

        self.__on_viewport_changed()

    def save_current_viewport(self):
        """Save the viewport for current view/scene combo so it can be restored later (in setScene())."""
        x_trunc, y_trunc = self.__center_truncated()
        current_scene = self.scene()
        current_scene.set_view_center_2d(Position(x_trunc, y_trunc))
        current_scene.set_zoom_factor_2d(self.__zoom_slider_value)

    def get_current_viewport(self) -> Tuple[Position, float]:
        """Gets the current center and the zoom factor."""
        x_trunc, y_trunc = self.__center_truncated()
        return Position(x_trunc, y_trunc), self.__zoom_slider_value

    def get_content_actor(self):
        """Get the actor shown by the view, ie whose children are currently visible in this view"""
        return self.scene().content_actor

    def on_child_part_added(self, child_part: BasePart):
        """
        Adjust the scene after a child has been added to the scene: a newly added part may go beyond the current
        scene rect, in which case the scrollbars need adjusting so the user can use them to show the
        hidden portion of the part.

        :param child_part: The part that is added.
        """
        new_part_pos = map_from_scenario(Position(child_part.part_frame.pos_x, child_part.part_frame.pos_y))
        if not self.sceneRect().contains(new_part_pos):
            vp_scene = self.mapToScene(self.viewport().rect().center())
            self.__set_view_center(vp_scene)

    def on_child_part_moved(self):
        """
        Adjust the scene after a child part has been moved: it may go beyond the current
        scene rect, in which case the scrollbars need adjusting so the user can use them to
        show the hidden portion of the part.
        """
        self.__update_scene_extents()

    def on_part_selection_changed(self, selected_parts: List[BasePart]):
        self.__update_canvas_actions()
        self.__update_selection_actions()

    def update_edit_actions(self):
        """
        Update the state of the Edit actions that are managed by the View
        """
        self.__update_canvas_actions()
        self.__update_paste_action()
        self.__update_selection_actions()

    def is_clipboard_empty(self) -> bool:
        """False if there are parts on the clipboard, True if there are no parts."""
        return self.__clipboard is None

    def clear_parts_clipboard(self):
        """Clears the clipboard."""
        self.__replace_clipboard(None)

    def get_parts_clipboard(self) -> List[BasePart]:
        """Get a copy of the parts clipboard"""
        return [] if self.__clipboard is None else self.__clipboard.parts

    def replace_clipboard_by_ori(self, on_replacement_done_cb: Callable[[], None]):
        """
        Replaces the clipboard list of parts with a list of proxy ORI definitions. Used for pasting
        ops between scenarios.
        :param on_replacement_done_cb: A callback to execute after the clipboard replacement.
        """
        self.__clipboard.replace_by_ori(on_replacement_done_cb)

    def set_cursor_override(self):
        """
        Override the view drag mode cursor to allow another cursor to be set on the View.
        """
        log.debug("Actor2dView in cursor OVERRIDE mode")
        self.setDragMode(QGraphicsView.NoDrag)
        self.__cursor_override = True

    def set_rubberband_mode(self):
        """
        Sets the drag-mode to RubberBandDrag.
        """
        log.debug("Actor2dView in RUBBER-BAND mode")
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.__rubberband_mode = True

    def set_cursor_default(self):
        """
        Restore the view to the default ScrollHandDrag mode.
        """
        log.debug("Actor2dView in cursor DEFAULT mode")
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.__cursor_override = False
        self.__rubberband_mode = False

    def is_cursor_overridden(self) -> bool:
        """
        Return the value of the cursor override.
        """
        return self.__cursor_override

    def is_rubberband_mode(self) -> bool:
        """
        Return the value state of rubberband mode.
        """
        return self.__rubberband_mode

    slot_on_request_add_part = safe_slot(on_request_add_part)
    slot_on_paste_action = safe_slot(paste_clipboard)
    slot_on_cut_action = safe_slot(cut_selected_parts)
    slot_on_copy_action = safe_slot(copy_selected_parts)
    slot_on_delete_action = safe_slot(delete_selected_items)
    slot_on_child_part_added = safe_slot(on_child_part_added)
    slot_on_child_part_moved = safe_slot(on_child_part_moved)
    slot_on_part_selection_changed = safe_slot(on_part_selection_changed)

    # --------------------------- instance PUBLIC properties ----------------------------

    content_actor = property(get_content_actor)
    last_view_nav_center = property(get_last_view_nav_center)
    last_view_nav_zoom_slider_value = property(get_last_view_nav_zoom_slider_value)
    parts_clipboard = property(get_parts_clipboard)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __replace_clipboard(self, new_clipboard: ViewClipboard):
        """Replace the existing clipboard member by a new clipboard instance"""
        old_clipboard = self.__clipboard
        self.__clipboard = new_clipboard
        self.__update_clipboard_view(old_clipboard)

    def __update_clipboard_view(self, old_clipboard: ViewClipboard = None):
        """
        Update the view of the clipboard. Currently this is just logging whether clipboard is empty or
        (if not empty) what its next paste action will be.
        """
        if self.__clipboard is None and old_clipboard is None:
            # if both clipboards are none, nothing to update:
            return

        if self.__clipboard is None:
            assert old_clipboard is not None
            log.info('Clipboard is now EMPTY')

        else:
            if old_clipboard is None or set(old_clipboard.parts) != set(self.__clipboard.parts):
                part_names = (str(p) for p in self.__clipboard.parts)
                log.info('Clipboard changed, it is now: {}', ','.join(part_names))
            self.__clipboard.show_next_paste_action()

    def __on_viewport_changed(self):
        """
        Tracks the last viewport to facilitate the view navigation.
        """
        old_x, old_y = self.__last_view_nav_center
        new_x, new_y = self.__center_truncated()

        if math.isclose(new_x, old_x, abs_tol=self.VIEW_CENTER_CHANGE_TOL):
            new_x = old_x

        if math.isclose(new_y, old_y, abs_tol=self.VIEW_CENTER_CHANGE_TOL):
            new_y = old_y

        self.__last_view_nav_center = (new_x, new_y)
        self.__last_view_nav_zoom_slider_value = self.__zoom_slider_value

    def __update_canvas_actions(self):
        """
        Enable/disable actions specific to the canvas: New part, and Paste part (if the clipboard has parts).
        :param enable: False to disable
        """
        new_part_allowed = not self.scene().has_selection()
        self.__new_part_menu.setEnabled(new_part_allowed)

    def __update_paste_action(self, item_context: bool = False):
        clipboard_has_parts = self.__clipboard is not None
        paste_allowed = clipboard_has_parts and (not item_context)
        self.__paste_action.setEnabled(paste_allowed)
        # log.debug("Updated paste action to {} {} {}", clipboard_empty, item_context, paste_allowed)

    def __update_selection_actions(self):
        """
        Update the edit actions based on whether there is selection (Cut, Copy, Delete).
        """
        if self.scene().has_part_selection():
            self.__cut_action.setEnabled(True)
            self.__copy_action.setEnabled(True)
            self.__delete_action.setEnabled(True)
            self.__zoom_to_selection_action.setEnabled(True)

        elif self.scene().has_waypoint_selection():
            self.__cut_action.setEnabled(False)
            self.__copy_action.setEnabled(False)
            self.__delete_action.setEnabled(True)
            self.__zoom_to_selection_action.setEnabled(True)

        else:
            self.__cut_action.setEnabled(False)
            self.__copy_action.setEnabled(False)
            self.__delete_action.setEnabled(False)
            if self.scene().has_link_selection():
                self.__zoom_to_selection_action.setEnabled(True)
            else:
                self.__zoom_to_selection_action.setEnabled(False)

    def __get_bounding_rect_center_scenario(self, parts: List[BasePart]) -> Tuple[float, float]:
        """Get the center of the bounding rectangle of all the parts positions"""
        min_x = None
        min_y = None
        max_x = None
        max_y = None
        for part in parts:
            pos_x = part.part_frame.pos_x
            pos_y = part.part_frame.pos_y
            min_x = pos_x if min_x is None else min(pos_x, min_x)
            min_y = pos_y if min_y is None else min(pos_y, min_y)
            max_x = pos_x if max_x is None else max(pos_x, max_x)
            max_y = pos_y if max_y is None else max(pos_y, max_y)

        return (max_x - min_x) / 2, (max_y - min_y) / 2

    def __set_zoom(self, zoom_slider_value: float):
        """
        Zoom this view. Make the zooming reasonable by restricting the zoom slider value between 0 and 500.
        :param zoom_slider_value: a float number [0, 500]. The value beyond that will be capped to [0, 500]
        """
        self.__zoom_slider_value = zoom_slider_value
        if self.__zoom_slider_value < 0.0:
            self.__zoom_slider_value = 0.0
        if self.__zoom_slider_value > self.MAX_ZOOM_VALUE:
            self.__zoom_slider_value = self.MAX_ZOOM_VALUE
        scale = pow(Actor2dView.SCALE_BASE,
                    (self.__zoom_slider_value - Actor2dView.DEFAULT_ZOOM_SLIDER_VALUE) / Actor2dView.ZOOM_SENSITIVITY)
        self.__update_scene_extents(scale)

    def __set_viewport(self, center: Position, zoom_factor: float):
        """
        Center and zoom the view.
        :param center: The center on the scene where the center of the view is placed.
        :param zoom_factor: The zoom factor of the view.
        """
        # Center it to a known state before transformation and viewport changes. Otherwise, the Qt does not seem
        # to produce repeatable results.
        self.centerOn(QPointF(0.0, 0.0))
        self.resetTransform()

        self.__set_zoom(self.scene().zoom_factor_2d if zoom_factor is None else zoom_factor)
        center_to_go = self.scene().view_center_2d if center is None else center
        self.__set_view_center(QPointF(center_to_go.x, center_to_go.y))

    def __handle_zoom_event(self, event: QWheelEvent):
        """Zoom in or out depending on the angleDelta of WheelEvent"""
        num_degrees = event.angleDelta() / Actor2dView.WHEEL_RESOLUTION_ADJUSTMENT_FACTOR
        # log.debug("Wheel Mouse Degrees: {},{}", num_degrees.x(), num_degrees.y() )
        self.__zoom_slider_value += num_degrees.y()
        self.__set_zoom(self.__zoom_slider_value)

    def __center_truncated(self) -> Tuple[float, float]:
        """
        Gets the center up to 3 decimal points.
        :return The truncated center.
        """
        # We depend on the Qt to calculate the center. The resolution of the calculation is too high. We
        # use this to truncate the decimal points to 5.
        how_much_to_trunc = '%.3f'
        vp_scene = self.mapToScene(self.viewport().rect().center())
        x_trunc = float(how_much_to_trunc % (vp_scene.x()))
        y_trunc = float(how_much_to_trunc % (vp_scene.y()))
        return x_trunc, y_trunc

    def __set_unlimited_scene(self):
        """
        Sets the scene rectangle to a virtually unlimited size, i.e., width and height approximately equal to the
        full scroll bar range (SCROLL_BAR_MAX - SCROLL_BAR_MIN)
        
        A typical use case is to call it before dragging the view beyond the current extent of the view because the view
        does not do this automatically during mouse move.
        
        Note: This function should be called only during mouse move, because it makes the scene very big. A huge scene 
        is just virtual - not consuming any extra memory as something like bitmap does. Also, Qt has already taken care 
        of always presenting a pair of reasonably good-looking sliders, which won't go as small as view size/2147483647 
        however the scene is adjusted. Setting the scene rectangle that way likely helps performance because setting 
        a pair of reasonable values would require some calculation depending on the current scale factor. I speculate 
        that the values will be used by Qt internally to do a single conditional check MIN < actual < MAX. So, less 
        drastic lower and upper limits won't make a difference.
        """
        rect = self.sceneRect()
        rect.adjust(self.SCROLL_BAR_MIN, self.SCROLL_BAR_MIN, self.SCROLL_BAR_MAX, self.SCROLL_BAR_MAX)
        self.setSceneRect(rect)

    def __set_view_center(self, center: QPointF):
        """
        Moves the center of the view port to the given center. Before the move, the scene must be adjusted so that
        the view port centered on the point will be covered by the adjusted scene.
        
        Note: Unlike the QGraphicsView.centerOn(), which cannot center on a point beyond the current scene rectangle,
        this function extends the scene, if necessary, before calling the centerOn(). We do not override the centerOn()
        because that basic center moving mechanism is also used for other purposes.
        
        :param center: The center the view port will centered on.
        """
        vp_rect = QRectF(self.viewport().rect())

        rect_needed = self.__eval_rect_needed_by_all_items()

        # mapToScene(QRectF) does not exist, so...
        vp_polygon = self.mapToScene(QRect(int(vp_rect.x()), int(vp_rect.y()), int(vp_rect.width()), int(vp_rect.height())))

        rect_needed = rect_needed.united(vp_polygon.boundingRect())

        rect_to_go = QRectF(center.x() - (vp_rect.width() / 2.0),
                            center.y() - (vp_rect.height() / 2.0),
                            vp_rect.width(),
                            vp_rect.height())
        rect_needed = rect_needed.united(rect_to_go)

        # Still make the scene slightly bigger to ensure proper display of the view
        rect_needed = self.__add_extra_margins(rect_needed)

        self.setSceneRect(rect_needed)
        self.centerOn(center)

    def __update_scene_extents(self, scale: float = None, item_list: List[PartBoxItem] = None) -> QPointF:
        """
        Adjusts the scene size to accommodate the items specified by the item_list; if not specified, to accommodate
        all the items in the scene.
        :param scale: the value used for zooming or None for operations that do not need zooming.
        :param item_list: A list of objects that need to fit into the view. Fit all parts in view if this list is None.
        :return: The content center after the scene extents are updated
        """
        if scale is not None and scale != Actor2dView.ACTUAL_SIZE_SCALE:
            existing_scale = self.transform().m11()
            if existing_scale < scale and existing_scale < Actor2dView.MAX_SCALE \
                    or existing_scale > scale and existing_scale > Actor2dView.MIN_SCALE:
                # Checking the MAX_SCALE and MIN_SCALE is intended to minimize viewport center drifting. A Qt bug?
                # Resetting the transformation and setting the same transformation back to the view repeatedly will
                # cause the drifting.

                relative_scale = scale / existing_scale
                self.scale(relative_scale, relative_scale)

        vp_rect = QRectF(self.viewport().rect())
        # log.debug('Viewport rect (in adjust_scene): {}', vp_rect)

        rect_needed = QRectF()
        if item_list is None:
            rect_needed = self.__eval_rect_needed_by_all_items()
        else:
            for item in item_list:
                rect_needed = rect_needed.united(item.mapToScene(item.boundingRect()).boundingRect())

        # log.debug('Viewport rect needed (in adjust_scene): {}', rect_needed)

        # Take the scene center into consideration when an actor has 0 item. This technique is necessary. When using
        # "New" scenario while the current scenario is not saved, you will get a prompt asking if you want to save the
        # scenario. The popup message box will distort the scene, thus misplace the root actor. The rect
        # surrounding the (0, 0) in the scene will solve the problem.

        content_center = rect_needed.center()

        # mapToScene(QRectF) does not exist, so...
        vp_polygon = self.mapToScene(QRect(int(vp_rect.x()), int(vp_rect.y()), int(vp_rect.width()), int(vp_rect.height())))

        rect_needed = rect_needed.united(vp_polygon.boundingRect())

        # Still make the scene slightly bigger to force smooth scrolling.
        rect_needed = self.__add_extra_margins(rect_needed)

        self.setSceneRect(rect_needed)
        return content_center

    def __eval_rect_needed_by_all_items(self) -> QRectF:
        """
        Evaluates the rectangle needed by all the items or empty scenario, i.e., 0 item.
        :return: The rect needed
        """
        vp_rect = QRectF(self.viewport().rect())
        rect_needed = QRectF()
        empty_scene = True
        part_list = self.scene().get_child_part_items()
        if len(part_list) > 0:
            for item in self.scene().get_root_items():
                rect_needed = rect_needed.united(item.mapToScene(item.boundingRect()).boundingRect())
                empty_scene = False

        if empty_scene:
            center_rect = QRectF(-vp_rect.width() / 2.0,
                                 -vp_rect.height() / 2.0,
                                 vp_rect.width() + vp_rect.width() * self.EMPTY_ACTOR_PARENT_PROXY_POS_OFFSET_X,
                                 vp_rect.height() + vp_rect.height() * self.EMPTY_ACTOR_PARENT_PROXY_POS_OFFSET_Y)
            return center_rect

        proxy_item = self.scene().get_content_actor_proxy_item()
        rect_needed = rect_needed.united(proxy_item.mapToScene(proxy_item.boundingRect()).boundingRect())

        return rect_needed

    def __add_extra_margins(self, rect: QRectF) -> QRectF:
        """
        Adds margins to the given rect and returns the enlarged (new) rect. The added margins are based on the width and 
        height of the given rect.
        :param rect: The rect to be based on
        :return: The new enlarged rect.
        """
        margins = QMarginsF(rect.width() * Actor2dView.EXTRA_MARGIN_FACTOR,
                            rect.height() * Actor2dView.EXTRA_MARGIN_FACTOR,
                            rect.width() * Actor2dView.EXTRA_MARGIN_FACTOR,
                            rect.height() * Actor2dView.EXTRA_MARGIN_FACTOR)
        return rect + margins

    def __on_horizontal_mouse_wheel(self):
        """
        When the mouse wheel drives the slider either to the min and the max of the scroll bar, we extend the scene.
        """
        bar = self.horizontalScrollBar()
        val = bar.value()
        lower = bar.minimum()
        upper = bar.maximum()
        page_step = bar.pageStep()
        if val == upper:
            self.setSceneRect(self.sceneRect().adjusted(0, 0, page_step, 0))
        elif val == lower:
            self.setSceneRect(self.sceneRect().adjusted(-page_step, 0, 0, 0))

    def __on_vertical_mouse_wheel(self):
        """
        When the mouse wheel drives the slider either to the min and the max of the scroll bar, we extend the scene.
        """
        bar = self.verticalScrollBar()
        val = bar.value()
        lower = bar.minimum()
        upper = bar.maximum()
        page_step = bar.pageStep()
        if val == upper:
            self.setSceneRect(self.sceneRect().adjusted(0, 0, 0, page_step))
        elif val == lower:
            self.setSceneRect(self.sceneRect().adjusted(0, -page_step, 0, 0))

    def __on_horizontal_scrollbar_triggered(self, slider_action: int):
        """
        Processes the horizontal slider movements: sliding and steps.

        :param slider_action: the slider action emitted by the Qt.
        """
        bar = self.horizontalScrollBar()
        val = bar.value()
        lower = bar.minimum()
        upper = bar.maximum()
        single_step = bar.singleStep()
        page_step = bar.pageStep()

        if slider_action == QAbstractSlider.SliderMove:
            self.__command_type = NavToViewCmdTypeEnum.horizontal_slider_move

        elif slider_action == QAbstractSlider.SliderSingleStepAdd:
            if upper - val < self.SINGLE_STEP_TOL:
                self.setSceneRect(self.sceneRect().adjusted(0, 0, page_step, 0))
                bar.setValue(val + single_step)

            self.__command_type = NavToViewCmdTypeEnum.slider_step

        elif slider_action == QAbstractSlider.SliderSingleStepSub:
            if val - lower < self.SINGLE_STEP_TOL:
                self.setSceneRect(self.sceneRect().adjusted(-page_step, 0, 0, 0))
                bar.setValue(val - single_step)

            self.__command_type = NavToViewCmdTypeEnum.slider_step

        elif slider_action == QAbstractSlider.SliderPageStepAdd:
            self.__command_type = NavToViewCmdTypeEnum.slider_step

        elif slider_action == QAbstractSlider.SliderPageStepSub:
            self.__command_type = NavToViewCmdTypeEnum.slider_step

        else:
            # The remaining slider actions won't cause view changes.
            pass

    def __on_vertical_scrollbar_triggered(self, slider_action: int):
        """
        Processes the vertical slider movements: sliding and steps.

        :param slider_action: the slider action emitted by the Qt.
        """
        bar = self.verticalScrollBar()
        val = bar.value()
        lower = bar.minimum()
        upper = bar.maximum()
        single_step = bar.singleStep()
        page_step = bar.pageStep()

        if slider_action == QAbstractSlider.SliderMove:
            self.__command_type = NavToViewCmdTypeEnum.vertical_slider_move

        elif slider_action == QAbstractSlider.SliderSingleStepAdd:
            if upper - val < self.SINGLE_STEP_TOL:
                self.setSceneRect(self.sceneRect().adjusted(0, 0, 0, page_step))
                bar.setValue(val + single_step)

            self.__command_type = NavToViewCmdTypeEnum.slider_step

        elif slider_action == QAbstractSlider.SliderSingleStepSub:
            if val - lower < self.SINGLE_STEP_TOL:
                self.setSceneRect(self.sceneRect().adjusted(0, -page_step, 0, 0))
                bar.setValue(val - single_step)

            self.__command_type = NavToViewCmdTypeEnum.slider_step

        elif slider_action == QAbstractSlider.SliderPageStepAdd:
            self.__command_type = NavToViewCmdTypeEnum.slider_step

        elif slider_action == QAbstractSlider.SliderPageStepSub:
            self.__command_type = NavToViewCmdTypeEnum.slider_step

        else:
            # The remaining slider actions won't cause view changes.
            pass

    def __shrink_scene(self, bar: QScrollBar):
        """
        Shrinks the scene if the slider touches neither the min nor the max of the given scroll bar.
        :param bar: The horizontal scroll bar or the vertical scroll bar.
        """
        val = bar.value()
        lower = bar.minimum()
        upper = bar.maximum()
        if val == lower or val == upper:
            return

        self.__set_view_center(self.mapToScene(self.viewport().rect().center()))

    def __on_horizontal_scrollbar_released(self):
        self.__shrink_scene(self.horizontalScrollBar())

    def __on_vertical_scrollbar_released(self):
        self.__shrink_scene(self.verticalScrollBar())

    def __check_moving_view(self, event: QMouseEvent) -> bool:
        """Return True if the event indicates that view is being moved over scene"""
        return event.buttons() == Qt.LeftButton and self.itemAt(event.pos()) is None

    def __check_view_changed(self):
        """
        Detects if a view change happens. If so, pushes a NavToViewCmd into the view nav stack.
        """
        assert self.__command_type is not None
        command_type = self.__command_type
        self.__command_type = None

        x_now, y_now = self.__center_truncated()
        x_prev, y_prev = self.__last_view_nav_center
        if x_now == x_prev and y_now == y_prev:
            # nothing to do:
            return

        if math.isclose(x_now, x_prev, abs_tol=self.VIEW_CENTER_CHANGE_TOL):
            x_now = x_prev

        if math.isclose(y_now, y_prev, abs_tol=self.VIEW_CENTER_CHANGE_TOL):
            y_now = y_prev

        center_now = (x_now, y_now)
        if (math.isclose(x_now, x_prev, abs_tol=self.VIEW_CENTER_CHANGE_TOL) and
                math.isclose(y_now, y_prev, abs_tol=self.VIEW_CENTER_CHANGE_TOL) and
                math.isclose(self.__zoom_slider_value,
                             self.__last_view_nav_zoom_slider_value,
                             abs_tol=self.ZOOM_CHANGE_TOL)):
            # The view has not changed, so no undo/redo
            log.debug("WARNING: The view has changed but only by < {}, no undo/redo for this view:",
                      self.VIEW_CENTER_CHANGE_TOL)
            log.debug("   old center {}:", self.__last_view_nav_center)
            log.debug("   new center {}:", center_now)
            log.debug("   old zoom {}:", self.__last_view_nav_zoom_slider_value)
            log.debug("   new zoom {}:", self.__zoom_slider_value)
            return

        log.debug("Viewport changed beyond tolerance due to {}, emitting.", command_type)
        self.sig_view_nav.emit(self.__last_view_nav_center, self.__last_view_nav_zoom_slider_value,
                               center_now, self.__zoom_slider_value,
                               command_type.value)

    __slot_on_horizontal_scrollbar_triggered = safe_slot(__on_horizontal_scrollbar_triggered)
    __slot_on_vertical_scrollbar_triggered = safe_slot(__on_vertical_scrollbar_triggered)
    __slot_on_horizontal_scrollbar_released = safe_slot(__on_horizontal_scrollbar_released)
    __slot_on_vertical_scrollbar_released = safe_slot(__on_vertical_scrollbar_released)
