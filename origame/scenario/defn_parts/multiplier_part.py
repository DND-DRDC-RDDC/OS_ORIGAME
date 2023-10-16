# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This module defines the MultiplierPart class and the functionality that supports the part as
a building block for the Origame application.

The Multiplier Part allows for one-shot instigation of ASAP signalling of all parts it is linked to, or one-shot
instigation of direct calls to each part it is linked to.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ...core import override
from ...core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO
from ...core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

from ..event_queue import EventQueue
from ..ori import OriMultiplierPartKeys as MpKeys
from ..part_execs.iexecutable_part import IExecutablePart

from .actor_part import ActorPart
from .base_part import BasePart
from .common import Position
from .part_link import PartLink
from .part_types_info import register_new_part_type

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'MultiplierPart',
    'InvalidLinkingError'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class InvalidLinkingError(Exception):
    """
    This class is a custom error raised when a Multiplier part tries to call a part that doesn't
    implement the IExecutablePart interface.
    """
    pass


class MultiplierPart(BasePart, IExecutablePart):
    """
    This class defines the functionality required to support an Origame Multiplier Part.

    The Multiplier Part allows for one-shot instigation of ASAP signalling of all parts it is linked to, or one-shot
    instigation of direct calls to each part it is linked to.

    The MultiplierPart, along with all of its target objects, implements the IExecutablePart interface. One call
    made on the MultiplierPart interface is propagated identically to all of its target parts.
    """

    SHOW_FRAME = False
    RESIZABLE_FRAME = False
    CAN_BE_LINK_SOURCE = True
    DEFAULT_VISUAL_SIZE = dict(width=1.5, height=1.5)
    MIN_CONTENT_SIZE = DEFAULT_VISUAL_SIZE
    PART_TYPE_NAME = "multiplier"
    DESCRIPTION = """\
        Use this part to signal or call many parts at once.

        A part that is linked to a multiplier part can call or signal all parts linked from the multiplier part
        by simply signaling the multiplier part."""

    def __init__(self, parent: ActorPart, name: str = None, position: Position = None):
        IExecutablePart.__init__(self)
        BasePart.__init__(self, parent, name=name, position=position)
        self.__linking_changed = True
        self.__sorted_outgoing_links = []

        if parent:
            self._sim_controller = self._shared_scenario_state.sim_controller

    @override(IExecutablePart)
    def get_parameters(self) -> str:
        """
        Gets the parameters of the part at the end of the link chain.
        """
        for link in self.part_frame.get_outgoing_links():
            part = link.target_part_frame.part.get_as_link_target_part()
            self.__assert_type_executable(part)

            # Design decision: we only check the first part because this is used to support button part triggering
            # mechanism and the button part requires the same parameter for all the target parts
            return part.parameters

    @override(BasePart)
    def on_removing_from_scenario(self, scen_data: Dict[BasePart, Any], restorable: bool = False):
        BasePart.on_removing_from_scenario(self, scen_data, restorable=restorable)
        IExecutablePart.on_removed_from_scenario(self, scen_data, restorable=restorable)

    @override(BasePart)
    def on_restored_to_scenario(self, scen_data: Dict[BasePart, Any]):
        BasePart.on_restored_to_scenario(self, scen_data)
        IExecutablePart.on_restored_to_scenario(self, scen_data)

    @override(BasePart)
    def on_outgoing_link_added(self, link: PartLink):
        """
        This type of part calls target part of each link, but order of links is not guaranteed by the part frame
        *across separate application runs* (see discussions about PYTHONHASHSEED). The trick is to sort the
        links by name; this works because the names are guaranteed unique. This method allows the sorting to
        occur only the first time called and when linking has changed.
        """
        self.__linking_changed = True

    @override(BasePart)
    def on_outgoing_link_removed(self, link: PartLink):
        """See docstring for MultiplierPart.on_outgoing_link_added()."""
        self.__linking_changed = True

    # --------------------------- instance PUBLIC properties ----------------------------
    parameters = property(get_parameters)

    # --------------------------- CLASS META data for public API ------------------------

    META_AUTO_EDITING_API_EXTEND = ()
    META_AUTO_SCRIPTING_API_EXTEND = (parameters, get_parameters, )

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override(IExecutablePart)
    def _exec(self, _debug_mode: bool, _as_signal: bool, *args, **kwargs):
        """
        This function is an override of the base interface class' function. It is called when the current instance
        is either signalled or called directly, to execute. If signalled to execute, this instance, in turn,
        adds ASAP events to the event queue to signal each part its outgoing links point to. If called to execute, this
        instance, in turn, calls each part its outgoing links point to.
        :param _debug_mode: True if execution is currently in Debug mode; False otherwise.
        :param _as_signal: True if this function is called as a result of a signal; False if the function was called
            directly.
        :param args: The arguments to be passed to the target Parts of the outgoing links.
        :param kwargs: Additional arguments to be passed to the target Parts of the outgoing links.
        """

        if self.__linking_changed:
            # need to re-sort the links; use name since this is the only repeatable keys (session IDs are not)
            self.__sorted_outgoing_links = list(self.part_frame.get_outgoing_links())
            self.__sorted_outgoing_links.sort(key=lambda x: x.name)
            self.__linking_changed = False

        if _as_signal:
            # Signal all parts pointed at by outgoing links.
            for link in self.__sorted_outgoing_links:
                part = link.target_part_frame.part.get_as_link_target_part()
                if part is not None:
                    self._sim_controller.add_event(iexec_part=part, args=args,
                                                   priority=EventQueue.ASAP_PRIORITY_VALUE)
                else:
                    log.warning("Resolved link target from {} is None, used by multipler {}: can't signal",
                                link.target_part_frame.part, self)

        else:
            # Call all parts pointed at by outgoing links.
            for link in self.__sorted_outgoing_links:
                part = link.target_part_frame.part.get_as_link_target_part()
                self.__assert_type_executable(part)

                try:
                    part.call(*args, _debug_mode=_debug_mode, **kwargs)

                except Exception as e:
                    log.warning("Multiplier Part exception while calling target part: {}. Error: {}", part, str(e))
                    raise

    # --------------------------- instance __PRIVATE members-------------------------------------
    def __assert_type_executable(self, part: BasePart):
        """
        Asserts the given part is an instance of IExecutablePart.
        :param part: To be asserted
        :raises: InvalidLinkingError
        """
        if not isinstance(part, IExecutablePart):
            msg = "Invalid part linking. Multiplier part {} should not be linked to part {}. " \
                  "Multiplier parts should only be linked to parts that are 'executable'."
            log.error(msg, self, (part or '<none>'))
            raise InvalidLinkingError(msg.format(self, part))

""" Add this part to the global part type/class lookup dictionary. """
register_new_part_type(MultiplierPart, MpKeys.PART_TYPE_MULTIPLIER)
