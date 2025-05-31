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

# ฟังก์ชันสำหรับเชื่อมต่อ gspread
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
with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=False): # Default to collapsed
    st.subheader("พอร์ตทั้งหมดของคุณ")
    # df_portfolios_gs should be loaded globally/module level before this UI section
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

 with st.form("new_portfolio_form_main_v5", clear_on_submit=True): # Key ใหม่ v5
        st.markdown("**กรอกข้อมูลพอร์ตใหม่:**")
        
        form_c1, form_c2 = st.columns(2)
        with form_c1:
            form_new_portfolio_name = st.text_input("ชื่อพอร์ต (Portfolio Name)*", key="form_pf_name_v5")
            form_program_type_options = ["", "Personal Account", "Prop Firm Challenge", "Funded Account", "Trading Competition"]
            selected_program_type = st.selectbox("ประเภทพอร์ต (Program Type)*", options=form_program_type_options, index=0, key="form_pf_type_v5")
        with form_c2:
            form_new_initial_balance = st.number_input("บาลานซ์เริ่มต้น (Initial Balance)*", min_value=0.01, value=10000.0, step=100.0, format="%.2f", key="form_pf_balance_v5")
            form_status_options = ["Active", "Inactive", "Pending", "Passed", "Failed"]
            form_new_status = st.selectbox("สถานะพอร์ต (Status)*", options=form_status_options, index=form_status_options.index("Active"), key="form_pf_status_v5")
        
        form_new_evaluation_step_val = ""
        if selected_program_type == "Prop Firm Challenge":
            evaluation_step_options = ["", "Phase 1", "Phase 2", "Phase 3", "Verification"]
            form_new_evaluation_step_val = st.selectbox("ขั้นตอนการประเมิน (Evaluation Step)", 
                                                        options=evaluation_step_options, index=0, 
                                                        help="เลือกขั้นตอนการประเมินของ Prop Firm Challenge", 
                                                        key="form_pf_eval_step_select_v5")

        # --- Conditional Inputs Defaults ---
        form_profit_target_val = 8.0; form_daily_loss_val = 5.0; form_total_stopout_val = 10.0; form_leverage_val = 100.0; form_min_days_val = 0
        form_comp_end_date = None; form_comp_goal_metric = ""
        form_pers_overall_profit_val = 0.0; form_pers_target_end_date = None; form_pers_weekly_profit_val = 0.0; form_pers_daily_profit_val = 0.0
        form_pers_max_dd_overall_val = 0.0; form_pers_max_dd_daily_val = 0.0
        form_enable_scaling_checkbox_val = False; form_scaling_freq_val = "Weekly"; form_su_wr_val = 55.0; form_su_gain_val = 2.0; form_su_inc_val = 0.25
        form_sd_loss_val = -5.0; form_sd_wr_val = 40.0; form_sd_dec_val = 0.25; form_min_risk_val = 0.25; form_max_risk_val = 2.0; form_current_risk_val = 1.0
        form_notes_val = ""

        if selected_program_type in ["Prop Firm Challenge", "Funded Account"]:
            st.markdown("**กฎเกณฑ์ Prop Firm/Funded:**")
            f_pf1, f_pf2, f_pf3 = st.columns(3)
            with f_pf1: form_profit_target_val = st.number_input("เป้าหมายกำไร %*", value=form_profit_target_val, format="%.1f", key="f_pf_profit_v5")
            with f_pf2: form_daily_loss_val = st.number_input("จำกัดขาดทุนต่อวัน %*", value=form_daily_loss_val, format="%.1f", key="f_pf_dd_v5")
            with f_pf3: form_total_stopout_val = st.number_input("จำกัดขาดทุนรวม %*", value=form_total_stopout_val, format="%.1f", key="f_pf_maxdd_v5")
            f_pf_col1, f_pf_col2 = st.columns(2)
            with f_pf_col1: form_leverage_val = st.number_input("Leverage", value=form_leverage_val, format="%.0f", key="f_pf_lev_v5")
            with f_pf_col2: form_min_days_val = st.number_input("จำนวนวันเทรดขั้นต่ำ", value=form_min_days_val, step=1, key="f_pf_mindays_v5")
        
        if selected_program_type == "Trading Competition":
            st.markdown("**ข้อมูลการแข่งขัน:**")
            f_tc1, f_tc2 = st.columns(2)
            with f_tc1: 
                form_comp_end_date = st.date_input("วันสิ้นสุดการแข่งขัน", value=form_comp_end_date, key="f_tc_enddate_v5")
                form_profit_target_val = st.number_input("เป้าหมายกำไร % (Comp)", value=20.0, format="%.1f", key="f_tc_profit_v5")
            with f_tc2: 
                form_comp_goal_metric = st.text_input("ตัวชี้วัดเป้าหมาย (Comp)", value=form_comp_goal_metric, help="เช่น %Gain, ROI", key="f_tc_goalmetric_v5")
                form_daily_loss_val = st.number_input("จำกัดขาดทุนต่อวัน % (Comp)", value=5.0, format="%.1f", key="f_tc_dd_v5")
                form_total_stopout_val = st.number_input("จำกัดขาดทุนรวม % (Comp)", value=10.0, format="%.1f", key="f_tc_maxdd_v5")

        if selected_program_type == "Personal Account":
            st.markdown("**เป้าหมายส่วนตัว (Optional):**")
            f_ps1, f_ps2 = st.columns(2)
            with f_ps1:
                # --- แก้ไข label ที่นี่ ---
                form_pers_overall_profit_val = st.number_input("เป้าหมายกำไรโดยรวม ($)", value=form_pers_overall_profit_val, format="%.2f", key="f_ps_profit_overall_v5")
                form_pers_weekly_profit_val = st.number_input("เป้าหมายกำไรรายสัปดาห์ ($)", value=form_pers_weekly_profit_val, format="%.2f", key="f_ps_profit_weekly_v5")
                form_pers_max_dd_overall_val = st.number_input("Max DD รวมที่ยอมรับได้ ($)", value=form_pers_max_dd_overall_val, format="%.2f", key="f_ps_dd_overall_v5")
            with f_ps2:
                form_pers_target_end_date = st.date_input("วันที่คาดว่าจะถึงเป้าหมายรวม", value=form_pers_target_end_date, key="f_ps_enddate_v5")
                form_pers_daily_profit_val = st.number_input("เป้าหมายกำไรรายวัน ($)", value=form_pers_daily_profit_val, format="%.2f", key="f_ps_profit_daily_v5")
                form_pers_max_dd_daily_val = st.number_input("Max DD ต่อวันที่ยอมรับได้ ($)", value=form_pers_max_dd_daily_val, format="%.2f", key="f_ps_dd_daily_v5")

        st.markdown("**การตั้งค่า Scaling Manager (Optional):**")
        form_enable_scaling_checkbox_val = st.checkbox("เปิดใช้งาน Scaling Manager?", value=form_enable_scaling_checkbox_val, key="f_scale_enable_v5")
        if form_enable_scaling_checkbox_val:
            f_sc1, f_sc2, f_sc3 = st.columns(3)
            with f_sc1:
                form_scaling_freq_val = st.selectbox("ความถี่ตรวจสอบ Scaling", ["Weekly", "Monthly"], index=["Weekly", "Monthly"].index(form_scaling_freq_val), key="f_scale_freq_v5")
                form_su_wr_val = st.number_input("Scale Up: Min Winrate %", value=form_su_wr_val, format="%.1f", key="f_scale_su_wr_v5")
                form_sd_loss_val = st.number_input("Scale Down: Max Loss %", value=form_sd_loss_val, format="%.1f", key="f_scale_sd_loss_v5")
            with f_sc2:
                form_min_risk_val = st.number_input("Min Risk % Allowed", value=form_min_risk_val, format="%.2f", key="f_scale_min_risk_v5")
                form_su_gain_val = st.number_input("Scale Up: Min Gain %", value=form_su_gain_val, format="%.1f", key="f_scale_su_gain_v5")
                form_sd_wr_val = st.number_input("Scale Down: Low Winrate %", value=form_sd_wr_val, format="%.1f", key="f_scale_sd_wr_v5")
            with f_sc3:
                form_max_risk_val = st.number_input("Max Risk % Allowed", value=form_max_risk_val, format="%.2f", key="f_scale_max_risk_v5")
                form_su_inc_val = st.number_input("Scale Up: Risk Increment %", value=form_su_inc_val, format="%.2f", key="f_scale_su_inc_v5")
                form_sd_dec_val = st.number_input("Scale Down: Risk Decrement %", value=form_sd_dec_val, format="%.2f", key="f_scale_sd_dec_v5")
            form_current_risk_val = st.number_input("Current Risk % (สำหรับ Scaling)", value=form_current_risk_val, format="%.2f", key="f_scale_current_risk_v5")

        form_notes_val = st.text_area("หมายเหตุเพิ่มเติม (Notes)", value=form_notes_val, key="f_pf_notes_v5")

        submitted_add_portfolio = st.form_submit_button("💾 บันทึกพอร์ตใหม่")
        
        if submitted_add_portfolio:
            # Validation
            if not form_new_portfolio_name or not selected_program_type or not form_new_status or form_new_initial_balance <= 0:
                st.warning("กรุณากรอกข้อมูลที่จำเป็น (*) ให้ครบถ้วนและถูกต้อง: ชื่อพอร์ต, ประเภทพอร์ต, สถานะพอร์ต, และยอดเงินเริ่มต้นต้องมากกว่า 0")
            elif 'df_portfolios_gs' in locals() and not df_portfolios_gs.empty and form_new_portfolio_name in df_portfolios_gs['PortfolioName'].astype(str).values:
                st.error(f"ชื่อพอร์ต '{form_new_portfolio_name}' มีอยู่แล้ว กรุณาใช้ชื่ออื่น")
            else:
                new_id_value = str(uuid.uuid4())
                new_portfolio_row_data = {
                    'PortfolioID': new_id_value,
                    'PortfolioName': form_new_portfolio_name, 'ProgramType': selected_program_type,
                    'EvaluationStep': form_new_evaluation_step_val if selected_program_type == "Prop Firm Challenge" else "", 
                    'Status': form_new_status,
                    'InitialBalance': form_new_initial_balance, 'CreationDate': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'ProfitTargetPercent': form_profit_target_val if selected_program_type in ["Prop Firm Challenge", "Funded Account", "Trading Competition"] else None,
                    'DailyLossLimitPercent': form_daily_loss_val if selected_program_type in ["Prop Firm Challenge", "Funded Account", "Trading Competition"] else None,
                    'TotalStopoutPercent': form_total_stopout_val if selected_program_type in ["Prop Firm Challenge", "Funded Account", "Trading Competition"] else None,
                    'Leverage': form_leverage_val if selected_program_type in ["Prop Firm Challenge", "Funded Account"] else None,
                    'MinTradingDays': form_min_days_val if selected_program_type in ["Prop Firm Challenge", "Funded Account"] else None,
                    'CompetitionEndDate': form_comp_end_date.strftime("%Y-%m-%d") if selected_program_type == "Trading Competition" and form_comp_end_date else None,
                    'CompetitionGoalMetric': form_comp_goal_metric if selected_program_type == "Trading Competition" else None,
                    'OverallProfitTarget': form_pers_overall_profit_val if selected_program_type == "Personal Account" else None,
                    'TargetEndDate': form_pers_target_end_date.strftime("%Y-%m-%d") if selected_program_type == "Personal Account" and form_pers_target_end_date else None,
                    'WeeklyProfitTarget': form_pers_weekly_profit_val if selected_program_type == "Personal Account" else None,
                    'DailyProfitTarget': form_pers_daily_profit_val if selected_program_type == "Personal Account" else None,
                    'MaxAcceptableDrawdownOverall': form_pers_max_dd_overall_val if selected_program_type == "Personal Account" else None,
                    'MaxAcceptableDrawdownDaily': form_pers_max_dd_daily_val if selected_program_type == "Personal Account" else None,
                    'EnableScaling': form_enable_scaling_checkbox_val,
                    'ScalingCheckFrequency': form_scaling_freq_val if form_enable_scaling_checkbox_val else None,
                    'ScaleUp_MinWinRate': form_su_wr_val if form_enable_scaling_checkbox_val else None,
                    'ScaleUp_MinGainPercent': form_su_gain_val if form_enable_scaling_checkbox_val else None,
                    'ScaleUp_RiskIncrementPercent': form_su_inc_val if form_enable_scaling_checkbox_val else None,
                    'ScaleDown_MaxLossPercent': form_sd_loss_val if form_enable_scaling_checkbox_val else None,
                    'ScaleDown_LowWinRate': form_sd_wr_val if form_enable_scaling_checkbox_val else None,
                    'ScaleDown_RiskDecrementPercent': form_sd_dec_val if form_enable_scaling_checkbox_val else None,
                    'MinRiskPercentAllowed': form_min_risk_val if form_enable_scaling_checkbox_val else None,
                    'MaxRiskPercentAllowed': form_max_risk_val if form_enable_scaling_checkbox_val else None,
                    'CurrentRiskPercent': form_current_risk_val,
                    'Notes': form_notes_val
                }
                
                success_save = save_new_portfolio_to_gsheets(new_portfolio_row_data) 
                
                if success_save:
                    st.success(f"เพิ่มพอร์ต '{form_new_portfolio_name}' (ID: {new_id_value}) สำเร็จ!")
                    if hasattr(load_portfolios_from_gsheets, 'clear'):
                         load_portfolios_from_gsheets.clear()
                    st.rerun()
                else:
                    st.error("เกิดข้อผิดพลาดในการบันทึกพอร์ตใหม่ไปยัง Google Sheets")
