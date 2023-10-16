# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains the VariablePart class definition and supporting code.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import json
import logging
import pickle
from hashlib import md5

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter
from ...core.utils import get_verified_eval
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream
from ...core.typing import AnnotationDeclarations
from ...core.utils import get_verified_repr

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj, OriSchemaEnum, SaveErrorLocationEnum
from ..ori import get_pickled_str, pickle_from_str, check_needs_pickling
from ..ori import OriCommonPartKeys as CpKeys
from ..ori import OriVariablePartKeys as VpKeys

from .base_part import BasePart
from .actor_part import ActorPart
from .common import Position
from .part_types_info import register_new_part_type

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    "VariablePart"
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class VariablePart(BasePart):
    """
    This class represents a scenario part that proxies a Python object. Any Python object can be proxied.
    This scenario part can be accessed from linked scripts as though it is a value.
    """

    class Signals(BridgeEmitter):
        sig_editable_str_changed = BridgeSignal(str)
        sig_obj_changed = BridgeSignal(object)

    DEFAULT_VISUAL_SIZE = dict(width=8.0, height=3.1)
    PART_TYPE_NAME = "variable"
    DESCRIPTION = """\
        Use this part to store any python variable.

        Double-click to set the value of the variable.
    """

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The Actor Part to which this part belongs.
        :param name: Name for this instance of the VariablePart.
        :param position: A position to be assigned to the newly instantiated default VariablePart. This argument
            is only required when the ori_def default (None) is used.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = VariablePart.Signals()

        self._editable_str = "None"
        self._value_obj = None

        self.__deep_value_mod_possible = False

    @override(BasePart)
    def on_exec_done(self):
        """
        If an inner element of the variable part is changed, the sig_obj_changed is emitted to give the variable part
        widget a chance to refresh its content. For that matter, any component that is interested in the inner changes
        of a variable part should connect to its sig_obj_changed.
        """
        if self.__deep_value_mod_possible:
            if self._anim_mode_shared:
                self.signals.sig_obj_changed.emit(self._value_obj)
        self.__deep_value_mod_possible = False

    def get_editable_str(self) -> str:
        """
        Get the raw string before it is evaluated.

        Get the string set by the editor. The string must pass eval() before it can come to the instance of this
        class. The "raw" means something like "2+3", not 5, which is the result of the eval("2+3").

        :returns: The raw string of the variable.
        """
        return self._editable_str

    def set_editable_str(self, editable_str: str):
        """
        Set the raw string by the editor.

        The string must pass eval() before it can come to the instance of this class.

        """
        if self._editable_str == editable_str:
            return

        obj_verified = get_verified_eval(editable_str)
        self._editable_str = editable_str
        if self._anim_mode_shared:
            self.signals.sig_editable_str_changed.emit(self._editable_str)

        self._value_obj = obj_verified
        if self._anim_mode_shared:
            self.signals.sig_obj_changed.emit(self._value_obj)

    def get_obj(self) -> object:
        """
        Get the object, which is usually set by the script.

        The editor can only display the repr() of the object, but cannot edit it graphically in a meaningful way.

        :returns: The object of the variable.
        """
        self.__deep_value_mod_possible = True
        return self._value_obj

    def set_obj(self, obj: Any):
        """
        Set the object, which is usually by the script

        The editor can only display the repr() of the object, but cannot edit it graphically in a meaningful way.

        """
        if isinstance(obj, BasePart):
            raise ValueError('Variable parts cannot reference scenario parts (like {})'.format(obj))

        self._value_obj = obj
        if self._anim_mode_shared:
            self.signals.sig_obj_changed.emit(self._value_obj)

        self._editable_str = repr(self._value_obj)
        if self._anim_mode_shared:
            self.signals.sig_editable_str_changed.emit(self._editable_str)

    @override(BasePart)
    def get_as_link_target_value(self) -> object:
        """
        Get the object in the variable part. This does not need further resolution because it cannot be another
        scenario part.
        :return: resolved part
        """
        return self.get_obj()

    @override(BasePart)
    def assign_from_object(self, value: not BasePart):
        """
        If this part is a link target, then setting the target sets the value object stored in this Variable part.
        The object cannot be another scenario part

        :param value: The new object to represent.

        Example: hub H linked to a node N, linked to a part P. Each one has a frame Hf, Nf, Pf respectively.
            H.N = 'string' will cause H.N.P to become a Variable Part, with frame Pf. The old parent of Pf will be
            destroyed.
        """
        self.set_obj(value)

    # --------------------------- instance PUBLIC properties ----------------------------

    editable_str = property(get_editable_str, set_editable_str)
    obj = property(get_obj, set_obj)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (editable_str,)
    META_AUTO_SCRIPTING_API_EXTEND = (obj, get_obj, set_obj)
    META_AUTO_ORI_DIFFING_API_EXTEND = (obj,)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]

        self._editable_str = part_content.get(VpKeys.EDITABLE_STR, "None")

        temp_obj = part_content[VpKeys.VALUE_OBJ]
        # to determine whether value_obj was pickled
        if ori_data.schema_version < OriSchemaEnum.version_2_1:
            # always used pickling
            self._value_obj = pickle.loads(pickle_from_str(temp_obj))

        else:
            # pickled only if necessary per per part_content[VpKeys.IS_PICKLED]:
            is_pickled = part_content.get(VpKeys.IS_PICKLED, False)
            if is_pickled:
                self._value_obj = pickle.loads(pickle_from_str(temp_obj))

            elif ori_data.schema_version == OriSchemaEnum.version_3:
                # version 3 attempted to repr the data
                try:
                    self._value_obj = eval(temp_obj)
                except:
                    # the value was not picklable originally and was replaced by an error message string, use it:
                    self._value_obj = temp_obj

            else:
                # if not pickled then it's pure data:
                self._value_obj = temp_obj

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)

        if context == OriContextEnum.save_load:
            editable_str, is_pickled, safe_value = self.__get_ori_def_for_saving()
        else:
            editable_str, is_pickled, safe_value = self._editable_str, False, self._value_obj

        var_ori_def = {
            VpKeys.EDITABLE_STR: editable_str,
            VpKeys.IS_PICKLED: is_pickled,
            VpKeys.VALUE_OBJ: safe_value
        }

        ori_def[CpKeys.CONTENT].update(var_ori_def)
        return ori_def

    def __get_ori_def_for_saving(self):
        editable_str = self._editable_str
        needs_pickling, _ = check_needs_pickling(self._value_obj)
        if needs_pickling:
            safe_value, is_pickled = get_pickled_str(self._value_obj, SaveErrorLocationEnum.variable_part)
            if not is_pickled:
                editable_str = safe_value
        else:
            safe_value, is_pickled = self._value_obj, False
        return editable_str, is_pickled, safe_value

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        safe_val, _ = get_pickled_str(self._value_obj, SaveErrorLocationEnum.variable_part)
        val = pickle.dumps(safe_val)

        md5_var_obj = md5(val).digest()
        snapshot.update({
            VpKeys.EDITABLE_STR: self._editable_str,
            VpKeys.VALUE_OBJ: md5_var_obj,
        })


# Add this part to the global part type/class lookup dictionary
register_new_part_type(VariablePart, VpKeys.PART_TYPE_VARIABLE)
