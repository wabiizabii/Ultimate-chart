# 31:5:21:36main.py

# ===================== SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime, date  # เพิ่ม date สำหรับ date_input
import plotly.express as px
import google.generativeai as genai  # ถ้ายังใช้อยู่
import gspread
import plotly.graph_objects as go
import random
import io
import uuid  # <<< เพิ่ม import uuid

st.set_page_config(page_title="Ultimate-Chart", layout="wide")
acc_balance = 10000  # ยอดคงเหลือเริ่มต้นของบัญชีเทรด (อาจจะดึงมาจาก Active Portfolio ในอนาคต)

# กำหนดชื่อ Google Sheet และ Worksheet ที่จะใช้เก็บข้อมูล
GOOGLE_SHEET_NAME = "TradeLog"  # ชื่อ Google Sheet ของลูกพี่ตั้ม
WORKSHEET_PORTFOLIOS = "Portfolios"
WORKSHEET_PLANNED_LOGS = "PlannedTradeLogs"
WORKSHEET_ACTUAL_TRADES = "ActualTrades"
WORKSHEET_ACTUAL_ORDERS = "ActualOrders"
WORKSHEET_ACTUAL_POSITIONS = "ActualPositions"
WORKSHEET_STATEMENT_SUMMARIES = "StatementSummaries"

# ฟังก์ชันสำหรับเชื่อมต่อ gspread
@st.cache_resource  # ใช้ cache_resource สำหรับ gspread client object
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
@st.cache_data(ttl=300)  # Cache ข้อมูลไว้ 5 นาที
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

        if 'EnableScaling' in df_portfolios.columns:  # คอลัมน์นี้ควรเป็น Boolean
            df_portfolios['EnableScaling'] = df_portfolios['EnableScaling'].astype(str).str.upper().map(
                {'TRUE': True, 'YES': True, '1': True, 'FALSE': False, 'NO': False, '0': False}
            ).fillna(False)

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
df_portfolios_gs = load_portfolios_from_gsheets()  # โหลดข้อมูลพอร์ตก่อนส่วน UI อื่นๆ

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

# Initialize session state variables for portfolio selection
if 'active_portfolio_name_gs' not in st.session_state:
    st.session_state.active_portfolio_name_gs = ""
if 'active_portfolio_id_gs' not in st.session_state:
    st.session_state.active_portfolio_id_gs = None
if 'current_portfolio_details' not in st.session_state:  # เพิ่มเพื่อเก็บรายละเอียดพอร์ตที่เลือก
    st.session_state.current_portfolio_details = None

portfolio_names_list_gs = [""]  # Start with an empty option
if not df_portfolios_gs.empty and 'PortfolioName' in df_portfolios_gs.columns:
    valid_portfolio_names = sorted(df_portfolios_gs['PortfolioName'].dropna().unique().tolist())
    portfolio_names_list_gs.extend(valid_portfolio_names)

if st.session_state.active_portfolio_name_gs not in portfolio_names_list_gs:
    st.session_state.active_portfolio_name_gs = portfolio_names_list_gs[0]

selected_portfolio_name_gs = st.sidebar.selectbox(
    "เลือกพอร์ต:",
    options=portfolio_names_list_gs,
    index=portfolio_names_list_gs.index(st.session_state.active_portfolio_name_gs),
    key='sb_active_portfolio_selector_gs'
)

if selected_portfolio_name_gs != "":
    st.session_state.active_portfolio_name_gs = selected_portfolio_name_gs
    if not df_portfolios_gs.empty:
        selected_portfolio_row_df = df_portfolios_gs[df_portfolios_gs['PortfolioName'] == selected_portfolio_name_gs]
        if not selected_portfolio_row_df.empty:
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

if st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details
    st.sidebar.markdown(f"**💡 ข้อมูลพอร์ต '{details.get('PortfolioName', 'N/A')}'**")
    if pd.notna(details.get('InitialBalance')):
        st.sidebar.write(f"- Balance เริ่มต้น: {details['InitialBalance']:,.2f} USD")
    if pd.notna(details.get('ProgramType')):
        st.sidebar.write(f"- ประเภท: {details['ProgramType']}")
    if pd.notna(details.get('Status')):
        st.sidebar.write(f"- สถานะ: {details['Status']}")
    if details.get('ProgramType') in ["Prop Firm Challenge", "Funded Account", "Trading Competition"]:
        if pd.notna(details.get('ProfitTargetPercent')):
            st.sidebar.write(f"- เป้าหมายกำไร: {details['ProfitTargetPercent']:.1f}%")
        if pd.notna(details.get('DailyLossLimitPercent')):
            st.sidebar.write(f"- Daily Loss Limit: {details['DailyLossLimitPercent']:.1f}%")
        if pd.notna(details.get('TotalStopoutPercent')):
            st.sidebar.write(f"- Total Stopout: {details['TotalStopoutPercent']:.1f}%")
elif not df_portfolios_gs.empty and selected_portfolio_name_gs == "":
    st.sidebar.info("กรุณาเลือกพอร์ตที่ใช้งานจากรายการ")
elif df_portfolios_gs.empty:
    st.sidebar.warning("ไม่พบข้อมูล Portfolio ใน Google Sheets หรือเกิดข้อผิดพลาดในการโหลด.")

# ========== Function Utility (ต่อจากของเดิม) ==========
def get_today_drawdown(log_source_df, acc_balance_input):
    if log_source_df.empty:
        return 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)
        df_today = log_source_df[log_source_df["Timestamp"].dt.strftime("%Y-%m-%d") == today_str]
        drawdown = df_today["Risk $"].sum()
        return drawdown
    except KeyError:
        return 0
    except Exception:
        return 0


def get_performance(log_source_df, mode="week"):
    if log_source_df.empty:
        return 0, 0, 0
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
    except KeyError:
        return 0, 0, 0
    except Exception:
        return 0, 0, 0


def save_plan_to_gsheets(plan_data_list, trade_mode_arg, asset_name, risk_percentage, trade_direction,
                          portfolio_id, portfolio_name):
    gc = get_gspread_client()
    if not gc:
        st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกแผนได้")
        return False
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        timestamp_now = datetime.now()
        rows_to_append = []
        expected_headers_plan = [
            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",
            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"
        ]
        current_headers_plan = []
        if ws.row_count > 0:
            try:
                current_headers_plan = ws.row_values(1)
            except Exception:
                current_headers_plan = []

        if not current_headers_plan or all(h == "" for h in current_headers_plan):
            ws.update([expected_headers_plan])
        elif set(current_headers_plan) != set(expected_headers_plan) and any(h != "" for h in current_headers_plan):
            st.warning(f"Worksheet '{WORKSHEET_PLANNED_LOGS}' has incorrect headers. "
                       f"Please ensure headers match: {', '.join(expected_headers_plan)}")

        for idx, plan_entry in enumerate(plan_data_list):
            log_id = f"{timestamp_now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}-{idx}"
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

        expected_gsheet_headers_portfolio = [
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

        current_sheet_headers = []
        if ws.row_count > 0:
            try:
                current_sheet_headers = ws.row_values(1)
            except Exception:
                pass

        if not current_sheet_headers or all(h == "" for h in current_sheet_headers):
            ws.update([expected_gsheet_headers_portfolio])

        new_row_values = [str(portfolio_data_dict.get(header, "")) for header in expected_gsheet_headers_portfolio]
        ws.append_row(new_row_values, value_input_option='USER_ENTERED')
        return True
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}'. กรุณาสร้างชีตนี้ก่อน และใส่ Headers ให้ถูกต้อง")
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกพอร์ตใหม่ไปยัง Google Sheets: {e}")
        st.exception(e)
        return False
