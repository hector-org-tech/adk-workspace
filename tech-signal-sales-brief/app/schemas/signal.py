from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any


class Signal(BaseModel):
    source: str = Field(description="github or stackexchange")
    external_id: str
    title: str
    url: str
    author: str | None = None
    created_at: datetime
    tags: list[str] = []
    raw_text: str
    engagement_score: float = 0.0
    metadata: dict[str, Any] = {}
