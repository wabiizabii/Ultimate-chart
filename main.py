# ======================= main.py (ฉบับรวมทุกส่วน + แก้ไขล่าสุด) =======================
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
log_file = "trade_log.csv"
PORTFOLIO_FILE = 'portfolios.csv'

# 0.3. Initialize session state for variables that need to persist
if 'active_portfolio_name' not in st.session_state:
    st.session_state.active_portfolio_name = None
if 'fibo_asset' not in st.session_state:
    st.session_state.fibo_asset = "XAUUSD"
if 'fibo_risk_pct' not in st.session_state:
    st.session_state.fibo_risk_pct = 1.0
# ... (Initialize other session state variables from your original sidebar if needed) ...
if 'fibo_flags_inputs' not in st.session_state:
    st.session_state.fibo_flags_inputs = [True] * 5 # Assuming 5 Fibo levels
if 'custom_asset' not in st.session_state:
    st.session_state.custom_asset = "XAUUSD"
if 'custom_risk_pct' not in st.session_state:
    st.session_state.custom_risk_pct = 1.0
if 'custom_n_entry' not in st.session_state:
    st.session_state.custom_n_entry = 1


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
        if "Portfolio" not in df.columns: return 0
        df = df[df["Portfolio"] == active_portfolio]
        if df.empty: return 0
        today_str = datetime.now().strftime("%Y-%m-%d")
        if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0)
        df_today = df[df["Timestamp"].str.startswith(today_str)]
        return df_today["Risk $"].sum()
    except Exception: return 0

def get_performance_for_active_portfolio(log_file_path, active_portfolio, mode="week"):
    if not os.path.exists(log_file_path) or active_portfolio is None: return 0, 0, 0
    try:
        df = pd.read_csv(log_file_path)
        if "Portfolio" not in df.columns: return 0,0,0
        df = df[df["Portfolio"] == active_portfolio]
        if df.empty: return 0,0,0
        if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0, 0, 0
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0)
        now = datetime.now()
        start_date_str = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d") if mode == "week" else now.strftime("%Y-%m-01")
        df_period = df[df["Timestamp"] >= start_date_str]
        if df_period.empty: return 0,0,0
        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0]
        total_trades_period = win + loss
        winrate = (100 * win / total_trades_period) if total_trades_period > 0 else 0
        gain = df_period["Risk $"].sum()
        return winrate, gain, total_trades_period
    except Exception: return 0,0,0

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
    except Exception as e: st.sidebar.error(f"Save Plan ไม่สำเร็จ: {e}")

# 0.4.4. Statement Extraction Function (for SEC 4)
def extract_data_from_report_sec4(file_buffer, stat_definitions_arg):
    df_raw_sec4 = None
    try:
        file_buffer.seek(0)
        if file_buffer.name.endswith('.csv'):
            df_raw_sec4 = pd.read_csv(file_buffer, header=None, low_memory=False)
        elif file_buffer.name.endswith('.xlsx'):
            df_raw_sec4 = pd.read_excel(file_buffer, header=None, engine='openpyxl')
    except Exception as e_read:
        st.error(f"SEC 4: เกิดข้อผิดพลาดในการอ่านไฟล์: {e_read}"); return None
    if df_raw_sec4 is None or df_raw_sec4.empty: st.warning("SEC 4: ไม่สามารถอ่านข้อมูลจากไฟล์ได้ หรือไฟล์ว่างเปล่า"); return None
    section_starts_sec4 = {}
    section_keywords_sec4 = ["Positions", "Orders", "Deals", "History", "Results"]
    for keyword_s4 in section_keywords_sec4:
        if keyword_s4 not in section_starts_sec4:
            for r_idx_s4, row_s4 in df_raw_sec4.iterrows():
                if row_s4.astype(str).str.contains(keyword_s4, case=False, regex=False).any():
                    actual_key_s4 = "Deals" if keyword_s4 == "History" else keyword_s4
                    if actual_key_s4 not in section_starts_sec4: section_starts_sec4[actual_key_s4] = r_idx_s4
                    break
    extracted_data_sec4 = {}
    sorted_sections_s4 = sorted(section_starts_sec4.items(), key=lambda x_s4: x_s4[1])
    tabular_keywords_s4 = ["Positions", "Orders", "Deals"]
    for i_s4, (section_name_s4, start_row_s4) in enumerate(sorted_sections_s4):
        if section_name_s4 not in tabular_keywords_s4: continue
        header_row_idx_s4 = start_row_s4 + 1
        while header_row_idx_s4 < len(df_raw_sec4) and df_raw_sec4.iloc[header_row_idx_s4].isnull().all(): header_row_idx_s4 += 1
        if header_row_idx_s4 < len(df_raw_sec4):
            headers_s4 = [str(h_s4).strip() for h_s4 in df_raw_sec4.iloc[header_row_idx_s4] if pd.notna(h_s4) and str(h_s4).strip() != '']
            data_start_row_s4 = header_row_idx_s4 + 1
            end_row_s4 = len(df_raw_sec4)
            if i_s4 + 1 < len(sorted_sections_s4): end_row_s4 = sorted_sections_s4[i_s4+1][1]
            df_section_s4 = df_raw_sec4.iloc[data_start_row_s4:end_row_s4].copy().dropna(how='all')
            if not df_section_s4.empty:
                num_data_cols_s4 = df_section_s4.shape[1]
                final_headers_s4 = headers_s4[:num_data_cols_s4]
                if len(final_headers_s4) < num_data_cols_s4:
                    final_headers_s4.extend([f'Unnamed_S4_{j_s4}' for j_s4 in range(len(final_headers_s4), num_data_cols_s4)]) # Unique Unnamed
                df_section_s4.columns = final_headers_s4
                extracted_data_sec4[section_name_s4.lower()] = df_section_s4
    if "Results" in section_starts_sec4:
        results_stats_s4 = {}
        start_row_res_s4 = section_starts_sec4["Results"]
        results_df_s4 = df_raw_sec4.iloc[start_row_res_s4 : start_row_res_s4 + 20]
        for _, row_res_s4 in results_df_s4.iterrows():
            for c_idx_res_s4, cell_res_s4 in enumerate(row_res_s4):
                if pd.notna(cell_res_s4):
                    label_res_s4 = str(cell_res_s4).strip().replace(':', '')
                    if label_res_s4 in stat_definitions_arg:
                        for k_s4 in range(1, 5):
                            if (c_idx_res_s4 + k_s4) < len(row_res_s4):
                                value_s4 = row_res_s4.iloc[c_idx_res_s4 + k_s4]
                                if pd.notna(value_s4) and str(value_s4).strip() != "":
                                    clean_value_s4 = str(value_s4).split('(')[0].strip().replace(' ', '')
                                    results_stats_s4[label_res_s4] = clean_value_s4
                                    break
                        break 
        if results_stats_s4: extracted_data_sec4["balance_summary"] = pd.DataFrame(list(results_stats_s4.items()), columns=['Metric', 'Value'])
    return extracted_data_sec4

