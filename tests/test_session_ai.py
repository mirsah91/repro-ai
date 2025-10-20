from app.models.session import SessionDocument
from app.services.session_ai import SessionAIService


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
