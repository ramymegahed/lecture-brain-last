# Lecture Brain — Implementation Plan
> Based on plan review. Ready for team execution.
> Last updated: 2026-04-01

---

## Overview & Build Order

Tasks are ordered by dependency. Each phase must be completed before the next.

```
Phase 1 — Quick Fixes & Foundation          (no dependencies, start immediately)
Phase 2 — Model & Data Changes              (required before Phase 3+)
Phase 3 — New Ingestion Sources             (depends on Phase 2)
Phase 4 — AI Feature Updates                (depends on Phase 2)
Phase 5 — Video Pipeline                    (largest item, depends on Phase 2-3)
Phase 6 — Optional: OCR for Image PDFs
Phase 7 — Optional: Video Frame OCR         (user-enabled, heavy process)
Phase 8 — Docker Setup                      (can be done after Phase 1, parallel with others)
Phase 9 — Documentation                     (done last, after all features are finalized)
```

---

## Phase 1 — Quick Fixes & Foundation

> These have zero dependencies. Can be done in parallel by the team on Day 1.

---

### Task 1.1 — Fix Ownership Security Bug in AI Endpoints

**Priority:** Critical (security bug)
**Effort:** Very Low (< 1 hour)
**Files to edit:** `app/ai/ask.py`, `app/ai/explain.py`, `app/ai/summary.py`

**Problem:**
`user_id` is passed into `generate_answer()`, `generate_explanation()`, and `get_lecture_summary()` but is **never used**. Any authenticated user can query any lecture by ID.

**Fix — add this ownership check at the top of each function:**

```python
# In generate_answer(), generate_explanation(), get_lecture_summary():
lecture = await Lecture.get(PydanticObjectId(lecture_id))
if not lecture:
    raise ValueError("Lecture not found")

subject = await Subject.get(lecture.subject.ref.id)
if not subject or str(subject.owner.ref.id) != str(user_id):
    raise ValueError("Access denied")
```

**Route-level:** Wrap `ValueError` in the route handler as HTTP 403/404:

```python
# In ai_routes.py
try:
    answer, sources = await generate_answer(...)
except ValueError as e:
    raise HTTPException(status_code=403, detail=str(e))
```

---

### Task 1.2 — Add Status Polling Endpoint

**Priority:** High (unblocks frontend development)
**Effort:** Very Low (< 30 min)
**File to edit:** `app/routes/lecture_routes.py`

**New endpoint:**

```
GET /lectures/{lecture_id}/status
```

**Response:**
```json
{
  "lecture_id": "...",
  "status": "pending | processing | completed | failed"
}
```

**Implementation:**
```python
@router.get("/{lecture_id}/status")
async def get_lecture_status(
    lecture_id: str,
    current_user: User = Depends(get_current_active_user)
):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Lecture not found")
    return {"lecture_id": lecture_id, "status": lecture.status}
```

---

### Task 1.3 — Add DELETE Endpoints for Subjects and Lectures

**Priority:** High
**Effort:** Low (2-3 hours including cascade logic)
**Files to edit:** `app/routes/subject_routes.py`, `app/routes/lecture_routes.py`

**New endpoints:**
```
DELETE /subjects/{subject_id}      → deletes subject + all its lectures + their chunks + cards
DELETE /lectures/{lecture_id}      → deletes lecture + its chunks + its card
```

**Cascade deletion logic for a lecture:**
```python
async def delete_lecture_data(lecture_id: str):
    lid = PydanticObjectId(lecture_id)
    await KnowledgeChunk.find(KnowledgeChunk.lecture.id == lid).delete()
    await KnowledgeCard.find(KnowledgeCard.lecture.id == lid).delete()

# In DELETE /lectures/{lecture_id}:
await delete_lecture_data(lecture_id)
await lecture.delete()
```

**For subject deletion:** iterate all lectures under the subject, call `delete_lecture_data()` for each, then delete the lectures and the subject.

---

## Phase 2 — Model & Data Structure Changes

> Must be completed before Phase 3 and 4. These are schema-level changes.

---

### Task 2.1 — Update Knowledge Card Model (5 Fields)

**Effort:** Low (1-2 hours)
**Files to edit:** `app/models/knowledge_card.py`, `app/knowledge/knowledge_card.py`

**New model (`app/models/knowledge_card.py`):**
```python
class KnowledgeCard(Document):
    lecture: Link[Lecture]
    summary: str
    key_points: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    important_details: str = Field(default="")
    examples: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "knowledge_cards"
```

