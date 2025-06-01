# ===================== SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date # เพิ่ม date สำหรับ date_input
import plotly.express as px
import google.generativeai as genai # ถ้ายังใช้อยู่
import gspread
import plotly.graph_objects as go
# import yfinance as yf # ถ้าไม่ได้ใช้ในส่วนนี้ อาจจะไม่ต้อง import หรือถ้าใช้ก็เอา comment ออก
import random
# import csv # อาจจะไม่จำเป็นถ้าใช้ io.StringIO กับ pandas โดยตรง
import io 
import uuid # <<< เพิ่ม import uuid

st.set_page_config(page_title="Ultimate-Chart", layout="wide")
acc_balance = 10000 # ยอดคงเหลือเริ่มต้นของบัญชีเทรด (อาจจะดึงมาจาก Active Portfolio ในอนาคต)

# กำหนดชื่อ Google Sheet และ Worksheet ที่จะใช้เก็บข้อมูล
GOOGLE_SHEET_NAME = "TradeLog" # ชื่อ Google Sheet ของลูกพี่ตั้ม
WORKSHEET_PORTFOLIOS = "Portfolios"
WORKSHEET_PLANNED_LOGS = "PlannedTradeLogs"
WORKSHEET_ACTUAL_TRADES = "ActualTrades"
WORKSHEET_ACTUAL_ORDERS = "ActualOrders"
WORKSHEET_ACTUAL_POSITIONS = "ActualPositions"
WORKSHEET_STATEMENT_SUMMARIES = "StatementSummaries"
WORKSHEET_UPLOAD_HISTORY = "UploadHistory" #
@st.cache_resource # ใช้ cache_resource สำหรับ gspread client object
def get_gspread_client():
    try:
        if "gcp_service_account" not in st.secrets:
            st.warning("⚠️ โปรดตั้งค่า 'gcp_service_account' ใน `.streamlit/secrets.toml` เพื่อเชื่อมต่อ Google Sheets.")
            return None
        return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการเชื่อมต่อ Google Sheets: {e}")
        st.info("ตรวจสอบว่า 'gcp_service_account' ใน secrets.toml ถูกต้อง และได้แชร์ Sheet กับ Service Account แล้ว")
        return None

# ฟังก์ชันสำหรับโหลดข้อมูล Portfolios
@st.cache_data(ttl=300) # Cache ข้อมูลไว้ 5 นาที
def load_portfolios_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        st.error("ไม่สามารถโหลดข้อมูลพอร์ตได้: Client Google Sheets ไม่พร้อมใช้งาน")
        return pd.DataFrame()

    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PORTFOLIOS)
        records = worksheet.get_all_records()
        
        if not records:
            st.info(f"ไม่พบข้อมูลใน Worksheet '{WORKSHEET_PORTFOLIOS}'.")
            return pd.DataFrame()
        
        df_portfolios = pd.DataFrame(records)
        
        # แปลงคอลัมน์ที่ควรเป็นตัวเลข
        cols_to_numeric_type = {
            'InitialBalance': float, 'ProfitTargetPercent': float, 
            'DailyLossLimitPercent': float, 'TotalStopoutPercent': float,
            'Leverage': float, 'MinTradingDays': int,
            'OverallProfitTarget': float, 'WeeklyProfitTarget': float, 'DailyProfitTarget': float,
            'MaxAcceptableDrawdownOverall': float, 'MaxAcceptableDrawdownDaily': float,
            'ScaleUp_MinWinRate': float, 'ScaleUp_MinGainPercent': float, 'ScaleUp_RiskIncrementPercent': float,
            'ScaleDown_MaxLossPercent': float, 'ScaleDown_LowWinRate': float, 'ScaleDown_RiskDecrementPercent': float,
            'MinRiskPercentAllowed': float, 'MaxRiskPercentAllowed': float, 'CurrentRiskPercent': float
        }
        for col, target_type in cols_to_numeric_type.items():
            if col in df_portfolios.columns:
                df_portfolios[col] = pd.to_numeric(df_portfolios[col], errors='coerce').fillna(0)
                if target_type == int:
                    df_portfolios[col] = df_portfolios[col].astype(int)

        if 'EnableScaling' in df_portfolios.columns: # คอลัมน์นี้ควรเป็น Boolean
             df_portfolios['EnableScaling'] = df_portfolios['EnableScaling'].astype(str).str.upper().map({'TRUE': True, 'YES': True, '1': True, 'FALSE': False, 'NO': False, '0': False}).fillna(False)


        # แปลงคอลัมน์วันที่ ถ้ามี
        date_cols = ['CompetitionEndDate', 'TargetEndDate', 'CreationDate']
        for col in date_cols:
            if col in df_portfolios.columns:
                df_portfolios[col] = pd.to_datetime(df_portfolios[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')


        return df_portfolios
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'.")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios: {e}")
        return pd.DataFrame()

# ===================== SEC 1: PORTFOLIO SELECTION (Sidebar) =======================
df_portfolios_gs = load_portfolios_from_gsheets() # โหลดข้อมูลพอร์ตก่อนส่วน UI อื่นๆ

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

# Initialize session state variables for portfolio selection
if 'active_portfolio_name_gs' not in st.session_state:
    st.session_state.active_portfolio_name_gs = ""
if 'active_portfolio_id_gs' not in st.session_state:
    st.session_state.active_portfolio_id_gs = None
if 'current_portfolio_details' not in st.session_state: # เพิ่มเพื่อเก็บรายละเอียดพอร์ตที่เลือก
    st.session_state.current_portfolio_details = None


portfolio_names_list_gs = [""] # Start with an empty option
if not df_portfolios_gs.empty and 'PortfolioName' in df_portfolios_gs.columns:
    # Filter out NaNs and ensure unique names before sorting
    valid_portfolio_names = sorted(df_portfolios_gs['PortfolioName'].dropna().unique().tolist())
    portfolio_names_list_gs.extend(valid_portfolio_names)

# Ensure current selection is valid
if st.session_state.active_portfolio_name_gs not in portfolio_names_list_gs:
    st.session_state.active_portfolio_name_gs = portfolio_names_list_gs[0] # Default to empty or first valid

selected_portfolio_name_gs = st.sidebar.selectbox(
    "เลือกพอร์ต:",
    options=portfolio_names_list_gs,
    index=portfolio_names_list_gs.index(st.session_state.active_portfolio_name_gs), # Handles if list is empty
    key='sb_active_portfolio_selector_gs'
)

if selected_portfolio_name_gs != "":
    st.session_state.active_portfolio_name_gs = selected_portfolio_name_gs
    if not df_portfolios_gs.empty:
        selected_portfolio_row_df = df_portfolios_gs[df_portfolios_gs['PortfolioName'] == selected_portfolio_name_gs]
        if not selected_portfolio_row_df.empty:
            # Convert the first row to a dictionary
            st.session_state.current_portfolio_details = selected_portfolio_row_df.iloc[0].to_dict()
            if 'PortfolioID' in st.session_state.current_portfolio_details:
                st.session_state.active_portfolio_id_gs = st.session_state.current_portfolio_details['PortfolioID']
            else:
                st.session_state.active_portfolio_id_gs = None
                st.sidebar.warning("ไม่พบ PortfolioID สำหรับพอร์ตที่เลือก.")
        else:
            st.session_state.active_portfolio_id_gs = None
            st.session_state.current_portfolio_details = None
            st.sidebar.warning(f"ไม่พบข้อมูลสำหรับพอร์ตชื่อ '{selected_portfolio_name_gs}'.")
else:
    st.session_state.active_portfolio_name_gs = ""
    st.session_state.active_portfolio_id_gs = None
    st.session_state.current_portfolio_details = None

# Display details of the selected active portfolio
if st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details
    st.sidebar.markdown(f"**💡 ข้อมูลพอร์ต '{details.get('PortfolioName', 'N/A')}'**")
    if pd.notna(details.get('InitialBalance')): st.sidebar.write(f"- Balance เริ่มต้น: {details['InitialBalance']:,.2f} USD")
    if pd.notna(details.get('ProgramType')): st.sidebar.write(f"- ประเภท: {details['ProgramType']}")
    if pd.notna(details.get('Status')): st.sidebar.write(f"- สถานะ: {details['Status']}")
    
    # Display rules based on ProgramType
    if details.get('ProgramType') in ["Prop Firm Challenge", "Funded Account", "Trading Competition"]:
        if pd.notna(details.get('ProfitTargetPercent')): st.sidebar.write(f"- เป้าหมายกำไร: {details['ProfitTargetPercent']:.1f}%")
        if pd.notna(details.get('DailyLossLimitPercent')): st.sidebar.write(f"- Daily Loss Limit: {details['DailyLossLimitPercent']:.1f}%")
        if pd.notna(details.get('TotalStopoutPercent')): st.sidebar.write(f"- Total Stopout: {details['TotalStopoutPercent']:.1f}%")
    # Add more specific details as needed
elif not df_portfolios_gs.empty and selected_portfolio_name_gs == "":
     st.sidebar.info("กรุณาเลือกพอร์ตที่ใช้งานจากรายการ")
elif df_portfolios_gs.empty:
    st.sidebar.warning("ไม่พบข้อมูล Portfolio ใน Google Sheets หรือเกิดข้อผิดพลาดในการโหลด.")


# ========== Function Utility (ต่อจากของเดิม) ==========
def get_today_drawdown(log_source_df, acc_balance_input): # Renamed acc_balance to avoid conflict
    # ... (โค้ดเดิมของลูกพี่ตั้ม) ...
    if log_source_df.empty:
        return 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)
        df_today = log_source_df[log_source_df["Timestamp"].dt.strftime("%Y-%m-%d") == today_str]
        drawdown = df_today["Risk $"].sum()
        return drawdown
    except KeyError: return 0
    except Exception: return 0


def get_performance(log_source_df, mode="week"):
    # ... (โค้ดเดิมของลูกพี่ตั้ม) ...
    if log_source_df.empty: return 0, 0, 0
    try:
        log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)
        now = datetime.now()
        if mode == "week":
            week_start_date = now - pd.Timedelta(days=now.weekday())
            df_period = log_source_df[log_source_df["Timestamp"] >= week_start_date.replace(hour=0, minute=0, second=0, microsecond=0)]
        else:  # month
            month_start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            df_period = log_source_df[log_source_df["Timestamp"] >= month_start_date]
        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0]
        total_trades = win + loss
        winrate = (100 * win / total_trades) if total_trades > 0 else 0
        gain = df_period["Risk $"].sum()
        return winrate, gain, total_trades
    except KeyError: return 0,0,0
    except Exception: return 0,0,0

def save_plan_to_gsheets(plan_data_list, trade_mode_arg, asset_name, risk_percentage, trade_direction, portfolio_id, portfolio_name):
    # ... (โค้dเดิมของลูกพี่ตั้ม สำหรับบันทึกแผน) ...
    gc = get_gspread_client()
    if not gc:
        st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกแผนได้")
        return False
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        timestamp_now = datetime.now()
        rows_to_append = []
        expected_headers_plan = [ # Changed name to avoid conflict
            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",
            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"
        ]
        current_headers_plan = []
        if ws.row_count > 0:
            try: current_headers_plan = ws.row_values(1)
            except Exception: current_headers_plan = []
        
        if not current_headers_plan or all(h == "" for h in current_headers_plan):
            ws.update([expected_headers_plan]) # Use update for single row list
        elif set(current_headers_plan) != set(expected_headers_plan) and any(h!="" for h in current_headers_plan):
             st.warning(f"Worksheet '{WORKSHEET_PLANNED_LOGS}' has incorrect headers. Please ensure headers match: {', '.join(expected_headers_plan)}")

        for idx, plan_entry in enumerate(plan_data_list):
            log_id = f"{timestamp_now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}-{idx}"
            row_data = {
                "LogID": log_id, "PortfolioID": portfolio_id, "PortfolioName": portfolio_name,
                "Timestamp": timestamp_now.strftime("%Y-%m-%d %H:%M:%S"), "Asset": asset_name,
                "Mode": trade_mode_arg, "Direction": trade_direction, "Risk %": risk_percentage,
                "Fibo Level": plan_entry.get("Fibo Level", ""), "Entry": plan_entry.get("Entry", "0.00"),
                "SL": plan_entry.get("SL", "0.00"), "TP": plan_entry.get("TP", "0.00"),
                "Lot": plan_entry.get("Lot", "0.00"), "Risk $": plan_entry.get("Risk $", "0.00"),
                "RR": plan_entry.get("RR", "")
            }
            rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers_plan])
        if rows_to_append:
            ws.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            return True
        return False
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PLANNED_LOGS}'.")
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกแผน: {e}")
        return False

# +++ START: โค้ดใหม่สำหรับฟังก์ชัน save_new_portfolio_to_gsheets +++
def save_new_portfolio_to_gsheets(portfolio_data_dict):
    gc = get_gspread_client() 
    if not gc:
        st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกพอร์ตได้")
        return False
    try:
        sh = gc.open(GOOGLE_SHEET_NAME) 
        ws = sh.worksheet(WORKSHEET_PORTFOLIOS)

        # !!! สำคัญมาก: ลูกพี่ตั้มต้องปรับแก้ลำดับและชื่อคอลัมน์ให้ตรงกับชีต "Portfolios" จริงๆ !!!
        expected_gsheet_headers_portfolio = [ # Changed name to avoid conflict
            'PortfolioID', 'PortfolioName', 'ProgramType', 'EvaluationStep', 
            'Status', 'InitialBalance', 'CreationDate', 
            'ProfitTargetPercent', 'DailyLossLimitPercent', 'TotalStopoutPercent',
            'Leverage', 'MinTradingDays',
            'CompetitionEndDate', 'CompetitionGoalMetric',
            'OverallProfitTarget', 'TargetEndDate', 'WeeklyProfitTarget', 'DailyProfitTarget',
            'MaxAcceptableDrawdownOverall', 'MaxAcceptableDrawdownDaily',
            'EnableScaling', 'ScalingCheckFrequency',
            'ScaleUp_MinWinRate', 'ScaleUp_MinGainPercent', 'ScaleUp_RiskIncrementPercent',
            'ScaleDown_MaxLossPercent', 'ScaleDown_LowWinRate', 'ScaleDown_RiskDecrementPercent',
            'MinRiskPercentAllowed', 'MaxRiskPercentAllowed', 'CurrentRiskPercent',
            'Notes' 
        ]
        
        # Check if headers exist, if not, add them
        current_sheet_headers = []
        if ws.row_count > 0:
            try: current_sheet_headers = ws.row_values(1)
            except Exception: pass # Handle empty sheet case
        
        if not current_sheet_headers or all(h == "" for h in current_sheet_headers) :
             ws.update([expected_gsheet_headers_portfolio]) # Use update for single row list

        new_row_values = [str(portfolio_data_dict.get(header, "")) for header in expected_gsheet_headers_portfolio]
        ws.append_row(new_row_values, value_input_option='USER_ENTERED')
        return True
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}'. กรุณาสร้างชีตนี้ก่อน และใส่ Headers ให้ถูกต้อง")
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกพอร์ตใหม่ไปยัง Google Sheets: {e}")
        st.exception(e) # Show full traceback in logs for debugging
        return False
# +++ END: โค้ดใหม่สำหรับฟังก์ชัน save_new_portfolio_to_gsheets +++


# ===================== SEC 1.5: PORTFOLIO MANAGEMENT UI (Main Area) =======================
def on_program_type_change_v8():
    st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8