# 0.4.5. Dashboard Data Loading Function (for SEC 5)
def load_data_for_dashboard_sec5(active_portfolio_arg, current_portfolio_initial_balance):
    source_option_sec5 = st.selectbox("เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:", ["Log File (แผนเทรด)", "Statement Import (ผลเทรดจริง)"], index=0, key="dashboard_source_selector_sec5")
    df_dashboard_sec5 = pd.DataFrame()
    profit_col_identified_sec5, asset_col_identified_sec5, date_col_identified_sec5 = None, None, None

    if source_option_sec5 == "Log File (แผนเทรด)":
        if not active_portfolio_arg: st.warning("SEC 5: กรุณาเลือก Active Portfolio"); return df_dashboard_sec5, profit_col_identified_sec5, asset_col_identified_sec5, date_col_identified_sec5
        if os.path.exists(log_file):
            try:
                df_log_all_sec5 = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all_sec5.columns: st.warning("SEC 5: Log file ไม่มีคอลัมน์ 'Portfolio'"); return df_dashboard_sec5, profit_col_identified_sec5, asset_col_identified_sec5, date_col_identified_sec5
                df_dashboard_sec5 = df_log_all_sec5[df_log_all_sec5["Portfolio"] == active_portfolio_arg].copy()
                if df_dashboard_sec5.empty: st.info(f"SEC 5: ไม่พบข้อมูล Log File สำหรับพอร์ต '{active_portfolio_arg}'")
            except Exception as e_log_s5: st.error(f"SEC 5: ไม่สามารถโหลด Log File: {e_log_s5}")
        else: st.info(f"SEC 5: ไม่พบ Log File ({log_file})")
    else: # Statement Import
        if not active_portfolio_arg: st.warning("SEC 5: กรุณาเลือก Active Portfolio"); return df_dashboard_sec5, profit_col_identified_sec5, asset_col_identified_sec5, date_col_identified_sec5
        df_from_session = st.session_state.get('df_stmt_current_active_portfolio', pd.DataFrame())
        if not df_from_session.empty:
            df_dashboard_sec5 = df_from_session.copy()
            if 'Portfolio' in df_dashboard_sec5.columns and not df_dashboard_sec5[df_dashboard_sec5['Portfolio'] == active_portfolio_arg].empty:
                df_dashboard_sec5 = df_dashboard_sec5[df_dashboard_sec5['Portfolio'] == active_portfolio_arg]
        if df_dashboard_sec5.empty: st.info(f"SEC 5: ไม่มีข้อมูล Statement สำหรับพอร์ต '{active_portfolio_arg}' (โปรดอัปโหลดใน SEC 4)")

    if not df_dashboard_sec5.empty:
        if 'Profit' in df_dashboard_sec5.columns:
            df_dashboard_sec5['Profit'] = pd.to_numeric(df_dashboard_sec5['Profit'], errors='coerce').fillna(0)
            if df_dashboard_sec5['Profit'].abs().sum() > 0: profit_col_identified_sec5 = 'Profit'
        if not profit_col_identified_sec5 and 'Risk $' in df_dashboard_sec5.columns:
            df_dashboard_sec5['Risk $'] = pd.to_numeric(df_dashboard_sec5['Risk $'], errors='coerce').fillna(0)
            profit_col_identified_sec5 = 'Risk $'
        for col_numeric in ['RR', 'Lot', 'Commission', 'Swap', 'Volume']:
            if col_numeric in df_dashboard_sec5.columns: df_dashboard_sec5[col_numeric] = pd.to_numeric(df_dashboard_sec5[col_numeric], errors='coerce').fillna(0)
        if 'Asset' in df_dashboard_sec5.columns: asset_col_identified_sec5 = 'Asset'
        elif 'Symbol' in df_dashboard_sec5.columns: asset_col_identified_sec5 = 'Symbol'
        date_col_options_sec5 = [col for col in ["Timestamp", "Time", "Date", "Open Time", "Close Time"] if col in df_dashboard_sec5.columns]
        for col_date_s5 in date_col_options_sec5:
            df_dashboard_sec5[col_date_s5] = pd.to_datetime(df_dashboard_sec5[col_date_s5], errors='coerce')
            if df_dashboard_sec5[col_date_s5].notna().any(): date_col_identified_sec5 = col_date_s5; break
    return df_dashboard_sec5, profit_col_identified_sec5, asset_col_identified_sec5, date_col_identified_sec5

