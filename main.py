# ===================== SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import openpyxl
import numpy as np
import os
from datetime import datetime
import plotly.express as px
import google.generativeai as genai
import gspread
import plotly.graph_objects as go
import yfinance as yf
import random # For LogID generation
import csv

st.set_page_config(page_title="Ultimate-Chart", layout="wide")
acc_balance = 10000

# กำหนดชื่อ Google Sheet และ Worksheet ที่จะใช้เก็บข้อมูล Statement
GOOGLE_SHEET_NAME = "TradeLog"
WORKSHEET_PORTFOLIOS = "Portfolios"
WORKSHEET_PLANNED_LOGS = "PlannedTradeLogs"
#WORKSHEET_UPLOADED_STATEMENTS = "Uploaded Statements"
WORKSHEET_ACTUAL_TRADES = "ActualTrades"
WORKSHEET_ACTUAL_ORDERS = "ActualOrders"
WORKSHEET_ACTUAL_POSITIONS = "ActualPositions"
WORKSHEET_STATEMENT_SUMMARIES = "StatementSummaries" 

# ฟังก์ชันสำหรับเชื่อมต่อ gspread (ยังคงเดิม)
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

# --- **ฟังก์ชันใหม่สำหรับโหลดข้อมูล Portfolios** ---
@st.cache_data(ttl=600) # Cache ข้อมูลไว้ 10 นาที
def load_portfolios_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        return pd.DataFrame()

    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PORTFOLIOS)
        records = worksheet.get_all_records()
        
        if not records:
            # st.sidebar.warning(f"ไม่พบข้อมูลใน Worksheet '{WORKSHEET_PORTFOLIOS}' หรือ Worksheet ว่างเปล่า กรุณาเพิ่มข้อมูล Portfolio") # Commented out as it might be too verbose in sidebar
            return pd.DataFrame()
        
        df_portfolios = pd.DataFrame(records)
        
        cols_to_numeric = ['InitialBalance', 'ProfitTargetPercent', 'DailyLossLimitPercent', 'TotalStopoutPercent', 'ScalingProfitTargetPercent']
        for col in cols_to_numeric:
            if col in df_portfolios.columns:
                df_portfolios[col] = pd.to_numeric(df_portfolios[col], errors='coerce').fillna(0)

        return df_portfolios
    except gspread.exceptions.WorksheetNotFound:
        st.sidebar.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'.")
        st.sidebar.info(f"กรุณาสร้าง Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}' และใส่หัวคอลัมน์พร้อมข้อมูลตัวอย่าง")
        return pd.DataFrame()
    except Exception as e:
        st.sidebar.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios: {e}")
        return pd.DataFrame()

# (Existing load_statement_from_gsheets and save_statement_to_gsheets can remain here if needed for other functionalities)
# ...

# ===================== SEC 1: PORTFOLIO MANAGEMENT =======================
# (ส่วนนี้รวมการจัดการพอร์ตใน Sidebar)

# PORTFOLIO_FILE = 'portfolios.csv' # This local CSV for portfolios is now superseded by Google Sheets

# --- โหลดข้อมูลพอร์ตทั้งหมดที่มีจาก Google Sheets ---
df_portfolios_gs = load_portfolios_from_gsheets()

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

# เพิ่มการตรวจสอบและกำหนดค่าเริ่มต้นที่แข็งแกร่งขึ้นสำหรับ session_state ของพอร์ต
if 'active_portfolio_name_gs' not in st.session_state:
    st.session_state.active_portfolio_name_gs = "" # ค่าเริ่มต้นเป็น string ว่าง
if 'active_portfolio_id_gs' not in st.session_state:
    st.session_state.active_portfolio_id_gs = None # ค่าเริ่มต้นเป็น None

# สร้างรายการชื่อพอร์ตสำหรับ selectbox
# ตรวจสอบว่า df_portfolios_gs ไม่ว่างเปล่าและมีคอลัมน์ 'PortfolioName' ก่อนที่จะดำเนินการ
portfolio_names_list_gs = [""]
if not df_portfolios_gs.empty and 'PortfolioName' in df_portfolios_gs.columns:
    portfolio_names_list_gs.extend(sorted(df_portfolios_gs['PortfolioName'].dropna().unique().tolist()))

# ตรวจสอบว่าค่าใน session_state ยังอยู่ใน options ที่มีอยู่หรือไม่
if st.session_state.active_portfolio_name_gs not in portfolio_names_list_gs:
    st.session_state.active_portfolio_name_gs = portfolio_names_list_gs[0] # ตั้งค่ากลับไปที่ตัวเลือกแรกหากไม่ถูกต้อง

selected_portfolio_name_gs = st.sidebar.selectbox(
    "เลือกพอร์ต:",
    options=portfolio_names_list_gs,
    index=portfolio_names_list_gs.index(st.session_state.active_portfolio_name_gs),
    key='sb_active_portfolio_selector_gs'
)

# อัปเดต session_state เมื่อมีการเลือกพอร์ต
if selected_portfolio_name_gs != "":
    st.session_state.active_portfolio_name_gs = selected_portfolio_name_gs
    # ดึง PortfolioID จาก DataFrame ที่โหลดมา
    selected_portfolio_row = df_portfolios_gs[df_portfolios_gs['PortfolioName'] == selected_portfolio_name_gs]
    if not selected_portfolio_row.empty and 'PortfolioID' in selected_portfolio_row.columns:
        st.session_state.active_portfolio_id_gs = selected_portfolio_row['PortfolioID'].iloc[0]
    else:
        st.session_state.active_portfolio_id_gs = None
        st.sidebar.warning("ไม่พบ PortfolioID สำหรับพอร์ตที่เลือก. กรุณาตรวจสอบข้อมูลในชีต 'Portfolios'.")
else: # ถ้าเลือกตัวเลือกว่าง ("")
    st.session_state.active_portfolio_name_gs = ""
    st.session_state.active_portfolio_id_gs = None

# แสดงกฎเกณฑ์ของพอร์ตที่เลือก
if st.session_state.active_portfolio_name_gs and not df_portfolios_gs.empty:
    current_portfolio_rules = df_portfolios_gs[df_portfolios_gs['PortfolioName'] == st.session_state.active_portfolio_name_gs]
    if not current_portfolio_rules.empty:
        st.sidebar.markdown(f"**💡 ข้อมูลพอร์ต '{st.session_state.active_portfolio_name_gs}'**")
        # ตรวจสอบว่าคอลัมน์มีอยู่ก่อนแสดง
        if 'InitialBalance' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Initial Balance:** {current_portfolio_rules['InitialBalance'].iloc[0]:,.2f} USD")
        if 'ProfitTargetPercent' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Profit Target:** {current_portfolio_rules['ProfitTargetPercent'].iloc[0]:.1f}%")
        if 'DailyLossLimitPercent' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Daily Loss Limit:** {current_portfolio_rules['DailyLossLimitPercent'].iloc[0]:.1f}%")
        if 'TotalStopoutPercent' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Total Stopout:** {current_portfolio_rules['TotalStopoutPercent'].iloc[0]:.1f}%")
        if 'Status' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Status:** {current_portfolio_rules['Status'].iloc[0]}")
    else:
        st.sidebar.warning("ไม่พบรายละเอียดสำหรับพอร์ตที่เลือก.")
elif df_portfolios_gs.empty:
    st.sidebar.warning("ไม่พบข้อมูล Portfolio ใน Google Sheets หรือเกิดข้อผิดพลาดในการโหลด.")
    st.sidebar.info("กรุณาเพิ่มข้อมูลในชีต 'Portfolios' และตรวจสอบการตั้งค่า Google Sheets.")

# --- UI for managing portfolios (can be enhanced later per Phase 4.1) ---
# with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)"):
#     # This section would need to be updated to interact with Google Sheets
#     # For now, managing portfolios is done directly in Google Sheets as per initial setup.
#     # st.info("การจัดการพอร์ต (เพิ่ม/แก้ไข) ทำได้โดยตรงใน Google Sheet 'Portfolios'")
#     # if not df_portfolios_gs.empty:
#     #     st.dataframe(df_portfolios_gs, use_container_width=True, hide_index=True)
#     # else:
#     #    st.info("ยังไม่มีข้อมูลพอร์ตใน Google Sheets")

# ========== Function Utility ==========
# log_file = 'trade_log.csv' # This will be less used for planned trades.
# Functions like get_today_drawdown, get_performance might need updating later
# to use Google Sheets data if they are for *planned* trades.
# For now, they might reflect local CSV if it's still used for other purposes or historical data.

def get_today_drawdown(log_source_df, acc_balance): # Now accepts a DataFrame
    if log_source_df.empty:
        return 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    # Ensure 'Timestamp' is datetime for comparison, and 'Risk $' is numeric
    try: # Add try-except for robustness if columns are missing or data is malformed
        log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)

        df_today = log_source_df[log_source_df["Timestamp"].dt.strftime("%Y-%m-%d") == today_str]
        drawdown = df_today["Risk $"].sum()
        return drawdown
    except KeyError as e:
        # st.warning(f"Missing expected column for drawdown calculation: {e}") # Can be noisy
        return 0
    except Exception as e:
        # st.error(f"Error in get_today_drawdown: {e}")
        return 0


def get_performance(log_source_df, mode="week"): # Now accepts a DataFrame
    if log_source_df.empty:
        return 0, 0, 0
    
    try: # Add try-except
        log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)
        now = datetime.now()

        if mode == "week":
            week_start_date = now - pd.Timedelta(days=now.weekday())
            df_period = log_source_df[log_source_df["Timestamp"] >= week_start_date]
        else:  # month
            month_start_date = now.replace(day=1)
            df_period = log_source_df[log_source_df["Timestamp"] >= month_start_date]
        
        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0]
        total_trades = win + loss
        winrate = (100 * win / total_trades) if total_trades > 0 else 0
        gain = df_period["Risk $"].sum()
        return winrate, gain, total_trades
    except KeyError as e:
        # st.warning(f"Missing expected column for performance calculation: {e}")
        return 0,0,0
    except Exception as e:
        # st.error(f"Error in get_performance: {e}")
        return 0,0,0


# ===================== SEC 2: SIDEBAR - TRADE SETUP & INPUTS =======================
# (ส่วนนี้รวมการตั้งค่าพื้นฐานและ Input สำหรับแผนเทรดใน Sidebar)
st.sidebar.header("🎛️ Trade Setup")

# ===================== SEC 2.1: COMMON INPUTS & MODE SELECTION =======================
# (ส่วนนี้รวม Drawdown Limit, Trade Mode, และ Reset Form)
drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=st.session_state.get("drawdown_limit_pct", 2.0), # Use session state for persistence
    step=0.1, format="%.1f",
    key="drawdown_limit_pct" # Add key for session state
)

mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")


