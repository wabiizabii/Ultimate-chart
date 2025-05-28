# ======================= main.py (เริ่ม SEC 0 - อ้างอิง Master Version จาก Drive) =======================
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl # สำหรับ engine='openpyxl'
import os
from datetime import datetime, timedelta
import plotly.express as px
import google.generativeai as genai # สำหรับ AI Advisor (ถ้าใช้)
# import gspread # เปิดใช้งานเมื่อต้องการเชื่อมต่อ Google Sheets (จากโค้ดเดิมของคุณ)

# ======================= SEC 0: INITIAL SETUP & ALL FUNCTION DEFINITIONS =======================

# 0.1. Page Config (จากไฟล์ Master ของคุณ)
st.set_page_config(page_title="Ultimate-Chart", layout="wide") # ยึดตามไฟล์ Master

# 0.2. Initial Variables & File Paths (อ้างอิงจากไฟล์ Master และเพิ่มเติม)
acc_balance = 10000 # ค่าเริ่มต้น, จะถูก override ด้วย initial_balance ของ active portfolio
log_file = "trade_log.csv"
PORTFOLIO_FILE = 'portfolios.csv' # สำหรับระบบจัดการพอร์ตใหม่

# ชื่อ Google Sheet และ Worksheet (จากไฟล์ Master ของคุณ - ถ้าจะใช้ ให้เปิด comment)
# GOOGLE_SHEET_NAME = "TradeLog" 
# GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# 0.3. Google API Key (จากไฟล์ Master ของคุณ - ถ้าจะใช้ ให้เปิด comment และตั้งค่า secrets)
# if "gcp_service_account" in st.secrets: # ตรวจสอบ secrets ก่อน
#     try:
#         # gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
#         pass # Placeholder for gspread client
#     except Exception as e_gspread_init:
#         st.error(f"SEC 0.3: Error initializing gspread: {e_gspread_init}")
# if "google_api" in st.secrets and "GOOGLE_API_KEY" in st.secrets.google_api:
#     try:
#         genai.configure(api_key=st.secrets.google_api.GOOGLE_API_KEY)
#     except Exception as e_genai_config:
#         st.error(f"SEC 0.3: Error configuring Gemini AI: {e_genai_config}")


# 0.4. ALL FUNCTION DEFINITIONS

# 0.4.1. Portfolio Functions (ที่เราสร้างขึ้นใหม่)
def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            df = pd.read_csv(PORTFOLIO_FILE)
            required_cols = {'portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'}
            if not required_cols.issubset(df.columns):
                return pd.DataFrame(columns=list(required_cols)) # Return empty with correct structure
            df['initial_balance'] = pd.to_numeric(df['initial_balance'], errors='coerce').fillna(0.0)
            return df
        except pd.errors.EmptyDataError:
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
        except Exception as e:
            # st.error(f"SEC 0.4.1: เกิดข้อผิดพลาดในการโหลด {PORTFOLIO_FILE}: {e}")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
    else:
        return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])

def save_portfolios(df_to_save):
    try:
        df_to_save.to_csv(PORTFOLIO_FILE, index=False)
    except Exception as e:
        st.error(f"SEC 0.4.1: เกิดข้อผิดพลาดในการบันทึก {PORTFOLIO_FILE}: {e}")

# 0.4.2. Utility Functions (Drawdown & Performance - จากไฟล์ Master ของคุณ, ปรับปรุงเล็กน้อย)
def get_today_drawdown(log_file_path, current_acc_balance, active_portfolio=None): # current_acc_balance ไม่ได้ใช้ใน logic นี้
    if not os.path.exists(log_file_path): return 0.0
    try:
        df = pd.read_csv(log_file_path)
        if active_portfolio and "Portfolio" in df.columns:
            df = df[df["Portfolio"] == active_portfolio]
        elif "Portfolio" not in df.columns and active_portfolio: # Log file exists but no Portfolio column
             pass # Consider how to handle this - show all or show none? For now, show all if no Portfolio col.

        if df.empty and active_portfolio : return 0.0 # No data for this portfolio
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0.0
        
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0.0)
        df_today = df[df["Timestamp"].str.startswith(today_str)]
        return df_today["Risk $"].sum()
    except FileNotFoundError: return 0.0
    except Exception: return 0.0 # Catch other potential errors like empty file after filtering

def get_performance(log_file_path, active_portfolio=None, mode="week"):
    if not os.path.exists(log_file_path): return 0.0, 0.0, 0
    try:
        df = pd.read_csv(log_file_path)
        if active_portfolio and "Portfolio" in df.columns:
            df = df[df["Portfolio"] == active_portfolio]
        elif "Portfolio" not in df.columns and active_portfolio:
            pass # Show all if no Portfolio col
        
        if df.empty and active_portfolio: return 0.0,0.0,0

        if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0.0, 0.0, 0
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0.0)
            
        now = datetime.now()
        if mode == "week":
            start_date_str = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d") # Use timedelta here
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
    except Exception: return 0.0,0.0,0

# 0.4.3. Save Plan Function (ปรับปรุงให้รับ active_portfolio_arg)
def save_plan_to_log(data_to_save, trade_mode_arg, asset_arg, risk_pct_arg, direction_arg, active_portfolio_arg):
    if not active_portfolio_arg:
        st.sidebar.error("ไม่สามารถบันทึกแผน: กรุณาเลือกหรือสร้างพอร์ตก่อน")
        return
    
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if not isinstance(data_to_save, list) or not all(isinstance(item, dict) for item in data_to_save):
        st.sidebar.error("ข้อมูลสำหรับบันทึก Log ไม่ถูกต้อง (ต้องเป็น list of dictionaries)")
        return

    df_to_write = pd.DataFrame(data_to_save)
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
            all_cols = list(df_old_log.columns.union(df_to_write.columns, sort=False))
            df_old_log_aligned = df_old_log.reindex(columns=all_cols, fill_value=np.nan) # fill_value for new cols in old_log
            df_to_write_aligned = df_to_write.reindex(columns=all_cols, fill_value=np.nan) # fill_value for new cols in df_to_write

            df_final_log = pd.concat([df_old_log_aligned, df_to_write_aligned], ignore_index=True)
        else:
            df_final_log = df_to_write
        df_final_log.to_csv(log_file, index=False)
        st.sidebar.success(f"บันทึกแผน ({trade_mode_arg}) สำหรับพอร์ต '{active_portfolio_arg}' สำเร็จ!")
    except Exception as e:
        st.sidebar.error(f"SEC 0.4.3: Save Plan ไม่สำเร็จ: {e}")

# 0.4.4. Statement Extraction Function (extract_data_from_report เดิม, ปรับปรุง)
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
                
                numeric_cols_in_stmt = ['Volume', 'Price', 'S / L', 'T / P', 'Commission', 'Fee', 'Swap', 'Profit', 'Balance']
                for col_stmt_num in numeric_cols_in_stmt:
                    if col_stmt_num in df_section.columns:
                        if df_section[col_stmt_num].dtype == 'object':
                            df_section[col_stmt_num] = df_section[col_stmt_num].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
                        df_section[col_stmt_num] = pd.to_numeric(df_section[col_stmt_num], errors='coerce')
                extracted_data[section_name.lower()] = df_section

    if "Results" in section_starts:
        results_stats = {}
        start_row_res = section_starts["Results"]
        results_df_scan = df_raw.iloc[start_row_res : start_row_res + 20]
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
        if results_stats:
            df_balance_summary_ext = pd.DataFrame(list(results_stats.items()), columns=['Metric', 'Value'])
            df_balance_summary_ext['Value_temp'] = df_balance_summary_ext['Value'].astype(str).str.split(' ').str[0].str.replace(r'[^\d\.\-]', '', regex=True)
            df_balance_summary_ext['Value'] = pd.to_numeric(df_balance_summary_ext['Value_temp'], errors='coerce')
            # If conversion to numeric fails for some, keep original string, otherwise use numeric
            df_balance_summary_ext['Value'] = df_balance_summary_ext['Value'].fillna(df_balance_summary_ext['Value_temp'])
            df_balance_summary_ext.drop(columns=['Value_temp'], inplace=True, errors='ignore')
            extracted_data["balance_summary"] = df_balance_summary_ext
    return extracted_data

