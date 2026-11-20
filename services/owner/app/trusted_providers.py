"""Providers whose address and Umbral key the owner verified out of band (paper §4.2).
Access can only be granted to these. Public material only, persisted with the owner's keys."""

import json
import os
import tempfile
from pathlib import Path

import umbral_pre
from config import settings
from web3 import Web3


def _path() -> Path:
    return Path(settings.IDENTITY_DIR) / "trusted_providers.json"


def load() -> dict:
    """{checksummed address: {"encryption_pk": hex, "label": str}}"""
    p = _path()
    if not p.exists():
        return {}
    return json.loads(p.read_text())


def get(address: str):
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
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".trusted_providers-")
    with os.fdopen(fd, "w") as f:
        json.dump(entries, f, indent=2)
    os.replace(tmp, path)


def add(address: str, encryption_pk_hex: str, label: str = ""):
    """Validates and stores a provider. Returns (checksummed address, key_changed); make a
    changed key loud, it may be an impostor's. ValueError if malformed."""
    key = Web3.to_checksum_address(address.strip())
    parse_pk(encryption_pk_hex)

    entries = load()
    new_pk = encryption_pk_hex.strip().removeprefix("0x").lower()
    previous = entries.get(key)
    key_changed = previous is not None and previous.get("encryption_pk") != new_pk
    entries[key] = {"encryption_pk": new_pk, "label": label.strip()[:80]}
    _save(entries)
    return key, key_changed


def remove(address: str) -> bool:
    """Removes a provider; on-chain grants are untouched. Returns whether anything was removed."""
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