if st.sidebar.button("🔄 Reset Form"):
    # Keep essential settings if needed, or clear more selectively
    risk_keep = st.session_state.get("risk_pct", 1.0)
    asset_keep = st.session_state.get("asset", "XAUUSD")
    drawdown_limit_keep = st.session_state.get("drawdown_limit_pct", 2.0)
    
    # Define keys to keep explicitly
    keys_to_keep = {"risk_pct", "asset", "drawdown_limit_pct", "mode", 
                    "active_portfolio_name_gs", "active_portfolio_id_gs", # Keep portfolio selection
                    "gcp_service_account"} # Keep secrets related keys

    # More robust session state clearing
    for k in list(st.session_state.keys()):
        if k not in keys_to_keep:
            del st.session_state[k]

    # Restore or set defaults for specific items if needed
    st.session_state["risk_pct"] = risk_keep
    st.session_state["asset"] = asset_keep
    st.session_state["drawdown_limit_pct"] = drawdown_limit_keep
    st.session_state["fibo_flags"] = [False] * 5 # Reset Fibo flags

    st.rerun()

# ===================== SEC 2.2: FIBO TRADE DETAILS =======================
if mode == "FIBO":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value=st.session_state.get("asset", "XAUUSD"), key="asset")
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            value=st.session_state.get("risk_pct", 1.0), # Use session state
            step=0.01,
            format="%.2f",
            key="risk_pct" # Add key
        )
    with col3:
        # Ensure direction uses session_state or has a key for persistence if needed
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True, key="fibo_direction")


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
        st.session_state.fibo_flags = [True] * len(fibos) # Default all true or as desired

    fibo_selected_flags = [] # Renamed to avoid conflict if 'fibo_selected' is used elsewhere
    for i, col in enumerate(cols):
        checked = col.checkbox(labels[i], value=st.session_state.fibo_flags[i], key=f"fibo_cb_{i}")
        fibo_selected_flags.append(checked)

    st.session_state.fibo_flags = fibo_selected_flags

    try:
        high_val = float(swing_high) if swing_high else 0
        low_val = float(swing_low) if swing_low else 0
        if swing_high and swing_low and high_val <= low_val: # Check if inputs are provided
            st.sidebar.warning("High ต้องมากกว่า Low!")
    except ValueError:
        if swing_high or swing_low: # Show error only if there's an attempt to input
            st.sidebar.warning("กรุณาใส่ High/Low เป็นตัวเลขที่ถูกต้อง")
    except Exception:
        pass # General catch

    if 'risk_pct' in st.session_state and st.session_state.risk_pct <= 0: # Check session state
        st.sidebar.warning("Risk% ต้องมากกว่า 0")

    st.sidebar.markdown("---")
    try:
        high_preview = float(swing_high)
        low_preview = float(swing_low)
        if high_preview > low_preview and any(st.session_state.fibo_flags):
            st.sidebar.markdown("**Preview (เบื้องต้น):**")
            first_selected_fibo_index = st.session_state.fibo_flags.index(True)
            if direction == "Long": # Use session state for direction if it's keyed
                preview_entry = low_preview + (high_preview - low_preview) * fibos[first_selected_fibo_index]
            else:
                preview_entry = high_preview - (high_preview - low_preview) * fibos[first_selected_fibo_index]
            st.sidebar.markdown(f"Entry แรกที่เลือก ≈ **{preview_entry:.2f}**")
            st.sidebar.caption("Lot/TP/ผลลัพธ์เต็มอยู่ด้านล่าง (ใน Strategy Summary)")
    except Exception: # Catch errors if swing_high/low are not valid numbers or no fibo selected
        pass

    save_fibo = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo")

# ===================== SEC 2.3: CUSTOM TRADE DETAILS =======================
elif mode == "CUSTOM":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value=st.session_state.get("asset", "XAUUSD"), key="asset_custom") # Use different key if needed
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            value=st.session_state.get("risk_pct_custom", 1.00), # Use session state
            step=0.01,
            format="%.2f",
            key="risk_pct_custom" # Add key
        )
    with col3:
        n_entry = st.number_input(
            "จำนวนไม้",
            min_value=1,
            max_value=10,
            value=st.session_state.get("n_entry_custom", 2), # Use session state
            step=1,
            key="n_entry_custom" # Add key
        )

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")
    custom_inputs = []
    # Use risk_pct from session_state for calculations
    current_custom_risk_pct = st.session_state.get("risk_pct_custom", 1.0)
    risk_per_trade = current_custom_risk_pct / 100
    risk_dollar_total = acc_balance * risk_per_trade
    num_entries_val = st.session_state.get("n_entry_custom", 1) # Get from session state
    risk_dollar_per_entry = risk_dollar_total / num_entries_val if num_entries_val > 0 else 0

    for i in range(int(num_entries_val)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e, col_s, col_t = st.sidebar.columns(3)
        with col_e:
            entry = st.text_input(f"Entry {i+1}", value=st.session_state.get(f"custom_entry_{i}", "0.00"), key=f"custom_entry_{i}")
        with col_s:
            sl = st.text_input(f"SL {i+1}", value=st.session_state.get(f"custom_sl_{i}", "0.00"), key=f"custom_sl_{i}")
        with col_t:
            tp = st.text_input(f"TP {i+1}", value=st.session_state.get(f"custom_tp_{i}", "0.00"), key=f"custom_tp_{i}")
        
        try:
            entry_val = float(entry)
            sl_val = float(sl)
            stop = abs(entry_val - sl_val)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            lot_display = f"Lot: {lot:.2f}" if stop > 0 else "Lot: - (Invalid SL)"
            risk_per_entry_display = f"Risk$ ต่อไม้: {risk_dollar_per_entry:.2f}"
        except ValueError: # Handle cases where entry/sl are not numbers
            lot_display = "Lot: - (Error)"
            risk_per_entry_display = "Risk$ ต่อไม้: - (Error)"
            stop = None # Ensure stop is None if there's an error
        except Exception: # General catch
            lot_display = "Lot: -"
            risk_per_entry_display = "Risk$ ต่อไม้: -"
            stop = None

        try: # Separate try-except for TP calculation for clarity
            if stop is not None and stop > 0:
                # For CUSTOM, direction is not explicitly set like FIBO. Assume user knows.
                # Or add a direction radio for Custom mode as well.
                # For now, let's assume TP RR=3 means 3 times the stop distance.
                # User needs to ensure TP is on the correct side of Entry.
                # A simple placeholder or instruction might be better than assuming direction.
                tp_rr3_info = f"Stop: {stop:.2f}" # Example, provide useful info
            else:
                tp_rr3_info = "TP (RR=3): - (SL Error)"
        except Exception:
            tp_rr3_info = "TP (RR=3): -"
        
        st.sidebar.caption(f"{lot_display} | {risk_per_entry_display} | {tp_rr3_info}")
        custom_inputs.append({"entry": entry, "sl": sl, "tp": tp})

    if current_custom_risk_pct <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")
    save_custom = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom")

# ===================== SEC 3: SIDEBAR - CALCULATIONS, SUMMARY & ACTIONS =======================
# (ส่วนนี้รวม Strategy Summary, Scaling Manager, และ Save Plan Action)
st.sidebar.markdown("---") # Separator before summary
st.sidebar.markdown("### 🧾 Strategy Summary")

entry_data = [] # Initialize to ensure it's defined
custom_entries_summary = [] # Initialize for custom mode summary

if mode == "FIBO":
    try:
        # Ensure swing_high, swing_low, fibo_selected_flags, direction are from current inputs/session_state
        # For example, fibo_selected_flags comes from st.session_state.fibo_flags
        # direction comes from st.session_state.fibo_direction
        current_fibo_risk_pct = st.session_state.get("risk_pct", 1.0)
        current_fibo_direction = st.session_state.get("fibo_direction", "Long")
        current_swing_high = st.session_state.get("swing_high", "")
        current_swing_low = st.session_state.get("swing_low", "")
        current_fibo_flags = st.session_state.get("fibo_flags", [False]*5)

        high = float(current_swing_high)
        low = float(current_swing_low)
        selected_fibo_levels = [fibos[i] for i, sel in enumerate(current_fibo_flags) if sel]
        n = len(selected_fibo_levels)
        risk_per_trade = current_fibo_risk_pct / 100
        risk_dollar_total = acc_balance * risk_per_trade
        risk_dollar_per_entry = risk_dollar_total / n if n > 0 else 0
        
        for idx, fibo_level_val in enumerate(selected_fibo_levels): # Renamed fibo to fibo_level_val
            if current_fibo_direction == "Long":
                entry = low + (high - low) * fibo_level_val
                # Simplified SL logic, adjust as per your strategy
                sl = low # Example: SL at swing low for all long entries
            else: # Short
                entry = high - (high - low) * fibo_level_val
                sl = high # Example: SL at swing high for all short entries
            
            stop = abs(entry - sl)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            risk_val = stop * lot if stop > 0 else 0 # Risk amount for this entry

            # TP logic for Fibo (e.g., Fibo extension or fixed RR)
            # For this example, let's use a fixed RR of 1.618 for TP like before
            if stop > 0:
                if current_fibo_direction == "Long":
                    tp1 = entry + (stop * 1.618)
                else: # Short
                    tp1 = entry - (stop * 1.618)
                tp_display = f"{tp1:.2f}"
            else:
                tp_display = "-"


            entry_data.append({
                "Fibo Level": f"{fibo_level_val:.3f}",
                "Entry": f"{entry:.2f}",
                "SL": f"{sl:.2f}",
                "TP": tp_display, 
                "Lot": f"{lot:.2f}" if stop > 0 else "0.00",
                "Risk $": f"{risk_val:.2f}" if stop > 0 else "0.00",
            })
        if entry_data:
            entry_df_summary = pd.DataFrame(entry_data) # Use a different variable name
            st.sidebar.write(f"**Total Lots:** {entry_df_summary['Lot'].astype(float).sum():.2f}")
            st.sidebar.write(f"**Total Risk $:** {entry_df_summary['Risk $'].astype(float).sum():.2f}")
    except ValueError: # Catch error if high/low are not valid numbers
        if current_swing_high or current_swing_low: # Only show if input was attempted
             st.sidebar.warning("กรอก High/Low ให้ถูกต้องเพื่อดู Summary")
    except Exception as e: # General catch for other errors
        # st.sidebar.error(f"Error calculating Fibo summary: {e}") # Can be too verbose
        pass 
elif mode == "CUSTOM":
    try:
        # Use values from session_state for n_entry, risk_pct_custom
        num_entries_val_summary = st.session_state.get("n_entry_custom", 1)
        current_custom_risk_pct_summary = st.session_state.get("risk_pct_custom", 1.0)

        risk_per_trade_summary = current_custom_risk_pct_summary / 100
        risk_dollar_total_summary = acc_balance * risk_per_trade_summary
        risk_dollar_per_entry_summary = risk_dollar_total_summary / num_entries_val_summary if num_entries_val_summary > 0 else 0
        
        rr_list = []
        for i in range(int(num_entries_val_summary)):
            # Get entry, sl, tp from session_state
            entry_val_str = st.session_state.get(f"custom_entry_{i}", "0.00")
            sl_val_str = st.session_state.get(f"custom_sl_{i}", "0.00")
            tp_val_str = st.session_state.get(f"custom_tp_{i}", "0.00")

            entry_val = float(entry_val_str)
            sl_val = float(sl_val_str)
            tp_val = float(tp_val_str)

            stop = abs(entry_val - sl_val)
            target = abs(tp_val - entry_val)
            lot = risk_dollar_per_entry_summary / stop if stop > 0 else 0
            rr = (target / stop) if stop > 0 else 0
            rr_list.append(rr)
            custom_entries_summary.append({
                "Entry": f"{entry_val:.2f}",
                "SL": f"{sl_val:.2f}",
                "TP": f"{tp_val:.2f}",
                "Lot": f"{lot:.2f}" if stop > 0 else "0.00",
                "Risk $": f"{risk_dollar_per_entry_summary:.2f}" if stop > 0 else "0.00",
                "RR": f"{rr:.2f}" if stop > 0 else "0.00"
            })
        if custom_entries_summary:
            custom_df_summary = pd.DataFrame(custom_entries_summary) # Use different variable name
            st.sidebar.write(f"**Total Lots:** {custom_df_summary['Lot'].astype(float).sum():.2f}")
            st.sidebar.write(f"**Total Risk $:** {custom_df_summary['Risk $'].astype(float).sum():.2f}")
            avg_rr = np.mean([r for r in rr_list if r > 0]) if any(r > 0 for r in rr_list) else 0 # Avoid mean of empty or all zero
            if avg_rr > 0 :
                st.sidebar.write(f"**Average RR:** {avg_rr:.2f}")
    except ValueError: # Catch error if entry/sl/tp are not valid numbers
        st.sidebar.warning("กรอก Entry/SL/TP ให้ถูกต้องเพื่อดู Summary")
    except Exception as e: # General catch
        # st.sidebar.error(f"Error calculating Custom summary: {e}")
        pass

# ===================== SEC 3.1: SCALING MANAGER =======================
# (ส่วนนี้รวม Scaling Manager Settings และ Scaling Suggestion)
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    # Use session_state for scaling settings persistence
    scaling_step = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=1.0, 
        value=st.session_state.get('scaling_step', 0.25), 
        step=0.01, format="%.2f", key='scaling_step'
    )
    min_risk_pct = st.number_input(
        "Minimum Risk %", min_value=0.01, max_value=100.0, 
        value=st.session_state.get('min_risk_pct', 0.5), 
        step=0.01, format="%.2f", key='min_risk_pct'
    )
    max_risk_pct = st.number_input(
        "Maximum Risk %", min_value=0.01, max_value=100.0, 
        value=st.session_state.get('max_risk_pct', 5.0), 
        step=0.01, format="%.2f", key='max_risk_pct'
    )
    scaling_mode = st.radio(
        "Scaling Mode", ["Manual", "Auto"], 
        index=0 if st.session_state.get('scaling_mode', 'Manual') == 'Manual' else 1,
        horizontal=True, key='scaling_mode'
    )

