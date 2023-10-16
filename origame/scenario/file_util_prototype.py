# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Class that handles loading of Scenario from an R4 HR TDP prototype.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import pickle
import base64
import re
from collections import OrderedDict
from lib2to3 import refactor
from textwrap import dedent
import sys
import sqlite3 as sqlite
from pathlib import Path

# [2. third-party]
from . import pyor_pickling

# [3. local]
from ..core import override
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from .part_execs import LINKS_SCRIPT_OBJ_NAME
from .file_util_base import ScenarioReaderWriter
from .ori import OriClockPartKeys as ClkKeys, OriScenData, pickle_to_str
from .ori import OriCommonPartKeys as CpKeys
from .ori import OriScenarioKeys as SKeys
from .ori import OriScenarioDefKeys as SdKeys
from .ori import OriPartFrameKeys as PfKeys
from .ori import OriPositionKeys as PosKeys
from .ori import OriSizeKeys as SzKeys
from .ori import OriActorPartKeys as ApKeys
from .ori import OriHubPartKeys as HpKeys
from .ori import OriMultiplierPartKeys as MpKeys
from .ori import OriNodePartKeys as NpKeys
from .ori import OriPlotPartKeys as PpKeys
from .ori import OriRotation3dKeys as R3dKeys
from .ori import OriFunctionPartKeys as FpKeys
from .ori import OriSocketPartKeys as SopKeys
from .ori import OriVariablePartKeys as VpKeys
from .ori import OriInfoPartKeys as InfoKeys
from .ori import OriDataPartKeys as DpKeys
from .ori import OriLibraryPartKeys as LibKeys
from .ori import OriSheetPartKeys as SpKeys
from .ori import OriSqlPartKeys as SqlKeys
from .ori import OriPartLinkKeys as PwKeys
from .ori import OriTablePartKeys as TpKeys
from .ori import OriSchemaEnum

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module
    'ScenarioDatabaseReadError',
    'ScenarioDatabaseInvalidError',
    'PrototypeUnpicklingError',
    'ScenFileUtilPrototype',
]

log = logging.getLogger('system')

# when unpickling, the pickle module will look for classes defined in pyor module; make it use own version,
# created from prototype's pyor.py with only the code relevant to unpickling
sys.modules["pyor"] = pyor_pickling

# Set this to True if need to convert part member names in Function Part scripts from Prototype to Origame method names
REPLACE_PART_MEMBER_NAMES = False


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ScenarioDatabaseReadError(LookupError):
    """
    This class represents a custom error that is raised when a read operation on the prototype scenario
    database fails.
    """
    pass


class ScenarioDatabaseInvalidError(KeyError):
    """
    This class represents a custom error that is raised when a database element contains a parent part ID (parentID)
    that does not exist as an ID in the database.
    """
    pass


class ScenarioDatabaseUnsupportedPartError(Exception):
    """
    This class represents a custom error that is raised when a database element is not (or not yet) supported by
    Origame.
    """
    pass


class PrototypeUnpicklingError(Exception):
    """
    This class represents a custom error that is raised when an unpickling operation fails.
    """
    pass