# +++ END: โค้ดใหม่สำหรับฟังก์ชัน save_new_portfolio_to_gsheets +++


# ===================== SEC 1.5: PORTFOLIO MANAGEMENT UI (Main Area) =======================
def on_program_type_change_v8():
    st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8


with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=True):
    st.subheader("พอร์ตทั้งหมดของคุณ")
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

    program_type_options_outside = ["", "Personal Account", "Prop Firm Challenge", "Funded Account", "Trading Competition"]

    if 'exp_pf_type_select_v8_key' not in st.session_state:
        st.session_state.exp_pf_type_select_v8_key = ""

    def on_program_type_change_v8():
        st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8

    st.selectbox(
        "ประเภทพอร์ต (Program Type)*",
        options=program_type_options_outside,
        index=program_type_options_outside.index(st.session_state.exp_pf_type_select_v8_key),
        key="exp_pf_type_selector_widget_v8",
        on_change=on_program_type_change_v8
    )

    selected_program_type_to_use_in_form = st.session_state.exp_pf_type_select_v8_key

    st.write(f"**[DEBUG - นอก FORM, หลัง Selectbox] `selected_program_type_to_use_in_form` คือ:** `{selected_program_type_to_use_in_form}`")

    with st.form("new_portfolio_form_main_v8_final", clear_on_submit=True):
        st.markdown(f"**กรอกข้อมูลพอร์ต (สำหรับประเภท: {selected_program_type_to_use_in_form if selected_program_type_to_use_in_form else 'ยังไม่ได้เลือก'})**")

        form_c1_in_form, form_c2_in_form = st.columns(2)
        with form_c1_in_form:
            form_new_portfolio_name_in_form = st.text_input("ชื่อพอร์ต (Portfolio Name)*", key="form_pf_name_v8")
        with form_c2_in_form:
            form_new_initial_balance_in_form = st.number_input("บาลานซ์เริ่มต้น (Initial Balance)*", min_value=0.01,
                                                               value=10000.0, key="form_pf_balance_v8")

        form_status_options_in_form = ["Active", "Inactive", "Pending", "Passed", "Failed"]
        form_new_status_in_form = st.selectbox("สถานะพอร์ต (Status)*", options=form_status_options_in_form, index=0,
                                               key="form_pf_status_v8")

        form_new_evaluation_step_val_in_form = ""
        if selected_program_type_to_use_in_form == "Prop Firm Challenge":
            st.write(f"**[DEBUG - ใน FORM, ใน IF Evaluation Step] ประเภทคือ:** `{selected_program_type_to_use_in_form}`")
            evaluation_step_options_in_form = ["", "Phase 1", "Phase 2", "Phase 3", "Verification"]
            form_new_evaluation_step_val_in_form = st.selectbox("ขั้นตอนการประเมิน (Evaluation Step)",
                                                                options=evaluation_step_options_in_form, index=0,
                                                                key="form_pf_eval_step_select_v8")

        form_profit_target_val = 8.0
        form_daily_loss_val = 5.0
        form_total_stopout_val = 10.0
        form_leverage_val = 100.0
        form_min_days_val = 0
        form_comp_end_date = None
        form_comp_goal_metric = ""
        form_pers_overall_profit_val = 0.0
        form_pers_target_end_date = None
        form_pers_weekly_profit_val = 0.0
        form_pers_daily_profit_val = 0.0
        form_pers_max_dd_overall_val = 0.0
        form_pers_max_dd_daily_val = 0.0
        form_enable_scaling_checkbox_val = False
        form_scaling_freq_val = "Weekly"
        form_su_wr_val = 55.0
        form_su_gain_val = 2.0
        form_su_inc_val = 0.25
        form_sd_loss_val = -5.0
        form_sd_wr_val = 40.0
        form_sd_dec_val = 0.25
        form_min_risk_val = 0.25
        form_max_risk_val = 2.0
        form_current_risk_val = 1.0
        form_notes_val = ""

        if selected_program_type_to_use_in_form in ["Prop Firm Challenge", "Funded Account"]:
            st.markdown("**กฎเกณฑ์ Prop Firm/Funded:**")
            f_pf1, f_pf2, f_pf3 = st.columns(3)
            with f_pf1:
                form_profit_target_val = st.number_input("เป้าหมายกำไร %*", value=form_profit_target_val, format="%.1f",
                                                         key="f_pf_profit_v8")
            with f_pf2:
                form_daily_loss_val = st.number_input("จำกัดขาดทุนต่อวัน %*", value=form_daily_loss_val, format="%.1f",
                                                      key="f_pf_dd_v8")
            with f_pf3:
                form_total_stopout_val = st.number_input("จำกัดขาดทุนรวม %*", value=form_total_stopout_val,
                                                         format="%.1f", key="f_pf_maxdd_v8")
            f_pf_col1, f_pf_col2 = st.columns(2)
            with f_pf_col1:
                form_leverage_val = st.number_input("Leverage", value=form_leverage_val, format="%.0f", key="f_pf_lev_v8")
            with f_pf_col2:
                form_min_days_val = st.number_input("จำนวนวันเทรดขั้นต่ำ", value=form_min_days_val, step=1,
                                                    key="f_pf_mindays_v8")

        if selected_program_type_to_use_in_form == "Trading Competition":
            st.markdown("**ข้อมูลการแข่งขัน:**")
            f_tc1, f_tc2 = st.columns(2)
            with f_tc1:
                form_comp_end_date = st.date_input("วันสิ้นสุดการแข่งขัน", value=form_comp_end_date,
                                                   key="f_tc_enddate_v8")
                form_profit_target_val_comp = st.number_input("เป้าหมายกำไร % (Comp)", value=20.0, format="%.1f",
                                                              key="f_tc_profit_v8")
            with f_tc2:
                form_comp_goal_metric = st.text_input("ตัวชี้วัดเป้าหมาย (Comp)", value=form_comp_goal_metric,
                                                      help="เช่น %Gain, ROI", key="f_tc_goalmetric_v8")
                form_daily_loss_val_comp = st.number_input("จำกัดขาดทุนต่อวัน % (Comp)", value=5.0, format="%.1f",
                                                           key="f_tc_dd_v8")
                form_total_stopout_val_comp = st.number_input("จำกัดขาดทุนรวม % (Comp)", value=10.0, format="%.1f",
                                                              key="f_tc_maxdd_v8")

        if selected_program_type_to_use_in_form == "Personal Account":
            st.markdown("**เป้าหมายส่วนตัว (Optional):**")
            f_ps1, f_ps2 = st.columns(2)
            with f_ps1:
                form_pers_overall_profit_val = st.number_input("เป้าหมายกำไรโดยรวม ($)", value=form_pers_overall_profit_val,
                                                               format="%.2f", key="f_ps_profit_overall_v8")
                form_pers_weekly_profit_val = st.number_input("เป้าหมายกำไรรายสัปดาห์ ($)",
                                                              value=form_pers_weekly_profit_val, format="%.2f",
                                                              key="f_ps_profit_weekly_v8")
                form_pers_max_dd_overall_val = st.number_input("Max DD รวมที่ยอมรับได้ ($)",
                                                               value=form_pers_max_dd_overall_val, format="%.2f",
                                                               key="f_ps_dd_overall_v8")
            with f_ps2:
                form_pers_target_end_date = st.date_input("วันที่คาดว่าจะถึงเป้าหมายรวม",
                                                          value=form_pers_target_end_date, key="f_ps_enddate_v8")
                form_pers_daily_profit_val = st.number_input("เป้าหมายกำไรรายวัน ($)", value=form_pers_daily_profit_val,
                                                             format="%.2f", key="f_ps_profit_daily_v8")
                form_pers_max_dd_daily_val = st.number_input("Max DD ต่อวันที่ยอมรับได้ ($)",
                                                             value=form_pers_max_dd_daily_val, format="%.2f",
                                                             key="f_ps_dd_daily_v8")

        st.markdown("**การตั้งค่า Scaling Manager (Optional):**")
        form_enable_scaling_checkbox_val = st.checkbox("เปิดใช้งาน Scaling Manager?", value=form_enable_scaling_checkbox_val,
                                                      key="f_scale_enable_v8")
        if form_enable_scaling_checkbox_val:
            f_sc1, f_sc2, f_sc3 = st.columns(3)
            with f_sc1:
                form_scaling_freq_val = st.selectbox("ความถี่ตรวจสอบ Scaling", ["Weekly", "Monthly"],
                                                     index=["Weekly", "Monthly"].index(form_scaling_freq_val),
                                                     key="f_scale_freq_v8")
                form_su_wr_val = st.number_input("Scale Up: Min Winrate %", value=form_su_wr_val, format="%.1f",
                                                 key="f_scale_su_wr_v8")
                form_sd_loss_val = st.number_input("Scale Down: Max Loss %", value=form_sd_loss_val, format="%.1f",
                                                   key="f_scale_sd_loss_v8")
            with f_sc2:
                form_min_risk_val = st.number_input("Min Risk % Allowed", value=form_min_risk_val, format="%.2f",
                                                    key="f_scale_min_risk_v8")
                form_su_gain_val = st.number_input("Scale Up: Min Gain %", value=form_su_gain_val, format="%.1f",
                                                   key="f_scale_su_gain_v8")
                form_sd_wr_val = st.number_input("Scale Down: Low Winrate %", value=form_sd_wr_val, format="%.1f",
                                                 key="f_scale_sd_wr_v8")
            with f_sc3:
                form_max_risk_val = st.number_input("Max Risk % Allowed", value=form_max_risk_val, format="%.2f",
                                                    key="f_scale_max_risk_v8")
                form_su_inc_val = st.number_input("Scale Up: Risk Increment %", value=form_su_inc_val, format="%.2f",
                                                  key="f_scale_su_inc_v8")
                form_sd_dec_val = st.number_input("Scale Down: Risk Decrement %", value=form_sd_dec_val, format="%.2f",
                                                  key="f_scale_sd_dec_v8")
            form_current_risk_val = st.number_input("Current Risk % (สำหรับ Scaling)", value=form_current_risk_val,
                                                    format="%.2f", key="f_scale_current_risk_v8")

        form_notes_val = st.text_area("หมายเหตุเพิ่มเติม (Notes)", value=form_notes_val, key="f_pf_notes_v8")

        submitted_add_portfolio_in_form = st.form_submit_button("💾 บันทึกพอร์ตใหม่")

        if submitted_add_portfolio_in_form:
            if not form_new_portfolio_name_in_form or not selected_program_type_to_use_in_form or not form_new_status_in_form or form_new_initial_balance_in_form <= 0:
                st.warning("กรุณากรอกข้อมูลที่จำเป็น (*) ให้ครบถ้วนและถูกต้อง: ชื่อพอร์ต, ประเภทพอร์ต, สถานะพอร์ต, และยอดเงินเริ่มต้นต้องมากกว่า 0")
            elif 'df_portfolios_gs' in locals() and not df_portfolios_gs.empty and form_new_portfolio_name_in_form in df_portfolios_gs['PortfolioName'].astype(str).values:
                st.error(f"ชื่อพอร์ต '{form_new_portfolio_name_in_form}' มีอยู่แล้ว กรุณาใช้ชื่ออื่น")
            else:
                new_id_value = str(uuid.uuid4())

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
                    data_to_save['ProfitTargetPercent'] = form_profit_target_val_comp
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
                    for scale_key in ['ScalingCheckFrequency', 'ScaleUp_MinWinRate', 'ScaleUp_MinGainPercent',
                                      'ScaleUp_RiskIncrementPercent', 'ScaleDown_MaxLossPercent', 'ScaleDown_LowWinRate',
                                      'ScaleDown_RiskDecrementPercent', 'MinRiskPercentAllowed', 'MaxRiskPercentAllowed']:
                        data_to_save[scale_key] = None
                    data_to_save['CurrentRiskPercent'] = form_current_risk_val

                success_save = save_new_portfolio_to_gsheets(data_to_save)

                if success_save:
                    st.success(f"เพิ่มพอร์ต '{form_new_portfolio_name_in_form}' (ID: {new_id_value}) สำเร็จ!")
                    st.session_state.exp_pf_type_select_v8_key = ""
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

