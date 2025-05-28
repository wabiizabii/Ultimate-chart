# ======================= main.py (ฉบับยกเครื่องใหม่ สมบูรณ์) =======================
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl # สำหรับ engine='openpyxl'
import os
from datetime import datetime, timedelta
import plotly.express as px
import google.generativeai as genai # สำหรับ AI Advisor

# ======================= SEC 0: INITIAL SETUP & ALL FUNCTION DEFINITIONS =======================
# 0.1. Page Config
st.set_page_config(
    page_title="Ultimate Trading Dashboard",
    page_icon="📊",
    layout="wide" 
)

# 0.2. Initial Variables & File Paths
# acc_balance will be dynamically set by the selected portfolio
# default_acc_balance = 10000 # Default if no portfolio is selected or has no balance
log_file = "trade_log.csv"
PORTFOLIO_FILE = 'portfolios.csv'

# 0.3. Google API Key Placeholder (User will input via UI)
# GOOGLE_API_KEY_FROM_USER = "" # Defined in SEC 5 (Dashboard AI Tab)

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
            # Convert initial_balance to numeric, coercing errors
            df['initial_balance'] = pd.to_numeric(df['initial_balance'], errors='coerce').fillna(0)
            return df
        except pd.errors.EmptyDataError:
            # st.info(f"ไฟล์ {PORTFOLIO_FILE} ว่างเปล่า กำลังสร้าง DataFrame ใหม่")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลด {PORTFOLIO_FILE}: {e}")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
    else:
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
            return 0 # Or handle as global if no portfolio column exists
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
        else:
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
        # st.error(f"Error in get_performance_for_active_portfolio: {e}")
        return 0,0,0

# 0.4.3. Save Plan Function
def save_plan_to_log(data_to_save, trade_mode_arg, asset_arg, risk_pct_arg, direction_arg, active_portfolio_arg):
    if not active_portfolio_arg:
        st.sidebar.error("ไม่สามารถบันทึกแผน: กรุณาเลือกหรือสร้างพอร์ตก่อน")
        return
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

# 0.4.4. Statement Extraction Function (for SEC 4 - Statement Import)
def extract_data_from_report_sec4(file_buffer, stat_definitions_arg): # Renamed for clarity
    df_raw_sec4 = None
    try:
        file_buffer.seek(0)
        if file_buffer.name.endswith('.csv'):
            df_raw_sec4 = pd.read_csv(file_buffer, header=None, low_memory=False)
        elif file_buffer.name.endswith('.xlsx'):
            df_raw_sec4 = pd.read_excel(file_buffer, header=None, engine='openpyxl')
    except Exception as e_read:
        st.error(f"SEC 4: เกิดข้อผิดพลาดในการอ่านไฟล์: {e_read}")
        return None

    if df_raw_sec4 is None or df_raw_sec4.empty:
        st.warning("SEC 4: ไม่สามารถอ่านข้อมูลจากไฟล์ได้ หรือไฟล์ว่างเปล่า")
        return None

    section_starts_sec4 = {}
    section_keywords_sec4 = ["Positions", "Orders", "Deals", "History", "Results"]
    for keyword_s4 in section_keywords_sec4:
        if keyword_s4 not in section_starts_sec4:
            for r_idx_s4, row_s4 in df_raw_sec4.iterrows():
                if row_s4.astype(str).str.contains(keyword_s4, case=False, regex=False).any():
                    actual_key_s4 = "Deals" if keyword_s4 == "History" else keyword_s4
                    if actual_key_s4 not in section_starts_sec4:
                        section_starts_sec4[actual_key_s4] = r_idx_s4
                    break
    
    extracted_data_sec4 = {}
    sorted_sections_s4 = sorted(section_starts_sec4.items(), key=lambda x_s4: x_s4[1])

    tabular_keywords_s4 = ["Positions", "Orders", "Deals"]
    for i_s4, (section_name_s4, start_row_s4) in enumerate(sorted_sections_s4):
        if section_name_s4 not in tabular_keywords_s4:
            continue
        header_row_idx_s4 = start_row_s4 + 1
        while header_row_idx_s4 < len(df_raw_sec4) and df_raw_sec4.iloc[header_row_idx_s4].isnull().all():
            header_row_idx_s4 += 1
        if header_row_idx_s4 < len(df_raw_sec4):
            headers_s4 = [str(h_s4).strip() for h_s4 in df_raw_sec4.iloc[header_row_idx_s4] if pd.notna(h_s4) and str(h_s4).strip() != '']
            data_start_row_s4 = header_row_idx_s4 + 1
            end_row_s4 = len(df_raw_sec4)
            if i_s4 + 1 < len(sorted_sections_s4):
                end_row_s4 = sorted_sections_s4[i_s4+1][1]
            df_section_s4 = df_raw_sec4.iloc[data_start_row_s4:end_row_s4].copy().dropna(how='all')
            if not df_section_s4.empty:
                num_data_cols_s4 = df_section_s4.shape[1]
                final_headers_s4 = headers_s4[:num_data_cols_s4]
                if len(final_headers_s4) < num_data_cols_s4:
                    final_headers_s4.extend([f'Unnamed_S4:{j_s4}' for j_s4 in range(len(final_headers_s4), num_data_cols_s4)])
                df_section_s4.columns = final_headers_s4
                extracted_data_sec4[section_name_s4.lower()] = df_section_s4

    if "Results" in section_starts_sec4:
        results_stats_s4 = {}
        start_row_res_s4 = section_starts_sec4["Results"]
        results_df_s4 = df_raw_sec4.iloc[start_row_res_s4 : start_row_res_s4 + 20] # Increased scan range for stats
        for _, row_res_s4 in results_df_s4.iterrows():
            for c_idx_res_s4, cell_res_s4 in enumerate(row_res_s4):
                if pd.notna(cell_res_s4):
                    label_res_s4 = str(cell_res_s4).strip().replace(':', '')
                    if label_res_s4 in stat_definitions_arg:
                        for k_s4 in range(1, 5): # Increased lookahead for value
                            if (c_idx_res_s4 + k_s4) < len(row_res_s4):
                                value_s4 = row_res_s4.iloc[c_idx_res_s4 + k_s4]
                                if pd.notna(value_s4) and str(value_s4).strip() != "":
                                    clean_value_s4 = str(value_s4).split('(')[0].strip() # "123 (xxx)" -> "123"
                                    clean_value_s4 = clean_value_s4.replace(' ', '') # Remove spaces for numbers like "1 234.56"
                                    results_stats_s4[label_res_s4] = clean_value_s4
                                    break 
                        # break # Removed this break to allow finding multiple stats in the same row if structured differently
        if results_stats_s4:
            extracted_data_sec4["balance_summary"] = pd.DataFrame(list(results_stats_s4.items()), columns=['Metric', 'Value'])
    return extracted_data_sec4

