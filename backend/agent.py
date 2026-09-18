"""
backend/agent.py — Strands Agent assembly for Omni-File AI Agent.

Configured with Qwen 2.5 via Ollama and bound to prebuilt media_tools.
Enforces strict tool-only execution without raw Python code generation.
"""

from __future__ import annotations

import logging
from strands import Agent

from .config import ACTIVE_MODEL, get_model
from .media_tools import ALL_MEDIA_TOOLS

logger = logging.getLogger(__name__)

# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are the Omni-File Agent. You have a suite of dedicated tools for media and PDF operations:
- merge_pdfs(input_paths, output_path): Merges ANY number of PDF files (2, 3, 5, 10+) into one. You must pass ALL input file paths in the input_paths list.
- split_pdf_to_zip(input_path, output_dir): Splits a PDF into individual pages and zips them.
- extract_pdf_text(input_path): Extracts all text from a PDF.
- compress_pdf(input_path, output_path): Compresses a PDF.
- convert_media(input_path, output_path): Converts audio or video to a new format based on output extension.
- extract_audio(input_video, output_audio): Strips video track and saves only audio.
- trim_media(input_path, output_path, start_time, end_time): Trims media using HH:MM:SS or SS timestamps.
- compress_video(input_path, output_path, crf): Compresses a video to reduce file size.

When a user requests a file operation, you MUST use the provided tools. You are STRICTLY FORBIDDEN from generating or executing raw Python scripts for these standard tasks. Execute the tool silently, and return only the final output file path and a brief success message.

Format rule: Always wrap the generated output file path in your reply exactly like this:
[OUTPUT: /absolute/path/to/file]
""".strip()


# ── Agent Factory & Singleton ─────────────────────────────────────────────────

def create_omni_agent() -> Agent:
    """Instantiates the Strands Agent bound to local Qwen 2.5 and explicit media tools."""
    model = get_model()
    agent_instance = Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=ALL_MEDIA_TOOLS,
    )
    logger.info(
        "Omni-File Strands Agent created — model=%s  tools=%s",
        ACTIVE_MODEL,
        [t.__name__ if hasattr(t, "__name__") else str(t) for t in ALL_MEDIA_TOOLS],
    )
    return agent_instance


agent = create_omni_agent()
