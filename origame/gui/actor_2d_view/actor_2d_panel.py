# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Actor 2D Panel components

It includes a view, toolbar, title bar, and makes use of one or more scenes (only one active at any moment).

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum

# [2. third-party]
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QWidget, QAction, QActionGroup, QFrame, QLabel, QVBoxLayout, QHBoxLayout, QToolButton
from PyQt5.QtWidgets import QSizePolicy
from PyQt5.QtGui import QColor, QPalette, QIcon
from PyQt5.Qt import Qt

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import BasePart, ActorPart, Position, InScenarioState
from ...scenario import Scenario, ScenarioManager
from ...scenario.alerts import IScenAlertSource

from ..async_methods import AsyncRequest
from ..conversions import map_from_scenario
from ..gui_utils import PART_ICON_COLORS, IScenarioMonitor, set_button_image, get_icon_path
from ..safe_slot import safe_slot
from ..undo_manager import scene_undo_stack, UndoCommandBase
from ..animation import IHasAnimationMode
from ..actions_utils import create_action, IMenuActionsProvider

from .Ui_view_panel_toolbar import Ui_Actor2dPanelToolbar
from .actor_2d_view import Actor2dView, ViewActions, EditActions
from .actor_2d_scene import Actor2dScene
from .common import DetailLevelOverrideEnum
from .view_nav_manager import ViewNavStack, NavToViewCmd, NavToViewCmdTypeEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # defines module members that are public; one line per string
    'Actor2dPanel',
    'ExpansionStatusEnum',
]

log = logging.getLogger('system')

# The intent is to have consistent height for all the title bars.
DEFAULT_TITLE_BAR_HEIGHT = 20

# use same gray color that is used in the dock window title bars from the current windows7 style
TITLE_BAR_COLOR = QColor(219, 219, 219)

# In case the client does not like the default button visual effects, which have a middle line dividing the
# background, we will use these style sheets.
HORIZONTAL_BUTTON_BACKGROUND_STYLE = ("QToolButton {"
                                      "background-color: "
                                      "qlineargradient(x1:0 y1:0, x2:0 y2:1, "
                                      "stop:0 rgb(240, 240, 240), stop:1 rgb(212, 212, 212)); "
                                      "border: 1px solid ;"
                                      "border-radius: 2px;}"
                                      ""
                                      "QToolButton:hover:!pressed{background-color: "
                                      "qlineargradient(x1:0 y1:0, x2:0 y2:1, "
                                      "stop:0 rgb(228, 244, 252), stop:1 rgb(181, 226, 250));}"
                                      ""
                                      "QToolButton:pressed{background-color: "
                                      "qlineargradient(x1:0 y1:0, x2:0 y2:1, "
                                      "stop:0 rgb(228, 244, 252), stop:1 rgb(171, 216, 240));}"
                                      )

VERTICAL_BUTTON_BACKGROUND_STYLE = ("QToolButton {"
                                    "background-color: "
                                    "qlineargradient(x1:0 y1:0, x2:1 y2:0, "
                                    "stop:0 rgb(240, 240, 240), stop:1 rgb(212, 212, 212)); "
                                    "border: 1px solid black;"
                                    "border-radius: 2px;}"
                                    ""
                                    "QToolButton:hover:!pressed{background-color: "
                                    "qlineargradient(x1:0 y1:0, x2:1 y2:0, "
                                    "stop:0 rgb(228, 244, 252), stop:1 rgb(181, 226, 250));}"
                                    ""
                                    "QToolButton:pressed{background-color: "
                                    "qlineargradient(x1:0 y1:0, x2:1 y2:0, "
                                    "stop:0 rgb(228, 244, 252), stop:1 rgb(171, 216, 240));}"
                                    )

EXPANSION_CHANGE_BUTTON_HORIZONTAL_SIZE_POLICY = QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
EXPANSION_CHANGE_BUTTON_VERTICAL_SIZE_POLICY = QSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)

ICON_EXPAND = QIcon(get_icon_path("expand.svg"))
ICON_COLLAPSE = QIcon(get_icon_path("compress.svg"))

# The expansion change button names, which are mainly used to facilitate testing
EXPANSION_CHANGE_ALL = "origame.gui.actor_2d_view.actor_2d_panel.expansion_change_all"
EXPANSION_CHANGE_LEFT = "origame.gui.actor_2d_view.actor_2d_panel.expansion_change_left"
EXPANSION_CHANGE_RIGHT = "origame.gui.actor_2d_view.actor_2d_panel.expansion_change_right"
EXPANSION_CHANGE_BOTTOM = "origame.gui.actor_2d_view.actor_2d_panel.expansion_change_bottom"


# -- Function definitions -----------------------------------------------------------------------
# -- Class Definitions --------------------------------------------------------------------------


class ExpansionStatusEnum(IntEnum):
    """
    Describes each expansion area's status, i.e., empty, visible, invisible
    """
    empty, visible, invisible = range(3)


class Actor2dPanelToolBar(QWidget):
    """
    Represents the tool bar used in the Actor2dPanel.
    """

    def __init__(self):
        super().__init__()
        self.ui = Ui_Actor2dPanelToolbar()
        self.ui.setupUi(self)


class ExpansionButtonStateEnum(IntEnum):
    """
    The arrow directions of the expansion change buttons. Note: The information is similar to the button icon state, but
    the enum comparison is more efficient than icon comparison in order to get the state info.
    """
    left, right, up, down, expand, collapse = range(6)