**Updated generation prompt (`app/knowledge/knowledge_card.py`):**
```python
prompt = f"""
You are an expert educational AI.
Read the following lecture text and return a JSON object with EXACTLY these fields:
{{
  "summary": "3-4 sentence overview of the entire lecture",
  "key_points": ["main point 1", "main point 2", ...],
  "concepts": ["concept1", "concept2", ...],
  "important_details": "Any critical formulas, dates, definitions, or facts",
  "examples": ["example 1", "example 2", ...]
}}

Lecture text:
{document_text}
"""
```

**Update saving logic** to map all 5 fields from the parsed JSON.

**Note:** Existing `key_concepts` → rename to `concepts` in the model. Any existing cards in MongoDB will need migration or re-ingestion.

---

### Task 2.2 — Update Lecture Model for Multiple Sources

**Effort:** Medium (3-4 hours including route updates)
**Files to edit:** `app/models/lecture.py`, `app/schemas/lecture_schema.py`, all knowledge routes

**New Lecture model:**
```python
class LectureSource(BaseModel):
    type: str           # "pdf" | "video" | "text"
    url: str            # local path or video URL
    status: str = "pending"   # pending | processing | completed | failed
    error: Optional[str] = None

class Lecture(Document):
    title: str = Field(..., max_length=150)
    description: str = Field(default="")
    subject: Link[Subject]
    sources: List[LectureSource] = Field(default_factory=list)
    # Keep overall lecture status (completed when ALL sources done)
    status: str = Field(default="pending")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "lectures"
```

**Remove:** `source_file_url` (replaced by `sources` list)

**Update schemas** (`app/schemas/lecture_schema.py`):
- Add `sources: List[dict] = []` to `LectureResponse`
- Remove `source_file_url`

**Update upload routes** to append to `lecture.sources` instead of setting `source_file_url`.

**Lecture overall status rule:**
- `pending` → no sources yet
- `processing` → at least one source is processing
- `completed` → all sources completed
- `failed` → at least one source failed (with error details per source)

---

## Phase 3 — New Ingestion Sources

> Depends on Phase 2 (Lecture model update).

---

### Task 3.1 — Raw Text Ingestion

**Effort:** Low (2-3 hours)
**New file:** `app/knowledge/upload_text.py`
**Edit:** `app/routes/knowledge_routes.py`

**New endpoint:**
```
POST /knowledge/upload_text/{lecture_id}
Body: { "text": "raw text content here..." }
```

**Schema addition (`app/schemas/knowledge_schema.py`):**
```python
class RawTextUpload(BaseModel):
    text: str
```

**Processing pipeline (`app/knowledge/upload_text.py`):**
```python
async def process_text_background(lecture_id: str, raw_text: str):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))

    try:
        # 1. Simple cleaning
        cleaned = clean_text(raw_text)

        # 2. Chunk (reuse existing chunker, treat as single "page 1")
        pages = [{"page_number": 1, "text": cleaned}]
        chunks = chunk_document(pages)

        # 3. Embed + store (reuse existing batch logic)
        # ... (same as PDF pipeline)

        # 4. Generate/update Knowledge Card
        await generate_and_save_knowledge_card(lecture_id, cleaned[:15000])

        # 5. Update source status
        # update source with type="text" to "completed"
        lecture.status = "completed"
        await lecture.save()

    except Exception as e:
        # update source status to "failed"
        lecture.status = "failed"
        await lecture.save()
```

**New utility — `clean_text()` (add to `app/knowledge/chunking.py` or a new `utils.py`):**
```python
import re

def clean_text(text: str) -> str:
    text = re.sub(r'\s+', ' ', text)       # collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text) # max 2 newlines
    return text.strip()
```

Apply this same `clean_text()` to the PDF pipeline as well.

---

### Task 3.2 — Update PDF Ingestion for Multiple Sources

**Effort:** Low (1-2 hours)
**File to edit:** `app/knowledge/upload_pdf.py`, `app/routes/knowledge_routes.py`

**Changes:**
- Instead of setting `lecture.source_file_url`, append to `lecture.sources`
- Update per-source status (not just the overall lecture status)
- Apply `clean_text()` to extracted text before chunking
- Detect empty text extraction (image-based PDF) → log warning now, OCR in Phase 6

**Route change (`knowledge_routes.py`):**
```python
# Before saving:
lecture.sources.append(LectureSource(
    type="pdf",
    url=file_location,
    status="processing"
))
await lecture.save()

background_tasks.add_task(process_pdf_background, lecture_id, file_location)
```

---

## Phase 4 — AI Feature Updates

> Depends on Phase 2 (Knowledge Card model update). Parallel with Phase 3.

---