with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=True): # Setting expanded=True for easier testing
    st.subheader("พอร์ตทั้งหมดของคุณ")
    # df_portfolios_gs should be loaded globally/module level before this UI section
    # Ensure df_portfolios_gs is available, e.g., df_portfolios_gs = load_portfolios_from_gsheets()
    if 'df_portfolios_gs' not in locals() or df_portfolios_gs.empty:
        st.info("ยังไม่มีข้อมูลพอร์ต หรือยังไม่ได้โหลดข้อมูลพอร์ต โปรดเพิ่มพอร์ตใหม่ด้านล่าง หรือตรวจสอบการเชื่อมต่อ Google Sheets")
    else:
        cols_to_display_pf_table = ['PortfolioID', 'PortfolioName', 'ProgramType', 'EvaluationStep', 'Status', 'InitialBalance']
        cols_exist_pf_table = [col for col in cols_to_display_pf_table if col in df_portfolios_gs.columns]
        if cols_exist_pf_table:
            st.dataframe(df_portfolios_gs[cols_exist_pf_table], use_container_width=True, hide_index=True)
        else:
            st.info("ไม่พบคอลัมน์ที่ต้องการแสดงในตารางพอร์ต (ตรวจสอบ df_portfolios_gs และการโหลดข้อมูล)")

    st.markdown("---")
    st.subheader("➕ เพิ่มพอร์ตใหม่")

    # --- Selectbox for Program Type (OUTSIDE THE FORM for immediate UI update) ---
    program_type_options_outside = ["", "Personal Account", "Prop Firm Challenge", "Funded Account", "Trading Competition"]
    
    if 'exp_pf_type_select_v8_key' not in st.session_state: # Using a distinct key for session state storage
        st.session_state.exp_pf_type_select_v8_key = ""

    def on_program_type_change_v8(): # Renamed callback
        st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8 # Update session state from widget key

    # The selectbox that controls the conditional UI
    st.selectbox(
        "ประเภทพอร์ต (Program Type)*", 
        options=program_type_options_outside, 
        index=program_type_options_outside.index(st.session_state.exp_pf_type_select_v8_key), 
        key="exp_pf_type_selector_widget_v8", # Widget's own key
        on_change=on_program_type_change_v8 
    )
    
    # This variable will hold the value from session_state, updated by the callback
    selected_program_type_to_use_in_form = st.session_state.exp_pf_type_select_v8_key

    st.write(f"**[DEBUG - นอก FORM, หลัง Selectbox] `selected_program_type_to_use_in_form` คือ:** `{selected_program_type_to_use_in_form}`")

    with st.form("new_portfolio_form_main_v8_final", clear_on_submit=True): # Key ใหม่ v8_final
        st.markdown(f"**กรอกข้อมูลพอร์ต (สำหรับประเภท: {selected_program_type_to_use_in_form if selected_program_type_to_use_in_form else 'ยังไม่ได้เลือก'})**")
        
        form_c1_in_form, form_c2_in_form = st.columns(2)
        with form_c1_in_form:
            form_new_portfolio_name_in_form = st.text_input("ชื่อพอร์ต (Portfolio Name)*", key="form_pf_name_v8")
        with form_c2_in_form:
            form_new_initial_balance_in_form = st.number_input("บาลานซ์เริ่มต้น (Initial Balance)*", min_value=0.01, value=10000.0, key="form_pf_balance_v8")
        
        form_status_options_in_form = ["Active", "Inactive", "Pending", "Passed", "Failed"]
        form_new_status_in_form = st.selectbox("สถานะพอร์ต (Status)*", options=form_status_options_in_form, index=0, key="form_pf_status_v8")
        
        form_new_evaluation_step_val_in_form = ""
        if selected_program_type_to_use_in_form == "Prop Firm Challenge":
            st.write(f"**[DEBUG - ใน FORM, ใน IF Evaluation Step] ประเภทคือ:** `{selected_program_type_to_use_in_form}`")
            evaluation_step_options_in_form = ["", "Phase 1", "Phase 2", "Phase 3", "Verification"]
            form_new_evaluation_step_val_in_form = st.selectbox("ขั้นตอนการประเมิน (Evaluation Step)", 
                                                                options=evaluation_step_options_in_form, index=0, 
                                                                key="form_pf_eval_step_select_v8")

        # --- Conditional Inputs Defaults ---
        form_profit_target_val = 8.0; form_daily_loss_val = 5.0; form_total_stopout_val = 10.0; form_leverage_val = 100.0; form_min_days_val = 0
        form_comp_end_date = None; form_comp_goal_metric = ""
        form_pers_overall_profit_val = 0.0; form_pers_target_end_date = None; form_pers_weekly_profit_val = 0.0; form_pers_daily_profit_val = 0.0
        form_pers_max_dd_overall_val = 0.0; form_pers_max_dd_daily_val = 0.0
        form_enable_scaling_checkbox_val = False; form_scaling_freq_val = "Weekly"; form_su_wr_val = 55.0; form_su_gain_val = 2.0; form_su_inc_val = 0.25
        form_sd_loss_val = -5.0; form_sd_wr_val = 40.0; form_sd_dec_val = 0.25; form_min_risk_val = 0.25; form_max_risk_val = 2.0; form_current_risk_val = 1.0
        form_notes_val = ""

        if selected_program_type_to_use_in_form in ["Prop Firm Challenge", "Funded Account"]:
            st.markdown("**กฎเกณฑ์ Prop Firm/Funded:**")
            f_pf1, f_pf2, f_pf3 = st.columns(3)
            with f_pf1: form_profit_target_val = st.number_input("เป้าหมายกำไร %*", value=form_profit_target_val, format="%.1f", key="f_pf_profit_v8")
            with f_pf2: form_daily_loss_val = st.number_input("จำกัดขาดทุนต่อวัน %*", value=form_daily_loss_val, format="%.1f", key="f_pf_dd_v8")
            with f_pf3: form_total_stopout_val = st.number_input("จำกัดขาดทุนรวม %*", value=form_total_stopout_val, format="%.1f", key="f_pf_maxdd_v8")
            f_pf_col1, f_pf_col2 = st.columns(2)
            with f_pf_col1: form_leverage_val = st.number_input("Leverage", value=form_leverage_val, format="%.0f", key="f_pf_lev_v8")
            with f_pf_col2: form_min_days_val = st.number_input("จำนวนวันเทรดขั้นต่ำ", value=form_min_days_val, step=1, key="f_pf_mindays_v8")
        
        if selected_program_type_to_use_in_form == "Trading Competition":
            st.markdown("**ข้อมูลการแข่งขัน:**")
            f_tc1, f_tc2 = st.columns(2)
            with f_tc1: 
                form_comp_end_date = st.date_input("วันสิ้นสุดการแข่งขัน", value=form_comp_end_date, key="f_tc_enddate_v8")
                # For competition, reuse ProfitTarget, DailyLoss, TotalStopout if they share the same variable, or use new ones
                form_profit_target_val_comp = st.number_input("เป้าหมายกำไร % (Comp)", value=20.0, format="%.1f", key="f_tc_profit_v8") 
            with f_tc2: 
                form_comp_goal_metric = st.text_input("ตัวชี้วัดเป้าหมาย (Comp)", value=form_comp_goal_metric, help="เช่น %Gain, ROI", key="f_tc_goalmetric_v8")
                form_daily_loss_val_comp = st.number_input("จำกัดขาดทุนต่อวัน % (Comp)", value=5.0, format="%.1f", key="f_tc_dd_v8")
                form_total_stopout_val_comp = st.number_input("จำกัดขาดทุนรวม % (Comp)", value=10.0, format="%.1f", key="f_tc_maxdd_v8")

        if selected_program_type_to_use_in_form == "Personal Account":
            st.markdown("**เป้าหมายส่วนตัว (Optional):**")
            f_ps1, f_ps2 = st.columns(2)
            with f_ps1:
                form_pers_overall_profit_val = st.number_input("เป้าหมายกำไรโดยรวม ($)", value=form_pers_overall_profit_val, format="%.2f", key="f_ps_profit_overall_v8")
                form_pers_weekly_profit_val = st.number_input("เป้าหมายกำไรรายสัปดาห์ ($)", value=form_pers_weekly_profit_val, format="%.2f", key="f_ps_profit_weekly_v8")
                form_pers_max_dd_overall_val = st.number_input("Max DD รวมที่ยอมรับได้ ($)", value=form_pers_max_dd_overall_val, format="%.2f", key="f_ps_dd_overall_v8")
            with f_ps2:
                form_pers_target_end_date = st.date_input("วันที่คาดว่าจะถึงเป้าหมายรวม", value=form_pers_target_end_date, key="f_ps_enddate_v8")
                form_pers_daily_profit_val = st.number_input("เป้าหมายกำไรรายวัน ($)", value=form_pers_daily_profit_val, format="%.2f", key="f_ps_profit_daily_v8")
                form_pers_max_dd_daily_val = st.number_input("Max DD ต่อวันที่ยอมรับได้ ($)", value=form_pers_max_dd_daily_val, format="%.2f", key="f_ps_dd_daily_v8")

        st.markdown("**การตั้งค่า Scaling Manager (Optional):**")
        form_enable_scaling_checkbox_val = st.checkbox("เปิดใช้งาน Scaling Manager?", value=form_enable_scaling_checkbox_val, key="f_scale_enable_v8")
        if form_enable_scaling_checkbox_val:
            f_sc1, f_sc2, f_sc3 = st.columns(3)
            with f_sc1:
                form_scaling_freq_val = st.selectbox("ความถี่ตรวจสอบ Scaling", ["Weekly", "Monthly"], index=["Weekly", "Monthly"].index(form_scaling_freq_val), key="f_scale_freq_v8")
                form_su_wr_val = st.number_input("Scale Up: Min Winrate %", value=form_su_wr_val, format="%.1f", key="f_scale_su_wr_v8")
                form_sd_loss_val = st.number_input("Scale Down: Max Loss %", value=form_sd_loss_val, format="%.1f", key="f_scale_sd_loss_v8")
            with f_sc2:
                form_min_risk_val = st.number_input("Min Risk % Allowed", value=form_min_risk_val, format="%.2f", key="f_scale_min_risk_v8")
                form_su_gain_val = st.number_input("Scale Up: Min Gain %", value=form_su_gain_val, format="%.1f", key="f_scale_su_gain_v8")
                form_sd_wr_val = st.number_input("Scale Down: Low Winrate %", value=form_sd_wr_val, format="%.1f", key="f_scale_sd_wr_v8")
            with f_sc3:
                form_max_risk_val = st.number_input("Max Risk % Allowed", value=form_max_risk_val, format="%.2f", key="f_scale_max_risk_v8")
                form_su_inc_val = st.number_input("Scale Up: Risk Increment %", value=form_su_inc_val, format="%.2f", key="f_scale_su_inc_v8")
                form_sd_dec_val = st.number_input("Scale Down: Risk Decrement %", value=form_sd_dec_val, format="%.2f", key="f_scale_sd_dec_v8")
            form_current_risk_val = st.number_input("Current Risk % (สำหรับ Scaling)", value=form_current_risk_val, format="%.2f", key="f_scale_current_risk_v8")

        form_notes_val = st.text_area("หมายเหตุเพิ่มเติม (Notes)", value=form_notes_val, key="f_pf_notes_v8")

        submitted_add_portfolio_in_form = st.form_submit_button("💾 บันทึกพอร์ตใหม่")
        
        if submitted_add_portfolio_in_form:
            if not form_new_portfolio_name_in_form or not selected_program_type_to_use_in_form or not form_new_status_in_form or form_new_initial_balance_in_form <= 0:
                st.warning("กรุณากรอกข้อมูลที่จำเป็น (*) ให้ครบถ้วนและถูกต้อง: ชื่อพอร์ต, ประเภทพอร์ต, สถานะพอร์ต, และยอดเงินเริ่มต้นต้องมากกว่า 0")
            elif 'df_portfolios_gs' in locals() and not df_portfolios_gs.empty and form_new_portfolio_name_in_form in df_portfolios_gs['PortfolioName'].astype(str).values:
                st.error(f"ชื่อพอร์ต '{form_new_portfolio_name_in_form}' มีอยู่แล้ว กรุณาใช้ชื่ออื่น")
            else:
                new_id_value = str(uuid.uuid4())
                
                # Prepare data for saving, ensuring conditional values are handled
                data_to_save = {
                    'PortfolioID': new_id_value,
                    'PortfolioName': form_new_portfolio_name_in_form, 
                    'ProgramType': selected_program_type_to_use_in_form,
                    'EvaluationStep': form_new_evaluation_step_val_in_form if selected_program_type_to_use_in_form == "Prop Firm Challenge" else "", 
                    'Status': form_new_status_in_form,
                    'InitialBalance': form_new_initial_balance_in_form, 
                    'CreationDate': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'Notes': form_notes_val
                }

                if selected_program_type_to_use_in_form in ["Prop Firm Challenge", "Funded Account"]:
                    data_to_save['ProfitTargetPercent'] = form_profit_target_val
                    data_to_save['DailyLossLimitPercent'] = form_daily_loss_val
                    data_to_save['TotalStopoutPercent'] = form_total_stopout_val
                    data_to_save['Leverage'] = form_leverage_val
                    data_to_save['MinTradingDays'] = form_min_days_val
                
                if selected_program_type_to_use_in_form == "Trading Competition":
                    data_to_save['CompetitionEndDate'] = form_comp_end_date.strftime("%Y-%m-%d") if form_comp_end_date else None
                    data_to_save['CompetitionGoalMetric'] = form_comp_goal_metric
                    # Overwrite or use specific competition profit/loss targets if different
                    data_to_save['ProfitTargetPercent'] = form_profit_target_val_comp # Using specific comp variable
                    data_to_save['DailyLossLimitPercent'] = form_daily_loss_val_comp
                    data_to_save['TotalStopoutPercent'] = form_total_stopout_val_comp


                if selected_program_type_to_use_in_form == "Personal Account":
                    data_to_save['OverallProfitTarget'] = form_pers_overall_profit_val
                    data_to_save['TargetEndDate'] = form_pers_target_end_date.strftime("%Y-%m-%d") if form_pers_target_end_date else None
                    data_to_save['WeeklyProfitTarget'] = form_pers_weekly_profit_val
                    data_to_save['DailyProfitTarget'] = form_pers_daily_profit_val
                    data_to_save['MaxAcceptableDrawdownOverall'] = form_pers_max_dd_overall_val
                    data_to_save['MaxAcceptableDrawdownDaily'] = form_pers_max_dd_daily_val

                if form_enable_scaling_checkbox_val:
                    data_to_save['EnableScaling'] = True
                    data_to_save['ScalingCheckFrequency'] = form_scaling_freq_val
                    data_to_save['ScaleUp_MinWinRate'] = form_su_wr_val
                    data_to_save['ScaleUp_MinGainPercent'] = form_su_gain_val
                    data_to_save['ScaleUp_RiskIncrementPercent'] = form_su_inc_val
                    data_to_save['ScaleDown_MaxLossPercent'] = form_sd_loss_val
                    data_to_save['ScaleDown_LowWinRate'] = form_sd_wr_val
                    data_to_save['ScaleDown_RiskDecrementPercent'] = form_sd_dec_val
                    data_to_save['MinRiskPercentAllowed'] = form_min_risk_val
                    data_to_save['MaxRiskPercentAllowed'] = form_max_risk_val
                    data_to_save['CurrentRiskPercent'] = form_current_risk_val
                else:
                    data_to_save['EnableScaling'] = False
                    # Set other scaling fields to None or default empty if scaling is disabled
                    for scale_key in ['ScalingCheckFrequency', 'ScaleUp_MinWinRate', 'ScaleUp_MinGainPercent', 
                                      'ScaleUp_RiskIncrementPercent', 'ScaleDown_MaxLossPercent', 'ScaleDown_LowWinRate', 
                                      'ScaleDown_RiskDecrementPercent', 'MinRiskPercentAllowed', 'MaxRiskPercentAllowed']:
                        data_to_save[scale_key] = None
                    data_to_save['CurrentRiskPercent'] = form_current_risk_val # Still save current risk

                success_save = save_new_portfolio_to_gsheets(data_to_save) 
                
                if success_save:
                    st.success(f"เพิ่มพอร์ต '{form_new_portfolio_name_in_form}' (ID: {new_id_value}) สำเร็จ!")
                    st.session_state.exp_pf_type_select_v8_key = "" # Reset selectboxนอกฟอร์ม
                    if hasattr(load_portfolios_from_gsheets, 'clear'):
                         load_portfolios_from_gsheets.clear()
                    st.rerun()
                else:
                    st.error("เกิดข้อผิดพลาดในการบันทึกพอร์ตใหม่ไปยัง Google Sheets")
# ==============================================================================
# END: ส่วนจัดการ Portfolio (SEC 1.5)
# ==============================================================================

# ===================== SEC 2.1: COMMON INPUTS & MODE SELECTION =======================
drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=st.session_state.get("drawdown_limit_pct", 2.0),
    step=0.1, format="%.1f",
    key="drawdown_limit_pct"
)

mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")

# ใน SEC 2.1: COMMON INPUTS & MODE SELECTION
# แทนที่โค้ดส่วน if st.sidebar.button("🔄 Reset Form"): เดิมด้วยโค้ดนี้

if st.sidebar.button("🔄 Reset Form"):
    # ค่าที่ต้องการคงไว้หลังจากการ Reset
    mode_to_keep = st.session_state.get("mode", "FIBO")
    dd_limit_to_keep = st.session_state.get("drawdown_limit_pct", 2.0)
    
    # ข้อมูล Portfolio ที่สำคัญ
    active_portfolio_name_gs_keep = st.session_state.get('active_portfolio_name_gs', "")
    active_portfolio_id_gs_keep = st.session_state.get('active_portfolio_id_gs', None)
    current_portfolio_details_keep = st.session_state.get('current_portfolio_details', None)
    current_account_balance_keep = st.session_state.get('current_account_balance', 10000.0)
    # สถานะ UI ของการเลือกประเภทพอร์ตใน Portfolio Management
    exp_pf_type_select_v8_key_keep = st.session_state.get("exp_pf_type_select_v8_key", "")
    # สถานะ UI ของตัวเลือก active portfolio ใน sidebar
    sb_active_portfolio_selector_gs_keep = st.session_state.get('sb_active_portfolio_selector_gs', "")


    # ค่าที่ควรจะคงอยู่ตลอดการใช้งานแอป (เช่น gcp_service_account ถ้ามาจาก secrets)
    keys_to_fully_preserve = {"gcp_service_account"}
    temp_preserved_values = {}
    for k_fp in keys_to_fully_preserve:
        if k_fp in st.session_state:
            temp_preserved_values[k_fp] = st.session_state[k_fp]

    # ล้าง session state ส่วนใหญ่
    for key in list(st.session_state.keys()):
        if key not in keys_to_fully_preserve:
            try:
                del st.session_state[key]
            except KeyError:
                pass # อาจจะถูกลบไปแล้วใน loop ก่อนหน้า ถ้ามี key ซ้ำซ้อน (ไม่น่าเกิด)
            
    # คืนค่าที่ preserve ไว้
    for k_fp, v_fp in temp_preserved_values.items():
        st.session_state[k_fp] = v_fp

    # คืนค่า/ตั้งค่าเริ่มต้นที่จำเป็น
    st.session_state.mode = mode_to_keep
    st.session_state.drawdown_limit_pct = dd_limit_to_keep
    st.session_state.active_portfolio_name_gs = active_portfolio_name_gs_keep
    st.session_state.active_portfolio_id_gs = active_portfolio_id_gs_keep
    st.session_state.current_portfolio_details = current_portfolio_details_keep
    st.session_state.current_account_balance = current_account_balance_keep
    st.session_state.exp_pf_type_select_v8_key = exp_pf_type_select_v8_key_keep
    if sb_active_portfolio_selector_gs_keep: # คืนค่าตัวเลือก portfolio ถ้ามี
        st.session_state.sb_active_portfolio_selector_gs = sb_active_portfolio_selector_gs_keep


    # คำนวณ default_risk จาก current_portfolio_details ที่คงไว้
    default_risk = 1.0 # ค่า fallback
    if current_portfolio_details_keep: # ใช้ current_portfolio_details_keep ที่ถูก preserve ไว้
        risk_val_str = current_portfolio_details_keep.get('CurrentRiskPercent')
        if pd.notna(risk_val_str) and str(risk_val_str).strip() != "":
            try:
                risk_val_float = float(risk_val_str)
                if risk_val_float > 0:
                    default_risk = risk_val_float
            except (ValueError, TypeError):
                pass # ใช้ default_risk ถ้าแปลงไม่ได้

    st.session_state.risk_pct_fibo_val_v2 = default_risk
    st.session_state.asset_fibo_val_v2 = "XAUUSD" # ตั้งค่า Asset เริ่มต้น
    st.session_state.risk_pct_custom_val_v2 = default_risk
    st.session_state.asset_custom_val_v2 = "XAUUSD" # ตั้งค่า Asset เริ่มต้น

    # ตั้งค่าเริ่มต้นสำหรับ FIBO
    st.session_state.swing_high_fibo_val_v2 = ""
    st.session_state.swing_low_fibo_val_v2 = ""
    # fibos_fibo_v2 ถูก define ใน SEC 2.2 ซึ่งมี 5 ตัว
    st.session_state.fibo_flags_v2 = [False] * 5 # ตั้งค่าให้ Fibo levels ถูก check ทั้งหมด

    # ตั้งค่าเริ่มต้นสำหรับ CUSTOM
    default_n_entries = 2
    st.session_state.n_entry_custom_val_v2 = default_n_entries
    for i in range(default_n_entries):
        st.session_state[f"custom_entry_{i}_v3"] = "0.00"
        st.session_state[f"custom_sl_{i}_v3"] = "0.00"
        st.session_state[f"custom_tp_{i}_v3"] = "0.00"
        
    # ล้างข้อมูล plot data ถ้ามี
    if 'plot_data' in st.session_state:
        del st.session_state['plot_data']
        
    st.toast("รีเซ็ตฟอร์มเรียบร้อยแล้ว!", icon="🔄")
    st.rerun()