# 0.4.5. Dashboard Data Loading Function (for SEC 5 - Dashboard)
def load_data_for_dashboard_sec5(active_portfolio_arg, current_acc_balance_for_dash): # Renamed for clarity
    source_option_sec5 = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Log File (แผนเทรด)", "Statement Import (ผลเทรดจริง)"],
        index=0,
        key="dashboard_source_selector_sec5"
    )
    df_dashboard_sec5 = pd.DataFrame()

    if source_option_sec5 == "Log File (แผนเทรด)":
        if not active_portfolio_arg:
            st.warning("SEC 5: กรุณาเลือก Active Portfolio ใน Sidebar ก่อน")
            return df_dashboard_sec5, None, None, None # Return empty df and None for cols
        if os.path.exists(log_file):
            try:
                df_log_all_sec5 = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all_sec5.columns:
                    st.warning("SEC 5: Log file ไม่มีคอลัมน์ 'Portfolio'")
                    return df_dashboard_sec5, None, None, None
                df_dashboard_sec5 = df_log_all_sec5[df_log_all_sec5["Portfolio"] == active_portfolio_arg].copy()
                if df_dashboard_sec5.empty:
                    st.info(f"SEC 5: ไม่พบข้อมูล Log File สำหรับพอร์ต '{active_portfolio_arg}'")
            except Exception as e_log_s5:
                st.error(f"SEC 5: ไม่สามารถโหลด Log File: {e_log_s5}")
        else:
            st.info(f"SEC 5: ไม่พบ Log File ({log_file})")
    
    else: # Statement Import (ผลเทรดจริง)
        if not active_portfolio_arg:
            st.warning("SEC 5: กรุณาเลือก Active Portfolio ใน Sidebar ก่อน")
            return df_dashboard_sec5, None, None, None
        
        # Use df_stmt_current_active_portfolio which should be for the active portfolio
        df_from_session = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame())
        if not df_from_session.empty:
            df_dashboard_sec5 = df_from_session.copy()
            # Ensure it's for the active portfolio if the Portfolio column exists (it should after SEC 4 update)
            if 'Portfolio' in df_dashboard_sec5.columns:
                if not df_dashboard_sec5[df_dashboard_sec5['Portfolio'] == active_portfolio_arg].empty:
                    df_dashboard_sec5 = df_dashboard_sec5[df_dashboard_sec5['Portfolio'] == active_portfolio_arg]
                # else: # Data in session is not for current active port, this case should be handled by SEC 4 update
                #    df_dashboard_sec5 = pd.DataFrame() 
            # else: # If df_stmt_current_active_portfolio somehow doesn't have Portfolio col, means it's already filtered.
            #    pass
        
        if df_dashboard_sec5.empty:
             st.info(f"SEC 5: ไม่มีข้อมูล Statement สำหรับพอร์ต '{active_portfolio_arg}' (โปรดอัปโหลดใน SEC 4)")

    # --- Data Cleaning and Column Identification ---
    profit_col_identified_sec5 = None
    asset_col_identified_sec5 = None
    date_col_identified_sec5 = None

    if not df_dashboard_sec5.empty:
        # Clean and identify Profit column
        if 'Profit' in df_dashboard_sec5.columns:
            df_dashboard_sec5['Profit'] = pd.to_numeric(df_dashboard_sec5['Profit'], errors='coerce').fillna(0)
            if df_dashboard_sec5['Profit'].abs().sum() > 0:
                profit_col_identified_sec5 = 'Profit'
        if not profit_col_identified_sec5 and 'Risk $' in df_dashboard_sec5.columns: # Fallback for log file
            df_dashboard_sec5['Risk $'] = pd.to_numeric(df_dashboard_sec5['Risk $'], errors='coerce').fillna(0)
            profit_col_identified_sec5 = 'Risk $'
        
        # Clean other numeric columns if they exist
        for col_numeric in ['RR', 'Lot', 'Commission', 'Swap', 'Volume']:
            if col_numeric in df_dashboard_sec5.columns:
                df_dashboard_sec5[col_numeric] = pd.to_numeric(df_dashboard_sec5[col_numeric], errors='coerce').fillna(0)

        # Identify Asset column
        if 'Asset' in df_dashboard_sec5.columns: asset_col_identified_sec5 = 'Asset'
        elif 'Symbol' in df_dashboard_sec5.columns: asset_col_identified_sec5 = 'Symbol'

        # Identify and convert Date column
        date_col_options_sec5 = [col for col in ["Timestamp", "Time", "Date", "Open Time", "Close Time"] if col in df_dashboard_sec5.columns] # Added "Time"
        for col_date_s5 in date_col_options_sec5:
            df_dashboard_sec5[col_date_s5] = pd.to_datetime(df_dashboard_sec5[col_date_s5], errors='coerce')
            if df_dashboard_sec5[col_date_s5].notna().any(): # Pick first valid date column
                date_col_identified_sec5 = col_date_s5
                break
    
    return df_dashboard_sec5, profit_col_identified_sec5, asset_col_identified_sec5, date_col_identified_sec5


