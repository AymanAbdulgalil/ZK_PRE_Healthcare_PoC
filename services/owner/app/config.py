import os


def _split_csv(value: str):
    return [v.strip() for v in value.split(",") if v.strip()]


class Settings:
    # --- storage --------------------------------------------------------
    MINIO_ENDPOINT: str = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    # This client's own MinIO user, never root. Required.
    MINIO_ACCESS_KEY: str = os.environ["MINIO_ACCESS_KEY"]
    MINIO_SECRET_KEY: str = os.environ["MINIO_SECRET_KEY"]

    # --- proxy re-encryption nodes ---------------------------------------
    PRE_PROXY_ENDPOINTS = _split_csv(os.environ.get("PRE_PROXY_ENDPOINTS", ""))
    PRE_THRESHOLD: int = int(os.environ.get("PRE_THRESHOLD", "2"))
    PRE_SHARES: int = int(os.environ.get("PRE_SHARES", "3"))

    # --- ledger -----------------------------------------------------------
    LEDGER_RPC_URL: str = os.environ.get("LEDGER_RPC_URL", "http://ledger:8545")
    LEDGER_DEPLOYMENT_FILE: str = os.environ.get(
        "LEDGER_DEPLOYMENT_FILE", "/app/ledger-deployment/AccessControl.json"
    )

    # Hardhat dev account #2: public and pre-funded, local chain only. Required.
    OWNER_ETH_PRIVATE_KEY: str = os.environ["OWNER_ETH_PRIVATE_KEY"]

    # Where the owner's Umbral keypair is persisted across restarts.
    IDENTITY_DIR: str = os.environ.get("IDENTITY_DIR", "/app/identity")


settings = Settings()
