"""Output models for the split-agent experiment.

Call 1 (classify): substance + element + tags + name
Call 2 (creative): behaviors + visual descriptor (given Call 1 output)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.blueprint import BehaviorVerbSpec, VisualDescriptor
from app.models.substances import Element, Substance
from app.models.tags import LLM_VISIBLE_TAGS, Tag


class ClassifyOutput(BaseModel):
    """Call 1 output: classification decisions."""

    name: str
    substance: Substance
    element: Element | None = None
    tags: list[Tag] = Field(default_factory=list, max_length=3)

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name must not be empty")
        if len(v.split()) > 3:
            raise ValueError("Name must be 1-3 words")
        return v

    @field_validator("tags")
    @classmethod
    def tags_must_be_v2_visible(cls, v: list[Tag]) -> list[Tag]:
        invalid = [t for t in v if t not in LLM_VISIBLE_TAGS]
        if invalid:
            valid = ", ".join(sorted(t.value for t in LLM_VISIBLE_TAGS))
            raise ValueError(
                f"Tags {[t.value for t in invalid]} not in V2 visible set. "
                f"Valid tags: {valid}"
            )
        return v


class CreativeOutput(BaseModel):
    """Call 2 output: creative generation given classification."""

    behaviors: list[BehaviorVerbSpec] = Field(default_factory=list, max_length=4)
    visual_descriptor: VisualDescriptor
