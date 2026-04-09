import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from app.schemas.admin_schema import SubjectAnalyticsResponse, AnalyticsTriggerResponse, AdminLectureOperationsResponse
from app.schemas.ai_schema import PresentationResponse
from app.models.subject_analytics import SubjectAnalytics
from app.models.lecture import Lecture
from app.ai.analytics import generate_subject_analytics
from app.ai.presentation import generate_presentation

router = APIRouter(prefix="/admin", tags=["Admin"])

async def require_admin(x_admin_key: str = Header(...)):
    """Simple shared-secret auth for demo purposes."""
    expected_key = os.getenv("ADMIN_SECRET", "super-secret-admin-key")
    if x_admin_key != expected_key:
        raise HTTPException(status_code=403, detail="Invalid admin key")

@router.post("/analytics/generate", response_model=AnalyticsTriggerResponse, dependencies=[Depends(require_admin)])
async def trigger_analytics_generation():
    """
    Manually triggers batch LLM analysis of all unanalyzed chat logs 
    across all subjects. Useful for live demos.
    """
    try:
        result = await generate_subject_analytics()
        return AnalyticsTriggerResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate analytics: {str(e)}")

@router.get("/analytics", response_model=List[SubjectAnalyticsResponse], dependencies=[Depends(require_admin)])
async def get_all_analytics():
    """
    Returns the most recent analytics dashboard data for all subjects.
    """
    analytics = await SubjectAnalytics.find_all().to_list()
    
    response = []
    for a in analytics:
        weak_topics = [{"topic": wt.topic, "frequency_score": wt.frequency_score} for wt in a.weak_topics]
        
        response.append(SubjectAnalyticsResponse(
            subject_id=a.subject_id,
            subject_name=a.subject_name,
            weak_topics=weak_topics,
            common_questions=a.common_questions,
            confusing_concepts=a.confusing_concepts,
            engagement_count=a.engagement_count,
            ai_insight=a.ai_insight,
            last_analyzed_at=a.last_analyzed_at
        ))
        
    return response

@router.get("/presentation/{lecture_id}", response_model=PresentationResponse, dependencies=[Depends(require_admin)])
async def create_presentation(
    lecture_id: str,
    force_regenerate: bool = Query(False, description="Set to true to ignore the cache and generate a new deck")
):
    """
    Auto-generates a slide deck presentation using RAG from all sources uploaded to the lecture.
    Only accessible by administrators.
    """
    try:
        presentation_doc = await generate_presentation(lecture_id, force_regenerate)
        
        return PresentationResponse(
            lecture_id=lecture_id,
            presentation_title=presentation_doc.presentation_title,
            slides=[s.model_dump() for s in presentation_doc.slides]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate presentation: {str(e)}")

@router.get("/operations", response_model=List[AdminLectureOperationsResponse], dependencies=[Depends(require_admin)])
async def get_admin_operations():
    """
    Returns the processing status of all uploaded lectures for dashboard observability.
    Intended to be polled periodically by the frontend.
    """
    # Fetch all lectures, sorted by newest first
    lectures = await Lecture.find_all().sort("-created_at").to_list()
    
    response = []
    for l in lectures:
        response.append(AdminLectureOperationsResponse(
            lecture_id=str(l.id),
            title=l.title,
            status=l.status,
            job_tracker=l.job_tracker,
            created_at=l.created_at
        ))
        
    return response
