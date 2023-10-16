# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Event Queue functionality and methods for the GUI.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from pathlib import Path
from inspect import signature

# [2. third-party]
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtWidgets import QWidget, QTableWidgetItem, QDialog, QAbstractItemView, QMessageBox

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario import EventQueue, CallInfo, EventInfo, ScenarioManager, Scenario, SimStatesEnum as MainSimStatesEnum
from ...scenario.part_execs import IExecutablePart
from ...scenario.defn_parts import BasePart

from ..async_methods import AsyncRequest
from ..animation import IHasAnimationMode
from ..conversions import convert_days_to_time_components, convert_float_days_to_string, convert_time_components_to_days
from ..gui_utils import IScenarioMonitor, BUTTON_ICON_PIXMAPS, set_button_image, get_scenario_font
from ..gui_utils import get_icon_path, exec_modal_dialog
from ..safe_slot import safe_slot, ext_safe_slot

from .Ui_event_queue import Ui_SimulationEventQueue
from .Ui_event_queue_item import Ui_SimulationEventQueueItemDialog
from .common import SimDialog

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'SimEventQueuePanel',
    'CreateEventDialog'
]

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class RowItem(QObject):
    """
    A row item representing an event in the Event Queue Panel table.

    Input arguments:
        - num_days: [float] the time expressed in days
        - priority: [float] the priority of the event
        - call_info: [CallInfo] executable part exec information

    Each row item contains seven cells that display a piece of the event information. Each cell is a QTableWidgetItem
    that display the following event information:
        - Event ID: [int] a unique number used to identify the event (not displayed but used to look-up the event)
        - Event time: [str] a time stamp formatted as days and then hours: minutes: seconds. e.g. 'dddd hh:mm:ss'
        - Event priority: [str] the event priority from 0 (low) to 1,000,000 (high) or ASAP (1 million +1)
        - Part name: [str] the executable part responsible for generating this event
        - Part type: [str] the type of executable part including 'function', 'SQL', and 'multiplier' parts
        - Part arguments: [str] the set of arguments associated with the executable part
        - Path: [str] the path in the actor hierarchy to the executable part
    """

    def __init__(self, num_days: float, priority: float, call_info: CallInfo):
        super().__init__()

        # Keep the input args for editing
        self._input_num_days = num_days
        self._input_priority = float(priority)
        self._input_call_info = call_info

        # The executable part associated with this row data
        self._exec_part = call_info.iexec

        # The event data for this row
        self._id = call_info.unique_id
        self._time = convert_float_days_to_string(num_days)
        self._part_name = self._exec_part.part_frame.name
        self._part_type = self._exec_part.PART_TYPE_NAME
        self._part_args = call_info.get_args_as_string()
        self._path = '/'.join(self._exec_part.get_path_list(with_root=True, with_name=False))

        if priority == EventQueue.ASAP_PRIORITY_VALUE:
            self._priority = 'ASAP'
        else:
            self._priority = repr(self._input_priority)

        # Table widget items
        self._id_table_widget = QTableWidgetItem()
        self._time_table_widget = QTableWidgetItem()
        self._priority_table_widget = QTableWidgetItem()
        self._part_name_table_widget = QTableWidgetItem()
        self._part_type_table_widget = QTableWidgetItem()
        self._part_args_table_widget = QTableWidgetItem()
        self._path_table_widget = QTableWidgetItem()

        self._id_table_widget.setFont(get_scenario_font())
        self._time_table_widget.setFont(get_scenario_font())
        self._priority_table_widget.setFont(get_scenario_font())
        self._part_name_table_widget.setFont(get_scenario_font())
        self._part_type_table_widget.setFont(get_scenario_font())
        self._part_args_table_widget.setFont(get_scenario_font())
        self._path_table_widget.setFont(get_scenario_font())

        # Set text to display in each widget
        self._id_table_widget.setData(Qt.DisplayRole, self._id)
        self._time_table_widget.setText(self._time)
        self._priority_table_widget.setText(self._priority)
        self._part_name_table_widget.setText(self._part_name)
        self._part_type_table_widget.setText(self._part_type)
        self._part_args_table_widget.setText(self._part_args)
        self._path_table_widget.setText(self._path)

        # Signals from back-end that will change row data
        self._exec_part.part_frame.signals.sig_name_changed.connect(self.__slot_on_name_changed)
        self._exec_part.part_frame.part.base_part_signals.sig_parent_path_change.connect(self.__slot_on_path_changed)

    def get_event_inputs(self) -> Tuple[float, float, CallInfo]:
        return (self._input_num_days, self._input_priority, self._input_call_info)

    def get_exec_part(self) -> IExecutablePart:
        return self._exec_part

    def get_id(self) -> int:
        return self._id

    def get_time(self) -> str:
        return self._time

    def set_time(self, new_time: float):
        self._input_num_days = new_time
        self._time = convert_float_days_to_string(new_time)
        self._time_table_widget.setText(self._time)

    def get_priority(self) -> str:
        return self._priority

    def set_priority(self, new_priority: float):
        self._input_priority = float(new_priority)

        if new_priority == EventQueue.ASAP_PRIORITY_VALUE:
            self._priority = 'ASAP'
        else:
            self._priority = repr(self._input_priority)

        self._priority_table_widget.setText(self._priority)

    def get_part_name(self) -> str:
        return self._part_name

    def get_part_type(self) -> str:
        return self._part_type

    def get_part_args(self) -> str:
        return self._part_args

    def set_part_args(self, new_args: str):
        self._part_args = new_args
        self._part_args_table_widget.setText(self._part_args)

    def get_path(self) -> str:
        return self._path

    def get_id_table_widget(self) -> QTableWidgetItem:
        return self._id_table_widget

    def get_time_table_widget(self) -> QTableWidgetItem:
        return self._time_table_widget

    def get_priority_table_widget(self) -> QTableWidgetItem:
        return self._priority_table_widget

    def get_part_name_table_widget(self) -> QTableWidgetItem:
        return self._part_name_table_widget

    def get_part_type_table_widget(self) -> QTableWidgetItem:
        return self._part_type_table_widget

    def get_part_args_table_widget(self) -> QTableWidgetItem:
        return self._part_args_table_widget

    def get_path_table_widget(self) -> QTableWidgetItem:
        return self._path_table_widget

    def disconnect_part_signal(self):
        """
        Allows external class methods to disconnect the signal from the executable part for this row
        """
        self._exec_part.part_frame.signals.sig_name_changed.disconnect(self.__slot_on_name_changed)

    # Properties
    exec_part = property(get_exec_part)
    id = property(get_id)
    time = property(get_time, set_time)
    priority = property(get_priority, set_priority)
    part_name = property(get_part_name)
    part_type = property(get_part_type)
    part_args = property(get_part_args, set_part_args)
    path = property(get_path)
    id_table_widget = property(get_id_table_widget)
    time_table_widget = property(get_time_table_widget)
    priority_table_widget = property(get_priority_table_widget)
    part_name_table_widget = property(get_part_name_table_widget)
    part_type_table_widget = property(get_part_type_table_widget)
    part_args_table_widget = property(get_part_args_table_widget)
    path_table_widget = property(get_path_table_widget)

    # Slots
    def __on_name_changed(self, new_name: str):
        """
        Reset the executable part name in the table widget item.
        """
        self._part_name = new_name
        self._part_name_table_widget.setText(self._part_name)

    def __on_path_changed(self):
        """
        Reset the path in the table widget item.
        """
        self._path = '/'.join(self._exec_part.get_path_list(with_root=True, with_name=False))
        self._path_table_widget.setText(self._path)

    __slot_on_name_changed = safe_slot(__on_name_changed)
    __slot_on_path_changed = safe_slot(__on_path_changed)


