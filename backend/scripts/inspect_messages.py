#!/usr/bin/env python3
"""Inspect exact API payloads for each PydanticAI output mode.

Monkey-patches httpx to capture the raw request body sent to SGLang,
showing exactly what the model sees (system prompt, tools, response_format)
and what it responds with.

Usage:
    cd backend && uv run python scripts/inspect_messages.py
"""

from __future__ import annotations

import asyncio
import json
import textwrap

import httpx
from pydantic_ai import Agent, NativeOutput, PromptedOutput, TextOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from app.config import settings

PROMPT = (
    "A rock collides with another rock. Damage to rock? "
    "0=none 10=scratch 25=moderate 50=severe 75=critical 100=destroyed"
)

# Global capture of last request/response
_last_request_body: dict | None = None
_last_response_body: dict | None = None


def _base_settings() -> dict:
    s: dict = {"temperature": 0.0}
    if settings.local_llm_url:
        s["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    return s


def _build_model(with_profile=False):
    if settings.local_llm_url:
        kw = {}
        if with_profile:
            kw["profile"] = OpenAIModelProfile(supports_json_schema_output=True)
        return OpenAIChatModel(
            settings.llm_model,
            provider=OpenAIProvider(base_url=settings.local_llm_url, api_key="unused"),
            **kw,
        )
    return settings.llm_model


def _parse_int(text: str) -> int:
    cleaned = text.strip().strip('"').strip()
    num = ""
    for ch in cleaned:
        if ch in "-0123456789":
            num += ch
        elif num:
            break
    return int(num) if num else 0


# Monkey-patch httpx to capture requests
_original_send = httpx.AsyncClient.send


async def _capturing_send(self, request, **kwargs):
    global _last_request_body, _last_response_body
    if request.content:
        try:
            _last_request_body = json.loads(request.content)
        except Exception:
            _last_request_body = None

    response = await _original_send(self, request, **kwargs)

    # Capture response body
    try:
        await response.aread()
        _last_response_body = json.loads(response.content)
    except Exception:
        _last_response_body = None

    return response


httpx.AsyncClient.send = _capturing_send


def _indent(text: str, prefix: str = "    ") -> str:
    return textwrap.indent(text, prefix)


def _print_request(body: dict) -> None:
    """Print the interesting parts of the API request."""

    # Messages
    messages = body.get("messages", [])
    print("\n  INPUT MESSAGES:")
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "")
        if isinstance(content, str):
            print(f"    [{role}] {content[:500]}")
            if len(content) > 500:
                print(f"    ... ({len(content)} chars)")
        elif isinstance(content, list):
            # Multi-part content
            for part in content:
                if isinstance(part, dict):
                    print(f"    [{role}] {json.dumps(part, indent=6)[:300]}")

    # Tools
    tools = body.get("tools")
    if tools:
        print(f"\n  TOOLS ({len(tools)} defined):")
        print(_indent(json.dumps(tools, indent=2)))

    # Tool choice
    tc = body.get("tool_choice")
    if tc:
        print(f"\n  TOOL_CHOICE: {json.dumps(tc)}")

    # Response format
    rf = body.get("response_format")
    if rf:
        print(f"\n  RESPONSE_FORMAT:")
        print(_indent(json.dumps(rf, indent=2)))

    # Extra body fields (regex, etc)
    for key in ["regex", "ebnf", "guided_regex", "guided_json"]:
        if key in body:
            print(f"\n  {key.upper()}: {body[key]}")

    # Chat template kwargs
    ctk = body.get("chat_template_kwargs")
    if ctk:
        print(f"\n  CHAT_TEMPLATE_KWARGS: {json.dumps(ctk)}")


def _print_response(body: dict) -> None:
    """Print the model's response."""
    choices = body.get("choices", [])
    if not choices:
        print("\n  OUTPUT: (no choices)")
        return

    msg = choices[0].get("message", {})
    content = msg.get("content")
    tool_calls = msg.get("tool_calls")

    print("\n  OUTPUT MESSAGE:")
    if content:
        print(f"    content: {content[:300]}")
    if tool_calls:
        for tc in tool_calls:
            fn = tc.get("function", {})
            print(f"    tool_call: {fn.get('name')}({fn.get('arguments')})")

    # Token usage
    usage = body.get("usage", {})
    if usage:
        print(f"\n  USAGE: {json.dumps(usage)}")


async def run_mode(name: str, agent: Agent, prompt: str, **kw) -> None:
    global _last_request_body, _last_response_body
    _last_request_body = None
    _last_response_body = None

    print(f"\n{'=' * 80}")
    print(f"MODE: {name}")
    print(f"{'=' * 80}")

    try:
        result = await agent.run(prompt, **kw)
        print(f"\n  PYDANTIC-AI OUTPUT: {result.output}")
    except Exception as e:
        print(f"\n  ERROR: {e}")

    if _last_request_body:
        _print_request(_last_request_body)
    if _last_response_body:
        _print_response(_last_response_body)


async def main() -> None:
    model = _build_model()
    model_profiled = _build_model(with_profile=True)
    base = _base_settings()

    # 1. Tool mode
    await run_mode(
        "tool (output_type=int) — CURRENT PRODUCTION",
        Agent(model, output_type=int, retries=0, model_settings=base),
        PROMPT,
    )

    # 2. Native mode
    await run_mode(
        "native (NativeOutput(int)) — json_schema response_format",
        Agent(model_profiled, output_type=NativeOutput(int), retries=0, model_settings=base),
        PROMPT,
    )

    # 3. Prompted mode
    await run_mode(
        "prompted (PromptedOutput(int)) — schema in system prompt",
        Agent(model, output_type=PromptedOutput(int), retries=0, model_settings=base),
        PROMPT,
    )

    # 4. TextOutput + regex
    regex_settings = _base_settings()
    if settings.local_llm_url:
        regex_settings["extra_body"]["regex"] = r"-?[0-9]{1,3}"
    await run_mode(
        "text+regex (TextOutput + SGLang regex constraint)",
        Agent(model, output_type=TextOutput(_parse_int), retries=0, model_settings=base),
        PROMPT,
        model_settings=regex_settings,
    )

    # 5. TextOutput + prompt
    await run_mode(
        "text+prompt (TextOutput + instruction suffix)",
        Agent(model, output_type=TextOutput(_parse_int), retries=0, model_settings=base),
        PROMPT + " Reply with ONLY a number, nothing else.",
    )


if __name__ == "__main__":
    asyncio.run(main())
