import streamlit as st
import pandas as pd
import os
import sqlite3
from datetime import date, datetime, timedelta
from io import BytesIO
import hashlib

# ------------------------
# Configuration
# ------------------------
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_TITLE = "SJCET - AttendPro (Advanced)"

# Candidates (both common layouts)
CANDIDATE_STUDENTS_DIRS = [
    os.path.join(BASE_DIR, "students_list"),                      # app.py and folder at repo root
    os.path.join(BASE_DIR, "sjcet-attendpro", "students_list"),   # app.py at root, folder inside subdir
]

# Pick the first that exists; otherwise create the first path
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

# --- (Optional) debug: see what the server actually sees. Remove later. ---
import glob
try:
    import streamlit as st  # already imported above, but safe if moved
except Exception:
    pass
# ------------------------
# Section name normalization / alias resolver
# ------------------------
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
    # II-CSE_A
    _loose_key("II-CSE_A"): "II-CSE_A",
    _loose_key("II CSE A"): "II-CSE_A",
    _loose_key("II-CSE.A"): "II-CSE_A",

    # II-CSE_B
    _loose_key("II-CSE_B"): "II-CSE_B",
    _loose_key("II CSE B"): "II-CSE_B",
    _loose_key("II-CSE.B"): "II-CSE_B",

    # II-CSE_C
    _loose_key("II-CSE_C"): "II-CSE_C",
    _loose_key("II CSE C"): "II-CSE_C",
    _loose_key("II-CSE.C"): "II-CSE_C",

    # II-CSD (CSE-DS)
    _loose_key("II-CSD"):   "II-CSD",
    _loose_key("CSE_DS"):   "II-CSD",
    _loose_key("CSE.DS"):   "II-CSD",
    _loose_key("II-CSE_DS"):"II-CSD",
    _loose_key("II-CSE.DS"):"II-CSD",
    _loose_key("II CSE DS"):"II-CSD",

    # III-CSE
    _loose_key("III-CSE"):  "III-CSE",
    _loose_key("III CSE"):  "III-CSE",

    # III-CSD
    _loose_key("III-CSD"):  "III-CSD",
    _loose_key("III CSD"):  "III-CSD",
    _loose_key("lll-CSD"):  "III-CSD",  # uploaded alias
}

# Preferred filenames per canonical section (first item is the canonical save name)
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

# ------------------------
# Utility Functions
# ------------------------
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
        ("admin", hash_password("admin123"), "Admin")
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

# ------------------------
# Initialize DB & defaults
# ------------------------
init_db()
add_default_users()

# ------------------------
# Streamlit App Layout
# ------------------------
st.set_page_config(page_title=APP_TITLE, layout="wide")

# ---- Global UI polish: gradient background, softer cards, mobile tweaks ----
APP_CSS = """
<style>
/* Full app background gradient */
[data-testid="stAppViewContainer"] {
  background: radial-gradient(1200px circle at 12% 8%, #0c555a 0%, #0a3f49 35%, #072a34 100%) !important;
}
/* Transparent header so gradient shows */
[data-testid="stHeader"] { background: rgba(0,0,0,0) !important; }
/* Slightly tighter padding */
.block-container { padding-top: 1.2rem; }
/* Buttons: rounded & bold */
.stButton>button {
  border-radius: 12px !important;
  font-weight: 600 !important;
}
/* Attendance card look (CONSTANT border color) */
.attn-card {
  border-radius: 12px;
  padding: 10px 8px;
  border: 2px solid #4f6b6d;   /* constant neutral border */
  text-align: center;
  background: rgba(255,255,255,0.02);
  backdrop-filter: blur(2px);
}
/* Compact toggle label under the card */
.stToggle { text-align: center; margin-top: 6px !important; }
.stToggle label { font-size: 0.9rem !important; font-weight: 600 !important; }

/* Title */
.centered-title {
  text-align: center;
  font-weight: 800;
  font-size: clamp(1.4rem, 2.6vw, 2.0rem);
  margin: 0.5rem 0 1rem 0;
}
/* Dataframes spacing */
[data-testid="stDataFrame"] div[data-testid="stHorizontalBlock"] {
  row-gap: 0.25rem !important;
}
/* Mobile tweaks */
@media (max-width: 640px) {
  .block-container { padding-left: 0.6rem; padding-right: 0.6rem; }
  .centered-title { font-size: 1.3rem; }
  .stButton>button { width: 100% !important; }
  .attn-card { font-size: 0.95rem; padding: 8px 6px; }
}
</style>
"""
st.markdown(APP_CSS, unsafe_allow_html=True)
st.markdown(f"<div class=\"centered-title\">🎓 {APP_TITLE}</div>", unsafe_allow_html=True)

