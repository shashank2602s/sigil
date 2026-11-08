"""Turn uploaded files into plain text plus accessibility notes."""
import io
import re

MAX_CHARS = 20000
ALLOWED = ("txt", "md", "docx", "pdf")


def normalize(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _docx(data):
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    notes = []
    for i, shape in enumerate(doc.inline_shapes, 1):
        try:
            doc_pr = shape._inline.docPr
            descr = (doc_pr.get("descr") or doc_pr.get("title") or "").strip()
        except Exception:
            descr = ""
        if not descr:
            notes.append({"type": "image_no_alt", "index": i})
    return "\n\n".join(parts), notes


def _pdf(data):
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages[:30]:
            pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def parse_upload(filename, data):
    """Return (text, notes). Raises ValueError for unsupported or empty files."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED:
        raise ValueError("Unsupported file type. Use .txt, .md, .docx or .pdf.")
    notes = []
    if ext in ("txt", "md"):
        text = data.decode("utf-8", "replace")
    elif ext == "docx":
        text, notes = _docx(data)
    else:
        text = _pdf(data)
    text = normalize(text)
    if not text:
        raise ValueError("No readable text found in that file.")
    if len(text) > MAX_CHARS:
        raise ValueError(f"File is too long (limit {MAX_CHARS} characters).")
    return text, notes
