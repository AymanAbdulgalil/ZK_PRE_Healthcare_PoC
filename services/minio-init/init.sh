#!/bin/sh
# minio-init: one-shot set-up, run before the clients start. As MinIO root, creates
# the bucket and one user and policy per client, then checks access as each user.
# Safe to repeat. Any failure exits non-zero and the clients do not start.

set -eu

BUCKET=healthcare-records
ENDPOINT=${MINIO_ENDPOINT:-minio:9000}
POLICY_DIR=${POLICY_DIR:-/init/policies}

say()  { printf 'minio-init: %s\n' "$*"; }
fail() { printf 'minio-init: ERROR: %s\n' "$*" >&2; exit 1; }

# The mc image has no grep, sed or awk: shell built-ins only.
contains() { case $1 in *"$2"*) return 0 ;; esac; return 1; }   # TEXT WORD

# ------------------------------------------------------------ the inputs --
for name in MINIO_ROOT_USER MINIO_ROOT_PASSWORD \
            OWNER_MINIO_USER OWNER_MINIO_PASSWORD \
            PROVIDER_MINIO_USER PROVIDER_MINIO_PASSWORD; do
  eval "value=\${$name:-}"
  [ -n "$value" ] || fail "$name is not set (see .env.example)"
done

# These go into URLs and command lines, so only characters that need no quoting.
check_credential() {   # NAME VALUE MINIMUM-LENGTH
  case $2 in
    *[!A-Za-z0-9._~-]*) fail "$1 may only contain letters, digits and . _ ~ -" ;;
  esac
  [ "${#2}" -ge "$3" ] || fail "$1 must be at least $3 characters long"
}
check_credential OWNER_MINIO_USER "$OWNER_MINIO_USER" 3
check_credential OWNER_MINIO_PASSWORD "$OWNER_MINIO_PASSWORD" 8
check_credential PROVIDER_MINIO_USER "$PROVIDER_MINIO_USER" 3
check_credential PROVIDER_MINIO_PASSWORD "$PROVIDER_MINIO_PASSWORD" 8

[ "$OWNER_MINIO_USER" != "$PROVIDER_MINIO_USER" ] \
  || fail "OWNER_MINIO_USER and PROVIDER_MINIO_USER must be different users"
{ [ "$OWNER_MINIO_USER" != "$MINIO_ROOT_USER" ] && [ "$PROVIDER_MINIO_USER" != "$MINIO_ROOT_USER" ]; } \
  || fail "the client users must not be the MinIO root user"

for role in owner provider; do
  [ -f "$POLICY_DIR/$role.json" ] || fail "missing policy file $POLICY_DIR/$role.json"
done

# -------------------------------------------------- connect as the root user --
as_owner()    { MC_HOST_owner="http://${OWNER_MINIO_USER}:${OWNER_MINIO_PASSWORD}@${ENDPOINT}" mc "$@"; }
as_provider() { MC_HOST_provider="http://${PROVIDER_MINIO_USER}:${PROVIDER_MINIO_PASSWORD}@${ENDPOINT}" mc "$@"; }

# MinIO may pass its health check before it accepts logins, so retry.
ATTEMPTS=${MINIO_INIT_ATTEMPTS:-30}
PAUSE=${MINIO_INIT_PAUSE:-2}
tries=0
until answer=$(mc alias set local "http://$ENDPOINT" "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" 2>&1); do
  tries=$((tries + 1))
  [ "$tries" -lt "$ATTEMPTS" ] || fail "MinIO at $ENDPOINT did not accept the root credentials after $ATTEMPTS tries: $answer"
  sleep "$PAUSE"
done
say "connected to MinIO at $ENDPOINT"

