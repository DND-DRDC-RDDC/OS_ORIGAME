# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This package provides functionality related to scenario part definitions.

Version History: See SVN log.
"""

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5788$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- PUBLIC API ---------------------------------------------------------------------------------
# import *public* symbols (classes/functions/constants) from contained modules:

from .actor_part import ActorPart, Rotation3D, RestoreIfxPortInfo, ActorIfxPortSide, RestoreReparentInfo, parts_to_str
from .actor_part import get_parents_map, check_same_parent
from .base_part import BasePart, PastablePartOri, InScenarioState, RestorePartInfo
from .button_part import ButtonPart, ButtonStateEnum, ButtonActionEnum, ButtonTriggerStyleEnum
from .clock_part import ClockPart
from .common import Position, Vector, Size
from .data_part import DataPart, DisplayOrderEnum
from .datetime_part import DateTimePart
from .function_part import FunctionPart, RunRolesEnum
from .hub_part import HubPart
from .info_part import InfoPart
from .file_part import FilePart, is_path_below_directory, check_valid_file_path
from .library_part import LibraryPart
from .multiplier_part import MultiplierPart, InvalidLinkingError
from .node_part import NodePart
from .part_frame import PartFrame, FrameStyleEnum, DetailLevelEnum, FrameStyleEnum, RestoreIfxLevelInfo
from .part_link import LinkIfxLevelsTooLowError, UnresolvedLinkPathError
from .part_link import MissingLinkEndpointPathError, InvalidPartLinkArgumentsError, InvalidLinkPathSegmentError
from .part_link import PartLink, LinkWaypoint, PARENT_ACTOR_PATH, LINK_PATH_DELIM, LinkSet
from .part_link import RestoreLinkInfo, UnrestorableLinks
from .part_link import LINK_PATTERN, get_patterns_by_link_item, get_link_find_replace_info, get_frame_repr
from .part_link import TypeReferencingParts, TypeRefTraversalHistory, TypeLinkChainNameAndLink, TypeMissingLinkInfo
from .part_types_info import get_pretty_type_name, get_registered_type_names
from .plot_part import PlotPart
from .pulse_part import PulsePart, PulsePartState
from .scenario_object import ScenarioObjectType
from .scripted_scen_modifiers import SimControllerProxy, SimControllerReaderProxy
from .sheet_part import ExcelSheetValueError, ExcelSheetIndexError, ExcelSheetTypeError, ExcelSheetIndexStyleError
from .sheet_part import SheetPart, excel_column_letter, get_col_header, SheetIndexStyleEnum
from .sheet_part import translate_excel_column, translate_excel_range, translate_excel_index, get_excel_sheets
from .sql_part import SqlPart
from .table_part import TablePart, TablePartIndexEmptyError, TablePartSQLiteTableNotFoundError, get_db_tables
from .time_part import TimePart
from .variable_part import VariablePart
