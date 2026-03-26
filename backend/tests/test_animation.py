"""Tests for animation routing logic."""

from __future__ import annotations

from app.images.animation import AnimationConfig, AnimationMeta, get_animation_config
from app.models.behaviors import (
    Behavior,
    BehaviorAction,
    BehaviorTarget,
    BehaviorTrigger,
    Intensity,
)
from app.models.tags import Tag


def _make_behavior(action: BehaviorAction) -> Behavior:
    return Behavior(
        trigger=BehaviorTrigger.ALWAYS,
        action=action,
        target=BehaviorTarget.NEAREST_OBJECT,
        intensity=Intensity.MEDIUM,
    )


def test_non_living_returns_static() -> None:
    config = get_animation_config([Tag.SOLID, Tag.HEAVY], [])
    assert config.animated is False


def test_living_returns_animated() -> None:
    config = get_animation_config([Tag.LIVING, Tag.SOLID], [])
    assert config.animated is True


def test_living_without_movement_low_fps() -> None:
    config = get_animation_config([Tag.LIVING], [])
    assert config.animated is True
    assert config.has_movement is False
    assert config.fps == 3


def test_living_with_patrol_high_fps() -> None:
    config = get_animation_config(
        [Tag.LIVING], [_make_behavior(BehaviorAction.PATROL)]
    )
    assert config.animated is True
    assert config.has_movement is True
    assert config.fps == 6


def test_living_with_move_toward() -> None:
    config = get_animation_config(
        [Tag.LIVING], [_make_behavior(BehaviorAction.MOVE_TOWARD)]
    )
    assert config.has_movement is True


def test_living_with_move_away() -> None:
    config = get_animation_config(
        [Tag.LIVING], [_make_behavior(BehaviorAction.MOVE_AWAY)]
    )
    assert config.has_movement is True


def test_living_with_non_movement_behavior() -> None:
    config = get_animation_config(
        [Tag.LIVING], [_make_behavior(BehaviorAction.DEAL_DAMAGE)]
    )
    assert config.has_movement is False


def test_empty_tags() -> None:
    config = get_animation_config([], [])
    assert config == AnimationConfig()


def test_animation_meta_to_dict() -> None:
    meta = AnimationMeta(columns=2, rows=2, frame_count=4, fps=6)
    d = meta.to_dict()
    assert d == {"columns": 2, "rows": 2, "frame_count": 4, "fps": 6}


def test_animation_meta_defaults() -> None:
    meta = AnimationMeta()
    assert meta.columns == 2
    assert meta.rows == 2
    assert meta.frame_count == 4
    assert meta.fps == 6
