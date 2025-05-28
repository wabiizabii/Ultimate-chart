# ======================= main.py (ฉบับสมบูรณ์ อัปเดตล่าสุด) =======================
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl # ยังคงต้อง import ไว้สำหรับ engine
import os
from datetime import datetime, timedelta # แก้ไขการ import Timedelta
import plotly.express as px
import google.generativeai as genai # สำหรับ AI Advisor

# ======================= SEC 0: CONFIG & INITIAL SETUP =======================
# 0.1. Page Config
st.set_page_config(
    page_title="Ultimate Trading Dashboard",
    page_icon="📊",
    layout="wide"
)

# 0.2. Initial Variables & File Paths
acc_balance = 10000  # หรือจะดึงมาจาก Portfolio ที่เลือก
log_file = "trade_log.csv"
PORTFOLIO_FILE = 'portfolios.csv'

# 0.3. Google API Key (ผู้ใช้ต้องใส่เอง)
# เก็บใน st.secrets ถ้า deploy หรือให้ผู้ใช้กรอกใน UI
# GOOGLE_API_KEY_FROM_USER = "" # จะถูกกำหนดค่าจาก st.text_input

# ======================= SEC 0.8: PORTFOLIO SETUP & MANAGEMENT =======================
# 0.8.1. Function to load portfolios
def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            df = pd.read_csv(PORTFOLIO_FILE)
            required_cols = {'portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'}
            if not required_cols.issubset(df.columns):
                st.warning(f"ไฟล์ {PORTFOLIO_FILE} มีโครงสร้างไม่ถูกต้อง กำลังสร้าง DataFrame ใหม่")
                return pd.DataFrame(columns=list(required_cols))
            return df
        except pd.errors.EmptyDataError:
            st.info(f"ไฟล์ {PORTFOLIO_FILE} ว่างเปล่า กำลังสร้าง DataFrame ใหม่")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลด {PORTFOLIO_FILE}: {e}")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
    else:
        return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])

# 0.8.2. Function to save portfolios
def save_portfolios(df_to_save):
    try:
        df_to_save.to_csv(PORTFOLIO_FILE, index=False)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก {PORTFOLIO_FILE}: {e}")

portfolios_df = load_portfolios()

# 0.8.3. Active Portfolio Selection in Sidebar
st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

if not portfolios_df.empty:
    portfolio_names_list = portfolios_df['portfolio_name'].tolist()
    
    # Set default active portfolio if not in session state or if selected was deleted
    current_active_portfolio_name = st.session_state.get('active_portfolio_name', None)
    if current_active_portfolio_name not in portfolio_names_list:
        st.session_state.active_portfolio_name = portfolio_names_list[0] if portfolio_names_list else None
    
    # Get current index for selectbox
    try:
        current_index = portfolio_names_list.index(st.session_state.active_portfolio_name) if st.session_state.active_portfolio_name in portfolio_names_list else 0
    except ValueError:
        current_index = 0 # Default to first if current_active_portfolio_name somehow not in list but list is not empty

    st.session_state.active_portfolio_name = st.sidebar.selectbox(
        "เลือกพอร์ต:",
        options=portfolio_names_list,
        index=current_index,
        key='sb_active_portfolio_selector'
    )
    
    if st.session_state.active_portfolio_name:
        active_portfolio_details = portfolios_df[portfolios_df['portfolio_name'] == st.session_state.active_portfolio_name]
        if not active_portfolio_details.empty:
            acc_balance = active_portfolio_details['initial_balance'].iloc[0] # Update global acc_balance
            st.sidebar.success(f"Active Portfolio: **{st.session_state.active_portfolio_name}** (Balance: ${acc_balance:,.2f})")
        else:
            st.sidebar.error("ไม่พบรายละเอียดของพอร์ตที่เลือก") # Should not happen if list is populated correctly
    else:
        st.sidebar.info("กรุณาเลือกพอร์ต") # If active_portfolio_name is None after selection (e.g. list was empty)

else:
    st.sidebar.info("ยังไม่มีพอร์ต กรุณาเพิ่มพอร์ตด้านล่าง")
    st.session_state.active_portfolio_name = None
    acc_balance = 10000 # Default if no portfolio

# 0.8.4. Portfolio Management UI (Expander in main area or separate page)
with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)"):
    st.subheader("พอร์ตทั้งหมดของคุณ")
    if portfolios_df.empty:
        st.info("ยังไม่มีการสร้างพอร์ต โปรดเพิ่มพอร์ตใหม่ด้านล่าง")
    else:
        st.dataframe(portfolios_df, use_container_width=True, hide_index=True)

    st.subheader("➕ เพิ่มพอร์ตใหม่")
    with st.form("new_portfolio_form", clear_on_submit=True):
        new_portfolio_name_input = st.text_input("ชื่อพอร์ต (เช่น My Personal, FTMO Challenge)")
        new_initial_balance_input = st.number_input("บาลานซ์เริ่มต้น ($)", min_value=0.0, value=10000.0, step=100.0, format="%.2f")
        
        submitted_add_portfolio = st.form_submit_button("💾 บันทึกพอร์ตใหม่")
        
        if submitted_add_portfolio:
            if not new_portfolio_name_input:
                st.warning("กรุณาใส่ชื่อพอร์ต")
            elif new_portfolio_name_input in portfolios_df['portfolio_name'].values:
                st.error(f"ชื่อพอร์ต '{new_portfolio_name_input}' มีอยู่แล้ว กรุณาใช้ชื่ออื่น")
            else:
                if portfolios_df.empty or 'portfolio_id' not in portfolios_df.columns or portfolios_df['portfolio_id'].isnull().all():
                    new_id = 1
                else:
                    new_id = portfolios_df['portfolio_id'].max() + 1 if pd.notna(portfolios_df['portfolio_id'].max()) else 1
                
                new_portfolio_entry = pd.DataFrame([{
                    'portfolio_id': int(new_id),
                    'portfolio_name': new_portfolio_name_input,
                    'initial_balance': new_initial_balance_input,
                    'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }])
                
                updated_portfolios_df = pd.concat([portfolios_df, new_portfolio_entry], ignore_index=True)
                save_portfolios(updated_portfolios_df)
                st.success(f"เพิ่มพอร์ต '{new_portfolio_name_input}' สำเร็จ!")
                if st.session_state.active_portfolio_name is None: # If no port was active, set this new one as active
                    st.session_state.active_portfolio_name = new_portfolio_name_input
                st.rerun()
st.markdown("---")

# ======================= SEC 0.5: Function Definitions (Utility from original code) =======================
# (Adjusted to use active_portfolio_name for filtering trade_log)
def get_today_drawdown_for_active_portfolio(log_file_path, current_acc_balance, active_portfolio):
    if not os.path.exists(log_file_path) or active_portfolio is None:
        return 0
    try:
        df = pd.read_csv(log_file_path)
        # Filter for active portfolio FIRST
        df = df[df["Portfolio"] == active_portfolio]
        if df.empty:
            return 0

        today_str = datetime.now().strftime("%Y-%m-%d")
        if "Timestamp" not in df.columns or "Risk $" not in df.columns:
            return 0
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0)
        df_today = df[df["Timestamp"].str.startswith(today_str)]
        drawdown = df_today["Risk $"].sum() 
        return drawdown
    except Exception as e:
        st.error(f"Error in get_today_drawdown_for_active_portfolio: {e}")
        return 0

def get_performance_for_active_portfolio(log_file_path, active_portfolio, mode="week"):
    if not os.path.exists(log_file_path) or active_portfolio is None:
        return 0, 0, 0
    try:
        df = pd.read_csv(log_file_path)
        # Filter for active portfolio FIRST
        df = df[df["Portfolio"] == active_portfolio]
        if df.empty:
            return 0,0,0

        if "Timestamp" not in df.columns or "Risk $" not in df.columns:
            return 0, 0, 0
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0)
            
        now = datetime.now()
        if mode == "week":
            start_date = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d") # Corrected Timedelta
        else:  # month
            start_date = now.strftime("%Y-%m-01")
        
        df_period = df[df["Timestamp"] >= start_date]
        if df_period.empty:
            return 0,0,0

        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0]
        total_trades_period = win + loss
        
        winrate = (100 * win / total_trades_period) if total_trades_period > 0 else 0
        gain = df_period["Risk $"].sum()
        return winrate, gain, total_trades_period
    except Exception as e:
        st.error(f"Error in get_performance_for_active_portfolio: {e}")
        return 0,0,0

