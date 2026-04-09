from beanie import Document, Link
from pydantic import BaseModel, Field
from typing import List
from datetime import datetime, timezone
from app.models.subject import Subject

class WeakTopic(BaseModel):
    topic: str
    frequency_score: int   # 1–10, derived from LLM reasoning

class SubjectAnalytics(Document):
    """
    Stores the most recent AI-generated analytics snapshot for one subject.
    Overwritten (not appended) on each batch run — the LLM merges old+new.
    """
    subject: Link[Subject]
    subject_id: str            # flat copy for filtering
    subject_name: str          # stored for display, so the dashboard doesn't need an extra fetch
    weak_topics: List[WeakTopic] = []
    common_questions: List[str] = []
    confusing_concepts: List[str] = []
    engagement_count: int = 0  # cumulative total chat messages analyzed so far
    ai_insight: str = ""       # one paragraph of free-text AI commentary
    last_analyzed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "subject_analytics"
