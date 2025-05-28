# =================================================================================
# SEC 0: INITIAL SETUP & CORE FUNCTIONS
# =================================================================================

# ----------------- SEC 0.1: Imports & Page Config -----------------
import streamlit as st
import pandas as pd
import openpyxl
import numpy as np
import os
from datetime import datetime
import plotly.express as px
import google.generativeai as genai
import gspread

st.set_page_config(page_title="Ultimate-Chart", layout="wide")
acc_balance = 10000
log_file = "trade_log.csv"
GOOGLE_SHEET_NAME = "TradeLog"
GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# ----------------- SEC 0.2: Google Sheets Credentials & Functions -----------------
def get_gspread_client():
    try:
        if "gcp_service_account" not in st.secrets:
            st.warning("⚠️ โปรดตั้งค่า 'gcp_service_account' ใน `.streamlit/secrets.toml` เพื่อเชื่อมต่อ Google Sheets.")
            return None
        return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการเชื่อมต่อ Google Sheets: {e}")
        st.info("ตรวจสอบว่า 'gcp_service_account' ใน secrets.toml ถูกต้อง และได้แชร์ Sheet กับ Service Account แล้ว")
        return None

@st.cache_data(ttl=3600)
def load_statement_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        return {}
    # ... (โค้ดส่วนที่เหลือของฟังก์ชันนี้เหมือนเดิม) ...

def save_statement_to_gsheets(df_to_save):
    if df_to_save.empty:
        st.warning("ไม่มีข้อมูลที่จะบันทึกไปยัง Google Sheets.")
        return
    gc = get_gspread_client()
    if gc is None:
        return
    # ... (โค้ดส่วนที่เหลือของฟังก์ชันนี้เหมือนเดิม) ...

# ----------------- SEC 0.3: Utility Functions -----------------
def get_today_drawdown(log_file, acc_balance):
    if not os.path.exists(log_file):
        return 0
    df = pd.read_csv(log_file)
    today_str = datetime.now().strftime("%Y-%m-%d")
    if "Timestamp" not in df.columns or "Risk $" not in df.columns:
        return 0
    df_today = df[df["Timestamp"].str.startswith(today_str)]
    try:
        drawdown = df_today["Risk $"].astype(float).sum()
    except Exception:
        drawdown = 0
    return drawdown

def get_performance(log_file, mode="week"):
    if not os.path.exists(log_file):
        return 0, 0, 0
    df = pd.read_csv(log_file)
    if "Timestamp" not in df.columns or "Risk $" not in df.columns:
        return 0, 0, 0
    now = datetime.now()
    if mode == "week":
        week_start = (now - pd.Timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        df_period = df[df["Timestamp"] >= week_start]
    else:  # month
        month_start = now.strftime("%Y-%m-01")
        df_period = df[df["Timestamp"] >= month_start]
    win = df_period[df_period["Risk $"].astype(float) > 0].shape[0]
    loss = df_period[df_period["Risk $"].astype(float) <= 0].shape[0]
    total = win + loss if (win + loss) > 0 else 1
    winrate = 100 * win / total
    gain = df_period["Risk $"].astype(float).sum()
    return winrate, gain, total


# =================================================================================
# SEC 1: SIDEBAR - CORE CONTROLS & INPUTS
# =================================================================================

st.sidebar.header("🎛️ Trade Setup")

# ----------------- SEC 1.1: Core Controls (Drawdown Limit, Mode, Reset) -----------------
drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=2.0, step=0.1, format="%.1f"
)

mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")

if st.sidebar.button("🔄 Reset Form"):
    risk_keep = st.session_state.get("risk_pct", 1.0)
    asset_keep = st.session_state.get("asset", "XAUUSD")
    keys_to_keep = {"risk_pct", "asset"}
    keys_to_delete = [k for k in list(st.session_state.keys()) if k not in keys_to_keep]
    for k in keys_to_delete:
        del st.session_state[k]
    st.session_state["risk_pct"] = risk_keep
    st.session_state["asset"] = asset_keep
    st.session_state["fibo_flags"] = [False, False, False, False, False]
    st.rerun()

