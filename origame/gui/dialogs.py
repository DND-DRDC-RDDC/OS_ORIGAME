# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Reusable QDialog derived-classes

Version History: See SVN log.
"""

import logging

from PyQt5.QtWidgets import QDialog, QWidget, QDialogButtonBox, QTreeWidgetItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette

from ..core import override, validate_python_name
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from .Ui_rename_link_dialog import Ui_LinkRenameDialog
from .gui_utils import TEXT_LINK_MISSING_COLOR, set_default_dialog_frame_flags

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # defines module members that are public; one line per string
    'LinkRenameDialog'
]

log = logging.getLogger("system")


# -- Class Definitions --------------------------------------------------------------------------

# R4 Dialogs V2 by Alan Ezust


class LinkRenameDialog(QDialog):
    """
    The is a modal dialog that is used during a link name change. It displays the existing name, its references
    and waits for a valid new name, i.e., a new that has passed the validate_python_name function.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    INVALID_NAME_HIGHLIGHT_COLOR = TEXT_LINK_MISSING_COLOR

    # Design decisions:
    #
    # During the initialisation of the dialog, if the total required height is between the min and max,
    # use the height. If it is smaller than the min, use the min. If it is larger than max, use the max.
    #
    #  After the initialisation, no restrictions except those imposed by the Qt.
    DIALOG_HEIGHT_MIN = 250  # pixels
    DIALOG_HEIGHT_MAX = 800  # pixels
    DIALOG_TOP_MARGIN = 80  # pixels, for the instructions, etc.
    DIALOG_BOTTOM_MARGIN = 80  # pixels, for the OK, Cancel buttons, etc.

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QWidget = None):
        QDialog.__init__(self, parent=parent)
        self.ui = Ui_LinkRenameDialog()
        self.ui.setupUi(self)
        self.ui.references.setHeaderLabels(['Path', 'References'])
        set_default_dialog_frame_flags(self)
        self.__valid_name_palette = self.ui.new_name_edit.palette()
        self.__invalid_name_palette = QPalette()
        self.__invalid_name_palette.setColor(QPalette.Base, self.INVALID_NAME_HIGHLIGHT_COLOR)
        self.validate_new_name("")

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    def populate_refs(self, ref_part_info: List[Tuple[str, List[str]]]):
        """
        Populates the tree widget with the path of the referencing part and the lines, in the part, that reference
        the link.
        
        :param ref_part_info: A list of tuples, each of which contains a part path and the lines that reference
        the link.
        """
        for ref_part_path, lines in ref_part_info:
            top_level_item = QTreeWidgetItem([ref_part_path])
            for line in lines:
                top_level_item.addChild(QTreeWidgetItem(['', line]))

            self.ui.references.addTopLevelItem(top_level_item)

        if not ref_part_info:
            top_level_item = QTreeWidgetItem(['', 'No scripts found that reference this link'])
            self.ui.references.addTopLevelItem(top_level_item)

        self.__make_pretty_presentation()

    def validate_new_name(self, name: str, further_validation: Callable = None):
        """
        If the name is not a valid Python name, this function colors the "New Name" field light red and
        disables the OK button; otherwise, white and enables it.

        If the caller has further validation to do, it passes the further_validation function, which returns True
        if the validation has passed.

        :param name: The name to be validated
        :param further_validation: The function that does further validation outside this function
        """
        is_valid = True
        try:
            validate_python_name(name)
            if further_validation is not None:
                is_valid = further_validation()
        except:
            is_valid = False

        if is_valid:
            self.ui.new_name_edit.setPalette(self.__valid_name_palette)
        else:
            self.ui.new_name_edit.setPalette(self.__invalid_name_palette)

        self.ui.button_box_ok_cancel.button(QDialogButtonBox.Ok).setEnabled(is_valid)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __make_pretty_presentation(self):
        """
        Makes all tree item expand and sizes fit column contents.
        """
        self.ui.references.expandAll()

        for i in range(self.ui.references.columnCount()):
            self.ui.references.resizeColumnToContents(i)

        total_height = self.DIALOG_TOP_MARGIN + self.DIALOG_BOTTOM_MARGIN
        for i in range(self.ui.references.topLevelItemCount()):
            top = self.ui.references.topLevelItem(i)
            total_height += self.ui.references.visualItemRect(top).height()
            for j in range(top.childCount()):
                child = top.child(j)
                total_height += self.ui.references.visualItemRect(child).height()

        if total_height <= self.DIALOG_HEIGHT_MIN:
            total_height = self.DIALOG_HEIGHT_MIN
        elif total_height >= self.DIALOG_HEIGHT_MAX:
            total_height = self.DIALOG_HEIGHT_MAX
        else:
            # No changes
            pass

        self.resize(int(self.width()), int(total_height))
