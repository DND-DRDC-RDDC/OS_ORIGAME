# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Registery of all part editor classes defined

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'register_part_editor_class',
    'get_part_editor_class',
]

log = logging.getLogger('system')

__part_type_editor_classes = {}


# -- Function definitions -----------------------------------------------------------------------

def register_part_editor_class(part_type_str: str, PartEditorClass: type):
    """
    Register a new part graphics item class.
    :param part_type_str: name of part type
    :param PartEditorClass: class to be instantiated for given part_type_str
    :raise: ValueError if a class already registered for same part_type_str
    """
    if part_type_str in __part_type_editor_classes:
        raise ValueError("Type '{}' already has editor class registered, fatal error".format(part_type_str))

    msg = "Editor class '{}' will be used for part type '{}' editing".format(PartEditorClass.__name__, part_type_str)
    log.debug(msg)
    __part_type_editor_classes[part_type_str] = PartEditorClass


def get_part_editor_class(part_type_str: str) -> type:
    """Return the class for given part type name, or None if none registered"""
    return __part_type_editor_classes.get(part_type_str)

# -- Class Definitions --------------------------------------------------------------------------
