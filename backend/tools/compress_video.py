"""
Tool: compress_video
--------------------
Compresses an MP4 video using ffmpeg-python (libx264, CRF 28).

Fast-path: no LLM round-trip once the agent selects this tool.
Requires the `ffmpeg` binary to be available on the system PATH.
"""

from __future__ import annotations

import logging
import os

import ffmpeg
from strands import tool

logger = logging.getLogger(__name__)


@tool
def compress_video(input_path: str, output_path: str) -> str:
    """
    Compress an MP4 video file using H.264 encoding.

    Parameters
    ----------
    input_path : str
        Absolute path to the source MP4 file.
    output_path : str
        Absolute path where the compressed MP4 will be saved.

    Returns
    -------
    str
        The *output_path* on success.

    Raises
    ------
    FileNotFoundError
        If *input_path* does not exist.
    ffmpeg.Error
        If the ffmpeg subprocess exits with a non-zero return code.

    Notes
    -----
    * ``crf=28``     — Constant Rate Factor; higher = smaller file / lower quality.
                       28 is a good balance for a significant size reduction.
    * ``preset=fast`` — Encoding speed preset; faster encodes are less efficient
                        but complete quickly enough for interactive use.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Video not found: {input_path!r}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logger.info("compress_video: %s → %s", input_path, output_path)

    (
        ffmpeg
        .input(input_path)
        .output(
            output_path,
            vcodec="libx264",
            crf=28,
            preset="fast",
            acodec="aac",          # re-encode audio to AAC for broad compatibility
        )
        .overwrite_output()
        .run(quiet=True)           # suppress ffmpeg stdout/stderr spam
    )

    original_mb = os.path.getsize(input_path) / 1_048_576
    compressed_mb = os.path.getsize(output_path) / 1_048_576
    logger.info(
        "compress_video: done. %.1f MB → %.1f MB (%.0f%% reduction)",
        original_mb,
        compressed_mb,
        (1 - compressed_mb / original_mb) * 100,
    )
    return output_path
