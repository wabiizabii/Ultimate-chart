# ===================================================================================
#                                 ULTIMATE CHART
#                                  RESTRUCTURED CODE
# ===================================================================================

# ======================= SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime
import plotly.express as px
import google.generativeai as genai
import gspread

# --- Page Config ---
st.set_page_config(page_title="Ultimate Chart", layout="wide")

# --- Constants ---
ACC_BALANCE = 10000
LOG_FILE = "trade_log.csv"
GOOGLE_SHEET_NAME = "TradeLog"
GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# ======================= SEC 1: HELPER FUNCTIONS =======================
# All functions are grouped here for better organization.

# --- Google Sheets Functions ---
def get_gspread_client():
    try:
        if "gcp_service_account" not in st.secrets:
            st.warning("⚠️ โปรดตั้งค่า 'gcp_service_account' ใน `.streamlit/secrets.toml` เพื่อเชื่อมต่อ Google Sheets.")
            return None
        return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการเชื่อมต่อ Google Sheets: {e}")
        return None

@st.cache_data(ttl=600) # Cache for 10 minutes
def load_statement_from_gsheets():
    gc = get_gspread_client()
    if gc is None: return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(GOOGLE_WORKSHEET_NAME)
        data = worksheet.get_all_records()
        if not data: return pd.DataFrame()
        df = pd.DataFrame(data)
        # Basic data cleaning
        for col in ['Profit', 'Risk $', 'Lot', 'RR', 'Entry', 'SL', 'TP']:
            if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
        for col in ['Timestamp', 'Time', 'Date', 'Open Time', 'Close Time']:
            if col in df.columns: df[col] = pd.to_datetime(df[col], errors='coerce')
        return df
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ ไม่พบ Google Sheet '{GOOGLE_SHEET_NAME}'.")
        return pd.DataFrame()
    except gspread.exceptions.WorksheetNotFound:
        # This is not an error, just means we need to create it later.
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการโหลดข้อมูลจาก Google Sheets: {e}")
        return pd.DataFrame()

