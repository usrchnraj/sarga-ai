import os, base64, json, uuid, datetime as dt
import streamlit as st
import streamlit.components.v1 as components
from utils import fetch_today_appointments, call_n8n_first_webhook, call_n8n_second_webhook, get_letter_by_id

st.set_page_config(page_title="Clinic Letters", layout="wide")

st.title("Appointments")

# Load today's appointments
apts = fetch_today_appointments()
if not apts:
    st.info("No appointments scheduled today.")
else:
    # Left: list, Right: action panel
    colL, colR = st.columns([1.2,1])

    with colL:
        st.subheader("Today's List")
        selected = st.radio(
            "Select a patient",
            apts,
            format_func=lambda r: f"{r['patient_name']} • {r['reason']} • {dt.datetime.fromisoformat(str(r['start_time'])).strftime('%H:%M')}",
            index=0,
        )

    with colR:
        st.subheader("Actions")
        st.caption("1) Record → 2) Get Draft → 3) Edit → 4) Approve & Send")

        # --- Recorder ---
        st.write("### Voice Notes")
        st.caption("Tap Start, dictate your findings; tap Stop to finish. (~30–120s)")

        # Listen for a custom JS event that passes base64 audio
        components.html(open("recorder_component.html","r").read(), height=120)
        js_code = """
        <script>
        const handler = (e) => {
            const data = e.detail.base64;
            // Find the Streamlit textarea by its aria-label (the label you used in st.text_area)
            const textarea = window.parent.document.querySelector('textarea[aria-label="Hidden base64 dump"]');
            if (textarea) {
                textarea.value = data;
                // Fire an input event so Streamlit picks up the change
                const event = new Event('input', { bubbles: true });
                textarea.dispatchEvent(event);
            } else {
                console.warn('Hidden base64 dump textarea not found');
            }
        };
        window.addEventListener('FROM_RECORDER', handler);
        </script>
        """
        components.html(js_code, height=0)
        audio_b64 = st.text_area("Hidden base64 dump", key="audio_b64", label_visibility="collapsed", height=1)

        if st.button("Generate Draft from Recording", type="primary", use_container_width=True, disabled=not audio_b64):
            try:
                audio_bytes = base64.b64decode(audio_b64)
                ctx = {
                    "patient_id": selected["patient_id"],
                    "patient_name": selected["patient_name"],
                    "patient_email": selected["patient_email"],
                    "patient_phone": selected["patient_phone"],
                    "appointment_id": selected["appointment_id"],
                    "doctor_id": "dr-001",
                    "doctor_name": "Mr Rajesh Sharma",
                    "consultation_type": "follow-up"
                }
                resp = call_n8n_first_webhook(audio_bytes, ctx)
                st.session_state["consultation_id"] = resp.get("consultation_id")
                st.session_state["transcript"] = resp.get("transcript","")
                st.session_state["letter_draft"] = resp.get("letter_draft","")
                st.success("Draft generated.")
            except Exception as e:
                st.error(f"Failed to generate draft: {e}")

        # --- Review/Edit panel (appears after draft) ---
        if "consultation_id" in st.session_state:
            st.write("### Voice Transcript")
            st.info(st.session_state.get("transcript",""))

            st.write("### Clinic Letter (Editable)")
            final_html = st.text_area("Letter HTML", value=st.session_state.get("letter_draft",""), height=400)

            if st.button("Approve & Send (Email + WhatsApp)", type="primary", use_container_width=True):
                try:
                    res2 = call_n8n_second_webhook(st.session_state["consultation_id"], final_html)
                    st.success("Letter sent. Email + WhatsApp notification done.")
                except Exception as e:
                    st.error(f"Send failed: {e}")
