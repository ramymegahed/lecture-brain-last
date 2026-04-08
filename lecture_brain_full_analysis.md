# Lecture Brain — Complete Project Analysis

---

## 1. Overall Architecture

Lecture Brain is an **AI-powered Educational SaaS backend** built with **FastAPI** (Python). The system's core purpose is to ingest lecture content (PDFs, videos, raw text) and make it queryable by students through a natural-language AI assistant, leveraging a **Retrieval-Augmented Generation (RAG)** pipeline.

```
┌──────────────────────────────────────────────────────────────────┐
│                         CLIENTS (Frontend / API Consumer)        │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ HTTPS / REST
┌────────────────────────────────▼─────────────────────────────────┐
│                      FastAPI Application (main.py)               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ │
│  │  /auth   │ │/subjects │ │/lectures │ │/knowledge│ │  /ai  │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └───────┘ │
└───────────┬─────────────────────────┬────────────────────────────┘
            │ (sync CRUD via Beanie)  │ (Background Tasks: chunking, embedding)
┌───────────▼─────────────────────────▼────────────────────────────┐
│               MongoDB Atlas                                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                         │
│  │  users   │ │ subjects │ │ lectures │                         │
│  └──────────┘ └──────────┘ └──────────┘                         │
│  ┌────────────────────┐ ┌───────────────────┐                    │
│  │  knowledge_chunks  │ │  knowledge_cards  │                    │
│  │  (+ Vector Index)  │ │  (global context) │                    │
│  └────────────────────┘ └───────────────────┘                    │
└──────────────────────────────────────────────────────────────────┘
            │
┌───────────▼──────────────────────────────────────────────────────┐
│               OpenAI API                                          │
│   text-embedding-ada-002 (embeddings) + gpt-4o-mini (inference)  │
└──────────────────────────────────────────────────────────────────┘
```

Key architectural principles:
- **Async-first**: All I/O — DB queries, OpenAI calls, file ops — is non-blocking using Python's `asyncio`.
- **Background processing**: Heavy workloads (PDF parsing, transcription, embedding) are offloaded to FastAPI's `BackgroundTasks` so upload endpoints return immediately.
- **Modular separation**: Routes, business logic, models, schemas, and AI functions are in distinct directories—no concerns bleed across boundaries.
- **Docker-first deployment**: The project ships with a `Dockerfile` and `docker-compose.yml` for both dev and production environments.

---

## 2. File-by-File Breakdown

### Root Level

| File | Role |
|---|---|
| `Dockerfile` | Multi-stage Docker image. Installs system deps (ffmpeg, tesseract), pins CPU-only PyTorch, then installs Python requirements. Exposes port 8000 and runs uvicorn. |
| `docker-compose.yml` | Minimal production compose — launches the FastAPI service. |
| `docker-compose.dev.yml` | Development  compose with live-reload settings. |
| `.dockerignore` | Excludes venv, uploads, and cache dirs from the Docker build context. |
| `requirements.txt` | Python dependency manifest (pinned to avoid conflicts — see §5). |
| `.env` | Environment variable store (`MONGO_URI`, `OPENAI_API_KEY`, `SECRET_KEY`, etc.). **Never committed to git.** |
| `README.md` | Project documentation. |

---

### `app/main.py` — Application Entry Point

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()   # connect MongoDB + register Beanie models
    yield
    await close_db()  # graceful shutdown
