# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Base class to be used by all Origame class that are available in Qt Designer

To make an Origame widget available from Designer, import it in origame_plugins.py, and create a
class that derives from OrigameGuiQtDesignerPluginBase as shown in that module.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QWidget
from PyQt5.QtDesigner import QPyDesignerCustomWidgetPlugin

# [3. local]


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'add_plugin'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

def add_plugin(cls, tooltip, import_path) -> type:
    if QWidget in cls.__bases__:
        UiWidget = cls

    else:
        class UiWidgetBase(QWidget):
            """
            If you only want to expose the Ui_ portion of a widget, then you need to create a widget wrapper for it.
            Then the wrapper can be given as arg to the OrigameGuiQtDesignerPluginBase.__init__ in plugin's __init__.
            """

            def __init__(self, parent):
                super().__init__(parent)
                self.ui = cls()
                self.ui.setupUi(self)

        UiWidget = type(cls.__name__, (UiWidgetBase,), {})

    class PluginClass(OrigameGuiQtDesignerPluginBase):
        def __init__(self, parent=None):
            super().__init__(parent, UiWidget, tooltip, import_path)

    return PluginClass


# -- Class Definitions --------------------------------------------------------------------------

class OrigameGuiQtDesignerPluginBase(QPyDesignerCustomWidgetPlugin):
    """
    This class implements the interface expected by Qt Designer to access the custom widget.  See
    the description of the QDesignerCustomWidgetInterface class for full details. This is the base
    class for all Origame components that should be available in Qt Designer.
    """

    def __init__(self, parent, plugin_class, plugin_tooltip, plugin_import):
        """
        Define a plugin for an Origame widget.
        :param parent: the parent received from Qt Designer
        :param plugin_class: the class to instantiate when user drags class onto a container widget
        :param plugin_tooltip: the tooltip to use when user hovers mouses over class
        :param plugin_import: the import path to use when code is generated
        """
        super().__init__(parent)
        self._initialized = False

        self._group = "Origame"
        self._PluginClass = plugin_class
        self._name = plugin_class.__name__  # Name MUST match the class name!!!
        self._tooltip = plugin_tooltip
        self._whats_this = (plugin_class.__doc__ or "no doc").strip()
        self._include_file = plugin_import

    def initialize(self, formEditor):
        """Initialise the custom widget for use with the specified formEditor interface."""
        if self._initialized:
            return
        self._initialized = True

    def isInitialized(self):
        """Return True if the custom widget has been intialised."""
        return self._initialized

    def createWidget(self, parent):
        """Return a new instance of the custom widget with the given parent."""
        return self._PluginClass(parent)

    def name(self):
        """Return the name of the class that implements the custom widget."""
        return self._name

    def group(self):
        """
        Return the name of the group to which the custom widget belongs.  A new
        group will be created if it doesn't already exist.
        """
        return self._group

    def icon(self):
        """Return the icon used to represent the custom widget in Designer's widget box."""
        return QIcon(_logo_pixmap)

    def toolTip(self):
        """Return a short description of the custom widget used by Designer in a tool tip."""
        return self._tooltip

    def whatsThis(self):
        """
        Return a full description of the custom widget used by Designer in
        "What's This?" help for the widget.
        """
        return self._whats_this

    def isContainer(self):
        """Return True if the custom widget acts as a container for other widgets."""
        return False

    def domXml(self):
        """
        Return an XML fragment that allows the default values of the custom
        widget's properties to be overridden.
        """
        return '''<widget class="{_name}" name="{_name}">
                    <property name="toolTip" >
                        <string>{_tooltip}</string>
                    </property>
                    <property name="whatsThis" >
                        <string>{_whats_this}</string>
                    </property>
               </widget>
               '''.format_map(self.__dict__)

    def includeFile(self):
        """custom widget.  It may include a module path."""
        return self._include_file


# Define the image used for the icon (same for all Origame plugins).
_logo_16x16_xpm = [
    "16 16 61 1",
    "6 c #5bbd7c",
    "a c #7aaada",
    "h c #7eaddb",
    "n c #7faddb",
    "E c #82afdc",
    "x c #83b0dd",
    "C c #84b0dd",
    "z c #84b1dd",
    "B c #85b1dd",
    "u c #87b2de",
    "U c #9ec1e4",
    "Z c #9fc1e4",
    "H c #a1c3e5",
    "Y c #a5c5e4",
    "V c #a6c6e4",
    "P c #afcbe2",
    "S c #afcbe3",
    "O c #b1cde9",
    "T c #b2cee9",
    "t c #b4cee3",
    "r c #b5cee3",
    "q c #c2d8ee",
    "0 c #c7dbef",
    "f c #cedddb",
    "b c #cfdddb",
    "1 c #d0e1f2",
    "J c #d8e2d2",
    "I c #d9e2d2",
    "# c #dfeaf6",
    "g c #e3edf7",
    "K c #ecf2f9",
    "N c #ecf3f9",
    "o c #eeecbb",
    "i c #f2edb2",
    "l c #f2edb3",
    "w c #f6eea6",
    "v c #f7eea6",
    "W c #fcee8c",
    "m c #fcfdfe",
    "L c #fdec73",
    "k c #fedd00",
    "e c #fede06",
    "p c #fede07",
    "j c #fee013",
    "X c #fee015",
    "s c #fee223",
    "d c #fee32c",
    "A c #fee749",
    "Q c #fee850",
    "R c #fee851",
    "D c #fee854",
    "y c #feea65",
    "M c #feec74",
    "c c #feed7c",
    "F c #feee85",
    "G c #feee86",
    "5 c #fef095",
    "4 c #fef195",
    "3 c #fef6bb",
    "2 c #fefdf5",
    ". c #fefefe",
    "..#abcdeedcfa#..",
    ".ghijkkkkkkjlhg.",
    "mnopkkkkkkkkponm",
    "qrskkkkkkkkkkstq",
    "uvkkkkkkkkkkkkwu",
    "xykkkkkkkkkkkkyx",
    "zAkkkkkkkkkkkkAB",
    "CDkkkkkkkkkkkkDC",
    "EFkkkkkkkkkkkkGE",
    "HIekkkkkkkkkkeJH",
    "KBLkkkkkkkkkkMBN",
    ".OPQkkkkkkkkRST.",
    "..UVWXkkkkXWYZ..",
    "...0123453210...",
    "6666666666666666",
    "BBBBBBBBBBBBBBBB"]

_logo_pixmap = QPixmap(_logo_16x16_xpm)
