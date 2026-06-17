"""Live Stage-2 verification (Phase 3): run the full pipeline on the hero contract
against real Bedrock + FAISS and print the cited Stage-2 outputs. Run from backend/:

    .venv/Scripts/python.exe scripts/verify_stage2.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.graph import run_pipeline
from app.models.schemas import Job, JobStatus
from app.routes import analyses
from app.store import artifacts, get_job_store

HERO = Path(__file__).resolve().parents[2] / "data" / "sample_contracts" / "software_dev_agreement.pdf"


def main() -> None:
    store = get_job_store()
    job = store.create(Job(name="Phase 3 live verify", status=JobStatus.queued))
    jid = job.job_id
    (artifacts.uploads_dir(jid) / HERO.name).write_bytes(HERO.read_bytes())
    artifacts.add_document(jid, {
        "doc_id": "doc_hero", "doc_name": HERO.stem, "filename": HERO.name, "s3_key": f"jobs/{jid}/{HERO.name}",
    })

    print(f"Running pipeline for job {jid} on {HERO.name} ...")
    run_pipeline(jid)
    print("Status:", store.get(jid).status, "| stage:", store.get(jid).current_stage)

    items = artifacts.read_json(jid, artifacts.STRUCTURED, default=[])
    rag_meta = artifacts.read_json(jid, artifacts.RAG_META, default={})
    eg = artifacts.read_json(jid, artifacts.ENTITY_GRAPH, default={})
    findings = artifacts.read_json(jid, artifacts.FINDINGS, default=[])

    by_cat: dict[str, int] = {}
    for it in items:
        by_cat[it["category"]] = by_cat.get(it["category"], 0) + 1
    print("\n== STRUCTURED ITEMS ==", by_cat, f"(total {len(items)})")
    for it in items[:6]:
        print(f"  [{it['category']}] {it['title']}  attrs={it['attributes']}  cites={len(it['citations'])}")

    print("\n== RAG LOOP COUNTS ==", rag_meta)

    print(f"\n== GRAPH == nodes={len(eg.get('nodes', []))} edges={len(eg.get('edges', []))}")
    for e in eg.get("edges", [])[:8]:
        print(f"  {e['relation']}: {e['source'][:8]} -> {e['target'][:8]}  cites={len(e['citations'])}")

    print(f"\n== FINDINGS == ({len(findings)})")
    for f in findings:
        v = f.get("judge") or {}
        flag = "" if v.get("passed") else "  <-- FLAGGED"
        print(f"  [{f['severity']}/{f['type']}] {f['title']}")
        print(f"      cites={len(f['citations'])} loop={f['loop_count']} judge={v.get('score')}/{v.get('passed')}{flag}")

    obs = analyses.get_observability(jid)
    t = obs["totals"]
    step_calls = sum(s["calls"] for s in obs["by_step"].values())
    print(f"\n== OBSERVABILITY == calls={t['calls']} cost=${t['cost_usd']:.4f} "
          f"latency={t['latency_ms']}ms | per-step sum reconciles={step_calls == t['calls']}")
    for step, s in sorted(obs["by_step"].items()):
        print(f"  {step:24s} calls={s['calls']:3d} cost=${s['cost_usd']:.4f}")

    # ---- High-severity citation narrowing, verified via GET /{id}/source/{chunk_id} ----
    print("\n== HIGH-SEVERITY CITATION NARROWING (via source endpoint) ==")

    def _show(label: str, finding: dict | None) -> None:
        if not finding:
            print(f"  {label}: NOT FOUND"); return
        print(f"  {label}: [{finding['severity']}/{finding['type']}] {finding['title']}")
        for cite in finding["citations"]:
            src = analyses.get_source(jid, cite["chunk_id"])  # the result API endpoint
            section = src["bbox"]
            cb = cite["bbox"]
            inside = (cb and section and cb[0] >= section[0] - 0.5 and cb[1] >= section[1] - 0.5
                      and cb[2] <= section[2] + 0.5 and cb[3] <= section[3] + 0.5 and cb != section)
            print(f"    chunk {cite['chunk_id']}  heading='{src['lines'][0]['text'] if src['lines'] else ''}'")
            print(f"      section bbox : {section}")
            print(f"      citation bbox: {cb}  page={cite['page']}  (strict subset of section: {inside})")
            print(f"      citation text: {cite['text_span'][:90]!r}")

    ms2 = next((f for f in findings if "milestone 2" in f["title"].lower()), None)
    conflict = next((f for f in findings if f["type"] == "conflict"), None)
    _show("Milestone-2 gap", ms2)
    _show("UAT-vs-migration conflict", conflict)


if __name__ == "__main__":
    main()
