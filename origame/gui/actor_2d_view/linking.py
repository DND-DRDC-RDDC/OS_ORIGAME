# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Classes related to visuals for linking between parts

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from math import cos, sin, tan, degrees, radians, atan2
from pathlib import Path
from enum import IntEnum

# [2. third-party]
from PyQt5.QtCore import Qt, QObject, pyqtSignal
from PyQt5.QtCore import QRectF, QPoint, QPointF, QLineF, QSize, QVariant
from PyQt5.QtGui import QColor, QPen, QPainterPath, QPainter, QBrush, QKeyEvent, QPolygonF, QMouseEvent, QCursor
from PyQt5.QtWidgets import QGraphicsObject, QGraphicsItem, QStyleOptionGraphicsItem, QWidget
from PyQt5.QtWidgets import QGraphicsSceneContextMenuEvent, QMenu, QGraphicsScene
from PyQt5.QtWidgets import QGraphicsSceneMouseEvent, QMessageBox, QGraphicsRectItem
from PyQt5.QtSvg import QGraphicsSvgItem

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...core import override, override_optional, override_required
from ...scenario.defn_parts import PartLink, LinkWaypoint, Position, PartFrame, ActorPart, BasePart

from ..async_methods import AsyncRequest
from ..link_renamer import LinkRenameManager
from ..gui_utils import exec_modal_dialog, get_icon_path
from ..gui_utils import PART_ICON_COLORS, get_scenario_font, try_disconnect
from ..conversions import map_from_scenario, map_to_scenario
from ..safe_slot import safe_slot, ext_safe_slot
from ..actions_utils import create_action
from ..undo_manager import scene_undo_stack, RemoveLinkCommand, DeclutterLinkCommand
from ..undo_manager import AddWaypointCommand, RemoveWaypointCommand, RemoveWaypointsCommand, RemoveAllWaypointsCommand

from .common import ZLevelsEnum, CustomItemEnum, IInteractiveItem, EventStr, ICustomItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'LinkAnchorItem',
    'LinkSceneObject',
    'LinkSegmentSourceItem',
    'PartLinkTargetSelLineItem',
    'PartLinkTargetMarkerItem',
    'WaypointMarkerItem',
    'LinkCreationStatusEnum'
]

log = logging.getLogger('system')

WAYPOINT_SIZE_PIX = 10  # Controls waypoint item size


class Decl(AnnotationDeclarations):
    PartBoxItem = 'PartBoxItem'
    LinkAnchorItem = 'LinkAnchorItem'
    LinkSceneObject = 'LinkSceneObject'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class LinkAnchorSideEnum(IntEnum):
    """
    Enumeration class to indicate the side of the anchor that a link is attached.
    """
    right, left, top, bottom = range(4)


class DeclutterEnum(IntEnum):
    """
    Enumeration class to indicate the list index for the link segment to show.
    """
    normal, decluttered = range(2)


class LinkCreationStatusEnum(IntEnum):
    """
    Enumeration class to indicate the validity status during link creation.
    """
    valid_target, invalid_target, waypoint_added = range(3)


