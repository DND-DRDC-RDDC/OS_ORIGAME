# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The custom graphics items implemented for the Origame project.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging, base64, mimetypes
from xml.dom.minidom import parseString
from pathlib import Path

# [2. third-party]
from PyQt5.QtCore import pyqtSignal, QSize, QByteArray, QEvent, QPointF, QPoint, QRectF, Qt
from PyQt5.QtGui import QPixmap, QTransform, QPolygonF, QColor, QBrush, QPen, QCursor, QPainterPath
from PyQt5.QtSvg import QGraphicsSvgItem, QSvgRenderer
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsWidget, QGraphicsRectItem
from PyQt5.QtWidgets import QAction, QGraphicsPolygonItem, QWidget, QGraphicsSceneMouseEvent

# [3. local]
from ...core import override, override_required
from ..gui_utils import OBJECT_NAME, MARGIN_OF_SELECTED_PART, QTBUG_55918_OPACITY
from .common import CustomItemEnum, ICustomItem, EventStr

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'SizeGripCornerItem',
    'SizeGripRightItem',
    'SizeGripBottomItem',
    'SvgFromImageItem'
]

log = logging.getLogger('system')

# Size grip item
SIZE_GRIP_STROKE_WIDTH = MARGIN_OF_SELECTED_PART
SIZE_GRIP_COLOR = QColor(0, 160, 0)


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class SizeGripItem(ICustomItem, QGraphicsWidget):
    """
    Used to resize a part box item.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    MAX_SIZE = 16777215

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, widget_to_resize: QWidget, min_width: float, min_height: float,
                 parent: QGraphicsWidget = None, end_action: QAction = None):
        ICustomItem.__init__(self)
        QGraphicsWidget.__init__(self, parent)
        self.setData(OBJECT_NAME, "size_grip")
        self.setVisible(False)
        self.setOpacity(QTBUG_55918_OPACITY)  # QTBUG-55918

        # Init data
        self._pos_pressed = QPoint()
        self._widget = widget_to_resize
        self._size = widget_to_resize.size()
        self.__end_action = end_action
        self.set_min_size(min_width, min_height)
        self._min_delta_x = min_width - self._size.width()
        self._min_delta_y = min_height - self._size.height()


    def set_min_size(self, min_width: float, min_height: float):
        self.__min_width = min_width
        self.__min_height = min_height

    @override_required
    def parent_rect_changed(self, rect: QRectF):
        """
        Since a size grip usually sits on the edges of the item (parent) that is being re-sized, this function
        must use the rect of parent to position the size grip.
        :param rect: The rect of the item that is being re-sized.
        """
        raise NotImplementedError

    @override(QGraphicsItem)
    def boundingRect(self):
        return self.childrenBoundingRect()

    @override(QGraphicsItem)
    def shape(self):
        the_shape = QPainterPath()
        the_shape.addRect(self.boundingRect())
        return the_shape

    @override(QGraphicsItem)
    def type(self) -> int:
        return CustomItemEnum.size_grip.value

    @override(QGraphicsWidget)
    def mousePressEvent(self, mouse_evt: QGraphicsSceneMouseEvent):
        log.debug("{} got mouse press: {}", type(self).__name__, EventStr(mouse_evt))
        self.scene().start_object_interaction(self)

        self._widget.setMaximumSize(self.MAX_SIZE, self.MAX_SIZE)
        self._widget.setMinimumSize(0, 0)
        self._size = self._widget.size()
        self._pos_pressed = self._widget.mapFromGlobal(mouse_evt.screenPos())
        self._min_delta_x = self.__min_width - self._size.width()
        self._min_delta_y = self.__min_height - self._size.height()

    @override(QGraphicsWidget)
    def mouseMoveEvent(self, mouse_evt: QGraphicsSceneMouseEvent):
        """
        Calculates the distances the mouse has moved since the last mouse press. If the movement would cause the
        widget to become too small, the distances will be set to the pre-defined minimum values.
        """
        delta = self._widget.mapFromGlobal(mouse_evt.screenPos()) - self._pos_pressed

        warn_x = None
        delta_x = delta.x()

        if delta_x < self._min_delta_x:
            delta_x = self._min_delta_x
            warn_x = "min width resizing reached"

        warn_y = None
        delta_y = delta.y()

        if delta_y < self._min_delta_y:
            delta_y = self._min_delta_y
            warn_y = "min height resizing reached"

        self._resize_on_mouse_move(delta_x, delta_y, warn_x, warn_y)

    def mouseReleaseEvent(self, mouse_evt: QGraphicsSceneMouseEvent):
        log.debug("{} got mouse release", type(self).__name__)
        self.__end_action.setData(self._size)
        self.__end_action.triggered.emit()
        self.scene().end_object_interaction()

        # --------------------------- instance PUBLIC properties and safe_slots ---------------------
        # --------------------------- instance __SPECIAL__ method overrides -------------------------
        # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_required
    def _resize_on_mouse_move(self, pos_delta_x: float, pos_delta_y: float, warning_x: str = None,
                              warning_y: str = None):
        """
        The derived class must implement this by resizing the widget horizontally, vertically, both or in any other
        manners.
        :param pos_delta_x: the distance the mouse has moved along the x
        :param pos_delta_x: the distance the mouse has moved along the y
        :param warning_x: the message if the movement would cause the widget width to become too small
        :param warning_y: the message if the movement would cause the widget height to become too small
        """
        raise NotImplementedError("The derived class must implement this function.")

        # --------------------------- instance _PROTECTED properties and safe slots -----------------
        # --------------------------- instance __PRIVATE members-------------------------------------


class SizeGripCornerItem(SizeGripItem):
    """
    Used to resize a part box item.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, widget_to_resize: QWidget, min_width: float, min_height: float,
                 parent: QGraphicsWidget = None, end_action: QAction = None):
        SizeGripItem.__init__(self, widget_to_resize, min_width, min_height, parent, end_action)
        self.setData(OBJECT_NAME, "size_grip_corner")
        # GUI

        self.setCursor(QCursor(Qt.SizeFDiagCursor))
        bar_width = SIZE_GRIP_STROKE_WIDTH
        self.__width_adjustment = SIZE_GRIP_STROKE_WIDTH / 2
        short_side = 3 * bar_width
        long_side = 4 * bar_width

        corner = QGraphicsPolygonItem(self)
        polygon = QPolygonF([QPointF(short_side, 0),
                             QPointF(long_side, 0),
                             QPointF(long_side, long_side),
                             QPointF(0, long_side),
                             QPointF(0, short_side),
                             QPointF(short_side, short_side),
                             ])
        corner.setPolygon(polygon)
        corner.setBrush(QBrush(SIZE_GRIP_COLOR))
        corner.setPen(QPen(Qt.NoPen))

    @override(SizeGripItem)
    def parent_rect_changed(self, rect: QRectF):
        square_side_len = self.childrenBoundingRect().width()
        self.setPos(rect.width() - square_side_len + rect.x() + self.__width_adjustment,
                    rect.height() - square_side_len + rect.y() + self.__width_adjustment)

    @override(QGraphicsItem)
    def type(self) -> int:
        return CustomItemEnum.size_grip_corner.value

        # --------------------------- instance PUBLIC properties and safe_slots ---------------------
        # --------------------------- instance __SPECIAL__ method overrides -------------------------
        # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(SizeGripItem)
    def _resize_on_mouse_move(self, pos_delta_x: float, pos_delta_y: float, warning_x: str = None,
                              warning_y: str = None):
        """
        Changes the width and the height of the widget. Log warning messages if available.
        """
        if warning_x is not None:
            log.debug(warning_x)

        if warning_y is not None:
            log.debug(warning_y)

        self._widget.setFixedSize(int(self._size.width() + pos_delta_x), int(self._size.height() + pos_delta_y))

        # --------------------------- instance _PROTECTED properties and safe slots -----------------
        # --------------------------- instance __PRIVATE members-------------------------------------


