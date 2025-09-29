# app.py
import os, json, datetime as dt
import streamlit as st
from audio_recorder_streamlit import audio_recorder

from utils import (
    fetch_today_appointments,
    call_n8n_first_webhook,
    call_n8n_second_webhook,
)

st.set_page_config(page_title="Appointments", layout="wide")

# ---------- Tiny helpers ----------
def _has_secret(k: str) -> bool:
    try:
        return bool(os.getenv(k) or st.secrets.get(k))
    except Exception:
        return False

def _fmt_apt(r: dict) -> str:
    # r['start_time'] might be datetime or string; keep robust
    try:
        t = dt.datetime.fromisoformat(str(r["start_time"]))
        hhmm = t.strftime("%H:%M")
    except Exception:
        hhmm = "—"
    return f"{r['patient_name']} • {r['reason']} • {hhmm}"

# ---------- CSS polish ----------
st.markdown(
    """
    <style>
      .block-container { padding-top: 2rem; }
      .pill { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; background:#eef2ff; color:#4338ca; }
      .muted { color:#64748b; font-size:13px; }
      .card { border-radius:16px; padding:16px; background:white; box-shadow:0 1px 3px rgba(16,24,40,.08); }
      .btn-row { display:flex; gap:.5rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Appointments")

# ---------- Session boot ----------
if "appointments" not in st.session_state:
    st.session_state["appointments"] = []
if "consultation_id" not in st.session_state:
    st.session_state["consultation_id"] = None
if "transcript" not in st.session_state:
    st.session_state["transcript"] = ""
if "letter_draft" not in st.session_state:
    st.session_state["letter_draft"] = ""

colL, colR = st.columns([1.25, 1])

# ---------- LEFT: list & refresh ----------
with colL:
    st.subheader("Today's List")

    if st.button("🔄 Refresh appointments", use_container_width=True):
        try:
            st.session_state["appointments"] = fetch_today_appointments()
            st.success(f"Loaded {len(st.session_state['appointments'])} appointments.")
        except Exception as e:
            st.error(f"Failed to load appointments: {e}")

    apts = st.session_state["appointments"]

    if not apts:
        st.info("No data loaded. Click **Refresh appointments** to fetch from Neon.")
        st.stop()  # stop rendering right column until we have data

    selected = st.radio(
        "Select a patient",
        apts,
        format_func=_fmt_apt,
        index=0,
        key="patient_radio",
    )

# ---------- RIGHT: actions ----------
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
            st.session_state["consultation_id"] = resp.get("consultation_id")
            st.session_state["transcript"] = resp.get("transcript", "")
            st.session_state["letter_draft"] = resp.get("letter_draft", "")
            st.success("Draft generated.")
        except Exception as e:
            st.error(f"Failed to generate draft: {e}")

    # ----- Draft review + approve -----
    if st.session_state["consultation_id"]:
        st.divider()
        st.markdown(f"<span class='pill'>Draft • ID: {st.session_state['consultation_id']}</span>", unsafe_allow_html=True)

        with st.expander("Voice Transcript", expanded=True):
            st.write(st.session_state["transcript"] or "_No transcript returned_")

        st.write("### Clinic Letter (Editable)")
        final_html = st.text_area(
            "Letter HTML",
            value=st.session_state["letter_draft"],
            height=360,
            key="letter_editor",
            label_visibility="collapsed",
        )

        disabled_second = not (_has_secret("N8N_WEBHOOK_2") and final_html.strip())
        if st.button(
            "Approve & Send (Email + WhatsApp)",
            type="primary",
            use_container_width=True,
            disabled=disabled_second,
            key="approve_send_btn",
        ):
            try:
                res2 = call_n8n_second_webhook(st.session_state["consultation_id"], final_html)
                st.success("Letter sent. Email + WhatsApp notification done.")
            except Exception as e:
                st.error(f"Send failed: {e}")

