FROM python:3.11-slim

WORKDIR /app

# Prevents Python from writing .pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ── Layer 1: System packages ─────────────────────────────────────────────────
# ffmpeg: required by yt-dlp for audio extraction (MP3 postprocessor)
# curl, ca-certificates, openssl: HTTPS and health checks
# Removed: tesseract-ocr, poppler-utils, libgl1 (not used anywhere in codebase)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    openssl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 2: Python dependencies ─────────────────────────────────────────────
# NOTE: torch/torchaudio are intentionally NOT installed.
# We previously ran openai-whisper locally, which requires ~2 GB RAM for the
# 'small' model — 4× the Railway Free Tier limit (0.5 GB). We now use the
# OpenAI Whisper API (whisper-1) instead, which uses zero local RAM.
# Removing torch saves ~400 MB of Docker image size.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Layer 3: Application code ─────────────────────────────────────────────────
COPY . .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
