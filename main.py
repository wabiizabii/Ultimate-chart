# ======================= main.py (เริ่ม SEC 0) =======================
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl # สำหรับ engine='openpyxl'
import os
from datetime import datetime, timedelta
import plotly.express as px
import google.generativeai as genai # สำหรับ AI Advisor (ถ้าใช้)

# ======================= SEC 0: INITIAL SETUP & ALL FUNCTION DEFINITIONS =======================

# 0.1. Page Config
st.set_page_config(
    page_title="Ultimate Trading Dashboard",
    page_icon="📊",
    layout="wide"
)

# 0.2. Initial Variables & File Paths
# acc_balance will be dynamically set by the selected portfolio later
# default_initial_balance = 10000 
log_file = "trade_log.csv"
PORTFOLIO_FILE = 'portfolios.csv'

# 0.3. Google API Key Placeholder (User will input via UI later)
# GOOGLE_API_KEY_FROM_USER = "" 

# 0.4. ALL FUNCTION DEFINITIONS

# 0.4.1. Portfolio Functions
def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            df = pd.read_csv(PORTFOLIO_FILE)
            required_cols = {'portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'}
            if not required_cols.issubset(df.columns):
                st.warning(f"ไฟล์ {PORTFOLIO_FILE} มีโครงสร้างไม่ถูกต้อง กำลังสร้าง DataFrame ใหม่")
                return pd.DataFrame(columns=list(required_cols))
            df['initial_balance'] = pd.to_numeric(df['initial_balance'], errors='coerce').fillna(0)
            return df
        except pd.errors.EmptyDataError:
            # st.info(f"ไฟล์ {PORTFOLIO_FILE} ว่างเปล่า กำลังสร้าง DataFrame ใหม่")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลด {PORTFOLIO_FILE}: {e}")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
    else:
        # st.info(f"ไม่พบไฟล์ {PORTFOLIO_FILE} กำลังสร้าง DataFrame ใหม่")
        return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])

def save_portfolios(df_to_save):
    try:
        df_to_save.to_csv(PORTFOLIO_FILE, index=False)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก {PORTFOLIO_FILE}: {e}")

# 0.4.2. Utility Functions (Drawdown & Performance for Active Portfolio)
def get_today_drawdown_for_active_portfolio(log_file_path, active_portfolio):
    if not os.path.exists(log_file_path) or active_portfolio is None:
        return 0
    try:
        df = pd.read_csv(log_file_path)
        if "Portfolio" not in df.columns:
            # st.warning("Log file is missing 'Portfolio' column for drawdown calculation.")
            return 0 
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
    except FileNotFoundError:
        # st.info(f"Log file not found at {log_file_path} for drawdown calculation.")
        return 0
    except Exception as e:
        # st.error(f"Error in get_today_drawdown_for_active_portfolio: {e}")
        return 0

def get_performance_for_active_portfolio(log_file_path, active_portfolio, mode="week"):
    if not os.path.exists(log_file_path) or active_portfolio is None:
        return 0, 0, 0
    try:
        df = pd.read_csv(log_file_path)
        if "Portfolio" not in df.columns:
            # st.warning("Log file is missing 'Portfolio' column for performance calculation.")
            return 0,0,0
        df = df[df["Portfolio"] == active_portfolio]
        if df.empty:
            return 0,0,0

        if "Timestamp" not in df.columns or "Risk $" not in df.columns:
            return 0, 0, 0
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0)
            
        now = datetime.now()
        if mode == "week":
            start_date = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        else: # month
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
    except FileNotFoundError:
        # st.info(f"Log file not found at {log_file_path} for performance calculation.")
        return 0,0,0
    except Exception as e:
        # st.error(f"Error in get_performance_for_active_portfolio: {e}")
        return 0,0,0

# 0.4.3. Save Plan Function
def save_plan_to_log(data_to_save, trade_mode_arg, asset_arg, risk_pct_arg, direction_arg, active_portfolio_arg):
    if not active_portfolio_arg:
        st.sidebar.error("ไม่สามารถบันทึกแผน: กรุณาเลือกหรือสร้างพอร์ตก่อน")
        return
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Ensure data_to_save is a list of dictionaries as expected by pd.DataFrame
    if not isinstance(data_to_save, list) or not all(isinstance(item, dict) for item in data_to_save):
        st.sidebar.error("ข้อมูลสำหรับบันทึก Log ไม่ถูกต้อง (ต้องเป็น list of dictionaries)")
        return

    df_to_write = pd.DataFrame(data_to_save)
    df_to_write["Mode"] = trade_mode_arg
    df_to_write["Asset"] = asset_arg
    df_to_write["Risk %"] = risk_pct_arg
    df_to_write["Direction"] = direction_arg
    df_to_write["Portfolio"] = active_portfolio_arg
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