# ----------------- SEC 1.2: FIBO Mode Inputs -----------------
if mode == "FIBO":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2:
        risk_pct = st.number_input(
            "Risk %", min_value=0.01, max_value=100.0, step=0.01, format="%.2f", key="risk_pct"
        )
    with col3:
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True)
    col4, col5 = st.sidebar.columns(2)
    with col4:
        swing_high = st.text_input("High", key="swing_high")
    with col5:
        swing_low = st.text_input("Low", key="swing_low")

    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibos = [0.114, 0.25, 0.382, 0.5, 0.618]
    labels = [f"{l:.3f}" for l in fibos]
    cols = st.sidebar.columns(len(fibos))
    if "fibo_flags" not in st.session_state:
        st.session_state.fibo_flags = [True] * len(fibos)
    fibo_selected = []
    for i, col in enumerate(cols):
        checked = col.checkbox(labels[i], value=st.session_state.fibo_flags[i])
        fibo_selected.append(checked)
    st.session_state.fibo_flags = fibo_selected
    # ... (โค้ดส่วนที่เหลือของ FIBO mode เหมือนเดิม) ...

# ----------------- SEC 1.3: CUSTOM Mode Inputs -----------------
elif mode == "CUSTOM":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2:
        risk_pct = st.number_input(
            "Risk %", min_value=0.01, max_value=100.0, value=1.00, step=0.01, format="%.2f"
        )
    with col3:
        n_entry = st.number_input(
            "จำนวนไม้", min_value=1, max_value=10, value=2, step=1
        )
    # ... (โค้ดส่วนที่เหลือของ CUSTOM mode เหมือนเดิม) ...

# ----------------- SEC 1.4: Plan Summary in Sidebar -----------------
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")
if mode == "FIBO":
    # ... (โค้ดคำนวณและแสดงผล FIBO summary เหมือนเดิม) ...
elif mode == "CUSTOM":
    # ... (โค้ดคำนวณและแสดงผล CUSTOM summary เหมือนเดิม) ...

# ----------------- SEC 1.5: Risk Scaling Manager -----------------
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    scaling_step = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=1.0, value=0.25, step=0.01, format="%.2f"
    )
    min_risk_pct = st.number_input(
        "Minimum Risk %", min_value=0.01, max_value=100.0, value=0.5, step=0.01, format="%.2f"
    )
    max_risk_pct = st.number_input(
        "Maximum Risk %", min_value=0.01, max_value=100.0, value=5.0, step=0.01, format="%.2f"
    )
    scaling_mode = st.radio(
        "Scaling Mode", ["Manual", "Auto"], horizontal=True
    )

winrate, gain, total = get_performance(log_file, mode="week")
current_risk = risk_pct
if winrate > 55 and gain > 0.02 * acc_balance:
    suggest_risk = min(current_risk + scaling_step, max_risk_pct)
    scaling_msg = f"🎉 ผลงานดี! Winrate {winrate:.1f}%, กำไร {gain:.2f} แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}"
elif winrate < 45 or gain < 0:
    suggest_risk = max(current_risk - scaling_step, min_risk_pct)
    scaling_msg = f"⚠️ ควรลด Risk%! Winrate {winrate:.1f}%, กำไร {gain:.2f} แนะนำลด Risk% เป็น {suggest_risk:.2f}"
else:
    suggest_risk = current_risk
    scaling_msg = "Risk% คงที่"

st.sidebar.info(scaling_msg)

if scaling_mode == "Manual" and suggest_risk != current_risk:
    if st.sidebar.button(f"ปรับ Risk% เป็น {suggest_risk:.2f}"):
        risk_pct = suggest_risk
elif scaling_mode == "Auto":
    risk_pct = suggest_risk


# ----------------- SEC 1.6: Save Plan Logic & Execution -----------------
drawdown_today = get_today_drawdown(log_file, acc_balance)
drawdown_limit = -acc_balance * (drawdown_limit_pct / 100)

