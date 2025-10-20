from __future__ import annotations

from typing import Any, Iterable, List, Sequence

from bson import json_util
from pymongo import MongoClient

from app.models.session import SessionDocument
from app.services.settings import settings


class MongoSessionRepository:
    """Repository that aggregates session documents from every collection."""

    def __init__(
        self,
        client: MongoClient | None = None,
        session_id_fields: Sequence[str] | None = None,
    ) -> None:
        self._client = client or MongoClient(settings.mongo_uri)
        self._db = self._client[settings.mongo_db]
        if session_id_fields is None:
            session_id_fields = settings.session_id_fields
        self._session_id_fields: tuple[str, ...] = tuple(session_id_fields)

    def fetch_session_documents(self, session_id: str) -> List[SessionDocument]:
        documents: List[SessionDocument] = []
        for collection_name in self._iter_collection_names():
            collection = self._db[collection_name]
            cursor = collection.find(self._build_session_query(session_id))
            for raw_document in cursor:
                documents.append(
                    SessionDocument(
                        source=collection_name,
                        content=self._stringify_document(raw_document),
                    )
                )
        return documents

    def _build_session_query(self, session_id: str) -> dict[str, Any]:
        return self._build_query_from_fields(session_id, self._session_id_fields)

    def _iter_collection_names(self) -> Iterable[str]:
        for name in self._db.list_collection_names():
            # system collections are ignored because they do not store business data
            if name.startswith("system."):
                continue
            yield name

    @staticmethod
    def _stringify_document(document: dict) -> str:
        clean_document = dict(document)
        clean_document.pop("_id", None)
        return json_util.dumps(clean_document, ensure_ascii=False)

    @staticmethod
    def _build_query_from_fields(
        session_id: str, session_id_fields: Sequence[str]
    ) -> dict[str, Any]:
        normalized = [field.strip() for field in session_id_fields if field.strip()]
        # Fall back to the canonical name when no valid custom fields are provided.
        if not normalized:
            normalized = ["sessionId"]

        if len(normalized) == 1:
            return {normalized[0]: session_id}

        return {"$or": [{field: session_id} for field in normalized]}
