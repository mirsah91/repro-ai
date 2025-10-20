from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence, Tuple

from bson import json_util
from bson.binary import Binary, UUID_SUBTYPE
from bson.errors import InvalidId
from bson.objectid import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection

from app.models.session import SessionDocument
from app.services.settings import settings


@dataclass
class SessionLookupResult:
    session_id: str
    documents: List[SessionDocument]
    session_id_fields: Tuple[str, ...]
    candidate_values: Tuple[Any, ...]
    scanned_collections: Tuple[str, ...]
    matched_collections: Tuple[str, ...]
    fallback_collections: Tuple[str, ...]
    fallback_documents_scanned: int


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

    def fetch_session_documents(self, session_id: str) -> SessionLookupResult:
        documents: List[SessionDocument] = []
        scanned_collections: list[str] = []
        matched_collections: set[str] = set()
        fallback_collections: set[str] = set()
        fallback_documents_scanned = 0
        candidate_values = self._candidate_session_values(session_id)
        query = self._build_session_query(session_id, candidate_values=candidate_values)

        for collection_name in self._iter_collection_names():
            scanned_collections.append(collection_name)
            collection = self._db[collection_name]
            matched = False

            for raw_document in collection.find(query):
                matched = True
                matched_collections.add(collection_name)
                documents.append(
                    SessionDocument(
                        source=collection_name,
                        content=self._stringify_document(raw_document),
                    )
                )

            if not matched and settings.enable_fallback_scan:
                fallback_matches, scanned_count = self._scan_collection_for_session(
                    collection, candidate_values
                )
                fallback_documents_scanned += scanned_count
                if fallback_matches:
                    matched_collections.add(collection_name)
                    fallback_collections.add(collection_name)
                    for raw_document in fallback_matches:
                        documents.append(
                            SessionDocument(
                                source=collection_name,
                                content=self._stringify_document(raw_document),
                            )
                        )

        return SessionLookupResult(
            session_id=session_id,
            documents=documents,
            session_id_fields=self._session_id_fields,
            candidate_values=candidate_values,
            scanned_collections=tuple(scanned_collections),
            matched_collections=tuple(sorted(matched_collections)),
            fallback_collections=tuple(sorted(fallback_collections)),
            fallback_documents_scanned=fallback_documents_scanned,
        )

    def _build_session_query(
        self, session_id: str, candidate_values: Tuple[Any, ...]
    ) -> dict[str, Any]:
        return self._build_query_from_fields(
            session_id, self._session_id_fields, candidate_values=candidate_values
        )

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
        session_id: str,
        session_id_fields: Sequence[str],
        *,
        candidate_values: Sequence[Any] | None = None,
    ) -> dict[str, Any]:
        normalized = [field.strip() for field in session_id_fields if field.strip()]
        # Fall back to the canonical name when no valid custom fields are provided.
        if not normalized:
            normalized = ["sessionId"]

        if candidate_values is None:
            candidate_values = MongoSessionRepository._candidate_session_values(session_id)

        if len(normalized) == 1 and len(candidate_values) == 1:
            return {normalized[0]: candidate_values[0]}

        clauses: list[dict[str, Any]] = []
        for field in normalized:
            for value in candidate_values:
                clauses.append({field: value})

        if len(clauses) == 1:
            return clauses[0]

        return {"$or": clauses}

    @staticmethod
    def _candidate_session_values(session_id: str) -> tuple[Any, ...]:
        canonical = session_id.strip()
        candidates: list[Any] = [canonical]

        if canonical and canonical.startswith("S_") and len(canonical) > 2:
            candidates.append(canonical.split("_", 1)[1])

        no_hyphen = canonical.replace("-", "")
        if no_hyphen and no_hyphen not in candidates:
            candidates.append(no_hyphen)

        if canonical.startswith("S_") and len(canonical) > 2:
            trimmed = canonical.split("_", 1)[1].replace("-", "")
            if trimmed and trimmed not in candidates:
                candidates.append(trimmed)

        try:
            candidates.append(ObjectId(canonical))
        except InvalidId:
            pass

        try:
            uuid_value = uuid.UUID(canonical)
        except ValueError:
            uuid_value = None

        if uuid_value is not None:
            candidates.append(uuid_value)
            candidates.append(Binary(uuid_value.bytes, subtype=UUID_SUBTYPE))

        deduped: list[Any] = []
        seen: set[str] = set()
        for candidate in candidates:
            marker = f"{type(candidate).__qualname__}:{repr(candidate)}"
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(candidate)

        return tuple(deduped)

    @staticmethod
    def _scan_collection_for_session(
        collection: Collection, candidate_values: Sequence[Any]
    ) -> tuple[list[dict[str, Any]], int]:
        matches: list[dict[str, Any]] = []
        scanned = 0
        for raw_document in collection.find(limit=settings.fallback_scan_limit):
            scanned += 1
            if MongoSessionRepository._document_contains_session(
                raw_document, candidate_values
            ):
                matches.append(raw_document)
        return matches, scanned

    @staticmethod
    def _document_contains_session(
        document: Any, candidate_values: Sequence[Any]
    ) -> bool:
        queue: list[Any] = [document]
        normalized_strings = {
            str(value).lower() for value in candidate_values if isinstance(value, str)
        }
        normalized_strings.update({
            str(value).lower()
            for value in candidate_values
            if not isinstance(value, str)
        })
        literal_candidates = tuple(candidate_values)

        while queue:
            current = queue.pop()
            if isinstance(current, dict):
                queue.extend(current.values())
                continue
            if isinstance(current, (list, tuple, set)):
                queue.extend(current)
                continue

            for candidate in literal_candidates:
                if current == candidate:
                    return True

            if isinstance(current, (str, bytes)):
                comparison = current.decode() if isinstance(current, bytes) else current
                comparison_lower = comparison.lower()
                if comparison_lower in normalized_strings:
                    return True
                for target in normalized_strings:
                    if target and target in comparison_lower:
                        return True

        return False

    @staticmethod
    def describe_candidate(candidate: Any) -> str:
        return json_util.dumps(candidate, ensure_ascii=False)