# Test objects live under records/_selftest/ and are always removed.
cleanup() {
  mc rm --recursive --force "local/$BUCKET/records/_selftest/" >/dev/null 2>&1 || true
  mc rm --force "local/$BUCKET/outside-records" >/dev/null 2>&1 || true
  mc rb --force "local/zkpre-selftest-bucket" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# --------------------------------------------------------------- the set-up --
mc mb --ignore-existing "local/$BUCKET" >/dev/null || fail "could not create the bucket $BUCKET"
say "bucket $BUCKET is there"

for role in owner provider; do
  mc admin policy create local "zkpre-$role" "$POLICY_DIR/$role.json" >/dev/null \
    || fail "could not load the policy zkpre-$role"
done

mc admin user add local "$OWNER_MINIO_USER" "$OWNER_MINIO_PASSWORD" >/dev/null \
  || fail "could not create the owner (Patient) user"
mc admin user add local "$PROVIDER_MINIO_USER" "$PROVIDER_MINIO_PASSWORD" >/dev/null \
  || fail "could not create the provider (Health Care Provider) user"

# Re-attaching errors on some versions, so check the end state, not the exit status.
attach() {   # POLICY USER
  said=$(mc admin policy attach local "$1" --user "$2" 2>&1) || true
  info=$(mc admin user info local "$2" 2>/dev/null) || info=
  while IFS= read -r line; do
    case $line in *[Pp][Oo][Ll][Ii][Cc][Yy]*"$1"*) return 0 ;; esac
  done <<EOF
$info
EOF
  fail "policy $1 is not attached to user $2 (mc said: $said)"
}
attach zkpre-owner "$OWNER_MINIO_USER"
attach zkpre-provider "$PROVIDER_MINIO_USER"
say "users created, one policy each"

# -------------------------------------------- check what the policies allow --
# Refusals are judged by the bucket's contents afterwards, not just the exit status.
# Missing client abilities only WARN: the clients report those errors themselves.
PROBE="$BUCKET/records/_selftest/probe"
printf probe | mc pipe "local/$PROBE" >/dev/null || fail "self-test: could not write a test object"

# Health Care Provider: may read, must not write, delete or create buckets.
[ "$(as_provider cat "provider/$PROBE" 2>/dev/null)" = probe ] \
  && say "ok: the provider can read a stored record" \
  || say "WARNING: the provider could not read a stored record"
printf tampered | as_provider pipe "provider/$PROBE" >/dev/null 2>&1 || true
as_provider rm "provider/$PROBE" >/dev/null 2>&1 || true
as_provider mb "provider/zkpre-selftest-bucket" >/dev/null 2>&1 || true
[ "$(mc cat "local/$PROBE" 2>/dev/null)" = probe ] \
  || fail "self-test FAILED: the provider changed or removed a stored object"
if mc stat "local/zkpre-selftest-bucket" >/dev/null 2>&1; then
  fail "self-test FAILED: the provider created a bucket"
fi
say "ok: the provider cannot overwrite, delete or create anything"

# Patient: may store, list and erase; must not read back, write outside records/ or
# create buckets. Erase uses `rm --recursive`: plain `mc rm` stats first, needing read.
if printf record | as_owner pipe "owner/$BUCKET/records/_selftest/stored" >/dev/null 2>&1 \
   && contains "$(as_owner ls "owner/$BUCKET/records/_selftest/" 2>/dev/null)" stored \
   && as_owner rm --recursive --force "owner/$BUCKET/records/_selftest/stored" >/dev/null 2>&1 \
   && ! mc stat "local/$BUCKET/records/_selftest/stored" >/dev/null 2>&1; then
  say "ok: the patient can store, list and erase records"
else
  say "WARNING: the patient could not store, list and erase a test record"
fi
printf outside | as_owner pipe "owner/$BUCKET/outside-records" >/dev/null 2>&1 || true
as_owner mb "owner/zkpre-selftest-bucket" >/dev/null 2>&1 || true
if mc stat "local/$BUCKET/outside-records" >/dev/null 2>&1; then
  fail "self-test FAILED: the patient wrote outside records/"
fi
if mc stat "local/zkpre-selftest-bucket" >/dev/null 2>&1; then
  fail "self-test FAILED: the patient created a bucket"
fi
if contains "$(as_owner cat "owner/$PROBE" 2>/dev/null)" probe; then
  fail "self-test FAILED: the patient can read stored objects back"
fi
say "ok: the patient cannot write outside records/, read objects back or create buckets"

say "done"
