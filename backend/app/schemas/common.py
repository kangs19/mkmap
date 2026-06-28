from pydantic import BaseModel
from typing import Any


class ErrorResponse(BaseModel):
    error: str
    message: str
    code: int

    model_config = {"json_schema_extra": {
        "example": {
            "error": "item_not_found",
            "message": "요청한 품목 코드를 찾을 수 없습니다.",
            "code": 404
        }
    }}
