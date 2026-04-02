from beanie import Document, Link
from pydantic import Field
from datetime import datetime, timezone
from app.models.user import User

class Subject(Document):
    name: str = Field(..., max_length=100)
    description: str = Field(default="")
    owner: Link[User]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    class Settings:
        name = "subjects"
