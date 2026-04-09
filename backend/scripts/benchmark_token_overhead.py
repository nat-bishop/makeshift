#!/usr/bin/env python3
"""Benchmark PydanticAI structured output modes — real-world latency.

Runs each request sequentially with a gap between them to prevent SGLang
from batching. Shuffles mode order each round. Measures wall-clock time
from Python call to result.

Also tests end-to-end API latency if the FastAPI server is running.

Usage:
    cd backend && uv run python scripts/benchmark_token_overhead.py
"""

from __future__ import annotations

import asyncio
import random
import statistics
import sys
import time
from dataclasses import dataclass, field

import httpx
from pydantic_ai import Agent, NativeOutput, PromptedOutput, TextOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings

ROUNDS = 5
INTER_REQUEST_DELAY = 0.3  # seconds between requests to prevent SGLang batching

# Pairwise-style prompts (the hot path)
TEST_PROMPTS = [
    (
        "damage",
        "A rock collides with another rock. Damage to rock? "
        "0=none 10=scratch 25=moderate 50=severe 75=critical 100=destroyed",
    ),
    (
        "force",
        "A rock collides with a wooden chair. "
        "Force on chair? -100(pull) to 100(push), 0=none",
    ),
    (
        "state",
        "A rock collides with a wooden chair. State change on chair? "
        "0=none 1=burning 2=frozen 3=wet 4=electrified "
        "5=remove_burning 6=remove_frozen 7=remove_wet 8=remove_electrified",
    ),
]


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


def _regex_settings() -> dict:
    s = _base_settings()
    if settings.local_llm_url:
        s["extra_body"]["regex"] = r"-?[0-9]{1,3}"
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


@dataclass
class Measurement:
    mode: str
    prompt_label: str
    input_tokens: int
    output_tokens: int
    wall_ms: float
    output_value: str
    round_num: int
    position: int  # position in shuffled order this round


@dataclass
class ModeRunner:
    name: str
    agent: Agent
    run_kwargs: dict = field(default_factory=dict)
    prompt_suffix: str = ""


async def measure(runner: ModeRunner, prompt_label: str, prompt: str,
                  round_num: int, position: int) -> Measurement:
    actual_prompt = prompt + runner.prompt_suffix
    t0 = time.monotonic()
    result = await runner.agent.run(actual_prompt, **runner.run_kwargs)
    elapsed = (time.monotonic() - t0) * 1000
    u = result.usage()
    inp = getattr(u, "input_tokens", None) or getattr(u, "request_tokens", 0) or 0
    out = getattr(u, "output_tokens", None) or getattr(u, "response_tokens", 0) or 0
    return Measurement(
        mode=runner.name, prompt_label=prompt_label,
        input_tokens=inp, output_tokens=out,
        wall_ms=elapsed,
        output_value=str(result.output).strip()[:20],
        round_num=round_num, position=position,
    )


async def measure_api_latency() -> list[float] | None:
    """Measure end-to-end latency through the FastAPI API if running."""
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
            # Check if API is up
            r = await client.get("/health", timeout=2)
            if r.status_code != 200:
                return None

            # Create a session
            r = await client.post("/api/sessions", timeout=5)
            if r.status_code != 200:
                return None
            session_id = r.json()["session"]["id"]

            # Measure object creation (full pipeline: LLM + sprite gen starts)
            times = []
            for prompt in ["rock", "wooden sword", "ice cube"]:
                await asyncio.sleep(INTER_REQUEST_DELAY)
                t0 = time.monotonic()
                r = await client.post(
                    f"/api/sessions/{session_id}/objects",
                    json={"description": prompt},
                    timeout=30,
                )
                elapsed = (time.monotonic() - t0) * 1000
                if r.status_code == 200:
                    times.append(elapsed)
                    name = r.json().get("blueprint", {}).get("name", "?")
                    print(f"    API create '{prompt}': {elapsed:.0f}ms -> {name}")

            return times if times else None
    except Exception:
        return None