# ------------------------
# Session State
# ------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None

# ------------------------
# Authentication
# ------------------------
if not st.session_state.logged_in:
    with st.container():
        st.subheader("🔐 Login")
        cols = st.columns([1,2,1])
        with cols[1]:
            username = st.text_input("Username", placeholder="Enter username")
            password = st.text_input("Password", type="password", placeholder="Enter password")
            if st.button("Login", use_container_width=True):
                ok, role = check_user(username.strip(), password)
                if ok:
                    st.session_state.logged_in = True
                    st.session_state.username = username.strip()
                    st.session_state.role = role
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
    st.stop()

# ------------------------
# Sidebar (Profile + Logout)
# ------------------------
st.sidebar.markdown(f"**👤 {st.session_state.username}**")
st.sidebar.markdown(f"**Role:** {st.session_state.role}")
if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.role = None
    st.rerun()

st.sidebar.markdown("---")

# ✅ Local timezone (India)
from datetime import datetime
from zoneinfo import ZoneInfo
now = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y — %I:%M %p")
st.sidebar.markdown(f"🕒 {now}")

# ------------------------
# Admin Panel
# ------------------------
if st.session_state.role == "Admin":
    st.header("⚙️ Admin Panel - User Management")
    conn = sqlite3.connect(DB_PATH)
    users_df = pd.read_sql_query("SELECT username, role FROM users", conn)
    conn.close()
    st.dataframe(users_df, use_container_width=True)

    with st.expander("Add / Update User"):
        uname = st.text_input("Username", key="adm_user")
        pwd = st.text_input("Password", type="password", key="adm_pass")
        role = st.selectbox("Role", ["Faculty", "HOD", "Admin"], key="adm_role")
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
                    st.error(e)
                finally:
                    conn.close()
    st.stop()

# ------------------------
# Faculty Dashboard  (fixed six sections + alias resolver + 6 periods + mobile grid)
# ------------------------
if st.session_state.role == "Faculty":
    st.header(f"📋 Faculty Dashboard ({st.session_state.username})")

    # Determine available vs missing canonical sections based on files present (via resolver)
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

    # Upload helper for any missing section
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

    # Section selector from available canonicals
    section = st.selectbox("Select Section", available_sections)

    # Resolve actual CSV file for this section (aliases supported)
    student_file = find_csv_for_section(section)

    search_query = st.text_input("🔎 Search student by Name or Regd.")
    period = st.selectbox("Select Period", ["1","2","3","4","5","6"], index=0)  # keep 6 periods
    attendance_date = st.date_input("Select Date", date.today())

    # Mobile-friendly grid: let user choose columns (good on phones)
    col_choice = st.radio(
        "Card columns (mobile friendly)",
        options=[1, 2, 4],
        index=1,  # default = 2
        horizontal=True
    )
    cols_per_row = col_choice

    # Load students CSV
    if not student_file or not os.path.exists(student_file):
        st.error(f"CSV not found for {section}. Place the CSV in {STUDENTS_FOLDER}/")
        st.stop()

    students = pd.read_csv(student_file)
    students.columns = students.columns.str.strip()

    # Basic validation
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

    # --- Cards with TOGGLE (constant color; no red/green logic) ---
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
                # Toggle switch
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
    st.info(f"✅ Summary: {present_count}/{total_students} present — {pct:.1f}%")

    if st.button("📤 Submit Attendance", use_container_width=True):
        absent_list, rows_to_save = [], []
        # iterate over original full CSV (not filtered by search)
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

        meta_id = save_attendance_to_db(section, attendance_date, period, st.session_state.username, rows_to_save)

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
        st.balloons()

