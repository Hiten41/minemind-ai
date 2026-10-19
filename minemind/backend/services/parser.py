import pymupdf as fitz
import os
import time
from pathlib import Path
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


def _ocr_page(page) -> str:
    pytesseract = _load_tesseract()
    zoom = OCR_DPI / 72
    if page.rect.width * page.rect.height * zoom * zoom > 25_000_000:
        raise RuntimeError('Page is too large for OCR')
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = Image.frombytes('RGB', [pix.width,pix.height],pix.samples)
    try:
        return pytesseract.image_to_string(image, timeout=20).strip()
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError('This page needs OCR. Install Tesseract or configure TESSERACT_CMD, then retry.') from exc


def _ocr_pdf(file_path: str) -> str:
    with fitz.open(file_path) as doc:
        return '\n\n'.join(f'[OCR page {i}]\n{_ocr_page(page)}' for i,page in enumerate(doc,1))


def _table_rows(page) -> str:
    """Preserve ruled table row membership alongside native text, including merged cells.

    Strict line detection ignores coloured header backgrounds that otherwise create
    phantom columns. Extraction can be incomplete; never infer missing cell values.
    """
    blocks=[]
    try:
        # Layout inference loads a large model in PyMuPDF 2.0. We only need
        # ruled-table geometry here; keep upload memory bounded on small hosts.
        tables=page.find_tables(strategy='lines_strict', use_layout=False).tables
        textpage=page.get_textpage() if tables else None
        for index,table in enumerate(tables[:20],1):
            # Read native text inside detected cells: PyMuPDF 2.0's character
            # reconstruction can drop word spaces in otherwise readable PDFs.
            rows=[[page.get_textbox(cell, textpage=textpage) if cell else '' for cell in row.cells]
                  for row in table.rows]
            if not rows or len(rows)<2 or max(len(row) for row in rows)<2:
                continue
            lines=[]
            for row in rows:
                cells=[' '.join((cell or '').split()) for cell in row]
                lines.append(' | '.join(cells))
            blocks.append(f'[Extracted table {index}: columns separated by |; each line is one row]\n'+'\n'.join(lines))
    except (AttributeError,ValueError,RuntimeError):
        # Native text remains available when a layout cannot be recognized.
        return ''
    return '\n\n'.join(blocks)


def parse_pdf(file_path: str) -> str:
    try:
        # Opening bytes avoids PyMuPDF retaining a Windows file handle when
        # construction fails on malformed input, which otherwise blocks cleanup.
        with fitz.open(stream=Path(file_path).read_bytes(), filetype="pdf") as doc:
            if doc.needs_pass:
                raise RuntimeError('Encrypted PDFs must be unlocked before upload')
            if len(doc)>200:
                raise RuntimeError('PDF exceeds the 200-page limit')
            chunks=[]
            deadline = time.monotonic() + 60
            for index,page in enumerate(doc,1):
                if time.monotonic() > deadline:
                    raise RuntimeError('PDF extraction exceeded its time budget; split the document and retry')
                text=page.get_text().strip()
                native=len(text)>=20 and sum(c.isalpha() for c in text)>=8
                if not native:
                    text=_ocr_page(page)
                else:
                    rows=_table_rows(page)
                    if rows:
                        text+='\n\n'+rows
                if text:
                    chunks.append(f"[{'PDF' if native else 'OCR'} page {index}]\n{text}")
            return '\n\n'.join(chunks)
    except (fitz.FileDataError, fitz.EmptyFileError) as exc:
        raise RuntimeError('Invalid or corrupt PDF') from exc


def parse_docx(file_path: str) -> str:
    from zipfile import ZipFile, BadZipFile
    from docx.opc.exceptions import PackageNotFoundError
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph
    from docx.table import Table
    from lxml.etree import XMLSyntaxError
    try:
        with ZipFile(file_path) as archive:
            if sum(info.file_size for info in archive.infolist())>32*1024*1024:
                raise RuntimeError('DOCX expanded content exceeds 32 MB')
        doc=Document(file_path)
        output=[]
        table_number=0
        def visit(element,parent,location=''):
            nonlocal table_number
            for child in element:
                if child.tag==qn('w:p'):
                    text=Paragraph(child,parent).text.strip()
                    if text:
                        output.append((f'[{location}]\n' if location else '')+text)
                elif child.tag==qn('w:tbl'):
                    table_number+=1
                    number=table_number
                    table=Table(child,parent)
                    seen=set()
                    for row_index,row in enumerate(table.rows,1):
                        for col_index,cell in enumerate(row.cells,1):
                            if cell._tc in seen:
                                continue
                            seen.add(cell._tc)
                            visit(cell._tc,cell,f'Table {number} row {row_index} column {col_index}')
        visit(doc.element.body,doc)
        return '\n\n'.join(output)
    except (BadZipFile, PackageNotFoundError, XMLSyntaxError, KeyError) as exc:
        raise RuntimeError('Invalid or corrupt DOCX') from exc


def parse_txt(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8",
              errors="strict") as f:
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
    raise RuntimeError("Supported formats are PDF, DOCX and UTF-8 TXT")
