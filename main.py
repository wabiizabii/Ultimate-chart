# ======================= main.py (เริ่ม SEC 0 - อ้างอิง Master Version จาก Drive) =======================
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl # สำหรับ engine='openpyxl'
import os
from datetime import datetime, timedelta
import plotly.express as px
import google.generativeai as genai # สำหรับ AI Advisor (ถ้าใช้)
# import gspread # เปิดใช้งานเมื่อต้องการเชื่อมต่อ Google Sheets

# ======================= SEC 0: INITIAL SETUP & ALL FUNCTION DEFINITIONS =======================

# 0.1. Page Config
st.set_page_config(
    page_title="Ultimate Trading Dashboard", # หรือชื่อที่คุณต้องการจากไฟล์เดิม
    page_icon="📊", # หรือไอคอนที่คุณต้องการจากไฟล์เดิม
    layout="wide"
)

# 0.2. Initial Variables & File Paths
# acc_balance จะถูกกำหนดค่าแบบไดนามิกจากพอร์ตที่เลือกใน SEC 1
# หากคุณมีค่า default acc_balance ในไฟล์เดิม สามารถนำมาใส่ตรงนี้ได้
# default_initial_balance = 10000.0 
log_file = "trade_log.csv"
PORTFOLIO_FILE = 'portfolios.csv' # สำหรับระบบจัดการพอร์ตใหม่

# ชื่อ Google Sheet และ Worksheet (จากโค้ดเดิมของคุณ - ถ้าจะใช้ ให้เปิด comment)
# GOOGLE_SHEET_NAME = "TradeLog" 
# GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# 0.3. Google API Key Placeholder (ผู้ใช้จะกรอกผ่าน UI หรือ st.secrets)
# (ถ้าคุณมี GOOGLE_API_KEY ใน st.secrets จากโค้ดเดิม ก็สามารถโหลดมาใช้ได้)
# if "google_api" in st.secrets and "GOOGLE_API_KEY" in st.secrets.google_api:
#     try:
#         genai.configure(api_key=st.secrets.google_api.GOOGLE_API_KEY)
#     except Exception as e_genai_config:
#         st.error(f"SEC 0.3: Error configuring Gemini AI: {e_genai_config}")
# else:
#     # st.warning("ไม่พบ Google API Key ใน secrets.toml สำหรับ Gemini AI")
#     pass


# 0.4. ALL FUNCTION DEFINITIONS

# 0.4.1. Portfolio Functions
def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            df = pd.read_csv(PORTFOLIO_FILE)
            required_cols = {'portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'}
            if not required_cols.issubset(df.columns):
                # st.warning(f"ไฟล์ {PORTFOLIO_FILE} มีโครงสร้างไม่ถูกต้อง กำลังสร้าง DataFrame ใหม่")
                return pd.DataFrame(columns=list(required_cols))
            df['initial_balance'] = pd.to_numeric(df['initial_balance'], errors='coerce').fillna(0.0)
            return df
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
        except Exception as e:
            st.error(f"SEC 0.4.1: เกิดข้อผิดพลาดในการโหลด {PORTFOLIO_FILE}: {e}")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
    else:
        return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])

def save_portfolios(df_to_save):
    try:
        df_to_save.to_csv(PORTFOLIO_FILE, index=False)
    except Exception as e:
        st.error(f"SEC 0.4.1: เกิดข้อผิดพลาดในการบันทึก {PORTFOLIO_FILE}: {e}")

