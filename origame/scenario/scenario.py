# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Scenario module containing Scenario, ScenarioDefinition and SharedScenarioState classes

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import random
from pathlib import Path
from enum import IntEnum, Enum
import pickle
from collections import defaultdict
from textwrap import indent

# [2. third-party]

# [3. local]
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType
from ..core import override, BridgeEmitter, BridgeSignal
from ..core.typing import AnnotationDeclarations

from .batch_data import BatchDataMgr, DataPathTypesEnum
from .alerts import IScenAlertSource, ScenAlertLevelEnum
from .part_execs import PyDebugger, PyScenarioImportsManager
from .event_queue import EventQueue
from .sim_controller import SimController, SimStatesEnum
from .embedded_db import EmbeddedDatabase
from .defn_parts import ActorPart, BasePart, SimControllerReaderProxy, SimControllerProxy
from .event_queue import EventQueue
from .ori import IOriSerializable, OriBaselineEnum, OriContextEnum, JsonObj, pickle_from_str, pickle_to_str
from .ori import OriScenarioDefKeys as SdKeys, OriImageDictionaryKeys as IdKeys
from .ori import OriScenarioKeys as SKeys, OriSchemaEnum, OriScenData
from .animation import SharedAnimationModeReader, AnimationMode

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'ScenarioDefinition',
    'EventQueue',
    'SimController',
    'Scenario',
    'ImageDictionary',
    'UnresolvedImageError',
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ErrorCatEnum(Enum):
    mismatched, out_of_sync = range(2)

class Decl(AnnotationDeclarations):
    SharedScenarioState = 'SharedScenarioState'


class UnresolvedImageError(Exception):
    """
    This error is used to raise an error when an image cannot be resolved by either its ID or its path.
    """
    pass


