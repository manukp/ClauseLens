"""Render the presentation diagrams for the deck (Phase 5, task 5).

Produces, in ``docs/``:
  - architecture.pdf / architecture.png  — S3, Bedrock (two tiers + Titan), FAISS,
    SQLite, the single FastAPI process, React SPA, and the LangGraph nodes.
  - flow.pdf / flow.png                   — the Stage-1 -> Stage-2 pipeline,
    including the self-reflective RAG loop and the independent LLM-as-judge.

Drawn directly with PyMuPDF primitives (the project's only parser dep, D4) so the
export is deterministic and needs no headless browser or extra packages. The
on-brand mermaid sources (architecture.mmd / flow.mmd) are committed alongside for
anyone who wants to re-style in a mermaid tool. Design tokens match CLAUDE.md.

Run:  backend/.venv/Scripts/python scripts/make_diagrams.py
"""
from __future__ import annotations

from pathlib import Path

import fitz

DOCS = Path(__file__).resolve().parents[1] / "docs"

# Design tokens (CLAUDE.md), as 0..1 RGB.
INK = (0.106, 0.141, 0.188)        # #1B2430
CANVAS = (0.969, 0.957, 0.937)     # #F7F4EF
SLATE = (0.278, 0.333, 0.392)      # #475569
MARIGOLD = (0.851, 0.463, 0.024)   # #D97706
NAVY = (0.078, 0.114, 0.161)       # recessed stage
GARNET = (0.608, 0.173, 0.173)     # #9B2C2C
OCHRE = (0.710, 0.451, 0.102)      # #B5731A
SAGE = (0.302, 0.486, 0.435)       # #4D7C6F
WHITE = (1, 1, 1)
PAPER = (0.992, 0.988, 0.980)

HELV, BOLD = "helv", "hebo"

# Base-14 fonts (helv/hebo) are Latin-1 only — map the few non-Latin glyphs we use
# to faithful ASCII so they don't render as the replacement char (D4/md_to_pdf note).
_ASCII = {"—": "-", "–": "-", "·": "-", "→": "->",
          "→": "->", "‘": "'", "’": "'", "“": '"', "”": '"'}


def _san(s: str) -> str:
    for bad, good in _ASCII.items():
        s = s.replace(bad, good)
    return s


def _text(page, rect, lines, *, size, color, font=HELV, align=fitz.TEXT_ALIGN_CENTER, leading=1.32):
    """Insert vertically-centred multi-line text into rect."""
    if isinstance(lines, str):
        lines = [lines]
    lines = [_san(ln) for ln in lines]
    total = len(lines) * size * leading
    y = rect.y0 + (rect.height - total) / 2 + size
    for ln in lines:
        page.insert_textbox(
            fitz.Rect(rect.x0, y - size, rect.x1, y + size),
            ln, fontname=font, fontsize=size, color=color, align=align,
        )
        y += size * leading


def _box(page, rect, *, fill, border=None, width=1.0, radius=8):
    shape = page.new_shape()
    if radius and min(rect.width, rect.height) > 0:
        frac = min(0.5, radius / min(rect.width, rect.height))
        shape.draw_rect(rect, radius=frac)
    else:
        shape.draw_rect(rect)
    shape.finish(fill=fill, color=border or fill, width=width)
    shape.commit()


def _card(page, rect, title, subtitle=None, *, fill=PAPER, border=SLATE,
          title_color=INK, sub_color=SLATE, accent=None, title_size=12, sub_size=8.5):
    _box(page, rect, fill=fill, border=border, width=1.0)
    if accent:  # left accent bar
        bar = fitz.Rect(rect.x0, rect.y0, rect.x0 + 5, rect.y1)
        _box(page, bar, fill=accent, border=accent, radius=4)
    pad = 10
    if subtitle:
        _text(page, fitz.Rect(rect.x0 + pad, rect.y0 + 6, rect.x1 - pad, rect.y0 + rect.height * 0.55),
              title, size=title_size, color=title_color, font=BOLD)
        _text(page, fitz.Rect(rect.x0 + pad, rect.y0 + rect.height * 0.45, rect.x1 - pad, rect.y1 - 6),
              subtitle, size=sub_size, color=sub_color)
    else:
        _text(page, fitz.Rect(rect.x0 + pad, rect.y0, rect.x1 - pad, rect.y1),
              title, size=title_size, color=title_color, font=BOLD)


