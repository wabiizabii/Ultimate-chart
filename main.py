# ===================== UltimateChart V2.X.X =======================
# Version: 2.X.X (จะอัปเดตตามเวอร์ชันที่คุณกำลังพัฒนา)
# Last Updated: 2025-06-05 (วันที่เริ่มการจัดเรียงใหม่)
# Description: Refactored for improved workflow and clarity.
#              Integrated TradingView Chart Visualizer.
# ==================================================================

# ============== SEC 1.0: INITIAL SETUP ============================

# --- SEC 1.1: Imports ---
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta # เพิ่ม timedelta
import gspread
import plotly.graph_objects as go # ยังคงไว้เผื่อมีการใช้ Plotly GO ในอนาคต
import plotly.express as px # ยังคงไว้เผื่อมีการใช้ Plotly Express
import io
import uuid # สำหรับ Unique ID
import hashlib # สำหรับ Hashing (ถ้ามีการใช้งาน เช่น password)
# import google.generativeai as genai # เอาออกถ้าไม่ได้ใช้ หรือใส่ไว้ถ้ามีแผนจะใช้

# --- SEC 1.2: Page Configuration ---
st.set_page_config(
    page_title="UltimateChart Dashboard",
    page_icon="📊",  # สามารถเปลี่ยน Icon ได้
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- SEC 1.3: Global Constants & Configuration ---
# Google Sheets Configuration
GOOGLE_SHEET_NAME = "TradeLog"  # ชื่อ Google Sheet หลัก
WORKSHEET_PORTFOLIOS = "Portfolios"
WORKSHEET_PLANNED_LOGS = "PlannedTradeLogs"
WORKSHEET_ACTUAL_TRADES = "ActualTrades"    # สำหรับ MT5 Deals/History
WORKSHEET_ACTUAL_ORDERS = "ActualOrders"    # สำหรับ MT5 Orders
WORKSHEET_ACTUAL_POSITIONS = "ActualPositions" # สำหรับ MT5 Positions
WORKSHEET_STATEMENT_SUMMARIES = "StatementSummaries" # สรุป Statement ที่อัปโหลด
WORKSHEET_UPLOAD_HISTORY = "UploadHistory"       # ประวัติการอัปโหลด Statement

# Default values for Trade Planner
DEFAULT_ACCOUNT_BALANCE = 10000.0
DEFAULT_RISK_PERCENT = 1.0
DEFAULT_ASSET = "XAUUSD"

# --- SEC 1.4: Session State Initialization ---
def initialize_session_state():
    """Initialize session state variables if they don't exist."""
    # Portfolio related
    if 'portfolios_df' not in st.session_state:
        st.session_state.portfolios_df = pd.DataFrame()
    if 'active_portfolio_name' not in st.session_state:
        st.session_state.active_portfolio_name = None
    if 'active_portfolio_data' not in st.session_state:
        st.session_state.active_portfolio_data = None # จะเก็บข้อมูล dict ของ portfolio ที่ active

    # Trade planning modes
    if 'current_trade_mode' not in st.session_state:
        st.session_state.current_trade_mode = "FIBO" # Default mode

    # FIBO Mode specific
    if 'asset_fibo_val_v2' not in st.session_state: # คง key เดิมไว้ก่อน
        st.session_state.asset_fibo_val_v2 = DEFAULT_ASSET
    if 'direction_fibo_val_v2' not in st.session_state:
        st.session_state.direction_fibo_val_v2 = "BUY"
    # ... (เพิ่ม session state อื่นๆ ที่จำเป็นสำหรับ FIBO ที่เคยมี)

    # CUSTOM Mode specific
    if 'asset_custom_val_v2' not in st.session_state: # คง key เดิมไว้ก่อน
        st.session_state.asset_custom_val_v2 = DEFAULT_ASSET
    if 'direction_custom_val_v2' not in st.session_state:
        st.session_state.direction_custom_val_v2 = "BUY"
    # ... (เพิ่ม session state อื่นๆ ที่จำเป็นสำหรับ CUSTOM ที่เคยมี)

    # For Statement Uploading
    if 'uploader_key' not in st.session_state: # สำหรับ reset uploader
        st.session_state.uploader_key = str(uuid.uuid4())
    if 'uploaded_statement_df' not in st.session_state:
        st.session_state.uploaded_statement_df = None
    if 'statement_summary' not in st.session_state:
        st.session_state.statement_summary = None
    if 'upload_successful' not in st.session_state:
        st.session_state.upload_successful = False


    # For Log Viewer and Chart Visualizer
    if 'planned_trades_df' not in st.session_state:
        st.session_state.planned_trades_df = pd.DataFrame()
    if 'plot_data' not in st.session_state: # ข้อมูลสำหรับ TradingView Chart
        st.session_state.plot_data = None

    # For AI Assistant (ถ้ามี)
    if 'ai_analysis_result' not in st.session_state:
        st.session_state.ai_analysis_result = None

    # General UI state
    if 'show_success_message' not in st.session_state: # ตัวอย่างการใช้ session state ทั่วไป
        st.session_state.show_success_message = False
    if 'error_message' not in st.session_state:
        st.session_state.error_message = ""

    # Scaling Manager related (จากโค้ดเดิม)
    if 'base_lot_scaling' not in st.session_state:
        st.session_state.base_lot_scaling = 0.01
    if 'balance_threshold_scaling' not in st.session_state:
        st.session_state.balance_threshold_scaling = 100.0
    if 'increment_lot_scaling' not in st.session_state:
        st.session_state.increment_lot_scaling = 0.01
    if 'max_lot_scaling' not in st.session_state:
        st.session_state.max_lot_scaling = 1.00
    if 'enable_scaling_notifications' not in st.session_state:
        st.session_state.enable_scaling_notifications = True
    if 'last_shown_lot_scaling' not in st.session_state:
        st.session_state.last_shown_lot_scaling = 0.0

# เรียกใช้ initialize_session_state ตอนเริ่มต้น
initialize_session_state()


# --- SEC 1.5: Google Sheets Connection ---
@st.cache_resource(ttl=timedelta(hours=1)) # Cache resource for 1 hour
def init_gspread_connection():
    """Initialize and return the gspread client."""
    try:
        creds = st.secrets["gcp_service_account"]
        gs = gspread.service_account_from_dict(creds)
        return gs
    except Exception as e:
        st.error(f"GSpread Connection Error: {e}")
        return None

@st.cache_data(ttl=timedelta(minutes=10)) # Cache data for 10 minutes
def get_worksheet(_gs_client, sheet_name, worksheet_name):
    """Get a specific worksheet from a Google Sheet."""
    if not _gs_client:
        st.warning("GSpread client not initialized. Cannot fetch worksheet.")
        return None
    try:
        spreadsheet = _gs_client.open(sheet_name)
        worksheet = spreadsheet.worksheet(worksheet_name)
        return worksheet
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"Spreadsheet '{sheet_name}' not found.")
        return None
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Worksheet '{worksheet_name}' not found in '{sheet_name}'.")
        return None
    except Exception as e:
        st.error(f"Error accessing worksheet '{worksheet_name}': {e}")
        return None

# Initialize gspread client globally for the session
gs_client = init_gspread_connection()

# ============== END OF SEC 1.0 ===================================

# ============== SEC 2.0: UTILITY FUNCTIONS =======================

# --- SEC 2.1: Google Sheets Data Handling ---
@st.cache_data(ttl=timedelta(minutes=5)) # Cache for 5 mins, adjust as needed
def get_worksheet_as_dataframe(_gs_client, sheet_name, worksheet_name, expected_headers=None):
    """
    Fetches a worksheet from Google Sheets and returns it as a Pandas DataFrame.
    If expected_headers are provided, it ensures the DataFrame has these columns.
    """
    if not _gs_client:
        st.warning("GSpread client not initialized. Cannot fetch dataframe.")
        return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()

    try:
        ws = get_worksheet(_gs_client, sheet_name, worksheet_name)
        if ws:
            data = ws.get_all_records() # Fetches data as a list of dicts
            df = pd.DataFrame(data)
            
            # Ensure all expected headers are present, fill with NA if not
            if expected_headers:
                for header in expected_headers:
                    if header not in df.columns:
                        df[header] = np.nan # Or use pd.NA for Pandas > 1.0
            return df
        else:
            st.warning(f"Could not retrieve worksheet '{worksheet_name}'. Returning empty DataFrame.")
            return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()
    except Exception as e:
        st.error(f"Error converting worksheet '{worksheet_name}' to DataFrame: {e}")
        return pd.DataFrame(columns=expected_headers) if expected_headers else pd.DataFrame()

def append_data_to_sheet(_gs_client, sheet_name, worksheet_name, data_to_append_df, required_headers=None):
    """
    Appends a DataFrame to a Google Sheet. Creates the worksheet with headers if it doesn't exist.
    Ensures all required_headers are present in data_to_append_df before appending.
    """
    if not _gs_client:
        st.error("GSpread client not initialized. Cannot append data.")
        return False
    if data_to_append_df.empty:
        st.info("Data to append is empty. Nothing to save.")
        return False

    try:
        spreadsheet = _gs_client.open(sheet_name)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            st.info(f"Worksheet '{worksheet_name}' not found. Creating it...")
            if required_headers:
                worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows="1", cols=str(len(required_headers)))
                worksheet.append_row(required_headers) # Add header row
            else: # Create with columns from dataframe if no required_headers
                worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows="1", cols=str(len(data_to_append_df.columns)))
                worksheet.append_row(list(data_to_append_df.columns))


        # Ensure all required headers exist in the DataFrame before appending
        if required_headers:
            missing_headers = [header for header in required_headers if header not in data_to_append_df.columns]
            if missing_headers:
                st.error(f"Data to append is missing required columns: {', '.join(missing_headers)}")
                return False
            # Reorder df columns to match required_headers for consistency, if needed
            df_to_append_ordered = data_to_append_df[required_headers].copy()
        else:
            df_to_append_ordered = data_to_append_df.copy()
            
        # Convert DataFrame to list of lists for appending (without header)
        # Handle NaT/NaN to be empty strings for gspread
        list_of_lists = df_to_append_ordered.astype(object).where(pd.notnull(df_to_append_ordered), "").values.tolist()
        
        if list_of_lists: # Check if there's data after conversion
            worksheet.append_rows(list_of_lists, value_input_option='USER_ENTERED')
            st.success(f"Data successfully appended to '{worksheet_name}'.")
            # Clear relevant cache after updating sheet
            get_worksheet_as_dataframe.clear_cache()
            return True
        else:
            st.info("No data rows to append after processing.")
            return False
            
    except Exception as e:
        st.error(f"Error appending data to '{worksheet_name}': {e}")
        return False

def update_entire_sheet(_gs_client, sheet_name, worksheet_name, data_df):
    """
    Updates an entire Google Sheet with data from a DataFrame.
    The first row in the sheet will be headers, followed by data.
    """
    if not _gs_client:
        st.error("GSpread client not initialized. Cannot update sheet.")
        return False

    try:
        spreadsheet = _gs_client.open(sheet_name)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            st.info(f"Worksheet '{worksheet_name}' not found. Creating it to update...")
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=str(data_df.shape[0]+1), cols=str(data_df.shape[1]))

        # Clear the existing sheet content (except headers, or all if writing new headers)
        worksheet.clear()
        
        # Prepare data for update: headers + data rows
        # Convert NaT/NaN to be empty strings for gspread
        header_list = list(data_df.columns)
        data_list = data_df.astype(object).where(pd.notnull(data_df), "").values.tolist()
        
        worksheet.update([header_list] + data_list, value_input_option='USER_ENTERED')
        st.success(f"Sheet '{worksheet_name}' successfully updated.")
        # Clear relevant cache
        get_worksheet_as_dataframe.clear_cache()
        return True
    except Exception as e:
        st.error(f"Error updating sheet '{worksheet_name}': {e}")
        return False

