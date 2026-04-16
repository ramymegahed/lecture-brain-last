import json
import re
from beanie import PydanticObjectId
from typing import Optional

from app.core.clients import openai_client
from app.database.mongodb import vector_search
from app.knowledge.embeddings import get_embeddings
from app.models.lecture import Lecture
from app.models.knowledge_card import KnowledgeCard
from app.models.presentation import Presentation, Slide
from app.ai.prompts import SYSTEM_PROMPT_PRESENTATION

async def generate_presentation(lecture_id: str, force_regenerate: bool = False) -> Presentation:
    """
    Generates or retrieves an AI slide presentation for the given lecture.
    If force_regenerate is True, any existing cache is deleted and recreated.
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise ValueError("Lecture not found")

    # 1. Check Cache
    if not force_regenerate:
        existing = await Presentation.find_one(Presentation.lecture.id == PydanticObjectId(lecture_id))
        if existing:
            return existing
    else:
        # If force regenerating, delete the old one first
        await Presentation.find(Presentation.lecture.id == PydanticObjectId(lecture_id)).delete_all()

    # 2. Fetch Global Context
    card = await KnowledgeCard.find_one(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id))
    global_context = ""
    if card:
        global_context = f"Global Summary: {card.summary}\nKey Points: {', '.join(card.key_points)}\nConcepts: {', '.join(card.concepts)}\nImportant Details: {card.important_details}\nExamples: {', '.join(card.examples)}"

    # 3. Fetch Deep Context via Vector Search
    # We use a broad prompt designed to surface the core educational meat of the lecture
    query = "Core educational concepts, primary definitions, major points, and key examples"
    query_embeddings = await get_embeddings([query])
    
    chunk_context = ""
    if query_embeddings:
        results = await vector_search(query_embedding=query_embeddings[0], limit=15, lecture_id=lecture_id)
        for idx, doc in enumerate(results):
            text = doc.get('text', '')
            chunk_context += f"\n--- Chunk {idx + 1} ---\n{text}\n"

    # 4. LLM Generation
    prompt = SYSTEM_PROMPT_PRESENTATION.format(
        global_context=global_context,
        chunk_context=chunk_context
    )

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": prompt}],
        temperature=0.3
    )

    content = response.choices[0].message.content

    # 5. Sanitize LLM output: strip markdown code fences if the model wrapped JSON in ```json ... ```
    # This MUST happen on the raw string before json.loads() — json.loads() never returns a str.
    content = re.sub(r"^```(?:json)?\s*", "", content.strip(), flags=re.IGNORECASE)
    content = re.sub(r"\s*```$", "", content.strip())

    # 6. Parse and Save
    try:
        parsed = json.loads(content)
    except Exception as e:
        raise ValueError(f"Failed to parse LLM presentation output: {e}")

    slides_data = parsed.get("slides", [])
    slides = []
    for s in slides_data:
        slides.append(Slide(
            slide_number=s.get("slide_number", 0),
            title=s.get("title", "Untitled Slide"),
            bullets=s.get("bullets", []),
            speaker_notes=s.get("speaker_notes", ""),
            suggested_visual=s.get("suggested_visual", "")
        ))

    presentation = Presentation(
        lecture=lecture,
        lecture_id=lecture_id,
        presentation_title=parsed.get("presentation_title", "Auto-Generated Presentation"),
        slides=slides
    )
    
    await presentation.insert()
    return presentation
