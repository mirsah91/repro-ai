from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    mongo_uri: str = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.environ.get("MONGO_DB", "sessions")
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    session_id_fields: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        configured = os.environ.get("SESSION_ID_FIELDS")
        if configured:
            self.session_id_fields = [
                field.strip() for field in configured.split(",") if field.strip()
            ]
        else:
            # Default to common naming conventions supported out of the box
            self.session_id_fields = ["sessionId", "session_id"]


settings = Settings()