# ===================== SEC 2.2: FIBO TRADE DETAILS =======================
# <<< ลูกพี่ตั้มต้องแน่ใจว่าโค้ดส่วนนี้ถูกวางไว้ในตำแหน่งที่ถูกต้อง >>>
# <<< คือ หลัง SEC 1 (ที่ st.session_state.current_portfolio_details ถูกกำหนด) >>>
# <<< และ ก่อนที่จะเริ่ม SEC 2.2 หรือ SEC 2.3 >>>

# --- ดึงค่า InitialBalance และ CurrentRiskPercent จาก Active Portfolio ---
active_balance_to_use = st.session_state.get('current_account_balance', 10000.0) # Fallback

initial_risk_pct_from_portfolio = 1.0 # Default
if 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details
    current_risk_val_str = details.get('CurrentRiskPercent') # สมมติว่าในชีต Portfolios มีคอลัมน์นี้
    if pd.notna(current_risk_val_str) and str(current_risk_val_str).strip() != "":
        try:
            risk_val_float = float(current_risk_val_str)
            if risk_val_float > 0:
                 initial_risk_pct_from_portfolio = risk_val_float
        except (ValueError, TypeError):
            pass # ใช้ค่า default ถ้าแปลงไม่ได้

# ===================== SEC 2.2: FIBO TRADE DETAILS =======================
if mode == "FIBO": # mode ควรจะถูก define ใน SEC 2.1
    col1_fibo_v2, col2_fibo_v2, col3_fibo_v2 = st.sidebar.columns([2, 2, 2])
    with col1_fibo_v2:
        asset_fibo_v2 = st.text_input("Asset", 
                                   value=st.session_state.get("asset_fibo_val_v2", "XAUUSD"), 
                                   key="asset_fibo_input_v3") # Key ใหม่
        st.session_state.asset_fibo_val_v2 = asset_fibo_v2
    with col2_fibo_v2:
        risk_pct_fibo_v2 = st.number_input(
            "Risk %",
            min_value=0.01, max_value=100.0,
            value=st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio), # <<< ใช้ค่าจาก Active Portfolio
            step=0.01, format="%.2f",
            key="risk_pct_fibo_input_v3") # Key ใหม่
        st.session_state.risk_pct_fibo_val_v2 = risk_pct_fibo_v2
    with col3_fibo_v2:
        # ตรวจสอบว่า key "direction_fibo_val_v2" มีใน session_state หรือยัง
        default_direction_index = 0 # Default to "Long"
        if "direction_fibo_val_v2" in st.session_state:
            if st.session_state.direction_fibo_val_v2 == "Short":
                default_direction_index = 1
        
        direction_fibo_v2 = st.radio("Direction", ["Long", "Short"], 
                                  index=default_direction_index,
                                  horizontal=True, key="fibo_direction_radio_v3") # Key ใหม่
        st.session_state.direction_fibo_val_v2 = direction_fibo_v2

    col4_fibo_v2, col5_fibo_v2 = st.sidebar.columns(2)
    with col4_fibo_v2:
        swing_high_fibo_v2 = st.text_input("High", 
                                        value=st.session_state.get("swing_high_fibo_val_v2", ""),
                                        key="swing_high_fibo_input_v3") # Key ใหม่
        st.session_state.swing_high_fibo_val_v2 = swing_high_fibo_v2
    with col5_fibo_v2:
        swing_low_fibo_v2 = st.text_input("Low", 
                                       value=st.session_state.get("swing_low_fibo_val_v2", ""),
                                       key="swing_low_fibo_input_v3") # Key ใหม่
        st.session_state.swing_low_fibo_val_v2 = swing_low_fibo_v2

    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibos_fibo_v2 = [0.114, 0.25, 0.382, 0.5, 0.618] # เปลี่ยนชื่อตัวแปร
    labels_fibo_v2 = [f"{l:.3f}" for l in fibos_fibo_v2]
    cols_fibo_v2 = st.sidebar.columns(len(fibos_fibo_v2))

    if "fibo_flags_v2" not in st.session_state: # Key ใหม่
        st.session_state.fibo_flags_v2 = [True] * len(fibos_fibo_v2)

    fibo_selected_flags_v2 = []
    for i, col_fibo_v2_loop in enumerate(cols_fibo_v2): # เปลี่ยนชื่อตัวแปร
        checked_fibo_v2 = col_fibo_v2_loop.checkbox(labels_fibo_v2[i], 
                                                 value=st.session_state.fibo_flags_v2[i], 
                                                 key=f"fibo_cb_{i}_v3") # Key ใหม่
        fibo_selected_flags_v2.append(checked_fibo_v2)
    st.session_state.fibo_flags_v2 = fibo_selected_flags_v2

    try:
        high_val_fibo_v2 = float(swing_high_fibo_v2) if swing_high_fibo_v2 else 0
        low_val_fibo_v2 = float(swing_low_fibo_v2) if swing_low_fibo_v2 else 0
        if swing_high_fibo_v2 and swing_low_fibo_v2 and high_val_fibo_v2 <= low_val_fibo_v2:
            st.sidebar.warning("High ต้องมากกว่า Low!")
    except ValueError:
        if swing_high_fibo_v2 or swing_low_fibo_v2:
            st.sidebar.warning("กรุณาใส่ High/Low เป็นตัวเลขที่ถูกต้อง")
    except Exception:
        pass

    if risk_pct_fibo_v2 <= 0: # ใช้ risk_pct_fibo_v2
        st.sidebar.warning("Risk% ต้องมากกว่า 0")

    st.sidebar.markdown("---")
    try:
        high_preview_fibo_v2 = float(swing_high_fibo_v2)
        low_preview_fibo_v2 = float(swing_low_fibo_v2)
        if high_preview_fibo_v2 > low_preview_fibo_v2 and any(st.session_state.fibo_flags_v2):
            st.sidebar.markdown("**Preview (เบื้องต้น):**")
            first_selected_fibo_index_v2 = st.session_state.fibo_flags_v2.index(True)
            if direction_fibo_v2 == "Long":
                preview_entry_fibo_v2 = low_preview_fibo_v2 + (high_preview_fibo_v2 - low_preview_fibo_v2) * fibos_fibo_v2[first_selected_fibo_index_v2]
            else:
                preview_entry_fibo_v2 = high_preview_fibo_v2 - (high_preview_fibo_v2 - low_preview_fibo_v2) * fibos_fibo_v2[first_selected_fibo_index_v2]
            st.sidebar.markdown(f"Entry แรกที่เลือก ≈ **{preview_entry_fibo_v2:.2f}**")
            st.sidebar.caption("Lot/TP/ผลลัพธ์เต็มอยู่ด้านล่าง (ใน Strategy Summary)")
    except Exception:
        pass

    save_fibo = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo_v3") # Key ใหม่