# ==============================================================================
# END: ส่วนจัดการ Portfolio (SEC 1.5)
# ==============================================================================
# ==============================================================================
# END: ส่วนจัดการ Portfolio
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

if st.sidebar.button("🔄 Reset Form"):
    risk_keep = st.session_state.get("risk_pct", 1.0)
    asset_keep = st.session_state.get("asset", "XAUUSD")
    drawdown_limit_keep = st.session_state.get("drawdown_limit_pct", 2.0)
    
    keys_to_keep = {"risk_pct", "asset", "drawdown_limit_pct", "mode", 
                    "active_portfolio_name_gs", "active_portfolio_id_gs",
                    "gcp_service_account"}

    for k in list(st.session_state.keys()):
        if k not in keys_to_keep:
            del st.session_state[k]

    st.session_state["risk_pct"] = risk_keep
    st.session_state["asset"] = asset_keep
    st.session_state["drawdown_limit_pct"] = drawdown_limit_keep
    st.session_state["fibo_flags"] = [False] * 5
    st.rerun()

# ===================== SEC 2.2: FIBO TRADE DETAILS =======================
if mode == "FIBO":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value=st.session_state.get("asset", "XAUUSD"), key="asset")
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            value=st.session_state.get("risk_pct", 1.0),
            step=0.01,
            format="%.2f",
            key="risk_pct"
        )
    with col3:
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True, key="fibo_direction")

    col4, col5 = st.sidebar.columns(2)
    with col4:
        swing_high = st.text_input("High", key="swing_high")
    with col5:
        swing_low = st.text_input("Low", key="swing_low")

    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibos = [0.114, 0.25, 0.382, 0.5, 0.618]
    labels = [f"{l:.3f}" for l in fibos]
    cols = st.sidebar.columns(len(fibos))

    if "fibo_flags" not in st.session_state:
        st.session_state.fibo_flags = [True] * len(fibos)

    fibo_selected_flags = []
    for i, col in enumerate(cols):
        checked = col.checkbox(labels[i], value=st.session_state.fibo_flags[i], key=f"fibo_cb_{i}")
        fibo_selected_flags.append(checked)

    st.session_state.fibo_flags = fibo_selected_flags

    try:
        high_val = float(swing_high) if swing_high else 0
        low_val = float(swing_low) if swing_low else 0
        if swing_high and swing_low and high_val <= low_val:
            st.sidebar.warning("High ต้องมากกว่า Low!")
    except ValueError:
        if swing_high or swing_low:
            st.sidebar.warning("กรุณาใส่ High/Low เป็นตัวเลขที่ถูกต้อง")
    except Exception:
        pass

    if 'risk_pct' in st.session_state and st.session_state.risk_pct <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")

    st.sidebar.markdown("---")
    try:
        high_preview = float(swing_high)
        low_preview = float(swing_low)
        if high_preview > low_preview and any(st.session_state.fibo_flags):
            st.sidebar.markdown("**Preview (เบื้องต้น):**")
            first_selected_fibo_index = st.session_state.fibo_flags.index(True)
            if direction == "Long":
                preview_entry = low_preview + (high_preview - low_preview) * fibos[first_selected_fibo_index]
            else:
                preview_entry = high_preview - (high_preview - low_preview) * fibos[first_selected_fibo_index]
            st.sidebar.markdown(f"Entry แรกที่เลือก ≈ **{preview_entry:.2f}**")
            st.sidebar.caption("Lot/TP/ผลลัพธ์เต็มอยู่ด้านล่าง (ใน Strategy Summary)")
    except Exception:
        pass

    save_fibo = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo")

