import os
import json
from beanie import PydanticObjectId
from typing import List

from app.core.clients import openai_client

from app.models.lecture import Lecture
from app.models.subject import Subject
from app.models.knowledge_card import KnowledgeCard
from app.ai.prompts import SYSTEM_PROMPT_QUIZ
from app.schemas.ai_schema import QuizQuestion, QuizResponse, QuizOption

async def generate_quiz(lecture_id: str, user_id: PydanticObjectId) -> QuizResponse:
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise ValueError("Lecture not found")

    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(user_id):
        raise ValueError("Access denied")

    card = await KnowledgeCard.find_one(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id))
    global_context = ""
    if card:
        global_context = f"Summary: {card.summary}\nKey Points: {', '.join(card.key_points)}\nConcepts: {', '.join(card.concepts)}\nImportant Details: {', '.join(card.important_details)}"

    prompt = SYSTEM_PROMPT_QUIZ.format(global_context=global_context)

    response = await openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    try:
        content = response.choices[0].message.content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        data = json.loads(content)
        
        questions = []
        for q in data:
            options = [QuizOption(id=opt["id"], text=opt["text"]) for opt in q["options"]]
            questions.append(
                QuizQuestion(
                    question=q["question"],
                    options=options,
                    correct_option_id=q["correct_option_id"],
                    explanation=q["explanation"]
                )
            )
            
        return QuizResponse(lecture_id=lecture_id, questions=questions)
    except Exception as e:
        print(f"Error parsing quiz JSON: {e}")
        print(response.choices[0].message.content)
        raise ValueError("Failed to generate quiz properly")