# ===================== SEC 2.3: CUSTOM TRADE DETAILS =======================
elif mode == "CUSTOM": # mode ควรจะถูก define ใน SEC 2.1
    col1_custom_v2, col2_custom_v2, col3_custom_v2 = st.sidebar.columns([2, 2, 2])
    with col1_custom_v2:
        asset_custom_v2 = st.text_input("Asset", 
                                     value=st.session_state.get("asset_custom_val_v2", "XAUUSD"), 
                                     key="asset_custom_input_v3") # Key ใหม่
        st.session_state.asset_custom_val_v2 = asset_custom_v2
    with col2_custom_v2:
        risk_pct_custom_v2 = st.number_input( 
            "Risk %",
            min_value=0.01, max_value=100.0,
            value=st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio), # <<< ใช้ค่าจาก Active Portfolio
            step=0.01, format="%.2f",
            key="risk_pct_custom_input_v3") # Key ใหม่
        st.session_state.risk_pct_custom_val_v2 = risk_pct_custom_v2
    with col3_custom_v2:
        n_entry_custom_v2 = st.number_input( 
            "จำนวนไม้",
            min_value=1, max_value=10,
            value=st.session_state.get("n_entry_custom_val_v2", 2), 
            step=1,
            key="n_entry_custom_input_v3") # Key ใหม่
        st.session_state.n_entry_custom_val_v2 = n_entry_custom_v2

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")
    custom_inputs_v2 = [] # เปลี่ยนชื่อตัวแปร
    
    current_custom_risk_pct_v2 = risk_pct_custom_v2 
    risk_per_trade_custom_v2 = current_custom_risk_pct_v2 / 100
    
    # --- แก้ไขการคำนวณ risk_dollar_total ---
    risk_dollar_total_custom_v2 = active_balance_to_use * risk_per_trade_custom_v2 # <<< ใช้ active_balance_to_use
    
    num_entries_val_custom_v2 = n_entry_custom_v2
    risk_dollar_per_entry_custom_v2 = risk_dollar_total_custom_v2 / num_entries_val_custom_v2 if num_entries_val_custom_v2 > 0 else 0

    for i in range(int(num_entries_val_custom_v2)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e_v2, col_s_v2, col_t_v2 = st.sidebar.columns(3)
        entry_key_v2 = f"custom_entry_{i}_v3" # Key ใหม่
        sl_key_v2 = f"custom_sl_{i}_v3"       # Key ใหม่
        tp_key_v2 = f"custom_tp_{i}_v3"       # Key ใหม่

        if entry_key_v2 not in st.session_state: st.session_state[entry_key_v2] = "0.00"
        if sl_key_v2 not in st.session_state: st.session_state[sl_key_v2] = "0.00"
        if tp_key_v2 not in st.session_state: st.session_state[tp_key_v2] = "0.00"

        with col_e_v2:
            entry_str_v2 = st.text_input(f"Entry {i+1}", value=st.session_state[entry_key_v2], key=entry_key_v2)
        with col_s_v2:
            sl_str_v2 = st.text_input(f"SL {i+1}", value=st.session_state[sl_key_v2], key=sl_key_v2)
        with col_t_v2:
            tp_str_v2 = st.text_input(f"TP {i+1}", value=st.session_state[tp_key_v2], key=tp_key_v2)
        
        try:
            entry_float_v2 = float(entry_str_v2)
            sl_float_v2 = float(sl_str_v2)
            stop_val_v2 = abs(entry_float_v2 - sl_float_v2)
            lot_val_v2 = risk_dollar_per_entry_custom_v2 / stop_val_v2 if stop_val_v2 > 0 else 0
            lot_display_str_v2 = f"Lot: {lot_val_v2:.2f}" if stop_val_v2 > 0 else "Lot: - (Invalid SL)"
            risk_per_entry_display_str_v2 = f"Risk$ ต่อไม้: {risk_dollar_per_entry_custom_v2:.2f}"
        except ValueError:
            lot_display_str_v2 = "Lot: - (Error)"
            risk_per_entry_display_str_v2 = "Risk$ ต่อไม้: - (Error)"
            stop_val_v2 = None
        except Exception:
            lot_display_str_v2 = "Lot: -"
            risk_per_entry_display_str_v2 = "Risk$ ต่อไม้: -"
            stop_val_v2 = None

        try:
            if stop_val_v2 is not None and stop_val_v2 > 0:
                tp_rr3_info_str_v2 = f"Stop: {stop_val_v2:.2f}"
            else:
                tp_rr3_info_str_v2 = "Stop: - (SL Error)"
        except Exception:
            tp_rr3_info_str_v2 = "Stop: -"
        
        st.sidebar.caption(f"{lot_display_str_v2} | {risk_per_entry_display_str_v2} | {tp_rr3_info_str_v2}")
        custom_inputs_v2.append({"entry": entry_str_v2, "sl": sl_str_v2, "tp": tp_str_v2})

    if current_custom_risk_pct_v2 <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")
    save_custom = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom_v3") # Key ใหม่

# ===================== SEC 3: SIDEBAR - CALCULATIONS, SUMMARY & ACTIONS =======================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")

# Initialize summary variables (these are for display, should be updated after calculations)
summary_total_lots = 0.0
summary_total_risk_dollar = 0.0
summary_avg_rr = 0.0
summary_total_profit_at_primary_tp = 0.0
custom_tp_recommendation_messages = [] # Kept for CUSTOM mode

# Define new effective TP ratios (used in FIBO mode calculations below)
RATIO_TP1_EFF = 1.618108 # Effective ratio for TP1
RATIO_TP2_EFF = 2.618108 # Effective ratio for TP2
RATIO_TP3_EFF = 4.325946 # Effective ratio for TP3

# --- START: CRITICAL INITIALIZATION FOR NameError ---
# Ensure these list variables always exist before being potentially populated or accessed.
entry_data_summary_sec3 = []
custom_entries_summary_sec3 = []
# --- END: CRITICAL INITIALIZATION FOR NameError ---

if mode == "FIBO":
    # The variable 'entry_data_summary_sec3' is already initialized as [] globally for SEC 3.
    # It will be populated below if conditions are met.
    try:
        h_input_str_fibo = st.session_state.get("swing_high_fibo_val_v2", "")
        l_input_str_fibo = st.session_state.get("swing_low_fibo_val_v2", "")
        direction_fibo = st.session_state.get("direction_fibo_val_v2", "Long")
        risk_pct_fibo = st.session_state.get("risk_pct_fibo_val_v2", 1.0)

        if 'fibos_fibo_v2' not in locals() and 'fibos_fibo_v2' not in globals():
             fibos_fibo_v2 = [0.114, 0.25, 0.382, 0.5, 0.618]
        current_fibo_flags_fibo = st.session_state.get("fibo_flags_v2", [True] * len(fibos_fibo_v2))

        if not h_input_str_fibo or not l_input_str_fibo:
            st.sidebar.info("กรอก High และ Low (FIBO) เพื่อคำนวณ Summary")
            # entry_data_summary_sec3 remains []
        else:
            high_fibo_input = float(h_input_str_fibo)
            low_fibo_input = float(l_input_str_fibo)
            
            valid_hl_fibo = False
            fibo_0_percent_level_calc = 0.0 

            if direction_fibo == "Long":
                if high_fibo_input > low_fibo_input:
                    fibo_0_percent_level_calc = low_fibo_input
                    valid_hl_fibo = True
                else:
                    st.sidebar.warning("Long: Swing High ที่กรอก ต้องมากกว่า Swing Low ที่กรอก!")
            else: # Short
                if high_fibo_input > low_fibo_input:
                    fibo_0_percent_level_calc = high_fibo_input
                    valid_hl_fibo = True
                else:
                    st.sidebar.warning("Short: Swing High ที่กรอก ต้องมากกว่า Swing Low ที่กรอก!")

            if not valid_hl_fibo:
                pass # entry_data_summary_sec3 remains []
            elif risk_pct_fibo <= 0:
                st.sidebar.warning("Risk % (FIBO) ต้องมากกว่า 0")
                # entry_data_summary_sec3 remains []
            else:
                range_fibo_calc = abs(high_fibo_input - low_fibo_input)

                if range_fibo_calc <= 1e-9:
                    st.sidebar.warning("Range ระหว่าง High และ Low ต้องมากกว่า 0 อย่างมีนัยสำคัญ")
                    # entry_data_summary_sec3 remains []
                else:
                    global_tp1_fibo, global_tp2_fibo, global_tp3_fibo = 0.0, 0.0, 0.0
                    if direction_fibo == "Long":
                        global_tp1_fibo = fibo_0_percent_level_calc + (range_fibo_calc * RATIO_TP1_EFF)
                        # global_tp2_fibo and global_tp3_fibo are calculated but not used per leg for saving
                    else: # Short
                        global_tp1_fibo = fibo_0_percent_level_calc - (range_fibo_calc * RATIO_TP1_EFF)
                        # Similar for global_tp2_fibo, global_tp3_fibo

                    selected_fibo_levels_count = sum(current_fibo_flags_fibo)
                    if selected_fibo_levels_count > 0:
                        risk_dollar_total_fibo_plan = active_balance_to_use * (risk_pct_fibo / 100.0)
                        risk_dollar_per_entry_fibo = risk_dollar_total_fibo_plan / selected_fibo_levels_count
                        
                        temp_fibo_rr_to_tp1_list = []
                        temp_fibo_entry_details_for_saving = [] # Initialize here for this specific calculation path

                        for i, is_selected_fibo in enumerate(current_fibo_flags_fibo):
                            if is_selected_fibo:
                                fibo_ratio_for_entry = fibos_fibo_v2[i]
                                entry_price_fibo, sl_price_fibo_final = 0.0, 0.0

                                if direction_fibo == "Long":
                                    entry_price_fibo = fibo_0_percent_level_calc + (range_fibo_calc * fibo_ratio_for_entry)
                                    if abs(fibo_ratio_for_entry - 0.5) < 1e-4:
                                        sl_price_fibo_final = fibo_0_percent_level_calc + (range_fibo_calc * ((0.25 + 0.382) / 2.0))
                                    elif abs(fibo_ratio_for_entry - 0.618) < 1e-4:
                                        sl_price_fibo_final = fibo_0_percent_level_calc + (range_fibo_calc * ((0.382 + 0.5) / 2.0))
                                    else: 
                                        sl_price_fibo_final = fibo_0_percent_level_calc 
                                else: # Short
                                    entry_price_fibo = fibo_0_percent_level_calc - (range_fibo_calc * fibo_ratio_for_entry)
                                    if abs(fibo_ratio_for_entry - 0.5) < 1e-4: 
                                        sl_price_fibo_final = fibo_0_percent_level_calc - (range_fibo_calc * ((0.25 + 0.382) / 2.0))
                                    elif abs(fibo_ratio_for_entry - 0.618) < 1e-4: 
                                        sl_price_fibo_final = fibo_0_percent_level_calc - (range_fibo_calc * ((0.382 + 0.5) / 2.0))
                                    else: 
                                        sl_price_fibo_final = fibo_0_percent_level_calc 
                                
                                stop_distance_fibo = abs(entry_price_fibo - sl_price_fibo_final)
                                lot_size_fibo, actual_risk_dollar_fibo = 0.0, 0.0
                                if stop_distance_fibo > 1e-9:
                                    lot_size_fibo = risk_dollar_per_entry_fibo / stop_distance_fibo
                                    actual_risk_dollar_fibo = lot_size_fibo * stop_distance_fibo
                                else:
                                    actual_risk_dollar_fibo = risk_dollar_per_entry_fibo

                                profit_at_tp1_fibo, rr_to_tp1_fibo = 0.0, 0.0
                                if stop_distance_fibo > 1e-9:
                                    price_diff_to_tp1 = abs(global_tp1_fibo - entry_price_fibo)
                                    if (direction_fibo == "Long" and global_tp1_fibo > entry_price_fibo) or \
                                       (direction_fibo == "Short" and global_tp1_fibo < entry_price_fibo):
                                        profit_at_tp1_fibo = lot_size_fibo * price_diff_to_tp1
                                        rr_to_tp1_fibo = price_diff_to_tp1 / stop_distance_fibo
                                        temp_fibo_rr_to_tp1_list.append(rr_to_tp1_fibo)
                                    else: 
                                        rr_to_tp1_fibo = 0.0 
                                        profit_at_tp1_fibo = 0.0
                                else:
                                    rr_to_tp1_fibo = 0.0
                                
                                summary_total_lots += lot_size_fibo
                                summary_total_risk_dollar += actual_risk_dollar_fibo 
                                summary_total_profit_at_primary_tp += profit_at_tp1_fibo

                                temp_fibo_entry_details_for_saving.append({
                                    "Fibo Level": f"{fibo_ratio_for_entry:.3f}",
                                    "Entry": round(entry_price_fibo, 5), 
                                    "SL": round(sl_price_fibo_final, 5),  
                                    "Lot": round(lot_size_fibo, 2),      
                                    "Risk $": round(actual_risk_dollar_fibo, 2), 
                                    "TP": round(global_tp1_fibo, 5),    
                                    "RR": round(rr_to_tp1_fibo, 2)      
                                })
                        
                        entry_data_summary_sec3 = temp_fibo_entry_details_for_saving # Assign populated list

                        if temp_fibo_rr_to_tp1_list:
                            valid_rrs = [r for r in temp_fibo_rr_to_tp1_list if isinstance(r, (float, int)) and r > 0]
                            summary_avg_rr = np.mean(valid_rrs) if valid_rrs else 0.0
                        else:
                            summary_avg_rr = 0.0
                    else:
                        st.sidebar.info("กรุณาเลือก Fibo Level สำหรับ Entry")
                        # entry_data_summary_sec3 remains []
            
    except ValueError:
        if st.session_state.get("swing_high_fibo_val_v2", "") or st.session_state.get("swing_low_fibo_val_v2", ""):
             st.sidebar.warning("กรอก High/Low (FIBO) เป็นตัวเลข")
        # entry_data_summary_sec3 remains []
    except Exception as e_fibo_summary:
        st.sidebar.error(f"คำนวณ FIBO Summary ไม่สำเร็จ: {e_fibo_summary}")
        st.exception(e_fibo_summary) 
        # entry_data_summary_sec3 remains []

elif mode == "CUSTOM":
    # The variable 'custom_entries_summary_sec3' is already initialized as [] globally for SEC 3.
    # It will be populated below.
    try:
        n_entry_custom = st.session_state.get("n_entry_custom_val_v2", 1)
        risk_pct_custom = st.session_state.get("risk_pct_custom_val_v2", 1.0)

        if risk_pct_custom <= 0:
            st.sidebar.warning("Risk % (CUSTOM) ต้องมากกว่า 0")
            # custom_entries_summary_sec3 remains []
        elif n_entry_custom <=0:
            st.sidebar.warning("จำนวนไม้ (CUSTOM) ต้องมากกว่า 0")
            # custom_entries_summary_sec3 remains []
        else:
            risk_per_trade_custom_total = active_balance_to_use * (risk_pct_custom / 100.0)
            risk_dollar_per_entry_custom = risk_per_trade_custom_total / n_entry_custom
            
            temp_custom_rr_list = []
            temp_custom_legs_for_saving = [] # Initialize here for this specific calculation path
            current_total_actual_risk_custom = 0.0 
            
            for i in range(int(n_entry_custom)):
                entry_str = st.session_state.get(f"custom_entry_{i}_v3", "0.00")
                sl_str = st.session_state.get(f"custom_sl_{i}_v3", "0.00")
                tp_str = st.session_state.get(f"custom_tp_{i}_v3", "0.00")

                try:
                    entry_val = float(entry_str)
                    sl_val = float(sl_str)
                    tp_val = float(tp_str)

                    stop_custom = abs(entry_val - sl_val)
                    target_custom = abs(tp_val - entry_val)
                    lot_custom, actual_risk_dollar_custom, rr_custom, profit_at_user_tp_custom = 0.0, 0.0, 0.0, 0.0

                    if stop_custom > 1e-9:
                        lot_custom = risk_dollar_per_entry_custom / stop_custom 
                        actual_risk_dollar_custom = lot_custom * stop_custom 
                        if target_custom > 1e-9 : 
                            rr_custom = target_custom / stop_custom
                            profit_at_user_tp_custom = lot_custom * target_custom
                        temp_custom_rr_list.append(rr_custom)
                        
                        if rr_custom < 3.0 and rr_custom >= 0: 
                            recommended_tp_target_distance = 3 * stop_custom
                            if sl_val < entry_val: 
                                recommended_tp_price = entry_val + recommended_tp_target_distance
                            elif sl_val > entry_val: 
                                recommended_tp_price = entry_val - recommended_tp_target_distance
                            else: 
                                recommended_tp_price = tp_val 
                            
                            if sl_val != entry_val : 
                                custom_tp_recommendation_messages.append(
                                    f"ไม้ {i+1}: หากต้องการ RR≈3, TP ควรเป็น ≈ {recommended_tp_price:.5f} (TP ปัจจุบัน RR={rr_custom:.2f})"
                                )
                    else: 
                         actual_risk_dollar_custom = risk_dollar_per_entry_custom 
                    
                    summary_total_lots += lot_custom
                    current_total_actual_risk_custom += actual_risk_dollar_custom
                    summary_total_profit_at_primary_tp += profit_at_user_tp_custom
                    
                    temp_custom_legs_for_saving.append({
                        "Entry": round(entry_val, 5), 
                        "SL": round(sl_val, 5), 
                        "TP": round(tp_val, 5),
                        "Lot": round(lot_custom, 2), 
                        "Risk $": round(actual_risk_dollar_custom, 2), 
                        "RR": round(rr_custom, 2)
                    })

                except ValueError: 
                    current_total_actual_risk_custom += risk_dollar_per_entry_custom 
                    temp_custom_legs_for_saving.append({
                        "Entry": entry_str, "SL": sl_str, "TP": tp_str,
                        "Lot": "0.00", "Risk $": f"{risk_dollar_per_entry_custom:.2f}", "RR": "Error"
                    })
            
            custom_entries_summary_sec3 = temp_custom_legs_for_saving # Assign populated list
            summary_total_risk_dollar = current_total_actual_risk_custom 

            if temp_custom_rr_list:
                valid_rrs = [r for r in temp_custom_rr_list if isinstance(r, (float, int)) and r > 0]
                summary_avg_rr = np.mean(valid_rrs) if valid_rrs else 0.0
            else:
                summary_avg_rr = 0.0
                
    except ValueError:
        st.sidebar.warning("กรอกข้อมูล CUSTOM ไม่ถูกต้อง (ตรวจสอบค่าตัวเลข)")
        # custom_entries_summary_sec3 remains []
    except Exception as e_custom_summary:
        st.sidebar.error(f"คำนวณ CUSTOM Summary ไม่สำเร็จ: {e_custom_summary}")
        st.exception(e_custom_summary)
        # custom_entries_summary_sec3 remains []

# --- Display Summaries in Sidebar ---
# (This part uses the summary_... variables populated by the calculations above in SEC 3)
display_summary_info = False
if mode == "FIBO" and (st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", "")):
    # For FIBO, display if there are entries calculated.
    # summary_avg_rr and summary_total_profit_at_primary_tp are now calculated per leg.
    if entry_data_summary_sec3: # Check if the list has been populated
        display_summary_info = True
elif mode == "CUSTOM" and st.session_state.get("n_entry_custom_val_v2", 0) > 0:
    # For CUSTOM, display if there are entries.
    if custom_entries_summary_sec3: # Check if the list has been populated
        display_summary_info = True
    elif custom_tp_recommendation_messages: # Also display if there are only recommendation messages
        display_summary_info = True


if display_summary_info:
    current_risk_display = 0.0
    # active_balance_to_use should be defined globally or earlier in the script
    # For example: active_balance_to_use = st.session_state.get('current_account_balance', 10000.0)
    # Ensure active_balance_to_use is available in this scope.
    # If not, you might need to retrieve it from session_state again or ensure it's passed correctly.
    active_balance_display = active_balance_to_use # Assuming active_balance_to_use is correctly defined and available

    if mode == "FIBO": current_risk_display = st.session_state.get('risk_pct_fibo_val_v2', 0.0)
    elif mode == "CUSTOM": current_risk_display = st.session_state.get('risk_pct_custom_val_v2', 0.0)

    st.sidebar.write(f"**Total Lots ({mode}):** {summary_total_lots:.2f}")
    st.sidebar.write(f"**Total Risk $ ({mode}):** {summary_total_risk_dollar:.2f} (Balance: {active_balance_display:,.2f}, Risk: {current_risk_display:.2f}%)")
    
    if summary_avg_rr > 0: 
        tp_ref_text = "(to Global TP1)" if mode == "FIBO" else "(to User TP)"
        st.sidebar.write(f"**Average RR ({mode}) {tp_ref_text}:** {summary_avg_rr:.2f}")
    
    profit_ref_text = "(at Global TP1)" if mode == "FIBO" else "(at User TP)"
    st.sidebar.write(f"**Total Expected Profit {profit_ref_text} ({mode}):** {summary_total_profit_at_primary_tp:,.2f} USD")
    
    if mode == "CUSTOM" and custom_tp_recommendation_messages:
        st.sidebar.markdown("**คำแนะนำ TP (เพื่อให้ RR ≈ 3):**")
        for msg in custom_tp_recommendation_messages:
            st.sidebar.caption(msg)
else:
    # Fallback message logic if no summary is displayed
    show_fallback_info = True
    if mode == "FIBO" and (not st.session_state.get("swing_high_fibo_val_v2", "") or not st.session_state.get("swing_low_fibo_val_v2", "")):
        # If essential inputs for FIBO summary are missing, the info message is already shown in the calculation block.
        show_fallback_info = False 
    elif mode == "CUSTOM" and not (st.session_state.get("n_entry_custom_val_v2", 0) > 0 and st.session_state.get("risk_pct_custom_val_v2", 0.0) > 0):
        # If essential inputs for CUSTOM summary are missing, warnings are shown in the calculation block.
        show_fallback_info = False
    
    if show_fallback_info:
        # This fallback is if no other specific info/warning was triggered by the calc blocks,
        # and display_summary_info is still False (e.g., no Fibo levels selected in FIBO mode).
        if not ( (mode == "FIBO" and not entry_data_summary_sec3 and (st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", ""))) or \
                 (mode == "CUSTOM" and not custom_entries_summary_sec3 and (st.session_state.get("n_entry_custom_val_v2", 0) > 0 and st.session_state.get("risk_pct_custom_val_v2", 0.0) > 0) ) ):
            # The conditions above are a bit complex, aiming to show the generic message only if specific input prompts weren't the cause.
            # A simpler approach might be needed if this doesn't cover all edge cases gracefully.
            st.sidebar.info("กรอกข้อมูลให้ครบถ้วนและถูกต้อง หรือเลือกเงื่อนไข (เช่น Fibo Levels) เพื่อคำนวณ Summary")


# --- End of modified SEC 3 ---

# ===================== SEC 3.1: SCALING MANAGER =======================
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    scaling_step = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=1.0, 
        value=st.session_state.get('scaling_step', 0.25), 
        step=0.01, format="%.2f", key='scaling_step'
    )
    min_risk_pct = st.number_input(
        "Minimum Risk %", min_value=0.01, max_value=100.0, 
        value=st.session_state.get('min_risk_pct', 0.5), 
        step=0.01, format="%.2f", key='min_risk_pct'
    )
    max_risk_pct = st.number_input(
        "Maximum Risk %", min_value=0.01, max_value=100.0, 
        value=st.session_state.get('max_risk_pct', 5.0), 
        step=0.01, format="%.2f", key='max_risk_pct'
    )
    scaling_mode = st.radio(
        "Scaling Mode", ["Manual", "Auto"], 
        index=0 if st.session_state.get('scaling_mode', 'Manual') == 'Manual' else 1,
        horizontal=True, key='scaling_mode'
    )

# ===================== SEC 3.1.1: SCALING SUGGESTION LOGIC =======================
df_planned_logs_for_scaling = pd.DataFrame()
gc_scaling = get_gspread_client()
if gc_scaling:
    try:
        sh_scaling = gc_scaling.open(GOOGLE_SHEET_NAME)
        ws_planned_logs = sh_scaling.worksheet(WORKSHEET_PLANNED_LOGS) # Make sure this worksheet name is correct
        records_scaling = ws_planned_logs.get_all_records()
        if records_scaling:
            df_planned_logs_for_scaling = pd.DataFrame(records_scaling)
            # Ensure necessary columns are correctly typed for get_performance
            if 'Risk $' in df_planned_logs_for_scaling.columns:
                df_planned_logs_for_scaling['Risk $'] = pd.to_numeric(df_planned_logs_for_scaling['Risk $'], errors='coerce').fillna(0)
            if 'Timestamp' in df_planned_logs_for_scaling.columns:
                df_planned_logs_for_scaling['Timestamp'] = pd.to_datetime(df_planned_logs_for_scaling['Timestamp'], errors='coerce')
            # Add other necessary type conversions if get_performance depends on them
    except gspread.exceptions.WorksheetNotFound:
        # st.info(f"Worksheet '{WORKSHEET_PLANNED_LOGS}' not found for scaling performance. Scaling suggestions may be limited.")
        pass # Continue without historical performance if sheet not found
    except Exception as e_scaling_load:
        # st.warning(f"Error loading data for scaling performance: {e_scaling_load}")
        pass # Continue, but scaling suggestions might be affected

# active_balance_to_use should be defined globally from active portfolio's initial balance
# initial_risk_pct_from_portfolio should also be defined globally based on active portfolio's CurrentRiskPercent

winrate_perf, gain_perf, total_trades_perf = get_performance(df_planned_logs_for_scaling.copy(), mode="week")

current_risk_for_scaling = initial_risk_pct_from_portfolio # Default to portfolio's risk
if mode == "FIBO":
    # Use the actual current risk % from the input field (via session state)
    current_risk_for_scaling = st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio)
elif mode == "CUSTOM":
    current_risk_for_scaling = st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio)

scaling_step_val = st.session_state.get('scaling_step', 0.25) # From SEC 3.1 inputs
max_risk_pct_val = st.session_state.get('max_risk_pct', 5.0)   # From SEC 3.1 inputs
min_risk_pct_val = st.session_state.get('min_risk_pct', 0.5)   # From SEC 3.1 inputs
current_scaling_mode = st.session_state.get('scaling_mode', 'Manual') # From SEC 3.1 inputs

suggest_risk = current_risk_for_scaling # Initialize with current risk
scaling_msg = f"Risk% ปัจจุบัน: {current_risk_for_scaling:.2f}%. "

if total_trades_perf > 0:
    # Use active_balance_to_use (from active portfolio) for gain threshold
    gain_threshold = 0.02 * active_balance_to_use
    if winrate_perf > 55 and gain_perf > gain_threshold:
        suggest_risk = min(current_risk_for_scaling + scaling_step_val, max_risk_pct_val)
        scaling_msg += f"🎉 ผลงานดี! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f} (เป้า {gain_threshold:,.2f}). แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}%"
    elif winrate_perf < 45 or gain_perf < 0: # Consider if gain_perf < 0 is too strict, maybe gain_perf < -loss_threshold
        suggest_risk = max(current_risk_for_scaling - scaling_step_val, min_risk_pct_val)
        scaling_msg += f"⚠️ ควรลด Risk! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f}. แนะนำลด Risk% เป็น {suggest_risk:.2f}%"
    else:
        scaling_msg += f"คง Risk% (Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f})"
else:
    scaling_msg += "ยังไม่มีข้อมูล Performance เพียงพอในสัปดาห์นี้ หรือ Performance อยู่ในเกณฑ์"

st.sidebar.info(scaling_msg)

# Apply suggested risk
if abs(suggest_risk - current_risk_for_scaling) > 0.001: # Only show button or auto-apply if there's a change
    if current_scaling_mode == "Manual":
        if st.sidebar.button(f"ปรับ Risk% ตามคำแนะนำเป็น {suggest_risk:.2f}%"):
            if mode == "FIBO":
                st.session_state.risk_pct_fibo_val_v2 = suggest_risk # Update new key
            elif mode == "CUSTOM":
                st.session_state.risk_pct_custom_val_v2 = suggest_risk # Update new key
            st.rerun()
    elif current_scaling_mode == "Auto":
        if mode == "FIBO":
            st.session_state.risk_pct_fibo_val_v2 = suggest_risk # Update new key
        elif mode == "CUSTOM":
            st.session_state.risk_pct_custom_val_v2 = suggest_risk # Update new key
        # Potentially st.rerun() here if auto-adjustment needs to immediately reflect in UI inputs
        # However, be cautious with auto-reruns to avoid infinite loops.
        # If input widgets are bound to these session state keys, they should update on next interaction.
        # For now, mirroring original behavior (no explicit rerun on auto-apply unless it was already there).
        # The user's original code did not have a rerun here. Let's add a note for them.
        if st.session_state.get(f"last_auto_suggested_risk_{mode}", 0) != suggest_risk : # Rerun only if risk actually changed by auto
            st.session_state[f"last_auto_suggested_risk_{mode}"] = suggest_risk
            st.toast(f"Auto Scaling: ปรับ Risk% ของโหมด {mode} เป็น {suggest_risk:.2f}%", icon="⚙️")
            st.rerun() # Rerun to update the input field display immediately

# ===================== SEC 3.2: SAVE PLAN ACTION & DRAWDOWN LOCK =======================
def save_plan_to_gsheets(plan_data_list, trade_mode_arg, asset_name, risk_percentage, trade_direction, portfolio_id, portfolio_name):
    gc = get_gspread_client()
    if not gc:
        st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกแผนได้")
        return False
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        timestamp_now = datetime.now()
        rows_to_append = []
        expected_headers = [
            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",
            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"
        ]
        current_headers = []
        if ws.row_count > 0:
            try:
                current_headers = ws.row_values(1)
            except Exception:
                current_headers = []
        
        if not current_headers or all(h == "" for h in current_headers) :
            ws.append_row(expected_headers, value_input_option='USER_ENTERED')
        elif set(current_headers) != set(expected_headers) and any(h!="" for h in current_headers):
            st.warning(f"Worksheet '{WORKSHEET_PLANNED_LOGS}' has incorrect headers. Please ensure headers match: {', '.join(expected_headers)}")

        for idx, plan_entry in enumerate(plan_data_list):
            log_id = f"{timestamp_now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}-{idx}"
            row_data = {
                "LogID": log_id,
                "PortfolioID": portfolio_id,
                "PortfolioName": portfolio_name,
                "Timestamp": timestamp_now.strftime("%Y-%m-%d %H:%M:%S"),
                "Asset": asset_name,
                "Mode": trade_mode_arg,
                "Direction": trade_direction,
                "Risk %": risk_percentage,
                "Fibo Level": plan_entry.get("Fibo Level", ""),
                "Entry": plan_entry.get("Entry", "0.00"),
                "SL": plan_entry.get("SL", "0.00"),
                "TP": plan_entry.get("TP", "0.00"),
                "Lot": plan_entry.get("Lot", "0.00"),
                "Risk $": plan_entry.get("Risk $", "0.00"),
                "RR": plan_entry.get("RR", "")
            }
            rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])

        if rows_to_append:
            ws.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            return True
        return False
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PLANNED_LOGS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกแผนไปยัง Google Sheets: {e}")
        return False

