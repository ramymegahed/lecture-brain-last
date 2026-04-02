from pydantic import BaseModel
from typing import List, Optional

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str
    lecture_id: Optional[str] = None # Optional: user can ask global or lecture-specific
    history: List[Message] = []

class ChatResponse(BaseModel):
    answer: str
    sources: List[str] = [] # e.g. "Lecture X, Page Y"

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
