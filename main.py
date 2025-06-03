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
import hashlib # เพิ่มสำหรับ SEC 7

st.set_page_config(page_title="Ultimate-Chart", layout="wide")
acc_balance = 10000 # ยอดคงเหลือเริ่มต้นของบัญชีเทรด (อาจจะดึงมาจาก Active Portfolio ในอนาคต)

# +++ START: โค้ดส่วนตรวจสอบและดำเนินการตาม Flag สำหรับเคลียร์ File Uploader +++
if st.session_state.get("clear_uploader_flag_v7_final", False): # ใช้ชื่อ key ของ flag ที่เฉพาะเจาะจง
    st.session_state.ultimate_stmt_uploader_v7_final = None
    st.session_state.clear_uploader_flag_v7_final = False # Reset flag กลับเป็น False
    # print("Debug: Uploader cleared by flag.") # Optional: for debugging
# +++ END: โค้ดส่วนตรวจสอบ Flag +++

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
    except gspread.exceptions.APIError as e_api: # เพิ่มการดักจับ APIError
        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:
            st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios (Quota Exceeded): {e_api.args[0] if e_api.args else 'Unknown quota error'}. ลองอีกครั้งในภายหลัง")
        else:
            st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios (API Error): {e_api}")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios: {e}")
        return pd.DataFrame()

# +++ START: ฟังก์ชันใหม่สำหรับโหลด PlannedTradeLogs แบบรวมศูนย์พร้อม Cache +++
@st.cache_data(ttl=180) # Cache ข้อมูลไว้ 3 นาที (ปรับ TTL ได้ตามความเหมาะสม)
def load_all_planned_trade_logs_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        # st.warning("GSpread client not available for loading planned trade logs.") # ลดการแสดงข้อความใน UI สำหรับการโหลดพื้นหลัง
        print("Warning: GSpread client not available for loading planned trade logs.")
        return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        records = worksheet.get_all_records()
        
        if not records:
            return pd.DataFrame()
        
        df_logs = pd.DataFrame(records)
        
        # การแปลงประเภทข้อมูลพื้นฐาน
        if 'Timestamp' in df_logs.columns:
            df_logs['Timestamp'] = pd.to_datetime(df_logs['Timestamp'], errors='coerce')
        if 'Risk $' in df_logs.columns:
            df_logs['Risk $'] = pd.to_numeric(df_logs['Risk $'], errors='coerce').fillna(0)
        if 'RR' in df_logs.columns:
            df_logs['RR'] = pd.to_numeric(df_logs['RR'], errors='coerce')
        if 'PortfolioID' in df_logs.columns: # ตรวจสอบว่า PortfolioID เป็น string
            df_logs['PortfolioID'] = df_logs['PortfolioID'].astype(str)
        
        # เพิ่มการแปลงประเภทข้อมูลอื่นๆ ที่จำเป็นสำหรับคอลัมน์ เช่น Entry, SL, TP, Lot
        cols_to_numeric_viewer = ['Entry', 'SL', 'TP', 'Lot', 'Risk %'] # เพิ่ม 'Risk %' หากมีการใช้งานทั่วไป
        for col_viewer in cols_to_numeric_viewer:
            if col_viewer in df_logs.columns:
                df_logs[col_viewer] = pd.to_numeric(df_logs[col_viewer], errors='coerce')

        return df_logs
    except gspread.exceptions.WorksheetNotFound:
        # st.warning(f"Worksheet '{WORKSHEET_PLANNED_LOGS}' not found for centralized loading.") # ลดการแสดงข้อความ
        print(f"Warning: Worksheet '{WORKSHEET_PLANNED_LOGS}' not found for centralized loading.")
        return pd.DataFrame()
    except gspread.exceptions.APIError as e_api:
        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429: # Quota Exceeded
            print(f"APIError (Quota Exceeded) loading planned trade logs: {e_api.args[0] if e_api.args else 'Unknown quota error'}")
        else:
            print(f"APIError loading planned trade logs: {e_api}")
        return pd.DataFrame() # ส่ง DataFrame ว่างเปล่าเมื่อเกิดข้อผิดพลาด API
    except Exception as e:
        # st.error(f"Unexpected error loading all planned trade logs: {e}") # ลดการแสดงข้อความ
        print(f"Unexpected error loading all planned trade logs: {e}")
        return pd.DataFrame()
# (วางฟังก์ชันนี้ไว้ใกล้กับฟังก์ชันโหลดข้อมูลอื่นๆ เช่น load_all_planned_trade_logs_from_gsheets())

@st.cache_data(ttl=180) # Cache ข้อมูลไว้ 3 นาที (ปรับ TTL ได้ตามความเหมาะสม)
def load_actual_trades_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        print("Warning: GSpread client not available for loading actual trades.")
        return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME) # GOOGLE_SHEET_NAME ถูกกำหนดไว้ใน SEC 0
        worksheet = sh.worksheet(WORKSHEET_ACTUAL_TRADES) # WORKSHEET_ACTUAL_TRADES ถูกกำหนดไว้ใน SEC 0
        
        records = worksheet.get_all_records(numericise_ignore=['all']) # อ่านทุกอย่างเป็น string ก่อน
        
        if not records:
            # print(f"Info: Worksheet '{WORKSHEET_ACTUAL_TRADES}' is empty or no records found.")
            return pd.DataFrame()
        
        df_actual_trades = pd.DataFrame(records)
        
        # --- การแปลงประเภทข้อมูลที่สำคัญ ---
        # คอลัมน์ที่ควรเป็น datetime
        if 'Time_Deal' in df_actual_trades.columns:
            df_actual_trades['Time_Deal'] = pd.to_datetime(df_actual_trades['Time_Deal'], errors='coerce')

        # คอลัมน์ที่ควรเป็นตัวเลข
        numeric_cols_actual = [
            'Volume_Deal', 'Price_Deal', 'Commission_Deal', 
            'Fee_Deal', 'Swap_Deal', 'Profit_Deal', 'Balance_Deal'
        ]
        for col in numeric_cols_actual:
            if col in df_actual_trades.columns:
                df_actual_trades[col] = pd.to_numeric(df_actual_trades[col], errors='coerce')

        # คอลัมน์ PortfolioID ควรเป็น string เพื่อการเปรียบเทียบที่สอดคล้องกัน
        if 'PortfolioID' in df_actual_trades.columns:
            df_actual_trades['PortfolioID'] = df_actual_trades['PortfolioID'].astype(str)
        
        # คอลัมน์อื่นๆ ที่อาจสำคัญ (เช่น Deal_ID, Order_ID_Deal) โดยทั่วไปจะยังคงเป็น string

        # print(f"Successfully loaded {len(df_actual_trades)} records from '{WORKSHEET_ACTUAL_TRADES}'.")
        return df_actual_trades

    except gspread.exceptions.WorksheetNotFound:
        print(f"Warning: Worksheet '{WORKSHEET_ACTUAL_TRADES}' not found for loading actual trades.")
        return pd.DataFrame()
    except gspread.exceptions.APIError as e_api:
        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429: # Quota Exceeded
            print(f"APIError (Quota Exceeded) loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e_api.args[0] if e_api.args else 'Unknown quota error'}")
        else:
            print(f"APIError loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e_api}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Unexpected error loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e}")
        return pd.DataFrame()
# +++ END: ฟังก์ชันใหม่สำหรับโหลด PlannedTradeLogs +++





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

# +++ START: โค้ดที่เพิ่มเข้ามาเพื่อรีเซ็ตไฟล์อัปโหลดเมื่อมีการเปลี่ยนพอร์ต +++
if selected_portfolio_name_gs != st.session_state.active_portfolio_name_gs:
    # ตรวจสอบว่ามีการเลือกพอร์ตที่แตกต่างจากเดิมจริงๆ
    if 'ultimate_stmt_uploader_v7_final' in st.session_state and st.session_state.ultimate_stmt_uploader_v7_final is not None:
        st.session_state.ultimate_stmt_uploader_v7_final = None
        st.sidebar.warning("⚠️ การเปลี่ยนพอร์ตทำให้ไฟล์ที่อัปโหลดไว้ (ในส่วน Statement Import) ถูกรีเซ็ต กรุณาอัปโหลดไฟล์อีกครั้งหากต้องการ")
# +++ END: โค้ดที่เพิ่มเข้ามา +++

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
    # If selected_portfolio_name_gs is "", it means user selected the blank option (to deselect)
    # The st.session_state.active_portfolio_name_gs would have been the previously active portfolio.
    # The reset logic above would have already triggered if a file was pending.
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
        # Ensure Timestamp is datetime before strftime
        if not pd.api.types.is_datetime64_any_dtype(log_source_df['Timestamp']):
            log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        
        # Filter out NaT from Timestamp after conversion
        log_source_df = log_source_df.dropna(subset=['Timestamp'])

        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)
        df_today = log_source_df[log_source_df["Timestamp"].dt.strftime("%Y-%m-%d") == today_str]
        drawdown = df_today["Risk $"].sum() # This should be sum of losses, so usually negative or zero
        return drawdown
    except KeyError as e: 
        # print(f"KeyError in get_today_drawdown: {e}") # Optional: for debugging
        return 0
    except Exception as e: 
        # print(f"Exception in get_today_drawdown: {e}") # Optional: for debugging
        return 0


def get_performance(log_source_df, mode="week"):
    # ... (โค้ดเดิมของลูกพี่ตั้ม) ...
    if log_source_df.empty: return 0, 0, 0
    try:
        # Ensure Timestamp is datetime
        if not pd.api.types.is_datetime64_any_dtype(log_source_df['Timestamp']):
            log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        
        log_source_df = log_source_df.dropna(subset=['Timestamp']) # Drop rows where Timestamp conversion failed

        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)
        now = datetime.now()
        if mode == "week":
            week_start_date = now - pd.Timedelta(days=now.weekday())
            df_period = log_source_df[log_source_df["Timestamp"] >= week_start_date.replace(hour=0, minute=0, second=0, microsecond=0)]
        else:  # month
            month_start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            df_period = log_source_df[log_source_df["Timestamp"] >= month_start_date]
        
        # Ensure "Risk $" column exists before trying to use it for win/loss calculation
        if "Risk $" not in df_period.columns:
            return 0,0,0

        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0] # Assuming 0 or negative is a loss or break-even
        total_trades = win + loss
        winrate = (100 * win / total_trades) if total_trades > 0 else 0
        gain = df_period["Risk $"].sum()
        return winrate, gain, total_trades
    except KeyError as e: 
        # print(f"KeyError in get_performance: {e}") # Optional
        return 0,0,0
    except Exception as e: 
        # print(f"Exception in get_performance: {e}") # Optional
        return 0,0,0

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
        expected_headers_plan = [ 
            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",
            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"
        ]
        current_headers_plan = []
        if ws.row_count > 0:
            try: current_headers_plan = ws.row_values(1)
            except Exception: current_headers_plan = []
        
        if not current_headers_plan or all(h == "" for h in current_headers_plan):
            ws.update([expected_headers_plan], value_input_option='USER_ENTERED') # Use update for single row list
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
# +++ END: โค้ดใหม่สำหรับฟังก์ชัน save_new_portfolio_to_gsheets +++

# ===================== SEC 1.5: PORTFOLIO MANAGEMENT UI (Main Area) =======================
def on_program_type_change_v8(): # This callback seems to be defined but its key might have changed or it might need adjustment based on usage
    st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8

