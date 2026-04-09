from typing import List, Optional
from beanie import Document, Link
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from app.models.lecture import Lecture

class Slide(BaseModel):
    slide_number: int
    title: str
    bullets: List[str]
    speaker_notes: str
    suggested_visual: str

class Presentation(Document):
    """
    Stores an AI-generated slide presentation for a given lecture.
    Acts as a cache so presentations load instantly on subsequent requests.
    """
    lecture: Link[Lecture]
    lecture_id: str  # Flat copy for fast querying
    presentation_title: str
    slides: List[Slide]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "presentations"
