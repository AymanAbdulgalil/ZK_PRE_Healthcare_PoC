# IMAGE: owner  (Streamlit GUI -- patient / data owner client)
# Names say "owner" (the paper's term); the UI says "Patient" and "Health Care Provider".
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import crypto_ops
import identity as identity_mod
import labels
import proxy_client
import records
import storage
import streamlit as st
import trusted_providers
import umbral_pre
from config import settings
from ledger_client import LedgerClient
from ui import copy_block, short_address
from web3 import Web3

st.set_page_config(page_title="Patient", page_icon=":file_cabinet:", layout="wide")


@st.cache_resource
def get_identity() -> identity_mod.OwnerIdentity:
    return identity_mod.load_identity()


@st.cache_resource
def get_ledger() -> LedgerClient:
    ident = get_identity()
    return LedgerClient(
        ident.eth_account, settings.LEDGER_RPC_URL, settings.LEDGER_DEPLOYMENT_FILE
    )


@st.cache_resource
def check_storage() -> bool:
    storage.check_bucket()
    return True


try:
    check_storage()
except storage.StorageNotReady as exc:
    st.error(str(exc))
    st.stop()
ident = get_identity()
ledger = get_ledger()


def grant_access_flow(record_hash: str, provider_address: str, provider_pk_hex: str) -> None:
    """Paper §5.3 steps 2-3: send kfrags to the proxies, then anchor the grant on-chain."""
    provider_pk_hex = provider_pk_hex.strip()
    try:
        receiving_pk = umbral_pre.PublicKey.from_compressed_bytes(bytes.fromhex(provider_pk_hex))
    except Exception as exc:
        st.error(f"Couldn't parse the health care provider's Umbral public key: {exc}")
        return

    try:
        # Checksummed once: also a case-sensitive key component in MinIO and the proxy store.
        provider_address = Web3.to_checksum_address(provider_address.strip())
    except ValueError:
        st.error("That doesn't look like a valid Ethereum address.")
        return

    endpoints = settings.PRE_PROXY_ENDPOINTS
    if len(endpoints) != settings.PRE_SHARES:
        st.error(
            f"Misconfigured: PRE_PROXY_ENDPOINTS lists {len(endpoints)} node(s) but "
            f"PRE_SHARES is {settings.PRE_SHARES}."
        )
        return

    # The contract refuses a second live grant. Check first, so a refused grant can't
    # replace the live grant's fragments on the proxies.
    for g in ledger.my_grants():
        if (
            g["provider"] == provider_address
            and g["record_hash"] == record_hash
            and not g["revoked_at"]
        ):
            st.error(
                "A live grant for this health care provider and record already exists. "
                "Revoke it first if you want to issue a fresh one."
            )
            return

    delegating_pk_hex = ident.delegating_pk.to_compressed_bytes().hex()
    verifying_pk_hex = ident.verifying_pk.to_compressed_bytes().hex()

    with st.status("Granting access...", expanded=True) as status:
        # 1. Split the key and give each node a fragment, signed with the patient's Ethereum key.
        kfrags = crypto_ops.generate_kfrags(
            ident.delegating_sk,
            receiving_pk,
            ident.signer,
            settings.PRE_THRESHOLD,
            settings.PRE_SHARES,
        )
        delivered = 0
        for i, endpoint in enumerate(endpoints):
            ok, err = proxy_client.submit_kfrag(
                endpoint,
                ident.eth_account,
                provider=provider_address,
                record_hash=record_hash,
                kfrag=kfrags[i],
                delegating_pk_hex=delegating_pk_hex,
                receiving_pk_hex=provider_pk_hex,
                verifying_pk_hex=verifying_pk_hex,
            )
            delivered += ok
            status.write(
                f"proxy {i} ({endpoint}): "
                + ("delivered" if ok else f"not delivered -- {err}")
            )

        # Below threshold the grant is unusable, and the contract would refuse a re-grant as a duplicate.
        if delivered < settings.PRE_THRESHOLD:
            status.update(label="Not enough proxy nodes accepted a key fragment", state="error")
            st.error(
                f"Only {delivered} of {settings.PRE_THRESHOLD} required proxy nodes accepted "
                "their fragment, so nothing was recorded on-chain. Check that the pre-proxy "
                "nodes are up, then try again."
            )
            return

        # 2. Anchor the grant: the signed transaction is the authorisation.
        try:
            tx_hash = ledger.grant_access(provider_address, record_hash)
        except Exception as exc:
            status.update(label="Ledger transaction failed", state="error")
            st.error(str(exc))
            return
        status.write(f"grant recorded on-chain: tx {tx_hash}")
        status.update(label="Grant recorded -- waiting for the health care provider", state="complete")

    if delivered < len(endpoints):
        st.warning(
            f"Grant recorded, but only {delivered} of {len(endpoints)} proxy nodes hold a "
            "fragment. It will work while those nodes stay up; re-issue the grant "
            "(revoke, then grant again) to reach the rest."
        )
    st.success(
        "Grant recorded on-chain. It becomes usable once the health care provider "
        "acknowledges it from their side."
    )