### Task 4.1 — Rename /ai/ask → /ai/chat + Add Conversation Memory

**Effort:** Medium (3-4 hours)
**Files to edit:** `app/routes/ai_routes.py`, `app/schemas/ai_schema.py`, `app/ai/ask.py` (rename/update), `app/ai/prompts.py`

**Updated schema (`app/schemas/ai_schema.py`):**
```python
class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    lecture_id: str
    message: str
    history: List[ChatMessage] = []   # last N messages, sent by client

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = []
```

**Updated route:**
```
POST /ai/chat
```

**Updated prompt assembly (`app/ai/ask.py`):**
```python
# Build messages list for OpenAI
messages = [{"role": "system", "content": SYSTEM_PROMPT_CHAT.format(
    global_context=global_ctx,
    retrieved_chunks=retrieved_chunks
)}]

# Append conversation history
for msg in request.history[-6:]:  # last 6 messages (3 turns)
    messages.append({"role": msg.role, "content": msg.content})

# Add current user message
messages.append({"role": "user", "content": request.message})

response = await client.chat.completions.create(
    model="gpt-4o-mini",
    messages=messages,
    temperature=0.2
)
```

**New prompt in `prompts.py`:**
```python
SYSTEM_PROMPT_CHAT = """
You are LectureBrain, an expert AI tutor.
Answer the student's question using ONLY the lecture context provided.
If the answer is not in the context, say so clearly.

Lecture Summary & Key Points:
{global_context}

Relevant Lecture Sections:
{retrieved_chunks}
"""
```

**Keep `/ai/ask` as a deprecated alias** (or remove it — team decision).

---

### Task 4.2 — Update /ai/summary to Use New Knowledge Card Fields

**Effort:** Very Low (< 30 min)
**Files to edit:** `app/schemas/ai_schema.py`, `app/ai/summary.py`

**Updated response schema:**
```python
class SummaryResponse(BaseModel):
    lecture_id: str
    summary: str
    key_points: List[str]
    concepts: List[str]
    important_details: str
    examples: List[str]
```

**Updated `get_lecture_summary()`** to return all 5 fields from the card.

---

### Task 4.3 — Add /ai/explain Update

**Effort:** Very Low (< 30 min)
**File to edit:** `app/ai/prompts.py`

Update `SYSTEM_PROMPT_EXPLAIN` to use the new Knowledge Card structure (reference `key_points` and `examples` if relevant).

```python
SYSTEM_PROMPT_EXPLAIN = """
You are LectureBrain, an expert AI tutor.
A student wants you to explain: "{concept}"

Use ONLY the following lecture material to explain it clearly.
Include an example from the lecture if available.

Lecture Context:
{global_context}

Relevant Sections:
{retrieved_chunks}
"""
```

---

### Task 4.4 — Add Quiz Endpoint

**Effort:** Low (2-3 hours)
**New file:** `app/ai/quiz.py`
**Edit:** `app/routes/ai_routes.py`, `app/schemas/ai_schema.py`, `app/ai/prompts.py`

**New endpoint:**
```
POST /ai/quiz/{lecture_id}
```

**Request (optional params):**
```python
class QuizRequest(BaseModel):
    lecture_id: str
    num_questions: int = 5   # default 5
    difficulty: str = "medium"  # "easy" | "medium" | "hard"
```

**Response:**
```python
class QuizQuestion(BaseModel):
    question: str
    options: List[str]       # 4 options (A, B, C, D)
    correct_answer: str      # "A" | "B" | "C" | "D"
    explanation: str

class QuizResponse(BaseModel):
    lecture_id: str
    questions: List[QuizQuestion]
```

**Quiz prompt (`app/ai/prompts.py`):**
```python
SYSTEM_PROMPT_QUIZ = """
You are LectureBrain, an expert AI tutor.
Generate {num_questions} multiple-choice questions based ONLY on this lecture.
Difficulty: {difficulty}

Return a JSON array with this exact format:
[
  {{
    "question": "...",
    "options": ["A. ...", "B. ...", "C. ...", "D. ..."],
    "correct_answer": "A",
    "explanation": "Brief explanation why this is correct"
  }}
]

Lecture Summary:
{global_context}

Key Lecture Content:
{retrieved_chunks}
"""
```

**Implementation (`app/ai/quiz.py`):**
- Fetch Knowledge Card → build global_context
- Run vector search (higher limit, e.g. 10 chunks for better coverage)
- Call GPT-4o-mini with `response_format: json_object`
- Parse and return structured questions

---

## Phase 5 — Video Pipeline

> Largest item. Depends on Phase 2 (Lecture model) and Phase 3 (ingestion patterns established).

