from __future__ import annotations
from typing import Dict, Any, List
from .schemas import Profile, Question

class MemoryStore:
    def __init__(self):
        self.sessions: Dict[str, Dict[str, Any]] = {}

    def create(self, profile: Profile) -> str:
        import uuid, time
        sid = str(uuid.uuid4())
        self.sessions[sid] = {
            "created_at": time.time(),
            "profile": profile,
            "asked": [],
            "log": [],   # list of {q, a, ts}
        }
        return sid

    def get(self, sid: str) -> Dict[str, Any] | None:
        return self.sessions.get(sid)

STORE = MemoryStore()
