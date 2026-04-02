from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from beanie import PydanticObjectId

from app.models.subject import Subject
from app.models.user import User
from app.models.lecture import Lecture
from app.models.knowledge import KnowledgeChunk
from app.models.knowledge_card import KnowledgeCard
from app.schemas.subject_schema import SubjectCreate, SubjectResponse, SubjectUpdate
from app.auth.dependencies import get_current_active_user

router = APIRouter(prefix="/subjects", tags=["Subjects"])

@router.post("/", response_model=SubjectResponse, status_code=status.HTTP_201_CREATED)
async def create_subject(
    subject_in: SubjectCreate, 
    current_user: User = Depends(get_current_active_user)
):
    subject = Subject(
        name=subject_in.name,
        description=subject_in.description,
        owner=current_user
    )
    await subject.insert()
    return SubjectResponse(
        id=str(subject.id),
        name=subject.name,
        description=subject.description,
        created_at=subject.created_at
    )

@router.get("/", response_model=List[SubjectResponse])
async def list_subjects(current_user: User = Depends(get_current_active_user)):
    subjects = await Subject.find(Subject.owner.id == current_user.id).to_list()
    return [
        SubjectResponse(
            id=str(s.id), name=s.name, description=s.description, created_at=s.created_at
        ) for s in subjects
    ]

@router.get("/{subject_id}", response_model=SubjectResponse)
async def get_subject(
    subject_id: str,
    current_user: User = Depends(get_current_active_user)
):
    subject = await Subject.get(PydanticObjectId(subject_id))
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Subject not found")
        
    return SubjectResponse(
        id=str(subject.id), name=subject.name, description=subject.description, created_at=subject.created_at
    )

async def delete_lecture_data(lecture_id: PydanticObjectId):
    await KnowledgeChunk.find(KnowledgeChunk.lecture.id == lecture_id).delete()
    await KnowledgeCard.find(KnowledgeCard.lecture.id == lecture_id).delete()

@router.delete("/{subject_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subject(
    subject_id: str,
    current_user: User = Depends(get_current_active_user)
):
    subject = await Subject.get(PydanticObjectId(subject_id))
    if not subject or str(subject.owner.ref.id) != str(current_user.id):
        raise HTTPException(status_code=404, detail="Subject not found")
        
    lectures = await Lecture.find(Lecture.subject.id == subject.id).to_list()
    for lecture in lectures:
        await delete_lecture_data(lecture.id)
        await lecture.delete()
        
    await subject.delete()
    return None