if st.sidebar.button("🔄 Reset Form"):
    mode_to_keep = st.session_state.get("mode", "FIBO")
    dd_limit_to_keep = st.session_state.get("drawdown_limit_pct", 2.0)
    active_portfolio_name_gs_keep = st.session_state.get('active_portfolio_name_gs', "")
    active_portfolio_id_gs_keep = st.session_state.get('active_portfolio_id_gs', None)
    current_portfolio_details_keep = st.session_state.get('current_portfolio_details', None)
    current_account_balance_keep = st.session_state.get('current_account_balance', 10000.0)
    exp_pf_type_select_v8_key_keep = st.session_state.get("exp_pf_type_select_v8_key", "")
    sb_active_portfolio_selector_gs_keep = st.session_state.get('sb_active_portfolio_selector_gs', "")

    keys_to_fully_preserve = {"gcp_service_account"}
    temp_preserved_values = {}
    for k_fp in keys_to_fully_preserve:
        if k_fp in st.session_state:
            temp_preserved_values[k_fp] = st.session_state[k_fp]

    for key in list(st.session_state.keys()):
        if key not in keys_to_fully_preserve:
            try:
                del st.session_state[key]
            except KeyError:
                pass
    for k_fp, v_fp in temp_preserved_values.items():
        st.session_state[k_fp] = v_fp

    st.session_state.mode = mode_to_keep
    st.session_state.drawdown_limit_pct = dd_limit_to_keep
    st.session_state.active_portfolio_name_gs = active_portfolio_name_gs_keep
    st.session_state.active_portfolio_id_gs = active_portfolio_id_gs_keep
    st.session_state.current_portfolio_details = current_portfolio_details_keep
    st.session_state.current_account_balance = current_account_balance_keep
    st.session_state.exp_pf_type_select_v8_key = exp_pf_type_select_v8_key_keep
    if sb_active_portfolio_selector_gs_keep:
        st.session_state.sb_active_portfolio_selector_gs = sb_active_portfolio_selector_gs_keep

    default_risk = 1.0
    if current_portfolio_details_keep:
        risk_val_str = current_portfolio_details_keep.get('CurrentRiskPercent')
        if pd.notna(risk_val_str) and str(risk_val_str).strip() != "":
            try:
                risk_val_float = float(risk_val_str)
                if risk_val_float > 0:
                    default_risk = risk_val_float
            except (ValueError, TypeError):
                pass

    st.session_state.risk_pct_fibo_val_v2 = default_risk
    st.session_state.asset_fibo_val_v2 = "XAUUSD"
    st.session_state.risk_pct_custom_val_v2 = default_risk
    st.session_state.asset_custom_val_v2 = "XAUUSD"
    st.session_state.swing_high_fibo_val_v2 = ""
    st.session_state.swing_low_fibo_val_v2 = ""
    st.session_state.fibo_flags_v2 = [False] * 5

    default_n_entries = 2
    st.session_state.n_entry_custom_val_v2 = default_n_entries
    for i in range(default_n_entries):
        st.session_state[f"custom_entry_{i}_v3"] = "0.00"
        st.session_state[f"custom_sl_{i}_v3"] = "0.00"
        st.session_state[f"custom_tp_{i}_v3"] = "0.00"
    if 'plot_data' in st.session_state:
        del st.session_state['plot_data']
    st.toast("รีเซ็ตฟอร์มเรียบร้อยแล้ว!", icon="🔄")
    st.rerun()