```

- Creates the FastAPI app instance and attaches the DB lifecycle using the modern `lifespan` context manager pattern.
- Registers all 5 routers: `auth`, `subjects`, `lectures`, `knowledge`, `ai`.
- Applies permissive CORS (`allow_origins=["*"]`) — this must be locked down before production.
- Defines a simple health-check root endpoint `GET /`.

---

### `app/database/mongodb.py` — Database Client & Vector Search

The single most important infrastructure file. It does three things:

1. **Connection**: Creates an `AsyncIOMotorClient` pointing to MongoDB Atlas with TLS enabled and a 10-second server selection timeout.
2. **ODM Init**: Calls `init_beanie()`, registering all five document models. This is what allows the ORM-style `User.find_one()` calls throughout the codebase.
3. **`vector_search()` function**: This is the RAG retrieval engine. Since Beanie's query API doesn't support the `$vectorSearch` aggregation stage, it drops down to the raw `motor` client to run an Atlas Vector Search pipeline.

```python
"$vectorSearch": {
    "index":        "vector_index",   # Atlas Search Index name
    "path":         "embedding",      # field holding the float[] vector
    "queryVector":  query_embedding,  # 1536-dim float[] from the user question
    "numCandidates": limit * 10,      # ANN candidates pool (10x for recall)
    "limit":        limit             # top-k results to return
}
```

---

### `app/auth/jwt.py` — Token & Password Utilities

- Reads `SECRET_KEY`, `ALGORITHM`, and `ACCESS_TOKEN_EXPIRE_MINUTES` from env.
- Uses `passlib` with **bcrypt** for password hashing.
- Uses **python-jose** to generate and sign HS256 JWT tokens.
- The `create_access_token()` function encodes the user's email as the `sub` (subject) claim.

### `app/auth/dependencies.py` — Auth Middleware

- Defines `get_current_user()`: a FastAPI dependency that reads the `Bearer` token from the `Authorization` header, decodes the JWT, and fetches the corresponding `User` from MongoDB.
- Defines `get_current_active_user()`: wraps `get_current_user()` and additionally checks the `is_active` flag. This is injected into every protected endpoint via `Depends(get_current_active_user)`.

---

### `app/models/` — Database Document Definitions (Beanie ODM)

All models inherit from `beanie.Document`, which maps them to MongoDB collections.

| File | Collection | Key Fields |
|---|---|---|
| `user.py` | `users` | `email` (unique indexed), `hashed_password`, `is_active` |
| `subject.py` | `subjects` | `name`, `owner: Link[User]` |
| `lecture.py` | `lectures` | `title`, `subject: Link[Subject]`, `sources: List[LectureSource]`, `status` |
| `knowledge.py` | `knowledge_chunks` | `lecture: Link[Lecture]`, `lecture_id: str`, `text`, `page_number`, `embedding: List[float]` |
| `knowledge_card.py` | `knowledge_cards` | `lecture: Link[Lecture]`, `summary`, `key_points`, `concepts`, `important_details`, `examples` |

> **Note on `lecture_id` duplication in `KnowledgeChunk`**: The `embedding: Link[Lecture]` field is a Beanie reference (ObjectId). For the raw `$vectorSearch` pipeline to filter by lecture, MongoDB requires the filter to be on a simple, indexed scalar field. The `lecture_id: str` field serves this exact purpose.

---

### `app/schemas/` — API Request/Response Validators (Pydantic)

These are pure data contracts with no DB interaction. They validate incoming JSON and shape outgoing responses.

| File | Schemas Defined |
|---|---|
| `auth_schema.py` | `UserCreate`, `UserResponse`, `Token`, `TokenData` |
| `subject_schema.py` | `SubjectCreate`, `SubjectResponse` |
| `lecture_schema.py` | `LectureCreate`, `LectureResponse`, `LectureUpdate` |
| `knowledge_schema.py` | `UploadResponse`, `UploadTextRequest`, `UploadVideoRequest` |
| `ai_schema.py` | `ChatRequest`, `ChatResponse`, `ExplainRequest`, `ExplainResponse`, `SummaryResponse`, `QuizQuestion`, `QuizOption`, `QuizResponse` |

---

### `app/routes/` — API Endpoint Routers

| File | Prefix | Endpoints |
|---|---|---|
| `auth_routes.py` | `/auth` | `POST /register`, `POST /login`, `GET /me` |
| `subject_routes.py` | `/subjects` | `POST /`, `GET /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}` |
| `lecture_routes.py` | `/lectures` | `POST /`, `GET /subject/{id}`, `GET /{id}`, `GET /{id}/status`, `DELETE /{id}` |
| `knowledge_routes.py` | `/knowledge` | `POST /upload_pdf/{lecture_id}`, `POST /upload_video/{lecture_id}`, `POST /upload_text/{lecture_id}` |
| `ai_routes.py` | `/ai` | `POST /chat`, `POST /explain`, `GET /summary/{lecture_id}`, `POST /quiz/{lecture_id}` |

Every route except `/auth/register` and `/auth/login` requires a valid JWT (`Depends(get_current_active_user)`). Authorization is ownership-based: a user can only access subjects and lectures they own (checked by `subject.owner.ref.id == current_user.id`).

The `lecture_routes.py` includes a cascade delete helper `delete_lecture_data()` that removes all `KnowledgeChunk` and `KnowledgeCard` documents before deleting the parent `Lecture`.

---

### `app/knowledge/` — Ingestion Pipeline

#### `chunking.py`
- `clean_text()`: Normalizes whitespace and collapses excessive newlines using regex.
- `recursive_character_text_splitter()`: A custom implementation that splits text by `\n\n`, `\n`, `. `, and spaces, producing chunks of ~1000 characters with 200-character overlap to preserve context across chunk boundaries.
- `chunk_document()`: Iterates over pages and produces a flat list of `{text, page_number}` objects ready for embedding.

#### `embeddings.py`
- `get_embeddings(texts)`: Sends a list of text strings to OpenAI's `text-embedding-ada-002` model in a single batch call. Returns a list of 1536-dimensional float vectors. Each vector maps semantically — similar texts produce vectors that are geometrically close (cosine similarity).

#### `upload_pdf.py`
- `process_pdf_background()`: The full PDF ingestion pipeline:
  1. Opens the file with **PyMuPDF** (`fitz.open()`).
  2. Extracts text page-by-page, building both a per-page list and a `full_text` string.
  3. Chunks each page's text while preserving `page_number`.
  4. Sends chunks to OpenAI for embeddings in batches of 100.
  5. Saves all `KnowledgeChunk` documents to MongoDB with `insert_many()`.
  6. Calls `generate_and_save_knowledge_card()` with the first 15,000 characters of the full text.
  7. Updates the `Lecture.status` to `completed` or `failed`.

#### `upload_text.py`
- Identical pipeline to `upload_pdf.py`, but skips extraction and works directly with the raw string submitted in the request body. The text is split into page-1 pseudo page entries.

#### `video_processor.py`
- `process_video_background()`: The most complex ingestion task.
  1. First attempts **subtitle extraction** via `yt-dlp` (downloads `.en.vtt` subtitle tracks — fast, high quality).
  2. Falls back to a full **audio download + Whisper transcription** pipeline if no subtitles are found.
  3. Runs the blocking download/transcription in a thread via `asyncio.to_thread()` to avoid blocking the event loop.
  4. Feeds the resulting transcript text into the same chunk → embed → save → knowledge_card flow.
- `extract_frames: bool` is accepted as a parameter (already in the API schema) but the actual frame extraction logic is noted as a potential future feature.

#### `knowledge_card.py`
- `generate_and_save_knowledge_card()`: Calls `gpt-4o-mini` with `response_format={"type": "json_object"}` (JSON mode) to extract a structured global summary from the document text.
- Intelligently handles updates: if a `KnowledgeCard` already exists for the lecture (e.g., after uploading a second PDF to the same lecture), it passes the existing card's data to the LLM with instructions to **merge** the new insights.
- Returns a `KnowledgeCard` Beanie document with: `summary`, `key_points`, `concepts`, `important_details`, `examples`.

---

### `app/ai/` — Inference & Reasoning Engine

#### `prompts.py`
Centralizes all system prompts as module-level constants to avoid scattering prompt engineering across business logic files.

| Prompt Constant | Used By | Purpose |
|---|---|---|
| `SYSTEM_PROMPT_ASK` | `ask.py` | Strict context-based Q&A. Instructs the LLM to answer ONLY from the provided context. |
| `SYSTEM_PROMPT_EXPLAIN` | `explain.py` | Deep concept explanation using lecture context. |
| `SYSTEM_PROMPT_QUIZ` | `quiz.py` | Generates a 5-question MCQ JSON array. Strict JSON-only output instruction. |

#### `ask.py` — The RAG Core
The most critical AI file. Contains two key functions:

- **`build_context(lecture_id, query)`**: Hybrid context retrieval.
  1. Fetches the `KnowledgeCard` (global context — big picture).
  2. Embeds the user's query using `get_embeddings()`.
  3. Calls `vector_search()` to find the top 5 semantically relevant chunks.
  4. Returns: `(global_context_str, retrieved_chunks_str, sources_list)`.

- **`generate_answer(message, lecture_id, user_id, history)`**: Full chat completion.
  1. Validates lecture ownership.
  2. Calls `build_context()`.
  3. Builds a multi-turn message array: `[system_prompt, ...history[-6:], user_message]`.
  4. Calls `gpt-4o-mini` at temperature 0.2 (very deterministic).
  5. Returns the answer text and source citations.

#### `explain.py`
Same pattern as `ask.py` — builds hybrid context, injects `SYSTEM_PROMPT_EXPLAIN` with the target concept, and calls `gpt-4o-mini`. Returns a detailed explanation string.

#### `quiz.py`
Uses only the `KnowledgeCard` (global context) — no vector search. Sends `SYSTEM_PROMPT_QUIZ` to `gpt-4o-mini` at temperature 0.3. Parses the returned JSON string into typed `QuizQuestion` and `QuizOption` Pydantic objects. Handles the common issue of LLMs wrapping JSON in markdown code fences (strips ` ```json ` wrappers before parsing).