class LinkAnchorItem(ICustomItem, QGraphicsObject):
    """
    This is a base class for anything that can be the end-point of a link segment:
    -   ParentActorProxyItem
    -	PartBoxItem
    -	LinkWaypointItem
    -	IfxPortItem
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # Items that use this class as base must connect their Qt signals for size/pos
    # to these LinkAnchorItem signals for size/pos
    sig_link_anchor_size_changed = pyqtSignal()
    sig_link_anchor_pos_changed = pyqtSignal()

    # Counter for unique ITEM_ID of each LinkItem instance (easier to debug with than id())
    __next_id = 0

    class ContactPointAlgoritmEnum(IntEnum):
        """Contact point algorithm selection"""
        boundary, mid_locked = range(2)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QGraphicsItem = None, parent_part_box_item: Decl.PartBoxItem = None):
        """
        Init the Link Anchor. Note: users must call set_part to set the part as a Link Anchor.
        :param parent: The parent item of this Link Anchor item.
        :param parent_part_box_item: The parent PartBoxItem of this Link Anchor item e.g. (ifx ports).
        """
        ICustomItem.__init__(self)
        QGraphicsObject.__init__(self, parent)
        self.__parent_part_box_item = parent_part_box_item
        self.ITEM_ID = self.__next_id
        LinkAnchorItem.__next_id += 1

        self.__proposed_link_name = None
        self.__create_missing_link_action = create_action(self,
                                                          "Create Missing Link",
                                                          tooltip="Create missing link from link anchor item")

        self.setCursor(QCursor(Qt.ArrowCursor))
        self._set_flags_item_change_link_anchor()

        self.vis_link_anchor_point_item = None
        self.__visualize_anchor_point = False

        self.__contact_point_algorithm = LinkAnchorItem.ContactPointAlgoritmEnum.boundary

        # Must call set_part to set the part's frame
        self.__part_frame = None
        log.debug('Done initializer of {}', self)

    @override(QGraphicsObject)
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, new_value: QVariant) -> QVariant:
        """
        Intercept item scene position changes to signal that the link anchor has moved regardless of parent.
        :param change: the change that occurred
        :param new_value: the new value of attribute associated with change
        :returns: False if attempted disallowed selection, or superclass itemChange() otherwise
        """
        if change == QGraphicsItem.ItemScenePositionHasChanged:
            self.sig_link_anchor_pos_changed.emit()

        return super().itemChange(change, new_value)

    @override(QGraphicsObject)
    def deleteLater(self):
        log.debug('DeleteLater of {}', self)
        super().deleteLater()

    @override_required
    def get_link_boundary_rect(self) -> QRectF:
        """
        Derived classes must override this method to return the attachment boundary for links.
        :return: A rectangular boundary.
        """
        raise NotImplementedError

    @override_optional
    def get_contact_point(self, anchor_point: QPointF, link_line: QLineF) -> QPointF:
        """
        The default implementation of this method calculates the contact point around the LinkAnchorItem
        boundary of a connected link using the anchor-point (a point on or near the LinkAnchorItem object
        calculated to ensure the link line is never less than 45 degrees to the object's
        boundary) and the link line that connects the source anchor item to the target anchor
        item. This point is returned in scene coordinates.

        This method can be overridden to change our the contact point is calculated.

        :param anchor_point: The point on the link anchor that marks the link end-point. This point
            is not necessarily on the anchor boundary, but ensures the link-to-anchor angle is never
            less than 45 deg.
        :param link_line: The link line drawn from source to target anchor item. This line needs to be
            trimmed to the boundary of the anchor item.
        :return: A point on the anchor item's boundary and expressed in Scene coordinates where the link
            segment attaches to this LinkAnchorItem.
        """
        if self.__contact_point_algorithm == LinkAnchorItem.ContactPointAlgoritmEnum.mid_locked:
            return self.get_mid_locked_contact_point(link_line)

        return self.get_boundary_contact_point(anchor_point, link_line)

    @override_optional
    def get_part_id(self) -> int:
        """Return a constant, unique ID for this item"""
        return id(self)

    @override_optional
    def get_children_anchor_items(self) -> List[Decl.LinkAnchorItem]:
        """Return a list of LinkAnchorItem objects that have this anchor as parent"""
        return []

    @override_optional
    def can_start_link(self) -> bool:
        """
        By default, anchors cannot start a link. Override this for anchor types that can sometimes or always
        start a link.
        """
        return False

    @override_optional
    def is_link_allowed(self, link_anchor: Decl.LinkAnchorItem) -> bool:
        """
        Determine if the link is allowed to/from the provided link anchor. Derived classes override this method to
        perform any special checking. By default, this method returns True.
        :param link_anchor: The source or target link anchor.
        :return: True if link is allowed and False, otherwise.
        """
        return True

    @override_optional
    def on_link_added(self, link: PartLink):
        """Create a graphics link item in scene for the given link ID, created by backend."""
        self.scene().on_part_link_added(self, link)

    def get_boundary_contact_point(self, anchor_point: QPointF, link_line: QLineF) -> QPointF:
        """
        The default implementation of this method calculates the contact point around the LinkAnchorItem
        boundary of a connected link using the anchor-point (a point on or near the LinkAnchorItem object
        calculated to ensure the link line is never less than 45 degrees to the object's
        boundary) and the link line that connects the source anchor item to the target anchor
        item. This point is returned in scene coordinates.

        This method can be overridden to change our the contact point is calculated.

        :param anchor_point: The point on the link anchor that marks the link end-point. This point
            is not necessarily on the anchor boundary, but ensures the link-to-anchor angle is never
            less than 45 deg.
        :param link_line: The link line drawn from source to target anchor item. This line needs to be
            trimmed to the boundary of the anchor item.
        :return: A point on the anchor item's boundary and expressed in Scene coordinates where the link
            segment attaches to this LinkAnchorItem.
        """
        if self.__visualize_anchor_point:
            self.visualize_anchor_point(anchor_point)

        # Create 'sides' to check for intersection with provided link_line
        bounding_rect = self.link_boundary_rect
        side_top = QLineF(bounding_rect.topRight(), bounding_rect.topLeft())
        side_right = QLineF(bounding_rect.topRight(), bounding_rect.bottomRight())
        side_left = QLineF(bounding_rect.topLeft(), bounding_rect.bottomLeft())
        side_bottom = QLineF(bounding_rect.bottomLeft(), bounding_rect.bottomRight())

        sides = [side_top, side_right, side_bottom, side_left]

        # Trim link line to anchor boundary
        points = []
        for side in sides:
            intersect_point = QPointF()
            intersect_type = link_line.intersect(side, intersect_point)
            if intersect_type == QLineF.BoundedIntersection:
                # Note that you must copy intersect_point's value into
                # a new variable before placing it into the list as this
                # variable behaves like a pointer -> if appended directly
                # to the list, then if its value changes, the value in
                # the list will change too.
                contact_point = intersect_point
                points.append(contact_point)

        if not points:
            # If no bounded intersection points are found, the parts may be overlapped
            # Return the center of the anchor as the contact point
            contact_point = bounding_rect.center()

        elif len(points) == 1:
            # Found one intersection point
            contact_point = points[0]

        else:
            # Found more than one intersection point
            # Select opposite point from anchor point
            if link_line.p1() == anchor_point:
                opp_point = link_line.p2()
            else:
                opp_point = link_line.p1()

            # Determine link length from each intersection point to
            # the opposite point
            lengths = []
            for point in points:
                line = QLineF(point, opp_point)
                lengths.append(line.length())

            # Select the shortest one - the one on the anchor item's side
            # closest to the opposite end-point
            index = lengths.index(min(lengths))
            contact_point = points[index]

        return contact_point

    def get_mid_locked_contact_point(self, link_line: QLineF) -> QPointF:
        """
        Get the contact point locked at the mid-point of the boundary for the LinkAnchorItem.
        This code provides a contact point at the mid-point of the top, bottom, left, or right side
        of the item as an alternative to get_contact_point.

        :param link_line: The link line drawn from source to target anchor item. This line needs to be
        trimmed to the boundary of the anchor item.
        :return: A point on the anchor item's boundary and expressed in Scene coordinates where the link
        segment attaches to this LinkAnchorItem.
        """
        # Create 'sides' to check for intersection with provided link_line
        bounding_rect = self.link_boundary_rect
        side_top = QLineF(bounding_rect.topRight(), bounding_rect.topLeft())
        side_right = QLineF(bounding_rect.topRight(), bounding_rect.bottomRight())
        side_left = QLineF(bounding_rect.topLeft(), bounding_rect.bottomLeft())
        side_bottom = QLineF(bounding_rect.bottomLeft(), bounding_rect.bottomRight())

        # Search for the side intersecting the link
        sides = [side_top, side_right, side_bottom, side_left]
        for side in sides:
            intersect_point = QPointF()
            intersect_type = link_line.intersect(side, intersect_point)
            if intersect_type == QLineF.BoundedIntersection:
                # Return the mid-point of the side
                return side.pointAt(0.5)

        # If we got here, no intersection was found:
        # Return the mid-point of the left or right side
        if self.__is_left_side:
            return side_left.pointAt(0.5)
        else:
            return side_right.pointAt(0.5)

    def toggle_contact_point_algorithm(self):
        """
        Toggles between 'boundary' and 'mid_point' get_contact_point algorithms.
        """
        if self.__contact_point_algorithm == LinkAnchorItem.ContactPointAlgoritmEnum.boundary:
            self.__contact_point_algorithm = LinkAnchorItem.ContactPointAlgoritmEnum.mid_locked
        else:
            self.__contact_point_algorithm = LinkAnchorItem.ContactPointAlgoritmEnum.boundary

    def toggle_visualize_anchor_point(self):
        """
        Toggles the flag to visualize the anchor point between True and False
        """
        self.__visualize_anchor_point = not self.__visualize_anchor_point

    def visualize_anchor_point(self, anchor_point: QPointF):
        """
        Used to visualize the anchor points provided by the LinkSegmentItem. Adds a QGraphicsRectItem to the scene.
        :param anchor_point: The point on the link anchor that marks the link end-point. This point
            is not necessarily on the anchor boundary, but ensures the link-to-anchor angle is never
            less than 45 deg.
        """
        if self.vis_link_anchor_point_item is None:
            self.vis_link_anchor_point_item = QGraphicsRectItem()
            pen = QPen(Qt.SolidLine)
            pen.setWidth(5)
            pen.setColor(Qt.black)
            self.vis_link_anchor_point_item.setPen(pen)
            self.vis_link_anchor_point_item.setZValue(50)
            self.scene().addItem(self.vis_link_anchor_point_item)

        rect = QRectF(anchor_point.x(), anchor_point.y(), 5, 5)
        self.vis_link_anchor_point_item.setRect(rect)

    def on_link_removed(self, link_id: int, link_name: str):
        """Notify the scene to remove the outgoing link"""
        self.scene().on_part_link_removed(link_id, link_name)

    def set_frame(self, part_frame: PartFrame):
        """
        Set this part's frame as a link anchor.
        :param part_frame: the part frame to set.
        """
        # If setting a new part into this item, disconnect previous part
        if self.__part_frame is not None:
            self.__part_frame.signals.sig_outgoing_link_added.disconnect(self.slot_on_link_added)
            self.__part_frame.signals.sig_outgoing_link_removed.disconnect(self.slot_on_link_removed)

        self.__part_frame = part_frame
        self.__part_frame.signals.sig_outgoing_link_added.connect(self.slot_on_link_added)
        self.__part_frame.signals.sig_outgoing_link_removed.connect(self.slot_on_link_removed)
        log.debug('Link anchor {} on {}', self, self.__parent_part_box_item)

        assert self.__part_frame is not None
        self.setObjectName(str(self))

    def get_part_frame(self) -> PartFrame:
        """
        Accessor for the part frame.
        :return: the part frame
        """
        return self.__part_frame

    def get_parent_part_box_item(self) -> Decl.PartBoxItem:
        """Returns the parent part box item of this link anchor."""
        return self.__parent_part_box_item

    def get_proposed_link_name(self):
        """
        Gets the proposed link name. The use case is to create a missing link with the name.
        :return: The proposed link name
        """
        return self.__proposed_link_name

    def set_proposed_link_name(self, link_name: str):
        """
        Sets the proposed link name. The use case is to set a link name before creating a missing link.
        :param link_name: The proposed link name
        """
        self.__proposed_link_name = link_name

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    proposed_link_name = property(get_proposed_link_name, set_proposed_link_name)
    link_boundary_rect = property(get_link_boundary_rect)
    part_frame = property(get_part_frame)
    parent_part_box_item = property(get_parent_part_box_item)

    slot_on_link_added = ext_safe_slot(on_link_added)
    slot_on_link_removed = safe_slot(on_link_removed)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    def __str__(self):
        return '{} #{} for {}'.format(type(self).__qualname__, self.ITEM_ID, self.__part_frame or '<undefined>')

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def _set_flags_item_change_link_anchor(self):
        """
        Set the flags necessary so itemChange() is called for the desired events. Derived classes MUST
        call this if they further override itemChange(), otherwise only one of the base class itemChange()
        gets called (this is likely due to a PyQt bug, or to how the Qt library handles this flag).
        """
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges)

    @override_optional
    def _disconnect_all_slots(self):
        try_disconnect(self.__part_frame.signals.sig_outgoing_link_added, self.slot_on_link_added)
        try_disconnect(self.__part_frame.signals.sig_outgoing_link_removed, self.slot_on_link_removed)

    def _populate_create_missing_link_menu(self, context_menu: QMenu, end_callback: Callable[[], None]):
        """
        If the derived class needs to create missing links, it should call this function in the contextMenuEvent()
        to set up the infrastructure.
        :param context_menu: The menu to be populated with sub menu items representing the missing links
        :param end_callback: Since this function involves async call, the end_call is called at the end of the async
        call's response_cb.
        """
        def populate_missing_link_action(unique_link_names: List[str]):
            if unique_link_names is not None:
                context_menu.addAction(self.__create_missing_link_action)
                missing_menu = QMenu(parent=context_menu)
                self.__create_missing_link_action.setMenu(missing_menu)
                self.__create_missing_link_action.setEnabled(bool(unique_link_names))
                if unique_link_names:
                    for link_name in unique_link_names:
                        one_link_action = create_action(parent=missing_menu,
                                                        text=link_name,
                                                        tooltip='Create the missing link "{}"'.format(link_name),
                                                        connect=self.__slot_on_create_link_by_name)
                        self.__create_missing_link_action.menu().addAction(one_link_action)

            end_callback()

        AsyncRequest.call(self.part.get_unique_missing_link_names, response_cb=populate_missing_link_action)

    def __on_create_link_by_name(self):
        """
        Start the creation of a link from this part. Delegates to the scene, allowing the user to select the
        target part or ESC to cancel. The name of the link comes from the sender.text()
        """
        # Forcing selection is necessary because the link creation shortcut doesn't select this automatically.
        self.scene().set_selection(self)
        self.proposed_link_name = self.sender().text()
        self.scene().start_link_creation_from(self)

    __slot_on_create_link_by_name = safe_slot(__on_create_link_by_name)


class LinkSegmentBaseItem(QGraphicsObject):
    """
    This class represents the base class for link segments by providing the common graphics-object components, painting
    attributes (pens, colours), and link segment start- and end-point calculation methods.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    MIN_LINK_LENGTH = 0.0
    PEN_WIDTH = 4.0    #3.5
    COLOR_DEFAULT = PART_ICON_COLORS['link']
    COLOR_HIGHLIGHT = QColor(0, 255, 0, 255)
    PARALLEL_LINK_OFFSET = 5.0  # Number of scene units between links of two interconnected parts

    # ---------------------------- instance PUBLIC methods ----------------------------

    def __init__(self):
        """
        Initialize the Link Segment Base Item.
        """
        QGraphicsObject.__init__(self)

        self._draw_link = True

        self._source_anchor_item = None
        self._target_anchor_item = None

        self._start_point = QPointF()
        self._end_point = QPointF()

        self._bounding_rect_path = QPainterPath()
        self._link_path = QPainterPath()

        self._link_pen = QPen(Qt.SolidLine)
        self._link_pen.setWidth(int(self.PEN_WIDTH))
        self._link_pen.setColor(self.COLOR_DEFAULT)


    @override(QGraphicsObject)
    def type(self) -> int:
        return CustomItemEnum.link.value

    @override(QGraphicsItem)
    def boundingRect(self) -> QRectF:
        return self._bounding_rect_path.boundingRect()

    @override(QGraphicsItem)
    def shape(self) -> QPainterPath:
        return self._bounding_rect_path

    @override(QGraphicsObject)
    def deleteLater(self):
        self._source_anchor_item = None
        self._target_anchor_item = None
        super().deleteLater()

    @override_optional
    def calculate_painter_path(self, start_point: QPointF, end_point: QPointF, alpha_rad: float, link_name: str = None):
        """
        Calculates the path to draw whenever the end-points change.
        :param start_point: The start point as determined by intersection with the origin anchor frame.
        :param end_point: The end point as determined by intersection with the target anchor frame.
        :param alpha_rad: The angle of the link with respect the the horizontal x-axis.
        :param link_name: The label on the link.
        """
        self.prepareGeometryChange()
        self._link_path = QPainterPath()
        self._start_point = start_point
        self._end_point = end_point

    def get_start_point(self) -> QPointF:
        """
        Returns the start point of the link in scene coordinates.
        :return: The link start point.
        """
        return self._start_point

    def get_end_point(self) -> QPointF:
        """
        Returns the end point of the link in scene coordinates.
        :return: The link end point.
        """
        return self._end_point

    def get_mid_point(self) -> QPointF:
        """
        Returns the mid-point of the segment.
        :return: The mid-point.
        """
        line = QLineF(self._start_point, self._end_point)
        return line.pointAt(0.5)

    def set_source_anchor_item(self, item: LinkAnchorItem):
        """
        Sets the source anchor item of the link.
        :param item: The item containing the anchor which is the source of the link.
        """
        self._source_anchor_item = item
        self._source_anchor_item.sig_link_anchor_pos_changed.connect(self._slot_calculate_link_end_points)
        self._source_anchor_item.sig_link_anchor_size_changed.connect(self._slot_calculate_link_end_points)
        self._calculate_link_end_points()

        #DRWA
        #if item.get_part_frame() is not None:
        #    self.COLOR_DEFAULT = PART_ICON_COLORS[item.get_part_frame().get_part().PART_TYPE_NAME]
        #    self._link_pen.setColor(self.COLOR_DEFAULT)


    def get_source_anchor_item(self) -> LinkAnchorItem:
        """
        Retrieves the source (start-point) item of the link.
        :return: The origin item
        """
        return self._source_anchor_item

    def set_target_anchor_item(self, item: LinkAnchorItem):
        """
        Set the target anchor item of the link.
        :param item: The target item
        """

        if self._target_anchor_item is item:
            return

        if self._target_anchor_item is not None:
            # Disconnect the old connections...
            self._target_anchor_item.sig_link_anchor_pos_changed.disconnect(self._slot_calculate_link_end_points)
            self._target_anchor_item.sig_link_anchor_size_changed.disconnect(self._slot_calculate_link_end_points)

        self._target_anchor_item = item
        if item is not None:
            # ... connect to the item's own front-end signals
            self._target_anchor_item.sig_link_anchor_pos_changed.connect(self._slot_calculate_link_end_points)
            self._target_anchor_item.sig_link_anchor_size_changed.connect(self._slot_calculate_link_end_points)

        self._calculate_link_end_points()

    def get_target_anchor_item(self) -> LinkAnchorItem:
        """
        Retrieves the target (end-point) item of the link.
        :return: The target item
        """
        return self._target_anchor_item

    # ---------------------------- instance PUBLIC properties ----------------------------

    start_point = property(get_start_point)
    end_point = property(get_end_point)
    mid_point = property(get_mid_point)
    source_anchor_item = property(get_source_anchor_item, set_source_anchor_item)
    target_anchor_item = property(get_target_anchor_item, set_target_anchor_item)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_optional
    def _calculate_link_end_points(self):
        """
        Calculates the link start and end points when either the source or target anchor is moved.

        The movement of the either the source or target anchor items trigger this method to recalculate the
        start and end point of an attached link by using the items' boundingRect to compute the intersection of
        a painted link line with the anchor's frame (right, left, top, bottom edges).

        The start and end points are determined based on the design illustrated in file 'link_positioning.png' that is
        located in the same directory as this module. The file shows a link-positioning design that ensures that the
        angle the link line makes with respect to the anchor edge where the connection point is made is never less than
        45 deg. The 45 deg minimum angle occurs at the corners of the source and target parts and increases to 90 deg
        in the horizontal or vertical directions as the link line moves around the anchor.
        """

        # No need to continue if either source or target doesn't exist
        if None in (self._source_anchor_item, self._target_anchor_item):
            return

        # Create a temporary link line from the anchor centers to determine the general direction of the link
        source_bounding_rect = self._source_anchor_item.link_boundary_rect
        target_bounding_rect = self._target_anchor_item.link_boundary_rect

        # Get the four possible link connection points on the source and target link anchors
        src_right, src_top, src_left, src_bottom = self.__compute_link_points(source_bounding_rect)
        tgt_right, tgt_top, tgt_left, tgt_bottom = self.__compute_link_points(target_bounding_rect)

        # Pair the sides of the anchor that will be connected (opposite to link direction)
        link_right_pair = (src_right, tgt_left)
        link_up_pair = (src_top, tgt_bottom)
        link_left_pair = (src_left, tgt_right)
        link_down_pair = (src_bottom, tgt_top)

        # Select the link to draw of the four possible
        link_line, source_point, target_point = self.__compute_link_line(source_bounding_rect, target_bounding_rect,
                                                                         link_right_pair, link_up_pair,
                                                                         link_left_pair, link_down_pair)

        # Apply a small off-set so links between two interconnected parts do not overlap
        link_normal = link_line.normalVector()
        link_unit = link_normal.unitVector()
        x_offset = (link_unit.x2() - link_unit.x1()) * self.PARALLEL_LINK_OFFSET
        y_offset = (link_unit.y2() - link_unit.y1()) * self.PARALLEL_LINK_OFFSET
        source_point.setX(source_point.x() + x_offset)
        source_point.setY(source_point.y() + y_offset)
        target_point.setX(target_point.x() + x_offset)
        target_point.setY(target_point.y() + y_offset)

        # Create the line between the current link anchor points
        link_line = QLineF(source_point, target_point)

        self._start_point = self._source_anchor_item.get_contact_point(source_point, link_line)
        self._end_point = self._target_anchor_item.get_contact_point(target_point, link_line)

        # Recompute the link angle using atan2 (not link_line.angle())
        # This accounts for the +y down coordinate system where the angle is measured clockwise from +x (rather than
        # the typical counter-clockwise where +y is up used by the angle() method).
        t_y = self._end_point.y() - self._start_point.y()
        t_x = self._end_point.x() - self._start_point.x()
        self._alpha_rad = atan2(t_y, t_x)

    def _can_draw_link(self) -> bool:
        """
        Determine if the link should be drawn. Do not draw the link if the parts overlap, or are about to.
        :return: A boolean flag indicating if the link should be drawn.
        """
        source_bounding_rect = self._source_anchor_item.link_boundary_rect
        target_bounding_rect = self._target_anchor_item.link_boundary_rect

        # Adjust the margin of the anchors' link-bounding-rects by a minimum link length within which the link is hidden
        # If the adjusted bounding rects touch/overlap, the link will not be shown
        draw_link = True
        min_link_len = self.MIN_LINK_LENGTH
        source_rect_adjusted = source_bounding_rect.adjusted(-min_link_len, -min_link_len, min_link_len, min_link_len)
        target_rect_adjusted = target_bounding_rect.adjusted(-min_link_len, -min_link_len, min_link_len, min_link_len)
        if source_rect_adjusted.intersects(target_rect_adjusted):
            draw_link = False  # the bounding rects overlap

        return draw_link

    def _calculate_segment_bounding_rect(self, start_point: QPointF, end_point: QPointF, angle_radians: float):
        """
        Calculates an invisible polygon around the link segment length which provides a bounding rectangle for the
        graphics view and makes the segment more easily selectable. Call every time the segment end-points change.
        :param start_point: The start point of the link.
        :param end_point: The end point of the link.
        :param angle_radians: The angle the link makes with the horizontal x-axis in radians.
        """

        # Reset the bounding rectangle
        self._bounding_rect_path = QPainterPath()

        thickness = self.PEN_WIDTH
        link_poly_points = []  # List container for the generated polygon points (4 in total)
        link_end_points = [start_point, end_point]

        for point in link_end_points:
            # For each link end-point, calculate the two points on either
            # side of the link's central line due to the pen thickness
            top_x = -thickness * sin(angle_radians) + point.x()
            top_y = thickness * cos(angle_radians) + point.y()
            bottom_x = thickness * sin(angle_radians) + point.x()
            bottom_y = -thickness * cos(angle_radians) + point.y()

            top_point = QPointF(top_x, top_y)
            bottom_point = QPointF(bottom_x, bottom_y)

            # Append to the list container
            link_poly_points.append(top_point)
            link_poly_points.append(bottom_point)

        # Connect the points from start-top, to end-top, to end-bottom, to start_bottom
        link_poly = QPolygonF([link_poly_points[0], link_poly_points[2], link_poly_points[3], link_poly_points[1]])

        # Re-define the bounding rectangle. This informs the view where to redraw.
        # The rectangle covers link completely with a diagonal length extending from one end of the link to the other.
        self._bounding_rect_path.addPolygon(link_poly)

    _slot_calculate_link_end_points = safe_slot(_calculate_link_end_points)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __compute_link_points(self, link_anchor_rect: QRectF) -> Tuple[QPointF, QPointF, QPointF, QPointF]:
        """
        Calculate the four link connection points for the given link anchor rect: right, top, left, and bottom sides.
        :param link_anchor_rect: A rectangle that defines the edges of a selected anchor.
        :returns A tuple of four link attachment points.
        """
        right = self.__compute_link_point(link_anchor_rect, LinkAnchorSideEnum(LinkAnchorSideEnum.right))
        top = self.__compute_link_point(link_anchor_rect, LinkAnchorSideEnum(LinkAnchorSideEnum.top))
        left = self.__compute_link_point(link_anchor_rect, LinkAnchorSideEnum(LinkAnchorSideEnum.left))
        bottom = self.__compute_link_point(link_anchor_rect, LinkAnchorSideEnum(LinkAnchorSideEnum.bottom))
        return right, top, left, bottom

    def __compute_link_point(self, link_anchor_rect: QRectF, anchor_side: LinkAnchorSideEnum) -> QPointF:
        """
        Calculate a link connection point on the right, left, top, or bottom side of the anchor.
        :param link_anchor_rect: A rectangle that defines the edges of a selected anchor.
        :param anchor_side: The side of the link anchor to attach the link (right, left, top, bottom).
        :returns point: A link attachment point located such that the link angle to the anchor edge is never < 45.0 deg.
        """
        if anchor_side.value == LinkAnchorSideEnum.right:
            # Construct the right side of the link anchor
            part_edge = QLineF(link_anchor_rect.topRight(), link_anchor_rect.bottomRight())
            offset_dir = -1.0  # move offset left
        elif anchor_side.value == LinkAnchorSideEnum.left:
            # Construct the left side of the link anchor
            part_edge = QLineF(link_anchor_rect.topLeft(), link_anchor_rect.bottomLeft())
            offset_dir = 1.0  # move offset right
        elif anchor_side.value == LinkAnchorSideEnum.top:
            # Construct the top side of the link anchor
            part_edge = QLineF(link_anchor_rect.topLeft(), link_anchor_rect.topRight())
            offset_dir = 1.0  # move offset down (+y is down)
        else:  # LinkAnchorSideEnum.bottom
            # Construct the bottom line of the link anchor
            part_edge = QLineF(link_anchor_rect.bottomLeft(), link_anchor_rect.bottomRight())
            offset_dir = -1.0  # move offset up (-y is up)

        # select mid-point of edge
        MID_POINT = 0.5  # 50% along
        link_point = part_edge.pointAt(MID_POINT)
        offset = offset_dir * part_edge.length() / 2.0

        if anchor_side == LinkAnchorSideEnum.right or anchor_side == LinkAnchorSideEnum.left:
            link_point.setX(link_point.x() + offset)
        else:
            link_point.setY(link_point.y() + offset)

        return link_point

    def __compute_link_line(self,
                            source_link_anchor_rect: QRectF,
                            target_link_anchor_rect: QRectF,
                            right_pair: Tuple[QPointF, QPointF],
                            up_pair: Tuple[QPointF, QPointF],
                            left_pair: Tuple[QPointF, QPointF],
                            down_pair: Tuple[QPointF, QPointF]) -> Tuple[QLineF, QPointF, QPointF]:
        """
        Computes four link lines and determines which one satisfies the requirement that the line angle be >=45 deg.

        The link is valid for only one pair of points since the goal is to limit the link line to >= 45 deg to the
        respective edge the link is attached to. Therefore, each link line has a corresponding valid range in which it
        must lie in order to be valid, and the link can only be in one range at a time.

        :param source_link_anchor_rect: A rectangle that defines the edges of the source anchor.
        :param target_link_anchor_rect: A rectangle that defines the edges of the target anchor.
        :param right_pair: The pair of points that draw a link line from source to target pointing to the right.
        :param up_pair: The pair of points that draw a link line from source to target pointing to the up.
        :param left_pair: The pair of points that draw a link line from source to target pointing to the left.
        :param down_pair: The pair of points that draw a link line from source to target pointing to the down.
        :return: The link line and corresponding pair of linked points from source to target.
        :raises a RuntimeError if the link angle could not be determined.
        """
        # Create four possible link lines using the four pairs of link connection points
        link_line_right = QLineF(right_pair[0], right_pair[1])
        link_line_up = QLineF(up_pair[0], up_pair[1])
        link_line_left = QLineF(left_pair[0], left_pair[1])
        link_line_down = QLineF(down_pair[0], down_pair[1])

        # Measure the angle of each possible link
        # 0.0 <= angle < 360.0 degrees counter-clockwise from +x
        link_line_right_angle = link_line_right.angle()
        link_line_up_angle = link_line_up.angle()
        link_line_left_angle = link_line_left.angle()
        link_line_down_angle = link_line_down.angle()

        # Compare each of the four angles formed by each possible link line.
        # If the angle falls into it's valid range it COULD be the link line to draw.
        # However, it's possible that the line could fall within range but not be valid.
        # e.g. for parts directly above or below, the angles will fall within range for both top
        # and bottom cases. Therefore, use the anchor positions to verify that source and target
        # anchors are in the correct relative positions for the link line at the angle to be valid.
        source_pos = source_link_anchor_rect.topRight()
        target_pos = target_link_anchor_rect.topRight()
        if 0.0 <= link_line_right_angle <= 45.0 or 315.0 <= link_line_right_angle < 360.0:
            # Verify the target is to the right of the source
            if target_pos.x() > source_pos.x():
                return link_line_right, right_pair[0], right_pair[1]
        else:
            pass  # not in this quadrant -> check next quadrant

        if 45.0 < link_line_up_angle < 135:
            # Verify the target is above of the source (+y-down)
            if target_pos.y() < source_pos.y():
                return link_line_up, up_pair[0], up_pair[1]
        else:
            pass  # not in this quadrant -> check next quadrant

        if 135.0 <= link_line_left_angle <= 225.0:
            # Verify the target is to the left of the source
            if target_pos.x() < source_pos.x():
                return link_line_left, left_pair[0], left_pair[1]
        else:
            pass  # not in this quadrant -> check next quadrant

        # link must be in quadrant four with target below the source (+y-down)
        assert 225.0 < link_line_down_angle < 315.0
        assert target_pos.y() > source_pos.y()
        return link_line_down, down_pair[0], down_pair[1]