def print_results(measurements: list[Measurement]) -> None:
    modes = ["tool", "native", "prompted", "text+regex", "text+prompt"]
    modes_seen = [m for m in modes if any(x.mode == m for x in measurements)]

    print(f"\n{'=' * 85}")
    print(f"  PydanticAI Output Mode Benchmark — Sequential, Shuffled")
    print(f"  Model: {settings.llm_model}")
    if settings.local_llm_url:
        print(f"  Endpoint: {settings.local_llm_url}")
    print(f"  Rounds: {ROUNDS}, inter-request delay: {INTER_REQUEST_DELAY}s")
    print(f"{'=' * 85}")

    # Per-mode summary
    fmt = "  {:<14} {:>5} {:>5} {:>7} {:>7} {:>7} {:>7}  {}"
    print(f"\n{fmt.format('Mode', 'In', 'Out', 'Median', 'Mean', 'Min', 'Max', 'Answers')}")
    print(f"  {'-' * 78}")

    mode_medians = {}
    for mode in modes_seen:
        ms = [m for m in measurements if m.mode == mode]
        times = [m.wall_ms for m in ms]
        med = statistics.median(times)
        mean = statistics.mean(times)
        mode_medians[mode] = med

        # Show unique answers
        answers = sorted(set(m.output_value for m in ms))
        answers_str = ", ".join(answers[:5])

        print(fmt.format(
            mode,
            str(ms[0].input_tokens),
            str(ms[0].output_tokens),
            f"{med:.0f}ms",
            f"{mean:.0f}ms",
            f"{min(times):.0f}ms",
            f"{max(times):.0f}ms",
            answers_str,
        ))

    # Speed comparison vs tool
    if "tool" in mode_medians:
        tool_med = mode_medians["tool"]
        print(f"\n  Speed vs tool mode (median):")
        for mode in modes_seen:
            if mode == "tool":
                continue
            med = mode_medians[mode]
            diff = tool_med - med
            ratio = tool_med / med if med > 0 else 0
            print(f"    {mode:<14}  {diff:>+.0f}ms  ({ratio:.1f}x faster)")

    # Per-prompt breakdown
    print(f"\n  Per-prompt medians (ms):")
    pfmt = "  {:<14}" + " {:>10}" * len(modes_seen)
    print(pfmt.format("", *modes_seen))
    print(f"  {'-' * (14 + 11 * len(modes_seen))}")
    for label in dict.fromkeys(m.prompt_label for m in measurements):
        row = []
        for mode in modes_seen:
            ms = [m for m in measurements if m.mode == mode and m.prompt_label == label]
            row.append(f"{statistics.median(m.wall_ms for m in ms):.0f}ms" if ms else "-")
        print(pfmt.format(label, *row))

    # Pipeline estimates
    if "tool" in mode_medians:
        print(f"\n  Pipeline latency estimates (sequential, 6 calls per pairwise pair):")
        for mode in modes_seen:
            med = mode_medians[mode]
            total = med * 6
            print(f"    {mode:<14}  {total:>7.0f}ms  ({med:.0f}ms × 6)")


async def main() -> None:
    model = _build_model()
    model_profiled = _build_model(with_profile=True)
    base = _base_settings()

    runners = [
        ModeRunner("tool", Agent(model, output_type=int, retries=0, model_settings=base)),
        ModeRunner("native", Agent(model_profiled, output_type=NativeOutput(int), retries=0, model_settings=base)),
        ModeRunner("prompted", Agent(model, output_type=PromptedOutput(int), retries=0, model_settings=base)),
        ModeRunner("text+regex", Agent(model, output_type=TextOutput(_parse_int), retries=0, model_settings=base),
                   run_kwargs={"model_settings": _regex_settings()}),
        ModeRunner("text+prompt", Agent(model, output_type=TextOutput(_parse_int), retries=0, model_settings=base),
                   prompt_suffix=" Reply with ONLY a number, nothing else."),
    ]

    # Warmup — 2 calls per runner to prime SGLang
    print("Warming up (2 calls each)...")
    warmup = "What is 1+1? 0-10"
    for r in runners:
        for _ in range(2):
            try:
                await r.agent.run(warmup + r.prompt_suffix, **r.run_kwargs)
            except Exception:
                pass
            await asyncio.sleep(0.1)
        print(f"  {r.name}: ready")

    print(f"\nRunning {ROUNDS} rounds × {len(TEST_PROMPTS)} prompts × {len(runners)} modes")
    print(f"(sequential, {INTER_REQUEST_DELAY}s gap, shuffled order each round)\n")

    measurements: list[Measurement] = []

    for rnd in range(ROUNDS):
        # Shuffle runner order each round
        order = list(range(len(runners)))
        random.shuffle(order)
        shuffled = [runners[i] for i in order]
        mode_order = " > ".join(r.name for r in shuffled)
        print(f"  Round {rnd + 1}/{ROUNDS}  [{mode_order}]")

        for label, prompt in TEST_PROMPTS:
            for pos, runner in enumerate(shuffled):
                await asyncio.sleep(INTER_REQUEST_DELAY)
                try:
                    m = await measure(runner, label, prompt, rnd, pos)
                    measurements.append(m)
                    print(f"    {label:<8} {runner.name:<14} {m.wall_ms:>6.0f}ms -> {m.output_value}")
                except Exception as e:
                    print(f"    {label:<8} {runner.name:<14} FAIL: {e}")

    if not measurements:
        print("\nAll measurements failed.")
        sys.exit(1)

    print_results(measurements)

    # End-to-end API test
    print(f"\n{'=' * 85}")
    print(f"  End-to-end API latency (FastAPI -> LLM pipeline -> response)")
    print(f"{'=' * 85}")
    print(f"  Checking if API is running on :8000...")
    api_times = await measure_api_latency()
    if api_times:
        print(f"\n  API create object: median {statistics.median(api_times):.0f}ms")
        print(f"  (includes: HTTP overhead + name gen + parallel fan-out + cache write)")
    else:
        print(f"  API not running — skipping. Start with 'make api' to test.")


if __name__ == "__main__":
    asyncio.run(main())
