"""Tests for the behavior system: enums, model validation, cost calculation, budget enforcement."""

import pytest
from app.models.behaviors import (
    BEHAVIOR_ACTION_COSTS,
    INTENSITY_COST_MODIFIER,
    SPAWN_EXPLODE_FLOOR,
    Behavior,
    BehaviorAction,
    BehaviorCondition,
    BehaviorConditionType,
    BehaviorRange,
    BehaviorTarget,
    BehaviorTrigger,
    Intensity,
    Interval,
    Speed,
    compute_behavior_cost,
)
from app.models.blueprint import CreatorOutput, GameObjectBlueprint, VisualDescriptor
from app.models.tags import Tag
from pydantic import ValidationError
from pydantic_ai import ModelRetry


def _make_visual() -> VisualDescriptor:
    return VisualDescriptor(
        base_form="cube",
        material="stone",
        color_primary="#888888",
        color_primary_name="gray",
        color_secondary="#666666",
        color_secondary_name="dark gray",
        visual_effects=[],
        size_category="medium",
        bg_color="#808080",
    )


def _make_behavior(**kwargs) -> Behavior:  # type: ignore[no-untyped-def]
    defaults = {
        "trigger": BehaviorTrigger.ALWAYS,
        "action": BehaviorAction.PATROL,
        "target": BehaviorTarget.SELF,
    }
    defaults.update(kwargs)
    return Behavior(**defaults)


class TestComputeBehaviorCost:
    def test_basic_action_costs(self) -> None:
        for action, expected_base in BEHAVIOR_ACTION_COSTS.items():
            extras: dict = {}
            if action in {BehaviorAction.ADD_TAGS, BehaviorAction.REMOVE_TAGS}:
                extras["tags_to_apply"] = [Tag.HOT]
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
        assert b.condition is None
        assert b.message is None
        assert b.tags_to_apply is None
        assert b.trigger_tag is None

    def test_on_tag_added_requires_trigger_tag(self) -> None:
        with pytest.raises(ModelRetry):
            _make_behavior(trigger=BehaviorTrigger.ON_TAG_ADDED)

    def test_on_tag_added_with_trigger_tag_valid(self) -> None:
        b = _make_behavior(
            trigger=BehaviorTrigger.ON_TAG_ADDED,
            trigger_tag=Tag.HOT,
            action=BehaviorAction.EXPLODE,
        )
        assert b.trigger_tag == Tag.HOT

    def test_non_tag_added_trigger_rejects_trigger_tag(self) -> None:
        with pytest.raises(ModelRetry):
            _make_behavior(trigger=BehaviorTrigger.ALWAYS, trigger_tag=Tag.HOT)

    def test_contact_body_requires_compatible_trigger(self) -> None:
        with pytest.raises(ModelRetry):
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

    def test_contact_body_with_on_proximity_valid(self) -> None:
        b = _make_behavior(
            trigger=BehaviorTrigger.ON_PROXIMITY,
            target=BehaviorTarget.CONTACT_BODY,
            action=BehaviorAction.HEAL,
        )
        assert b.target == BehaviorTarget.CONTACT_BODY

    def test_contact_body_with_on_damaged_valid(self) -> None:
        b = _make_behavior(
            trigger=BehaviorTrigger.ON_DAMAGED,
            target=BehaviorTarget.CONTACT_BODY,
            action=BehaviorAction.DEAL_DAMAGE,
        )
        assert b.target == BehaviorTarget.CONTACT_BODY

    def test_contact_body_with_on_timer_rejected(self) -> None:
        with pytest.raises(ModelRetry):
            _make_behavior(
                trigger=BehaviorTrigger.ON_TIMER, target=BehaviorTarget.CONTACT_BODY
            )

    def test_add_tags_requires_tags_to_apply(self) -> None:
        with pytest.raises(ModelRetry):
            _make_behavior(action=BehaviorAction.ADD_TAGS)

    def test_add_tags_with_tags_to_apply_valid(self) -> None:
        b = _make_behavior(
            action=BehaviorAction.ADD_TAGS, tags_to_apply=[Tag.HOT, Tag.HEAT_SOURCE]
        )
        assert b.tags_to_apply == [Tag.HOT, Tag.HEAT_SOURCE]

    def test_remove_tags_requires_tags_to_apply(self) -> None:
        with pytest.raises(ModelRetry):
            _make_behavior(action=BehaviorAction.REMOVE_TAGS)


class TestBehaviorMessage:
    def test_message_none_valid(self) -> None:
        b = _make_behavior(message=None)
        assert b.message is None

    def test_message_short_valid(self) -> None:
        b = _make_behavior(message="BOOM!")
        assert b.message == "BOOM!"

    def test_message_60_chars_valid(self) -> None:
        msg = "A" * 60
        b = _make_behavior(message=msg)
        assert b.message == msg

    def test_message_over_60_chars_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _make_behavior(message="A" * 61)


