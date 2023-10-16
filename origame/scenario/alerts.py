# This file is part of Origame. See the __license__ variable below for licensing information.
#
# This file is provided AS IS with NO WARRANTY OF ANY KIND, INCLUDING THE
# WARRANTY OF DESIGN, MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE.
#
# For coding standards that apply to this file, see the project's Coding Standards document,
# r4_coding_standards.html, in the project's docs/CodingStandards/html folder.

"""
*Project - R4 HR TDP*: This class is used to control the behaviour of error indicator for those
parts that can show these buttons.

Version History: See SVN log.
"""

# -- Imports ------------------------------------------------------------------------------------

# [1. standard library]
import logging
from contextlib import contextmanager
from enum import Enum

# [2. third-party]

# [3. local]
from ..core import BridgeSignal, BridgeEmitter, override_optional, override, override_required
from ..core.typing import Any, Either, Optional, Callable, PathType, TextIO, BinaryIO, AnnotationDeclarations
from ..core.typing import List, Tuple, Sequence, Set, Dict, Iterable, Stream

# -- Meta-data ----------------------------------------------------------------------------------

__version__ = "$Revision: 5800$"
__license__ = """This file can ONLY be copied, used or modified according to the terms and conditions
                 described in the LICENSE.txt located in the root folder of the Origame package."""
__copyright__ = "(c) Her Majesty the Queen in Right of Canada"

# -- Module-level objects -----------------------------------------------------------------------


__all__ = [
    # public API of module: one line per string
    'IScenAlertSource',
    'ScenAlertLevelEnum',
    'ScenAlertManageEnum',
    'ScenAlertInfo',
]

log = logging.getLogger('system')


class Decl(AnnotationDeclarations):
    IScenAlertSource = 'IScenAlertSource'


# -- Function definitions -----------------------------------------------------------------------


# -- Class Definitions --------------------------------------------------------------------------

class ScenAlertLevelEnum(Enum):
    """Alerts have a level; the higher the level, the more severe the alert should be considered."""

    warning, error = range(2)


class ScenAlertManageEnum(Enum):
    """
    Ways that alerts are managed. Those that are auto managed are automatically generated and removed
    without user intervention. The on-demand alerts are only added and removed when the user causes a
    call to IScenAlertSource.check_ondemand_alerts().
    """

    auto, on_demand = range(2)


class ScenAlertInfo:
    """Represent all the information for a given Alert."""

    def __init__(self, level: ScenAlertLevelEnum, category: Enum, msg: str,
                 source: Decl.IScenAlertSource, auto: bool, **err_data):
        self.level = level
        self.category = category
        self.msg = msg
        self.source = source
        assert len(ScenAlertManageEnum) == 2
        self.manage = ScenAlertManageEnum.auto if auto else ScenAlertManageEnum.on_demand
        self.err_data = err_data


