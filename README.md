# Lecture Brain

Lecture Brain is a backend service for analyzing, chunking, and querying educational material (PDFs, Videos, and Text). It uses state-of-the-art AI parsing, embeddings, and chat completions to create an interactive learning experience.

## Project Overview
Lecture Brain allows students or educators to create **Subjects** and **Lectures**. Each Lecture can ingest multiple **Sources** (e.g., a PDF of lecture slides, a YouTube video of the lecture, or raw text notes). The system extracts text from these sources, cleans, chunks, and vectorizes it. 

The Inference Engine then enables students to chat with the material, ask for concept explanations, or generate quizzes. The AI is strictly grounded in the ingested material using an advanced RAG (Retrieval-Augmented Generation) pipeline that combines semantic chunk search with a global "Knowledge Card" summary over the lecture.

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend Framework | FastAPI + Uvicorn | Async REST API |
| Database | MongoDB Atlas | Document storage + Vector Search |
| ODM | Beanie 1.25.0 | Async MongoDB object mapper |
| DB Driver | Motor 3.3.2 | Async MongoDB driver (pinned with PyMongo <4.9) |
| Core Driver | PyMongo <4.9.0 | Required for Motor 3.3.2 compatibility |
| Vector Search | MongoDB Atlas `$vectorSearch` | Semantic chunk retrieval |
| LLM | OpenAI `gpt-4o-mini` | Q&A, explain, quiz, knowledge card generation |
| Embeddings | OpenAI `text-embedding-3-small` | Vectors for semantic search |
| PDF Parsing | PyMuPDF (`fitz`) | Text extraction from PDFs |
| Video Download | yt-dlp | Download video + extract subtitles |
| Audio Transcription | OpenAI Whisper | Speech-to-text for videos without subtitles |
| Authentication | python-jose + passlib/bcrypt | JWT tokens + password hashing |
| Config | pydantic-settings + python-dotenv | Environment variable management |
| Containerization | Docker + docker-compose | Reproducible deployment |
| Optional (Phase 6) | pdf2image + pytesseract | OCR fallback for image-based PDFs |
| Optional (Phase 7) | opencv-python + pytesseract + Pillow | Frame extraction + OCR for videos |
| System Dependency | libgl1 | OpenGL support for OpenCV |

---

## API Endpoints Reference

### 1. Authentication
- **POST `/auth/register`**: Register a new user. Body: `{ "email": "...", "password": "..." }`
- **POST `/auth/login`**: Login to receive an access token. Form-data: `username=` and `password=`

### 2. Subjects and Lectures
*(Require `Authorization: Bearer <token>`)*

- **POST `/subjects/`**: Create a subject. Body: `{ "name": "Math", "description": "..." }`
- **GET `/subjects/`**: List all user's subjects.
- **GET `/subjects/{id}`**: Get a specific subject.
- **DELETE `/subjects/{id}`**: Delete a subject and cascade delete all its lectures.

- **POST `/lectures/`**: Create a lecture under a subject. Body: `{ "title": "...", "description": "...", "subject_id": "..." }`
- **GET `/lectures/subject/{id}`**: List lectures by subject.
- **GET `/lectures/{id}`**: Get a specific lecture.
- **GET `/lectures/{id}/status`**: Polling endpoint to check ingestion processing status. Returns: `{ "lecture_id": "...", "status": "processing/completed/failed" }`
- **DELETE `/lectures/{id}`**: Delete a lecture and its data.

### 3. Knowledge Ingestion Pipeline
*(Require `Authorization: Bearer <token>`)*

- **POST `/knowledge/upload_text/{lecture_id}`**: Upload raw text. Body: `{ "text": "..." }`
- **POST `/knowledge/upload_pdf/{lecture_id}`**: Upload a PDF file. Form Data: `file`
- **POST `/knowledge/upload_video/{lecture_id}`**: Process a YouTube/Video URL. Body: `{ "url": "https://youtube.com/...", "extract_frames": false }`

### 4. AI Inference
*(Require `Authorization: Bearer <token>`)*

- **POST `/ai/chat`**: Chat with the AI tutor based on lecture context, maintaining history.
  - Body: `{ "message": "...", "lecture_id": "...", "history": [{"role": "user", "content": "..."}] }`
- **POST `/ai/explain`**: Get a detailed explanation of a specific concept.
  - Body: `{ "concept": "...", "lecture_id": "..." }`
