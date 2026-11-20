"""web3.py client for the owner: issue and revoke grants, list them from the event log."""

import json

from eth_account.signers.local import LocalAccount
from web3 import Web3


def strip_0x(s: str) -> str:
    return s.removeprefix("0x")


def fold_grants(granted, acknowledged, revoked) -> list[dict]:
    """Rebuilds grant state from the three event streams, one row per grantId, so a
    re-grant after revocation is its own row."""
    grants: dict = {}
    for ev in sorted(granted, key=lambda e: (e["blockNumber"], e["logIndex"])):
        a = ev["args"]
        grants[a["grantId"]] = {
            "grant_id": a["grantId"],
            "owner": a["owner"],
            "provider": a["provider"],
            "record_hash": "0x" + bytes(a["recordHash"]).hex(),
            "granted_at": a["grantedAt"],
            "acknowledged": False,
            "acknowledged_at": 0,
            "revoked_at": 0,
        }
    for ev in acknowledged:
        g = grants.get(ev["args"]["grantId"])
        if g is not None:
            g["acknowledged"] = True
            g["acknowledged_at"] = ev["args"]["acknowledgedAt"]
    for ev in revoked:
        g = grants.get(ev["args"]["grantId"])
        if g is not None:
            g["revoked_at"] = ev["args"]["revokedAt"]
    return [grants[k] for k in sorted(grants)]


class LedgerClient:
    def __init__(self, eth_account: LocalAccount, rpc_url: str, deployment_file: str):
        self.w3 = Web3(Web3.HTTPProvider(rpc_url))
        with open(deployment_file) as f:
            deployment = json.load(f)
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(deployment["address"]),
            abi=deployment["abi"],
        )
        self.account = eth_account

    def _send(self, fn) -> str:
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "chainId": self.w3.eth.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        if receipt.status != 1:
            raise RuntimeError("transaction was mined but reverted")
        h = receipt.transactionHash.hex()
        return h if h.startswith("0x") else "0x" + h

    def grant_access(self, provider: str, record_hash_hex: str) -> str:
        """Paper §5.3 step 3: the signed transaction is the authorisation."""
        fn = self.contract.functions.grantAccess(
            Web3.to_checksum_address(provider),
            bytes.fromhex(strip_0x(record_hash_hex)),
        )
        return self._send(fn)

    def revoke_access(self, provider: str, record_hash_hex: str) -> str:
        fn = self.contract.functions.revokeAccess(
            Web3.to_checksum_address(provider),
            bytes.fromhex(strip_0x(record_hash_hex)),
        )
        return self._send(fn)

    def my_grants(self) -> list[dict]:
        """Grants this owner issued, oldest first. Reads from genesis: fine on a local chain only."""
        events = self.contract.events
        flt = {"owner": self.account.address}
        return fold_grants(
            events.AccessGranted.get_logs(from_block=0, argument_filters=flt),
            events.AccessAcknowledged.get_logs(from_block=0, argument_filters=flt),
            events.AccessRevoked.get_logs(from_block=0, argument_filters=flt),
        )