# ===================== SEC 2.3: CUSTOM TRADE DETAILS =======================
elif mode == "CUSTOM":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value=st.session_state.get("asset", "XAUUSD"), key="asset_custom")
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            value=st.session_state.get("risk_pct_custom", 1.00),
            step=0.01,
            format="%.2f",
            key="risk_pct_custom"
        )
    with col3:
        n_entry = st.number_input(
            "จำนวนไม้",
            min_value=1,
            max_value=10,
            value=st.session_state.get("n_entry_custom", 2),
            step=1,
            key="n_entry_custom"
        )

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")
    custom_inputs = []
    current_custom_risk_pct = st.session_state.get("risk_pct_custom", 1.0)
    risk_per_trade = current_custom_risk_pct / 100
    risk_dollar_total = acc_balance * risk_per_trade
    num_entries_val = st.session_state.get("n_entry_custom", 1)
    risk_dollar_per_entry = risk_dollar_total / num_entries_val if num_entries_val > 0 else 0

    for i in range(int(num_entries_val)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e, col_s, col_t = st.sidebar.columns(3)
        with col_e:
            entry = st.text_input(f"Entry {i+1}", value=st.session_state.get(f"custom_entry_{i}", "0.00"), key=f"custom_entry_{i}")
        with col_s:
            sl = st.text_input(f"SL {i+1}", value=st.session_state.get(f"custom_sl_{i}", "0.00"), key=f"custom_sl_{i}")
        with col_t:
            tp = st.text_input(f"TP {i+1}", value=st.session_state.get(f"custom_tp_{i}", "0.00"), key=f"custom_tp_{i}")
        
        try:
            entry_val = float(entry)
            sl_val = float(sl)
            stop = abs(entry_val - sl_val)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            lot_display = f"Lot: {lot:.2f}" if stop > 0 else "Lot: - (Invalid SL)"
            risk_per_entry_display = f"Risk$ ต่อไม้: {risk_dollar_per_entry:.2f}"
        except ValueError:
            lot_display = "Lot: - (Error)"
            risk_per_entry_display = "Risk$ ต่อไม้: - (Error)"
            stop = None
        except Exception:
            lot_display = "Lot: -"
            risk_per_entry_display = "Risk$ ต่อไม้: -"
            stop = None

        try:
            if stop is not None and stop > 0:
                tp_rr3_info = f"Stop: {stop:.2f}"
            else:
                tp_rr3_info = "TP (RR=3): - (SL Error)"
        except Exception:
            tp_rr3_info = "TP (RR=3): -"
        
        st.sidebar.caption(f"{lot_display} | {risk_per_entry_display} | {tp_rr3_info}")
        custom_inputs.append({"entry": entry, "sl": sl, "tp": tp})

    if current_custom_risk_pct <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")
    save_custom = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom")

# ===================== SEC 3: SIDEBAR - CALCULATIONS, SUMMARY & ACTIONS =======================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")

entry_data = []
custom_entries_summary = []

if mode == "FIBO":
    try:
        current_fibo_risk_pct = st.session_state.get("risk_pct", 1.0)
        current_fibo_direction = st.session_state.get("fibo_direction", "Long")
        current_swing_high = st.session_state.get("swing_high", "")
        current_swing_low = st.session_state.get("swing_low", "")
        current_fibo_flags = st.session_state.get("fibo_flags", [False]*5)

        high = float(current_swing_high)
        low = float(current_swing_low)
        selected_fibo_levels = [fibos[i] for i, sel in enumerate(current_fibo_flags) if sel]
        n = len(selected_fibo_levels)
        risk_per_trade = current_fibo_risk_pct / 100
        risk_dollar_total = acc_balance * risk_per_trade
        risk_dollar_per_entry = risk_dollar_total / n if n > 0 else 0
        
        for idx, fibo_level_val in enumerate(selected_fibo_levels):
            if current_fibo_direction == "Long":
                entry = low + (high - low) * fibo_level_val
                sl = low
            else:
                entry = high - (high - low) * fibo_level_val
                sl = high
            
            stop = abs(entry - sl)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            risk_val = stop * lot if stop > 0 else 0

            if stop > 0:
                if current_fibo_direction == "Long":
                    tp1 = entry + (stop * 1.618)
                else:
                    tp1 = entry - (stop * 1.618)
                tp_display = f"{tp1:.2f}"
            else:
                tp_display = "-"

            entry_data.append({
                "Fibo Level": f"{fibo_level_val:.3f}",
                "Entry": f"{entry:.2f}",
                "SL": f"{sl:.2f}",
                "TP": tp_display, 
                "Lot": f"{lot:.2f}" if stop > 0 else "0.00",
                "Risk $": f"{risk_val:.2f}" if stop > 0 else "0.00",
            })
        if entry_data:
            entry_df_summary = pd.DataFrame(entry_data)
            st.sidebar.write(f"**Total Lots:** {entry_df_summary['Lot'].astype(float).sum():.2f}")
            st.sidebar.write(f"**Total Risk $:** {entry_df_summary['Risk $'].astype(float).sum():.2f}")
    except ValueError:
        if current_swing_high or current_swing_low:
             st.sidebar.warning("กรอก High/Low ให้ถูกต้องเพื่อดู Summary")
    except Exception as e:
        pass 
elif mode == "CUSTOM":
    try:
        num_entries_val_summary = st.session_state.get("n_entry_custom", 1)
        current_custom_risk_pct_summary = st.session_state.get("risk_pct_custom", 1.0)

        risk_per_trade_summary = current_custom_risk_pct_summary / 100
        risk_dollar_total_summary = acc_balance * risk_per_trade_summary
        risk_dollar_per_entry_summary = risk_dollar_total_summary / num_entries_val_summary if num_entries_val_summary > 0 else 0
        
        rr_list = []
        for i in range(int(num_entries_val_summary)):
            entry_val_str = st.session_state.get(f"custom_entry_{i}", "0.00")
            sl_val_str = st.session_state.get(f"custom_sl_{i}", "0.00")
            tp_val_str = st.session_state.get(f"custom_tp_{i}", "0.00")

            entry_val = float(entry_val_str)
            sl_val = float(sl_val_str)
            tp_val = float(tp_val_str)

            stop = abs(entry_val - sl_val)
            target = abs(tp_val - entry_val)
            lot = risk_dollar_per_entry_summary / stop if stop > 0 else 0
            rr = (target / stop) if stop > 0 else 0
            rr_list.append(rr)
            custom_entries_summary.append({
                "Entry": f"{entry_val:.2f}",
                "SL": f"{sl_val:.2f}",
                "TP": f"{tp_val:.2f}",
                "Lot": f"{lot:.2f}" if stop > 0 else "0.00",
                "Risk $": f"{risk_dollar_per_entry_summary:.2f}" if stop > 0 else "0.00",
                "RR": f"{rr:.2f}" if stop > 0 else "0.00"
            })
        if custom_entries_summary:
            custom_df_summary = pd.DataFrame(custom_entries_summary)
            st.sidebar.write(f"**Total Lots:** {custom_df_summary['Lot'].astype(float).sum():.2f}")
            st.sidebar.write(f"**Total Risk $:** {custom_df_summary['Risk $'].astype(float).sum():.2f}")
            avg_rr = np.mean([r for r in rr_list if r > 0]) if any(r > 0 for r in rr_list) else 0
            if avg_rr > 0 :
                st.sidebar.write(f"**Average RR:** {avg_rr:.2f}")
    except ValueError:
        st.sidebar.warning("กรอก Entry/SL/TP ให้ถูกต้องเพื่อดู Summary")
    except Exception as e:
        pass

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
        ws_planned_logs = sh_scaling.worksheet(WORKSHEET_PLANNED_LOGS)
        records_scaling = ws_planned_logs.get_all_records()
        if records_scaling:
            df_planned_logs_for_scaling = pd.DataFrame(records_scaling)
    except Exception as e:
        pass

winrate_perf, gain_perf, total_trades_perf = get_performance(df_planned_logs_for_scaling.copy(), mode="week")

current_risk_for_scaling = 1.0
if mode == "FIBO":
    current_risk_for_scaling = st.session_state.get("risk_pct", 1.0)
elif mode == "CUSTOM":
    current_risk_for_scaling = st.session_state.get("risk_pct_custom", 1.0)

scaling_step_val = st.session_state.get('scaling_step', 0.25)
max_risk_pct_val = st.session_state.get('max_risk_pct', 5.0)
min_risk_pct_val = st.session_state.get('min_risk_pct', 0.5)
current_scaling_mode = st.session_state.get('scaling_mode', 'Manual')

suggest_risk = current_risk_for_scaling
scaling_msg = "Risk% คงที่ (ยังไม่มีข้อมูล Performance เพียงพอ หรือ Performance อยู่ในเกณฑ์)"

if total_trades_perf > 0:
    if winrate_perf > 55 and gain_perf > 0.02 * acc_balance:
        suggest_risk = min(current_risk_for_scaling + scaling_step_val, max_risk_pct_val)
        scaling_msg = f"🎉 ผลงานดี! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f}. แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}%"
    elif winrate_perf < 45 or gain_perf < 0:
        suggest_risk = max(current_risk_for_scaling - scaling_step_val, min_risk_pct_val)
        scaling_msg = f"⚠️ ควรลด Risk%! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f}. แนะนำลด Risk% เป็น {suggest_risk:.2f}%"
    else:
        scaling_msg = f"Risk% คงที่ (Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f})"

st.sidebar.info(scaling_msg)

if current_scaling_mode == "Manual" and abs(suggest_risk - current_risk_for_scaling) > 0.001:
    if st.sidebar.button(f"ปรับ Risk% เป็น {suggest_risk:.2f}%"):
        if mode == "FIBO":
            st.session_state.risk_pct = suggest_risk
        elif mode == "CUSTOM":
            st.session_state.risk_pct_custom = suggest_risk
        st.rerun()
elif current_scaling_mode == "Auto":
    if abs(suggest_risk - current_risk_for_scaling) > 0.001:
        if mode == "FIBO":
            st.session_state.risk_pct = suggest_risk
        elif mode == "CUSTOM":
            st.session_state.risk_pct_custom = suggest_risk

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

df_drawdown_check = pd.DataFrame()
gc_drawdown = get_gspread_client()
if gc_drawdown:
    try:
        sh_drawdown = gc_drawdown.open(GOOGLE_SHEET_NAME)
        ws_planned_logs_drawdown = sh_drawdown.worksheet(WORKSHEET_PLANNED_LOGS)
        records_drawdown = ws_planned_logs_drawdown.get_all_records()
        if records_drawdown:
            df_drawdown_check = pd.DataFrame(records_drawdown)
    except Exception as e:
        pass

drawdown_today = get_today_drawdown(df_drawdown_check.copy(), acc_balance)
drawdown_limit_pct_val = st.session_state.get('drawdown_limit_pct', 2.0)
drawdown_limit_abs = -acc_balance * (drawdown_limit_pct_val / 100)

if drawdown_today < 0:
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** <font color='red'>{drawdown_today:,.2f} USD</font>", unsafe_allow_html=True)
else:
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** {drawdown_today:,.2f} USD")

active_portfolio_id = st.session_state.get('active_portfolio_id_gs', None)
active_portfolio_name = st.session_state.get('active_portfolio_name_gs', None)

asset_to_save = ""
risk_pct_to_save = 0.0
direction_to_save = "N/A"
data_to_save = []

if mode == "FIBO":
    asset_to_save = st.session_state.get("asset", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct", 1.0)
    direction_to_save = st.session_state.get("fibo_direction", "Long")
    data_to_save = entry_data
    save_button_pressed = save_fibo
elif mode == "CUSTOM":
    asset_to_save = st.session_state.get("asset_custom", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct_custom", 1.0)
    direction_to_save = st.session_state.get("custom_direction_for_log", "N/A")
    data_to_save = custom_entries_summary
    save_button_pressed = save_custom

if save_button_pressed and data_to_save:
    if drawdown_today <= drawdown_limit_abs and drawdown_limit_abs < 0 :
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนจากแผนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit_abs):,.2f} ({drawdown_limit_pct_val:.1f}%)"
        )
    elif not active_portfolio_id:
        st.sidebar.error("กรุณาเลือกพอร์ตที่ใช้งานก่อนบันทึกแผน")
    else:
        try:
            if save_plan_to_gsheets(data_to_save, mode, asset_to_save, risk_pct_to_save, direction_to_save, active_portfolio_id, active_portfolio_name):
                st.sidebar.success(f"บันทึกแผน ({mode}) สำหรับพอร์ต '{active_portfolio_name}' ลง Google Sheets สำเร็จ!")
                st.balloons()
            else:
                st.sidebar.error(f"Save ({mode}) ไปยัง Google Sheets ไม่สำเร็จ.")
        except Exception as e:
            st.sidebar.error(f"Save ({mode}) ไม่สำเร็จ: {e}")

