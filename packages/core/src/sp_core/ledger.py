"""The three-amount ledger: requested, insurer-approved, collected (MH-08).

The three amounts are separate fields and are never added together. Only the live
packet set (status ``frozen`` or ``sent``, never ``superseded``) counts, so a superseded
packet's approvals are never counted twice (UT-10, UT-17). Collected counts only
supplement payments that name a packet and carry a remittance document (UT-18).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

__all__ = [
    "LIVE_PACKET_STATUSES",
    "RESPONSE_STATUSES",
    "SUPPLEMENT_PAYMENT_KINDS",
    "LedgerPacket",
    "LedgerPacketLine",
    "LedgerPayment",
    "PaymentError",
    "ResponseError",
    "RoLedger",
    "compute_ro_ledger",
    "validate_response",
    "validate_supplement_payment",
]

LIVE_PACKET_STATUSES = frozenset({"frozen", "sent"})
RESPONSE_STATUSES = ("no_response", "approved_full", "approved_partial", "denied", "withdrawn", "preapproved")
SUPPLEMENT_PAYMENT_KINDS = frozenset({"supplement", "supplement_repayment"})
_NOT_REQUESTED = frozenset({"withdrawn", "preapproved"})


@dataclass(frozen=True)
class LedgerPacket:
    packet_id: str
    status: str


@dataclass(frozen=True)
class LedgerPacketLine:
    packet_id: str
    requested_cents: int
    response_status: str
    approved_cents: int | None
    origin: str = "diff"


@dataclass(frozen=True)
class LedgerPayment:
    payment_id: str
    packet_id: str | None
    kind: str
    amount_cents: int
    has_remittance_document: bool
    reverses_payment_id: str | None = None


@dataclass(frozen=True)
class RoLedger:
    requested_cents: int
    insurer_approved_cents: int
    collected_evidenced_cents: int
    recorded_not_evidenced_cents: int
    withdrawn_cents: int
    live_packet_ids: tuple[str, ...]


def _evidenced(payment: LedgerPayment, by_id: Mapping[str, LedgerPayment]) -> bool:
    """A reversal is classified like the payment it reverses."""
    seen: set[str] = set()
    current = payment
    while current.reverses_payment_id and current.reverses_payment_id in by_id:
        if current.payment_id in seen:
            break
        seen.add(current.payment_id)
        current = by_id[current.reverses_payment_id]
    return current.has_remittance_document


def compute_ro_ledger(
    packets: Iterable[LedgerPacket],
    packet_lines: Iterable[LedgerPacketLine],
    payments: Iterable[LedgerPayment],
) -> RoLedger:
    packet_list = list(packets)
    live = sorted(p.packet_id for p in packet_list if p.status in LIVE_PACKET_STATUSES)
    live_set = set(live)
    ro_packets = {p.packet_id for p in packet_list}

    requested = approved = withdrawn = 0
    for line in packet_lines:
        if line.packet_id not in live_set:
            continue
        if line.response_status == "withdrawn":
            withdrawn += line.requested_cents
        if line.response_status in _NOT_REQUESTED:
            continue
        requested += line.requested_cents
        approved += line.approved_cents or 0

    payment_list = list(payments)
    by_id = {p.payment_id: p for p in payment_list}
    evidenced = not_evidenced = 0
    for payment in payment_list:
        if payment.kind not in SUPPLEMENT_PAYMENT_KINDS:
            continue
        if payment.packet_id is None or payment.packet_id not in ro_packets:
            continue
        if _evidenced(payment, by_id):
            evidenced += payment.amount_cents
        else:
            not_evidenced += payment.amount_cents

    return RoLedger(
        requested_cents=requested,
        insurer_approved_cents=approved,
        collected_evidenced_cents=evidenced,
        recorded_not_evidenced_cents=not_evidenced,
        withdrawn_cents=withdrawn,
        live_packet_ids=tuple(live),
    )


class ResponseError(ValueError):
    pass


def validate_response(
    *,
    requested_cents: int,
    response_status: str,
    approved_cents: int | None,
    denial_reason: str | None = None,
    override_reason: str | None = None,
) -> int | None:
    """Return the approved amount to store, or raise ResponseError (UT-09)."""
    if response_status not in RESPONSE_STATUSES:
        raise ResponseError("unknown response status")
    if response_status == "no_response":
        return None
    if response_status in ("denied", "withdrawn", "preapproved"):
        if approved_cents not in (None, 0):
            raise ResponseError(f"{response_status} implies an insurer-approved amount of 0")
        if response_status == "denied" and not (denial_reason or "").strip():
            raise ResponseError("a denial needs a reason")
        return 0
    if approved_cents is None:
        if response_status == "approved_full":
            return requested_cents
        raise ResponseError("approved_partial needs an amount")
    if approved_cents < 0:
        raise ResponseError("insurer-approved amount cannot be negative")
    if response_status == "approved_full" and approved_cents != requested_cents:
        raise ResponseError("approved_full means insurer-approved equals requested")
    if response_status == "approved_partial" and approved_cents <= 0:
        raise ResponseError("approved_partial needs an amount above 0")
    if approved_cents > requested_cents and not (override_reason or "").strip():
        raise ResponseError("insurer-approved above requested needs an override reason")
    return approved_cents


class PaymentError(ValueError):
    pass


def validate_supplement_payment(
    *,
    kind: str,
    packet_id: str | None,
    amount_cents: int,
    reverses_payment_id: str | None,
    packet_insurer_approved_cents: int,
    packet_supplement_paid_cents: int,
    over_approved_reason: str | None,
) -> None:
    """Rules for a new payment row (MH-08, UT-18)."""
    if kind in SUPPLEMENT_PAYMENT_KINDS and packet_id is None:
        raise PaymentError("a supplement payment must name the packet it pays")
    if amount_cents == 0:
        raise PaymentError("amount cannot be 0")
    if amount_cents < 0 and reverses_payment_id is None and kind != "supplement_repayment":
        raise PaymentError("a negative amount is only allowed for a reversal or repayment")
    if kind in SUPPLEMENT_PAYMENT_KINDS and reverses_payment_id is None:
        cumulative = packet_supplement_paid_cents + amount_cents
        if cumulative > packet_insurer_approved_cents and not (over_approved_reason or "").strip():
            raise PaymentError("cumulative supplement payments on this packet exceed its insurer-approved total; give a reason")
