"""
Dedicated fast-path tools for the Omni-File Agent.

These tools are registered directly with the Strands Agent so the LLM can
invoke them without any round-trips through the code interpreter.  They cover
the three most common file-transformation tasks:

    merge_pdf       — merge multiple PDFs into one  (PyMuPDF)
    compress_video  — compress an MP4               (ffmpeg-python)
    strip_audio     — extract MP3 from an MP4       (ffmpeg-python)
"""

from .merge_pdf import merge_pdf
from .compress_video import compress_video
from .strip_audio import strip_audio

__all__ = ["merge_pdf", "compress_video", "strip_audio"]