# 0.4.4. Statement Extraction Function ( เดิมคือ extract_data_from_report_sec7 / extract_data_from_report_sec4 )
def extract_data_from_statement(file_buffer, stat_definitions_arg):
    df_raw = None
    try:
        file_buffer.seek(0)
        if file_buffer.name.endswith('.csv'):
            df_raw = pd.read_csv(file_buffer, header=None, low_memory=False)
        elif file_buffer.name.endswith('.xlsx'):
            df_raw = pd.read_excel(file_buffer, header=None, engine='openpyxl')
    except Exception as e_read:
        st.error(f"Statement Import: เกิดข้อผิดพลาดในการอ่านไฟล์: {e_read}")
        return None

    if df_raw is None or df_raw.empty:
        st.warning("Statement Import: ไม่สามารถอ่านข้อมูลจากไฟล์ได้ หรือไฟล์ว่างเปล่า")
        return None

    section_starts = {}
    section_keywords = ["Positions", "Orders", "Deals", "History", "Results"]
    for keyword in section_keywords:
        if keyword not in section_starts: # Check to process each keyword only once
            for r_idx, row in df_raw.iterrows():
                if row.astype(str).str.contains(keyword, case=False, regex=False).any():
                    actual_key = "Deals" if keyword == "History" else keyword # Standardize "History" to "Deals"
                    if actual_key not in section_starts: # Ensure we only take the first occurrence
                        section_starts[actual_key] = r_idx
                    break # Found keyword, move to next keyword
    
    extracted_data = {}
    # Sort sections by their starting row to process them in order
    sorted_sections = sorted(section_starts.items(), key=lambda item: item[1])

    tabular_keywords = ["Positions", "Orders", "Deals"]
    for i, (section_name, start_row) in enumerate(sorted_sections):
        if section_name not in tabular_keywords:
            continue
        
        header_row_idx = start_row + 1
        # Skip any completely empty rows between section title and header
        while header_row_idx < len(df_raw) and df_raw.iloc[header_row_idx].isnull().all():
            header_row_idx += 1
        
        if header_row_idx < len(df_raw):
            headers = [str(h).strip() for h in df_raw.iloc[header_row_idx] if pd.notna(h) and str(h).strip() != '']
            data_start_row = header_row_idx + 1
            
            # Determine end_row for the current section
            end_row = len(df_raw) # Default to end of DataFrame
            if i + 1 < len(sorted_sections): # If there is a next section
                end_row = sorted_sections[i+1][1] # End before the next section starts
            
            df_section = df_raw.iloc[data_start_row:end_row].copy().dropna(how='all')
            
            if not df_section.empty:
                num_data_cols = df_section.shape[1]
                final_headers = headers[:num_data_cols] # Take headers up to the number of actual data columns
                if len(final_headers) < num_data_cols: # If fewer headers than data columns, pad with Unnamed
                    final_headers.extend([f'Unnamed_Stmt_{j}' for j in range(len(final_headers), num_data_cols)])
                
                df_section.columns = final_headers
                extracted_data[section_name.lower()] = df_section

    if "Results" in section_starts:
        results_stats = {}
        start_row_res = section_starts["Results"]
        # Scan a bit further for results, e.g., 20 rows after "Results" title
        results_df_scan_area = df_raw.iloc[start_row_res : start_row_res + 20] 
        
        for _, row_res in results_df_scan_area.iterrows():
            for c_idx_res, cell_res in enumerate(row_res):
                if pd.notna(cell_res):
                    label_res = str(cell_res).strip().replace(':', '')
                    if label_res in stat_definitions_arg:
                        # Look for value in subsequent cells (e.g., up to 4 cells away)
                        for k_val_offset in range(1, 5): 
                            if (c_idx_res + k_val_offset) < len(row_res):
                                value_candidate = row_res.iloc[c_idx_res + k_val_offset]
                                if pd.notna(value_candidate) and str(value_candidate).strip() != "":
                                    # Basic cleaning: take part before parenthesis, remove spaces
                                    clean_value = str(value_candidate).split('(')[0].strip().replace(' ', '')
                                    results_stats[label_res] = clean_value
                                    break # Found value for this label, move to next label
                        # break # Commented out: if a stat is found, we might want to find more on the same row
        if results_stats:
            extracted_data["balance_summary"] = pd.DataFrame(list(results_stats.items()), columns=['Metric', 'Value'])
            
    return extracted_data

