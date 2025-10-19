from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SessionDocument(BaseModel):
    """Represents a generic record associated with a session."""

    source: str = Field(..., description="Collection or logical source name")
    content: str = Field(..., description="Human-readable representation of the record")


class SessionSummaryResponse(BaseModel):
    session_id: str
    summary: str
    used_documents: List[SessionDocument] = Field(
        ..., description="Documents that were provided to the language model"
    )


class SessionChatRequest(BaseModel):
    question: str = Field(..., description="Natural language question about the session")
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional identifier that lets clients continue a multi-turn conversation",
    )


class SessionChatResponse(BaseModel):
    session_id: str
    answer: str
    used_documents: List[SessionDocument]
    conversation_id: str