# ======================= SEC 0.8: PORTFOLIO SELECTION & MANAGEMENT (UI in Sidebar) =======================
portfolios_df = load_portfolios()
acc_balance = 10000 # Default balance if no portfolio is selected or found

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")
if not portfolios_df.empty:
    portfolio_names = portfolios_df['portfolio_name'].tolist()
    if 'active_portfolio_name' not in st.session_state or st.session_state.active_portfolio_name not in portfolio_names:
        st.session_state.active_portfolio_name = portfolio_names[0] if portfolio_names else None
    
    selected_portfolio_name = st.sidebar.selectbox(
        "เลือกพอร์ต:", options=portfolio_names,
        index=portfolio_names.index(st.session_state.active_portfolio_name) if st.session_state.active_portfolio_name in portfolio_names else 0,
        key='portfolio_selector_widget' # Unique key
    )
    if selected_portfolio_name != st.session_state.active_portfolio_name: # Update if changed
        st.session_state.active_portfolio_name = selected_portfolio_name
        st.rerun() # Rerun to update context for the selected portfolio

    if st.session_state.active_portfolio_name:
        active_portfolio_details = portfolios_df[portfolios_df['portfolio_name'] == st.session_state.active_portfolio_name]
        if not active_portfolio_details.empty:
            acc_balance = float(active_portfolio_details['initial_balance'].iloc[0])
            st.sidebar.success(f"Active: **{st.session_state.active_portfolio_name}** (Bal: ${acc_balance:,.2f})")
        else: st.sidebar.error("ไม่พบรายละเอียดพอร์ต")
else:
    st.sidebar.info("ยังไม่มีพอร์ต กรุณาเพิ่มพอร์ตด้านล่าง")
    st.session_state.active_portfolio_name = None

