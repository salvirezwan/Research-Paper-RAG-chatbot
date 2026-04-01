from typing import Optional, List
from pydantic import BaseModel


class RAGChunk(BaseModel):
    content: str
    paper_title: Optional[str] = None
    authors: Optional[str] = None
    arxiv_id: Optional[str] = None
    section_id: Optional[str] = None
    score: float = 0.0


class RetrievalResult(BaseModel):
    chunks: List[RAGChunk]
    query: str
    total: int