with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=True): # Setting expanded=True for easier testing
    st.subheader("พอร์ตทั้งหมดของคุณ")
    # df_portfolios_gs should be loaded globally/module level before this UI section
    # Ensure df_portfolios_gs is available. It is loaded at the beginning of SEC 1.
    if df_portfolios_gs.empty: # Check if df_portfolios_gs is empty (loaded in SEC 1)
        st.info("ยังไม่มีข้อมูลพอร์ต หรือยังไม่ได้โหลดข้อมูลพอร์ต โปรดเพิ่มพอร์ตใหม่ด้านล่าง หรือตรวจสอบการเชื่อมต่อ Google Sheets")
    else:
        cols_to_display_pf_table = ['PortfolioID', 'PortfolioName', 'ProgramType', 'EvaluationStep', 'Status', 'InitialBalance']
        # Filter out columns that might not exist in the DataFrame to prevent KeyErrors
        cols_exist_pf_table = [col for col in cols_to_display_pf_table if col in df_portfolios_gs.columns]
        if cols_exist_pf_table:
            st.dataframe(df_portfolios_gs[cols_exist_pf_table], use_container_width=True, hide_index=True)
        else:
            st.info("ไม่พบคอลัมน์ที่ต้องการแสดงในตารางพอร์ต (ตรวจสอบ df_portfolios_gs และการโหลดข้อมูล)")

    st.markdown("---")
    st.subheader("➕ เพิ่มพอร์ตใหม่")

    # --- Selectbox for Program Type (OUTSIDE THE FORM for immediate UI update) ---
    program_type_options_outside = ["", "Personal Account", "Prop Firm Challenge", "Funded Account", "Trading Competition"]
    
    if 'exp_pf_type_select_v8_key' not in st.session_state: 
        st.session_state.exp_pf_type_select_v8_key = ""

    # Callback function for the program type selectbox
    # def on_program_type_change_v8(): # Defined globally above the expander now
    #    st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8

    # The selectbox that controls the conditional UI
    st.selectbox(
        "ประเภทพอร์ต (Program Type)*", 
        options=program_type_options_outside, 
        index=program_type_options_outside.index(st.session_state.exp_pf_type_select_v8_key), 
        key="exp_pf_type_selector_widget_v8", 
        on_change=on_program_type_change_v8 
    )
    
    selected_program_type_to_use_in_form = st.session_state.exp_pf_type_select_v8_key

    # DEBUG line, can be commented out or removed in production
    # st.write(f"**[DEBUG - นอก FORM, หลัง Selectbox] `selected_program_type_to_use_in_form` คือ:** `{selected_program_type_to_use_in_form}`")

    with st.form("new_portfolio_form_main_v8_final", clear_on_submit=True): 
        st.markdown(f"**กรอกข้อมูลพอร์ต (สำหรับประเภท: {selected_program_type_to_use_in_form if selected_program_type_to_use_in_form else 'ยังไม่ได้เลือก'})**")
        
        form_c1_in_form, form_c2_in_form = st.columns(2)
        with form_c1_in_form:
            form_new_portfolio_name_in_form = st.text_input("ชื่อพอร์ต (Portfolio Name)*", key="form_pf_name_v8")
        with form_c2_in_form:
            form_new_initial_balance_in_form = st.number_input("บาลานซ์เริ่มต้น (Initial Balance)*", min_value=0.01, value=10000.0, format="%.2f", key="form_pf_balance_v8")
        
        form_status_options_in_form = ["Active", "Inactive", "Pending", "Passed", "Failed"]
        form_new_status_in_form = st.selectbox("สถานะพอร์ต (Status)*", options=form_status_options_in_form, index=0, key="form_pf_status_v8")
        
        form_new_evaluation_step_val_in_form = "" # Initialize
        if selected_program_type_to_use_in_form == "Prop Firm Challenge":
            # DEBUG line
            # st.write(f"**[DEBUG - ใน FORM, ใน IF Evaluation Step] ประเภทคือ:** `{selected_program_type_to_use_in_form}`")
            evaluation_step_options_in_form = ["", "Phase 1", "Phase 2", "Phase 3", "Verification"]
            form_new_evaluation_step_val_in_form = st.selectbox("ขั้นตอนการประเมิน (Evaluation Step)", 
                                                                options=evaluation_step_options_in_form, index=0, 
                                                                key="form_pf_eval_step_select_v8")

        # --- Conditional Inputs Defaults ---
        form_profit_target_val = 8.0; form_daily_loss_val = 5.0; form_total_stopout_val = 10.0; form_leverage_val = 100.0; form_min_days_val = 0
        form_comp_end_date = None; form_comp_goal_metric = ""
        form_profit_target_val_comp = 20.0 # Default for competition profit target
        form_daily_loss_val_comp = 5.0    # Default for competition daily loss
        form_total_stopout_val_comp = 10.0 # Default for competition total stopout

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
                form_sd_loss_val = st.number_input("Scale Down: Max Loss %", value=form_sd_loss_val, format="%.1f", key="f_scale_sd_loss_v8") # Usually a negative value
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
            # Validation
            if not form_new_portfolio_name_in_form or not selected_program_type_to_use_in_form or not form_new_status_in_form or form_new_initial_balance_in_form <= 0:
                st.warning("กรุณากรอกข้อมูลที่จำเป็น (*) ให้ครบถ้วนและถูกต้อง: ชื่อพอร์ต, ประเภทพอร์ต, สถานะพอร์ต, และยอดเงินเริ่มต้นต้องมากกว่า 0")
            elif not df_portfolios_gs.empty and form_new_portfolio_name_in_form in df_portfolios_gs['PortfolioName'].astype(str).values: # Check against loaded portfolios
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
                    # Set other scaling fields to None or default empty if scaling is disabled
                    # This ensures that if a user disables scaling later, old values are not mistakenly kept active
                    # However, the provided GSheet headers expect values or blanks.
                    # For boolean, False is fine. For others, blank or a defined "not set" value.
                    # The save_new_portfolio_to_gsheets handles .get(header, "") which results in blanks.
                    data_to_save['CurrentRiskPercent'] = form_current_risk_val # Still save current risk if entered, even if scaling disabled

                success_save = save_new_portfolio_to_gsheets(data_to_save) 
                
                if success_save:
                    st.success(f"เพิ่มพอร์ต '{form_new_portfolio_name_in_form}' (ID: {new_id_value}) สำเร็จ!")
                    st.session_state.exp_pf_type_select_v8_key = "" # Reset selectboxนอกฟอร์ม
                    if hasattr(load_portfolios_from_gsheets, 'clear'): # Clear cache for portfolio list
                         load_portfolios_from_gsheets.clear()
                    st.rerun()
                else:
                    st.error("เกิดข้อผิดพลาดในการบันทึกพอร์ตใหม่ไปยัง Google Sheets")

# ==============================================================================
# END: ส่วนจัดการ Portfolio (SEC 1.5)
# ==============================================================================


# ===================== SEC 2: COMMON INPUTS & MODE SELECTION =======================
# --- ดึงค่า InitialBalance และ CurrentRiskPercent จาก Active Portfolio ---
# หมายเหตุ: ส่วนนี้ถูกย้ายขึ้นมาเพื่อให้แน่ใจว่า active_balance_to_use และ initial_risk_pct_from_portfolio
# ถูกกำหนดค่าก่อนที่จะถูกใช้งานใน SEC 2.2 หรือ SEC 2.3 หาก mode ถูกเลือก
# และก่อนปุ่ม Reset Form ที่อาจจะ re-initialize ค่าเหล่านี้

active_balance_to_use = 10000.0 # Fallback default value
initial_risk_pct_from_portfolio = 1.0 # Fallback default value

if 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details
    
    # ดึง InitialBalance จาก current_portfolio_details ถ้ามี
    portfolio_initial_balance_val = details.get('InitialBalance')
    if pd.notna(portfolio_initial_balance_val):
        try:
            active_balance_to_use = float(portfolio_initial_balance_val)
        except (ValueError, TypeError):
            # st.sidebar.warning("ไม่สามารถแปลง InitialBalance จากพอร์ตเป็นตัวเลขได้ ใช้ค่าเริ่มต้นแทน")
            pass # ใช้ active_balance_to_use ที่ตั้งไว้เป็น fallback

    # ดึง CurrentRiskPercent จาก current_portfolio_details ถ้ามี
    current_risk_val_str = details.get('CurrentRiskPercent')
    if pd.notna(current_risk_val_str) and str(current_risk_val_str).strip() != "":
        try:
            risk_val_float = float(current_risk_val_str)
            if risk_val_float > 0:
                 initial_risk_pct_from_portfolio = risk_val_float
        except (ValueError, TypeError):
            # st.sidebar.warning("ไม่สามารถแปลง CurrentRiskPercent จากพอร์ตเป็นตัวเลขได้ ใช้ค่าเริ่มต้นแทน")
            pass # ใช้ initial_risk_pct_from_portfolio ที่ตั้งไว้เป็น fallback
elif 'active_portfolio_name_gs' in st.session_state and st.session_state.active_portfolio_name_gs == "":
    # กรณีที่ยังไม่ได้เลือกพอร์ต (active_portfolio_name_gs เป็นสตริงว่าง)
    # ให้ใช้ค่า default ที่ตั้งไว้ด้านบน (10000.0 และ 1.0)
    pass
else:
    # กรณีอื่นๆ ที่ current_portfolio_details อาจจะไม่มี (เช่น โหลดไม่สำเร็จ)
    # st.sidebar.warning("ไม่พบรายละเอียดพอร์ตที่ใช้งาน (active portfolio) อาจกำลังใช้ค่า Balance และ Risk เริ่มต้นของระบบ")
    pass


# กำหนดค่าเริ่มต้นให้กับ st.session_state.current_account_balance หากยังไม่มี
if 'current_account_balance' not in st.session_state:
    st.session_state.current_account_balance = active_balance_to_use


drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=st.session_state.get("drawdown_limit_pct", 2.0), # ดึงค่าจาก session_state ถ้ามี, 아니면 default
    step=0.1, format="%.1f",
    key="drawdown_limit_pct" # Key นี้จะใช้เก็บค่าใน session_state
)

mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")


if st.sidebar.button("🔄 Reset Form"):
    # ค่าที่ต้องการคงไว้หลังจากการ Reset
    mode_to_keep = st.session_state.get("mode", "FIBO") # คงค่า mode ที่เลือกไว้
    dd_limit_to_keep = st.session_state.get("drawdown_limit_pct", 2.0) # คงค่า drawdown limit
    
    # ข้อมูล Portfolio ที่สำคัญ
    active_portfolio_name_gs_keep = st.session_state.get('active_portfolio_name_gs', "")
    active_portfolio_id_gs_keep = st.session_state.get('active_portfolio_id_gs', None)
    current_portfolio_details_keep = st.session_state.get('current_portfolio_details', None)
    
    # current_account_balance จะถูก re-evaluate จาก current_portfolio_details_keep ด้านล่าง
    # exp_pf_type_select_v8_key_keep = st.session_state.get("exp_pf_type_select_v8_key", "")
    sb_active_portfolio_selector_gs_keep = st.session_state.get('sb_active_portfolio_selector_gs', "")


    keys_to_fully_preserve = {"gcp_service_account"} # ค่าที่ควรจะคงอยู่ตลอดการใช้งานแอป
    temp_preserved_values = {}
    for k_fp in keys_to_fully_preserve:
        if k_fp in st.session_state:
            temp_preserved_values[k_fp] = st.session_state[k_fp]

    # ล้าง session state ส่วนใหญ่
    # st.session_state.clear() # วิธีนี้จะล้างทั้งหมดรวมถึง gcp_service_account ซึ่งอาจจะไม่ต้องการ
    keys_to_clear = [k for k in st.session_state.keys() if k not in keys_to_fully_preserve]
    for key in keys_to_clear:
        del st.session_state[key]
            
    for k_fp, v_fp in temp_preserved_values.items(): # คืนค่าที่ preserve ไว้
        st.session_state[k_fp] = v_fp

    # คืนค่า/ตั้งค่าเริ่มต้นที่จำเป็น
    st.session_state.mode = mode_to_keep
    st.session_state.drawdown_limit_pct = dd_limit_to_keep
    
    st.session_state.active_portfolio_name_gs = active_portfolio_name_gs_keep
    st.session_state.active_portfolio_id_gs = active_portfolio_id_gs_keep
    st.session_state.current_portfolio_details = current_portfolio_details_keep
    
    # st.session_state.exp_pf_type_select_v8_key = exp_pf_type_select_v8_key_keep # Portfolio management UI state
    if sb_active_portfolio_selector_gs_keep: 
        st.session_state.sb_active_portfolio_selector_gs = sb_active_portfolio_selector_gs_keep

    # Re-evaluate active_balance_to_use and initial_risk_pct_from_portfolio based on preserved details
    preserved_active_balance = 10000.0
    preserved_initial_risk = 1.0
    if current_portfolio_details_keep:
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
            
    st.session_state.current_account_balance = preserved_active_balance # ตั้งค่า current_account_balance ใหม่

    # ตั้งค่า session state สำหรับ input fields โดยใช้ค่า default หรือค่าจาก portfolio ที่ preserve ไว้
    st.session_state.risk_pct_fibo_val_v2 = preserved_initial_risk
    st.session_state.asset_fibo_val_v2 = "XAUUSD" 
    st.session_state.risk_pct_custom_val_v2 = preserved_initial_risk
    st.session_state.asset_custom_val_v2 = "XAUUSD" 

    st.session_state.swing_high_fibo_val_v2 = ""
    st.session_state.swing_low_fibo_val_v2 = ""
    st.session_state.fibo_flags_v2 = [True] * 5 # Default 5 fibo levels, all checked (ปรับตามจำนวน fibos_fibo_v2 จริง)

    default_n_entries_custom = 2
    st.session_state.n_entry_custom_val_v2 = default_n_entries_custom
    for i in range(default_n_entries_custom): # ตั้งค่าเริ่มต้นสำหรับ custom entries
        st.session_state[f"custom_entry_{i}_v3"] = "0.00"
        st.session_state[f"custom_sl_{i}_v3"] = "0.00"
        st.session_state[f"custom_tp_{i}_v3"] = "0.00"
        
    if 'plot_data' in st.session_state: # ล้างข้อมูล plot data ถ้ามี
        del st.session_state['plot_data']
        
    st.toast("รีเซ็ตฟอร์มเรียบร้อยแล้ว!", icon="🔄")
    st.rerun()

# ===================== SEC 2.1: FIBO TRADE DETAILS =======================
if mode == "FIBO": # mode ควรจะถูก define ใน SEC 2 (เดิม SEC 2.1)
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
            value=st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio), #  ใช้ค่าจาก Active Portfolio ที่กำหนดใน SEC 2
            step=0.01, format="%.2f",
            key="risk_pct_fibo_input_v3") 
        st.session_state.risk_pct_fibo_val_v2 = risk_pct_fibo_v2
    with col3_fibo_v2:
        default_direction_index = 0 # Default to "Long"
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
        st.session_state.fibo_flags_v2 = [True] * len(fibos_fibo_v2) # Default all to True

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
        if swing_high_fibo_v2 and swing_low_fibo_v2: # Check if both have values
            if high_val_fibo_v2 <= low_val_fibo_v2:
                st.sidebar.warning("High ต้องมากกว่า Low!")
    except ValueError:
        if swing_high_fibo_v2 or swing_low_fibo_v2: # Only warn if at least one input is non-empty and invalid
            st.sidebar.warning("กรุณาใส่ High/Low เป็นตัวเลขที่ถูกต้อง")
    # except Exception: # Avoid generic exception unless specific handling is needed
        # pass

    if risk_pct_fibo_v2 <= 0: 
        st.sidebar.warning("Risk% ต้องมากกว่า 0")

    st.sidebar.markdown("---")
    try:
        # Ensure values are valid floats before preview
        if swing_high_fibo_v2 and swing_low_fibo_v2: # Check again for valid inputs
            high_preview_fibo_v2 = float(swing_high_fibo_v2)
            low_preview_fibo_v2 = float(swing_low_fibo_v2)
            if high_preview_fibo_v2 > low_preview_fibo_v2 and any(st.session_state.fibo_flags_v2):
                st.sidebar.markdown("**Preview (เบื้องต้น):**")
                first_selected_fibo_index_v2 = -1
                try:
                    first_selected_fibo_index_v2 = st.session_state.fibo_flags_v2.index(True)
                except ValueError: # Should not happen if any() is true, but good practice
                    pass
                
                if first_selected_fibo_index_v2 != -1:
                    preview_entry_fibo_v2 = 0.0
                    if direction_fibo_v2 == "Long":
                        preview_entry_fibo_v2 = low_preview_fibo_v2 + (high_preview_fibo_v2 - low_preview_fibo_v2) * fibos_fibo_v2[first_selected_fibo_index_v2]
                    else: # Short
                        preview_entry_fibo_v2 = high_preview_fibo_v2 - (high_preview_fibo_v2 - low_preview_fibo_v2) * fibos_fibo_v2[first_selected_fibo_index_v2]
                    st.sidebar.markdown(f"Entry แรกที่เลือก ≈ **{preview_entry_fibo_v2:.2f}**") # Assuming 2 decimal places for price preview
                    st.sidebar.caption("Lot/TP/ผลลัพธ์เต็มอยู่ด้านล่าง (ใน Strategy Summary)")
    except ValueError: # Handles cases where conversion to float fails after initial checks
        pass # Warnings are handled above
    except Exception: # Catch any other unexpected error during preview
        pass

    save_fibo = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo_v3")

