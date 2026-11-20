"""Owner-side Umbral operations (paper §5.3 steps 1-2): encrypt records and split
re-encryption keys. Hashes use Web3.keccak, matching the proxies and the provider."""

import umbral_pre
from web3 import Web3


def encrypt_record(delegating_pk: umbral_pre.PublicKey, plaintext: bytes) -> tuple[bytes, bytes]:
    """Encrypts with the owner's public key. Returns (capsule_bytes, ciphertext_bytes)."""
    capsule, ciphertext = umbral_pre.encrypt(delegating_pk, plaintext)
    return bytes(capsule), ciphertext


def record_hash_from_ciphertext(ciphertext: bytes) -> str:
    """0x-prefixed keccak256: the record's on-chain pointer and storage address."""
    return "0x" + Web3.keccak(ciphertext).hex()


def generate_kfrags(
    delegating_sk: umbral_pre.SecretKey,
    receiving_pk: umbral_pre.PublicKey,
    signer: umbral_pre.Signer,
    threshold: int,
    shares: int,
) -> list[bytes]:
    """Splits a re-encryption key into `shares` kfrags; any `threshold` of them suffice."""
    verified_kfrags = umbral_pre.generate_kfrags(
        delegating_sk,
        receiving_pk,
        signer,
        threshold,
        shares,
        True,  # sign_delegating_key
        True,  # sign_receiving_key
    )
    return [bytes(kfrag) for kfrag in verified_kfrags]
