# SGLang Servers

Two SGLang instances run side-by-side on the same GPU:

| Server | Model | Port | Purpose |
|--------|-------|------|---------|
| FLUX | FLUX.2-klein-4b-fp8 | 5100 | Image generation |
| LLM | Qwen/Qwen3.5-7B | 5200 | Object creation (PydanticAI agent) |

Both use `mem_fraction_static: 0.40` to share VRAM.

## Install

```bash
pip install 'sglang[all]'
```

## FLUX Image Server

```bash
make serve-gpu          # start in WSL2
make wait-gpu           # wait until ready
make stop-gpu           # stop
```

Configure backend:
```env
IMAGE_BACKEND=local
LOCAL_IMAGE_URL=http://127.0.0.1:5100
LOCAL_IMAGE_MODEL=black-forest-labs/FLUX.2-klein-4b-fp8
```

## LLM Server (Qwen 3.5)

```bash
make serve-llm          # start in WSL2
make wait-llm           # wait until ready
make stop-llm           # stop
```

Configure backend:
```env
LLM_MODEL=Qwen/Qwen3.5-7B
LOCAL_LLM_URL=http://127.0.0.1:5200/v1
```

### Alternative models

```bash
# Edit the serve-llm target or run directly:
wsl -d Ubuntu-24.04 -u root -- /bin/bash -c '\
    /opt/sglang/bin/python -m sglang.launch_server \
        --model-path Qwen/Qwen3.5-14B --port 5200 --mem-fraction-static 0.40'
```

## Environment variables for Blackwell RTX 6000 Pro

```bash
SGLANG_ENABLE_JIT_DEEPGEMM=0     # Required -- DeepGemm JIT not supported on SM120
SGLANG_CACHE_DIT_ENABLED=true     # Up to 1.69x speedup
SGLANG_SET_CPU_AFFINITY=1         # Performance
SAFETENSORS_FAST_GPU=1            # Faster model loading
```

## Batching & concurrency

SGLang automatically batches concurrent requests for GPU efficiency. The backend sends
requests without client-side throttling -- SGLang's server-side scheduler handles queuing
and batching.

Key settings in config files:

- `max_running_requests` -- max concurrent GPU inferences (default 8). Excess requests queue.
- `mem_fraction_static` -- fraction of VRAM to allocate. Set to 0.40 to leave room for both servers on one GPU.
