# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module is a stub module for the Prototype's pyor.py module. It contains
classes that can be used to unpickle data from prototype scenario, without relying on prototype
source code (by telling pickle to get these unpickle these classes from here!).

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------


# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module
    'link_props_manager',
    'link_props'
]


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class link_props:
    def __init__(self):
        self.Short = False
        self.Bold = False
        self.Hidden = False


class link_props_manager(object):
    def __init__(self):
        self.Settings = {}