---

### Task 5.1 — Install Required Libraries

**Add to `requirements.txt`:**
```
yt-dlp
openai-whisper
ffmpeg-python
```

**Note:** `ffmpeg` binary must also be installed on the server (not just the Python wrapper).

---

### Task 5.2 — Change Video Route: URL Input Instead of File Upload

**Edit:** `app/routes/knowledge_routes.py`

**New endpoint:**
```
POST /knowledge/upload_video/{lecture_id}
Body: { "url": "https://youtube.com/watch?v=..." }
```

**Schema (`app/schemas/knowledge_schema.py`):**
```python
class VideoUpload(BaseModel):
    url: str
    extract_frames: bool = False  # Optional — user must explicitly enable this
```

**Route logic:**
```python
@router.post("/upload_video/{lecture_id}")
async def upload_video(
    lecture_id: str,
    video_in: VideoUpload,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_active_user)
):
    # Verify ownership ...
    lecture.sources.append(LectureSource(type="video", url=video_in.url, status="processing"))
    await lecture.save()
    background_tasks.add_task(
        process_video_background,
        lecture_id,
        video_in.url,
        video_in.extract_frames   # passed through to the pipeline
    )
    return UploadResponse(...)
```

> ⚠️ **Warning to surface in API docs / frontend:** If `extract_frames=true` is set, processing time increases significantly depending on video length. A 1-hour video can take 10–30+ minutes. Users should be clearly informed before enabling this.

---

### Task 5.3 — Build the Video Processing Pipeline

**File to fully rewrite:** `app/knowledge/video_processor.py`

**Full pipeline (standard — transcription only):**

```python
import yt_dlp
import whisper
import os
from app.knowledge.chunking import chunk_document, clean_text
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card
from app.models.knowledge import KnowledgeChunk
from app.models.lecture import Lecture
from beanie import PydanticObjectId

async def process_video_background(lecture_id: str, video_url: str, extract_frames: bool = False):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        return

    try:
        # Step 1: Try to fetch subtitles via yt-dlp
        transcript = await fetch_subtitles(video_url)

        # Step 2: If no subtitles, download audio and run Whisper
        if not transcript:
            audio_path = await download_audio(video_url, lecture_id)
            transcript = await transcribe_audio(audio_path)
            # Clean up audio file
            if os.path.exists(audio_path):
                os.remove(audio_path)

        if not transcript:
            raise Exception("Could not extract transcript from video")

        # Step 3: Clean text
        cleaned = clean_text(transcript)

        # Step 4: Chunk (treat as single source, no page numbers)
        pages = [{"page_number": 1, "text": cleaned}]
        chunks = chunk_document(pages)

        # Step 5: Embed + store (batch, same as PDF pipeline)
        BATCH_SIZE = 100
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            texts = [c["text"] for c in batch]
            embeddings = await get_embeddings(texts)
            knowledge_chunks = [
                KnowledgeChunk(
                    lecture=lecture,
                    lecture_id=lecture_id,
                    text=batch[j]["text"],
                    page_number=None,
                    embedding=embeddings[j]
                ) for j in range(len(batch))
            ]
            if knowledge_chunks:
                await KnowledgeChunk.insert_many(knowledge_chunks)

        # Step 6: Optional frame OCR (only if user enabled it — see Phase 7)
        if extract_frames:
            frame_text = await extract_text_from_frames(video_url, lecture_id)
            if frame_text:
                frame_cleaned = clean_text(frame_text)
                frame_pages = [{"page_number": None, "text": frame_cleaned}]
                frame_chunks = chunk_document(frame_pages)
                # Embed + store frame text chunks (same batch logic)
                # ... (reuse existing batch embed-and-store pattern)

        # Step 7: Generate Knowledge Card
        await generate_and_save_knowledge_card(lecture_id, cleaned[:15000])

        # Step 8: Update source + lecture status
        _update_source_status(lecture, video_url, "completed")
        lecture.status = "completed"
        await lecture.save()

    except Exception as e:
        print(f"Video processing error: {e}")
        _update_source_status(lecture, video_url, "failed", str(e))
        lecture.status = "failed"
        await lecture.save()


def fetch_subtitles(video_url: str) -> str | None:
    """Try to get auto or manual subtitles via yt-dlp."""
    ydl_opts = {
        "skip_download": True,
        "writeautomaticsub": True,
        "writesubtitles": True,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
        "quiet": True,
        "outtmpl": "/tmp/%(id)s",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            # Check for subtitle file
            video_id = info.get("id", "")
            sub_file = f"/tmp/{video_id}.en.vtt"
            if os.path.exists(sub_file):
                with open(sub_file, "r", encoding="utf-8") as f:
                    raw = f.read()
                os.remove(sub_file)
                return _parse_vtt(raw)
    except Exception:
        pass
    return None


def _parse_vtt(vtt_content: str) -> str:
    """Extract plain text from VTT subtitle file."""
    import re
    lines = vtt_content.split("\n")
    text_lines = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("WEBVTT") or "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        text_lines.append(line)
    return " ".join(text_lines)


async def download_audio(video_url: str, lecture_id: str) -> str:
    """Download audio track using yt-dlp."""
    output_path = f"uploads/{lecture_id}_audio"
    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        "outtmpl": output_path,
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])
    return f"{output_path}.mp3"


async def transcribe_audio(audio_path: str) -> str:
    """Use OpenAI Whisper to transcribe audio file."""
    model = whisper.load_model("base")  # Use "small" or "medium" for better accuracy
    result = model.transcribe(audio_path)
    return result.get("text", "")


def _update_source_status(lecture, url: str, status: str, error: str = None):
    for source in lecture.sources:
        if source.url == url:
            source.status = status
            if error:
                source.error = error
            break
```

