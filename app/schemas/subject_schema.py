from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class SubjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class SubjectResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True
