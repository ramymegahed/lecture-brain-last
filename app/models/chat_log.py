from beanie import Document, Link
from pydantic import Field
from datetime import datetime, timezone
from app.models.lecture import Lecture
from app.models.subject import Subject

class ChatLog(Document):
    """
    Records each student question for downstream analytics processing.
    
    - analyzed (bool): Flag set to True after this message has been
      included in a SubjectAnalytics batch. Prevents double-counting.
    - subject_id (str): Duplicated string for efficient grouping.
    """
    lecture: Link[Lecture]
    lecture_id: str           # flat copy for simple queries
    subject_id: str           # flat copy for grouping — DO NOT REMOVE
    question: str
    answer: str               # stored for context richness in LLM prompt
    analyzed: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "chat_logs"
        indexes = [
            "lecture_id",
            "subject_id"
        ]
