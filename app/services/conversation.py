from __future__ import annotations

import secrets
from collections import defaultdict
from typing import DefaultDict, List


class ConversationStore:
    """Ephemeral in-memory storage for conversation turns."""

    def __init__(self) -> None:
        self._store: DefaultDict[str, List[dict[str, str]]] = defaultdict(list)

    def generate_id(self) -> str:
        return secrets.token_hex(8)

    def append(self, conversation_id: str, role: str, content: str) -> None:
        self._store[conversation_id].append({"role": role, "content": content})

    def get(self, conversation_id: str) -> List[dict[str, str]]:
        return list(self._store.get(conversation_id, []))
