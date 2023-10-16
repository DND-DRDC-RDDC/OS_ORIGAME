# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provide functionality common to scenario parts that have script that can modify the scenario

Scenario modification includes simulation control.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import re

# [2. third-party]

# [3. local]
from ...core import BridgeEmitter, BridgeSignal, override, override_optional
from ...core import HOURS_TO_DAYS, MINUTES_TO_DAYS, SECONDS_TO_DAYS
from ...core.utils import FileLock, timedelta_to_rel, rel_to_timedelta
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys, OriLibraryPartKeys as LibKeys, OriPyScriptExecKeys as PsxKeys
from ..event_queue import EventQueue
from ..part_execs import PyScriptExec, IExecutablePart, PyScenarioImportsManager
from ..proto_compat_warn import prototype_compat_method_alias
from ..batch_data import DataPathTypesEnum
from ..alerts import IScenAlertSource

from .base_part import BasePart
from .actor_part import ActorPart
from .common import Position, Vector
from .part_frame import PartFrame
from .part_types_info import get_scripting_constants
from .part_link import TypeReferencingParts, PartLink, TypeMissingLinkInfo
from .scripted_part import IScriptedPart

# DRDC prototype uses pyodbc which has same API as pypyodbc so re-direct theirs to
# the one used by Origame:
import pypyodbc
import sys

sys.modules['pyodbc'] = pypyodbc
import pyodbc

assert pyodbc is pypyodbc

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'ScriptedScenModifierPart',
    'SimControllerReaderProxy',
    'SimControllerProxy'
]

log = logging.getLogger('system')

NEW_PART_OFFSET_X = 15  # offset of new part from creator part, along x

PartFrames = List[Either[str, PartFrame]]