---

## Phase 6 — Optional: OCR Fallback for Image-Based PDFs

> Only implement if there are actual use cases with scanned PDFs.

**Effort:** Medium (4-5 hours)
**New libraries to add:** `pdf2image`, `pytesseract`
**Also requires:** `poppler` (for pdf2image) and `tesseract` binaries on the server

**Detection logic (add to `upload_pdf.py`):**
```python
# After extracting text:
total_text = full_text.strip()
if len(total_text) < 100:  # likely image-based PDF
    print(f"Low text content detected, attempting OCR for lecture {lecture_id}")
    full_text = await extract_text_with_ocr(file_path)
    pages = [{"page_number": 1, "text": full_text}]
```

**OCR extraction:**
```python
from pdf2image import convert_from_path
import pytesseract

async def extract_text_with_ocr(file_path: str) -> str:
    images = convert_from_path(file_path)
    text = ""
    for image in images:
        text += pytesseract.image_to_string(image) + "\n"
    return text
```

---

## Phase 7 — Optional: Video Frame Extraction + OCR

> User-enabled feature. Off by default. Must be explicitly opted into via `extract_frames: true` in the video upload request.

**Effort:** Medium-High (5-7 hours)
**New libraries to add:** `opencv-python`, `pytesseract`, `Pillow`
**Also requires:** `tesseract` binary on the server + `ffmpeg` (already needed for Phase 5)

### How It Works

1. User sets `extract_frames: true` in the video upload request
2. Video is downloaded (or re-used from audio download step)
3. Frames are extracted at a fixed interval (e.g., 1 frame every 5 seconds)
4. Each frame is checked — frames with low text density are skipped
5. OCR is applied to text-rich frames via `pytesseract`
6. Extracted frame text is cleaned, chunked, embedded, and stored as additional `KnowledgeChunk` documents (alongside the transcript chunks)
7. Frame chunks are tagged with `source_type: "frame"` for traceability

### ⚠️ Time Warning (Must Be Surfaced to User)

```
Frame extraction and OCR is a heavy process.
Estimated processing time:
  - 30 min video  →  5–15 minutes
  - 1 hour video  →  15–35 minutes
  - 2 hour video  →  30–70 minutes
(Depends on server specs and frame interval settings)
```

This warning **must be shown** in the frontend before the user enables this option, and returned in the API response when `extract_frames=true`.

### Implementation (`app/knowledge/video_processor.py` — add these functions)

```python
import cv2
import pytesseract
from PIL import Image
import numpy as np

FRAME_INTERVAL_SECONDS = 5   # Extract 1 frame every N seconds
MIN_TEXT_LENGTH = 30         # Skip frames with less than N characters of text

async def extract_text_from_frames(video_path: str, lecture_id: str) -> str:
    """
    Extract frames from video, run OCR on text-rich frames,
    and return concatenated text.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(fps * FRAME_INTERVAL_SECONDS)

    all_text = []
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            # Convert frame to PIL Image
            pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            # Run OCR
            text = pytesseract.image_to_string(pil_image).strip()
            if len(text) >= MIN_TEXT_LENGTH:
                all_text.append(text)

        frame_count += 1

    cap.release()
    return "\n".join(all_text)
```

### Key Design Decisions

