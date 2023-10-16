# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: A collection of custom classes used to provide special functionality to part items and widgets.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from inspect import signature

# [2. third-party]
from PyQt5.QtCore import QSize, QObject, pyqtSignal, Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import QDialog, QListWidgetItem, QSizePolicy, QHBoxLayout, QStackedLayout
from PyQt5.QtWidgets import QWidget, QTextBrowser, QLineEdit, QPlainTextEdit, QLabel, QPushButton, QToolButton

import matplotlib

if matplotlib.get_backend() != 'Qt5Agg':
    matplotlib.use('Qt5Agg')
from matplotlib.backends.backend_qt5agg import FigureCanvas

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ..gui_utils import get_scenario_font, get_icon_path, set_default_dialog_frame_flags
from ..safe_slot import safe_slot
from ..svg_utils import SvgFromImageWidget

from .Ui_list_and_fire import Ui_ListAndFireDialog
from .Ui_label_button_item import Ui_LabelButtonItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'DetailLevelChangeButton',
    'InfoTextBrowser',
    'PlotFigureCanvas',
    'ScriptEditBox',
    'CallParameters',
    'SvgPushButton',
    'SvgToolButton',
    'ListAndFirePopup'
    'VariableTextEdit'
]

log = logging.getLogger('system')

# The size for the small icons.
SMALL_ICON_SIZE_WIDTH = 25
SMALL_ICON_SIZE_HEIGHT = 25


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------


class InfoTextBrowser(QTextBrowser):
    """
    Subclass in order to override mouseClickEvent. This allows the widgets frame to become selected and the part moved
    by clicking anywhere on the part.
    """

    def __init__(self, parent: QWidget = None):
        """
        Provide initialization of the class
        :param parent: a parent for the widget
        """
        super().__init__(parent)

    @override(QTextBrowser)
    def mousePressEvent(self, evt):
        """
        Ignore mouse clicks in order to propagate the event to the part's frame.
        """
        evt.ignore()

    @override(QTextBrowser)
    def contextMenuEvent(self, evt):
        """
        Ignore context menu events in order to propagate the event to the part's frame.
        """
        evt.ignore()


class PlotFigureCanvas(FigureCanvas):
    """
    Subclass in order to override mouseClickEvent. This allows the widgets frame to become selected and the part moved
    by clicking anywhere on the part.
    """

    def __init__(self, figure):
        super().__init__(figure)

    # noinspection PyPep8Naming
    @override(FigureCanvas)
    def mousePressEvent(self, evt):
        """
        Ignore mouse clicks in order to propagate the event to the part's frame.
        """
        evt.ignore()


class CallParameters(QLineEdit):
    """
    Subclass in order to override mouseClickEvent. This allows the widgets frame to become selected and the part moved
    by clicking anywhere on the part.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setFont(get_scenario_font())
        self.setReadOnly(True)

    # noinspection PyPep8Naming
    @override(QLineEdit)
    def mousePressEvent(self, evt):
        """
        Ignore mouse clicks in order to propagate the event to the part's frame.
        """
        evt.ignore()

    @override(QLineEdit)
    def contextMenuEvent(self, evt):
        """
        Ignore context menu events in order to propagate the event to the part's frame.
        """
        evt.ignore()


class ScriptEditBox(QPlainTextEdit):
    """
    Subclass in order to override mouseClickEvent. This allows the widgets frame to become selected and the part moved
    by clicking anywhere on the part.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setReadOnly(True)
        self.setFont(get_scenario_font(mono=True))

    # noinspection PyPep8Naming
    @override(QPlainTextEdit)
    def mousePressEvent(self, evt):
        """
        Ignore mouse clicks in order to propagate the event to the part's frame.
        """
        evt.ignore()

    @override(QPlainTextEdit)
    def contextMenuEvent(self, evt):
        """
        Ignore context menu events in order to propagate the event to the part's frame.
        """
        evt.ignore()


class VariableTextEdit(QPlainTextEdit):
    """
    Subclass in order to override mouseClickEvent. This allows the widgets frame to become selected and the part moved
    by clicking anywhere on the part.
    """

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)

    # noinspection PyPep8Naming
    @override(QPlainTextEdit)
    def mousePressEvent(self, evt):
        """
        Ignore mouse clicks in order to propagate the event to the part's frame.
        """
        evt.ignore()

    @override(QPlainTextEdit)
    def contextMenuEvent(self, evt):
        """
        Ignore context menu events in order to propagate the event to the part's frame.
        """
        evt.ignore()


