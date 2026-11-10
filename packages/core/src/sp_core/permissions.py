"""Function-level permission table (schema section 5, PRD section 5, IT-02).

Only an Estimator or Owner of the tenant approves, excludes, freezes, marks or unmarks
sent. No Operator, Office user, job or model does. There is no "send" action at all.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = ["PERMISSIONS", "Action", "Role", "allowed"]


class Role(StrEnum):
    OWNER = "owner"
    ESTIMATOR = "estimator"
    OFFICE = "office"
    OPERATOR = "operator"  # vendor operator inside a tenant with an unexpired grant


class Action(StrEnum):
    READ = "read"
    EDIT_RO = "edit_ro"  # ROs, documents, parse corrections
    EDIT_LINE = "edit_line"  # supplement lines and evidence
    APPROVE_LINE = "approve_line"
    EXCLUDE_LINE = "exclude_line"
    FREEZE_PACKET = "freeze_packet"
    MARK_SENT = "mark_sent"
    UNMARK_SENT = "unmark_sent"
    RECORD_RESPONSE = "record_response"
    RECORD_PAYMENT = "record_payment"
    EDIT_BASELINE = "edit_baseline"
    TAKEDOWN = "takedown"


_ALL = frozenset(Role)
_SHOP_DECIDERS = frozenset({Role.OWNER, Role.ESTIMATOR})

PERMISSIONS: dict[Action, frozenset[Role]] = {
    Action.READ: _ALL,
    Action.EDIT_RO: frozenset({Role.OWNER, Role.ESTIMATOR, Role.OPERATOR}),
    Action.EDIT_LINE: frozenset({Role.OWNER, Role.ESTIMATOR, Role.OPERATOR}),
    Action.APPROVE_LINE: _SHOP_DECIDERS,
    Action.EXCLUDE_LINE: _SHOP_DECIDERS,
    Action.FREEZE_PACKET: _SHOP_DECIDERS,
    Action.MARK_SENT: _SHOP_DECIDERS,
    Action.UNMARK_SENT: _SHOP_DECIDERS,
    Action.RECORD_RESPONSE: _SHOP_DECIDERS,
    Action.RECORD_PAYMENT: frozenset({Role.OWNER, Role.OFFICE}),
    Action.EDIT_BASELINE: frozenset({Role.OWNER, Role.OFFICE}),
    Action.TAKEDOWN: frozenset({Role.OWNER}),
}


def allowed(role: Role, action: Action) -> bool:
    return role in PERMISSIONS[action]
