# ======================= main.py (เริ่ม SEC 0 - อ้างอิง Master Version จาก Drive) =======================
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl # สำหรับ engine='openpyxl'
import os
from datetime import datetime, timedelta
import plotly.express as px
import google.generativeai as genai # สำหรับ AI Advisor (ถ้าใช้)
# import gspread # ถ้าจะใช้ Google Sheets ค่อยเปิดใช้งาน (จากโค้ดเดิมของคุณ)

# ======================= SEC 0: INITIAL SETUP & ALL FUNCTION DEFINITIONS =======================

# 0.1. Page Config
st.set_page_config(
    page_title="Ultimate Trading Dashboard", 
    page_icon="📊",
    layout="wide"
)

# 0.2. Initial Variables & File Paths
# acc_balance จะถูกกำหนดค่าแบบไดนามิกจากพอร์ตที่เลือกใน SEC 1
# default_initial_balance = 10000.0 
log_file = "trade_log.csv"
PORTFOLIO_FILE = 'portfolios.csv'

# 0.3. Google API Key Placeholder (ผู้ใช้จะกรอกผ่าน UI หรือ st.secrets)
# GOOGLE_API_KEY_FROM_USER = "" # จะถูกจัดการในส่วน UI ที่เรียกใช้ AI

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
def get_today_drawdown_for_active_portfolio(log_file_path, active_portfolio):
    if not os.path.exists(log_file_path) or active_portfolio is None:
        return 0.0
    try:
        df = pd.read_csv(log_file_path)
        if "Portfolio" not in df.columns: return 0.0
        df_portfolio = df[df["Portfolio"] == active_portfolio]
        if df_portfolio.empty: return 0.0

        today_str = datetime.now().strftime("%Y-%m-%d")
        if "Timestamp" not in df_portfolio.columns or "Risk $" not in df_portfolio.columns: return 0.0
        
        df_portfolio["Risk $"] = pd.to_numeric(df_portfolio["Risk $"], errors='coerce').fillna(0.0)
        df_today = df_portfolio[df_portfolio["Timestamp"].str.startswith(today_str)]
        return df_today["Risk $"].sum()
    except FileNotFoundError: return 0.0
    except Exception as e:
        # st.error(f"SEC 0.4.2: Error in get_today_drawdown: {e}")
        return 0.0

def get_performance_for_active_portfolio(log_file_path, active_portfolio, current_initial_balance, mode="week"):
    if not os.path.exists(log_file_path) or active_portfolio is None:
        return 0.0, 0.0, 0 # winrate, gain_or_loss, total_trades
    try:
        df = pd.read_csv(log_file_path)
        if "Portfolio" not in df.columns: return 0.0,0.0,0
        df_portfolio = df[df["Portfolio"] == active_portfolio]
        if df_portfolio.empty: return 0.0,0.0,0

        if "Timestamp" not in df_portfolio.columns or "Risk $" not in df_portfolio.columns: return 0.0, 0.0, 0
        df_portfolio["Risk $"] = pd.to_numeric(df_portfolio["Risk $"], errors='coerce').fillna(0.0)
            
        now = datetime.now()
        if mode == "week":
            start_date_str = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        else: # month
            start_date_str = now.strftime("%Y-%m-01")
        
        df_period = df_portfolio[df_portfolio["Timestamp"] >= start_date_str]
        if df_period.empty: return 0.0,0.0,0

        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0] 
        total_trades_period = win + loss
        
        winrate = (100 * win / total_trades_period) if total_trades_period > 0 else 0.0
        gain_or_loss = df_period["Risk $"].sum() 
        return winrate, gain_or_loss, total_trades_period
    except FileNotFoundError: return 0.0,0.0,0
    except Exception as e:
        # st.error(f"SEC 0.4.2: Error in get_performance: {e}")
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
    # Ensure all expected columns exist, add if not (helps prevent errors with pd.concat)
    expected_cols = ["Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"] # Add all possible cols from FIBO and CUSTOM
    for col in expected_cols:
        if col not in df_to_write.columns:
            df_to_write[col] = np.nan # Or appropriate default

    df_to_write["Mode"] = trade_mode_arg
    df_to_write["Asset"] = asset_arg
    df_to_write["Risk %"] = risk_pct_arg
    df_to_write["Direction"] = direction_arg
    df_to_write["Portfolio"] = active_portfolio_arg
    df_to_write["Timestamp"] = now_str
    
    try:
        if os.path.exists(log_file):
            df_old_log = pd.read_csv(log_file)
            # Ensure old log also has all expected columns before concat
            for col in df_to_write.columns: # Check against the new dataframe's columns
                if col not in df_old_log.columns:
                    df_old_log[col] = np.nan
            # Reorder columns to match if necessary or ensure consistent order
            df_final_log = pd.concat([df_old_log, df_to_write], ignore_index=True)
        else:
            df_final_log = df_to_write
        df_final_log.to_csv(log_file, index=False)
        st.sidebar.success(f"บันทึกแผน ({trade_mode_arg}) สำหรับพอร์ต '{active_portfolio_arg}' สำเร็จ!")
    except Exception as e:
        st.sidebar.error(f"SEC 0.4.3: Save Plan ไม่สำเร็จ: {e}")

