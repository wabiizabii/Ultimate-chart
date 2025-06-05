# ===================== UltimateChart V2.0.0 =======================
# Version: 2.0.0
# Last Updated: 2025-06-04
# Description: Integrated actual balance handling from statement uploads
#              for improved trade planning and sidebar display.
# ==================================================================

# ============== PART 1.1: IMPORTS ==============
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import plotly.express as px
# import google.generativeai as genai #  Removed if not used, or keep if planned
import gspread
import plotly.graph_objects as go
import random
import io
import uuid
import hashlib

# ============== PART 1.2: PAGE CONFIGURATION ==============
st.set_page_config(page_title="Ultimate-Chart", layout="wide")

# ============== PART 1.3: GLOBAL CONSTANTS & CONFIG ==============
GOOGLE_SHEET_NAME = "TradeLog" # ชื่อ Google Sheet
WORKSHEET_PORTFOLIOS = "Portfolios"
WORKSHEET_PLANNED_LOGS = "PlannedTradeLogs"
WORKSHEET_ACTUAL_TRADES = "ActualTrades" # For Deals
WORKSHEET_ACTUAL_ORDERS = "ActualOrders"
WORKSHEET_ACTUAL_POSITIONS = "ActualPositions"
WORKSHEET_STATEMENT_SUMMARIES = "StatementSummaries"
WORKSHEET_UPLOAD_HISTORY = "UploadHistory"

# Default values
DEFAULT_ACCOUNT_BALANCE = 10000.0
DEFAULT_RISK_PERCENT = 1.0

# ============== PART 1.4: SESSION STATE INITIALIZATION ==============
if 'uploader_key_version' not in st.session_state:
    st.session_state.uploader_key_version = 0
if 'latest_statement_equity' not in st.session_state: # For storing equity from the latest statement
    st.session_state.latest_statement_equity = None
if 'current_account_balance' not in st.session_state: # This will be the primary balance for calculations
    st.session_state.current_account_balance = DEFAULT_ACCOUNT_BALANCE
if 'active_portfolio_name_gs' not in st.session_state:
    st.session_state.active_portfolio_name_gs = ""
if 'active_portfolio_id_gs' not in st.session_state:
    st.session_state.active_portfolio_id_gs = None
if 'current_portfolio_details' not in st.session_state:
    st.session_state.current_portfolio_details = None
if 'plot_data' not in st.session_state:
    st.session_state.plot_data = None

# Initializing other session states if they are commonly used across sections or reset
# For trade planning inputs (FIBO)
if "asset_fibo_val_v2" not in st.session_state: st.session_state.asset_fibo_val_v2 = "XAUUSD"
if "risk_pct_fibo_val_v2" not in st.session_state: st.session_state.risk_pct_fibo_val_v2 = DEFAULT_RISK_PERCENT
if "direction_fibo_val_v2" not in st.session_state: st.session_state.direction_fibo_val_v2 = "Long"
if "swing_high_fibo_val_v2" not in st.session_state: st.session_state.swing_high_fibo_val_v2 = ""
if "swing_low_fibo_val_v2" not in st.session_state: st.session_state.swing_low_fibo_val_v2 = ""
if "fibo_flags_v2" not in st.session_state: st.session_state.fibo_flags_v2 = [True] * 5 # Default 5 fibo levels

# For trade planning inputs (CUSTOM)
if "asset_custom_val_v2" not in st.session_state: st.session_state.asset_custom_val_v2 = "XAUUSD"
if "risk_pct_custom_val_v2" not in st.session_state: st.session_state.risk_pct_custom_val_v2 = DEFAULT_RISK_PERCENT
if "n_entry_custom_val_v2" not in st.session_state: st.session_state.n_entry_custom_val_v2 = 2
for i in range(st.session_state.get("n_entry_custom_val_v2", 2)): # Initialize based on default N
    if f"custom_entry_{i}_v3" not in st.session_state: st.session_state[f"custom_entry_{i}_v3"] = "0.00"
    if f"custom_sl_{i}_v3" not in st.session_state: st.session_state[f"custom_sl_{i}_v3"] = "0.00"
    if f"custom_tp_{i}_v3" not in st.session_state: st.session_state[f"custom_tp_{i}_v3"] = "0.00"

# For portfolio management UI
if 'exp_pf_type_select_v8_key' not in st.session_state:
    st.session_state.exp_pf_type_select_v8_key = ""


# ============== PART 1.5: GOOGLE SHEETS UTILITY FUNCTIONS ==============
@st.cache_resource # Use cache_resource for gspread client object
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

@st.cache_data(ttl=300) # Cache ข้อมูลไว้ 5 นาที
def load_portfolios_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        # st.error("ไม่สามารถโหลดข้อมูลพอร์ตได้: Client Google Sheets ไม่พร้อมใช้งาน") # Reduced verbosity for background loads
        print("Error: GSpread client not available for loading portfolios.")
        return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PORTFOLIOS)
        records = worksheet.get_all_records(numericise_ignore=['all']) # Read all as string first
        
        if not records:
            # st.info(f"ไม่พบข้อมูลใน Worksheet '{WORKSHEET_PORTFOLIOS}'.")
            print(f"Info: No records found in Worksheet '{WORKSHEET_PORTFOLIOS}'.") #
            return pd.DataFrame()
        
        df_portfolios = pd.DataFrame(records) #
        
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
                # Replace empty strings with NaN before converting to numeric
                df_portfolios[col] = df_portfolios[col].replace('', np.nan) #
                df_portfolios[col] = pd.to_numeric(df_portfolios[col], errors='coerce').fillna(0) #
                if target_type == int:
                    df_portfolios[col] = df_portfolios[col].astype(int) #

        if 'EnableScaling' in df_portfolios.columns:
             df_portfolios['EnableScaling'] = df_portfolios['EnableScaling'].astype(str).str.upper().map({'TRUE': True, 'YES': True, '1': True, 'FALSE': False, 'NO': False, '0': False}).fillna(False) #

        date_cols = ['CompetitionEndDate', 'TargetEndDate', 'CreationDate'] #
        for col in date_cols:
            if col in df_portfolios.columns:
                df_portfolios[col] = pd.to_datetime(df_portfolios[col], errors='coerce').dt.strftime('%Y-%m-%d %H:%M:%S') #
        return df_portfolios
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'.") #
        return pd.DataFrame()
    except gspread.exceptions.APIError as e_api:
        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:
            st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios (Quota Exceeded). ลองอีกครั้งในภายหลัง") #
        else:
            st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios (API Error): {e_api}") #
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios: {e}") #
        return pd.DataFrame()

@st.cache_data(ttl=180)
def load_all_planned_trade_logs_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        print("Warning: GSpread client not available for loading planned trade logs.") #
        return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        records = worksheet.get_all_records(numericise_ignore=['all']) #
        
        if not records:
            return pd.DataFrame()
        
        df_logs = pd.DataFrame(records) #
        
        if 'Timestamp' in df_logs.columns:
            df_logs['Timestamp'] = pd.to_datetime(df_logs['Timestamp'], errors='coerce') #
        
        cols_to_numeric_planned = ['Risk $', 'RR', 'Entry', 'SL', 'TP', 'Lot', 'Risk %'] #
        for col_viewer in cols_to_numeric_planned:
            if col_viewer in df_logs.columns:
                df_logs[col_viewer] = df_logs[col_viewer].replace('', np.nan) # Treat empty strings as NaN
                df_logs[col_viewer] = pd.to_numeric(df_logs[col_viewer], errors='coerce') #
                if col_viewer == 'Risk $': df_logs[col_viewer] = df_logs[col_viewer].fillna(0) #


        if 'PortfolioID' in df_logs.columns:
            df_logs['PortfolioID'] = df_logs['PortfolioID'].astype(str) #
        
        return df_logs
    except gspread.exceptions.WorksheetNotFound:
        print(f"Warning: Worksheet '{WORKSHEET_PLANNED_LOGS}' not found.") #
        return pd.DataFrame()
    except gspread.exceptions.APIError as e_api:
        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:
            print(f"APIError (Quota Exceeded) loading planned trade logs: {e_api.args[0] if e_api.args else 'Unknown quota error'}") #
        else:
            print(f"APIError loading planned trade logs: {e_api}") #
        return pd.DataFrame()
    except Exception as e:
        print(f"Unexpected error loading all planned trade logs: {e}") #
        return pd.DataFrame()

@st.cache_data(ttl=180)
def load_actual_trades_from_gsheets(): # Loads "Deals"
    gc = get_gspread_client()
    if gc is None:
        print("Warning: GSpread client not available for loading actual trades (deals).") #
        return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_ACTUAL_TRADES)
        records = worksheet.get_all_records(numericise_ignore=['all']) #
        
        if not records:
            return pd.DataFrame()
        
        df_actual_trades = pd.DataFrame(records) #
        
        if 'Time_Deal' in df_actual_trades.columns:
            df_actual_trades['Time_Deal'] = pd.to_datetime(df_actual_trades['Time_Deal'], errors='coerce') #

        numeric_cols_actual = [
            'Volume_Deal', 'Price_Deal', 'Commission_Deal', 
            'Fee_Deal', 'Swap_Deal', 'Profit_Deal', 'Balance_Deal'
        ] #
        for col in numeric_cols_actual:
            if col in df_actual_trades.columns:
                df_actual_trades[col] = df_actual_trades[col].replace('', np.nan) #
                df_actual_trades[col] = pd.to_numeric(df_actual_trades[col], errors='coerce') #

        if 'PortfolioID' in df_actual_trades.columns:
            df_actual_trades['PortfolioID'] = df_actual_trades['PortfolioID'].astype(str) #
        
        return df_actual_trades
    except gspread.exceptions.WorksheetNotFound:
        print(f"Warning: Worksheet '{WORKSHEET_ACTUAL_TRADES}' not found.") #
        return pd.DataFrame()
    except gspread.exceptions.APIError as e_api:
        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:
            print(f"APIError (Quota Exceeded) loading actual trades from '{WORKSHEET_ACTUAL_TRADES}'.") #
        else:
            print(f"APIError loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e_api}") #
        return pd.DataFrame()
    except Exception as e:
        print(f"Unexpected error loading actual trades from '{WORKSHEET_ACTUAL_TRADES}': {e}") #
        return pd.DataFrame()

# +++ FUNCTION TO LOAD STATEMENT SUMMARIES (NEW) +++
@st.cache_data(ttl=180) # Cache for 3 minutes
def load_statement_summaries_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        print("Error: GSpread client not available for loading statement summaries.")
        return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_STATEMENT_SUMMARIES)
        # numericise_ignore=['all'] is important to handle mixed types and formatting issues
        records = worksheet.get_all_records(numericise_ignore=['all']) 
        
        if not records:
            print(f"Info: No records found in Worksheet '{WORKSHEET_STATEMENT_SUMMARIES}'.")
            return pd.DataFrame()
        
        df_summaries = pd.DataFrame(records)
        
        # Convert necessary columns
        if 'PortfolioID' in df_summaries.columns:
            df_summaries['PortfolioID'] = df_summaries['PortfolioID'].astype(str)
        
        if 'Equity' in df_summaries.columns:
            # Clean common issues like commas before converting to numeric
            df_summaries['Equity'] = df_summaries['Equity'].astype(str).str.replace(',', '', regex=False)
            df_summaries['Equity'] = pd.to_numeric(df_summaries['Equity'], errors='coerce')
        
        if 'Timestamp' in df_summaries.columns:
            df_summaries['Timestamp'] = pd.to_datetime(df_summaries['Timestamp'], errors='coerce')
            
        return df_summaries
    except gspread.exceptions.WorksheetNotFound:
        print(f"Warning: Worksheet '{WORKSHEET_STATEMENT_SUMMARIES}' not found during summary load.")
        return pd.DataFrame()
    except gspread.exceptions.APIError as e_api:
        if hasattr(e_api, 'response') and e_api.response and e_api.response.status_code == 429:
            print(f"APIError (Quota Exceeded) loading statement summaries: {e_api.args[0] if e_api.args else 'Unknown quota error'}")
        else:
            print(f"APIError loading statement summaries: {e_api}")
        return pd.DataFrame()
    except Exception as e:
        print(f"Unexpected error loading statement summaries: {e}")
        return pd.DataFrame()
# +++ END FUNCTION TO LOAD STATEMENT SUMMARIES +++

# ============== PART 1.6: GENERAL UTILITY FUNCTIONS ==============
# (Your existing get_today_drawdown, get_performance, save_plan_to_gsheets, save_new_portfolio_to_gsheets should be here)
def get_today_drawdown(log_source_df):
    if log_source_df.empty:
        return 0.0
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        # Ensure Timestamp is datetime before strftime
        if 'Timestamp' not in log_source_df.columns or not pd.api.types.is_datetime64_any_dtype(log_source_df['Timestamp']):
            log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce') #
        
        log_source_df_cleaned = log_source_df.dropna(subset=['Timestamp']) #
        if 'Risk $' not in log_source_df_cleaned.columns:
            return 0.0
            
        df_today = log_source_df_cleaned[log_source_df_cleaned["Timestamp"].dt.strftime("%Y-%m-%d") == today_str] #
        # Ensure "Risk $" is numeric; it should be after load_all_planned_trade_logs_from_gsheets
        drawdown = df_today["Risk $"].sum()  #
        return float(drawdown) if pd.notna(drawdown) else 0.0
    except KeyError as e: 
        print(f"KeyError in get_today_drawdown: {e}") #
        return 0.0
    except Exception as e: 
        print(f"Exception in get_today_drawdown: {e}") #
        return 0.0

def get_performance(log_source_df, mode="week"):
    if log_source_df.empty: return 0.0, 0.0, 0 #
    try:
        if 'Timestamp' not in log_source_df.columns or not pd.api.types.is_datetime64_any_dtype(log_source_df['Timestamp']):
            log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce') #
        
        log_source_df_cleaned = log_source_df.dropna(subset=['Timestamp']) #
        if 'Risk $' not in log_source_df_cleaned.columns:
            return 0.0, 0.0, 0 #

        now = datetime.now() #
        if mode == "week":
            week_start_date = now - pd.Timedelta(days=now.weekday()) #
            df_period = log_source_df_cleaned[log_source_df_cleaned["Timestamp"] >= week_start_date.replace(hour=0, minute=0, second=0, microsecond=0)] #
        else:  # month
            month_start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) #
            df_period = log_source_df_cleaned[log_source_df_cleaned["Timestamp"] >= month_start_date] #
        
        win = df_period[df_period["Risk $"] > 0].shape[0] #
        loss = df_period[df_period["Risk $"] <= 0].shape[0] # Assuming 0 or negative is a loss or break-even
        total_trades = win + loss #
        winrate = (100 * win / total_trades) if total_trades > 0 else 0.0 #
        gain = df_period["Risk $"].sum() #
        return float(winrate), float(gain) if pd.notna(gain) else 0.0, int(total_trades)
    except KeyError as e: 
        print(f"KeyError in get_performance: {e}") #
        return 0.0, 0.0, 0
    except Exception as e: 
        print(f"Exception in get_performance: {e}") #
        return 0.0, 0.0, 0

def save_plan_to_gsheets(plan_data_list, trade_mode_arg, asset_name, risk_percentage, trade_direction, portfolio_id, portfolio_name):
    gc = get_gspread_client()
    if not gc:
        st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกแผนได้") #
        return False
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        ws = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        timestamp_now = datetime.now() #
        rows_to_append = []
        expected_headers_plan = [ 
            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",
            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"
        ] #
        current_headers_plan = []
        if ws.row_count > 0:
            try: current_headers_plan = ws.row_values(1) #
            except Exception: current_headers_plan = []
        
        if not current_headers_plan or all(h == "" for h in current_headers_plan) or set(current_headers_plan) != set(expected_headers_plan):
            ws.update([expected_headers_plan], value_input_option='USER_ENTERED') #

        for idx, plan_entry in enumerate(plan_data_list):
            log_id = f"{timestamp_now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000,9999)}-{idx}" #
            row_data = {
                "LogID": log_id, "PortfolioID": str(portfolio_id), "PortfolioName": str(portfolio_name), #
                "Timestamp": timestamp_now.strftime("%Y-%m-%d %H:%M:%S"), "Asset": str(asset_name), #
                "Mode": str(trade_mode_arg), "Direction": str(trade_direction),  #
                "Risk %": str(risk_percentage) if pd.notna(risk_percentage) else "", #
                "Fibo Level": str(plan_entry.get("Fibo Level", "")),  #
                "Entry": str(plan_entry.get("Entry", "")), #
                "SL": str(plan_entry.get("SL", "")),  #
                "TP": str(plan_entry.get("TP", "")), #
                "Lot": str(plan_entry.get("Lot", "")),  #
                "Risk $": str(plan_entry.get("Risk $", "")),  #
                "RR": str(plan_entry.get("RR", "")) #
            }
            rows_to_append.append([row_data.get(h, "") for h in expected_headers_plan]) #
        if rows_to_append:
            ws.append_rows(rows_to_append, value_input_option='USER_ENTERED') #
            # Clear cache for planned logs after saving
            if hasattr(load_all_planned_trade_logs_from_gsheets, 'clear'):
                load_all_planned_trade_logs_from_gsheets.clear() #
            return True
        return False
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PLANNED_LOGS}'.") #
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกแผน: {e}") #
        return False

def save_new_portfolio_to_gsheets(portfolio_data_dict):
    gc = get_gspread_client() 
    if not gc:
        st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client เพื่อบันทึกพอร์ตได้") #
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
        ] #
        
        current_sheet_headers = []
        if ws.row_count > 0:
            try: current_sheet_headers = ws.row_values(1) #
            except Exception: pass 
        
        if not current_sheet_headers or all(h == "" for h in current_sheet_headers) or set(current_sheet_headers) != set(expected_gsheet_headers_portfolio):
             ws.update([expected_gsheet_headers_portfolio], value_input_option='USER_ENTERED')  #

        new_row_values = [str(portfolio_data_dict.get(header, "")).strip() for header in expected_gsheet_headers_portfolio] #
        ws.append_row(new_row_values, value_input_option='USER_ENTERED') #
        # Clear cache for portfolios after saving new one
        if hasattr(load_portfolios_from_gsheets, 'clear'):
            load_portfolios_from_gsheets.clear() #
        return True
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}'. กรุณาสร้างชีตนี้ก่อน และใส่ Headers ให้ถูกต้อง") #
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกพอร์ตใหม่ไปยัง Google Sheets: {e}") #
        st.exception(e)  #
        return False

# ===================== SEC 1: PORTFOLIO SELECTION (Sidebar) =======================
df_portfolios_gs = load_portfolios_from_gsheets() #

st.sidebar.markdown("---") #
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)") #

portfolio_names_list_gs = [""] # Start with an empty option for deselection
if not df_portfolios_gs.empty and 'PortfolioName' in df_portfolios_gs.columns:
    valid_portfolio_names = sorted(df_portfolios_gs['PortfolioName'].dropna().unique().tolist()) #
    portfolio_names_list_gs.extend(valid_portfolio_names) #

