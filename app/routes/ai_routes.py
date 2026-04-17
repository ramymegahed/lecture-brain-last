from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.ai_schema import ChatRequest, ChatResponse, ChatHistoryResponse, ExplainRequest, ExplainResponse, SummaryResponse, QuizResponse, Message
from app.models.user import User
from app.auth.dependencies import get_current_active_user

# Will implement these in app.ai
from app.ai.ask import generate_answer, generate_answer_stream
from app.ai.explain import generate_explanation
from app.ai.summary import get_lecture_summary
from app.ai.quiz import generate_quiz

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


@router.get("/chat/history/{lecture_id}", response_model=ChatHistoryResponse, tags=["AI Inference"])
async def get_chat_history(
    lecture_id: str,
    current_user: User = Depends(get_current_active_user)
):
    from app.models.lecture import Lecture
    from app.models.subject import Subject
    from beanie import PydanticObjectId
    from app.models.chat_log import ChatLog

    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    logs = await ChatLog.find(
        ChatLog.lecture_id == lecture_id,
        ChatLog.action_type == "chat"
    ).sort(+ChatLog.created_at).to_list()
    
    history_messages = []
    for log in logs:
        history_messages.append(Message(role="user", content=log.question))
        history_messages.append(Message(role="assistant", content=log.answer))
        
    return ChatHistoryResponse(history=history_messages)

@router.post("/chat/stream", tags=["AI Inference"])
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user)
):
    """
    Server-Sent Events (SSE) streaming endpoint for real-time AI chat.

    Returns a `text/event-stream` response. Each event is a JSON object:
    - `{"type": "sources", "sources": [...]}` — emitted first with citation list
    - `{"type": "token", "content": "..."}` — one event per generated token
    - `{"type": "done"}` — signals stream completion

    The original `/ai/chat` endpoint (blocking JSON) is preserved for non-SSE consumers.
    """
    history_dicts = [h.model_dump() for h in request.history[-6:]]

    # Validate access BEFORE starting the generator — once StreamingResponse begins,
    # HTTP headers are committed and we can no longer return a 4xx status code.
    from app.models.lecture import Lecture
    from app.models.subject import Subject
    from beanie import PydanticObjectId

    lecture = await Lecture.get(PydanticObjectId(request.lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")

    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    generator = generate_answer_stream(
        message=request.message,
        lecture_id=request.lecture_id,
        user_id=current_user.id,
        history=history_dicts
    )

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disables Nginx/Railway proxy buffering
        }
    )

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