# 0.4.4. Statement Extraction Function
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
        if keyword not in section_starts:
            for r_idx, row in df_raw.iterrows():
                if row.astype(str).str.contains(keyword, case=False, regex=False).any():
                    actual_key = "Deals" if keyword == "History" else keyword
                    if actual_key not in section_starts:
                        section_starts[actual_key] = r_idx
                    break 
    
    extracted_data = {}
    sorted_sections = sorted(section_starts.items(), key=lambda item: item[1])

    tabular_keywords = ["Positions", "Orders", "Deals"]
    for i, (section_name, start_row) in enumerate(sorted_sections):
        if section_name not in tabular_keywords:
            continue
        
        header_row_idx = start_row + 1
        while header_row_idx < len(df_raw) and df_raw.iloc[header_row_idx].isnull().all():
            header_row_idx += 1
        
        if header_row_idx < len(df_raw):
            headers = [str(h).strip() for h in df_raw.iloc[header_row_idx] if pd.notna(h) and str(h).strip() != '']
            data_start_row = header_row_idx + 1
            
            end_row = len(df_raw)
            if i + 1 < len(sorted_sections):
                end_row = sorted_sections[i+1][1]
            
            df_section = df_raw.iloc[data_start_row:end_row].copy().dropna(how='all')
            
            if not df_section.empty:
                num_data_cols = df_section.shape[1]
                final_headers = headers[:num_data_cols]
                if len(final_headers) < num_data_cols:
                    final_headers.extend([f'Unnamed_Stmt_{j}' for j in range(len(final_headers), num_data_cols)])
                
                df_section.columns = final_headers
                # Convert known numeric columns to numeric, coercing errors
                for col_to_convert in ['Volume', 'Price', 'S / L', 'T / P', 'Commission', 'Swap', 'Profit', 'Balance']:
                    if col_to_convert in df_section.columns:
                        df_section[col_to_convert] = pd.to_numeric(df_section[col_to_convert], errors='coerce') # .fillna(0) might be too aggressive here

                extracted_data[section_name.lower()] = df_section

    if "Results" in section_starts:
        results_stats = {}
        start_row_res = section_starts["Results"]
        results_df_scan_area = df_raw.iloc[start_row_res : start_row_res + 20] 
        
        for _, row_res in results_df_scan_area.iterrows():
            for c_idx_res, cell_res in enumerate(row_res):
                if pd.notna(cell_res):
                    label_res = str(cell_res).strip().replace(':', '')
                    if label_res in stat_definitions_arg:
                        for k_val_offset in range(1, 5): 
                            if (c_idx_res + k_val_offset) < len(row_res):
                                value_candidate = row_res.iloc[c_idx_res + k_val_offset]
                                if pd.notna(value_candidate) and str(value_candidate).strip() != "":
                                    clean_value = str(value_candidate).split('(')[0].strip().replace(' ', '')
                                    results_stats[label_res] = clean_value
                                    break 
                        # break # Keep allowing to find multiple stats on same row if possible
        if results_stats:
            df_balance_summary = pd.DataFrame(list(results_stats.items()), columns=['Metric', 'Value'])
            # Attempt to convert 'Value' column to numeric if possible
            df_balance_summary['Value'] = pd.to_numeric(df_balance_summary['Value'], errors='ignore')
            extracted_data["balance_summary"] = df_balance_summary
            
    return extracted_data

