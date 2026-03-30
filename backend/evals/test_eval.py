"""Pytest-integrated eval tests for the creator agent.

Run with: cd backend && uv run pytest evals/test_eval.py -v

These tests call a real LLM and cost money — they are NOT included
in `make test` (testpaths only covers backend/tests/).
"""

from __future__ import annotations

import pytest

from evals.conftest import make_agent, make_task
from evals.dataset import EVAL_CASES, build_dataset
from evals.distribution import print_distribution_report
from evals.metrics import default_evaluators
from evals.prompts import PROMPT_VARIANTS

VARIANT = "baseline"


@pytest.fixture(scope="module")
def report():
    """Run all eval cases through the agent once, score with all evaluators."""
    agent = make_agent(PROMPT_VARIANTS[VARIANT])
    dataset = build_dataset(evaluators=default_evaluators())
    return dataset.evaluate_sync(make_task(agent), name=VARIANT, max_concurrency=1)


@pytest.fixture(scope="module", autouse=True)
def show_report(report):
    """Print the full eval report and distribution stats after all tests."""
    yield
    report.print(include_input=True, include_reasons=True)
    print_distribution_report(report)


@pytest.mark.parametrize("case_name", [c.name for c in EVAL_CASES])
def test_validity(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Validity")
    assert score is not None, f"{case_name}: Validity score missing"
    assert score.value >= 1.0, f"{case_name}: validity={score.value}, reason={score.reason}"


@pytest.mark.parametrize("case_name", [c.name for c in EVAL_CASES])
def test_relevance(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Relevance")
    assert score is not None, f"{case_name}: Relevance score missing"


@pytest.mark.parametrize("case_name", [c.name for c in EVAL_CASES])
def test_creativity(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Creativity")
    assert score is not None, f"{case_name}: Creativity score missing"


@pytest.mark.parametrize("case_name", [c.name for c in EVAL_CASES])
def test_coherence(report, case_name):
    rc = next(c for c in report.cases if c.name == case_name)
    score = rc.scores.get("Coherence")
    assert score is not None, f"{case_name}: Coherence score missing"
