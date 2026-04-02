from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

class LectureCreate(BaseModel):
    title: str
    description: Optional[str] = None
    subject_id: str

class LectureUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class LectureResponse(BaseModel):
    id: str
    title: str
    description: str
    subject_id: str
    sources: List[dict] = []
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