with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=False): # Collapsed by default
    st.subheader("พอร์ตทั้งหมดของคุณ")
    st.dataframe(portfolios_df, use_container_width=True, hide_index=True)
    st.subheader("➕ เพิ่มพอร์ตใหม่")
    with st.form("new_portfolio_form_main", clear_on_submit=True): # Unique key
        new_p_name = st.text_input("ชื่อพอร์ต")
        new_p_bal = st.number_input("บาลานซ์เริ่มต้น ($)", min_value=0.0, value=10000.0, step=100.0, format="%.2f")
        if st.form_submit_button("💾 บันทึกพอร์ตใหม่"):
            if not new_p_name: st.warning("กรุณาใส่ชื่อพอร์ต")
            elif new_p_name in portfolios_df['portfolio_name'].values: st.error(f"ชื่อพอร์ต '{new_p_name}' มีอยู่แล้ว")
            else:
                new_id = (portfolios_df['portfolio_id'].max() + 1) if not portfolios_df.empty and pd.notna(portfolios_df['portfolio_id'].max()) else 1
                new_p_data = pd.DataFrame([{'portfolio_id': int(new_id), 'portfolio_name': new_p_name, 'initial_balance': new_p_bal, 'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}])
                portfolios_df = pd.concat([portfolios_df, new_p_data], ignore_index=True)
                save_portfolios(portfolios_df)
                st.success(f"เพิ่มพอร์ต '{new_p_name}' สำเร็จ!"); st.rerun()
st.markdown("---")

# ======================= SEC 1: SIDEBAR - TRADE SETUP & CONTROLS =======================
st.sidebar.header("🎛️ Trade Setup & Controls")
# 1.1. Main Trade Setup
drawdown_limit_pct_input = st.sidebar.number_input("Drawdown Limit ต่อวัน (%)", min_value=0.1, max_value=20.0, value=st.session_state.get("sidebar_dd_limit_pct", 2.0), step=0.1, format="%.1f", key="sidebar_dd_limit_pct_val") # Unique key
current_trade_mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="trade_mode_selector") # Unique key
if st.sidebar.button("🔄 Reset Form", key="reset_form_button"): # Unique key
    keys_to_clear = [k for k in st.session_state if not k.startswith('portfolio_') and k not in ['active_portfolio_name', 'sidebar_dd_limit_pct_val', 'trade_mode_selector']]
    for k in keys_to_clear: del st.session_state[k]
    st.session_state.fibo_flags_inputs = [True] * 5; st.rerun()

# 1.2. FIBO Input Zone
entry_data_fibo_list = []
if current_trade_mode == "FIBO":
    st.sidebar.subheader("FIBO Mode Inputs")
    st.session_state.fibo_asset = st.sidebar.text_input("Asset", value=st.session_state.get("fibo_asset","XAUUSD"), key="fibo_asset_input")
    st.session_state.fibo_risk_pct = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("fibo_risk_pct",1.0), step=0.01, key="fibo_risk_input")
    st.session_state.fibo_direction = st.sidebar.radio("Direction", ["Long", "Short"], horizontal=True, key="fibo_direction_input")
    st.session_state.fibo_swing_high = st.sidebar.text_input("High", key="fibo_high_input")
    st.session_state.fibo_swing_low = st.sidebar.text_input("Low", key="fibo_low_input")
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibo_levels_const = [0.114, 0.25, 0.382, 0.5, 0.618]
    if "fibo_flags_inputs" not in st.session_state: st.session_state.fibo_flags_inputs = [True] * len(fibo_levels_const)
    cols_fibo_cb = st.sidebar.columns(len(fibo_levels_const))
    for i, col_cb_fibo in enumerate(cols_fibo_cb): st.session_state.fibo_flags_inputs[i] = col_cb_fibo.checkbox(f"{fibo_levels_const[i]:.3f}", value=st.session_state.fibo_flags_inputs[i], key=f"fibo_level_cb_{i}")
    
    # Calculation for FIBO (populates entry_data_fibo_list)
    try:
        high_fibo_val = float(st.session_state.fibo_swing_high)
        low_fibo_val = float(st.session_state.fibo_swing_low)
        if high_fibo_val > low_fibo_val:
            selected_fib_levels = [fibo_levels_const[i] for i, sel in enumerate(st.session_state.fibo_flags_inputs) if sel]
            n_selected = len(selected_fib_levels)
            risk_dollar_total = acc_balance * (st.session_state.fibo_risk_pct / 100)
            risk_dollar_per_entry = risk_dollar_total / n_selected if n_selected > 0 else 0
            for fib_level_val in selected_fib_levels:
                entry_p = low_fibo_val + (high_fibo_val - low_fibo_val) * fib_level_val if st.session_state.fibo_direction == "Long" else high_fibo_val - (high_fibo_val - low_fibo_val) * fib_level_val
                sl_p = low_fibo_val if st.session_state.fibo_direction == "Long" else high_fibo_val
                stop_p = abs(entry_p - sl_p)
                lot = (risk_dollar_per_entry / stop_p) if stop_p > 0 else 0
                entry_data_fibo_list.append({"Fibo Level": f"{fib_level_val:.3f}", "Entry": f"{entry_p:.2f}", "SL": f"{sl_p:.2f}", "Lot": f"{lot:.2f}", "Risk $": f"{lot * stop_p:.2f}"})
    except (ValueError, TypeError): pass # Handle empty or non-numeric inputs gracefully for calculation
    
    save_fibo_button = st.sidebar.button("Save Plan (FIBO)", key="fibo_save_plan_btn") # Unique key

# 1.3. CUSTOM Input Zone
custom_entries_list = []
if current_trade_mode == "CUSTOM":
    st.sidebar.subheader("CUSTOM Mode Inputs")
    st.session_state.custom_asset = st.sidebar.text_input("Asset", value=st.session_state.get("custom_asset","XAUUSD"), key="custom_asset_input")
    st.session_state.custom_risk_pct = st.sidebar.number_input("Risk %", min_value=0.01, value=st.session_state.get("custom_risk_pct",1.0), step=0.01, key="custom_risk_input")
    st.session_state.custom_n_entry = st.sidebar.number_input("จำนวนไม้", min_value=1, value=st.session_state.get("custom_n_entry",1), step=1, key="custom_n_entry_input")
    for i in range(int(st.session_state.custom_n_entry)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        e = st.sidebar.text_input(f"Entry {i+1}", key=f"custom_e_{i}")
        s = st.sidebar.text_input(f"SL {i+1}", key=f"custom_s_{i}")
        t = st.sidebar.text_input(f"TP {i+1}", key=f"custom_t_{i}")
        try: # Calculation for CUSTOM (populates custom_entries_list)
            risk_dollar_total_cust = acc_balance * (st.session_state.custom_risk_pct / 100)
            risk_dollar_per_entry_cust = risk_dollar_total_cust / int(st.session_state.custom_n_entry) if int(st.session_state.custom_n_entry) > 0 else 0
            entry_p_cust, sl_p_cust, tp_p_cust = float(e), float(s), float(t)
            stop_p_cust = abs(entry_p_cust - sl_p_cust)
            lot_cust = (risk_dollar_per_entry_cust / stop_p_cust) if stop_p_cust > 0 else 0
            rr_cust = abs(tp_p_cust - entry_p_cust) / stop_p_cust if stop_p_cust > 0 else 0
            custom_entries_list.append({"Entry": f"{entry_p_cust:.2f}", "SL": f"{sl_p_cust:.2f}", "TP": f"{tp_p_cust:.2f}", "Lot": f"{lot_cust:.2f}", "Risk $": f"{lot_cust * stop_p_cust:.2f}", "RR": f"{rr_cust:.2f}"})
        except (ValueError, TypeError): pass
    save_custom_button = st.sidebar.button("Save Plan (CUSTOM)", key="custom_save_plan_btn") # Unique key

# 1.4. Strategy Summary
st.sidebar.markdown("---")
st.sidebar.subheader("🧾 Strategy Summary")
if current_trade_mode == "FIBO" and entry_data_fibo_list:
    df_fibo_summary = pd.DataFrame(entry_data_fibo_list)
    st.sidebar.write(f"Total Lots: {pd.to_numeric(df_fibo_summary['Lot'], errors='coerce').sum():.2f}")
    st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_fibo_summary['Risk $'], errors='coerce').sum():.2f}")
elif current_trade_mode == "CUSTOM" and custom_entries_list:
    df_custom_summary = pd.DataFrame(custom_entries_list)
    st.sidebar.write(f"Total Lots: {pd.to_numeric(df_custom_summary['Lot'], errors='coerce').sum():.2f}")
    st.sidebar.write(f"Total Risk $: {pd.to_numeric(df_custom_summary['Risk $'], errors='coerce').sum():.2f}")
else: st.sidebar.caption("กรอกข้อมูลเพื่อดู Summary")

# 1.5. Scaling Manager
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    scaling_step = st.number_input("Scaling Step (%)", min_value=0.01, value=0.25, step=0.01, key="scaling_step")
    min_risk = st.number_input("Minimum Risk %", min_value=0.01, value=0.5, step=0.01, key="scaling_min_risk")
    max_risk = st.number_input("Maximum Risk %", min_value=0.01, value=5.0, step=0.01, key="scaling_max_risk")
    scaling_mode = st.radio("Scaling Mode", ["Manual", "Auto"], horizontal=True, key="scaling_mode_radio")

