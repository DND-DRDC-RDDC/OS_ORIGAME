# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the SheetPart class and the functionality that supports the part as
a building block for the Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import copy
import string
from enum import IntEnum, unique
from hashlib import md5
import pickle
import re
import json
from pathlib import Path
from datetime import datetime

# [2. third-party]
from xlrd import open_workbook, xldate, XLRDError, XL_CELL_DATE
from xlwt import Workbook
from xlutils.copy import copy as xl_copy
from copy import deepcopy

# [3. local]
from ...core import override, override_optional
from ...core import BridgeEmitter, BridgeSignal
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...core.utils import get_verified_repr

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj, OriSchemaEnum, SaveErrorLocationEnum
from ..ori import get_pickled_str, pickle_from_str, pickle_to_str, check_needs_pickling
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriSheetPartKeys as SpKeys
from ..proto_compat_warn import prototype_compat_property_alias

from .base_part import BasePart, check_diff_val
from .common import Position
from .part_types_info import register_new_part_type
from .actor_part import ActorPart
from .table_part import TablePart, TablePartSQLiteTableNotFoundError
from .common import ExcelReadError, ExcelWriteError

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SheetPart',
    'SheetIndexStyleEnum',
    'ExcelSheetIndexStyleError',
    'ExcelSheetIndexError',
    'ExcelSheetValueError',
    'ExcelSheetTypeError',
    'excel_column_letter',
    'translate_excel_column',
    'translate_excel_range',
    'translate_excel_index',
    'get_col_header',
    'get_excel_sheets',
]

log = logging.getLogger('system')

InCellRange = Either[str, int, Tuple[int, int], Tuple[int, slice], Tuple[slice, int], Tuple[slice, slice]]
RowOrColSubset = Either[int, Tuple[int, int], None]

COL_PATTERN = r'^[A-Z]{1,3}_[A-Z]{1,3}$'  # pattern describing a column cell range A_A, A_B, AA_ABC
ROW_PATTERN = r'^[0-9]+$'  # pattern describing a row cell range
CELL_PATTERN = r'^[A-Z]{1,3}[0-9]+$'  # pattern describing a single cell cell range
CELL_RNG_PATTERN = r'^[A-Z]{1,3}[0-9]+[:_][A-Z]{1,3}[0-9]+$'  # multi-dimension cell range A1:B2 or A1_B2
CELL_RNG_PATTERN_ATTR = r'^[A-Z]{1,3}[0-9]+[:_][A-Z]{1,3}[0-9]+$'  # same as above but only A1_B2

DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


class Decl(AnnotationDeclarations):
    SheetIndexStyleEnum = 'SheetIndexStyleEnum'
    ExcelSheet = 'ExcelSheet'
    SheetPart = 'SheetPart'


# -- Function definitions -----------------------------------------------------------------------

def excel_column_letter(col_idx: int) -> str:
    """
    This function translates a column index into an Excel-styled equivalent column heading. Excel column
    headings are of the form: "A", "B", "C", ..., "AA", "AB", ..., "ZY", "ZZ", "AAA", "AAB" ...
    The Excel column letter increments based on the 26 character English alphabet, so calculations below
    are all based on 26 unit 'chunks' and 'chunk' remainders. The string module is used for its
    ascii_uppercase() function which provides a readily available uppercase string of the alphabet.
    The algorithm below builds multi-character Excel column headings in reverse order and then reverses
    the heading as a final step before returning it.
    :param col_idx: The index of the column for which an Excel heading is required.
    :return: The Excel-equivalent column heading corresponding to the input column index.
    """
    alphabet_size = len(string.ascii_uppercase)  # The size of the English alphabet.

    xls_idx = string.ascii_uppercase[col_idx % alphabet_size]
    col_idx -= col_idx % alphabet_size

    while col_idx > 0:
        col_idx = int(col_idx / alphabet_size)

        xls_idx += string.ascii_uppercase[(col_idx % alphabet_size) - 1]
        if col_idx % alphabet_size != 0:
            col_idx -= (col_idx % alphabet_size)
        else:
            col_idx = 0

    return xls_idx[::-1]


def translate_excel_column(xls_idx: str) -> int:
    """
    This function translates an Excel-styled alpha column heading into an equivalent column index. Excel column
    headings are of the form: "A", "B", "C", ..., "AA", "AB", ..., "ZY", "ZZ", "AAA", "AAB" ...
    The column index returned is zero-based. The algorithm below starts at the last character of the Excel-styled
    column header and iterates through it in reverse order, calculating the column heading value based on 26
    character "chunks" from which the alpha column headings are created.
    :param xls_idx: The Excel-styled alpha column heading for which a numerical column index equivalent is required.
    :return: The zero-based column index corresponding to the input Excel-styled alpha column heading.
    """

    alphabet_size = len(string.ascii_uppercase)  # The size of the English alphabet.

    xls_idx = xls_idx.upper()

    # go through xlsColumn in reverse order
    row = range(len(xls_idx), 0, -1)

    col_num = 0
    order = 0

    for i in row:
        a = xls_idx[i - 1]
        col_num += (string.ascii_uppercase.find(a) + 1) * alphabet_size ** order
        order += 1

    return col_num - 1


def translate_excel_range(xls_range: str) -> Tuple[int, int, int, int]:
    """
    This function translates the input Excel-styled table array range into a starting
    row/column index and an ending row/column index.
    :param xls_range: A string representing an excel range, of the format: "A", "A1", "3", "A1:D4".
    :return: A four integer tuple containing: (start row index, start column index, end row index, end column index)
    """
    # remove spaces
    xls_range = xls_range.replace(' ', '')

    if not (re.match(COL_PATTERN, xls_range) or
                re.match(ROW_PATTERN, xls_range) or
                re.match(CELL_PATTERN, xls_range) or
                re.match(CELL_RNG_PATTERN, xls_range)):
        raise ValueError("Unrecognized sheet range: {}".format(xls_range))
        return

    step = 1

    for i in range(len(xls_range)):
        if step == 1:
            if xls_range[i] in string.digits:
                c1 = i - 1
                col1 = translate_excel_column(xls_range[:i])
                step = 2
        elif step == 2:
            if xls_range[i] == ':' or xls_range[i] == '_':
                r1 = i - 1
                row1 = int(xls_range[c1 + 1:i]) - 1
                step = 3
        elif step == 3:
            if xls_range[i] in string.digits:
                col2 = translate_excel_column(xls_range[r1 + 2:i])
                row2 = int(xls_range[i:]) - 1
                break

    return row1, col1, row2, col2


def translate_excel_index(xls_index: str) -> Tuple[int, int]:
    """
    This function converts an Excel-styled index, like "A1" and returns
    the corresponding col/row index.
    :param xls_index: A string representing an Excel-styled index, like "A1".
    :return: A tuple containing the corresponding numeric row and col index: (row index, column index).
    """
    xls_index = xls_index.replace(' ', '')

    for i in range(len(xls_index)):
        if xls_index[i] in string.digits:
            col = translate_excel_column(xls_index[:i])
            row = int(xls_index[i:]) - 1
            break

    return row, col


def resolve_cell_range(cell_range: InCellRange, num_rows: int, num_cols: int) -> Tuple[Either[int, slice],
                                                                                       Either[int, slice]]:
    """
    This function resolves the input 'cell_range' into more usable row and col indices descriptions. The resolved
    row/col indices are returned as a tuple, each expressed as either an integer or a slice where an integer
    describes a specific row or column and a slice describes a set or subset of rows or columns respectively.

    :param cell_range: The cell range of the ExcelSheet data to be resolved. The cell_range can
        be a string, integer, or tuple.  The acceptable formats for the cell_range parameter and the associated
        returns are summarized as follows:
            Excel styled cell_range value examples - type: string
                "A" - Indicates column A. Returned as: (slice(start row index, end row index+1), column index)
                "5" - Indicates row number (row index + 1). Returned as:
                    (row index, slice(start col index, end col index+1)), or
                    col index if the row only contained a single column.
                "A1" - Indicates column "A", row: 1. Returned as: (row index, col index)
                "A1:D4" or "A1_D4" - Indicates a 2-D range of cells. Returned as:
                    (slice(start row index, end row index+1), slice(start col index, end col index+1))
            Non-Excel styled cell_range value examples - type: int, tuple, slice
                3 - Interpreted as a row index. Returned as:
                    (row index, col index), or
                    (row index, slice(start col index, end col index+1)
                (2, 3) - A tuple is interpreted as a row/col index pair. Returned as: (row index, col index)
                (2, slice(2, 4)) - A tuple containing an int/slice pair interpreted as row index and col subset.
                    Returned as: (row index, slice(start col index, end col index+1)
                (slice(1, 5), 0) - A tuple containing a slice/int pair interpreted as row subset and col index.
                    Returned as: (slice(start row index, end row index+1), col index)
                (slice(2, 4), slice(3, 6)) - A tuple containing a slice/slice pair interpreted as row subset/col
                subset. Returned as: (slice(start row index, end row index+1),
                slice(start col index, end col index+1))
    :param num_rows: The number of rows in the sheet.
    :param num_cols: The number of columns in the sheet.
    :return: A tuple describing the row(s) and cell(s) corresponding to the input cell_range.
    :raises TypeError: Raised if an input tuple index contains neither an int nor a slice.
    :raises ValueError: Raised if the 'cell_range' value is determined to be invalid.
    """

    if isinstance(cell_range, str):

        cell_range = cell_range.replace(' ', '')

        if re.match(CELL_RNG_PATTERN, cell_range):
            row1, col1, row2, col2 = translate_excel_range(cell_range)
            row = slice(row1, row2 + 1)
            col = slice(col1, col2 + 1)

        elif re.match(COL_PATTERN, cell_range):
            col_range = cell_range.split(sep='_')
            if col_range[0] == col_range[1]:
                # single column: e.g. A_A
                col = translate_excel_column(col_range[0])
            else:
                # range of columns: e.g. A_Z
                col1 = translate_excel_column(col_range[0])
                col2 = translate_excel_column(col_range[1])
                col = slice(col1, col2 + 1)
                if col2 < col1:
                    raise ValueError("The second column must be greater than the first column. Column {} is less than"
                                     " column {}.".format(col_range[1], col_range[0]))

            if num_rows == 1:
                row = 0
            else:
                row = slice(0, num_rows)

        elif re.match(ROW_PATTERN, cell_range):
            row = int(cell_range) - 1
            if num_cols == 1:
                col = 0
            else:
                col = slice(0, num_cols)

        elif re.match(CELL_PATTERN, cell_range):
            row, col = translate_excel_index(cell_range)

        else:
            raise ValueError("Unrecognized sheet range: {}".format(cell_range))

    else:
        # if cell_range is a single integer
        if isinstance(cell_range, int):
            # if Sheet is one dimensional (index into chosen column or row)
            if num_rows == 1:
                row = 0
                col = cell_range
            elif num_cols == 1:
                row = cell_range
                col = 0
            # else, it's a 2D Sheet, return whole row
            else:
                row = cell_range
                col = slice(0, num_cols)

        # if it's a tuple, extract row and col
        elif isinstance(cell_range, tuple):
            row, col = cell_range
            if type(row) not in (int, slice):
                raise TypeError("Invalid row tuple format for ExcelSheet indexing. "
                                "Expecting one of the following formats: (int, int), (int, slice), or (slice, int)")
            if type(col) not in (int, slice):
                raise TypeError("Invalid column tuple format for ExcelSheet indexing. "
                                "Expecting one of the following formats: (int, int), (int, slice), or (slice, int)")
        else:
            raise ValueError("Unrecognized sheet range: {}".format(cell_range))

    return row, col


def get_excel_sheets(xls_file: str) -> List[str]:
    """
    Returns a list of all sheets in the given Excel file. An empty list is returned if the file does not exist.
    :param xls_file: The Excel file.
    :return: A list of sheet names.
    """
    if not Path(xls_file).exists():
        return []

    try:
        log.info("Getting sheet names from Excel file: {}.", xls_file)
        wb = open_workbook(xls_file)
        return wb.sheet_names()

    except Exception as exc:
        log.error("Read_from_excel() error. The following error occurred: {}.", str(exc))
        raise ExcelReadError("Read_from_excel() error. The following error occurred: {}.".format(exc))