# 0.4.5. Dashboard Data Loading Function (ปรับปรุงจากโค้ดเดิม)
def load_data_for_dashboard(active_portfolio_arg, current_portfolio_initial_balance):
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Log File (แผนเทรด)", "Statement Import (ผลเทรดจริง)"],
        index=0, 
        key="main_dashboard_source_selector_key_final" 
    )
    df_dashboard = pd.DataFrame()
    profit_col_identified, asset_col_identified, date_col_identified = None, None, None

    if source_option == "Log File (แผนเทรด)":
        if not active_portfolio_arg: st.warning("Dashboard: กรุณาเลือก Active Portfolio"); return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
        if os.path.exists(log_file):
            try:
                df_log_all_dash = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all_dash.columns: st.warning("Dashboard: Log file ไม่มีคอลัมน์ 'Portfolio'"); return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
                df_dashboard = df_log_all_dash[df_log_all_dash["Portfolio"] == active_portfolio_arg].copy()
                if df_dashboard.empty: st.info(f"Dashboard: ไม่พบข้อมูล Log File สำหรับพอร์ต '{active_portfolio_arg}'")
            except Exception as e_log_dash_load: st.error(f"Dashboard: ไม่สามารถโหลด Log File: {e_log_dash_load}")
        else: st.info(f"Dashboard: ไม่พบ Log File ({log_file})")
    
    else: # Statement Import (ผลเทรดจริง)
        if not active_portfolio_arg: st.warning("Dashboard: กรุณาเลือก Active Portfolio"); return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
        df_from_session_dash = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame())
        if not df_from_session_dash.empty:
            df_dashboard = df_from_session_dash.copy()
            if 'Portfolio' in df_dashboard.columns: df_dashboard = df_dashboard[df_dashboard['Portfolio'] == active_portfolio_arg]
        if df_dashboard.empty: st.info(f"Dashboard: ไม่มีข้อมูล Statement สำหรับพอร์ต '{active_portfolio_arg}' (โปรดอัปโหลดในส่วน Statement Import)")

    if not df_dashboard.empty:
        # Standardize and clean 'Profit' and 'Risk $'
        if 'Profit' in df_dashboard.columns:
            if df_dashboard['Profit'].dtype == 'object': df_dashboard['Profit'] = df_dashboard['Profit'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
            df_dashboard['Profit'] = pd.to_numeric(df_dashboard['Profit'], errors='coerce').fillna(0.0)
        if 'Risk $' in df_dashboard.columns:
            if df_dashboard['Risk $'].dtype == 'object': df_dashboard['Risk $'] = df_dashboard['Risk $'].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
            df_dashboard['Risk $'] = pd.to_numeric(df_dashboard['Risk $'], errors='coerce').fillna(0.0)

        # Identify profit column
        if 'Profit' in df_dashboard.columns and df_dashboard['Profit'].abs().sum() != 0: profit_col_identified = 'Profit'
        elif 'Risk $' in df_dashboard.columns: profit_col_identified = 'Risk $'
        
        numeric_cols_to_clean_dash = ['RR', 'Lot', 'Commission', 'Swap', 'Volume', 'Price', 'S / L', 'T / P']
        for col_num_clean_dash in numeric_cols_to_clean_dash:
            if col_num_clean_dash in df_dashboard.columns:
                if df_dashboard[col_num_clean_dash].dtype == 'object': df_dashboard[col_num_clean_dash] = df_dashboard[col_num_clean_dash].astype(str).str.replace(r'[^\d\.\-]', '', regex=True)
                df_dashboard[col_num_clean_dash] = pd.to_numeric(df_dashboard[col_num_clean_dash], errors='coerce').fillna(0.0)

        if 'Asset' in df_dashboard.columns: asset_col_identified = 'Asset'
        elif 'Symbol' in df_dashboard.columns: asset_col_identified = 'Symbol'

        date_col_options_dash = [col for col in ["Timestamp", "Time", "Date", "Open Time", "Close Time"] if col in df_dashboard.columns]
        for col_date_dash in date_col_options_dash:
            try:
                if not pd.api.types.is_datetime64_any_dtype(df_dashboard[col_date_dash]):
                    df_dashboard[col_date_dash] = pd.to_datetime(df_dashboard[col_date_dash], errors='coerce')
                if df_dashboard[col_date_dash].notna().any(): date_col_identified = col_date_dash; break
            except Exception: continue
            
    return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified

# 0.4.6. Google Sheets Functions (Placeholder - จากไฟล์ Master ของคุณ)
# def get_gspread_client():
#     # ... (โค้ดเดิมของคุณจากไฟล์ Master) ...
#     # ตรวจสอบ st.secrets["gcp_service_account"]
#     return None 

# @st.cache_data(ttl=3600) 
# def load_statement_from_gsheets():
#     # ... (โค้ดเดิมของคุณจากไฟล์ Master) ...
#     # ควรมี parser_config และการวน loop อ่านข้อมูล
#     return {} 

# def save_statement_to_gsheets(df_to_save):
#     # ... (โค้ดเดิมของคุณจากไฟล์ Master) ...
#     # ควรมี worksheet.clear() และ worksheet.update()
#     pass

# ======================= END OF SEC 0 =======================

# ======================= (ต่อจาก SEC 0) =======================

# ======================= SEC 1: SIDEBAR - CORE CONTROLS, PORTFOLIO, INPUTS, RISK MGMT =======================

# --- 1.1. Portfolio Selection & Management UI ---
portfolios_df_sec1 = load_portfolios() # ใช้ชื่อตัวแปรใหม่เพื่อไม่ให้สับสน
acc_balance_sec1 = 10000.0 # Default balance, จะถูกอัปเดตตามพอร์ตที่เลือก

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน") # UI: ไม่มีเลขนำหน้า

if not portfolios_df_sec1.empty:
    portfolio_names_list_sidebar = portfolios_df_sec1['portfolio_name'].tolist()
    
    # จัดการ session_state สำหรับ active_portfolio_name
    if 'active_portfolio_name' not in st.session_state:
        st.session_state.active_portfolio_name = portfolio_names_list_sidebar[0] if portfolio_names_list_sidebar else None
    elif st.session_state.active_portfolio_name not in portfolio_names_list_sidebar:
        st.session_state.active_portfolio_name = portfolio_names_list_sidebar[0] if portfolio_names_list_sidebar else None

    # หา index ของพอร์ตที่เลือกปัจจุบัน (หรือ default)
    current_index_sidebar = 0
    if st.session_state.active_portfolio_name and portfolio_names_list_sidebar:
        try:
            current_index_sidebar = portfolio_names_list_sidebar.index(st.session_state.active_portfolio_name)
        except ValueError:
            st.session_state.active_portfolio_name = portfolio_names_list_sidebar[0] # Default to first if not found
            current_index_sidebar = 0
            
    selected_portfolio_name_sidebar = st.sidebar.selectbox(
        "เลือกพอร์ต:",
        options=portfolio_names_list_sidebar,
        index=current_index_sidebar,
        key='widget_sidebar_portfolio_selector' 
    )
    
    if selected_portfolio_name_sidebar != st.session_state.active_portfolio_name:
        st.session_state.active_portfolio_name = selected_portfolio_name_sidebar
        st.rerun() 

    if st.session_state.active_portfolio_name:
        active_portfolio_details_sidebar = portfolios_df_sec1[portfolios_df_sec1['portfolio_name'] == st.session_state.active_portfolio_name]
        if not active_portfolio_details_sidebar.empty:
            acc_balance_sec1 = float(active_portfolio_details_sidebar['initial_balance'].iloc[0])
            st.sidebar.success(f"Active: **{st.session_state.active_portfolio_name}** (Bal: ${acc_balance_sec1:,.2f})")
        else:
            st.sidebar.warning("ไม่พบรายละเอียดพอร์ตที่เลือก กำลังใช้ค่าเริ่มต้น")
            # st.session_state.active_portfolio_name = None # ไม่ควรรีเซ็ตตรงนี้ อาจทำให้เกิด loop
            acc_balance_sec1 = 10000.0 
else:
    st.sidebar.info("ยังไม่มีพอร์ต กรุณาเพิ่มพอร์ตด้านล่าง")
    st.session_state.active_portfolio_name = None
    acc_balance_sec1 = 10000.0 

# --- Expander for managing portfolios in Sidebar ---
with st.sidebar.expander("💼 จัดการพอร์ต", expanded=False): 
    st.subheader("พอร์ตทั้งหมดของคุณ") 
    portfolios_df_display_sidebar_exp = load_portfolios() 
    st.dataframe(portfolios_df_display_sidebar_exp, use_container_width=True, hide_index=True, 
                 column_config={"portfolio_id": "ID", "portfolio_name": "ชื่อพอร์ต", 
                                "initial_balance": st.column_config.NumberColumn("บาลานซ์ ($)", format="$%.2f"),
                                "creation_date": "วันที่สร้าง"})

    with st.form("sidebar_new_portfolio_form_key_exp", clear_on_submit=True): 
        st.subheader("➕ เพิ่มพอร์ตใหม่") 
        new_p_name_sidebar_form_exp = st.text_input("ชื่อพอร์ต")
        new_p_bal_sidebar_form_exp = st.number_input("บาลานซ์เริ่มต้น ($)", min_value=0.0, value=10000.0, step=100.0, format="%.2f")
        
        if st.form_submit_button("💾 บันทึกพอร์ตใหม่"):
            current_portfolios_df_in_form_exp = load_portfolios()
            if not new_p_name_sidebar_form_exp: st.warning("กรุณาใส่ชื่อพอร์ต")
            elif new_p_name_sidebar_form_exp in current_portfolios_df_in_form_exp['portfolio_name'].values: st.error(f"ชื่อพอร์ต '{new_p_name_sidebar_form_exp}' มีอยู่แล้ว")
            else:
                if current_portfolios_df_in_form_exp.empty or 'portfolio_id' not in current_portfolios_df_in_form_exp.columns or current_portfolios_df_in_form_exp['portfolio_id'].isnull().all():
                    new_id_sidebar_form_exp = 1
                else:
                    new_id_sidebar_form_exp = current_portfolios_df_in_form_exp['portfolio_id'].max() + 1 if pd.notna(current_portfolios_df_in_form_exp['portfolio_id'].max()) else 1
                
                new_p_data_sidebar_form_exp = pd.DataFrame([{'portfolio_id': int(new_id_sidebar_form_exp), 'portfolio_name': new_p_name_sidebar_form_exp, 'initial_balance': new_p_bal_sidebar_form_exp, 'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                updated_portfolios_df_form_exp = pd.concat([current_portfolios_df_in_form_exp, new_p_data_sidebar_form_exp], ignore_index=True)
                save_portfolios(updated_portfolios_df_form_exp)
                st.success(f"เพิ่มพอร์ต '{new_p_name_sidebar_form_exp}' สำเร็จ!")
                if st.session_state.active_portfolio_name is None and not updated_portfolios_df_form_exp.empty:
                    st.session_state.active_portfolio_name = new_p_name_sidebar_form_exp
                st.rerun()
st.sidebar.markdown("---")

# --- 1.2. Main Trade Setup ---
st.sidebar.header("Trade Setup & Controls") 
if 'sidebar_dd_limit_pct_val' not in st.session_state: st.session_state.sidebar_dd_limit_pct_val = 2.0
drawdown_limit_pct_input = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)", min_value=0.1, max_value=20.0, 
    value=st.session_state.sidebar_dd_limit_pct_val, step=0.1, format="%.1f", 
    key="widget_sidebar_dd_limit_main" 
)
st.session_state.sidebar_dd_limit_pct_val = drawdown_limit_pct_input

if 'sidebar_current_trade_mode_val' not in st.session_state: st.session_state.sidebar_current_trade_mode_val = "FIBO"
current_trade_mode = st.sidebar.radio(
    "Trade Mode", ["FIBO", "CUSTOM"], 
    index=["FIBO", "CUSTOM"].index(st.session_state.sidebar_current_trade_mode_val),
    horizontal=True, key="widget_sidebar_trade_mode_main"
)
st.session_state.sidebar_current_trade_mode_val = current_trade_mode

if st.sidebar.button("🔄 Reset Form", key="widget_sidebar_reset_form_main"):
    keys_to_preserve_main = {
        'active_portfolio_name', 'sidebar_portfolio_selector_widget_key', 
        'sidebar_dd_limit_pct_val', 'widget_sidebar_dd_limit_main',
        'sidebar_current_trade_mode_val', 'widget_sidebar_trade_mode_main'
    }
    for k_scale_main in ['widget_scaling_step_main', 'widget_scaling_min_risk_main', 'widget_scaling_max_risk_main', 'widget_scaling_mode_radio_main']:
        if k_scale_main in st.session_state: keys_to_preserve_main.add(k_scale_main) # Preserve scaling config
        if st.session_state.get(k_scale_main, None) is not None: # Also preserve their actual values
            keys_to_preserve_main.add(st.session_state[k_scale_main])

    for key_in_ss_main in list(st.session_state.keys()):
        if key_in_ss_main not in keys_to_preserve_main:
            if key_in_ss_main.startswith('fibo_') or key_in_ss_main.startswith('custom_') or \
               key_in_ss_main.startswith('widget_fibo_') or key_in_ss_main.startswith('widget_custom_'):
                del st.session_state[key_in_ss_main]
    
    if "fibo_flags_list_config_main" in st.session_state: 
        st.session_state.fibo_flags_list_config_main = [True] * 5 # Assuming 5 Fibo levels
    st.rerun()

# --- 1.3. FIBO Input Zone ---
entry_data_fibo_list = [] 
if current_trade_mode == "FIBO":
    st.sidebar.subheader("FIBO Mode Inputs") 
    
    fibo_asset_key, fibo_risk_key, fibo_direction_key, fibo_high_key, fibo_low_key = "fibo_asset_cfg", "fibo_risk_cfg", "fibo_direction_cfg", "fibo_high_cfg", "fibo_low_cfg"
    if fibo_asset_key not in st.session_state: st.session_state[fibo_asset_key] = "XAUUSD"
    if fibo_risk_key not in st.session_state: st.session_state[fibo_risk_key] = 1.0
    if fibo_direction_key not in st.session_state: st.session_state[fibo_direction_key] = "Long"
    if fibo_high_key not in st.session_state: st.session_state[fibo_high_key] = ""
    if fibo_low_key not in st.session_state: st.session_state[fibo_low_key] = ""

    col1_fibo_main, col2_fibo_main = st.sidebar.columns(2)
    with col1_fibo_main:
        st.session_state[fibo_asset_key] = st.text_input("Asset", value=st.session_state[fibo_asset_key], key="widget_" + fibo_asset_key)
    with col2_fibo_main:
        st.session_state[fibo_risk_key] = st.number_input("Risk %", min_value=0.01, value=st.session_state[fibo_risk_key], step=0.01, key="widget_" + fibo_risk_key)

    st.session_state[fibo_direction_key] = st.sidebar.radio("Direction", ["Long", "Short"], index=["Long", "Short"].index(st.session_state[fibo_direction_key]), horizontal=True, key="widget_" + fibo_direction_key)
    
    col_h_fibo_main, col_l_fibo_main = st.sidebar.columns(2)
    with col_h_fibo_main:
        st.session_state[fibo_high_key] = st.text_input("High", value=st.session_state[fibo_high_key], key="widget_" + fibo_high_key)
    with col_l_fibo_main:
        st.session_state[fibo_low_key] = st.text_input("Low", value=st.session_state[fibo_low_key], key="widget_" + fibo_low_key)
    
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibo_levels_list_main = [0.114, 0.25, 0.382, 0.5, 0.618] 
    fibo_flags_key = "fibo_flags_list_config_main"
    if fibo_flags_key not in st.session_state: st.session_state[fibo_flags_key] = [True] * len(fibo_levels_list_main)
    
    cols_fibo_checkboxes_main = st.sidebar.columns(len(fibo_levels_list_main))
    temp_fibo_flags_val = st.session_state[fibo_flags_key][:] 
    for i, col_cb_fibo_item_main in enumerate(cols_fibo_checkboxes_main): 
        temp_fibo_flags_val[i] = col_cb_fibo_item_main.checkbox(f"{fibo_levels_list_main[i]:.3f}", value=temp_fibo_flags_val[i], key=f"widget_fibo_level_cb_main_{i}")
    st.session_state[fibo_flags_key] = temp_fibo_flags_val
    
    try:
        high_f_calc_main = float(st.session_state[fibo_high_key])
        low_f_calc_main = float(st.session_state[fibo_low_key])
        current_risk_pct_fibo_main_calc = st.session_state[fibo_risk_key]
        current_direction_fibo_main_calc = st.session_state[fibo_direction_key]
        if high_f_calc_main > low_f_calc_main and acc_balance_sec1 > 0:
            selected_fibs_f_calc_main = [fibo_levels_list_main[i] for i, sel_main_calc in enumerate(st.session_state[fibo_flags_key]) if sel_main_calc]
            n_selected_fibs_f_calc_main = len(selected_fibs_f_calc_main)
            risk_dollar_total_f_calc_main = acc_balance_sec1 * (current_risk_pct_fibo_main_calc / 100)
            risk_dollar_per_entry_f_calc_main = risk_dollar_total_f_calc_main / n_selected_fibs_f_calc_main if n_selected_fibs_f_calc_main > 0 else 0.0
            for fib_level_item_f_calc_main in selected_fibs_f_calc_main:
                entry_p_f_calc_main = low_f_calc_main + (high_f_calc_main - low_f_calc_main) * fib_level_item_f_calc_main if current_direction_fibo_main_calc == "Long" else high_f_calc_main - (high_f_calc_main - low_f_calc_main) * fib_level_item_f_calc_main
                sl_p_f_calc_main = low_f_calc_main if current_direction_fibo_main_calc == "Long" else high_f_calc_main
                stop_p_f_calc_main = abs(entry_p_f_calc_main - sl_p_f_calc_main)
                lot_f_calc_main = (risk_dollar_per_entry_f_calc_main / stop_p_f_calc_main) if stop_p_f_calc_main > 0 else 0.0
                entry_data_fibo_list.append({"Fibo Level": f"{fib_level_item_f_calc_main:.3f}", "Entry": f"{entry_p_f_calc_main:.2f}", "SL": f"{sl_p_f_calc_main:.2f}", "Lot": f"{lot_f_calc_main:.2f}", "Risk $": f"{lot_f_calc_main * stop_p_f_calc_main:.2f}"})
    except (ValueError, TypeError, ZeroDivisionError): pass 
    
    save_fibo_button = st.sidebar.button("💾 Save Plan (FIBO)", key="widget_sidebar_btn_save_fibo_final")

# --- 1.4. CUSTOM Input Zone ---
custom_entries_list = [] 
if current_trade_mode == "CUSTOM":
    st.sidebar.subheader("CUSTOM Mode Inputs") 
    
    custom_asset_key, custom_risk_key, custom_n_key = "custom_asset_cfg", "custom_risk_cfg", "custom_n_entry_cfg"
    if custom_asset_key not in st.session_state: st.session_state[custom_asset_key] = "XAUUSD"
    if custom_risk_key not in st.session_state: st.session_state[custom_risk_key] = 1.0
    if custom_n_key not in st.session_state: st.session_state[custom_n_key] = 1

    col1_cust_sb, col2_cust_sb = st.sidebar.columns(2)
    with col1_cust_sb:
        st.session_state[custom_asset_key] = st.text_input("Asset", value=st.session_state[custom_asset_key], key="widget_" + custom_asset_key)
    with col2_cust_sb:
        st.session_state[custom_risk_key] = st.number_input("Risk %", min_value=0.01, value=st.session_state[custom_risk_key], step=0.01, key="widget_" + custom_risk_key)
    
    st.session_state[custom_n_key] = st.sidebar.number_input("จำนวนไม้", min_value=1, value=st.session_state[custom_n_key], step=1, key="widget_" + custom_n_key)
    current_risk_pct_custom_sb = st.session_state[custom_risk_key]
    num_entries_custom_sb = int(st.session_state[custom_n_key])

    for i_cust_sb_loop in range(num_entries_custom_sb):
        st.sidebar.markdown(f"--- ไม้ที่ {i_cust_sb_loop+1} ---")
        e_key_sb = f"widget_custom_entry_main_sb_{i_cust_sb_loop}"
        s_key_sb = f"widget_custom_sl_main_sb_{i_cust_sb_loop}"
        t_key_sb = f"widget_custom_tp_main_sb_{i_cust_sb_loop}"
        
        st.session_state[e_key_sb] = st.sidebar.text_input(f"Entry {i_cust_sb_loop+1}", value=st.session_state.get(e_key_sb, "0.0"), key=e_key_sb)
        st.session_state[s_key_sb] = st.sidebar.text_input(f"SL {i_cust_sb_loop+1}", value=st.session_state.get(s_key_sb, "0.0"), key=s_key_sb)
        st.session_state[t_key_sb] = st.sidebar.text_input(f"TP {i_cust_sb_loop+1}", value=st.session_state.get(t_key_sb, "0.0"), key=t_key_sb)
        
        try:
            if acc_balance_sec1 > 0 and num_entries_custom_sb > 0 :
                risk_dollar_total_cust_c_sb = acc_balance_sec1 * (current_risk_pct_custom_sb / 100)
                risk_dollar_per_entry_cust_c_sb = risk_dollar_total_cust_c_sb / num_entries_custom_sb
                entry_p_cust_c_sb, sl_p_cust_c_sb, tp_p_cust_c_sb = float(st.session_state[e_key_sb]), float(st.session_state[s_key_sb]), float(st.session_state[t_key_sb])
                stop_p_cust_c_sb = abs(entry_p_cust_c_sb - sl_p_cust_c_sb)
                lot_cust_c_sb = (risk_dollar_per_entry_cust_c_sb / stop_p_cust_c_sb) if stop_p_cust_c_sb > 0 else 0.0
                rr_cust_c_sb = abs(tp_p_cust_c_sb - entry_p_cust_c_sb) / stop_p_cust_c_sb if stop_p_cust_c_sb > 0 else 0.0
                custom_entries_list.append({
                    "Entry": f"{entry_p_cust_c_sb:.2f}", "SL": f"{sl_p_cust_c_sb:.2f}", "TP": f"{tp_p_cust_c_sb:.2f}",
                    "Lot": f"{lot_cust_c_sb:.2f}", "Risk $": f"{lot_cust_c_sb * stop_p_cust_c_sb:.2f}", "RR": f"{rr_cust_c_sb:.2f}"
                })
        except (ValueError, TypeError, ZeroDivisionError): pass
    save_custom_button = st.sidebar.button("💾 Save Plan (CUSTOM)", key="widget_sidebar_btn_save_custom_final")

# --- 1.5. Strategy Summary (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Strategy Summary") 
if current_trade_mode == "FIBO":
    if entry_data_fibo_list:
        df_fibo_summary_sidebar = pd.DataFrame(entry_data_fibo_list)
        st.sidebar.write(f"Total Lots: {pd.to_numeric(df_fibo_summary_sidebar['Lot'], errors='coerce').sum():.2f}")
        st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_fibo_summary_sidebar['Risk $'], errors='coerce').sum():.2f}")
    else: st.sidebar.caption("กรอกข้อมูล FIBO เพื่อดู Summary")
