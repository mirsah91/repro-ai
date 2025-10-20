# repro-ai

AI service providing session summarization and conversational insights over MongoDB-backed data. The service is built with FastAPI and integrates with an LLM provider for natural language understanding.

## Features

- Summarize a session across multiple MongoDB collections using a single endpoint.
- Conversational interface that answers arbitrary questions about the session data.
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

3. Run the API server

```bash
uvicorn app.main:app --reload
```

The interactive API docs are available at `http://localhost:8000/docs`.

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
