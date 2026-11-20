"""S3 client for MinIO, provider's side: reads capsule and ciphertext under
records/<record_hash>/; no keys or labels there. This user may only list and read
(policies/provider.json); listing lets a missing record report as missing, not denied."""

import re

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from config import settings

BUCKET = "healthcare-records"

_HASH = re.compile(r"^0x[0-9a-f]{64}$")


class RecordNotFound(Exception):
    """The record is not in storage -- typically because the patient deleted it."""


def _client():
    return boto3.client(
        "s3",
        endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
        aws_access_key_id=settings.MINIO_ACCESS_KEY,
        aws_secret_access_key=settings.MINIO_SECRET_KEY,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


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


def _get(key: str) -> bytes:
    s3 = _client()
    try:
        return s3.get_object(Bucket=BUCKET, Key=key)["Body"].read()
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            raise RecordNotFound(key) from exc
        raise


def get_record(record_hash: str):
    """Returns (capsule, ciphertext). Raises RecordNotFound if either object
    is missing, ValueError for a malformed hash."""
    if not isinstance(record_hash, str) or not _HASH.match(record_hash):
        raise ValueError("a record hash is 0x followed by 64 lowercase hexadecimal digits")
    prefix = f"records/{record_hash}"
    return _get(f"{prefix}/capsule.bin"), _get(f"{prefix}/ciphertext.bin")