# ===================== SEC 3.1.1: SCALING SUGGESTION LOGIC =======================
# (ส่วนนี้คือ Logic การคำนวณและแสดงผล Scaling Suggestion)
df_planned_logs_for_scaling = pd.DataFrame()
gc_scaling = get_gspread_client()
if gc_scaling:
    try:
        sh_scaling = gc_scaling.open(GOOGLE_SHEET_NAME)
        ws_planned_logs = sh_scaling.worksheet(WORKSHEET_PLANNED_LOGS)
        records_scaling = ws_planned_logs.get_all_records()
        if records_scaling:
            df_planned_logs_for_scaling = pd.DataFrame(records_scaling)
    except Exception as e:
        # st.sidebar.warning(f"Could not load planned logs for scaling: {e}") # Can be noisy
        pass

winrate_perf, gain_perf, total_trades_perf = get_performance(df_planned_logs_for_scaling.copy(), mode="week") # use .copy()

# Get current risk based on mode (FIBO or CUSTOM)
current_risk_for_scaling = 1.0 # Default
if mode == "FIBO":
    current_risk_for_scaling = st.session_state.get("risk_pct", 1.0)
elif mode == "CUSTOM":
    current_risk_for_scaling = st.session_state.get("risk_pct_custom", 1.0)

# Get scaling parameters from session_state
scaling_step_val = st.session_state.get('scaling_step', 0.25)
max_risk_pct_val = st.session_state.get('max_risk_pct', 5.0)
min_risk_pct_val = st.session_state.get('min_risk_pct', 0.5)
current_scaling_mode = st.session_state.get('scaling_mode', 'Manual')

suggest_risk = current_risk_for_scaling # Default to current risk
scaling_msg = "Risk% คงที่ (ยังไม่มีข้อมูล Performance เพียงพอ หรือ Performance อยู่ในเกณฑ์)"

if total_trades_perf > 0: # Only suggest if there's performance data
    if winrate_perf > 55 and gain_perf > 0.02 * acc_balance: # Example criteria
        suggest_risk = min(current_risk_for_scaling + scaling_step_val, max_risk_pct_val)
        scaling_msg = f"🎉 ผลงานดี! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f}. แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}%"
    elif winrate_perf < 45 or gain_perf < 0: # Example criteria
        suggest_risk = max(current_risk_for_scaling - scaling_step_val, min_risk_pct_val)
        scaling_msg = f"⚠️ ควรลด Risk%! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f}. แนะนำลด Risk% เป็น {suggest_risk:.2f}%"
    else:
        scaling_msg = f"Risk% คงที่ (Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f})"

st.sidebar.info(scaling_msg)

if current_scaling_mode == "Manual" and abs(suggest_risk - current_risk_for_scaling) > 0.001: # Check for actual change
    if st.sidebar.button(f"ปรับ Risk% เป็น {suggest_risk:.2f}%"):
        if mode == "FIBO":
            st.session_state.risk_pct = suggest_risk
        elif mode == "CUSTOM":
            st.session_state.risk_pct_custom = suggest_risk
        st.rerun()
elif current_scaling_mode == "Auto":
    if abs(suggest_risk - current_risk_for_scaling) > 0.001: # Apply only if different
        if mode == "FIBO":
            st.session_state.risk_pct = suggest_risk
        elif mode == "CUSTOM":
            st.session_state.risk_pct_custom = suggest_risk
        # st.rerun() # Auto-rerun might be disruptive, consider if needed

# ===================== SEC 3.2: SAVE PLAN ACTION & DRAWDOWN LOCK =======================
# (ส่วนนี้รวม Logic การบันทึกแผน และการตรวจสอบ Drawdown Limit)

# --- ฟังก์ชันสำหรับบันทึก Plan ลง Google Sheets ---
def save_plan_to_gsheets(plan_data_list, trade_mode_arg, asset_name, risk_percentage, trade_direction, portfolio_id, portfolio_name):
    gc = get_gspread_client()
    if not gc:
        st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกแผนได้")
        return False
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        timestamp_now = datetime.now()
        rows_to_append = []
        expected_headers = [
            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",
            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"
        ]
        current_headers = []
        if ws.row_count > 0: # Check if sheet has any rows
            try:
                current_headers = ws.row_values(1) # Try to get first row
            except Exception: # Handle if sheet is completely empty or inaccessible
                current_headers = []
        
        if not current_headers or all(h == "" for h in current_headers) : # If no headers or all are empty
            ws.append_row(expected_headers, value_input_option='USER_ENTERED') # Add headers if missing
        elif set(current_headers) != set(expected_headers) and any(h!="" for h in current_headers):
            # Headers exist but are incorrect, warn user or attempt to fix (carefully)
            st.warning(f"Worksheet '{WORKSHEET_PLANNED_LOGS}' has incorrect headers. Please ensure headers match: {', '.join(expected_headers)}")
            # For safety, don't automatically clear and reset if there's data with wrong headers.
            # return False # Or handle as an error

        for idx, plan_entry in enumerate(plan_data_list):
            log_id = f"{timestamp_now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}-{idx}"
            row_data = {
                "LogID": log_id,
                "PortfolioID": portfolio_id,
                "PortfolioName": portfolio_name,
                "Timestamp": timestamp_now.strftime("%Y-%m-%d %H:%M:%S"),
                "Asset": asset_name,
                "Mode": trade_mode_arg,
                "Direction": trade_direction,
                "Risk %": risk_percentage,
                "Fibo Level": plan_entry.get("Fibo Level", ""),
                "Entry": plan_entry.get("Entry", "0.00"),
                "SL": plan_entry.get("SL", "0.00"),
                "TP": plan_entry.get("TP", "0.00"),
                "Lot": plan_entry.get("Lot", "0.00"),
                "Risk $": plan_entry.get("Risk $", "0.00"),
                "RR": plan_entry.get("RR", "")
            }
            rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers]) # Ensure order and convert to string

        if rows_to_append:
            ws.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            return True
        return False
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PLANNED_LOGS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกแผนไปยัง Google Sheets: {e}")
        return False

# Load current day's drawdown from Google Sheets
df_drawdown_check = pd.DataFrame()
gc_drawdown = get_gspread_client()
if gc_drawdown:
    try:
        sh_drawdown = gc_drawdown.open(GOOGLE_SHEET_NAME)
        ws_planned_logs_drawdown = sh_drawdown.worksheet(WORKSHEET_PLANNED_LOGS)
        records_drawdown = ws_planned_logs_drawdown.get_all_records()
        if records_drawdown:
            df_drawdown_check = pd.DataFrame(records_drawdown)
    except Exception as e:
        # st.sidebar.warning(f"Could not load planned logs for drawdown check: {e}") # Can be noisy
        pass

drawdown_today = get_today_drawdown(df_drawdown_check.copy(), acc_balance)
drawdown_limit_pct_val = st.session_state.get('drawdown_limit_pct', 2.0)
drawdown_limit_abs = -acc_balance * (drawdown_limit_pct_val / 100) # Absolute loss limit

# Display current drawdown status
if drawdown_today < 0: # Assuming drawdown is negative for losses
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** <font color='red'>{drawdown_today:,.2f} USD</font>", unsafe_allow_html=True)
else: # No loss or a gain (if Risk $ can be positive)
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** {drawdown_today:,.2f} USD")


# --- Save Plan Logic ---
active_portfolio_id = st.session_state.get('active_portfolio_id_gs', None)
active_portfolio_name = st.session_state.get('active_portfolio_name_gs', None)

# Determine asset and risk_pct for saving based on current mode
asset_to_save = ""
risk_pct_to_save = 0.0
direction_to_save = "N/A"
data_to_save = []

if mode == "FIBO":
    asset_to_save = st.session_state.get("asset", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct", 1.0)
    direction_to_save = st.session_state.get("fibo_direction", "Long")
    data_to_save = entry_data # This should be the calculated entry_data from Strategy Summary section
    save_button_pressed = save_fibo # save_fibo is the button state
elif mode == "CUSTOM":
    asset_to_save = st.session_state.get("asset_custom", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct_custom", 1.0)
    # For custom, direction might be per entry or general. Using a general one for now.
    direction_to_save = st.session_state.get("custom_direction_for_log", "N/A") # Assuming this key exists if custom direction is used
    data_to_save = custom_entries_summary # This should be from Strategy Summary
    save_button_pressed = save_custom # save_custom is the button state


if save_button_pressed and data_to_save: # Check if button was pressed and there's data
    if drawdown_today <= drawdown_limit_abs and drawdown_limit_abs < 0 :
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนจากแผนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit_abs):,.2f} ({drawdown_limit_pct_val:.1f}%)"
        )
    elif not active_portfolio_id:
        st.sidebar.error("กรุณาเลือกพอร์ตที่ใช้งานก่อนบันทึกแผน")
    else:
        try:
            if save_plan_to_gsheets(data_to_save, mode, asset_to_save, risk_pct_to_save, direction_to_save, active_portfolio_id, active_portfolio_name):
                st.sidebar.success(f"บันทึกแผน ({mode}) สำหรับพอร์ต '{active_portfolio_name}' ลง Google Sheets สำเร็จ!")
                st.balloons()
            else:
                st.sidebar.error(f"Save ({mode}) ไปยัง Google Sheets ไม่สำเร็จ.")
        except Exception as e:
            st.sidebar.error(f"Save ({mode}) ไม่สำเร็จ: {e}")