#### `summary.py`
A lightweight read: just fetches the pre-generated `KnowledgeCard` from MongoDB. No LLM call needed at retrieval time since the card was generated during ingestion.

---

## 3. Database Structure & Connection

### Collections

```
lecture_brain (database)
├── users
│   └── { _id, email (unique), hashed_password, is_active, created_at }
├── subjects
│   └── { _id, name, description, owner → users._id, created_at }
├── lectures
│   └── { _id, title, description, subject → subjects._id,
│           sources: [{ type, url, status, error }],
│           status, created_at }
├── knowledge_chunks
│   └── { _id, lecture → lectures._id, lecture_id (str copy),
│           text, page_number,
│           embedding: [float × 1536]  ← VECTOR INDEXED }
└── knowledge_cards
    └── { _id, lecture → lectures._id (1:1),
            summary, key_points, concepts, important_details, examples,
            created_at }
```

### Relationship Diagram

```
User ──< Subject ──< Lecture ──< KnowledgeChunk (many)
                           └── KnowledgeCard (one)
```

All cross-document relationships use Beanie's `Link[T]` type, which stores a MongoDB `DBRef` (a typed `{$ref, $id}` pointer). When you `.fetch_link()` or use the `.ref.id` accessor, Beanie resolves these to the correct document.

