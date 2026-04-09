from pydantic import BaseModel
from typing import List
from datetime import datetime

class WeakTopicResponse(BaseModel):
    topic: str
    frequency_score: int

class SubjectAnalyticsResponse(BaseModel):
    subject_id: str
    subject_name: str
    weak_topics: List[WeakTopicResponse]
    common_questions: List[str]
    confusing_concepts: List[str]
    engagement_count: int
    ai_insight: str
    last_analyzed_at: datetime

class AnalyticsTriggerResponse(BaseModel):
    subjects_processed: int
    total_messages_analyzed: int
    message: str
