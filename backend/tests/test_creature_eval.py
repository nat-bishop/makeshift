"""Tests for creature behavior evaluation pipeline (engine/creature.py).

Covers _collect_results and evaluate_creature_behaviors — the staged
LLM evaluation pipeline. compute_utility is tested in test_engine.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.cache.scene import BehaviorCache
from app.engine.creature import _collect_results, evaluate_creature_behaviors
from app.models.blueprint import GameObjectBlueprint, PhysicsProperties


def _make_blueprint(**overrides: object) -> GameObjectBlueprint:
    defaults: dict[str, object] = {
        "id": "test-id",
        "name": "zombie",
        "description": "a zombie",
        "visual_description": "a shambling zombie",
        "physics": PhysicsProperties(mass_kg=70.0, height_cm=170, surface=1, bounce=5, gravity=50),
        "durability": 2,
        "affordance": 3,
        "autonomous": True,
    }
    defaults.update(overrides)
    return GameObjectBlueprint(**defaults)


# ---------------------------------------------------------------------------
# _collect_results
# ---------------------------------------------------------------------------


class TestCollectResults:
    def test_zips_results_with_names(self) -> None:
        raw: list[dict[str, int | float | bool | str] | BaseException] = [
            {"movement": 0, "priority": 2},
            {"movement": 1, "priority": 3},
        ]
        result = _collect_results(raw, ["sword", "shield"], "test_event", "zombie")
        assert result == {
            "sword": {"movement": 0, "priority": 2},
            "shield": {"movement": 1, "priority": 3},
        }

    def test_skips_exception_entries(self) -> None:
        raw: list[dict[str, int | float | bool | str] | BaseException] = [
            RuntimeError("LLM failed"),
            {"movement": 0, "priority": 1},
        ]
        result = _collect_results(raw, ["sword", "shield"], "test_event", "zombie")
        assert "sword" not in result
        assert "shield" in result

    def test_logs_warning_for_exceptions(self) -> None:
        raw: list[dict[str, int | float | bool | str] | BaseException] = [
            RuntimeError("boom"),
        ]
        with patch("app.engine.creature.logger") as mock_logger:
            _collect_results(raw, ["sword"], "creature_stage1_failed", "zombie")
            mock_logger.warning.assert_called_once_with(
                "creature_stage1_failed",
                creature="zombie",
                target="sword",
                error="boom",
            )


# ---------------------------------------------------------------------------
# evaluate_creature_behaviors
# ---------------------------------------------------------------------------


def _make_side_effect(stage_responses: dict[str, list[dict[str, object]]]):
    """Build a side_effect callable that dispatches based on question keys.

    stage_responses maps a question key (present in the questions list)
    to a list of return values consumed in order.
    """
    counters: dict[str, int] = dict.fromkeys(stage_responses, 0)

    async def _side_effect(questions, context):
        # Identify stage by first question key
        key = questions[0].key
        for stage_key, responses in stage_responses.items():
            if key == stage_key:
                idx = counters[stage_key]
                counters[stage_key] += 1
                return responses[idx]
        return {}

    return _side_effect


class TestEvaluateCreatureBehaviors:
    async def test_non_autonomous_returns_empty(self) -> None:
        creature = _make_blueprint(autonomous=False)
        target = _make_blueprint(id="t1", name="sword")
        result = await evaluate_creature_behaviors(
            creature, [target], ["zombie", "sword"], BehaviorCache()
        )
        assert result == {}

    async def test_empty_targets_returns_empty(self) -> None:
        creature = _make_blueprint()
        result = await evaluate_creature_behaviors(creature, [], ["zombie"], BehaviorCache())
        assert result == {}

    async def test_full_pipeline_approach_damage_amount(self) -> None:
        """Stage 1 approach -> Stage 2 damage -> Stage 3 amount param."""
        creature = _make_blueprint()
        target = _make_blueprint(id="t1", name="villager")

        side_effect = _make_side_effect(
            {
                "movement": [{"movement": 0, "priority": 3}],
                "action": [{"action": 1}],  # damage
                "amount": [{"amount": 75}],
            }
        )
        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=side_effect)):
            scene = BehaviorCache()
            result = await evaluate_creature_behaviors(
                creature, [target], ["zombie", "villager"], scene
            )

        assert "villager" in result
        b = result["villager"]
        assert b.movement == 0
        assert b.priority == 3
        assert b.action == 1
        assert b.amount == 75
        assert b.state_id == 0

        # Verify cached in scene
        cached = scene.get_behavior("zombie", "villager")
        assert cached is not None
        assert cached.amount == 75

    async def test_full_pipeline_approach_add_state(self) -> None:
        """Stage 1 approach -> Stage 2 add_state -> Stage 3 state_id param."""
        creature = _make_blueprint()
        target = _make_blueprint(id="t1", name="villager")

        side_effect = _make_side_effect(
            {
                "movement": [{"movement": 0, "priority": 2}],
                "action": [{"action": 3}],  # add state
                "state_id": [{"state_id": 2}],
            }
        )
        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=side_effect)):
            result = await evaluate_creature_behaviors(
                creature, [target], ["zombie", "villager"], BehaviorCache()
            )

        b = result["villager"]
        assert b.action == 3
        assert b.state_id == 2
        assert b.amount == 0

    async def test_all_targets_ignored_skips_stage2(self) -> None:
        """All targets get movement=2 (ignore) -> stage 2 never called."""
        creature = _make_blueprint()
        t1 = _make_blueprint(id="t1", name="rock", autonomous=False)
        t2 = _make_blueprint(id="t2", name="tree", autonomous=False)

        call_count = 0

        async def _side_effect(questions, context):
            nonlocal call_count
            call_count += 1
            # All stage 1 calls return ignore
            return {"movement": 2, "priority": 0}

        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=_side_effect)):
            result = await evaluate_creature_behaviors(
                creature, [t1, t2], ["zombie", "rock", "tree"], BehaviorCache()
            )

        # 2 calls for stage 1, 0 for stage 2
        assert call_count == 2
        assert result["rock"].movement == 2
        assert result["rock"].action == 0
        assert result["tree"].movement == 2
        assert result["tree"].action == 0

    async def test_stage1_exception_gives_defaults(self) -> None:
        """Exception in stage 1 for one target -> defaults (movement=2, priority=0)."""
        creature = _make_blueprint()
        t1 = _make_blueprint(id="t1", name="sword", autonomous=False)
        t2 = _make_blueprint(id="t2", name="shield", autonomous=False)

        async def _side_effect(questions, context):
            if questions[0].key == "movement":
                if context.get("target") == "sword":
                    raise RuntimeError("LLM timeout")
                return {"movement": 0, "priority": 2}
            # stage 2 for shield (approach)
            return {"action": 0}

        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=_side_effect)):
            result = await evaluate_creature_behaviors(
                creature, [t1, t2], ["zombie", "sword", "shield"], BehaviorCache()
            )

        # sword gets defaults (ignore)
        assert result["sword"].movement == 2
        assert result["sword"].priority == 0
        assert result["sword"].action == 0

        # shield processed normally
        assert result["shield"].movement == 0
        assert result["shield"].priority == 2

    async def test_results_stored_in_behavior_cache(self) -> None:
        """All behavior results are persisted via scene.put_behavior()."""
        creature = _make_blueprint()
        t1 = _make_blueprint(id="t1", name="cat")
        t2 = _make_blueprint(id="t2", name="dog")

        async def _side_effect(questions, context):
            if questions[0].key == "movement":
                return {"movement": 1, "priority": 1}  # flee, no stage 2
            return {}

        scene = BehaviorCache()
        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=_side_effect)):
            await evaluate_creature_behaviors(creature, [t1, t2], ["zombie", "cat", "dog"], scene)

        # Both should be in behavior cache
        assert scene.get_behavior("zombie", "cat") is not None
        assert scene.get_behavior("zombie", "dog") is not None
        assert scene.get_behavior("zombie", "cat").movement == 1

    async def test_ignore_skips_stage2(self) -> None:
        """Ignore (movement=2) does not proceed to stage 2."""
        creature = _make_blueprint()
        target = _make_blueprint(id="t1", name="campfire", autonomous=False)

        call_count = 0

        async def _side_effect(questions, context):
            nonlocal call_count
            call_count += 1
            return {"movement": 2, "priority": 2}

        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=_side_effect)):
            result = await evaluate_creature_behaviors(
                creature, [target], ["zombie", "campfire"], BehaviorCache()
            )

        assert call_count == 1  # only stage 1
        assert result["campfire"].movement == 2
        assert result["campfire"].action == 0

    async def test_flee_skips_stage2(self) -> None:
        """Flee (movement=1) does not proceed to stage 2."""
        creature = _make_blueprint()
        target = _make_blueprint(id="t1", name="fire")

        call_count = 0

        async def _side_effect(questions, context):
            nonlocal call_count
            call_count += 1
            return {"movement": 1, "priority": 3}

        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=_side_effect)):
            result = await evaluate_creature_behaviors(
                creature, [target], ["zombie", "fire"], BehaviorCache()
            )

        assert call_count == 1  # only stage 1
        assert result["fire"].movement == 1
        assert result["fire"].action == 0

    async def test_action_not_needing_params_skips_stage3(self) -> None:
        """Actions 0, 5 skip stage 3 (no params needed)."""
        creature = _make_blueprint()
        target = _make_blueprint(id="t1", name="barrel")

        side_effect = _make_side_effect(
            {
                "movement": [{"movement": 0, "priority": 2}],
                "action": [{"action": 5}],  # consume — no params
            }
        )
        mock = AsyncMock(side_effect=side_effect)
        with patch("app.engine.creature.run_questions", new=mock):
            result = await evaluate_creature_behaviors(
                creature, [target], ["zombie", "barrel"], BehaviorCache()
            )

        assert mock.call_count == 2  # stage 1 + stage 2, no stage 3
        assert result["barrel"].action == 5
        assert result["barrel"].amount == 0
        assert result["barrel"].state_id == 0

    async def test_multiple_targets_mixed_responses(self) -> None:
        """Multiple targets with different stage progression paths."""
        creature = _make_blueprint()
        t_approach = _make_blueprint(id="t1", name="villager", autonomous=False)
        t_ignore = _make_blueprint(id="t2", name="rock", autonomous=False)
        t_flee = _make_blueprint(id="t3", name="torch", autonomous=False)

        async def _side_effect(questions, context):
            key = questions[0].key
            target = context.get("target", "")
            if key == "movement":
                if target == "villager":
                    return {"movement": 0, "priority": 3}
                if target == "rock":
                    return {"movement": 2, "priority": 0}
                if target == "torch":
                    return {"movement": 1, "priority": 2}
                return {"movement": 2, "priority": 0}
            if key == "action":
                return {"action": 2}  # heal
            if key == "amount":
                return {"amount": 50}
            return {}

        with patch("app.engine.creature.run_questions", new=AsyncMock(side_effect=_side_effect)):
            scene = BehaviorCache()
            result = await evaluate_creature_behaviors(
                creature,
                [t_approach, t_ignore, t_flee],
                ["zombie", "villager", "rock", "torch"],
                scene,
            )

        # villager: approach -> heal -> amount 50
        assert result["villager"].movement == 0
        assert result["villager"].action == 2
        assert result["villager"].amount == 50

        # rock: ignore, no action
        assert result["rock"].movement == 2
        assert result["rock"].action == 0

        # torch: flee, no action
        assert result["torch"].movement == 1
        assert result["torch"].action == 0
