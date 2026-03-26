"""Tag-driven animation routing: determines if an object needs a sprite sheet."""

from __future__ import annotations

from dataclasses import dataclass

from app.models.behaviors import Behavior, BehaviorAction
from app.models.tags import Tag

MOVEMENT_ACTIONS: frozenset[BehaviorAction] = frozenset(
    {BehaviorAction.MOVE_TOWARD, BehaviorAction.MOVE_AWAY, BehaviorAction.PATROL}
)


@dataclass
class AnimationConfig:
    """Configuration for how an object should be animated."""

    animated: bool = False
    has_movement: bool = False
    fps: int = 6


@dataclass
class AnimationMeta:
    """Metadata sent alongside a sprite sheet to the client."""

    columns: int = 2
    rows: int = 2
    frame_count: int = 4
    fps: int = 6

    def to_dict(self) -> dict[str, int]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "frame_count": self.frame_count,
            "fps": self.fps,
        }


def get_animation_config(tags: list[Tag], behaviors: list[Behavior]) -> AnimationConfig:
    """Determine animation type from tags. Only LIVING triggers sprite sheets."""
    if Tag.LIVING not in tags:
        return AnimationConfig()
    has_movement = any(b.action in MOVEMENT_ACTIONS for b in behaviors)
    fps = 6 if has_movement else 3
    return AnimationConfig(animated=True, has_movement=has_movement, fps=fps)