# ===================== SEC 3.2: SAVE PLAN ACTION & DRAWDOWN LOCK =======================
# (ฟังก์ชัน save_plan_to_gsheets อยู่ก่อนหน้านี้ ไม่ต้องแก้ไข)

df_drawdown_check = pd.DataFrame()
gc_drawdown = get_gspread_client()
if gc_drawdown:
    try:
        sh_drawdown = gc_drawdown.open(GOOGLE_SHEET_NAME)
        ws_planned_logs_drawdown = sh_drawdown.worksheet(WORKSHEET_PLANNED_LOGS)
        records_drawdown = ws_planned_logs_drawdown.get_all_records()
        if records_drawdown:
            df_drawdown_check = pd.DataFrame(records_drawdown)
            # Ensure 'Timestamp' and 'Risk $' columns are correctly typed for get_today_drawdown
            if 'Timestamp' in df_drawdown_check.columns:
                df_drawdown_check['Timestamp'] = pd.to_datetime(df_drawdown_check['Timestamp'], errors='coerce')
            if 'Risk $' in df_drawdown_check.columns:
                df_drawdown_check['Risk $'] = pd.to_numeric(df_drawdown_check['Risk $'], errors='coerce')

    except gspread.exceptions.WorksheetNotFound:
        # This case is handled by df_drawdown_check remaining empty if worksheet not found
        pass # Silently continue if PlannedTradeLogs doesn't exist for drawdown check
    except Exception as e_dd_load:
        # st.warning(f"ไม่สามารถโหลดข้อมูล PlannedTradeLogs สำหรับ Drawdown check: {e_dd_load}") # Optional warning
        pass


# Use active_balance_to_use for drawdown calculations if limit is portfolio-dependent
drawdown_today = get_today_drawdown(df_drawdown_check.copy(), active_balance_to_use) # Pass active_balance_to_use
drawdown_limit_pct_val = st.session_state.get('drawdown_limit_pct', 2.0)
drawdown_limit_abs = -abs(active_balance_to_use * (drawdown_limit_pct_val / 100.0)) # Use active_balance_to_use

if drawdown_today < 0: # Only show if there's actual drawdown from plans
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** <font color='red'>{drawdown_today:,.2f} USD</font>", unsafe_allow_html=True)
    st.sidebar.markdown(f"**ลิมิตขาดทุนที่ตั้งไว้:** {drawdown_limit_abs:,.2f} USD ({drawdown_limit_pct_val:.1f}% ของ {active_balance_to_use:,.2f} USD)")
else:
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** {drawdown_today:,.2f} USD")


active_portfolio_id = st.session_state.get('active_portfolio_id_gs', None)
active_portfolio_name = st.session_state.get('active_portfolio_name_gs', None)

asset_to_save = ""
risk_pct_to_save = 0.0
direction_to_save = "N/A"
current_data_to_save = [] # This will be populated by summary data from SEC 3

save_button_pressed_flag = False

# Determine which save button was pressed (save_fibo or save_custom are from SEC 2.2 and SEC 2.3)
if mode == "FIBO" and 'save_fibo' in locals() and save_fibo:
    save_button_pressed_flag = True
elif mode == "CUSTOM" and 'save_custom' in locals() and save_custom:
    save_button_pressed_flag = True

if mode == "FIBO":
    asset_to_save = st.session_state.get("asset_fibo_val_v2", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct_fibo_val_v2", 1.0)
    direction_to_save = st.session_state.get("direction_fibo_val_v2", "Long")
    current_data_to_save = entry_data_summary_sec3 # From new SEC 3 calculations
elif mode == "CUSTOM":
    asset_to_save = st.session_state.get("asset_custom_val_v2", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct_custom_val_v2", 1.0)
    
    # Infer direction for CUSTOM mode
    if custom_entries_summary_sec3: # Check if there are entries to infer from
        long_count = 0
        short_count = 0
        valid_trade_count = 0
        for item in custom_entries_summary_sec3:
            try:
                # Ensure 'Entry' and 'SL' keys exist and are valid numbers
                entry_price_str = item.get("Entry")
                sl_price_str = item.get("SL")
                if entry_price_str is None or sl_price_str is None: continue

                entry_price = float(entry_price_str)
                sl_price = float(sl_price_str)
                
                if pd.notna(entry_price) and pd.notna(sl_price) and entry_price != sl_price:
                    valid_trade_count += 1
                    if entry_price > sl_price: # Standard: SL is below entry for Long
                        long_count += 1
                    elif entry_price < sl_price: # Standard: SL is above entry for Short
                        short_count += 1
            except (ValueError, TypeError):
                # Silently skip if conversion to float fails or keys missing
                pass 

        if valid_trade_count > 0:
            if long_count == valid_trade_count and short_count == 0:
                direction_to_save = "Long"
            elif short_count == valid_trade_count and long_count == 0:
                direction_to_save = "Short"
            elif long_count > 0 and short_count > 0: # Mixed
                direction_to_save = "Mixed"
            elif long_count > 0: # Only longs, but maybe not all trades were valid for direction
                 direction_to_save = "Long"
            elif short_count > 0: # Only shorts
                 direction_to_save = "Short"
            else: # No clear direction from valid trades (e.g., all SL=Entry or invalid numbers)
                direction_to_save = "N/A"
        else:
            direction_to_save = "N/A" # No valid trades to infer direction from
    else:
        direction_to_save = "N/A" # No custom entries available

    current_data_to_save = custom_entries_summary_sec3 # From new SEC 3 calculations

if save_button_pressed_flag:
    if not current_data_to_save:
        st.sidebar.warning(f"ไม่พบข้อมูลแผน ({mode}) ที่จะบันทึก กรุณาคำนวณแผนใน Summary ให้ถูกต้องก่อน")
    elif drawdown_today <= drawdown_limit_abs : # drawdown_limit_abs is negative
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนจากแผนรวมวันนี้ {abs(drawdown_today):,.2f} ถึง/เกินลิมิต {abs(drawdown_limit_abs):,.2f} ({drawdown_limit_pct_val:.1f}%)"
        )
    elif not active_portfolio_id:
        st.sidebar.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ด้านบนก่อนบันทึกแผน")
    else:
        try:
            if save_plan_to_gsheets(current_data_to_save, mode, asset_to_save, risk_pct_to_save, direction_to_save, active_portfolio_id, active_portfolio_name):
                st.sidebar.success(f"บันทึกแผน ({mode}) สำหรับพอร์ต '{active_portfolio_name}' ลง Google Sheets สำเร็จ!")
                st.balloons()
                # Optional: Clear input fields after successful save
                # if mode == "FIBO":
                #     st.session_state.swing_high_fibo_val_v2 = ""
                #     st.session_state.swing_low_fibo_val_v2 = ""
                #     # Potentially reset fibo_flags_v2 as well
                # elif mode == "CUSTOM":
                #     for i in range(st.session_state.get("n_entry_custom_val_v2",1)):
                #         st.session_state[f"custom_entry_{i}_v3"] = "0.00"
                #         st.session_state[f"custom_sl_{i}_v3"] = "0.00"
                #         st.session_state[f"custom_tp_{i}_v3"] = "0.00"
                # st.rerun() # To reflect cleared inputs
            else:
                st.sidebar.error(f"Save ({mode}) ไปยัง Google Sheets ไม่สำเร็จ (อาจเกิดจาก Headers ไม่ตรง หรือการเชื่อมต่อมีปัญหา)")
        except Exception as e_save_plan:
            st.sidebar.error(f"เกิดข้อผิดพลาดรุนแรงระหว่างบันทึกแผน ({mode}): {e_save_plan}")
            # st.exception(e_save_plan) # Uncomment for full traceback during debugging

# --- End of new SEC 3.2 ---

# ===================== SEC 4: MAIN AREA - ENTRY PLAN DETAILS TABLE =======================
with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):
    if mode == "FIBO":
        col1_main, col2_main = st.columns(2)
        with col1_main:
            st.markdown("### 🎯 Entry Levels (FIBO)")
            # ใช้ตัวแปรใหม่จาก SEC 3 และตรวจสอบว่าถูก define และมีข้อมูลหรือไม่
            if 'entry_data_summary_sec3' in locals() and entry_data_summary_sec3:
                entry_df_main = pd.DataFrame(entry_data_summary_sec3)
                st.dataframe(entry_df_main, hide_index=True, use_container_width=True)
            else:
                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level ใน Sidebar เพื่อดู Entry Levels (หรือยังไม่มีข้อมูลสรุป).")
        with col2_main:
            st.markdown("### 🎯 Take Profit Zones (FIBO)")
            try:
                # ใช้ session state keys ที่อัปเดตแล้วจาก SEC 2.2 เพื่อความสอดคล้อง
                current_swing_high_tp_sec4 = st.session_state.get("swing_high_fibo_val_v2", "")
                current_swing_low_tp_sec4 = st.session_state.get("swing_low_fibo_val_v2", "")
                current_fibo_direction_tp_sec4 = st.session_state.get("direction_fibo_val_v2", "Long")

                if not current_swing_high_tp_sec4 or not current_swing_low_tp_sec4:
                    st.info("📌 กรอก High/Low ใน Sidebar (FIBO) ให้ครบถ้วนเพื่อคำนวณ TP.")
                else:
                    high_tp = float(current_swing_high_tp_sec4)
                    low_tp = float(current_swing_low_tp_sec4)

                    if high_tp > low_tp:
                        if current_fibo_direction_tp_sec4 == "Long":
                            tp1_main = low_tp + (high_tp - low_tp) * 1.618
                            tp2_main = low_tp + (high_tp - low_tp) * 2.618
                            tp3_main = low_tp + (high_tp - low_tp) * 4.236
                        else: # Short
                            tp1_main = high_tp - (high_tp - low_tp) * 1.618
                            tp2_main = high_tp - (high_tp - low_tp) * 2.618
                            tp3_main = high_tp - (high_tp - low_tp) * 4.236
                        tp_df_main = pd.DataFrame({
                            "TP Zone": ["TP1 (1.618)", "TP2 (2.618)", "TP3 (4.236)"],
                            # แสดงทศนิยม 5 ตำแหน่งสำหรับราคา TP เพื่อความแม่นยำ
                            "Price": [f"{tp1_main:.5f}", f"{tp2_main:.5f}", f"{tp3_main:.5f}"]
                        })
                        st.dataframe(tp_df_main, hide_index=True, use_container_width=True)
                    else:
                        st.warning("📌 High ต้องมากกว่า Low เพื่อคำนวณ TP.")
            except ValueError:
                st.warning("📌 กรอก High/Low (FIBO) เป็นตัวเลขที่ถูกต้องเพื่อคำนวณ TP.")
            except Exception as e_tp_fibo:
                st.info(f"📌 เกิดข้อผิดพลาดในการคำนวณ TP (FIBO): {e_tp_fibo}")

    elif mode == "CUSTOM":
        st.markdown("### 🎯 Entry & Take Profit Zones (CUSTOM)")
        # ใช้ตัวแปรใหม่จาก SEC 3 และตรวจสอบว่าถูก define และมีข้อมูลหรือไม่
        if 'custom_entries_summary_sec3' in locals() and custom_entries_summary_sec3:
            custom_df_main = pd.DataFrame(custom_entries_summary_sec3)
            
            # เลือกคอลัมน์ที่จะแสดงผล (ไม่รวม "ไม้ที่" ถ้าไม่ต้องการ หรือจัดลำดับใหม่)
            cols_to_display_custom = [col for col in ["Entry", "SL", "TP", "Lot", "Risk $", "RR"] if col in custom_df_main.columns]
            if cols_to_display_custom:
                 st.dataframe(custom_df_main[cols_to_display_custom], hide_index=True, use_container_width=True)
            else: # กรณีที่ custom_entries_summary_sec3 อาจมีโครงสร้างอื่น หรือ คอลัมน์ที่คาดหวังไม่มี
                 st.dataframe(custom_df_main, hide_index=True, use_container_width=True)


            for i, row_data_dict in enumerate(custom_entries_summary_sec3): # ใช้ตัวแปรใหม่
                try:
                    rr_val_str = row_data_dict.get("RR", "0")
                    # ตรวจสอบค่า RR ก่อนแปลง เพื่อหลีกเลี่ยง error ถ้าเป็น None, "", "NaN", หรือ "Error"
                    if rr_val_str is None or str(rr_val_str).strip() == "" or \
                       str(rr_val_str).lower() == "nan" or "error" in str(rr_val_str).lower():
                        continue 
                    
                    rr_val = float(rr_val_str)
                    if 0 < rr_val < 2: # ตรวจสอบว่า RR อยู่ระหว่าง 0 และ 2 (ไม่รวม 0)
                        # พยายามใช้ "ไม้ที่" จาก dict ถ้ามี, ถ้าไม่มีให้ใช้ i+1
                        entry_label = row_data_dict.get("ไม้ที่", i + 1)
                        st.warning(f"🎯 Entry {entry_label} มี RR ค่อนข้างต่ำ ({rr_val:.2f}) — ลองปรับ TP/SL เพื่อ Risk:Reward ที่ดีขึ้น")
                except ValueError: 
                    # กรณี RR ไม่สามารถแปลงเป็น float ได้ (เช่น ยังเป็น "Error" จากการคำนวณก่อนหน้า)
                    pass
                except Exception: # ดักจับ error อื่นๆ ที่อาจเกิดขึ้น
                    pass
        else:
            st.info("กรอกข้อมูล Custom ใน Sidebar เพื่อดู Entry & TP Zones (หรือยังไม่มีข้อมูลสรุป).")

