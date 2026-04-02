from typing import List, Optional
from beanie import Document, Link
from pydantic import BaseModel, Field
from datetime import datetime, timezone
from app.models.subject import Subject

class LectureSource(BaseModel):
    type: str           # "pdf" | "video" | "text"
    url: str            # local path or video URL
    status: str = "pending"   # pending | processing | completed | failed
    error: Optional[str] = None

class Lecture(Document):
    title: str = Field(..., max_length=150)
    description: str = Field(default="")
    subject: Link[Subject]
    sources: List[LectureSource] = Field(default_factory=list)
    status: str = Field(default="pending") # pending, processing, completed, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Settings:
        name = "lectures"
