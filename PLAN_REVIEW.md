# Lecture Brain — Plan Review & Comparison
> Comparing the new updated plan against the current implementation (PROJECT_STATUS.md)

---

## 1. What Already Matches the New Plan ✅

| New Plan Item | Current Status |
|---|---|
| FastAPI backend | ✅ Already in place |
| MongoDB Atlas + Vector Search (no separate vector DB) | ✅ Already in place |
| Subject → Lecture hierarchy | ✅ Already implemented |
| PDF ingestion (PyMuPDF text extraction) | ✅ Already implemented |
| Chunk → Embed → Store pipeline | ✅ Already implemented for PDF |
| Knowledge Card per lecture | ✅ Already implemented (partially matching) |
| RAG Q&A using vector search + Knowledge Card | ✅ Already implemented |
| Lecture-scoped vector search (`lecture_id` filter) | ✅ Already implemented |
| Modular architecture (routes / models / schemas / ai / knowledge) | ✅ Already in place |
| Prompts in a separate file (`prompts.py`) | ✅ Already done |
| Explain endpoint | ✅ Already exists (`/ai/explain`) |
| Summary endpoint | ✅ Already exists (`/ai/summary`) |
| Clean, no-over-engineering direction | ✅ Architecture is already minimal and direct |

---

## 2. What Is Different or Needs to Change 🔄

### 2.1 — Multiple Sources Per Lecture (NEW)
**New Plan:** A lecture can have PDF + Video + Raw Text — all as sources under one lecture.

**Current:** A lecture has ONE `source_file_url` field (single file). The model doesn't support multiple sources. You'd need to restructure the `Lecture` model or create a separate `LectureSource` collection.

**Action needed:** Redesign the `Lecture` model to support multiple sources, or add a `sources` list field.

---

### 2.2 — Raw Text Source (NEW)
**New Plan:** Raw text as a third source type.

**Current:** Not implemented at all. No upload/ingestion route for raw text.

**Action needed:** Add a `POST /knowledge/upload_text/{lecture_id}` endpoint + processing function (simplest pipeline: clean → chunk → embed → store).

---

### 2.3 — Video Pipeline (SIMPLIFIED vs. STUB)
**New Plan:** Video URL → check subtitles → if yes use them, if no → extract audio → Whisper → clean → chunk → embed → store. No frame extraction. No OCR.

**Current:** The video processor is a **complete stub**. It saves the file and immediately marks the lecture as `"failed"`. Nothing works.

**Action needed:** Build the actual video pipeline using:
- `yt-dlp` — to download video + check/fetch subtitles
- `openai-whisper` or OpenAI Whisper API — to transcribe audio if no subtitles
- Then plug into existing chunk → embed → store pipeline

This is the **biggest gap** between the plan and the current code.

---

### 2.4 — Knowledge Card Structure (DIFFERENT)
**New Plan:**
```json
{
  "summary": "...",
  "key_points": [],
  "concepts": [],
  "important_details": "...",
  "examples": []
}
```

**Current:**
```json
{
  "summary": "...",
  "key_concepts": []
}
```

The current card is simpler — missing `key_points`, `important_details`, and `examples`.

**Action needed:**
- Update the `KnowledgeCard` model to add the new fields.
- Update the Knowledge Card generation prompt to request and parse the new structure.
- Update the `knowledge_card.py` saving logic.

---

### 2.5 — Quiz Action (NEW)
**New Plan:** Quiz is one of the action buttons alongside Explain and Summary.

**Current:** No quiz endpoint exists anywhere — no route, no prompt, no logic.

**Action needed:** Add `POST /ai/quiz/{lecture_id}` endpoint + a quiz-generation prompt in `prompts.py`.

---

### 2.6 — Chat with Memory (NEW — partially different)
**New Plan:** Chat with last-few-messages memory (conversational context).

**Current:** The `/ai/ask` endpoint is **stateless** — each question is independent. There is no conversation history, no session, no memory.

**Action needed:**
- Add a `conversation_history` field to the `AskRequest` (client sends last N messages).
- Or store a chat session in MongoDB and retrieve it by session ID.
- The simpler approach: client sends last N messages in the request body, server includes them in the prompt. No server-side session storage needed. This aligns with the "no over-engineering" direction.

---

### 2.7 — Ownership Check in AI Endpoints (BUG — not in new plan but must be fixed)
**New Plan:** Doesn't mention this, but the current code has a **security gap** — the `user_id` passed to `generate_answer()` is never actually used to verify ownership of the lecture.

**Action needed:** Add one DB lookup in `generate_answer()` to confirm the lecture belongs to the current user before answering. This is a one-liner fix.

---

