from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Iterable, List, Sequence, Tuple

from bson import json_util
from bson.binary import Binary, UUID_SUBTYPE
from bson.errors import InvalidId
from bson.objectid import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from app.models.session import SessionDocument
from app.services.settings import settings


@dataclass
class SessionLookupResult:
    session_id: str
    documents: List[SessionDocument]
    session_id_fields: Tuple[str, ...]
    requested_collections: Tuple[str, ...]
    candidate_values: Tuple[Any, ...]
    scanned_collections: Tuple[str, ...]
    matched_collections: Tuple[str, ...]
    fallback_collections: Tuple[str, ...]
    fallback_documents_scanned: int
    connection_ok: bool
    collection_samples: Tuple[Tuple[str, Tuple[str, ...]], ...]


class MongoSessionRepository:
    """Repository that aggregates session documents from every collection."""

    def __init__(
        self,
        client: MongoClient | None = None,
        session_id_fields: Sequence[str] | None = None,
        session_collections: Sequence[str] | None = None,
    ) -> None:
        self._logger = logging.getLogger(__name__)
        self._uri_description = self._mask_uri(settings.mongo_uri)
        if client is None:
            self._client = MongoClient(settings.mongo_uri)
        else:
            self._client = client
            # When a client is injected (e.g. tests), avoid leaking configuration
            # details and use a synthetic description.
            self._uri_description = "<injected MongoClient>"

        self._db = self._client[settings.mongo_db]
        if session_id_fields is None:
            session_id_fields = settings.session_id_fields
        self._session_id_fields: tuple[str, ...] = tuple(session_id_fields)
        if session_collections is None:
            session_collections = settings.session_collections
        self._session_collections: tuple[str, ...] = tuple(session_collections)
        self._connection_ok = self._check_connection()

    def fetch_session_documents(self, session_id: str) -> SessionLookupResult:
        raw_documents: list[tuple[str, dict[str, Any]]] = []
        scanned_collections: list[str] = []
        matched_collections: set[str] = set()
        fallback_collections: set[str] = set()
        fallback_documents_scanned = 0
        candidate_values = self._candidate_session_values(session_id)
        query = self._build_session_query(session_id, candidate_values=candidate_values)

        connection_ok = self._check_connection()
        self._connection_ok = connection_ok
        self._logger.info(
            "Fetching session '%s' using fields %s (connection_ok=%s)",
            session_id,
            ", ".join(self._session_id_fields) or "<none>",
            connection_ok,
        )

        collection_names = tuple(self._iter_collection_names())
        if not collection_names:
            self._logger.warning(
                "No collections discovered in MongoDB database '%s'", self._db.name
            )

        for collection_name in collection_names:
            scanned_collections.append(collection_name)
            collection = self._db[collection_name]
            matched = False

            try:
                cursor = collection.find(query)
            except PyMongoError:
                self._logger.exception(
                    "Query failed for collection '%s' when searching for session '%s'",
                    collection_name,
                    session_id,
                )
                cursor = []

            for raw_document in cursor:
                matched = True
                matched_collections.add(collection_name)
                raw_documents.append((collection_name, raw_document))

            if not matched and settings.enable_fallback_scan:
                try:
                    fallback_matches, scanned_count = self._scan_collection_for_session(
                        collection, candidate_values
                    )
                except PyMongoError:
                    self._logger.exception(
                        "Fallback scan failed for collection '%s' when searching for session '%s'",
                        collection_name,
                        session_id,
                    )
                    continue
                fallback_documents_scanned += scanned_count
                if fallback_matches:
                    matched_collections.add(collection_name)
                    fallback_collections.add(collection_name)
                    for raw_document in fallback_matches:
                        raw_documents.append((collection_name, raw_document))

        collection_samples: Tuple[Tuple[str, Tuple[str, ...]], ...] = tuple()
        documents = self._format_documents(raw_documents)

        if not documents:
            collection_samples = self._collect_collection_documents(collection_names)

        return SessionLookupResult(
            session_id=session_id,
            documents=documents,
            session_id_fields=self._session_id_fields,
            requested_collections=self._session_collections,
            candidate_values=candidate_values,
            scanned_collections=tuple(scanned_collections),
            matched_collections=tuple(sorted(matched_collections)),
            fallback_collections=tuple(sorted(fallback_collections)),
            fallback_documents_scanned=fallback_documents_scanned,
            connection_ok=connection_ok,
            collection_samples=collection_samples,
        )

    def _build_session_query(
        self, session_id: str, candidate_values: Tuple[Any, ...]
    ) -> dict[str, Any]:
        return self._build_query_from_fields(
            session_id, self._session_id_fields, candidate_values=candidate_values
        )

    def _iter_collection_names(self) -> Iterable[str]:
        specified_collections = self._session_collections
        try:
            collection_names = self._db.list_collection_names()
        except PyMongoError:
            self._logger.exception(
                "Failed to list MongoDB collections for %s/%s",
                self._uri_description,
                self._db.name,
            )
            if specified_collections:
                self._logger.warning(
                    "Falling back to configured session collections after list failure: %s",
                    ", ".join(specified_collections),
                )
                for name in specified_collections:
                    yield name
            return

        filtered_names = [
            name for name in collection_names if not name.startswith("system.")
        ]

        if specified_collections:
            missing = [
                name for name in specified_collections if name not in filtered_names
            ]
            if missing:
                self._logger.warning(
                    "Configured session collections not found in database '%s': %s",
                    self._db.name,
                    ", ".join(missing),
                )
            for name in specified_collections:
                if name in filtered_names:
                    yield name
            return

        for name in filtered_names:
            yield name

    def _format_documents(
        self, raw_documents: Sequence[tuple[str, dict[str, Any]]]
    ) -> List[SessionDocument]:
        if not raw_documents:
            return []

        sorted_documents = sorted(raw_documents, key=self._document_sort_key)
        formatted: List[SessionDocument] = []
        for source, document in sorted_documents:
            formatted.append(self._to_session_document(source, document))
        return formatted

    def _document_sort_key(self, item: tuple[str, dict[str, Any]]) -> tuple[Any, ...]:
        _, document = item
        batch_index = self._coerce_int(document.get("batchIndex"))
        timestamp = self._coerce_int(document.get("t")) or 0
        request_rid = document.get("requestRid") or document.get("rid")
        action_id = document.get("actionId")
        identifier = request_rid or action_id or str(document.get("_id", ""))

        if batch_index is not None:
            return (0, batch_index, identifier)

        return (1, timestamp, identifier)

    def _to_session_document(self, source: str, document: dict[str, Any]) -> SessionDocument:
        batch_index = self._coerce_int(document.get("batchIndex"))
        request_rid = document.get("requestRid") or document.get("rid")
        action_id = document.get("actionId")
        data = document.get("data") if isinstance(document.get("data"), dict) else None
        total_events = None
        if data is not None:
            total_raw = data.get("total")
            total_events = self._coerce_int(total_raw)
        events = data.get("events") if data is not None else None
        event_preview, inferred_total = self._summarize_events(events)
        if total_events is None:
            total_events = inferred_total

        header_parts = []
        if batch_index is not None:
            header_parts.append(f"Batch #{batch_index}")
        if request_rid:
            header_parts.append(f"requestRid={request_rid}")
        if action_id:
            header_parts.append(f"actionId={action_id}")
        if total_events is not None:
            header_parts.append(f"{total_events} event(s)")

        header = " | ".join(header_parts) if header_parts else "Session document"

        sanitized = self._stringify_document(document, prune_large_fields=True)

        content_lines = [header]
        if event_preview:
            content_lines.append("Key events:")
            content_lines.extend(f"- {line}" for line in event_preview)
        content_lines.append(f"Details: {sanitized}")

        return SessionDocument(
            source=source,
            content="\n".join(content_lines),
            batch_index=batch_index,
            total_events=total_events,
            event_preview=event_preview,
        )

    def _summarize_events(
        self, events: Any
    ) -> tuple[List[str], int | None]:
        if events is None:
            return [], None

        if isinstance(events, str):
            stripped = events.strip()
            if not stripped:
                return [], None
            if stripped[0] in "[{":
                try:
                    parsed = json_util.loads(stripped)
                except (TypeError, ValueError):
                    truncated = self._truncate_text(
                        stripped, settings.session_event_preview_chars
                    )
                    return [truncated], None
                else:
                    # Prevent infinite recursion if parsing yields the same string.
                    if isinstance(parsed, str) and parsed == events:
                        truncated = self._truncate_text(
                            stripped, settings.session_event_preview_chars
                        )
                        return [truncated], None
                    return self._summarize_events(parsed)
            truncated = self._truncate_text(stripped, settings.session_event_preview_chars)
            return [truncated], None

        if isinstance(events, list):
            total = len(events)
            preview_items = events[: settings.session_event_preview_count]
            preview_lines = [self._describe_event(item) for item in preview_items]
            if total > len(preview_items):
                preview_lines.append(f"... {total - len(preview_items)} more event(s)")
            return preview_lines, total

        if isinstance(events, dict):
            # Treat a dict payload as a single event snapshot.
            return [self._describe_event(events)], 1

        return [self._truncate_text(str(events), settings.session_event_preview_chars)], None

    def _describe_event(self, event: Any) -> str:
        if isinstance(event, dict):
            flat_items = []
            for key, value in event.items():
                if isinstance(value, (dict, list)):
                    continue
                flat_items.append(f"{key}={value}")
            if flat_items:
                return ", ".join(flat_items)
            serialized = json_util.dumps(event, ensure_ascii=False)
            return self._truncate_text(serialized, settings.session_event_preview_chars)

        if isinstance(event, str):
            return self._truncate_text(event, settings.session_event_preview_chars)

        serialized = json_util.dumps(event, ensure_ascii=False)
        return self._truncate_text(serialized, settings.session_event_preview_chars)

    @staticmethod
    def _truncate_text(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(1, limit - 1)] + "…"

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if isinstance(value, bool):  # bool is subclass of int
            return None
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _stringify_document(
        document: dict, *, prune_large_fields: bool = False
    ) -> str:
        clean_document = MongoSessionRepository._sanitize_document(
            document, prune_large_fields=prune_large_fields
        )
        return json_util.dumps(clean_document, ensure_ascii=False)

    @staticmethod
    def _sanitize_document(
        document: dict[str, Any], *, prune_large_fields: bool = False
    ) -> dict[str, Any]:
        clean_document: dict[str, Any] = dict(document)
        clean_document.pop("_id", None)
        if prune_large_fields:
            data = clean_document.get("data")
            if isinstance(data, dict) and "events" in data:
                sanitized_data = dict(data)
                events_value = sanitized_data.get("events")
                if isinstance(events_value, list):
                    sanitized_data["events"] = (
                        f"<omitted {len(events_value)} event(s) for brevity>"
                    )
                elif events_value is not None:
                    sanitized_data["events"] = "<omitted events for brevity>"
                clean_document["data"] = sanitized_data
        return clean_document

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

    def _check_connection(self) -> bool:
        try:
            self._client.admin.command("ping")
        except PyMongoError:
            self._logger.exception(
                "MongoDB ping failed for %s/%s",
                self._uri_description,
                self._db.name,
            )
            return False

        self._logger.info(
            "MongoDB ping succeeded for %s/%s",
            self._uri_description,
            self._db.name,
        )
        return True

    def _collect_collection_documents(
        self, collection_names: Sequence[str]
    ) -> Tuple[Tuple[str, Tuple[str, ...]], ...]:
        samples: list[Tuple[str, Tuple[str, ...]]] = []
        for collection_name in collection_names:
            collection = self._db[collection_name]
            try:
                estimated = collection.estimated_document_count()
            except PyMongoError:
                self._logger.exception(
                    "Unable to estimate document count for collection '%s'", collection_name
                )
                estimated = None
            else:
                self._logger.info(
                    "Collection '%s' estimated document count: %s",
                    collection_name,
                    estimated,
                )

            try:
                documents = list(collection.find())
            except PyMongoError:
                self._logger.exception(
                    "Unable to fetch documents from collection '%s' for debugging",
                    collection_name,
                )
                continue

            self._logger.info(
                "Fetched %d document(s) from collection '%s' for debugging",
                len(documents),
                collection_name,
            )

            if estimated is not None and estimated > len(documents):
                self._logger.warning(
                    "Collection '%s' returned fewer documents (%d) than its estimate (%d)",
                    collection_name,
                    len(documents),
                    estimated,
                )

            stringified = tuple(self._stringify_document(document) for document in documents)
            for index, payload in enumerate(stringified, start=1):
                self._logger.debug(
                    "Collection '%s' document %d contents: %s",
                    collection_name,
                    index,
                    payload,
                )

            samples.append((collection_name, stringified))

        return tuple(samples)

    @staticmethod
    def _mask_uri(uri: str) -> str:
        if "@" not in uri:
            return uri
        prefix, suffix = uri.split("@", 1)
        if "//" in prefix:
            scheme, _ = prefix.split("//", 1)
            masked_prefix = f"{scheme}//***"
        else:
            masked_prefix = "***"
        return f"{masked_prefix}@{suffix}"
