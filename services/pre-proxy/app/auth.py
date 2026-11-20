"""Owner authentication for kfrag submissions (paper §5.3 step 2).

A kfrag's Umbral signature only shows self-consistency, since its keys arrive in the same
request: anyone could file one under another owner's address. So the owner also signs with
their Ethereum key, over the kfrag and keys, this proxy's id (no replay to another node)
and an issue time (no stale replay).

The message format MUST stay byte-identical to owner/app/proxy_client.py.
"""

import hashlib
import json

from eth_account import Account
from eth_account.messages import encode_defunct

DOMAIN = "zk-pre/kfrag-submission/v1"


def submission_message(
    *,
    owner: str,
    provider: str,
    record_hash: str,
    kfrag_hex: str,
    delegating_pk_hex: str,
    receiving_pk_hex: str,
    verifying_pk_hex: str,
    proxy_id: str,
    issued_at_ms: int,
) -> str:
    body = {
        "owner": owner.lower(),
        "provider": provider.lower(),
        "record_hash": record_hash.lower(),
        "kfrag_sha256": hashlib.sha256(bytes.fromhex(kfrag_hex)).hexdigest(),
        "delegating_pk": delegating_pk_hex.lower(),
        "receiving_pk": receiving_pk_hex.lower(),
        "verifying_pk": verifying_pk_hex.lower(),
        "proxy_id": str(proxy_id),
        "issued_at_ms": int(issued_at_ms),
    }
    return DOMAIN + "\n" + json.dumps(body, sort_keys=True, separators=(",", ":"))


def verify_owner_signature(req) -> bool:
    """True iff `req.owner_signature` is by `req.owner`'s key, over exactly this submission."""
    try:
        message = submission_message(
            owner=req.owner,
            provider=req.provider,
            record_hash=req.record_hash,
            kfrag_hex=req.kfrag_hex,
            delegating_pk_hex=req.delegating_pk_hex,
            receiving_pk_hex=req.receiving_pk_hex,
            verifying_pk_hex=req.verifying_pk_hex,
            proxy_id=req.proxy_id,
            issued_at_ms=req.issued_at_ms,
        )
        signer = Account.recover_message(
            encode_defunct(text=message), signature=req.owner_signature
        )
    except Exception:
        return False
    return signer.lower() == req.owner.lower()
