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

# ======================= SEC 1: SIDEBAR - CORE CONTROLS, PORTFOLIO, INPUTS, RISK MGMT =======================

# --- 1.1. Portfolio Selection & Management UI ---
portfolios_df = load_portfolios() # ฟังก์ชันนี้ถูก define ใน SEC 0
acc_balance = 10000.0 # Default balance, จะถูกอัปเดตตามพอร์ตที่เลือก

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน") # UI: ไม่มีเลขนำหน้า

if not portfolios_df.empty:
    portfolio_names_list_sec1 = portfolios_df['portfolio_name'].tolist()
    
    current_active_portfolio_name_sb_sec1 = st.session_state.get('active_portfolio_name', None)
    
    # ตั้งค่า default ถ้า active_portfolio_name ยังไม่ได้ตั้ง หรือ ไม่มีอยู่ใน list ปัจจุบัน
    if current_active_portfolio_name_sb_sec1 not in portfolio_names_list_sec1:
        st.session_state.active_portfolio_name = portfolio_names_list_sec1[0] if portfolio_names_list_sec1 else None
        # อัปเดต acc_balance ตามพอร์ต default ใหม่ (ถ้ามี)
        if st.session_state.active_portfolio_name:
            active_details_default = portfolios_df[portfolios_df['portfolio_name'] == st.session_state.active_portfolio_name]
            if not active_details_default.empty:
                acc_balance = float(active_details_default['initial_balance'].iloc[0])
    
    # หา index ของพอร์ตที่เลือกปัจจุบัน (หรือ default)
    try:
        if st.session_state.active_portfolio_name and st.session_state.active_portfolio_name in portfolio_names_list_sec1:
            current_index_sb_sec1 = portfolio_names_list_sec1.index(st.session_state.active_portfolio_name)
        elif portfolio_names_list_sec1: 
            current_index_sb_sec1 = 0 # Default to first item
            st.session_state.active_portfolio_name = portfolio_names_list_sec1[0] # Set if was None and list exists
        else: 
            current_index_sb_sec1 = 0 # Should not happen if list is not empty
    except ValueError: # Should not happen if logic above is correct
        current_index_sb_sec1 = 0 
        if portfolio_names_list_sec1:
             st.session_state.active_portfolio_name = portfolio_names_list_sec1[0]

    selected_portfolio_name_sb_sec1 = st.sidebar.selectbox(
        "เลือกพอร์ต:",
        options=portfolio_names_list_sec1,
        index=current_index_sb_sec1,
        key='sidebar_portfolio_selector_widget_key' 
    )
    
    if selected_portfolio_name_sb_sec1 != st.session_state.get('active_portfolio_name'):
        st.session_state.active_portfolio_name = selected_portfolio_name_sb_sec1
        # เมื่อมีการเปลี่ยนพอร์ต ให้ Rerun เพื่ออัปเดต acc_balance และส่วนอื่นๆ ที่เกี่ยวข้อง
        st.rerun() 

    if st.session_state.active_portfolio_name:
        active_portfolio_details_sb_sec1 = portfolios_df[portfolios_df['portfolio_name'] == st.session_state.active_portfolio_name]
        if not active_portfolio_details_sb_sec1.empty:
            acc_balance = float(active_portfolio_details_sb_sec1['initial_balance'].iloc[0])
            st.sidebar.success(f"Active: **{st.session_state.active_portfolio_name}** (Bal: ${acc_balance:,.2f})")
        # else: # กรณีไม่เจอรายละเอียดพอร์ต (ซึ่งไม่ควรเกิดถ้า selectbox ถูก populate ถูกต้อง)
            # st.sidebar.error("Error: ไม่พบรายละเอียดพอร์ตที่เลือก")
            # st.session_state.active_portfolio_name = None 
            # acc_balance = 10000.0 # Reset to default
else:
    st.sidebar.info("ยังไม่มีพอร์ต กรุณาเพิ่มพอร์ตด้านล่าง หรือในหน้าจัดการหลัก")
    st.session_state.active_portfolio_name = None
    acc_balance = 10000.0 

