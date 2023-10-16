# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This modules manages the link rename GUI, input validation, and the link rename command
dispatch

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QDialog, QTreeWidgetItem, QAction, QMessageBox
from PyQt5.QtCore import QObject

# [3. local]
from ..scenario.defn_parts import PartLink
from .actions_utils import create_action
from .gui_utils import exec_modal_dialog
from .undo_manager import RenameLinkCommand, scene_undo_stack
from .dialogs import LinkRenameDialog
from .async_methods import AsyncRequest
from .safe_slot import safe_slot

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 7016 $"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'LinkRenameManager'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------
# -- Class Definitions --------------------------------------------------------------------------


class LinkRenameManager(QObject):
    """
    Launches the GUI. Validates input. Sends the RenameLinkCommand.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        """
        Note: It must be a QObject in order to use safe_slot.
        """
        QObject.__init__(self)
        self.__link = None
        self.__link_rename_dialog = LinkRenameDialog()
        self.__link_rename_dialog.ui.new_name_edit.textEdited.connect(self.__slot_on_new_name_edited)
        self.__start_rename_action = create_action(self.__link_rename_dialog, "Rename",
                                                   tooltip="Rename link",
                                                   connect=self.__slot_on_start_rename)

    def is_link_rename_ready(self, park_link: PartLink, use_dialog: bool = True) -> bool:
        """
        After the construction of the class, this function must be called before any other functions can be used.
        If it returns True, other functions can proceed; otherwise the behaviors are undefined.

        The functions returns True when all the open editors of the parts that reference this link have applied its
        edits. Otherwise, when use_dialog is True, it pops up an info dialog to inform the user of the
        fact that unapplied edits are detected and returns False
        :param park_link: The link to be checked to determine its readiness
        :param use_dialog: If True, pops up the dialog
        :return: True - ready to run other functions.
        """
        self.__link = park_link
        allowed = self.__link.check_rename_allowed()
        self.__start_rename_action.setEnabled(allowed)
        if not allowed and use_dialog:
            exec_modal_dialog(dialog_title="Rename Link",
                              message='Unable to rename this link',
                              icon=QMessageBox.Information,
                              detailed_message="You cannot rename this link because you have not "
                                               "applied changes in the open editors that reference this link.")

        return allowed

    def get_start_rename_action(self) -> QAction:
        """
        The action that is to be shared by all the GUI components.
        :return: The action that is used to open the GUI.
        """
        return self.__start_rename_action

    def get_link_rename_dialog(self) -> LinkRenameDialog:
        """
        Gets the dialog this manager manges. Mostly used to facilitate testing.
        :return: The link rename dialog
        """
        return self.__link_rename_dialog

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    start_rename_action = property(get_start_rename_action)
    link_rename_dialog = property(get_link_rename_dialog)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_start_rename(self):
        """
        Opens the GUI and populates the link references into it.
        """
        assert self.__link is not None

        ref_parts = list()
        history = list()

        def start_traversal():
            self.__link.get_link_chain_sources(ref_parts, history)
            return [(ref_part.get_path(), lines) for ref_part, lines in ref_parts]

        AsyncRequest.call(start_traversal, response_cb=self.__link_rename_dialog.populate_refs)

        self.__link_rename_dialog.ui.current_name_edit.setText(self.__link.name)
        self.__link_rename_dialog.ui.new_name_edit.setText("")
        # Makes the initial color of the new name field right
        self.__on_new_name_edited("")
        ret = self.__link_rename_dialog.exec()
        self.__link_rename_dialog.ui.references.clear()

        if ret == QDialog.Accepted:
            new_name = self.__link_rename_dialog.ui.new_name_edit.text()
            log.debug("Rename {} to {}", self.__link.name, new_name)
            ref_parts = list()
            history = list()

            def start_traversal_with_new_name():
                self.__link.on_link_renamed(ref_parts, history, new_name)

            def send_command():
                cmd = RenameLinkCommand(self.__link, new_name, ref_parts)
                scene_undo_stack().push(cmd)

            AsyncRequest.call(start_traversal_with_new_name, response_cb=send_command)

    def __on_new_name_edited(self, new_name: str):
        """
        Validates the new name based on Python naming validity and link duplication avoidance.

        :param new_name: The name to be validated
        """

        # Link duplication validation
        def available():
            return not self.__link.source_part_frame.is_link_name_taken(new_name)

        self.__link_rename_dialog.validate_new_name(new_name, available)

    __slot_on_start_rename = safe_slot(__on_start_rename)
    __slot_on_new_name_edited = safe_slot(__on_new_name_edited)