class TestBehaviorCondition:
    def test_has_tag_condition(self) -> None:
        cond = BehaviorCondition(condition_type=BehaviorConditionType.HAS_TAG, tag=Tag.FROZEN)
        b = _make_behavior(condition=cond)
        assert b.condition is not None
        assert b.condition.condition_type == BehaviorConditionType.HAS_TAG
        assert b.condition.tag == Tag.FROZEN

    def test_not_has_tag_condition(self) -> None:
        cond = BehaviorCondition(condition_type=BehaviorConditionType.NOT_HAS_TAG, tag=Tag.FROZEN)
        b = _make_behavior(condition=cond)
        assert b.condition is not None
        assert b.condition.condition_type == BehaviorConditionType.NOT_HAS_TAG

    def test_target_has_tag_condition(self) -> None:
        cond = BehaviorCondition(
            condition_type=BehaviorConditionType.TARGET_HAS_TAG, tag=Tag.CONDUCTING
        )
        b = _make_behavior(condition=cond)
        assert b.condition is not None
        assert b.condition.condition_type == BehaviorConditionType.TARGET_HAS_TAG

    def test_condition_does_not_affect_cost(self) -> None:
        b_no_cond = _make_behavior(action=BehaviorAction.DEAL_DAMAGE)
        cond = BehaviorCondition(condition_type=BehaviorConditionType.HAS_TAG, tag=Tag.HOT)
        b_with_cond = _make_behavior(action=BehaviorAction.DEAL_DAMAGE, condition=cond)
        assert compute_behavior_cost(b_no_cond) == compute_behavior_cost(b_with_cond)


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
                    message="Wags tail",
                )
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 1

    def test_behavior_budget_exceeded_raises(self) -> None:
        with pytest.raises(ModelRetry):
            CreatorOutput(
                name="Overpowered",
                tags=[Tag.SOLID, Tag.RIGID],
                behaviors=[
                    Behavior(
                        trigger=BehaviorTrigger.ALWAYS,
                        action=BehaviorAction.SPAWN_PROJECTILE,
                        target=BehaviorTarget.NEAREST_LIVING,
                        intensity=Intensity.EXTREME,
                    ),
                    Behavior(
                        trigger=BehaviorTrigger.ALWAYS,
                        action=BehaviorAction.MOVE_TOWARD,
                        target=BehaviorTarget.NEAREST_LIVING,
                    ),
                ],
                visual_descriptor=_make_visual(),
            )  # 5 + 2 = 7 > 6

    def test_max_3_behaviors(self) -> None:
        with pytest.raises(ValidationError):
            CreatorOutput(
                name="Too Many",
                tags=[Tag.SOLID, Tag.RIGID],
                behaviors=[
                    Behavior(
                        trigger=BehaviorTrigger.ALWAYS,
                        action=BehaviorAction.SELF_DESTRUCT,
                    ),
                    Behavior(
                        trigger=BehaviorTrigger.ON_CREATE,
                        action=BehaviorAction.SELF_DESTRUCT,
                    ),
                    Behavior(
                        trigger=BehaviorTrigger.ON_DESTROY,
                        action=BehaviorAction.SELF_DESTRUCT,
                    ),
                    Behavior(
                        trigger=BehaviorTrigger.ON_TIMER,
                        action=BehaviorAction.SELF_DESTRUCT,
                    ),
                ],
                visual_descriptor=_make_visual(),
            )

    def test_dragon_example_valid(self) -> None:
        """Full dragon example from the plan: tag cost 8, behavior cost 6."""
        out = CreatorOutput(
            name="Fire Dragon",
            tags=[Tag.LIVING, Tag.HEAT_SOURCE, Tag.HOT],
            behaviors=[
                Behavior(
                    trigger=BehaviorTrigger.ALWAYS,
                    action=BehaviorAction.MOVE_TOWARD,
                    target=BehaviorTarget.NEAREST_LIVING,
                    speed=Speed.MEDIUM,
                    condition=BehaviorCondition(
                        condition_type=BehaviorConditionType.NOT_HAS_TAG, tag=Tag.FROZEN
                    ),
                    message="The dragon stalks its prey...",
                ),
                Behavior(
                    trigger=BehaviorTrigger.ON_PROXIMITY,
                    action=BehaviorAction.SPAWN_PROJECTILE,
                    target=BehaviorTarget.NEAREST_LIVING,
                    range=BehaviorRange.CLOSE,
                    intensity=Intensity.HIGH,
                    interval=Interval.SLOW,
                    message="The dragon breathes fire!",
                ),
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 2

    def test_reactive_bomb_example_valid(self) -> None:
        """ON_TAG_ADDED example: sits inert until HOT tag added."""
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
                    message="The bomb detonates!",
                )
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 1

    def test_behavior_budget_exactly_6_valid(self) -> None:
        """Dragon: MOVE_TOWARD(2) + SPAWN_PROJECTILE@HIGH(4) = 6."""
        out = CreatorOutput(
            name="Dragon",
            tags=[Tag.LIVING, Tag.SOLID],
            behaviors=[
                Behavior(
                    trigger=BehaviorTrigger.ALWAYS,
                    action=BehaviorAction.MOVE_TOWARD,
                    target=BehaviorTarget.NEAREST_LIVING,
                ),
                Behavior(
                    trigger=BehaviorTrigger.ON_PROXIMITY,
                    action=BehaviorAction.SPAWN_PROJECTILE,
                    target=BehaviorTarget.NEAREST_LIVING,
                    intensity=Intensity.HIGH,
                ),
            ],
            visual_descriptor=_make_visual(),
        )
        assert len(out.behaviors) == 2


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

    def test_serialization_includes_behavior_cost(self) -> None:
        bp = GameObjectBlueprint(
            id="test",
            name="Rock",
            description="a rock",
            tags=[Tag.SOLID, Tag.RIGID],
            visual_descriptor=_make_visual(),
        )
        data = bp.model_dump(mode="json")
        assert "behavior_cost" in data
        assert "behaviors" in data

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
                    message="BOOM!",
                )
            ],
            visual_descriptor=_make_visual(),
        )
        data = bp.model_dump(mode="json")
        assert len(data["behaviors"]) == 1
        assert data["behaviors"][0]["trigger"] == "ON_TIMER"
        assert data["behaviors"][0]["message"] == "BOOM!"
        assert data["behavior_cost"] == 5
