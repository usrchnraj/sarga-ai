# app.py
import os
import json
import datetime as dt
import streamlit as st
from audio_recorder_streamlit import audio_recorder

from utils import (
    fetch_today_appointments,
    call_n8n_first_webhook,
    call_n8n_second_webhook,  # compat: accepts letter_id OR full patient context
)

st.set_page_config(page_title="Appointments", layout="wide")

def _sec(k: str):
    try:
        return os.getenv(k) or st.secrets.get(k)
    except Exception:
        return None

def _has_secret(k: str) -> bool:
    return bool(_sec(k))

def _fmt_apt(r: dict) -> str:
    try:
        t = dt.datetime.fromisoformat(str(r["start_time"]))
        hhmm = t.strftime("%H:%M")
    except Exception:
        hhmm = "—"
    return f"{r['patient_name']} • {r['reason']} • {hhmm}"

st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; }
      .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; background:#eef2ff; color:#4338ca; }
      .muted { color:#64748b; font-size:13px; }
      .card { border-radius:16px; padding:16px; background:var(--background-color); box-shadow:0 1px 3px rgba(16,24,40,.08); }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Appointments")

# session
if "appointments" not in st.session_state:
    st.session_state["appointments"] = []
if "consultation_id" not in st.session_state:
    st.session_state["consultation_id"] = None
if "transcript" not in st.session_state:
    st.session_state["transcript"] = ""
if "letter_draft" not in st.session_state:
    st.session_state["letter_draft"] = ""

colL, colR = st.columns([1.25, 1])

with colL:
    st.subheader("Today's List")

    if st.button("🔄 Refresh appointments", use_container_width=True, key="refresh_btn"):
        try:
            st.session_state["appointments"] = fetch_today_appointments()
            st.success(f"Loaded {len(st.session_state['appointments'])} appointments.")
        except Exception as e:
            st.error(f"Failed to load appointments: {e}")

    apts = st.session_state["appointments"]
    if not apts:
        st.info("No data loaded. Click **Refresh appointments** to fetch from Neon.")
        st.stop()

    selected = st.radio(
        "Select a patient",
        apts,
        format_func=_fmt_apt,
        index=0,
        key="patient_radio",
    )

with colR:
    st.subheader("Actions")
    st.caption("1) Record → 2) Get Draft → 3) Edit → 4) Approve & Send")

    st.write("### Voice Notes")
    st.caption("Click the mic, speak, click again to stop.")
    audio_bytes = audio_recorder(text="", pause_threshold=2.0)

    if audio_bytes:
        st.audio(audio_bytes, format="audio/wav")

    disabled_first = not (audio_bytes and _has_secret("N8N_WEBHOOK_1"))
    if st.button(
        "Generate Draft from Recording",
        type="primary",
        use_container_width=True,
        disabled=disabled_first,
        key="gen_draft_btn",
    ):
        try:
            ctx = {
                "patient_id": selected["patient_id"],
                "patient_name": selected["patient_name"],
                "patient_email": selected["patient_email"],
                "patient_phone": selected["patient_phone"],
                "appointment_id": selected["appointment_id"],
                "doctor_id": "dr-001",
                "doctor_name": "Mr Rajesh Sharma",
                "consultation_type": "follow-up",
            }
            resp = call_n8n_first_webhook(audio_bytes, ctx, mime="audio/wav", filename="note.wav")

            # Use ONLY the webhook response; do not hit Neon here
            cid = resp.get("consultation_id") or resp.get("letter_id") or resp.get("id")
            letter_html = resp.get("letter_draft") or resp.get("html") or resp.get("letter_html") or ""
            transcript_text = resp.get("transcript") or resp.get("text") or ""

            st.session_state["consultation_id"] = cid
            st.session_state["transcript"] = transcript_text
            st.session_state["letter_draft"] = letter_html

            if cid:
                st.success("Draft generated.")
            else:
                st.warning("Draft generated, but your workflow didn't return a letter ID. (No DB fallback to save Neon.)")
        except Exception as e:
            st.error(f"Failed to generate draft: {e}")

    # Review & Approve
    if st.session_state.get("letter_draft"):
        st.divider()
        st.subheader("Review & Approve")

        if st.session_state.get("consultation_id"):
            st.markdown(
                f"<span class='pill'>Draft • ID: {st.session_state['consultation_id']}</span>",
                unsafe_allow_html=True,
            )

        with st.expander("Voice Transcript", expanded=True):
            st.write(st.session_state.get("transcript") or "_No transcript returned_")

        final_html = st.text_area(
            "Clinic Letter (HTML)",
            value=st.session_state["letter_draft"],
            height=360,
            key="letter_editor",
        )

        can_send = _has_secret("N8N_WEBHOOK_2") and final_html.strip()
        if st.button(
            "Approve & Send (Email + WhatsApp)",
            type="primary",
            use_container_width=True,
            key="approve_send_btn",
            disabled=not can_send,
        ):
            try:
                payload_ctx = {
                    # send full context so Workflow 2 can work with or without letter_id
                    "patient_id": selected["patient_id"],
                    "patient_name": selected["patient_name"],
                    "patient_email": selected["patient_email"],
                    "patient_phone": selected["patient_phone"],
                    "appointment_id": selected["appointment_id"],
                    "doctor_id": "dr-001",
                    "doctor_name": "Mr Rajesh Sharma",
                }
                res2 = call_n8n_second_webhook(
                    letter_id=st.session_state.get("consultation_id"),
                    final_letter_html=final_html,
                    context=payload_ctx,
                )
                st.success("Letter sent. Email + WhatsApp notification done.")
            except Exception as e:
                st.error(f"Send failed: {e}")

        if st.button("Reset draft", key="reset_draft_btn"):
            for k in ("consultation_id", "transcript", "letter_draft", "letter_editor"):
                st.session_state.pop(k, None)
            st.rerun()



