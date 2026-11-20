"""HTTP client for proxy kfrag intake (paper §5.3 step 2). Submissions are signed and
bound to one proxy. The message format MUST stay byte-identical to pre-proxy/app/auth.py."""

import hashlib
import json
import time

import requests
from eth_account.messages import encode_defunct
from eth_account.signers.local import LocalAccount

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


def get_proxy_id(endpoint: str, timeout: int = 5):
    """Asks a node for its PROXY_ID. Returns (proxy_id, error_message); exactly one is None."""
    try:
        resp = requests.get(f"http://{endpoint}/health", timeout=timeout)
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code} from /health"
        return str(resp.json()["proxy_id"]), None
    except (requests.RequestException, KeyError, ValueError) as exc:
        return None, str(exc)


def submit_kfrag(
    endpoint: str,
    account: LocalAccount,
    *,
    provider: str,
    record_hash: str,
    kfrag: bytes,
    delegating_pk_hex: str,
    receiving_pk_hex: str,
    verifying_pk_hex: str,
    timeout: int = 5,
):
    """Delivers one kfrag to one proxy. Returns (delivered, error_message)."""
    proxy_id, err = get_proxy_id(endpoint, timeout)
    if proxy_id is None:
        return False, err

    kfrag_hex = kfrag.hex()
    issued_at_ms = time.time_ns() // 1_000_000
    message = submission_message(
        owner=account.address,
        provider=provider,
        record_hash=record_hash,
        kfrag_hex=kfrag_hex,
        delegating_pk_hex=delegating_pk_hex,
        receiving_pk_hex=receiving_pk_hex,
        verifying_pk_hex=verifying_pk_hex,
        proxy_id=proxy_id,
        issued_at_ms=issued_at_ms,
    )
    signature = account.sign_message(encode_defunct(text=message)).signature.hex()

    try:
        resp = requests.post(
            f"http://{endpoint}/kfrags",
            json={
                "owner": account.address,
                "provider": provider,
                "record_hash": record_hash,
                "kfrag_hex": kfrag_hex,
                "delegating_pk_hex": delegating_pk_hex,
                "receiving_pk_hex": receiving_pk_hex,
                "verifying_pk_hex": verifying_pk_hex,
                "proxy_id": proxy_id,
                "issued_at_ms": issued_at_ms,
                "owner_signature": signature if signature.startswith("0x") else "0x" + signature,
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, str(exc)

    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    return True, None