def provider_name(address: str, trusted: dict) -> str:
    label = (trusted.get(address) or {}).get("label")
    return f"{label} ({short_address(address)})" if label else short_address(address)


def fmt_size(n) -> str:
    if n is None:
        return "unknown size"
    if n < 1024:
        return f"{n} bytes"
    size = float(n)
    for unit in ("KiB", "MiB", "GiB"):
        size /= 1024
        if size < 1024 or unit == "GiB":
            return f"{size:.1f} {unit}"


LABEL_HELP = (
    "A label is your own note, so you can tell records apart. It stays on this device, "
    "in this container's private volume. It is never uploaded to storage, to the proxy "
    "nodes or to the ledger, and the health care provider cannot see it. It is not "
    "encrypted, so keep sensitive detail out of it."
)

st.title("Patient (Data Owner)")

if "flash" in st.session_state:
    flash_kind, flash_message = st.session_state.pop("flash")
    getattr(st, flash_kind)(flash_message)

with st.sidebar:
    st.subheader("Your identity")
    copy_block([
        ("Ethereum address (signs ledger transactions)", ident.eth_account.address),
        ("Umbral encryption public key", ident.delegating_pk.to_compressed_bytes().hex()),
        ("Umbral verifying (signing) public key", ident.verifying_pk.to_compressed_bytes().hex()),
    ], mask=True)
    st.caption(
        "Share these three values with a health care provider, out of band, before granting "
        "them access -- they add them to their trusted-patients list. Object "
        "storage never carries keys, so this is the only way a health care provider learns them. "
        "They are hidden on purpose: use the Copy buttons, which copy each value exactly."
    )

tab_upload, tab_records, tab_providers, tab_grant, tab_grants = st.tabs(
    ["Upload record", "My records", "Trusted health care providers", "Grant access", "My grants"]
)

# --------------------------------------------------------------- upload --
with tab_upload:
    st.subheader("Encrypt & store a health record")
    st.caption(
        "Encrypted locally with your own Umbral key before it ever leaves this container."
    )

    record_text = st.text_area(
        "Record contents (plaintext, for the demo -- paste JSON, notes, whatever)",
        height=200,
        placeholder='{"patient": "Jane Doe", "diagnosis": "..."}',
    )
    upload_label = st.text_input(
        "Label (optional, stays on this device)",
        max_chars=labels.MAX_LENGTH,
        placeholder="e.g. Blood test, March",
        help=LABEL_HELP,
    )

    if st.button("Encrypt & upload", type="primary"):
        plaintext = record_text.encode("utf-8")
        capsule, ciphertext = crypto_ops.encrypt_record(ident.delegating_pk, plaintext)
        record_hash = crypto_ops.record_hash_from_ciphertext(ciphertext)
        storage.put_record(record_hash, capsule, ciphertext)
        if upload_label.strip():
            labels.set_label(record_hash, upload_label)          # local file only
        st.success("Encrypted and stored." + (" Label saved on this device." if upload_label.strip() else ""))
        copy_block([("Record hash", record_hash)])
        st.session_state["last_record_hash"] = record_hash