class LinkSegmentItem(IInteractiveItem, LinkSegmentBaseItem):
    """
    This class implements common features of link segments including link arrow creation and implementation of context-
    menu options for link delete, link delcutter, link end-point 'goto' methods, link re-targeting, and addition/removal
    of waypoints.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, link_obj: Decl.LinkSceneObject, part_link: PartLink, declutter: bool = False):
        """
        Initialize the link attributes including start and end points, origin and target items,
        the pen and drawing paths, and the context-menu 'actions'.
        :param link_obj: The link object to which this segment belongs.
        :param part_link: The backend link of this link graphics item.
        :param declutter: Flag that indicates if the link should be drawn in decluttered mode.
        """
        IInteractiveItem.__init__(self)
        LinkSegmentBaseItem.__init__(self)

        self.setCursor(QCursor(Qt.ArrowCursor))

        self._set_flags_item_change_interactive()
        assert self.flags() & (QGraphicsItem.ItemIsFocusable | QGraphicsItem.ItemIsSelectable)
        assert not (self.flags() & self.ItemIsMovable)

        self.setObjectName(part_link.name)
        self.__link_obj = link_obj
        self.__part_link = part_link
        self.__is_link_decluttered = declutter
        self._alpha_rad = float()  # angle the link makes with horizontal x-axis
        self._link_len = 0.0

        # Arrow params
        self.arrow_length = 18.0    #15.0  # Adjust to make the arrow longer
        self.arrow_half_angle = radians(15.0)  # Adjust to make the arrow narrow or wide
        self.arrow_offset = self.arrow_length  # The arrowhead offset from the link end-point
        self.arrow_stem_offset = 8.0  # The arrow stem offset from the ARROW_OFFSET

        #DRWA
        self.COLOR_DEFAULT = PART_ICON_COLORS[part_link.part_type_name].darker(175)

        # Fine pen for link arrow
        self._arrow_pen = QPen(Qt.SolidLine)
        self._arrow_pen.setWidthF(int(0.1))
        self._arrow_pen.setColor(self.COLOR_DEFAULT)

        # Fine pen for link label
        self._label_pen = QPen(Qt.SolidLine)
        self._label_pen.setWidthF(int(0.1))
        self._label_pen.setColor(self.COLOR_DEFAULT)
        self._label_brush = QBrush(self.COLOR_DEFAULT, Qt.SolidPattern)

        self.label_offset = self.arrow_offset + self.arrow_stem_offset  # Offset label from the link endpoint

        # Brushes (for filling shapes)
        self._default_brush = QBrush(self.COLOR_DEFAULT, Qt.SolidPattern)
        self._highlight_brush = QBrush(self.COLOR_HIGHLIGHT, Qt.SolidPattern)

        # Create context-menu 'actions'
        self.__action_delete = create_action(self, "Delete",
                                             tooltip="Delete link",
                                             connect=self.slot_on_action_delete)
        self.__action_declutter = create_action(self, "Toggle Declutter",
                                                tooltip="Toggle decluttering mode on link",
                                                connect=self.slot_on_action_toggle_declutter)
        self.__action_goto_source_part = create_action(self, "Source Part",
                                                       tooltip="Show the link's source part",
                                                       connect=self.slot_on_action_goto_source_part)
        self.__action_goto_target_part = create_action(self, "Target Part",
                                                       tooltip="Show the link's target part",
                                                       connect=self.slot_on_action_goto_target_part)
        self.__action_goto_source_ifx_port = create_action(self, "Source Port",
                                                           tooltip="Show the link's source interface port",
                                                           connect=self.slot_on_action_goto_source_ifx_port)
        self.__action_goto_target_ifx_port = create_action(self, "Target Port",
                                                           tooltip="Show the link's target interface port",
                                                           connect=self.slot_on_action_goto_target_ifx_port)
        self.__action_add_waypoint = create_action(self, "Insert Waypoint",
                                                   tooltip="Insert waypoint in link, at mouse",
                                                   connect=self.slot_on_action_add_waypoint)
        self.__action_remove_all_waypoints = create_action(self, "Remove All Waypoints",
                                                           tooltip="Remove all waypoints from link",
                                                           connect=self.slot_on_action_remove_all_waypoints)
        self.__action_retarget_link = create_action(self, "Change Link Endpoint",
                                                    tooltip="Select a new target part to link",
                                                    connect=self.slot_on_action_retarget_link)

        self.enable_remove_all_waypoints_action(False)  # Initially there will be no waypoints

    @override(IInteractiveItem)
    def get_scenario_object(self) -> PartLink:
        """Get the scenario object that corresponds to this item."""
        return self.get_part_link()

    @override(QGraphicsObject)
    def keyPressEvent(self, event: QKeyEvent):
        """
        Handles the deletion of links by pressing the Delete key.
        :param event: A key press event.
        """
        key_pressed = event.key()
        if key_pressed == Qt.Key_Delete:
            self.on_action_delete()

    @override(QGraphicsObject)
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        """Override to provide link selection on right-click."""
        log.debug("Link segment for {} got mouse press: {}", self.__part_link, EventStr(event))
        super().mousePressEvent(event)

        right_click = event.button() & Qt.RightButton
        if right_click:
            self.scene().set_selection(self)

    @override(QGraphicsObject)
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """
        Open the rename dialog on mouse double-click.
        """
        link_rename_manager = LinkRenameManager()
        if link_rename_manager.is_link_rename_ready(self.__part_link):
            link_rename_manager.start_rename_action.triggered.emit()

    @override(QGraphicsItem)
    def contextMenuEvent(self, evt: QGraphicsSceneContextMenuEvent):
        """
        Set up context menu for GUI-based link editing. Adds the QActions created in 'init'.
        :param evt: Qt context menu event information.
        """
        context_menu = QMenu()
        link_rename_manager = LinkRenameManager()
        _ = link_rename_manager.is_link_rename_ready(self.__part_link, use_dialog=False)
        context_menu.addAction(link_rename_manager.start_rename_action)
        context_menu.addAction(self.__action_delete)
        context_menu.addAction(self.__action_declutter)

        # "Go to..." submenu -------------------------------------
        menu_goto_part = QMenu("Go to...")
        context_menu.addMenu(menu_goto_part)

        source_part = self.__part_link.source_part_frame.part
        if self.scene().content_actor is source_part.parent_actor_part:
            # Source part's parent is the content actor -> disable 'go to source port'
            self.__action_goto_source_ifx_port.setEnabled(False)
        else:
            # Source part's parent is another actor -> enable 'go to source port'
            self.__action_goto_source_ifx_port.setEnabled(True)

        target_part = self.__part_link.target_part_frame.part
        if self.scene().content_actor is target_part.parent_actor_part:
            # Target part's parent is the content actor -> disable 'go to target port'
            self.__action_goto_target_ifx_port.setEnabled(False)
        else:
            # Target part's parent is another actor -> enable 'go to target port'
            self.__action_goto_target_ifx_port.setEnabled(True)

        menu_goto_part.addAction(self.__action_goto_source_part)
        menu_goto_part.addAction(self.__action_goto_target_part)
        menu_goto_part.addAction(self.__action_goto_source_ifx_port)
        menu_goto_part.addAction(self.__action_goto_target_ifx_port)
        context_menu.addSeparator()
        # ------------------------------------------------------

        context_menu.addAction(self.__action_add_waypoint)
        context_menu.addAction(self.__action_remove_all_waypoints)
        context_menu.addSeparator()
        context_menu.addAction(self.__action_retarget_link)
        context_menu.exec(evt.screenPos())

    def enable_add_waypoint_action(self, enable: bool):
        """
        Enable or disable 'add' action for waypoints.
        :param enable: Flag indicates if action is enabled.
        """
        self.__action_add_waypoint.setEnabled(enable)

    def enable_remove_all_waypoints_action(self, enable: bool):
        """
        Enable or disable 'remove all' action for waypoints.
        :param enable: Flag indicates if action is enabled.
        """
        self.__action_remove_all_waypoints.setEnabled(enable)

    def on_action_delete(self):
        """
        Remove the link from the scene.
        """
        if not self.scene().is_item_visible(self):
            msg = 'Some Links are not in view: "{}". Click Yes to delete them anyways, ' \
                  'or No to go back without deletion.'.format(self.__part_link.name)

            if exec_modal_dialog("Delete Link", msg, QMessageBox.Question) != QMessageBox.Yes:
                return

        self.remove_link()

    def on_action_toggle_declutter(self):
        """
        Requests the back-end link part to toggle its declutter flag.
        """
        if self.is_link_decluttered:
            # If declutter is True, set to False
            cmd = DeclutterLinkCommand(self.__part_link, False)
            scene_undo_stack().push(cmd)
        else:
            # ..else, set to True
            cmd = DeclutterLinkCommand(self.__part_link, True)
            scene_undo_stack().push(cmd)

    def on_action_goto_source_part(self):
        """
        Show the source part for the link in the 2D View.
        """
        source_part = self.__part_link.source_part_frame.part
        self.scene().sig_show_child_part.emit(source_part)
        log.info('The source part for link {} is {}.', self.__part_link, source_part)

    def on_action_goto_target_part(self):
        """
        Show the target part for the link in the 2D View.
        """
        target_part = self.__part_link.target_part_frame.part
        self.scene().sig_show_child_part.emit(target_part)
        log.info('The exit part for link {} is {}.', self.__part_link, target_part)

    def on_action_goto_source_ifx_port(self):
        """
        Show the source ifx port for the link in the 2D View.
        """
        source_port = self.__part_link.source_part_frame.part
        found_source_port = self.__goto_ifx_port(source_port)
        assert found_source_port
        log.debug('The source port for link {} is {}.', self.__part_link, source_port)

    def on_action_goto_target_ifx_port(self):
        """
        Show the target ifx port for the link in the 2D View.
        """
        target_port = self.__part_link.target_part_frame.part
        found_target_port = self.__goto_ifx_port(target_port)
        assert found_target_port
        log.debug('The target port for link {} is {}.', self.__part_link, target_port)

    def on_action_add_waypoint(self):
        """Triggers the insertion of a waypoint on this link segment."""
        self.__link_obj.add_waypoint(self)

    def on_action_remove_all_waypoints(self):
        """Triggers the removal of all waypoints on the link to which this segment belongs."""
        self.__link_obj.remove_all_waypoints()

    def on_action_retarget_link(self):
        """Initiates link retargeting for the link this segment belongs to."""
        self.__link_obj.retarget_link()

    def get_part_link(self) -> PartLink:
        """Gets the part link."""
        return self.__part_link

    def get_link_obj(self) -> Decl.LinkSceneObject:
        """Gets the graphic link object."""
        return self.__link_obj

    @override_optional
    def get_link_decluttered(self) -> bool:
        """
        Gets the current decluttered flag.
        :return: True if decluttered and False, otherwise.
        """
        return self.__is_link_decluttered

    @override_optional
    def set_link_decluttered(self, is_decluttered: bool):
        """
        Sets the declutter flag.
        """
        if is_decluttered:
            self.enable_add_waypoint_action(False)
        else:
            self.enable_add_waypoint_action(True)

        self.__is_link_decluttered = is_decluttered
        self._calculate_link_end_points()

    def remove_link(self):
        """Requests the backend to remove the link to which this segment belongs."""
        remove_link_command = RemoveLinkCommand(self.__part_link)
        scene_undo_stack().push(remove_link_command)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    part_link = property(get_part_link)
    link_obj = property(get_link_obj)
    is_link_decluttered = property(get_link_decluttered, set_link_decluttered)

    slot_on_action_delete = safe_slot(on_action_delete)
    slot_on_action_toggle_declutter = safe_slot(on_action_toggle_declutter)
    slot_on_action_goto_source_part = safe_slot(on_action_goto_source_part)
    slot_on_action_goto_target_part = safe_slot(on_action_goto_target_part)
    slot_on_action_goto_source_ifx_port = safe_slot(on_action_goto_source_ifx_port)
    slot_on_action_goto_target_ifx_port = safe_slot(on_action_goto_target_ifx_port)
    slot_on_action_add_waypoint = safe_slot(on_action_add_waypoint)
    slot_on_action_remove_all_waypoints = safe_slot(on_action_remove_all_waypoints)
    slot_on_action_retarget_link = safe_slot(on_action_retarget_link)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IInteractiveItem)
    def _highlighting_changed(self):
        self.__link_obj.on_segment_selected(self.is_highlighted)

    def _calculate_segment_offset_point(self, link_point: QPointF, alpha_rad: float, offset: float) -> QPointF:
        """
        Calculates a point lying along the link and offset from the given point on the link.
        :param link_point: The point on the link.
        :param alpha_rad: The angle of the link with respect the the horizontal x-axis (radians).
        :param offset: An offset from the point provided (negative for behind the point and positive for in front).
        :return: An offset point lying along the link.
        """
        x0 = link_point.x()
        y0 = link_point.y()

        x = x0 + offset * cos(alpha_rad)
        y = y0 + offset * sin(alpha_rad)

        return QPointF(x, y)

    def _calculate_arrow_poly(self, end_point: QPointF, alpha_rad: float) -> QPolygonF:
        """
        Calculates the arrowhead geometry.
        :param end_point: The end point as determined by intersection with the target anchor frame.
        :param alpha_rad: The angle of the link with respect the the horizontal x-axis.
        :returns: The polygon that defines the arrow shape.
        """
        x1 = end_point.x()
        y1 = end_point.y()

        # Determine if the arrow should be scaled
        link_len_bias = 45.0  # seems that there is some unaccounted for length when self._link_len == 0.0
        link_length = self._link_len + link_len_bias
        if link_length < self.arrow_length:
            # Scale the arrow down with the ratio of link length to arrow length
            arrow_scale = link_length / self.arrow_length if link_length / self.arrow_length > 0.3 else 0.3
            arrow_height = self.arrow_length * tan(self.arrow_half_angle)
            arrow_length = self.arrow_length * arrow_scale
            arrow_half_angle = atan2(arrow_height, arrow_length)
            self.arrow_offset = arrow_length  # update the offset so that link endpoint is set at the arrow
        else:
            # No scaling required
            arrow_length = self.arrow_length
            arrow_half_angle = self.arrow_half_angle

        x2 = x1 - arrow_length * cos(arrow_half_angle + alpha_rad)
        y2 = y1 - arrow_length * sin(arrow_half_angle + alpha_rad)
        x3 = x1 - arrow_length * cos(arrow_half_angle - alpha_rad)
        y3 = y1 + arrow_length * sin(arrow_half_angle - alpha_rad)

        arrow_corner2 = QPointF(x2, y2)
        arrow_corner3 = QPointF(x3, y3)
        arrow_poly = QPolygonF([end_point, arrow_corner2, arrow_corner3])
        return arrow_poly

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __goto_ifx_port(self, part: BasePart) -> bool:
        """
        Navigate the Model View to the ifx port corresponding to the given part.
        :param part: The part corresponding to the ifx port to show.
        :return: A boolean indicating that the ifx port was found.
        """
        found_port = False
        parts_path = part.get_parts_path(with_part=False)
        for actor in parts_path:
            if self.scene().content_actor is actor.parent_actor_part:
                self.scene().sig_show_ifx_port.emit(actor, part)
                found_port = True
                break

        return found_port


class LinkSegmentSourceItem(LinkSegmentItem):
    """
    A LinkSegmentItem created from the source anchor and drawn to the target anchor, waypoint, or port.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, link_obj: Decl.LinkSceneObject,
                 part_link: PartLink,
                 source_anchor: LinkAnchorItem,
                 target_anchor: LinkAnchorItem,
                 declutter: bool = False):
        """
        Initializes the link segment connected to the source anchor item.
        :param link_obj: The frontend Link item shown in the scene to which this segment belongs.
        :param part_link: The backend Link part associated with the link_obj.
        :param source_anchor: The source item of this link segment.
        :param target_anchor: The target item of this link segment.
        :param declutter: A flag indicating True if the link is decluttered and False otherwise.
        """
        LinkSegmentItem.__init__(self, link_obj, part_link, declutter)

        self.__draw_arrow = True  # draw arrow at end-point by default
        self.__draw_label = True
        self.__label_len = 0.0
        self._label_scale = 1.0  # used to scale paintable link components (label, arrow)

        self.set_source_anchor_item(source_anchor)
        self.set_target_anchor_item(target_anchor)

        self.setZValue(ZLevelsEnum.link)

        self._arrow_path = QPainterPath()
        self._arrow_path_declutter = QPainterPath()
        self._text_path = QPainterPath()
        self._text_start_point = QPointF()
        self._text_start_point_flipped = QPointF()

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        if not self._draw_link:
            return

        painter.setRenderHints(QPainter.TextAntialiasing | QPainter.Antialiasing | QPainter.HighQualityAntialiasing)

        #DRWA

        #if self.is_highlighted:
        #    self.setZValue(ZLevelsEnum.link_selected)
        #    self._link_pen.setColor(self.COLOR_HIGHLIGHT)
        #    self._arrow_pen.setColor(self.COLOR_HIGHLIGHT)
        #    painter.setBrush(self._highlight_brush)
        #else:
        #    self.setZValue(ZLevelsEnum.link)
        #    self._link_pen.setColor(self.COLOR_DEFAULT)
        #    self._arrow_pen.setColor(self.COLOR_DEFAULT)
        #    painter.setBrush(self._default_brush)
        #    #DRWA
        #    self._label_pen.setColor(self.COLOR_DEFAULT)
        #    self._label_brush.setColor(self.COLOR_DEFAULT)

        if self.is_link_decluttered:
            self.setZValue(ZLevelsEnum.link_decluttered)
            #DRWA
            grey = QColor(200,200,200)
            self._link_pen.setColor(grey)
            self._arrow_pen.setColor(grey)
            painter.setBrush(QBrush(grey, Qt.SolidPattern))
            self._label_pen.setColor(grey)
            self._label_brush.setColor(grey)
        else:
            self.setZValue(ZLevelsEnum.link)
            self._link_pen.setColor(self.COLOR_DEFAULT)
            self._arrow_pen.setColor(self.COLOR_DEFAULT)
            painter.setBrush(self._default_brush)
            #DRWA
            self._label_pen.setColor(self.COLOR_DEFAULT)
            self._label_brush.setColor(self.COLOR_DEFAULT)

        if self.is_highlighted:
            self.setZValue(ZLevelsEnum.link_selected)
            self._link_pen.setColor(self.COLOR_HIGHLIGHT)
            self._arrow_pen.setColor(self.COLOR_HIGHLIGHT)
            painter.setBrush(self._highlight_brush)

        # Draw the link
        painter.setPen(self._link_pen)
        painter.drawPath(self._link_path)

        # Draw the arrowhead
        painter.setPen(self._arrow_pen)

        if self.__draw_arrow:
            # Draw the arrowhead
            painter.drawPath(self._arrow_path)

        if self.is_link_decluttered:
            painter.drawPath(self._arrow_path_declutter)

        # WARNING: since the link label is actually set to the origin of the scene, it must be translated to the link,
        # and oriented with the link. Here, a transform is applied to the link's 'painter' object to accomplish this.
        # Once that happens, anything the painter paints will also have the same transform applied. Therefore, only
        # link label painting should occur after this line.
        # -------------------------------------------------
        # Translate and rotate text label to the position on the link
        if self.__draw_label:
            self.__apply_label_transform(painter)

            # Create a background field behind text
            rect_f = self._text_path.boundingRect().adjusted(-self.PEN_WIDTH, -self.PEN_WIDTH,
                                                             self.PEN_WIDTH, self.PEN_WIDTH)

            if self.is_highlighted:
                # Highlight the background field
                painter.fillRect(rect_f, QBrush(self.COLOR_HIGHLIGHT, Qt.SolidPattern))
            else:
                # Default 'white' background field
                painter.fillRect(rect_f, QBrush(Qt.white, Qt.SolidPattern))

            # Draw the label
            painter.setPen(self._label_pen)
            painter.setBrush(self._label_brush)
            painter.drawPath(self._text_path)

    @override(LinkSegmentBaseItem)
    def calculate_painter_path(self, start_point: QPointF, end_point: QPointF, alpha_rad: float, link_name: str = None):
        """
        Calculates the painter paths for the link, arrow, label, and selection highlight
        :param start_point: The start point of the link based on the intersection with the source anchor frame
        :param end_point: The end point of the link based on the intersection with the target anchor frame
        :param alpha_rad: The angle of the link with respect the the horizontal x-axis
        :param link_name: The name of the link part
        """
        super().calculate_painter_path(start_point, end_point, alpha_rad)

        # Set the link angle for use in other methods
        self._alpha_rad = alpha_rad

        # Arrowhead
        if self.__draw_arrow:
            arrow_poly = self._calculate_arrow_poly(end_point, alpha_rad)
            self._arrow_path = QPainterPath()
            self._arrow_path.addPolygon(arrow_poly)
            self._arrow_path.closeSubpath()

        # Add label to scene origin
        # This will be translated/rotated to the link by QPainter during 'self.paint(...)'.
        scene_origin = QPointF(0, 0)
        self._text_path = QPainterPath()

        if link_name is None:
            link_name = str()

        # Draw link label only if it's less than the length of the line
        self._text_path.addText(scene_origin, get_scenario_font(point_size=7), link_name)
        label_len = QLineF(self._text_path.boundingRect().topLeft(),
                           self._text_path.boundingRect().topRight()).length()
        link_len = QLineF(self._start_point, self._end_point).length() - self.label_offset - self.arrow_length * 2
        self.__label_len = label_len
        self._link_len = link_len

        # Determine label scale factor
        if label_len < link_len:
            self._label_scale = 1.0
        else:
            self._label_scale = link_len / label_len if link_len / label_len >= 0.0 else 0.0
            assert 0.0 <= self._label_scale <= 1.0

        self.__calculate_label_start_position(start_point, alpha_rad, label_len)

        # Calculate the link path
        if self.is_link_decluttered:
            # adjust the end point to just past the end of the label
            orig_end_point = end_point
            end_point = self.__calculate_decluttered_endpoint(start_point, alpha_rad, label_len)

            # determine if the parts are far enough apart to bother drawing the decluttered link
            test_link_line = QLineF(start_point, end_point)
            if self.__can_draw_decluttered_link(test_link_line):
                # draw first part of decluttered link from the source part to just past the label
                self._link_path = QPainterPath(start_point)
                self._link_path.lineTo(end_point)

                # draw second part of delcuttered link that touches the target (a small line that will attach to arrow)
                offset1 = -(self.arrow_offset + self.arrow_stem_offset)
                second_start_point = self._calculate_segment_offset_point(orig_end_point, alpha_rad, offset1)
                offset2 = -self.arrow_stem_offset
                second_end_point = self._calculate_segment_offset_point(orig_end_point, alpha_rad, offset2)
                link_end_line = QPainterPath(second_start_point)
                link_end_line.lineTo(second_end_point)
                self._link_path.addPath(link_end_line)
            else:
                # the decluttered line from source part is touching the target -> so
                # just draw the link from source to target (tell target line not to draw)
                end_point = self._calculate_segment_offset_point(orig_end_point, alpha_rad, -self.arrow_offset)
                self._link_path = QPainterPath(start_point)
                self._link_path.lineTo(end_point)
                self._arrow_path_declutter = QPainterPath()
        else:
            # Calculate the full link line
            if self.__draw_arrow:
                # Offset the link line slightly from arrowhead
                end_point = self._calculate_segment_offset_point(end_point, alpha_rad, -self.arrow_offset)

            self._link_path = QPainterPath(start_point)
            self._link_path.lineTo(end_point)

        # The selectable area of the link
        self._calculate_segment_bounding_rect(start_point, end_point, alpha_rad)

    def draw_arrow(self, draw: bool):
        """
        Shows or hides the arrow at the link end-point.
        :param show: Flag that indicates if the arrow should be shown.
        """
        self.__draw_arrow = draw

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(LinkSegmentBaseItem)
    def _calculate_link_end_points(self):
        """
        Calculates the link path start and end points (super() class) and then the link path.
        """

        # No need to continue if either source or target doesn't exist
        if None in (self._source_anchor_item, self._target_anchor_item):
            return

        self._draw_link = self._can_draw_link()
        if self._draw_link:
            super()._calculate_link_end_points()

        # Use the end points the calculate the path for link
        self.calculate_painter_path(self._start_point, self._end_point, self._alpha_rad, self.objectName())

    _slot_calculate_link_end_points = safe_slot(_calculate_link_end_points)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __calculate_label_start_position(self, start_point: QPointF, alpha_rad: float, label_len: int):
        """
        Determines where along the link to start the link label.
        This will be translated/rotated to the link by QPainter during 'self.paint(...)'.
        :param start_point: The start point as determined by intersection with the target anchor frame
        :param alpha_rad: The angle of the link with respect the the horizontal x-axis
        :param label_len: The length of the label in scenario coordinates.
        """
        # Set label position along the link from the link start point
        start_offset = self.label_offset + self.PEN_WIDTH * 2.0  # <- use 2*PEN_WIDTH to finesse label spacing
        start_offset_flipped = start_offset + label_len

        # Move the label to the middle of the link (otherwise it sits above the link)
        # Subtract the adjustment when the link is quadrants 1 or 4, add when in quadrants 2 or 3 (flipped versions)
        link_thickness = self.PEN_WIDTH
        RAD_90 = radians(90)
        label_adjustment = QPointF(link_thickness * cos(RAD_90 - alpha_rad),
                                   -link_thickness * sin(RAD_90 - alpha_rad))

        # The regular start point is for quadrants 1 or 4, and flipped for quadrants 2 or 3
        # The flipped version moves the label further up the link from the start point as it will be rotated
        # around it's start point to appear right-side-up when the link is rotated into quad 2 and 3.
        label_start_point = QPointF(start_offset * cos(alpha_rad), start_offset * sin(alpha_rad))
        label_start_point_flipped = QPointF(start_offset_flipped * cos(alpha_rad),
                                            start_offset_flipped * sin(alpha_rad))

        self._text_start_point = start_point + label_start_point - label_adjustment
        self._text_start_point_flipped = start_point + label_start_point_flipped + label_adjustment

    def __calculate_decluttered_endpoint(self, start_point: QPointF, alpha_rad: float, label_len: int) -> QPointF:
        """
        Calculates the shortened end-point of the link for decluttering and its arrowhead.
        :param start_point: The link's start point.
        :param alpha_rad: The angle of the link with respect to the horizontal x-axis (radians).
        :param label_len: The length of the label in scenario coordinates.
        :returns: The end point of the bottom link half set to an offset off the link label.
        """
        # Shorten the link to the end just ahead of the label
        link_offset = self.label_offset + label_len + self.arrow_stem_offset + self.arrow_offset
        new_end_point = self._calculate_segment_offset_point(start_point, alpha_rad, link_offset)

        # Place the arrowhead just ahead of the end-point calculated above
        offset = link_offset + self.arrow_offset
        arrow_end_point = self._calculate_segment_offset_point(start_point, alpha_rad, offset)
        arrow_poly_declutter = self._calculate_arrow_poly(arrow_end_point, alpha_rad)
        self._arrow_path_declutter = QPainterPath()
        self._arrow_path_declutter.addPolygon(arrow_poly_declutter)
        self._arrow_path_declutter.closeSubpath()

        return new_end_point

    def __can_draw_decluttered_link(self, src_decluttered_link_line: QLineF) -> bool:
        """
        Determines if the decluttered link should be drawn. If the line on the source anchor intersects the target
        anchor, then the decluttered link should not be drawn.
        :param src_decluttered_link_line: The decluttered link line emanating from the source part.
        :return: True if the source decluttered link line does not intersect the target, and False otherwise.
        """
        # construct the target boundary rect edges to test for intersection
        # buffer added to avoid small overlap of anchor by decluttered link in Model View before intersection detected
        # this probably occurs since the link line passed in doesn't include arrow component lengths
        BUFFER = 15.0
        target_rect = self._target_anchor_item.link_boundary_rect.adjusted(-BUFFER, -BUFFER, BUFFER, BUFFER)
        left_edge = QLineF(target_rect.topLeft(), target_rect.bottomLeft())
        top_edge = QLineF(target_rect.topLeft(), target_rect.topRight())
        right_edge = QLineF(target_rect.topRight(), target_rect.bottomRight())
        bottom_edge = QLineF(target_rect.bottomLeft(), target_rect.bottomRight())

        # search for intersections with the given src decluttered link
        target_edges = [left_edge, top_edge, right_edge, bottom_edge]
        intersect_point = None
        for edge in target_edges:
            if edge.intersect(src_decluttered_link_line, intersect_point) == QLineF.BoundedIntersection:
                # the source decluttered link line touches the target, so return False
                return False

        return True  # no bounded intersections found

    def __apply_label_transform(self, painter: QPainter):
        """
        Applies a translation and rotation to the link's label to move it from the scene origin to the link.
        :param painter: The painter object of this link.
        """
        alpha_degrees = degrees(self._alpha_rad)
        if (0 > alpha_degrees >= -90) or (0 <= alpha_degrees < 90):
            painter.translate(self._text_start_point)  # move label from origin to start point
            painter.rotate(alpha_degrees)  # rotation label to be parallel with link
            # if the label is being scaled, move label down link to make more room from label
            painter.translate(QPointF(-self.label_offset * (1.0 - self._label_scale), 0.0))
        else:
            painter.translate(self._text_start_point_flipped)  # move label from origin to start point
            painter.rotate(alpha_degrees + 180.0)  # rotation label to be parallel with link
            # if the label is being scaled, move label down link to make more room from label
            painter.translate(QPointF(self.label_offset * (1.0 - self._label_scale), 0.0))
            # since scaling the label does so at the top left corner, need to shift the label right by the scaled amt
            painter.translate(QPointF(self.__label_len * (1.0 - self._label_scale), 0.0))

        painter.scale(self._label_scale, 1.0)  # scale the label to shrink it as link length -> 0


