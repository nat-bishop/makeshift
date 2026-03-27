#!/bin/bash
set -e

CONVERTED_DIR="/root/.cache/huggingface/flux2-klein-4b-fp8-channel"

if [ ! -f "$CONVERTED_DIR/config.json" ]; then
    echo "=== FP8 conversion: FLUX.2-klein-4B transformer ==="

    # Resolve the cached BF16 transformer directory via huggingface_hub
    BF16_TRANSFORMER=$(python -c "
from huggingface_hub import snapshot_download
path = snapshot_download('black-forest-labs/FLUX.2-klein-4B', allow_patterns=['transformer/*'])
print(f'{path}/transformer')
")
    echo "BF16 source: $BF16_TRANSFORMER"

    python -m sglang.multimodal_gen.tools.convert_hf_to_fp8 \
        --model-dir "$BF16_TRANSFORMER" \
        --save-dir "$CONVERTED_DIR" \
        --strategy channel

    echo "=== FP8 conversion complete: $CONVERTED_DIR ==="
fi

exec sglang serve "$@"
