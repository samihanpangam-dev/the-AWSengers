"""Safe file inspection and editing tools exposed to the agent."""

from __future__ import annotations

import contextvars
import os
from pathlib import Path

try:
    from strands import tool
except ImportError:
    def tool(fn):
        fn.__is_strands_tool__ = True
        return fn

_workspace: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "agent_workspace", default=None
)
MAX_INSPECT_BYTES = 1 * 1024 * 1024
MAX_EDIT_BYTES = 256 * 1024
EDITABLE_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".srt", ".html", ".css", ".js", ".xml"}


def set_workspace(path: Path):
    """Confine file tools to a request directory and return a reset token."""
    return _workspace.set(path.resolve())


def reset_workspace(token) -> None:
    _workspace.reset(token)


def _confined(path: str) -> Path:
    root = _workspace.get()
    if root is None:
        raise ValueError("File tools are only available during an active request")
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path is outside the request workspace")
    return candidate


@tool
def inspect_file(path: str) -> str:
    """Return bounded UTF-8 text and metadata for a file in the request workspace."""
    try:
        candidate = _confined(path)
        if not candidate.is_file():
            return f"Error: file not found: {path}"
        if candidate.stat().st_size > MAX_INSPECT_BYTES:
            return f"Error: file exceeds inspection limit ({MAX_INSPECT_BYTES} bytes)"
        data = candidate.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return f"Error: file is not UTF-8 text ({candidate.stat().st_size} bytes)"
        return f"File: {candidate.name}\nSize: {len(data)} bytes\n\n{text}"
    except (OSError, ValueError) as exc:
        return f"Error: {exc}"


@tool
def edit_file(path: str, content: str) -> str:
    """Replace a small, approved text file in the request workspace atomically."""
    try:
        candidate = _confined(path)
        if candidate.suffix.lower() not in EDITABLE_EXTENSIONS:
            return "Error: file type is not editable"
        if not candidate.is_file():
            return f"Error: file not found: {path}"
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_EDIT_BYTES:
            return f"Error: edited content exceeds {MAX_EDIT_BYTES} bytes"
        temp = candidate.with_name(f".{candidate.name}.tmp")
        temp.write_bytes(encoded)
        os.replace(temp, candidate)
        return f"Updated {candidate.name} ({len(encoded)} bytes)"
    except (OSError, ValueError) as exc:
        return f"Error: {exc}"


ALL_FILE_TOOLS = [inspect_file, edit_file]