elif current_trade_mode == "CUSTOM":
    if custom_entries_list:
        df_custom_summary_sidebar = pd.DataFrame(custom_entries_list)
        st.sidebar.write(f"Total Lots: {pd.to_numeric(df_custom_summary_sidebar['Lot'], errors='coerce').sum():.2f}")
        st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_custom_summary_sidebar['Risk $'], errors='coerce').sum():.2f}")
        avg_rr_sidebar = pd.to_numeric(df_custom_summary_sidebar['RR'], errors='coerce').mean()
        if pd.notna(avg_rr_sidebar): st.sidebar.write(f"Average RR: {avg_rr_sidebar:.2f}")
    else: st.sidebar.caption("กรอกข้อมูล CUSTOM เพื่อดู Summary")

# --- 1.6. Scaling Manager (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Scaling Manager") 
default_scaling_cfg_sb = {"scaling_step_cfg_sb": 0.25, "scaling_min_risk_cfg_sb": 0.5, "scaling_max_risk_cfg_sb": 5.0, "scaling_mode_cfg_sb": "Manual"}
for k_cfg_sb, v_cfg_sb in default_scaling_cfg_sb.items():
    if k_cfg_sb not in st.session_state: st.session_state[k_cfg_sb] = v_cfg_sb
with st.sidebar.expander("Scaling Settings", expanded=False):
    st.session_state.scaling_step_cfg_sb = st.number_input("Scaling Step (%)", min_value=0.01,max_value=1.0,value=st.session_state.scaling_step_cfg_sb,step=0.01,format="%.2f",key="widget_scaling_step_sb")
    st.session_state.scaling_min_risk_cfg_sb = st.number_input("Minimum Risk %",min_value=0.01,max_value=100.0,value=st.session_state.scaling_min_risk_cfg_sb,step=0.01,format="%.2f",key="widget_scaling_min_risk_sb")
    st.session_state.scaling_max_risk_cfg_sb = st.number_input("Maximum Risk %",min_value=0.01,max_value=100.0,value=st.session_state.scaling_max_risk_cfg_sb,step=0.01,format="%.2f",key="widget_scaling_max_risk_sb")
    st.session_state.scaling_mode_cfg_sb = st.radio("Scaling Mode",["Manual","Auto"],index=["Manual","Auto"].index(st.session_state.scaling_mode_cfg_sb),horizontal=True,key="widget_scaling_mode_radio_sb")