# Expander for managing portfolios in Sidebar
with st.sidebar.expander("💼 จัดการพอร์ต", expanded=False): # UI: ไม่มีเลขนำหน้า
    # portfolios_df_display_sidebar = load_portfolios() # โหลดล่าสุดเสมอเมื่อเปิด expander
    st.dataframe(portfolios_df, use_container_width=True, hide_index=True, 
                 column_config={"portfolio_id": "ID", "portfolio_name": "ชื่อพอร์ต", 
                                "initial_balance": st.column_config.NumberColumn("บาลานซ์ ($)", format="$%.2f"),
                                "creation_date": "วันที่สร้าง"})

    with st.form("sidebar_new_portfolio_form_key", clear_on_submit=True): # Unique key
        st.subheader("➕ เพิ่มพอร์ตใหม่") # UI: ไม่มีเลขนำหน้า
        new_p_name_sidebar_form = st.text_input("ชื่อพอร์ต")
        new_p_bal_sidebar_form = st.number_input("บาลานซ์เริ่มต้น ($)", min_value=0.0, value=10000.0, step=100.0, format="%.2f")
        
        if st.form_submit_button("💾 บันทึกพอร์ตใหม่"):
            # โหลดข้อมูลล่าสุดก่อนตรวจสอบและเพิ่ม
            current_portfolios_df_in_form = load_portfolios()
            if not new_p_name_sidebar_form:
                st.warning("กรุณาใส่ชื่อพอร์ต")
            elif new_p_name_sidebar_form in current_portfolios_df_in_form['portfolio_name'].values:
                st.error(f"ชื่อพอร์ต '{new_p_name_sidebar_form}' มีอยู่แล้ว")
            else:
                if current_portfolios_df_in_form.empty or 'portfolio_id' not in current_portfolios_df_in_form.columns or current_portfolios_df_in_form['portfolio_id'].isnull().all():
                    new_id_sidebar_form = 1
                else:
                    new_id_sidebar_form = current_portfolios_df_in_form['portfolio_id'].max() + 1 if pd.notna(current_portfolios_df_in_form['portfolio_id'].max()) else 1
                
                new_p_data_sidebar_form = pd.DataFrame([{'portfolio_id': int(new_id_sidebar_form), 
                                                       'portfolio_name': new_p_name_sidebar_form, 
                                                       'initial_balance': new_p_bal_sidebar_form, 
                                                       'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                
                updated_portfolios_df_form = pd.concat([current_portfolios_df_in_form, new_p_data_sidebar_form], ignore_index=True)
                save_portfolios(updated_portfolios_df_form)
                st.success(f"เพิ่มพอร์ต '{new_p_name_sidebar_form}' สำเร็จ!")
                # อัปเดต active_portfolio_name เป็นพอร์ตที่เพิ่งสร้าง ถ้ายังไม่มีการเลือก หรือเป็นพอร์ตแรก
                if st.session_state.active_portfolio_name is None and not updated_portfolios_df_form.empty:
                    st.session_state.active_portfolio_name = new_p_name_sidebar_form
                st.rerun()
st.sidebar.markdown("---")

# --- 1.2. Main Trade Setup ---
st.sidebar.header("Trade Setup & Controls") # UI: ไม่มีเลขนำหน้า
# ใช้ session state เพื่อเก็บค่า config ที่ผู้ใช้ตั้งไว้
if 'sidebar_dd_limit_pct_val' not in st.session_state: st.session_state.sidebar_dd_limit_pct_val = 2.0
drawdown_limit_pct_input = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)", 
    min_value=0.1, max_value=20.0, 
    value=st.session_state.sidebar_dd_limit_pct_val, 
    step=0.1, format="%.1f", 
    key="widget_sidebar_dd_limit" 
)
st.session_state.sidebar_dd_limit_pct_val = drawdown_limit_pct_input # อัปเดตค่าใน session_state

if 'sidebar_current_trade_mode_val' not in st.session_state: st.session_state.sidebar_current_trade_mode_val = "FIBO"
current_trade_mode = st.sidebar.radio(
    "Trade Mode", ["FIBO", "CUSTOM"], 
    index=["FIBO", "CUSTOM"].index(st.session_state.sidebar_current_trade_mode_val),
    horizontal=True, key="widget_sidebar_trade_mode"
)
st.session_state.sidebar_current_trade_mode_val = current_trade_mode

if st.sidebar.button("🔄 Reset Form", key="widget_sidebar_reset_form"):
    keys_to_preserve = {
        'active_portfolio_name', 'sidebar_portfolio_selector_widget_key', 
        'sidebar_dd_limit_pct_val', 'widget_sidebar_dd_limit',
        'sidebar_current_trade_mode_val', 'widget_sidebar_trade_mode'
    }
    # Preserve scaling config keys
    for k_scale in ['widget_scaling_step', 'widget_scaling_min_risk', 'widget_scaling_max_risk', 'widget_scaling_mode_radio']:
        if k_scale in st.session_state: keys_to_preserve.add(st.session_state[k_scale]) # Store value if exists

    for key_in_ss in list(st.session_state.keys()):
        if key_in_ss not in keys_to_preserve:
            # More specific clearing for FIBO/CUSTOM inputs based on typical key patterns
            if key_in_ss.startswith('fibo_') or key_in_ss.startswith('custom_') or key_in_ss.startswith('widget_fibo_') or key_in_ss.startswith('widget_custom_'):
                del st.session_state[key_in_ss]
    
    # Explicitly reset Fibo flags if they use a specific key pattern
    if "fibo_flags_list_config" in st.session_state: 
        st.session_state.fibo_flags_list_config = [True] * 5
    st.rerun()

# --- 1.3. FIBO Input Zone ---
entry_data_fibo_list = [] # Initialize for this run, will be populated if mode is FIBO
if current_trade_mode == "FIBO":
    st.sidebar.subheader("FIBO Mode Inputs") # UI: ไม่มีเลขนำหน้า
    
    # Initialize session state for FIBO inputs if they don't exist, and assign to local variables
    fibo_asset = st.session_state.fibo_asset_val = st.sidebar.text_input("Asset", value=st.session_state.get("fibo_asset_val", "XAUUSD"), key="widget_fibo_asset")
    fibo_risk_pct = st.session_state.fibo_risk_val = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("fibo_risk_val", 1.0), step=0.01, key="widget_fibo_risk")
    fibo_direction = st.session_state.fibo_direction_val = st.sidebar.radio("Direction", ["Long", "Short"], index=["Long", "Short"].index(st.session_state.get("fibo_direction_val", "Long")), horizontal=True, key="widget_fibo_direction")
    
    col_fibo_hl1, col_fibo_hl2 = st.sidebar.columns(2)
    fibo_swing_high = st.session_state.fibo_high_val = col_fibo_hl1.text_input("High", value=st.session_state.get("fibo_high_val", ""), key="widget_fibo_high")
    fibo_swing_low = st.session_state.fibo_low_val = col_fibo_hl2.text_input("Low", value=st.session_state.get("fibo_low_val", ""), key="widget_fibo_low")
    
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibo_levels_list = [0.114, 0.25, 0.382, 0.5, 0.618] 
    if "fibo_flags_list_config" not in st.session_state: 
        st.session_state.fibo_flags_list_config = [True] * len(fibo_levels_list)
    
    cols_fibo_checkboxes_list = st.sidebar.columns(len(fibo_levels_list))
    current_fibo_flags = st.session_state.fibo_flags_list_config[:] 
    for i, col_cb_fibo_item_list in enumerate(cols_fibo_checkboxes_list): 
        current_fibo_flags[i] = col_cb_fibo_item_list.checkbox(
            f"{fibo_levels_list[i]:.3f}", 
            value=current_fibo_flags[i], 
            key=f"widget_fibo_level_cb_{i}"
        )
    st.session_state.fibo_flags_list_config = current_fibo_flags
    
    try:
        high_f_calc = float(fibo_swing_high)
        low_f_calc = float(fibo_swing_low)
        if high_f_calc > low_f_calc and acc_balance > 0:
            selected_fibs_f_calc = [fibo_levels_list[i] for i, sel_f_calc in enumerate(st.session_state.fibo_flags_list_config) if sel_f_calc]
            n_selected_f_calc = len(selected_fibs_f_calc)
            risk_dollar_total_f_calc = acc_balance * (fibo_risk_pct / 100)
            risk_dollar_per_entry_f_calc = risk_dollar_total_f_calc / n_selected_f_calc if n_selected_f_calc > 0 else 0.0
            
            for fib_level_f_calc in selected_fibs_f_calc:
                entry_p_f_calc = low_f_calc + (high_f_calc - low_f_calc) * fib_level_f_calc if fibo_direction == "Long" else high_f_calc - (high_f_calc - low_f_calc) * fib_level_f_calc
                sl_p_f_calc = low_f_calc if fibo_direction == "Long" else high_f_calc
                stop_p_f_calc = abs(entry_p_f_calc - sl_p_f_calc)
                lot_f_calc = (risk_dollar_per_entry_f_calc / stop_p_f_calc) if stop_p_f_calc > 0 else 0.0
                entry_data_fibo_list.append({
                    "Fibo Level": f"{fib_level_f_calc:.3f}", "Entry": f"{entry_p_f_calc:.2f}", "SL": f"{sl_p_f_calc:.2f}",
                    "Lot": f"{lot_f_calc:.2f}", "Risk $": f"{lot_f_calc * stop_p_f_calc:.2f}"
                })
    except (ValueError, TypeError, ZeroDivisionError): pass 
    
    save_fibo_button = st.sidebar.button("💾 Save Plan (FIBO)", key="widget_sidebar_btn_save_fibo")

