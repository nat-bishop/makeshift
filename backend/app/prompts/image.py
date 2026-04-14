"""Prompts for the image generation pipeline.

Two kinds of prompts live here:

1. **FLUX prompts** — strings passed directly to the local FLUX model
   (text-to-image and Kontext img2img). These are the style wrapper
   (`IMG2IMG_STYLE`, `IMG2IMG_SUFFIX_*`) and `build_text_to_image_prompt()`.

2. **LLM prompts** — strings passed to the text LLM (via
   `app.creator.llm.ask_text` / `ask_choice`) which *produce* the
   natural-language description that then gets wrapped with the FLUX
   style wrapper. Each LLM call has one `build_*_prompt()` function that
   returns `(instructions, user_message)` so the system prompt and the
   user-message template are visible side-by-side.

Consumed by `app.images.pipeline`. Pure strings / pure functions — no
blueprint or image-processing dependencies, so this file can be scanned
end-to-end when iterating on prompt content.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# FLUX prompt fragments
# ---------------------------------------------------------------------------

# Style wrapper applied to every img2img generation.
IMG2IMG_STYLE = "mixed media collage style paper cutout, side view, flat lighting, clean edges"

# Suffix appended to img2img generations of a single object (destruction, combine).
IMG2IMG_SUFFIX_OBJECT = "single centered object, contrasting solid background color, no text"

# Suffix appended to img2img generations of a multi-subject scene (carry, ride).
IMG2IMG_SUFFIX_SCENE = "single centered scene, contrasting solid background color, no text"


def build_text_to_image_prompt(name: str, visual_description: str) -> str:
    """Build the narrative FLUX text-to-image prompt for a new object sprite."""
    return (
        f"A mixed media collage of {name} made from cut paper, magazine clippings, "
        f"and cardboard, held together with visible scotch tape and glue. "
        f"{visual_description} "
        f"Side view, single centered object on a solid contrasting background. "
        f"Flat lighting, clean edges, no text."
    )


# ---------------------------------------------------------------------------
# LLM prompts — carry / ride (img2img composite with the player)
# ---------------------------------------------------------------------------

CARRY_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "A character is carrying an object. You receive descriptions of both. "
    "Write a visual description of the character holding/carrying the object "
    "as a single scene. Reference specific visual details from both descriptions. "
    "Under 25 words. Output ONLY the visual description."
)

RIDE_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "A character is riding a mount. You receive descriptions of both. "
    "Write a visual description of the character sitting on/riding the mount "
    "as a single scene. Reference specific visual details from both descriptions. "
    "Under 25 words. Output ONLY the visual description."
)


def build_carry_ride_prompt(
    affordance: int,
    object_name: str,
    object_visual: str,
) -> tuple[str, str]:
    """Bundle (system instructions, user message) for the carry/ride LLM call.

    affordance == 1 → ride; anything else → carry. Matches
    `AFFORDANCE_LABELS` on the blueprint.
    """
    if affordance == 1:
        instructions, action, role = RIDE_INSTRUCTION, "riding", "Mount"
    else:
        instructions, action, role = CARRY_INSTRUCTION, "carrying", "Object"
    user_message = (
        f"Character: player\n"
        f"{role}: {object_name} — {object_visual}\n"
        f"Describe the player {action} the {role.lower()}:"
    )
    return instructions, user_message


# ---------------------------------------------------------------------------
# LLM prompts — destruction (img2img debris from a single source sprite)
# ---------------------------------------------------------------------------

DESTRUCTION_INSTRUCTION = (
    "You write visual descriptions for a mixed media collage paper cutout game. "
    "An object was smashed. Describe the debris as a single paper cutout sprite. "
    "The debris must look completely different from the original object's silhouette. "
    "It should be a low, flat pile or scatter of broken fragments. "
    "Reference the original's specific colors and material textures. "
    "Under 20 words. Output ONLY the visual description."
)


def build_destruction_prompt(
    object_name: str,
    object_visual: str,
    destruction_result_name: str,
) -> tuple[str, str]:
    """Bundle (system instructions, user message) for the destruction debris LLM call."""
    user_message = (
        f"Object: {object_name} — {object_visual}\n"
        f"Debris name: {destruction_result_name}\n"
        f"Describe the destroyed remains:"
    )
    return DESTRUCTION_INSTRUCTION, user_message


# ---------------------------------------------------------------------------
# LLM prompts — combination (img2img hybrid of two source sprites)
# ---------------------------------------------------------------------------

COMBINE_INSTRUCTION = (
    "You write visual descriptions for a sprite image generator. "
    "Two objects are being combined. Choose the best approach:\n"
    "- MATERIAL: 'the shape of B but made from/constructed of A' "
    "(when A is a material-like thing)\n"
    "- THEMED: 'B with A elements, accents, and motifs woven into its design' "
    "(when A is an aesthetic)\n"
    "- SEMANTIC: 'an A B, combining elements of both into one object' "
    "(when both contribute equally)\n"
    "Pick the best fit. Reference specific visual details from both source descriptions. "
    "Under 25 words. Output ONLY the visual description."
)

COMBINE_ORDER_INSTRUCTION = (
    "Two objects are being combined into one sprite image. "
    "The first reference image has more influence on the overall shape and form. "
    "Pick which object should be the primary shape reference."
)


def build_combine_prompt(
    name_a: str,
    visual_a: str,
    name_b: str,
    visual_b: str,
) -> tuple[str, str]:
    """Bundle (system instructions, user message) for the combination description LLM call."""
    user_message = (
        f"Object A: {name_a} — {visual_a}\n"
        f"Object B: {name_b} — {visual_b}\n"
        f"Write the visual description for combining A with B:"
    )
    return COMBINE_INSTRUCTION, user_message


def build_combine_order_prompt(name_a: str, name_b: str) -> tuple[str, str]:
    """Bundle (system instructions, user message) for the combination-order choice call.

    The choice is between "1" and "2" — which object should be the primary shape reference.
    """
    user_message = f"1: {name_a}\n2: {name_b}"
    return COMBINE_ORDER_INSTRUCTION, user_message
