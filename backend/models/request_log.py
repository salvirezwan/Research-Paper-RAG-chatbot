from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, GetJsonSchemaHandler, ConfigDict
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from bson import ObjectId


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


class RequestLog(BaseModel):
    id: Optional[PyObjectId] = Field(default=None, alias="_id")
    endpoint: Optional[str] = None
    response_time: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status_code: Optional[int] = None
    error_type: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str}
    )

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude={"id"}, mode='python')
        if self.id:
            data["_id"] = self.id
        return data

    @classmethod
    def from_mongo(cls, data: dict) -> "RequestLog":
        return cls(**data)