# 0.4.5. Dashboard Data Loading Function
def load_data_for_dashboard(active_portfolio_arg, current_portfolio_initial_balance):
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Log File (แผนเทรด)", "Statement Import (ผลเทรดจริง)"],
        index=0, 
        key="main_dashboard_source_selector" # Ensure unique key
    )
    df_dashboard = pd.DataFrame()
    profit_col_identified, asset_col_identified, date_col_identified = None, None, None

    if source_option == "Log File (แผนเทรด)":
        if not active_portfolio_arg:
            st.warning("Dashboard: กรุณาเลือก Active Portfolio")
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
            st.warning("Dashboard: กรุณาเลือก Active Portfolio")
            return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified
        
        df_from_session = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame())
        if not df_from_session.empty:
            df_dashboard = df_from_session.copy()
            if 'Portfolio' in df_dashboard.columns: 
                df_dashboard = df_dashboard[df_dashboard['Portfolio'] == active_portfolio_arg]
        
        if df_dashboard.empty:
             st.info(f"Dashboard: ไม่มีข้อมูล Statement สำหรับพอร์ต '{active_portfolio_arg}' (โปรดอัปโหลดในส่วน Statement Import)")

    # Data Cleaning and Column Identification for Dashboard
    if not df_dashboard.empty:
        # Ensure 'Profit' or 'Risk $' column is numeric and identified
        if 'Profit' in df_dashboard.columns:
            df_dashboard['Profit_temp'] = pd.to_numeric(df_dashboard['Profit'], errors='coerce')
            if df_dashboard['Profit_temp'].notna().any() and df_dashboard['Profit_temp'].abs().sum() > 0:
                 df_dashboard['Profit'] = df_dashboard['Profit_temp'].fillna(0.0)
                 profit_col_identified = 'Profit'
            else: # If 'Profit' is all NaN or zeros, try 'Risk $'
                 if 'Risk $' in df_dashboard.columns:
                    df_dashboard['Risk $'] = pd.to_numeric(df_dashboard['Risk $'], errors='coerce').fillna(0.0)
                    profit_col_identified = 'Risk $'
            df_dashboard.drop(columns=['Profit_temp'], inplace=True, errors='ignore')
        elif 'Risk $' in df_dashboard.columns: # If 'Profit' col doesn't exist at all
            df_dashboard['Risk $'] = pd.to_numeric(df_dashboard['Risk $'], errors='coerce').fillna(0.0)
            profit_col_identified = 'Risk $'
        
        # Clean other potential numeric columns
        for col_numeric in ['RR', 'Lot', 'Commission', 'Swap', 'Volume', 'Price', 'S / L', 'T / P']:
            if col_numeric in df_dashboard.columns:
                df_dashboard[col_numeric] = pd.to_numeric(df_dashboard[col_numeric], errors='coerce').fillna(0.0)

        # Identify Asset column
        if 'Asset' in df_dashboard.columns: asset_col_identified = 'Asset'
        elif 'Symbol' in df_dashboard.columns: asset_col_identified = 'Symbol'

        # Identify and convert Date column
        date_col_options = [col for col in ["Timestamp", "Time", "Date", "Open Time", "Close Time"] if col in df_dashboard.columns]
        for col_date in date_col_options:
            try:
                df_dashboard[col_date] = pd.to_datetime(df_dashboard[col_date], errors='coerce')
                if df_dashboard[col_date].notna().any():
                    date_col_identified = col_date
                    break
            except Exception: continue
    
    return df_dashboard, profit_col_identified, asset_col_identified, date_col_identified

# 0.4.6 (จากโค้ดเดิมของคุณ อาจจะมี Google Sheets functions - ถ้าไม่ใช้ ให้ comment ไว้)
# def get_gspread_client():
#     # ...
#     return None

# def load_statement_from_gsheets(): # ฟังก์ชันนี้อาจจะซ้ำซ้อนกับ extract_data_from_statement ถ้าใช้ไฟล์อัปโหลด
#     # ...
#     return {}

# def save_statement_to_gsheets(df_to_save):
#     # ...
#     pass

# ======================= END OF SEC 0 =======================

# ======================= SEC 1: SIDEBAR - CORE CONTROLS, PORTFOLIO, INPUTS, RISK MGMT =======================

# --- 1.1. Portfolio Selection & Management (UI in Sidebar) ---
# (ฟังก์ชัน load_portfolios และ save_portfolios ถูกประกาศไว้ใน SEC 0.4.1 แล้ว)
portfolios_df = load_portfolios() # โหลดข้อมูลพอร์ต (ทำซ้ำเพื่อให้แน่ใจว่า acc_balance ถูกต้อง)
acc_balance = 10000.0 # Default balance, will be updated by selected portfolio

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

if not portfolios_df.empty:
    portfolio_names_list_sec1 = portfolios_df['portfolio_name'].tolist() # ใช้ชื่อตัวแปรใหม่
    
    current_active_portfolio_name_sb_sec1 = st.session_state.get('active_portfolio_name', None)
    if current_active_portfolio_name_sb_sec1 not in portfolio_names_list_sec1:
        st.session_state.active_portfolio_name = portfolio_names_list_sec1[0] if portfolio_names_list_sec1 else None
    
    try:
        if st.session_state.active_portfolio_name and st.session_state.active_portfolio_name in portfolio_names_list_sec1:
            current_index_sb_sec1 = portfolio_names_list_sec1.index(st.session_state.active_portfolio_name)
        elif portfolio_names_list_sec1: 
            current_index_sb_sec1 = 0
            st.session_state.active_portfolio_name = portfolio_names_list_sec1[0]
        else: 
            current_index_sb_sec1 = 0 
    except ValueError:
        current_index_sb_sec1 = 0 
        if portfolio_names_list_sec1:
             st.session_state.active_portfolio_name = portfolio_names_list_sec1[0]

    selected_portfolio_name_sb_sec1 = st.sidebar.selectbox(
        "เลือกพอร์ต:",
        options=portfolio_names_list_sec1,
        index=current_index_sb_sec1,
        key='sidebar_portfolio_selector_widget_sec1' 
    )
    
    if selected_portfolio_name_sb_sec1 != st.session_state.get('active_portfolio_name'):
        st.session_state.active_portfolio_name = selected_portfolio_name_sb_sec1
        st.rerun() 

    if st.session_state.active_portfolio_name:
        active_portfolio_details_sb_sec1 = portfolios_df[portfolios_df['portfolio_name'] == st.session_state.active_portfolio_name]
        if not active_portfolio_details_sb_sec1.empty:
            acc_balance = float(active_portfolio_details_sb_sec1['initial_balance'].iloc[0])
            st.sidebar.success(f"Active: **{st.session_state.active_portfolio_name}** (Bal: ${acc_balance:,.2f})")
        else:
            st.sidebar.error("ไม่พบรายละเอียดพอร์ตที่เลือก, กำลังใช้ค่าเริ่มต้น")
            st.session_state.active_portfolio_name = None 
            acc_balance = 10000.0 
