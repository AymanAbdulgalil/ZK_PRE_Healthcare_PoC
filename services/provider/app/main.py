# IMAGE: provider  (Streamlit GUI -- health care provider client)
# Names say "provider" and "owner" (the paper's terms); the UI says "Health Care Provider" and "Patient".
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import crypto_ops
import identity as identity_mod
import labels
import proxy_client
import storage
import streamlit as st
import trusted_owners
from config import settings
from ledger_client import LedgerClient
from ui import copy_block, short_address

st.set_page_config(page_title="Health Care Provider", page_icon=":stethoscope:", layout="wide")


@st.cache_resource
def get_identity() -> identity_mod.ProviderIdentity:
    return identity_mod.load_identity()


@st.cache_resource
def get_ledger() -> LedgerClient:
    ident = get_identity()
    return LedgerClient(ident.eth_account, settings.LEDGER_RPC_URL, settings.LEDGER_DEPLOYMENT_FILE)


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


def access_record(owner: str, record_hash: str, owner_keys: dict) -> bytes | None:
    """Paper §5.3 steps 5-8. Returns the plaintext, or None if access failed (reason already shown)."""
    delegating_pk = trusted_owners.parse_pk(owner_keys["delegating_pk"])
    verifying_pk = trusted_owners.parse_pk(owner_keys["verifying_pk"])

    with st.status("Accessing record...", expanded=True) as status:
        # Storage is untrusted: check the content-addressed record is the one asked for.
        try:
            capsule, ciphertext = storage.get_record(record_hash)
        except storage.RecordNotFound:
            status.update(label="The record is no longer in storage", state="error")
            st.error(
                "This record is no longer in storage. The patient may have deleted it, "
                "in which case it cannot be opened any more."
            )
            return None
        except Exception as exc:
            status.update(label="Couldn't fetch the record", state="error")
            st.error(str(exc))
            return None
        if not crypto_ops.matches_content_address(ciphertext, record_hash):
            status.update(label="Stored ciphertext doesn't match its content address", state="error")
            st.error(
                "The ciphertext served by object storage does not hash to the record's "
                "identifier, so it is not the record the patient uploaded. Not using it."
            )
            return None
        status.write("ciphertext matches its content address")

        # Step 5: ask every proxy; each checks the ledger itself.
        received = []
        for i, endpoint in enumerate(settings.PRE_PROXY_ENDPOINTS):
            cfrag_hex, err = proxy_client.request_cfrag(
                endpoint, owner, ident.eth_account.address, record_hash, capsule.hex()
            )
            if cfrag_hex:
                received.append((endpoint, cfrag_hex))
                status.write(f"proxy {i} ({endpoint}): fragment received")
            else:
                status.write(f"proxy {i} ({endpoint}): refused -- {err or 'no fragment available'}")

        # Step 7: verify each fragment alone; a bad one is discarded and its sender flagged.
        verified, rejected = crypto_ops.verify_cfrags(
            capsule, received, verifying_pk, delegating_pk, ident.receiving_pk
        )
        for source, _ in verified:
            status.write(f"{source}: correctness proof verified")
        for source, reason in rejected:
            status.write(
                f":red[{source}: fragment REJECTED -- proof check failed ({reason}). "
                "Treated as byzantine for this request.]"
            )

        if len(verified) < settings.PRE_THRESHOLD:
            status.update(label="Not enough verified re-encryption fragments", state="error")
            st.warning(
                f"Got {len(verified)} verified fragment(s); {settings.PRE_THRESHOLD} are "
                "required. The proxy nodes may be down, may have refused (grant not "
                "active), or may never have received this grant's key fragments."
            )
            return None

        # Step 8: combine and decrypt, locally.
        try:
            plaintext = crypto_ops.decrypt_with_verified(
                ident.receiving_sk, delegating_pk, capsule, verified, ciphertext,
                settings.PRE_THRESHOLD,
            )
        except Exception as exc:
            status.update(label="Decryption failed", state="error")
            st.error(str(exc))
            return None
        status.update(label="Record decrypted", state="complete")
        return plaintext


def owner_name(address: str, trusted: dict) -> str:
    label = (trusted.get(address) or {}).get("label")
    return f"{label} ({short_address(address)})" if label else short_address(address)


LABEL_HELP = (
    "A label is your own note, so you can tell records apart. It stays on this device, "
    "in this container's private volume. It is never uploaded to storage, to the proxy "
    "nodes or to the ledger, and the patient cannot see it. It is not encrypted, so "
    "keep sensitive detail out of it."
)

st.title("Health Care Provider — Requesting Access")

if "flash" in st.session_state:
    flash_kind, flash_message = st.session_state.pop("flash")
    getattr(st, flash_kind)(flash_message)

with st.sidebar:
    st.subheader("Your identity")
    copy_block([
        ("Ethereum address", ident.eth_account.address),
        ("Umbral encryption public key", ident.receiving_pk.to_compressed_bytes().hex()),
    ], mask=True)
    st.caption(
        "Give both of these to a patient, out of band, before they grant you access. They are "
        "hidden on purpose: use the Copy buttons, which copy each value exactly."
    )

tab_grants, tab_owners = st.tabs(["Grants naming you", "Trusted patients"])

