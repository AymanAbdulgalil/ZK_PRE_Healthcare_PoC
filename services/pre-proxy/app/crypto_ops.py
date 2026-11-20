"""This node's only crypto: verify a kfrag and re-encrypt a capsule. It holds no key that
can decrypt, so compromising it reveals no record contents."""

import umbral_pre


def verify_kfrag(
    kfrag_bytes: bytes,
    verifying_pk: umbral_pre.PublicKey,
    delegating_pk: umbral_pre.PublicKey,
    receiving_pk: umbral_pre.PublicKey,
) -> umbral_pre.VerifiedKeyFrag:
    """Checks the kfrag's signature against the claimed keys; raises if forged or mismatched.
    Who may file it under an owner is checked separately (auth.py)."""
    kfrag = umbral_pre.KeyFrag.from_bytes(kfrag_bytes)
    return kfrag.verify(verifying_pk, delegating_pk, receiving_pk)


def reencrypt(capsule_bytes: bytes, verified_kfrag: umbral_pre.VerifiedKeyFrag) -> bytes:
    capsule = umbral_pre.Capsule.from_bytes(capsule_bytes)
    vcfrag = umbral_pre.reencrypt(capsule, verified_kfrag)
    return bytes(vcfrag)