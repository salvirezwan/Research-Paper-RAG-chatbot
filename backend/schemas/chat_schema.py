from typing import List, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    query: str
    answer: str
    citations: List[str] = []
    status: str = "success"