class ImageDictionary(IOriSerializable):
    """
    This class represents the image dictionary for the scenario. It is used to track images loaded into the scenario.
    The images themselves are not stored in this instance, but image IDs and the number of parts referencing each image,
    and each image's source path are stored herein.

    This class implements the IOriSerializable interface to persist image IDs and associated paths for the scenario.
    The interface implementation does not include scenario change-related function implementations because changes
    to image references or new images added to the scenario would be reflected in the change status of individual
    parts using the images.
    """

    PATH = 'path'  # an image dictionary key
    COUNT = 'count'  # an image dictionary key

    def __init__(self):

        IOriSerializable.__init__(self)

        self.__images = {}  # A dict of dicts keyed by image id. The sub-dicts contain an image path and reference count.
        self.__next_image_id = 0  # The next available image ID.
        self.__image_id_offset = 0  # An offset value added to image IDs of imported scenarios to prevent ID clashes.

    def new_image(self, path: str) -> int:
        """
        This function creates a record of a new image in the dictionary based on the specified path. If the
        path, or even just the filename, already exists in the dictionary, a new entry is not made, the ID of the
        existing image is returned, its reference count is increased by one, and the occurrence is logged.

        :param path: The file system path to the new image.
        :return: The unique ID of the new image.
        :raises FileNotFoundError: Raised if an image path can't be found (on file system) while being resolved.
        :raises RuntimeError: Raised if an infinite loop is encountered while resolving an image path.

        """
        # Check if a file with that path has already been loaded.
        filename = Path(path).name
        res_input_path = str(Path(path).resolve())

        for image_id, image_data in self.__images.items():
            res_image_data_path = str(Path(image_data[self.PATH]))
            if res_image_data_path == res_input_path or Path(image_data[self.PATH]).name == filename:
                log.warning("An image with filename '{}' has already been loaded from "
                            "path '{}'. It will be referenced instead of loading the similarly named file from "
                            "path '{}'.", filename, res_image_data_path, res_input_path)
                image_data[self.COUNT] += 1
                return image_id

        # File at path is not recognized as having been loaded. Add it to dictionary.
        image_id = self.__next_image_id
        self.__next_image_id += 1

        self.__images[image_id] = {self.PATH: res_input_path, self.COUNT: 1}

        return image_id

    def add_image_reference(self, image_id: int):
        """
        This function increases the reference count by 1 for the specified image.
        :param image_id: The ID of the image whose reference count is to be increased.
        :raises KeyError: Raised if the image_id is not in the dictionary.
        """
        if self.__images.get(image_id):
            self.__images[image_id][self.COUNT] += 1
        else:
            raise KeyError("Invalid image ID. Attempting to add a reference to an image in the Image Dictionary "
                           "using an image ID ({}) that does not exist in the dictionary.".format(image_id))

    def subtract_image_reference(self, image_id: int):
        """
        This function decreases the reference count by 1 for the specified image.
        :param image_id: The ID of the image whose reference count is to be decreased.
        :raises KeyError: Raised if the specified image_id does not exist in the dictionary.
        """
        if self.__images.get(image_id):
            self.__images[image_id][self.COUNT] -= 1
        else:
            raise KeyError("Invalid image ID. Trying to remove a reference to an image in the Image Dictionary "
                           "but an image with the specified ID ({}) does not exist in the "
                           "dictionary.".format(image_id))

        if self.__images[image_id][self.COUNT] <= 0:
            del self.__images[image_id]

    def get_image_path(self, image_id: int) -> str:
        """
        This function returns the file system path for the specified image.
        :param image_id: The ID of the image.
        :return: The filesystem path.
        :raises UnresolvedImageError: Raised if the image_id does not exist in the dictionary, or if the image file
            at the path resolved from the image ID does not exist.
        """
        if self.__images.get(image_id):
            return self.__images[image_id][self.PATH]
        else:
            raise UnresolvedImageError("Invalid image ID. The Image Dictionary is being queried for an image with ID "
                                       "({}) which does not exist in the dictionary.".format(image_id))

    def set_image_id_offset(self):
        """
        This function calculates and sets an image ID offset value. The offset is equal to the maximum image ID
        value in the dictionary plus 1. The offset is applied to the image IDs of IMPORTED scenarios to prevent
        ID clashes between the existing scenario and the imported scenario. Once a scenario import is complete, the
        offset value should be reset to 0 by calling reset_import_image_id_offset().
        """
        if len(self.__images) > 0:
            self.__image_id_offset = max(int(k) for k in self.__images.keys()) + 1
        else:
            self.__image_id_offset = 0

    def reset_image_id_offset(self):
        """
        This function resets the image ID offset value to zero. This function should be called when the import of a
        scenario is complete.
        """
        self.__image_id_offset = 0

    def get_image_id_offset(self):
        """
        This function returns the current value of the image ID offset.
        """
        return self.__image_id_offset

    def import_image_dict(self, imported_dict_ori: {}):
        """
        This function adds the image dictionary info from an imported scenario to the existing image dictionary.
        The image IDs of the imported image dictionary are offset to avoid ID clashes between the original and
        imported scenario.
        :param imported_dict_ori: The ORI data structure describing the image dictionary of the imported scenario.
        """

        if imported_dict_ori and len(imported_dict_ori) > 0:
            for image_id, image_path in imported_dict_ori.items():
                image_id_as_int = int(image_id)
                image_id_as_int += self.__image_id_offset
                image_data = {
                    self.PATH: image_path,
                    self.COUNT: 0
                }

                self.__images[image_id_as_int] = image_data
            self.__next_image_id = image_id_as_int + 1

    def update_image_paths(self, updated_dict_ori: {}):
        """
        This function updates the image dictionary image paths with those of the input image dictionary.
        This function is called when a scenario is saved to ensure that the in-memory image dictionary image
        paths are consistent with the image dictionary saved to the scenario .ori file because image paths can be
        modified during the save operation.
        The image IDs of the input image dictionary are expected to be the same as those in the current
        dictionary. Image counts in the current dictionary remain unchanged.
        :param updated_dict_ori: The ORI data structure describing the updated image dictionary.
        """

        assert len(self.__images) == len(updated_dict_ori)

        if updated_dict_ori and len(updated_dict_ori) > 0:
            for image_id, image_path in updated_dict_ori.items():
                image_id_as_int = int(image_id)
                self.__images[image_id_as_int][IdKeys.PATH] = image_path

    def clean_up(self):
        """
        This function iterates through the image dictionary and deletes any image entries with reference count equal
        to 0 (meaning they are unreferenced by the scenario).
        """
        cleanup_list = []
        for image_id, image_data in self.__images.items():
            if self.__images[image_id][self.COUNT] == 0:
                cleanup_list.append(image_id)
        for image_id in cleanup_list:
            del self.__images[image_id]

    # --------------------------- instance PUBLIC properties ----------------------------

    image_id_offset = property(get_image_id_offset)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _ori_id(self) -> str:
        return 'Scenario Image Dictionary'

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):

        assert ori_data

        self.__images = {}
        self.__next_image_id = 0

        for image_id, path in ori_data.items():
            image_data = {
                self.PATH: path,
                self.COUNT: 0
            }
            self.__images[int(image_id)] = image_data

        # Set the next available ID to be 1 greater than the maximum ID loaded.
        self.__next_image_id = max(int(k) for k in self.__images.keys()) + 1

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        return self.__get_ori_def_local()

    @override(IOriSerializable)
    def _get_ori_snapshot_local(self, snapshot: JsonObj, snapshot_slow: JsonObj):
        snapshot.update(self.__get_ori_def_local())

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __get_ori_def_local(self) -> Dict[str, Any]:
        return {str(image_id): image_info[self.PATH] for image_id, image_info in self.__images.items()}


