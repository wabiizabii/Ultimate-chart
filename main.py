# ===================================================================================
#                                 LEGENDARY RR PLANNER
#                            RESTRUCTURED CODE (COMPLETE)
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
st.set_page_config(page_title="Legendary RR Planner", layout="wide")

# --- Constants ---
ACC_BALANCE = 10000
LOG_FILE = "trade_log.csv"
GOOGLE_SHEET_NAME = "TradeLog"
GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# ======================= SEC 1: HELPER FUNCTIONS =======================
# (ส่วนฟังก์ชันทั้งหมดของคุณอยู่ที่นี่ - ไม่มีการเปลี่ยนแปลง)
# ... (วาง def functions ทั้งหมดของคุณที่นี่) ...

# ======================= SEC 2: SESSION STATE & INITIAL LOAD =======================
if 'df_stmt_current' not in st.session_state:
    st.session_state.df_stmt_current = pd.DataFrame() # เริ่มต้นด้วย DataFrame ว่าง
    # ลองโหลดข้อมูลจาก gsheets เมื่อเริ่มต้นแอป
    # st.session_state.df_stmt_current = load_statement_from_gsheets() 

# ======================= SEC 3: SIDEBAR =======================
st.sidebar.header("🎛️ Trade Setup")
mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")
entry_data = []
custom_entries = []

# --- Trade Inputs (FIBO) ---
if mode == "FIBO":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1: asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2: risk_pct = st.number_input("Risk %", 0.01, 100.0, 1.0, 0.01, "%.2f", key="risk_pct")
    with col3: direction = st.radio("Direction", ["Long", "Short"], horizontal=True)
    col4, col5 = st.sidebar.columns(2)
    with col4: swing_high = st.text_input("High", key="swing_high")
    with col5: swing_low = st.text_input("Low", key="swing_low")
    
    # ... (โค้ดส่วน Fibo levels checkbox ของคุณ) ...
    fibos = [0.114, 0.25, 0.382, 0.5, 0.618]
    if "fibo_flags" not in st.session_state: st.session_state.fibo_flags = [True] * len(fibos)
    fibo_selected_flags = [st.sidebar.checkbox(f"{f:.3f}", st.session_state.fibo_flags[i], key=f"fibo_{i}") for i, f in enumerate(fibos)]
    st.session_state.fibo_flags = fibo_selected_flags

    save_button = st.sidebar.button("Save Plan", key="save_fibo")

# --- Trade Inputs (CUSTOM) ---
elif mode == "CUSTOM":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1: asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2: risk_pct = st.number_input("Risk %", 0.01, 100.0, 1.0, 0.01, "%.2f")
    with col3: n_entry = st.number_input("จำนวนไม้", 1, 10, 2, 1)
    
    custom_inputs = []
    for i in range(int(n_entry)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e, col_s, col_t = st.sidebar.columns(3)
        entry = col_e.text_input(f"Entry {i+1}", "0.00", key=f"custom_entry_{i}")
        sl = col_s.text_input(f"SL {i+1}", "0.00", key=f"custom_sl_{i}")
        tp = col_t.text_input(f"TP {i+1}", "0.00", key=f"custom_tp_{i}")
        custom_inputs.append({"entry": entry, "sl": sl, "tp": tp})
    
    save_button = st.sidebar.button("Save Plan", key="save_custom")

# ... (โค้ดส่วน Drawdown & Scaling Manager ใน Sidebar ของคุณ) ...

# ======================= SEC 4: MAIN PAGE =======================
st.title("✨ Legendary RR Planner")

# --- 4.1 Trade Plan Details (ส่วนที่หายไป เอาคืนมาไว้ตรงนี้) ---
st.subheader("📋 แผนการเข้าเทรด (Trade Plan)")
with st.container(border=True):
    if mode == "FIBO":
        try:
            high = float(swing_high)
            low = float(swing_low)
            selected_fibo_levels = [fibos[i] for i, sel in enumerate(st.session_state.fibo_flags) if sel]
            n = len(selected_fibo_levels)
            risk_per_trade = risk_pct / 100
            risk_dollar_total = ACC_BALANCE * risk_per_trade
            risk_dollar_per_entry = risk_dollar_total / n if n > 0 else 0
            
            for fibo in selected_fibo_levels:
                if direction == "Long":
                    entry = low + (high - low) * fibo
                    sl = low
                else:
                    entry = high - (high - low) * fibo
                    sl = high
                stop = abs(entry - sl)
                lot = risk_dollar_per_entry / stop if stop > 0 else 0
                entry_data.append({
                    "Fibo Level": f"{fibo:.3f}", "Entry": f"{entry:.2f}", "SL": f"{sl:.2f}",
                    "Lot": f"{lot:.2f}", "Risk $": f"{risk_dollar_per_entry:.2f}"
                })
            
            if entry_data:
                entry_df = pd.DataFrame(entry_data)
                st.dataframe(entry_df, hide_index=True, use_container_width=True)
            else:
                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level เพื่อดูแผนการเข้าเทรด")

        except Exception:
            st.info("กรุณากรอกข้อมูลใน Sidebar เพื่อคำนวณแผนเทรด (FIBO)")

    elif mode == "CUSTOM":
        try:
            risk_per_trade = risk_pct / 100
            risk_dollar_total = ACC_BALANCE * risk_per_trade
            risk_dollar_per_entry = risk_dollar_total / n_entry if n_entry > 0 else 0
            
            for item in custom_inputs:
                entry_val, sl_val, tp_val = float(item["entry"]), float(item["sl"]), float(item["tp"])
                stop = abs(entry_val - sl_val)
                target =
