import streamlit as st
import requests
import json
import pandas as pd
from datetime import datetime
import time
import base64
import uuid
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None  # Continue without database


# Page configuration
st.set_page_config(
    page_title="Clinic Letter System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better UI
st.markdown("""
<style>
    .stButton > button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        border: none;
        padding: 0.5rem 1rem;
        transition: all 0.3s;
    }
    .stButton > button:hover {
        background-color: #45a049;
        transform: translateY(-2px);
        box-shadow: 0 5px 10px rgba(0,0,0,0.2);
    }
    .recording-button > button {
        background-color: #dc3545 !important;
    }
    .status-card {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 4px solid #4CAF50;
        margin-bottom: 1rem;
    }
    .patient-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        margin-bottom: 1rem;
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
    }
    .success-message {
        padding: 1rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 10px;
        color: #155724;
    }
    .error-message {
        padding: 1rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        border-radius: 10px;
        color: #721c24;
    }
    div[data-testid="stSidebar"] {
        background-color: #f0f2f6;
    }
    .metric-card {
        background: white;
        padding: 1rem;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'consultation_stage' not in st.session_state:
    st.session_state.consultation_stage = 'select'  # select -> record -> review -> complete
if 'consultation_id' not in st.session_state:
    st.session_state.consultation_id = None
if 'selected_patient' not in st.session_state:
    st.session_state.selected_patient = None
if 'transcript' not in st.session_state:
    st.session_state.transcript = None
if 'letter_draft' not in st.session_state:
    st.session_state.letter_draft = None
if 'audio_recorded' not in st.session_state:
    st.session_state.audio_recorded = False

# Configuration - Update these
WEBHOOK_BASE_URL = st.secrets.get("webhook_base_url", "https://mangattilrajesh.app.n8n.cloud/webhook/audio-to-transcribe")
DB_CONFIG = {
    "host": st.secrets.get("db_host", "localhost"),
    "database": st.secrets.get("db_name", "clinic"),
    "user": st.secrets.get("db_user", "postgres"),
    "password": st.secrets.get("db_password", "password")
}

# Mock doctor data (hardcoded for prototype)
DOCTOR_INFO = {
    "id": "dr-001",
    "name": "Mr. Mangattil Rajesh",
    "email": "rajesh@spinesurgeon.london",
    "specialty": "Consultant Spine Surgeon",
    "hospital": "Royal London Hospital",
    "phone": "+447928333999"
}

# Mock patient data (for prototype - replace with DB query)
PATIENTS = [
    {"id": "p-001", "name": "John Smith", "email": "john@example.com", "phone": "+447700900001", "appointment_type": "Follow-up"},
    {"id": "p-002", "name": "Sarah Johnson", "email": "sarah@example.com", "phone": "+447700900002", "appointment_type": "Initial"},
    {"id": "p-003", "name": "Michael Brown", "email": "michael@example.com", "phone": "+447700900003", "appointment_type": "Post-op"}
]

@st.cache_resource
def get_db_connection():
    """Create database connection"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except:
        return None  # For prototype, continue without DB

def get_recent_letters():
    """Fetch recent letters from database with full status details"""
    conn = get_db_connection()
    if not conn:
        # Return mock data if DB not available
        return pd.DataFrame({
            'patient_name': ['Demo Patient 1', 'Demo Patient 2'],
            'created_at': [datetime.now(), datetime.now()],
            'status': ['SENT', 'DRAFT'],
            'email_sent': [True, False],
            'whatsapp_sent': [True, False],
            'letter_id': ['demo-001', 'demo-002']
        })
    
    try:
        query = """
            SELECT 
                letter_id,
                patient_name, 
                created_at, 
                status, 
                email_sent, 
                email_sent_at,
                whatsapp_sent,
                whatsapp_sent_at
            FROM ops_clinic_letter
            WHERE doctor_id = %s
            ORDER BY created_at DESC
            LIMIT 10
        """
        df = pd.read_sql(query, conn, params=[DOCTOR_INFO["id"]])
        conn.close()
        return df
    except:
        conn.close()
        return pd.DataFrame()

def process_audio(audio_data, patient_data, is_base64=False):
    """Send audio to webhook for processing"""
    try:
        # Convert base64 to bytes if needed
        if is_base64:
            import base64
            audio_bytes = base64.b64decode(audio_data)
        else:
            audio_bytes = audio_data
            
        # Prepare context with doctor email for CC
        context = {
            "patient_id": patient_data["id"],
            "patient_name": patient_data["name"],
            "patient_email": patient_data["email"],
            "patient_phone": patient_data["phone"],
            "appointment_id": f"apt-{uuid.uuid4().hex[:8]}",
            "doctor_id": DOCTOR_INFO["id"],
            "doctor_name": DOCTOR_INFO["name"],
            "doctor_email": DOCTOR_INFO["email"],
            "consultation_type": patient_data["appointment_type"]
        }
        
        # Prepare multipart data
        files = {
            'audio_file': ('recording.webm', audio_bytes, 'audio/webm')
        }
        data = {
            'context': json.dumps(context)
        }
        
        # Call webhook
        response = requests.post(
            f"{WEBHOOK_BASE_URL}/consultation/cliniclettergeneration",
            files=files,
            data=data,
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()
            # Always use the consultation_id from webhook (it's the DB letter_id)
            return result
        else:
            # Still return error state with consultation_id for tracking
            return {
                "consultation_id": str(uuid.uuid4()),
                "status": "ERROR_WEBHOOK",
                "error": f"Server returned {response.status_code}"
            }
            
    except requests.exceptions.Timeout:
        # Create error record but still return consultation_id
        return {
            "consultation_id": str(uuid.uuid4()),
            "status": "ERROR_TIMEOUT",
            "error": "Processing timeout"
        }
    except Exception as e:
        # Create error record but still return consultation_id
        return {
            "consultation_id": str(uuid.uuid4()),
            "status": "ERROR_GENERAL",
            "error": str(e)
        }

def send_letter(consultation_id, final_html):
    """Send the finalized letter"""
    try:
        payload = {
            "letter_id": consultation_id,
            "final_letter_html": final_html
        }
        
        response = requests.post(
            f"{WEBHOOK_BASE_URL}/consultation/sendclinicletter",
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            return None
            
    except Exception as e:
        st.error(f"Error sending letter: {str(e)}")
        return None

# HTML for audio recorder component
AUDIO_RECORDER_HTML = """
<div id="recorder-container">
    <button id="recordButton" style="
        background-color: #dc3545;
        color: white;
        padding: 12px 24px;
        font-size: 16px;
        border: none;
        border-radius: 25px;
        cursor: pointer;
        width: 200px;
        margin: 20px auto;
        display: block;
    ">🎤 Start Recording</button>
    <div id="status" style="text-align: center; margin-top: 10px;"></div>
    <audio id="audioPlayback" controls style="display: none; margin: 20px auto;"></audio>
</div>

<script>
let mediaRecorder;
let audioChunks = [];
let isRecording = false;

document.getElementById('recordButton').addEventListener('click', async () => {
    if (!isRecording) {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];
            
            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };
            
            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                const audioUrl = URL.createObjectURL(audioBlob);
                document.getElementById('audioPlayback').src = audioUrl;
                document.getElementById('audioPlayback').style.display = 'block';
                
                // Send to Streamlit
                const reader = new FileReader();
                reader.readAsDataURL(audioBlob);
                reader.onloadend = () => {
                    const base64Audio = reader.result.split(',')[1];
                    window.parent.postMessage({
                        type: 'streamlit:setComponentValue',
                        value: base64Audio
                    }, '*');
                };
                
                stream.getTracks().forEach(track => track.stop());
            };
            
            mediaRecorder.start();
            isRecording = true;
            document.getElementById('recordButton').textContent = '⏹️ Stop Recording';
            document.getElementById('recordButton').style.backgroundColor = '#6c757d';
            document.getElementById('status').textContent = 'Recording...';
            
        } catch (error) {
            document.getElementById('status').textContent = 'Error: Microphone access denied';
        }
    } else {
        mediaRecorder.stop();
        isRecording = false;
        document.getElementById('recordButton').textContent = '🎤 Start Recording';
        document.getElementById('recordButton').style.backgroundColor = '#dc3545';
        document.getElementById('status').textContent = 'Recording complete';
    }
});
</script>
"""

# Main app
def main():
    # Sidebar
    with st.sidebar:
        st.markdown(f"""
        <div class="patient-card">
            <h3>👨‍⚕️ {DOCTOR_INFO["name"]}</h3>
            <p>{DOCTOR_INFO["specialty"]}</p>
            <p>{DOCTOR_INFO["hospital"]}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Navigation
        page = st.radio(
            "Navigation",
            ["📝 New Consultation", "📊 Recent Letters", "ℹ️ Help"],
            label_visibility="collapsed"
        )
    
    # Main content area
    if page == "📝 New Consultation":
        consultation_workflow()
    elif page == "📊 Recent Letters":
        show_recent_letters()
    else:
        show_help()

def consultation_workflow():
    """Main consultation workflow"""
    
    st.title("📝 Generate Clinic Letter")
    
    # Progress indicator
    progress = 0.0
    if st.session_state.consultation_stage == 'select':
        progress = 0.25
    elif st.session_state.consultation_stage == 'record':
        progress = 0.5
    elif st.session_state.consultation_stage == 'review':
        progress = 0.75
    else:
        progress = 1.0
    
    st.progress(progress)
    
    # Stage 1: Patient Selection
    if st.session_state.consultation_stage == 'select':
        st.header("Step 1: Select Patient")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            patient_names = ["Select a patient..."] + [p["name"] for p in PATIENTS]
            selected_name = st.selectbox(
                "Choose patient for consultation",
                patient_names,
                key="patient_selector"
            )
            
            if selected_name != "Select a patient...":
                # Find selected patient data
                patient = next((p for p in PATIENTS if p["name"] == selected_name), None)
                if patient:
                    st.session_state.selected_patient = patient
                    
                    # Show patient info
                    st.markdown(f"""
                    <div class="status-card">
                        <h4>Patient Information</h4>
                        <p><strong>Name:</strong> {patient["name"]}</p>
                        <p><strong>Email:</strong> {patient["email"]}</p>
                        <p><strong>Type:</strong> {patient["appointment_type"]}</p>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("▶️ Start Consultation", type="primary"):
                        st.session_state.consultation_stage = 'record'
                        st.rerun()
    
    # Stage 2: Audio Recording
    elif st.session_state.consultation_stage == 'record':
        st.header("Step 2: Record Consultation Summary")
        
        patient = st.session_state.selected_patient
        st.info(f"Recording for: **{patient['name']}**")
        
        tab1, tab2 = st.tabs(["🎤 Voice Recording", "⌨️ Type Notes"])
        
        with tab1:
            st.write("Click the button below to start recording your consultation summary:")
            
            # Simple audio recorder using HTML component
            audio_component = st.components.v1.html(AUDIO_RECORDER_HTML, height=200)
            
            # Note about base64 audio bridge
            st.info("📌 For demo: Please use the file uploader below for reliable audio submission")
            
            # PRIMARY PATH: File uploader (more reliable for demo)
            st.markdown("---")
            st.write("**Upload a pre-recorded audio file:** (Recommended)")
            audio_file = st.file_uploader("Choose audio file", type=['webm', 'wav', 'mp3', 'm4a'])
            
            if audio_file:
                st.audio(audio_file)
                if st.button("📤 Process Audio", type="primary"):
                    with st.spinner("🔄 Transcribing and generating letter..."):
                        result = process_audio(audio_file.read(), patient, is_base64=False)
                        
                        # Handle both success and error states
                        st.session_state.consultation_id = result.get("consultation_id")
                        
                        if result.get("status") and result["status"].startswith("ERROR"):
                            st.error(f"⚠️ Processing failed: {result.get('error', 'Unknown error')}")
                            st.info("A record has been created for manual review. ID: " + st.session_state.consultation_id[:8])
                        else:
                            st.session_state.transcript = result.get("transcript")
                            st.session_state.letter_draft = result.get("letter_draft")
                            st.session_state.consultation_stage = 'review'
                            st.rerun()
        
        with tab2:
            st.write("Type or paste your consultation notes:")
            notes = st.text_area(
                "Consultation Notes",
                height=300,
                placeholder="Patient presented with... Examination findings... Management plan..."
            )
            
            if st.button("📝 Generate Letter from Notes", type="primary"):
                if notes:
                    # For text-based generation without audio
                    # This should ideally call a modified webhook endpoint
                    # For now, creating a draft letter locally
                    
                    # Generate a consultation_id to track this attempt
                    consultation_id = str(uuid.uuid4())
                    
                    # Create structured letter from notes
                    st.session_state.transcript = notes
                    st.session_state.letter_draft = f"""
                    <html>
                    <body>
                    <div style="font-family: Arial;">
                        <h2>{DOCTOR_INFO["name"]}</h2>
                        <p>{DOCTOR_INFO["specialty"]}</p>
                        <hr>
                        <p>Date: {datetime.now().strftime("%d %B %Y")}</p>
                        <p>Dear {patient["name"]},</p>
                        <div>{notes}</div>
                        <p>Yours sincerely,<br>{DOCTOR_INFO["name"]}</p>
                    </div>
                    </body>
                    </html>
                    """
                    # Use the generated ID, not create a new one
                    st.session_state.consultation_id = consultation_id
                    st.session_state.consultation_stage = 'review'
                    st.rerun()
    
    # Stage 3: Review and Edit
    elif st.session_state.consultation_stage == 'review':
        st.header("Step 3: Review and Edit Letter")
        
        patient = st.session_state.selected_patient
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("Letter Draft")
            
            # Editable letter
            edited_letter = st.text_area(
                "Edit the letter as needed:",
                value=st.session_state.letter_draft,
                height=500,
                key="letter_editor"
            )
            
            # Preview in expander
            with st.expander("📄 Preview Formatted Letter"):
                st.markdown(edited_letter, unsafe_allow_html=True)
        
        with col2:
            st.subheader("Actions")
            
            st.markdown(f"""
            <div class="status-card">
                <p><strong>Patient:</strong><br>{patient["name"]}</p>
                <p><strong>Email:</strong><br>{patient["email"]}</p>
                <p><strong>Consultation ID:</strong><br>{st.session_state.consultation_id[:8]}...</p>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("✅ Approve & Send", type="primary"):
                with st.spinner("📧 Sending letter..."):
                    result = send_letter(st.session_state.consultation_id, edited_letter)
                    if result:
                        st.session_state.consultation_stage = 'complete'
                        st.rerun()
                    else:
                        st.error("Failed to send letter. Please try again.")
            
            if st.button("🔄 Start New Consultation"):
                # Reset state
                st.session_state.consultation_stage = 'select'
                st.session_state.consultation_id = None
                st.session_state.selected_patient = None
                st.session_state.transcript = None
                st.session_state.letter_draft = None
                st.rerun()
    
    # Stage 4: Complete
    elif st.session_state.consultation_stage == 'complete':
        st.markdown("""
        <div class="success-message">
            <h2>✅ Letter Successfully Sent!</h2>
            <p>The clinic letter has been sent to the patient's email address.</p>
            <p>A WhatsApp notification has also been sent.</p>
        </div>
        """, unsafe_allow_html=True)
        
        patient = st.session_state.selected_patient
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Patient", patient["name"])
        with col2:
            st.metric("Email", patient["email"])
        with col3:
            st.metric("Time", datetime.now().strftime("%H:%M"))
        
        st.markdown("---")
        
        if st.button("📝 Start New Consultation", type="primary"):
            # Reset state
            st.session_state.consultation_stage = 'select'
            st.session_state.consultation_id = None
            st.session_state.selected_patient = None
            st.session_state.transcript = None
            st.session_state.letter_draft = None
            st.rerun()

def show_recent_letters():
    """Display recent letters with full status tracking"""
    st.title("📊 Recent Letters")
    
    # Get recent letters
    df = get_recent_letters()
    
    if not df.empty:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Letters", len(df))
        with col2:
            sent = len(df[df['status'] == 'SENT'])
            st.metric("Sent", sent)
        with col3:
            draft = len(df[df['status'] == 'DRAFT'])
            st.metric("Drafts", draft)
        with col4:
            errors = len(df[df['status'].str.startswith('ERROR', na=False)]) if 'status' in df.columns else 0
            st.metric("Errors", errors)
        
        st.markdown("---")
        
        # Display letters with enhanced status
        for _, row in df.iterrows():
            # Determine status indicators
            if row['status'] == 'SENT':
                status_color = "🟢"
                card_border = "#28a745"
            elif row['status'] == 'DRAFT':
                status_color = "🟡"
                card_border = "#ffc107"
            elif row['status'].startswith('ERROR'):
                status_color = "🔴"
                card_border = "#dc3545"
            else:
                status_color = "⚪"
                card_border = "#6c757d"
            
            # Email and WhatsApp status
            email_status = "✅ Sent" if row.get('email_sent') else "⏳ Pending"
            whatsapp_status = "✅ Sent" if row.get('whatsapp_sent') else "⏳ Pending"
            
            # Format timestamps
            created_time = row['created_at'].strftime("%d %b %Y %H:%M") if pd.notnull(row['created_at']) else "N/A"
            
            st.markdown(f"""
            <div style="background-color: #f8f9fa; padding: 1.5rem; border-radius: 10px; border-left: 4px solid {card_border}; margin-bottom: 1rem;">
                <h4>{status_color} {row['patient_name']}</h4>
                <p><strong>Letter ID:</strong> {row.get('letter_id', 'N/A')[:8]}...</p>
                <p><strong>Created:</strong> {created_time}</p>
                <p><strong>Status:</strong> {row['status']}</p>
                <div style="display: flex; gap: 20px; margin-top: 10px;">
                    <span><strong>📧 Email:</strong> {email_status}</span>
                    <span><strong>💬 WhatsApp:</strong> {whatsapp_status}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No letters found. Start a new consultation to create your first letter.")

def show_help():
    """Display help information"""
    st.title("ℹ️ Help & Instructions")
    
    st.markdown("""
    ## How to Use the Clinic Letter System
    
    ### 1️⃣ **Start a New Consultation**
    - Select a patient from the dropdown
    - Click "Start Consultation"
    
    ### 2️⃣ **Record Your Notes**
    - **Option A:** Click the red recording button and speak your consultation summary
    - **Option B:** Type or paste your notes in the text area
    
    ### 3️⃣ **Review the Generated Letter**
    - The system will automatically generate a formal clinic letter
    - Edit any parts that need adjustment
    - Preview the formatted version
    
    ### 4️⃣ **Send to Patient**
    - Click "Approve & Send"
    - The letter will be emailed to the patient
    - A WhatsApp notification will be sent
    
    ---
    
    ### 🔧 **Technical Support**
    - Webhook URL: `{WEBHOOK_BASE_URL}`
    - Database: {'Connected ✅' if get_db_connection() else 'Not Connected ❌'}
    
    ### 📞 **Contact**
    For issues or questions, contact the development team.
    """)

if __name__ == "__main__":
    main()






