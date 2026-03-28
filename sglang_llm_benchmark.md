# SGLang LLM Benchmark Results

**Model:** Qwen/Qwen3.5-9B
**Server:** SGLang dev-cu13, port 5200
**Hardware:** Single GPU, 17.6GB weight, 10.3GB KV cache, mem_fraction_static=0.40
**Reasoning parser:** qwen3
**Date:** 2026-03-27

## Summary

| Mode | Avg Tok/s | Avg Wall Time | Usable? |
|------|-----------|---------------|---------|
| No thinking | 60-77 | 200-600ms | Yes — fast and practical |
| Full thinking | 78-82 | 3-90s | Slow — massive thinking overhead |
| Thinking budget (50-200) | 73-83 | 3-26s | **Budget param is ignored** by SGLang |

**Key finding:** `thinking_budget` is NOT an SGLang feature (it's NVIDIA NIM). SGLang only supports binary thinking control via `chat_template_kwargs: {enable_thinking: false}`. There is no way to limit thinking token count through the API — it's all or nothing.

## Detailed Results

### NO THINKING (`chat_template_kwargs: {enable_thinking: false}`)

| Prompt | Wall | Input | Think | Output | Total | Tok/s | Fin | Response |
|--------|------|-------|-------|--------|-------|-------|-----|----------|
| Simple factual | 199ms | 24 | 0 | 8 | 8 | 40.1 | stop | The capital of France is Paris. |
| Creative short | 370ms | 20 | 0 | 22 | 22 | 59.3 | stop | Silent cone stands tall, Red earth sleeps beneath gray clouds, Earth w... |
| Code gen | 585ms | 32 | 0 | 39 | 39 | 66.6 | stop | `def is_palindrome(s): cleaned = ''.join(char.lower() for...` |
| Game design | 599ms | 32 | 0 | 46 | 46 | 76.8 | stop | The Incinerator blade pulses with ancient fire. First, it never cools,... |

### WITH THINKING (default, max_tokens=8192)

| Prompt | Wall | Input | Think | Output | Total | Tok/s | Fin | Response |
|--------|------|-------|-------|--------|-------|-------|-----|----------|
| Simple factual | 2.9s | 22 | 221 | 9 | 230 | 80.1 | stop | The capital of France is Paris. |
| Creative short | 75.9s | 18 | 6,079 | 30 | 6,109 | 80.5 | stop | Mountain stands in sleep Red lava flows down the slope Ash falls from... |
| Code gen | 40.6s | 30 | 3,286 | 33 | 3,319 | 81.7 | stop | `def is_palindrome(s): cleaned = ''.join(c.lower() for c...` |
| Game design | 90.0s | 30 | 7,093 | 100 | 7,193 | 79.9 | stop | The Emberbolt Cleaver flows with purple fire... |

Note: Think/Output split is estimated from character ratio — SGLang reports all as `completion_tokens`.

### THINKING BUDGET = 200 (IGNORED BY SERVER)

| Prompt | Wall | Input | Think | Output | Total | Tok/s | Fin |
|--------|------|-------|-------|--------|-------|-------|-----|
| Simple factual | 2.7s | 22 | 192 | 10 | 202 | 73.7 | stop |
| Creative short | 26.5s | 18 | 2,048 | 0 | 2,048 | 77.4 | length |
| Code gen | 26.0s | 30 | 2,048 | 0 | 2,048 | 78.6 | length |
| Game design | 25.2s | 30 | 2,048 | 0 | 2,048 | 81.3 | length |

### THINKING BUDGET = 100 (IGNORED BY SERVER)

| Prompt | Wall | Input | Think | Output | Total | Tok/s | Fin |
|--------|------|-------|-------|--------|-------|-------|-----|
| Simple factual | 2.9s | 22 | 229 | 10 | 239 | 83.4 | stop |
| Creative short | 25.2s | 18 | 2,048 | 0 | 2,048 | 81.3 | length |
| Code gen | 26.5s | 30 | 2,048 | 0 | 2,048 | 77.3 | length |
| Game design | 25.9s | 30 | 2,048 | 0 | 2,048 | 79.0 | length |

### THINKING BUDGET = 50 (IGNORED BY SERVER)

| Prompt | Wall | Input | Think | Output | Total | Tok/s | Fin |
|--------|------|-------|-------|--------|-------|-------|-----|
| Simple factual | 2.6s | 22 | 181 | 10 | 191 | 72.7 | stop |
| Creative short | 25.1s | 18 | 2,048 | 0 | 2,048 | 81.5 | length |
| Code gen | 25.6s | 30 | 2,024 | 15 | 2,039 | 79.7 | stop |
| Game design | 25.7s | 30 | 2,048 | 0 | 2,048 | 79.7 | length |

## Observations

1. **Throughput is consistent at ~78-82 tok/s** with thinking, ~40-77 tok/s without (lower numbers are just small-sample variance on short outputs).

2. **Thinking is wildly disproportionate.** The model spends 6,000+ tokens thinking about a haiku and 7,000+ tokens thinking about a 50-word game description. The actual output is <100 tokens in every case.

3. **`thinking_budget` parameter is not implemented in SGLang** for Qwen3. The parameter is accepted silently but has no effect. The only way to control thinking is binary: `enable_thinking: true/false`.

4. **Without thinking, response quality is still good** and latency drops from 3-90 seconds to 200-600ms. For the game's use case (object creation), no-thinking mode is likely the right choice.

5. **SGLang reports `reasoning_tokens: 0`** in the usage object regardless of actual thinking. The thinking content is returned in `reasoning_content` field on the message, but token accounting doesn't separate it from `completion_tokens`.

## API Parameters

```json
// Disable thinking (recommended for game use):
{
  "model": "Qwen/Qwen3.5-9B",
  "messages": [...],
  "max_tokens": 1024,
  "chat_template_kwargs": {"enable_thinking": false}
}

// Enable thinking (default):
{
  "model": "Qwen/Qwen3.5-9B",
  "messages": [...],
  "max_tokens": 8192
}
```

## Thinking Control Research

**SGLang does NOT support `thinking_budget` or `max_thinking_tokens`.** Those are NVIDIA NIM features. SGLang's only control is binary on/off via `chat_template_kwargs`.

The only way to get granular thinking limits would be a custom `LogitsProcessor` that force-injects `</think>` after N tokens, but this requires direct `transformers` library access — not available through SGLang's OpenAI-compatible API.

Sources:
- [SGLang Reasoning Parser docs](https://docs.sglang.io/advanced_features/separate_reasoning.html)
- [SGLang Qwen3.5 Cookbook](https://cookbook.sglang.io/autoregressive/Qwen/Qwen3.5)
- [Limiting Qwen3 Thinking (Zach Mueller)](https://muellerzr.github.io/til/end_thinking.html)
- [SGLang issue #20573 — Qwen3.5 thinking mode](https://github.com/sgl-project/sglang/issues/20573)
