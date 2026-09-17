"""
Mock Guardrail — simulates Amazon Bedrock Guardrails for demo / CI purposes.

Production swap-out:
    Replace `mock_apply_guardrail` with a call to the real Bedrock Guardrails
    API (bedrock-runtime.apply_guardrail) without touching any other module.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Patterns that trigger the guardrail.
# "AKIA"                          → AWS IAM access-key prefix (secret leak)
# "ignore all previous instructions" → classic prompt-injection string
_BLOCKED_PATTERNS: list[str] = [
    "AKIA",
    "ignore all previous instructions",
]


class GuardrailException(Exception):
    """Raised when the guardrail intervenes; carries a human-readable reason."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def mock_apply_guardrail(code_snippet: str) -> dict[str, str]:
    """
    Inspect *code_snippet* for policy violations.

    Returns
    -------
    {"action": "NONE"}
        The snippet is safe to execute.
    {"action": "GUARDRAIL_INTERVENED"}
        A blocked pattern was detected; execution must be aborted.

    The caller is responsible for raising ``GuardrailException`` when the
    action is ``"GUARDRAIL_INTERVENED"``.

    Examples
    --------
    >>> mock_apply_guardrail("print('hello')")
    {'action': 'NONE'}
    >>> mock_apply_guardrail("key = 'AKIAIOSFODNN7EXAMPLE'")
    {'action': 'GUARDRAIL_INTERVENED'}
    """
    for pattern in _BLOCKED_PATTERNS:
        if pattern in code_snippet:
            logger.warning(
                "Guardrail intervened — blocked pattern detected: %r", pattern
            )
            return {"action": "GUARDRAIL_INTERVENED"}

    logger.debug("Guardrail passed — no blocked patterns found.")
    return {"action": "NONE"}