# ===================== SEC 2.2: CUSTOM TRADE DETAILS =======================
elif mode == "CUSTOM": # mode ควรจะถูก define ใน SEC 2 (เดิม SEC 2.1)
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
            value=st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio), #  ใช้ค่าจาก Active Portfolio ที่กำหนดใน SEC 2
            step=0.01, format="%.2f",
            key="risk_pct_custom_input_v3") 
        st.session_state.risk_pct_custom_val_v2 = risk_pct_custom_v2
    with col3_custom_v2:
        n_entry_custom_v2 = st.number_input( 
            "จำนวนไม้",
            min_value=1, max_value=10, # สมมติว่าจำกัดจำนวนไม้สูงสุดที่ 10
            value=st.session_state.get("n_entry_custom_val_v2", 2), 
            step=1,
            key="n_entry_custom_input_v3") 
        st.session_state.n_entry_custom_val_v2 = int(n_entry_custom_v2) # Ensure it's an integer for range

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")
    custom_inputs_v2 = [] 
    
    current_custom_risk_pct_v2 = risk_pct_custom_v2 
    risk_per_trade_custom_v2 = current_custom_risk_pct_v2 / 100.0 # Ensure float division
    
    # active_balance_to_use ควรถูกกำหนดค่าแล้วใน SEC 2
    risk_dollar_total_custom_v2 = active_balance_to_use * risk_per_trade_custom_v2 
    
    num_entries_val_custom_v2 = st.session_state.n_entry_custom_val_v2 # ใช้ค่าจาก session_state ที่เป็น int แล้ว
    risk_dollar_per_entry_custom_v2 = risk_dollar_total_custom_v2 / num_entries_val_custom_v2 if num_entries_val_custom_v2 > 0 else 0

    for i in range(num_entries_val_custom_v2): # Make sure num_entries_val_custom_v2 is int
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
        stop_val_v2 = None # Initialize

        try:
            entry_float_v2 = float(entry_str_v2)
            sl_float_v2 = float(sl_str_v2)
            
            if sl_float_v2 == entry_float_v2: # SL cannot be equal to Entry
                stop_val_v2 = 0
                lot_display_str_v2 = "Lot: - (SL=Entry)"
                tp_rr3_info_str_v2 = "Stop: 0 (SL=Entry)"
            else:
                stop_val_v2 = abs(entry_float_v2 - sl_float_v2)
                if stop_val_v2 > 1e-9: # Check for non-zero stop distance
                    lot_val_v2 = risk_dollar_per_entry_custom_v2 / stop_val_v2
                    lot_display_str_v2 = f"Lot: {lot_val_v2:.2f}"
                    tp_rr3_info_str_v2 = f"Stop: {stop_val_v2:.5f}" # Display stop with more precision
                else: # stop_val is effectively zero
                    lot_display_str_v2 = "Lot: - (Stop=0)"
                    tp_rr3_info_str_v2 = "Stop: 0"

        except ValueError: # If float conversion fails
            # lot_display_str_v2, risk_per_entry_display_str_v2, tp_rr3_info_str_v2 remain as default error strings
            pass
        except Exception: # Catch any other unexpected error
            pass
        
        st.sidebar.caption(f"{lot_display_str_v2} | {risk_per_entry_display_str_v2} | {tp_rr3_info_str_v2}")
        custom_inputs_v2.append({"entry": entry_str_v2, "sl": sl_str_v2, "tp": tp_str_v2})

    if current_custom_risk_pct_v2 <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")
    save_custom = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom_v3")

# ===================== SEC 2.3: SIDEBAR - CALCULATIONS, SUMMARY & ACTIONS =======================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")

# Initialize summary variables (these are for display, should be updated after calculations)
summary_total_lots = 0.0
summary_total_risk_dollar = 0.0
summary_avg_rr = 0.0
summary_total_profit_at_primary_tp = 0.0
custom_tp_recommendation_messages = [] 

# Define new effective TP ratios (used in FIBO mode calculations below)
RATIO_TP1_EFF = 1.618 # Per user's original TP logic in SEC 4 (1.618)
RATIO_TP2_EFF = 2.618 # Per user's original TP logic in SEC 4 (2.618)
RATIO_TP3_EFF = 4.236 # Per user's original TP logic in SEC 4 (4.236)

# --- START: CRITICAL INITIALIZATION FOR NameError ---
# Ensure these list variables always exist before being potentially populated or accessed.
entry_data_summary_sec3 = [] # Will be renamed if this section becomes SEC 2.3, but keep var name for now
custom_entries_summary_sec3 = [] # Same as above
# --- END: CRITICAL INITIALIZATION FOR NameError ---

# active_balance_to_use should have been defined in SEC 2 from st.session_state.current_account_balance or portfolio details
# If not, ensure it's retrieved here or passed correctly.
# For this example, we assume active_balance_to_use is available from the execution of SEC 2.
# fallback_balance = 10000.0 # Default if not found for some reason
# current_active_balance_for_summary = st.session_state.get('current_account_balance', fallback_balance)
# The variable 'active_balance_to_use' was defined at the start of SEC 2. We'll use that.

