import asyncio
import logging
from beanie import PydanticObjectId

logger = logging.getLogger(__name__)

from app.models.lecture import Lecture
from app.models.knowledge import KnowledgeChunk
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card
from app.knowledge.chunking import chunk_document, clean_text

async def process_text_background(lecture_id: str, text: str):
    """
    Background task to process raw text.
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        logger.error(f"Lecture {lecture_id} not found during processing.")
        return

    try:
        cleaned_text = clean_text(text)
        pages = [{"page_number": 1, "text": cleaned_text}]
        
        chunks = chunk_document(pages)
        
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

        sample_text = text[:15000]
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
