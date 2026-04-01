from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from enum import Enum
from pydantic import BaseModel, Field, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from bson import ObjectId



class PaperSource(str, Enum):
    UPLOAD = "upload"
    ARXIV = "arxiv"
    SEMANTIC_SCHOLAR = "semantic_scholar"
    OPENALEX = "openalex"
    OTHER = "other"


class PaperStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class PyObjectId(ObjectId):
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        def validate_from_str(input_value: str) -> ObjectId:
            if isinstance(input_value, ObjectId):
                return input_value
            if isinstance(input_value, str):
                if ObjectId.is_valid(input_value):
                    return ObjectId(input_value)
                raise ValueError("Invalid ObjectId string")
            raise ValueError("Invalid ObjectId type")

        return core_schema.no_info_plain_validator_function(validate_from_str)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return {"type": "string"}


class ResearchPaper(BaseModel):
    """
    ResearchPaper model for MongoDB.
    Represents metadata about an uploaded or fetched research paper.
    """
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    filename: str
    stored_path: str
    file_hash: str
    source: PaperSource
    status: PaperStatus
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    abstract: Optional[str] = None
    publication_year: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    subject_areas: Optional[List[str]] = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    chunk_count: int = 0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}
        json_schema_extra = {
            "example": {
                "filename": "attention_is_all_you_need.pdf",
                "source": "upload",
                "title": "Attention Is All You Need",
                "authors": ["Vaswani et al."],
                "publication_year": "2017"
            }
        }

    def to_mongo(self) -> dict:
        data = self.dict(by_alias=True, exclude={"id"})
        if self.id:
            data["_id"] = self.id
        return data

    @classmethod
    def from_mongo(cls, data: dict) -> "ResearchPaper":
        if "_id" in data:
            data = {**data, "_id": str(data["_id"])}
        return cls(**data)