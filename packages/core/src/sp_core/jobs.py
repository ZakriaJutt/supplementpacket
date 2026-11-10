"""Job state machine with compare-and-set on ``state_version`` (TRD 8.5, R-01, UT-13)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["JOB_STATES", "TERMINAL_STATES", "TRANSITIONS", "Transition", "decide_transition"]

JOB_STATES = ("queued", "running", "succeeded", "failed", "partial")
TERMINAL_STATES = frozenset({"succeeded", "failed", "partial"})
TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running"}),
    "running": frozenset({"succeeded", "failed", "partial", "queued"}),
    "failed": frozenset({"queued"}),  # manual retry only
    "partial": frozenset({"queued"}),  # retry skips completed items
    "succeeded": frozenset(),
}


@dataclass(frozen=True)
class Transition:
    accepted: bool
    reason: str
    new_version: int | None = None


def decide_transition(current_state: str, current_version: int, target_state: str, based_on_version: int) -> Transition:
    """Accept only a transition computed from the current version; discard stale ones."""
    if based_on_version != current_version:
        return Transition(False, f"stale: event based on version {based_on_version}, current {current_version}")
    if target_state not in TRANSITIONS.get(current_state, frozenset()):
        return Transition(False, f"illegal transition {current_state} -> {target_state}")
    return Transition(True, "ok", current_version + 1)