# --- 1.4. CUSTOM Input Zone ---
custom_entries_list = [] 
if current_trade_mode == "CUSTOM":
    st.sidebar.subheader("CUSTOM Mode Inputs") # UI: ไม่มีหมายเลข
    col1_cust_main, col2_cust_main = st.sidebar.columns(2)
    with col1_cust_main:
        custom_asset = st.session_state.custom_asset_val = st.sidebar.text_input("Asset", value=st.session_state.get("custom_asset_val", "XAUUSD"), key="widget_custom_asset")
    with col2_cust_main:
        custom_risk_pct = st.session_state.custom_risk_val = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("custom_risk_val", 1.0), step=0.01, key="widget_custom_risk")
    
    custom_n_entry = st.session_state.custom_n_entry_val = st.sidebar.number_input("จำนวนไม้", min_value=1, value=st.session_state.get("custom_n_entry_val", 1), step=1, key="widget_custom_n_entry")
    
    num_entries_cust_calc = int(custom_n_entry)

    for i_cust_loop in range(num_entries_cust_calc):
        st.sidebar.markdown(f"--- ไม้ที่ {i_cust_loop+1} ---")
        # Initialize session state for each custom entry field inside the loop or ensure keys are unique
        e_key = f"widget_custom_entry_{i_cust_loop}"
        s_key = f"widget_custom_sl_{i_cust_loop}"
        t_key = f"widget_custom_tp_{i_cust_loop}"
        
        st.session_state[e_key] = st.sidebar.text_input(f"Entry {i_cust_loop+1}", value=st.session_state.get(e_key, "0.0"), key=e_key)
        st.session_state[s_key] = st.sidebar.text_input(f"SL {i_cust_loop+1}", value=st.session_state.get(s_key, "0.0"), key=s_key)
        st.session_state[t_key] = st.sidebar.text_input(f"TP {i_cust_loop+1}", value=st.session_state.get(t_key, "0.0"), key=t_key)
        
        try:
            if acc_balance > 0 and num_entries_cust_calc > 0 :
                risk_dollar_total_cust_c = acc_balance * (custom_risk_pct / 100)
                risk_dollar_per_entry_cust_c = risk_dollar_total_cust_c / num_entries_cust_calc
                entry_p_cust_c, sl_p_cust_c, tp_p_cust_c = float(st.session_state[e_key]), float(st.session_state[s_key]), float(st.session_state[t_key])
                stop_p_cust_c = abs(entry_p_cust_c - sl_p_cust_c)
                lot_cust_c = (risk_dollar_per_entry_cust_c / stop_p_cust_c) if stop_p_cust_c > 0 else 0.0
                rr_cust_c = abs(tp_p_cust_c - entry_p_cust_c) / stop_p_cust_c if stop_p_cust_c > 0 else 0.0
                custom_entries_list.append({
                    "Entry": f"{entry_p_cust_c:.2f}", "SL": f"{sl_p_cust_c:.2f}", "TP": f"{tp_p_cust_c:.2f}",
                    "Lot": f"{lot_cust_c:.2f}", "Risk $": f"{lot_cust_c * stop_p_cust_c:.2f}", "RR": f"{rr_cust_c:.2f}"
                })
        except (ValueError, TypeError, ZeroDivisionError): pass
    save_custom_button = st.sidebar.button("💾 Save Plan (CUSTOM)", key="widget_sidebar_btn_save_custom")

