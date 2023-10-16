# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: A collection of SVG utility classes for use in the GUI.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import base64
import mimetypes
from pathlib import Path
from xml.dom.minidom import parseString

# [2. third-party]
from PyQt5.QtCore import QSize, QByteArray, Qt
from PyQt5.QtGui import QPixmap, QTransform
from PyQt5.QtSvg import QSvgWidget
from PyQt5.QtWidgets import QWidget

# [3. local]
from ..core import override

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'SvgFromImageWidget'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class SvgFromImageWidget(QSvgWidget):
    """
    Loads an image file such as a png file to construct a SVG widget. If an SVG file is passed to the constructor,
    this class will use it directly without any conversion.

    Note: you should use the QSvgWidget directly if you have SVG images. The main purpose of this class is
    to work as a wrapper of other image formats such as png files.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    DEFAULT_SIZE = 25
    SVG_TEMPLATE = """\
        <svg
         version="1.1"
         xmlns="http://www.w3.org/2000/svg"
         xmlns:xlink="http://www.w3.org/1999/xlink"
         width="{0}px" height="{0}px"
         viewBox="0 0 {0} {0}" preserveAspectRatio="none">
           <g>
                <image width="{0}" height="{0}" xlink:href="" />
           </g>
        </svg>
    """.format(DEFAULT_SIZE)

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QWidget = None, file_name: str = None):
        """
        Loads an image file such as a png file to construct a SVG widget. If an SVG file is passed in,
        it will be used directly to construct this class.
        :param parent: The parent of this widget
        :param file_name: The name of an image file or SVG file
        """
        super(SvgFromImageWidget, self).__init__(parent)
        self.__mime = None
        self.__svg_dom = parseString(SvgFromImageWidget.SVG_TEMPLATE)
        self.__rotation_2d = 0.0
        self.__file_name = None
        self.__actual_image = QPixmap()
        self.__actual_image_size = QSize()
        if file_name is not None:
            self.load(file_name)

    @override(QSvgWidget)
    def load(self, file_name: str):
        """
        Loads an image file such as a png file to construct a SVG widget. If an SVG file is passed in,
        it will be used directly.

        A mini-cache mechanism is introduced - if the same file name is attempted again, it will not be re-loaded.

        :param file_name: The name of an image file or SVG file
        """
        if file_name == self.__file_name:
            return

        self.__file_name = file_name
        self.__mime = mimetypes.guess_type(file_name)
        with Path(file_name).open('rb') as img_file:
            file_content = img_file.read()

        self.__actual_image = QPixmap(file_name)
        self.__actual_image_size = self.__actual_image.size()

        svg_byte_array = QByteArray()
        if self.__mime[0] == "image/svg+xml":
            # It is already an svg file
            svg_byte_array.append(file_content)
            super(SvgFromImageWidget, self).load(svg_byte_array)
            self.__svg_dom = parseString(file_content.decode())
            return

        # Using the image file to construct an SVG file
        img_b64 = base64.b64encode(file_content).decode("utf-8")

        self.__svg_dom = parseString(SvgFromImageWidget.SVG_TEMPLATE)
        root_tag = self.__svg_dom.getElementsByTagName("svg")
        root_tag[0].setAttribute("transform",
                                 "rotate({0} {1} {1})".format(self.__rotation_2d,
                                                              self.__actual_image_size.width() / 2,
                                                              self.__actual_image_size.height() / 2))
        image_tag = self.__svg_dom.getElementsByTagName("image")
        image_tag[0].setAttribute("xlink:href", "data:{};base64, {}".format(self.__mime[0], img_b64))
        svg_byte_array.append(self.__svg_dom.toxml())
        super(SvgFromImageWidget, self).load(svg_byte_array)

    def rotate(self, angle_in_degree):
        """
        Rotates the underlying SVG by a given angle.

        :param angle_in_degree: The angle that is applied to the underlying SVG transformation rotate() attribute.
        """
        self.__rotation_2d = angle_in_degree
        root_tag = self.__svg_dom.getElementsByTagName("svg")
        root_tag[0].setAttribute("transform",
                                 "rotate({0} {1} {1})".format(self.__rotation_2d,
                                                              self.__actual_image_size.width() / 2,
                                                              self.__actual_image_size.height() / 2))
        svg_byte_array = QByteArray()
        svg_byte_array.append(self.__svg_dom.toxml())
        super(SvgFromImageWidget, self).load(svg_byte_array)

        self.__actual_image_size = self.__actual_image.transformed(QTransform().rotate(angle_in_degree)).size()

    def get_actual_image_size(self) -> QSize:
        """
        Gets the original size of the image file, i.e., the size properties stored in the hard drive.
        :return: The original size of the image. From the hard drive, not scaled.
        """
        return self.__actual_image_size

    def get_file_name(self) -> str:
        """
        Gets the the name of the image file that is displayed on this widget.
        :return: The full path of the image file. The supported image formats are same as those in Qt.
        """
        return self.__file_name

    def manage_size(self, container_size: QSize, size_scale_factor: float = 1.0):
        """
        Makes the image fit in the container - centered and with aspect ratio.
        :param container_size: The size of the widget to fit the SVG into.
        :param size_scale_factor: A scale factor for the size.
        """
        size = self.actual_image_size.scaled(container_size, Qt.KeepAspectRatio)
        self.setFixedSize(size * size_scale_factor)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    actual_image_size = property(get_actual_image_size)
    file_name = property(get_file_name)