# noinspection PyUnresolvedReferences
class Actor2dPanel(IScenarioMonitor, IHasAnimationMode, IMenuActionsProvider, QWidget):
    """
    Central Widget containing a title bar, a command tool bar, the 2d view, etc.
    Responsible for communication between the MainWindow and the View.

    The panel creates one scene per actor visited, and tells the view which scene to use.

    NOTE: the scene MUST remain an implementation detail of the panel. The view is
    exposed.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    sig_part_selection_changed = pyqtSignal(list)  # list of BasePart
    sig_update_context_help = pyqtSignal(BasePart)  # part for context help
    sig_reset_context_help = pyqtSignal()  # Reset the context help menu when part removed
    sig_filter_events_for_part = pyqtSignal(BasePart)  # part for event filtering
    sig_open_part_editor = pyqtSignal(BasePart)  # part to edit
    sig_part_opened = pyqtSignal(BasePart)  # when a child actor is opened, or the parent button is clicked

    # Show or hide the panels in the specified area. The area id (int) is defined in enum Qt::DockWidgetArea in C++,
    # but but in PyQt, it is just one of the plain int definitions in the Qt class.
    sig_expansion_change = pyqtSignal(int)
    sig_alert_source_selected = pyqtSignal(IScenAlertSource)

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, scenario_manager: ScenarioManager = None):
        QWidget.__init__(self)
        IScenarioMonitor.__init__(self, scenario_manager)
        IHasAnimationMode.__init__(self)
        IMenuActionsProvider.__init__(self)

        layout_self = QVBoxLayout()
        layout_self.setSpacing(1)
        layout_self.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout_self)

        self.__title_bar = QFrame()
        self.__title_bar.setFixedHeight(DEFAULT_TITLE_BAR_HEIGHT)
        self.__title_bar.setFrameShape(QFrame.StyledPanel)
        self.__title_bar.setFrameShadow(QFrame.Sunken)
        self.__title_bar.setLineWidth(2)
        self._title_label = QLabel()

        color = PART_ICON_COLORS['actor']
        self.color = color
        self.__button_expansion_change_all = QToolButton(parent=self)
        self.__button_backward = QToolButton(parent=self)
        self.__button_forward = QToolButton(parent=self)
        self.__button_goto_parent = QToolButton(parent=self)
        self.__setup_button_goto_parent()
        self.__view_nav_stack = ViewNavStack()
        self.__button_backward.setDefaultAction(self.__view_nav_stack.createUndoAction(self))
        self.__button_forward.setDefaultAction(self.__view_nav_stack.createRedoAction(self))

        layout = QHBoxLayout()
        layout.setContentsMargins(1, 1, 1, 1)
        self.__title_bar.setLayout(layout)
        layout.addWidget(self.__button_expansion_change_all)
        layout.addWidget(self.__button_backward)
        layout.addWidget(self.__button_forward)
        layout.addWidget(self.__button_goto_parent)
        layout.addWidget(self._title_label)

        layout_self.addWidget(self.__title_bar)

        layout_toolbar_and_view = QHBoxLayout()
        layout_toolbar_and_view.setSpacing(1)
        layout_toolbar_and_view.setContentsMargins(0, 0, 0, 0)
        layout_including_bottom_expansion_change_button = QVBoxLayout()
        layout_including_bottom_expansion_change_button.addLayout(layout_toolbar_and_view)
        layout_expansion_change_bottom = QHBoxLayout()
        self.__button_expansion_change_bottom = QToolButton()
        # See the comments on HORIZONTAL_BUTTON_BACKGROUND_STYLE
        # self.__button_expansion_change_bottom.setStyleSheet(HORIZONTAL_BUTTON_BACKGROUND_STYLE)
        self.__button_expansion_change_bottom.setSizePolicy(EXPANSION_CHANGE_BUTTON_HORIZONTAL_SIZE_POLICY)
        layout_expansion_change_bottom.addWidget(self.__button_expansion_change_bottom)
        layout_including_bottom_expansion_change_button.addLayout(layout_expansion_change_bottom)
        layout_self.addLayout(layout_including_bottom_expansion_change_button, 1)

        self.__edit_actions = None
        self.__view_actions = None
        self.__toolbar_2d_panel = Actor2dPanelToolBar()
        self.setup_edit_actions()
        self.setup_view_actions()

        self.__button_expansion_change_left = QToolButton()
        # See the comments on HORIZONTAL_BUTTON_BACKGROUND_STYLE
        # self.__button_expansion_change_left.setStyleSheet(VERTICAL_BUTTON_BACKGROUND_STYLE)
        self.__button_expansion_change_left.setSizePolicy(EXPANSION_CHANGE_BUTTON_VERTICAL_SIZE_POLICY)
        layout_toolbar_and_view.addWidget(self.__button_expansion_change_left)
        layout_toolbar_and_view.addWidget(self.__toolbar_2d_panel)

        # one view and the multiple scenes (one per actor)
        self.__scenes = {}
        self.__current_scene = None
        self.__view = Actor2dView(self.edit_actions, self.view_actions)
        layout_toolbar_and_view.addWidget(self.__view)
        self.__button_expansion_change_right = QToolButton()
        # See the comments on HORIZONTAL_BUTTON_BACKGROUND_STYLE
        # self.__button_expansion_change_right.setStyleSheet(VERTICAL_BUTTON_BACKGROUND_STYLE)
        self.__button_expansion_change_right.setSizePolicy(EXPANSION_CHANGE_BUTTON_VERTICAL_SIZE_POLICY)
        layout_toolbar_and_view.addWidget(self.__button_expansion_change_right)
        self.__view.sig_view_nav.connect(self.__slot_view_nav)

        # which actor being shown:
        self.__content_actor = None

        self.__title_bar.setAutoFillBackground(True)
        palette = self.__title_bar.palette()
        palette.setColor(QPalette.Window, TITLE_BAR_COLOR)
        self.__title_bar.setPalette(palette)

        self._monitor_scenario_replacement()

        self.__button_expansion_change_all.setObjectName(EXPANSION_CHANGE_ALL)
        self.__button_expansion_change_left.setObjectName(EXPANSION_CHANGE_LEFT)
        self.__button_expansion_change_right.setObjectName(EXPANSION_CHANGE_RIGHT)
        self.__button_expansion_change_bottom.setObjectName(EXPANSION_CHANGE_BOTTOM)

        self.__button_expansion_change_all.clicked.connect(self.__slot_on_expansion_change_all)
        self.__button_expansion_change_left.clicked.connect(self.__slot_on_expansion_change_left)
        self.__button_expansion_change_right.clicked.connect(self.__slot_on_expansion_change_right)
        self.__button_expansion_change_bottom.clicked.connect(self.__slot_on_expansion_bottom)

        self.__map_expansion_area_to_button = {Qt.LeftDockWidgetArea: self.__button_expansion_change_left,
                                               Qt.RightDockWidgetArea: self.__button_expansion_change_right,
                                               Qt.BottomDockWidgetArea: self.__button_expansion_change_bottom}

        self.__map_expansion_rule_to_method = {
            ExpansionButtonStateEnum.expand:
                [
                    (Qt.LeftDockWidgetArea, ExpansionButtonStateEnum.left, self.__on_expansion_change_left),
                    (Qt.RightDockWidgetArea, ExpansionButtonStateEnum.right, self.__on_expansion_change_right),
                    (Qt.BottomDockWidgetArea, ExpansionButtonStateEnum.down, self.__on_expansion_change_bottom)
                ],
            ExpansionButtonStateEnum.collapse:
                [
                    (Qt.LeftDockWidgetArea, ExpansionButtonStateEnum.right, self.__on_expansion_change_left),
                    (Qt.RightDockWidgetArea, ExpansionButtonStateEnum.left, self.__on_expansion_change_right),
                    (Qt.BottomDockWidgetArea, ExpansionButtonStateEnum.up, self.__on_expansion_change_bottom)
                ]
        }

        self.__map_overall_area_to_icon = {
            ExpansionStatusEnum.empty: ICON_EXPAND,
            ExpansionStatusEnum.visible: ICON_EXPAND,
            ExpansionStatusEnum.invisible: ICON_COLLAPSE
        }

        self.__map_expansion_area_to_arrow_type = {
            Qt.LeftDockWidgetArea: {
                ExpansionStatusEnum.empty: Qt.LeftArrow,
                ExpansionStatusEnum.visible: Qt.LeftArrow,
                ExpansionStatusEnum.invisible: Qt.RightArrow},
            Qt.RightDockWidgetArea: {
                ExpansionStatusEnum.empty: Qt.RightArrow,
                ExpansionStatusEnum.visible: Qt.RightArrow,
                ExpansionStatusEnum.invisible: Qt.LeftArrow},
            Qt.BottomDockWidgetArea: {
                ExpansionStatusEnum.empty: Qt.DownArrow,
                ExpansionStatusEnum.visible: Qt.DownArrow,
                ExpansionStatusEnum.invisible: Qt.UpArrow}
        }

        self.__map_expansion_area_to_button_state_spec = {
            Qt.AllDockWidgetAreas: {
                ExpansionStatusEnum.empty: ExpansionButtonStateEnum.expand,
                ExpansionStatusEnum.visible: ExpansionButtonStateEnum.expand,
                ExpansionStatusEnum.invisible: ExpansionButtonStateEnum.collapse},
            Qt.LeftDockWidgetArea: {
                ExpansionStatusEnum.empty: ExpansionButtonStateEnum.left,
                ExpansionStatusEnum.visible: ExpansionButtonStateEnum.left,
                ExpansionStatusEnum.invisible: ExpansionButtonStateEnum.right},
            Qt.RightDockWidgetArea: {
                ExpansionStatusEnum.empty: ExpansionButtonStateEnum.right,
                ExpansionStatusEnum.visible: ExpansionButtonStateEnum.right,
                ExpansionStatusEnum.invisible: ExpansionButtonStateEnum.left},
            Qt.BottomDockWidgetArea: {
                ExpansionStatusEnum.empty: ExpansionButtonStateEnum.down,
                ExpansionStatusEnum.visible: ExpansionButtonStateEnum.down,
                ExpansionStatusEnum.invisible: ExpansionButtonStateEnum.up}
        }

        self.__map_expansion_area_to_button_state = {Qt.AllDockWidgetAreas: ExpansionButtonStateEnum.expand,
                                                     Qt.LeftDockWidgetArea: ExpansionButtonStateEnum.left,
                                                     Qt.RightDockWidgetArea: ExpansionButtonStateEnum.right,
                                                     Qt.BottomDockWidgetArea: ExpansionButtonStateEnum.down}

        self.__map_expansion_area_expansion_status = dict()

    def get_view_nav_stack(self) -> ViewNavStack:
        """
        Gets the view nav stack. Since the undo/redo command does not have the access to the stack based on the Qt, we
        publish it here.
        :return: The view nav stack
        """
        return self.__view_nav_stack

    @override(IMenuActionsProvider)
    def get_edit_actions(self) -> EditActions:
        """
        Get the list of Edit menu actions for the panel.
        :return: a list of QActions.
        """
        return self.__edit_actions

    def setup_edit_actions(self):
        """
        Define and set the Edit menu actions for this panel.
        """
        toolbar_ui = self.__toolbar_2d_panel.ui

        edit_actions_def = {
            'Cut': {
                'pix_path': ":/icons/cut.png",
                'text': 'Cut',
                'name': 'action_cut',
                'checkable': False,
                'tooltip': 'Cut the currently selected parts to app clipboard',
                'shortcut': 'Ctrl+X',
                'connect': self.slot_cut_selected_parts,
                'button': toolbar_ui.button_cut,
            },
            'Copy': {
                'pix_path': ":/icons/copy.png",
                'text': 'Copy',
                'name': 'action_copy',
                'checkable': False,
                'tooltip': 'Copy the currently selected parts to app clipboard',
                'shortcut': 'Ctrl+C',
                'connect': self.slot_copy_selected_parts,
                'button': toolbar_ui.button_copy,
            },
            'Paste': {
                'pix_path': ":/icons/paste.png",
                'text': 'Paste',
                'name': 'action_paste',
                'checkable': False,
                'tooltip': 'Paste parts from app clipboard into this actor',
                'shortcut': 'Ctrl+V',
                'connect': self.slot_paste,
                'button': toolbar_ui.button_paste,
            },
            'Delete': {
                'pix_path': ":/icons/delete.png",
                'text': 'Delete',
                'name': 'action_delete',
                'checkable': False,
                'tooltip': 'Delete the currently selected parts',
                'shortcut': 'Delete',
                'connect': self.slot_delete,
                'button': toolbar_ui.button_delete,
            },
        }

        self.__edit_actions = EditActions(cut_action=create_action(self, **edit_actions_def['Cut']),
                                          copy_action=create_action(self, **edit_actions_def['Copy']),
                                          paste_action=create_action(self, **edit_actions_def['Paste']),
                                          delete_action=create_action(self, **edit_actions_def['Delete']),
                                          undo_action=scene_undo_stack().get_action_undo(),
                                          redo_action=scene_undo_stack().get_action_redo())

        toolbar_ui.button_undo.setDefaultAction(scene_undo_stack().get_action_undo())
        toolbar_ui.button_redo.setDefaultAction(scene_undo_stack().get_action_redo())

    def get_view_actions(self) -> ViewActions:
        """
        Get the list of View menu actions for the panel.
        :return: a list of QActions.
        """
        return self.__view_actions

    def setup_view_actions(self):
        """
        Define and set the View menu actions for this panel.
        """
        toolbar_ui = self.__toolbar_2d_panel.ui

        # Note: we use action names like DetailLevelOverrideEnum.full.name for a purpose. The function
        # __activate_actor_scene will use the naming convention to identify which action is checked.
        view_actions_def = {
            'Override Full': {
                'text': 'Part Details: Override Full',
                'name': DetailLevelOverrideEnum.full.name,
                'checkable': True,
                'tooltip': 'Show full detail level by overriding the real detail level',
                'connect': self.slot_on_override_detail_level_full
            },
            'Override Minimal': {
                'text': 'Part Details: Override Minimal',
                'name': DetailLevelOverrideEnum.minimal.name,
                'checkable': True,
                'tooltip': 'Show minimal detail level by overriding the real detail level',
                'connect': self.slot_on_override_detail_level_minimal
            },
            'Override None': {
                'text': 'Part Details: Override None',
                'name': DetailLevelOverrideEnum.none.name,
                'checkable': True,
                'tooltip': 'Allow items to have their own detail level',
                'connect': self.slot_on_override_detail_level_none
            },
            'Zoom_2d_to_fit_all': {
                'text': 'Zoom to Fit All',
                'name': 'action_zoom_2d_to_fit_all',
                'checkable': False,
                'tooltip': 'Zoom to make all the parts fit in the view',
                'pix_path': get_icon_path("zoom_fit_all.svg"),
                'connect': self.__slot_on_zoom_to_fit_all,
                'button': toolbar_ui.button_zoom_to_fit_all,
            },
            'Zoom_2d_to_selection': {
                'text': 'Zoom to Selection',
                'name': 'action_zoom_2d_to_selection',
                'checkable': False,
                'tooltip': 'Zoom to make all the selected parts fit in the view',
                'pix_path': get_icon_path("zoom_fit_selection.svg"),
                'connect': self.__slot_on_zoom_to_selection,
                'button': toolbar_ui.button_zoom_to_selection,
            }
        }

        # Note: this particular order is based on the DetailLevelOverrideEnum. Since __view_actions is a list, the
        # order is important.
        self.__view_actions = ViewActions(
            action_override_full=create_action(self, **view_actions_def['Override Full']),
            action_override_minimal=create_action(self, **view_actions_def['Override Minimal']),
            action_override_none=create_action(self, **view_actions_def['Override None']),
            action_zoom_to_fit_all=create_action(self, **view_actions_def['Zoom_2d_to_fit_all']),
            action_zoom_to_selection=create_action(self, **view_actions_def['Zoom_2d_to_selection']))
        # Add some actions to an exclusive action group, so that the checkable menu items become radio buttons.
        detail_level_override_group = QActionGroup(self)
        detail_level_override_group.addAction(self.__view_actions.action_override_none)
        detail_level_override_group.addAction(self.__view_actions.action_override_full)
        detail_level_override_group.addAction(self.__view_actions.action_override_minimal)
        self.__view_actions.action_override_none.setChecked(True)

    @override(IMenuActionsProvider)
    def update_actions(self):
        """
        Enables or disables the actions of this panel depending on part selection state.

        Some actions require parts to be selected (Cut, Copy, Delete) in order to be enabled, while Paste requires items
        of the clipboard, and Undo and Redo are always enabled while the panel is in focus.
        """
        if self.__current_scene is None:
            return

        log.debug("Model view (2d panel) updating its actions")
        self.__view.update_edit_actions()
        scene_undo_stack().setActive(True)

    @override(IMenuActionsProvider)
    def disable_actions(self):
        """
        Disables all actions.
        """
        for action in self.__edit_actions:
            action.setEnabled(False)
        scene_undo_stack().setActive(False)

    def show_part_in_parent_actor(self, child_part: BasePart):
        """
        Change the view so that the parent of given part is the current actor, and the part is selected and
        near the center of the view.
        :param child_part: The child part to show.
        """
        center_to_go, parent_actor, selected_parts = self.__get_scene_content_actor_info(child_part)

        curr_view = dict(actor=self.__content_actor,
                         center=self.__view.last_view_nav_center,
                         zoom_factor=self.__view.last_view_nav_zoom_slider_value)
        new_view = dict(actor=parent_actor,
                        center=(center_to_go.x, center_to_go.y),
                        zoom_factor=Actor2dView.DEFAULT_ZOOM_SLIDER_VALUE,
                        selected_parts=selected_parts)

        self.__view_nav_stack.push(NavToViewCmd(curr_view, new_view, actor_2d_panel=self))

    def show_actor_ifx_port_in_parent_actor(self, child_actor: ActorPart, ifx_port: BasePart):
        """
        Change the view so that the parent of given child actor part is the current actor, and the ifx port on the child
        actor is selected and near the center of the view.
        :param child_actor: The child actor part the ifx port is on.
        :param ifx_port: The interface port on the child actor to show.
        """
        center_to_go, parent_actor, _ = self.__get_scene_content_actor_info(child_actor)

        curr_view = dict(actor=self.__content_actor,
                         center=self.__view.last_view_nav_center,
                         zoom_factor=self.__view.last_view_nav_zoom_slider_value)
        new_view = dict(actor=parent_actor,
                        center=(center_to_go.x, center_to_go.y),
                        zoom_factor=Actor2dView.DEFAULT_ZOOM_SLIDER_VALUE,
                        selected_ifx_port=ifx_port)

        self.__view_nav_stack.push(NavToViewCmd(curr_view, new_view, actor_2d_panel=self))

    def nav_to_actor(self, actor: ActorPart):
        """
        Show a different actor from current.
        :param actor: The actor to be displayed.
        """
        if actor is not self.__content_actor:
            self.__view_nav_stack.push(NavToViewCmd(current_view=dict(actor=self.__content_actor),
                                                    new_view=dict(actor=actor),
                                                    actor_2d_panel=self))

    def nav_relative(self, *part_names: List[str]):
        """
        Show a different actor from current.
        :param *part_names: list of relative paths from currently displayed actor. A part name that is
            ".." indicates "go up".

        Example: nav_relative("..", "..", "abc") would show the actor that is named abc, child of the
        grandparent of current actor.
        """
        actor = self.__content_actor
        for part_name in part_names:
            if part_name == '..':
                actor = actor.get_parent_actor_part()
            else:
                actor = actor.get_child_by_name(part_name)
        self.__view_nav_stack.push(NavToViewCmd(current_view=dict(actor=self.__content_actor),
                                                new_view=dict(actor=actor),
                                                actor_2d_panel=self))

    def set_content_actor(self, actor: ActorPart, force_new_scene: bool = False,
                          center: Position = None, zoom_factor: float = None,
                          selected_parts: List[BasePart] = None, selected_ifx_port: BasePart = None,
                          command_type: NavToViewCmdTypeEnum = None):
        """
        Called when we want to display the children of an actor. If the center of the view on the scene and the zoom
        factor are specified, the view will be displayed at the given center and with the given zoom factor.
        If the selected_parts is specified, this function will highlight the selected parts.
        If the selected_ifx_port is specified, this function will highlight it.

        Note: This function must only be called directly when no NavToViewCmd is not required.

        :param actor: The actor to be used for this panel.
        :param force_new_scene: Set to True to generate a new scene even if there already exists one for actor
        :param center: The center where the undo/redo needs to go.
        :param zoom_factor: The zoom factor that undo/redo needs to use.
        :param selected_parts: Parts to select upon completion.
        :param selected_ifx_port: The interface port to select upon completion.
        :param command_type: The command that drives the view change.
        """
        assert isinstance(actor, ActorPart)

        def activate():
            self.__activate_actor_scene(actor.SESSION_ID, command_type)
            if selected_parts is not None:
                self.select_parts(selected_parts)
            if selected_ifx_port is not None:
                self.select_ifx_port(selected_ifx_port)

        if force_new_scene or actor.SESSION_ID not in self.__scenes:
            # trigger creation of a new scene instance

            def get_new_content_data() -> List[BasePart]:
                return actor.children[:]

            def create_new_scene(children: List[BasePart]):
                self.__create_new_scene(actor, children, center, zoom_factor)
                activate()

            AsyncRequest.call(get_new_content_data, response_cb=create_new_scene)

        else:
            # update view center/zoom then activate the existing scene instance
            scene = self.__scenes[actor.SESSION_ID]
            if center is not None:
                scene.view_center_2d = center
            if zoom_factor is not None:
                scene.zoom_factor_2d = zoom_factor
            activate()

    def get_current_actor(self) -> BasePart:
        """Get the currently displayed actor"""
        return self.__content_actor

    def check_showing_actor(self, name: str = None) -> bool:
        """
        Check whether the 2d view is currently showing an actor.
        :param name: the name of actor part being shown; None to test if showing *any* actor at all
        :return: True if showing an actor (and if name given, its name matches 'name'). False otherwise.
        """
        if name:
            return self.__content_actor is not None and self.__content_actor.name == name
        else:
            return self.__content_actor is not None

    def get_current_scene(self) -> Actor2dScene:
        """Get the scene currently visible in the view"""
        return self.__current_scene

    def get_view(self) -> Actor2dView:
        """Get the Actor2dView instance managed by this panel."""
        return self.__view

    def select_parts(self, parts: List[BasePart]):
        """Unselect all and select given parts"""
        part_items = self.__current_scene.get_child_part_items(subset=parts)
        self.__current_scene.set_multi_selection(part_items)

    def select_ifx_port(self, ifx_port: BasePart):
        """Unselect all and select given interface port"""
        self.__current_scene.select_ifx_port_item(ifx_port)

    def get_selected_objects(self) -> List[BasePart]:
        """Get the list of selected scenario objects (parts, waypoints, or a link)"""
        return self.__current_scene.get_selected_objects()

    def cut_selected_parts(self):
        """
        Command the backend to remove whatever parts are selected in the Actor 2D View, after adding
        them to the clipboard.
        """
        self.__view.cut_selected_parts()

    def copy_selected_parts(self):
        """
        Add whatever parts are selected in the Actor 2D View to the scenario clipboard.
        """
        self.__view.copy_selected_parts()

    def paste_clipboard(self):
        """
        Command the backend to paste whatever is in the clipboard (per last cut or last copy operation).
        """
        self.__view.paste_clipboard()

    def delete_selected_items(self):
        """
        Command the backend to delete whatever items are selected in the Actor 2D View.
        """
        self.__view.delete_selected_items()

    def undo(self, checked: bool = None):
        """
        Undo the scenario edit command that is current on the undo stack.
        """
        scene_undo_stack().undo()

    def redo(self, checked: bool = None):
        """
        Redo the scenario edit command that is current on the undo stack.
        """
        scene_undo_stack().redo()

    def on_command_undone(self, command: UndoCommandBase):
        """Some commands required that the view be notified when they are undone"""
        self.__view.on_command_undone(command)

    def on_command_redone(self, command: UndoCommandBase):
        """Some commands required that the view be notified when they are done/redone"""
        self.__view.on_command_redone(command)

    def on_filter_events_for_part(self, filter_part: BasePart):
        """
        Called from components inside the panel when an event filter for a particular part is requested.
        :param filter_part: The part to filter events on, ie only show events in the Simulation Event Queue Panel that
            belong to this part.
        """
        self.sig_filter_events_for_part.emit(filter_part)

    def on_override_detail_level_none(self):
        """
        Update the view to show part detail after it is overridden by Override Full, Override Minimal, or Override None,
        based on the current setting of the associated View action objects.
        """
        self.__current_scene.override_detail_level(DetailLevelOverrideEnum.none)

    def on_override_detail_level_full(self):
        """
        Update the view to show part detail after it is overridden by Override Full, Override Minimal, or Override None,
        based on the current setting of the associated View action objects.
        """
        self.__current_scene.override_detail_level(DetailLevelOverrideEnum.full)

    def on_override_detail_level_minimal(self):
        """
        Update the view to show part detail after it is overridden by Override Full, Override Minimal, or Override None,
        based on the current setting of the associated View action objects.
        """
        self.__current_scene.override_detail_level(DetailLevelOverrideEnum.minimal)

    def on_expansion_changed(self, area: int, expansion_status: ExpansionStatusEnum):
        """
        Asks the panel to show different icons on the expansion change buttons, depending on the current status of the
        panels.
        :param area: The area where the button is updated 
        :param expansion_status: The status of this area
        """
        button = self.__map_expansion_area_to_button[area]
        button.setArrowType(self.__map_expansion_area_to_arrow_type[area][expansion_status])
        button.setEnabled(expansion_status != ExpansionStatusEnum.empty)
        button_state = self.__map_expansion_area_to_button_state_spec[area][expansion_status]
        self.__map_expansion_area_to_button_state[area] = button_state

        self.__map_expansion_area_expansion_status[area] = expansion_status
        self.__present_overall_button()

    # --------------------------- instance (self) PUBLIC methods --------------------------------
    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_cut_selected_parts = safe_slot(cut_selected_parts)
    slot_copy_selected_parts = safe_slot(copy_selected_parts)
    slot_paste = safe_slot(paste_clipboard)
    slot_delete = safe_slot(delete_selected_items)
    slot_undo = safe_slot(undo)
    slot_redo = safe_slot(redo)
    slot_on_filter_events_for_part = safe_slot(on_filter_events_for_part)
    slot_on_override_detail_level_none = safe_slot(on_override_detail_level_none)
    slot_on_override_detail_level_full = safe_slot(on_override_detail_level_full)
    slot_on_override_detail_level_minimal = safe_slot(on_override_detail_level_minimal)
    slot_nav_to_actor = safe_slot(nav_to_actor)
    slot_show_part_in_parent_actor = safe_slot(show_part_in_parent_actor)
    slot_show_actor_ifx_port_in_parent_actor = safe_slot(show_actor_ifx_port_in_parent_actor)
    slot_on_expansion_changed = safe_slot(on_expansion_changed)

    edit_actions = property(get_edit_actions)
    view_actions = property(get_view_actions)
    view = property(get_view)
    current_actor = property(get_current_actor)
    current_scene = property(get_current_scene)
    view_nav_stack = property(get_view_nav_stack)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IHasAnimationMode)
    def _on_animation_mode_enabled(self):
        """
        When animation resumes, refresh the scene entirely, but don't loose the viewport;
        the actor for the current scene may even have been deleted, if that's the case then find
        the nearest one up the actor hierarchy
        """
        self.__view.set_animated()
        self.__toolbar_2d_panel.setEnabled(True)
        self.__title_bar.setEnabled(True)

        refresh_actor = self.__content_actor
        if refresh_actor.in_scenario_state != InScenarioState.active:
            # find the nearest parent that is active
            parent_actor = refresh_actor.parent_actor_part
            while parent_actor is not None:
                if parent_actor.in_scenario_state == InScenarioState.active:
                    refresh_actor = parent_actor
                    break
                else:
                    parent_actor = refresh_actor.parent_actor_part

        # if none was found, use root:
        if refresh_actor.in_scenario_state != InScenarioState.active:
            refresh_actor = self.__root_actor

        assert refresh_actor.in_scenario_state == InScenarioState.active
        self.set_content_actor(refresh_actor, force_new_scene=True)

    @override(IHasAnimationMode)
    def _on_animation_mode_disabled(self):
        """
        When animation is disabled, no actions are allowed in the panel.
        """
        self.__view.save_current_viewport()
        self.__view.set_animated(False)
        self.__toolbar_2d_panel.setDisabled(True)
        self.__title_bar.setDisabled(True)

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        """
        Replace the scenario being referenced by this panel. The root actor of the scenario will be shown by default.
        """
        self.__view_nav_stack.clear()
        self.__scenes.clear()
        self.__root_actor = scenario.scenario_def.root_actor
        assert self.__root_actor.in_scenario_state == InScenarioState.active
        self.set_content_actor(self.__root_actor)
        self.monitor_animation_changes(scenario.sim_controller)
        scene_undo_stack().clear()

    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __create_new_scene(self, actor: ActorPart, children: List[BasePart], center: Position, zoom_factor: float):
        """
        Create a new scene instance for an actor, discarding the previous one if any.
        :param actor: Actor instance for which to create scene
        :param children: The actor's children
        :param center: where in scene to center the view
        :param zoom_factor: what scaling factor to use to view scene around center of view
        """
        # if actor has already been visited, then previous scene for it has connections to break, and view
        # info needs copying over
        if actor.SESSION_ID in self.__scenes:
            prev_scene = self.__scenes[actor.SESSION_ID]
            del self.__scenes[actor.SESSION_ID]

            # keep same viewport, unless overridden by call args:
            use_center = prev_scene.view_center_2d if center is None else center
            use_zoom_factor = prev_scene.zoom_factor_2d if zoom_factor is None else zoom_factor

        else:
            use_center = center
            use_zoom_factor = zoom_factor

        self.__scenes[actor.SESSION_ID] = Actor2dScene(actor, children, use_center, use_zoom_factor)

    def __get_scene_content_actor_info(self, part):
        """
        Gets the information required to show the given part at the center of its parent actor.
        :param part: The part to show at center of the content actor.
        :return: The part's scene location to center the view on, the parent ('content') actor it's in, part to select.
        """
        part_frame = part.part_frame
        if part.is_root:
            parent_actor = part
            center_to_go = Position()
            selected_parts = None
        else:
            parent_actor = part.parent_actor_part
            pos_scenario = Position(part_frame.pos_x, part_frame.pos_y)
            to_scene = map_from_scenario(pos_scenario)
            center_to_go = Position(to_scene.x(), to_scene.y())
            selected_parts = [part]
        return center_to_go, parent_actor, selected_parts

    def __activate_actor_scene(self, actor_id: int, command_type: Optional[NavToViewCmdTypeEnum]):
        """
        Activate the scene associated to an actor into the panel's 2d view.
        :param actor_id: the actor for which scene should be activated
        :param command_type: The command that drives the view change.
        """
        new_scene = self.__scenes[actor_id]
        if new_scene is self.__current_scene:
            assert self.__current_scene.content_actor is self.__content_actor
            self.__view.setup_viewport(new_scene.view_center_2d, new_scene.zoom_factor_2d, command_type)
            return

        if self.__current_scene is not None:
            # disconnect from previous scene:
            self.__current_scene.sig_part_selection_changed.disconnect(self.sig_part_selection_changed)
            self.__current_scene.sig_alert_source_selected.disconnect(self.sig_alert_source_selected)
            self.__current_scene.sig_nav_to_actor.disconnect(self.slot_nav_to_actor)
            self.__current_scene.sig_show_child_part.disconnect(self.slot_show_part_in_parent_actor)
            self.__current_scene.sig_show_ifx_port.disconnect(self.slot_show_actor_ifx_port_in_parent_actor)
            self.__current_scene.sig_filter_events_for_part.disconnect(self.slot_on_filter_events_for_part)
            self.__current_scene.sig_update_context_help.disconnect(self.sig_update_context_help)
            self.__current_scene.sig_reset_context_help.disconnect(self.sig_reset_context_help)
            self.__current_scene.sig_open_part_editor.disconnect(self.sig_open_part_editor)
            # disconnect from previous actor:
            self.__content_actor.part_frame.signals.sig_name_changed.disconnect(self.__slot_on_part_renamed)
            self.__content_actor.base_part_signals.sig_in_scenario.disconnect(self.__slot_in_scenario_changed)

        # connect to new scene:
        new_scene.sig_part_selection_changed.connect(self.sig_part_selection_changed)
        new_scene.sig_alert_source_selected.connect(self.sig_alert_source_selected)
        new_scene.sig_nav_to_actor.connect(self.slot_nav_to_actor)
        new_scene.sig_show_child_part.connect(self.slot_show_part_in_parent_actor)
        new_scene.sig_show_ifx_port.connect(self.slot_show_actor_ifx_port_in_parent_actor)
        new_scene.sig_filter_events_for_part.connect(self.slot_on_filter_events_for_part)
        new_scene.sig_update_context_help.connect(self.sig_update_context_help)
        new_scene.sig_reset_context_help.connect(self.sig_reset_context_help)
        new_scene.sig_open_part_editor.connect(self.sig_open_part_editor)

        # connect to new actor:
        new_actor = new_scene.content_actor
        assert new_actor.SESSION_ID == actor_id
        new_actor.part_frame.signals.sig_name_changed.connect(self.__slot_on_part_renamed)
        new_actor.base_part_signals.sig_in_scenario.connect(self.__slot_in_scenario_changed)

        log.debug('Actor2dPanel activating scene for actor {}', new_actor)

        self.__current_scene = new_scene
        self.__content_actor = new_actor

        self.__view.setScene(new_scene)

        # update title bar
        self.__update_title(new_actor.get_path(with_root=True))
        nav_up_possible = not new_actor.is_root
        self.__button_goto_parent.setEnabled(nav_up_possible)
        self.__button_goto_parent.setVisible(nav_up_possible)

        # update detail level:
        detail_override_group = self.__view_actions.action_override_none.actionGroup()
        self.__current_scene.override_detail_level(
            DetailLevelOverrideEnum[detail_override_group.checkedAction().objectName()])

        # update actions:
        self.update_actions()

        # notify:
        self.sig_reset_context_help.emit()
        self.sig_part_opened.emit(new_actor)
        self.sig_part_selection_changed.emit(new_scene.get_selected_objects())

        self.__view.setup_viewport(new_scene.view_center_2d, new_scene.zoom_factor_2d, command_type)

    def __setup_button_goto_parent(self):
        """
        Helper method to set up properties of the Go 'up' to parent button.
        """
        set_button_image(self.__button_goto_parent, get_icon_path("shortcut_gotoparent.svg"))
        self.__button_goto_parent.clicked.connect(self.__slot_on_select_parent)
        self.__button_goto_parent.setToolTip("Go to Parent Actor")

    def __on_content_actor_renamed(self):
        AsyncRequest.call(self.__content_actor.get_path, True, response_cb=self.__update_title)

    def __update_title(self, title: str):
        """Prettify the title bar"""
        self._title_label.setText(" " + title)

    def __on_select_parent(self):
        """
        Make the parent of the current content actor the new content actor. Will create the scene for it if
        it doesn't exist.
        """
        parent = self.__content_actor.parent_actor_part
        if parent is not None:
            self.nav_to_actor(parent)
        else:
            log.debug("BUG: Attempt to go to parent of root actor")

    def __in_scenario_changed(self, in_scenario: bool):
        """When current actor is removed from scenario, need to change to new actor"""
        if not in_scenario:
            first_parent_part_in_scenario = self.__content_actor.in_scenario_parent
            self.set_content_actor(first_parent_part_in_scenario)

    def __on_zoom_to_fit_all(self):
        """
        Zooms to make all the parts fit in the view.
        """
        self.__view.fit_content_in_view()

    def __on_zoom_to_selection(self):
        """
        Zooms to make all the parts fit in the view.
        """
        self.__view.fit_selection_in_view()

    def __view_nav(self,
                   prev_center: Tuple[float, float], prev_zoom_factor: float,
                   new_center: Tuple[float, float], new_zoom_factor: float,
                   cmd_type: int):
        """
        Uses two sets of the states and the command type to push a command to the undo stack.
        :param prev_center: the view center before the change
        :param prev_zoom_factor: the zoom factor before the change
        :param new_center: the view center after the change
        :param new_zoom_factor: the zoom factor after the change
        :param cmd_type: The command type that matches the int value of the NavToViewCmdTypeEnum
        """
        curr_view = dict(actor=self.__content_actor,
                         center=prev_center,
                         zoom_factor=prev_zoom_factor)
        new_view = dict(actor=self.__content_actor,
                        center=new_center,
                        zoom_factor=new_zoom_factor)
        log.debug("Navigating to new viewport for actor {}:", self.__content_actor)
        if new_center != prev_center:
            log.debug("    changing center from {} to {}", prev_center, new_center)
        if new_zoom_factor != prev_zoom_factor:
            log.debug("    changing zoom from {} to {}", prev_zoom_factor, new_zoom_factor)

        self.__view_nav_stack.push(NavToViewCmd(curr_view,
                                                new_view,
                                                actor_2d_panel=self,
                                                command_type=NavToViewCmdTypeEnum(cmd_type)))

    def __present_overall_button(self):
        """
        Presents the overall button. For now, it sets the right icon, depending on the status of each individual
        expansion area.
        """
        overall_empty = all([status == ExpansionStatusEnum.empty
                             for status in self.__map_expansion_area_expansion_status.values()])

        if overall_empty:
            status = ExpansionStatusEnum.empty
        else:
            overall_visible = any([status == ExpansionStatusEnum.visible
                                   for status in self.__map_expansion_area_expansion_status.values()])
            status = ExpansionStatusEnum.visible if overall_visible else ExpansionStatusEnum.invisible

        self.__button_expansion_change_all.setEnabled(not overall_empty)
        self.__button_expansion_change_all.setIcon(self.__map_overall_area_to_icon[status])
        button_state = self.__map_expansion_area_to_button_state_spec[Qt.AllDockWidgetAreas][status]
        self.__map_expansion_area_to_button_state[Qt.AllDockWidgetAreas] = button_state

    def __on_expansion_change_all(self):
        """
        Sends a signal to change expansion in all areas.
        """
        expansion_all_btn_state = self.__map_expansion_area_to_button_state[Qt.AllDockWidgetAreas]
        for area, direction, method in self.__map_expansion_rule_to_method[expansion_all_btn_state]:
            if self.__map_expansion_area_to_button_state[area] == direction:
                method()

    def __on_expansion_change_left(self):
        """
        Sends a signal to change expansion on the left.
        """
        self.sig_expansion_change.emit(Qt.LeftDockWidgetArea)

    def __on_expansion_change_right(self):
        """
        Sends a signal to change expansion on the right.
        """
        self.sig_expansion_change.emit(Qt.RightDockWidgetArea)

    def __on_expansion_change_bottom(self):
        """
        Sends a signal to change expansion at the bottom.
        """
        self.sig_expansion_change.emit(Qt.BottomDockWidgetArea)

    __slot_on_zoom_to_fit_all = safe_slot(__on_zoom_to_fit_all)
    __slot_on_zoom_to_selection = safe_slot(__on_zoom_to_selection)
    __slot_on_select_parent = safe_slot(__on_select_parent)
    __slot_on_part_renamed = safe_slot(__on_content_actor_renamed)
    __slot_in_scenario_changed = safe_slot(__in_scenario_changed)
    __slot_view_nav = safe_slot(__view_nav)
    __slot_on_expansion_change_all = safe_slot(__on_expansion_change_all)
    __slot_on_expansion_change_left = safe_slot(__on_expansion_change_left)
    __slot_on_expansion_change_right = safe_slot(__on_expansion_change_right)
    __slot_on_expansion_bottom = safe_slot(__on_expansion_change_bottom)
