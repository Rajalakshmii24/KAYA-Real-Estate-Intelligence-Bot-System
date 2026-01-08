import streamlit as st
import ollama
import sqlite3
import json
import pandas as pd
from datetime import datetime
from io import BytesIO

# --- 1. BRANDING & STYLE ---
st.set_page_config(page_title="KAYA Real Estate", page_icon="🔑", layout="wide")
st.markdown("""
    <style>
    .stApp { background-color: #0c0d11; color: #e0e0e0; }
    .stButton > button { width: 100%; border-radius: 10px; border: 1px solid #d4af37; background-color: #16181d; color: #d4af37; font-weight: bold; margin-bottom: 5px; }
    .stChatMessage { border-radius: 15px; border: 1px solid #2d2f39; margin-bottom: 10px; }
    div[data-testid="stChatMessage"]:nth-child(even) { background-color: #1c1e26 !important; border-left: 5px solid #d4af37; }
    h1 { color: #d4af37 !important; text-align: center; font-family: 'Playfair Display', serif; }
    [data-testid="stSidebar"] { background-color: #111217; border-right: 1px solid #2d2f39; }
    .sidebar-title { color: #d4af37; font-size: 0.8rem; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 10px; }
    .login-box { max-width: 500px; margin: auto; padding: 40px; border: 1px solid #d4af37; border-radius: 20px; background-color: #16181d; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
    .del-btn > button { border: none !important; background-color: transparent !important; color: #ff4b4b !important; font-size: 0.8rem !important; text-align: right !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. DATABASE INITIALIZATION ---
def init_db():
    conn = sqlite3.connect('kaya_leads.db', check_same_thread=False)
    # Added 'status' column to the table
    conn.execute('''CREATE TABLE IF NOT EXISTS chat_history 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     name TEXT, email TEXT, mobile TEXT, messages TEXT, 
                     lead_data TEXT, status TEXT, timestamp TEXT)''')
    conn.commit()
    return conn

db = init_db()

def save_registry_to_db(name, email, mobile):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO chat_history (name, email, mobile, messages, lead_data, status, timestamp) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, email, mobile, json.dumps([]), json.dumps({}), "Pending", timestamp)
    )
    db.commit()
    return cursor.lastrowid

# --- 3. SESSION INITIALIZATION ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_data" not in st.session_state:
    st.session_state.user_data = None
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.lead_data = {"unit": None, "purpose": None, "budget": None, "area": None}
    st.session_state.current_step = "greeting"
    st.session_state.session_id = None 

# --- 4. FRONT PAGE ---
if not st.session_state.logged_in:
    st.markdown("<br><br><br><h1>K.A.Y.A REAL ESTATE</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.subheader("Register to Access Concierge")
        reg_name = st.text_input("Full Name")
        reg_email = st.text_input("Email ID")
        reg_mobile = st.text_input("Mobile Number")
        if st.button("ENTER TO CHAT"):
            if reg_name and reg_email and reg_mobile:
                new_id = save_registry_to_db(reg_name, reg_email, reg_mobile)
                st.session_state.user_data = {"name": reg_name, "email": reg_email, "mobile": reg_mobile}
                st.session_state.session_id = new_id
                st.session_state.logged_in = True
                st.rerun() 
    st.stop()

# --- 5. CHAT BOT LOGIC ---
def get_flow():
    ld = st.session_state.lead_data
    is_rent = ld.get("purpose") == "Rent"
    budget_msg = "What is your yearly rental budget?" if is_rent else "What is your ideal budget range for this investment?"
    budget_sug = ["50k - 100k", "100k - 200k", "250k+"] if is_rent else ["Below 1.5M", "1.5M - 3M", "Luxury (5M+)"]
    return {
        "greeting": {"msg": f"Welcome, {st.session_state.user_data['name']} to KAYA Real Estate. I am your digital concierge. Are you looking to find a new property today?", "suggestions": ["Yes, I'm looking!", "Just browsing"]},
        "unit": {"msg": "Excellent. What kind of unit are you looking for?", "suggestions": ["Studio / 1BR", "2BR or 3BR", "Villa / Penthouse"]},
        "purpose": {"msg": "Are you looking to Rent or Buy?", "suggestions": ["Rent", "Buy"]},
        "budget": {"msg": budget_msg, "suggestions": budget_sug},
        "area": {"msg": "Which area in Dubai do you prefer? (e.g., Dunes Village, Downtown, Marina)", "suggestions": ["Downtown Dubai", "Dubai Marina", "Jumeirah Village Circle"]},
        "qanda": {"msg": "I've noted your preferences. Any specific questions?", "suggestions": ["No, I'm ready", "Talk to an agent"]},
        "closing": {"msg": "I've noted your preferences. Thank you. Your request is now priority. A KAYA team member will connect with you shortly via WhatsApp. Have a prestigious day!", "suggestions": []}
    }

def extract_info(text):
    t_low = text.lower()
    ld = st.session_state.lead_data
    if any(x in t_low for x in ["studio", "1br", "2br", "3br", "villa", "penthouse"]): ld["unit"] = text
    if "rent" in t_low: ld["purpose"] = "Rent"
    elif any(x in t_low for x in ["buy", "invest"]): ld["purpose"] = "Buy"
    if any(x in t_low for x in ["million", "aed", "budget", "k ", "50k", "100k", "200k"]): ld["budget"] = text
    if not ld["area"] and st.session_state.current_step == "area":
        try:
            resp = ollama.chat(model='llama3.1', messages=[{"role": "system", "content": "Extract Dubai area. Else 'NONE'"},{"role": "user", "content": text}])
            ai_ext = resp['message']['content'].strip()
            ld["area"] = ai_ext if "NONE" not in ai_ext.upper() else text
        except: ld["area"] = text

def handle_input(user_text):
    st.session_state.messages.append({"role": "user", "content": user_text})
    extract_info(user_text)
    ld = st.session_state.lead_data
    if not ld["unit"]: st.session_state.current_step = "unit"
    elif not ld["purpose"]: st.session_state.current_step = "purpose"
    elif not ld["budget"]: st.session_state.current_step = "budget"
    elif not ld["area"]: st.session_state.current_step = "area"
    elif st.session_state.current_step != "closing": st.session_state.current_step = "qanda"
    if user_text in ["No, I'm ready", "Talk to an agent"]: st.session_state.current_step = "closing"
    
    st.session_state.messages.append({"role": "assistant", "content": get_flow()[st.session_state.current_step]["msg"]})
    db.execute("UPDATE chat_history SET messages = ?, lead_data = ? WHERE id = ?", 
               (json.dumps(st.session_state.messages), json.dumps(st.session_state.lead_data), st.session_state.session_id))
    db.commit()

# --- 6. SIDEBAR ---
with st.sidebar:
    st.markdown("<div class='sidebar-title'>Registry</div>", unsafe_allow_html=True)
    st.write(f"👤 **{st.session_state.user_data['name']}**")
    
    # Status Updater for the active lead
    if st.session_state.session_id:
        st.write("---")
        res = db.execute("SELECT status FROM chat_history WHERE id = ?", (st.session_state.session_id,)).fetchone()
        current_status = res[0] if res else "Pending"
        status_options = ["Pending", "Agent Talking", "Success", "Unsuccessful"]
        new_status = st.selectbox("Update Lead Status", status_options, index=status_options.index(current_status))
        if new_status != current_status:
            db.execute("UPDATE chat_history SET status = ? WHERE id = ?", (new_status, st.session_state.session_id))
            db.commit()
            st.rerun()

    # Excel Export
    if st.button("📊 Export Leads to Excel"):
        df = pd.read_sql_query("SELECT name, email as 'Email ID', mobile as 'Mobile Number', lead_data, status as 'Status' FROM chat_history", db)
        
        # Create Description column from lead_data
        def create_desc(ld_json):
            d = json.loads(ld_json)
            if not d.get('unit'): return "New Lead / Browsing"
            return f"Looking for {d.get('unit')} to {d.get('purpose')} in {d.get('area')} (Budget: {d.get('budget')})"
        
        df['Description'] = df['lead_data'].apply(create_desc)
        final_excel_df = df[['name', 'Email ID', 'Mobile Number', 'Description', 'Status']]
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            final_excel_df.to_excel(writer, index=False, sheet_name='KAYA Leads')
        st.download_button("📥 Download Excel Report", output.getvalue(), "KAYA_Leads.xlsx")

    if st.button("➕ New Chat Session"):
        st.session_state.messages, st.session_state.lead_data = [], {"unit": None, "purpose": None, "budget": None, "area": None}
        st.session_state.current_step = "greeting"
        st.session_state.session_id = save_registry_to_db(st.session_state.user_data['name'], st.session_state.user_data['email'], st.session_state.user_data['mobile'])
        st.rerun()

    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.rerun()
        
    st.write("---")
    st.markdown("<div class='sidebar-title'>Saved Leads</div>", unsafe_allow_html=True)
    cursor = db.execute("SELECT id, timestamp, status FROM chat_history WHERE email = ? ORDER BY id DESC", (st.session_state.user_data['email'],))
    for item_id, item_time, item_stat in cursor.fetchall():
        col_chat, col_del = st.columns([4, 1])
        with col_chat:
            if st.button(f"📜 {item_id}: {item_stat}", key=f"h_{item_id}"):
                row = db.execute("SELECT messages, lead_data FROM chat_history WHERE id = ?", (item_id,)).fetchone()
                st.session_state.session_id, st.session_state.messages = item_id, json.loads(row[0])
                st.session_state.lead_data = json.loads(row[1])
                st.rerun()
        with col_del:
            if st.button("🗑️", key=f"del_{item_id}"):
                db.execute("DELETE FROM chat_history WHERE id = ?", (item_id,)); db.commit(); st.rerun()

# --- 7. MAIN INTERFACE ---
st.markdown("<h1>KAYA PRIVATE CONCIERGE</h1>", unsafe_allow_html=True)
if not st.session_state.messages: st.session_state.messages.append({"role": "assistant", "content": get_flow()["greeting"]["msg"]})
for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

if st.session_state.current_step != "closing":
    st.write("---")
    sugs = get_flow()[st.session_state.current_step]["suggestions"]
    cols = st.columns(len(sugs))
    for i, choice in enumerate(sugs):
        if cols[i].button(choice): handle_input(choice); st.rerun()

if prompt := st.chat_input("How can KAYA assist you?"):
    handle_input(prompt); st.rerun()