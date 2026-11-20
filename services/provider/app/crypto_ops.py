"""Provider-side Umbral operations (paper §5.3 steps 7-8): verify each cfrag's correctness
proof, then combine a threshold of verified ones and decrypt locally. Never skip step 7:
without it a byzantine proxy's output would be trusted."""

import umbral_pre
from web3 import Web3


def matches_content_address(ciphertext: bytes, record_hash: str) -> bool:
    """Re-derives the record's keccak256 identifier, so storage serving other bytes is noticed."""
    return ("0x" + Web3.keccak(ciphertext).hex()).lower() == record_hash.lower()


def verify_cfrags(
    capsule_bytes: bytes,
    received: list[tuple[str, str]],
    verifying_pk: umbral_pre.PublicKey,
    delegating_pk: umbral_pre.PublicKey,
    receiving_pk: umbral_pre.PublicKey,
):
    """Step 7. Checks each (source, cfrag_hex) alone; a bad fragment is discarded and its node
    reported as byzantine. Returns (verified, rejected): [(source, VerifiedCapsuleFrag)] and
    [(source, reason)]."""
    capsule = umbral_pre.Capsule.from_bytes(capsule_bytes)
    verified, rejected = [], []
    for source, cfrag_hex in received:
        try:
            suspicious = umbral_pre.CapsuleFrag.from_bytes(bytes.fromhex(cfrag_hex))
            verified.append(
                (source, suspicious.verify(capsule, verifying_pk, delegating_pk, receiving_pk))
            )
        except Exception as exc:
            rejected.append((source, f"{type(exc).__name__}: {exc}"))
    return verified, rejected


def decrypt_with_verified(
    receiving_sk: umbral_pre.SecretKey,
    delegating_pk: umbral_pre.PublicKey,
    capsule_bytes: bytes,
    verified: list,
    ciphertext: bytes,
    threshold: int,
) -> bytes:
    """Step 8. Combines `threshold` verified fragments with the provider's key. Refuses fewer,
    since the library can't tell too few from wrong until decryption fails."""
    if len(verified) < threshold:
        raise ValueError(
            f"only {len(verified)} verified fragment(s); need {threshold}"
        )
    capsule = umbral_pre.Capsule.from_bytes(capsule_bytes)
    vcfrags = [vcfrag for _source, vcfrag in verified[:threshold]]
    return umbral_pre.decrypt_reencrypted(
        receiving_sk, delegating_pk, capsule, vcfrags, ciphertext
    )
