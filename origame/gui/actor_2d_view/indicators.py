# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Indicators shared by all types of parts

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QColor, QBrush, QPen, QPolygonF
from PyQt5.QtWidgets import QGraphicsProxyWidget, QGraphicsItem, QGraphicsSceneMouseEvent, QMessageBox, \
    QGraphicsPolygonItem

# [3. local]
from ...core import override
from ...core.typing import AnnotationDeclarations
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.alerts import ScenAlertLevelEnum
from ...scenario.defn_parts import BasePart

from ..async_methods import AsyncRequest, async_call_needed
from ..gui_utils import QTBUG_55918_OPACITY, get_icon_path, exec_modal_dialog, OBJECT_NAME
from ..safe_slot import safe_slot

from .comment_box import CommentBoxWidget
from .common import CustomItemEnum, ZLevelsEnum, ICustomItem
from .custom_items import SvgFromImageItem
from .part_box_side_item_base import BottomSideTrayItemTypeEnum, BaseSideTrayItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [  # defines module members that are public; one line per string
    'CommentBoxItem',
    'AlertIndicator',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    PartBoxItem = 'PartBoxItem'


class CommentBoxItem(ICustomItem, QGraphicsProxyWidget):
    """
    This class is used to show a text comment box above a part.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    DEFAULT_WIDTH = 200
    MAX_HEIGHT = 124
    TEXT_HEIGHT_THRESHOLD = 112  # It reaches 7 lines
    ROOM_TO_AVOID_SCROLL = 25

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: QGraphicsItem = None):
        """
        Initialization method for a Comment.  When the toggle for a comment visibility is changed
        (in the part properties), this item is shown/hidden.
        :param part_box_item: It hosts this bubble.
        :param parent: The parent item.
        """
        ICustomItem.__init__(self)
        QGraphicsProxyWidget.__init__(self, parent)

        comment_box = CommentBoxWidget()
        self.setWidget(comment_box)
        comment_box.setFixedWidth(int(self.DEFAULT_WIDTH))
        self.setZValue(ZLevelsEnum.bubble_comment)
        self.setVisible(False)
        self.setOpacity(QTBUG_55918_OPACITY)  # QTBUG-55918
        self.setFlag(QGraphicsItem.ItemIsFocusable, False)

        part_box_item.part_frame.signals.sig_comment_changed.connect(self.__slot_set_comment_text)
        AsyncRequest.call(part_box_item.part_frame.get_comment, response_cb=self.__set_comment_text)

    @override(QGraphicsProxyWidget)
    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        self.scene().set_selection(self)
        super().mousePressEvent(event)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __set_comment_text(self, text: str):
        """
        Method used to set the bubble comment text for a part.
        :param text: The new text to put in the bubble comment.
        """
        self.widget().ui.comment_text.setPlainText(text)
        height_needed = self.widget().ui.comment_text.document().size().height()
        if height_needed >= self.TEXT_HEIGHT_THRESHOLD:
            height_needed = self.MAX_HEIGHT
        else:
            height_needed += self.ROOM_TO_AVOID_SCROLL

        self.widget().setFixedHeight(int(height_needed))
        self.parentItem().setVisible(bool(text.strip()))

        self.setY(-self.boundingRect().height())

    __slot_set_comment_text = safe_slot(__set_comment_text)


class AlertIndicator:
    """
    Indicates the alert status of parts.  Example parts are Function, Plot, Library, and SQL parts.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: BasePart, parent_part_box_item: Decl.PartBoxItem):
        if parent_part_box_item is None:
            # nothing to monitor
            self.__alert_ind = None
            self.__missing_links_ind = None
            return

        self.__parent_part_box_item = parent_part_box_item

        # general alert indicator:
        self.__map_alert_level_to_icon = {
            ScenAlertLevelEnum.warning: str(get_icon_path("alert_warning.svg")),
            ScenAlertLevelEnum.error: str(get_icon_path("alert_error.svg"))
        }
        self.__alert_ind = SvgFromImageItem(self.__map_alert_level_to_icon[ScenAlertLevelEnum.error])
        self.__alert_ind.setVisible(False)
        parent_part_box_item.bottom_side_tray_item.add_obj(BottomSideTrayItemTypeEnum.exec_warning,
                                                           self.__alert_ind)
        self.__alert_ind.sig_mouse_pressed.connect(self.__slot_show_alerts_panel)

        # missing links indicator:
        self.__missing_links_ind = MissingLinkIndicatorItem(
            parent_part_box_item, parent_part_box_item.bottom_side_tray_item)
        self.__missing_links_ind.setVisible(False)
        parent_part_box_item.bottom_side_tray_item.add_obj(BottomSideTrayItemTypeEnum.missing_links,
                                                           self.__missing_links_ind)

        # start monitoring the part for alerts:
        self.__part = part
        self.__monitor_part(part)

    def show_alerts_message(self):
        """
        Emits the sig_alert_source_selected to notify the scene.
        Opens a message box showing all the alerts for the part. 
        """
        self.__show_alerts_panel()

        def show_alerts_msg(formatted_msg: str):
            exec_modal_dialog(dialog_title="Part Alert",
                              message=formatted_msg,
                              icon=QMessageBox.Critical)

        AsyncRequest.call(self.__get_formatted_alerts_message, response_cb=show_alerts_msg)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def _disconnect_all_slots(self):
        alert_signals = self.__part.alert_signals
        alert_signals.sig_alert_status_changed.disconnect(self.__slot_on_alert_status_changed)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_alert_status_changed(self):
        """
        Intercepts the 'backend' signal indicating if the last Async call was successful.
        """
        part = self.__part  # assumes self used as mixin that provides _part
        if part.has_alerts(ScenAlertLevelEnum.error):
            self.__alert_ind.load(self.__map_alert_level_to_icon[ScenAlertLevelEnum.error])
            self.__alert_ind.setVisible(True)

        elif part.has_alerts(ScenAlertLevelEnum.warning):
            self.__alert_ind.load(self.__map_alert_level_to_icon[ScenAlertLevelEnum.warning])
            self.__alert_ind.setVisible(True)

        else:
            self.__alert_ind.setVisible(False)

    def __monitor_part(self, part: BasePart):
        alert_signals = part.alert_signals
        alert_signals.sig_alert_status_changed.connect(self.__slot_on_alert_status_changed)
        self.__on_alert_status_changed()

    @async_call_needed
    def __get_formatted_alerts_message(self) -> str:
        """
        Get a message that contains a list of all the alerts. The messages are sorted since there is
        no particular order, might as well make it easier to read.
        :return: A formatted string, one alert per line (although some alerts could span be multiple lines)
        """
        part = self.__part  # assumes self used as mixin that provides __part
        formatted_msg = '\n'.join(sorted(alert.msg for alert in part.get_alerts()))
        formatted_msg += '\n\nThe Alerts panel may have more info.'
        return  formatted_msg

    def __show_alerts_panel(self):
        """
        Emits the sig_alert_source_selected to notify the scene.
        """
        if self.__parent_part_box_item is None:
            return

        self.__parent_part_box_item.scene().sig_alert_source_selected.emit(self.__part)

    __slot_show_alerts_panel = safe_slot(__show_alerts_panel)
    __slot_on_alert_status_changed = safe_slot(__on_alert_status_changed)


