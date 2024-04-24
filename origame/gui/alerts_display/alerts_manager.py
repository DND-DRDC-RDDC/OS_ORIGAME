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
from PyQt5.QtWidgets import QWidget, QLabel, QTableWidgetItem, QHeaderView, QMenu, QWidgetAction, QCheckBox, QTableWidget, QAbstractItemView
from PyQt5.QtGui import QPixmap, QFont
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
ALERTS_TABLE_HEADER_NAMES_WITH_FILTER = ['Type*', 'Component*', 'Category*']

COL_WIDTH = 150

ALERT_IMG_SIZE = QSize(24, 24)
MAP_ALERT_LEVEL_TO_IMG = {
}

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

class AlertFilterMenu(QMenu):
    """
    The drop-down menu in the alerts table header
    """

    # --------------------------- class-wide data and signals -----------------------------------

    filter_update_signal = pyqtSignal()

    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        super().__init__()
        self.setStyleSheet("QMenu { menu-scrollable: 1; }")

        self.add_checkable_action("Select All", True)

        self.filter_items = []

    def add_checkable_action(self, item, checked):
        checkbox = QCheckBox(item, self)
        checkbox.setChecked(checked)
        checkbox.toggled.connect(self.__slot_on_item_toggled)

        checkableAction = QWidgetAction(self)
        checkableAction.setDefaultWidget(checkbox)
        self.addAction(checkableAction)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_item_toggled(self, checked: bool):
        # All items in the menu except for "Select All"
        items = self.actions()
        del items[0]
 
        # Get the item that triggered this call
        item = self.sender()

        # If the item toggled is "Select All"
        if item.text() == "Select All":
            # If "Select All" is unchecked and no other items are checked, check "Select All" again
            if not checked:
                if not any(_item.defaultWidget().isChecked() for _item in items):
                    item.setChecked(True)
            # If "Select All" is checked, uncheck all other items
            else:
                for _item in items:
                    _item.defaultWidget().setChecked(False)
                self.filter_items = []
        # All other items
        else:
            # If the item is unchecked, remove it from the filtering items
            if not checked:
                self.filter_items.remove(item.text())
            # If the item is checked, add it to the filtering items
            else:
                self.filter_items.append(item.text())

            # If any item is checked, uncheck "Select All"
            if any(_item.defaultWidget().isChecked() for _item in items):
                self.actions()[0].defaultWidget().setChecked(False)
            # Otherwise, "Select All" has to be checked
            else:
                self.actions()[0].defaultWidget().setChecked(True)

        self.filter_update_signal.emit()

    __slot_on_item_toggled = safe_slot(__on_item_toggled)


