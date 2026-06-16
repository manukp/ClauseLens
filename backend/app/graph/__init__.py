"""LangGraph orchestration spine (D1) — Stage-1 pipeline for Phase 2.

LangGraph structures the staged, stateful flow only; it never owns job/infra
orchestration (that stays in FastAPI + SQLite). Model calls inside nodes go
through the boto3 Converse wrappers (D2), never langchain-aws.
"""
from .pipeline import build_graph, run_pipeline

__all__ = ["build_graph", "run_pipeline"]
