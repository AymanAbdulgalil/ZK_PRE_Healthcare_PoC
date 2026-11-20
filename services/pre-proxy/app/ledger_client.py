"""Read-only web3.py client. The node checks isAccessActive() itself, uncached, rather
than trusting the provider's claim."""

import json
from functools import lru_cache

from web3 import Web3

from .config import settings


class LedgerClient:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.LEDGER_RPC_URL))
        with open(settings.LEDGER_DEPLOYMENT_FILE) as f:
            deployment = json.load(f)
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(deployment["address"]),
            abi=deployment["abi"],
        )

    def is_access_active(self, owner: str, provider: str, record_hash_hex: str) -> bool:
        record_hash = record_hash_hex.removeprefix("0x")
        return self.contract.functions.isAccessActive(
            Web3.to_checksum_address(owner),
            Web3.to_checksum_address(provider),
            bytes.fromhex(record_hash),
        ).call()


@lru_cache(maxsize=1)
def get_ledger_client() -> LedgerClient:
    return LedgerClient()