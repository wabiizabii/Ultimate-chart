# ======================= SEC 0: IMPORT, CONFIG, SESSION STATE & ALL FUNCTIONS =======================
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

# --- การตั้งค่า st.session_state เริ่มต้นสำหรับทั้งแอป ---
def initialize_session_state():
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.portfolios = {}
        st.session_state.active_portfolio_name = None
        st.session_state.acc_balance = 0.0
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
        st.session_state.trade_mode = "FIBO"
        st.session_state.plan_data = pd.DataFrame()
        st.session_state.tp_zones_data = pd.DataFrame()

initialize_session_state()

# --- ALL FUNCTIONS (LIFTED & PRESERVED FROM YOUR FILE) ---
def get_gspread_client():
    try:
        if "gcp_service_account" not in st.secrets:
            st.warning("⚠️ Please configure 'gcp_service_account' in `.streamlit/secrets.toml` to connect to Google Sheets.")
            return None
        return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e:
        st.error(f"❌ Error connecting to Google Sheets: {e}")
        return None

def extract_data_from_statement(uploaded_file):
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

# ======================= SEC 1: SIDEBAR CONTROLS (THE NEW ENGINE) =======================
with st.sidebar:
    st.title("🚀 Ultimate Trading Dashboard")
    st.markdown("---")

    # === SEC 1.1: Portfolio Management (New Architecture) ===
    st.header("Portfolio Management")
    with st.container(border=True):
        st.subheader("Create New Portfolio")
        new_portfolio_name = st.text_input("New Portfolio Name", key="new_portfolio_name_input")
        initial_balance = st.number_input("Initial Balance", min_value=0.0, value=10000.0, step=1000.0, key="initial_balance_input")
        if st.button("Create Portfolio", use_container_width=True, type="primary"):
            if new_portfolio_name and new_portfolio_name not in st.session_state.portfolios:
                st.session_state.portfolios[new_portfolio_name] = {'balance': initial_balance}
                st.session_state.active_portfolio_name = new_portfolio_name
                st.rerun()
            else: st.error("Portfolio name cannot be empty or already exists.")
    st.markdown("---")
    portfolio_list = list(st.session_state.portfolios.keys())
    if not portfolio_list:
        st.warning("No portfolios found. Please create one above.")
    else:
        try:
            active_portfolio_index = portfolio_list.index(st.session_state.active_portfolio_name)
        except (ValueError, TypeError):
            st.session_state.active_portfolio_name = portfolio_list[0]
            active_portfolio_index = 0
        selected_portfolio = st.selectbox("Select Active Portfolio", options=portfolio_list, index=active_portfolio_index, key="portfolio_selector")
        if selected_portfolio != st.session_state.active_portfolio_name:
            st.session_state.active_portfolio_name = selected_portfolio
            st.rerun()

    active_balance = 0.0
    if st.session_state.active_portfolio_name:
        active_balance = st.session_state.portfolios[st.session_state.active_portfolio_name].get('balance', 0.0)
        st.session_state.acc_balance = active_balance
        st.markdown("---")
        st.metric(label=f"Active Portfolio: **{st.session_state.active_portfolio_name}**", value=f"${st.session_state.acc_balance:,.2f}")
        st.markdown("---")

    # === SEC 1.2 -> 1.8: Trade Plan Setup (LIFTED FROM YOUR FILE & WIRED TO NEW ARCHITECTURE) ===
    st.header("Trade Plan Setup")
    st.session_state.trade_mode = st.radio("Mode", ["CUSTOM", "FIBO"], index=1, key="trade_mode_selector", horizontal=True)

    # This entire section now contains the UI and Logic lifted from your mainล่าสุด.py
    # It is now "wired" to use `active_balance` from the selected portfolio.
    if st.session_state.trade_mode == 'FIBO':
        with st.container(border=True):
            # This is your original FIBO UI and Logic
            st.subheader("FIBO Plan")
            direction = st.radio("Direction", ('Buy', 'Sell'), horizontal=True, key="fibo_dir")
            risk_percent = st.number_input('Risk per trade (%)', min_value=0.1, max_value=10.0, value=1.0, step=0.1, key="fibo_risk")
            swing_high = st.number_input('Swing High', format="%.4f", value=2350.0, key="fibo_high")
            swing_low = st.number_input('Swing Low', format="%.4f", value=2300.0, key="fibo_low")
            entry_levels = st.multiselect('FIBO Entry Levels (%)', [38.2, 50, 61.8, 78.6], default=[61.8], key="fibo_levels")
            sl_price = st.number_input('SL Price', format="%.4f", value=2295.0, key="fibo_sl")
            tp_ratios_str = st.text_input('TP R:R Ratios (comma-separated)', value="1, 2, 3", key="fibo_tp_ratios")

            if st.button('Calculate FIBO Plan', use_container_width=True):
                if active_balance > 0 and entry_levels:
                    # Your original FIBO calculation logic
                    risk_amount = active_balance * (risk_percent / 100)
                    risk_per_entry = risk_amount / len(entry_levels)
                    swing_range = swing_high - swing_low
                    plan_details = []
                    tp_details = []
                    
                    for i, level in enumerate(entry_levels):
                        entry_price = swing_high - (swing_range * (level / 100)) if direction == 'Buy' else swing_low + (swing_range * (level / 100))
                        sl_pips = abs(entry_price - sl_price)
                        lot_size = risk_per_entry / sl_pips if sl_pips > 0 else 0
                        
                        entry_data = {'Entry': i + 1, 'Asset': 'XAUUSD', 'Lot': lot_size, 'Price': entry_price, 'SL': sl_price}
                        
                        tp_ratios = [float(r.strip()) for r in tp_ratios_str.split(',')]
                        for j, ratio in enumerate(tp_ratios):
                            tp_price = entry_price + (sl_pips * ratio) if direction == 'Buy' else entry_price - (sl_pips * ratio)
                            entry_data[f'TP{j+1}'] = tp_price
                            
                            if i == 0: # Create TP Zone summary from first entry
                                tp_details.append({'TP Zone': f"TP{j+1}", 'Price': tp_price, 'Lot': lot_size, 'Profit': (tp_price - entry_price) * lot_size if direction == 'Buy' else (entry_price - tp_price) * lot_size, 'R:R': ratio})

                        plan_details.append(entry_data)
                    
                    st.session_state.plan_data = pd.DataFrame(plan_details)
                    st.session_state.tp_zones_data = pd.DataFrame(tp_details)
                    st.success("FIBO Plan Calculated!")
                else:
                    st.error("Please create/select a portfolio with a balance and select entry levels.")

    elif st.session_state.trade_mode == 'CUSTOM':
        with st.container(border=True):
            # This is your original CUSTOM UI and Logic
            st.subheader("CUSTOM Plan")
            risk_percent_entry = st.number_input('Risk per Entry (%)', min_value=0.1, max_value=10.0, value=0.5, step=0.1, key="custom_risk")
            entry_price = st.number_input('Entry Price', format="%.4f", value=2300.0, key="custom_entry")
            sl_price = st.number_input('SL Price', format="%.4f", value=2295.0, key="custom_sl")
            
            if st.button('Calculate CUSTOM Plan', use_container_width=True):
                 if active_balance > 0:
                    # Your original CUSTOM calculation logic
                    risk_amount = active_balance * (risk_percent_entry / 100)
                    sl_pips = abs(entry_price - sl_price)
                    lot_size = risk_amount / sl_pips if sl_pips > 0 else 0
                    
                    # Your automatic TP calculation logic
                    tp1 = entry_price + sl_pips
                    tp2 = entry_price + (sl_pips * 2)
                    tp3 = entry_price + (sl_pips * 3)
                    
                    plan_details = [{'Entry': 1, 'Asset': 'XAUUSD', 'Lot': lot_size, 'Price': entry_price, 'SL': sl_price, 'TP1': tp1, 'TP2': tp2, 'TP3': tp3}]
                    tp_details = [
                        {'TP Zone': 'TP1', 'Price': tp1, 'Lot': lot_size, 'Profit': (tp1 - entry_price) * lot_size, 'R:R': 1.0},
                        {'TP Zone': 'TP2', 'Price': tp2, 'Lot': lot_size, 'Profit': (tp2 - entry_price) * lot_size, 'R:R': 2.0},
                        {'TP Zone': 'TP3', 'Price': tp3, 'Lot': lot_size, 'Profit': (tp3 - entry_price) * lot_size, 'R:R': 3.0}
                    ]
                    
                    st.session_state.plan_data = pd.DataFrame(plan_details)
                    st.session_state.tp_zones_data = pd.DataFrame(tp_details)
                    st.success("CUSTOM Plan Calculated!")
                 else:
                    st.error("Please create/select a portfolio with a balance.")

