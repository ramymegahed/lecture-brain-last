import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Header
from app.schemas.admin_schema import SubjectAnalyticsResponse, AnalyticsTriggerResponse
from app.models.subject_analytics import SubjectAnalytics
from app.ai.analytics import generate_subject_analytics

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
