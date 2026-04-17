from typing import Tuple, List
from beanie import PydanticObjectId
import asyncio

from app.core.clients import openai_client

from app.database.mongodb import vector_search
from app.knowledge.embeddings import get_embeddings
from app.models.knowledge_card import KnowledgeCard
from app.models.lecture import Lecture
from app.models.subject import Subject
from app.models.chat_log import ChatLog
from app.ai.prompts import SYSTEM_PROMPT_ASK

async def build_context(lecture_id: str, query: str) -> Tuple[str, str, List[str]]:
    """
    Retrieve hybrid context: Global Knowledge Card + Vector retrieved chunks.
    Raises ValueError if lecture validation fails.
    """
    # 1. Fetch Knowledge Card
    card = await KnowledgeCard.find_one(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id))
    global_context = ""
    if card:
        global_context = f"Global Summary: {card.summary}\nKey Points: {', '.join(card.key_points)}\nConcepts: {', '.join(card.concepts)}\nImportant Details: {card.important_details}\nExamples: {', '.join(card.examples)}"
        
    # 2. Get embeddings for query
    query_embeddings = await get_embeddings([query])
    if not query_embeddings:
        return global_context, "", []

    # 3. Vector Search
    results = await vector_search(query_embedding=query_embeddings[0], limit=8, lecture_id=lecture_id)
    
    retrieved_chunks = ""
    sources = []
    
    for idx, doc in enumerate(results):
        score = doc.get('score', 0)
        page = doc.get('page_number', 'unknown')
        text = doc.get('text', '')
        
        sources.append(f"Page {page} (Similarity: {score:.2f})")
        retrieved_chunks += f"\n--- Chunk {idx + 1} (Source: Page / Timestamp: {page}) ---\n{text}\n"

    return global_context, retrieved_chunks, sources

async def fetch_chat_history(lecture_id: str, limit: int = 6) -> List[dict]:
    """Fetch the most recent chat logs to build short-term conversational memory."""
    logs = await ChatLog.find(ChatLog.lecture_id == lecture_id).sort(-ChatLog.created_at).limit(limit//2).to_list()
    # Reverse to chronological order
    logs.reverse()
    
    history = []
    for log in logs:
        history.append({"role": "user", "content": log.question})
        history.append({"role": "assistant", "content": log.answer})
    return history

async def _save_chat_log(lecture: Lecture, message: str, answer: str):
    """Awaitable save to guarantee the record is securely stored in MongoDB."""
    try:
        log = ChatLog(
            lecture=lecture,
            lecture_id=str(lecture.id),
            subject_id=str(lecture.subject.ref.id),
            question=message,
            answer=answer,
        )
        await log.insert()
    except Exception as e:
        print(f"Failed to save chat log: {e}")

async def generate_answer(message: str, lecture_id: str, user_id: PydanticObjectId, history: List[dict] = None) -> Tuple[str, List[str]]:
    """
    Generate an answer to the student's question using RAG and optional chat history.
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise ValueError("Lecture not found")

    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(user_id):
        raise ValueError("Access denied")
    
    global_ctx, retrieved_chunks, sources = await build_context(lecture_id, message)
    
    prompt = SYSTEM_PROMPT_ASK.format(
        global_context=global_ctx,
        retrieved_chunks=retrieved_chunks
    )

    db_history = await fetch_chat_history(lecture_id, limit=6)

    messages = [{"role": "system", "content": prompt}]
    # Override client history with authenticated, verified DB history
    messages.extend(db_history)
    messages.append({"role": "user", "content": message})

    response = await openai_client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0.2
    )
    
    answer = response.choices[0].message.content
    
    # Synchronously await saving to guarantee no lost context or state fragmentation
    await _save_chat_log(lecture, message, answer)
    
    return answer, sources


async def generate_answer_stream(
    message: str,
    lecture_id: str,
    user_id: PydanticObjectId,
    history: List[dict] = None
):
    """
    Streaming variant of generate_answer(). 
    Async generator that yields SSE-formatted token chunks as they arrive from OpenAI.
    The full assembled answer is logged to ChatLog after streaming completes.
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise ValueError("Lecture not found")

    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(user_id):
        raise ValueError("Access denied")

    global_ctx, retrieved_chunks, sources = await build_context(lecture_id, message)

    prompt = SYSTEM_PROMPT_ASK.format(
        global_context=global_ctx,
        retrieved_chunks=retrieved_chunks
    )
    
    db_history = await fetch_chat_history(lecture_id, limit=6)

    messages = [{"role": "system", "content": prompt}]
    messages.extend(db_history)
    messages.append({"role": "user", "content": message})

    # Yield sources metadata as the first SSE event so the client knows the citations
    import json as _json
    yield f"data: {_json.dumps({'type': 'sources', 'sources': sources})}\n\n"

    full_answer = []
    try:
        async with await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.2,
            stream=True
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_answer.append(delta)
                    # Yield each token chunk as an SSE data event
                    yield f"data: {_json.dumps({'type': 'token', 'content': delta})}\n\n"

        # Signal stream completion
        yield f"data: {_json.dumps({'type': 'done'})}\n\n"
    finally:
        # Guarantee saving even if client disconnects mid-stream or generates partial tokens
        assembled_answer = "".join(full_answer)
        if assembled_answer:
            await _save_chat_log(lecture, message, assembled_answer)