# ------------------------
# HOD Dashboard (Single + Aggregated + Daily/Weekly/Monthly + Individual)
# ------------------------
elif st.session_state.role == "HOD":
    st.header("🏫 HOD Dashboard - Absentees & Reports")

    # fetch sections available (from records)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT section FROM attendance_meta ORDER BY section")
    sections_db = [r[0] for r in c.fetchall()]
    conn.close()

    if not sections_db:
        st.info("No attendance data found yet.")
        st.stop()

    section = st.selectbox("Select Section", sections_db)

    main_mode = st.selectbox("Choose Report Area", [
        "Single Record (saved attendance)",
        "Aggregated: All Periods on a Date",
        "Aggregated: Date Range",
        "Daily Report",
        "Weekly Report (7 days)",
        "Monthly Report",
        "Individual Student Report"
    ])

    # helper: get metas for section
    def fetch_metas_for_section(sec, start=None, end=None):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        if start and end:
            c.execute("SELECT id, attendance_date, period, submitted_by FROM attendance_meta WHERE section=? AND attendance_date BETWEEN ? AND ? ORDER BY attendance_date, period", (sec, str(start), str(end)))
        else:
            c.execute("SELECT id, attendance_date, period, submitted_by FROM attendance_meta WHERE section=? ORDER BY attendance_date DESC, created_at DESC", (sec,))
        metas = c.fetchall()
        conn.close()
        return metas

    # helper: build dataframe aggregated from meta ids
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

    # MODE: Single Record
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
                    st.dataframe(df_abs, use_container_width=True)
                    towrite = BytesIO()
                    df_abs.to_excel(towrite, index=False, sheet_name='absentees_single')
                    towrite.seek(0)
                    st.download_button("📥 Download (Excel)", towrite, file_name=f"absentees_single_{sel_mid}.xlsx")
                else:
                    st.success("🎉 All present in selected record.")

    # MODE: Aggregated - All Periods on a Date
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
                    st.dataframe(df_group, use_container_width=True)
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='agg_date')
                    towrite.seek(0)
                    st.download_button("📥 Download Aggregated (Excel)", towrite, file_name=f"aggregated_{section}_{agg_date}.xlsx")

    # MODE: Aggregated - Date Range
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
                        st.dataframe(df_group, use_container_width=True)
                        towrite = BytesIO()
                        df_group.to_excel(towrite, index=False, sheet_name='agg_range')
                        towrite.seek(0)
                        st.download_button("📥 Download Aggregated (Excel)", towrite, file_name=f"aggregated_{section}_{start_d}_to_{end_d}.xlsx")

    # MODE: Daily Report
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
                    st.dataframe(df_group, use_container_width=True)
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='daily')
                    towrite.seek(0)
                    st.download_button("📥 Download Daily (Excel)", towrite, file_name=f"daily_absentees_{section}_{daily_date}.xlsx")

    # MODE: Weekly Report (7 days)
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
                    st.dataframe(df_group, use_container_width=True)
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='weekly')
                    towrite.seek(0)
                    st.download_button("📥 Download Weekly (Excel)", towrite, file_name=f"weekly_absentees_{section}_{start_week}_to_{end_week}.xlsx")

    # MODE: Monthly Report
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
                    st.dataframe(df_group, use_container_width=True)
                    towrite = BytesIO()
                    df_group.to_excel(towrite, index=False, sheet_name='monthly')
                    towrite.seek(0)
                    st.download_button("📥 Download Monthly (Excel)", towrite, file_name=f"monthly_absentees_{section}_{month_start.year}_{month_start.month}.xlsx")

    # MODE: Individual Student Report
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
                    nm = start.replace(year=start.year+1, month=1, day=1) if start.month == 12 else start.replace(month=start.month+1, day=1)
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
                            parent_name = students_df.loc[students_df['Regd. No.'].astype(str)==sel_regd, 'Father Name'].values
                            parent_phone = students_df.loc[students_df['Regd. No.'].astype(str)==sel_regd, 'Parent Ph.-1'].values
                            parent_name = parent_name[0] if len(parent_name)>0 else ""
                            parent_phone = parent_phone[0] if len(parent_phone)>0 else ""
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
                                st.dataframe(df, use_container_width=True)
                                st.markdown(f"**Total Absences:** {len(df)}")
                                towrite = BytesIO()
                                df.to_excel(towrite, index=False, sheet_name='student_absences')
                                towrite.seek(0)
                                st.download_button("📥 Download Student Report (Excel)", towrite, file_name=f"student_{sel_regd}_{start}_to_{end}.xlsx")

# ------------------------
# Generic fallback
# ------------------------
else:
    st.info("Your role does not have a specific dashboard yet.")

 
    
