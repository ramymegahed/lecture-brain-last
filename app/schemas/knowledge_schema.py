from pydantic import BaseModel
from typing import Optional

class UploadResponse(BaseModel):
    filename: str
    lecture_id: str
    status: str
    message: str
    warning: Optional[str] = None

class UploadTextRequest(BaseModel):
    text: str

class UploadVideoRequest(BaseModel):
    url: str
    extract_frames: bool = False
