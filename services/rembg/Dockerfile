FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir --break-system-packages -r /app/requirements.txt

COPY server.py /app/server.py

WORKDIR /app
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "5150"]
