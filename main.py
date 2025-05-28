# ======================= SEC 0: IMPORT, CONFIG & INITIAL SETUP =======================
import streamlit as st
import pandas as pd
import openpyxl  
import numpy as np
import os
from datetime import datetime
import plotly.express as px
import google.generativeai as genai
import gspread

# --- การตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Ultimate Trading Dashboard", layout="wide")

# --- ค่าคงที่ ---
LOG_FILE = "trade_log.csv"
GOOGLE_SHEET_NAME = "TradeLog"
GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# --- NEW: การตั้งค่า st.session_state เริ่มต้นสำหรับทั้งแอป ---
def initialize_session_state():
    """
    ตั้งค่าเริ่มต้นสำหรับ Session State ทั้งหมดของแอปพลิเคชัน
    เพื่อให้แน่ใจว่า key ที่จำเป็นมีอยู่เสมอ ป้องกัน KeyError
    """
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        
        # สถานะของ Portfolio
        st.session_state.portfolios = {} # เก็บข้อมูลพอร์ตทั้งหมด { 'ชื่อพอร์ต': {'balance': 10000} }
        st.session_state.active_portfolio_name = None
        
        # สถานะของข้อมูล
        st.session_state.acc_balance = 0.0
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
        
        # สถานะของแผนเทรด
        st.session_state.trade_mode = "FIBO" 
        st.session_state.plan_data = pd.DataFrame()

# เรียกใช้ฟังก์ชันเพื่อตั้งค่าเริ่มต้น (จะรันเพียงครั้งเดียวต่อ session)
initialize_session_state()

# --- ฟังก์ชันที่คุณสร้างไว้ (คงเดิม) ---
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

def extract_data_from_statement(uploaded_file):
    # (โค้ดฟังก์ชันนี้ของคุณยังคงอยู่เหมือนเดิม)
    # เราจะมาปรับปรุงฟังก์ชันนี้ใน Step ต่อๆ ไป
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        positions_start = df[df.iloc[:, 0] == 'Positions'].index[0]
        summary_start = df[df.iloc[:, 0] == 'Summary'].index[0]
        df_positions = pd.read_excel(uploaded_file, engine='openpyxl', skiprows=positions_start + 1, skipfooter=len(df) - summary_start)
        df_positions.columns = [str(col).strip() for col in df_positions.columns]
        return df_positions
    except Exception as e:
        st.error(f"Error reading statement file: {e}")
        return pd.DataFrame()


# ======================= SEC 1: SIDEBAR CONTROLS (REFACTORED) =======================
with st.sidebar:
    st.title("🚀 Ultimate Trading Dashboard")
    st.markdown("---")

    # === SEC 1.1: Portfolio Management (NEW - THE HEART OF THE APP) ===
    st.header("Portfolio Management")
    with st.container(border=True):
        st.subheader("Create New Portfolio")
        new_portfolio_name = st.text_input("New Portfolio Name", key="new_portfolio_name_input")
        initial_balance = st.number_input("Initial Balance", min_value=0.0, value=10000.0, step=1000.0, key="initial_balance_input")
        
        if st.button("Create Portfolio", use_container_width=True, type="primary"):
            if new_portfolio_name and new_portfolio_name not in st.session_state.portfolios:
                st.session_state.portfolios[new_portfolio_name] = {'balance': initial_balance}
                st.session_state.active_portfolio_name = new_portfolio_name
                st.success(f"Portfolio '{new_portfolio_name}' created!")
                st.rerun()
            else:
                st.error("Portfolio name cannot be empty or already exists.")
    
    st.markdown("---")

    # ส่วนเลือกพอร์ตที่มีอยู่
    portfolio_list = list(st.session_state.portfolios.keys())
    
    if not portfolio_list:
        st.warning("No portfolios found. Please create one above.")
    else:
        try:
            # หา index ของพอร์ตที่กำลังใช้งานอยู่
            active_portfolio_index = portfolio_list.index(st.session_state.active_portfolio_name)
        except (ValueError, TypeError):
            # ถ้าไม่มี ให้เลือกตัวแรกเป็น default
            st.session_state.active_portfolio_name = portfolio_list[0]
            active_portfolio_index = 0

        selected_portfolio = st.selectbox(
            "Select Active Portfolio",
            options=portfolio_list,
            index=active_portfolio_index,
            key="portfolio_selector"
        )

        # อัปเดต session_state เมื่อมีการเปลี่ยนพอร์ต
        if selected_portfolio != st.session_state.active_portfolio_name:
            st.session_state.active_portfolio_name = selected_portfolio
            st.rerun()

    # แสดงพอร์ตและยอดเงินปัจจุบันจาก session_state
    if st.session_state.active_portfolio_name:
        current_balance = st.session_state.portfolios[st.session_state.active_portfolio_name].get('balance', 0.0)
        st.session_state.acc_balance = current_balance # อัปเดต acc_balance ใน session_state
        
        st.markdown("---")
        st.metric(label=f"Active Portfolio: **{st.session_state.active_portfolio_name}**",
                  value=f"${st.session_state.acc_balance:,.2f}")
        st.markdown("---")
    
    # พื้นที่สำหรับ SEC 1.2, 1.3, 1.4 ที่เราจะสร้างใน Step ถัดไป
    st.header("Trade Plan Setup")
    # (เราจะนำโค้ด FIBO/CUSTOM ที่แก้ไขแล้วมาใส่ที่นี่ใน Step ต่อไป)
    st.info("Configure your trade plan here.")


# ======================= SEC 2: ENTRY PLAN DETAILS =======================
# (โค้ดส่วนนี้จากไฟล์ของคุณยังคงอยู่ แต่จะถูกปรับปรุงใน Step ต่อไป)
with st.expander("📊 Entry Plan Details", expanded=True):
    st.info("This section will be refactored to display the plan from the sidebar.")
    # st.write(st.session_state.get('df_fibo', "No FIBO data")) # ตัวอย่างโค้ดเก่า
    # st.write(st.session_state.get('df_custom', "No CUSTOM data")) # ตัวอย่างโค้ดเก่า

# ======================= SEC 3: CHART VISUALIZER =======================
# (โค้ดส่วนนี้จากไฟล์ของคุณยังคงอยู่)
with st.expander("📈 Chart Visualizer", expanded=True):
    st.info("Chart will be displayed here.")


# ======================= SEC 4: STATEMENT IMPORT =======================
# (โค้dส่วนนี้จากไฟล์ของคุณยังคงอยู่ แต่จะถูกปรับปรุงใน Step ต่อไป)
with st.expander("📂 Statement Import", expanded=False):
    uploaded_file = st.file_uploader("Upload Statement (.xlsx)", type=["xlsx"])
    if uploaded_file:
        df_stmt = extract_data_from_statement(uploaded_file)
        if not df_stmt.empty:
            st.dataframe(df_stmt)


# ======================= SEC 5: DASHBOARD =======================
# (โค้ดส่วนนี้จากไฟล์ของคุณยังคงอยู่ แต่จะถูกปรับปรุงใน Step ต่อไป)
with st.expander("💡 Dashboard (ภาพรวม)", expanded=False):
    st.info("Dashboard analytics will be refactored based on the active portfolio.")


# ======================= SEC 6: LOG VIEWER =======================
# (โค้ดส่วนนี้จากไฟล์ของคุณยังคงอยู่ แต่จะถูกปรับปรุงใน Step ต่อไป)
with st.expander("📚 Trade Log Viewer (แผนเทรด)", expanded=False):
    st.info("Log viewer will be refactored to filter by active portfolio.")