# ===================== SEC 4: MAIN AREA - ENTRY PLAN DETAILS TABLE =======================
with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):
    if mode == "FIBO":
        col1_main, col2_main = st.columns(2)
        with col1_main:
            st.markdown("### 🎯 Entry Levels (FIBO)")
            if entry_data:
                entry_df_main = pd.DataFrame(entry_data)
                st.dataframe(entry_df_main, hide_index=True, use_container_width=True)
            else:
                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level ใน Sidebar เพื่อดู Entry Levels.")
        with col2_main:
            st.markdown("### 🎯 Take Profit Zones (FIBO)")
            try:
                current_swing_high_tp = st.session_state.get("swing_high", "")
                current_swing_low_tp = st.session_state.get("swing_low", "")
                current_fibo_direction_tp = st.session_state.get("fibo_direction", "Long")

                high_tp = float(current_swing_high_tp)
                low_tp = float(current_swing_low_tp)

                if high_tp > low_tp:
                    if current_fibo_direction_tp == "Long":
                        tp1_main = low_tp + (high_tp - low_tp) * 1.618
                        tp2_main = low_tp + (high_tp - low_tp) * 2.618
                        tp3_main = low_tp + (high_tp - low_tp) * 4.236
                    else:
                        tp1_main = high_tp - (high_tp - low_tp) * 1.618
                        tp2_main = high_tp - (high_tp - low_tp) * 2.618
                        tp3_main = high_tp - (high_tp - low_tp) * 4.236
                    tp_df_main = pd.DataFrame({
                        "TP Zone": ["TP1 (1.618)", "TP2 (2.618)", "TP3 (4.236)"],
                        "Price": [f"{tp1_main:.2f}", f"{tp2_main:.2f}", f"{tp3_main:.2f}"]
                    })
                    st.dataframe(tp_df_main, hide_index=True, use_container_width=True)
                else:
                    if current_swing_high_tp or current_swing_low_tp :
                        st.warning("📌 High ต้องมากกว่า Low เพื่อคำนวณ TP.")
                    else:
                        st.info("📌 กรอก High/Low ใน Sidebar เพื่อดู TP.")
            except ValueError:
                 if current_swing_high_tp or current_swing_low_tp :
                    st.warning("📌 กรอก High/Low เป็นตัวเลขที่ถูกต้องเพื่อคำนวณ TP.")
                 else:
                    st.info("📌 กรอก High/Low ใน Sidebar เพื่อดู TP.")
            except Exception:
                st.info("📌 เกิดข้อผิดพลาดในการคำนวณ TP.")

    elif mode == "CUSTOM":
        st.markdown("### 🎯 Entry & Take Profit Zones (CUSTOM)")
        if custom_entries_summary:
            custom_df_main = pd.DataFrame(custom_entries_summary)
            st.dataframe(custom_df_main, hide_index=True, use_container_width=True)
            for i, row_data_dict in enumerate(custom_entries_summary):
                try:
                    rr_val_str = row_data_dict.get("RR", "0")
                    rr_val = float(rr_val_str)
                    if rr_val < 2 and rr_val > 0:
                        st.warning(f"🎯 Entry {i+1} มี RR ค่อนข้างต่ำ ({rr_val:.2f}) — ลองปรับ TP/SL เพื่อ Risk:Reward ที่ดีขึ้น")
                except ValueError:
                    pass
                except Exception:
                    pass
        else:
            st.info("กรอกข้อมูล Custom ใน Sidebar เพื่อดู Entry & TP Zones.")

