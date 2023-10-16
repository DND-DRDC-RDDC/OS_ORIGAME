# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The dialog that reports the search progress.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QDialogButtonBox

# [3. local]
from ..safe_slot import safe_slot
from .Ui_search_progress import Ui_SearchProgressDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SearchProgressDialog'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class SearchProgressDialog(QDialog):
    """
    The dialog is popped up upon the start of the search proximity and reports its progress. If nothing is found, this
    dialog will show a message. If something is found, the dialog will close itself automatically.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------
    def __init__(self):
        super().__init__(None, Qt.WindowSystemMenuHint | Qt.WindowTitleHint)

        self.__ui = Ui_SearchProgressDialog()
        self.__ui.setupUi(self)

    def progress(self, part_path: str):
        """
        Uses the part_path to update the progress dialog.
        :param part_path: The full path of the part that is currently searched on.
        """
        self.__ui.part_path_label.setText(part_path)

    def on_start(self):
        """
        Sets the correct state of the search progress dialog and shows it when the search starts.
        """
        self.__ui.current_part_label_name.setVisible(True)
        self.__ui.current_part_label_name.setText("Current Part: ")
        self.__ui.part_path_label.setText("")
        self.__ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)
        self.show()

    def on_end(self, found: bool):
        """
        Closes the search progress dialog if at least one hit is found. Enables the OK button if nothing is found.

        :param found: True if at least one hit is found.
        """
        self.__ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(True)
        if found:
            self.close()
        else:
            self.__ui.current_part_label_name.setText("")
            # The attempt to work around a possible Qt bug. setText("") ends up with "CNothing found." sometimes.
            self.__ui.current_part_label_name.setVisible(False)
            self.__ui.part_path_label.setText("There are no search results matching the specified search criteria.")

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    slot_progress = safe_slot(progress)
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------
