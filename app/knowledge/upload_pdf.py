import io
import logging
import fitz  # PyMuPDF
from beanie import PydanticObjectId

logger = logging.getLogger(__name__)

from app.models.lecture import Lecture
from app.models.knowledge import KnowledgeChunk
from app.knowledge.chunking import chunk_document, clean_text
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card


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
        # 1 & 2. Open from bytes — PyMuPDF accepts a bytes stream directly
        doc = fitz.open(stream=io.BytesIO(pdf_bytes), filetype="pdf")
        pages = []
        full_text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = clean_text(page.get_text())
            full_text += text + "\n"
            pages.append({"page_number": page_num + 1, "text": text})
        doc.close()

        # 3. Chunk text (preserving page numbers)
        chunks = chunk_document(pages)

        # 4 & 5. Embed and save in batches of 100
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

        # 6. Generate Knowledge Card from a representative sample of the text
        sample_text = full_text[:15000]
        await generate_and_save_knowledge_card(lecture_id, sample_text)

        # 7. Update status
        for source in lecture.sources:
            if source.type == "pdf" and source.status == "processing":
                source.status = "completed"
                break
        lecture.status = "completed" if all(s.status == "completed" for s in lecture.sources) else "processing"
        await lecture.save()

    except Exception as e:
        logger.error(f"Error processing PDF for lecture {lecture_id}: {e}", exc_info=True)
        for source in lecture.sources:
            if source.type == "pdf" and source.status == "processing":
                source.status = "failed"
                source.error = str(e)
                break
        lecture.status = "failed"
        await lecture.save()