if st.session_state.active_portfolio_name_gs not in portfolio_names_list_gs:
    st.session_state.active_portfolio_name_gs = portfolio_names_list_gs[0] # Default to empty or first valid

previous_portfolio_name_gs = st.session_state.active_portfolio_name_gs #

selected_portfolio_name_gs = st.sidebar.selectbox(
    "เลือกพอร์ต:",
    options=portfolio_names_list_gs, #
    index=portfolio_names_list_gs.index(st.session_state.active_portfolio_name_gs), #
    key='sb_active_portfolio_selector_gs' # This key will update st.session_state.active_portfolio_name_gs on change through rerun
)

# --- Handle Portfolio Change ---
if selected_portfolio_name_gs != previous_portfolio_name_gs:
    st.session_state.active_portfolio_name_gs = selected_portfolio_name_gs # Update session state
    st.session_state.latest_statement_equity = None # ** CRITICAL: Reset latest equity on portfolio change **
    st.session_state.current_account_balance = DEFAULT_ACCOUNT_BALANCE # Reset to default, will be updated below
    
    if 'ultimate_stmt_uploader_v7_final' in st.session_state: # Assuming this is the key for file uploader state
        uploader_key_to_check = f"ultimate_stmt_uploader_v7_final_{st.session_state.get('uploader_key_version', 0)}" #
        if uploader_key_to_check in st.session_state and st.session_state[uploader_key_to_check] is not None:
            st.session_state[uploader_key_to_check] = None # Reset file uploader
            st.sidebar.warning("⚠️ การเปลี่ยนพอร์ตทำให้ไฟล์ที่อัปโหลดไว้ (ในส่วน Statement Import) ถูกรีเซ็ต") #

    if selected_portfolio_name_gs != "":
        if not df_portfolios_gs.empty:
            selected_portfolio_row_df = df_portfolios_gs[df_portfolios_gs['PortfolioName'] == selected_portfolio_name_gs] #
            if not selected_portfolio_row_df.empty:
                st.session_state.current_portfolio_details = selected_portfolio_row_df.iloc[0].to_dict() #
                st.session_state.active_portfolio_id_gs = st.session_state.current_portfolio_details.get('PortfolioID', None) #
                
                # +++ NEW: Attempt to load latest equity from StatementSummaries for the NEWLY selected portfolio +++
                if st.session_state.active_portfolio_id_gs:
                    df_all_summaries = load_statement_summaries_from_gsheets() # Calls the new cached function
                    if not df_all_summaries.empty and \
                       'PortfolioID' in df_all_summaries.columns and \
                       'Equity' in df_all_summaries.columns and \
                       'Timestamp' in df_all_summaries.columns:
                        
                        # Ensure columns are of correct type for filtering and sorting
                        # This was already handled in load_statement_summaries_from_gsheets, but defensive check is okay
                        if not pd.api.types.is_string_dtype(df_all_summaries['PortfolioID']):
                             df_all_summaries['PortfolioID'] = df_all_summaries['PortfolioID'].astype(str)
                        if not pd.api.types.is_numeric_dtype(df_all_summaries['Equity']):
                             df_all_summaries['Equity'] = pd.to_numeric(df_all_summaries['Equity'].astype(str).str.replace(',', '', regex=False), errors='coerce')
                        if not pd.api.types.is_datetime64_any_dtype(df_all_summaries['Timestamp']):
                             df_all_summaries['Timestamp'] = pd.to_datetime(df_all_summaries['Timestamp'], errors='coerce')
                        
                        df_portfolio_specific_summaries = df_all_summaries[
                            (df_all_summaries['PortfolioID'] == str(st.session_state.active_portfolio_id_gs)) &
                            (df_all_summaries['Equity'].notna()) &
                            (df_all_summaries['Timestamp'].notna()) # Ensure timestamp is valid for sorting
                        ].copy() # Use .copy() to avoid SettingWithCopyWarning

                        if not df_portfolio_specific_summaries.empty:
                            # Sort by Timestamp to get the latest
                            df_portfolio_specific_summaries.sort_values(by='Timestamp', ascending=False, inplace=True)
                            latest_equity_value = df_portfolio_specific_summaries.iloc[0]['Equity']
                            if pd.notna(latest_equity_value):
                                st.session_state.latest_statement_equity = float(latest_equity_value)
                                print(f"SEC 1 (Portfolio Change): Loaded latest equity {latest_equity_value} for portfolio '{selected_portfolio_name_gs}' from summaries.")
                            else:
                                st.session_state.latest_statement_equity = None
                                print(f"SEC 1 (Portfolio Change): Latest equity value from summary is NaN for portfolio '{selected_portfolio_name_gs}'.")
                        else:
                            st.session_state.latest_statement_equity = None 
                            print(f"SEC 1 (Portfolio Change): No valid equity summary found for portfolio '{selected_portfolio_name_gs}'.")
                    else:
                        st.session_state.latest_statement_equity = None
                        print(f"SEC 1 (Portfolio Change): StatementSummaries sheet empty or missing required columns for portfolio '{selected_portfolio_name_gs}'.")
                else: 
                    st.session_state.latest_statement_equity = None
                # +++ END NEW +++

                # Set current_account_balance: Prioritize latest_statement_equity, then InitialBalance from portfolio details
                if st.session_state.latest_statement_equity is not None:
                    st.session_state.current_account_balance = st.session_state.latest_statement_equity #
                else: 
                    initial_bal_val = st.session_state.current_portfolio_details.get('InitialBalance', DEFAULT_ACCOUNT_BALANCE) #
                    try:
                        st.session_state.current_account_balance = float(initial_bal_val) #
                    except (ValueError, TypeError):
                        st.session_state.current_account_balance = DEFAULT_ACCOUNT_BALANCE #
                        st.sidebar.warning(f"ไม่สามารถแปลง InitialBalance ของพอร์ต '{selected_portfolio_name_gs}' เป็นตัวเลขได้") #
                
                if st.session_state.active_portfolio_id_gs is None:
                     st.sidebar.warning("ไม่พบ PortfolioID สำหรับพอร์ตที่เลือก.") #
            else: 
                st.session_state.active_portfolio_id_gs = None #
                st.session_state.current_portfolio_details = None #
                st.session_state.latest_statement_equity = None
                st.session_state.current_account_balance = DEFAULT_ACCOUNT_BALANCE #
        else: 
            st.session_state.active_portfolio_id_gs = None #
            st.session_state.current_portfolio_details = None #
            st.session_state.latest_statement_equity = None
            st.session_state.current_account_balance = DEFAULT_ACCOUNT_BALANCE #
    else: # Portfolio deselected (selected_portfolio_name_gs is "")
        st.session_state.active_portfolio_id_gs = None #
        st.session_state.current_portfolio_details = None #
        st.session_state.latest_statement_equity = None 
        st.session_state.current_account_balance = DEFAULT_ACCOUNT_BALANCE # Reset to default
    
    st.rerun() # Rerun to apply changes immediately, especially for balance display

# --- Display details of the selected active portfolio ---
if st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details #
    st.sidebar.markdown(f"**💡 ข้อมูลพอร์ต '{details.get('PortfolioName', 'N/A')}'**") #
    initial_balance_display = details.get('InitialBalance') #
    if pd.notna(initial_balance_display):
        try:
            st.sidebar.write(f"- Balance เริ่มต้น (พอร์ต): {float(initial_balance_display):,.2f} USD") #
        except ValueError:
            st.sidebar.write(f"- Balance เริ่มต้น (พอร์ต): {initial_balance_display} (ไม่สามารถแปลงเป็นตัวเลข)") #
            
    if pd.notna(details.get('ProgramType')): st.sidebar.write(f"- ประเภท: {details['ProgramType']}") #
    if pd.notna(details.get('Status')): st.sidebar.write(f"- สถานะ: {details['Status']}") #
    
    if details.get('ProgramType') in ["Prop Firm Challenge", "Funded Account", "Trading Competition"]: #
        if pd.notna(details.get('ProfitTargetPercent')): st.sidebar.write(f"- เป้าหมายกำไร: {float(details['ProfitTargetPercent']):.1f}%") #
        if pd.notna(details.get('DailyLossLimitPercent')): st.sidebar.write(f"- Daily Loss Limit: {float(details['DailyLossLimitPercent']):.1f}%") #
        if pd.notna(details.get('TotalStopoutPercent')): st.sidebar.write(f"- Total Stopout: {float(details['TotalStopoutPercent']):.1f}%") #

elif not df_portfolios_gs.empty and selected_portfolio_name_gs == "": # Corrected key
     st.sidebar.info("กรุณาเลือกพอร์ตที่ใช้งานจากรายการ") #
elif df_portfolios_gs.empty:
    st.sidebar.warning("ไม่พบข้อมูล Portfolio ใน Google Sheets หรือเกิดข้อผิดพลาดในการโหลด.") #

# ===================== SEC 1.5: PORTFOLIO MANAGEMENT UI (Main Area) =======================
def on_program_type_change_v8(): # This callback seems to be defined but its key might have changed or it might need adjustment based on usage
    st.session_state.exp_pf_type_select_v8_key = st.session_state.exp_pf_type_selector_widget_v8

with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)", expanded=False): # Setting expanded=True for easier testing
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

# ===================== SEC 2: COMMON INPUTS, BALANCE DISPLAY & MODE SELECTION (Sidebar) =======================
# --- Determine active_balance_to_use and initial_risk_pct_from_portfolio ---
# This logic prioritizes:
# 1. Equity from the latest uploaded statement.
# 2. InitialBalance from the selected portfolio's details.
# 3. A default account balance.

active_balance_to_use = DEFAULT_ACCOUNT_BALANCE # Fallback
initial_risk_pct_from_portfolio = DEFAULT_RISK_PERCENT # Fallback

# Display section for Balance used in calculations
st.sidebar.markdown("---") # Separator
st.sidebar.subheader("💰 Balance สำหรับคำนวณ")

if 'latest_statement_equity' in st.session_state and st.session_state.latest_statement_equity is not None:
    active_balance_to_use = st.session_state.latest_statement_equity
    # Ensure st.session_state.current_account_balance is aligned (already updated in SEC 1 or SEC 6)
    st.sidebar.markdown(f"<font color='lime'>**{active_balance_to_use:,.2f} USD**</font> (จาก Statement Equity ล่าสุด)", unsafe_allow_html=True)

elif 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details
    portfolio_initial_balance_val = details.get('InitialBalance')
    if pd.notna(portfolio_initial_balance_val):
        try:
            active_balance_to_use = float(portfolio_initial_balance_val)
            # st.session_state.current_account_balance is set during portfolio selection in SEC 1
            st.sidebar.markdown(f"<font color='gold'>**{active_balance_to_use:,.2f} USD**</font> (จาก Initial Balance พอร์ต)", unsafe_allow_html=True)
        except (ValueError, TypeError):
            active_balance_to_use = st.session_state.current_account_balance # Should be DEFAULT_ACCOUNT_BALANCE if conversion failed
            st.sidebar.warning(f"ไม่สามารถใช้ InitialBalance จากพอร์ตได้ ({portfolio_initial_balance_val}).")
            st.sidebar.markdown(f"**{active_balance_to_use:,.2f} USD** (ค่าเริ่มต้นระบบ)", unsafe_allow_html=True)
    else: # InitialBalance is not available in details, but portfolio is selected
        active_balance_to_use = st.session_state.current_account_balance # Should be DEFAULT_ACCOUNT_BALANCE
        st.sidebar.markdown(f"**{active_balance_to_use:,.2f} USD** (ค่าเริ่มต้น - ไม่มี InitialBalance ในพอร์ต)", unsafe_allow_html=True)
elif 'active_portfolio_name_gs' in st.session_state and not st.session_state.active_portfolio_name_gs:
    # No portfolio selected, use default (current_account_balance should be DEFAULT_ACCOUNT_BALANCE)
    active_balance_to_use = st.session_state.current_account_balance
    st.sidebar.markdown(f"**{active_balance_to_use:,.2f} USD** (ค่าเริ่มต้น - ไม่ได้เลือกพอร์ต)", unsafe_allow_html=True)
else: # Other fallbacks (e.g., portfolio details failed to load completely)
    active_balance_to_use = st.session_state.current_account_balance # Should be DEFAULT_ACCOUNT_BALANCE
    st.sidebar.warning("ไม่พบรายละเอียดพอร์ตที่สมบูรณ์ หรือยังไม่ได้เลือกพอร์ต")
    st.sidebar.markdown(f"**{active_balance_to_use:,.2f} USD** (ค่าเริ่มต้นระบบ)", unsafe_allow_html=True)

# Update current_account_balance in session_state to reflect the determined active_balance_to_use
# This ensures that if other parts of the app reference st.session_state.current_account_balance directly,
# they get the most up-to-date value used for calculations.
st.session_state.current_account_balance = active_balance_to_use


# --- Get CurrentRiskPercent from portfolio details for initial risk setting ---
if 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:
    details = st.session_state.current_portfolio_details
    current_risk_val_str = details.get('CurrentRiskPercent')
    if pd.notna(current_risk_val_str) and str(current_risk_val_str).strip() != "":
        try:
            risk_val_float = float(current_risk_val_str)
            if risk_val_float > 0:
                 initial_risk_pct_from_portfolio = risk_val_float
        except (ValueError, TypeError):
            # st.sidebar.warning("ไม่สามารถแปลง CurrentRiskPercent จากพอร์ตเป็นตัวเลขได้ ใช้ค่าเริ่มต้นแทน") # Optional warning
            pass # Uses default initial_risk_pct_from_portfolio
else: # No portfolio selected or no details
    pass # Uses default initial_risk_pct_from_portfolio


# --- Common Inputs ---
st.sidebar.markdown("---") # Separator
st.sidebar.subheader("⚙️ ตั้งค่าการเทรด")

drawdown_limit_pct_default = 2.0
if 'current_portfolio_details' in st.session_state and st.session_state.current_portfolio_details:
    portfolio_dd_limit = st.session_state.current_portfolio_details.get('DailyLossLimitPercent')
    if pd.notna(portfolio_dd_limit):
        try:
            drawdown_limit_pct_default = float(portfolio_dd_limit)
        except (ValueError, TypeError):
            pass # Use global default

drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=100.0, # Max can be adjusted
    value=st.session_state.get("drawdown_limit_pct", drawdown_limit_pct_default),
    step=0.1, format="%.1f",
    key="drawdown_limit_pct_input" # Use a distinct key for the widget
)
st.session_state.drawdown_limit_pct = drawdown_limit_pct # Update session_state for actual use

mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="trade_mode_radio")
st.session_state.mode = mode # Ensure mode is in session_state for other parts

if st.sidebar.button("🔄 Reset Form & Inputs"):
    # Values to preserve
    mode_to_keep = st.session_state.get("mode", "FIBO")
    dd_limit_to_keep = st.session_state.get("drawdown_limit_pct", drawdown_limit_pct_default) # Use the dynamic default
    
    # Portfolio related states to preserve
    active_portfolio_name_gs_keep = st.session_state.get('active_portfolio_name_gs', "")
    active_portfolio_id_gs_keep = st.session_state.get('active_portfolio_id_gs', None)
    current_portfolio_details_keep = st.session_state.get('current_portfolio_details', None)
    
    # Crucial: Preserve latest_statement_equity
    preserved_latest_statement_equity = st.session_state.get('latest_statement_equity', None)
    
    # Preserve uploader key version and GCloud service account
    uploader_key_version_keep = st.session_state.get('uploader_key_version', 0)
    gcp_service_account_keep = st.session_state.get('gcp_service_account', None) # If using secrets through session_state

    # Selectively clear relevant session state keys for form inputs, not everything
    keys_to_reset_for_form = [
        "asset_fibo_val_v2", "risk_pct_fibo_val_v2", "direction_fibo_val_v2",
        "swing_high_fibo_val_v2", "swing_low_fibo_val_v2", "fibo_flags_v2",
        "asset_custom_val_v2", "risk_pct_custom_val_v2", "n_entry_custom_val_v2",
        # Add keys for custom entry/sl/tp loops, e.g. "custom_entry_0_v3", "custom_sl_0_v3", ...
        "scaling_step", "min_risk_pct", "max_risk_pct", "scaling_mode", # Scaling manager settings
        # "plot_data" # Clearing plot_data might be desired
    ]
    # Add custom entry, SL, TP keys dynamically
    num_entries_on_reset = st.session_state.get("n_entry_custom_val_v2", 2) # Get current or default
    for i in range(num_entries_on_reset):
        keys_to_reset_for_form.extend([f"custom_entry_{i}_v3", f"custom_sl_{i}_v3", f"custom_tp_{i}_v3"])
    
    if 'plot_data' in st.session_state: keys_to_reset_for_form.append('plot_data')


    for key_to_reset in keys_to_reset_for_form:
        if key_to_reset in st.session_state:
            del st.session_state[key_to_reset]
            
    # Restore essential preserved states
    st.session_state.mode = mode_to_keep
    st.session_state.drawdown_limit_pct = dd_limit_to_keep
    
    st.session_state.active_portfolio_name_gs = active_portfolio_name_gs_keep
    st.session_state.active_portfolio_id_gs = active_portfolio_id_gs_keep
    st.session_state.current_portfolio_details = current_portfolio_details_keep
    st.session_state.latest_statement_equity = preserved_latest_statement_equity # Restore this!
    
    st.session_state.uploader_key_version = uploader_key_version_keep
    if gcp_service_account_keep: st.session_state.gcp_service_account = gcp_service_account_keep


    # Re-evaluate active_balance_to_use and initial_risk_pct_from_portfolio based on preserved details
    # This logic will now run based on the restored states at the beginning of SEC 2 upon rerun.
    # We need to set the default input values for risk percentages correctly.
    
    preserved_initial_risk = DEFAULT_RISK_PERCENT
    if current_portfolio_details_keep:
        pf_risk_str = current_portfolio_details_keep.get('CurrentRiskPercent')
        if pd.notna(pf_risk_str) and str(pf_risk_str).strip() != "":
            try:
                pf_risk_float = float(pf_risk_str)
                if pf_risk_float > 0: preserved_initial_risk = pf_risk_float
            except (ValueError, TypeError): pass
    
    # Initialize form inputs to their defaults or portfolio-derived values
    st.session_state.risk_pct_fibo_val_v2 = preserved_initial_risk
    st.session_state.risk_pct_custom_val_v2 = preserved_initial_risk
    # Other inputs will use their default initializations from global setup if not explicitly set here

    st.toast("รีเซ็ตฟอร์มและ Input เบื้องต้นแล้ว!", icon="🔄")
    st.rerun()

# ===================== SEC 2.1: FIBO TRADE DETAILS (Sidebar) =======================
# active_balance_to_use and initial_risk_pct_from_portfolio are determined in SEC 2