def _elbow(page, pts, *, color=SLATE, width=1.6, head=7.0):
    """Orthogonal multi-segment connector with an arrowhead on the final segment."""
    import math
    shape = page.new_shape()
    for a, b in zip(pts, pts[1:]):
        shape.draw_line(fitz.Point(*a), fitz.Point(*b))
    # closePath=False: do NOT join the last point back to the first (that stray
    # segment from the arrowhead back to the start is what was ruining the image).
    shape.finish(color=color, width=width, closePath=False)
    p0, p1 = pts[-2], pts[-1]
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for da in (math.radians(150), math.radians(-150)):
        shape.draw_line(fitz.Point(*p1),
                        fitz.Point(p1[0] + head * math.cos(ang + da),
                                   p1[1] + head * math.sin(ang + da)))
    shape.finish(color=color, width=width, closePath=False)
    shape.commit()


def _arrow(page, p0, p1, *, color=SLATE, width=1.6, head=7.0, dash=None):
    shape = page.new_shape()
    shape.draw_line(fitz.Point(*p0), fitz.Point(*p1))
    shape.finish(color=color, width=width, dashes=dash)
    # arrow head
    import math
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    for da in (math.radians(150), math.radians(-150)):
        hx = p1[0] + head * math.cos(ang + da)
        hy = p1[1] + head * math.sin(ang + da)
        shape.draw_line(fitz.Point(*p1), fitz.Point(hx, hy))
    shape.finish(color=color, width=width)
    shape.commit()


def _save(doc, stem):
    DOCS.mkdir(parents=True, exist_ok=True)
    pdf = DOCS / f"{stem}.pdf"
    doc.save(str(pdf))
    page = doc[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(2.4, 2.4))  # ~2.4x for crisp slides
    png = DOCS / f"{stem}.png"
    pix.save(str(png))
    doc.close()
    print(f"wrote {pdf.name} ({pdf.stat().st_size} B) and {png.name} ({png.stat().st_size} B)")


# ---------------------------------------------------------------- architecture
def architecture():
    W, H = 1180, 720
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    _box(page, fitz.Rect(0, 0, W, H), fill=CANVAS, border=CANVAS, radius=0)
    _text(page, fitz.Rect(0, 18, W, 50), "ClauseLens — Architecture",
          size=20, color=INK, font=BOLD)
    _text(page, fitz.Rect(0, 46, W, 68),
          "Single long-lived FastAPI process · no Docker · local-first (D5/D6/D7)",
          size=10.5, color=SLATE)

    # Browser (left)
    browser = fitz.Rect(40, 120, 300, 250)
    _card(page, browser, "Browser — React SPA",
          ["Vite + React + Tailwind", "react-flow · react-pdf · recharts",
           "fonts bundled locally (D14)"], accent=MARIGOLD, title_size=12.5)

    # FastAPI container (center)
    fast = fitz.Rect(360, 96, 760, 624)
    _box(page, fast, fill=PAPER, border=INK, width=1.6)
    _text(page, fitz.Rect(fast.x0, fast.y0 + 10, fast.x1, fast.y0 + 46),
          "FastAPI — single process", size=14, color=INK, font=BOLD)
    _text(page, fitz.Rect(fast.x0, fast.y0 + 38, fast.x1, fast.y0 + 60),
          "serves the built React dist + JSON API (D7)", size=9, color=SLATE)

    lg = fitz.Rect(fast.x0 + 24, fast.y0 + 76, fast.x1 - 24, fast.y0 + 250)
    _box(page, lg, fill=NAVY, border=NAVY)
    _text(page, fitz.Rect(lg.x0, lg.y0 + 8, lg.x1, lg.y0 + 30),
          "LangGraph pipeline — orchestration only (D1)", size=11, color=WHITE, font=BOLD)
    nodes = ["parse", "chunk", "embed", "entities", "summaries", "master",
             "structured", "graph", "findings", "judge"]
    # Size the cells to the box so all 10 nodes (incl. the rightmost "summaries"
    # and "judge") sit INSIDE the LangGraph boundary.
    per, gap, chh, pad = 5, 8, 26, 16
    cw = (lg.width - 2 * pad - (per - 1) * gap) / per
    nx, ny = lg.x0 + pad, lg.y0 + 44
    for i, n in enumerate(nodes):
        col, row = i % per, i // per
        x0 = nx + col * (cw + gap)
        y0 = ny + row * (chh + 14)
        r = fitz.Rect(x0, y0, x0 + cw, y0 + chh)
        accent = MARIGOLD if n in ("structured", "findings") else (SAGE if n == "judge" else None)
        _box(page, r, fill=WHITE, border=accent or SLATE, width=1.2 if accent else 0.8)
        _text(page, r, n, size=8, color=INK, font=BOLD)
    _text(page, fitz.Rect(lg.x0, lg.y1 - 22, lg.x1, lg.y1 - 6),
          "reflective RAG loop on structured/findings · independent judge", size=7.6, color=(0.8, 0.84, 0.88))

    stores = [
        ("Job store — SQLite", "data/clauselens.db (D6)"),
        ("Vector index — FAISS", "local file, per-job (D5)"),
        ("Artifacts + uploads", "local JSON + source PDFs"),
    ]
    sy = lg.y1 + 18
    for t, s in stores:
        r = fitz.Rect(fast.x0 + 24, sy, fast.x1 - 24, sy + 56)
        _card(page, r, t, s, title_size=10.5, sub_size=8)
        sy += 66

    # AWS cluster (right)
    aws = fitz.Rect(820, 96, 1140, 540)
    _box(page, aws, fill=(0.94, 0.93, 0.91), border=SLATE, width=1.2)
    _text(page, fitz.Rect(aws.x0, aws.y0 + 8, aws.x1, aws.y0 + 28),
          "AWS  (us-east-1)", size=12, color=INK, font=BOLD)

    bed = fitz.Rect(aws.x0 + 18, aws.y0 + 40, aws.x1 - 18, aws.y0 + 300)
    _box(page, bed, fill=PAPER, border=INK)
    _text(page, fitz.Rect(bed.x0, bed.y0 + 8, bed.x1, bed.y0 + 28),
          "Amazon Bedrock", size=11.5, color=INK, font=BOLD)
    _text(page, fitz.Rect(bed.x0, bed.y0 + 26, bed.x1, bed.y0 + 42),
          "boto3 Converse / InvokeModel (D2)", size=8, color=SLATE)
    tiers = [
        ("Claude Haiku 4.5", "high-volume / structural", OCHRE),
        ("Claude Sonnet 4.6", "reasoning · judge (D8/D11)", GARNET),
        ("Titan Embeddings V2", "1024-dim vectors", SAGE),
    ]
    ty = bed.y0 + 52
    for t, s, c in tiers:
        r = fitz.Rect(bed.x0 + 12, ty, bed.x1 - 12, ty + 56)
        _card(page, r, t, s, accent=c, title_size=10, sub_size=7.8)
        ty += 64

    s3 = fitz.Rect(aws.x0 + 18, aws.y0 + 320, aws.x1 - 18, aws.y0 + 392)
    _card(page, s3, "Amazon S3", "source-of-truth for uploaded PDFs", title_size=11, sub_size=8)

    # arrows
    _arrow(page, (browser.x1, 185), (fast.x0, 185), color=MARIGOLD, width=2.0)
    _arrow(page, (fast.x0, 205), (browser.x1, 205), color=SLATE, width=1.2)
    _text(page, fitz.Rect(browser.x1, 150, fast.x0, 170), "HTTPS", size=8, color=SLATE)
    _text(page, fitz.Rect(browser.x1, 206, fast.x0, 224), "dist + /api", size=7.5, color=SLATE)

    _arrow(page, (fast.x1, 220), (bed.x0, 220), color=GARNET, width=2.0)
    _text(page, fitz.Rect(fast.x1, 196, bed.x0, 214), "model calls", size=8, color=GARNET)
    _arrow(page, (fast.x1, 470), (s3.x0, s3.y0 + 30), color=SLATE, width=1.4)
    _text(page, fitz.Rect(fast.x1, 452, s3.x0, 468), "put / get PDFs", size=7.5, color=SLATE)

    _save(doc, "architecture")