# noinspection PyUnresolvedReferences
class EventQueueDialog(SimDialog):
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.ui = Ui_SimulationEventQueueItemDialog()
        self.ui.setupUi(self)
        self._args_list_editable = True
        self.ui.asap_check_box.stateChanged.connect(self._slot_on_asap_checked)

        self._orig_time = None
        self.orig_time_components = None
        self._event_info = None
        self._priority = None
        self._time = None
        self._args_str = None
        self._isvalid = False

    def _validate_input(self, result: int):
        """
        Method used to validate teh inputs by the user in teh Event Queue Dialog.
        :param result: The button role that the user clicked.
        """
        if result == QDialog.Accepted:

            # Time
            days = int(self.ui.days_spinbox.value())
            hours = int(self.ui.hours_spinbox.value())
            minutes = int(self.ui.minutes_spinbox.value())
            seconds = int(self.ui.seconds_spinbox.value())

            if self.orig_time_components == (days, hours, minutes, seconds):
                self._time = self._orig_time
            else:
                self._time = convert_time_components_to_days(float(days), float(hours),
                                                             float(minutes), float(seconds))

            # Priority
            if self.ui.asap_check_box.isChecked():
                self._priority = EventQueue.ASAP_PRIORITY_VALUE
            else:
                self._priority = self.ui.priority_double_spin_box.value()

            # Args
            self._args_str = self.ui.param_line_edit.text()
            # IF the args can be edited, check that changes are valid
            if self._args_list_editable:
                is_valid_str = CallInfo.repr_evaluatable(self._args_str)
                if not is_valid_str:
                    exec_modal_dialog('Syntax Error', 'Arguments list contains invalid Python syntax.',
                                      QMessageBox.Critical)

                    # Do not set validity to true
                    return

            self._isvalid = True

    @override(QDialog)
    def done(self, result: int):

        # Check input validity - skip the super() method if invalid
        # to keep the dialog open so user can enter valid inputs
        if not self._isvalid and result != QDialog.Rejected:
            return

        # Otherwise dialog is accepted with valid inputs or rejected
        super().done(result)

    def _on_asap_checked(self, state: int):
        """
        Shows the event priority spinbox if ASAP is not checked and hides it otherwise.
        :param state: the checked state (checked, unchecked)
        """
        if state == Qt.Unchecked:
            self.ui.priority_double_spin_box.setVisible(True)
            self.ui.days_spinbox.setEnabled(True)
            self.ui.hours_spinbox.setEnabled(True)
            self.ui.minutes_spinbox.setEnabled(True)
            self.ui.seconds_spinbox.setEnabled(True)
        else:
            self.ui.priority_double_spin_box.setVisible(False)
            self.ui.days_spinbox.setEnabled(False)
            self.ui.hours_spinbox.setEnabled(False)
            self.ui.minutes_spinbox.setEnabled(False)
            self.ui.seconds_spinbox.setEnabled(False)

    _slot_on_asap_checked = safe_slot(_on_asap_checked)


