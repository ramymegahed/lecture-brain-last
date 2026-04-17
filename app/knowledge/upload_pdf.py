import asyncio
import io
import logging
import fitz  # PyMuPDF
from beanie import PydanticObjectId

logger = logging.getLogger(__name__)

from app.models.lecture import Lecture, update_job_status
from app.models.knowledge import KnowledgeChunk
from app.knowledge.chunking import chunk_document, clean_text, sample_document_text
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card


def _extract_pages_from_bytes(pdf_bytes_inner: bytes):
    """
    Synchronous helper: open a PDF from raw bytes and extract per-page text.
    Designed to run inside asyncio.to_thread() so it never blocks the event loop.

    Uses a list-then-join pattern for building full_text which is O(n) across
    pages, compared to the += operator which creates a new string object on every
    iteration and is O(n²) for large documents.
    """
    doc = fitz.open(stream=io.BytesIO(pdf_bytes_inner), filetype="pdf")
    pages = []
    full_text_parts = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = clean_text(page.get_text())
        full_text_parts.append(text)
        pages.append({"page_number": page_num + 1, "text": text})
    doc.close()
    return pages, "\n".join(full_text_parts)


async def process_pdf_background(lecture_id: str, pdf_bytes: bytes):
    """
    Background task to process a PDF entirely in memory — no local file is kept.

    Pipeline:
    1. Open PDF from raw bytes using PyMuPDF (no disk I/O after this point)
    2. Extract text page-by-page
    3. Chunk text with page-number metadata
    4. Generate OpenAI embeddings in batches of 100
    5. Save KnowledgeChunks to MongoDB
    6. Generate KnowledgeCard (global context summary)
    7. Update Lecture status to 'completed' or 'failed'
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        logger.error(f"Lecture {lecture_id} not found during processing.")
        return

    try:
        await update_job_status(lecture_id, "upload_status", "completed")
        await update_job_status(lecture_id, "extraction_status", "processing")
        # 1 & 2. Run the synchronous PyMuPDF extraction in a thread pool so it never
        # blocks the asyncio event loop. The helper also switches from += (O(n²))
        # to list-join (O(n)) for building full_text across pages.
        pages, full_text = await asyncio.to_thread(_extract_pages_from_bytes, pdf_bytes)
        del pdf_bytes  # our reference is no longer needed — the thread has its own copy
        await update_job_status(lecture_id, "extraction_status", "completed")

        # 3. Chunk text (preserving page numbers)
        # chunk_document() is a CPU-bound while-loop — run in a thread pool so it
        # does not stall the event loop (and therefore does not stall other uploads).
        await update_job_status(lecture_id, "chunking_status", "processing")
        chunks = await asyncio.to_thread(chunk_document, pages)
        del pages  # chunker has consumed pages; free before the embedding loop
        await update_job_status(lecture_id, "chunking_status", "completed")

        # 4 & 5. Embed and save in batches of 100
        await update_job_status(lecture_id, "embedding_status", "processing")
        BATCH_SIZE = 100
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            texts_to_embed = [item["text"] for item in batch]
            embeddings = await get_embeddings(texts_to_embed)

            knowledge_chunks = [
                KnowledgeChunk(
                    lecture=lecture,
                    lecture_id=lecture_id,
                    text=item["text"],
                    page_number=item["page_number"],
                    embedding=embeddings[j],
                )
                for j, item in enumerate(batch)
            ]
            if knowledge_chunks:
                await KnowledgeChunk.insert_many(knowledge_chunks)
        await update_job_status(lecture_id, "embedding_status", "completed")

        # 6. Generate Knowledge Card from a representative sample of the text
        await update_job_status(lecture_id, "card_generation_status", "processing")
        sample_text = sample_document_text(full_text)
        del full_text  # release the accumulated page-text string; sample_text holds the excerpt
        await generate_and_save_knowledge_card(lecture_id, sample_text)
        await update_job_status(lecture_id, "card_generation_status", "completed")

        # 7. Update status
        lecture = await Lecture.get(PydanticObjectId(lecture_id))
        if lecture:
            for source in lecture.sources:
                if source.type == "pdf" and source.status == "processing":
                    source.status = "completed"
                    break
            lecture.status = "completed" if all(s.status == "completed" for s in lecture.sources) else "processing"
            await lecture.save()

    except Exception as e:
        logger.error(f"Error processing PDF for lecture {lecture_id}: {e}", exc_info=True)
        # Catch-all status update for failure
        await update_job_status(lecture_id, "extraction_status", "failed", error=str(e))
        lecture = await Lecture.get(PydanticObjectId(lecture_id))
        if lecture:
            for source in lecture.sources:
                if source.type == "pdf" and source.status == "processing":
                    source.status = "failed"
                    source.error = str(e)
                    break
            lecture.status = "failed"
            await lecture.save()