if drawdown_today < 0:
    st.sidebar.markdown(f"**ขาดทุนรวมวันนี้:** {drawdown_today:,.2f} USD")
else:
    st.sidebar.markdown(f"**ขาดทุนรวมวันนี้:** {drawdown_today:,.2f} USD")

def save_plan(data, mode, asset, risk_pct, direction):
    # ... (โค้ดฟังก์ชัน save_plan เหมือนเดิม) ...

# ... (โค้ดส่วนที่เหลือของ Logic การ Save และเช็ค Drawdown Limit เหมือนเดิม) ...


# =================================================================================
# SEC 2: MAIN AREA - CURRENT ENTRY PLAN DETAILS
# =================================================================================
with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):
    if mode == "FIBO":
        # ... (โค้ดแสดงตาราง Entry และ TP ของ FIBO เหมือนเดิม) ...
    elif mode == "CUSTOM":
        # ... (โค้ดแสดงตาราง Entry และ TP ของ CUSTOM เหมือนเดิม) ...

# =================================================================================
# SEC 3: MAIN AREA - CHART VISUALIZER
# =================================================================================
with st.expander("📈 Chart Visualizer", expanded=True):
    plot = st.button("Plot Plan", key="plot_plan")
    if plot:
        # ... (โค้ด TradingView Widget HTML เหมือนเดิม) ...
    else:
        st.info("กดปุ่ม Plot Plan เพื่อแสดงกราฟ TradingView")

# =================================================================================
# SEC 4: MAIN AREA - STATEMENT IMPORT & PROCESSING
# =================================================================================
with st.expander("📂 Statement Import & Auto-Mapping", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")
    # ... (โค้ดทั้งหมดของส่วน Import Statement เหมือนเดิม) ...

# =================================================================================
# SEC 5: MAIN AREA - PERFORMANCE DASHBOARD & AI ANALYSIS
# =================================================================================
with st.expander("📊 Performance Dashboard", expanded=True):
    # ----------------- SEC 5.1: Data Source Selection -----------------
    def load_data_for_dashboard():
        source_option = st.selectbox(
            "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด",
            ["Log File (แผน)", "Statement Import (ของจริง)"],
            index=0,
            key="dashboard_source_select"
        )
        if source_option == "Log File (แผน)":
            if os.path.exists(log_file):
                df_data = pd.read_csv(log_file)
            else:
                df_data = pd.DataFrame()
        else: # Statement Import (ของจริง)
            return st.session_state.df_stmt_current
        return df_data

    df_data = load_data_for_dashboard()

    # ----------------- SEC 5.2: Dashboard Tabs -----------------
    tab_dashboard, tab_rr, tab_lot, tab_time, tab_ai, tab_export = st.tabs([
        "📊 Dashboard",
        "📈 RR Histogram",
        "📉 Lot Size Evolution",
        "🕒 Time Analysis",
        "🤖 AI Recommendation",
        "⬇️ Export/Report"
    ])

    with tab_dashboard:
        # ... (โค้ดของ Tab Dashboard เหมือนเดิม) ...
    with tab_rr:
        # ... (โค้ดของ Tab RR Histogram เหมือนเดิม) ...
    with tab_lot:
        # ... (โค้ดของ Tab Lot Size Evolution เหมือนเดิม) ...
    with tab_time:
        # ... (โค้ดของ Tab Time Analysis เหมือนเดิม) ...
    with tab_ai:
        # ... (โค้ดของ Tab AI Recommendation เหมือนเดิม) ...
    with tab_export:
        # ... (โค้ดของ Tab Export/Report เหมือนเดิม) ...

# =================================================================================
# SEC 6: MAIN AREA - TRADE LOG VIEWER (PLANNED TRADES)
# =================================================================================
with st.expander("📚 Trade Log Viewer (แผนเทรด)", expanded=False):
    if os.path.exists(log_file):
        # ... (โค้ดของส่วน Log Viewer เหมือนเดิม) ...
    else:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้")
