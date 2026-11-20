"""HTTP client for re-encryption fragments (paper §5.3 step 5). POST /reencrypt returns
{"cfrag_hex": ...}, or non-200 if the grant isn't active or no kfrag is on file.
A cfrag is untrusted until crypto_ops.verify_cfrags checks it."""

import requests


def request_cfrag(endpoint: str, owner: str, provider: str, record_hash: str, capsule_hex: str, timeout: int = 5):
    """Returns (cfrag_hex, error_message). Exactly one is None."""
    try:
        resp = requests.post(
            f"http://{endpoint}/reencrypt",
            json={
                "owner": owner,
                "provider": provider,
                "record_hash": record_hash,
                "capsule_hex": capsule_hex,
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code}: {resp.text[:200]}"
        return resp.json().get("cfrag_hex"), None
    except requests.RequestException as exc:
        return None, str(exc)