class LinkSegmentTargetItem(LinkSegmentItem):
    """
    The LinkSegmentItem connecting to the target LinkAnchorItem.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, link_obj: Decl.LinkSceneObject,
                 part_link: PartLink,
                 source_anchor: LinkAnchorItem,
                 target_anchor: LinkAnchorItem,
                 declutter: bool = False):
        """
        Initializes the link segment connected to the target anchor item.
        :param link_obj: The frontend Link item shown in the scene to which this segment belongs.
        :param part_link: The backend Link part associated with the link_obj.
        :param source_anchor: The source item of this link segment.
        :param target_anchor: The target item of this link segment.
        :param declutter: A flag indicating True if the link is decluttered and False otherwise.
        """
        LinkSegmentItem.__init__(self, link_obj, part_link, declutter)
        self.set_source_anchor_item(source_anchor)
        self.set_target_anchor_item(target_anchor)
        self.setZValue(ZLevelsEnum.link)
        self._arrow_path = QPainterPath()

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        if not self._draw_link:
            return

        painter.setRenderHints(QPainter.TextAntialiasing | QPainter.Antialiasing | QPainter.HighQualityAntialiasing)

        if self.is_highlighted:
            self.setZValue(ZLevelsEnum.link_selected)
            self._link_pen.setColor(self.COLOR_HIGHLIGHT)
            self._arrow_pen.setColor(self.COLOR_HIGHLIGHT)
            painter.setBrush(self._highlight_brush)
        else:
            self.setZValue(ZLevelsEnum.link)
            self._link_pen.setColor(self.COLOR_DEFAULT)
            self._arrow_pen.setColor(self.COLOR_DEFAULT)
            painter.setBrush(self._default_brush)

        if self.is_link_decluttered:
            self.setZValue(ZLevelsEnum.link_decluttered)

        # Draw the link
        painter.setPen(self._link_pen)
        painter.drawPath(self._link_path)

        # Draw the arrowhead
        painter.setPen(self._arrow_pen)
        painter.drawPath(self._arrow_path)

    @override(LinkSegmentBaseItem)
    def calculate_painter_path(self, start_point: QPointF, end_point: QPointF, alpha_rad: float, link_name: str = None):
        super().calculate_painter_path(start_point, end_point, alpha_rad)

        # Set the link angle for use in other methods
        self._alpha_rad = alpha_rad

        # Arrowhead
        arrow_poly = self._calculate_arrow_poly(end_point, alpha_rad)
        self._arrow_path = QPainterPath()
        self._arrow_path.addPolygon(arrow_poly)
        self._arrow_path.closeSubpath()

        # Calculate the link path
        if self.is_link_decluttered:
            # draw nothing: source target link item will paint the declutted link
            self._link_path = QPainterPath()
            self._arrow_path = QPainterPath()
            self._bounding_rect_path = QPainterPath()  # cannot select link segment
        else:
            # Calculate the full link line from source to arrowhead
            offset = -self.arrow_offset  # Offset the link line slightly from arrowhead
            adjusted_end_point = self._calculate_segment_offset_point(end_point, alpha_rad, offset)
            self._link_path = QPainterPath(start_point)
            self._link_path.lineTo(adjusted_end_point)
            self._calculate_segment_bounding_rect(start_point, end_point, alpha_rad)  # calc selectable area of segment

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(LinkSegmentBaseItem)
    def _calculate_link_end_points(self):
        # No need to continue if either source or target doesn't exist
        if None in (self._source_anchor_item, self._target_anchor_item):
            return

        self._draw_link = self._can_draw_link()
        if self._draw_link:
            super()._calculate_link_end_points()

        # Use the end points the calculate the path for link
        self.calculate_painter_path(self._start_point, self._end_point, self._alpha_rad, self.objectName())

    _slot_calculate_link_end_points = safe_slot(_calculate_link_end_points)


class LinkSegmentWaypointItem(LinkSegmentItem):
    """
    A LinkSegmentItem created between two waypoint items.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, link_obj: Decl.LinkSceneObject,
                 part_link: PartLink,
                 source_anchor: LinkAnchorItem,
                 target_anchor: LinkAnchorItem,
                 declutter: bool = False):
        """
        Initializes the link segment connecting two waypoint anchor items.
        :param link_obj: The frontend Link item shown in the scene to which this segment belongs.
        :param part_link: The backend Link part associated with the link_obj.
        :param source_anchor: The source item of this link segment.
        :param target_anchor: The target item of this link segment.
        :param declutter: A flag indicating True if the link is decluttered and False otherwise.
        """
        LinkSegmentItem.__init__(self, link_obj, part_link, declutter)

        self.set_source_anchor_item(source_anchor)
        self.set_target_anchor_item(target_anchor)

        self.setZValue(ZLevelsEnum.link)
        self.setFlags(QGraphicsItem.ItemIsFocusable | QGraphicsItem.ItemIsSelectable)

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHints(QPainter.TextAntialiasing | QPainter.Antialiasing | QPainter.HighQualityAntialiasing)

        if self.is_highlighted:
            self.setZValue(ZLevelsEnum.link_selected)
            self._link_pen.setColor(self.COLOR_HIGHLIGHT)
            painter.setBrush(self._highlight_brush)
        else:
            self.setZValue(ZLevelsEnum.link)
            self._link_pen.setColor(self.COLOR_DEFAULT)
            painter.setBrush(self._default_brush)

        # Draw the link
        painter.setPen(self._link_pen)
        painter.drawPath(self._link_path)

    @override(LinkSegmentBaseItem)
    def calculate_painter_path(self, start_point: QPointF, end_point: QPointF, alpha_rad: float, link_name: str = None):
        super().calculate_painter_path(start_point, end_point, alpha_rad)

        # Set the link angle for use in other methods
        self._alpha_rad = alpha_rad

        # Calculate the link path
        if self.is_link_decluttered:
            self._link_path = QPainterPath()
            self._bounding_rect_path = QPainterPath()  # cannot select link segment
        else:
            self._link_path = QPainterPath(start_point)
            self._link_path.lineTo(end_point)
            self._calculate_segment_bounding_rect(start_point, end_point, alpha_rad)  # calc selectable area of segment

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(LinkSegmentBaseItem)
    def _calculate_link_end_points(self):
        # No need to continue if either source or target doesn't exist
        if None in (self._source_anchor_item, self._target_anchor_item):
            return

        # Calculate the link start and end points and the angle with x-axis
        # based on source and target anchor frames
        super()._calculate_link_end_points()

        # Use the end points the calculate the path for link
        self.calculate_painter_path(self._start_point, self._end_point, self._alpha_rad, self.objectName())

    _slot_calculate_link_end_points = safe_slot(_calculate_link_end_points)


