# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Actor 2D View Navigation Management.

It has the features offered by the Qt's Undo Framework. The navigation means the user can show the Actor 2D View, view
by view, by using backward action and forward action. The backward action is associated with an undo concept in the
Qt; forward redo.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum

# [2. third-party]
from PyQt5.QtWidgets import QUndoStack, QUndoCommand
from PyQt5.QtCore import QObject, QTimer

# [3. local]
from ...core import override
from ...core.typing import AnnotationDeclarations
from ...scenario.defn_parts import Position
from ..actions_utils import config_action
from ..gui_utils import get_icon_path

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 6966 $"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # API to support the view navigation
    'NavToViewCmd',
    'NavToViewCmdTypeEnum'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------


class Decl(AnnotationDeclarations):
    Actor2dPanel = 'Actor2dPanel'


class NavToViewCmdTypeEnum(IntEnum):
    """
    Commands need an id to accomplish merging. The enum is used as an id. For example, the mouse wheeling will
    generate successive view changes. We want to merge those changes into one change to make the undo/redo
    user experiences better.
    
    Examples:
        In the Actor2dView class, if a view navigation happens due to one of the reasons defined in the enum, we
        set the correspondent enum to the self.__command_type. The viewportEvent() is driven by the Qt framework for
        any kinds of view port events, which include those events we are interested in. If it sees None in
        self.__command_type, it does nothing; otherwise, it process the command, then resets the 
        self.__command_type to None.
    """
    (fit_content_in_view,
     mouse_dragged,
     horizontal_slider_move,
     vertical_slider_move,
     slider_step,
     zoom) = range(6)


class ViewNavStack(QUndoStack):
    """
    It tracks the backward and forward navigation of the actor 2d view.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        """
        The view navigation stack for the actor_2d_panel
        :param actor_2d_panel: The panel where the view nav stack resides.
        """
        super().__init__()
        self.clear()
        self.setObjectName("ViewNavStack")

    @override(QUndoStack)
    def createRedoAction(self, parent: QObject, prefix: str = ''):
        """
        Configures and returns an action that has a tooltip "Forward" and a forward icon.
        :return: The action used to do the "Forward" navigation.
        """
        action = super().createRedoAction(parent, prefix)
        config_action(action,
                      tooltip='Forward',
                      pix_path=get_icon_path("forward.svg")
                      )
        return action

    @override(QUndoStack)
    def createUndoAction(self, parent: QObject, prefix: str = ''):
        """
        Configures and returns an action that has a tooltip "Backward" and a backward icon.
        :return: The action used to do the "Backward" navigation.
        """
        action = super().createUndoAction(parent, prefix)
        config_action(action,
                      tooltip='Backward',
                      pix_path=get_icon_path("backward.svg")
                      )
        return action


class NavToViewCmd(QUndoCommand):
    """
    It presents the view based on the information passed in when it is pushed to the ViewNavStack.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------
    def __init__(self, current_view: {}, new_view: {},
                 actor_2d_panel: Decl.Actor2dPanel,
                 command_type: NavToViewCmdTypeEnum = NavToViewCmdTypeEnum.fit_content_in_view):
        """
        Constructs a view nav command by using two view parameter dictionaries and a command type. The command type
        must be used if you want to merge the commands. The keys in the view dictionaries must match
        the arguments (or a subset of them) of the set_content_actor of the Actor2dPanel.

        :param current_view: The parameters in a dictionary for undo
        :param new_view: The parameters in a dictionary for redo
        :param actor_2d_panel: The panel this command uses to change the view.
        :param command_type: The type that is used to do command merging.
        """
        super().__init__()
        self.__current_view = current_view
        self.__new_view = new_view
        self.__actor_2d_panel = actor_2d_panel
        self.__command_type = command_type

    @override(QUndoCommand)
    def redo(self):
        """
        Displays the current view. If the actor associated with the view is deleted, it will proceed to run
        the next redo.
        """
        actor = self.__new_view.get('actor')
        if actor.in_scenario:
            self.__set_view(self.__new_view)
        else:
            log.warning("Skip the redo because the actor ({}) is not in the scenario anymore. ", actor.name)
            QTimer.singleShot(0, self.__actor_2d_panel.view_nav_stack.redo)

    @override(QUndoCommand)
    def undo(self):
        """
        Displays the previous view. If the actor associated with the view is deleted, it will proceed to run
        the next undo.
        """
        actor = self.__current_view.get('actor')
        if actor.in_scenario:
            self.__set_view(self.__current_view)
        else:
            log.warning("Skip the undo because the actor ({}) is not in the scenario anymore. ", actor.name)
            QTimer.singleShot(0, self.__actor_2d_panel.view_nav_stack.undo)

    @override(QUndoCommand)
    def id(self) -> int:
        """
        Returns the command type set by the constructor. If the command type is None, the super().id() will be returned.
        :return: The command type or the super().id()
        """
        if self.__command_type in [NavToViewCmdTypeEnum.fit_content_in_view,
                                   NavToViewCmdTypeEnum.slider_step,
                                   NavToViewCmdTypeEnum.mouse_dragged]:
            return super().id()
        else:
            return self.__command_type.value

    @override(QUndoCommand)
    def mergeWith(self, cmd: QUndoCommand) -> bool:
        """
        Returns True. Before it returns, it copies the data from the cmd to this command. In other words, the latest
        command's data will be used when the redo of the merged command is run.
        :return: True
        """
        self.__new_view = cmd.new_view
        return True

    def get_new_view(self):
        return self.__new_view

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    new_view = property(get_new_view)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __set_view(self, view: {}):
        """
        Displays the view based on the data in the view dictionary. The keys in the view dictionary must match
        the arguments (or a subset of them) of the set_content_actor of the Actor2dPanel.
        :param view: The view dictionary that represents the arguments of the set_content_actor.
        """
        actor = view.get('actor')
        center = view.get('center')
        if center is not None:
            center = Position.from_tuple(center)

        zoom_factor = view.get('zoom_factor')
        selected_parts = view.get('selected_parts')
        selected_ifx_port = view.get('selected_ifx_port')
        self.__actor_2d_panel.set_content_actor(actor=actor,
                                                center=center,
                                                zoom_factor=zoom_factor,
                                                selected_parts=selected_parts,
                                                selected_ifx_port=selected_ifx_port,
                                                command_type=self.__command_type)
