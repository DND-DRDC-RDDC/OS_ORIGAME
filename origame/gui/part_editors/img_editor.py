# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The ImgEditorWidget is designed to be shared by those parts that need image editing

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import datetime

# [2. third-party]
from PyQt5.QtCore import QSize, QDir, QSettings
from PyQt5.QtWidgets import QWidget, QFileDialog, QMessageBox
from PyQt5.QtGui import QImageReader, QPixmap, QImage, QTransform

# [3. local]
from ...core import override
from ..gui_utils import exec_modal_dialog
from ..safe_slot import safe_slot
from .Ui_img_editor import Ui_ImgEditorWidget

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ButtonPartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ImgEditorWidget(QWidget):
    """
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 337
    INIT_HEIGHT = 572

    # Rotation Delta. 90 degrees.
    ROTATION_DELTA = 90.0

    # Used for the QSettings
    TEMP_IMG_LOCATION_TRACKING = "TEMP_IMG_LOCATION_TRACKING"

    def __init__(self, parent: QWidget = None):
        """
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(parent)
        self.ui = Ui_ImgEditorWidget()
        self.ui.setupUi(self)

        self.__rotation_2d = 0.0
        self.__img_path = None

        self.ui.select.clicked.connect(self.__slot_on_select_clicked)
        self.ui.rotate_left.clicked.connect(self.__slot_on_rotate_clicked)
        self.ui.rotate_right.clicked.connect(self.__slot_on_rotate_clicked)

    @override(QWidget)
    def sizeHint(self):
        return QSize(ImgEditorWidget.INIT_WIDTH, ImgEditorWidget.INIT_HEIGHT)

    def __on_select_clicked(self):
        """
        Handles the Select buttons to load the images.
        """
        dialog_filter = list()
        for mime_type in QImageReader.supportedMimeTypes():
            dialog_filter.append(mime_type.data().decode('utf-8'))
        dialog_filter.append('application/octet-stream')
        dialog_filter.sort()
        location = QSettings().value(ImgEditorWidget.TEMP_IMG_LOCATION_TRACKING + self.__class__.__name__,
                                     QDir.currentPath())

        dialog = QFileDialog(None, "Select Image", location)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setMimeTypeFilters(dialog_filter)
        while dialog.exec() == QFileDialog.Accepted and not self.load_img(dialog.selectedFiles()[0]):
            pass

    def load_img(self, file_name: str, rotation_2d: float = 0.0, suppress_warning_popup: bool = False) -> bool:
        """
        Loads the image and displays it.
        :param file_name: The file name of the image to be loaded from the hard drive.
        :param rotation_2d: The angle of degrees to be rotated.
        :param suppress_warning_popup: True - do not pop up a message if the image file is invalid.
        :returns: True if the loading succeeds.
        """
        img = QImage(file_name)
        if img.isNull():
            if suppress_warning_popup:
                self.position_img(QPixmap(), 0.0)
                return True
            else:
                exec_modal_dialog("Invalid File", "Invalid image file selection.", QMessageBox.Critical)
                return False
        pix = QPixmap.fromImage(img)
        self.__rotation_2d = rotation_2d
        self.position_img(pix, self.__rotation_2d)
        QSettings().setValue(ImgEditorWidget.TEMP_IMG_LOCATION_TRACKING + self.__class__.__name__, file_name)
        self.__img_path = file_name
        return True

    def position_img(self, pix: QPixmap, rotation_angle: float):
        """
        Positions the image and displays it either in the Switch-On Image section or the Switch-Off Image section.
        Note: The rotation_angle is a relative value that rotates the pix starting from its current angular position.
        It implies the same pix should be passed in if you want to rotate it continuously. For example, if you want to
        rotate a pix for 180 degrees (clicking the Rotate Left twice), you can call this function with 90 degrees the
        first time. Then, you call it with another 90 degrees the second time on the same pix. The degrees rotated
        are accumulated on the same pix.

        :param pix: The image to be positioned.
        :param rotation_angle: the relative rotation angle.
        """
        transform = QTransform()
        transform.rotate(rotation_angle)
        pix_transformed = pix.transformed(transform)
        self.ui.image_label.setPixmap(pix_transformed)

    def button_control(self, use_default: bool):
        """
        Controls which buttons are enabled or disabled, depending on whether default images are used.
        :param use_default: True, to disable the Select and Rotate Left and Rotate Right buttons.
        """
        self.ui.select.setEnabled(not use_default)
        self.ui.rotate_left.setEnabled(not use_default)
        self.ui.rotate_right.setEnabled(not use_default)

    def get_rotation_2d(self) -> float:
        return self.__rotation_2d % 360

    def get_img_path(self) -> str:
        return self.__img_path

    rotation_2d = property(get_rotation_2d)
    img_path = property(get_img_path)

    def __on_rotate_clicked(self):
        """
        Handles all rotation buttons, depending on who is the sender.
        """
        the_sender = self.sender()
        if the_sender == self.ui.rotate_left:
            if self.__img_path is None:
                return
            self.__rotation_2d -= ImgEditorWidget.ROTATION_DELTA
            self.position_img(self.ui.image_label.pixmap(), -ImgEditorWidget.ROTATION_DELTA)
        elif the_sender == self.ui.rotate_right:
            if self.__img_path is None:
                return
            self.__rotation_2d += ImgEditorWidget.ROTATION_DELTA
            self.position_img(self.ui.image_label.pixmap(), ImgEditorWidget.ROTATION_DELTA)
        else:
            raise ValueError

    __slot_on_select_clicked = safe_slot(__on_select_clicked)
    __slot_on_rotate_clicked = safe_slot(__on_rotate_clicked)