class SizeGripRightItem(SizeGripItem):
    """
    Used to resize a widget at the right edge.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, widget_to_resize: QWidget, min_width: float, min_height: float,
                 parent: QGraphicsWidget = None, end_action: QAction = None):
        SizeGripItem.__init__(self, widget_to_resize, min_width, min_height, parent, end_action)
        self.setData(OBJECT_NAME, "size_grip_right")
        # GUI
        self.setCursor(QCursor(Qt.SizeHorCursor))
        width = SIZE_GRIP_STROKE_WIDTH
        self.__width_adjustment = SIZE_GRIP_STROKE_WIDTH / 2
        height = min_height / 2
        right = QGraphicsRectItem(0, 0, width, height, self)

        right.setBrush(QBrush(SIZE_GRIP_COLOR))
        right.setPen(QPen(Qt.NoPen))

    @override(SizeGripItem)
    def parent_rect_changed(self, rect: QRectF):
        shape_width = self.childrenBoundingRect().width()
        shape_height = self.childrenBoundingRect().height()
        self.setPos(rect.width() - shape_width + rect.x() + self.__width_adjustment,
                    (rect.height() - shape_height) / 2 + rect.y())

    @override(QGraphicsItem)
    def type(self) -> int:
        return CustomItemEnum.size_grip_right.value

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(SizeGripItem)
    def _resize_on_mouse_move(self, pos_delta_x: float, pos_delta_y: float, warning_x: str = None,
                              warning_y: str = None):
        """
        Changes the width of the widget. Log warning messages if available.
        """
        if warning_x is not None:
            log.debug(warning_x)

        self._widget.setFixedWidth(int(self._size.width() + pos_delta_x))


class SizeGripBottomItem(SizeGripItem):
    """
    Used to resize a widget at the bottom edge.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, widget_to_resize: QWidget, min_width: float, min_height: float,
                 parent: QGraphicsWidget = None, end_action: QAction = None):
        SizeGripItem.__init__(self, widget_to_resize, min_width, min_height, parent, end_action)
        self.setData(OBJECT_NAME, "size_grip_bottom")
        # GUI
        self.setCursor(QCursor(Qt.SizeVerCursor))
        height = SIZE_GRIP_STROKE_WIDTH
        self.__width_adjustment = SIZE_GRIP_STROKE_WIDTH / 2
        width = min_width / 2
        bottom = QGraphicsRectItem(0, 0, width, height, self)

        bottom.setBrush(QBrush(SIZE_GRIP_COLOR))
        bottom.setPen(QPen(Qt.NoPen))

    @override(SizeGripItem)
    def parent_rect_changed(self, rect: QRectF):
        shape_width = self.childrenBoundingRect().width()
        shape_height = self.childrenBoundingRect().height()
        self.setPos((rect.width() - shape_width) / 2 + rect.x(),
                    rect.height() - shape_height + rect.y() + self.__width_adjustment)

    @override(QGraphicsItem)
    def type(self) -> int:
        return CustomItemEnum.size_grip_bottom.value

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(SizeGripItem)
    def _resize_on_mouse_move(self, pos_delta_x: float, pos_delta_y: float, warning_x: str = None,
                              warning_y: str = None):
        """
        Changes the height of the widget. Log warning messages if available.
        """
        if warning_y is not None:
            log.debug(warning_y)

        self._widget.setFixedWidth(int(self._widget.size().width()))
        self._widget.setFixedHeight(int(self._size.height() + pos_delta_y))


