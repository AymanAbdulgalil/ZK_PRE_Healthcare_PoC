"""Deleting a record, in order (each step is idempotent):
  1. Revoke live grants on-chain; if any revocation fails, nothing is erased.
  2. Confirm no live grant is left.
  3. Erase capsule and ciphertext from storage and confirm it.
  4. Drop the local label.

Not removed: ledger history, kfrags in proxy memory until restart (useless without the
ciphertext), and anything a provider already decrypted.
"""

import re

_HASH = re.compile(r"^0x[0-9a-f]{64}$")


class DeleteError(RuntimeError):
    """The delete stopped at a step; the message says which, and the record's state."""


def live_grants(grants: list[dict], record_hash: str) -> list[dict]:
    """Grants for this record that have not been revoked."""
    return [
        g for g in grants
        if g["record_hash"].lower() == record_hash and not g["revoked_at"]
    ]


def delete_record(record_hash: str, ledger, storage, labels, on_step=None) -> dict:
    """Returns {"revoked": n, "objects": m}. Raises DeleteError."""
    record_hash = (record_hash or "").strip().lower()
    if not _HASH.match(record_hash):
        raise DeleteError("not a valid record hash; nothing was changed")

    def say(msg: str) -> None:
        if on_step:
            on_step(msg)

    # 1. revoke live grants
    try:
        live = live_grants(ledger.my_grants(), record_hash)
    except Exception as exc:
        raise DeleteError(f"couldn't read the ledger ({exc}); nothing was changed") from exc

    revoked = 0
    for g in live:
        try:
            tx = ledger.revoke_access(g["provider"], record_hash)
        except Exception as exc:
            raise DeleteError(
                f"revoking the grant to {g['provider']} failed ({exc}). "
                f"{revoked} grant(s) were revoked; the record has NOT been erased."
            ) from exc
        revoked += 1
        say(f"revoked the grant to {g['provider']} (tx {tx})")
    if not live:
        say("no live grants to revoke")

    # 2. confirm
    try:
        still_live = live_grants(ledger.my_grants(), record_hash)
    except Exception as exc:
        raise DeleteError(
            f"couldn't confirm the revocations ({exc}); the record has NOT been erased."
        ) from exc
    if still_live:
        raise DeleteError(
            f"{len(still_live)} grant(s) are still live after revocation; the record has NOT been erased."
        )

    # 3. erase from storage
    try:
        objects = storage.delete_record(record_hash)
    except Exception as exc:
        raise DeleteError(
            f"all grants are revoked, but erasing the stored record failed ({exc}). "
            "Delete it again to retry."
        ) from exc
    say(f"erased {objects} stored object(s)" if objects else "nothing was left in storage")

    # 4. drop the local label
    try:
        if labels.remove(record_hash):
            say("removed the local label")
    except Exception as exc:                     # the record is already gone; a stale label is harmless
        say(f"couldn't remove the local label ({exc})")

    return {"revoked": revoked, "objects": objects}