# ===================== SEC 4: MAIN AREA - ENTRY PLAN DETAILS TABLE =======================
with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):
    if mode == "FIBO":
        col1_main, col2_main = st.columns(2) # Renamed to avoid conflict with sidebar cols
        with col1_main:
            st.markdown("### 🎯 Entry Levels (FIBO)")
            if entry_data: # entry_data from summary calculation
                entry_df_main = pd.DataFrame(entry_data) # Use different var name
                st.dataframe(entry_df_main, hide_index=True, use_container_width=True)
            else:
                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level ใน Sidebar เพื่อดู Entry Levels.")
        with col2_main:
            st.markdown("### 🎯 Take Profit Zones (FIBO)")
            try:
                # Use values from session state for TP calculation
                current_swing_high_tp = st.session_state.get("swing_high", "")
                current_swing_low_tp = st.session_state.get("swing_low", "")
                current_fibo_direction_tp = st.session_state.get("fibo_direction", "Long")

                high_tp = float(current_swing_high_tp)
                low_tp = float(current_swing_low_tp)

                if high_tp > low_tp:
                    if current_fibo_direction_tp == "Long":
                        tp1_main = low_tp + (high_tp - low_tp) * 1.618
                        tp2_main = low_tp + (high_tp - low_tp) * 2.618
                        tp3_main = low_tp + (high_tp - low_tp) * 4.236
                    else: # Short
                        tp1_main = high_tp - (high_tp - low_tp) * 1.618
                        tp2_main = high_tp - (high_tp - low_tp) * 2.618
                        tp3_main = high_tp - (high_tp - low_tp) * 4.236
                    tp_df_main = pd.DataFrame({
                        "TP Zone": ["TP1 (1.618)", "TP2 (2.618)", "TP3 (4.236)"],
                        "Price": [f"{tp1_main:.2f}", f"{tp2_main:.2f}", f"{tp3_main:.2f}"]
                    })
                    st.dataframe(tp_df_main, hide_index=True, use_container_width=True)
                else:
                    if current_swing_high_tp or current_swing_low_tp : # Show only if inputs are attempted
                        st.warning("📌 High ต้องมากกว่า Low เพื่อคำนวณ TP.")
                    else:
                        st.info("📌 กรอก High/Low ใน Sidebar เพื่อดู TP.")
            except ValueError: # If high/low cannot be converted to float
                 if current_swing_high_tp or current_swing_low_tp :
                    st.warning("📌 กรอก High/Low เป็นตัวเลขที่ถูกต้องเพื่อคำนวณ TP.")
                 else:
                    st.info("📌 กรอก High/Low ใน Sidebar เพื่อดู TP.")
            except Exception: # General catch
                st.info("📌 เกิดข้อผิดพลาดในการคำนวณ TP.")

    elif mode == "CUSTOM":
        st.markdown("### 🎯 Entry & Take Profit Zones (CUSTOM)")
        if custom_entries_summary: # custom_entries_summary from summary calculation
            custom_df_main = pd.DataFrame(custom_entries_summary) # Use different var name
            st.dataframe(custom_df_main, hide_index=True, use_container_width=True)
            # RR Warning
            for i, row_data_dict in enumerate(custom_entries_summary): # Iterate over list of dicts
                try:
                    rr_val_str = row_data_dict.get("RR", "0") # Get RR string from dict
                    rr_val = float(rr_val_str)
                    if rr_val < 2 and rr_val > 0: # Check if RR is low but valid
                        st.warning(f"🎯 Entry {i+1} มี RR ค่อนข้างต่ำ ({rr_val:.2f}) — ลองปรับ TP/SL เพื่อ Risk:Reward ที่ดีขึ้น")
                except ValueError: # If RR is not a valid number string
                    pass # Silently ignore if RR can't be converted
                except Exception:
                    pass # General catch
        else:
            st.info("กรอกข้อมูล Custom ใน Sidebar เพื่อดู Entry & TP Zones.")

