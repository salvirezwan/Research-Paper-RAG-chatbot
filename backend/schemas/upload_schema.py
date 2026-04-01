from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel

from backend.models.uploaded_doc import PaperStatus


class UploadRequest(BaseModel):
    """Optional metadata supplied during file upload."""
    title: Optional[str] = None
    authors: Optional[str] = None
    publication_year: Optional[str] = None
    description: Optional[str] = None


class UploadResponse(BaseModel):
    paper_id: str
    filename: str
    status: str
    message: str


class UploadStatusResponse(BaseModel):
    paper_id: str
    status: PaperStatus
    filename: str
    chunk_count: int = 0
    error_message: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None


class PaperListResponse(BaseModel):
    papers: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int