if st.session_state.get("mode") == "FIBO":
    # Ensure initial_risk_pct_from_portfolio is available from SEC 2
    current_default_risk_fibo = initial_risk_pct_from_portfolio 

    col1_fibo, col2_fibo, col3_fibo = st.sidebar.columns([2, 2, 2])
    with col1_fibo:
        asset_fibo_v2 = st.text_input("Asset (FIBO)", 
                                   value=st.session_state.get("asset_fibo_val_v2", "XAUUSD"), 
                                   key="asset_fibo_input_widget_v3") 
        st.session_state.asset_fibo_val_v2 = asset_fibo_v2 # Update session state
    with col2_fibo:
        risk_pct_fibo_v2 = st.number_input(
            "Risk % (FIBO)",
            min_value=0.01, max_value=100.0,
            value=st.session_state.get("risk_pct_fibo_val_v2", current_default_risk_fibo),
            step=0.01, format="%.2f",
            key="risk_pct_fibo_input_widget_v3") 
        st.session_state.risk_pct_fibo_val_v2 = risk_pct_fibo_v2 # Update session state
    with col3_fibo:
        default_direction_index_fibo = 0 # Default to "Long"
        if st.session_state.get("direction_fibo_val_v2") == "Short":
            default_direction_index_fibo = 1
        
        direction_fibo_v2 = st.radio("Direction (FIBO)", ["Long", "Short"], 
                                  index=default_direction_index_fibo,
                                  horizontal=True, key="fibo_direction_radio_widget_v3") 
        st.session_state.direction_fibo_val_v2 = direction_fibo_v2 # Update session state

    col4_fibo, col5_fibo = st.sidebar.columns(2)
    with col4_fibo:
        swing_high_fibo_v2 = st.text_input("Swing High (FIBO)", 
                                        value=st.session_state.get("swing_high_fibo_val_v2", ""),
                                        key="swing_high_fibo_input_widget_v3", help="ราคา High ของช่วง Fibo") 
        st.session_state.swing_high_fibo_val_v2 = swing_high_fibo_v2 # Update session state
    with col5_fibo:
        swing_low_fibo_v2 = st.text_input("Swing Low (FIBO)", 
                                       value=st.session_state.get("swing_low_fibo_val_v2", ""),
                                       key="swing_low_fibo_input_widget_v3", help="ราคา Low ของช่วง Fibo") 
        st.session_state.swing_low_fibo_val_v2 = swing_low_fibo_v2 # Update session state

    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    # fibos_fibo_v2 is already in session_state from global init or reset
    fibos_options_fibo = [0.114, 0.25, 0.382, 0.5, 0.618] 
    labels_fibo = [f"{l:.3f}" for l in fibos_options_fibo]
    
    # Ensure fibo_flags_v2 has the correct length
    if len(st.session_state.get("fibo_flags_v2", [])) != len(fibos_options_fibo):
        st.session_state.fibo_flags_v2 = [True] * len(fibos_options_fibo)

    cols_fibo_checkboxes = st.sidebar.columns(len(fibos_options_fibo))
    fibo_selected_flags_current = []
    for i, col_cb in enumerate(cols_fibo_checkboxes): 
        checked_fibo = col_cb.checkbox(labels_fibo[i], 
                                         value=st.session_state.fibo_flags_v2[i], 
                                         key=f"fibo_cb_widget_{i}_v3") 
        fibo_selected_flags_current.append(checked_fibo)
    st.session_state.fibo_flags_v2 = fibo_selected_flags_current # Update session state

    # Validation messages for Fibo inputs
    try:
        valid_high_low = False
        if swing_high_fibo_v2 and swing_low_fibo_v2: # Check if both have values
            high_val_fibo = float(swing_high_fibo_v2)
            low_val_fibo = float(swing_low_fibo_v2)
            if high_val_fibo <= low_val_fibo:
                st.sidebar.warning("High (FIBO) ต้องมากกว่า Low!")
            else:
                valid_high_low = True
    except ValueError:
        if swing_high_fibo_v2 or swing_low_fibo_v2: 
            st.sidebar.warning("กรุณาใส่ High/Low (FIBO) เป็นตัวเลขที่ถูกต้อง")
    
    if risk_pct_fibo_v2 <= 0: 
        st.sidebar.warning("Risk % (FIBO) ต้องมากกว่า 0")

    # Preview (optional, can be expanded in summary)
    if valid_high_low and any(st.session_state.fibo_flags_v2):
        st.sidebar.markdown("---")
        st.sidebar.markdown("**Preview (FIBO - Entry แรกที่เลือก):**")
        try:
            first_selected_idx = st.session_state.fibo_flags_v2.index(True)
            preview_entry_fibo = 0.0
            range_val = float(swing_high_fibo_v2) - float(swing_low_fibo_v2)
            if direction_fibo_v2 == "Long":
                preview_entry_fibo = float(swing_low_fibo_v2) + (range_val * fibos_options_fibo[first_selected_idx])
            else: # Short
                preview_entry_fibo = float(swing_high_fibo_v2) - (range_val * fibos_options_fibo[first_selected_idx])
            st.sidebar.markdown(f"Entry ≈ **{preview_entry_fibo:.5f}**")
            st.sidebar.caption("รายละเอียด Lot/TP/ผลลัพธ์เต็ม อยู่ใน Strategy Summary ด้านล่าง")
        except ValueError: # No Fibo level selected or conversion error
            pass 
        except Exception as e_fibo_preview:
            print(f"Error in Fibo preview: {e_fibo_preview}")


    save_fibo_button = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo_button_v3")
    if 'save_fibo' not in st.session_state: st.session_state.save_fibo = False # Init for logic in SEC 2.5
    if save_fibo_button: st.session_state.save_fibo = True

# ===================== SEC 2.2: CUSTOM TRADE DETAILS (Sidebar) =======================
# active_balance_to_use and initial_risk_pct_from_portfolio are determined in SEC 2

elif st.session_state.get("mode") == "CUSTOM":
    # Ensure initial_risk_pct_from_portfolio is available from SEC 2
    current_default_risk_custom = initial_risk_pct_from_portfolio

    col1_custom, col2_custom, col3_custom = st.sidebar.columns([2, 2, 2])
    with col1_custom:
        asset_custom_v2 = st.text_input("Asset (CUSTOM)", 
                                     value=st.session_state.get("asset_custom_val_v2", "XAUUSD"), 
                                     key="asset_custom_input_widget_v3") 
        st.session_state.asset_custom_val_v2 = asset_custom_v2
    with col2_custom:
        risk_pct_custom_v2 = st.number_input( 
            "Risk % (CUSTOM - Total for all entries)",
            min_value=0.01, max_value=100.0,
            value=st.session_state.get("risk_pct_custom_val_v2", current_default_risk_custom),
            step=0.01, format="%.2f",
            key="risk_pct_custom_input_widget_v3") 
        st.session_state.risk_pct_custom_val_v2 = risk_pct_custom_v2
    with col3_custom:
        n_entry_custom_v2 = st.number_input( 
            "จำนวนไม้ (CUSTOM)",
            min_value=1, max_value=10, 
            value=st.session_state.get("n_entry_custom_val_v2", 2), 
            step=1, format="%d",
            key="n_entry_custom_input_widget_v3") 
        st.session_state.n_entry_custom_val_v2 = int(n_entry_custom_v2)

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้ (CUSTOM)**")
    
    # Dynamically initialize session state for custom entries if n_entry changes
    for i in range(st.session_state.n_entry_custom_val_v2):
        if f"custom_entry_{i}_v3" not in st.session_state: st.session_state[f"custom_entry_{i}_v3"] = "0.00"
        if f"custom_sl_{i}_v3" not in st.session_state: st.session_state[f"custom_sl_{i}_v3"] = "0.00"
        if f"custom_tp_{i}_v3" not in st.session_state: st.session_state[f"custom_tp_{i}_v3"] = "0.00"

    # Calculate risk per entry for display purposes
    risk_dollar_total_custom_plan = 0.0
    if active_balance_to_use > 0 and risk_pct_custom_v2 > 0:
        risk_dollar_total_custom_plan = active_balance_to_use * (risk_pct_custom_v2 / 100.0)
    
    risk_dollar_per_entry_custom_plan = 0.0
    if st.session_state.n_entry_custom_val_v2 > 0 and risk_dollar_total_custom_plan > 0:
        risk_dollar_per_entry_custom_plan = risk_dollar_total_custom_plan / st.session_state.n_entry_custom_val_v2

    for i in range(st.session_state.n_entry_custom_val_v2):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e_cust, col_s_cust, col_t_cust = st.sidebar.columns(3)
        entry_key = f"custom_entry_{i}_v3" 
        sl_key = f"custom_sl_{i}_v3"       
        tp_key = f"custom_tp_{i}_v3"       

        with col_e_cust:
            entry_str = st.text_input(f"Entry {i+1}", value=st.session_state[entry_key], key=f"{entry_key}_widget")
            st.session_state[entry_key] = entry_str # Update session state
        with col_s_cust:
            sl_str = st.text_input(f"SL {i+1}", value=st.session_state[sl_key], key=f"{sl_key}_widget")
            st.session_state[sl_key] = sl_str # Update session state
        with col_t_cust:
            tp_str = st.text_input(f"TP {i+1}", value=st.session_state[tp_key], key=f"{tp_key}_widget")
            st.session_state[tp_key] = tp_str # Update session state
        
        # Display Lot & Stop info (calculated in Strategy Summary for full details)
        lot_display_str = "Lot: - (คำนวณใน Summary)"
        stop_display_str = "Stop: - (คำนวณใน Summary)"
        try:
            entry_float = float(entry_str)
            sl_float = float(sl_str)
            if sl_float == entry_float:
                stop_display_str = "Stop: 0 (SL=Entry)"
                lot_display_str = "Lot: - (SL=Entry)"
            else:
                stop_val = abs(entry_float - sl_float)
                stop_display_str = f"Stop Dist: {stop_val:.5f}"
                if stop_val > 1e-9 and risk_dollar_per_entry_custom_plan > 0:
                    lot_val_pre = risk_dollar_per_entry_custom_plan / stop_val
                    lot_display_str = f"Lot (est.): {lot_val_pre:.2f}"
                else:
                    lot_display_str = "Lot: - (Stop=0 or No Risk)"
        except ValueError:
            lot_display_str = "Lot: - (รอ Input E/SL)"
            stop_display_str = "Stop: - (รอ Input E/SL)"
        
        st.sidebar.caption(f"{lot_display_str} | Risk/ไม้ (est.): {risk_dollar_per_entry_custom_plan:.2f} | {stop_display_str}")

    if risk_pct_custom_v2 <= 0:
        st.sidebar.warning("Risk % (CUSTOM) ต้องมากกว่า 0")

    save_custom_button = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom_button_v3")
    if 'save_custom' not in st.session_state: st.session_state.save_custom = False # Init for logic in SEC 2.5
    if save_custom_button: st.session_state.save_custom = True

# ===================== SEC 2.3: STRATEGY SUMMARY (Calculations & Display - Sidebar) =======================
st.sidebar.markdown("---")
st.sidebar.subheader("🧾 Strategy Summary")

# Initialize summary variables
summary_total_lots = 0.0
summary_total_risk_dollar = 0.0 # Actual calculated risk based on lot sizes and stop distances
summary_avg_rr = 0.0
summary_total_profit_at_primary_tp = 0.0
summary_direction_display = "N/A"

entry_data_for_saving = [] # This list will hold dicts for each entry

RATIO_TP1_EFF = 1.618 
RATIO_TP2_EFF = 2.618 
RATIO_TP3_EFF = 4.236

current_active_balance_for_summary = st.session_state.get('current_account_balance', DEFAULT_ACCOUNT_BALANCE)

if st.session_state.get("mode") == "FIBO":
    # ... (ส่วน FIBO ยังคงเหมือนเดิม ไม่มีการเปลี่ยนแปลงที่นี่) ...
    summary_direction_display = st.session_state.get("direction_fibo_val_v2", "N/A")
    try:
        h_str_fibo = st.session_state.get("swing_high_fibo_val_v2", "")
        l_str_fibo = st.session_state.get("swing_low_fibo_val_v2", "")
        risk_pct_fibo_input = st.session_state.get("risk_pct_fibo_val_v2", 0.0)
        fibo_levels_to_use = [0.114, 0.25, 0.382, 0.5, 0.618] 
        fibo_flags_selected = st.session_state.get("fibo_flags_v2", [False]*len(fibo_levels_to_use))

        if not h_str_fibo or not l_str_fibo:
            st.sidebar.info("กรอก High และ Low (FIBO) และเลือก Fibo Levels เพื่อคำนวณ Summary")
        elif risk_pct_fibo_input <= 0:
            st.sidebar.warning("Risk % (FIBO) ต้องมากกว่า 0")
        else:
            high_fibo = float(h_str_fibo)
            low_fibo = float(l_str_fibo)
            
            if high_fibo <= low_fibo:
                st.sidebar.warning("High (FIBO) ต้องมากกว่า Low ใน Summary Calculation!")
            else:
                range_fibo = abs(high_fibo - low_fibo)
                if range_fibo <= 1e-9:
                     st.sidebar.warning("Range ระหว่าง High และ Low (FIBO) น้อยเกินไป")
                else:
                    num_selected_fibo_entries = sum(fibo_flags_selected)
                    if num_selected_fibo_entries == 0:
                        st.sidebar.info("กรุณาเลือก Fibo Level อย่างน้อยหนึ่งระดับสำหรับ Entry")
                    else:
                        total_planned_risk_dollar_fibo = current_active_balance_for_summary * (risk_pct_fibo_input / 100.0)
                        risk_dollar_per_fibo_entry = total_planned_risk_dollar_fibo / num_selected_fibo_entries
                        
                        temp_fibo_rr_list = []
                        
                        for i, is_selected in enumerate(fibo_flags_selected):
                            if is_selected:
                                fibo_ratio = fibo_levels_to_use[i]
                                entry_price, sl_price, tp1_price_global = 0.0, 0.0, 0.0

                                if summary_direction_display == "Long":
                                    entry_price = low_fibo + (range_fibo * fibo_ratio)
                                    sl_price = low_fibo 
                                    tp1_price_global = low_fibo + (range_fibo * RATIO_TP1_EFF) 
                                else: # Short
                                    entry_price = high_fibo - (range_fibo * fibo_ratio)
                                    sl_price = high_fibo 
                                    tp1_price_global = high_fibo - (range_fibo * RATIO_TP1_EFF) 
                                
                                stop_distance = abs(entry_price - sl_price)
                                lot_size, actual_risk_this_leg, rr_to_tp1, profit_at_tp1_this_leg = 0.0, 0.0, 0.0, 0.0

                                if stop_distance > 1e-9:
                                    lot_size = risk_dollar_per_fibo_entry / stop_distance
                                    actual_risk_this_leg = lot_size * stop_distance 
                                    
                                    target_distance_tp1 = abs(tp1_price_global - entry_price)
                                    if (summary_direction_display == "Long" and tp1_price_global > entry_price) or \
                                       (summary_direction_display == "Short" and tp1_price_global < entry_price):
                                        profit_at_tp1_this_leg = lot_size * target_distance_tp1
                                        rr_to_tp1 = target_distance_tp1 / stop_distance
                                        temp_fibo_rr_list.append(rr_to_tp1)
                                else: 
                                    actual_risk_this_leg = risk_dollar_per_fibo_entry 
                                    lot_size = 0 

                                summary_total_lots += lot_size
                                summary_total_risk_dollar += actual_risk_this_leg
                                summary_total_profit_at_primary_tp += profit_at_tp1_this_leg
                                
                                entry_data_for_saving.append({
                                    "Fibo Level": f"{fibo_ratio:.3f}", "Entry": round(entry_price, 5), 
                                    "SL": round(sl_price, 5), "TP": round(tp1_price_global, 5), 
                                    "Lot": round(lot_size, 2), "Risk $": round(actual_risk_this_leg, 2), 
                                    "RR": round(rr_to_tp1, 2) if rr_to_tp1 > 0 else "N/A"
                                })
                        
                        if temp_fibo_rr_list:
                            summary_avg_rr = np.mean([r for r in temp_fibo_rr_list if pd.notna(r) and r > 0])
    except ValueError:
        if st.session_state.get("swing_high_fibo_val_v2", "") or st.session_state.get("swing_low_fibo_val_v2", ""):
             st.sidebar.warning("กรอก High/Low (FIBO) เป็นตัวเลขที่ถูกต้องใน Summary")
    except Exception as e_fibo_calc:
        st.sidebar.error(f"คำนวณ FIBO Summary ผิดพลาด: {e_fibo_calc}")

elif st.session_state.get("mode") == "CUSTOM":
    try:
        num_entries_custom = st.session_state.get("n_entry_custom_val_v2", 0)
        risk_pct_custom_input = st.session_state.get("risk_pct_custom_val_v2", 0.0)
        # custom_tp_recommendations = [] # REMOVED: This will now be a column in the table

        if num_entries_custom <= 0:
            st.sidebar.info("เลือกจำนวนไม้ (CUSTOM) มากกว่า 0 เพื่อคำนวณ Summary")
        elif risk_pct_custom_input <= 0:
            st.sidebar.warning("Risk % (CUSTOM) ต้องมากกว่า 0")
        else:
            total_planned_risk_dollar_custom = current_active_balance_for_summary * (risk_pct_custom_input / 100.0)
            risk_dollar_per_custom_entry = 0
            if num_entries_custom > 0:
                risk_dollar_per_custom_entry = total_planned_risk_dollar_custom / num_entries_custom
            
            temp_custom_rr_list = []
            long_trades_count = 0
            short_trades_count = 0
            
            for i in range(num_entries_custom):
                entry_str = st.session_state.get(f"custom_entry_{i}_v3", "0.00")
                sl_str = st.session_state.get(f"custom_sl_{i}_v3", "0.00")
                tp_str = st.session_state.get(f"custom_tp_{i}_v3", "0.00")
                
                entry_val, sl_val, tp_val = 0.0,0.0,0.0
                lot_size, actual_risk_this_leg, rr_custom, profit_at_tp_this_leg = 0.0, 0.0, 0.0, 0.0
                tp_at_rr3_display = "N/A" # For the new column

                try:
                    entry_val = float(entry_str)
                    sl_val = float(sl_str)
                    tp_val = float(tp_str) # User's TP

                    stop_distance = abs(entry_val - sl_val)
                    
                    if sl_val == entry_val: 
                        actual_risk_this_leg = risk_dollar_per_custom_entry 
                        lot_size = 0 
                    else:
                        if entry_val > sl_val: long_trades_count +=1
                        elif entry_val < sl_val: short_trades_count += 1

                        if stop_distance > 1e-9:
                            lot_size = risk_dollar_per_custom_entry / stop_distance
                            actual_risk_this_leg = lot_size * stop_distance
                            
                            target_distance = abs(tp_val - entry_val)
                            if target_distance > 1e-9 and tp_val != entry_val:
                                current_direction_is_long = (entry_val > sl_val)
                                tp_is_profitable = (current_direction_is_long and tp_val > entry_val) or \
                                                   (not current_direction_is_long and tp_val < entry_val)
                                if tp_is_profitable:
                                    rr_custom = target_distance / stop_distance
                                    profit_at_tp_this_leg = lot_size * target_distance
                                    temp_custom_rr_list.append(rr_custom)
                            
                            # *** NEW: Calculate TP for RR=3 ***
                            direction_for_rr3_tp = ""
                            if entry_val > sl_val: direction_for_rr3_tp = "Long"
                            elif sl_val > entry_val: direction_for_rr3_tp = "Short"

                            if direction_for_rr3_tp: # Only if direction can be determined
                                recommended_tp_target_for_rr3 = 3 * stop_distance
                                if direction_for_rr3_tp == "Long":
                                    tp_at_rr3_calc = entry_val + recommended_tp_target_for_rr3
                                else: # Short
                                    tp_at_rr3_calc = entry_val - recommended_tp_target_for_rr3
                                tp_at_rr3_display = round(tp_at_rr3_calc, 5)
                            # *** END NEW ***
                        else: 
                            actual_risk_this_leg = risk_dollar_per_custom_entry
                            lot_size = 0
                except ValueError:
                     actual_risk_this_leg = risk_dollar_per_custom_entry 
                     entry_data_for_saving.append({
                         "Entry": entry_str, "SL": sl_str, "TP": tp_str, 
                         "Lot": "Error", "Risk $": f"{actual_risk_this_leg:.2f}", "RR": "Error",
                         "TP (RR≈3)": "Error" # Add new key here too
                        })
                     summary_total_risk_dollar += actual_risk_this_leg 
                     continue 
                
                summary_total_lots += lot_size
                summary_total_risk_dollar += actual_risk_this_leg
                summary_total_profit_at_primary_tp += profit_at_tp_this_leg
                
                entry_data_for_saving.append({
                    "Fibo Level": "", 
                    "Entry": round(entry_val, 5), "SL": round(sl_val, 5), "TP": round(tp_val, 5),
                    "Lot": round(lot_size, 2), "Risk $": round(actual_risk_this_leg, 2), 
                    "RR": round(rr_custom, 2) if rr_custom > 0 else "N/A",
                    "TP (RR≈3)": tp_at_rr3_display # *** ADDED NEW KEY AND VALUE ***
                })

            if long_trades_count == num_entries_custom and short_trades_count == 0: summary_direction_display = "Long"
            elif short_trades_count == num_entries_custom and long_trades_count == 0: summary_direction_display = "Short"
            elif long_trades_count > 0 and short_trades_count > 0: summary_direction_display = "Mixed"
            elif long_trades_count > 0 : summary_direction_display = "Long" 
            elif short_trades_count > 0 : summary_direction_display = "Short" 
            
            if temp_custom_rr_list:
                summary_avg_rr = np.mean([r for r in temp_custom_rr_list if pd.notna(r) and r > 0])
            
            # REMOVED: st.session_state.custom_tp_recommendation_messages_for_summary
            # if 'custom_tp_recommendation_messages_for_summary' in st.session_state:
            #    del st.session_state.custom_tp_recommendation_messages_for_summary


    except ValueError:
        st.sidebar.warning("กรอกข้อมูล CUSTOM ไม่ถูกต้อง (ตรวจสอบจำนวนไม้ หรือ Risk %)")
    except Exception as e_custom_calc:
        st.sidebar.error(f"คำนวณ CUSTOM Summary ผิดพลาด: {e_custom_calc}")


