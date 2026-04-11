# Future Optimizations

Optimizations evaluated during architecture review that aren't part of the current build. Each can be adopted independently. These apply to the **local LLM path** (when `LOCAL_LLM_URL` is set), not the default Gemini cloud backend.

---

## Raw httpx + SGLang constrained decoding

**What:** Bypass PydanticAI for 1-token numeric LLM calls. Use raw httpx to SGLang's OpenAI-compatible API with the `regex` parameter for constrained decoding.

**Why:** SGLang supports regex constraints that force output to match a pattern (e.g., `[0-9]{1,5}`) at the grammar level. This eliminates parsing failures entirely — the model physically cannot output "The mass would be about 2 kg" when constrained to digits only.

**Speed:** ~5-10ms overhead saved per call by skipping PydanticAI's agent/parsing machinery. Hidden by parallelism when firing 13 calls concurrently.

**Tradeoff:** Two LLM client systems to maintain (PydanticAI for structured output, raw httpx for constrained numeric). Adds complexity.

**When to adopt:** If parsing failures on 1-token calls become a problem during playtesting. If the model reliably returns clean integers with PydanticAI, this optimization isn't needed.

```python
# What it would look like
async def ask_int(client: httpx.AsyncClient, prompt: str, max_val: int = 100) -> int:
    resp = await client.post(SGLANG_URL, json={
        "model": MODEL,
        "prompt": prompt,
        "max_tokens": 1,
        "regex": f"[0-9]{{1,{len(str(max_val))}}}"
    })
    return int(resp.json()["choices"][0]["text"])
```

---

## stamina retry library

**What:** Replace hand-rolled retry logic with [stamina](https://stamina.hynek.me/) for exponential backoff + jitter on transient failures (503 from SGLang, network errors).

**When to adopt:** If we move to raw httpx calls (above) and lose PydanticAI's built-in retry. Not needed while PydanticAI handles retries.