class SearchingStateEnum(IntEnum):
    idle, in_progress, cancelled = range(3)


class SharedScenarioState:
    """
    Provide a central location for objects that are shared between the scenario definition components and
    the simulation control. This includes:

    - scenario sim controller (which has the sim event queue and sim time)
    - sim controller proxy to be shared by all scripts
    - integrated database
    - history etc

    Note: the attributes of a class instance will not change for lifetime of a Scenario, so they can be safely
    cached locally in various scenario parts.
    """

    class Signals(BridgeEmitter):
        sig_search_progress = BridgeSignal(str)
        sig_search_hit = BridgeSignal(BasePart, list)  # List[str]
        sig_scenario_path_changed = BridgeSignal(str) # whenever path to scenario changes (save-as, New, Load)

    def __init__(self, sim_controller: SimController, anim_reader: SharedAnimationModeReader,
                 image_dict: ImageDictionary = None, embedded_db: EmbeddedDatabase = None):
        """
        :param sim_controller: the SimController instance for the scenario, for scenario parts that need to
            access the simulation state (event queue, replication ID, etc) or even change it (animation setting,
            etc)
        :param anim_reader: the animation mode reader for the scenario, for scenario parts that need to read
            the mode
        :param image_dict: the image dictionary that maps image IDs to file paths and tracks image reference counts.
        :param embedded_db: which embedded database to share amongst all scenario parts
        """
        self.signals = SharedScenarioState.Signals()

        self.__scen_filepath = None  # needed so scripts have access to scenario file path

        self.sim_controller = sim_controller
        self.animation_mode_reader = anim_reader
        self.sim_controller_scripting_proxy = SimControllerProxy(sim_controller)
        self.sim_controller_scripting_proxy_ro = SimControllerReaderProxy(sim_controller)

        self.scen_script_imports_mgr = PyScenarioImportsManager()
        self.batch_data_mgr = BatchDataMgr(self.scen_folder_path, file_type=DataPathTypesEnum.scen_folder)
        self.batch_data_mgr._create_replic_data_store(sim_controller)

        self.embedded_db = embedded_db
        self.image_dictionary = image_dict

        self.__search_state = SearchingStateEnum.idle

    @property
    def scen_folder_path(self) -> Optional[Path]:
        """The folder containing scenario file, or None if scenario not loaded from a file"""
        return None if self.__scen_filepath is None else self.__scen_filepath.parent

    def get_scen_filepath(self) -> Path:
        return self.__scen_filepath

    def set_scen_filepath(self, new_path: PathType):
        self.__scen_filepath = None if new_path is None else Path(new_path)
        self.batch_data_mgr.set_data_path(self.scen_folder_path, file_type=DataPathTypesEnum.scen_folder)
        self.signals.sig_scenario_path_changed.emit(str(new_path))

    def start_search(self):
        """
        Must be called before any of the other search methods are called, to indicate that a search is being
        started on an actor
        """
        self.__search_state = SearchingStateEnum.in_progress

    def update_search_progress(self, part_path: str):
        """
        The search engine calls this to emit progress signal.
        :param part_path: The path of the part that is being search on.
        """
        assert self.__search_state == SearchingStateEnum.in_progress
        self.signals.sig_search_progress.emit(part_path)

    def add_search_result(self, part: BasePart, prop_names: List[str]):
        """
        The search engine calls this to emit search hit.
        :param part_path: The path of the part that matched search query.
        """
        if self.__search_state == SearchingStateEnum.in_progress:
            self.signals.sig_search_hit.emit(part, prop_names)

    def cancel_search(self):
        """Cancel an in-progress search: any children not already searched will be skipped."""
        assert self.__search_state in (SearchingStateEnum.in_progress, SearchingStateEnum.cancelled)
        self.__search_state = SearchingStateEnum.cancelled

    def is_search_in_progress(self) -> bool:
        """True if start_search() was called, and end_search() was not"""
        return self.__search_state == SearchingStateEnum.in_progress

    def is_search_cancelled(self) -> bool:
        """True if cancel_search() was called, and end_search() was not"""
        return self.__search_state == SearchingStateEnum.cancelled

    def end_search(self):
        """Mark in-progress search as done (due to completion or cancellation)"""
        assert self.__search_state in (SearchingStateEnum.in_progress, SearchingStateEnum.cancelled)
        self.__search_state = SearchingStateEnum.idle

    scen_filepath = property(get_scen_filepath)


