# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains the DataPart class definition and supporting code.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import json
import logging
from collections import OrderedDict
import pickle
from enum import IntEnum, unique
from hashlib import md5
import re

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...core.utils import get_verified_repr

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj, OriSchemaEnum, SaveErrorLocationEnum
from ..ori import get_pickled_str, check_needs_pickling, pickle_from_str, pickle_to_str
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriDataPartKeys as DpKeys

from .part_types_info import register_new_part_type
from .base_part import BasePart, check_diff_val
from .actor_part import ActorPart
from .common import Position

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'DataPart',
    'DisplayOrderEnum',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    DataPart = 'DataPart'


@unique
class DisplayOrderEnum(IntEnum):
    """
    This class represents the display order of the keys in the Data Part.
    """
    of_creation, alphabetical, reverse_alphabetical = range(3)


class DataPart(BasePart):
    """
    This class represents a scenario part that supports mapping of keys (text strings) to values.
    The part supports attribute access, and the values can be any valid Python expression.
    """

    class Signals(BridgeEmitter):

        sig_data_added = BridgeSignal(int)  # Position in the ordered dict
        sig_data_changed = BridgeSignal(int)  # Position in the ordered dict
        sig_data_deleted = BridgeSignal(int)  # Position in the ordered dict
        sig_data_cleared = BridgeSignal()
        sig_display_order_changed = BridgeSignal(int)  # DisplayOrderEnum

        # This signal is for overall changes. It can be emitted only by on_exec_done when necessary.
        sig_data_reset = BridgeSignal()

    DEFAULT_VISUAL_SIZE = dict(width=10.0, height=5.1)
    PART_TYPE_NAME = "data"
    DESCRIPTION = """\
        Data parts are used to store multiple variables.  Data variables can be accessed from a function that is
        linked to it. The function script uses dot-notation. For example, 'link.data.area = 10', accesses the part
        pointed at by a linked named 'data' and sets the 'area' variable in the data part to the value 10.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this Part
        :param position: A position to be assigned to the newly instantiated default DataPart. This argument
            is only required when the ori_def default (None) is used.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = DataPart.Signals()
        self.__deep_value_mod_possible = False

        self.__dict__['_Order'] = []
        super().__setattr__('_pos_key_index', {})
        super().__setattr__('_key_pos_index', {})
        super().__setattr__('_display_order', DisplayOrderEnum.of_creation)

    @override(BasePart)
    def on_exec_done(self):
        """
        If an inner element of the data part is changed, the sig_data_reset is emitted to give the data part
        widget a chance to refresh its content. For that matter, any component that is interested in the inner changes
        of a data part should connect to its sig_data_reset.
        """
        if self.__deep_value_mod_possible:
            if self._anim_mode_shared:
                self.signals.sig_data_reset.emit()
        self.__deep_value_mod_possible = False

    @override(BasePart)
    def get_snapshot_for_edit(self) -> {}:
        data = super().get_snapshot_for_edit()
        data['_data'] = self.__get_as_ordered_dict()
        return data

    @override(BasePart)
    def get_matching_properties(self, re_pattern: str) -> List[str]:
        """In addition to basic search, add first key or value that matches pattern (case insensitive)."""
        matches = BasePart.get_matching_properties(self, re_pattern)

        regexp = re.compile(re.escape(re_pattern), re.IGNORECASE)
        for key, value in self.__get_as_ordered_dict().items():
            # first search the key names:
            key_str = str(key)
            result = regexp.search(key_str)
            if result:
                log.debug('Data part {} key "{}" matches pattern "{}"', self, key_str, result.string)
                matches.append("keys[{}]".format(self._Order.index(key_str)))
                break

            # if no hit, then perhaps the key values:
            val_str = str(value)
            result = regexp.search(val_str)
            if result:
                MAX_LEN_MATCHED_PROP_VAL = 100
                log.debug('Data part {} key "{}" matches pattern "{}" on value "{}"',
                          self, key_str, re_pattern, val_str[:MAX_LEN_MATCHED_PROP_VAL])
                matches.append(key_str)
                break

        return matches

    def get_key_at_row(self, row: int) -> str:
        """
        Get the the key at the specified row.

        :param row: The row
        :returns: dict.keys The key in the underlying dict.
        """
        assert row < len(self._Order)
        return self._pos_key_index[row]

    def get_value_at_row(self, row: int) -> Any:
        """
        Get the the value at the specified row.

        :param row: The row
        :returns: dict.values The value in the underlying dict.
        """
        assert row < len(self._Order)
        self.__deep_value_mod_possible = True
        return self.__dict__[self._pos_key_index[row]]

    def get_value_in_string_at_row(self, row: int) -> str:
        """
        Get the string representation of the value at the specified row.

        :param row: The row
        :returns: str The string representation of the value.
        """
        assert row < len(self._Order)
        return repr(self.__dict__[self._pos_key_index[row]])

    def keys(self) -> List[str]:
        """
        Get all the keys.

        The keys are those in the underlying dict.

        :returns: list All the keys of this part.
        """
        return self._Order

    def values(self) -> List[Any]:
        """
        Get all the values.

        The values are those in the underlying dict.

        :returns: list All the values of this part.
        """
        self.__deep_value_mod_possible = True
        return [getattr(self, key) for key in self._Order]

    def items(self):
        """
        Get all the items of this part in OrderedDict format.
        :returns: The items in an OrderedDict.
        """
        return self.__get_as_ordered_dict()

    def clear(self):
        """
        Clear all the data.
        """
        # Clear the underlying dict and its index.
        for k in self._Order:
            del self.__dict__[k]
        self.__dict__['_Order'] = []
        # Clear indices
        self._pos_key_index.clear()
        self._key_pos_index.clear()
        if self._anim_mode_shared:
            self.signals.sig_data_cleared.emit()

    def get_display_order(self) -> DisplayOrderEnum:
        """
        Get the display order on the GUI.

        This is the setting that indicates the preferences of the display order on the GUI. It is not the order of the
        underlying dict, whose order is updated only when an entry is added or deleted.
        :returns: DisplayOrderEnum The display order on the GUI.
        """
        return self._display_order

    def set_display_order(self, display_order: DisplayOrderEnum):
        """
        Set the display order on the GUI.

        This is the setting that indicates the preferences of the display order on the GUI. It is not the order of the
        underlying dict, whose order is updated only when an entry is added or deleted.

        :param display_order: The display order on the GUI.
        """
        super().__setattr__('_display_order', DisplayOrderEnum(display_order))
        self.signals.sig_display_order_changed.emit(display_order.value)

    def assign_from_object(self, rhs_obj: Either[Dict[str, Any], Decl.DataPart]):
        """
        Assignment for DataPart only supports RHS being a dictionary or another DataPart.
        :param rhs_obj: The source part on the right side of the "="
        """
        if isinstance(rhs_obj, dict):
            self.clear()
            for x, value in rhs_obj.items():
                self[x] = value

        else:
            super().assign_from_object(rhs_obj)

    def __setitem__(self, key, value):
        """
        Add or change the entry.

        After an entry is added, its key will be indexed for future faster retrieval of the associated value.

        :param key: The key
        :param value: Any object is accepted.
        """
        self.__setattr__(key, value)

    def __getitem__(self, item):
        """
        Get the entry.

        Get the value associated with the specified item.

        :param item: The key
        :returns: The value associated with the specified item.
        """
        self.__deep_value_mod_possible = True
        return self.__dict__[item]

    def __delitem__(self, key):
        """
        Delete the entry.

        Delete the value associated with the specified key. Remove the index associated with the key.

        :param key: The key
        """
        self.__delattr__(key)

    def __setattr__(self, key, value):
        """
        Add or change the entry.

        :param key: The key
        :param value: Any object is accepted.
        """
        # After an entry is added, its key will be indexed for future faster retrieval of the associated value.
        should_append = key not in self.__dict__ and key not in self.__class__.__dict__ and "_Order" in self.__dict__
        if key == 'display_order':
            super().__setattr__('_display_order', DisplayOrderEnum(value))
        else:
            self.__dict__[key] = value

        if should_append:
            self._Order.append(key)
            # Build indices
            pos = len(self._Order) - 1
            self._pos_key_index[pos] = key
            self._key_pos_index[key] = pos
            if self._anim_mode_shared:
                self.signals.sig_data_added.emit(pos)

    def __getattr__(self, item):
        """
        Get the entry.

        Get the value associated with the specified item.

        :param item: The key
        :returns: The value associated with the specified item.
        """
        try:
            self.__deep_value_mod_possible = True
            return self.__dict__[item]
        except KeyError:
            # Used to satisfy the contract for the caller to do hasattr(a_data_part)
            e = 'The key "' + item + '" does not exist'
            raise AttributeError(e)

    def __delattr__(self, name):
        """
        Delete the entry.

        :param name: The key
        """
        # Delete the value associated with the specified key. Remove the index associated with the key.
        pos = self._key_pos_index[name]
        del self.__dict__[name]
        self._Order.remove(name)
        # Rebuild the indices
        self._pos_key_index.clear()
        self._key_pos_index.clear()
        for i, x in enumerate(self._Order):
            self._pos_key_index[i] = x
            self._key_pos_index[x] = i

        if self._anim_mode_shared:
            self.signals.sig_data_deleted.emit(pos)

    def __contains__(self, item):
        """
        Test if this part has the specified item.

        Forward the test to the underlying dic.

        :param item: The key
        :returns: bool True if the item is contained; otherwise, False.
        """
        return item in self._key_pos_index

    def __iter__(self):
        """
        The iterator of this part.

        Wrap the underlying dict up with the iter()

        :returns: The iterator of the underlying dict.
        """
        for key in self._Order:
            yield key

    def __dir__(self) -> List[str]:
        """The keys are accessible as attributes, so add them to code-completion"""
        return super().__dir__() + list(self.keys())

    def __repr__(self):
        return repr(self.items())

    # --------------------------- instance PUBLIC properties ----------------------------

    display_order = property(get_display_order, set_display_order)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (display_order,)
    META_AUTO_SCRIPTING_API_EXTEND = (
        display_order, get_display_order, set_display_order,
        keys, values, items,
    )
    META_SCRIPTING_CONSTANTS = (DisplayOrderEnum,)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(BasePart)
    def _receive_edited_snapshot(self, submitted_data: Dict[str, Any], order: List[str] = None):
        super()._receive_edited_snapshot(submitted_data, order=order)

        self.clear()
        ordered_dict = submitted_data['_data']
        for x in ordered_dict:
            self[x] = ordered_dict[x]
        self.signals.sig_data_reset.emit()

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        # if legacy, data is a pickle so giving it to ordered dict will raise:
        dict_data = part_content[DpKeys.DICT]
        if ori_data.schema_version < OriSchemaEnum.version_2_1:
            # always pickled:
            ordered_data = pickle.loads(pickle_from_str(dict_data))

        else:
            # values pickled only when necessary, per part_content[DpKeys.PICKLED_KEYS]
            if ori_data.schema_version == OriSchemaEnum.version_3:
                # always repr'd
                ordered_data = OrderedDict(eval(dict_data))
            else:
                # always JSON
                ordered_data = OrderedDict(dict_data)
            self.__unpickle_ori_values(part_content, ordered_data)

        # copy the pairs into our own dict:
        self.clear()
        for x in ordered_data:
            self[x] = ordered_data[x]

        # etc:
        display_order = part_content.get(DpKeys.DISPLAY_ORDER)
        if display_order is not None:
            val = DisplayOrderEnum(display_order) if type(display_order) == int else DisplayOrderEnum[display_order]
            self.set_display_order(val)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)

        # JSON does not have ordered mappings so convert to pairs;
        # use list for each pair in case need to pickle some of the values:
        ori_dict_data = [[key, self.__dict__[key]] for key in self._Order]
        if context == OriContextEnum.save_load:
            pickled_keys = self.__get_ori_def_for_saving(ori_dict_data)
        else:
            pickled_keys = []

        data_part_ori_def = {
            DpKeys.DISPLAY_ORDER: self._display_order.name,
            DpKeys.PICKLED_KEYS: pickled_keys,
            DpKeys.DICT: ori_dict_data,
        }

        ori_def[CpKeys.CONTENT].update(data_part_ori_def)
        return ori_def

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):

        try:
            val = pickle.dumps(self.__get_as_ordered_dict())
        except:
            # At least one of the values is bad - cannot be pickled.
            # yes, need to loop over every value and test; first clone the data
            ori_data = self.__get_as_ordered_dict()
            for key, value in ori_data.items():
                safe_val, is_pickle_successful = get_pickled_str(value, SaveErrorLocationEnum.data_part)
                if not is_pickle_successful:
                    ori_data[key] = safe_val

            # At this point, the pickle has to succeed because every cell has been checked.
            val = pickle.dumps(ori_data)

        md5_data = md5(val).digest()

        snapshot.update({
            DpKeys.DICT: md5_data,
            DpKeys.DISPLAY_ORDER: self._display_order
        })

    @override(IOriSerializable)
    def _check_ori_diffs(self, other_ori: Decl.DataPart, diffs: Dict[str, Any], tol_float: float):
        BasePart._check_ori_diffs(self, other_ori, diffs, tol_float)

        # keys added or missing
        keys = set(self.keys())
        other_keys = set(other_ori.keys())
        other_missing_keys = keys - other_keys
        other_adds_keys = other_keys - keys
        if other_missing_keys:
            diffs['missing_keys'] = list(other_missing_keys)
        if other_adds_keys:
            diffs['added_keys'] = list(other_adds_keys)

        # values of common keys
        for key in keys.intersection(other_keys):
            if self[key] != other_ori[key]:
                if isinstance(self[key], (list, tuple)):
                    for index, (item, other_item) in enumerate(zip(self[key], other_ori[key])):
                        diff = check_diff_val(item, other_item, tol_float)
                        if diff is not None:
                            diffs['{}[{}]'.format(key, index)] = diff
                else:
                    diff = check_diff_val(self[key], other_ori[key], tol_float)
                    if diff is not None:
                        diffs[key] = diff

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_as_ordered_dict(self) -> OrderedDict:
        """
        Get the key-value pairs of this part in OrderedDict format.
        :returns: The key-value in an OrderedDict.
        """
        # Note: The str() could call the items(), resulting calling this function in the super class.
        # At that point, the self._Order may not exist. So, we have to check the existence of the self._Order
        ordered_data = OrderedDict()
        if "_Order" in self.__dict__:
            for x in self._Order:
                ordered_data[x] = self.__dict__[x]

        return ordered_data

    def __unpickle_ori_values(self, part_content: Dict[Any, Any], ordered_data: OrderedDict):
        """
        Uses each key in the part_content[DpKeys.PICKLED_KEYS] to locate the entry in the ordered_data and converts
        the pickled str to un-pickled object.
        :param part_content: The dict that provides for the key info
        :param ordered_data: The dict of input and output. It contains the pickled values and stores the results of 
        un-pickled values.
        """
        if part_content.get(DpKeys.PICKLED_KEYS) is None:
            return

        for key in part_content[DpKeys.PICKLED_KEYS]:
            pickled_data = ordered_data[key]
            unpickled = pickle.loads(pickle_from_str(pickled_data))
            ordered_data[key] = unpickled

    def __get_ori_def_for_saving(self, ori_dict_data: List[Tuple[str, Any]]) -> List[str]:
        """
        Prepares data for saving. If some values are found that are not jsonable, they are replaced in ori_dict_data.
        :param ori_dict_data: the data structure to prepare
        :return: list of keys for which value was pickled in ori_dict_data
        """
        # quickly determine if any cells will need pickling:
        needs_pickling, unjsoned_data = check_needs_pickling(ori_dict_data)
        if not needs_pickling:
            return []

        pickled_keys = []

        def pickle_value(orig_value: Any, value_id: str) -> bytes:
            safe_val, is_pickled = get_pickled_str(orig_value, SaveErrorLocationEnum.data_part)
            if is_pickled:
                pickled_keys.append(value_id)
            return safe_val

        if unjsoned_data is None:
            # it could not even be json'd, find the culprits and pickle them
            for index, (key, value) in enumerate(ori_dict_data):
                val_needs_pickling, unj_value = check_needs_pickling(value)
                if val_needs_pickling:
                    ori_dict_data[index] = [key, pickle_value(value, key)]
        else:
            # was json'd, but any values that contained dicts that had non-string keys will end up with string keys!
            # find the values that do not match unjsoned value:
            for index, (orig_pair, unj_pair) in enumerate(zip(ori_dict_data, unjsoned_data)):
                key = orig_pair[0]
                assert key == unj_pair[0]
                if orig_pair[1] != unj_pair[1]:
                    ori_dict_data[index] = [key, pickle_value(orig_pair[1], key)]

        return pickled_keys


# Add this part to the global part type/class lookup dictionary
register_new_part_type(DataPart, DpKeys.PART_TYPE_DATA)
