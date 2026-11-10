"""Per-line estimator approval rules and the fingerprints that bind a freeze to what was seen.

MH-06, T-4.2.2. Approval is per line, per permitted user. A line's approval fingerprint
covers its amount, wording and the content hashes of its evidence; the review
fingerprint covers every line, the email draft and the recipient details the freezing
user's screen displayed. Any difference at freeze time refuses the freeze (IT-06, IT-18).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

__all__ = [
    "MIN_EXPLANATION_CHARS",
    "EvidenceItem",
    "FreezeProblem",
    "LineSnapshot",
    "approval_blockers",
    "changed_components",
    "freeze_blockers",
    "line_fingerprint",
    "photo_content_hash",
    "reference_content_hash",
    "review_components",
    "review_fingerprint",
]

MIN_EXPLANATION_CHARS = 20


def _canonical(value: Any) -> bytes:
    def default(obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        raise TypeError(f"not canonical: {type(obj).__name__}")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=default).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    kind: str  # "photo" | "reference"
    content_hash: str


@dataclass(frozen=True)
class LineSnapshot:
    line_id: str
    row_version: int
    status: str
    match_state: str
    origin: str
    category: str
    description: str
    requested_cents: int
    hours_delta: Decimal | None
    explanation: str | None
    evidence: tuple[EvidenceItem, ...]
    approved_row_version: int | None = None
    approved_fingerprint: str | None = None


def photo_content_hash(*, sha256_hex: str, taken_by_shop: bool, attested: bool, attestation_note: str | None) -> str:
    return _sha({"sha256": sha256_hex, "taken_by_shop": taken_by_shop, "attested": attested, "note": attestation_note})


def reference_content_hash(fields: Mapping[str, Any]) -> str:
    keys = ("material_type", "publisher", "title", "identifier", "url", "accessed_on", "note")
    return _sha({k: (str(fields.get(k)) if fields.get(k) is not None else None) for k in keys})


def line_fingerprint(line: LineSnapshot) -> str:
    """SHA-256 over amount, wording and sorted evidence content hashes."""
    return _sha(
        {
            "category": line.category,
            "description": line.description,
            "requested_cents": line.requested_cents,
            "hours_delta": line.hours_delta,
            "explanation": line.explanation,
            "evidence": sorted(e.content_hash for e in line.evidence),
        }
    )


def approval_blockers(line: LineSnapshot) -> list[str]:
    """Reasons this line cannot be approved now (empty list means it can)."""
    problems: list[str] = []
    if line.match_state == "needs_review":
        problems.append("needs_review: resolve the pairing before approving")
    if not line.evidence:
        explanation = (line.explanation or "").strip()
        if len(explanation) < MIN_EXPLANATION_CHARS:
            problems.append(f"no attached evidence: a written explanation of at least {MIN_EXPLANATION_CHARS} characters is required")
    if line.requested_cents < 0:
        problems.append("requested amount is negative")
    return problems


def review_components(lines: Iterable[LineSnapshot], *, email_draft: str, recipient: Mapping[str, str | None]) -> dict[str, str]:
    """Per-item hashes of everything the review screen displays."""
    components: dict[str, str] = {}
    for line in lines:
        components[f"line:{line.line_id}"] = _sha(
            {
                "row_version": line.row_version,
                "status": line.status,
                "match_state": line.match_state,
                "origin": line.origin,
                "content": line_fingerprint(line),
            }
        )
    components["email_draft"] = _sha(email_draft)
    components["recipient"] = _sha(dict(recipient))
    return components


def review_fingerprint(components: Mapping[str, str]) -> str:
    return _sha(dict(components))


def changed_components(shown: Mapping[str, str], current: Mapping[str, str]) -> list[str]:
    names = set(shown) | set(current)
    return sorted(n for n in names if shown.get(n) != current.get(n))


@dataclass(frozen=True)
class FreezeProblem:
    item: str
    reason: str


def freeze_blockers(lines: Iterable[LineSnapshot]) -> list[FreezeProblem]:
    """Every included line must be approved, unchanged since approval and not needs_review."""
    problems: list[FreezeProblem] = []
    included = 0
    for line in sorted(lines, key=lambda x: x.line_id):
        if line.status == "excluded":
            continue
        included += 1
        item = f"line:{line.line_id}"
        if line.match_state == "needs_review":
            problems.append(FreezeProblem(item, "needs review"))
            continue
        if line.status != "approved":
            problems.append(FreezeProblem(item, "not approved"))
            continue
        if line.approved_row_version != line.row_version or line.approved_fingerprint != line_fingerprint(line):
            problems.append(FreezeProblem(item, "changed after approval"))
    if included == 0:
        problems.append(FreezeProblem("packet", "no included lines"))
    return problems
