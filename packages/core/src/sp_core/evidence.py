"""Evidence rules for the licensed-content guard (MH-05, AD-06, Decision 3.1, IT-15).

Licensed repair material is reference-only. There is no procedure-document upload and
no URL for subscription-portal material. The product does not detect licensed content;
these checks enforce only the stated controls.
"""

from __future__ import annotations

from urllib.parse import urlparse

__all__ = [
    "FREE_TEXT_NOTICE",
    "MATERIAL_TYPES",
    "NOTE_MAX_CHARS",
    "NO_URL_MATERIAL_TYPES",
    "EvidenceError",
    "validate_photo_attestation",
    "validate_reference",
]

MATERIAL_TYPES = ("oem_procedure_subscription", "oem_position_statement", "estimating_guide", "industry_body", "other")
NO_URL_MATERIAL_TYPES = frozenset({"oem_procedure_subscription", "estimating_guide"})
NOTE_MAX_CHARS = 300
FREE_TEXT_NOTICE = "Do not paste procedure or estimating-guide text. Cite the document by title and identifier."


class EvidenceError(ValueError):
    pass


def validate_reference(*, material_type: str, publisher: str, title: str, url: str | None, note: str | None) -> None:
    if material_type not in MATERIAL_TYPES:
        raise EvidenceError("unknown material type")
    if not publisher.strip() or not title.strip():
        raise EvidenceError("publisher and title are required")
    if url is not None:
        if material_type in NO_URL_MATERIAL_TYPES:
            raise EvidenceError("a URL is not accepted for subscription-portal procedures or estimating guides; cite title and identifier")
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise EvidenceError("a reference URL must be an https URL to openly published material")
    if note is not None and len(note) > NOTE_MAX_CHARS:
        raise EvidenceError(f"note is limited to {NOTE_MAX_CHARS} characters")


def validate_photo_attestation(*, attested: bool | None, taken_by_shop: bool | None, attestation_note: str | None) -> None:
    """The attestation must be ticked explicitly (never pre-ticked) for every batch."""
    if attested is not True:
        raise EvidenceError(
            "tick the attestation: these are the shop's own photos of this vehicle, not screenshots or copies of licensed documents"
        )
    if taken_by_shop is None:
        raise EvidenceError("answer whether the shop took these photos")
    if taken_by_shop is False and not (attestation_note or "").strip():
        raise EvidenceError("explain the source of photos the shop did not take")
