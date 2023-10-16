# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Management of alerts at the front end.


Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QLabel, QTableWidgetItem
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QSize, pyqtSignal
from PyQt5.Qt import Qt

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core import override

from ...scenario.alerts import ScenAlertInfo, ScenAlertLevelEnum, IScenAlertSource, ScenAlertManageEnum
from ...scenario.defn_parts import BasePart
from ...scenario import Scenario
from ..safe_slot import safe_slot
from ..async_methods import AsyncRequest
from ..gui_utils import get_icon_path, IScenarioMonitor
from .Ui_alerts import Ui_AlertsContent


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "Revision"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"


# -- Module-level objects -----------------------------------------------------------------------

__all__ = [  
    # public API of module: one line per string
    'AlertsPanel'
]

log = logging.getLogger('system')

ALERTS_TABLE_HEADER_NAMES = ['Type', 'Component', 'Category']
COL_TYPE_WIDTH = 48

ALERT_IMG_SIZE = QSize(24, 24)
MAP_ALERT_LEVEL_TO_IMG = {
}

FILTER_BUTTON_FILTER = "Filter"
FILTER_BUTTON_UN_FILTER = "Un-filter"
FILTER_LABEL_NONE = "None"

ALERT_COL_TYPE, ALERT_COL_COMPONENT, ALERT_COL_CATEGORY = range(3)
USER_ROLE_ALERT_INFO = Qt.UserRole


# -- Function definitions -----------------------------------------------------------------------

def pretty_details_in_html(alert_info: ScenAlertInfo) -> str:
    """
    Formats a user-friendly text to describe the details of this alert.
    :param alert_info: The raw data of the alert info
    :return: The user-friendly text
    """
    full_template = """
        <!DOCTYPE html>
        <html>
            <body>
            <h3>{manage} Alert</h3>
            <p>{msg}</p>
            
            {err_data}
            </body> 
        </html> 
        """

    err_data_template = """
        <h3>Error Data Map</h3>
        <br>
        <table style="width: 100%; border: 1px solid black;">
            {error_rows}
        </table>
        """

    rows = list()
    for key in sorted(alert_info.err_data):
        rows.append('<tr><td>{key}</td>  <td>=</td>  <td>{value}</td></tr>'.format(key=key,
                                                                                   value=alert_info.err_data[key]))

    err_data = err_data_template.format(error_rows=''.join(rows)) if rows else ''
    manage = "Automatic" if alert_info.manage == ScenAlertManageEnum.auto else "On-demand"
    return full_template.format(manage=manage, msg=alert_info.msg, err_data=err_data)


# -- Class Definitions --------------------------------------------------------------------------