if st.session_state.active_portfolio_name:
    winrate_scaling_sb, gain_scaling_sb, _ = get_performance(log_file, st.session_state.active_portfolio_name, acc_balance_sec1)
    current_risk_for_scaling_sidebar_val = st.session_state.get("fibo_risk_cfg", 1.0) if current_trade_mode == "FIBO" else st.session_state.get("custom_risk_cfg", 1.0)
    
    suggest_risk_val_sidebar_val = current_risk_for_scaling_sidebar_val
    msg_scale_sidebar_val = f"Risk% ({st.session_state.active_portfolio_name}) คงที่: {current_risk_for_scaling_sidebar_val:.2f}%"

    if acc_balance_sec1 > 0:
        if winrate_scaling_sb > 55 and gain_scaling_sb > 0.02 * acc_balance_sec1:
            suggest_risk_val_sidebar_val = min(current_risk_for_scaling_sidebar_val + st.session_state.scaling_step_cfg_sb, st.session_state.scaling_max_risk_cfg_sb)
            msg_scale_sidebar_val = f"🎉 ผลงานดี! ({st.session_state.active_portfolio_name}) Winrate {winrate_scaling_sb:.1f}%, Gain {gain_scaling_sb:.2f}. แนะนำเพิ่ม Risk เป็น {suggest_risk_val_sidebar_val:.2f}%"
        elif winrate_scaling_sb < 45 or gain_scaling_sb < 0:
            suggest_risk_val_sidebar_val = max(current_risk_for_scaling_sidebar_val - st.session_state.scaling_step_cfg_sb, st.session_state.scaling_min_risk_cfg_sb)
            msg_scale_sidebar_val = f"⚠️ ควรลด Risk! ({st.session_state.active_portfolio_name}) Winrate {winrate_scaling_sb:.1f}%, P/L {gain_scaling_sb:.2f}. แนะนำลด Risk เป็น {suggest_risk_val_sidebar_val:.2f}%"
    
    st.sidebar.info(msg_scale_sidebar_val)
    if st.session_state.scaling_mode_cfg_sb == "Manual" and suggest_risk_val_sidebar_val != current_risk_for_scaling_sidebar_val:
        if st.sidebar.button(f"ปรับ Risk เป็น {suggest_risk_val_sidebar_val:.2f}", key="widget_sidebar_btn_scaling_adjust_final"):
            if current_trade_mode == "FIBO": st.session_state.fibo_risk_cfg = suggest_risk_val_sidebar_val # Use the correct session state key
            else: st.session_state.custom_risk_cfg = suggest_risk_val_sidebar_val # Use the correct session state key
            st.rerun()
    elif st.session_state.scaling_mode_cfg_sb == "Auto" and suggest_risk_val_sidebar_val != current_risk_for_scaling_sidebar_val:
        if current_trade_mode == "FIBO": st.session_state.fibo_risk_cfg = suggest_risk_val_sidebar_val
        else: st.session_state.custom_risk_cfg = suggest_risk_val_sidebar_val