# 0.4.5. Dashboard Data Loading Function ( เดิมคือ load_data_for_dashboard_sec5 / load_data_for_dashboard_sec9 )
def load_data_for_dashboard(active_portfolio_arg, current_portfolio_initial_balance):
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Log File (แผนเทรด)", "Statement Import (ผลเทรดจริง)"],
        index=0, # Default to Log File
        key="dashboard_source_selector" # Generic key
    )
    df_dashboard = pd.DataFrame()
    profit_col_identified, asset_col_identified, date_col_identified = None, None, None

    if source_option == "Log File (แผนเทรด)":
        if not active_portfolio_arg:
            st.warning("Dashboard: กรุณาเลือก Active Portfolio ใน Sidebar ก่อน")
            return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
        if os.path.exists(log_file):
            try:
                df_log_all = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all.columns:
                    st.warning("Dashboard: Log file ไม่มีคอลัมน์ 'Portfolio'")
                    return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
                df_dashboard = df_log_all[df_log_all["Portfolio"] == active_portfolio_arg].copy()
                if df_dashboard.empty:
                    st.info(f"Dashboard: ไม่พบข้อมูล Log File สำหรับพอร์ต '{active_portfolio_arg}'")
            except Exception as e_log_dash:
                st.error(f"Dashboard: ไม่สามารถโหลด Log File: {e_log_dash}")
        else:
            st.info(f"Dashboard: ไม่พบ Log File ({log_file})")
    
    else: # Statement Import (ผลเทรดจริง)
        if not active_portfolio_arg:
            st.warning("Dashboard: กรุณาเลือก Active Portfolio ใน Sidebar ก่อน")
            return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
        
        df_from_session = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame())
        if not df_from_session.empty:
            df_dashboard = df_from_session.copy()
            # Ensure it's for the active portfolio if the Portfolio column exists
            if 'Portfolio' in df_dashboard.columns:
                if not df_dashboard[df_dashboard['Portfolio'] == active_portfolio_arg].empty:
                    df_dashboard = df_dashboard[df_dashboard['Portfolio'] == active_portfolio_arg]
                else: # Data in session is not for current active port
                   df_dashboard = pd.DataFrame() 
        
        if df_dashboard.empty:
             st.info(f"Dashboard: ไม่มีข้อมูล Statement สำหรับพอร์ต '{active_portfolio_arg}' (โปรดอัปโหลดใน SEC ว่าด้วย Statement Import)")

    # --- Data Cleaning and Column Identification ---
    if not df_dashboard.empty:
        # Identify and Clean Profit column (Prefer 'Profit', fallback to 'Risk $')
        if 'Profit' in df_dashboard.columns:
            df_dashboard['Profit'] = pd.to_numeric(df_dashboard['Profit'], errors='coerce').fillna(0)
            # Check if 'Profit' column actually contains meaningful data after conversion
            if df_dashboard['Profit'].abs().sum() > 0 or ('Risk $' not in df_dashboard.columns): # Use Profit if it has data or Risk $ doesn't exist
                profit_col_identified = 'Profit'
        
        if not profit_col_identified and 'Risk $' in df_dashboard.columns: # Fallback for log file or if Profit is all zeros
            df_dashboard['Risk $'] = pd.to_numeric(df_dashboard['Risk $'], errors='coerce').fillna(0)
            profit_col_identified = 'Risk $'
        
        # Clean other potential numeric columns
        for col_numeric in ['RR', 'Lot', 'Commission', 'Swap', 'Volume', 'Price', 'S / L', 'T / P']: # Added Price, S/L, T/P
            if col_numeric in df_dashboard.columns:
                df_dashboard[col_numeric] = pd.to_numeric(df_dashboard[col_numeric], errors='coerce').fillna(0)

        # Identify Asset column
        if 'Asset' in df_dashboard.columns: asset_col_identified = 'Asset'
        elif 'Symbol' in df_dashboard.columns: asset_col_identified = 'Symbol'

        # Identify and convert Date column (pick the first valid one)
        date_col_options = [col for col in ["Timestamp", "Time", "Date", "Open Time", "Close Time"] if col in df_dashboard.columns]
        for col_date in date_col_options:
            try: # Attempt conversion, skip if it fails for all entries
                df_dashboard[col_date] = pd.to_datetime(df_dashboard[col_date], errors='coerce')
                if df_dashboard[col_date].notna().any(): # Check if any date was successfully parsed
                    date_col_identified = col_date
                    break
            except Exception:
                continue # Try next date column option
    
    return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified

# --- (อาจจะมีฟังก์ชันอื่นๆ ที่คุณสร้างไว้ เช่น Google Sheets functions ถ้าเปิดใช้งาน) ---

# ======================= END OF SEC 0 =======================

# ======================= SEC 1: SIDEBAR - CORE CONTROLS, PORTFOLIO, INPUTS, RISK MGMT =======================

# --- 1.0. Portfolio Selection & Management (UI in Sidebar) ---
# (ฟังก์ชัน load_portfolios และ save_portfolios ถูกประกาศไว้ใน SEC 0.4.1 แล้ว)
portfolios_df = load_portfolios()
acc_balance = 10000.0 # Default balance, will be updated by selected portfolio

st.sidebar.markdown("---")
st.sidebar.subheader("1.1. เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

if not portfolios_df.empty:
    portfolio_names_list = portfolios_df['portfolio_name'].tolist()
    
    current_active_portfolio_name_sb = st.session_state.get('active_portfolio_name', None)
    if current_active_portfolio_name_sb not in portfolio_names_list:
        st.session_state.active_portfolio_name = portfolio_names_list[0] if portfolio_names_list else None
    
    try:
        current_index_sb = portfolio_names_list.index(st.session_state.active_portfolio_name) if st.session_state.active_portfolio_name in portfolio_names_list else 0
    except ValueError:
        current_index_sb = 0

    selected_portfolio_name_sb = st.sidebar.selectbox(
        "เลือกพอร์ต:",
        options=portfolio_names_list,
        index=current_index_sb,
        key='sidebar_portfolio_selector' # Unique key for this selectbox
    )
    
    if selected_portfolio_name_sb != st.session_state.active_portfolio_name:
        st.session_state.active_portfolio_name = selected_portfolio_name_sb
        # No rerun here, let other interactions trigger rerun to avoid loops
        # Or explicitly rerun if immediate update of acc_balance is critical for subsequent sidebar items
        # For now, acc_balance update will happen on the next natural rerun

    if st.session_state.active_portfolio_name:
        active_portfolio_details_sb = portfolios_df[portfolios_df['portfolio_name'] == st.session_state.active_portfolio_name]
        if not active_portfolio_details_sb.empty:
            acc_balance = float(active_portfolio_details_sb['initial_balance'].iloc[0])
            st.sidebar.success(f"Active: **{st.session_state.active_portfolio_name}** (Bal: ${acc_balance:,.2f})")
        else:
            st.sidebar.error("ไม่พบรายละเอียดพอร์ตที่เลือก")
            st.session_state.active_portfolio_name = None # Reset if details not found
            acc_balance = 10000.0 # Reset to default
else:
    st.sidebar.info("ยังไม่มีพอร์ต กรุณาเพิ่มพอร์ตใน 'จัดการพอร์ต' (Main Area)")
    st.session_state.active_portfolio_name = None
    acc_balance = 10000.0 # Reset to default

# --- 1.2. Main Trade Setup ---
st.sidebar.header("1.2. 🎛️ Trade Setup & Controls")
drawdown_limit_pct_input = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)", 
    min_value=0.1, max_value=20.0, 
    value=st.session_state.get("sidebar_dd_limit_pct_config", 2.0), # Unique key for config
    step=0.1, format="%.1f", 
    key="sidebar_dd_limit_pct_config_val" # Main key
)
current_trade_mode = st.sidebar.radio(
    "Trade Mode", 
    ["FIBO", "CUSTOM"], 
    horizontal=True, 
    key="sidebar_current_trade_mode"
)

if st.sidebar.button("🔄 Reset Form", key="sidebar_btn_reset_form"):
    # Preserve essential states
    keys_to_preserve = {
        'active_portfolio_name', 'sidebar_portfolio_selector', 
        'sidebar_dd_limit_pct_config_val', 'sidebar_current_trade_mode'
    }
    # Clear other form-specific states
    for key in list(st.session_state.keys()):
        if key not in keys_to_preserve and \
           (key.startswith('fibo_') or key.startswith('custom_') or key.startswith('scaling_') or key.startswith('sidebar_dd_limit_pct_config')):
            del st.session_state[key]

    # Specifically reset fibo flags
    if "fibo_flags_inputs_list" in st.session_state: # Use a unique key for this list
        st.session_state.fibo_flags_inputs_list = [True] * 5 
    st.rerun()