else:
    st.sidebar.info("ยังไม่มีพอร์ต กรุณาเพิ่มพอร์ตใน 'จัดการพอร์ต'")
    st.session_state.active_portfolio_name = None
    acc_balance = 10000.0

with st.sidebar.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=False):
    st.subheader("พอร์ตทั้งหมดของคุณ")
    portfolios_df_display_sec1 = load_portfolios() # โหลดล่าสุดเพื่อแสดงผล
    st.dataframe(portfolios_df_display_sec1, use_container_width=True, hide_index=True)

    st.subheader("➕ เพิ่มพอร์ตใหม่")
    with st.form("sidebar_new_portfolio_form_sec1", clear_on_submit=True): 
        new_p_name_sidebar_sec1 = st.text_input("ชื่อพอร์ต")
        new_p_bal_sidebar_sec1 = st.number_input("บาลานซ์เริ่มต้น ($)", min_value=0.0, value=10000.0, step=100.0, format="%.2f")
        
        if st.form_submit_button("💾 บันทึกพอร์ตใหม่"):
            if not new_p_name_sidebar_sec1: st.warning("กรุณาใส่ชื่อพอร์ต")
            elif new_p_name_sidebar_sec1 in portfolios_df_display_sec1['portfolio_name'].values: st.error(f"ชื่อพอร์ต '{new_p_name_sidebar_sec1}' มีอยู่แล้ว")
            else:
                current_portfolios_df_before_add_sec1 = load_portfolios()
                if current_portfolios_df_before_add_sec1.empty or 'portfolio_id' not in current_portfolios_df_before_add_sec1.columns or current_portfolios_df_before_add_sec1['portfolio_id'].isnull().all():
                    new_id_sidebar_sec1 = 1
                else:
                    new_id_sidebar_sec1 = current_portfolios_df_before_add_sec1['portfolio_id'].max() + 1 if pd.notna(current_portfolios_df_before_add_sec1['portfolio_id'].max()) else 1
                
                new_p_data_sidebar_sec1 = pd.DataFrame([{'portfolio_id': int(new_id_sidebar_sec1), 'portfolio_name': new_p_name_sidebar_sec1, 'initial_balance': new_p_bal_sidebar_sec1, 'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                updated_portfolios_df_sidebar_sec1 = pd.concat([current_portfolios_df_before_add_sec1, new_p_data_sidebar_sec1], ignore_index=True)
                save_portfolios(updated_portfolios_df_sidebar_sec1)
                st.success(f"เพิ่มพอร์ต '{new_p_name_sidebar_sec1}' สำเร็จ!")
                if st.session_state.active_portfolio_name is None and not updated_portfolios_df_sidebar_sec1.empty:
                    st.session_state.active_portfolio_name = new_p_name_sidebar_sec1
                st.rerun()
st.sidebar.markdown("---")

# --- Main Trade Setup ---
st.sidebar.header("Trade Setup & Controls") # ไม่มีหมายเลข
if 'sidebar_dd_limit_pct_val_config_mainsetup' not in st.session_state: st.session_state.sidebar_dd_limit_pct_val_config_mainsetup = 2.0
drawdown_limit_pct_input = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)", 
    min_value=0.1, max_value=20.0, 
    value=st.session_state.sidebar_dd_limit_pct_val_config_mainsetup, 
    step=0.1, format="%.1f", 
    key="sidebar_dd_limit_widget_mainsetup" 
)
st.session_state.sidebar_dd_limit_pct_val_config_mainsetup = drawdown_limit_pct_input

if 'sidebar_current_trade_mode_config_mainsetup' not in st.session_state: st.session_state.sidebar_current_trade_mode_config_mainsetup = "FIBO"
current_trade_mode = st.sidebar.radio(
    "Trade Mode", ["FIBO", "CUSTOM"], 
    index=["FIBO", "CUSTOM"].index(st.session_state.sidebar_current_trade_mode_config_mainsetup),
    horizontal=True, key="sidebar_trade_mode_widget_mainsetup"
)
st.session_state.sidebar_current_trade_mode_config_mainsetup = current_trade_mode

if st.sidebar.button("🔄 Reset Form", key="sidebar_btn_reset_form_overall"):
    keys_to_preserve_on_reset_overall = {
        'active_portfolio_name', 'sidebar_portfolio_selector_widget_sec1', 
        'sidebar_dd_limit_pct_val_config_mainsetup', 'sidebar_dd_limit_widget_mainsetup',
        'sidebar_current_trade_mode_config_mainsetup', 'sidebar_trade_mode_widget_mainsetup'
    }
    for k_scale_cfg_overall in ['scaling_step_cfg_val_main', 'scaling_min_risk_cfg_val_main', 'scaling_max_risk_cfg_val_main', 'scaling_mode_cfg_radio_main']:
        if k_scale_cfg_overall in st.session_state: keys_to_preserve_on_reset_overall.add(k_scale_cfg_overall)
    for key_in_state_overall in list(st.session_state.keys()):
        if key_in_state_overall not in keys_to_preserve_on_reset_overall:
            if key_in_state_overall.startswith('fibo_') or key_in_state_overall.startswith('custom_'):
                del st.session_state[key_in_state_overall]
    if "fibo_flags_inputs_list_config_main" in st.session_state: st.session_state.fibo_flags_inputs_list_config_main = [True] * 5
    st.rerun()

# --- FIBO Input Zone ---
entry_data_fibo_list = [] 
if current_trade_mode == "FIBO":
    st.sidebar.subheader("FIBO Mode Inputs") # ไม่มีหมายเลข
    
    # Asset & Risk % in one row
    col1_fibo, col2_fibo = st.sidebar.columns(2)
    with col1_fibo:
        if 'fibo_asset_val_cfg_main' not in st.session_state: st.session_state.fibo_asset_val_cfg_main = "XAUUSD"
        st.session_state.fibo_asset_val_cfg_main = st.text_input("Asset", value=st.session_state.fibo_asset_val_cfg_main, key="fibo_asset_widget_main")
    with col2_fibo:
        if 'fibo_risk_val_cfg_main' not in st.session_state: st.session_state.fibo_risk_val_cfg_main = 1.0
        st.session_state.fibo_risk_val_cfg_main = st.number_input("Risk %", min_value=0.01, value=st.session_state.fibo_risk_val_cfg_main, step=0.01, key="fibo_risk_widget_main")

    # Direction
    if 'fibo_direction_val_cfg_main' not in st.session_state: st.session_state.fibo_direction_val_cfg_main = "Long"
    st.session_state.fibo_direction_val_cfg_main = st.sidebar.radio("Direction", ["Long", "Short"], index=["Long", "Short"].index(st.session_state.fibo_direction_val_cfg_main), horizontal=True, key="fibo_direction_widget_main")

    # High & Low in one row
    col_h_fibo, col_l_fibo = st.sidebar.columns(2)
    with col_h_fibo:
        if 'fibo_high_val_cfg_main' not in st.session_state: st.session_state.fibo_high_val_cfg_main = ""
        st.session_state.fibo_high_val_cfg_main = st.text_input("High", value=st.session_state.fibo_high_val_cfg_main, key="fibo_high_widget_main")
    with col_l_fibo:
        if 'fibo_low_val_cfg_main' not in st.session_state: st.session_state.fibo_low_val_cfg_main = ""
        st.session_state.fibo_low_val_cfg_main = st.text_input("Low", value=st.session_state.fibo_low_val_cfg_main, key="fibo_low_widget_main")
    
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibo_levels_const_list_val_main = [0.114, 0.25, 0.382, 0.5, 0.618] 
    if "fibo_flags_inputs_list_config_main" not in st.session_state: st.session_state.fibo_flags_inputs_list_config_main = [True] * len(fibo_levels_const_list_val_main)
    
    cols_fibo_cb_list_val_main = st.sidebar.columns(len(fibo_levels_const_list_val_main))
    temp_fibo_flags_main = st.session_state.fibo_flags_inputs_list_config_main[:] 
    for i, col_cb_fibo_item_val_main in enumerate(cols_fibo_cb_list_val_main): 
        temp_fibo_flags_main[i] = col_cb_fibo_item_val_main.checkbox(f"{fibo_levels_const_list_val_main[i]:.3f}", value=temp_fibo_flags_main[i], key=f"fibo_level_cb_widget_main_{i}")
    st.session_state.fibo_flags_inputs_list_config_main = temp_fibo_flags_main
    
    try:
        high_fibo_calc_val_main = float(st.session_state.fibo_high_val_cfg_main)
        low_fibo_calc_val_main = float(st.session_state.fibo_low_val_cfg_main)
        current_risk_pct_fibo_main = st.session_state.fibo_risk_val_cfg_main
        current_direction_fibo_main = st.session_state.fibo_direction_val_cfg_main
        if high_fibo_calc_val_main > low_fibo_calc_val_main and acc_balance > 0:
            selected_fibs_calc_val_main = [fibo_levels_const_list_val_main[i] for i, sel_main in enumerate(st.session_state.fibo_flags_inputs_list_config_main) if sel_main]
            n_selected_fibs_calc_val_main = len(selected_fibs_calc_val_main)
            risk_dollar_total_calc_val_main = acc_balance * (current_risk_pct_fibo_main / 100)
            risk_dollar_per_entry_calc_val_main = risk_dollar_total_calc_val_main / n_selected_fibs_calc_val_main if n_selected_fibs_calc_val_main > 0 else 0
            for fib_level_item_calc_val_main in selected_fibs_calc_val_main:
                entry_p_calc_val_main = low_fibo_calc_val_main + (high_fibo_calc_val_main - low_fibo_calc_val_main) * fib_level_item_calc_val_main if current_direction_fibo_main == "Long" else high_fibo_calc_val_main - (high_fibo_calc_val_main - low_fibo_calc_val_main) * fib_level_item_calc_val_main
                sl_p_calc_val_main = low_fibo_calc_val_main if current_direction_fibo_main == "Long" else high_fibo_calc_val_main
                stop_p_calc_val_main = abs(entry_p_calc_val_main - sl_p_calc_val_main)
                lot_calc_val_main = (risk_dollar_per_entry_calc_val_main / stop_p_calc_val_main) if stop_p_calc_val_main > 0 else 0.0
                entry_data_fibo_list.append({"Fibo Level": f"{fib_level_item_calc_val_main:.3f}", "Entry": f"{entry_p_calc_val_main:.2f}", "SL": f"{sl_p_calc_val_main:.2f}", "Lot": f"{lot_calc_val_main:.2f}", "Risk $": f"{lot_calc_val_main * stop_p_calc_val_main:.2f}"})
    except (ValueError, TypeError, ZeroDivisionError): pass 
    save_fibo_button = st.sidebar.button("💾 Save Plan (FIBO)", key="sidebar_btn_save_fibo_final")

# --- CUSTOM Input Zone ---
custom_entries_list = [] 
if current_trade_mode == "CUSTOM":
    st.sidebar.subheader("CUSTOM Mode Inputs") # ไม่มีหมายเลข
    col1_custom, col2_custom = st.sidebar.columns(2)
    with col1_custom:
        if 'custom_asset_val_cfg_main' not in st.session_state: st.session_state.custom_asset_val_cfg_main = "XAUUSD"
        st.session_state.custom_asset_val_cfg_main = st.text_input("Asset", value=st.session_state.custom_asset_val_cfg_main, key="custom_asset_widget_main")
    with col2_custom:
        if 'custom_risk_val_cfg_main' not in st.session_state: st.session_state.custom_risk_val_cfg_main = 1.0
        st.session_state.custom_risk_val_cfg_main = st.number_input("Risk %", min_value=0.01, value=st.session_state.custom_risk_val_cfg_main, step=0.01, key="custom_risk_widget_main")
    
    if 'custom_n_entry_val_cfg_main' not in st.session_state: st.session_state.custom_n_entry_val_cfg_main = 1
    st.session_state.custom_n_entry_val_cfg_main = st.sidebar.number_input("จำนวนไม้", min_value=1, value=st.session_state.custom_n_entry_val_cfg_main, step=1, key="custom_n_entry_widget_main")
    current_risk_pct_custom_main = st.session_state.custom_risk_val_cfg_main
    num_entries_custom_val_main = int(st.session_state.custom_n_entry_val_cfg_main)

    for i_cust_main in range(num_entries_custom_val_main):
        st.sidebar.markdown(f"--- ไม้ที่ {i_cust_main+1} ---")
        if f"custom_entry_val_widget_main_{i_cust_main}" not in st.session_state: st.session_state[f"custom_entry_val_widget_main_{i_cust_main}"] = "0.0"
        if f"custom_sl_val_widget_main_{i_cust_main}" not in st.session_state: st.session_state[f"custom_sl_val_widget_main_{i_cust_main}"] = "0.0"
        if f"custom_tp_val_widget_main_{i_cust_main}" not in st.session_state: st.session_state[f"custom_tp_val_widget_main_{i_cust_main}"] = "0.0"

        e_cust_val_main = st.sidebar.text_input(f"Entry {i_cust_main+1}", value=st.session_state[f"custom_entry_val_widget_main_{i_cust_main}"], key=f"custom_entry_val_widget_main_{i_cust_main}")
        s_cust_val_main = st.sidebar.text_input(f"SL {i_cust_main+1}", value=st.session_state[f"custom_sl_val_widget_main_{i_cust_main}"], key=f"custom_sl_val_widget_main_{i_cust_main}")
        t_cust_val_main = st.sidebar.text_input(f"TP {i_cust_main+1}", value=st.session_state[f"custom_tp_val_widget_main_{i_cust_main}"], key=f"custom_tp_val_widget_main_{i_cust_main}")
        st.session_state[f"custom_entry_val_widget_main_{i_cust_main}"] = e_cust_val_main
        st.session_state[f"custom_sl_val_widget_main_{i_cust_main}"] = s_cust_val_main
        st.session_state[f"custom_tp_val_widget_main_{i_cust_main}"] = t_cust_val_main
        
        try:
            if acc_balance > 0 and num_entries_custom_val_main > 0 :
                risk_dollar_total_cust_calc_val_main = acc_balance * (current_risk_pct_custom_main / 100)
                risk_dollar_per_entry_cust_calc_val_main = risk_dollar_total_cust_calc_val_main / num_entries_custom_val_main
                entry_p_cust_calc_val_main, sl_p_cust_calc_val_main, tp_p_cust_calc_val_main = float(e_cust_val_main), float(s_cust_val_main), float(t_cust_val_main)
                stop_p_cust_calc_val_main = abs(entry_p_cust_calc_val_main - sl_p_cust_calc_val_main)
                lot_cust_calc_val_main = (risk_dollar_per_entry_cust_calc_val_main / stop_p_cust_calc_val_main) if stop_p_cust_calc_val_main > 0 else 0.0
                rr_cust_calc_val_main = abs(tp_p_cust_calc_val_main - entry_p_cust_calc_val_main) / stop_p_cust_calc_val_main if stop_p_cust_calc_val_main > 0 else 0.0
                custom_entries_list.append({"Entry": f"{entry_p_cust_calc_val_main:.2f}", "SL": f"{sl_p_cust_calc_val_main:.2f}", "TP": f"{tp_p_cust_calc_val_main:.2f}", "Lot": f"{lot_cust_calc_val_main:.2f}", "Risk $": f"{lot_cust_calc_val_main * stop_p_cust_calc_val_main:.2f}", "RR": f"{rr_cust_calc_val_main:.2f}"})
        except (ValueError, TypeError, ZeroDivisionError): pass
    save_custom_button = st.sidebar.button("💾 Save Plan (CUSTOM)", key="sidebar_btn_save_custom_final")

# --- Strategy Summary (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Strategy Summary") # ไม่มีหมายเลข
if current_trade_mode == "FIBO":
    if entry_data_fibo_list:
        df_fibo_summary_display_val_main = pd.DataFrame(entry_data_fibo_list)
        st.sidebar.write(f"Total Lots: {pd.to_numeric(df_fibo_summary_display_val_main['Lot'], errors='coerce').sum():.2f}")
        st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_fibo_summary_display_val_main['Risk $'], errors='coerce').sum():.2f}")
    else: st.sidebar.caption("กรอกข้อมูล FIBO และคำนวณเพื่อดู Summary")