else: st.sidebar.caption("เลือก Active Portfolio เพื่อดูคำแนะนำ Scaling")

# --- 1.7. Drawdown Display & Lock Logic (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader(f"การควบคุมความเสี่ยง ({st.session_state.active_portfolio_name or 'N/A'})") 
drawdown_today_val_sidebar = 0.0
if st.session_state.active_portfolio_name:
    drawdown_today_val_sidebar = get_today_drawdown(log_file, acc_balance_sec1, st.session_state.active_portfolio_name)

drawdown_limit_abs_sidebar_val = -acc_balance_sec1 * (drawdown_limit_pct_input / 100) if acc_balance_sec1 > 0 else 0.0
st.sidebar.metric(label="ขาดทุนรวมวันนี้ (Today's P/L)", value=f"{drawdown_today_val_sidebar:,.2f} USD", delta_color="inverse")
st.sidebar.caption(f"ลิมิตขาดทุนต่อวัน: {drawdown_limit_abs_sidebar_val:,.2f} USD ({drawdown_limit_pct_input:.1f}%)")

trade_locked = False 
if acc_balance_sec1 > 0 and drawdown_today_val_sidebar != 0 and drawdown_today_val_sidebar <= drawdown_limit_abs_sidebar_val :
    st.sidebar.error(f"🔴 หยุดเทรด! เกินลิมิตขาดทุนสำหรับพอร์ต {st.session_state.active_portfolio_name}")
    trade_locked = True

# --- 1.8. Save Plan Button Click Logic (Sidebar) ---
# This logic uses variables populated by FIBO/CUSTOM input sections
asset_to_save_sidebar, risk_pct_to_save_sidebar, direction_to_save_sidebar = "", 0.0, "N/A"
data_list_to_save_sidebar = []
button_pressed_save_sidebar = False 

if current_trade_mode == "FIBO":
    asset_to_save_sidebar = st.session_state.get("fibo_asset_cfg", "N/A")
    risk_pct_to_save_sidebar = st.session_state.get("fibo_risk_cfg", 0.0)
    direction_to_save_sidebar = st.session_state.get("fibo_direction_cfg", "N/A")
    data_list_to_save_sidebar = entry_data_fibo_list # This list is calculated fresh on each run
    if 'widget_sidebar_btn_save_fibo_final' in st.session_state and st.session_state.widget_sidebar_btn_save_fibo_final:
        button_pressed_save_sidebar = True
elif current_trade_mode == "CUSTOM":
    asset_to_save_sidebar = st.session_state.get("custom_asset_cfg", "N/A")
    risk_pct_to_save_sidebar = st.session_state.get("custom_risk_cfg", 0.0)
    direction_to_save_sidebar = "N/A" 
    data_list_to_save_sidebar = custom_entries_list 
    if 'widget_sidebar_btn_save_custom_final' in st.session_state and st.session_state.widget_sidebar_btn_save_custom_final:
        button_pressed_save_sidebar = True

if button_pressed_save_sidebar:
    if not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    elif trade_locked:
        st.sidebar.error(f"ไม่สามารถบันทึกแผนสำหรับพอร์ต {st.session_state.active_portfolio_name} เนื่องจากเกินลิมิตขาดทุนรายวัน")
    elif data_list_to_save_sidebar: 
        save_plan_to_log(data_list_to_save_sidebar, current_trade_mode, asset_to_save_sidebar, risk_pct_to_save_sidebar, direction_to_save_sidebar, st.session_state.active_portfolio_name)
    else:
        st.sidebar.warning(f"กรุณากรอกข้อมูล {current_trade_mode} ให้ครบถ้วน เพื่อให้ระบบคำนวณค่าต่างๆ ก่อนบันทึก")