def save_statement_to_gsheets(df_to_save):
    if df_to_save.empty: return
    gc = get_gspread_client()
    if gc is None: return
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        try:
            worksheet = sh.worksheet(GOOGLE_WORKSHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sh.add_worksheet(title=GOOGLE_WORKSHEET_NAME, rows="1", cols="1")
        
        df_str = df_to_save.astype(str)
        worksheet.clear()
        worksheet.update([df_str.columns.values.tolist()] + df_str.values.tolist())
        st.success(f"บันทึกข้อมูลไปยัง Google Sheet '{GOOGLE_SHEET_NAME}/{GOOGLE_WORKSHEET_NAME}' เรียบร้อย!")
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูลไปยัง Google Sheets: {e}")

def save_plan_to_logfile(data, mode, asset, risk_pct, direction):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_save = pd.DataFrame(data)
    df_save["Mode"] = mode
    df_save["Asset"] = asset
    df_save["Risk %"] = risk_pct
    df_save["Direction"] = direction
    df_save["Timestamp"] = now
    
    df_old = pd.read_csv(LOG_FILE) if os.path.exists(LOG_FILE) else pd.DataFrame()
    df_final = pd.concat([df_old, df_save], ignore_index=True)
    df_final.to_csv(LOG_FILE, index=False)

# --- Performance Calculation Functions ---
def get_today_drawdown(log_file, acc_balance):
    if not os.path.exists(log_file): return 0
    df = pd.read_csv(log_file)
    today_str = datetime.now().strftime("%Y-%m-%d")
    if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0
    df_today = df[df["Timestamp"].str.startswith(today_str)]
    return pd.to_numeric(df_today["Risk $"], errors='coerce').sum()

def get_performance(log_file, mode="week"):
    if not os.path.exists(log_file): return 0, 0, 0
    df = pd.read_csv(log_file)
    if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0, 0, 0
    now = datetime.now()
    if mode == "week":
        start_date = (now - pd.Timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    else: # month
        start_date = now.strftime("%Y-%m-01")
    df_period = df[df["Timestamp"] >= start_date]
    win = df_period[pd.to_numeric(df_period["Risk $"], errors='coerce') > 0].shape[0]
    loss = df_period[pd.to_numeric(df_period["Risk $"], errors='coerce') <= 0].shape[0]
    total = win + loss if (win + loss) > 0 else 1
    winrate = 100 * win / total
    gain = pd.to_numeric(df_period["Risk $"], errors='coerce').sum()
    return winrate, gain, total

# --- Statement Processing Functions ---
def extract_sections_from_file(file):
    if file.name.endswith(".xlsx"):
        df_raw = pd.read_excel(file, header=None, engine='openpyxl')
    else:
        df_raw = pd.read_csv(file, header=None)
    
    section_starts = {}
    section_keys = ["Positions", "Orders", "Deals", "Balance", "Drawdown", "History", "Trades"]
    for idx, row in df_raw.iterrows():
        cell_value = str(row.iloc[0]).strip()
        for key in section_keys:
            if cell_value.startswith(key):
                section_starts[key] = idx
                break
    
    target_sections = ["Deals", "Trades", "Positions", "History"]
    found_section_key = next((key for key in target_sections if key in section_starts), None)
    
    if not found_section_key:
        return {}
        
    header_row_idx = section_starts[found_section_key] + 1
    data_start_idx = header_row_idx + 1
    end_row_idx = len(df_raw)
    
    df_section = df_raw.iloc[data_start_idx:end_row_idx].dropna(how="all")
    if not df_section.empty:
        df_section.columns = df_raw.iloc[header_row_idx].tolist()
        return {found_section_key: df_section.reset_index(drop=True)}
    return {}

def preprocess_stmt_data(df):
    rename_map = {
        'Open Time': 'Timestamp', 'Close Time': 'Timestamp', 'Time': 'Timestamp',
        'Profit': 'Profit', 'Symbol': 'Asset', 'Lots': 'Lot', 'Stop Loss': 'SL',
        'Take Profit': 'TP', 'Ticket': 'Trade ID'
    }
    df = df.rename(columns=lambda c: rename_map.get(c, c))
    for col in ['Profit', 'Lot', 'Entry', 'SL', 'TP', 'RR']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df.dropna(subset=['Profit']) if 'Profit' in df.columns else df
    return df

# ======================= SEC 2: SESSION STATE & INITIAL LOAD =======================
# Initialize session state for statement data
if 'df_stmt_current' not in st.session_state:
    st.session_state.df_stmt_current = load_statement_from_gsheets()

# ======================= SEC 3: SIDEBAR =======================
st.sidebar.header("🎛️ Trade Setup")
mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")

# --- Trade Inputs (FIBO/CUSTOM) ---
if mode == "FIBO":
    # ... (โค้ดส่วน FIBO input ของคุณ) ...
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1: asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2: risk_pct = st.number_input("Risk %", 0.01, 100.0, 1.0, 0.01, "%.2f", key="risk_pct")
    with col3: direction = st.radio("Direction", ["Long", "Short"], horizontal=True)
    col4, col5 = st.sidebar.columns(2)
    with col4: swing_high = st.text_input("High", key="swing_high")
    with col5: swing_low = st.text_input("Low", key="swing_low")
    save_button = st.sidebar.button("Save Plan", key="save_fibo")
    # ... (ส่วนคำนวณและแสดงผล FIBO ของคุณ) ...

elif mode == "CUSTOM":
    # ... (โค้ดส่วน CUSTOM input ของคุณ) ...
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1: asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2: risk_pct = st.number_input("Risk %", 0.01, 100.0, 1.0, 0.01, "%.2f")
    with col3: n_entry = st.number_input("จำนวนไม้", 1, 10, 2, 1)
    # ... (Loop กรอกข้อมูลแต่ละไม้) ...
    save_button = st.sidebar.button("Save Plan", key="save_custom")
    # ... (ส่วนคำนวณและแสดงผล CUSTOM ของคุณ) ...

# --- Drawdown & Scaling Manager in Sidebar ---
st.sidebar.markdown("---")
drawdown_limit_pct = st.sidebar.number_input("Drawdown Limit ต่อวัน (%)", 0.1, 20.0, 2.0, 0.1, "%.1f")
drawdown_today = get_today_drawdown(LOG_FILE, ACC_BALANCE)
drawdown_limit_val = -ACC_BALANCE * (drawdown_limit_pct / 100)
st.sidebar.markdown(f"**ขาดทุนรวมวันนี้:** {drawdown_today:,.2f} USD")

# ... (โค้ด Scaling Manager ของคุณ) ...

# --- Save Plan Logic ---
# (ควรจะอยู่ใกล้ปุ่ม Save เพื่อความชัดเจน หรือจะรวมไว้ที่นี่ก็ได้)
# if save_button:
#     if drawdown_today <= drawdown_limit_val:
#         st.sidebar.error(f"หยุดเทรด! ขาดทุนเกินลิมิต")
#     else:
#         # ... (Logic การเตรียม data สำหรับ save_plan_to_logfile) ...
#         st.sidebar.success("บันทึกแผนสำเร็จ!")

# ======================= SEC 4: MAIN PAGE =======================
st.title("Legendary RR Planner")
st.markdown("---")

# --- 4.1 Statement Upload & Processing ---
st.subheader("📤 อัปโหลดและจัดการ Statement")
with st.container(border=True):
    uploaded_files = st.file_uploader(
        "อัปโหลด Statement (.xlsx, .csv)", 
        type=["xlsx", "csv"], 
        accept_multiple_files=True
    )
    if uploaded_files:
        processed_dfs = [extract_sections_from_file(f).get("Deals", pd.DataFrame()) for f in uploaded_files]
        df_new_uploads = pd.concat([preprocess_stmt_data(df) for df in processed_dfs if not df.empty], ignore_index=True)
        
        st.write("**Preview ข้อมูลใหม่:**")
        st.dataframe(df_new_uploads.head(3), use_container_width=True)

        col1, col2 = st.columns(2)
        if col1.button("🔄 แทนที่ข้อมูลเดิมทั้งหมด", use_container_width=True):
            st.session_state.df_stmt_current = df_new_uploads
            save_statement_to_gsheets(st.session_state.df_stmt_current)
            st.rerun()

        if col2.button("➕ รวมกับข้อมูลเดิม (ลบตัวซ้ำ)", use_container_width=True):
            df_combined = pd.concat([st.session_state.df_stmt_current, df_new_uploads], ignore_index=True)
            if 'Trade ID' in df_combined.columns:
                st.session_state.df_stmt_current = df_combined.drop_duplicates(subset=['Trade ID'], keep='last')
            else:
                st.session_state.df_stmt_current = df_combined.drop_duplicates(keep='last')
            save_statement_to_gsheets(st.session_state.df_stmt_current)
            st.rerun()

# --- 4.2 Performance Dashboard ---
st.subheader("📊 Performance Dashboard")
with st.expander("เปิด/ปิด Dashboard", expanded=True):
    df_dashboard = st.session_state.df_stmt_current
    if df_dashboard.empty:
        st.info("ยังไม่มีข้อมูล Statement สำหรับ Dashboard (โปรดอัปโหลด หรือตรวจสอบการโหลดจาก Google Sheets)")
    else:
        # ... (โค้ดทั้งหมดในส่วน Dashboard เดิมของคุณ) ...
        # (เช่น Pie Chart, Bar Chart, Balance Curve, และ Tabs ต่างๆ)
        st.markdown("### 🥧 Pie Chart: Win/Loss")
        win_count = df_dashboard[df_dashboard['Profit'] > 0].shape[0]
        loss_count = df_dashboard[df_dashboard['Profit'] <= 0].shape[0]
        pie_df = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count, loss_count]})
        pie_chart = px.pie(pie_df, names="Result", values="Count", color="Result", color_discrete_map={"Win":"green", "Loss":"red"})
        st.plotly_chart(pie_chart, use_container_width=True)
        # ... และกราฟอื่นๆ ตามที่คุณมี ...

# --- 4.3 Chart Visualizer ---
st.subheader("📈 Chart Visualizer")
with st.expander("เปิด/ปิด กราฟ", expanded=True):
    # ... (โค้ดส่วน Visualizer ที่เรากำลังทำกันอยู่) ...
    # (นำโค้ดที่ผมส่งให้ก่อนหน้านี้มาวางที่นี่ได้เลย)
    st.info("กดปุ่ม Plot Plan ใน Sidebar เพื่อแสดงกราฟและแผนเทรด")

# --- 4.4 Trade Log Viewer ---
st.subheader("📚 Trade Log Viewer (แผนเทรด)")
with st.expander("เปิด/ปิด ตาราง Log", expanded=False):
    if os.path.exists(LOG_FILE):
        df_log = pd.read_csv(LOG_FILE)
        st.dataframe(df_log, use_container_width=True, hide_index=True)
    else:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้")
