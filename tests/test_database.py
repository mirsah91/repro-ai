from app.services.database import MongoSessionRepository


def test_build_query_from_fields_single_field():
    query = MongoSessionRepository._build_query_from_fields(
        "session-123", ["sessionId"]
    )

    assert query == {"sessionId": "session-123"}


def test_build_query_from_fields_multiple_fields():
    query = MongoSessionRepository._build_query_from_fields(
        "session-123", ["sessionId", "session_id", " metadata.id "]
    )

    assert query == {
        "$or": [
            {"sessionId": "session-123"},
            {"session_id": "session-123"},
            {"metadata.id": "session-123"},
        ]
    }


def test_build_query_from_fields_empty_defaults_to_session_id():
    query = MongoSessionRepository._build_query_from_fields("session-123", [])

    assert query == {"sessionId": "session-123"}