# ======================= END OF SEC 1 =======================

# ======================= SEC 2: MAIN AREA - CURRENT ENTRY PLAN DETAILS =======================
st.header("🎯 Entry Plan Details")

if st.session_state.get('active_portfolio_name', None):
    current_display_balance_main = acc_balance_sec1 # Use balance from active portfolio in sidebar
    st.caption(f"สำหรับพอร์ต: **{st.session_state.active_portfolio_name}** (Balance: ${current_display_balance_main:,.2f})")
    
    if current_trade_mode == "FIBO":
        if entry_data_fibo_list: 
            df_display_fibo_main_area = pd.DataFrame(entry_data_fibo_list)
            st.dataframe(df_display_fibo_main_area, hide_index=True, use_container_width=True)
            try:
                high_fibo_tp_main = float(st.session_state.get("fibo_high_cfg", "0"))
                low_fibo_tp_main = float(st.session_state.get("fibo_low_cfg", "0"))
                direction_fibo_tp_main = st.session_state.get("fibo_direction_cfg", "Long")
                if high_fibo_tp_main > low_fibo_tp_main:
                    tp1_main = low_fibo_tp_main + (high_fibo_tp_main - low_fibo_tp_main) * 1.618 if direction_fibo_tp_main == "Long" else high_fibo_tp_main - (high_fibo_tp_main - low_fibo_tp_main) * 1.618
                    tp2_main = low_fibo_tp_main + (high_fibo_tp_main - low_fibo_tp_main) * 2.618 if direction_fibo_tp_main == "Long" else high_fibo_tp_main - (high_fibo_tp_main - low_fibo_tp_main) * 2.618
                    tp3_main = low_fibo_tp_main + (high_fibo_tp_main - low_fibo_tp_main) * 4.236 if direction_fibo_tp_main == "Long" else high_fibo_tp_main - (high_fibo_tp_main - low_fibo_tp_main) * 4.236
                    st.markdown("##### Take Profit Zones (FIBO):")
                    tp_data_main = {"Zone": ["TP1 (1.618)", "TP2 (2.618)", "TP3 (4.236)"], "Price": [f"{tp1_main:.2f}", f"{tp2_main:.2f}", f"{tp3_main:.2f}"]}
                    st.table(pd.DataFrame(tp_data_main)) 
            except (ValueError, TypeError): st.caption("กรอก High/Low ใน Sidebar ให้ถูกต้องเพื่อคำนวณ TP Zones")
            except Exception as e_tp_main: st.warning(f"ไม่สามารถคำนวณ TP Zones: {e_tp_main}")
        else:
            df_empty_fibo_main_area = pd.DataFrame(columns=["Fibo Level", "Entry", "SL", "Lot", "Risk $"])
            st.dataframe(df_empty_fibo_main_area, hide_index=True, use_container_width=True)
            st.info("กรอกข้อมูลใน Sidebar (FIBO) เพื่อให้ระบบคำนวณและแสดงรายละเอียดแผน")
    elif current_trade_mode == "CUSTOM":
        if custom_entries_list: 
            df_display_custom_main_area = pd.DataFrame(custom_entries_list)
            st.dataframe(df_display_custom_main_area, hide_index=True, use_container_width=True)
            try:
                df_check_rr_main_area = pd.to_numeric(df_display_custom_main_area["RR"], errors='coerce').dropna()
                low_rr_trades_main_area = df_check_rr_main_area[df_check_rr_main_area < 2.0]
                if not low_rr_trades_main_area.empty: st.warning(f"มี {len(low_rr_trades_main_area)} ไม้ที่มี R:R ต่ำกว่า 2.0 ควรพิจารณาปรับปรุง TP/SL")
            except Exception: pass 
        else:
            df_empty_custom_main_area = pd.DataFrame(columns=["Entry", "SL", "TP", "Lot", "Risk $", "RR"])
            st.dataframe(df_empty_custom_main_area, hide_index=True, use_container_width=True)
            st.info("กรอกข้อมูลใน Sidebar (CUSTOM) เพื่อให้ระบบคำนวณและแสดงรายละเอียดแผน")
else:
    st.warning("กรุณาเลือก Active Portfolio ใน Sidebar เพื่อดูและสร้างรายละเอียดแผน")
st.markdown("---")
# ======================= END OF SEC 2 =======================

# ======================= SEC 3: MAIN AREA - CHART VISUALIZER =======================
with st.expander("📈 Chart Visualizer", expanded=True): # UI: ไม่มีเลขนำหน้า
    # Determine chart symbol based on current active plan
    chart_symbol_tv_main = "OANDA:XAUUSD" # Default
    if current_trade_mode == "FIBO" and st.session_state.get("fibo_asset_cfg"):
        chart_symbol_tv_main = st.session_state.get("fibo_asset_cfg")
    elif current_trade_mode == "CUSTOM" and st.session_state.get("custom_asset_cfg"):
        chart_symbol_tv_main = st.session_state.get("custom_asset_cfg")
    
    # Basic formatting for common symbols for TradingView
    if "XAUUSD" in chart_symbol_tv_main.upper(): chart_symbol_tv_main = "OANDA:XAUUSD"
    elif "BTCUSD" in chart_symbol_tv_main.upper(): chart_symbol_tv_main = "BINANCE:BTCUSDT"
    # Add more forex pairs or other symbols as needed:
    # elif "EURUSD" in chart_symbol_tv_main.upper(): chart_symbol_tv_main = "OANDA:EURUSD" 
    # elif "GBPUSD" in chart_symbol_tv_main.upper(): chart_symbol_tv_main = "OANDA:GBPUSD"

    if st.button("Plot Active Plan on Chart", key="widget_main_plot_tv_chart_btn"):
        # In a real scenario, you would pass entry_data_fibo_list or custom_entries_list
        # to a function that generates TradingView drawing commands.
        # For now, just showing the chart.
        st.components.v1.html(f"""
        <div id="tradingview_widget_main_area_div"></div>
        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script type="text/javascript">
        new TradingView.widget({{
            "width": "100%", "height": 600, "symbol": "{chart_symbol_tv_main}", "interval": "15",
            "timezone": "Asia/Bangkok", "theme": "dark", "style": "1", "locale": "th",
            "enable_publishing": false, "withdateranges": true, "allow_symbol_change": true,
            "hide_side_toolbar": false, "details": true, "hotlist": true, "calendar": true,
            "container_id": "tradingview_widget_main_area_div"
        }});
        </script>""", height=620)
    else:
        st.info("กดปุ่ม 'Plot Active Plan on Chart' เพื่อแสดงกราฟ TradingView (สัญลักษณ์จะอิงจากแผนปัจจุบัน)")
st.markdown("---")
# ======================= END OF SEC 3 =======================

