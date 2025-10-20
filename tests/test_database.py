import uuid

from bson.binary import Binary, UUID_SUBTYPE
from bson.objectid import ObjectId

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


def test_build_query_includes_object_id_variants():
    session_id = "507f1f77bcf86cd799439011"

    query = MongoSessionRepository._build_query_from_fields(session_id, ["sessionId"])

    assert query == {
        "$or": [
            {"sessionId": session_id},
            {"sessionId": ObjectId(session_id)},
        ]
    }


def test_build_query_includes_uuid_variants():
    session_uuid = uuid.uuid4()
    session_id = str(session_uuid)

    query = MongoSessionRepository._build_query_from_fields(
        session_id, ["sessionId", "session_id"]
    )

    assert query == {
        "$or": [
            {"sessionId": session_id},
            {"sessionId": session_uuid},
            {"sessionId": Binary(session_uuid.bytes, subtype=UUID_SUBTYPE)},
            {"session_id": session_id},
            {"session_id": session_uuid},
            {"session_id": Binary(session_uuid.bytes, subtype=UUID_SUBTYPE)},
        ]
    }
