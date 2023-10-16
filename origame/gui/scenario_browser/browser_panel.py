# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Scenario Browser Panel

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import weakref

# [2. third-party]
from PyQt5.QtCore import QItemSelection, pyqtSignal, QPoint, QItemSelectionModel, QModelIndex, Qt, QObject
from PyQt5.QtGui import QMouseEvent, QKeyEvent
from PyQt5.QtWidgets import QMenu, QMessageBox, QTreeView, QWidget, QSplitter, QAction, QVBoxLayout, QListWidgetItem

# [3. local]
from ...core import override, internal
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...scenario import ScenarioManager, Scenario, OriActorPartKeys as ApKeys
from ...scenario.defn_parts import BasePart, ActorPart

from ..gui_utils import exec_modal_dialog, IScenarioMonitor, get_scenario_font
from ..safe_slot import safe_slot, ext_safe_slot
from ..actions_utils import create_action, IMenuActionsProvider
from ..async_methods import AsyncRequest
from ..undo_manager import scene_undo_stack

from .tree_model import TreeModel, TreeItem
from .search_progress import SearchProgressDialog
from .Ui_search_panel import Ui_ScenSearchPanel

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------
__all__ = [
    # defines module members that are public; one line per string
    'ScenarioBrowserPanel',
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

class ActorHierarchyView(IMenuActionsProvider, QTreeView):
    """
    This is a tree view that uses ActorHierarchyModel as its model
    """

    sig_user_selected_part = pyqtSignal(BasePart)

    def __init__(self, parent=None):
        QTreeView.__init__(self, parent)
        IMenuActionsProvider.__init__(self)

        self.setFont(get_scenario_font())

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setSelectionMode(self.SingleSelection)
        self.customContextMenuRequested.connect(self.__slot_show_context_menu)
        self.context_menu = QMenu(self)

        self.__set_edit_actions()

        self.context_menu.addAction(self.__action_add)
        self.context_menu.addAction(self.__action_delete)
        self.context_menu.addAction(self.__action_rename)

        self.__current_selection_index = QModelIndex()

    @override(QTreeView)
    def selectionChanged(self, selected_items: QItemSelection, deselected_items: QItemSelection):
        """
        Overrided method to keep track of current selection of item in the tree.  This is to eliminate the problem
        when a user right clicks on an item and moves the mouse to a different item in the tree - when the user lets go
        of right click in this case, and selects one of the actions, the asynchronous call is made on the item that
        the mouse is hovering over (and not the initial item that the right click was done on).
        :param selected_items: A list of tree items that are currently selected.
        :param deselected_items: A list of tree items that had been previously selected, but are now deselected.
        """
        # One can only ever select one actor from the Browser Panel, so the selected_items will only consist of a
        # single QModelIndex.

        if selected_items.indexes():
            self.__current_selection_index = selected_items.indexes()[0]
            selected_part = self.__current_selection_index.data(Qt.UserRole)
            log.debug('Browser hierarchy view selected {}', selected_part)

        else:
            log.debug('Browser hierarchy view selection now empty')
            self.__current_selection_index = None

    @override(QTreeView)
    def mousePressEvent(self, event: QMouseEvent):
        """Must only emit selection change signal if user-initiated"""
        current_selection = self.__current_selection_index.data(Qt.UserRole)
        super().mousePressEvent(event)
        self.__check_user_selection_change(current_selection)

    @override(QTreeView)
    def keyPressEvent(self, event: QKeyEvent):
        """Must only emit selection change signal if user-initiated"""
        current_selection = self.__current_selection_index.data(Qt.UserRole)
        super().keyPressEvent(event)
        self.__check_user_selection_change(current_selection)

    @override(IMenuActionsProvider)
    def get_edit_actions(self) -> List[QAction]:
        return (self.__action_add, self.__action_delete,
                scene_undo_stack().get_action_undo(), scene_undo_stack().get_action_redo())

    @override(IMenuActionsProvider)
    def update_actions(self):
        # log.debug('Browser hierarchy view updating actions')
        if self.__current_selection_index is None:
            deletable = False
        else:
            selected_part = self.__current_selection_index.data(Qt.UserRole)
            deletable = (selected_part.parent_actor_part is not None)
            # log.debug('Browser hierarchy view part deletion allowed: {}', deletable)

        self.__action_delete.setEnabled(deletable)
        self.__action_add.setEnabled(True)
        self.__action_rename.setEnabled(True)
        scene_undo_stack().setActive(True)

    @override(IMenuActionsProvider)
    def disable_actions(self):
        # log.debug('Browser hierarchy view disabling actions')
        self.__action_delete.setEnabled(False)
        self.__action_add.setEnabled(False)
        self.__action_rename.setEnabled(False)
        scene_undo_stack().setActive(False)

    def get_current_selection(self) -> QModelIndex:
        """
        Gets the current item index selected.
        :return: The model index of the selected item.
        """
        return self.__current_selection_index

    def __check_user_selection_change(self, previous_selection: ActorPart):
        """
        Check to see if the user has changed selection. If so, emit sig_user_selected_part.
        :param previous_selection: the previous user selection
        """
        new_selection = self.__current_selection_index.data(Qt.UserRole)
        if previous_selection is not new_selection:
            assert new_selection is not None
            self.sig_user_selected_part.emit(new_selection)

    def __show_context_menu(self, point: QPoint):
        """Show context menu actions at given QPoint"""
        CONTEXT_Y_OFFSET = 30
        idx = self.indexAt(point)
        # Prevent the popup menu from obscuring the text in the TreeView
        if idx.internalPointer() is not None:
            point.setY(point.y() + CONTEXT_Y_OFFSET)
            for action in self.context_menu.actions():
                if action.text() == "Delete":
                    if idx.internalPointer()._parent_item._parent_item is None:
                        action.setDisabled(True)
                    else:
                        action.setDisabled(False)
                action.setData(idx)

            if idx.isValid():
                self.update_actions()
                self.context_menu.exec(self.mapToGlobal(point), self.__action_add)

    def __set_edit_actions(self):
        """
        Define and set the Edit menu actions for this panel.
        """
        self.__action_add = create_action(
            self,
            text='Add Actor',
            tooltip='Add a child actor to currently selected part',
            connect=self.__slot_on_action_add,
        )
        self.__action_delete = create_action(
            self,
            text='Delete',
            tooltip='Delete the currently selected part',
            pix_path=":/icons/delete.png",
            shortcut='Delete',
            connect=self.__slot_on_action_delete,
        )
        self.__action_rename = create_action(
            self,
            text='Rename',
            tooltip='Rename the currently selected part',
            connect=self.__slot_on_action_rename,
        )

    def __on_action_add(self):
        """Execute the Add Actor action"""
        assert self.__action_add.isEnabled()
        self.model().add_actor(self.__current_selection_index)

    def __on_action_delete(self):
        """Execute the Delete Actor action"""
        assert self.__action_delete.isEnabled()
        user_confirmed = self.model().delete_actor(self.__current_selection_index)
        if user_confirmed:
            # selection will change:
            self.__current_selection_index = None

    def __on_action_rename(self):
        """Execute the Rename Actor action"""
        assert self.__action_rename.isEnabled()
        self.edit(self.__current_selection_index)

    __slot_on_action_add = safe_slot(__on_action_add)
    __slot_on_action_delete = safe_slot(__on_action_delete)
    __slot_on_action_rename = safe_slot(__on_action_rename)
    __slot_show_context_menu = safe_slot(__show_context_menu)


class ActorHierarchyModel(TreeModel):
    """
    A Tree Model of the scenario actor hierarchy that is based on ScenarioDefinition
    """

    def __init__(self, scenario: Scenario, parent=None):
        TreeModel.__init__(self, parent=parent)
        self._root_item = None
        self.create_tree_from_root([scenario.root_actor])

    def create_tree_from_root(self, actors: List[ActorPart]) -> TreeItem:
        """
        Method used to traverse an ActorPart and create a TreeItem.
        :param actors: A list of ActorParts, each of which may contain other child ActorParts.
        :return: root item of hierarchy
        """
        self.beginResetModel()
        self._root_item = TreeItem(["Actor Hierarchy"], model=self)
        self.create_branch(actors, self._root_item)
        self.endResetModel()

        return self._root_item

    def create_branch(self, actors: List[ActorPart], parent_item: TreeItem):
        """
        Method used to traverse an ActorPart's children and create TreeItems.
        :param actors: A list of ActorParts, each of which may contain other child ActorParts.
        :param parent_item: The root TreeItem object
        """
        for child in actors:
            if child.PART_TYPE_NAME == ApKeys.PART_TYPE_ACTOR:
                new_item = parent_item.add_child(child)
                self.create_branch(child.children, new_item)


class ListItemPartMonitor(QObject):
    def __init__(self, parent_list_item: QListWidgetItem, part: BasePart):
        """
        This class monitors a BasePart object for changes, and notifies the parent_list_item.

        NOTE: This class is required because QListWidgetItem-derived classes cannot have pyqtSlotted
        methods; these are only allowed on QObject, but PyQt does not support deriving a class from
        multiple Qt classes, so a class that derives from QListWidgetItem cannot also derive from
        QObject. Slots are possible, but pyqtSlot'd method (as done by safe_slot) are significantly
        faster and use less memory than non-pyqtSlot'd method.

        Note: it is necessary to hold the parent list item by weak reference otherwise when the list widget
        is cleared, the list item is still kept alive by the signals connected to it.

        :param parent_list_item: The list item that this instance will be assigned to as associated data.
        :param part: The part to be monitored on behalf of the associated list item.
        """
        super().__init__()
        self.__parent_list_item = weakref.ref(parent_list_item)
        part.part_frame.signals.sig_name_changed.connect(self.__slot_on_list_item_name_changed)
        part.base_part_signals.sig_in_scenario.connect(self.__slot_on_part_in_scenario)
        part.base_part_signals.sig_parent_path_change.connect(self.__slot_on_part_path_change)

    def __on_list_item_name_changed(self, _: str):
        """When backend signals that part name has changed, notify list item"""
        widget_list_item = self.__parent_list_item()
        if widget_list_item is None:
            self.__discard()
        else:
            widget_list_item._on_part_path_changed()

    def __on_part_in_scenario(self, in_scenario: bool):
        """
        When the part has been removed or restored to the scenario, notify the associated list widget item
        :param in_scenario: True if the part being monitored has been restored to the scenario; False if removed from
            the scenario.
        """
        widget_list_item = self.__parent_list_item()
        if widget_list_item is None:
            self.__discard()
        else:
            widget_list_item._on_part_in_scenario_changed(in_scenario)

    def __on_list_item_path_changed(self):
        """When backend signals that part path has changed, notify list item"""
        widget_list_item = self.__parent_list_item()
        if widget_list_item is None:
            self.__discard()
        else:
            widget_list_item._on_part_path_changed()

    def __discard(self):
        # self.disconnect()
        self.deleteLater()

    __slot_on_list_item_name_changed = safe_slot(__on_list_item_name_changed)
    __slot_on_part_in_scenario = safe_slot(__on_part_in_scenario)
    __slot_on_part_path_change = safe_slot(__on_list_item_path_changed)


class SearchHitItem(QListWidgetItem):
    def __init__(self, part: BasePart):
        QListWidgetItem.__init__(self, part.get_path())

        self.default_font_color = self.foreground()
        self.__part = part
        self.__data = ListItemPartMonitor(self, part)

    def get_part(self) -> BasePart:
        return self.__part

    @internal(ListItemPartMonitor)
    def _on_part_path_changed(self):
        part_path = self.__part.get_path()
        self.setText(part_path)

    @internal(ListItemPartMonitor)
    def _on_part_in_scenario_changed(self, in_scenario: bool):
        if in_scenario:
            self.setText(self.__part.get_path())
            self.setForeground(self.default_font_color)
            self.setToolTip("")
            self.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        else:
            self.setForeground(Qt.red)
            self.setToolTip("Part has been deleted or cut from scenario")
            self.setFlags(Qt.NoItemFlags)


class ScenarioSearchPanel(IScenarioMonitor, QWidget):
    """
    This is the "scenario search" part of the panel.
    """
    sig_search_hit_selected = pyqtSignal(BasePart)

    def __init__(self, scenario_manager: ScenarioManager, parent=None):

        IScenarioMonitor.__init__(self, scenario_manager)
        QWidget.__init__(self, parent)

        self.__scenario_weak = None
        self.__current_search_text = None

        self.ui = Ui_ScenSearchPanel()
        self.ui.setupUi(self)
        self.ui.list_search_results.setFont(get_scenario_font())
        self.ui.text_pattern.setFont(get_scenario_font())
        self.ui.button_cancel.hide()
        self.ui.button_search.clicked.connect(self.slot_on_search_clicked)
        self.ui.button_cancel.clicked.connect(self.slot_on_cancel_search)
        self.ui.text_pattern.returnPressed.connect(self.slot_on_search_clicked)
        self.ui.text_pattern.textEdited.connect(self.__slot_on_search_box_text_edited)
        self.ui.list_search_results.itemDoubleClicked.connect(self.__slot_show_search_hit_part)

        self._monitor_scenario_replacement()

    def set_pattern(self, pattern: str):
        """Set the search pattern"""
        self.ui.text_pattern.setText(pattern or '')

    @property
    def num_results(self) -> int:
        """Get how many results were found from last search. Returns 0 if no search done yet."""
        return self.ui.list_search_results.count()

    def get_search_result_item(self, row: int) -> QListWidgetItem:
        """
        This function returns the Search Results list item object corresponding to the specified row.
        :param row: The 0-based row number of the list item to be returned.
        """
        return self.ui.list_search_results.item(row)

    def on_cancel_search(self):
        scenario = self.__scenario_weak()
        assert scenario is not None
        scenario.cancel_search()

    def on_search_clicked(self):
        """
        Method called when the search button is clicked in the Scenario Browser.
        """
        # if the scenario doesn't exist there is no point in taking action:
        scenario = self.__scenario_weak()
        assert scenario is not None

        text = self.ui.text_pattern.text()

        if not text:
            exec_modal_dialog("Search Error", "Please enter a text string in the search box.", QMessageBox.Warning)
            return

        self.__current_search_text = text

        self.ui.button_cancel.show()
        self.ui.button_search.hide()
        self.ui.text_pattern.setEnabled(False)
        self.ui.list_search_results.setEnabled(False)

        self.ui.list_search_results.clear()

        AsyncRequest.call(scenario.search_parts, text, response_cb=self.__on_search_done)

    slot_on_search_clicked = safe_slot(on_search_clicked)
    slot_on_cancel_search = safe_slot(on_cancel_search)

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        """
        Method called whenever the scenario is replaced.
        :param scenario: The new scenario loaded by the Scenario Manager.
        """
        if self.__scenario_weak is not None and self.__scenario_weak() is not None:
            shared_signals = self.__scenario_weak().shared_state.signals
            shared_signals.sig_search_hit.disconnect(self.__slot_on_search_hit)

        self.__scenario_weak = weakref.ref(scenario)
        scenario.shared_state.signals.sig_search_hit.connect(self.__slot_on_search_hit)

        # When scenario has been replaced, clear panel
        self.ui.text_pattern.setText("")
        self.ui.list_search_results.clear()

    def __on_search_hit(self, part: BasePart, props: List[str]):
        log.info('Search hit for part {}: props={}', part, props)
        hit_item = SearchHitItem(part)
        self.ui.list_search_results.addItem(hit_item)

    def __on_search_done(self):
        """
        Callback method once results have been obtained for a particular query. The results have been obtained
        one at a time already so they are merely sorted and the widgets states updated.
        """
        self.ui.button_cancel.hide()
        self.ui.button_search.show()
        self.ui.text_pattern.setEnabled(True)
        self.ui.list_search_results.setEnabled(True)
        self.ui.list_search_results.sortItems()

    def __on_search_box_text_edited(self, new_search_box_text: str):
        """
        Method used to gray out search results list if the search content changes within the search box
        text field.
        :params new_search_box_text: This is the new text that is visible within the search box as a result
                                     of edits by a user.
        """
        if self.__current_search_text is not None and new_search_box_text != self.__current_search_text:
            self.ui.list_search_results.setEnabled(False)
            self.__set_search_results_font_italic(True)
        else:
            self.ui.list_search_results.setEnabled(True)
            self.__set_search_results_font_italic(False)

    def __set_search_results_font_italic(self, is_italic: bool = True):
        """
        This function toggles the font of all list items in the search results list between regular and italic. The
        italic font indicates that the displayed search results no longer reflect the currently displayed search
        string. A tool tip explaining this is also added to each italicised list item.

        :param is_italic: True if the list item text is to be set to italic; False if text is to be non-italic.
        """
        for i in range(self.ui.list_search_results.count()):
            if self.ui.list_search_results.item(i).font().italic() != is_italic:
                ft = self.ui.list_search_results.item(i).font()
                ft.setItalic(is_italic)
                self.ui.list_search_results.item(i).setFont(ft)
            if is_italic:
                self.ui.list_search_results.item(i).setToolTip("Search results do not reflect current search string")
            else:
                self.ui.list_search_results.item(i).setToolTip("")

    def __show_search_hit_part(self, hit_item: QListWidgetItem):
        """
        When user wants to see a part that is in the search results
        :param hit_item:
        """
        hit_part = hit_item.get_part()
        self.sig_search_hit_selected.emit(hit_part)

    __slot_on_search_box_text_edited = safe_slot(__on_search_box_text_edited)
    __slot_on_search_hit = ext_safe_slot(__on_search_hit, arg_types=(BasePart, list))
    __slot_show_search_hit_part = safe_slot(__show_search_hit_part)


class ActorHierarchyPanel(IScenarioMonitor, QWidget):
    """
    A panel that manages the model and view, and communication to/from this model/view pair.

    """
    # emitted whenever the user selects an item in the treeview
    sig_user_selected_part = pyqtSignal(BasePart)
    sig_context_help_changed = pyqtSignal(BasePart)

    def __init__(self, scenario_manager: ScenarioManager, parent=None):
        QWidget.__init__(self, parent)
        IScenarioMonitor.__init__(self, scenario_manager)
        self.actor_hierarchy_view = ActorHierarchyView()
        self.actor_hierarchy_model = None

        actor_hierarchy_layout = QVBoxLayout()
        actor_hierarchy_layout.addWidget(self.actor_hierarchy_view)
        self.setLayout(actor_hierarchy_layout)

        self.actor_hierarchy_view.sig_user_selected_part.connect(self.sig_user_selected_part)
        self.actor_hierarchy_view.setMouseTracking(True)
        self.actor_hierarchy_view.entered.connect(self.__slot_on_hovered)

        self._monitor_scenario_replacement()

    def on_actor_part_opened(self, actor_part: ActorPart):
        """
        Update the browser selection to match the newly opened actor
        """
        index = self.actor_hierarchy_model.find_part_in_model(actor_part)
        if index is None:
            log.debug('Scenario Browser: Actor opened is not ours, likely will be receiving new scenario signal soon')
            return

        sel_model = self.actor_hierarchy_view.selectionModel()
        sel_model.setCurrentIndex(index, QItemSelectionModel.ClearAndSelect)

    slot_on_actor_part_opened = safe_slot(on_actor_part_opened)

    @override(IScenarioMonitor)
    def _replace_scenario(self, scenario: Scenario):
        if self.actor_hierarchy_model is not None:
            self.actor_hierarchy_model.modelReset.disconnect(self.__slot_on_model_reset)
            self.actor_hierarchy_model = None

        assert self.actor_hierarchy_model is None
        self.actor_hierarchy_model = ActorHierarchyModel(scenario)
        self.actor_hierarchy_model.modelReset.connect(self.__slot_on_model_reset)
        self.actor_hierarchy_view.setModel(self.actor_hierarchy_model)

        # select root actor:
        self.__select_root_item()
        self.actor_hierarchy_view.expandAll()

    def __on_model_reset(self):
        """
        When a new model is loaded set the currently selected item of the model to be the root actor.
        """
        index = self.__select_root_item()
        self.actor_hierarchy_view.expandAll()
        self.sig_user_selected_part.emit(index.data(Qt.UserRole))

    def __on_hovered(self, index: QModelIndex):
        """When mouse hovers over an item, context help must be notified"""
        self.sig_context_help_changed.emit(index.data(Qt.UserRole))

    def __select_root_item(self) -> QModelIndex:
        """Select the root actor and return its index"""
        PART_NAME_COLUMN = 0
        index = self.actor_hierarchy_model.index(0, PART_NAME_COLUMN)
        self.actor_hierarchy_view.selectionModel().select(index, QItemSelectionModel.ClearAndSelect)
        return index

    __slot_on_hovered = safe_slot(__on_hovered)
    __slot_on_model_reset = safe_slot(__on_model_reset)


class ScenarioBrowserPanel(IMenuActionsProvider, QWidget):
    """
    Contains the Actor Hierarchy View and also the Scenario Search Panel.

    A QSplitter should be used to separate them.

    """
    sig_search_hit_selected = pyqtSignal(BasePart)

    def __init__(self, scenario_manager: ScenarioManager, parent=None):
        QWidget.__init__(self, parent)
        IMenuActionsProvider.__init__(self)

        self.actor_hierarchy_panel = ActorHierarchyPanel(scenario_manager)
        self.scenario_search_panel = ScenarioSearchPanel(scenario_manager)

        panel_splitter = QSplitter(Qt.Vertical)
        panel_splitter.addWidget(self.actor_hierarchy_panel)
        panel_splitter.addWidget(self.scenario_search_panel)

        scenario_browser_layout = QVBoxLayout(self)
        scenario_browser_layout.addWidget(panel_splitter)
        self.setLayout(scenario_browser_layout)

        self.scenario_search_panel.sig_search_hit_selected.connect(self.sig_search_hit_selected)

    @override(IMenuActionsProvider)
    def get_edit_actions(self) -> List[QAction]:
        """
        Get the list of Edit menu actions for the panel.
        :return: a list of QActions.
        """
        return self.actor_hierarchy_panel.actor_hierarchy_view.get_edit_actions()

    @override(IMenuActionsProvider)
    def update_actions(self):
        self.actor_hierarchy_panel.actor_hierarchy_view.update_actions()

    @override(IMenuActionsProvider)
    def disable_actions(self):
        self.actor_hierarchy_panel.actor_hierarchy_view.disable_actions()
