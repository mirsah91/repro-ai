import uuid

from bson.binary import Binary, UUID_SUBTYPE
from bson.objectid import ObjectId

from app.services.database import MongoSessionRepository


class _StubCollection:
    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def find(self, *args, **kwargs):  # pragma: no cover - simple stub
        return []

    def estimated_document_count(self):  # pragma: no cover - simple stub
        return 0


class _StubDatabase:
    def __init__(self, collections: dict[str, _StubCollection]) -> None:
        self._collections = collections

    def list_collection_names(self):
        return list(self._collections.keys())

    def __getitem__(self, name: str) -> _StubCollection:
        return self._collections[name]

    @property
    def name(self) -> str:  # pragma: no cover - simple stub
        return "test-db"


class _StubAdmin:
    @staticmethod
    def command(cmd: str):  # pragma: no cover - simple stub
        return {"ok": 1, "command": cmd}


class _StubClient:
    def __init__(self, collections: dict[str, _StubCollection]) -> None:
        self._database = _StubDatabase(collections)
        self.admin = _StubAdmin()

    def __getitem__(self, name: str) -> _StubDatabase:
        return self._database


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

    assert "$or" in query
    assert {"sessionId": session_id} in query["$or"]
    assert {"sessionId": ObjectId(session_id)} in query["$or"]


def test_build_query_includes_uuid_variants():
    session_uuid = uuid.uuid4()
    session_id = str(session_uuid)

    query = MongoSessionRepository._build_query_from_fields(
        session_id, ["sessionId", "session_id"]
    )

    assert "$or" in query
    clauses = query["$or"]
    expected = [
        {"sessionId": session_id},
        {"sessionId": session_uuid},
        {"sessionId": Binary(session_uuid.bytes, subtype=UUID_SUBTYPE)},
        {"session_id": session_id},
        {"session_id": session_uuid},
        {"session_id": Binary(session_uuid.bytes, subtype=UUID_SUBTYPE)},
    ]
    for clause in expected:
        assert clause in clauses


def test_candidate_session_values_include_prefix_and_hyphen_variants():
    values = MongoSessionRepository._candidate_session_values(
        "S_c1fd035b-4a2f-4097-a29c-8df0ad50c80c"
    )

    assert "S_c1fd035b-4a2f-4097-a29c-8df0ad50c80c" in values
    assert "c1fd035b-4a2f-4097-a29c-8df0ad50c80c" in values
    assert "S_c1fd035b4a2f4097a29c8df0ad50c80c" in values
    assert "c1fd035b4a2f4097a29c8df0ad50c80c" in values


def test_document_contains_session_matches_nested_values():
    document = {
        "metadata": {"ids": ["ignored", "S_c1fd035b-4a2f-4097-a29c-8df0ad50c80c"]},
        "payload": {"description": "Session S_c1fd035b-4a2f-4097-a29c-8df0ad50c80c"},
    }

    candidates = MongoSessionRepository._candidate_session_values(
        "S_c1fd035b-4a2f-4097-a29c-8df0ad50c80c"
    )

    assert MongoSessionRepository._document_contains_session(document, candidates)


def test_iter_collection_names_respects_configured_collections():
    collections = {
        "traces": _StubCollection("traces"),
        "events": _StubCollection("events"),
    }
    repo = MongoSessionRepository(
        client=_StubClient(collections),
        session_collections=["traces"],
    )

    assert list(repo._iter_collection_names()) == ["traces"]


def test_format_documents_orders_batches_and_condenses_events():
    collections = {"traces": _StubCollection("traces")}
    repo = MongoSessionRepository(client=_StubClient(collections))

    raw_documents = [
        (
            "traces",
            {
                "batchIndex": 2,
                "requestRid": "rid-002",
                "data": {
                    "events": [
                        {"type": "update", "status": "ok", "index": idx}
                        for idx in range(6)
                    ],
                    "total": 6,
                },
            },
        ),
        (
            "traces",
            {
                "batchIndex": 1,
                "requestRid": "rid-001",
                "data": {
                    "events": [{"type": "create", "status": "start"}],
                    "total": 1,
                },
            },
        ),
    ]

    formatted = repo._format_documents(raw_documents)

    assert [doc.batch_index for doc in formatted] == [1, 2]
    assert formatted[0].event_preview == ["type=create, status=start"]
    assert formatted[1].event_preview[-1] == "... 1 more event(s)"
    assert formatted[1].total_events == 6
    assert "<omitted 6 event(s)" in formatted[1].content