class ScenarioDefinition(IOriSerializable, IScenAlertSource):
    """
    This class represents the Scenario Definition portion of an Origame scenario.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------

    _ORI_HAS_CHILDREN = True

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, shared_scenario_state: SharedScenarioState, alert_parent: IScenAlertSource=None):
        """
        The constructor converts the input ori data into an Origame Part hierarchy structure.
        :param bridge_parent: The parent class that provide BridgeEmitter functionality to this instance.
        :param shared_scenario_state: A container for scenario objects that are shared between this instance and
        the Sim Controller.
        """
        IOriSerializable.__init__(self)
        IScenAlertSource.__init__(self)

        self._name = "Default Scenario"
        self._shared_scenario_state = shared_scenario_state
        self._root_actor = ActorPart(self)
        self.__alert_parent = alert_parent

    def import_scenario(self, ori_data: OriScenData, dest_actor: ActorPart):
        """
        This function imports (adds) the specified .ori data dictionary into the specified Actor Part that is contained
        in the current scenario.
        :param ori_data: An .ori file data structure representing the imported scenario definition.
        :param dest_actor: An Actor Part in the current scenario into which the ori_data is to be loaded.
        :raises: UnsupportedPartTypeError See ActorPart.create_child_part_from_ori() documentation.
        """
        refs_map = {}
        dest_actor.create_child_part_from_ori(ori_data.get_sub_ori(SdKeys.ROOT_ACTOR),
                                              OriContextEnum.save_load,
                                              refs_map, resolve_links=True)

    def get_name(self) -> str:
        """
        Get the name of the Scenario Definition
        """
        return self._name

    def set_name(self, value: str):
        """
        Set the name of the Scenario Definition.
        :param value: Scenario Definition name.
        """
        self._name = value

    def get_root_actor(self) -> ActorPart:
        """
        Get the root Actor Part of the Scenario Definition
        """
        return self._root_actor

    def get_shared_scenario_state(self) -> SharedScenarioState:
        """Get the shared scenario data for the scenario that this definition belongs to"""
        return self._shared_scenario_state

    def search_parts(self, re_pattern: str) -> {BasePart: List[str]}:
        """
        Find all parts that have properties with string value that matches a pattern.
        :param re_pattern: pattern to match
        :return: dictionary where each key is the path through actor hierarchy, and value is a list of property names
            on the associated part
        """
        return self._root_actor.search_parts(re_pattern, new_search=True)

    def cancel_search(self):
        """
        Cancel a search that was started with search_parts(). Does nothing if not searching.
        """
        self._shared_scenario_state.cancel_search()

    def fix_invalid_linking(self):
        """Attempt to fix any linking issues in scenario, such as nodes with more than one outgoing link"""
        self._root_actor.fix_invalid_linking()

    def on_scenario_shutdown(self):
        """Called automatically when scenario is discarded"""
        self._root_actor.on_scenario_shutdown()

    def get_all_parts(self) -> Dict[int, BasePart]:
        """Get all the parts in this scenario in a dict keyed by part SESSION_ID"""
        dest = {}
        self._root_actor.get_all_descendants_by_id(dest)
        return dest

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    name = property(get_name, set_name)
    root_actor = property(get_root_actor)
    shared_scenario_state = property(get_shared_scenario_state)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _ori_id(self) -> str:
        return 'Scenario Definition'

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, refs_map: Dict[int, BasePart],
                           **kwargs):
        self._name = ori_data.get('name')
        if not self._name:
            self._name = "Unnamed Scenario"
        self._root_actor.set_from_ori(ori_data.get_sub_ori(SdKeys.ROOT_ACTOR),
                                      context=context, refs_map=refs_map, **kwargs)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:
        return {
            SdKeys.NAME: self._name,
            SdKeys.ROOT_ACTOR: self._root_actor.get_ori_def(context=context, **kwargs)
        }

    @override(IOriSerializable)
    def _has_ori_changes_children(self) -> bool:
        return self._root_actor.has_ori_changes()

    @override(IOriSerializable)
    def _set_ori_snapshot_baseline_children(self, baseline_id: OriBaselineEnum):
        self._root_actor.set_ori_snapshot_baseline(baseline_id)

    @override(IScenAlertSource)
    def _get_alert_parent(self):
        return self.__alert_parent

    @override(IScenAlertSource)
    def _get_children_alert_sources(self) -> List[IScenAlertSource]:
        return [self._root_actor]

    @override(IScenAlertSource)
    def _get_source_name(self) -> str:
        """
        This class has a name property. We return it to satisfy the IScenAlertSource
        :return: The source name
        """
        return self._name


class Scenario(IOriSerializable, IScenAlertSource):
    """
    The Scenario class holds the full definition of an Origame scenario.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------

    _ORI_HAS_CHILDREN = True

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, anim_mode_constness: Either[None, bool] = True):
        """
        Represent an Origame scenario.

        The scenario has an animation mode that is used by all scenario parts: when the mode is boolean false,
        parts do not emit signals when they change their state; when the mode is boolean true, they emit signals.

        The animation mode may be constant or dynamic; when dynamic, the mode is managed by the simulation
        controller depending on the controller's anim_while_run_dyn setting and the state (paused or running)
        that the controller is in. For example when the controller is in the paused state, the animation mode
        is always True; when in the running state, the mode is the same as the controller's anim_while_run_dyn
        setting. This is how the animation mode can be controlled from the GUI (dynamic), set to constant False
        in the Console variant, and set to either constant or dynamic in unit tests.

        :param anim_mode_constness:
            - if True or False, the animation mode will be constant and have this value
              for the lifecycle of the Scenario instance; the self.sim_controller.settings.anim_while_run_dyn
              setting will have no impact on the animation mode of the scenario.
            - if None, an instance of AnimationMode will be created, so that changing
              self.sim_controller.settings.anim_while_run_dyn will impact the scenario's animation mode as
              described above.
        """
        IOriSerializable.__init__(self)
        IScenAlertSource.__init__(self)

        if PyDebugger.get_singleton() is None:
            log.warning("No python script debugging available during sim runs")
        else:
            PyDebugger.clear_debug_events_registry()

        # scenario animation: Console variant will use constant False; GUI will use dynamic; tests will use
        # constant True (except tests related to animation toggling!)
        if anim_mode_constness is None:
            shared_anim_mode = AnimationMode()
            anim_reader = shared_anim_mode.reader
            log.info('Animation mode is currently {} but may changed based on sim run animation setting',
                     bool(anim_reader))
        else:
            shared_anim_mode = anim_mode_constness
            anim_reader = shared_anim_mode
            log.warning('Constant animation mode is {}', shared_anim_mode)

        # sim related
        self._event_queue = EventQueue()
        self._sim_controller = SimController(event_queue=self._event_queue,
                                             anim_mode=shared_anim_mode,
                                             alert_parent=self)

        # scenario definition related
        self._image_dictionary = ImageDictionary()
        self._embedded_db = EmbeddedDatabase()
        self._shared_state = SharedScenarioState(
            self._sim_controller, anim_reader, image_dict=self._image_dictionary, embedded_db=self._embedded_db)
        self._scenario_def = ScenarioDefinition(self._shared_state, alert_parent=self)

        self.set_ori_snapshot_baseline(OriBaselineEnum.current)

    def shutdown(self):
        """
        Clean up any resources such as database etc.
        """
        self.save_batch_replic_data()

        # no need to clear event queue, esp. if large number of events

        # Oliver TODO build 3.4: Determine if sim controller needs to be paused
        #     Reason: pausing causes issue, seems should be the right thing to do
        # if not self._sim_controller.is_state(SimStatesEnum.paused):
        #    self._sim_controller.sim_pause()

        self._scenario_def.on_scenario_shutdown()
        self._embedded_db.shutdown()

    def import_scenario(self, ori_data: OriScenData, dest_actor: ActorPart):
        """
        Import a Scenario, defined in raw ORI data format, into an actor of current Scenario.
        :param ori_data: the dictionary containing the raw Scenario data in ORI format
        :param dest_actor: actor part in which to put the root actor of imported Scenario
        """
        self._image_dictionary.set_image_id_offset()
        self._image_dictionary.import_image_dict(ori_data['image_dictionary'])
        self._scenario_def.import_scenario(ori_data.get_sub_ori('scenario_def'), dest_actor)
        self._image_dictionary.reset_image_id_offset()

    def get_event_queue(self) -> EventQueue:
        """
        Get the simulation event queue of the Scenario.
        """
        return self._event_queue

    def get_scenario_def(self) -> ScenarioDefinition:
        """
        Get the Scenario Definition for the Scenario.
        """
        return self._scenario_def

    def get_sim_controller(self) -> SimController:
        """
        Get the sim_config settings for the Scenario.
        """
        return self._sim_controller

    def get_filepath(self) -> Path:
        """
        Get the file path of the current scenario.
        """
        return self._shared_state.scen_filepath

    def set_filepath(self, value: PathType):
        """
        Set the file path of the current scenario. This should be updated when a new scenario is loaded or when the
        current scenario is saved.
        """
        path = Path(value)
        self._shared_state.set_scen_filepath(path)
        self._sim_controller.set_replic_folder(path.parent)

    def get_root_actor(self) -> ActorPart:
        """Get the root actor of this scenario"""
        return self._scenario_def.root_actor

    def get_part(self, name: str) -> BasePart:
        """
        Get a part that has the given name. The first scenario part found is returned. See
        ActorPart.get_first_descendant() and ActorPart.get_all_descendants(), which can be called on the
        scenario's root actor, for more powerful retrieval capabilities.
        """
        root_actor = self.root_actor
        if root_actor.part_frame.name == name:
            return root_actor
        return root_actor.get_first_descendant(name=name)

    def get_image_dictionary(self) -> ImageDictionary:
        """ Returns the image dicationary instance of this scenario. """
        return self._image_dictionary

    def get_shared_state(self) -> SharedScenarioState:
        """
        Get the shared state of this scenario.
        """
        return self._shared_state

    def search_parts(self, re_pattern: str) -> {BasePart: List[str]}:
        """
        Find all parts that have properties with string value that matches a pattern.
        :param re_pattern: pattern to match
        :return: dictionary where each key is the path through actor hierarchy, and value is a list of property names
            on the associated part
        """
        return self._scenario_def.search_parts(re_pattern)

    def cancel_search(self):
        """
        Cancel a search started with search_parts(). The cancellation takes effect as soon as current part doing
        search has completed its local search. Any children remaining are skipped.
        NOTE: this must not be called asynchronously, since the backend event loop is busy during the whole search
        """
        self._scenario_def.cancel_search()

    def find_all_parts(self, type_name: str) -> List[BasePart]:
        """Find all parts of a give type name."""
        parts = list()
        root_actor = self._scenario_def.root_actor
        if type_name == ActorPart.PART_TYPE_NAME:
            parts.append(root_actor)
        root_actor.find_all_parts(type_name, parts)
        return parts

    def import_for_export(self, parts: List[BasePart]):
        """
        This function copies the part(s) from another scenario into the current scenario's root actor.
        :param parts: The parts to be copied into the current instance.
        """
        root = self._scenario_def.root_actor
        root.copy_parts(parts, context=OriContextEnum.export)

    def fix_invalid_linking(self):
        """Attempt to fix any linking issues in scenario, such as nodes with more than one outgoing link"""
        self._scenario_def.fix_invalid_linking()

    def on_file_saved(self, filepath: Path):
        """When the scenario has been saved successfully, notify relevant sub-components"""
        self._sim_controller.on_scenario_saved()

    def on_file_loaded(self, filepath: Path):
        """After the scenario has been loaded from a file, notify relevant sub-components"""
        self._sim_controller.on_scenario_loaded()

    def on_file_unlinked(self):
        """When the scenario file is removed the system, this is automatically called"""
        self._sim_controller.on_scenario_unlinked()
        self._shared_state.set_scen_filepath(None)

    def save_batch_replic_data(self, clear_after: bool=False):
        """
        Save the batch replication data that is in memory to the filesystem.
        :param clear_after: If True, will also clear the data from memory. The next call to this method (e.g.,
            during shutdown()), will not save anything.
        """
        try:
            self._shared_state.batch_data_mgr.write_replication_data()
            if clear_after:
                self.clear_batch_replic_data()

        except Exception:
            variant_id = self.sim_controller.variant_id
            replic_id = self.sim_controller.replic_id
            log.warning('Skipping batch replication (v={}, r={}) data save: Could not save it to {}',
                        variant_id, replic_id, self.filepath)

    def clear_batch_replic_data(self):
        """Clear the batch replication data that is in memory."""
        self._shared_state.batch_data_mgr._reset()

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    filepath = property(get_filepath)  # setting is a complex op, not suitable for property notation
    event_queue = property(get_event_queue)
    scenario_def = property(get_scenario_def)
    sim_controller = property(get_sim_controller)
    root_actor = property(get_root_actor)
    image_dictionary = property(get_image_dictionary)
    shared_state = property(get_shared_state)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IOriSerializable)
    def _ori_id(self) -> str:
        return 'Scenario {}'.format(self._shared_state.scen_filepath or "<unsaved>")

    @override(IOriSerializable)
    def _set_from_ori_impl(self, ori_data: OriScenData, context: OriContextEnum, **kwargs):

        assert ori_data
        assert ori_data.schema_version is not None

        if ori_data.get(SKeys.IMAGE_DICT):
            # image dictionary must be set up before scenario
            self._image_dictionary.set_from_ori(ori_data.get_sub_ori(SKeys.IMAGE_DICT))

        if ori_data.get(SKeys.SCENARIO_DEF) is None:
            raise RuntimeError('Bad scenario: no definition!')
        map_ori_key_to_part = {}
        self._scenario_def.set_from_ori(ori_data.get_sub_ori(SKeys.SCENARIO_DEF), refs_map=map_ori_key_to_part)
        self._image_dictionary.clean_up()

        if ori_data.get(SKeys.EVENT_QUEUE):
            assert self._scenario_def is not None
            self._event_queue.set_from_ori(ori_data.get_sub_ori(SKeys.EVENT_QUEUE), refs_map=map_ori_key_to_part)

        if ori_data.get(SKeys.SIM_CONFIG):
            self._sim_controller.set_from_ori(ori_data.get_sub_ori(SKeys.SIM_CONFIG))

        if ori_data.get(SKeys.RNG_STATE):
            random.setstate(pickle.loads(pickle_from_str(ori_data[SKeys.RNG_STATE])))

        if context == OriContextEnum.save_load:
            self.on_file_loaded(self._shared_state.scen_filepath)

    @override(IOriSerializable)
    def _get_ori_def_impl(self, context: OriContextEnum, **kwargs) -> JsonObj:

        self._image_dictionary.clean_up()

        return {
            SKeys.SCHEMA_VERSION: OriScenData.DEFAULT_SCHEMA_VERSION.value,
            SKeys.EVENT_QUEUE: self._event_queue.get_ori_def(**kwargs),
            SKeys.SIM_CONFIG: self._sim_controller.get_ori_def(**kwargs),
            SKeys.SCENARIO_DEF: self._scenario_def.get_ori_def(context=context, **kwargs),
            SKeys.IMAGE_DICT: self._image_dictionary.get_ori_def(**kwargs),
            SKeys.RNG_STATE: pickle_to_str(pickle.dumps(random.getstate()))
        }

    @override(IOriSerializable)
    def _has_ori_changes_children(self) -> bool:
        return (self._event_queue.has_ori_changes()
                or self._sim_controller.has_ori_changes()
                or self._scenario_def.has_ori_changes()
                or self._image_dictionary.has_ori_changes())

    @override(IOriSerializable)
    def _set_ori_snapshot_baseline_children(self, baseline_id: OriBaselineEnum):
        self._event_queue.set_ori_snapshot_baseline(baseline_id)
        self._sim_controller.set_ori_snapshot_baseline(baseline_id)
        self._scenario_def.set_ori_snapshot_baseline(baseline_id)
        self._image_dictionary.set_ori_snapshot_baseline(baseline_id)

    @override(IScenAlertSource)
    def _get_children_alert_sources(self) -> List[IScenAlertSource]:
        return [self._scenario_def, self._sim_controller]

    @override(IScenAlertSource)
    def _on_get_ondemand_alerts(self):
        self.__check_date_time_sync()
        # NOTE: Time parts are expected to be used freely with different times (since they can be used to
        # keep track of time from when an event occurred), so no check for 'time' parts

    @override(IScenAlertSource)
    def _get_source_name(self) -> str:
        """
        Returns "Scenario"
        :return: The source name
        """
        return "Scenario"

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __check_property_same(self, part_type_str: str, property_name: str):
        """
        Check that all parts of a certain type have the same value for a given property. If some are found,
        an on-demand alert is created.
        """
        if property_name == 'date_time':
            raise ValueError('Use self.__check_datetime_sync for date_time checks')

        all_parts_of_type = self.find_all_parts(part_type_str)
        map_property_vals_to_parts = defaultdict(list)
        for part in all_parts_of_type:
            map_property_vals_to_parts[getattr(part, property_name)].append(part)

        if len(map_property_vals_to_parts) <= 1:
            # no parts, or all parts have same property value!
            return

        # create alert:
        prop_list_str = self.__get_prop_mismatch_err_str(map_property_vals_to_parts)
        msg = 'Some {} parts do not have same {} property value:\n{}'.format(
            part_type_str, property_name, prop_list_str)
        self._add_ondemand_alert(ScenAlertLevelEnum.warning, ErrorCatEnum.mismatched, msg)

    def __check_date_time_sync(self):
        """
        Check that all date-time related parts (currently datetime and clock) have the same date_time value.
        If some are found, an on-demand alert is created.
        """
        all_datetime_parts = self.find_all_parts('datetime')
        all_datetime_parts.extend(self.find_all_parts('clock'))
        map_property_vals_to_parts = defaultdict(list)
        for part in all_datetime_parts:
            map_property_vals_to_parts[part.date_time].append(part)

        if len(map_property_vals_to_parts) <= 1:
            # no parts, or all parts have same property value!
            return

        # generate alert:
        prop_list_str = self.__get_prop_mismatch_err_str(map_property_vals_to_parts)
        msg = 'Some datetime-related parts do not have same date_time value:\n{}'.format(prop_list_str)
        self._add_ondemand_alert(ScenAlertLevelEnum.warning, ErrorCatEnum.out_of_sync, msg)

    def __get_prop_mismatch_err_str(self, map_property_vals_to_parts: Dict[Any, List[BasePart]]) -> str:
        """Generate a string that lists the keys found and for each one, the associated parts as a sublist"""
        def sub_list_parts(parts):
            """Create a multi-line string for the list of parts, sorted by path, indented (because sub-list)"""
            part_str_gen = ('- {}'.format(p) for p in sorted(parts, key=BasePart.get_path))
            return indent('\n'.join(part_str_gen), '    ')

        # create a list of property values sorted ascending, and for each one, the parts (sorted by path) that have
        # that property value:
        list_gen = ('- {}:\n{}'.format(dt, sub_list_parts(map_property_vals_to_parts[dt]))
                    for dt in sorted(map_property_vals_to_parts))
        prop_list_str = '\n'.join(list_gen)
        return prop_list_str

