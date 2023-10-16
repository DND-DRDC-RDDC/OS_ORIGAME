# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module is used to provide Help from different places in Origame.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
from pathlib import Path
import logging

# [2. third-party]

# [3. local]


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    'PartHelp'
]

log = logging.getLogger('system')


# -- Class Definitions --------------------------------------------------------------------------


class PartHelp:
    import origame  # to find package path since docs stored there

    PART_SPECIFIC_HELP_DIR = str(Path(origame.__file__).with_name("docs")) + "\\user_manual_html"

    def __init__(self):
        self.__user_manual_part_lookup = {}
        self.__populate_user_manual_parts_lookup()

    def get_part_help_path(self, part_type: str) -> Path:
        """
        Method used to get the pathname for the file in the user manual describing the given part type.
        :param part_type: The type of part to get the help file path for.
        :return: A path string representing the user manual section describing the specified part_type.
        """
        part_specific_file = self.__user_manual_part_lookup[part_type]
        path = "file:///" + self.PART_SPECIFIC_HELP_DIR + "\\" + part_specific_file

        return path

    def __populate_user_manual_parts_lookup(self):
        """
        Method used to populate the dictionary that holds all part's html help file names that comprise the Origame
        User Manual.
        """
        self.__user_manual_part_lookup["actor"] = "actor_part_ref.html"
        self.__user_manual_part_lookup["button"] = "button_part_ref.html"
        self.__user_manual_part_lookup["clock"] = "clock_part_ref.html"
        self.__user_manual_part_lookup["datetime"] = "datetime_part_ref.html"
        self.__user_manual_part_lookup["data"] = "data_part_ref.html"
        self.__user_manual_part_lookup["function"] = "function_part_ref.html"
        self.__user_manual_part_lookup["hub"] = "hub_part_ref.html"
        self.__user_manual_part_lookup["info"] = "info_part_ref.html"
        self.__user_manual_part_lookup["multiplier"] = "multiplier_part_ref.html"
        self.__user_manual_part_lookup["node"] = "node_part_ref.html"
        self.__user_manual_part_lookup["part_frame"] = "index.html"
        self.__user_manual_part_lookup["part_link"] = "index.html"
        self.__user_manual_part_lookup["plot"] = "plot_part_ref.html"
        self.__user_manual_part_lookup["pulse"] = "pulse_part_ref.html"
        self.__user_manual_part_lookup["library"] = "library_part_ref.html"
        self.__user_manual_part_lookup["sheet"] = "sheet_part_ref.html"
        self.__user_manual_part_lookup["sql"] = "sql_part_ref.html"
        self.__user_manual_part_lookup["table"] = "table_part_ref.html"
        self.__user_manual_part_lookup["time"] = "time_part_ref.html"
        self.__user_manual_part_lookup["variable"] = "variable_part_ref.html"
        self.__user_manual_part_lookup["file"] = "file_part_ref.html"
