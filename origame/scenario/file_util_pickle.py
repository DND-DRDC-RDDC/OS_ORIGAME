# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module provides utility functions for loading and saving Origame formatted scenario files.

This module provides the capabilities required to load an Origame-formatted scenario from file and to save the current
in-memory scenario definition out to file. The file type and format is JSON (.json). When loaded, the JSON data
structure is represented as a Python dictionary structure hierarchy, referred to herein as the ori scenario data format.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import pickle
from pathlib import Path

# [2. third-party]

# [3. local]
from ..core import override
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from .file_util_base import ScenarioReaderWriter
from .ori import OriScenData


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module
    'ScenFileUtilPickle',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------


class ScenFileUtilPickle(ScenarioReaderWriter):
    """
    This class represents a file utility class for loading and saving scenario files formatted
    and stored as Python pickle files.
    """

    @override(ScenarioReaderWriter)
    def _load_from_file(self, pathname: Path) -> Tuple[OriScenData, list[str]]:
        with pathname.open("rb") as file_obj:
            ori = pickle.load(file_obj)

        non_serialized_obj = self.find_save_error_objs(ori)

        if not isinstance(ori, OriScenData):
            ori = OriScenData(ori)

        return ori, non_serialized_obj

    @override(ScenarioReaderWriter)
    def _dump_to_file(self, ori_scenario: OriScenData, path: Path):
        pickled = pickle.dumps(ori_scenario)
        with path.open("wb") as file_obj:
            file_obj.write(pickled)

        non_serialized_obj = self.find_save_error_objs(pickle.loads(pickled))

        return non_serialized_obj
