# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Implements the Parent Actor Proxy Item class.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from math import atan, cos, tan

# [2. third-party]
from PyQt5.QtCore import Qt, QRectF, QPointF, QVariant
from PyQt5.QtWidgets import QWidget, QGraphicsProxyWidget, QGraphicsItem, QGraphicsObject
from PyQt5.QtWidgets import QStyleOptionGraphicsItem, QGraphicsRectItem, QGraphicsSceneMouseEvent
from PyQt5.QtGui import QColor, QBrush, QPainter, QPainterPath, QPen, QPolygonF

# [3. local]
from ...core import override
from ...core.typing import AnnotationDeclarations
from ...scenario.defn_parts import PartFrame, ActorPart, BasePart

from ..gui_utils import PART_ICON_COLORS, MARGIN_OF_SELECTED_PART, QTBUG_55918_OPACITY
from ..safe_slot import safe_slot

from .framed_part_widgets import ParentActorProxyWidget
from .common import ZLevelsEnum, CustomItemEnum, IInteractiveItem, EventStr
from .linking import LinkAnchorItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    'ParentActorProxyItem',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ParentActorProxyItem(IInteractiveItem, LinkAnchorItem):
    """
    A graphics item in the 2D scene that serves as a container for a ParentActorProxyWidget.
    """

    DRAGGABLE = True

    MARGIN = 0.5  # Distance from the embedded widget
    TRAPEZOID_DELTA = 20.0
    HIGHLIGHT_DELTA = 8.0
    COLOR_HIGHLIGHT = QColor(0, 255, 0, 255)  # Color for the selected part

    def __init__(self, actor_part: ActorPart):
        """
        Initializes brushes, calculates the painter path for the highlighting borders, and connects the signals from
        the actor_part
        :param actor_part: The actor part this item represents
        """
        IInteractiveItem.__init__(self)
        LinkAnchorItem.__init__(self)

        self.__part_item = None  # the frontend actor proxy widget

        # Flags
        self._set_flags_item_change_interactive()
        self._set_flags_item_change_link_anchor()
        assert self.flags() & (QGraphicsItem.ItemIsFocusable | QGraphicsItem.ItemIsSelectable | self.ItemIsMovable)
        assert self.flags() & QGraphicsItem.ItemSendsScenePositionChanges
        self.setAcceptHoverEvents(True)

        # Brushes (for filling shapes)
        self.__default_brush = QBrush(PART_ICON_COLORS['actor_proxy'], Qt.SolidPattern)
        self.__highlight_brush = QBrush(ParentActorProxyItem.COLOR_HIGHLIGHT, Qt.SolidPattern)

        # Bounding rectangles on the widget allow the size of the actor proxy to change
        # when the name changes and apply a highlight around it
        pen = QPen(Qt.NoPen)
        self.__margin = ParentActorProxyItem.MARGIN
        self.__widget_rect = QGraphicsRectItem(self)
        self.__widget_rect.setPen(pen)
        self.__widget_rect.setZValue(ZLevelsEnum.part_item_border)
        self.__widget_rect.setVisible(False)

        self.__actor_proxy_path = QPainterPath()
        self.__highlight_path = QPainterPath()
        self.__bounding_rect_path = QPainterPath()

        self.__highlight_dx_top = None
        self.__highlight_dx_bottom = None

        self.__calculate_painter_path()

        self.__part = actor_part
        self.set_frame(actor_part.part_frame)
        self.prepareGeometryChange()
        widget = ParentActorProxyWidget(actor_part)
        self.__part_item = QGraphicsProxyWidget(self)
        self.__part_item.setWidget(widget)
        self.__part_item.setZValue(ZLevelsEnum.parent_proxy)
        self.__part_item.setOpacity(QTBUG_55918_OPACITY)  # QTBUG-55918

        self.__part_item.geometryChanged.connect(self.slot_on_size_changed)

        self.__part.signals.sig_proxy_pos_changed.connect(self.slot_set_scene_pos_from_scenario)
        pos_x, pos_y = self.__part.proxy_pos
        self.set_scene_pos_from_scenario(pos_x, pos_y)

        self.on_size_changed()

    @override(QGraphicsItem)
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, new_value: QVariant) -> QVariant:
        """Call 'itemChange' from every base class"""
        LinkAnchorItem.itemChange(self, change, new_value)
        return IInteractiveItem.itemChange(self, change, new_value)

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHints(QPainter.TextAntialiasing | QPainter.Antialiasing | QPainter.HighQualityAntialiasing)
        painter.setPen(Qt.NoPen)

        if self._highlighted:
            painter.setBrush(self.__highlight_brush)
            painter.drawPath(self.__highlight_path)

        painter.setBrush(self.__default_brush)
        painter.drawPath(self.__actor_proxy_path)

    @override(QGraphicsObject)
    def type(self) -> int:
        return CustomItemEnum.parent_proxy.value

    @override(QGraphicsObject)
    def boundingRect(self) -> QRectF:
        return self.__bounding_rect_path.boundingRect()

    @override(LinkAnchorItem)
    def get_link_boundary_rect(self) -> QRectF:
        return self.sceneBoundingRect()

    @override(QGraphicsObject)
    def shape(self) -> QPainterPath:
        return self.__actor_proxy_path

    @override(QGraphicsObject)
    def mousePressEvent(self, evt: QGraphicsSceneMouseEvent):
        log.debug("Parent proxy got mouse press: {}", EventStr(evt))
        super().mousePressEvent(evt)

    @override(QGraphicsObject)
    def mouseReleaseEvent(self, evt: QGraphicsSceneMouseEvent):
        log.debug("Parent proxy got mouse release")
        super().mouseReleaseEvent(evt)

    @override(IInteractiveItem)
    def get_scenario_object(self) -> BasePart:
        return self.__part

    def get_name(self) -> str:
        """
        Returns the name of this proxy item
        """
        return self.__part_item.widget().ui_parent_actor_proxy.name_label.text()

    def get_part_frame(self) -> PartFrame:
        """
        Returns the proxied part's (scenario) frame object.
        """
        return self.__part.part_frame

    def on_size_changed(self):
        """
        Slot called when the item changes its size or is selected.
        """
        self.prepareGeometryChange()
        self.__part_item.widget().ui_parent_actor_proxy.name_label.adjustSize()
        widget_rect = QRectF(self.__part_item.boundingRect())

        self.__widget_rect.setRect(widget_rect)
        self.__calculate_highlight_xmargins(self.__widget_rect.boundingRect())
        self.__calculate_painter_path()

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_size_changed = safe_slot(on_size_changed)
    slot_set_scene_pos_from_scenario = safe_slot(IInteractiveItem.set_scene_pos_from_scenario)

    name = property(get_name)
    part_frame = property(get_part_frame)
    link_boundary_rect = property(get_link_boundary_rect)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IInteractiveItem)
    def _highlighting_changed(self):
        self.prepareGeometryChange()
        if self.__part_item is not None:

            if self._highlighted:
                self.__widget_rect.setVisible(True)
                self.__margin = ParentActorProxyItem.MARGIN + MARGIN_OF_SELECTED_PART
                self.setZValue(ZLevelsEnum.child_part_selected)
            else:
                self.__widget_rect.setVisible(False)
                self.__margin = ParentActorProxyItem.MARGIN
                self.setZValue(ZLevelsEnum.child_part)

            self.on_size_changed()

    # --------------------------- instance _PROTECTED SLOTS ----------------------------

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __calculate_painter_path(self):
        """
        Calculates the path to draw whenever the end-points change.
        """
        self.prepareGeometryChange()
        self.__actor_proxy_path = QPainterPath()
        self.__highlight_path = QPainterPath()
        self.__bounding_rect_path = QPainterPath()

        trapezoid_poly = self.__trapezoid_poly()

        if self._highlighted:
            highlight_poly = self.__trapezoid_poly(get_highlight=True)
            self.__highlight_path.addPolygon(highlight_poly)
            self.__bounding_rect_path.addPolygon(highlight_poly)
        else:
            self.__bounding_rect_path.addPolygon(trapezoid_poly)

        # Painter paths
        self.__actor_proxy_path.addPolygon(trapezoid_poly)
        self.__actor_proxy_path.closeSubpath()

    def __trapezoid_poly(self, get_highlight: bool = False) -> QPolygonF:
        """
        Calculates the four corners of a trapezoid.

        Uses the widget's bounding rectangle as the base and extends the two lower corners out by a delta amount
        to create the trapezoid shape.
        :param get_highlight: a flag that indicates whether to return the highlighted trapezoid or non-highlighted one.
        :returns a trapezoid shape.
        """

        bounding_rect = self.__widget_rect.boundingRect()
        trapezoid_delta = ParentActorProxyItem.TRAPEZOID_DELTA

        # Left side
        trap_top_left = bounding_rect.topLeft()
        rect_bottom_left = bounding_rect.bottomLeft()
        x_left = rect_bottom_left.x() - trapezoid_delta
        y_left = rect_bottom_left.y()
        trap_bottom_left = QPointF(x_left, y_left)

        # Right side
        trap_top_right = bounding_rect.topRight()
        rect_bottom_right = bounding_rect.bottomRight()
        x_right = rect_bottom_right.x() + trapezoid_delta
        y_right = rect_bottom_right.y()
        trap_bottom_right = QPointF(x_right, y_right)

        # If selected, offset the border by the calculated margin/highlight border
        if get_highlight:
            dy = self.__margin
            trap_top_left.setX(trap_top_left.x() - self.__highlight_dx_top)
            trap_top_left.setY(trap_top_left.y() - dy)
            trap_bottom_left.setX(trap_bottom_left.x() - self.__highlight_dx_bottom)
            trap_bottom_left.setY(trap_bottom_left.y() + dy)
            trap_top_right.setX(trap_top_right.x() + self.__highlight_dx_top)
            trap_top_right.setY(trap_top_right.y() - dy)
            trap_bottom_right.setX(trap_bottom_right.x() + self.__highlight_dx_bottom)
            trap_bottom_right.setY(trap_bottom_right.y() + dy)

        # The trapezoid
        return QPolygonF([trap_top_left, trap_top_right, trap_bottom_right, trap_bottom_left])

    def __calculate_highlight_xmargins(self, bounding_rect: QRectF):
        """
        Calculates the top and bottom x-delta values to offset the margin when the proxy is highlighted/selected.
        :param bounding_rect: The bounding rect of the proxy widget.
        """
        self.prepareGeometryChange()

        # The angle of the triangular side of the trapezoid
        alpha = atan(bounding_rect.height() / ParentActorProxyItem.TRAPEZOID_DELTA)

        # Picture the left triangular side of the trapezoid when it is selected. Next picture a similar but smaller
        # triangle positioned with the perpendicular right edge touching the left tip of the larger one and its base
        # aligned with the bottom edge of the highlight. Then the vertical length of the similar triangle is equal to
        # the margin width + some value. Based on the fact that the triangles are similar, then the following expression
        # determines this vertical length.
        similar_triangle_vert_length = self.__margin / cos(alpha) + self.__margin

        # The top and bottom x-coordinates of the trapezoid when highlight will be different as follows...
        self.__highlight_dx_top = self.__margin * cos(alpha)
        self.__highlight_dx_bottom = similar_triangle_vert_length / tan(alpha)
