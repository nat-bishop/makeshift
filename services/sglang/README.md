# SGLang Servers

Two SGLang instances run side-by-side on the same GPU:

| Server | Model | Port | Purpose |
|--------|-------|------|---------|
| FLUX | FLUX.2-klein-9B (float8 via cache-dit) | 5100 | Image generation (Docker) |
| LLM | Qwen/Qwen3.5-9B | 5200 | Object creation (PydanticAI agent) |

## Prerequisites

- Docker Desktop with WSL2 backend
- NVIDIA GPU driver installed (GPU passthrough is automatic with Docker Desktop)
- Verify: `docker run --rm --gpus all nvidia/cuda:13.0.1-base-ubuntu24.04 nvidia-smi`

## FLUX Image Server (Docker)

Both servers are managed via [honcho](https://honcho.readthedocs.io/) from the project root. See the root `Procfile.dev` for process definitions.

```bash
make dev-servers                   # start all servers (gpu + llm + api)
make dev-servers SERVICES="gpu api"  # start specific servers
make wait-gpu                      # wait until FLUX is ready
```

First run builds Docker image and downloads model (~45GB). Subsequent runs use cache.
Uses `--backend diffusers` with cache-dit torchao float8 quantization (~0.45s/image at 512x512).

Configure backend:
```env
IMAGE_BACKEND=local
LOCAL_IMAGE_URL=http://127.0.0.1:5100
LOCAL_IMAGE_MODEL=black-forest-labs/FLUX.2-klein-9B
HF_TOKEN=hf_...  # required for gated 9B model
```

## LLM Server (Qwen 3.5)

```bash
make dev-servers SERVICES="llm api"  # start LLM + backend
make wait-llm                      # wait until LLM is ready
```

Configure backend:
```env
LLM_MODEL=Qwen/Qwen3.5-9B
LOCAL_LLM_URL=http://127.0.0.1:5200/v1
```

### Alternative models

Edit the `llm` entry in `Procfile.dev` at the project root, or run directly:

```bash
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

The two servers handle concurrency differently:

- **LLM server** — SGLang continuously batches concurrent requests for GPU efficiency. The backend sends requests without client-side throttling; SGLang's scheduler handles queuing and batching. `max_running_requests` controls how many inferences run concurrently (default 8).
- **FLUX server** — Diffusion requests are processed **serially**. A single image generation saturates the GPU (multi-step denoising loop), so concurrent requests queue and wait. Throughput scales by adding GPU replicas, not by batching.

Key settings in config files:

- `max_running_requests` -- max concurrent GPU inferences. Meaningful for LLM; for FLUX it controls queue depth only.
- `mem_fraction_static` -- fraction of VRAM to allocate. Set to 0.40 to leave room for both servers on one GPU.