# 0.4.2. Utility Functions (Drawdown & Performance for Active Portfolio)
def get_today_drawdown(log_file_path, acc_balance_arg, active_portfolio=None): # acc_balance_arg ไม่ได้ใช้ใน logic ปัจจุบัน แต่อาจมีไว้สำหรับอนาคต
    if not os.path.exists(log_file_path): return 0.0
    try:
        df = pd.read_csv(log_file_path)
        if active_portfolio and "Portfolio" in df.columns:
            df = df[df["Portfolio"] == active_portfolio]
        elif "Portfolio" not in df.columns and active_portfolio: # Log มี แต่ไม่มีคอลัมน์ Portfolio
             pass # หรือจะ return 0.0 ถ้าต้องการให้กรองเสมอ
        
        if df.empty: return 0.0
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0.0
        
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0.0)
        df_today = df[df["Timestamp"].str.startswith(today_str)]
        return df_today["Risk $"].sum()
    except FileNotFoundError: return 0.0
    except Exception as e:
        # st.error(f"SEC 0.4.2: Error in get_today_drawdown: {e}") # Comment out for cleaner UI
        return 0.0

def get_performance(log_file_path, active_portfolio=None, mode="week"): 
    if not os.path.exists(log_file_path): return 0.0, 0.0, 0
    try:
        df = pd.read_csv(log_file_path)
        if active_portfolio and "Portfolio" in df.columns:
            df = df[df["Portfolio"] == active_portfolio]
        elif "Portfolio" not in df.columns and active_portfolio:
            pass

        if df.empty: return 0.0,0.0,0

        if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0.0, 0.0, 0
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0.0)
            
        now = datetime.now()
        if mode == "week":
            start_date_str = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        else: # month
            start_date_str = now.strftime("%Y-%m-01")
        
        df_period = df[df["Timestamp"] >= start_date_str]
        if df_period.empty: return 0.0,0.0,0

        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0]
        total_trades_period = win + loss
        
        winrate = (100 * win / total_trades_period) if total_trades_period > 0 else 0.0
        gain_or_loss = df_period["Risk $"].sum() 
        return winrate, gain_or_loss, total_trades_period
    except FileNotFoundError: return 0.0,0.0,0
    except Exception as e:
        # st.error(f"SEC 0.4.2: Error in get_performance: {e}") # Comment out for cleaner UI
        return 0.0,0.0,0

# 0.4.3. Save Plan Function
def save_plan_to_log(data_to_save, trade_mode_arg, asset_arg, risk_pct_arg, direction_arg, active_portfolio_arg):
    if not active_portfolio_arg:
        st.sidebar.error("ไม่สามารถบันทึกแผน: กรุณาเลือกหรือสร้างพอร์ตก่อน")
        return
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not isinstance(data_to_save, list) or not all(isinstance(item, dict) for item in data_to_save):
        st.sidebar.error("ข้อมูลสำหรับบันทึก Log ไม่ถูกต้อง (ต้องเป็น list of dictionaries)")
        return

    df_to_write = pd.DataFrame(data_to_save)
    # Ensure all expected columns exist to prevent issues during concat or save
    expected_cols = ["Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"] 
    for col in expected_cols:
        if col not in df_to_write.columns: df_to_write[col] = np.nan

    df_to_write["Mode"] = trade_mode_arg
    df_to_write["Asset"] = asset_arg
    df_to_write["Risk %"] = risk_pct_arg
    df_to_write["Direction"] = direction_arg
    df_to_write["Portfolio"] = active_portfolio_arg
    df_to_write["Timestamp"] = now_str
    
    try:
        if os.path.exists(log_file):
            df_old_log = pd.read_csv(log_file)
            # Align columns for robust concatenation
            common_cols = list(set(df_old_log.columns) & set(df_to_write.columns)) # Use common columns
            all_cols = list(df_old_log.columns.union(df_to_write.columns, sort=False)) # All unique columns in order of first appearance

            df_old_log_aligned = df_old_log.reindex(columns=all_cols)
            df_to_write_aligned = df_to_write.reindex(columns=all_cols)

            df_final_log = pd.concat([df_old_log_aligned, df_to_write_aligned], ignore_index=True)
        else:
            df_final_log = df_to_write
        df_final_log.to_csv(log_file, index=False)
        st.sidebar.success(f"บันทึกแผน ({trade_mode_arg}) สำหรับพอร์ต '{active_portfolio_arg}' สำเร็จ!")
    except Exception as e:
        st.sidebar.error(f"SEC 0.4.3: Save Plan ไม่สำเร็จ: {e}")