# --- Display Summary ---
display_calculated_summary = False
if st.session_state.get("mode") == "FIBO" and entry_data_for_saving and st.session_state.get("swing_high_fibo_val_v2", "") and st.session_state.get("swing_low_fibo_val_v2", ""):
    display_calculated_summary = True
elif st.session_state.get("mode") == "CUSTOM" and entry_data_for_saving and st.session_state.get("n_entry_custom_val_v2", 0) > 0:
    display_calculated_summary = True

if display_calculated_summary:
    risk_pct_display = 0.0
    if st.session_state.get("mode") == "FIBO": risk_pct_display = st.session_state.get('risk_pct_fibo_val_v2', 0.0)
    elif st.session_state.get("mode") == "CUSTOM": risk_pct_display = st.session_state.get('risk_pct_custom_val_v2', 0.0)

    st.sidebar.write(f"**Direction:** {summary_direction_display}")
    st.sidebar.write(f"**Total Lots:** {summary_total_lots:.2f}")
    st.sidebar.write(f"**Total Risk $ (Calculated):** {summary_total_risk_dollar:.2f} (จาก Balance: {current_active_balance_for_summary:,.2f}, Risk Input: {risk_pct_display:.2f}%)")
    
    tp_ref_text = "(to Global TP1)" if st.session_state.get("mode") == "FIBO" else "(to User TPs)"
    st.sidebar.write(f"**Average RR {tp_ref_text}:** {summary_avg_rr:.2f}" if summary_avg_rr > 0 else f"**Average RR {tp_ref_text}:** N/A")
    st.sidebar.write(f"**Total Expected Profit {tp_ref_text}:** {summary_total_profit_at_primary_tp:,.2f} USD")
    
    # REMOVED the display of custom_tp_recommendation_messages_for_summary from sidebar
    # if st.session_state.get("mode") == "CUSTOM" and 'custom_tp_recommendation_messages_for_summary' in st.session_state:
    #    st.sidebar.markdown("**คำแนะนำ TP (เพื่อให้ RR ≈ 3):**")
    #    for msg in st.session_state.custom_tp_recommendation_messages_for_summary:
    #        st.sidebar.caption(msg)
else: 
    mode_selected = st.session_state.get("mode")
    if mode_selected == "FIBO" and (not st.session_state.get("swing_high_fibo_val_v2", "") or not st.session_state.get("swing_low_fibo_val_v2", "") or not any(st.session_state.get("fibo_flags_v2",[]))):
        pass 
    elif mode_selected == "CUSTOM" and not (st.session_state.get("n_entry_custom_val_v2", 0) > 0 and st.session_state.get("risk_pct_custom_val_v2", 0.0) > 0):
        pass 
    elif not entry_data_for_saving : 
        st.sidebar.info("กรอกข้อมูลให้ครบถ้วนและถูกต้อง หรือเลือกเงื่อนไข (เช่น Fibo Levels) เพื่อคำนวณ Summary")

# ===================== SEC 2.4: SCALING MANAGER (Sidebar) =======================
with st.sidebar.expander("⚖️ Scaling Manager Settings", expanded=False):
    # Default values for scaling parameters
    scaling_step_default_val = 0.25
    min_risk_pct_default_val = 0.50
    max_risk_pct_default_val = 5.0
    scaling_mode_default_val = 'Manual'
    
    # Retrieve values from portfolio details if available, else use session_state or defaults
    current_portfolio_scaling_settings = st.session_state.get('current_portfolio_details', {})
    
    # Helper to get value: portfolio -> session_state -> default
    def get_scaling_param(param_name_portfolio, param_name_session, default_value, is_float=True):
        val = default_value
        if current_portfolio_scaling_settings and pd.notna(current_portfolio_scaling_settings.get(param_name_portfolio)):
            try:
                val = float(current_portfolio_scaling_settings.get(param_name_portfolio)) if is_float else current_portfolio_scaling_settings.get(param_name_portfolio)
            except: val = default_value # Fallback on conversion error
        return st.session_state.get(param_name_session, val)

    # Use CurrentRiskPercent from portfolio as the basis for scaling_step if not otherwise set
    # This means scaling step will be relative to current risk if 'ScaleUp_RiskIncrementPercent' is not set
    # This interpretation might need review based on desired logic for 'scaling_step'
    # For now, 'scaling_step' is an independent value like in original code.
    
    # Scaling Step
    # Portfolio fields: 'ScaleUp_RiskIncrementPercent' or 'ScaleDown_RiskDecrementPercent' could be used
    # For simplicity, keeping scaling_step as a direct input or session state value for now.
    scaling_step = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=5.0, # Max step can be adjusted
        value=st.session_state.get('scaling_step', scaling_step_default_val), 
        step=0.01, format="%.2f", key='scaling_step_input'
    )
    st.session_state.scaling_step = scaling_step

    # Min Risk %
    min_risk_pct = st.number_input(
        "Minimum Risk % Allowed", min_value=0.01, max_value=100.0, 
        value=get_scaling_param('MinRiskPercentAllowed', 'min_risk_pct', min_risk_pct_default_val), 
        step=0.01, format="%.2f", key='min_risk_pct_input'
    )
    st.session_state.min_risk_pct = min_risk_pct

    # Max Risk %
    max_risk_pct = st.number_input(
        "Maximum Risk % Allowed", min_value=0.01, max_value=100.0, 
        value=get_scaling_param('MaxRiskPercentAllowed', 'max_risk_pct', max_risk_pct_default_val), 
        step=0.01, format="%.2f", key='max_risk_pct_input'
    )
    st.session_state.max_risk_pct = max_risk_pct
    
    # Scaling Mode (Manual/Auto) - Portfolio 'EnableScaling' could influence this
    # For now, 'scaling_mode' is a direct user choice in UI.
    # 'EnableScaling' from portfolio is primarily for the add/edit portfolio form.
    scaling_mode_options = ["Manual", "Auto"]
    current_scaling_mode_val = st.session_state.get('scaling_mode', scaling_mode_default_val)
    scaling_mode_idx = scaling_mode_options.index(current_scaling_mode_val) if current_scaling_mode_val in scaling_mode_options else 0
    
    scaling_mode = st.radio(
        "Scaling Mode", scaling_mode_options, 
        index=scaling_mode_idx,
        horizontal=True, key='scaling_mode_radio'
    )
    st.session_state.scaling_mode = scaling_mode

# ===================== SEC 2.4.1: SCALING SUGGESTION LOGIC (Sidebar) =======================
# This section generates risk scaling suggestions based on performance.
# active_balance_to_use and initial_risk_pct_from_portfolio are from SEC 2.

# Load all planned trade logs (uses cache via load_all_planned_trade_logs_from_gsheets)
df_all_planned_logs = load_all_planned_trade_logs_from_gsheets() 

# Filter logs for the active portfolio, if one is selected
df_logs_for_scaling_analysis = pd.DataFrame()
active_portfolio_id_scaling = st.session_state.get('active_portfolio_id_gs', None)

if active_portfolio_id_scaling and not df_all_planned_logs.empty:
    if 'PortfolioID' in df_all_planned_logs.columns:
        df_logs_for_scaling_analysis = df_all_planned_logs[
            df_all_planned_logs['PortfolioID'] == str(active_portfolio_id_scaling)
        ].copy() # Use .copy() to avoid SettingWithCopyWarning on later modifications
    else: # Fallback if PortfolioID column is missing (should not happen with correct setup)
        df_logs_for_scaling_analysis = df_all_planned_logs.copy()
        print("Warning: Scaling - PortfolioID column not found in planned logs. Using all logs.")
elif not df_all_planned_logs.empty: # No active portfolio, use all logs for general analysis
    df_logs_for_scaling_analysis = df_all_planned_logs.copy()
# If df_all_planned_logs is empty, df_logs_for_scaling_analysis remains empty.

# Get performance metrics (winrate, gain, total trades for the week)
# The get_performance function uses a copy of the df, so no SettingWithCopyWarning from there.
winrate_weekly, gain_weekly, total_trades_weekly = get_performance(df_logs_for_scaling_analysis, mode="week")

# Determine the current risk % being used in the active trade mode (FIBO or CUSTOM)
current_risk_in_active_mode = initial_risk_pct_from_portfolio # Default from portfolio or global
if st.session_state.get("mode") == "FIBO":
    current_risk_in_active_mode = st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio)
elif st.session_state.get("mode") == "CUSTOM":
    current_risk_in_active_mode = st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio)

# Get Scaling Manager parameters from session_state (set in SEC 2.4)
scaling_step_ui = st.session_state.get('scaling_step', 0.25) 
max_risk_allowed_ui = st.session_state.get('max_risk_pct', 5.0)   
min_risk_allowed_ui = st.session_state.get('min_risk_pct', 0.5)   
selected_scaling_mode_ui = st.session_state.get('scaling_mode', 'Manual') 

# --- Scaling Suggestion Logic (based on original File1, using portfolio rules if available) ---
# This part can be enhanced to use detailed scaling rules from st.session_state.current_portfolio_details
# For now, it uses a simplified version similar to the original code, but with UI-defined step/min/max.

suggested_new_risk = current_risk_in_active_mode 
scaling_advice_message = f"Risk ปัจจุบัน (โหมด {st.session_state.get('mode')}): {current_risk_in_active_mode:.2f}%. "

if total_trades_weekly > 0: # Only suggest if there's performance data
    # Define thresholds (can be made dynamic or from portfolio settings later)
    # Example: ScaleUp_MinWinRate, ScaleUp_MinGainPercent from portfolio
    #          ScaleDown_MaxLossPercent, ScaleDown_LowWinRate from portfolio
    
    # Simplified logic from original code:
    gain_threshold_for_scaleup = 0.02 * current_active_balance_for_summary # 2% of current balance as gain target for scale-up
    
    if winrate_weekly > 55 and gain_weekly > gain_threshold_for_scaleup: # Scale Up condition
        suggested_new_risk = min(current_risk_in_active_mode + scaling_step_ui, max_risk_allowed_ui)
        scaling_advice_message += (f"<font color='lightgreen'>ผลงานดีเยี่ยม! (Winrate: {winrate_weekly:.1f}%, กำไรสัปดาห์: {gain_weekly:,.2f} USD)</font><br>"
                                   f"<b>แนะนำเพิ่ม Risk% เป็น {suggested_new_risk:.2f}%</b>")
    elif winrate_weekly < 45 or gain_weekly < 0: # Scale Down condition
        suggested_new_risk = max(current_risk_in_active_mode - scaling_step_ui, min_risk_allowed_ui)
        scaling_advice_message += (f"<font color='salmon'>ควรพิจารณาลดความเสี่ยง (Winrate: {winrate_weekly:.1f}%, กำไรสัปดาห์: {gain_weekly:,.2f} USD)</font><br>"
                                   f"<b>แนะนำลด Risk% เป็น {suggested_new_risk:.2f}%</b>")
    else: # Maintain current risk
        scaling_advice_message += f"คง Risk% ปัจจุบัน (Winrate สัปดาห์: {winrate_weekly:.1f}%, กำไร: {gain_weekly:,.2f} USD)"
else:
    scaling_advice_message += "ยังไม่มีข้อมูล Performance เพียงพอในสัปดาห์นี้ (จากแผนเทรด) หรือ Performance อยู่ในเกณฑ์คงที่."

st.sidebar.markdown(f"<div style='font-size: 0.9em; padding: 8px; border: 1px solid #444; border-radius: 5px;'>{scaling_advice_message}</div>", unsafe_allow_html=True)


# --- Apply Suggested Risk (Button for Manual, Auto-apply for Auto) ---
# Check if suggested_new_risk is meaningfully different from current_risk_in_active_mode
if abs(suggested_new_risk - current_risk_in_active_mode) > 1e-3: # Use a small epsilon for float comparison
    if selected_scaling_mode_ui == "Manual":
        if st.sidebar.button(f"✅ ปรับ Risk% (โหมด {st.session_state.get('mode')}) เป็น {suggested_new_risk:.2f}% ตามคำแนะนำ", key="apply_suggested_risk_manual"):
            if st.session_state.get("mode") == "FIBO":
                st.session_state.risk_pct_fibo_val_v2 = suggested_new_risk 
            elif st.session_state.get("mode") == "CUSTOM":
                st.session_state.risk_pct_custom_val_v2 = suggested_new_risk
            st.toast(f"ปรับ Risk% ในโหมด {st.session_state.get('mode')} เป็น {suggested_new_risk:.2f}% แล้ว", icon="👍")
            st.rerun()
    elif selected_scaling_mode_ui == "Auto":
        # Auto-apply logic
        risk_actually_changed_by_auto = False
        if st.session_state.get("mode") == "FIBO":
            if abs(st.session_state.get("risk_pct_fibo_val_v2", initial_risk_pct_from_portfolio) - suggested_new_risk) > 1e-3:
                st.session_state.risk_pct_fibo_val_v2 = suggested_new_risk 
                risk_actually_changed_by_auto = True
        elif st.session_state.get("mode") == "CUSTOM":
            if abs(st.session_state.get("risk_pct_custom_val_v2", initial_risk_pct_from_portfolio) - suggested_new_risk) > 1e-3:
                st.session_state.risk_pct_custom_val_v2 = suggested_new_risk
                risk_actually_changed_by_auto = True
        
        if risk_actually_changed_by_auto:
            # To prevent multiple reruns if suggestion remains the same, store last auto suggestion
            session_key_last_auto_risk = f"last_auto_suggested_risk_{st.session_state.get('mode')}"
            if st.session_state.get(session_key_last_auto_risk, current_risk_in_active_mode) != suggested_new_risk: 
                st.session_state[session_key_last_auto_risk] = suggested_new_risk
                st.toast(f"Auto Scaling: ปรับ Risk% ของโหมด {st.session_state.get('mode')} เป็น {suggested_new_risk:.2f}%", icon="⚙️")
                st.rerun()

# ===================== SEC 2.5: SAVE PLAN ACTION & DRAWDOWN LOCK (Sidebar) =======================
# This section handles saving the calculated plan and checking drawdown limits.
# `entry_data_for_saving` is populated in SEC 2.3 (Strategy Summary)
# `current_active_balance_for_summary` (aliased as active_balance_to_use here for consistency with original context)
# and `summary_direction_display` are also from SEC 2.3.

st.sidebar.markdown("---")
st.sidebar.subheader("💾 บันทึกแผน & ตรวจสอบ Drawdown")

# Load all planned trade logs for drawdown check (uses cache)
df_all_logs_for_drawdown = load_all_planned_trade_logs_from_gsheets()
df_logs_for_active_port_drawdown = pd.DataFrame()

active_portfolio_id_drawdown = st.session_state.get('active_portfolio_id_gs', None)
if active_portfolio_id_drawdown and not df_all_logs_for_drawdown.empty:
    if 'PortfolioID' in df_all_logs_for_drawdown.columns:
        df_logs_for_active_port_drawdown = df_all_logs_for_drawdown[
            df_all_logs_for_drawdown['PortfolioID'] == str(active_portfolio_id_drawdown)
        ].copy()
    else: # Should not happen
        df_logs_for_active_port_drawdown = df_all_logs_for_drawdown.copy()
elif not df_all_logs_for_drawdown.empty: # No active portfolio, use all logs
     df_logs_for_active_port_drawdown = df_all_logs_for_drawdown.copy()

# Calculate today's drawdown from PLANNED trades for the active portfolio (or all if no port selected)
# The get_today_drawdown function uses a copy, so no SettingWithCopyWarning.
drawdown_today_from_plans = get_today_drawdown(df_logs_for_active_port_drawdown) 

# Get Drawdown Limit % from UI (SEC 2)
drawdown_limit_percentage_ui = st.session_state.get('drawdown_limit_pct', 2.0) 
# Calculate absolute drawdown limit based on the active balance used for calculations
# current_active_balance_for_summary is the balance used for risk calculation (from SEC 2.3, ultimately from SEC 2)
drawdown_limit_absolute_value = -abs(current_active_balance_for_summary * (drawdown_limit_percentage_ui / 100.0)) 

# Display Drawdown Info
if drawdown_today_from_plans < 0: # Only show if there's actual negative P/L (loss) from plans
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้ (สะสม):** <font color='red'>{drawdown_today_from_plans:,.2f} USD</font>", unsafe_allow_html=True)
else:
    st.sidebar.markdown(f"**กำไร/ขาดทุนจากแผนวันนี้ (สะสม):** {drawdown_today_from_plans:,.2f} USD")
