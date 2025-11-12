# app.py
import os
import base64
import hashlib
from io import BytesIO
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import sqlite3
import streamlit as st

# Optional rich tables + animations (safe fallbacks)
try:
    from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode
    HAS_AGGRID = True
except Exception:
    HAS_AGGRID = False

try:
    from streamlit_lottie import st_lottie
    import json
    HAS_LOTTIE = True
except Exception:
    HAS_LOTTIE = False

# =========================
# Basic Config & Constants
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_TITLE = "SJCET - AttendPro"

# Streamlit page config MUST be called before any other Streamlit output
st.set_page_config(page_title=APP_TITLE, layout="wide")

# ------------------------
# Where to store / read data
# ------------------------
CANDIDATE_STUDENTS_DIRS = [
    os.path.join(BASE_DIR, "students_list"),
    os.path.join(BASE_DIR, "sjcet-attendpro", "students_list"),
]
for p in CANDIDATE_STUDENTS_DIRS:
    if os.path.exists(p) and os.path.isdir(p):
        STUDENTS_FOLDER = p
        break
else:
    STUDENTS_FOLDER = CANDIDATE_STUDENTS_DIRS[0]
    os.makedirs(STUDENTS_FOLDER, exist_ok=True)  # allow upload-in-app fallback

ATTENDANCE_FOLDER = os.path.join(BASE_DIR, "attendance_records")
DB_PATH = os.path.join(BASE_DIR, "attendpro.db")
os.makedirs(ATTENDANCE_FOLDER, exist_ok=True)

# =========================
# UI: Global CSS (Theme-aware)
# =========================
APP_CSS = """
<style>
:root{
  --bg-1-dark: #072a34;
  --bg-2-dark: #0a3f49;
  --bg-3-dark: #0c555a;
  --glass-dark: rgba(255,255,255,0.06);
  --glass-border-dark: rgba(255,255,255,0.12);
  --text-dark: #e6f6f5;

  --bg-1-light: #f6fbfb;
  --bg-2-light: #e8f7f6;
  --bg-3-light: #dff3f2;
  --glass-light: rgba(0,0,0,0.04);
  --glass-border-light: rgba(0,0,0,0.08);
  --text-light: #0b2b2c;

  --brand-1: #0077b6;
  --brand-2: #00b4d8;

  --kpi-bg: rgba(255,255,255,0.02);
}

/* Default (assume dark) */
[data-testid="stAppViewContainer"]{
  background: radial-gradient(1200px circle at 12% 8%, var(--bg-3-dark) 0%, var(--bg-2-dark) 35%, var(--bg-1-dark) 100%) !important;
  color: var(--text-dark);
}
.block-container{ padding-top: 1.2rem; }

/* Buttons */
.stButton>button{
  border-radius: 12px !important;
  font-weight: 700 !important;
  border: 1px solid var(--glass-border-dark) !important;
  background: var(--glass-dark) !important;
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s;
  color: var(--text-dark) !important;
}

/* Cards & glass */
.attn-card{
  border-radius: 14px;
  padding: 12px 10px;
  border: 1px solid var(--glass-border-dark);
  background: var(--glass-dark);
  backdrop-filter: blur(6px);
  transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
  text-align: center;
}

/* Title */
.centered-title{
  text-align:center;
  font-weight:800;
  font-size: clamp(1.4rem, 2.6vw, 2.0rem);
  margin: .5rem 0 .6rem 0;
  letter-spacing:.2px;
  background: linear-gradient(90deg, var(--brand-1), var(--brand-2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* Dataframe glass */
[data-testid="stDataFrame"] div[data-testid="stHorizontalBlock"]{ row-gap:.25rem !important; }
[data-testid="stDataFrame"]{
  border-radius: 12px; overflow:hidden;
  border:1px solid var(--glass-border-dark);
  background: var(--glass-dark);
  backdrop-filter: blur(6px);
}

/* Light theme overrides */
@media (prefers-color-scheme: light) {
  :root {
    --glass: var(--glass-light);
    --glass-border: var(--glass-border-light);
    --text: var(--text-light);
  }
  [data-testid="stAppViewContainer"]{
    background: radial-gradient(1200px circle at 12% 8%, var(--bg-3-light) 0%, var(--bg-2-light) 35%, var(--bg-1-light) 100%) !important;
    color: var(--text-light);
  }
  .stButton>button{
    border: 1px solid var(--glass-border-light) !important;
    background: var(--glass-light) !important;
    color: var(--text-light) !important;
  }
  .attn-card{
    border: 1px solid var(--glass-border-light);
    background: var(--glass-light);
    color: var(--text-light);
  }
  [data-testid="stDataFrame"]{
    border:1px solid var(--glass-border-light);
    background: var(--glass-light);
    color: var(--text-light);
  }
}

/* Small screens */
@media (max-width:640px){
  .block-container{ padding-left:.6rem; padding-right:.6rem; }
  .centered-title{ font-size:1.3rem; }
  .stButton>button{ width:100% !important; }
  .attn-card{ font-size:.95rem; padding:8px 6px; }
}
</style>
"""
st.markdown(APP_CSS, unsafe_allow_html=True)

