# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: TreeModel and TreeItem classes

Implements the following classes:

    TreeItem: an item in the TreeModel class.
    TreeModel: an editable model based on TreeItem.
    TODO: handle additional roles in a nice way

Version History: based on the PyQt5 itemviews/editabletreemodel.py example
    PEP-8-ized by Alan Ezust, 2014
    Some bugs fixed by the R4HR team. 2014

"""

# --------------------------------------------------------------------------------------------------

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtCore import QAbstractItemModel, Qt, QObject, QModelIndex
from PyQt5.QtWidgets import QMessageBox

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...scenario.defn_parts import ActorPart, BasePart
from ...scenario import OriActorPartKeys as ApKeys

from ..safe_slot import safe_slot, ext_safe_slot
from ..gui_utils import exec_modal_dialog
from ..undo_manager import RemovePartCommand, AddPartCommand, RenamePartCommand
from ..undo_manager import scene_undo_stack

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    TreeItem = 'TreeItem'
    TreeModel = 'TreeModel'


class TreeItem(QObject):
    """
    An item in the TreeModel.  The user_data data member contains the BasePart (Currently only Actor)
    that the TreeItem represents.
    This was originally supposed to be an internal class not exposed to other modules.
    """

    def __init__(self, data: List[str], parent: Decl.TreeItem = None, user_data: ActorPart = None,
                 model: Decl.TreeModel = None):
        """
        :param data: a list of columns, or a single element if there is only 1 column of data.
        :param parent: optional parent TreeItem
        :param user_data: optional user data, returned from Qt.UserRole, can be any object
        """
        QObject.__init__(self)
        self._parent_item = parent
        self.__item_data = data  # the name of the tree item that will appear in the Scenario Browser
        self.__child_items = []
        self.__user_data = None  # the actual Actor Part represented by the tree item (set using set_data)
        self.__model = model
        self._undo = scene_undo_stack()

        self.set_data(0, user_data, Qt.UserRole)

    def child(self, child_num: int):
        """
        :param child_num the row/child number
        :returns the nth TreeItem child
        """
        return self.__child_items[child_num]

    def child_count(self) -> int:
        return len(self.__child_items)

    def child_number(self) -> int:
        if not self._parent_item:
            return self._parent_item.__child_items.index(self)
        return 0

    def column_count(self) -> int:
        return len(self.__item_data)

    def data(self, column, role=Qt.DisplayRole) -> object:
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return self.__item_data[column]
        else:
            if role == Qt.UserRole:
                return self.__user_data

        return None

    def add_child(self, child):
        new_item = TreeItem([child.part_frame.name], self, child, model=self.__model)
        self.__child_items.append(new_item)

        return new_item

    def insert_children(self, position: int, count: int, columns: int) -> bool:
        if position < 0 or position > len(self.__child_items):
            return False

        for row in range(count):
            data = [None for v in range(columns)]  # [None for v in range(columns)]
            item = TreeItem(data, self, model=self.__model)
            assert self is item._parent_item
            assert item not in self.__child_items
            self.__child_items.insert(position, item)

        return True

    def insert_columns(self, position, columns) -> bool:
        if position < 0 or position > len(self.__item_data):
            return False

        for column in range(columns):
            self.__item_data.insert(position, None)

        for child in self.__child_items:
            child.insert_columns(position, columns)

        return True

    def parent(self):
        if not hasattr(self, "_parent_item"):
            pass
        return self._parent_item

    def get_child_items(self):
        """
        Get this instance's child items.
        :return:  A list of tree items that are direct children of this instance's tree item.
        """
        return self.__child_items

    def get_user_data(self) -> ActorPart:
        """
        Get this instance's user data.  The user data is the actual Actor Part represented by the TreeItem.
        :return: The Actor Part represented by this tree item.
        """
        return self.__user_data

    def get_item_data(self) -> str:
        """
        Get this instance's item data, which is the name of the TreeItem that is visible in the Scenario
        Browser.  The TreeItem represents an Actor Part.
        :return: A list containing the item data.  The name of the TreeItem can be found in the first position.
        """
        return self.__item_data

    def set_item_data(self, value):
        """
        Set this instance's item data. The item data is the name of the Actor Part as shown in the Scenario
        Browser.
        :param value: A new value for item data.
        """
        self.__item_data = value

    def remove_children(self, position: int, count: int) -> bool:
        """
        This method is used to remove a number of TreeItems (specified by count) starting at a give
        position of self (specified by position).
        :param position: The position at which to start the removal of child TreeItems.
        :param count: The number of child TreeItems to remove.
        :return: Boolean indicating whether or not the children TreeItem(s) were successfully removed from self.
        """
        if position < 0 or position + count > len(self.__child_items):
            return False

        for row in range(position, position + count):
            # Disconnect this child's signal connections otherwise multiple calls to slots can trigger a bug
            # where child parts that have been removed are triggered to be removed again.
            child_item = self.child(row)
            child_actor = child_item.user_data
            child_actor.signals.sig_child_added.disconnect(child_item.slot_on_child_added)
            child_actor.signals.sig_child_deleted.disconnect(child_item.slot_on_child_deleted)
            child_actor.part_frame.signals.sig_name_changed.disconnect(child_item.slot_on_renamed)
            self.__child_items.pop(row)

        return True

    def remove_columns(self, position: int, columns: int) -> bool:
        """
        This method is used to remove a number of TreeItems (specified by columns) starting at a given
        position of self (specified by position). Currently only the first (index 0) is used to set user_data.
        :param position: The position at which to start the removal of child TreeItems.
        :param columns: The number of child TreeItems to remove.
        :return: Boolean indicating whether or not the children TreeItem(s) were successfully removed from self.
        """
        if position < 0 or position + columns > len(self.__item_data):
            return False

        for column in range(columns):
            self.__item_data.pop(position)

        for child in self.__child_items:
            child.remove_columns(position, columns)

        return True

    def set_data(self, column: int, user_data: Either[ActorPart, str], role: Qt.ItemDataRole) -> bool:
        """
        This method is used to set the data of a TreeItem.  The self.__item_data represents the name
        of the Actor Part that is displayed as a TreeItem within the Scenario Browser.  The self.__user_data
        contains the actual Actor Part.
        :param column: The column into which to add a TreeItem.
        :param user_data: This represents the actual Actor Part if user role, else string
        :param role: A role to set application specific data.
        :return: Boolean indicating whether or not the TreeItem's data was set successfully.
        """
        if role == int(Qt.UserRole):
            if self.__user_data == user_data:
                return True

            if self.__user_data is not None:
                self.__user_data.signals.sig_child_added.disconnect(self.slot_on_child_added)
                self.__user_data.signals.sig_child_deleted.disconnect(self.slot_on_child_deleted)
                self.__user_data.part_frame.signals.sig_name_changed.disconnect(self.slot_on_renamed)

            self.__user_data = user_data

            if self.__user_data is not None:
                self.__user_data.signals.sig_child_added.connect(self.slot_on_child_added)
                self.__user_data.signals.sig_child_deleted.connect(self.slot_on_child_deleted)
                self.__user_data.part_frame.signals.sig_name_changed.connect(self.slot_on_renamed)

            return True

        if role != int(Qt.EditRole):
            return False

        if column < 0 or column >= len(self.__item_data):
            return False

        self.__item_data[column] = user_data

        return True

    def on_child_added(self, child_part: BasePart):
        """
        This slot is called when a child gets added to the Actor hierarchy.
        This is what creates a new tree item with the correct data.
        :param id_part_to_add: The session id of the part object that is to be added.
        """
        if child_part.PART_TYPE_NAME != ApKeys.PART_TYPE_ACTOR:
            # if not an actor part, nothing else to do
            return

        # Before the child can be added to this tree item (self), we need to determine self's QModelIndex.
        self_index = self.__model.get_q_index(self)
        if self_index is None:
            # we are no longer a valid node in tree
            return

        position = self.__get_alphabetical_position(child_part, self)
        self.__model.insertRows(position, 1, self_index)
        child_index = self.__model.index(position, 0, self_index)

        self.__model.set_index_data(child_index, child_part.part_frame.name)
        self.__model.set_index_data(child_index, child_part, Qt.UserRole)

        new_tree_item = child_index.internalPointer()

        # In the case that an Actor has children, we need to create the hierarchy for it as well.
        # This is the case when an Actor (potentially with children) is 'imported' into a another actor.
        self.__model.create_branch(child_part.children, new_tree_item)

    def on_child_deleted(self, deleted_part_id: int):
        """
        This slot is called when a child has been deleted in the backend.
        When this slot is called, the child item is deleted from the current (self) tree item.
        :param deleted_part_id: The id of the part that needs to be found to delete the corresponding tree item.
        """
        for child in self.__child_items:
            if child.__user_data.SESSION_ID == deleted_part_id:
                child_q_index = self.__model.get_q_index(child)
                self.__model.removeRows(child_q_index.row(), 1, child_q_index.parent())
                break

    def on_renamed(self, new_name: str):
        """
        Slot called when this instance of the tree item's name has changed.
        """
        self.__item_data[0] = new_name
        self.parent().on_child_renamed(self.__user_data, self)

    def on_child_renamed(self, child_part: ActorPart, child_tree_item: Decl.TreeItem):
        """
        This slot is called when one of this instance's child Tree Item name is changed.
        """
        parent_index = self.__model.get_q_index(self)
        child_index = self.__model.get_q_index(child_tree_item)

        # Keep a reference to the row number of the child for use after the row has been removed.
        temp_child_row = child_index.row()

        position = self.__get_alphabetical_position(child_part, self)

        # Qt documentation states that when moving items within the same parent, one should not attempt invalid
        # or no-operation moves.  The two conditions that are considered invalid or no-operation moves are:
        #       1. Moving an item to the position that it is already in.
        #       2. Moving an item to a position that is one after the position that the item is in.
        if position == child_index.row() or position == child_index.row() + 1:
            self.__model.dataChanged.emit(child_index, child_index)
            return

        self.__model.beginMoveRows(parent_index, child_index.row(), child_index.row(), parent_index, position)
        self.remove_children(child_index.row(), 1)

        # Since the insertion position comes after the current position, the remove_children would have decremented
        # the number of rows by 1.  Hence, the computed 'position' has to be decremented by one.
        if position > temp_child_row:
            position -= 1

        self.__reinsert_tree_item(position, child_tree_item, 0)
        self.__model.endMoveRows()

    slot_on_child_added = ext_safe_slot(on_child_added)
    slot_on_child_deleted = safe_slot(on_child_deleted)
    slot_on_renamed = safe_slot(on_renamed)

    child_items = property(get_child_items)
    item_data = property(get_item_data, set_item_data)
    user_data = property(get_user_data)

    def __reinsert_tree_item(self, position: int, tree_item: Decl.TreeItem, columns: int) -> bool:
        if position < 0 or position > len(self.__child_items):
            return False

        assert self is tree_item.parent()
        assert tree_item not in self.__child_items
        self.__child_items.insert(position, tree_item)

        child_actor = tree_item.user_data
        child_actor.signals.sig_child_deleted.connect(tree_item.slot_on_child_deleted, Qt.UniqueConnection)
        child_actor.part_frame.signals.sig_name_changed.connect(tree_item.slot_on_renamed, Qt.UniqueConnection)
        child_actor.signals.sig_child_added.connect(tree_item.slot_on_child_added, Qt.UniqueConnection)

        return True

    def __get_alphabetical_position(self, part_to_find_position_for: ActorPart, parent_tree_item: Decl.TreeItem) -> int:
        """
        This method is used to determine where to insert a newly added part or a renamed part within a parent tree item.
        This is based on the newly inserted items alphabetical position (with respect to the existing items).
        :param part_to_find_position_for: The part that is either being added to the Scenario or being renamed within
            the Scenario.
        :param parent_tree_item: The tree item within the Scenario Browser that is the parent of the tree item whose
            user_data is part_to_find_position_for.
        :return:  The position at which a newly added part/renamed part is to be inserted within the parent_tree_item.
        """
        found_position = None

        for position, item in enumerate(parent_tree_item.__child_items):
            if part_to_find_position_for.name < item.__item_data[0]:
                found_position = position
                break
            elif part_to_find_position_for.name == item.__item_data[0]:
                if part_to_find_position_for.SESSION_ID < item.__user_data.SESSION_ID:
                    found_position = position
                    break

        if found_position is None:
            found_position = len(parent_tree_item.__child_items)

        return found_position


class TreeModel(QAbstractItemModel):
    """
    An editable TreeModel consisting of TreeItems, implementing the QAbstractItemModel interface.

    TreeModel subclasses QAbstractItemModel and most of its interface is inherited from that class.
    For complete API Documentation, please see Qt Documentation:
    http://qt-project.org/doc/qt-5/qabstractitemmodel.html

    Note: It would have been nice if instead of exposing TreeItem in this API,
    we used BasePart as the argument/return types instead!!!
    Then I wouldn't have to implement them for BasePart again for communicating with other Panels.
    TreeItem was supposed to be an internal class!!
    """

    def __init__(self, root_item: TreeItem = None, parent: QObject = None):
        super().__init__(parent)
        self._root_item = None
        self._undo_stack = scene_undo_stack()

    def get_item(self, index: QModelIndex) -> TreeItem:
        if index.isValid():
            item = index.internalPointer()
            if item:
                return item
        return self._root_item

    @override(QAbstractItemModel)
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return self._root_item.column_count() if self._root_item else 0

    @override(QAbstractItemModel)
    def data(self, index: QModelIndex, role=Qt.DisplayRole) -> object:
        """
        override from base class. called from index.data().

        :param index: the location in data model
        :param role: The kind of data that is requested (display text, size hint, background color, etc)
        :return: data of any type, representing the item at the indexed index, or None if the index was not valid
        """
        if not index.isValid():
            return None

        try:
            item = self.get_item(index)
            return item.data(index.column(), role)
        except IndexError:
            return None

    @override(QAbstractItemModel)
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        """ Returns what kinds of interactions the user can have with an item at a particular location
        :param index: the index of the item
        :return: A bitwise or of flags defined in Qt.ItemFlags
        """
        if not index.isValid():
            return 0

        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable

    @override(QAbstractItemModel)
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole) -> object:
        """
        Returns information about the header row or column for this model.
        :param section: the row or column number
        :param orientation: horizontal or vertial
        :param role: The kind of data that is requested (display text, size hint, background color, etc)
        :return: data of any type
        """
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._root_item.data(section)

    @override(QAbstractItemModel)
    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        if row < 0 or column < 0 or row >= self.rowCount(parent):
            return QModelIndex()
        if parent.isValid() and parent.column() != 0:
            return QModelIndex()
        parent_item = self.get_item(parent)
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    @override(QAbstractItemModel)
    def insertColumns(self, position: int, columns: int, parent=QModelIndex()) -> bool:
        self.beginInsertColumns(parent, position, position + columns - 1)
        success = self._root_item.insert_columns(position, columns)
        self.endInsertColumns()

        return success

    @override(QAbstractItemModel)
    def insertRows(self, position: int, rows: int, parent=QModelIndex()) -> bool:
        parent_item = self.get_item(parent)
        self.beginInsertRows(parent, position, position + rows - 1)
        success = parent_item.insert_children(position, rows,
                                              self._root_item.column_count())
        self.endInsertRows()

        return success

    @override(QAbstractItemModel)
    def parent(self, index: QModelIndex) -> QModelIndex:
        if not index.isValid():
            return QModelIndex()

        child_item = self.get_item(index)
        try:
            parent_item = child_item.parent()
        except Exception:
            return QModelIndex()

        if parent_item is None or parent_item == self._root_item:
            return QModelIndex()

        return self.createIndex(parent_item.child_number(), 0, parent_item)

    @override(QAbstractItemModel)
    def removeColumns(self, position: int, columns: int, parent=QModelIndex()) -> bool:
        self.beginRemoveColumns(parent, position, position + columns - 1)
        success = self._root_item.remove_columns(position, columns)
        self.endRemoveColumns()
        if self._root_item.column_count() == 0:
            self.removeRows(0, self.rowCount())
        return success

    @override(QAbstractItemModel)
    def removeRows(self, position: int, num_rows: int, parent=QModelIndex()) -> bool:
        parent_item = self.get_item(parent)
        self.beginRemoveRows(parent, position, position + num_rows - 1)
        success = parent_item.remove_children(position, num_rows)
        self.endRemoveRows()
        return success

    @override(QAbstractItemModel)
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        parent_item = self.get_item(parent)
        return parent_item.child_count() if parent_item else 0

    # I wish we didn't expose TreeItem in our API.
    def get_q_index(self, tree_item: TreeItem) -> QModelIndex:
        """
        This method is used to get a QModelIndex given a TreeItem.
        :param tree_item: The tree item for which to get the QModelIndex for.
        :return: QModelIndex
        """

        # This list will hold a list of TreeItem objects that forms the link to
        # the tree_item that we need to find the QModelIndex for.  The right most
        # TreeItem object in this list will be the tree_item we are looking the QModelIndex for.
        # The left most TreeItem object in this list will be the root tree item.
        tree_item_path_to_root = [tree_item]

        # This while loop fills the tree_item_path_to_root with TreeItem objects.
        # At the end of this loop, tree_item_path_to_root should look like (as an example):
        # [tree_item_root, tree_item1, tree_item2, tree_item]
        while tree_item.parent() is not None:
            tree_item = tree_item.parent()
            tree_item_path_to_root.insert(0, tree_item)

        # This gives us the TreeModel's root QModelIndex from which we can
        # determine all other QModelIndex's within this model.
        index = QModelIndex()

        # The for loop here starts at element one because element 0 is the TreeItem
        # that is inserted into the Actor Hierarchy panel (so essentially, this TreeItem
        # isn't shown as part of being 'within' the tree.  Therefor, Origame's 'Root Actor' TreeItem
        # is actually element 1.
        # In the first iteration of this loop, we are looking for the QModelIndex
        # of Origame's 'Root Actor'.  Once we get that, we just keep looping over the
        # tree_item_path_to_root list until we get the QModelIndex of the tree_item that
        # is of interest.
        for tree_item in tree_item_path_to_root[1:]:
            new_index = self.get_index_in_parent(tree_item, index)
            if new_index is None:
                break
            index = new_index

        return index

    def find_part_in_model(self, part: BasePart) -> QModelIndex:
        """
        Find given part in model, based on its path from root
        :param part: the part we are looking for
        :return: QModelIndex corresponding to that part, or None if not found
        """
        parts_path = part.get_parts_path(with_root=True)
        parent_index = QModelIndex()
        for part in parts_path:
            found_index = self._find_child(part, parent_index)
            if found_index is None:
                return None
            else:
                parent_index = found_index

        return parent_index

    def get_index_in_parent(self, tree_item: TreeItem, parent_index: QModelIndex) -> QModelIndex:
        """
        Given a tree_item and a parent QModelItem parent_index, this method determines what the
        QModelIndex of the tree_item itself.

        :param tree_item: TreeItem for which to find the QModelIndex for.
        :param parent_index: The tree_item's parent QModelIndex.
        :return: The tree_items's QModelIndex.
        """
        for index_row in range(self.rowCount(parent_index)):
            child_index = self.index(index_row, 0, parent_index)
            if child_index.internalPointer() is tree_item:
                return child_index

        # This should never happen, if it does, there is a problem.
        # The reason being is that if you have a tree item that you are looking for,
        # it must have a QModelIndex in the model.
        # Colin FIXME build 3: find proper fix so code does not get here: why is item not found??? Then remove the return
        return None
        raise ValueError('BUG: QModelIndex for tree item {} not found!'.format(tree_item.get_user_data()))

    @override(QAbstractItemModel)
    def setData(self, index: QModelIndex, value: Any, role=Qt.EditRole) -> bool:
        """
        This is how  values from user editing operations get sent to the model.
        Called when the user finishes editing a cell in the View.
        :param index: index of the data to set
        :param value: an arbitrary value that came from the editor widget
        :param role: the kind of data to set.
        :return: true if successful.
        """

        actioned_actor = index.data(Qt.UserRole)
        rename_command = RenamePartCommand(actioned_actor, value)
        self._undo_stack.push(rename_command)

        return True

    def set_index_data(self, index: QModelIndex, value: Either[ActorPart, str], role=Qt.EditRole) -> bool:
        """
        When values (part names) on the backend change, they must call this method to update our cached copy
        of the data.
        Given a QModelIndex, this method is used to set data for different roles that are represented
        by this index. If role is Qt.EditRole, the value must be of type string.  If role is UserData, then value must
        be of type ActorPart.
        :param index:  The QModelIndex of tree item.
        :param value:  The value of a particular Qt role being set.
        :param role:  The role for which the value is being set.
        :return:
        """
        if role == Qt.EditRole:
            assert isinstance(value, str)

        if role == Qt.UserRole:
            assert isinstance(value, ActorPart)

        result = index.internalPointer().set_data(index.column(), value, role)

        if result:
            self.dataChanged.emit(index, index)

    def add_actor(self, index: QModelIndex):
        """
        :param index: QModelIndex of the tree item that was actioned upon using the right-click
            select on an item within the Scenario Browser.  This is the tree item into
            which a new actor is to be added.  It is the models responsibility
            to send this request to the backend (which is being done here via the undo stack).
        """
        if index is None:
            pass
        actioned_actor = index.data(Qt.UserRole)
        log.info("Add Actor clicked for actor {} row {} col {}", actioned_actor, index.row(), index.column())
        add_command = AddPartCommand(actioned_actor, 'actor')
        self._undo_stack.push(add_command)

    def delete_actor(self, index: QModelIndex) -> bool:
        """
        :param index: QModelIndex of the tree item that was actioned upon using the right-click
            select on an item within the Scenario Browser.  This is the tree item that
            is to be deleted.  It is the models responsibility to send this request to
            the backend (which is being done here via the AsyncRequest call).
        :returns a boolean flag indicating if the user confirmed actor deletion.
        """
        actioned_actor = index.data(Qt.UserRole)
        assert actioned_actor.parent_actor_part is not None

        msg = "Delete '{}'? Are you sure?".format(actioned_actor.name)
        if exec_modal_dialog("Delete Actor", msg, QMessageBox.Question) == QMessageBox.Yes:
            log.info("Delete clicked on actor {}", actioned_actor.name)
            remove_command = RemovePartCommand(actioned_actor, view_is_parent=True)
            self._undo_stack.push(remove_command)
            return True
        else:
            return False

    @override(QAbstractItemModel)
    def setHeaderData(self, section, orientation: Qt.Orientation, value: Any, role=Qt.EditRole) -> bool:
        if role != Qt.EditRole or orientation != Qt.Horizontal:
            return False

        result = self._root_item.set_data(section, value)
        if result:
            self.headerDataChanged.emit(orientation, section, section)

        return result

    def _find_child(self, find_part: BasePart, parent_index: QModelIndex) -> QModelIndex:
        """
        Find the given part among the children of parent_index.
        :param find_part: the BasePart to find
        :param parent_index: index of model item containing children to search
        :return: QModelIndex of the found TreeItem associated with find_part, or None if not found
        """
        row_count = self.rowCount(parent_index)
        for row in range(0, row_count):
            idx = self.index(row, 0, parent_index)
            part_obj = self.data(idx, Qt.UserRole)
            if part_obj is find_part:
                return idx

        return None
