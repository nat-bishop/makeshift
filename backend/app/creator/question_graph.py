"""Declarative LLM question graph with conditional gating.

Questions declare dependencies via Gate tuples. The executor uses
asyncio.Event per node for maximum parallelism — each question fires
the instant all its gates resolve, not when the entire prior stage completes.

Used by: creation pipeline, pairwise evaluation, creature behavior.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from app.creator.llm import ask_bool, ask_float, ask_int, ask_text

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

logger = structlog.get_logger()


@dataclass(frozen=True)
class Gate:
    """Dependency on a prior question's result."""

    key: str  # question key to wait on
    check: Callable[[object], bool]  # predicate — True means "fire this question"


@dataclass(frozen=True)
class Question:
    """Single LLM question with optional conditional gates."""

    key: str
    prompt: str  # f-string with named placeholders
    qtype: str  # "int", "float", "bool", "text"
    lo: int | float = 0
    hi: int | float = 100
    default: int | float | str = 50
    max_tokens: int = 4  # only used for qtype="text"
    gates: tuple[Gate, ...] = field(default_factory=tuple)


async def run_questions(
    questions: Sequence[Question],
    context: dict[str, str],
) -> dict[str, int | float | bool | str]:
    """Execute a question graph with maximum parallelism.

    Each question fires as soon as all its gates resolve and pass.
    Ungated questions fire immediately. Returns results dict keyed by question key.
    Skipped questions (gate condition failed) are absent from results.
    """
    results: dict[str, int | float | bool | str] = {}
    events: dict[str, asyncio.Event] = {q.key: asyncio.Event() for q in questions}

    async def _run(q: Question) -> None:
        # Wait for all gate dependencies
        for gate in q.gates:
            if gate.key not in events:
                logger.warning("gate_key_missing", question=q.key, gate=gate.key)
                events[q.key].set()
                return
            await events[gate.key].wait()
            if not gate.check(results.get(gate.key)):
                events[q.key].set()  # unblock any dependents even if skipped
                return

        # Dispatch to the appropriate ask_* function
        prompt = q.prompt.format_map(context)
        try:
            if q.qtype == "float":
                results[q.key] = await ask_float(prompt, float(q.lo), float(q.hi), float(q.default))
            elif q.qtype == "bool":
                results[q.key] = await ask_bool(prompt)
            elif q.qtype == "text":
                results[q.key] = await ask_text(
                    prompt, max_tokens=q.max_tokens, default=str(q.default)
                )
            else:
                results[q.key] = await ask_int(prompt, int(q.lo), int(q.hi), int(q.default))
        except Exception:
            logger.warning("question_failed", key=q.key, prompt=prompt[:80])

        events[q.key].set()

    await asyncio.gather(*[_run(q) for q in questions], return_exceptions=True)
    return results
