"""Benchmark: break down the ~65ms floor into HTTP overhead vs inference.

Tests:
1. Raw HTTP round-trip (health endpoint, no inference)
2. Empty-ish inference (minimal prompt, 1 token)
3. Same via raw TCP socket (skip httpx overhead)
4. Keep-alive vs fresh connection
5. SGLang /generate endpoint if available (less HTTP overhead than /chat/completions)

Usage:
    cd backend && uv run python bench_overhead.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import statistics
import time

import httpx

BASE_URL = "http://127.0.0.1:5200/v1"
MODEL = "Qwen/Qwen3.5-35B-A3B-FP8"

EXTRA_BODY = {"chat_template_kwargs": {"enable_thinking": False}}


async def main():
    print("=" * 70)
    print("OVERHEAD BREAKDOWN")
    print("=" * 70)

    # ----- Test 1: Raw HTTP GET (no inference) -----
    print("\n--- 1. Raw HTTP GET /models (no inference) ---")
    async with httpx.AsyncClient() as client:
        times = []
        for _ in range(50):
            t0 = time.perf_counter()
            resp = await client.get(f"{BASE_URL}/models")
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            times.append(elapsed)
        print(f"  mean={statistics.mean(times)*1000:5.2f}ms  "
              f"median={statistics.median(times)*1000:5.2f}ms  "
              f"min={min(times)*1000:5.2f}ms  "
              f"max={max(times)*1000:5.2f}ms")

    # ----- Test 2: Raw TCP socket GET (bypass httpx entirely) -----
    print("\n--- 2. Raw TCP socket GET /v1/models (no httpx) ---")
    times = []
    for _ in range(50):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(("127.0.0.1", 5200))
        req = b"GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:5200\r\nConnection: close\r\n\r\n"
        t0 = time.perf_counter()
        sock.sendall(req)
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        sock.close()
    print(f"  mean={statistics.mean(times)*1000:5.2f}ms  "
          f"median={statistics.median(times)*1000:5.2f}ms  "
          f"min={min(times)*1000:5.2f}ms")

    # ----- Test 3: Keep-alive TCP socket (reuse connection) -----
    print("\n--- 3. Keep-alive TCP socket GET /v1/models ---")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(("127.0.0.1", 5200))
    times = []
    for _ in range(50):
        req = b"GET /v1/models HTTP/1.1\r\nHost: 127.0.0.1:5200\r\nConnection: keep-alive\r\n\r\n"
        t0 = time.perf_counter()
        sock.sendall(req)
        data = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            data += chunk
            # Simple check for end of HTTP response
            if b"\r\n\r\n" in data:
                # Check for Content-Length
                header_end = data.index(b"\r\n\r\n")
                headers = data[:header_end].decode(errors="replace")
                for line in headers.split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        cl = int(line.split(":")[1].strip())
                        body_start = header_end + 4
                        if len(data) - body_start >= cl:
                            break
                else:
                    # Chunked or no content-length, just take what we got
                    break
                if len(data) - body_start >= cl:
                    break
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
    sock.close()
    print(f"  mean={statistics.mean(times)*1000:5.2f}ms  "
          f"median={statistics.median(times)*1000:5.2f}ms  "
          f"min={min(times)*1000:5.2f}ms")

    # ----- Test 4: httpx inference - minimal (1 token) -----
    print("\n--- 4. httpx chat/completions - minimal prompt, 1 token out ---")
    async with httpx.AsyncClient() as client:
        # Warmup
        for _ in range(5):
            await client.post(f"{BASE_URL}/chat/completions", json={
                "model": MODEL, "max_tokens": 1,
                "messages": [{"role": "user", "content": "1"}],
                **EXTRA_BODY,
            })

        times = []
        for _ in range(30):
            body = {
                "model": MODEL, "max_tokens": 1, "temperature": 0,
                "messages": [{"role": "user", "content": "1"}],
                **EXTRA_BODY,
            }
            t0 = time.perf_counter()
            resp = await client.post(f"{BASE_URL}/chat/completions", json=body)
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            times.append(elapsed)
        print(f"  mean={statistics.mean(times)*1000:5.2f}ms  "
              f"median={statistics.median(times)*1000:5.2f}ms  "
              f"min={min(times)*1000:5.2f}ms")

    # ----- Test 5: httpx inference - longer prompt, 1 token out -----
    print("\n--- 5. httpx chat/completions - 500 token prompt, 1 token out ---")
    long_prompt = "word " * 250  # ~500 tokens
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            await client.post(f"{BASE_URL}/chat/completions", json={
                "model": MODEL, "max_tokens": 1,
                "messages": [{"role": "user", "content": long_prompt + " Reply: 1"}],
                **EXTRA_BODY,
            })
        times = []
        for _ in range(30):
            body = {
                "model": MODEL, "max_tokens": 1, "temperature": 0,
                "messages": [
                    {"role": "system", "content": "Reply with only the number 1."},
                    {"role": "user", "content": long_prompt},
                ],
                **EXTRA_BODY,
            }
            t0 = time.perf_counter()
            resp = await client.post(f"{BASE_URL}/chat/completions", json=body)
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            times.append(elapsed)
        print(f"  mean={statistics.mean(times)*1000:5.2f}ms  "
              f"median={statistics.median(times)*1000:5.2f}ms  "
              f"min={min(times)*1000:5.2f}ms")

    # ----- Test 6: httpx inference - 1500 token prompt (like creator), 1 token out -----
    print("\n--- 6. httpx chat/completions - 1500 token prompt, 1 token out ---")
    very_long_prompt = "word " * 750  # ~1500 tokens
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            await client.post(f"{BASE_URL}/chat/completions", json={
                "model": MODEL, "max_tokens": 1,
                "messages": [{"role": "user", "content": very_long_prompt + " Reply: 1"}],
                **EXTRA_BODY,
            })
        times = []
        for _ in range(30):
            body = {
                "model": MODEL, "max_tokens": 1, "temperature": 0,
                "messages": [
                    {"role": "system", "content": "Reply with only the number 1."},
                    {"role": "user", "content": very_long_prompt},
                ],
                **EXTRA_BODY,
            }
            t0 = time.perf_counter()
            resp = await client.post(f"{BASE_URL}/chat/completions", json=body)
            elapsed = time.perf_counter() - t0
            resp.raise_for_status()
            times.append(elapsed)
        print(f"  mean={statistics.mean(times)*1000:5.2f}ms  "
              f"median={statistics.median(times)*1000:5.2f}ms  "
              f"min={min(times)*1000:5.2f}ms")

    # ----- Test 7: Parallel inference - 4 minimal calls -----
    print("\n--- 7. Parallel 4x minimal inference (1 token each) ---")
    async with httpx.AsyncClient() as client:
        for _ in range(3):
            await client.post(f"{BASE_URL}/chat/completions", json={
                "model": MODEL, "max_tokens": 1,
                "messages": [{"role": "user", "content": "1"}],
                **EXTRA_BODY,
            })
        times = []
        for _ in range(30):
            async def one_call():
                t0 = time.perf_counter()
                resp = await client.post(f"{BASE_URL}/chat/completions", json={
                    "model": MODEL, "max_tokens": 1, "temperature": 0,
                    "messages": [{"role": "user", "content": "1"}],
                    **EXTRA_BODY,
                })
                return time.perf_counter() - t0

            t0 = time.perf_counter()
            results = await asyncio.gather(one_call(), one_call(), one_call(), one_call())
            wall = time.perf_counter() - t0
            times.append(wall)
        print(f"  wall: mean={statistics.mean(times)*1000:5.2f}ms  "
              f"median={statistics.median(times)*1000:5.2f}ms  "
              f"min={min(times)*1000:5.2f}ms")

    # ----- Summary -----
    print(f"\n{'='*70}")
    print("BREAKDOWN ESTIMATE")
    print(f"{'='*70}")
    print("  Compare tests 1 vs 4 to see: HTTP overhead vs inference overhead")
    print("  Compare tests 4 vs 5 vs 6 to see: prefill cost scaling with prompt length")
    print("  Compare tests 4 vs 7 to see: parallel batching overhead")


if __name__ == "__main__":
    asyncio.run(main())
