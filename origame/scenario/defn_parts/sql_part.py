# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the SqlPart class and supporting functionality or the Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriSqlPartKeys as SqlKeys
from ..part_execs import SqlPartExec, IExecutablePart
from ..proto_compat_warn import prototype_compat_method_alias, prototype_compat_property_alias
from ..alerts import IScenAlertSource

from .common import Position
from .part_types_info import register_new_part_type
from .actor_part import ActorPart
from .base_part import BasePart, PartLink
from .part_link import TypeReferencingParts, TypeMissingLinkInfo
from .scripted_part import IScriptedPart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SqlPart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------


class SqlPart(BasePart, SqlPartExec, IScriptedPart):
    """
    Represents the data from the embedded database or the operation on it.
    """

    class Signals(BridgeEmitter):
        sig_sql_script_changed = BridgeSignal(str)
        sig_multi_changed = BridgeSignal(bool)

    CAN_BE_LINK_SOURCE = True
    DEFAULT_VISUAL_SIZE = dict(width=10.0, height=5.1)
    PART_TYPE_NAME = "sql"
    DESCRIPTION = """\
        Use this part to create SQL queries.

        Link this part to table parts to execute queries on the tables.  Refer to the tables using dot notation
        within the SQL, e.g. 'select * from {{link.table}}'.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this instance of the SQL Part.
        :param position: A position to be assigned to the newly instantiated default SqlPart. This argument
            is only required when the ori_def default (None) is used.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        SqlPartExec.__init__(self)

        self.signals = SqlPart.Signals()

        self._sql_script_str = ""

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

    def get_sql_script(self) -> str:
        """
        Get the SQL statements in one string.

        :returns: The SQL statements in one string.
        """
        return self._sql_script_str

    def set_sql_script(self, sql_str: str):
        """
        Set the SQL statements in one string.

        :param sql_str: It represents the SQL script.
        """
        self._sql_script_str = sql_str
        if self._anim_mode_shared:
            self.signals.sig_sql_script_changed.emit(sql_str)

    @override(BasePart)
    def on_removing_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        BasePart.on_removing_from_scenario(self, scen_data, restorable=restorable)
        IExecutablePart.on_removed_from_scenario(self, scen_data, restorable=restorable)

    @override(BasePart)
    def on_restored_to_scenario(self, scen_data: Dict[BasePart, Any]):
        BasePart.on_restored_to_scenario(self, scen_data)
        IExecutablePart.on_restored_to_scenario(self, scen_data)

    @override(BasePart)
    def on_outgoing_link_removed(self, link: PartLink):
        SqlPartExec.on_outgoing_link_removed(self, link)

    @override(BasePart)
    def on_outgoing_link_renamed(self, old_name: str, new_name: str):
        SqlPartExec.on_outgoing_link_renamed(self, old_name, new_name)

    @override(BasePart)
    def on_link_target_part_changed(self, link: PartLink):
        SqlPartExec.on_link_target_part_changed(self, link)

    @override(IScriptedPart)
    def get_canonical_script(self) -> str:
        return self._sql_script_str

    @override(IScriptedPart)
    def set_canonical_script(self, val: str):
        # Needs to signal, so avoid self._sql_script_str = val
        self.sql_script = val

    # prototype compatibility adjustments:
    get_params = prototype_compat_method_alias(IExecutablePart.get_parameters, 'get_params')
    set_params = prototype_compat_method_alias(IExecutablePart.set_parameters, 'set_params')
    set_query = prototype_compat_method_alias(set_sql_script, 'set_query')
    edit_query = prototype_compat_method_alias(set_sql_script, 'edit_query')
    edit_params = prototype_compat_method_alias(IExecutablePart.set_parameters, 'edit_params')

    # --------------------------- instance PUBLIC properties ----------------------------

    sql_script = property(get_sql_script, set_sql_script)

    Query = prototype_compat_property_alias(sql_script, 'Query')

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (sql_script,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        sql_script, get_sql_script, set_sql_script,
    )

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

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        # Per BasePart._set_from_ori_impl() docstring, set via property.

        self.parameters = part_content.get(SqlKeys.PARAMETERS, self._param_str) or ''
        sql_statement_pieces = part_content.get(SqlKeys.SQL_SCRIPT)
        if sql_statement_pieces:
            self.sql_script = '\n'.join(sql_statement_pieces)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)
        sql_ori_def = {
            SqlKeys.PARAMETERS: self._param_str,
            SqlKeys.SQL_SCRIPT: self._sql_script_str.split('\n')
        }

        ori_def[CpKeys.CONTENT].update(sql_ori_def)
        return ori_def

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        snapshot.update({
            SqlKeys.PARAMETERS: self._param_str,
            SqlKeys.SQL_SCRIPT: self._sql_script_str
        })


# Add this part to the global part type/class lookup dictionary
register_new_part_type(SqlPart, SqlKeys.PART_TYPE_SQL)