# ======================= SEC 1: SIDEBAR - CORE CONTROLS, INPUTS, SUMMARY, SCALING, DRAWDOWN =======================
# (Portfolio Selection and Management UI is now in SEC 0.8, executed before this)
st.sidebar.header("🎛️ Trade Setup & Controls")

# 1.1. Main Trade Setup (Drawdown Limit, Trade Mode, Reset Form)
# Drawdown Limit (already defined as drawdown_limit_pct_input)
# Trade Mode (already defined as current_trade_mode)
# Reset Form Button (already defined)

# 1.2. FIBO Input Zone (if mode is FIBO)
entry_data_fibo_list = []
if current_trade_mode == "FIBO":
    st.sidebar.subheader("FIBO Mode Inputs")
    # asset_input_fibo, risk_pct_input_fibo, etc. are already defined above
    # ... (rest of your FIBO input UI from main.py, like fibo_levels checkboxes)
    # For calculation and table:
    try:
        high_fibo = float(st.session_state.get("fibo_swing_high",0))
        low_fibo = float(st.session_state.get("fibo_swing_low",0))
        risk_fibo = st.session_state.get("fibo_risk_pct",1.0)
        direction_fibo = st.session_state.get("fibo_direction", "Long")
        fibo_flags_current = st.session_state.get("fibo_flags_inputs", [True]*5)
        active_port_bal = acc_balance # This is now set based on active portfolio
        
        if high_fibo > low_fibo:
            selected_fib_levels_actual = [fibo_levels[i] for i, sel in enumerate(fibo_flags_current) if sel]
            n_selected_fibs = len(selected_fib_levels_actual)
            risk_dollar_total_fibo = active_port_bal * (risk_fibo / 100)
            risk_dollar_per_entry_fibo = risk_dollar_total_fibo / n_selected_fibs if n_selected_fibs > 0 else 0

            for fib_level in selected_fib_levels_actual:
                if direction_fibo == "Long":
                    entry_p_fibo = low_fibo + (high_fibo - low_fibo) * fib_level
                    sl_p_fibo = low_fibo # Simplified SL
                else: # Short
                    entry_p_fibo = high_fibo - (high_fibo - low_fibo) * fib_level
                    sl_p_fibo = high_fibo # Simplified SL
                
                stop_fibo = abs(entry_p_fibo - sl_p_fibo)
                lot_fibo = (risk_dollar_per_entry_fibo / stop_fibo) if stop_fibo > 0 else 0
                risk_val_fibo = lot_fibo * stop_fibo
                entry_data_fibo_list.append({
                    "Fibo Level": f"{fib_level:.3f}", "Entry": f"{entry_p_fibo:.2f}", "SL": f"{sl_p_fibo:.2f}",
                    "Lot": f"{lot_fibo:.2f}", "Risk $": f"{risk_val_fibo:.2f}"
                })
    except ValueError: # Handle cases where high/low are not numbers yet
        pass
    except Exception as e_fibo_calc:
        st.sidebar.warning(f"Fibo calc error: {e_fibo_calc}")


# 1.3. CUSTOM Input Zone (if mode is CUSTOM)
custom_entries_list = []
if current_trade_mode == "CUSTOM":
    st.sidebar.subheader("CUSTOM Mode Inputs")
    # asset_input_custom, risk_pct_input_custom, n_entry_input_custom are defined above
    # ... (rest of your CUSTOM input UI from main.py, looping through n_entry)
    # For calculation and table:
    try:
        num_entries_custom = int(st.session_state.get("custom_n_entry",1))
        risk_custom = st.session_state.get("custom_risk_pct",1.0)
        active_port_bal_custom = acc_balance
        risk_dollar_total_custom = active_port_bal_custom * (risk_custom / 100)
        risk_dollar_per_entry_custom = risk_dollar_total_custom / num_entries_custom if num_entries_custom > 0 else 0

        for i_c in range(num_entries_custom):
            entry_c = float(st.session_state.get(f"custom_entry_{i_c}",0))
            sl_c = float(st.session_state.get(f"custom_sl_{i_c}",0))
            tp_c = float(st.session_state.get(f"custom_tp_{i_c}",0))
            stop_c = abs(entry_c - sl_c)
            lot_c = (risk_dollar_per_entry_custom / stop_c) if stop_c > 0 else 0
            risk_val_c = lot_c * stop_c
            rr_c = abs(tp_c - entry_c) / stop_c if stop_c > 0 else 0
            custom_entries_list.append({
                "Entry": f"{entry_c:.2f}", "SL": f"{sl_c:.2f}", "TP": f"{tp_c:.2f}",
                "Lot": f"{lot_c:.2f}", "Risk $": f"{risk_val_c:.2f}", "RR": f"{rr_c:.2f}"
            })
    except ValueError: # Handle cases where entry/sl/tp are not numbers yet
        pass
    except Exception as e_custom_calc:
        st.sidebar.warning(f"Custom calc error: {e_custom_calc}")