# =========================
# Branding: Centered Logo + Title
# =========================
def render_branding():
    logo_path = os.path.join(BASE_DIR, "sjcet_logo.png")
    if os.path.exists(logo_path):
        with open(logo_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        st.markdown(
            f"""
            <div style="display:flex; flex-direction:column; align-items:center; gap:10px; margin: 4px 0 16px;">
                <img src="data:image/png;base64,{b64}" alt="College Logo"
                     style="width:160px; height:auto; border-radius:10px;" />
                <div class="centered-title">🎓 {APP_TITLE}</div>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"""
            <div style="text-align:center; margin: 4px 0 16px;">
                <div class="centered-title">🎓 {APP_TITLE}</div>
            </div>
            """,
            unsafe_allow_html=True
        )

render_branding()

# =========================
# Section aliasing
# =========================
SECTION_CANONICALS = [
    "II-CSE_A", "II-CSE_B", "II-CSE_C", "II-CSD", "III-CSE", "III-CSD"
]

def _loose_key(s: str) -> str:
    return (
        str(s).strip().lower()
        .replace(" ", "")
        .replace(".", "_")
        .replace("-", "_")
    )

ALIAS_TO_CANON = {
    _loose_key("II-CSE_A"): "II-CSE_A",
    _loose_key("II CSE A"): "II-CSE_A",
    _loose_key("II-CSE.A"): "II-CSE_A",
    _loose_key("II-CSE_B"): "II-CSE_B",
    _loose_key("II CSE B"): "II-CSE_B",
    _loose_key("II-CSE.B"): "II-CSE_B",
    _loose_key("II-CSE_C"): "II-CSE_C",
    _loose_key("II CSE C"): "II-CSE_C",
    _loose_key("II-CSE.C"): "II-CSE_C",
    _loose_key("II-CSD"):   "II-CSD",
    _loose_key("CSE_DS"):   "II-CSD",
    _loose_key("CSE.DS"):   "II-CSD",
    _loose_key("II-CSE_DS"):"II-CSD",
    _loose_key("II-CSE.DS"):"II-CSD",
    _loose_key("II CSE DS"):"II-CSD",
    _loose_key("III-CSE"):  "III-CSE",
    _loose_key("III CSE"):  "III-CSE",
    _loose_key("III-CSD"):  "III-CSD",
    _loose_key("III CSD"):  "III-CSD",
    _loose_key("lll-CSD"):  "III-CSD",
}

CANON_TO_FILENAMES = {
    "II-CSE_A": ["II-CSE_A.csv", "II-CSE.A.csv"],
    "II-CSE_B": ["II-CSE_B.csv", "II-CSE.B.csv"],
    "II-CSE_C": ["II-CSE_C.csv", "II-CSE.C.csv"],
    "II-CSD"  : ["II-CSD.csv", "CSE_DS.csv", "CSE.DS.csv", "II-CSE_DS.csv", "II-CSE.DS.csv"],
    "III-CSE" : ["III-CSE.csv"],
    "III-CSD" : ["III-CSD.csv", "lll-CSD.csv"],
}

def normalize_section(sec: str) -> str:
    return ALIAS_TO_CANON.get(_loose_key(sec), sec)

def find_csv_for_section(sec: str) -> str | None:
    canon = normalize_section(sec)
    candidates = CANON_TO_FILENAMES.get(canon, [f"{canon}.csv"])
    for fname in candidates:
        p = os.path.join(STUDENTS_FOLDER, fname)
        if os.path.exists(p):
            return p
    fallback = os.path.join(STUDENTS_FOLDER, f"{sec}.csv")
    return fallback if os.path.exists(fallback) else None

def primary_filename_for_canon(canon: str) -> str:
    files = CANON_TO_FILENAMES.get(canon, [f"{canon}.csv"])
    return files[0]

# =========================
# DB & Auth Utilities
# =========================
SALT = "sjcet_attendpro_salt_2025"

def hash_password(plain: str) -> str:
    return hashlib.sha256((plain + SALT).encode()).hexdigest()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users(
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_meta(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            section TEXT,
            attendance_date TEXT,
            period TEXT,
            submitted_by TEXT,
            created_at TEXT
        )
        """
    )
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance_rows(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            meta_id INTEGER,
            regd_no TEXT,
            name TEXT,
            present INTEGER,
            parent_name TEXT,
            parent_phone TEXT,
            FOREIGN KEY(meta_id) REFERENCES attendance_meta(id)
        )
        """
    )
    conn.commit()
    conn.close()

def add_default_users():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    default_users = [
        ("fac1", hash_password("pass1"), "Faculty"),
        ("fac2", hash_password("pass2"), "Faculty"),
        ("fac3", hash_password("pass3"), "Faculty"),
        ("hod", hash_password("pass10"), "HOD"),
        ("admin", hash_password("admin123"), "Admin"),
        ("coord", hash_password("coord123"), "Coordinator"),
    ]
    for u, p, r in default_users:
        try:
            c.execute("INSERT INTO users(username,password_hash,role) VALUES (?,?,?)", (u, p, r))
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()

def check_user(username, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT password_hash, role FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    if not row:
        return False, None
    stored_hash, role = row
    return (stored_hash == hash_password(password)), role

def save_attendance_to_db(section, attendance_date, period, submitted_by, rows):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    created_at = datetime.now().isoformat()
    c.execute(
        "INSERT INTO attendance_meta(section,attendance_date,period,submitted_by,created_at) VALUES (?,?,?,?,?)",
        (section, str(attendance_date), str(period), submitted_by, created_at),
    )
    meta_id = c.lastrowid
    for r in rows:
        c.execute(
            "INSERT INTO attendance_rows(meta_id,regd_no,name,present,parent_name,parent_phone) VALUES (?,?,?,?,?,?)",
            (meta_id, r.get("Regd. No."), r.get("Name"), 1 if r.get("Present") else 0, r.get("Father Name", ""), r.get("Parent Ph.-1", "")),
        )
    conn.commit()
    conn.close()
    return meta_id

def get_attendance_meta_for_section(section):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT id, attendance_date, period, submitted_by, created_at FROM attendance_meta WHERE section=? ORDER BY attendance_date DESC, created_at DESC",
        (section,)
    )
    rows = c.fetchall()
    conn.close()
    return rows

def get_attendance_rows(meta_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT regd_no,name,present,parent_name,parent_phone FROM attendance_rows WHERE meta_id=?", (meta_id,))
    rows = c.fetchall()
    conn.close()
    return rows

# Initialize DB & defaults
init_db()
add_default_users()

# =========================
# Small helpers (table, kpi, celebrate)
# =========================
def render_table(df, key=None, height=460, fit_cols=True, editable=False, group_by=None, enable_sidebar=True):
    if not HAS_AGGRID:
        st.dataframe(df, use_container_width=True, height=height)
        return
    gob = GridOptionsBuilder.from_dataframe(df)
    gob.configure_default_column(resizable=True, filter=True, sortable=True)
    if editable:
        gob.configure_grid_options(editable=True)
    if group_by:
        for col in group_by:
            if col in df.columns:
                gob.configure_column(col, rowGroup=True, hide=True)
        gob.configure_grid_options(groupSelectsChildren=True, rowGroupPanelShow='always')
    if enable_sidebar:
        gob.configure_side_bar()
    grid_options = gob.build()
    AgGrid(
        df,
        gridOptions=grid_options,
        height=height,
        update_mode=GridUpdateMode.NO_UPDATE,
        enable_enterprise_modules=False,
        fit_columns_on_grid_load=fit_cols,
        key=key
    )

def kpi_row(title_left, value_left, delta_left,
            title_mid, value_mid, delta_mid,
            title_right, value_right, delta_right):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(title_left, value_left, delta=delta_left)
    with c2:
        st.metric(title_mid, value_mid, delta=delta_mid)
    with c3:
        st.metric(title_right, value_right, delta=delta_right)

def celebrate(event="success"):
    try:
        if event == "success":
            st.balloons()
        else:
            st.balloons()
    except Exception:
        pass

# =========================
# Visual Intro (optional)
# =========================
st.sidebar.markdown("---")
if HAS_LOTTIE:
    try:
        with open(os.path.join(BASE_DIR, "intro.json"), "r") as f:
            st_lottie(json.load(f), height=120, loop=True)
    except Exception:
        pass
else:
    st.sidebar.caption("Optional: add a Lottie animation (intro.json) next to app.py for a visual intro.")
st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)

# Quick message about Streamlit sleep policy (informational)
st.info(
    "Note: Streamlit Cloud (free) may put apps to sleep when idle. "
    "To keep the app always reachable consider using an uptime-monitoring service (UptimeRobot / Freshping) "
    "or host on an always-on provider (VPS / Render with paid plan / DigitalOcean)."
)

# =========================
# Session State (Auth)
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None

# =========================
# Auth Screen (ROLE FIRST)
# =========================
if not st.session_state.logged_in:
    with st.container():
        st.subheader("🔐 Login")
        selected_role = st.selectbox("Select Role", ["Faculty", "Coordinator", "HOD", "Admin"])
        cols = st.columns([1,2,1])
        with cols[1]:
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            if st.button("Login", use_container_width=True):
                ok, role_in_db = check_user(username.strip(), password)
                if not ok:
                    st.error("Invalid username or password.")
                elif role_in_db != selected_role:
                    st.error(f"Role mismatch: your account role is '{role_in_db}', not '{selected_role}'.")
                else:
                    st.session_state.logged_in = True
                    st.session_state.username = username.strip()
                    st.session_state.role = role_in_db
                    st.rerun()
    st.stop()

# =========================
# Sidebar
# =========================
st.sidebar.markdown(f"**👤 {st.session_state.username}**")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")
if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None
    st.rerun()

st.sidebar.markdown("---")
now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y — %I:%M %p")
st.sidebar.markdown(f"🕒 {now}")

# =========================
# Admin Panel
# =========================
if st.session_state.role == "Admin":
    st.header("⚙️ Admin Panel - User Management")
    conn = sqlite3.connect(DB_PATH)
    users_df = pd.read_sql_query("SELECT username, role FROM users", conn)
    conn.close()
    render_table(users_df, key="admin_users_grid")

    with st.expander("Add / Update User"):
        uname = st.text_input("Username", key="adm_user")
        pwd = st.text_input("Password", type="password", key="adm_pass")
        role = st.selectbox("Role", ["Faculty", "HOD", "Admin", "Coordinator"], key="adm_role")
        if st.button("Save User"):
            if uname and pwd:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                try:
                    c.execute("INSERT OR REPLACE INTO users(username,password_hash,role) VALUES (?,?,?)",
                              (uname.strip(), hash_password(pwd), role))
                    conn.commit()
                    st.success("User saved.")
                except Exception as e:
                    st.error(str(e))
                finally:
                    conn.close()
    st.stop()

# =========================
# Faculty Dashboard
# =========================
if st.session_state.role == "Faculty":
    st.header(f"📋 Faculty Dashboard ({st.session_state.username})")

    available_sections, missing_sections = [], []
    for canon in SECTION_CANONICALS:
        path = find_csv_for_section(canon)
        if path:
            available_sections.append(canon)
        else:
            missing_sections.append(canon)

    if not available_sections:
        st.warning("No section CSVs found in students_list/. Upload the missing sections below.")
    else:
        st.success(f"Sections ready: {', '.join(available_sections)}")

    if missing_sections:
        with st.expander("Upload missing section CSV(s)"):
            up_sec = st.selectbox("Select section to upload", missing_sections)
            uploaded = st.file_uploader("Upload CSV for the selected section", type=['csv'], key="upl_csv_missing")
            if uploaded and st.button("Save Section CSV"):
                save_name = primary_filename_for_canon(up_sec)
                save_path = os.path.join(STUDENTS_FOLDER, save_name)
                df_up = pd.read_csv(uploaded)
                df_up.to_csv(save_path, index=False)
                st.success(f"Saved {up_sec} → {save_name}. Refresh to load it.")
                st.stop()

    if not available_sections:
        st.stop()

    section = st.selectbox("Select Section", available_sections)
    student_file = find_csv_for_section(section)

    search_query = st.text_input("🔎 Search student by Name or Regd.")
    period = st.selectbox("Select Period", ["1","2","3","4","5","6"], index=0)
    attendance_date = st.date_input("Select Date", date.today())

    col_choice = st.radio("Card columns (mobile friendly)", options=[1, 2, 4], index=1, horizontal=True)
    cols_per_row = col_choice

    if not student_file or not os.path.exists(student_file):
        st.error(f"CSV not found for {section}. Place the CSV in {STUDENTS_FOLDER}/")
        st.stop()

    students = pd.read_csv(student_file)
    students.columns = students.columns.str.strip()
    req_cols = ["Regd. No.", "Name"]
    for rc in req_cols:
        if rc not in students.columns:
            st.error(f"CSV for {section} must have columns: {', '.join(req_cols)} (and optional Father Name, Parent Ph.-1).")
            st.stop()

    if search_query:
        students = students[students.apply(
            lambda r: search_query.lower() in str(r.get('Name', '')).lower() or
                      search_query.lower() in str(r.get('Regd. No.', '')).lower(),
            axis=1
        )]

    roll_col = "Regd. No."
    name_col = "Name"

    key_base = f"attendance_{section}_{period}_{attendance_date}"
    if key_base not in st.session_state:
        st.session_state[key_base] = {row[roll_col]: True for _, row in students.iterrows()}

    st.subheader(f"🗓️ Mark Attendance: {section} — Period {period} — {attendance_date}")
    c1, c2, c3 = st.columns([1,1,1])
    if c1.button("✅ Mark All Present"):
        for r in st.session_state[key_base]:
            st.session_state[key_base][r] = True
    if c2.button("❌ Mark All Absent"):
        for r in st.session_state[key_base]:
            st.session_state[key_base][r] = False
    if c3.button("⏪ Prefill from Previous"):
        prev_date = attendance_date - timedelta(days=1)
        prev_key = f"attendance_{section}_{period}_{prev_date}"
        if prev_key in st.session_state:
            st.session_state[key_base] = st.session_state[prev_key].copy()
            st.success("Prefilled from previous day.")
        else:
            st.info("No previous attendance found in session.")

    st.markdown("---")

    # Card toggles
    rows_chunks = [students[i:i+cols_per_row] for i in range(0, len(students), cols_per_row)]
    for row_students in rows_chunks:
        cols = st.columns(cols_per_row)
        for col, (_, student) in zip(cols, row_students.iterrows()):
            roll = student[roll_col]
            name = student[name_col]
            is_present = st.session_state[key_base].get(roll, True)
            with col:
                st.markdown(
                    f"<div class='attn-card'>"
                    f"<div style='font-weight:700'>{roll}</div>"
                    f"<div style='font-weight:600'>{name}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                toggle_val = st.toggle(
                    label="Present",
                    value=is_present,
                    key=f"{key_base}_{roll}_toggle",
                )
                st.session_state[key_base][roll] = toggle_val

    st.markdown("---")
    present_count = sum(1 for v in st.session_state[key_base].values() if v)
    total_students = len(st.session_state[key_base]) if st.session_state[key_base] else 0
    pct = (present_count/total_students*100) if total_students else 0.0

    kpi_row("Present", f"{present_count}", f"{pct:.1f}%",
            "Total", f"{total_students}", "class size",
            "Absent", f"{total_students - present_count}", f"{100-pct:.1f}%")

    if st.button("📤 Submit Attendance", use_container_width=True):
        absent_list, rows_to_save = [], []
        full_df = pd.read_csv(student_file)
        full_df.columns = full_df.columns.str.strip()
        for _, row in full_df.iterrows():
            rno = row.get(roll_col)
            present = st.session_state[key_base].get(rno, False)
            rows_to_save.append({
                "Regd. No.": rno,
                "Name": row.get(name_col, ""),
                "Present": present,
                "Father Name": row.get("Father Name", ""),
                "Parent Ph.-1": row.get("Parent Ph.-1", "")
            })
            if not present:
                absent_list.append([
                    rno,
                    row.get(name_col, ""),
                    row.get("Father Name", ""),
                    row.get("Parent Ph.-1", "")
                ])

        _ = save_attendance_to_db(section, attendance_date, period, st.session_state.username, rows_to_save)

        section_folder = os.path.join(ATTENDANCE_FOLDER, section)
        os.makedirs(section_folder, exist_ok=True)
        file_path = os.path.join(
            section_folder,
            f"absentees_{attendance_date}_period{period}_by_{st.session_state.username}.csv"
        )
        df_absent = (
            pd.DataFrame(absent_list, columns=[roll_col, name_col, "Father Name", "Parent Ph.-1"])
            if absent_list else
            pd.DataFrame([["All present", "", "", ""]], columns=[roll_col, name_col, "Father Name", "Parent Ph.-1"])
        )
        header_info = pd.DataFrame(
            [["Section", section],["Date", str(attendance_date)],["Period", period],["Submitted By", st.session_state.username]],
            columns=["Field","Value"]
        )
        with open(file_path, 'w', newline='') as f:
            header_info.to_csv(f, index=False); f.write('\n'); df_absent.to_csv(f, index=False)

        st.success("✅ Attendance submitted and saved.")
        celebrate("success")

# =========================
# HOD Dashboard (NO charts/heatmaps)
# =========================
elif st.session_state.role == "HOD":
    st.header("🏫 HOD Dashboard — Absentees & Reports")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT section FROM attendance_meta ORDER BY section")
    sections_db = [r[0] for r in c.fetchall()]
    conn.close()

    if not sections_db:
        st.info("No attendance data found yet.")
        st.stop()

    section = st.selectbox("Select Section", sections_db)

    # Quick Student % Lookup (no charts)
    with st.expander("🔎 Quick Student Attendance % Lookup"):
        q = st.text_input("Search by Name or Regd. No.")
        colx, coly = st.columns(2)
        with colx:
            start_q = st.date_input("Start (optional)", value=None, key="hod_q_start")
        with coly:
            end_q = st.date_input("End (optional)", value=None, key="hod_q_end")

        if start_q and end_q and start_q > end_q:
            st.error("Start must be before or equal to End.")
        elif q:
            student_file = find_csv_for_section(section)
            if not student_file or not os.path.exists(student_file):
                st.warning("Student list CSV not found for this section.")
            else:
                sdf = pd.read_csv(student_file)
                sdf.columns = sdf.columns.str.strip()
                sdf["Regd. No."] = sdf["Regd. No."].astype(str)
                name_mask = sdf["Name"].astype(str).str.lower().str.contains(q.strip().lower())
                regd_mask = sdf["Regd. No."].str.lower().str.contains(q.strip().lower())
                matches = sdf[name_mask | regd_mask].copy()

                if matches.empty:
                    st.info("No matching student found in the section CSV.")
                else:
                    def fetch_metas(sec, s=None, e=None):
                        conn = sqlite3.connect(DB_PATH)
                        cur = conn.cursor()
                        if s and e:
                            cur.execute(
                                "SELECT id, attendance_date, period FROM attendance_meta "
                                "WHERE section=? AND attendance_date BETWEEN ? AND ? "
                                "ORDER BY attendance_date, period",
                                (sec, str(s), str(e))
                            )
                        else:
                            cur.execute(
                                "SELECT id, attendance_date, period FROM attendance_meta "
                                "WHERE section=? ORDER BY attendance_date, period",
                                (sec,)
                            )
                        out = cur.fetchall()
                        conn.close()
                        return out

                    metas = fetch_metas(section, start_q, end_q) if (start_q and end_q) else fetch_metas(section)
                    if not metas:
                        st.info("No attendance sessions in this timeframe.")
                    else:
                        meta_ids = [m[0] for m in metas]
                        total_classes = len(meta_ids)
                        conn = sqlite3.connect(DB_PATH)
                        cur = conn.cursor()
                        placeholders = ",".join(["?"] * len(meta_ids))
                        results = []
                        for _, row in matches.iterrows():
                            regd = str(row["Regd. No."])
                            cur.execute(
                                f"SELECT SUM(CASE WHEN present=1 THEN 1 ELSE 0 END) "
                                f"FROM attendance_rows WHERE regd_no=? AND meta_id IN ({placeholders})",
                                tuple([regd] + meta_ids)
                            )
                            presents = cur.fetchone()[0] or 0
                            pct = round((presents / total_classes * 100), 2) if total_classes else 0.0
                            results.append([regd, row["Name"], presents, total_classes, total_classes - presents, pct])
                        conn.close()

                        out_df = pd.DataFrame(
                            results,
                            columns=["Regd. No.", "Name", "Presents", "Total Classes", "Absences", "% Attendance"]
                        ).sort_values("% Attendance", ascending=True)

                        render_table(out_df, key="hod_quick_lookup")
                        towrite = BytesIO()
                        out_df.to_excel(towrite, index=False, sheet_name="student_percent_lookup")
                        towrite.seek(0)
                        st.download_button(
                            "📥 Download Lookup (Excel)",
                            towrite,
                            file_name=f"student_percent_lookup_{section}.xlsx"
                        )

    main_mode = st.selectbox("Choose Report Area", [
        "Single Record (saved attendance)",
        "Aggregated: All Periods on a Date",
        "Aggregated: Date Range",
        "Daily Report",
        "Weekly Report (7 days)",
        "Monthly Report",
        "Individual Student Report",
        "Attendance % (Date Range)",
    ])

    def fetch_metas_for_section(sec, start=None, end=None):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if start and end:
            c.execute(
                "SELECT id, attendance_date, period, submitted_by "
                "FROM attendance_meta WHERE section=? AND attendance_date BETWEEN ? AND ? "
                "ORDER BY attendance_date, period",
                (sec, str(start), str(end))
            )
        else:
            c.execute(
                "SELECT id, attendance_date, period, submitted_by "
                "FROM attendance_meta WHERE section=? "
                "ORDER BY attendance_date DESC, created_at DESC",
                (sec,)
            )
        metas = c.fetchall()
        conn.close()
        return metas

    def aggregated_absentees_from_meta_ids(meta_list):
        if not meta_list:
            return pd.DataFrame()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        q = f"SELECT meta_id, regd_no, name, parent_name, parent_phone FROM attendance_rows WHERE present=0 AND meta_id IN ({','.join('?'*len(meta_list))})"
        c.execute(q, tuple(meta_list))
        rows = c.fetchall()
        conn.close()
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=["meta_id","Regd. No.","Name","Parent Name","Parent Phone"])
        return df

    if main_mode == "Single Record (saved attendance)":
        metas = fetch_metas_for_section(section)
        if not metas:
            st.info("No saved attendance records for this section.")
        else:
            meta_map = {f"{m[1]} | Period {m[2]} | by {m[3]} (id:{m[0]})": m[0] for m in metas}
            sel_key = st.selectbox("Select Attendance Record", list(meta_map.keys()))
            sel_mid = meta_map[sel_key]
            if st.button("📋 Show Absentees (Single)"):
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("SELECT regd_no, name, parent_name, parent_phone FROM attendance_rows WHERE meta_id=? AND present=0", (sel_mid,))
                rows = c.fetchall()
                conn.close()
                if rows:
                    df_abs = pd.DataFrame(rows, columns=["Regd. No.", "Name", "Parent Name", "Parent Phone"])
                    st.subheader("❌ Absentees (Selected Record)")
                    render_table(df_abs, key="hod_single")
                    towrite = BytesIO()
                    df_abs.to_excel(towrite, index=False, sheet_name='absentees_single')
                    towrite.seek(0)
                    st.download_button("📥 Download (Excel)", towrite, file_name=f"absentees_single_{sel_mid}.xlsx")
                else:
                    st.success("🎉 All present in selected record.")

    elif main_mode == "Aggregated: All Periods on a Date":
        agg_date = st.date_input("Select Date to aggregate", date.today())
        if st.button("📋 Show Aggregated Absentees (Date)"):
            metas = fetch_metas_for_section(section, start=agg_date, end=agg_date)
            if not metas:
                st.info("No records for selected date.")
            else:
                meta_ids = [m[0] for m in metas]
                df = aggregated_absentees_from_meta_ids(meta_ids)
                if df.empty:
                    st.success("🎉 No absentees on this date.")
                else:
                    meta_map = {m[0]: {"period": m[2], "date": m[1]} for m in metas}
                    df['Period_Date'] = df['meta_id'].map(lambda x: f"P{meta_map[x]['period']} ({meta_map[x]['date']})")
                    df_group = df.groupby(["Regd. No.","Name","Parent Name","Parent Phone"], as_index=False).agg({
                        'Period_Date': lambda s: ', '.join(sorted(set(s))),
                        'meta_id': 'count'
                    }).rename(columns={'meta_id': 'Absence Count'})
                    df_group = df_group[["Regd. No.","Name","Parent Name","Parent Phone","Period_Date","Absence Count"]].sort_values("Absence Count", ascending=False).reset_index(drop=True)
                    st.subheader(f"❌ Aggregated Absentees for {agg_date}")
                    render_table(df_group, key="hod_agg_date", group_by=["Regd. No.","Name"])
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='agg_date')
                    towrite.seek(0)
                    st.download_button("📥 Download Aggregated (Excel)", towrite, file_name=f"aggregated_{section}_{agg_date}.xlsx")

    elif main_mode == "Aggregated: Date Range":
        col1, col2 = st.columns(2)
        with col1:
            start_d = st.date_input("Start Date", date.today() - timedelta(days=7))
        with col2:
            end_d = st.date_input("End Date", date.today())
        if start_d > end_d:
            st.error("Start Date must be before or equal to End Date.")
        else:
            if st.button("📋 Show Aggregated Absentees (Range)"):
                metas = fetch_metas_for_section(section, start=start_d, end=end_d)
                if not metas:
                    st.info("No records in this date range.")
                else:
                    meta_ids = [m[0] for m in metas]
                    df = aggregated_absentees_from_meta_ids(meta_ids)
                    if df.empty:
                        st.success("🎉 No absentees in range.")
                    else:
                        meta_map = {m[0]: {"period": m[2], "date": m[1]} for m in metas}
                        df['Period_Date'] = df['meta_id'].map(lambda x: f"P{meta_map[x]['period']} ({meta_map[x]['date']})")
                        df_group = df.groupby(["Regd. No.","Name","Parent Name","Parent Phone"], as_index=False).agg({
                            'Period_Date': lambda s: ', '.join(sorted(set(s))),
                            'meta_id': 'count'
                        }).rename(columns={'meta_id': 'Absence Count'})
                        df_group = df_group[["Regd. No.","Name","Parent Name","Parent Phone","Period_Date","Absence Count"]].sort_values("Absence Count", ascending=False).reset_index(drop=True)
                        st.subheader(f"❌ Aggregated Absentees {start_d} → {end_d}")
                        render_table(df_group, key="hod_agg_range", group_by=["Regd. No.","Name"])
                        towrite = BytesIO()
                        df_group.to_excel(towrite, index=False, sheet_name='agg_range')
                        towrite.seek(0)
                        st.download_button("📥 Download Aggregated (Excel)", towrite, file_name=f"aggregated_{section}_{start_d}_to_{end_d}.xlsx")

    elif main_mode == "Daily Report":
        daily_date = st.date_input("Select Date (Daily Report)", date.today())
        if st.button("📋 Show Daily Absentees"):
            metas = fetch_metas_for_section(section, start=daily_date, end=daily_date)
            if not metas:
                st.info("No attendance records on this date.")
            else:
                meta_ids = [m[0] for m in metas]
                df = aggregated_absentees_from_meta_ids(meta_ids)
                if df.empty:
                    st.success("🎉 No absentees on this date.")
                else:
                    meta_map = {m[0]: {"period": m[2], "date": m[1]} for m in metas}
                    df['Period_Date'] = df['meta_id'].map(lambda x: f"P{meta_map[x]['period']}")
                    df_group = df.groupby(["Regd. No.","Name","Parent Name","Parent Phone"], as_index=False).agg({
                        'Period_Date': lambda s: ', '.join(sorted(set(s))),
                        'meta_id': 'count'
                    }).rename(columns={'meta_id': 'Absence Count'})
                    df_group = df_group[["Regd. No.","Name","Parent Name","Parent Phone","Period_Date","Absence Count"]].sort_values("Absence Count", ascending=False).reset_index(drop=True)
                    st.subheader(f"📅 Daily Absentees on {daily_date}")
                    render_table(df_group, key="hod_daily")
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='daily')
                    towrite.seek(0)
                    st.download_button("📥 Download Daily (Excel)", towrite, file_name=f"daily_absentees_{section}_{daily_date}.xlsx")

    elif main_mode == "Weekly Report (7 days)":
        week_anchor = st.date_input("Pick a date (week shown will be that date - 6 days → date)", date.today())
        start_week = week_anchor - timedelta(days=6)
        end_week = week_anchor
        st.info(f"Showing absentees from {start_week} to {end_week}")
        if st.button("📋 Show Weekly Absentees"):
            metas = fetch_metas_for_section(section, start=start_week, end=end_week)
            if not metas:
                st.info("No attendance records in this week.")
            else:
                meta_ids = [m[0] for m in metas]
                df = aggregated_absentees_from_meta_ids(meta_ids)
                if df.empty:
                    st.success("🎉 No absentees in this week.")
                else:
                    meta_map = {m[0]: {"period": m[2], "date": m[1]} for m in metas}
                    df['Period_Date'] = df['meta_id'].map(lambda x: f"{meta_map[x]['date']} P{meta_map[x]['period']}")
                    df_group = df.groupby(["Regd. No.","Name","Parent Name","Parent Phone"], as_index=False).agg({
                        'Period_Date': lambda s: ', '.join(sorted(set(s))),
                        'meta_id': 'count'
                    }).rename(columns={'meta_id': 'Absence Count'})
                    df_group = df_group[["Regd. No.","Name","Parent Name","Parent Phone","Period_Date","Absence Count"]].sort_values("Absence Count", ascending=False).reset_index(drop=True)
                    st.subheader(f"📆 Weekly Absentees {start_week} → {end_week}")
                    render_table(df_group, key="hod_weekly")
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='weekly')
                    towrite.seek(0)
                    st.download_button("📥 Download Weekly (Excel)", towrite, file_name=f"weekly_absentees_{section}_{start_week}_to_{end_week}.csv")

    elif main_mode == "Monthly Report":
        any_date_in_month = st.date_input("Pick any date in the month to report", date.today())
        month_start = any_date_in_month.replace(day=1)
        if month_start.month == 12:
            next_month_start = month_start.replace(year=month_start.year+1, month=1, day=1)
        else:
            next_month_start = month_start.replace(month=month_start.month+1, day=1)
        month_end = next_month_start - timedelta(days=1)
        st.info(f"Showing absentees for {month_start.strftime('%B %Y')} ({month_start} → {month_end})")
        if st.button("📋 Show Monthly Absentees"):
            metas = fetch_metas_for_section(section, start=month_start, end=month_end)
            if not metas:
                st.info("No attendance records in this month.")
            else:
                meta_ids = [m[0] for m in metas]
                df = aggregated_absentees_from_meta_ids(meta_ids)
                if df.empty:
                    st.success("🎉 No absentees in this month.")
                else:
                    meta_map = {m[0]: {"period": m[2], "date": m[1]} for m in metas}
                    df['Period_Date'] = df['meta_id'].map(lambda x: f"{meta_map[x]['date']} P{meta_map[x]['period']}")
                    df_group = df.groupby(["Regd. No.","Name","Parent Name","Parent Phone"], as_index=False).agg({
                        'Period_Date': lambda s: ', '.join(sorted(set(s))),
                        'meta_id': 'count'
                    }).rename(columns={'meta_id': 'Absence Count'})
                    df_group = df_group[["Regd. No.","Name","Parent Name","Parent Phone","Period_Date","Absence Count"]].sort_values("Absence Count", ascending=False).reset_index(drop=True)
                    st.subheader(f"🗓️ Monthly Absentees: {month_start.strftime('%B %Y')}")
                    render_table(df_group, key="hod_monthly")
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='monthly')
                    towrite.seek(0)
                    st.download_button("📥 Download Monthly (Excel)", towrite, file_name=f"monthly_absentees_{section}_{month_start.year}_{month_start.month}.csv")

    elif main_mode == "Individual Student Report":
        student_file = find_csv_for_section(section)
        if not student_file or not os.path.exists(student_file):
            st.warning("Student list CSV not found for this section (checked aliases too). Please place the CSV in students_list/.")
        else:
            students_df = pd.read_csv(student_file)
            students_df.columns = students_df.columns.str.strip()
            if "Regd. No." not in students_df.columns or "Name" not in students_df.columns:
                st.error("CSV must have columns: Regd. No., Name (and optional Father Name, Parent Ph.-1).")
            else:
                students_df['label'] = students_df['Regd. No.'].astype(str) + " | " + students_df['Name'].astype(str)
                sel = st.selectbox("Select Student", students_df['label'].tolist())
                sel_regd = sel.split("|")[0].strip()
                student_mode = st.selectbox("Select Timeframe for Student Report", ["Daily", "Weekly (7 days)", "Monthly", "Custom Range"])
                if student_mode == "Daily":
                    start = end = st.date_input("Select Date (Student - Daily)", date.today())
                elif student_mode == "Weekly (7 days)":
                    anchor = st.date_input("Pick a date; week = date -6 → date", date.today())
                    start = anchor - timedelta(days=6); end = anchor
                    st.info(f"Week: {start} → {end}")
                elif student_mode == "Monthly":
                    any_date_m = st.date_input("Pick a date in the month", date.today())
                    start = any_date_m.replace(day=1)
                    if start.month == 12:
                        nm = start.replace(year=start.year+1, month=1, day=1)
                    else:
                        nm = start.replace(month=start.month+1, day=1)
                    end = nm - timedelta(days=1)
                    st.info(f"Month: {start.strftime('%B %Y')} ({start} → {end})")
                else:
                    c1, c2 = st.columns(2)
                    with c1: start = st.date_input("Custom Start Date", date.today() - timedelta(days=7))
                    with c2: end = st.date_input("Custom End Date", date.today())
                    if start > end:
                        st.error("Start must be <= End")

                if start and end:
                    if st.button("📋 Show Student Report"):
                        metas = fetch_metas_for_section(section, start=start, end=end)
                        if not metas:
                            st.info("No attendance records found in this timeframe.")
                        else:
                            meta_ids = [m[0] for m in metas]
                            conn = sqlite3.connect(DB_PATH)
                            c = conn.cursor()
                            q = f"SELECT meta_id, regd_no, name, parent_name, parent_phone FROM attendance_rows WHERE present=0 AND regd_no=? AND meta_id IN ({','.join('?'*len(meta_ids))})"
                            params = tuple([sel_regd] + meta_ids)
                            c.execute(q, params)
                            rows = c.fetchall()
                            conn.close()

                            if not rows:
                                st.success("🎉 Student had no absences in this timeframe.")
                                st.markdown(f"**Student:** {sel_regd} — {students_df.loc[students_df['Regd. No.'].astype(str)==sel_regd, 'Name'].values[0]}")
                                st.markdown("**Absences in timeframe:** 0")
                            else:
                                meta_map = {m[0]: {"date": m[1], "period": m[2]} for m in metas}
                                df = pd.DataFrame(rows, columns=["meta_id","Regd. No.","Name","Parent Name","Parent Phone"])
                                df['Date'] = df['meta_id'].map(lambda x: meta_map[x]['date'])
                                df['Period'] = df['meta_id'].map(lambda x: meta_map[x]['period'])
                                df = df[["Regd. No.","Name","Date","Period","Parent Name","Parent Phone"]].sort_values(["Date","Period"]).reset_index(drop=True)
                                st.subheader(f"👤 Absence details: {sel_regd}")
                                render_table(df, key="hod_student_detail")
                                st.markdown(f"**Total Absences:** {len(df)}")
                                towrite = BytesIO()
                                df.to_excel(towrite, index=False, sheet_name='student_absences')
                                towrite.seek(0)
                                st.download_button("📥 Download Student Report (Excel)", towrite, file_name=f"student_{sel_regd}_{start}_to_{end}.xlsx")

    elif main_mode == "Attendance % (Date Range)":
        c1, c2 = st.columns(2)
        with c1:
            start_d = st.date_input("Start Date", date.today() - timedelta(days=30))
        with c2:
            end_d = st.date_input("End Date", date.today())
        if start_d > end_d:
            st.error("Start Date must be before or equal to End Date.")
            st.stop()

        metas = fetch_metas_for_section(section, start=start_d, end=end_d)
        if not metas:
            st.info("No attendance sessions in this date range.")
            st.stop()

        meta_ids = [m[0] for m in metas]
        total_classes = len(meta_ids)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        q = f"""
            SELECT regd_no, name, SUM(CASE WHEN present=1 THEN 1 ELSE 0 END) as presents
            FROM attendance_rows
            WHERE meta_id IN ({','.join('?'*len(meta_ids))})
            GROUP BY regd_no, name
        """
        c.execute(q, tuple(meta_ids))
        rows = c.fetchall()
        conn.close()

        if not rows:
            st.info("No attendance rows found for this range.")
            st.stop()

        df = pd.DataFrame(rows, columns=["Regd. No.", "Name", "Presents"])
        df["Total Classes"] = total_classes
        df["Absences"] = df["Total Classes"] - df["Presents"]
        df["% Attendance"] = (df["Presents"] / df["Total Classes"] * 100).round(2)

        student_file = find_csv_for_section(section)
        if student_file and os.path.exists(student_file):
            base_students = pd.read_csv(student_file)[["Regd. No.", "Name"]]
            merged = base_students.merge(
                df,
                on=["Regd. No.", "Name"],
                how="left"
            ).fillna({
                "Presents": 0,
                "Absences": total_classes,
                "Total Classes": total_classes,
                "% Attendance": 0
            })
            df = merged

        st.subheader(f"📊 Attendance % — {section}  ({start_d} → {end_d})")
        render_table(df.sort_values("% Attendance"), key="hod_pct_table")

        towrite = BytesIO()
        df.to_excel(towrite, index=False, sheet_name="attendance_percent")
        towrite.seek(0)
        st.download_button(
            "📥 Download Attendance % (Excel)",
            towrite,
            file_name=f"attendance_percent_{section}_{start_d}_to_{end_d}.xlsx"
        )

# ======================
# Coordinator Dashboard
# ======================
elif st.session_state.role == "Coordinator":
    st.header("👥 Coordinator Dashboard — Absentees (Read-only)")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT section FROM attendance_meta ORDER BY section")
    sections_db = [r[0] for r in c.fetchall()]
    conn.close()

    if not sections_db:
        st.info("No attendance data found yet.")
        st.stop()

    section = st.selectbox("Select Section", sections_db)

    col1, col2 = st.columns(2)
    with col1:
        start_d = st.date_input("Start Date", date.today() - timedelta(days=7))
    with col2:
        end_d = st.date_input("End Date", date.today())
    if start_d > end_d:
        st.error("Start Date must be before or equal to End Date.")
        st.stop()

    def _fetch_metas(sec, start, end):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT id, attendance_date, period, submitted_by FROM attendance_meta "
            "WHERE section=? AND attendance_date BETWEEN ? AND ? ORDER BY attendance_date, period",
            (sec, str(start), str(end)),
        )
        metas_ = c.fetchall()
        conn.close()
        return metas_

    metas = _fetch_metas(section, start_d, end_d)
    if not metas:
        st.info("No attendance records in this range.")
        st.stop()

    meta_ids = [m[0] for m in metas]
    meta_map = {m[0]: {"date": m[1], "period": m[2]} for m in metas}

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    q = f"""
        SELECT meta_id, regd_no, name, parent_name, parent_phone
        FROM attendance_rows
        WHERE present=0 AND meta_id IN ({','.join('?'*len(meta_ids))})
    """
    c.execute(q, tuple(meta_ids))
    rows = c.fetchall()
    conn.close()

    if not rows:
        st.success("🎉 No absentees in this date range.")
        st.stop()

    df = pd.DataFrame(rows, columns=["meta_id", "Regd. No.", "Name", "Parent Name", "Parent Phone"])
    df["Period"] = df["meta_id"].map(lambda x: meta_map[x]["period"])
    df["Date"] = df["meta_id"].map(lambda x: meta_map[x]["date"])
    df["Period"] = df["Period"].astype(str)

    base_group_cols = ["Regd. No.", "Name", "Parent Name", "Parent Phone"]
    pivot = (
        df.groupby(base_group_cols + ["Period"])
          .size()
          .unstack("Period", fill_value=0)
    )
    for p in ["1","2","3","4","5","6"]:
        if p not in pivot.columns:
            pivot[p] = 0
    pivot = pivot[["1","2","3","4","5","6"]]
    pivot.columns = [f"P{c}" for c in pivot.columns]
    pivot = pivot.reset_index()

    df["Date-Period"] = df.apply(lambda r: f"{r['Date']} (P{r['Period']})", axis=1)
    compact = (
        df.groupby(base_group_cols, as_index=False)
          .agg({"Date-Period": lambda s: ", ".join(sorted(set(s)))})
          .rename(columns={"Date-Period": "Periods Absent"})
    )

    agg = pivot.merge(compact, on=base_group_cols, how="left")
    period_cols = ["P1","P2","P3","P4","P5","P6"]
    agg["Absence Count"] = agg[period_cols].sum(axis=1)
    agg = agg.loc[:, base_group_cols + period_cols + ["Absence Count", "Periods Absent"]] \
             .sort_values(["Absence Count", "Regd. No."], ascending=[False, True]) \
             .reset_index(drop=True)

    st.subheader(f"❌ Absentees — {section} ({start_d} → {end_d})")
    render_table(agg, key="coord_abs_grid")

    csv_bytes = agg.to_csv(index=False).encode("utf-8")
    st.download_button(
        "📥 Download Absentees (CSV)",
        csv_bytes,
        file_name=f"absentees_{section}_{start_d}_to_{end_d}.csv",
        mime="text/csv"
    )

# =========================
# Generic fallback
# =========================
else:
    st.info("Your role does not have a specific dashboard yet.")
