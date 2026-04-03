from typing import Dict, List, Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    chat_history: Optional[List[Dict[str, str]]] = None  # [{"role": "user"|"assistant", "content": "..."}]


class ChatResponse(BaseModel):
    query: str
    answer: str
    citations: List[str] = []
    status: str = "success"
