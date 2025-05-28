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
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.portfolios = {}
        st.session_state.active_portfolio_name = None
        st.session_state.acc_balance = 0.0
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
        st.session_state.trade_mode = "FIBO" # ตั้ง FIBO เป็น default
        st.session_state.plan_data = pd.DataFrame()

initialize_session_state()

# --- ฟังก์ชันทั้งหมดจะถูกย้ายมารวมที่นี่ ---
def get_gspread_client():
    # (โค้ดฟังก์ชันเดิม)
    try:
        if "gcp_service_account" not in st.secrets: return None
        return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e: return None

def extract_data_from_statement(uploaded_file):
    # (โค้ดฟังก์ชันเดิม)
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        positions_start = df[df.iloc[:, 0] == 'Positions'].index[0]
        summary_start = df[df.iloc[:, 0] == 'Summary'].index[0]
        df_positions = pd.read_excel(uploaded_file, engine='openpyxl', skiprows=positions_start + 1, skipfooter=len(df) - summary_start)
        df_positions.columns = [str(col).strip() for col in df_positions.columns]
        return df_positions
    except Exception as e: return pd.DataFrame()

def calculate_tp_zones(df_plan):
    # (โค้ดฟังก์ชันเดิมที่เราปรับปรุงแล้ว)
    tp_zones_data = []
    if not df_plan.empty:
        for index, entry_row in df_plan.iterrows():
            entry_price = entry_row['Price']
            sl_price = entry_row['SL']
            risk_per_point = abs(entry_price - sl_price)
            if risk_per_point > 0:
                for i in range(1, 6):
                    tp_col = f'TP{i}'
                    if tp_col in entry_row and pd.notna(entry_row[tp_col]) and entry_row[tp_col] != 0:
                        tp_price = entry_row[tp_col]
                        lot_size = entry_row['Lot']
                        profit_point = abs(tp_price - entry_price)
                        profit_usd = profit_point * lot_size * 1 # สมมติ Point Value เป็น 1
                        rr_ratio = profit_point / risk_per_point if risk_per_point > 0 else 0
                        tp_zones_data.append({"From Entry": entry_row['Entry'],"TP Zone": f"TP{i}","Price": tp_price,"Lot": lot_size,"Profit ($)": f"{profit_usd:,.2f}","R:R": f"1:{rr_ratio:.2f}"})
    unique_zones_dict = {}
    for zone in tp_zones_data:
        unique_zones_dict[zone['TP Zone']] = zone
    return pd.DataFrame(list(unique_zones_dict.values()))

