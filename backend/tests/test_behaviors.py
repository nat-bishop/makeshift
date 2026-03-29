"""Tests for the behavior system: enums, model validation, cost calculation, budget enforcement."""

import pytest
from app.models.behaviors import (
    BEHAVIOR_ACTION_COSTS,
    INTENSITY_COST_MODIFIER,
    SPAWN_EXPLODE_FLOOR,
    Behavior,
    BehaviorAction,
    BehaviorRange,
    BehaviorSpec,
    BehaviorTarget,
    BehaviorTrigger,
    Intensity,
    Interval,
    Power,
    Speed,
    compute_behavior_cost,
    compute_spec_cost,
    expand_behavior_spec,
)
from app.models.blueprint import (
    CreatorOutput,
    CreatorOutputSpec,
    GameObjectBlueprint,
    VisualDescriptor,
)
from app.models.tags import Tag
from pydantic import ValidationError
from pydantic_ai import ModelRetry


def _make_visual() -> VisualDescriptor:
    return VisualDescriptor(
        visual_description="a gray stone cube",
        size_category="medium",
    )


def _make_behavior(**kwargs: object) -> Behavior:
    defaults: dict[str, object] = {
        "trigger": BehaviorTrigger.ALWAYS,
        "action": BehaviorAction.PATROL,
        "target": BehaviorTarget.SELF,
    }
    defaults.update(kwargs)
    return Behavior(**defaults)  # type: ignore[arg-type]


def _make_spec(**kwargs: object) -> BehaviorSpec:
    defaults: dict[str, object] = {
        "trigger": BehaviorTrigger.ALWAYS,
        "action": BehaviorAction.PATROL,
    }
    defaults.update(kwargs)
    return BehaviorSpec(**defaults)  # type: ignore[arg-type]


class TestComputeBehaviorCost:
    def test_basic_action_costs(self) -> None:
        for action, expected_base in BEHAVIOR_ACTION_COSTS.items():
            extras: dict = {}
            if action in {BehaviorAction.ADD_TAGS, BehaviorAction.REMOVE_TAGS}:
                extras["tags_to_apply"] = [Tag.HOT]
            if action in {BehaviorAction.MOVE_TOWARD, BehaviorAction.MOVE_AWAY}:
                extras["target"] = BehaviorTarget.NEAREST_PLAYER
            b = _make_behavior(action=action, intensity=Intensity.MEDIUM, **extras)
            assert compute_behavior_cost(b) == max(1, expected_base)

    def test_intensity_modifiers(self) -> None:
        for intensity, modifier in INTENSITY_COST_MODIFIER.items():
            b = _make_behavior(action=BehaviorAction.DEAL_DAMAGE, intensity=intensity)
            expected = max(1, 2 + modifier)
            assert compute_behavior_cost(b) == expected

    def test_spawn_projectile_floor(self) -> None:
        b = _make_behavior(action=BehaviorAction.SPAWN_PROJECTILE, intensity=Intensity.MINIMAL)
        cost = compute_behavior_cost(b)
        assert cost == SPAWN_EXPLODE_FLOOR  # max(2, 3 + (-1)) = max(2, 2) = 2

    def test_explode_floor(self) -> None:
        b = _make_behavior(action=BehaviorAction.EXPLODE, intensity=Intensity.MINIMAL)
        cost = compute_behavior_cost(b)
        assert cost == SPAWN_EXPLODE_FLOOR

    def test_self_destruct_minimal_floors_at_1(self) -> None:
        b = _make_behavior(action=BehaviorAction.SELF_DESTRUCT, intensity=Intensity.MINIMAL)
        assert compute_behavior_cost(b) == 1  # max(1, 1 + (-1)) = max(1, 0) = 1

    def test_extreme_spawn_projectile(self) -> None:
        b = _make_behavior(action=BehaviorAction.SPAWN_PROJECTILE, intensity=Intensity.EXTREME)
        assert compute_behavior_cost(b) == 5  # max(2, 3 + 2) = 5

    def test_extreme_explode(self) -> None:
        b = _make_behavior(action=BehaviorAction.EXPLODE, intensity=Intensity.EXTREME)
        assert compute_behavior_cost(b) == 5


