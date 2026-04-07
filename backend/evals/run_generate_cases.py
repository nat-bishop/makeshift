"""Synthetic test case generator for eval dataset expansion.

Uses a pydantic-ai agent to generate new eval cases from game design context.
Cases are saved to a YAML file for human review — NOT auto-added to the main dataset.

Usage:
    cd backend && uv run python -m evals.run_generate_cases
    cd backend && uv run python -m evals.run_generate_cases --n 50
    cd backend && uv run python -m evals.run_generate_cases --model google-gla:gemini-3-flash-preview
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_evals import Case, Dataset

from evals.dataset import CaseMeta

SYSTEM_PROMPT = """\
You generate test cases for evaluating a 2D physics sandbox game object creator (like Scribblenauts).
Players type a description and an LLM creates a game object with tags and behaviors.

LLM-VISIBLE TAGS (0-3 per object, the only tags the creator LLM can pick):
SHARP, HEAVY, LIGHT, BOUNCY, BREAKABLE, STICKY, REFLECTIVE, EXPLOSIVE, FLYING, WET

Other tags (LIVING, HOSTILE, METALLIC, RIGID, FLAMMABLE, etc.) are auto-derived from \
substance, element, or category — the LLM does not pick them directly.

GUIDELINES:
- Diverse: cover all categories, not just weapons and creatures
- Realistic: mimic actual player input patterns (terse, sloppy, excited, questions, etc.)
- Include edge cases: contradictions, abstract concepts, pop culture, problem-framing
- For adversarial: vague inputs, misspellings, questions, prompt injection attempts
- For expected_tags: ONLY include tags that are unambiguously correct from the prompt. \
Leave empty [] for ambiguous cases.
- Avoid common cases like "fire sword", "rock", "helicopter" — focus on coverage gaps.
"""


class GeneratedCase(BaseModel):
    name: str
    inputs: str
    category: str
    expected_tags: list[str]
    notes: str


class GeneratedDataset(BaseModel):
    cases: list[GeneratedCase]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate synthetic eval cases")
    parser.add_argument(
        "--n", type=int, default=30, help="Number of cases to generate (default: 30)"
    )
    parser.add_argument(
        "--model",
        default="google-gla:gemini-3-flash-preview",
        help="Model to use for generation",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output file path (default: evals/generated_cases.yaml)",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    output_path = Path(args.output) if args.output else Path(__file__).parent / "generated_cases.yaml"

    print(f"Generating {args.n} synthetic cases with {args.model}...")

    agent = Agent(
        args.model,
        output_type=GeneratedDataset,
        system_prompt=SYSTEM_PROMPT,
    )

    result = await agent.run(
        f"Generate {args.n} diverse test cases. "
        "Categories to cover: mundane, weapon, trap, creature, abstract, adversarial, "
        "environment, defensive, utility, vehicle, traversal, nature, consumable, problem. "
        "Vary input styles: terse keywords, full sentences, questions, misspellings, slang, "
        "ALL CAPS, rambling."
    )

    generated = result.output

    # Convert to pydantic-evals Dataset
    cases = [
        Case(
            name=c.name,
            inputs=c.inputs,
            metadata=CaseMeta(
                category=c.category,
                expected_tags=c.expected_tags,
                notes=c.notes,
            ),
        )
        for c in generated.cases
    ]
    dataset: Dataset[str, str, CaseMeta] = Dataset(cases=cases)
    dataset.to_file(output_path)

    print(f"\nGenerated {len(cases)} cases -> {output_path}")
    print("\nCases:")
    for c in cases:
        tags = c.metadata.expected_tags if c.metadata else []
        cat = c.metadata.category if c.metadata else "?"
        print(f"  [{cat}] {c.name}: {c.inputs!r} -> {tags}")

    print(f"\nReview {output_path} and cherry-pick good cases into dataset.yaml.")


if __name__ == "__main__":
    asyncio.run(main())
