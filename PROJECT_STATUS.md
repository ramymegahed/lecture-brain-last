# Lecture Brain — Full Project Status Analysis

---

## 8. Project Idea (My Understanding)

Lecture Brain is an **AI-powered academic assistant backend** for students.

The core idea:
- A student signs up, organizes their courses into **Subjects**, and creates **Lectures** under each subject.
- They upload their lecture material (PDF or video) to a lecture slot.
- The system processes that material in the background: extracts text, breaks it into chunks, generates vector embeddings, and creates a global "Knowledge Card" (a summary + key concepts).
- The student can then ask natural-language questions about a specific lecture, and the system retrieves the most relevant text chunks via vector search, combines them with the Knowledge Card, and feeds everything to an LLM to produce a grounded, lecture-specific answer.
- The AI only answers from the uploaded material — it won't hallucinate general knowledge; it stays within the lecture context.

This is a **RAG (Retrieval-Augmented Generation) SaaS backend** meant ultimately to compete in the EdTech space, with the video pipeline being a key differentiator (yet to be built).

---

## 1. Implementation Status Overview

### ✅ Fully Implemented

| Component | What's Done |
|---|---|
| **Authentication** | Register, Login (JWT), `/me` endpoint, password hashing (bcrypt), token validation middleware |
| **Subject Management** | Create, List all (user-scoped), Get by ID — with full ownership verification |
| **Lecture Management** | Create, List by subject, Get by ID — with full ownership cascade check |
| **PDF Upload & Ingestion** | File saved locally → `BackgroundTask` fired → PyMuPDF text extraction → chunking → batch embedding → MongoDB insert → Knowledge Card generation → lecture status updated |
| **Chunking Engine** | Custom recursive character splitter (1000 char chunks, 200 char overlap) preserving page-number metadata |
| **Embedding Generation** | OpenAI `text-embedding-ada-002`, async, batched in groups of 100 |
| **Knowledge Card Generation** | GPT-4o-mini reads first 15,000 chars of the doc → generates summary + key concepts → saved to DB |
| **Vector Search** | MongoDB Atlas `$vectorSearch` aggregation pipeline, filtered by `lecture_id`, returns top-5 chunks with scores |
| **RAG Q&A (`/ai/ask`)** | Fetches Knowledge Card + runs vector search → builds hybrid context → GPT-4o-mini answers with sources |
| **Concept Explanation (`/ai/explain`)** | Same `build_context()` pipeline, different prompt focused on explaining a concept |
| **Summary Retrieval (`/ai/summary/{id}`)** | Fetches pre-computed Knowledge Card directly |
| **Database Init** | Beanie ODM initialized with all 5 document models, Motor async client, proper lifespan handler |
| **CORS Middleware** | Configured (open in dev, noted for production tightening) |

---

### 🟡 Partially Implemented

| Component | What Exists | What's Missing |
|---|---|---|
| **Video Processing** | Route exists, file saved, BackgroundTask called | `process_video_background` is a **stub** — immediately sets status to `"failed"` and prints a message. No actual processing. |
| **Subject Routes** | Create, List, Get | No `PUT` (update) or `DELETE` endpoints |
| **Lecture Routes** | Create, List by subject, Get | No `PUT` (update) or `DELETE` endpoints |
| **Ownership Security on `/ai/*`** | Comment says ownership verified at route level | **The `/ai/ask` and `/ai/explain` routes do NOT verify that `current_user` owns the lecture being queried** — `user_id` is passed to `generate_answer()` but never actually checked inside it |
| **Chunking** | Works correctly | Custom implementation; acknowledged in code that LangChain's splitter would be better for production |
| **Knowledge Card** | Generated from first 15,000 chars only | Large documents will lose context past that limit; no chunked summarization strategy |

---

### ❌ Completely Missing