# ===================== SEC 5: MAIN AREA - CHART VISUALIZER =======================
with st.expander("📈 Chart Visualizer", expanded=True):
    asset_to_display = "OANDA:XAUUSD" # Default
    # Logic to determine asset_to_display based on current mode and inputs
    current_asset_input = ""
    if mode == "FIBO":
        current_asset_input = st.session_state.get("asset", "XAUUSD")
    elif mode == "CUSTOM":
        current_asset_input = st.session_state.get("asset_custom", "XAUUSD")
    
    # Basic mapping (can be expanded)
    if current_asset_input.upper() == "XAUUSD":
        asset_to_display = "OANDA:XAUUSD"
    elif current_asset_input.upper() == "EURUSD":
        asset_to_display = "OANDA:EURUSD"
    elif current_asset_input: # If asset is something else, try using it directly
        asset_to_display = current_asset_input.upper() # Or map to specific broker symbols

    # Check if plot_data from log viewer is selected
    if 'plot_data' in st.session_state and st.session_state['plot_data']:
        asset_from_log = st.session_state['plot_data'].get('Asset', asset_to_display) # Fallback to current input asset
        if asset_from_log.upper() == "XAUUSD":
            asset_to_display = "OANDA:XAUUSD"
        elif asset_from_log.upper() == "EURUSD":
            asset_to_display = "OANDA:EURUSD"
        elif asset_from_log:
            asset_to_display = asset_from_log.upper()
        st.info(f"แสดงกราฟ TradingView สำหรับ: {asset_to_display} (จาก Log Viewer)")
    else:
        st.info(f"แสดงกราฟ TradingView สำหรับ: {asset_to_display} (จาก Input ปัจจุบัน)")

    tradingview_html = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_legendary"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%",
        "height": 600,
        "symbol": "{asset_to_display}",
        "interval": "15",
        "timezone": "Asia/Bangkok",
        "theme": "dark",
        "style": "1",
        "locale": "th",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "withdateranges": true,
        "allow_symbol_change": true,
        "hide_side_toolbar": false,
        "details": true,
        "hotlist": true,
        "calendar": true,
        "container_id": "tradingview_legendary"
      }});
      </script>
    </div>
    """
    st.components.v1.html(tradingview_html, height=620)

# ===================== SEC 6: MAIN AREA - AI ASSISTANT =======================
with st.expander("🤖 AI Assistant", expanded=True):
    # AI Assistant should use data from Google Sheets PlannedTradeLogs
    df_ai_logs = pd.DataFrame() # Default empty
    gc_ai = get_gspread_client()
    if gc_ai:
        try:
            sh_ai = gc_ai.open(GOOGLE_SHEET_NAME)
            ws_ai_logs = sh_ai.worksheet(WORKSHEET_PLANNED_LOGS)
            records_ai = ws_ai_logs.get_all_records()
            if records_ai:
                df_ai_logs = pd.DataFrame(records_ai)
                # Convert relevant columns
                if 'Risk $' in df_ai_logs.columns:
                    df_ai_logs['Risk $'] = pd.to_numeric(df_ai_logs['Risk $'], errors='coerce').fillna(0)
                if 'RR' in df_ai_logs.columns:
                    df_ai_logs['RR'] = pd.to_numeric(df_ai_logs['RR'], errors='coerce')
                if 'Timestamp' in df_ai_logs.columns:
                    df_ai_logs['Timestamp'] = pd.to_datetime(df_ai_logs['Timestamp'], errors='coerce')
        except Exception as e:
            # st.warning(f"Could not load Planned Logs for AI Assistant: {e}")
            pass
            
    if df_ai_logs.empty:
        st.info("ยังไม่มีข้อมูลแผนเทรดใน Log (Google Sheets) สำหรับ AI Assistant")
    else:
        total_trades_ai = df_ai_logs.shape[0]
        win_trades_ai = df_ai_logs[df_ai_logs["Risk $"] > 0].shape[0] if "Risk $" in df_ai_logs.columns else 0
        # loss_trades_ai = df_ai_logs[df_ai_logs["Risk $"] <= 0].shape[0] if "Risk $" in df_ai_logs.columns else 0
        winrate_ai = (100 * win_trades_ai / total_trades_ai) if total_trades_ai > 0 else 0
        gross_profit_ai = df_ai_logs["Risk $"].sum() if "Risk $" in df_ai_logs.columns else 0
        
        avg_rr_ai = df_ai_logs["RR"].mean() if "RR" in df_ai_logs.columns and not df_ai_logs["RR"].dropna().empty else None

        # Max Drawdown (simplified, based on cumulative sum of 'Risk $' in planned logs)
        max_drawdown_ai = 0
        if "Risk $" in df_ai_logs.columns:
            df_ai_logs_sorted = df_ai_logs.sort_values(by="Timestamp") if "Timestamp" in df_ai_logs.columns else df_ai_logs
            current_balance_sim = acc_balance # Start with initial balance
            peak_balance_sim = acc_balance
            for pnl_val in df_ai_logs_sorted["Risk $"]: # Assuming Risk $ is the P/L of that planned trade
                current_balance_sim += pnl_val
                if current_balance_sim > peak_balance_sim:
                    peak_balance_sim = current_balance_sim
                drawdown_val = peak_balance_sim - current_balance_sim
                if drawdown_val > max_drawdown_ai:
                    max_drawdown_ai = drawdown_val
        
        # Best/Worst Day
        win_day_ai = "-"
        loss_day_ai = "-"
        if "Timestamp" in df_ai_logs.columns and "Risk $" in df_ai_logs.columns and not df_ai_logs["Timestamp"].isnull().all():
            df_ai_logs["Weekday"] = df_ai_logs["Timestamp"].dt.day_name()
            daily_pnl = df_ai_logs.groupby("Weekday")["Risk $"].sum()
            if not daily_pnl.empty:
                win_day_ai = daily_pnl.idxmax() if daily_pnl.max() > 0 else "-"
                loss_day_ai = daily_pnl.idxmin() if daily_pnl.min() < 0 else "-"


        st.markdown("### 🧠 AI Intelligence Report (จากข้อมูลแผนเทรด)")
        st.write(f"- **จำนวนแผนเทรดทั้งหมด:** {total_trades_ai:,}")
        st.write(f"- **Winrate (ตามแผน):** {winrate_ai:.2f}% (คำนวณจาก Risk $ > 0)")
        st.write(f"- **กำไร/ขาดทุนสุทธิ (ตามแผน):** {gross_profit_ai:,.2f} USD")
        if avg_rr_ai is not None:
            st.write(f"- **RR เฉลี่ย (ตามแผน):** {avg_rr_ai:.2f}")
        st.write(f"- **Max Drawdown (จำลองจากแผน):** {max_drawdown_ai:,.2f} USD")
        st.write(f"- **วันที่ทำกำไรดีที่สุด (ตามแผน):** {win_day_ai}")
        st.write(f"- **วันที่ขาดทุนมากที่สุด (ตามแผน):** {loss_day_ai}")

        st.markdown("### 🤖 AI Insight (จากกฎที่คุณกำหนดเอง)")
        insight_messages = []
        if winrate_ai >= 60:
            insight_messages.append("✅ Winrate (ตามแผน) สูง: ระบบการวางแผนมีแนวโน้มที่ดี")
        elif winrate_ai < 40 and total_trades_ai > 10 : # Add condition for sufficient trades
            insight_messages.append("⚠️ Winrate (ตามแผน) ต่ำ: ควรทบทวนกลยุทธ์การวางแผน")
        
        if avg_rr_ai is not None and avg_rr_ai < 1.5 and total_trades_ai > 5: # Adjusted RR threshold
            insight_messages.append("📉 RR เฉลี่ย (ตามแผน) ต่ำกว่า 1.5: อาจต้องพิจารณาการตั้ง TP/SL เพื่อ Risk:Reward ที่เหมาะสมขึ้น")
        
        if max_drawdown_ai > acc_balance * 0.10: # Adjusted Drawdown threshold (e.g., 10% of account)
            insight_messages.append("🚨 Max Drawdown (จำลองจากแผน) ค่อนข้างสูง: ควรระมัดระวังการบริหารความเสี่ยง")
        
        if not insight_messages:
            insight_messages = ["ดูเหมือนว่าข้อมูลแผนเทรดปัจจุบันยังไม่มีจุดที่น่ากังวลเป็นพิเศษตามเกณฑ์ที่ตั้งไว้"]
        
        for msg in insight_messages:
            if "✅" in msg: st.success(msg)
            elif "⚠️" in msg or "📉" in msg: st.warning(msg)
            elif "🚨" in msg: st.error(msg)
            else: st.info(msg)

# ===================== SEC 7: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
# (This section corresponds to the expander "📂 SEC 7: Ultimate Statement Import & Processing")
with st.expander("📂 SEC 7: Ultimate Chart Dashboard Import & Processing", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # --- ฟังก์ชันสำหรับแยกข้อมูลจากเนื้อหาไฟล์ Statement (CSV) ---
    # ฟังก์ชันนี้ถูกปรับปรุงให้รับเนื้อหาไฟล์ทั้งหมด (string) และแยกส่วนต่างๆ
    def extract_data_from_report_content(file_content):
        extracted_data = {} # เยื้อง 4 ช่องว่าง

        # Define raw headers from the CSV report for identification
        section_raw_headers = {
            "Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit,",
            "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment,,",
            "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment",
        }
        
        # Define expected clean column names for each section (Hardcoded for robust parsing)
        expected_cleaned_columns = {
            "Positions": ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time", "Close_Price", "Commission", "Swap", "Profit"],
            "Orders": ["Open_Time", "Order", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time", "State", "Comment1", "Comment2", "Comment3"], # Handle extra commas in Comments
            "Deals": ["Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order", "Commission", "Fee", "Swap", "Profit", "Balance", "Comment"],
        }


        lines = file_content.strip().split('\n')
        
        section_order = ["Positions", "Orders", "Deals"]
        
        # Find the start line indices for each section's header
        section_start_indices = {}
        for section_name, header_template in section_raw_headers.items():
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                if line_stripped == header_template.strip() or \
                   (line_stripped.startswith(header_template.split(',')[0]) and \
                    len(line_stripped.split(',')) >= (len(header_template.split(',')) - 2) and \
                    len(line_stripped.split(',')) <= (len(header_template.split(',')) + 2)
                   ):
                    section_start_indices[section_name] = i
                    break
        
        # --- DEBUGGING: แสดง indices ที่เจอ ---
        # st.write("DEBUG: section_start_indices found:", section_start_indices)
        # --- END DEBUGGING ---

        dfs_output = {}
        # Parse collected table sections into DataFrames
        for i, section_name in enumerate(section_order):
            if section_name in section_start_indices:
                header_idx = section_start_indices[section_name]
                
                # Determine end_idx (start of next section or end of file before summaries)
                end_idx = len(lines)
                for j in range(i + 1, len(section_order)):
                    next_section_name = section_order[j]
                    if next_section_name in section_start_indices:
                        end_idx = section_start_indices[next_section_name]
                        break
                
                # Extract raw lines for this section
                raw_section_lines_block = lines[header_idx : end_idx]
                
                # --- Specific parsing for each table section ---
                # This part now directly uses pd.read_csv with skiprows and names
                
                # Find the first data line (which is concatenated with header)
                # It's at header_idx. We need to split this line.
                
                # Read the header line + first data line
                first_line_of_block = raw_section_lines_block[0]
                
                # Use csv.reader to correctly split the first line of the block
                try:
                    # current_line_parts will contain parts like ['Time', 'Position', ..., 'Profit', '2025.05.02...', '7213', ...]
                    current_line_parts = list(csv.reader(io.StringIO(first_line_of_block)))[0]
                except Exception as e_csv_reader_first_line:
                    st.error(f"❌ Critical Error: Could not parse the first line of '{section_name}' section with csv.reader: '{first_line_of_block.strip()}' ({e_csv_reader_first_line})")
                    dfs_output[section_key.lower()] = pd.DataFrame()
                    continue # Skip to next section if first line is broken

                header_template_parts_count = len(section_raw_headers[section_name].split(','))

                table_data_lines = []
                if len(current_line_parts) > header_template_parts_count:
                    # It's concatenated. Extract the data part.
                    first_data_row_extracted = current_line_parts[header_template_parts_count:]
                    table_data_lines.append(','.join(first_data_row_extracted)) # Add as a new row
                
                # Add all subsequent lines (from index 1 of raw_section_lines_block)
                # Filter out lines that are not data lines (e.g., summary keywords, blank lines)
                for line_val in raw_section_lines_block[1:]:
                    line_val_stripped = line_val.strip()
                    if not line_val_stripped: continue
                    
                    if line_val_stripped.startswith("Name:") or \
                       line_val_stripped.startswith("Account:") or \
                       line_val_stripped.startswith("Company:") or \
                       line_val_stripped.startswith("Date:") or \
                       line_val_stripped.startswith("Results") or \
                       line_val_stripped.startswith("Balance:") or \
                       line_val_stripped.startswith("Total Net Profit:"):
                       break
                    
                    table_data_lines.append(line_val) # These are already clean data lines

                csv_string_data_to_parse = "\n".join(table_data_lines)
                
                # DEBUG: Add this to see the CSV string being passed to pandas
                st.write(f"DEBUG: CSV string for {section_name} (before pandas):")
                st.code(csv_string_data_to_parse)

                if csv_string_data_to_parse.strip():
                    try:
                        # Use pandas to read the data. Provide column names explicitly.
                        # header=None and skiprows=0 (default) or not specified means pandas reads from first line given, assuming no header.
                        df = pd.read_csv(io.StringIO(csv_string_data_to_parse),
                                         sep=',',
                                         names=expected_cleaned_columns[section_name], # Use hardcoded names
                                         header=None, # Important: Tell pandas there's no header row in this string
                                         skipinitialspace=True,
                                         on_bad_lines='warn', # Warn but don't skip rows with errors
                                         engine='python') # Use Python engine for more flexibility
                        
                        # Remove 'Empty' columns (from Orders section)
                        df = df.loc[:, ~df.columns.str.startswith('Empty')]

                        # Drop rows that are entirely empty or contain only NaN values after parsing
                        df.dropna(how='all', inplace=True)
                        
                        dfs_output[section_name.lower()] = df
                    except ValueError as ve: # Catch if column count doesn't match names
                        st.error(f"❌ Column mismatch error in {section_name}: {ve}. Expected {len(expected_cleaned_columns[section_name])} columns, got different count in data.")
                        dfs_output[section_key.lower()] = pd.DataFrame()
                    except Exception as e:
                        st.error(f"❌ Error creating DataFrame for {section_name}: {e}")
                        dfs_output[section_key.lower()] = pd.DataFrame()
                else:
                    st.warning(f"No valid data rows collected for {section_name} table in the uploaded file.")
                    dfs_output[section_key.lower()] = pd.DataFrame()
            else:
                dfs_output[section_key.lower()] = pd.DataFrame() # Return empty if section not found in file
        
        # --- Pass 3: Extract Balance Summary and Results Summary (non-table sections) ---
        balance_summary_dict = {}
        results_summary_dict = {}
        
        balance_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Balance:"):
                balance_start_line_idx = i
                break

        if balance_start_line_idx != -1:
            for i in range(balance_start_line_idx, len(lines)):
                line_stripped = lines[i].strip()
                if not line_stripped:
                    break
                
                if line_stripped.startswith("Results"):
                    break

                parts = [p.strip() for p in line_stripped.split(',')]
                
                def safe_float_convert(value_str):
                    try:
                        return float(value_str.replace(" ", "").replace(",", ""))
                    except ValueError:
                        return None

                if parts[0].replace(":", "").strip() == "Balance" and len(parts) >= 2:
                    balance_summary_dict["Balance"] = safe_float_convert(parts[1])
                    if len(parts) >= 6 and parts[4].replace(":", "").strip() == "Free Margin":
                        balance_summary_dict["Free_Margin"] = safe_float_convert(parts[5])
                elif parts[0].replace(":", "").strip() == "Credit Facility" and len(parts) >= 2:
                    balance_summary_dict["Credit_Facility"] = safe_float_convert(parts[1])
                    if len(parts) >= 6 and parts[4].replace(":", "").strip() == "Margin":
                        balance_summary_dict["Margin"] = safe_float_convert(parts[5])
                elif parts[0].replace(":", "").strip() == "Floating P/L" and len(parts) >= 2:
                    balance_summary_dict["Floating_P_L"] = safe_float_convert(parts[1])
                    if len(parts) >= 6 and parts[4].replace(":", "").strip() == "Margin Level":
                        balance_summary_dict["Margin_Level"] = safe_float_convert(parts[5].replace("%", ""))
                elif parts[0].replace(":", "").strip() == "Equity" and len(parts) >= 2:
                    balance_summary_dict["Equity"] = safe_float_convert(parts[1])
        
        results_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Results") or line.strip().startswith("Total Net Profit:"):
                results_start_line_idx = i
                break
        
        if results_start_line_idx != -1:
            for i in range(results_start_line_idx + 1, len(lines)):
                line_stripped = lines[i].strip()
                if not line_stripped:
                    break
                
                parts = [p.strip() for p in line_stripped.split(',')]
                for k_idx in range(0, len(parts), 2):
                    if k_idx + 1 < len(parts):
                        key = parts[k_idx].replace(":", "").replace(" ", "_").replace(".", "").strip()
                        value_str = parts[k_idx + 1].strip()
                        
                        if key:
                            try:
                                if '%' in value_str:
                                    results_summary_dict[key] = float(value_str.replace('%', ''))
                                elif '(' in value_str and ')' in value_str:
                                    num_part = value_str.split('(')[0].strip()
                                    results_summary_dict[key] = safe_float_convert(num_part)
                                else:
                                    results_summary_dict[key] = float(value_str)
                            except ValueError:
                                if "won %" in key and '(' in value_str:
                                    try:
                                        num_val_str = value_str.split('(')[0].strip()
                                        results_summary_dict[key] = safe_float_convert(num_val_str)
                                    except Exception:
                                        results_summary_dict[key] = value_str
                                elif "%" in value_str:
                                    results_summary_dict[key] = safe_float_convert(value_str.replace("%", ""))
                                else:
                                    results_summary_dict[key] = value_str

                if "Average consecutive losses" in line_stripped:
                    break

        dfs_output['balance_summary'] = balance_summary_dict
        dfs_output['results_summary'] = results_summary_dict

        return dfs_output

    # --- ฟังก์ชันสำหรับบันทึก Positions ลงในชีท ActualPositions ---
    def save_positions_to_gsheets(df_positions, portfolio_id, portfolio_name, source_file_name="N/A"):
        gc = get_gspread_client()
        if not gc: return False
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
            ws = sh.worksheet(WORKSHEET_ACTUAL_POSITIONS)
            expected_headers = [
                "Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P",
                "Close_Time", "Close_Price", "Commission", "Swap", "Profit",
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.append_row(expected_headers)

            rows_to_append = []
            for index, row in df_positions.iterrows():
                row_data = {
                    "Time": row.get("Time", ""),
                    "Position": row.get("Position", ""),
                    "Symbol": row.get("Symbol", ""),
                    "Type": row.get("Type", ""),
                    "Volume": row.get("Volume", ""),
                    "Price": row.get("Price", ""),
                    "S_L": row.get("S_L", ""),
                    "T_P": row.get("T_P", ""),
                    "Close_Time": row.get("Close_Time", ""), # Use new clean name
                    "Close_Price": row.get("Close_Price", ""), # Use new clean name
                    "Commission": row.get("Commission", ""),
                    "Swap": row.get("Swap", ""),
                    "Profit": row.get("Profit", ""),
                    "PortfolioID": portfolio_id,
                    "PortfolioName": portfolio_name,
                    "SourceFile": source_file_name
                }
                rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])
            if rows_to_append: ws.append_rows(rows_to_append, value_input_option='USER_ENTERED'); return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_POSITIONS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Positions: {e}"); return False

    # --- ฟังก์ชันสำหรับบันทึก Orders ลงในชีท ActualOrders ---
    def save_orders_to_gsheets(df_orders, portfolio_id, portfolio_name, source_file_name="N/A"):
        gc = get_gspread_client()
        if not gc: return False
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
            ws = sh.worksheet(WORKSHEET_ACTUAL_ORDERS)
            expected_headers = [
                "Open_Time", "Order", "Symbol", "Type", "Volume", "Price", "S_L", "T_P",
                "Close_Time", "State", "Comment", # Renamed "Time" to "Close_Time" for clarity
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.append_row(expected_headers)

            rows_to_append = []
            for index, row in df_orders.iterrows():
                row_data = {
                    "Open_Time": row.get("Open_Time", ""),
                    "Order": row.get("Order", ""),
                    "Symbol": row.get("Symbol", ""),
                    "Type": row.get("Type", ""),
                    "Volume": row.get("Volume", ""),
                    "Price": row.get("Price", ""),
                    "S_L": row.get("S_L", ""),
                    "T_P": row.get("T_P", ""),
                    "Close_Time": row.get("Close_Time", ""), # Use new clean name
                    "State": row.get("State", ""),
                    "Comment": row.get("Comment", ""),
                    "PortfolioID": portfolio_id,
                    "PortfolioName": portfolio_name,
                    "SourceFile": source_file_name
                }
                rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])
            if rows_to_append: ws.append_rows(rows_to_append, value_input_option='USER_ENTERED'); return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_ORDERS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Orders: {e}"); return False

    # --- ฟังก์ชันสำหรับบันทึก Results Summary ลงในชีท StatementSummaries ---
    def save_results_summary_to_gsheets(summary_dict, portfolio_id, portfolio_name, source_file_name="N/A"):
        gc = get_gspread_client()
        if not gc: return False
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
            ws = sh.worksheet(WORKSHEET_STATEMENT_SUMMARIES)
            
            # Define expected headers for StatementSummaries worksheet (must match your GSheet exactly)
            expected_headers = [
                "Timestamp", "PortfolioID", "PortfolioName", "SourceFile", 
                "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", 
                "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", 
                "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", 
                "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative", 
                "Balance_Drawdown_Relative_Percent", "Total_Trades", 
                "Short_Trades", "Short_Trades_won_%", "Long_Trades", 
                "Long_Trades_won_%", "Profit_Trades", "Profit_Trades_Percent_of_total", 
                "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", 
                "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", 
                "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", 
                "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit",
                "Maximal_consecutive_profit_Count", "Maximal_consecutive_profit_Amount",
                "Maximal_consecutive_loss_Count", "Maximal_consecutive_loss_Amount",
                "Average_consecutive_wins", "Average_consecutive_losses"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.append_row(expected_headers)

            rows_to_append = []
            row_data = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "PortfolioID": portfolio_id,
                "PortfolioName": portfolio_name,
                "SourceFile": source_file_name
            }
            # Add all summary items from the dictionary
            for key, value in summary_dict.items():
                # Clean up key names to match expected_headers (replace spaces, etc.)
                cleaned_key = key.replace(" ", "_").replace("%", "Percent").replace("(won_%)", "won_%").replace("__", "_")
                if cleaned_key in expected_headers:
                    row_data[cleaned_key] = value
            
            rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])
            
            if rows_to_append: ws.append_rows(rows_to_append, value_input_option='USER_ENTERED'); return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_STATEMENT_SUMMARIES}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Statement Summaries: {e}"); return False


    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement Report (CSV) เพื่อประมวลผลและบันทึก")
    
    # ใช้ st.file_uploader แทนการโหลดจาก Google Sheet โดยตรงในตอนนี้
    uploaded_file_statement = st.file_uploader( 
        "ลากและวางไฟล์ Statement Report (CSV) ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["csv"], # จำกัดให้รับเฉพาะ CSV เพื่อการประมวลผลที่แม่นยำ
        key="full_stmt_uploader"
    )

    st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้)", key="debug_statement_processing")
    
    active_portfolio_id_for_actual = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_for_actual = st.session_state.get('active_portfolio_name_gs', None)

    if uploaded_file_statement:
        file_name_for_saving = uploaded_file_statement.name # Get original file name
        
        # Read the file content as string
        file_content_str = uploaded_file_statement.getvalue().decode("utf-8") # Decode bytes to string
        
        st.info(f"กำลังประมวลผลไฟล์: {uploaded_file_statement.name}")
        with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {uploaded_file_statement.name}..."):
            # ใช้ฟังก์ชัน extract_data_from_report_content ใหม่
            extracted_sections = extract_data_from_report_content(file_content_str)
            
            if st.session_state.get("debug_statement_processing", False):
                st.subheader("📄 ข้อมูลที่แยกได้ (Debug)")
                for section_name, data_item in extracted_sections.items():
                    st.write(f"#### {section_name.replace('_',' ').title()}")
                    if isinstance(data_item, pd.DataFrame):
                        st.dataframe(data_item)
                    else: # For balance_summary and results_summary (dictionaries)
                        st.json(data_item)

            if not active_portfolio_id_for_actual:
                st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.")
            else:
                # --- บันทึกข้อมูลแต่ละส่วนไปยัง Google Sheets ---
                st.markdown("---")
                st.subheader("💾 กำลังบันทึกข้อมูลไปยัง Google Sheets...")
                
                # Deals
                if not extracted_sections.get('deals', pd.DataFrame()).empty:
                    if save_deals_to_actual_trades(extracted_sections['deals'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success(f"บันทึก Deals จำนวน {len(extracted_sections['deals'])} รายการ ไปยังชีต 'ActualTrades' สำเร็จ!")
                        st.session_state.df_stmt_deals = extracted_sections['deals'].copy() # Update for Dashboard
                    else: st.error("บันทึก Deals ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Deals ใน Statement.")

                # Orders
                if not extracted_sections.get('orders', pd.DataFrame()).empty:
                    if save_orders_to_gsheets(extracted_sections['orders'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success(f"บันทึก Orders จำนวน {len(extracted_sections['orders'])} รายการ ไปยังชีต 'ActualOrders' สำเร็จ!")
                    else: st.error("บันทึก Orders ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Orders ใน Statement.")
                
                # Positions
                if not extracted_sections.get('positions', pd.DataFrame()).empty:
                    if save_positions_to_gsheets(extracted_sections['positions'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success(f"บันทึก Positions จำนวน {len(extracted_sections['positions'])} รายการ ไปยังชีต 'ActualPositions' สำเร็จ!")
                    else: st.error("บันทึก Positions ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Positions ใน Statement.")

                # Results Summary
                if extracted_sections.get('results_summary'):
                    if save_results_summary_to_gsheets(extracted_sections['results_summary'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success("บันทึก Results Summary ไปยังชีท 'StatementSummaries' สำเร็จ!")
                    else: st.error("บันทึก Results Summary ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Results Summary ใน Statement.")

    else:
        st.info("โปรดอัปโหลดไฟล์ Statement Report (CSV) เพื่อเริ่มต้นประมวลผล.")

    st.markdown("---")
    # ไม่แสดงข้อมูลจาก Uploaded Statements Worksheet แล้ว เนื่องจากตอนนี้รับไฟล์โดยตรง
    # st.subheader("📁 ข้อมูล Statement ที่โหลดจาก 'Uploaded Statements' (สำหรับตรวจสอบ)")
    # if not df_gs_uploaded_stmt.empty:
    #     st.dataframe(df_gs_uploaded_stmt, use_container_width=True)
    # else:
    #     st.info("ไม่พบข้อมูลในชีต 'Uploaded Statements'.")

    # ปุ่มล้างข้อมูลในชีท 'Uploaded Statements' อาจจะยังเก็บไว้ถ้าคุณต้องการใช้ชีทนั้นเพื่อวัตถุประสงค์อื่น
    # หรือถ้าต้องการเคลียร์มันเป็นประจำ
    # if st.button("🗑️ ล้างข้อมูลในชีท 'Uploaded Statements'", key="clear_uploaded_gs_data"):
    #     gc = get_gspread_client()
    #     if gc:
    #         try:
    #             sh = gc.open(GOOGLE_SHEET_NAME)
    #             ws = sh.worksheet(WORKSHEET_UPLOADED_STATEMENTS)
    #             ws.clear() # ล้างข้อมูลทั้งหมดในชีท
    #             st.success("ล้างข้อมูลในชีท 'Uploaded Statements' ทั้งหมดแล้ว")
    #             st.cache_data.clear()
    #             st.rerun()
    #         except Exception as e:
    #             st.error(f"❌ เกิดข้อผิดพลาดในการล้างชีต: {e}")
# ===================== SEC 8: MAIN AREA - PERFORMANCE DASHBOARD =======================
def load_data_for_dashboard(): # Function to select data source for dashboard
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Planned Trades (Google Sheets)", "Actual Trades (Statement Import)"],
        index=0, # Default to planned trades
        key="dashboard_source_selector"
    )
    
    df_dashboard_data = pd.DataFrame()
    if source_option == "Planned Trades (Google Sheets)":
        # Load from Google Sheets 'PlannedTradeLogs'
        gc_dash = get_gspread_client()
        if gc_dash:
            try:
                sh_dash = gc_dash.open(GOOGLE_SHEET_NAME)
                ws_dash_logs = sh_dash.worksheet(WORKSHEET_PLANNED_LOGS)
                records_dash = ws_dash_logs.get_all_records()
                if records_dash:
                    df_dashboard_data = pd.DataFrame(records_dash)
                    # Convert types for dashboard
                    if 'Risk $' in df_dashboard_data.columns:
                        df_dashboard_data['Profit'] = pd.to_numeric(df_dashboard_data['Risk $'], errors='coerce').fillna(0)
                    if 'Timestamp' in df_dashboard_data.columns:
                        df_dashboard_data['Time'] = pd.to_datetime(df_dashboard_data['Timestamp'], errors='coerce')
                    if 'RR' in df_dashboard_data.columns: # Ensure RR is numeric
                         df_dashboard_data['RR'] = pd.to_numeric(df_dashboard_data['RR'], errors='coerce')
                    if 'Lot' in df_dashboard_data.columns: # Ensure Lot is numeric
                         df_dashboard_data['Lot'] = pd.to_numeric(df_dashboard_data['Lot'], errors='coerce')
                    # Rename columns for consistency if needed, e.g. Asset -> Symbol
                    if 'Asset' in df_dashboard_data.columns:
                        df_dashboard_data.rename(columns={'Asset': 'Symbol'}, inplace=True)

            except Exception as e:
                st.warning(f"ไม่สามารถโหลด Planned Trades สำหรับ Dashboard: {e}")
        st.caption("ข้อมูลจากชีต 'PlannedTradeLogs'")

    else: # Actual Trades (Statement Import)
        df_dashboard_data = st.session_state.get('df_stmt_deals', pd.DataFrame()).copy()
        # For actual trades, 'Profit' and 'Time' columns are usually standard from MT4/5 statements
        # Ensure they are correctly named and typed after parsing.
        # Example: if your parser names profit column 'Profit_USD', rename it to 'Profit'
        # And convert 'Time' to datetime if it's not already.
        if not df_dashboard_data.empty:
            # Standardize column names from statement for dashboard
            # This depends heavily on your statement parser output
            rename_map = {} 
            # Example common renames (ADAPT THESE TO YOUR ACTUAL STATEMENT PARSER OUTPUT)
            for col in df_dashboard_data.columns:
                col_lower = col.lower()
                if 'profit' in col_lower and 'Profit' not in rename_map.values(): rename_map[col] = 'Profit'
                if 'time' in col_lower and 'open time' not in col_lower and 'Time' not in rename_map.values(): rename_map[col] = 'Time' # Assuming general time is close time
                if 'open time' in col_lower and 'Open Time' not in rename_map.values(): rename_map[col] = 'Open Time'
                if 'symbol' in col_lower and 'Symbol' not in rename_map.values(): rename_map[col] = 'Symbol'
                if 'volume' in col_lower or 'lots' in col_lower and 'Lot' not in rename_map.values(): rename_map[col] = 'Lot'
                # Add more mappings as needed based on your statement format

            df_dashboard_data.rename(columns=rename_map, inplace=True)

            if 'Profit' in df_dashboard_data.columns:
                df_dashboard_data['Profit'] = pd.to_numeric(df_dashboard_data['Profit'], errors='coerce').fillna(0)
            if 'Time' in df_dashboard_data.columns: # Assuming 'Time' is close time
                df_dashboard_data['Time'] = pd.to_datetime(df_dashboard_data['Time'], errors='coerce')
            elif 'Open Time' in df_dashboard_data.columns: # Use Open Time if Close Time isn't available
                 df_dashboard_data['Time'] = pd.to_datetime(df_dashboard_data['Open Time'], errors='coerce')
            if 'Lot' in df_dashboard_data.columns:
                df_dashboard_data['Lot'] = pd.to_numeric(df_dashboard_data['Lot'], errors='coerce').fillna(0)


        st.caption("ข้อมูลจากไฟล์ Statement ที่อัปโหลด (Deals)")
        
    return df_dashboard_data


with st.expander("📊 Performance Dashboard", expanded=True):
    df_data_dash = load_data_for_dashboard() # Renamed variable

    if df_data_dash.empty:
        st.info("ยังไม่มีข้อมูลสำหรับ Dashboard หรือไม่สามารถโหลดข้อมูลได้")
    else:
        # Ensure essential columns exist before proceeding with tabs
        required_cols_present = True
        if 'Profit' not in df_data_dash.columns:
            st.warning("ไม่พบคอลัมน์ 'Profit' ในข้อมูลสำหรับ Dashboard")
            required_cols_present = False
        if 'Time' not in df_data_dash.columns:
            st.warning("ไม่พบคอลัมน์ 'Time' (หรือเทียบเท่า) ในข้อมูลสำหรับ Dashboard")
            required_cols_present = False
        
        if not required_cols_present:
            st.stop() # Stop rendering dashboard if essential data is missing

        # --- Filters ---
        st.markdown("#### ⚙️ Filters")
        col_filter1, col_filter2 = st.columns(2)

        with col_filter1: # Portfolio Filter
            portfolio_col_name = None
            if "Portfolio" in df_data_dash.columns and df_data_dash["Portfolio"].notna().any():
                portfolio_col_name = "Portfolio"
            elif "PortfolioName" in df_data_dash.columns and df_data_dash["PortfolioName"].notna().any(): # From Planned Logs
                portfolio_col_name = "PortfolioName"
            
            if portfolio_col_name:
                portfolio_list_dash = ["ทั้งหมด"] + sorted(df_data_dash[portfolio_col_name].dropna().unique().tolist())
                selected_portfolio_dash = st.selectbox(
                    "📂 Filter by Portfolio", portfolio_list_dash, key="dash_portfolio_filter"
                )
                if selected_portfolio_dash != "ทั้งหมด":
                    df_data_dash = df_data_dash[df_data_dash[portfolio_col_name] == selected_portfolio_dash]
            else:
                st.selectbox("📂 Filter by Portfolio", ["- (ไม่มีข้อมูลพอร์ต)"], disabled=True, key="dash_portfolio_filter_disabled")
        
        with col_filter2: # Asset/Symbol Filter
            symbol_col_name = None
            if "Symbol" in df_data_dash.columns and df_data_dash["Symbol"].notna().any():
                symbol_col_name = "Symbol"
            
            if symbol_col_name:
                asset_list_dash = ["ทั้งหมด"] + sorted(df_data_dash[symbol_col_name].dropna().unique().tolist())
                selected_asset_dash = st.selectbox(
                    f"🎯 Filter by {symbol_col_name}", asset_list_dash, key="dash_asset_filter"
                )
                if selected_asset_dash != "ทั้งหมด":
                    df_data_dash = df_data_dash[df_data_dash[symbol_col_name] == selected_asset_dash]
            else:
                st.selectbox("🎯 Filter by Asset/Symbol", ["- (ไม่มีข้อมูล Symbol)"], disabled=True, key="dash_asset_filter_disabled")
        
        st.markdown("---")

        # --- Dashboard Tabs ---
        tab_names = ["📊 Dashboard", "📈 RR Analysis", "📉 Lot Size", "🕒 Time Analysis", "🤖 AI Insight", "⬇️ Export"]
        # Conditionally remove RR tab if RR column not present or not relevant for 'Actual Trades'
        if 'RR' not in df_data_dash.columns and st.session_state.get("dashboard_source_selector") == "Actual Trades (Statement Import)":
            # Or if 'RR' doesn't make sense for actual trades directly from statement
            if "📈 RR Analysis" in tab_names: tab_names.remove("📈 RR Analysis")
        
        tabs = st.tabs(tab_names)
        
        with tabs[0]: # Dashboard Tab
            st.markdown("### ⚖️ Win/Loss Ratio")
            win_count_dash = df_data_dash[df_data_dash['Profit'] > 0].shape[0]
            loss_count_dash = df_data_dash[df_data_dash['Profit'] <= 0].shape[0]
            if win_count_dash + loss_count_dash > 0:
                pie_df_dash = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count_dash, loss_count_dash]})
                pie_chart_dash = px.pie(pie_df_dash, names="Result", values="Count", color="Result",
                                        color_discrete_map={"Win": "mediumseagreen", "Loss": "indianred"}, title="Win vs Loss Trades")
                st.plotly_chart(pie_chart_dash, use_container_width=True)
            else:
                st.info("ไม่มีข้อมูล Win/Loss เพียงพอสำหรับ Pie Chart")

            st.markdown("### 🗓️ Daily Profit/Loss")
            df_data_dash['TradeDate'] = df_data_dash['Time'].dt.date # Group by date part only
            daily_pnl_df = df_data_dash.groupby("TradeDate")['Profit'].sum().reset_index(name="Daily P/L")
            daily_bar_chart = px.bar(daily_pnl_df, x="TradeDate", y="Daily P/L", 
                                     color="Daily P/L", title="กำไร/ขาดทุนรายวัน",
                                     color_continuous_scale=["indianred", "lightgrey", "mediumseagreen"])
            st.plotly_chart(daily_bar_chart, use_container_width=True)

            st.markdown("### 📉 Balance Curve (Equity Timeline)")
            df_data_dash_sorted = df_data_dash.sort_values(by="Time")
            df_data_dash_sorted["Balance"] = acc_balance + df_data_dash_sorted['Profit'].cumsum() # Start with acc_balance
            balance_curve_chart = px.line(df_data_dash_sorted, x="Time", y="Balance", markers=True, title="Balance Curve")
            balance_curve_chart.update_traces(line_color='deepskyblue')
            st.plotly_chart(balance_curve_chart, use_container_width=True)

        # Conditional RR Tab
        rr_tab_index = -1
        if "📈 RR Analysis" in tab_names:
            rr_tab_index = tab_names.index("📈 RR Analysis")
        
        if rr_tab_index != -1:
            with tabs[rr_tab_index]:
                if 'RR' in df_data_dash.columns and not df_data_dash['RR'].dropna().empty:
                    rr_data_dash = df_data_dash['RR'].dropna()
                    st.markdown("#### Risk:Reward Ratio (RR) Histogram")
                    rr_hist = px.histogram(rr_data_dash, nbins=20, title="RR Distribution", labels={'value': 'RR Ratio'}, opacity=0.8)
                    rr_hist.update_layout(bargap=0.1, xaxis_title='Risk:Reward Ratio', yaxis_title='จำนวนเทรด')
                    rr_hist.update_traces(marker_color='cornflowerblue')
                    st.plotly_chart(rr_hist, use_container_width=True)
                    st.caption("วิเคราะห์การกระจายตัวของ RR. RR ที่สูงกว่า 1.5 หรือ 2 ถือว่าดี.")
                else:
                    st.info("ไม่พบข้อมูล RR หรือข้อมูลไม่เพียงพอสำหรับ Histogram นี้.")
        
        # Lot Size Tab
        lot_tab_index = tab_names.index("📉 Lot Size")
        with tabs[lot_tab_index]:
            if 'Lot' in df_data_dash.columns and not df_data_dash['Lot'].dropna().empty:
                st.markdown("#### Lot Size Over Time")
                # Ensure data is sorted by time for line chart
                lot_df_sorted = df_data_dash.dropna(subset=['Lot', 'Time']).sort_values(by="Time")
                lot_line_chart = px.line(lot_df_sorted, x="Time", y="Lot", markers=True, title="Lot Size Evolution")
                lot_line_chart.update_traces(line_color='goldenrod')
                st.plotly_chart(lot_line_chart, use_container_width=True)
                st.caption("ติดตามการเปลี่ยนแปลงของ Lot Size เพื่อวิเคราะห์ Money Management และ Scaling.")
            else:
                st.info("ไม่พบข้อมูล Lot Size หรือข้อมูลไม่เพียงพอ.")

        # Time Analysis Tab
        time_analysis_tab_index = tab_names.index("🕒 Time Analysis")
        with tabs[time_analysis_tab_index]:
            st.markdown("#### Performance by Day of Week")
            df_data_dash['Weekday'] = df_data_dash['Time'].dt.day_name()
            weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            weekday_pnl = df_data_dash.groupby("Weekday")['Profit'].sum().reindex(weekday_order).reset_index()
            weekday_chart = px.bar(weekday_pnl, x="Weekday", y="Profit", title="Total P/L by Day of Week", color="Profit",
                                   color_continuous_scale=["tomato", "lightgoldenrodyellow", "lightgreen"])
            st.plotly_chart(weekday_chart, use_container_width=True)
            st.caption("ดูว่าวันไหนในสัปดาห์ที่มักทำกำไรหรือขาดทุน.")

        # AI Insight Tab
        ai_insight_tab_index = tab_names.index("🤖 AI Insight")
        with tabs[ai_insight_tab_index]:
            st.markdown("### AI Insight & Recommendation (Dashboard Data)")
            # Simplified AI prompt based on aggregated dashboard data
            total_trades_dash_ai = df_data_dash.shape[0]
            winrate_dash_ai = (win_count_dash / total_trades_dash_ai * 100) if total_trades_dash_ai > 0 else 0
            gross_profit_dash_ai = df_data_dash['Profit'].sum()
            
            st.write(f"Trades in current view: {total_trades_dash_ai}")
            st.write(f"Winrate: {winrate_dash_ai:.2f}%")
            st.write(f"Net Profit: {gross_profit_dash_ai:,.2f} USD")
            
            # You can add more stats here for the AI prompt

            # Gemini AI call (ensure API key is set in secrets)
            try:
                if "google_api" in st.secrets and "GOOGLE_API_KEY" in st.secrets.google_api:
                    genai.configure(api_key=st.secrets.google_api.GOOGLE_API_KEY)
                    model_gemini = genai.GenerativeModel('gemini-pro')
                    prompt_text_dash = (
                        f"Analyze this trading performance: Total trades: {total_trades_dash_ai}, "
                        f"Winrate: {winrate_dash_ai:.2f}%, Net Profit/Loss: {gross_profit_dash_ai:,.2f} USD. "
                        f"Provide concise trading insights and recommendations for improvement. "
                        f"What are potential strengths and weaknesses? Focus on practical advice. Respond in Thai."
                    )
                    with st.spinner("🤖 Gemini AI กำลังวิเคราะห์ข้อมูล Dashboard..."):
                        response_gemini = model_gemini.generate_content(prompt_text_dash)
                    st.markdown("---")
                    st.markdown("**มุมมองจาก Gemini AI:**")
                    st.write(response_gemini.text)
                else:
                    st.info("โปรดตั้งค่า Google API Key ใน `secrets.toml` (ใต้ `[google_api]`) เพื่อเปิดใช้งาน AI Assistant จาก Gemini.")
            except Exception as e_gemini:
                st.error(f"❌ เกิดข้อผิดพลาดในการเรียกใช้ Gemini AI: {e_gemini}")

        # Export Tab
        export_tab_index = tab_names.index("⬇️ Export")
        with tabs[export_tab_index]:
            st.markdown("### 📄 Export Filtered Data")
            if not df_data_dash.empty:
                csv_export = df_data_dash.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Data as CSV",
                    data=csv_export,
                    file_name=f"dashboard_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                )
            else:
                st.info("ไม่มีข้อมูลที่กรองไว้สำหรับ Export.")

# ===================== SEC 9: MAIN AREA - TRADE LOG VIEWER =======================
# --- ฟังก์ชันสำหรับโหลด Planned Trades จาก Google Sheets ---
@st.cache_data(ttl=120) # Cache for 2 minutes
def load_planned_trades_from_gsheets_for_viewer(): # Renamed to be specific
    gc = get_gspread_client()
    if gc is None: return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        records = worksheet.get_all_records()
        if not records: return pd.DataFrame()
        
        df_logs_viewer = pd.DataFrame(records)
        if 'Timestamp' in df_logs_viewer.columns:
            df_logs_viewer['Timestamp'] = pd.to_datetime(df_logs_viewer['Timestamp'], errors='coerce')
        
        # Ensure numeric columns are correctly typed for display, handle empty strings
        cols_to_numeric_log_viewer = ['Risk %', 'Entry', 'SL', 'TP', 'Lot', 'Risk $', 'RR']
        for col_viewer in cols_to_numeric_log_viewer:
            if col_viewer in df_logs_viewer.columns:
                df_logs_viewer[col_viewer] = pd.to_numeric(df_logs_viewer[col_viewer].astype(str).str.replace('', 'NaN', regex=False), errors='coerce')
        
        return df_logs_viewer.sort_values(by="Timestamp", ascending=False) if 'Timestamp' in df_logs_viewer.columns else df_logs_viewer
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ Log Viewer: ไม่พบ Worksheet '{WORKSHEET_PLANNED_LOGS}'.")
        return pd.DataFrame()
    except Exception as e_log_viewer:
        st.error(f"❌ Log Viewer: เกิดข้อผิดพลาดในการโหลด Log - {e_log_viewer}")
        return pd.DataFrame()

with st.expander("📚 Trade Log Viewer (แผนเทรดจาก Google Sheets)", expanded=False):
    df_log_viewer_gs = load_planned_trades_from_gsheets_for_viewer()

    if df_log_viewer_gs.empty:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้ใน Google Sheets หรือ Worksheet 'PlannedTradeLogs' ว่างเปล่า.")
    else:
        df_show_log_viewer = df_log_viewer_gs.copy()

        # --- Filters for Log Viewer ---
        log_filter_cols = st.columns(4)
        with log_filter_cols[0]:
            portfolios_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["PortfolioName"].dropna().unique().tolist()) if "PortfolioName" in df_show_log_viewer else ["ทั้งหมด"]
            portfolio_filter_log = st.selectbox("Portfolio", portfolios_in_log, key="log_viewer_portfolio_filter")
        with log_filter_cols[1]:
            modes_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["Mode"].dropna().unique().tolist()) if "Mode" in df_show_log_viewer else ["ทั้งหมด"]
            mode_filter_log = st.selectbox("Mode", modes_in_log, key="log_viewer_mode_filter")
        with log_filter_cols[2]:
            assets_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["Asset"].dropna().unique().tolist()) if "Asset" in df_show_log_viewer else ["ทั้งหมด"]
            asset_filter_log = st.selectbox("Asset", assets_in_log, key="log_viewer_asset_filter")
        with log_filter_cols[3]:
            date_filter_log = None
            if 'Timestamp' in df_show_log_viewer.columns and not df_show_log_viewer['Timestamp'].isnull().all():
                 date_filter_log = st.date_input("ค้นหาวันที่ (Log)", value=None, key="log_viewer_date_filter", help="เลือกวันที่เพื่อกรอง Log")


        # --- Apply Filters ---
        if portfolio_filter_log != "ทั้งหมด" and "PortfolioName" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["PortfolioName"] == portfolio_filter_log]
        if mode_filter_log != "ทั้งหมด" and "Mode" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Mode"] == mode_filter_log]
        if asset_filter_log != "ทั้งหมด" and "Asset" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Asset"] == asset_filter_log]
        if date_filter_log and 'Timestamp' in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Timestamp"].dt.date == date_filter_log]
        
        # Displaying the filtered log
        # st.dataframe(df_show_log_viewer, use_container_width=True, hide_index=True)
        
        # Display with Plot button (more interactive)
        st.markdown("---")
        st.markdown("**Log Details & Actions:**")
        
        # Define columns to display and their headers
        cols_to_display = {
            "Timestamp": "Timestamp", "PortfolioName": "Portfolio", "Asset": "Asset",
            "Mode": "Mode", "Direction": "Direction", "Entry": "Entry", "SL": "SL", "TP": "TP",
            "Lot": "Lot", "Risk $": "Risk $" , "RR": "RR"
        }
        # Filter out columns not present in the DataFrame
        actual_cols_to_display = {k:v for k,v in cols_to_display.items() if k in df_show_log_viewer.columns}
        
        num_display_cols = len(actual_cols_to_display)
        header_display_cols = st.columns(num_display_cols + 1) # +1 for Action button

        for i, (col_key, col_name) in enumerate(actual_cols_to_display.items()):
            header_display_cols[i].markdown(f"**{col_name}**")
        header_display_cols[num_display_cols].markdown(f"**Action**")


        for index_log, row_log in df_show_log_viewer.iterrows():
            row_display_cols = st.columns(num_display_cols + 1)
            for i, col_key in enumerate(actual_cols_to_display.keys()):
                val = row_log.get(col_key, "-")
                if isinstance(val, float): # Format floats nicely
                    row_display_cols[i].write(f"{val:.2f}" if not np.isnan(val) else "-")
                elif isinstance(val, pd.Timestamp):
                    row_display_cols[i].write(val.strftime("%Y-%m-%d %H:%M") if pd.notnull(val) else "-")
                else:
                    row_display_cols[i].write(str(val) if pd.notnull(val) and str(val).strip() != "" else "-")

            if row_display_cols[num_display_cols].button(f"📈 Plot", key=f"plot_log_{row_log.get('LogID', index_log)}"):
                st.session_state['plot_data'] = row_log.to_dict()
                st.success(f"เลือกข้อมูลเทรด '{row_log.get('Asset', '-')}' ที่ Entry '{row_log.get('Entry', '-')}' เตรียมพร้อมสำหรับ Plot บน Chart Visualizer!")
                st.rerun()
        
        if 'plot_data' in st.session_state and st.session_state['plot_data']:
            st.sidebar.success(f"ข้อมูลพร้อม Plot: {st.session_state['plot_data'].get('Asset')} @ {st.session_state['plot_data'].get('Entry')}")
            st.sidebar.json(st.session_state['plot_data'], expanded=False)
