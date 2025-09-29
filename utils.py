import os, json, uuid, time
import psycopg2
import psycopg2.extras
import requests
from dotenv import load_dotenv; load_dotenv()

def get_db():
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=os.getenv("PGPASSWORD"),
        port=os.getenv("PGPORT","5432"),
        sslmode="require",
    )
    return conn

def fetch_today_appointments():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
      SELECT a.appointment_id, a.start_time, a.end_time, a.reason, a.fee_gbp, a.clinic_name,
             p.patient_id, p.patient_name, p.patient_email, p.patient_phone, p.insurer
      FROM appointments a
      JOIN patients p ON p.patient_id = a.patient_id
      WHERE date(a.start_time AT TIME ZONE 'Europe/London') = date(now() AT TIME ZONE 'Europe/London')
      ORDER BY a.start_time ASC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return rows

def call_n8n_first_webhook(audio_bytes, context):
    # n8n webhook 1 URL
    url = os.getenv("N8N_WEBHOOK_1")  # e.g., https://<your-n8n>/webhook/consultation/cliniclettergeneration
    files = {
        "audio_file": ("note.webm", audio_bytes, "audio/webm"),
        "context": (None, json.dumps(context), "application/json"),
    }
    r = requests.post(url, files=files, timeout=60)
    r.raise_for_status()
    return r.json()

def call_n8n_second_webhook(letter_id, final_html):
    url = os.getenv("N8N_WEBHOOK_2")  # e.g., https://<your-n8n>/webhook/consultation/sendclinicletter
    payload = {"letter_id": str(letter_id), "final_letter_html": final_html}
    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()
    return r.json()

def get_letter_by_id(letter_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""SELECT * FROM ops_clinic_letter WHERE letter_id = %s""", (letter_id,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row