class CreateEventDialog(EventQueueDialog):
    """
    Dialog to handle user event creation
    """

    # noinspection PyUnresolvedReferences
    def __init__(self, part: IExecutablePart, parent: QWidget = None):
        super().__init__(parent)

        self.setWindowTitle("Simulation Event Queue: Create Item")

        # Populate dialog

        # Non-editable fields
        self._part = part
        self.ui.path_line_edit.setFont(get_scenario_font())
        self.ui.name_line_edit.setFont(get_scenario_font())
        self.ui.param_line_edit.setFont(get_scenario_font())
        self.ui.days_spinbox.setFont(get_scenario_font())
        self.ui.hours_spinbox.setFont(get_scenario_font())
        self.ui.minutes_spinbox.setFont(get_scenario_font())
        self.ui.seconds_spinbox.setFont(get_scenario_font())
        self.ui.priority_double_spin_box.setFont(get_scenario_font())

        self.ui.path_line_edit.setText(part.path)
        self.ui.name_line_edit.setText(part.name)
        self.ui.asap_check_box.setChecked(True)
        self._on_asap_checked(Qt.Checked)

        def ui_init_from_backend():
            sim_controller = part.shared_scenario_state.sim_controller
            return part.get_signature(), sim_controller.sim_time_days

        def ui_init_to_frontend(inspected_signature: signature, current_sim_time: float):
            args_in_str = ""
            if len(inspected_signature.parameters) > 0:
                params = inspected_signature.parameters
                at_least_one_default = False
                for param_val in params.values():
                    if param_val.default is not param_val.empty:
                        at_least_one_default = True
                        break

                if at_least_one_default:
                    first = True
                    for param_val in params.values():
                        if first:
                            first = False
                        else:
                            args_in_str += ","
                        if param_val.default is not param_val.empty:
                            args_in_str += str(param_val.default)

            self.ui.param_line_edit.setText(args_in_str)

            self.orig_time_components = convert_days_to_time_components(current_sim_time)
            days, hours, minutes, seconds = self.orig_time_components
            self.ui.days_spinbox.setValue(days)
            self.ui.hours_spinbox.setValue(hours)
            self.ui.minutes_spinbox.setValue(minutes)
            self.ui.seconds_spinbox.setValue(seconds)

        AsyncRequest.call(ui_init_from_backend, response_cb=ui_init_to_frontend)

    @override(EventQueueDialog)
    def _validate_input(self, result: int):
        super()._validate_input(result)

        if self._isvalid:
            # noinspection PyTypeChecker
            args_tuple = CallInfo.get_args_from_string(self._args_str)
            AsyncRequest.call(self._part.add_event, self._part, args_tuple, self._time, self._priority)

    @override(EventQueueDialog)
    def done(self, result: int):
        self._validate_input(result)
        super().done(result)