# --- 1.3. FIBO Input Zone ---
entry_data_fibo_list = [] # Initialize here to ensure it's always available
if current_trade_mode == "FIBO":
    st.sidebar.subheader("1.3.1. FIBO Mode Inputs")
    st.session_state.fibo_asset = st.sidebar.text_input("Asset", value=st.session_state.get("fibo_asset","XAUUSD"), key="fibo_asset_val")
    st.session_state.fibo_risk_pct = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("fibo_risk_pct",1.0), step=0.01, key="fibo_risk_val")
    st.session_state.fibo_direction = st.sidebar.radio("Direction", ["Long", "Short"], horizontal=True, key="fibo_direction_val")
    st.session_state.fibo_swing_high = st.sidebar.text_input("High", key="fibo_high_val")
    st.session_state.fibo_swing_low = st.sidebar.text_input("Low", key="fibo_low_val")
    
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibo_levels_const_list = [0.114, 0.25, 0.382, 0.5, 0.618] # Define const list
    if "fibo_flags_inputs_list" not in st.session_state: 
        st.session_state.fibo_flags_inputs_list = [True] * len(fibo_levels_const_list)
    
    cols_fibo_cb_list = st.sidebar.columns(len(fibo_levels_const_list))
    for i, col_cb_fibo_item in enumerate(cols_fibo_cb_list): 
        st.session_state.fibo_flags_inputs_list[i] = col_cb_fibo_item.checkbox(
            f"{fibo_levels_const_list[i]:.3f}", 
            value=st.session_state.fibo_flags_inputs_list[i], 
            key=f"fibo_level_cb_val_{i}" # Unique key for each checkbox
        )
    
    # Calculation for FIBO (populates entry_data_fibo_list for summary and main area)
    try:
        high_fibo_calc = float(st.session_state.fibo_swing_high)
        low_fibo_calc = float(st.session_state.fibo_swing_low)
        if high_fibo_calc > low_fibo_calc and acc_balance > 0: # Ensure acc_balance is positive
            selected_fibs_calc = [fibo_levels_const_list[i] for i, sel in enumerate(st.session_state.fibo_flags_inputs_list) if sel]
            n_selected_fibs_calc = len(selected_fibs_calc)
            risk_dollar_total_calc = acc_balance * (st.session_state.fibo_risk_pct / 100)
            risk_dollar_per_entry_calc = risk_dollar_total_calc / n_selected_fibs_calc if n_selected_fibs_calc > 0 else 0
            
            for fib_level_item_calc in selected_fibs_calc:
                entry_p_calc = low_fibo_calc + (high_fibo_calc - low_fibo_calc) * fib_level_item_calc if st.session_state.fibo_direction == "Long" else high_fibo_calc - (high_fibo_calc - low_fibo_calc) * fib_level_item_calc
                sl_p_calc = low_fibo_calc if st.session_state.fibo_direction == "Long" else high_fibo_calc
                stop_p_calc = abs(entry_p_calc - sl_p_calc)
                lot_calc = (risk_dollar_per_entry_calc / stop_p_calc) if stop_p_calc > 0 else 0
                entry_data_fibo_list.append({
                    "Fibo Level": f"{fib_level_item_calc:.3f}", "Entry": f"{entry_p_calc:.2f}", "SL": f"{sl_p_calc:.2f}",
                    "Lot": f"{lot_calc:.2f}", "Risk $": f"{lot_calc * stop_p_calc:.2f}"
                })
    except (ValueError, TypeError, ZeroDivisionError): 
        pass # Silently pass if inputs are not valid numbers yet or acc_balance is zero
    
    save_fibo_button = st.sidebar.button("💾 Save Plan (FIBO)", key="sidebar_btn_save_fibo")