# --- 1.5. Strategy Summary (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Strategy Summary") # UI: ไม่มีหมายเลข
if current_trade_mode == "FIBO":
    if entry_data_fibo_list:
        df_fibo_summary_sb = pd.DataFrame(entry_data_fibo_list)
        st.sidebar.write(f"Total Lots: {pd.to_numeric(df_fibo_summary_sb['Lot'], errors='coerce').sum():.2f}")
        st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_fibo_summary_sb['Risk $'], errors='coerce').sum():.2f}")
    else: st.sidebar.caption("กรอกข้อมูล FIBO เพื่อดู Summary")
elif current_trade_mode == "CUSTOM":
    if custom_entries_list:
        df_custom_summary_sb = pd.DataFrame(custom_entries_list)
        st.sidebar.write(f"Total Lots: {pd.to_numeric(df_custom_summary_sb['Lot'], errors='coerce').sum():.2f}")
        st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_custom_summary_sb['Risk $'], errors='coerce').sum():.2f}")
        avg_rr_sb = pd.to_numeric(df_custom_summary_sb['RR'], errors='coerce').mean()
        if pd.notna(avg_rr_sb): st.sidebar.write(f"Average RR: {avg_rr_sb:.2f}")
    else: st.sidebar.caption("กรอกข้อมูล CUSTOM เพื่อดู Summary")

