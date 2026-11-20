"""The provider's identity: a persisted Umbral receiving keypair, plus a Hardhat dev
account that acknowledges grants (paper §5.3 step 4) and reads the ledger."""

import os
from dataclasses import dataclass
from pathlib import Path

import umbral_pre
from config import settings
from eth_account import Account
from eth_account.signers.local import LocalAccount


@dataclass
class ProviderIdentity:
    receiving_sk: umbral_pre.SecretKey
    receiving_pk: umbral_pre.PublicKey
    eth_account: LocalAccount


def _load_or_create_key(path: Path) -> umbral_pre.SecretKey:
    if path.exists():
        return umbral_pre.SecretKey.from_be_bytes(path.read_bytes())

    sk = umbral_pre.SecretKey.random()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(sk.to_be_bytes())
    os.chmod(path, 0o600)
    return sk


def load_identity() -> ProviderIdentity:
    identity_dir = Path(settings.IDENTITY_DIR)
    receiving_sk = _load_or_create_key(identity_dir / "receiving.key")
    eth_account = Account.from_key(settings.PROVIDER_ETH_PRIVATE_KEY)

    return ProviderIdentity(
        receiving_sk=receiving_sk,
        receiving_pk=receiving_sk.public_key(),
        eth_account=eth_account,
    )