class LinkWaypointItem(IInteractiveItem, LinkAnchorItem):
    """
    This class provides the graphics-object components and management logic for waypoint items.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    DRAGGABLE = True
    MULTI_SELECTABLE = True
    COLOR_DEFAULT = PART_ICON_COLORS['waypoint']
    COLOR_HIGHLIGHT = QColor(0, 255, 0, 255)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, link_obj: Decl.LinkSceneObject, waypoint: LinkWaypoint, parent: QGraphicsItem = None):
        """
        Initialize the waypoint anchor item appearing between two link segments.
        :param link_obj: The link object to which this waypoint belongs.
        :param waypoint: The waypoint to set in this graphics item.
        :param parent: The parent item of this waypoint, if any.
        """
        IInteractiveItem.__init__(self)
        LinkAnchorItem.__init__(self, parent=parent)
        self._set_flags_item_change_link_anchor()
        self._set_flags_item_change_interactive()
        assert self.flags() & (QGraphicsItem.ItemIsFocusable | QGraphicsItem.ItemIsSelectable | self.ItemIsMovable)
        assert self.flags() & QGraphicsItem.ItemSendsScenePositionChanges

        self.__waypoint = waypoint
        self.__waypoint_size = QSize(WAYPOINT_SIZE_PIX, WAYPOINT_SIZE_PIX)

        # Drawing objects
        #DRWA
        #self.__default_brush = QBrush(LinkWaypointItem.COLOR_DEFAULT, Qt.SolidPattern)
        self.__default_brush = QBrush(PART_ICON_COLORS[waypoint.part_type_name].darker(175), Qt.SolidPattern)
        self.__highlight_brush = QBrush(LinkWaypointItem.COLOR_HIGHLIGHT, Qt.SolidPattern)

        # Waypoint bounds and shape
        self.__bounding_rect_path = QPainterPath()
        self.__waypoint_path = QPainterPath()

        # Context menu
        self.__action_delete = create_action(self, "Delete", tooltip="Delete link",
                                             connect=self.slot_on_action_delete)

        self.__link_obj = link_obj
        self.__is_waypoint_decluttered = link_obj.is_link_decluttered

        # Add to scene
        self.__waypoint.signals.sig_position_changed.connect(self._slot_on_position_changed)
        x, y = waypoint.position
        self._on_position_changed(x, y)
        self._calculate_painter_path()

    @override(QGraphicsItem)
    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, new_value: QVariant) -> QVariant:
        LinkAnchorItem.itemChange(self, change, new_value)
        return IInteractiveItem.itemChange(self, change, new_value)

    @override(QGraphicsObject)
    def type(self) -> int:
        return CustomItemEnum.waypoint.value

    @override(QGraphicsItem)
    def boundingRect(self) -> QRectF:
        margin = 5.0  # Increase the margin to improve waypoint selectability
        return self.__bounding_rect_path.boundingRect().adjusted(-margin, -margin, margin, margin)

    @override(LinkAnchorItem)
    def get_link_boundary_rect(self) -> QRectF:
        return self.sceneBoundingRect()

    @override(QGraphicsItem)
    def shape(self) -> QPainterPath:
        return self.__bounding_rect_path

    @override(IInteractiveItem)
    def get_scenario_object(self) -> LinkWaypoint:
        return self.__waypoint

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHints(QPainter.Antialiasing | QPainter.HighQualityAntialiasing)
        painter.setPen(Qt.NoPen)

        if self.is_highlighted:
            self.setZValue(ZLevelsEnum.waypoint_selected)
            painter.setBrush(self.__highlight_brush)
        else:
            self.setZValue(ZLevelsEnum.waypoint)
            painter.setBrush(self.__default_brush)

        painter.drawPath(self.__waypoint_path)

    @override(QGraphicsItem)
    def contextMenuEvent(self, evt: QGraphicsSceneContextMenuEvent):
        self.scene().set_selection(self)
        menu = QMenu()
        menu.addAction(self.__action_delete)
        menu.exec(evt.screenPos())

    @override(LinkAnchorItem)
    def get_contact_point(self, anchor_point: QPointF, link_line: QLineF) -> QPointF:
        return self.sceneBoundingRect().center()

    def get_waypoint(self) -> LinkWaypoint:
        """
        Returns the waypoint object.
        """
        return self.__waypoint

    def get_link_obj(self) -> Decl.LinkSceneObject:
        """
        Returns the waypoint's link object.
        """
        return self.__link_obj

    def get_waypoint_decluttered(self) -> bool:
        """
        Returns the declutter flag.
        :return: True if decluttered and False, otherwise.
        """
        return self.__is_waypoint_decluttered

    def set_waypoint_decluttered(self, is_decluttered: bool):
        """
        Sets the declutter flag.
        :return: True if decluttered and False, otherwise.
        """
        self.__is_waypoint_decluttered = is_decluttered
        self._calculate_painter_path()

    def on_action_delete(self):
        """
        Remove the link from the scene.
        """
        self.scene().delete_selected_waypoints()

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    waypoint = property(get_waypoint)
    link_obj = property(get_link_obj)
    is_waypoint_decluttered = property(get_waypoint_decluttered, set_waypoint_decluttered)
    link_boundary_rect = property(get_link_boundary_rect)

    slot_on_action_delete = safe_slot(on_action_delete)

    # --------------------------- instance PROTECTED properties & safe_slots ----------------------------

    def _calculate_painter_path(self):
        """
        Calculates the paths to draw the waypoint and it's bounding rectangle.
        """
        self.prepareGeometryChange()
        self.__bounding_rect_path = QPainterPath()
        self.__waypoint_path = QPainterPath()

        outer = QRectF(-self.__waypoint_size.width() / 2.0,
                       -self.__waypoint_size.height() / 2.0,
                       self.__waypoint_size.width(),
                       self.__waypoint_size.height())

        if not self.is_waypoint_decluttered:
            self.__bounding_rect_path.addRect(outer)
            self.__waypoint_path.addEllipse(outer)

    def _on_position_changed(self, x: float, y: float):
        """
        Update the front-end position if different from back-end.
        :param x: x scenario coordinate.
        :param y: y scenario coordinate.
        """
        backend_scene_pos = map_from_scenario(Position.from_tuple((x, y)))
        scene_pos = self.pos()
        if scene_pos != backend_scene_pos:
            self.setPos(backend_scene_pos)

    _slot_on_position_changed = safe_slot(_on_position_changed)


class LinkSceneObject(QObject):
    """
    This class provides link segment management between the link segments and waypoints such as adding waypoints and/or
    segments to the link, removing them, link highlighting, and link decluttering. The LinkSceneObject is composed of,
        - LinkSegmentSourceItem: one link from the source LinkAnchorItem (always present).
        - LinkSegmentTargetItem: one link to the target LinkAnchorItem (present if more than one segments).
        - LinkSegmentWaypointsItem: one or more links in-between two waypoints (present if more than two segments).
        - LinkWaypointItems: one or more waypoints in-between the segments (present if more than one segment).
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, scene: QGraphicsScene,
                 part_link: PartLink,
                 source_anchor: LinkAnchorItem,
                 target_anchor: LinkAnchorItem):
        """
        Initializes the scene object representing the link including all segments and waypoints.
        :param scene: The 2D scene in which the link is object is created.
        :param part_link: The back-end link part
        :param source_anchor: The front-end widget or item from which link creation is started (link start-point)
        :param target_anchor: The connected front-end widget or item (link end-point)
        """
        super().__init__()

        self._part_link = None
        self._name = None

        # Used for the in-editor link renaming
        self.__temp_name = None

        # Set the link line drawn in this class to valid
        # Base class link is 'invalid' by default
        self._valid_line = True

        # The scene this link is in
        self.__scene = scene

        # The two end-point anchors of this link item
        self.__link_source_anchor = None
        self.__link_target_anchor = None

        self.__is_link_decluttered = False
        self.__link_segment_items = None
        self.__link_waypoint_items = None
        self.__source_link_segment_items = None
        self.__target_link_segment_items = None

        # Disable highlighting on init
        self.__enable_link_highlighting = False

        # Init the first segment of this link item
        assert part_link is not None
        self.set_source_segment(part_link, source_anchor, target_anchor)
        self.__init_waypoints()

        # Show link decluttered if flag is True
        if self._part_link.declutter:
            self.__toggle_declutter(self._part_link.declutter)

        part_link.signals.sig_name_changed.connect(self.__slot_set_name)
        part_link.signals.sig_temp_name_changed.connect(self.__slot_set_temp_name)
        part_link.signals.sig_link_decluttering_changed.connect(self.__slot_toggle_declutter)
        part_link.signals.sig_waypoint_added.connect(self.__slot_on_waypoint_added)
        part_link.signals.sig_waypoint_removed.connect(self.__slot_on_waypoint_removed)
        part_link.signals.sig_target_changed.connect(self.__slot_on_retarget_link)

        # Enable highlighting now init is complete
        self.__enable_link_highlighting = True

    def on_part_link_removed(self):
        """
        Method called when the backend link is removed.
        """
        log.debug("LinkSceneObject cleanup for link {}", self._part_link)

        for link_segment_item in self.__link_segment_items:
            link_segment_item.dispose()

        for waypoint_item in self.__link_waypoint_items:
            waypoint_item.dispose()

        self._part_link.signals.sig_name_changed.disconnect(self.__slot_set_name)
        self._part_link.signals.sig_temp_name_changed.disconnect(self.__slot_set_temp_name)
        self._part_link.signals.sig_link_decluttering_changed.disconnect(self.__slot_toggle_declutter)
        self._part_link.signals.sig_waypoint_added.disconnect(self.__slot_on_waypoint_added)
        self._part_link.signals.sig_waypoint_removed.disconnect(self.__slot_on_waypoint_removed)
        self._part_link.signals.sig_target_changed.disconnect(self.__slot_on_retarget_link)

        self.__link_segment_items = None
        self.__link_waypoint_items = None
        self.__source_link_segment_items = None
        self.__target_link_segment_items = None
        self._part_link = None

    def set_source_segment(self, part_link: PartLink, source_anchor: LinkAnchorItem, target_anchor: LinkAnchorItem):
        """
        Sets the back-end link part and name to self, and creates the source link object and adds it to the Scene.
        :param part_link: The back-end link part
        :param source_anchor: The source item of this link segment.
        :param target_anchor: The target item of this link segment.
        """
        assert (self._part_link is None)
        self._part_link = part_link
        self.__link_source_anchor = source_anchor
        self.__link_target_anchor = target_anchor
        self.__link_segment_items = []
        self.__link_waypoint_items = []

        # Init source link segment
        source_link_segment = LinkSegmentSourceItem(self, part_link, source_anchor, target_anchor, False)
        source_link_segment_deluttered = LinkSegmentSourceItem(self, part_link, source_anchor, target_anchor, True)
        self.__source_link_segment_items = [source_link_segment, source_link_segment_deluttered]
        self.__link_segment_items.append(source_link_segment)
        self.__set_name(part_link.name)

        self.__scene.addItem(source_link_segment)

    def add_waypoint(self, link_segment: LinkSegmentItem):
        """
        Requests the back-end to create a waypoint.
        :param link_segment: The segment on to which the waypoint will be inserted.
        """
        idx = self.__link_segment_items.index(link_segment)
        position = map_to_scenario(link_segment.mid_point)
        add_waypoint_command = AddWaypointCommand(self._part_link, position, idx)
        scene_undo_stack().push(add_waypoint_command)

    def remove_waypoint(self, waypoint_item: LinkWaypointItem):
        """
        Requests the back-end to remove a waypoint.
        :param waypoint_item: The waypoint to remove.
        """
        waypoint = waypoint_item.waypoint
        remove_waypoint_command = RemoveWaypointCommand(self._part_link, waypoint)
        scene_undo_stack().push(remove_waypoint_command)

    def remove_waypoints(self, waypoint_items: List[LinkWaypointItem]):
        """
        Requests the back-end to remove the selected waypoints.
        :param waypoint_items: The list of waypoints to remove.
        """
        map_links_to_waypoints = dict()
        waypoints = [waypoint_item.waypoint for waypoint_item in waypoint_items]
        map_links_to_waypoints[self._part_link] = waypoints
        remove_waypoints_command = RemoveWaypointsCommand(self.__scene.content_actor, map_links_to_waypoints)
        scene_undo_stack().push(remove_waypoints_command)

    def remove_all_waypoints(self):
        """
        Remove all waypoints in this link.
        """
        remove_all_waypoints_command = RemoveAllWaypointsCommand(self._part_link)
        scene_undo_stack().push(remove_all_waypoints_command)

    def retarget_link(self):
        """
        Set a new target anchor for this link.
        """
        if not self.__is_link_decluttered and self.__link_waypoint_items:
            # If in normal (not decluttered) mode and if there are waypoints,
            # use the last waypoint as the source during retargeting
            retarget_source = self.__link_waypoint_items[-1]
        else:
            # otherwise use the source link anchor for decluttered links, or links with no waypoints
            retarget_source = self.__link_source_anchor

        orig_source = self.__link_source_anchor
        orig_target = self.__link_target_anchor
        self.__scene.start_link_retarget(self._part_link, retarget_source, orig_source, orig_target)

    def on_segment_selected(self, is_highlighted: bool):
        """
        Toggles highlighting on or off for all segments and waypoints managed by this Link Manager.
        :param is_highlighted: Flag indicates if the link is highlighted or not.
        """
        for segment in self.__link_segment_items:
            if segment.is_highlighted != is_highlighted:
                segment.set_highlighted(is_highlighted)

        for waypoint in self.__link_waypoint_items:
            if waypoint.is_highlighted != is_highlighted:
                waypoint.set_highlighted(is_highlighted)

    def get_link_source_anchor(self) -> LinkAnchorItem:
        """Returns the source link anchor."""
        return self.__link_source_anchor

    def get_link_target_anchor(self) -> LinkAnchorItem:
        """Returns the source link anchor."""
        return self.__link_target_anchor

    def get_part_link(self) -> PartLink:
        return self._part_link

    def get_num_segments(self) -> int:
        """Returns the number of segments."""
        return len(self.__link_segment_items)

    def get_segment_items(self) -> List[LinkSegmentItem]:
        """Returns a list of link segment items."""
        return self.__link_segment_items

    def get_num_waypoints(self) -> int:
        """Returns the number of waypoints."""
        return len(self.__link_waypoint_items)

    def get_waypoint_items(self) -> List[LinkWaypointItem]:
        """Returns a list of link segment items."""
        return self.__link_waypoint_items

    def get_link_decluttered(self) -> bool:
        """
        Returns the declutter flag.
        :return: True if decluttered and False, otherwise.
        """
        return self.__is_link_decluttered

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    link_source_anchor = property(get_link_source_anchor)
    link_target_anchor = property(get_link_target_anchor)
    part_link = property(get_part_link)
    is_link_decluttered = property(get_link_decluttered)
    num_segments = property(get_num_segments)
    num_waypoints = property(get_num_waypoints)
    segment_items = property(get_segment_items)
    waypoint_items = property(get_waypoint_items)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __set_name(self, name: str):
        """
        Slot called when backend link name changes.
        """
        self._name = name
        self.__show_displayed_name()

    def __set_temp_name(self, name: str):
        """
        Slot called when backend link temp name changes.
        :param name: The new temp name
        """
        self.__temp_name = name
        self.__show_displayed_name()

    def __show_displayed_name(self):
        """
        This function displays a link name on the 2d view. The displayed link name may be different
        from its real name. If the link name is changed inside an editor, the real name is prefixed with a star "* "
        to form its displayed name.
        """
        name = self._name if self.__temp_name is None or self.__temp_name == '' else "* " + self._name
        # Rename all segments currently displayed
        for segment in self.__link_segment_items:
            segment.setObjectName(name)

        # Rename the two source segments (normal and decluttered)
        for source_segment in self.__source_link_segment_items:
            source_segment.setObjectName(name)

        self.__link_segment_items[0]._calculate_link_end_points()

    def __toggle_declutter(self, declutter: bool):
        """
        Responds to back-end link decluttering flag redrawing either the full link or the decluttered link.
        :param declutter: A boolean flag indicating a decluttered link (True) or regular link (False).
        """
        self.__is_link_decluttered = declutter

        # Swap decluttered and non-decluttered source and target segments
        if len(self.__link_segment_items) > 1:

            # Deselect all segments:
            # As segments will be removed and added from the scene, and since we
            # don't know which segment the user clicked to select the link, remove
            # all selection. The link will be reselected at the end by selecting the
            # first segment.
            for segment in self.__link_segment_items:
                if segment.isSelected:
                    segment.setSelected(False)

            first_segment = self.__link_segment_items[0]
            self.__scene.removeItem(first_segment)

            last_segment = self.__link_segment_items[-1]
            self.__scene.removeItem(last_segment)

            if declutter:
                first_segment = self.__source_link_segment_items[DeclutterEnum.decluttered]
                last_segment = self.__target_link_segment_items[DeclutterEnum.decluttered]
                self.__link_segment_items[0] = first_segment
                self.__link_segment_items[-1] = last_segment
            else:
                first_segment = self.__source_link_segment_items[DeclutterEnum.normal]
                last_segment = self.__target_link_segment_items[DeclutterEnum.normal]
                self.__link_segment_items[0] = first_segment
                self.__link_segment_items[-1] = last_segment

            self.__scene.addItem(first_segment)
            self.__scene.addItem(last_segment)

        # Refresh all segments to show appropriate link setting
        for segment in self.__link_segment_items:
            segment.is_link_decluttered = declutter

        for waypoint in self.__link_waypoint_items:
            waypoint.is_waypoint_decluttered = declutter

        # Select the first segment
        if self.__enable_link_highlighting:
            self.__scene.clearSelection()
            self.__link_segment_items[0].setSelected(True)

    def __init_waypoints(self):
        """
        Initialize the waypoints of this link.
        """
        num_waypoints = len(self._part_link.waypoints)
        for index in range(0, num_waypoints):
            self.__on_waypoint_added(index)

        if self.__link_waypoint_items:
            # Enable waypoint context actions for all segments
            for segment in self.__link_segment_items:
                segment.enable_remove_all_waypoints_action(True)

    def __add_new_link_segment(self, anchor_source: LinkAnchorItem,
                               anchor_target: LinkAnchorItem,
                               index: int) -> LinkSegmentItem:
        """
        Adds a new link segment to this link.
        :param anchor_source: The start of the link segment.
        :param anchor_target: The target of the link segment.
        :param index: The index of the first segment in the list of link segments.
        :return: The new segment item.
        """

        # This new segment can only be added when the link is not decluttered
        # so there is no need to consider the decluttered case
        assert not self.__is_link_decluttered

        if len(self.__link_segment_items) == 1:
            # Hide the arrow on the source link segment
            self.__link_segment_items[0].draw_arrow(False)

            # Add a new 'target' segment item
            target_link_segment = LinkSegmentTargetItem(self,
                                                        self._part_link,
                                                        anchor_source,
                                                        anchor_target,
                                                        declutter=False)
            target_link_segment_deluttered = LinkSegmentTargetItem(self,
                                                                   self._part_link,
                                                                   self.__link_source_anchor,
                                                                   self.__link_target_anchor,
                                                                   declutter=True)
            self.__target_link_segment_items = [target_link_segment, target_link_segment_deluttered]
            new_link_segment = target_link_segment

        else:
            # Add a new 'waypoint' segment item
            new_link_segment = LinkSegmentWaypointItem(self,
                                                       self._part_link,
                                                       anchor_source,
                                                       anchor_target,
                                                       self.__is_link_decluttered)

        self.__link_segment_items.insert(index, new_link_segment)
        self.__scene.addItem(new_link_segment)

        # Enable waypoint actions on each new segment
        new_link_segment.enable_remove_all_waypoints_action(True)
        if len(self.__link_segment_items) == 2:
            # Enable waypoint actions from the first segment
            self.__link_segment_items[0].enable_remove_all_waypoints_action(True)
            # Refresh the end-point calculations
            self.__link_segment_items[0]._calculate_link_end_points()
            self.__link_segment_items[1]._calculate_link_end_points()

        return new_link_segment

    def __on_waypoint_added(self, index: int):
        """
        When a waypoint has been added to the link, this method divides the link segment
        into two and inserts a waypoint between them.
        :param index: The index of the waypoint that was added.
        """
        assert self.__link_segment_items is not None

        # Get the waypoint
        waypoint = self._part_link.get_waypoint(index)
        waypoint_item = LinkWaypointItem(self, waypoint)

        if len(self.__link_segment_items) > 1 and self.__link_segment_items[index] == self.__link_segment_items[-1]:
            # The 'target' (last) link segment was selected, so insert the waypoint BEFORE it
            segment_item2 = self.__link_segment_items[index]
            source_anchor = segment_item2.source_anchor_item
            segment_item2.source_anchor_item = waypoint_item
            # insert new segment before the waypoint (i.e. at 'index')
            self.__add_new_link_segment(source_anchor, waypoint_item, index)
        else:
            # Insert the waypoint AFTER the selected 'source' link or 'waypoint' link segment
            segment_item1 = self.__link_segment_items[index]
            target_anchor = segment_item1.target_anchor_item
            segment_item1.target_anchor_item = waypoint_item
            # insert new segment after the waypoint (i.e. at 'index + 1')
            self.__add_new_link_segment(waypoint_item, target_anchor, index + 1)

        self.__link_waypoint_items.insert(index, waypoint_item)
        self.__scene.addItem(waypoint_item)
        if self.__enable_link_highlighting:
            self.__scene.set_selection(waypoint_item)

    def __on_waypoint_removed(self, index: int):
        """
        When a waypoint has been removed from the link, this method removes the waypoint and replaces the two link
        segments with a single link segment.
        :param index: The index of the waypoint to remove.
        """
        # This new segment can only be added when the link is not decluttered
        # so there is no need to consider the decluttered case
        assert not self.__is_link_decluttered

        # Remove one of the link segments, and reset the source or target anchor for the remaining segment
        if len(self.__link_waypoint_items) > 1 and self.__link_waypoint_items[index] == self.__link_waypoint_items[-1]:
            # The waypoint on the target-segment is being removed: remove the link segment BEFORE it and
            # connect the target segment to the removed waypoint's source anchor
            segment_to_remove = self.__link_segment_items[index]
            source_anchor_to_connect = segment_to_remove.source_anchor_item
            self.__link_segment_items.remove(segment_to_remove)
            connect_segment = self.__link_segment_items[-1]
            connect_segment.source_anchor_item = source_anchor_to_connect

        else:
            # A waypoint other than the one connected to the target segment is being removed:
            # remove the link segment AFTER the removed waypoint and connect the remaining segment to the
            # removed waypoint's target anchor
            segment_to_remove = self.__link_segment_items[index + 1]
            target_anchor_to_connect = segment_to_remove.target_anchor_item
            self.__link_segment_items.remove(segment_to_remove)
            connect_segment = self.__link_segment_items[index]
            connect_segment.target_anchor_item = target_anchor_to_connect

            if len(self.__link_segment_items) == 1:
                self.__link_segment_items[0].draw_arrow(True)

        # Remove the waypoint from the link item and the scene
        waypoint_item_to_remove = self.__link_waypoint_items[index]
        self.__link_waypoint_items.remove(waypoint_item_to_remove)

        if not self.__link_waypoint_items:
            # Disable waypoint actions on the first segment if there are no more waypoints
            self.__link_segment_items[0].enable_remove_all_waypoints_action(False)

        waypoint_item_to_remove.dispose()
        segment_to_remove.dispose()
        connect_segment._calculate_link_end_points()

    def __on_retarget_link(self):
        """
        Update the link to connect to the new target.
        """
        # Changes the target on the current 'target' link
        target_part_frame = self._part_link.target_part_frame
        target_link_anchor_item = self.__scene.find_link_endpoint_item(target_part_frame.part)
        last_segment = self.__link_segment_items[-1]
        last_segment.target_anchor_item = target_link_anchor_item
        self.__link_target_anchor = target_link_anchor_item

        # Update the decluttered 'source' link
        source_segment_decluttered = self.__source_link_segment_items[DeclutterEnum.decluttered]
        source_segment_decluttered.target_anchor_item = target_link_anchor_item

        if len(self.__link_segment_items) > 1:

            if self.__is_link_decluttered:
                # Decluttered mode -> update the hidden normal 'target' segment
                link_segment_normal = self.__target_link_segment_items[DeclutterEnum.normal]
                link_segment_normal.target_anchor_item = target_link_anchor_item
            else:
                # Normal mode (not declutteredd) -> update the hidden decluttered 'target' segment
                target_segment_decluttered = self.__target_link_segment_items[DeclutterEnum.decluttered]
                target_segment_decluttered.target_anchor_item = target_link_anchor_item

        # Select the first segment
        if self.__enable_link_highlighting:
            # De-select the new target part
            self.__scene.clearSelection()
            self.__link_segment_items[0].setSelected(True)

    __slot_set_name = safe_slot(__set_name)
    __slot_set_temp_name = safe_slot(__set_temp_name)
    __slot_toggle_declutter = safe_slot(__toggle_declutter)
    __slot_on_waypoint_added = safe_slot(__on_waypoint_added)
    __slot_on_waypoint_removed = safe_slot(__on_waypoint_removed)
    __slot_on_retarget_link = safe_slot(__on_retarget_link)


