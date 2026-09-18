import fitz
import ffmpeg
import shutil
from pathlib import Path

# --- PDF OPERATIONS ---

def merge_pdfs(input_paths: list[str], output_path: str) -> str:
    """Merges multiple PDFs into one."""
    with fitz.open(input_paths[0]) as doc:
        for path in input_paths[1:]:
            with fitz.open(path) as next_doc:
                doc.insert_pdf(next_doc)
        doc.save(output_path)
    return output_path

def split_pdf_to_zip(input_path: str, output_dir: str) -> str:
    """Splits a PDF into individual pages and zips them."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(input_path) as doc:
        for i in range(len(doc)):
            with fitz.open() as new_doc:
                new_doc.insert_pdf(doc, from_page=i, to_page=i)
                new_doc.save(out_dir / f"page_{i+1}.pdf")
    zip_path = out_dir / "pages.zip"
    shutil.make_archive(base_name=str(out_dir / "pages"), format="zip", root_dir=out_dir)
    return str(zip_path)

def extract_pdf_text(input_path: str) -> str:
    """Extracts all text from a PDF."""
    with fitz.open(input_path) as doc:
        return "\n".join([page.get_text() for page in doc])

def compress_pdf(input_path: str, output_path: str) -> str:
    """Compresses a PDF file."""
    with fitz.open(input_path) as doc:
        doc.save(output_path, garbage=4, deflate=True)
    return output_path

# --- MEDIA OPERATIONS (FFMPEG) ---

def convert_media(input_path: str, output_path: str) -> str:
    """Converts audio or video to a new format based on output extension."""
    ffmpeg.input(input_path).output(output_path).run(overwrite_output=True, quiet=True)
    return output_path

def extract_audio(input_video: str, output_audio: str) -> str:
    """Strips video track and saves only audio."""
    ffmpeg.input(input_video).audio.output(output_audio).run(overwrite_output=True, quiet=True)
    return output_audio

def trim_media(input_path: str, output_path: str, start_time: str, end_time: str) -> str:
    """Trims media using HH:MM:SS timestamps."""
    ffmpeg.input(input_path, ss=start_time, to=end_time).output(output_path).run(overwrite_output=True, quiet=True)
    return output_path

def compress_video(input_path: str, output_path: str, crf: int = 28) -> str:
    """Compresses a video to reduce file size."""
    ffmpeg.input(input_path).output(output_path, vcodec='libx264', crf=crf).run(overwrite_output=True, quiet=True)
    return output_path