st.sidebar.markdown(f"**ลิมิตขาดทุนที่ตั้งไว้:** {drawdown_limit_absolute_value:,.2f} USD ({drawdown_limit_percentage_ui:.1f}% ของ {current_active_balance_for_summary:,.2f} USD)")


# --- Save Plan Action ---
# `save_fibo` or `save_custom` flags are set by their respective buttons in SEC 2.1 / 2.2
save_button_pressed_this_run = st.session_state.get('save_fibo', False) or st.session_state.get('save_custom', False)

if save_button_pressed_this_run:
    active_mode_for_save = st.session_state.get("mode")
    
    # Get asset and risk % based on active mode
    asset_to_save_plan = ""
    risk_pct_to_save_plan = 0.0
    if active_mode_for_save == "FIBO":
        asset_to_save_plan = st.session_state.get("asset_fibo_val_v2", "N/A")
        risk_pct_to_save_plan = st.session_state.get("risk_pct_fibo_val_v2", 0.0)
    elif active_mode_for_save == "CUSTOM":
        asset_to_save_plan = st.session_state.get("asset_custom_val_v2", "N/A")
        risk_pct_to_save_plan = st.session_state.get("risk_pct_custom_val_v2", 0.0)

    # Get portfolio info
    portfolio_id_for_save = st.session_state.get('active_portfolio_id_gs', None)
    portfolio_name_for_save = st.session_state.get('active_portfolio_name_gs', "N/A")

    # Validation before saving
    if not entry_data_for_saving: # entry_data_for_saving is populated in SEC 2.3
        st.sidebar.warning(f"ไม่พบข้อมูลแผน ({active_mode_for_save}) ที่จะบันทึก กรุณาคำนวณแผนใน Strategy Summary ให้ถูกต้องก่อน")
    elif drawdown_today_from_plans <= drawdown_limit_absolute_value and drawdown_today_from_plans != 0 : # Drawdown limit reached or exceeded
        st.sidebar.error(
            f"‼️ หยุดเทรด! ขาดทุนจากแผนรวมวันนี้ {abs(drawdown_today_from_plans):,.2f} USD ถึง/เกินลิมิตที่ตั้งไว้ {abs(drawdown_limit_absolute_value):,.2f} USD ({drawdown_limit_percentage_ui:.1f}%)"
        )
    elif not portfolio_id_for_save or portfolio_id_for_save == "N/A":
        st.sidebar.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ก่อนบันทึกแผน")
    else:
        try:
            # Call the globally defined save_plan_to_gsheets function
            # summary_direction_display comes from SEC 2.3
            if save_plan_to_gsheets(entry_data_for_saving, active_mode_for_save, asset_to_save_plan, risk_pct_to_save_plan, summary_direction_display, portfolio_id_for_save, portfolio_name_for_save):
                st.sidebar.success(f"บันทึกแผน ({active_mode_for_save}) สำหรับพอร์ต '{portfolio_name_for_save}' ลง Google Sheets สำเร็จ!")
                st.balloons()
                
                # Optionally clear some inputs after save, e.g., Fibo High/Low
                # if active_mode_for_save == "FIBO":
                #     st.session_state.swing_high_fibo_val_v2 = ""
                #     st.session_state.swing_low_fibo_val_v2 = ""
                # This would require a rerun to reflect cleared inputs.
                
            else:
                st.sidebar.error(f"การบันทึกแผน ({active_mode_for_save}) ไปยัง Google Sheets ไม่สำเร็จ (ตรวจสอบข้อความหรือ Console Log)")
        except Exception as e_save_plan_generic:
            st.sidebar.error(f"เกิดข้อผิดพลาดรุนแรงระหว่างบันทึกแผน ({active_mode_for_save}): {e_save_plan_generic}")
            print(f"Exception during save_plan: {e_save_plan_generic}")

    # Reset save button flags to prevent re-submission on next rerun without interaction
    if st.session_state.get('save_fibo', False): st.session_state.save_fibo = False
    if st.session_state.get('save_custom', False): st.session_state.save_custom = False
    # If inputs were cleared or state changed significantly, a st.rerun() might be needed here.
    # For now, rely on Streamlit's natural rerun for widget interactions.



# ===================== SEC 3: MAIN AREA - ENTRY PLAN DETAILS TABLE =======================
with st.expander("📋 Entry Table (รายละเอียดแผนเทรด)", expanded=True):
    active_mode_display = st.session_state.get("mode")
    
    if not entry_data_for_saving: # Check if entry_data_for_saving (from SEC 2.3) is empty
        st.info(f"กรุณากรอกข้อมูล {active_mode_display} ใน Sidebar และคำนวณ Strategy Summary เพื่อดูรายละเอียดแผนเทรดที่นี่")
    else:
        try:
            df_entry_plan_display = pd.DataFrame(entry_data_for_saving)
            
            if active_mode_display == "FIBO":
                # ... (ส่วน FIBO ยังคงเหมือนเดิม) ...
                st.markdown(f"### 🎯 Entry Levels & TP1 (FIBO - {st.session_state.get('asset_fibo_val_v2', 'N/A')})")
                cols_to_show_fibo = ["Fibo Level", "Entry", "SL", "Lot", "Risk $", "TP", "RR"]
                actual_cols_fibo = [col for col in cols_to_show_fibo if col in df_entry_plan_display.columns]
                if actual_cols_fibo:
                    st.dataframe(df_entry_plan_display[actual_cols_fibo], hide_index=True, use_container_width=True)
                else:
                    st.info("ไม่สามารถแสดงรายละเอียดแผน FIBO ได้ (อาจยังไม่ได้คำนวณ)")

                st.markdown("### 🎯 Global Take Profit Zones (FIBO)")
                h_str_fibo_tp = st.session_state.get("swing_high_fibo_val_v2", "")
                l_str_fibo_tp = st.session_state.get("swing_low_fibo_val_v2", "")
                direction_fibo_tp = st.session_state.get("direction_fibo_val_v2", "Long")

                if not h_str_fibo_tp or not l_str_fibo_tp:
                    st.info("📌 กรอก High/Low (FIBO) ใน Sidebar เพื่อคำนวณ Global TP Zones.")
                else:
                    high_tp_calc = float(h_str_fibo_tp)
                    low_tp_calc = float(l_str_fibo_tp)
                    if high_tp_calc > low_tp_calc:
                        range_fibo_tp = high_tp_calc - low_tp_calc
                        tp1_main = low_tp_calc + (range_fibo_tp * RATIO_TP1_EFF) if direction_fibo_tp == "Long" else high_tp_calc - (range_fibo_tp * RATIO_TP1_EFF)
                        tp2_main = low_tp_calc + (range_fibo_tp * RATIO_TP2_EFF) if direction_fibo_tp == "Long" else high_tp_calc - (range_fibo_tp * RATIO_TP2_EFF)
                        tp3_main = low_tp_calc + (range_fibo_tp * RATIO_TP3_EFF) if direction_fibo_tp == "Long" else high_tp_calc - (range_fibo_tp * RATIO_TP3_EFF)
                        
                        tp_df_main_display = pd.DataFrame({
                            "TP Zone": [f"TP1 ({RATIO_TP1_EFF:.3f})", f"TP2 ({RATIO_TP2_EFF:.3f})", f"TP3 ({RATIO_TP3_EFF:.3f})"],
                            "Price": [f"{tp1_main:.5f}", f"{tp2_main:.5f}", f"{tp3_main:.5f}"]
                        })
                        st.dataframe(tp_df_main_display, hide_index=True, use_container_width=True)
                    else: 
                        st.warning("📌 High (FIBO) ต้องมากกว่า Low เพื่อคำนวณ Global TP Zones.")
            
            elif active_mode_display == "CUSTOM":
                st.markdown(f"### 🎯 Entry & Take Profit Zones (CUSTOM - {st.session_state.get('asset_custom_val_v2', 'N/A')})")
                # *** MODIFIED: Added "TP (RR≈3)" to the list of columns to show ***
                cols_to_show_custom = ["Entry", "SL", "TP", "Lot", "Risk $", "RR", "TP (RR≈3)"]
                actual_cols_custom = [col for col in cols_to_show_custom if col in df_entry_plan_display.columns]
                
                if actual_cols_custom:
                    # Format TP (RR≈3) column for display if it's numeric
                    df_display_custom_formatted = df_entry_plan_display.copy()
                    if "TP (RR≈3)" in df_display_custom_formatted.columns:
                        # Ensure it's treated as numeric where possible for formatting, but keep "N/A" or "Error" as strings
                        def format_tp_rr3(val):
                            if isinstance(val, (float, int)):
                                return f"{val:.5f}"
                            return str(val) # Keep "N/A", "Error" as is
                        df_display_custom_formatted["TP (RR≈3)"] = df_display_custom_formatted["TP (RR≈3)"].apply(format_tp_rr3)

                    st.dataframe(df_display_custom_formatted[actual_cols_custom], hide_index=True, use_container_width=True)
                else:
                    st.info("ไม่สามารถแสดงรายละเอียดแผน CUSTOM ได้ (อาจยังไม่ได้คำนวณ หรือไม่พบคอลัมน์)")

                # Display RR warnings based on calculated data in entry_data_for_saving
                for i, entry_detail in enumerate(entry_data_for_saving):
                    rr_val_str = str(entry_detail.get("RR", "N/A")).lower()
                    if rr_val_str not in ["error", "n/a", ""]:
                        try:
                            rr_float = float(rr_val_str)
                            if 0 <= rr_float < 2.0: # Threshold for low RR
                                st.warning(f"🎯 Entry {i+1} (CUSTOM) มี RR ค่อนข้างต่ำ ({rr_float:.2f}). ลองปรับ TP/SL เพื่อ Risk:Reward ที่ดีขึ้น")
                        except ValueError:
                            pass 
            
            else: 
                st.info("กรุณาเลือก Trade Mode (FIBO/CUSTOM) ใน Sidebar")

        except Exception as e_display_plan:
            st.error(f"เกิดข้อผิดพลาดในการแสดงตารางแผนเทรด: {e_display_plan}")
            print(f"Error displaying entry plan table: {e_display_plan}")

    # ===================== SEC 5: MAIN AREA - AI ASSISTANT =======================
# This section uses the active_balance_to_use (via current_active_balance_for_summary) for AI simulation.

with st.expander("🤖 AI Assistant (วิเคราะห์ข้อมูล)", expanded=False): # Default to not expanded
    active_portfolio_id_for_ai = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_for_ai = st.session_state.get('active_portfolio_name_gs', "ทั่วไป (ไม่ได้เลือกพอร์ต)")
    
    # Use the balance that's currently active for calculations (from SEC 2/2.3)
    balance_for_ai_simulation = st.session_state.get('current_account_balance', DEFAULT_ACCOUNT_BALANCE) 
    
    report_title_suffix_planned_ai = "(จากข้อมูลแผนเทรดทั้งหมด)"
    report_title_suffix_actual_ai = "(จากข้อมูลผลการเทรดจริงทั้งหมด)"

    if active_portfolio_id_for_ai:
        report_title_suffix_planned_ai = f"(พอร์ต: '{active_portfolio_name_for_ai}' - จากแผน)"
        report_title_suffix_actual_ai = f"(พอร์ต: '{active_portfolio_name_for_ai}' - จากผลจริง)"
        st.info(f"AI Assistant กำลังวิเคราะห์ข้อมูลสำหรับพอร์ต: **'{active_portfolio_name_for_ai}'** (Balance เริ่มต้นจำลอง: {balance_for_ai_simulation:,.2f} USD)")
    else:
        st.info(f"AI Assistant กำลังวิเคราะห์ข้อมูลจากแผนเทรดและผลการเทรดจริงทั้งหมด (ยังไม่ได้เลือก Active Portfolio - Balance เริ่มต้นจำลอง: {balance_for_ai_simulation:,.2f} USD)")

    # --- Part 1: Analysis from PlannedTradeLogs ---
    df_ai_planned_logs_all = load_all_planned_trade_logs_from_gsheets() # Cached
    df_ai_planned_to_analyze = pd.DataFrame()
    
    if active_portfolio_id_for_ai and not df_ai_planned_logs_all.empty:
        if 'PortfolioID' in df_ai_planned_logs_all.columns:
            df_ai_planned_to_analyze = df_ai_planned_logs_all[df_ai_planned_logs_all['PortfolioID'] == str(active_portfolio_id_for_ai)].copy()
    elif not df_ai_planned_logs_all.empty: # No active portfolio, use all
        df_ai_planned_to_analyze = df_ai_planned_logs_all.copy()

    st.markdown(f"### 📝 AI Intelligence Report {report_title_suffix_planned_ai}")
    if df_ai_planned_to_analyze.empty:
        if df_ai_planned_logs_all.empty:
             st.info("ยังไม่มีข้อมูลแผนเทรดใน Log (Google Sheets) สำหรับวิเคราะห์")
        elif active_portfolio_id_for_ai:
             st.info(f"ไม่พบข้อมูลแผนเทรดใน Log สำหรับพอร์ต '{active_portfolio_name_for_ai}'.")
        else: # Should be covered by first case if all logs are empty
             st.info("ไม่พบข้อมูลแผนเทรดที่ตรงเงื่อนไขสำหรับวิเคราะห์")
    else: 
        # Ensure 'Risk $' is numeric, handle missing values for calculations
        if 'Risk $' in df_ai_planned_to_analyze.columns:
            df_ai_planned_to_analyze['Risk $'] = pd.to_numeric(df_ai_planned_to_analyze['Risk $'], errors='coerce').fillna(0.0)
        else: # If 'Risk $' column doesn't exist, create it with zeros to prevent errors
            df_ai_planned_to_analyze['Risk $'] = 0.0
            st.warning("AI (Planned): ไม่พบคอลัมน์ 'Risk $' ในข้อมูลแผนเทรด")

        total_trades_ai_planned_val = df_ai_planned_to_analyze.shape[0]
        win_trades_ai_planned_val = df_ai_planned_to_analyze[df_ai_planned_to_analyze["Risk $"] > 0].shape[0]
        winrate_ai_planned_val = (100 * win_trades_ai_planned_val / total_trades_ai_planned_val) if total_trades_ai_planned_val > 0 else 0.0
        gross_profit_ai_planned_val = df_ai_planned_to_analyze["Risk $"].sum()
        
        avg_rr_ai_planned_val = None
        if "RR" in df_ai_planned_to_analyze.columns:
            rr_series_planned_ai = pd.to_numeric(df_ai_planned_to_analyze["RR"], errors='coerce').dropna()
            if not rr_series_planned_ai.empty and rr_series_planned_ai.nunique() > 0 : # Check for non-empty and actual values
                 avg_rr_ai_planned_val = rr_series_planned_ai[rr_series_planned_ai > 0].mean() # Only positive RRs for average

        # Max Drawdown from PLANNED P/L (simulation)
        max_drawdown_sim_planned = 0.0
        if not df_ai_planned_to_analyze.empty:
            current_balance_sim = balance_for_ai_simulation 
            peak_balance_sim = balance_for_ai_simulation
            # Sort by Timestamp if available for more realistic drawdown simulation
            df_dd_calc_planned = df_ai_planned_to_analyze
            if "Timestamp" in df_dd_calc_planned.columns and pd.api.types.is_datetime64_any_dtype(df_dd_calc_planned['Timestamp']) and not df_dd_calc_planned['Timestamp'].isnull().all():
                 df_dd_calc_planned = df_dd_calc_planned.sort_values(by="Timestamp")
            
            for pnl_planned_val in df_dd_calc_planned["Risk $"]: # Assumes "Risk $" is P/L of the plan
                current_balance_sim += pnl_planned_val
                if current_balance_sim > peak_balance_sim: peak_balance_sim = current_balance_sim
                drawdown_val = peak_balance_sim - current_balance_sim
                if drawdown_val > max_drawdown_sim_planned: max_drawdown_sim_planned = drawdown_val
        
        # Best/Worst Day (from Planned P/L)
        win_day_planned, loss_day_planned = "-", "-"
        if "Timestamp" in df_ai_planned_to_analyze.columns and pd.api.types.is_datetime64_any_dtype(df_ai_planned_to_analyze['Timestamp']) and \
           not df_ai_planned_to_analyze.empty and not df_ai_planned_to_analyze['Timestamp'].isnull().all():
            
            df_daily_pnl_planned = df_ai_planned_to_analyze.copy()
            df_daily_pnl_planned.dropna(subset=["Timestamp"], inplace=True) # Ensure no NaT Timestamps
            if not df_daily_pnl_planned.empty:
                df_daily_pnl_planned["Weekday"] = df_daily_pnl_planned["Timestamp"].dt.day_name()
                daily_pnl_sum_planned = df_daily_pnl_planned.groupby("Weekday")["Risk $"].sum()
                if not daily_pnl_sum_planned.empty:
                    if daily_pnl_sum_planned.max() > 0: win_day_planned = daily_pnl_sum_planned.idxmax()
                    if daily_pnl_sum_planned.min() < 0: loss_day_planned = daily_pnl_sum_planned.idxmin()

        st.write(f"- **จำนวนแผนเทรดที่วิเคราะห์:** {total_trades_ai_planned_val:,}")
        st.write(f"- **Winrate (ตามแผน):** {winrate_ai_planned_val:.2f}%")
        st.write(f"- **กำไร/ขาดทุนสุทธิ (ตามแผน):** {gross_profit_ai_planned_val:,.2f} USD")
        st.write(f"- **RR เฉลี่ย (ตามแผน, >0):** {avg_rr_ai_planned_val:.2f}" if pd.notna(avg_rr_ai_planned_val) else "N/A")
        st.write(f"- **Max Drawdown (จำลองจากแผน):** {max_drawdown_sim_planned:,.2f} USD")
        st.write(f"- **วันที่ทำกำไรดีที่สุด (ตามแผน):** {win_day_planned}")
        st.write(f"- **วันที่ขาดทุนมากที่สุด (ตามแผน):** {loss_day_planned}")
        
        st.markdown("#### 🤖 AI Insight (จากแผนเทรด)")
        # ... (AI Insight messages logic as in original File1, adapted for new variable names) ...
        insight_msgs_planned_ai = []
        if total_trades_ai_planned_val > 0 : 
            if winrate_ai_planned_val >= 60: insight_msgs_planned_ai.append(f"✅ Winrate (แผน: {winrate_ai_planned_val:.1f}%) สูง: ระบบการวางแผนมีแนวโน้มที่ดี")
            elif winrate_ai_planned_val < 40 and total_trades_ai_planned_val >=10 : insight_msgs_planned_ai.append(f"⚠️ Winrate (แผน: {winrate_ai_planned_val:.1f}%) ต่ำ: ควรทบทวนกลยุทธ์การวางแผน")
            if avg_rr_ai_planned_val is not None and avg_rr_ai_planned_val < 1.5 and total_trades_ai_planned_val >=5 : insight_msgs_planned_ai.append(f"📉 RR เฉลี่ย (แผน: {avg_rr_ai_planned_val:.2f}) ต่ำกว่า 1.5: อาจต้องพิจารณาการตั้ง TP/SL เพื่อ Risk:Reward ที่เหมาะสมขึ้น")
            if balance_for_ai_simulation > 0 and max_drawdown_sim_planned > (balance_for_ai_simulation * 0.10) : insight_msgs_planned_ai.append(f"🚨 Max Drawdown (จำลองจากแผน: {max_drawdown_sim_planned:,.2f} USD) ค่อนข้างสูง ({ (max_drawdown_sim_planned/balance_for_ai_simulation)*100:.1f}% ของ Balance): ควรระมัดระวัง")
        if not insight_msgs_planned_ai and total_trades_ai_planned_val > 0: insight_msgs_planned_ai = ["ดูเหมือนว่าข้อมูลแผนเทรดที่วิเคราะห์ยังไม่มีจุดที่น่ากังวลเป็นพิเศษ"]
        
        for msg_ai_p in insight_msgs_planned_ai:
            if "✅" in msg_ai_p: st.success(msg_ai_p)
            elif "⚠️" in msg_ai_p or "📉" in msg_ai_p: st.warning(msg_ai_p)
            elif "🚨" in msg_ai_p: st.error(msg_ai_p)
            else: st.info(msg_ai_p)

    st.markdown("---") # Separator

    # --- Part 2: Analysis from ActualTrades (Deals) ---
    df_ai_actual_trades_all = load_actual_trades_from_gsheets() # Cached
    df_ai_actual_to_analyze = pd.DataFrame()

    if active_portfolio_id_for_ai and not df_ai_actual_trades_all.empty:
        if 'PortfolioID' in df_ai_actual_trades_all.columns:
            df_ai_actual_to_analyze = df_ai_actual_trades_all[df_ai_actual_trades_all['PortfolioID'] == str(active_portfolio_id_for_ai)].copy()
    elif not df_ai_actual_trades_all.empty: # No active portfolio, use all
        df_ai_actual_to_analyze = df_ai_actual_trades_all.copy()

    st.markdown(f"### 📈 AI Intelligence Report {report_title_suffix_actual_ai}")
    if df_ai_actual_to_analyze.empty:
        if df_ai_actual_trades_all.empty :
             st.info("ยังไม่มีข้อมูลผลการเทรดจริงใน Log (Google Sheets) สำหรับวิเคราะห์")
        elif active_portfolio_id_for_ai:
             st.info(f"ไม่พบข้อมูลผลการเทรดจริงใน Log สำหรับพอร์ต '{active_portfolio_name_for_ai}'.")
        else:
             st.info("ไม่พบข้อมูลผลการเทรดจริงที่ตรงเงื่อนไขสำหรับวิเคราะห์")

    elif 'Profit_Deal' not in df_ai_actual_to_analyze.columns:
        st.warning("AI (Actual): ไม่พบคอลัมน์ 'Profit_Deal' ในข้อมูลผลการเทรดจริง ไม่สามารถคำนวณสถิติได้")
    else:
        # Ensure 'Profit_Deal' is numeric
        df_ai_actual_to_analyze['Profit_Deal'] = pd.to_numeric(df_ai_actual_to_analyze['Profit_Deal'], errors='coerce').fillna(0.0)

        # Filter out non-trading deals (e.g., 'balance', 'credit')
        df_trading_deals_ai = df_ai_actual_to_analyze
        if 'Type_Deal' in df_ai_actual_to_analyze.columns:
            df_trading_deals_ai = df_ai_actual_to_analyze[
                ~df_ai_actual_to_analyze['Type_Deal'].astype(str).str.lower().isin(['balance', 'credit', 'deposit', 'withdrawal']) # Expanded list
            ].copy()
        
        if df_trading_deals_ai.empty:
            st.info("ไม่พบรายการ Deals ที่เป็นการซื้อขายจริงสำหรับวิเคราะห์ (หลังจากกรอง Balance/Credit/Deposit/Withdrawal)")
        else:
            actual_total_deals_val = len(df_trading_deals_ai)
            actual_winning_deals_df = df_trading_deals_ai[df_trading_deals_ai['Profit_Deal'] > 0]
            actual_losing_deals_df = df_trading_deals_ai[df_trading_deals_ai['Profit_Deal'] < 0]
            
            actual_winning_deals_count_val = len(actual_winning_deals_df)
            actual_losing_deals_count_val = len(actual_losing_deals_df)

            actual_win_rate_val = (100 * actual_winning_deals_count_val / actual_total_deals_val) if actual_total_deals_val > 0 else 0.0
            
            actual_gross_profit_val = actual_winning_deals_df['Profit_Deal'].sum()
            actual_gross_loss_val = abs(actual_losing_deals_df['Profit_Deal'].sum())

            actual_profit_factor_val = actual_gross_profit_val / actual_gross_loss_val if actual_gross_loss_val > 0 else float('inf') if actual_gross_profit_val > 0 else 0.0
            
            actual_avg_profit_deal_val = actual_gross_profit_val / actual_winning_deals_count_val if actual_winning_deals_count_val > 0 else 0.0
            actual_avg_loss_deal_val = actual_gross_loss_val / actual_losing_deals_count_val if actual_losing_deals_count_val > 0 else 0.0
            
            st.write(f"- **จำนวน Deals ซื้อขายจริง:** {actual_total_deals_val:,}")
            st.write(f"- **Deal-Level Win Rate (ผลจริง):** {actual_win_rate_val:.2f}%")
            st.write(f"- **กำไรทั้งหมด (Gross Profit - ผลจริง):** {actual_gross_profit_val:,.2f} USD")
            st.write(f"- **ขาดทุนทั้งหมด (Gross Loss - ผลจริง):** {actual_gross_loss_val:,.2f} USD")
            st.write(f"- **Profit Factor (Deal-Level - ผลจริง):** {actual_profit_factor_val:.2f}" if actual_profit_factor_val != float('inf') else "∞ (No Losses)" if actual_gross_profit_val > 0 else "0.00 (No Profit/Loss)")
            st.write(f"- **กำไรเฉลี่ยต่อ Deal ที่ชนะ (ผลจริง):** {actual_avg_profit_deal_val:,.2f} USD")
            st.write(f"- **ขาดทุนเฉลี่ยต่อ Deal ที่แพ้ (ผลจริง):** {actual_avg_loss_deal_val:,.2f} USD")

            st.markdown("#### 🤖 AI Insight (จากผลการเทรดจริง)")
            # ... (AI Insight messages logic as in original File1, adapted for new variable names) ...
            insight_msgs_actual_ai = []
            if actual_total_deals_val > 0:
                if actual_win_rate_val >= 50: insight_msgs_actual_ai.append(f"✅ Win Rate (ผลจริง: {actual_win_rate_val:.1f}%) อยู่ในเกณฑ์ดี")
                else: insight_msgs_actual_ai.append(f"📉 Win Rate (ผลจริง: {actual_win_rate_val:.1f}%) ควรปรับปรุง")
                if actual_profit_factor_val > 1.5: insight_msgs_actual_ai.append(f"📈 Profit Factor (ผลจริง: {actual_profit_factor_val:.2f}) อยู่ในระดับที่ดี")
                elif actual_profit_factor_val < 1.0 and actual_total_deals_val >= 10: insight_msgs_actual_ai.append(f"⚠️ Profit Factor (ผลจริง: {actual_profit_factor_val:.2f}) ต่ำกว่า 1 บ่งชี้ว่าขาดทุนมากกว่ากำไร ควรทบทวนกลยุทธ์")
            
            if not insight_msgs_actual_ai and actual_total_deals_val > 0 : insight_msgs_actual_ai = ["ข้อมูลผลการเทรดจริงกำลังถูกรวบรวม โปรดตรวจสอบ Insights เพิ่มเติมในอนาคต"]
            elif not actual_total_deals_val > 0 : insight_msgs_actual_ai = ["ยังไม่มีข้อมูลผลการเทรดจริงเพียงพอสำหรับการสร้าง Insight"]

            for msg_ai_a in insight_msgs_actual_ai:
                if "✅" in msg_ai_a or "📈" in msg_ai_a : st.success(msg_ai_a)
                elif "⚠️" in msg_ai_a or "📉" in msg_ai_a: st.warning(msg_ai_a)
                else: st.info(msg_ai_a)