class EditEventDialog(EventQueueDialog):
    """
    Dialog to handle user event edits.
    """

    # noinspection PyUnresolvedReferences
    def __init__(self, event_queue_item: RowItem, parent: QWidget = None):
        super().__init__(parent)

        self.setWindowTitle("Simulation Event Queue: Edit Item")

        # Create EventInfo with original values for back-end EventQueue
        self._orig_time, orig_priority, orig_call_info = event_queue_item.get_event_inputs()
        self._event_info = EventInfo(self._orig_time, orig_priority, orig_call_info)

        # Populate dialog

        # Non-editable fields
        self.ui.path_line_edit.setText(event_queue_item.path)
        self.ui.name_line_edit.setText(event_queue_item.part_name)

        # Args list
        self.ui.param_line_edit.setText(event_queue_item.part_args)
        if not orig_call_info.args_repr_evaluatable():
            # Disable if any parameter cannot be edited (e.g. it is an object)
            self.ui.param_line_edit.setEnabled(False)
            self._args_list_editable = False

        # Time values
        self.orig_time_components = convert_days_to_time_components(self._orig_time)
        if self.orig_time_components:
            days, hours, minutes, seconds = self.orig_time_components
            self.ui.days_spinbox.setValue(days)
            self.ui.hours_spinbox.setValue(hours)
            self.ui.minutes_spinbox.setValue(minutes)
            self.ui.seconds_spinbox.setValue(seconds)

        # Priority
        self.ui.priority_double_spin_box.setValue(orig_priority)
        if orig_priority == EventQueue.ASAP_PRIORITY_VALUE:
            self.ui.asap_check_box.setChecked(True)
        else:
            self.ui.asap_check_box.setChecked(False)

    @override(EventQueueDialog)
    def done(self, result: int):
        self._validate_input(result)
        super().done(result)

    def get_user_input(self) -> Tuple[EventInfo, float, float, str]:
        """
        Get the input from the dialog.
        :return: A tuple of user input.
        """
        assert self._isvalid
        return self._event_info, self._time, self._priority, self._args_str

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(EventQueueDialog)
    def _validate_input(self, result: int):
        super()._validate_input(result)


