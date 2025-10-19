from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    mongo_uri: str = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.environ.get("MONGO_DB", "sessions")
    openai_api_key: str | None = os.environ.get("OPENAI_API_KEY")
    openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")


settings = Settings()
