# Sample contracts

Four domain contracts with **deliberately planted issues** for the demo. Each
issue is the test oracle in [`ANSWER_KEY.md`](ANSWER_KEY.md) — do not "fix" them;
the demo's value is that ClauseLens catches them, cites them, and the judge
confirms them.

| Domain | Files | Notes |
|--------|-------|-------|
| Software development (**hero**) | `software_dev/` — MSA + SOW + Change Order | Upload all **three** as **one** analysis; exercises cross-document reconciliation (C1–C3). |
| Construction fit-out | `construction_fitout_agreement.{md,pdf}` | Single document. |
| Marketing services | `marketing_services_agreement.{md,pdf}` | Single document. |
| Clinical research | `clinical_research_agreement.{md,pdf}` | Single document. |

Each contract is authored in Markdown (the human-readable source) and rendered to
a PDF for upload (ClauseLens ingests PDFs only, D17). To re-render after editing a
source:

```sh
python scripts/md_to_pdf.py --all          # renders every *.md (recursively) to .pdf
```

The hero PDFs under `software_dev/` are the exact files the **pre-baked analysis**
(`data/seed/`) was run against, so a fresh live upload of them reproduces the
pre-baked findings. See the top-level `README.md` for the demo flow.
