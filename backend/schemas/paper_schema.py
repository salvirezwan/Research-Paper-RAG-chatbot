from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel

from backend.models.uploaded_doc import PaperSource, PaperStatus


class PaperResponse(BaseModel):
    paper_id: str
    filename: str
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    abstract: Optional[str] = None
    source: PaperSource
    status: PaperStatus
    publication_year: Optional[str] = None
    arxiv_id: Optional[str] = None
    doi: Optional[str] = None
    subject_areas: Optional[List[str]] = None
    chunk_count: int = 0
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
