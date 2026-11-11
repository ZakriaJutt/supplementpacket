"""Integration-only fixtures."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text


@pytest.fixture(autouse=True)
def _fresh_throttle(owner_engine: Any) -> None:
    """Every TestClient request comes from the same address; each test starts with empty sign-in counters."""
    with owner_engine.begin() as conn:
        conn.execute(text("DELETE FROM auth_throttle"))