# --- SEC 2.2: General Data Utilities ---
def generate_unique_id(prefix="ID"):
    """Generates a unique ID string with a prefix."""
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}" # Example: LOG_A1B2C3D4

def get_next_log_id(df, id_column_name, prefix="LOG"):
    """
    Generates the next sequential Log ID based on existing IDs in a DataFrame.
    Assumes IDs are in format PREFIX_NUMBER (e.g., LOG_001).
    """
    if df.empty or id_column_name not in df.columns or df[id_column_name].isnull().all():
        return f"{prefix}_001"
    
    # Extract numbers from existing IDs, filter out non-numeric if any malformed
    existing_ids = df[id_column_name].dropna().astype(str)
    numeric_parts = existing_ids.str.extract(rf'^{prefix}_(\d+)$', expand=False).dropna().astype(int)
    
    if numeric_parts.empty:
        max_id_num = 0
    else:
        max_id_num = numeric_parts.max()
        
    return f"{prefix}_{max_id_num + 1:03d}"


# ============== END OF SEC 2.0 ===================================


# ============== SEC 3.0: CORE LOGIC FUNCTIONS (TRADE PLANNING) ====

# --- SEC 3.1: Asset Parameter Retrieval ---
def get_asset_parameters(asset_name, active_portfolio_data):
    """
    Retrieves parameters for a given asset from the active portfolio data.
    Returns a dictionary with parameters like PipValue, ContractSize, etc.
    Uses default values if asset or specific parameters are not found in portfolio.
    """
    default_params = {
        "XAUUSD": {"PipValue": 0.01, "ContractSize": 100, "Digits": 2, "MinLot": 0.01, "LotStep": 0.01}, # Example for Gold
        "EURUSD": {"PipValue": 0.0001, "ContractSize": 100000, "Digits": 5, "MinLot": 0.01, "LotStep": 0.01}, # Example for EURUSD
        # Add other common assets with their typical parameters
    }

    if active_portfolio_data and 'Assets' in active_portfolio_data:
        portfolio_assets = active_portfolio_data['Assets'] # Assuming 'Assets' is a list of dicts or dict of dicts
        
        # Normalize asset_name for lookup (e.g., remove "OANDA:")
        normalized_asset_name = asset_name.split(':')[-1].upper()

        asset_config = None
        if isinstance(portfolio_assets, list): # If Assets is a list of dictionaries
            for asset_item in portfolio_assets:
                if isinstance(asset_item, dict) and asset_item.get('Symbol', '').upper() == normalized_asset_name:
                    asset_config = asset_item
                    break
        elif isinstance(portfolio_assets, dict): # If Assets is a dictionary of dictionaries (keyed by asset name)
            asset_config = portfolio_assets.get(normalized_asset_name)

        if asset_config:
            # Ensure critical keys exist, falling back to defaults if necessary
            final_params = default_params.get(normalized_asset_name, {}).copy() # Start with defaults for the asset type
            final_params.update(asset_config) # Override with specifics from portfolio
            return final_params
        else: # Asset not found in portfolio, use generic default if available
            return default_params.get(normalized_asset_name, {
                "PipValue": 0.0001, "ContractSize": 100000, "Digits": 4, "MinLot": 0.01, "LotStep": 0.01 # Generic fallback
            })
    else: # No portfolio data or no 'Assets' key, use generic default
        normalized_asset_name = asset_name.split(':')[-1].upper()
        return default_params.get(normalized_asset_name, {
            "PipValue": 0.0001, "ContractSize": 100000, "Digits": 4, "MinLot": 0.01, "LotStep": 0.01 # Generic fallback
        })

# --- SEC 3.2: Risk and Lot Size Calculation ---
def calculate_lot_size(account_balance, risk_percentage, sl_pips, pip_value_per_lot, contract_size, min_lot=0.01, lot_step=0.01):
    """
    Calculates the appropriate lot size based on risk parameters.
    SL pips should be positive.
    """
    if account_balance <= 0 or risk_percentage <= 0 or sl_pips <= 0 or pip_value_per_lot <= 0 or contract_size <= 0:
        return 0.0

    risk_amount_per_trade = account_balance * (risk_percentage / 100.0)
    
    # Value per pip for 1 standard lot (using contract_size, but often pip_value_per_lot is already "value of 1 pip movement for 1 lot")
    # For forex, value_per_pip_one_lot = pip_value (e.g., 0.0001) * contract_size (e.g., 100000) * lot_size (which is 1 here)
    # However, brokers often provide pip value per standard lot directly. Let's assume pip_value_per_lot is this direct value.
    # If pip_value_per_lot is the price increment (e.g. 0.0001), then:
    # value_per_pip_one_standard_lot = pip_value_per_lot * contract_size
    # For simplicity, let's assume 'pip_value_per_lot' is the monetary value of 1 pip movement for 1 standard lot.
    # E.g., for EURUSD on a USD account, 1 pip move for 1 lot is $10.
    # This needs to be consistent with how PipValue is defined in get_asset_parameters.

    # Let's re-evaluate based on typical broker definitions:
    # Pip Value is often given as (Tick Size / Exchange Rate) * Lot Size for CFDs or (Tick Size * Lot Size) for futures
    # Or for Forex: (0.0001 / QuoteCurrencyToAccountCurrencyRate) * ContractSize
    # Given the complexity, it's often simpler if the `get_asset_parameters` provides a "MoneyValuePerPipPerLot" directly.
    # Assuming `pip_value_per_lot` *IS* the money risked per pip for 1 lot.
    # E.g., if XAUUSD 1 pip = $1 movement for 1 lot, then pip_value_per_lot = 1.
    
    # Simplified: risk_per_pip_for_one_lot can be derived from asset parameters
    # For XAUUSD (Gold), if 1 lot = 100 oz, and pip value = 0.01 (tick size), then 1 pip move for 1 lot = 0.01 * 100 = $1
    # For EURUSD, if 1 lot = 100,000 EUR, and pip value = 0.0001, then 1 pip move for 1 lot = 0.0001 * 100,000 = $10 (if account is USD and EURUSD ~ 1.0)
    # The `pip_value_per_lot` here should be this $ value.
    # The `get_asset_parameters` should provide `MoneyPerPipPerLot` for the asset.
    # Let's rename `pip_value_per_lot` in the function signature to `money_per_pip_per_lot` for clarity.

    # Re-defining based on input:
    # money_per_pip_per_lot = (asset_params['PipValue'] / asset_params['TickSizeForRateConversion']) * asset_params['ContractSize']
    # Let's assume for now `pip_value_per_lot` is passed in as the direct monetary value of one pip for one standard lot
    # e.g., for XAUUSD, it's $1 (if 1 tick = 0.01, 1 lot = 100 units, 0.01 * 100 = 1)
    # e.g., for EURUSD, it's $10 (if 1 tick = 0.0001, 1 lot = 100,000 units, 0.0001 * 100000 = 10)
    
    if sl_pips == 0: return 0.0 # Avoid division by zero
    calculated_lot = risk_amount_per_trade / (sl_pips * pip_value_per_lot) # pip_value_per_lot is the $ value of 1 pip for 1 lot

    # Adjust to lot step and min lot
    if calculated_lot < min_lot:
        return min_lot
    else:
        # Ensure lot is a multiple of lot_step
        adjusted_lot = round(calculated_lot / lot_step) * lot_step
        # It's possible rounding down made it less than min_lot
        if adjusted_lot < min_lot:
            adjusted_lot = min_lot 
            # Or, if strict about risk, one might not trade or warn the user
            # For now, we default to min_lot if calculated is too small after step adjustment
        return round(adjusted_lot, 2) # Assuming lot sizes are typically 2 decimal places

def calculate_risk_reward_values(entry_price, sl_price, tp_price, lot_size, direction, money_per_pip_per_lot, digits):
    """
    Calculates Risk amount, Reward amount, and Risk/Reward Ratio.
    money_per_pip_per_lot: The monetary value of 1 pip movement for 1 lot (e.g., $1 for XAUUSD, $10 for EURUSD).
    digits: Number of decimal places for the asset's price.
    """
    if lot_size <= 0 or money_per_pip_per_lot <= 0:
        return 0.0, 0.0, 0.0

    sl_pips = 0
    tp_pips = 0

    # Calculate SL pips
    if direction.upper() == "BUY":
        sl_pips = round((entry_price - sl_price) * (10**digits), 1) # Pips for XAUUSD often 1 decimal (e.g., 1900.5 -> 1900.0 = 5 pips)
        tp_pips = round((tp_price - entry_price) * (10**digits), 1)
    elif direction.upper() == "SELL":
        sl_pips = round((sl_price - entry_price) * (10**digits), 1)
        tp_pips = round((entry_price - tp_price) * (10**digits), 1)
    
    if sl_pips <= 0: # SL must be some distance away
        return 0.0, 0.0, 0.0

    risk_amount = sl_pips * lot_size * money_per_pip_per_lot
    reward_amount = tp_pips * lot_size * money_per_pip_per_lot
    
    rr_ratio = reward_amount / risk_amount if risk_amount > 0 else 0.0
    
    return round(risk_amount, 2), round(reward_amount, 2), round(rr_ratio, 2)


