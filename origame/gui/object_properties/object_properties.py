# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Object Properties Docked Dialog

This module implements the classes and methods used by the dockable Object Properties Panel.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget, QMessageBox, QDialog

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario.defn_parts import BasePart, LinkWaypoint, PartLink
from ...scenario.defn_parts import Position, part_types_info, ScenarioObjectType

from ..undo_manager import scene_undo_stack, RenamePartCommand
from ..undo_manager import PartsPositionsCommand, SetPartPropertyCommand
from ..undo_manager import WaypointPositionCommand, ChangeIfxLevelCommand, DeclutterLinkCommand
from ..actions_utils import verify_ifx_level_change_ok, get_labels_ifx_levels
from ..async_methods import AsyncRequest
from ..gui_utils import part_image, exec_modal_dialog, get_scenario_font, get_icon_path
from ..safe_slot import safe_slot, ext_safe_slot
from ..link_renamer import LinkRenameManager

from .Ui_object_properties import Ui_ObjectPropertiesEditor

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'ObjectPropertiesPanel',
    'PartNameLineEdit',
]

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ObjectPropertiesPanel(QWidget):
    """
    Provides a panel to display and change the properties of scenario objects when individually selected. The following
    objects are supported:
    - parts
    - links
    - waypoints
    """

    # --------------------------- class-wide data and signals -----------------------------------

    PROPERTY_ICON_WIDTH = 50
    PROPERTY_ICON_HEIGHT = 50

    SelectableSet = Either[List[BasePart], List[LinkWaypoint], List[PartLink]]

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    # noinspection PyUnresolvedReferences
    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.ui = Ui_ObjectPropertiesEditor()
        self.ui.setupUi(self)

        self.ui.id_line_edit.setFont(get_scenario_font())
        self.ui.ifx_level_combobox.setFont(get_scenario_font())

        # Only show part object by default
        self.ui.waypoint_group_box.hide()
        self.ui.link_group_box.hide()
        self.ui.rename_link_button.hide()

        self.__selected_object = None

        # Connect part signals for user 'edit' actions
        self.ui.id_line_edit.sig_editing_finished.connect(self.__slot_on_object_name_edit_gui)
        self.ui.ifx_level_combobox.activated.connect(self.__slot_on_ifx_level_edit_gui)
        self.ui.x_part_pos_doublespinbox.editingFinished.connect(self.__slot_on_part_position_edit_gui)
        self.ui.y_part_pos_doublespinbox.editingFinished.connect(self.__slot_on_part_position_edit_gui)
        self.ui.comment_text_edit.sig_editing_finished.connect(self.__slot_on_part_comment_edit_gui)

        # Connect waypoint signals for user 'edit' actions
        self.ui.x_waypoint_pos_doublespinbox.editingFinished.connect(self.__slot_on_waypoint_position_edit_gui)
        self.ui.y_waypoint_pos_doublespinbox.editingFinished.connect(self.__slot_on_waypoint_position_edit_gui)

        # Connect link signals for user 'edit' actions
        self.ui.declutter_checkbox.clicked.connect(self.__slot_on_link_declutter_changed_gui)

        # Rename link
        self.ui.rename_link_button.clicked.connect(self.__slot_on_rename_link)

        self.__old_name = None
        self.__old_ifx_level = None
        self.__old_x = None
        self.__old_y = None
        self.__old_comment = None
        self.__old_declutter = None
        self.__old_source_type = None
        self.__old_target_type = None
        self.__old_num_waypoints = None

    def on_object_selection_changed(self, selected_objects: SelectableSet):
        """
        When the selected object changes, the properties panel updates the displayed property info.
        If nothing is selected (empty list) or more than one item selected, the panel displays
        no information and is disabled.
        :param selected_objects: a list of selected objects.
        """

        # Disable panel when click on blank canvas (no selection) or multiple selected parts
        if len(selected_objects) != 1:
            self.__disconnect_from_backend_object()
            self.__on_no_object_selected()
            return

        # This method should only be triggered if selection changed
        if self.__selected_object is selected_objects[0]:
            # No selection change - nothing to do
            return

        # Get the new selected object
        object_selected = selected_objects[0]
        self.setEnabled(True)

        if object_selected.SCENARIO_OBJECT_TYPE == ScenarioObjectType.part:
            # Process part properties
            self.ui.part_group_box.show()
            self.ui.waypoint_group_box.hide()
            self.ui.link_group_box.hide()
            self.ui.rename_link_button.hide()
            self.ui.id_line_edit.setReadOnly(False)

            # Update the panel properties
            self.__disconnect_from_backend_object()
            self.__connect_to_backend_object(object_selected)
            self.__display_part_properties(object_selected)

        elif object_selected.SCENARIO_OBJECT_TYPE == ScenarioObjectType.waypoint:
            # Process waypoint properties
            self.ui.part_group_box.hide()
            self.ui.waypoint_group_box.show()
            self.ui.link_group_box.hide()
            self.ui.rename_link_button.hide()
            self.ui.id_line_edit.setReadOnly(True)

            # Update the panel properties
            self.__disconnect_from_backend_object()
            self.__connect_to_backend_object(object_selected)
            self.__display_waypoint_properties(object_selected)

        elif object_selected.SCENARIO_OBJECT_TYPE == ScenarioObjectType.link:
            # Process waypoint properties
            self.ui.part_group_box.hide()
            self.ui.waypoint_group_box.hide()
            self.ui.link_group_box.show()
            self.ui.rename_link_button.show()
            self.ui.id_line_edit.setReadOnly(True)

            # Update the panel properties
            self.__disconnect_from_backend_object()
            self.__connect_to_backend_object(object_selected)
            self.__display_link_properties(object_selected)

        else:
            # Object properties are not displayed
            self.__disconnect_from_backend_object()

    def get_selected_object(self) -> Either[object, None]:
        """
        Returns the currently selected object
        """
        return self.__selected_object

    slot_on_object_selection_changed = safe_slot(on_object_selection_changed, arg_types=[list])

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __disconnect_from_backend_object(self):
        """
        Disconnects from the previously connected object.
        """
        if self.__selected_object is None:
            return

        object_type = self.__selected_object.SCENARIO_OBJECT_TYPE

        if object_type == ScenarioObjectType.part:
            # Remove connections from deselected part
            frame_sig = self.__selected_object.part_frame.signals
            frame_sig.sig_name_changed.disconnect(self.__slot_on_object_name_changed_backend)
            frame_sig.sig_ifx_level_changed.disconnect(self.__slot_on_ifx_level_changed_backend)
            frame_sig.sig_position_changed.disconnect(self.__slot_on_part_position_changed_backend)
            frame_sig.sig_comment_changed.disconnect(self.__slot_on_part_comment_changed_backend)
            self.__selected_object.base_part_signals.sig_parent_path_change.disconnect(self.__slot_on_part_path_change)

        elif object_type == ScenarioObjectType.waypoint:
            waypoint_sig = self.__selected_object.signals
            waypoint_sig.sig_position_changed.disconnect(self.__slot_on_waypoint_position_changed_backend)

        elif object_type == ScenarioObjectType.link:
            link_sig = self.__selected_object.signals
            link_sig.sig_name_changed.disconnect(self.__slot_on_object_name_changed_backend)
            link_sig.sig_link_decluttering_changed.disconnect(self.__slot_on_link_declutter_changed_backend)
            link_sig.sig_waypoint_added.disconnect(self.__slot_on_link_waypoint_added_backend)
            link_sig.sig_waypoint_removed.disconnect(self.__slot_on_link_waypoint_removed_backend)
            link_sig.sig_target_changed.disconnect(self.__slot_on_link_target_changed_backend)
        else:
            pass  # Object type not supported to display properties

        self.__selected_object = None

    def __connect_to_backend_object(self, object_selected: BasePart or LinkWaypoint or PartLink):
        """
        Makes the connections to the selected object in the 'backend' thread.
        :param object_selected: the currently selected part (in the 2D View or Actor Hierarchy)
        """
        object_type = object_selected.SCENARIO_OBJECT_TYPE
        assert object_type in (ScenarioObjectType.part, ScenarioObjectType.waypoint, ScenarioObjectType.link)

        # Set for next part selection
        self.__selected_object = object_selected

        # Make connections to selected part
        if object_type == ScenarioObjectType.part:
            frame_sig = object_selected.part_frame.signals
            frame_sig.sig_name_changed.connect(self.__slot_on_object_name_changed_backend)
            frame_sig.sig_ifx_level_changed.connect(self.__slot_on_ifx_level_changed_backend)
            frame_sig.sig_position_changed.connect(self.__slot_on_part_position_changed_backend)
            frame_sig.sig_comment_changed.connect(self.__slot_on_part_comment_changed_backend)
            object_selected.base_part_signals.sig_parent_path_change.connect(self.__slot_on_part_path_change)

        elif object_type == ScenarioObjectType.waypoint:
            waypoint_sig = self.__selected_object.signals
            waypoint_sig.sig_position_changed.connect(self.__slot_on_waypoint_position_changed_backend)

        elif object_type == ScenarioObjectType.link:
            link_sig = self.__selected_object.signals
            link_sig.sig_name_changed.connect(self.__slot_on_object_name_changed_backend)
            link_sig.sig_link_decluttering_changed.connect(self.__slot_on_link_declutter_changed_backend)
            link_sig.sig_waypoint_added.connect(self.__slot_on_link_waypoint_added_backend)
            link_sig.sig_waypoint_removed.connect(self.__slot_on_link_waypoint_removed_backend)
            link_sig.sig_target_changed.connect(self.__slot_on_link_target_changed_backend)

        else:
            # No properties to display for the selected object
            pass

    def __display_part_properties(self, part_selected: BasePart):
        """
        Displays the part property values in the Properties Panel.
        :param part_selected: the selected part in the 2D View.
        """

        ui = self.ui
        part_type = part_types_info.get_type_name(part_selected)

        def async_get_properties() -> Tuple[str, int, List[Tuple[int, str]], float, float, str]:
            # Access part frame properties
            part_frame = part_selected.part_frame

            part_name = part_frame.name
            ifx_level = part_frame.ifx_level
            ifx_levels_labels = get_labels_ifx_levels(part_selected)
            part_pos_x = part_frame.pos_x
            part_pos_y = part_frame.pos_y
            part_comments = part_frame.comment

            return part_name, ifx_level, ifx_levels_labels, part_pos_x, part_pos_y, part_comments

        def display_props(part_name: str,
                          ifx_level: int, ifx_levels_labels: List[Tuple[int, str]],
                          part_pos_x: float, part_pos_y: float,
                          part_comments: str):
            # Display in the panel
            ui.id_line_edit.setText(part_name)
            ui.x_part_pos_doublespinbox.setValue(part_pos_x)
            ui.y_part_pos_doublespinbox.setValue(part_pos_y)

            # Interface levels hierarchy
            self.__update_ifx_combobox(ifx_levels_labels, part_selected)

            # Reset old values to new values to compare on next update
            self.__old_name = part_name
            self.__old_ifx_level = ifx_level
            self.__old_x = part_pos_x
            self.__old_y = part_pos_y

            # Populate the comment box
            ui.comment_text_edit.setEnabled(True)
            ui.comment_text_edit.setPlainText(part_comments)
            self.__old_comment = part_comments

            # Display object properties from the back-end thread to ensure the
            # most recent properties are displayed.

        AsyncRequest.call(async_get_properties, response_cb=display_props)

        # Set the type and icon
        self.__display_icon(part_type)
        self.ui.type_display.setText(part_type)

    def __display_waypoint_properties(self, waypoint_selected: LinkWaypoint):
        """
        Displays the waypoint property values in the Properties Panel.
        :param waypoint_selected: the selected waypoint in the 2D View.
        """

        ui = self.ui
        part_type = 'waypoint'

        def async_get_properties() -> Tuple[int, float, float]:
            # Access waypoint properties
            id = waypoint_selected.wp_id
            pos_x, pos_y = waypoint_selected.position
            return (id, pos_x, pos_y)

        def display_props(id: int, pos_x: float, pos_y: float):
            # Display in the panel
            ui.id_line_edit.setText(str(id))
            ui.x_waypoint_pos_doublespinbox.setValue(pos_x)
            ui.y_waypoint_pos_doublespinbox.setValue(pos_y)

            self.__old_name = str(id)
            # self.__old_ifx_level = ui.ifx_level_combobox.currentIndex()
            self.__old_x = pos_x
            self.__old_y = pos_y

        # Display object properties from the back-end thread to ensure the
        # most recent properties are displayed.
        AsyncRequest.call(async_get_properties, response_cb=display_props)

        # Set the type and icon
        self.__display_icon(part_type)
        self.ui.type_display.setText(part_type)

    def __display_link_properties(self, link_selected: PartLink):
        """
        Displays the link property values in the Properties Panel.
        :param link_selected: the selected link in the 2D View.
        """

        ui = self.ui
        part_type = 'link'

        def async_get_properties() -> Tuple[str, bool, str, str, int]:
            # Access link properties
            name = link_selected.name
            declutter = link_selected.declutter
            source_type = link_selected.source_part_frame.part.PART_TYPE_NAME
            target_type = link_selected.target_part_frame.part.PART_TYPE_NAME
            num_waypoints = len(link_selected.waypoints)

            return name, declutter, source_type, target_type, num_waypoints

        def display_props(name: str, declutter: bool, source_type: str, target_type: str, num_waypoints: int):
            # Display in the panel
            ui.id_line_edit.setText(name)
            ui.declutter_checkbox.setChecked(declutter)
            ui.source_type_line_edit.setText(source_type)
            ui.target_type_line_edit.setText(target_type)
            ui.waypoint_number_spinbox.setValue(num_waypoints)

            self.__old_name = name
            self.__old_declutter = declutter
            self.__old_source_type = source_type
            self.__old_target_type = target_type
            self.__old_num_waypoints = num_waypoints

        # Display object properties from the back-end thread to ensure the
        # most recent properties are displayed.
        AsyncRequest.call(async_get_properties, response_cb=display_props)

        # Set the type and icon
        self.__display_icon(part_type)
        self.ui.type_display.setText(part_type)

    def __display_icon(self, object_type: str):
        """
        Displays the icon in the Properties Panel based on object type
        :param object_type: The type of object selected
        """
        self.ui.icon_display.load(str(part_image(object_type)))
        self.ui.icon_display.setFixedSize(int(ObjectPropertiesPanel.PROPERTY_ICON_WIDTH),
                                          int(ObjectPropertiesPanel.PROPERTY_ICON_HEIGHT))

    def __on_no_object_selected(self):
        """
        Removes all object information and disables the panel
        """

        # Show the part tab
        self.ui.part_group_box.show()
        self.ui.waypoint_group_box.hide()
        self.ui.link_group_box.hide()
        self.ui.rename_link_button.hide()

        self.__selected_object = None
        self.ui.icon_display.load(get_icon_path("blank.svg"))
        self.ui.icon_display.setFixedSize(int(ObjectPropertiesPanel.PROPERTY_ICON_WIDTH),
                                          int(ObjectPropertiesPanel.PROPERTY_ICON_HEIGHT))

        self.__old_name = None
        self.ui.id_line_edit.clear()
        self.ui.id_line_edit.setReadOnly(True)
        self.ui.type_display.clear()

        self.__old_ifx_level = None
        self.ui.ifx_level_combobox.clear()

        self.__old_x = 0.00
        self.__old_y = 0.00
        self.ui.x_part_pos_doublespinbox.setValue(self.__old_x)
        self.ui.y_part_pos_doublespinbox.setValue(self.__old_y)
        self.__old_comment = None
        self.ui.comment_text_edit.clear()
        self.setEnabled(False)

    def __on_object_name_edit_gui(self):
        """
        Requests a name change for the object running on the 'backend' thread.
        """

        new_name = self.ui.id_line_edit.text()

        if not new_name:
            msg = "Name '{}' can't be empty. Click OK to close and edit name.".format(new_name)
            exec_modal_dialog("Name Error", msg, QMessageBox.Critical, default_button=QMessageBox.Ok)
            return

        if new_name.isspace():
            msg = "Name '{}' can't be empty spaces. Click OK to close and edit name.".format(new_name)
            exec_modal_dialog("Name Error", msg, QMessageBox.Critical, default_button=QMessageBox.Ok)
            return

        if self.__old_name == new_name:
            return

        cmd = RenamePartCommand(self.__selected_object, new_name)

        self.__old_name = new_name

        scene_undo_stack().push(cmd)

    def __on_ifx_level_edit_gui(self, combo_index: int):
        """
        Requests the back-end part update it's current interface level.
        :param combo_index: The index highlighted in the panel's combo box.
        """

        # Convert the index highlighted in combo box to ifx level
        # The ifx level is the reverse order from the index in the list (minus 1 due to 0 index)
        ifx_level_selected = self.__ifx_level_converter(combo_index)
        if self.__old_ifx_level == ifx_level_selected:
            return

        if self.__selected_object is None:
            return

        part = self.__selected_object
        if verify_ifx_level_change_ok(part, ifx_level_selected):
            scene_undo_stack().push(ChangeIfxLevelCommand(part, ifx_level_selected))

    def __on_part_position_edit_gui(self):
        """
        Requests a position change for the part running on the 'backend' thread.
        """
        old_pos = Position(self.__old_x, self.__old_y)
        new_pos = Position(self.ui.x_part_pos_doublespinbox.value(),
                           self.ui.y_part_pos_doublespinbox.value())

        # use 'round' since backend can have higher precision
        # than value displayed in properties panel
        if round(old_pos, 2) == new_pos:
            return

        part = self.__selected_object
        scene_undo_stack().push(PartsPositionsCommand([part], [old_pos], [new_pos]))
        self.__old_x = self.ui.x_part_pos_doublespinbox.value()
        self.__old_y = self.ui.y_part_pos_doublespinbox.value()

    def __on_part_comment_edit_gui(self):
        """
        Requests a comment update for the part running on the 'backend' thread.
        """
        new_comment = self.ui.comment_text_edit.toPlainText().strip()

        if self.__old_comment.strip() == new_comment:
            return

        self.__old_comment = new_comment
        part = self.__selected_object
        cmd = SetPartPropertyCommand(part, 'comment', new_comment)
        scene_undo_stack().push(cmd)

    def __on_waypoint_position_edit_gui(self):
        """
        Requests a position change for the waypoint running on the 'backend' thread.
        """
        old_pos = Position(self.__old_x, self.__old_y)
        new_pos = Position(self.ui.x_waypoint_pos_doublespinbox.value(),
                           self.ui.y_waypoint_pos_doublespinbox.value())

        # use 'round' since backend can have higher precision
        # than value displayed in properties panel
        if round(old_pos, 2) == new_pos:
            return

        waypoint = self.__selected_object
        scene_undo_stack().push(WaypointPositionCommand([waypoint], [old_pos], [new_pos]))
        self.__old_x = self.ui.x_waypoint_pos_doublespinbox.value()
        self.__old_y = self.ui.y_waypoint_pos_doublespinbox.value()

    def __on_link_declutter_changed_gui(self, checked: bool):
        """
        Requests the back-end link to update it's declutter flag.
        :param checked: The checked status of the declutter check box. True or False.
        """
        if self.__old_declutter == checked:
            return

        self.__old_declutter = checked
        link = self.__selected_object
        cmd = DeclutterLinkCommand(link, checked)
        scene_undo_stack().push(cmd)

    def __on_object_name_changed_backend(self, name: str):
        """
        Updates the name in the Property Panel when signalled by the object in the 'back-end' thread.
        :param name: the object name
        """

        if self.isEnabled():
            self.ui.id_line_edit.setText(name)
            self.__old_name = self.ui.id_line_edit.text()
            self.__update_ifx_levels_display()

    def __ifx_level_converter(self, from_value: int) -> int:
        """
        Converts from interface level to combo box index and vice versa.

        The combo box drop down displays the interface levels with the highest level at the root listed first.
        This corresponds to the combo box's zeroth index. Therefore, the selected interface level can be computed
        directly from the selected index by reversing it based on the number of entries the combo box is currently
        displaying.  E.g. when an entry in the combo box is selected, the index of the listed item is sent to the slot
        via the 'activated' Qt signal. So for the root entry (top of the list and highest interface level), the zeroth
        index is sent. To get the selected level, the count of current displayed items minus index minus 1 (to convert
        to zero-based indeces) is computed. This also works if the inverse is required (going from interface level to
        combo box index).
        """
        return self.ui.ifx_level_combobox.count() - from_value - 1

    def __on_ifx_level_changed_backend(self, new_ifx_level: int):
        """
        Updates the interface level when signalled by the back-end part.
        :param ifx_level: The new interface level of the displayed part.
        """

        if self.isEnabled():
            self.__update_ifx_levels_display()
            self.__old_ifx_level = self.__ifx_level_converter(self.ui.ifx_level_combobox.currentIndex())

    def __update_ifx_combobox(self, ifx_levels_labels: List[Tuple[int, str]], part_selected: BasePart):
        if part_selected is not None:
            part_frame = part_selected.part_frame
            current_level = part_frame.ifx_level
            ifx_level_combobox = self.ui.ifx_level_combobox
            ifx_level_combobox.clear()
            for ifx_level, item_text in ifx_levels_labels:
                ifx_level_combobox.addItem(item_text, userData=ifx_level)
            combo_idx = self.__ifx_level_converter(current_level)
            ifx_level_combobox.setCurrentIndex(combo_idx)
            self.__old_ifx_level = current_level

    def __update_ifx_levels_display(self):
        """
        Update the ifx levels combo box.
        """

        if self.__selected_object is None:
            return

        if self.__selected_object.SCENARIO_OBJECT_TYPE != ScenarioObjectType.part:
            return

        part_selected = self.__selected_object

        def update_ifx(ifx_levels_labels: List[Tuple[int, str]]):
            self.__update_ifx_combobox(ifx_levels_labels, part_selected)

        AsyncRequest.call(get_labels_ifx_levels, self.__selected_object, response_cb=update_ifx)

    def __on_part_position_changed_backend(self, x: float, y: float):
        """
        Updates the part's position values displayed in the panel when signalled by the 'back-end' part.
        :param x: The new x position coordinate.
        :param y: The new y position coordinate.
        """

        if self.isEnabled():
            self.ui.x_part_pos_doublespinbox.setValue(x)
            self.ui.y_part_pos_doublespinbox.setValue(y)
            self.__old_x = self.ui.x_part_pos_doublespinbox.value()
            self.__old_y = self.ui.y_part_pos_doublespinbox.value()

    def __on_part_comment_changed_backend(self, comment: str):
        """
        Updates the part comment string in the Property Panel when signalled by the part in the 'back-end' thread.
        :param comment: a string object containing the comment
        """
        if self.isEnabled():
            self.ui.comment_text_edit.setPlainText(comment)
            self.__old_comment = comment

    def __on_waypoint_position_changed_backend(self, x: float, y: float):
        """
        Updates the waypoint's position values displayed in the panel when signalled by the 'back-end' part.
        :param x: The new x position coordinate.
        :param y: The new y position coordinate.
        """

        if self.isEnabled():
            self.ui.x_waypoint_pos_doublespinbox.setValue(x)
            self.ui.y_waypoint_pos_doublespinbox.setValue(y)
            self.__old_x = self.ui.x_waypoint_pos_doublespinbox.value()
            self.__old_y = self.ui.y_waypoint_pos_doublespinbox.value()

    def __on_link_declutter_changed_backend(self, declutter: bool):
        """
        Updates the declutter checkbox to correspond with back-end link.
        :param declutter: Checks the box when declutter is True, and unchecks it otherwise.
        """
        if self.isEnabled():
            self.ui.declutter_checkbox.setChecked(declutter)
            self.__old_declutter = self.ui.declutter_checkbox.isChecked()

    def __on_link_waypoint_added_backend(self, _: int):
        """
        Increments the number of waypoints to correspond with the back-end link.
        The given waypoint index is not used.
        """

        # Must check if the selected part is a waypoint since selection changes from link to waypoint when waypoint added
        if self.isEnabled() and self.__selected_object.SCENARIO_OBJECT_TYPE != ScenarioObjectType.waypoint:
            self.ui.waypoint_number_spinbox.setValue(len(self.__selected_object.waypoints))
            self.__old_num_waypoints = self.ui.waypoint_number_spinbox.value()

    def __on_link_waypoint_removed_backend(self, _: int):
        """
        Decrements the number of waypoints to correspond with the back-end link.
        The given waypoint index is not used.
        """
        if self.isEnabled():
            self.ui.waypoint_number_spinbox.setValue(len(self.__selected_object.waypoints))
            self.__old_num_waypoints = self.ui.waypoint_number_spinbox.value()

    def __on_link_target_changed_backend(self):
        """
        Updates the target link anchor type to correspond with the back-end link.
        """
        if self.isEnabled():
            object_type = self.__selected_object.SCENARIO_OBJECT_TYPE
            assert object_type in (ScenarioObjectType.part, ScenarioObjectType.link)

            # Selected object may be a part (clicked during link retarget) or a link (undo-command)
            if object_type == ScenarioObjectType.part:
                self.ui.target_type_line_edit.setText(self.__selected_object.PART_TYPE_NAME)
            else:
                link_target_part_frame = self.__selected_object.target_part_frame
                self.ui.target_type_line_edit.setText(link_target_part_frame.part.PART_TYPE_NAME)

            self.__old_target_type = self.ui.target_type_line_edit.text()

    def __on_ifx_item_path_changed(self):
        """When backend signals that part path has changed, notify interface list items"""
        self.__update_ifx_levels_display()

    def __on_rename_link(self):
        link_rename_manager = LinkRenameManager()
        if link_rename_manager.is_link_rename_ready(self.__selected_object):
            link_rename_manager.start_rename_action.triggered.emit()

    # Gui changes: front-to-back
    __slot_on_object_name_edit_gui = safe_slot(__on_object_name_edit_gui)
    __slot_on_ifx_level_edit_gui = safe_slot(__on_ifx_level_edit_gui)
    __slot_on_part_position_edit_gui = safe_slot(__on_part_position_edit_gui)
    __slot_on_part_comment_edit_gui = safe_slot(__on_part_comment_edit_gui)
    __slot_on_waypoint_position_edit_gui = safe_slot(__on_waypoint_position_edit_gui)
    __slot_on_link_declutter_changed_gui = safe_slot(__on_link_declutter_changed_gui)

    # Backend updates: back-to-front
    __slot_on_object_name_changed_backend = safe_slot(__on_object_name_changed_backend)
    __slot_on_ifx_level_changed_backend = safe_slot(__on_ifx_level_changed_backend)
    __slot_on_part_position_changed_backend = safe_slot(__on_part_position_changed_backend)
    __slot_on_part_comment_changed_backend = safe_slot(__on_part_comment_changed_backend)
    __slot_on_waypoint_position_changed_backend = safe_slot(__on_waypoint_position_changed_backend)
    __slot_on_link_declutter_changed_backend = safe_slot(__on_link_declutter_changed_backend)
    __slot_on_link_waypoint_added_backend = safe_slot(__on_link_waypoint_added_backend)
    __slot_on_link_waypoint_removed_backend = safe_slot(__on_link_waypoint_removed_backend)
    __slot_on_link_target_changed_backend = safe_slot(__on_link_target_changed_backend)
    __slot_on_part_path_change = safe_slot(__on_ifx_item_path_changed)
    __slot_on_rename_link = safe_slot(__on_rename_link)
