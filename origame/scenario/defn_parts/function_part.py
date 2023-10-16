# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains the FunctionPart class definition and supporting code.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path
import textwrap
from enum import IntEnum, unique, Enum
from inspect import Parameter

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...core.utils import plural_if

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys, OriFunctionPartKeys as FpKeys
from ..part_execs import PyScriptExec, PyScriptFuncCallError, IExecutablePart
from ..proto_compat_warn import prototype_compat_method_alias
from ..alerts import ScenAlertLevelEnum

from .base_part import BasePart
from .actor_part import ActorPart
from .part_frame import DetailLevelEnum
from .part_types_info import register_new_part_type
from .common import Position
from .scripted_scen_modifiers import ScriptedScenModifierPart
from .scripted_part import IScriptedPart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module
    'FunctionPart',
    'RunRolesEnum',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ErrorCatEnum(Enum):
    default_missing = range(1)


@unique
class RunRolesEnum(IntEnum):
    """
    This class represents the run roles which may be assigned to a supporting part. "Run Roles" are an advancement of
    the original run priority (reset/startup/normal) that could be supported by Function Parts.
    The details surrounding these roles is still TBD. See email: Subject: "reset/startup", From: Stephen Okazawa, To:
    Oliver Schoenborn, Date: December-08-14 10:31 AM.
    """
    setup, reset, startup, finish, batch = range(5)