# ======================= SEC 4: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
stat_definitions_for_statement = { # Define once for this section
    "Total Net Profit", "Gross Profit", "Gross Loss", "Profit Factor", "Expected Payoff", "Recovery Factor",
    "Sharpe Ratio", "Balance Drawdown Absolute", "Balance Drawdown Maximal", "Balance Drawdown Relative",
    "Total Trades", "Short Trades (won %)", "Long Trades (won %)", "Profit Trades (% of total)", 
    "Loss Trades (% of total)", "Largest profit trade", "Largest loss trade", "Average profit trade", 
    "Average loss trade", "Maximum consecutive wins ($)", "Maximal consecutive profit (count)",
    "Average consecutive wins", "Maximum consecutive losses ($)", "Maximal consecutive loss (count)", 
    "Average consecutive losses"
}
with st.expander("📂 Statement Import & Auto-Mapping", expanded=False): # UI: ไม่มีเลขนำหน้า
    # Session state for this section's data
    if 'df_stmt_current_active_portfolio' not in st.session_state: st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
    if 'all_statement_data_s4' not in st.session_state: st.session_state.all_statement_data_s4 = {} # Use a unique key

    st.subheader("อัปโหลด Statement") # UI: ไม่มีเลขนำหน้า
    uploaded_files_s4_main = st.file_uploader(
        "ลากและวางไฟล์ Statement ที่นี่ (ไฟล์นี้จะถูกเชื่อมกับ Active Portfolio ปัจจุบัน)", 
        type=["xlsx", "csv"], accept_multiple_files=True, key="widget_stmt_uploader_s4"
    )
    
    if 'debug_mode_s4' not in st.session_state: st.session_state.debug_mode_s4 = False
    st.session_state.debug_mode_s4 = st.checkbox("⚙️ เปิดโหมด Debug (Statement Import)", value=st.session_state.debug_mode_s4, key="widget_debug_checkbox_s4")

    if uploaded_files_s4_main:
        if not st.session_state.active_portfolio_name: st.warning("Statement Import: เลือก Active Portfolio ก่อนอัปโหลด")
        else:
            active_p_stmt_s4 = st.session_state.active_portfolio_name
            st.info(f"ไฟล์ที่อัปโหลดจะเชื่อมกับพอร์ต: **{active_p_stmt_s4}**")
            for uploaded_file_item_s4_main in uploaded_files_s4_main:
                st.write(f"กำลังประมวลผล: {uploaded_file_item_s4_main.name}")
                with st.spinner("กำลังแยกส่วนข้อมูล..."):
                    # extract_data_from_statement is defined in SEC 0
                    extracted_s4_main = extract_data_from_statement(uploaded_file_item_s4_main, stat_definitions_for_statement)
                    if extracted_s4_main:
                        st.success(f"พบข้อมูล: {', '.join(extracted_s4_main.keys())}")
                        if 'deals' in extracted_s4_main:
                            df_deals_s4_new_main = extracted_s4_main['deals'].copy()
                            df_deals_s4_new_main['Portfolio'] = active_p_stmt_s4 # Add portfolio identifier
                            st.session_state.df_stmt_current_active_portfolio = df_deals_s4_new_main
                        
                        # Store all extracted parts for this portfolio and file
                        if active_p_stmt_s4 not in st.session_state.all_statement_data_s4: st.session_state.all_statement_data_s4[active_p_stmt_s4] = {}
                        st.session_state.all_statement_data_s4[active_p_stmt_s4][uploaded_file_item_s4_main.name] = extracted_s4_main
                        
                        if 'balance_summary' in extracted_s4_main:
                            st.write(f"#### Balance Summary ({active_p_stmt_s4} - {uploaded_file_item_s4_main.name})")
                            st.dataframe(extracted_s4_main['balance_summary'])
                        if st.session_state.debug_mode_s4:
                            for k_s4, v_df_s4 in extracted_s4_main.items():
                                if k_s4 != 'balance_summary': st.write(f"##### ข้อมูลส่วน: {k_s4.title()}"); st.dataframe(v_df_s4)
                    else: st.warning(f"ไม่พบข้อมูลใน {uploaded_file_item_s4_main.name}")
    else: st.info("ยังไม่มีไฟล์ Statement อัปโหลด")
    st.markdown("---")
    st.subheader(f"Deals ล่าสุดของพอร์ต: {st.session_state.active_portfolio_name or 'N/A'}")
    df_to_display_s4_deals = st.session_state.df_stmt_current_active_portfolio
    if not df_to_display_s4_deals.empty and st.session_state.active_portfolio_name:
        if 'Portfolio' in df_to_display_s4_deals.columns: # Should always be true if processed correctly
            df_filtered_s4_deals = df_to_display_s4_deals[df_to_display_s4_deals['Portfolio'] == st.session_state.active_portfolio_name]
            if not df_filtered_s4_deals.empty: st.dataframe(df_filtered_s4_deals, height=300) # Set height for deals table
            else: st.info(f"ไม่มีข้อมูล Deals สำหรับพอร์ต {st.session_state.active_portfolio_name}")
        else: st.dataframe(df_to_display_s4_deals, height=300) # If no Portfolio column, show as is
    else: st.info(f"ไม่มีข้อมูล Deals สำหรับพอร์ต {st.session_state.active_portfolio_name}")
    if st.button("🗑️ ล้างข้อมูล Statement ปัจจุบันของพอร์ตนี้", key="widget_clear_stmt_s4_btn"):
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame(); st.success("ล้างข้อมูล Statement ปัจจุบันแล้ว"); st.rerun()
st.markdown("---")
# ======================= END OF SEC 4 =======================

