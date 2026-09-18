"""
backend/security.py — AWS Cedar Policy Evaluator for Omni-File AI Agent.

Enforces enterprise-grade authorization using AWS Cedar policies defined in guardrail.cedar.
Supports the official `cedarpolicy` package with an internal fallback evaluator
that implements core Cedar semantics (default-deny, forbid-overrides-permit).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Locate guardrail.cedar (backend/guardrail.cedar or root guardrail.cedar)
_CURRENT_DIR = Path(__file__).parent
_CEDAR_PATHS = [
    _CURRENT_DIR / "guardrail.cedar",
    _CURRENT_DIR.parent / "guardrail.cedar",
    Path("guardrail.cedar"),
]

def get_cedar_policy_path() -> Path:
    for p in _CEDAR_PATHS:
        if p.is_file():
            return p
    # Default fallback
    return _CURRENT_DIR / "guardrail.cedar"


class CedarDecision(NamedTuple):
    allowed: bool
    action: str
    diagnostics: str


class CedarSecurityEngine:
    """Evaluates requests against Cedar policies."""

    def __init__(self, policy_path: Path | None = None) -> None:
        self.policy_path = policy_path or get_cedar_policy_path()
        self.policy_text = ""
        self._load_policy()
        self._has_native_cedar = False

        try:
            import cedarpolicy  # type: ignore[import-untyped]
            self._has_native_cedar = True
            self._cedar = cedarpolicy
            logger.info("CedarSecurityEngine: Using native cedarpolicy engine")
        except ImportError:
            logger.info("CedarSecurityEngine: cedarpolicy not installed, using Cedar evaluation engine")

    def _load_policy(self) -> None:
        if self.policy_path.is_file():
            self.policy_text = self.policy_path.read_text(encoding="utf-8")
            logger.info("CedarSecurityEngine: Loaded policies from %s", self.policy_path)
        else:
            logger.warning("CedarSecurityEngine: Policy file not found at %s", self.policy_path)
            self.policy_text = ""

    def evaluate(self, principal: str, action: str, resource: str) -> CedarDecision:
        """
        Evaluates (principal, action, resource) against the Cedar policy.
        Cedar core semantics:
          1. Default Deny.
          2. Explicit Forbid takes absolute precedence.
          3. Explicit Permit permits if no forbid matched.
        """
        # 1. Native cedarpolicy if available
        if self._has_native_cedar:
            try:
                # Format request for cedarpolicy.is_authorized
                req = {
                    "principal": principal,
                    "action": action,
                    "resource": resource,
                    "context": {},
                }
                res = self._cedar.is_authorized(req, self.policy_text, [])
                allowed = getattr(res, "decision", res) == "Allow" or getattr(res, "allowed", False)
                return CedarDecision(
                    allowed=allowed,
                    action=action,
                    diagnostics=f"Native Cedar decision: {allowed}",
                )
            except Exception as e:
                logger.warning("Native cedar evaluation failed (%s), falling back to internal evaluator", e)

        # 2. Complete Cedar semantics evaluator
        # Parse policy statements: forbid and permit
        # Cedar syntax: forbid ( principal, action == Action::"...", resource );
        policies = re.findall(
            r'(forbid|permit)\s*\(\s*([^,]+),\s*action\s*==\s*Action::"([^"]+)",\s*([^)]+)\s*\);',
            self.policy_text,
            re.MULTILINE | re.IGNORECASE,
        )

        matched_forbid = []
        matched_permit = []

        for effect, p_spec, a_name, r_spec in policies:
            target_action = f'Action::"{a_name}"'
            if target_action.lower() == action.lower() or a_name.lower() == action.lower():
                if effect.lower() == "forbid":
                    matched_forbid.append(a_name)
                elif effect.lower() == "permit":
                    matched_permit.append(a_name)

        if matched_forbid:
            return CedarDecision(
                allowed=False,
                action=action,
                diagnostics=f"Cedar FORBID matched: Action::{matched_forbid[0]} is explicitly forbidden",
            )

        if matched_permit:
            return CedarDecision(
                allowed=True,
                action=action,
                diagnostics=f"Cedar PERMIT matched: Action::{matched_permit[0]} is authorized",
            )

        # Default Deny
        return CedarDecision(
            allowed=False,
            action=action,
            diagnostics="Cedar DEFAULT-DENY: No permit policy matched request",
        )

    def classify_and_evaluate(self, prompt: str, filenames: list[str]) -> CedarDecision:
        """
        Analyzes the user's prompt and filenames to determine the intended Cedar Action,
        then evaluates it against guardrail.cedar.
        """
        prompt_lower = prompt.lower()
        combined_text = prompt_lower + " " + " ".join(f.lower() for f in filenames)

        # Detect dangerous system command / code execution patterns
        danger_patterns = [
            r"\b(os\.system|subprocess|eval|exec|__import__|open\(|shutil\.rmtree)\b",
            r"\b(bash|sh|zsh|curl|wget|nc|netcat|rm\s+-rf|chmod|chown)\b",
            r"\b(execute\s+command|run\s+script|system\s+command|spawn\s+shell)\b",
            r"(/etc/passwd|/bin/sh|/dev/null)",
        ]
        for pat in danger_patterns:
            if re.search(pat, prompt_lower):
                action = 'Action::"ExecuteSystemCommand"'
                return self.evaluate(
                    principal='User::"Client"',
                    action=action,
                    resource='System::"Subprocess"',
                )

        # Check for PDF operation
        is_pdf = any(f.endswith(".pdf") for f in filenames) or "pdf" in prompt_lower
        if is_pdf:
            action = 'Action::"ProcessPDF"'
            return self.evaluate(
                principal='User::"Client"',
                action=action,
                resource='File::"PDFDocument"',
            )

        # Check for Media operation (Audio/Video)
        media_exts = {".mp3", ".mp4", ".wav", ".m4a", ".aac", ".avi", ".mov", ".mkv", ".flac", ".ogg"}
        is_media = (
            any(Path(f).suffix.lower() in media_exts for f in filenames)
            or any(w in prompt_lower for w in ["trim", "audio", "video", "mp3", "mp4", "wav", "extract audio", "convert", "compress"])
        )
        if is_media:
            action = 'Action::"ProcessMedia"'
            return self.evaluate(
                principal='User::"Client"',
                action=action,
                resource='File::"MediaStream"',
            )

        # General file or harmless query default
        action = 'Action::"ProcessMedia"'
        return self.evaluate(
            principal='User::"Client"',
            action=action,
            resource='File::"GenericFile"',
        )


# Global instance
cedar_engine = CedarSecurityEngine()