# --- 1.4. CUSTOM Input Zone ---
custom_entries_list = [] # Initialize here
if current_trade_mode == "CUSTOM":
    st.sidebar.subheader("1.4.1. CUSTOM Mode Inputs")
    st.session_state.custom_asset = st.sidebar.text_input("Asset", value=st.session_state.get("custom_asset","XAUUSD"), key="custom_asset_val")
    st.session_state.custom_risk_pct = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("custom_risk_pct",1.0), step=0.01, key="custom_risk_val")
    st.session_state.custom_n_entry = st.sidebar.number_input("จำนวนไม้", min_value=1, value=st.session_state.get("custom_n_entry",1), step=1, key="custom_n_entry_val")
    
    for i in range(int(st.session_state.custom_n_entry)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        e_cust = st.sidebar.text_input(f"Entry {i+1}", key=f"custom_entry_val_{i}")
        s_cust = st.sidebar.text_input(f"SL {i+1}", key=f"custom_sl_val_{i}")
        t_cust = st.sidebar.text_input(f"TP {i+1}", key=f"custom_tp_val_{i}")
        try:
            if acc_balance > 0: # Ensure acc_balance is positive
                risk_dollar_total_cust_calc = acc_balance * (st.session_state.custom_risk_pct / 100)
                risk_dollar_per_entry_cust_calc = risk_dollar_total_cust_calc / int(st.session_state.custom_n_entry) if int(st.session_state.custom_n_entry) > 0 else 0
                entry_p_cust_calc, sl_p_cust_calc, tp_p_cust_calc = float(e_cust), float(s_cust), float(t_cust)
                stop_p_cust_calc = abs(entry_p_cust_calc - sl_p_cust_calc)
                lot_cust_calc = (risk_dollar_per_entry_cust_calc / stop_p_cust_calc) if stop_p_cust_calc > 0 else 0
                rr_cust_calc = abs(tp_p_cust_calc - entry_p_cust_calc) / stop_p_cust_calc if stop_p_cust_calc > 0 else 0
                custom_entries_list.append({
                    "Entry": f"{entry_p_cust_calc:.2f}", "SL": f"{sl_p_cust_calc:.2f}", "TP": f"{tp_p_cust_calc:.2f}",
                    "Lot": f"{lot_cust_calc:.2f}", "Risk $": f"{lot_cust_calc * stop_p_cust_calc:.2f}", "RR": f"{rr_cust_calc:.2f}"
                })
        except (ValueError, TypeError, ZeroDivisionError): pass
    save_custom_button = st.sidebar.button("💾 Save Plan (CUSTOM)", key="sidebar_btn_save_custom")

# --- 1.5. Strategy Summary (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("1.5. 🧾 Strategy Summary")
if current_trade_mode == "FIBO" and entry_data_fibo_list:
    df_fibo_summary_display = pd.DataFrame(entry_data_fibo_list)
    st.sidebar.write(f"Total Lots: {pd.to_numeric(df_fibo_summary_display['Lot'], errors='coerce').sum():.2f}")
    st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_fibo_summary_display['Risk $'], errors='coerce').sum():.2f}")
elif current_trade_mode == "CUSTOM" and custom_entries_list:
    df_custom_summary_display = pd.DataFrame(custom_entries_list)
    st.sidebar.write(f"Total Lots: {pd.to_numeric(df_custom_summary_display['Lot'], errors='coerce').sum():.2f}")
    st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_custom_summary_display['Risk $'], errors='coerce').sum():.2f}")
else: st.sidebar.caption("กรอกข้อมูลและคำนวณเพื่อดู Summary")

# --- 1.6. Scaling Manager (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("1.6. ⚙️ Scaling Manager")
with st.sidebar.expander("Scaling Settings", expanded=False):
    scaling_step_config = st.number_input("Scaling Step (%)", min_value=0.01, value=st.session_state.get("scaling_step_cfg",0.25), step=0.01, key="scaling_step_cfg_val")
    min_risk_config = st.number_input("Minimum Risk %", min_value=0.01, value=st.session_state.get("scaling_min_risk_cfg",0.5), step=0.01, key="scaling_min_risk_cfg_val")
    max_risk_config = st.number_input("Maximum Risk %", min_value=0.01, value=st.session_state.get("scaling_max_risk_cfg",5.0), step=0.01, key="scaling_max_risk_cfg_val")
    scaling_mode_config = st.radio("Scaling Mode", ["Manual", "Auto"], horizontal=True, key="scaling_mode_cfg_radio")