# --- 1.6. Scaling Manager (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Scaling Manager") # UI: ไม่มีหมายเลข
# Initialize scaling session state values
default_scaling_config = {"scaling_step_cfg": 0.25, "scaling_min_risk_cfg": 0.5, "scaling_max_risk_cfg": 5.0, "scaling_mode_cfg": "Manual"}
for k_cfg, v_cfg in default_scaling_config.items():
    if k_cfg not in st.session_state: st.session_state[k_cfg] = v_cfg

with st.sidebar.expander("Scaling Settings", expanded=False):
    st.session_state.scaling_step_cfg = st.number_input("Scaling Step (%)", min_value=0.01,max_value=1.0,value=st.session_state.scaling_step_cfg,step=0.01,format="%.2f",key="widget_scaling_step")
    st.session_state.scaling_min_risk_cfg = st.number_input("Minimum Risk %",min_value=0.01,max_value=100.0,value=st.session_state.scaling_min_risk_cfg,step=0.01,format="%.2f",key="widget_scaling_min_risk")
    st.session_state.scaling_max_risk_cfg = st.number_input("Maximum Risk %",min_value=0.01,max_value=100.0,value=st.session_state.scaling_max_risk_cfg,step=0.01,format="%.2f",key="widget_scaling_max_risk")
    st.session_state.scaling_mode_cfg = st.radio("Scaling Mode",["Manual","Auto"],index=["Manual","Auto"].index(st.session_state.scaling_mode_cfg),horizontal=True,key="widget_scaling_mode_radio")

if st.session_state.active_portfolio_name:
    winrate_scaling_val, gain_scaling_val, _ = get_performance(log_file, st.session_state.active_portfolio_name, acc_balance) # Use get_performance
    
    # Determine current risk based on mode from session state
    current_risk_for_scaling_sidebar = 0.0
    if current_trade_mode == "FIBO":
        current_risk_for_scaling_sidebar = st.session_state.get("fibo_risk_val", 1.0) # Default if key not found
    elif current_trade_mode == "CUSTOM":
        current_risk_for_scaling_sidebar = st.session_state.get("custom_risk_val", 1.0) # Default if key not found

    suggest_risk_val_sidebar = current_risk_for_scaling_sidebar
    msg_scale_sidebar = f"Risk% ({st.session_state.active_portfolio_name}) คงที่: {current_risk_for_scaling_sidebar:.2f}%"

    if acc_balance > 0:
        if winrate_scaling_val > 55 and gain_scaling_val > 0.02 * acc_balance:
            suggest_risk_val_sidebar = min(current_risk_for_scaling_sidebar + st.session_state.scaling_step_cfg, st.session_state.scaling_max_risk_cfg)
            msg_scale_sidebar = f"🎉 ผลงานดี! ({st.session_state.active_portfolio_name}) Winrate {winrate_scaling_val:.1f}%, Gain {gain_scaling_val:.2f}. แนะนำเพิ่ม Risk เป็น {suggest_risk_val_sidebar:.2f}%"
        elif winrate_scaling_val < 45 or gain_scaling_val < 0:
            suggest_risk_val_sidebar = max(current_risk_for_scaling_sidebar - st.session_state.scaling_step_cfg, st.session_state.scaling_min_risk_cfg)
            msg_scale_sidebar = f"⚠️ ควรลด Risk! ({st.session_state.active_portfolio_name}) Winrate {winrate_scaling_val:.1f}%, P/L {gain_scaling_val:.2f}. แนะนำลด Risk เป็น {suggest_risk_val_sidebar:.2f}%"
    
    st.sidebar.info(msg_scale_sidebar)
    if st.session_state.scaling_mode_cfg == "Manual" and suggest_risk_val_sidebar != current_risk_for_scaling_sidebar:
        if st.sidebar.button(f"ปรับ Risk เป็น {suggest_risk_val_sidebar:.2f}", key="widget_sidebar_btn_scaling_adjust"):
            if current_trade_mode == "FIBO": st.session_state.fibo_risk_val = suggest_risk_val_sidebar
            else: st.session_state.custom_risk_val = suggest_risk_val_sidebar
            st.rerun()
    elif st.session_state.scaling_mode_cfg == "Auto" and suggest_risk_val_sidebar != current_risk_for_scaling_sidebar:
        if current_trade_mode == "FIBO": st.session_state.fibo_risk_val = suggest_risk_val_sidebar
        else: st.session_state.custom_risk_val = suggest_risk_val_sidebar
        # st.sidebar.caption(f"Risk% ของ {current_trade_mode} ถูกปรับเป็น {suggest_risk_val_sidebar:.2f}% อัตโนมัติ") # Optional feedback
