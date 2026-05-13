# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: It represents the data returned from the SQL Part.

It is not the dataset directly returned from the sqlite query. Instead, it supports data manipulation in a pythonic
way. Tuples and slicing techniques are used to retrieve subsets of the data from this dataset.


Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
import sqlite3

# [3. local]
from ..core.typing import AnnotationDeclarations
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ..core.typing import Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SqlDataSet'
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    SqlDataSet = 'SqlDataSet'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

RangeDef = Tuple[Either[int, slice]]


class SqlDataSet:
    """
    Represent an execution outcome of a SQLPart.

    The rational behind this class is that the result of a SQL execution can be a table name or the actual result set.
    The former is used for chaining SQL parts; the latter delivering the data to other business logic.

    Both performance and usability of this class must be taken into consideration. The result set from the underlying
    database is a list of tuples, which are immutable. So, the result set is not fully mutable. By default, it remains
    immutable, because we want to avoid paying a price for converting the immutable result set to a mutable one.
    Immutable result sets usually satisfy the vast majority of use cases.

    The first attempt to change an immutable result will change it to a mutable one. It will remain mutable for the
    rest of its life.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    MutableRecord = List[Any]
    ImmutableRecord = Tuple[Any]
    Record = Either[MutableRecord, ImmutableRecord]

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, table_name: str, sql_statement: str, db_connection: sqlite3.Connection,
                 data: List[Record] = None, col_name_index: Dict[str, int] = None,
                 col_index_name: Dict[int, str] = None):
        """
        The result set is produced on demand because the intermediate SQLPart instances only need
        the __table_name.

        Note: It may look strange to pass col_name_index and col_index_name as arguments. But they are necessary
        because the header info (column names) of the data set and its actual data are maintained separately.
        Alternatively, the header info could be the first row of the data set - that would make the data
        manipulation difficult because you would always have to exclude the first row whenever you want to
        manipulate (for example, slice) the data set.

        :param table_name: A SQL statement.
        :param sql_statement: A SQL statement.
        :param data: used when a SqlDataSet's data is used to construct another SqlDataSet.
        :param col_name_index: A dict used to look up the index by name
        :param col_index_name: A dict used to look up the name by index
        all other parameters are ignored.
        """
        # The correct way of using the default values:
        # See http://effbot.org/zone/default-values.htm
        if col_name_index is None:
            col_name_index = dict()
        if col_index_name is None:
            col_index_name = dict()

        self.__num_rows = 0
        self.__num_cols = 0
        self.__col_name_index_dict = dict()
        self.__col_index_name_dict = dict()

        self.__table_name = table_name
        self.__sql_statement = sql_statement
        self.__db_connection = db_connection

        self.__is_mutable = False
        self.__data = None
        if data is not None:
            self.__data = data
            rows = len(data)
            if rows > 0:
                if type(data[0]) == list:
                    self.__is_mutable = True

            cols = 0 if rows == 0 else len(data[0])
            self.__num_rows = rows
            self.__num_cols = cols
            self.__col_name_index_dict = col_name_index
            self.__col_index_name_dict = col_index_name

        # If data is None, self.__data will be constructed on demand.
        pass  # so Code -> Reformat leaves previous comment alone

    def get_is_mutable(self) -> bool:
        """
        Describes whether the data set is mutable.
        :return: Returns True after the first attempt to change any records; False by default
        """
        return self.__is_mutable

    def get_table_name(self) -> str:
        """Get the name of the dynamically created table."""
        return self.__table_name

    def get_records(self) -> List[Record]:
        """
        Gets a list of all the records.

        When the "is_mutable" property is True, the List[Tuple] is returned; otherwise, the List[List]

        :return: All the records
        """
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        return self.__data

    def get_value(self) -> Any:
        """If the result of SQL query is 1 row, 1 column, get it. Else, raises RuntimeError."""
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        if self.__num_cols != 1 or self.__num_rows != 1:
            msg = "This dataset is ({} rows x {} cols), get_value() only defined for 1x1"
            raise RuntimeError(msg.format(self.__num_rows, self.__num_cols))

        return self.__data[0][0]

    def get_column(self, index: Either[int, str]) -> List[Any]:
        """Get the column at given index. If the index is a string, it must be a valid column name."""
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        if type(index) == str:
            col = self.__col_name_index_dict[index]
        else:
            assert type(index) == int
            col = index

        return [row_record[col] for row_record in self.__data]

    def get_num_columns(self) -> int:
        """
        Get the number of columns in the results. Each record is assume to have same number of fields, so this
        is taken from the first record. If there are no records, returns 0.
        """
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None
        return self.__num_cols

    def get_column_names(self) -> List[str]:
        """
        Get a list of the column names.
        :return: A list of column names for this table.
        """
        return list(self.__col_index_name_dict.values())

    def iter_cells(self) -> Stream[Any]:
        """Returns an iterator which supports iterating over the entire results set."""
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        for row in self.__data:
            for cell in row:
                yield cell

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    is_mutable = property(get_is_mutable)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    def __contains__(self, item: Any) -> bool:
        """
        Checks if a cell value is in the data set.

        :param item: The cell value in the data grid.
        :returns: True if the value exists.
        """
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        for row_record in self.__data:
            if item in row_record:
                return True

        return False

    def __eq__(self, other: Either[Decl.SqlDataSet, Record]) -> bool:
        """
        Checks if this object is equal to the other object.

        :param other: The other object.
        :returns: True if they are equal.
        """
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        # can't be equal if they don't have same number of rows:
        if len(self.__data) != len(other):
            return False

        for self_row, other_row in zip(self.__data, other):
            if len(self_row) != len(other_row):
                return False
            for cell1, cell2 in zip(self_row, other_row):
                if cell1 != cell2:
                    return False

        return True

    def __ne__(self, other) -> bool:
        """
        Checks if this object is not equal to the other object.

        :param other: The other object.
        :returns: True if they are not equal.
        """
        return not (self == other)

    def __getitem__(self, index: Either[int, str, RangeDef]) -> Either[Any, Record, Decl.SqlDataSet]:
        """
        Get a subset out of this data set. The types of the parameter vary, so do those of the return value.

        Examples:

                    Sample data of this instance
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      11      12      13      14
                    20      21      22      23      24
                    30      31      32      33      34
                    40      41      42      43      44

        =============================================================================================
        index: 0, meaning row
        return: ('00', '01', '02', '03', '04')

        =============================================================================================
        index: slice(1, 5, 2), meaning the row index 1 and 3
        return: [('10', '11', '12', '13', '14'), ('30', '31', '32', '33', '34')]

        =============================================================================================
        index: 'Col0', meaning column
        return: ['00', '10', '20', '30', '40']

        =============================================================================================
        index: (0, 0), meaning a cell
        return: '00'

        =============================================================================================
        index: (1, slice(1, 5, 2)), meaning the 2nd row and the columns covered by the slice
        return: ('11', '13')

        =============================================================================================
        index: (slice(1, 5, 2), 1), meaning the 2nd column and the rows covered by the slice
        return: ['11', '31']

        =============================================================================================
        index: (slice(1, 5, 2), slice(1, 5, 2)), meaning the rows and columns covered by the slices
        return: a new SqlDateSet instance that represents [('11', '13'), ('31', '33')], immutable
        """

        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        if isinstance(index, str):
            # Design decision: When index is a str, we interpret that as column name and return whole column.
            return self.get_column(index)

        if isinstance(index, int):
            # It's 2D. Return the whole row.
            return self.__data[index]

        if isinstance(index, slice):
            # Design decision: When index is a slice, we return the rows indicated by the slice
            return self.__data[index]

        if not isinstance(index, tuple):
            raise TypeError('Invalid type ({}) for index, must be an integer or a pair'.format(type(index)))

        # Index is a tuple: extract the row and the col.
        row, col = index

        if type(row) not in (int, slice):
            raise TypeError('Invalid type ({}) for first "index", must be int or slice'.format(type(row)))
        if type(col) not in (int, slice):
            raise TypeError('Invalid type ({}) for second "index", must be int or slice'.format(type(col)))

        # First handle the case where row is integer:
        if isinstance(row, int):
            if type(col) == int:
                return self.__data[row][col]

            if isinstance(col, slice):
                # One row, a slice of columns
                return self.__data[row][col]

            raise TypeError('Invalid type ({}) for second "index", must be int or slice'.format(type(col)))

        if not isinstance(row, slice):
            raise TypeError('Invalid type ({}) for first "index", must be int or slice'.format(type(row)))

        # Row is a slice; of col is int, then slice of rows in given column:
        if isinstance(col, int):
            return [row_record[col] for row_record in self.__data[row]]

        # Column must be a slice:
        if not isinstance(col, slice):
            raise TypeError('Invalid type ({}) for second "index", must be int or slice'.format(type(col)))

        # Only thing left is a block of cells
        # Construct new dicts in order to construct a new SqlDataSet
        new_col_name_index_dict = dict()
        new_col_index_name_dict = dict()
        new_index = 0
        for colIdx in range(self.__num_cols)[col]:
            new_col_name_index_dict[self.__col_index_name_dict[colIdx]] = new_index
            new_col_index_name_dict[new_index] = self.__col_index_name_dict[colIdx]
            new_index += 1

        new_sql_data_set = SqlDataSet(self.__table_name, self.__sql_statement, self.__db_connection,
                                      [row_record[col] for row_record in self.__data[row]],
                                      new_col_name_index_dict, new_col_index_name_dict)

        return new_sql_data_set

    def __setitem__(self, index: RangeDef, val: Any):
        """
        Sets a single value or another SqlDataSet instance to this SqlDataSet instance.

        Once this function is called, this SqlDataSet instance will be mutable for the rest of its life.

        Examples:

                    Sample data of this instance
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      11      12      13      14
                    20      21      22      23      24
                    30      31      32      33      34
                    40      41      42      43      44

        =============================================================================================
        index: (0), meaning a row
        val: 'Yes'
        result:
                            Col0    Col1    Col2    Col3    Col4
                            -------------------------------------
                            Yes     Yes     Yes     Yes     Yes
                            10      11      12      13      14
                            20      21      22      23      24
                            30      31      32      33      34
                            40      41      42      43      44

        val: another SqlDataSet
                            Col0    Col1    Col2    Col3    Col4
                            -------------------------------------
                            00a     01a     02a     03a     04a
                            10a     11a     12a     13a     14a
                            20a     21a     22a     23a     24a
                            30a     31a     32a     33a     34a
                            40a     41a     42a     43a     44a
        result:
                            Col0    Col1    Col2    Col3    Col4
                            -------------------------------------
                            00a     01a     02a     03a     04a
                            10      11      12      13      14
                            20      21      22      23      24
                            30      31      32      33      34
                            40      41      42      43      44

        =============================================================================================
        index: (slice(1, 5, 2)), meaning the row index 1 and 3
        val: 'Yes'
        result:
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    Yes     Yes     Yes     Yes     Yes
                    20      21      22      23      24
                    Yes     Yes     Yes     Yes     Yes
                    40      41      42      43      44

        val: another SqlDataSet
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00a     01a     02a     03a     04a
                    10a     11a     12a     13a     14a
                    20a     21a     22a     23a     24a
                    30a     31a     32a     33a     34a
                    40a     41a     42a     43a     44a

        result:
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10a     11a     12a     13a     14a
                    20      21      22      23      24
                    30a     31a     32a     33a     34a
                    40      41      42      43      44

        =============================================================================================
        index: (0, 0), meaning a cell
        val: 'changed'
        result:
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    changed 01      02      03      04
                    10      11      12      13      14
                    20      21      22      23      24
                    30      31      32      33      34
                    40      41      42      43      44

        =============================================================================================
        index:  (1, slice(1, 5, 2)), meaning the 2nd row and the columns covered by the slice
        val: 'changed'
        result:
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      changed 12      changed 14
                    20      21      22      23      24
                    30      31      32      33      34
                    40      41      42      43      44

        =============================================================================================
        index:  (1, slice(1, 5, 2)), meaning the 2nd row and the columns covered by the slice
        val: another SqlDataSet
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00a     01a     02a     03a     04a
                    10a     11a     12a     13a     14a
                    20a     21a     22a     23a     24a
                    30a     31a     32a     33a     34a
                    40a     41a     42a     43a     44a

        result: The first row of the val, starting at 0 with step 2, is used to populate this object.
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      00a     12      02a     14
                    20      21      22      23      24
                    30      31      32      33      34
                    40      41      42      43      44

        =============================================================================================
        index:  (slice(1, 5, 2), 1), meaning the 2nd column and the rows covered by the slice
        val: 'changed'
        result:
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      changed 12      13      14
                    20      21      22      23      24
                    30      changed 32      33      34
                    40      41      42      43      44

        =============================================================================================
        index:  (slice(1, 5, 2), 1), meaning the 2nd column and the rows covered by the slice
        val: another SqlDataSet
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00a     01a     02a     03a     04a
                    10a     11a     12a     13a     14a
                    20a     21a     22a     23a     24a
                    30a     31a     32a     33a     34a
                    40a     41a     42a     43a     44a

        result: The first column of the val, starting at 0 with step 2, is used to populate this object.
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      00a     12      02     14
                    20      21      22      23      24
                    30      20a     32      33      34
                    40      41      42      43      44

        =============================================================================================
        index: (slice(1, 5, 2), slice(1, 5, 2)), meaning the rows and columns covered by the slices
        val: 'changed'
        result:
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      changed 12      changed 14
                    20      21      22      23      24
                    30      changed 32      changed 34
                    40      41      42      43      44

        =============================================================================================
        index: (slice(1, 5, 2), slice(1, 5, 2)), meaning the rows and columns covered by the slices
        val: another SqlDataSet
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00a     01a     02a     03a     04a
                    10a     11a     12a     13a     14a
                    20a     21a     22a     23a     24a
                    30a     31a     32a     33a     34a
                    40a     41a     42a     43a     44a

        result: The rows and columns of the val, starting at 0 with step 2, is used to populate this object.
                    Col0    Col1    Col2    Col3    Col4
                    -------------------------------------
                    00      01      02      03      04
                    10      00a     12      02a     14
                    20      21      22      23      24
                    30      20a     32      22a     34
                    40      41      42      43      44
        """

        if self.__data is None:
            self.__get_data()

        assert self.__data is not None

        if not self.__is_mutable:
            # Not mutable yet, so make it mutable
            for i, rec in enumerate(self.__data):
                self.__data[i] = list(rec)

            self.__is_mutable = True

        if isinstance(index, int):
            # It's 2D. Set the whole row.
            if isinstance(val, SqlDataSet):
                for ci in range(self.__num_cols):
                    self.__data[index][ci] = val.__get_data()[0][ci]
            else:
                for ci in range(self.__num_cols):
                    self.__data[index][ci] = val
            return

        if isinstance(index, slice):
            # Design decision: When index is a slice, we set the rows indicated by the slice
            ro = 0 if index.start is None else index.start
            if isinstance(val, SqlDataSet):
                for ri in range(self.__num_rows)[index]:
                    for ci in range(self.__num_cols):
                        self.__data[ri][ci] = val.__get_data()[ri - ro][ci]
            else:
                for ri in range(self.__num_rows)[index]:
                    for ci in range(self.__num_cols):
                        self.__data[ri][ci] = val
            return

        row, col = index
        if type(row) not in (int, slice):
            raise TypeError('Invalid type ({}) for first index, must be an integer or a pair'.format(type(row)))
        if type(col) not in (int, slice):
            raise TypeError('Invalid type ({}) for second index, must be an integer or a pair'.format(type(col)))

        if isinstance(row, int):
            if isinstance(col, int):
                # One row, one column
                self.__data[row][col] = val
                return

            if not isinstance(col, slice):
                raise TypeError('Invalid type ({}) for second "index", must be int or slice'.format(type(col)))

            # One row, a slice of columns
            co = 0 if col.start is None else col.start
            if isinstance(val, SqlDataSet):
                for ci in range(self.__num_cols)[col]:
                    self.__data[row][ci] = val.__get_data()[0][ci - co]
            else:
                for ci in range(self.__num_cols)[col]:
                    self.__data[row][ci] = val
            return

        if not isinstance(row, slice):
            raise TypeError('Invalid type ({}) for first "index", must be int or slice'.format(type(row)))

        ro = 0 if row.start is None else row.start
        if isinstance(col, int):
            # One column, a slice of row
            # ri for row index, and ci for column index.
            if isinstance(val, SqlDataSet):
                for ri in range(self.__num_rows)[row]:
                    self.__data[ri][col] = val.__get_data()[ri - ro][0]
            else:
                for ri in range(self.__num_rows)[row]:
                    self.__data[ri][col] = val
            return

        if not isinstance(col, slice):
            raise TypeError('Invalid type ({}) for second "index", must be int or slice'.format(type(col)))

        # A block of cells
        co = 0 if col.start is None else col.start
        if isinstance(val, SqlDataSet):
            for ri in range(self.__num_rows)[row]:
                for ci in range(self.__num_cols)[col]:
                    self.__data[ri][ci] = val.__get_data()[ri - ro][ci - co]
        else:
            for ri in range(self.__num_rows)[row]:
                for ci in range(self.__num_cols)[col]:
                    self.__data[ri][ci] = val

    def __iter__(self) -> Stream[Record]:
        """Iterate over each row (record)"""
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        for row in self.__data:
            yield row

    def __repr__(self):
        """The repr of the underlying raw data received from SQLite"""
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None
        return repr(self.__data)

    def __len__(self):
        """Returns the number of rows (records)"""
        # The design principle of this class is that it retrieves data only when necessary. So, we do it now because
        # we have to do it in order to evaluate the length.
        if self.__data is None:
            self.__get_data()
        assert self.__data is not None

        return self.__num_rows

    def __get_data(self) -> List[Record]:
        """
        Gets a list of all the records. It represents a result of a SQL Select query.

        When the "is_mutable" property is True, the List[Tuple] is returned; otherwise, the List[List]

        :return: All the records
        """
        if self.__data is not None:
            return self.__data

        cursor = self.__db_connection.execute(self.__sql_statement)
        self.__data = cursor.fetchall()

        self.__num_rows = len(self.__data)
        self.__num_cols = 0 if self.__num_rows == 0 else len(self.__data[0])

        for col_idx, col_info in enumerate(cursor.description):
            self.__col_name_index_dict[col_info[0]] = col_idx
            self.__col_index_name_dict[col_idx] = col_info[0]

        return self.__data
