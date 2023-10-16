# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: The part widgets that need event counter features use this module.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...scenario.defn_parts import BasePart, FunctionPart, ActorPart, SqlPart, PulsePart
from ..async_methods import AsyncRequest
from ..safe_slot import safe_slot
from ..gui_utils import ITEM_SPACE, EVENT_COUNTER_RECT_HEIGHT, try_disconnect
from .part_box_item import PartBoxItem
from .part_box_side_items import EventCounterItem

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'EventCounterManager'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class EventCounterManager:
    """
    The widgets that need event counter features derive from this class
    """

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- class-wide methods --------------------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self, part: BasePart, part_box_item: PartBoxItem = None):
        self.__part_box_item = part_box_item
        self._part = part
        self._event_counter_item = EventCounterItem(part_box_item, part_box_item)
        self._event_counter_item.setX(-ITEM_SPACE)
        self._event_counter_item.setY((self.ui.header_frame.height() - EVENT_COUNTER_RECT_HEIGHT) / 2)

        if self._part.PART_TYPE_NAME in 'actor':
            self._part.signals.sig_queue_actor_counters_changed.connect(self._slot_update_queue_indicators_actor)
        else:
            assert self._part.PART_TYPE_NAME in ('function', 'pulse', 'sql')
            self._part.exec_signals.sig_queue_counters_changed.connect(self._slot_queue_counters_changed)

        def __get_init_data():
            is_next, count_concur, count_after = part_box_item.part.get_queue_counts()
            return is_next, count_concur, count_after

        def __set_init_data(is_next, count_concur, count_after):
            self._queue_counters_changed(is_next, count_concur, count_after)

        AsyncRequest.call(__get_init_data, response_cb=__set_init_data)

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    def _queue_counters_changed(self, is_next: bool, count_concur_next: int, later_than_next: int):
        """
        Handles the event counter. See IExecutablePart.ExecSignals for more information.
        Shows one of three background colors and the text on it, depending on the combinations of the arguments.
        :param is_next:
        :param count_concur_next:
        :param later_than_next:
        """
        total_events = count_concur_next + later_than_next
        self._event_counter_item.setVisible(count_concur_next > 0 or later_than_next > 0)
        if is_next:
            self._event_counter_item.show_next(total_events)
        else:
            if count_concur_next > 0:
                self._event_counter_item.show_concurrent_next(total_events)
            else:
                self._event_counter_item.show_later_than_next(total_events)

    def _update_queue_indicators_actor(self):
        """
        The event queue indicators on a part are expensive to update because the counting has to traverse
        the scenario actor hierarchy. Hence this method is only called when the backend signals that the
        queue counts for the actor of this part item is "sufficiently" out of date.

        See ActorPart.Signals for more information.
        """
        # Colin TODO ASAP: check that this is correct
        #     Reason: Colin implemented this class
        # is_next, count_concur, count_after = self.__part_box_item.part.get_queue_counts()
        # self._queue_counters_changed(is_next, count_concur, count_after)
        AsyncRequest.call(self.__part_box_item.part.get_queue_counts, response_cb=self._queue_counters_changed)

    def _disconnect_all_slots(self):
        if self._part.PART_TYPE_NAME in 'actor':
            try_disconnect(self._part.signals.sig_queue_actor_counters_changed,
                           self._slot_update_queue_indicators_actor)
        else:
            assert self._part.PART_TYPE_NAME in ('function', 'pulse', 'sql')
            try_disconnect(self._part.exec_signals.sig_queue_counters_changed, self._slot_queue_counters_changed)

    _slot_update_queue_indicators_actor = safe_slot(_update_queue_indicators_actor)
    _slot_queue_counters_changed = safe_slot(_queue_counters_changed)

    # --------------------------- instance __SPECIAL__ method overrides -------------------------

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    # --------------------------- instance _PROTECTED properties and safe slots -----------------

    # --------------------------- instance __PRIVATE members-------------------------------------
