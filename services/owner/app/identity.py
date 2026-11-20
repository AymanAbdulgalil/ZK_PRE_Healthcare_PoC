"""The owner's identity: persisted Umbral encryption and signing keypairs, plus a
Hardhat dev account (see config.py) that signs AccessControl.sol transactions."""

import os
from dataclasses import dataclass
from pathlib import Path

import umbral_pre
from config import settings
from eth_account import Account
from eth_account.signers.local import LocalAccount


@dataclass
class OwnerIdentity:
    delegating_sk: umbral_pre.SecretKey
    delegating_pk: umbral_pre.PublicKey
    signing_sk: umbral_pre.SecretKey
    signer: umbral_pre.Signer
    verifying_pk: umbral_pre.PublicKey
    eth_account: LocalAccount


def _load_or_create_key(path: Path) -> umbral_pre.SecretKey:
    if path.exists():
        return umbral_pre.SecretKey.from_be_bytes(path.read_bytes())

    sk = umbral_pre.SecretKey.random()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sk.to_be_bytes())
    os.chmod(path, 0o600)
    return sk


def load_identity() -> OwnerIdentity:
    identity_dir = Path(settings.IDENTITY_DIR)

    delegating_sk = _load_or_create_key(identity_dir / "delegating.key")
    signing_sk = _load_or_create_key(identity_dir / "signing.key")
    signer = umbral_pre.Signer(signing_sk)

    eth_account = Account.from_key(settings.OWNER_ETH_PRIVATE_KEY)

    return OwnerIdentity(
        delegating_sk=delegating_sk,
        delegating_pk=delegating_sk.public_key(),
        signing_sk=signing_sk,
        signer=signer,
        verifying_pk=signing_sk.public_key(),
        eth_account=eth_account,
    )
