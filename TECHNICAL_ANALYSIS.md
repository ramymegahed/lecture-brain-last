# Lecture Brain — Technical RAG Pipeline Analysis

> **Primary Reference for Graduation Project Defense**
> All figures and logic in this document are traced directly from the production source code.

---

## Table of Contents
1. [System Overview](#1-system-overview)
2. [Data Ingestion Pipeline](#2-data-ingestion-pipeline)
3. [Chunking Strategy](#3-chunking-strategy)
4. [Embedding Model](#4-embedding-model)
5. [MongoDB Atlas Vector Search](#5-mongodb-atlas-vector-search)
6. [Hybrid Context Construction](#6-hybrid-context-construction)
7. [LLM Inference Layer](#7-llm-inference-layer)
8. [Knowledge Card: Global Context Layer](#8-knowledge-card-global-context-layer)
9. [End-to-End RAG Query Flow](#9-end-to-end-rag-query-flow)
10. [Data Models Reference](#10-data-models-reference)

---

## 1. System Overview

Lecture Brain is a **Retrieval-Augmented Generation (RAG)** platform built for educational content. Its purpose is to allow students to have grounded, accurate conversations with their lecture materials — PDFs and video recordings — without the model hallucinating information outside those materials.

The RAG system prevents hallucination by constraining the LLM:

> *"Use ONLY the provided context to answer the question. If the answer is not contained in the context, say 'I don't have enough information from the lecture to answer this.'"*
> — `app/ai/prompts.py`, `SYSTEM_PROMPT_ASK`

The stack is:

| Layer | Technology |
|---|---|
| Backend Framework | FastAPI (Python, async) |
| ODM | Beanie (Motor/AsyncIOMotorClient) |
| Database | MongoDB Atlas |
| Embedding Model | OpenAI `text-embedding-ada-002` |
| LLM | OpenAI `gpt-4o-mini` |
| PDF Extraction | PyMuPDF (`fitz`) |
| Audio Transcription | OpenAI Whisper (`small` model) |
| Video Download | `yt-dlp` |

---

## 2. Data Ingestion Pipeline

The system supports two source types. Both share the **same downstream chunking → embedding → storage pipeline**.

### 2.1 PDF Ingestion (`upload_pdf.py`)

```
[Admin Uploads PDF bytes]
        │
        ▼
[PyMuPDF: Extract text page-by-page]
        │  (each page is a dict: {page_number, text})
        ▼
[clean_text(): collapse whitespace, normalize newlines]
        │
        ▼
[chunk_document(): recursive character splitter]
        │  (chunked with page_number metadata preserved)
        ▼
[get_embeddings(): OpenAI Ada-002 in batches of 100]
        │
        ▼
[KnowledgeChunk.insert_many() → MongoDB Atlas]
        │
        ▼
[sample_document_text() → generate_and_save_knowledge_card()]
        │
        ▼
[Lecture.status = "completed"]
```

**Key detail:** The PDF is processed entirely in memory — `fitz.open(stream=io.BytesIO(pdf_bytes))` — no file is ever written to disk after the initial upload.

### 2.2 Video Ingestion (`video_processor.py`)

The video pipeline has a **two-path transcription strategy** to minimize cost and latency:

```
[Admin provides Video URL (e.g. YouTube)]
        │
        ▼
[Fast Path: fetch_subtitles() via yt-dlp]
        │  ─ If English VTT/subtitles exist → parse and use them
        │
        │  ─ If no subtitles found:
        ▼
[Slow Path: yt-dlp downloads best-audio → converts to MP3 @ 192kbps]
        │
        ▼
[Whisper 'small' model transcribes MP3]
        │  (model is a lazy singleton, loaded once per process lifetime)
        ▼
[MP3 deleted in try/finally block (guaranteed cleanup)]
        │
        ▼
[Same downstream pipeline: clean → chunk → embed → save → KnowledgeCard]
```

**Async design:** The blocking Whisper transcription runs in a thread pool via `asyncio.to_thread()` to avoid blocking the async event loop.

---

## 3. Chunking Strategy

**File:** `app/knowledge/chunking.py` — `recursive_character_text_splitter()`

### Parameters (hardcoded defaults)

| Parameter | Value | Rationale |
|---|---|---|
| `chunk_size` | **1000 characters** | Balances enough context per chunk vs. embedding cost |
| `chunk_overlap` | **200 characters** | Prevents answer fragmentation at chunk boundaries |

### Algorithm: Recursive Character Splitter

The splitter uses a **priority-ordered separator hierarchy** to find the most semantically natural break point within the allowed window:

```python
for separator in ["\n\n", "\n", ". ", " "]:
    sep_idx = text.rfind(separator, start, end)
    if sep_idx != -1:
        break_point = sep_idx + len(separator)
        break
```

**Priority order:**
1. `\n\n` — Paragraph boundary (preferred, most semantic)
2. `\n` — Line break
3. `. ` — End of sentence
4. ` ` — Word boundary (last resort, avoids mid-word splits)

This means the splitter will **never blindly cut at exactly 1000 chars**; it walks backwards from the 1000-char mark to find the nearest paragraph, sentence, or at minimum a word boundary.

**Overlap implementation:**
```python
start = break_point - chunk_overlap  # next chunk starts 200 chars before the previous end
```
This ensures that a concept split across the previous chunk's tail is captured again at the start of the next chunk.

### Cross-Page Context Preservation (`chunk_document()`)

A naive chunker would reset at every page boundary, breaking concepts that span pages. Lecture Brain solves this by:

1. **Concatenating all pages** into a single string with `\n\n` separators.
2. Tracking each page's **character offset** in `page_offsets`.
3. Running the splitter on the **entire document** at once.
4. Using `bisect.bisect_right()` to **map each resulting chunk back** to the page it originated from.

Result: chunks correctly cross page boundaries while still carrying accurate `page_number` source attribution.

### Document Sampling for Knowledge Card (`sample_document_text()`)

For the Knowledge Card generation, sending the entire document to the LLM would be token-prohibitive. Instead, a **stratified sampling** approach extracts a representative 12,000-character sample:

| Sample Region | Allocation | Purpose |
|---|---|---|
| Beginning (`0 → max/2`) | **50%** (6,000 chars) | Introduction, definitions, key concepts |
| Middle (`n/2 ± max/8`) | **25%** (3,000 chars) | Core body content |
| End (`-max/4`) | **25%** (3,000 chars) | Summary, conclusions, examples |

This is far superior to a naive `text[:12000]` truncation for documents that front-load boilerplate.

---

## 4. Embedding Model

**File:** `app/knowledge/embeddings.py`

| Property | Value |
|---|---|
| Model | `text-embedding-ada-002` |
| Provider | OpenAI API |
| Output Dimensions | **1536 floats** |
| Batch size | **100 texts per API call** |
| Client | Shared async `openai_client` singleton |

```python
response = await openai_client.embeddings.create(
    input=texts,
    model="text-embedding-ada-002"  # outputs 1536-dim vectors
)
```

**Why Ada-002?** It is OpenAI's most cost-effective embedding model, well-suited for semantic similarity tasks at educational document scale. Its 1536-dimensional space provides rich semantic representation without the cost of newer, larger models.

**Batching:** Chunks are embedded in batches of 100 (`BATCH_SIZE = 100`) to minimize round-trip latency to the OpenAI API while staying within rate limits.

---

## 5. MongoDB Atlas Vector Search

**File:** `app/database/mongodb.py` — `vector_search()`

### Atlas Search Index Configuration

The vector search requires a pre-configured **Atlas Search Index** named `vector_index` on the `knowledge_chunks` collection:

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1536,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "lecture_id"
    }
  ]
}
```

### The `$vectorSearch` Aggregation Pipeline

```python
pipeline = [
    {
        "$vectorSearch": {
            "index": "vector_index",
            "path": "embedding",           # field storing the 1536-dim vector
            "queryVector": query_embedding, # 1536-dim vector of the student's question
            "numCandidates": limit * 10,   # ANN search pool = 50 candidates
            "limit": limit                 # return top 5 results
        }
    }
]
```

**`numCandidates` = `limit × 10`:** This is the HNSW (Hierarchical Navigable Small World) approximate nearest neighbor search pool size. A larger pool improves recall accuracy at the cost of slightly more compute. The `10×` multiplier is a well-established production heuristic.

### Lecture-Scoped Filtering

When a `lecture_id` is provided, a pre-filter is injected into the `$vectorSearch` stage:

```python
pipeline[0]["$vectorSearch"]["filter"] = {
    "lecture_id": { "$eq": lecture_id }
}
```

> **Design Decision:** `KnowledgeChunk` stores `lecture_id` as a **flat string field** alongside the Beanie `Link[Lecture]` foreign reference. This is intentional — MongoDB Atlas `$vectorSearch` pre-filters require a scalar field, not a `DBRef`. The denormalized string enables performant, index-friendly filtering without a join.

### Score Projection

```python
pipeline.append({
    "$project": {
        "_id": 1,
        "text": 1,
        "lecture_id": 1,
        "page_number": 1,
        "score": { "$meta": "vectorSearchScore" }  # cosine similarity score
    }
})
```

The `vectorSearchScore` metadata field exposes the cosine similarity score for each result, which is surfaced in the API response as the source citation: `"Page 4 (Similarity: 0.89)"`.

---

## 6. Hybrid Context Construction

**File:** `app/ai/ask.py` — `build_context()`

This is the core RAG innovation in Lecture Brain. Rather than relying solely on retrieved vector chunks (which only capture local semantics), the system builds a **two-layer context** for every query.

### Layer 1: Global Context — The Knowledge Card

```python
card = await KnowledgeCard.find_one(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id))
global_context = f"""Global Summary: {card.summary}
Key Points: {', '.join(card.key_points)}
Concepts: {', '.join(card.concepts)}
Important Details: {card.important_details}
Examples: {', '.join(card.examples)}"""
```

The Knowledge Card is a pre-generated, LLM-distilled summary of the **entire lecture** (see Section 8). It provides the model with:
- What the lecture is fundamentally about
- The key points and named concepts
- Important formulas, dates, and definitions
- Representative examples

**Purpose:** Prevents the model from giving a narrow answer based only on a small retrieved chunk. The global summary provides orientation and allows the LLM to reason about where a specific chunk fits in the bigger picture.

### Layer 2: Local Context — Top-5 Vector Chunks

```python
results = await vector_search(query_embedding=query_embeddings[0], limit=5, lecture_id=lecture_id)

for idx, doc in enumerate(results):
    retrieved_chunks += f"\n--- Chunk {idx + 1} (Page {page}) ---\n{text}\n"
    sources.append(f"Page {page} (Similarity: {score:.2f})")
```

The vector search retrieves the **5 most semantically similar chunks** to the student's specific question. This provides:
- Precise, verbatim text from the lecture
- The exact passage most likely to contain the answer
- Page number attribution for source citations

### How They Combine in the Prompt

```
SYSTEM PROMPT
├── Global Context (Knowledge Card)       ← "Here is what this lecture is about"
│    ├── Summary
│    ├── Key Points
│    ├── Concepts
│    └── Important Details
│
└── Retrieved Chunks (Vector Search Top-5)  ← "Here is the specific relevant text"
     ├── Chunk 1 (Page 3) — 1000 chars
     ├── Chunk 2 (Page 7) — 1000 chars
     ├── ...
     └── Chunk 5 (Page 12) — 1000 chars
```

### Why Hybrid > Pure Vector Search

| Scenario | Pure Vector Search | Hybrid (Card + Chunks) |
|---|---|---|
| "What is this lecture about?" | Returns one random relevant chunk | Returns the distilled summary |
| "Give me an example of X" | May miss examples in unretrieved pages | Knowledge Card preserves all examples |
| "How does Y relate to Z?" | Only has local context | Global context enables relational reasoning |
| Precise quote questions | ✅ Chunk retrieval works well | ✅ Also works |

---

## 7. LLM Inference Layer

**File:** `app/ai/ask.py` — `generate_answer()`

| Property | Value |
|---|---|
| Model | `gpt-4o-mini` |
| Temperature | `0.2` (very deterministic, factual) |
| Context Window | System prompt + chat history + user message |

```python
messages = [{"role": "system", "content": prompt}]
if history:
    messages.extend(history)   # multi-turn conversation support
messages.append({"role": "user", "content": message})
```

**Multi-turn support:** The chat history (`List[Message]`) is prepended between the system prompt and the new user message, enabling coherent follow-up questions within a session.

**Post-response:** The Q&A pair is saved to `ChatLog` as a **non-blocking async task** (`asyncio.create_task`) so it never delays the response to the student.

---

## 8. Knowledge Card: Global Context Layer

**File:** `app/knowledge/knowledge_card.py`

The Knowledge Card solves a fundamental RAG problem: *"What do I do about questions that require understanding the whole document, not just a retrieved chunk?"*

### Generation

```python
response = await openai_client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": prompt}],
    response_format={ "type": "json_object" },
    temperature=0.7   # slightly creative for richer summaries
)
```

The LLM is instructed to produce a strict JSON object:

```json
{
  "summary": "3-4 sentence overview of the entire lecture",
  "key_points": ["main point 1", "main point 2"],
  "concepts": ["concept1", "concept2"],
  "important_details": "Critical formulas, dates, definitions",
  "examples": ["example 1", "example 2"]
}
```

### Multi-Source Merging

When a second source (e.g., a video) is added to an existing lecture that already has a Knowledge Card from a PDF, the system **merges** rather than replaces:

```python
if existing_card:
    prompt += f"""
    This lecture already has an existing knowledge card. Please MERGE the new text's insights
    with the existing card's data to create a comprehensive global summary.

    Existing Summary: {existing_card.summary}
    Existing Concepts: {', '.join(existing_card.concepts)}
    ...
    """
```

This makes the Knowledge Card a living, accumulating document that grows richer as more sources are added to a lecture.

---

## 9. End-to-End RAG Query Flow

```
Student asks: "What is eventual consistency?"
        │
        ▼
POST /ai/ask  {message, lecture_id, history}
        │
        ▼
[Validate: lecture exists, user owns subject]
        │
        ▼
build_context(lecture_id, query)
    ├── [1] KnowledgeCard lookup              → global_context string
    └── [2] get_embeddings([query])           → 1536-dim query vector
                │
                ▼
           vector_search(query_vector, limit=5, lecture_id)
                │  ($vectorSearch in MongoDB Atlas, filtered to this lecture)
                ▼
           Top-5 KnowledgeChunks              → retrieved_chunks string
        │
        ▼
Assemble messages:
    [system: SYSTEM_PROMPT_ASK.format(global_context, retrieved_chunks)]
    [prior history messages...]
    [user: "What is eventual consistency?"]
        │
        ▼
gpt-4o-mini (temperature=0.2)
        │
        ▼
Return: { answer: "...", sources: ["Page 4 (Similarity: 0.91)", ...] }
        │
        └──► asyncio.create_task(_save_chat_log(...))  [non-blocking]
```

---

## 10. Data Models Reference

### `KnowledgeChunk` (collection: `knowledge_chunks`)

| Field | Type | Description |
|---|---|---|
| `lecture` | `Link[Lecture]` | Beanie DBRef to the parent Lecture |
| `lecture_id` | `str` | Denormalized flat copy for `$vectorSearch` filter |
| `text` | `str` | The raw chunk text (~1000 chars) |
| `page_number` | `int?` | Source page (PDF) or `1` (video) |
| `embedding` | `List[float]` | 1536-dimensional Ada-002 vector |

### `KnowledgeCard` (collection: `knowledge_cards`)

| Field | Type | Description |
|---|---|---|
| `lecture` | `Link[Lecture]` | Parent lecture reference |
| `summary` | `str` | 3-4 sentence whole-document overview |
| `key_points` | `List[str]` | Main takeaways |
| `concepts` | `List[str]` | Named concepts and terminology |
| `important_details` | `str` | Formulas, dates, definitions |
| `examples` | `List[str]` | Concrete examples from the text |

### `JobTracker` (embedded in `Lecture`)

| Field | Values | Description |
|---|---|---|
| `upload_status` | `pending/processing/completed/failed` | Source file received |
| `extraction_status` | `pending/processing/completed/failed` | Text/audio extracted |
| `chunking_status` | `pending/processing/completed/failed` | Text split into chunks |
| `embedding_status` | `pending/processing/completed/failed` | Vectors generated & saved |
| `card_generation_status` | `pending/processing/completed/failed` | KnowledgeCard built |
| `error_traceback` | `str?` | Stack trace if any stage failed |