# ===================== SEC 6: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
with st.expander("📂  Ultimate Chart Dashboard Import & Processing", expanded=False):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")
# Helper functions (extract_data_from_report_content_sec6, save_transactional_data_to_gsheets_sec6, 
# save_deals_to_actual_trades_sec6, save_orders_to_gsheets_sec6, save_positions_to_gsheets_sec6,
# save_results_summary_to_gsheets_sec6) are assumed to be defined above or globally as in your original mainV2.0.0.py.
# Ensure they are correctly defined and accessible.

# --- START: Placeholder for Helper Functions for SEC 6 (Copy from your mainV2.0.0.py) ---
def extract_data_from_report_content_sec6(file_content_str_input):
    # ... (Full implementation from your mainV2.0.0.py) ...
    extracted_data = {'deals': pd.DataFrame(), 'orders': pd.DataFrame(), 'positions': pd.DataFrame(), 'balance_summary': {}, 'results_summary': {}}
    def safe_float_convert(value_str):
        if isinstance(value_str, (int, float)): return value_str
        try:
            clean_value = str(value_str).strip().replace(" ", "").replace(",", "").replace("%", "")
            if not clean_value: return None
            if clean_value.count('.') > 1:
                parts = clean_value.split('.'); integer_part = "".join(parts[:-1]); decimal_part = parts[-1]
                clean_value = integer_part + "." + decimal_part
            return float(clean_value)
        except (ValueError, TypeError, AttributeError): return None
    lines = []
    if isinstance(file_content_str_input, str): lines = file_content_str_input.strip().split('\n')
    elif isinstance(file_content_str_input, bytes): lines = file_content_str_input.decode('utf-8', errors='replace').strip().split('\n')
    else: return extracted_data
    if not lines: return extracted_data
    section_raw_headers = {"Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit", "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment", "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment"}
    expected_cleaned_columns = {"Positions": ["Time_Pos", "Position_ID", "Symbol_Pos", "Type_Pos", "Volume_Pos", "Price_Open_Pos", "S_L_Pos", "T_P_Pos", "Time_Close_Pos", "Price_Close_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos"], "Orders": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Filler_Ord","Comment_Ord"], "Deals": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal"]}
    section_order_for_tables = ["Positions", "Orders", "Deals"]; section_header_indices = {}
    for line_idx, current_line_str in enumerate(lines):
        stripped_line = current_line_str.strip()
        for section_name, raw_header_template in section_raw_headers.items():
            if section_name not in section_header_indices:
                first_col_of_template = raw_header_template.split(',')[0].strip()
                if stripped_line.startswith(first_col_of_template) and raw_header_template in stripped_line: section_header_indices[section_name] = line_idx; break
    for table_idx, section_name in enumerate(section_order_for_tables):
        section_key_lower = section_name.lower()
        if section_name in section_header_indices:
            header_line_num = section_header_indices[section_name]; data_start_line_num = header_line_num + 1; data_end_line_num = len(lines)
            for next_table_name_idx in range(table_idx + 1, len(section_order_for_tables)):
                next_table_section_name = section_order_for_tables[next_table_name_idx]
                if next_table_section_name in section_header_indices: data_end_line_num = section_header_indices[next_table_section_name]; break
            current_table_data_lines = []
            for line_num_for_data in range(data_start_line_num, data_end_line_num):
                line_content_for_data = lines[line_num_for_data].strip()
                if not line_content_for_data:
                    if any(current_table_data_lines): pass
                    else: continue
                if line_content_for_data.startswith(("Balance:", "Credit Facility:", "Floating P/L:", "Equity:", "Results", "Total Net Profit:")): break
                is_another_header_line = False
                for other_sec_name, other_raw_hdr_template in section_raw_headers.items():
                    if other_sec_name != section_name and line_content_for_data.startswith(other_raw_hdr_template.split(',')[0]) and other_raw_hdr_template in line_content_for_data: is_another_header_line = True; break
                if is_another_header_line: break
                if section_name == "Deals":
                    cols_in_line = [col.strip() for col in line_content_for_data.split(',')]; is_balance_type_row = False
                    if len(cols_in_line) > 3 and str(cols_in_line[3]).lower() in ['balance', 'credit', 'initial_deposit', 'deposit', 'withdrawal', 'correction']: is_balance_type_row = True
                    missing_essential_identifiers = False
                    if len(cols_in_line) < 3: missing_essential_identifiers = True
                    elif not cols_in_line[0] or not cols_in_line[1] or not cols_in_line[2]: missing_essential_identifiers = True
                    if is_balance_type_row or missing_essential_identifiers: continue
                current_table_data_lines.append(line_content_for_data)
            if current_table_data_lines:
                csv_data_str = "\n".join(current_table_data_lines)
                try:
                    col_names_for_df = expected_cleaned_columns[section_name]; df_section = pd.read_csv(io.StringIO(csv_data_str), header=None, names=col_names_for_df, skipinitialspace=True, on_bad_lines='warn', engine='python', dtype=str)
                    df_section.dropna(how='all', inplace=True); final_cols = expected_cleaned_columns[section_name]
                    for col in final_cols:
                        if col not in df_section.columns: df_section[col] = ""
                    df_section = df_section[final_cols]
                    if section_name == "Deals" and not df_section.empty and "Symbol_Deal" in df_section.columns: df_section = df_section[df_section["Symbol_Deal"].astype(str).str.strip() != ""]
                    if not df_section.empty: extracted_data[section_key_lower] = df_section
                except Exception: pass
    balance_summary_dict = {}; balance_start_line_idx = -1
    for i, line in enumerate(lines):
        if line.strip().lower().startswith("balance:"): balance_start_line_idx = i; break
    if balance_start_line_idx != -1:
        for i_bal in range(balance_start_line_idx, min(balance_start_line_idx + 8, len(lines))):
            line_stripped = lines[i_bal].strip()
            if not line_stripped : continue
            if line_stripped.startswith(("Results", "Total Net Profit:")) and i_bal > balance_start_line_idx: break
            parts_raw = line_stripped.split(',')
            if line_stripped.lower().startswith("balance:"):
                if len(parts_raw) > 3:
                    val_from_parts = safe_float_convert(parts_raw[3].strip())
                    if val_from_parts is not None: balance_summary_dict['balance'] = val_from_parts
            elif line_stripped.lower().startswith("equity:"):
                if len(parts_raw) > 3:
                    val_from_parts = safe_float_convert(parts_raw[3].strip())
                    if val_from_parts is not None: balance_summary_dict['equity'] = val_from_parts
            temp_key = ""; val_expected_next = False
            for part_val in parts_raw:
                part_val_clean = part_val.strip()
                if not part_val_clean: continue
                if ':' in part_val_clean:
                    key_str, val_str = part_val_clean.split(':', 1); key_clean = key_str.strip().replace(" ", "_").replace(".", "").replace("/","_").lower(); val_strip = val_str.strip()
                    if val_strip:
                        num_val = safe_float_convert(val_strip.split(' ')[0])
                        if num_val is not None and (key_clean not in balance_summary_dict or balance_summary_dict[key_clean] is None): balance_summary_dict[key_clean] = num_val
                        val_expected_next = False; temp_key = ""
                    else: temp_key = key_clean; val_expected_next = True
                elif val_expected_next and temp_key:
                    num_val = safe_float_convert(part_val_clean.split(' ')[0])
                    if num_val is not None and (temp_key not in balance_summary_dict or balance_summary_dict[temp_key] is None): balance_summary_dict[temp_key] = num_val
                    temp_key = ""; val_expected_next = False
    essential_balance_keys = ["balance", "equity", "free_margin", "margin", "floating_p_l", "margin_level", "credit_facility"]
    for k_b in essential_balance_keys:
        if k_b not in balance_summary_dict: balance_summary_dict[k_b] = None
    extracted_data['balance_summary'] = balance_summary_dict
    results_summary_dict = {}; stat_definitions_map = {"Total Net Profit": "Total_Net_Profit", "Gross Profit": "Gross_Profit", "Gross Loss": "Gross_Loss", "Profit Factor": "Profit_Factor", "Expected Payoff": "Expected_Payoff", "Recovery Factor": "Recovery_Factor", "Sharpe Ratio": "Sharpe_Ratio", "Balance Drawdown Absolute": "Balance_Drawdown_Absolute", "Balance Drawdown Maximal": "Balance_Drawdown_Maximal", "Balance Drawdown Relative": "Balance_Drawdown_Relative_Percent", "Total Trades": "Total_Trades", "Short Trades (won %)": "Short_Trades", "Long Trades (won %)": "Long_Trades", "Profit Trades (% of total)": "Profit_Trades", "Loss Trades (% of total)": "Loss_Trades", "Largest profit trade": "Largest_profit_trade", "Largest loss trade": "Largest_loss_trade", "Average profit trade": "Average_profit_trade", "Average loss trade": "Average_loss_trade", "Maximum consecutive wins ($)": "Maximum_consecutive_wins_Count", "Maximal consecutive profit (count)": "Maximal_consecutive_profit_Amount", "Average consecutive wins": "Average_consecutive_wins", "Maximum consecutive losses ($)": "Maximum_consecutive_losses_Count", "Maximal consecutive loss (count)": "Maximal_consecutive_loss_Amount", "Average consecutive losses": "Average_consecutive_losses"}
    results_start_line_idx = -1; results_section_processed_lines = 0; max_lines_for_results = 35
    for i_res, line_res in enumerate(lines):
        if results_start_line_idx == -1 and (line_res.strip().startswith("Results") or line_res.strip().startswith("Total Net Profit:")):
            results_start_line_idx = i_res
            if line_res.strip().startswith("Total Net Profit:"): results_start_line_idx -=1
            continue
        if results_start_line_idx != -1 and results_section_processed_lines < max_lines_for_results:
            line_stripped_res = line_res.strip()
            if not line_stripped_res:
                if results_section_processed_lines > 2: break
                else: continue
            results_section_processed_lines += 1; row_cells = [cell.strip() for cell in line_stripped_res.split(',')]
            for c_idx, cell_content in enumerate(row_cells):
                if not cell_content: continue
                current_label = cell_content.replace(':', '').strip()
                if current_label in stat_definitions_map:
                    gsheet_key = stat_definitions_map[current_label]
                    for k_val_search in range(1, 5):
                        if (c_idx + k_val_search) < len(row_cells):
                            raw_value_from_cell = row_cells[c_idx + k_val_search]
                            if raw_value_from_cell:
                                value_part_before_paren = raw_value_from_cell.split('(')[0].strip(); numeric_value = safe_float_convert(value_part_before_paren)
                                if numeric_value is not None:
                                    results_summary_dict[gsheet_key] = numeric_value
                                    if '(' in raw_value_from_cell and ')' in raw_value_from_cell:
                                        try:
                                            paren_content_str = raw_value_from_cell[raw_value_from_cell.find('(')+1:raw_value_from_cell.find(')')].strip().replace('%',''); paren_numeric_value = safe_float_convert(paren_content_str)
                                            if paren_numeric_value is not None:
                                                if current_label == "Balance Drawdown Maximal": results_summary_dict["Balance_Drawdown_Maximal_Percent"] = paren_numeric_value
                                                elif current_label == "Balance Drawdown Relative": results_summary_dict["Balance_Drawdown_Relative_Amount"] = numeric_value
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
            if line_stripped_res.startswith("Average consecutive losses"): break
        elif results_start_line_idx != -1 and results_section_processed_lines >= max_lines_for_results: break
    extracted_data['results_summary'] = results_summary_dict
    return extracted_data