class ScenFileUtilPrototype(ScenarioReaderWriter):
    """
    This class is used to create an in memory representation of prototype Scenario data
    in the form of a dictionary.  The dictionary can the be passed to the JSON module
    to generate a JSON representation of the Scenario data.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    PartOri = Dict[str, Any]

    SAVABLE = False

    """
    A prototype scenario db file does not contain a record for the root actor. In the db, record ids
    start at 1 and increase in sequence in accordance with part creation order. During prototype to origame
    scenario file conversion, a root actor part is created and added to the Origame scenario and assigned
    the ROOT_ACTOR_ID value.
    """
    ROOT_ACTOR_ID = 0
    NO_PARENT_ID = -1

    root_actor_ori = {
        "id": 0,  # Relevant to prototype only. Preserved herein to help sort out linking links.
        "pid": NO_PARENT_ID,  # Relevant to prototype only. Preserved herein to help sort out linking links.
        CpKeys.REF_KEY: 0,
        CpKeys.TYPE: ApKeys.PART_TYPE_ACTOR,
        CpKeys.PART_FRAME: {
            PfKeys.NAME: "simulation",  # Default for prototype's "simulation" view. Can't be renamed by proto.
            PfKeys.IFX_LEVEL: 0,
            PfKeys.VISIBLE: True,
            PfKeys.FRAME_STYLE: "normal",
            PfKeys.DETAIL_LEVEL: "full",
            PfKeys.POSITION: {  # Default this to position of prototype's "simulation" view proxy icon.
                PosKeys.X: 0,
                PosKeys.Y: 0
            },
            PfKeys.SIZE: {
                SzKeys.WIDTH: 4.85,
                SzKeys.HEIGHT: 1.55,
                SzKeys.SCALE_3D: 1.0
            },
            PfKeys.COMMENT: None,  # Comments can't be saved for proto's simulation view.
            PfKeys.OUTGOING_LINKS: None  # Proto doesn't support outgoing links from Actor Parts.
        },
        CpKeys.CONTENT: {
            ApKeys.GEOM_PATH: None,
            ApKeys.ROTATION_2D: 0.0,
            ApKeys.ROTATION_3D: {
                R3dKeys.ROLL: 0.0,
                R3dKeys.PITCH: 0.0,
                R3dKeys.YAW: 0.0
            },
            ApKeys.PROXY_POS: {
                PosKeys.X: 0,
                PosKeys.Y: 0
            },
            ApKeys.CHILDREN: []
        }
    }

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        """
        The _ori_scenario is an in-memory representation of the Scenario as a whole -
        Master Clock, Event Queue, and Scenario Definition.
        Since the Origame prototype did not save Master Clock and Event Queue information
        within the SQLite database file, these are represented as emtpy dictionaries in
        key="master_clock" and key="sim_event_queue".
        """
        super().__init__()

        self._ori_scenario = OriScenData({}, schema_version=OriSchemaEnum.prototype)
        # The following dictionary maps prototype part type names to their Origame equivalent. The keys represent
        # The prototype name.
        self._parts_renamed = {"code": "function", "python": "variable", "comment": "info"}
        # The following list represents the part types currently supported by Origame. It will grow as Origame is
        # advanced.
        self._currently_supported_parts = [
            ApKeys.PART_TYPE_ACTOR,
            ClkKeys.PART_TYPE_CLOCK,
            DpKeys.PART_TYPE_DATA,
            FpKeys.PART_TYPE_FUNCTION,
            HpKeys.PART_TYPE_HUB,
            MpKeys.PART_TYPE_MULTIPLIER,
            NpKeys.PART_TYPE_NODE,
            PpKeys.PART_TYPE_PLOT,
            LibKeys.PART_TYPE_LIBRARY,
            SpKeys.PART_TYPE_SHEET,
            SopKeys.PART_TYPE_SOCKET,
            SqlKeys.PART_TYPE_SQL,
            TpKeys.PART_TYPE_TABLE,
            VpKeys.PART_TYPE_VARIABLE,
            InfoKeys.PART_TYPE_INFO
        ]

        avail_fixes = refactor.get_fixers_from_package('lib2to3.fixes')
        self.py_script_converter = refactor.RefactoringTool(avail_fixes)

    def read_all_parts(self, path):
        """
        Get a list of all the parts in the prototype scenario. Useful for debugging a prototype scenario when
        parentage may be an issue.
        """
        connection = sqlite.connect(path)
        cursor = connection.cursor()
        cursor.execute("SELECT copy FROM Save")

        parts = []
        for row in cursor:
            record = eval(row[0])
            part_type = self._parts_renamed[record["type"]] if record["type"] in self._parts_renamed else record["type"]

            part = {
                'id': record["ID"],
                'pid': record["parentID"],
                CpKeys.TYPE: part_type,

                CpKeys.PART_FRAME: {
                    PfKeys.NAME: record["name"],
                },

                CpKeys.CONTENT: {},
            }

            parts.append(part)

        return parts

    def get_ori_scenario(self) -> OriScenData:
        """
        Gets the dictionary object that 'represents' the scenario in json format.
        The item with key="master_clock" is data about the Master Clock.
        The item with key="event_queue" is data about the Event Queue.
        The item with key="scenario_def" is data about the Scenario Definition.
        Since the prototype Scenario does not have a MasterClock and EventQueue,
        key="master_clock" and key="sim_event_queue" are empty dictionaries.
        """
        return self._ori_scenario

    def sql_from_prototype_to_ori(self, sql_script_in_prototype: str, param_names_in_prototype: str) -> str:
        """
        Convert the SQL statements from the prototype format to the Origame format.

        :param sql_script_in_prototype: the string with the $-prefixed variables
        :param param_names_in_prototype: the comma delimited string
        :returns: the string with the link. prefixed variables enclosed with {{}}
        """

        list_expr = []

        # Use multi-pass approach to parse the $ sign prefixed expressions and the parameter name list.

        def pass_1(dollar_prefixed):
            hit = dollar_prefixed.group(0)
            list_expr.append(LINKS_SCRIPT_OBJ_NAME + "." + hit[1:])
            return "{" + str(len(list_expr) - 1) + "}"

        def pass_2(dollar_prefixed):
            hit = dollar_prefixed.group(0)
            list_expr.append(LINKS_SCRIPT_OBJ_NAME + "." + hit[1:-1])
            return "{" + str(len(list_expr) - 1) + "} "

        def pass_3(dollar_prefixed):
            hit = dollar_prefixed.group(0)
            list_expr.append(LINKS_SCRIPT_OBJ_NAME + "." + hit[1:])
            return "{" + str(len(list_expr) - 1) + "}"

        def pass_final(param):
            hit = param.group(0)
            list_expr.append(hit[1:])
            return hit[0] + "{" + str(len(list_expr) - 1) + "}"

        # Harvest the $ sign prefixed expressions with parameters
        sql_script_1 = re.sub(r'\$[a-zA-Z_]+[a-zA-Z_0-9]*(\s*\(.*?\))', pass_1, sql_script_in_prototype)

        # Harvest the $ sign prefixed expressions without parameters. Not the end of the line
        sql_script_2 = re.sub(r'\$[a-zA-Z_]+[a-zA-Z_0-9\.]*? ', pass_2, sql_script_1)

        # Harvest the $ sign prefixed expressions without parameters. The end of the line
        sql_script_3 = re.sub(r'\$[a-zA-Z_]+[a-zA-Z_0-9\.]*\w', pass_3, sql_script_2)

        # Form a re to hit the parameters.
        p_name_list = param_names_in_prototype.split(',')
        p_name_list.sort(key=len, reverse=True)
        p_name_expr = r""
        for x in p_name_list:
            stripped = x.strip()
            if stripped:
                if p_name_expr:
                    p_name_expr += "|"
                p_name_expr += "\W" + stripped

        if p_name_expr:
            sql_script_final = re.sub(p_name_expr, pass_final, sql_script_3)
        else:
            sql_script_final = sql_script_3

        # Harvest the parameter expressions
        sql_script_converted = sql_script_final.format(*("{{" + x + "}}" for x in list_expr))

        return sql_script_converted

    def func_from_prototype_to_ori(self, py_script: str) -> str:
        """
        Convert the SQL statements from the prototype format to the Origame format.

        :param py_script: the string with the $-prefixed variables
        :returns: the string with the link. prefixed variables enclosed with {{}}
        """
        py_script = dedent(py_script)

        # Regexp for python object names: starts with letter or underscore, followed by 0 or more letters,
        # underscore, and digits in any order:
        RE_PY_OBJ_NAME = '[a-zA-Z_][a-zA-Z_0-9]*'

        # now map member names of frames and parts from proto to Origame

        if REPLACE_PART_MEMBER_NAMES:
            def replace_member_name(match):
                obj = match.group(1)
                member_name = match.group(2)
                # note: if member is not in the map, then return it's lower-case form
                return obj + member_map_proto_ori.get(member_name, member_name.lower())

            member_map_proto_ori = PART_FRAME_MEMBER_MAP_PROTO_ORI
            re_frame_member_name = re.compile(r'(\$\${0}\.)({0})'.format(RE_PY_OBJ_NAME))
            py_script = re_frame_member_name.sub(replace_member_name, py_script)

            member_map_proto_ori = PART_MEMBER_MAP_PROTO_ORI
            re_part_member_name = re.compile(r'(\${0}\.)({0})'.format(RE_PY_OBJ_NAME))
            py_script = re_part_member_name.sub(replace_member_name, py_script)

        # replace Python portions of SQL statements
        def replace_sql_python(match) -> str:
            # first find the parameters to the SQL:
            obj_name = match.group(1)
            sql_start_pos = match.regs[1][0]
            re_quotes = r'(?:"|\')'
            obj_params = r'\${0}.set_params\({1}(.*){1}\)'.format(obj_name, re_quotes)
            params_found = re.findall(obj_params, py_script[:sql_start_pos])
            params = '' if params_found == [] else params_found[-1]

            # now convert using same alg used for SQL parts:
            new_sql = self.sql_from_prototype_to_ori(match.group(2), params)

            return '${}.set_sql_script({})'.format(obj_name, new_sql)

        re_sql_part_script = re.compile(r'\$({})\.set_query\((.*)\)'.format(RE_PY_OBJ_NAME))
        py_script = re_sql_part_script.sub(replace_sql_python, py_script)
        re_sql_part_script = re.compile(r'\$({})\.edit_query\((.*)\)'.format(RE_PY_OBJ_NAME))
        py_script = re_sql_part_script.sub(replace_sql_python, py_script)

        # first convert the $ and $$ to "link." and "link._app_specific_link_name_" resp.

        def replace_1_dollar(dollar_prefixed) -> str:
            link_name = dollar_prefixed.group(1)
            return LINKS_SCRIPT_OBJ_NAME + '.' + link_name

        def replace_2_dollars(dollar_prefixed) -> str:
            link_name = dollar_prefixed.group(1)
            return LINKS_SCRIPT_OBJ_NAME + '._' + link_name + '_'

        re_double_dollar = r'\$\$({})'.format(RE_PY_OBJ_NAME)
        py_script = re.sub(re_double_dollar, replace_2_dollars, py_script)

        re_one_dollar = r'\$({})'.format(RE_PY_OBJ_NAME)
        py_script = re.sub(re_one_dollar, replace_1_dollar, py_script)

        # now convert it through 2to3.py refactorer:

        if not py_script.endswith('\n'):
            # AST will fail if no linefeed after last statement
            py_script += '\n'
        ast = self.py_script_converter.refactor_string(py_script, '<script>')
        return str(ast)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    ori_scenario = property(get_ori_scenario)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(ScenarioReaderWriter)
    def _load_from_file(self, pathname: Path) -> OriScenData:
        """
        This function loads a prototype scenario defined in an SQLite database at the specified pathname
        and maps the information into the raw Python dictionary structure required by base class method.

        :raises PrototypeUnpicklingError: Prototype data could not be unpickled.
        :raises ScenarioDatabaseReadError: Unable to read an opened database.
        """

        # all_parts is used to hold all of the parts within the scenario with no regards
        # to parent-child relationships.  The sole purpose is to hold the ori data in the
        # form of a part. Once all_parts has been filled, it will be used to generate the
        # outgoing link paths.  The first item in all_parts is simply the root actor with id=0
        # and pid=NO_PARENT_ID.
        # Note: The prototype does not save a record in its .db to represent the root actor, so
        # one is created here with ID 0.
        all_parts = {
            0: self.root_actor_ori
        }

        TEMP_OUTLINK_PROPERTIES = "temp_outlink_props"

        # flattened_actor_child_hierarchy is a dictionary that holds parent child relationships of the parts.
        # Each key represents an ID of an Actor and the value is a list of its children (as a dictionary).
        flattened_actor_child_hierarchy = dict()
        flattened_actor_child_hierarchy[0] = []

        connection = sqlite.connect(str(pathname))
        cursor = connection.cursor()
        cursor.execute("SELECT copy FROM Save")

        for row in cursor:
            record = eval(row[0])
            part_type = self._parts_renamed[record["type"]] if record["type"] in self._parts_renamed else record["type"]

            # Only load part types currently supported by Origame. This check can be eliminated once Origame is fully
            # implemented.
            if part_type not in self._currently_supported_parts:
                log.critical("Prototype scenario contains unsupported part type: {}", part_type)
                raise ScenarioDatabaseUnsupportedPartError(
                    "Prototype scenario contains unsupported part type: '{}'.".format(part_type))

            part = dict()
            corrupt_part = False  # sometimes prototype file contains parts that can't be loaded (zombie etc)
            part[CpKeys.PART_FRAME] = {}
            part[CpKeys.CONTENT] = {}

            part_frame = part[CpKeys.PART_FRAME]

            part["id"] = record["ID"]
            part["pid"] = record["parentID"]
            part[CpKeys.TYPE] = part_type
            part[CpKeys.REF_KEY] = record["ID"]
            part_frame[PfKeys.NAME] = record["name"]
            part_frame[PfKeys.VISIBLE] = record["visible"]
            part_frame[PfKeys.FRAME_STYLE] = "bold" if record.get("bold", False) else "normal"

            # We could have done str(DetailLevelEnum.minimal) and str(DetailLevelEnum.full) here. But that would
            # force us to import the part frame. This situation applies to a few other cases in this class.
            #
            # Since this class is used to deal with the legacy (prototype) data, we avoid importing too many Origame
            # objects. But changes of the DetailLevelEnum will lead to the changes in the following line.
            part_frame[PfKeys.DETAIL_LEVEL] = "minimal" if record["collapsed"] else "full"

            part_frame[PfKeys.POSITION] = {}
            part_frame[PfKeys.POSITION][PosKeys.X] = record["posX"]
            # Swapping Y with Z to accomodate Prototye-to-Origame conversion
            part_frame[PfKeys.POSITION][PosKeys.Y] = record["posZ"]
            part_frame[PfKeys.SIZE] = {}
            part_frame[PfKeys.SIZE][SzKeys.WIDTH] = record["width"]
            part_frame[PfKeys.SIZE][SzKeys.HEIGHT] = record["height"]
            part_frame[PfKeys.SIZE][SzKeys.SCALE_3D] = 0.0
            part_frame[PfKeys.COMMENT] = record["comment"]

            # Put the 'links' (links) as-is from the Prototype database into the
            # part["part_frame"]["outgoing_links"] attribute.  As-is, the attribute has the
            # format:  'links': [(u'd1', 7), (u'd2', 9] in the database.  We're
            # storing this attribute in the part as-is (temporarily) because the link could be pointing to
            # an id that has not been created yet in the current loop that we are processing.
            part_frame[PfKeys.OUTGOING_LINKS] = record["links"]
            # Unpickle the 'linkProps' (link properties) into a Prototype data structure and store as-is
            # until the link data is finalized (later on in this function).
            # Prototype's pickled data references proto's pyor module. Origame stubs one to provide what is needed.
            # Note: Prototype only saves 'linkProps' for links given settings other than the defaults.

            if "linkProps" in record:
                try:
                    link_props = pickle.loads(str.encode(record["linkProps"]), fix_imports=True)
                except Exception as exc:
                    err_msg = "Error unpickling linkProps for record ID:{}, record name:{}. Error: {}"
                    raise PrototypeUnpicklingError(err_msg.format(record["ID"], record["name"], exc))
            else:
                link_props = pyor_pickling.link_props_manager()
            part_frame[TEMP_OUTLINK_PROPERTIES] = link_props.Settings  # temporary storage

            part_content = part[CpKeys.CONTENT]
            part_id = part["id"]
            parent_part_id = part["pid"]

            if part[CpKeys.TYPE] == ApKeys.PART_TYPE_ACTOR:
                part_content[ApKeys.CHILDREN] = []
                part_content[ApKeys.GEOM_PATH] = ""
                part_content[ApKeys.ROTATION_2D] = 0.0
                part_content[ApKeys.ROTATION_3D] = {}
                part_content[ApKeys.ROTATION_3D][R3dKeys.ROLL] = 0.0
                part_content[ApKeys.ROTATION_3D][R3dKeys.PITCH] = 0.0
                part_content[ApKeys.ROTATION_3D][R3dKeys.YAW] = 0.0
                part_content[ApKeys.PROXY_POS] = {}
                part_content[ApKeys.PROXY_POS][PosKeys.X] = record.get("parPosX", 0)
                part_content[ApKeys.PROXY_POS][PosKeys.Y] = record.get("parPosY", 0)

            elif part[CpKeys.TYPE] == ClkKeys.PART_TYPE_CLOCK:
                part_content[ClkKeys.TICKS] = record['time']
                part_content[ClkKeys.PERIOD_DAYS] = 1.0 / (record['speed'])
                part_content[ClkKeys.DATE_TIME] = {}
                part_content[ClkKeys.DATE_TIME][ClkKeys.YEAR] = record['year']
                part_content[ClkKeys.DATE_TIME][ClkKeys.MONTH] = record['month']
                part_content[ClkKeys.DATE_TIME][ClkKeys.DAY] = record['day']
                part_content[ClkKeys.DATE_TIME][ClkKeys.HOUR] = record['hour']
                part_content[ClkKeys.DATE_TIME][ClkKeys.MINUTE] = record['minute']
                part_content[ClkKeys.DATE_TIME][ClkKeys.SECOND] = record['second']

            elif part[CpKeys.TYPE] == DpKeys.PART_TYPE_DATA:
                legacy_dict_obj = pickle.loads(str.encode(record["dict"]))
                legacy_order_obj = pickle.loads(str.encode(record["order"]))
                # The legacy uses a dict and a list to record the order of the dict. Since the Python 3.x offers
                # the OrderedDict, we construct it here.
                new_dict_obj = OrderedDict()
                for ordered_key in legacy_order_obj:
                    new_dict_obj[ordered_key] = legacy_dict_obj[ordered_key]
                new_pickled_obj = pickle_to_str(pickle.dumps(new_dict_obj))
                part_content[DpKeys.DICT] = new_pickled_obj

            elif part[CpKeys.TYPE] == FpKeys.PART_TYPE_FUNCTION:
                part_content[FpKeys.RUN_ROLES] = []
                if record.get("start", False):
                    part_content[FpKeys.RUN_ROLES].append(FpKeys.STARTUP)
                if record.get("reset", False):
                    part_content[FpKeys.RUN_ROLES].append(FpKeys.RESET)
                part_content[FpKeys.PARAMETERS] = record["params"]
                converted = self.func_from_prototype_to_ori(record["code"])
                part_content[FpKeys.SCRIPT] = converted.split('\n')

            elif part[CpKeys.TYPE] == InfoKeys.PART_TYPE_INFO:
                part_content[InfoKeys.TEXT] = record["text"]

            elif part[CpKeys.TYPE] == PpKeys.PART_TYPE_PLOT:
                script = """\
                    def configure():
                        setup_axes()
                    def plot():
                        pass
                    """
                part_content[PpKeys.SCRIPT] = script.split('\n')

            elif part[CpKeys.TYPE] == LibKeys.PART_TYPE_LIBRARY:
                converted = self.func_from_prototype_to_ori(record["code"])
                part_content[LibKeys.SCRIPT] = converted.split('\n')

            elif part[CpKeys.TYPE] == SpKeys.PART_TYPE_SHEET:
                try:
                    part_content[SpKeys.DATA] = pickle.loads(str.encode(record["data"]), fix_imports=True)
                    part_content[SpKeys.COL_WIDTHS] = pickle.loads(str.encode(record["colwidth"]), fix_imports=True)
                    part_content[SpKeys.NAMED_COLS] = pickle.loads(str.encode(record["namedcols"]),
                                                                   fix_imports=True)
                except Exception as e:
                    raise PrototypeUnpicklingError(
                        "Error unpickling sheet part data:{}, record name:{}, Error: {}".format(
                            record["ID"], record["name"], str(e)))
                part_content[SpKeys.NUM_COLS] = record['numcols']
                part_content[SpKeys.NUM_ROWS] = record['numrows']
                part_content[SpKeys.INDEX_STYLE] = record['indexstyle']

            elif part[CpKeys.TYPE] == SopKeys.PART_TYPE_SOCKET:
                side = record['side']
                part_content[SopKeys.SIDE] = '{}_side'.format(record['side']) if side != 'none' else None
                part_content[SopKeys.ORIENTATION] = 'vertical' if record['vertical'] else 'horizontal'
                # nodes referenced will be added as they are traversed in the NODE type
                part_content[SopKeys.NODE_REFS] = []

            elif part[CpKeys.TYPE] == NpKeys.PART_TYPE_NODE:
                # only nodes that are in socket need further processing: in prototype, their parent is socket, whereas
                # in Origame, their parent is same as that of socket; so if Node's pid is NOT id of an Actor part,
                # it belongs to a socket.
                if flattened_actor_child_hierarchy.get(part['pid']) is None:
                    socket_part = all_parts[part['pid']]
                    assert socket_part[CpKeys.TYPE] == SopKeys.PART_TYPE_SOCKET
                    new_parent_id = socket_part['pid']
                    part['pid'] = new_parent_id
                    parent_part_id = new_parent_id
                    siblings = flattened_actor_child_hierarchy.get(new_parent_id)
                    # add this part's children-list index into its parent socket "node refs" list
                    child_index = len(siblings)
                    socket_part[CpKeys.CONTENT][SopKeys.NODE_REFS].append(child_index)

            elif part[CpKeys.TYPE] == SqlKeys.PART_TYPE_SQL:
                part_content[SqlKeys.PARAMETERS] = record["params"]
                converted = self.sql_from_prototype_to_ori(record["query"], record["params"])
                part_content[SqlKeys.SQL_SCRIPT] = converted.split('\n')

            elif part[CpKeys.TYPE] == TpKeys.PART_TYPE_TABLE:
                column_names = [col[0] for col in record['tableFields']]

                part_content[TpKeys.COLUMN_NAMES] = column_names
                part_content[TpKeys.COLUMN_TYPES] = [col[1] for col in record['tableFields']]
                part_content[TpKeys.SCHEMA] = record.get('tableSchema')
                db_table_name = record['tableName']

                part_content[TpKeys.INDICES] = None
                if 'tableIndexes' in record:
                    indexed_columns = pickle.loads(str.encode(record["tableIndexes"]))
                    if indexed_columns:
                        index_dict = {"indices": indexed_columns}
                        part_content[TpKeys.INDICES] = index_dict

                        if not column_names:
                            log.warning(
                                "Indices in table '{}' (id {}), but no column names! Corrupt .DB? Dropping part.",
                                record["name"], record["ID"])
                            corrupt_part = True

                data_rows = []
                data_cursor = connection.cursor()
                data_cursor.execute("PRAGMA table_info({})".format(db_table_name))

                if column_names:
                    # Table Part has one or more columns, check if there are data as well, if so populate Table Parts
                    # TpKeys.DATA with the correct list of data.
                    if len(data_cursor.fetchall()) > 0:
                        data_cursor.execute("SELECT * FROM {}".format(db_table_name))
                        for data_row in data_cursor:
                            data_rows.append(data_row)
                        part_content[TpKeys.DATA] = data_rows
                    else:
                        # Nothing to do as Table Part contains one or more columns but no data.  The instance
                        # of the Table Part will create the columns, types and, indices based on _set_from_ori_impl
                        pass
                else:
                    if len(data_cursor.fetchall()) > 0:
                        # Table Part has no columns but there was data, should not be possible.
                        log.warning("Data in table '{}' (id {}), but no column names! Corrupt .DB? Dropping part.",
                                    record["name"], record["ID"])
                        corrupt_part = True
                    else:
                        # Table Part contains no columns and no data, create Origame's equivalent of empty table.
                        part_content[TpKeys.DATA] = None
                        part_content[TpKeys.COLUMN_NAMES] = ['Col 0']
                        part_content[TpKeys.COLUMN_TYPES] = ['']

            elif part[CpKeys.TYPE] == VpKeys.PART_TYPE_VARIABLE:
                # Python 3.x and 2.x use different approaches to pickle objects.
                # The following technique is used to satisfy both the pickling and the design patterns by presenting
                # the new_variable_pickled_obj as if it came from the Origame.
                legacy_variable_obj = pickle.loads(str.encode(record["save"]))
                new_variable_pickled_obj = pickle_to_str(pickle.dumps(legacy_variable_obj))
                part_content[VpKeys.VALUE_OBJ] = new_variable_pickled_obj
                # Since we are loading the legacy object, which is either a script assigned pickled Python object or
                # the pickled return value of an eval of the expression input by the user in the Variable Part
                # editor, repr seems to be the proper thing to do. The user may not be able to save the repr value
                # back to the scenario, but the repr may help some simple cases such as primitives or complex
                # numbers.
                part_content[VpKeys.EDITABLE_STR] = repr(legacy_variable_obj)

            # DONE mapping of this part, now added to flattened part hierarchy:
            if not corrupt_part:
                log.debug('Found part {}, child of {}', part_id, parent_part_id)

                if record["type"] == ApKeys.PART_TYPE_ACTOR:
                    log.debug('New parent actor: {} (whose parent is {})', part_id, parent_part_id)
                    flattened_actor_child_hierarchy[part_id] = []

                # Associate child part to its parent Actor.
                if flattened_actor_child_hierarchy.get(parent_part_id) is not None:
                    flattened_actor_child_hierarchy[parent_part_id].append(part)
                all_parts[part_id] = part

            # Done this part, continue loop
            pass  # so Code -> Reformat leaves previous comment alone

        # All parts loaded. Sanity check the part relationships to ensure all referenced part IDs exist.
        self.__sanity_check_part_ids(all_parts)

        for actor_id, children in flattened_actor_child_hierarchy.items():
            for child in children:
                if child[CpKeys.TYPE] == ApKeys.PART_TYPE_ACTOR:
                    child_id = child["id"]
                    children = flattened_actor_child_hierarchy[child_id]
                    child[CpKeys.CONTENT][ApKeys.CHILDREN] = children

        # Now that we have all of the parts in all_parts, we use this for loop to
        # inspect the outgoing links and set them to the 'type' of outgoing link.
        for part_id, part in all_parts.items():
            if int(part_id) == self.ROOT_ACTOR_ID:
                continue

            part_frame = part[CpKeys.PART_FRAME]
            if not part_frame[PfKeys.OUTGOING_LINKS]:
                # links record is empty list, but we want empty dict as final data struct:
                part_frame[PfKeys.OUTGOING_LINKS] = {}
                continue

            if TEMP_OUTLINK_PROPERTIES not in part_frame:
                part_frame[PfKeys.OUTGOING_LINKS] = {}
                continue

            proper_links = {}
            raw_outlink_props = part_frame[TEMP_OUTLINK_PROPERTIES]
            assert len(part_frame[PfKeys.OUTGOING_LINKS]) != 0
            links = part_frame[PfKeys.OUTGOING_LINKS]
            for link in links:
                link_name = link[0]
                end_point_id = link[1]
                target_path = end_point_id
                link_props = None
                if link_name in raw_outlink_props:
                    link_props = raw_outlink_props[link_name]

                # Initialize link attributes. Booleans are defaulted here, but set properly after.
                if target_path is None:
                    log.warning("Target part not found for Link '{}' originating at part '{}', dropping it",
                                link_name, part_frame[PfKeys.NAME])

                else:
                    proper_links[link_name] = {
                        PwKeys.DECLUTTER: False,
                        PwKeys.TARGET_PATH: target_path,
                        PwKeys.VISIBLE: True,
                        PwKeys.BOLD: False
                    }
                    if link_props is not None:
                        link = proper_links[link_name]
                        link[PwKeys.DECLUTTER] = link_props.Short
                        if link_props.Hidden is True:
                            link[PwKeys.VISIBLE] = False
                        link[PwKeys.BOLD] = link_props.Bold

            part_frame[PfKeys.OUTGOING_LINKS] = proper_links
            # Clean up the temporary 'raw' link properties imported from proto.
            del part_frame[TEMP_OUTLINK_PROPERTIES]

        # Now that we have all of the parts in all_parts and all of the outgoing_links have been
        # properly deconstructed, we need to update the flattened_actor_hierarchy.
        for actor_id, children in flattened_actor_child_hierarchy.items():
            for child in children:
                if len(child[CpKeys.PART_FRAME][PfKeys.OUTGOING_LINKS]) != 0:
                    child[CpKeys.PART_FRAME][PfKeys.OUTGOING_LINKS] = \
                        all_parts[child["id"]][CpKeys.PART_FRAME][PfKeys.OUTGOING_LINKS]

        # Set up the Root Actor data structure that will hold the prototype scenario. Note: The prototype
        # scenario does not support the concept of a "root actor" as Origame does, so one is created below and
        # populated with known values or reasonable defaults for the root actor instance itself.

        # Load values from the Global table. This currently only stores the proxy icon position for the prototype's
        # "simulation" view's proxy icon.
        root_actor_proxy_x = 0.0
        root_actor_proxy_y = 0.0
        try:
            cursor.execute('SELECT Key, Value FROM Globals')
        except sqlite.OperationalError:
            log.error("Unable to load Global table from prototype scenario database ({})", pathname)
            raise ScenarioDatabaseReadError(
                "Unable to load Global table from prototype scenario database ({})".format(pathname))
        else:
            for key, value in cursor:
                if key == 'simPos':
                    # Swapping Y with Z to accomodate Prototye-to-Origame conversion
                    root_actor_proxy_x, _, root_actor_proxy_y = eval(value)
        finally:
            connection.close()

        self.root_actor_ori[CpKeys.PART_FRAME][PfKeys.POSITION] = {
            # Default this to position of prototype's "simulation" view proxy icon.
            PosKeys.X: root_actor_proxy_x,
            PosKeys.Y: root_actor_proxy_y
        }
        self.root_actor_ori[CpKeys.CONTENT][ApKeys.PROXY_POS] = {
            PosKeys.X: root_actor_proxy_x,
            PosKeys.Y: root_actor_proxy_y
        }
        self.root_actor_ori[CpKeys.CONTENT][ApKeys.CHILDREN] = flattened_actor_child_hierarchy[0]

        scenario_def = {
            SdKeys.NAME: "prototype scenario",  # arbitrary
            SdKeys.ROOT_ACTOR: self.root_actor_ori
        }

        self._ori_scenario[SKeys.SCENARIO_DEF] = scenario_def
        self._ori_scenario[SKeys.SCHEMA_VERSION] = OriSchemaEnum.prototype.value
        self._ori_scenario[SKeys.EVENT_QUEUE] = {}
        self._ori_scenario[SKeys.SIM_CONFIG] = {}

        return self._ori_scenario

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __sanity_check_part_ids(self, all_parts: Dict[int, Dict[int, str]]):
        """
        This function iterates over the all_parts dictionary and checks that all parent IDs referenced by
        parts exist in the scenario. If all is okay, the function returns quietly; otherwise an exception is
        raised.
        :param all_parts: A flat dictionary of dictionaries keyed by part ID. The sub-dictionaries each contain
            a part description.
        :raises ScenarioDatabaseInvalidError: Raised if parts in the scenario hold references to part IDs of
            deleted parts. This ocassionally happens as a result of a bug in the prototype that allows parts to
            maintain references to the part IDs of deleted parts.
        """
        for _, part in all_parts.items():
            if part['pid'] is not self.NO_PARENT_ID and all_parts.get(part['pid']) is None:
                raise ScenarioDatabaseInvalidError(
                    "Invalid scenario file. Part (type: {}, name: {}, ID: {}) references non-existant "
                    "parent part ID ({}).".format(
                        part[CpKeys.TYPE], part[CpKeys.PART_FRAME][PfKeys.NAME], part['id'], part['pid']))

    def __get_child_index_str(self, parent_id: int, child_id: int, actor_child_hier: Dict[int, List[PartOri]]) -> str:
        """
        This method returns the index (not id) of a child part within its parent Actor part.
        This method is used to obtain the index position of a part within a dictionary of key-List pairs.

        :param parent_id: Parent (actor) part id from which the child index is to be retrieved.
        :param child_id: The id of the part for which to find the index.
        :param actor_child_hier: The hierarchy that contains a dictionary of parent-child
            relationships between parts. Each key represents an ID of an Actor and the value is a list of its
            children (as dictionaries).
        :return: The index (as a string) associated with the input child_id.
        """
        for index, child in enumerate(actor_child_hier.get(parent_id, [])):
            if child["id"] == child_id:
                return str(index)


"""
Mapping of part frame member names to Origame part frame member names
"""
PART_FRAME_MEMBER_MAP_PROTO_ORI = dict(
    PosX='pos_x',
    PosY='pos_y',

    # all others just auto-lowercase
)

"""
Mapping of part member names to Origame part member names (other than frame members)
"""
PART_MEMBER_MAP_PROTO_ORI = dict(
    # function part
    get_code='get_script',
    set_code='set_script',

    # function and sql
    get_params='get_parameters',
    set_params='set_parameters',

    # sql
    set_query='set_sql_script',
    edit_query='set_sql_script',
    edit_params='set_parameters',
    Query='sql_script',

    # sheet
    NumCols='num_cols',
    NumRows='num_rows',

    # clock
    Speed='tick_period_days',
    Period='tick_period_days',
    Time='tick_value',
    get_speed='get_tick_period_days',
    set_speed='set_tick_period_days',
    get_time='get_tick_value',
    set_time='set_tick_value',
    # all others just auto-lowercase

    # actor
    IconFilename='geometry_path',

    # plot and information
    setup_axes='setup_axes_proto'
    # all just auto-lowercase
)