class IScenAlertSource:
    """
    Base class for scenario objects that support Alerts. It provides methods to add and clear alerts, and
    has the concept of a "parent" source that gets notified of new alerts in a child (recursively). Therefore
    it has the notion of "own" alerts vs alerts from descendant sources. It also
    provides methods to check and clear on-demand alerts, and emits signal when alerts added or removed.
    """

    class AlertSignals(BridgeEmitter):
        sig_alert_status_changed = BridgeSignal()

    # --------------------------- class-wide data and signals -----------------------------------
    # --------------------------- instance (self) PUBLIC methods --------------------------------

    def __init__(self):
        self.alert_signals = IScenAlertSource.AlertSignals()
        self.__alerts = set()
        self.__propagating_to_children = False
        self._source_name = None

    def get_alerts(self, level: ScenAlertLevelEnum = None,
                   category: Enum = None, manage: ScenAlertManageEnum = None) -> Set[ScenAlertInfo]:
        """
        Get the currently stored alerts for this source.
        :param level: the level to filter for; only alerts *at* that level will be returned
        :param category: the category to filter for
        :param manage: the management flag to filter for
        :return: the set of alerts that satisfy the set of filters given (or all alerts, if no filtering)
        """
        container = self.__alerts

        if level is not None:
            container = [err for err in container if err.level == level]

        if manage is not None:
            container = [err for err in container if err.manage == manage]

        if category is not None:
            container = [err for err in container if err.category == category]

        # return results; must not be the self container
        container = container.copy() if container is self.__alerts else set(container)
        assert container is not self.__alerts
        return container

    def has_alerts(self, level: ScenAlertLevelEnum = None,
                   category: Enum = None, manage: ScenAlertManageEnum = None) -> bool:
        """
        :param level: the level to filter for; only alerts *at* that level will be returned
        :param category: the category to filter for
        :param manage: the management flag to filter for
        :return: True if there are any alerts with given filter criteria (or any alerts at all, if no filtering).
        """
        return bool(self.get_alerts(level=level, category=category, manage=manage))

    def check_ondemand_alerts(self):
        """
        Clear alerts specific to this source, then recheck. If this source has children sources, propagates the
        check to children, recursively. However, only emits sig_alert_status_changed once all descendants have
        been cleared and re-checked (instead of once for *every* descendant that has alerts that will get
        cleared and/or added).

        Note: to define the alerts to check for, override _on_get_ondemand_alerts (do not override check_ondemand_alerts!)
        """
        children_sources = self._get_children_alert_sources()
        if children_sources:
            with self.__one_alert_signal():
                self._clear_own_alerts(manage=ScenAlertManageEnum.on_demand)
                self._on_get_ondemand_alerts()
                for child in children_sources:
                    child.check_ondemand_alerts()

        else:
            self._clear_own_alerts(manage=ScenAlertManageEnum.on_demand)
            self._on_get_ondemand_alerts()

    def clear_ondemand_alerts(self):
        """
        Override so that if called by the check_ondemand_alerts(), sig_alert_status_changed will be
        emitted only once (instead of once for *every* descendant (child within its domain) that has alerts
        that will get cleared).
        """
        children_sources = self._get_children_alert_sources()
        if not children_sources:
            # then just clear own alerts, no propagation necessary
            self._clear_own_alerts(manage=ScenAlertManageEnum.on_demand)

        elif self.__propagating_to_children:
            # then have children, but method was called from check_ondemand_alerts() which handles traversal of tree
            # so do not propagate clearing to children:
            self._clear_own_alerts(manage=ScenAlertManageEnum.on_demand)

        else:
            # have children and direct call: must propagate to children.
            # use "with" block to emit sig_alert_status_changed only after all cleared (without it, every descendant
            # will cause emission, which will scale as N^2 children.
            with self.__one_alert_signal():
                self._clear_own_alerts(manage=ScenAlertManageEnum.on_demand)
                for child in children_sources:
                    child.clear_ondemand_alerts()

    def get_source_name(self) -> str:
        """
        Gets the ready-made source name
        :return: A user-friendly name.
        """
        if self._source_name is None:
            source_name = str(self)
            log.warning('_get_source_name has not been implemented by this alert source "{}"', source_name)
            return str(self)

        return self._source_name

    # --------------------------- instance PUBLIC properties and safe_slots ---------------------

    source_name = property(get_source_name)

    # --------------------------- instance _PROTECTED and _INTERNAL methods ---------------------

    @override_optional
    def _get_source_name(self) -> str:
        """
        All derived classes should implement this function in order to return a user-friendly name. Otherwise, a
        Python generated name is returned.
        
        The rationale is that the _add_alert will call this function to produce a ready-made name. A source like Part
        needs to produce a full path. The full path operation must be done at the backend. An async request would 
        have to be sent out on each part. That would make it inefficient for the alert panel to populate the
        "Component" column.
        
        When a ready-made is produced, the front end can simply call .source_name on any IScenAlertSource instances.
        
        :return: A user-friendly name.
        """
        self._source_name = None
        return self._source_name

    @override_optional
    def _get_alert_parent(self) -> Decl.IScenAlertSource:
        """If alerts should be propagated up to a "parent" alert source, override this method to return it"""
        return None

    @override_optional
    def _get_children_alert_sources(self) -> List[Decl.IScenAlertSource]:
        """
        Get any children sources that can provide alerts. This is called automatically by check_ondemand_alerts()
        and clear_ondemand_alerts(). A child source of alerts is an attribute of self that references an object
        that derives from IScenAlertSource: in that case, the root source recursively transmits requests to check
        or clear alerts to child sources.
        """
        return None

    @override_optional
    def _on_get_ondemand_alerts(self):
        """
        Override this completely in derived classes that can perform on-demand validation checks. The override
        should call self._add_ondemand_alert(...) for every alert.
        """
        return

    @override_optional
    def _notify_alert_changes(self) -> bool:
        """
        Returns True only if sig_alert_status_changed should be emitted when alerts added/removed. Derived classes
        should override this if there are situations where self should not emit the signal (such as if sim animation
        mode is off, or if suspending propagation to children).
        """
        return not self.__propagating_to_children

    def _add_alert(self, level: ScenAlertLevelEnum, category: Enum, message: str,
                   auto: bool = True, **err_data) -> ScenAlertInfo:
        """
        Add an alert.
        :param level: the (severity) level of the alert
        :param category: the category of the alert; categories are arbitrarily defined by derived classes and
            used only for filtering.
        :param message: the text message for the alert
        :param auto: True if the alert is an automatically managed one, False if it is on-demand only. False should
            be used only when the alert is added as a result of an on-demand check.
        :param err_data: additional data to put in the alert
        :return: the alert instantiated
        """
        alert = ScenAlertInfo(level, category, message, self, auto, **err_data)
        self.__alerts.add(alert)
        if self._notify_alert_changes():
            self.alert_signals.sig_alert_status_changed.emit()

        # propagate up the chain of parents:
        alert_parent = self._get_alert_parent()
        if alert_parent is not None:
            alert_parent.__add_child_alert(alert)

        self._source_name = self._get_source_name()
        return alert

    def _add_ondemand_alert(self, level: ScenAlertLevelEnum, category: Enum, message: str, **err_data):
        """Convenience method for adding on-demand alerts"""
        self._add_alert(level, category, message, auto=False, **err_data)

    def _clear_own_alerts(self, *categories: List[Enum], level: ScenAlertLevelEnum = None,
                          manage: ScenAlertManageEnum = None):
        """
        Clear alerts of this source. Does not clear alerts from children sources.
        :param categories: the categories of alerts to clear
        :param level: the level of alerts to clear
        :param manage: the management type of alerts clear

        Only clears alerts that satisfy all non-None conditions.
        """
        if not self.__alerts:
            return

        remove_alerts = set(alert for alert in self.__alerts if alert.source is self)
        if level is not None:
            remove_alerts = set(err for err in remove_alerts if err.level == level)
        if categories:
            remove_alerts = set(err for err in remove_alerts if err.category in categories)
        if manage is not None:
            remove_alerts = set(err for err in remove_alerts if err.manage == manage)

        if remove_alerts is self.__alerts:
            self.__alerts = set()
        else:
            self.__alerts.difference_update(remove_alerts)

        if remove_alerts:
            if self._notify_alert_changes():
                self.alert_signals.sig_alert_status_changed.emit()

            # propagate up the chain of parents:
            alert_parent = self._get_alert_parent()
            if alert_parent is not None:
                alert_parent.__remove_child_alerts(remove_alerts)

    def _clear_all_own_alerts(self):
        """
        Clear all alerts specific to this source, regardless of level, category or management type.
        """
        if not self.__alerts:
            return

        remove_alerts = set(alert for alert in self.__alerts if alert.source is self)
        self.__alerts.difference_update(remove_alerts)
        if self._notify_alert_changes():
            self.alert_signals.sig_alert_status_changed.emit()

        # propagate up the chain of parents:
        alert_parent = self._get_alert_parent()
        if alert_parent is not None:
            alert_parent.__remove_child_alerts(remove_alerts)

    # --------------------------- instance __PRIVATE members-------------------------------------

    def __add_child_alert(self, alert: ScenAlertInfo):
        """Add the given alert. Assumes called by a child."""
        self.__alerts.add(alert)
        if self._notify_alert_changes():
            self.alert_signals.sig_alert_status_changed.emit()

        # propagate up the chain of parents:
        alert_parent = self._get_alert_parent()
        if alert_parent is not None:
            alert_parent.__add_child_alert(alert)

    def __remove_child_alerts(self, alerts: Set[ScenAlertInfo]):
        """
        Remove a set of alerts. Assumes each alert of the set was added via __add_child_alert(). Alerts from
        the set that are not in this source do not cause an error.
        """
        self.__alerts.difference_update(alerts)
        if self._notify_alert_changes():
            self.alert_signals.sig_alert_status_changed.emit()

        # propagate up the chain of parents:
        alert_parent = self._get_alert_parent()
        if alert_parent is not None:
            alert_parent.__remove_child_alerts(alerts)

    def __check_ondemand_alerts(self):
        """
        Clear any current on-demand alerts and run a new check. This assumes that derived class has overridden
        _on_get_ondemand_alerts() to perform whatever check are support by this alert source.
        """
        self.clear_ondemand_alerts()
        self._on_get_ondemand_alerts()

    @contextmanager
    def __one_alert_signal(self):
        """
        Context manager that can be used to automatically suspend emission of sig_alert_status_changed, and
        automatically emit only at exit of the "with" block.
        """
        # entry:
        orig_val = self.__propagating_to_children
        self.__propagating_to_children = True

        yield

        # exit:
        self.__propagating_to_children = orig_val
        if self._notify_alert_changes():
            self.alert_signals.sig_alert_status_changed.emit()
