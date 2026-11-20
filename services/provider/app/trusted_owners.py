"""Owners whose identities were verified out of band (paper §4.2, §5.3). Holds their
address and two Umbral public keys, needed for proof checks (step 7). Public material
only, persisted with the provider's key."""

import json
import os
import tempfile
from pathlib import Path

import umbral_pre
from config import settings
from web3 import Web3


def _path() -> Path:
    return Path(settings.IDENTITY_DIR) / "trusted_owners.json"


def load() -> dict:
    """{checksummed address: {"delegating_pk": hex, "verifying_pk": hex, "label": str}}; older entries lack label."""
    p = _path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def get(address: str):
    """The stored entry for this owner, or None."""
    try:
        key = Web3.to_checksum_address(address)
    except ValueError:
        return None
    return load().get(key)


def parse_pk(pk_hex: str) -> umbral_pre.PublicKey:
    return umbral_pre.PublicKey.from_compressed_bytes(
        bytes.fromhex(pk_hex.strip().removeprefix("0x"))
    )


def _save(entries: dict) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".trusted_owners-")
    with os.fdopen(fd, "w") as f:
        json.dump(entries, f, indent=2)
    os.replace(tmp, path)


def add(address: str, delegating_pk_hex: str, verifying_pk_hex: str, label: str = ""):
    """Validates and stores an owner. Returns (checksummed address, keys_changed); make
    changed keys loud, they may be an impostor's. ValueError if malformed."""
    key = Web3.to_checksum_address(address.strip())
    parse_pk(delegating_pk_hex)
    parse_pk(verifying_pk_hex)

    entries = load()
    new_d = delegating_pk_hex.strip().removeprefix("0x").lower()
    new_v = verifying_pk_hex.strip().removeprefix("0x").lower()
    previous = entries.get(key)
    keys_changed = previous is not None and (
        previous.get("delegating_pk") != new_d or previous.get("verifying_pk") != new_v
    )
    entries[key] = {"delegating_pk": new_d, "verifying_pk": new_v, "label": label.strip()[:80]}
    _save(entries)
    return key, keys_changed


def remove(address: str) -> bool:
    """Removes an owner; their grants can't be acknowledged or used until re-trusted.
    Returns whether anything was removed."""
    try:
        key = Web3.to_checksum_address(address)
    except ValueError:
        return False
    entries = load()
    if key not in entries:
        return False
    del entries[key]
    _save(entries)
    return True