# ======================= SEC 1: SIDEBAR / INPUT ZONE =======================
st.sidebar.header("🎛️ Trade Setup")

# 1.1. Drawdown Limit
drawdown_limit_pct_input = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=st.session_state.get("sidebar_dd_limit_pct", 2.0), # Persist value
    step=0.1, format="%.1f",
    key="sidebar_dd_limit_pct"
)

# 1.2. Trade Mode
current_trade_mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="sidebar_trade_mode")

# 1.3. Reset Form Button
if st.sidebar.button("🔄 Reset Form", key="sidebar_reset_button_main"):
    keys_to_keep = {"sidebar_dd_limit_pct", "sidebar_trade_mode", "active_portfolio_name", 
                    "fibo_asset", "fibo_risk_pct", "custom_asset", "custom_risk_pct"} # Add keys to keep
    
    all_keys = list(st.session_state.keys())
    for k in all_keys:
        if k not in keys_to_keep and not k.startswith("sb_active_portfolio_selector"): # Don't clear portfolio selector
            del st.session_state[k]
    
    # Reset specific Fibo flags if they exist
    if "fibo_flags_inputs" in st.session_state: # Changed key name
         st.session_state.fibo_flags_inputs = [True] * 5 
    st.rerun()

# 1.4. Input Zone (FIBO/CUSTOM)
entry_data_for_table = [] # Initialize for use in main area
custom_entries_for_table = []

if current_trade_mode == "FIBO":
    asset_input_fibo = st.sidebar.text_input("Asset", value=st.session_state.get("fibo_asset","XAUUSD"), key="fibo_asset")
    risk_pct_input_fibo = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("fibo_risk_pct",1.0), step=0.01, key="fibo_risk_pct")
    direction_input_fibo = st.sidebar.radio("Direction", ["Long", "Short"], horizontal=True, key="fibo_direction")
    swing_high_input_fibo = st.sidebar.text_input("High", key="fibo_swing_high")
    swing_low_input_fibo = st.sidebar.text_input("Low", key="fibo_swing_low")
    
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibo_levels = [0.114, 0.25, 0.382, 0.5, 0.618]
    if "fibo_flags_inputs" not in st.session_state:
        st.session_state.fibo_flags_inputs = [True] * len(fibo_levels)
    
    cols_fibo_checkboxes = st.sidebar.columns(len(fibo_levels))
    fibo_selected_flags = []
    for i, col_cb in enumerate(cols_fibo_checkboxes):
        is_checked = col_cb.checkbox(f"{fibo_levels[i]:.3f}", value=st.session_state.fibo_flags_inputs[i], key=f"fibo_checkbox_{i}")
        fibo_selected_flags.append(is_checked)
    st.session_state.fibo_flags_inputs = fibo_selected_flags
    
    save_fibo_button = st.sidebar.button("Save Plan (FIBO)", key="fibo_save_plan_button")

