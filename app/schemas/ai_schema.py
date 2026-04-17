from pydantic import BaseModel
from typing import List, Optional, Union, Any

class Message(BaseModel):
    role: str
    content: Union[str, dict, Any]
    type: str = "chat"

class ChatRequest(BaseModel):
    message: str
    lecture_id: Optional[str] = None # Optional: user can ask global or lecture-specific
    history: List[Message] = []

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = [] # e.g. "Lecture X, Page Y"

class ChatHistoryResponse(BaseModel):
    history: List[Message]

class ExplainRequest(BaseModel):
    concept: str
    lecture_id: Optional[str] = None

class ExplainResponse(BaseModel):
    explanation: str

class SummaryResponse(BaseModel):
    lecture_id: str
    summary: str
    key_points: List[str]
    concepts: List[str]
    important_details: str
    examples: List[str]

class QuizOption(BaseModel):
    id: str
    text: str

class QuizQuestion(BaseModel):
    question: str
    options: List[QuizOption]
    correct_option_id: str
    explanation: str

class QuizResponse(BaseModel):
    lecture_id: str
    questions: List[QuizQuestion]

class SlideResponse(BaseModel):
    slide_number: int
    title: str
    bullets: List[str]
    speaker_notes: str
    suggested_visual: str

class PresentationResponse(BaseModel):
    lecture_id: str
    presentation_title: str
    slides: List[SlideResponse]
