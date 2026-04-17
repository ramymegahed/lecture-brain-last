from typing import Tuple, List
from beanie import PydanticObjectId

from app.models.knowledge_card import KnowledgeCard
from app.models.lecture import Lecture
from app.models.subject import Subject

async def get_lecture_summary(lecture_id: str, user_id: PydanticObjectId) -> KnowledgeCard:
    """
    Fetch the pre-computed Knowledge Card for a lecture.
    """
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise ValueError("Lecture not found")

    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(user_id):
        raise ValueError("Access denied")

    card = await KnowledgeCard.find_one({"lecture.$id": PydanticObjectId(lecture_id)})
    
    if not card:
        return None
        
    return card
