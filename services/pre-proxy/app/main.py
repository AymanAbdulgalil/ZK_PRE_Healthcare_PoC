import logging
import time

import umbral_pre
from fastapi import FastAPI, HTTPException

from .auth import verify_owner_signature
from .config import settings
from .crypto_ops import reencrypt, verify_kfrag
from .ledger_client import get_ledger_client
from .schemas import (
    HealthResponse,
    ReencryptRequest,
    ReencryptResponse,
    SubmitKfragRequest,
    SubmitKfragResponse,
)
from .store import store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(f"pre-proxy-{settings.PROXY_ID}")

app = FastAPI(title=f"pre-proxy-{settings.PROXY_ID}", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        proxy_id=settings.PROXY_ID,
        kfrags_held=store.count(),
        threshold=settings.PRE_THRESHOLD,
        shares=settings.PRE_SHARES,
    )


@app.post("/kfrags", response_model=SubmitKfragResponse)
def submit_kfrag(req: SubmitKfragRequest):
    try:
        verifying_pk = umbral_pre.PublicKey.from_compressed_bytes(bytes.fromhex(req.verifying_pk_hex))
        delegating_pk = umbral_pre.PublicKey.from_compressed_bytes(bytes.fromhex(req.delegating_pk_hex))
        receiving_pk = umbral_pre.PublicKey.from_compressed_bytes(bytes.fromhex(req.receiving_pk_hex))
        kfrag_bytes = bytes.fromhex(req.kfrag_hex)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"malformed request: {exc}")

    # 1. The owner's Ethereum signature ties the submission to the owner address.
    if req.proxy_id != settings.PROXY_ID:
        raise HTTPException(status_code=403, detail="submission was signed for a different proxy node")
    age_ms = abs(int(time.time() * 1000) - req.issued_at_ms)
    if age_ms > settings.KFRAG_MAX_AGE_SECONDS * 1000:
        raise HTTPException(status_code=403, detail="submission is outside the accepted time window")
    if not verify_owner_signature(req):
        log.warning("rejected kfrag submission: bad owner signature (claimed owner %s)", req.owner)
        raise HTTPException(status_code=403, detail="the patient's signature does not match the claimed patient address")

    # 2. Reject a kfrag not validly signed by the owner's Umbral key.
    try:
        verified = verify_kfrag(kfrag_bytes, verifying_pk, delegating_pk, receiving_pk)
    except Exception as exc:
        log.warning("kfrag failed verification: %s", exc)
        raise HTTPException(status_code=400, detail="kfrag failed verification")

    if not store.put(req.owner, req.provider, req.record_hash, verified, req.issued_at_ms):
        raise HTTPException(
            status_code=409,
            detail="an equal or newer key fragment for this patient / health care provider / record is already stored",
        )
    log.info("stored verified kfrag for %s -> %s (%s)", req.owner, req.provider, req.record_hash)
    return SubmitKfragResponse(stored=True)


@app.post("/reencrypt", response_model=ReencryptResponse)
def do_reencrypt(req: ReencryptRequest):
    # Paper §5.3 step 5: ask the ledger directly on every request, uncached. This live
    # check is what makes revocation take effect.
    ledger = get_ledger_client()
    try:
        active = ledger.is_access_active(req.owner, req.provider, req.record_hash)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"malformed patient / health care provider / record hash: {exc}")
    except Exception as exc:
        log.error("ledger check failed: %s", exc)
        raise HTTPException(status_code=502, detail="could not verify access status on-chain")

    if not active:
        raise HTTPException(
            status_code=403,
            detail="access not active on-chain (no grant, not yet acknowledged by the health care provider, or revoked)",
        )

    # Paper §5.3 step 6: re-encrypt using only this node's own fragment.
    verified_kfrag = store.get(req.owner, req.provider, req.record_hash)
    if verified_kfrag is None:
        raise HTTPException(status_code=404, detail="no key fragment on file for this patient / health care provider / record")

    try:
        cfrag_bytes = reencrypt(bytes.fromhex(req.capsule_hex), verified_kfrag)
    except Exception as exc:
        log.error("re-encryption failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"re-encryption failed: {exc}")

    return ReencryptResponse(cfrag_hex=cfrag_bytes.hex())
