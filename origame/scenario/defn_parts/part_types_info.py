# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains a Part class dictionary for mapping Origame Part types with
                       their associated classes.

The lookup dictionary defined herein is populated at runtime by each Part module as it is imported. That is to say, it
is the responsibility of a Part's defining module to include a global call to this module that adds the Part's type and
associate class to the dictionary. This type name is used in the .ORI files to identify the type of part being defined.
The name is also used as the default name for the associated part type.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
from textwrap import dedent

# [2. third-party]

# [3. local]
from ...core.typing import AnnotationDeclarations
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # Public API of the module
    'get_part_class_by_name',
    'get_type_name',
    'register_new_part_type',
    'default_name_for_part',
    'get_scripting_constants',
]

# -- Module-level objects -----------------------------------------------------------------------

"""
The following dictionary gets populated at runtime by a call to register_new_part_type() in each different Part-defining
module. This add the Part type and associated class to the dictionary. Entries should be keyed by part type.

Example:
    _part_class_dict = {
        "actor": ActorPart
    }
"""
_part_class_dict = {}

"""
Part type aliases are used to look up the official part name by its aliases.

Example:
    _part_type_aliases = {
        "script": "library"
    }
"""
_part_type_aliases = dict()

# This dict is used to map a type name to a pretty name. For example, an "actor" is mapped to "Actor".
# If a pretty name is not specified, we will derive a pretty name by converting the first letter of the
# type name to upper case. The keys in this dict must match those in the _part_class_dict
_pretty_type_name = {}

# Scenario part scripts have access to the constants in the following map:
_scripting_constants = {}


# -- Function definitions -----------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    BasePart = 'BasePart'


def get_registered_type_names(non_creatable: bool = True) -> List[str]:
    """
    Get the list of all part types that have been registered (which should happen when their module is imported).
    The type names are all lower-case.
    :param non_creatable: if True, then all parts are returned; if False, only part types that are creatable
        by user are returned (ie the class has USER_CREATABLE True)
    """
    if non_creatable:
        return sorted(list(_part_class_dict.keys()))

    # only want those that have USER_CREATABLE = True:
    return sorted(name for name, cls in _part_class_dict.items() if cls.USER_CREATABLE)


def get_part_class_by_name(part_type_name: str) -> Decl.BasePart:
    """
    Get class for given type name. Type name can be either 'function' or 'actor'.
    :param part_type_name: the name for type
    :return: class to use for given type name
    """
    if part_type_name in _part_type_aliases:
        return _part_class_dict.get(_part_type_aliases[part_type_name])

    return _part_class_dict.get(part_type_name)


def register_new_part_type(part_class: Decl.BasePart, ori_type_name: str, ori_aliases: List[str] = None):
    """
    Register a new part type class to be associated with the given part type name. This should be called by each
    module ONCE.

    :param part_class: the associated part class. It must have a DESCRIPTION attribute. It may have a
        META_SCRIPTING_CONSTANTS attribute if it uses constants that may be used in scripts.
    :param ori_aliases: the alias of the part name. For example, "library" part has an alias - "script" part
    :raises: RuntimeError, if a part_type_name has already been registered for a different class type.
    """
    part_type_name = part_class.PART_TYPE_NAME
    if part_type_name != ori_type_name:
        msg = 'Part class {} has PART_TYPE_STR ({}) that does not match ORI name ({})'
        raise ValueError(msg.format(part_class.__name__, part_type_name, ori_type_name))

    if part_type_name in _part_class_dict and _part_class_dict[part_type_name] != part_class:
        err_msg = "A class type ({}) has already been associated with this type name ({})"
        raise RuntimeError(err_msg.format(part_class.__name__, part_type_name))

    _part_class_dict[part_type_name] = part_class
    _pretty_type_name[part_type_name] = part_type_name.title()

    # ORI aliases for this part type
    if ori_aliases is not None:
        for alias in ori_aliases:
            _part_type_aliases[alias] = part_type_name

    # Scripting constants
    if hasattr(part_class, 'META_SCRIPTING_CONSTANTS'):
        for const in part_class.META_SCRIPTING_CONSTANTS:
            try:
                _scripting_constants[const.__name__] = const
            except Exception:
                _scripting_constants[const[0]] = const[1]


def get_type_name(part: Decl.BasePart) -> str:
    """
    Returns the scenario part type name for the given part.
    :param part: part for which type name desired
    :return: type name
    :raises: ValueError, if part is not registered (this would indicate a bug in the part's module)
    """
    part_class = type(part)
    for key, cls in _part_class_dict.items():
        if cls == part_class:
            return key

    raise ValueError("The part class (" + part_class.__name__ + ") was not found in the registry of part types")


def get_pretty_type_name(part_type_name: str) -> str:
    """
    Use the internal type name to get a pretty type name.

    :param part_type_name: The internal name of the part type. For example, "actor"
    :returns: The pretty name. For example, "Actor"
    """
    return _pretty_type_name[part_type_name]


def default_name_for_part(part: Decl.BasePart) -> str:
    """
    Returns the default name for the given part.
    :param part: The object for which default name is needed
    :return: default name
    :raises: ValueError, if part is not registered (this would indicate a bug in the part's module)
    """
    part_class = type(part)
    for key, cls in _part_class_dict.items():
        if cls == part_class:
            return key

    raise ValueError("The part class (" + part_class.__name__ + ") was not found in the registry of part types")


def get_scripting_constants() -> Dict[str, Any]:
    """
    Get the read-only map of constants registered by each part type for access from part scripts.
    The key is the name to be used in the scripts to access the constant object.
    """
    return _scripting_constants

# -- Class Definitions --------------------------------------------------------------------------
