# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Data about the application (version, about, license, etc)

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
from os import system
import logging
from pathlib import Path
import re
import origame
import webbrowser

# [2. third-party]
from PyQt5.QtCore import QT_VERSION_STR, PYQT_VERSION_STR, Qt, QUrl, __license__ as PYQT_LICENSE
from PyQt5.QtWidgets import QSplashScreen, QDialog, QWidget, QGroupBox
from PyQt5.QtGui import QCloseEvent, QKeyEvent

from sip import SIP_VERSION_STR

# [3. local]
from ..core import override
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from .safe_slot import safe_slot
from .Ui_about import Ui_AboutBox
from .Ui_about_dialog import Ui_AboutDialog
from .gui_utils import set_default_dialog_frame_flags

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'RELEASE_VERSION',
    'AboutDialog',
    'get_splash_screen',
]

log = logging.getLogger('system')

# When released to client, update this
RELEASE_VERSION = '0.8.0 beta (2023-03-02)'

ABOUT_APP = '''\
<h1 align="center">ORIGAME</h1>

<h3 align="center">A discrete event modeling and simulation environment for operational research and analysis </h3>

<p align="center">Version: {app_ver} </p>

<p align="center">© 2017 Her Majesty the Queen in Right of Canada</p>

<p><b>LICENSE:</b>
{license}
</p>

<p>Origame is using the following third-party components found on your system: </p>
<ul>
    <li>PyQt version: {pyqt_ver} </li>
    <li>sip version: {sip_ver} </li>
    <li>Qt version: {qt_ver} </li>
</ul>
'''


# -- Function definitions -----------------------------------------------------------------------

def get_pyqt_lic(license_info: Dict[str, str]) -> str:
    pyqt_lic = license_info['Type'].title()
    if pyqt_lic == 'Commercial':
        pyqt_lic += ', #' + license_info['Licensee']
    else:
        if pyqt_lic == 'Gpl':
            pyqt_lic = 'GPL'
        #pyqt_lic += '-- NOT the one distributed with Origame!'

    return pyqt_lic


def get_about_info() -> str:
    """
    Get the HTML string representing information about the application, such as version number for it and
    its depedencies, etc.
    """
    return ABOUT_APP.format(app_ver=RELEASE_VERSION, pyqt_ver=PYQT_VERSION_STR, sip_ver=SIP_VERSION_STR,
                            pyqt_lic=get_pyqt_lic(PYQT_LICENSE),
                            qt_ver=QT_VERSION_STR, contact='stephen.okazawa@forces.gc.ca', license=get_license())


def get_splash_screen() -> QSplashScreen:
    """Get the application's splash screen"""
    widget = AboutBox()
    widget.setStyleSheet("background-color: rgb(255, 0, 5);")
    pixmap = widget.grab()
    return QSplashScreen(pixmap, flags=Qt.WindowStaysOnTopHint)


def get_license():
    try:
        license_path = Path(origame.__file__).with_name('LICENSE.txt')
        license_html = Path(origame.__file__).with_name('docs') / 'licensing' / 'LICENSE.html'
        
        info = '''Terms and conditions are in LICENSE.txt (<a href="file:{path}">show in Explorer</a>; or
                <a href="file:{html_path}">view as HTML</a>).'''

        return info.format(path=license_path, html_path=license_html)

    except:
        return '''This application can only be used by employees of The Government of Canada
                and contractors given access by Defense R&amp;D Canada (DRDC). It may NOT be
                re-distributed without permission from DRDC.'''

    return license


# -- Class Definitions --------------------------------------------------------------------------

class AboutBox(QWidget):
    """Represents just the text panel"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.ui = Ui_AboutBox()
        self.ui.setupUi(self)
        self.ui.textBrowser.setHtml(get_about_info())
        self.ui.textBrowser.anchorClicked.connect(self.slot_anchor_clicked)
        self.ui.textBrowser.setOpenLinks(False)
        self.ui.textBrowser.setOpenExternalLinks(True)

    @override(QGroupBox)
    def setTitle(self, title: str):
        # Only needed because using QGroupBox in the dialog's Ui file, and Designer sets title
        pass

    @override(QWidget)
    def keyPressEvent(self, evt: QKeyEvent):
        if evt.key() == Qt.Key_Backspace:
            self.ui.textBrowser.setHtml(get_about_info())
            evt.accept()
        else:
            super().keyPressEvent(evt)

    def anchor_clicked(self, url: QUrl):
        if url.scheme() == 'mailto':
            webbrowser.open(url.toString(), new=1)
            return

        filename = url.fileName()
        if filename.endswith('.txt'):
            system('explorer /select,' + filename)
        else:
            self.ui.textBrowser.setSource(url)

    slot_anchor_clicked = safe_slot(anchor_clicked)


class AboutDialog(QDialog):
    """Dialog that shows the text panel and allows user to close it"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.ui = Ui_AboutDialog()
        # the UI has a bogus group that need to get replaced by an AboutBox
        from . import Ui_about_dialog
        Ui_about_dialog.Ui_AboutBox = AboutBox
        self.ui.setupUi(self)
        set_default_dialog_frame_flags(self)

    @override(QDialog)
    def closeEvent(self, evt: QCloseEvent):
        self.accept()

    @override(QDialog)
    def accept(self):
        self.hide()