# 1.4. Strategy Summary in Sidebar (Now uses calculated lists)
# (This section was SEC 4 in your old code)
# The actual display of total lots/risk is already integrated into the FIBO/CUSTOM calculation blocks above.

# 1.5. Scaling Manager & Suggestion in Sidebar
# (This was SEC 1.X & 1.5 in your old code)
# The UI for settings (scaling_step_input etc.) and display (scaling_msg_display etc.) are already in SEC 0.

# 1.6. Drawdown Display & Lock Logic in Sidebar
# (This was SEC 5 in your old code)
# The UI for drawdown (daily_drawdown_value etc.) is already in SEC 0.

# 1.7. Save Plan Button Logic (Consolidated)
# (This was part of SEC 5 in your old code)
# The save_fibo_button and save_custom_button are defined in section 1.2 and 1.3
# The logic for handling their clicks (calling save_plan_to_log) is also in SEC 0 (Function Definitions part).
# Make sure the button click handling uses the correct variables based on mode.

# Determine asset and risk_pct for saving based on current_trade_mode
asset_to_save = ""
risk_pct_to_save = 0.0
direction_to_save = "N/A"

if current_trade_mode == "FIBO":
    asset_to_save = st.session_state.get("fibo_asset", "N/A")
    risk_pct_to_save = st.session_state.get("fibo_risk_pct", 0.0)
    direction_to_save = st.session_state.get("fibo_direction", "N/A")
    if 'fibo_save_plan_button' in st.session_state and st.session_state.fibo_save_plan_button: # Check if button exists and was clicked
        if not st.session_state.active_portfolio_name:
            st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
        elif trade_locked: # trade_locked defined in SEC 0
            st.sidebar.error(f"ไม่สามารถบันทึกแผนสำหรับพอร์ต {st.session_state.active_portfolio_name} เนื่องจากเกินลิมิตขาดทุนรายวัน")
        elif entry_data_fibo_list:
            save_plan_to_log(entry_data_fibo_list, "FIBO", asset_to_save, risk_pct_to_save, direction_to_save, st.session_state.active_portfolio_name)
        else:
            st.sidebar.warning("กรุณากรอกข้อมูล FIBO ให้ครบถ้วนและให้ระบบคำนวณ Summary ก่อนบันทึก")


elif current_trade_mode == "CUSTOM":
    asset_to_save = st.session_state.get("custom_asset", "N/A")
    risk_pct_to_save = st.session_state.get("custom_risk_pct", 0.0)
    # Direction is not typically part of custom multi-entry, can be N/A or derived if needed
    if 'custom_save_plan_button' in st.session_state and st.session_state.custom_save_plan_button: # Check if button exists and was clicked
        if not st.session_state.active_portfolio_name:
            st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
        elif trade_locked: # trade_locked defined in SEC 0
            st.sidebar.error(f"ไม่สามารถบันทึกแผนสำหรับพอร์ต {st.session_state.active_portfolio_name} เนื่องจากเกินลิมิตขาดทุนรายวัน")
        elif custom_entries_list:
            save_plan_to_log(custom_entries_list, "CUSTOM", asset_to_save, risk_pct_to_save, "N/A", st.session_state.active_portfolio_name)
        else:
            st.sidebar.warning("กรุณากรอกข้อมูล CUSTOM ให้ครบถ้วนและให้ระบบคำนวณ Summary ก่อนบันทึก")


# ======================= SEC 2: MAIN AREA - CURRENT ENTRY PLAN DETAILS =======================
# (This was SEC 2+3 in your old structure)
st.header("🎯 Entry Plan Details")
if st.session_state.active_portfolio_name:
    st.caption(f"สำหรับพอร์ต: **{st.session_state.active_portfolio_name}**")
    if current_trade_mode == "FIBO":
        if entry_data_fibo_list: # Use the list populated in SEC 1
            st.dataframe(pd.DataFrame(entry_data_fibo_list), hide_index=True, use_container_width=True)
            # You can add TP Zones calculation and display for FIBO here if needed
        else:
            st.info("กรอกข้อมูลใน Sidebar (FIBO) เพื่อดู Entry Plan.")
    elif current_trade_mode == "CUSTOM":
        if custom_entries_list: # Use the list populated in SEC 1
            st.dataframe(pd.DataFrame(custom_entries_list), hide_index=True, use_container_width=True)
        else:
            st.info("กรอกข้อมูลใน Sidebar (CUSTOM) เพื่อดู Entry Plan.")
else:
    st.warning("กรุณาเลือก Active Portfolio ใน Sidebar เพื่อดูรายละเอียดแผน")
st.markdown("---")

