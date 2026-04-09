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

class JobTracker(BaseModel):
    upload_status: str = "pending"
    extraction_status: str = "pending"
    chunking_status: str = "pending"
    embedding_status: str = "pending"
    card_generation_status: str = "pending"
    error_traceback: Optional[str] = None

class Lecture(Document):
    title: str = Field(..., max_length=150)
    description: str = Field(default="")
    subject: Link[Subject]
    sources: List[LectureSource] = Field(default_factory=list)
    status: str = Field(default="pending") # pending, processing, completed, failed
    job_tracker: JobTracker = Field(default_factory=JobTracker)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Settings:
        name = "lectures"

async def update_job_status(lecture_id: str, step: str, status: str, error: str = None):
    """Safely updates the embedded JobTracker for a given lecture."""
    from beanie import PydanticObjectId
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if lecture and hasattr(lecture.job_tracker, step):
        setattr(lecture.job_tracker, step, status)
        if error:
            lecture.job_tracker.error_traceback = error
        await lecture.save()
