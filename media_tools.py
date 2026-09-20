"""
media_tools.py — Root-level proxy for backend.media_tools.
"""
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

__all__ = [
    "ALL_MEDIA_TOOLS",
    "merge_pdfs",
    "split_pdf_to_zip",
    "extract_pdf_text",
    "compress_pdf",
    "convert_media",
    "extract_audio",
    "trim_media",
    "compress_video",
    "inspect_media",
]
