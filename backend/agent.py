"""
Agent assembly for the Omni-File AI Agent.

Responsibilities
----------------
1. Build the Strands Agent with all tools registered (fast-path + interpreter).
2. Embed the system prompt that governs tool selection, guardrail gating, and
   the code-interpreter fallback.
3. Wrap everything in a BedrockAgentCoreApp for deployment compatibility.

Guardrail contract
------------------
The system prompt instructs the LLM to call ``check_guardrail`` (a registered
Strands tool) on any code snippet *before* executing it.  The tool raises
``GuardrailException`` on a hit, which propagates up to the FastAPI handler
and is returned to the user as a 400 error — never silently swallowed.
"""

from __future__ import annotations

import logging

from strands import Agent, tool
from bedrock_agentcore import BedrockAgentCoreApp
from bedrock_agentcore.tools import AgentCoreCodeInterpreter

from .config import OLLAMA_MODEL, OLLAMA_BASE_URL
from .guardrail import mock_apply_guardrail, GuardrailException
from .tools import merge_pdf, compress_video, strip_audio

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────
# This is the single source of truth for the agent's decision-making policy.

SYSTEM_PROMPT = """
You are the Omni-File AI Agent, an expert file-transformation assistant.

## Tool Selection Policy

1. **Fast-path tools first** — for the operations listed below, *always* prefer
   the dedicated tool over the code interpreter:
   - Merging two or more PDF files          → use `merge_pdf`
   - Compressing an MP4 video               → use `compress_video`
   - Extracting an MP3 audio track from MP4 → use `strip_audio`

2. **Guardrail gate** — before executing ANY dynamically generated Python code
   (including code interpreter scripts), you MUST call `check_guardrail` with
   the full code string as the argument.
   - If `check_guardrail` returns `GUARDRAIL_INTERVENED`, stop immediately and
     tell the user: "I cannot execute that code because it was blocked by the
     safety guardrail."
   - If it returns `NONE`, you may proceed with execution.

3. **Code interpreter fallback** — if the user's request cannot be satisfied by
   the three dedicated tools, use `AgentCoreCodeInterpreter` to write and run a
   custom Python script dynamically.  Always pass the script through
   `check_guardrail` first (step 2).

## Response Style
- Be concise.  Report what you did, which tool you used, and the output path or
  result value.
- If an error occurs, explain it clearly and suggest what the user can do next.
""".strip()


# ── Guardrail Tool ────────────────────────────────────────────────────────────
# Registered as a Strands @tool so the LLM can call it explicitly from within
# its reasoning loop — no hidden side-effects, fully auditable.

@tool
def check_guardrail(code_snippet: str) -> str:
    """
    Run the mock guardrail on a code snippet before execution.

    Parameters
    ----------
    code_snippet : str
        The Python code string the agent is about to execute.

    Returns
    -------
    str
        ``"NONE"`` if the snippet is safe to execute.

    Raises
    ------
    GuardrailException
        If a blocked pattern is detected.  The caller (agent loop / FastAPI
        handler) must catch this and report it to the user.
    """
    result = mock_apply_guardrail(code_snippet)

    if result["action"] == "GUARDRAIL_INTERVENED":
        logger.warning("check_guardrail: blocked snippet (first 120 chars): %s", code_snippet[:120])
        raise GuardrailException(
            "Guardrail detected a policy violation in the generated code. "
            "Execution has been blocked."
        )

    logger.debug("check_guardrail: snippet cleared.")
    return "NONE"


# ── Code Interpreter ──────────────────────────────────────────────────────────

_code_interpreter = AgentCoreCodeInterpreter()


# ── Agent ─────────────────────────────────────────────────────────────────────

agent = Agent(
    model=OLLAMA_MODEL,
    # Some Strands providers accept an extra base_url kwarg for local Ollama.
    # If your strands version surfaces it differently, set the OLLAMA_HOST env
    # var instead: export OLLAMA_HOST=http://localhost:11434
    model_config={"base_url": OLLAMA_BASE_URL},
    system_prompt=SYSTEM_PROMPT,
    tools=[
        # Fast-path file tools
        merge_pdf,
        compress_video,
        strip_audio,
        # Guardrail gate (callable by the LLM)
        check_guardrail,
        # Fallback: dynamic code execution
        _code_interpreter,
    ],
)

logger.info("Strands Agent initialised with model=%s", OLLAMA_MODEL)

# ── BedrockAgentCoreApp wrapper ───────────────────────────────────────────────
# Provides the execution environment expected by Bedrock AgentCore at deploy
# time.  During local development, it acts as a transparent pass-through.

agent_app = BedrockAgentCoreApp(agent=agent)

logger.info("BedrockAgentCoreApp wrapper ready.")