# ======================= SEC 3: MAIN AREA - CHART VISUALIZER =======================
# (This was SEC B in your old structure)
with st.expander("📈 Chart Visualizer", expanded=True):
    # Simple placeholder for TradingView widget
    # You would put your st.components.v1.html code here
    # Ensure the symbol in the widget can be dynamically updated if needed
    
    # Default symbol or from current trade plan
    chart_symbol = "OANDA:XAUUSD" 
    if current_trade_mode == "FIBO" and asset_to_save != "N/A":
        chart_symbol = asset_to_save
    elif current_trade_mode == "CUSTOM" and asset_to_save != "N/A":
        chart_symbol = asset_to_save
    
    # Attempt to format for TradingView (common prefixes)
    if "XAUUSD" in chart_symbol.upper(): chart_symbol = "OANDA:XAUUSD"
    elif "BTCUSD" in chart_symbol.upper(): chart_symbol = "BINANCE:BTCUSDT" # Example

    # Check if plot button exists in session state before creating it
    # This is to avoid error if the button itself is conditional and not always rendered
    # For now, let's assume button is always there or handle its state if needed.
    
    plot_chart_button = st.button("Plot Active Plan on Chart", key="plot_chart_button_main")

    if plot_chart_button:
        st.components.v1.html(f"""
        <div class="tradingview-widget-container">
          <div id="tradingview_widget_main"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({{
            "width": "100%",
            "height": 600,
            "symbol": "{chart_symbol}",
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
            "container_id": "tradingview_widget_main"
          }});
          </script>
        </div>
        """, height=620)
    else:
        st.info("กดปุ่ม 'Plot Active Plan on Chart' เพื่อแสดงกราฟ TradingView")
st.markdown("---")


# ======================= SEC 4: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
# (This was SEC 7 in your old structure)
# The functions extract_data_from_report_sec4 and stat_definitions_sec7 are defined in SEC 0
# Renamed stat_definitions_sec7 to stat_definitions_for_stmt_import for clarity
stat_definitions_for_stmt_import = {
    "Total Net Profit", "Gross Profit", "Gross Loss", "Profit Factor", "Expected Payoff", "Recovery Factor",
    "Sharpe Ratio", "Balance Drawdown Absolute", "Balance Drawdown Maximal", "Balance Drawdown Relative",
    "Total Trades", "Short Trades (won %)", "Long Trades (won %)", "Profit Trades (% of total)", 
    "Loss Trades (% of total)", "Largest profit trade", "Largest loss trade", "Average profit trade", 
    "Average loss trade", "Maximum consecutive wins ($)", "Maximal consecutive profit (count)",
    "Average consecutive wins", "Maximum consecutive losses ($)", "Maximal consecutive loss (count)", 
    "Average consecutive losses"
}

with st.expander("📂 SEC 4: Statement Import & Auto-Mapping", expanded=False):
    # UI for file uploader (already defined as uploaded_files_sec7)
    # Debug mode checkbox (already defined as st.session_state.sec7_debug_display_mode)
    
    if uploaded_files_sec7: # Variable from SEC 0
        if not st.session_state.active_portfolio_name:
            st.warning("SEC 4: กรุณาเลือก 'Active Portfolio' ใน Sidebar ก่อนอัปโหลด Statement")
        else:
            active_portfolio_for_statement = st.session_state.active_portfolio_name
            st.info(f"ไฟล์ที่อัปโหลดใน SEC 4 จะเชื่อมโยงกับพอร์ต: **{active_portfolio_for_statement}**")

            for uploaded_file_item_s4 in uploaded_files_sec7: # Use unique variable name
                st.info(f"กำลังประมวลผล (SEC 4): {uploaded_file_item_s4.name} สำหรับพอร์ต {active_portfolio_for_statement}")
                with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {uploaded_file_item_s4.name}..."):
                    extracted_data_s4 = extract_data_from_report_sec4(uploaded_file_item_s4, stat_definitions_for_stmt_import)
                    
                    if extracted_data_s4:
                        st.success(f"ประมวลผลสำเร็จ (SEC 4)! พบข้อมูล: {', '.join(extracted_data_s4.keys())}")

                        if 'deals' in extracted_data_s4:
                            df_deals_new_s4 = extracted_data_s4['deals'].copy()
                            df_deals_new_s4['Portfolio'] = active_portfolio_for_statement
                            st.session_state.df_stmt_current_active_portfolio = df_deals_new_s4 # Update session state for current port
                        
                        # Store all data for this portfolio and file (can be complex if storing all history)
                        # For now, st.session_state.all_statement_data stores by portfolio, then by filename
                        if active_portfolio_for_statement not in st.session_state.all_statement_data:
                             st.session_state.all_statement_data[active_portfolio_for_statement] = {}
                        st.session_state.all_statement_data[active_portfolio_for_statement][uploaded_file_item_s4.name] = extracted_data_s4

                        if 'balance_summary' in extracted_data_s4:
                            st.write(f"### 📊 Balance Summary ({active_portfolio_for_statement} - {uploaded_file_item_s4.name})")
                            st.dataframe(extracted_data_s4['balance_summary'])
                        
                        if st.session_state.get('sec7_debug_display_mode', False): # Use correct debug key
                            for section_key_s4, section_df_item_s4 in extracted_data_s4.items():
                                if section_key_s4 != 'balance_summary':
                                    st.write(f"### 📄 ข้อมูลส่วน ({active_portfolio_for_statement} - {section_key_s4.title()}):")
                                    st.dataframe(section_df_item_s4)
                    else:
                        st.warning(f"ไม่สามารถแยกส่วนข้อมูลใดๆ จากไฟล์ {uploaded_file_item_s4.name} (SEC 4)")
    else:
        st.info("ยังไม่มีไฟล์ Statement อัปโหลด (SEC 4)")

    st.markdown("---")
    st.subheader(f"📁 Deals ล่าสุดของพอร์ต (SEC 4): {st.session_state.active_portfolio_name or 'N/A'}")
    current_stmt_df_display = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame())
    if not current_stmt_df_display.empty and st.session_state.active_portfolio_name:
        # Ensure we only show data for the truly active portfolio if the df still holds mixed data
        if 'Portfolio' in current_stmt_df_display.columns:
            display_df = current_stmt_df_display[current_stmt_df_display['Portfolio'] == st.session_state.active_portfolio_name]
            if not display_df.empty:
                st.dataframe(display_df)
            else:
                st.info(f"ไม่มีข้อมูล Deals สำหรับพอร์ต {st.session_state.active_portfolio_name} ใน Statement ปัจจุบัน")
        else: # If no Portfolio column, assume it's already filtered
            st.dataframe(current_stmt_df_display)
    else:
        st.info(f"ไม่มีข้อมูล Deals สำหรับแสดงของพอร์ต {st.session_state.active_portfolio_name}")

    if st.button("🗑️ ล้างข้อมูล Statement ปัจจุบันของพอร์ตนี้ (SEC 4)", key="sec4_clear_stmt_button"):
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
        if st.session_state.active_portfolio_name and st.session_state.active_portfolio_name in st.session_state.all_statement_data:
            # Optionally clear more specific data from all_statement_data
            # For now, just clears the 'current view' for active portfolio
            pass
        st.success("ล้างข้อมูล Statement ปัจจุบันที่แสดงผลแล้ว (SEC 4)")
        st.rerun()