if mode == "FIBO":
    try:
        h_input_str_fibo = st.session_state.get("swing_high_fibo_val_v2", "")
        l_input_str_fibo = st.session_state.get("swing_low_fibo_val_v2", "")
        direction_fibo = st.session_state.get("direction_fibo_val_v2", "Long")
        risk_pct_fibo = st.session_state.get("risk_pct_fibo_val_v2", 1.0)

        # fibos_fibo_v2 is defined in SEC 2.1 (formerly 2.2)
        # Ensure it's available here or redefine if necessary for context
        if 'fibos_fibo_v2' not in locals() and 'fibos_fibo_v2' not in globals():
             fibos_fibo_v2 = [0.114, 0.25, 0.382, 0.5, 0.618] # Fallback definition
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
            else: # Short
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

                if range_fibo_calc <= 1e-9: # Use a small epsilon for float comparison
                    st.sidebar.warning("Range ระหว่าง High และ Low ต้องมากกว่า 0 อย่างมีนัยสำคัญ")
                else:
                    # Global TPs based on the main Fibo range, using ratios from SEC 4's TP logic
                    global_tp1_fibo, global_tp2_fibo, global_tp3_fibo = 0.0, 0.0, 0.0
                    if direction_fibo == "Long":
                        global_tp1_fibo = low_fibo_input + (range_fibo_calc * RATIO_TP1_EFF) # TP based on 0% level + range * ratio
                        # global_tp2_fibo = low_fibo_input + (range_fibo_calc * RATIO_TP2_EFF)
                        # global_tp3_fibo = low_fibo_input + (range_fibo_calc * RATIO_TP3_EFF)
                    else: # Short
                        global_tp1_fibo = high_fibo_input - (range_fibo_calc * RATIO_TP1_EFF) # TP based on 0% level - range * ratio
                        # global_tp2_fibo = high_fibo_input - (range_fibo_calc * RATIO_TP2_EFF)
                        # global_tp3_fibo = high_fibo_input - (range_fibo_calc * RATIO_TP3_EFF)

                    selected_fibo_levels_count = sum(current_fibo_flags_fibo)
                    if selected_fibo_levels_count > 0:
                        # Use active_balance_to_use defined in SEC 2
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
                                    # Original SL logic: SL is at the 0% level of the Fibo range for Long
                                    sl_price_fibo_final = fibo_0_percent_level_calc 
                                else: # Short
                                    entry_price_fibo = fibo_0_percent_level_calc - (range_fibo_calc * fibo_ratio_for_entry)
                                    # Original SL logic: SL is at the 0% level of the Fibo range for Short
                                    sl_price_fibo_final = fibo_0_percent_level_calc
                                
                                stop_distance_fibo = abs(entry_price_fibo - sl_price_fibo_final)
                                lot_size_fibo, actual_risk_dollar_fibo = 0.0, 0.0
                                if stop_distance_fibo > 1e-9: # Epsilon check
                                    lot_size_fibo = risk_dollar_per_entry_fibo / stop_distance_fibo
                                    actual_risk_dollar_fibo = lot_size_fibo * stop_distance_fibo # Recalculate actual risk based on lot size
                                else: # Avoid division by zero if stop distance is too small
                                    actual_risk_dollar_fibo = risk_dollar_per_entry_fibo # Assign planned risk if SL is at entry
                                    lot_size_fibo = 0 # Or handle as invalid trade

                                profit_at_tp1_fibo, rr_to_tp1_fibo = 0.0, 0.0
                                if stop_distance_fibo > 1e-9:
                                    price_diff_to_tp1 = abs(global_tp1_fibo - entry_price_fibo)
                                    
                                    # Ensure TP1 is actually profitable
                                    if (direction_fibo == "Long" and global_tp1_fibo > entry_price_fibo) or \
                                       (direction_fibo == "Short" and global_tp1_fibo < entry_price_fibo):
                                        profit_at_tp1_fibo = lot_size_fibo * price_diff_to_tp1
                                        rr_to_tp1_fibo = price_diff_to_tp1 / stop_distance_fibo
                                        temp_fibo_rr_to_tp1_list.append(rr_to_tp1_fibo)
                                    # Else, TP1 is not profitable or is behind SL/entry, RR is 0 or negative.
                                else: # Stop distance is zero, RR is undefined or infinite if TP is different.
                                    pass # rr_to_tp1_fibo remains 0.0
                                
                                summary_total_lots += lot_size_fibo
                                summary_total_risk_dollar += actual_risk_dollar_fibo 
                                summary_total_profit_at_primary_tp += profit_at_tp1_fibo

                                temp_fibo_entry_details_for_saving.append({
                                    "Fibo Level": f"{fibo_ratio_for_entry:.3f}",
                                    "Entry": round(entry_price_fibo, 5), 
                                    "SL": round(sl_price_fibo_final, 5),  
                                    "Lot": round(lot_size_fibo, 2),      
                                    "Risk $": round(actual_risk_dollar_fibo, 2), 
                                    "TP": round(global_tp1_fibo, 5), # Using global_tp1_fibo as the TP for this leg
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
            
    except ValueError: # Handles errors from float conversion of High/Low
        if st.session_state.get("swing_high_fibo_val_v2", "") or st.session_state.get("swing_low_fibo_val_v2", ""):
             st.sidebar.warning("กรอก High/Low (FIBO) เป็นตัวเลข")
    except Exception as e_fibo_summary:
        st.sidebar.error(f"คำนวณ FIBO Summary ไม่สำเร็จ: {e_fibo_summary}")
        # st.exception(e_fibo_summary) # Uncomment for debugging

elif mode == "CUSTOM":
    try:
        n_entry_custom = st.session_state.get("n_entry_custom_val_v2", 1)
        risk_pct_custom = st.session_state.get("risk_pct_custom_val_v2", 1.0)

        if risk_pct_custom <= 0:
            st.sidebar.warning("Risk % (CUSTOM) ต้องมากกว่า 0")
        elif n_entry_custom <=0:
            st.sidebar.warning("จำนวนไม้ (CUSTOM) ต้องมากกว่า 0")
        else:
            # Use active_balance_to_use defined in SEC 2
            risk_per_trade_custom_total = active_balance_to_use * (risk_pct_custom / 100.0)
            risk_dollar_per_entry_custom = risk_per_trade_custom_total / n_entry_custom
            
            temp_custom_rr_list = []
            temp_custom_legs_for_saving = [] 
            current_total_actual_risk_custom = 0.0 # To sum actual risk $ per leg
            
            for i in range(int(n_entry_custom)): # Ensure n_entry_custom is int
                entry_str = st.session_state.get(f"custom_entry_{i}_v3", "0.00")
                sl_str = st.session_state.get(f"custom_sl_{i}_v3", "0.00")
                tp_str = st.session_state.get(f"custom_tp_{i}_v3", "0.00")

                entry_val, sl_val, tp_val = 0.0, 0.0, 0.0
                lot_custom, actual_risk_dollar_custom, rr_custom, profit_at_user_tp_custom = 0.0, 0.0, 0.0, 0.0
                
                try:
                    entry_val = float(entry_str)
                    sl_val = float(sl_str)
                    tp_val = float(tp_str)

                    if sl_val == entry_val: # SL cannot be equal to Entry
                        stop_custom = 0
                        # actual_risk_dollar_custom will be risk_dollar_per_entry_custom if stop is 0 (handled below)
                    else:
                        stop_custom = abs(entry_val - sl_val)
                    
                    target_custom = abs(tp_val - entry_val) # Target distance

                    if stop_custom > 1e-9: # Epsilon check for valid stop distance
                        lot_custom = risk_dollar_per_entry_custom / stop_custom 
                        actual_risk_dollar_custom = lot_custom * stop_custom # Recalculate actual risk
                        if target_custom > 1e-9 and tp_val != entry_val : # Check valid target and TP is not at entry
                            rr_custom = target_custom / stop_custom
                            profit_at_user_tp_custom = lot_custom * target_custom
                        # else RR remains 0, profit remains 0
                        temp_custom_rr_list.append(rr_custom)
                        
                        # TP Recommendation (original logic)
                        if 0 <= rr_custom < 3.0 : # Check if rr_custom is valid before comparison
                            recommended_tp_target_distance = 3 * stop_custom # Target RR=3
                            recommended_tp_price = 0.0
                            # Determine direction based on SL vs Entry
                            if sl_val < entry_val: # Likely a Long trade
                                recommended_tp_price = entry_val + recommended_tp_target_distance
                            elif sl_val > entry_val: # Likely a Short trade
                                recommended_tp_price = entry_val - recommended_tp_target_distance
                            
                            if recommended_tp_price != 0.0: # if direction was determinable
                                custom_tp_recommendation_messages.append(
                                    f"ไม้ {i+1}: หากต้องการ RR≈3, TP ควรเป็น ≈ {recommended_tp_price:.5f} (TP ปัจจุบัน RR={rr_custom:.2f})"
                                )
                    else: # Stop distance is zero or too small
                         actual_risk_dollar_custom = risk_dollar_per_entry_custom # Assign full planned risk for this leg if stop is at entry
                         # lot_custom, rr_custom, profit_at_user_tp_custom remain 0.0
                    
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

                except ValueError: # Error converting E/SL/TP to float
                    current_total_actual_risk_custom += risk_dollar_per_entry_custom # Assume full risk for this leg on error
                    temp_custom_legs_for_saving.append({
                        "Entry": entry_str, "SL": sl_str, "TP": tp_str, # Save original strings
                        "Lot": "Error", "Risk $": f"{risk_dollar_per_entry_custom:.2f}", "RR": "Error"
                    })
            
            custom_entries_summary_sec3 = temp_custom_legs_for_saving 
            summary_total_risk_dollar = current_total_actual_risk_custom 

            if temp_custom_rr_list:
                valid_rrs = [r for r in temp_custom_rr_list if isinstance(r, (float, int)) and pd.notna(r) and r > 0]
                summary_avg_rr = np.mean(valid_rrs) if valid_rrs else 0.0
            else:
                summary_avg_rr = 0.0
                
    except ValueError: # Handles error from n_entry_custom conversion if it's not number
        st.sidebar.warning("กรอกข้อมูล CUSTOM ไม่ถูกต้อง (ตรวจสอบจำนวนไม้)")
    except Exception as e_custom_summary:
        st.sidebar.error(f"คำนวณ CUSTOM Summary ไม่สำเร็จ: {e_custom_summary}")
        # st.exception(e_custom_summary) # Uncomment for debugging

# --- Display Summaries in Sidebar ---
display_summary_info = False
if mode == "FIBO" and entry_data_summary_sec3 and (st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", "")):
    display_summary_info = True
elif mode == "CUSTOM" and custom_entries_summary_sec3 and st.session_state.get("n_entry_custom_val_v2", 0) > 0 :
    display_summary_info = True
elif mode == "CUSTOM" and custom_tp_recommendation_messages: # Also display if there are only recommendation messages
    display_summary_info = True


if display_summary_info:
    current_risk_display = 0.0
    active_balance_display = active_balance_to_use # From SEC 2

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
        # Check if specific input prompts were already shown for FIBO missing H/L or CUSTOM missing entries/risk
        # This generic message should appear if those specific conditions aren't met but summary is still not displayable
        # (e.g. FIBO H/L entered, but no Fibo levels selected)
        fibo_inputs_present = mode == "FIBO" and st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", "")
        fibo_no_levels_selected = fibo_inputs_present and not any(st.session_state.get("fibo_flags_v2", []))
        
        custom_inputs_present = mode == "CUSTOM" and st.session_state.get("n_entry_custom_val_v2",0) > 0 and st.session_state.get("risk_pct_custom_val_v2",0.0) > 0
        
        if (fibo_inputs_present and not entry_data_summary_sec3) or \
           (custom_inputs_present and not custom_entries_summary_sec3 and not custom_tp_recommendation_messages):
            st.sidebar.info("กรอกข้อมูลให้ครบถ้วนและถูกต้อง หรือเลือกเงื่อนไข (เช่น Fibo Levels) เพื่อคำนวณ Summary")

# --- End of modified SEC 2.3 (formerly SEC 3) ---

# ===================== SEC 2.4: SCALING MANAGER =======================
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    # ดึงค่าจาก session_state ถ้ามี, หรือใช้ค่า default ที่เหมาะสม
    # ค่า default เหล่านี้สามารถปรับเปลี่ยนได้ตามความต้องการ
    scaling_step_default = 0.25
    min_risk_pct_default = 0.5
    max_risk_pct_default = 5.0
    scaling_mode_default = 'Manual'
    
    # ตรวจสอบว่าค่า scaling step, min/max risk, และ mode ถูกโหลดจาก portfolio details หรือยัง
    # หากยังไม่ได้โหลด หรือไม่มีใน portfolio details ให้ใช้ค่า default ที่กำหนดไว้
    # หมายเหตุ: ส่วนนี้อาจจะต้องมีการปรับปรุงเพิ่มเติมหากต้องการให้ค่า default มาจาก Active Portfolio
    # ในกรณีที่ Portfolio มีการตั้งค่า Scaling Manager มาโดยเฉพาะ
    # สำหรับตอนนี้ จะใช้ค่าจาก session_state หรือ default ทั่วไปก่อน

    scaling_step = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=1.0, # สมมติว่า step ไม่เกิน 1%
        value=st.session_state.get('scaling_step', scaling_step_default), 
        step=0.01, format="%.2f", key='scaling_step' # key นี้จะใช้เก็บค่าใน session_state
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

    # อัปเดต session_state ด้วยค่าที่ผู้ใช้ป้อน (Streamlit ทำให้อัตโนมัติผ่าน key)
    # st.session_state.scaling_step = scaling_step
    # st.session_state.min_risk_pct = min_risk_pct
    # st.session_state.max_risk_pct = max_risk_pct
    # st.session_state.scaling_mode = scaling_mode

# ===================== SEC 2.4.1: SCALING SUGGESTION LOGIC =======================
# โหลดข้อมูล PlannedTradeLogs ทั้งหมดจาก cache
df_planned_logs_for_scaling_all = load_all_planned_trade_logs_from_gsheets() 

# กรองข้อมูลตาม Portfolio ที่ active อยู่ (ถ้ามีการเลือก)
active_portfolio_id_for_scaling = st.session_state.get('active_portfolio_id_gs', None)
df_planned_logs_for_scaling_filtered = pd.DataFrame() # Default to empty DataFrame

if active_portfolio_id_for_scaling and not df_planned_logs_for_scaling_all.empty:
    if 'PortfolioID' in df_planned_logs_for_scaling_all.columns:
        df_planned_logs_for_scaling_filtered = df_planned_logs_for_scaling_all[
            df_planned_logs_for_scaling_all['PortfolioID'] == str(active_portfolio_id_for_scaling)
        ].copy()
    else:
        # กรณีไม่พบคอลัมน์ PortfolioID (ไม่ควรเกิดขึ้นหาก header ถูกต้อง) ให้ใช้ข้อมูลทั้งหมด
        df_planned_logs_for_scaling_filtered = df_planned_logs_for_scaling_all.copy()
        # print("Warning: Scaling - PortfolioID column not found in logs, using all logs for performance.")
elif not df_planned_logs_for_scaling_all.empty: # หากไม่มีพอร์ต active, ใช้ log ทั้งหมด
    df_planned_logs_for_scaling_filtered = df_planned_logs_for_scaling_all.copy()
# หาก df_planned_logs_for_scaling_all ว่างเปล่า, df_planned_logs_for_scaling_filtered จะยังคงว่างเปล่า

# active_balance_to_use และ initial_risk_pct_from_portfolio ถูกกำหนดค่าใน SEC 2
winrate_perf, gain_perf, total_trades_perf = get_performance(df_planned_logs_for_scaling_filtered.copy(), mode="week")

current_risk_for_scaling = initial_risk_pct_from_portfolio # ค่าเริ่มต้นจาก portfolio
if mode == "FIBO":
    current_risk_for_scaling = st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio)
elif mode == "CUSTOM":
    current_risk_for_scaling = st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio)

# ค่า Scaling Manager จาก UI (SEC 2.4)
scaling_step_val = st.session_state.get('scaling_step', 0.25) 
max_risk_pct_val = st.session_state.get('max_risk_pct', 5.0)   
min_risk_pct_val = st.session_state.get('min_risk_pct', 0.5)   
current_scaling_mode = st.session_state.get('scaling_mode', 'Manual') 

suggest_risk = current_risk_for_scaling 
scaling_msg = f"Risk% ปัจจุบัน: {current_risk_for_scaling:.2f}%. "

if total_trades_perf > 0:
    # active_balance_to_use ถูกกำหนดใน SEC 2
    gain_threshold = 0.02 * active_balance_to_use 
    if winrate_perf > 55 and gain_perf > gain_threshold: # เงื่อนไข Scale Up
        suggest_risk = min(current_risk_for_scaling + scaling_step_val, max_risk_pct_val)
        scaling_msg += f"🎉 ผลงานดี! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f} (เป้า {gain_threshold:,.2f}). แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}%"
    elif winrate_perf < 45 or gain_perf < 0: # เงื่อนไข Scale Down
        suggest_risk = max(current_risk_for_scaling - scaling_step_val, min_risk_pct_val)
        scaling_msg += f"⚠️ ควรลด Risk! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f}. แนะนำลด Risk% เป็น {suggest_risk:.2f}%"
    else: # คง Risk เดิม
        scaling_msg += f"คง Risk% (Winrate {winrate_perf:.1f}%, กำไร {gain_perf:,.2f})"
else: # ไม่มีข้อมูล performance เพียงพอ
    scaling_msg += "ยังไม่มีข้อมูล Performance เพียงพอในสัปดาห์นี้ หรือ Performance อยู่ในเกณฑ์"

st.sidebar.info(scaling_msg)

# Apply suggested risk (ตรวจสอบด้วย epsilon เล็กน้อยสำหรับการเปรียบเทียบ float)
if abs(suggest_risk - current_risk_for_scaling) > 1e-3: 
    if current_scaling_mode == "Manual":
        if st.sidebar.button(f"ปรับ Risk% ตามคำแนะนำเป็น {suggest_risk:.2f}%"):
            if mode == "FIBO":
                st.session_state.risk_pct_fibo_val_v2 = suggest_risk 
            elif mode == "CUSTOM":
                st.session_state.risk_pct_custom_val_v2 = suggest_risk 
            st.rerun()
    elif current_scaling_mode == "Auto":
        # Auto-apply logic from user's original code structure
        risk_changed_by_auto = False
        if mode == "FIBO" and abs(st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio) - suggest_risk) > 1e-3:
            st.session_state.risk_pct_fibo_val_v2 = suggest_risk 
            risk_changed_by_auto = True
        elif mode == "CUSTOM" and abs(st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio) - suggest_risk) > 1e-3:
            st.session_state.risk_pct_custom_val_v2 = suggest_risk
            risk_changed_by_auto = True
        
        if risk_changed_by_auto:
            # Rerun only if risk actually changed by auto and is different from last auto suggestion
            if st.session_state.get(f"last_auto_suggested_risk_{mode}", current_risk_for_scaling) != suggest_risk: 
                st.session_state[f"last_auto_suggested_risk_{mode}"] = suggest_risk
                st.toast(f"Auto Scaling: ปรับ Risk% ของโหมด {mode} เป็น {suggest_risk:.2f}%", icon="⚙️")
                st.rerun()

# ===================== SEC 2.5: SAVE PLAN ACTION & DRAWDOWN LOCK =======================
# หมายเหตุ: ฟังก์ชัน save_plan_to_gsheets(plan_data_list, ...) ได้ถูกกำหนดไว้แล้วในส่วน Function Utility (หลัง SEC 1)
# จึงไม่จำเป็นต้องกำหนดซ้ำที่นี่

# โหลดข้อมูล PlannedTradeLogs ทั้งหมดจาก cache สำหรับการตรวจสอบ Drawdown
df_drawdown_check_all = load_all_planned_trade_logs_from_gsheets() 

# กรองข้อมูลตาม Portfolio ที่ active อยู่ (ถ้ามีการเลือก) สำหรับ Drawdown
active_portfolio_id_for_drawdown = st.session_state.get('active_portfolio_id_gs', None)
df_drawdown_check_filtered = pd.DataFrame() # Default to empty DataFrame

if active_portfolio_id_for_drawdown and not df_drawdown_check_all.empty:
    if 'PortfolioID' in df_drawdown_check_all.columns:
        df_drawdown_check_filtered = df_drawdown_check_all[
            df_drawdown_check_all['PortfolioID'] == str(active_portfolio_id_for_drawdown)
        ].copy()
    else:
        # กรณีไม่พบคอลัมน์ PortfolioID (ไม่ควรเกิดขึ้นหาก header ถูกต้อง) ให้ใช้ข้อมูลทั้งหมด
        df_drawdown_check_filtered = df_drawdown_check_all.copy()
        # print("Warning: Drawdown Check - PortfolioID column not found, using all logs.")
elif not df_drawdown_check_all.empty: # หากไม่มีพอร์ต active, ใช้ log ทั้งหมด
    df_drawdown_check_filtered = df_drawdown_check_all.copy()
# หาก df_drawdown_check_all ว่างเปล่า, df_drawdown_check_filtered จะยังคงว่างเปล่า


# active_balance_to_use ถูกกำหนดใน SEC 2
drawdown_today = get_today_drawdown(df_drawdown_check_filtered.copy(), active_balance_to_use) 
drawdown_limit_pct_val = st.session_state.get('drawdown_limit_pct', 2.0) # จาก SEC 2
drawdown_limit_abs = -abs(active_balance_to_use * (drawdown_limit_pct_val / 100.0)) 

if drawdown_today < 0: # Only show if there's actual drawdown from plans
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** <font color='red'>{drawdown_today:,.2f} USD</font>", unsafe_allow_html=True)
    st.sidebar.markdown(f"**ลิมิตขาดทุนที่ตั้งไว้:** {drawdown_limit_abs:,.2f} USD ({drawdown_limit_pct_val:.1f}% ของ {active_balance_to_use:,.2f} USD)")
else:
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** {drawdown_today:,.2f} USD")


active_portfolio_id = st.session_state.get('active_portfolio_id_gs', None)
active_portfolio_name = st.session_state.get('active_portfolio_name_gs', None)

asset_to_save = ""
risk_pct_to_save = 0.0
direction_to_save = "N/A" # Default direction
current_data_to_save = [] # This will be populated by summary data from SEC 2.3 (formerly SEC 3)

save_button_pressed_flag = False

# ตรวจสอบว่าปุ่ม Save ของโหมดไหนถูกกด (save_fibo, save_custom ถูก define ใน SEC 2.1 และ 2.2 ตามลำดับ)
if mode == "FIBO" and 'save_fibo' in st.session_state and st.session_state.save_fibo: # Check session_state for button press
    save_button_pressed_flag = True
elif mode == "CUSTOM" and 'save_custom' in st.session_state and st.session_state.save_custom: # Check session_state for button press
    save_button_pressed_flag = True


