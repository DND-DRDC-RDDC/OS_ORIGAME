# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Functions, classes, constants common to multiple editors

Version History: See SVN log.
"""
from enum import IntEnum

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path
from enum import IntEnum

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QDialog
from PyQt5.Qt import Qt

# [3. local]
from ...core import override_required
from ...core.typing import Any, Either, Optional, List, Tuple, Set, Dict, Callable
from ...gui.part_editors.Ui_preview_widget import Ui_PreviewWidget
from ..gui_utils import set_default_dialog_frame_flags

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'EditorDialog',
    'IPreviewWidget',
    'DialogHelp'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class EditorDialog(QDialog):
    """
    The base class for part editor dialogs used to set Window's flags so that the context help '?' is hidden.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        set_default_dialog_frame_flags(self)


class IPreviewWidget(QWidget):
    """
    Base class for part editor preview panels.
    """

    def __init__(self, set_wait_mode_callback: Callable[[bool], None] = None):
        """
        Initialization of base UI.
        :param set_wait_mode_callback: A method to call to place the preview widget and it's panel into wait mode.
        """
        super().__init__()
        self.ui = Ui_PreviewWidget()
        self.ui.setupUi(self)
        self.__display_widget = None
        self._set_wait_mode_callback = set_wait_mode_callback

    @override_required
    def update(self):
        """
        Each specific preview widget must implement this function to update the preview panel.
        """
        raise NotImplementedError('Implementation needed.')

    def add_display_widget(self, display_widget: QWidget):
        """
        Add the widget used to display the preview content to the UI of the preview widget.
        :param display_widget: The widget component used to display the preview content.
        """
        self.__display_widget = display_widget
        self.ui.tab.layout().addWidget(display_widget)

    def remove_display_widget(self):
        """
        Remove the widget used to display the preview content from the UI of the preview widget.
        :return: The display widget.
        """
        if self.__display_widget is not None:
            self.__display_widget.setParent(None)
            self.__display_widget = None


class DialogHelp:
    """
    This class encapsulates the functionality for retrieving the help file to display when an editor panel 'Help'
    button is pressed. By creating a DialogHelp object in the dialog class, when dialog help is requested, use
    get_dialog_help_path(dialog_type) to retrieve the file path to the html help file corresponding to the given
    dialog_type key. Each key accesses an html path (from the user manual) value that are hard-coded in the dictionary
    __user_manual_dialog_lookup.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    import origame  # to find package path since docs stored there

    DIALOG_SPECIFIC_HELP_DIR = Path(origame.__file__).with_name("docs") / "user_manual_html"

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        self.__user_manual_dialog_lookup = {}
        self.__populate_user_manual_dialog_lookup()

    def get_dialog_help_path(self, dialog_type: str) -> str:
        """
        Method used to get the pathname for the file in the user manual describing the given dialog.
        :param dialog_type: The type of dialog to get the help file path for.
        :return: A path string representing the user manual section describing the specified dialog_type.
        """
        dialog_specific_file = self.__user_manual_dialog_lookup[dialog_type]
        path = "file:///" + str(self.DIALOG_SPECIFIC_HELP_DIR) + "\\" + dialog_specific_file

        return path

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __populate_user_manual_dialog_lookup(self):
        """
        Method used to populate the dictionary that holds all dialog's html help file names that comprise the Origame
        User Manual.
        """
        self.__user_manual_dialog_lookup["sheet"] = "sheet_part_ref.html"
        self.__user_manual_dialog_lookup["table"] = "table_part_ref.html"
