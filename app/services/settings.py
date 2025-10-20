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
    session_collections: List[str] = field(default_factory=list)
    enable_fallback_scan: bool = True
    fallback_scan_limit: int = 1000

    def __post_init__(self) -> None:
        configured = os.environ.get("SESSION_ID_FIELDS")
        if configured:
            self.session_id_fields = [
                field.strip() for field in configured.split(",") if field.strip()
            ]
        else:
            # Default to common naming conventions supported out of the box
            self.session_id_fields = ["sessionId", "session_id"]

        configured_collections = os.environ.get("SESSION_COLLECTIONS")
        if configured_collections:
            self.session_collections = [
                name.strip() for name in configured_collections.split(",") if name.strip()
            ]

        fallback_scan_flag = os.environ.get("ENABLE_SESSION_FALLBACK_SCAN")
        if fallback_scan_flag is not None:
            self.enable_fallback_scan = fallback_scan_flag.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }

        fallback_scan_limit = os.environ.get("SESSION_FALLBACK_SCAN_LIMIT")
        if fallback_scan_limit:
            try:
                parsed_limit = int(fallback_scan_limit)
            except ValueError:
                parsed_limit = self.fallback_scan_limit
            else:
                if parsed_limit > 0:
                    self.fallback_scan_limit = parsed_limit


settings = Settings()