if mode == "FIBO":
    asset_to_save = st.session_state.get("asset_fibo_val_v2", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct_fibo_val_v2", 1.0)
    direction_to_save = st.session_state.get("direction_fibo_val_v2", "Long")
    # entry_data_summary_sec3 ถูกคำนวณใน SEC 2.3 (formerly SEC 3)
    current_data_to_save = entry_data_summary_sec3 # Ensure this var name is consistent or passed
elif mode == "CUSTOM":
    asset_to_save = st.session_state.get("asset_custom_val_v2", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct_custom_val_v2", 1.0)
    
    # Infer direction for CUSTOM mode based on custom_entries_summary_sec3 from SEC 2.3
    if custom_entries_summary_sec3: 
        long_count = 0
        short_count = 0
        valid_trade_count = 0
        for item in custom_entries_summary_sec3:
            try:
                entry_price_str = item.get("Entry")
                sl_price_str = item.get("SL")
                if entry_price_str is None or sl_price_str is None or \
                   str(entry_price_str).lower() == "error" or str(sl_price_str).lower() == "error": # Skip if error
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
            # else direction_to_save remains "N/A"
        # else direction_to_save remains "N/A"
    # else direction_to_save remains "N/A"
    current_data_to_save = custom_entries_summary_sec3 # Ensure this var name is consistent or passed


if save_button_pressed_flag:
    if not current_data_to_save:
        st.sidebar.warning(f"ไม่พบข้อมูลแผน ({mode}) ที่จะบันทึก กรุณาคำนวณแผนใน Summary ให้ถูกต้องก่อน")
    elif drawdown_today <= drawdown_limit_abs and drawdown_today != 0 : # drawdown_limit_abs is negative. drawdown_today can be 0.
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนจากแผนรวมวันนี้ {abs(drawdown_today):,.2f} ถึง/เกินลิมิต {abs(drawdown_limit_abs):,.2f} ({drawdown_limit_pct_val:.1f}%)"
        )
    elif not active_portfolio_id:
        st.sidebar.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ด้านบนก่อนบันทึกแผน")
    else:
        try:
            # Call the globally defined save_plan_to_gsheets function
            if save_plan_to_gsheets(current_data_to_save, mode, asset_to_save, risk_pct_to_save, direction_to_save, active_portfolio_id, active_portfolio_name):
                st.sidebar.success(f"บันทึกแผน ({mode}) สำหรับพอร์ต '{active_portfolio_name}' ลง Google Sheets สำเร็จ!")
                st.balloons()
                # Reset button states to prevent re-submission on next rerun without interaction
                if mode == "FIBO" and 'save_fibo' in st.session_state: st.session_state.save_fibo = False
                if mode == "CUSTOM" and 'save_custom' in st.session_state: st.session_state.save_custom = False
                
                # Optional: Clear relevant input fields after successful save by resetting their session_state keys
                # This part was commented out in the original, kept as is.
                # if mode == "FIBO":
                #     st.session_state.swing_high_fibo_val_v2 = ""
                #     st.session_state.swing_low_fibo_val_v2 = ""
                # elif mode == "CUSTOM":
                #     for i in range(st.session_state.get("n_entry_custom_val_v2",1)):
                #         st.session_state[f"custom_entry_{i}_v3"] = "0.00" # etc.
                # st.rerun() # To reflect cleared inputs and reset button state visually
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
            # entry_data_summary_sec3 ถูกคำนวณใน SEC 2.3 (เดิม SEC 3)
            if 'entry_data_summary_sec3' in locals() and entry_data_summary_sec3:
                try:
                    entry_df_main = pd.DataFrame(entry_data_summary_sec3)
                    # Ensure essential columns exist before trying to display them
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
                            tp1_main = low_tp + (high_tp - low_tp) * 1.618 # Consistent with RATIO_TP1_EFF
                            tp2_main = low_tp + (high_tp - low_tp) * 2.618 # Consistent with RATIO_TP2_EFF
                            tp3_main = low_tp + (high_tp - low_tp) * 4.236 # Consistent with RATIO_TP3_EFF
                        else: # Short
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
        # custom_entries_summary_sec3 ถูกคำนวณใน SEC 2.3 (เดิม SEC 3)
        if 'custom_entries_summary_sec3' in locals() and custom_entries_summary_sec3:
            try:
                custom_df_main = pd.DataFrame(custom_entries_summary_sec3)
                expected_cols_custom = ["Entry", "SL", "TP", "Lot", "Risk $", "RR"]
                cols_to_display_custom = [col for col in expected_cols_custom if col in custom_df_main.columns]

                if cols_to_display_custom:
                     st.dataframe(custom_df_main[cols_to_display_custom], hide_index=True, use_container_width=True)
                else:
                     st.info("ไม่พบคอลัมน์ที่คาดหวังสำหรับแสดงผล CUSTOM Trades.")
                
                # RR Warning (original logic)
                for i, row_data_dict in enumerate(custom_entries_summary_sec3): 
                    try:
                        rr_val_str = str(row_data_dict.get("RR", "0")).lower()
                        if rr_val_str == "error" or rr_val_str == "n/a" or rr_val_str == "" or rr_val_str == "nan":
                            continue 
                        
                        rr_val = float(rr_val_str)
                        if 0 <= rr_val < 2: # Check if RR is valid and between 0 and 2 (exclusive of 2)
                            entry_label = row_data_dict.get("ไม้ที่", i + 1) # Use "ไม้ที่" if available, else index
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
    asset_to_display = "OANDA:XAUUSD" # Default asset for TradingView
    current_asset_input_from_form = "" 

    if mode == "FIBO":
        # ใช้ key ใหม่จาก SEC 2.1 (เดิม SEC 2.2)
        current_asset_input_from_form = st.session_state.get("asset_fibo_val_v2", "XAUUSD") 
    elif mode == "CUSTOM":
        # ใช้ key ใหม่จาก SEC 2.2 (เดิม SEC 2.3)
        current_asset_input_from_form = st.session_state.get("asset_custom_val_v2", "XAUUSD") 
    
    # กำหนด asset_to_display โดยดูจาก plot_data ก่อน, ถ้าไม่มีให้ใช้จาก form input
    # 'plot_data' ถูกตั้งค่าใน SEC 7 (เดิม SEC 9) Trade Log Viewer
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
    
    balance_for_ai_sim = active_balance_to_use # active_balance_to_use ถูกกำหนดใน SEC 2
    report_title_suffix_planned = "(จากข้อมูลแผนเทรดทั้งหมด)"
    report_title_suffix_actual = "(จากข้อมูลผลการเทรดจริงทั้งหมด)"

    if active_portfolio_id_ai:
        report_title_suffix_planned = f"(สำหรับพอร์ต: '{active_portfolio_name_ai}' จากแผน)"
        report_title_suffix_actual = f"(สำหรับพอร์ต: '{active_portfolio_name_ai}' จากผลจริง)"
        st.info(f"AI Assistant กำลังวิเคราะห์ข้อมูลสำหรับพอร์ต: '{active_portfolio_name_ai}' (Balance เริ่มต้นจำลอง: {balance_for_ai_sim:,.2f} USD)")
    else:
        st.info(f"AI Assistant กำลังวิเคราะห์ข้อมูลจากแผนเทรดและผลการเทรดจริงทั้งหมด (ยังไม่ได้เลือก Active Portfolio - Balance เริ่มต้นจำลอง: {balance_for_ai_sim:,.2f} USD)")

    # --- ส่วนที่ 1: วิเคราะห์จาก PlannedTradeLogs (โค้ดเดิม) ---
    df_ai_logs_all_cached = load_all_planned_trade_logs_from_gsheets()
    df_ai_logs_to_analyze = pd.DataFrame() # Planned trades analysis
    
    if active_portfolio_id_ai and not df_ai_logs_all_cached.empty:
        if 'PortfolioID' in df_ai_logs_all_cached.columns:
            df_ai_logs_to_analyze = df_ai_logs_all_cached[df_ai_logs_all_cached['PortfolioID'] == str(active_portfolio_id_ai)].copy()
    elif not df_ai_logs_all_cached.empty:
        df_ai_logs_to_analyze = df_ai_logs_all_cached.copy()

    if df_ai_logs_to_analyze.empty:
        if df_ai_logs_all_cached.empty:
             st.markdown(f"### 🧠 AI Intelligence Report {report_title_suffix_planned}")
             st.info("ยังไม่มีข้อมูลแผนเทรดใน Log (Google Sheets) สำหรับวิเคราะห์")
        elif active_portfolio_id_ai : # มี log ทั้งหมด แต่ไม่มีของพอร์ตที่เลือก
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

        max_drawdown_ai_planned = 0.0 # Max Drawdown จากแผน (จำลอง)
        # ... (โค้ดคำนวณ Max Drawdown จาก Planned Logs เหมือนเดิม) ...
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
        # ... (โค้ดคำนวณ Win/Loss Day จาก Planned Logs เหมือนเดิม) ...
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
        # ... (ส่วนแสดง Insight จาก Planned Logs เหมือนเดิม) ...
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

    st.markdown("---") # เส้นคั่นระหว่าง Planned และ Actual Analysis

    # --- ส่วนที่ 2: วิเคราะห์จาก ActualTrades (Deals) ---
    df_actual_trades_all = load_actual_trades_from_gsheets()
    df_actual_trades_to_analyze = pd.DataFrame()

    if active_portfolio_id_ai and not df_actual_trades_all.empty:
        if 'PortfolioID' in df_actual_trades_all.columns:
            df_actual_trades_to_analyze = df_actual_trades_all[df_actual_trades_all['PortfolioID'] == str(active_portfolio_id_ai)].copy()
    elif not df_actual_trades_all.empty: # No active portfolio, use all actual trades
        df_actual_trades_to_analyze = df_actual_trades_all.copy()

    st.markdown(f"### 📈 AI Intelligence Report {report_title_suffix_actual}")
    if df_actual_trades_to_analyze.empty:
        if df_actual_trades_all.empty :
             st.info("ยังไม่มีข้อมูลผลการเทรดจริงใน Log (Google Sheets) สำหรับวิเคราะห์")
        elif active_portfolio_id_ai:
             st.info(f"ไม่พบข้อมูลผลการเทรดจริงใน Log สำหรับพอร์ต '{active_portfolio_name_ai}'.")
    else:
        # ตรวจสอบว่าคอลัมน์ 'Profit_Deal' มีอยู่จริง
        if 'Profit_Deal' not in df_actual_trades_to_analyze.columns:
            st.warning("ไม่พบคอลัมน์ 'Profit_Deal' ในข้อมูลผลการเทรดจริง ไม่สามารถคำนวณสถิติได้")
        else:
            # กรองเฉพาะ Deals ที่ไม่ใช่ Balance/Credit (ถ้ายังไม่ได้กรองตอน extract)
            # สมมติว่า Type_Deal ถูกโหลดมาด้วย
            if 'Type_Deal' in df_actual_trades_to_analyze.columns:
                df_trading_deals = df_actual_trades_to_analyze[
                    ~df_actual_trades_to_analyze['Type_Deal'].astype(str).str.lower().isin(['balance', 'credit'])
                ].copy()
            else:
                df_trading_deals = df_actual_trades_to_analyze.copy() # ถ้าไม่มี Type_Deal, ใช้ทั้งหมด (อาจต้องปรับปรุง)

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
                actual_gross_loss = abs(actual_losing_deals_df['Profit_Deal'].sum()) # abs for positive value

                actual_profit_factor = actual_gross_profit / actual_gross_loss if actual_gross_loss > 0 else float('inf') if actual_gross_profit > 0 else 0
                
                actual_avg_profit_deal = actual_gross_profit / actual_winning_deals_count if actual_winning_deals_count > 0 else 0
                actual_avg_loss_deal = actual_gross_loss / actual_losing_deals_count if actual_losing_deals_count > 0 else 0 # abs value
                
                # --- แสดงผล Metrics จาก Actual Trades ---
                st.write(f"- **จำนวน Deals ที่วิเคราะห์ (ผลจริง):** {actual_total_deals:,}")
                st.write(f"- **Deal-Level Win Rate (ผลจริง):** {actual_win_rate:.2f}%")
                st.write(f"- **กำไรทั้งหมด (Gross Profit - ผลจริง):** {actual_gross_profit:,.2f} USD")
                st.write(f"- **ขาดทุนทั้งหมด (Gross Loss - ผลจริง):** {actual_gross_loss:,.2f} USD")
                st.write(f"- **Profit Factor (Deal-Level - ผลจริง):** {actual_profit_factor:.2f}" if actual_profit_factor != float('inf') else "∞ (No Losses)")
                st.write(f"- **กำไรเฉลี่ยต่อ Deal ที่ชนะ (ผลจริง):** {actual_avg_profit_deal:,.2f} USD")
                st.write(f"- **ขาดทุนเฉลี่ยต่อ Deal ที่แพ้ (ผลจริง):** {actual_avg_loss_deal:,.2f} USD")

                # เพิ่ม AI Insights จาก Actual Trades ในอนาคตตรงนี้
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
with st.expander("📂  Ultimate Chart Dashboard Import & Processing", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # --- ฟังก์ชันสำหรับแยกข้อมูลจากเนื้อหาไฟล์ Statement (CSV) ---
    # This function is based on the user's provided version from the original main.py
    def extract_data_from_report_content(file_content_str_input):
        extracted_data = {'deals': pd.DataFrame(), 'orders': pd.DataFrame(), 'positions': pd.DataFrame(), 'balance_summary': {}, 'results_summary': {}}
        
        def safe_float_convert(value_str):
            if isinstance(value_str, (int, float)): return value_str
            try:
                clean_value = str(value_str).replace(" ", "").replace(",", "").replace("%", "")
                if clean_value.count('.') > 1: # Handle cases like "1.234.56" -> "1234.56"
                    parts = clean_value.split('.'); integer_part = "".join(parts[:-1]); decimal_part = parts[-1]
                    clean_value = integer_part + "." + decimal_part
                return float(clean_value)
            except (ValueError, TypeError, AttributeError): return None

        lines = []
        if isinstance(file_content_str_input, str): 
            lines = file_content_str_input.strip().split('\n')
        elif isinstance(file_content_str_input, bytes): 
            lines = file_content_str_input.decode('utf-8', errors='replace').strip().split('\n')
        else:
            # st.error("Error: Invalid file_content type for processing in extract_data_from_report_content.")
            print("Error: Invalid file_content type in extract_data_from_report_content.")
            return extracted_data 
        
        if not lines: 
            # st.warning("Warning: File content is empty after splitting lines in extract_data_from_report_content.")
            print("Warning: File content is empty in extract_data_from_report_content.")
            return extracted_data

        section_raw_headers = {
            "Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit",
            "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment", # Note the double comma for potential empty column
            "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment",
        }
        # Ensure column names are unique and suitable for DataFrame
        expected_cleaned_columns = {
            "Positions": ["Time_Pos", "Position_ID", "Symbol_Pos", "Type_Pos", "Volume_Pos", "Price_Open_Pos", "S_L_Pos", "T_P_Pos", "Time_Close_Pos", "Price_Close_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos"],
            "Orders": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Filler_Ord","Comment_Ord"], # Added Filler for the double comma
            "Deals": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal"],
        }
        section_order_for_tables = ["Positions", "Orders", "Deals"] # Define order for parsing
        section_header_indices = {}
        
        for line_idx, current_line_str in enumerate(lines):
            stripped_line = current_line_str.strip()
            for section_name, raw_header_template in section_raw_headers.items():
                if section_name not in section_header_indices: # Find first occurrence
                    first_col_of_template = raw_header_template.split(',')[0].strip()
                    # Check if the line starts with the first column and contains the raw header (loosely)
                    if stripped_line.startswith(first_col_of_template) and raw_header_template in stripped_line: # Ensure it's the actual header
                        section_header_indices[section_name] = line_idx
                        break 
        
        for table_idx, section_name in enumerate(section_order_for_tables):
            section_key_lower = section_name.lower()
            # extracted_data[section_key_lower] = pd.DataFrame() # Already initialized

            if section_name in section_header_indices:
                header_line_num = section_header_indices[section_name]
                data_start_line_num = header_line_num + 1
                data_end_line_num = len(lines) # Default to end of file

                # Find where the next section starts to limit current section's data
                for next_table_name_idx in range(table_idx + 1, len(section_order_for_tables)):
                    next_table_section_name = section_order_for_tables[next_table_name_idx]
                    if next_table_section_name in section_header_indices:
                        data_end_line_num = section_header_indices[next_table_section_name]
                        break
                
                current_table_data_lines = []
                
                for line_num_for_data in range(data_start_line_num, data_end_line_num):
                    line_content_for_data = lines[line_num_for_data].strip()
                    
                    if not line_content_for_data: # Skip empty lines
                        if any(current_table_data_lines): # If we already have data, an empty line might be a separator
                             pass # Or break, depending on strictness. For now, allow continuation.
                        else:
                             continue # Leading empty lines

                    # Stop if encountering lines that indicate end of transactional data or start of summary
                    if line_content_for_data.startswith(("Balance:", "Credit Facility:", "Floating P/L:", "Equity:", "Results", "Total Net Profit:")):
                        break
                    
                    # Stop if it looks like another known header line
                    is_another_header_line = False
                    for other_sec_name, other_raw_hdr_template in section_raw_headers.items():
                        if other_sec_name != section_name and \
                           line_content_for_data.startswith(other_raw_hdr_template.split(',')[0]) and \
                           other_raw_hdr_template in line_content_for_data:
                            is_another_header_line = True
                            break
                    if is_another_header_line:
                        break
                    
                    # Specific filtering for "Deals" to remove "balance" type rows and rows with missing essential IDs
                    if section_name == "Deals":
                        cols_in_line = [col.strip() for col in line_content_for_data.split(',')]
                        is_balance_type_row = False
                        if len(cols_in_line) > 3 and "balance" in str(cols_in_line[3]).lower():
                            is_balance_type_row = True
                        
                        missing_essential_identifiers = False
                        if len(cols_in_line) < 3: 
                            missing_essential_identifiers = True
                        elif not cols_in_line[0] or not cols_in_line[1] or not cols_in_line[2]: # Time, Deal_ID, Symbol
                            missing_essential_identifiers = True

                        if is_balance_type_row or missing_essential_identifiers:
                            if st.session_state.get("debug_statement_processing_v2", False):
                                print(f"DEBUG [extract_data]: SKIPPING Deals line: '{line_content_for_data}' (Balance: {is_balance_type_row}, MissingIDs: {missing_essential_identifiers})")
                            continue 
                        
                    current_table_data_lines.append(line_content_for_data)

                if current_table_data_lines:
                    csv_data_str = "\n".join(current_table_data_lines)
                    try:
                        # Use names from expected_cleaned_columns, ensure correct number of names for pd.read_csv
                        col_names_for_df = expected_cleaned_columns[section_name]
                        df_section = pd.read_csv(io.StringIO(csv_data_str),
                                                 header=None, 
                                                 names=col_names_for_df,
                                                 skipinitialspace=True, 
                                                 on_bad_lines='warn', # 'skip' or 'warn'
                                                 engine='python', 
                                                 dtype=str, # Read all as string first
                                                 # Make sure an appropriate number of columns is expected for orders
                                                 # For orders, if "Comment" can be empty and there's a filler
                                                 # `usecols` might be useful if number of delimiters is inconsistent
                                                 )
                        df_section.dropna(how='all', inplace=True) # Drop rows that are entirely NaN
                        
                        # Re-align columns to expected_cleaned_columns, adding missing ones as empty
                        final_cols = expected_cleaned_columns[section_name]
                        for col in final_cols:
                            if col not in df_section.columns: 
                                df_section[col] = "" # Add missing columns with empty strings
                        df_section = df_section[final_cols] # Ensure correct order and all expected columns

                        # Additional filtering at DataFrame level if needed (e.g., after type conversion)
                        # The string-level "Deals" filtering for "balance" type should be primary.
                        if section_name == "Deals" and not df_section.empty:
                             if "Symbol_Deal" in df_section.columns: 
                                 df_section = df_section[df_section["Symbol_Deal"].astype(str).str.strip() != ""]
                        
                        if not df_section.empty:
                            extracted_data[section_key_lower] = df_section

                    except pd.errors.ParserError as e_parse_df:
                        if st.session_state.get("debug_statement_processing_v2", False):
                            print(f"ParserError for {section_name}: {e_parse_df}. Data: {csv_data_str[:300]}")
                    except Exception as e_gen_parse_df:
                        if st.session_state.get("debug_statement_processing_v2", False):
                            print(f"Error parsing table data for {section_name}: {e_gen_parse_df}")
        
        # --- Balance Summary Extraction (from original code) ---
        balance_summary_dict = {}
        balance_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Balance:"): 
                balance_start_line_idx = i
                break
        if balance_start_line_idx != -1:
            for i in range(balance_start_line_idx, min(balance_start_line_idx + 8, len(lines))): # Look in next few lines
                line_stripped = lines[i].strip()
                if not line_stripped : continue
                if line_stripped.startswith(("Results", "Total Net Profit:")) and i > balance_start_line_idx: break # Stop if results section starts
                
                parts = [p.strip() for p in line_stripped.split(',') if p.strip()]
                temp_key = ""
                val_expected_next = False
                for part_val in parts:
                    if not part_val: continue
                    if ':' in part_val:
                        key_str, val_str = part_val.split(':', 1)
                        key_clean = key_str.strip().replace(" ", "_").replace(".", "").replace("/","_").lower()
                        val_strip = val_str.strip()
                        if val_strip: 
                            balance_summary_dict[key_clean] = safe_float_convert(val_strip.split(' ')[0]) # Take first part if "USD" follows
                            val_expected_next = False
                            temp_key = ""
                        else: 
                            temp_key = key_clean
                            val_expected_next = True
                    elif val_expected_next and temp_key:
                        balance_summary_dict[temp_key] = safe_float_convert(part_val.split(' ')[0])
                        temp_key = ""
                        val_expected_next = False
        
        essential_balance_keys = ["balance", "credit_facility", "floating_p_l", "equity", "free_margin", "margin", "margin_level"]
        for k_b in essential_balance_keys:
            if k_b not in balance_summary_dict: 
                balance_summary_dict[k_b] = None # Use None for missing, will be "" in GSheet
        extracted_data['balance_summary'] = balance_summary_dict
        
        # --- Results Summary Extraction (from original code) ---
        results_summary_dict = {}
        stat_definitions_map = { # From original user code
            "Total Net Profit": "Total_Net_Profit", "Gross Profit": "Gross_Profit", "Gross Loss": "Gross_Loss", "Profit Factor": "Profit_Factor", "Expected Payoff": "Expected_Payoff",
            "Recovery Factor": "Recovery_Factor", "Sharpe Ratio": "Sharpe_Ratio", "Balance Drawdown Absolute": "Balance_Drawdown_Absolute", "Balance Drawdown Maximal": "Balance_Drawdown_Maximal",
            "Balance Drawdown Relative": "Balance_Drawdown_Relative_Percent", # This key implies the % value
            "Total Trades": "Total_Trades", "Short Trades (won %)": "Short_Trades", # This key for count
            "Long Trades (won %)": "Long_Trades", # This key for count
            "Profit Trades (% of total)": "Profit_Trades", # This key for count
            "Loss Trades (% of total)": "Loss_Trades", # This key for count
            "Largest profit trade": "Largest_profit_trade", "Largest loss trade": "Largest_loss_trade",
            "Average profit trade": "Average_profit_trade", "Average loss trade": "Average_loss_trade", 
            "Maximum consecutive wins ($)": "Maximum_consecutive_wins_Count", # This key for count of wins
            "Maximal consecutive profit (count)": "Maximal_consecutive_profit_Amount", # This key for profit amount
            "Average consecutive wins": "Average_consecutive_wins",
            "Maximum consecutive losses ($)": "Maximum_consecutive_losses_Count", # This key for count of losses
            "Maximal consecutive loss (count)": "Maximal_consecutive_loss_Amount", # This key for loss amount
            "Average consecutive losses": "Average_consecutive_losses"
        }
        results_start_line_idx = -1
        results_section_processed_lines = 0
        max_lines_for_results = 35 # Increased slightly for more coverage

        for i_res, line_res in enumerate(lines):
            if results_start_line_idx == -1 and (line_res.strip().startswith("Results") or line_res.strip().startswith("Total Net Profit:")):
                results_start_line_idx = i_res
                continue # Start processing from next line

            if results_start_line_idx != -1 and results_section_processed_lines < max_lines_for_results:
                line_stripped_res = line_res.strip()
                if not line_stripped_res:
                    if results_section_processed_lines > 2: break # Empty line likely means end of section
                    else: continue 
                
                results_section_processed_lines += 1
                row_cells = [cell.strip() for cell in line_stripped_res.split(',')]

                for c_idx, cell_content in enumerate(row_cells):
                    if not cell_content: continue
                    current_label = cell_content.replace(':', '').strip()

                    if current_label in stat_definitions_map:
                        gsheet_key = stat_definitions_map[current_label]
                        # Try to find the value in the next few cells
                        for k_val_search in range(1, 5): # Look ahead up to 4 cells for the value
                            if (c_idx + k_val_search) < len(row_cells):
                                raw_value_from_cell = row_cells[c_idx + k_val_search]
                                if raw_value_from_cell: # If cell is not empty
                                    value_part_before_paren = raw_value_from_cell.split('(')[0].strip()
                                    numeric_value = safe_float_convert(value_part_before_paren)
                                    if numeric_value is not None:
                                        results_summary_dict[gsheet_key] = numeric_value
                                        # Extract parenthesized value if it exists
                                        if '(' in raw_value_from_cell and ')' in raw_value_from_cell:
                                            try:
                                                paren_content_str = raw_value_from_cell[raw_value_from_cell.find('(')+1:raw_value_from_cell.find(')')].strip().replace('%','')
                                                paren_numeric_value = safe_float_convert(paren_content_str)
                                                if paren_numeric_value is not None:
                                                    # Assign parenthesized values to their specific keys
                                                    if current_label == "Balance Drawdown Maximal": results_summary_dict["Balance_Drawdown_Maximal_Percent"] = paren_numeric_value
                                                    elif current_label == "Balance Drawdown Relative": results_summary_dict["Balance_Drawdown_Relative_Amount"] = paren_numeric_value # The % is primary, this is amount
                                                    elif current_label == "Short Trades (won %)": results_summary_dict["Short_Trades_won_Percent"] = paren_numeric_value
                                                    elif current_label == "Long Trades (won %)": results_summary_dict["Long_Trades_won_Percent"] = paren_numeric_value
                                                    elif current_label == "Profit Trades (% of total)": results_summary_dict["Profit_Trades_Percent_of_total"] = paren_numeric_value
                                                    elif current_label == "Loss Trades (% of total)": results_summary_dict["Loss_Trades_Percent_of_total"] = paren_numeric_value
                                                    elif current_label == "Maximum consecutive wins ($)": results_summary_dict["Maximum_consecutive_wins_Profit"] = paren_numeric_value # This is $ value
                                                    elif current_label == "Maximal consecutive profit (count)": results_summary_dict["Maximal_consecutive_profit_Count"] = paren_numeric_value # This is count
                                                    elif current_label == "Maximum consecutive losses ($)": results_summary_dict["Maximum_consecutive_losses_Profit"] = paren_numeric_value # This is $ value
                                                    elif current_label == "Maximal consecutive loss (count)": results_summary_dict["Maximal_consecutive_loss_Count"] = paren_numeric_value # This is count
                                            except Exception: pass # Ignore errors in parsing parenthesized content
                                        break # Found value, move to next label
                if line_stripped_res.startswith("Average consecutive losses"): break # Likely end of stats
            elif results_start_line_idx != -1 and results_section_processed_lines >= max_lines_for_results:
                break # Stop after processing a reasonable number of lines for results
        
        extracted_data['results_summary'] = results_summary_dict
        return extracted_data
    # --- END: ฟังก์ชัน extract_data_from_report_content ---

    # --- START: ฟังก์ชันใหม่/แก้ไข สำหรับบันทึกข้อมูลพร้อม Deduplication และ Header Handling ---
    def save_transactional_data_to_gsheets(ws, df_input, unique_id_col, expected_headers_with_portfolio, data_type_name, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        if df_input is None or df_input.empty:
            return True, 0, 0 
        try:
            if ws is None: 
                print(f"Error ({data_type_name}): Worksheet object is None. Cannot proceed.")
                return False, 0, 0

            current_headers = []
            header_check_successful = False
            if ws.row_count > 0:
                try:
                    current_headers = ws.row_values(1)
                    header_check_successful = True
                except gspread.exceptions.APIError as e_api_header:
                    if hasattr(e_api_header, 'response') and e_api_header.response and e_api_header.response.status_code == 429: 
                        print(f"Warning: Quota exceeded for '{ws.title}' headers. Assuming update needed.")
                        current_headers = [] 
                    else: raise 
                except Exception as e_get_header:
                    print(f"Warning: Could not get header for '{ws.title}': {e_get_header}. Assuming update needed.")
                    current_headers = []
            
            if not header_check_successful or not current_headers or all(h == "" for h in current_headers) or set(current_headers) != set(expected_headers_with_portfolio):
                try:
                    ws.update([expected_headers_with_portfolio], value_input_option='USER_ENTERED')
                    print(f"Info: Headers written/updated for '{ws.title}'.")
                except Exception as e_update_header:
                    st.error(f"Failed to write/update headers for '{ws.title}': {e_update_header}")
                    return False, 0, 0

            existing_ids = set()
            if ws.row_count > 1: 
                try:
                    all_sheet_records = ws.get_all_records(
                        expected_headers=expected_headers_with_portfolio, # Use full headers for get_all_records
                        numericise_ignore=['all'] 
                    )
                    if all_sheet_records:
                        df_existing_sheet_data = pd.DataFrame(all_sheet_records)
                        # Filter by PortfolioID first, then get unique IDs for that portfolio
                        if 'PortfolioID' in df_existing_sheet_data.columns and unique_id_col in df_existing_sheet_data.columns:
                            df_existing_sheet_data['PortfolioID'] = df_existing_sheet_data['PortfolioID'].astype(str)
                            # Ensure portfolio_id is also string for comparison
                            df_portfolio_data = df_existing_sheet_data[df_existing_sheet_data['PortfolioID'] == str(portfolio_id)]
                            if not df_portfolio_data.empty:
                                existing_ids = set(df_portfolio_data[unique_id_col].astype(str).str.strip().tolist())
                except gspread.exceptions.APIError as e_api_get_all:
                    if hasattr(e_api_get_all, 'response') and e_api_get_all.response and e_api_get_all.response.status_code == 429: 
                        print(f"Warning: Quota exceeded getting records from '{ws.title}' for {data_type_name}. Deduplication incomplete.")
                    else: 
                        print(f"Warning: API error getting records from '{ws.title}' for {data_type_name} ({e_api_get_all}).")
                except Exception as e_get_records:
                    print(f"Warning: Could not get existing records from '{ws.title}' for {data_type_name} ({e_get_records}).")
            
            df_to_check = df_input.copy()
            if unique_id_col not in df_to_check.columns:
                st.error(f"Unique ID column '{unique_id_col}' MISSING from extracted '{data_type_name}'. All data treated as new.")
                new_df = df_to_check 
            else:
                df_to_check[unique_id_col] = df_to_check[unique_id_col].astype(str).str.strip()
                new_df = df_to_check[~df_to_check[unique_id_col].isin(existing_ids)]

            num_new = len(new_df)
            num_duplicates_skipped = len(df_to_check) - num_new

            if new_df.empty:
                return True, num_new, num_duplicates_skipped

            # Add PortfolioID, PortfolioName, SourceFile, ImportBatchID to new_df before creating list_of_lists
            new_df_to_save = new_df.copy() # Work on a copy
            new_df_to_save["PortfolioID"] = str(portfolio_id)
            new_df_to_save["PortfolioName"] = str(portfolio_name)
            new_df_to_save["SourceFile"] = str(source_file_name)
            new_df_to_save["ImportBatchID"] = str(import_batch_id)
            
            # Ensure all expected columns are present in the order of expected_headers_with_portfolio
            final_df_for_append = pd.DataFrame(columns=expected_headers_with_portfolio)
            for col_h in expected_headers_with_portfolio:
                if col_h in new_df_to_save.columns:
                    final_df_for_append[col_h] = new_df_to_save[col_h]
                else:
                    final_df_for_append[col_h] = "" # Add empty string for missing columns
            
            list_of_lists = final_df_for_append.astype(str).replace('nan', '').replace('None','').fillna("").values.tolist()

            if list_of_lists:
                ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
            return True, num_new, num_duplicates_skipped

        except gspread.exceptions.APIError as e_api:
            st.error(f"❌ ({ws.title}) Google Sheets API Error ({data_type_name}): {e_api.args[0] if e_api.args else 'Unknown API error'}")
            return False, 0, 0
        except Exception as e:
            st.error(f"❌ ({ws.title}) เกิดข้อผิดพลาดในการบันทึก {data_type_name}: {e}")
            # st.exception(e) # Uncomment for full traceback
            return False, 0, 0

    def save_deals_to_actual_trades(ws, df_deals_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        # Original expected headers for deals + new portfolio/tracking cols
        expected_headers_deals = ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_deals_input, "Deal_ID", expected_headers_deals, "Deals", portfolio_id, portfolio_name, source_file_name, import_batch_id)

    def save_orders_to_gsheets(ws, df_orders_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_orders = ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Filler_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_orders_input, "Order_ID_Ord", expected_headers_orders, "Orders", portfolio_id, portfolio_name, source_file_name, import_batch_id)

    def save_positions_to_gsheets(ws, df_positions_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        expected_headers_positions = ["Time_Pos", "Position_ID", "Symbol_Pos", "Type_Pos", "Volume_Pos", "Price_Open_Pos", "S_L_Pos", "T_P_Pos", "Time_Close_Pos", "Price_Close_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
        return save_transactional_data_to_gsheets(ws, df_positions_input, "Position_ID", expected_headers_positions, "Positions", portfolio_id, portfolio_name, source_file_name, import_batch_id)
    
    def save_results_summary_to_gsheets(ws, balance_summary_data, results_summary_data, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
        try:
            if ws is None:
                st.error(f"({WORKSHEET_STATEMENT_SUMMARIES}) Worksheet object is None. Cannot save summary.")
                return False, "Worksheet object is None"
            
            # Define all expected headers for the StatementSummaries sheet
            expected_headers = [
                "Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", 
                "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Credit_Facility", # Added Credit_Facility
                "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", 
                "Recovery_Factor", "Sharpe_Ratio", 
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
            if ws.row_count > 0:
                try: current_headers_ws = ws.row_values(1)
                except Exception: pass
            if not current_headers_ws or all(h == "" for h in current_headers_ws) or set(current_headers_ws) != set(expected_headers):
                ws.update([expected_headers], value_input_option='USER_ENTERED')
            
            new_summary_row_data = {h: None for h in expected_headers} # Initialize with None
            new_summary_row_data.update({
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "PortfolioID": str(portfolio_id), 
                "PortfolioName": str(portfolio_name), "SourceFile": str(source_file_name), 
                "ImportBatchID": str(import_batch_id) 
            })

            balance_key_map = { # Map from extracted keys to GSheet keys
                "balance":"Balance", "equity":"Equity", "free_margin":"Free_Margin", 
                "margin":"Margin", "floating_p_l":"Floating_P_L", "margin_level":"Margin_Level",
                "credit_facility": "Credit_Facility" # Added from essential_balance_keys
            }
            if isinstance(balance_summary_data, dict): 
                for k_extract, k_gsheet in balance_key_map.items():
                    if k_extract in balance_summary_data:
                        new_summary_row_data[k_gsheet] = balance_summary_data[k_extract]
            
            if isinstance(results_summary_data, dict): 
                for k_gsheet_expected in expected_headers: # Iterate through all GSheet headers
                    if k_gsheet_expected in results_summary_data: # If data was extracted for this GSheet header
                         new_summary_row_data[k_gsheet_expected] = results_summary_data[k_gsheet_expected]
            
            # --- Deduplication based on content for the same PortfolioID ---
            # Define a subset of critical fields for creating a "fingerprint" of the summary
            comparison_keys = [ # Keys that define uniqueness of a summary record's content
                "Balance", "Equity", "Total_Net_Profit", "Total_Trades", 
                "Balance_Drawdown_Maximal", "Profit_Factor"
            ] # Add more keys if needed for stricter comparison
            
            new_summary_fingerprint_values = []
            for k_comp in comparison_keys:
                val = new_summary_row_data.get(k_comp)
                try: new_summary_fingerprint_values.append(f"{float(val):.2f}" if pd.notna(val) else "None")
                except (ValueError, TypeError): new_summary_fingerprint_values.append(str(val).strip() if pd.notna(val) else "None")
            new_summary_fingerprint = tuple(new_summary_fingerprint_values)

            if ws.row_count > 1: 
                try:
                    existing_summaries_records = ws.get_all_records(expected_headers=expected_headers, numericise_ignore=['all'])
                    df_existing_summaries = pd.DataFrame(existing_summaries_records)
                    
                    if not df_existing_summaries.empty and 'PortfolioID' in df_existing_summaries.columns:
                        # Filter for the current portfolio
                        df_portfolio_summaries = df_existing_summaries[df_existing_summaries['PortfolioID'].astype(str) == str(portfolio_id)]
                        
                        for _, existing_row in df_portfolio_summaries.iterrows():
                            existing_summary_comparable_values = []
                            for k_comp in comparison_keys:
                                val = existing_row.get(k_comp)
                                try: existing_summary_comparable_values.append(f"{float(val):.2f}" if pd.notna(val) else "None")
                                except (ValueError, TypeError): existing_summary_comparable_values.append(str(val).strip() if pd.notna(val) else "None")
                            
                            if tuple(existing_summary_comparable_values) == new_summary_fingerprint:
                                # st.info(f"({ws.title}) ข้อมูล Summary ที่มีเนื้อหาคล้ายกันสำหรับพอร์ต '{portfolio_name}' นี้มีอยู่แล้ว จะไม่บันทึกซ้ำ (BatchID: {import_batch_id})")
                                return True, "skipped_duplicate_content" # Indicate skipped due to content duplication
                except gspread.exceptions.APIError as e_api_get_sum: 
                    if hasattr(e_api_get_sum, 'response') and e_api_get_sum.response and e_api_get_sum.response.status_code == 429: 
                        print(f"Warning: Quota exceeded getting summaries from '{ws.title}'. Append will proceed.")
                    else:
                        print(f"Warning: API error getting summaries from '{ws.title}' ({e_api_get_sum}). Append will proceed.")
                except Exception as e_get_sum_records:
                    print(f"Warning: Could not get existing summaries from '{ws.title}' ({e_get_sum_records}). Append will proceed.")

            final_row_values = [str(new_summary_row_data.get(h, "")).strip() for h in expected_headers]
            ws.append_rows([final_row_values], value_input_option='USER_ENTERED')
            return True, "saved_new" # Indicate new summary was saved
        except gspread.exceptions.APIError as e_api: 
            st.error(f"❌ ({ws.title}) Google Sheets API Error (Summary): {e_api.args[0] if e_api.args else 'Unknown API error'}")
            return False, f"API Error: {e_api.args[0] if e_api.args else 'Unknown API error'}"
        except Exception as e: 
            st.error(f"❌ ({ws.title}) เกิดข้อผิดพลาดในการบันทึก Statement Summaries: {e}")
            # st.exception(e)
            return False, f"Exception: {e}"
    # --- END: ฟังก์ชัน save_... ---

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement Report (CSV) เพื่อประมวลผลและบันทึก")
    
    uploaded_file_statement = st.file_uploader( 
        "ลากและวางไฟล์ Statement Report (CSV) ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["csv"],
        key="ultimate_stmt_uploader_v7_final" 
    )

    # The debug checkbox was in the original code.
    st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้ + Log การทำงานบางส่วนใน Console)", value=False, key="debug_statement_processing_v2")
    
    active_portfolio_id_for_actual = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_for_actual = st.session_state.get('active_portfolio_name_gs', None)

    if uploaded_file_statement is not None: # Check if a file is uploaded
        file_name_for_saving = uploaded_file_statement.name
        file_size_for_saving = uploaded_file_statement.size 
        
        file_hash_for_saving = ""
        try:
            uploaded_file_statement.seek(0) 
            file_content_for_hash = uploaded_file_statement.read()
            uploaded_file_statement.seek(0) # Reset pointer for further processing
            file_hash_for_saving = hashlib.md5(file_content_for_hash).hexdigest()
        except Exception as e_hash:
            file_hash_for_saving = f"hash_error_{random.randint(1000,9999)}" # Fallback hash
            print(f"Warning: Could not compute MD5 hash for file: {e_hash}")

        if not active_portfolio_id_for_actual: 
            st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.")
            st.stop() # Stop execution if no active portfolio
        
        st.info(f"ไฟล์ที่อัปโหลด: {file_name_for_saving} (ขนาด: {file_size_for_saving} bytes, Hash: {file_hash_for_saving})")
        gc_for_sheets = get_gspread_client()
        if not gc_for_sheets: 
            st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client ได้")
            st.stop()

        ws_dict = {}
        default_sheet_specs = {"rows": "1000", "cols": "26"} # Increased default cols
        
        # Ensure WORKSHEET_UPLOAD_HISTORY is defined (it is in SEC 0)
        # worksheet_definitions includes headers for creation and checking
        worksheet_definitions = {
            WORKSHEET_UPLOAD_HISTORY: {"rows": "1000", "cols": "10", "headers": ["UploadTimestamp", "PortfolioID", "PortfolioName", "FileName", "FileSize", "FileHash", "Status", "ImportBatchID", "Notes"]},
            WORKSHEET_ACTUAL_TRADES: {"rows": "2000", "cols": "18", "headers": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_ACTUAL_ORDERS: {"rows": "1000", "cols": "16", "headers": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Filler_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_ACTUAL_POSITIONS: {"rows": "1000", "cols": "17", "headers": ["Time_Pos", "Position_ID", "Symbol_Pos", "Type_Pos", "Volume_Pos", "Price_Open_Pos", "S_L_Pos", "T_P_Pos", "Time_Close_Pos", "Price_Close_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]},
            WORKSHEET_STATEMENT_SUMMARIES: {"rows": "1000", "cols": "46", "headers": ["Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Credit_Facility", "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", "Total_Trades", "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count", "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count", "Average_consecutive_wins", "Average_consecutive_losses"]}
        }

        all_sheets_successfully_accessed_or_created = True 
        sh_trade_log = None 
        try:
            sh_trade_log = gc_for_sheets.open(GOOGLE_SHEET_NAME)
            for ws_name, specs in worksheet_definitions.items():
                try:
                    ws_dict[ws_name] = sh_trade_log.worksheet(ws_name)
                    current_ws_headers_check = []
                    if ws_dict[ws_name].row_count > 0 :
                        try: current_ws_headers_check = ws_dict[ws_name].row_values(1)
                        except Exception: pass 
                    if not current_ws_headers_check or all(h=="" for h in current_ws_headers_check) or set(current_ws_headers_check) != set(specs["headers"]):
                        if "headers" in specs: 
                            ws_dict[ws_name].update([specs["headers"]], value_input_option='USER_ENTERED')
                            print(f"Info: Ensured/Updated headers for '{ws_name}' sheet.")
                except gspread.exceptions.WorksheetNotFound:
                    print(f"Info: Worksheet '{ws_name}' not found. Creating it now...")
                    try:
                        new_ws = sh_trade_log.add_worksheet(title=ws_name, rows=specs.get("rows", default_sheet_specs["rows"]), cols=specs.get("cols", default_sheet_specs["cols"]))
                        ws_dict[ws_name] = new_ws 
                        if "headers" in specs: 
                            new_ws.update([specs["headers"]], value_input_option='USER_ENTERED') 
                            print(f"Info: Created worksheet '{ws_name}' and added headers.")
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
            st.error(f"❌ Google Sheets API Error (Opening Spreadsheet or Initial Worksheet Access): {e_api.args[0] if e_api.args else 'Unknown API error'}.")
            st.stop()
        except Exception as e_setup: 
            st.error(f"❌ เกิดข้อผิดพลาดในการเข้าถึง Spreadsheet หรือสร้าง Worksheet: {type(e_setup).__name__} - {str(e_setup)[:200]}...")
            st.stop()

        for ws_name_key in worksheet_definitions.keys(): # Final check
            if ws_name_key not in ws_dict or ws_dict[ws_name_key] is None:
                st.error(f"❌ ไม่สามารถเข้าถึง Worksheet '{ws_name_key}' ได้สมบูรณ์ โปรดตรวจสอบและลองอีกครั้ง")
                st.stop()  
        
        import_batch_id = str(uuid.uuid4()) 
        current_upload_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        is_duplicate_file_found = False 
        try:
            # Ensure WORKSHEET_UPLOAD_HISTORY is in ws_dict
            if WORKSHEET_UPLOAD_HISTORY in ws_dict and ws_dict[WORKSHEET_UPLOAD_HISTORY].row_count > 1:
                history_records = ws_dict[WORKSHEET_UPLOAD_HISTORY].get_all_records(numericise_ignore=['all'])
                for record in history_records:
                    try: record_file_size_val = int(float(str(record.get("FileSize","0")).replace(",","")))
                    except: record_file_size_val = 0
                    
                    # Stricter check: all conditions must match for a duplicate
                    if str(record.get("PortfolioID","")) == str(active_portfolio_id_for_actual) and \
                       record.get("FileName","") == file_name_for_saving and \
                       record_file_size_val == file_size_for_saving and \
                       record.get("FileHash","") == file_hash_for_saving and \
                       str(record.get("Status","")).startswith("Success"): # Only count if previous was fully successful
                        is_duplicate_file_found = True
                        break 
        except Exception as e_hist_read:
            print(f"Warning: Could not read UploadHistory for duplicate file check: {e_hist_read}")

        # Log initial processing attempt
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
            file_content_str = uploaded_file_statement.getvalue().decode("utf-8", errors="replace") # Ensure it's decoded
            
            with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {file_name_for_saving}..."): 
                extracted_sections = extract_data_from_report_content(file_content_str)
            
            if st.session_state.get("debug_statement_processing_v2", False): 
                st.write("--- DEBUG: Extracted Sections ---")
                for sec_name, sec_data in extracted_sections.items():
                    st.write(f"**Section: {sec_name}**")
                    if isinstance(sec_data, pd.DataFrame): st.dataframe(sec_data.head())
                    else: st.json(sec_data)
                st.write("--- END DEBUG: Extracted Sections ---")


            if not extracted_sections or not any(isinstance(df, pd.DataFrame) and not df.empty for df_name, df in extracted_sections.items() if df_name in ['deals', 'orders', 'positions']):
                if not extracted_sections.get('balance_summary') and not extracted_sections.get('results_summary'):
                    overall_processing_successful = False # Mark as failed if no data at all
                    save_results_details['Extraction'] = {'ok': False, 'notes': "Failed to extract any meaningful data from file."}
                    st.warning("ไม่สามารถแยกข้อมูลที่มีความหมายจากไฟล์ได้ หรือไฟล์อาจจะไม่มีข้อมูล Deals/Orders/Positions และ Summary")


            if overall_processing_successful: # Proceed only if initial extraction seems okay or has summary
                st.subheader("💾 กำลังบันทึกข้อมูลส่วนต่างๆไปยัง Google Sheets...")
                
                deals_df = extracted_sections.get('deals', pd.DataFrame())
                ok_d, new_d, skip_d = save_deals_to_actual_trades(ws_dict.get(WORKSHEET_ACTUAL_TRADES), deals_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Deals'] = {'ok': ok_d, 'new': new_d, 'skipped': skip_d, 'notes': f"Deals: New={new_d}, Skipped={skip_d}, Success={ok_d}"}
                if ok_d: st.write(f"✔️ ({WORKSHEET_ACTUAL_TRADES}) Deals: เพิ่ม {new_d}, ข้าม {skip_d}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_TRADES}) Deals: การบันทึกล้มเหลว")
                if new_d > 0: any_new_transactional_data_added = True
                if not ok_d: overall_processing_successful = False
                
                orders_df = extracted_sections.get('orders', pd.DataFrame())
                ok_o, new_o, skip_o = save_orders_to_gsheets(ws_dict.get(WORKSHEET_ACTUAL_ORDERS), orders_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Orders'] = {'ok': ok_o, 'new': new_o, 'skipped': skip_o, 'notes': f"Orders: New={new_o}, Skipped={skip_o}, Success={ok_o}"}
                if ok_o: st.write(f"✔️ ({WORKSHEET_ACTUAL_ORDERS}) Orders: เพิ่ม {new_o}, ข้าม {skip_o}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_ORDERS}) Orders: การบันทึกล้มเหลว")
                if new_o > 0: any_new_transactional_data_added = True
                if not ok_o: overall_processing_successful = False

                positions_df = extracted_sections.get('positions', pd.DataFrame())
                ok_p, new_p, skip_p = save_positions_to_gsheets(ws_dict.get(WORKSHEET_ACTUAL_POSITIONS), positions_df, active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving, import_batch_id)
                save_results_details['Positions'] = {'ok': ok_p, 'new': new_p, 'skipped': skip_p, 'notes': f"Positions: New={new_p}, Skipped={skip_p}, Success={ok_p}"}
                if ok_p: st.write(f"✔️ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: เพิ่ม {new_p}, ข้าม {skip_p}.")
                else: st.error(f"❌ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: การบันทึกล้มเหลว")
                if new_p > 0: any_new_transactional_data_added = True
                if not ok_p: overall_processing_successful = False
                
                balance_summary = extracted_sections.get('balance_summary', {})
                results_summary_data_ext = extracted_sections.get('results_summary', {})
                summary_save_ok = True # Assume true unless save fails
                summary_status_note = "no_data_to_save"

                should_save_summary_now = True
                if is_duplicate_file_found and not any_new_transactional_data_added: 
                    st.info(f"({WORKSHEET_STATEMENT_SUMMARIES}) ข้ามการบันทึก Summary: ไฟล์ซ้ำและไม่พบข้อมูล Transaction ใหม่")
                    summary_status_note = "skipped_duplicate_file_no_new_transactions"
                    save_results_details['Summary'] = {'ok': True, 'status': summary_status_note, 'notes': "Summary: Skipped (duplicate file with no new transactional data)."}
                    should_save_summary_now = False
                
                if should_save_summary_now:
                    if balance_summary or results_summary_data_ext: # Only save if there's something to save
                        summary_ok, summary_status_note = save_results_summary_to_gsheets( 
                            ws_dict.get(WORKSHEET_STATEMENT_SUMMARIES), balance_summary, results_summary_data_ext, 
                            active_portfolio_id_for_actual, active_portfolio_name_for_actual, 
                            file_name_for_saving, import_batch_id
                        )
                        save_results_details['Summary'] = {'ok': summary_ok, 'status': summary_status_note, 'notes': f"Summary: Processed, Status={summary_status_note}, Success={summary_ok}"}
                        if summary_ok: 
                             if summary_status_note == "saved_new":
                                st.write(f"✔️ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary Data: บันทึกข้อมูลใหม่สำเร็จ")
                             elif summary_status_note == "skipped_duplicate_content":
                                st.info(f"({WORKSHEET_STATEMENT_SUMMARIES}) Summary Data: ข้อมูลเนื้อหาซ้ำกับที่มีอยู่แล้ว ไม่บันทึกเพิ่ม")
                        else: 
                            st.error(f"❌ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary Data: การบันทึกล้มเหลว ({summary_status_note})")
                        summary_save_ok = summary_ok # Update overall success flag
                    else: 
                        summary_status_note = "no_data_to_save"
                        save_results_details['Summary'] = {'ok': True, 'status': summary_status_note, 'notes': "Summary: No balance/results data in file to save."}
                
                if not summary_save_ok: # If summary save was attempted and failed
                    overall_processing_successful = False
        
        except UnicodeDecodeError as e_decode_main:
            st.error(f"เกิดข้อผิดพลาดในการ Decode ไฟล์: {e_decode_main}. กรุณาตรวจสอบ Encoding ของไฟล์ (ควรเป็น UTF-8).")
            overall_processing_successful = False
            save_results_details['MainError'] = {'ok': False, 'notes': f"UnicodeDecodeError: {e_decode_main}"}
        except gspread.exceptions.APIError as e_api_main: 
            st.error(f"❌ Google Sheets API Error (Main Processing): {e_api_main.args[0] if e_api_main.args else 'Unknown API error'}.")
            overall_processing_successful = False
            save_results_details['MainError'] = {'ok': False, 'notes': f"APIError: {e_api_main.args[0] if e_api_main.args else 'Unknown API error'}"}
        except Exception as e_main:
            st.error(f"เกิดข้อผิดพลาดระหว่างประมวลผลหลัก: {type(e_main).__name__} - {str(e_main)[:200]}...")
            overall_processing_successful = False
            save_results_details['MainError'] = {'ok': False, 'notes': f"MainError: {type(e_main).__name__} - {str(e_main)[:100]}"}
            # st.exception(e_main) # Uncomment for full traceback during dev

        final_processing_notes_list = [res.get('notes', '') for res in save_results_details.values() if isinstance(res, dict) and res.get('notes')]
        final_notes_str = " | ".join(filter(None, final_processing_notes_list))[:49999] # Limit notes length
        if not final_notes_str and overall_processing_successful : final_notes_str = "Processing complete successfully."
        elif not final_notes_str and not overall_processing_successful : final_notes_str = "Processing failed with unspecified errors."


        final_status = "Failed" 
        user_message_display = "การประมวลผลไฟล์ล้มเหลว"

        if overall_processing_successful:
            summary_op_status = save_results_details.get('Summary', {}).get('status', 'unknown')
            
            if any_new_transactional_data_added or summary_op_status == 'saved_new':
                final_status = "Success"
                user_message_display = "ประมวลผลไฟล์สำเร็จและมีการเพิ่มข้อมูลใหม่!"
                if any_new_transactional_data_added and summary_op_status == 'skipped_duplicate_content':
                     user_message_display = "ประมวลผลไฟล์สำเร็จ มีการเพิ่มข้อมูล Deals/Orders/Positions ใหม่ แต่ข้าม Summary ที่มีเนื้อหาซ้ำ"
                elif not any_new_transactional_data_added and summary_op_status == 'saved_new':
                     user_message_display = "ประมวลผลไฟล์สำเร็จ ข้อมูล Deals/Orders/Positions ซ้ำทั้งหมด แต่มีการบันทึก Summary ใหม่"
            elif is_duplicate_file_found and not any_new_transactional_data_added and \
                 (summary_op_status == 'skipped_duplicate_file_no_new_transactions' or summary_op_status == 'skipped_duplicate_content' or summary_op_status == 'no_data_to_save'):
                final_status = "Success_DuplicateFile_NoNewData"
                user_message_display = f"ไฟล์ '{file_name_for_saving}' เป็นไฟล์ซ้ำ (หรือไม่มีข้อมูลใหม่) และไม่พบรายการ Transactional หรือ Summary ใหม่ที่จะเพิ่ม"
            elif not any_new_transactional_data_added and \
                 (summary_op_status == 'no_data_to_save' or summary_op_status == 'skipped_duplicate_content'):
                final_status = "Success_NoNewRecords"
                user_message_display = "ประมวลผลไฟล์สำเร็จ แต่ไม่พบข้อมูล Transactional หรือ Summary ใหม่ที่จะเพิ่ม (ข้อมูลอาจซ้ำทั้งหมด หรือไฟล์ไม่มีข้อมูล)"
            else: 
                final_status = "Success_NoNewDataOrPartial" # A general success if no new data but no errors
                user_message_display = "ประมวลผลไฟล์สำเร็จ แต่ไม่พบข้อมูลใหม่ที่จะเพิ่ม หรือข้อมูลบางส่วนอาจซ้ำ"
        
        # Display final user message based on status
        if final_status.startswith("Success"):
            if "มีการเพิ่มข้อมูลใหม่" in user_message_display:
                st.balloons(); st.success(user_message_display)
            else:
                st.info(user_message_display)
        else: # Failed case, error messages should have been shown by specific exceptions
            if 'MainError' not in save_results_details and 'Extraction' not in save_results_details: # If no specific error was caught by st.error
                 st.error(user_message_display)


        # Update UploadHistory with the final status and notes
        try:
            history_rows_for_update = ws_dict[WORKSHEET_UPLOAD_HISTORY].get_all_values() 
            row_to_update_idx = None
            for idx_update, row_val_update in reversed(list(enumerate(history_rows_for_update))): # Search from bottom up
                if len(row_val_update) > 7 and row_val_update[7] == import_batch_id: # Index 7 is ImportBatchID
                    row_to_update_idx = idx_update + 1 # gspread rows are 1-indexed
                    break
            
            if row_to_update_idx:
                ws_dict[WORKSHEET_UPLOAD_HISTORY].batch_update([
                    {'range': f'G{row_to_update_idx}', 'values': [[final_status]]},      # Column G for Status
                    {'range': f'I{row_to_update_idx}', 'values': [[final_notes_str]]}  # Column I for Notes
                ], value_input_option='USER_ENTERED')
                print(f"Info: Updated UploadHistory for ImportBatchID '{import_batch_id}' to '{final_status}'.")
            else: 
                print(f"Warning: Could not find ImportBatchID '{import_batch_id}' in {WORKSHEET_UPLOAD_HISTORY} to update final status.")
        except Exception as e_update_hist: 
            print(f"Warning: Could not update final status in {WORKSHEET_UPLOAD_HISTORY} for batch {import_batch_id}: {e_update_hist}")
        
        # Clear the uploader state to prevent reprocessing the same file on rerun unless re-uploaded
        st.session_state.ultimate_stmt_uploader_v7_final = True 
        # st.rerun() # Consider if a rerun is always needed here. 
        # It might be better to let user continue interaction.
        # If rerun is needed to refresh some display dependent on these GSheets, then uncomment.

    st.markdown("---")
    
# --- End of SEC 6 (formerly SEC 7) ---

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
