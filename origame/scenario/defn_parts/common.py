# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Common classes, constants, functions, etc. specific to the back-end.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...core import override
from ...core.typing import AnnotationDeclarations
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'Size',
    'Position',
    'Vector',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    Position = 'Position'
    Vector = 'Vector'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class Size:
    """
    This class represents the size description of a Part frame.
    """

    def __init__(self, width: float, height: float, scale_3d: float = 1.0):
        # They are not in pixels.
        self._width = float(width)
        self._height = float(height)
        self._scale_3d = scale_3d or 1.0

    def get_height(self) -> float:
        """
        Get the height.
        """
        return self._height

    def set_height(self, value: float):
        """
        Set the height.
        :param value: The new height.
        """
        self._height = float(value)

    def get_width(self) -> float:
        """
        Get the width.
        """
        return self._width

    def set_width(self, value: float):
        """
        Set the width.
        :param value: The new width.
        """
        self._width = float(value)

    def get_scale_3d(self) -> float:
        """
        Get the 3D scale.
        """
        return self._scale_3d

    def set_scale_3d(self, value: float):
        """
        Set the 3D scale.
        :param value: The new 3D scale.
        """
        self._scale_3d = value

    height = property(get_height, set_height)
    width = property(get_width, set_width)
    scale_3d = property(get_scale_3d, set_scale_3d)

    def __str__(self):
        return "({}, {})".format(self._width, self._height)

    def __format__(self, format_spec):
        return "({}, {})".format(format(self._width, format_spec), format(self._height, format_spec))


class Vector:
    """
    This class represents a 2d vector in scenario coordinates, i.e. a difference
    between two points in space.

    Note that it is intentionally
    designed as immutable so there is no setter for a vector's coordinates. Rather,
    a new vector must be created, usually via an addition or subtraction of two
    vectors or positions and offsets.
    """

    @classmethod
    def from_tuple(cls: type, xy: Tuple[float, float]) -> Decl.Vector:
        """
        This function returns a new Vector instance constructed from the specified x/y tuple.
        :param xy: A tuple describing the x/y coordinates of a position to be created.
        :return: The new Vector instance.
        """
        return cls(xy[0], xy[1])

    def __init__(self, x: float = 0.0, y: float = 0.0):
        """
        :param x: x-coordinate of the part
        :param y: y-coordinate of the part
        """
        self._x = float(x)
        self._y = float(y)

    def get_x(self) -> float:
        """Get the x coord."""
        return self._x

    def get_y(self) -> float:
        """Get the y coord."""
        return self._y

    def copy(self) -> Decl.Vector:
        """Get a copy of this vector."""
        return Vector(self._x, self._y)

    def to_tuple(self) -> Tuple[float, float]:
        """Get a tuple-form of this vector."""
        return self.x, self.y

    def add(self, x: float, y: float) -> Decl.Vector:
        """Extend a vector. Returns a new instance."""
        return Vector(self._x + x, self._y + y)

    x = property(get_x)  # NO SETTER because self is immutable
    y = property(get_y)  # NO SETTER because self is immutable

    def __getitem__(self, item: int) -> float:
        """Support tuple-like access, self[0] or self[1]"""
        assert item in (0, 1)
        return self._x if item == 0 else self._y

    def __add__(self, vec: Decl.Vector) -> Decl.Vector:
        """Support self + vec"""
        return Vector(self._x + vec._x, self._y + vec._y)

    def __sub__(self, vec: Decl.Vector) -> Decl.Vector:
        """Support self - vec"""
        return Vector(self._x - vec._x, self._y - vec._y)

    def __neg__(self):
        """Support -self"""
        return Vector(-self._x, -self._y)

    def __str__(self):
        return str(self.to_tuple())

    def __format__(self, format_spec):
        """Support '{format_spec}'.format(self); format spec is applied to all coords."""
        return "({}, {})".format(format(self._x, format_spec), format(self._y, format_spec))

    def __eq__(self, other: Decl.Vector) -> bool:
        """Support self == other and self != other"""
        return self._x == other._x and self._y == other._y

    def __round__(self, n: int = None):
        """Support round(self, n) (returns a new Vector instance)"""
        return Vector(round(self._x, n), round(self._y, n))


class Position(Vector):
    """
    This class represents a 2d position in scenario coordinates. It is a kind of
    vector, in that it is a difference from (0, 0), the origin.
    """

    @override(Vector)
    def copy(self) -> Decl.Position:
        """Copy this position"""
        return Position(self._x, self._y)

    @override(Vector)
    def add(self, x: float, y: float) -> Decl.Position:
        """A position plus an offset is a position"""
        return Position(self._x + x, self._y + y)

    @override(Vector)
    def __add__(self, vec: Decl.Vector) -> Decl.Position:
        """A position plus a vector is a new position"""
        return Position(self._x + vec._x, self._y + vec._y)

    @override(Vector)
    def __sub__(self, vec: Decl.Vector) -> Either[Vector, Decl.Position]:
        """A position minus a vector is a new position; minus another position, it is a vector."""
        if vec.__class__.__name__ == 'Vector':
            return Position(self._x - vec._x, self._y - vec._y)
        else:
            pos = vec
            return Vector(self._x - pos._x, self._y - pos._y)

    def __round__(self, n: int = None):
        """Returns a new Position instance, with each coordinate rounded."""
        return Position(round(self._x, n), round(self._y, n))


class ExcelReadError(Exception):
    """
    Custom error class used for raising Sheet part exceptions. This exception represents an error condition where
    a sheet value, such a number of rows or columns is invalid.
    """
    pass


class ExcelWriteError(Exception):
    """
    Custom error class used for raising Sheet part exceptions. This exception represents an error condition where
    a sheet value, such a number of rows or columns is invalid for the current Sheet part.
    """
    pass
