# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the LibraryPart class and the functionality that supports the part as
                       a building block for the Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import Enum
from inspect import signature

# [2. third-party]

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ..ori import IOriSerializable, OriContextEnum, OriScenData
from ..ori import OriLibraryPartKeys as LibKeys
from ..defn_parts import ActorPart, Position
from ..alerts import ScenAlertLevelEnum

from .scripted_scen_modifiers import ScriptedScenModifierPart
from .part_types_info import register_new_part_type

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'LibraryPart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ErrorCatEnum(Enum):
    compile, call = range(2)
    
    
class LibraryPart(ScriptedScenModifierPart):
    """
    This scenario part contains a script that can define variables and callables that can be accessed as
    data members of the Library part. For example if the Library part's script has a script with "def f(): print(123)"
    then calling library_part.f() will print 123. If the script does not define f a PyScriptCompileError will result.
    If it does define f but f raises, then attempt to call f will raise PyScriptFuncRunError.
    """

    CAN_BE_LINK_SOURCE = True
    PART_TYPE_NAME = "library"
    DESCRIPTION = """\
        Scripts are used to implement a collection of helper functions or classes that
        are to be available for use in the model.

        Double-click to edit the library code.
    """

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        Default script is empty.
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this Part
        :param position: A position to be assigned to the newly instantiated default LibraryPart. This argument
            is only required when the ori_def default (None) is used.
        """
        ScriptedScenModifierPart.__init__(self, parent, name=name, position=position)
        self._update_debuggable_script(self._script_str)
        # save a copy of the script's namespace variable names so far, for use later by auto-completion:
        self.__script_auto_obj_names = list(self.get_py_namespace().keys())

    def check_script_validity(self):
        """
        Attempt to compile and execute the script.
        :raise: any exception raised as a result of compilating or executing the script
        """
        self._clear_own_alerts(ScenAlertLevelEnum.error, ErrorCatEnum.compile, ErrorCatEnum.call)
        assert not self.has_alerts()
        try:
            self._check_compile_and_exec()
        except Exception as exc:
            self._add_alert(ScenAlertLevelEnum.error, ErrorCatEnum.compile, str(exc), path=self.path)
            raise

    def get_script_function_defs(self) -> Tuple[List[str], List[signature]]:
        """
        Get information about all the callables defined in this part's script. This attempts to compile and run
        the script, so it can raise syntax error etc.
        :return: The list of the callable names and the list of their signatures
        """
        self.check_script_validity()
        names = list()
        signatures = list()

        for obj_name, obj in self.get_py_namespace().items():
            if obj_name not in self.__script_auto_obj_names and not obj_name.startswith("__") and callable(obj):
                names.append(obj_name)
                signatures.append(signature(obj))

        return names, signatures

    def call_script_func(self, func_name: str, *call_args, _debug_mode: bool = False, **call_kwargs):
        """
        Executes a previously selected function.
        :param func_name: The name of the selected function to be executed.
        :param call_args: The positional arguments of the selected function.
        :param _debug_mode: True - to debug
        :param call_kwargs: The keyword arguments of the selected function.
        """
        log.debug('Executable a script function in {} executing via {}', self, ('debug ' if _debug_mode else ''))

        try:
            self._clear_own_alerts(ScenAlertLevelEnum.error, ErrorCatEnum.call)
            func_obj = self.__get_script_func_obj(func_name)
            return self._py_exec(func_obj, *call_args, _debug_mode=_debug_mode, **call_kwargs)

        except Exception as exc:
            self._add_alert(ScenAlertLevelEnum.error, ErrorCatEnum.call, str(exc))
            raise

    def get_script_func_signature(self, func_name: str) -> signature:
        """
        Get the signature of the named function, assumed to be defined in the part's script.
        If it does not exist, a KeyError will be raised.
        """
        return signature(self.__get_script_func_obj(func_name))

    def __getattr__(self, member_name: str) -> Any:
        """
        If attempt to get a member that does not exist in class, attempt to compile and execute the script,
        then look in the script execution namespace (which gets updated automatically when executing it)
        and return found object.
        :param member_name: name of member to get
        :return: the Python object that member_name points to
        :raise: any exceptions raised by self._check_compile_and_exec()
        """
        self.check_script_validity()
        return self.get_from_namespace(member_name)

    def __dir__(self):
        """For code completion, need to return script objects"""
        try:
            self.check_script_validity()
        except:
            # error in script: just ignore, means no code completion available for objects defined by script
            pass

        objects_from_script = set(self.get_py_namespace()).difference(self.__script_auto_obj_names)
        # __builtins__ gets added by eval(), which may or may not have been run: if there, remove it!
        try:
            objects_from_script.remove('__builtins__')
        except ValueError:
            pass

        return super().__dir__() + list(objects_from_script)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SCRIPTING_API_EXTEND = ()

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        ScriptedScenModifierPart._set_from_ori_impl(self,
                                                    ori_data=ori_data,
                                                    context=context,
                                                    **kwargs)

        self._update_debuggable_script(self._script_str)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_script_func_obj(self, func_name: str) -> Callable:
        """
        Searches the namespace by name and returns the public script function object that only belongs to this part.
        :param func_name: The name of the function to be executed.
        :return: The public script function that belongs to this part.
        :raises KeyError: If the script function specified by the func_name does not exist.
        """
        for obj_name in self.get_py_namespace():
            obj = self.get_from_namespace(obj_name)
            if obj_name not in self.__script_auto_obj_names and not obj_name.startswith("__") and callable(obj):
                if obj_name == func_name:
                    return obj

        raise KeyError("{} does not exist.".format(func_name))


register_new_part_type(LibraryPart, LibKeys.PART_TYPE_LIBRARY, ori_aliases=LibKeys.PART_TYPE_LIBRARY_ALIASES)