### Vector Search Index
A MongoDB Atlas Search index named **`vector_index`** must be manually created on the `knowledge_chunks` collection with the following configuration:

```json
{
  "mappings": {
    "dynamic": false,
    "fields": {
      "embedding": {
        "type": "knnVector",
        "dimensions": 1536,
        "similarity": "cosine"
      },
      "lecture_id": { "type": "string" }
    }
  }
}
```

> [!IMPORTANT]
> This index cannot be created programmatically through Beanie or Motor — it must be done via the MongoDB Atlas UI or Atlas CLI before the RAG features will work.

---

## 4. RAG Implementation

The RAG pattern is split across two phases: **Ingestion** (at upload time) and **Retrieval** (at query time).

### Phase A — Ingestion (Happens in Background)

```
User uploads PDF/Video/Text
        │
        ▼
knowledge_routes.py → BackgroundTasks.add_task(process_*_background)
        │
        ▼
┌── Extract Text ──────────────────────────────────────────────────┐
│   PDF    → PyMuPDF (fitz) — extracts text per page              │
│   Video  → yt-dlp subtitles → or Whisper transcription          │
│   Text   → raw string from request body                          │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
chunking.py → 1000-char chunks with 200-char overlap + page_number
        │
        ▼
embeddings.py → OpenAI text-embedding-ada-002 → List[List[float]]
        │
        ▼
KnowledgeChunk.insert_many(chunks) → MongoDB knowledge_chunks
        │                             (stored with embedding vector)
        ▼
knowledge_card.py → gpt-4o-mini (JSON mode)
                 → KnowledgeCard.insert() or .save() (upsert/merge)
```

### Phase B — Retrieval & Generation (Happens per Request)

