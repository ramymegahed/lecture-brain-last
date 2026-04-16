import asyncio
import logging
from beanie import PydanticObjectId

logger = logging.getLogger(__name__)

from app.models.lecture import Lecture
from app.models.knowledge import KnowledgeChunk
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card
from app.knowledge.chunking import chunk_document, clean_text, sample_document_text

async def process_text_background(lecture_id: str, text: str):
    """
    Background task to process raw text.
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        logger.error(f"Lecture {lecture_id} not found during processing.")
        return

    try:
        # clean_text (regex) and chunk_document (while-loop) are CPU-bound.
        # Run them in the thread pool so they do not block the asyncio event loop.
        cleaned_text = await asyncio.to_thread(clean_text, text)
        del text  # release raw input — cleaned_text is now the canonical copy
        pages = [{"page_number": 1, "text": cleaned_text}]
        del cleaned_text  # release before chunking; `pages` holds the only copy needed

        chunks = await asyncio.to_thread(chunk_document, pages)
        del pages  # chunker has consumed pages; free before the embedding loop

        BATCH_SIZE = 100
        for i in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[i:i + BATCH_SIZE]
            texts_to_embed = [item["text"] for item in batch]
            
            embeddings = await get_embeddings(texts_to_embed)
            
            knowledge_chunks = []
            for j, item in enumerate(batch):
                kc = KnowledgeChunk(
                    lecture=lecture,
                    lecture_id=lecture_id,
                    text=item["text"],
                    page_number=item["page_number"],
                    embedding=embeddings[j]
                )
                knowledge_chunks.append(kc)
                
            if knowledge_chunks:
                await KnowledgeChunk.insert_many(knowledge_chunks)

        # BUG FIX: `text` was deleted above; re-derive the sample from chunks
        # (same approach used in video_processor.py after the memory refactor).
        sample_text = sample_document_text(" ".join(c["text"] for c in chunks))
        await generate_and_save_knowledge_card(lecture_id, sample_text)

        for source in lecture.sources:
            if source.type == "text" and source.status == "processing":
                source.status = "completed"
                break
        lecture.status = "completed" if all(s.status == "completed" for s in lecture.sources) else "processing"
        await lecture.save()

    except Exception as e:
        logger.error(f"Error processing text for lecture {lecture_id}: {e}", exc_info=True)
        for source in lecture.sources:
            if source.type == "text" and source.status == "processing":
                source.status = "failed"
                source.error = str(e)
                break
        lecture.status = "failed"
        await lecture.save()
