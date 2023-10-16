# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Button Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import QDir, QSettings
from PyQt5.QtWidgets import QMessageBox, QWidget, QFileDialog
from PyQt5.QtGui import QImageReader, QResizeEvent

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import ButtonPart, ButtonActionEnum, ButtonTriggerStyleEnum
from ...scenario import ori

from ..gui_utils import DEFAULT_BUTTON_DOWN, DEFAULT_BUTTON_UP, DEFAULT_BUTTON_ON, DEFAULT_BUTTON_OFF
from ..safe_slot import safe_slot
from ..gui_utils import exec_modal_dialog

from .scenario_part_editor import BaseContentEditor
from .Ui_button_part_editor import Ui_ButtonPartEditorWidget
from .part_editors_registry import register_part_editor_class

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

class ButtonPartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 380
    INIT_HEIGHT = 720

    # Rotation Delta. 90 degrees.
    ROTATION_DELTA = 90.0

    # Used for the QSettings
    TEMP_IMG_LOCATION_TRACKING = "TEMP_IMG_LOCATION_TRACKING"

    def __init__(self, part: ButtonPart, parent: QWidget = None):
        """
        Initializes this panel with a back end Button Part and a parent QWidget.

        :param part: The Button Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_ButtonPartEditorWidget()
        self.ui.setupUi(self)

        self.__rotation_2d_pressed = 0.0
        self.__rotation_2d_released = 0.0
        self.__img_pressed = None
        self.__img_released = None

        self.ui.radio_momentary.clicked.connect(self.__slot_on_button_action_selected)
        self.ui.radio_toggle.clicked.connect(self.__slot_on_button_action_selected)
        self.ui.checkbox_on_press.clicked.connect(self.__slot_on_button_trigger_style_selected)
        self.ui.checkbox_on_release.clicked.connect(self.__slot_on_button_trigger_style_selected)
        self.ui.switch_on_select.clicked.connect(self.__slot_on_select_clicked)
        self.ui.switch_off_select.clicked.connect(self.__slot_on_select_clicked)
        self.ui.switch_on_rotate_left.clicked.connect(self.__slot_on_rotate_clicked)
        self.ui.switch_on_rotate_right.clicked.connect(self.__slot_on_rotate_clicked)
        self.ui.switch_off_rotate_left.clicked.connect(self.__slot_on_rotate_clicked)
        self.ui.switch_off_rotate_right.clicked.connect(self.__slot_on_rotate_clicked)
        self.ui.use_default_images.clicked.connect(self.__slot_on_use_default_images_clicked)

    @override(QWidget)
    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self.__manage_image_size()

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.radio_momentary,
                     self.ui.radio_toggle,
                     self.ui.checkbox_on_press,
                     self.ui.checkbox_on_release,
                     self.ui.use_default_images,
                     self.ui.switch_on_select,
                     self.ui.switch_on_rotate_left,
                     self.ui.switch_on_rotate_right,
                     self.ui.switch_off_select,
                     self.ui.switch_off_rotate_left,
                     self.ui.switch_off_rotate_right]
        return tab_order

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Collects the data from the Button Part editor GUI in order to submit them to the back end. The fields presented
        on the GUI do not match exactly the properties available in the Button Part. So, we format them before sending
        them to the backend.

        :returns: the data collected from the Button Part editor GUI.
        """
        btn_action = ButtonActionEnum.momentary if self.ui.radio_momentary.isChecked() else ButtonActionEnum.toggle
        if self.ui.checkbox_on_press.isChecked() and self.ui.checkbox_on_release.isChecked():
            btn_trigger_style = ButtonTriggerStyleEnum.on_press_and_release
        else:
            if self.ui.checkbox_on_press.isChecked():
                btn_trigger_style = ButtonTriggerStyleEnum.on_press
            else:
                btn_trigger_style = ButtonTriggerStyleEnum.on_release

        data_dict = dict(button_action=btn_action,
                         button_trigger_style=btn_trigger_style,
                         rotation_2d_pressed=self.__rotation_2d_pressed % 360,
                         rotation_2d_released=self.__rotation_2d_released % 360,
                         image_path_pressed=None if self.ui.use_default_images.isChecked() else self.__img_pressed,
                         image_path_released=None if self.ui.use_default_images.isChecked() else self.__img_released)
        return data_dict

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        :param data: The data from the back end.
        """
        button_action = data['button_action']
        button_trigger_style = data['button_trigger_style']
        self.__rotation_2d_pressed = data['rotation_2d_pressed']
        self.__rotation_2d_released = data['rotation_2d_released']
        image_path_pressed = data['image_path_pressed']
        image_path_released = data['image_path_released']

        if button_action == ButtonActionEnum.momentary:
            self.ui.radio_momentary.setChecked(True)
        else:
            self.ui.radio_toggle.setChecked(True)

        self.__on_button_action_selected()

        if button_trigger_style == ButtonTriggerStyleEnum.on_press_and_release:
            self.ui.checkbox_on_press.setChecked(True)
            self.ui.checkbox_on_release.setChecked(True)
        elif button_trigger_style == ButtonTriggerStyleEnum.on_press:
            self.ui.checkbox_on_press.setChecked(True)
            self.ui.checkbox_on_release.setChecked(False)
        else:
            self.ui.checkbox_on_press.setChecked(False)
            self.ui.checkbox_on_release.setChecked(True)

        if not image_path_pressed:
            if button_action == ButtonActionEnum.momentary:
                self.__load_img(DEFAULT_BUTTON_DOWN, True)
            else:
                self.__load_img(DEFAULT_BUTTON_ON, True)
        else:
            self.__load_img(image_path_pressed, True)

        self.__rotate_image(True, self.__rotation_2d_pressed)

        if not image_path_released:
            if button_action == ButtonActionEnum.momentary:
                self.__load_img(DEFAULT_BUTTON_UP, False)
            else:
                self.__load_img(DEFAULT_BUTTON_OFF, False)
        else:
            self.__load_img(image_path_released, False)

        self.__rotate_image(False, self.__rotation_2d_released)

        if not image_path_pressed and not image_path_released:
            self.ui.use_default_images.setChecked(True)
        else:
            self.ui.use_default_images.setChecked(False)

        self.__button_control(self.ui.use_default_images.isChecked())

    def __on_button_action_selected(self):
        """
        Handles the button action changes.
        """
        if self.ui.radio_momentary.isChecked():
            self.ui.checkbox_on_press.setEnabled(True)
            self.ui.checkbox_on_press.setChecked(True)
            self.ui.checkbox_on_release.setEnabled(True)
            self.ui.checkbox_on_release.setChecked(False)
        else:
            # Must be the toggle
            self.ui.checkbox_on_press.setEnabled(False)
            self.ui.checkbox_on_press.setChecked(True)
            self.ui.checkbox_on_release.setEnabled(False)
            self.ui.checkbox_on_release.setChecked(True)
        self.__on_use_default_images_clicked()

    def __on_button_trigger_style_selected(self):
        """
        Handles the button trigger style changes. When it is a momentary button, the trigger style checkboxes
        cannot be both unchecked.
        """
        if self.ui.radio_momentary.isChecked() \
                and not self.ui.checkbox_on_press.isChecked() and not self.ui.checkbox_on_release.isChecked():
            self.ui.checkbox_on_press.setChecked(True)

    def __on_select_clicked(self):
        """
        Handles both Select buttons to load the images, depending on who is the sender. If the sender is the Select
        button from the "Switch-On Image" section, the self.__load_img will load the image to that section; otherwise,
        to the "Switch-Off Image" section.
        """
        dialog_filter = list()
        for mime_type in QImageReader.supportedMimeTypes():
            dialog_filter.append(mime_type.data().decode('utf-8'))
        dialog_filter.append('application/octet-stream')
        dialog_filter.sort()
        trk_key_suffix = self.__class__.__name__ + self.sender().objectName()
        location = QSettings().value(ButtonPartEditorPanel.TEMP_IMG_LOCATION_TRACKING + trk_key_suffix,
                                     QDir.currentPath())

        dialog = QFileDialog(None, "Select Image", location)
        dialog.setAcceptMode(QFileDialog.AcceptOpen)
        dialog.setMimeTypeFilters(dialog_filter)
        while dialog.exec() == QFileDialog.Accepted \
                and not self.__load_img(dialog.selectedFiles()[0], self.sender() == self.ui.switch_on_select):
            pass

    def __load_img(self, file_name: str, switch_on: bool) -> bool:
        """
        Loads the image and displays it either in the Switch-On Image section or the Switch-Off Image section.
        :param file_name: The file name of the image to be loaded from the hard drive.
        :param switch_on: True to load the switch-on image, otherwise False to load the switch-off image.
        :returns: True if the loading succeeds.
        """
        try:
            if switch_on:
                self.ui.switch_on_image_widget.load(file_name)
                self.__img_pressed = file_name
                trk_key_suffix = self.__class__.__name__ + self.ui.switch_on_select.objectName()
            else:
                self.ui.switch_off_image_widget.load(file_name)
                self.__img_released = file_name
                trk_key_suffix = self.__class__.__name__ + self.ui.switch_off_select.objectName()

        except FileNotFoundError:
            exec_modal_dialog("Invalid File", "Invalid image file selection.", QMessageBox.Critical)
            return False

        self.__manage_image_size()
        QSettings().setValue(ButtonPartEditorPanel.TEMP_IMG_LOCATION_TRACKING + trk_key_suffix, file_name)
        return True

    def __rotate_image(self, switch_on: bool, rotation_angle: float = 0.0):
        """
        Rotates the image.
        :param switch_on: True to rotate the switch-on image, otherwise False to rotate the switch-off image.
        :param rotation_angle: the rotation angle.
        """
        if switch_on:
            self.ui.switch_on_image_widget.rotate(rotation_angle)
        else:
            self.ui.switch_off_image_widget.rotate(rotation_angle)

        self.__manage_image_size()

    def __on_rotate_clicked(self):
        """
        Handles all rotation buttons, depending on who is the sender.
        """
        the_sender = self.sender()
        if the_sender == self.ui.switch_on_rotate_left:
            if self.__img_pressed is None:
                return
            self.__rotation_2d_pressed -= ButtonPartEditorPanel.ROTATION_DELTA
            self.__rotate_image(True, self.__rotation_2d_pressed)
        elif the_sender == self.ui.switch_on_rotate_right:
            if self.__img_pressed is None:
                return
            self.__rotation_2d_pressed += ButtonPartEditorPanel.ROTATION_DELTA
            self.__rotate_image(True, self.__rotation_2d_pressed)
        elif the_sender == self.ui.switch_off_rotate_left:
            if self.__img_released is None:
                return
            self.__rotation_2d_released -= ButtonPartEditorPanel.ROTATION_DELTA
            self.__rotate_image(False, self.__rotation_2d_released)
        elif the_sender == self.ui.switch_off_rotate_right:
            if self.__img_released is None:
                return
            self.__rotation_2d_released += ButtonPartEditorPanel.ROTATION_DELTA
            self.__rotate_image(False, self.__rotation_2d_released)
        else:
            raise ValueError

    def __on_use_default_images_clicked(self):
        """
        Sets both the "pressed" and "released" images to the defaults if the "Use default images" is checked.
        """
        if self.ui.use_default_images.isChecked():
            if self.ui.radio_momentary.isChecked():
                self.__load_img(DEFAULT_BUTTON_DOWN, True)
                self.__load_img(DEFAULT_BUTTON_UP, False)
            else:
                self.__load_img(DEFAULT_BUTTON_ON, True)
                self.__load_img(DEFAULT_BUTTON_OFF, False)

            self.__img_pressed = None
            self.__img_released = None
            self.__rotation_2d_pressed = 0.0
            self.__rotation_2d_released = 0.0

        self.__button_control(self.ui.use_default_images.isChecked())

    def __manage_image_size(self):
        """
        Runs the image widget's size managers.
        """
        self.ui.switch_on_image_widget.manage_size(self.ui.on_scroll_area.size(), size_scale_factor=.9)
        self.ui.switch_off_image_widget.manage_size(self.ui.off_scroll_area.size(), size_scale_factor=.9)

    def __button_control(self, use_default: bool):
        """
        Controls which buttons are enabled or disabled, depending on whether default images are used.
        :param use_default: True, to disable the Select and Rotate Left and Rotate Right buttons.
        """
        self.ui.switch_on_select.setEnabled(not use_default)
        self.ui.switch_on_rotate_left.setEnabled(not use_default)
        self.ui.switch_on_rotate_right.setEnabled(not use_default)
        self.ui.switch_off_select.setEnabled(not use_default)
        self.ui.switch_off_rotate_left.setEnabled(not use_default)
        self.ui.switch_off_rotate_right.setEnabled(not use_default)

    __slot_on_button_action_selected = safe_slot(__on_button_action_selected)
    __slot_on_button_trigger_style_selected = safe_slot(__on_button_trigger_style_selected)
    __slot_on_select_clicked = safe_slot(__on_select_clicked)
    __slot_on_rotate_clicked = safe_slot(__on_rotate_clicked)
    __slot_on_use_default_images_clicked = safe_slot(__on_use_default_images_clicked)


register_part_editor_class(ori.OriButtonPartKeys.PART_TYPE_BUTTON, ButtonPartEditorPanel)
