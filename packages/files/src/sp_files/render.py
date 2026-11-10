"""Packet PDF rendering behind an interface (T-4.2.3, partly).

B1 ships a deterministic stand-in renderer: the same snapshot always gives the same
bytes and therefore the same SHA-256 (render_packet idempotency, TRD 8.5). The real
HTML-to-PDF template with WeasyPrint is not part of B1. User text is escaped and the
renderer fetches nothing.
"""

from __future__ import annotations

import html
import json
from typing import Any, Protocol

__all__ = ["DeterministicRenderer", "PacketRenderer"]


class PacketRenderer(Protocol):
    name: str

    def render(self, snapshot: dict[str, Any]) -> bytes: ...


class DeterministicRenderer:
    name = "deterministic-stand-in-1"

    def render(self, snapshot: dict[str, Any]) -> bytes:
        body = html.escape(json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str))
        return b"%PDF-1.4\n% SupplementPacket B1 stand-in render\n" + body.encode() + b"\n%%EOF\n"
