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
import json
import logging
from pathlib import Path
import datetime

# [2. third-party]

# [3. local]
from ..core import override
from ..core.typing import Tuple
from .file_util_base import ScenarioReaderWriter
from .ori import OriScenData, SaveError, SaveErrorLocationEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module
    'ScenFileUtilJsonOri'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def as_python_object(dct):
    '''"Invert" (decode) ExtendedJSONEncoder, key extension is serialization of datetime objects.''' 
    if '_datetime_object' in dct:
        string_date = json.loads(str(dct['_datetime_object']))
        return datetime.datetime.strptime(string_date, '%Y-%m-%d %H:%M:%S.%f')
    #if '_set_object' in dct:
    #    return set(json.loads(str(dct['_set_object'])))
    return dct

# -- Class Definitions --------------------------------------------------------------------------

class ExtendedJSONEncoder(json.JSONEncoder):
    '''Extend types that are JSON serializable, key extension is datetime objects. Use as_python_object to decode.'''
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return {'_datetime_object': json.dumps(obj.strftime('%Y-%m-%d %H:%M:%S.%f'))}
        #if isinstance(obj, set):
        #    return {'_set_object': json.dumps(list(obj))}
        return json.JSONEncoder.default(self, obj) # handle default types + errors
    
class ScenFileUtilJsonOri(ScenarioReaderWriter):
    """
    This class represents a file utility class for loading and saving Origame (.ori) scenario files formatted
    and stored as JSON-formatted files.
    """

    @override(ScenarioReaderWriter)
    def _load_from_file(self, pathname: Path) -> Tuple[OriScenData, list[str]]:
        """
        :raises: ValueError. This error is raised by the JSON interpreter if a parsing error occurs while the file
            is being loaded.
        """
        with pathname.open() as f:
            ori_scenario = json.load(f, object_hook=as_python_object)

        non_serialized_obj = self.find_save_error_objs(ori_scenario)

        return OriScenData(ori_scenario), non_serialized_obj

    @override(ScenarioReaderWriter)
    def _dump_to_file(self, ori_scenario: OriScenData, path: Path):
        default = lambda o: SaveError(o, SaveErrorLocationEnum.other).to_json()
        jsond = json.dumps(ori_scenario, indent=4, separators=(',', ': '), sort_keys=True, cls=ExtendedJSONEncoder, default=default)

        with path.open("w") as f:
            f.write(jsond)

        non_serialized_obj = self.find_save_error_objs(json.loads(jsond))

        return non_serialized_obj
