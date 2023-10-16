# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The purpose is to capture the common features such as "find and replace" among
the part types like Function, Library, Plot and SQL.


Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
import re
from enum import Enum

# [2. third-party]

# [3. local]
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ...core import override_optional, override
from ...core.utils import plural_if
from ..alerts import ScenAlertLevelEnum, IScenAlertSource
from .part_link import TypeReferencingParts, TypeMissingLinkInfo, LINK_PATTERN
from .part_link import get_patterns_by_link_item, get_link_find_replace_info
from . import BasePart

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 7257 $"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'IScriptedPart'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ErrorCatEnum(Enum):
    link_missing, link_unused = range(2)


class IScriptedPart:
    """
    The part type that has a script should derive from this class.

    Note: This is not a pure interface. Some concrete implementations such as traversal are included here.
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    @override_optional
    def find(self,
             referencing_parts: TypeReferencingParts,
             referenced_link_name: str):
        """
        Finds the affected lines of the script of this part

        :param referencing_parts: All the parts that reference the "referenced_link_name"
        :param referenced_link_name: The link name referenced by the parts
        """
        original_script = self.get_canonical_script()
        found_part, existing_content = self.__find_current_part_content(referencing_parts)

        patterns = get_patterns_by_link_item(referenced_link_name)
        lines = list()
        for line in original_script.split('\r\n'):
            ret = None
            for pattern in patterns:
                ret = re.search(pattern, line)
                if ret is not None:
                    break

            if ret is None:
                continue

            lines.append(line)

        if len(lines) == 0:
            return

        if found_part is None:
            referencing_parts.append((self, lines))
        else:
            existing_content += lines

    @override_optional
    def replace(self,
                referencing_parts: TypeReferencingParts,
                referenced_link_name: str,
                new_referenced_link_name: str):
        """
        Replaces the old link names in those affected lines with the new link names.

        :param referencing_parts: All the parts that reference the "referenced_link_name"
        :param referenced_link_name: The link name referenced by the parts
        :param new_referenced_link_name: The new name to replace the old name
        """
        original_script = self.get_canonical_script()
        found_part, existing_content = self.__find_current_part_content(referencing_parts)

        fri = get_link_find_replace_info(referenced_link_name, new_referenced_link_name)
        if found_part is None:
            new_script = original_script
        else:
            new_script = existing_content

        for pattern, replacement in fri:
            new_script = re.sub(pattern, replacement, new_script)

        if new_script == original_script:
            return

        referencing_parts.append((self, new_script))

    @override_optional
    def get_canonical_script(self) -> str:
        """
        For historical reasons, the script variable and its getter function are not consistently named among the
        Function, Library, Plot and SQL parts. We use this function to get the script to satisfy the find() and
        replace().

        Note: Though this function is optional, the derived class must implement it if the class does not have
        a function called "get_script", which is assumed by the default implementation of this function.
        :return: The script from the derived class
        """
        return self.get_script()

    @override_optional
    def set_canonical_script(self, val: str):
        """
        For historical reasons, the script variable and its getter function are not consistently named among the
        Function, Library, Plot and SQL parts. We use this function to get the script to satisfy the find() and
        replace().

        Note: Though this function is optional, the derived class must implement it if the class does not have
        a function called "get_script", which is assumed by the default implementation of this function.
        :return: The script from the derived class
        """
        return self.set_script(val)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------
    # --------------------------- instance __SPECIAL__ method overrides -------------------------
    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IScenAlertSource)
    def _on_get_ondemand_alerts(self):
        """
        Processes missing links and unused links.
        """
        # Missing links
        unique_names = self.get_unique_missing_link_names()
        if unique_names:
            msg = "This part has {} missing link{}.".format(len(unique_names), plural_if(unique_names))
            data_map = dict()
            for i, unique_name in enumerate(unique_names):
                data_map["Missing Link {}".format(i)] = unique_name

            self._add_ondemand_alert(ScenAlertLevelEnum.warning, ErrorCatEnum.link_missing, msg, **data_map)

        # Unused links
        unused_names = self.get_unused_link_info()
        if unused_names:
            msg = "This part has {} unreferenced link{}.".format(len(unused_names), plural_if(unused_names))
            data_map = dict()
            for i, unused_name in enumerate(unused_names):
                data_map["Unreferenced link {}".format(i)] = unused_name

            self._add_ondemand_alert(ScenAlertLevelEnum.warning, ErrorCatEnum.link_unused, msg, **data_map)

    @override(BasePart)
    def _get_unused_link_info(self, script: str = None) -> List[str]:
        item_list = []
        part_links, chained_name_and_links = self.get_formatted_link_chains()
        for link in part_links:
            displayed_name = link.name if link.temp_name is None else link.temp_name
            item_list.append(displayed_name)

        for chained_name, link in chained_name_and_links:
            item_list.append(chained_name)

        unused = list()
        text = self.get_canonical_script() if script is None else script
        for link_item in item_list:
            partial_link_pattern = link_item.replace(".", r"\.")
            patterns = get_patterns_by_link_item(partial_link_pattern)

            match_object = None
            for pattern in patterns:
                match_object = re.search(pattern, text)
                if match_object is not None:
                    break

            if match_object is None:
                # Unused
                unused.append(link_item)

        return unused

    @override(BasePart)
    def _get_missing_link_info(self, script: str = None) -> TypeMissingLinkInfo:
        """
        Finds the missing links in the script of the part. Returns the each link's name, line number, start and end 
        cursor positions.
        :param script: If it is None, the existing script of the part is investigated; otherwise, the given script.
        :return: The missing link info (link name, line number, start, end)
        """
        link_list = list()
        part_links, chained_name_and_links = self.get_formatted_link_chains()
        for link in part_links:
            displayed_name = link.name if link.temp_name is None else link.temp_name
            link_list.append(displayed_name)

        for chained_name, link in chained_name_and_links:
            link_list.append(chained_name)

        missing_list = list()
        text = self.get_canonical_script() if script is None else script
        for num_line, line_text in enumerate(text.split('\n')):
            match_objects = re.finditer(LINK_PATTERN, line_text)
            for match_obj in match_objects:
                matched_line_text = line_text[match_obj.start():match_obj.end()]
                if not link_list:
                    # matched_line_text may look like this: link.hub.func. We want hub, so [1]
                    link_name = matched_line_text.split('.')[1]
                    missing_list.append((link_name, num_line, match_obj.start(), num_line, match_obj.end()))
                    continue

                missing = True
                for item_text in link_list:
                    partial_link_pattern = item_text.replace(".", r"\.")
                    patterns = get_patterns_by_link_item(partial_link_pattern)
                    for pattern in patterns:
                        item_match_obj = re.match(pattern, matched_line_text)
                        if item_match_obj is not None:
                            missing = False
                            break

                    if not missing:
                        break

                if missing:
                    # matched_line_text may look like this: link.hub.func. We want hub, so [1]
                    link_name = matched_line_text.split('.')[1]
                    missing_list.append((link_name, num_line, match_obj.start(), num_line, match_obj.end()))

        return missing_list

    # --------------------------- instance _PROTECTED properties and safe slots -----------------
    # --------------------------- instance __PRIVATE members-------------------------------------

    def __find_current_part_content(self,
                                    referencing_parts: TypeReferencingParts) -> Tuple[BasePart, Either[List[str], str]]:
        """
        From the given referencing_parts, finds the record that matches the current instance.
        :param referencing_parts: All the parts that reference the "referenced_link_name".
        The info that contains the parts and their content
        :return: This part and its content
        """
        found_part = None
        existing_content = None
        for existing_part, existing_content in referencing_parts:
            if existing_part is self:
                found_part = existing_part
                break

        return found_part, existing_content
