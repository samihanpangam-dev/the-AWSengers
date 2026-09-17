"""
Tool: merge_pdf
---------------
Merges a list of PDF files into a single PDF using PyMuPDF (fitz).

Fast-path: no LLM round-trip once the agent selects this tool.
"""

from __future__ import annotations

import logging
import os

import fitz  # PyMuPDF
from strands import tool

logger = logging.getLogger(__name__)


@tool
def merge_pdf(pdf_paths: list[str], output_path: str) -> str:
    """
    Merge multiple PDF files into a single PDF document.

    Parameters
    ----------
    pdf_paths : list[str]
        Ordered list of absolute paths to the PDF files to merge.
    output_path : str
        Absolute path where the merged PDF will be saved.

    Returns
    -------
    str
        The *output_path* on success, confirming where the file was written.

    Raises
    ------
    FileNotFoundError
        If any path in *pdf_paths* does not exist on disk.
    ValueError
        If *pdf_paths* is empty.
    """
    if not pdf_paths:
        raise ValueError("pdf_paths must contain at least one file path.")

    for path in pdf_paths:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"PDF not found: {path!r}")

    logger.info("merge_pdf: merging %d files → %s", len(pdf_paths), output_path)

    merged = fitz.open()

    for path in pdf_paths:
        with fitz.open(path) as src:
            merged.insert_pdf(src)
        logger.debug("merge_pdf: inserted %s (%d pages)", path, fitz.open(path).page_count)

    # Ensure the output directory exists.
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    merged.save(output_path)
    merged.close()

    logger.info("merge_pdf: saved merged PDF (%d pages) → %s", merged.page_count, output_path)
    return output_path