class PartLinkTargetSelLineItem(ICustomItem, LinkSegmentBaseItem):
    """
    Creates a temporary link to allow user to select a start and end link anchor.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        """
        Initializes the target selection line item displayed while creating a new link.
        """
        ICustomItem.__init__(self)
        LinkSegmentBaseItem.__init__(self)

        self.setZValue(ZLevelsEnum.link_creation_line)
        self.setObjectName('Selection-line to part-link target')

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setPen(self._link_pen)
        painter.setBrush(QBrush(self.COLOR_DEFAULT, Qt.SolidPattern))
        painter.setRenderHints(QPainter.TextAntialiasing | QPainter.Antialiasing | QPainter.HighQualityAntialiasing)
        painter.drawPath(self._link_path)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(LinkSegmentBaseItem)
    def _calculate_link_end_points(self):
        # No need to continue if either source or target doesn't exist
        if None in (self._source_anchor_item, self._target_anchor_item):
            return

        self._draw_link = self._can_draw_link()
        if self._draw_link:
            super()._calculate_link_end_points()

        self.prepareGeometryChange()
        self._bounding_rect_path = QPainterPath()

        self._link_path = QPainterPath(self._start_point)
        self._link_path.lineTo(self._end_point)

        link_rect = QRectF(self._start_point, self._end_point)
        self._bounding_rect_path.addRect(link_rect)

    _slot_calculate_link_end_points = safe_slot(_calculate_link_end_points)


class PartLinkTargetMarkerItem(LinkAnchorItem):
    """
    A item which tracks mouse movements and indicates to the user whether it is possible
    to link to an item under it. Its appearance changes depending on whether it is over
    something that is linkable.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    LINK_VALID_SVG = get_icon_path("link_target_ok.svg")
    LINK_INVALID_SVG = get_icon_path("link_target_invalid.svg")
    LINK_ADD_WAYPOINT = get_icon_path("link_target_add_waypoint.svg")

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent=None):
        """
        Initializes the target marker item placed at the mouse cursor to indicate if a link target is valid.
        :param parent: A parent widget for this item
        """
        LinkAnchorItem.__init__(self, parent=parent)
        self.setZValue(ZLevelsEnum.link_creation_target_marker)

        self.__valid_target = QGraphicsSvgItem(PartLinkTargetMarkerItem.LINK_VALID_SVG, self)
        self.__invalid_target = QGraphicsSvgItem(PartLinkTargetMarkerItem.LINK_INVALID_SVG, self)
        self.__add_waypoint = QGraphicsSvgItem(PartLinkTargetMarkerItem.LINK_ADD_WAYPOINT, self)
        self.__valid_target.setScale(3)

        self.__linkable = None
        self.__visible_marker = None
        self.set_linkable(LinkCreationStatusEnum.invalid_target)

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        pass  # override to satisfy Qt subclass requirements.

    @override(QGraphicsItem)
    def boundingRect(self) -> QRectF:
        return self.__visible_marker.boundingRect()

    @override(QGraphicsItem)
    def shape(self):
        marker_path = QPainterPath()
        marker_path.addRect(self.boundingRect())
        return marker_path

    @override(LinkAnchorItem)
    def get_contact_point(self, anchor_point: QPointF, link_line: QLineF) -> QPointF:
        return self.__visible_marker.sceneBoundingRect().center()

    @override(LinkAnchorItem)
    def get_link_boundary_rect(self) -> QRectF:
        return self.__visible_marker.sceneBoundingRect()

    def get_linkable(self) -> LinkCreationStatusEnum:
        """
        Returns the validity of linking to the current target.
        """
        return self.__linkable

    def set_linkable(self, linkable: LinkCreationStatusEnum):
        """
        Sets the link icon to the corresponding link validity status: 'valid target', or 'invalid target'.
        :param linkable: The link validity status to set.
        """
        if linkable == self.__linkable:
            return

        self.prepareGeometryChange()
        if linkable == LinkCreationStatusEnum.valid_target:
            self.__valid_target.setVisible(True)
            self.__invalid_target.setVisible(False)
            self.__add_waypoint.setVisible(False)
            self.__visible_marker = self.__valid_target
        elif linkable == LinkCreationStatusEnum.invalid_target:
            self.__valid_target.setVisible(False)
            self.__invalid_target.setVisible(True)
            self.__add_waypoint.setVisible(False)
            self.__visible_marker = self.__invalid_target
        else:  # create waypoint
            self.__valid_target.setVisible(False)
            self.__invalid_target.setVisible(False)
            self.__add_waypoint.setVisible(True)
            self.__visible_marker = self.__add_waypoint

        self.__linkable = linkable

    link_boundary_rect = property(get_link_boundary_rect)
    linkable = property(get_linkable)


