# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains the FilePart class definition and supporting code.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path, PurePath
import re

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream, AnnotationDeclarations

from ..ori import OriFilePartKeys as FileKeys
from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys

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
    'FilePart',
    'is_path_below_directory',
    'check_valid_file_path',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------
def is_path_below_directory(file: str, scen_folder: str) -> bool:
    """
    check if the file path is under the scenario folder
    """
    if not scen_folder:
        return False

    if not Path(file).is_absolute():
        return True

    return Path(scen_folder) in Path(file).parents


def check_valid_file_path(params_str: str) -> bool:
    bad_chars = re.compile(r'["*?<>|]')
    return not bad_chars.search(params_str)


# -- Class Definitions --------------------------------------------------------------------------
class Decl(AnnotationDeclarations):
    FilePart = 'FilePart'


class FilePart(BasePart):
    """
    This class represents a scenario part that hold a path to a file path.
    """

    class Signals(BridgeEmitter):
        sig_path_changed = BridgeSignal(str)
        sig_is_relative_to_scen_folder_changed = BridgeSignal(bool)

    DEFAULT_VISUAL_SIZE = dict(width=18.0, height=5.1)

    PART_TYPE_NAME = "file"
    DESCRIPTION = """\
        Use this part to store any file path string.

        Double-click to set the filename/path.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this instance of the VariablePart.
        :param position: A position to be assigned to the newly instantiated default FilePart. This argument
            is only required when the ori_def default (None) is used.
        """

        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = FilePart.Signals()

        self.__path = None
        self.__relative_to_scen_folder = False

    def get_filepath(self) -> Path:
        """
        Get the path set by the editor.
        """
        if self.__path:
            return Path(self.__path)
        else:
            return None

    def set_filepath(self, the_path: Either[str, Path]):
        """
        Set the path. It takes string or Path
        """
        if the_path is None:
            path_str = None
        else:
            path_str = str(the_path)

        if self.__path != path_str:
            if path_str:
                self.__path = path_str
            else:
                self.__path = None
        if self._anim_mode_shared:
            self.signals.sig_path_changed.emit(self.__path)

    def get_is_relative_to_scen_folder(self) -> bool:
        """
        Return True if the path is relative to scenario folder, False otherwise.
        """
        return self.__relative_to_scen_folder

    def set_is_relative_to_scen_folder(self, is_relative: bool):
        """
        Configure the path to be relative to scenario folder.

        :param is_relative: True if current path should be interpreted as relative
        :raises ValueError: if current path is absolute and there is no scenario folder, or there is a
            scenario folder and the path is not an ancestor of it.
        """
        if is_relative != self.__relative_to_scen_folder:
            self.__relative_to_scen_folder = is_relative

            if self._anim_mode_shared:
                self.signals.sig_is_relative_to_scen_folder_changed.emit(is_relative)

    def get_full_path(self) -> Path:
        """this returns the absolute path if relative to scenario to folder is true """
        if self.__relative_to_scen_folder:
            if self.shared_scenario_state.scen_filepath:
                return Path(self.shared_scenario_state.scen_filepath.parent / self.__path)

        return Path(self.__path)

    def __dir__(self) -> List[str]:
        """for code-completion. Need to access all the Path public functions """
        return super().__dir__() + [attrib for attrib in dir(Path) if not attrib.startswith('_')]

    def __truediv__(self, other: Either[Path, Decl.FilePart, str]) -> Path:
        try:
            other = other.get_filepath()
        except:
            pass

        return Path(self.get_full_path()) / other

    def __getattr__(self, key: str):
        """
        If this method is called, it is because script is asking for path related attribute

        :param key: Path method name
        :return: the result from Path.key (for example: Path.write, Path.suffix)
        """
        if key.startswith('_'):
            raise TypeError("no attribute named <{}>".format(key))
        else:
            return getattr(Path(self.get_full_path()), key)

    def validate_edited_snapshot(self, path_str: str, relative_to_folder: bool):
        """
        Run the inputs, will raise exception if doesn't pass the verification.
        :param path_str: absolute or relative path string.
        :param relative_to_folder: bool value to indicate if the path is relative to scenario folder
        """
        if self.shared_scenario_state.scen_filepath:
            self.__scenario_path = str(self.shared_scenario_state.scen_filepath.parent)
        else:
            self.__scenario_path = None

        if not check_valid_file_path(path_str):
            error_msg = "You've entered illegal path char. Please fix the path!"
            raise RuntimeError(error_msg)

        if relative_to_folder and Path(path_str).is_absolute():
            if not self.__scenario_path:
                error_msg = "Path must be relative and/or relative-to-scenario must be True because scenario " \
                            "does not have a file path yet!"
                raise RuntimeError(error_msg)

            if not is_path_below_directory(path_str, self.__scenario_path):
                error_msg = "Absolute path must be below scenario folder since relative-to-scenario=True!"
                raise RuntimeError(error_msg)

        if (path_str and relative_to_folder and is_path_below_directory(path_str, self.__scenario_path) and
                Path(path_str).is_absolute()):
            if str(path_str) == self.__scenario_path:
                path_str = ''
            else:
                path_str = Path(path_str).relative_to(self.__scenario_path)

        self.set_filepath(path_str)


    # --------------------------- instance PUBLIC properties ----------------------------

    filepath = property(get_filepath, set_filepath)
    is_relative_to_scen_folder = property(get_is_relative_to_scen_folder, set_is_relative_to_scen_folder)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (filepath, is_relative_to_scen_folder)
    META_AUTO_SCRIPTING_API_EXTEND = (filepath, get_filepath, set_filepath, get_full_path, is_relative_to_scen_folder)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    @override(BasePart)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        self.filepath = part_content.get(FileKeys.PATH_STR, None)
        if FileKeys.RELATIVE_TO_SCEN_FOLDER in part_content:
            self.is_relative_to_scen_folder = part_content[FileKeys.RELATIVE_TO_SCEN_FOLDER]

    @override(BasePart)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        temp = self.__path
        file_ori_def = {
            FileKeys.PATH_STR: self.__path,
            FileKeys.RELATIVE_TO_SCEN_FOLDER: self.__relative_to_scen_folder
        }

        ori_def[CpKeys.CONTENT].update(file_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update({FileKeys.PATH_STR: self.__path,
                         FileKeys.RELATIVE_TO_SCEN_FOLDER: self.__relative_to_scen_folder})

    @override(BasePart)
    def _receive_edited_snapshot(self, submitted_data: Dict[str, Any], order: List[str] = None):
        """validate the file part input before accepting the input"""
        self.validate_edited_snapshot(submitted_data['filepath'], submitted_data['is_relative_to_scen_folder'])
        submitted_data['filepath'] = self.get_filepath()
        super()._receive_edited_snapshot(submitted_data, order=order)


# Add this part to the global part type/class lookup dictionary
register_new_part_type(FilePart, FileKeys.PART_TYPE_FILE)
