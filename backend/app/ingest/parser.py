"""PyMuPDF parsing (D4): PDF bytes -> ordered transcript with page + bbox.

We extract span-level geometry (text, bounding box in PDF points, font size and
weight) so the chunker can detect headings by layout and so citations can point
to an exact region for clickable highlighting. PyMuPDF (``fitz``) only — no
second parser (D4 guard).

Transcript shape (persisted as JSON under ``data/jobs/{id}/``):

    {
      "doc_id": str, "doc_name": str, "page_count": int,
      "pages": [
        { "page": 1, "width": float, "height": float,
          "text": str,
          "lines": [
            { "text": str, "bbox": [x0,y0,x1,y1],
              "size": float, "bold": bool }
          ] }
      ]
    }
"""
from __future__ import annotations

import fitz  # PyMuPDF


def _line_is_bold(spans: list[dict]) -> bool:
    """A line reads as bold if any span carries the bold flag or a bold name."""
    for s in spans:
        # PyMuPDF flags bit 4 (value 16) marks bold; font names also hint it.
        if s.get("flags", 0) & 16:
            return True
        if "bold" in str(s.get("font", "")).lower():
            return True
    return False


def parse_pdf(data: bytes, doc_id: str, doc_name: str) -> dict:
    """Parse PDF bytes into an ordered, geometry-aware transcript."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        pages: list[dict] = []
        for index in range(doc.page_count):
            page = doc.load_page(index)
            rect = page.rect
            page_dict = page.get_text("dict")
            lines_out: list[dict] = []
            text_parts: list[str] = []
            for block in page_dict.get("blocks", []):
                if block.get("type", 0) != 0:  # 0 == text block
                    continue
                for line in block.get("lines", []):
                    spans = line.get("spans", [])
                    line_text = "".join(s.get("text", "") for s in spans).strip()
                    if not line_text:
                        continue
                    bbox = [round(float(v), 2) for v in line.get("bbox", rect)]
                    size = max((float(s.get("size", 0.0)) for s in spans), default=0.0)
                    lines_out.append(
                        {
                            "text": line_text,
                            "bbox": bbox,
                            "size": round(size, 2),
                            "bold": _line_is_bold(spans),
                        }
                    )
                    text_parts.append(line_text)
            pages.append(
                {
                    "page": index + 1,  # 1-based (Citation contract)
                    "width": round(float(rect.width), 2),
                    "height": round(float(rect.height), 2),
                    "text": "\n".join(text_parts),
                    "lines": lines_out,
                }
            )
        return {
            "doc_id": doc_id,
            "doc_name": doc_name,
            "page_count": doc.page_count,
            "pages": pages,
        }
    finally:
        doc.close()
