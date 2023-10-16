# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: General Purpose Accordion Widget


Version History: See SVN log.

Notes:

"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path

# [2. third-party]
from PyQt5.QtCore import QSettings, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QScrollArea, QPushButton, QVBoxLayout

# [3. local]
from .gui_utils import get_icon_path
from .safe_slot import safe_slot

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # defines module members that are public; one line per string
    'AccordionWidget',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ArrowIcon(QIcon):
    """ A QIcon with expanded/collapsed indicator for on/off states.
    """

    def __init__(self):
        super().__init__()
        arrow_down = get_icon_path("arrow_down.png")
        arrow_right = get_icon_path("arrow_right.png")

        self.addFile(str(arrow_down), state=QIcon.On)
        self.addFile(str(arrow_right), state=QIcon.Off)


class Pleat(QWidget):
    """  A unit of the bellows in an Accordion

    A single pleat is a button above a widget,
    where the button toggles the visibility of the widget and remembers its state across
    process sessions.
    """
    arrow_icon = None

    def __init__(self, name: str, child_widget: QWidget, prefix: str = None):
        """
        :param name: QSettings key suffix (of "pleat.")
        :param child_widget: A widget to show or hide depending on the button state
        :param prefix: optional prefix (before name) for the QSettings key
        """

        super().__init__()
        if prefix is not None:
            self.setObjectName(prefix + "." + name)
        else:
            self.setObjectName(name)

        if Pleat.arrow_icon is None:
            Pleat.arrow_icon = ArrowIcon()

        self.settings_key = "pleat." + self.objectName()
        self.child_widget = child_widget
        self.toggle_button = QPushButton(name)
        self.toggle_button.setIcon(ArrowIcon())
        self.toggle_button.setStyleSheet("""
QPushButton {
 text-align: left;
 background-color: #C9DADA;
 border-color: #405A5B;
 border-style: solid;
 border-width: 1px;
 border-radius: 2;
}
QPushButton:pressed{
 background-color: #C9DADA;
  border-color: #405A5B;
  border-style: solid;
  border-width: 1px;
  border-radius: 2;
}""")

        self.toggle_button.setCheckable(True)
        settings = QSettings()
        is_visible = settings.value(self.settings_key, True, type=bool)
        self.toggle_button.setChecked(is_visible)

        def make_visible():
            # we can't make visible immediately (for unknown reason), wait till start processing events
            child_widget.setVisible(is_visible)

        QTimer.singleShot(0, make_visible)
        self.toggle_button.toggled.connect(self.slot_handle_toggle)
        vertical_box = QVBoxLayout(self)
        vertical_box.setContentsMargins(0, 0, 0, 0)
        vertical_box.addWidget(self.toggle_button)
        vertical_box.addWidget(self.child_widget)

    def handle_toggle(self, is_checked: bool):
        self.child_widget.setVisible(is_checked)
        s = QSettings()
        s.setValue(self.settings_key, is_checked)

    slot_handle_toggle = safe_slot(handle_toggle)


class AccordionWidget(QScrollArea):
    """
    Similar to a QToolBox but shows multiple items at the same time.

    Each item is a "Pleat". The visible state of each pleat is saved to QSettings
    with a key of this format: "pleat.accordionName.pleatName"

    """

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setObjectName(name)
        self.setWidgetResizable(True)
        self.central_widget = QWidget()
        self.top_layout = QVBoxLayout()
        self.top_layout.setContentsMargins(5, 2, 10, 0)
        self.top_layout.addStretch()
        self.central_widget.setLayout(self.top_layout)
        self.setWidget(self.central_widget)

    def add_item(self, widget: QWidget, name: str):
        pleat = Pleat(name, widget, self.objectName())
        num_items = self.top_layout.count()
        self.top_layout.insertWidget(num_items - 1, pleat)