# ===================== SEC 5: MAIN AREA - CHART VISUALIZER =======================
with st.expander("📈 Chart Visualizer", expanded=True):
    asset_to_display = "OANDA:XAUUSD"
    current_asset_input = ""
    if mode == "FIBO":
        current_asset_input = st.session_state.get("asset", "XAUUSD")
    elif mode == "CUSTOM":
        current_asset_input = st.session_state.get("asset_custom", "XAUUSD")
    
    if current_asset_input.upper() == "XAUUSD":
        asset_to_display = "OANDA:XAUUSD"
    elif current_asset_input.upper() == "EURUSD":
        asset_to_display = "OANDA:EURUSD"
    elif current_asset_input:
        asset_to_display = current_asset_input.upper()

    if 'plot_data' in st.session_state and st.session_state['plot_data']:
        asset_from_log = st.session_state['plot_data'].get('Asset', asset_to_display)
        if asset_from_log.upper() == "XAUUSD":
            asset_to_display = "OANDA:XAUUSD"
        elif asset_from_log.upper() == "EURUSD":
            asset_to_display = "OANDA:EURUSD"
        elif asset_from_log:
            asset_to_display = asset_from_log.upper()
        st.info(f"แสดงกราฟ TradingView สำหรับ: {asset_to_display} (จาก Log Viewer)")
    else:
        st.info(f"แสดงกราฟ TradingView สำหรับ: {asset_to_display} (จาก Input ปัจจุบัน)")

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
    df_ai_logs = pd.DataFrame()
    gc_ai = get_gspread_client()
    if gc_ai:
        try:
            sh_ai = gc_ai.open(GOOGLE_SHEET_NAME)
            ws_ai_logs = sh_ai.worksheet(WORKSHEET_PLANNED_LOGS)
            records_ai = ws_ai_logs.get_all_records()
            if records_ai:
                df_ai_logs = pd.DataFrame(records_ai)
                if 'Risk $' in df_ai_logs.columns:
                    df_ai_logs['Risk $'] = pd.to_numeric(df_ai_logs['Risk $'], errors='coerce').fillna(0)
                if 'RR' in df_ai_logs.columns:
                    df_ai_logs['RR'] = pd.to_numeric(df_ai_logs['RR'], errors='coerce')
                if 'Timestamp' in df_ai_logs.columns:
                    df_ai_logs['Timestamp'] = pd.to_datetime(df_ai_logs['Timestamp'], errors='coerce')
        except Exception as e:
            pass
            
    if df_ai_logs.empty:
        st.info("ยังไม่มีข้อมูลแผนเทรดใน Log (Google Sheets) สำหรับ AI Assistant")
    else:
        total_trades_ai = df_ai_logs.shape[0]
        win_trades_ai = df_ai_logs[df_ai_logs["Risk $"] > 0].shape[0] if "Risk $" in df_ai_logs.columns else 0
        winrate_ai = (100 * win_trades_ai / total_trades_ai) if total_trades_ai > 0 else 0
        gross_profit_ai = df_ai_logs["Risk $"].sum() if "Risk $" in df_ai_logs.columns else 0
        
        avg_rr_ai = df_ai_logs["RR"].mean() if "RR" in df_ai_logs.columns and not df_ai_logs["RR"].dropna().empty else None

        max_drawdown_ai = 0
        if "Risk $" in df_ai_logs.columns:
            df_ai_logs_sorted = df_ai_logs.sort_values(by="Timestamp") if "Timestamp" in df_ai_logs.columns else df_ai_logs
            current_balance_sim = acc_balance
            peak_balance_sim = acc_balance
            for pnl_val in df_ai_logs_sorted["Risk $"]:
                current_balance_sim += pnl_val
                if current_balance_sim > peak_balance_sim:
                    peak_balance_sim = current_balance_sim
                drawdown_val = peak_balance_sim - current_balance_sim
                if drawdown_val > max_drawdown_ai:
                    max_drawdown_ai = drawdown_val
        
        win_day_ai = "-"
        loss_day_ai = "-"
        if "Timestamp" in df_ai_logs.columns and "Risk $" in df_ai_logs.columns and not df_ai_logs["Timestamp"].isnull().all():
            df_ai_logs["Weekday"] = df_ai_logs["Timestamp"].dt.day_name()
            daily_pnl = df_ai_logs.groupby("Weekday")["Risk $"].sum()
            if not daily_pnl.empty:
                win_day_ai = daily_pnl.idxmax() if daily_pnl.max() > 0 else "-"
                loss_day_ai = daily_pnl.idxmin() if daily_pnl.min() < 0 else "-"

        st.markdown("### 🧠 AI Intelligence Report (จากข้อมูลแผนเทรด)")
        st.write(f"- **จำนวนแผนเทรดทั้งหมด:** {total_trades_ai:,}")
        st.write(f"- **Winrate (ตามแผน):** {winrate_ai:.2f}% (คำนวณจาก Risk $ > 0)")
        st.write(f"- **กำไร/ขาดทุนสุทธิ (ตามแผน):** {gross_profit_ai:,.2f} USD")
        if avg_rr_ai is not None:
            st.write(f"- **RR เฉลี่ย (ตามแผน):** {avg_rr_ai:.2f}")
        st.write(f"- **Max Drawdown (จำลองจากแผน):** {max_drawdown_ai:,.2f} USD")
        st.write(f"- **วันที่ทำกำไรดีที่สุด (ตามแผน):** {win_day_ai}")
        st.write(f"- **วันที่ขาดทุนมากที่สุด (ตามแผน):** {loss_day_ai}")

        st.markdown("### 🤖 AI Insight (จากกฎที่คุณกำหนดเอง)")
        insight_messages = []
        if winrate_ai >= 60:
            insight_messages.append("✅ Winrate (ตามแผน) สูง: ระบบการวางแผนมีแนวโน้มที่ดี")
        elif winrate_ai < 40 and total_trades_ai > 10 :
            insight_messages.append("⚠️ Winrate (ตามแผน) ต่ำ: ควรทบทวนกลยุทธ์การวางแผน")
        
        if avg_rr_ai is not None and avg_rr_ai < 1.5 and total_trades_ai > 5:
            insight_messages.append("📉 RR เฉลี่ย (ตามแผน) ต่ำกว่า 1.5: อาจต้องพิจารณาการตั้ง TP/SL เพื่อ Risk:Reward ที่เหมาะสมขึ้น")
        
        if max_drawdown_ai > acc_balance * 0.10:
            insight_messages.append("🚨 Max Drawdown (จำลองจากแผน) ค่อนข้างสูง: ควรระมัดระวังการบริหารความเสี่ยง")
        
        if not insight_messages:
            insight_messages = ["ดูเหมือนว่าข้อมูลแผนเทรดปัจจุบันยังไม่มีจุดที่น่ากังวลเป็นพิเศษตามเกณฑ์ที่ตั้งไว้"]
        
        for msg in insight_messages:
            if "✅" in msg: st.success(msg)
            elif "⚠️" in msg or "📉" in msg: st.warning(msg)
            elif "🚨" in msg: st.error(msg)
            else: st.info(msg)

