# ===================== SEC 0: IMPORT & CONFIG =======================

import streamlit as st

import pandas as pd

import numpy as np

from datetime import datetime, date

import plotly.express as px

import google.generativeai as genai

import gspread

import plotly.graph_objects as go

import random

import io 

import uuid

import hashlib



st.set_page_config(page_title="Ultimate-Chart", layout="wide")



if 'uploader_key_version' not in st.session_state:

    st.session_state.uploader_key_version = 0



if 'latest_statement_equity' not in st.session_state:

    st.session_state.latest_statement_equity = None 



if 'current_account_balance' not in st.session_state:

    st.session_state.current_account_balance = 10000.0 # Default fallback



# กำหนดชื่อ Google Sheet และ Worksheet ที่จะใช้เก็บข้อมูล

GOOGLE_SHEET_NAME = "TradeLog"

WORKSHEET_PORTFOLIOS = "Portfolios"

WORKSHEET_PLANNED_LOGS = "PlannedTradeLogs"

WORKSHEET_ACTUAL_TRADES = "ActualTrades"

WORKSHEET_ACTUAL_ORDERS = "ActualOrders"

WORKSHEET_ACTUAL_POSITIONS = "ActualPositions"

WORKSHEET_STATEMENT_SUMMARIES = "StatementSummaries"

WORKSHEET_UPLOAD_HISTORY = "UploadHistory"



@st.cache_resource

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



@st.cache_data(ttl=300)

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



        if 'EnableScaling' in df_portfolios.columns:

             df_portfolios['EnableScaling'] = df_portfolios['EnableScaling'].astype(str).str.upper().map({'TRUE': True, 'YES': True, '1': True, 'FALSE': False, 'NO': False, '0': False}).fillna(False)



        date_cols = ['CompetitionEndDate', 'TargetEndDate', 'CreationDate']

        for col in date_cols:

            if col in df_portfolios.columns:

                df_portfolios[col] = pd.to_datetime(df_portfolios[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S')



        return df_portfolios

    except gspread.exceptions.WorksheetNotFound:

        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'.")

        return pd.DataFrame()

    except gspread.exceptions.APIError as e_api:

        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:

            st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios (Quota Exceeded): {e_api.args[0] if e_api.args else 'Unknown quota error'}. ลองอีกครั้งในภายหลัง")

        else:

            st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios (API Error): {e_api}")

        return pd.DataFrame()

    except Exception as e:

        st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios: {e}")

        return pd.DataFrame()



@st.cache_data(ttl=180)

def load_all_planned_trade_logs_from_gsheets():

    gc = get_gspread_client()

    if gc is None:

        print("Warning: GSpread client not available for loading planned trade logs.")

        return pd.DataFrame()

    try:

        sh = gc.open(GOOGLE_SHEET_NAME)

        worksheet = sh.worksheet(WORKSHEET_PLANNED_LOGS)

        records = worksheet.get_all_records()

        

        if not records:

            return pd.DataFrame()

        

        df_logs = pd.DataFrame(records)

        

        if 'Timestamp' in df_logs.columns:

            df_logs['Timestamp'] = pd.to_datetime(df_logs['Timestamp'], errors='coerce')

        if 'Risk $' in df_logs.columns:

            df_logs['Risk $'] = pd.to_numeric(df_logs['Risk $'], errors='coerce').fillna(0)

        if 'RR' in df_logs.columns:

            df_logs['RR'] = pd.to_numeric(df_logs['RR'], errors='coerce')

        if 'PortfolioID' in df_logs.columns:

            df_logs['PortfolioID'] = df_logs['PortfolioID'].astype(str)

        

        cols_to_numeric_viewer = ['Entry', 'SL', 'TP', 'Lot', 'Risk %']

        for col_viewer in cols_to_numeric_viewer:

            if col_viewer in df_logs.columns:

                df_logs[col_viewer] = pd.to_numeric(df_logs[col_viewer], errors='coerce')



        return df_logs

    except gspread.exceptions.WorksheetNotFound:

        print(f"Warning: Worksheet '{WORKSHEET_PLANNED_LOGS}' not found for centralized loading.")

        return pd.DataFrame()

    except gspread.exceptions.APIError as e_api:

        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:

            print(f"APIError (Quota Exceeded) loading planned trade logs: {e_api.args[0] if e_api.args else 'Unknown quota error'}")

        else:

            print(f"APIError loading planned trade logs: {e_api}")

        return pd.DataFrame()

    except Exception as e:

        print(f"Unexpected error loading all planned trade logs: {e}")

        return pd.DataFrame()



@st.cache_data(ttl=180)

def load_actual_trades_from_gsheets():

    gc = get_gspread_client()

    if gc is None:

        print("Warning: GSpread client not available for loading actual trades.")

        return pd.DataFrame()

    try:

        sh = gc.open(GOOGLE_SHEET_NAME)

        worksheet = sh.worksheet(WORKSHEET_ACTUAL_TRADES)

        

        records = worksheet.get_all_records(numericise_ignore=['all'])

        

        if not records:

            return pd.DataFrame()

        

        df_actual_trades = pd.DataFrame(records)

        

        if 'Time_Deal' in df_actual_trades.columns:

            df_actual_trades['Time_Deal'] = pd.to_datetime(df_actual_trades['Time_Deal'], errors='coerce')



        numeric_cols_actual = [

            'Volume_Deal', 'Price_Deal', 'Commission_Deal', 

            'Fee_Deal', 'Swap_Deal', 'Profit_Deal', 'Balance_Deal'

        ]

        for col in numeric_cols_actual:

            if col in df_actual_trades.columns:

                df_actual_trades[col] = pd.to_numeric(df_actual_trades[col], errors='coerce')



        if 'PortfolioID' in df_actual_trades.columns:

            df_actual_trades['PortfolioID'] = df_actual_trades['PortfolioID'].astype(str)

        

        return df_actual_trades



    except gspread.exceptions.WorksheetNotFound:

        print(f"Warning: Worksheet '{WORKSHEET_ACTUAL_TRADES}' not found for loading actual trades.")

        return pd.DataFrame()

    except gspread.exceptions.APIError as e_api:

        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:

            print(f"APIError (Quota Exceeded) loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e_api.args[0] if e_api.args else 'Unknown quota error'}")

        else:

            print(f"APIError loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e_api}")

        return pd.DataFrame()

    except Exception as e:

        print(f"Unexpected error loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e}")

        return pd.DataFrame()



# ===================== SEC 1: PORTFOLIO SELECTION (Sidebar) =======================

df_portfolios_gs = load_portfolios_from_gsheets()



st.sidebar.markdown("---")

st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")



if 'active_portfolio_name_gs' not in st.session_state:

    st.session_state.active_portfolio_name_gs = ""

if 'active_portfolio_id_gs' not in st.session_state:

    st.session_state.active_portfolio_id_gs = None

if 'current_portfolio_details' not in st.session_state:

    st.session_state.current_portfolio_details = None



portfolio_names_list_gs = [""]

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



if selected_portfolio_name_gs != st.session_state.active_portfolio_name_gs:

    if 'ultimate_stmt_uploader_v7_final' in st.session_state and st.session_state.ultimate_stmt_uploader_v7_final is not None:

        st.session_state.ultimate_stmt_uploader_v7_final = None

        st.sidebar.warning("⚠️ การเปลี่ยนพอร์ตทำให้ไฟล์ที่อัปโหลดไว้ (ในส่วน Statement Import) ถูกรีเซ็ต กรุณาอัปโหลดไฟล์อีกครั้งหากต้องการ")



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



            portfolio_initial_balance_val = st.session_state.current_portfolio_details.get('InitialBalance')

            if pd.notna(portfolio_initial_balance_val):

                try:

                    st.session_state.current_account_balance = float(portfolio_initial_balance_val)

                    st.session_state.latest_statement_equity = None 

                except (ValueError, TypeError):

                    st.sidebar.warning("ไม่สามารถแปลง InitialBalance จากพอร์ตเป็นตัวเลขได้ ใช้ค่าเริ่มต้นแทน.")

                    st.session_state.current_account_balance = 10000.0

                    st.session_state.latest_statement_equity = None

            else:

                st.session_state.current_account_balance = 10000.0

                st.session_state.latest_statement_equity = None



        else:

            st.session_state.active_portfolio_id_gs = None

            st.session_state.current_portfolio_details = None

            st.sidebar.warning(f"ไม่พบข้อมูลสำหรับพอร์ตชื่อ '{selected_portfolio_name_gs}'.")

else:

    st.session_state.active_portfolio_name_gs = ""

    st.session_state.active_portfolio_id_gs = None

    st.session_state.current_portfolio_details = None

    st.session_state.current_account_balance = 10000.0

    st.session_state.latest_statement_equity = None



if st.session_state.current_portfolio_details:

    details = st.session_state.current_portfolio_details

    st.sidebar.markdown(f"**💡 ข้อมูลพอร์ต '{details.get('PortfolioName', 'N/A')}'**")

    if pd.notna(details.get('InitialBalance')): st.sidebar.write(f"- Balance เริ่มต้น: {details['InitialBalance']:,.2f} USD")

    if pd.notna(details.get('ProgramType')): st.sidebar.write(f"- ประเภท: {details['ProgramType']}")

    if pd.notna(details.get('Status')): st.sidebar.write(f"- สถานะ: {details['Status']}")

    

    if details.get('ProgramType') in ["Prop Firm Challenge", "Funded Account", "Trading Competition"]:

        if pd.notna(details.get('ProfitTargetPercent')): st.sidebar.write(f"- เป้าหมายกำไร: {details['ProfitTargetPercent']:.1f}%")

        if pd.notna(details.get('DailyLossLimitPercent')): st.sidebar.write(f"- Daily Loss Limit: {details['DailyLossLimitPercent']:.1f}%")

        if pd.notna(details.get('TotalStopoutPercent')): st.sidebar.write(f"- Total Stopout: {details['TotalStopoutPercent']:.1f}%")

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

        if not pd.api.types.is_datetime64_any_dtype(log_source_df['Timestamp']):

            log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')

        

        log_source_df = log_source_df.dropna(subset=['Timestamp'])



        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)

        df_today = log_source_df[log_source_df["Timestamp"].dt.strftime("%Y-%m-%d") == today_str]

        drawdown = df_today["Risk $"].sum()

        return drawdown

    except KeyError as e: 

        return 0

    except Exception as e: 

        return 0



def get_performance(log_source_df, mode="week"):

    if log_source_df.empty: return 0, 0, 0

    try:

        if not pd.api.types.is_datetime64_any_dtype(log_source_df['Timestamp']):

            log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')

        

        log_source_df = log_source_df.dropna(subset=['Timestamp'])



        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)

        now = datetime.now()

        if mode == "week":

            week_start_date = now - pd.Timedelta(days=now.weekday())

            df_period = log_source_df[log_source_df["Timestamp"] >= week_start_date.replace(hour=0, minute=0, second=0, microsecond=0)]

        else:

            month_start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            df_period = log_source_df[log_source_df["Timestamp"] >= month_start_date]

        

        if "Risk $" not in df_period.columns:

            return 0,0,0



        win = df_period[df_period["Risk $"] > 0].shape[0]

        loss = df_period[df_period["Risk $"] <= 0].shape[0]

        total_trades = win + loss

        winrate = (100 * win / total_trades) if total_trades > 0 else 0

        gain = df_period["Risk $"].sum()

        return winrate, gain, total_trades

    except KeyError as e: 

        return 0,0,0

    except Exception as e: 

        return 0,0,0



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

        expected_headers_plan = [ 

            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",

            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"

        ]

        current_headers_plan = []

        if ws.row_count > 0:

            try: current_headers_plan = ws.row_values(1)

            except Exception: current_headers_plan = []

        

        if not current_headers_plan or all(h == "" for h in current_headers_plan):

            ws.update([expected_headers_plan], value_input_option='USER_ENTERED')

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

            try: current_sheet_headers = ws.row_values(1)

            except Exception: pass 

        

        if not current_sheet_headers or all(h == "" for h in current_sheet_headers) :

             ws.update([expected_gsheet_headers_portfolio], value_input_option='USER_ENTERED') 



        new_row_values = [str(portfolio_data_dict.get(header, "")).strip() for header in expected_gsheet_headers_portfolio]

        ws.append_row(new_row_values, value_input_option='USER_ENTERED')

        return True

    except gspread.exceptions.WorksheetNotFound:

        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}'. กรุณาสร้างชีตนี้ก่อน และใส่ Headers ให้ถูกต้อง")

        return False

    except Exception as e:

        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกพอร์ตใหม่ไปยัง Google Sheets: {e}")

        st.exception(e) 

        return False



# ===================== SEC 1.5: PORTFOLIO MANAGEMENT UI (Main Area) =======================

def on_program_type_change_v8():

    st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8