elif current_trade_mode == "CUSTOM":
    if custom_entries_list:
        df_custom_summary_display_val_main = pd.DataFrame(custom_entries_list)
        st.sidebar.write(f"Total Lots: {pd.to_numeric(df_custom_summary_display_val_main['Lot'], errors='coerce').sum():.2f}")
        st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_custom_summary_display_val_main['Risk $'], errors='coerce').sum():.2f}")
        avg_rr_val_main = pd.to_numeric(df_custom_summary_display_val_main['RR'], errors='coerce').mean()
        if pd.notna(avg_rr_val_main): st.sidebar.write(f"Average RR: {avg_rr_val_main:.2f}")
    else: st.sidebar.caption("กรอกข้อมูล CUSTOM และคำนวณเพื่อดู Summary")

# --- Scaling Manager (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("Scaling Manager") # ไม่มีหมายเลข
default_scaling_values_main = {"scaling_step_val_cfg_main": 0.25, "scaling_min_risk_val_cfg_main": 0.5, "scaling_max_risk_val_cfg_main": 5.0, "scaling_mode_val_cfg_main": "Manual"}
for k_scale_cfg_main, v_scale_cfg_main in default_scaling_values_main.items():
    if k_scale_cfg_main not in st.session_state: st.session_state[k_scale_cfg_main] = v_scale_cfg_main
