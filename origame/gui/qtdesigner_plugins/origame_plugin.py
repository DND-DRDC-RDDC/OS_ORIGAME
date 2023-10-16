# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Defines plugin classes for each Origame widget that must be usable from Qt Designer

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]
from PyQt5.QtWidgets import QWidget
from pyplugin_base import add_plugin

# -- Example Plugins --

# from origame.gui.actor_2d_view.part_widgets import ClockPart2dContent
# from origame.gui.actor_2d_view.Ui_button_part import Ui_ButtonPartWidget
#
# ExampleClockPartPlugin = add_plugin(ClockPart2dContent, "Clock Part (Example)", "..actor_2d_view.part_widgets")
# ExampleUi_ButtonPartWidgetPlugin = add_plugin(Ui_ButtonPartWidget, "Button Part (Example)", "..actor_2d_view.part_widgets")


# -- Actual plugins --

# plugin dependencies

from origame.gui.debugging.ops_panel import DebugOpsPanel
from origame.gui.scenario_browser.Ui_search_panel import Ui_ScenSearchPanel

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

# create each plugin here:

DebugOpsPlugin = add_plugin(DebugOpsPanel, "Debug Operations Panel", "origame.gui.debugging.ops_panel")
SearchPanelPlugin = add_plugin(Ui_ScenSearchPanel, "Search Panel", "origame.gui.scenario_browser")
