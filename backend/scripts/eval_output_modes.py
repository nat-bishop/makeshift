#!/usr/bin/env python3
"""Run pairwise evals with different PydanticAI output modes.

Patches app.creator.llm to use each output mode, then runs the pairwise
eval suite. Compares pass rates and latency across modes.

Usage:
    cd backend && uv run python scripts/eval_output_modes.py
"""

from __future__ import annotations

import asyncio
import io
import sys
import time

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, NativeOutput, PromptedOutput, TextOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.cache.scene import SceneCache
from app.cache.store import CacheStore
from app.config import settings
from app.creator import llm as llm_module
from app.engine.pairwise import evaluate_pair

from evals.helpers import (
    SummaryEvaluator,
    load_suite,
    make_blueprint,
    orient_expected,
)
from evals.run_pairwise import (
    PairwiseEvaluator,
    PairwiseExpected,
    PairwiseInput,
)
from pydantic_evals import Case, Dataset


# ---------------------------------------------------------------------------
# Model builders
# ---------------------------------------------------------------------------

def _build_model(with_profile=False):
    if settings.local_llm_url:
        kw = {}
        if with_profile:
            kw["profile"] = OpenAIModelProfile(supports_json_schema_output=True)
        return OpenAIChatModel(
            settings.llm_model,
            provider=OpenAIProvider(base_url=settings.local_llm_url, api_key="unused"),
            **kw,
        )
    return settings.llm_model


