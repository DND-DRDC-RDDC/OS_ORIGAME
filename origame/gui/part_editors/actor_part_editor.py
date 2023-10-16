# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Actor Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import datetime

# [2. third-party]
from PyQt5.QtWidgets import QWidget

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import ActorPart
from ...scenario import ori

from ..gui_utils import DEFAULT_ACTOR_IMAGE
from ..safe_slot import safe_slot

from .scenario_part_editor import BaseContentEditor
from .Ui_actor_part_editor import Ui_ActorPartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ActorPartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ActorPartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 330
    INIT_HEIGHT = 400

    # Rotation Delta. 90 degrees.
    ROTATION_DELTA = 90.0

    # Used for the QSettings
    TEMP_IMG_LOCATION_TRACKING = "TEMP_IMG_LOCATION_TRACKING"

    def __init__(self, part: ActorPart, parent: QWidget = None):
        """
        Initializes this panel with a back end Actor Part and a parent QWidget.

        :param part: The Actor Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_ActorPartEditorWidget()
        self.ui.setupUi(self)

        self.ui.use_default_image.clicked.connect(self.__slot_on_use_default_image_clicked)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = []
        return tab_order

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Collects the data from the Actor Part GUI in order to submit them to the back end. The fields presented on
        the GUI do not match exactly the properties available in the Actor Part. So, we format them before sending
        them to the backend.

        :returns: the data collected from the Actor Part GUI.
        """
        img_path = self.ui.img_editor_widget.img_path
        if self.ui.use_default_image.isChecked():
            img_path = None

        data_dict = dict(rotation_2d=self.ui.img_editor_widget.rotation_2d,
                         image_path=img_path)
        return data_dict

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        :param data: The data from the back end.
        """
        rotation_2d = data['rotation_2d']
        image_path = data['image_path']

        if not image_path:
            self.ui.img_editor_widget.load_img(DEFAULT_ACTOR_IMAGE)
            self.ui.use_default_image.setChecked(True)
        else:
            self.ui.img_editor_widget.load_img(image_path, rotation_2d, True)
            self.ui.use_default_image.setChecked(False)

        self.ui.img_editor_widget.button_control(self.ui.use_default_image.isChecked())

    def __on_use_default_image_clicked(self):
        """
        Sets both the "pressed" and "released" images to the defaults if the "Use default images" is checked.
        """
        if self.ui.use_default_image.isChecked():
            self.ui.img_editor_widget.load_img(DEFAULT_ACTOR_IMAGE)
        self.ui.img_editor_widget.button_control(self.ui.use_default_image.isChecked())

    __slot_on_use_default_image_clicked = safe_slot(__on_use_default_image_clicked)


register_part_editor_class(ori.OriActorPartKeys.PART_TYPE_ACTOR, ActorPartEditorPanel)