def save_transactional_data_to_gsheets_sec6(ws, df_input, unique_id_col, expected_headers_with_portfolio, data_type_name, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
    # ... (Full implementation from your mainV2.0.0.py) ...
    if df_input is None or df_input.empty: return True, 0, 0
    try:
        if ws is None: return False, 0, 0
        current_headers = []; header_check_successful = False
        if ws.row_count > 0:
            try: current_headers = ws.row_values(1); header_check_successful = True
            except Exception: pass
        if not header_check_successful or not current_headers or all(h == "" for h in current_headers) or set(current_headers) != set(expected_headers_with_portfolio):
            try: ws.update([expected_headers_with_portfolio], value_input_option='USER_ENTERED')
            except Exception: return False, 0, 0
        existing_ids = set()
        if ws.row_count > 1:
            try:
                all_sheet_records = ws.get_all_records(expected_headers=expected_headers_with_portfolio, numericise_ignore=['all'])
                if all_sheet_records:
                    df_existing_sheet_data = pd.DataFrame(all_sheet_records)
                    if 'PortfolioID' in df_existing_sheet_data.columns and unique_id_col in df_existing_sheet_data.columns:
                        df_existing_sheet_data['PortfolioID'] = df_existing_sheet_data['PortfolioID'].astype(str)
                        df_portfolio_data = df_existing_sheet_data[df_existing_sheet_data['PortfolioID'] == str(portfolio_id)]
                        if not df_portfolio_data.empty: existing_ids = set(df_portfolio_data[unique_id_col].astype(str).str.strip().tolist())
            except Exception as e_get_existing_ids: print(f"Warning ({data_type_name}): Could not get existing IDs from '{ws.title}'. Deduplication incomplete: {e_get_existing_ids}")
        df_to_check = df_input.copy()
        if unique_id_col not in df_to_check.columns: new_df = df_to_check
        else:
            df_to_check[unique_id_col] = df_to_check[unique_id_col].astype(str).str.strip()
            new_df = df_to_check[~df_to_check[unique_id_col].isin(existing_ids)]
        num_new = len(new_df); num_duplicates_skipped = len(df_to_check) - num_new
        if new_df.empty: return True, num_new, num_duplicates_skipped
        new_df_to_save = new_df.copy(); new_df_to_save["PortfolioID"] = str(portfolio_id); new_df_to_save["PortfolioName"] = str(portfolio_name); new_df_to_save["SourceFile"] = str(source_file_name); new_df_to_save["ImportBatchID"] = str(import_batch_id)
        final_df_for_append = pd.DataFrame(columns=expected_headers_with_portfolio)
        for col_h in expected_headers_with_portfolio:
            if col_h in new_df_to_save.columns: final_df_for_append[col_h] = new_df_to_save[col_h]
            else: final_df_for_append[col_h] = ""
        list_of_lists = final_df_for_append.astype(str).replace('nan', '').replace('None','').fillna("").values.tolist()
        if list_of_lists: ws.append_rows(list_of_lists, value_input_option='USER_ENTERED')
        return True, num_new, num_duplicates_skipped
    except Exception as e_save_trans: print(f"Error saving {data_type_name} to GSheets: {e_save_trans}"); return False, 0, 0

def save_deals_to_actual_trades_sec6(ws, df_deals_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
    expected_headers_deals = ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
    return save_transactional_data_to_gsheets_sec6(ws, df_deals_input, "Deal_ID", expected_headers_deals, "Deals", portfolio_id, portfolio_name, source_file_name, import_batch_id)

def save_orders_to_gsheets_sec6(ws, df_orders_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
    expected_headers_orders = ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Filler_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
    return save_transactional_data_to_gsheets_sec6(ws, df_orders_input, "Order_ID_Ord", expected_headers_orders, "Orders", portfolio_id, portfolio_name, source_file_name, import_batch_id)

def save_positions_to_gsheets_sec6(ws, df_positions_input, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
    expected_headers_positions = ["Time_Pos", "Position_ID", "Symbol_Pos", "Type_Pos", "Volume_Pos", "Price_Open_Pos", "S_L_Pos", "T_P_Pos", "Time_Close_Pos", "Price_Close_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]
    return save_transactional_data_to_gsheets_sec6(ws, df_positions_input, "Position_ID", expected_headers_positions, "Positions", portfolio_id, portfolio_name, source_file_name, import_batch_id)
    
def save_results_summary_to_gsheets_sec6(ws, balance_summary_data, results_summary_data, portfolio_id, portfolio_name, source_file_name="N/A", import_batch_id="N/A"):
    # ... (Full implementation from your mainV2.0.0.py) ...
    try:
        if ws is None: return False, "Worksheet object is None"
        expected_headers = ["Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", "Balance", "Equity", "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Credit_Facility", "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", "Total_Trades", "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count", "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count", "Average_consecutive_wins", "Average_consecutive_losses"]
        current_headers_ws = []
        if ws.row_count > 0:
            try: current_headers_ws = ws.row_values(1)
            except Exception: pass
        if not current_headers_ws or all(h == "" for h in current_headers_ws) or set(current_headers_ws) != set(expected_headers): ws.update([expected_headers], value_input_option='USER_ENTERED')
        new_summary_row_data = {h: None for h in expected_headers}; new_summary_row_data.update({"Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "PortfolioID": str(portfolio_id), "PortfolioName": str(portfolio_name), "SourceFile": str(source_file_name), "ImportBatchID": str(import_batch_id)})
        balance_key_map = {"balance":"Balance", "equity":"Equity", "free_margin":"Free_Margin", "margin":"Margin", "floating_p_l":"Floating_P_L", "margin_level":"Margin_Level", "credit_facility": "Credit_Facility"}
        if isinstance(balance_summary_data, dict):
            for k_extract, k_gsheet in balance_key_map.items():
                if k_extract in balance_summary_data: new_summary_row_data[k_gsheet] = balance_summary_data[k_extract]
        if isinstance(results_summary_data, dict):
            for k_gsheet_expected in expected_headers:
                if k_gsheet_expected in results_summary_data: new_summary_row_data[k_gsheet_expected] = results_summary_data[k_gsheet_expected]
        comparison_keys_summary = ["Balance", "Equity", "Total_Net_Profit", "Total_Trades", "ImportBatchID"]
        new_summary_fingerprint_values = []
        for k_comp_sum in comparison_keys_summary:
            val_sum = new_summary_row_data.get(k_comp_sum)
            try: new_summary_fingerprint_values.append(f"{float(val_sum):.2f}" if pd.notna(val_sum) and isinstance(val_sum, (float, int)) else str(val_sum).strip())
            except (ValueError, TypeError): new_summary_fingerprint_values.append(str(val_sum).strip() if pd.notna(val_sum) else "None")
        new_summary_fingerprint = tuple(new_summary_fingerprint_values)
        if ws.row_count > 1:
            try:
                existing_summaries_records = ws.get_all_records(expected_headers=expected_headers, numericise_ignore=['all']); df_existing_summaries = pd.DataFrame(existing_summaries_records)
                if not df_existing_summaries.empty and 'PortfolioID' in df_existing_summaries.columns:
                    df_portfolio_summaries = df_existing_summaries[df_existing_summaries['PortfolioID'].astype(str) == str(portfolio_id)]
                    for _, existing_row_sum in df_portfolio_summaries.iterrows():
                        existing_summary_comparable_values = []
                        for k_comp_sum_exist in comparison_keys_summary:
                            val_exist = existing_row_sum.get(k_comp_sum_exist)
                            try: existing_summary_comparable_values.append(f"{float(val_exist):.2f}" if pd.notna(val_exist) and isinstance(val_exist, (float,int)) else str(val_exist).strip())
                            except (ValueError, TypeError): existing_summary_comparable_values.append(str(val_exist).strip() if pd.notna(val_exist) else "None")
                        if tuple(existing_summary_comparable_values) == new_summary_fingerprint: return True, "skipped_duplicate_content"
            except Exception as e_get_sum_records_dedup: print(f"Warning (Summary Deduplication): Could not get existing summaries for deduplication: {e_get_sum_records_dedup}")
        final_row_values = [str(new_summary_row_data.get(h, "")).strip() for h in expected_headers]; ws.append_rows([final_row_values], value_input_option='USER_ENTERED')
        return True, "saved_new"
    except Exception as e_save_summary: print(f"Error saving results summary to GSheet: {e_save_summary}"); return False, f"Exception during save: {e_save_summary}"
# --- END: Helper Functions for SEC 6 ---

#st.markdown("---") #
#st.subheader("📤 อัปโหลด Statement Report (CSV) เพื่อประมวลผลและบันทึก") #

if 'uploader_key_version' not in st.session_state: # Should be in SEC 0, but defensive check
    st.session_state.uploader_key_version = 0 #

uploaded_file_statement = st.file_uploader(
    "ลากและวางไฟล์ Statement Report (CSV) ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
    type=["csv"], #
    key=f"ultimate_stmt_uploader_v2_{st.session_state.uploader_key_version}" # Use a distinct key
)

st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้ + Log การทำงานบางส่วนใน Console)", 
            value=st.session_state.get("debug_statement_processing_v2", False), # Persist debug mode choice
            key="debug_statement_processing_v2") #

active_portfolio_id_for_stmt_import = st.session_state.get('active_portfolio_id_gs', None) #
active_portfolio_name_for_stmt_import = st.session_state.get('active_portfolio_name_gs', None) #

# Flag to ensure processing logic for a single upload runs only once per script execution cycle
_UPLOAD_PROCESSED_IN_THIS_CYCLE = "_upload_processed_in_this_cycle_v2" 
if _UPLOAD_PROCESSED_IN_THIS_CYCLE not in st.session_state:
    st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE] = False

if uploaded_file_statement is not None and not st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE]:
    st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE] = True # Mark as processing for this cycle
    
    file_name_stmt = uploaded_file_statement.name #
    file_size_stmt = uploaded_file_statement.size #
    
    file_hash_stmt = ""
    try:
        uploaded_file_statement.seek(0) #
        file_content_for_hash_stmt = uploaded_file_statement.read() #
        uploaded_file_statement.seek(0) #
        file_hash_stmt = hashlib.md5(file_content_for_hash_stmt).hexdigest() #
    except Exception as e_hash_stmt:
        file_hash_stmt = f"hash_error_{random.randint(1000,9999)}" #
        print(f"Warning: Could not compute MD5 hash for file: {e_hash_stmt}") #

    # This flag will determine if a st.rerun() is needed at the very end of this block
    # It's true by default to ensure the uploader is reset.
    # It can be set to False only if we are absolutely sure no rerun is needed (very rare).
    _trigger_rerun_after_upload_handling = True 
    _equity_updated_successfully_this_cycle = False

    if not active_portfolio_id_for_stmt_import:
        st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.") #
        # No st.stop(), proceed to uploader reset logic at the end
    else:
        st.info(f"ไฟล์ที่อัปโหลด: {file_name_stmt} (ขนาด: {file_size_stmt} bytes, Hash: {file_hash_stmt})") #
        
        gc_stmt = get_gspread_client() #
        if not gc_stmt:
            st.error("ไม่สามารถเชื่อมต่อ Google Sheets Client ได้") #
            # No st.stop()
        else:
            ws_stmt_dict = {} #
            # Ensure worksheet constants from SEC 0 are used here
            worksheet_definitions_stmt = {
                WORKSHEET_UPLOAD_HISTORY: {"rows": "1000", "cols": "10", "headers": ["UploadTimestamp", "PortfolioID", "PortfolioName", "FileName", "FileSize", "FileHash", "Status", "ImportBatchID", "Notes"]}, #
                WORKSHEET_ACTUAL_TRADES: {"rows": "2000", "cols": "18", "headers": ["Time_Deal", "Deal_ID", "Symbol_Deal", "Type_Deal", "Direction_Deal", "Volume_Deal", "Price_Deal", "Order_ID_Deal", "Commission_Deal", "Fee_Deal", "Swap_Deal", "Profit_Deal", "Balance_Deal", "Comment_Deal", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]}, #
                WORKSHEET_ACTUAL_ORDERS: {"rows": "1000", "cols": "16", "headers": ["Open_Time_Ord", "Order_ID_Ord", "Symbol_Ord", "Type_Ord", "Volume_Ord", "Price_Ord", "S_L_Ord", "T_P_Ord", "Close_Time_Ord", "State_Ord", "Filler_Ord", "Comment_Ord", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]}, #
                WORKSHEET_ACTUAL_POSITIONS: {"rows": "1000", "cols": "17", "headers": ["Time_Pos", "Position_ID", "Symbol_Pos", "Type_Pos", "Volume_Pos", "Price_Open_Pos", "S_L_Pos", "T_P_Pos", "Time_Close_Pos", "Price_Close_Pos", "Commission_Pos", "Swap_Pos", "Profit_Pos", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID"]}, #
                WORKSHEET_STATEMENT_SUMMARIES: {"rows": "1000", "cols": "46", "headers": [ # Ensure full headers list
                    "Timestamp", "PortfolioID", "PortfolioName", "SourceFile", "ImportBatchID", "Balance", "Equity", 
                    "Free_Margin", "Margin", "Floating_P_L", "Margin_Level", "Credit_Facility", "Total_Net_Profit", 
                    "Gross_Profit", "Gross_Loss", "Profit_Factor", "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", 
                    "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", "Balance_Drawdown_Maximal_Percent", 
                    "Balance_Drawdown_Relative_Percent", "Balance_Drawdown_Relative_Amount", "Total_Trades", 
                    "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", "Long_Trades_won_Percent", 
                    "Profit_Trades", "Profit_Trades_Percent_of_total", "Loss_Trades", "Loss_Trades_Percent_of_total", 
                    "Largest_profit_trade", "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", 
                    "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", 
                    "Maximal_consecutive_profit_Amount", "Maximal_consecutive_profit_Count",
                    "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit", 
                    "Maximal_consecutive_loss_Amount", "Maximal_consecutive_loss_Count",
                    "Average_consecutive_wins", "Average_consecutive_losses"
                ]}
            }
            sheets_ok_stmt = True #
            sh_log_stmt = None #
            try:
                sh_log_stmt = gc_stmt.open(GOOGLE_SHEET_NAME) #
                for ws_name, specs in worksheet_definitions_stmt.items():
                    try:
                        ws_stmt_dict[ws_name] = sh_log_stmt.worksheet(ws_name) #
                        # Header check and update logic (as in File2)
                        current_ws_headers = []
                        if ws_stmt_dict[ws_name].row_count > 0:
                            try: current_ws_headers = ws_stmt_dict[ws_name].row_values(1) #
                            except Exception: pass
                        if not current_ws_headers or all(h=="" for h in current_ws_headers) or set(current_ws_headers) != set(specs["headers"]):
                            if "headers" in specs:
                                ws_stmt_dict[ws_name].update([specs["headers"]], value_input_option='USER_ENTERED') #
                                print(f"Info: Headers updated/written for worksheet '{ws_name}'.") #
                    except gspread.exceptions.WorksheetNotFound:
                        print(f"Info: Worksheet '{ws_name}' not found. Creating it now...") #
                        try:
                            new_ws_stmt = sh_log_stmt.add_worksheet(title=ws_name, rows=specs.get("rows", "1000"), cols=specs.get("cols", "26")) # Adjust cols if needed
                            ws_stmt_dict[ws_name] = new_ws_stmt #
                            if "headers" in specs:
                                new_ws_stmt.update([specs["headers"]], value_input_option='USER_ENTERED') #
                        except Exception as e_add_ws_stmt:
                            st.error(f"❌ Failed to create worksheet '{ws_name}': {e_add_ws_stmt}") #
                            sheets_ok_stmt = False; break #
                    except Exception as e_open_ws_stmt:
                        st.error(f"❌ Error accessing worksheet '{ws_name}': {e_open_ws_stmt}") #
                        sheets_ok_stmt = False; break #
                if not sheets_ok_stmt: gc_stmt = None # Prevent further GSheet operations
            except gspread.exceptions.APIError as e_api_stmt_main:
                st.error(f"❌ Google Sheets API Error (Opening Spreadsheet): {e_api_stmt_main.args[0] if e_api_stmt_main.args else 'Unknown API error'}.") #
                gc_stmt = None #
            except Exception as e_setup_stmt:
                st.error(f"❌ เกิดข้อผิดพลาดในการเข้าถึง Spreadsheet: {type(e_setup_stmt).__name__} - {str(e_setup_stmt)[:200]}...") #
                gc_stmt = None #
            
            if sheets_ok_stmt and gc_stmt: # Proceed only if GSheet setup was okay
                previously_processed_successfully = False #
                try:
                    if WORKSHEET_UPLOAD_HISTORY in ws_stmt_dict and ws_stmt_dict[WORKSHEET_UPLOAD_HISTORY].row_count > 1: #
                        history_records_stmt = ws_stmt_dict[WORKSHEET_UPLOAD_HISTORY].get_all_records(numericise_ignore=['all']) #
                        for record_stmt in history_records_stmt:
                            try: record_file_size_stmt_val = int(float(str(record_stmt.get("FileSize","0")).replace(",",""))) #
                            except: record_file_size_stmt_val = 0
                            
                            if str(record_stmt.get("PortfolioID","")) == str(active_portfolio_id_for_stmt_import) and \
                               record_stmt.get("FileName","") == file_name_stmt and \
                               record_file_size_stmt_val == file_size_stmt and \
                               record_stmt.get("FileHash","") == file_hash_stmt and \
                               str(record_stmt.get("Status","")).startswith("Success"): #
                                previously_processed_successfully = True #
                                break
                except Exception as e_hist_read_stmt:
                    print(f"Warning: Could not read UploadHistory for duplicate file check: {e_hist_read_stmt}") #

                if previously_processed_successfully:
                    st.warning(f"⚠️ ไฟล์ '{file_name_stmt}' นี้ เคยถูกประมวลผลสำเร็จสำหรับพอร์ต '{active_portfolio_name_for_stmt_import}' ไปแล้ว จะไม่ดำเนินการใดๆ ซ้ำอีก") #
                    # Rerun is handled by the logic at the end.
                else:
                    import_batch_id_stmt = str(uuid.uuid4()) #
                    upload_timestamp_stmt = datetime.now().strftime("%Y-%m-%d %H:%M:%S") #
                    initial_log_ok_stmt = False #
                    try:
                        ws_stmt_dict[WORKSHEET_UPLOAD_HISTORY].append_row([ #
                            upload_timestamp_stmt, str(active_portfolio_id_for_stmt_import), str(active_portfolio_name_for_stmt_import), #
                            file_name_stmt, file_size_stmt, file_hash_stmt, #
                            "Processing", import_batch_id_stmt, "Attempting to process." #
                        ])
                        initial_log_ok_stmt = True #
                    except Exception as e_log_init_stmt:
                        st.error(f"ไม่สามารถบันทึก Log เริ่มต้นใน {WORKSHEET_UPLOAD_HISTORY}: {e_log_init_stmt}") #

                    if initial_log_ok_stmt:
                        st.markdown(f"--- \n**Import Batch ID: `{import_batch_id_stmt}`**") #
                        st.info(f"กำลังประมวลผลไฟล์: {file_name_stmt}") #

                        processing_errors_stmt = False #
                        final_status_stmt = "Failed_Unknown" #
                        processing_notes_stmt = [] #

                        try:
                            uploaded_file_statement.seek(0) # Ensure pointer is at the beginning
                            file_content_bytes_stmt = uploaded_file_statement.getvalue()  #
                            
                            with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {file_name_stmt}..."): #
                                extracted_stmt_data = extract_data_from_report_content_sec6(file_content_bytes_stmt)  #

                            if st.session_state.get("debug_statement_processing_v2", False): #
                                st.write("--- DEBUG: Extracted Statement Data ---") #
                                st.json({k: (v.to_dict() if isinstance(v, pd.DataFrame) else v) for k, v in extracted_stmt_data.items()}, expanded=False) #
                                st.write("--- END DEBUG ---") #

                            extraction_successful = extracted_stmt_data and \
                                                    (any(isinstance(df, pd.DataFrame) and not df.empty \
                                                         for name, df in extracted_stmt_data.items() if name in ['deals', 'orders', 'positions']) or \
                                                     extracted_stmt_data.get('balance_summary') or extracted_stmt_data.get('results_summary')) #
                            
                            if not extraction_successful:
                                st.warning("ไม่สามารถแยกข้อมูลที่มีความหมายจากไฟล์ได้ หรือไฟล์ไม่มีข้อมูล Transactional/Summary.") #
                                final_status_stmt = "Failed_Extraction" #
                                processing_notes_stmt.append("Failed to extract meaningful data.") #
                                processing_errors_stmt = True #
                            
                            if not processing_errors_stmt:
                                st.subheader("💾 กำลังบันทึกข้อมูลส่วนต่างๆไปยัง Google Sheets...") #
                                
                                deals_data = extracted_stmt_data.get('deals', pd.DataFrame()) #
                                ok_d_stmt, new_d_stmt, skip_d_stmt = save_deals_to_actual_trades_sec6(ws_stmt_dict.get(WORKSHEET_ACTUAL_TRADES), deals_data, active_portfolio_id_for_stmt_import, active_portfolio_name_for_stmt_import, file_name_stmt, import_batch_id_stmt) #
                                processing_notes_stmt.append(f"Deals:New={new_d_stmt},Skip={skip_d_stmt},OK={ok_d_stmt}") #
                                if ok_d_stmt: st.write(f"✔️ ({WORKSHEET_ACTUAL_TRADES}) Deals: เพิ่ม {new_d_stmt}, ข้าม {skip_d_stmt}.") #
                                else: st.error(f"❌ ({WORKSHEET_ACTUAL_TRADES}) Deals: ล้มเหลว"); processing_errors_stmt = True #

                                orders_data = extracted_stmt_data.get('orders', pd.DataFrame()) #
                                ok_o_stmt, new_o_stmt, skip_o_stmt = save_orders_to_gsheets_sec6(ws_stmt_dict.get(WORKSHEET_ACTUAL_ORDERS), orders_data, active_portfolio_id_for_stmt_import, active_portfolio_name_for_stmt_import, file_name_stmt, import_batch_id_stmt) #
                                processing_notes_stmt.append(f"Orders:New={new_o_stmt},Skip={skip_o_stmt},OK={ok_o_stmt}") #
                                if ok_o_stmt: st.write(f"✔️ ({WORKSHEET_ACTUAL_ORDERS}) Orders: เพิ่ม {new_o_stmt}, ข้าม {skip_o_stmt}.") #
                                else: st.error(f"❌ ({WORKSHEET_ACTUAL_ORDERS}) Orders: ล้มเหลว"); processing_errors_stmt = True #
                                
                                positions_data = extracted_stmt_data.get('positions', pd.DataFrame()) #
                                ok_p_stmt, new_p_stmt, skip_p_stmt = save_positions_to_gsheets_sec6(ws_stmt_dict.get(WORKSHEET_ACTUAL_POSITIONS), positions_data, active_portfolio_id_for_stmt_import, active_portfolio_name_for_stmt_import, file_name_stmt, import_batch_id_stmt) #
                                processing_notes_stmt.append(f"Positions:New={new_p_stmt},Skip={skip_p_stmt},OK={ok_p_stmt}") #
                                if ok_p_stmt: st.write(f"✔️ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: เพิ่ม {new_p_stmt}, ข้าม {skip_p_stmt}.") #
                                else: st.error(f"❌ ({WORKSHEET_ACTUAL_POSITIONS}) Positions: ล้มเหลว"); processing_errors_stmt = True #

                                bal_summary_data = extracted_stmt_data.get('balance_summary', {}) #
                                res_summary_data = extracted_stmt_data.get('results_summary', {}) #
                                summary_ok_stmt, summary_note_stmt = False, "no_data_to_save" #

                                if bal_summary_data or res_summary_data: # Only save if there's something to save
                                    summary_ok_stmt, summary_note_stmt = save_results_summary_to_gsheets_sec6( #
                                        ws_stmt_dict.get(WORKSHEET_STATEMENT_SUMMARIES), bal_summary_data, res_summary_data, #
                                        active_portfolio_id_for_stmt_import, active_portfolio_name_for_stmt_import, #
                                        file_name_stmt, import_batch_id_stmt #
                                    )
                                processing_notes_stmt.append(f"Summary:Status={summary_note_stmt},OK={summary_ok_stmt}") #
                                if summary_note_stmt == "saved_new": st.write(f"✔️ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary: บันทึกใหม่") #
                                elif summary_note_stmt == "skipped_duplicate_content": st.info(f"({WORKSHEET_STATEMENT_SUMMARIES}) Summary: ข้อมูลซ้ำ, ไม่บันทึกเพิ่ม") #
                                elif summary_note_stmt != "no_data_to_save": st.error(f"❌ ({WORKSHEET_STATEMENT_SUMMARIES}) Summary: ล้มเหลว ({summary_note_stmt})"); processing_errors_stmt = True #
                                
                                # ---- KEY UPDATE FOR BALANCE DISPLAY ----
                                if not processing_errors_stmt and 'equity' in bal_summary_data and bal_summary_data['equity'] is not None: #
                                    try:
                                        current_latest_equity = float(bal_summary_data['equity']) #
                                        st.session_state.latest_statement_equity = current_latest_equity #
                                        st.session_state.current_account_balance = current_latest_equity # อัปเดต balance ที่ใช้คำนวณ
                                        st.success(f"✔️ อัปเดต Balance สำหรับคำนวณจาก Statement Equity ล่าสุด: {current_latest_equity:,.2f} USD") #
                                        processing_notes_stmt.append(f"Updated_Session_Equity={current_latest_equity}") #
                                        _equity_updated_successfully_this_cycle = True # Mark that equity was updated
                                        # Clear cache for statement summaries so SEC 1 can pick up new data
                                        if hasattr(load_statement_summaries_from_gsheets, 'clear'):
                                            load_statement_summaries_from_gsheets.clear()
                                    except ValueError:
                                        st.warning("⚠️ ไม่สามารถแปลงค่า Equity จาก Statement เป็นตัวเลขเพื่ออัปเดต session state.") #
                                        processing_notes_stmt.append("Warning: Failed to convert Equity from Statement for session state.") #
                                elif not processing_errors_stmt: # No processing errors, but equity not found or not valid
                                    st.warning("⚠️ ไม่พบค่า 'Equity' ใน Statement ที่อัปโหลด หรือค่าไม่ถูกต้อง จะยังคงใช้ Balance ก่อนหน้า หรือ Initial Balance.") #
                                    processing_notes_stmt.append("Warning: 'Equity' not found/valid in Statement for session update.") #
                                # ---- END KEY UPDATE ----
                                
                                if not processing_errors_stmt:
                                    final_status_stmt = "Success" #
                                    st.balloons() #
                                    st.success(f"ประมวลผลและบันทึกข้อมูลจากไฟล์ '{file_name_stmt}' (Batch ID '{import_batch_id_stmt}') เสร็จสิ้นสมบูรณ์!") #
                                else:
                                    final_status_stmt = "Failed_PartialSave" #
                                    st.error(f"การประมวลผลไฟล์ '{file_name_stmt}' (Batch ID '{import_batch_id_stmt}') มีบางส่วนล้มเหลว โปรดตรวจสอบข้อความและ Log") #
                        
                        except UnicodeDecodeError as e_decode_stmt:
                            st.error(f"เกิดข้อผิดพลาดในการ Decode ไฟล์: {e_decode_stmt}. กรุณาตรวจสอบ Encoding (ควรเป็น UTF-8).") #
                            final_status_stmt = "Failed_UnicodeDecode"; processing_notes_stmt.append(f"UnicodeDecodeError: {e_decode_stmt}") #
                        except Exception as e_main_proc_stmt:
                            st.error(f"เกิดข้อผิดพลาดระหว่างประมวลผลหลัก: {type(e_main_proc_stmt).__name__} - {str(e_main_proc_stmt)[:200]}...") #
                            final_status_stmt = f"Failed_MainProcessing_{type(e_main_proc_stmt).__name__}"; processing_notes_stmt.append(f"MainError: {type(e_main_proc_stmt).__name__}") #

                        # Update UploadHistory with final status
                        try:
                            hist_rows_update_stmt = ws_stmt_dict[WORKSHEET_UPLOAD_HISTORY].get_all_values() #
                            row_idx_to_update_stmt = None #
                            for r_idx, r_val in reversed(list(enumerate(hist_rows_update_stmt))):
                                if len(r_val) > 7 and r_val[7] == import_batch_id_stmt: # Index 7 for ImportBatchID
                                    row_idx_to_update_stmt = r_idx + 1; break #
                            if row_idx_to_update_stmt:
                                notes_str_stmt = " | ".join(filter(None, processing_notes_stmt))[:49999] #
                                ws_stmt_dict[WORKSHEET_UPLOAD_HISTORY].batch_update([ #
                                    {'range': f'G{row_idx_to_update_stmt}', 'values': [[final_status_stmt]]}, #
                                    {'range': f'I{row_idx_to_update_stmt}', 'values': [[notes_str_stmt]]} #
                                ])
                                print(f"Info: Updated UploadHistory for ImportBatchID '{import_batch_id_stmt}' to '{final_status_stmt}'.") #
                        except Exception as e_update_hist_final_stmt:
                            print(f"Warning: Could not update final status in {WORKSHEET_UPLOAD_HISTORY} for batch {import_batch_id_stmt}: {e_update_hist_final_stmt}") #
            # else:
                # This 'else' (for GSheet setup fail or no active portfolio) will also fall through to the uploader reset.
                # Error messages would have been shown above.

    # This block executes after the `if uploaded_file_statement is not None:` block finishes,
    # OR if `uploaded_file_statement` was None initially.
    # The key is to reset the flag for the *next actual script run if a file is present again*.
    if not uploaded_file_statement and st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE]:
        st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE] = False


    # Always increment key and rerun if a file was present and processed (or attempted) in this cycle.
    # This ensures the file uploader widget is reset.
    if uploaded_file_statement is not None and st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE]:
        st.session_state.uploader_key_version += 1
        # Only rerun if the flag dictates (e.g., successful equity update, or general reset desire)
        # For the loop fix, a rerun is generally good to clear the uploader state.
        # The _trigger_rerun_after_upload_handling can be fine-tuned if needed.
        if _trigger_rerun_after_upload_handling:
            st.rerun()
        # If not rerunning, the uploader is still reset for the *next interaction* due to key change.

elif st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE]:
    # This case: no file is currently in uploaded_file_statement (it's None),
    # but we *did* process one in the previous state of this *same script run* before a non-explicit rerun.
    # This happens if we didn't call st.rerun() immediately after key increment.
    # Reset the flag, so if the user uploads *another* file without a full page reload, it gets processed.
    st.session_state[_UPLOAD_PROCESSED_IN_THIS_CYCLE] = False


