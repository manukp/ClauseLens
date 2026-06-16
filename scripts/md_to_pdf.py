"""Render a sample-contract markdown file to a structured PDF for ingest testing.

The sample contracts in ``data/sample_contracts/*.md`` are authored in markdown,
but ClauseLens ingests PDFs only (D17). This converter renders them with real
typographic structure — headings in a larger bold face, body text wrapped and
paginated — so the clause-aware chunker's font/layout heuristics (and multi-page
citation attribution) are exercised the way a real contract would exercise them.

PyMuPDF only (consistent with D4). Builtin fonts: ``helv`` / ``hebo`` (bold) —
the bold face reports a "Bold" name, which the chunker's heading heuristic reads.

Usage:
    python scripts/md_to_pdf.py data/sample_contracts/software_dev_agreement.md
    python scripts/md_to_pdf.py --all        # convert every sample contract
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import fitz  # PyMuPDF

PAGE = fitz.paper_rect("a4")
MARGIN = 64.0
BODY_FONT, BOLD_FONT = "helv", "hebo"

# (markdown prefix) -> (font, size, space-before)
_HEADINGS = [
    ("### ", (BOLD_FONT, 12.0, 8.0)),
    ("## ", (BOLD_FONT, 13.5, 12.0)),
    ("# ", (BOLD_FONT, 18.0, 14.0)),
]
BODY = (BODY_FONT, 11.0, 2.0)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

# The Base-14 fonts (helv/hebo) are Latin-1 only — non-Latin glyphs (₹, em dash,
# smart quotes) would render as the replacement char and silently corrupt the
# source text we ingest. Map them to faithful ASCII so amounts/dashes survive.
_ASCII = {
    "₹": "INR ",  # ₹ rupee
    "—": "-", "–": "-",  # em / en dash
    "‘": "'", "’": "'",  # smart single quotes
    "“": '"', "”": '"',  # smart double quotes
    "…": "...",  # ellipsis
    "•": "-",   # bullet
    " ": " ",   # non-breaking space
}


def _ascii(s: str) -> str:
    for bad, good in _ASCII.items():
        s = s.replace(bad, good)
    return s


def _style(line: str) -> tuple[str, tuple[str, float, float]]:
    """Strip markdown markers; return (clean_text, (font, size, space_before))."""
    for prefix, style in _HEADINGS:
        if line.startswith(prefix):
            return _ascii(_BOLD_RE.sub(r"\1", line[len(prefix):]).strip()), style
    text = line
    # A line that is entirely a bold label (e.g. **Parties:** ...) -> bold body.
    if text.startswith("**"):
        return _ascii(_BOLD_RE.sub(r"\1", text).strip()), (BOLD_FONT, 11.0, 4.0)
    if text.startswith("- "):
        text = "-  " + text[2:]
    return _ascii(_BOLD_RE.sub(r"\1", text).strip()), BODY


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    if not text:
        return [""]
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if fitz.get_text_length(trial, fontname=font, fontsize=size) <= width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render(md_path: Path, pdf_path: Path | None = None) -> Path:
    pdf_path = pdf_path or md_path.with_suffix(".pdf")
    doc = fitz.open()
    page = doc.new_page(width=PAGE.width, height=PAGE.height)
    usable = PAGE.width - 2 * MARGIN
    y = MARGIN

    def new_page() -> None:
        nonlocal page, y
        page = doc.new_page(width=PAGE.width, height=PAGE.height)
        y = MARGIN

    for raw in md_path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip():
            y += 6.0
            continue
        text, (font, size, space_before) = _style(line)
        y += space_before
        for wrapped in _wrap(text, font, size, usable):
            if y + size > PAGE.height - MARGIN:
                new_page()
            page.insert_text((MARGIN, y), wrapped, fontname=font, fontsize=size)
            y += size * 1.45

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parents[1] / "data" / "sample_contracts"
    if "--all" in argv:
        targets = sorted(p for p in root.glob("*.md") if p.name != "ANSWER_KEY.md")
    elif argv:
        targets = [Path(argv[0])]
    else:
        print(__doc__)
        return 2
    for md in targets:
        out = render(md)
        print(f"rendered {md.name} -> {out}  ({out.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
