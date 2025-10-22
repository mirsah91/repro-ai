from __future__ import annotations

from typing import List

from fastapi import HTTPException

from app.models.session import (
    ChatMessage,
    SessionChatResponse,
    SessionDocument,
    SessionSummaryResponse,
)
from app.services.conversation import ConversationStore
from app.services.database import MongoSessionRepository, SessionLookupResult
from app.services.llm import LLMClient
from app.services.settings import settings


class SessionAIService:
    def __init__(
        self,
        repository: MongoSessionRepository | None = None,
        llm_client: LLMClient | None = None,
        conversation_store: ConversationStore | None = None,
    ) -> None:
        self._repository = repository or MongoSessionRepository()
        self._llm = llm_client or LLMClient()
        self._conversations = conversation_store or ConversationStore()

    def summarize(self, session_id: str) -> SessionSummaryResponse:
        documents, _ = self._load_documents(session_id)
        summary = self._llm.summarize_session(session_id, documents)
        return SessionSummaryResponse(
            session_id=session_id,
            summary=summary,
            used_documents=documents,
        )

    def chat(
        self, session_id: str, question: str, conversation_id: str | None = None
    ) -> SessionChatResponse:
        documents, lookup = self._load_documents(session_id)
        if conversation_id:
            history_dicts = self._conversations.get(conversation_id)
        else:
            conversation_id = self._conversations.generate_id()
            history_dicts = []

        answer = self._llm.answer_question(
            session_id, question, documents, history_dicts
        )
        self._conversations.append(conversation_id, "user", question)
        self._conversations.append(conversation_id, "assistant", answer)

        full_history = [
            ChatMessage(**message)
            for message in self._conversations.get(conversation_id)
        ]

        response = SessionChatResponse(
            session_id=session_id,
            answer=answer,
            used_documents=documents,
            conversation_id=conversation_id,
            history=full_history,
        )

        # Persist the most recent lookup metadata for debugging purposes.
        self._conversations.metadata[conversation_id] = {
            "lookup": {
                "requested_collections": list(lookup.requested_collections),
                "collections": list(lookup.scanned_collections),
                "matched_collections": list(lookup.matched_collections),
            }
        }

        return response

    def _load_documents(
        self, session_id: str
    ) -> tuple[List[SessionDocument], SessionLookupResult]:
        lookup = self._repository.fetch_session_documents(session_id)
        if not lookup.documents:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "Session not found",
                    "session_id": session_id,
                    "checked_fields": list(lookup.session_id_fields),
                    "target_collections": list(lookup.requested_collections),
                    "candidate_values": [
                        self._repository.describe_candidate(candidate)
                        for candidate in lookup.candidate_values
                    ],
                    "mongo_connection_ok": lookup.connection_ok,
                    "collections_scanned": list(lookup.scanned_collections),
                    "fallback_scan_enabled": settings.enable_fallback_scan,
                    "fallback_documents_scanned": lookup.fallback_documents_scanned,
                    "fallback_collections": list(lookup.fallback_collections),
                    "collection_documents": {
                        name: list(documents)
                        for name, documents in lookup.collection_samples
                    },
                },
            )
        return self._truncate_documents(lookup.documents), lookup

    @staticmethod
    def _truncate_documents(
        documents: List[SessionDocument], max_characters: int = 12_000
    ) -> List[SessionDocument]:
        truncated: List[SessionDocument] = []
        running_total = 0
        for document in documents:
            content = document.content
            if running_total + len(content) > max_characters:
                remaining = max_characters - running_total
                if remaining <= 0:
                    break
                content = content[:remaining]
            truncated.append(document.model_copy(update={"content": content}))
            running_total += len(content)
            if running_total >= max_characters:
                break
        return truncated