class Decl(AnnotationDeclarations):
    SimController = 'SimController'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ScriptedScenModifierPart(BasePart, PyScriptExec, IScriptedPart):
    """
    This class implements the logic common to scenario parts that have a Python script that can modify a scenario.
    It extends BasePart to contain a script as ORI data, and to provide certain scripting functions such as
    new_part, new_link, etc. It intercepts certain script-related operations to make the script available to
    the PyScriptExec base class.
    """

    # NOTE: functions that are published in the scripting API must have a consistent API. For instance, functions
    # that work on parts linked from self should be referenced by part frame instead of part, and should all
    # support the part frame being given directly or via the name of a link. This affects for example copy_contents,
    # copy_parts, reparent_parts, new_link, etc.

    unsupported_proto_api = [
        'xkcd_on',
        'xkcd_off',
        'asap',
        'nextFuncID',
        'excel_column_letter',
        'translate_excel_column',
        'translate_excel_index',
        'translate_excel_range',
        'get_placeholder_string',
        'get_query_type',
        'get_db_name',
        'extract_kw_uses',
        'parse',
        'get_result',
        'report_fields_and_data',
    ]

    DEFAULT_VISUAL_SIZE = dict(width=10.0, height=5.1)

    class ScriptingSignals(BridgeEmitter):
        sig_script_changed = BridgeSignal(str)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this Part
        :param position: A position to be assigned to the newly instantiated default part. This argument
            is only required when the ori_def default (None) is used.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.scripting_signals = ScriptedScenModifierPart.ScriptingSignals()

        # sim controller and event queue:
        if self._shared_scenario_state:
            self._sim_controller = self._shared_scenario_state.sim_controller
            scen_script_imports_mgr = self._shared_scenario_state.scen_script_imports_mgr
        else:
            self._sim_controller = None
            scen_script_imports_mgr = PyScenarioImportsManager()

        PyScriptExec.__init__(self, scen_script_imports_mgr)

        self._setup_namespace()
        self._script_str = ""

    @override(BasePart)
    def update_temp_link_name(self, new_temp_name: str, link: PartLink):
        """
        Forwards the execution to the proxy.
        """
        self._parts_proxy.update_temp_link_name(new_temp_name, link)

    @override(BasePart)
    def clear_temp_link_names(self):
        """
        Forwards the execution to the proxy.
        """
        self._parts_proxy.clear_temp_link_names()

    def get_script(self) -> str:
        """
        Get the script of the Function part.
        """
        return self._script_str

    def set_script(self, script_str: str):
        """
        Set the script text.
        :param script_str: The new script.
        :raise: Exception if invalid script (SyntaxError, TypeError)
        """
        if self._script_str != script_str:
            self._script_str = script_str
            self._update_debuggable_script(self._get_whole_script())
            # reset the namespace since any symbols defined by the script that were added by last execution of script
            # are possible no longer valid:
            self._setup_namespace()
            if self._anim_mode_shared:
                self.scripting_signals.sig_script_changed.emit(self._script_str)

    def new_part(self, part_type: str, name: str = None, pos: Tuple[float, float] = None) -> BasePart:
        """
        Create a new part in our parent actor, linked to self. This function is expected to be script driven.
        :param part_type: The type of part to be added.
        :param name: The name of the new part and also the link from this instance to the new part.
        :param pos: The position of the new part. If the position is not specified, the new part
            is given a position at a default offset from the current instance's position.
        :return: the scenario part created
        :raises: RuntimeError: A link originating from this instance already exists with the specified name.
        """
        if name is not None and (
                    self._part_frame.is_link_name_taken(name) or self._part_frame.is_link_temp_name_taken(name)):
            raise RuntimeError('Link already exists with this name')

        if pos is None:
            pos_x, pos_y = self._part_frame.get_position()
            pos = Position(pos_x + NEW_PART_OFFSET_X, pos_y)
        else:
            pos = Position(*pos)

        new_child = self._parent_actor_part.create_child_part(part_type, name=name, pos=pos)
        self._part_frame.create_link(new_child.part_frame)
        return new_child

    def remove_part(self, link_name_or_part_frame: Either[str, PartFrame]):
        """
        Permanently remove a part from the scenario.
        :param link_name_or_part_frame: if a string, then it represents the link name, for which *target* part will be removed;
            else, it must be the PartFrame instance that contains the scenario part to remove
        """
        part = self.__get_part_from_link_name_or_part_frame(link_name_or_part_frame)
        part.remove_self()

    def copy_parts(self, link_names_or_part_frames: PartFrames, dest_actor: ActorPart = None,
                   paste_offset: Vector = None) -> List[PartFrame]:
        """
        Create a copy of parts. Links to the parts are assumed to exist with self as source, so no new
        links are created.

        :param link_names_or_part_frames: The parts to be copied into this instance, referenced via either
            a link name or their part frame.
        :param paste_offset: Vector(x,y) offset in scenario coordinates, relative to original part positions
        :return: list of newly created children. The children are *not* linked to the function part that created
            them (this can be done easily via a loop such as "for part in copy_parts(): new_link(part.part_frame)").
        """
        parts = [self.__get_part_from_link_name_or_part_frame(obj) for obj in link_names_or_part_frames]
        dest_actor = dest_actor or self.parent_actor_part
        return [part.part_frame for part in dest_actor.copy_parts(parts, paste_offset=paste_offset)]

    def reparent_parts(self, link_names_or_part_frames: PartFrames, dest_actor: ActorPart = None,
                       maintain_links: bool = True, paste_offset: Vector = None):
        """
        Reparent the given parts from their current actor parent to another actor. Links to the parts are assumed
        to exist with self as source, so no new links are created.

        :param link_names_or_part_frames: The parts to be reparented, referenced via either
            a link name or their part frame. The parts MUST all have the same parent actor.
        :param dest_actor: The destination actor; if not specified, uses parent of function part
            from which this function is called
        :param maintain_links: if True, links to and from parts not in "parts" argument will be maintained by
            making necessary adjustments to the interface levels of all parts involved in the operation (i.e.,
            target parts not in the "parts" argument could also be affected);
            if False, the links that would require interface level changes to their source or target are
            eliminated.
        :param paste_offset: Vector(x,y) offset in scenario coordinates, relative to original part positions
        """
        if not link_names_or_part_frames:
            return

        parts = [self.__get_part_from_link_name_or_part_frame(obj) for obj in link_names_or_part_frames]
        source_parent = parts[0].parent_actor_part
        assert all(part.parent_actor_part is source_parent for part in parts)
        dest_actor = dest_actor or self.parent_actor_part
        restore_infos = source_parent.remove_child_parts(parts, restorable=True)
        dest_actor.reparent_child_parts(parts, restore_infos,
                                        maintain_links=maintain_links, paste_offset=paste_offset)

    def new_link(self, from_part_frame: PartFrame, to_part_frame: Either[PartFrame, str], link_name: str = None):
        """
        Create a link between the two frames.
        :param from_part_frame: part frame from which to link
        :param to_part_frame: part frame that target (endpoint) of link; if it is a string = 'parent', the link is
            to from_part_frame's parent actor
        :param link_name: if given, the name of the new link; else the name will be chosen automatically
        """
        if to_part_frame == 'parent':
            from_part_frame.create_link(from_part_frame.part.parent_actor_part.part_frame)
        else:
            from_part_frame.create_link(to_part_frame, link_name=link_name)

    def new_link_to(self, to_part_frame: PartFrame, link_name: str = None):
        """
        Create a link from this part to another part frame.
        :param to_part_frame: part frame that target (endpoint) of link; if it is a string = 'parent', the link is
            to self's parent actor
        :param link_name: if given, the name of the new link; else the name will be chosen automatically
        """
        if to_part_frame == 'parent':
            self._part_frame.create_link(self._parent_actor_part.part_frame, link_name=link_name)
        else:
            self._part_frame.create_link(to_part_frame, link_name=link_name)

    def remove_link(self, link_name_or_from_part_frame: Either[str, PartFrame], to_part_frame: PartFrame = None):
        """
        Remove a link. If there is no link from first part frame to second part frame, does nothing.

        :param link_name_or_from_part_frame: if str, it is the name of outgoing link to delete; else, it is the
            PartFrame instance that is the source of the link to remove
        :param to_part_frame: the PartFrame instance that is the target of the link to remove
        :raise: ValueError if link of given name does not exist, or no link between the two given frames
        """
        if isinstance(link_name_or_from_part_frame, str):
            link_name = link_name_or_from_part_frame
            link = self._part_frame.get_outgoing_link(link_name)
            if not link:
                raise ValueError("no link named {}, cannot delete".format(link_name))
            link.remove_self()

        else:
            from_part_frame = link_name_or_from_part_frame
            link = from_part_frame.get_outgoing_link_to_part(to_part_frame)
            if link:
                link.remove_self()
            else:
                raise ValueError("no link from '{}' (in actor '{}') to '{}'".format(
                    from_part_frame.name, to_part_frame.name, from_part_frame.parent_actor_part.path))

    def remove_link_to(self, to_part_frame: PartFrame):
        """
        Remove the link from from_part_frame to to_part_frame.
        :param to_part_frame: the PartFrame instance that is the target of the link to remove
        :raise: ValueError if no link from self to given frame
        """
        self.remove_link(self.part_frame, to_part_frame=to_part_frame)

    @override(PyScriptExec)
    def get_debug_line_offset(self) -> int:
        """
        Get the number of lines that are at beginning of self._get_whole_script() that should be ignored.
        THese are lines hidden from the user, added by the application to support required functionality.
        A derived class that overrides _get_whole_script() should also override this method.
        """
        return 0

    @override(BasePart)
    def on_outgoing_link_removed(self, link: PartLink):
        PyScriptExec.on_outgoing_link_removed(self, link)

    @override(BasePart)
    def on_outgoing_link_renamed(self, old_name: str, new_name: str):
        PyScriptExec.on_outgoing_link_renamed(self, old_name, new_name)

    @override(BasePart)
    def on_link_target_part_changed(self, link: PartLink):
        PyScriptExec.on_link_target_part_changed(self, link)

    # --------------------------- instance PUBLIC properties ----------------------------

    script = property(get_script, set_script)

    # prototype compatibility adjustments:
    get_code = prototype_compat_method_alias(get_script, 'get_code')
    set_code = prototype_compat_method_alias(set_script, 'set_code')

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (script,) + PyScriptExec.META_AUTO_EDITING_API_EXTEND
    META_AUTO_SEARCHING_API_EXTEND = (script,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        script, get_script, set_script,
        new_part, remove_part,
        new_link, remove_link
    )
    META_SCRIPTING_CONSTANTS = (DataPathTypesEnum,)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenAlertSource)
    def _on_get_ondemand_alerts(self):
        IScriptedPart._on_get_ondemand_alerts(self)

    @override(BasePart)
    def _get_unused_link_info(self, script: str = None) -> List[str]:
        return IScriptedPart._get_unused_link_info(self, script)

    @override(BasePart)
    def _get_missing_link_info(self, script: str = None) -> TypeMissingLinkInfo:
        return IScriptedPart._get_missing_link_info(self, script)

    @override(BasePart)
    def _handle_link_chain_sources(self,
                                   referencing_parts: TypeReferencingParts,
                                   referenced_link_name: str):
        """
        Finds the references to the "referenced_link_name" in the script, and replaces all of them with
        the "new_referenced_link_name", based on the Origame syntax rules.
        """
        self.find(referencing_parts, referenced_link_name)

    @override(BasePart)
    def _handle_link_chain_rename(self,
                                  referencing_parts: TypeReferencingParts,
                                  referenced_link_name: str,
                                  new_referenced_link_name: str = None):
        """
        Finds the references to the "referenced_link_name" in the script, and replaces all of them with
        the "new_referenced_link_name", based on the Origame syntax rules.
        """
        self.replace(referencing_parts, referenced_link_name, new_referenced_link_name)

    @override_optional
    def _get_whole_script(self) -> str:
        """
        Get the script to be used for debugging. Unless overridden, this is the script defined via set_script().
        A derived class can override this if the script must be wrapped before being compiled.
        """
        return self._script_str

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        script_pieces = part_content.get(LibKeys.SCRIPT)
        if script_pieces:
            # Per BasePart._set_from_ori_impl() docstring, set via property.
            self.script = '\n'.join(script_pieces)

        # find if script contains any unsupported calls
        unsups_found = []
        for unsup_api in self.unsupported_proto_api:
            if unsup_api in self._script_str:
                unsups_found.append(unsup_api)
        if unsups_found:
            log.warning("The part '{}' uses unsupported calls: {}. Edit the code before running the scenario.",
                        self, ', '.join(unsups_found))

        self.set_all_imports(part_content.get(PsxKeys.SCRIPT_IMPORTS, {}))

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        func_ori_def = {
            LibKeys.SCRIPT: self._script_str.split('\n'),
            PsxKeys.SCRIPT_IMPORTS: self.get_all_imports()
        }

        ori_def[CpKeys.CONTENT].update(func_ori_def)
        return ori_def

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update({
            LibKeys.SCRIPT: self._script_str,
        })

    @override(PyScriptExec)
    def _setup_namespace(self):
        """
        Adds more objects into the namespace.
        """
        super()._setup_namespace()

        # sim controller and event queue:
        if self._shared_scenario_state:
            sim_proxy = self._shared_scenario_state.sim_controller_scripting_proxy
            self.add_to_namespace('signal', sim_proxy.signal)
            self.add_to_namespace('sim', sim_proxy)
            self.add_to_namespace('delay', sim_proxy.delay)

        # other script functions and vars/consts:
        self.add_to_namespace('ASAP', EventQueue.ASAP_PRIORITY_VALUE)
        self.add_to_namespace('new_part', self.new_part)
        self.add_to_namespace('del_part', self.remove_part)
        self.add_to_namespace('copy_parts', self.copy_parts)
        self.add_to_namespace('reparent_parts', self.reparent_parts)
        self.add_to_namespace('new_link', self.new_link)
        self.add_to_namespace('del_link', self.remove_link)
        self.add_to_namespace('del_link_to', self.remove_link_to)
        self.add_to_namespace('elapsed_to_rel_delta', timedelta_to_rel)
        self.add_to_namespace('rel_delta_to_elapsed', rel_to_timedelta)
        self.add_to_namespace('Vector', Vector)
        if self.shared_scenario_state is not None:
            self.add_to_namespace('batch', self.shared_scenario_state.batch_data_mgr)

        def assign_from(dest_part_frame: Either[str, PartFrame], orig_part_frame: Either[str, PartFrame]):
            """
            Copy the contents of one part to another part of the same type.
            :param dest_part_frame: part to put contents into, specified by its frame or name of a link to the part
            :param orig_part_frame: part to get the contents of, specified by its frame or name of a link to the part
            """
            dest_part = self.__get_part_from_link_name_or_part_frame(dest_part_frame)
            orig_part = self.__get_part_from_link_name_or_part_frame(orig_part_frame)
            dest_part.assign_from_object(orig_part)

        self.add_to_namespace('copy_content', assign_from)
        self.add_to_namespace('FileLock', FileLock)

        # Make all registered scripting constants available to the script:
        for const_name, const_obj in get_scripting_constants().items():
            self.add_to_namespace(const_name, const_obj)

    def __get_part_from_link_name_or_part_frame(self, link_name_or_part_frame: Either[str, PartFrame]) -> BasePart:
        """Resolve the given object to a part. The object can be a part frame, or string represeting a link name"""
        if not isinstance(link_name_or_part_frame, str):
            # assume it is a frame
            return link_name_or_part_frame.part

        link_name = link_name_or_part_frame
        link = self._part_frame.get_outgoing_link(link_name)
        if link is None:
            raise ValueError("Link named '{}' does not exist on {}".format(link_name, self))

        part_frame = link.target_part_frame
        return part_frame.part