with st.sidebar.expander("Scaling Settings", expanded=False):
    st.session_state.scaling_step_val_cfg_main = st.number_input("Scaling Step (%)", min_value=0.01, max_value=1.0, value=st.session_state.scaling_step_val_cfg_main, step=0.01, format="%.2f", key="scaling_step_widget_main")
    st.session_state.scaling_min_risk_val_cfg_main = st.number_input("Minimum Risk %", min_value=0.01, max_value=100.0, value=st.session_state.scaling_min_risk_val_cfg_main, step=0.01, format="%.2f", key="scaling_min_risk_widget_main")
    st.session_state.scaling_max_risk_val_cfg_main = st.number_input("Maximum Risk %", min_value=0.01, max_value=100.0, value=st.session_state.scaling_max_risk_val_cfg_main, step=0.01, format="%.2f", key="scaling_max_risk_widget_main")
    st.session_state.scaling_mode_val_cfg_main = st.radio("Scaling Mode", ["Manual", "Auto"], index=["Manual", "Auto"].index(st.session_state.scaling_mode_val_cfg_main), horizontal=True, key="scaling_mode_widget_main")

if st.session_state.active_portfolio_name:
    winrate_scale_val_main, gain_scale_val_main, _ = get_performance_for_active_portfolio(log_file, st.session_state.active_portfolio_name, acc_balance)
    current_risk_for_scaling_val_main = st.session_state.fibo_risk_val_cfg_main if current_trade_mode == "FIBO" else st.session_state.custom_risk_val_cfg_main
    suggest_risk_display_val_main = current_risk_for_scaling_val_main
    msg_scale_display_val_main = f"Risk% ({st.session_state.active_portfolio_name}) คงที่: {current_risk_for_scaling_val_main:.2f}%"
    if acc_balance > 0:
        if winrate_scale_val_main > 55 and gain_scale_val_main > 0.02 * acc_balance:
            suggest_risk_display_val_main = min(current_risk_for_scaling_val_main + st.session_state.scaling_step_val_cfg_main, st.session_state.scaling_max_risk_val_cfg_main)
            msg_scale_display_val_main = f"🎉 ผลงานดี! ({st.session_state.active_portfolio_name}) Winrate {winrate_scale_val_main:.1f}%, Gain {gain_scale_val_main:.2f}. แนะนำเพิ่ม Risk เป็น {suggest_risk_display_val_main:.2f}%"
        elif winrate_scale_val_main < 45 or gain_scale_val_main < 0:
            suggest_risk_display_val_main = max(current_risk_for_scaling_val_main - st.session_state.scaling_step_val_cfg_main, st.session_state.scaling_min_risk_val_cfg_main)
            msg_scale_display_val_main = f"⚠️ ควรลด Risk! ({st.session_state.active_portfolio_name}) Winrate {winrate_scale_val_main:.1f}%, P/L {gain_scale_val_main:.2f}. แนะนำลด Risk เป็น {suggest_risk_display_val_main:.2f}%"
    st.sidebar.info(msg_scale_display_val_main)
    if st.session_state.scaling_mode_val_cfg_main == "Manual" and suggest_risk_display_val_main != current_risk_for_scaling_val_main:
        if st.sidebar.button(f"ปรับ Risk เป็น {suggest_risk_display_val_main:.2f}", key="sidebar_btn_scaling_adjust_final"):
            if current_trade_mode == "FIBO": st.session_state.fibo_risk_val_cfg_main = suggest_risk_display_val_main
            else: st.session_state.custom_risk_val_cfg_main = suggest_risk_display_val_main
            st.rerun()
    elif st.session_state.scaling_mode_val_cfg_main == "Auto" and suggest_risk_display_val_main != current_risk_for_scaling_val_main:
        if current_trade_mode == "FIBO": st.session_state.fibo_risk_val_cfg_main = suggest_risk_display_val_main
        else: st.session_state.custom_risk_val_cfg_main = suggest_risk_display_val_main
