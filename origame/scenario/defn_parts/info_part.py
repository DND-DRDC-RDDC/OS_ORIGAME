# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the InfoPart class and supporting functionality or the Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriInfoPartKeys as InfoKeys

from .base_part import BasePart
from .actor_part import ActorPart
from .common import Position
from .part_types_info import register_new_part_type

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'InfoPart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class InfoPart(BasePart):
    """
    This class represents a scenario part that stores textual information that can be useful to the
    person editing or running the scenario.
    """

    class Signals(BridgeEmitter):
        sig_text_changed = BridgeSignal(str)

    SHOW_FRAME = False
    CAN_BE_LINK_SOURCE = True
    DEFAULT_VISUAL_SIZE = dict(width=10.0, height=4.0)
    MIN_CONTENT_SIZE = dict(width=2.0, height=2.0)
    PART_TYPE_NAME = "info"
    DESCRIPTION = """\
        Use this part to display helpful information about the model.

        Double-click the part to open its editor and enter information.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this instance of the InfoPart.
        :param position: A position to be assigned to the newly instantiated default InfoPart. This argument
            is only required when the ori_def default (None) is used.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = InfoPart.Signals()

        self._text = ""

    def get_text(self) -> str:
        """
        Get the text of the part.
        """
        return self._text

    def set_text(self, text: str):
        """
        Set the text of the part

        :param text: The new text.
        """
        if self._text != text:
            self._text = text
            if self._anim_mode_shared:
                self.signals.sig_text_changed.emit(self._text)

    # --------------------------- instance PUBLIC properties ----------------------------

    text = property(get_text, set_text)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (text,)
    META_AUTO_SCRIPTING_API_EXTEND = (text, get_text, set_text)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(BasePart)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        # Per BasePart._set_from_ori_impl() docstring, set via property.
        self.text = part_content.get(InfoKeys.TEXT, "")

    @override(BasePart)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        info_ori_def = {
            InfoKeys.TEXT: self._text
        }

        ori_def[CpKeys.CONTENT].update(info_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update({InfoKeys.TEXT: self._text})


# Add this part to the global part type/class lookup dictionary
register_new_part_type(InfoPart, InfoKeys.PART_TYPE_INFO)
