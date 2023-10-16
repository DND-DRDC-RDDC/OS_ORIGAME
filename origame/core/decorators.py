# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Decorators for various uses

Decorators for various uses, including annotating function/method signatures. For use anywhere in Origame.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import inspect

# [2. third-party]

# [3. local]
from .typing import TypeVar, Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from .typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # defines module members that are public; one line per string
    'override',
    'override_required',
    'override_optional',
    'attrib_override_required',
    'internal',
]

# -- Module-level objects -----------------------------------------------------------------------

TAny = TypeVar('TAny')
TCallable = Callable[[Any], Any]  # any callable is accepted
Decorator = Callable[[TCallable], TCallable]


# -- Function definitions -----------------------------------------------------------------------

def override(base_class: type) -> Decorator:
    """
    Indicate that a method is an override of a base class method. For documentation, and checks that the method
    indeed exists in the base class. If not, an assertion error will arise at import time. Example:

        >>> class Foo:
        ...    def base_meth(self):
        ...        print('foo')
        ...
        >>> class Bar(Foo):
        ...    @override(Foo)  # if Foo.base_meth does not exist, AssertError will be raised at import time
        ...    def base_meth(self):
        ...        Foo.base_meth(self)
        ...        print('bar')
        ...
        >>> bar = Bar()
        >>> bar.base_meth()
        foo
        bar
        >>> print('name:', bar.base_meth.__name__)
        name: base_meth
    """
    if not inspect.isclass(base_class):
        raise ValueError('Need base class to be given as arg to decorator')

    def check_derived_method(fn):
        func_name = fn.__name__
        if not hasattr(base_class, func_name):
            err_msg = "Derived method '{}' is not in {}".format(func_name, base_class.__qualname__)
            raise AttributeError(err_msg)
        return fn

    return check_derived_method


def override_required(func: TCallable) -> TCallable:
    """
    Use this decorator to indicate that a method MUST be overridden in a derived class. The based class method
    should raise NotImplementedError to ensure that calling a non-overridden override_required doesn't go unnoticed.
    """
    return func


def override_optional(func: TCallable) -> TCallable:
    """
    Use this decorator to indicate that a method can safely be overridden in a derived class. The base class
    method should provide valid default behavior.
    """
    return func


def attrib_override_required(default_val: TAny) -> TAny:
    """
    When a base class attribute is marked with this "decorator", it MUST be overridden by the derived class.
    There is currently no way to enforce this, so this is just a means to make the base class API contract explicit.
    :return: default_val
    """
    return default_val


def internal(*types: List[type]) -> Decorator:
    """
    Decorator to indicate that a function should be treated as public only to the types given or, if no
    types given, to types defined within the same module; the function should be treated as private for
    everything else. Note: The decorator has no way of enforcing that access to the decorated function is
    only through specified classes (if specified) or classes of the same module; it can only make the
    intent clear to the caller.

    The decorated function must start with one (and only one) underscore (or a ValueError is raised).

    Example:

    >>> class Foo:
    ...     @internal(Baz)       # _meth should be accessed only by Baz, assumed to be in same module or package
    ...     def _meth(self):
    ...         pass
    ...
    >>>
    """

    def check_valid_name(func: Callable):
        func_name = func.__name__
        if not func_name.startswith('_') or func_name.startswith('__'):
            raise ValueError('All internal function names must start with one and only one underscore')

    # handle the case where no types were specified:
    if len(types) == 1 and type(types[0]).__name__ in ('function',):
        method = types[0]
        check_valid_name(method)
        return method

    # when types specified, the return must be the "actual" decorator that will wrap the function:
    def decorator(func):
        check_valid_name(func)
        return func

    return decorator
