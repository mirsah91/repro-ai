from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, Depends

from app.models.session import (
    SessionChatRequest,
    SessionChatResponse,
    SessionSummaryResponse,
)
from app.services.session_ai import SessionAIService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@lru_cache(maxsize=1)
def get_service() -> SessionAIService:
    return SessionAIService()


@router.get("/{session_id}/summary", response_model=SessionSummaryResponse)
def summarize_session(
    session_id: str, service: SessionAIService = Depends(get_service)
) -> SessionSummaryResponse:
    return service.summarize(session_id)


@router.post("/{session_id}/chat", response_model=SessionChatResponse)
def chat_with_session(
    session_id: str,
    payload: SessionChatRequest,
    service: SessionAIService = Depends(get_service),
) -> SessionChatResponse:
    return service.chat(session_id, payload.question, payload.conversation_id)