with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=True):

    st.subheader("พอร์ตทั้งหมดของคุณ")

    if df_portfolios_gs.empty:

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



    st.selectbox(

        "ประเภทพอร์ต (Program Type)*", 

        options=program_type_options_outside, 

        index=program_type_options_outside.index(st.session_state.exp_pf_type_select_v8_key), 

        key="exp_pf_type_selector_widget_v8", 

        on_change=on_program_type_change_v8 

    )

    

    selected_program_type_to_use_in_form = st.session_state.exp_pf_type_select_v8_key



    with st.form("new_portfolio_form_main_v8_final", clear_on_submit=True): 

        st.markdown(f"**กรอกข้อมูลพอร์ต (สำหรับประเภท: {selected_program_type_to_use_in_form if selected_program_type_to_use_in_form else 'ยังไม่ได้เลือก'})**")

        

        form_c1_in_form, form_c2_in_form = st.columns(2)

        with form_c1_in_form:

            form_new_portfolio_name_in_form = st.text_input("ชื่อพอร์ต (Portfolio Name)*", key="form_pf_name_v8")

        with form_c2_in_form:

            form_new_initial_balance_in_form = st.number_input("บาลานซ์เริ่มต้น (Initial Balance)*", min_value=0.01, value=10000.0, format="%.2f", key="form_pf_balance_v8")

        

        form_status_options_in_form = ["Active", "Inactive", "Pending", "Passed", "Failed"]

        form_new_status_in_form = st.selectbox("สถานะพอร์ต (Status)*", options=form_status_options_in_form, index=0, key="form_pf_status_v8")

        

        form_new_evaluation_step_val_in_form = ""

        if selected_program_type_to_use_in_form == "Prop Firm Challenge":

            evaluation_step_options_in_form = ["", "Phase 1", "Phase 2", "Phase 3", "Verification"]

            form_new_evaluation_step_val_in_form = st.selectbox("ขั้นตอนการประเมิน (Evaluation Step)", 

                                                                options=evaluation_step_options_in_form, index=0, 

                                                                key="form_pf_eval_step_select_v8")



        form_profit_target_val = 8.0; form_daily_loss_val = 5.0; form_total_stopout_val = 10.0; form_leverage_val = 100.0; form_min_days_val = 0

        form_comp_end_date = None; form_comp_goal_metric = ""

        form_profit_target_val_comp = 20.0

        form_daily_loss_val_comp = 5.0    

        form_total_stopout_val_comp = 10.0



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

                form_profit_target_val_comp = st.number_input("เป้าหมายกำไร % (Comp)", value=form_profit_target_val_comp, format="%.1f", key="f_tc_profit_v8") 

            with f_tc2: 

                form_comp_goal_metric = st.text_input("ตัวชี้วัดเป้าหมาย (Comp)", value=form_comp_goal_metric, help="เช่น %Gain, ROI", key="f_tc_goalmetric_v8")

                form_daily_loss_val_comp = st.number_input("จำกัดขาดทุนต่อวัน % (Comp)", value=form_daily_loss_val_comp, format="%.1f", key="f_tc_dd_v8")

                form_total_stopout_val_comp = st.number_input("จำกัดขาดทุนรวม % (Comp)", value=form_total_stopout_val_comp, format="%.1f", key="f_tc_maxdd_v8")



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

            elif not df_portfolios_gs.empty and form_new_portfolio_name_in_form in df_portfolios_gs['PortfolioName'].astype(str).values:

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

                    data_to_save.update({

                        'ProfitTargetPercent': form_profit_target_val,

                        'DailyLossLimitPercent': form_daily_loss_val,

                        'TotalStopoutPercent': form_total_stopout_val,

                        'Leverage': form_leverage_val,

                        'MinTradingDays': form_min_days_val

                    })

                

                if selected_program_type_to_use_in_form == "Trading Competition":

                    data_to_save.update({

                        'CompetitionEndDate': form_comp_end_date.strftime("%Y-%m-%d") if form_comp_end_date else None,

                        'CompetitionGoalMetric': form_comp_goal_metric,

                        'ProfitTargetPercent': form_profit_target_val_comp, 

                        'DailyLossLimitPercent': form_daily_loss_val_comp,

                        'TotalStopoutPercent': form_total_stopout_val_comp

                    })



                if selected_program_type_to_use_in_form == "Personal Account":

                    data_to_save.update({

                        'OverallProfitTarget': form_pers_overall_profit_val,

                        'TargetEndDate': form_pers_target_end_date.strftime("%Y-%m-%d") if form_pers_target_end_date else None,

                        'WeeklyProfitTarget': form_pers_weekly_profit_val,

                        'DailyProfitTarget': form_pers_daily_profit_val,

                        'MaxAcceptableDrawdownOverall': form_pers_max_dd_overall_val,

                        'MaxAcceptableDrawdownDaily': form_pers_max_dd_daily_val

                    })



                if form_enable_scaling_checkbox_val:

                    data_to_save.update({

                        'EnableScaling': True,

                        'ScalingCheckFrequency': form_scaling_freq_val,

                        'ScaleUp_MinWinRate': form_su_wr_val,

                        'ScaleUp_MinGainPercent': form_su_gain_val,

                        'ScaleUp_RiskIncrementPercent': form_su_inc_val,

                        'ScaleDown_MaxLossPercent': form_sd_loss_val,

                        'ScaleDown_LowWinRate': form_sd_wr_val,

                        'ScaleDown_RiskDecrementPercent': form_sd_dec_val,

                        'MinRiskPercentAllowed': form_min_risk_val,

                        'MaxRiskPercentAllowed': form_max_risk_val,

                        'CurrentRiskPercent': form_current_risk_val

                    })

                else:

                    data_to_save['EnableScaling'] = False

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



# ===================== SEC 2: COMMON INPUTS & MODE SELECTION =======================

active_balance_to_use = 10000.0

initial_risk_pct_from_portfolio = 1.0



if 'latest_statement_equity' in st.session_state and st.session_state.latest_statement_equity is not None:

    active_balance_to_use = st.session_state.latest_statement_equity

    st.session_state.current_account_balance = st.session_state.latest_statement_equity

    st.sidebar.markdown(f"**💰 Balance สำหรับคำนวณ:** <font color='lime'>{st.session_state.current_account_balance:,.2f} USD (จาก Statement Equity)</font>", unsafe_allow_html=True)

elif 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:

    details = st.session_state.current_portfolio_details

    

    portfolio_initial_balance_val = details.get('InitialBalance')

    if pd.notna(portfolio_initial_balance_val):

        try:

            active_balance_to_use = float(portfolio_initial_balance_val)

            st.session_state.current_account_balance = active_balance_to_use

            st.sidebar.markdown(f"**💰 Balance สำหรับคำนวณ:** <font color='gold'>{st.session_state.current_account_balance:,.2f} USD (จาก Initial Balance พอร์ต)</font>", unsafe_allow_html=True)

        except (ValueError, TypeError):

            st.sidebar.warning("ไม่สามารถแปลง InitialBalance จากพอร์ตเป็นตัวเลขได้ ใช้ค่าเริ่มต้นแทน")

            st.session_state.current_account_balance = 10000.0

            st.sidebar.markdown(f"**💰 Balance สำหรับคำนวณ:** {st.session_state.current_account_balance:,.2f} USD (จากค่าเริ่มต้น)", unsafe_allow_html=True)

    else:

        st.session_state.current_account_balance = 10000.0

        st.sidebar.markdown(f"**💰 Balance สำหรับคำนวณ:** {st.session_state.current_account_balance:,.2f} USD (จากค่าเริ่มต้น)", unsafe_allow_html=True)



else:

    st.session_state.current_account_balance = 10000.0

    st.sidebar.info("ยังไม่ได้เลือกพอร์ต หรือไม่พบข้อมูลพอร์ต ใช้ Balance เริ่มต้น: 10,000.00 USD")

    st.sidebar.markdown(f"**💰 Balance สำหรับคำนวณ:** {st.session_state.current_account_balance:,.2f} USD (จากค่าเริ่มต้น)", unsafe_allow_html=True)



if 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:

    details = st.session_state.current_portfolio_details

    current_risk_val_str = details.get('CurrentRiskPercent')

    if pd.notna(current_risk_val_str) and str(current_risk_val_str).strip() != "":

        try:

            risk_val_float = float(current_risk_val_str)

            if risk_val_float > 0:

                 initial_risk_pct_from_portfolio = risk_val_float

        except (ValueError, TypeError):

            st.sidebar.warning("ไม่สามารถแปลง CurrentRiskPercent จากพอร์ตเป็นตัวเลขได้ ใช้ค่าเริ่มต้นแทน")

            pass



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

    

    sb_active_portfolio_selector_gs_keep = st.session_state.get('sb_active_portfolio_selector_gs', "")



    keys_to_fully_preserve = {"gcp_service_account"}

    temp_preserved_values = {}

    for k_fp in keys_to_fully_preserve:

        if k_fp in st.session_state:

            temp_preserved_values[k_fp] = st.session_state[k_fp]



    keys_to_clear = [k for k in st.session_state.keys() if k not in keys_to_fully_preserve]

    for key in keys_to_clear:

        del st.session_state[key]

            

    for k_fp, v_fp in temp_preserved_values.items():

        st.session_state[k_fp] = v_fp



    st.session_state.mode = mode_to_keep

    st.session_state.drawdown_limit_pct = dd_limit_to_keep

    

    st.session_state.active_portfolio_name_gs = active_portfolio_name_gs_keep

    st.session_state.active_portfolio_id_gs = active_portfolio_id_gs_keep

    st.session_state.current_portfolio_details = current_portfolio_details_keep

    

    if sb_active_portfolio_selector_gs_keep: 

        st.session_state.sb_active_portfolio_selector_gs = sb_active_portfolio_selector_gs_keep



    preserved_active_balance = 10000.0

    preserved_initial_risk = 1.0

    preserved_latest_statement_equity = None

    if 'latest_statement_equity' in st.session_state and st.session_state.latest_statement_equity is not None:

        preserved_latest_statement_equity = st.session_state.latest_statement_equity

        preserved_active_balance = preserved_latest_statement_equity

    elif current_portfolio_details_keep:

        pf_balance_val = current_portfolio_details_keep.get('InitialBalance')

        if pd.notna(pf_balance_val):

            try: preserved_active_balance = float(pf_balance_val)

            except (ValueError, TypeError): pass

        

        pf_risk_str = current_portfolio_details_keep.get('CurrentRiskPercent')

        if pd.notna(pf_risk_str) and str(pf_risk_str).strip() != "":

            try:

                pf_risk_float = float(pf_risk_str)

                if pf_risk_float > 0: preserved_initial_risk = pf_risk_float

            except (ValueError, TypeError): pass

            

    st.session_state.current_account_balance = preserved_active_balance

    st.session_state.latest_statement_equity = preserved_latest_statement_equity



    st.session_state.risk_pct_fibo_val_v2 = preserved_initial_risk

    st.session_state.asset_fibo_val_v2 = "XAUUSD" 

    st.session_state.risk_pct_custom_val_v2 = preserved_initial_risk

    st.session_state.asset_custom_val_v2 = "XAUUSD" 



    st.session_state.swing_high_fibo_val_v2 = ""

    st.session_state.swing_low_fibo_val_v2 = ""

    st.session_state.fibo_flags_v2 = [True] * 5



    default_n_entries_custom = 2

    st.session_state.n_entry_custom_val_v2 = default_n_entries_custom

    for i in range(default_n_entries_custom):

        st.session_state[f"custom_entry_{i}_v3"] = "0.00"

        st.session_state[f"custom_sl_{i}_v3"] = "0.00"

        st.session_state[f"custom_tp_{i}_v3"] = "0.00"

        

    if 'plot_data' in st.session_state:

        del st.session_state['plot_data']

        

    st.toast("รีเซ็ตฟอร์มเรียบร้อยแล้ว!", icon="🔄")

    st.rerun()



# ===================== SEC 2.1: FIBO TRADE DETAILS =======================

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

        high_val_fibo_v2 = float(swing_high_fibo_v2) if swing_high_fibo_v2 else 0.0

        low_val_fibo_v2 = float(swing_low_fibo_v2) if swing_low_fibo_v2 else 0.0

        if swing_high_fibo_v2 and swing_low_fibo_v2:

            if high_val_fibo_v2 <= low_val_fibo_v2:

                st.sidebar.warning("High ต้องมากกว่า Low!")

    except ValueError:

        if swing_high_fibo_v2 or swing_low_fibo_v2:

            st.sidebar.warning("กรุณาใส่ High/Low เป็นตัวเลขที่ถูกต้อง")



    if risk_pct_fibo_v2 <= 0: 

        st.sidebar.warning("Risk% ต้องมากกว่า 0")



    st.sidebar.markdown("---")

    try:

        if swing_high_fibo_v2 and swing_low_fibo_v2:

            high_preview_fibo_v2 = float(swing_high_fibo_v2)

            low_preview_fibo_v2 = float(swing_low_fibo_v2)

            if high_preview_fibo_v2 > low_preview_fibo_v2 and any(st.session_state.fibo_flags_v2):

                st.sidebar.markdown("**Preview (เบื้องต้น):**")

                first_selected_fibo_index_v2 = -1

                try:

                    first_selected_fibo_index_v2 = st.session_state.fibo_flags_v2.index(True)

                except ValueError:

                    pass

                

                if first_selected_fibo_index_v2 != -1:

                    preview_entry_fibo_v2 = 0.0

                    if direction_fibo_v2 == "Long":

                        preview_entry_fibo_v2 = low_preview_fibo_v2 + (high_preview_fibo_v2 - low_preview_fibo_v2) * fibos_fibo_v2[first_selected_fibo_index_v2]

                    else:

                        preview_entry_fibo_v2 = high_preview_fibo_v2 - (high_preview_fibo_v2 - low_preview_fibo_v2) * fibos_fibo_v2[first_selected_fibo_index_v2]

                    st.sidebar.markdown(f"Entry แรกที่เลือก ≈ **{preview_entry_fibo_v2:.2f}**")

                    st.sidebar.caption("Lot/TP/ผลลัพธ์เต็มอยู่ด้านล่าง (ใน Strategy Summary)")

    except ValueError:

        pass

    except Exception:

        pass



    save_fibo = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo_v3")



# ===================== SEC 2.2: CUSTOM TRADE DETAILS =======================

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

        st.session_state.n_entry_custom_val_v2 = int(n_entry_custom_v2)



    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")

    custom_inputs_v2 = [] 

    

    current_custom_risk_pct_v2 = risk_pct_custom_v2 

    risk_per_trade_custom_v2 = current_custom_risk_pct_v2 / 100.0 

    

    risk_dollar_total_custom_v2 = active_balance_to_use * risk_per_trade_custom_v2 

    

    num_entries_val_custom_v2 = st.session_state.n_entry_custom_val_v2

    risk_dollar_per_entry_custom_v2 = risk_dollar_total_custom_v2 / num_entries_val_custom_v2 if num_entries_val_custom_v2 > 0 else 0



    for i in range(num_entries_val_custom_v2):

        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")

        col_e_v2, col_s_v2, col_t_v2 = st.sidebar.columns(3)

        entry_key_v2 = f"custom_entry_{i}_v3" 

        sl_key_v2 = f"custom_sl_{i}_v3"       

        tp_key_v2 = f"custom_tp_{i}_v3"       



        if entry_key_v2 not in st.session_state: st.session_state[entry_key_v2] = "0.00"

        if sl_key_v2 not in st.session_state: st.session_state[sl_key_v2] = "0.00"

        if tp_key_v2 not in st.session_state: st.session_state[tp_key_v2] = "0.00"



        with col_e_v2:

            entry_str_v2 = st.text_input(f"Entry {i+1}", value=st.session_state[entry_key_v2], key=entry_key_v2)

        with col_s_v2:

            sl_str_v2 = st.text_input(f"SL {i+1}", value=st.session_state[sl_key_v2], key=sl_key_v2)

        with col_t_v2:

            tp_str_v2 = st.text_input(f"TP {i+1}", value=st.session_state[tp_key_v2], key=tp_key_v2)

        

        lot_display_str_v2 = "Lot: - (Error)"

        risk_per_entry_display_str_v2 = f"Risk$ ต่อไม้: {risk_dollar_per_entry_custom_v2:.2f}"

        tp_rr3_info_str_v2 = "Stop: - (Error)"

        stop_val_v2 = None



        try:

            entry_float_v2 = float(entry_str_v2)

            sl_float_v2 = float(sl_str_v2)

            

            if sl_float_v2 == entry_float_v2:

                stop_val_v2 = 0

                lot_display_str_v2 = "Lot: - (SL=Entry)"

                tp_rr3_info_str_v2 = "Stop: 0 (SL=Entry)"

            else:

                stop_val_v2 = abs(entry_float_v2 - sl_float_v2)

                if stop_val_v2 > 1e-9:

                    lot_val_v2 = risk_dollar_per_entry_custom_v2 / stop_val_v2

                    lot_display_str_v2 = f"Lot: {lot_val_v2:.2f}"

                    tp_rr3_info_str_v2 = f"Stop: {stop_val_v2:.5f}"

                else:

                    lot_display_str_v2 = "Lot: - (Stop=0)"

                    tp_rr3_info_str_v2 = "Stop: 0"



        except ValueError:

            pass

        except Exception:

            pass

        

        st.sidebar.caption(f"{lot_display_str_v2} | {risk_per_entry_display_str_v2} | {tp_rr3_info_str_v2}")

        custom_inputs_v2.append({"entry": entry_str_v2, "sl": sl_str_v2, "tp": tp_str_v2})



    if current_custom_risk_pct_v2 <= 0:

        st.sidebar.warning("Risk% ต้องมากกว่า 0")

    save_custom = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom_v3")



