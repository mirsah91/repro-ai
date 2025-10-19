from __future__ import annotations

from typing import Iterable, List

from bson import json_util
from pymongo import MongoClient

from app.models.session import SessionDocument
from app.services.settings import settings


class MongoSessionRepository:
    """Repository that aggregates session documents from every collection."""

    def __init__(self, client: MongoClient | None = None) -> None:
        self._client = client or MongoClient(settings.mongo_uri)
        self._db = self._client[settings.mongo_db]

    def fetch_session_documents(self, session_id: str) -> List[SessionDocument]:
        documents: List[SessionDocument] = []
        for collection_name in self._iter_collection_names():
            collection = self._db[collection_name]
            cursor = collection.find({"sessionId": session_id})
            for raw_document in cursor:
                documents.append(
                    SessionDocument(
                        source=collection_name,
                        content=self._stringify_document(raw_document),
                    )
                )
        return documents

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