def read_from_excel(xls_file: str, xls_sheet: str, xls_range: str, accept_empty_cells: bool = False) -> [[object]]:
    """
    This file opens the specified Excel file and worksheet, and reads the specified range of data from the
    worksheet. The read data is returned in a 2D array.  The current instance is fully reset to accommodate the loaded
    data.
    :param xls_file: Excel file path.
    :param xls_sheet: The name of a worksheet within the specified Excel file.
    :param xls_range: An Excel-styled range specifying the data to be read from the opened worksheet.
    :param accept_empty_cells: True if empty data cells are allowed: False if empty cells are to default to 0.
    :raises ExcelReadError: Raised when an error occurs locating or reading the excel file or file sheet.
    """

    # retrieve the data and store in a 2d list
    try:
        log.info("Reading from Excel file: {}, sheet: {}, range: {}", xls_file, xls_sheet, xls_range)
        wb = open_workbook(xls_file)
        sh = wb.sheet_by_name(xls_sheet)

        # convert range to rows and cols
        # if range is None, get all items in the sheet
        if xls_range == '':
            col1 = 0
            row1 = 0
            col2 = sh.ncols - 1
            row2 = sh.nrows - 1
        else:
            row1, col1, row2, col2 = translate_excel_range(xls_range)

    except FileNotFoundError:
        log.error("read_from_excel() error. File not found: {}", xls_file)
        raise ExcelReadError("read_from_excel() error. File not found: {}".format(xls_file))
    except XLRDError:
        log.error("read_from_excel() error. Invalid sheet name. File: {}, Sheet: {}", xls_file, xls_sheet)
        raise ExcelReadError("read_from_excel() error. Invalid sheet name. "
                             "File: {}, Sheet: {}".format(xls_file, xls_sheet))
    except Exception as e:
        log.error("read_from_excel() error. Invalid sheet range. File: {}, Sheet: {}, Range: {}. "
                  "More info: {}",
                  xls_file, xls_sheet, xls_range, str(e))
        raise ExcelReadError("read_from_excel() error. Invalid sheet range. File: {}, Sheet: {}, Range: {}. "
                             "More info: {}".format(xls_file, xls_sheet, xls_range, e))

    # validate that the sheet contains data in the requested range before commencing.
    if row1 > sh.nrows or row2 > sh.nrows or col1 > sh.ncols or col2 > sh.ncols:
        log.error("read_from_excel() error. Specified cell range is beyond the limits of the Excel "
                  "sheet data. File: {}, Sheet: {}, Range: {}", xls_file, xls_sheet, xls_range)
        raise ExcelReadError("read_from_excel() error. Specified cell range is beyond "
                             "the limits of the Excel sheet data. File: {}, "
                             "Sheet: {}, Range: {}".format(xls_file, xls_sheet, xls_range))

    # setup the grid and store the excel data
    num_rows = row2 - row1 + 1
    num_cols = col2 - col1 + 1

    data = [([SheetPart.DEFAULT_CELL_VAL] * num_cols) for _ in range(num_rows)]

    # read the excel data into local array
    for row in range(num_rows):
        for col in range(num_cols):
            try:
                if sh.cell_value(row1 + row, col1 + col) != '' or accept_empty_cells:
                    value = sh.cell_value(row1 + row, col1 + col)
                    if sh.cell_type(row1 + row, col1 + col) == XL_CELL_DATE:
                        data[row][col] = xldate.xldate_as_datetime(value, wb.datemode).strftime(DATE_FORMAT)
                    else:
                        data[row][col] = value

            except IndexError:
                data[row][col] = ''
                log.error("read_from_excel() error. Invalid data indices: row: {}, col: {})", row, col)
                raise ExcelReadError("read_from_excel() error. Invalid data indices: row: {}, "
                                     "col: {})".format(row, col))

    return data


def write_to_excel(data: List[List[Any]], xls_file: str, xls_sheet: str, xls_range: str = ''):
    """
    This function creates an Excel file at the specified path, adds a worksheet with the specified name to the
    file, then writes the provided data to the new worksheet and saves the file.
    :param data: The 2D array of data to be written.
    :param xls_file: The path of the Excel file to be created.
    :param xls_sheet: The name of the worksheet to be added to the file.
    :param xls_range: An Excel-styled range specifying the data to be read from the opened worksheet. Empty means full
    sheet.
    :raises ExcelWriteError: Raised when an error occurs opening or writing to the excel file or worksheet.
    """
    is_new_sheet = True
    sheet_idx = None
    num_rows = len(data)
    num_cols = len(data[0])

    try:
        log.info("Writing data to Excel file: {}, sheet: {}", xls_file, xls_sheet)

        if Path(xls_file).exists():
            # open existing workbook
            wb_orig = open_workbook(xls_file)

            # check if the sheet already exists.. if not, a new sheet will be added
            if xls_sheet in wb_orig.sheet_names():
                # find the sheet index to insert data into
                for i, name in enumerate(wb_orig.sheet_names()):
                    if name == xls_sheet:
                        sheet_idx = i
                        break

                assert sheet_idx is not None
                is_new_sheet = False

            wb = xl_copy(wb_orig)  # copy to writable version for editing/saving

        else:
            # create new workbook
            wb = Workbook()

        if is_new_sheet:
            # add new sheet
            sheet = wb.add_sheet(xls_sheet)
        else:
            assert sheet_idx is not None
            sheet = wb.get_sheet(sheet_idx)  # get sheet for writing

        # resolve data range
        if xls_range:
            row_range, col_range = resolve_cell_range(xls_range, num_rows, num_cols)

            if isinstance(row_range, int):
                insert_at_row = row_range
            else:  # slice
                insert_at_row = row_range.start
                stop_at_row = row_range.stop
                trim_row_idx = stop_at_row - insert_at_row
                data = data[:trim_row_idx]  # only export rows within range specified
                num_rows = len(data)

            if isinstance(col_range, int):
                insert_at_col = col_range
            else:  # slice
                insert_at_col = col_range.start
                stop_at_col = col_range.stop
                trim_col_idx = stop_at_col - insert_at_col
                xdata = [row[:trim_col_idx] for row in data]  # only export cols within range specified
                data = xdata
                num_cols = len(data[0])
        else:
            insert_at_row, insert_at_col = (0, 0)

        # insert the exported data
        assert sheet is not None
        for row in range(num_rows):
            for col in range(num_cols):
                sheet.write(insert_at_row + row, insert_at_col + col, data[row][col])

        wb.save(xls_file)
    except Exception as exc:
        log.error("write_to_excel() error. File: {}, Sheet: {}. Error: {}", xls_file, xls_sheet, exc)
        raise ExcelWriteError(
            "write_to_excel() error. File: {}, Sheet: {}. Error: {}".format(xls_file, xls_sheet, exc))


def get_col_header(col_idx: int, named_cols: Dict[str, Tuple[int, int]], index_style: Decl.SheetIndexStyleEnum) -> str:
    """
    This function returns a formatted header string for the specified column index and named-column dict look-up.
    :param col_idx: The index of the column for which a formatted header is to be returned.
    :param named_cols: A dictionary of custom-named columns associated with column index keys.
    :param index_style: The index style of the sheet columns.
    :return: If the column has a custom header, and the current index style is 'excel', the column's
        equivalent Excel header is appended with the custom header in the format column_letter-column_name-. If
        there is no custom name associated with the column, and the current index style is 'excel', the column's
        Excel header name is returned.  If the current index style is 'array', the input index is returned as a
        string. The number of characters returned in the string is limited by the column width associated with
        the column.
    """
    if index_style == SheetIndexStyleEnum.excel:
        if col_idx in named_cols.values():
            for name, index in named_cols.items():
                if col_idx == index:
                    val = excel_column_letter(col_idx) + '-' + name + '-'
                    break
        else:
            val = excel_column_letter(col_idx=col_idx)
    else:
        val = str(col_idx)

    return val[:]


# -- Class Definitions --------------------------------------------------------------------------


@unique
class SheetIndexStyleEnum(IntEnum):
    """
    This class represents the index styles supported for Sheet columns.
    """
    excel = 0
    array = 1


@unique
class ColShiftDirectionEnum(IntEnum):
    """
    This class represents the possible sheet column shift directions when another column is added or deleted
    from the Sheet Part.
    """
    right = 0
    left = 1


@unique
class SheetSetItemIndexType(IntEnum):
    """
    This class represents the row_col index type combinations possible when __setitem__ is invoked.
    """
    int_int, int_slice, slice_int, slice_slice = range(4)


@unique
class SheetFillType(IntEnum):
    """
    This class represents sheet fill types possible when 'fill' is invoked.
    """
    full, cell, row, col, sheet = range(5)


class ExcelSheetIndexStyleError(KeyError):
    """
    Custom error class used for raising Sheet part exceptions. This exception represents an error condition where
    an invalid Index Style was specified for the Sheet Part.
    """
    pass


class ExcelSheetIndexError(IndexError):
    """
    Custom error class used for raising Sheet part exceptions. This exception represents an error condition where
    a row or column value is out of the range of the current Sheet part.
    """
    pass


class ExcelSheetValueError(ValueError):
    """
    Custom error class used for raising Sheet part exceptions. This exception represents an error condition where
    a sheet value, such a number of rows or columns is invalid for the current Sheet part.
    """
    pass


class ExcelSheetTypeError(Exception):
    """
    Custom error class used for raising Sheet part exceptions. This exception represents an error condition where
    a sheet value, such a number of rows or columns is invalid for the current Sheet part.
    """
    pass


"""
Signature of callback to be given to the SheetPart's fill() function for operation on the SheetPart's cells.
:param arg 1: The index of the the row to be operated on by the callback.
:param arg 2: The index of the the column to be operated on by the callback.
:return: the object to insert into the specified row/col cell of the sheet part.
"""
FillCallable = Callable[[int, int], Any]