# ===================== SEC 7: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
with st.expander("📂 SEC 7: Ultimate Chart Dashboard Import & Processing", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # --- ฟังก์ชันสำหรับแยกข้อมูลจากเนื้อหาไฟล์ Statement (CSV) ---
    def extract_data_from_report_content(file_content_str_input): # Changed param name for clarity
        extracted_data = {}

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
            return extracted_data

        # Define raw headers and expected cleaned column names for table sections
        # These are crucial for identifying and parsing the tabular data.
        section_raw_headers = {
            "Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit",
            "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment",
            "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment",
        }
        
        # Using unique column names for each expected table to avoid conflicts if DataFrames are merged later
        # or if keys are used in a flat structure.
        expected_cleaned_columns = {
            "Positions": ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos"],
            "Orders": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Comment_Ord"], # Assuming 11 relevant columns based on typical MT reports
            "Deals": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal"],
        }
        
        section_order_for_tables = ["Positions", "Orders", "Deals"]
        section_header_indices = {} # Stores index of the header line for each section
        
        # 1. Find header lines for all table sections
        for line_idx, current_line_str in enumerate(lines):
            stripped_line = current_line_str.strip()
            for section_name, raw_header_template in section_raw_headers.items():
                if section_name not in section_header_indices: # Only find once
                    # A simple check: if the line starts with the first part of the template
                    # AND the template is a substring of the line.
                    first_col_of_template = raw_header_template.split(',')[0].strip()
                    if stripped_line.startswith(first_col_of_template) and raw_header_template in stripped_line:
                        section_header_indices[section_name] = line_idx
                        break # Found header for this section_name, move to next section_name

        # 2. Parse each table section
        for table_idx, section_name in enumerate(section_order_for_tables):
            section_key_lower = section_name.lower()
            extracted_data[section_key_lower] = pd.DataFrame() # Initialize with empty DataFrame

            if section_name in section_header_indices:
                header_line_num = section_header_indices[section_name]
                data_start_line_num = header_line_num + 1
                
                # Determine where data for current table ends
                data_end_line_num = len(lines)
                for next_table_name_idx in range(table_idx + 1, len(section_order_for_tables)):
                    next_table_section_name = section_order_for_tables[next_table_name_idx]
                    if next_table_section_name in section_header_indices:
                        data_end_line_num = section_header_indices[next_table_section_name]
                        break # Found start of next table, so current table data ends before it
                
                current_table_data_lines = []
                for line_num_for_data in range(data_start_line_num, data_end_line_num):
                    line_content_for_data = lines[line_num_for_data].strip()
                    if not line_content_for_data: # Blank line often signifies end of data block or gap
                        if any(current_table_data_lines): # If we already have some data, assume blank line is end
                            break
                        else:
                            continue # Skip leading blank lines after header

                    # Heuristic: If line starts looking like a summary or a different section header, stop.
                    if line_content_for_data.startswith(("Balance:", "Credit Facility:", "Floating P/L:", "Equity:", "Results", "Total Net Profit:")):
                        break
                    # Check if it's a header of another known table section
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
                                                 header=None, # Data does not contain header row
                                                 names=expected_cleaned_columns[section_name],
                                                 skipinitialspace=True,
                                                 on_bad_lines='warn', # or 'skip'
                                                 engine='python')
                        
                        # Data Cleaning for the DataFrame
                        df_section.dropna(how='all', inplace=True) # Drop rows that are all NaN
                        # df_section = df_section.loc[:, ~df_section.columns.str.contains('^Unnamed')] # Remove unnamed columns if pandas adds them

                        # Ensure all expected columns are present, fill with NaN if missing, and reorder
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
                            st.text(f"Problematic CSV data for {section_name}:\n{csv_data_str[:500]}") # Show first 500 chars

        # --- Extract Balance Summary (Equity, Free Margin, etc.) ---
        balance_summary_dict = {}
        balance_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Balance:"):
                balance_start_line_idx = i
                break

        if balance_start_line_idx != -1:
            for i in range(balance_start_line_idx, min(balance_start_line_idx + 5, len(lines))):
                line_stripped = lines[i].strip()
                if not line_stripped : continue # Skip truly empty lines
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

        # --- Extract Results Summary (Total Net Profit, Profit Factor, etc.) ---
        results_summary_dict = {}
        stat_definitions_map = { # Renamed from stat_definitions for clarity
            "Total Net Profit": "Total_Net_Profit", "Gross Profit": "Gross_Profit", "Gross Loss": "Gross_Loss",
            "Profit Factor": "Profit_Factor", "Expected Payoff": "Expected_Payoff",
            "Recovery Factor": "Recovery_Factor", "Sharpe Ratio": "Sharpe_Ratio",
            "Balance Drawdown Absolute": "Balance_Drawdown_Absolute",
            "Balance Drawdown Maximal": "Balance_Drawdown_Maximal",
            "Balance Drawdown Relative": "Balance_Drawdown_Relative_Percent", # This key from CSV is %
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
        max_lines_for_results = 25 # Safety limit for processing results section

        for i_res, line_res in enumerate(lines):
            if results_start_line_idx == -1 and (line_res.strip().startswith("Results") or line_res.strip().startswith("Total Net Profit:")):
                results_start_line_idx = i_res
                continue # Move to next line to start processing data

            if results_start_line_idx != -1 and results_section_processed_lines < max_lines_for_results:
                line_stripped_res = line_res.strip()
                if not line_stripped_res: # If blank line after results started, might be end
                    if results_section_processed_lines > 2: # Ensure we've processed some lines
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
                        
                        # Find value for this label in subsequent cells
                        for k_val_search in range(1, 5): # Look in next few cells
                            if (c_idx + k_val_search) < len(row_cells):
                                raw_value_from_cell = row_cells[c_idx + k_val_search]
                                if raw_value_from_cell: # If cell has content
                                    value_part_before_paren = raw_value_from_cell.split('(')[0].strip()
                                    numeric_value = safe_float_convert(value_part_before_paren)

                                    if numeric_value is not None:
                                        results_summary_dict[gsheet_key] = numeric_value
                                        
                                        # Handle composite values in parentheses
                                        if '(' in raw_value_from_cell and ')' in raw_value_from_cell:
                                            try:
                                                paren_content_str = raw_value_from_cell[raw_value_from_cell.find('(')+1:raw_value_from_cell.find(')')].strip().replace('%','')
                                                paren_numeric_value = safe_float_convert(paren_content_str)
                                                if paren_numeric_value is not None:
                                                    # Assign to specific _Percent, _Count, or _Amount keys
                                                    if current_label == "Balance Drawdown Maximal": results_summary_dict["Balance_Drawdown_Maximal_Percent"] = paren_numeric_value
                                                    elif current_label == "Balance Drawdown Relative": results_summary_dict["Balance_Drawdown_Relative_Amount"] = paren_numeric_value # Amount for Relative DD
                                                    elif current_label == "Short Trades (won %)": results_summary_dict["Short_Trades_won_Percent"] = paren_numeric_value
                                                    elif current_label == "Long Trades (won %)": results_summary_dict["Long_Trades_won_Percent"] = paren_numeric_value
                                                    elif current_label == "Profit Trades (% of total)": results_summary_dict["Profit_Trades_Percent_of_total"] = paren_numeric_value
                                                    elif current_label == "Loss Trades (% of total)": results_summary_dict["Loss_Trades_Percent_of_total"] = paren_numeric_value
                                                    elif current_label == "Maximum consecutive wins ($)": results_summary_dict["Maximum_consecutive_wins_Profit"] = paren_numeric_value
                                                    elif current_label == "Maximal consecutive profit (count)": results_summary_dict["Maximal_consecutive_profit_Count"] = paren_numeric_value
                                                    elif current_label == "Maximum consecutive losses ($)": results_summary_dict["Maximum_consecutive_losses_Profit"] = paren_numeric_value
                                                    elif current_label == "Maximal consecutive loss (count)": results_summary_dict["Maximal_consecutive_loss_Count"] = paren_numeric_value
                                            except Exception: pass # Ignore if parenthesis parsing fails
                                        break # Value found for current_label, break from k_val_search loop
                
                if line_stripped_res.startswith("Average consecutive losses"): # Known last line of results
                    break
            elif results_start_line_idx != -1 and results_section_processed_lines >= max_lines_for_results:
                break # Reached safety limit for lines in results section

        extracted_data['balance_summary'] = balance_summary_dict
        extracted_data['results_summary'] = results_summary_dict
        
        if st.session_state.get("debug_statement_processing_v2", False):
            st.subheader("DEBUG: Final Parsed Summaries (after extract_data_from_report_content)")
            st.write("Balance Summary (Equity, Free Margin, etc.):")
            st.json(balance_summary_dict if balance_summary_dict else "Balance summary not parsed or empty.")
            st.write("Results Summary (Profit Factor, Trades, etc.):")
            st.json(results_summary_dict if results_summary_dict else "Results summary not parsed or empty.")

        return extracted_data

    # --- ฟังก์ชันสำหรับบันทึก Deals ลงในชีท ActualTrades ---
    def save_deals_to_actual_trades(sh, df_deals, portfolio_id, portfolio_name, source_file_name="N/A"):
        if df_deals is None or df_deals.empty:
            st.warning("No Deals data to save.")
            return False
        try:
            ws = sh.worksheet(WORKSHEET_ACTUAL_TRADES)
            expected_headers = [
                "Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal",
                "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal",
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.update([expected_headers]) # Use update for single row

            # Ensure df_deals has columns matching expected_headers before converting to list
            rows_to_append = []
            df_deals_to_save = pd.DataFrame(columns=expected_headers)
            for col in expected_headers:
                if col in df_deals.columns:
                    df_deals_to_save[col] = df_deals[col]
                elif col not in ["PortfolioID", "PortfolioName", "SourceFile"]: # System-added columns
                     df_deals_to_save[col] = None # Fill missing expected columns with None

            df_deals_to_save["PortfolioID"] = portfolio_id
            df_deals_to_save["PortfolioName"] = portfolio_name
            df_deals_to_save["SourceFile"] = source_file_name
            
            # Convert all data to string to avoid gspread type issues
            list_of_lists = df_deals_to_save.astype(str).values.tolist()
            if list_of_lists:
                 ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
                 return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_TRADES}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Deals: {e}"); return False

    # --- ฟังก์ชันสำหรับบันทึก Positions ลงในชีท ActualPositions ---
    def save_positions_to_gsheets(sh, df_positions, portfolio_id, portfolio_name, source_file_name="N/A"):
        if df_positions is None or df_positions.empty:
            st.warning("No Positions data to save.")
            return False
        try:
            ws = sh.worksheet(WORKSHEET_ACTUAL_POSITIONS)
            expected_headers = [
                "Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P",
                "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos",
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.update([expected_headers])

            df_positions_to_save = pd.DataFrame(columns=expected_headers)
            for col in expected_headers:
                if col in df_positions.columns:
                    df_positions_to_save[col] = df_positions[col]
                elif col not in ["PortfolioID", "PortfolioName", "SourceFile"]:
                     df_positions_to_save[col] = None

            df_positions_to_save["PortfolioID"] = portfolio_id
            df_positions_to_save["PortfolioName"] = portfolio_name
            df_positions_to_save["SourceFile"] = source_file_name
            
            list_of_lists = df_positions_to_save.astype(str).values.tolist()
            if list_of_lists:
                ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
                return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_POSITIONS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Positions: {e}"); return False

    # --- ฟังก์ชันสำหรับบันทึก Orders ลงในชีท ActualOrders ---
    def save_orders_to_gsheets(sh, df_orders, portfolio_id, portfolio_name, source_file_name="N/A"):
        if df_orders is None or df_orders.empty:
            st.warning("No Orders data to save.")
            return False
        try:
            ws = sh.worksheet(WORKSHEET_ACTUAL_ORDERS)
            expected_headers = [
                "Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord",
                "Close_Time_Ord", "State_Ord", "Comment_Ord",
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.update([expected_headers])

            df_orders_to_save = pd.DataFrame(columns=expected_headers)
            for col in expected_headers:
                if col in df_orders.columns:
                    df_orders_to_save[col] = df_orders[col]
                elif col not in ["PortfolioID", "PortfolioName", "SourceFile"]:
                     df_orders_to_save[col] = None
            
            df_orders_to_save["PortfolioID"] = portfolio_id
            df_orders_to_save["PortfolioName"] = portfolio_name
            df_orders_to_save["SourceFile"] = source_file_name

            list_of_lists = df_orders_to_save.astype(str).values.tolist()
            if list_of_lists:
                ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
                return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_ORDERS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Orders: {e}"); return False
        
    # --- ฟังก์ชันสำหรับบันทึก Results Summary ลงในชีท StatementSummaries ---
    def save_results_summary_to_gsheets(sh, balance_summary_data, results_summary_data, portfolio_id, portfolio_name, source_file_name="N/A"):
        try:
            ws = sh.worksheet(WORKSHEET_STATEMENT_SUMMARIES)
            expected_headers = [
                "Timestamp", "PortfolioID", "PortfolioName", "SourceFile", 
                "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", # From balance_summary
                "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", 
                "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", 
                "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", 
                "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", # Added _Amount for relative
                "Total_Trades", 
                "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", 
                "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", 
                "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", 
                "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", 
                "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit",
                "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count",
                "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count",
                "Average_consecutive_wins", "Average_consecutive_losses"
            ]
            
            current_headers_ws = []
            if ws.row_count > 0: current_headers_ws = ws.row_values(1)
            if not current_headers_ws or all(h == "" for h in current_headers_ws): ws.update([expected_headers])

            row_data_to_save = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "PortfolioID": str(portfolio_id), # Ensure string
                "PortfolioName": str(portfolio_name),
                "SourceFile": str(source_file_name)
            }
            
            # Populate from balance_summary_data
            if isinstance(balance_summary_data, dict):
                for key, value in balance_summary_data.items():
                    # Map cleaned keys from balance_summary_dict to expected_headers
                    if key == "balance": row_data_to_save["Balance"] = value
                    elif key == "equity": row_data_to_save["Equity"] = value
                    elif key == "free_margin": row_data_to_save["Free_Margin"] = value
                    elif key == "margin": row_data_to_save["Margin"] = value
                    elif key == "floating_p_l": row_data_to_save["Floating_P_L"] = value
                    elif key == "margin_level": row_data_to_save["Margin_Level"] = value
                    # Add other mappings if balance_summary_dict produces more keys needed in this sheet

            # Populate from results_summary_data
            if isinstance(results_summary_data, dict):
                for gsheet_key, val_res in results_summary_data.items():
                    if gsheet_key in expected_headers: # Only add if it's an expected header
                        row_data_to_save[gsheet_key] = val_res
            
            final_row_values = [str(row_data_to_save.get(h, "")) for h in expected_headers] # Default to empty string if key not found
            
            ws.append_rows([final_row_values], value_input_option='USER_ENTERED')
            return True
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_STATEMENT_SUMMARIES}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Statement Summaries: {e}")
            st.exception(e)
            return False

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement Report (CSV) เพื่อประมวลผลและบันทึก")
    
    uploaded_file_statement = st.file_uploader( 
        "ลากและวางไฟล์ Statement Report (CSV) ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["csv"],
        key="full_stmt_uploader_final_v3" # Changed key to avoid conflict
    )

    st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้)", value=False, key="debug_statement_processing_v2") # Default to False
    
    active_portfolio_id_for_actual = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_for_actual = st.session_state.get('active_portfolio_name_gs', None)

    if uploaded_file_statement:
        file_name_for_saving = uploaded_file_statement.name
        
        try:
            file_content_bytes = uploaded_file_statement.getvalue()
            file_content_str = file_content_bytes.decode("utf-8")
        except Exception as e_decode:
            st.error(f"เกิดข้อผิดพลาดในการอ่านหรือ decode ไฟล์: {e_decode}")
            # st.stop() # Stop further execution for this upload if file can't be read
            extracted_sections = {} # Ensure extracted_sections is defined to avoid NameError
        else: # Only proceed if file decoding was successful
            if st.session_state.get("debug_statement_processing_v2", False):
                st.subheader("Raw File Content (Debug)")
                st.text_area("File Content", file_content_str, height=200, key="raw_file_content_debug_area")

            st.info(f"กำลังประมวลผลไฟล์: {uploaded_file_statement.name}")
            with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {uploaded_file_statement.name}..."):
                # Call the main extraction function
                extracted_sections = extract_data_from_report_content(file_content_str) 
            
            if st.session_state.get("debug_statement_processing_v2", False):
                st.subheader("📄 ข้อมูลที่แยกได้ (Debug)")
                if extracted_sections:
                    for section_name, data_item in extracted_sections.items():
                        st.write(f"#### {section_name.replace('_',' ').title()}")
                        if isinstance(data_item, pd.DataFrame):
                            if not data_item.empty:
                                st.dataframe(data_item.head()) # Show head for brevity
                            else:
                                st.info(f"DataFrame for {section_name.replace('_',' ').title()} is empty.")
                        elif isinstance(data_item, dict):
                            st.json(data_item if data_item else f"Dictionary for {section_name} is empty.")
                        else:
                            st.write(data_item if data_item is not None else f"Data for {section_name} is None.")
                else:
                    st.warning("ไม่สามารถแยกส่วนข้อมูลใดๆ ได้จากไฟล์")

            if not active_portfolio_id_for_actual:
                st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.")
            elif not extracted_sections:
                 st.error("ไม่สามารถประมวลผลข้อมูลจากไฟล์ Statement ได้ กรุณาตรวจสอบไฟล์หรือโหมด Debug")
            else:
                st.markdown("---")
                st.subheader("💾 กำลังบันทึกข้อมูลไปยัง Google Sheets...")
                
                gc_for_save = get_gspread_client()
                if gc_for_save:
                    save_successful_flags = {}
                    try:
                        sh_for_save = gc_for_save.open(GOOGLE_SHEET_NAME)
                        
                        deals_df = extracted_sections.get('deals')
                        if deals_df is not None and not deals_df.empty:
                            if save_deals_to_actual_trades(sh_for_save, deals_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                                st.success(f"บันทึก Deals ({len(deals_df)} รายการ) สำเร็จ!")
                                save_successful_flags['deals'] = True
                            else: st.error("บันทึก Deals ไม่สำเร็จ.")
                        else: st.warning("ไม่พบข้อมูล Deals ใน Statement หรือไม่สามารถประมวลผลได้.")

                        orders_df = extracted_sections.get('orders')
                        if orders_df is not None and not orders_df.empty:
                            if save_orders_to_gsheets(sh_for_save, orders_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                                st.success(f"บันทึก Orders ({len(orders_df)} รายการ) สำเร็จ!")
                                save_successful_flags['orders'] = True
                            else: st.error("บันทึก Orders ไม่สำเร็จ.")
                        else: st.warning("ไม่พบข้อมูล Orders ใน Statement หรือไม่สามารถประมวลผลได้.")
                        
                        positions_df = extracted_sections.get('positions')
                        if positions_df is not None and not positions_df.empty:
                            if save_positions_to_gsheets(sh_for_save, positions_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                                st.success(f"บันทึก Positions ({len(positions_df)} รายการ) สำเร็จ!")
                                save_successful_flags['positions'] = True
                            else: st.error("บันทึก Positions ไม่สำเร็จ.")
                        else: st.warning("ไม่พบข้อมูล Positions ใน Statement หรือไม่สามารถประมวลผลได้.")

                        balance_summary_data = extracted_sections.get('balance_summary', {}) # Default to empty dict
                        results_summary_data = extracted_sections.get('results_summary', {}) # Default to empty dict

                        if balance_summary_data or results_summary_data:
                            if save_results_summary_to_gsheets(sh_for_save, balance_summary_data, results_summary_data, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                                st.success("บันทึก Summary Data (Balance & Results) สำเร็จ!")
                                save_successful_flags['summary'] = True
                            else: st.error("บันทึก Summary Data ไม่สำเร็จ.")
                        else: st.warning("ไม่พบข้อมูล Summary (Balance หรือ Results) ใน Statement.")
                        
                        if any(save_successful_flags.values()):
                            st.balloons()

                    except Exception as e_save_all:
                        st.error(f"❌ เกิดข้อผิดพลาดในการเข้าถึง Google Sheet หรือระหว่างการบันทึก: {e_save_all}")
                        st.exception(e_save_all)
                else:
                    st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกข้อมูลได้.")
    else:
        st.info("โปรดอัปโหลดไฟล์ Statement Report (CSV) เพื่อเริ่มต้นประมวลผล.")

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
