# ZK-PRE-Healthcare

Threshold proxy re-encryption (Umbral, 2-of-3) for sharing health records, with a four-function Solidity audit ledger and MinIO object storage. Everything runs under Docker Compose.

> **Status: archived.** This was a semester research project, and it did not meet its objectives. It is kept here as a record and is no longer maintained.

## Outcome

The project fell short of what it set out to do, but it was worth the experience and what I learned along the way.

**Verdict: the premise is valid, but this approach is not optimal.** Combining threshold proxy re-encryption, an on-chain access ledger and separate object storage does give patient-controlled, revocable sharing of health records. Other approaches, or a combination of them, can meet the same objectives with better performance and less overhead, setup time and complexity.

The code below still builds and runs as described, for anyone who wants to study or reuse parts of it.

## Roles in the interface

| Interface name | Compose service | URL |
| --- | --- | --- |
| **Patient** (the data owner) | `owner` | http://localhost:8501 |
| **Health Care Provider** (a physician, lab, specialist or insurer) | `provider` | http://localhost:8502 |
| MinIO console (ciphertext only) | `minio` | http://localhost:9090 (loopback only, port set by `MINIO_CONSOLE_PORT`) |
| One-shot storage set-up (runs, checks, exits) | `minio-init` | none |

The service, container, volume and environment-variable names (`owner`, `provider`, `OWNER_ETH_PRIVATE_KEY`, ...) and the contract's own parameter names are unchanged, so the code still lines up with the paper and the ledger. Only what you see on screen uses the new names.

## Run

```bash
cp .env.example .env
# then in .env give MINIO_ROOT_PASSWORD, OWNER_MINIO_PASSWORD and
# PROVIDER_MINIO_PASSWORD three different random values, e.g. from:  openssl rand -hex 24
docker compose up --build
docker compose logs minio-init      # shows the storage access checks (see below)
```
## Object-storage access

Each client connects to MinIO as its own user, with one policy (`services/minio-init/policies/`). The MinIO root credentials are seen only by `minio` and by the one-shot `minio-init` service, never by a client.

| Client | May | May not |
| --- | --- | --- |
| Patient (`owner`, user `OWNER_MINIO_USER`) | list the bucket; store and erase objects under `records/` | read objects back, write anywhere else, create buckets |
| Health Care Provider (`provider`, user `PROVIDER_MINIO_USER`) | list the bucket; read objects under `records/` | write, overwrite or delete anything, create buckets |

`minio-init` runs on every `docker compose up`, before the clients: it creates the bucket, creates or updates the two users and their policies, and then acts as each user to check the result (the provider's attempts to overwrite, delete or create are refused and leave the stored object unchanged; the patient cannot write outside `records/`, read back, or create a bucket). If any check fails it exits with an error and `owner` and `provider` do not start. Changing a password in `.env` and running `docker compose up -d` applies it.

The provider may list the bucket because S3 answers "access denied" rather than "not found" for a missing key when the caller cannot list; with listing, a deleted record is shown as "no longer in storage".

## Records, labels and deletion (Patient)

* **Upload record** encrypts on the device and stores a capsule and a ciphertext. A label is optional.
* **My records** lists what storage holds for you, with the size, the number of live grants and a label field.
* **Labels are local only.** A label is your own note about a record. It is written to a file in that client's private volume and nowhere else: not to MinIO, not to the proxy nodes, not to the ledger. The Patient and the Health Care Provider each keep their own labels, independent of each other (the provider labels a grant's record under *Grants naming you*). A label is plain text, so keep sensitive detail out of it.
* **Delete record** asks for confirmation, then in this order: revokes every live grant for the record on-chain; checks that none is left live; erases the capsule and ciphertext from storage and checks that nothing remains; removes the local label. If any revocation fails nothing is erased. Repeating a delete that was cut short is safe.
  * The ledger keeps its history: deleting adds revocations and removes nothing.
  * Proxy nodes have no delete operation, so key fragments they hold for the record stay in memory until the node restarts. They are useless without the ciphertext.
  * A health care provider who already decrypted the record keeps what they saw. Opening a deleted record shows "no longer in storage".

## Tests

Each service has its own tests (they share module names, so run them separately). They use an in-memory object store and a fake ledger, and drive the real Streamlit apps. The storage tests put each client behind an object store that enforces that client's real policy file, so a policy that is missing something the client needs, or that grants too much, fails a test. The tests in `tests/` check the policy files, `docker-compose.yml` and `services/minio-init/init.sh`.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r services/owner/requirements.txt pytest pyyaml
(cd services/owner    && python -m pytest -q tests)
(cd services/provider && python -m pytest -q tests)
python -m pytest -q tests                                    # policies, compose file, minio-init
(cd services/ledger   && npm install && npx hardhat test)   # the contract, unchanged
```

These tests run `init.sh` against `tests/fake_mc.py`, a model of `mc` and MinIO written from their documentation, and the policy checks use a small evaluator of the S3 policy rules. They show that the script's logic and the policies are right; they cannot show that the real `mc` and MinIO behave the same way. The check that does is the one `minio-init` makes against the real server on every start: read `docker compose logs minio-init`.

### In-process protocol checks

Two scripts under `tests/inprocess/` drive the real service code without containers or a chain. The ledger is the only stand-in: a dictionary that answers the question `isAccessActive` answers. They use real umbral-pre objects and real Ethereum signatures.

```bash
pip install fastapi httpx umbral-pre==0.11.0 web3==7.16.0 eth-account==0.13.7
python tests/inprocess/component_checks.py   # 20 checks: key-fragment intake, live ledger check, proof verification, quorum
python tests/inprocess/flow_checks.py        # 10 checks: owner client -> three proxy nodes -> provider client, end to end
```

`component_checks.py` covers the owner-authenticated fragment intake (wrong signer, wrong node, stale, altered after signing, malformed signature, older replay), a node's 403 before acknowledgement and after revocation, a tampered, wrong-capsule and all-zero capsule fragment, and fewer than two verified fragments. `flow_checks.py` runs the whole protocol through `owner/app/proxy_client.py` and `provider/app/proxy_client.py` against three instances of the proxy-node app, including one node down, two nodes down, a corrupted fragment, revocation, and a node restart that loses its in-memory fragment. They do not show that a node and the deployed contract interoperate; the Hardhat tests and a Compose run cover that.