- `extract_frames_from_frames()` is called **after** transcription completes — it adds supplementary chunks, not replacement chunks
- Frame chunks and transcript chunks are all stored in the same `knowledge_chunks` collection under the same `lecture_id` — the vector search retrieves from both automatically
- The `FRAME_INTERVAL_SECONDS` constant should be configurable per-environment (e.g., via `.env`)
- For local file videos: `video_path` is the local file. For URL-based videos: the file must be downloaded first (reuse the `download_audio` download step but keep the full video file)

### Schema Update (add warning field to response)

```python
class UploadResponse(BaseModel):
    filename: str
    lecture_id: str
    status: str
    message: str
    warning: Optional[str] = None  # populated when extract_frames=True
```

**Route populates warning:**
```python
warning = None
if video_in.extract_frames:
    warning = (
        "Frame extraction is enabled. Processing time may be significantly longer "
        "depending on video length (estimated 5–35+ minutes for a typical lecture)."
    )
return UploadResponse(..., warning=warning)
```

### File Changes for Phase 7

| File | Change |
|---|---|
| `app/knowledge/video_processor.py` | Add `extract_text_from_frames()` function |
| `app/schemas/knowledge_schema.py` | Add `warning` field to `UploadResponse` |
| `requirements.txt` | Add `opencv-python`, `Pillow` (pytesseract already added in Phase 6) |

---

## File Change Summary

| File | Change Type | Phase |
|---|---|---|
| `app/models/lecture.py` | Update — add `LectureSource`, replace `source_file_url` with `sources: List` | 2 |
| `app/models/knowledge_card.py` | Update — add 3 new fields | 2 |
| `app/schemas/lecture_schema.py` | Update — reflect model changes | 2 |
| `app/schemas/ai_schema.py` | Update — add Chat, Quiz schemas | 4 |
| `app/schemas/knowledge_schema.py` | Update — add `VideoUpload`, `RawTextUpload` | 3, 5 |
| `app/routes/lecture_routes.py` | Add `GET /{id}/status`, `DELETE /{id}` | 1 |
| `app/routes/subject_routes.py` | Add `DELETE /{id}` with cascade | 1 |
| `app/routes/knowledge_routes.py` | Update PDF/video routes, add text route | 3, 5 |
| `app/routes/ai_routes.py` | Rename ask→chat, add quiz endpoint, add error handling | 4 |
| `app/ai/ask.py` | Add ownership check, add conversation history to prompt | 1, 4 |
| `app/ai/explain.py` | Add ownership check | 1 |
| `app/ai/summary.py` | Add ownership check, return all 5 card fields | 1, 4 |
| `app/ai/quiz.py` | New file — quiz generation logic | 4 |
| `app/ai/prompts.py` | Update all prompts, add QUIZ prompt | 4 |
| `app/knowledge/upload_pdf.py` | Use `clean_text()`, update source status | 3 |
| `app/knowledge/upload_text.py` | New file — raw text pipeline | 3 |
| `app/knowledge/video_processor.py` | Full rewrite — yt-dlp + Whisper + optional frame OCR | 5, 7 |
| `app/knowledge/knowledge_card.py` | Update prompt + saving logic for 5 fields | 2 |
| `app/knowledge/chunking.py` | Add `clean_text()` utility | 3 |
| `app/schemas/knowledge_schema.py` | Add `extract_frames` to `VideoUpload`, `warning` to `UploadResponse` | 5, 7 |
| `requirements.txt` | Add yt-dlp, openai-whisper, ffmpeg-python (Phase 5); pdf2image, pytesseract (Phase 6); opencv-python, Pillow (Phase 7) | 5, 6, 7 |

---

## API Endpoints — Final State

### Auth
| Method | Endpoint | Status |
|---|---|---|
| POST | `/auth/register` | ✅ Exists |
| POST | `/auth/login` | ✅ Exists |
| GET | `/auth/me` | ✅ Exists |

### Subjects
| Method | Endpoint | Status |
|---|---|---|
| POST | `/subjects/` | ✅ Exists |
| GET | `/subjects/` | ✅ Exists |
| GET | `/subjects/{id}` | ✅ Exists |
| DELETE | `/subjects/{id}` | 🔨 Phase 1 |

### Lectures
| Method | Endpoint | Status |
|---|---|---|
| POST | `/lectures/` | ✅ Exists |
| GET | `/lectures/subject/{id}` | ✅ Exists |
| GET | `/lectures/{id}` | ✅ Exists |
| GET | `/lectures/{id}/status` | 🔨 Phase 1 |
| DELETE | `/lectures/{id}` | 🔨 Phase 1 |