class SimControllerReaderProxy:
    """Provide read-only methods to get simulation-related information"""

    def __init__(self, sim_controller: Decl.SimController):
        self._sim_controller = sim_controller

    def delay(self, days: float = 0, hours: float = 0, minutes: float = 0, seconds: float = 0):
        """
        Returns the current sim time plus the specified time
        :return: The time in days
        """
        return (self._sim_controller.get_sim_time_days()
                + days
                + hours * HOURS_TO_DAYS
                + minutes * MINUTES_TO_DAYS
                + seconds * SECONDS_TO_DAYS)

    def get_runtime_animation_setting(self):
        """Get current animation setting"""
        return self._sim_controller.setting.anim_while_run_dyn

    def get_realtime_mode(self):
        """Get whether in realtime mode (True)"""
        return self._sim_controller.is_realtime()

    def get_realtime_scale(self):
        """Get scale for realtime mode."""
        return self._sim_controller.get_realtime_scale()

    def get_replication_id(self):
        """Get the replication ID, for current variant. Smallest allowed is 1."""
        return self._sim_controller.get_replic_id()

    def get_variant_id(self):
        """Get the variant ID. Smallest allowed is 1."""
        return self._sim_controller.get_variant_id()

    def get_replication_folder(self):
        """Get the folder used by this simulation replication"""
        return self._sim_controller.get_replic_folder()

    def get_sim_time_days(self) -> float:
        """Get the current simulation time, in days."""
        return self._sim_controller.get_sim_time_days()

    def get_num_events(self) -> int:
        """Get the number of events currently on the queue"""
        return self._sim_controller.get_num_events()

    runtime_animation = property(get_runtime_animation_setting)
    realtime_mode = property(get_realtime_mode)
    realtime_scale = property(get_realtime_scale)

    replication_id = property(get_replication_id)
    variant_id = property(get_variant_id)
    replication_folder = property(get_replication_folder)

    sim_time_days = property(get_sim_time_days)
    num_events = property(get_num_events)


