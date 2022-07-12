# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: All scenario part editors

Version History: See SVN log.
"""

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5788$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- PUBLIC API ---------------------------------------------------------------------------------
# import *public* symbols (classes/functions/constants) from contained modules:

from .data_part_editor import DataPartEditorPanel
from .variable_part_editor import VariablePartEditorPanel
from .clock_part_editor import ClockPartEditorPanel
from .datetime_part_editor import DateTimePartEditorPanel
from .button_part_editor import ButtonPartEditorPanel
from .function_part_editor import FunctionPartEditorPanel
from .sql_part_editor import SqlPartEditorPanel
from .library_part_editor import LibraryPartEditorPanel
from .plot_part_editor import PlotPartEditorPanel, ExportImageDialog, ExportDataDialog
from .pulse_part_editor import PulsePartEditorPanel
from .info_part_editor import InfoPartEditorPanel
from .actor_part_editor import ActorPartEditorPanel
from .table_part_editor import TablePartEditorPanel, ImportDatabaseDialog, ExportDatabaseDialog, on_database_error
from .time_part_editor import TimePartEditorPanel
from .sheet_part_editor import SheetPartEditorPanel, ImportExcelDialog, ExportExcelDialog, on_excel_error
from .img_editor import ImgEditorWidget
from .scenario_part_editor import ScenarioPartEditorDlg, SortFilterProxyModelByColumns
from .file_part_editor import FilePartEditorPanel

from .part_editors_registry import get_part_editor_class