if st.session_state.active_portfolio_name:
    winrate_scale_calc, gain_scale_calc, _ = get_performance_for_active_portfolio(log_file, st.session_state.active_portfolio_name)
    current_risk_for_scale_calc = st.session_state.fibo_risk_pct if current_trade_mode == "FIBO" else st.session_state.custom_risk_pct
    
    suggest_risk_display = current_risk_for_scale_calc
    msg_scale_display = f"Risk% ({st.session_state.active_portfolio_name}) คงที่: {current_risk_for_scale_calc:.2f}%"

    if acc_balance > 0 : # Ensure acc_balance is positive for meaningful scaling
        if winrate_scale_calc > 55 and gain_scale_calc > 0.02 * acc_balance:
            suggest_risk_display = min(current_risk_for_scale_calc + scaling_step_config, max_risk_config)
            msg_scale_display = f"🎉 ผลงานดี! ({st.session_state.active_portfolio_name}) แนะนำเพิ่ม Risk เป็น {suggest_risk_display:.2f}%"
        elif winrate_scale_calc < 45 or gain_scale_calc < 0:
            suggest_risk_display = max(current_risk_for_scale_calc - scaling_step_config, min_risk_config)
            msg_scale_display = f"⚠️ ควรลด Risk! ({st.session_state.active_portfolio_name}) แนะนำลด Risk เป็น {suggest_risk_display:.2f}%"
    
    st.sidebar.info(msg_scale_display)
    if scaling_mode_config == "Manual" and suggest_risk_display != current_risk_for_scale_calc:
        if st.sidebar.button(f"ปรับ Risk เป็น {suggest_risk_display:.2f}", key="sidebar_btn_scaling_adjust"):
            if current_trade_mode == "FIBO": st.session_state.fibo_risk_pct = suggest_risk_display
            else: st.session_state.custom_risk_pct = suggest_risk_display
            st.rerun()
    elif scaling_mode_config == "Auto" and suggest_risk_display != current_risk_for_scale_calc:
        if current_trade_mode == "FIBO": st.session_state.fibo_risk_pct = suggest_risk_display
        else: st.session_state.custom_risk_pct = suggest_risk_display
        # For Auto, we might want to indicate it has been auto-adjusted without rerun
        # st.sidebar.caption("Risk % auto-adjusted.") 
else:
    st.sidebar.caption("เลือก Active Portfolio เพื่อดูคำแนะนำ Scaling")


# --- 1.7. Drawdown Display & Lock Logic (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader(f"1.7. 🛡️ การควบคุมความเสี่ยง ({st.session_state.active_portfolio_name or 'N/A'})")
drawdown_today_val = 0.0
if st.session_state.active_portfolio_name:
    drawdown_today_val = get_today_drawdown_for_active_portfolio(log_file, st.session_state.active_portfolio_name)

drawdown_limit_abs_val = -acc_balance * (drawdown_limit_pct_input / 100) if acc_balance > 0 else 0
st.sidebar.metric(label="ขาดทุนรวมวันนี้ (Today's P/L)", value=f"{drawdown_today_val:,.2f} USD", delta_color="inverse")
st.sidebar.caption(f"ลิมิตขาดทุนต่อวัน: {drawdown_limit_abs_val:,.2f} USD ({drawdown_limit_pct_input:.1f}%)")

trade_locked = False
if acc_balance > 0 and drawdown_today_val != 0 and drawdown_today_val <= drawdown_limit_abs_val :
    st.sidebar.error(f"🔴 หยุดเทรด! เกินลิมิตขาดทุนสำหรับพอร์ต {st.session_state.active_portfolio_name}")
    trade_locked = True

# --- 1.8. Save Plan Button Logic (Consolidated) ---
# This logic uses variables populated by FIBO/CUSTOM input sections
asset_to_save_final, risk_pct_to_save_final, direction_to_save_final = "", 0.0, "N/A"
data_list_to_save = []

if current_trade_mode == "FIBO":
    asset_to_save_final = st.session_state.get("fibo_asset", "N/A")
    risk_pct_to_save_final = st.session_state.get("fibo_risk_pct", 0.0)
    direction_to_save_final = st.session_state.get("fibo_direction", "N/A")
    data_list_to_save = entry_data_fibo_list # Use the calculated list
    button_pressed = 'sidebar_btn_save_fibo' in st.session_state and st.session_state.sidebar_btn_save_fibo
elif current_trade_mode == "CUSTOM":
    asset_to_save_final = st.session_state.get("custom_asset", "N/A")
    risk_pct_to_save_final = st.session_state.get("custom_risk_pct", 0.0)
    direction_to_save_final = "N/A" # Direction N/A for custom
    data_list_to_save = custom_entries_list # Use the calculated list
    button_pressed = 'sidebar_btn_save_custom' in st.session_state and st.session_state.sidebar_btn_save_custom