if st.session_state.active_portfolio_name:
    wr_scale, gain_scale, _ = get_performance_for_active_portfolio(log_file, st.session_state.active_portfolio_name)
    current_risk_val = st.session_state.fibo_risk_pct if current_trade_mode == "FIBO" else st.session_state.custom_risk_pct
    suggest_risk_val = current_risk_val
    msg_scale = f"Risk% ({st.session_state.active_portfolio_name}) คงที่: {current_risk_val:.2f}%"
    if wr_scale > 55 and gain_scale > 0.02 * acc_balance:
        suggest_risk_val = min(current_risk_val + scaling_step, max_risk)
        msg_scale = f"🎉 ผลงานดี! ({st.session_state.active_portfolio_name}) แนะนำเพิ่ม Risk เป็น {suggest_risk_val:.2f}%"
    elif wr_scale < 45 or gain_scale < 0:
        suggest_risk_val = max(current_risk_val - scaling_step, min_risk)
        msg_scale = f"⚠️ ควรลด Risk! ({st.session_state.active_portfolio_name}) แนะนำลด Risk เป็น {suggest_risk_val:.2f}%"
    st.sidebar.info(msg_scale)
    if scaling_mode == "Manual" and suggest_risk_val != current_risk_val:
        if st.sidebar.button(f"ปรับ Risk เป็น {suggest_risk_val:.2f}", key="scaling_adjust_btn"):
            if current_trade_mode == "FIBO": st.session_state.fibo_risk_pct = suggest_risk_val
            else: st.session_state.custom_risk_pct = suggest_risk_val
            st.rerun()
    elif scaling_mode == "Auto" and suggest_risk_val != current_risk_val:
        if current_trade_mode == "FIBO": st.session_state.fibo_risk_pct = suggest_risk_val
        else: st.session_state.custom_risk_pct = suggest_risk_val
        # No rerun for auto, will apply on next interaction

# 1.6. Drawdown Display & Lock Logic
st.sidebar.markdown("---")
st.sidebar.subheader(f"การควบคุมความเสี่ยง ({st.session_state.active_portfolio_name or 'N/A'})")
drawdown_today_val = 0
if st.session_state.active_portfolio_name:
    drawdown_today_val = get_today_drawdown_for_active_portfolio(log_file, st.session_state.active_portfolio_name)
drawdown_limit_abs = -acc_balance * (drawdown_limit_pct_input / 100)
st.sidebar.metric(label="ขาดทุนรวมวันนี้", value=f"{drawdown_today_val:,.2f} USD", delta_color="inverse")
st.sidebar.caption(f"ลิมิตขาดทุน: {drawdown_limit_abs:,.2f} USD ({drawdown_limit_pct_input:.1f}%)")
trade_locked = False
if drawdown_today_val !=0 and drawdown_today_val <= drawdown_limit_abs :
    st.sidebar.error(f"🔴 หยุดเทรด! เกินลิมิตขาดทุนพอร์ต {st.session_state.active_portfolio_name}")
    trade_locked = True

# 1.7. Save Plan Button Logic (Consolidated from original logic)
asset_to_save_final, risk_pct_to_save_final, direction_to_save_final = "", 0.0, "N/A"
if current_trade_mode == "FIBO":
    asset_to_save_final = st.session_state.fibo_asset
    risk_pct_to_save_final = st.session_state.fibo_risk_pct
    direction_to_save_final = st.session_state.fibo_direction
    if 'fibo_save_plan_btn' in st.session_state and st.session_state.fibo_save_plan_btn:
        if not st.session_state.active_portfolio_name: st.sidebar.error("เลือกพอร์ตก่อนบันทึก")
        elif trade_locked: st.sidebar.error("ไม่สามารถบันทึก, เกินลิมิตขาดทุน")
        elif entry_data_fibo_list: save_plan_to_log(entry_data_fibo_list, "FIBO", asset_to_save_final, risk_pct_to_save_final, direction_to_save_final, st.session_state.active_portfolio_name)
        else: st.sidebar.warning("กรอกข้อมูล FIBO ให้ครบก่อนบันทึก")
elif current_trade_mode == "CUSTOM":
    asset_to_save_final = st.session_state.custom_asset
    risk_pct_to_save_final = st.session_state.custom_risk_pct
    if 'custom_save_plan_btn' in st.session_state and st.session_state.custom_save_plan_btn:
        if not st.session_state.active_portfolio_name: st.sidebar.error("เลือกพอร์ตก่อนบันทึก")
        elif trade_locked: st.sidebar.error("ไม่สามารถบันทึก, เกินลิมิตขาดทุน")
        elif custom_entries_list: save_plan_to_log(custom_entries_list, "CUSTOM", asset_to_save_final, risk_pct_to_save_final, "N/A", st.session_state.active_portfolio_name)
        else: st.sidebar.warning("กรอกข้อมูล CUSTOM ให้ครบก่อนบันทึก")

# ======================= SEC 2: MAIN AREA - CURRENT ENTRY PLAN DETAILS =======================
st.header("🎯 Entry Plan Details")
if st.session_state.active_portfolio_name:
    st.caption(f"สำหรับพอร์ต: **{st.session_state.active_portfolio_name}**")
    if current_trade_mode == "FIBO":
        if entry_data_fibo_list: df_display_fibo = pd.DataFrame(entry_data_fibo_list)
        else: df_display_fibo = pd.DataFrame(columns=["Fibo Level", "Entry", "SL", "Lot", "Risk $"]) # Show empty structure
        st.dataframe(df_display_fibo, hide_index=True, use_container_width=True)
    elif current_trade_mode == "CUSTOM":
        if custom_entries_list: df_display_custom = pd.DataFrame(custom_entries_list)
        else: df_display_custom = pd.DataFrame(columns=["Entry", "SL", "TP", "Lot", "Risk $", "RR"]) # Show empty structure
        st.dataframe(df_display_custom, hide_index=True, use_container_width=True)