# ------------------------------------------------------------- my records --
with tab_records:
    st.subheader("Your stored records")
    st.caption(
        "What object storage holds for you: ciphertext and capsules only. Give a record a label "
        "to recognise it. " + LABEL_HELP
    )
    if st.button("Refresh", key="refresh-records"):
        st.rerun()

    stored = storage.list_records()
    all_grants = ledger.my_grants()
    label_map = labels.load()

    if not stored:
        st.info("No records stored yet. Upload one on the first tab.")

    for rec in stored:
        h = rec["hash"]
        live = records.live_grants(all_grants, h)
        issued = sum(1 for g in all_grants if g["record_hash"].lower() == h)
        current = label_map.get(h, "")

        with st.container(border=True):
            st.markdown(f"**{current or 'Unlabelled record'}**")
            copy_block([("Record hash", h)], compact=True)
            st.caption(
                f"{fmt_size(rec['size'])} encrypted · stored {rec['last_modified']:%Y-%m-%d %H:%M} UTC · "
                f"{len(live)} live grant(s), {issued} issued in total"
            )

            with st.form(f"label-form-{h}-{current}", border=False):
                field_col, save_col = st.columns([5, 1])
                new_label = field_col.text_input(
                    "Label (stays on this device)",
                    value=current,
                    max_chars=labels.MAX_LENGTH,
                    placeholder="Label (stays on this device)",
                    label_visibility="collapsed",
                    key=f"label-{h}-{current}",
                )
                saved = save_col.form_submit_button("Save label")
            if saved:
                stored_label = labels.set_label(h, new_label)
                st.session_state["flash"] = (
                    "success", "Label saved on this device." if stored_label else "Label cleared."
                )
                st.rerun()

            if st.session_state.get("confirm_delete") == h:
                st.warning(
                    f"**Delete this record?** This revokes {len(live)} live grant(s) on-chain, then "
                    "permanently erases the encrypted record from storage and removes its label from "
                    "this device. It cannot be undone. The ledger keeps its history of the grants and "
                    "revocations. Key fragments held by the proxy nodes become useless and disappear "
                    "when those nodes restart. Anything a health care provider has already decrypted "
                    "stays with them."
                )
                yes_col, no_col, _ = st.columns([2, 1, 4])
                if no_col.button("Cancel", key=f"cancel-delete-{h}"):
                    st.session_state.pop("confirm_delete", None)
                    st.rerun()
                if yes_col.button("Yes, delete permanently", key=f"confirm-delete-{h}", type="primary"):
                    outcome = None
                    with st.status("Deleting record...", expanded=True) as status:
                        try:
                            outcome = records.delete_record(
                                h, ledger, storage, labels, on_step=status.write
                            )
                        except records.DeleteError as exc:
                            status.update(label="Delete stopped", state="error")
                            st.error(str(exc))
                        else:
                            status.update(label="Record deleted", state="complete")
                    if outcome is not None:
                        st.session_state.pop("confirm_delete", None)
                        if st.session_state.get("last_record_hash") == h:
                            st.session_state.pop("last_record_hash")
                        st.session_state["flash"] = (
                            "success",
                            f"Record deleted: {outcome['revoked']} live grant(s) revoked and "
                            f"{outcome['objects']} stored object(s) erased. The ledger keeps its history.",
                        )
                        st.rerun()
            elif st.button("Delete record…", key=f"delete-{h}"):
                st.session_state["confirm_delete"] = h
                st.rerun()

