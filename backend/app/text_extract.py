# backend/app/text_extract.py
from __future__ import annotations
from typing import Optional
from io import BytesIO


def _normalize(text: str) -> str:
    # compact whitespace while keeping line breaks
    return "\n".join(
        " ".join(line.split()) for line in text.replace("\r", "").split("\n")
    ).strip()


def pdf_bytes_to_text(data: bytes) -> str:
    """
    Minimal, dependency-light PDF text extractor using pypdf.
    Falls back to utf-8 decode if needed.
    """
    try:
        from pypdf import PdfReader  # pip install pypdf

        reader = PdfReader(BytesIO(data))
        pages = []
        for p in reader.pages:
            try:
                pages.append(p.extract_text() or "")
            except Exception:
                pages.append("")
        return _normalize("\n".join(pages))
    except Exception:
        # last-resort: try binary decode
        try:
            return _normalize(data.decode("utf-8", errors="ignore"))
        except Exception:
            return ""