# ======================= SEC 5: MAIN AREA - PERFORMANCE DASHBOARD =======================
with st.expander("📊 Performance Dashboard", expanded=True): # UI: ไม่มีเลขนำหน้า
    if not st.session_state.active_portfolio_name: st.warning("เลือก Active Portfolio เพื่อดู Dashboard")
    else:
        active_p_dash_main = st.session_state.active_portfolio_name
        initial_bal_dash_main = acc_balance_sec1 # Use updated acc_balance from active portfolio selection
        st.subheader(f"Dashboard สำหรับพอร์ต: {active_p_dash_main} (Bal: ${initial_bal_dash_main:,.2f})")
        
        # load_data_for_dashboard is defined in SEC 0
        df_dash_main, profit_col_dash_main, asset_col_dash_main, date_col_dash_main = load_data_for_dashboard(active_p_dash_main, initial_bal_dash_main)
        
        tabs_s5_main = st.tabs(["📊 Dashboard", "📈 RR", "📉 Lot Size", "🕒 Time", "🤖 AI Advisor", "⬇️ Export"])
        if df_dash_main.empty: st.info(f"ไม่มีข้อมูลสำหรับ Dashboard ของพอร์ต '{active_p_dash_main}'")
        else:
            with tabs_s5_main[0]: # Dashboard Tab
                if not profit_col_dash_main: st.warning("Dashboard: ไม่พบคอลัมน์ Profit/Risk $ สำหรับสร้างกราฟ")
                else:
                    df_tab_s5_main = df_dash_main.copy()
                    if asset_col_dash_main:
                        assets_unique_s5_main = ["ทั้งหมด"] + sorted(df_tab_s5_main[asset_col_dash_main].dropna().unique())
                        asset_sel_s5_main = st.selectbox(f"Filter by {asset_col_dash_main}", assets_unique_s5_main, key="widget_dash_asset_filter_s5")
                        if asset_sel_s5_main != "ทั้งหมด": df_tab_s5_main = df_tab_s5_main[df_tab_s5_main[asset_col_dash_main] == asset_sel_s5_main]
                    if df_tab_s5_main.empty: st.info("ไม่มีข้อมูลหลัง Filter")
                    else:
                        st.markdown("##### Pie Chart: Win/Loss")
                        wins_s5_main = df_tab_s5_main[df_tab_s5_main[profit_col_dash_main] > 0].shape[0]
                        losses_s5_main = df_tab_s5_main[df_tab_s5_main[profit_col_dash_main] <= 0].shape[0]
                        if wins_s5_main > 0 or losses_s5_main > 0:
                            pie_df_s5_main = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [wins_s5_main, losses_s5_main]})
                            st.plotly_chart(px.pie(pie_df_s5_main, names="Result", values="Count", color="Result", color_discrete_map={"Win":"green", "Loss":"red"}), use_container_width=True)
                        else: st.info("ไม่มีข้อมูล Win/Loss")
                        if date_col_dash_main:
                            st.markdown("##### Bar Chart: กำไร/ขาดทุนแต่ละวัน")
                            df_bar_chart_s5_main = df_tab_s5_main.copy()
                            df_bar_chart_s5_main["TradeDate"] = df_bar_chart_s5_main[date_col_dash_main].dt.date
                            bar_grouped_s5_main = df_bar_chart_s5_main.groupby("TradeDate")[profit_col_dash_main].sum().reset_index(name="P/L")
                            if not bar_grouped_s5_main.empty: st.plotly_chart(px.bar(bar_grouped_s5_main, x="TradeDate", y="P/L", color="P/L", color_continuous_scale=["red","lightcoral","lightgreen","green"]), use_container_width=True)
                            else: st.info("ไม่มีข้อมูลสำหรับ Bar Chart")
                            st.markdown("##### Timeline: Balance Curve")
                            df_bal_s5_main = df_tab_s5_main.copy().sort_values(by=date_col_dash_main)
                            df_bal_s5_main["Balance"] = initial_bal_dash_main + df_bal_s5_main[profit_col_dash_main].cumsum()
                            if not df_bal_s5_main.empty: st.plotly_chart(px.line(df_bal_s5_main, x=date_col_dash_main, y="Balance", markers=True, title="Balance Curve"), use_container_width=True)
                            else: st.info("ไม่มีข้อมูลสำหรับ Balance Curve")
                        else: st.warning("ไม่พบคอลัมน์วันที่สำหรับ Bar Chart และ Balance Curve")
            with tabs_s5_main[1]: # RR
                if "RR" in df_dash_main.columns and df_dash_main["RR"].notna().any():
                    if not df_dash_main["RR"].dropna().empty: st.plotly_chart(px.histogram(df_dash_main["RR"].dropna(), nbins=20, title="RR Distribution"), use_container_width=True)
                    else: st.info("ไม่มีข้อมูล RR")
                else: st.warning("ไม่พบคอลัมน์ 'RR'")
            with tabs_s5_main[2]: # Lot Size
                if "Lot" in df_dash_main.columns and date_col_dash_main and df_dash_main["Lot"].notna().any():
                    if not df_dash_main["Lot"].dropna().empty: st.plotly_chart(px.line(df_dash_main.dropna(subset=[date_col_dash_main, "Lot"]).sort_values(by=date_col_dash_main), x=date_col_dash_main, y="Lot", markers=True, title="Lot Size Over Time"), use_container_width=True)
                    else: st.info("ไม่มีข้อมูล Lot หรือ วันที่")
                else: st.warning("ไม่พบคอลัมน์ 'Lot' หรือ วันที่")
            with tabs_s5_main[3]: # Time Analysis
                if date_col_dash_main and profit_col_dash_main:
                    df_time_s5_main = df_dash_main.copy()
                    df_time_s5_main["Weekday"] = df_time_s5_main[date_col_dash_main].dt.day_name()
                    order_days_s5 = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    weekday_profit_s5_main = df_time_s5_main.groupby("Weekday")[profit_col_dash_main].sum().reindex(order_days_s5).fillna(0.0).reset_index()
                    if not weekday_profit_s5_main.empty: st.plotly_chart(px.bar(weekday_profit_s5_main, x="Weekday", y=profit_col_dash_main, title="P/L by Weekday"), use_container_width=True)
                    else: st.info("ไม่มีข้อมูลวิเคราะห์ตามวัน")
                else: st.warning("ไม่พบคอลัมน์ วันที่ หรือ Profit/Risk $")
            with tabs_s5_main[4]: # AI Advisor
                st.subheader("🤖 AI Advisor (Gemini)")
                if 'google_api_key_s5_dash_cfg' not in st.session_state: st.session_state.google_api_key_s5_dash_cfg = "" 
                st.session_state.google_api_key_s5_dash_cfg = st.text_input("ใส่ Google API Key (Dashboard):", type="password", value=st.session_state.google_api_key_s5_dash_cfg, key="widget_gemini_api_s5_dash_input")
                if st.button("วิเคราะห์โดย AI (Dashboard)", key="widget_ai_analyze_s5_dash_btn"):
                    if not st.session_state.google_api_key_s5_dash_cfg: st.warning("ใส่ Google API Key ก่อน")
                    elif not profit_col_dash_main or df_dash_main.empty: st.warning("ไม่มีข้อมูลให้ AI วิเคราะห์")
                    else:
                        try:
                            genai.configure(api_key=st.session_state.google_api_key_s5_dash_cfg)
                            model_s5_dash = genai.GenerativeModel('gemini-pro')
                            total_t_s5 = df_dash_main.shape[0]; win_t_s5 = df_dash_main[df_dash_main[profit_col_dash_main] > 0].shape[0]
                            wr_s5 = (100*win_t_s5/total_t_s5) if total_t_s5 > 0 else 0; g_pl_s5 = df_dash_main[profit_col_dash_main].sum()
                            avg_rr_s5 = pd.to_numeric(df_dash_main.get('RR', pd.Series(dtype='float')), errors='coerce').mean()
                            prompt_txt_s5 = f"วิเคราะห์ผลเทรดพอร์ต '{active_p_dash_main}': Trades: {total_t_s5}, Winrate: {wr_s5:.2f}%, P/L: {g_pl_s5:,.2f}, Avg RR: {avg_rr_s5 if pd.notna(avg_rr_s5) else 'N/A'}. บอกจุดแข็ง, จุดอ่อน, แนะนำปรับปรุง (ภาษาไทย)"
                            with st.spinner("AI กำลังคิด..."): response_s5 = model_s5_dash.generate_content(prompt_txt_s5)
                            st.markdown("--- \n**AI Says:**"); st.markdown(response_s5.text)
                        except Exception as e_ai_dash_run: st.error(f"Gemini AI Error: {e_ai_dash_run}")
            with tabs_s5_main[5]: # Export
                if not df_dash_main.empty:
                    st.download_button("Download Data (CSV)", df_dash_main.to_csv(index=False).encode('utf-8'), f"dash_report_{active_p_dash_main.replace(' ','_') if active_p_dash_main else 'data'}.csv", "text/csv", key="widget_export_dash_s5_btn")
                else: st.info("ไม่มีข้อมูลให้ Export")
st.markdown("---")
# ======================= END OF SEC 5 =======================

# ======================= SEC 6: MAIN AREA - TRADE LOG VIEWER =======================
with st.expander("📚 Trade Log Viewer (แผนเทรดที่บันทึกไว้)", expanded=False): # UI: ไม่มีเลขนำหน้า
    if not st.session_state.active_portfolio_name: st.warning("เลือก Active Portfolio เพื่อดู Log")
    else:
        st.subheader(f"Log สำหรับพอร์ต: {st.session_state.active_portfolio_name}")
        if os.path.exists(log_file):
            try:
                df_log_all_s6_main = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all_s6_main.columns: st.warning("Log file ไม่มีคอลัมน์ 'Portfolio'")
                else:
                    df_show_s6_main = df_log_all_s6_main[df_log_all_s6_main["Portfolio"] == st.session_state.active_portfolio_name].copy()
                    if df_show_s6_main.empty: st.info(f"ไม่พบ Log สำหรับพอร์ต '{st.session_state.active_portfolio_name}'.")
                    else:
                        c1_s6,c2_s6,c3_s6 = st.columns(3)
                        mf_s6 = c1_s6.selectbox("Mode", ["ทั้งหมด"]+sorted(df_show_s6_main["Mode"].unique().tolist()),key="widget_log_mode_s6")
                        af_s6 = c2_s6.selectbox("Asset",["ทั้งหมด"]+sorted(df_show_s6_main["Asset"].unique().tolist()),key="widget_log_asset_s6")
                        df_s6_date_filter = c3_s6.text_input("ค้นหาวันที่ (YYYY-MM-DD)",key="widget_log_date_s6")
                        df_filtered_s6_main = df_show_s6_main.copy()
                        if mf_s6!="ทั้งหมด": df_filtered_s6_main = df_filtered_s6_main[df_filtered_s6_main["Mode"]==mf_s6]
                        if af_s6!="ทั้งหมด": df_filtered_s6_main = df_filtered_s6_main[df_filtered_s6_main["Asset"]==af_s6]
                        if df_s6_date_filter: df_filtered_s6_main = df_filtered_s6_main[df_filtered_s6_main["Timestamp"].str.contains(df_s6_date_filter,na=False)]
                        st.dataframe(df_filtered_s6_main, use_container_width=True, hide_index=True)
            except Exception as e_log_s6_read: st.error(f"อ่าน Log ไม่ได้ (SEC 6): {e_log_s6_read}")
        else: st.info(f"ยังไม่มี Log File ({log_file})")
st.markdown("---")
# ======================= END OF SEC 6 =======================

# ======================= SEC 9 (เดิมคือ SEC END): END OF APP =======================
# (ในโครงสร้างใหม่ อาจจะเป็น SEC 7 หรือ 8 ถ้ามี AI Assistant แยก)
st.caption("Ultimate Trading Dashboard - End of Application")
# ======================= END OF APP =======================