### Knowledge Ingestion
| Method | Endpoint | Status |
|---|---|---|
| POST | `/knowledge/upload_pdf/{id}` | ✅ Exists (update in Phase 3) |
| POST | `/knowledge/upload_text/{id}` | 🔨 Phase 3 |
| POST | `/knowledge/upload_video/{id}` | 🔨 Phase 5 (rewrite); accepts `extract_frames` flag for Phase 7 |

### AI
| Method | Endpoint | Status |
|---|---|---|
| POST | `/ai/chat` | 🔨 Phase 4 (replaces /ai/ask) |
| POST | `/ai/explain` | ✅ Exists (fix in Phase 1) |
| GET | `/ai/summary/{id}` | ✅ Exists (update in Phase 4) |
| POST | `/ai/quiz/{id}` | 🔨 Phase 4 |

---

## Team Assignment Suggestion

| Developer | Recommended Tasks |
|---|---|
| Dev 1 | Phase 1 (security fix + status endpoint + DELETE) + Phase 8 (Docker) |
| Dev 2 | Phase 2 (model changes — Knowledge Card + Lecture sources) |
| Dev 3 | Phase 3 + 4.2 + 4.3 (raw text ingestion + summary/explain updates) |
| Dev 4 | Phase 4.1 + 4.4 (chat with memory + quiz endpoint) |
| All (after P1-4) | Phase 5 (video pipeline — pair program recommended) |
| Any (last) | Phase 9 (documentation — once all features are stable) |

---

## General Principles (Non-Negotiable)

- All prompts live in `app/ai/prompts.py` only
- No server-side chat sessions — client sends `history[]`
- Single Knowledge Card per lecture — never duplicated
- No frame extraction by default — it is an **opt-in** feature (`extract_frames: true`) with a clear time warning surfaced to the user
- No separate vector DB — MongoDB Atlas only
- Background tasks stay as FastAPI `BackgroundTasks` for now
- Keep functions small and single-purpose

---

## Phase 8 — Docker Setup

> Can be started after Phase 1. Does not block any other phase. Assign to one developer early.

**Effort:** Low-Medium (3-5 hours)
**New files:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`

---

### Task 8.1 — Dockerfile

**New file: `Dockerfile`**

```dockerfile
# Use official Python slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
# - ffmpeg: required for audio extraction (Phase 5)
# - tesseract: required for OCR (Phase 6 & 7)
# - poppler-utils: required by pdf2image (Phase 6)
# - libgl1: required by opencv (Phase 7)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    tesseract-ocr \
    poppler-utils \
    libgl1-mesa-glx \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory
RUN mkdir -p uploads

# Expose API port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

### Task 8.2 — docker-compose.yml

**New file: `docker-compose.yml`**

```yaml
version: "3.9"

services:
  api:
    build: .
    container_name: lecture_brain_api
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      - ./uploads:/app/uploads   # Persist uploaded files outside the container
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/"]
      interval: 30s
      timeout: 10s
      retries: 3
```

> **Note:** MongoDB Atlas is cloud-hosted — no local MongoDB container is needed. The `MONGO_URI` in `.env` connects to Atlas directly.

---

### Task 8.3 — .dockerignore

**New file: `.dockerignore`**

```
venv/
__pycache__/
*.pyc
*.pyo
.env
uploads/
.git/
*.md
*.egg-info/
dist/
.pytest_cache/
```

---

### Task 8.4 — Environment Variables for Docker

The `.env` file is **not copied into the image** (excluded in `.dockerignore`). It is loaded at runtime via `env_file` in `docker-compose.yml`.

**Required `.env` variables:**
```ini
MONGO_URI=mongodb+srv://<user>:<password>@cluster0...
DB_NAME=lecture_brain
OPENAI_API_KEY=sk-...
SECRET_KEY=your-secure-random-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
FRAME_INTERVAL_SECONDS=5   # Optional: for Phase 7 frame extraction
```

---

### Task 8.5 — Running with Docker

**Build and start:**
```bash
docker-compose up --build
```

**Run in background:**
```bash
docker-compose up -d --build
```

**Stop:**
```bash
docker-compose down
```

**View logs:**
```bash
docker-compose logs -f api
```

**Access API docs:** `http://localhost:8080/docs`

---

### Task 8.6 — File Changes for Phase 8

| File | Type |
|---|---|
| `Dockerfile` | New |
| `docker-compose.yml` | New |
| `.dockerignore` | New |

---

## Phase 9 — Documentation

> Do this last, once all features are stable. One developer can own this entirely.

**Effort:** Medium (4-6 hours)
**Output:** An updated and comprehensive `README.md` that replaces the current one.

---

### Task 9.1 — README Structure

The final `README.md` must cover all the sections below.

---