# 0.4.4. Statement Extraction Function (ชื่อเดิม extract_data_from_report)
def extract_data_from_statement(file_buffer, stat_definitions_arg):
    df_raw = None
    try:
        file_buffer.seek(0)
        if file_buffer.name.endswith('.csv'):
            df_raw = pd.read_csv(file_buffer, header=None, low_memory=False)
        elif file_buffer.name.endswith('.xlsx'):
            df_raw = pd.read_excel(file_buffer, header=None, engine='openpyxl')
    except Exception as e_read:
        st.error(f"Statement Import: เกิดข้อผิดพลาดในการอ่านไฟล์: {e_read}"); return None
    if df_raw is None or df_raw.empty: st.warning("Statement Import: ไม่สามารถอ่านข้อมูลจากไฟล์ได้ หรือไฟล์ว่างเปล่า"); return None

    section_starts = {}
    section_keywords = ["Positions", "Orders", "Deals", "History", "Results"]
    for keyword in section_keywords:
        if keyword not in section_starts:
            for r_idx, row in df_raw.iterrows():
                if row.astype(str).str.contains(keyword, case=False, regex=False).any():
                    actual_key = "Deals" if keyword == "History" else keyword
                    if actual_key not in section_starts: section_starts[actual_key] = r_idx
                    break
    
    extracted_data = {}
    sorted_sections = sorted(section_starts.items(), key=lambda item: item[1])
    tabular_keywords = ["Positions", "Orders", "Deals"]
    for i, (section_name, start_row) in enumerate(sorted_sections):
        if section_name not in tabular_keywords: continue
        header_row_idx = start_row + 1
        while header_row_idx < len(df_raw) and df_raw.iloc[header_row_idx].isnull().all(): header_row_idx += 1
        if header_row_idx < len(df_raw):
            headers = [str(h).strip() for h in df_raw.iloc[header_row_idx] if pd.notna(h) and str(h).strip() != '']
            data_start_row = header_row_idx + 1
            end_row = len(df_raw)
            if i + 1 < len(sorted_sections): end_row = sorted_sections[i+1][1]
            df_section = df_raw.iloc[data_start_row:end_row].copy().dropna(how='all')
            if not df_section.empty:
                num_data_cols = df_section.shape[1]
                final_headers = headers[:num_data_cols]
                if len(final_headers) < num_data_cols:
                    final_headers.extend([f'Unnamed_Stmt_{j}' for j in range(len(final_headers), num_data_cols)])
                df_section.columns = final_headers
                
                # Convert known numeric columns, more robustly
                numeric_cols_in_stmt = ['Volume', 'Price', 'S / L', 'T / P', 'Commission', 'Fee', 'Swap', 'Profit', 'Balance']
                for col_stmt_num in numeric_cols_in_stmt:
                    if col_stmt_num in df_section.columns:
                        # Replace non-numeric characters like spaces before attempting conversion
                        if df_section[col_stmt_num].dtype == 'object':
                            df_section[col_stmt_num] = df_section[col_stmt_num].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
                        df_section[col_stmt_num] = pd.to_numeric(df_section[col_stmt_num], errors='coerce') # .fillna(0) might be too aggressive here
                extracted_data[section_name.lower()] = df_section

    if "Results" in section_starts:
        results_stats = {}
        start_row_res = section_starts["Results"]
        results_df_scan = df_raw.iloc[start_row_res : start_row_res + 20] # Increased scan range just in case
        
        for _, row_res_item in results_df_scan.iterrows():
            for c_idx_res_item, cell_res_item in enumerate(row_res_item):
                if pd.notna(cell_res_item):
                    label_res_item = str(cell_res_item).strip().replace(':', '')
                    if label_res_item in stat_definitions_arg:
                        for k_val_offset_item in range(1, 5):
                            if (c_idx_res_item + k_val_offset_item) < len(row_res_item):
                                value_candidate_item = row_res_item.iloc[c_idx_res_item + k_val_offset_item]
                                if pd.notna(value_candidate_item) and str(value_candidate_item).strip() != "":
                                    clean_value_item = str(value_candidate_item).split('(')[0].strip().replace(' ', '').replace(',', '')
                                    results_stats[label_res_item] = clean_value_item
                                    break 
                        # Allow finding multiple stats on the same row if needed
        if results_stats:
            df_balance_summary_ext = pd.DataFrame(list(results_stats.items()), columns=['Metric', 'Value'])
            # Convert 'Value' column to numeric, handling potential errors for mixed types (e.g. "10 (50%)")
            # For values like "123.45 (xxx)", it takes "123.45"
            df_balance_summary_ext['Value'] = df_balance_summary_ext['Value'].astype(str).str.split(' ').str[0].str.replace(r'[^\d\.\-]', '', regex=True)
            df_balance_summary_ext['Value'] = pd.to_numeric(df_balance_summary_ext['Value'], errors='coerce').fillna(df_balance_summary_ext['Value']) # Keep original if conversion fails
            extracted_data["balance_summary"] = df_balance_summary_ext
    return extracted_data

