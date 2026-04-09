"""Tests for pairwise interaction engine (screening, evaluation, spawn integration)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.cache.scene import PairwiseResult, SceneCache
from app.cache.store import CacheStore
from app.engine.pairwise import _obj_summary, evaluate_pair, screen_pairs, spawn_integration
from app.models.blueprint import GameObjectBlueprint, PhysicsProperties


def _make_blueprint(**overrides) -> GameObjectBlueprint:
    defaults = {
        "id": "test-id",
        "name": "sword",
        "description": "a sword",
        "visual_description": "a steel sword",
        "physics": PhysicsProperties(mass_kg=1.5, height_cm=120, surface=1, bounce=10, gravity=50),
        "durability": 2,
        "affordance": 0,
        "autonomous": False,
    }
    defaults.update(overrides)
    return GameObjectBlueprint(**defaults)


# ---- _obj_summary ----


class TestObjSummary:
    def test_basic_format(self):
        bp = _make_blueprint()
        result = _obj_summary(bp)
        assert "sword" in result
        assert "1.5kg" in result
        assert "120cm" in result
        assert "normal" in result  # durability=2 -> "normal"
        assert "normal-surface" in result  # surface=1

    def test_creature_label(self):
        bp = _make_blueprint(autonomous=True)
        result = _obj_summary(bp)
        assert "creature" in result

    def test_no_creature_label_when_not_autonomous(self):
        bp = _make_blueprint(autonomous=False)
        result = _obj_summary(bp)
        assert "creature" not in result

    def test_field_label(self):
        bp = _make_blueprint(has_field=True, field_range_cm=200)
        result = _obj_summary(bp)
        assert "field 200cm" in result

    def test_no_field_label_when_no_field(self):
        bp = _make_blueprint(has_field=False)
        result = _obj_summary(bp)
        assert "field" not in result

    def test_slippery_surface(self):
        bp = _make_blueprint(
            physics=PhysicsProperties(
                mass_kg=1.0, height_cm=50, surface=0, bounce=10, gravity=50
            ),
        )
        result = _obj_summary(bp)
        assert "slippery" in result

    def test_sticky_surface(self):
        bp = _make_blueprint(
            physics=PhysicsProperties(
                mass_kg=1.0, height_cm=50, surface=2, bounce=10, gravity=50
            ),
        )
        result = _obj_summary(bp)
        assert "sticky" in result

    def test_durability_names(self):
        bp = _make_blueprint(durability=0)
        assert "fragile" in _obj_summary(bp)

        bp = _make_blueprint(durability=6)
        assert "indestructible" in _obj_summary(bp)


# ---- screen_pairs ----


class TestScreenPairs:
    async def test_empty_scene_returns_empty(self):
        bp = _make_blueprint()
        result = await screen_pairs(bp, [])
        assert result == []

    @patch("app.engine.pairwise.ask_text", new_callable=AsyncMock)
    async def test_none_response_returns_empty(self, mock_ask):
        mock_ask.return_value = "none"
        bp = _make_blueprint()
        scene = [_make_blueprint(name="rock", id="r1")]
        result = await screen_pairs(bp, scene)
        assert result == []

    @patch("app.engine.pairwise.ask_text", new_callable=AsyncMock)
    async def test_parses_numbered_response(self, mock_ask):
        mock_ask.return_value = "1, 3"
        bp = _make_blueprint()
        scene = [
            _make_blueprint(name="rock", id="r1"),
            _make_blueprint(name="paper", id="r2"),
            _make_blueprint(name="scissors", id="r3"),
        ]
        result = await screen_pairs(bp, scene)
        assert result == ["rock", "scissors"]

    @patch("app.engine.pairwise.ask_text", new_callable=AsyncMock)
    async def test_fallback_all_on_invalid_response(self, mock_ask):
        mock_ask.return_value = "banana"
        bp = _make_blueprint()
        scene = [
            _make_blueprint(name="rock", id="r1"),
            _make_blueprint(name="paper", id="r2"),
        ]
        result = await screen_pairs(bp, scene)
        assert result == ["rock", "paper"]

    @patch("app.engine.pairwise.ask_text", new_callable=AsyncMock)
    async def test_out_of_range_indices_fallback(self, mock_ask):
        mock_ask.return_value = "99, 100"
        bp = _make_blueprint()
        scene = [_make_blueprint(name="rock", id="r1")]
        result = await screen_pairs(bp, scene)
        # No valid indices → returns all names
        assert result == ["rock"]

    @patch("app.engine.pairwise.ask_text", new_callable=AsyncMock)
    async def test_exception_returns_all(self, mock_ask):
        mock_ask.side_effect = RuntimeError("LLM down")
        bp = _make_blueprint()
        scene = [_make_blueprint(name="rock", id="r1")]
        result = await screen_pairs(bp, scene)
        assert result == ["rock"]


# ---- evaluate_pair ----


class TestEvaluatePair:
    async def test_scene_cache_hit(self):
        """Scene cache hit returns cached result without calling LLM."""
        bp_a = _make_blueprint(name="apple", id="a1")
        bp_b = _make_blueprint(name="banana", id="b1")
        scene = SceneCache()
        expected = PairwiseResult(10, 20, 0, 0, 0, False)
        scene.put_pairwise("apple", "banana", expected)

        cache = await CacheStore.open(":memory:")
        try:
            with patch("app.engine.pairwise.run_questions") as mock_rq:
                result = await evaluate_pair(bp_a, bp_b, cache, scene)
                mock_rq.assert_not_called()
            assert result.damage_a == 10
            assert result.damage_b == 20
        finally:
            await cache.close()

    async def test_persistent_cache_hit(self):
        """Persistent cache hit loads result and stores it in scene cache."""
        bp_a = _make_blueprint(name="apple", id="a1")
        bp_b = _make_blueprint(name="banana", id="b1")
        scene = SceneCache()
        cached_data = PairwiseResult(30, 40, 1, 2, 10, True).to_dict()

        cache = await CacheStore.open(":memory:")
        try:
            await cache.put_pairwise("apple", "banana", cached_data)

            with patch("app.engine.pairwise.run_questions") as mock_rq:
                result = await evaluate_pair(bp_a, bp_b, cache, scene)
                mock_rq.assert_not_called()

            assert result.damage_a == 30
            assert result.damage_b == 40
            assert result.continuous is True
            # Also stored in scene cache now
            assert scene.get_pairwise("apple", "banana") is not None
        finally:
            await cache.close()

    @patch("app.engine.pairwise.run_questions", new_callable=AsyncMock)
    async def test_llm_path_stores_in_both_caches(self, mock_rq):
        """LLM evaluation stores result in both scene and persistent caches."""
        mock_rq.return_value = {
            "damage_a": 25,
            "damage_b": 50,
            "state_change_a": 1,
            "state_change_b": 0,
            "force_b": 15,
            "continuous": False,
        }
        bp_a = _make_blueprint(name="apple", id="a1")
        bp_b = _make_blueprint(name="banana", id="b1")
        scene = SceneCache()

        cache = await CacheStore.open(":memory:")
        try:
            result = await evaluate_pair(bp_a, bp_b, cache, scene)

            assert result.damage_a == 25
            assert result.damage_b == 50
            assert result.force_b == 15

            # Stored in scene cache
            assert scene.get_pairwise("apple", "banana") is not None

            # Stored in persistent cache (commit=False, so flush manually)
            await cache.flush()
            db_entry = await cache.get_pairwise("apple", "banana")
            assert db_entry is not None
            assert db_entry["damage_a"] == 25
        finally:
            await cache.close()

    @patch("app.engine.pairwise.run_questions", new_callable=AsyncMock)
    async def test_names_sorted_lexicographically(self, mock_rq):
        """When bp_a.name > bp_b.name, they get swapped for consistent ordering."""
        mock_rq.return_value = {
            "damage_a": 10,
            "damage_b": 20,
            "state_change_a": 0,
            "state_change_b": 0,
            "force_b": 0,
            "continuous": False,
        }
        # "zebra" > "apple" lexicographically, so they should be swapped
        bp_a = _make_blueprint(name="zebra", id="z1")
        bp_b = _make_blueprint(name="apple", id="a1")
        scene = SceneCache()

        cache = await CacheStore.open(":memory:")
        try:
            await evaluate_pair(bp_a, bp_b, cache, scene)

            # run_questions context should have a="apple", b="zebra"
            call_ctx = mock_rq.call_args[0][1]
            assert call_ctx["a"] == "apple"
            assert call_ctx["b"] == "zebra"
        finally:
            await cache.close()

    @patch("app.engine.pairwise.run_questions", new_callable=AsyncMock)
    async def test_cache_disabled_skips_persistent(self, mock_rq):
        """When creation_cache_enabled=False, skips persistent cache read/write."""
        mock_rq.return_value = {
            "damage_a": 5,
            "damage_b": 5,
            "state_change_a": 0,
            "state_change_b": 0,
            "force_b": 0,
            "continuous": False,
        }
        bp_a = _make_blueprint(name="apple", id="a1")
        bp_b = _make_blueprint(name="banana", id="b1")
        scene = SceneCache()

        cache = await CacheStore.open(":memory:")
        try:
            with patch("app.engine.pairwise.settings") as mock_settings:
                mock_settings.creation_cache_enabled = False
                mock_settings.llm_model = "test-model"
                result = await evaluate_pair(bp_a, bp_b, cache, scene)

            assert result.damage_a == 5
            # Scene cache still used
            assert scene.get_pairwise("apple", "banana") is not None
            # Persistent cache NOT written
            await cache.flush()
            db_entry = await cache.get_pairwise("apple", "banana")
            assert db_entry is None
        finally:
            await cache.close()


# ---- spawn_integration ----


class TestSpawnIntegration:
    @patch("app.engine.pairwise.screen_pairs", new_callable=AsyncMock)
    async def test_empty_screening_returns_empty(self, mock_screen):
        """When screening returns no interesting pairs, no evals happen."""
        mock_screen.return_value = []
        bp = _make_blueprint()
        scene_objs = [_make_blueprint(name="rock", id="r1")]
        scene = SceneCache()

        cache = await CacheStore.open(":memory:")
        try:
            result = await spawn_integration(bp, scene_objs, cache, scene)
            assert result == {}
        finally:
            await cache.close()

    @patch("app.engine.pairwise.evaluate_pair", new_callable=AsyncMock)
    @patch("app.engine.pairwise.screen_pairs", new_callable=AsyncMock)
    async def test_orchestrates_screening_and_eval(self, mock_screen, mock_eval):
        """Orchestrates screening + parallel eval + cache flush."""
        mock_screen.return_value = ["rock"]
        mock_eval.return_value = PairwiseResult(10, 20, 0, 0, 0, False)

        bp = _make_blueprint()
        rock = _make_blueprint(name="rock", id="r1")
        scene = SceneCache()

        cache = await CacheStore.open(":memory:")
        try:
            result = await spawn_integration(bp, [rock], cache, scene)

            mock_screen.assert_called_once_with(bp, [rock])
            mock_eval.assert_called_once()
            assert "rock" in result
            assert result["rock"].damage_a == 10
        finally:
            await cache.close()

    @patch("app.engine.pairwise.evaluate_pair", new_callable=AsyncMock)
    @patch("app.engine.pairwise.screen_pairs", new_callable=AsyncMock)
    async def test_handles_eval_exception(self, mock_screen, mock_eval):
        """Failed evals are logged but don't crash; result dict excludes them."""
        mock_screen.return_value = ["rock", "paper"]
        mock_eval.side_effect = [
            PairwiseResult(10, 20, 0, 0, 0, False),
            RuntimeError("LLM failure"),
        ]

        bp = _make_blueprint()
        scene_objs = [
            _make_blueprint(name="rock", id="r1"),
            _make_blueprint(name="paper", id="r2"),
        ]
        scene = SceneCache()

        cache = await CacheStore.open(":memory:")
        try:
            result = await spawn_integration(bp, scene_objs, cache, scene)
            assert "rock" in result
            assert "paper" not in result
        finally:
            await cache.close()
