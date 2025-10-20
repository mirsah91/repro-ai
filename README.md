# repro-ai

AI service providing session summarization and conversational insights over MongoDB-backed data. The service is built with FastAPI and integrates with an LLM provider for natural language understanding.

## Features

- Summarize a session across multiple MongoDB collections using a single endpoint.
- Conversational interface that answers arbitrary questions about the session data.
- Automatically orders batched trace documents by `batchIndex`, merges them into a
  chronological view, and condenses oversized event payloads before handing them to the LLM.
- Modular design that separates data access, orchestration, and language model integrations.

## Getting started

1. Install dependencies

```bash
pip install -e .
```

2. Set required environment variables (use a `.env` file or export directly):

- `MONGO_URI`
- `MONGO_DB`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` (defaults to `gpt-4o-mini` if omitted)
- `SESSION_ID_FIELDS` (optional, comma-separated list of field names to search for a
  session identifier; defaults to `sessionId,session_id`). The repository automatically
  attempts to match identifiers stored as strings, MongoDB `ObjectId`s, or UUID values
  (including legacy binary encodings).
- `SESSION_COLLECTIONS` (optional). Provide a comma-separated list of MongoDB collection
  names (e.g. `traces,events`) to limit lookups to known sources instead of scanning every
  collection in the database. This is useful when session data is consolidated in a
  specific collection such as `traces`.
- `ENABLE_SESSION_FALLBACK_SCAN` (optional, defaults to `true`). When enabled, each
  collection is opportunistically scanned for documents that contain the provided
  session identifier anywhere in the payload. This helps locate sessions where the ID
  is stored in unexpected fields or nested objects.
- `SESSION_FALLBACK_SCAN_LIMIT` (optional, defaults to `1000`). Caps the number of
  documents scanned per collection during the fallback search.
- `SESSION_EVENT_PREVIEW_COUNT` (optional, defaults to `5`). Controls how many events are
  included in the condensed preview for each batch when `data.events` contains large arrays.
- `SESSION_EVENT_PREVIEW_CHARS` (optional, defaults to `400`). Caps the length of each
  preview line so extremely large event payloads do not overwhelm the prompt budget.

If a session cannot be found, the API now returns a structured 404 response outlining
the fields and collections that were checked, plus details about the fallback scan.
This diagnostic data is useful for tuning `SESSION_ID_FIELDS` or confirming that the
database contains the requested identifier.

3. Run the API server

```bash
uvicorn app.main:app --reload
```

The interactive API docs are available at `http://localhost:8000/docs`.

### Handling large batched traces

Session data stored in collections such as `traces` is often written in batches. The
service retrieves every document that matches the session ID, sorts the records by
`batchIndex`, and builds a chronological narrative for the language model. When
`data.events` holds a very large JSON array, only the leading events (up to the configured
preview count) are surfaced alongside a summary string indicating how many additional
entries were omitted. This keeps prompts small enough for reliable LLM responses while
retaining the most useful context for summarisation and follow-up questions.

## Project structure

```
app/
  main.py              # FastAPI application instance
  models/              # Pydantic models
  routers/             # API route definitions
  services/            # Database + AI orchestration logic
```

## Testing

```bash
pytest
```
