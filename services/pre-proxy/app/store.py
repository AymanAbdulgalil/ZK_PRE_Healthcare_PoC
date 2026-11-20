"""In-memory kfrag store, one per replica; lost on restart, and the owner can re-issue.
Only a strictly newer submission replaces an entry, so replays can't displace fresher ones."""

import threading
from typing import Optional

import umbral_pre


def _key(owner: str, provider: str, record_hash: str) -> str:
    return f"{owner.lower()}:{provider.lower()}:{record_hash.lower()}"


class KfragStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict = {}   # key -> (verified_kfrag, issued_at_ms)

    def put(
        self,
        owner: str,
        provider: str,
        record_hash: str,
        verified_kfrag: "umbral_pre.VerifiedKeyFrag",
        issued_at_ms: int,
    ) -> bool:
        """Stores the kfrag unless an equal-or-newer one is held. Returns whether it was stored."""
        k = _key(owner, provider, record_hash)
        with self._lock:
            current = self._entries.get(k)
            if current is not None and issued_at_ms <= current[1]:
                return False
            self._entries[k] = (verified_kfrag, issued_at_ms)
            return True

    def get(self, owner: str, provider: str, record_hash: str) -> Optional["umbral_pre.VerifiedKeyFrag"]:
        with self._lock:
            entry = self._entries.get(_key(owner, provider, record_hash))
            return entry[0] if entry else None

    def count(self) -> int:
        with self._lock:
            return len(self._entries)


store = KfragStore()
