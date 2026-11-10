"""Generated email draft for a packet (MH-07, UT-19).

The draft is generated from the approved lines plus one free-text paragraph the
Estimator writes. It is refused if it contains a currency amount other than the
requested total. The product never sends it: the Estimator copies it and sends it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sp_core.money import MoneyFormatError, format_cents, parse_cents

__all__ = ["EmailDraft", "build_email_draft", "foreign_amounts"]

# Currency amounts: "USD 1,500", "$1,500.00", "1500 dollars", "US$ 12".
_AMOUNT_PATTERNS = (
    re.compile(r"(?:USD|US\$|\$)\s?(-?\d[\d,]*(?:\.\d{1,2})?)", re.IGNORECASE),
    re.compile(r"(-?\d[\d,]*(?:\.\d{1,2})?)\s?(?:USD|dollars?|bucks)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class EmailDraft:
    text: str
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems


def foreign_amounts(text: str, allowed_cents: int) -> list[str]:
    """Currency amounts in ``text`` other than ``allowed_cents``, as written."""
    found: list[str] = []
    for pattern in _AMOUNT_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1)
            try:
                cents = parse_cents(raw)
            except MoneyFormatError:
                found.append(match.group(0).strip())
                continue
            if cents != allowed_cents:
                found.append(match.group(0).strip())
    return sorted(set(found))


def build_email_draft(
    *,
    ro_number: str,
    claim_number: str | None,
    line_count: int,
    requested_total_cents: int,
    free_paragraph: str | None,
) -> EmailDraft:
    claim = f", claim {claim_number}" if claim_number else ""
    header = (
        f"Supplement request for RO {ro_number}{claim}: {line_count} "
        f"line{'s' if line_count != 1 else ''}, requested total "
        f"{format_cents(requested_total_cents, currency=True)} (excluding sales tax). "
        "The supplement packet is attached."
    )
    paragraph = (free_paragraph or "").strip()
    text = header if not paragraph else f"{header}\n\n{paragraph}"
    problems = tuple(f"amount not allowed in the email draft: {amount}" for amount in foreign_amounts(paragraph, requested_total_cents))
    return EmailDraft(text=text, problems=problems)
