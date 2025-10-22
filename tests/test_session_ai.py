from app.models.session import ChatMessage, SessionDocument
from app.services.session_ai import SessionAIService


class FakeRepository:
    def __init__(self, documents: list[SessionDocument]):
        self._documents = documents

    def fetch_session_documents(self, session_id: str):
        from app.services.database import SessionLookupResult

        return SessionLookupResult(
            session_id=session_id,
            documents=self._documents,
            session_id_fields=("sessionId",),
            requested_collections=("traces",),
            candidate_values=(session_id,),
            scanned_collections=("traces",),
            matched_collections=("traces",),
            fallback_collections=(),
            fallback_documents_scanned=0,
            connection_ok=True,
            collection_samples=(),
        )


class FakeLLM:
    def __init__(self) -> None:
        self.history_arguments: list[list[dict[str, str]]] = []

    def summarize_session(self, session_id, documents):  # pragma: no cover - unused here
        return "summary"

    def answer_question(
        self, session_id, question, documents, conversation_history
    ) -> str:
        self.history_arguments.append(list(conversation_history))
        return f"answer-for-{question}"


def test_truncate_documents_limits_total_characters():
    documents = [
        SessionDocument(
            source="a",
            content="x" * 6000,
            batch_index=1,
            event_preview=["alpha"],
        ),
        SessionDocument(source="b", content="y" * 6000),
        SessionDocument(source="c", content="z" * 6000),
    ]

    truncated = SessionAIService._truncate_documents(documents, max_characters=12000)

    assert len(truncated) == 2
    assert len("".join(doc.content for doc in truncated)) == 12000
    assert truncated[0].source == "a"
    assert truncated[1].source == "b"
    assert truncated[0].batch_index == 1
    assert truncated[0].event_preview == ["alpha"]


def test_chat_returns_history_and_tracks_conversation_turns():
    documents = [SessionDocument(source="traces", content="payload")]
    repository = FakeRepository(documents)
    llm = FakeLLM()
    service = SessionAIService(repository=repository, llm_client=llm)

    first = service.chat("session-1", "What happened?")

    assert first.answer == "answer-for-What happened?"
    assert [msg.model_dump() for msg in first.history] == [
        ChatMessage(role="user", content="What happened?").model_dump(),
        ChatMessage(role="assistant", content="answer-for-What happened?").model_dump(),
    ]
    assert llm.history_arguments[0] == []

    second = service.chat("session-1", "Any errors?", first.conversation_id)

    assert llm.history_arguments[1] == [
        {"role": "user", "content": "What happened?"},
        {"role": "assistant", "content": "answer-for-What happened?"},
    ]
    assert [msg.model_dump() for msg in second.history][-2:] == [
        {"role": "user", "content": "Any errors?"},
        {"role": "assistant", "content": "answer-for-Any errors?"},
    ]