# ===================== SEC 2.3: SIDEBAR - CALCULATIONS, SUMMARY & ACTIONS =======================

st.sidebar.markdown("---")

st.sidebar.markdown("### 🧾 Strategy Summary")



summary_total_lots = 0.0

summary_total_risk_dollar = 0.0

summary_avg_rr = 0.0

summary_total_profit_at_primary_tp = 0.0

custom_tp_recommendation_messages = [] 



RATIO_TP1_EFF = 1.618

RATIO_TP2_EFF = 2.618

RATIO_TP3_EFF = 4.236



entry_data_summary_sec3 = []

custom_entries_summary_sec3 = []



if mode == "FIBO":

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

            else:

                if high_fibo_input > low_fibo_input:

                    fibo_0_percent_level_calc = high_fibo_input

                    valid_hl_fibo = True

                else:

                    st.sidebar.warning("Short: Swing High ที่กรอก ต้องมากกว่า Swing Low ที่กรอก!")



            if not valid_hl_fibo:

                pass

            elif risk_pct_fibo <= 0:

                st.sidebar.warning("Risk % (FIBO) ต้องมากกว่า 0")

            else:

                range_fibo_calc = abs(high_fibo_input - low_fibo_input)



                if range_fibo_calc <= 1e-9:

                    st.sidebar.warning("Range ระหว่าง High และ Low ต้องมากกว่า 0 อย่างมีนัยสำคัญ")

                else:

                    global_tp1_fibo, global_tp2_fibo, global_tp3_fibo = 0.0, 0.0, 0.0

                    if direction_fibo == "Long":

                        global_tp1_fibo = low_fibo_input + (range_fibo_calc * RATIO_TP1_EFF)

                    else:

                        global_tp1_fibo = high_fibo_input - (range_fibo_calc * RATIO_TP1_EFF)



                    selected_fibo_levels_count = sum(current_fibo_flags_fibo)

                    if selected_fibo_levels_count > 0:

                        risk_dollar_total_fibo_plan = active_balance_to_use * (risk_pct_fibo / 100.0)

                        risk_dollar_per_entry_fibo = risk_dollar_total_fibo_plan / selected_fibo_levels_count

                        

                        temp_fibo_rr_to_tp1_list = []

                        temp_fibo_entry_details_for_saving = [] 



                        for i, is_selected_fibo in enumerate(current_fibo_flags_fibo):

                            if is_selected_fibo:

                                fibo_ratio_for_entry = fibos_fibo_v2[i]

                                entry_price_fibo, sl_price_fibo_final = 0.0, 0.0



                                if direction_fibo == "Long":

                                    entry_price_fibo = fibo_0_percent_level_calc + (range_fibo_calc * fibo_ratio_for_entry)

                                    sl_price_fibo_final = fibo_0_percent_level_calc 

                                else:

                                    entry_price_fibo = fibo_0_percent_level_calc - (range_fibo_calc * fibo_ratio_for_entry)

                                    sl_price_fibo_final = fibo_0_percent_level_calc

                                

                                stop_distance_fibo = abs(entry_price_fibo - sl_price_fibo_final)

                                lot_size_fibo, actual_risk_dollar_fibo = 0.0, 0.0

                                if stop_distance_fibo > 1e-9:

                                    lot_size_fibo = risk_dollar_per_entry_fibo / stop_distance_fibo

                                    actual_risk_dollar_fibo = lot_size_fibo * stop_distance_fibo

                                else:

                                    actual_risk_dollar_fibo = risk_dollar_per_entry_fibo

                                    lot_size_fibo = 0



                                profit_at_tp1_fibo, rr_to_tp1_fibo = 0.0, 0.0

                                if stop_distance_fibo > 1e-9:

                                    price_diff_to_tp1 = abs(global_tp1_fibo - entry_price_fibo)

                                    

                                    if (direction_fibo == "Long" and global_tp1_fibo > entry_price_fibo) or \

                                       (direction_fibo == "Short" and global_tp1_fibo < entry_price_fibo):

                                        profit_at_tp1_fibo = lot_size_fibo * price_diff_to_tp1

                                        rr_to_tp1_fibo = price_diff_to_tp1 / stop_distance_fibo

                                        temp_fibo_rr_to_tp1_list.append(rr_to_tp1_fibo)

                                else:

                                    pass

                                

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

                                    "RR": round(rr_to_tp1_fibo, 2) if rr_to_tp1_fibo is not None else "N/A"

                                })

                        

                        entry_data_summary_sec3 = temp_fibo_entry_details_for_saving 



                        if temp_fibo_rr_to_tp1_list:

                            valid_rrs = [r for r in temp_fibo_rr_to_tp1_list if isinstance(r, (float, int)) and pd.notna(r) and r > 0]

                            summary_avg_rr = np.mean(valid_rrs) if valid_rrs else 0.0

                        else:

                            summary_avg_rr = 0.0

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

        elif n_entry_custom <=0:

            st.sidebar.warning("จำนวนไม้ (CUSTOM) ต้องมากกว่า 0")

        else:

            risk_per_trade_custom_total = active_balance_to_use * (risk_pct_custom / 100.0)

            risk_dollar_per_entry_custom = risk_per_trade_custom_total / n_entry_custom

            

            temp_custom_rr_list = []

            temp_custom_legs_for_saving = [] 

            current_total_actual_risk_custom = 0.0

            

            for i in range(int(n_entry_custom)):

                entry_str = st.session_state.get(f"custom_entry_{i}_v3", "0.00")

                sl_str = st.session_state.get(f"custom_sl_{i}_v3", "0.00")

                tp_str = st.session_state.get(f"custom_tp_{i}_v3", "0.00")



                entry_val, sl_val, tp_val = 0.0, 0.0, 0.0

                lot_custom, actual_risk_dollar_custom, rr_custom, profit_at_user_tp_custom = 0.0, 0.0, 0.0, 0.0

                

                try:

                    entry_val = float(entry_str)

                    sl_val = float(sl_str)

                    tp_val = float(tp_str)



                    if sl_val == entry_val:

                        stop_custom = 0

                    else:

                        stop_custom = abs(entry_val - sl_val)

                    

                    target_custom = abs(tp_val - entry_val)



                    if stop_custom > 1e-9:

                        lot_custom = risk_dollar_per_entry_custom / stop_custom 

                        actual_risk_dollar_custom = lot_custom * stop_custom

                        if target_custom > 1e-9 and tp_val != entry_val :

                            rr_custom = target_custom / stop_custom

                            profit_at_user_tp_custom = lot_custom * target_custom

                        temp_custom_rr_list.append(rr_custom)

                        

                        if 0 <= rr_custom < 3.0 :

                            recommended_tp_target_distance = 3 * stop_custom

                            recommended_tp_price = 0.0

                            if sl_val < entry_val:

                                recommended_tp_price = entry_val + recommended_tp_target_distance

                            elif sl_val > entry_val:

                                recommended_tp_price = entry_val - recommended_tp_target_distance

                            

                            if recommended_tp_price != 0.0:

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

                        "RR": round(rr_custom, 2) if rr_custom is not None else "N/A"

                    })



                except ValueError:

                    current_total_actual_risk_custom += risk_dollar_per_entry_custom

                    temp_custom_legs_for_saving.append({

                        "Entry": entry_str, "SL": sl_str, "TP": tp_str,

                        "Lot": "Error", "Risk $": f"{risk_dollar_per_entry_custom:.2f}", "RR": "Error"

                    })

            

            custom_entries_summary_sec3 = temp_custom_legs_for_saving 

            summary_total_risk_dollar = current_total_actual_risk_custom 



            if temp_custom_rr_list:

                valid_rrs = [r for r in temp_custom_rr_list if isinstance(r, (float, int)) and pd.notna(r) and r > 0]

                summary_avg_rr = np.mean(valid_rrs) if valid_rrs else 0.0

            else:

                summary_avg_rr = 0.0

                

    except ValueError:

        st.sidebar.warning("กรอกข้อมูล CUSTOM ไม่ถูกต้อง (ตรวจสอบจำนวนไม้)")

    except Exception as e_custom_summary:

        st.sidebar.error(f"คำนวณ CUSTOM Summary ไม่สำเร็จ: {e_custom_summary}")



display_summary_info = False

if mode == "FIBO" and entry_data_summary_sec3 and (st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", "")):

    display_summary_info = True

elif mode == "CUSTOM" and custom_entries_summary_sec3 and st.session_state.get("n_entry_custom_val_v2", 0) > 0 :

    display_summary_info = True

elif mode == "CUSTOM" and custom_tp_recommendation_messages:

    display_summary_info = True





if display_summary_info:

    current_risk_display = 0.0

    active_balance_display = active_balance_to_use



    if mode == "FIBO": current_risk_display = st.session_state.get('risk_pct_fibo_val_v2', 0.0)

    elif mode == "CUSTOM": current_risk_display = st.session_state.get('risk_pct_custom_val_v2', 0.0)



    st.sidebar.write(f"**Total Lots ({mode}):** {summary_total_lots:.2f}")

    st.sidebar.write(f"**Total Risk $ ({mode}):** {summary_total_risk_dollar:.2f} (Balance: {active_balance_display:,.2f}, Risk: {current_risk_display:.2f}%)")

    

    if summary_avg_rr > 0: 

        tp_ref_text = "(to Global TP1)" if mode == "FIBO" else "(to User TP)"

        st.sidebar.write(f"**Average RR ({mode}) {tp_ref_text}:** {summary_avg_rr:.2f}")

    else:

        st.sidebar.write(f"**Average RR ({mode}):** N/A")



    profit_ref_text = "(at Global TP1)" if mode == "FIBO" else "(at User TP)"

    st.sidebar.write(f"**Total Expected Profit {profit_ref_text} ({mode}):** {summary_total_profit_at_primary_tp:,.2f} USD")

    

    if mode == "CUSTOM" and custom_tp_recommendation_messages:

        st.sidebar.markdown("**คำแนะนำ TP (เพื่อให้ RR ≈ 3):**")

        for msg in custom_tp_recommendation_messages:

            st.sidebar.caption(msg)

else:

    show_fallback_info = True

    if mode == "FIBO" and (not st.session_state.get("swing_high_fibo_val_v2", "") or not st.session_state.get("swing_low_fibo_val_v2", "")):

        show_fallback_info = False 

    elif mode == "CUSTOM" and not (st.session_state.get("n_entry_custom_val_v2", 0) > 0 and st.session_state.get("risk_pct_custom_val_v2", 0.0) > 0):

        show_fallback_info = False

    

    if show_fallback_info:

        fibo_inputs_present = mode == "FIBO" and st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", "")

        fibo_no_levels_selected = fibo_inputs_present and not any(st.session_state.get("fibo_flags_v2", []))

        

        custom_inputs_present = mode == "CUSTOM" and st.session_state.get("n_entry_custom_val_v2",0) > 0 and st.session_state.get("risk_pct_custom_val_v2",0.0) > 0

        

        if (fibo_inputs_present and not entry_data_summary_sec3) or \

           (custom_inputs_present and not custom_entries_summary_sec3 and not custom_tp_recommendation_messages):

            st.sidebar.info("กรอกข้อมูลให้ครบถ้วนและถูกต้อง หรือเลือกเงื่อนไข (เช่น Fibo Levels) เพื่อคำนวณ Summary")



# --- End of modified SEC 2.3 (formerly SEC 3) ---



# ===================== SEC 2.4: SCALING MANAGER =======================

with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):

    scaling_step_default = 0.25

    min_risk_pct_default = 0.5

    max_risk_pct_default = 5.0

    scaling_mode_default = 'Manual'

    

    scaling_step = st.number_input(

        "Scaling Step (%)", min_value=0.01, max_value=1.0,

        value=st.session_state.get('scaling_step', scaling_step_default), 

        step=0.01, format="%.2f", key='scaling_step'

    )

    min_risk_pct = st.number_input(

        "Minimum Risk %", min_value=0.01, max_value=100.0, 

        value=st.session_state.get('min_risk_pct', min_risk_pct_default), 

        step=0.01, format="%.2f", key='min_risk_pct'

    )

    max_risk_pct = st.number_input(

        "Maximum Risk %", min_value=0.01, max_value=100.0, 

        value=st.session_state.get('max_risk_pct', max_risk_pct_default), 

        step=0.01, format="%.2f", key='max_risk_pct'

    )

    scaling_mode = st.radio(

        "Scaling Mode", ["Manual", "Auto"], 

        index=0 if st.session_state.get('scaling_mode', scaling_mode_default) == 'Manual' else 1,

        horizontal=True, key='scaling_mode'

    )



# ===================== SEC 2.4.1: SCALING SUGGESTION LOGIC =======================

df_planned_logs_for_scaling_all = load_all_planned_trade_logs_from_gsheets() 



active_portfolio_id_for_scaling = st.session_state.get('active_portfolio_id_gs', None)

df_planned_logs_for_scaling_filtered = pd.DataFrame()



if active_portfolio_id_for_scaling and not df_planned_logs_for_scaling_all.empty:

    if 'PortfolioID' in df_planned_logs_for_scaling_all.columns:

        df_planned_logs_for_scaling_filtered = df_planned_logs_for_scaling_all[

            df_planned_logs_for_scaling_all['PortfolioID'] == str(active_portfolio_id_for_scaling)

        ].copy()

    else:

        df_planned_logs_for_scaling_filtered = df_planned_logs_for_scaling_all.copy()

elif not df_planned_logs_for_scaling_all.empty:

    df_planned_logs_for_scaling_filtered = df_planned_logs_for_scaling_all.copy()



winrate_perf, gain_perf, total_trades_perf = get_performance(df_planned_logs_for_scaling_filtered.copy(), mode="week")



current_risk_for_scaling = initial_risk_pct_from_portfolio

if mode == "FIBO":

    current_risk_for_scaling = st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio)

elif mode == "CUSTOM":

    current_risk_for_scaling = st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio)