elif current_trade_mode == "CUSTOM":
    asset_input_custom = st.sidebar.text_input("Asset", value=st.session_state.get("custom_asset","XAUUSD"), key="custom_asset")
    risk_pct_input_custom = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("custom_risk_pct",1.0), step=0.01, key="custom_risk_pct")
    n_entry_input_custom = st.sidebar.number_input("จำนวนไม้", min_value=1, value=1, step=1, key="custom_n_entry")
    
    custom_inputs_data_list = []
    for i in range(int(n_entry_input_custom)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        entry_val = st.sidebar.text_input(f"Entry {i+1}", key=f"custom_entry_{i}")
        sl_val = st.sidebar.text_input(f"SL {i+1}", key=f"custom_sl_{i}")
        tp_val = st.sidebar.text_input(f"TP {i+1}", key=f"custom_tp_{i}")
        custom_inputs_data_list.append({"entry": entry_val, "sl": sl_val, "tp": tp_val})
    save_custom_button = st.sidebar.button("Save Plan (CUSTOM)", key="custom_save_plan_button")

# ======================= SEC 4: SUMMARY (in Sidebar) =======================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")
# Based on the mode, calculate and display summary
if current_trade_mode == "FIBO":
    try:
        high_val = float(swing_high_input_fibo)
        low_val = float(swing_low_input_fibo)
        selected_fibo_levels = [fibo_levels[i] for i, sel in enumerate(st.session_state.fibo_flags_inputs) if sel]
        n_selected = len(selected_fibo_levels)
        risk_per_trade_total = risk_pct_input_fibo / 100
        risk_dollar_total_val = acc_balance * risk_per_trade_total
        risk_dollar_per_entry_val = risk_dollar_total_val / n_selected if n_selected > 0 else 0
        
        current_entry_data_fibo = []
        for fibo_val in selected_fibo_levels:
            if direction_input_fibo == "Long":
                entry_price = low_val + (high_val - low_val) * fibo_val
                sl_price = low_val # Simplified SL for example
            else: # Short
                entry_price = high_val - (high_val - low_val) * fibo_val
                sl_price = high_val # Simplified SL for example
            
            stop_pips = abs(entry_price - sl_price)
            lot_size = (risk_dollar_per_entry_val / stop_pips) if stop_pips > 0 else 0
            risk_actual = stop_pips * lot_size

            current_entry_data_fibo.append({
                "Fibo Level": f"{fibo_val:.3f}", "Entry": f"{entry_price:.2f}", "SL": f"{sl_price:.2f}",
                "Lot": f"{lot_size:.2f}", "Risk $": f"{risk_actual:.2f}"
            })
        if current_entry_data_fibo:
            entry_data_for_table = current_entry_data_fibo # For main area display
            df_summary_fibo = pd.DataFrame(current_entry_data_fibo)
            st.sidebar.write(f"**Total Lots:** {pd.to_numeric(df_summary_fibo['Lot'], errors='coerce').sum():.2f}")
            st.sidebar.write(f"**Total Risk $:** {pd.to_numeric(df_summary_fibo['Risk $'], errors='coerce').sum():.2f}")
    except Exception as e:
        # st.sidebar.warning(f"FIBO Summary Error: {e}") # Optional: show error
        pass # Keep sidebar clean

elif current_trade_mode == "CUSTOM":
    try:
        risk_per_trade_total_custom = risk_pct_input_custom / 100
        risk_dollar_total_custom_val = acc_balance * risk_per_trade_total_custom
        risk_dollar_per_entry_custom_val = risk_dollar_total_custom_val / int(n_entry_input_custom) if int(n_entry_input_custom) > 0 else 0
        
        current_custom_entries = []
        total_lots_custom = 0
        total_risk_custom = 0
        for i_custom in range(int(n_entry_input_custom)):
            entry_p = float(st.session_state[f"custom_entry_{i_custom}"])
            sl_p = float(st.session_state[f"custom_sl_{i_custom}"])
            tp_p = float(st.session_state[f"custom_tp_{i_custom}"])
            stop_pips_custom = abs(entry_p - sl_p)
            lot_size_custom = (risk_dollar_per_entry_custom_val / stop_pips_custom) if stop_pips_custom > 0 else 0
            risk_actual_custom = lot_size_custom * stop_pips_custom
            rr_custom = abs(tp_p - entry_p) / stop_pips_custom if stop_pips_custom > 0 else 0

            current_custom_entries.append({
                "Entry": f"{entry_p:.2f}", "SL": f"{sl_p:.2f}", "TP": f"{tp_p:.2f}",
                "Lot": f"{lot_size_custom:.2f}", "Risk $": f"{risk_actual_custom:.2f}", "RR": f"{rr_custom:.2f}"
            })
            total_lots_custom += lot_size_custom
            total_risk_custom += risk_actual_custom
        
        if current_custom_entries:
            custom_entries_for_table = current_custom_entries # For main area display
            st.sidebar.write(f"**Total Lots:** {total_lots_custom:.2f}")
            st.sidebar.write(f"**Total Risk $:** {total_risk_custom:.2f}")
    except Exception as e:
        # st.sidebar.warning(f"CUSTOM Summary Error: {e}") # Optional: show error
        pass


# ======================= SEC 1.X: SCALING MANAGER SETTINGS (Sidebar) =======================
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    scaling_step_input = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=1.0, value=0.25, step=0.01, format="%.2f",
        key="scaling_step_input"
    )
    min_risk_pct_input = st.number_input(
        "Minimum Risk %", min_value=0.01, max_value=100.0, value=0.5, step=0.01, format="%.2f",
        key="min_risk_pct_input"
    )
    max_risk_pct_input = st.number_input(
        "Maximum Risk %", min_value=0.01, max_value=100.0, value=5.0, step=0.01, format="%.2f",
        key="max_risk_pct_input"
    )
    scaling_mode_input = st.radio(
        "Scaling Mode", ["Manual", "Auto"], horizontal=True, key="scaling_mode_input"
    )

# ======================= SEC 1.5: SCALING SUGGESTION & CONFIRM (Sidebar) =======================
if st.session_state.active_portfolio_name: # Only show if a portfolio is active
    winrate_scaling, gain_scaling, _ = get_performance_for_active_portfolio(log_file, st.session_state.active_portfolio_name, mode="week")
    
    # Determine current risk_pct based on mode
    current_risk_for_scaling = risk_pct_input_fibo if current_trade_mode == "FIBO" else risk_pct_input_custom

    suggest_risk_val = current_risk_for_scaling
    scaling_msg_display = f"Risk% ({st.session_state.active_portfolio_name}) คงที่: {current_risk_for_scaling:.2f}%"

    if winrate_scaling > 55 and gain_scaling > 0.02 * acc_balance: # Assuming acc_balance is the active portfolio's balance
        suggest_risk_val = min(current_risk_for_scaling + scaling_step_input, max_risk_pct_input)
        scaling_msg_display = f"🎉 ผลงานดี! Winrate {winrate_scaling:.1f}%, กำไร {gain_scaling:.2f}. แนะนำเพิ่ม Risk% ({st.session_state.active_portfolio_name}) เป็น {suggest_risk_val:.2f}%"
    elif winrate_scaling < 45 or gain_scaling < 0:
        suggest_risk_val = max(current_risk_for_scaling - scaling_step_input, min_risk_pct_input)
        scaling_msg_display = f"⚠️ ควรลด Risk%! Winrate {winrate_scaling:.1f}%, กำไร {gain_scaling:.2f}. แนะนำลด Risk% ({st.session_state.active_portfolio_name}) เป็น {suggest_risk_val:.2f}%"

    st.sidebar.info(scaling_msg_display)

    if scaling_mode_input == "Manual" and suggest_risk_val != current_risk_for_scaling:
        if st.sidebar.button(f"ปรับ Risk% เป็น {suggest_risk_val:.2f}", key="scaling_adjust_button"):
            if current_trade_mode == "FIBO":
                st.session_state.fibo_risk_pct = suggest_risk_val # Update session state for FIBO
            else: # CUSTOM
                st.session_state.custom_risk_pct = suggest_risk_val # Update session state for CUSTOM
            st.rerun()
    elif scaling_mode_input == "Auto" and suggest_risk_val != current_risk_for_scaling:
        if current_trade_mode == "FIBO":
            st.session_state.fibo_risk_pct = suggest_risk_val
        else: # CUSTOM
            st.session_state.custom_risk_pct = suggest_risk_val
        # No rerun needed for auto, value will be used on next interaction or rerun from elsewhere

