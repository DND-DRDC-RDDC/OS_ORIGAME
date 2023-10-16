# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Annotation symbols standard in R4.

See docs for the standard "typing" and "collections.abc" modules.
Use type aliases when the annotation is too verbose::

    Range = Either[int, str, slice, List[int]]

    def func(abc: Range) -> int:
        pass

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
from typing import Any              # any type of object
from typing import Optional         # Ex: def func(abc: Optional[int]): a can be int or None
from typing import Callable         # Ex: def func(on_done: Callable[[int, str], List[int]]: on_done is a callable
                                    # that takes an int and str (in that order), and returns a list of integers

from typing import TextIO           # Ex: def func(writer: TextIO): writer is an object that has write(str)
from typing import BinaryIO         # Ex: def func(writer: BinaryIO): writer is an object that has write(bytes)

from typing import Tuple            # Ex: def func(a1: Tuple[int, int, str]): a1 is a tuple with an 2 ints and a str
from typing import List, Sequence   # Ex: def func(a1: List[int], a2: Sequence[str]): a1 is a list of integers,
                                    # whereas a2 can be a list or a tuple or other iteratable object
from typing import Set, FrozenSet   # Ex: def func(s1: Set[int], s2: FrozenSet[str]): s1 is a set() of integers,
                                    # s2 is a frozenset() of strings
from typing import NamedTuple       # Ex: def func(nt: NamedTuple('Employee', [('name', str), ('id', int)])):
                                    # nt is a collections.namedtuple('Employee', ['name', 'id'])
from typing import Iterable         # iterable is a generic, dynamically generated sequence of items
                                    # Ex: def func(iter: Iterable): iter can be used in a for loop/list comprehension
                                    #     as many times as desired
from typing import Generator        # a function that has yield

from typing import Dict             # type is dict; Ex: def func(d1: Dict[int, str]): d1 maps ints to strings
from typing import KeysView         # Ex: def func(m1: KeysView[int, str]): m1 is a Dict[int, str].keys()
from typing import ValuesView       # Ex: def func(m1: ValuesView[int, str]): m1 is a Dict[int, str].values()
from typing import ItemsView        # Ex: def func(m1: ItemsView[int, str]): m1 is a Dict[int, str].items()

from typing import Generic, TypeVar

# [2. third-party]

# [3. local]


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 6971 $"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

# the following lines are solely so PyCharm can find "Either" as a symbol and provide code completion
from typing import Union as _Union, Iterator as _Iterator

Either = _Union     # Ex: def func(abc: Either[int, str, None]): abc can be int or str or None
Stream = _Iterator  # iterable that can only be used once (usually because it was created by calling a
                    # generator function (a function that yields); once loop to end, can't loop again

from pathlib import Path
PathType = Either[str, Path]


class AnnotationDeclarations:
    """
    Used to define *forward declarations* for type hints (annotations).
    These are only needed where a class defines methods that take and/or returns objects of its own
    type, or when two objects' type hints need to refer to each other. Example:

    # in the globals section of a module:

    class Decl(AnnotationDeclarations):
        Foo = 'Foo'
        Bar = 'Bar'

    # further down in the module:

    class Foo:
        def method(self, foo: Decl.Foo, bar: Decl.Bar):
            ...

    class Bar:
        def method(self, foo: Decl.Foo, bar: Decl.Bar):
            ...

    The AnnotationDeclarations base class must be used and will ensure (at import type) that the derived
    class name is Decl and that all symbols match their string value.
    """
    pass