st.markdown("---")

# ======================= SEC 5: MAIN AREA - PERFORMANCE DASHBOARD =======================
# (This was SEC 9 in your old structure)
# The function load_data_for_dashboard_sec5 is defined in SEC 0
with st.expander("📊 Performance Dashboard (SEC 5)", expanded=True):
    if not st.session_state.active_portfolio_name:
        st.warning("กรุณาเลือก 'Active Portfolio' ใน Sidebar เพื่อดู Dashboard")
    else:
        active_portfolio_for_dash = st.session_state.active_portfolio_name
        # Get the initial balance for the active portfolio
        initial_balance_for_dash = acc_balance # Default to global, but will be updated
        if not portfolios_df.empty and active_portfolio_for_dash in portfolios_df['portfolio_name'].values:
            initial_balance_for_dash = portfolios_df[portfolios_df['portfolio_name'] == active_portfolio_for_dash]['initial_balance'].iloc[0]
        
        st.subheader(f"Dashboard สำหรับพอร์ต: {active_portfolio_for_dash} (เริ่มต้น: ${initial_balance_for_dash:,.2f})")
        df_data_for_dash, profit_col_for_dash, asset_col_for_dash, date_col_for_dash = load_data_for_dashboard_sec5(active_portfolio_for_dash, initial_balance_for_dash)

        tab_names_sec5 = ["📊 Dashboard", "📈 RR", "📉 Lot Size", "🕒 Time", "🤖 AI Advisor", "⬇️ Export"]
        tabs_main_dash, tabs_rr_dash, tabs_lot_dash, tabs_time_dash, tabs_ai_dash, tabs_export_dash = st.tabs(tab_names_sec5)

        if df_data_for_dash.empty:
            st.info(f"SEC 5: ยังไม่มีข้อมูลสำหรับ Dashboard ของพอร์ต '{active_portfolio_for_dash}'")
        else:
            with tabs_main_dash: # 📊 Dashboard
                if not profit_col_for_dash:
                    st.warning("SEC 5: ไม่พบคอลัมน์ 'Profit' หรือ 'Risk $' ที่มีข้อมูลสำหรับสร้างกราฟ")
                else:
                    df_tab_data_sec5 = df_data_for_dash.copy()
                    if asset_col_for_dash:
                        unique_assets_sec5 = ["ทั้งหมด"] + sorted(df_tab_data_sec5[asset_col_for_dash].dropna().unique())
                        selected_asset_sec5 = st.selectbox(
                            f"Filter by {asset_col_for_dash}", unique_assets_sec5, key="dash_asset_filter_sec5"
                        )
                        if selected_asset_sec5 != "ทั้งหมด":
                            df_tab_data_sec5 = df_tab_data_sec5[df_tab_data_sec5[asset_col_for_dash] == selected_asset_sec5]
                    
                    if df_tab_data_sec5.empty:
                        st.info("ไม่มีข้อมูลหลังจากใช้ Filter ใน Dashboard")
                    else:
                        st.markdown("### 🥧 Pie Chart: Win/Loss")
                        win_count_sec5 = df_tab_data_sec5[df_tab_data_sec5[profit_col_for_dash] > 0].shape[0]
                        loss_count_sec5 = df_tab_data_sec5[df_tab_data_sec5[profit_col_for_dash] <= 0].shape[0]
                        if win_count_sec5 > 0 or loss_count_sec5 > 0:
                            pie_df_sec5 = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count_sec5, loss_count_sec5]})
                            pie_chart_sec5 = px.pie(pie_df_sec5, names="Result", values="Count", color="Result",
                                            color_discrete_map={"Win": "green", "Loss": "red"})
                            st.plotly_chart(pie_chart_sec5, use_container_width=True)
                        else:
                            st.info("ไม่มีข้อมูล Win/Loss สำหรับ Pie Chart (SEC 5).")

                        if date_col_for_dash:
                            st.markdown("### 📊 Bar Chart: กำไร/ขาดทุนแต่ละวัน")
                            df_bar_s5 = df_tab_data_sec5.copy()
                            df_bar_s5["TradeDate"] = df_bar_s5[date_col_for_dash].dt.date # Use .dt.date
                            bar_df_grouped_s5 = df_bar_s5.groupby("TradeDate")[profit_col_for_dash].sum().reset_index(name="Profit/Loss")
                            if not bar_df_grouped_s5.empty:
                                bar_chart_s5 = px.bar(bar_df_grouped_s5, x="TradeDate", y="Profit/Loss", 
                                                   color="Profit/Loss", color_continuous_scale=["red", "lightcoral", "lightgreen", "green"])
                                st.plotly_chart(bar_chart_s5, use_container_width=True)
                            else:
                                st.info("ไม่มีข้อมูลสำหรับ Bar Chart หลัง Group by (SEC 5).")
                        
                            st.markdown("### 📈 Timeline: Balance Curve")
                            df_balance_s5 = df_tab_data_sec5.copy().sort_values(by=date_col_for_dash)
                            # Use initial_balance_for_dash defined at start of SEC 5
                            df_balance_s5["Balance"] = initial_balance_for_dash + df_balance_s5[profit_col_for_dash].cumsum()
                            if not df_balance_s5.empty:
                                timeline_chart_s5 = px.line(df_balance_s5, x=date_col_for_dash, y="Balance", markers=True, title="Balance Curve")
                                st.plotly_chart(timeline_chart_s5, use_container_width=True)
                            else:
                                st.info("ไม่มีข้อมูลสำหรับ Balance Curve (SEC 5).")
                        else:
                            st.warning("ไม่พบคอลัมน์วันที่หลักสำหรับ Bar Chart และ Balance Curve (SEC 5)")
            
            with tabs_rr_dash:
                if "RR" in df_data_for_dash.columns and df_data_for_dash["RR"].notna().any():
                    rr_data_numeric_s5 = df_data_for_dash["RR"].dropna()
                    if not rr_data_numeric_s5.empty:
                        st.markdown("#### RR Histogram")
                        fig_rr_s5 = px.histogram(rr_data_numeric_s5, nbins=20, title="RR Distribution")
                        st.plotly_chart(fig_rr_s5, use_container_width=True)
                    else:
                        st.info("ไม่มีข้อมูล RR ที่ถูกต้องสำหรับ Histogram (SEC 5)")
                else:
                    st.warning("ไม่พบคอลัมน์ 'RR' หรือไม่มีข้อมูล RR (SEC 5)")

            with tabs_lot_dash:
                if "Lot" in df_data_for_dash.columns and date_col_for_dash and df_data_for_dash["Lot"].notna().any():
                    df_lot_s5 = df_data_for_dash.copy().sort_values(by=date_col_for_dash)
                    if not df_lot_s5["Lot"].dropna().empty:
                        st.markdown("#### Lot Size Evolution")
                        fig_lot_s5 = px.line(df_lot_s5.dropna(subset=[date_col_for_dash, "Lot"]), 
                                          x=date_col_for_dash, y="Lot", markers=True, title="Lot Size Over Time")
                        st.plotly_chart(fig_lot_s5, use_container_width=True)
                    else:
                        st.info("ไม่มีข้อมูล Lot หรือ วันที่ ที่ถูกต้องสำหรับกราฟ Lot Size (SEC 5)")
                else:
                    st.warning("ไม่พบคอลัมน์ 'Lot' หรือคอลัมน์วันที่หลักในข้อมูล (SEC 5)")
            
            with tabs_time_dash:
                if date_col_for_dash and profit_col_for_dash:
                    df_time_s5 = df_data_for_dash.copy()
                    df_time_s5["Weekday"] = df_time_s5[date_col_for_dash].dt.day_name()
                    weekday_order_s5 = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    weekday_profit_s5 = df_time_s5.groupby("Weekday")[profit_col_for_dash].sum().reindex(weekday_order_s5).fillna(0).reset_index() #fillna for days with no trades
                    if not weekday_profit_s5.empty:
                        st.markdown("#### Profit/Loss by Weekday")
                        fig_weekday_s5 = px.bar(weekday_profit_s5, x="Weekday", y=profit_col_for_dash, title="Total Profit/Loss by Weekday")
                        st.plotly_chart(fig_weekday_s5, use_container_width=True)
                    else:
                        st.info("ไม่มีข้อมูลสำหรับวิเคราะห์ตามวัน (SEC 5)")
                else:
                    st.warning("ไม่พบคอลัมน์วันที่หลัก หรือ Profit/Risk $ สำหรับวิเคราะห์ตามวัน (SEC 5)")

            with tabs_ai_dash:
                st.subheader("🤖 AI Advisor (Gemini)")
                st.markdown("วิเคราะห์ผลการเทรดและให้คำแนะนำเบื้องต้น (เฉพาะข้อมูลที่แสดงใน Dashboard ปัจจุบัน)")

                if 'google_api_key_sec5' not in st.session_state: # Unique key for this AI instance
                    st.session_state.google_api_key_sec5 = ""
                
                st.session_state.google_api_key_sec5 = st.text_input("ใส่ Google API Key สำหรับ Gemini (SEC 5):", type="password", value=st.session_state.google_api_key_sec5, key="gemini_api_key_input_sec5")

                if st.button("วิเคราะห์โดย AI (SEC 5)", key="ai_analyze_button_sec5"):
                    if not st.session_state.google_api_key_sec5:
                        st.warning("กรุณาใส่ Google API Key ก่อน")
                    elif not profit_col_for_dash or df_data_for_dash.empty: # Use df_data_for_dash (which is filtered for active port)
                        st.warning("ไม่มีข้อมูลเพียงพอสำหรับให้ AI วิเคราะห์ (SEC 5)")
                    else:
                        try:
                            genai.configure(api_key=st.session_state.google_api_key_sec5)
                            model_s5 = genai.GenerativeModel('gemini-pro') # Use a unique model instance name

                            total_trades_ai_s5 = df_data_for_dash.shape[0]
                            win_trades_ai_s5 = df_data_for_dash[df_data_for_dash[profit_col_for_dash] > 0].shape[0]
                            winrate_ai_s5 = (100 * win_trades_ai_s5 / total_trades_ai_s5) if total_trades_ai_s5 > 0 else 0
                            gross_pl_ai_s5 = df_data_for_dash[profit_col_for_dash].sum()
                            avg_rr_ai_s5 = pd.to_numeric(df_data_for_dash.get('RR', pd.Series(dtype='float')), errors='coerce').mean() if 'RR' in df_data_for_dash else 'N/A'
                            
                            prompt_s5 = f"""
                            วิเคราะห์ผลการเทรดจากพอร์ต '{active_portfolio_for_dash}':
                            - จำนวนเทรด: {total_trades_ai_s5}
                            - Winrate: {winrate_ai_s5:.2f}%
                            - กำไร/ขาดทุนสุทธิ: {gross_pl_ai_s5:,.2f} USD
                            - R:R เฉลี่ย: {avg_rr_ai_s5 if isinstance(avg_rr_ai_s5, str) else f"{avg_rr_ai_s5:.2f}"}
                            
                            บอกจุดแข็ง, จุดอ่อน, และให้คำแนะนำเชิงปฏิบัติ 2-3 ข้อเพื่อปรับปรุงการเทรด (ภาษาไทย)
                            """
                            with st.spinner("AI (SEC 5) กำลังวิเคราะห์..."):
                                response_s5 = model_s5.generate_content(prompt_s5)
                                st.markdown("--- \n**AI (SEC 5) Says:**")
                                st.markdown(response_s5.text)
                        except Exception as e_ai_s5:
                            st.error(f"เกิดข้อผิดพลาดในการเรียกใช้ Gemini AI (SEC 5): {e_ai_s5}")
                            st.info("โปรดตรวจสอบ API Key, อินเทอร์เน็ต, และโควต้า Gemini API")

            with tabs_export_dash:
                st.markdown("### Export/Download Dashboard Data")
                if not df_data_for_dash.empty:
                    csv_export_s5 = df_data_for_dash.to_csv(index=False).encode('utf-8')
                    filename_s5 = f"dashboard_report_{active_portfolio_for_dash.replace(' ','_') if active_portfolio_for_dash else 'data'}.csv"
                    st.download_button(
                        "Download Data (CSV)", csv_export_s5, filename_s5, "text/csv",
                        key="dash_export_csv_button_sec5"
                    )
                else:
                    st.info("ไม่มีข้อมูลสำหรับ Export (SEC 5)")
