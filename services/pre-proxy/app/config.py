import os


class Settings:
    PROXY_ID: str = os.environ.get("PROXY_ID", "0")
    PRE_THRESHOLD: int = int(os.environ.get("PRE_THRESHOLD", "2"))
    PRE_SHARES: int = int(os.environ.get("PRE_SHARES", "3"))

    LEDGER_RPC_URL: str = os.environ.get("LEDGER_RPC_URL", "http://ledger:8545")
    LEDGER_DEPLOYMENT_FILE: str = os.environ.get(
        "LEDGER_DEPLOYMENT_FILE", "/app/ledger-deployment/AccessControl.json"
    )

    # Max clock skew for a signed kfrag submission before it is refused as stale (see auth.py).
    KFRAG_MAX_AGE_SECONDS: int = int(os.environ.get("KFRAG_MAX_AGE_SECONDS", "300"))


settings = Settings()