def _base_settings() -> dict:
    s: dict = {"temperature": 0.0}
    if settings.local_llm_url:
        s["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    return s


def _parse_int(text: str) -> int:
    cleaned = text.strip().strip('"').strip()
    num = ""
    for ch in cleaned:
        if ch in "-0123456789":
            num += ch
        elif num:
            break
    return int(num) if num else 0


# ---------------------------------------------------------------------------
# Mode configurations
# ---------------------------------------------------------------------------

@dataclass
class ModeConfig:
    name: str
    description: str

    def patch(self) -> None:
        """Monkey-patch llm_module to use this output mode."""
        raise NotImplementedError


class ToolMode(ModeConfig):
    """Default: output_type=int, tool call."""

    def patch(self) -> None:
        llm_module.reset_agents()
        model = _build_model()
        base = _base_settings()
        llm_module._int_agent = Agent(model, output_type=int, retries=2, model_settings=base)
        llm_module._float_agent = Agent(model, output_type=float, retries=2, model_settings=base)


class NativeMode(ModeConfig):
    """NativeOutput: response_format json_schema."""

    def patch(self) -> None:
        llm_module.reset_agents()
        model = _build_model(with_profile=True)
        base = _base_settings()
        llm_module._int_agent = Agent(model, output_type=NativeOutput(int), retries=2, model_settings=base)
        llm_module._float_agent = Agent(model, output_type=NativeOutput(float), retries=2, model_settings=base)


class PromptedMode(ModeConfig):
    """PromptedOutput: schema in system prompt + json_object mode."""

    def patch(self) -> None:
        llm_module.reset_agents()
        model = _build_model()
        base = _base_settings()
        llm_module._int_agent = Agent(model, output_type=PromptedOutput(int), retries=2, model_settings=base)
        llm_module._float_agent = Agent(model, output_type=PromptedOutput(float), retries=2, model_settings=base)


class TextPromptMode(ModeConfig):
    """TextOutput + 'Reply with ONLY a number' suffix.

    Patches ask_int and ask_bool to append instruction and parse.
    """

    def patch(self) -> None:
        llm_module.reset_agents()
        model = _build_model()
        base = _base_settings()

        text_agent = Agent(model, output_type=TextOutput(_parse_int), retries=2, model_settings=base)
        # Store on module so ask_int/ask_bool can find it
        llm_module._text_int_agent = text_agent

        # Monkey-patch ask_int
        async def patched_ask_int(prompt, lo=0, hi=100, default=50):
            try:
                result = await text_agent.run(
                    prompt + " Reply with ONLY a number, nothing else."
                )
                return max(lo, min(hi, result.output))
            except Exception:
                return default

        async def patched_ask_bool(prompt, default=False):
            try:
                result = await text_agent.run(
                    prompt + " Reply with ONLY 0 or 1, nothing else."
                )
                return result.output == 1
            except Exception:
                return default

        llm_module.ask_int = patched_ask_int
        llm_module.ask_bool = patched_ask_bool

    def unpatch(self) -> None:
        """Restore original ask_int/ask_bool."""
        import importlib
        importlib.reload(llm_module)


MODES = [
    ToolMode("tool", "output_type=int (tool call) -- current production"),
    NativeMode("native", "NativeOutput(int) -- response_format json_schema"),
    PromptedMode("prompted", "PromptedOutput(int) -- schema in system prompt"),
    TextPromptMode("text+prompt", "TextOutput + 'Reply ONLY a number' instruction"),
]


# ---------------------------------------------------------------------------
# Build dataset (same as run_pairwise.py)
# ---------------------------------------------------------------------------

def build_pairwise_dataset() -> Dataset[PairwiseInput, dict[str, Any], PairwiseExpected]:
    suite = load_suite()
    cases = []
    for entry in suite["pairs"]:
        pair = entry["pair"]
        raw_expected = entry["expected"]
        oriented = orient_expected(pair, raw_expected)
        cases.append(
            Case(
                name=f"{pair[0]} vs {pair[1]}",
                inputs=PairwiseInput(pair=pair),
                metadata=PairwiseExpected(expected=oriented, note=entry.get("note", "")),
            )
        )
    return Dataset(
        cases=cases, evaluators=[PairwiseEvaluator()], report_evaluators=[SummaryEvaluator()]
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

REPEAT = 3


async def main() -> None:
    settings.creation_cache_enabled = False

    dataset = build_pairwise_dataset()
    results: list[dict[str, Any]] = []

    for mode in MODES:
        print(f"\n{'=' * 70}")
        print(f"  MODE: {mode.name} -- {mode.description}")
        print(f"{'=' * 70}\n")

        mode.patch()

        # Fresh cache each mode
        cache = await CacheStore.open(":memory:")
        scene = SceneCache()

        async def pairwise_task(inputs: PairwiseInput) -> dict[str, Any]:
            bp_a = make_blueprint(inputs.pair[0])
            bp_b = make_blueprint(inputs.pair[1])
            pr = await evaluate_pair(bp_a, bp_b, cache, scene)
            return pr.to_dict()

        t0 = time.monotonic()
        report = await dataset.evaluate(
            pairwise_task, name=f"pairwise_{mode.name}", repeat=REPEAT,
        )
        elapsed = time.monotonic() - t0

        report.print(include_reasons=True)

        # Extract pass rate from report analyses
        pass_rate = None
        for analysis in report.analyses:
            if hasattr(analysis, "value") and "pass rate" in getattr(analysis, "title", "").lower():
                pass_rate = analysis.value
                break

        results.append({
            "mode": mode.name,
            "pass_rate": pass_rate,
            "elapsed_s": elapsed,
            "cases": len(report.cases),
        })

        await cache.close()

        # Restore original functions if needed
        if isinstance(mode, TextPromptMode):
            mode.unpatch()

    # Summary comparison
    print(f"\n{'=' * 70}")
    print(f"  COMPARISON ACROSS MODES")
    print(f"{'=' * 70}")
    fmt = "  {:<14} {:>10} {:>10} {:>12}"
    print(fmt.format("Mode", "Pass Rate", "Time", "Per Case"))
    print(f"  {'-' * 52}")
    for r in results:
        pr = f"{r['pass_rate']}%" if r["pass_rate"] is not None else "N/A"
        per_case = r["elapsed_s"] / (r["cases"] * REPEAT) if r["cases"] else 0
        print(fmt.format(
            r["mode"], pr,
            f"{r['elapsed_s']:.1f}s",
            f"{per_case * 1000:.0f}ms",
        ))


if __name__ == "__main__":
    asyncio.run(main())
