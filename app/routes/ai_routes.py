from fastapi import APIRouter, Depends, HTTPException, Query
from app.schemas.ai_schema import ChatRequest, ChatResponse, ExplainRequest, ExplainResponse, SummaryResponse, QuizResponse, PresentationResponse
from app.models.user import User
from app.auth.dependencies import get_current_active_user

# Will implement these in app.ai
from app.ai.ask import generate_answer
from app.ai.explain import generate_explanation
from app.ai.summary import get_lecture_summary
from app.ai.quiz import generate_quiz
from app.ai.presentation import generate_presentation

router = APIRouter(prefix="/ai", tags=["AI Inference"])

@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user)
):
    try:
        # Limit history to the last 6 messages (3 turns)
        history_dicts = [h.model_dump() for h in request.history[-6:]]
        answer, sources = await generate_answer(request.message, request.lecture_id, current_user.id, history_dicts)
        return ChatResponse(answer=answer, sources=sources)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.post("/explain", response_model=ExplainResponse)
async def explain_concept(
    request: ExplainRequest,
    current_user: User = Depends(get_current_active_user)
):
    try:
        explanation = await generate_explanation(request.concept, request.lecture_id, current_user.id)
        return ExplainResponse(explanation=explanation)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("/summary/{lecture_id}", response_model=SummaryResponse)
async def get_summary(
    lecture_id: str,
    current_user: User = Depends(get_current_active_user)
):
    try:
        card = await get_lecture_summary(lecture_id, current_user.id)
        if not card:
             raise HTTPException(status_code=404, detail="Summary not available yet")
        return SummaryResponse(
            lecture_id=lecture_id,
            summary=card.summary,
            key_points=card.key_points,
            concepts=card.concepts,
            important_details=card.important_details,
            examples=card.examples
        )
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.post("/quiz/{lecture_id}", response_model=QuizResponse)
async def create_quiz(
    lecture_id: str,
    current_user: User = Depends(get_current_active_user)
):
    try:
        return await generate_quiz(lecture_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@router.get("/presentation/{lecture_id}", response_model=PresentationResponse)
async def create_presentation(
    lecture_id: str,
    force_regenerate: bool = Query(False, description="Set to true to ignore the cache and generate a new deck"),
    current_user: User = Depends(get_current_active_user)
):
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