else: st.sidebar.caption("เลือก Active Portfolio เพื่อดูคำแนะนำ Scaling")

# --- 1.7. Drawdown Display & Lock Logic (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader(f"การควบคุมความเสี่ยง ({st.session_state.active_portfolio_name or 'N/A'})") # UI: ไม่มีหมายเลข
drawdown_today_val_sb = 0.0
if st.session_state.active_portfolio_name:
    drawdown_today_val_sb = get_today_drawdown(log_file, acc_balance, st.session_state.active_portfolio_name) # Use get_today_drawdown

drawdown_limit_abs_sb_val = -acc_balance * (drawdown_limit_pct_input / 100) if acc_balance > 0 else 0.0
st.sidebar.metric(label="ขาดทุนรวมวันนี้ (Today's P/L)", value=f"{drawdown_today_val_sb:,.2f} USD", delta_color="inverse")
st.sidebar.caption(f"ลิมิตขาดทุนต่อวัน: {drawdown_limit_abs_sb_val:,.2f} USD ({drawdown_limit_pct_input:.1f}%)")

trade_locked = False 
if acc_balance > 0 and drawdown_today_val_sb != 0 and drawdown_today_val_sb <= drawdown_limit_abs_sb_val :
    st.sidebar.error(f"🔴 หยุดเทรด! เกินลิมิตขาดทุนสำหรับพอร์ต {st.session_state.active_portfolio_name}")
    trade_locked = True

# --- 1.8. Save Plan Button Click Logic (Sidebar) ---
# This logic uses variables populated by FIBO/CUSTOM input sections
# Values are taken directly from session_state where inputs are stored
asset_to_save_sb, risk_pct_to_save_sb, direction_to_save_sb = "", 0.0, "N/A"
data_list_to_save_sb = []
button_pressed_save_sb_flag = False # Flag to check if any save button was pressed

if current_trade_mode == "FIBO":
    asset_to_save_sb = st.session_state.get("fibo_asset_val", "N/A")
    risk_pct_to_save_sb = st.session_state.get("fibo_risk_val", 0.0)
    direction_to_save_sb = st.session_state.get("fibo_direction_val", "N/A")
    data_list_to_save_sb = entry_data_fibo_list # This list is calculated fresh on each run
    if 'widget_sidebar_btn_save_fibo' in st.session_state and st.session_state.widget_sidebar_btn_save_fibo: # Check the correct button key
        button_pressed_save_sb_flag = True
elif current_trade_mode == "CUSTOM":
    asset_to_save_sb = st.session_state.get("custom_asset_val", "N/A")
    risk_pct_to_save_sb = st.session_state.get("custom_risk_val", 0.0)
    direction_to_save_sb = "N/A" 
    data_list_to_save_sb = custom_entries_list # This list is calculated fresh on each run
    if 'widget_sidebar_btn_save_custom' in st.session_state and st.session_state.widget_sidebar_btn_save_custom: # Check the correct button key
        button_pressed_save_sb_flag = True

if button_pressed_save_sb_flag:
    if not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    elif trade_locked:
        st.sidebar.error(f"ไม่สามารถบันทึกแผนสำหรับพอร์ต {st.session_state.active_portfolio_name} เนื่องจากเกินลิมิตขาดทุนรายวัน")
    elif data_list_to_save_sb: 
        save_plan_to_log(data_list_to_save_sb, current_trade_mode, asset_to_save_sb, risk_pct_to_save_sb, direction_to_save_sb, st.session_state.active_portfolio_name)
    else:
        st.sidebar.warning(f"กรุณากรอกข้อมูล {current_trade_mode} ให้ครบถ้วน เพื่อให้ระบบคำนวณค่าต่างๆ ก่อนบันทึก")

# ======================= END OF SEC 1 =======================