# --- SEC 3.3: FIBO Mode Trade Parameter Calculation ---
def calculate_fibo_trade_params(account_balance, risk_percentage, asset, direction, 
                                fib_start, fib_end, entry_level_percent, sl_level_percent, tp_level_percent, 
                                active_portfolio_data):
    """
    Calculates all trade parameters for FIBO mode.
    Returns a dictionary with all parameters (Lot, Entry, SL, TP, Risk$, Reward$, RR, etc.)
    """
    params = {}
    asset_params = get_asset_parameters(asset, active_portfolio_data)
    digits = asset_params.get('Digits', 2)
    money_value_per_pip_per_lot = asset_params.get('ContractSize', 100) * asset_params.get('PipValue', 0.01) # Simplified for now

    # Calculate Fibonacci levels
    fib_range = abs(fib_end - fib_start)
    
    # Determine actual price levels based on direction
    if direction.upper() == "BUY": # Expecting fib_start < fib_end for an uptrend to buy on retracement
        # For BUY: Fib levels are measured DOWN from fib_end (high) if fib_start is low
        # Or UP from fib_start (low) if fib_end is high
        # Assuming standard Fibo: fib_start = swing low, fib_end = swing high for BUY setup on retracement
        # Entry, SL, TP are percentages of the fib_range, applied from fib_start or fib_end
        # Example: Entry at 50% retracement from swing high (fib_end)
        # Here, entry_level_percent, sl_level_percent, tp_level_percent are direct Fibo % like 0.5, 0.618, -0.27
        # If fib_start is low and fib_end is high:
        base_for_entry_sl = fib_start if fib_start < fib_end else fib_end # Should be swing low
        top_for_tp_extension = fib_end if fib_start < fib_end else fib_start # Should be swing high

        params['Entry'] = round(base_for_entry_sl + (fib_range * entry_level_percent/100.0), digits) if fib_start < fib_end else round(base_for_entry_sl - (fib_range * entry_level_percent/100.0), digits)
        params['SL'] = round(base_for_entry_sl + (fib_range * sl_level_percent/100.0), digits) if fib_start < fib_end else round(base_for_entry_sl - (fib_range * sl_level_percent/100.0), digits)
        params['TP'] = round(top_for_tp_extension + (fib_range * abs(tp_level_percent)/100.0), digits) if fib_start < fib_end else round(top_for_tp_extension - (fib_range * abs(tp_level_percent)/100.0), digits)
        # This Fibo logic needs refinement based on precise definition of % levels.
        # A more standard way for BUY:
        # Entry = fib_end - (fib_range * entry_level_percent/100.0) # e.g. 50% retracement from high
        # SL    = fib_end - (fib_range * sl_level_percent/100.0)   # e.g. below 61.8% or below 100% (fib_start)
        # TP    = fib_end + (fib_range * tp_level_percent/100.0)   # e.g. -27% extension
        if fib_start < fib_end: # Uptrend, expect to buy on dip
            params['Entry'] = round(fib_end - (fib_range * entry_level_percent / 100.0), digits)
            params['SL'] = round(fib_end - (fib_range * sl_level_percent / 100.0), digits)
            # TP is an extension beyond fib_end
            params['TP'] = round(fib_end + (fib_range * tp_level_percent / 100.0), digits)
        else: # fib_start > fib_end -- this case for BUY usually means Fibo is drawn downwards, not typical for buying retracement
              # For simplicity, let's assume fib_start is always the beginning of the primary move, fib_end is the end.
              # So for BUY, fib_start < fib_end. For SELL, fib_start > fib_end.
            st.warning("FIBO BUY: fib_start should be less than fib_end for typical retracement. Calculations might be off.")
            # Fallback or error needed here. For now, proceed with assumption.
            params['Entry'] = round(fib_start - (fib_range * entry_level_percent / 100.0), digits) # This is if fib_start is high
            params['SL'] = round(fib_start - (fib_range * sl_level_percent / 100.0), digits)
            params['TP'] = round(fib_start + (fib_range * tp_level_percent / 100.0), digits)


    elif direction.upper() == "SELL": # Expecting fib_start > fib_end for a downtrend to sell on retracement
        # For SELL: Fib levels are measured UP from fib_end (low) if fib_start is high
        # Entry, SL, TP are percentages of the fib_range
        # Example: Entry at 50% retracement from swing low (fib_end)
        if fib_start > fib_end: # Downtrend, expect to sell on rally
            params['Entry'] = round(fib_end + (fib_range * entry_level_percent / 100.0), digits)
            params['SL'] = round(fib_end + (fib_range * sl_level_percent / 100.0), digits)
            # TP is an extension beyond fib_end
            params['TP'] = round(fib_end - (fib_range * tp_level_percent / 100.0), digits)
        else: # fib_start < fib_end -- this case for SELL is not typical.
            st.warning("FIBO SELL: fib_start should be greater than fib_end for typical retracement. Calculations might be off.")
            params['Entry'] = round(fib_start + (fib_range * entry_level_percent / 100.0), digits) # This is if fib_start is low
            params['SL'] = round(fib_start + (fib_range * sl_level_percent / 100.0), digits)
            params['TP'] = round(fib_start - (fib_range * tp_level_percent / 100.0), digits)
    else:
        st.error(f"Invalid direction: {direction}")
        return {}

    # Calculate SL pips (distance)
    sl_pips_distance = abs(params['Entry'] - params['SL']) * (10**digits)
    sl_pips_distance = round(sl_pips_distance, 1) # Often SL pips are to 1 decimal place

    if sl_pips_distance <= 0:
        st.error("SL Pips must be greater than 0. Adjust FIBO levels or start/end points.")
        params['Lot'] = 0.0
        params['Risk $'] = 0.0
        params['Reward $'] = 0.0
        params['RR'] = 0.0
        return params

    params['Lot'] = calculate_lot_size(account_balance, risk_percentage, sl_pips_distance,
                                       money_value_per_pip_per_lot, 
                                       asset_params.get('ContractSize',100000), 
                                       asset_params.get('MinLot',0.01), 
                                       asset_params.get('LotStep',0.01))

    risk_val, reward_val, rr_val = calculate_risk_reward_values(params['Entry'], params['SL'], params['TP'],
                                                                params['Lot'], direction,
                                                                money_value_per_pip_per_lot, digits)
    params['Risk $'] = risk_val
    params['Reward $'] = reward_val
    params['RR'] = rr_val
    params['SL Pips'] = sl_pips_distance
    params['TP Pips'] = round(abs(params['TP'] - params['Entry']) * (10**digits), 1)
    params['Risk %'] = risk_percentage
    params['Asset'] = asset
    params['Direction'] = direction
    
    return params

# ============== END OF SEC 3.0 (Ongoing) ========================

# ============== SEC 3.0: CORE LOGIC FUNCTIONS (TRADE PLANNING) (Continued) ====

# --- SEC 3.4: CUSTOM Mode Trade Parameter Calculation ---
def calculate_custom_trade_params(account_balance, risk_percentage, asset, direction, 
                                  entry_price, sl_price, tp_price, 
                                  active_portfolio_data, fixed_lot_size=None):
    """
    Calculates all trade parameters for CUSTOM mode.
    If fixed_lot_size is provided and > 0, it uses that lot size and calculates risk based on it.
    Otherwise, it calculates lot size based on risk_percentage.
    Returns a dictionary with all parameters (Lot, Risk$, Reward$, RR, etc.)
    """
    params = {}
    asset_params = get_asset_parameters(asset, active_portfolio_data)
    digits = asset_params.get('Digits', 2)
    # This is a critical value: Money value of 1 pip movement for 1 standard lot.
    # Example: For XAUUSD, if contract size is 100 and pip value (tick size) is 0.01, then 100 * 0.01 = $1 per pip per lot.
    # Example: For EURUSD, if contract size is 100000 and pip value (tick size) is 0.0001, then 100000 * 0.0001 = $10 per pip per lot.
    # This should ideally be directly available from asset_params or accurately derived.
    money_value_per_pip_per_lot = asset_params.get('MoneyValuePerPipPerLot', asset_params.get('ContractSize', 100) * asset_params.get('PipValue', 0.01))


    params['Entry'] = float(entry_price)
    params['SL'] = float(sl_price)
    params['TP'] = float(tp_price)
    params['Asset'] = asset
    params['Direction'] = direction

    # Calculate SL pips (distance)
    sl_pips_distance = 0
    if direction.upper() == "BUY":
        if params['Entry'] <= params['SL']: # Entry must be above SL for BUY
            st.error("CUSTOM BUY Error: Entry Price must be HIGHER than Stop Loss Price.")
            return {"error": "Entry Price must be HIGHER than Stop Loss Price for BUY."}
        sl_pips_distance = round((params['Entry'] - params['SL']) * (10**digits), 1)
    elif direction.upper() == "SELL":
        if params['Entry'] >= params['SL']: # Entry must be below SL for SELL
            st.error("CUSTOM SELL Error: Entry Price must be LOWER than Stop Loss Price.")
            return {"error": "Entry Price must be LOWER than Stop Loss Price for SELL."}
        sl_pips_distance = round((params['SL'] - params['Entry']) * (10**digits), 1)
    else:
        st.error(f"Invalid direction: {direction}")
        return {"error": f"Invalid direction: {direction}"}

    if sl_pips_distance <= 0:
        st.error("SL Pips (distance between Entry and SL) must be greater than 0.")
        params['Lot'] = 0.0
        params['Risk $'] = 0.0
        params['Reward $'] = 0.0
        params['RR'] = 0.0
        params['SL Pips'] = 0.0
        params['TP Pips'] = 0.0
        params['Risk %'] = 0.0
        if fixed_lot_size and fixed_lot_size > 0:
            params['Risk %'] = "N/A (Fixed Lot)"
        return params

    params['SL Pips'] = sl_pips_distance

    if fixed_lot_size and fixed_lot_size > 0:
        params['Lot'] = round(fixed_lot_size, 2) # Use the provided fixed lot size
        # Calculate risk based on this fixed lot size
        risk_amount = sl_pips_distance * params['Lot'] * money_value_per_pip_per_lot
        params['Risk $'] = round(risk_amount, 2)
        if account_balance > 0:
            params['Risk %'] = round((risk_amount / account_balance) * 100, 2)
        else:
            params['Risk %'] = "N/A" # Cannot calculate % risk if balance is zero
    else: # Calculate lot size based on risk percentage
        params['Lot'] = calculate_lot_size(account_balance, risk_percentage, sl_pips_distance,
                                           money_value_per_pip_per_lot,
                                           asset_params.get('ContractSize',100000),
                                           asset_params.get('MinLot',0.01),
                                           asset_params.get('LotStep',0.01))
        params['Risk %'] = risk_percentage


    risk_val, reward_val, rr_val = calculate_risk_reward_values(params['Entry'], params['SL'], params['TP'],
                                                                params['Lot'], direction,
                                                                money_value_per_pip_per_lot, digits)
    # If using fixed lot, risk_val from calculate_risk_reward_values will be the actual risk
    if not (fixed_lot_size and fixed_lot_size > 0) : # Only override Risk $ if not fixed lot
         params['Risk $'] = risk_val
    
    params['Reward $'] = reward_val
    params['RR'] = rr_val
    
    tp_pips_distance = 0
    if direction.upper() == "BUY" and params['TP'] > params['Entry']:
        tp_pips_distance = round((params['TP'] - params['Entry']) * (10**digits),1)
    elif direction.upper() == "SELL" and params['TP'] < params['Entry']:
        tp_pips_distance = round((params['Entry'] - params['TP']) * (10**digits),1)
    params['TP Pips'] = tp_pips_distance
    
    return params

# ============== END OF SEC 3.0 =====================================

