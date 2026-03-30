"""Prompt variant registry for A/B evaluation.

Add a new variant by adding a key to PROMPT_VARIANTS.
The key is used as the variant name in CLI args and reports.
"""

from __future__ import annotations

from app.creator.agent import SYSTEM_PROMPT

PROMPT_VARIANTS: dict[str, str] = {
    "baseline": SYSTEM_PROMPT,
    # Add new variants here. Example:
    # "v2_shorter": "You are a game object designer ...",
    # "v3_more_examples": SYSTEM_PROMPT + "\n\n## More Examples\n...",
}
