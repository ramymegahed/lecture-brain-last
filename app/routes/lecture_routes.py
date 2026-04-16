from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from beanie import PydanticObjectId

from app.models.lecture import Lecture
from app.models.subject import Subject
from app.models.user import User
from app.models.knowledge import KnowledgeChunk
from app.models.knowledge_card import KnowledgeCard
from app.schemas.lecture_schema import LectureCreate, LectureResponse
from app.auth.dependencies import get_current_active_user

router = APIRouter(prefix="/lectures", tags=["Lectures"])

@router.post("/", response_model=LectureResponse, status_code=status.HTTP_201_CREATED)
async def create_lecture(
    lecture_in: LectureCreate, 
    current_user: User = Depends(get_current_active_user)
):
    subject = await Subject.get(PydanticObjectId(lecture_in.subject_id))
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Subject not found")

    lecture = Lecture(
        title=lecture_in.title,
        description=lecture_in.description,
        subject=subject
    )
    await lecture.insert()
    return LectureResponse(
        id=str(lecture.id),
        title=lecture.title,
        description=lecture.description,
        subject_id=str(subject.id),
        status=lecture.status,
        created_at=lecture.created_at
    )

@router.get("/subject/{subject_id}", response_model=List[LectureResponse])
async def list_lectures_by_subject(
    subject_id: str,
    current_user: User = Depends(get_current_active_user)
):
    subject = await Subject.get(PydanticObjectId(subject_id))
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Subject not found")

    lectures = await Lecture.find(Lecture.subject.id == subject.id).to_list()
    return [
        LectureResponse(
            id=str(l.id), title=l.title, description=l.description, 
            subject_id=str(l.subject.ref.id), sources=[s.model_dump() for s in l.sources],
            status=l.status, created_at=l.created_at
        ) for l in lectures
    ]

@router.get("/{lecture_id}", response_model=LectureResponse)
async def get_lecture(
    lecture_id: str,
    current_user: User = Depends(get_current_active_user)
):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Lecture not found")
    lecture.subject = subject
        
    return LectureResponse(
        id=str(lecture.id), title=lecture.title, description=lecture.description, 
        subject_id=str(lecture.subject.id), sources=[s.model_dump() for s in lecture.sources],
        status=lecture.status, created_at=lecture.created_at
    )

@router.get("/{lecture_id}/status")
async def get_lecture_status(
    lecture_id: str,
    current_user: User = Depends(get_current_active_user)
):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Lecture not found")
    return {"lecture_id": lecture_id, "status": lecture.status}

async def delete_lecture_data(lecture_id: PydanticObjectId):
    await KnowledgeChunk.find(KnowledgeChunk.lecture.id == lecture_id).delete()
    await KnowledgeCard.find(KnowledgeCard.lecture.id == lecture_id).delete()

@router.delete("/{lecture_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lecture(
    lecture_id: str,
    current_user: User = Depends(get_current_active_user)
):
    lecture = await Lecture.get(PydanticObjectId(lecture_id))
    if not lecture:
        raise HTTPException(status_code=404, detail="Lecture not found")
    subject = await Subject.get(lecture.subject.ref.id)
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Lecture not found")
        
    await delete_lecture_data(lecture.id)
    await lecture.delete()
    return None
