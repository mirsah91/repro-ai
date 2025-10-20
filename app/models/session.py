from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class SessionDocument(BaseModel):
    """Represents a generic record associated with a session."""

    source: str = Field(..., description="Collection or logical source name")
    content: str = Field(..., description="Human-readable representation of the record")
    batch_index: Optional[int] = Field(
        default=None,
        description="Order of the batch within the session, if available",
    )
    total_events: Optional[int] = Field(
        default=None,
        description="Number of events represented by this record, when known",
    )
    event_preview: List[str] = Field(
        default_factory=list,
        description="High level highlights extracted from large event payloads",
    )


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