st.markdown("---")

# ======================= SEC 6: MAIN AREA - TRADE LOG VIEWER =======================
# (This was SEC 6 in your old structure)
with st.expander("📚 Trade Log Viewer (แผนเทรดที่บันทึกไว้)", expanded=False):
    if not st.session_state.active_portfolio_name:
        st.warning("กรุณาเลือก 'Active Portfolio' ใน Sidebar เพื่อดู Log")
    else:
        st.subheader(f"Log สำหรับพอร์ต: {st.session_state.active_portfolio_name}")
        if os.path.exists(log_file):
            try:
                df_log_all_s6 = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all_s6.columns:
                    st.warning("Log file ไม่มีคอลัมน์ 'Portfolio'. ไม่สามารถกรองตามพอร์ตที่เลือก.")
                    df_show_s6 = df_log_all_s6.copy() # Show all if no portfolio column
                else:
                    df_show_s6 = df_log_all_s6[df_log_all_s6["Portfolio"] == st.session_state.active_portfolio_name].copy()

                if df_show_s6.empty:
                    st.info(f"ไม่พบ Log สำหรับพอร์ต '{st.session_state.active_portfolio_name}'.")
                else:
                    # Filters for the log viewer
                    col1_s6, col2_s6, col3_s6 = st.columns(3)
                    with col1_s6:
                        mode_filter_s6 = st.selectbox("Mode", ["ทั้งหมด"] + sorted(df_show_s6["Mode"].unique().tolist()), key="log_mode_filter_s6")
                    with col2_s6:
                        asset_filter_s6 = st.selectbox("Asset", ["ทั้งหมด"] + sorted(df_show_s6["Asset"].unique().tolist()), key="log_asset_filter_s6")
                    with col3_s6:
                        date_filter_s6 = st.text_input("ค้นหาวันที่ (YYYY-MM-DD)", value="", key="log_date_filter_s6")
                    
                    df_filtered_s6 = df_show_s6.copy()
                    if mode_filter_s6 != "ทั้งหมด":
                        df_filtered_s6 = df_filtered_s6[df_filtered_s6["Mode"] == mode_filter_s6]
                    if asset_filter_s6 != "ทั้งหมด":
                        df_filtered_s6 = df_filtered_s6[df_filtered_s6["Asset"] == asset_filter_s6]
                    if date_filter_s6:
                        df_filtered_s6 = df_filtered_s6[df_filtered_s6["Timestamp"].str.contains(date_filter_s6, na=False)]
                    
                    st.dataframe(df_filtered_s6, use_container_width=True, hide_index=True)
            except Exception as e_log_view:
                st.error(f"อ่าน Log ไม่ได้ (SEC 6): {e_log_view}")
        else:
            st.info(f"ยังไม่มี Log File ({log_file}) สำหรับแสดงผล")
st.markdown("---")

# ======================= END OF MAIN APP STRUCTURE =======================
st.caption("Ultimate Trading Dashboard - End of Application")
