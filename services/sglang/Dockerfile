FROM lmsysorg/sglang:dev-cu13

# Install SGLang diffusion extra (includes diffusers, yunchang, etc.)
RUN cd /sgl-workspace/sglang && pip install --no-cache-dir -e "python[diffusion]" accelerate

COPY cache-dit-config.yaml /app/cache-dit-config.yaml
COPY server-config.yaml /app/server-config.yaml