class MissingLinkIndicatorItem(BaseSideTrayItem):
    """
    Represents a missing link item - a red horizontal outgoing arrow
    """

    # --------------------------- class-wide data and signals -----------------------------------

    ITEM_COLOR = QColor(255, 0, 0)
    ITEM_WIDTH_TAIL = 13
    ITEM_HEIGHT_TAIL = 10
    ITEM_WIDTH_ARROW = 13
    ITEM_HEIGHT_ARROW = 26

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part_box_item: Decl.PartBoxItem, parent: QGraphicsItem = None):
        """
        A red horizontal outgoing arrow.
        """
        super().__init__(part_box_item, parent)
        self.setData(OBJECT_NAME, 'missing_link_indicator')

        self.setVisible(False)
        self.__icon = QGraphicsPolygonItem(self)
        self.__icon.setBrush(QBrush(self.ITEM_COLOR))
        self.__icon.setPen(QPen(Qt.NoPen))

        p0 = QPointF(0, (self.ITEM_HEIGHT_ARROW - self.ITEM_HEIGHT_TAIL) / 2)
        p1 = QPointF(self.ITEM_WIDTH_TAIL, (self.ITEM_HEIGHT_ARROW - self.ITEM_HEIGHT_TAIL) / 2)
        p2 = QPointF(self.ITEM_WIDTH_TAIL, 0)
        p3 = QPointF(self.ITEM_WIDTH_TAIL + self.ITEM_WIDTH_ARROW, self.ITEM_HEIGHT_ARROW / 2)
        p4 = QPointF(self.ITEM_WIDTH_TAIL, self.ITEM_HEIGHT_ARROW)
        p5 = QPointF(self.ITEM_WIDTH_TAIL, (self.ITEM_HEIGHT_ARROW + self.ITEM_HEIGHT_TAIL) / 2)
        p6 = QPointF(0, (self.ITEM_HEIGHT_ARROW + self.ITEM_HEIGHT_TAIL) / 2)
        self.__icon.setPolygon(QPolygonF([p0, p1, p2, p3, p4, p5, p6]))

    @override(BaseSideTrayItem)
    def type(self) -> int:
        return CustomItemEnum.event_counter.value
