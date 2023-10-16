# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Classes etc common to all scenario file readers/writers

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path

# [2. third-party]

# [3. local]
from ..core import override_required
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from .ori import OriSchemaEnum, OriScenData

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ScenarioFileNotFoundError',
    'ScenarioFileSaveError',
    'ScenarioReaderWriter',
    'ScenarioFormatNotSavable',
    'ScenarioFormatNotLoadable'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ScenarioFileNotFoundError(FileNotFoundError):
    """
    This class represents a custom error that is raised when the specified file path is invalid.
    """
    pass


class ScenarioFileSaveError(Exception):
    """
    This class represents a custom error that is raised when an exception is caught while saving
    a scenario to file.
    """
    pass


class ScenarioFormatNotLoadable(Exception):
    """
    The derived class does not implement loading of a scenario in its format
    """
    pass


class ScenarioFormatNotSavable(Exception):
    """
    The derived class does not implement saving of a scenario in its format
    """
    pass


class ScenarioReaderWriter:
    """
    Base class for all scenario readers and writers.
    """

    # derived class should set this to False if it does not support saving:
    SAVABLE = True

    def load_file(self, pathname: str) -> OriScenData:
        """
        Load the scenario from pathname into a dict structure.
        :param pathname: scenario file to load
        :return: JSON-like dict structure
        """
        path = Path(pathname)
        if not path.exists():
            raise ScenarioFileNotFoundError("Invalid scenario file path: " + pathname)

        return self._load_from_file(path)

    def save(self, ori_scenario: OriScenData, path: PathType):
        """
        Write the ori scenario data out to the file specified by pathname. Pathname is
        expected to resolve to an Origame (.ori) file path or a Prototype (.db) file path. If no file
        extension is provided, the .ori extension is assumed.

        :param ori_scenario: A Python directory hierarchy representing a full Origame scenario configuration to be
            saved to the specified pathname. The ori_scenario structure should reflect that expected
            once converted to JSON format.
        :param path: A full pathname to an Origame (.ori) JSON-formatted file or Prototype (.db) file.
            If the pathname already exists, it is deleted and replaced by the a new instance.
        :raises: Exception: An error occurred while saving the specified file.
        """
        path, pathname = Path(path), str(path)
        try:
            if path.exists():
                if path.is_file():
                    path.unlink()  # Delete existing file
                else:
                    raise IsADirectoryError('Directory specified instead of file path: ' + pathname)

            if not path.parent.exists():
                path.parent.mkdir(parents=True)

            return self._dump_to_file(ori_scenario, path)

        except Exception as exc:
            log.exception('Error saving scenario to file "{}": {}', path, exc)
            raise ScenarioFileSaveError('Error saving file "{}": {}'.format(path, exc))

        log.info('Scenario file saved: {}', path)

    def find_save_error_objs(self, data: any) -> list[str]:
        '''Returns the list of SaveError objects to be saved in the file or loaded from the file'''
        non_serialized_obj = []
    
        def find_save_error_obj(d: any):
            if isinstance(d, dict):
                for k,v in d.items():
                    find_save_error_obj(v)
            elif isinstance(d, list):
                for item in d:
                    find_save_error_obj(item)
            elif isinstance(d, str) and d.startswith("SaveError: ") and d not in non_serialized_obj:
                non_serialized_obj.append(d)
        
        find_save_error_obj(data)
        return non_serialized_obj

    @override_required
    def _load_from_file(self, pathname: Path):
        """Derived class must implement reading from the given file object and returning an ORI dict."""
        raise ScenarioFormatNotLoadable('File format does not support loading')

    @override_required
    def _dump_to_file(self, ori_scenario: OriScenData, path: Path):
        """Derived class must implement writing the provided ORI dict to the given file object"""
        raise ScenarioFormatNotSavable('File format does not support saving to')