- **GET `/ai/summary/{lecture_id}`**: Get the structured Knowledge Card summary.
- **POST `/ai/quiz/{lecture_id}`**: Generate a 5-question multiple choice quiz.

---

## Running Locally (Without Docker)

```bash
# 1. Clone the repo
git clone <repo-url>
cd lecture_brain

# 2. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file (see Environment Variables section)

# 5. Run the development server
uvicorn app.main:app --reload

# 6. Open API docs
# http://127.0.0.1:8000/docs
```

---

## Running with Docker

Two configurations are available.

### Production Mode
The image is fully self-contained. Code is baked into the image, no volume mounts.

```bash
# Build and run
docker-compose up --build -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

> **Access the API:** `http://localhost:8002/docs`
>
> The container runs on port `8000` internally, but `docker-compose.yml` maps it to **`8002`** on your host. There is no conflict — other local services running on `8000` are unaffected.

### Development Mode (fast iteration, no full rebuild needed)
The `docker-compose.dev.yml` override mounts your local `./app` directory into the container and enables `--reload`. Any code change you save locally is picked up **immediately** without rebuilding the image.

```bash
# First-time setup (build the image once)
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up --build

# After the first build, subsequent runs skip the rebuild:
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Stop
docker-compose -f docker-compose.yml -f docker-compose.dev.yml down
```

> **Access the API:** `http://localhost:8002/docs` (same port mapping as production)

> [!TIP]
> When do you need `--build` again? Only when you change `requirements.txt` or the `Dockerfile` itself (e.g. new system package). Regular `.py` file edits never need a rebuild in dev mode.

---

## Environment Variables

Create a `.env` file in the root directory:

```ini
# MongoDB
MONGO_URI=mongodb+srv://<user>:<password>@cluster0...
DB_NAME=lecture_brain

# OpenAI
OPENAI_API_KEY=sk-...

# Auth
SECRET_KEY=your-long-random-secret-string
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Optional (Phase 7)
FRAME_INTERVAL_SECONDS=5
```

---

## MongoDB Atlas Setup

Step-by-step to configure the Vector Search Index:
1. Go to MongoDB Atlas dashboard → Database → **Atlas Search**
2. Click **Create Search Index** → **JSON Editor**
3. Target: `lecture_brain` database, `knowledge_chunks` collection
4. Index name: `vector_index`
5. Paste this config:

```json
{
  "fields": [
    {
      "numDimensions": 1536,
      "path": "embedding",
      "similarity": "cosine",
      "type": "vector"
    },
    {
      "path": "lecture_id",
      "type": "filter"
    }
  ]
}
```

---

## Optional Features

**OCR Fallback for Image-Based PDFs (Phase 6 - Future)**
- Automatically activated when PyMuPDF detects less than 100 characters of text in a PDF
- Requires `tesseract` and `poppler` installed on the server
- No action needed from the user

**Video Frame Extraction + OCR (Phase 7 - Future)**
> ⚠️ This is a heavy optional feature. Enable only when needed.

- Set `extract_frames: true` in the `/knowledge/upload_video/{id}` request body
- Extracts one frame every `FRAME_INTERVAL_SECONDS` seconds
- Runs OCR on frames that contain significant text
- Processing time estimates:
  - 30 min video → 5–15 minutes additional processing
  - 1 hour video → 15–35 minutes additional processing
  - 2 hour video → 30–70 minutes additional processing
- Requires `opencv-python`, `Pillow`, `pytesseract` installed
- The `warning` field in the upload response will confirm this is active

---

## Architecture Overview

Lecture Brain is composed of two core engines:

**Ingestion Engine (`app/knowledge/`):**
> Handles all file processing. When a source is uploaded, a background task extracts text directly (PyMuPDF) or transcribes it depending on the source format (Whisper, YouTube Captions). It cleans the text, chunks it, generates vector embeddings via OpenAI, stores chunks in MongoDB, and triggers the `KnowledgeCard` generation logic to construct a global representation of the source.

**Inference Engine (`app/ai/`):**
> Handles all student interactions. When a student chats, explains, or takes a quiz, the system embeds the query, runs `$vectorSearch` to find the top-5 most relevant chunks, fetches the Knowledge Card summary, and injects everything into a structured prompt for OpenAI language models. This dual retrieval approach (macro summary + micro chunks) ensures the AI never hallucinates while still having complete context.