# ============== SEC 4.0: SIDEBAR UI & LOGIC ========================
def display_sidebar(gs_client):
    """Renders the sidebar UI and handles its logic."""
    st.sidebar.header("UltimateChart Control Panel")
    st.sidebar.markdown("---")

    # --- SEC 4.1: Portfolio Selection and Management ---
    st.sidebar.subheader("📊 Portfolio Management")

    portfolios_df = get_worksheet_as_dataframe(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_PORTFOLIOS)
    st.session_state.portfolios_df = portfolios_df # Update session state

    if not portfolios_df.empty and 'PortfolioName' in portfolios_df.columns:
        portfolio_names = portfolios_df['PortfolioName'].tolist()
        
        # Determine the index of the currently active portfolio, if any
        try:
            active_portfolio_index = portfolio_names.index(st.session_state.active_portfolio_name) if st.session_state.active_portfolio_name in portfolio_names else 0
        except ValueError:
            active_portfolio_index = 0 # Default to first if name not found (e.g. after deletion)
            if portfolio_names: # If there are portfolios, set the first one as active by default if current one is invalid
                 st.session_state.active_portfolio_name = portfolio_names[0]
            else: # No portfolios exist
                 st.session_state.active_portfolio_name = None


        selected_portfolio_name = st.sidebar.selectbox(
            "Select Active Portfolio:",
            options=portfolio_names,
            index=active_portfolio_index,
            key="sb_select_portfolio"
        )

        if selected_portfolio_name != st.session_state.active_portfolio_name:
            st.session_state.active_portfolio_name = selected_portfolio_name
            st.rerun() # Rerun to update everything based on new portfolio

        if st.session_state.active_portfolio_name:
            active_data_row = portfolios_df[portfolios_df['PortfolioName'] == st.session_state.active_portfolio_name]
            if not active_data_row.empty:
                st.session_state.active_portfolio_data = active_data_row.iloc[0].to_dict()
                st.sidebar.success(f"Active: **{st.session_state.active_portfolio_name}**")
                
                # Display key portfolio details (example)
                # Actual Balance might come from StatementSummaries or be part of Portfolios sheet
                current_balance_display = st.session_state.active_portfolio_data.get('CurrentBalance', "N/A")
                if 'statement_summary' in st.session_state and st.session_state.statement_summary and \
                   st.session_state.statement_summary.get('Portfolio') == st.session_state.active_portfolio_name:
                    current_balance_display = st.session_state.statement_summary.get('Ending Balance', current_balance_display)

                st.sidebar.metric("Portfolio Balance", f"${current_balance_display:,.2f}" if isinstance(current_balance_display, (int,float)) else current_balance_display)
                
            else:
                st.session_state.active_portfolio_data = None
                st.sidebar.warning("Could not load data for the selected portfolio.")
        else:
            st.sidebar.warning("No portfolio selected or available.")
            st.session_state.active_portfolio_data = None

    else:
        st.sidebar.warning("No portfolios found or 'PortfolioName' column missing.")
        st.sidebar.info(f"Please create a portfolio in the '{WORKSHEET_PORTFOLIOS}' sheet.")
        st.session_state.active_portfolio_name = None
        st.session_state.active_portfolio_data = None

    # Option to create a new portfolio (simplified example)
    with st.sidebar.expander("Create New Portfolio", expanded=False):
        new_portfolio_name = st.text_input("New Portfolio Name", key="sb_new_portfolio_name")
        initial_balance = st.number_input("Initial Balance", min_value=0.0, value=10000.0, step=100.0, key="sb_initial_balance")
        # Add other fields as necessary (Broker, AccountID, Asset configurations etc.)
        # For Asset Configurations, it might be complex for UI here. Could be managed directly in GSheet or a more advanced UI later.
        # Example: st.text_area("Asset Config (JSON format)", key="sb_asset_config_json")

        if st.button("Create Portfolio", key="sb_create_portfolio_btn"):
            if new_portfolio_name and not portfolios_df[portfolios_df['PortfolioName'] == new_portfolio_name].empty:
                st.error(f"Portfolio '{new_portfolio_name}' already exists.")
            elif new_portfolio_name and initial_balance > 0 :
                # Basic structure for a new portfolio entry
                new_portfolio_data = {
                    "PortfolioID": [generate_unique_id("PORT")],
                    "PortfolioName": [new_portfolio_name],
                    "InitialBalance": [initial_balance],
                    "CurrentBalance": [initial_balance], # Initially same as initial
                    "Broker": [st.text_input("Broker Name (Optional)", key="sb_new_broker")], # Example additional field
                    "AccountID": [st.text_input("Account ID (Optional)", key="sb_new_accountid")], # Example
                    "DateCreated": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                    "Assets": [str([ # Example: Store default assets as JSON string or similar
                        {"Symbol": "XAUUSD", "PipValue": 0.01, "ContractSize": 100, "Digits": 2, "MinLot": 0.01, "LotStep": 0.01, "MoneyValuePerPipPerLot": 1.0},
                        {"Symbol": "EURUSD", "PipValue": 0.0001, "ContractSize": 100000, "Digits": 5, "MinLot": 0.01, "LotStep": 0.01, "MoneyValuePerPipPerLot": 10.0}
                    ])] # This needs to be parsed correctly in get_asset_parameters
                }
                new_portfolio_df = pd.DataFrame(new_portfolio_data)
                
                # Define expected headers for Portfolios sheet
                portfolio_headers = ["PortfolioID", "PortfolioName", "InitialBalance", "CurrentBalance", "Broker", "AccountID", "DateCreated", "Assets"]

                success = append_data_to_sheet(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_PORTFOLIOS, new_portfolio_df, required_headers=portfolio_headers)
                if success:
                    st.success(f"Portfolio '{new_portfolio_name}' created successfully!")
                    st.session_state.active_portfolio_name = new_portfolio_name # Set as active
                    # Clear cache for portfolios_df to fetch fresh data
                    get_worksheet_as_dataframe.clear_cache() # Ensure this matches the cached function
                    st.rerun()
                else:
                    st.error("Failed to create portfolio in Google Sheets.")
            else:
                st.warning("Please provide a valid portfolio name and initial balance.")

    st.sidebar.markdown("---")

    # --- SEC 4.2: Scaling Manager ---
    # (Adapted from original code's session state)
    st.sidebar.subheader("⚙️ Scaling Manager")
    st.session_state.base_lot_scaling = st.sidebar.number_input(
        "Base Lot", 
        min_value=0.01, 
        value=st.session_state.get('base_lot_scaling', 0.01), 
        step=0.01, 
        format="%.2f",
        key="sb_base_lot_scaling"
    )
    st.session_state.balance_threshold_scaling = st.sidebar.number_input(
        "Balance Threshold ($)", 
        min_value=0.0, 
        value=st.session_state.get('balance_threshold_scaling', 100.0), 
        step=10.0,
        key="sb_balance_thresh_scaling"
    )
    st.session_state.increment_lot_scaling = st.sidebar.number_input(
        "Increment Lot By", 
        min_value=0.01, 
        value=st.session_state.get('increment_lot_scaling', 0.01), 
        step=0.01, 
        format="%.2f",
        key="sb_increment_lot_scaling"
    )
    st.session_state.max_lot_scaling = st.sidebar.number_input(
        "Max Lot", 
        min_value=0.01, 
        value=st.session_state.get('max_lot_scaling', 1.00), 
        step=0.01, 
        format="%.2f",
        key="sb_max_lot_scaling"
    )
    st.session_state.enable_scaling_notifications = st.sidebar.checkbox(
        "Enable Scaling Notifications", 
        value=st.session_state.get('enable_scaling_notifications', True),
        key="sb_enable_scaling_notif"
    )
    
    # Placeholder for displaying calculated scaling lot - this logic would typically run when a trade is planned or an event occurs
    # For now, just showing the inputs. The actual calculation logic would be elsewhere.
    # current_account_balance_for_scaling = st.session_state.active_portfolio_data.get('CurrentBalance', 0.0) if st.session_state.active_portfolio_data else 0.0
    # if current_account_balance_for_scaling > st.session_state.balance_threshold_scaling:
    #    num_increments = int((current_account_balance_for_scaling - st.session_state.balance_threshold_scaling) / st.session_state.balance_threshold_scaling) # Example logic
    #    calculated_scaled_lot = st.session_state.base_lot_scaling + (num_increments * st.session_state.increment_lot_scaling)
    #    calculated_scaled_lot = min(calculated_scaled_lot, st.session_state.max_lot_scaling)
    #    st.sidebar.info(f"Calculated Scaled Lot: {calculated_scaled_lot:.2f}")
    # else:
    #    st.sidebar.info(f"Calculated Scaled Lot: {st.session_state.base_lot_scaling:.2f} (Below threshold)")


    st.sidebar.markdown("---")
    # Add other sidebar elements as needed (e.g., AI assistant toggle, global settings)

# ============== END OF SEC 4.0 =====================================

# ============== SEC 5.0: MAIN PAGE UI & LOGIC - STATEMENT MANAGEMENT ====

# --- SEC 5.1: Statement Parsing Functions ---
def parse_mt_statement_html(uploaded_file_content, portfolio_id):
    """
    Parses an MT4/MT5 HTML statement file.
    Extracts trades, orders, positions, and summary information.
    This function will need to be robust to handle variations in HTML structure.
    Returns a dictionary containing 'summary_data', 'deals_df', 'orders_df', 'positions_df'.
    """
    from bs4 import BeautifulSoup # Import here if not globally, or ensure it's at the top
    
    summary_data = {"PortfolioID": portfolio_id, "StatementFile": uploaded_file_content.name}
    deals = []
    # Placeholder for parsing logic. The actual implementation will be complex.
    # You'll need to identify tables for deals, orders, summary section, etc.
    
    try:
        soup = BeautifulSoup(uploaded_file_content, 'html.parser')

        # --- Attempt to find summary table (common in MT5/MT4 reports) ---
        # This is highly dependent on the HTML structure of your statements
        # Look for tables, then look for specific headers like 'Closed P/L:', 'Balance:', 'Deposit:', 'Withdrawal:'
        # Example simplified search for a summary table (needs to be made robust)
        summary_table = None
        # Try to find a table with 'Account:' or 'Login:' which often precedes summary
        account_info_tag = soup.find(lambda tag: tag.name == "td" and "Account:" in tag.text)
        if not account_info_tag: # Try 'Login:' for MT4 style
             account_info_tag = soup.find(lambda tag: tag.name == "td" and "Login:" in tag.text)

        if account_info_tag:
            # The summary table is often the parent table or a sibling/nephew table
            # This is a guess and needs verification with actual statement HTML
            potential_summary_table = account_info_tag.find_parent('table')
            if potential_summary_table:
                 summary_table = potential_summary_table
                 # More specific: try finding a table that has "Closed Trade P/L" or "Profit:"
                 specific_summary_tag = soup.find(lambda tag: tag.name == "td" and ("Closed Trade P/L:" in tag.text or "Profit:" in tag.text or "Total Net Profit" in tag.text))
                 if specific_summary_tag:
                     summary_table = specific_summary_tag.find_parent('table')


        if summary_table:
            rows = summary_table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) >= 2:
                    key = cols[0].text.strip().replace(':', '')
                    value = cols[1].text.strip()
                    # Standardize keys
                    if key == "Closed Trade P/L" or key == "Total Net Profit": summary_data["ClosedPL"] = float(value.replace(',', '').split()[0]) # Take first number if "USD" is present
                    elif key == "Deposit": summary_data["Deposits"] = float(value.replace(',', '').split()[0])
                    elif key == "Withdrawal": summary_data["Withdrawals"] = float(value.replace(',', '').split()[0])
                    elif key == "Balance": summary_data["EndingBalance"] = float(value.replace(',', '').split()[0])
                    elif key == "Account" or key == "Login": summary_data["StatementAccountID"] = value.split()[0] # Get ID part
                    # Add more fields as needed: Equity, Margin, Free Margin, Gross Profit, Gross Loss etc.
        else:
            st.warning("Could not automatically find a clear summary table in the statement. Some summary fields might be missing.")

        # --- Attempt to find deals/trades table ---
        # MT5 often has a table with headers like 'Order', 'Time', 'Type', 'Symbol', 'Volume', 'Price', 'S/L', 'T/P', 'Profit', 'Balance'
        # MT4 might be different ('Ticket', 'Open Time', 'Type', 'Size', 'Item', 'Price', 'S/L', 'T/P', 'Close Time', 'Price', 'Commission', 'Taxes', 'Swap', 'Profit')
        # This is a placeholder for robust parsing logic
        deals_table_header_candidates = ['Order', 'Time', 'Deal', 'Ticket', 'Open Time'] # Add more specific headers
        deals_table = None
        
        all_tables = soup.find_all('table')
        for table in all_tables:
            header_row = table.find('tr')
            if header_row:
                headers_in_table = [th.text.strip() for th in header_row.find_all(['th', 'td'])] # Some use <td> for headers
                if any(header_candidate in headers_in_table for header_candidate in deals_table_header_candidates) and "Profit" in headers_in_table:
                    # More checks: e.g., number of columns, presence of 'Symbol' or 'Item'
                    if "Symbol" in headers_in_table or "Item" in headers_in_table:
                        deals_table = table
                        break
        
        if deals_table:
            df_list = pd.read_html(io.StringIO(str(deals_table)), flavor='bs4') # Use io.StringIO
            if df_list:
                deals_df = df_list[0]
                # TODO: Clean and standardize columns for deals_df (e.g., 'Time' to datetime, numeric columns)
                # Rename columns to a standard format: e.g., 'Order'/'Ticket' -> 'TradeID', 'Symbol'/'Item' -> 'Asset'
                # This is highly statement-specific
                deals_df.columns = [col.replace(' ', '').replace('/', '') for col in deals_df.columns] # Basic cleaning
                
                # Example column renaming (very basic, needs specific logic)
                rename_map = {
                    'Ticket': 'BrokerTradeID', 'Order': 'BrokerTradeID', 'Deal': 'BrokerDealID',
                    'OpenTime': 'OpenTimestamp', 'Time': 'Timestamp', # 'Time' in MT5 deals can be exec time
                    'CloseTime': 'CloseTimestamp',
                    'Type': 'TradeType', # buy, sell, balance, credit
                    'Size': 'VolumeLots', 'Volume': 'VolumeLots',
                    'Item': 'Asset', 'Symbol': 'Asset',
                    'OpenPrice': 'Price', # MT4 open price
                                        # MT5 Price is execution price
                    # 'SL': 'SLPrice', 'TP': 'TPPrice', # These are often order SL/TP not execution SL/TP for deals
                    'Profit': 'NetProfit',
                    'Balance': 'BalanceAfterTrade',
                    'Comment': 'Comment'
                }
                deals_df.rename(columns=lambda c: rename_map.get(c, c), inplace=True)

                # Convert data types
                for col in ['VolumeLots', 'Price', 'SL', 'TP', 'NetProfit', 'BalanceAfterTrade', 'Commission', 'Swap']: # Add other numeric cols
                    if col in deals_df.columns:
                        deals_df[col] = pd.to_numeric(deals_df[col], errors='coerce')
                
                for col in ['Timestamp', 'OpenTimestamp', 'CloseTimestamp']: # Add other datetime cols
                    if col in deals_df.columns:
                        deals_df[col] = pd.to_datetime(deals_df[col], errors='coerce')
                
                # Add PortfolioID to each deal
                deals_df['PortfolioID'] = portfolio_id
                deals_df['StatementFile'] = uploaded_file_content.name

            else: deals_df = pd.DataFrame()
        else:
            st.warning("Could not find a clear deals/trades table.")
            deals_df = pd.DataFrame()

        # Fallback / Manual calculation if summary not fully parsed
        if not deals_df.empty and "ClosedPL" not in summary_data and "NetProfit" in deals_df.columns:
            # Filter for actual trades (not balance operations if they are mixed)
            trade_rows = deals_df[deals_df['TradeType'].str.lower().isin(['buy', 'sell', 'short', 'long']) & deals_df['NetProfit'].notna()]
            summary_data["ClosedPL"] = trade_rows["NetProfit"].sum()
        
        if "Deposits" not in summary_data and not deals_df.empty and "NetProfit" in deals_df.columns and "TradeType" in deals_df.columns:
            summary_data["Deposits"] = deals_df[deals_df['TradeType'].str.lower() == 'deposit']['NetProfit'].sum()

        if "Withdrawals" not in summary_data and not deals_df.empty and "NetProfit" in deals_df.columns and "TradeType" in deals_df.columns:
             # Withdrawals are often negative profit in statements if listed as deals
            summary_data["Withdrawals"] = abs(deals_df[deals_df['TradeType'].str.lower() == 'withdrawal']['NetProfit'].sum())


        # TODO: Parse orders and positions if needed, similar to deals_df
        orders_df = pd.DataFrame()
        positions_df = pd.DataFrame()
        
        return {"summary_data": summary_data, "deals_df": deals_df, "orders_df": orders_df, "positions_df": positions_df}

    except Exception as e:
        st.error(f"Error parsing statement: {e}")
        return {"summary_data": summary_data, "deals_df": pd.DataFrame(), "orders_df": pd.DataFrame(), "positions_df": pd.DataFrame()}