| What's Missing | Why It Matters |
|---|---|
| **Video pipeline** (download, frame extraction, OCR, audio extraction, Whisper transcription) | The entire video-to-knowledge flow does not exist |
| **YouTube/URL video ingestion** | No `yt-dlp` or similar. The route accepts a file upload, not a URL |
| **DELETE & UPDATE for Subjects/Lectures** | Users can't manage their data |
| **Cascade deletion** | Deleting a lecture should remove its `KnowledgeChunk` and `KnowledgeCard` documents |
| **Actual lecture ownership check in AI endpoints** | A user who knows another user's `lecture_id` can ask questions about their material |
| **Re-ingestion / update flow** | No way to re-process a lecture if it changes or fails partially |
| **Error/status polling endpoint** | No `/lectures/{id}/status` endpoint; the frontend can't know when processing finishes |
| **File storage beyond local disk** | Files saved to `uploads/` folder on server. No S3/cloud storage. `source_file_url` field exists but stores a local path |
| **Token refresh / logout** | JWT is stateless; no refresh token, no blacklist/logout system |
| **Rate limiting** | No protection against API abuse |
| **Input validation beyond Pydantic basics** | No max file size check, no content-type check for video format |
| **Tests** | No unit tests, no integration tests, no test configuration |
| **Logging** | Raw `print()` statements only — no structured logging (`loguru`, `logging` module) |
| **Celery / task queue** | Heavy background tasks (PDF processing) run in FastAPI's `BackgroundTasks` which is not persistent — if the server crashes mid-processing, the task is lost |
| **Frontend** | Backend only; no UI |

---

## 2. Technologies Used

| Layer | Technology | Version / Notes |
|---|---|---|
| **Web Framework** | FastAPI | Async, with Uvicorn |
| **Database** | MongoDB Atlas | Cloud-hosted |
| **ODM (Object-Document Mapper)** | Beanie | `1.25.0` — pinned for compatibility |
| **Async DB Driver** | Motor | `3.3.2` — pinned for Beanie compatibility |
| **Vector Search** | MongoDB Atlas Vector Search | `$vectorSearch` aggregation, 1536-dim cosine similarity |
| **LLM** | OpenAI `gpt-4o-mini` | For Q&A inference + Knowledge Card generation |
| **Embeddings** | OpenAI `text-embedding-ada-002` | 1536-dimensional vectors |
| **PDF Parsing** | PyMuPDF (`fitz`) | Page-by-page text extraction |
| **Authentication** | `python-jose` (JWT) + `passlib`/`bcrypt` | HS256 tokens, bcrypt hashing (pinned `1.7.4`/`3.2.2`) |
| **Data Validation** | Pydantic + `pydantic-settings` | Models and schemas |
| **Environment Config** | `python-dotenv` | `.env` file loading |
| **HTTP Client** | `httpx` | Listed in requirements; not actively used in current code |

**Notably Absent (not installed):**
- `yt-dlp` or `pytube` — for video URL downloading
- `Whisper` or `openai-whisper` — for audio transcription
- `ffmpeg-python` or `moviepy` — for frame/audio extraction
- `Pillow` / `pytesseract` — for OCR on frames
- `Celery` + `Redis/RabbitMQ` — for robust task queuing
- `boto3` — for S3 file storage

---

## 3. Technologies Used (Summary)

```
Backend:      FastAPI + Uvicorn
Database:     MongoDB Atlas (Motor async driver)
ODM:          Beanie 1.25.0
Auth:         JWT (python-jose) + bcrypt (passlib)
AI/LLM:       OpenAI (gpt-4o-mini + text-embedding-ada-002)
PDF:          PyMuPDF (fitz)
Video:        ❌ Not implemented
Config:       pydantic-settings + python-dotenv
```

---

## 4. End-to-End User Flow (Current State)

### Step 1 — User Registration
```
POST /auth/register  { email, password }
→ Checks email uniqueness
→ Hashes password with bcrypt
→ Inserts User document into MongoDB
→ Returns { id, email, is_active }
```

### Step 2 — User Login
```
POST /auth/login  { username (email), password }  [OAuth2 form]
→ Finds user by email
→ Verifies password hash
→ Creates JWT with { sub: email, exp: 30 min }
→ Returns { access_token, token_type: "bearer" }
```

### Step 3 — Create a Subject
```
POST /subjects/  { name, description }  [Bearer Token required]
→ JWT decoded → user identified
→ Subject document created with owner = current_user
→ Returns SubjectResponse
```

### Step 4 — Create a Lecture under that Subject
```
POST /lectures/  { title, description, subject_id }  [Bearer Token]
→ Fetches Subject, verifies ownership
→ Creates Lecture document with status="pending"
→ Returns LectureResponse (no file yet)
```

### Step 5 — Upload a PDF to the Lecture
```
POST /knowledge/upload_pdf/{lecture_id}  [multipart file + Bearer Token]
→ Verifies lecture exists + user owns it
→ Saves file to ./uploads/{lecture_id}_{filename}.pdf
→ Sets lecture.status = "processing", saves to DB
→ Fires BackgroundTask: process_pdf_background(lecture_id, file_path)
→ Immediately returns { filename, lecture_id, status: "processing", message }
```