scaling_step_val = st.session_state.get('scaling_step', 0.25) 

max_risk_pct_val = st.session_state.get('max_risk_pct', 5.0)   

min_risk_pct_val = st.session_state.get('min_risk_pct', 0.5)   

current_scaling_mode = st.session_state.get('scaling_mode', 'Manual') 



suggest_risk = current_risk_for_scaling 

scaling_msg = f"Risk% ปัจจุบัน: {current_risk_for_scaling:.2f}%. "



if total_trades_perf > 0:

    gain_threshold = 0.02 * active_balance_to_use 

    if winrate_perf > 55 and gain_perf > gain_threshold:

        suggest_risk = min(current_risk_for_scaling + scaling_step_val, max_risk_pct_val)

        scaling_msg += f"🎉 ผลงานดี! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f} (เป้า {gain_threshold:,.2f}). แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}%"

    elif winrate_perf < 45 or gain_perf < 0:

        suggest_risk = max(current_risk_for_scaling - scaling_step_val, min_risk_pct_val)

        scaling_msg += f"⚠️ ควรลด Risk! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f}. แนะนำลด Risk% เป็น {suggest_risk:.2f}%"

    else:

        scaling_msg += f"คง Risk% (Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f})"

else:

    scaling_msg += "ยังไม่มีข้อมูล Performance เพียงพอในสัปดาห์นี้ หรือ Performance อยู่ในเกณฑ์"



st.sidebar.info(scaling_msg)



if abs(suggest_risk - current_risk_for_scaling) > 1e-3: 

    if current_scaling_mode == "Manual":

        if st.sidebar.button(f"ปรับ Risk% ตามคำแนะนำเป็น {suggest_risk:.2f}%"):

            if mode == "FIBO":

                st.session_state.risk_pct_fibo_val_v2 = suggest_risk 

            elif mode == "CUSTOM":

                st.session_state.risk_pct_custom_val_v2 = suggest_risk 

            st.rerun()

    elif current_scaling_mode == "Auto":

        risk_changed_by_auto = False

        if mode == "FIBO" and abs(st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio) - suggest_risk) > 1e-3:

            st.session_state.risk_pct_fibo_val_v2 = suggest_risk 

            risk_changed_by_auto = True

        elif mode == "CUSTOM" and abs(st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio) - suggest_risk) > 1e-3:

            st.session_state.risk_pct_custom_val_v2 = suggest_risk

            risk_changed_by_auto = True

        

        if risk_changed_by_auto:

            if st.session_state.get(f"last_auto_suggested_risk_{mode}", current_risk_for_scaling) != suggest_risk: 

                st.session_state[f"last_auto_suggested_risk_{mode}"] = suggest_risk

                st.toast(f"Auto Scaling: ปรับ Risk% ของโหมด {mode} เป็น {suggest_risk:.2f}%", icon="⚙️")

                st.rerun()



# ===================== SEC 2.5: SAVE PLAN ACTION & DRAWDOWN LOCK =======================

df_drawdown_check_all = load_all_planned_trade_logs_from_gsheets() 



active_portfolio_id_for_drawdown = st.session_state.get('active_portfolio_id_gs', None)

df_drawdown_check_filtered = pd.DataFrame()



if active_portfolio_id_for_drawdown and not df_drawdown_check_all.empty:

    if 'PortfolioID' in df_drawdown_check_all.columns:

        df_drawdown_check_filtered = df_drawdown_check_all[

            df_drawdown_check_all['PortfolioID'] == str(active_portfolio_id_for_drawdown)

        ].copy()

    else:

        df_drawdown_check_filtered = df_drawdown_check_all.copy()

elif not df_drawdown_check_all.empty:

    df_drawdown_check_filtered = df_drawdown_check_all.copy()



drawdown_today = get_today_drawdown(df_drawdown_check_filtered.copy(), active_balance_to_use) 

drawdown_limit_pct_val = st.session_state.get('drawdown_limit_pct', 2.0)

drawdown_limit_abs = -abs(active_balance_to_use * (drawdown_limit_pct_val / 100.0)) 



if drawdown_today < 0:

    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** <font color='red'>{drawdown_today:,.2f} USD</font>", unsafe_allow_html=True)

    st.sidebar.markdown(f"**ลิมิตขาดทุนที่ตั้งไว้:** {drawdown_limit_abs:,.2f} USD ({drawdown_limit_pct_val:.1f}% ของ {active_balance_to_use:,.2f} USD)")

else:

    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** {drawdown_today:,.2f} USD")



active_portfolio_id = st.session_state.get('active_portfolio_id_gs', None)

active_portfolio_name = st.session_state.get('active_portfolio_name_gs', None)



asset_to_save = ""

risk_pct_to_save = 0.0

direction_to_save = "N/A"

current_data_to_save = []



save_button_pressed_flag = False



if mode == "FIBO" and 'save_fibo' in st.session_state and st.session_state.save_fibo:

    save_button_pressed_flag = True

elif mode == "CUSTOM" and 'save_custom' in st.session_state and st.session_state.save_custom:

    save_button_pressed_flag = True



if mode == "FIBO":

    asset_to_save = st.session_state.get("asset_fibo_val_v2", "XAUUSD")

    risk_pct_to_save = st.session_state.get("risk_pct_fibo_val_v2", 1.0)

    direction_to_save = st.session_state.get("direction_fibo_val_v2", "Long")

    current_data_to_save = entry_data_summary_sec3

elif mode == "CUSTOM":

    asset_to_save = st.session_state.get("asset_custom_val_v2", "XAUUSD")

    risk_pct_to_save = st.session_state.get("risk_pct_custom_val_v2", 1.0)

    

    if custom_entries_summary_sec3: 

        long_count = 0

        short_count = 0

        valid_trade_count = 0

        for item in custom_entries_summary_sec3:

            try:

                entry_price_str = item.get("Entry")

                sl_price_str = item.get("SL")

                if entry_price_str is None or sl_price_str is None or \

                   str(entry_price_str).lower() == "error" or str(sl_price_str).lower() == "error":

                    continue



                entry_price = float(entry_price_str)

                sl_price = float(sl_price_str)

                

                if pd.notna(entry_price) and pd.notna(sl_price) and entry_price != sl_price:

                    valid_trade_count += 1

                    if entry_price > sl_price: 

                        long_count += 1

                    elif entry_price < sl_price: 

                        short_count += 1

            except (ValueError, TypeError):

                pass 



        if valid_trade_count > 0:

            if long_count == valid_trade_count and short_count == 0:

                direction_to_save = "Long"

            elif short_count == valid_trade_count and long_count == 0:

                direction_to_save = "Short"

            elif long_count > 0 and short_count > 0: 

                direction_to_save = "Mixed"

            elif long_count > 0: 

                 direction_to_save = "Long"

            elif short_count > 0: 

                 direction_to_save = "Short"

    current_data_to_save = custom_entries_summary_sec3



if save_button_pressed_flag:

    if not current_data_to_save:

        st.sidebar.warning(f"ไม่พบข้อมูลแผน ({mode}) ที่จะบันทึก กรุณาคำนวณแผนใน Summary ให้ถูกต้องก่อน")

    elif drawdown_today <= drawdown_limit_abs and drawdown_today != 0 :

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

                if mode == "FIBO" and 'save_fibo' in st.session_state: st.session_state.save_fibo = False

                if mode == "CUSTOM" and 'save_custom' in st.session_state: st.session_state.save_custom = False

            else:

                st.sidebar.error(f"Save ({mode}) ไปยัง Google Sheets ไม่สำเร็จ (ตรวจสอบ Headers หรือการเชื่อมต่อ)")

        except Exception as e_save_plan:

            st.sidebar.error(f"เกิดข้อผิดพลาดรุนแรงระหว่างบันทึกแผน ({mode}): {e_save_plan}")



# --- End of SEC 2.5 (formerly SEC 3.2) ---



# ===================== SEC 3: MAIN AREA - ENTRY PLAN DETAILS TABLE =======================

with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):

    if mode == "FIBO":

        col1_main, col2_main = st.columns(2)

        with col1_main:

            st.markdown("### 🎯 Entry Levels (FIBO)")

            if 'entry_data_summary_sec3' in locals() and entry_data_summary_sec3:

                try:

                    entry_df_main = pd.DataFrame(entry_data_summary_sec3)

                    expected_cols_fibo = ["Fibo Level", "Entry", "SL", "Lot", "Risk $", "TP", "RR"]

                    cols_to_display_fibo = [col for col in expected_cols_fibo if col in entry_df_main.columns]

                    if cols_to_display_fibo:

                        st.dataframe(entry_df_main[cols_to_display_fibo], hide_index=True, use_container_width=True)

                    else:

                        st.info("ไม่พบคอลัมน์ที่คาดหวังสำหรับแสดงผล Entry Levels (FIBO).")

                except Exception as e_df_fibo:

                    st.error(f"เกิดข้อผิดพลาดในการสร้างตาราง FIBO Entry Levels: {e_df_fibo}")

                    st.info("กรุณาตรวจสอบข้อมูล Input ใน Sidebar")

            else:

                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level ใน Sidebar เพื่อดู Entry Levels (หรือยังไม่มีข้อมูลสรุป).")

        

        with col2_main:

            st.markdown("### 🎯 Take Profit Zones (FIBO)")

            try:

                current_swing_high_tp_sec4 = st.session_state.get("swing_high_fibo_val_v2", "")

                current_swing_low_tp_sec4 = st.session_state.get("swing_low_fibo_val_v2", "")

                current_fibo_direction_tp_sec4 = st.session_state.get("direction_fibo_val_v2", "Long")



                if not current_swing_high_tp_sec4 or not current_swing_low_tp_sec4:

                    st.info("📌 กรอก High/Low ใน Sidebar (FIBO) ให้ครบถ้วนเพื่อคำนวณ TP.")

                else:

                    high_tp = float(current_swing_high_tp_sec4)

                    low_tp = float(current_swing_low_tp_sec4)



                    if high_tp > low_tp:

                        tp1_main, tp2_main, tp3_main = 0.0, 0.0, 0.0

                        if current_fibo_direction_tp_sec4 == "Long":

                            tp1_main = low_tp + (high_tp - low_tp) * 1.618

                            tp2_main = low_tp + (high_tp - low_tp) * 2.618

                            tp3_main = low_tp + (high_tp - low_tp) * 4.236

                        else:

                            tp1_main = high_tp - (high_tp - low_tp) * 1.618

                            tp2_main = high_tp - (high_tp - low_tp) * 2.618

                            tp3_main = high_tp - (high_tp - low_tp) * 4.236

                        

                        tp_df_main = pd.DataFrame({

                            "TP Zone": ["TP1 (1.618)", "TP2 (2.618)", "TP3 (4.236)"],

                            "Price": [f"{tp1_main:.5f}", f"{tp2_main:.5f}", f"{tp3_main:.5f}"]

                        })

                        st.dataframe(tp_df_main, hide_index=True, use_container_width=True)

                    else:

                        st.warning("📌 High ต้องมากกว่า Low เพื่อคำนวณ TP.")

            except ValueError:

                st.warning("📌 กรอก High/Low (FIBO) เป็นตัวเลขที่ถูกต้องเพื่อคำนวณ TP.")

            except Exception as e_tp_fibo:

                st.error(f"📌 เกิดข้อผิดพลาดในการคำนวณ TP (FIBO): {e_tp_fibo}")



    elif mode == "CUSTOM":

        st.markdown("### 🎯 Entry & Take Profit Zones (CUSTOM)")

        if 'custom_entries_summary_sec3' in locals() and custom_entries_summary_sec3:

            try:

                custom_df_main = pd.DataFrame(custom_entries_summary_sec3)

                expected_cols_custom = ["Entry", "SL", "TP", "Lot", "Risk $", "RR"]

                cols_to_display_custom = [col for col in expected_cols_custom if col in custom_df_main.columns]



                if cols_to_display_custom:

                     st.dataframe(custom_df_main[cols_to_display_custom], hide_index=True, use_container_width=True)

                else:

                     st.info("ไม่พบคอลัมน์ที่คาดหวังสำหรับแสดงผล CUSTOM Trades.")

                

                for i, row_data_dict in enumerate(custom_entries_summary_sec3): 

                    try:

                        rr_val_str = str(row_data_dict.get("RR", "0")).lower()

                        if rr_val_str == "error" or rr_val_str == "n/a" or rr_val_str == "" or rr_val_str == "nan":

                            continue 

                        

                        rr_val = float(rr_val_str)

                        if 0 <= rr_val < 2:

                            entry_label = row_data_dict.get("ไม้ที่", i + 1)

                            st.warning(f"🎯 Entry {entry_label} มี RR ค่อนข้างต่ำ ({rr_val:.2f}) — ลองปรับ TP/SL เพื่อ Risk:Reward ที่ดีขึ้น")

                    except ValueError: 

                        pass 

                    except Exception: 

                        pass

            except Exception as e_df_custom:

                st.error(f"เกิดข้อผิดพลาดในการสร้างตาราง CUSTOM Trades: {e_df_custom}")

                st.info("กรุณาตรวจสอบข้อมูล Input ใน Sidebar")

        else:

            st.info("กรอกข้อมูล Custom ใน Sidebar เพื่อดู Entry & TP Zones (หรือยังไม่มีข้อมูลสรุป).")



# --- End of SEC 3 (formerly SEC 4) ---



# ===================== SEC 4: MAIN AREA - CHART VISUALIZER =======================

