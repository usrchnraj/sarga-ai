import os, json, base64
from dotenv import load_dotenv; load_dotenv()

import streamlit as st
import requests
import psycopg
from psycopg.rows import dict_row

def _sec(k):  # read from env or streamlit secrets
    return os.getenv(k) or st.secrets.get(k)

def get_db():
    return psycopg.connect(
        host=_sec("PGHOST"),
        dbname=_sec("PGDATABASE"),
        user=_sec("PGUSER"),
        password=_sec("PGPASSWORD"),
        port=_sec("PGPORT") or "5432",
        sslmode="require",
    )
    return conn

def fetch_today_appointments():
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
          SELECT a.appointment_id, a.start_time, a.end_time, a.reason, a.fee_gbp, a.clinic_name,
                 p.patient_id, p.patient_name, p.patient_email, p.patient_phone, p.insurer
          FROM appointments a
          JOIN patients p ON p.patient_id = a.patient_id
          WHERE date(a.start_time AT TIME ZONE 'Europe/London') = date(now() AT TIME ZONE 'Europe/London')
          ORDER BY a.start_time ASC
        """)
        return cur.fetchall()
    cur.close(); conn.close()
    return rows

"""def call_n8n_first_webhook(audio_bytes, context):
    # n8n webhook 1 URL
    url = os.getenv("N8N_WEBHOOK_1")  # e.g., https://<your-n8n>/webhook/consultation/cliniclettergeneration
    files = {
        "audio_file": ("note.webm", audio_bytes, "audio/webm"),
        "context": (None, json.dumps(context), "application/json"),
    }
    r = requests.post(url, files=files, timeout=60)
    r.raise_for_status()
    return r.json()"""

def call_n8n_first_webhook(audio_bytes, context, mime="audio/webm", filename="note.webm"):
    url = _sec("N8N_WEBHOOK_1")
    headers = {"X-Webhook-Token": _sec("WEBHOOK_TOKEN")} if _sec("WEBHOOK_TOKEN") else {}
    files = {
        "audio_file": (filename, audio_bytes, mime),
        "context": (None, json.dumps(context), "application/json"),
    }
    r = requests.post(url, files=files, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()

def call_n8n_second_webhook(letter_id, final_html):
    url = os.getenv("N8N_WEBHOOK_2")  # e.g., https://<your-n8n>/webhook/consultation/sendclinicletter
    payload = {"letter_id": str(letter_id), "final_letter_html": final_html}
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def get_letter_by_id(letter_id):
    with get_db() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM ops_clinic_letter WHERE letter_id = %s", (letter_id,))
        return cur.fetchone()
    cur.close(); conn.close()
    return row
