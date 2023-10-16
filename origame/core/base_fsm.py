# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: Provide a generic Finite State Machine (FSM) base class for objects that have states

An object that has states should derive from IFsmOwner and is called "the FSM owner". Each of its states should 
derive from BaseFsmState. The default state should be set directly by the FSM owner by setting self._state to 
an instance of the proper state class. Transitions are the responsibility of each state: it should call 
self._set_state(StateClass) for a transition to occur. This will automatically update the FSM owner with the 
new state. State-dependent methods of the FSM owner should delegate to the currently active state. Each
state is assumed to have a numeric ID and string representation, typically achieved by creating a class that 
derives from IntEnum listing the possible state, and each state class defines state_id from one of these 
enum values. 

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from enum import IntEnum

# [2. third-party]

# [3. local]
from ..core import attrib_override_required, override_optional, override_required
from ..core.typing import AnnotationDeclarations

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------

__all__ = [
    # public API of module: one line per string
    'BaseFsmState',
    'IFsmOwner'
]

# -- Module-level objects -----------------------------------------------------------------------

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    BaseFsmState = 'BaseFsmState'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class IFsmOwner:
    """
    Any object that uses states should derive from this class. The _state attribute can be used by the derived 
    class to delegate method calls to the current state. 
    """

    def __init__(self):
        self._state = None

    def is_state(self, state_id: IntEnum) -> bool:
        """Return True if our current state has ID state_id, False otherwise"""
        return state_id == self._state.state_id

    def get_state_name(self) -> str:
        """Return current state name"""
        return self._state.state_name

    def get_state_id(self) -> IntEnum:
        """Return current state ID"""
        return self._state.state_id

    state_name = property(get_state_name)
    state_id = property(get_state_id)

    def _set_state(self, state: Decl.BaseFsmState):
        """
        Set the state of the FSM owner. After this is done, the _on_state_changed() is automatically called; derived
        class may override as necessary to get notified of state changes.
        :param state: new state
        """
        prev_state = self._state
        self._state = state
        self._on_state_changed(prev_state)

    @override_optional
    def _on_state_changed(self, prev_state: Decl.BaseFsmState):
        """
        Called automatically by _set_state() to indicate a state change. The new state is self._state.
        :param prev_state: the previous state
        """
        pass


class FsmOpUnavailable:
    """
    Return value proxy that automatically logs a warning when created and when called.
    """
    WARNING_IS_ERROR = True

    class Error(RuntimeError):
        pass

    def __init__(self, state_name: str, attr_name: str):
        msg = "state '{}' does not have an attribute called '{}'".format(state_name, attr_name)
        if self.WARNING_IS_ERROR:
            raise self.Error(msg)
        else:
            log.debug("WARNING: {}", msg)
        self.__state_name = state_name
        self.__attr_name = attr_name

    def __call__(self, *args, **kwargs):
        args = [str(arg) for arg in args]
        kwargs = ['{}={}'.format(k, v) for k, v in kwargs.items()]
        log.debug("WARNING: ignoring call of method {}({}) on state '{}'",
                  self.__attr_name, ', '.join(args + kwargs), self.__state_name)


class BaseFsmState:
    """
    Base class for all states of a FSM.

    Note:
    - derived class must override state_id
    - derived class can override the base versions of enter_state and exit_state.
    - FSM owner must provide _set_state() method
    """

    state_id = attrib_override_required(None)

    __state_name = None  # used by get_state_name()

    def __init__(self, prev_state: Decl.BaseFsmState, fsm_owner: IFsmOwner = None):
        """
        Initialize data for a new state. Set the previous state to None for the initial state, as this
        automatically calls self.enter_state().

        :param prev_state: previous state; if None, the enter_state() method is automatically called.
        :param fsm_owner: the object that owns the FSM for this state. It is assumed to have a _state
            attribute which will hold this instance.
        """

        assert self.state_id is not None

        self._fsm_owner = fsm_owner
        self._prev_state_class = prev_state.__class__
        if prev_state is None:
            log.debug('FSM {} initialized in {}', self.__get_fsm_owner_type_name(), self.state_id.name)
            self.enter_state(None)

    @override_optional
    def enter_state(self, prev_state: Decl.BaseFsmState):
        """
        This will be called automatically by _set_state() after the FSM owner has had its state data member
        reset to the new state, but before the previous state's exit_state() method is called. Most classes
        don't need to override this, but can be useful if some actions should be taken only after the FSM
        has new state.
        :param prev_state: state that is being exited
        """
        pass

    @override_optional
    def exit_state(self, new_state: Decl.BaseFsmState):
        """
        States that need to take action on exit can override this to cleanup etc. It is called automatically
        when a derived class calls _set_state, before entering new state.
        :param new_state: state being transitioned to
        """
        pass

    def get_state_name(self) -> str:
        """Get the name for this state. It is the string rep of enumeration constant returned by state_id()."""
        if self.__state_name is None:
            self.__state_name = str(self.state_id).split('.')[-1]
        return self.__state_name

    state_name = property(get_state_name)

    def __getattr__(self, attr_name: str):
        """Attempt to get an attribute (to read it or call it as a function) that does not exist in this state"""
        return FsmOpUnavailable(self.state_name, attr_name)

    def _unsupported_op(self, op_name: str):
        """
        A derived class that is base to other states can call this method when a method it provides was
        not overridden, indicating that the concrete state does not support it.
        """
        log.debug("WARNING: state '{}' does not have an attribute called '{}'", self.state_name, op_name)

    def _set_state(self, state_class, **kwargs):
        """
        Transition to a new state. Derived class must call this to cause a transition to a new state.
        The new state object is created from state_class, and set as fsm_data._state. Then _self.exit_state(new_state)
        is called, followed by new_state.enter_state(). Finally, the sig_state_changed signal is emitted.

        Note: If the current state cannot be exited, or the new state cannot be created or entered, the caller
        of this method will have to decide what to do.

        :param state_class: class to use for new state
        :param **kwargs: arguments to give to state constructor
        """
        # first create the new state, and set in FSM owner
        new_state = state_class(self, fsm_owner=self._fsm_owner, **kwargs) if state_class else None

        # if this worked, can exit current state
        log.debug("FSM {} exiting state {}", self.__get_fsm_owner_type_name(), self.state_name)
        self.exit_state(new_state)

        # and enter new state
        log.debug("FSM {} entering state {}", self.__get_fsm_owner_type_name(), new_state.state_name)
        self._fsm_owner._set_state(new_state)

        new_state.enter_state(self)

    def __get_fsm_owner_type_name(self) -> str:
        """Get class name of FSM owner"""
        return self._fsm_owner.__class__.__name__