with st.expander("📈 Chart Visualizer", expanded=False):

    asset_to_display = "OANDA:XAUUSD"

    current_asset_input_from_form = "" 



    if mode == "FIBO":

        current_asset_input_from_form = st.session_state.get("asset_fibo_val_v2", "XAUUSD") 

    elif mode == "CUSTOM":

        current_asset_input_from_form = st.session_state.get("asset_custom_val_v2", "XAUUSD") 

    

    if 'plot_data' in st.session_state and st.session_state['plot_data'] and st.session_state['plot_data'].get('Asset'):

        asset_from_log = st.session_state['plot_data'].get('Asset')

        st.info(f"กำลังแสดงกราฟ TradingView สำหรับ: {str(asset_from_log).upper()} (จาก Log Viewer)")

        asset_str_upper = str(asset_from_log).upper()

        if asset_str_upper == "XAUUSD":

            asset_to_display = "OANDA:XAUUSD"

        elif asset_str_upper == "EURUSD":

            asset_to_display = "OANDA:EURUSD"

        elif ":" not in asset_str_upper: 

            asset_to_display = f"OANDA:{asset_str_upper}" 

        else:

            asset_to_display = asset_str_upper

    elif current_asset_input_from_form:

        st.info(f"กำลังแสดงกราฟ TradingView สำหรับ: {str(current_asset_input_from_form).upper()} (จาก Input ปัจจุบัน)")

        asset_str_upper = str(current_asset_input_from_form).upper()

        if asset_str_upper == "XAUUSD":

            asset_to_display = "OANDA:XAUUSD"

        elif asset_str_upper == "EURUSD":

            asset_to_display = "OANDA:EURUSD"

        elif ":" not in asset_str_upper:

            asset_to_display = f"OANDA:{asset_str_upper}"

        else:

            asset_to_display = asset_str_upper

    else: 

        st.info(f"กำลังแสดงกราฟ TradingView สำหรับ: {asset_to_display} (ค่าเริ่มต้น)")



    tradingview_html = f"""

    <div class="tradingview-widget-container" style="height:100%;width:100%">

      <div id="tradingview_legendary" style="height:calc(100% - 32px);width:100%"></div>

      <div class="tradingview-widget-copyright">

          <a href="https://th.tradingview.com/" rel="noopener nofollow" target="_blank">

              <span class="blue-text">ติดตามตลาดทั้งหมดทาง TradingView</span>

          </a>

      </div>

      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>

      <script type="text/javascript">

      new TradingView.widget({{

        "autosize": true,

        "symbol": "{asset_to_display}",

        "interval": "15",

        "timezone": "Asia/Bangkok",

        "theme": "dark",

        "style": "1",

        "locale": "th",

        "enable_publishing": false,

        "withdateranges": true,

        "hide_side_toolbar": false,

        "allow_symbol_change": true,

        "details": true,

        "hotlist": true,

        "calendar": true,

        "container_id": "tradingview_legendary"

      }});

      </script>

    </div>

    """

    st.components.v1.html(tradingview_html, height=620)



# --- End of SEC 4 (formerly SEC 5) ---





# ===================== SEC 5: MAIN AREA - AI ASSISTANT =======================

with st.expander("🤖 AI Assistant", expanded=True):

    active_portfolio_id_ai = st.session_state.get('active_portfolio_id_gs', None)

    active_portfolio_name_ai = st.session_state.get('active_portfolio_name_gs', "ทั่วไป (ไม่ได้เลือกพอร์ต)")

    

    balance_for_ai_sim = active_balance_to_use

    report_title_suffix_planned = "(จากข้อมูลแผนเทรดทั้งหมด)"

    report_title_suffix_actual = "(จากข้อมูลผลการเทรดจริงทั้งหมด)"



    if active_portfolio_id_ai:

        report_title_suffix_planned = f"(สำหรับพอร์ต: '{active_portfolio_name_ai}' จากแผน)"

        report_title_suffix_actual = f"(สำหรับพอร์ต: '{active_portfolio_name_ai}' จากผลจริง)"

        st.info(f"AI Assistant กำลังวิเคราะห์ข้อมูลสำหรับพอร์ต: '{active_portfolio_name_ai}' (Balance เริ่มต้นจำลอง: {balance_for_ai_sim:,.2f} USD)")

    else:

        st.info(f"AI Assistant กำลังวิเคราะห์ข้อมูลจากแผนเทรดและผลการเทรดจริงทั้งหมด (ยังไม่ได้เลือก Active Portfolio - Balance เริ่มต้นจำลอง: {balance_for_ai_sim:,.2f} USD)")



    df_ai_logs_all_cached = load_all_planned_trade_logs_from_gsheets()

    df_ai_logs_to_analyze = pd.DataFrame()

    

    if active_portfolio_id_ai and not df_ai_logs_all_cached.empty:

        if 'PortfolioID' in df_ai_logs_all_cached.columns:

            df_ai_logs_to_analyze = df_ai_logs_all_cached[df_ai_logs_all_cached['PortfolioID'] == str(active_portfolio_id_ai)].copy()

    elif not df_ai_logs_all_cached.empty:

        df_ai_logs_to_analyze = df_ai_logs_all_cached.copy()



    if df_ai_logs_to_analyze.empty:

        if df_ai_logs_all_cached.empty:

             st.markdown(f"### 🧠 AI Intelligence Report {report_title_suffix_planned}")

             st.info("ยังไม่มีข้อมูลแผนเทรดใน Log (Google Sheets) สำหรับวิเคราะห์")

        elif active_portfolio_id_ai :

             st.markdown(f"### 🧠 AI Intelligence Report {report_title_suffix_planned}")

             st.info(f"ไม่พบข้อมูลแผนเทรดใน Log สำหรับพอร์ต '{active_portfolio_name_ai}'.")

    else: 

        total_trades_ai_planned = df_ai_logs_to_analyze.shape[0]

        win_trades_ai_planned = 0

        if "Risk $" in df_ai_logs_to_analyze.columns:

             win_trades_ai_planned = df_ai_logs_to_analyze[df_ai_logs_to_analyze["Risk $"] > 0].shape[0]

        winrate_ai_planned = (100 * win_trades_ai_planned / total_trades_ai_planned) if total_trades_ai_planned > 0 else 0

        

        gross_profit_ai_planned = 0.0

        if "Risk $" in df_ai_logs_to_analyze.columns:

            gross_profit_ai_planned = df_ai_logs_to_analyze["Risk $"].sum()

        

        avg_rr_ai_planned = None

        if "RR" in df_ai_logs_to_analyze.columns:

            rr_series_planned = pd.to_numeric(df_ai_logs_to_analyze["RR"], errors='coerce').dropna()

            if not rr_series_planned.empty: avg_rr_ai_planned = rr_series_planned.mean()



        max_drawdown_ai_planned = 0.0

        if "Risk $" in df_ai_logs_to_analyze.columns and not df_ai_logs_to_analyze.empty:

            df_ai_logs_sorted_for_dd_planned = df_ai_logs_to_analyze

            if "Timestamp" in df_ai_logs_to_analyze.columns and not df_ai_logs_to_analyze["Timestamp"].isnull().all():

                 df_ai_logs_sorted_for_dd_planned = df_ai_logs_to_analyze.sort_values(by="Timestamp")

            current_balance_sim_planned = balance_for_ai_sim 

            peak_balance_sim_planned = balance_for_ai_sim

            for pnl_val_planned in df_ai_logs_sorted_for_dd_planned["Risk $"]:

                if pd.notna(pnl_val_planned): 

                    current_balance_sim_planned += pnl_val_planned

                    if current_balance_sim_planned > peak_balance_sim_planned: peak_balance_sim_planned = current_balance_sim_planned

                    drawdown_val_planned = peak_balance_sim_planned - current_balance_sim_planned

                    if drawdown_val_planned > max_drawdown_ai_planned: max_drawdown_ai_planned = drawdown_val_planned

        

        win_day_ai_planned, loss_day_ai_planned = "-", "-"

        if "Timestamp" in df_ai_logs_to_analyze.columns and "Risk $" in df_ai_logs_to_analyze.columns and \

           not df_ai_logs_to_analyze["Timestamp"].isnull().all() and not df_ai_logs_to_analyze.empty:

            df_for_daily_pnl_planned = df_ai_logs_to_analyze.copy()

            if not pd.api.types.is_datetime64_any_dtype(df_for_daily_pnl_planned["Timestamp"]):

                df_for_daily_pnl_planned["Timestamp"] = pd.to_datetime(df_for_daily_pnl_planned["Timestamp"], errors='coerce')

            df_for_daily_pnl_planned.dropna(subset=["Timestamp"], inplace=True)

            if not df_for_daily_pnl_planned.empty:

                df_for_daily_pnl_planned["Weekday"] = df_for_daily_pnl_planned["Timestamp"].dt.day_name()

                daily_pnl_planned = df_for_daily_pnl_planned.groupby("Weekday")["Risk $"].sum()

                if not daily_pnl_planned.empty:

                    win_day_ai_planned = daily_pnl_planned.idxmax() if daily_pnl_planned.max() > 0 else "-"

                    loss_day_ai_planned = daily_pnl_planned.idxmin() if daily_pnl_planned.min() < 0 else "-"



        st.markdown(f"### 📝 AI Intelligence Report {report_title_suffix_planned}")

        st.write(f"- **จำนวนแผนเทรดที่วิเคราะห์:** {total_trades_ai_planned:,}")

        st.write(f"- **Winrate (ตามแผน):** {winrate_ai_planned:.2f}%")

        st.write(f"- **กำไร/ขาดทุนสุทธิ (ตามแผน):** {gross_profit_ai_planned:,.2f} USD")

        st.write(f"- **RR เฉลี่ย (ตามแผน):** {avg_rr_ai_planned:.2f}" if avg_rr_ai_planned is not None else "N/A")

        st.write(f"- **Max Drawdown (จำลองจากแผน):** {max_drawdown_ai_planned:,.2f} USD")

        st.write(f"- **วันที่ทำกำไรดีที่สุด (ตามแผน):** {win_day_ai_planned}")

        st.write(f"- **วันที่ขาดทุนมากที่สุด (ตามแผน):** {loss_day_ai_planned}")

        st.markdown("#### 🤖 AI Insight (จากแผนเทรด)")

        insight_messages_planned = []

        if total_trades_ai_planned > 0 : 

            if winrate_ai_planned >= 60: insight_messages_planned.append("✅ Winrate (ตามแผน) สูง: ระบบการวางแผนมีแนวโน้มที่ดี")

            elif winrate_ai_planned < 40 and total_trades_ai_planned >=10 : insight_messages_planned.append("⚠️ Winrate (ตามแผน) ต่ำ: ควรทบทวนกลยุทธ์การวางแผน")

            if avg_rr_ai_planned is not None and avg_rr_ai_planned < 1.5 and total_trades_ai_planned >=5 : insight_messages_planned.append("📉 RR เฉลี่ย (ตามแผน) ต่ำกว่า 1.5: อาจต้องพิจารณาการตั้ง TP/SL เพื่อ Risk:Reward ที่เหมาะสมขึ้น")

            if balance_for_ai_sim > 0 and max_drawdown_ai_planned > (balance_for_ai_sim * 0.10) : insight_messages_planned.append(f"🚨 Max Drawdown (จำลองจากแผน) {max_drawdown_ai_planned:,.2f} USD ค่อนข้างสูง ({ (max_drawdown_ai_planned/balance_for_ai_sim)*100:.1f}% ของ Balance): ควรระมัดระวัง")

        if not insight_messages_planned and total_trades_ai_planned > 0: insight_messages_planned = ["ดูเหมือนว่าข้อมูลแผนเทรดที่วิเคราะห์ยังไม่มีจุดที่น่ากังวลเป็นพิเศษ"]

        for msg in insight_messages_planned:

            if "✅" in msg: st.success(msg)

            elif "⚠️" in msg or "📉" in msg: st.warning(msg)

            elif "🚨" in msg: st.error(msg)

            else: st.info(msg)



    st.markdown("---")



    df_actual_trades_all = load_actual_trades_from_gsheets()

    df_actual_trades_to_analyze = pd.DataFrame()



    if active_portfolio_id_ai and not df_actual_trades_all.empty:

        if 'PortfolioID' in df_actual_trades_all.columns:

            df_actual_trades_to_analyze = df_actual_trades_all[df_actual_trades_all['PortfolioID'] == str(active_portfolio_id_ai)].copy()

    elif not df_actual_trades_all.empty:

        df_actual_trades_to_analyze = df_actual_trades_all.copy()



    st.markdown(f"### 📈 AI Intelligence Report {report_title_suffix_actual}")

    if df_actual_trades_to_analyze.empty:

        if df_actual_trades_all.empty :

             st.info("ยังไม่มีข้อมูลผลการเทรดจริงใน Log (Google Sheets) สำหรับวิเคราะห์")

        elif active_portfolio_id_ai:

             st.info(f"ไม่พบข้อมูลผลการเทรดจริงใน Log สำหรับพอร์ต '{active_portfolio_name_ai}'.")

    else:

        if 'Profit_Deal' not in df_actual_trades_to_analyze.columns:

            st.warning("ไม่พบคอลัมน์ 'Profit_Deal' ในข้อมูลผลการเทรดจริง ไม่สามารถคำนวณสถิติได้")

        else:

            if 'Type_Deal' in df_actual_trades_to_analyze.columns:

                df_trading_deals = df_actual_trades_to_analyze[

                    ~df_actual_trades_to_analyze['Type_Deal'].astype(str).str.lower().isin(['balance', 'credit'])

                ].copy()

            else:

                df_trading_deals = df_actual_trades_to_analyze.copy()



            if df_trading_deals.empty:

                st.info("ไม่พบรายการ Deals ที่เป็นการซื้อขายจริงสำหรับวิเคราะห์")

            else:

                actual_total_deals = len(df_trading_deals)

                actual_winning_deals_df = df_trading_deals[df_trading_deals['Profit_Deal'] > 0]

                actual_losing_deals_df = df_trading_deals[df_trading_deals['Profit_Deal'] < 0]

                

                actual_winning_deals_count = len(actual_winning_deals_df)

                actual_losing_deals_count = len(actual_losing_deals_df)



                actual_win_rate = (100 * actual_winning_deals_count / actual_total_deals) if actual_total_deals > 0 else 0

                

                actual_gross_profit = actual_winning_deals_df['Profit_Deal'].sum()

                actual_gross_loss = abs(actual_losing_deals_df['Profit_Deal'].sum())



                actual_profit_factor = actual_gross_profit / actual_gross_loss if actual_gross_loss > 0 else float('inf') if actual_gross_profit > 0 else 0

                

                actual_avg_profit_deal = actual_gross_profit / actual_winning_deals_count if actual_winning_deals_count > 0 else 0

                actual_avg_loss_deal = actual_gross_loss / actual_losing_deals_count if actual_losing_deals_count > 0 else 0

                

                st.write(f"- **จำนวน Deals ที่วิเคราะห์ (ผลจริง):** {actual_total_deals:,}")

                st.write(f"- **Deal-Level Win Rate (ผลจริง):** {actual_win_rate:.2f}%")

                st.write(f"- **กำไรทั้งหมด (Gross Profit - ผลจริง):** {actual_gross_profit:,.2f} USD")

                st.write(f"- **ขาดทุนทั้งหมด (Gross Loss - ผลจริง):** {actual_gross_loss:,.2f} USD")

                st.write(f"- **Profit Factor (Deal-Level - ผลจริง):** {actual_profit_factor:.2f}" if actual_profit_factor != float('inf') else "∞ (No Losses)")

                st.write(f"- **กำไรเฉลี่ยต่อ Deal ที่ชนะ (ผลจริง):** {actual_avg_profit_deal:,.2f} USD")

                st.write(f"- **ขาดทุนเฉลี่ยต่อ Deal ที่แพ้ (ผลจริง):** {actual_avg_loss_deal:,.2f} USD")



                st.markdown("#### 🤖 AI Insight (จากผลการเทรดจริง)")

                insight_messages_actual = []

                if actual_total_deals > 0:

                    if actual_win_rate >= 50: insight_messages_actual.append("✅ Win Rate (ผลจริง) อยู่ในเกณฑ์ดี")

                    else: insight_messages_actual.append("📉 Win Rate (ผลจริง) ควรปรับปรุง")

                    if actual_profit_factor > 1.5: insight_messages_actual.append("📈 Profit Factor (ผลจริง) อยู่ในระดับที่ดี")

                    elif actual_profit_factor < 1 and actual_total_deals > 10: insight_messages_actual.append("⚠️ Profit Factor (ผลจริง) ต่ำกว่า 1 บ่งชี้ว่าขาดทุนมากกว่ากำไร ควรทบทวนกลยุทธ์")

                

                if not insight_messages_actual and actual_total_deals > 0 : insight_messages_actual = ["ข้อมูลผลการเทรดจริงกำลังถูกรวบรวม โปรดตรวจสอบ Insights เพิ่มเติมในอนาคต"]

                elif not actual_total_deals > 0 : insight_messages_actual = ["ยังไม่มีข้อมูลผลการเทรดจริงเพียงพอสำหรับการสร้าง Insight"]



                for msg in insight_messages_actual:

                    if "✅" in msg or "📈" in msg : st.success(msg)

                    elif "⚠️" in msg or "📉" in msg: st.warning(msg)

                    else: st.info(msg)



