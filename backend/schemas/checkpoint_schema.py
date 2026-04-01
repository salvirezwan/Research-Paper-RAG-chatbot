from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class CheckpointResponse(BaseModel):
    checkpoint_id: str
    upload_id: str
    step: str
    status: str
    version: int = 1
    progress: Dict[str, Any] = {}
    metadata: Dict[str, Any] = {}
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None


class CheckpointListResponse(BaseModel):
    upload_id: str
    checkpoints: List[CheckpointResponse]
    total: int