else:
    st.warning("กรุณาเลือก Active Portfolio ใน Sidebar เพื่อดูรายละเอียดแผน")
st.markdown("---")

# ======================= SEC 3: MAIN AREA - CHART VISUALIZER =======================
with st.expander("📈 Chart Visualizer", expanded=True):
    chart_symbol_tv = "OANDA:XAUUSD" 
    if asset_to_save_final and asset_to_save_final != "N/A": chart_symbol_tv = asset_to_save_final # Use asset from current plan
    if "XAUUSD" in chart_symbol_tv.upper(): chart_symbol_tv = "OANDA:XAUUSD"
    elif "BTCUSD" in chart_symbol_tv.upper(): chart_symbol_tv = "BINANCE:BTCUSDT"

    if st.button("Plot Active Plan on Chart", key="plot_tv_chart_btn"): # Unique key
        st.components.v1.html(f"""
        <div id="tradingview_widget_main_area"></div>
        <script type_src="https://s3.tradingview.com/tv.js"></script>
        <script>new TradingView.widget({{
            "width": "100%", "height": 600, "symbol": "{chart_symbol_tv}", "interval": "15",
            "timezone": "Asia/Bangkok", "theme": "dark", "style": "1", "locale": "th",
            "enable_publishing": false, "withdateranges": true, "allow_symbol_change": true,
            "hide_side_toolbar": false, "details": true, "hotlist": true, "calendar": true,
            "container_id": "tradingview_widget_main_area"
        }});</script>""", height=620)
    else: st.info("กดปุ่ม 'Plot Active Plan on Chart' เพื่อแสดงกราฟ TradingView")
st.markdown("---")

# ======================= SEC 4: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
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
    if 'df_stmt_current_active_portfolio' not in st.session_state: st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
    if 'all_statement_data' not in st.session_state: st.session_state.all_statement_data = {}

    uploaded_files_s4 = st.file_uploader("อัปโหลด Statement (เชื่อมกับ Active Portfolio ปัจจุบัน)", type=["xlsx", "csv"], accept_multiple_files=True, key="stmt_uploader_s4") # Unique key
    if 'sec4_debug_mode' not in st.session_state: st.session_state.sec4_debug_mode = False
    st.session_state.sec4_debug_mode = st.checkbox("⚙️ เปิดโหมด Debug (SEC 4)", value=st.session_state.sec4_debug_mode, key="debug_checkbox_s4") # Unique key

    if uploaded_files_s4:
        if not st.session_state.active_portfolio_name: st.warning("SEC 4: เลือก Active Portfolio ก่อนอัปโหลด")
        else:
            active_p_stmt = st.session_state.active_portfolio_name
            st.info(f"ไฟล์ที่อัปโหลดจะเชื่อมกับพอร์ต: **{active_p_stmt}**")
            for uploaded_file_s4_item in uploaded_files_s4:
                st.write(f"กำลังประมวลผล: {uploaded_file_s4_item.name}")
                with st.spinner("กำลังแยกส่วนข้อมูล..."):
                    extracted_s4 = extract_data_from_report_sec4(uploaded_file_s4_item, stat_definitions_for_stmt_import)
                    if extracted_s4:
                        st.success(f"พบข้อมูล: {', '.join(extracted_s4.keys())}")
                        if 'deals' in extracted_s4:
                            df_deals_s4_new = extracted_s4['deals'].copy()
                            df_deals_s4_new['Portfolio'] = active_p_stmt
                            st.session_state.df_stmt_current_active_portfolio = df_deals_s4_new
                        if active_p_stmt not in st.session_state.all_statement_data: st.session_state.all_statement_data[active_p_stmt] = {}
                        st.session_state.all_statement_data[active_p_stmt][uploaded_file_s4_item.name] = extracted_s4
                        if 'balance_summary' in extracted_s4:
                            st.write(f"### 📊 Balance Summary ({active_p_stmt} - {uploaded_file_s4_item.name})")
                            st.dataframe(extracted_s4['balance_summary'])
                        if st.session_state.sec4_debug_mode:
                            for k, v_df in extracted_s4.items():
                                if k != 'balance_summary': st.write(f"### 📄 {k.title()}:"); st.dataframe(v_df)
                    else: st.warning(f"ไม่พบข้อมูลใน {uploaded_file_s4_item.name}")
    else: st.info("ยังไม่มีไฟล์ Statement อัปโหลด (SEC 4)")
    st.markdown("---")
    st.subheader(f"📁 Deals ล่าสุดของพอร์ต: {st.session_state.active_portfolio_name or 'N/A'} (SEC 4)")
    df_to_display_s4 = st.session_state.df_stmt_current_active_portfolio
    if not df_to_display_s4.empty and st.session_state.active_portfolio_name:
        if 'Portfolio' in df_to_display_s4.columns:
            df_filtered_s4 = df_to_display_s4[df_to_display_s4['Portfolio'] == st.session_state.active_portfolio_name]
            if not df_filtered_s4.empty: st.dataframe(df_filtered_s4)
            else: st.info(f"ไม่มีข้อมูล Deals สำหรับพอร์ต {st.session_state.active_portfolio_name}")
        else: st.dataframe(df_to_display_s4) # Assume already filtered if no Portfolio column
    else: st.info(f"ไม่มีข้อมูล Deals สำหรับพอร์ต {st.session_state.active_portfolio_name}")
    if st.button("🗑️ ล้างข้อมูล Statement ปัจจุบัน (SEC 4)", key="clear_stmt_s4_btn"): # Unique key
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame(); st.success("ล้างข้อมูล Statement ปัจจุบันแล้ว"); st.rerun()
st.markdown("---")

