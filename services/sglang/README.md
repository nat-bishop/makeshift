# Local LLM Server (SGLang)

Serves Qwen 3.5 locally on GPU via SGLang, exposing an OpenAI-compatible chat completions API for structured object generation.

## Install

```bash
pip install 'sglang[all]'
```

## Run

```bash
# From project root:
sglang serve --config services/sglang/llm-config.yaml

# Or use Makefile:
make serve-llm          # start SGLang LLM in background
make wait-llm           # wait until ready
make stop-llm           # stop SGLang LLM
```

First run downloads model weights from HuggingFace. Subsequent runs use cache.

## Alternative models

Edit `llm-config.yaml` or pass `--model-path`:

```bash
sglang serve --model-path Qwen/Qwen3.5-14B --port 5200          # 14B (needs ~32GB VRAM)
sglang serve --model-path Qwen/Qwen3.5-32B --port 5200          # 32B (needs ~70GB VRAM)
```

## Environment variables for Blackwell RTX 6000 Pro

```bash
SGLANG_ENABLE_JIT_DEEPGEMM=0     # Required -- DeepGemm JIT not supported on SM120
SGLANG_CACHE_DIT_ENABLED=true     # Up to 1.69x speedup
SGLANG_SET_CPU_AFFINITY=1         # Performance
SAFETENSORS_FAST_GPU=1            # Faster model loading
```

## Configure Makeshift backend

```env
LLM_MODEL=Qwen/Qwen3.5-7B
LOCAL_LLM_URL=http://127.0.0.1:5200/v1
```