class ImageWidget(QWidget):
    """
    This class works like a QLabel. The image scales with its parent.
    """

    def __init__(self, parent: QWidget = None):
        """
        :param parent: The parent of this class.
        """
        super().__init__(parent)
        self.__img_container = QLabel(self)
        self.__img_container.setAlignment(Qt.AlignCenter)

    def pixmap(self) -> QPixmap:
        """
        Gets a pixmap for this widget.
        """
        return self.__img_container.pixmap()

    def set_pixmap(self, pixmap: QPixmap):
        """
        Sets a pixmap for this widget.
        :param pixmap: The pixmap used for this widget.
        """
        self.__img_container.setPixmap(pixmap)
        self.__img_container.setFixedSize(self.size())
        self.__img_container.setPixmap(pixmap.scaled(self.size(), Qt.KeepAspectRatio))


class SvgPushButton(QPushButton):
    """
    This button uses images files including SVG as icons.
    """

    # To make the image smaller than the button icon that holds it.
    MAKE_IMG_SMALLER = 0.9
    FIT_INTO_OWNER_FACTOR = 0.8
    SVG_MARGIN = 0

    def __init__(self, parent: QWidget = None, button_pressed: bool = False):
        """
        Constructs the button. Note: The images are not set during the construction
        """
        super(SvgPushButton, self).__init__(parent)
        self.__logical_owner = None
        self.__on_svg = SvgFromImageWidget()
        self.__off_svg = SvgFromImageWidget()

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.__stacked_layout = QStackedLayout(self)

        self.__on_widget = QWidget()
        h_layout = QHBoxLayout(self.__on_widget)
        h_layout.setContentsMargins(SvgPushButton.SVG_MARGIN, SvgPushButton.SVG_MARGIN,
                                    SvgPushButton.SVG_MARGIN, SvgPushButton.SVG_MARGIN)
        h_layout.setSpacing(0)
        h_layout.addWidget(self.__on_svg, Qt.AlignCenter)

        self.__off_widget = QWidget()
        h_layout = QHBoxLayout(self.__off_widget)
        h_layout.setContentsMargins(SvgPushButton.SVG_MARGIN, SvgPushButton.SVG_MARGIN,
                                    SvgPushButton.SVG_MARGIN, SvgPushButton.SVG_MARGIN)
        h_layout.setSpacing(0)
        h_layout.addWidget(self.__off_svg, Qt.AlignCenter)

        self.__stacked_layout.addWidget(self.__on_widget)
        self.__stacked_layout.addWidget(self.__off_widget)
        if button_pressed:
            self.__stacked_layout.setCurrentWidget(self.__on_widget)
        else:
            self.__stacked_layout.setCurrentWidget(self.__off_widget)

        self.pressed.connect(self.__slot_on_pressed)
        self.released.connect(self.__slot_on_released)
        self.clicked.connect(self.__slot_on_clicked)

    def set_logical_owner(self, logical_owner):
        """
        Used to guide the size of the image inside this button.
        :param logical_owner: The logical owner of this button, not the Qt parent.
        :return:
        """
        self.__logical_owner = logical_owner

    def manage_size(self):
        """
        Makes the image fit in the container - centered and with aspect ratio.
        """
        if self.__logical_owner is None:
            size = self.size()
        else:
            size = self.__logical_owner.size() * SvgPushButton.FIT_INTO_OWNER_FACTOR

        self.__on_svg.manage_size(size, SvgPushButton.MAKE_IMG_SMALLER)
        self.__off_svg.manage_size(size, SvgPushButton.MAKE_IMG_SMALLER)

    def on_image_load(self, image_path: str):
        """
        Loads the image that represents the "on" state into this button.
        :param image_path: The "on" image path used by this button.
        """
        self.__on_svg.load(image_path)

    def off_image_load(self, image_path: str):
        """
        Loads the image that represents the "off" state into this button.
        :param image_path: The "off" image path used by this button.
        """
        self.__off_svg.load(image_path)

    def on_image_rotate(self, angle_in_degree: float):
        """
        Rotates the image that represents the "on" state.
        :param angle_in_degree: The angle to be rotated on the "on" image.
        """
        self.__on_svg.rotate(angle_in_degree)

    def off_image_rotate(self, angle_in_degree: float):
        """
        Rotates the image that represents the "off" state.
        :param angle_in_degree: The angle to be rotated on the "off" image.
        """
        self.__off_svg.rotate(angle_in_degree)

    def __on_pressed(self):
        """
        Changes the image to make the button look like the "on" state. Applicable to momentary buttons only.
        """
        if not self.isChecked():
            self.__stacked_layout.setCurrentWidget(self.__on_widget)

    def __on_released(self):
        """
        Changes the image to make the button look like the "off" state. Applicable to momentary buttons only.
        """
        if not self.isChecked():
            self.__stacked_layout.setCurrentWidget(self.__off_widget)

    def __on_clicked(self, check: bool):
        """
        Changes the image to make the button look like the "on" state if the "check" is True; otherwise, the "off"
        state. Applicable to toggle buttons only.
        :param check: True - the "on" state.
        """
        if self.isChecked():
            if check:
                self.__stacked_layout.setCurrentWidget(self.__on_widget)
            else:
                self.__stacked_layout.setCurrentWidget(self.__off_widget)

    __slot_on_pressed = safe_slot(__on_pressed)
    __slot_on_released = safe_slot(__on_released)
    __slot_on_clicked = safe_slot(__on_clicked)


