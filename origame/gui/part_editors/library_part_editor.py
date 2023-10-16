# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Library Part Editor.

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
from ...scenario.defn_parts import LibraryPart
from ...scenario import ori

from .scenario_part_editor import BaseContentEditor
from .script_editing import PythonScriptEditor
from .part_editors_registry import register_part_editor_class

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'LibraryPartEditorPanel'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class LibraryPartEditorPanel(PythonScriptEditor):
    """
    Represents the content of the editor under the header of the common Origame editing framework.
    """

    # The initial size to make this editor look nice.
    INIT_WIDTH = 800
    INIT_HEIGHT = 640

    def __init__(self, part: LibraryPart, parent: QWidget = None):
        super().__init__(part, parent)

    @override(BaseContentEditor)
    def _on_data_arrived(self, data: Dict[str, Any]):
        """
        This method is used to set part specific content into editors.
        """
        super()._on_data_arrived(data)
        self.ui.code_editor.set_breakpoints(data['breakpoints'])


register_part_editor_class(ori.OriLibraryPartKeys.PART_TYPE_LIBRARY, LibraryPartEditorPanel)