```
POST /ai/chat  {message, lecture_id, history}
        │
        ▼
ask.py::generate_answer()
        │
        ├─── 1. Ownership check (User → Subject → Lecture)
        │
        ├─── 2. build_context()
        │         │
        │         ├── KnowledgeCard.find_one() → global_context string
        │         │       (summary, key_points, concepts, examples)
        │         │
        │         ├── get_embeddings([query]) → query_vector [float×1536]
        │         │
        │         └── vector_search(query_vector, limit=5, lecture_id)
        │               │
        │               └── MongoDB $vectorSearch aggregation
        │                     → top-5 KnowledgeChunks by cosine similarity
        │                     → returns  {text, page_number, score}
        │
        ├─── 3. Build system prompt (SYSTEM_PROMPT_ASK)
        │         {global_context} + {retrieved_chunks with page refs}
        │
        ├─── 4. Build message array
        │         [system_prompt, ...history[-6:], user_message]
        │
        └─── 5. gpt-4o-mini.chat.completions.create(temp=0.2)
                    → answer text
                    → sources ["Page 5 (Similarity: 0.91)", ...]
```

**Why Hybrid Context?**
Using only vector-retrieved chunks risks missing the big picture when chunks are too granular. The `KnowledgeCard` (always included) grounds the LLM in the lecture's overarching themes, preventing hallucinations about unrelated topics while ensuring the LLM can reason about concepts that might not appear in the top-5 chunks.

---

## 5. Important Dependencies