class SimEventQueuePanel(QWidget, IHasAnimationMode, IScenarioMonitor):
    """
    Event Queue UI class to handle front-end user-actions to 'back-end' Event Queue object.
    """
    sig_clear_event_queue = pyqtSignal()
    sig_enable_event_queue = pyqtSignal(bool)  # True if enabled, False otherwise

    # noinspection PyUnresolvedReferences
    def __init__(self, scenario_manager: ScenarioManager, parent: QWidget = None):
        QWidget.__init__(self, parent)
        IHasAnimationMode.__init__(self)
        IScenarioMonitor.__init__(self, scenario_manager)

        self.ui = Ui_SimulationEventQueue()
        self.ui.setupUi(self)
        self.ui.event_queue_table_widget.setAutoScroll(True)

        # Hide the event ID column, customize column widths (can't in Designer)
        self.ui.event_queue_table_widget.hideColumn(0)

        # Set column headers to left-aligned
        for col in range(0, self.ui.event_queue_table_widget.columnCount()):
            self.ui.event_queue_table_widget.horizontalHeaderItem(col).setTextAlignment(Qt.AlignLeft)

        # Set the delete icon
        icon_file = BUTTON_ICON_PIXMAPS['delete']
        path_to_image = get_icon_path(icon_file)
        set_button_image(self.ui.delete_tool_button, path_to_image)

        # Set the Clear Queue icon
        icon_file = BUTTON_ICON_PIXMAPS['clear']
        path_to_image = get_icon_path(icon_file)
        set_button_image(self.ui.clear_queue_tool_button, path_to_image)

        # Disable until populated with events or event selected
        self.ui.edit_tool_button.setEnabled(False)
        self.ui.delete_tool_button.setEnabled(False)
        self.ui.clear_queue_tool_button.setEnabled(False)

        # Limit selection to one row at a time, no cell edits
        self.ui.event_queue_table_widget.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.ui.event_queue_table_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.ui.event_queue_table_widget.setEditTriggers(QAbstractItemView.NoEditTriggers)

        # Connect buttons
        self.ui.edit_tool_button.clicked.connect(self._slot_on_user_event_edit_dialog)
        self.ui.delete_tool_button.clicked.connect(self._slot_on_user_delete_event)
        self.ui.clear_queue_tool_button.clicked.connect(self._slot_on_user_clear_queue)
        self.ui.clear_filter_button.clicked.connect(self.__slot_on_user_cleared_filter)
        self.ui.clear_filter_button.setEnabled(False)

        # Class attributes
        self._table_data = dict()
        self._prev_row_selected = None
        self._waiting_for_queue_reload = False
        self._user_edit_event = False

        # Other front-end signals
        self.ui.event_queue_table_widget.itemSelectionChanged.connect(self._slot_on_item_selected_changed)
        self.ui.event_queue_table_widget.itemDoubleClicked.connect(self._slot_on_row_double_clicked)

        # Connect to the 'backend' components
        self.__backend_event_queue = None
        self.__sim_controller = None

        # When a user double clicks on the number of events on an IExecutable part, then the only events that are
        # shown in the Simulation Event Panel are the events specifically for the IExectuable part that was doubled
        # clicked on (in the events indicator area).
        # Originally when the events are loaded, the Simulation Event Panel displays all of the events from all
        # IExecutable part because the __filtered_part_session_id is None.  When a double-click event happens in
        # the events indicator area, this will set the self.__filtered_part_session_id to the IExecutable that was
        # double clicked on.
        self.__filtered_part_session_id = None

        self._monitor_scenario_replacement()

    def on_user_event_edit(self, event_info: EventInfo, new_time: float, new_priority: float, new_call_args_str: str):
        """
        Requests the backend Event Queue to change the requested values.
        Called by the EditEventDialog that allows user to enter their changes.
        :param event_info: an EventInfo object (named-tuple) containing the original event information
        :param new_time: a new value for (float) time
        :param new_priority: a new value for (float) priority
        :param new_call_args_str: a new value for (str) arguments
        """
        AsyncRequest.call(self.__backend_event_queue.edit_event, event_info, new_time, new_priority, new_call_args_str)

    def get_filtered_part_session_id(self) -> int:
        """
        Get the session id part that may be being used to filter the Simulation Events Queue Panel.
        :return: Tbe session id of the part.
        """
        return self.__filtered_part_session_id

    def on_filter_events_for_part(self, filter_part: BasePart):
        """
        Method called when the events in the Simulation Event Queue Panel are to be filtered on a given filter_part.
        :param filter_part: The part to filter the events on.
        """
        self._reload_event_queue(filter_part)
        self.ui.clear_filter_button.setEnabled(True)

    slot_on_filter_events_for_part = safe_slot(on_filter_events_for_part)

    def _reload_event_queue(self, filter_part: BasePart = None):
        """
        Reloads the event queue from the 'back-end'
        :param filter_part: A part that can be used to filter events on, ie only events belonging to the filter part
        will be shown in the Simulation Event Queue Panel.
        """

        def on_get_all_events(event_info_list: List[EventInfo]):

            self._waiting_for_queue_reload = False

            if not event_info_list:
                return

            self._add_all_events(event_info_list)
            self.ui.clear_queue_tool_button.setEnabled(True)
            self.sig_enable_event_queue.emit(True)

            if self._prev_row_selected is None:
                return

            row_count = self.ui.event_queue_table_widget.rowCount()

            if self._prev_row_selected > row_count - 1:
                return

            # Restore the previous selected row
            self.ui.event_queue_table_widget.selectRow(self._prev_row_selected)
            self.ui.edit_tool_button.setEnabled(True)
            self.ui.delete_tool_button.setEnabled(True)

        # If the user double-clicked on an event indicator to filter out events to a specific IExecutable part,
        # then self.__filtered_part_session_id is used to keep track of this so that new events or removal of
        # events that are not specific to the filtered part can be ignored.
        if filter_part is not None:
            self.__filtered_part_session_id = filter_part.SESSION_ID
        else:
            self.__filtered_part_session_id = None

        AsyncRequest.call(self.__backend_event_queue.get_all_as_list, filter_part, response_cb=on_get_all_events)
        self._waiting_for_queue_reload = True

    def _add_all_events(self, event_info_list: List[EventInfo]):
        """
        Adds all events to an empty Sim Event Queue, from soonest to latest.
        This method is used to initialize the queue or restore it after being disabled.
        :param event_info_list: list of EventInfo added, from soonest to latest
        """

        # If it is an empty Simulation Event Queue, then there should be nothing in the event_queue_table_widget.
        self._clear_panel_queue()

        for row, event_info in enumerate(event_info_list):
            time = event_info.time_days
            priority = event_info.priority
            call_info = event_info.call_info
            row_item = RowItem(time, priority, call_info)

            # Set the widgets to each table column in the row
            self.ui.event_queue_table_widget.insertRow(row)
            self.ui.event_queue_table_widget.setItem(row, 0, row_item.id_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 1, row_item.time_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 2, row_item.priority_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 3, row_item.part_name_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 4, row_item.part_type_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 5, row_item.part_args_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 6, row_item.path_table_widget)

            # Add the row info to the dictionary
            self._table_data[row_item.id] = row_item

        self.ui.event_queue_table_widget.resizeColumnsToContents()

    def _set_selected_row(self):
        """
        Sets the selected row attribute so that it can be restored during edit operations.
        """
        self._prev_row_selected = self.ui.event_queue_table_widget.currentRow()

    def _on_item_selected_changed(self):
        """
        Enable edit and delete once a row is selected
        """
        self._set_selected_row()
        self.ui.edit_tool_button.setEnabled(True)
        self.ui.delete_tool_button.setEnabled(True)

    # noinspection PyUnusedLocal
    def _on_row_double_clicked(self, widget_item: QTableWidgetItem):
        """
        Launches the edit dialogue when an item in a row is double-clicked.
        :param widget_item: the cell in the row that was double-clicked (not used)
        """
        self._on_user_event_edit_dialog()

    def _on_user_event_edit_dialog(self):
        """
        Open edit dialogue to change parameter values, time, or priority
        """
        self._set_selected_row()
        self._user_edit_event = True
        row_selected = self.ui.event_queue_table_widget.currentRow()
        id_table_widget = self.ui.event_queue_table_widget.item(row_selected, 0)
        event_id = int(id_table_widget.text())
        row_item = self._table_data[event_id]

        event_edit_dialog = EditEventDialog(row_item, self)
        answer = event_edit_dialog.exec()
        if answer:
            event_info, new_time, new_priority, new_call_args_str = event_edit_dialog.get_user_input()
            self.on_user_event_edit(event_info, new_time, new_priority, new_call_args_str)

        self.ui.event_queue_table_widget.resizeColumnsToContents()

    # noinspection PyUnusedLocal
    def _on_user_delete_event(self, checked: bool = False):
        """
        Deletes the event item selected (if any) in the Event Queue.
        """

        # Get the RowItem associated with the selected cell
        self._set_selected_row()
        row_selected = self.ui.event_queue_table_widget.currentRow()
        id_table_widget = self.ui.event_queue_table_widget.item(row_selected, 0)
        event_id = int(id_table_widget.text())
        row_item = self._table_data[event_id]
        self._prev_row_selected = None

        # Request 'back-end' to delete the event
        orig_inputs = row_item.get_event_inputs()
        days = orig_inputs[0]
        priority = orig_inputs[1]
        call_info = orig_inputs[2]
        AsyncRequest.call(self.__backend_event_queue.remove_event, days, priority, call_info)

    # noinspection PyUnusedLocal
    def _on_user_clear_queue(self, _: bool = False):
        """
        Emits the signal to trigger the MainSimBridge to signal the back-end to clear the Event Queue.
        :param _: unused boolean parameter.
        """
        self.sig_clear_event_queue.emit()

    def _on_backend_events_added(self, predecessor_id: int, event_info: EventInfo):
        """
        Adds new events to the UI Event Queue
        The input provides the events as a list of dictionaries, where each dict defines the preceding event ID
        used to determine where to insert the new event, and the new EventInfo. Events are listed from soonest to
        latest.
        :param event_info: data about the sim event add
        """
        if not self.ui.clear_queue_tool_button.isEnabled():
            self.ui.clear_queue_tool_button.setEnabled(True)
            self.sig_enable_event_queue.emit(True)

        # If front-end queue has been cleared during animation-mode change,
        # wait for back-end to refresh the entire queue before adding new events
        if self._waiting_for_queue_reload:
            return

        if self.__filtered_part_session_id is not None:
            if event_info.call_info.iexec.SESSION_ID == self.__filtered_part_session_id:
                self.__process_add_new_event(predecessor_id, event_info)
        else:
            self.__process_add_new_event(predecessor_id, event_info)

    def _on_backend_event_removed(self, event_id: int):
        """
        Removes a list of events from the UI Event Queue
        :param event_id: ID of the event removed
        """

        # If front-end queue has been cleared during animation-mode change,
        # wait for back-end to refresh the entire queue before deleting events
        if self._waiting_for_queue_reload:
            return

        # Check if event has already been removed
        if event_id not in self._table_data:
            return

        row_item_to_remove = self._table_data[event_id]

        if self.__filtered_part_session_id is not None:
            if row_item_to_remove.exec_part.SESSION_ID == self.__filtered_part_session_id:
                self.__remove_event(row_item_to_remove, event_id)
        else:
            self.__remove_event(row_item_to_remove, event_id)

        # Disable if all events are removed
        if self.ui.event_queue_table_widget.rowCount() == 0:
            self.ui.edit_tool_button.setEnabled(False)
            self.ui.delete_tool_button.setEnabled(False)
            self.ui.clear_queue_tool_button.setEnabled(False)
            self.sig_enable_event_queue.emit(False)

    def _on_backend_event_args_changed(self, call_info: CallInfo):
        """
        Changes the arguments of an event.
        :param call_info: The CallInfo of the changed event.
        """

        # If front-end queue has been cleared during animation-mode change,
        # wait for back-end to refresh the entire queue before changing event arguments
        if self._waiting_for_queue_reload:
            return

        # Check if event has already been removed
        event_id = call_info.unique_id
        if event_id not in self._table_data:
            return

        row_item = self._table_data[event_id]

        if self.__filtered_part_session_id is not None:
            if row_item.exec_part.SESSION_ID == self.__filtered_part_session_id:
                row_item.part_args = call_info.get_args_as_string()
        else:
            row_item.part_args = call_info.get_args_as_string()

    def _disconnect_all_part_signals(self):
        """
        Disconnects all panel signals and deletes table data, optionally.
        """
        for row_item in self._table_data.values():
            row_item.disconnect_part_signal()

    def _clear_panel_queue(self):
        """
        Clears all events from the panel
        """
        self._table_data = dict()
        self.ui.event_queue_table_widget.clearContents()
        self.ui.event_queue_table_widget.setRowCount(0)
        self.ui.edit_tool_button.setEnabled(False)
        self.ui.delete_tool_button.setEnabled(False)
        self.ui.clear_queue_tool_button.setEnabled(False)
        self.sig_enable_event_queue.emit(False)

    def _on_backend_queue_cleared(self):
        """
        Clears the queue of all events when signalled from the back-end.
        """
        self._disconnect_all_part_signals()
        self._clear_panel_queue()

    def _on_backend_time_stamps_changed(self, num_days_shifted: float):
        """
        Updates the time stamps for all events when the times have shifted by num_days_shifted
        :param num_days_shifted: the time-shift in number of days for all events
        """
        for row_item in self._table_data.values():
            current_days, _, _ = row_item.get_event_inputs()
            new_time = num_days_shifted + current_days
            row_item.time = new_time

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        """
        Removes previous event queue and loads the new one.
        :param scenario: a new scenario
        """

        # Disconnect from parts and previous scenario Event Queue
        self._disconnect_all_part_signals()
        if self.__backend_event_queue is not None:
            event_queue_signals = self.__backend_event_queue.signals
            event_queue_signals.sig_event_added.disconnect(self._slot_on_backend_events_added)
            event_queue_signals.sig_event_removed.disconnect(self._slot_on_backend_event_removed)
            event_queue_signals.sig_queue_cleared.disconnect(self._slot_on_backend_queue_cleared)
            event_queue_signals.sig_time_stamps_changed.disconnect(self._slot_on_backend_time_stamps_changed)

        if self.__sim_controller is not None:
            self.__sim_controller.signals.sig_state_changed.disconnect(self._slot_on_sim_state_changed)

        # Get the new Event Queue and re-initialize
        self.__backend_event_queue = scenario.get_event_queue()
        event_queue_signals = self.__backend_event_queue.signals
        event_queue_signals.sig_event_added.connect(self._slot_on_backend_events_added)
        event_queue_signals.sig_event_removed.connect(self._slot_on_backend_event_removed)
        event_queue_signals.sig_args_changed.connect(self._slot_on_backend_event_args_changed)
        event_queue_signals.sig_queue_cleared.connect(self._slot_on_backend_queue_cleared)
        event_queue_signals.sig_time_stamps_changed.connect(self._slot_on_backend_time_stamps_changed)

        self.__sim_controller = scenario.sim_controller
        self.__sim_controller.signals.sig_state_changed.connect(self._slot_on_sim_state_changed)

        # Sets up the animation monitor and loads events
        self.monitor_animation_changes(scenario.sim_controller)
        self._on_animation_mode_enabled()

    @override(IHasAnimationMode)
    def _on_animation_mode_enabled(self):
        """
        When animation is re-enabled, refreshes the Sim Event Queue Panel and enables it.
        """
        self.setEnabled(True)
        self._clear_panel_queue()
        self._reload_event_queue()

    @override(IHasAnimationMode)
    def _on_animation_mode_disabled(self):
        """
        Disables the Sim Event Queue Panel from responding to back-end signals
        """
        self.setEnabled(False)

    def _on_sim_state_changed(self, state: MainSimStatesEnum):
        """
        Method called when the state of the Simulation Engine changes
        """
        if state == MainSimStatesEnum.debugging:
            self.ui.clear_queue_tool_button.setEnabled(False)
            self.sig_enable_event_queue.emit(False)

    _slot_on_item_selected_changed = safe_slot(_on_item_selected_changed)
    _slot_on_row_double_clicked = safe_slot(_on_row_double_clicked)
    _slot_on_user_event_edit_dialog = safe_slot(_on_user_event_edit_dialog)
    _slot_on_user_delete_event = safe_slot(_on_user_delete_event)
    _slot_on_user_clear_queue = safe_slot(_on_user_clear_queue)
    _slot_on_backend_events_added = ext_safe_slot(_on_backend_events_added)
    _slot_on_backend_event_removed = safe_slot(_on_backend_event_removed)
    _slot_on_backend_event_args_changed = ext_safe_slot(_on_backend_event_args_changed)
    _slot_on_backend_queue_cleared = safe_slot(_on_backend_queue_cleared)
    _slot_on_backend_time_stamps_changed = safe_slot(_on_backend_time_stamps_changed)
    _slot_on_animation_mode_enabled = safe_slot(_on_animation_mode_enabled)
    _slot_on_animation_mode_disabled = safe_slot(_on_animation_mode_disabled)
    _slot_on_sim_state_changed = safe_slot(_on_sim_state_changed)

    def __remove_event(self, row_item_to_remove: RowItem, event_id: int):
        """
        Convenience method to remove a row from the Event Queue Panel.
        :param row_item_to_remove: The RowItem instance of the row to remove.
        :param event_id: The id of the event for cleaning up the self._table_data
        """
        # Remove row from queue and disconnect signals, then delete table data
        row_to_remove = self.ui.event_queue_table_widget.row(row_item_to_remove.id_table_widget)
        self.ui.event_queue_table_widget.removeRow(row_to_remove)
        row_item_to_remove.disconnect_part_signal()
        del self._table_data[event_id]

    def __insert_event(self, pred_id: int) -> int:
        """
        Convenience method to insert a new event row into the Event Queue Panel.
        :param pred_id:  The id of the predecessor.
        :return The row offset in the table where a new item is to be inserted.
        """
        if pred_id is None:
            return 0

        ins_row_item = self._table_data[pred_id]
        ins_row = self.ui.event_queue_table_widget.row(ins_row_item.id_table_widget)
        row = ins_row + 1

        return row

    def __process_add_new_event(self, predecessor_id: int, event_info: EventInfo):
        """
        Helper method used to add events to the Gui table widget.
        :param event_info_dict: A dictionary containing the predecessor_id of this event info and the event info itself.
        """
        call_info = event_info.call_info
        event_id = call_info.unique_id

        # Check if the event is already in the queue
        if event_id in self._table_data:
            return

        time = event_info.time_days
        priority = event_info.priority

        row_item = RowItem(time, priority, call_info)

        def add_new_event(row: int):

            # Set the widgets to each table column in the row
            self.ui.event_queue_table_widget.insertRow(row)
            self.ui.event_queue_table_widget.setItem(row, 0, row_item.id_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 1, row_item.time_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 2, row_item.priority_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 3, row_item.part_name_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 4, row_item.part_type_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 5, row_item.part_args_table_widget)
            self.ui.event_queue_table_widget.setItem(row, 6, row_item.path_table_widget)

            # Add the row info to the dictionary
            self._table_data[row_item.id] = row_item

            self.ui.event_queue_table_widget.resizeColumnsToContents()

            # If the added event resulted from editing an existing event, auto-scroll to and select it
            if self._user_edit_event:

                self.ui.event_queue_table_widget.selectRow(row)
                self._prev_row_selected = self.ui.event_queue_table_widget.currentRow()
                self._user_edit_event = False

            # Restore the previous selected row if it exists
            elif self._prev_row_selected is not None:
                row_count = self.ui.event_queue_table_widget.rowCount()
                if self._prev_row_selected <= row_count - 1:
                    self.ui.event_queue_table_widget.selectRow(self._prev_row_selected)

        def on_receive_predecessor_id(id: int):
            row = self.__insert_event(id)
            add_new_event(row)

        # Insert the new event after the event associated with the insertion ID
        if predecessor_id is not None:
            if predecessor_id in self._table_data:
                row = self.__insert_event(predecessor_id)
            else:
                assert self.__filtered_part_session_id is not None
                AsyncRequest.call(self.__backend_event_queue.get_predecessor_id,
                                  event_info,
                                  same_iexec=True,
                                  response_cb=on_receive_predecessor_id)
                return
        else:
            row = 0

        add_new_event(row)

    def __on_user_cleared_filter(self):
        """
        Method used to clear the session id of the part that has been filtered on.
        """
        self.__filtered_part_session_id = None
        self._reload_event_queue()
        self.ui.clear_filter_button.setEnabled(False)

    __slot_on_user_cleared_filter = safe_slot(__on_user_cleared_filter)