class TestBehaviorValidation:
    def test_valid_basic_behavior(self) -> None:
        b = _make_behavior()
        assert b.trigger == BehaviorTrigger.ALWAYS
        assert b.action == BehaviorAction.PATROL

    def test_defaults(self) -> None:
        b = _make_behavior()
        assert b.intensity == Intensity.MEDIUM
        assert b.range == BehaviorRange.MEDIUM
        assert b.speed == Speed.MEDIUM
        assert b.interval == Interval.MEDIUM
        assert b.tags_to_apply is None
        assert b.trigger_tag is None

    def test_on_tag_added_requires_trigger_tag(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(trigger=BehaviorTrigger.ON_TAG_ADDED)

    def test_on_tag_added_with_trigger_tag_valid(self) -> None:
        b = _make_behavior(
            trigger=BehaviorTrigger.ON_TAG_ADDED,
            trigger_tag=Tag.HOT,
            action=BehaviorAction.EXPLODE,
        )
        assert b.trigger_tag == Tag.HOT

    def test_non_tag_added_trigger_rejects_trigger_tag(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(trigger=BehaviorTrigger.ALWAYS, trigger_tag=Tag.HOT)

    def test_contact_body_requires_compatible_trigger(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(
                trigger=BehaviorTrigger.ALWAYS, target=BehaviorTarget.CONTACT_BODY
            )

    def test_contact_body_with_on_contact_valid(self) -> None:
        b = _make_behavior(
            trigger=BehaviorTrigger.ON_CONTACT,
            target=BehaviorTarget.CONTACT_BODY,
            action=BehaviorAction.DEAL_DAMAGE,
        )
        assert b.target == BehaviorTarget.CONTACT_BODY

    def test_add_tags_requires_tags_to_apply(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(action=BehaviorAction.ADD_TAGS)

    def test_add_tags_with_tags_to_apply_valid(self) -> None:
        b = _make_behavior(
            action=BehaviorAction.ADD_TAGS, tags_to_apply=[Tag.HOT, Tag.HEAT_SOURCE]
        )
        assert b.tags_to_apply == [Tag.HOT, Tag.HEAT_SOURCE]


class TestActionTargetValidation:
    def test_self_destruct_rejects_non_self_target(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(
                action=BehaviorAction.SELF_DESTRUCT, target=BehaviorTarget.NEAREST_PLAYER
            )

    def test_self_destruct_with_self_target_valid(self) -> None:
        b = _make_behavior(action=BehaviorAction.SELF_DESTRUCT, target=BehaviorTarget.SELF)
        assert b.action == BehaviorAction.SELF_DESTRUCT

    def test_explode_rejects_non_self_target(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(
                trigger=BehaviorTrigger.ON_TAG_ADDED,
                trigger_tag=Tag.HOT,
                action=BehaviorAction.EXPLODE,
                target=BehaviorTarget.NEAREST_OBJECT,
            )

    def test_move_toward_rejects_self_target(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(
                action=BehaviorAction.MOVE_TOWARD, target=BehaviorTarget.SELF
            )

    def test_move_toward_with_nearest_player_valid(self) -> None:
        b = _make_behavior(
            action=BehaviorAction.MOVE_TOWARD, target=BehaviorTarget.NEAREST_PLAYER
        )
        assert b.target == BehaviorTarget.NEAREST_PLAYER

    def test_patrol_with_self_target_valid(self) -> None:
        b = _make_behavior(action=BehaviorAction.PATROL, target=BehaviorTarget.SELF)
        assert b.action == BehaviorAction.PATROL


class TestActionTriggerValidation:
    def test_on_destroy_rejects_movement(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(
                trigger=BehaviorTrigger.ON_DESTROY,
                action=BehaviorAction.MOVE_TOWARD,
                target=BehaviorTarget.NEAREST_PLAYER,
            )

    def test_on_destroy_allows_explode(self) -> None:
        b = _make_behavior(
            trigger=BehaviorTrigger.ON_DESTROY,
            action=BehaviorAction.EXPLODE,
        )
        assert b.action == BehaviorAction.EXPLODE


# ---------------------------------------------------------------------------
# BehaviorSpec tests
# ---------------------------------------------------------------------------


class TestBehaviorSpec:
    def test_basic_spec(self) -> None:
        s = _make_spec()
        assert s.trigger == BehaviorTrigger.ALWAYS
        assert s.action == BehaviorAction.PATROL
        assert s.target == BehaviorTarget.NEAREST_OBJECT
        assert s.power == "medium"

    def test_trigger_tag_required_for_on_tag_added(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(trigger=BehaviorTrigger.ON_TAG_ADDED)

    def test_trigger_tag_rejected_for_other_triggers(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(trigger=BehaviorTrigger.ALWAYS, trigger_tag=Tag.HOT)

    def test_tags_to_apply_required_for_add_tags(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(action=BehaviorAction.ADD_TAGS)

    def test_tags_to_apply_required_for_remove_tags(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(action=BehaviorAction.REMOVE_TAGS)

    def test_valid_add_tags(self) -> None:
        s = _make_spec(action=BehaviorAction.ADD_TAGS, tags_to_apply=[Tag.HOT])
        assert s.tags_to_apply == [Tag.HOT]

    def test_valid_on_tag_added(self) -> None:
        s = _make_spec(
            trigger=BehaviorTrigger.ON_TAG_ADDED,
            trigger_tag=Tag.HOT,
            action=BehaviorAction.EXPLODE,
            target=BehaviorTarget.SELF,
        )
        assert s.trigger_tag == Tag.HOT

    def test_explode_rejects_non_self_target(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(
                trigger=BehaviorTrigger.ON_TAG_ADDED,
                trigger_tag=Tag.HOT,
                action=BehaviorAction.EXPLODE,
                target=BehaviorTarget.NEAREST_OBJECT,
            )

    def test_self_destruct_rejects_non_self_target(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(
                action=BehaviorAction.SELF_DESTRUCT,
                target=BehaviorTarget.NEAREST_PLAYER,
            )

    def test_move_toward_rejects_self_target(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(
                action=BehaviorAction.MOVE_TOWARD,
                target=BehaviorTarget.SELF,
            )

    def test_contact_body_rejects_wrong_trigger(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(
                trigger=BehaviorTrigger.ALWAYS,
                action=BehaviorAction.DEAL_DAMAGE,
                target=BehaviorTarget.CONTACT_BODY,
            )

    def test_on_destroy_rejects_movement(self) -> None:
        with pytest.raises(ModelRetry):
            _make_spec(
                trigger=BehaviorTrigger.ON_DESTROY,
                action=BehaviorAction.MOVE_TOWARD,
                target=BehaviorTarget.NEAREST_PLAYER,
            )


class TestComputeSpecCost:
    def test_low_medium_same_cost(self) -> None:
        s_low = _make_spec(action=BehaviorAction.DEAL_DAMAGE, power="low")
        s_med = _make_spec(action=BehaviorAction.DEAL_DAMAGE, power="medium")
        assert compute_spec_cost(s_low) == compute_spec_cost(s_med) == 2

    def test_high_costs_one_more(self) -> None:
        s_med = _make_spec(action=BehaviorAction.DEAL_DAMAGE, power="medium")
        s_high = _make_spec(action=BehaviorAction.DEAL_DAMAGE, power="high")
        assert compute_spec_cost(s_high) == compute_spec_cost(s_med) + 1

    def test_spawn_projectile_floor(self) -> None:
        s = _make_spec(action=BehaviorAction.SPAWN_PROJECTILE, power="low")
        assert compute_spec_cost(s) == 3  # base 3, modifier 0, floor 2 → 3

    def test_spawn_projectile_high(self) -> None:
        s = _make_spec(action=BehaviorAction.SPAWN_PROJECTILE, power="high")
        assert compute_spec_cost(s) == 4  # base 3 + 1

    def test_self_destruct_always_1(self) -> None:
        for power in ("low", "medium", "high"):
            s = _make_spec(
                action=BehaviorAction.SELF_DESTRUCT,
                target=BehaviorTarget.SELF,
                power=power,
            )
            # base 1, high adds 1 → max(1, 2) = 2 for high; otherwise 1
            if power == "high":
                assert compute_spec_cost(s) == 2
            else:
                assert compute_spec_cost(s) == 1


class TestExpandBehaviorSpec:
    def test_movement_maps_speed(self) -> None:
        cases = [("low", Speed.SLOW), ("medium", Speed.MEDIUM), ("high", Speed.FAST)]
        for power, expected in cases:
            s = _make_spec(
                action=BehaviorAction.MOVE_TOWARD,
                target=BehaviorTarget.NEAREST_PLAYER,
                power=power,
            )
            b = expand_behavior_spec(s)
            assert b.speed == expected

    def test_damage_maps_intensity(self) -> None:
        for power, expected in [
            ("low", Intensity.LOW),
            ("medium", Intensity.MEDIUM),
            ("high", Intensity.HIGH),
        ]:
            s = _make_spec(action=BehaviorAction.DEAL_DAMAGE, power=power)
            b = expand_behavior_spec(s)
            assert b.intensity == expected

    def test_explode_maps_intensity_and_range(self) -> None:
        s = _make_spec(action=BehaviorAction.EXPLODE, target=BehaviorTarget.SELF, power="high")
        b = expand_behavior_spec(s)
        assert b.intensity == Intensity.HIGH
        assert b.range == BehaviorRange.FAR

    def test_interval_mapped(self) -> None:
        s = _make_spec(power="high")
        b = expand_behavior_spec(s)
        assert b.interval == Interval.FAST

    def test_tags_to_apply_preserved(self) -> None:
        s = _make_spec(
            action=BehaviorAction.ADD_TAGS, tags_to_apply=[Tag.HOT, Tag.HEAT_SOURCE]
        )
        b = expand_behavior_spec(s)
        assert b.tags_to_apply == [Tag.HOT, Tag.HEAT_SOURCE]

    def test_trigger_tag_preserved(self) -> None:
        s = _make_spec(
            trigger=BehaviorTrigger.ON_TAG_ADDED,
            trigger_tag=Tag.HOT,
            action=BehaviorAction.EXPLODE,
            target=BehaviorTarget.SELF,
        )
        b = expand_behavior_spec(s)
        assert b.trigger_tag == Tag.HOT


class TestCreatorOutputSpec:
    def test_no_behaviors_valid(self) -> None:
        out = CreatorOutputSpec(
            name="Rock", tags=[Tag.SOLID, Tag.RIGID], visual_descriptor=_make_visual()
        )
        assert out.behaviors == []

    def test_behavior_budget_exceeded_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutputSpec(
                name="Overpowered",
                tags=[Tag.SOLID, Tag.RIGID],
                behaviors=[
                    BehaviorSpec(
                        trigger=BehaviorTrigger.ALWAYS,
                        action=BehaviorAction.SPAWN_PROJECTILE,
                        power=Power.HIGH,
                    ),
                    BehaviorSpec(
                        trigger=BehaviorTrigger.ON_PROXIMITY,
                        action=BehaviorAction.SPAWN_PROJECTILE,
                        power=Power.HIGH,
                    ),
                    BehaviorSpec(
                        trigger=BehaviorTrigger.ON_TIMER,
                        action=BehaviorAction.EXPLODE,
                        power=Power.HIGH,
                    ),
                ],
                visual_descriptor=_make_visual(),
            )  # 4 + 4 + 4 = 12 > 8


class TestCreatorOutputBehaviors:
    def test_no_behaviors_valid(self) -> None:
        out = CreatorOutput(
            name="Rock", tags=[Tag.SOLID, Tag.RIGID], visual_descriptor=_make_visual()
        )
        assert out.behaviors == []

    def test_behaviors_within_budget_valid(self) -> None:
        out = CreatorOutput(
            name="Guard Dog",
            tags=[Tag.LIVING, Tag.SOLID, Tag.FLEXIBLE],
            behaviors=[
                Behavior(
                    trigger=BehaviorTrigger.ALWAYS,
                    action=BehaviorAction.MOVE_TOWARD,
                    target=BehaviorTarget.NEAREST_PLAYER,
                    speed=Speed.FAST,
                )
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 1

    def test_dragon_example_valid(self) -> None:
        out = CreatorOutput(
            name="Fire Dragon",
            tags=[Tag.LIVING, Tag.HEAT_SOURCE, Tag.HOT],
            behaviors=[
                Behavior(
                    trigger=BehaviorTrigger.ALWAYS,
                    action=BehaviorAction.MOVE_TOWARD,
                    target=BehaviorTarget.NEAREST_LIVING,
                    speed=Speed.MEDIUM,
                ),
                Behavior(
                    trigger=BehaviorTrigger.ON_PROXIMITY,
                    action=BehaviorAction.SPAWN_PROJECTILE,
                    target=BehaviorTarget.NEAREST_LIVING,
                    range=BehaviorRange.CLOSE,
                    intensity=Intensity.HIGH,
                    interval=Interval.SLOW,
                ),
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 2

    def test_reactive_bomb_example_valid(self) -> None:
        out = CreatorOutput(
            name="Reactive Bomb",
            tags=[Tag.EXPLOSIVE, Tag.SOLID, Tag.FLAMMABLE],
            behaviors=[
                Behavior(
                    trigger=BehaviorTrigger.ON_TAG_ADDED,
                    trigger_tag=Tag.HOT,
                    action=BehaviorAction.EXPLODE,
                    intensity=Intensity.EXTREME,
                    range=BehaviorRange.FAR,
                )
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 1


class TestGameObjectBlueprintBehaviors:
    def test_behavior_cost_computed(self) -> None:
        bp = GameObjectBlueprint(
            id="test",
            name="Dragon",
            description="fire dragon",
            tags=[Tag.LIVING, Tag.SOLID],
            behaviors=[
                Behavior(
                    trigger=BehaviorTrigger.ALWAYS,
                    action=BehaviorAction.MOVE_TOWARD,
                    target=BehaviorTarget.NEAREST_LIVING,
                ),
            ],
            visual_descriptor=_make_visual(),
        )
        assert bp.behavior_cost == 2

    def test_behavior_cost_zero_when_empty(self) -> None:
        bp = GameObjectBlueprint(
            id="test",
            name="Rock",
            description="a rock",
            tags=[Tag.SOLID, Tag.RIGID],
            visual_descriptor=_make_visual(),
        )
        assert bp.behavior_cost == 0

    def test_serialization_round_trip_with_behaviors(self) -> None:
        bp = GameObjectBlueprint(
            id="test",
            name="Bomb",
            description="a bomb",
            tags=[Tag.EXPLOSIVE, Tag.SOLID],
            behaviors=[
                Behavior(
                    trigger=BehaviorTrigger.ON_TIMER,
                    action=BehaviorAction.EXPLODE,
                    intensity=Intensity.EXTREME,
                    range=BehaviorRange.FAR,
                    interval=Interval.ONCE_MEDIUM,
                )
            ],
            visual_descriptor=_make_visual(),
        )
        data = bp.model_dump(mode="json")
        assert len(data["behaviors"]) == 1
        assert data["behaviors"][0]["trigger"] == "ON_TIMER"
        assert data["behavior_cost"] == 5
