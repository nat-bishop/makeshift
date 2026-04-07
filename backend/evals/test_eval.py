"""Pytest-integrated eval tests for the creator agent.

Run with: cd backend && uv run pytest evals/test_eval.py -v

These tests call a real LLM and cost money — they are NOT included
in `make test` (testpaths only covers backend/tests/).
"""

from __future__ import annotations

import pytest
from app.config import settings

from evals.conftest import make_agent, make_task
from evals.dataset import build_dataset
from evals.distribution import print_distribution_report
from evals.io import report_to_result, save_result
from evals.metrics import default_evaluators
from evals.prompts import PROMPT_VARIANTS

VARIANT = "baseline"

_CASE_NAMES = [c.name for c in build_dataset().cases]


@pytest.fixture(scope="module")
def report():
    """Run all eval cases through the agent once, score with all evaluators."""
    agent = make_agent(PROMPT_VARIANTS[VARIANT])
    dataset = build_dataset(evaluators=default_evaluators())
    return dataset.evaluate_sync(make_task(agent), name=VARIANT, max_concurrency=64)


@pytest.fixture(scope="module", autouse=True)
def show_report(report):
    """Print the full eval report, save results, and show distribution stats."""
    yield
    import contextlib

    with contextlib.suppress(UnicodeEncodeError):
        report.print(include_input=True, include_reasons=True)

    result = report_to_result(report, VARIANT, settings.llm_model)
    run_dir = save_result(result)
    print(f"\nResults saved to {run_dir}")

    print_distribution_report(result)


@pytest.mark.parametrize("case_name", _CASE_NAMES)
def test_validity(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Validity")
    assert score is not None, f"{case_name}: Validity score missing"
    assert score.value >= 1.0, f"{case_name}: validity={score.value}, reason={score.reason}"


@pytest.mark.parametrize("case_name", _CASE_NAMES)
def test_faithfulness(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Faithfulness")
    assert score is not None, f"{case_name}: Faithfulness score missing"


@pytest.mark.parametrize("case_name", _CASE_NAMES)
def test_delight(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Delight")
    assert score is not None, f"{case_name}: Delight score missing"


@pytest.mark.parametrize("case_name", _CASE_NAMES)
def test_visual_clarity(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Visual Clarity")
    assert score is not None, f"{case_name}: Visual Clarity score missing"