# --- End of SEC 5 (formerly SEC 6) ---



# ===================== SEC 6: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================

with st.expander("📂  Ultimate Chart Dashboard Import & Processing", expanded=True):

    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")



    # --- ฟังก์ชันสำหรับแยกข้อมูลจากเนื้อหาไฟล์ Statement (CSV) ---

    def extract_data_from_report_content(file_content_str_input):

        extracted_data = {'deals': pd.DataFrame(), 'orders': pd.DataFrame(), 'positions': pd.DataFrame(), 'balance_summary': {}, 'results_summary': {}}



        # Function to safely convert values to float (from mainโหลดได้หมด.py's logic)

        def safe_float_convert(value_str):

            if isinstance(value_str, (int, float)):

                return value_str

            try:

                # Remove spaces, commas, and percentage signs

                clean_value = str(value_str).strip().replace(" ", "").replace(",", "").replace("%", "")

                if clean_value.count('.') > 1: # Handle cases like "1.234.56"

                    parts = clean_value.split('.'); integer_part = "".join(parts[:-1]); decimal_part = parts[-1]

                    clean_value = integer_part + "." + decimal_part

                if not clean_value:

                    return None

                return float(clean_value)

            except (ValueError, TypeError, AttributeError):

                return None



        lines = []

        if isinstance(file_content_str_input, str):

            lines = file_content_str_input.strip().split('\n')

        elif isinstance(file_content_str_input, bytes):

            lines = file_content_str_input.decode('utf-8', errors='replace').strip().split('\n')

        else:

            print("Error: Invalid file_content type in extract_data_from_report_content.")

            return extracted_data

        

        if not lines:

            print("Warning: File content is empty in extract_data_from_report_content.")

            return extracted_data



        # Section keywords for identifying data blocks (from mainโหลดได้หมด.py's logic)

        section_keywords_for_structure = ["Positions", "Orders", "Deals", "History", "Results", "Balance"]

        section_starts = {}



        for i, line in enumerate(lines):

            for keyword in section_keywords_for_structure:

                if keyword not in section_starts and keyword in line:

                    # Special handling for "Deals" section, as "History" might be its keyword in some reports

                    actual_key = "Deals" if keyword == "History" else keyword

                    if actual_key not in section_starts: # Only record the first occurrence

                        section_starts[actual_key] = i

                    break # Move to next line after finding a keyword



        # Define raw headers and expected cleaned column names for table sections

        section_raw_headers = {

            "Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit",

            "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment",

            "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment",

        }

        

        expected_cleaned_columns = {

            "Positions": ["Time_Pos", "Position_ID", "Symbol_Pos", "Type_Pos", "Volume_Pos", "Price_Open_Pos", "S_L_Pos", "T_P_Pos", "Time_Close_Pos", "Price_Close_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos"],

            "Orders": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Filler_Ord","Comment_Ord"], # Keeping Filler for consistency with typical structure

            "Deals": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal"],

        }

        

        section_order_for_tables = ["Positions", "Orders", "Deals"]



        # 1. Parse each table section (Positions, Orders, Deals)

        for table_idx, section_name in enumerate(section_order_for_tables):

            section_key_lower = section_name.lower()

            extracted_data[section_key_lower] = pd.DataFrame() # Initialize with empty DataFrame



            if section_name in section_starts:

                start_row_idx = section_starts[section_name]

                header_row_idx = start_row_idx + 1 # Assuming header is always 1 line after section keyword



                # Find actual header row (skip empty lines if any)

                while header_row_idx < len(lines) and not lines[header_row_idx].strip():

                    header_row_idx += 1



                if header_row_idx >= len(lines):

                    if st.session_state.get("debug_statement_processing_v2", False):

                        st.warning(f"DEBUG: Could not find header row for {section_name} after keyword.")

                    continue # Skip if no header found



                headers_raw = lines[header_row_idx].strip().split(',')

                # Clean headers by stripping and removing empty strings, and handle duplicates (e.g. from merged cells)

                headers_cleaned = [h.strip() for h in headers_raw if h.strip()]

                

                # Check for duplicates and make unique, e.g., by appending numbers

                seen = {}

                headers_final = []

                for h in headers_cleaned:

                    if h in seen:

                        seen[h] += 1

                        headers_final.append(f"{h}_{seen[h]}")

                    else:

                        seen[h] = 1

                        headers_final.append(h)





                data_start_row = header_row_idx + 1

                

                # Determine where data for current table ends

                data_end_row = len(lines)

                for next_table_name_idx in range(table_idx + 1, len(section_order_for_tables)):

                    next_section_name_candidate = section_order_for_tables[next_table_name_idx]

                    if next_section_name_candidate in section_starts:

                        data_end_row = section_starts[next_section_name_candidate]

                        break

                

                current_table_data_lines = []

                for line_num in range(data_start_row, data_end_row):

                    line_content = lines[line_num].strip()

                    if not line_content: # Empty line, might be end of data

                        if any(current_table_data_lines): # If we have collected data, this blank line marks end

                            break

                        else: # Skip leading blank lines after header

                            continue



                    # Heuristic: If line starts looking like a summary or a different section header, stop.

                    if line_content.startswith(("Balance:", "Credit Facility:", "Floating P/L:", "Equity:", "Results", "Total Net Profit:")):

                        break

                    is_another_header = False

                    for other_sec_name, other_raw_hdr_template in section_raw_headers.items():

                        if other_sec_name != section_name and line_content.startswith(other_raw_hdr_template.split(',')[0].strip()) and other_raw_hdr_template in line_content:

                            is_another_header = True

                            break

                    if is_another_header:

                        break



                    # Special handling for Deals/Balance/Credit rows that are part of the Deals table but are summary-like

                    if section_name == "Deals":

                        parts_of_line = [p.strip().lower() for p in line_content.split(',')]

                        if len(parts_of_line) > 3 and parts_of_line[3] in ['balance', 'credit', 'initial_deposit']:

                            if st.session_state.get("debug_statement_processing_v2", False):

                                print(f"DEBUG [extract_data]: Skipping summary-like row in Deals: '{line_content}'")

                            continue # Skip these lines as they are not actual trades



                    current_table_data_lines.append(line_content)



                if current_table_data_lines:

                    csv_data_str = "\n".join(current_table_data_lines)

                    try:

                        df_section = pd.read_csv(io.StringIO(csv_data_str),

                                                 header=None,

                                                 names=headers_final, # Use the dynamic headers

                                                 skipinitialspace=True,

                                                 on_bad_lines='warn',

                                                 engine='python')

                        df_section.dropna(how='all', inplace=True)

                        if not df_section.empty:

                            extracted_data[section_key_lower] = df_section

                    except Exception as e_parse_df:

                        if st.session_state.get("debug_statement_processing_v2", False):

                            st.error(f"Error parsing table data for {section_name}: {e_parse_df}")

                            st.text(f"Problematic CSV data for {section_name}:\n{csv_data_str[:500]}")





        # --- Extract Balance Summary (Equity, Free Margin, etc.) ---

        balance_summary_dict = {}

        balance_section_start_line = -1



        # Search for the "Balance:" keyword (more robustly)

        for i, line in enumerate(lines):

            if "Balance:" in line: # Use "in" for more flexibility

                balance_section_start_line = i

                break

        

        if balance_section_start_line != -1:

            for i in range(balance_section_start_line, min(balance_section_start_line + 10, len(lines))): # Check next 10 lines

                line_stripped = lines[i].strip()

                if not line_stripped: continue

                if line_stripped.startswith(("Results", "Total Net Profit:")): break # Stop if results section begins



                # Specific parsing for Balance and Equity lines based on your format

                # Example: "Balance:,,,4 708.36,,,Free Margin:,,,4 708.36,,,,"

                # Example: "Equity:,,,4 708.36,,,,,,,,,"

                if "Balance:" in line_stripped:

                    parts = line_stripped.split(',')

                    # Find the first non-empty, convertable value after "Balance:"

                    for p in parts[1:]: # Start from the part after "Balance:"

                        val = safe_float_convert(p)

                        if val is not None:

                            balance_summary_dict['balance'] = val

                            break

                elif "Equity:" in line_stripped:

                    parts = line_stripped.split(',')

                    # Find the first non-empty, convertable value after "Equity:"

                    for p in parts[1:]:

                        val = safe_float_convert(p)

                        if val is not None:

                            balance_summary_dict['equity'] = val

                            break

                # Generic parsing for other summary fields (Free Margin, Credit Facility etc.)

                parts_with_colon = [p.strip() for p in line_stripped.split(',') if ':' in p]

                for part in parts_with_colon:

                    key_part, val_part = part.split(':', 1)

                    key_clean = key_part.strip().lower().replace(" ", "_").replace(".", "")

                    val_clean = val_part.strip()

                    if val_clean:

                        numeric_val = safe_float_convert(val_clean.split(' ')[0]) # Take first word before space

                        if numeric_val is not None:

                            balance_summary_dict[key_clean] = numeric_val



        # Ensure essential keys are present, defaulting to 0.0 if not found

        essential_balance_keys = ["balance", "credit_facility", "floating_p_l", "equity", "free_margin", "margin", "margin_level"]

        for k_b in essential_balance_keys:

            if k_b not in balance_summary_dict:

                balance_summary_dict[k_b] = 0.0 # Default to 0.0 if not found



        extracted_data['balance_summary'] = balance_summary_dict

        

        # --- Extract Results Summary (Total Net Profit, Profit Factor, etc.) ---

        results_summary_dict = {}

        results_section_start_line = -1



        for i_res, line_res in enumerate(lines):

            if "Results" in line_res or "Total Net Profit:" in line_res:

                results_section_start_line = i_res

                break



        if results_section_start_line != -1:

            stat_definitions_map = { # Keeping this map as it was, it's robust

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

                "Maximal consecutive loss (count)": "Maximal_consecutive_loss_Count",

                "Average consecutive losses": "Average_consecutive_losses"

            }

            max_lines_to_read = 25 # Safety limit



            for i_res_line in range(results_section_start_line, min(results_section_start_line + max_lines_to_read, len(lines))):

                line_stripped_res = lines[i_res_line].strip()

                if not line_stripped_res: continue



                # Try to parse key-value pairs separated by comma for results

                # This needs to be robust for varied formatting

                parts = line_stripped_res.split(',')

                for part_idx, part_content in enumerate(parts):

                    content_clean = part_content.strip()

                    if not content_clean: continue



                    # Check if it's a known label (e.g., "Total Net Profit:")

                    label_to_check = content_clean.replace(':', '')

                    if label_to_check in stat_definitions_map:

                        gsheet_key = stat_definitions_map[label_to_check]

                        

                        # Search for value in the next few parts of the same line

                        for val_search_idx in range(1, 4): # Check next 1, 2, or 3 parts

                            if (part_idx + val_search_idx) < len(parts):

                                raw_value_part = parts[part_idx + val_search_idx].strip()

                                if raw_value_part:

                                    value_before_paren = raw_value_part.split('(')[0].strip()

                                    numeric_value = safe_float_convert(value_before_paren)

                                    if numeric_value is not None:

                                        results_summary_dict[gsheet_key] = numeric_value

                                        

                                        # Handle parenthetical values (e.g. percentages, counts)

                                        if '(' in raw_value_part and ')' in raw_value_part:

                                            paren_content = raw_value_part[raw_value_part.find('(')+1:raw_value_part.find(')')].strip().replace('%','')

                                            paren_numeric = safe_float_convert(paren_content)

                                            if paren_numeric is not None:

                                                # Assign composite keys (e.g., Balance_Drawdown_Maximal_Percent)

                                                if label_to_check == "Balance Drawdown Maximal": results_summary_dict["Balance_Drawdown_Maximal_Percent"] = paren_numeric

                                                elif label_to_check == "Balance Drawdown Relative": results_summary_dict["Balance_Drawdown_Relative_Amount"] = paren_numeric # Amount for Relative DD

                                                elif label_to_check == "Short Trades (won %)": results_summary_dict["Short_Trades_won_Percent"] = paren_numeric

                                                elif label_to_check == "Long Trades (won %)": results_summary_dict["Long_Trades_won_Percent"] = paren_numeric

                                                elif label_to_check == "Profit Trades (% of total)": results_summary_dict["Profit_Trades_Percent_of_total"] = paren_numeric

                                                elif label_to_check == "Loss Trades (% of total)": results_summary_dict["Loss_Trades_Percent_of_total"] = paren_numeric

                                                elif label_to_check == "Maximum consecutive wins ($)": results_summary_dict["Maximum_consecutive_wins_Profit"] = paren_numeric

                                                elif label_to_check == "Maximal consecutive profit (count)": results_summary_dict["Maximal_consecutive_profit_Count"] = paren_numeric

                                                elif label_to_check == "Maximum consecutive losses ($)": results_summary_dict["Maximum_consecutive_losses_Profit"] = paren_numeric

                                                elif label_to_check == "Maximal consecutive loss (count)": results_summary_dict["Maximal_consecutive_loss_Count"] = paren_numeric

                                        break # Value found for this label, move to next label

                

                if line_stripped_res.startswith("Average consecutive losses"): break # Common end marker

        

        extracted_data['results_summary'] = results_summary_dict



        # Debug print for parsed data

        if st.session_state.get("debug_statement_processing_v2", False):

            st.subheader("DEBUG: Final Parsed Summaries (after extract_data_from_report_content)")

            st.write("Balance Summary (Equity, Free Margin, etc.):")

            st.json(balance_summary_dict if balance_summary_dict else "Balance summary not parsed or empty.")

            st.write("Results Summary (Profit Factor, Trades, etc.):")

            st.json(results_summary_dict if results_summary_dict else "Results summary not parsed or empty.")



        return extracted_data



    # --- ฟังก์ชันสำหรับบันทึก Deals ลงในชีท ActualTrades ---

    def save_deals_to_actual_trades(sh, df_deals, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):

        if df_deals is None or df_deals.empty:

            if st.session_state.get("debug_statement_processing_v2", False):

                st.info("DEBUG: No Deals data to save for this call.")

            return True # Consider as success if no data to save

        try:

            ws = sh.worksheet(WORKSHEET_ACTUAL_TRADES)

            expected_headers = [

                "Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P",

                "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos",

                "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"

            ]

            

            # Auto-create/update headers if needed

            current_headers = []

            if ws.row_count > 0: current_headers = ws.row_values(1)

            if not current_headers or all(h == "" for h in current_headers) or set(current_headers) != set(expected_headers): ws.update([expected_headers])



            # Prepare DataFrame for saving, ensuring all expected headers are present

            df_deals_to_save = pd.DataFrame(columns=expected_headers)

            for col in expected_headers:

                if col in df_deals.columns:

                    df_deals_to_save[col] = df_deals[col]

                else:

                    df_deals_to_save[col] = None # Fill missing columns with None/NaN



            # Add system-generated columns

            df_deals_to_save["PortfolioID"] = str(portfolio_id)

            df_deals_to_save["PortfolioName"] = str(portfolio_name)

            df_deals_to_save["SourceFile"] = str(source_file_name)

            df_deals_to_save["ImportBatchID"] = str(import_batch_id)

            

            # Convert all data to string to avoid gspread type issues

            list_of_lists = df_deals_to_save.astype(str).replace('nan', '').fillna('').values.tolist()

            

            if list_of_lists:

                 ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')

                 return True

            return False

        except gspread.exceptions.WorksheetNotFound:

            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_TRADES}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")

            return False

        except Exception as e:

            st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Deals: {e}"); st.exception(e); return False



    # --- ฟังก์ชันสำหรับบันทึก Positions ลงในชีท ActualPositions ---

    def save_positions_to_gsheets(sh, df_positions, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):

        if df_positions is None or df_positions.empty:

            if st.session_state.get("debug_statement_processing_v2", False):

                st.info("DEBUG: No Positions data to save for this call.")

            return True

        try:

            ws = sh.worksheet(WORKSHEET_ACTUAL_POSITIONS)

            expected_headers = [

                "Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P",

                "Close_Time_Pos", "Close_Price_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos",

                "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"

            ]

            current_headers = []

            if ws.row_count > 0: current_headers = ws.row_values(1)

            if not current_headers or all(h == "" for h in current_headers) or set(current_headers) != set(expected_headers): ws.update([expected_headers])



            df_positions_to_save = pd.DataFrame(columns=expected_headers)

            for col in expected_headers:

                if col in df_positions.columns:

                    df_positions_to_save[col] = df_positions[col]

                else:

                    df_positions_to_save[col] = None



            df_positions_to_save["PortfolioID"] = str(portfolio_id)

            df_positions_to_save["PortfolioName"] = str(portfolio_name)

            df_positions_to_save["SourceFile"] = str(source_file_name)

            df_positions_to_save["ImportBatchID"] = str(import_batch_id)

            

            list_of_lists = df_positions_to_save.astype(str).replace('nan', '').fillna('').values.tolist()

            if list_of_lists:

                ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')

                return True

            return False

        except gspread.exceptions.WorksheetNotFound:

            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_POSITIONS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")

            return False

        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Positions: {e}"); st.exception(e); return False



    # --- ฟังก์ชันสำหรับบันทึก Orders ลงในชีท ActualOrders ---

    def save_orders_to_gsheets(sh, df_orders, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):

        if df_orders is None or df_orders.empty:

            if st.session_state.get("debug_statement_processing_v2", False):

                st.info("DEBUG: No Orders data to save for this call.")

            return True

        try:

            ws = sh.worksheet(WORKSHEET_ACTUAL_ORDERS)

            expected_headers = [

                "Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord",

                "Close_Time_Ord", "State_Ord", "Comment_Ord", # Adjusted to match fewer columns in provided report

                "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"

            ]

            current_headers = []

            if ws.row_count > 0: current_headers = ws.row_values(1)

            if not current_headers or all(h == "" for h in current_headers) or set(current_headers) != set(expected_headers): ws.update([expected_headers])



            df_orders_to_save = pd.DataFrame(columns=expected_headers)

            for col in expected_headers:

                if col in df_orders.columns:

                    df_orders_to_save[col] = df_orders[col]

                else:

                    df_orders_to_save[col] = None

            

            df_orders_to_save["PortfolioID"] = str(portfolio_id)

            df_orders_to_save["PortfolioName"] = str(portfolio_name)

            df_orders_to_save["SourceFile"] = str(source_file_name)

            df_orders_to_save["ImportBatchID"] = str(import_batch_id)



            list_of_lists = df_orders_to_save.astype(str).replace('nan', '').fillna('').values.tolist()

            if list_of_lists:

                ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')

                return True

            return False

        except gspread.exceptions.WorksheetNotFound:

            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_ORDERS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")

            return False

        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Orders: {e}"); st.exception(e); return False

        

    # --- ฟังก์ชันสำหรับบันทึก Results Summary ลงในชีท StatementSummaries ---

    def save_results_summary_to_gsheets(sh, balance_summary_data, results_summary_data, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):

        try:

            ws = sh.worksheet(WORKSHEET_STATEMENT_SUMMARIES)

            expected_headers = [

                "Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID",

                "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Credit_Facility",

                "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", 

                "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", 

                "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", 

                "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount",

                "Total_Trades", "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", 

                "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", 

                "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", 

                "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", 

                "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count",

                "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", 

                "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count",

                "Average_consecutive_wins", "Average_consecutive_losses"

            ]

            

            current_headers_ws = []

            if ws.row_count > 0: current_headers_ws = ws.row_values(1)

            if not current_headers_ws or all(h == "" for h in current_headers_ws) or set(current_headers_ws) != set(expected_headers): ws.update([expected_headers])



            row_data_to_save = {h: None for h in expected_headers} # Initialize with None

            row_data_to_save.update({

                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),

                "PortfolioID": str(portfolio_id),

                "PortfolioName": str(portfolio_name),

                "SourceFile": str(source_file_name),

                "ImportBatchID": str(import_batch_id) # Add ImportBatchID for summaries too

            })

            

            # Populate from balance_summary_data

            if isinstance(balance_summary_data, dict):

                for key, value in balance_summary_data.items():

                    key_mapped = key.replace("_", " ").title().replace(" ", "_") # Try to map to original header

                    if key == "balance": row_data_to_save["Balance"] = value

                    elif key == "equity": row_data_to_save["Equity"] = value

                    elif key == "free_margin": row_data_to_save["Free_Margin"] = value

                    elif key == "margin": row_data_to_save["Margin"] = value

                    elif key == "floating_p_l": row_data_to_save["Floating_P_L"] = value

                    elif key == "margin_level": row_data_to_save["Margin_Level"] = value

                    elif key == "credit_facility": row_data_to_save["Credit_Facility"] = value





            # Populate from results_summary_data

            if isinstance(results_summary_data, dict):

                for gsheet_key, val_res in results_summary_data.items():

                    if gsheet_key in expected_headers:

                        row_data_to_save[gsheet_key] = val_res

            

            final_row_values = [str(row_data_to_save.get(h, "")).strip() for h in expected_headers]

            

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



    st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้)", value=False, key="debug_statement_processing_v2")

    

    active_portfolio_id_for_actual = st.session_state.get('active_portfolio_id_gs', None)

    active_portfolio_name_for_actual = st.session_state.get('active_portfolio_name_gs', None)



    if uploaded_file_statement:

        file_name_for_saving = uploaded_file_statement.name

        

        # --- NEW: Add FileHash for Deduplication ---

        file_hash_for_saving = ""

        try:

            uploaded_file_statement.seek(0) # Reset pointer

            file_content_bytes_for_hash = uploaded_file_statement.read()

            uploaded_file_statement.seek(0) # Reset pointer again

            file_hash_for_saving = hashlib.md5(file_content_bytes_for_hash).hexdigest()

        except Exception as e_hash:

            file_hash_for_saving = f"hash_error_{random.randint(10000,99999)}"

            print(f"Warning: Could not compute MD5 hash for file {file_name_for_saving}: {e_hash}")

        # --- END NEW ---



        # Check for previous successful uploads of the same file

        previously_successfully_processed = False

        if active_portfolio_id_for_actual: # Only check for duplicates if a portfolio is selected

            gc_history = get_gspread_client()

            if gc_history:

                try:

                    sh_history = gc_history.open(GOOGLE_SHEET_NAME)

                    ws_upload_history = sh_history.worksheet(WORKSHEET_UPLOAD_HISTORY)

                    

                    history_records = ws_upload_history.get_all_records(numericise_ignore=['all']) # Read all as string to compare hash/size

                    for record in history_records:

                        try:

                            record_file_size_val = int(float(str(record.get("FileSize","0")).replace(",","")))

                        except ValueError:

                            record_file_size_val = 0 # Default to 0 if conversion fails



                        if str(record.get("PortfolioID","")) == str(active_portfolio_id_for_actual) and \

                           record.get("FileName","") == file_name_for_saving and \

                           record_file_size_val == uploaded_file_statement.size and \

                           record.get("FileHash","") == file_hash_for_saving and \

                           str(record.get("Status","")).startswith("Success"):

                            previously_successfully_processed = True

                            break

                except gspread.exceptions.WorksheetNotFound:

                    print(f"Warning: Upload history worksheet '{WORKSHEET_UPLOAD_HISTORY}' not found. Cannot check for duplicates.")

                except Exception as e_hist_read:

                    print(f"Warning: Error reading upload history for duplicate check: {e_hist_read}")

            else:

                print("Warning: GSpread client not available for upload history check.")





        if previously_successfully_processed:

            st.warning(f"⚠️ ไฟล์ '{file_name_for_saving}' นี้ เคยถูกประมวลผลสำเร็จสำหรับพอร์ต '{active_portfolio_name_for_actual}' ไปแล้ว และข้อมูลได้ถูกบันทึกเรียบร้อย จะไม่ดำเนินการใดๆ ซ้ำอีก")

        else: # Proceed with processing only if not previously successful for this portfolio

            import_batch_id = str(uuid.uuid4())

            current_upload_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")



            initial_log_success = False

            gc_log_init = get_gspread_client()

            if gc_log_init:

                try:

                    sh_log_init = gc_log_init.open(GOOGLE_SHEET_NAME)

                    ws_upload_history_init = sh_log_init.worksheet(WORKSHEET_UPLOAD_HISTORY)

                    # Ensure headers are correct for UploadHistory

                    expected_upload_history_headers = ["UploadTimestamp", "PortfolioID", "PortfolioName", "FileName", "FileSize", "FileHash", "Status", "ImportBatchID", "Notes"]

                    if ws_upload_history_init.row_count == 0 or set(ws_upload_history_init.row_values(1)) != set(expected_upload_history_headers):

                        ws_upload_history_init.update([expected_upload_history_headers])



                    ws_upload_history_init.append_row([

                        current_upload_timestamp, str(active_portfolio_id_for_actual), str(active_portfolio_name_for_actual),

                        file_name_for_saving, uploaded_file_statement.size, file_hash_for_saving,

                        "Processing", import_batch_id, "Attempting to process new/previously failed file."

                    ])

                    initial_log_success = True

                except Exception as e_log_init:

                    st.error(f"ไม่สามารถบันทึก Log เริ่มต้นใน {WORKSHEET_UPLOAD_HISTORY}: {e_log_init}")



            if initial_log_success:

                st.markdown(f"--- \n**Import Batch ID: `{import_batch_id}`**")

                st.info(f"กำลังประมวลผลไฟล์ (ใหม่/เคยล้มเหลว): {file_name_for_saving}")



                processing_had_errors = False

                final_status_for_history = "Failed_Unknown"

                final_processing_notes = []



                try:

                    uploaded_file_statement.seek(0)

                    file_content_bytes = uploaded_file_statement.getvalue()

                    file_content_str = file_content_bytes.decode("utf-8", errors="replace")

                    

                    with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {file_name_for_saving}..."):

                        # THIS IS THE CORE CALL to the updated extraction function

                        extracted_sections = extract_data_from_report_content(file_content_str)



                    # --- DEBUG: Show extracted balance_summary before saving ---

                    st.sidebar.markdown("---")

                    st.sidebar.info(f"DEBUG: Extracted Balance Summary (Pre-Save): {extracted_sections.get('balance_summary', {})}")

                    print(f"DEBUG Console: Extracted Balance Summary (Pre-Save): {extracted_sections.get('balance_summary', {})}")

                    st.sidebar.markdown("---")

                    # --- END DEBUG ---



                    if st.session_state.get("debug_statement_processing_v2", False):

                        st.subheader("DEBUG: Extracted Sections (Details)")

                        if extracted_sections:

                            for section_name, data_item in extracted_sections.items():

                                st.write(f"#### {section_name.replace('_',' ').title()}")

                                if isinstance(data_item, pd.DataFrame):

                                    if not data_item.empty:

                                        st.dataframe(data_item.head())

                                    else:

                                        st.info(f"DataFrame for {section_name.replace('_',' ').title()} is empty.")

                                elif isinstance(data_item, dict):

                                    st.json(data_item if data_item else f"Dictionary for {section_name} is empty.")

                                else:

                                    st.write(data_item if data_item is not None else f"Data for {section_name} is None.")

                        else:

                            st.warning("No sections extracted from file.")





                    if not active_portfolio_id_for_actual:

                        st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.")

                        processing_had_errors = True

                    elif not extracted_sections:

                        st.error("ไม่สามารถประมวลผลข้อมูลจากไฟล์ Statement ได้ กรุณาตรวจสอบไฟล์หรือโหมด Debug")

                        processing_had_errors = True

                    else: # If portfolio is selected and extraction succeeded

                        st.markdown("---")

                        st.subheader("💾 กำลังบันทึกข้อมูลไปยัง Google Sheets...")

                        

                        gc_for_save_data = get_gspread_client()

                        if gc_for_save_data:

                            try:

                                sh_for_save_data = gc_for_save_data.open(GOOGLE_SHEET_NAME)

                                

                                # Save Deals

                                deals_df = extracted_sections.get('deals')

                                if deals_df is not None and not deals_df.empty:

                                    if save_deals_to_actual_trades(sh_for_save_data, deals_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id):

                                        st.success(f"บันทึก Deals ({len(deals_df)} รายการ) สำเร็จ!")

                                    else:

                                        st.error("บันทึก Deals ไม่สำเร็จ."); processing_had_errors = True

                                else: st.info("ไม่พบข้อมูล Deals ใน Statement หรือไม่สามารถประมวลผลได้.")



                                # Save Orders

                                orders_df = extracted_sections.get('orders')

                                if orders_df is not None and not orders_df.empty:

                                    if save_orders_to_gsheets(sh_for_save_data, orders_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id):

                                        st.success(f"บันทึก Orders ({len(orders_df)} รายการ) สำเร็จ!")

                                    else:

                                        st.error("บันทึก Orders ไม่สำเร็จ."); processing_had_errors = True

                                else: st.info("ไม่พบข้อมูล Orders ใน Statement หรือไม่สามารถประมวลผลได้.")

                                

                                # Save Positions

                                positions_df = extracted_sections.get('positions')

                                if positions_df is not None and not positions_df.empty:

                                    if save_positions_to_gsheets(sh_for_save_data, positions_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id):

                                        st.success(f"บันทึก Positions ({len(positions_df)} รายการ) สำเร็จ!")

                                    else:

                                        st.error("บันทึก Positions ไม่สำเร็จ."); processing_had_errors = True

                                else: st.info("ไม่พบข้อมูล Positions ใน Statement หรือไม่สามารถประมวลผลได้.")



                                # Save Summaries (Balance & Results)

                                balance_summary_data = extracted_sections.get('balance_summary', {})

                                results_summary_data = extracted_sections.get('results_summary', {})



                                if balance_summary_data or results_summary_data:

                                    if save_results_summary_to_gsheets(sh_for_save_data, balance_summary_data, results_summary_data, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id):

                                        st.success("บันทึก Summary Data (Balance & Results) สำเร็จ!")

                                    else:

                                        st.error("บันทึก Summary Data ไม่สำเร็จ."); processing_had_errors = True

                                else: st.info("ไม่พบข้อมูล Summary (Balance หรือ Results) ใน Statement.")

                                

                                # --- Update session_state.latest_statement_equity AND current_account_balance ---

                                # This is the crucial step to update the balance used for calculations

                                if 'equity' in balance_summary_data and balance_summary_data['equity'] is not None:

                                    try:

                                        latest_equity_from_stmt = float(balance_summary_data['equity'])

                                        st.session_state.latest_statement_equity = latest_equity_from_stmt

                                        st.session_state.current_account_balance = latest_equity_from_stmt

                                        st.success(f"✔️ อัปเดต Balance สำหรับคำนวณจาก Statement Equity ล่าสุด: {latest_equity_from_stmt:,.2f} USD")

                                        final_processing_notes.append(f"Updated_Equity={latest_equity_from_stmt}")

                                    except ValueError:

                                        st.warning("⚠️ ไม่สามารถแปลงค่า Equity จาก Statement เป็นตัวเลขได้")

                                        final_processing_notes.append("Warning: Failed to convert Equity from Statement.")

                                else:

                                    st.warning("⚠️ ไม่พบค่า 'Equity' ใน Statement ที่อัปโหลด. จะใช้ Balance ที่ตั้งไว้")

                                    final_processing_notes.append("Warning: 'Equity' not found in Statement.")



                            except Exception as e_save_data:

                                st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูลเข้า Google Sheets: {e_save_data}")

                                st.exception(e_save_data)

                                processing_had_errors = True

                        else:

                            st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกข้อมูลได้."); processing_had_errors = True

                    

                    if not processing_had_errors:

                        final_status_for_history = "Success"

                        st.balloons()

                        st.success(f"ประมวลผลและบันทึกข้อมูลจากไฟล์ '{file_name_for_saving}' สำหรับ Batch ID '{import_batch_id}' เสร็จสิ้นสมบูรณ์!")

                    else:

                        final_status_for_history = "Failed_PartialSave"

                        st.error(f"การประมวลผลไฟล์ '{file_name_for_saving}' (Batch ID '{import_batch_id}') มีบางส่วนล้มเหลว โปรดตรวจสอบข้อความด้านบนและ Log")

                

                except UnicodeDecodeError as e_decode_main:

                    st.error(f"เกิดข้อผิดพลาดในการ Decode ไฟล์: {e_decode_main}. กรุณาตรวจสอบ Encoding (ควรเป็น UTF-8).")

                    final_status_for_history = "Failed_UnicodeDecode"

                    final_processing_notes.append(f"UnicodeDecodeError: {e_decode_main}")

                except Exception as e_main:

                    st.error(f"เกิดข้อผิดพลาดระหว่างประมวลผลหลัก: {type(e_main).__name__} - {str(e_main)[:200]}...")

                    final_status_for_history = f"Failed_MainProcessing_{type(e_main).__name__}"

                    final_processing_notes.append(f"MainError: {type(e_main).__name__} - {str(e_main)[:100]}")



                # Update UploadHistory with the final status and notes

                gc_log_update = get_gspread_client()

                if gc_log_update and initial_log_success: # Only attempt to update if initial log was written

                    try:

                        sh_log_update = gc_log_update.open(GOOGLE_SHEET_NAME)

                        ws_upload_history_update = sh_log_update.worksheet(WORKSHEET_UPLOAD_HISTORY)

                        history_rows = ws_upload_history_update.get_all_values()

                        row_to_update_idx = None

                        for idx_update, row_val_update in reversed(list(enumerate(history_rows))):

                            if len(row_val_update) > 7 and row_val_update[7] == import_batch_id:

                                row_to_update_idx = idx_update + 1

                                break

                        if row_to_update_idx:

                            notes_to_save_str = " | ".join(filter(None, final_processing_notes))[:49999] # Truncate if too long

                            ws_upload_history_update.batch_update([

                                {'range': f'G{row_to_update_idx}', 'values': [[final_status_for_history]]},

                                {'range': f'I{row_to_update_idx}', 'values': [[notes_to_save_str]]}

                            ], value_input_option='USER_ENTERED')

                            print(f"Info: Updated UploadHistory for ImportBatchID '{import_batch_id}' to '{final_status_for_history}'.")

                        else:

                            print(f"Warning: Could not find ImportBatchID '{import_batch_id}' in {WORKSHEET_UPLOAD_HISTORY} to update final status.")

                    except Exception as e_update_hist_final:

                        print(f"Warning: Could not update final status in {WORKSHEET_UPLOAD_HISTORY} for batch {import_batch_id}: {e_update_hist_final}")

                else:

                    print(f"Warning: Could not update upload history (no client or initial log failed) for batch {import_batch_id}.")



                st.session_state.uploader_key_version += 1 # Increment key to reset uploader widget

                st.rerun() # Rerun to reflect changes immediately

    else: # No file uploaded

        st.info("โปรดอัปโหลดไฟล์ Statement Report (CSV) เพื่อเริ่มต้นประมวลผล.")



    st.markdown("---")