else: st.sidebar.caption("เลือก Active Portfolio เพื่อดูคำแนะนำ Scaling")

# --- Drawdown Display & Lock Logic (Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader(f"การควบคุมความเสี่ยง ({st.session_state.active_portfolio_name or 'N/A'})") # ไม่มีหมายเลข
drawdown_today_val_display_main = 0.0
if st.session_state.active_portfolio_name:
    drawdown_today_val_display_main = get_today_drawdown_for_active_portfolio(log_file, st.session_state.active_portfolio_name)
drawdown_limit_abs_display_val_main = -acc_balance * (drawdown_limit_pct_input / 100) if acc_balance > 0 else 0.0
st.sidebar.metric(label="ขาดทุนรวมวันนี้ (Today's P/L)", value=f"{drawdown_today_val_display_main:,.2f} USD", delta_color="inverse")
st.sidebar.caption(f"ลิมิตขาดทุนต่อวัน: {drawdown_limit_abs_display_val_main:,.2f} USD ({drawdown_limit_pct_input:.1f}%)")
trade_locked = False 
if acc_balance > 0 and drawdown_today_val_display_main != 0 and drawdown_today_val_display_main <= drawdown_limit_abs_display_val_main :
    st.sidebar.error(f"🔴 หยุดเทรด! เกินลิมิตขาดทุนสำหรับพอร์ต {st.session_state.active_portfolio_name}")
    trade_locked = True