# ===================== SEC 2.2 & 2.3: INPUT ZONES (FIBO / CUSTOM) =======================
# --- ดึงค่า InitialBalance และ CurrentRiskPercent จาก Active Portfolio ---
active_balance_to_use = st.session_state.get('current_account_balance', 10000.0)

initial_risk_pct_from_portfolio = 1.0
if 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details
    current_risk_val_str = details.get('CurrentRiskPercent')
    if pd.notna(current_risk_val_str) and str(current_risk_val_str).strip() != "":
        try:
            risk_val_float = float(current_risk_val_str)
            if risk_val_float > 0:
                initial_risk_pct_from_portfolio = risk_val_float
        except (ValueError, TypeError):
            pass

# ===================== SEC 2.2: FIBO TRADE DETAILS =======================
if mode == "FIBO":
    col1_fibo_v2, col2_fibo_v2, col3_fibo_v2 = st.sidebar.columns([2, 2, 2])
    with col1_fibo_v2:
        asset_fibo_v2 = st.text_input("Asset",
                                      value=st.session_state.get("asset_fibo_val_v2", "XAUUSD"),
                                      key="asset_fibo_input_v3")
        st.session_state.asset_fibo_val_v2 = asset_fibo_v2
    with col2_fibo_v2:
        risk_pct_fibo_v2 = st.number_input(
            "Risk %",
            min_value=0.01, max_value=100.0,
            value=st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio),
            step=0.01, format="%.2f",
            key="risk_pct_fibo_input_v3")
        st.session_state.risk_pct_fibo_val_v2 = risk_pct_fibo_v2
    with col3_fibo_v2:
        default_direction_index = 0
        if "direction_fibo_val_v2" in st.session_state:
            if st.session_state.direction_fibo_val_v2 == "Short":
                default_direction_index = 1

        direction_fibo_v2 = st.radio("Direction", ["Long", "Short"],
                                     index=default_direction_index,
                                     horizontal=True, key="fibo_direction_radio_v3")
        st.session_state.direction_fibo_val_v2 = direction_fibo_v2

    col4_fibo_v2, col5_fibo_v2 = st.sidebar.columns(2)
    with col4_fibo_v2:
        swing_high_fibo_v2 = st.text_input("High",
                                           value=st.session_state.get("swing_high_fibo_val_v2", ""),
                                           key="swing_high_fibo_input_v3")
        st.session_state.swing_high_fibo_val_v2 = swing_high_fibo_v2
    with col5_fibo_v2:
        swing_low_fibo_v2 = st.text_input("Low",
                                          value=st.session_state.get("swing_low_fibo_val_v2", ""),
                                          key="swing_low_fibo_input_v3")
        st.session_state.swing_low_fibo_val_v2 = swing_low_fibo_v2

    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibos_fibo_v2 = [0.114, 0.25, 0.382, 0.5, 0.618]
    labels_fibo_v2 = [f"{l:.3f}" for l in fibos_fibo_v2]
    cols_fibo_v2 = st.sidebar.columns(len(fibos_fibo_v2))

    if "fibo_flags_v2" not in st.session_state:
        st.session_state.fibo_flags_v2 = [True] * len(fibos_fibo_v2)

    fibo_selected_flags_v2 = []
    for i, col_fibo_v2_loop in enumerate(cols_fibo_v2):
        checked_fibo_v2 = col_fibo_v2_loop.checkbox(labels_fibo_v2[i],
                                                     value=st.session_state.fibo_flags_v2[i],
                                                     key=f"fibo_cb_{i}_v3")
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

    if risk_pct_fibo_v2 <= 0:
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

    save_fibo = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo_v3")