# --- End of SEC 7 ---

# ===================== SEC 7: MAIN AREA - TRADE LOG VIEWER =======================

@st.cache_data(ttl=120) # Cache ผลลัพธ์ของฟังก์ชันนี้ (ซึ่งรวมการเรียงข้อมูลแล้ว) ไว้ 2 นาที

def load_planned_trades_from_gsheets_for_viewer():

    # เรียกใช้ฟังก์ชันกลางเพื่อโหลดข้อมูล PlannedTradeLogs (ซึ่งมี cache ของตัวเอง)

    df_logs_viewer = load_all_planned_trade_logs_from_gsheets() 

    

    if df_logs_viewer.empty:

        return pd.DataFrame()



    # การเรียงข้อมูลจะทำหลังจากโหลดข้อมูลจาก cache กลางแล้ว

    # ตรวจสอบว่าคอลัมน์ 'Timestamp' มีอยู่ และไม่เป็นค่าว่างทั้งหมดก่อนเรียง

    if 'Timestamp' in df_logs_viewer.columns and not df_logs_viewer['Timestamp'].isnull().all():

        return df_logs_viewer.sort_values(by="Timestamp", ascending=False)

    return df_logs_viewer # คืนค่า df เดิมถ้าไม่สามารถเรียงได้



with st.expander("📚 Trade Log Viewer (แผนเทรดจาก Google Sheets)", expanded=False):

    df_log_viewer_gs = load_planned_trades_from_gsheets_for_viewer()



    if df_log_viewer_gs.empty:

        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้ใน Google Sheets หรือ Worksheet 'PlannedTradeLogs' ว่างเปล่า/โหลดไม่สำเร็จ.")

    else:

        df_show_log_viewer = df_log_viewer_gs.copy() # ทำงานบนสำเนาเพื่อการกรอง



        # --- Filters UI ---

        log_filter_cols = st.columns(4)

        with log_filter_cols[0]:

            portfolios_in_log = ["ทั้งหมด"]

            if "PortfolioName" in df_show_log_viewer.columns:

                 portfolios_in_log.extend(sorted(df_show_log_viewer["PortfolioName"].dropna().unique().tolist()))

            portfolio_filter_log = st.selectbox("Portfolio", portfolios_in_log, key="log_viewer_portfolio_filter")

        

        with log_filter_cols[1]:

            modes_in_log = ["ทั้งหมด"]

            if "Mode" in df_show_log_viewer.columns:

                modes_in_log.extend(sorted(df_show_log_viewer["Mode"].dropna().unique().tolist()))

            mode_filter_log = st.selectbox("Mode", modes_in_log, key="log_viewer_mode_filter")



        with log_filter_cols[2]:

            assets_in_log = ["ทั้งหมด"]

            if "Asset" in df_show_log_viewer.columns:

                assets_in_log.extend(sorted(df_show_log_viewer["Asset"].dropna().unique().tolist()))

            asset_filter_log = st.selectbox("Asset", assets_in_log, key="log_viewer_asset_filter")



        with log_filter_cols[3]:

            date_filter_log = None

            # ตรวจสอบว่าคอลัมน์ Timestamp มีอยู่และมีข้อมูลก่อนแสดง date_input

            if 'Timestamp' in df_show_log_viewer.columns and not df_show_log_viewer['Timestamp'].isnull().all():

                 date_filter_log = st.date_input("ค้นหาวันที่ (Log)", value=None, key="log_viewer_date_filter", help="เลือกวันที่เพื่อกรอง Log")





        # --- Apply Filters ---

        if portfolio_filter_log != "ทั้งหมด" and "PortfolioName" in df_show_log_viewer:

            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["PortfolioName"] == portfolio_filter_log]

        if mode_filter_log != "ทั้งหมด" and "Mode" in df_show_log_viewer:

            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Mode"] == mode_filter_log]

        if asset_filter_log != "ทั้งหมด" and "Asset" in df_show_log_viewer:

            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Asset"] == asset_filter_log]

        

        # Filter by date (ensure Timestamp is datetime)

        if date_filter_log and 'Timestamp' in df_show_log_viewer.columns:

            # Ensure 'Timestamp' is datetime64 for comparison with date_filter_log (which is datetime.date)

            if not pd.api.types.is_datetime64_any_dtype(df_show_log_viewer['Timestamp']):

                df_show_log_viewer['Timestamp'] = pd.to_datetime(df_show_log_viewer['Timestamp'], errors='coerce')

            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Timestamp"].dt.date == date_filter_log]

        

        st.markdown("---")

        st.markdown("**Log Details & Actions:**")

        

        # --- Display Logic (Iterative rows - Original user's style) ---

        # Define columns to display and their headers

        cols_to_display_log_viewer = {

            "Timestamp": "Timestamp", "PortfolioName": "Portfolio", "Asset": "Asset",

            "Mode": "Mode", "Direction": "Direction", "Entry": "Entry", "SL": "SL", "TP": "TP",

            "Lot": "Lot", "Risk $": "Risk $" , "RR": "RR"

            # "LogID": "LogID" # Optional: for debugging or unique keying if needed

        }

        # Filter out columns not present in the DataFrame to prevent KeyErrors

        actual_cols_to_display_keys = [k for k in cols_to_display_log_viewer.keys() if k in df_show_log_viewer.columns]

        

        num_display_cols = len(actual_cols_to_display_keys)

        

        if not df_show_log_viewer.empty:

            # Create header row

            header_cols = st.columns(num_display_cols + 1) # +1 for Action button

            for i, col_key in enumerate(actual_cols_to_display_keys):

                header_cols[i].markdown(f"**{cols_to_display_log_viewer[col_key]}**")

            header_cols[num_display_cols].markdown(f"**Action**")



            # Iterate through filtered DataFrame to display rows

            for index_log, row_log in df_show_log_viewer.iterrows():

                row_display_cols = st.columns(num_display_cols + 1)

                for i, col_key in enumerate(actual_cols_to_display_keys):

                    val = row_log.get(col_key, "-") # Default to "-" if value is missing

                    if pd.isna(val): # Check for pd.NA or np.nan

                        val_display = "-"

                    elif isinstance(val, float):

                        # Format floats (e.g., Entry, SL, TP, Lot, Risk $, RR)

                        if col_key in ['Entry', 'SL', 'TP']:

                            val_display = f"{val:.5f}" if val != 0 else "0.00000" # More precision for prices

                        elif col_key in ['Lot', 'Risk $', 'RR', 'Risk %']:

                             val_display = f"{val:.2f}"

                        else:

                             val_display = str(val)

                    elif isinstance(val, pd.Timestamp):

                        val_display = val.strftime("%Y-%m-%d %H:%M")

                    else:

                        val_display = str(val)

                    

                    row_display_cols[i].write(val_display)



                # Action button for each row

                log_id_for_key = row_log.get('LogID', index_log) # Use LogID if available, else index

                if row_display_cols[num_display_cols].button(f"📈 Plot", key=f"plot_log_{log_id_for_key}"):

                    st.session_state['plot_data'] = row_log.to_dict()

                    st.success(f"เลือกข้อมูลเทรด '{row_log.get('Asset', '-')}' @ Entry '{row_log.get('Entry', '-')}' เตรียมพร้อมสำหรับ Plot บน Chart Visualizer!")

                    # Consider if rerun is needed or if Chart Visualizer updates reactively

                    st.rerun() # Rerun to make chart visualizer pick up the new plot_data

        else:

            st.info("ไม่พบข้อมูล Log ที่ตรงกับเงื่อนไขการค้นหา")

        

        # Display plot_data in sidebar if it exists (from original code)

        if 'plot_data' in st.session_state and st.session_state['plot_data']:

            st.sidebar.success(f"ข้อมูลพร้อม Plot: {st.session_state['plot_data'].get('Asset')} @ {st.session_state['plot_data'].get('Entry')}")

            # Limit the display if plot_data is too large

            # For instance, convert to string and truncate, or select specific keys

            try:

                plot_data_str = str(st.session_state['plot_data'])

                if len(plot_data_str) > 300: # Limit length for display

                    plot_data_display = plot_data_str[:300] + "..."

                else:

                    plot_data_display = plot_data_str

                st.sidebar.json(plot_data_display, expanded=False) # Display as JSON string

            except:

                st.sidebar.text("ไม่สามารถแสดง plot_data (อาจมีปัญหาการแปลง)")





# --- End of SEC 7 (formerly SEC 9) ---

