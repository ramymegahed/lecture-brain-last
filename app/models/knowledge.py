from beanie import Document, Link
from pydantic import Field
from typing import List, Optional
from app.models.lecture import Lecture

class KnowledgeChunk(Document):
    """
    Stores individual text chunks and their embeddings for vector search.
    
    lecture_id (str): Duplicated from the Link[Lecture] reference.
    This redundancy is intentional: MongoDB Atlas $vectorSearch filters
    require a flat scalar field (not a DBRef). The `lecture_id` string
    is used exclusively to constrain the vector search in mongodb.py.
    """
    lecture: Link[Lecture]
    lecture_id: str  # Duplicated for $vectorSearch filter — DO NOT REMOVE
    text: str = Field(..., description="The textual chunk content")
    page_number: Optional[int] = Field(default=None, description="Source page number or timestamp if video")
    embedding: List[float] = Field(..., description="1536-dimensional embedding vector from OpenAI")
    
    class Settings:
        name = "knowledge_chunks"
        # In MongoDB Atlas, you will need to create a Vector Search Index separately
        #.e.g {"embedding": {"type": "knnVector", "dimensions": 1536...}}
