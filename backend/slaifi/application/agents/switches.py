"""Per-agent on/off switches, kept in SLAIFI's own settings table and audited."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from datetime import UTC, datetime

from slaifi.application.contracts import AGENT_INFO, AgentName, AgentStatus, FinanceStore

_KEY = "agent.{}.enabled"
# The Financial agent took over from the Optimization agent that SLAIFI used earlier: a choice the
# person saved under the old name still counts until they save one under the new name.
_LEGACY_KEY = {AgentName.FINANCIAL: "agent.optimization.enabled"}


class AgentSwitches:
    """Whether each optional SLAI agent may be used, and how its last use went.

    The first-start default comes from configuration; once the person flips a switch in Settings
    their choice is stored and wins. Nothing here starts an agent: adapters ask ``is_enabled`` on
    every call and report back with ``note_result``.
    """

    def __init__(
        self,
        store: FinanceStore,
        defaults: Mapping[AgentName, bool],
        *,
        slai_enabled: bool = True,
    ) -> None:
        self._store = store
        self._defaults = dict(defaults)
        self._slai_enabled = slai_enabled
        self._lock = threading.Lock()
        self._last: dict[AgentName, tuple[bool, str | None]] = {}

    @staticmethod
    def _name(name: str | AgentName) -> AgentName:
        try:
            return AgentName(name)
        except ValueError as exc:
            raise KeyError(name) from exc

    def is_enabled(self, name: str | AgentName) -> bool:
        agent = self._name(name)
        if not self._slai_enabled:
            return False
        stored = self._store.get_setting(_KEY.format(agent.value))
        if stored is None and agent in _LEGACY_KEY:
            stored = self._store.get_setting(_LEGACY_KEY[agent])
        if stored is None:
            return bool(self._defaults.get(agent, False))
        return stored == "1"

    def set_enabled(
        self, name: str | AgentName, enabled: bool, *, now: datetime | None = None
    ) -> AgentStatus:
        agent = self._name(name)
        with self._store.transaction():
            self._store.set_setting(_KEY.format(agent.value), "1" if enabled else "0")
            self._store.append_audit(
                at=now or datetime.now(UTC),
                actor="user",
                action="agent.enabled" if enabled else "agent.disabled",
                subject=f"agent:{agent.value}",
                detail={"enabled": enabled},
            )
        with self._lock:
            self._last.pop(agent, None)  # a fresh choice starts from "not used yet"
        return self.status(agent)

    def note_result(self, name: str | AgentName, ok: bool, detail: str | None = None) -> None:
        agent = self._name(name)
        with self._lock:
            self._last[agent] = (ok, None if ok else detail)

    def status(self, name: str | AgentName) -> AgentStatus:
        agent = self._name(name)
        label, purpose = AGENT_INFO[agent]
        if not self._slai_enabled:
            return AgentStatus(
                agent.value, label, purpose, False, "disabled",
                "The SLAI integration is switched off in the configuration.",
            )  # fmt: skip
        if not self.is_enabled(agent):
            return AgentStatus(agent.value, label, purpose, False, "disabled", None)
        with self._lock:
            last = self._last.get(agent)
        if last is None:
            return AgentStatus(agent.value, label, purpose, True, "untested", "Not used yet.")
        ok, detail = last
        if ok:
            return AgentStatus(agent.value, label, purpose, True, "ready", None)
        return AgentStatus(agent.value, label, purpose, True, "unavailable", detail)

    def all_statuses(self) -> list[AgentStatus]:
        return [self.status(agent) for agent in AgentName]
