"""
backend/guardrail.py — Mock Bedrock Guardrails (development mode).

In ENV=production this module is NOT called directly. config.py wires
apply_guardrail to the real boto3 bedrock-runtime.apply_guardrail call.

In ENV=development config.py imports mock_apply_guardrail from here as
apply_guardrail, so the rest of the codebase never needs to know which
implementation is active.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ── Blocked pattern registry ──────────────────────────────────────────────────
#
# Each entry: (pattern_string, human_readable_violation_name)
# Matched as plain substrings (case-sensitive).

_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    ("os.system(",    "Dangerous shell execution (os.system)"),
    ("subprocess.",   "Subprocess spawning (subprocess.*)"),
    ("__import__(",   "Dynamic import bypass (__import__)"),
    ("eval(",         "Code injection via eval()"),
    ("exec(",         "Code injection via exec()"),
    ("socket.",       "Raw network access (socket.*)"),
    ("AKIA",          "Potential AWS credential (AKIA prefix)"),
    ("ignore all previous instructions", "Prompt injection attempt"),
    # NOTE: open() is handled separately below via regex so that
    # fitz.open(), PIL.Image.open() etc. are NOT false-positives.
]

# ── Exception ─────────────────────────────────────────────────────────────────

class GuardrailException(Exception):
    """
    Raised by check_guardrail() in agent.py when the guardrail intervenes.
    Carries a human-readable reason and the name of the matched pattern.
    """

    def __init__(self, reason: str, detected_pattern: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detected_pattern = detected_pattern


# ── Core function ─────────────────────────────────────────────────────────────

def mock_apply_guardrail(code_snippet: str) -> dict[str, str]:
    """
    Scan *code_snippet* for policy violations.
    """
    # ── 1. Explicit Whitelists (PyMuPDF and ffmpeg) ───────────────────────────
    # We allow these specific patterns unconditionally if they are the only file handling.
    whitelisted_patterns = ["fitz.open", "ffmpeg.input", "ffmpeg.output", "fitz.Document"]
    # We do not return "NONE" immediately because we still need to check for dangerous commands.

    # ── 2. Plain substring patterns ───────────────────────────────────────────
    for pattern, violation_name in _BLOCKED_PATTERNS:
        if pattern in code_snippet:
            logger.warning(
                "Guardrail intervened — pattern=%r  violation=%r  head=%r",
                pattern, violation_name, code_snippet[:120],
            )
            return {
                "action": "GUARDRAIL_INTERVENED",
                "detected_pattern": violation_name,
            }

    # ── 3. Standalone open() check (regex) ────────────────────────────────────
    # Regex ensures we don't catch fitz.open( or PIL.Image.open(
    _STANDALONE_OPEN_RE = re.compile(r'(?<!\.)(?<!\w)open\s*\(')
    if _STANDALONE_OPEN_RE.search(code_snippet):
        violation_name = "Standalone open() call — use pathlib.Path or library APIs instead"
        logger.warning(
            "Guardrail intervened — standalone open() detected  head=%r",
            code_snippet[:120],
        )
        return {
            "action": "GUARDRAIL_INTERVENED",
            "detected_pattern": violation_name,
        }

    logger.debug("Guardrail passed — snippet length=%d chars", len(code_snippet))
    return {"action": "NONE"}