# ======================= SEC 5: MAIN AREA - PERFORMANCE DASHBOARD =======================
with st.expander("📊 Performance Dashboard (SEC 5)", expanded=True):
    if not st.session_state.active_portfolio_name: st.warning("เลือก Active Portfolio เพื่อดู Dashboard")
    else:
        active_p_dash = st.session_state.active_portfolio_name
        initial_bal_dash = acc_balance # Uses updated acc_balance from active portfolio selection
        st.subheader(f"Dashboard สำหรับพอร์ต: {active_p_dash} (Bal: ${initial_bal_dash:,.2f})")
        df_dash, profit_col_dash, asset_col_dash, date_col_dash = load_data_for_dashboard_sec5(active_p_dash, initial_bal_dash)
        
        tabs_s5 = st.tabs(["📊 Dashboard", "📈 RR", "📉 Lot Size", "🕒 Time", "🤖 AI Advisor", "⬇️ Export"])
        if df_dash.empty: st.info(f"SEC 5: ไม่มีข้อมูลสำหรับ Dashboard '{active_p_dash}'")
        else:
            with tabs_s5[0]: # Dashboard
                if not profit_col_dash: st.warning("SEC 5: ไม่พบคอลัมน์ Profit/Risk $")
                else:
                    df_tab_s5 = df_dash.copy()
                    if asset_col_dash:
                        assets_unique_s5 = ["ทั้งหมด"] + sorted(df_tab_s5[asset_col_dash].dropna().unique())
                        asset_sel_s5 = st.selectbox(f"Filter by {asset_col_dash}", assets_unique_s5, key="dash_asset_filter_s5_tab") # Unique key
                        if asset_sel_s5 != "ทั้งหมด": df_tab_s5 = df_tab_s5[df_tab_s5[asset_col_dash] == asset_sel_s5]
                    if df_tab_s5.empty: st.info("ไม่มีข้อมูลหลัง Filter")
                    else:
                        st.markdown("### 🥧 Pie Chart: Win/Loss")
                        wins_s5 = df_tab_s5[df_tab_s5[profit_col_dash] > 0].shape[0]
                        losses_s5 = df_tab_s5[df_tab_s5[profit_col_dash] <= 0].shape[0]
                        if wins_s5 > 0 or losses_s5 > 0:
                            pie_df_s5 = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [wins_s5, losses_s5]})
                            st.plotly_chart(px.pie(pie_df_s5, names="Result", values="Count", color="Result", color_discrete_map={"Win":"green", "Loss":"red"}), use_container_width=True)
                        else: st.info("ไม่มีข้อมูล Win/Loss")
                        if date_col_dash:
                            st.markdown("### 📊 Bar Chart: กำไร/ขาดทุนรายวัน")
                            df_bar_chart_s5 = df_tab_s5.copy()
                            df_bar_chart_s5["TradeDate"] = df_bar_chart_s5[date_col_dash].dt.date
                            bar_grouped_s5 = df_bar_chart_s5.groupby("TradeDate")[profit_col_dash].sum().reset_index(name="P/L")
                            if not bar_grouped_s5.empty: st.plotly_chart(px.bar(bar_grouped_s5, x="TradeDate", y="P/L", color="P/L", color_continuous_scale=["red","lightcoral","lightgreen","green"]), use_container_width=True)
                            else: st.info("ไม่มีข้อมูลสำหรับ Bar Chart")
                            st.markdown("### 📈 Timeline: Balance Curve")
                            df_bal_s5 = df_tab_s5.copy().sort_values(by=date_col_dash)
                            df_bal_s5["Balance"] = initial_bal_dash + df_bal_s5[profit_col_dash].cumsum()
                            if not df_bal_s5.empty: st.plotly_chart(px.line(df_bal_s5, x=date_col_dash, y="Balance", markers=True, title="Balance Curve"), use_container_width=True)
                            else: st.info("ไม่มีข้อมูลสำหรับ Balance Curve")
                        else: st.warning("ไม่พบคอลัมน์วันที่สำหรับ Bar Chart และ Balance Curve")
            with tabs_s5[1]: # RR
                if "RR" in df_dash.columns and df_dash["RR"].notna().any():
                    if not df_dash["RR"].dropna().empty: st.plotly_chart(px.histogram(df_dash["RR"].dropna(), nbins=20, title="RR Distribution"), use_container_width=True)
                    else: st.info("ไม่มีข้อมูล RR")
                else: st.warning("ไม่พบคอลัมน์ 'RR'")
            with tabs_s5[2]: # Lot Size
                if "Lot" in df_dash.columns and date_col_dash and df_dash["Lot"].notna().any():
                    if not df_dash["Lot"].dropna().empty: st.plotly_chart(px.line(df_dash.dropna(subset=[date_col_dash, "Lot"]).sort_values(by=date_col_dash), x=date_col_dash, y="Lot", markers=True, title="Lot Size Over Time"), use_container_width=True)
                    else: st.info("ไม่มีข้อมูล Lot หรือ วันที่")
                else: st.warning("ไม่พบคอลัมน์ 'Lot' หรือ วันที่")
            with tabs_s5[3]: # Time Analysis
                if date_col_dash and profit_col_dash:
                    df_time_s5 = df_dash.copy()
                    df_time_s5["Weekday"] = df_time_s5[date_col_dash].dt.day_name()
                    order_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                    weekday_profit_s5 = df_time_s5.groupby("Weekday")[profit_col_dash].sum().reindex(order_days).fillna(0).reset_index()
                    if not weekday_profit_s5.empty: st.plotly_chart(px.bar(weekday_profit_s5, x="Weekday", y=profit_col_dash, title="P/L by Weekday"), use_container_width=True)
                    else: st.info("ไม่มีข้อมูลวิเคราะห์ตามวัน")
                else: st.warning("ไม่พบคอลัมน์ วันที่ หรือ Profit/Risk $")
            with tabs_s5[4]: # AI Advisor
                st.subheader("🤖 AI Advisor (Gemini)")
                if 'google_api_key_s5_dash' not in st.session_state: st.session_state.google_api_key_s5_dash = "" # Unique key
                st.session_state.google_api_key_s5_dash = st.text_input("ใส่ Google API Key (SEC 5):", type="password", value=st.session_state.google_api_key_s5_dash, key="gemini_api_s5_dash_input") # Unique key
                if st.button("วิเคราะห์โดย AI (SEC 5)", key="ai_analyze_s5_dash_btn"): # Unique key
                    if not st.session_state.google_api_key_s5_dash: st.warning("ใส่ Google API Key ก่อน")
                    elif not profit_col_dash or df_dash.empty: st.warning("ไม่มีข้อมูลให้ AI วิเคราะห์")
                    else:
                        try:
                            genai.configure(api_key=st.session_state.google_api_key_s5_dash)
                            model = genai.GenerativeModel('gemini-pro')
                            total_t = df_dash.shape[0]; win_t = df_dash[df_dash[profit_col_dash] > 0].shape[0]
                            wr = (100*win_t/total_t) if total_t > 0 else 0; g_pl = df_dash[profit_col_dash].sum()
                            avg_rr = pd.to_numeric(df_dash.get('RR', pd.Series(dtype='float')), errors='coerce').mean()
                            prompt_txt = f"วิเคราะห์ผลเทรดพอร์ต '{active_p_dash}': Trades: {total_t}, Winrate: {wr:.2f}%, P/L: {g_pl:,.2f}, Avg RR: {avg_rr if pd.notna(avg_rr) else 'N/A'}. บอกจุดแข็ง, จุดอ่อน, แนะนำปรับปรุง (ภาษาไทย)"
                            with st.spinner("AI กำลังคิด..."): response = model.generate_content(prompt_txt)
                            st.markdown("--- \n**AI Says:**"); st.markdown(response.text)
                        except Exception as e_ai_dash: st.error(f"Gemini AI Error: {e_ai_dash}")
            with tabs_s5[5]: # Export
                if not df_dash.empty:
                    st.download_button("Download Data (CSV)", df_dash.to_csv(index=False).encode('utf-8'), f"dash_report_{active_p_dash.replace(' ','_')}.csv", "text/csv", key="export_dash_s5_btn") # Unique key
                else: st.info("ไม่มีข้อมูลให้ Export")