# ------------------------------------------------ trusted health care providers --
with tab_providers:
    st.subheader("Trusted health care providers")
    st.caption(
        "Health care providers whose identity you verified out of band. You can only grant access to "
        "someone on this list. Removing one here does not revoke grants you already "
        "issued -- do that under My grants. Addresses and keys are hidden; use Copy."
    )

    with st.form("add-trusted-provider", clear_on_submit=True):
        new_label = st.text_input("Name (optional)", placeholder="e.g. Dr. Rao, City Hospital")
        new_address = st.text_input("Health care provider's Ethereum address (0x...)")
        new_pk = st.text_input("Health care provider's Umbral encryption public key (hex)")
        add_clicked = st.form_submit_button("Add trusted health care provider")
    if add_clicked:
        try:
            added, key_changed = trusted_providers.add(new_address, new_pk, new_label)
        except Exception as exc:
            st.error(f"Couldn't add that health care provider: {exc}")
        else:
            if key_changed:
                st.warning(
                    f"{short_address(added)} was already on your list under a different public key, and the "
                    "key has been REPLACED. Make sure you verified the new one out of band."
                )
            else:
                st.success(
                    f"Added {short_address(added)}" + (f" as {new_label.strip()}" if new_label.strip() else "") + "."
                )

    trusted = trusted_providers.load()
    st.markdown(f"**Your trusted health care providers ({len(trusted)})**")
    if not trusted:
        st.info(
            "No trusted health care providers yet. Ask one for the two values in their sidebar "
            "(Ethereum address and Umbral encryption public key) and add them above."
        )
    for address, entry in trusted.items():
        with st.container(border=True):
            title_col, action_col = st.columns([6, 1])
            title_col.markdown(
                f"**{entry.get('label') or 'Unnamed health care provider'}**  ·  `{short_address(address)}`"
            )
            if action_col.button("Remove", key=f"rm-provider-{address}"):
                trusted_providers.remove(address)
                st.rerun()
            copy_block([
                ("Ethereum address", address),
                ("Umbral encryption public key", entry["encryption_pk"]),
            ], mask=True)

# ---------------------------------------------------------------- grant --
with tab_grant:
    st.subheader("Grant a health care provider access")

    record_hashes = storage.list_record_hashes()
    trusted = trusted_providers.load()
    label_map = labels.load()
    if not record_hashes:
        st.info("Upload a record first, on the first tab.")
    elif not trusted:
        st.info("Add the health care provider to your trusted list first, on the third tab.")
    else:
        last_uploaded = st.session_state.get("last_record_hash")
        default_index = (
            record_hashes.index(last_uploaded) if last_uploaded in record_hashes else 0
        )
        record_hash = st.selectbox(
            "Record",
            record_hashes,
            index=default_index,
            format_func=lambda h: labels.display(h, label_map),
        )
        if last_uploaded and record_hash != last_uploaded:
            st.caption("Note: this isn't the record you most recently uploaded.")
        provider_address = st.selectbox(
            "Health care provider",
            list(trusted),
            format_func=lambda a: provider_name(a, trusted),
        )
        provider_pk_hex = trusted[provider_address]["encryption_pk"]
        copy_block(
            [("Health care provider's Umbral encryption public key", provider_pk_hex)], mask=True
        )

        st.caption(
            f"Threshold scheme: {settings.PRE_THRESHOLD} of {settings.PRE_SHARES} "
            "proxy nodes must cooperate to re-encrypt for the health care provider."
        )

        if st.button("Grant access", type="primary"):
            grant_access_flow(record_hash, provider_address, provider_pk_hex)

# --------------------------------------------------------------- grants --
with tab_grants:
    st.subheader("Grants you've issued")

    if st.button("Refresh"):
        st.rerun()

    grants = ledger.my_grants()
    trusted = trusted_providers.load()
    label_map = labels.load()
    if not grants:
        st.info("No grants issued yet.")

    for g in sorted(grants, key=lambda x: x["grant_id"], reverse=True):
        cols = st.columns([4, 3, 3, 2])
        with cols[0]:
            name = (trusted.get(g["provider"]) or {}).get("label")
            if name:
                st.markdown(f"**{name}**")
            copy_block([("", g["provider"])], compact=True)
        with cols[1]:
            record_label = label_map.get(g["record_hash"].lower())
            if record_label:
                st.markdown(f"**{record_label}**")
            copy_block([("", g["record_hash"])], compact=True)
        if g["revoked_at"]:
            cols[2].write("revoked")
        elif g["acknowledged"]:
            cols[2].write("active")
        else:
            cols[2].write("awaiting health care provider acknowledgement")
        if not g["revoked_at"]:
            if cols[3].button("Revoke", key=f"revoke-{g['grant_id']}"):
                try:
                    ledger.revoke_access(g["provider"], g["record_hash"])
                except Exception as exc:
                    st.error(f"Revocation failed: {exc}")
                else:
                    st.rerun()
