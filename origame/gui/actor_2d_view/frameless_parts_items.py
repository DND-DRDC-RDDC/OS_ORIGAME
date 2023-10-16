# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: frameless_2ditems module for displaying graphics items in the 2d view

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import QRectF, QRect, Qt
from PyQt5.QtWidgets import QGraphicsObject, QGraphicsItem, QWidget, QStyleOptionGraphicsItem
from PyQt5.QtGui import QBrush, QColor, QPainter

# [3. local]
from ...core import override
from ...scenario.defn_parts import BasePart
from ...scenario import ori

from ..safe_slot import safe_slot

from .common import register_part_item_class, CustomItemEnum
from .part_box_item import FramelessPartItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'HubPartItem',
    'NodePartItem',
    'MultiplierPartItem',
]

log = logging.getLogger('system')

FRAMELESS_PART_TYPES = (ori.OriHubPartKeys.PART_TYPE_HUB,
                        ori.OriMultiplierPartKeys.PART_TYPE_MULTIPLIER,
                        ori.OriNodePartKeys.PART_TYPE_NODE)


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class HubPartItem(FramelessPartItem):
    """
    Hub part 'frameless' class
    """

    HUB_COLOR = QColor(118, 118, 118)
    INNER_OUTER_RATIO = 0.7

    @override(QGraphicsItem)
    def type(self) -> int:
        return CustomItemEnum.hub.value

    @override(FramelessPartItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        """
        Paints the contents of an item in local coordinates.
        :param painter something to perform draw operations on.
        :param option  style options for the item, such as its state, exposed area and its level-of-detail hints.
        :param widget  optional but may point to the actual widget being painted on, or None if painting off-screen.
        """
        painter.setPen(Qt.NoPen)
        painter.setRenderHint(QPainter.Antialiasing)
        offset_x = self._icon_size.width() / 2.0
        offset_y = self._icon_size.height() / 2.0
        painter.translate(offset_x, offset_y)

        painter.setBrush(QBrush(HubPartItem.HUB_COLOR))
        outer = QRectF(-self._icon_size.width() / 2.0,
                       -self._icon_size.height() / 2.0,
                       self._icon_size.width(),
                       self._icon_size.height())
        painter.drawEllipse(outer)

        painter.setBrush(QBrush(Qt.white))
        inner_size = self._icon_size * HubPartItem.INNER_OUTER_RATIO
        inner = QRectF(-inner_size.width() / 2.0,
                       -inner_size.height() / 2.0,
                       inner_size.width(),
                       inner_size.height())
        painter.drawEllipse(inner)


class NodePartItem(FramelessPartItem):
    """
    Node part 'frameless' class
    """

    NODE_COLOR = QColor(118, 118, 118)

    def __init__(self, part: BasePart, parent: QGraphicsObject = None):
        """
        :param part the BasePart of this graphics object.
        :param parent: the parent graphics object.
        """
        super().__init__(part, parent)

    @override(QGraphicsItem)
    def type(self) -> int:
        return CustomItemEnum.node.value

    @override(FramelessPartItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        """
        Paints the contents of an item in local coordinates.
        :param painter something to perform draw operations on.
        :param option  style options for the item, such as its state, exposed area and its level-of-detail hints.
        :param widget  optional but may point to the actual widget being painted on, or None if painting off-screen.
        """
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(NodePartItem.NODE_COLOR))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QRect(0, 0, self._icon_size.width(), self._icon_size.height()))


class MultiplierPartItem(FramelessPartItem):
    """
    Multiplier part 'frameless' class
    """
    MULTIPLIER_COLOR = QColor(118, 118, 118)
    TOTAL_RADIUS = 124.0
    OUTER_RADIUS = 70.0
    OUTER_DIAMETER = 140.0
    INNER_RADIUS = 40.0
    INNER_DIAMETER = 80.0
    HALF_STROKE_WIDTH = 15.0  # (OUTER_RADIUS - INNER_RADIUS) / 2
    STROKE_WIDTH = 30.0

    def __init__(self, part: BasePart, parent: QGraphicsObject = None):
        FramelessPartItem.__init__(self, part, parent)

    @override(QGraphicsItem)
    def type(self) -> int:
        return CustomItemEnum.multiplier.value

    @override(FramelessPartItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        """
        Paints the contents of an item in local coordinates.
        :param painter something to perform draw operations on.
        :param option  style options for the item, such as its state, exposed area and its level-of-detail hints.
        :param widget  optional but may point to the actual widget being painted on, or None if painting off-screen.
        """
        painter.setPen(Qt.NoPen)
        painter.setRenderHint(QPainter.Antialiasing)
        offset_x = self._icon_size.width() / 2.0
        offset_y = self._icon_size.height() / 2.0
        painter.translate(offset_x, offset_y)
        scale_factor = offset_x / MultiplierPartItem.TOTAL_RADIUS  # assuming the overall shape is a square
        painter.scale(scale_factor, scale_factor)

        # Draw the outer circle
        brush = QBrush(MultiplierPartItem.MULTIPLIER_COLOR)
        painter.setBrush(brush)
        outer = QRectF(-MultiplierPartItem.OUTER_RADIUS,
                       -MultiplierPartItem.OUTER_RADIUS,
                       MultiplierPartItem.OUTER_DIAMETER,
                       MultiplierPartItem.OUTER_DIAMETER)
        painter.drawEllipse(outer)

        # Draw the 8 horns on the outer circle
        num_of_horns = 8
        angle_to_rotate = 360.0 / num_of_horns
        for i in range(num_of_horns):
            one_circle = QRectF(-MultiplierPartItem.HALF_STROKE_WIDTH,
                                -MultiplierPartItem.TOTAL_RADIUS,
                                MultiplierPartItem.STROKE_WIDTH,
                                MultiplierPartItem.STROKE_WIDTH)
            one_rect = QRectF(-MultiplierPartItem.HALF_STROKE_WIDTH,
                              -MultiplierPartItem.TOTAL_RADIUS + MultiplierPartItem.HALF_STROKE_WIDTH,
                              MultiplierPartItem.STROKE_WIDTH,
                              MultiplierPartItem.TOTAL_RADIUS - MultiplierPartItem.INNER_RADIUS)
            painter.drawEllipse(one_circle)
            painter.drawRect(one_rect)
            painter.rotate(angle_to_rotate)

        # Draw the inner circle
        painter.setBrush(QBrush(Qt.white))
        inner = QRectF(-MultiplierPartItem.INNER_RADIUS,
                       -MultiplierPartItem.INNER_RADIUS,
                       MultiplierPartItem.INNER_DIAMETER,
                       MultiplierPartItem.INNER_DIAMETER)
        painter.drawEllipse(inner)

    def __on_exec_error_changed(self):
        if self._part.last_exec_error_info is not None:
            # Do not show error message: this will be done by caller (part or SimController)
            pass

    __slot_on_exec_error_changed = safe_slot(__on_exec_error_changed)


register_part_item_class(ori.OriHubPartKeys.PART_TYPE_HUB, HubPartItem)
register_part_item_class(ori.OriNodePartKeys.PART_TYPE_NODE, NodePartItem)
register_part_item_class(ori.OriMultiplierPartKeys.PART_TYPE_MULTIPLIER, MultiplierPartItem)
