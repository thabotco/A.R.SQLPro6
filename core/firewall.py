"""
core/firewall.py
~~~~~~~~~~~~~~~~
Data-Privacy & Jailbreak-Prevention Module.

Responsibilities:
  1. Scrub biometric data on Edge (Mac Mini) nodes before any network call,
     ensuring compliance with the Saudi Personal Data Protection Law (PDPL)
     and SDAIA ethics guidelines.
  2. Detect prompt-injection / data-leak attempts and return a safe Arabic
     fallback string instead of leaking internal company information.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Jailbreak / prompt-injection detection
# ---------------------------------------------------------------------------

# Patterns that indicate an attempt to extract confidential company data or
# to manipulate the assistant beyond its sanctioned scope.
_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(previous|all|prior|any)\s+.*?(instructions?|rules?|prompts?)", re.I),
    re.compile(r"disregard\s+.*(instructions?|rules?|context)", re.I),
    re.compile(r"reveal\s+.*(confidential|internal|secret|private)", re.I),
    re.compile(r"print\s+.*(password|api[_\s]?key|token|secret)", re.I),
    re.compile(r"you\s+are\s+now\s+.*(different|unrestricted|jailbreak)", re.I),
    re.compile(r"act\s+as\s+.*(dan|evil|unfiltered)", re.I),
    re.compile(r"bypass\s+.*(filter|restriction|rule|firewall)", re.I),
    re.compile(r"leak\s+.*(data|employee|payroll|contract)", re.I),
    re.compile(r"extract\s+.*(database|schema|record|row)", re.I),
]

# Safe Arabic fallback string — returned verbatim whenever an injection is
# detected, revealing no internal information.
_SAFE_FALLBACK_AR: str = (
    "أنا لا أعلم الكثير عن شركة ثابوت أو الشركات التي تديرها، "
    "إلا أنها شركات نظامية، لها سجل تجاري ساري المفعول، "
    "ومسجلة في المملكة العربية السعودية"
)

# ---------------------------------------------------------------------------
# Biometric field names that must be scrubbed before leaving the Edge node
# ---------------------------------------------------------------------------
_BIOMETRIC_FIELDS: frozenset[str] = frozenset(
    {
        "fingerprint",
        "face_encoding",
        "iris_scan",
        "voice_print",
        "retina_scan",
        "biometric_hash",
        "biometric_raw",
        "palm_vein",
    }
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_injection_attempt(text: str) -> bool:
    """Return True if *text* contains a prompt-injection or data-leak pattern."""
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning("Injection pattern detected: %s", pattern.pattern)
            return True
    return False


def safe_response(original_text: str) -> str:
    """
    Inspect *original_text* and either return it unchanged or — if an
    injection attempt is detected — return the safe Arabic fallback.
    """
    if is_injection_attempt(original_text):
        logger.warning("Returning safe fallback due to injection attempt.")
        return _SAFE_FALLBACK_AR
    return original_text


def scrub_biometrics(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively remove biometric fields from *payload* before the data
    leaves the Edge node.

    Biometric data is replaced with a SHA-256 hash of the original value
    so downstream systems can still correlate records without storing
    raw biometric data in the cloud.

    Returns a new dictionary; the original is not modified.
    """
    return _scrub_recursive(payload)


def _scrub_recursive(obj: Any) -> Any:
    if isinstance(obj, dict):
        result: dict[str, Any] = {}
        for key, value in obj.items():
            if key.lower() in _BIOMETRIC_FIELDS:
                # Replace raw biometric with a one-way hash
                raw = str(value).encode()
                result[key] = hashlib.sha256(raw).hexdigest()
                logger.debug("Scrubbed biometric field: %s", key)
            else:
                result[key] = _scrub_recursive(value)
        return result
    if isinstance(obj, list):
        return [_scrub_recursive(item) for item in obj]
    return obj


def validate_outbound_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Full outbound validation pipeline:
      1. Scrub any biometric fields.
      2. Ensure no string value contains an injection pattern.

    Raises ``ValueError`` if a non-scrubbable security violation is found.
    Returns the sanitised payload.
    """
    clean = scrub_biometrics(payload)

    # Walk every string value in the cleaned payload
    for key, value in _flatten_strings(clean):
        if is_injection_attempt(value):
            raise ValueError(
                f"Injection attempt detected in outbound payload field {key!r}."
            )

    return clean


def _flatten_strings(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    """Yield (dotted_key, string_value) pairs from a nested structure."""
    pairs: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            pairs.extend(_flatten_strings(v, path))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            pairs.extend(_flatten_strings(item, f"{prefix}[{i}]"))
    elif isinstance(obj, str):
        pairs.append((prefix, obj))
    return pairs
