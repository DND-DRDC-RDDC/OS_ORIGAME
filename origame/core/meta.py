# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Meta classes and meta programming support.


Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from .typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from .typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'AttributeAggregator'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------


class AttributeAggregator(type):
    """
    This class is a metaclass. It is used by those classes that need to combine attributes consistently.

    This takes the META_AUTO_*_API_EXTEND class attributes of a class being
    imported and combines them into the class's AUTO_*_API_CUMUL attribute. Hence each class in the part type hierarchy
    ends up with its own AUTO_*_API_CUMUL attribute that contains the EXTEND items of all levels "up". The AUTO
    attributes are used by BaePart to provide functionality that is common to all parts, such as editing
    a part, searching its properties, accessing its scripting API, and so forth.

    Example: if class A derives from B which derives from BasePart, both A and B can define
    META_AUTO_SCRIPTING_API_EXTEND. B.META_AUTO_SCRIPTING_API_EXTEND contains, as per the META_ docs in BasePart,
    references to B members that should be available via auto-completion when scripting, such as B.bar1 and B.bar2;
    A.META_AUTO_SCRIPTING_API_EXTEND does the same, such as A.aaa1 and A.aaa2. This this meta class will cause
    B.AUTO_SCRIPTING_API_CUMUL to be ('bar1', 'bar2'), and A.AUTO_SCRIPTING_API_CUMUL to be
    ('bar1', 'bar2', 'aaa1', 'aaa2'). The META_*_EXTEND members are deleted from the class once processed,
    so that optional METAs can be ommitted:

    - META_AUTO_EDITING_API_EXTEND and META_AUTO_SCRIPTING_API_EXTEND: required
    - META_AUTO_SEARCHING_API_EXTEND: if not given, AUTO_SEARCHING_API_CUMUL will be AUTO_EDITING_API_CUMUL
    - META_AUTO_ORI_DIFFING_API_EXTEND: if not given, AUTO_ORI_DIFFING_CUMUL will be AUTO_SEARCHING_API_CUMUL
    """

    def __init__(cls, name, bases, *args):
        """
        :param cls: the class that is being imported, and is ready for final initialization (ex FunctionPart, etc)
        :param name: the class name
        :param bases: the base classes of the class
        :param args: unused arguments
        """
        assert hasattr(cls, 'META_AUTO_EDITING_API_EXTEND')

        cls.__combine_api_traits(bases, 'META_AUTO_EDITING_API_EXTEND',
                                 'AUTO_EDITING_API_CUMUL')
        cls.__combine_api_traits(bases, 'META_AUTO_SEARCHING_API_EXTEND',
                                 'AUTO_SEARCHING_API_CUMUL', 'AUTO_EDITING_API_CUMUL')
        cls.__combine_api_traits(bases, 'META_AUTO_ORI_DIFFING_API_EXTEND',
                                 'AUTO_ORI_DIFFING_CUMUL', 'AUTO_SEARCHING_API_CUMUL')
        cls.__combine_api_traits(bases, 'META_AUTO_SCRIPTING_API_EXTEND',
                                 'AUTO_SCRIPTING_API_CUMUL')

    def __combine_api_traits(cls, bases: List[type], trait_members_list_name: str, cumul_name: str,
                             default_cumul_name: str = None):
        base_cumul_list = []
        for base in bases:
            if hasattr(base, cumul_name):
                base_cumul_list += getattr(base, cumul_name)

        try:
            trait_members = getattr(cls, trait_members_list_name)
            # must delete so that optional METAs supported:
            delattr(cls, trait_members_list_name)

        except AttributeError:
            if default_cumul_name is None:
                raise ValueError('Class {} does not define required "{}"'.format(cls.__name__, trait_members_list_name))
            setattr(cls, cumul_name, getattr(cls, default_cumul_name))

        else:
            cls_cumul_list = []
            for item in trait_members:
                attrib_names = dir(cls)
                found = False
                for attrib_name in attrib_names:
                    if getattr(cls, attrib_name) is item:
                        cls_cumul_list.append(attrib_name)
                        found = True
                        break

                if not found:
                    raise RuntimeError('BUG: attrib "{}" could not be matched to an object in class {}'
                                       .format(attrib_name, cls.__name__))

            assert len(cls_cumul_list) == len(trait_members)
            setattr(cls, cumul_name, tuple(base_cumul_list + cls_cumul_list))