# ======================= SEC 1: SIDEBAR CONTROLS (REFACTORED) =======================
with st.sidebar:
    st.title("🚀 Ultimate Trading Dashboard")
    st.markdown("---")

    # === SEC 1.1: Portfolio Management (ทำงานสมบูรณ์แล้ว) ===
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
    if st.session_state.active_portfolio_name:
        current_balance = st.session_state.portfolios[st.session_state.active_portfolio_name].get('balance', 0.0)
        st.session_state.acc_balance = current_balance
        st.markdown("---")
        st.metric(label=f"Active Portfolio: **{st.session_state.active_portfolio_name}**", value=f"${st.session_state.acc_balance:,.2f}")
        st.markdown("---")
    
    # === SEC 1.2 & 1.3 & 1.4: Trade Plan Setup (NEW - FULLY FUNCTIONAL) ===
    st.header("Trade Plan Setup")
    st.session_state.trade_mode = st.radio("Mode", ["CUSTOM", "FIBO"], index=1, key="trade_mode_selector", horizontal=True) # FIBO-First

    # === SEC 1.3: FIBO Inputs & Calculation (Risk-Based) ===
    if st.session_state.trade_mode == "FIBO":
        with st.container(border=True):
            st.subheader("FIBO Inputs (Risk-Based)")
            fibo_asset = st.text_input("Asset", "XAUUSD", key="fibo_asset")
            fibo_direction = st.radio("Direction", ["Buy", "Sell"], horizontal=True, key="fibo_direction")
            col1, col2 = st.columns(2)
            with col1:
                fibo_swing_high = st.number_input("Swing High", value=2350.0, format="%.4f")
                fibo_swing_low = st.number_input("Swing Low", value=2300.0, format="%.4f")
                fibo_risk_percent = st.number_input("% Risk per Trade", min_value=0.1, max_value=100.0, value=1.0, step=0.1, format="%.2f", help="ความเสี่ยงรวมของทุก Entry ในแผนนี้")
            with col2:
                fibo_sl = st.number_input("Stop Loss Price", value=2290.0, format="%.4f")
                fibo_entry_levels = st.multiselect("Entry Levels (%)", options=[23.6, 38.2, 50.0, 61.8, 78.6, 88.6], default=[50.0, 61.8])
                fibo_point_value = st.number_input("Point Value ($)", value=1.0, help="มูลค่าเมื่อราคาเคลื่อนที่ 1 จุด สำหรับ 1 lot (เช่น XAUUSD=1)")
            st.write("Take Profit Levels")
            tp_cols = st.columns(5)
            fibo_tps = [col.number_input(f"TP{i+1}", value=2350.0 + i*10, format="%.4f", key=f"fibo_tp{i+1}") for i, col in enumerate(tp_cols)]
            if st.button("Calculate Fibo Plan", use_container_width=True, type="primary"):
                plan_entries = []
                swing_range = fibo_swing_high - fibo_swing_low
                risk_per_trade_usd = st.session_state.acc_balance * (fibo_risk_percent / 100)
                if swing_range > 0 and fibo_entry_levels and st.session_state.acc_balance > 0:
                    for i, level in enumerate(sorted(fibo_entry_levels)):
                        entry_price = fibo_swing_high - (swing_range * level / 100) if fibo_direction == "Buy" else fibo_swing_low + (swing_range * level / 100)
                        sl_points = abs(entry_price - fibo_sl)
                        lot_size = (risk_per_trade_usd / len(fibo_entry_levels)) / (sl_points * fibo_point_value) if sl_points > 0 and fibo_point_value > 0 else 0.0
                        plan_entries.append({"Entry": i + 1, "Asset": fibo_asset, "Lot": round(lot_size, 2), "Price": round(entry_price, 4), "SL": fibo_sl, "TP1": fibo_tps[0], "TP2": fibo_tps[1], "TP3": fibo_tps[2], "TP4": fibo_tps[3], "TP5": fibo_tps[4]})
                    st.session_state.plan_data = pd.DataFrame(plan_entries)
                    st.success(f"Fibo plan calculated! Total risk: ${risk_per_trade_usd:,.2f}")
                else: st.error("Invalid inputs. Please check swing range, entry levels, and portfolio balance.")

    # === SEC 1.4: CUSTOM Inputs & Calculation (Risk-Based) ===
    if st.session_state.trade_mode == "CUSTOM":
        with st.container(border=True):
            st.subheader("CUSTOM Inputs (Risk-Based)")
            custom_risk_percent = st.number_input("% Risk per Entry", min_value=0.1, max_value=100.0, value=0.5, step=0.1, format="%.2f", help="ความเสี่ยงสำหรับ 'แต่ละแถว' ในแผน")
            custom_point_value = st.number_input("Point Value ($)", value=1.0, help="มูลค่าเมื่อราคาเคลื่อนที่ 1 จุด สำหรับ 1 lot (เช่น XAUUSD=1)")
            initial_plan_df = pd.DataFrame([{"Entry": 1, "Asset": "XAUUSD", "Price": 2300.0, "SL": 2295.0, "TP1": 2305.0, "TP2": 2310.0, "TP3": None, "TP4": None, "TP5": None}])
            st.write("Edit your custom trade plan below (Lot will be calculated automatically):")
            edited_df = st.data_editor(initial_plan_df, num_rows="dynamic", key="custom_plan_editor", hide_index=True)
            if st.button("Calculate Custom Plan", use_container_width=True, type="primary"):
                if not edited_df.empty and st.session_state.acc_balance > 0:
                    lots_calculated = []
                    risk_per_entry_usd = st.session_state.acc_balance * (custom_risk_percent / 100)
                    for index, row in edited_df.iterrows():
                        sl_points = abs(row['Price'] - row['SL'])
                        lot_size = risk_per_entry_usd / (sl_points * custom_point_value) if sl_points > 0 and custom_point_value > 0 else 0.0
                        lots_calculated.append(round(lot_size, 2))
                    final_df = edited_df.copy()
                    final_df['Lot'] = lots_calculated
                    st.session_state.plan_data = final_df
                    st.success(f"Custom plan updated with calculated lots!")
                else: st.error("Cannot calculate lots. Please check plan details and portfolio balance.")


# ======================= SEC 2: ENTRY PLAN DETAILS (REFACTORED) =======================
with st.expander("📊 Entry Plan Details", expanded=True):
    if 'plan_data' in st.session_state and not st.session_state.plan_data.empty:
        df_plan = st.session_state.plan_data
        st.subheader("Trade Entry Plan: Summary")
        st.dataframe(df_plan.style.format({"Lot": "{:.2f}", "Price": "{:.4f}", "SL": "{:.4f}", "TP1": "{:.4f}", "TP2": "{:.4f}", "TP3": "{:.4f}", "TP4": "{:.4f}", "TP5": "{:.4f}"}), use_container_width=True, hide_index=True)
        st.subheader("Take Profit Zone")
        df_tp_zones = calculate_tp_zones(df_plan)
        if not df_tp_zones.empty:
            st.dataframe(df_tp_zones, use_container_width=True, hide_index=True)
        else: st.warning("Could not calculate TP zones. Please ensure SL and TP values are set correctly.")
    else:
        st.info("No active trade plan. Please configure a plan in the sidebar.")

# ======================= SEC 3, 4, 5, 6 (Placeholders for now) =======================
with st.expander("📈 Chart Visualizer", expanded=True):
    st.info("Chart will be displayed here, based on the plan above.")
with st.expander("📂 Statement Import", expanded=False):
    st.info("Statement import functionality will be connected to the active portfolio.")
with st.expander("💡 Dashboard (ภาพรวม)", expanded=False):
    st.info("Dashboard analytics will be refactored based on the active portfolio's data.")
with st.expander("📚 Trade Log Viewer (แผนเทรด)", expanded=False):
    st.info("Log viewer will be refactored to filter by active portfolio.")
