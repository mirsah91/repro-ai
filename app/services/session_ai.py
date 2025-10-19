from __future__ import annotations

from typing import List

from fastapi import HTTPException

from app.models.session import SessionChatResponse, SessionDocument, SessionSummaryResponse
from app.services.conversation import ConversationStore
from app.services.database import MongoSessionRepository
from app.services.llm import LLMClient


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
        documents = self._load_documents(session_id)
        summary = self._llm.summarize_session(session_id, documents)
        return SessionSummaryResponse(
            session_id=session_id,
            summary=summary,
            used_documents=documents,
        )

    def chat(
        self, session_id: str, question: str, conversation_id: str | None = None
    ) -> SessionChatResponse:
        documents = self._load_documents(session_id)
        if conversation_id:
            history = self._conversations.get(conversation_id)
        else:
            conversation_id = self._conversations.generate_id()
            history = []

        answer = self._llm.answer_question(session_id, question, documents, history)
        self._conversations.append(conversation_id, "user", question)
        self._conversations.append(conversation_id, "assistant", answer)

        return SessionChatResponse(
            session_id=session_id,
            answer=answer,
            used_documents=documents,
            conversation_id=conversation_id,
        )

    def _load_documents(self, session_id: str) -> List[SessionDocument]:
        documents = self._repository.fetch_session_documents(session_id)
        if not documents:
            raise HTTPException(status_code=404, detail="Session not found")
        return self._truncate_documents(documents)

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
            truncated.append(SessionDocument(source=document.source, content=content))
            running_total += len(content)
            if running_total >= max_characters:
                break
        return truncated
