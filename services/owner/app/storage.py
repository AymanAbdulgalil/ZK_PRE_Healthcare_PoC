# IMAGE: owner  (Streamlit GUI -- patient / data owner client)
#
"""S3 client for MinIO. Holds only capsule and ciphertext, under records/<record_hash>/;
never keys or labels. The patient's user may list, and write and erase under records/
(policies/owner.json)."""

import re

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from config import settings

BUCKET = "healthcare-records"

_HASH = re.compile(r"^0x[0-9a-f]{64}$")


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def _check_hash(record_hash: str) -> str:
    """Refuses anything but 0x + 64 lowercase hex, so a short value can't widen a delete."""
    if not isinstance(record_hash, str) or not _HASH.match(record_hash):
        raise ValueError("a record hash is 0x followed by 64 lowercase hexadecimal digits")
    return record_hash


class StorageNotReady(RuntimeError):
    """The bucket cannot be used; the message says why, in plain words."""


def check_bucket() -> None:
    """Confirms the bucket is visible. minio-init creates it; this user cannot."""
    s3 = _client()
    try:
        s3.head_bucket(Bucket=BUCKET)
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in ("404", "NoSuchBucket", "NotFound"):
            raise StorageNotReady(
                f"The storage bucket '{BUCKET}' does not exist. It is created by the minio-init "
                "service; run `docker compose up` again and check `docker compose logs minio-init`."
            ) from exc
        if code in ("403", "AccessDenied", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
            raise StorageNotReady(
                "Object storage refused this client's credentials. Check the MinIO user and "
                "password in .env, and `docker compose logs minio-init`."
            ) from exc
        raise StorageNotReady(f"Object storage returned an error ({code or exc}).") from exc
    except BotoCoreError as exc:
        raise StorageNotReady(f"Can't reach object storage: {exc}") from exc


def put_record(record_hash: str, capsule: bytes, ciphertext: bytes):
    _check_hash(record_hash)
    s3 = _client()
    s3.put_object(Bucket=BUCKET, Key=f"records/{record_hash}/capsule.bin", Body=capsule)
    s3.put_object(Bucket=BUCKET, Key=f"records/{record_hash}/ciphertext.bin", Body=ciphertext)


def list_records() -> list[dict]:
    """Every stored record: {"hash", "size" (ciphertext bytes, or None if the
    ciphertext object is missing), "last_modified" (datetime)}, newest first."""
    s3 = _client()
    paginator = s3.get_paginator("list_objects_v2")
    found: dict = {}
    for page in paginator.paginate(Bucket=BUCKET, Prefix="records/"):
        for obj in page.get("Contents", []):
            parts = obj["Key"].split("/")
            if len(parts) != 3 or not _HASH.match(parts[1]):
                continue
            entry = found.setdefault(
                parts[1], {"hash": parts[1], "size": None, "last_modified": obj["LastModified"]}
            )
            if obj["LastModified"] > entry["last_modified"]:
                entry["last_modified"] = obj["LastModified"]
            if parts[2] == "ciphertext.bin":
                entry["size"] = obj["Size"]
    return sorted(found.values(), key=lambda e: e["last_modified"], reverse=True)


def list_record_hashes():
    return sorted(r["hash"] for r in list_records())


def delete_record(record_hash: str) -> int:
    """Erases a record's objects and checks none remain. Returns the count (0 if none), so
    repeating is safe. Raises RuntimeError on an error or leftovers."""
    _check_hash(record_hash)
    s3 = _client()
    prefix = f"records/{record_hash}/"

    def keys_under_prefix() -> list[str]:
        out: list[str] = []
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=prefix):
            out.extend(o["Key"] for o in page.get("Contents", []))
        return out

    keys = keys_under_prefix()
    if not keys:
        return 0
    resp = s3.delete_objects(
        Bucket=BUCKET, Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True}
    )
    errors = resp.get("Errors") or []
    if errors:
        first = errors[0]
        raise RuntimeError(
            f"storage refused to delete {len(errors)} object(s): "
            f"{first.get('Key')}: {first.get('Code')} {first.get('Message', '')}".strip()
        )
    if keys_under_prefix():
        raise RuntimeError("objects are still present after the delete request")
    return len(keys)
