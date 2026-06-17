"""Stage-2 analysis (Phase 3): reason over the Stage-1 knowledge base.

Modules:
  rag.py          the self-reflective RAG loop as a compiled LangGraph sub-cycle (D10)
  structured.py   deliverables/owners/budgets/timelines/plans/compliance (Sonnet, D8)
  graph_build.py  node/edge JSON for react-flow (D12, graph-lite)
  findings.py     risk/conflict/gap/dependency/issue detection + LLM-as-judge (D11)

All model calls go through the boto3 Converse wrappers (D2); every artifact is
cited deterministically from chunk provenance (D9/D18); every call is logged (D13).
"""