# ======================= SEC 5: SAVE PLAN & DRAWDOWN LOCK (Logic Part) =======================
# (Moved UI part of drawdown to sidebar for better visibility)
daily_drawdown_value = 0
if st.session_state.active_portfolio_name:
    daily_drawdown_value = get_today_drawdown_for_active_portfolio(log_file, acc_balance, st.session_state.active_portfolio_name)

# Display Drawdown in Sidebar
st.sidebar.markdown("---")
st.sidebar.subheader(f"การควบคุมความเสี่ยง ({st.session_state.active_portfolio_name or 'N/A'})")
drawdown_limit_amount = -acc_balance * (drawdown_limit_pct_input / 100)
st.sidebar.metric(label="ขาดทุนรวมวันนี้ (Today's P/L)", value=f"{daily_drawdown_value:,.2f} USD", delta_color="inverse")
st.sidebar.caption(f"ลิมิตขาดทุนต่อวัน: {drawdown_limit_amount:,.2f} USD ({drawdown_limit_pct_input:.1f}%)")

trade_locked = False
if daily_drawdown_value <= drawdown_limit_amount and daily_drawdown_value !=0 : # Ensure it's a loss exceeding limit
    st.sidebar.error(
        f"🔴 หยุดเทรด! ขาดทุนรวมวันนี้ {abs(daily_drawdown_value):,.2f} เกินลิมิต {abs(drawdown_limit_amount):,.2f} ({drawdown_limit_pct_input:.1f}%) สำหรับพอร์ต {st.session_state.active_portfolio_name}"
    )
    trade_locked = True

# Save Plan Function
def save_plan_to_log(data_to_save, trade_mode_arg, asset_arg, risk_pct_arg, direction_arg, active_portfolio_arg):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_to_write = pd.DataFrame(data_to_save)
    df_to_write["Mode"] = trade_mode_arg
    df_to_write["Asset"] = asset_arg
    df_to_write["Risk %"] = risk_pct_arg
    df_to_write["Direction"] = direction_arg
    df_to_write["Portfolio"] = active_portfolio_arg # <<< Add active portfolio
    df_to_write["Timestamp"] = now_str
    
    try:
        if os.path.exists(log_file):
            df_old_log = pd.read_csv(log_file)
            df_final_log = pd.concat([df_old_log, df_to_write], ignore_index=True)
        else:
            df_final_log = df_to_write
        df_final_log.to_csv(log_file, index=False)
        st.sidebar.success(f"บันทึกแผน ({trade_mode_arg}) สำหรับพอร์ต '{active_portfolio_arg}' สำเร็จ!")
    except Exception as e:
        st.sidebar.error(f"Save Plan ไม่สำเร็จ: {e}")

# Handling Save Button Click
if current_trade_mode == "FIBO" and 'save_fibo_button' in st.session_state and st.session_state.fibo_save_plan_button:
    if not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    elif trade_locked:
        st.sidebar.error("ไม่สามารถบันทึกแผนได้ เนื่องจากเกินลิมิตขาดทุนรายวัน")
    elif entry_data_for_table: # Check if data is ready
        save_plan_to_log(entry_data_for_table, "FIBO", asset_input_fibo, risk_pct_input_fibo, direction_input_fibo, st.session_state.active_portfolio_name)
    else:
        st.sidebar.warning("กรุณากรอกข้อมูล FIBO ให้ครบถ้วนก่อนบันทึก")


elif current_trade_mode == "CUSTOM" and 'save_custom_button' in st.session_state and st.session_state.custom_save_plan_button:
    if not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    elif trade_locked:
        st.sidebar.error("ไม่สามารถบันทึกแผนได้ เนื่องจากเกินลิมิตขาดทุนรายวัน")
    elif custom_entries_for_table: # Check if data is ready
        save_plan_to_log(custom_entries_for_table, "CUSTOM", asset_input_custom, risk_pct_input_custom, "N/A", st.session_state.active_portfolio_name) # Direction N/A for custom
    else:
        st.sidebar.warning("กรุณากรอกข้อมูล CUSTOM ให้ครบถ้วนก่อนบันทึก")


# ======================= SEC 2+3: MAIN AREA – ENTRY TABLE (FIBO/CUSTOM) =======================
st.header("🎯 Entry Plan Details")
if current_trade_mode == "FIBO":
    if entry_data_for_table:
        st.dataframe(pd.DataFrame(entry_data_for_table), hide_index=True, use_container_width=True)
        # TP Zones for FIBO can be added here if needed
    else:
        st.info("กรอกข้อมูลใน Sidebar (FIBO) และคำนวณ Summary เพื่อดู Entry Plan.")
elif current_trade_mode == "CUSTOM":
    if custom_entries_for_table:
        st.dataframe(pd.DataFrame(custom_entries_for_table), hide_index=True, use_container_width=True)
    else:
        st.info("กรอกข้อมูลใน Sidebar (CUSTOM) และคำนวณ Summary เพื่อดู Entry Plan.")