| Library | Version | Purpose |
|---|---|---|
| `fastapi` | latest | Async web framework |
| `uvicorn` | latest | ASGI server |
| `motor` | **3.3.2** | Async MongoDB driver (pinned — newer versions broke Beanie's connection lifecycle) |
| `beanie` | **1.25.0** | Async MongoDB ODM built on Motor (pinned for Motor compatibility) |
| `pymongo` | **<4.9.0** | Motor's underlying sync driver (pinned for stability) |
| `pydantic` | latest | Data validation / serialization |
| `python-dotenv` | latest | Loads `.env` file into `os.environ` |
| `openai` | latest | Python SDK for OpenAI APIs (embeddings + chat completions) |
| `PyMuPDF` | latest | Fast PDF text extraction (`import fitz`) |
| `passlib` | **1.7.4** | Password hashing framework |
| `bcrypt` | **3.2.2** | Bcrypt backend for passlib (pinned — newer versions have API-breaking changes) |
| `python-jose[cryptography]` | latest | JWT encoding/decoding |
| `python-multipart` | latest | Required by FastAPI for `UploadFile` / form data |
| `httpx` | latest | Async HTTP client (used internally by OpenAI SDK) |
| `email-validator` | latest | Validates `EmailStr` fields in Pydantic |
| `yt-dlp` | latest | Downloads YouTube/web video audio and subtitles |
| `openai-whisper` | latest | Local Whisper speech-to-text model (loads `base` model by default) |
| `torch` / `torchaudio` | **2.2.2 (CPU)** | Whisper dependency — pinned to CPU-only build to avoid ~2GB CUDA download |

---

## 6. Potential Improvements & Considerations

### 🔴 Production-Critical Issues

> [!CAUTION]
> These must be addressed before any production deployment.

1. **CORS is wide open**: `allow_origins=["*"]` in `main.py`. This should be restricted to specific frontend domains in production.
2. **File storage is local only**: Uploaded PDFs are saved to a local `uploads/` directory. In a containerized/multi-instance or cloud deployment, these files are ephemeral and will be lost on restart. **Fix**: Use cloud object storage (AWS S3, GCS) and store the `s3://` URL instead of a local path.
3. **No Whisper model caching**: `whisper.load_model("base")` is called inside `_download_and_transcribe()` every time a video is processed. Loading the model is slow (~10 seconds) and memory-intensive. **Fix**: Load the model once at application startup and store it in a module-level variable.
4. **Uploads directory is not excluded from the Docker build COPY**: The `COPY . .` instruction in the Dockerfile will include any files in `uploads/` at build time. This should be added to `.dockerignore`.

### 🟡 Architecture & Scalability

> [!WARNING]
> These will become significant pain points at scale.

5. **`BackgroundTasks` is not a real queue**: FastAPI's `BackgroundTasks` runs tasks in the same process as the web server. Long-running video processing (potentially 10-35+ minutes) will tie up worker threads. **Fix**: Replace with a proper task queue like **Celery + Redis** or **ARQ**, with separate worker processes.
6. **`OpenAIClient` is instantiated per-request**: In `ask.py`, `quiz.py`, `explain.py`, and `knowledge_card.py`, `AsyncOpenAI(...)` is constructed each time a function is called. **Fix**: Create a single, module-level shared client instance.
7. **Chunking strategy is page-scoped**: `chunk_document()` processes each page independently. A table or concept that spans a page boundary will be split in two, losing cross-page context. Consider a document-level chunking pass before splitting by page.
8. **No re-indexing strategy**: If a lecture already has `KnowledgeChunk` records and a user uploads a second PDF to the same lecture, new chunks are appended without removing old ones. The `KnowledgeCard` is correctly merged, but old chunks remain. This is fine for multi-source lectures, but there is no "replace" option.

### 🟢 Code Quality & Developer Experience

9. **Logging is `print()`-based**: All error handling uses `print(f"Error: {e}")`. This should be replaced with Python's `logging` module (with structured JSON logs in production).
10. **`chunking.py` TODO comment**: The code explicitly acknowledges that using **LangChain's `RecursiveCharacterTextSplitter`** would be better. The current custom implementation works but is less battle-tested for edge cases (e.g., very short pages, pages with only code, tables).
11. **Quiz uses only `KnowledgeCard`, not vector search**: `quiz.py` generates questions using only the global summary. This can result in repetitive or high-level questions. Adding a vector search step to pull diverse, specific chunks from across the lecture would improve quiz quality significantly.
12. **`lecture_id` stored as both `Link` and `str` in `KnowledgeChunk`**: This is an intentional workaround for the `$vectorSearch` filter (see §3). It works well, but it's worth documenting clearly to avoid confusion for new developers.
13. **No token budget management**: In `upload_pdf.py`, `full_text[:15000]` is used as a hard character cap for the Knowledge Card prompt. For very large PDFs this truncates significant portions. A smarter approach would be to take a distributed sample (first page, middle, last page) or summarize in chunks and merge.

---

## 7. Resolved Issues (Phase 1–3 Optimizations)

During the stabilization phase, several of the critical and architectural issues outlined above were resolved to prepare the backend for a production-ready graduation demo:

### Phase 1: Critical Fixes & Stability
*   **Shared OpenAI Client**: Created a module-level `AsyncOpenAI` singleton in `app/core/clients.py` instead of instantiating it per request (resolves #6).
*   **Whisper Caching & Audio Cleanup**: Upgraded to the `"small"` Whisper model and cached it using a lazy-loaded singleton. Wrapped audio parsing in a `try/finally` block and added an app startup sweep task to guarantee no `.mp3` orphaned files remain on disk (resolves #3 and #2 regarding video temporary audio).
*   **Zero-Disk PDF Processing**: Re-wrote the PDF pipeline to evaluate raw byte streams strictly in-memory using `PyMuPDF`, discarding the file context locally after parsing rather than saving it (resolves #2 regarding PDFs).

### Phase 2: Code Quality
*   **Centralized Logging**: Replaced all standard `print()` statements with standard Python `logging` to provide reliable stdout monitoring data for Docker environments (resolves #9).
*   **Schema Documentation**: Added strict Python docstrings for `KnowledgeChunk` explaining the DBRef/String duplication on `lecture_id` (resolves #12).

### Phase 3: Feature Enhancements
*   **Vector Search in Quizzes**: Re-engineered `quiz.py` to retrieve up to 10 context-heavy diverse chunks using `$vectorSearch` in addition to the `KnowledgeCard` global summary, ensuring detailed, nuanced MCQs (resolves #11).
*   **Smart Token Sampling**: Replaced the native `[:15000]` truncation with an intelligent `sample_document_text()` splitter that pulls 50% from the start, 25% from the middle, and 25% from the end (resolves #13).
*   **Document-Level Chunking**: Updated `chunking.py` to concat all pages into a complete string to avoid severing sentences across page breaks, matching them back to the correct metadata using a mathematical `bisect` logic mapping array (resolves #7).
*   **Re-Indexing Param**: Introduced an optional `?replace=true` query parameter for the ingestion endpoints allowing strict purging of prior chunks and cards (resolves #8).
