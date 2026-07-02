import fitz
import os
import requests
from bs4 import BeautifulSoup
from docx import Document
from PIL import Image

OCR_DPI = 220


def _load_tesseract():
    try:
        import pytesseract
    except ImportError as exc:
        raise RuntimeError(
            "OCR needs the Python package pytesseract. "
            "Run: python -m pip install pytesseract"
        ) from exc
    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if not tesseract_cmd:
        default_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.exists(default_cmd):
            tesseract_cmd = default_cmd
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    return pytesseract


def _ocr_pdf(file_path: str) -> str:
    pytesseract = _load_tesseract()
    doc = fitz.open(file_path)
    chunks: list[str] = []
    try:
        zoom = OCR_DPI / 72
        matrix = fitz.Matrix(zoom, zoom)
        for index, page in enumerate(doc, start=1):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = pytesseract.image_to_string(image)
            if text.strip():
                chunks.append(f"[OCR page {index}]\n{text.strip()}")
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "OCR engine not found. Install Tesseract OCR for Windows and "
            "add it to PATH, or set TESSERACT_CMD to tesseract.exe."
        ) from exc
    finally:
        doc.close()
    return "\n\n".join(chunks)


def parse_pdf(file_path: str) -> str:
    doc = fitz.open(file_path)
    chunks = []
    for index, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if text:
            chunks.append(f"[PDF page {index}]\n{text}")
    doc.close()
    extracted = "\n\n".join(chunks)
    if extracted.strip():
        return extracted
    ocr_text = _ocr_pdf(file_path)
    return ocr_text or extracted


def parse_docx(file_path: str) -> str:
    doc = Document(file_path)
    return "\n".join([p.text for p in doc.paragraphs
                      if p.text.strip()])


def parse_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8",
              errors="ignore") as f:
        return f.read()


def parse_url(url: str) -> str:
    resp = requests.get(url, timeout=10)
    soup = BeautifulSoup(resp.content, "html.parser")
    return soup.get_text(separator="\n")


def parse_file(file_path: str, filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "pdf":
        return parse_pdf(file_path)
    elif ext == "docx":
        return parse_docx(file_path)
    elif ext == "txt":
        return parse_txt(file_path)
    return ""
