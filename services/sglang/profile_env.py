"""Read SGLang server config from model_profiles.toml for the active LLM_MODEL.

Prints KEY=VALUE lines suitable for shell eval or docker-compose env injection.
Used by `make llm-restart` so server flags live alongside sampling params.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

PROFILES_PATH = Path(__file__).resolve().parents[2] / "backend" / "app" / "model_profiles.toml"

# TOML key → docker-compose env var
SERVER_KEYS = {
    "mem_fraction_static": "LLM_MEM_FRACTION",
    "kv_cache_dtype": "LLM_KV_CACHE_DTYPE",
    "mamba_ssm_dtype": "LLM_MAMBA_DTYPE",
    "context_length": "LLM_CONTEXT_LENGTH",
}


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: profile_env.py <model-name>", file=sys.stderr)
        sys.exit(1)

    model = sys.argv[1]
    with PROFILES_PATH.open("rb") as f:
        profiles = tomllib.load(f)

    profile = profiles.get(model, profiles.get("default", {}))
    for toml_key, env_var in SERVER_KEYS.items():
        if toml_key in profile:
            print(f"{env_var}={profile[toml_key]}")


if __name__ == "__main__":
    main()