class SvgToolButton(QToolButton):
    """
    This button uses images files including SVG as icons.
    """

    def __init__(self, image_path: str, parent: QWidget = None):
        """
        Constructs the button.

        Note: this class may not be needed because we may be able to use the QToolButton directly with an SVG icon.
        But for some unknown reasons, the SVG icon does not show itself in a QToolButton.

        :param image_path: The full path of an SVG file
        :param parent: The parent widget according to the Qt pattern
        """
        super(SvgToolButton, self).__init__(parent)
        self.__svg = QSvgWidget(image_path, self)
        self.__svg.setFixedSize(QSize(SMALL_ICON_SIZE_WIDTH, SMALL_ICON_SIZE_HEIGHT))
        self.setAutoRaise(True)

        # We are not using icons here, but we use this to help sizeHint in case we want to use the icon size as
        # a base size to return sizeHint with a margin or something.
        self.setIconSize(QSize(SMALL_ICON_SIZE_WIDTH, SMALL_ICON_SIZE_HEIGHT))

    @override(QToolButton)
    def sizeHint(self) -> QSize:
        return self.iconSize()


class DetailLevelChangeButton(QToolButton):
    """
    A button that toggles between two different SVG icons when pressed.
    """

    MINIMIZE_SVG = get_icon_path("shortcut_detail_level_minimal.svg")
    SHOW_CONTENT_SVG = get_icon_path("shortcut_detail_level_full.svg")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)

        self.released.connect(self.slot_toggle_detail_level)
        self.setToolTip("Show minimal detail")

        self.__minimize_icon = QSvgWidget(DetailLevelChangeButton.MINIMIZE_SVG, self)
        self.__minimize_icon.setFixedSize(QSize(SMALL_ICON_SIZE_WIDTH, SMALL_ICON_SIZE_HEIGHT))
        self.__show_content_icon = QSvgWidget(DetailLevelChangeButton.SHOW_CONTENT_SVG, self)
        self.__show_content_icon.setFixedSize(QSize(SMALL_ICON_SIZE_WIDTH, SMALL_ICON_SIZE_HEIGHT))

        self.__is_minimized = False
        self.__minimize_icon.setVisible(True)
        self.__show_content_icon.setVisible(False)

        # We are not using icons here, but we use this to help sizeHint in case we want to use the icon size as
        # a base size to return sizeHint with a margin or something.
        self.setIconSize(QSize(SMALL_ICON_SIZE_WIDTH, SMALL_ICON_SIZE_HEIGHT))

    @override(QToolButton)
    def sizeHint(self) -> QSize:
        return self.iconSize()

    def toggle_detail_level(self):
        """
        Toggles the state of this button to make it suitable for the detail level of the widget that uses
        the button.
        """
        if self.__is_minimized:
            # Transition to the detail level "full"
            self.__is_minimized = False
            self.__minimize_icon.setVisible(True)  # Show minimize minimal
            self.__show_content_icon.setVisible(False)  # Hide 'full' minimal
        else:
            # Transition to minimized
            self.__is_minimized = True
            self.__minimize_icon.setVisible(False)  # Hide minimize minimal
            self.__show_content_icon.setVisible(True)  # Show 'full' minimal

        self.__update_tooltip()

    def override_tooltip(self, tip: str = None):
        """
        The tooltip depends on the button states. But we can use this method to override the tooltip. When the
        parameter 'tip' is None, the state specific tooltip will be restored.
        :param tip: The text used to override the default tooltip.
        """
        if tip is None:
            self.__update_tooltip()
            return

        self.setToolTip(tip)

    def get_is_minimized(self) -> bool:
        """
        Get the button's detail level status.
        """
        return self.__is_minimized

    is_minimized = property(get_is_minimized)

    slot_toggle_detail_level = safe_slot(toggle_detail_level)

    def __update_tooltip(self):
        """
        Updates the tooltip based on the current state self.__is_minimized.
        """
        if self.__is_minimized:
            self.setToolTip("Show full detail")
        else:
            self.setToolTip("Show minimal detail")


