"""Shared value parsing for uploaded business files: amounts, dates, currencies, booleans, text decoding, and safe
CSV export. Pure functions (no database), used by the profit investigation's ingestion (profit/ingest.py), quotes
and exports. The former invoice-import pipeline of the collections ledger was removed.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

# ISO 4217 codes we accept, with their minor-unit exponent.
CURRENCY_EXPONENT = {"EGP": 2, "USD": 2, "EUR": 2, "GBP": 2, "SAR": 2, "AED": 2, "QAR": 2, "KWD": 3, "BHD": 3,
                     "OMR": 3, "JOD": 3, "TND": 3, "MAD": 2, "LBP": 2, "TRY": 2, "CNY": 2, "INR": 2, "JPY": 0,
                     "CHF": 2, "CAD": 2, "AUD": 2}
_CURRENCY_ALIASES = {"ج.م": "EGP", "ج م": "EGP", "جنيه": "EGP", "جنيه مصري": "EGP", "le": "EGP", "l.e": "EGP",
                     "l.e.": "EGP", "e£": "EGP", "egp": "EGP", "us$": "USD", "dollar": "USD", "دولار": "USD",
                     "€": "EUR", "euro": "EUR", "يورو": "EUR", "£": "GBP", "ر.س": "SAR", "ريال": "SAR",
                     "د.إ": "AED", "درهم": "AED"}

_TRUE = {"1", "true", "yes", "y", "open", "disputed", "active", "نعم", "اه", "أيوه", "ايوه", "صح"}
_FALSE = {"0", "false", "no", "n", "none", "resolved", "closed", "", "لا", "لأ"}
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
_FORMULA_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def _norm_header(h: str) -> str:
    h = unicodedata.normalize("NFKC", h or "").strip().lower().lstrip("﻿")
    return re.sub(r"[\s_]+", " ", h)


def decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1256"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("file is not UTF-8 or Windows-1256 text")


def _clean(value: str | None) -> str:
    return unicodedata.normalize("NFKC", (value or "")).strip()


def parse_amount(text: str, exponent: int) -> int:
    """'12,450.50' / '١٢٬٤٥٠٫٥٠' / 'EGP 1,200' -> minor units. Raises ValueError."""
    t = _clean(text).translate(_ARABIC_DIGITS)
    if not re.search(r"\d", t):
        raise ValueError("not a number")
    t = re.sub(r"[^\d.,\-()]", "", t)
    negative = t.startswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("-()")
    if not t:
        raise ValueError("empty")
    if "," in t and "." in t:
        t = t.replace(",", "")
    elif "," in t:
        # '1,200' (thousands) vs '1200,50' (decimal comma): decimal comma only if exactly 1-2 digits follow.
        parts = t.split(",")
        t = t.replace(",", ".") if len(parts) == 2 and 1 <= len(parts[1]) <= 2 else t.replace(",", "")
    try:
        value = Decimal(t)
    except InvalidOperation as exc:
        raise ValueError("not a number") from exc
    if negative:
        value = -value
    scaled = value * (10 ** exponent)
    if scaled != scaled.to_integral_value():
        raise ValueError(f"more than {exponent} decimal places")
    return int(scaled)


def parse_date(text: str, fmt: str) -> tuple[date, bool]:
    """Returns (date, ambiguous). fmt: auto | DMY | MDY | YMD. auto = ISO, else day-first (Egyptian convention)."""
    t = _clean(text).translate(_ARABIC_DIGITS)
    if not t:
        raise ValueError("empty")
    t = t.split("T")[0].split(" ")[0]
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3])), False
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", t)
    if not m:
        raise ValueError("unrecognised date format (use YYYY-MM-DD)")
    a, b, y = int(m[1]), int(m[2]), int(m[3])
    if fmt == "MDY":
        return date(y, a, b), False
    if fmt == "YMD":
        raise ValueError("expected YYYY-MM-DD")
    ambiguous = fmt == "auto" and a <= 12 and b <= 12 and a != b
    return date(y, b, a), ambiguous


def parse_bool(text: str) -> bool | None:
    t = _clean(text).lower()
    if t in _TRUE:
        return True
    if t in _FALSE:
        return False
    return None


def parse_currency(text: str) -> str | None:
    t = _clean(text)
    if not t:
        return None
    alias = _CURRENCY_ALIASES.get(t.lower()) or _CURRENCY_ALIASES.get(t)
    code = alias or t.upper()
    return code if code in CURRENCY_EXPONENT else None


def csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection when we write user data back out as CSV."""
    return "'" + value if value and value.startswith(_FORMULA_PREFIX) else value


def money_str(minor: int, currency: str) -> str:
    exp = CURRENCY_EXPONENT.get(currency, 2)
    value = minor / (10 ** exp)
    return f"{value:,.{exp}f}"


AR_SYMBOL = {"EGP": "ج.م", "SAR": "ر.س", "AED": "د.إ"}


def money_fmt(minor: int, currency: str, lang: str = "en") -> str:
    if lang == "ar" and currency in AR_SYMBOL:
        return f"{money_str(minor, currency)} {AR_SYMBOL[currency]}"
    return f"{currency} {money_str(minor, currency)}"
