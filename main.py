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
