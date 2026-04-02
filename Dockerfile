FROM python:3.11-slim

WORKDIR /app

# ── Layer 1: System packages (cached until Dockerfile changes) ──────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    openssl \
    tesseract-ocr \
    poppler-utils \
    libgl1 \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Layer 2: CPU-only PyTorch (prevents openai-whisper pulling CUDA/GPU ~2GB) 
# This layer is cached as long as the torch version pin doesn't change.
RUN pip install --no-cache-dir \
    torch==2.2.2 torchaudio==2.2.2 \
    --index-url https://download.pytorch.org/whl/cpu

# ── Layer 3: Python dependencies (cached until requirements.txt changes) ────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Layer 4: Application code (only layer that changes on each code edit) ───
COPY . .

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
