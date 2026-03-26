# Local FLUX Server (SGLang)

Serves FLUX.2 Klein 4B locally on GPU via SGLang, exposing an OpenAI-compatible image generation API.

## Install

```bash
pip install 'sglang[all]'
```

## Run

```bash
# From project root:
sglang serve --config services/sglang/config.yaml

# With optimizations:
SGLANG_CACHE_DIT_ENABLED=true sglang serve --config services/sglang/config.yaml --enable-torch-compile

# Or use Makefile:
make serve-gpu          # start SGLang in background
make wait-gpu           # wait until ready
make serve-all          # start SGLang + backend together
make stop-gpu           # stop SGLang
```

First run downloads model weights from HuggingFace. Subsequent runs use cache.

## Alternative models

Edit `config.yaml` or pass `--model-path`:

```bash
sglang serve --model-path black-forest-labs/FLUX.2-klein-4B --port 5100        # bf16
sglang serve --model-path black-forest-labs/FLUX.2-klein-9B --port 5100        # 9B (non-commercial)
sglang serve --model-path black-forest-labs/FLUX.1-schnell --port 5100         # FLUX.1
```

## Environment variables for Blackwell RTX 6000 Pro

```bash
SGLANG_ENABLE_JIT_DEEPGEMM=0     # Required — DeepGemm JIT not supported on SM120
SGLANG_CACHE_DIT_ENABLED=true     # Up to 1.69x speedup
SGLANG_SET_CPU_AFFINITY=1         # Performance
SAFETENSORS_FAST_GPU=1            # Faster model loading
```

## Configure Makeshift backend

```env
IMAGE_BACKEND=local
LOCAL_IMAGE_URL=http://127.0.0.1:5100
LOCAL_IMAGE_MODEL=black-forest-labs/FLUX.2-klein-4b-fp8
```

## Batching & concurrency

SGLang automatically batches concurrent requests for GPU efficiency. The backend sends
requests without client-side throttling — SGLang's server-side scheduler handles queuing
and batching.

Key settings in `config.yaml`:

- `max_running_requests` — max concurrent GPU inferences (default 8). Excess requests queue.
- `mem_fraction_static` — fraction of VRAM to allocate (default 0.45). Set to leave room
  for a second SGLang instance (e.g. local LLM) on the same GPU.

For GPUs with more VRAM, raise `mem_fraction_static` and `max_running_requests` accordingly.