# ===================== SEC 2.3: CUSTOM TRADE DETAILS =======================
elif mode == "CUSTOM":
    col1_custom_v2, col2_custom_v2, col3_custom_v2 = st.sidebar.columns([2, 2, 2])
    with col1_custom_v2:
        asset_custom_v2 = st.text_input("Asset",
                                        value=st.session_state.get("asset_custom_val_v2", "XAUUSD"),
                                        key="asset_custom_input_v3")
        st.session_state.asset_custom_val_v2 = asset_custom_v2
    with col2_custom_v2:
        risk_pct_custom_v2 = st.number_input(
            "Risk %",
            min_value=0.01, max_value=100.0,
            value=st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio),
            step=0.01, format="%.2f",
            key="risk_pct_custom_input_v3")
        st.session_state.risk_pct_custom_val_v2 = risk_pct_custom_v2
    with col3_custom_v2:
        n_entry_custom_v2 = st.number_input(
            "จำนวนไม้",
            min_value=1, max_value=10,
            value=st.session_state.get("n_entry_custom_val_v2", 2),
            step=1,
            key="n_entry_custom_input_v3")
        st.session_state.n_entry_custom_val_v2 = n_entry_custom_v2

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")
    custom_inputs_v2 = []

    current_custom_risk_pct_v2 = risk_pct_custom_v2
    risk_per_trade_custom_v2 = current_custom_risk_pct_v2 / 100
    risk_dollar_total_custom_v2 = active_balance_to_use * risk_per_trade_custom_v2
    num_entries_val_custom_v2 = n_entry_custom_v2
    risk_dollar_per_entry_custom_v2 = risk_dollar_total_custom_v2 / num_entries_val_custom_v2 if num_entries_val_custom_v2 > 0 else 0

    for i in range(int(num_entries_val_custom_v2)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e_v2, col_s_v2, col_t_v2 = st.sidebar.columns(3)
        entry_key_v2 = f"custom_entry_{i}_v3"
        sl_key_v2 = f"custom_sl_{i}_v3"
        tp_key_v2 = f"custom_tp_{i}_v3"

        if entry_key_v2 not in st.session_state:
            st.session_state[entry_key_v2] = "0.00"
        if sl_key_v2 not in st.session_state:
            st.session_state[sl_key_v2] = "0.00"
        if tp_key_v2 not in st.session_state:
            st.session_state[tp_key_v2] = "0.00"

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

    save_custom = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom_v3")

# ===================== SEC 3: SIDEBAR - CALCULATIONS, SUMMARY & ACTIONS =======================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")

# Initialize summary variables
summary_total_lots = 0.0
summary_total_risk_dollar = 0.0
summary_avg_rr = 0.0
summary_total_profit_at_primary_tp = 0.0
custom_tp_recommendation_messages = []

SPREAD_ADJUSTMENT_PRICE_UNITS = 0.20

entry_data_summary_sec3 = []
custom_entries_summary_sec3 = []

if mode == "FIBO":
    try:
        h_input_str_fibo = st.session_state.get("swing_high_fibo_val_v2", "")
        l_input_str_fibo = st.session_state.get("swing_low_fibo_val_v2", "")
        direction_fibo = st.session_state.get("direction_fibo_val_v2", "Long")
        risk_pct_fibo = st.session_state.get("risk_pct_fibo_val_v2", 1.0)

        fibos_fibo_v2 = [0.114, 0.25, 0.382, 0.5, 0.618]
        current_fibo_flags_fibo = st.session_state.get("fibo_flags_v2", [True] * len(fibos_fibo_v2))

        if not h_input_str_fibo or not l_input_str_fibo:
            st.sidebar.info("กรอก High และ Low (FIBO) เพื่อคำนวณ Summary")
        else:
            high_fibo_input = float(h_input_str_fibo)
            low_fibo_input = float(l_input_str_fibo)

            valid_hl_fibo = False
            fibo_0_percent_level_calc = 0.0
            fibo_100_percent_level_calc = 0.0

            if direction_fibo == "Long":
                if high_fibo_input > low_fibo_input:
                    fibo_0_percent_level_calc = low_fibo_input
                    fibo_100_percent_level_calc = high_fibo_input
                    valid_hl_fibo = True
                else:
                    st.sidebar.warning("Long: Swing High ที่กรอก ต้องมากกว่า Swing Low ที่กรอก!")
            else:  # Short
                if high_fibo_input > low_fibo_input:
                    fibo_0_percent_level_calc = high_fibo_input
                    fibo_100_percent_level_calc = low_fibo_input
                    valid_hl_fibo = True
                else:
                    st.sidebar.warning("Short: Swing High ที่กรอก ต้องมากกว่า Swing Low ที่กรอก!")

            if not valid_hl_fibo:
                pass
            elif risk_pct_fibo <= 0:
                st.sidebar.warning("Risk % (FIBO) ต้องมากกว่า 0")
            else:
                range_fibo_calc = abs(fibo_100_percent_level_calc - fibo_0_percent_level_calc)

                if range_fibo_calc <= 1e-9:
                    st.sidebar.warning("Range ระหว่าง High และ Low ต้องมากกว่า 0 อย่างมีนัยสำคัญ")
                else:
                    global_tp1_fibo, global_tp2_fibo, global_tp3_fibo = 0.0, 0.0, 0.0
                    if direction_fibo == "Long":
                        global_tp1_fibo = fibo_0_percent_level_calc + (range_fibo_calc * 1.618)
                        global_tp2_fibo = fibo_0_percent_level_calc + (range_fibo_calc * 2.618)
                        global_tp3_fibo = fibo_0_percent_level_calc + (range_fibo_calc * 4.236)
                    else:
                        global_tp1_fibo = fibo_0_percent_level_calc - (range_fibo_calc * 1.618)
                        global_tp2_fibo = fibo_0_percent_level_calc - (range_fibo_calc * 2.618)
                        global_tp3_fibo = fibo_0_percent_level_calc - (range_fibo_calc * 4.236)

                    selected_fibo_levels_count = sum(current_fibo_flags_fibo)
                    if selected_fibo_levels_count > 0:
                        risk_dollar_total_fibo_plan = active_balance_to_use * (risk_pct_fibo / 100.0)
                        risk_dollar_per_entry_fibo = risk_dollar_total_fibo_plan / selected_fibo_levels_count

                        temp_fibo_rr_to_tp1_list = []
                        temp_fibo_entry_details_for_saving = []

                        for i, is_selected_fibo in enumerate(current_fibo_flags_fibo):
                            if is_selected_fibo:
                                fibo_ratio_for_entry = fibos_fibo_v2[i]
                                entry_price_fibo = 0.0
                                sl_price_fibo_final = 0.0

                                # ---------- 1) ENTRY PRICE ----------
                                if direction_fibo == "Long":
                                    entry_price_fibo = fibo_0_percent_level_calc + (range_fibo_calc * fibo_ratio_for_entry)
                                else:
                                    entry_price_fibo = fibo_0_percent_level_calc - (range_fibo_calc * fibo_ratio_for_entry)

                                # ---------- 2) SL PRICE ----------
                                if abs(fibo_ratio_for_entry - 0.114) < 1e-9 or abs(fibo_ratio_for_entry - 0.25) < 1e-9 or abs(fibo_ratio_for_entry - 0.382) < 1e-9:
                                    # สำหรับ fibo = 0.114, 0.25, 0.382:
                                    sl_price_fibo_final = (fibo_0_percent_level_calc if direction_fibo == "Long"
                                                           else fibo_100_percent_level_calc)
                                elif abs(fibo_ratio_for_entry - 0.5) < 1e-9:
                                    mid_factor = (0.25 + 0.382) / 2.0
                                    if direction_fibo == "Long":
                                        sl_price_fibo_final = fibo_0_percent_level_calc + (range_fibo_calc * mid_factor)
                                    else:
                                        sl_price_fibo_final = fibo_100_percent_level_calc - (range_fibo_calc * mid_factor)
                                else:  # fibo == 0.618
                                    factor_0618 = 0.25 + (0.50 - 0.382) * 0.7  # = 0.3326
                                    if direction_fibo == "Long":
                                        sl_price_fibo_final = fibo_0_percent_level_calc + (range_fibo_calc * factor_0618)
                                    else:
                                        sl_price_fibo_final = fibo_100_percent_level_calc - (range_fibo_calc * factor_0618)

                                # ---------- 3) SL (Points) ----------
                                sl_points = abs(entry_price_fibo - sl_price_fibo_final) / 0.01

                                # ---------- 4) LOT SIZE ----------
                                if sl_points > 0:
                                    raw_lot = risk_dollar_per_entry_fibo / sl_points
                                    floored = math.floor(raw_lot * 100) / 100.0
                                    lot_size_fibo = max(0.01, floored)
                                else:
                                    lot_size_fibo = 0.0

                                # ---------- 5) RISK $ ----------
                                actual_risk_dollar_fibo = sl_points * lot_size_fibo

                                # ---------- 6) RR : TP1 ----------
                                if direction_fibo == "Long":
                                    tp1_price = fibo_0_percent_level_calc + (range_fibo_calc * 0.618)
                                    rr_to_tp1_fibo = ((tp1_price - entry_price_fibo) / abs(entry_price_fibo - sl_price_fibo_final)
                                                      if abs(entry_price_fibo - sl_price_fibo_final) > 0 else 0)
                                else:
                                    tp1_price = fibo_100_percent_level_calc - (range_fibo_calc * 0.618)
                                    rr_to_tp1_fibo = ((entry_price_fibo - tp1_price) / abs(entry_price_fibo - sl_price_fibo_final)
                                                      if abs(entry_price_fibo - sl_price_fibo_final) > 0 else 0)

                                temp_fibo_rr_to_tp1_list.append(rr_to_tp1_fibo)

                                summary_total_lots += lot_size_fibo
                                summary_total_risk_dollar += actual_risk_dollar_fibo
                                summary_total_profit_at_primary_tp += (lot_size_fibo * abs(tp1_price - entry_price_fibo))

                                temp_fibo_entry_details_for_saving.append({
                                    "Fibo Level": f"{fibo_ratio_for_entry:.3f}",
                                    "Entry": f"{entry_price_fibo:.5f}",
                                    "SL": f"{sl_price_fibo_final:.5f}",
                                    "SL (points)": f"{sl_points:.1f}",
                                    "Lot": f"{lot_size_fibo:.2f}",
                                    "Risk $": f"{actual_risk_dollar_fibo:.2f}",
                                    "RR : TP1": f"{rr_to_tp1_fibo:.6f}"
                                })

                        entry_data_summary_sec3 = temp_fibo_entry_details_for_saving

                        valid_rrs = [r for r in temp_fibo_rr_to_tp1_list if isinstance(r, (float, int)) and r > 0]
                        summary_avg_rr = np.mean(valid_rrs) if valid_rrs else 0.0
                    else:
                        st.sidebar.info("กรุณาเลือก Fibo Level สำหรับ Entry")

    except ValueError:
        if st.session_state.get("swing_high_fibo_val_v2", "") or st.session_state.get("swing_low_fibo_val_v2", ""):
            st.sidebar.warning("กรอก High/Low (FIBO) เป็นตัวเลข")
    except Exception as e_fibo_summary:
        st.sidebar.error(f"คำนวณ FIBO Summary ไม่สำเร็จ: {e_fibo_summary}")

elif mode == "CUSTOM":
    try:
        n_entry_custom = st.session_state.get("n_entry_custom_val_v2", 1)
        risk_pct_custom = st.session_state.get("risk_pct_custom_val_v2", 1.0)

        if risk_pct_custom <= 0:
            st.sidebar.warning("Risk % (CUSTOM) ต้องมากกว่า 0")
        elif n_entry_custom <= 0:
            st.sidebar.warning("จำนวนไม้ (CUSTOM) ต้องมากกว่า 0")
        else:
            risk_per_trade_custom_total = active_balance_to_use * (risk_pct_custom / 100.0)
            risk_dollar_per_entry_custom = risk_per_trade_custom_total / n_entry_custom

            temp_custom_rr_list = []
            temp_custom_legs_for_saving = []

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
                    lot_custom = 0.0
                    actual_risk_dollar_custom = 0.0
                    rr_custom = 0.0
                    profit_at_user_tp_custom = 0.0

                    if stop_custom > 1e-9:
                        lot_custom = risk_dollar_per_entry_custom / stop_custom
                        actual_risk_dollar_custom = lot_custom * stop_custom
                        if target_custom > 1e-9:
                            rr_custom = target_custom / stop_custom
                            profit_at_user_tp_custom = lot_custom * target_custom
                            temp_custom_rr_list.append(rr_custom)

                        if 0 <= rr_custom < 3.0:
                            recommended_tp_target_distance = 3 * stop_custom
                            if sl_val < entry_val:  # likely Long
                                recommended_tp_price = entry_val + recommended_tp_target_distance
                            elif sl_val > entry_val:  # likely Short
                                recommended_tp_price = entry_val - recommended_tp_target_distance
                            else:
                                recommended_tp_price = tp_val
                            if sl_val != entry_val:
                                custom_tp_recommendation_messages.append(
                                    f"ไม้ {i+1}: หากต้องการ RR≈3, TP ควรเป็น ≈ {recommended_tp_price:.5f} (TP ปัจจุบัน RR={rr_custom:.2f})"
                                )
                    else:
                        actual_risk_dollar_custom = risk_dollar_per_entry_custom

                    summary_total_lots += lot_custom
                    summary_total_risk_dollar += actual_risk_dollar_custom
                    summary_total_profit_at_primary_tp += profit_at_user_tp_custom

                    temp_custom_legs_for_saving.append({
                        "Entry": f"{entry_val:.5f}", "SL": f"{sl_val:.5f}", "TP": f"{tp_val:.5f}",
                        "Lot": f"{lot_custom:.2f}", "Risk $": f"{actual_risk_dollar_custom:.2f}", "RR": f"{rr_custom:.2f}"
                    })

                except ValueError:
                    summary_total_risk_dollar += risk_dollar_per_entry_custom
                    temp_custom_legs_for_saving.append({
                        "Entry": entry_str, "SL": sl_str, "TP": tp_str,
                        "Lot": "0.00", "Risk $": f"{risk_dollar_per_entry_custom:.2f}", "RR": "Error"
                    })

            custom_entries_summary_sec3 = temp_custom_legs_for_saving
            valid_rrs = [r for r in temp_custom_rr_list if isinstance(r, (float, int)) and r > 0]
            summary_avg_rr = np.mean(valid_rrs) if valid_rrs else 0.0

    except ValueError:
        st.sidebar.warning("กรอกข้อมูล CUSTOM ไม่ถูกต้อง")
    except Exception as e_custom_summary:
        st.sidebar.error(f"คำนวณ CUSTOM Summary ไม่สำเร็จ: {e_custom_summary}")

# --- Display Summaries in Sidebar ---
display_summary_info = False
if mode == "FIBO" and (st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", "")):
    if summary_total_lots > 0 or summary_total_risk_dollar > 0 or summary_total_profit_at_primary_tp != 0 or summary_avg_rr != 0:
        display_summary_info = True
elif mode == "CUSTOM" and st.session_state.get("n_entry_custom_val_v2", 0) > 0:
    if summary_total_lots > 0 or summary_total_risk_dollar > 0 or summary_total_profit_at_primary_tp != 0 or summary_avg_rr != 0:
        display_summary_info = True
    elif custom_tp_recommendation_messages:
        display_summary_info = True

if display_summary_info:
    current_risk_display = 0.0
    active_balance_display = active_balance_to_use
    if mode == "FIBO":
        current_risk_display = st.session_state.get('risk_pct_fibo_val_v2', 0.0)
    elif mode == "CUSTOM":
        current_risk_display = st.session_state.get('risk_pct_custom_val_v2', 0.0)

    st.sidebar.write(f"**Total Lots ({mode}):** {summary_total_lots:.2f}")
    st.sidebar.write(
        f"**Total Risk $ ({mode}):** {summary_total_risk_dollar:.2f} (Balance: {active_balance_display:,.2f}, Risk: {current_risk_display:.2f}%)"
    )
    if summary_avg_rr > 0:
        tp_ref_text = "(to Global TP1)" if mode == "FIBO" else "(to User TP)"
        st.sidebar.write(f"**Average RR ({mode}) {tp_ref_text}:** {summary_avg_rr:.2f}")
    profit_ref_text = "(at Global TP1)" if mode == "FIBO" else "(at User TP)"
    st.sidebar.write(f"**Total Expected Profit {profit_ref_text} ({mode}):** {summary_total_profit_at_primary_tp:,.2f} USD")
    if mode == "CUSTOM" and custom_tp_recommendation_messages:
        st.sidebar.markdown("**คำแนะนำ TP (เพื่อให้ RR ≈ 3):**")
        for msg in custom_tp_recommendation_messages:
            st.sidebar.caption(msg)

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

# ===================== SEC 4: MAIN AREA - ENTRY PLAN DETAILS TABLE =======================
with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):
    if mode == "FIBO":
        col1_main, col2_main = st.columns(2)
        with col1_main:
            st.markdown("### 🎯 Entry Levels (FIBO)")
            if 'entry_data_summary_sec3' in locals() and entry_data_summary_sec3:
                entry_df_main = pd.DataFrame(entry_data_summary_sec3)
                st.dataframe(entry_df_main, hide_index=True, use_container_width=True)
            else:
                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level ใน Sidebar เพื่อดู Entry Levels (หรือยังไม่มีข้อมูลสรุป).")
        with col2_main:
            st.markdown("### 🎯 Take Profit Zones (FIBO)")
            try:
                current_swing_high_tp_sec4 = st.session_state.get("swing_high_fibo_val_v2", "")
                current_swing_low_tp_sec4 = st.session_state.get("swing_low_fibo_val_v2", "")
                current_fibo_direction_tp_sec4 = st.session_state.get("direction_fibo_val_v2", "Long")
                if current_swing_high_tp_sec4 and current_swing_low_tp_sec4:
                    high_tp = float(current_swing_high_tp_sec4)
                    low_tp = float(current_swing_low_tp_sec4)
                    range_tp = abs(high_tp - low_tp)
                    if current_fibo_direction_tp_sec4 == "Long":
                        tp1 = low_tp + 1.618 * range_tp
                        tp2 = low_tp + 2.618 * range_tp
                        tp3 = low_tp + 4.236 * range_tp
                    else:
                        tp1 = high_tp - 1.618 * range_tp
                        tp2 = high_tp - 2.618 * range_tp
                        tp3 = high_tp - 4.236 * range_tp
                    tp_df_main = pd.DataFrame({
                        "TP": ["TP1", "TP2", "TP3"],
                        "Price": [f"{tp1:.5f}", f"{tp2:.5f}", f"{tp3:.5f}"]
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
        if 'custom_entries_summary_sec3' in locals() and custom_entries_summary_sec3:
            custom_df_main = pd.DataFrame(custom_entries_summary_sec3)
            cols_to_display_custom = [col for col in ["Entry", "SL", "TP", "Lot", "Risk $", "RR"] if col in custom_df_main.columns]
            if cols_to_display_custom:
                st.dataframe(custom_df_main[cols_to_display_custom], hide_index=True, use_container_width=True)
            else:
                st.dataframe(custom_df_main, hide_index=True, use_container_width=True)

            for i, row_data_dict in enumerate(custom_entries_summary_sec3):
                try:
                    rr_val_str = row_data_dict.get("RR", "0")
                    if rr_val_str is None or str(rr_val_str).strip() == "" or str(rr_val_str).lower() == "nan" or "error" in str(rr_val_str).lower():
                        continue
                    rr_val = float(rr_val_str)
                    if 0 < rr_val < 2:
                        entry_label = row_data_dict.get("ไม้ที่", i + 1)
                        st.warning(f"🎯 Entry {entry_label} มี RR ค่อนข้างต่ำ ({rr_val:.2f})")
                except:
                    pass

# ===================== SEC 5: เชื่อมปุ่ม Save Plan กับ save_plan + Drawdown Lock =======================
drawdown_today = get_today_drawdown(pd.read_csv(log_file) if os.path.exists(log_file) else pd.DataFrame(), acc_balance)
drawdown_limit = -acc_balance * (drawdown_limit_pct / 100)

if drawdown_today < 0:
    st.sidebar.markdown(f"**ขาดทุนรวมวันนี้:** {drawdown_today:,.2f} USD")
else:
    st.sidebar.markdown(f"**ขาดทุนรวมวันนี้:** {drawdown_today:,.2f} USD")

def save_plan(data, mode, asset, risk_pct, direction):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_save = pd.DataFrame(data)
    df_save["Mode"] = mode
    df_save["Asset"] = asset
    df_save["Risk %"] = risk_pct
    df_save["Direction"] = direction
    df_save["Timestamp"] = now
    if os.path.exists(log_file):
        df_old = pd.read_csv(log_file)
        df_save = pd.concat([df_old, df_save], ignore_index=True)
    df_save.to_csv(log_file, index=False)

if mode == "FIBO" and 'entry_data_summary_sec3' in locals() and save_fibo and entry_data_summary_sec3:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    else:
        try:
            save_plan(entry_data_summary_sec3, "FIBO", asset_fibo_v2, risk_pct_fibo_v2, direction_fibo_v2)
            st.sidebar.success("บันทึกแผน (FIBO) สำเร็จ!")
        except Exception as e:
            st.sidebar.error(f"Save ไม่สำเร็จ: {e}")

elif mode == "CUSTOM" and 'custom_entries_summary_sec3' in locals() and save_custom and custom_entries_summary_sec3:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    else:
        try:
            save_plan(custom_entries_summary_sec3, "CUSTOM", asset_custom_v2, risk_pct_custom_v2, "")
            st.sidebar.success("บันทึกแผน (CUSTOM) สำเร็จ!")
        except Exception as e:
            st.sidebar.error(f"Save ไม่สำเร็จ: {e}")

# ===================== SEC 7: VISUALIZER (เหลือแต่กราฟ) =======================
st.markdown("## 🟢 SEC 7: Visualizer (แสดงกราฟเท่านั้น)")

plot = st.button("Plot Plan", key="plot_plan")

if plot:
    st.markdown("#### กราฟ TradingView Widget (ลากเส้นได้, overlay plan จริง!)")
    st.components.v1.html("""
    <div class="tradingview-widget-container">
      <div id="tradingview_legendary"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({
        "width": "100%",
        "height": 600,
        "symbol": "OANDA:XAUUSD",
        "interval": "15",
        "timezone": "Asia/Bangkok",
        "theme": "dark",
        "style": "1",
        "locale": "th",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": true,
        "withdateranges": true,
        "allow_symbol_change": true,
        "hide_side_toolbar": false,
        "details": true,
        "hotlist": true,
        "calendar": true,
        "container_id": "tradingview_legendary"
      });
      </script>
    </div>
    """, height=620)
    st.caption("ลาก Fibo, Line, Box, วัด RR ได้เต็มรูปแบบ")
    st.info("Overlay แผนเทรดจริงจาก input/log! (รอต่อยอด overlay เส้นอัตโนมัติใน engine ต่อไป)")
else:
    st.info("กดปุ่ม Plot Plan เพื่อแสดงกราฟ TradingView")

st.markdown("---")
st.markdown("Visualizer รับข้อมูลแผนเทรดจริง พร้อม plot overlay (ขยาย/ปรับ engine ได้ทันทีในอนาคต)")

# ===================== SEC 8: AI SUMMARY & INSIGHT =======================
with st.expander("🤖 SEC 8: AI Summary & Insight (Beta)", expanded=True):
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            if df_log.empty:
                st.info("ยังไม่มีข้อมูลแผนเทรดใน log")
            else:
                total_trades = df_log.shape[0]
                win_trades = df_log[df_log["Risk $"].astype(float) > 0].shape[0]
                loss_trades = df_log[df_log["Risk $"].astype(float) <= 0].shape[0]
                winrate = 100 * win_trades / total_trades if total_trades > 0 else 0

                gross_profit = df_log["Risk $"].astype(float).sum()

                rr_list = []
                if "RR" in df_log.columns:
                    rr_list = pd.to_numeric(df_log["RR"], errors='coerce').dropna().tolist()
                avg_rr = np.mean(rr_list) if len(rr_list) > 0 else None

                balance = acc_balance
                max_balance = balance
                drawdowns = []
                for risk in df_log["Risk $"].astype(float):
                    balance += risk
                    if balance > max_balance:
                        max_balance = balance
                    drawdown = max_balance - balance
                    drawdowns.append(drawdown)
                max_drawdown = max(drawdowns) if drawdowns else 0

                df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce')
                if not df_log["Date"].isnull().all():
                    df_log["Weekday"] = df_log["Date"].dt.day_name()
                    win_day = df_log[df_log["Risk $"].astype(float) > 0]["Weekday"].mode()[0] if not df_log[df_log["Risk $"].astype(float) > 0].empty else "-"
                    loss_day = df_log[df_log["Risk $"].astype(float) <= 0]["Weekday"].mode()[0] if not df_log[df_log["Risk $"].astype(float) <= 0].empty else "-"
                else:
                    win_day = loss_day = "-"

                st.markdown("### สรุป AI วิเคราะห์ข้อมูลแผนเทรดล่าสุด")
                st.write(f"- **จำนวนแผนเทรด:** {total_trades:,}")
                st.write(f"- **Winrate:** {winrate:.2f}%")
                st.write(f"- **กำไร/ขาดทุนสุทธิ:** {gross_profit:,.2f} USD")
                if avg_rr is not None:
                    st.write(f"- **RR เฉลี่ย:** {avg_rr:.2f}")
                st.write(f"- **Max Drawdown:** {max_drawdown:,.2f} USD")
                st.write(f"- **วันชนะมากสุด:** {win_day}")
                st.write(f"- **วันขาดทุนมากสุด:** {loss_day}")

                st.markdown("### 🤖 AI Insight")
                insight = []
                if winrate >= 60:
                    insight.append("ระบบมี Winrate สูง มีความเสถียรภาพดี")
                elif winrate < 40:
                    insight.append("Winrate ต่ำ ควรพิจารณาจุดเข้า/วางแผนใหม่")
                if avg_rr is not None and avg_rr < 2:
                    insight.append("RR ต่ำกว่าค่าเฉลี่ยตลาด (<2) อาจเสี่ยงเกินไป")
                if max_drawdown > acc_balance * 0.05:
                    insight.append("Drawdown สูงกว่าปลอดภัย (5%) ควรควบคุม Money Management")
                if win_day != "-" and loss_day != "-" and win_day == loss_day:
                    insight.append("วันเทรดที่ชนะและแพ้มากสุดตรงกัน ลองวิเคราะห์ behavior เพิ่มเติม")
                if not insight:
                    insight = ["ยังไม่พบความเสี่ยงสำคัญในระบบเทรดล่าสุด"]
                for msg in insight:
                    st.info(msg)
        except Exception as e:
            st.warning(f"เกิดข้อผิดพลาดในการวิเคราะห์ AI: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ AI Summary")

# ===================== SEC 9: DASHBOARD + AI ULTIMATE (Tab Template) =======================
tab_dashboard, tab_rr, tab_lot, tab_time, tab_ai, tab_export = st.tabs([
    "📊 Dashboard",
    "📈 RR Histogram",
    "📉 Lot Size Evolution",
    "🕒 Time Analysis",
    "🤖 AI Recommendation",
    "⬇️ Export/Report"
])

# ----------- Tab 1: Dashboard Overview -----------
with tab_dashboard:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            if df_log.empty:
                st.info("ยังไม่มีข้อมูลสำหรับ Dashboard")
            else:
                st.markdown("### 🥧 Pie Chart: Win/Loss")
                win_count = df_log[df_log["Risk $"].astype(float) > 0].shape[0]
                loss_count = df_log[df_log["Risk $"].astype(float) <= 0].shape[0]
                pie_df = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count, loss_count]})
                pie_chart = px.pie(
                    pie_df, names="Result", values="Count", color="Result",
                    color_discrete_map={"Win": "green", "Loss": "red"}
                )
                st.plotly_chart(pie_chart, use_container_width=True)

                st.markdown("### 📊 Bar Chart: กำไร/ขาดทุนแต่ละวัน")
                df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce').dt.date
                bar_df = df_log.groupby("Date")["Risk $"].sum().reset_index()
                bar_chart = px.bar(
                    bar_df, x="Date", y="Risk $", color="Risk $",
                    color_continuous_scale=["red", "orange", "green"]
                )
                st.plotly_chart(bar_chart, use_container_width=True)

                st.markdown("### 📈 Timeline: Balance Curve")
                df_log["Balance"] = acc_balance + df_log["Risk $"].astype(float).cumsum()
                timeline_chart = px.line(df_log, x="Date", y="Balance", markers=True)
                st.plotly_chart(timeline_chart, use_container_width=True)

                st.markdown("### 🔍 Filter Dashboard")
                asset_options = ["ทั้งหมด"] + sorted(df_log["Asset"].unique().tolist())
                selected_asset = st.selectbox("Asset", asset_options, key="asset_filter_dashboard")
                if selected_asset != "ทั้งหมด":
                    df_log = df_log[df_log["Asset"] == selected_asset]
        except Exception as e:
            st.error(f"Error loading dashboard: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Dashboard Visualization")

