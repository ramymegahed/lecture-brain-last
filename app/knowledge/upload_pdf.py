import fitz  # PyMuPDF
import asyncio
from beanie import PydanticObjectId

from app.models.lecture import Lecture
from app.models.knowledge import KnowledgeChunk
from app.knowledge.chunking import chunk_document, clean_text
from app.knowledge.embeddings import get_embeddings
from app.knowledge.knowledge_card import generate_and_save_knowledge_card

async def process_pdf_background(lecture_id: str, file_path: str):
    """
    Background task to process a PDF:
    1. Extract text via PyMuPDF
    2. Chunk text
    3. Generate embeddings
    4. Save to MongoDB (Atlas Vector Search enabled collection)
    5. Generate a Knowledge Card (Global context)
    6. Update Lecture status
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        print(f"Lecture {lecture_id} not found during processing.")
        return

    try:
        # 1. Extract text with page numbers
        doc = fitz.open(file_path)
        pages = []
        full_text = ""
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = clean_text(page.get_text())
            full_text += text + "\n"
            pages.append({"page_number": page_num + 1, "text": text})
            
        doc.close()

        # 2. Chunk text
        chunks = chunk_document(pages)
        
        # 3 & 4. Embed and Save in batches
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

        # 5. Generate Knowledge Card using full text (or a sample if too large)
        # To avoid token limits, we might summarize the first N chars
        sample_text = full_text[:15000] # Adjust according to context window
        await generate_and_save_knowledge_card(lecture_id, sample_text)

        # 6. Update status
        for source in lecture.sources:
            if source.url == file_path:
                source.status = "completed"
        lecture.status = "completed" if all(s.status == "completed" for s in lecture.sources) else "processing"
        await lecture.save()

    except Exception as e:
        print(f"Error processing PDF {file_path}: {e}")
        for source in lecture.sources:
            if source.url == file_path:
                source.status = "failed"
                source.error = str(e)
        lecture.status = "failed"
        await lecture.save()
