# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Animation-related classes for backend

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging

# [2. third-party]

# [3. local]
from ..core.typing import AnnotationDeclarations

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'AnimationMode',
    'SharedAnimationModeReader'
]

log = logging.getLogger('system')


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class Decl(AnnotationDeclarations):
    SharedAnimationModeReader = 'SharedAnimationModeReader'


class AnimationMode:
    """
    Provides a container for animation mode flag so the flag can be safely shared between components.

    Sharing of the flag is achieved by controlling read/write access: objects that have access to an instance
    of this class can read and write the flag; but classes that have access to the reader can only read it.

    This class is designed to be created by the Scenario and used only by the SimController, and provides a
    SharedAnimationModeReader that all other components of the scenario use to determine if animation
    is currently on or off. If a scenario should not provide animation, then this class should not be
    instantiated (use None instead of an instance of AnimationMode).
    """

    def __init__(self):
        """Starts off as True."""
        self._anim_on = True
        self.set_state(True)

    def set_state(self, value: bool):
        """
        Set the state of animation to given value.
        :param value: new state
        """
        self._anim_on = value

    def get_reader(self) -> Decl.SharedAnimationModeReader:
        """Provide a reader for the animation mode. The reader gives read-only access to the mode state."""
        return SharedAnimationModeReader(self)

    def __bool__(self) -> bool:
        """
        Returns animation state. Enables instance to be used as pure boolean so that Console variant and tests can
        hardcode animation as pure boolean (True for tests, False for Console).
        """
        return self._anim_on

    def __eq__(self, other: bool) -> bool:
        """
        Returns whether animation state == 'other'. Allows comparisons of animation state to work regardless of
        whether animation state is an instance of this class (as in GUI variant) or a pure boolean (Console
        variant and most tests ('if anim_mode == other:' whether anim_mode is pure boolean or an instance of this
        class)."""
        return self._anim_on == other

    def __str__(self):
        return str(self._anim_on)

    reader = property(get_reader)


class SharedAnimationModeReader:
    """
    Allow scenario parts to read the scenario's animation mode, managed by the SimController.

    The class is designed as a boolean proxy: it pretends to be a boolean but in reality it merely wraps the
    boolean which is controlled by the SimController. Example of use:

        clas Foo:
            def __init__(self, anim_reader: SharedAnimationModeReader):
                self.__anim_mode = anim_reader
            def some_meth(self):
                ... change state, then:
                if self.__anim_mode:
                    sig_whatever.emit(...)
    """

    def __init__(self, anim_mode: AnimationMode):
        """The anim_mode must be obtained from the instance of AnimationMode controlled by scenario's SimController."""
        self.__anim_mode = anim_mode

    def __bool__(self) -> bool:
        """
        Return whether the animation mode is True or False. Allows replacement of this instance by hardcoded
        boolean without changing code (tests use hardcoded anim mode=True, Console variant uses False).
        """
        return bool(self.__anim_mode)
