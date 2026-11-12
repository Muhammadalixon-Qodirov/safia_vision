# CPU image by default (works anywhere). For GPU, see the note in the README:
# switch the base image to an NVIDIA CUDA runtime and run with --gpus all.
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# models and videos are mounted in (see docker-compose.yml), not baked into the image.
# The 4-camera live demo with its web page on :8010 (same command as outside Docker).
CMD ["python", "run.py", "--config", "config/local.yaml", "--web", "--host", "0.0.0.0", "--port", "8010"]