st.markdown("---") # End of statement processing expander

# ===================== SEC 7: MAIN AREA - TRADE LOG VIEWER =======================
@st.cache_data(ttl=120) # Cache ผลลัพธ์ของฟังก์ชันนี้ (ซึ่งรวมการเรียงข้อมูลแล้ว) ไว้ 2 นาที
def load_planned_trades_from_gsheets_for_viewer():
    # เรียกใช้ฟังก์ชันกลางเพื่อโหลดข้อมูล PlannedTradeLogs (ซึ่งมี cache ของตัวเอง)
    df_logs_viewer = load_all_planned_trade_logs_from_gsheets() # load_all_planned_trade_logs_from_gsheets ควรเป็นเวอร์ชันที่ใช้ร่วมกัน
    
    if df_logs_viewer.empty:
        return pd.DataFrame()

    # การเรียงข้อมูลจะทำหลังจากโหลดข้อมูลจาก cache กลางแล้ว
    # ตรวจสอบว่าคอลัมน์ 'Timestamp' มีอยู่ และไม่เป็นค่าว่างทั้งหมดก่อนเรียง
    if 'Timestamp' in df_logs_viewer.columns and not df_logs_viewer['Timestamp'].isnull().all():
        # Ensure Timestamp is datetime before sorting
        if not pd.api.types.is_datetime64_any_dtype(df_logs_viewer['Timestamp']):
             df_logs_viewer['Timestamp'] = pd.to_datetime(df_logs_viewer['Timestamp'], errors='coerce')
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
            portfolio_filter_log = st.selectbox("Portfolio", portfolios_in_log, key="log_viewer_portfolio_filter_v1") # Added _v1 to key if needed
        
        with log_filter_cols[1]:
            modes_in_log = ["ทั้งหมด"]
            if "Mode" in df_show_log_viewer.columns:
                modes_in_log.extend(sorted(df_show_log_viewer["Mode"].dropna().unique().tolist()))
            mode_filter_log = st.selectbox("Mode", modes_in_log, key="log_viewer_mode_filter_v1")

        with log_filter_cols[2]:
            assets_in_log = ["ทั้งหมด"]
            if "Asset" in df_show_log_viewer.columns:
                assets_in_log.extend(sorted(df_show_log_viewer["Asset"].dropna().unique().tolist()))
            asset_filter_log = st.selectbox("Asset", assets_in_log, key="log_viewer_asset_filter_v1")

        with log_filter_cols[3]:
            date_filter_log = None
            if 'Timestamp' in df_show_log_viewer.columns and not df_show_log_viewer['Timestamp'].isnull().all():
                 # Ensure 'Timestamp' is datetime for min/max_value if they were to be used
                 # For st.date_input, just ensuring the column exists is often enough.
                 date_filter_log = st.date_input("ค้นหาวันที่ (Log)", value=None, key="log_viewer_date_filter_v1", help="เลือกวันที่เพื่อกรอง Log")


        # --- Apply Filters ---
        if portfolio_filter_log != "ทั้งหมด" and "PortfolioName" in df_show_log_viewer.columns: # Check column existence
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["PortfolioName"] == portfolio_filter_log]
        if mode_filter_log != "ทั้งหมด" and "Mode" in df_show_log_viewer.columns:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Mode"] == mode_filter_log]
        if asset_filter_log != "ทั้งหมด" and "Asset" in df_show_log_viewer.columns:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Asset"] == asset_filter_log]
        
        if date_filter_log and 'Timestamp' in df_show_log_viewer.columns:
            if not pd.api.types.is_datetime64_any_dtype(df_show_log_viewer['Timestamp']): # Ensure datetime
                df_show_log_viewer['Timestamp'] = pd.to_datetime(df_show_log_viewer['Timestamp'], errors='coerce')
            # Filter out NaT rows that might result from errors='coerce' before attempting .dt accessor
            df_show_log_viewer = df_show_log_viewer.dropna(subset=['Timestamp'])
            if not df_show_log_viewer.empty: # Check if still has data after dropna
                df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Timestamp"].dt.date == date_filter_log]
        
        st.markdown("---")
        st.markdown("**Log Details & Actions:**")
        
        cols_to_display_log_viewer = {
            "Timestamp": "Timestamp", "PortfolioName": "Portfolio", "Asset": "Asset",
            "Mode": "Mode", "Direction": "Direction", "Entry": "Entry", "SL": "SL", "TP": "TP",
            "Lot": "Lot", "Risk $": "Risk $" , "RR": "RR"
        }
        actual_cols_to_display_keys = [k for k in cols_to_display_log_viewer.keys() if k in df_show_log_viewer.columns]
        
        num_display_cols = len(actual_cols_to_display_keys)
        
        if not df_show_log_viewer.empty:
            header_cols = st.columns(num_display_cols + 1) 
            for i, col_key in enumerate(actual_cols_to_display_keys):
                header_cols[i].markdown(f"**{cols_to_display_log_viewer[col_key]}**")
            header_cols[num_display_cols].markdown(f"**Action**")

            for index_log, row_log in df_show_log_viewer.iterrows():
                row_display_cols = st.columns(num_display_cols + 1)
                for i, col_key in enumerate(actual_cols_to_display_keys):
                    val = row_log.get(col_key, "-") 
                    if pd.isna(val): val_display = "-"
                    elif isinstance(val, float):
                        if col_key in ['Entry', 'SL', 'TP']: val_display = f"{val:.5f}" if val != 0 else "0.00000"
                        elif col_key in ['Lot', 'Risk $', 'RR', 'Risk %']: val_display = f"{val:.2f}"
                        else: val_display = str(val)
                    elif isinstance(val, pd.Timestamp): val_display = val.strftime("%Y-%m-%d %H:%M")
                    else: val_display = str(val)
                    row_display_cols[i].write(val_display)

                log_id_for_key = row_log.get('LogID', index_log) 
                if row_display_cols[num_display_cols].button(f"📈 Plot", key=f"plot_log_sec7_{log_id_for_key}"): # Unique key
                    st.session_state['plot_data'] = row_log.to_dict()
                    st.success(f"เลือกข้อมูลเทรด '{row_log.get('Asset', '-')}' @ Entry '{row_log.get('Entry', '-')}' เตรียมพร้อมสำหรับ Plot บน Chart Visualizer!")
                    st.rerun() 
        else:
            st.info("ไม่พบข้อมูล Log ที่ตรงกับเงื่อนไขการค้นหา")
        
        if 'plot_data' in st.session_state and st.session_state['plot_data']:
            st.sidebar.success(f"ข้อมูลพร้อม Plot: {st.session_state['plot_data'].get('Asset')} @ {st.session_state['plot_data'].get('Entry')}")
            try:
                plot_data_str = str(st.session_state['plot_data'])
                plot_data_display = (plot_data_str[:297] + "...") if len(plot_data_str) > 300 else plot_data_str
                st.sidebar.json(plot_data_display, expanded=False) 
            except:
                st.sidebar.text("ไม่สามารถแสดง plot_data (อาจมีปัญหาการแปลง)")