#### Section 1: Project Overview
- What Lecture Brain is (1 paragraph)
- Core user flow: Subjects → Lectures → Sources → Chat/Actions
- What the AI does and how it stays grounded in lecture material

---

#### Section 2: Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend Framework | FastAPI + Uvicorn | Async REST API |
| Database | MongoDB Atlas | Document storage + Vector Search |
| ODM | Beanie 1.25.0 | Async MongoDB object mapper |
| DB Driver | Motor 3.3.2 | Async MongoDB driver (pinned for Beanie compatibility) |
| Vector Search | MongoDB Atlas `$vectorSearch` | Semantic chunk retrieval |
| LLM | OpenAI `gpt-4o-mini` | Q&A, explain, quiz, knowledge card generation |
| Embeddings | OpenAI `text-embedding-ada-002` | 1536-dim vectors for semantic search |
| PDF Parsing | PyMuPDF (`fitz`) | Text extraction from PDFs |
| Video Download | yt-dlp | Download video + extract subtitles |
| Audio Transcription | OpenAI Whisper | Speech-to-text for videos without subtitles |
| Authentication | python-jose + passlib/bcrypt | JWT tokens + password hashing |
| Config | pydantic-settings + python-dotenv | Environment variable management |
| Containerization | Docker + docker-compose | Reproducible deployment |
| Optional (Phase 6) | pdf2image + pytesseract | OCR fallback for image-based PDFs |
| Optional (Phase 7) | opencv-python + pytesseract + Pillow | Frame extraction + OCR for videos |

---

#### Section 3: API Endpoints Reference

Document every endpoint with:
- Method + URL
- Auth required (yes/no)
- Request body schema
- Response schema
- Example request/response

**Endpoint groups to document:**

```
Authentication
  POST  /auth/register
  POST  /auth/login
  GET   /auth/me

Subjects
  POST  /subjects/
  GET   /subjects/
  GET   /subjects/{id}
  DELETE /subjects/{id}

Lectures
  POST  /lectures/
  GET   /lectures/subject/{subject_id}
  GET   /lectures/{id}
  GET   /lectures/{id}/status
  DELETE /lectures/{id}

Knowledge Ingestion
  POST  /knowledge/upload_pdf/{lecture_id}
  POST  /knowledge/upload_text/{lecture_id}
  POST  /knowledge/upload_video/{lecture_id}

AI Actions
  POST  /ai/chat
  POST  /ai/explain
  GET   /ai/summary/{lecture_id}
  POST  /ai/quiz/{lecture_id}
```

---

#### Section 4: Running Locally (Without Docker)

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

#### Section 5: Running with Docker

```bash
# 1. Make sure Docker Desktop is running

# 2. Create .env file (see Environment Variables section)

# 3. Build and start
docker-compose up --build

# 4. Open API docs
# http://localhost:8000/docs

# Stop
docker-compose down
```

---

#### Section 6: Environment Variables

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

#### Section 7: MongoDB Atlas Setup

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

#### Section 8: Optional Features

**OCR Fallback for Image-Based PDFs (Phase 6)**
- Automatically activated when PyMuPDF detects less than 100 characters of text in a PDF
- Requires `tesseract` and `poppler` installed on the server
- No action needed from the user

**Video Frame Extraction + OCR (Phase 7)**
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

#### Section 9: Architecture Overview

Include a short description of the two core engines:

**Ingestion Engine (`app/knowledge/`):**
> Handles all file processing. When a source is uploaded, a background task extracts text (via PyMuPDF / Whisper / raw text), cleans it, chunks it, generates 1536-dim embeddings via OpenAI, stores chunks in MongoDB, and generates a Knowledge Card summary.

**Inference Engine (`app/ai/`):**
> Handles all student interactions. When a student chats, explains, or takes a quiz, the system embeds the query, runs `$vectorSearch` to find the top-5 most relevant chunks, fetches the Knowledge Card, and injects everything into a structured prompt for GPT-4o-mini.

---

### Task 9.2 — Docstrings Review

Before finalizing documentation, do a pass through all files to ensure every function has a clear docstring:
- `app/knowledge/*.py` — all ingestion functions
- `app/ai/*.py` — all inference functions
- `app/database/mongodb.py` — `vector_search()`
- `app/auth/*.py` — auth utilities

Format:
```python
async def function_name(param: type) -> type:
    """
    One-line summary.

    Args:
        param: Description.

    Returns:
        Description of return value.
    """
```

---

### Task 9.3 — File Changes for Phase 9

| File | Change |
|---|---|
| `README.md` | Full rewrite with all 9 sections above |
| All `app/**/*.py` files | Docstring review pass |