# --- SEC 5.2: Statement Upload UI and Processing Logic ---
def display_statement_management(gs_client, active_portfolio_data):
    """Displays UI for statement upload and processing, and summary."""
    st.header("📜 Statement Management")
    st.markdown("Upload your MT4/MT5 trading statement (HTML file) to analyze performance and update your records.")

    if not active_portfolio_data:
        st.warning("Please select or create an active portfolio in the sidebar to upload statements.")
        return

    portfolio_id = active_portfolio_data.get("PortfolioID")
    portfolio_name = active_portfolio_data.get("PortfolioName")

    # File Uploader
    # Use a unique key for the uploader based on portfolio to allow re-upload for different portfolios
    # Or use a general uploader_key from session_state that gets reset
    uploaded_file = st.file_uploader("Choose an HTML statement file", type=['html', 'htm'], key=st.session_state.uploader_key)

    if uploaded_file is not None:
        file_content_bytes = uploaded_file.getvalue() # Read file content as bytes
        
        # Store a hash of the file to prevent re-processing the exact same file for the same portfolio
        file_hash = hashlib.md5(file_content_bytes).hexdigest()
        
        # Check UploadHistory
        upload_history_df = get_worksheet_as_dataframe(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_UPLOAD_HISTORY)
        is_already_uploaded = False
        if not upload_history_df.empty and 'FileHash' in upload_history_df.columns and 'PortfolioID' in upload_history_df.columns:
            if not upload_history_df[(upload_history_df['FileHash'] == file_hash) & (upload_history_df['PortfolioID'] == portfolio_id)].empty:
                is_already_uploaded = True
                st.warning(f"This statement file ('{uploaded_file.name}') seems to have been uploaded already for portfolio '{portfolio_name}'. Processing anyway for this session, but no new records will be saved if it's an exact duplicate.")
                # To strictly prevent re-processing, you could return here or disable the "Process" button.

        st.info(f"File '{uploaded_file.name}' uploaded. Size: {len(file_content_bytes)} bytes.")

        if st.button(f"Process Statement for Portfolio: {portfolio_name}", key="proc_stmt_btn"):
            with st.spinner("Processing statement... This may take a moment."):
                parsed_data = parse_mt_statement_html(io.BytesIO(file_content_bytes), portfolio_id) # Pass BytesIO object
                
                summary_data = parsed_data.get("summary_data", {})
                deals_df = parsed_data.get("deals_df", pd.DataFrame())
                
                st.session_state.uploaded_statement_df = deals_df # For display
                st.session_state.statement_summary = summary_data # For display & potential use elsewhere

                if not deals_df.empty:
                    st.subheader("Extracted Trades/Deals")
                    st.dataframe(deals_df.head(), height=300)
                else:
                    st.warning("No trades/deals were extracted from the statement.")

                if summary_data:
                    st.subheader("Statement Summary")
                    # Format summary for display
                    summary_display = {k: (f"${v:,.2f}" if isinstance(v, (int, float)) else v) for k,v in summary_data.items()}
                    st.json(summary_display) # Or display as a table/metrics

                    # Save to Google Sheets (if not a duplicate that's already saved)
                    if not is_already_uploaded: # Only save if it's a new file for this portfolio
                        # 1. Save Statement Summary
                        summary_df_to_save = pd.DataFrame([summary_data])
                        summary_headers = ["PortfolioID", "StatementFile", "StatementAccountID", "ClosedPL", "Deposits", "Withdrawals", "EndingBalance", "UploadTimestamp"] # Add other headers
                        summary_df_to_save["UploadTimestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Ensure all headers are present before saving
                        for header in summary_headers:
                            if header not in summary_df_to_save.columns:
                                summary_df_to_save[header] = None # Add missing column with None
                        
                        append_data_to_sheet(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_STATEMENT_SUMMARIES, summary_df_to_save[summary_headers], required_headers=summary_headers)

                        # 2. Save Actual Trades/Deals (if any)
                        if not deals_df.empty:
                            # Define expected headers for ActualTrades sheet
                            actual_trades_headers = ['PortfolioID', 'StatementFile', 'BrokerTradeID', 'BrokerDealID', 'Timestamp', 'OpenTimestamp', 'CloseTimestamp', 
                                                     'Asset', 'TradeType', 'VolumeLots', 'Price', 'SLPrice', 'TPPrice', # SL/TP might be separate
                                                     'Commission', 'Swap', 'NetProfit', 'BalanceAfterTrade', 'Comment'] # Adjust as per your deals_df
                            
                            # Ensure deals_df has these columns before appending
                            deals_to_save = deals_df.copy()
                            for header in actual_trades_headers:
                                if header not in deals_to_save.columns:
                                    deals_to_save[header] = None # Add missing column with None
                            
                            append_data_to_sheet(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_ACTUAL_TRADES, deals_to_save[actual_trades_headers], required_headers=actual_trades_headers)

                        # 3. Update Upload History
                        upload_log = {
                            "UploadID": [generate_unique_id("UPL")],
                            "PortfolioID": [portfolio_id],
                            "PortfolioName": [portfolio_name],
                            "FileName": [uploaded_file.name],
                            "FileSize": [len(file_content_bytes)],
                            "FileHash": [file_hash],
                            "UploadTimestamp": [datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
                            "DealsExtracted": [len(deals_df)],
                            "SummaryExtracted": [bool(summary_data)]
                        }
                        upload_log_df = pd.DataFrame(upload_log)
                        upload_history_headers = list(upload_log.keys())
                        append_data_to_sheet(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_UPLOAD_HISTORY, upload_log_df, required_headers=upload_history_headers)
                        
                        st.success("Statement data processed and saved to Google Sheets.")
                        st.session_state.upload_successful = True

                        # Optionally, update CurrentBalance in Portfolios sheet
                        if 'EndingBalance' in summary_data and portfolio_id:
                            portfolios_df_current = get_worksheet_as_dataframe(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_PORTFOLIOS)
                            if not portfolios_df_current.empty and 'PortfolioID' in portfolios_df_current.columns:
                                portfolio_idx = portfolios_df_current.index[portfolios_df_current['PortfolioID'] == portfolio_id].tolist()
                                if portfolio_idx:
                                    portfolios_df_current.loc[portfolio_idx[0], 'CurrentBalance'] = summary_data['EndingBalance']
                                    portfolios_df_current.loc[portfolio_idx[0], 'LastStatementUpdate'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    update_entire_sheet(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_PORTFOLIOS, portfolios_df_current)
                                    st.info(f"Portfolio '{portfolio_name}' current balance updated to ${summary_data['EndingBalance']:,.2f}.")
                                    # Rerun to reflect updated balance in sidebar if needed
                                    st.rerun() 
                    else: # Already uploaded and saved previously
                        st.info("Statement data (based on file hash) has already been saved previously. Displaying data for this session.")

                else: # No summary or no deals
                    st.error("Could not extract sufficient data from the statement. Please check the file format or content.")
            
            # Reset uploader key to allow uploading another file
            st.session_state.uploader_key = str(uuid.uuid4())
            st.rerun() # Rerun to reset the file uploader widget state

    # Display last uploaded statement summary if available in session state
    elif st.session_state.get('upload_successful') and st.session_state.get('statement_summary'):
        st.subheader("Last Processed Statement Summary")
        summary_display = {k: (f"${v:,.2f}" if isinstance(v, (int, float)) else v) for k,v in st.session_state.statement_summary.items()}
        st.json(summary_display)
        if st.session_state.get('uploaded_statement_df') is not None and not st.session_state.get('uploaded_statement_df').empty:
            st.subheader("Last Extracted Trades/Deals")
            st.dataframe(st.session_state.uploaded_statement_df.head(), height=300)


# ============== END OF SEC 5.0 =======================================

# ============== SEC 6.0: MAIN PAGE UI & LOGIC - TRADE PLANNING INTERFACE ====

def display_trade_planning_interface(gs_client, active_portfolio_data):
    """Displays the trade planning UI (FIBO and CUSTOM modes)."""
    st.header("📝 Trade Planner")

    if not active_portfolio_data:
        st.warning("Please select or create an active portfolio in the sidebar to use the Trade Planner.")
        return

    # --- SEC 6.1: Mode Selection (FIBO/CUSTOM) ---
    # Using columns for a cleaner layout for mode selection and perhaps general inputs
    col_mode_select, col_balance_info = st.columns([1, 2])

    with col_mode_select:
        trade_mode_options = ["FIBO Retracement/Extension", "CUSTOM Entry/SL/TP"]
        # Map display names to internal keys if needed, e.g., "FIBO", "CUSTOM"
        selected_trade_mode_display = st.radio(
            "Select Trade Planning Mode:",
            options=trade_mode_options,
            horizontal=False, # Can be True for side-by-side radio buttons
            key="tp_trade_mode_radio"
        )
    
    # Determine internal mode key
    if selected_trade_mode_display == "FIBO Retracement/Extension":
        current_mode = "FIBO"
    else: # CUSTOM Entry/SL/TP
        current_mode = "CUSTOM"
    
    st.session_state.current_trade_mode = current_mode # Store for other parts if needed

    # --- Get Account Balance for Calculations ---
    # Priority: 1. Statement Ending Balance, 2. Portfolio CurrentBalance, 3. Default
    account_balance_for_calc = DEFAULT_ACCOUNT_BALANCE # Fallback
    balance_source_message = f"Default: ${DEFAULT_ACCOUNT_BALANCE:,.2f}"

    if st.session_state.get('statement_summary') and \
       st.session_state.statement_summary.get('PortfolioID') == active_portfolio_data.get('PortfolioID') and \
       isinstance(st.session_state.statement_summary.get('EndingBalance'), (int, float)):
        account_balance_for_calc = st.session_state.statement_summary['EndingBalance']
        balance_source_message = f"Last Statement: ${account_balance_for_calc:,.2f}"
    elif active_portfolio_data.get('CurrentBalance') and isinstance(active_portfolio_data.get('CurrentBalance'), (int, float)):
        account_balance_for_calc = active_portfolio_data['CurrentBalance']
        balance_source_message = f"Portfolio: ${account_balance_for_calc:,.2f}"

    with col_balance_info:
        st.info(f"Using Account Balance for calculation: **{balance_source_message}** (Portfolio: {active_portfolio_data.get('PortfolioName', 'N/A')})")
        override_balance = st.checkbox("Manually override balance for this plan?", key="tp_override_balance_cb")
        if override_balance:
            account_balance_for_calc = st.number_input(
                "Manual Account Balance ($):",
                min_value=0.0,
                value=account_balance_for_calc,
                step=100.0,
                key="tp_manual_balance_input",
                help="This balance will be used for the current plan calculation only."
            )

    st.markdown("---")

    # --- Shared Inputs (Asset, Direction, Risk %) ---
    # These are common to both FIBO and CUSTOM modes
    # Use a form for each mode to group inputs and submission
    
    # Get available assets (e.g., from portfolio config or a predefined list)
    # For now, using a simple list, but ideally this comes from active_portfolio_data['Assets']
    default_assets = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "BTCUSD"] # Add more
    available_assets = default_assets
    if active_portfolio_data and 'Assets' in active_portfolio_data:
        try:
            # Assuming 'Assets' is a stringified list of dicts in portfolio data
            assets_config_str = active_portfolio_data['Assets']
            if isinstance(assets_config_str, str):
                import ast # Or json if it's strictly JSON
                parsed_assets_list = ast.literal_eval(assets_config_str)
                if isinstance(parsed_assets_list, list):
                    available_assets = [asset_dict.get('Symbol', '').upper() for asset_dict in parsed_assets_list if asset_dict.get('Symbol')]
                    if not available_assets: available_assets = default_assets # Fallback if parsing fails or empty
            elif isinstance(assets_config_str, list): # If it's already a list
                 available_assets = [asset_dict.get('Symbol', '').upper() for asset_dict in assets_config_str if asset_dict.get('Symbol')]
                 if not available_assets: available_assets = default_assets
        except Exception as e:
            st.error(f"Could not parse asset list from portfolio: {e}. Using default assets.")
            available_assets = default_assets


    # Store calculation results in session state to persist them across reruns if form is resubmitted
    if 'trade_plan_results' not in st.session_state:
        st.session_state.trade_plan_results = {}

    # --- SEC 6.2: FIBO Mode Interface ---
    if current_mode == "FIBO":
        st.subheader("📈 FIBO Retracement/Extension Planner")
        with st.form(key="fibo_plan_form"):
            fibo_cols1, fibo_cols2 = st.columns(2)
            with fibo_cols1:
                asset_fibo = st.selectbox("Asset:", available_assets, key="asset_fibo_val_v2", index=available_assets.index(st.session_state.get("asset_fibo_val_v2", available_assets[0])) if st.session_state.get("asset_fibo_val_v2", available_assets[0]) in available_assets else 0)
                direction_fibo = st.selectbox("Direction:", ["BUY", "SELL"], key="direction_fibo_val_v2", index=["BUY", "SELL"].index(st.session_state.get("direction_fibo_val_v2", "BUY")))
                risk_percent_fibo = st.number_input("Risk per Trade (%):", min_value=0.1, max_value=100.0, value=st.session_state.get("risk_percent_fibo", DEFAULT_RISK_PERCENT), step=0.1, format="%.1f", key="risk_fibo_input")
            
            with fibo_cols2:
                fib_start_price = st.number_input("Fibo Start Price:", step=0.00001, format="%.5f", key="fibo_start_price_input", value=st.session_state.get("fibo_start_price_input", 0.0))
                fib_end_price = st.number_input("Fibo End Price:", step=0.00001, format="%.5f", key="fibo_end_price_input", value=st.session_state.get("fibo_end_price_input", 0.0))

            st.markdown("Define Entry, SL, TP as Fibo Levels (% of the Fibo Range):")
            fibo_levels_cols = st.columns(3)
            with fibo_levels_cols[0]:
                entry_level_percent = st.number_input("Entry Level (%)", help="e.g., 50 for 50% retracement, 0 for Fibo End Price", value=st.session_state.get("fibo_entry_level", 50.0), key="fibo_entry_level")
            with fibo_levels_cols[1]:
                sl_level_percent = st.number_input("SL Level (%)", help="e.g., 0 for Fibo Start Price, or 110 for 10% beyond start", value=st.session_state.get("fibo_sl_level", 0.0), key="fibo_sl_level") # Or 100 for fib_start
            with fibo_levels_cols[2]:
                tp_level_percent = st.number_input("TP Level (Extension %)", help="e.g., 27 for -27% Fibo Extension (from Fibo End), or -61.8 for -61.8%", value=st.session_state.get("fibo_tp_level", 27.0), key="fibo_tp_level") # Often -27, -61.8

            submit_fibo_button = st.form_submit_button(label="Calculate FIBO Plan")

            if submit_fibo_button:
                if fib_start_price == 0.0 or fib_end_price == 0.0 or fib_start_price == fib_end_price:
                    st.error("Fibo Start and End prices must be different and non-zero.")
                else:
                    st.session_state.trade_plan_results = calculate_fibo_trade_params(
                        account_balance=account_balance_for_calc,
                        risk_percentage=risk_percent_fibo,
                        asset=asset_fibo,
                        direction=direction_fibo,
                        fib_start=fib_start_price,
                        fib_end=fib_end_price,
                        entry_level_percent=entry_level_percent,
                        sl_level_percent=sl_level_percent,
                        tp_level_percent=tp_level_percent, # This is extension beyond fib_end
                        active_portfolio_data=active_portfolio_data
                    )
                    # Store inputs for pre-filling form on rerun
                    st.session_state.asset_fibo_val_v2 = asset_fibo
                    st.session_state.direction_fibo_val_v2 = direction_fibo
                    st.session_state.risk_percent_fibo = risk_percent_fibo
                    st.session_state.fibo_start_price_input = fib_start_price
                    st.session_state.fibo_end_price_input = fib_end_price
                    st.session_state.fibo_entry_level = entry_level_percent
                    st.session_state.fibo_sl_level = sl_level_percent
                    st.session_state.fibo_tp_level = tp_level_percent


    # --- SEC 6.3: CUSTOM Mode Interface ---
    elif current_mode == "CUSTOM":
        st.subheader("🔧 CUSTOM Entry/SL/TP Planner")
        with st.form(key="custom_plan_form"):
            custom_cols1, custom_cols2 = st.columns(2)
            with custom_cols1:
                asset_custom = st.selectbox("Asset:", available_assets, key="asset_custom_val_v2", index=available_assets.index(st.session_state.get("asset_custom_val_v2", available_assets[0])) if st.session_state.get("asset_custom_val_v2", available_assets[0]) in available_assets else 0)
                direction_custom = st.selectbox("Direction:", ["BUY", "SELL"], key="direction_custom_val_v2", index=["BUY", "SELL"].index(st.session_state.get("direction_custom_val_v2", "BUY")))
                
                use_fixed_lot = st.checkbox("Use Fixed Lot Size?", key="custom_use_fixed_lot_cb", value=st.session_state.get("custom_use_fixed_lot_cb", False))
                fixed_lot_input = 0.0
                if use_fixed_lot:
                    fixed_lot_input = st.number_input("Fixed Lot Size:", min_value=0.01, value=st.session_state.get("custom_fixed_lot_input", 0.01), step=0.01, format="%.2f", key="custom_fixed_lot_input")
                    risk_percent_custom = 0.0 # Not used if fixed lot
                else:
                    risk_percent_custom = st.number_input("Risk per Trade (%):", min_value=0.1, max_value=100.0, value=st.session_state.get("risk_percent_custom", DEFAULT_RISK_PERCENT), step=0.1, format="%.1f", key="risk_custom_input")

            with custom_cols2:
                entry_price_custom = st.number_input("Entry Price:", step=0.00001, format="%.5f", key="entry_price_custom_input", value=st.session_state.get("entry_price_custom_input", 0.0))
                sl_price_custom = st.number_input("Stop Loss Price:", step=0.00001, format="%.5f", key="sl_price_custom_input", value=st.session_state.get("sl_price_custom_input", 0.0))
                tp_price_custom = st.number_input("Take Profit Price:", step=0.00001, format="%.5f", key="tp_price_custom_input", value=st.session_state.get("tp_price_custom_input", 0.0))

            submit_custom_button = st.form_submit_button(label="Calculate CUSTOM Plan")

            if submit_custom_button:
                if entry_price_custom == 0 or sl_price_custom == 0 or tp_price_custom == 0:
                     st.error("Entry, SL, and TP prices must be non-zero.")
                else:
                    st.session_state.trade_plan_results = calculate_custom_trade_params(
                        account_balance=account_balance_for_calc,
                        risk_percentage=risk_percent_custom if not use_fixed_lot else 0.0,
                        asset=asset_custom,
                        direction=direction_custom,
                        entry_price=entry_price_custom,
                        sl_price=sl_price_custom,
                        tp_price=tp_price_custom,
                        active_portfolio_data=active_portfolio_data,
                        fixed_lot_size=fixed_lot_input if use_fixed_lot else None
                    )
                    # Store inputs for pre-filling
                    st.session_state.asset_custom_val_v2 = asset_custom
                    st.session_state.direction_custom_val_v2 = direction_custom
                    st.session_state.custom_use_fixed_lot_cb = use_fixed_lot
                    st.session_state.custom_fixed_lot_input = fixed_lot_input
                    st.session_state.risk_percent_custom = risk_percent_custom
                    st.session_state.entry_price_custom_input = entry_price_custom
                    st.session_state.sl_price_custom_input = sl_price_custom
                    st.session_state.tp_price_custom_input = tp_price_custom
    
    # --- SEC 6.4: Display Calculation Results & Save Plan ---
    if st.session_state.trade_plan_results:
        results = st.session_state.trade_plan_results
        if "error" in results:
            st.error(f"Calculation Error: {results['error']}")
        else:
            st.subheader("📊 Calculated Trade Plan Parameters")
            res_cols = st.columns(4)
            # Ensure these keys match what your calculation functions return
            res_cols[0].metric("Lot Size", f"{results.get('Lot', 0.0):.2f}")
            res_cols[1].metric("Risk $", f"${results.get('Risk $', 0.0):,.2f}")
            res_cols[2].metric("Reward $", f"${results.get('Reward $', 0.0):,.2f}")
            res_cols[3].metric("RR Ratio", f"{results.get('RR', 0.0):.2f}:1")
            
            st.markdown(f"""
            - **Asset:** {results.get('Asset', 'N/A')}
            - **Direction:** {results.get('Direction', 'N/A')}
            - **Entry Price:** {results.get('Entry', 0.0):.5f}
            - **Stop Loss:** {results.get('SL', 0.0):.5f} ({results.get('SL Pips', 0.0)} pips)
            - **Take Profit:** {results.get('TP', 0.0):.5f} ({results.get('TP Pips', 0.0)} pips)
            - **Account Risk %:** {results.get('Risk %', 0.0):.2f}% 
            """)

            # Add notes/strategy input
            trade_notes = st.text_area("Trade Notes/Strategy:", key="tp_trade_notes", value=st.session_state.get("tp_trade_notes", ""))
            st.session_state.tp_trade_notes = trade_notes # Save notes to session_state immediately

            if st.button("💾 Save Trade Plan", key="save_plan_btn"):
                log_id = get_next_log_id(get_worksheet_as_dataframe(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_PLANNED_LOGS), "LogID", "PLAN")
                
                plan_data = {
                    "LogID": log_id,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "PortfolioID": active_portfolio_data.get('PortfolioID'),
                    "PortfolioName": active_portfolio_data.get('PortfolioName'),
                    "PlanningMode": current_mode,
                    "Asset": results.get('Asset'),
                    "Direction": results.get('Direction'),
                    "EntryPrice": results.get('Entry'),
                    "StopLossPrice": results.get('SL'),
                    "TakeProfitPrice": results.get('TP'),
                    "LotSize": results.get('Lot'),
                    "RiskAmount": results.get('Risk $'),
                    "RewardAmount": results.get('Reward $'),
                    "RiskRewardRatio": results.get('RR'),
                    "SL_Pips": results.get('SL Pips'),
                    "TP_Pips": results.get('TP Pips'),
                    "AccountRiskPercent": results.get('Risk %'),
                    "AccountBalanceUsed": account_balance_for_calc, # Balance used for this plan
                    "Status": "Planned", # Initial status
                    "Notes": trade_notes,
                    # Add Fibo specific inputs if mode is FIBO
                    "Fibo_StartPrice": fib_start_price if current_mode == "FIBO" else None,
                    "Fibo_EndPrice": fib_end_price if current_mode == "FIBO" else None,
                    "Fibo_EntryPercent": entry_level_percent if current_mode == "FIBO" else None,
                    "Fibo_SLPercent": sl_level_percent if current_mode == "FIBO" else None,
                    "Fibo_TPPercent": tp_level_percent if current_mode == "FIBO" else None,
                }
                plan_df = pd.DataFrame([plan_data])
                
                # Define headers for PlannedTradeLogs sheet
                planned_log_headers = list(plan_data.keys()) # Dynamically get headers

                success = append_data_to_sheet(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_PLANNED_LOGS, plan_df, required_headers=planned_log_headers)
                if success:
                    st.success(f"Trade plan '{log_id}' saved successfully!")
                    st.session_state.trade_plan_results = {} # Clear results after saving
                    st.session_state.tp_trade_notes = "" # Clear notes
                    st.rerun()
                else:
                    st.error("Failed to save trade plan.")
# ============== END OF SEC 6.0 =======================================

# ============== SEC 7.0: MAIN PAGE UI & LOGIC - LOG VIEWER ================

def display_log_viewer(gs_client, active_portfolio_data):
    """Displays planned trade logs and allows plotting them."""
    st.header("📓 Trade Log Viewer (Planned Trades)")

    if not active_portfolio_data:
        st.warning("Please select an active portfolio in the sidebar to view its trade logs.")
        return

    portfolio_id = active_portfolio_data.get("PortfolioID")

    # --- SEC 7.1: Fetch and Filter Logs ---
    # Define expected headers for PlannedTradeLogs to ensure DataFrame consistency
    # These should match the keys in plan_data from display_trade_planning_interface
    expected_log_headers = [
        "LogID", "Timestamp", "PortfolioID", "PortfolioName", "PlanningMode", "Asset",
        "Direction", "EntryPrice", "StopLossPrice", "TakeProfitPrice", "LotSize",
        "RiskAmount", "RewardAmount", "RiskRewardRatio", "SL_Pips", "TP_Pips",
        "AccountRiskPercent", "AccountBalanceUsed", "Status", "Notes",
        "Fibo_StartPrice", "Fibo_EndPrice", "Fibo_EntryPercent", "Fibo_SLPercent", "Fibo_TPPercent"
    ] # Add any other headers you have in your sheet

    all_logs_df = get_worksheet_as_dataframe(gs_client, GOOGLE_SHEET_NAME, WORKSHEET_PLANNED_LOGS, expected_headers=expected_log_headers)

    if all_logs_df.empty:
        st.info(f"No planned trades found for any portfolio in '{WORKSHEET_PLANNED_LOGS}'.")
        return

    # Filter logs for the active portfolio
    if 'PortfolioID' in all_logs_df.columns:
        portfolio_logs_df = all_logs_df[all_logs_df['PortfolioID'] == portfolio_id].copy()
    else:
        st.warning(f"'PortfolioID' column not found in '{WORKSHEET_PLANNED_LOGS}'. Displaying all logs.")
        portfolio_logs_df = all_logs_df.copy()


    if portfolio_logs_df.empty:
        st.info(f"No planned trades found for the active portfolio: {active_portfolio_data.get('PortfolioName', 'N/A')}")
        # Optionally show all logs if user wants
        # if st.checkbox("Show logs for all portfolios?"):
        #     portfolio_logs_df = all_logs_df.copy()
        # else:
        return

    # Convert relevant columns to numeric/datetime if they aren't already (gspread might return strings)
    for col in ['EntryPrice', 'StopLossPrice', 'TakeProfitPrice', 'LotSize', 'RiskAmount', 'RewardAmount', 'RiskRewardRatio', 'SL_Pips', 'TP_Pips', 'AccountRiskPercent', 'AccountBalanceUsed']:
        if col in portfolio_logs_df.columns:
            portfolio_logs_df[col] = pd.to_numeric(portfolio_logs_df[col], errors='coerce')
    if 'Timestamp' in portfolio_logs_df.columns:
        portfolio_logs_df['Timestamp'] = pd.to_datetime(portfolio_logs_df['Timestamp'], errors='coerce')

    portfolio_logs_df.sort_values(by="Timestamp", ascending=False, inplace=True)

    # --- Filtering Options ---
    st.markdown("---")
    st.subheader("Filter Logs")
    filter_cols = st.columns([1, 1, 1, 1])

    # Filter by Asset
    unique_assets = portfolio_logs_df['Asset'].dropna().unique().tolist()
    selected_asset_filter = filter_cols[0].multiselect("Filter by Asset:", unique_assets, default=[], key="log_asset_filter")

    # Filter by Status
    unique_statuses = portfolio_logs_df['Status'].dropna().unique().tolist()
    selected_status_filter = filter_cols[1].multiselect("Filter by Status:", unique_statuses, default=[], key="log_status_filter")
    
    # Filter by Date Range
    min_date = portfolio_logs_df['Timestamp'].min().date() if not portfolio_logs_df.empty and pd.notna(portfolio_logs_df['Timestamp'].min()) else date.today() - timedelta(days=30)
    max_date = portfolio_logs_df['Timestamp'].max().date() if not portfolio_logs_df.empty and pd.notna(portfolio_logs_df['Timestamp'].max()) else date.today()
    
    start_date_filter = filter_cols[2].date_input("Start Date:", value=min_date, min_value=min_date, max_value=max_date, key="log_start_date")
    end_date_filter = filter_cols[3].date_input("End Date:", value=max_date, min_value=min_date, max_value=max_date, key="log_end_date")

    # Apply filters
    filtered_logs_df = portfolio_logs_df.copy()
    if selected_asset_filter:
        filtered_logs_df = filtered_logs_df[filtered_logs_df['Asset'].isin(selected_asset_filter)]
    if selected_status_filter:
        filtered_logs_df = filtered_logs_df[filtered_logs_df['Status'].isin(selected_status_filter)]
    if start_date_filter and end_date_filter:
         # Ensure Timestamp column is datetime for comparison
        if pd.api.types.is_datetime64_any_dtype(filtered_logs_df['Timestamp']):
            filtered_logs_df = filtered_logs_df[
                (filtered_logs_df['Timestamp'].dt.date >= start_date_filter) &
                (filtered_logs_df['Timestamp'].dt.date <= end_date_filter)
            ]
        else:
            st.warning("Timestamp column is not in a proper datetime format for date filtering.")


    # --- SEC 7.2: Display Logs ---
    st.markdown("---")
    if not filtered_logs_df.empty:
        st.subheader(f"Displaying {len(filtered_logs_df)} Planned Trades")

        # Define columns to display and their order
        cols_to_display = ['Timestamp', 'Asset', 'Direction', 'EntryPrice', 'StopLossPrice', 'TakeProfitPrice', 'LotSize', 'RiskRewardRatio', 'Status', 'Notes']
        # Ensure all selected columns exist in the DataFrame
        display_df_cols = [col for col in cols_to_display if col in filtered_logs_df.columns]
        
        # For a more interactive table with a "Plot" button per row:
        # We iterate through the DataFrame and use st.columns for each row.
        
        # Header row for our custom table
        header_ui_cols = st.columns(len(display_df_cols) + 1) # +1 for the Plot button column
        for i, col_name in enumerate(display_df_cols):
            header_ui_cols[i].markdown(f"**{col_name}**")
        header_ui_cols[len(display_df_cols)].markdown("**Action**")
        st.markdown("---") # Separator after header

        for index_log, row_log in filtered_logs_df.iterrows():
            row_display_cols = st.columns(len(display_df_cols) + 1)
            for i, col_key in enumerate(display_df_cols):
                val = row_log.get(col_key)
                val_display = ""
                if pd.isna(val): val_display = "-"
                elif isinstance(val, float):
                    if col_key in ['EntryPrice', 'StopLossPrice', 'TakeProfitPrice']: val_display = f"{val:.5f}" # Adjust precision as needed
                    elif col_key in ['LotSize', 'RiskRewardRatio', 'AccountRiskPercent', 'SL_Pips', 'TP_Pips']: val_display = f"{val:.2f}"
                    elif col_key in ['RiskAmount', 'RewardAmount', 'AccountBalanceUsed']: val_display = f"${val:,.2f}"
                    else: val_display = f"{val:.2f}"
                elif isinstance(val, pd.Timestamp): val_display = val.strftime("%Y-%m-%d %H:%M")
                else: val_display = str(val)
                row_display_cols[i].write(val_display)

            log_id_for_key = row_log.get('LogID', str(index_log)) # Use LogID or index for unique key
            
            # "Plot" button for each row
            if row_display_cols[len(display_df_cols)].button(f"📈 Plot", key=f"plot_log_sec7_{log_id_for_key}", help="Load this trade's data into Chart Visualizer"):
                # Store the entire row or selected fields for the chart
                # Ensure asset, entry, sl, tp are present for plotting lines
                plot_data_payload = {
                    'Asset': row_log.get('Asset'),
                    'Entry': row_log.get('EntryPrice'),
                    'SL': row_log.get('StopLossPrice'),
                    'TP': row_log.get('TakeProfitPrice'),
                    'Direction': row_log.get('Direction'),
                    'Timestamp': str(row_log.get('Timestamp')), # Pass as string
                    'Source': 'LogViewer'
                }
                st.session_state['plot_data'] = plot_data_payload
                st.success(f"Selected '{plot_data_payload.get('Asset')}' @ Entry {plot_data_payload.get('Entry')} for Chart Visualizer.")
                # No rerun here, chart should pick it up. Or rerun if chart is in an expander that needs to update.
                # For immediate effect if chart is visible, a rerun might be desired or using st.experimental_set_query_params
                st.rerun() # Rerun to potentially update chart visualizer immediately if it depends on session_state directly for visibility or symbol change

    else:
        st.info("No planned trades match the current filter criteria.")

    # Display message in sidebar if plot_data is ready (from your original code)
    if 'plot_data' in st.session_state and st.session_state['plot_data'] and st.session_state['plot_data'].get('Source') == 'LogViewer':
        p_data = st.session_state['plot_data']
        st.sidebar.success(f"Chart Data: {p_data.get('Asset')} @ E:{p_data.get('Entry')} SL:{p_data.get('SL')} TP:{p_data.get('TP')}")

# ============== END OF SEC 7.0 =========================================

# ============== SEC 8.0: MAIN PAGE UI & LOGIC - CHART VISUALIZER =======

def display_chart_visualizer():
    """Displays the TradingView Chart Visualizer."""
    # The expander will be part of the main layout, called from the main function.
    # For now, this function defines how to determine the asset and render the chart.

    asset_to_display = "OANDA:XAUUSD" # Default asset
    chart_info_message = f"Displaying default chart: {asset_to_display}"

    # Priority for asset display:
    # 1. From Log Viewer's 'plot_data'
    # 2. From current Trade Planner's asset input (FIBO or CUSTOM mode)
    # 3. Default

    # Check Log Viewer data first
    if 'plot_data' in st.session_state and st.session_state['plot_data'] and st.session_state['plot_data'].get('Asset'):
        asset_from_log = st.session_state['plot_data'].get('Asset')
        if asset_from_log: # Ensure it's not None or empty
            chart_info_message = f"Displaying chart for: {asset_from_log.upper()} (from Log Viewer)"
            # Symbol Formatting for TradingView (add prefixes if needed)
            if asset_from_log.upper() == "XAUUSD": asset_to_display = "OANDA:XAUUSD"
            elif asset_from_log.upper() == "EURUSD": asset_to_display = "OANDA:EURUSD"
            # Add more common mappings or a more generic prefix logic
            elif ":" not in asset_from_log: # If no prefix, assume OANDA or try a common one
                asset_to_display = f"OANDA:{asset_from_log.upper()}"
            else:
                asset_to_display = asset_from_log.upper()
    else:
        # Check Trade Planner's current asset (if Log Viewer data isn't active)
        current_trade_mode = st.session_state.get('current_trade_mode', "FIBO") # Default to FIBO if not set
        asset_from_planner = None

        if current_trade_mode == "FIBO":
            asset_from_planner = st.session_state.get("asset_fibo_val_v2")
        elif current_trade_mode == "CUSTOM":
            asset_from_planner = st.session_state.get("asset_custom_val_v2")
        
        if asset_from_planner:
            chart_info_message = f"Displaying chart for: {asset_from_planner.upper()} (from Trade Planner)"
            if asset_from_planner.upper() == "XAUUSD": asset_to_display = "OANDA:XAUUSD"
            elif asset_from_planner.upper() == "EURUSD": asset_to_display = "OANDA:EURUSD"
            elif ":" not in asset_from_planner:
                asset_to_display = f"OANDA:{asset_from_planner.upper()}"
            else:
                asset_to_display = asset_from_planner.upper()
        # If neither log data nor planner asset is available, it uses the initial default.
    
    st.info(chart_info_message)

    # Prepare lines to draw (if any from plot_data)
    lines_to_draw_js = ""
    if 'plot_data' in st.session_state and st.session_state['plot_data']:
        plot = st.session_state['plot_data']
        entry = plot.get('Entry')
        sl = plot.get('SL')
        tp = plot.get('TP')
        
        # Simple JavaScript to draw horizontal lines. This requires the chart to be fully loaded.
        # This is an example; robust line drawing often needs more complex interaction with the TV library API
        # or using features that allow passing line data directly in the widget constructor if available.
        # For this lightweight widget, drawing after load is a common approach.
        lines_js_parts = []
        if entry is not None:
            lines_js_parts.append(f"widget.chart().createOrderLine().setText('Entry').setPrice({entry}).setLineColor('blue').setBodyBorderColor('blue').setQuantity('');")
        if sl is not None:
            lines_js_parts.append(f"widget.chart().createOrderLine().setText('SL').setPrice({sl}).setLineColor('red').setBodyBorderColor('red').setQuantity('');")
        if tp is not None:
            lines_js_parts.append(f"widget.chart().createOrderLine().setText('TP').setPrice({tp}).setLineColor('green').setBodyBorderColor('green').setQuantity('');")
        
        if lines_js_parts:
            lines_to_draw_js = " ".join(lines_js_parts)


    tradingview_html = f"""
    <div class="tradingview-widget-container" style="height:600px; width:100%;">
      <div id="tradingview_chart_widget_container" style="height:calc(100% - 32px); width:100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      var widget; // Make widget accessible for line drawing
      function initTradingViewChart() {{
        widget = new TradingView.widget({{
          "autosize": true, // Changed width/height to autosize
          "symbol": "{asset_to_display}",
          "interval": "15", // Default interval
          "timezone": "Asia/Bangkok",
          "theme": "dark",
          "style": "1",
          "locale": "th",
          "toolbar_bg": "#f1f3f6",
          "enable_publishing": false,
          "withdateranges": true,
          "allow_symbol_change": true,
          "hide_side_toolbar": false,
          "details": true, // Show details window
          "hotlist": true, // Show hotlist
          "calendar": true, // Show economic calendar
          "studies": [ // Example: Add Moving Average
            // "MASimple@tv-basicstudies" 
          ],
          "container_id": "tradingview_chart_widget_container"
        }});

        // Attempt to draw lines after widget is ready
        widget.onChartReady(function() {{
            console.log("Chart is ready. Attempting to draw lines.");
            try {{
                {lines_to_draw_js}
                console.log("Lines drawing script executed.");
            }} catch (e) {{
                console.error("Error drawing lines:", e);
            }}
        }});
      }}
      
      // Ensure tv.js is loaded before initializing
      if (typeof TradingView !== 'undefined') {{
          initTradingViewChart();
      }} else {{
          // Fallback if tv.js takes time to load from CDN (less reliable)
          var script = document.createElement('script');
          script.src = 'https://s3.tradingview.com/tv.js';
          script.async = true;
          script.onload = function() {{
              initTradingViewChart();
          }};
          document.head.appendChild(script);
      }}
      </script>
    </div>
    """
    st.components.v1.html(tradingview_html, height=610, scrolling=False)

    # After displaying the chart, clear plot_data if it came from LogViewer to prevent re-plotting on next non-log related rerun
    # Or only clear if the asset displayed matches the plot_data asset
    if 'plot_data' in st.session_state and st.session_state['plot_data'] and \
       st.session_state['plot_data'].get('Source') == 'LogViewer' and \
       asset_to_display.endswith(st.session_state['plot_data'].get('Asset','').upper()): # Check if displayed asset matches
        # st.warning("Clearing plot_data from LogViewer to prevent re-draw on next rerun.") # For debugging
        del st.session_state['plot_data']


# ============== END OF SEC 8.0 =========================================

# ============== SEC 9.0: MAIN PAGE UI & LOGIC - AI ASSISTANT (Placeholder) ===

def display_ai_assistant_placeholder():
    """Displays a placeholder for the AI Assistant feature."""
    st.header("🤖 AI Trading Assistant")
    
    with st.expander("Ask the AI Assistant (Future Feature)", expanded=False):
        st.info(
            """
            **This feature is currently under development.**

            Future capabilities may include:
            - Analyzing your trading patterns from uploaded statements (`ActualTrades`).
            - Providing insights on risk management based on your planned trades.
            - Answering questions about your trading performance.
            - Suggesting potential areas for improvement.
            """
        )
        
        user_query_ai = st.text_area(
            "What would you like to ask or analyze?", 
            placeholder="e.g., 'Analyze my win rate for XAUUSD last month', 'What's my average Risk/Reward ratio on winning trades?'",
            key="ai_user_query",
            height=100,
            disabled=True # Disable until feature is implemented
        )
        
        if st.button("Submit to AI (Disabled)", key="ai_submit_btn", disabled=True):
            # Placeholder for when AI processing is added
            st.session_state.ai_analysis_result = "AI processing not yet implemented."

        if st.session_state.get('ai_analysis_result'):
            st.markdown("### AI Response:")
            st.write(st.session_state.ai_analysis_result)

# ============== END OF SEC 9.0 =========================================

# ============== SEC 10.0: MAIN APPLICATION FLOW ========================

def main():
    """
    Main function to orchestrate the Streamlit application.
    Sets up the page structure and calls display functions for each section.
    """
    # --- Initialize GSpread client (already done globally in SEC 1.5 after imports) ---
    # gs_client is available globally if initialized successfully in SEC 1.5

    if not gs_client:
        st.error("🔴 Critical Error: Could not connect to Google Sheets. Application cannot proceed.")
        st.info("Please check your `gcp_service_account` secrets and network connection.")
        return # Stop further execution if no GSheet connection

    # --- Display Sidebar ---
    # Sidebar function should handle its own data loading for portfolios etc.
    display_sidebar(gs_client) # gs_client is passed to functions that need it

    # --- Main Page Content ---
    # Based on active portfolio data, which should be set by the sidebar
    active_portfolio = st.session_state.get('active_portfolio_data') # Retrieve after sidebar has run

    st.title("🚀 UltimateChart Trading Dashboard")
    st.markdown(f"**Portfolio Active:** `{active_portfolio.get('PortfolioName', 'None Selected') if active_portfolio else 'None Selected'}`")
    st.markdown("---")

    # --- Section: Chart Visualizer (Often useful to have it accessible near the top) ---
    # The chart visualizer can react to 'plot_data' from Log Viewer or inputs from Trade Planner
    with st.expander("📈 Chart Visualizer", expanded=True): # Default to expanded or not as you prefer
        display_chart_visualizer()
    st.markdown("---")

    # --- Section: Statement Management ---
    # Needs active_portfolio_data to know which portfolio to associate uploads with
    display_statement_management(gs_client, active_portfolio)
    st.markdown("---")
    
    # --- Section: Trade Planning Interface ---
    # Needs active_portfolio_data for asset parameters and account balance
    display_trade_planning_interface(gs_client, active_portfolio)
    st.markdown("---")

    # --- Section: Log Viewer ---
    # Needs active_portfolio_data to filter logs
    display_log_viewer(gs_client, active_portfolio)
    st.markdown("---")

    # --- Section: AI Assistant Placeholder ---
    display_ai_assistant_placeholder()
    st.markdown("---")

    # --- Footer or other global elements ---
    st.markdown("<hr><p style='text-align: center;'>UltimateChart Dashboard - End of Page</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    # Ensure session state initialization is called if not already (it's called in SEC 1.4)
    # initialize_session_state() # Called at the end of SEC 1.4 definitions

    main()

# ============== END OF SEC 10.0 ========================================