# ------------------------------------------------------------------------ flow
def flow():
    W, H = 1180, 760
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    _box(page, fitz.Rect(0, 0, W, H), fill=CANVAS, border=CANVAS, radius=0)
    _text(page, fitz.Rect(0, 16, W, 46), "ClauseLens — Analysis pipeline",
          size=20, color=INK, font=BOLD)
    _text(page, fitz.Rect(0, 44, W, 64),
          "Stage-1 ingest  →  Stage-2 analysis · every output carries a source citation (doc · page · bbox, D9/D18)",
          size=10, color=SLATE)

    def chip(x, y, w, h, title, sub=None, accent=None, fill=PAPER):
        r = fitz.Rect(x, y, x + w, y + h)
        _card(page, r, title, sub, accent=accent, fill=fill, title_size=10.5, sub_size=7.6)
        return r

    # Stage 1 row
    _text(page, fitz.Rect(40, 86, 300, 104), "STAGE 1 — INGEST  (Haiku · Titan)",
          size=10, color=SLATE, font=BOLD, align=fitz.TEXT_ALIGN_LEFT)
    s1 = [
        ("parse", "PyMuPDF: text + page + bbox"),
        ("chunk", "clause-aware (full clause)"),
        ("embed -> FAISS", "Titan vectors, per job"),
        ("entities", "parties / roles (Haiku)"),
        ("summaries", "per-doc + master"),
    ]
    y1 = 112
    w, h, gap = 196, 66, 30   # 5 chips fit within the 40px page margins (40..1140)
    rects1 = []
    x = 40
    for t, s in s1:
        rects1.append(chip(x, y1, w, h, t, s))
        x += w + gap
    for a, b in zip(rects1, rects1[1:]):
        _arrow(page, (a.x1, y1 + h / 2), (b.x0, y1 + h / 2))
    # (the stage-1 -> stage-2 connector is drawn after the stage-2 row, below,
    #  once extract_structured's rect exists — see _elbow call.)

    # Stage 2 row. The label sits just under row 1, leaving a clear channel below
    # it for the stage-1 -> stage-2 connector (drawn after the row, below).
    _text(page, fitz.Rect(40, 190, 380, 208), "STAGE 2 — ANALYSIS  (Sonnet)",
          size=10, color=SLATE, font=BOLD, align=fitz.TEXT_ALIGN_LEFT)
    y2 = 276
    s2 = [
        ("extract structured", "deliverables · owners · budgets", MARIGOLD),
        ("build graph", "node/edge JSON (D12)", None),
        ("detect findings", "risks · conflicts · gaps · deps", MARIGOLD),
        ("judge", "independent verify (D11)", SAGE),
    ]
    rects2 = []
    x = 40
    w2 = 230
    for t, s, acc in s2:
        rects2.append(chip(x, y2, w2, h, t, s, accent=acc))
        x += w2 + gap
    for a, b in zip(rects2, rects2[1:]):
        _arrow(page, (a.x1, y2 + h / 2), (b.x0, y2 + h / 2))

    # Stage-1 -> Stage-2: route summaries (rightmost, top row) down through a clear
    # channel below the STAGE-2 label, then into the TOP-CENTRE of extract structured
    # (clear of its left accent bar). The arrowhead lands on the box edge, not on it.
    su, es = rects1[-1], rects2[0]
    su_cx = su.x0 + w / 2
    es_cx = es.x0 + w2 / 2
    channel_y = 234
    _elbow(page, [(su_cx, y1 + h), (su_cx, channel_y), (es_cx, channel_y), (es_cx, y2)],
           width=1.6)

    # reflective RAG loop callout (D10) under extract structured + detect findings
    loop = fitz.Rect(40, 400, 40 + w2, 520)
    _box(page, loop, fill=NAVY, border=NAVY)
    _text(page, fitz.Rect(loop.x0, loop.y0 + 8, loop.x1, loop.y0 + 26),
          "self-reflective RAG loop (D10)", size=10, color=WHITE, font=BOLD)
    _text(page, fitz.Rect(loop.x0 + 10, loop.y0 + 28, loop.x1 - 10, loop.y1 - 8),
          ["retrieve  ->  grade relevance",
           "   -> (re-retrieve if weak)",
           "generate  ->  grade groundedness",
           "   -> (regenerate if ungrounded)"],
          size=8.4, color=(0.86, 0.89, 0.92), align=fitz.TEXT_ALIGN_LEFT, leading=1.5)
    _arrow(page, (rects2[0].x0 + w2 / 2, y2 + h), (loop.x0 + w2 / 2, loop.y0), color=MARIGOLD, width=1.6)

    # judge callout (D11)
    jcall = fitz.Rect(rects2[3].x0 - 40, 400, rects2[3].x1, 520)
    _box(page, jcall, fill=PAPER, border=SAGE, width=1.4)
    _text(page, fitz.Rect(jcall.x0, jcall.y0 + 8, jcall.x1, jcall.y0 + 26),
          "LLM-as-judge (D11)", size=10, color=SAGE, font=BOLD)
    _text(page, fitz.Rect(jcall.x0 + 10, jcall.y0 + 26, jcall.x1 - 10, jcall.y1 - 8),
          ["separate Sonnet reviewer,",
           "distinct role — scores each",
           "finding for correctness +",
           "bias against the whole",
           "contract; flags low/failed."],
          size=8.2, color=SLATE, align=fitz.TEXT_ALIGN_LEFT, leading=1.4)
    _arrow(page, (rects2[3].x0 + w2 / 2, y2 + h), (jcall.x0 + (jcall.width) / 2, jcall.y0),
           color=SAGE, width=1.6)

    # assurance ribbon
    rib = fitz.Rect(40, 560, W - 40, 632)
    _box(page, rib, fill=PAPER, border=MARIGOLD, width=1.2)
    _text(page, fitz.Rect(rib.x0, rib.y0 + 8, rib.x1, rib.y0 + 28),
          "Every finding:  grounded  ->  self-checked  ->  independently verified",
          size=12, color=INK, font=BOLD)
    _text(page, fitz.Rect(rib.x0, rib.y0 + 30, rib.x1, rib.y1 - 6),
          "cited to its source clause   ·   reflective loop re-retrieves/regenerates weak answers   ·   a separate AI judge scores correctness & bias",
          size=8.8, color=SLATE)

    _save(doc, "flow")


if __name__ == "__main__":
    architecture()
    flow()
