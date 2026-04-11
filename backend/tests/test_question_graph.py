"""Tests for the question graph executor (run_questions)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from app.creator.question_graph import Gate, Question, run_questions

# Patch targets — the functions are imported into question_graph's namespace.
_PATCH_INT = "app.creator.question_graph.ask_int"
_PATCH_FLOAT = "app.creator.question_graph.ask_float"
_PATCH_BOOL = "app.creator.question_graph.ask_bool"
_PATCH_TEXT = "app.creator.question_graph.ask_text"


class TestUngatedQuestions:
    async def test_single_int_question(self):
        q = Question(key="mass", prompt="How heavy is {name}?", qtype="int", lo=1, hi=100)
        with patch(_PATCH_INT, new_callable=AsyncMock, return_value=42) as mock:
            result = await run_questions([q], {"name": "rock"})
        assert result == {"mass": 42}
        mock.assert_awaited_once_with("How heavy is rock?", 1, 100, 50, instructions="")

    async def test_multiple_ungated_fire_immediately(self):
        qs = [
            Question(key="a", prompt="A {x}", qtype="int"),
            Question(key="b", prompt="B {x}", qtype="float"),
            Question(key="c", prompt="C {x}", qtype="bool"),
        ]
        with (
            patch(_PATCH_INT, new_callable=AsyncMock, return_value=10),
            patch(_PATCH_FLOAT, new_callable=AsyncMock, return_value=2.5),
            patch(_PATCH_BOOL, new_callable=AsyncMock, return_value=False),
        ):
            result = await run_questions(qs, {"x": "thing"})
        assert result == {"a": 10, "b": 2.5, "c": False}


class TestQtypeDispatch:
    async def test_int_dispatch(self):
        q = Question(key="k", prompt="P", qtype="int", lo=0, hi=10, default=5)
        with patch(_PATCH_INT, new_callable=AsyncMock, return_value=7) as mock:
            result = await run_questions([q], {})
        assert result["k"] == 7
        mock.assert_awaited_once_with("P", 0, 10, 5, instructions="")

    async def test_float_dispatch(self):
        q = Question(key="k", prompt="P", qtype="float", lo=0.0, hi=10.0, default=5.0)
        with patch(_PATCH_FLOAT, new_callable=AsyncMock, return_value=3.0) as mock:
            result = await run_questions([q], {})
        assert result["k"] == 3.0
        mock.assert_awaited_once_with("P", 0.0, 10.0, 5.0, instructions="")

    async def test_bool_dispatch(self):
        q = Question(key="k", prompt="P", qtype="bool")
        with patch(_PATCH_BOOL, new_callable=AsyncMock, return_value=True) as mock:
            result = await run_questions([q], {})
        assert result["k"] is True
        mock.assert_awaited_once_with("P")

    async def test_text_dispatch(self):
        q = Question(key="k", prompt="P", qtype="text", max_tokens=20, default="fallback")
        with patch(_PATCH_TEXT, new_callable=AsyncMock, return_value="answer") as mock:
            result = await run_questions([q], {})
        assert result["k"] == "answer"
        mock.assert_awaited_once_with("P", max_tokens=20, default="fallback", instructions="")


class TestFormatMap:
    async def test_prompt_substitution(self):
        q = Question(key="k", prompt="{name} weighs how much in {unit}?", qtype="int")
        with patch(_PATCH_INT, new_callable=AsyncMock, return_value=5) as mock:
            await run_questions([q], {"name": "anvil", "unit": "kg"})
        mock.assert_awaited_once_with("anvil weighs how much in kg?", 0, 100, 50, instructions="")


class TestGatePass:
    async def test_dependent_fires_when_gate_passes(self):
        gate = Gate(key="durability", check=lambda v: v is not None and v < 6)
        qs = [
            Question(key="durability", prompt="D", qtype="int", lo=0, hi=6, default=3),
            Question(
                key="destruction",
                prompt="What happens?",
                qtype="text",
                gates=(gate,),
            ),
        ]
        with (
            patch(_PATCH_INT, new_callable=AsyncMock, return_value=4),
            patch(_PATCH_TEXT, new_callable=AsyncMock, return_value="it breaks") as txt,
        ):
            result = await run_questions(qs, {})
        assert result["durability"] == 4
        assert result["destruction"] == "it breaks"
        txt.assert_awaited_once()


class TestGateFail:
    async def test_skipped_when_gate_fails(self):
        gate = Gate(key="durability", check=lambda v: v is not None and v < 6)
        qs = [
            Question(key="durability", prompt="D", qtype="int", lo=0, hi=6, default=3),
            Question(
                key="destruction",
                prompt="What happens?",
                qtype="text",
                gates=(gate,),
            ),
        ]
        with (
            patch(_PATCH_INT, new_callable=AsyncMock, return_value=6),
            patch(_PATCH_TEXT, new_callable=AsyncMock) as txt,
        ):
            result = await run_questions(qs, {})
        assert result == {"durability": 6}  # destruction skipped
        txt.assert_not_awaited()

    async def test_skipped_question_event_still_set(self):
        """A question gated on a failed check should still unblock its dependents."""
        gate_ab = Gate(key="a", check=lambda v: False)  # always fails
        gate_bc = Gate(key="b", check=lambda v: True)  # always passes
        qs = [
            Question(key="a", prompt="A", qtype="int"),
            Question(key="b", prompt="B", qtype="int", gates=(gate_ab,)),
            Question(key="c", prompt="C", qtype="int", gates=(gate_bc,)),
        ]
        with patch(_PATCH_INT, new_callable=AsyncMock, return_value=1):
            # Must complete without deadlock within a reasonable timeout.
            result = await asyncio.wait_for(run_questions(qs, {}), timeout=2.0)
        # b skipped (gate_ab fails), c skipped (gate_bc passes but b has no result,
        # however gate_bc check is `lambda v: True` so it passes even on None)
        assert "a" in result
        assert "b" not in result
        # c depends on b's event (which was set even though b was skipped),
        # and gate_bc passes, so c fires
        assert "c" in result


class TestMissingGateKey:
    async def test_missing_gate_key_skips_without_deadlock(self):
        gate = Gate(key="nonexistent", check=lambda v: True)
        qs = [
            Question(key="q", prompt="Q", qtype="int", gates=(gate,)),
        ]
        with patch(_PATCH_INT, new_callable=AsyncMock, return_value=1):
            result = await asyncio.wait_for(run_questions(qs, {}), timeout=2.0)
        assert "q" not in result

    async def test_missing_gate_unblocks_dependents(self):
        """Question with missing gate is skipped; its dependents should still run."""
        gate_bad = Gate(key="nonexistent", check=lambda v: True)
        gate_on_b = Gate(key="b", check=lambda v: True)
        qs = [
            Question(key="b", prompt="B", qtype="int", gates=(gate_bad,)),
            Question(key="c", prompt="C", qtype="int", gates=(gate_on_b,)),
        ]
        with patch(_PATCH_INT, new_callable=AsyncMock, return_value=99):
            result = await asyncio.wait_for(run_questions(qs, {}), timeout=2.0)
        # b skipped because gate key missing; c depends on b but gate_on_b passes (True)
        assert "b" not in result
        assert "c" in result


class TestExceptionHandling:
    async def test_exception_result_missing_but_event_set(self):
        qs = [
            Question(key="broken", prompt="P", qtype="int"),
            Question(
                key="dependent",
                prompt="D",
                qtype="int",
                gates=(Gate(key="broken", check=lambda v: True),),
            ),
        ]
        with patch(
            _PATCH_INT,
            new_callable=AsyncMock,
            side_effect=[RuntimeError("LLM down"), 99],
        ):
            result = await asyncio.wait_for(run_questions(qs, {}), timeout=2.0)
        # broken raised an exception — result missing
        assert "broken" not in result
        # dependent's gate check receives None (broken not in results), but
        # `lambda v: True` passes, so dependent fires with the second call (99)
        assert result["dependent"] == 99

    async def test_exception_does_not_deadlock(self):
        qs = [Question(key="k", prompt="P", qtype="int")]
        with patch(_PATCH_INT, new_callable=AsyncMock, side_effect=RuntimeError("boom")):
            result = await asyncio.wait_for(run_questions(qs, {}), timeout=2.0)
        assert "k" not in result


class TestChainedGates:
    async def test_chain_of_three(self):
        """A -> B -> C: all gates pass, all results present."""
        qs = [
            Question(key="a", prompt="A", qtype="int"),
            Question(
                key="b",
                prompt="B",
                qtype="int",
                gates=(Gate(key="a", check=lambda v: v is not None),),
            ),
            Question(
                key="c",
                prompt="C",
                qtype="int",
                gates=(Gate(key="b", check=lambda v: v is not None),),
            ),
        ]
        call_count = 0

        async def counting_int(*_args, **_kwargs) -> int:
            nonlocal call_count
            call_count += 1
            return call_count * 10

        with patch(_PATCH_INT, side_effect=counting_int):
            result = await asyncio.wait_for(run_questions(qs, {}), timeout=2.0)
        assert len(result) == 3
        assert "a" in result and "b" in result and "c" in result

    async def test_chain_breaks_midway(self):
        """A -> B -> C: B's gate fails, so C is also skipped."""
        qs = [
            Question(key="a", prompt="A", qtype="int"),
            Question(
                key="b",
                prompt="B",
                qtype="int",
                gates=(Gate(key="a", check=lambda v: False),),  # always fails
            ),
            Question(
                key="c",
                prompt="C",
                qtype="int",
                gates=(Gate(key="b", check=lambda v: v is not None),),
            ),
        ]
        with patch(_PATCH_INT, new_callable=AsyncMock, return_value=1):
            result = await asyncio.wait_for(run_questions(qs, {}), timeout=2.0)
        assert "a" in result
        assert "b" not in result
        # c's gate checks b's result which is None (missing) -> fails -> c skipped
        assert "c" not in result
