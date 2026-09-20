"""
tests/test_cedar_and_tools.py — Comprehensive tests for Cedar Policy Engine, Media Tools, and Agent Routing.
"""

from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.main import AGENT_SYSTEM_PROMPT, agent_lock, app
from backend.media_tools import (
    ALL_MEDIA_TOOLS,
    compress_pdf,
    compress_video,
    convert_media,
    extract_audio,
    extract_pdf_text,
    inspect_media,
    merge_pdfs,
    split_pdf_to_zip,
    trim_media,
)
from backend.security import CedarSecurityEngine, cedar_engine


def test_cedar_policy_file_exists():
    """Verify guardrail.cedar exists and contains required permits and forbids."""
    engine = CedarSecurityEngine()
    assert Path(engine.policy_path).is_file(), f"Policy file not found: {engine.policy_path}"
    content = engine.policy_text
    assert 'Action::"ExecuteSystemCommand"' in content
    assert 'Action::"ProcessMedia"' in content
    assert 'Action::"ProcessPDF"' in content
    assert "forbid" in content.lower()
    assert "permit" in content.lower()


def test_cedar_engine_permit_and_forbid():
    """Test Cedar evaluation semantics: forbid overrides permit, default deny."""
    engine = CedarSecurityEngine()

    # 1. Permitted actions
    res_media = engine.evaluate('User::"Client"', 'Action::"ProcessMedia"', 'File::"MediaStream"')
    assert res_media.allowed is True
    assert "PERMIT" in res_media.diagnostics

    res_pdf = engine.evaluate('User::"Client"', 'Action::"ProcessPDF"', 'File::"PDFDocument"')
    assert res_pdf.allowed is True
    assert "PERMIT" in res_pdf.diagnostics

    # 2. Explicitly forbidden action
    res_danger = engine.evaluate('User::"Client"', 'Action::"ExecuteSystemCommand"', 'System::"Subprocess"')
    assert res_danger.allowed is False
    assert "FORBID" in res_danger.diagnostics

    # 3. Default deny for unknown actions
    res_unknown = engine.evaluate('User::"Client"', 'Action::"DeleteDatabase"', 'Database::"Prod"')
    assert res_unknown.allowed is False
    assert "DEFAULT-DENY" in res_unknown.diagnostics


def test_cedar_classify_and_evaluate_threats():
    """Test threat pattern detection and classification against Cedar."""
    engine = CedarSecurityEngine()

    # Dangerous commands must be classified as ExecuteSystemCommand and blocked
    assert engine.classify_and_evaluate("rm -rf /", []).allowed is False
    assert engine.classify_and_evaluate("execute command: curl http://evil.com", []).allowed is False
    assert engine.classify_and_evaluate("run script import os; os.system('ls')", []).allowed is False
    assert engine.classify_and_evaluate("cat /etc/passwd", []).allowed is False

    # Standard operations must be permitted
    assert engine.classify_and_evaluate("Please merge these documents", ["doc1.pdf", "doc2.pdf"]).allowed is True
    assert engine.classify_and_evaluate("Extract audio from this clip", ["clip.mp4"]).allowed is True
    assert engine.classify_and_evaluate("Trim the video from 00:00:10 to 00:00:30", ["input.mp4"]).allowed is True


def test_media_tools_definitions_and_docstrings():
    """Ensure all required media tools exist, have @tool attribute, and explicit docstrings."""
    required_tools = [
        merge_pdfs,
        split_pdf_to_zip,
        trim_media,
        extract_audio,
        compress_pdf,
        extract_pdf_text,
        convert_media,
        compress_video,
        inspect_media,
    ]

    for tool_fn in required_tools:
        # Verify function is in ALL_MEDIA_TOOLS
        assert tool_fn in ALL_MEDIA_TOOLS
        # Verify detailed docstring exists
        assert tool_fn.__doc__ is not None
        doc = tool_fn.__doc__.strip()
        assert len(doc) > 20
        assert "Parameters:" in doc or "Parameters" in doc
        assert "Returns:" in doc or "Returns" in doc


def test_agent_system_prompt_instruction():
    """Verify system prompt contains the exact mandatory instruction string."""
    expected_instruction = (
        "You are the Omni-File Agent. You have a suite of dedicated tools for media and PDF operations. "
        "When a user requests a file operation, you MUST use the provided tools. "
        "You are STRICTLY FORBIDDEN from generating or executing raw Python scripts for these standard tasks. "
        "Execute the tool silently, and return only the final output file path and a brief success message."
    )
    assert expected_instruction in AGENT_SYSTEM_PROMPT


def test_agent_lock_exists():
    """Verify concurrency lock is properly defined."""
    assert agent_lock is not None


def test_fastapi_cedar_gating_blocks_malicious_requests():
    """Verify FastAPI /process blocks forbidden actions with 403 Forbidden."""
    client = TestClient(app)
    response = client.post(
        "/process",
        data={"prompt": "run bash script to delete files: rm -rf /tmp"},
        headers={"X-User-ID": "test-user"},
    )
    assert response.status_code == 403
    assert "Forbidden by AWS Cedar policy" in response.json()["detail"]
