#!/bin/bash
# Benchmark sprite generation timing
# Usage: bash bench.sh <label>
# Runs a warm-up then 5 sprites, outputs CSV rows

LABEL="$1"
PROMPTS=("fire sword" "wooden barrel" "robot" "campfire" "treasure chest")

# Warm-up run (primes BiRefNet)
make cli-sprite PROMPT="warm up test" OUT="sprite_comparison/warmup.png" 2>&1 > /dev/null

for prompt in "${PROMPTS[@]}"; do
  safe=$(echo "$prompt" | tr ' ' '_')
  output=$(make cli-sprite PROMPT="$prompt" OUT="sprite_comparison/bench_${safe}.png" 2>&1)
  
  llm=$(echo "$output" | grep "llm create" | awk '{print $3}' | tr -d 's')
  img=$(echo "$output" | grep "image gen" | awk '{print $3}' | tr -d 's')
  bgr=$(echo "$output" | grep "bg removal" | awk '{print $3}' | tr -d 's')
  total=$(echo "$output" | grep "total" | awk '{print $2}' | tr -d 's')
  
  echo "${LABEL},${prompt},${llm},${img},${bgr},${total}"
done
