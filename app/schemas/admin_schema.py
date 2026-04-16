from pydantic import BaseModel
from typing import List, Optional
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

class SystemAnalyticsResponse(BaseModel):
    total_subjects: int
    total_lectures: int
    completion_rate: float
    ai_interactions: int

class AnalyticsTriggerResponse(BaseModel):
    subjects_processed: int
    total_messages_analyzed: int
    message: str

class JobTrackerResponse(BaseModel):
    upload_status: Optional[str] = None
    extraction_status: Optional[str] = None
    chunking_status: Optional[str] = None
    embedding_status: Optional[str] = None
    card_generation_status: Optional[str] = None
    error_traceback: Optional[str] = None

class AdminLectureOperationsResponse(BaseModel):
    lecture_id: str
    lecture_name: str
    subject_name: str
    ingestion_status: str
    job_tracker: Optional[JobTrackerResponse] = None
    created_at: datetime

class AdminUploadVideoRequest(BaseModel):
    lecture_id: Optional[str] = None
    url: str
    extract_frames: bool = False

class AdminUploadResponse(BaseModel):
    lecture_id: str
    status: str
    message: str
    warning: Optional[str] = None
