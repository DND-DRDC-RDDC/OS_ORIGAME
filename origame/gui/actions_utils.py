# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Components related to managing user actions supported by the application

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from os import path, listdir

# [2. third-party]
from PyQt5.QtGui import QPixmap, QIcon, QKeySequence
from PyQt5.QtWidgets import QWidget, QAction, QToolButton, QMessageBox

# [3. local]
from ..core import override_required, override_optional
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..scenario.defn_parts import BasePart, ActorPart

from .gui_utils import exec_modal_dialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'create_action',
    'IMenuActionsProvider',
]

log = logging.getLogger('system')

IfxLevelLabels = List[Tuple[int, str]]
QActionSlot = Callable[[], None]  # action configured with checkable=False
QActionSlotCheckable = Callable[[bool], None]  # action configured with checkable=True


# -- Function definitions -----------------------------------------------------------------------

def create_action(parent: QWidget, text: str, name: str = None, **config_args) -> QAction:
    """
    Instantiate a QAction as child of parent and configure it according to the remaining arguments.

    :param parent: parent widget of the action
    :param text: the text that should appear in menu item or button for the action; text MUST contain at least
        one char because each widget that uses the action decides how to display its information (image, text etc)
    :param name: a QObject name for the action

    :return: the QAction created
    """
    # Create the action using the definition
    action = QAction(parent)

    assert text
    action.setText(text)
    if name is None:
        name = text.lower().replace(' ', '_')
    action.setObjectName(name)

    if config_args.get('tooltip', None) is None:
        tooltip = text

    if config_args.get('enabled', None) is None:
        enabled = True

    if config_args.get('checkable', None) is None:
        checkable = False

    config_action(action, **config_args)
    return action


def config_action(
        action: QAction,
        tooltip: str = None, shortcut: str = None, pix_path: str = None, button: QToolButton = None,
        checkable: bool = False, enabled: bool = None,
        connect: Either[QActionSlot, QActionSlotCheckable] = None):
    """
    Configure a QAction.

    :param action: the action to configure
    :param tooltip: the popup tip that appears when user hovers mouse over action object
    :param shortcut: the keyboard shortcut for the action
    :param pix_path: the resource path to the image for action
    :param button: a button to configure using the created action
    :param checkable: True if this is a checkmark action
    :param enabled: False if the initial state of the action should be disabled
    :param connect: the callable to signal when action triggered
    """

    if pix_path is not None:
        icon = QIcon()
        icon.addPixmap(QPixmap(pix_path), QIcon.Normal, QIcon.Off)
        action.setIcon(icon)

    if tooltip is not None:
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)

    if checkable is not None:
        action.setCheckable(checkable)

    if enabled is not None:
        action.setEnabled(enabled)

    if shortcut is not None:
        action.setShortcut(QKeySequence(shortcut))

    if connect is not None:
        action.triggered.connect(connect)

    if button is not None:
        button.setDefaultAction(action)

    return action


# -- Class Definitions --------------------------------------------------------------------------

class IMenuActionsProvider:
    """
    Derived classes that provide menu actions in the Edit and/or View menus must Implement this interface.
    The main window will use this to inform the derived class when its actions are in context.
    """

    @override_optional
    def get_edit_actions(self) -> List[QAction]:
        """Provide an ordered list of action items to add to the Edit menu"""
        return []

    @override_optional
    def get_view_actions(self) -> List[QAction]:
        """Provide an ordered list of action items to add to the View menu"""
        return []

    @override_optional
    def update_actions(self):
        """Enable the actions provided to menu. Some may be disabled, depending on state."""
        pass

    @override_optional
    def disable_actions(self):
        """Disable all the actions (edit and view) provided to menu."""
        pass


def verify_ifx_level_change_ok(part: BasePart, ifx_level: int):
    """
    Changes the specified part's interface level.
    :param part: The part specified
    :param ifx_level: The level
    :return: True if proceed with the command, False if cancel
    """
    # Launch a dialog if there will be broken links and ask the user if they'd like to continue.
    invalid = part.part_frame.get_invalid_links(ifx_level=ifx_level)
    if invalid.outgoing or invalid.incoming:
        title = 'Change Interface Level'
        msg = 'Changing the interface level of this part will break the following links:\n'
        from ..scenario.defn_parts import PartLink
        msg += ''.join('(out) {}\n'.format(link) for link in sorted(invalid.outgoing, key=PartLink.__str__))
        msg += ''.join('(in) {}\n'.format(link) for link in sorted(invalid.incoming, key=PartLink.__str__))
        msg += '\nClick OK to break the links and change the level, or CANCEL to go back.'
        user_input = exec_modal_dialog(title, msg, QMessageBox.Question,
                                       buttons=[QMessageBox.Ok, QMessageBox.Cancel])

        if user_input != QMessageBox.Ok:
            # user cancelled the operation
            return False

    return True


def get_labels_ifx_levels(part: BasePart) -> List[Tuple[int, str]]:
    """
    Returns a list of labels showing the ifx level and corresponding actor part name for each part
    in the hierarchy from part to root. They are returned in reverse order since the root is always shown first.
    The first member of each list item is the interface level, and the second its label.
    Format:
        3: root
        2: child1
        1: child11
        0: child111
    """
    ifx_labels = []
    parts_path = part.get_parts_path(with_root=True)
    max_levels = len(parts_path) - 1
    for index, parent_actor in enumerate(parts_path):
        ifx_level = max_levels - index
        text = '{}: {}'.format(ifx_level, parent_actor.name)
        ifx_labels.append((ifx_level, text))  # insert at start of list so root is first

    return ifx_labels


def get_labels_ifx_ports(part: BasePart, actor: ActorPart) -> Tuple[IfxLevelLabels, int]:
    """
    Returns a list of labels showing the ifx level and corresponding actor part name for each part port
    in the hierarchy with the exception of the part or the root. The part and root are excluded since there is no port
    to go to at those levels. They are returned in reverse order since the highest level is always shown first. The
    first member of each list item is the interface level, and the second its label.
    Format:
        3: child1
        2: child11
        1: child111
    :param part: The part associated with the port on the actor.
    :param actor: The actor on which the port appears.
    :returns: The label to display on the context menu (ifx level and text) and the ifx level currently being viewed.
    """
    ifx_labels = []
    parts_path = part.get_parts_path(with_root=True, with_part=False)
    max_level = len(parts_path)
    current_ifx_level = part.part_frame.ifx_level

    # Root-level ports at max Ifx cannot be viewed; so remove it
    if current_ifx_level == max_level:
        current_ifx_level -= 1

    # Remove all actors from path list without a port
    parts_path = parts_path[(max_level - current_ifx_level):]

    for index, parent_actor in enumerate(parts_path):
        ifx_level = current_ifx_level - index
        text = '{}: {}'.format(ifx_level, parent_actor.name)
        ifx_labels.append((ifx_level, text))  # insert at start of list so root is first

    assert actor in parts_path
    view_ifx_level = current_ifx_level - parts_path.index(actor)  # ifx level of the port we're viewing

    return ifx_labels, view_ifx_level

def get_batch_folders(scenario_path: path) -> list[str]:
    """
    Returns the list of batch folders in the given location.
    :param scenario_path: Location of the current open scenario
    :returns: A list of batch folders paths in the given location
    """
    batch_folders = []
    for file in sorted(listdir(scenario_path)):
        if path.isdir(path.join(scenario_path, file)) and file.startswith("batch_"):
            batch_folders.append(path.join(scenario_path, file))

    return batch_folders