# ======================= SEC 7: Ultimate Statement Import & Auto-Mapping =======================
with st.expander("📂 SEC 7: Statement Import & Auto-Mapping", expanded=False): # Default to collapsed
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # 7.1. Session State Initialization for Statement Data
    if 'all_statement_data' not in st.session_state:
        st.session_state.all_statement_data = {} # Stores all sections for all portfolios
    if 'df_stmt_current_active_portfolio' not in st.session_state: # Deals for the current active portfolio
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement (CSV/XLSX)")
    
    uploaded_files_sec7 = st.file_uploader(
        "ลากและวางไฟล์ Statement ที่นี่ (ไฟล์นี้จะถูกเชื่อมกับ Active Portfolio ปัจจุบัน)",
        type=["xlsx", "csv"],
        accept_multiple_files=True, # Allow multiple but process one by one with current active portfolio
        key="sec7_file_uploader_widget"
    )

    # 7.2. Debug Mode Checkbox for SEC 7
    if 'sec7_debug_display_mode' not in st.session_state:
        st.session_state.sec7_debug_display_mode = False
    st.session_state.sec7_debug_display_mode = st.checkbox("⚙️ เปิดโหมด Debug (SEC 7)", value=st.session_state.sec7_debug_display_mode, key="sec7_debug_display_checkbox")
    
    # 7.3. Data Extraction Function (No changes needed here from last version)
    def extract_data_from_report_sec7(file_buffer, stat_definitions_arg):
        df_raw_sec7 = None
        try:
            file_buffer.seek(0)
            if file_buffer.name.endswith('.csv'):
                df_raw_sec7 = pd.read_csv(file_buffer, header=None, low_memory=False)
            elif file_buffer.name.endswith('.xlsx'):
                df_raw_sec7 = pd.read_excel(file_buffer, header=None, engine='openpyxl')
        except Exception as e_read:
            st.error(f"SEC 7: เกิดข้อผิดพลาดในการอ่านไฟล์: {e_read}")
            return None

        if df_raw_sec7 is None or df_raw_sec7.empty:
            st.warning("SEC 7: ไม่สามารถอ่านข้อมูลจากไฟล์ได้ หรือไฟล์ว่างเปล่า")
            return None

        section_starts_sec7 = {}
        section_keywords_sec7 = ["Positions", "Orders", "Deals", "History", "Results"]
        for keyword_s7 in section_keywords_sec7:
            if keyword_s7 not in section_starts_sec7:
                for r_idx_s7, row_s7 in df_raw_sec7.iterrows():
                    if row_s7.astype(str).str.contains(keyword_s7, case=False, regex=False).any():
                        actual_key_s7 = "Deals" if keyword_s7 == "History" else keyword_s7
                        if actual_key_s7 not in section_starts_sec7:
                            section_starts_sec7[actual_key_s7] = r_idx_s7
                        break
        
        extracted_data_sec7 = {}
        sorted_sections_s7 = sorted(section_starts_sec7.items(), key=lambda x_s7: x_s7[1])

        tabular_keywords_s7 = ["Positions", "Orders", "Deals"]
        for i_s7, (section_name_s7, start_row_s7) in enumerate(sorted_sections_s7):
            if section_name_s7 not in tabular_keywords_s7:
                continue
            header_row_idx_s7 = start_row_s7 + 1
            while header_row_idx_s7 < len(df_raw_sec7) and df_raw_sec7.iloc[header_row_idx_s7].isnull().all():
                header_row_idx_s7 += 1
            if header_row_idx_s7 < len(df_raw_sec7):
                headers_s7 = [str(h_s7).strip() for h_s7 in df_raw_sec7.iloc[header_row_idx_s7] if pd.notna(h_s7) and str(h_s7).strip() != '']
                data_start_row_s7 = header_row_idx_s7 + 1
                end_row_s7 = len(df_raw_sec7)
                if i_s7 + 1 < len(sorted_sections_s7):
                    end_row_s7 = sorted_sections_s7[i_s7+1][1]
                df_section_s7 = df_raw_sec7.iloc[data_start_row_s7:end_row_s7].copy().dropna(how='all')
                if not df_section_s7.empty:
                    num_data_cols_s7 = df_section_s7.shape[1]
                    final_headers_s7 = headers_s7[:num_data_cols_s7]
                    if len(final_headers_s7) < num_data_cols_s7:
                        final_headers_s7.extend([f'Unnamed_S7:{j_s7}' for j_s7 in range(len(final_headers_s7), num_data_cols_s7)])
                    df_section_s7.columns = final_headers_s7
                    extracted_data_sec7[section_name_s7.lower()] = df_section_s7

        if "Results" in section_starts_sec7:
            results_stats_s7 = {}
            start_row_res_s7 = section_starts_sec7["Results"]
            results_df_s7 = df_raw_sec7.iloc[start_row_res_s7 : start_row_res_s7 + 15]
            for _, row_res_s7 in results_df_s7.iterrows():
                for c_idx_res_s7, cell_res_s7 in enumerate(row_res_s7):
                    if pd.notna(cell_res_s7):
                        label_res_s7 = str(cell_res_s7).strip().replace(':', '')
                        if label_res_s7 in stat_definitions_arg:
                            for k_s7 in range(1, 4):
                                if (c_idx_res_s7 + k_s7) < len(row_res_s7):
                                    value_s7 = row_res_s7.iloc[c_idx_res_s7 + k_s7]
                                    if pd.notna(value_s7) and str(value_s7).strip() != "":
                                        clean_value_s7 = str(value_s7).split('(')[0].strip()
                                        results_stats_s7[label_res_s7] = clean_value_s7
                                        break
                            break 
            if results_stats_s7:
                extracted_data_sec7["balance_summary"] = pd.DataFrame(list(results_stats_s7.items()), columns=['Metric', 'Value'])
        return extracted_data_sec7

    # 7.4. Define stat_definitions
    stat_definitions_sec7 = {
        "Total Net Profit", "Gross Profit", "Gross Loss", "Profit Factor", "Expected Payoff", "Recovery Factor",
        "Sharpe Ratio", "Balance Drawdown Absolute", "Balance Drawdown Maximal", "Balance Drawdown Relative",
        "Total Trades", "Short Trades (won %)", "Long Trades (won %)", "Profit Trades (% of total)", 
        "Loss Trades (% of total)", "Largest profit trade", "Largest loss trade", "Average profit trade", 
        "Average loss trade", "Maximum consecutive wins ($)", "Maximal consecutive profit (count)",
        "Average consecutive wins", "Maximum consecutive losses ($)", "Maximal consecutive loss (count)", 
        "Average consecutive losses"
    }

    # 7.5. Process Uploaded Files
    if uploaded_files_sec7:
        if not st.session_state.active_portfolio_name:
            st.warning("กรุณาเลือก 'Active Portfolio' ใน Sidebar ก่อนอัปโหลด Statement")
        else:
            active_portfolio_for_stmt = st.session_state.active_portfolio_name
            st.info(f"ไฟล์ที่อัปโหลดจะถูกเชื่อมโยงกับพอร์ต: **{active_portfolio_for_stmt}**")

            for uploaded_file_item_s7 in uploaded_files_sec7:
                st.info(f"กำลังประมวลผลไฟล์: {uploaded_file_item_s7.name} สำหรับพอร์ต {active_portfolio_for_stmt}")
                with st.spinner(f"กำลังแยกส่วนข้อมูล..."):
                    extracted_data_s7_results = extract_data_from_report_sec7(uploaded_file_item_s7, stat_definitions_sec7)
                    
                    if extracted_data_s7_results:
                        st.success(f"ประมวลผลสำเร็จ! พบข้อมูล: {', '.join(extracted_data_s7_results.keys())}")

                        # Store all extracted sections specific to this portfolio and file
                        # Example: st.session_state.all_statement_data['PortfolioA_filename.csv'] = extracted_data_s7_results
                        # For simplicity now, just update the current active portfolio's deals
                        if 'deals' in extracted_data_s7_results:
                            df_deals_new = extracted_data_s7_results['deals'].copy()
                            df_deals_new['Portfolio'] = active_portfolio_for_stmt # Add portfolio identifier
                            st.session_state.df_stmt_current_active_portfolio = df_deals_new
                            
                            # Option: Append to a master list or save to a per-portfolio file/db
                            # For now, st.session_state.all_statement_data can store dataframes keyed by portfolio
                            if active_portfolio_for_stmt not in st.session_state.all_statement_data:
                                st.session_state.all_statement_data[active_portfolio_for_stmt] = {}
                            # Store all parts under the portfolio, keyed by file or section
                            st.session_state.all_statement_data[active_portfolio_for_stmt][uploaded_file_item_s7.name] = extracted_data_s7_results
                            st.info(f"ข้อมูล Deals สำหรับพอร์ต '{active_portfolio_for_stmt}' ได้รับการอัปเดต")

                        if 'balance_summary' in extracted_data_s7_results:
                            st.write(f"### 📊 Balance Summary ({active_portfolio_for_stmt} - {uploaded_file_item_s7.name})")
                            st.dataframe(extracted_data_s7_results['balance_summary'])
                        
                        if st.session_state.sec7_debug_display_mode:
                            for section_key_s7, section_df_item_s7 in extracted_data_s7_results.items():
                                if section_key_s7 != 'balance_summary':
                                    st.write(f"### 📄 ข้อมูลส่วน ({active_portfolio_for_stmt} - {section_key_s7.title()}):")
                                    st.dataframe(section_df_item_s7)
                    else:
                        st.warning(f"ไม่สามารถแยกส่วนข้อมูลใดๆ จากไฟล์ {uploaded_file_item_s7.name}")
    else:
        st.info("ยังไม่มีไฟล์ Statement อัปโหลด (SEC 7)")

    # 7.6. Display Current Statement & Clear Button
    st.markdown("---")
    st.subheader(f"📁 Deals ล่าสุดของพอร์ต: {st.session_state.active_portfolio_name or 'N/A'} (SEC 7)")
    if not st.session_state.df_stmt_current_active_portfolio.empty and st.session_state.active_portfolio_name:
        # Ensure displayed data matches the active portfolio
        # This check might be redundant if df_stmt_current_active_portfolio is always updated correctly
        if 'Portfolio' in st.session_state.df_stmt_current_active_portfolio.columns and \
           not st.session_state.df_stmt_current_active_portfolio[st.session_state.df_stmt_current_active_portfolio['Portfolio'] == st.session_state.active_portfolio_name].empty:
            st.dataframe(st.session_state.df_stmt_current_active_portfolio[st.session_state.df_stmt_current_active_portfolio['Portfolio'] == st.session_state.active_portfolio_name])
        elif 'Portfolio' not in st.session_state.df_stmt_current_active_portfolio.columns and not st.session_state.df_stmt_current_active_portfolio.empty:
             st.dataframe(st.session_state.df_stmt_current_active_portfolio) # If no portfolio column, show as is (might be from older structure)
        else:
            st.info(f"ไม่มีข้อมูล Deals สำหรับพอร์ต {st.session_state.active_portfolio_name}")
    else:
        st.info(f"ไม่มีข้อมูล Deals สำหรับพอร์ต {st.session_state.active_portfolio_name}")


    if st.button("🗑️ ล้างข้อมูล Statement ปัจจุบัน (SEC 7)", key="sec7_clear_current_stmt_button"):
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
        # Optionally clear specific portfolio data from all_statement_data if needed
        st.success("ล้างข้อมูล Statement ปัจจุบันแล้ว (SEC 7)")
        st.rerun()

