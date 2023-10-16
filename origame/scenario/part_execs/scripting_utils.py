# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Scripting Utilities

This module is shared by other modules such as FunctionPart and SqlPart.

Version History: See SVN log.
"""
# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import inspect
from collections import OrderedDict

# [2. third-party]

# [3. local]
from ...core.typing import AnnotationDeclarations
from ...core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ..defn_parts import BasePart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'LinkedPartsScriptingProxy',
    'check_link_name_is_frame',
    'get_signature_from_str',
    'get_params_from_str',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    PartLink = 'PartLink'
    PartFrame = 'PartFrame'


FuncWrapper = Callable[..., None]


# -- Function definitions -----------------------------------------------------------------------

def check_link_name_is_frame(link_name_hint: str) -> Tuple[bool, str]:
    """
    Figures out if the caller wants to access the part frame or the part itself.

    :param link_name_hint: The name of the link that points to another part; or the "_" enclosed name of the link
    that points to the part frame of another part.
    :return: True, if it is for the part frame. The link name, with the frame markers "_" stripped if applicable.
    """
    is_part_frame = len(link_name_hint) >= 3 and link_name_hint.startswith('_') and link_name_hint.endswith('_')
    pure_link_name = link_name_hint
    if is_part_frame:
        # Stripping off the enclosing "_". For example, _clock_ means a part frame. After the underscores are
        # stripped off, clock means the link name.
        pure_link_name = link_name_hint[1: -1]
    return is_part_frame, pure_link_name


def get_func_proxy_from_str(param_str: str) -> FuncWrapper:
    """
    Gets the function object for a hypothetical function that had param_str as string-representation of its
    call parameters, ie of 'def func(<param_str>): pass'. Example: if param_str is the string 'a, b, c',
    then the object returned is a function that corresponds to 'def func(a, b, c): pass'.

    :param param_str: a string representing the sequence of function call parameters; it can contain type
        annotations as well as default values, basically it must follow the rules for function signatures
    :raises SyntaxError: if param_str leads to invalid Python function definition syntax
    """
    wrapped_script = "def func_proxy({}): pass".format(param_str)
    script_namespace = {}
    exec(wrapped_script, script_namespace)
    func_obj = script_namespace['func_proxy']
    return func_obj


def get_signature_from_str(param_str: str) -> inspect.signature:
    """
    Get the signature object for a hypothetical function that had param_str as string-representation of its
    call parameters, ie of 'def func(<param_str>): pass'. Example: if param_str is the string 'a, b, c',
    then signature will be that of 'def func(a, b, c): pass'.

    :param param_str: a string representing the sequence of function call parameters; it can contain type
        annotations as well as default values, basically it must follow the rules for function signatures
    :raises SyntaxError: if param_str leads to invalid Python function definition syntax
    """
    return inspect.signature(get_func_proxy_from_str(param_str))


def get_params_from_str(param_str: str) -> Dict[str, type]:
    """
    Get a dictionary of parameter names and expected argument type. Example: if param_str is the string
    'a, b: int, c: []=None', then signature will be {'a': Any, 'b': int, 'c': []}

    :param param_str: a string representing the sequence of function call parameters; it can contain type
        annotations as well as default values, basically it must follow the rules for function signatures
    :return: a dictionary where key is parameter name, and value is the type (object if no type annotation found)
    :raises SyntaxError: if param_str leads to invalid Python function definition syntax
    """
    signature = get_signature_from_str(param_str)

    def get_param_type(param_obj: inspect.Parameter) -> type:
        obj_type = param_obj.annotation
        if obj_type == inspect.Parameter.empty:
            obj_type = object
        return obj_type

    name_annotation = OrderedDict()
    for param_obj in signature.parameters.values():
        name_annotation[param_obj.name] = get_param_type(param_obj)

    return name_annotation


# -- Class Definitions --------------------------------------------------------------------------

class LinkedPartsScriptingProxy:
    """
    Proxy object provides attribute-like access to parts linked from another Part.

    This class enforces a naming convention on the attribute name. If it is prefixed and suffixed with "_",
    the part frame of the part will be retrieved; otherwise the part itself.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: BasePart):
        """:param part: The part from which links go to other parts"""
        self.__part = part
        self.__link_cache = {}
        self.__link_target_cache = {}

        self.__part_frame_cache = dict()

        # The names of outgoing links can be temporary. For example, a name is being edited and is not applied yet.
        # We need to know the relationship between a temporary name and its real name.
        self.__map_temp_to_real = dict()

    def update_temp_link_name(self, new_temp_name: str, link: Decl.PartLink):
        """
        The names of outgoing links can be temporary. For example, a name is being edited and is not applied yet.
        We need to know the relationship between a temporary name and its real name. 
        
        This function updates the internal map that tracks the relationship.
        
        :param new_temp_name: A temporary link name for the real link name
        :param link: The real link
        """
        self.invalidate_link_cache(link.name)
        self.invalidate_link_cache(new_temp_name)
        if link.temp_name is None:
            if new_temp_name != link.name:
                link.temp_name = new_temp_name
                self.__map_temp_to_real[new_temp_name] = link.SESSION_ID
        else:
            self.invalidate_link_cache(link.temp_name)
            self.__map_temp_to_real.pop(link.temp_name)
            if new_temp_name == link.name:
                link.temp_name = None
            else:
                link.temp_name = new_temp_name
                self.__map_temp_to_real[new_temp_name] = link.SESSION_ID

    def clear_temp_link_names(self):
        """
        Clears the relationship established in the update_temp_link_name()
        """
        for link in self.__part.part_frame.outgoing_links:
            self.invalidate_link_cache(link.name)
            if link.temp_name is not None:
                self.invalidate_link_cache(link.temp_name)
                link.temp_name = None

        self.__map_temp_to_real.clear()

    def invalidate_link_cache(self, link_name: str):
        """
        If the object represented by the link name exists in the cache, this function deletes it and the link from the
        target cache. If the object is cached with the key the "_" + link_name + "_", it will be deleted too.
        :param link_name: The key used to cache the object
        """
        cached_obj = self.__link_cache.get(link_name)
        if cached_obj is not None:
            log.debug('Removing link keyed by "{}" from part {} link cache', link_name, self.__part)
            del self.__link_cache[link_name]
            self.invalidate_target_cache(cached_obj)

        frame_name = "_" + link_name + "_"
        cached_obj = self.__part_frame_cache.get(frame_name)
        if cached_obj is not None:
            log.debug('Removing frame keyed by "{}" from part {} frame cache', frame_name, self.__part)
            del self.__part_frame_cache[frame_name]

    def invalidate_target_cache(self, link: Decl.PartLink):
        if link.SESSION_ID in self.__link_target_cache:
            link_target = self.__link_target_cache[link.SESSION_ID]
            log.debug('Removing link "{}" target {} from part {} link target cache',
                      link.name,
                      link_target,
                      self.__part)
            del self.__link_target_cache[link.SESSION_ID]

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    def __dir__(self) -> List[str]:
        """
        Provides a list of all the names accessible through this object. The names either point to parts or part frames.
        If a name contains a "_" prefix and a "_" suffix, the name points to a part frame.
        :return A list of names pointing to parts or part frames.
        """
        name_list = list()
        for link in self.__part.part_frame.outgoing_links:
            temp_name = link.temp_name
            name = link.name if temp_name is None else temp_name
            name_list.append(name)
            name_list.append('_{}_'.format(name))

        return name_list

    def __getattr__(self, attr_name: str) -> Either[BasePart, Decl.PartFrame]:
        """
        If this method is called, it is because script is asking for an attribute that does not exist:
        assume it is a link name: self.A looks for the part that is at end of link named "A", self._A_
        looks for the part FRAME that is at end of link named "A".

        Special cases:
        - if part at end of A is a Variable part, return its internal object; virtual method is used to resolve this
        - if part at end of A is a Node part, return part at end of node chain; virtual method is used to resolve this

        :param attr_name: The name of the link that points to another part; or the "_" enclosed name of the link
            that points to the part frame of another part.
        :return: the part or part frame, depending on presence/location of underscores in attr_name
        """
        if attr_name == '__objclass__':
            # Jedi code completer asks for this attribute, and seems to expect an AttributeError in
            # the context it is is when asking for this attribute; not clear if doing this here will
            # interfere with function call signature code completion
            raise AttributeError

        if attr_name == '__name__':
            # Jedi code completer asks for this attribute, and seems to expect self's class name:
            return self.__class__.__name__

        # 1.
        # Try link cache first blindly first. If an entry is not found, try the frame cache. If an entry is still
        # not found, start caching.
        cached_link = self.__link_cache.get(attr_name)
        if cached_link is not None:
            return self.__get_and_cache_link_target(cached_link)

        # 2.
        # Not a link. Try the part frame cache
        cached_frame = self.__part_frame_cache.get(attr_name)
        if cached_frame is not None:
            return cached_frame

        # 3.
        # Not cached yet. Cache it as a link and its target, if any, or a part frame.
        return self.__get_and_cache_object(attr_name)

    def __setattr__(self, attr_name: str, value: Any):
        """
        Provide attribute-like setting: self.A = B replaces the part at end of link named "A" with B. Note
        that this is only allowed on parts proper, not on their frames, i.e. we don't support self._A_ = B.
        """
        if attr_name.startswith('_'):
            object.__setattr__(self, attr_name, value)
            return

        link_name = attr_name
        cached_obj = self.__link_cache.get(link_name)
        if cached_obj is None:
            link = self.__part.part_frame.get_outgoing_link(link_name)
            if link is None:
                raise ValueError("Part '{}' does not have a link named '{}'".format(self.__part.name, link_name))
            else:
                self.__link_cache[link_name] = link
        else:
            link = cached_obj

        part = link.target_part_frame.part
        part.assign_from_object(value)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_and_cache_object(self, attr_name) -> Either[Decl.PartFrame, object, None]:
        """
        If the attr_name has the pattern _string_, we cache it as a part frame; otherwise, a link. If the link has a
        target, we also cache it.
        :param attr_name: Used as a key for the cached object
        :return: The value of the link target
        """

        # assume attr_name is link name with or without underscore (to indicate
        # whether target is part or part frame)
        is_part_frame, link_name = check_link_name_is_frame(attr_name)
        mapped_link_id = self.__map_temp_to_real.get(link_name)
        if mapped_link_id is None:
            link = self.__part.part_frame.get_outgoing_link(link_name)
            if link is None:
                raise ValueError("Part '{}' does not have a link named '{}'".format(
                    self.__part.name,
                    link_name))

            if link.temp_name is not None:
                raise ValueError("Part '{}' has a link named '{}', but has an unapplied name '{}'".format(
                    self.__part.name,
                    link_name,
                    link.temp_name))

        else:
            link = self.__part.part_frame.get_outgoing_link_by_id(mapped_link_id)
            if link is None:
                raise ValueError("Part '{}' does not have a link id mapped to '{}'".format(
                    self.__part.name,
                    link_name))

        if is_part_frame:
            self.__part_frame_cache[attr_name] = link.target_part_frame
            return link.target_part_frame
        else:
            self.__link_cache[attr_name] = link
            return self.__get_and_cache_link_target(link)

    def __get_and_cache_link_target(self, link) -> Either[None, object]:
        """
        Node parts resolve to the part at the far end of a node chain. That is clearly an expensive operation, 
        so we cache the target too.
        :param link: The link that may have the part at the far end of a node chain.
        :return: The target value of the link
        """
        target = self.__link_target_cache.get(link.SESSION_ID)
        if target is None:
            # add the link target to the cache
            part = link.target_part_frame.part
            target = part.get_as_link_target_part()
            if target is None:
                log.debug('WARNING: the link {} does not have a target!', link.name)
                return None

            self.__link_target_cache[link.SESSION_ID] = target

        # now that we have the target, some types of parts "appear to be values", such as Variable part:
        return target.get_as_link_target_value()

