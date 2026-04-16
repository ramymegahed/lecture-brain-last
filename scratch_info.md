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
