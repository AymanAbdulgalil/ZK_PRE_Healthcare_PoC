"""Local-only record labels: a JSON file (mode 0600) in the identity volume, never
uploaded. Each client keeps its own, keyed by record hash. Plain text, so keep
sensitive detail out."""

import json
import os
import re
import tempfile
from pathlib import Path

from config import settings

MAX_LENGTH = 80
_HASH = re.compile(r"^0x[0-9a-f]{64}$")


def _path() -> Path:
    return Path(settings.IDENTITY_DIR) / "record_labels.json"


def normalise_hash(record_hash: str) -> str:
    """Lower-cases and validates a record hash; raises ValueError if malformed."""
    h = (record_hash or "").strip().lower()
    if not _HASH.match(h):
        raise ValueError("a record hash is 0x followed by 64 hexadecimal digits")
    return h


def clean(label: str) -> str:
    """Collapses control characters and whitespace, trims, cuts to MAX_LENGTH."""
    text = re.sub(r"[\x00-\x1f\x7f]", " ", label or "")
    return re.sub(r"\s+", " ", text).strip()[:MAX_LENGTH]


def load() -> dict:
    """{record hash: label}. An unparsable file is set aside as record_labels.json.corrupt."""
    p = _path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text())
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return {str(k): str(v) for k, v in data.items()}
    except (ValueError, OSError):
        try:
            os.replace(p, p.with_name(p.name + ".corrupt"))
        except OSError:
            pass
        return {}


def get(record_hash: str) -> str:
    """The label for this record, or "" if it has none."""
    try:
        return load().get(normalise_hash(record_hash), "")
    except ValueError:
        return ""


def _save(entries: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".record_labels-")   # created 0600
    with os.fdopen(fd, "w") as f:
        json.dump(entries, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def set_label(record_hash: str, label: str) -> str:
    """Sets or (if empty) clears a label; returns it as stored. ValueError on a bad hash."""
    key = normalise_hash(record_hash)
    text = clean(label)
    entries = load()
    if text:
        entries[key] = text
    else:
        entries.pop(key, None)
    _save(entries)
    return text


def remove(record_hash: str) -> bool:
    """Drops a record's label. Returns whether there was one."""
    key = normalise_hash(record_hash)
    entries = load()
    if key not in entries:
        return False
    del entries[key]
    _save(entries)
    return True


def display(record_hash: str, labels: dict | None = None, *, head: int = 10) -> str:
    """Display name: the label if any, plus the start of the hash to tell duplicates apart."""
    entries = load() if labels is None else labels
    short = record_hash[:head] + "…" if len(record_hash) > head else record_hash
    label = entries.get(record_hash.lower(), "")
    return f"{label} ({short})" if label else short
