"""
backend/media_tools.py — Hardcoded Guaranteed Media Tools for Omni-File AI Agent.

Decorated with Strands @tool for deterministic, 100% reliable execution
without hallucinating dynamic code generation.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

try:
    import ffmpeg
except ImportError:
    ffmpeg = None

try:
    import fitz
except ImportError:
    fitz = None

try:
    from strands import tool
except ImportError:
    # Graceful fallback decorator if strands is not yet installed in local environment
    def tool(fn):
        fn.__is_strands_tool__ = True
        return fn

logger = logging.getLogger(__name__)


def _require_fitz() -> None:
    if fitz is None:
        raise RuntimeError("PyMuPDF (fitz) is not installed. Install with 'pip install pymupdf'")


def _require_ffmpeg_py() -> None:
    if ffmpeg is None:
        raise RuntimeError("ffmpeg-python is not installed. Install with 'pip install ffmpeg-python'")


def _validate_media(input_path: str, output_path: str | None = None) -> None:
    source = Path(input_path)
    if not source.is_file():
        raise ValueError(f"Input file not found: {input_path}")
    if output_path is not None and source.resolve() == Path(output_path).resolve():
        raise ValueError("Output path must be different from input path")


def _require_binary(name: str = "ffmpeg") -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"{name} binary is not installed or not on PATH")


def _run_media(stream):
    _require_ffmpeg_py()
    _require_binary("ffmpeg")
    try:
        return stream.run(overwrite_output=True, quiet=True)
    except ffmpeg.Error as exc:
        detail = (exc.stderr or b"").decode(errors="replace").strip()
        raise RuntimeError(f"ffmpeg processing failed{': ' + detail if detail else ''}") from exc


# ── PDF OPERATIONS ─────────────────────────────────────────────────────────────

@tool
def merge_pdfs(input_paths: list[str], output_path: str) -> str:
    """
    Merges multiple PDF documents into a single consolidated PDF file.

    Parameters:
      input_paths: A list of absolute file paths to the input PDF files to be merged in order (e.g. ['/path/to/doc1.pdf', '/path/to/doc2.pdf']).
      output_path: Absolute file path where the merged PDF document should be saved (e.g. '/path/to/merged.pdf').

    Returns:
      The absolute file path of the merged PDF document on success, or an error message string if inputs are empty.
    """
    if not input_paths:
        return "Error: No files provided."

    _require_fitz()
    logger.info("Tool merge_pdfs called: %d files -> %s", len(input_paths), output_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with fitz.open(input_paths[0]) as doc:
        for path in input_paths[1:]:
            with fitz.open(path) as next_doc:
                doc.insert_pdf(next_doc)
        doc.save(str(out))
    return str(out)


@tool
def split_pdf_to_zip(input_path: str, output_dir: str) -> str:
    """
    Splits a multi-page PDF document into individual single-page PDF files and bundles them into a zip archive.

    Parameters:
      input_path: Absolute file path to the source PDF file to split (e.g. '/path/to/document.pdf').
      output_dir: Absolute directory path where individual page PDFs and the final pages.zip will be saved (e.g. '/path/to/output_dir').

    Returns:
      The absolute file path of the resulting pages.zip archive.
    """
    _require_fitz()
    logger.info("Tool split_pdf_to_zip called: %s -> %s", input_path, output_dir)
    out_dir = Path(output_dir)
    pages_dir = out_dir / "split_pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    with fitz.open(input_path) as doc:
        for i in range(len(doc)):
            with fitz.open() as new_doc:
                new_doc.insert_pdf(doc, from_page=i, to_page=i)
                new_doc.save(str(pages_dir / f"page_{i+1}.pdf"))

    zip_path = out_dir / "pages.zip"
    shutil.make_archive(base_name=str(out_dir / "pages"), format="zip", root_dir=str(pages_dir))
    return str(zip_path)


@tool
def extract_pdf_text(input_path: str) -> str:
    """
    Extracts all textual content from every page of a PDF document.

    Parameters:
      input_path: Absolute file path to the source PDF file (e.g. '/path/to/document.pdf').

    Returns:
      A string containing all extracted text joined across pages.
    """
    _require_fitz()
    logger.info("Tool extract_pdf_text called: %s", input_path)
    with fitz.open(input_path) as doc:
        return "\n".join([page.get_text() for page in doc])


@tool
def compress_pdf(input_path: str, output_path: str) -> str:
    """
    Compresses a PDF file to reduce its file size using stream deflation and object garbage collection.

    Parameters:
      input_path: Absolute file path to the uncompressed source PDF (e.g. '/path/to/large.pdf').
      output_path: Absolute file path where the compressed PDF should be saved (e.g. '/path/to/compressed.pdf').

    Returns:
      The absolute file path of the compressed PDF.
    """
    _require_fitz()
    logger.info("Tool compress_pdf called: %s -> %s", input_path, output_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    with fitz.open(input_path) as doc:
        doc.save(str(out), garbage=4, deflate=True)
    return str(out)


# ── MEDIA OPERATIONS (FFMPEG) ─────────────────────────────────────────────────

@tool
def convert_media(input_path: str, output_path: str) -> str:
    """
    Converts an audio or video file to a new format determined by the output file extension (e.g. .mp3, .mp4, .wav, .aac).

    Parameters:
      input_path: Absolute file path to the source audio or video file.
      output_path: Absolute file path for the converted file with the desired target extension.

    Returns:
      The absolute file path of the converted media file.
    """
    logger.info("Tool convert_media called: %s -> %s", input_path, output_path)
    _validate_media(input_path, output_path)
    _require_binary()
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run_media(ffmpeg.input(input_path).output(output_path))
    return output_path


@tool
def extract_audio(input_video: str, output_audio: str) -> str:
    """
    Strips the video track from a video file and saves only the audio stream (e.g. to .mp3 or .wav).

    Parameters:
      input_video: Absolute file path to the source video file (e.g. '/path/to/video.mp4').
      output_audio: Absolute file path where the extracted audio file should be saved (e.g. '/path/to/extracted.mp3').

    Returns:
      The absolute file path of the extracted audio file.
    """
    logger.info("Tool extract_audio called: %s -> %s", input_video, output_audio)
    _validate_media(input_video, output_audio)
    Path(output_audio).parent.mkdir(parents=True, exist_ok=True)
    _run_media(ffmpeg.input(input_video).audio.output(output_audio))
    return output_audio


@tool
def trim_media(input_path: str, output_path: str, start_time: str, end_time: str) -> str:
    """
    Trims an audio or video file between specified start and end timestamps.

    Parameters:
      input_path: Absolute file path to the source audio or video file (e.g. '/path/to/source.mp4').
      output_path: Absolute file path where the trimmed file should be saved (must be distinct from input_path).
      start_time: Start timestamp in HH:MM:SS or SS format (e.g. '00:00:15' or '15').
      end_time: End timestamp in HH:MM:SS or SS format (e.g. '00:01:30' or '90').

    Returns:
      The absolute file path of the trimmed media file.
    """
    logger.info("Tool trim_media called: %s (%s -> %s) -> %s", input_path, start_time, end_time, output_path)
    _validate_media(input_path, output_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if not start_time or not end_time:
        raise ValueError("Start and end times are required")
    _run_media(ffmpeg.input(input_path, ss=start_time, to=end_time).output(output_path))
    return output_path


@tool
def compress_video(input_path: str, output_path: str, crf: int = 28) -> str:
    """
    Compresses a video to reduce file size using libx264 with Constant Rate Factor (CRF).

    Parameters:
      input_path: Absolute file path to the source video file.
      output_path: Absolute file path where the compressed video should be saved.
      crf: Constant Rate Factor between 18 and 35 (default 28; higher means smaller file size).

    Returns:
      The absolute file path of the compressed video file.
    """
    logger.info("Tool compress_video called: %s (crf=%d) -> %s", input_path, crf, output_path)
    _validate_media(input_path, output_path)
    if not 18 <= crf <= 35:
        raise ValueError("CRF must be between 18 and 35")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    _run_media(ffmpeg.input(input_path).output(output_path, vcodec='libx264', crf=crf))
    return output_path


@tool
def inspect_media(input_path: str) -> str:
    """
    Inspects a media file using ffprobe and returns technical stream metadata (codecs, duration, bitrate, resolution).

    Parameters:
      input_path: Absolute file path to the media file to inspect.

    Returns:
      A string representation of the ffprobe metadata dictionary.
    """
    _validate_media(input_path)
    _require_binary("ffprobe")
    try:
        probe = ffmpeg.probe(input_path)
    except ffmpeg.Error as exc:
        detail = (exc.stderr or b"").decode(errors="replace").strip()
        raise RuntimeError(f"ffprobe inspection failed{': ' + detail if detail else ''}") from exc
    return str(probe)


# Export all media tools as a list for agent binding
ALL_MEDIA_TOOLS = [
    merge_pdfs,
    split_pdf_to_zip,
    extract_pdf_text,
    compress_pdf,
    convert_media,
    extract_audio,
    trim_media,
    compress_video,
    inspect_media,
]