class ExcelSheet:
    """
    This class defines the functionality required to support an Excel sheet.

    The Excel sheet is a container for a two-dimensional array of data. The bulk of the part's
    functionality is devoted to accessing and manipulating the array of data and associated column headings.
    The Excel sheet supports the concept of column indices expressed in either Excel formatted
    (as alpha characters) or in array format (as integers).

    The sheet data can be saved to, or loaded from, an Excel spreadsheet.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    SheetSetItemIndex = Tuple[SheetSetItemIndexType, Either[int, slice], Either[int, slice]]

    DEFAULT_NUM_ROWS = 8
    DEFAULT_NUM_COLS = 8
    DEFAULT_COL_WIDTH = 8
    DEFAULT_CELL_VAL = 0
    MIN_NUM_ROWS = 0
    MIN_NUM_COLS = 0
    NUM_ROWS_ADD_DEL = 5
    NUM_COLS_ADD_DEL = 5
    REPR_LABEL = "com"

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self,
                 data: Either[List[List[Any]], Decl.ExcelSheet] = None,
                 row_idx: Either[int, slice] = None,
                 col_idx: Either[int, slice] = None):
        """
        :param data: Initial data for the current instance. When data is of type 'list within a list', it is
            directly assigned to this instance and the row_idx and col_idx arguments are not relevant.  When data is of
            type ExcelSheet, the data within the ExcelSheet is assigned to this instance based on the 'row_idx' and
            'col_idx' arguments. Additionally, when the 'data' argument is of type ExcelSheet, any relevant
            characteristics associated with the specified 'row_idx' and 'col_idx' (like column headers) are assigned to
            this instance.
        :param row_idx: The row index (indices) from a ExcelSheet type 'data' argument to be copied into this instance.
        :param col_idx: The col index (indices) from a ExcelSheet type 'data' argument to be copied into this instance.
        """
        # A list of lists, the entirety initialized to zero.
        self._sheet_data = [([self.DEFAULT_CELL_VAL] * self.DEFAULT_NUM_COLS) for _ in range(self.DEFAULT_NUM_ROWS)]
        # A list of column widths - integers, representing the number of characters displayable for a column heading.
        self._col_widths = [self.DEFAULT_COL_WIDTH] * self.DEFAULT_NUM_COLS
        self._named_cols = {}  # A dictionary to hold custom names for columns. Keyed by name, Valued is column index.
        self._num_cols = self.DEFAULT_NUM_COLS  # The number of columns in the data sheet
        self._num_rows = self.DEFAULT_NUM_ROWS  # The number of rows in the data sheet
        self._index_style = SheetIndexStyleEnum.excel  # The index style of the data sheet columns.

        if data is not None:
            if isinstance(data, list):
                self._sheet_data = copy.deepcopy(data)
            elif isinstance(data, ExcelSheet):
                if isinstance(row_idx, int) and isinstance(col_idx, int):
                    self.resize(num_rows=1, num_cols=1)
                    self._sheet_data[row_idx][col_idx] = copy.deepcopy(data.sheet_data[row_idx][col_idx])
                elif isinstance(row_idx, int) and isinstance(col_idx, slice):
                    self._sheet_data = copy.deepcopy([data.sheet_data[row_idx][col_idx]])
                elif isinstance(row_idx, slice) and isinstance(col_idx, int):
                    self._sheet_data = copy.deepcopy([[row[col_idx]] for row in data.sheet_data[row_idx]])
                elif type(row_idx is slice and isinstance(col_idx, slice)):
                    self._sheet_data = copy.deepcopy([row[col_idx] for row in data.sheet_data[row_idx]])

                # set column names
                if isinstance(col_idx, slice):
                    new_idx = 0
                    for col_idx in range(data.num_cols)[col_idx]:
                        self.set_col_name(new_idx, data.get_named_col(col_idx))
                        new_idx += 1

            self._num_cols = len(self._sheet_data[0])  # The number of columns in the data sheet
            self._num_rows = len(self._sheet_data)  # The number of rows in the data sheet
            self._col_widths = [self.DEFAULT_COL_WIDTH] * self._num_cols

    def get_sheet_data(self) -> List[List[Any]]:
        """
        This function returns a copy of the 2-D array of sheet part data.
        """
        return [row[:] for row in self._sheet_data]

    def resize(self, num_rows: int = None, num_cols: int = None):
        """
        This function resizes the data sheet to the specified number of rows and columns.
        :param num_rows: The number of rows that are to be in the resized sheet.
        :param num_cols: The number of columns that are to be in the resized sheet.
        """
        if num_rows is not None:
            self.set_rows(num_rows)
        if num_cols is not None:
            self.set_cols(num_cols)

    def get_rows(self) -> int:
        """
        This function returns the number of rows in the Sheet part.
        :return: Number of rows.
        """
        return self._num_rows

    def set_rows(self, num_rows: int = MIN_NUM_ROWS):
        """
        This function adjusts the sheet part to have the specified number of rows.

        If num_rows is less than the current number of rows in the sheet part, the extraneous rows are dropped.
        If num_rows is greater than the current number of rows in the sheet part, additional rows are appended
        to the list of rows, with the cell values set to 0.
        :param num_rows: The number of rows the table will have.
        :raises ExcelSheetValueError - Raised if an invalid number of rows is specified.
        """
        if num_rows < self.MIN_NUM_ROWS:
            raise ExcelSheetValueError(
                "Invalid number of rows ({}) specified. Minimum permitted is ({})".format(num_rows, self.MIN_NUM_ROWS))

        delta = num_rows - self.num_rows

        if delta > 0:
            self.add_rows(num_rows=delta)
        elif delta < 0:
            self.delete_rows(num_rows=delta * -1)

    def get_cols(self) -> int:
        """
        This function returns the number of columns in the Sheet part.
        :return: The number of columns.
        """
        return self._num_cols

    def set_cols(self, num_cols: int = MIN_NUM_COLS):
        """
        This function adjusts the sheet part to have the specified number of columns.

        If num_cols is less than the current number of columns in the sheet part, the extraneous columns are dropped.
        If num_cols is greater than the current number of columns in the sheet part, additional columns are appended
        to each row, with the cell values set to 0. Column widths are also adjusted and set to default values
        accordingly.
        :param num_cols: The number of columns the table will have.
        :raises ValueError - Raised if an invalid number of columns is specified.
        """
        if num_cols < self.MIN_NUM_COLS:
            raise ExcelSheetValueError(
                "Invalid number of columns ({}) specified. Minimum permitted is ({})".format(
                    num_cols, self.MIN_NUM_COLS))

        delta = num_cols - self.num_cols
        if delta > 0:
            self.add_cols(num_cols=delta)
        elif delta < 0:
            self.delete_cols(num_cols=delta * -1)

    def get_cell_data(self, row_idx: int, col_idx: int) -> Any:
        """
        This function returns the item stored in the sheet data cell identified by the specified row, column pair.
        :param row_idx: The cell row index (zero-based).
        :param col_idx: The cell column index (zero-based).
        :return: The item stored in the Sheet part data cell.
        :raises: ExcelSheetIndexError - This exception is raised when the either of the row or col indices
            are out of range of the current Sheet part dimensions.
        """
        self.validate_indices(row_idx, col_idx)
        return self._sheet_data[row_idx][col_idx]

    @override_optional
    def set_cell_data(self, row_idx: int, col_idx: int, item: Any) -> Any:
        """
        This function sets the Sheet part cell corresponding to the input row/col pair to the specified item.
        :param row_idx: The cell row index (zero-based).
        :param col_idx: The cell column index (zero-based).
        :raises: ExcelSheetIndexError - This exception is raised when the either of the row or col indices
            are out of range of the current Sheet part dimensions.
        :returns The original object for comparison to the new.
        """
        self.validate_indices(row_idx, col_idx)

        orig_item = self._sheet_data[row_idx][col_idx]

        if item != orig_item:
            if item == '':
                self._sheet_data[row_idx][col_idx] = 0
            else:
                self._sheet_data[row_idx][col_idx] = item

        return orig_item

    def get_row(self, row_idx: int) -> List[Any]:
        """
        This function returns the list of column values for the specified row.
        It is the same function as the row() function except this function raises
        a Sheet-specific exception if an invalid index is specified.

        :param row_idx: The zero-based index of the row to be returned.
        :return: The list of column values for the row.
        :raises ExcelSheetIndexError: Raised if the specified index is out of range.
        """
        self.validate_indices(row_idx=row_idx)
        return self._sheet_data[row_idx]

    @override_optional
    def set_row(self, row_idx: int, row_data: List[Any]) -> List[Any]:
        """
        This function sets the specified Sheet row with the provided row data.
        :param row_idx: The row index where the data is to be set.
        :param row_data: The row data to be set into the specified row.
        :raises ValueError: Raised if the specified row index is invalid or if the given row_data does not
            have the same number of columns as the Sheet. Note: This would be better raised as a ExcelSheetIndexError
            but ValueError has been raised to be consistent with prototype.
        :returns The original row object for comparison to the new.
        """
        if row_idx < 0 or row_idx > self._num_rows - 1:
            raise ValueError(
                'Invalid row index ({}). Index must be in range ({}-{})'.format(row_idx, 0, self._num_rows - 1))
        if len(row_data) != self._num_cols:
            raise ValueError('Row length mismatch. Row data must be limited to ({}) columns'.format(self._num_cols))

        orig_row = self._sheet_data[row_idx]

        if row_data[:] != orig_row:
            self._sheet_data[row_idx] = row_data[:]

            for col_idx in range(self._num_cols):
                if self._sheet_data[row_idx][col_idx] == '':
                    self._sheet_data[row_idx][col_idx] = self.DEFAULT_CELL_VAL

        return orig_row

    @override_optional
    def set_col(self, col_idx: int, col_data: List[Any]) -> List[Any]:
        """
        This function sets the specified Sheet column with the provided column data.
        :param col_idx: The column index where the data is to be set.
        :param col_data: The column data to be set into the specified column.
        :raises ValueError: Raised if the specified column index is invalid or if the given col_data does not
            have the same number of rows as the Sheet. Note: This would be better raised as a ExcelSheetIndexError
            but ValueError has been raised to be consistent with prototype.
        :returns The original column object for comparison to the new.
        """
        if col_idx < 0 or col_idx > self._num_cols - 1:
            raise ValueError(
                'Invalid column index ({}). Index must be in range ({}-{})'.format(col_idx, 0, self._num_cols))
        if len(col_data) < self._num_rows:
            raise ValueError('Column length mismatch. Column data must be limited to ({}) rows'.format(self._num_rows))

        orig_col = []

        for i, row in enumerate(self._sheet_data):
            if col_data[i] == '':
                row[col_idx] = self.DEFAULT_CELL_VAL
            else:
                if row[col_idx] != col_data[i]:
                    orig_col.append(row[col_idx])
                    row[col_idx] = col_data[i]

        return orig_col

    def get_col_width(self, col_idx: int) -> int:
        """
        This function returns the column width for the specified column.
        :param col_idx: The index of the column being queried.
        :returns: The column width.
        :raises: ExcelSheetIndexError - Raised if the specified column index is out of range.
        """
        self.validate_indices(col_idx=col_idx)
        return self._col_widths[col_idx]

    @override_optional
    def set_col_width(self, col_idx: int, width: int = DEFAULT_COL_WIDTH) -> int:
        """
        This function sets the column width to the specified value.
        :param col_idx: The index of the column being updated.
        :raises: ExcelSheetIndexError - Raised if the specified column index is out of range.
                 ExcelSheetValueError - Raised if the input width is invalid (< 0).
        :returns The original column width for comparison to the new.
        """
        self.validate_indices(col_idx=col_idx)
        if width >= 0:
            orig_width = self._col_widths[col_idx]
            if orig_width != width:
                self._col_widths[col_idx] = width
            return orig_width
        else:
            raise ExcelSheetValueError("Column width ({}) is invalid. Value must be a positive integer.")

    def validate_indices(self, row_idx: Either[int, slice] = None, col_idx: Either[int, slice] = None):
        """
        This function validates the row and col values (if not None) and raises an exception if one of the specified
        values is out of range of the Sheet part.
        :param row_idx: A zero-based row index to be validated. If provided as a slice, the slice limits are validated.
        :param col_idx: A zero-based column index to be validated. If provided as a slice, the slice limits are
            validated.
        :raises: ExcelSheetIndexError - specified row or column index is less than 0 or too large.
                 TypeError - Invalid type used for a cell index.
        """
        if row_idx is not None:
            if isinstance(row_idx, int):
                if row_idx >= 0 and row_idx < len(self._sheet_data):
                    pass
                else:
                    raise ExcelSheetIndexError(
                        "Row index ({}) out of range. Index must be in "
                        "range {}-{}.".format(row_idx, 0, len(self._sheet_data) - 1))

            elif isinstance(row_idx, slice):
                if row_idx.start is not None:
                    self.validate_indices(row_idx=row_idx.start)
                if row_idx.stop is not None:
                    self.validate_indices(row_idx=row_idx.stop - 1)
            else:
                raise TypeError("Row index must be of type 'int or slice'. Type '{}' was "
                                "specified.".format(type(row_idx)))

        if col_idx is not None:
            if isinstance(col_idx, int):
                if col_idx >= 0 and col_idx < len(self._sheet_data[0]):
                    pass
                else:
                    raise ExcelSheetIndexError(
                        "Column index ({}) out of range. Index "
                        "must be in range {}-{}.".format(col_idx, 0, len(self._sheet_data[0]) - 1))
            elif isinstance(col_idx, slice):
                if col_idx.start is not None:
                    self.validate_indices(col_idx=col_idx.start)
                if col_idx.stop is not None:
                    self.validate_indices(col_idx=col_idx.stop - 1)
            else:
                raise TypeError("Column index must be of type 'int or slice'. Type '{}' was "
                                "specified.".format(type(col_idx)))

    def get_index_style(self) -> str:
        """
        This function returns the name of the current index style of the sheet part.
        """
        return self._index_style.name

    @override_optional
    def set_index_style(self, style: str) -> str:
        """
        This function sets the column index style. The style is specified as a string, but must map to one of
        the types defined in SheetIndexStyleEnum.
        :param style: A string equivalent corresponding to one of the style types defined in SheetIndexStyleEnum.
        :raises ExcelSheetIndexStyleError: Raised if the input 'style' is not a valid option.
        :returns The original style name for comparison to the new.
        """
        # Ensure the input is valid.
        try:
            SheetIndexStyleEnum[style].value
        except KeyError:
            log.error("ExcelSheet set_index_style() error. Invalid index style: {}", style)
            raise ExcelSheetIndexStyleError("ExcelSheet set_index_style() error. Invalid index style: '{}'"
                                            .format(style))

        orig_style = self._index_style.name

        if orig_style != style:
            self._index_style = SheetIndexStyleEnum[style]

        return orig_style

    @override_optional
    def add_row(self, row_idx: int = None) -> int:
        """
        This function inserts a row into the sheet at the specified row index. If row_idx is None, the
        row is appended to the end of the list of rows.
        :param row_idx: The row index where the column is to be inserted.
        :raises: ExcelSheetIndexError: Raised if the input row_idx is invalid.
        :returns row_idx: The calculated index of the Sheet row to be inserted (since can be None on input).
        """
        self.validate_indices(row_idx=row_idx)

        if row_idx is None:
            row_idx = self._num_rows

        self._sheet_data.insert(row_idx, [self.DEFAULT_CELL_VAL] * self._num_cols)
        self._num_rows += 1

        return row_idx

    @override_optional
    def add_rows(self, num_rows: int = NUM_ROWS_ADD_DEL, row_idx: int = None) -> int:
        """
        This function adds the specified number of rows to the sheet starting at the specified row index. If
        row_idx is None, the new rows are added at the end of the Sheet.
        :param num_rows: The number of rows to be added to the Sheet.
        :param row_idx: The row index where the new rows are to be inserted/added.
        :raises ExcelSheetIndexError: Raised if an invalid row index was specified.
        :returns row_idx: The calculated index of the Sheet rows to be inserted (since can be None on input).
        """
        self.validate_indices(row_idx=row_idx)

        if row_idx is None:
            row_idx = self._num_rows

        for _ in range(num_rows):
            self._sheet_data.insert(row_idx, [self.DEFAULT_CELL_VAL] * self._num_cols)
        self._num_rows += num_rows

        return row_idx

    @override_optional
    def delete_row(self, row_idx: int = None) -> int:
        """
        This function deletes the Sheet row at the specified row index. If row_idx is None, the last row in
        the Sheet is deleted.
        :param row_idx: The index of the Sheet row to be deleted.
        :raises: ExcelSheetIndexError: Raised if the input row_idx is invalid.
        :returns row_idx: The calculated index of the Sheet row to be deleted (since can be None on input).
        """
        self.validate_indices(row_idx=row_idx)

        if row_idx is None:
            row_idx = self._num_rows - 1

        del self._sheet_data[row_idx]
        self._num_rows -= 1

        return row_idx

    @override_optional
    def delete_rows(self, num_rows: int = NUM_ROWS_ADD_DEL, row_idx: int = None) -> int:
        """
        This function deletes the specified number of rows from the Sheet starting at the specified row index.
        If row_idx is None, the rows are deleted from the end of the Sheet.
        :param num_rows: The number of rows to be deleted.
        :param row_idx: The row index where the deletion should commence.
        :raises ExcelSheetValueError: Raised if an invalid number of rows was specified.
        :raises ExcelSheetIndexError: Raised if an invalid row index was specified.
        :returns row_idx: The calculated row index where the deletion should commence (since can be None on input).
        """
        self.validate_indices(row_idx=row_idx)

        if num_rows > self._num_rows:
            raise ExcelSheetValueError("Invalid number of rows ({}) specified for deletion.".format(num_rows))

        if row_idx is None:
            row_idx = self._num_rows - num_rows

        self._sheet_data = self._sheet_data[:row_idx] + self._sheet_data[row_idx + num_rows:]
        self._num_rows -= num_rows

        return row_idx

    @override_optional
    def add_col(self, col_idx: int = None) -> int:
        """
        This function inserts a column into the sheet at the specified column index. If col_idx is None, the
        column is appended to the end of the list of columns.
        :param col_idx: The column index where the column is to be inserted.
        :raises ExcelSheetIndexError: Raised if an invalid column index was specified.
        :returns col_idx: The calculated column index where the column is to be inserted (since can be None on input).
        """
        self.validate_indices(col_idx=col_idx)

        if col_idx is None:
            col_idx = self._num_cols

        for row in self._sheet_data:
            row.insert(col_idx, self.DEFAULT_CELL_VAL)
            self._col_widths.insert(col_idx, self.DEFAULT_COL_WIDTH)
        self.__shift_column_headers(col_idx, ColShiftDirectionEnum.right)

        self._num_cols += 1

        return col_idx

    @override_optional
    def add_cols(self, num_cols: int = NUM_COLS_ADD_DEL, col_idx: int = None) -> int:
        """
        This function adds the specified number of columns to the Sheet starting at the specified column index.
        If col_idx is None, the columns are appended to the current list of columns.
        :param num_cols: The number of columns to be added.
        :param col_idx: The column index where the columns are to be added.
        :raises ExcelSheetIndexError: Raised if an invalid column index was specified.
        :returns col_idx: The calculated column index where the columns are to be added (since can be None on input).
        """
        self.validate_indices(col_idx=col_idx)

        if col_idx is None:
            col_idx = self._num_cols

        column_headers_managed = False

        for row in self._sheet_data:
            for _ in range(num_cols):
                row.insert(col_idx, self.DEFAULT_CELL_VAL)
                self._col_widths.insert(col_idx, self.DEFAULT_COL_WIDTH)
                if not column_headers_managed:
                    self.__shift_column_headers(col_idx, ColShiftDirectionEnum.right)
            column_headers_managed = True

        self._num_cols += num_cols

        return col_idx

    @override_optional
    def delete_col(self, col_idx: int = None) -> int:
        """
        This function deletes the column from the Sheet with the specified column index. If col_idx is None, the
        last column in the sheet is deleted.
        :param col_idx: The index of the column to be deleted.
        :returns col_idx: The calculated column index where the column is to be deleted (since can be None on input).
        """
        self.validate_indices(col_idx=col_idx)

        # Delete the column of data
        if col_idx is None:
            col_idx = self._num_cols - 1
        for row in self._sheet_data:
            del row[col_idx]
            self.del_col_name(col_idx=col_idx, emit=False)
        self._num_cols -= 1
        self.del_col_name(col_idx=col_idx, emit=False)
        del self._col_widths[col_idx]
        self.__shift_column_headers(col_idx, ColShiftDirectionEnum.left)

        return col_idx

    @override_optional
    def delete_cols(self, num_cols: int = NUM_COLS_ADD_DEL, col_idx: int = None) -> int:
        """
        This function deletes the specified number of columns starting at the specified column index. If col_idx
        is None, the last num_cols of the Sheet are deleted.
        :param num_cols: The number of columns to be deleted.
        :param col_idx: The column index of the first column to be deleted.
        :raises ExcelSheetValueError: Raised if an invalid number of columns was specified.
        :raises ExcelSheetIndexError: Raised if an invalid column index was specified.
        :returns col_idx: The calculated column index where the columns are to be deleted (since can be None on input).
        """
        self.validate_indices(col_idx=col_idx)

        if num_cols > self._num_cols:
            raise ExcelSheetValueError("Invalid number of columns ({}) specified for deletion.".format(num_cols))

        if col_idx is None:
            col_idx = self._num_cols - num_cols

        done_col_extras_cleanup = False

        for row in self._sheet_data:
            for _ in range(num_cols):
                del row[col_idx]
                if not done_col_extras_cleanup:
                    self.del_col_name(col_idx=col_idx, emit=False)
                    self.__shift_column_headers(col_idx, ColShiftDirectionEnum.left)
                    del self._col_widths[col_idx]
            done_col_extras_cleanup = True

        self._num_cols -= num_cols

        return col_idx

    @override_optional
    def transpose(self):
        """
        This function transposes the 2-D array such that the original array's column indices become the row
        indices and the original row indices become the column indices.
        """
        data = []
        rows = self._num_cols
        cols = self._num_rows

        for row in range(rows):
            data.append([self.DEFAULT_CELL_VAL] * cols)

        for row in range(rows):
            for col in range(cols):
                data[row][col] = self._sheet_data[col][row]

        self._sheet_data = data
        self._num_rows = rows
        self._num_cols = cols
        self._col_widths = [self.DEFAULT_COL_WIDTH] * cols

    @override_optional
    def clear(self):
        """
        This function clears all data from the sheet, clears the column widths list and the heading names dictionary,
        and sets the row and column sizes to zero.
        """
        self._sheet_data = []
        self._num_rows = 0
        self._num_cols = 0
        self._col_widths = []
        # Note: Prototype doesn't blank the column headings, but it's done here because it makes sense to do so.
        self._named_cols = {}

    def row(self, row_idx: int) -> List[Any]:
        """
        This function returns the list of column values for the specified row.

        :param row_idx: The zero-based index of the row to be returned.
        :return: The list of column values for the row.
        :raises: ExcelSheetIndexError - Raised if the specified row index is out of range.
        """
        self.validate_indices(row_idx=row_idx)
        return self._sheet_data[row_idx]

    def col(self, col_idx: int) -> List[Any]:
        """
        This function returns a list of row values for the specified column index.
        :param col_idx: The zero-based index of the column.
        :return: A list of row values for the column.
        :raises: ExcelSheetIndexError - Raised if the specified column index is out of range.
        """
        self.validate_indices(col_idx=col_idx)
        return [row[col_idx] for row in self._sheet_data]

    def total(self) -> float:
        """
        This function returns the summation of all values in the Sheet part.
        :return: The total sum of all values in the Sheet part.
        :raises ExcelSheetTypeError: Raised if an invalid data type is included in the summation.
        """
        try:
            res = sum([sum(row) for row in self._sheet_data])
        except TypeError as e:
            raise ExcelSheetTypeError("ExcelSheet.total() error. Invalid type for sum operation on sheet data: {}"
                                      .format(e))
        return res

    def find(self, item: Any) -> Either[int, Tuple[int, int]]:
        """
        This function searches the Sheet part for the first occurrence of the specified item.

        :param item: The sheet cell item to be found.
        :return: If the sheet is composed of a single row, the column index of the found item is returned.
            If the sheet is composed of a single column, the row index of the found item is returned.
            If the Sheet part has multiple rows and columns, the (row, col) tuple of the found item is returned.
            If the item is not found, a ValueError is raised.
        :raises: ValueError - Raised if the input item was not found in the Sheet part.
        """
        if self._num_rows == 1:
            try:
                col = self._sheet_data[0].index(item)
                return col
            except ValueError:
                pass

        elif self._num_cols == 1:
            for row in range(len(self._sheet_data)):
                i = self._sheet_data[row][0]
                if i == item:
                    return row
        else:
            for row in range(len(self._sheet_data)):
                a_row = self._sheet_data[row]
                try:
                    col = a_row.index(item)
                except ValueError:
                    pass
                else:
                    return row, col

        raise ValueError('"%s" not found.' % item)

    @override_optional
    def set_col_name(self, col_idx: Either[str, int], name: str):
        """
        This function sets the column name to the specified value if the name is not already in use.
        :param col_idx: The column to be named. This value can be a string representing an Excel-style spreadsheet
            column heading, or integer representing a Sheet column index.
        :param name: The new column name.
        :raises ExcelSheetIndexError: Raised if the input
        """
        if name is None:
            return
        if name in self._named_cols:
            log.warning("Sheet column name ('{}') already in use", name)
            raise ValueError("Column name ({}) already in use.".format(name))
        if isinstance(col_idx, str):
            col_idx = translate_excel_column(col_idx)
        self.validate_indices(col_idx=int(col_idx))

        self._named_cols[name] = col_idx

    @override_optional
    def del_col_name(self, name: str = None, col_idx: int = None, emit: bool = True):
        """
        This function deletes the specified custom column name from the _named_cols dictionary. The column name
        for deletion can be specified by the custom name itself, or by the column index. If no match is found,
        no action is taken.
        :param name: The custom column name to be deleted.
        :param col_idx: The column index of the custom column name to be deleted.
        :param emit: True if this function is to emit the sig_col_name_changed signal to the front-end;
            false otherwise. When a column is being deleted, the signal emitted by that function is
            sufficient to notify the front end that everything related to the column needs to be updated
            and this function therefore, does not need to emit.
        :return: The Excel column ID for the column name deleted.
        """
        if col_idx is not None:
            name = self.get_named_col(col_idx=col_idx)

        if name is not None:
            if name in self._named_cols:
                name_col_idx = self._named_cols[name]

                xls_idx = excel_column_letter(name_col_idx)
                del self._named_cols[name]

                return xls_idx, name_col_idx
        return None

    def get_named_col(self, col_idx: int) -> Optional[str]:
        """
        This function searches for the specified column index as a value in the dictionary of custom-named columns.
        If the column index is found, the name of the column is returned; otherwise, None is returned.
        :param col_idx: A column index for which a custom header will be returned if it exists.
        :return: The custom name of the specified column if one exists; None otherwise.
        """
        if col_idx in self._named_cols.values():
            for name, index in self._named_cols.items():
                if col_idx == index:
                    return name
        else:
            return None

    def get_named_cols(self) -> Dict[str, int]:
        """
        This function returns a map of custom column names to column indices.
        """
        return self._named_cols

    def get_col_widths(self) -> List[int]:
        """
        This function returns the list of column widths for the ExcelSheet.
        """
        return self._col_widths

    def get_col_header(self, col_idx: int) -> str:
        """
        This function returns a formatted header string for the specified column index.
        :param col_idx: The index of the column for which a formatted header is to be returned.
        :return: If the column has a custom header, and the current index style is 'excel', the column's
            equivalent Excel header is appended with the customer header in the format column_letter-column_name-. If
            there is no custom name associated with the column, and the current index style is 'excel', the column's
            Excel header name is returned.  If the current index style is 'array', the input index is returned as a
            string. The number of characters returned in the string is limited by the column width associated with
            the column.
        :raises ExcelSheetIndexError: Raised if the specified column index is invalid.
        """
        val = get_col_header(col_idx, self._named_cols, self._index_style)
        val = val[:self._col_widths[col_idx]]
        return val

    def get_row_header(self, row_idx: int) -> str:
        """
        This function returns a string representation of the row NUMBER.
        :param row_idx: The index of the row for which the row header is requested.
        :return: The row header.
        """

        val = str(row_idx + 1)
        val = val[:len(str(self._num_rows))]
        return val

    def set_data(self, data: Either[Decl.ExcelSheet, TablePart, int, float, str, tuple, list]):
        """
        This function replaces this instance's _sheet_data with the specified data and adjusts the sheets dimensions
        accordingly.
        :param data: Data to be assigned to this instance. Argument data can be one of the following data types:
            - ExcelSheet: The data argument is copied into this instance. This instance becomes a full copy of the
              data instance.
            - TablePart: The data argument represents a Table Part whose data values and column names are copied into
              this instance. This instance is reset and resized to the Table Part data dimensions accordingly.
            - int, float, str, unicode: The data argument represents a single cell value to be assigned to this
              instance. This instance is resized to a 1x1 ExcelSheet accordingly.
            - tuple, list: The data argument represents a cell, row, column or 2-D array of data. The dimensions of
              data are determined, this instance is resized accordingly, and the data values are assigned to this
              instance. A tuple with five elements results in a sheet of 5 rows x 1 column, and similarly for a list,
              a one-dimensional list of 5 elements results in a sheet of 5 rows x 1 column.
            - TablePart: The TablePart data and column headings are assigned to this instance and this instance is
              resized accordingly.
        """
        # copy from another ExcelSheet
        if isinstance(data, ExcelSheet):
            self.copyfrom(data)

        # update sheet to a single cell
        elif type(data) in (int, float, str):
            if data == '':
                self._sheet_data = [[self.DEFAULT_CELL_VAL]]
            else:
                self._sheet_data = [[data]]
            self._num_cols = 1
            self._num_rows = 1
            self._col_widths = [self.DEFAULT_COL_WIDTH]
            self._named_cols = {}

        # copy from a tuple or list
        elif type(data) in (tuple, list):

            # get dimensions of the data
            rows = len(data)
            cols = 1
            for row in data:
                try:
                    col = len(row)
                except:  # No-harm exception, now go the safe route
                    col = 1
                else:
                    if col > cols:
                        cols = col

            # setup the table
            self._sheet_data = []
            for row in range(rows):
                self._sheet_data.append([self.DEFAULT_CELL_VAL] * cols)
            self._num_rows = rows
            self._num_cols = cols
            self._col_widths = [self.DEFAULT_COL_WIDTH] * cols
            self._named_cols = {}

            # insert the data
            for row in range(rows):
                for col in range(cols):
                    try:
                        self._sheet_data[row][col] = data[row][col]
                    except:  # No-harm exception, now go the safe route
                        if col == 0:
                            self._sheet_data[row][col] = data[row]
                        else:
                            self._sheet_data[row][col] = 0

        # copy from a table
        elif isinstance(data, TablePart):

            num_records = 0
            try:
                num_records = data.get_number_of_records()
                if num_records:
                    self.set_data([data[1:] for data in data.get_all_data()])

                    fields = data.get_field_names()
                    for index, field in enumerate(fields):
                        self._named_cols[field] = index

                    # Note: No signal required here because it's already done in the 'copy from a tuple or list'
                    # block above.
                    pass  # so Code -> Reformat leaves previous comment alone

                else:
                    log.warning("ExcelSheet.set_data() found no records in source TablePart. Sheet: {}. Table: {}",
                                self, data)

            except TablePartSQLiteTableNotFoundError as e:
                log.error("ExcelSheet set_data() error. Table Part data unretrievable. More info: {}", str(e))
                raise

    @override_optional
    def read_excel(self, xls_file: str, xls_sheet: str, xls_range: str = None, accept_empty_cells: bool = False):
        """
        This file opens the specified Excel file and worksheet, and reads the specified range of data from the
        worksheet into the current Sheet Part.  The current instance is fully reset to accommodate the loaded data.
        :param xls_file: Excel file path.
        :param xls_sheet: The name of a worksheet within the specified Excel file.
        :param xls_range: An Excel-styled range specifying the data to be read from the opened worksheet.
        :raises ExcelReadError: Raised when an error occurs locating or reading the excel file or file sheet.
        """

        data = read_from_excel(
            xls_file=xls_file, xls_sheet=xls_sheet, xls_range=xls_range, accept_empty_cells=accept_empty_cells)

        # setup the sheet and store the excel data
        num_rows = len(data)
        num_cols = len(data[0])

        self.set_rows(num_rows)
        self.set_cols(num_cols)

        # read the excel data
        for row in range(num_rows):
            for col in range(num_cols):
                try:
                    self._sheet_data[row][col] = data[row][col]
                except IndexError:
                    self._sheet_data[row][col] = ''
                    log.error("ExcelSheet error reading Excel file. Invalid data indices: row: {}, col: {})", row, col)
                    raise ExcelReadError("Error reading Excel file. Invalid data indices:"
                                         " row: {}, col: {})".format(row, col))

    def write_excel(self, xls_file: str, xls_sheet: str, xls_range: str = ''):
        """
        This function creates an Excel file at the specified path, adds a worksheet with the specified name to the
        file, then writes this Sheet Part instance's data to the new worksheet and saves the file.
        :param xls_file: The path of the Excel file to be created.
        :param xls_sheet: The name of the worksheet to be added to the file.
        :param xls_range: An Excel-styled range specifying the data to be read from the opened worksheet. Empty means
        full sheet.
        :raises ExcelWriteError: Raised when an error occurs opening or writing to the excel file or worksheet.
        """
        write_to_excel(data=self._sheet_data, xls_file=xls_file, xls_sheet=xls_sheet, xls_range=xls_range)

    @override_optional
    def copyfrom(self, other_sheet: Decl.ExcelSheet) -> Decl.ExcelSheet:
        """
        This function copies the input ExcelSheet into the current sheet, replicating the former.
        :param other_sheet:
        :return: This instance updated as a copy of the input (i.e. returns 'self').
        """
        if not isinstance(other_sheet, ExcelSheet):
            raise TypeError('ExcelSheet copy error. Cannot copy a {} object into a {} object'.format(
                other_sheet.__class__, self.__class__))

        self._sheet_data = copy.deepcopy(other_sheet.sheet_data)
        self._num_rows = other_sheet.num_rows
        self._num_cols = other_sheet.num_cols
        self._col_widths = copy.deepcopy(other_sheet.col_widths)
        self._named_cols = copy.deepcopy(other_sheet.named_cols)

        return self

    def repr_data(self) -> str:
        """
        This function creates a tabular string representation of the sheet part data, devoid of row or column
        headings. The output is of the form:

            1        2        3        4
            5        6        7        8
            9        10       11       12
            13       14       15       16
        :return: A tabular string representation of only the sheet's data.
        """
        rep = ''
        for row in range(self._num_rows):
            try:
                for col in range(self._num_cols):
                    val = str(self._sheet_data[row][col])
                    val = val[:self._col_widths[col]]
                    val += ' ' * (self._col_widths[col] - len(val) + 2)
                    rep += val
            except:  # No-harm exception, just continue on
                pass
            rep += '\n'

        return rep

    def repr_row_names(self):
        """
        This function creates a string representation of row headings. The output is of the forrm:
            com 0
            com 1
            com 2
            com 3
            com 4
        :return: A string representation of row headings, with each heading on a new line.
        """
        rep = ''

        init_col_width = len(str(self._num_rows))

        for row in range(self._num_rows):
            val = self.get_row_header(row)
            val = ' ' * (init_col_width - len(val)) + val + '  '
            rep += '\1%s\1%s\2\n' % (self.REPR_LABEL, val)

        return rep

    def repr_col_names(self):
        """
        This function creates a string representation of column headings. The output factors in the current
        _index_type setting. If _index_type is set to 'excel', the column headings will be the Excel-styled
        column headings. If custom headings are defined for some columns, the output heading will be a concatenation
        of the Excel heading and the custom heading. If the _index_style is set to 'array' the column numbers are used
        as the column headings.
        :return: A string representation of the column headings.
        """

        rep = '\1%s\1' % self.REPR_LABEL

        # field names
        for col in range(self._num_cols):
            val = self.get_col_header(col)
            val += ' ' * (self._col_widths[col] - len(val) + 2)
            rep += val

        return rep

    @override_optional
    def fill(self, callback: FillCallable,
             cell_range: InCellRange = None) -> Tuple[SheetFillType, RowOrColSubset, RowOrColSubset]:
        """
        This function iterates over the specified 'cell_range' passing each cell row/col pair to the callback function
        with the result being assigned to the corresponding row/col cell in this sheet instance.
        See FillCallable description above for more info about it.

        :param cell_range: A cell or range of cells describing sheet cells to be iterated over. If
            'cell_range' is None, the entire sheet will be iterated over. The acceptable values for 'cell_range' are
            described in the resolve_cell_range() function's description for its 'cell_range' input parameter.
        :returns the sheet fill type and respective index values.

        :raises TypeError: Raised if an input tuple index contains neither an int nor a slice.
        :raises ValueError: Raised if the 'cell_range' value is determined to be invalid.
        :raises ExcelSheetIndexError: Raised if the resolved 'cell_range' is determined to be invalid.

        Examples of usage:

        Eg. 1.
        Fill sheet cells in the Excel-style range A1 to D3 with values for each cell computed by my_fill_callable.
            def my_fill_callable(row_idx: int, col_idx: int) -> float:
                return row_idx * 12.567 + col_idx * 2.315
            my_sheetpart.fill(callback=my_fill_callable, 'A1:D3')

        Eg. 2.
        Fill the entire sheet with 1's. Note: range not specified so whole sheet is filled.
            my_sheetpart.fill(lambda r, c: 1)

        Eg. 3.
        Fill entire sheet with sum of complementary values from two other sheets.
            my_sheetpart.fill(lambda r, c: sheetpart_a[(r, c)] + sheetpart_b[(r, c)])

        Eg. 4.
        Fill specified cell (4, 6) with the value 500
            my_sheetpart.fill(lambda r, c: 500, (4, 6))

        Eg. 5.
        Fill a range of row data in column 3 with the value 5
            slc = slice(2, 5)  # rows 2, 3, 4
            sp.fill(lambda r, c: 5, (slc, 3))

        Eg. 6.
        Fill a subset of rows and subset of columns with the value 5
            row_slc = slice(2, 5)
            col_slc = slice(3, 8)
            sp.fill(lambda r, c: 5, (row_slc, col_slc))

        """
        if cell_range is None:
            # Fill the entire sheet
            rows = self._num_rows
            cols = self._num_cols

            for row in range(rows):
                for col in range(cols):
                    self._sheet_data[row][col] = callback(row, col)

            return SheetFillType.full, None, None

        else:
            # Figure out what row/column range we've been given...
            row_idx, col_idx = resolve_cell_range(cell_range, self._num_rows, self._num_cols)

            self.validate_indices(row_idx=row_idx, col_idx=col_idx)

            # Fill the current sheet based on the range
            # row:int, col:int
            if isinstance(row_idx, int) and isinstance(col_idx, int):
                self._sheet_data[row_idx][col_idx] = callback(row_idx, col_idx)
                return SheetFillType.cell, row_idx, col_idx

            # row:int, col:slice
            elif isinstance(row_idx, int) and isinstance(col_idx, slice):
                for col in range(*col_idx.indices(self._num_cols)):
                    self._sheet_data[row_idx][col] = callback(row_idx, col)
                return SheetFillType.row, row_idx, tuple(col for col in range(*col_idx.indices(self._num_cols)))

            # row:slice, col:int
            elif isinstance(row_idx, slice) and isinstance(col_idx, int):
                for row in range(*row_idx.indices(self._num_rows)):
                    self._sheet_data[row][col_idx] = callback(row, col_idx)
                return SheetFillType.col, tuple(row for row in range(*row_idx.indices(self._num_rows))), col_idx

            # row:slice, col:slice
            else:
                for row in range(*row_idx.indices(self._num_rows)):
                    for col in range(*col_idx.indices(self._num_cols)):
                        self._sheet_data[row][col] = callback(row, col)
                return (SheetFillType.sheet,
                        tuple(range(*row_idx.indices(self._num_rows))),
                        tuple(range(*col_idx.indices(self._num_cols))))

    def __eq__(self, rhs: Decl.ExcelSheet) -> bool:
        """
        This function compares the input instance with the current instance for data equality.
        :param rhs: The right-hand side ExcelSheet instance to be compares with the current instance.
        :return: True if the sheet data within rhs is deemed equal to that in the current Sheet part;
            False otherwise.
        """
        if not issubclass(rhs.__class__, self.__class__):
            return False
        return rhs.sheet_data == self.sheet_data

    def __ne__(self, rhs: Decl.ExcelSheet) -> bool:
        """
        This function compares the input instance with the current instance for data inequality.
        :param rhs: The right-hand side ExcelSheet instance to be compares with the current instance.
        :return: True if the sheet data within rhs is deemed not equal to that in the current Sheet part;
            False otherwise.
        """
        return not (self == rhs)

    def __hash__(self) -> int:
        """
        This hash function returns the unique object ID for the instance, which will never be the same as the ID
        for another instance.

        NOTE: A python rule is that if two object are deemed equal by the __eq__() method, then the hash values
        should also be equal.  This rule is broken for the Sheet Part. The __eq__() method compares the mutable
        sheet part's _sheet_data between two sheet parts and returns true if they are the same. A custom __hash__()
        method implementation should be based on the attributes of an object, but only if the attributes are non-
        mutable so that the object's hash value does not change over the life of the object (having ramifications on
        dictionaries containing the objects).
        :return: A hash value for the instance.
        """
        return id(self)

    def __iter__(self):

        # iterates over entire grid
        for row in range(self._num_rows):
            for col in range(self._num_cols):
                yield self[row, col]

    def __getitem__(self, cell_range: InCellRange) -> Either[Decl.ExcelSheet, Any, None]:
        """
        This function provides index styled access (sheet_part[index]) to data in the _sheet_data attribute
        stored by this instance. For example:
            my_sheet['A']  # returns column A in a new Excel sheet instance
            my_sheet['A1']  # returns the value of cell A1
            my_sheet['A1:B4'] # returns cell range A1:B4 in a new Excel sheet instance
            my_sheet['A1_B4'] # returns cell range A1:B4 in a new Excel sheet instance
            my_sheet['3'] = 10  # returns third row in a new Excel sheet instance
            my_sheet[3] = 10  # returns row with INDEX:3 in a new Excel sheet instance
            my_sheet[(3,4)] # returns the value of cell row index: 3, column index:4
            my_sheet[2, slice(3,6)] = 10  # returns cell range at row index:2, in column index range:3-5, in 
                a new Excel sheet instance.
            my_sheet[slice(3,6), 2] = 10  # returns cell range between row index:3-5, in column index:2, in 
                a new Excel sheet instance.
            my_sheet[slice(3,6), slice(4, 7)] = 10  # returns cell range between row index:3-5, and between column
                index:4-6, in a new Excel sheet instance.

        :param cell_range: The cell_range of the ExcelSheet data to be returned by the current instance. The cell_range
            can be a string, integer, or tuple.  The acceptable formats for the cell_range parameter are described in
            the resolve_cell_range() function description.
        :return: An individual ExcelSheet cell value or a new ExcelSheet instance containing the range of data described
            by the input cell_range value, or None.
        :raises TypeError: Raised if an input tuple index contains neither an int nor a slice.
        :raises ValueError: Raised if the 'cell_range' value is determined to be invalid.
        :raises ExcelSheetIndexError: Raised if the resolved cell_range is determined to be invalid for the sheet.
        """

        # Figure out what row/column info we're dealing with...
        row, col = resolve_cell_range(cell_range, self._num_rows, self._num_cols)
        self.validate_indices(row_idx=row, col_idx=col)

        # The row/column information is now known. Compile the data into a returnable result...
        if isinstance(row, int) and isinstance(col, int):
            return self._sheet_data[row][col]

        elif isinstance(row, int) or slice and isinstance(col, int) or slice:
            return ExcelSheet(data=self, row_idx=row, col_idx=col)
        else:
            return None

    @override_optional
    def __setitem__(self, cell_range: InCellRange, val: Either[Decl.ExcelSheet, Any]) -> SheetSetItemIndex:
        """
        This function provides index capability (sheet_part[index]) to set data in the _sheet_data attribute
        stored by this instance. For example:
            my_sheet['A'] = 10  # sets all cell values in column A to 10
            my_sheet['A1'] = 10  # sets value of cell A1 to 10
            my_sheet['A1:B4'] = 10  # sets all cell values in range A1:B4 to 10
            my_sheet['A1_B4'] = 10  # same affect as my_sheet['A1:B4'] = 10
            my_sheet['3'] = 10  # sets all cell values in third row to 10
            my_sheet[3] = 10  # sets all cell values in row with INDEX 3 to 10
            my_sheet[(3,4)] = 10  # sets value of cell row index:3, column index: 4  to 10
            my_sheet[2, slice(3,6)] = 10  # sets cell values in row index:2, column index range: 3-5  to 10
            my_sheet[slice(3,6), 2] = 10  # sets cell values in row index range:3-5, column index:2  to 10
            my_sheet[slice(3,6), slice(4, 7)] = 10  # sets cell values in row index range:3-5, column index range
                4-6: to 10
        :param cell_range: The cell_range of the ExcelSheet data to be returned by the current instance. The cell_range
            can be a string, integer, or tuple.  The acceptable formats for the cell_range parameter are described in
            the resolve_cell_range() function description.
        :val: A value to be set into the current instance. val can be another ExcelSheet, or an item to be assigned to
            individual cells in the current instance.
        :raises TypeError: Raised if an input tuple index contains neither an int nor a slice.
        :raises ValueError: Raised if the 'cell_range' value is determined to be invalid.
        :raises ExcelSheetIndexError: Raised if the resolved 'cell_range' is determined to be invalid for the sheet.
        :returns the index type for the row and column indexes provided and their respecitve values.
        """

        # Figure out what row/column info we're dealing with...
        row, col = resolve_cell_range(cell_range, self._num_rows, self._num_cols)
        self.validate_indices(row_idx=row, col_idx=col)

        # The row/column information is now known. Assign the input values to the rows/columns...
        return self.__set_item(row=row, col=col, val=val)

    def __getattr__(self, index: InCellRange) -> Either[Decl.ExcelSheet, Any]:
        """
        This function provides 'dot notation' styled access to cells within the sheet part. For example:
            my_sheetpart.A1  # returns the value in cell A1.
            my_sheetpart.A   # returns a new sheet part that only contains the contents of column A from my_sheetpart
            my_sheetpart.A1_B3  # returns a new 2x3 sheet part containing the values of cell range A1:B3.

        :param index: See __getitem__ description above.
        :return: The value corresponding to the specified sheet range. If the 'index' specifies a single cell, a value
            is returned. If 'index' specifies a range of cells, a new ExcelSheet is returned sized to the returned data.
        """
        if self.__is_valid_range_pattern(index):
            return self.__getitem__(index)
        else:
            raise AttributeError("The sheet does not have an attribute named {}. If a sheet range was intended, "
                                 "ensure the range is specified using the format A_A for single columns, "
                                 "A_Z for a range of columns, A1 for cells, and A1_Z10 for a range of rows "
                                 "and columns. Columns must be specified using up to three capital letters."
                                 .format(index))

    def __setattr__(self, index: InCellRange, val: Either[Decl.ExcelSheet, Any]):
        """
        This function provides 'dot notation' styled access to cells within the sheet part. For example:
            my_sheetpart.A1 = 99  # sets cell A1 to the value 99.
            my_sheetpart.A = 99  # sets all cells in column A to the value 99
            my_sheetpart.A1_B3 = 99 # sets all cells in the range A1:B3 to 99
        :param index: See __setitem__ description above.
        """
        if self.__is_valid_range_pattern(index):
            self.__setitem__(index, val)
        else:
            BasePart.__setattr__(self, index, val)

    def __contains__(self, item: Any):

        for row in self._sheet_data:
            if item in row:
                return True
        return False

    def __repr__(self):
        """
        This function creates a string representation of the sheet's data. The output is of the form:

            com        0        1        2        4
            com 0     1        2        3        4
            com 1     5        6        7        8
            com 2     9        10       11       12
            com 3     13       14       15       16

        :return: A tabular string representation of the sheet's data.
        """
        rep = ''
        init_col_width = len(str(self._num_rows))
        rep += '\1%s\1' % self.REPR_LABEL
        rep += ' ' * (init_col_width + 4)

        # field names
        for col in range(self._num_cols):
            val = self.get_col_header(col)
            val += ' ' * (self._col_widths[col] - len(val) + 2)
            rep += val
        rep += '\2\n'
        for row in range(self._num_rows):
            val = self.get_row_header(row)
            val = ' ' * (init_col_width - len(val)) + val + '  '
            rep += '\1%s\1%s\2' % (self.REPR_LABEL, val)

            try:
                for col in range(self._num_cols):
                    val = str(self._sheet_data[row][col])
                    val = val[:self._col_widths[col]]
                    val += ' ' * (self._col_widths[col] - len(val) + 2)
                    rep += val
            except:  # No-harm exception, just continue on
                pass

            rep += '\n'
        return rep[:-1]

    # --------------------------- instance PUBLIC properties ----------------------------

    sheet_data = property(get_sheet_data)
    num_rows = property(get_rows, set_rows)
    num_cols = property(get_cols, set_cols)
    named_cols = property(get_named_cols)
    col_widths = property(get_col_widths)
    index_style = property(get_index_style, set_index_style)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __is_valid_range_pattern(self, pattern: str) -> Optional[bool]:
        """
        Determines if the pattern is a valid Excel range, column, or cell specification.
        :param pattern: The Excel range, column, or cell specification to check.
        :return: True if valid and False otherwise.
        """
        return (re.match(CELL_RNG_PATTERN_ATTR, pattern) or
                re.match(COL_PATTERN, pattern) or
                re.match(CELL_PATTERN, pattern))

    def __shift_column_headers(self, col_idx: int, direction: ColShiftDirectionEnum):
        """
        This function iterates over the _named_columns dictionary adjusting column indices, as necessary, to
        account for a column being added to, or deleted from, the sheet.
        :param col_idx: The index of the column that was added or deleted.
        :param direction: The direction to shift the sheet's columns per the action performed (add/delete column)
        on the sheet.
        """

        # Handle a column deletion
        if direction == ColShiftDirectionEnum.left:
            for name, idx in self._named_cols.items():
                if idx > col_idx:
                    self._named_cols[name] -= 1
        # Handle a column addition
        elif direction == ColShiftDirectionEnum.right:
            for name, idx in self._named_cols.items():
                if idx >= col_idx:
                    self._named_cols[name] += 1

    def __set_item(self, row: Either[int, slice], col: Either[int, slice],
                   val: Either[Decl.ExcelSheet, Any]) -> SheetSetItemIndex:
        """
        This function provides the actual value setting capability of the __setitem__() function, assigning
        the provided 'val' data to the Sheet Part data as described by the 'row' and 'col' parameters.
        :param row: The row index or row segment to which the specified value is to be applied.
        :param col: The column index or column segment to which the specified value is to be applied.
        :param val: The data to be applied to the portion of _sheet_data described by the row/col input parameters. If
           is another Sheet Part, the portion of the the input Sheet Part described by row and col, is copied into
           this instance.
        :returns the index type combination of (row, col) and their respective values.
        """

        # Ensure val is not an empty string if it is an object
        if not isinstance(val, ExcelSheet):
            if val == '':
                val = self.DEFAULT_CELL_VAL

        if isinstance(row, int):
            if isinstance(col, int):
                self._sheet_data[row][col] = val
                return SheetSetItemIndexType.int_int, row, col

            if isinstance(col, slice):
                col_start = 0 if col.start is None else col.start
                if isinstance(val, ExcelSheet):
                    for col_i in range(self._num_cols)[col]:
                        self._sheet_data[row][col_i] = copy.deepcopy(val.sheet_data[0][col_i - col_start])
                else:
                    for col_i in range(self._num_cols)[col]:
                        self._sheet_data[row][col_i] = val
                return SheetSetItemIndexType.int_slice, row, (col_start, col.stop - 1)

        if isinstance(row, slice):
            row_start = 0 if row.start is None else row.start
            if isinstance(col, int):
                if isinstance(val, ExcelSheet):
                    for row_i in range(self._num_rows)[row]:
                        self._sheet_data[row_i][col] = copy.deepcopy(val.sheet_data[row_i - row_start][0])
                else:
                    for row_i in range(self._num_rows)[row]:
                        self._sheet_data[row_i][col] = val
                return SheetSetItemIndexType.slice_int, (row_start, row.stop - 1), col

            if isinstance(col, slice):
                col_start = 0 if col.start is None else col.start
                if isinstance(val, ExcelSheet):
                    for row_i in range(self._num_rows)[row]:
                        for col_i in range(self._num_cols)[col]:
                            self._sheet_data[row_i][col_i] = \
                                copy.deepcopy(val.sheet_data[row_i - row_start][col_i - col_start])
                else:
                    for row_i in range(self._num_rows)[row]:
                        for col_i in range(self._num_cols)[col]:
                            self._sheet_data[row_i][col_i] = val
                return SheetSetItemIndexType.slice_slice, (row_start, row.stop - 1), (col_start, col.stop - 1)


class SheetPart(BasePart, ExcelSheet):
    """
    This class defines the functionality required to support an Origame Sheet Part.

    The Sheet Part combines the functionality of the Excel Sheet and Base Part classes.
    """

    class Signals(BridgeEmitter):
        # Supported signals
        sig_row_subset_changed = BridgeSignal(int, int, int)  # (row index, start col index, end col index)
        sig_col_subset_changed = BridgeSignal(int, int, int)  # (start row index, end row index, col index)
        # signal args are (start row idx, end row idx, start col idx, end col idx):
        sig_sheet_subset_changed = BridgeSignal(int, int, int, int)
        sig_cell_changed = BridgeSignal(int, int)  # (row index, col index)
        sig_col_width_changed = BridgeSignal(int, int)  # (column index, column width)
        sig_col_idx_style_changed = BridgeSignal(int)  # (SheetIndexStyleEnum)
        sig_rows_added = BridgeSignal(int, int)  # (start row index, number of rows  added (can be +/-)).
        sig_cols_added = BridgeSignal(int, int)  # (start col index, number of cols  added (can be +/-)).
        sig_col_name_changed = BridgeSignal(int, str)  # (col index, new name)
        sig_full_sheet_changed = BridgeSignal()  # All sheet part attributes have been modified by an operation

    DEFAULT_VISUAL_SIZE = dict(width=10.0, height=5.1)
    PART_TYPE_NAME = "sheet"
    DESCRIPTION = """\
        Sheets organize data in a grid that can be accessed by a function script using standard spreadsheet notation,
        for example 'link.sheet.A1 = 5'.

        Double-click to edit the sheet.
    """

    _ORI_HAS_SLOW_DATA = True

    def __init__(self, parent: ActorPart,
                 name: str = None,
                 position: Position = None,
                 data: Either[List[List[Any]], ExcelSheet] = None,
                 row_idx: Either[int, slice] = None,
                 col_idx: Either[int, slice] = None):
        """
        In addition to the base class params, the following are required:
        :param parent: The Actor Part to which this part belongs.
        :param name: The name assigned to this part instance.
        :param position: A position to be assigned to the newly instantiated default SheetPart. This argument
            is None when the part will be initialized from .ori data using the set_from_ori() function.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = SheetPart.Signals()
        ExcelSheet.__init__(self, data=data, row_idx=row_idx, col_idx=col_idx)

    @override(BasePart)
    def get_snapshot_for_edit(self) -> {}:
        data = super().get_snapshot_for_edit()

        data['sheet_data'] = self.get_sheet_data()
        data['custom_col_names'] = deepcopy(self.get_named_cols())
        data['all_col_names'] = []

        # Create a list of all column names (Excel and custom) in index-order
        num_cols = self.get_cols()
        if num_cols > 0:
            data['all_col_names'] = [self.get_col_header(col) for col in range(0, num_cols)]

        return data

    @override(BasePart)
    def get_matching_properties(self, re_pattern: str) -> List[str]:
        matches = BasePart.get_matching_properties(self, re_pattern)

        regexp = re.compile(re.escape(re_pattern), re.IGNORECASE)
        for row_num, row in enumerate(self._sheet_data):
            for cell_num, val in enumerate(row):
                val_str = str(val)
                result = regexp.search(val_str)
                if result:
                    log.debug('Sheet part {} row {} col {} matches pattern "{}" on cell content "{}"',
                              self, row_num, cell_num, re_pattern, result.string)
                    matches.append("cell({},{})".format(row_num, cell_num))
                    break

        return matches

    @override(ExcelSheet)
    def set_cell_data(self, row_idx: int, col_idx: int, item: Any):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_item = super().set_cell_data(row_idx, col_idx, item)

        if self._anim_mode_shared and orig_item != item:
            self.signals.sig_cell_changed.emit(row_idx, col_idx)

    @override(ExcelSheet)
    def set_row(self, row_idx: int, row_data: List[object]):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_row = super().set_row(row_idx, row_data)

        if self._anim_mode_shared and orig_row != row_data:
            self.signals.sig_row_subset_changed.emit(row_idx, 0, self._num_cols - 1)

    @override(ExcelSheet)
    def set_col(self, col_idx: int, col_data: List[object]):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_col = super().set_col(col_idx, col_data)

        if self._anim_mode_shared and orig_col != list(col_data):
            self.signals.sig_col_subset_changed.emit(0, self._num_rows - 1, col_idx)

    @override(ExcelSheet)
    def set_col_width(self, col_idx: int, width: int = ExcelSheet.DEFAULT_COL_WIDTH):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_width = super().set_col_width(col_idx, width)

        if self._anim_mode_shared and orig_width != width:
            self.signals.sig_col_width_changed.emit(col_idx, width)

    @override(ExcelSheet)
    def set_index_style(self, style: str):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_style = super().set_index_style(style)
        if self._anim_mode_shared and orig_style != style:
            self.signals.sig_col_idx_style_changed.emit(self._index_style.value)

    @override(ExcelSheet)
    def add_row(self, row_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_rows = self.num_rows
        row_idx = super().add_row(row_idx)
        assert row_idx is not None
        if self._anim_mode_shared and orig_rows != self.num_rows:
            self.signals.sig_rows_added.emit(row_idx, 1)

    @override(ExcelSheet)
    def add_rows(self, num_rows: int = ExcelSheet.NUM_ROWS_ADD_DEL, row_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_rows = self.num_rows
        row_idx = super().add_rows(num_rows, row_idx)
        assert row_idx is not None
        if self._anim_mode_shared and orig_rows != self.num_rows:
            self.signals.sig_rows_added.emit(row_idx, num_rows)

    @override(ExcelSheet)
    def delete_row(self, row_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_rows = self.num_rows
        row_idx = super().delete_row(row_idx)
        assert row_idx is not None
        if self._anim_mode_shared and orig_rows != self.num_rows:
            self.signals.sig_rows_added.emit(row_idx, -1)

    @override(ExcelSheet)
    def delete_rows(self, num_rows: int = ExcelSheet.NUM_ROWS_ADD_DEL, row_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_rows = self.num_rows
        row_idx = super().delete_rows(num_rows, row_idx)
        assert row_idx is not None
        if self._anim_mode_shared and orig_rows != self.num_rows:
            self.signals.sig_rows_added.emit(row_idx, -1 * num_rows)

    @override(ExcelSheet)
    def add_col(self, col_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_cols = self.num_cols
        col_idx = super().add_col(col_idx)
        assert col_idx is not None
        if self._anim_mode_shared and orig_cols != self.num_cols:
            self.signals.sig_cols_added.emit(col_idx, 1)

    @override(ExcelSheet)
    def add_cols(self, num_cols: int = ExcelSheet.NUM_COLS_ADD_DEL, col_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_cols = self.num_cols
        col_idx = super().add_cols(num_cols, col_idx)
        assert col_idx is not None
        if self._anim_mode_shared and orig_cols != self.num_cols:
            self.signals.sig_cols_added.emit(col_idx, num_cols)

    @override(ExcelSheet)
    def delete_col(self, col_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_cols = self.num_cols
        col_idx = super().delete_col(col_idx)
        assert col_idx is not None
        if self._anim_mode_shared and orig_cols != self.num_cols:
            self.signals.sig_cols_added.emit(col_idx, -1)

    @override(ExcelSheet)
    def delete_cols(self, num_cols: int = ExcelSheet.NUM_COLS_ADD_DEL, col_idx: int = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        orig_cols = self.num_cols
        col_idx = super().delete_cols(num_cols, col_idx)
        assert col_idx is not None
        if self._anim_mode_shared and orig_cols != self.num_cols:
            self.signals.sig_cols_added.emit(col_idx, -1 * num_cols)

    @override(ExcelSheet)
    def transpose(self):
        """
        Executes the super method and then emits signal to front-end.
        """
        super().transpose()
        if self._anim_mode_shared:
            self.signals.sig_full_sheet_changed.emit()

    @override(ExcelSheet)
    def clear(self):
        """
        Executes the super method and then emits signal to front-end.
        """
        super().clear()
        if self._anim_mode_shared:
            self.signals.sig_full_sheet_changed.emit()

    @override(ExcelSheet)
    def set_col_name(self, col_idx: Either[str, int], name: str):
        """
        Executes the super method and then emits signal to front-end.
        """
        super().set_col_name(col_idx, name)
        if self._anim_mode_shared:
            self.signals.sig_col_name_changed.emit(col_idx, name)

    @override(ExcelSheet)
    def del_col_name(self, name: str = None, col_idx: int = None, emit: bool = True):
        """
        Executes the super method and then emits signal to front-end.
        """
        indeces = super().del_col_name(name, col_idx, emit)
        if indeces is not None and emit and self._anim_mode_shared:
            xls_idx, name_col_idx = indeces
            self.signals.sig_col_name_changed.emit(name_col_idx, xls_idx)
            return xls_idx
        return None

    @override(ExcelSheet)
    def set_data(self, data: ExcelSheet or TablePart or int or float or str or tuple or list):
        """
        Executes the super method and then emits signal to front-end.
        """
        super().set_data(data)
        if not isinstance(data, TablePart) and self._anim_mode_shared:
            self.signals.sig_full_sheet_changed.emit()

    @override(ExcelSheet)
    def read_excel(self, xls_file: str, xls_sheet: str, xls_range: str, accept_empty_cells: bool = False):
        """
        Executes the super method and then emits signal to front-end.
        """
        super().read_excel(xls_file, xls_sheet, xls_range, accept_empty_cells=accept_empty_cells)
        if self._anim_mode_shared:
            self.signals.sig_full_sheet_changed.emit()

    @override(ExcelSheet)
    def copyfrom(self, other_sheet: ExcelSheet) -> ExcelSheet:
        """
        Executes the super method and then emits signal to front-end.
        """
        excel_sheet = super().copyfrom(other_sheet)
        assert excel_sheet is self  # ensure what is being returned is self
        if self._anim_mode_shared:
            self.signals.sig_full_sheet_changed.emit()

        return self

    @override(ExcelSheet)
    def fill(self, callback: FillCallable, cell_range: InCellRange = None):
        """
        Executes the super method and then emits signal to front-end.
        """
        fill_type, row_idx, col_idx = super().fill(callback, cell_range)

        if self._anim_mode_shared:

            if fill_type == SheetFillType.full:
                self.signals.sig_full_sheet_changed.emit()

            elif fill_type == SheetFillType.cell:
                self.signals.sig_cell_changed.emit(row_idx, col_idx)

            elif fill_type == SheetFillType.row:
                self.signals.sig_row_subset_changed.emit(row_idx, col_idx[0], col_idx[-1])

            elif fill_type == SheetFillType.col:
                self.signals.sig_col_subset_changed.emit(row_idx[0], row_idx[-1], col_idx)

            else:  # SheetFillType.sheet
                self.signals.sig_sheet_subset_changed.emit(row_idx[0], row_idx[-1], col_idx[0], col_idx[-1])

    @override(ExcelSheet)
    def __setitem__(self, cell_range: InCellRange, val: Either[ExcelSheet, Any]) -> SheetSetItemIndexType:
        """
        Executes the super method and then emits signal to front-end.
        """
        index_combo_type, row, col = super().__setitem__(cell_range, val)

        if self._anim_mode_shared:

            if index_combo_type == SheetSetItemIndexType.int_int:
                self.signals.sig_cell_changed.emit(row, col)

            elif index_combo_type == SheetSetItemIndexType.int_slice:
                self.signals.sig_row_subset_changed.emit(row, col[0], col[1])

            elif index_combo_type == SheetSetItemIndexType.slice_int:
                self.signals.sig_col_subset_changed.emit(row[0], row[1], col)

            else:  # SheetSetItemIndexType.slice_slice:
                self.signals.sig_sheet_subset_changed.emit(row[0], row[1], col[0], col[1])

    # prototype compatibility adjustments:
    NumCols = prototype_compat_property_alias(ExcelSheet.num_cols, 'NumCols')
    NumRows = prototype_compat_property_alias(ExcelSheet.num_rows, 'NumRows')

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SEARCHING_API_EXTEND = (ExcelSheet.named_cols, ExcelSheet.index_style)
    META_AUTO_SCRIPTING_API_EXTEND = (
        ExcelSheet.sheet_data, ExcelSheet.get_sheet_data,
        ExcelSheet.num_rows, ExcelSheet.get_rows, ExcelSheet.set_rows,
        ExcelSheet.num_cols, ExcelSheet.get_cols, ExcelSheet.set_cols,
        ExcelSheet.named_cols, ExcelSheet.get_named_cols,
        ExcelSheet.col_widths, ExcelSheet.get_col_widths,
        ExcelSheet.index_style, ExcelSheet.get_index_style, set_index_style,
        fill, ExcelSheet.find, ExcelSheet.repr_data, transpose,
        add_col, add_cols, ExcelSheet.col, del_col_name, delete_col, delete_cols, set_col_name,
        add_row, add_rows, ExcelSheet.row, delete_row, delete_rows,
        clear, ExcelSheet.resize, set_data, copyfrom, read_excel, ExcelSheet.write_excel
    )

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(BasePart)
    def _receive_edited_snapshot(self, submitted_data: Dict[str, Any], order: List[str] = None):
        """Reset the Sheet Part data and signal the Sheet widget to update"""
        super()._receive_edited_snapshot(submitted_data, order=order)

        # Replace sheet the data and drop column names
        self.set_data(submitted_data['sheet_data'])

        # Update the customized column names
        self._named_cols = submitted_data['custom_col_names']

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        self._sheet_data = part_content[SpKeys.DATA]

        if ori_data.schema_version < OriSchemaEnum.version_2_1:
            # always pickled:
            # That has already been processed in the file_util_prototype.py
            pass

        else:
            # starting with 2.1, data is pickled when necessary per part_content[SpKeys.PICKLED_CELLS]
            if ori_data.schema_version == OriSchemaEnum.version_3:
                # always repr rather than json:
                self._sheet_data = eval(part_content[SpKeys.DATA])

            self.__unpickle_ori_cells(part_content[SpKeys.PICKLED_CELLS])

        self._col_widths = part_content[SpKeys.COL_WIDTHS]
        self._named_cols = part_content[SpKeys.NAMED_COLS]
        self._num_cols = part_content[SpKeys.NUM_COLS]
        self._num_rows = part_content[SpKeys.NUM_ROWS]
        self._index_style = SheetIndexStyleEnum[part_content[SpKeys.INDEX_STYLE].lower()]

        # Replace any empty cells by default value:
        for row in range(self._num_rows):
            for col in range(self._num_cols):
                if self._sheet_data[row][col] == '':
                    self._sheet_data[row][col] = self.DEFAULT_CELL_VAL

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)

        pickled_cells = None
        if context == OriContextEnum.save_load:
            ori_sheet_data_json, pickled_cells = self.__get_ori_def_for_saving()
        else:
            ori_sheet_data_json = self._sheet_data

        sheet_ori_def = {
            SpKeys.DATA: ori_sheet_data_json,
            SpKeys.PICKLED_CELLS: pickled_cells,
            SpKeys.COL_WIDTHS: self._col_widths,
            SpKeys.NAMED_COLS: self._named_cols,
            SpKeys.NUM_COLS: self._num_cols,
            SpKeys.NUM_ROWS: self._num_rows,
            SpKeys.INDEX_STYLE: self._index_style.name,
        }

        ori_def[CpKeys.CONTENT].update(sheet_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        if snapshot_slow is not None:
            # data may be huge, so create an MD5 digest of it:
            try:
                val = pickle.dumps(self._sheet_data)
            except:
                # At least one of the cells is bad - cannot be pickled.
                # yes, need to loop over every cell and test; first clone the sheet data
                ori_sheet_data = [row.copy() for row in self._sheet_data]
                for row_index, row in enumerate(ori_sheet_data):
                    for col_index, value in enumerate(row):
                        safe_val, is_pickle_successful = get_pickled_str(value, SaveErrorLocationEnum.sheet_part)
                        if not is_pickle_successful:
                            ori_sheet_data[row_index][col_index] = safe_val

                # At this point, the pickle has to succeed because every cell has been checked.
                val = pickle.dumps(ori_sheet_data)

            md5_sheet_data = md5(val).digest()
            snapshot_slow.update({
                SpKeys.DATA: md5_sheet_data,
            })

        snapshot.update({
            SpKeys.COL_WIDTHS: self._col_widths,
            SpKeys.NAMED_COLS: self._named_cols,
            SpKeys.NUM_COLS: self._num_cols,
            SpKeys.NUM_ROWS: self._num_rows,
            SpKeys.INDEX_STYLE: self._index_style
        })

    @override(IOriSerializable)
    def _check_ori_diffs(self, other_ori: Decl.SheetPart, diffs: Dict[str, Any], tol_float: float):
        BasePart._check_ori_diffs(self, other_ori, diffs, tol_float)

        # cell values of common cells
        data = self._sheet_data
        for row_index, (row_data, other_row_data) in enumerate(zip(data, other_ori._sheet_data)):
            if row_data != other_row_data:
                for col_index, (cell, other_cell) in enumerate(zip(row_data, other_row_data)):
                    diff = check_diff_val(cell, other_cell, tol_value=tol_float)
                    if diff is not None:
                        diffs['data[{},{}]'.format(row_index, col_index)] = diff

    @override(BasePart)
    def _has_ori_changes_slow(self, baseline: JsonObj, last_get: JsonObj) -> bool:
        return baseline[SpKeys.DATA] != last_get[SpKeys.DATA]

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __unpickle_ori_cells(self, pickled_cells: List[Tuple[int, int]]):
        if pickled_cells is not None:
            for rindex, cindex in pickled_cells:
                pickled_data = self._sheet_data[rindex][cindex]
                unpickled = pickle.loads(pickle_from_str(pickled_data))
                self._sheet_data[rindex][cindex] = unpickled

    def __get_ori_def_for_saving(self):
        """
        Sheet part data cells can contain arbitrary Python objects, so careful handling is required when
        the context=save
        """
        pickled_cells = []

        needs_pickling, unjsoned_data = check_needs_pickling(self._sheet_data)
        if needs_pickling:
            if unjsoned_data is None:
                # some cells could not be jsonified, they will have to be pickled
                # create shallow copy of each row:
                ori_sheet_data_json = [row.copy() for row in self._sheet_data]
                for row_index, row in enumerate(ori_sheet_data_json):
                    for col_index, orig_value in enumerate(row):
                        try:
                            json.dumps(orig_value)
                        except TypeError:
                            ori_sheet_data_json[row_index][col_index] = self.__pickle_value(
                                orig_value, pickled_cells, (row_index, col_index))

            else:
                # The data could be json'd but if any cells contained a dictionary (anywhere in the object, say a
                # list of list with one of the items a dict), then special treatment is needed because JSON format
                # only supports string keys. So unjsonify the data, and if the data is same as original, we're good;
                # else loop over the two data structures (the original sheet data and the unjsonified data) to find
                # the ones that are not equal value; pickle those.
                # assert unjsoned_data != self._sheet_data
                # create shallow copy of each row:
                ori_sheet_data_json = [row.copy() for row in self._sheet_data]
                for row_index, (orig_row, unj_row) in enumerate(zip(ori_sheet_data_json, unjsoned_data)):
                    for col_index, (orig_value, unj_value) in enumerate(zip(orig_row, unj_row)):
                        if orig_value != unj_value:
                            ori_sheet_data_json[row_index][col_index] = self.__pickle_value(
                                orig_value, pickled_cells, (row_index, col_index))

        else:
            ori_sheet_data_json = self._sheet_data

        return ori_sheet_data_json, pickled_cells

    def __pickle_value(self, orig_value: Any, pickled_cells: List[Tuple[int, int]], cell_id: Tuple[int, int]) -> bytes:
        """
        Pickle a Python object representing the original value stored in the sheet part.
        :param orig_value: value to pickle
        :param pickled_cells: container in which to put the cell_id if the object was succesfully pickled
        :return: the pickle, or a replacement (text) if the object could not be pickled
        """
        safe_val, is_pickle_successful = get_pickled_str(orig_value, SaveErrorLocationEnum.sheet_part)
        if is_pickle_successful:
            pickled_cells.append(cell_id)
        return safe_val


# Add this part to the global part type/class lookup dictionary
register_new_part_type(SheetPart, SpKeys.PART_TYPE_SHEET)