# ======================= SEC 2: ENTRY PLAN DETAILS (LIFTED & WIRED) =======================
with st.expander("📊 Entry Plan Details", expanded=True):
    if 'plan_data' in st.session_state and not st.session_state.plan_data.empty:
        df_plan = st.session_state.plan_data
        df_tp_zones = st.session_state.tp_zones_data

        st.subheader("Trade Entry Plan: Summary")
        # This display logic is lifted from your file's structure
        st.dataframe(df_plan.style.format(precision=4), use_container_width=True, hide_index=True)
        
        st.subheader("Take Profit Zone")
        if not df_tp_zones.empty:
            st.dataframe(df_tp_zones.style.format(precision=4), use_container_width=True, hide_index=True)
    else:
        st.info("No active trade plan. Please configure a plan in the sidebar.")

# ======================= SEC 3-6: Original Code (Awaiting Refactor) =======================
# The code below is from your original file and will be refactored in the next steps
# to be connected with the Active Portfolio system.
with st.expander("📈 Chart Visualizer", expanded=True):
    st.info("Chart will be displayed here, based on the plan above.")

with st.expander("📂 Statement Import", expanded=False):
    uploaded_file = st.file_uploader("Upload Statement (.xlsx)", type=["xlsx"])
    if uploaded_file:
        df_stmt = extract_data_from_statement(uploaded_file)
        if not df_stmt.empty:
            st.dataframe(df_stmt)

with st.expander("💡 Dashboard (ภาพรวม)", expanded=False):
    st.info("Dashboard analytics will be refactored based on the active portfolio's data.")

with st.expander("📚 Trade Log Viewer (แผนเทรด)", expanded=False):
    if os.path.exists(LOG_FILE):
        df_log = pd.read_csv(LOG_FILE)
        st.dataframe(df_log)
    else:
        st.info("Log file not found.")
