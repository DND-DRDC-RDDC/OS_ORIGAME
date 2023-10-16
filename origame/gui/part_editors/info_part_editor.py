# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Info Part Editor and related widgets

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import InfoPart
from ...scenario import ori

from .scenario_part_editor import BaseContentEditor
from .Ui_info_part_editor import Ui_InfoPartEditorWidget
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'InfoPartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class InfoPartEditorPanel(BaseContentEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 337
    INIT_HEIGHT = 572

    def __init__(self, part: InfoPart, parent: QWidget = None):
        """
        Initializes this panel with a back end Info Part and a parent QWidget.

        :param part: The Info Part we intend to edit.
        :param parent: The parent, used to satisfy the Qt design pattern.
        """
        super().__init__(part, parent)
        self.ui = Ui_InfoPartEditorWidget()
        self.ui.setupUi(self)

    @override(BaseContentEditor)
    def get_tab_order(self) -> List[QWidget]:
        tab_order = [self.ui.info_text]
        return tab_order

    @override(BaseContentEditor)
    def _get_data_for_submission(self) -> Dict[str, Any]:
        """
        Collects the data from the Info Part editor GUI in order to submit them to the back end. The fields presented on
        the GUI do not match exactly the properties available in the Info Part. So, we format them before sending
        them to the backend.

        :returns: the data collected from the Info Part GUI.
        """
        data_dict = dict(text=self.ui.info_text.toPlainText())
        return data_dict

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        self.ui.info_text.setText(data['text'])


register_part_editor_class(ori.OriInfoPartKeys.PART_TYPE_INFO, InfoPartEditorPanel)