# ----------------------------------------------------------- trusted patients --
# Before the grants tab, so a patient added here is trusted on this same run.
with tab_owners:
    st.subheader("Trusted patients")
    st.caption(
        "Patients whose identity you exchanged out of band. A grant from an address that isn't "
        "on this list can't be acknowledged or used: the patient's public keys are needed to "
        "check what the proxy nodes send back, and object storage never carries keys. "
        "Addresses and keys are hidden; use Copy."
    )

    with st.form("add-trusted-owner", clear_on_submit=True):
        new_label = st.text_input("Name (optional)", placeholder="e.g. Jane Doe")
        new_address = st.text_input("Patient's Ethereum address (0x...)")
        new_delegating_pk = st.text_input("Patient's Umbral encryption public key (hex)")
        new_verifying_pk = st.text_input("Patient's Umbral verifying public key (hex)")
        add_clicked = st.form_submit_button("Add trusted patient")
    if add_clicked:
        try:
            added, keys_changed = trusted_owners.add(
                new_address, new_delegating_pk, new_verifying_pk, new_label
            )
        except Exception as exc:
            st.error(f"Couldn't add that patient: {exc}")
        else:
            if keys_changed:
                st.warning(
                    f"{short_address(added)} was already on your list under different public keys, and the "
                    "keys have been REPLACED. Make sure you verified the new ones out of band."
                )
            else:
                st.success(
                    f"Added {short_address(added)}" + (f" as {new_label.strip()}" if new_label.strip() else "") + "."
                )

    trusted = trusted_owners.load()
    st.markdown(f"**Your trusted patients ({len(trusted)})**")
    if not trusted:
        st.info(
            "No trusted patients yet. Ask a patient for the three values in their sidebar "
            "(Ethereum address and the two Umbral public keys) and add them above."
        )
    for address, entry in trusted.items():
        with st.container(border=True):
            title_col, action_col = st.columns([6, 1])
            title_col.markdown(f"**{entry.get('label') or 'Unnamed patient'}**  ·  `{short_address(address)}`")
            if action_col.button("Remove", key=f"rm-owner-{address}"):
                trusted_owners.remove(address)
                st.rerun()
            copy_block([
                ("Ethereum address", address),
                ("Umbral encryption public key", entry["delegating_pk"]),
                ("Umbral verifying public key", entry["verifying_pk"]),
            ], mask=True)

# -------------------------------------------------------------------- grants --
with tab_grants:
    st.subheader("Grants naming you")
    if st.button("Refresh"):
        st.rerun()

    grants = ledger.my_grants()
    trusted = trusted_owners.load()
    label_map = labels.load()
    if not grants:
        st.info("No grants issued to you yet. Ask a patient to grant access using your identity in the sidebar.")

    for g in sorted(grants, key=lambda x: x["grant_id"], reverse=True):
        owner = g["owner"]
        record_hash = g["record_hash"]
        if g["revoked_at"]:
            state = "revoked"
        elif g["acknowledged"]:
            state = "active"
        else:
            state = "awaiting your acknowledgement"

        current_label = label_map.get(record_hash.lower(), "")
        with st.expander(
            f"From {owner_name(owner, trusted)} — {labels.display(record_hash, label_map, head=14)} — {state}",
            expanded=st.session_state.get("open_grant") == g["grant_id"],
        ):
            copy_block(
                [("Patient's Ethereum address", owner), ("Record hash", record_hash)], compact=True
            )

            # This provider's own note, kept on this device only.
            with st.form(f"label-form-{g['grant_id']}-{current_label}", border=False):
                field_col, save_col = st.columns([5, 1])
                new_label = field_col.text_input(
                    "Label (stays on this device)",
                    value=current_label,
                    max_chars=labels.MAX_LENGTH,
                    placeholder="Label (stays on this device)",
                    label_visibility="collapsed",
                    key=f"label-{g['grant_id']}-{current_label}",
                    help=LABEL_HELP,
                )
                saved = save_col.form_submit_button("Save label")
            if saved:
                stored_label = labels.set_label(record_hash, new_label)
                st.session_state["open_grant"] = g["grant_id"]
                st.session_state["flash"] = (
                    "success", "Label saved on this device." if stored_label else "Label cleared."
                )
                st.rerun()

            if g["revoked_at"]:
                st.error("This grant has been revoked by the patient.")
                continue

            owner_keys = trusted.get(owner)
            if owner_keys is None:
                st.warning(
                    "This patient isn't on your trusted list. Exchange identities with them "
                    "out of band and add them on the Trusted patients tab before acting on this grant."
                )
                continue

            if not g["acknowledged"]:
                st.info(
                    "The patient has granted you access to this record. Acknowledging it records, "
                    "on-chain and under your own signature, that you accepted. The proxy nodes "
                    "will not re-encrypt anything for you until you do."
                )
                if st.button("Acknowledge grant", key=f"ack-{g['grant_id']}", type="primary"):
                    try:
                        tx_hash = ledger.acknowledge_grant(owner, record_hash)
                    except Exception as exc:
                        st.error(f"Acknowledgement failed: {exc}")
                    else:
                        st.session_state["flash"] = (
                            "success", f"Grant acknowledged on-chain (tx {tx_hash})."
                        )
                        st.rerun()
                continue

            if not st.button("Access record", key=f"access-{g['grant_id']}", type="primary"):
                continue

            plaintext = access_record(owner, record_hash, owner_keys)
            if plaintext is not None:
                st.success("Access granted and record decrypted.")
                st.text_area(
                    "Decrypted record", plaintext.decode("utf-8", errors="replace"), height=200,
                    key=f"plaintext-{g['grant_id']}",
                )
