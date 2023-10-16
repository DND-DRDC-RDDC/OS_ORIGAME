# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Methods related to compatibility module

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
from functools import wraps
import logging

# [2. third-party]

# [3. local]
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'warn_proto_compat_funcs',
    'prototype_compat_method',
    'prototype_compat_method_alias',
    'prototype_compat_property_alias'
]

proto_log = logging.getLogger('system')
# proto_log.setLevel(logging.WARNING)

SHOW_PROTO_COMPATIBILITY_WARNINGS = True


# -- Function definitions -----------------------------------------------------------------------

def warn_proto_compat_funcs(value: bool = True):
    # proto_log.setLevel(logging.WARNING if value else logging.CRITICAL)
    global SHOW_PROTO_COMPATIBILITY_WARNINGS
    SHOW_PROTO_COMPATIBILITY_WARNINGS = value


def prototype_compat_method(proto_method: Any):
    """
    Decorator to mark a scenario part method as being available only for prototype compatibility, and there is no
    equivalent Origame scenario method. This will cause a warning to be logged whenever the method is used. Users
    should convert their scripts as soon as possible after import from prototype scenario. Users should not
    use methods marked with prototype_compat_method in new scenarios.

    :param proto_method: the (unbound) method to mark as available only for compatibility
    :return: the wrapped method so that when called, a log message is automatically generated

    Example:
        class SomePartType(BasePart):
            ...
            @prototype_compat_method
            def some_proto_meth(self, ...):
                ...
            ...
    """

    @wraps(proto_method)
    def prototype_func_wrapper(*args, **kwargs):
        if SHOW_PROTO_COMPATIBILITY_WARNINGS:
            proto_log.warning('Calling deprecated method {}, replace ASAP by equiv. functionality',
                              proto_method.__name__)
        return proto_method(*args, **kwargs)

    prototype_func_wrapper.original_method = proto_method
    return prototype_func_wrapper


def prototype_compat_method_alias(ori_method: Any, proto_name: str = '<name not available>'):
    """
    Create a scenario part method strictly for prototype compatibility, and indicate which equivalent Origame
    scenario method it aliases. This will cause a warning to be logged whenever the method is used. Users should
    convert their scripts as soon as possible after import from prototype scenario. Users should not
    use methods marked with prototype_compat_method_alias in new scenarios.

    :param proto_method: the (unbound) method to mark as available only for compatibility
    :param proto_name: the name of the method in the prototype's scripting API
    :return: the wrapped method so that when called, a log message is automatically generated

    Example:

        class SomePartType(BasePart):
            ...
            proto_meth = prototype_compat_method_alias(ori_meth, 'proto_meth')
            ...

    Note: the proto_name must be the string representation of method created, as it will be logged
    """

    @wraps(ori_method)
    def prototype_func_wrapper(*args, **kwargs):
        if SHOW_PROTO_COMPATIBILITY_WARNINGS:
            proto_log.warning('Calling deprecated method {} (call {} instead)', proto_name, ori_method.__name__)
        return ori_method(*args, **kwargs)

    return prototype_func_wrapper


def prototype_compat_property_alias(property_obj: Any, proto_name: str):
    """
    Create a scenario part property strictly for prototype compatibility, and indicate which equivalent Origame
    scenario property it aliases. This will cause a warning to be logged whenever the method is used. Users should
    convert their scripts as soon as possible after import from prototype scenario. Users should not
    use methods marked with prototype_compat_method_alias in new scenarios.

    :param property_obj: the (unbound) property to mark as available only for compatibility
    :param proto_name: the name of the property in the prototype's scripting API
    :return: the wrapped property so that when used, a log message is automatically generated

    WARNING: this method assumes that the coding standard is followed for properties: property A has a get_A(self)
    getter and a set_A(val) setter.

    Example:

        class SomePartType(BasePart):
            ...
            proto_prop = prototype_compat_property_alias(ori_prop, 'proto_prop')
            ...

    Note: the proto_name must be the string representation of property created, as it will be logged
    """
    class_name, ori_name = property_obj.fget.__qualname__.split('.')[-2:]
    assert ori_name.startswith('get_')
    if ori_name.startswith('get_'):
        ori_name = ori_name.replace('get_', '', 1)
    get_msg = 'Getting deprecated property "{}" of {} (use "{}" instead)'.format(proto_name, class_name, ori_name)
    set_msg = 'Setting deprecated property "{}" of {} (use "{}" instead)'.format(proto_name, class_name, ori_name)

    @wraps(property_obj)
    def prototype_property_getter(self):
        if SHOW_PROTO_COMPATIBILITY_WARNINGS:
            proto_log.warning(get_msg)
        return property_obj.fget(self)

    @wraps(property_obj)
    def prototype_property_setter(self, value):
        if SHOW_PROTO_COMPATIBILITY_WARNINGS:
            proto_log.warning(set_msg)
        return property_obj.fset(self, value)

    return property(prototype_property_getter, prototype_property_setter)
