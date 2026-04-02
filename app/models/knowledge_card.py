from beanie import Document, Link
from pydantic import Field
from typing import List
from datetime import datetime, timezone
from app.models.lecture import Lecture

class KnowledgeCard(Document):
    """
    Global context summary for a specific lecture.
    Always included in the context window for any QA regarding this lecture.
    """
    lecture: Link[Lecture]
    summary: str
    key_points: List[str] = Field(default_factory=list)
    concepts: List[str] = Field(default_factory=list)
    important_details: str = Field(default="")
    examples: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Settings:
        name = "knowledge_cards"