class ListAndFirePopup(QDialog):
    """
    This dialog lists functions and allows the user to select one of them to be executed.
    """

    MAX_HEIGHT = 525
    HEIGHT_ADJUSTMENT = 75

    # --------------------------- class-wide data and signals -----------------------------------

    # --------------------------- class-wide methods --------------------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    # Colin FIXME ASAP: default values that are mutable are dangerous! should be None, the replace in body
    #     Reason: reminder for Colin
    def __init__(self, func_names: List[str] = [], signatures: List[signature] = [], parent: QWidget = None):
        """
        Constructs a dialog by using the Ui_InputParametersDialog.
        :param func_names: The list of the functions to be displayed in this dialog
        :param signatures: The list of the parameters
        :param parent: The parent of this dialog
        """
        super(ListAndFirePopup, self).__init__(parent)
        self.ui = Ui_ListAndFireDialog()
        self.ui.setupUi(self)
        set_default_dialog_frame_flags(self)
        self.__run_function_name = None

        if len(func_names) == 0:
            log.warning("This part does not have any functions.")
            return

        zip_sorted = sorted(zip(func_names, signatures))
        first_row = None
        total_height_needed = 0
        for func_name, sig in zip_sorted:
            label_button = Ui_LabelButtonItem()
            one_row = QWidget()
            label_button.setupUi(one_row)
            one_row.setObjectName(func_name)
            label_button.label.setFont(get_scenario_font())
            label_button.label.setText(func_name + str(sig))
            label_button.pushButton.setObjectName(func_name)
            label_button.pushButton.clicked.connect(self.__slot_run_this_function)
            label_button.pushButton.setFocusPolicy(Qt.NoFocus)

            item = QListWidgetItem(self.ui.listWidget)
            # setSizeHint is essential. Otherwise, nothing will be displayed in the one_row widget.
            item.setSizeHint(one_row.sizeHint())
            total_height_needed += one_row.sizeHint().height()
            self.ui.listWidget.addItem(item)
            self.ui.listWidget.setItemWidget(item, one_row)
            if first_row is None:
                first_row = one_row
                item.setSelected(True)

        new_height = min(ListAndFirePopup.MAX_HEIGHT, total_height_needed + ListAndFirePopup.HEIGHT_ADJUSTMENT)
        self.resize(self.size().width(), new_height)
        self.ui.listWidget.itemDoubleClicked.connect(self.__slot_update_run_function)

    def get_run_function_name(self) -> str:
        """
        Returns the name of the function to run.
        """
        assert self.__run_function_name is not None
        return self.__run_function_name

    # --------------------------- instance PUBLIC properties ----------------------------

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __run_this_function(self):
        """
        Sets the function name to run associated with the sender, which is a button.
        """
        self.__run_function_name = self.sender().objectName()
        self.done(QDialog.Accepted)

    def __update_run_function(self, list_item: QListWidgetItem):
        """
        Sets the function name to run associated with the item.
        """
        self.__run_function_name = self.ui.listWidget.itemWidget(list_item).objectName()
        self.done(QDialog.Accepted)

    __slot_run_this_function = safe_slot(__run_this_function)
    __slot_update_run_function = safe_slot(__update_run_function)