### Step 6 — PDF Processing (Background Task)
```
process_pdf_background(lecture_id, file_path):
  1. Load PDF with PyMuPDF
  2. Extract text page-by-page → build pages list + full_text string
  3. chunk_document(pages):
       → recursive_character_text_splitter per page
       → 1000-char chunks, 200-char overlap
       → preserves page_number on each chunk
  4. In batches of 100:
       → get_embeddings(chunk_texts) → OpenAI API → 1536-dim vectors
       → Insert KnowledgeChunk documents into MongoDB (lecture_id str + embedding)
  5. generate_and_save_knowledge_card(lecture_id, full_text[:15000]):
       → GPT-4o-mini generates { summary, key_concepts } as JSON
       → Inserts KnowledgeCard document
  6. lecture.status = "completed" → saved
  (On failure: lecture.status = "failed")
```

### Step 7 — Ask a Question
```
POST /ai/ask  { question, lecture_id }  [Bearer Token]
→ build_context(lecture_id, question):
    a. Fetch KnowledgeCard for lecture → global_context string
    b. get_embeddings([question]) → 1536-dim query vector
    c. vector_search(query_embedding, limit=5, lecture_id):
         → MongoDB $vectorSearch aggregation
         → filtered by lecture_id string
         → returns top-5 chunks + scores
    d. Build retrieved_chunks string with page numbers
→ Format SYSTEM_PROMPT_ASK with { global_context, retrieved_chunks, question }
→ GPT-4o-mini (temp=0.2) generates answer
→ Returns { answer, sources: ["Page X (Similarity: 0.91)", ...] }
```

### Step 8 — Explain a Concept
```
POST /ai/explain  { concept, lecture_id }  [Bearer Token]
→ Same build_context() pipeline as /ask
→ Different prompt: focused on explaining the concept simply
→ Returns { explanation }
```

### Step 9 — Get a Lecture Summary
```
GET /ai/summary/{lecture_id}  [Bearer Token]
→ Fetches pre-computed KnowledgeCard from DB
→ Returns { lecture_id, summary, key_concepts }
```

---

## 5. Video/Data Processing Pipeline Analysis

### Expected Pipeline (design intent)

| Step | Description |
|---|---|
| 1 | Take a video link (URL) |
| 2 | Download the video |
| 3 | Extract frames (images) |
| 4 | Extract audio track |
| 5 | Apply OCR on frames |
| 6 | Convert audio → text (transcription) |
| 7 | Clean and preprocess text |
| 8 | Chunk text |
| 9 | Embed chunks |
| 10 | Save to DB (vector store) |

### Current Implementation Status Per Step

| Step | Status | Details |
|---|---|---|
| **1. Take video link** | ❌ Not implemented | Route accepts file upload, not URL |
| **2. Download video** | ❌ Not implemented | No `yt-dlp`, no URL handling |
| **3. Extract frames** | ❌ Not implemented | No `ffmpeg`, `cv2`, or similar |
| **4. Extract audio** | ❌ Not implemented | No audio separation library |
| **5. OCR on frames** | ❌ Not implemented | No `pytesseract` or OCR tool |
| **6. Audio → text (Whisper)** | ❌ Not implemented | No Whisper integration |
| **7. Clean/preprocess text** | ⚠️ Simplified | PDF pipeline uses raw PyMuPDF text — no cleaning |
| **8. Chunk text** | ✅ Implemented | For PDF only — custom sliding window splitter |
| **9. Embed chunks** | ✅ Implemented | OpenAI `text-embedding-ada-002` |
| **10. Save to DB** | ✅ Implemented | KnowledgeChunk documents with vector field |

**In plain terms:** Steps 1–6 of the video pipeline are completely missing. The video upload route exists and saves the file to disk, then immediately marks the lecture as `"failed"`. There is literally a `print()` statement that says: *"Video processing not yet implemented."*

---

## 6. RAG Implementation — Deep Dive

### Where It Lives
- **Retrieval:** `app/database/mongodb.py` → `vector_search()`
- **Context building:** `app/ai/ask.py` → `build_context()`
- **Inference:** `app/ai/ask.py` → `generate_answer()` and `app/ai/explain.py` → `generate_explanation()`
- **Prompts:** `app/ai/prompts.py`
- **Ingestion:** `app/knowledge/upload_pdf.py` + `app/knowledge/embeddings.py` + `app/knowledge/chunking.py`

### How It Works Step by Step

