"""
Tool: strip_audio
-----------------
Extracts the audio track from an MP4 as a 192 kbps MP3 using ffmpeg-python.

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
def strip_audio(input_path: str, output_path: str) -> str:
    """
    Extract the audio track from an MP4 file and save it as an MP3.

    Parameters
    ----------
    input_path : str
        Absolute path to the source MP4 file.
    output_path : str
        Absolute path where the extracted MP3 will be saved.
        Should end with ``.mp3``.

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
    * ``vn=None``           — discard the video stream entirely.
    * ``acodec=libmp3lame`` — LAME MP3 encoder.
    * ``audio_bitrate=192k`` — good quality for speech and music.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Video not found: {input_path!r}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    logger.info("strip_audio: %s → %s", input_path, output_path)

    (
        ffmpeg
        .input(input_path)
        .output(
            output_path,
            vn=None,                  # no video
            acodec="libmp3lame",
            audio_bitrate="192k",
        )
        .overwrite_output()
        .run(quiet=True)
    )

    size_kb = os.path.getsize(output_path) / 1024
    logger.info("strip_audio: done. Extracted %.1f KB MP3 → %s", size_kb, output_path)
    return output_path