# ===================== SEC 5: MAIN AREA - CHART VISUALIZER =======================
with st.expander("📈 Chart Visualizer", expanded=False):
    asset_to_display = "OANDA:XAUUSD" # Default asset for TradingView
    current_asset_input_from_form = "" # จะเก็บค่า asset จาก form input ปัจจุบัน

    if mode == "FIBO":
        current_asset_input_from_form = st.session_state.get("asset_fibo_val_v2", "XAUUSD") # ใช้ key ใหม่
    elif mode == "CUSTOM":
        current_asset_input_from_form = st.session_state.get("asset_custom_val_v2", "XAUUSD") # ใช้ key ใหม่
    
    # กำหนด asset_to_display โดยดูจาก plot_data ก่อน, ถ้าไม่มีให้ใช้จาก form input
    if 'plot_data' in st.session_state and st.session_state['plot_data'] and st.session_state['plot_data'].get('Asset'):
        asset_from_log = st.session_state['plot_data'].get('Asset')
        st.info(f"กำลังแสดงกราฟ TradingView สำหรับ: {asset_from_log.upper()} (จาก Log Viewer)")
        if asset_from_log.upper() == "XAUUSD":
            asset_to_display = "OANDA:XAUUSD"
        elif asset_from_log.upper() == "EURUSD":
            asset_to_display = "OANDA:EURUSD"
        # เพิ่มเงื่อนไขสำหรับสินทรัพย์อื่นๆ ที่ TradingView อาจจะต้องมี Prefix
        elif ":" not in asset_from_log: # ถ้าไม่มี Prefix, ลองเดาว่าเป็น OANDA หรือ FXCM หรืออื่นๆ
            asset_to_display = f"OANDA:{asset_from_log.upper()}" # หรือ FXCM:{asset_from_log.upper()}
        else:
            asset_to_display = asset_from_log.upper()
    elif current_asset_input_from_form:
        st.info(f"กำลังแสดงกราฟ TradingView สำหรับ: {current_asset_input_from_form.upper()} (จาก Input ปัจจุบัน)")
        if current_asset_input_from_form.upper() == "XAUUSD":
            asset_to_display = "OANDA:XAUUSD"
        elif current_asset_input_from_form.upper() == "EURUSD":
            asset_to_display = "OANDA:EURUSD"
        elif ":" not in current_asset_input_from_form:
            asset_to_display = f"OANDA:{current_asset_input_from_form.upper()}"
        else:
            asset_to_display = current_asset_input_from_form.upper()
    else: # Fallback ถ้าไม่มีข้อมูลใดๆ
        st.info(f"กำลังแสดงกราฟ TradingView สำหรับ: {asset_to_display} (ค่าเริ่มต้น)")

    tradingview_html = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_legendary"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%",
        "height": 600,
        "symbol": "{asset_to_display}",
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
        "container_id": "tradingview_legendary"
      }});
      </script>
    </div>
    """
    st.components.v1.html(tradingview_html, height=620)

# ===================== SEC 6: MAIN AREA - AI ASSISTANT =======================
with st.expander("🤖 AI Assistant", expanded=True):
    # Get active portfolio details
    active_portfolio_id_ai = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_ai = st.session_state.get('active_portfolio_name_gs', "ทั่วไป (ไม่ได้เลือกพอร์ต)")
    # active_balance_to_use is defined globally and should reflect the active portfolio's initial balance
    # If no portfolio is selected, active_balance_to_use defaults to 10000.0 (as per its definition)
    # We will use this for simulation if a portfolio is active, otherwise, the old acc_balance (10000) for global.
    
    balance_for_ai_sim = acc_balance # Default to global acc_balance (10000)
    report_title_suffix = "(จากข้อมูลแผนเทรดทั้งหมด)"

    if active_portfolio_id_ai:
        balance_for_ai_sim = active_balance_to_use # Use active portfolio's balance for simulation
        report_title_suffix = f"(สำหรับพอร์ต: '{active_portfolio_name_ai}')"
        st.info(f"AI Assistant กำลังวิเคราะห์ข้อมูลสำหรับพอร์ต: '{active_portfolio_name_ai}' (Balance เริ่มต้น: {balance_for_ai_sim:,.2f} USD)")
    else:
        st.info("AI Assistant กำลังวิเคราะห์ข้อมูลจากแผนเทรดทั้งหมด (ยังไม่ได้เลือก Active Portfolio)")

    df_ai_logs_all = pd.DataFrame() # To store all logs first
    gc_ai = get_gspread_client()
    if gc_ai:
        try:
            sh_ai = gc_ai.open(GOOGLE_SHEET_NAME)
            ws_ai_logs = sh_ai.worksheet(WORKSHEET_PLANNED_LOGS)
            records_ai = ws_ai_logs.get_all_records()
            if records_ai:
                df_ai_logs_all = pd.DataFrame(records_ai)
                if 'Risk $' in df_ai_logs_all.columns:
                    df_ai_logs_all['Risk $'] = pd.to_numeric(df_ai_logs_all['Risk $'], errors='coerce').fillna(0)
                if 'RR' in df_ai_logs_all.columns:
                    df_ai_logs_all['RR'] = pd.to_numeric(df_ai_logs_all['RR'], errors='coerce')
                if 'Timestamp' in df_ai_logs_all.columns:
                    df_ai_logs_all['Timestamp'] = pd.to_datetime(df_ai_logs_all['Timestamp'], errors='coerce')
                if 'PortfolioID' in df_ai_logs_all.columns: # Ensure PortfolioID is string for consistent comparison
                    df_ai_logs_all['PortfolioID'] = df_ai_logs_all['PortfolioID'].astype(str)

        except gspread.exceptions.WorksheetNotFound:
            st.warning(f"ไม่พบ Worksheet '{WORKSHEET_PLANNED_LOGS}' สำหรับ AI Assistant.")
            df_ai_logs_all = pd.DataFrame() # Ensure it's an empty DF
        except Exception as e_ai_load:
            st.error(f"เกิดข้อผิดพลาดในการโหลดข้อมูลสำหรับ AI Assistant: {e_ai_load}")
            df_ai_logs_all = pd.DataFrame() # Ensure it's an empty DF
            
    # Filter logs if an active portfolio is selected
    df_ai_logs_to_analyze = pd.DataFrame()
    if active_portfolio_id_ai and not df_ai_logs_all.empty:
        if 'PortfolioID' in df_ai_logs_all.columns:
            # Ensure active_portfolio_id_ai is string for comparison, as PortfolioID in df is now string
            df_ai_logs_to_analyze = df_ai_logs_all[df_ai_logs_all['PortfolioID'] == str(active_portfolio_id_ai)].copy()
            if df_ai_logs_to_analyze.empty:
                st.info(f"ไม่พบข้อมูลแผนเทรดใน Log สำหรับพอร์ต '{active_portfolio_name_ai}'.")
        else:
            st.warning("คอลัมน์ 'PortfolioID' ไม่พบใน PlannedTradeLogs, ไม่สามารถกรองข้อมูลสำหรับ AI Assistant ได้")
            df_ai_logs_to_analyze = df_ai_logs_all.copy() # Analyze all if PortfolioID column is missing
    elif not df_ai_logs_all.empty: # No active portfolio, analyze all logs
        df_ai_logs_to_analyze = df_ai_logs_all.copy()
    else: # df_ai_logs_all is empty
        df_ai_logs_to_analyze = pd.DataFrame()


    if df_ai_logs_to_analyze.empty and df_ai_logs_all.empty: # No logs at all
        st.info("ยังไม่มีข้อมูลแผนเทรดใน Log (Google Sheets) สำหรับ AI Assistant")
    elif df_ai_logs_to_analyze.empty and not df_ai_logs_all.empty and active_portfolio_id_ai: # Active portfolio selected, but no logs for it
        # Message already shown above
        pass
    else: # Logs exist for analysis (either global or for active portfolio)
        total_trades_ai = df_ai_logs_to_analyze.shape[0]
        win_trades_ai = df_ai_logs_to_analyze[df_ai_logs_to_analyze["Risk $"] > 0].shape[0] if "Risk $" in df_ai_logs_to_analyze.columns else 0
        winrate_ai = (100 * win_trades_ai / total_trades_ai) if total_trades_ai > 0 else 0
        gross_profit_ai = df_ai_logs_to_analyze["Risk $"].sum() if "Risk $" in df_ai_logs_to_analyze.columns else 0
        
        avg_rr_ai_series = df_ai_logs_to_analyze["RR"].dropna() if "RR" in df_ai_logs_to_analyze.columns else pd.Series(dtype='float64')
        avg_rr_ai = avg_rr_ai_series.mean() if not avg_rr_ai_series.empty else None

        max_drawdown_ai = 0.0
        if "Risk $" in df_ai_logs_to_analyze.columns and not df_ai_logs_to_analyze.empty:
            df_ai_logs_sorted = df_ai_logs_to_analyze.sort_values(by="Timestamp") if "Timestamp" in df_ai_logs_to_analyze.columns and not df_ai_logs_to_analyze["Timestamp"].isnull().all() else df_ai_logs_to_analyze
            
            current_balance_sim = balance_for_ai_sim # Use the determined balance for simulation
            peak_balance_sim = balance_for_ai_sim
            
            for pnl_val in df_ai_logs_sorted["Risk $"]:
                current_balance_sim += pnl_val
                if current_balance_sim > peak_balance_sim:
                    peak_balance_sim = current_balance_sim
                drawdown_val = peak_balance_sim - current_balance_sim
                if drawdown_val > max_drawdown_ai:
                    max_drawdown_ai = drawdown_val
        
        win_day_ai = "-"
        loss_day_ai = "-"
        if "Timestamp" in df_ai_logs_to_analyze.columns and "Risk $" in df_ai_logs_to_analyze.columns and not df_ai_logs_to_analyze["Timestamp"].isnull().all() and not df_ai_logs_to_analyze.empty:
            # Ensure 'Weekday' is available or create it safely
            if not df_ai_logs_to_analyze["Timestamp"].isnull().all():
                df_ai_logs_to_analyze.loc[:, "Weekday"] = df_ai_logs_to_analyze["Timestamp"].dt.day_name()
                daily_pnl = df_ai_logs_to_analyze.groupby("Weekday")["Risk $"].sum()
                if not daily_pnl.empty:
                    win_day_ai = daily_pnl.idxmax() if daily_pnl.max() > 0 else "-"
                    loss_day_ai = daily_pnl.idxmin() if daily_pnl.min() < 0 else "-"
            else: # All timestamps are NaT
                 win_day_ai = loss_day_ai = "N/A (Invalid Dates)"


        st.markdown(f"### 🧠 AI Intelligence Report {report_title_suffix}")
        st.write(f"- **จำนวนแผนเทรดที่วิเคราะห์:** {total_trades_ai:,}")
        st.write(f"- **Winrate (ตามแผน):** {winrate_ai:.2f}% (คำนวณจาก Risk $ > 0)")
        st.write(f"- **กำไร/ขาดทุนสุทธิ (ตามแผน):** {gross_profit_ai:,.2f} USD")
        if avg_rr_ai is not None:
            st.write(f"- **RR เฉลี่ย (ตามแผน):** {avg_rr_ai:.2f}")
        else:
            st.write(f"- **RR เฉลี่ย (ตามแผน):** N/A")
        st.write(f"- **Max Drawdown (จำลองจากแผน):** {max_drawdown_ai:,.2f} USD (เริ่มจำลองจาก Balance: {balance_for_ai_sim:,.2f} USD)")
        st.write(f"- **วันที่ทำกำไรดีที่สุด (ตามแผน):** {win_day_ai}")
        st.write(f"- **วันที่ขาดทุนมากที่สุด (ตามแผน):** {loss_day_ai}")

        st.markdown("### 🤖 AI Insight (จากกฎที่คุณกำหนดเอง)")
        insight_messages = []
        if total_trades_ai > 0 : # Only provide insights if there are trades
            if winrate_ai >= 60:
                insight_messages.append("✅ Winrate (ตามแผน) สูง: ระบบการวางแผนมีแนวโน้มที่ดี")
            elif winrate_ai < 40 and total_trades_ai >= 10 : # Ensure enough trades for low winrate warning
                insight_messages.append("⚠️ Winrate (ตามแผน) ต่ำ: ควรทบทวนกลยุทธ์การวางแผน")
            
            if avg_rr_ai is not None and avg_rr_ai < 1.5 and total_trades_ai >= 5: # Ensure enough trades for RR warning
                insight_messages.append("📉 RR เฉลี่ย (ตามแผน) ต่ำกว่า 1.5: อาจต้องพิจารณาการตั้ง TP/SL เพื่อ Risk:Reward ที่เหมาะสมขึ้น")
            
            # Use balance_for_ai_sim for drawdown threshold comparison
            if max_drawdown_ai > (balance_for_ai_sim * 0.10) and balance_for_ai_sim > 0:
                insight_messages.append(f"🚨 Max Drawdown (จำลองจากแผน) {max_drawdown_ai:,.2f} USD ค่อนข้างสูงเมื่อเทียบกับ Balance เริ่มต้น ({balance_for_ai_sim * 0.10:,.2f} USD): ควรระมัดระวังการบริหารความเสี่ยง")
            elif max_drawdown_ai > 0 and balance_for_ai_sim == 0: # Edge case if balance_for_ai_sim ended up as 0
                 insight_messages.append(f"ℹ️ Max Drawdown (จำลองจากแผน) คือ {max_drawdown_ai:,.2f} USD แต่ไม่สามารถเทียบเป็น % กับ Balance เริ่มต้นได้ (Balance เริ่มต้น = 0)")


        if not insight_messages and total_trades_ai > 0:
            insight_messages = ["ดูเหมือนว่าข้อมูลแผนเทรดที่วิเคราะห์ยังไม่มีจุดที่น่ากังวลเป็นพิเศษตามเกณฑ์ที่ตั้งไว้"]
        elif not insight_messages and total_trades_ai == 0:
             insight_messages = ["ยังไม่มีข้อมูลแผนเทรดให้ AI วิเคราะห์สำหรับส่วนนี้"]

        for msg in insight_messages:
            if "✅" in msg: st.success(msg)
            elif "⚠️" in msg or "📉" in msg: st.warning(msg)
            elif "🚨" in msg: st.error(msg)
            else: st.info(msg)

# ===================== SEC 7: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
with st.expander("📂  Ultimate Chart Dashboard Import & Processing", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # --- ฟังก์ชันสำหรับแยกข้อมูลจากเนื้อหาไฟล์ Statement (CSV) ---
    # [!!! ใช้ฟังก์ชัน extract_data_from_report_content เดิมจากไฟล์ mainโหลดได้หมด.py ของคุณตรงนี้นะครับ !!!]
    # ผมจะย่อโค้ดส่วนนี้ไว้นะครับ แต่ให้คุณใช้โค้ดเดิมของคุณได้เลย
    def extract_data_from_report_content(file_content_str_input):
        extracted_data = {}
        # ... (โค้ดทั้งหมดของฟังก์ชัน extract_data_from_report_content จากไฟล์ #35 ของคุณ) ...
        # ตรวจสอบให้แน่ใจว่าฟังก์ชันนี้ return extracted_data ที่มี keys:
        # 'deals', 'orders', 'positions', 'balance_summary', 'results_summary'
        # และ DataFrame ที่ return มามีคอลัมน์ตรงกับ expected_cleaned_columns ที่ใช้ในฟังก์ชันนี้
        
        # --- START: ส่วนที่คัดลอกมาจากโค้ดของคุณใน #35 ---
        def safe_float_convert(value_str):
            if isinstance(value_str, (int, float)):
                return value_str
            try:
                clean_value = str(value_str).replace(" ", "").replace(",", "").replace("%", "")
                if clean_value.count('.') > 1:
                    parts = clean_value.split('.')
                    integer_part = "".join(parts[:-1])
                    decimal_part = parts[-1]
                    clean_value = integer_part + "." + decimal_part
                return float(clean_value)
            except ValueError:
                return None
            except Exception:
                return None

        lines = []
        if isinstance(file_content_str_input, str):
            lines = file_content_str_input.strip().split('\n')
        elif isinstance(file_content_str_input, bytes):
            lines = file_content_str_input.decode('utf-8', errors='replace').strip().split('\n')
        else:
            st.error("Error: Invalid file_content type for processing in extract_data_from_report_content.")
            return extracted_data # Return empty dict on error

        if not lines: # Added check for empty lines after splitting
            st.warning("Warning: File content is empty after splitting lines in extract_data_from_report_content.")
            return extracted_data


        section_raw_headers = {
            "Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit",
            "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment",
            "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment",
        }
        
        expected_cleaned_columns = {
            "Positions": ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos"],
            "Orders": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Comment_Ord"],
            "Deals": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal"],
        }
        
        section_order_for_tables = ["Positions", "Orders", "Deals"]
        section_header_indices = {} 
        
        for line_idx, current_line_str in enumerate(lines):
            stripped_line = current_line_str.strip()
            for section_name, raw_header_template in section_raw_headers.items():
                if section_name not in section_header_indices: 
                    first_col_of_template = raw_header_template.split(',')[0].strip()
                    if stripped_line.startswith(first_col_of_template) and raw_header_template in stripped_line:
                        section_header_indices[section_name] = line_idx
                        break 

        for table_idx, section_name in enumerate(section_order_for_tables):
            section_key_lower = section_name.lower()
            extracted_data[section_key_lower] = pd.DataFrame() 

            if section_name in section_header_indices:
                header_line_num = section_header_indices[section_name]
                data_start_line_num = header_line_num + 1
                
                data_end_line_num = len(lines)
                for next_table_name_idx in range(table_idx + 1, len(section_order_for_tables)):
                    next_table_section_name = section_order_for_tables[next_table_name_idx]
                    if next_table_section_name in section_header_indices:
                        data_end_line_num = section_header_indices[next_table_section_name]
                        break 
                
                current_table_data_lines = []
                for line_num_for_data in range(data_start_line_num, data_end_line_num):
                    line_content_for_data = lines[line_num_for_data].strip()
                    if not line_content_for_data: 
                        if any(current_table_data_lines): 
                            break
                        else:
                            continue 

                    if line_content_for_data.startswith(("Balance:", "Credit Facility:", "Floating P/L:", "Equity:", "Results", "Total Net Profit:")):
                        break
                    is_another_header = False
                    for other_sec_name, other_raw_hdr in section_raw_headers.items():
                        if other_sec_name != section_name and line_content_for_data.startswith(other_raw_hdr.split(',')[0]) and other_raw_hdr in line_content_for_data:
                            is_another_header = True
                            break
                    if is_another_header:
                        break
                        
                    current_table_data_lines.append(line_content_for_data)

                if current_table_data_lines:
                    csv_data_str = "\n".join(current_table_data_lines)
                    try:
                        df_section = pd.read_csv(io.StringIO(csv_data_str),
                                                 header=None, 
                                                 names=expected_cleaned_columns[section_name],
                                                 skipinitialspace=True,
                                                 on_bad_lines='warn', 
                                                 engine='python',
                                                 dtype=str) 
                        
                        df_section.dropna(how='all', inplace=True) 
                        final_cols = expected_cleaned_columns[section_name]
                        for col in final_cols:
                            if col not in df_section.columns:
                                df_section[col] = np.nan 
                        df_section = df_section[final_cols] 

                        if not df_section.empty:
                            extracted_data[section_key_lower] = df_section
                    except Exception as e_parse_df:
                        if st.session_state.get("debug_statement_processing_v2", False):
                            st.error(f"Error parsing table data for {section_name}: {e_parse_df}")
                            st.text(f"Problematic CSV data for {section_name}:\n{csv_data_str[:500]}")

        balance_summary_dict = {}
        balance_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Balance:"):
                balance_start_line_idx = i
                break

        if balance_start_line_idx != -1:
            for i in range(balance_start_line_idx, min(balance_start_line_idx + 8, len(lines))): 
                line_stripped = lines[i].strip()
                if not line_stripped : continue 
                if line_stripped.startswith(("Results", "Total Net Profit:")) and i > balance_start_line_idx:
                    break
                
                parts = [p.strip() for p in line_stripped.split(',') if p.strip()]
                temp_key = ""
                val_expected_next = False
                for part_idx, part_val in enumerate(parts):
                    if not part_val: continue

                    if ':' in part_val:
                        key_str, val_str = part_val.split(':', 1)
                        key_clean = key_str.strip().replace(" ", "_").replace(".", "").replace("/","_").lower()
                        val_strip = val_str.strip()
                        if val_strip:
                            balance_summary_dict[key_clean] = safe_float_convert(val_strip.split(' ')[0])
                            val_expected_next = False
                            temp_key = ""
                        else:
                            temp_key = key_clean
                            val_expected_next = True
                    elif val_expected_next:
                        balance_summary_dict[temp_key] = safe_float_convert(part_val.split(' ')[0])
                        temp_key = ""
                        val_expected_next = False
        
        essential_balance_keys = ["balance", "credit_facility", "floating_p_l", "equity", "free_margin", "margin", "margin_level"]
        for k_b in essential_balance_keys:
            if k_b not in balance_summary_dict:
                balance_summary_dict[k_b] = 0.0

        results_summary_dict = {}
        stat_definitions_map = { 
            "Total Net Profit": "Total_Net_Profit", "Gross Profit": "Gross_Profit", "Gross Loss": "Gross_Loss",
            "Profit Factor": "Profit_Factor", "Expected Payoff": "Expected_Payoff",
            "Recovery Factor": "Recovery_Factor", "Sharpe Ratio": "Sharpe_Ratio",
            "Balance Drawdown Absolute": "Balance_Drawdown_Absolute",
            "Balance Drawdown Maximal": "Balance_Drawdown_Maximal",
            "Balance Drawdown Relative": "Balance_Drawdown_Relative_Percent", 
            "Total Trades": "Total_Trades",
            "Short Trades (won %)": "Short_Trades", 
            "Long Trades (won %)": "Long_Trades",
            "Profit Trades (% of total)": "Profit_Trades",
            "Loss Trades (% of total)": "Loss_Trades",
            "Largest profit trade": "Largest_profit_trade", "Largest loss trade": "Largest_loss_trade",
            "Average profit trade": "Average_profit_trade", "Average loss trade": "Average_loss_trade",
            "Maximum consecutive wins ($)": "Maximum_consecutive_wins_Count",
            "Maximal consecutive profit (count)": "Maximal_consecutive_profit_Amount",
            "Average consecutive wins": "Average_consecutive_wins",
            "Maximum consecutive losses ($)": "Maximum_consecutive_losses_Count",
            "Maximal consecutive loss (count)": "Maximal_consecutive_loss_Amount",
            "Average consecutive losses": "Average_consecutive_losses"
        }

        results_start_line_idx = -1
        results_section_processed_lines = 0
        max_lines_for_results = 30 

        for i_res, line_res in enumerate(lines):
            if results_start_line_idx == -1 and (line_res.strip().startswith("Results") or line_res.strip().startswith("Total Net Profit:")):
                results_start_line_idx = i_res
                continue 

            if results_start_line_idx != -1 and results_section_processed_lines < max_lines_for_results:
                line_stripped_res = line_res.strip()
                if not line_stripped_res: 
                    if results_section_processed_lines > 2: 
                        break
                    else:
                        continue
                
                results_section_processed_lines += 1
                row_cells = [cell.strip() for cell in line_stripped_res.split(',')]

                for c_idx, cell_content in enumerate(row_cells):
                    if not cell_content: continue
                    
                    current_label = cell_content.replace(':', '').strip()

                    if current_label in stat_definitions_map:
                        gsheet_key = stat_definitions_map[current_label]
                        
                        for k_val_search in range(1, 5): 
                            if (c_idx + k_val_search) < len(row_cells):
                                raw_value_from_cell = row_cells[c_idx + k_val_search]
                                if raw_value_from_cell: 
                                    value_part_before_paren = raw_value_from_cell.split('(')[0].strip()
                                    numeric_value = safe_float_convert(value_part_before_paren)

                                    if numeric_value is not None:
                                        results_summary_dict[gsheet_key] = numeric_value
                                        
                                    if '(' in raw_value_from_cell and ')' in raw_value_from_cell:
                                        try:
                                            paren_content_str = raw_value_from_cell[raw_value_from_cell.find('(')+1:raw_value_from_cell.find(')')].strip().replace('%','')
                                            paren_numeric_value = safe_float_convert(paren_content_str)
                                            if paren_numeric_value is not None:
                                                if current_label == "Balance Drawdown Maximal": results_summary_dict["Balance_Drawdown_Maximal_Percent"] = paren_numeric_value
                                                elif current_label == "Balance Drawdown Relative": results_summary_dict["Balance_Drawdown_Relative_Amount"] = paren_numeric_value 
                                                elif current_label == "Short Trades (won %)": results_summary_dict["Short_Trades_won_Percent"] = paren_numeric_value
                                                elif current_label == "Long Trades (won %)": results_summary_dict["Long_Trades_won_Percent"] = paren_numeric_value
                                                elif current_label == "Profit Trades (% of total)": results_summary_dict["Profit_Trades_Percent_of_total"] = paren_numeric_value
                                                elif current_label == "Loss Trades (% of total)": results_summary_dict["Loss_Trades_Percent_of_total"] = paren_numeric_value
                                                elif current_label == "Maximum consecutive wins ($)": results_summary_dict["Maximum_consecutive_wins_Profit"] = paren_numeric_value 
                                                elif current_label == "Maximal consecutive profit (count)": results_summary_dict["Maximal_consecutive_profit_Count"] = paren_numeric_value 
                                                elif current_label == "Maximum consecutive losses ($)": results_summary_dict["Maximum_consecutive_losses_Profit"] = paren_numeric_value
                                                elif current_label == "Maximal consecutive loss (count)": results_summary_dict["Maximal_consecutive_loss_Count"] = paren_numeric_value
                                        except Exception: pass 
                                    break 
                
                if line_stripped_res.startswith("Average consecutive losses"): 
                    break
            elif results_start_line_idx != -1 and results_section_processed_lines >= max_lines_for_results:
                break 

        extracted_data['balance_summary'] = balance_summary_dict
        extracted_data['results_summary'] = results_summary_dict
        
        return extracted_data
        # --- END: ส่วนที่คัดลอกมาจากโค้ดของคุณใน #35 ---

    # --- START: ฟังก์ชันใหม่/แก้ไข สำหรับบันทึกข้อมูลพร้อม Deduplication และ Header Handling ---
    # [ภายใน SEC 7 ของไฟล์ mainโหลดได้หมด.py ของคุณ]
# [ฟังก์ชัน extract_data_from_report_content และฟังก์ชัน save_... อื่นๆ ให้คงเดิมจากไฟล์ #35 ของคุณก่อน]

    def save_transactional_data_to_gsheets(ws, df_input, unique_id_col, expected_headers, data_type_name, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        if df_input is None or df_input.empty:
            return True, 0, 0 
        try:
            if ws is None: 
                st.error(f"({data_type_name}) Worksheet object is None. Cannot proceed.")
                return False, 0, 0

            current_headers = []
            if ws.row_count > 0:
                try: current_headers = ws.row_values(1)
                except Exception as e_get_header:
                    st.warning(f"Could not get header for '{ws.title}': {e_get_header}. Will attempt to write headers.")
                    current_headers = []

            if not current_headers or all(h == "" for h in current_headers) or set(current_headers) != set(expected_headers):
                try:
                    ws.update([expected_headers], value_input_option='USER_ENTERED')
                    st.info(f"Headers written/updated for '{ws.title}'.")
                except Exception as e_update_header:
                    st.error(f"Failed to write/update headers for '{ws.title}': {e_update_header}")
                    return False, 0, 0

            existing_ids = set()
            if ws.row_count > 1: 
                try:
                    all_sheet_records = ws.get_all_records(
                        expected_headers=expected_headers, 
                        numericise_ignore=['all'] 
                    )
                    if all_sheet_records:
                        df_existing_sheet_data = pd.DataFrame(all_sheet_records)
                        if unique_id_col in df_existing_sheet_data.columns and 'PortfolioID' in df_existing_sheet_data.columns:
                            df_existing_sheet_data['PortfolioID'] = df_existing_sheet_data['PortfolioID'].astype(str)
                            df_portfolio_data = df_existing_sheet_data[df_existing_sheet_data['PortfolioID'] == str(portfolio_id)]
                            if not df_portfolio_data.empty and unique_id_col in df_portfolio_data.columns:
                                existing_ids = set(df_portfolio_data[unique_id_col].astype(str).tolist())
                except Exception as e_get_records:
                    st.warning(f"Could not reliably get existing records from '{ws.title}' for {data_type_name} ({e_get_records}). Proceeding assuming no initial duplicates for this run.")
                    existing_ids = set()

            df_to_check = df_input.copy()
            if unique_id_col not in df_to_check.columns:
                # ***** START MODIFICATION: Provide more context on missing unique_id_col *****
                st.error(f"Unique ID column '{unique_id_col}' is MISSING from the data extracted for '{data_type_name}'. Cannot perform deduplication.")
                st.write(f"Available columns in df_input for {data_type_name}: {df_input.columns.tolist()}")
                # ***** END MODIFICATION *****
                return False, 0, 0

            df_to_check[unique_id_col] = df_to_check[unique_id_col].astype(str)
            
            # ***** START DEBUGGING: Show unique IDs and existing IDs *****
            if data_type_name == "Deals" and st.session_state.get("debug_statement_processing_v2", False) :
                st.write(f"DEBUG ({ws.title}): Unique IDs from new Deals data to check (df_to_check['{unique_id_col}']):")
                st.dataframe(df_to_check[[unique_id_col]].head(10)) 
                st.write(f"DEBUG ({ws.title}): Existing IDs in GSheet for this Portfolio to compare against ({len(existing_ids)} items):")
                st.json(list(existing_ids)[:10] if existing_ids else "No existing IDs found in GSheet") 
            # ***** END DEBUGGING *****

            new_df = df_to_check[~df_to_check[unique_id_col].isin(existing_ids)]
            num_new = len(new_df)
            num_duplicates_skipped = len(df_to_check) - num_new

            # ***** START DEBUGGING: Show the 'new' deal(s) if any are found *****
            if data_type_name == "Deals" and num_new > 0 and st.session_state.get("debug_statement_processing_v2", False): 
                st.write(f"DEBUG ({ws.title}): Found {num_new} 'new' deal(s) to be added (content shown below):")
                st.dataframe(new_df) 
            # ***** END DEBUGGING *****

            if new_df.empty:
                return True, num_new, num_duplicates_skipped
            
            df_to_save = pd.DataFrame(columns=expected_headers)
            for col in expected_headers:
                if col in new_df.columns:
                    df_to_save[col] = new_df[col]
            
            df_to_save["PortfolioID"] = str(portfolio_id)
            df_to_save["PortfolioName"] = str(portfolio_name)
            df_to_save["SourceFile"] = str(source_file_name)
            df_to_save["ImportBatchID"] = str(import_batch_id)
            
            for col in expected_headers:
                if col not in df_to_save.columns:
                    df_to_save[col] = ""
            df_to_save = df_to_save[expected_headers]

            list_of_lists = df_to_save.astype(str).replace('nan', '').replace('None','').fillna("").values.tolist()

            if list_of_lists:
                if data_type_name == "Deals" and st.session_state.get("debug_statement_processing_v2", False) :
                    st.write(f"DEBUG ({ws.title}): Preparing to append {len(list_of_lists)} rows for Deals. First row sample:")
                    st.json(list_of_lists[0] if list_of_lists else "Empty list_of_lists")
                
                ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
                
            return True, num_new, num_duplicates_skipped

        except gspread.exceptions.APIError as e_api:
            st.error(f"❌ ({ws.title}) Google Sheets API Error ({data_type_name}): {e_api}")
            return False, 0, 0
        except Exception as e:
            st.error(f"❌ ({ws.title}) เกิดข้อผิดพลาดในการบันทึก {data_type_name}: {e}")
            st.exception(e) # Show full traceback for other exceptions
            return False, 0, 0

    # แก้ไขฟังก์ชัน save_... ให้รับ ws และ import_batch_id
    def save_deals_to_actual_trades(ws, df_deals_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_deals = ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_deals_input, "Deal_ID", expected_headers_deals, "Deals", portfolio_id, portfolio_name, source_file_name, import_batch_id)

    def save_orders_to_gsheets(ws, df_orders_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_orders = ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_orders_input, "Order_ID_Ord", expected_headers_orders, "Orders", portfolio_id, portfolio_name, source_file_name, import_batch_id)

    def save_positions_to_gsheets(ws, df_positions_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_positions = ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_positions_input, "Position", expected_headers_positions, "Positions", portfolio_id, portfolio_name, source_file_name, import_batch_id)
    
    def save_results_summary_to_gsheets(ws, balance_summary_data, results_summary_data, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        try:
            if ws is None:
                st.error(f"({WORKSHEET_STATEMENT_SUMMARIES}) Worksheet object is None. Cannot save summary.")
                return False
                
            expected_headers = ["Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", "Total_Trades", "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count", "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count", "Average_consecutive_wins", "Average_consecutive_losses"]
            
            current_headers_ws = []
            if ws.row_count > 0:
                try: current_headers_ws = ws.row_values(1)
                except Exception: pass
            if not current_headers_ws or all(h == "" for h in current_headers_ws) or set(current_headers_ws) != set(expected_headers):
                ws.update([expected_headers], value_input_option='USER_ENTERED')
            
            row_data_to_save = {"Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "PortfolioID": str(portfolio_id), "PortfolioName": str(portfolio_name), "SourceFile": str(source_file_name), "ImportBatchID": str(import_batch_id)}
            
            balance_key_map = {"balance":"Balance", "equity":"Equity", "free_margin":"Free_Margin", "margin":"Margin", "floating_p_l":"Floating_P_L", "margin_level":"Margin_Level"}
            if isinstance(balance_summary_data, dict): 
                for k, v in balance_summary_data.items():
                    if k in balance_key_map: row_data_to_save[balance_key_map[k]] = v
            
            if isinstance(results_summary_data, dict): 
                for k,v in results_summary_data.items():
                    if k in expected_headers: row_data_to_save[k] = v
            
            final_row_values = [str(row_data_to_save.get(h, "")).strip() for h in expected_headers]
            ws.append_rows([final_row_values], value_input_option='USER_ENTERED')
            return True 
        except gspread.exceptions.APIError as e_api: 
            st.error(f"❌ ({ws.title}) Google Sheets API Error (Summary): {e_api}")
            return False
        except Exception as e: 
            st.error(f"❌ ({ws.title}) เกิดข้อผิดพลาดในการบันทึก Statement Summaries: {e}")
            st.exception(e)
            return False
    # --- END: ฟังก์ชัน save_... ---

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement Report (CSV) เพื่อประมวลผลและบันทึก")
    
    uploaded_file_statement = st.file_uploader( 
        "ลากและวางไฟล์ Statement Report (CSV) ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["csv"],
        key="ultimate_stmt_uploader_v2_final" # New key
    )

    st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้)", value=False, key="debug_statement_processing_v2")
    
    active_portfolio_id_for_actual = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_for_actual = st.session_state.get('active_portfolio_name_gs', None)

    if uploaded_file_statement:
        file_name_for_saving = uploaded_file_statement.name
        file_size_for_saving = uploaded_file_statement.size 
        
        import hashlib 
        file_hash_for_saving = ""
        try:
            uploaded_file_statement.seek(0) 
            file_content_for_hash = uploaded_file_statement.read()
            uploaded_file_statement.seek(0) 
            file_hash_for_saving = hashlib.md5(file_content_for_hash).hexdigest()
        except Exception as e_hash:
            file_hash_for_saving = f"hash_error_{random.randint(1000,9999)}"
            st.warning(f"ไม่สามารถคำนวณ File Hash: {e_hash}")


        if not active_portfolio_id_for_actual: 
            st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.")
            st.stop()
        
        st.info(f"ไฟล์ที่อัปโหลด: {file_name_for_saving} (ขนาด: {file_size_for_saving} bytes, Hash: {file_hash_for_saving})")
        gc_for_sheets = get_gspread_client()
        if not gc_for_sheets: 
            st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client ได้")
            st.stop()

        # --- START: โค้ดสำหรับเปิด/สร้าง Worksheet อัตโนมัติ และจัดการ Header ---
        ws_dict = {}
        default_sheet_specs = {"rows": "100", "cols": "26"} 
        worksheet_definitions = {
            WORKSHEET_UPLOAD_HISTORY: {"rows": "1000", "cols": "10", "headers": ["UploadTimestamp", "PortfolioID", "PortfolioName", "FileName", "FileSize", "FileHash", "Status", "ImportBatchID", "Notes"]},
            WORKSHEET_ACTUAL_TRADES: {"rows": "1000", "cols": "20", "headers": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_ACTUAL_ORDERS: {"rows": "1000", "cols": "15", "headers": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_ACTUAL_POSITIONS: {"rows": "1000", "cols": "20", "headers": ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_STATEMENT_SUMMARIES: {"rows": "1000", "cols": "40", "headers": ["Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", "Total_Trades", "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count", "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count", "Average_consecutive_wins", "Average_consecutive_losses"]}
        }

        all_sheets_successfully_accessed_or_created = True 
        sh_trade_log = None 
        try:
            sh_trade_log = gc_for_sheets.open(GOOGLE_SHEET_NAME)
            for ws_name, specs in worksheet_definitions.items():
                try:
                    ws_dict[ws_name] = sh_trade_log.worksheet(ws_name)
                    # Check if sheet exists but is empty (row_count == 0 might mean it's truly empty, not even a header row)
                    # or if it has only one row which might be a problematic header.
                    # The save_... functions will handle header writing if the sheet is empty or headers are bad.
                    # This initial check is mostly for creating the sheet if it's entirely missing.
                    # For UploadHistory, we want to ensure headers are there immediately if created.
                    current_ws_headers_check = []
                    if ws_dict[ws_name].row_count > 0 :
                        try: current_ws_headers_check = ws_dict[ws_name].row_values(1)
                        except Exception: pass # Ignore if header cannot be read

                    if not current_ws_headers_check or all(h=="" for h in current_ws_headers_check) or set(current_ws_headers_check) != set(specs["headers"]):
                        if "headers" in specs: # Ensure headers are defined for this sheet
                            ws_dict[ws_name].update([specs["headers"]], value_input_option='USER_ENTERED')
                            st.info(f"Ensured/Updated headers for '{ws_name}' sheet.")

                except gspread.exceptions.WorksheetNotFound:
                    st.info(f"Worksheet '{ws_name}' not found. Creating it now...")
                    try:
                        new_ws = sh_trade_log.add_worksheet(title=ws_name, rows=specs.get("rows", default_sheet_specs["rows"]), cols=specs.get("cols", default_sheet_specs["cols"]))
                        ws_dict[ws_name] = new_ws 
                        if "headers" in specs: 
                            new_ws.update([specs["headers"]], value_input_option='USER_ENTERED') 
                            st.info(f"Created worksheet '{ws_name}' and added headers.")
                    except Exception as e_add_ws:
                        st.error(f"❌ Failed to create worksheet '{ws_name}': {e_add_ws}")
                        all_sheets_successfully_accessed_or_created = False; break 
                except Exception as e_open_ws: 
                    st.error(f"❌ Error accessing worksheet '{ws_name}': {e_open_ws}")
                    all_sheets_successfully_accessed_or_created = False; break
            
            if not all_sheets_successfully_accessed_or_created:
                st.error("One or more essential worksheets could not be accessed or created. Aborting.")
                st.stop()
        
        except gspread.exceptions.APIError as e_api:
            st.error(f"❌ Google Sheets API Error (Opening Spreadsheet or Initial Worksheet Access/Creation): {e_api}.")
            st.stop()
        except Exception as e_setup: 
            st.error(f"❌ เกิดข้อผิดพลาดในการเข้าถึง Spreadsheet หรือสร้าง Worksheet: {type(e_setup).__name__} - {str(e_setup)[:200]}...")
            st.stop()

        for ws_name_key in worksheet_definitions.keys():
            if ws_name_key not in ws_dict or ws_dict[ws_name_key] is None:
                st.error(f"❌ ไม่สามารถเข้าถึงหรือสร้าง Worksheet '{ws_name_key}' ได้อย่างสมบูรณ์ โปรดตรวจสอบ Google Sheets และลองอีกครั้ง")
                st.stop()  
        # ***** END: โค้ดสำหรับเปิด/สร้าง Worksheet อัตโนมัติ *****

        import_batch_id = str(uuid.uuid4()) 
        current_upload_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            ws_dict[WORKSHEET_UPLOAD_HISTORY].append_row([
                current_upload_timestamp, str(active_portfolio_id_for_actual), str(active_portfolio_name_for_actual),
                file_name_for_saving, file_size_for_saving, file_hash_for_saving,
                "Processing", import_batch_id, "Attempting to process file."
            ])
        except Exception as e_log_init:
            st.error(f"ไม่สามารถบันทึก Log เริ่มต้นใน {WORKSHEET_UPLOAD_HISTORY}: {e_log_init}")
            st.stop() 

        st.markdown(f"--- \n**Import Batch ID: `{import_batch_id}`**")
        st.info(f"กำลังประมวลผลไฟล์: {file_name_for_saving}")
        
        overall_processing_successful = True
        any_new_transactional_data_added = False 
        save_results_details = {} 
        
        try:
            uploaded_file_statement.seek(0) 
            file_content_str = uploaded_file_statement.getvalue().decode("utf-8", errors="replace")
            
            with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {file_name_for_saving}..."): 
                extracted_sections = extract_data_from_report_content(file_content_str)
            
            if st.session_state.get("debug_statement_processing_v2", False): 
                st.subheader("📄 ข้อมูลที่แยกได้ (Debug หลัง Parse)")
                if extracted_sections:
                    for section_name_debug, data_item_debug in extracted_sections.items():
                        st.write(f"#### {section_name_debug.replace('_',' ').title()}")
                        if isinstance(data_item_debug, pd.DataFrame):
                            st.dataframe(data_item_debug.head() if not data_item_debug.empty else f"Empty DataFrame for {section_name_debug}")
                        elif isinstance(data_item_debug, dict):
                            st.json(data_item_debug if data_item_debug else f"Empty Dict for {section_name_debug}")
                        else: st.write(data_item_debug)
                else: st.warning("ไม่สามารถแยกส่วนข้อมูลใดๆ ได้จากไฟล์ (Debug)")


            if not extracted_sections: 
                overall_processing_successful = False
                save_results_details['Extraction'] = {'ok': False, 'notes': "Failed to extract sections from file."}
            else:
                st.subheader("💾 กำลังบันทึกข้อมูลส่วนต่างๆไปยัง Google Sheets...")
                
                # Deals
                deals_df = extracted_sections.get('deals', pd.DataFrame())
                ok, new_count, skipped_count = save_deals_to_actual_trades(ws_dict[WORKSHEET_ACTUAL_TRADES], deals_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Deals'] = {'ok': ok, 'new': new_count, 'skipped': skipped_count, 'notes': f"Deals: New={new_count}, Skipped={skipped_count}, Success={ok}"}
                if ok: st.write(f"✔️ ({WORKSHEET_ACTUAL_TRADES}) Deals: เพิ่ม {new_count}, ข้าม {skipped_count}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_TRADES}) Deals: การบันทึกล้มเหลว")
                if new_count > 0: any_new_transactional_data_added = True
                if not ok: overall_processing_successful = False
                
                # Orders
                orders_df = extracted_sections.get('orders', pd.DataFrame())
                ok, new_count, skipped_count = save_orders_to_gsheets(ws_dict[WORKSHEET_ACTUAL_ORDERS], orders_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Orders'] = {'ok': ok, 'new': new_count, 'skipped': skipped_count, 'notes': f"Orders: New={new_count}, Skipped={skipped_count}, Success={ok}"}
                if ok: st.write(f"✔️ ({WORKSHEET_ACTUAL_ORDERS}) Orders: เพิ่ม {new_count}, ข้าม {skipped_count}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_ORDERS}) Orders: การบันทึกล้มเหลว")
                if new_count > 0: any_new_transactional_data_added = True
                if not ok: overall_processing_successful = False

                # Positions
                positions_df = extracted_sections.get('positions', pd.DataFrame())
                ok, new_count, skipped_count = save_positions_to_gsheets(ws_dict[WORKSHEET_ACTUAL_POSITIONS], positions_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Positions'] = {'ok': ok, 'new': new_count, 'skipped': skipped_count, 'notes': f"Positions: New={new_count}, Skipped={skipped_count}, Success={ok}"}
                if ok: st.write(f"✔️ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: เพิ่ม {new_count}, ข้าม {skipped_count}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: การบันทึกล้มเหลว")
                if new_count > 0: any_new_transactional_data_added = True
                if not ok: overall_processing_successful = False
                
                # Summaries
                balance_summary = extracted_sections.get('balance_summary', {})
                results_summary_data_ext = extracted_sections.get('results_summary', {})
                summary_save_attempted = False
                summary_save_ok = True 

                should_save_summary_now = True
                
                # Re-check duplicate file status for summary skipping decision
                is_duplicate_file_check_for_summary = False
                history_records_for_summary_check = []
                try: history_records_for_summary_check = ws_dict[WORKSHEET_UPLOAD_HISTORY].get_all_records(numericise_ignore=['all'])
                except: pass # Ignore if cannot fetch for this specific check

                if history_records_for_summary_check:
                    for record_hist in history_records_for_summary_check:
                        try: record_hist_fsize = int(float(str(record_hist.get("FileSize","0")).replace(",","")))
                        except: record_hist_fsize = 0
                        if str(record_hist.get("PortfolioID","")) == str(active_portfolio_id_for_actual) and \
                           record_hist.get("FileName","") == file_name_for_saving and \
                           record_hist_fsize == file_size_for_saving and \
                           (not file_hash_for_saving or record_hist.get("FileHash","") == file_hash_for_saving or file_hash_for_saving.startswith("hash_")) and \
                           str(record_hist.get("Status","")).startswith("Success") and \
                           record_hist.get("ImportBatchID") != import_batch_id: 
                            is_duplicate_file_check_for_summary = True; break
                
                if is_duplicate_file_check_for_summary and not any_new_transactional_data_added:
                    st.info(f"({WORKSHEET_STATEMENT_SUMMARIES}) ข้ามการบันทึก Summary เนื่องจากไฟล์นี้เป็นไฟล์ซ้ำที่เคยประมวลผลสำเร็จแล้ว และไม่พบข้อมูล Deals/Orders/Positions ใหม่จากการประมวลผลไฟล์ครั้งนี้")
                    save_results_details['Summary'] = {'ok': True, 'status': 'skipped_duplicate_file_no_new_transactions', 'notes': "Summary: Skipped (duplicate file with no new transactional data)."}
                    should_save_summary_now = False
                
                if should_save_summary_now:
                    if balance_summary or results_summary_data_ext:
                        summary_save_attempted = True
                        if st.session_state.get("debug_statement_processing_v2", False): st.write("DEBUG: Pausing 1s before saving summary...")
                        # import time # Ensure time is imported at the top of the script
                        # time.sleep(1) # Optional delay

                        ok_summary_save = save_results_summary_to_gsheets(
                            ws_dict[WORKSHEET_STATEMENT_SUMMARIES], balance_summary, results_summary_data_ext, 
                            active_portfolio_id_for_actual, active_portfolio_name_for_actual, 
                            file_name_for_saving, import_batch_id
                        )
                        save_results_details['Summary'] = {'ok': ok_summary_save, 'status': 'saved' if ok_summary_save else 'failed', 'notes': f"Summary: Attempted, Success={ok_summary_save}"}
                        if ok_summary_save: st.write(f"✔️ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary Data: บันทึกสำเร็จ")
                        else: st.error(f"❌ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary Data: การบันทึกล้มเหลว")
                        summary_save_ok = ok_summary_save
                    else: save_results_details['Summary'] = {'ok': True, 'status': 'no_data_to_save', 'notes': "Summary: No data in file to save."}
                
                if summary_save_attempted and not summary_save_ok: 
                    overall_processing_successful = False

                if overall_processing_successful:
                    if any_new_transactional_data_added or (save_results_details.get('Summary', {}).get('status') == 'saved'):
                        st.balloons(); st.success("ประมวลผลไฟล์สำเร็จและมีการเพิ่มข้อมูลใหม่!")
                    elif is_duplicate_file_check_for_summary and not any_new_transactional_data_added and not should_save_summary_now: 
                        st.info(f"ไฟล์ '{file_name_for_saving}' เป็นไฟล์ซ้ำ และไม่พบรายการข้อมูลใหม่ (รวมถึง Summary ที่ถูกข้ามไป)")
                    else: st.info("ประมวลผลไฟล์สำเร็จ แต่ไม่พบข้อมูลใหม่ที่จะเพิ่ม")
        
        except UnicodeDecodeError as e_decode_main:
            st.error(f"เกิดข้อผิดพลาดในการ Decode ไฟล์หลัก: {e_decode_main}. กรุณาตรวจสอบ Encoding ของไฟล์ (ควรเป็น UTF-8).")
            overall_processing_successful = False
            save_results_details['MainError'] = {'ok': False, 'notes': f"UnicodeDecodeError: {e_decode_main}"}
        except gspread.exceptions.APIError as e_api_main: 
            st.error(f"❌ Google Sheets API Error (Main Processing): {e_api_main}. การประมวลผลอาจไม่สมบูรณ์")
            overall_processing_successful = False
            save_results_details['MainError'] = {'ok': False, 'notes': f"APIError: {e_api_main}"}
        except Exception as e_main:
            st.error(f"เกิดข้อผิดพลาดระหว่างประมวลผลหลัก: {type(e_main).__name__} - {str(e_main)[:200]}...")
            overall_processing_successful = False
            save_results_details['MainError'] = {'ok': False, 'notes': f"MainError: {type(e_main).__name__} - {str(e_main)[:100]}"}
        
        final_processing_notes_list = [res.get('notes', '') for res in save_results_details.values() if res.get('notes')]
        final_notes_str = " | ".join(filter(None, final_processing_notes_list))[:49999] if final_processing_notes_list else "Processing complete."

        final_status = "Failed" 
        if overall_processing_successful:
            if any_new_transactional_data_added or (save_results_details.get('Summary', {}).get('status') == 'saved'): final_status = "Success"
            elif is_duplicate_file_check_for_summary and not any_new_transactional_data_added and save_results_details.get('Summary', {}).get('status') == 'skipped_duplicate_file_no_new_transactions': final_status = "Success_DuplicateFile_NoNewRecords"
            else: final_status = "Success_NoNewRecords"
        
        try:
            if st.session_state.get("debug_statement_processing_v2", False): st.write("DEBUG: Pausing 1s before updating UploadHistory status...")
            # import time # Ensure time is imported
            # time.sleep(1) # Optional delay

            history_rows_for_update = ws_dict[WORKSHEET_UPLOAD_HISTORY].get_all_values() 
            row_to_update_idx = None
            for idx_update, row_val_update in reversed(list(enumerate(history_rows_for_update))):
                if len(row_val_update) > 7 and row_val_update[7] == import_batch_id: 
                    row_to_update_idx = idx_update + 1 
                    break
            
            if row_to_update_idx:
                ws_dict[WORKSHEET_UPLOAD_HISTORY].batch_update([
                    {'range': f'G{row_to_update_idx}', 'values': [[final_status]]},      
                    {'range': f'I{row_to_update_idx}', 'values': [[final_notes_str]]} 
                ], value_input_option='USER_ENTERED')
                st.info(f"อัปเดตสถานะ ImportBatchID '{import_batch_id}' เป็น '{final_status}' ใน {WORKSHEET_UPLOAD_HISTORY}")
            else: st.warning(f"ไม่พบ ImportBatchID '{import_batch_id}' ใน {WORKSHEET_UPLOAD_HISTORY} เพื่ออัปเดตสถานะสุดท้าย.")
        except Exception as e_update_hist: st.warning(f"ไม่สามารถอัปเดตสถานะสุดท้ายใน {WORKSHEET_UPLOAD_HISTORY} ({import_batch_id}): {e_update_hist}")
    else: 
        if uploaded_file_statement is not None: 
             pass 
        # else: 
            # st.info("โปรดอัปโหลดไฟล์ Statement Report (CSV) เพื่อเริ่มต้นประมวลผล.") 

    st.markdown("---")
    


# ===================== SEC 9: MAIN AREA - TRADE LOG VIEWER =======================
@st.cache_data(ttl=120)
def load_planned_trades_from_gsheets_for_viewer():
    gc = get_gspread_client()
    if gc is None: return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        records = worksheet.get_all_records()
        if not records: return pd.DataFrame()
        
        df_logs_viewer = pd.DataFrame(records)
        if 'Timestamp' in df_logs_viewer.columns:
            df_logs_viewer['Timestamp'] = pd.to_datetime(df_logs_viewer['Timestamp'], errors='coerce')
        
        cols_to_numeric_log_viewer = ['Risk %', 'Entry', 'SL', 'TP', 'Lot', 'Risk $', 'RR']
        for col_viewer in cols_to_numeric_log_viewer:
            if col_viewer in df_logs_viewer.columns:
                # แก้ไข: แทนที่จะ replace '' เป็น 'NaN' แล้วค่อยแปลงเป็นตัวเลข
                # ให้แปลงเป็นตัวเลขโดยตรง แล้ว nan() จะเป็นค่า default ถ้าแปลงไม่ได้
                df_logs_viewer[col_viewer] = pd.to_numeric(df_logs_viewer[col_viewer], errors='coerce')
        
        return df_logs_viewer.sort_values(by="Timestamp", ascending=False) if 'Timestamp' in df_logs_viewer.columns else df_logs_viewer
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ Log Viewer: ไม่พบ Worksheet '{WORKSHEET_PLANNED_LOGS}'.")
        return pd.DataFrame()
    except Exception as e_log_viewer:
        st.error(f"❌ Log Viewer: เกิดข้อผิดพลาดในการโหลด Log - {e_log_viewer}")
        return pd.DataFrame()

with st.expander("📚 Trade Log Viewer (แผนเทรดจาก Google Sheets)", expanded=False):
    df_log_viewer_gs = load_planned_trades_from_gsheets_for_viewer()

    if df_log_viewer_gs.empty:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้ใน Google Sheets หรือ Worksheet 'PlannedTradeLogs' ว่างเปล่า.")
    else:
        df_show_log_viewer = df_log_viewer_gs.copy()

        log_filter_cols = st.columns(4)
        with log_filter_cols[0]:
            portfolios_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["PortfolioName"].dropna().unique().tolist()) if "PortfolioName" in df_show_log_viewer else ["ทั้งหมด"]
            portfolio_filter_log = st.selectbox("Portfolio", portfolios_in_log, key="log_viewer_portfolio_filter")
        with log_filter_cols[1]:
            modes_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["Mode"].dropna().unique().tolist()) if "Mode" in df_show_log_viewer else ["ทั้งหมด"]
            mode_filter_log = st.selectbox("Mode", modes_in_log, key="log_viewer_mode_filter")
        with log_filter_cols[2]:
            assets_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["Asset"].dropna().unique().tolist()) if "Asset" in df_show_log_viewer else ["ทั้งหมด"]
            asset_filter_log = st.selectbox("Asset", assets_in_log, key="log_viewer_asset_filter")
        with log_filter_cols[3]:
            date_filter_log = None
            if 'Timestamp' in df_show_log_viewer.columns and not df_show_log_viewer['Timestamp'].isnull().all():
                 date_filter_log = st.date_input("ค้นหาวันที่ (Log)", value=None, key="log_viewer_date_filter", help="เลือกวันที่เพื่อกรอง Log")


        if portfolio_filter_log != "ทั้งหมด" and "PortfolioName" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["PortfolioName"] == portfolio_filter_log]
        if mode_filter_log != "ทั้งหมด" and "Mode" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Mode"] == mode_filter_log]
        if asset_filter_log != "ทั้งหมด" and "Asset" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Asset"] == asset_filter_log]
        if date_filter_log and 'Timestamp' in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Timestamp"].dt.date == date_filter_log]
        
        st.markdown("---")
        st.markdown("**Log Details & Actions:**")
        
        cols_to_display = {
            "Timestamp": "Timestamp", "PortfolioName": "Portfolio", "Asset": "Asset",
            "Mode": "Mode", "Direction": "Direction", "Entry": "Entry", "SL": "SL", "TP": "TP",
            "Lot": "Lot", "Risk $": "Risk $" , "RR": "RR"
        }
        actual_cols_to_display = {k:v for k,v in cols_to_display.items() if k in df_show_log_viewer.columns}
        
        num_display_cols = len(actual_cols_to_display)
        header_display_cols = st.columns(num_display_cols + 1)

        for i, (col_key, col_name) in enumerate(actual_cols_to_display.items()):
            header_display_cols[i].markdown(f"**{col_name}**")
        header_display_cols[num_display_cols].markdown(f"**Action**")


        for index_log, row_log in df_show_log_viewer.iterrows():
            row_display_cols = st.columns(num_display_cols + 1)
            for i, col_key in enumerate(actual_cols_to_display.keys()):
                val = row_log.get(col_key, "-")
                if isinstance(val, float):
                    row_display_cols[i].write(f"{val:.2f}" if not np.isnan(val) else "-")
                elif isinstance(val, pd.Timestamp):
                    row_display_cols[i].write(val.strftime("%Y-%m-%d %H:%M") if pd.notnull(val) else "-")
                else:
                    row_display_cols[i].write(str(val) if pd.notnull(val) and str(val).strip() != "" else "-")

            if row_display_cols[num_display_cols].button(f"📈 Plot", key=f"plot_log_{row_log.get('LogID', index_log)}"):
                st.session_state['plot_data'] = row_log.to_dict()
                st.success(f"เลือกข้อมูลเทรด '{row_log.get('Asset', '-')}' ที่ Entry '{row_log.get('Entry', '-')}' เตรียมพร้อมสำหรับ Plot บน Chart Visualizer!")
                st.rerun()
        
        if 'plot_data' in st.session_state and st.session_state['plot_data']:
            st.sidebar.success(f"ข้อมูลพร้อม Plot: {st.session_state['plot_data'].get('Asset')} @ {st.session_state['plot_data'].get('Entry')}")
            st.sidebar.json(st.session_state['plot_data'], expanded=False)
