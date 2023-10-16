# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module contains the Origame backend Scenario Manager and related capabilities.

This module provides the backend Scenario Manager capabilities. The Scenario Manager manages the loading of
scenario definition files formatted for both the Origame version of the application and the prototype version and
the saving of scenarios to the respective formats. The two types of support are achieved by the scenario_file_util and
prototype_file_util modules respectively.

Version History: See SVN log.
"""

# [1. standard library]
import threading
from pathlib import Path, PureWindowsPath
from distutils.dir_util import copy_tree
import logging
import re
import shutil
import argparse

# [2. third-party]

# [3. local]
from ..core import BridgeEmitter, BridgeSignal, UniqueIdGenerator
from ..core.typing import Any, Either, Optional, List, Tuple, Sequence, Set, Dict, Iterable, Callable, PathType

from .defn_parts import ActorPart, BasePart
from .scenario import Scenario
from .file_util_base import ScenarioFileNotFoundError
from .file_util_json import ScenFileUtilJsonOri
from .file_util_prototype import ScenFileUtilPrototype
from .file_util_pickle import ScenFileUtilPickle
from .ori import OriBaselineEnum, OriScenData, OriContextEnum
from .ori import OriScenarioKeys as ScKeys
from .proto_compat_warn import warn_proto_compat_funcs
from . import event_queue  # to configure event_queue module

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'ScenarioManagerFileLoadError',
    'ImageManagerCopyDirError',
    'ScenarioManager',
    'ImageManager'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------

# -- Class Definitions --------------------------------------------------------------------------

class ScenarioManagerFileLoadError(Exception):
    """
    Custom error class used for handling/throwing ScenarioMgr exceptions.
    """

    def __init__(self, msg: str):
        super().__init__(msg)


class ImageManagerCopyDirError(Exception):
    """
    Custom error class used for handling/throwing exceptions that occur while copying directories.
    """
    pass


class ImageManager:
    """
    This class is responsible for the management of non-default image files that have been assigned to scenario parts.
    It ensures that image files are copied to a sub-directory within the related scenario folder and that the
    ImageDictionary maintains accurate paths to these files.
    """

    IMAGES_DIR = "images"  # Default directory name for image files

    FILE_NAME_PATTERN = re.compile('(.*)\([0-9]+\)$')  # used by the _copy_file() function. doesn't consider extension.

    def pre_process_image_dict_ori(self, scenario_path: PathType, image_dict_ori: {}):
        """
        This function pre-processes the image dictionary's ORI data before it is loaded into Origame. It converts
        relative image paths to absolute image paths, and also verifies that the expected images can be found at the
        absolute paths. Problems are logged as warnings.
        :param scenario_path: The path of the scenario file associated with the image dictionary being processed.
        :param image_dict_ori: The ORI data for the image dictionary associated with the specified scenario.
        """
        if image_dict_ori:
            images_dir = Path(scenario_path).parent / self.IMAGES_DIR

            if not images_dir.exists():
                log.warning("Image files not found. Scenario image files expected in '{}' subdirectory of scenario file"
                            " directory. Parts will assume their default images", self.IMAGES_DIR)
            else:
                for image_id in list(image_dict_ori.keys()):
                    filename = image_dict_ori[image_id]
                    image_path = images_dir / filename
                    if not image_path.exists():
                        log.error("Image Manager: Image file ({}) not found. Image-dependent parts will be displayed"
                                  "with an 'error' image.",
                                  str(image_path))
                    # update filename to be an absolute path
                    image_dict_ori[image_id] = str(image_path)

    def post_process_image_dict_ori(self, scenario_path: str, image_dict_ori: {}):
        """
        This function post-processes the image dictionary's ORI data after it has been generated from a scenario. It
        converts absolute image paths to relative paths, and any image files, with absolute paths that are different
        from the default absolute path for the currently loaded scenario, are copied to the default absolute path
        location. Further, to filter out any image files that are no longer referenced by the Image Dictionary,
        the set of files referenced by the scenario is compared to the set of files in the 'images' folder and the
        files in the folder that are not referenced in the scenario are deleted.
        :param scenario_path: The path of the scenario file associated with the image dictionary being processed.
        :param image_dict_ori: The ORI data for the image dictionary associated with the specified scenario.
        """

        if image_dict_ori and len(image_dict_ori) > 0:
            target_images_dir = Path(scenario_path).parent / self.IMAGES_DIR

            if not target_images_dir.exists():
                target_images_dir.mkdir(parents=True)
            target_images_dir.chmod(0o664)

            files_in_scenario = set()

            for image_id, source_image_path in image_dict_ori.items():

                filename = str(Path(source_image_path).name)

                try:
                    res_source_path = Path(source_image_path).resolve()
                    res_target_path = target_images_dir.resolve()
                    if res_source_path.parent != res_target_path:
                        # The current image file has been loaded from a different location than the scenario's 'images'
                        # directory. Copy it to the target director, correcting name clashes if they exist.
                        filename = self.__copy_file(source_path=source_image_path,
                                                    target_path=str(res_target_path / res_source_path.name))
                except:
                    log.warning("Custom image file ({}) cannot be resolved and can't be saved with scenario. "
                                "Part/image association will still be maintained in Image "
                                "Dictionary.", source_image_path)

                image_dict_ori[image_id] = filename
                files_in_scenario.add(filename)

            files_in_folder = set()

            for item in target_images_dir.iterdir():
                if item.is_file():
                    files_in_folder.add(item.name)

            unreferenced_files = [f for f in files_in_folder if f not in files_in_scenario]

            for unref_file in unreferenced_files:
                Path(target_images_dir / unref_file).unlink()

    def copy_dir(self, source_path: str, target_path: str):
        """
        This function copies the source_path directory into the target_path directory.
        :param source_path: The source directory.
        :param target_path: The target directory.
        :raises ImageManagerCopyDirError: Raised for invalid directory paths or other file copy errors that may occur.
        """
        source_images_path = Path(source_path)
        target_images_path = Path(target_path)

        if source_images_path.exists():

            try:
                if not Path(target_path).exists():
                    Path(target_path).mkdir(parents=True)

                copy_tree(str(source_images_path), str(target_images_path))

            except Exception as exc:
                log.error("Error copying directory '{}' to directory '{}'. Additional info: {}",
                          source_images_path, target_images_path, exc)
                raise ImageManagerCopyDirError("Error copying directory '{}' to directory '{}'. Additional info: "
                                               "{}".format(source_path, target_path, exc))

        else:
            log.info("No image files located at: '{}' for copy to scenario's new save location.", source_path)

    def __copy_file(self, source_path: str, target_path: str) -> str:
        """
        This function copies the source_path file to the target_path. If the target location already contains
        a file with the source file name, the source file name is modified to be unique in the target directory.
        :param source_path: The source path for an image file.
        :param target_path: The target path for the image file.
        :return: This function returns the name of the resulting name of the copied file in the target directory.
        """
        if not Path(target_path).exists():
            # no name clash, copy the file
            shutil.copy2(source_path, target_path)

        else:
            # name clash in target dir, make the source filename unique in the target dir
            count = 1  # start count at one so that second instance of clashed filename is named "filename(2).ext"
            while Path(target_path).exists():
                count += 1
                suffix = Path(target_path).suffix
                filename = Path(target_path).stem
                # if filename already has a unique index applied, remove the "(#)" characters and update the name
                match = self.FILE_NAME_PATTERN.match(filename)
                if match:
                    filename = match.group(1)
                new_filename = filename + '(' + str(count) + ')' + suffix
                target_path = str(Path(target_path).with_name(new_filename))
            shutil.copy2(source_path, target_path)

        return Path(target_path).name


class ScenarioManager:
    """
    This class is used to handle load and save Scenario data in various formats,
    including the Origame and prototype scenario formats.
    """

    ORIGAME_EXTENSION = ".ori"  # The Origame scenario file extension (a JSON-formatted file)
    ORI_BIN_EXTENSION = ".orib"  # Fast load/save format, not human-readable and doesn't reflect scenario hierarchy
    PROTOTYPE_EXTENSION = ".db"  # The prototype scenario database file extension
    FILE_EXTENSION_LIST = (ORIGAME_EXTENSION, ORI_BIN_EXTENSION, PROTOTYPE_EXTENSION)

    # Obsolete. For backward compatibility only. The .pkl is the Build 1 legacy.
    PKL_EXTENSION = ".pkl"

    FIX_INVALID_LINKING_ON_LOAD = True

    # Signals from back-end:
    class Signals(BridgeEmitter):
        sig_scenario_replaced = BridgeSignal()  # whenever scenario instance has been replaced by a new one (New, Load)
        sig_scenario_filepath_changed = BridgeSignal(str)  # whenever path to scenario changes (save-as, New, Load)
        sig_save_enabled = BridgeSignal(bool)  # True if file loaded is saveable in same format as on disk
        sig_scenario_saved = BridgeSignal()

    # --------------------------- class-wide methods --------------------------------------------

    @classmethod
    def enable_fix_linking_on_load(cls, value: bool = True):
        cls.FIX_INVALID_LINKING_ON_LOAD = value
        log.info('Will {}fix linking on scenario load', ('' if value else 'not '))

    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, thread=None):
        super().__init__()
        if thread is None:
            is_main_thread = (threading.current_thread() == threading.main_thread())
        else:
            is_main_thread = False
        self.signals = ScenarioManager.Signals(thread=thread, thread_is_main=is_main_thread)
        self.__scenario = None  # The current scenario definition object
        self.__anim_mode_constness = True  # constant and True by default
        UniqueIdGenerator.reset()  # assumes one instance per app session

    def config_logging(self, config: argparse.Namespace):
        """Configure the logging engine for scenario outputs using the given configuration"""
        if not config.log_deprecated:
            warn_proto_compat_funcs(False)

        if config.log_raw_events and not event_queue.LOG_RAW_EVENT_PUSH_POP:
            event_queue.LOG_RAW_EVENT_PUSH_POP = True

        if self.FIX_INVALID_LINKING_ON_LOAD and not config.fix_linking_on_load:
            self.enable_fix_linking_on_load(False)
            assert not self.FIX_INVALID_LINKING_ON_LOAD

    def set_future_anim_mode_constness(self, value: Either[bool, None] = True):
        """
        Set the animation mode const'ness of Scenario instances created after this call (i.e. calling
        this method does not affect mode const'ness of existing Scenario instances). Const'ness
        of animation refers to whether or not the animation mode of the scenario can be changed while
        a simulation is being run:

        - when animation mode is constant, a Scenario instance, including all its parts and the simulation
            controller, will have anim_mode=value and is_animated=value, regardless of the anim_while_run_dyn
            setting of the scenario;
        - when animation mode is dynamic, the simulation controller will honor the anim_while_run_dyn
            setting while running a simulation, and the setting can be programmatically changed at any time
            (via a scenario part script, or from a unit test; so if running, the change will have immediate
            effect; if paused, the setting change will be honored at the next run/resume)

        :param value:
            - None: animation mode is dynamic so it will be controlled by the sim-run animation setting
                (self.scenario.sim_controller.settings.anim_while_run_dyn).
            - True/False: animation mode has that value for lifetime of Scenario instance (it is as if
                the setting value had been hard-coded in the application).
        """
        self.__anim_mode_constness = value

    def set_future_anim_mode_dynamic(self):
        """
        Set the animation mode to be dynamic, i.e. to be controlled by
        self.scenario.sim_controller.settings.anim_while_run_dyn while running a simulation. This is an
        alias for self.set_future_anim_mode_constness(None), sometimes it is more readable. See
        set_future_anim_mode_constness() for details on animation mode const'ness.
        """
        self.set_future_anim_mode_constness(None)

    def get_future_anim_mode_constness(self) -> Either[bool, None]:
        """
        Get the animation mode const'ness for Scenario instances created after this method is called.
        This does not reflect whether existing Scenario instance of manager has const or dynamic animation.
        :return: True or False if constant animation; None if dynamic
        """
        return self.__anim_mode_constness

    def is_future_anim_mode_const(self) -> bool:
        """
        Check whether animation mode of future Scenario instances will be constant or dynamic.
        :return: True if constant, False if dynamic. Note that if constant, this method does not determine
            which constant (True or False).
        """
        return self.__anim_mode_constness in (True, False)

    def get_scenario(self) -> Scenario:
        """
        Get the scenario currently stored in memory.
        """
        return self.__scenario

    def check_for_changes(self) -> bool:
        """
        Determine if the scenario file has unsaved changes.
        :return: True if there are changes, False if no changes since last load or save
        """
        has_changes = False if self.__scenario is None else self.__scenario.has_ori_changes()
        log.info("Checked for changes in scenario: {}", has_changes)
        return has_changes

    def new_scenario(self) -> Scenario:
        """
        This function creates a new default scenario definition object containing only a root Actor part.
        :return: The new default scenario definition.
        """
        log.info("New scenario requested")
        orig_scenario = self.__scenario
        self.__scenario = Scenario(anim_mode_constness=self.__anim_mode_constness)

        self.signals.sig_scenario_replaced.emit()
        self.signals.sig_scenario_filepath_changed.emit(None)
        self.signals.sig_save_enabled.emit(True)

        # must do this last in case the new failed:
        if orig_scenario is not None:
            orig_scn_name = orig_scenario.filepath
            if orig_scenario.filepath is None:
                orig_scn_name = "<unsaved>"
            log.info("Shutting down previous scenario [{}]", orig_scn_name)
            orig_scenario.shutdown()
            log.info("Previous scenario shut-down completed")

        log.info("New scenario creation completed")
        return self.__scenario

    def load(self, path: PathType) -> Tuple[Scenario, list[str]]:
        """
        This function loads the scenario file from the specified path and returns the loaded data in the form of a
        Scenario object.
        :param path: The full pathname of the scenario file to be loaded. This path can point to an Origame (.ori in
            JSON-format) or prototype (.db) formatted scenario file.
        :return: Scenario instance for the loaded scenario
        :raises: ScenarioManagerFileLoadError: This error is raised if the load path is invalid, or if the
            scenario file format is invalid.
        """
        log.info("Scenario load of '{}' requested", path)
        orig_scenario = self.__scenario
        path = Path(path)
        scen_ori_def, path, non_serialized_obj = self.__load_ori(path)
        log.info("Scenario file '{}' loaded successfully; instantiating...", path)

        self.__scenario = Scenario(anim_mode_constness=self.__anim_mode_constness)
        image_dict = scen_ori_def.get(ScKeys.IMAGE_DICT, {})
        image_manager = ImageManager()
        image_manager.pre_process_image_dict_ori(path, image_dict)
        # Path must be set before setting from ORI data, in case objects created need to know where scenario
        # is located (example: FilePart)
        self.__scenario.set_filepath(path)
        self.__scenario.set_from_ori(scen_ori_def)
        log.info("Scenario instance created successfully")
        if self.FIX_INVALID_LINKING_ON_LOAD:
            self.__scenario.fix_invalid_linking()

        self.signals.sig_scenario_replaced.emit()
        self.signals.sig_scenario_filepath_changed.emit(str(path))

        # must do this last in case the load failed:
        if orig_scenario is not None:
            orig_scn_name = orig_scenario.filepath
            if orig_scenario.filepath is None:
                orig_scn_name = "<unsaved>"
            log.info("Shutting down previous scenario [{}]", orig_scn_name)
            orig_scenario.shutdown()

        log.info("Scenario loading completed")

        return self.__scenario, non_serialized_obj

    def save(self, path: PathType = None) -> list[str]:
        """
        This function saves the current scenario to the specified path. The function serves double-duty for 'save' and
        'save as' operations. If a file already exists at the specified path it will be overwritten without warning.
        If a path is not specified, the last loaded or saved filename is used.
        Prototype database (.db) and Origame scenario (.ori) file formats are supported.
        :param path: The full path at which to save the file.
        """
        path = Path(path or self.__scenario.filepath)
        assert path

        log.info("Save scenario to '{}' requested", path)

        # If the specified filename doesn't include an extension, the Origame file extension is assumed and
        # appended to the filename.
        path_suffix = path.suffix
        if not path_suffix:
            path_suffix = self.ORIGAME_EXTENSION
            path = path.with_suffix(path_suffix)

        non_serialized_obj = self.__save_ori(path, self.__scenario)

        log.info("Scenario saving completed successfully")

        return non_serialized_obj

    def erase_scenario_file(self):
        """Remove the saved scenario from filesystem. Does nothing if never saved."""
        if self.__scenario is None:
            return

        filepath = self.__scenario.filepath
        if filepath is None:
            return

        log.info('Erasing scenario {} from filesystem', filepath)
        filepath.unlink()
        self.__scenario.on_file_unlinked()

    def search_scenario_parts(self, re_pattern: str) -> {str: List[str]}:
        """
        Find all parts that have properties with string value that matches a pattern.
        :param re_pattern: pattern to match
        :return: dictionary where each key is the path through actor hierarchy, and value is a list of property names
            on the associated part
        """
        return self.__scenario.search_parts(re_pattern)

    def import_scenario(self, path: PathType, dest_actor: ActorPart):
        """
        This function loads a scenario file from the specified path and inserts the associated scenario definition
        portion of that scenario into the current scenario. The insertion point in the current scenario is the Actor
        Part specified as the dest_actor - that is to say, the root Actor Part of the imported scenario becomes a
        child part of the dest_actor Actor Part.
        :param path: A file path to the scenario to be imported.
        :param dest_actor: The Actor Part in the current scenario into which the imported scenario definition is to
        be inserted.
        :raises: ScenarioManagerFileLoadError See __load_ori() documentation.
        :raises: UnsupportedPartTypeError See Scenario.import_scenario() documentation.
        """
        path = Path(path)
        log.info("Scenario '{}' import requested into actor {}", path, dest_actor)
        ori_scenario, path = self.__load_ori(path)

        image_dict = ori_scenario.setdefault(ScKeys.IMAGE_DICT, {})
        image_manager = ImageManager()
        image_manager.pre_process_image_dict_ori(path, image_dict)
        self.scenario.import_scenario(ori_scenario, dest_actor)

        log.info("Scenario imported sucessfully")

    def export_scenario(self, parts: List[BasePart], path: PathType):
        """
        Method used to export a selection of parts as a scenario into an .ori file.
        :param parts: A list of parts to export from the current scenario into a new scenario.
        :param path: path to new file
        """
        assert parts
        log.info("Export to new scenario requested for parts {}", ', '.join(str(p) for p in parts))

        # If the specified filename doesn't include an extension, the Origame file extension is assumed and
        # appended to the filename.
        path = Path(path)
        path_suffix = path.suffix
        if path_suffix == "":
            path_suffix = self.ORIGAME_EXTENSION
            path = path.with_suffix(path_suffix)

        elif path_suffix not in (self.ORIGAME_EXTENSION, self.ORI_BIN_EXTENSION):
            log.error("Cannot export to unresolved scenario file type: {}", path)
            raise RuntimeError("The scenario type (" + path_suffix + ") specified for export is invalid")

        log.info("Exporting scenario parts to: {}", path)

        new_scenario = Scenario(anim_mode_constness=self.__anim_mode_constness)
        new_scenario.import_for_export(parts)

        self.__save_ori(path, new_scenario)
        # Undo the ORI baseline created when we did a get_ori_def() to export because we didn't save that version of
        # the ORI data, we just exported a portion of it.
        self.__scenario.set_ori_snapshot_baseline(OriBaselineEnum.existing)
        log.info("Scenario parts exported successfully to new scenario")

    def shutdown(self):
        """Shutdown the manager. It is no longer usable after this call."""
        if self.__scenario is not None:
            self.__scenario.shutdown()
            self.__scenario = None

    # --------------------------- instance PUBLIC properties ----------------------------

    scenario = property(get_scenario)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    def __load_ori(self, path: Path) -> Tuple[OriScenData, Path, list[str]]:
        """
        This function loads the scenario file corresponding to the specified path and returns the scenario in Python
        dictionary format.

        This function supports both prototype (.db) and Origame (.ori) scenario file formats but the returned data
        structure is the Python dictionary-equivalent to the JSON file format used in the .ori file.
        :param path: The path of scenario file to be loaded.
        :return: A Python dictionary data structure describing the loaded scenario. The data structure is the Python
        equivalent to the JSON file structure used in the Origame (.ori) scenario files.
        :raises: ScenarioManagerFileLoadError An error occurred loading the specified file.
        """
        log.info("Loading scenario '{}'", path)

        path_suffix = path.suffix.lower()  # Windows is case insensitive
        loaders = {
            self.ORIGAME_EXTENSION: ScenFileUtilJsonOri,
            self.PROTOTYPE_EXTENSION: ScenFileUtilPrototype,
            self.ORI_BIN_EXTENSION: ScenFileUtilPickle,
            self.PKL_EXTENSION: ScenFileUtilPickle,
        }
        if not path_suffix:
            path_suffix = self.ORIGAME_EXTENSION
            path = path.with_suffix(self.ORIGAME_EXTENSION)

        Loader = loaders.get(path_suffix)
        if Loader is None:
            log.error("ScenarioManager - Unresolved scenario file type: {}", path)
            raise ScenarioManagerFileLoadError("Scenario type ('" + path_suffix +
                                               "') specified for load is invalid.")

        scenario_loader = Loader()
        self.signals.sig_save_enabled.emit(scenario_loader.SAVABLE)
        try:
            ori_scenario, non_serialized_obj = scenario_loader.load_file(str(path))

        except ScenarioFileNotFoundError as path_error:
            log.exception("Scenario file not found ({}). More info: {}", path, str(path_error))
            raise ScenarioManagerFileLoadError("Scenario Manager failed to load scenario ({}). More info: {}"
                                               .format(path, path_error))
        except ValueError as format_error:
            log.exception("Scenario file format error. File:{}. Error:{}", path, str(format_error))
            raise

        return ori_scenario, path, non_serialized_obj

    def __save_ori(self, path: Path, scenario: Scenario) -> list[str]:
        """
        Save a scenario instance to file system.
        :param path: path to .ORI file in which to save scenario
        :param scenario: instance to save
        """
        # create the file writer:
        path_suffix = path.suffix
        savers = {
            self.ORIGAME_EXTENSION: ScenFileUtilJsonOri,
            self.ORI_BIN_EXTENSION: ScenFileUtilPickle,
        }
        SaveUtil = savers.get(path_suffix)
        if SaveUtil is None:
            log.error("Cannot save unresolved scenario file type: {}", path)
            raise RuntimeError("The Scenario type (" + path_suffix + ") specified for save is invalid")
        save_util = SaveUtil()

        # get the scenario's ORI data:
        ori_scenario = scenario.get_ori_def(context=OriContextEnum.save_load)
        image_manager = ImageManager()
        image_manager.post_process_image_dict_ori(path, image_dict_ori=ori_scenario[ScKeys.IMAGE_DICT])
        log.info("Got ORI definition data from scenario instance")
        try:
            non_serialized_obj = save_util.save(ori_scenario, path)
        except Exception:
            scenario.set_ori_snapshot_baseline(OriBaselineEnum.existing)
            raise

        # now that the commit has succeeded, commit the path to scenario:
        scenario.set_filepath(path)
        scenario.on_file_saved(path)
        image_dict_ori = ori_scenario[ScKeys.IMAGE_DICT]
        if image_dict_ori:
            # update the in-memory image dictionary so that it contains the latest image file paths.
            image_manager.pre_process_image_dict_ori(path, ori_scenario[ScKeys.IMAGE_DICT])
            scenario.image_dictionary.update_image_paths(ori_scenario[ScKeys.IMAGE_DICT])

        scenario.set_ori_snapshot_baseline(OriBaselineEnum.current)
        if scenario is self.__scenario:
            # only emit saved signals if the scenario to save is the current one
            # i.e. not for exported scenarios
            self.signals.sig_scenario_filepath_changed.emit(str(path))
            self.signals.sig_scenario_saved.emit()

        return non_serialized_obj