# ======================= SEC 9: DASHBOARD =======================
# 9.1. Data Loading Function for Dashboard
def load_data_for_dashboard_sec9(active_portfolio_arg):
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Log File (แผนเทรด)", "Statement Import (ผลเทรดจริง)"],
        index=0,
        key="dashboard_source_selector_sec9"
    )
    df_dashboard = pd.DataFrame()

    if source_option == "Log File (แผนเทรด)":
        if not active_portfolio_arg:
            st.warning("SEC 9: กรุณาเลือก Active Portfolio ใน Sidebar ก่อน")
            return df_dashboard
        if os.path.exists(log_file):
            try:
                df_log_all = pd.read_csv(log_file)
                # Filter by active portfolio
                df_dashboard = df_log_all[df_log_all["Portfolio"] == active_portfolio_arg].copy()
                if df_dashboard.empty:
                    st.info(f"SEC 9: ไม่พบข้อมูล Log File สำหรับพอร์ต '{active_portfolio_arg}'")
            except Exception as e_log:
                st.error(f"SEC 9: ไม่สามารถโหลด Log File: {e_log}")
        else:
            st.info(f"SEC 9: ไม่พบ Log File ({log_file})")
    
    else: # Statement Import (ผลเทรดจริง)
        if not active_portfolio_arg:
            st.warning("SEC 9: กรุณาเลือก Active Portfolio ใน Sidebar ก่อน")
            return df_dashboard
        # Use df_stmt_current_active_portfolio which should already be filtered for the active portfolio
        df_dashboard = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame()).copy()
        if df_dashboard.empty:
             st.info(f"SEC 9: ไม่มีข้อมูล Statement สำหรับพอร์ต '{active_portfolio_arg}' (โปรดอัปโหลดใน SEC 7)")
        elif 'Portfolio' in df_dashboard.columns and not df_dashboard[df_dashboard['Portfolio'] == active_portfolio_arg].empty:
             df_dashboard = df_dashboard[df_dashboard['Portfolio'] == active_portfolio_arg]
        elif 'Portfolio' not in df_dashboard.columns:
            st.warning("SEC 9: ข้อมูล Statement ที่โหลดไม่มีคอลัมน์ Portfolio, อาจแสดงข้อมูลไม่ถูกต้อง")


    # Ensure necessary columns exist and clean them
    cols_to_check_numeric = ['Risk $', 'Profit', 'RR', 'Lot', 'Commission', 'Swap']
    for col_to_check in cols_to_check_numeric:
        if col_to_check in df_dashboard.columns:
            df_dashboard[col_to_check] = pd.to_numeric(df_dashboard[col_to_check], errors='coerce').fillna(0)
        else:
            # If a critical numeric column is missing for calculation, add it as zero
            if col_to_check in ['Risk $', 'Profit']: 
                 df_dashboard[col_to_check] = 0 

    date_cols_to_check = ['Timestamp', 'Date', 'Open Time', 'Close Time']
    for col_date_check in date_cols_to_check:
        if col_date_check in df_dashboard.columns:
             df_dashboard[col_date_check] = pd.to_datetime(df_dashboard[col_date_check], errors='coerce')
             
    return df_dashboard