### 2.8 — OCR for Image-Based PDFs (MINOR ADDITION)
**New Plan:** "Use OCR only if needed (image-based PDFs)."

**Current:** No OCR fallback. If a PDF has no embedded text (scanned document), PyMuPDF returns empty strings and the lecture gets no content.

**Action needed:** Detect if extracted text is empty → fall back to OCR using `pytesseract` + `pdf2image`. This is optional but should be noted as a known limitation until implemented.

---

## 3. Contradictions Between Current Code and New Plan ⚠️

| Contradiction | Current Code | New Plan |
|---|---|---|
| Video processing | Stub — always fails | Should work: subtitles → Whisper fallback |
| Single source per lecture | One `source_file_url` | Multiple sources (PDF + video + text) |
| Knowledge Card fields | Only `summary` + `key_concepts` | 5 structured fields |
| No chat memory | Stateless per-question | Last-N-messages memory |
| No quiz | Not implemented | Action button / endpoint |
| No raw text ingestion | Not implemented | Third source type |

---

## 4. Is the New Plan Better, Simpler, More Realistic?

### Better? ✅ Yes.
- Dropping frame extraction and OCR-on-video was the right call. That path adds enormous complexity (ffmpeg, cv2, pytesseract on video frames) with limited payoff compared to subtitle/audio transcription alone.
- Adding raw text as a source is very practical — students often have notes or copy-pasted text they want to query.
- Structuring the Knowledge Card with more fields (key_points, examples) directly improves the quality of answers, summaries, and quizzes.

### Simpler? ✅ Yes, significantly.
- The video pipeline you've described is the minimum viable approach that actually works well.
- Using client-sent conversation history for "memory" avoids building a session management system entirely.
- One Knowledge Card per lecture (no separate brief/master cards) keeps the data model clean.

### More Realistic? ✅ Yes.
- The current implementation pretends to handle video but doesn't. The new plan sets a realistic scope.
- Each piece of the new plan is buildable with well-known, available Python libraries.
- The plan avoids architectural traps (no Celery, no Redis, no separate vector DB — just FastAPI + MongoDB Atlas).

---

## 5. Honest Opinion & Suggested Adjustments

### The direction is correct. Here's what I'd keep exactly as you described:
- Subtitle-first video ingestion (yt-dlp subtitles → Whisper fallback)
- Single Knowledge Card with the 5-field structure
- Client-side memory for chat (send last N messages in request)
- Prompts in a separate file
- No separate vector database

### Small adjustments I'd suggest (none add complexity):

**1. For multiple sources — use a `sources` list on Lecture, not a separate collection.**
```python
# In Lecture model:
sources: List[dict] = []
# Each source: { "type": "pdf"|"video"|"text", "url": "...", "status": "pending|completed|failed" }
```
This avoids a new collection while cleanly supporting multiple sources per lecture.

**2. For chat memory — keep it simple: client sends history.**
```json
POST /ai/chat
{
  "lecture_id": "...",
  "message": "What is X?",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```
No session storage, no IDs. The frontend holds the conversation. Clean and standard.

**3. Rename `/ai/ask` to `/ai/chat` to reflect conversational intent.**
The current `/ai/ask` is a better name for a one-shot question. Once memory is added, `/ai/chat` is more accurate.

**4. Fix the ownership security gap before adding new features.** It's a one-liner and it's a real bug.

**5. Add a `GET /lectures/{id}/status` endpoint.** Without it, there's no way to know when a video or PDF finishes processing. This is one line of code and removes a significant usability problem.

---

## 6. Recommended Build Order (Priority)

Given the new plan, here's the logical order to implement:

| Priority | Task | Effort |
|---|---|---|
| 1 | Fix ownership check in `/ai/ask` + `/ai/explain` | Very Low |
| 2 | Add `GET /lectures/{id}/status` endpoint | Very Low |
| 3 | Update Knowledge Card model + prompt (5 fields) | Low |
| 4 | Add `DELETE` for Subjects and Lectures (with cascade) | Low |
| 5 | Add raw text ingestion endpoint | Low |
| 6 | Update Lecture model for multiple sources | Medium |
| 7 | Add `/ai/chat` with conversation history | Medium |
| 8 | Add `/ai/quiz` endpoint + prompt | Low |
| 9 | Build the video pipeline (yt-dlp + Whisper) | High |
| 10 | OCR fallback for image-based PDFs | Medium |

---

## Summary

The new plan is a **clear improvement** over both the original design intent and the current implementation. It is:
- Scoped correctly (no frame extraction, no over-engineering)
- Architecturally consistent with what's already built
- Achievable with a small, focused set of additions

The biggest work item remaining is the **video pipeline** (yt-dlp + Whisper). Everything else is relatively small additions on top of a solid existing foundation.