# --- Save Plan Button Click Logic (Sidebar) ---
# This logic uses variables populated by FIBO/CUSTOM input sections
asset_to_save_final_sb, risk_pct_to_save_final_sb, direction_to_save_final_sb = "", 0.0, "N/A"
data_list_to_save_final_sb = []
button_pressed_save_sb = False

if current_trade_mode == "FIBO":
    asset_to_save_final_sb = st.session_state.get("fibo_asset_val_cfg_main", "N/A")
    risk_pct_to_save_final_sb = st.session_state.get("fibo_risk_val_cfg_main", 0.0)
    direction_to_save_final_sb = st.session_state.get("fibo_direction_val_cfg_main", "N/A")
    data_list_to_save_final_sb = entry_data_fibo_list 
    if 'sidebar_btn_save_fibo_final' in st.session_state and st.session_state.sidebar_btn_save_fibo_final:
        button_pressed_save_sb = True
elif current_trade_mode == "CUSTOM":
    asset_to_save_final_sb = st.session_state.get("custom_asset_val_cfg_main", "N/A")
    risk_pct_to_save_final_sb = st.session_state.get("custom_risk_val_cfg_main", 0.0)
    direction_to_save_final_sb = "N/A" 
    data_list_to_save_final_sb = custom_entries_list
    if 'sidebar_btn_save_custom_final' in st.session_state and st.session_state.sidebar_btn_save_custom_final:
        button_pressed_save_sb = True

if button_pressed_save_sb:
    if not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    elif trade_locked:
        st.sidebar.error(f"ไม่สามารถบันทึกแผนสำหรับพอร์ต {st.session_state.active_portfolio_name} เนื่องจากเกินลิมิตขาดทุนรายวัน")
    elif data_list_to_save_final_sb: 
        save_plan_to_log(data_list_to_save_final_sb, current_trade_mode, asset_to_save_final_sb, risk_pct_to_save_final_sb, direction_to_save_final_sb, st.session_state.active_portfolio_name)
    else:
        st.sidebar.warning(f"กรุณากรอกข้อมูล {current_trade_mode} ให้ครบถ้วนและให้ระบบคำนวณ Summary ก่อนบันทึก")

# ======================= END OF SEC 1 =======================
