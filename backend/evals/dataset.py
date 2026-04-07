"""Eval dataset — 90 curated cases loaded from YAML.

Cases live in dataset.yaml (editable without touching Python).
CaseMeta type is defined here for use by evaluators and result models.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator


@dataclass(frozen=True)
class CaseMeta:
    category: str
    expected_tags: list[str] = field(default_factory=list)
    expected_substance: str | None = None
    expected_element: str | None = None
    expected_categories: list[str] = field(default_factory=list)
    notes: str = ""


CreatorCase = Case[str, str, CaseMeta]

_DATASET_PATH = Path(__file__).parent / "dataset.yaml"


def build_dataset(
    evaluators: list[Evaluator] | None = None,
) -> Dataset[str, str, CaseMeta]:
    """Load the eval dataset from YAML with optional evaluators."""
    dataset = Dataset[str, str, CaseMeta].from_file(_DATASET_PATH)
    if evaluators:
        dataset.evaluators = evaluators
    return dataset