if button_pressed:
    if not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    elif trade_locked:
        st.sidebar.error(f"ไม่สามารถบันทึกแผนสำหรับพอร์ต {st.session_state.active_portfolio_name} เนื่องจากเกินลิมิตขาดทุนรายวัน")
    elif data_list_to_save: # Check if data list is populated
        save_plan_to_log(data_list_to_save, current_trade_mode, asset_to_save_final, risk_pct_to_save_final, direction_to_save_final, st.session_state.active_portfolio_name)
    else:
        st.sidebar.warning(f"กรุณากรอกข้อมูล {current_trade_mode} ให้ครบถ้วนและให้ระบบคำนวณ Summary ก่อนบันทึก")

# ======================= END OF SEC 1 =======================

# ======================= SEC 2: MAIN AREA - CURRENT ENTRY PLAN DETAILS =======================
st.header("🎯 Entry Plan Details")

if st.session_state.active_portfolio_name:
    st.caption(f"สำหรับพอร์ต: **{st.session_state.active_portfolio_name}** (Balance: ${acc_balance:,.2f})") # แสดง Balance ด้วย
    
    if current_trade_mode == "FIBO":
        if entry_data_fibo_list: # entry_data_fibo_list ถูกคำนวณและอัปเดตใน SEC 1
            df_display_fibo = pd.DataFrame(entry_data_fibo_list)
            st.dataframe(df_display_fibo, hide_index=True, use_container_width=True)
            
            # (Optional) เพิ่มการแสดง TP Zones สำหรับ FIBO ที่นี่ได้ ถ้าต้องการ
            # try:
            #     high_fibo_val_tp = float(st.session_state.fibo_swing_high)
            #     low_fibo_val_tp = float(st.session_state.fibo_swing_low)
            #     if high_fibo_val_tp > low_fibo_val_tp:
            #         tp1 = low_fibo_val_tp + (high_fibo_val_tp - low_fibo_val_tp) * 1.618 if st.session_state.fibo_direction == "Long" else high_fibo_val_tp - (high_fibo_val_tp - low_fibo_val_tp) * 1.618
            #         tp2 = low_fibo_val_tp + (high_fibo_val_tp - low_fibo_val_tp) * 2.618 if st.session_state.fibo_direction == "Long" else high_fibo_val_tp - (high_fibo_val_tp - low_fibo_val_tp) * 2.618
            #         tp3 = low_fibo_val_tp + (high_fibo_val_tp - low_fibo_val_tp) * 4.236 if st.session_state.fibo_direction == "Long" else high_fibo_val_tp - (high_fibo_val_tp - low_fibo_val_tp) * 4.236
            #         st.write("Take Profit Zones (FIBO):")
            #         st.write(f"TP1 (1.618): {tp1:.2f}")
            #         st.write(f"TP2 (2.618): {tp2:.2f}")
            #         st.write(f"TP3 (4.236): {tp3:.2f}")
            # except (ValueError, TypeError):
            #     st.caption("กรอก High/Low เพื่อดู TP Zones")

        else:
            # แสดงโครงตารางเปล่าสำหรับ FIBO
            df_empty_fibo = pd.DataFrame(columns=["Fibo Level", "Entry", "SL", "Lot", "Risk $"])
            st.dataframe(df_empty_fibo, hide_index=True, use_container_width=True)
            st.info("กรอกข้อมูลใน Sidebar (FIBO) และให้ระบบคำนวณเพื่อดูรายละเอียดแผน")

    elif current_trade_mode == "CUSTOM":
        if custom_entries_list: # custom_entries_list ถูกคำนวณและอัปเดตใน SEC 1
            df_display_custom = pd.DataFrame(custom_entries_list)
            st.dataframe(df_display_custom, hide_index=True, use_container_width=True)
        else:
            # แสดงโครงตารางเปล่าสำหรับ CUSTOM
            df_empty_custom = pd.DataFrame(columns=["Entry", "SL", "TP", "Lot", "Risk $", "RR"])
            st.dataframe(df_empty_custom, hide_index=True, use_container_width=True)
            st.info("กรอกข้อมูลใน Sidebar (CUSTOM) และให้ระบบคำนวณเพื่อดูรายละเอียดแผน")
else:
    st.warning("กรุณาเลือก Active Portfolio ใน Sidebar เพื่อดูและสร้างรายละเอียดแผน")

st.markdown("---")
# ======================= END OF SEC 2 =======================


