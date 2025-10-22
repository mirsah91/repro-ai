from __future__ import annotations

from typing import Iterable

from openai import OpenAI

from app.models.session import SessionDocument
from app.services.settings import settings


class LLMClient:
    """Wrapper around the OpenAI API for summarization and Q&A."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        api_key = api_key or settings.openai_api_key
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not configured. Set it in the environment before starting the service."
            )
        self._client = OpenAI(api_key=api_key)
        self._model = model or settings.openai_model

    def summarize_session(self, session_id: str, documents: Iterable[SessionDocument]) -> str:
        prompt = self._build_summary_prompt(session_id, documents)
        response = self._client.responses.create(
            model=self._model,
            input=[{"role": "user", "content": prompt}],
        )
        return response.output_text

    def answer_question(
        self,
        session_id: str,
        question: str,
        documents: Iterable[SessionDocument],
        conversation_history: list[dict[str, str]] | None = None,
    ) -> str:
        history = conversation_history or []
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an assistant that answers questions about a specific session. "
                    "Use only the provided session context and the conversation history shared "
                    "by the user."
                ),
            },
            *history,
            {
                "role": "user",
                "content": self._build_question_prompt(
                    session_id,
                    question,
                    documents,
                    self._format_conversation_history(history),
                ),
            },
        ]
        response = self._client.responses.create(model=self._model, input=messages)
        return response.output_text

    @staticmethod
    def _build_summary_prompt(session_id: str, documents: Iterable[SessionDocument]) -> str:
        document_text = "\n\n".join(
            (
                f"Source: {doc.source}\n"
                f"Batch: {doc.batch_index if doc.batch_index is not None else 'n/a'}\n"
                f"Content: {doc.content}"
            )
            for doc in documents
        )
        return (
            "Create a concise Jira-ready summary for the session below. "
            "Respond with a short title followed by up to three bullet points that capture the "
            "critical actions, decisions, and blockers. Mention remaining questions or follow-up "
            "items if needed and avoid unnecessary detail.\n\n"
            f"Session ID: {session_id}\n\n"
            f"Ordered Session Context:\n{document_text}"
        )

    @staticmethod
    def _build_question_prompt(
        session_id: str,
        question: str,
        documents: Iterable[SessionDocument],
        conversation_history_text: str | None = None,
    ) -> str:
        document_text = "\n\n".join(
            f"Source: {doc.source}\nContent: {doc.content}" for doc in documents
        )
        history_section = (
            "Conversation so far:\n"
            f"{conversation_history_text}\n\n"
            if conversation_history_text
            else ""
        )
        return (
            "You are given the aggregated records for a single session in chronological batches. "
            "Answer the user's question using only this context and what has been established in "
            "the conversation so far. If the answer cannot be derived, say that the information is "
            "not available. Highlight batch numbers when they clarify the answer.\n\n"
            f"Session ID: {session_id}\n"
            f"Question: {question}\n\n"
            f"{history_section}"
            f"Context:\n{document_text}"
        )

    @staticmethod
    def _format_conversation_history(
        conversation_history: Iterable[dict[str, str]] | None,
    ) -> str | None:
        if not conversation_history:
            return None

        def _label(role: str) -> str:
            if role == "user":
                return "User"
            if role == "assistant":
                return "Assistant"
            return role.title()

        lines = [
            f"{_label(message.get('role', 'user'))}: {message.get('content', '').strip()}"
            for message in conversation_history
            if message.get("content")
        ]

        return "\n".join(lines) if lines else None