class WaypointMarkerItem(LinkAnchorItem):
    """
    Creates a temporary waypoint to allow user to add waypoints while creating link.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    COLOR_DEFAULT = PART_ICON_COLORS['waypoint']

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, scene_pos: QPointF):
        """
        Initializes the waypoint marker item used to temporarily indicate new waypoints while creating a new link.
        :param scene_pos:
        """
        LinkAnchorItem.__init__(self, parent=None)

        self.__waypoint_size = QSize(WAYPOINT_SIZE_PIX, WAYPOINT_SIZE_PIX)
        self.__default_brush = QBrush(WaypointMarkerItem.COLOR_DEFAULT, Qt.SolidPattern)

        # Waypoint bounds and shape
        self.__bounding_rect_path = QPainterPath()
        self.__waypoint_path = QPainterPath()

        self.__position = Position()
        self.is_waypoint_decluttered = False

        # Add to scene
        self.__set_position(scene_pos)
        self._calculate_painter_path()

    @override(LinkAnchorItem)
    def get_link_boundary_rect(self) -> QRectF:
        return self.sceneBoundingRect()

    @override(LinkAnchorItem)
    def get_contact_point(self, anchor_point: QPointF, link_line: QLineF) -> QPointF:
        """Get the contact point for the waypoint item."""
        return self.sceneBoundingRect().center()

    @override(QGraphicsObject)
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        event.ignore()

    @override(QGraphicsObject)
    def type(self) -> int:
        return CustomItemEnum.waypoint.value

    @override(QGraphicsItem)
    def boundingRect(self) -> QRectF:
        margin = 5.0  # Increase the margin to improve waypoint selectability
        return self.__bounding_rect_path.boundingRect().adjusted(-margin, -margin, margin, margin)

    @override(QGraphicsItem)
    def shape(self) -> QPainterPath:
        return self.__bounding_rect_path

    @override(QGraphicsItem)
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHints(QPainter.Antialiasing | QPainter.HighQualityAntialiasing)
        painter.setPen(Qt.NoPen)
        self.setZValue(ZLevelsEnum.waypoint)
        painter.setBrush(self.__default_brush)
        painter.drawPath(self.__waypoint_path)

    def get_position(self) -> Position:
        """
        Get the position, in global scenario coordinates.
        :return: a Position object.
        """
        return self.__position

    position = property(get_position)
    link_boundary_rect = property(get_link_boundary_rect)

    # --------------------------- instance PROTECTED properties & safe_slots ----------------------------

    def _calculate_painter_path(self):
        """
        Calculates the paths to draw the waypoint and it's bounding rectangle.
        """
        self.prepareGeometryChange()
        self.__bounding_rect_path = QPainterPath()
        self.__waypoint_path = QPainterPath()

        outer = QRectF(-self.__waypoint_size.width() / 2.0,
                       -self.__waypoint_size.height() / 2.0,
                       self.__waypoint_size.width(),
                       self.__waypoint_size.height())

        self.__bounding_rect_path.addRect(outer)
        self.__waypoint_path.addEllipse(outer)

    # --------------------------- instance PRIVATE properties & safe_slots ----------------------------

    def __set_position(self, scene_pos: QPointF):
        """
        Add to scene and store the waypoint marker scenario position for use when the backend waypoints are created.
        :param scene_pos: The position in the scene in scene coordinates.
        """
        self.setPos(scene_pos)
        new_scen_pos = map_to_scenario(scene_pos)
        if new_scen_pos != self.__position:
            self.__position = new_scen_pos