# ----------- Tab 2: RR Histogram -----------
with tab_rr:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            rr_col = None
            for col in df_log.columns:
                if col.strip().upper() == "RR":
                    rr_col = col
                    break
            if rr_col is not None:
                rr_data = pd.to_numeric(df_log[rr_col], errors='coerce').dropna()
                if len(rr_data) == 0:
                    st.info("ยังไม่มีข้อมูล RR ที่บันทึกใน log_file")
                else:
                    st.markdown("#### RR Histogram (แจกแจง Risk:Reward)")
                    fig = px.histogram(
                        rr_data, nbins=20, title="RR Histogram",
                        labels={'value': 'RR'}, opacity=0.75
                    )
                    fig.update_layout(bargap=0.1, xaxis_title='Risk Reward Ratio', yaxis_title='จำนวนไม้')
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("ดูว่า RR ส่วนใหญ่อยู่โซนไหน ถ้ามี RR < 2 เยอะ = เสี่ยง/หลุดวินัย")
            else:
                st.warning("ไม่พบคอลัมน์ RR ใน log_file")
        except Exception as e:
            st.error(f"Error loading RR Histogram: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ RR Histogram")

# ----------- Tab 3: Lot Size Evolution -----------
with tab_lot:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            if "Lot" in df_log.columns:
                df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce').dt.date
                st.markdown("#### Lot Size Evolution (การเปลี่ยนแปลง Lot Size ตามเวลา)")
                fig = px.line(
                    df_log, x="Date", y="Lot", markers=True, title="Lot Size Evolution"
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption("วิเคราะห์ Money Management/Scaling ได้ที่นี่")
            else:
                st.warning("ไม่พบคอลัมน์ Lot ใน log_file")
        except Exception as e:
            st.error(f"Error loading Lot Size Evolution: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Lot Size Evolution")

# ----------- Tab 4: Time Analysis -----------
with tab_time:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            st.markdown("#### Time Analysis (วิเคราะห์ตามวัน/เวลา)")
            df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce')
            df_log["Weekday"] = df_log["Date"].dt.day_name()
            weekday_df = df_log.groupby("Weekday")["Risk $"].sum().reindex(
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            ).reset_index()
            bar_chart = px.bar(
                weekday_df, x="Weekday", y="Risk $", title="กำไร/ขาดทุนรวมตามวันในสัปดาห์"
            )
            st.plotly_chart(bar_chart, use_container_width=True)
            st.caption("ดูว่าเทรดวันไหนเวิร์ค วันไหนควรหลีกเลี่ยง")
        except Exception as e:
            st.error(f"Error loading Time Analysis: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Time Analysis")

# ----------- Tab 5: AI Recommendation -----------
with tab_ai:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            st.markdown("### AI Insight & Recommendation")
            total_trades = df_log.shape[0]
            win_trades = df_log[df_log["Risk $"].astype(float) > 0].shape[0]
            loss_trades = df_log[df_log["Risk $"].astype(float) <= 0].shape[0]
            winrate = 100 * win_trades / total_trades if total_trades > 0 else 0
            st.write(f"จำนวนแผนเทรด: {total_trades}")
            st.write(f"Winrate: {winrate:.2f}%")
            insight = []
            if winrate >= 60:
                insight.append("Winrate สูง ระบบเสถียรภาพดี")
            elif winrate < 40:
                insight.append("Winrate ต่ำ ควรพิจารณากลยุทธ์ใหม่")
            if not insight:
                insight.append("ยังไม่พบความเสี่ยงสำคัญ")
            for msg in insight:
                st.info(msg)
        except Exception as e:
            st.error(f"Error loading AI Recommendation: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ AI Recommendation")

# ----------- Tab 6: Export/Report -----------
with tab_export:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            st.markdown("### Export/Download Report")
            st.download_button("Download log_file (CSV)", df_log.to_csv(index=False), file_name="log_file.csv")
        except Exception as e:
            st.error(f"Error loading Export/Report: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Export/Report")

# ===================== SEC 6: LOG VIEWER (ล่างสุด + EXPANDER เดียว) =======================
with st.expander("📚 Log Viewer (คลิกเพื่อเปิด/ปิด)", expanded=False):
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            col1, col2, col3 = st.columns(3)
            with col1:
                mode_filter = st.selectbox("Mode", ["ทั้งหมด"] + sorted(df_log["Mode"].unique().tolist()))
            with col2:
                asset_filter = st.selectbox("Asset", ["ทั้งหมด"] + sorted(df_log["Asset"].unique().tolist()))
            with col3:
                date_filter = st.text_input("ค้นหาวันที่ (YYYY-MM-DD)", value="")
            df_show = df_log.copy()
            if mode_filter != "ทั้งหมด":
                df_show = df_show[df_show["Mode"] == mode_filter]
            if asset_filter != "ทั้งหมด":
                df_show = df_show[df_show["Asset"] == asset_filter]
            if date_filter:
                df_show = df_show[df_show["Timestamp"].str.contains(date_filter)]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"อ่าน log ไม่ได้: {e}")
    else:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้")
