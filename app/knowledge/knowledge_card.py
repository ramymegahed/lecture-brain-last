import json
import logging
from beanie import PydanticObjectId

from app.core.clients import openai_client

logger = logging.getLogger(__name__)

from app.models.lecture import Lecture
from app.models.knowledge_card import KnowledgeCard

async def generate_and_save_knowledge_card(lecture_id: str, document_text: str):
    """
    Uses OpenAI to generate a global summary and key concepts
    from a representative sample of the document.
    Uses the shared openai_client singleton from app.core.clients.
    """
    
    existing_card = await KnowledgeCard.find_one(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id))
    
    prompt = f"""
    You are an expert educational AI. 
    Read the following lecture text and return a JSON object with EXACTLY these fields:
    {{
      "summary": "3-4 sentence overview of the entire lecture",
      "key_points": ["main point 1", "main point 2", ...],
      "concepts": ["concept1", "concept2", ...],
      "important_details": "Any critical formulas, dates, definitions, or facts",
      "examples": ["example 1", "example 2", ...]
    }}
    """
    
    if existing_card:
        prompt += f"""
        This lecture already has an existing knowledge card. Please MERGE the new text's insights with the existing card's data organically to create a comprehensive global summary that accurately represents all combined sources.
        
        Existing Summary: {existing_card.summary}
        Existing Concepts: {', '.join(existing_card.concepts)}
        Existing Key Points: {', '.join(existing_card.key_points)}
        Existing Details: {existing_card.important_details}
        """

    prompt += f"""
    New extracted text to merge:
    {document_text}
    """
    
    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            response_format={ "type": "json_object" },
            temperature=0.7
        )
        
        result_str = response.choices[0].message.content
        data = json.loads(result_str)
        
        lecture = await Lecture.get(PydanticObjectId(lecture_id))
        
        if existing_card:
            existing_card.summary = data.get("summary", existing_card.summary)
            existing_card.key_points = data.get("key_points", existing_card.key_points)
            existing_card.concepts = data.get("concepts", existing_card.concepts)
            existing_card.important_details = data.get("important_details", existing_card.important_details)
            existing_card.examples = data.get("examples", existing_card.examples)
            await existing_card.save()
            return existing_card
        else:
            card = KnowledgeCard(
                lecture=lecture,
                summary=data.get("summary", "No summary generated."),
                key_points=data.get("key_points", []),
                concepts=data.get("concepts", []),
                important_details=data.get("important_details", ""),
                examples=data.get("examples", [])
            )
            await card.insert()
            return card
        
    except Exception as e:
        logger.error(f"Error generating knowledge card for Lecture {lecture_id}: {e}", exc_info=True)
        # In production handling is needed
        return None