```
INGESTION SIDE (pre-computation):
  PDF → [PyMuPDF] → raw text (per page)
      → [chunking.py] → ~1000-char chunks with overlap
      → [OpenAI ada-002] → 1536-dim embeddings
      → [MongoDB] → KnowledgeChunk documents (text + embedding + page_number + lecture_id)
  Full text → [GPT-4o-mini] → {summary, key_concepts}
           → [MongoDB] → KnowledgeCard document

QUERY SIDE (runtime):
  User question
      → [OpenAI ada-002] → 1536-dim query embedding
      → [MongoDB $vectorSearch] → top-5 most similar chunks (filtered by lecture_id)
      → [Fetch KnowledgeCard] → global_context
      → [Prompt assembly] → global_context + chunks + question
      → [GPT-4o-mini] → answer string + source citations
```

### Is It Properly Implemented?

**What's good:**
- ✅ Hybrid retrieval: Global Knowledge Card (breadth) + Vector chunks (depth) — genuinely solid design.
- ✅ Lecture-scoped filtering in vector search (prevents cross-lecture contamination).
- ✅ Sources returned to user (page number + similarity score).
- ✅ Low temperature (0.2) for factual, grounded answers.
- ✅ Async throughout — no blocking calls.
- ✅ Batch embedding (100 at a time) to avoid API timeout.
- ✅ `response_format: json_object` for deterministic Knowledge Card parsing.

**What needs improvement:**
- ⚠️ **No re-ranking**: After vector search, chunks are used as-is. A cross-encoder re-ranker would improve precision.
- ⚠️ **No chunking strategy for Knowledge Card**: Only first 15,000 characters sent to GPT. Long documents lose most context.
- ⚠️ **`lecture_id` filter uses string comparison**: Fragile if IDs are sometimes ObjectId vs string.
- ⚠️ **No ownership check in AI layer**: A valid JWT user can query any `lecture_id` — `user_id` is accepted but **never used**.
- ⚠️ **New client per request**: `AsyncOpenAI()` instantiated fresh on every call — should be a singleton.
- ⚠️ **Chunking is page-by-page, not document-wide**: Chunks near page breaks lose context.

---

## 7. AI Readiness Assessment

| Component | Status | Verdict |
|---|---|---|
| **Embeddings** | OpenAI `text-embedding-ada-002`, async, batched | ✅ Prototype-ready |
| **Knowledge Card generation** | GPT-4o-mini + JSON mode | ✅ Prototype-ready — works well for small/medium docs |
| **Vector Search** | MongoDB Atlas `$vectorSearch` | ✅ Solid foundation |
| **RAG Q&A Pipeline** | Hybrid context (card + chunks) → GPT-4o-mini | 🟡 **Prototype/Experimental** — correct logic, has security gap |
| **Prompts** | Two system prompts (ask + explain) | 🟡 Functional but basic |
| **Video Pipeline** | Stub only | ❌ **Incomplete** — does not exist |
| **Error Handling in AI** | `print()` + raw `raise` | ❌ Not production grade |
| **Overall AI System** | | 🟡 **Prototype / Experimental** |

**Honest verdict:** The PDF → RAG → answer loop works and is architecturally sound, but it is **not production-ready**. Critical gaps: security hole in AI endpoints, no video pipeline, no task persistence, local file storage, no test coverage.

---

## 9. Structured Summary Table

| Area | Status |
|---|---|
| Authentication (register/login/JWT) | ✅ Complete |
| Subject CRUD | 🟡 Partial (no update/delete) |
| Lecture CRUD | 🟡 Partial (no update/delete) |
| PDF upload & ingestion | ✅ Complete |
| PDF text extraction | ✅ Complete |
| Text chunking | ✅ Complete (simplified) |
| Embedding generation | ✅ Complete |
| Knowledge Card generation | ✅ Complete (15k char limit) |
| MongoDB vector store | ✅ Complete |
| RAG Q&A (`/ai/ask`) | 🟡 Works, has security gap |
| Concept explanation (`/ai/explain`) | 🟡 Works, has security gap |
| Lecture summary (`/ai/summary`) | ✅ Complete |
| Video upload route | 🟡 Route exists, no processing |
| Video download (URL) | ❌ Missing |
| Frame extraction | ❌ Missing |
| OCR on frames | ❌ Missing |
| Audio extraction | ❌ Missing |
| Whisper transcription | ❌ Missing |
| File storage (S3/cloud) | ❌ Missing (local only) |
| Status polling endpoint | ❌ Missing |
| Ownership check in AI layer | ❌ Missing |
| Token refresh/logout | ❌ Missing |
| Tests | ❌ Missing |
| Structured logging | ❌ Missing |
| Task queue (Celery) | ❌ Missing |
| Rate limiting | ❌ Missing |
| Frontend | ❌ Out of scope (backend only) |