class AlertsPanel(IScenarioMonitor, QWidget):
    """
    The alerts docked inside one of the main window docks.
    """

    # --------------------------- class-wide data and signals -----------------------------------

    sig_go_to_part = pyqtSignal(BasePart)

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, scenario_manager, parent: QWidget = None):
        IScenarioMonitor.__init__(self, scenario_manager)
        QWidget.__init__(self, parent)
        self.ui = Ui_AlertsContent()
        self.ui.setupUi(self)

        self.__scenario = None
        self.ui.alert_table_widget.setColumnWidth(ALERT_COL_TYPE, COL_TYPE_WIDTH)

        self.ui.alert_table_widget.setHorizontalHeaderLabels(ALERTS_TABLE_HEADER_NAMES)
        self.__filter = None

        self.__init_icons()

        self.ui.alert_table_widget.itemSelectionChanged.connect(self.__slot_on_item_selection_changed)
        self.ui.alert_table_widget.cellDoubleClicked.connect(self.__slot_on_cell_double_clicked)
        self.ui.validate_button.clicked.connect(self.__slot_on_validate_button_clicked)
        self.ui.filter_button.clicked.connect(self.__slot_on_filter_button_clicked)
        self._monitor_scenario_replacement()

    def on_alert_source_selected(self, source: IScenAlertSource):
        """
        It is equivalent to select a row on the panel and filter by it.
        :param source: The source to be used as a filter
        """
        self.__filter_by_source(source)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    slot_on_alert_source_selected = safe_slot(on_alert_source_selected)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        self.__scenario = scenario
        # Should disconnect the slot from the sig_alert_status_changed from the previous scenario? Wait and see...

        # init states
        self.__filter = None
        self.ui.val_filter.setText(FILTER_LABEL_NONE)
        self.ui.filter_button.setEnabled(False)
        self.ui.filter_button.setText(FILTER_BUTTON_FILTER)
        self.ui.alert_table_widget.clear()
        self.ui.alert_table_widget.setRowCount(0)
        self.ui.alert_table_widget.setHorizontalHeaderLabels(ALERTS_TABLE_HEADER_NAMES)
        self.ui.val_errors.setText(str(0))
        self.ui.val_warnings.setText(str(0))
        self.ui.details_text_browser.setText('')
        self.__ensure_filter_button_states()

        # Qt should automatically disconnect from previous Scenario when scenario is disposed of
        scenario.alert_signals.sig_alert_status_changed.connect(self.__slot_on_alert_status_changed)

    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __init_icons(self):
        MAP_ALERT_LEVEL_TO_IMG[ScenAlertLevelEnum.warning] = QPixmap(get_icon_path("alert_warning.svg"))
        MAP_ALERT_LEVEL_TO_IMG[ScenAlertLevelEnum.error] = QPixmap(get_icon_path("alert_error.svg"))

    def __on_item_selection_changed(self):
        """
        Displays the detailed info of the selected alert. Enables the filter button only if the source is a part.
        """
        alert_info = self.ui.alert_table_widget.item(self.ui.alert_table_widget.currentRow(),
                                                     ALERT_COL_COMPONENT).data(USER_ROLE_ALERT_INFO)

        self.ui.details_text_browser.setHtml(pretty_details_in_html(alert_info))

        if self.__filter is None:
            self.ui.filter_button.setEnabled(isinstance(alert_info.source, BasePart))
        else:
            self.ui.filter_button.setEnabled(True)

    def __on_validate_button_clicked(self):
        """
        Processes the validate button action. Re-check the on-demand alerts of the scenario.
        """
        AsyncRequest.call(self.__scenario.check_ondemand_alerts, response_cb=self.__get_alerts)

    def __filter_by_source(self, source: IScenAlertSource):
        self.__filter = source
        self.ui.val_filter.setText(source.source_name)
        self.ui.filter_button.setText(FILTER_BUTTON_UN_FILTER)
        self.ui.filter_button.setEnabled(True)
        AsyncRequest.call(source.get_alerts, response_cb=self.__update_alerts)

    def __on_filter_button_clicked(self):
        """
        Processes the filter button action.
        
        Filter on: gets the alerts on the filtered source only.
        Filter off: gets all the alerts on the scenario.
        """
        if self.__filter is None:
            alert_info = self.ui.alert_table_widget.item(self.ui.alert_table_widget.currentRow(),
                                                         ALERT_COL_COMPONENT).data(USER_ROLE_ALERT_INFO)
            self.__filter_by_source(alert_info.source)
        else:
            self.__filter = None
            self.ui.val_filter.setText(FILTER_LABEL_NONE)
            self.ui.filter_button.setText(FILTER_BUTTON_FILTER)
            AsyncRequest.call(self.__scenario.get_alerts, response_cb=self.__update_alerts)

    def __ensure_filter_button_states(self):
        """
        Enables/disables the filter button, depending on various situations.
        """
        if self.ui.alert_table_widget.currentRow() < 0:
            self.ui.filter_button.setEnabled(self.ui.filter_button.text() == FILTER_BUTTON_UN_FILTER)
            return

        alert_info = self.ui.alert_table_widget.item(self.ui.alert_table_widget.currentRow(),
                                                     ALERT_COL_COMPONENT).data(USER_ROLE_ALERT_INFO)

        self.ui.filter_button.setEnabled(isinstance(alert_info.source, BasePart))

    def __on_cell_double_clicked(self, row: int, col: int):
        """
        Displays the source, if it is a part, on the 2d view.
        :param row: The row index
        :param col: The column index
        """
        alert_info = self.ui.alert_table_widget.item(row, ALERT_COL_COMPONENT).data(USER_ROLE_ALERT_INFO)
        if isinstance(alert_info.source, BasePart):
            self.sig_go_to_part.emit(alert_info.source)

    def __on_alert_status_changed(self):
        self.__get_alerts()

    def __get_alerts(self):
        """
        Async call to get alerts on the filter or scenario if the filter is None.
        """
        which_item = self.__scenario if self.__filter is None else self.__filter
        AsyncRequest.call(which_item.get_alerts, response_cb=self.__update_alerts)

    def __update_alerts(self, alerts: Set[ScenAlertInfo]):
        """
        Populates the alert panel by using the values in the alerts.
        :param alerts: The alerts from various sources such as scenario, parts, etc.
        """
        sorted_alerts = sorted(alerts, key=lambda val: val.source.source_name)
        self.ui.alert_table_widget.clear()
        self.ui.alert_table_widget.setRowCount(0)
        self.ui.alert_table_widget.setHorizontalHeaderLabels(ALERTS_TABLE_HEADER_NAMES)
        num_errors = 0
        num_warnings = 0
        for row, alert in enumerate(sorted_alerts):
            self.ui.alert_table_widget.insertRow(row)

            # Type
            type_col = QLabel()
            type_col.setPixmap(MAP_ALERT_LEVEL_TO_IMG[alert.level])
            type_col.setAlignment(Qt.AlignCenter)
            self.ui.alert_table_widget.setCellWidget(row, ALERT_COL_TYPE, type_col)

            # Component
            # Use QTableWidgetItem because we want to use it to store some business data
            component_item = QTableWidgetItem(alert.source.source_name)
            component_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            component_item.setData(USER_ROLE_ALERT_INFO, alert)
            self.ui.alert_table_widget.setItem(row, ALERT_COL_COMPONENT, component_item)

            # Category
            self.ui.alert_table_widget.setCellWidget(row, ALERT_COL_CATEGORY, QLabel(alert.category.name))

            if alert.level == ScenAlertLevelEnum.error:
                num_errors += 1
            else:
                assert alert.level == ScenAlertLevelEnum.warning, ("The enum value {} is not defined in "
                                                                   "ScenAlertLevelEnum".format(alert.level))
                num_warnings += 1

        self.ui.val_errors.setText(str(num_errors))
        self.ui.val_warnings.setText(str(num_warnings))
        self.ui.details_text_browser.setText('')
        self.__ensure_filter_button_states()

    __slot_on_alert_status_changed = safe_slot(__on_alert_status_changed)
    __slot_on_validate_button_clicked = safe_slot(__on_validate_button_clicked)
    __slot_on_filter_button_clicked = safe_slot(__on_filter_button_clicked)
    __slot_on_item_selection_changed = safe_slot(__on_item_selection_changed)
    __slot_on_cell_double_clicked = safe_slot(__on_cell_double_clicked)

