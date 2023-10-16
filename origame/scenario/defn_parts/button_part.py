# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the ButtonPart class and the functionality that supports the part as
a building block for the Origame application.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum, unique

# [2. third-party]

# [3. local]
from ...core import override, BridgeSignal, BridgeEmitter
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ..ori import IOriSerializable, OriContextEnum, OriScenData, JsonObj
from ..ori import OriCommonPartKeys as CpKeys, OriButtonPartKeys as BtnKeys

from .part_types_info import register_new_part_type
from .base_part import BasePart
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
    'ButtonPart',
    'ButtonStateEnum',
    'ButtonActionEnum',
    'ButtonTriggerStyleEnum'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ButtonTargetNotCallable(Exception):
    def __init__(self, link_name: str, message: str):
        super().__init__("Button could not trigger part linked via '{}': {}".format(link_name, message))


class ButtonStateEnum(IntEnum):
    released, pressed = range(2)


@unique
class ButtonActionEnum(IntEnum):
    """
    This class represents the possible actions that an instance of a Button Part can be configured to.
    """
    momentary = 0  # Press-and-release action
    toggle = 1  # Remains in state until toggled to alternate state.


@unique
class ButtonTriggerStyleEnum(IntEnum):
    """
    This class represents the button trigger style possibilities for a Button Part.
    """
    on_press = 0  # Event raised on button press
    on_release = 1  # Event raised on button release
    on_press_and_release = 2  # Events raised on both press and release


