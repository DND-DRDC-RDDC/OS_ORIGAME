# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Components related to control, status and settings of main and batch simulation.

Version History: See SVN log.
"""

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5788$"

__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- PUBLIC API ---------------------------------------------------------------------------------
# import *public* symbols (classes/functions/constants) from contained modules:

from .alerts_manager import AlertsPanel
