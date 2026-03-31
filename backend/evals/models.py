"""Pydantic models for eval result persistence.

Every eval run (CLI or pytest) saves an EvalRunResult to JSON.
Comparison and distribution analysis load these files directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ParsedOutput(BaseModel):
    """Pre-parsed fields from CreatorOutputSpec for analysis."""

    name: str
    tags: list[str]
    signature: str | None = None
    resolved_behaviors: list[str] = []
    size_category: str
    visual_description: str


class CaseResult(BaseModel):
    """Result of evaluating a single case."""

    case: str
    inputs: str
    category: str
    expected_tags: list[str]

    output_raw: str | None
    output: ParsedOutput | None
    error: str | None

    scores: dict[str, float]
    reasons: dict[str, str]

    elapsed: float
    retries: int
    retry_errors: list[str] = []

    trace_id: str | None = None
    span_id: str | None = None


class DatasetInfo(BaseModel):
    """Snapshot of which cases were included in the run."""

    total_cases: int
    categories: dict[str, int]
    case_names: list[str]


class EvalRunResult(BaseModel):
    """Top-level result file schema. One file = one eval run."""

    version: int = 1
    name: str
    variant: str
    timestamp: datetime
    model: str
    judge_model: str
    dataset: DatasetInfo
    cases: list[CaseResult]
    mean_scores: dict[str, float]
    retry_stats: dict[str, float | int]