class ButtonPart(BasePart):
    """
    This class defines the functionality required to support an Origame Button Part.
    """

    class Signals(BridgeEmitter):
        # Supported signals
        sig_button_action_changed = BridgeSignal(int)  # ButtonActionEnum
        sig_button_state_changed = BridgeSignal(int)  # ButtonStateEnum
        sig_rotation_2d_pressed_changed = BridgeSignal(float)
        sig_rotation_2d_released_changed = BridgeSignal(float)
        sig_image_pressed_path_changed = BridgeSignal(str)
        sig_image_released_path_changed = BridgeSignal(str)

    CAN_BE_LINK_SOURCE = True
    DEFAULT_VISUAL_SIZE = dict(width=7.0, height=8.1)
    PART_TYPE_NAME = "button"
    DESCRIPTION = """\
        Buttons are used to trigger the immediate execution of the function part they are linked to. A button
        can be configured as either 'momentary' or 'toggle' style, and to trigger for 'on' events, 'off' events, or
        both. Button images can be customized.

        Double-click the title bar to edit the button.

        Click the button image to activate the button.
    """

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        """
        :param parent: The parent Actor Part to which this instance belongs.
        :param name: The name to be assigned to this instance.
        :param position: The coordinates of this instance within the parent Actor Part view.
        """
        BasePart.__init__(self, parent, name=name, position=position)
        self.signals = ButtonPart.Signals()

        self.__button_action = ButtonActionEnum.momentary
        self.__button_trigger_style = ButtonTriggerStyleEnum.on_press
        self.__image_id_pressed = None
        self.__image_id_released = None
        self.__rotation_2d_pressed = 0
        self.__rotation_2d_released = 0
        self._state = ButtonStateEnum.released

    # John TODO Build 3:  Image related functions are duplicating a similar API implemented in Actor Part.
    #    Suggestion: Same API as in Actor Part except Button handles two images instead of one. Could refactor to have
    #    and Image class that can be instantiated more than once, and each image would have the same API.
    def get_image_id_pressed(self) -> int:
        """
        This function returns the id of the 'pressed' image associated with this Button part instance.

        :return: This instance's 'pressed' image ID.
        """
        return self.__image_id_pressed

    def get_image_id_released(self) -> int:
        """
        This function returns the id of the 'released' image associated with this Button part instance.

        :return: This instance's 'released' image ID.
        """
        return self.__image_id_released

    def set_image_id_pressed(self, image_id: int):
        """
        This function sets the Button's 'pressed' image ID. The ID corresponds to an already loaded image file. The
        image dictionary's reference count is updated for the image.

        :param image_id: The ID of the 'pressed' image to be associated with this Button part instance.
        """

        if image_id is None and self.__image_id_pressed is not None:
            self.remove_image_pressed()

        elif image_id != self.__image_id_pressed:
            orig_image_id = self.__image_id_pressed

            image_dict = self._shared_scenario_state.image_dictionary
            try:
                image_dict.add_image_reference(image_id)
                self.__image_id_pressed = image_id
            except KeyError as e:
                log.error("Part: {} unable to set part image. Error: {} Part will assume default image.",
                          str(self), str(e))
                self.__image_id_pressed = None

            if orig_image_id is not None:
                try:
                    image_dict.subtract_image_reference(image_id=orig_image_id)
                except KeyError as e:
                    log.error("Part: {} unable to remove its reference to an image from the Image Dictionary. "
                              "Error: {}", str(self), str(e))

            if self._anim_mode_shared:
                self.signals.sig_image_pressed_path_changed.emit(self.get_image_pressed_path())

    def set_image_id_released(self, image_id: int):
        """
        This function sets the Button's 'released' image ID. The ID corresponds to an already loaded image file. The
        image dictionary's reference count is updated for the image.

        :param image_id: The ID of the 'released' image to be associated with this Button part instance.
        """

        if image_id is None and self.__image_id_released is not None:
            self.remove_image_released()

        elif image_id != self.__image_id_released:
            orig_image_id = self.__image_id_released

            image_dict = self._shared_scenario_state.image_dictionary
            try:
                image_dict.add_image_reference(image_id)
                self.__image_id_released = image_id
            except KeyError as e:
                log.error("Part: {} unable to set part image. Error: {} Part will assume default image.",
                          str(self), str(e))
                self.__image_id_released = None

            if orig_image_id is not None:
                try:
                    image_dict.subtract_image_reference(image_id=orig_image_id)
                except KeyError as e:
                    log.error("Part: {} unable to remove its reference to an image from the Image Dictionary. "
                              "Error: {}", str(self), str(e))

            if self._anim_mode_shared:
                self.signals.sig_image_released_path_changed.emit(self.get_image_released_path())

    def set_image_pressed_path(self, image_path: str):
        """
        This function sets the 'pressed' image that is to be associated with the current Button part instance. The path
        is translated into an image ID by the image dictionary and the image ID is stored by this instance.
        :param image_path: The image file path of the image assocated with this instance.
        """
        if image_path is None and self.__image_id_pressed is not None:
            self.remove_image_pressed()
        elif image_path is None and self.__image_id_pressed is None:
            pass
        else:
            image_dict = self._shared_scenario_state.image_dictionary
            self.__image_id_pressed = image_dict.new_image(image_path)

        if self._anim_mode_shared:
            # We don't check if the value is actually changed in order to signal here, because the signal is needed
            # in case the button action has been changed and the use wants to use the same image for both types.
            # This may not happen because different images are usually used for different button types.
            self.signals.sig_image_pressed_path_changed.emit(self.get_image_pressed_path())

    def set_image_released_path(self, image_path: str):
        """
        This function sets the 'released' image that is to be associated with the current Button part instance. The path
        is translated into an image ID by the image dictionary and the image ID is stored by this instance.
        :param image_path: The image file path of the image assocated with this instance.
        """
        if image_path is None and self.__image_id_released is not None:
            self.remove_image_released()
        elif image_path is None and self.__image_id_released is None:
            pass
        else:
            image_dict = self._shared_scenario_state.image_dictionary
            self.__image_id_released = image_dict.new_image(image_path)

        if self._anim_mode_shared:
            # We don't check if the value is actually changed in order to signal here, because the signal is needed
            # in case the button action has been changed and the use wants to use the same image for both types.
            # This may not happen because different images are usually used for different button types.
            self.signals.sig_image_released_path_changed.emit(self.get_image_released_path())

    def get_image_pressed_path(self) -> Either[str, None]:
        """
        This function returns the image path corresponding to the 'pressed' image ID stored by this part or None if
        no custom image has been assigned to the part..
        :return: The path to the associated image file, or None.
        """

        image_path = None

        if self.__image_id_pressed is None:
            return None
        image_dict = self._shared_scenario_state.image_dictionary

        try:
            image_path = image_dict.get_image_path(self.__image_id_pressed)
        except Exception as e:
            log.error("Part: {} is unable to retrieve the path of its associated custom image from the Image "
                      "Dictionary. Error: {}", str(self), str(e))
            return "Unresolved image path"

        return image_path

    def get_image_released_path(self) -> str:
        """
        This function returns the image path corresponding to the 'released' image ID stored by this part. For smooth
        operation, the has_image_released() function should be called prior to calling this function.
        :return: The path to the associated image file.
        """

        image_path = None

        if self.__image_id_released is None:
            return None
        image_dict = self._shared_scenario_state.image_dictionary
        try:
            image_path = image_dict.get_image_path(self.__image_id_released)
        except Exception as e:
            log.error("Part: {} is unable to retrieve the path of its associated custom image from the Image "
                      "Dictionary. Error: {}", str(self), str(e))
            return "Unresolved image path"

        return image_path

    def remove_image_pressed(self):
        """
        This function clears the __image_id_pressed value associated with this Button part instance causing the image
        associated with this Button part instance to be reverted to the default image.
        """
        if self.__image_id_pressed is not None:
            image_dict = self._shared_scenario_state.image_dictionary
            try:
                image_dict.subtract_image_reference(image_id=self.__image_id_pressed)
            except KeyError as e:
                log.error("Part: {} unable to remove its reference to an image from the Image Dictionary. "
                          "Error: {}", str(self), str(e))

            self.__image_id_pressed = None

            if self._anim_mode_shared:
                self.signals.sig_image_pressed_path_changed.emit(None)

    def remove_image_released(self):
        """
        This function clears the __image_id_released value associated with this Button part instance causing the image
        associated with this Button part instance to be reverted to the default image.
        """
        if self.__image_id_released is not None:
            image_dict = self._shared_scenario_state.image_dictionary
            try:
                image_dict.subtract_image_reference(image_id=self.__image_id_released)
            except KeyError as e:
                log.error("Part: {} unable to remove its reference to an image from the Image Dictionary. "
                          "Error: {}", str(self), str(e))

            self.__image_id_released = None

            if self._anim_mode_shared:
                self.signals.sig_image_released_path_changed.emit(None)

    def get_state(self) -> ButtonStateEnum:
        """
        Get the state of the button.
        :return: The state of the button.
        """
        return self._state

    def set_state(self, state: ButtonStateEnum):
        """
        Set the state of the button.
        :param: The new state of the button.
        """
        self._state = state
        if self._anim_mode_shared:
            self.signals.sig_button_state_changed.emit(self._state.value)

    def get_button_action(self) -> ButtonActionEnum:
        """
        This function returns the button action.
        """
        return self.__button_action

    def set_button_action(self, action: ButtonActionEnum):
        """
        Set the button's functional action.
        """
        if self.__button_action != action:
            self.__button_action = action
            if self._anim_mode_shared:
                self.signals.sig_button_action_changed.emit(self.__button_action.value)
            # Design decisions:
            # When the button action changes, we set the button state to its default, i.e., released.
            self.set_state(ButtonStateEnum.released)

    def get_button_trigger_style(self) -> ButtonTriggerStyleEnum:
        """
        This function returns the button trigger style.
        """
        return self.__button_trigger_style

    def set_button_trigger_style(self, trigger_style: ButtonTriggerStyleEnum):
        """
        This function sets the button's trigger style.
        """
        if self.__button_trigger_style != trigger_style:
            self.__button_trigger_style = trigger_style

    def get_rotation_2d_pressed(self) -> float:
        """
        This function returns the rotation angle of the button part in the 2D view.
        """
        return self.__rotation_2d_pressed

    def set_rotation_2d_pressed(self, rotation: float):
        """
        This function sets the rotation angle of the button part in the view.
        """
        if self.__rotation_2d_pressed != rotation:
            self.__rotation_2d_pressed = rotation

            if self._anim_mode_shared:
                self.signals.sig_rotation_2d_pressed_changed.emit(self.__rotation_2d_pressed)

    def get_rotation_2d_released(self) -> float:
        """
        This function returns the rotation angle of the button part in the 2D view.
        """
        return self.__rotation_2d_released

    def set_rotation_2d_released(self, rotation: float):
        """
        This function sets the rotation angle of the button part in the view.
        """
        if self.__rotation_2d_released != rotation:
            self.__rotation_2d_released = rotation

            if self._anim_mode_shared:
                self.signals.sig_rotation_2d_released_changed.emit(self.__rotation_2d_released)

    def on_user_press(self):
        """
        Method called when a user clicks on a Button Part.
        """
        current_state = self._state

        if self.__button_action == ButtonActionEnum.momentary:
            if self._state == ButtonStateEnum.released:
                self.set_state(ButtonStateEnum.pressed)
        elif self.__button_action == ButtonActionEnum.toggle:
            if self._state == ButtonStateEnum.pressed:
                self.set_state(ButtonStateEnum.released)
            else:
                self.set_state(ButtonStateEnum.pressed)

        if current_state != self._state:
            self.__trigger_linked_parts()

    def on_user_release(self):
        """
        Method called when a user releases the mouse on a Button Part.
        """
        if self.__button_action == ButtonActionEnum.momentary:
            if self._state == ButtonStateEnum.pressed:
                self.set_state(ButtonStateEnum.released)
                self.__trigger_linked_parts()

    @override(BasePart)
    def on_removing_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        super().on_removing_from_scenario(scen_data, restorable=restorable)

        image_released_path = self.get_image_released_path()
        self.remove_image_released()

        image_pressed_path = self.get_image_pressed_path()
        self.remove_image_pressed()

        if restorable:
            scen_data[self].update(image_released_path=image_released_path, image_pressed_path=image_pressed_path)

    @override(BasePart)
    def on_restored_to_scenario(self, scen_data: Dict[BasePart, Any]):
        # Oliver TODO build 3: Revisit the design of this and preceding function to eliminate key name typo potential.
        restoration_info = scen_data[self]
        if 'image_released_path' in restoration_info:
            self.set_image_released_path(restoration_info['image_released_path'])
        if 'image_pressed_path' in restoration_info:
            self.set_image_pressed_path(restoration_info['image_pressed_path'])

        super().on_restored_to_scenario(scen_data)

    # --------------------------- instance PUBLIC properties ----------------------------

    button_action = property(get_button_action, set_button_action)
    button_trigger_style = property(get_button_trigger_style, set_button_trigger_style)
    rotation_2d_pressed = property(get_rotation_2d_pressed, set_rotation_2d_pressed)
    rotation_2d_released = property(get_rotation_2d_released, set_rotation_2d_released)
    image_id_pressed = property(get_image_id_pressed, set_image_id_pressed)
    image_id_released = property(get_image_id_released, set_image_id_released)
    image_path_pressed = property(get_image_pressed_path, set_image_pressed_path)
    image_path_released = property(get_image_released_path, set_image_released_path)
    state = property(get_state, set_state)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = (
        button_action,
        button_trigger_style,
        image_path_pressed, image_path_released,
        rotation_2d_pressed, rotation_2d_released,
        state
    )
    META_AUTO_SCRIPTING_API_EXTEND = META_AUTO_EDITING_API_EXTEND + (
        get_button_action, set_button_action,
        get_button_trigger_style, set_button_trigger_style,
        get_image_pressed_path, set_image_pressed_path,
        get_image_released_path, set_image_released_path,
        get_rotation_2d_pressed, set_rotation_2d_pressed,
        get_rotation_2d_released, set_rotation_2d_released,
        get_state, set_state
    )
    META_SCRIPTING_CONSTANTS = (ButtonTriggerStyleEnum, ButtonActionEnum, ButtonStateEnum)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):
        BasePart._set_from_ori_impl(self, ori_data, context, **kwargs)

        part_content = ori_data[CpKeys.CONTENT]
        # Per BasePart._set_from_ori_impl() docstring, set via property.
        self.button_action = ButtonActionEnum[part_content[BtnKeys.BUTTON_ACTION].lower()]
        self.button_trigger_style = ButtonTriggerStyleEnum[part_content[BtnKeys.BUTTON_TRIGGER_STYLE].lower()]
        # pressed and released are optional; the current state will be used if not specified
        self.rotation_2d_pressed = part_content.get(BtnKeys.ROTATION_2D_PRESSED, self.__rotation_2d_pressed)
        self.rotation_2d_released = part_content.get(BtnKeys.ROTATION_2D_RELEASED, self.__rotation_2d_released)
        self.state = ButtonStateEnum[part_content[BtnKeys.BUTTON_STATE].lower()]

        image_dict = self._shared_scenario_state.image_dictionary

        if part_content.get(BtnKeys.IMAGE_ID_PRESSED) is not None:
            if context == OriContextEnum.export:
                # During export operation, image pathname was stored in place of image ID in ORI data to facilitate
                # replication of image dictionary (which is necessary during export).
                self.image_path_pressed = part_content[BtnKeys.IMAGE_ID_PRESSED]  # updates image dictionary
            else:
                self.__image_id_pressed = part_content[BtnKeys.IMAGE_ID_PRESSED]
                self.__image_id_pressed += image_dict.get_image_id_offset()
                try:
                    image_path = image_dict.get_image_path(self.__image_id_pressed)
                    image_dict.add_image_reference(self.__image_id_pressed)
                    if self._anim_mode_shared:
                        self.signals.sig_image_pressed_path_changed.emit(image_path)
                except Exception as e:
                    log.error("Part: {} is unable to retrieve the path of its associated custom image from the Image "
                              "Dictionary. Error: {}", str(self), str(e))
        else:
            if self._anim_mode_shared:
                self.signals.sig_image_pressed_path_changed.emit(None)

        if part_content.get(BtnKeys.IMAGE_ID_RELEASED) is not None:
            if context == OriContextEnum.export:
                # During export operation, image pathname was stored in place of image ID in ORI data to facilitate
                # replication of image dictionary (which is necessary during export).
                self.image_path_released = part_content[BtnKeys.IMAGE_ID_RELEASED]  # updates image dictionary
            else:
                self.__image_id_released = part_content[BtnKeys.IMAGE_ID_RELEASED]
                self.__image_id_released += image_dict.get_image_id_offset()
                try:
                    image_path = image_dict.get_image_path(self.__image_id_released)
                    image_dict.add_image_reference(self.__image_id_released)
                    if self._anim_mode_shared:
                        self.signals.sig_image_released_path_changed.emit(image_path)
                except Exception as e:
                    log.error("Part: {} is unable to retrieve the path of its associated custom image from the Image "
                              "Dictionary. Error: {}", str(self), str(e))
        else:
            if self._anim_mode_shared:
                self.signals.sig_image_released_path_changed.emit(None)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:

        ori_def = BasePart._get_ori_def_impl(self, context, **kwargs)

        button_ori_def = {
            BtnKeys.BUTTON_ACTION: self.__button_action.name,
            BtnKeys.BUTTON_STATE: self._state.name,
            BtnKeys.BUTTON_TRIGGER_STYLE: self.__button_trigger_style.name,
            BtnKeys.ROTATION_2D_PRESSED: self.__rotation_2d_pressed,
            BtnKeys.ROTATION_2D_RELEASED: self.__rotation_2d_released,
        }

        if context == OriContextEnum.export:
            # For an export, an new Image Dictionary instance needs to be populated. Capture image pathnames in the
            # ori data, instead of image IDs, to facilitate the task.
            if self.__image_id_pressed is not None:
                try:
                    button_ori_def[BtnKeys.IMAGE_ID_PRESSED] = \
                        self._shared_scenario_state.image_dictionary.get_image_path(self.__image_id_pressed)
                except Exception as e:
                    log.error("Part: {} is unable to retrieve the path of its associated custom image from the Image "
                              "Dictionary. Error: {}", str(self), str(e))
                    self.__image_id_pressed = None

            if self.__image_id_released is not None:
                try:
                    button_ori_def[BtnKeys.IMAGE_ID_RELEASED] = \
                        self._shared_scenario_state.image_dictionary.get_image_path(self.__image_id_released)
                except Exception as e:
                    log.error("Part: {} is unable to retrieve the path of its associated custom image from the Image "
                              "Dictionary. Error: {}", str(self), str(e))
                    self.__image_id_released = None
        else:
            button_ori_def[BtnKeys.IMAGE_ID_PRESSED] = self.__image_id_pressed
            button_ori_def[BtnKeys.IMAGE_ID_RELEASED] = self.__image_id_released

        ori_def[CpKeys.CONTENT].update(button_ori_def)
        return ori_def

    @override(BasePart)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        BasePart._get_ori_snapshot_local(self, snapshot, snapshot_slow)
        snapshot.update({
            BtnKeys.BUTTON_ACTION: self.__button_action,
            BtnKeys.BUTTON_STATE: self._state,
            BtnKeys.BUTTON_TRIGGER_STYLE: self.__button_trigger_style,
            BtnKeys.ROTATION_2D_PRESSED: self.__rotation_2d_pressed,
            BtnKeys.ROTATION_2D_RELEASED: self.__rotation_2d_released,
            BtnKeys.IMAGE_ID_PRESSED: self.__image_id_pressed,
            BtnKeys.IMAGE_ID_RELEASED: self.__image_id_released
        })

    def __trigger_linked_parts(self):
        """
        Method used to trigger the parts that this instance of the Button Part is linked to.
        """
        if self._state == ButtonStateEnum.pressed:
            if (self.__button_trigger_style == ButtonTriggerStyleEnum.on_press or
                        self.__button_trigger_style == ButtonTriggerStyleEnum.on_press_and_release):
                self.__trigger()

        elif self._state == ButtonStateEnum.released:
            if (self.__button_trigger_style == ButtonTriggerStyleEnum.on_release or
                        self.__button_trigger_style == ButtonTriggerStyleEnum.on_press_and_release):
                self.__trigger()

    def __trigger(self):
        """
        Accessory method to trigger the parts that this instance of the Button Part is linked to.
        """
        for link in self.part_frame.outgoing_links:
            if 'button_state' in link.target_part_frame.part.parameters:
                link.target_part_frame.part(button_state=self._state)
            else:
                link.target_part_frame.part()


# Add this part to the global part type/class lookup dictionary
register_new_part_type(ButtonPart, BtnKeys.PART_TYPE_BUTTON)