class AlertTableHeader(QHeaderView):
    """
    The alerts table header.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent = None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.sectionResized.connect(self.__slot_on_section_resized)
        self.setMinimumSectionSize(COL_WIDTH)

        self.header_sections = []

    def setItemWidget(self, index: int, widget: QWidget):
        self.header_sections.insert(index, widget)

    def showEvent(self, e):
        for i in range(self.count()):
            section = self.header_sections[i]

            if not section:
                section = QWidget(self)
            else:
                section.setParent(self)

            section.setGeometry(self.sectionViewportPosition(i), 0, self.sectionSize(i) - 1, self.height() - 1)
            section.show()

        super().showEvent(e)

    def sizeHint(self):
        size = super().sizeHint()

        if self.header_sections:
            height = self.header_sections[0].sizeHint().height()
            size.setHeight(height)

        return size

    def updateGeometries(self):
        self.setViewportMargins(0, 0, 0, 0)
        super().updateGeometries()
        self.__on_section_resized()

    def fixItemPosition(self):
        for i in range(self.count()):
            section = self.header_sections[i]
            margins = section.contentsMargins()
            section.setGeometry(self.sectionViewportPosition(i) + margins.left(),
                             margins.top(),
                             self.sectionSize(i) - margins.left() - margins.right() - 1,
                             self.height() - margins.top() - margins.bottom() - 1)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __on_section_resized(self):
        if not self.header_sections:
            return

        for i in range(self.count()):
            section = self.header_sections[i]
            height = section.sizeHint().height()
            section.move(self.sectionPosition(self.logicalIndex(i)) - self.offset(), 0)
            section.resize(self.sectionSize(self.logicalIndex(i)), height)
    
    __slot_on_section_resized = safe_slot(__on_section_resized)

class AlertsTableWidget(QTableWidget):
    """
    Alerts Table with custom header.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        header = AlertTableHeader(self)
        self.setHorizontalHeader(header)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setColumnCount(3)

    def setHorizontalHeaderItem(self, column: int, widget: QWidget):
        self.horizontalHeader().setItemWidget(column, widget)

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)

        if dx != 0:
            self.horizontalHeader().fixItemPosition()

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------
    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------


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

        self.alert_table_widget = AlertsTableWidget(self)
        self.ui.verticalLayout.insertWidget(0, self.alert_table_widget)
        self.__set_alert_table_header()

        self.alert_type_filter = AlertFilterMenu()
        self.ui.alert_type_btn.setMenu(self.alert_type_filter)

        self.alert_component_filter = AlertFilterMenu()
        self.ui.alert_component_btn.setMenu(self.alert_component_filter)

        self.alert_category_filter = AlertFilterMenu()
        self.ui.alert_category_btn.setMenu(self.alert_category_filter)

        self.__type_filter = None
        self.__category_filter = None
        self.__component_filter = None
        self.alert_type_filter.filter_update_signal.connect(self.__slot_on_type_filter_update_signal)
        self.alert_category_filter.filter_update_signal.connect(self.__slot_on_category_filter_update_signal)
        self.alert_component_filter.filter_update_signal.connect(self.__slot_on_component_filter_update_signal)

        self.__hidden_rows = {ALERT_COL_TYPE: [], ALERT_COL_COMPONENT: [], ALERT_COL_CATEGORY: []}

        self.__init_icons()

        self.alert_table_widget.itemSelectionChanged.connect(self.__slot_on_item_selection_changed)
        self.alert_table_widget.cellDoubleClicked.connect(self.__slot_on_cell_double_clicked)
        self.ui.validate_button.clicked.connect(self.__slot_on_validate_button_clicked)
        self.ui.clear_filters_button.clicked.connect(self.__slot_on_clear_filters_button_clicked)
        self._monitor_scenario_replacement()

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        self.__scenario = scenario
        # Should disconnect the slot from the sig_alert_status_changed from the previous scenario? Wait and see...

        # init states
        self.__type_filter = None
        self.__component_filter = None
        self.__category_filter = None
        self.ui.val_errors.setText(str(0))
        self.ui.val_warnings.setText(str(0))
        self.ui.details_text_browser.setText('')
        self.__ensure_clear_filters_button_states()
        self.__set_alert_table_header()

        # Reset the columns labels
        self._reset_label_component()
        self._reset_label_category()
        self._reset_label_type()

        # Reset the columns size
        self.alert_table_widget.setColumnWidth(ALERT_COL_TYPE, COL_WIDTH)
        self.alert_table_widget.setColumnWidth(ALERT_COL_CATEGORY, COL_WIDTH)
        self.alert_table_widget.setColumnWidth(ALERT_COL_COMPONENT, COL_WIDTH)

        # Enure the drop-down menus in the columns header are cleared (they will still have "Select All")
        self.alert_type_filter = AlertFilterMenu()
        self.ui.alert_type_btn.setMenu(self.alert_type_filter)
        self.alert_component_filter = AlertFilterMenu()
        self.ui.alert_component_btn.setMenu(self.alert_component_filter)
        self.alert_category_filter = AlertFilterMenu()
        self.ui.alert_category_btn.setMenu(self.alert_category_filter)
        self.alert_type_filter.filter_update_signal.connect(self.__slot_on_type_filter_update_signal)
        self.alert_category_filter.filter_update_signal.connect(self.__slot_on_category_filter_update_signal)
        self.alert_component_filter.filter_update_signal.connect(self.__slot_on_component_filter_update_signal)

        # Qt should automatically disconnect from previous Scenario when scenario is disposed of
        scenario.alert_signals.sig_alert_status_changed.connect(self.__slot_on_alert_status_changed)

    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __set_alert_table_header(self):
        """
        Sets the alerts table header and clears the table.
        """

        self.alert_table_widget.clear()
        self.alert_table_widget.setRowCount(0)

        self.alert_table_widget.setHorizontalHeaderItem(ALERT_COL_TYPE, self.ui.type_frame)
        self.alert_table_widget.setHorizontalHeaderItem(ALERT_COL_COMPONENT, self.ui.component_frame)
        self.alert_table_widget.setHorizontalHeaderItem(ALERT_COL_CATEGORY, self.ui.category_frame)

        # The header labels are already set in the header items in self.ui.label_type, self.ui.label_component and self.ui.label_category
        self.alert_table_widget.setHorizontalHeaderLabels(["", "", ""])

    def _reset_label_component(self):
        """
        Resets the Component label back to default
        """
        _font = QFont()
        _font.setBold(False)
        self.ui.label_component.setFont(_font)
        self.ui.label_component.setText(ALERTS_TABLE_HEADER_NAMES[ALERT_COL_COMPONENT])
    
    def _reset_label_category(self):
        """
        Resets the Category label back to default
        """
        _font = QFont()
        _font.setBold(False)
        self.ui.label_category.setFont(_font)
        self.ui.label_category.setText(ALERTS_TABLE_HEADER_NAMES[ALERT_COL_CATEGORY])

    def _reset_label_type(self):
        """
        Resets the Type label back to default
        """
        _font = QFont()
        _font.setBold(False)
        self.ui.label_type.setFont(_font)
        self.ui.label_type.setText(ALERTS_TABLE_HEADER_NAMES[ALERT_COL_TYPE])

    def __init_icons(self):
        MAP_ALERT_LEVEL_TO_IMG[ScenAlertLevelEnum.warning] = QPixmap(get_icon_path("alert_warning.svg"))
        MAP_ALERT_LEVEL_TO_IMG[ScenAlertLevelEnum.error] = QPixmap(get_icon_path("alert_error.svg"))

    def __on_item_selection_changed(self):
        """
        Displays the detailed info of the selected alert.
        """
        alert_info = self.alert_table_widget.item(self.alert_table_widget.currentRow(),
                                                     ALERT_COL_COMPONENT).data(USER_ROLE_ALERT_INFO)

        self.ui.details_text_browser.setHtml(pretty_details_in_html(alert_info))

        self.__ensure_clear_filters_button_states()

    def __on_validate_button_clicked(self):
        """
        Processes the validate button action. Re-check the on-demand alerts of the scenario.
        """
        AsyncRequest.call(self.__scenario.check_ondemand_alerts, response_cb=self.__get_alerts)

    def __on_clear_filters_button_clicked(self):
        """
        Processes the Clear Filters button action.
        """
        for _filter in [self.alert_category_filter, self.alert_component_filter, self.alert_type_filter]:
            # Uncheck all items expect the first item "Select All"
            all_items = _filter.actions()
            del all_items[0]

            for _item in all_items:
                _item.defaultWidget().setChecked(False)

            # Check "Select All"
            _filter.actions()[0].defaultWidget().setChecked(True)

            # Clear the list of filter items
            _filter.filter_items = []

        self.__get_alerts()

    def __ensure_clear_filters_button_states(self):
        """
        Enables/disables the Clear Filters button depending on whether there are active filters.
        """
        if self.__type_filter is None and self.__component_filter is None and self.__category_filter is None:
            self.ui.clear_filters_button.setEnabled(False)
        else:
            self.ui.clear_filters_button.setEnabled(True)

        self.__update_filters_number()

    def __update_filters_number(self):
        """
        Updates the number of current active filters.
        """
        __num_of_filters = 0

        if self.__type_filter:
            __num_of_filters += len(self.__type_filter)
        if self.__category_filter:
            __num_of_filters += len(self.__category_filter)
        if self.__component_filter:
            __num_of_filters += len(self.__component_filter)

        self.ui.val_filter.setText(str(__num_of_filters))

    def __on_cell_double_clicked(self, row: int, col: int):
        """
        Displays the source, if it is a part, on the 2d view.
        :param row: The row index
        :param col: The column index
        """
        alert_info = self.alert_table_widget.item(row, ALERT_COL_COMPONENT).data(USER_ROLE_ALERT_INFO)
        if isinstance(alert_info.source, BasePart):
            self.sig_go_to_part.emit(alert_info.source)

    def __on_alert_status_changed(self):
        self.__get_alerts()

    def __get_alerts(self):
        """
        Async call to get alerts on the filter or scenario if the filter is None.
        """
        AsyncRequest.call(self.__scenario.get_alerts, response_cb=self.__update_alerts)

    def __update_alerts(self, alerts: Set[ScenAlertInfo]):
        """
        Populates the alert panel by using the values in the alerts.
        :param alerts: The alerts from various sources such as scenario, parts, etc.
        """
        sorted_alerts = sorted(alerts, key=lambda val: val.source.source_name)
        self.__set_alert_table_header()
        num_errors = 0
        num_warnings = 0
        for row, alert in enumerate(sorted_alerts):
            self.alert_table_widget.insertRow(row)

            # Type
            type_col = QLabel()
            type_col.setPixmap(MAP_ALERT_LEVEL_TO_IMG[alert.level])
            type_col.setAlignment(Qt.AlignCenter)
            self.alert_table_widget.setCellWidget(row, ALERT_COL_TYPE, type_col)

            if not alert.level.name in [a.defaultWidget().text() for a in self.alert_type_filter.actions()]:
                self.alert_type_filter.add_checkable_action(alert.level.name, False)

            # Component
            # Use QTableWidgetItem because we want to use it to store some business data
            component_item = QTableWidgetItem(alert.source.source_name)
            component_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            component_item.setData(USER_ROLE_ALERT_INFO, alert)
            self.alert_table_widget.setItem(row, ALERT_COL_COMPONENT, component_item)

            # If the alert component doesn't already exist in the combobox, add it and set it as unchecked
            if not component_item.text() in [a.defaultWidget().text() for a in self.alert_component_filter.actions()]:
                self.alert_component_filter.add_checkable_action(component_item.text(), False)

            # Category
            self.alert_table_widget.setCellWidget(row, ALERT_COL_CATEGORY, QLabel(alert.category.name))

            # If the alert category doesn't already exist in the combobox, add it
            if not alert.category.name in [a.defaultWidget().text() for a in self.alert_category_filter.actions()]:
                self.alert_category_filter.add_checkable_action(alert.category.name, False)

            if alert.level == ScenAlertLevelEnum.error:
                num_errors += 1
            else:
                assert alert.level == ScenAlertLevelEnum.warning, ("The enum value {} is not defined in "
                                                                   "ScenAlertLevelEnum".format(alert.level))
                num_warnings += 1

        self.ui.val_errors.setText(str(num_errors))
        self.ui.val_warnings.setText(str(num_warnings))
        self.ui.details_text_browser.setText('')
        self.__ensure_clear_filters_button_states()

        # This will ensure that the active filter(s), if any, apply on the new alert(s)
        self.__on_component_filter_update()
        self.__on_category_filter_update()
        self.__on_type_filter_update()

        self.alert_table_widget.resizeColumnsToContents()

    def __on_type_filter_update(self):
        filters = self.alert_type_filter.filter_items

        if filters == []:
            self.__type_filter = None

            # Reset the font and column name
            self._reset_label_type()

            # Remove all row indices that were hidden because of the type filter
            for i in self.__hidden_rows[ALERT_COL_TYPE]:
                self.alert_table_widget.setRowHidden(i, False)
            self.__hidden_rows[ALERT_COL_TYPE] = []

        else:
            self.__type_filter = filters

            # Set the font to bold and change column name
            _font = QFont()
            _font.setBold(True)
            self.ui.label_type.setFont(_font)
            self.ui.label_type.setText(ALERTS_TABLE_HEADER_NAMES_WITH_FILTER[ALERT_COL_TYPE])

            for i in range(self.alert_table_widget.rowCount()):
                # If the row is hidden by another filter, skip the row
                if i not in self.__hidden_rows[ALERT_COL_CATEGORY] and i not in self.__hidden_rows[ALERT_COL_COMPONENT]:
                    _item = self.alert_table_widget.cellWidget(i, ALERT_COL_TYPE)
                    hide = True
                    for level in filters:
                        if _item.pixmap().toImage() == QPixmap(get_icon_path(f"alert_{level}.svg")).toImage():
                            hide = False
                            break
                    self.alert_table_widget.setRowHidden(i, hide)
                    # If hide is True, append the row to list of rows hidden by Type filter (if it doesn't already exist)
                    if hide:
                        if i not in self.__hidden_rows[ALERT_COL_TYPE]: self.__hidden_rows[ALERT_COL_TYPE].append(i)
                    # Otherwise, remove it from the list of rows hidden by Type filter (if it exists)
                    else:
                        if i in self.__hidden_rows[ALERT_COL_TYPE]: self.__hidden_rows[ALERT_COL_TYPE].remove(i)

        self.__ensure_clear_filters_button_states()

    def __on_category_filter_update(self): 
        filters = self.alert_category_filter.filter_items

        if filters == []:
            self.__category_filter = None

            # Reset the font and column name
            self._reset_label_category()
        
            # Remove all row indices that were hidden because of the category filter
            for i in self.__hidden_rows[ALERT_COL_CATEGORY]:
                self.alert_table_widget.setRowHidden(i, False)
            self.__hidden_rows[ALERT_COL_CATEGORY] = []

        else:
            self.__category_filter = filters

            # Set the font to bold and change column name
            _font = QFont()
            _font.setBold(True)
            self.ui.label_category.setFont(_font)
            self.ui.label_category.setText(ALERTS_TABLE_HEADER_NAMES_WITH_FILTER[ALERT_COL_CATEGORY])

            for i in range(self.alert_table_widget.rowCount()):
                # If the row is hidden by another filter, skip the row
                if i not in self.__hidden_rows[ALERT_COL_TYPE] and i not in self.__hidden_rows[ALERT_COL_COMPONENT]:
                    _item = self.alert_table_widget.cellWidget(i, ALERT_COL_CATEGORY)
                    hide = _item.text() not in filters
                    self.alert_table_widget.setRowHidden(i, hide)
                    # If hide is True, append the row to list of rows hidden by Category filter (if it doesn't already exist)
                    if hide:
                        if i not in self.__hidden_rows[ALERT_COL_CATEGORY]: self.__hidden_rows[ALERT_COL_CATEGORY].append(i)
                    # Otherwise, remove it from the list of rows hidden by Category filter (if it exists)
                    else:
                        if i in self.__hidden_rows[ALERT_COL_CATEGORY]: self.__hidden_rows[ALERT_COL_CATEGORY].remove(i)

        self.__ensure_clear_filters_button_states()

    def __on_component_filter_update(self):
        filters = self.alert_component_filter.filter_items

        if filters == []:    
            self.__component_filter = None

            # Reset the font and column name
            self._reset_label_component()

            # Remove all row indices that were hidden because of the component filter
            for i in self.__hidden_rows[ALERT_COL_COMPONENT]:
                self.alert_table_widget.setRowHidden(i, False)
            self.__hidden_rows[ALERT_COL_COMPONENT] = []    

        else:
            self.__component_filter = filters

            # Set the font to bold and change column name
            _font = QFont()
            _font.setBold(True)
            self.ui.label_component.setFont(_font)
            self.ui.label_component.setText(ALERTS_TABLE_HEADER_NAMES_WITH_FILTER[ALERT_COL_COMPONENT])

            for i in range(self.alert_table_widget.rowCount()):
                # If the row is hidden by another filter, skip the row
                if i not in self.__hidden_rows[ALERT_COL_TYPE] and i not in self.__hidden_rows[ALERT_COL_CATEGORY]:
                    _item = self.alert_table_widget.item(i, ALERT_COL_COMPONENT)
                    hide = _item.text() not in filters
                    self.alert_table_widget.setRowHidden(i, hide)
                    # If hide is True, append the row to list of rows hidden by Component filter (if it doesn't already exist)
                    if hide:
                        if i not in self.__hidden_rows[ALERT_COL_COMPONENT]: self.__hidden_rows[ALERT_COL_COMPONENT].append(i)
                    # Otherwise, remove it from the list of rows hidden by Component filter (if it exists)
                    else:
                        if i in self.__hidden_rows[ALERT_COL_COMPONENT]: self.__hidden_rows[ALERT_COL_COMPONENT].remove(i)

        self.__ensure_clear_filters_button_states()

    __slot_on_alert_status_changed = safe_slot(__on_alert_status_changed)
    __slot_on_validate_button_clicked = safe_slot(__on_validate_button_clicked)
    __slot_on_clear_filters_button_clicked = safe_slot(__on_clear_filters_button_clicked)
    __slot_on_item_selection_changed = safe_slot(__on_item_selection_changed)
    __slot_on_cell_double_clicked = safe_slot(__on_cell_double_clicked)
    __slot_on_type_filter_update_signal = safe_slot(__on_type_filter_update)
    __slot_on_category_filter_update_signal = safe_slot(__on_category_filter_update)
    __slot_on_component_filter_update_signal = safe_slot(__on_component_filter_update)
