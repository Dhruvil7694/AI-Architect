"""
guja_decoder.py
---------------
Decodes numbers stored in old Gujarati font encoding (pre-Unicode),
common in AUDA/SUDA government Excel/DXF files from the 1990s-2000s.

Font character → digit mapping (confirmed from TP14 PAL column numbering):
    _ → 0   ! → 1   Z → 2   # → 3   $ → 4
    5 → 5   & → 6   * → 7   ( → 8   ) → 9
    4 → '' (thousands comma separator, discarded)
    q → /  (fraction slash, e.g. 160/1 → plot sub-numbers)
"""

from __future__ import annotations

import re
from typing import Optional

_DIGIT_TABLE = str.maketrans({
    '_': '0',
    '!': '1',
    'Z': '2',
    '#': '3',
    '$': '4',
    '5': '5',
    '&': '6',
    '*': '7',
    '(': '8',
    ')': '9',
    '4': '',   # thousands separator — strip
    'q': '/',  # sub-plot slash
})

_VALID_FP_RE = re.compile(r'^\d+(/\d+)?$')  # e.g. "160" or "160/1"


def decode_number(raw: str) -> Optional[str]:
    """
    Decode a raw Gujarati-encoded string to a plain digit string.
    Returns None if the result contains no digits.

    Examples
    --------
    decode_number("&_")      → "60"
    decode_number("!4)!&")   → "1916"
    decode_number("!&_q!")   → "160/1"
    decode_number("5")       → "5"
    """
    if not isinstance(raw, str):
        return None
    translated = raw.strip().translate(_DIGIT_TABLE)
    digits_only = ''.join(c for c in translated if c.isdigit() or c == '/')
    return digits_only if digits_only else None


def decode_fp_number(raw: str) -> Optional[str]:
    """
    Decode a raw Gujarati-encoded FP number string.
    Returns the decoded string only if it looks like a valid plot number
    (digits only, or digits/digits for sub-plots).
    Returns None for empty, non-numeric, or special-purpose labels.
    """
    decoded = decode_number(raw)
    if decoded and _VALID_FP_RE.match(decoded):
        return decoded
    return None


def decode_area(raw: str) -> Optional[float]:
    """
    Decode a raw Gujarati-encoded area value to a float.
    Returns None if the value cannot be parsed.

    The thousands separator ('4' in this encoding) is stripped before
    parsing, so "!4)!&" (= "1,916") → 1916.0.
    """
    if not isinstance(raw, str):
        return None
    translated = raw.strip().translate(_DIGIT_TABLE)
    digits_only = ''.join(c for c in translated if c.isdigit() or c == '.')
    try:
        return float(digits_only) if digits_only else None
    except ValueError:
        return None
