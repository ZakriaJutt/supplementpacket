"""Money helpers. The only place amounts are parsed, rounded or formatted (R-03, AD-08).

Amounts are integer cents. Intermediate arithmetic (hours x rate, ratios) uses
``fractions.Fraction`` and is rounded once, half away from zero, to the cent.
"""

from __future__ import annotations

import re
from decimal import Decimal
from fractions import Fraction

__all__ = [
    "MoneyFormatError",
    "format_cents",
    "hours_times_rate_cents",
    "parse_cents",
    "round_half_up",
]

_AMOUNT_RE = re.compile(r"^(-)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?$")


class MoneyFormatError(ValueError):
    """Raised when a string is not an exact amount in dollars and cents."""


def parse_cents(text: str) -> int:
    """Parse "1,284.50" -> 128450, "0.1" -> 10, "-3.00" -> -300. No floats involved."""
    candidate = text.strip().removeprefix("USD").strip().replace("$", "", 1)
    match = _AMOUNT_RE.match(candidate)
    if match is None:
        raise MoneyFormatError("not an exact amount")
    sign, whole, frac = match.groups()
    value = int(whole.replace(",", "")) * 100 + int((frac or "0").ljust(2, "0"))
    return -value if sign else value


def format_cents(cents: int, *, currency: bool = False) -> str:
    """Format 128450 -> "1,284.50" (or "USD 1,284.50"); exact inverse of :func:`parse_cents`."""
    if not isinstance(cents, int) or isinstance(cents, bool):
        raise TypeError("cents must be int")
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    text = f"{sign}{whole:,}.{frac:02d}"
    return f"USD {text}" if currency else text


def round_half_up(value: Fraction | Decimal | int) -> int:
    """Round an exact value to an integer, halves away from zero. Never uses floats."""
    exact = Fraction(value)
    sign = -1 if exact < 0 else 1
    absolute = abs(exact)
    whole = absolute.numerator // absolute.denominator
    if absolute - whole >= Fraction(1, 2):
        whole += 1
    return sign * whole


def hours_times_rate_cents(hours: Decimal, rate_cents: int) -> int:
    """Hours (numeric(6,2)) times an hourly rate in cents, rounded half up once."""
    return round_half_up(Fraction(hours) * rate_cents)


def round_down(value: Fraction | Decimal | int) -> int:
    """Floor of an exact value (towards minus infinity)."""
    exact = Fraction(value)
    return exact.numerator // exact.denominator


def round_up(value: Fraction | Decimal | int) -> int:
    """Ceiling of an exact value (towards plus infinity)."""
    exact = Fraction(value)
    return -((-exact.numerator) // exact.denominator)


def cents_from_input(value: object, *, field: str = "amount", allow_negative: bool = False) -> int:
    """Accept integer cents as a JSON integer or a string of digits; refuse floats, bools, decimals (B1-009)."""
    if isinstance(value, bool) or value is None:
        raise MoneyFormatError(f"{field} must be integer cents")
    if isinstance(value, int):
        cents = value
    elif isinstance(value, str) and re.fullmatch(r"-?\d{1,15}", value.strip()):
        cents = int(value.strip())
    else:
        raise MoneyFormatError(f"{field} must be integer cents (a JSON integer or a string of digits), not {type(value).__name__}")
    if cents < 0 and not allow_negative:
        raise MoneyFormatError(f"{field} cannot be negative")
    if abs(cents) > 10**15:
        raise MoneyFormatError(f"{field} is out of range")
    return cents


__all__ += ["cents_from_input", "round_down", "round_up"]
