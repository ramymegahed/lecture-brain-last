from typing import Tuple
from beanie import PydanticObjectId

from app.core.clients import openai_client

from app.ai.ask import build_context
from app.ai.prompts import SYSTEM_PROMPT_EXPLAIN
from app.models.lecture import Lecture
from app.models.subject import Subject

async def generate_explanation(concept: str, lecture_id: str, user_id: PydanticObjectId) -> str:
    """
    Explain a specific concept based on lecture material.
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise ValueError("Lecture not found")

    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(user_id):
        raise ValueError("Access denied")

    global_ctx, retrieved_chunks, _ = await build_context(lecture_id, concept)
    
    prompt = SYSTEM_PROMPT_EXPLAIN.format(
        global_context=global_ctx,
        retrieved_chunks=retrieved_chunks,
        concept=concept
    )

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )
    
    return response.choices[0].message.content