# 0.4.5. Dashboard Data Loading Function (ปรับปรุงจากโค้ดเดิม)
def load_data_for_dashboard(active_portfolio_arg, current_portfolio_initial_balance):
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Log File (แผนเทรด)", "Statement Import (ผลเทรดจริง)"],
        index=0, 
        key="main_dashboard_source_selector_key_v2" # Ensure unique key
    )
    df_dashboard = pd.DataFrame()
    profit_col_identified, asset_col_identified, date_col_identified = None, None, None

    if source_option == "Log File (แผนเทรด)":
        if not active_portfolio_arg:
            st.warning("Dashboard: กรุณาเลือก Active Portfolio")
            return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
        if os.path.exists(log_file):
            try:
                df_log_all_dash = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all_dash.columns:
                    st.warning("Dashboard: Log file ไม่มีคอลัมน์ 'Portfolio'")
                    return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
                df_dashboard = df_log_all_dash[df_log_all_dash["Portfolio"] == active_portfolio_arg].copy()
                if df_dashboard.empty:
                    st.info(f"Dashboard: ไม่พบข้อมูล Log File สำหรับพอร์ต '{active_portfolio_arg}'")
            except Exception as e_log_dash_load:
                st.error(f"Dashboard: ไม่สามารถโหลด Log File: {e_log_dash_load}")
        else:
            st.info(f"Dashboard: ไม่พบ Log File ({log_file})")
    
    else: # Statement Import (ผลเทรดจริง)
        if not active_portfolio_arg:
            st.warning("Dashboard: กรุณาเลือก Active Portfolio")
            return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
        
        df_from_session_dash = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame())
        if not df_from_session_dash.empty:
            df_dashboard = df_from_session_dash.copy()
            if 'Portfolio' in df_dashboard.columns: 
                df_dashboard = df_dashboard[df_dashboard['Portfolio'] == active_portfolio_arg]
        
        if df_dashboard.empty:
             st.info(f"Dashboard: ไม่มีข้อมูล Statement สำหรับพอร์ต '{active_portfolio_arg}' (โปรดอัปโหลดในส่วน Statement Import)")

    # Data Cleaning and Column Identification for Dashboard
    if not df_dashboard.empty:
        # Identify and Clean Profit column
        if 'Profit' in df_dashboard.columns:
            # Attempt to clean and convert 'Profit' column
            # Handle cases where 'Profit' might contain non-numeric strings after initial parsing
            if df_dashboard['Profit'].dtype == 'object':
                 df_dashboard['Profit'] = df_dashboard['Profit'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
            df_dashboard['Profit_temp_dash'] = pd.to_numeric(df_dashboard['Profit'], errors='coerce')
            
            if df_dashboard['Profit_temp_dash'].notna().any() and df_dashboard['Profit_temp_dash'].abs().sum() > 0:
                 df_dashboard['Profit'] = df_dashboard['Profit_temp_dash'].fillna(0.0)
                 profit_col_identified = 'Profit'
            elif 'Risk $' in df_dashboard.columns: # Fallback if Profit is all NaN/zero after conversion
                 if df_dashboard['Risk $'].dtype == 'object':
                    df_dashboard['Risk $'] = df_dashboard['Risk $'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
                 df_dashboard['Risk $'] = pd.to_numeric(df_dashboard['Risk $'], errors='coerce').fillna(0.0)
                 profit_col_identified = 'Risk $'
            df_dashboard.drop(columns=['Profit_temp_dash'], inplace=True, errors='ignore')

        elif 'Risk $' in df_dashboard.columns: # If 'Profit' col doesn't exist at all
            if df_dashboard['Risk $'].dtype == 'object':
                df_dashboard['Risk $'] = df_dashboard['Risk $'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
            df_dashboard['Risk $'] = pd.to_numeric(df_dashboard['Risk $'], errors='coerce').fillna(0.0)
            profit_col_identified = 'Risk $'
        
        # Clean other potential numeric columns
        numeric_cols_to_clean_dash = ['RR', 'Lot', 'Commission', 'Swap', 'Volume', 'Price', 'S / L', 'T / P']
        for col_num_clean_dash in numeric_cols_to_clean_dash:
            if col_num_clean_dash in df_dashboard.columns:
                if df_dashboard[col_num_clean_dash].dtype == 'object':
                    df_dashboard[col_num_clean_dash] = df_dashboard[col_num_clean_dash].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
                df_dashboard[col_num_clean_dash] = pd.to_numeric(df_dashboard[col_num_clean_dash], errors='coerce').fillna(0.0)

        # Identify Asset column
        if 'Asset' in df_dashboard.columns: asset_col_identified = 'Asset'
        elif 'Symbol' in df_dashboard.columns: asset_col_identified = 'Symbol'

        # Identify and convert Date column
        date_col_options_dash = [col for col in ["Timestamp", "Time", "Date", "Open Time", "Close Time"] if col in df_dashboard.columns]
        for col_date_dash in date_col_options_dash:
            try:
                # Ensure the column is not all NaT before attempting conversion if it's already datetime
                if pd.api.types.is_datetime64_any_dtype(df_dashboard[col_date_dash]) and df_dashboard[col_date_dash].notna().all():
                    date_col_identified = col_date_dash
                    break
                elif not pd.api.types.is_datetime64_any_dtype(df_dashboard[col_date_dash]):
                    df_dashboard[col_date_dash] = pd.to_datetime(df_dashboard[col_date_dash], errors='coerce')
                
                if df_dashboard[col_date_dash].notna().any():
                    date_col_identified = col_date_dash
                    break
            except Exception: continue # Try next date column option
            
    return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified

# 0.4.6. Google Sheets Functions (จากไฟล์ต้นฉบับของคุณ - ปิด comment ไว้ก่อน ถ้าต้องการใช้)
# def get_gspread_client():
#     # ... (โค้ดเดิมของคุณจากไฟล์ Master) ...
#     return None 

# @st.cache_data(ttl=3600) 
# def load_statement_from_gsheets(): # ฟังก์ชันนี้อาจจะซ้ำซ้อนกับ extract_data_from_statement ถ้าใช้ไฟล์อัปโหลดเป็นหลัก
#     # ... (โค้ดเดิมของคุณจากไฟล์ Master) ...
#     return {} 

# def save_statement_to_gsheets(df_to_save):
#     # ... (โค้ดเดิมของคุณจากไฟล์ Master) ...
#     pass

# ======================= END OF SEC 0 =======================