with st.expander("📊 Performance Dashboard (SEC 9)", expanded=True):
    if not st.session_state.active_portfolio_name:
        st.warning("กรุณาเลือก 'Active Portfolio' ใน Sidebar เพื่อดู Dashboard")
    else:
        st.subheader(f"Dashboard สำหรับพอร์ต: {st.session_state.active_portfolio_name}")
        df_data_dash = load_data_for_dashboard_sec9(st.session_state.active_portfolio_name)

        # 9.2. Dashboard Tabs
        tab_names = ["📊 Dashboard", "📈 RR", "📉 Lot Size", "🕒 Time", "🤖 AI Advisor", "⬇️ Export"]
        tabs_dash = st.tabs(tab_names)

        if df_data_dash.empty:
            st.info(f"SEC 9: ยังไม่มีข้อมูลสำหรับ Dashboard ของพอร์ต '{st.session_state.active_portfolio_name}'")
        else:
            # Identify the primary profit column to use (Profit from statement, Risk $ from log)
            profit_col_dash = None
            if 'Profit' in df_data_dash.columns and df_data_dash['Profit'].abs().sum() > 0: # Prefer 'Profit' if it has non-zero values
                profit_col_dash = 'Profit'
            elif 'Risk $' in df_data_dash.columns:
                profit_col_dash = 'Risk $'
            
            # Identify the primary asset column
            asset_col_dash = None
            if 'Asset' in df_data_dash.columns: asset_col_dash = 'Asset'
            elif 'Symbol' in df_data_dash.columns: asset_col_dash = 'Symbol'

            # Identify primary date column
            date_col_dash_options = [col for col in ["Timestamp", "Date", "Open Time", "Close Time"] if col in df_data_dash.columns and df_data_dash[col].notna().any()]
            main_date_col_dash = date_col_dash_options[0] if date_col_dash_options else None


            with tabs_dash[0]: # 📊 Dashboard
                if not profit_col_dash:
                    st.warning("SEC 9: ไม่พบคอลัมน์ 'Profit' หรือ 'Risk $' ที่มีข้อมูลสำหรับสร้างกราฟ")
                else:
                    # 9.2.1. Asset Filter for this tab
                    df_tab_data = df_data_dash.copy() # Use a copy for filtering within tab
                    if asset_col_dash:
                        unique_assets_dash = ["ทั้งหมด"] + sorted(df_tab_data[asset_col_dash].dropna().unique())
                        selected_asset_dash = st.selectbox(
                            f"Filter by {asset_col_dash}", unique_assets_dash, key="dash_asset_filter_tab"
                        )
                        if selected_asset_dash != "ทั้งหมด":
                            df_tab_data = df_tab_data[df_tab_data[asset_col_dash] == selected_asset_dash]
                    
                    if df_tab_data.empty:
                        st.info("ไม่มีข้อมูลหลังจากใช้ Filter")
                    else:
                        st.markdown("### 🥧 Pie Chart: Win/Loss")
                        win_count_dash = df_tab_data[df_tab_data[profit_col_dash] > 0].shape[0]
                        loss_count_dash = df_tab_data[df_tab_data[profit_col_dash] <= 0].shape[0]
                        if win_count_dash > 0 or loss_count_dash > 0:
                            pie_df_dash = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count_dash, loss_count_dash]})
                            pie_chart_dash = px.pie(pie_df_dash, names="Result", values="Count", color="Result",
                                            color_discrete_map={"Win": "green", "Loss": "red"})
                            st.plotly_chart(pie_chart_dash, use_container_width=True)
                        else:
                            st.info("ไม่มีข้อมูล Win/Loss สำหรับ Pie Chart.")

                        if main_date_col_dash:
                            st.markdown("### 📊 Bar Chart: กำไร/ขาดทุนแต่ละวัน")
                            df_bar_dash = df_tab_data.copy()
                            df_bar_dash["TradeDate"] = df_bar_dash[main_date_col_dash].dt.date
                            bar_df_grouped_dash = df_bar_dash.groupby("TradeDate")[profit_col_dash].sum().reset_index(name="Profit/Loss")
                            if not bar_df_grouped_dash.empty:
                                bar_chart_dash = px.bar(bar_df_grouped_dash, x="TradeDate", y="Profit/Loss", 
                                                   color="Profit/Loss", color_continuous_scale=["red", "orange", "green"])
                                st.plotly_chart(bar_chart_dash, use_container_width=True)
                            else:
                                st.info("ไม่มีข้อมูลสำหรับ Bar Chart หลัง Group by.")
                        
                            st.markdown("### 📈 Timeline: Balance Curve")
                            df_balance_dash = df_tab_data.copy().sort_values(by=main_date_col_dash)
                            initial_bal_dash = portfolios_df[portfolios_df['portfolio_name'] == st.session_state.active_portfolio_name]['initial_balance'].iloc[0] if st.session_state.active_portfolio_name else acc_balance
                            df_balance_dash["Balance"] = initial_bal_dash + df_balance_dash[profit_col_dash].cumsum()
                            if not df_balance_dash.empty:
                                timeline_chart_dash = px.line(df_balance_dash, x=main_date_col_dash, y="Balance", markers=True, title="Balance Curve")
                                st.plotly_chart(timeline_chart_dash, use_container_width=True)
                            else:
                                st.info("ไม่มีข้อมูลสำหรับ Balance Curve.")
                        else:
                            st.warning("ไม่พบคอลัมน์วันที่หลักสำหรับ Bar Chart และ Balance Curve")
            
            with tabs_dash[1]: # 📈 RR
                if "RR" in df_data_dash.columns:
                    rr_data_numeric_dash = df_data_dash["RR"].dropna() # Already numeric from load_data
                    if not rr_data_numeric_dash.empty:
                        st.markdown("#### RR Histogram")
                        fig_rr_dash = px.histogram(rr_data_numeric_dash, nbins=20, title="RR Distribution")
                        st.plotly_chart(fig_rr_dash, use_container_width=True)
                    else:
                        st.info("ไม่มีข้อมูล RR ที่ถูกต้องสำหรับ Histogram")
                else:
                    st.warning("ไม่พบคอลัมน์ 'RR' ในข้อมูล")

            with tabs_dash[2]: # 📉 Lot Size
                if "Lot" in df_data_dash.columns and main_date_col_dash:
                    df_lot_dash = df_data_dash.copy().sort_values(by=main_date_col_dash)
                    if not df_lot_dash["Lot"].dropna().empty:
                        st.markdown("#### Lot Size Evolution")
                        fig_lot_dash = px.line(df_lot_dash.dropna(subset=[main_date_col_dash, "Lot"]), 
                                          x=main_date_col_dash, y="Lot", markers=True, title="Lot Size Over Time")
                        st.plotly_chart(fig_lot_dash, use_container_width=True)
                    else:
                        st.info("ไม่มีข้อมูล Lot หรือ วันที่ ที่ถูกต้องสำหรับกราฟ Lot Size")
                else:
                    st.warning("ไม่พบคอลัมน์ 'Lot' หรือคอลัมน์วันที่หลักในข้อมูล")
            
            with tabs_dash[3]: # 🕒 Time
                if main_date_col_dash and profit_col_dash:
                    df_time_dash = df_data_dash.copy()
                    df_time_dash["Weekday"] = df_time_dash[main_date_col_dash].dt.day_name()
                    weekday_order_dash = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    weekday_profit_dash = df_time_dash.groupby("Weekday")[profit_col_dash].sum().reindex(weekday_order_dash).reset_index()
                    if not weekday_profit_dash.empty:
                        st.markdown("#### Profit/Loss by Weekday")
                        fig_weekday_dash = px.bar(weekday_profit_dash, x="Weekday", y=profit_col_dash, title="Total Profit/Loss by Weekday")
                        st.plotly_chart(fig_weekday_dash, use_container_width=True)
                    else:
                        st.info("ไม่มีข้อมูลสำหรับวิเคราะห์ตามวัน")
                else:
                    st.warning("ไม่พบคอลัมน์วันที่หลัก หรือ Profit/Risk $ สำหรับวิเคราะห์ตามวัน")

            with tabs_dash[4]: # 🤖 AI Advisor
                st.subheader("🤖 AI Advisor (Gemini)")
                st.markdown("ส่วนนี้จะสรุปผลการเทรดและให้คำแนะนำเบื้องต้นโดย AI")

                # User input for API Key
                if 'google_api_key_user' not in st.session_state:
                    st.session_state.google_api_key_user = ""
                
                st.session_state.google_api_key_user = st.text_input("ใส่ Google API Key สำหรับ Gemini:", type="password", value=st.session_state.google_api_key_user, key="gemini_api_key_input")

                if st.button("วิเคราะห์โดย AI", key="ai_analyze_button"):
                    if not st.session_state.google_api_key_user:
                        st.warning("กรุณาใส่ Google API Key ก่อน")
                    elif not profit_col_dash or df_data_dash.empty:
                        st.warning("ไม่มีข้อมูลเพียงพอสำหรับให้ AI วิเคราะห์")
                    else:
                        try:
                            genai.configure(api_key=st.session_state.google_api_key_user)
                            model = genai.GenerativeModel('gemini-pro')

                            total_trades_ai = df_data_dash.shape[0]
                            win_trades_ai = df_data_dash[df_data_dash[profit_col_dash] > 0].shape[0]
                            winrate_ai = (100 * win_trades_ai / total_trades_ai) if total_trades_ai > 0 else 0
                            gross_pl_ai = df_data_dash[profit_col_dash].sum()
                            avg_rr_ai = pd.to_numeric(df_data_dash.get('RR', pd.Series(dtype='float')), errors='coerce').mean()
                            
                            prompt = f"""
                            ฉันเป็นเทรดเดอร์ และนี่คือสรุปผลการเทรดของฉันจากพอร์ต '{st.session_state.active_portfolio_name}':
                            - จำนวนเทรดทั้งหมด: {total_trades_ai}
                            - Winrate: {winrate_ai:.2f}%
                            - กำไร/ขาดทุนสุทธิ: {gross_pl_ai:,.2f} USD
                            - R:R เฉลี่ย (ถ้ามี): {avg_rr_ai:.2f}
                            
                            โปรดวิเคราะห์ผลการเทรดนี้อย่างกระชับ บอกจุดแข็ง จุดอ่อน และให้คำแนะนำเชิงปฏิบัติ 2-3 ข้อเพื่อปรับปรุงการเทรด (ตอบเป็นภาษาไทย)
                            """
                            with st.spinner("AI กำลังวิเคราะห์..."):
                                response = model.generate_content(prompt)
                                st.markdown("--- \n**AI Says:**")
                                st.markdown(response.text)
                        except Exception as e_ai:
                            st.error(f"เกิดข้อผิดพลาดในการเรียกใช้ Gemini AI: {e_ai}")
                            st.info("โปรดตรวจสอบ API Key, การเชื่อมต่ออินเทอร์เน็ต, และโควต้าการใช้งาน Gemini API ของคุณ")

            with tabs_dash[5]: # ⬇️ Export
                st.markdown("### Export/Download Report")
                if not df_data_dash.empty:
                    csv_export_dash = df_data_dash.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        "Download Dashboard Data (CSV)", 
                        csv_export_dash, 
                        f"dashboard_report_{st.session_state.active_portfolio_name.replace(' ','_') if st.session_state.active_portfolio_name else 'all'}.csv",
                        "text/csv",
                        key="dash_export_csv_button"
                    )
                else:
                    st.info("ไม่มีข้อมูลสำหรับ Export")
# ======================= SEC END =======================

# (โค้ดส่วนอื่นๆ ของคุณเช่น Chart Visualizer, AI Assistant เดิม สามารถวางต่อจากตรงนี้ได้)
# อย่าลืม import ไลบรารีที่จำเป็นที่ส่วนบนสุดของไฟล์
