"""
backend/config.py — Single source of truth for all runtime configuration.

This is the ONLY file that reads environment variables and makes
ENV-based branching decisions. Every other module imports constants
or callables from here and remains environment-agnostic.

Switching from local development to AWS production requires exactly one
change: set ENV=production in the process environment (or Docker -e flag).

Environment variable reference
-------------------------------
Variable                    | Required in | Default
----------------------------|-------------|-----------------------------
ENV                         | both        | development
OLLAMA_BASE_URL             | dev         | http://localhost:11434
OLLAMA_MODEL_ID             | dev         | qwen2.5
BEDROCK_MODEL_ID            | prod        | (required — no default)
BEDROCK_GUARDRAIL_ID        | prod        | (required — no default)
BEDROCK_GUARDRAIL_VERSION   | prod        | DRAFT
AWS_REGION                  | prod        | us-east-1
AWS_ACCESS_KEY_ID           | prod        | (from IAM role / env)
AWS_SECRET_ACCESS_KEY       | prod        | (from IAM role / env)
CODE_EXEC_TIMEOUT_SECONDS   | both        | 60
UPLOAD_TMP_DIR              | both        | /tmp/omni_agent
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ── Master switch ─────────────────────────────────────────────────────────────

ENV: str = os.environ.get("ENV", "development")

# ── Shared settings ───────────────────────────────────────────────────────────

UPLOAD_TMP_DIR: str = os.environ.get("UPLOAD_TMP_DIR", "/tmp/omni_agent")
CODE_EXEC_TIMEOUT: int = int(os.environ.get("CODE_EXEC_TIMEOUT_SECONDS", "60"))
MAX_UPLOAD_BYTES: int = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UPLOAD_FILES: int = int(os.environ.get("MAX_UPLOAD_FILES", "5"))
MAX_PROMPT_LENGTH: int = int(os.environ.get("MAX_PROMPT_LENGTH", "4000"))
TEMP_RETENTION_SECONDS: int = int(os.environ.get("TEMP_RETENTION_SECONDS", "3600"))
TRIAL_DAYS: int = int(os.environ.get("AI_AGENT_TRIAL_DAYS", "30"))
SUBSCRIPTION_PROVIDER: str = os.environ.get("SUBSCRIPTION_PROVIDER", "dev")
SUBSCRIPTION_WEBHOOK_SECRET: str = os.environ.get("SUBSCRIPTION_WEBHOOK_SECRET", "")
BILLING_CHECKOUT_URL: str = os.environ.get("BILLING_CHECKOUT_URL", "")

# ── Model ─────────────────────────────────────────────────────────────────────
# ACTIVE_MODEL   : human-readable model name string (for /health and logging)
# get_model()    : returns the Strands Model instance for Agent(model=...)
#
# We use a factory function rather than a module-level instance so the model
# object is only constructed when agent.py imports it — after logging is set up.

USE_BEDROCK = (
    ENV == "production"
    or os.environ.get("USE_BEDROCK", "").lower() in ("true", "1")
    or bool(os.environ.get("BEDROCK_MODEL_ID"))
)

if USE_BEDROCK:
    # Default to Amazon Nova Pro cross-region inference profile
    ACTIVE_MODEL: str = os.environ.get("BEDROCK_MODEL_ID", "us.amazon.nova-pro-v1:0")

    def get_model():
        from strands.models import BedrockModel  # type: ignore[import-untyped]
        return BedrockModel(
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            model_id=ACTIVE_MODEL,
        )

else:
    _OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    # qwen2.5 has the most reliable tool-calling support among local Ollama models.
    # llama3.1 technically supports tools but frequently prints raw JSON instead
    # of executing tool calls — qwen2.5 does not have this problem.
    # Pull with: ollama pull qwen2.5
    # Alternatives: qwen3, mistral
    _OLLAMA_MODEL_ID: str = os.environ.get("OLLAMA_MODEL_ID", "qwen2.5")
    ACTIVE_MODEL = f"ollama/{_OLLAMA_MODEL_ID}"

    def get_model():
        # OllamaModel is a submodule export in current strands-agents releases.
        try:
            from strands.models.ollama import OllamaModel  # type: ignore[import-untyped]
        except (ImportError, AttributeError) as exc:
            raise RuntimeError(
                "Local agent configuration requires the Strands Ollama adapter. "
                "Install a compatible strands-agents release or set USE_BEDROCK=true."
            ) from exc
        return OllamaModel(
            host=_OLLAMA_BASE_URL,
            model_id=_OLLAMA_MODEL_ID,
        )

# ── Guardrail ─────────────────────────────────────────────────────────────────
# apply_guardrail(code: str) -> {"action": "NONE" | "GUARDRAIL_INTERVENED", ...}
#
# Primary authorization is enforced via AWS Cedar (guardrail.cedar + security.py).
# If BEDROCK_GUARDRAIL_ID is provided, Bedrock Guardrails are called as an additional layer.

if USE_BEDROCK and os.environ.get("BEDROCK_GUARDRAIL_ID"):
    import boto3  # type: ignore[import-untyped]

    _AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
    _GUARDRAIL_ID: str = os.environ["BEDROCK_GUARDRAIL_ID"]
    _GUARDRAIL_VERSION: str = os.environ.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")
    _bedrock_rt = boto3.client("bedrock-runtime", region_name=_AWS_REGION)

    def apply_guardrail(code: str) -> dict[str, str]:
        """Call the live AWS Bedrock Guardrails API."""
        resp = _bedrock_rt.apply_guardrail(
            guardrailIdentifier=_GUARDRAIL_ID,
            guardrailVersion=_GUARDRAIL_VERSION,
            source="INPUT",
            content=[{"text": {"text": code}}],
        )
        action = (
            "GUARDRAIL_INTERVENED"
            if resp.get("action") == "GUARDRAIL_INTERVENED"
            else "NONE"
        )
        return {"action": action}

else:
    def apply_guardrail(code: str) -> dict[str, str]:
        return {"action": "NONE"}

# ── Startup log ───────────────────────────────────────────────────────────────

logger.info(
    "Config loaded — ENV=%s  model=%s  timeout=%ss",
    ENV,
    ACTIVE_MODEL,
    CODE_EXEC_TIMEOUT,
)
