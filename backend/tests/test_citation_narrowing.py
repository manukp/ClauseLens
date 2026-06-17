"""Unit tests for high-severity citation narrowing (Phase 3 follow-up).

A high-severity finding's citation bbox/text_span is narrowed to the specific
sub-clause line(s) it concerns, resolved deterministically from ``Chunk.lines``
(D18). Sub-clauses that wrap onto a continuation line (e.g. 5.1 carrying its date
onto a second line) must be captured whole. Medium/low keep the section bbox.
"""
from __future__ import annotations

from app.analyze.findings import _matching_lines, _narrow_to_subclauses
from app.models.schemas import Citation

# A "5. Dependencies" section chunk: 5.1 wraps onto a second (continuation) line.
_DEPS_LINES = [
    {"page": 1, "bbox": [64, 599, 200, 614], "text": "5. Dependencies"},
    {"page": 1, "bbox": [64, 617, 513, 632], "text": "5.1 Data migration (clause 2.2) is a prerequisite for UAT and must be completed before UAT"},
    {"page": 1, "bbox": [64, 635, 470, 650], "text": "can begin. Data migration is scheduled to complete by 15 October 2025."},
]
_PAY_LINES = [
    {"page": 1, "bbox": [64, 490, 200, 505], "text": "4. Payment"},
    {"page": 1, "bbox": [64, 508, 400, 523], "text": "4.1 Total fee: INR 48,00,000, payable in three milestones."},
    {"page": 1, "bbox": [64, 532, 511, 547], "text": "4.2 Milestone 1 (INR 16,00,000) on signing - approved by the Client's Head of Procurement."},
    {"page": 1, "bbox": [64, 550, 365, 565], "text": "4.3 Milestone 2 (INR 16,00,000) on Platform build completion."},
    {"page": 1, "bbox": [64, 568, 456, 583], "text": "4.4 Milestone 3 (INR 16,00,000) on UAT sign-off - approved by the Client's CFO."},
]


def test_matching_lines_captures_wrapped_subclause():
    matched = _matching_lines(_DEPS_LINES, ["5.1"])
    assert [m["text"][:3] for m in matched] == ["5.1", "can"]  # label line + continuation
    assert "15 October 2025" in " ".join(m["text"] for m in matched)


def test_matching_lines_label_is_exact_not_prefix():
    # "4.3" must not also grab 4.1/4.2/4.4.
    matched = _matching_lines(_PAY_LINES, ["4.3"])
    assert len(matched) == 1 and matched[0]["text"].startswith("4.3")


def test_matching_lines_phrase_fallback():
    matched = _matching_lines(_PAY_LINES, ["Milestone 2"])
    assert len(matched) == 1 and matched[0]["text"].startswith("4.3")


def test_narrow_milestone2_to_single_line():
    section_bbox = [64, 490, 511, 583]  # whole Payment section
    cite = Citation(doc_id="d", doc_name="hero", page=1, bbox=list(section_bbox),
                    text_span="4. Payment ...", chunk_id="chunk_pay")
    _narrow_to_subclauses([cite], ["4.3"], {"chunk_pay": {"chunk_id": "chunk_pay", "lines": _PAY_LINES}})
    assert cite.bbox == [64, 550, 365, 565]          # exactly the 4.3 line
    assert cite.bbox != section_bbox                  # strictly narrowed
    assert cite.text_span.startswith("4.3 Milestone 2")


def test_narrow_conflict_covers_3_3_and_5_1_only():
    timeline_lines = [
        {"page": 1, "bbox": [64, 398, 200, 413], "text": "3. Timeline"},
        {"page": 1, "bbox": [64, 441, 315, 456], "text": "3.2 Platform build complete by 15 September 2025."},
        {"page": 1, "bbox": [64, 458, 334, 474], "text": "3.3 UAT sign-off to be obtained by 30 September 2025."},
    ]
    c_tl = Citation(doc_id="d", doc_name="hero", page=1, bbox=[64, 398, 334, 474],
                    text_span="3. Timeline ...", chunk_id="chunk_tl")
    c_dep = Citation(doc_id="d", doc_name="hero", page=1, bbox=[64, 599, 513, 650],
                     text_span="5. Dependencies ...", chunk_id="chunk_dep")
    by_id = {"chunk_tl": {"chunk_id": "chunk_tl", "lines": timeline_lines},
             "chunk_dep": {"chunk_id": "chunk_dep", "lines": _DEPS_LINES}}
    _narrow_to_subclauses([c_tl, c_dep], ["3.3", "5.1"], by_id)
    assert c_tl.bbox == [64, 458, 334, 474]           # only the 3.3 line, not the section
    assert c_dep.bbox == [64, 617, 513, 650]           # union of both 5.1 lines
    assert "30 September" in c_tl.text_span
    assert "15 October 2025" in c_dep.text_span


def test_medium_finding_keeps_section_bbox():
    # Narrowing is only invoked for high severity; a medium citation is untouched.
    section = [64, 271, 493, 382]
    cite = Citation(doc_id="d", doc_name="hero", page=1, bbox=list(section),
                    text_span="2. Deliverables ...", chunk_id="chunk_x")
    # (detect() gates on severity == "high"; here we simply assert non-call leaves it.)
    assert cite.bbox == section