class SvgFromImageItem(ICustomItem, QGraphicsSvgItem):
    """
    Loads an image file such as a png file to construct a QGraphicsSvgItem. If an SVG file is passed to the constructor,
    this class will use it directly without any conversion.

    Note: you should use the QGraphicsSvgItem directly if you have SVG images. The main purpose of this class is
    to work as a wrapper of other image formats such as png files. Also, this class emits two mouse related signals.
    If you are not interested in the signals, it is better to use the QGraphicsSvgItem.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    DEFAULT_WIDTH = 25
    DEFAULT_HEIGHT = 25
    SVG_TEMPLATE = """\
        <svg
         version="1.1"
         xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="{0}px" height="{1}px"
         viewBox="0 0 {0} {1}" preserveAspectRatio="none">
           <g>
                <image width="{0}" height="{1}" xlink:href="" />
           </g>
        </svg>
    """

    sig_mouse_pressed = pyqtSignal()
    sig_mouse_released = pyqtSignal()

    def __init__(self, file_name: str = None, parent: QGraphicsItem = None):
        """
        Loads an image file such as a png file to construct a QGraphicsSvgItem. If an SVG file is passed in,
        it will be used directly to construct this class.
        :param file_name: The name of an image file or SVG file
        :param parent: The parent of this item
        """
        ICustomItem.__init__(self)
        QGraphicsSvgItem.__init__(self, parent)
        self.__parent = parent
        self.__mime = None
        self.__svg_dom = parseString(self.SVG_TEMPLATE.format(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT))
        self.__rotation_2d = 0.0
        self.__file_name = None
        self.__actual_image = QPixmap()
        self.__actual_image_size = QSize(self.DEFAULT_WIDTH, self.DEFAULT_HEIGHT)
        if file_name is not None:
            self.load(file_name)

    def load(self, file_name: str):
        """
        Loads an image file such as a png file to construct a QGraphicsSvgItem. If an SVG file is passed in,
        it will be used directly.

        A mini-cache mechanism is introduced - if the same file name is attempted again, it will not be re-loaded.

        :param file_name: The name of an image file or SVG file
        """
        if file_name == self.__file_name:
            return
        else:
            self.__file_name = file_name
        self.__mime = mimetypes.guess_type(file_name)
        with Path(file_name).open('rb') as img_file:
            file_content = img_file.read()

        self.__actual_image = QPixmap(file_name)
        self.__actual_image_size = self.__actual_image.size()

        if self.__mime[0] == "image/svg+xml":
            # It is already an svg file
            self.setSharedRenderer(QSvgRenderer(file_name))
            self.__svg_dom = parseString(file_content.decode())
            return

        # Using the image file to construct an SVG file
        img_b64 = base64.b64encode(file_content).decode("utf-8")

        sized_svg = self.SVG_TEMPLATE.format(self.__actual_image_size.width(), self.__actual_image_size.height())
        self.__svg_dom = parseString(sized_svg)
        root_tag = self.__svg_dom.getElementsByTagName("svg")
        root_tag[0].setAttribute("transform",
                                 "rotate({0} {1} {2})".format(self.__rotation_2d,
                                                              self.__actual_image_size.width() / 2,
                                                              self.__actual_image_size.height() / 2))
        image_tag = self.__svg_dom.getElementsByTagName("image")
        image_tag[0].setAttribute("xlink:href", "data:{};base64, {}".format(self.__mime[0], img_b64))
        svg_byte_array = QByteArray()
        svg_byte_array.append(self.__svg_dom.toxml())
        self.setSharedRenderer(QSvgRenderer(svg_byte_array))

    def rotate(self, angle_in_degree):
        """
        Rotates the underlying SVG by a given angle.

        :param angle_in_degree: The angle that is applied to the underlying SVG transformation rotate() attribute.
        """
        self.__rotation_2d = angle_in_degree
        root_tag = self.__svg_dom.getElementsByTagName("svg")
        root_tag[0].setAttribute("transform",
                                 "rotate({0} {1} {2})".format(self.__rotation_2d,
                                                              self.__actual_image_size.width() / 2,
                                                              self.__actual_image_size.height() / 2))
        svg_byte_array = QByteArray()
        svg_byte_array.append(self.__svg_dom.toxml())
        super(SvgFromImageItem, self).load(svg_byte_array)

        self.__actual_image_size = self.__actual_image.transformed(QTransform().rotate(angle_in_degree)).size()

    def get_actual_image_size(self) -> QSize:
        """
        Gets the original size of the image - the size when its scale factor is 1. For example, if a bitmap
        has 100 x 200 pixels on the hard drive, this size will be QSize(100, 200).
        :return: The original size of the image.
        """
        return self.__actual_image_size

    @override(QGraphicsSvgItem)
    def sceneEvent(self, event: QEvent):
        """
        Emits sig_mouse_pressed. Note: cannot implement the mousePressEvent() because it is not called when this item is
        used as a child in the BottomSideTrayItem.
        :return: super().sceneEvent(event)
        """
        if event.type() == QEvent.GraphicsSceneMousePress:
            event.accept()
            self.sig_mouse_pressed.emit()
            return True

        elif event.type() == QEvent.GraphicsSceneMouseRelease:
            event.accept()
            self.sig_mouse_released.emit()
            return True

        else:
            return super().sceneEvent(event)

    actual_image_size = property(get_actual_image_size)