class FunctionPart(ScriptedScenModifierPart, IExecutablePart):
    """
    This class represents Function parts in the scenario, i.e. parts that represent Python functions.
    It is executable/callable, so it adds over ScriptedScenModifierPart the concept of run roles and call parameters.
    """

    class FuncSignals(BridgeEmitter):
        sig_run_role_added = BridgeSignal(int)  # RunRolesEnum
        sig_run_role_removed = BridgeSignal(int)  # RunRolesEnum
        sig_run_role_reprioritized = BridgeSignal(int, int, int)  # RunRolesEnum, new priority, old priority

    DEFAULT_ROLE_PRIORITY = 0

    CAN_BE_LINK_SOURCE = True
    PART_TYPE_NAME = "function"
    DESCRIPTION = """\
        Functions are used to define events that occur in the simulation.  The function can be called
        or signaled by other functions that are linked to it.

        Double-click to edit the function.

        Click the run button in the upper-right corner of this part to run the function.

        To create a link to another part, right-click and choose "Create Link" and then click on the other part.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this Part
        :param position: A position to be assigned to the newly instantiated default FunctionPart. This argument
            is only required when the ori_def default (None) is used.
        """
        ScriptedScenModifierPart.__init__(self, parent, name=name, position=position)
        IExecutablePart.__init__(self)

        self.func_signals = FunctionPart.FuncSignals()

        self.__run_roles = set()  # no roles by default; don't care about priority
        self.__roles_prioritizing = {}  # priority relative to other parts that have roles

        self._update_debuggable_script(self._get_whole_script())

    def get_run_roles(self) -> Set[RunRolesEnum]:
        """
        Get the run roles of this part.
        :return: a set() of RunRolesEnum
        """
        return self.__run_roles

    def set_run_roles(self, roles: Set[RunRolesEnum]):
        """
        Replace the current roles with those in given set, with default prioritizing for each role (use
        set_roles_and_prioritizing() to also set the prioritizing).
        :param roles: the set of roles for this part (previous roles are discarded)
        """
        self.clear_roles()
        for role in roles:
            self.set_run_role(role)
        assert not self.__roles_prioritizing

    def set_roles_and_prioritizing(self, map_role_to_priority: Dict[RunRolesEnum, int]):
        """
        Clear the current roles of this part, then set the roles found as keys of map_role_to_priority, and the
        role prioritizing per the values of that map.
        :param map_role_to_priority: maps roles to set to their priority
        """
        self.clear_roles()
        for role, priority in map_role_to_priority.items():
            self.set_run_role(role, priority=priority)
        assert self.__run_roles.issuperset(self.__roles_prioritizing)

    def get_roles_and_prioritizing(self) -> Dict[RunRolesEnum, int]:
        """Get a map of roles set on this part, to their prioritizing"""
        assert self.__run_roles.issuperset(self.__roles_prioritizing)
        return {role: self.__roles_prioritizing.get(role, self.DEFAULT_ROLE_PRIORITY)
                for role in self.__run_roles}

    def set_roles_prioritizing(self, value: int):
        """Set the priority of each role that this part already has to a value."""
        for role in self.__run_roles:
            self.set_role_priority(role, value)

    def set_default_roles_prioritizing(self):
        """Set the priority of each role that this part already has to the default prioritizing value."""
        self.set_roles_prioritizing(self.DEFAULT_ROLE_PRIORITY)

    def clear_roles(self):
        """Remove all run roles already assigned to this part"""
        for role in self.__run_roles.copy():
            self.set_run_role(role, False)
        assert not self.__run_roles
        assert not self.__roles_prioritizing

    def set_run_role(self, role_enum: RunRolesEnum, state: bool = True, priority: int = DEFAULT_ROLE_PRIORITY):
        """
        Change whether this part has or doesn't have a specific run role.
        :param role_enum: The role to be associated with the part.
        :param state: True if the new role is to be assigned; false if the role is to be unassigned
        :param priority: (optional) when state=True, the priority relative to other parts with same role
            (ignored when state=False)
        """
        if not self._sim_controller:
            raise RuntimeError("No reference to SimController instance, can't register")

        if state:
            if role_enum not in self.__run_roles:
                self.__run_roles.add(role_enum)
                self._sim_controller.register_part_with_role(self, role_enum)
                if self._anim_mode_shared:
                    self.func_signals.sig_run_role_added.emit(role_enum.value)

            if priority != self.DEFAULT_ROLE_PRIORITY:
                self.set_role_priority(role_enum, priority)

        else:
            if role_enum in self.__run_roles:
                if role_enum in self.__roles_prioritizing:
                    del self.__roles_prioritizing[role_enum]

                self.__run_roles.remove(role_enum)
                self._sim_controller.unregister_part_with_role(self, role_enum)
                if self._anim_mode_shared:
                    self.func_signals.sig_run_role_removed.emit(role_enum.value)

            else:
                # nothing to do if the role is already unset
                assert role_enum not in self.__roles_prioritizing

    def set_role_priority(self, role: RunRolesEnum, priority: int):
        """
        Set the role priority of this part relative to other parts with same role. Higher numbers have precedence
        over lower numbers.
        :param role: which role to prioritize
        :param priority: relative priority indicator; number between DEFAULT_ROLE_PRIORITY and 100
        """
        current_priority = self.get_role_priority(role)
        if current_priority is None:
            raise ValueError('Cannot set role {} priority on {}: part does not have that role', role, self)

        if current_priority != priority:
            if priority == self.DEFAULT_ROLE_PRIORITY:
                del self.__roles_prioritizing[role]
            else:
                self.__roles_prioritizing[role] = priority
            if self._anim_mode_shared:
                self.func_signals.sig_run_role_reprioritized.emit(role.value, priority, current_priority)

    def get_role_priority(self, role: RunRolesEnum) -> Optional[int]:
        """
        Get this part's role priority.
        :param role: which role for which to get priority.
        :return: the integer representing the priority relative to other parts with same role, or None if
            the part does not have given role.
        """
        if role not in self.__run_roles:
            return None

        return self.__roles_prioritizing.get(role, self.DEFAULT_ROLE_PRIORITY)

    @override(PyScriptExec)
    def get_debug_line_offset(self) -> int:
        """
        Every Function part script has an additional line inserted at top, for function def, so every time
        line numbers are moved between UI and debugger, the offset must be added/removed:
        """
        return 1

    @override(BasePart)
    def on_removing_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        BasePart.on_removing_from_scenario(self, scen_data, restorable=restorable)
        for role in self.run_roles:
            self._sim_controller.unregister_part_with_role(self, role)
        IExecutablePart.on_removed_from_scenario(self, scen_data, restorable=restorable)

    @override(BasePart)
    def on_restored_to_scenario(self, scen_data: Dict[BasePart, Any]):
        BasePart.on_restored_to_scenario(self, scen_data)
        for role in self.run_roles:
            self._sim_controller.register_part_with_role(self, role)
        IExecutablePart.on_restored_to_scenario(self, scen_data)

    # --------------------------- instance PUBLIC properties ----------------------------

    run_roles = property(get_run_roles, set_run_roles)
    roles_and_prioritizing = property(get_roles_and_prioritizing, set_roles_and_prioritizing)

    # prototype compatibility adjustments:
    get_params = prototype_compat_method_alias(IExecutablePart.get_parameters, 'get_params')
    set_params = prototype_compat_method_alias(IExecutablePart.set_parameters, 'set_params')

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (roles_and_prioritizing,)
    META_AUTO_SEARCHING_API_EXTEND = (run_roles,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        set_run_role,
        run_roles, get_run_roles, set_run_roles,
        roles_and_prioritizing, get_roles_and_prioritizing, set_roles_and_prioritizing,
    )
    META_SCRIPTING_CONSTANTS = (RunRolesEnum, DetailLevelEnum)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScriptedPart)
    def _on_get_ondemand_alerts(self):
        IScriptedPart._on_get_ondemand_alerts(self)
        # Reset, Startup, Finish, Batch
        if (RunRolesEnum.reset in self.__run_roles
            or RunRolesEnum.startup in self.__run_roles
            or RunRolesEnum.finish in self.__run_roles
            or RunRolesEnum.batch in self.__run_roles):
            data_map = dict()
            for param_val in self.get_signature().parameters.values():
                if param_val.kind in [Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD]:
                    # The *args, **kwargs may not be useful in the part with those roles, but harmless.
                    continue

                if param_val.default is not Parameter.empty:
                    continue

                data_map[param_val.name] = 'missing'

            if not data_map:
                return

            msg = "This part cannot have required arguments due to its role{}.".format(plural_if(self.__run_roles))
            self._add_ondemand_alert(ScenAlertLevelEnum.error, ErrorCatEnum.default_missing, msg, **data_map)

    @override(IExecutablePart)
    def _on_parameters_changed(self):
        self._update_debuggable_script(self._get_whole_script())

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        ScriptedScenModifierPart._set_from_ori_impl(self,
                                                    ori_data=ori_data,
                                                    context=context,
                                                    **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        map_run_role_to_priority = part_content.get(FpKeys.ROLES_AND_PRIORITIZING)
        if map_run_role_to_priority is None:
            map_run_role_to_priority = part_content.get(FpKeys.ROLES_AND_PRIORITIZING_ALIASES)

        self.clear_roles()
        if map_run_role_to_priority is None:
            # must be legacy scenario, add each role from RUN_ROLES key with default prioritizing:
            for role in part_content.get(FpKeys.RUN_ROLES, []):
                self.set_run_role(RunRolesEnum[role])

        else:
            for role, priority in map_run_role_to_priority.items():
                self.set_run_role(RunRolesEnum[role], priority=priority)

        self.parameters = part_content.get(FpKeys.PARAMETERS, self._param_str) or ''
        self._update_debuggable_script(self._get_whole_script())

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = ScriptedScenModifierPart._get_ori_def_impl(self, context, **kwargs)
        func_ori_def = {
            FpKeys.ROLES_AND_PRIORITIZING: {role.name: priority
                                            for role, priority in self.roles_and_prioritizing.items()},
            FpKeys.PARAMETERS: self._param_str,
        }

        ori_def[CpKeys.CONTENT].update(func_ori_def)
        return ori_def

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        ScriptedScenModifierPart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        snapshot.update({
            FpKeys.ROLES_AND_PRIORITIZING: self.roles_and_prioritizing.copy(),
            FpKeys.PARAMETERS: self._param_str,
        })

    @override(IExecutablePart)
    def _exec(self, _debug_mode: bool, _as_signal: bool, *args, **kwargs):
        """
        Define how to "execute" this function part, i.e. how to call the function with body equal to
        the script of this part.
        :raise PyScriptCompileError: if could not compile script
        :raise PyScriptFuncRunError: if could not execute the script that defines the function
        :raise PyScriptFuncCallError: if args or kwargs don't match the parameters signature of defined function
        """
        # may need compilation since last exec:
        if self._check_compile_and_exec():
            self.__func_obj = self.get_from_namespace(self.__unique_func_name)

        # there is no difference between signal and call for function parts:
        try:
            return self._py_exec(self.__func_obj, *args, _debug_mode=_debug_mode, **kwargs)

        except PyScriptFuncCallError as exc:
            # replace the user-unfriendly name by the one the user knows
            message = str(exc).replace(self.__unique_func_name, self.name)
            raise PyScriptFuncCallError(exc_message=message)

    @override(ScriptedScenModifierPart)
    def _get_whole_script(self) -> str:
        """
        This first wraps the Function Part's script string to define a Python function with specified parameters,
        and gives that to base class _update_debuggable_script.
        """
        params = self._param_str  # if no parameters, should be empty string
        script = self._script_str or "pass"  # if no script, should be pass
        # save it to temp file so it can be debugged; always use same file
        self.__unique_func_name = 'func_' + Path(self.debug_file_path).name
        return "def {}({}):\n{}".format(self.__unique_func_name, params, textwrap.indent(script, ' ' * 4))


# Add this part to the global part type/class lookup dictionary
register_new_part_type(FunctionPart, FpKeys.PART_TYPE_FUNCTION)