class SimControllerProxy(SimControllerReaderProxy):
    """Provide additional methods (beyond getters of base class) to change sim state"""

    def __init__(self, sim_controller: Decl.SimController):
        super().__init__(sim_controller)

    def signal(self, iexec_part: IExecutablePart, args: Tuple = None, time: float = None, priority: float = 0):
        """Create a signal on the event queue, for given executable part, args, time, and priority"""
        self._sim_controller.add_event(iexec_part, args, time, priority)

    def pause(self):
        """Pause sim; works even if already paused"""
        if self._sim_controller.state_name != 'paused':
            self._sim_controller.sim_pause()

    def resume(self):
        """Resume sim; works even if already running"""
        if self._sim_controller.state_name != 'running':
            self._sim_controller.sim_resume()

    def set_runtime_animation_setting(self, enabled: bool = True):
        """Change runtime animation setting"""
        self._sim_controller.set_anim_while_run_dyn_setting(enabled)

    def set_realtime_mode(self, enabled: bool = True):
        """Change realtime mode"""
        self._sim_controller.set_realtime_mode(enabled)

    def set_realtime_scale(self, scale: float):
        """Change the scale for realtime mode. Not used when not realtime. """
        self._sim_controller.set_realtime_scale(scale)

    runtime_animation = property(SimControllerReaderProxy.get_runtime_animation_setting, set_runtime_animation_setting)
    realtime_mode = property(SimControllerReaderProxy.get_realtime_mode, set_realtime_mode)
    realtime_scale = property(SimControllerReaderProxy.get_realtime_scale, set_realtime_scale)
