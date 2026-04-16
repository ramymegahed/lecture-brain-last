from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, status, Query
from beanie import PydanticObjectId
import os

from app.models.lecture import Lecture, LectureSource
from app.models.knowledge import KnowledgeChunk
from app.models.knowledge_card import KnowledgeCard
from app.models.subject import Subject
from app.models.user import User
from app.schemas.knowledge_schema import UploadResponse, UploadTextRequest, UploadVideoRequest
from app.auth.dependencies import get_current_active_user

from app.knowledge.upload_pdf import process_pdf_background
from app.knowledge.upload_text import process_text_background
from app.knowledge.video_processor import process_video_background

router = APIRouter(prefix="/knowledge", tags=["Knowledge Ingestion"])

# uploads/ directory is only needed for temporary video audio files (Whisper fallback)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload_pdf/{lecture_id}", response_model=UploadResponse)
async def upload_pdf(
    lecture_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    replace: bool = Query(False, description="Clear existing knowledge chunks and cards before processing"),
    current_user: User = Depends(get_current_active_user)
):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Lecture not found")
    lecture.subject = subject

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported here")

    if replace:
        await KnowledgeChunk.find(KnowledgeChunk.lecture_id == lecture_id).delete()
        await KnowledgeCard.find(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id)).delete()

    # Read file into memory — no local disk write for PDFs
    pdf_bytes = await file.read()

    # Store source metadata (url is empty — file is not persisted)
    lecture.sources.append(LectureSource(type="pdf", url="", status="processing"))
    lecture.status = "processing"
    await lecture.save()

    # Pass raw bytes to the background task
    background_tasks.add_task(process_pdf_background, lecture_id, pdf_bytes)

    return UploadResponse(
        filename=file.filename,
        lecture_id=lecture_id,
        status="processing",
        message="PDF upload successful, processing started in background"
    )

@router.post("/upload_video/{lecture_id}", response_model=UploadResponse)
async def upload_video(
    lecture_id: str,
    request: UploadVideoRequest,
    background_tasks: BackgroundTasks,
    replace: bool = Query(False, description="Clear existing knowledge chunks and cards before processing"),
    current_user: User = Depends(get_current_active_user)
):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Lecture not found")
    lecture.subject = subject
        
    if replace:
        await KnowledgeChunk.find(KnowledgeChunk.lecture_id == lecture_id).delete()
        await KnowledgeCard.find(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id)).delete()
        
    lecture.sources.append(LectureSource(type="video", url=request.url, status="processing"))
    lecture.status = "processing"
    await lecture.save()

    background_tasks.add_task(process_video_background, lecture_id, request.url)

    return UploadResponse(
        filename=request.url,
        lecture_id=lecture_id,
        status="processing",
        message="Video processing started in background"
    )

@router.post("/upload_text/{lecture_id}", response_model=UploadResponse)
async def upload_text(
    lecture_id: str,
    request: UploadTextRequest,
    background_tasks: BackgroundTasks,
    replace: bool = Query(False, description="Clear existing knowledge chunks and cards before processing"),
    current_user: User = Depends(get_current_active_user)
):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Lecture not found")
    lecture.subject = subject
        
    if replace:
        await KnowledgeChunk.find(KnowledgeChunk.lecture_id == lecture_id).delete()
        await KnowledgeCard.find(KnowledgeCard.lecture.id == PydanticObjectId(lecture_id)).delete()
        
    lecture.sources.append(LectureSource(type="text", url="", status="processing"))
    lecture.status = "processing"
    await lecture.save()

    background_tasks.add_task(process_text_background, lecture_id, request.text)

    return UploadResponse(
        filename="raw_text",
        lecture_id=lecture_id,
        status="processing",
        message="Text upload successful, processing started in background"
    )