st.markdown("---")

# ======================= SEC 6: MAIN AREA - TRADE LOG VIEWER =======================
with st.expander("📚 Trade Log Viewer (แผนเทรดที่บันทึกไว้)", expanded=False):
    if not st.session_state.active_portfolio_name: st.warning("เลือก Active Portfolio เพื่อดู Log")
    else:
        st.subheader(f"Log สำหรับพอร์ต: {st.session_state.active_portfolio_name}")
        if os.path.exists(log_file):
            try:
                df_log_all_s6 = pd.read_csv(log_file)
                if "Portfolio" not in df_log_all_s6.columns: st.warning("Log file ไม่มีคอลัมน์ 'Portfolio'")
                else:
                    df_show_s6 = df_log_all_s6[df_log_all_s6["Portfolio"] == st.session_state.active_portfolio_name].copy()
                    if df_show_s6.empty: st.info(f"ไม่พบ Log สำหรับพอร์ต '{st.session_state.active_portfolio_name}'.")
                    else:
                        c1,c2,c3 = st.columns(3)
                        mf = c1.selectbox("Mode", ["ทั้งหมด"]+sorted(df_show_s6["Mode"].unique().tolist()),key="log_mode_s6") # Unique key
                        af = c2.selectbox("Asset",["ทั้งหมด"]+sorted(df_show_s6["Asset"].unique().tolist()),key="log_asset_s6") # Unique key
                        df = c3.text_input("ค้นหาวันที่ (YYYY-MM-DD)",key="log_date_s6") # Unique key
                        df_filtered_s6 = df_show_s6.copy()
                        if mf!="ทั้งหมด": df_filtered_s6 = df_filtered_s6[df_filtered_s6["Mode"]==mf]
                        if af!="ทั้งหมด": df_filtered_s6 = df_filtered_s6[df_filtered_s6["Asset"]==af]
                        if df: df_filtered_s6 = df_filtered_s6[df_filtered_s6["Timestamp"].str.contains(df,na=False)]
                        st.dataframe(df_filtered_s6, use_container_width=True, hide_index=True)
            except Exception as e_log_s6: st.error(f"อ่าน Log ไม่ได้ (SEC 6): {e_log_s6}")
        else: st.info(f"ยังไม่มี Log File ({log_file})")
st.markdown("---")

# ======================= END OF MAIN APP STRUCTURE =======================
st.caption("Ultimate Trading Dashboard - End of Application")
