# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: SQL Part Execution

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import re
from inspect import Parameter, Signature
import math

# [2. third-party]

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ...core.typing import AnnotationDeclarations

from ..ori import OriSqlPartKeys as SqlKeys
from ..ori import OriTablePartKeys as TblKeys
from ..sqlite_dataset import SqlDataSet
from ..embedded_db import EmbeddedDbSqlNotStatementError

from .iexecutable_part import IExecutablePart
from .scripting_utils import LinkedPartsScriptingProxy, get_func_proxy_from_str, get_signature_from_str
from .py_script_exec import LINKS_SCRIPT_OBJ_NAME

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SqlPartExec'
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    TablePart = 'TablePart'
    PartLink = 'PartLink'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class SqlPartExec(IExecutablePart):
    """
    Analyze and execute the SQL statement(s).
    """

    def __init__(self):
        super().__init__()

        self._parts_proxy = LinkedPartsScriptingProxy(self)

        self._script_namespace = {
            'self': self,
            'math': math,
            LINKS_SCRIPT_OBJ_NAME: self._parts_proxy
        }

        self._param_namespace = {}  # used to track parameters in the script namespace during editing

        # The table name is for the table created dynamically for the calling SQL Part instances to consume.
        # We drop it if it exists before re-creating it.
        # There could be some subtle issues here. If a SQL Part has multiple calling parents, dropping and
        # creating it can happen multiple times. We may have to accept the fact now for this build.
        #
        # We may introduce a new flag to identify the tables that are very static, for example, the names
        # of the planets of the solar system. In that case, we don't have to drop it and re-create it every time when
        # we access it.
        self._table_name = ""

    # @override(BasePart)
    def on_outgoing_link_removed(self, link: Decl.PartLink):
        link_name = link.name
        self._script_namespace[LINKS_SCRIPT_OBJ_NAME].invalidate_link_cache(link_name)

    # @override(BasePart)
    def on_outgoing_link_renamed(self, old_name: str, _: str):
        self._script_namespace[LINKS_SCRIPT_OBJ_NAME].invalidate_link_cache(old_name)

    # @override(BasePart)
    def on_link_target_part_changed(self, link: Decl.PartLink):
        self._script_namespace[LINKS_SCRIPT_OBJ_NAME].invalidate_target_cache(link)

    def get_py_namespace(self) -> Dict[str, Any]:
        return self._script_namespace

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SEARCHING_API_EXTEND = ()
    META_AUTO_SCRIPTING_API_EXTEND = ()

    def _is_select_stmt(self, stmt: str) -> bool:
        """
        To determine whether a SQL statement is a SELECT statement or not.

        Design decisions:

        There are no easy and efficient ways to do that. We use fixed format to identify a SELECT
        statement. All the SELECT statements must start with "SELECT ", case-insensitive.

        :param stmt: A SQL statement.
        :returns: True if it is a SELECT statement.
        """
        return stmt.strip().lower()[:7] == "select "

    @override(IExecutablePart)
    def _exec(self, _debug_mode: bool, _as_signal: bool, *args, **kwargs) -> SqlDataSet:
        """
        Analyze and execute the SQL statement(s).

        The return data type depends on what and how the script is executed. If the script is a single SELECT statement,
        the return type will be SqlDataSet. Otherwise, a cursor, which is the return value of executescript.

        :param _debug_mode: Not used for this part.
        :param _as_signal: Not used for this part. There is no difference between signal and call
        :param args: the python positional arguments.
        :param kwargs: the python named arguments.
        :returns: A SqlDataSet object or a cursor.
        """
        if self._param_validator is None:
            self._param_validator = get_func_proxy_from_str(self._param_str)
        self._param_validator(*args, **kwargs)

        bound_arguments = self.signature.bind(*args, **kwargs).arguments
        for bound_argument in bound_arguments:
            self._script_namespace[bound_argument] = bound_arguments[bound_argument]
            self._param_namespace[bound_argument] = bound_arguments[bound_argument]

        for param in self.signature.parameters.values():
            if param.name not in bound_arguments and param.default is not Parameter.empty:
                self._script_namespace[param.name] = param.default
                self._param_namespace[param.name] = param.default

        return self.__run_sql_script(self._sql_script_str, self._script_namespace)

    def get_preview_data(self, params: str, script: str, *args, **kwargs) -> SqlDataSet:
        """
        Get a preview of the result after executing the SQL script.
        WARNING: If the script contains UPDATE, INSERT, or DELETE, calling this method could result in modification of
        linked table part(s).
        :param params: Parameter names.
        :param script: The SQL script.
        :param args: The python positional arguments.
        :param kwargs: The python named arguments.
        :return: A SqlDataSet object or a cursor.
        """
        preview_limit = 100  # limit number of previewed records
        param_validator = get_func_proxy_from_str(params)
        param_validator(*args, **kwargs)
        signature = get_signature_from_str(params)
        bound_arguments = signature.bind(*args, **kwargs).arguments
        script_namespace = self.__get_script_namespace_no_params()  # remove any previous params

        for bound_argument in bound_arguments:
            script_namespace[bound_argument] = bound_arguments[bound_argument]

        for param in signature.parameters.values():
            if param.name not in bound_arguments and param.default is not Parameter.empty:
                script_namespace[param.name] = param.default

        return self.__run_sql_script(script, script_namespace, limit=preview_limit)

    def __run_sql_script(self, script: str, script_namespace: Dict[str, Any], limit: int = None) -> SqlDataSet:
        """
        Run the SQL script.
        :param script: The script to execute.
        :param script_namespace: The script namespace defines the parameters and their corresponding values.
        :param limit: Optional limit on the number of records returned.
        :returns: A SqlDataSet object or a cursor.
        """
        table_part_target = None

        def eval_expr(m):
            nonlocal table_part_target
            hit = m.group(0)
            # The [2:-2] is used to strip the {{}} off.
            # For example, the hit would look like this: {{link.table}} or {{passed_country}}
            # We are interested in the string enclosed by the {{}}. So, the_expr would be link.table or passed_country.
            the_expr = hit[2:-2]
            obj = eval(the_expr, script_namespace)
            if isinstance(obj, SqlDataSet):
                return obj.get_table_name()
            if hasattr(obj, 'PART_TYPE_NAME'):
                if obj.PART_TYPE_NAME == SqlKeys.PART_TYPE_SQL:
                    ret = obj()
                    return ret.get_table_name()
                elif obj.PART_TYPE_NAME == TblKeys.PART_TYPE_TABLE:
                    table_part_target = obj
                    return obj.database_table_name
                else:
                    raise TypeError('The part type is not supported: ' + obj.PART_TYPE_NAME)
            else:
                if isinstance(obj, int):
                    return str(obj)
                else:
                    return "'" + str(obj) + "'"

        sql_evaluated = re.sub(r'{{.+?}}', eval_expr, script)
        if limit:
            sql_evaluated += " LIMIT {}".format(limit)

        db_singleton = self.shared_scenario_state.embedded_db

        # Design decisions:
        # The implementation strategy is to use try except twice to execute the sql as a standalone sql statement first,
        # then as a script. The first try is to test if the script can be executed as a standalone statement. If not,
        # the second try will assume multiple sql statements exist in the script.
        #
        # A simple parsing "_is_select_stmt" is used to determine if a standalone SELECT statement exists.
        # If the determination turns out to be false positive, we run it as multiple statements.
        try:
            if self._is_select_stmt(sql_evaluated):
                table_name = '{}_{}'.format(self.PART_TYPE_NAME, self.SESSION_ID)
                db_singleton.drop_table(table_name)
                create_stmt = 'CREATE TABLE %s as %s' % (table_name, sql_evaluated)
                db_singleton.execute(create_stmt)
                result = db_singleton.select_as_sql_data_set(table_name, sql_evaluated)
                if result:
                    num_fields = len(result[0])
                    log.info("SQL part '{}' SELECT result: {} records, {} fields", self, len(result), num_fields)
                else:
                    log.info("SQL part '{}' SELECT yielded no result", self)
                return result

            else:
                # not a SELECT statement, so nothing to fetch, and assume table modified:
                db_singleton.execute(sql_evaluated)

        except EmbeddedDbSqlNotStatementError as exc:
            # the SQL code is a script, not a statement, so nothing to fetch, and assume table modified:
            db_singleton.execute_script(sql_evaluated)

        self.__table_changed(table_part_target)

        return None

    def __table_changed(self, table_part: Decl.TablePart):
        """
        Signals the table part if this sql part changes it.
        :param table_part: The table part that is updated.
        """
        if self._anim_mode_shared:
            if table_part is not None:
                table_part.signals.sig_full_table_changed.emit()

    def __get_script_namespace_no_params(self) -> Dict[str, Any]:
        """
        Get a new script namespace without any previously set script parameters and corresponding values.
        :return: A new script namespace with no parameters or values.
        """
        new_script_namespace = self._script_namespace.copy()
        for param in self._param_namespace.keys():
            if param in new_script_namespace:
                del new_script_namespace[param]

        return new_script_namespace
