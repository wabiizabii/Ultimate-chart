# ======================= SEC 0: IMPORT, CONFIG, SESSION STATE & ALL FUNCTIONS =======================
import streamlit as st
import pandas as pd
import openpyxl  
import numpy as np
import os
from datetime import datetime
import plotly.express as px
import google.generativeai as genai # Assuming you use this
import gspread # Assuming you use this

# --- การตั้งค่าหน้าเว็บ ---
st.set_page_config(page_title="Ultimate Trading Dashboard", layout="wide")

# --- ค่าคงที่ (จากไฟล์ของคุณ) ---
LOG_FILE = "trade_log.csv" # Will be used for saving plan later
GOOGLE_SHEET_NAME = "TradeLog" 
GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# --- NEW: การตั้งค่า st.session_state เริ่มต้นสำหรับทั้งแอป ---
def initialize_session_state():
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.portfolios = {} # {'Portfolio Name': {'balance': 10000}}
        st.session_state.active_portfolio_name = None
        st.session_state.acc_balance = 0.0 # Will be updated from active portfolio
        
        st.session_state.trade_mode = "FIBO" # Default to FIBO as requested
        
        # For plan data from sidebar calculations
        st.session_state.plan_data = pd.DataFrame() # For main entry plan summary
        st.session_state.tp_zones_data = pd.DataFrame() # For TP zones summary

        # Preserve keys from your original file if they are used for real-time UI updates
        # Example: If your original FIBO checkbox logic relies on a specific session_state key
        if "fibo_flags_original" not in st.session_state: # Example, adjust to your actual key
             st.session_state.fibo_flags_original = [True, True, True, True, True] # Default for 5 fibo levels

initialize_session_state()

# --- ALL FUNCTIONS (LIFTED FROM YOUR `mainล่าสุด.py`) ---
# Make sure all functions you defined globally are here

def get_gspread_client(): # Your original function
    try:
        if "gcp_service_account" not in st.secrets:
            st.warning("⚠️ Please configure 'gcp_service_account' in `.streamlit/secrets.toml` to connect to Google Sheets.")
            return None
        return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e:
        st.error(f"❌ Error connecting to Google Sheets: {e}")
        return None

def extract_data_from_statement(uploaded_file): # Your original function
    # This function will be integrated properly in a later step for SEC 4
    try:
        df = pd.read_excel(uploaded_file, engine='openpyxl')
        # ... (rest of your original extraction logic) ...
        # For now, returning a placeholder if complex, or your actual logic
        positions_start_series = df[df.apply(lambda row: row.astype(str).str.contains('Positions', case=False).any(), axis=1)]
        if not positions_start_series.empty:
            positions_start = positions_start_series.index[0]
            summary_start_series = df[df.apply(lambda row: row.astype(str).str.contains('Summary', case=False).any(), axis=1)]
            summary_start = summary_start_series.index[0] if not summary_start_series.empty else len(df)
            
            df_positions = pd.read_excel(uploaded_file, engine='openpyxl', skiprows=positions_start + 1, skipfooter=len(df) - summary_start if summary_start != len(df) else 0)
            df_positions.columns = [str(col).strip() for col in df_positions.columns]
            return df_positions
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error reading statement file (placeholder): {e}")
        return pd.DataFrame()

# Functions from your SEC 4 (Summary) / Drawdown / Performance - will be placed here
# For example, your get_today_drawdown, get_performance
# We will call these from relevant UI sections later.

def get_today_drawdown(log_file_path, current_account_balance):
    # Your original logic, but using current_account_balance from session_state
    if not os.path.exists(log_file_path): return 0
    df = pd.read_csv(log_file_path)
    today_str = datetime.now().strftime("%Y-%m-%d")
    if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0
    df_today = df[df["Timestamp"].str.startswith(today_str)]
    try:
        drawdown = df_today["Risk $"].astype(float).sum()
    except Exception: drawdown = 0
    return drawdown

def get_performance(log_file_path, mode="week"):
    # Your original logic
    if not os.path.exists(log_file_path): return 0, 0, 0
    df = pd.read_csv(log_file_path)
    if "Timestamp" not in df.columns or "Risk $" not in df.columns: return 0, 0, 0
    now = datetime.now()
    if mode == "week":
        week_start = (now - pd.Timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        df_period = df[df["Timestamp"] >= week_start]
    else: # month
        month_start = now.strftime("%Y-%m-01")
        df_period = df[df["Timestamp"] >= month_start]
    win = df_period[df_period["Risk $"].astype(float) > 0].shape[0]
    loss = df_period[df_period["Risk $"].astype(float) <= 0].shape[0]
    total = win + loss if (win + loss) > 0 else 1
    winrate = 100 * win / total
    gain = df_period["Risk $"].astype(float).sum()
    return winrate, gain, total

# ======================= SEC 1: SIDEBAR CONTROLS =======================
with st.sidebar:
    st.title("🚀 Ultimate Trading Dashboard")
    st.markdown("---")

    # === SEC 1.1: Portfolio Management (New Architecture) ===
    st.header("Portfolio Management")
    with st.container(border=True):
        st.subheader("Create New Portfolio")
        new_portfolio_name = st.text_input("New Portfolio Name", key="new_portfolio_name_input")
        initial_balance = st.number_input("Initial Balance", min_value=0.0, value=10000.0, step=1000.0, key="initial_balance_input")
        if st.button("Create Portfolio", use_container_width=True, type="primary"):
            if new_portfolio_name and new_portfolio_name not in st.session_state.portfolios:
                st.session_state.portfolios[new_portfolio_name] = {'balance': initial_balance}
                st.session_state.active_portfolio_name = new_portfolio_name
                st.rerun()
            else: st.error("Portfolio name cannot be empty or already exists.")
    st.markdown("---")
    portfolio_list = list(st.session_state.portfolios.keys())
    if not portfolio_list:
        st.warning("No portfolios found. Please create one above.")
    else:
        try:
            active_portfolio_index = portfolio_list.index(st.session_state.active_portfolio_name)
        except (ValueError, TypeError): # Handle case where active_portfolio_name might be None or not in list
            if portfolio_list:
                st.session_state.active_portfolio_name = portfolio_list[0]
                active_portfolio_index = 0
            else: # Should not happen if portfolio_list is not empty, but as a safeguard
                active_portfolio_index = 0 
        
        selected_portfolio = st.selectbox("Select Active Portfolio", options=portfolio_list, index=active_portfolio_index, key="portfolio_selector")
        if selected_portfolio != st.session_state.active_portfolio_name:
            st.session_state.active_portfolio_name = selected_portfolio
            st.rerun()

    active_balance_from_state = 0.0 # Default to 0
    if st.session_state.active_portfolio_name:
        active_balance_from_state = st.session_state.portfolios[st.session_state.active_portfolio_name].get('balance', 0.0)
        st.session_state.acc_balance = active_balance_from_state # Update global session state
        st.markdown("---")
        st.metric(label=f"Active Portfolio: **{st.session_state.active_portfolio_name}**", value=f"${st.session_state.acc_balance:,.2f}")
        st.markdown("---")
    else: # No portfolio selected or created yet
        st.session_state.acc_balance = 0.0


    # === SEC 1.2: Trade Mode (Lifted from your file's structure) ===
    st.header("🎛️ Trade Setup") # Using header from your file
    # Your original Drawdown Limit input
    drawdown_limit_pct = st.number_input( 
        "Drawdown Limit ต่อวัน (%)",
        min_value=0.1, max_value=20.0,
        value=2.0, step=0.1, format="%.1f", key="sidebar_drawdown_limit" # Added key for consistency
    )
    st.session_state.trade_mode = st.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, index=0, key="sidebar_mode") # FIBO-First

    # Your original Reset Form button
    if st.button("🔄 Reset Form", key="sidebar_reset_button"):
        risk_keep = st.session_state.get("risk_pct_fibo_original", 1.0) # Using example key from your structure
        asset_keep = st.session_state.get("asset_fibo_original", "XAUUSD")

        keys_to_delete = [k for k in list(st.session_state.keys()) if k not in {"portfolios", "active_portfolio_name", "acc_balance", "initialized", "trade_mode", "risk_pct_fibo_original", "asset_fibo_original", "fibo_flags_original"}]
        for k in keys_to_delete: del st.session_state[k]
        
        st.session_state["risk_pct_fibo_original"] = risk_keep # Example
        st.session_state["asset_fibo_original"] = asset_keep # Example
        st.session_state.fibo_flags_original = [True] * 5 # Assuming 5 fibo levels as in your example
        st.session_state.plan_data = pd.DataFrame()
        st.session_state.tp_zones_data = pd.DataFrame()
        st.rerun()

    # === SEC 1.3: FIBO Inputs & Real-time Calculation (Lifted & Wired) ===
    if st.session_state.trade_mode == "FIBO":
        with st.container(border=True): # Using container from your structure
            # This section should precisely mirror your UI and real-time calculation for FIBO
            # I will use the variable names and widget keys from your `mainล่าสุด.py`
            # All calculations will now use `active_balance_from_state`

            # --- Start of Lifted FIBO UI from your mainล่าสุด.py ---
            col1, col2, col3 = st.columns([2, 2, 2])
            with col1:
                asset_fibo = st.text_input("Asset", value=st.session_state.get("asset_fibo_original", "XAUUSD"), key="asset_fibo_original")
            with col2:
                risk_pct_fibo = st.number_input("Risk %", min_value=0.01,max_value=100.0,value=st.session_state.get("risk_pct_fibo_original", 1.0),step=0.01,format="%.2f",key="risk_pct_fibo_original")
            with col3:
                direction_fibo = st.radio("Direction", ["Long", "Short"], horizontal=True, key="direction_fibo_original")

            col4, col5 = st.columns(2)
            with col4:
                swing_high_fibo_str = st.text_input("High", key="swing_high_original_fibo", value=st.session_state.get("swing_high_original_fibo_val", "2350.0"))
            with col5:
                swing_low_fibo_str = st.text_input("Low", key="swing_low_original_fibo", value=st.session_state.get("swing_low_original_fibo_val", "2300.0"))
            
            st.session_state.swing_high_original_fibo_val = swing_high_fibo_str # Store text input for persistence
            st.session_state.swing_low_original_fibo_val = swing_low_fibo_str

            st.markdown("**📐 Entry Fibo Levels**")
            fibos_options = [0.114, 0.25, 0.382, 0.5, 0.618] # Your Fibo levels
            labels_fibo = [f"{l:.3f}" for l in fibos_options]
            cols_fibo_checkboxes = st.columns(len(fibos_options))

            if "fibo_flags_original" not in st.session_state:
                st.session_state.fibo_flags_original = [True] * len(fibos_options)

            current_fibo_flags = []
            for i, col_cb in enumerate(cols_fibo_checkboxes):
                checked = col_cb.checkbox(labels_fibo[i], value=st.session_state.fibo_flags_original[i], key=f"fibo_cb_{i}_original")
                current_fibo_flags.append(checked)
            st.session_state.fibo_flags_original = current_fibo_flags
            # --- End of Lifted FIBO UI ---

            # --- Start of Lifted FIBO Real-time Calculation from your mainล่าสุด.py ---
            # This logic will run on every interaction due to Streamlit's nature
            temp_plan_details_fibo = []
            temp_tp_zones_fibo = []
            
            try:
                high_fibo = float(swing_high_fibo_str)
                low_fibo = float(swing_low_fibo_str)
                selected_fibo_values = [fibos_options[i] for i, sel in enumerate(st.session_state.fibo_flags_original) if sel]
                
                # Assume SL and TP Ratios are defined in your original file, find them
                # For demonstration, I'll use placeholders or simple logic if not immediately obvious
                sl_price_fibo_val_str = st.session_state.get("sl_price_fibo_val", str(low_fibo * 0.99 if direction_fibo == "Long" else high_fibo * 1.01)) # Placeholder SL logic
                sl_price_fibo_val = float(st.text_input("SL Price (FIBO)", value=sl_price_fibo_val_str, key="sl_price_fibo_input_actual")) # Lifted from your file's SEC 1.5 like structure
                st.session_state.sl_price_fibo_val = str(sl_price_fibo_val)


                tp_ratios_fibo_str_val = st.session_state.get("tp_ratios_fibo_val","1,2,3") # Placeholder TP Ratios
                tp_ratios_fibo_str_val = st.text_input('TP R:R Ratios (FIBO)', value=tp_ratios_fibo_str_val, key="tp_ratios_fibo_input_actual")
                st.session_state.tp_ratios_fibo_val = tp_ratios_fibo_str_val


                if high_fibo > low_fibo and selected_fibo_values and active_balance_from_state > 0:
                    risk_amount_total_fibo = active_balance_from_state * (risk_pct_fibo / 100)
                    risk_per_entry_fibo = risk_amount_total_fibo / len(selected_fibo_values)
                    swing_range_fibo = high_fibo - low_fibo

                    for i, level in enumerate(selected_fibo_values):
                        entry_price_fibo = low_fibo + (swing_range_fibo * level) if direction_fibo == "Long" else high_fibo - (swing_range_fibo * level)
                        # SL logic from your file - this might be more complex
                        # For example, you had dynamic SL based on fibo level. I will try to replicate that:
                        effective_sl_price = sl_price_fibo_val # Default SL, or your dynamic logic
                        if abs(level - 0.5) < 1e-4: # Example from your logic
                             effective_sl_price = low_fibo + (high_fibo - low_fibo) * ((0.25 + 0.382)/2) if direction_fibo == "Long" else high_fibo - (high_fibo - low_fibo) * ((0.25 + 0.382)/2)
                        elif abs(level - 0.618) < 1e-4:
                             effective_sl_price = low_fibo + (high_fibo - low_fibo) * ((0.382 + 0.5)/2) if direction_fibo == "Long" else high_fibo - (high_fibo - low_fibo) * ((0.382 + 0.5)/2)
                        # else: use the fixed sl_price_fibo_val

                        stop_points_fibo = abs(entry_price_fibo - effective_sl_price)
                        lot_size_fibo = risk_per_entry_fibo / stop_points_fibo if stop_points_fibo > 0 else 0.0
                        
                        entry_data = {'Entry': i + 1, 'Asset': asset_fibo, 'Lot': lot_size_fibo, 'Price': entry_price_fibo, 'SL': effective_sl_price}
                        
                        tp_ratios_parsed_fibo = [float(r.strip()) for r in tp_ratios_fibo_str_val.split(',')]
                        for j, ratio in enumerate(tp_ratios_parsed_fibo):
                            tp_price_fibo = entry_price_fibo + (stop_points_fibo * ratio) if direction_fibo == "Long" else entry_price_fibo - (stop_points_fibo * ratio)
                            entry_data[f'TP{j+1}'] = tp_price_fibo
                            if i == 0 : # Or your logic for summarizing TP zones
                                temp_tp_zones_fibo.append({'TP Zone': f"TP{j+1}", 'Price': tp_price_fibo, 'Lot': lot_size_fibo, 'Profit': abs(tp_price_fibo - entry_price_fibo) * lot_size_fibo, 'R:R': ratio})
                        temp_plan_details_fibo.append(entry_data)
                    
                    st.session_state.plan_data = pd.DataFrame(temp_plan_details_fibo)
                    st.session_state.tp_zones_data = pd.DataFrame(temp_tp_zones_fibo)
                else: # Reset if inputs are invalid
                    st.session_state.plan_data = pd.DataFrame()
                    st.session_state.tp_zones_data = pd.DataFrame()
            except ValueError: # Handle cases where float conversion fails for text inputs
                st.session_state.plan_data = pd.DataFrame()
                st.session_state.tp_zones_data = pd.DataFrame()
                st.sidebar.warning("Invalid number format in High/Low/SL for FIBO.")
            except Exception as e: # Catch other potential errors
                st.session_state.plan_data = pd.DataFrame()
                st.session_state.tp_zones_data = pd.DataFrame()
                # st.sidebar.error(f"FIBO Calc Error: {e}") # Optional: show specific error
            # --- End of Lifted FIBO Real-time Calculation ---

            # Your original "Save Plan" button for FIBO (logic to be fully integrated later with portfolio_name)
            # This button press itself does not trigger calculation in real-time setup
            # Calculation happens on input change. Save button just saves the current state.
            if st.button("Save FIBO Plan", key="save_fibo_button_original"):
                if not st.session_state.plan_data.empty:
                    # Add portfolio name before saving
                    df_to_save = st.session_state.plan_data.copy()
                    df_to_save["Portfolio"] = st.session_state.active_portfolio_name
                    df_to_save["Mode"] = "FIBO"
                    df_to_save["Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    # Actual saving logic (CSV or GSheet) will be refined in Step 4 of our overall plan
                    st.info(f"Plan for {st.session_state.active_portfolio_name} (FIBO) ready to be saved (logic pending).")
                else:
                    st.warning("No FIBO plan data to save.")


    elif st.session_state.trade_mode == 'CUSTOM':
        with st.container(border=True):
            # This section should precisely mirror your UI and real-time calculation for CUSTOM
            # All calculations will now use `active_balance_from_state`

            # --- Start of Lifted CUSTOM UI from your mainล่าสุด.py ---
            st.subheader("CUSTOM Plan (Real-time Calc)")
            risk_pct_custom = st.number_input("Risk % per Entry", min_value=0.01, max_value=100.0, value=st.session_state.get("risk_pct_custom_original", 0.5), step=0.01, format="%.2f", key="risk_pct_custom_original")
            
            # Your logic for handling multiple entries in CUSTOM mode
            # Assuming you had a way to define number of entries or used st.data_editor
            # For simplicity, I'll adapt the single entry from your provided snippet, 
            # but this needs to match your multi-entry UI if it exists.
            # If you used st.data_editor, that logic would go here.

            # Adapting from your provided "CUSTOM" snippet structure
            num_entries_custom = st.number_input("จำนวนไม้ (CUSTOM)", min_value=1, max_value=10, value=st.session_state.get("num_entries_custom_val", 1), step=1, key="num_entries_custom_original")
            st.session_state.num_entries_custom_val = num_entries_custom

            temp_plan_details_custom = []
            temp_tp_zones_custom = []
            
            current_custom_inputs = st.session_state.get("current_custom_inputs_val", [{} for _ in range(num_entries_custom)])
            if len(current_custom_inputs) != num_entries_custom: # Adjust if num_entries changes
                current_custom_inputs = [{} for _ in range(num_entries_custom)]

            for i in range(num_entries_custom):
                st.markdown(f"--- ไม้ที่ {i+1} ---")
                cols_custom_entry = st.columns(3)
                entry_val_str = cols_custom_entry[0].text_input(f"Entry {i+1}", value=current_custom_inputs[i].get("entry_str", "0.00"), key=f"custom_entry_str_{i}")
                sl_val_str = cols_custom_entry[1].text_input(f"SL {i+1}", value=current_custom_inputs[i].get("sl_str", "0.00"), key=f"custom_sl_str_{i}")
                # TP is auto-calculated in your CUSTOM logic based on RR=3
                # tp_val_str = cols_custom_entry[2].text_input(f"TP {i+1}", value=current_custom_inputs[i].get("tp_str", "0.00"), key=f"custom_tp_str_{i}") # Keep if you want to override auto-TP
                
                current_custom_inputs[i]["entry_str"] = entry_val_str
                current_custom_inputs[i]["sl_str"] = sl_val_str
                # current_custom_inputs[i]["tp_str"] = tp_val_str


                try:
                    entry_val = float(entry_val_str)
                    sl_val = float(sl_val_str)
                    # tp_val = float(tp_val_str) # If TP is manual

                    if active_balance_from_state > 0:
                        risk_amount_custom_entry = active_balance_from_state * (risk_pct_custom / 100)
                        stop_points_custom = abs(entry_val - sl_val)
                        lot_size_custom = risk_amount_custom_entry / stop_points_custom if stop_points_custom > 0 else 0.0

                        # Your automatic TP calculation (e.g., TP at RR=3)
                        # Assuming 'Buy' direction for simplicity if not specified in your original CUSTOM UI
                        # Your original CUSTOM had a 'direction' from FIBO possibly leaking, so explicit direction is better
                        custom_direction = st.radio(f"Direction Entry {i+1}", ["Long", "Short"], horizontal=True, key=f"custom_dir_{i}", index=0 if current_custom_inputs[i].get("direction", "Long") == "Long" else 1)
                        current_custom_inputs[i]["direction"] = custom_direction

                        tp1_custom = entry_val + (stop_points_custom * 1) if custom_direction == "Long" else entry_val - (stop_points_custom * 1)
                        tp2_custom = entry_val + (stop_points_custom * 2) if custom_direction == "Long" else entry_val - (stop_points_custom * 2)
                        tp3_custom = entry_val + (stop_points_custom * 3) if custom_direction == "Long" else entry_val - (stop_points_custom * 3)

                        entry_data = {'Entry': i + 1, 'Asset': st.session_state.get("asset_fibo_original","XAUUSD"), 'Lot': lot_size_custom, 'Price': entry_val, 'SL': sl_val, 
                                      'TP1': tp1_custom, 'TP2': tp2_custom, 'TP3': tp3_custom}
                        temp_plan_details_custom.append(entry_data)
                        
                        # For TP Zones summary (can be adjusted based on your original logic)
                        temp_tp_zones_custom.append({'TP Zone': 'TP1', 'Price': tp1_custom, 'Lot': lot_size_custom, 'Profit': abs(tp1_custom-entry_val)*lot_size_custom, 'R:R': 1.0})
                        temp_tp_zones_custom.append({'TP Zone': 'TP2', 'Price': tp2_custom, 'Lot': lot_size_custom, 'Profit': abs(tp2_custom-entry_val)*lot_size_custom, 'R:R': 2.0})
                        temp_tp_zones_custom.append({'TP Zone': 'TP3', 'Price': tp3_custom, 'Lot': lot_size_custom, 'Profit': abs(tp3_custom-entry_val)*lot_size_custom, 'R:R': 3.0})

                        lot_display = f"Lot: {lot_size_custom:.2f}"
                        risk_per_entry_display = f"Risk$ ต่อไม้: {risk_amount_custom_entry:.2f}"
                        tp_rr3_display = f"TP ที่ RR=3: {tp3_custom:.4f}" # Using TP3 as example
                        st.caption(lot_display + " | " + risk_per_entry_display + " | " + tp_rr3_display)

                    else:
                        st.caption("Lot: - | Risk$ ต่อไม้: - | TP ที่ RR=3: -")
                except ValueError:
                    st.caption("Lot: - | Risk$ ต่อไม้: - | TP ที่ RR=3: - (Invalid input)")
                except Exception as e:
                    st.caption(f"Calc Error: {e}")
            
            st.session_state.current_custom_inputs_val = current_custom_inputs

            if temp_plan_details_custom:
                st.session_state.plan_data = pd.DataFrame(temp_plan_details_custom)
                # Consolidate TP zones for custom
                unique_custom_tp_zones = {}
                for zone in temp_tp_zones_custom:
                    if zone['TP Zone'] not in unique_custom_tp_zones or unique_custom_tp_zones[zone['TP Zone']]['Lot'] < zone['Lot']: # Example: take highest lot for the TP
                         unique_custom_tp_zones[zone['TP Zone']] = zone
                st.session_state.tp_zones_data = pd.DataFrame(list(unique_custom_tp_zones.values()))
            else:
                st.session_state.plan_data = pd.DataFrame()
                st.session_state.tp_zones_data = pd.DataFrame()
            # --- End of Lifted CUSTOM Real-time Calculation ---
            
            # Your original "Save Plan" button for CUSTOM
            if st.button("Save CUSTOM Plan", key="save_custom_button_original"):
                if not st.session_state.plan_data.empty:
                    df_to_save = st.session_state.plan_data.copy()
                    df_to_save["Portfolio"] = st.session_state.active_portfolio_name
                    df_to_save["Mode"] = "CUSTOM"
                    df_to_save["Timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.info(f"Plan for {st.session_state.active_portfolio_name} (CUSTOM) ready to be saved (logic pending).")
                else:
                    st.warning("No CUSTOM plan data to save.")


# ======================= SEC 2: ENTRY PLAN DETAILS (LIFTED & WIRED) =======================
# This section now reads from st.session_state updated by the real-time calculations above
with st.expander("📊 Entry Plan Details", expanded=True):
    if 'plan_data' in st.session_state and not st.session_state.plan_data.empty:
        df_plan_display = st.session_state.plan_data
        df_tp_zones_display = st.session_state.tp_zones_data

        # This display structure is lifted from your original file's main area (SEC 2+3)
        st.subheader("🎯 Entry Levels" if st.session_state.trade_mode == "FIBO" else "🎯 Entry & Take Profit Zones") # Dynamic title
        
        # Your original way of displaying the plan
        # If you used st.columns for FIBO entry and TP, that structure would be replicated here
        if st.session_state.trade_mode == "FIBO":
            col_entry_fibo, col_tp_fibo = st.columns(2)
            with col_entry_fibo:
                st.markdown("##### Entry Plan Summary (FIBO)")
                st.dataframe(df_plan_display.style.format(precision=4), use_container_width=True, hide_index=True)
            with col_tp_fibo:
                st.markdown("##### Take Profit Zones (FIBO)")
                if not df_tp_zones_display.empty:
                     st.dataframe(df_tp_zones_display.style.format(precision=4), use_container_width=True, hide_index=True)
                else:
                     st.info("TP Zones will appear once plan is calculated.")
        elif st.session_state.trade_mode == "CUSTOM":
            st.markdown("##### Entry Plan Summary (CUSTOM)")
            st.dataframe(df_plan_display.style.format(precision=4), use_container_width=True, hide_index=True)
            if not df_tp_zones_display.empty: # Assuming CUSTOM mode also produces tp_zones_data
                st.markdown("##### Take Profit Zones (CUSTOM)")
                st.dataframe(df_tp_zones_display.style.format(precision=4), use_container_width=True, hide_index=True)
            # Your original RR warning for CUSTOM
            # This needs to be adapted based on how RR is calculated and stored for CUSTOM
            # For now, let's assume df_plan_display might have an 'RR' column if you calculated it
            if 'RR' in df_plan_display.columns:
                 for i, row_rr in df_plan_display.iterrows():
                    try:
                        rr_val = float(row_rr["RR"])
                        if rr_val < 2:
                            st.warning(f"🎯 Entry {row_rr.get('Entry', i+1)} RR is low ({rr_val:.2f})")
                    except: pass
    else:
        st.info("กรอกข้อมูลแผนเทรดใน Sidebar เพื่อดูสรุป (Configure plan in sidebar to see summary).")


# ======================= SEC 3-6: Original Code (Placeholders - Awaiting Full Integration) =======================
# These sections are from your original file.
# They will be fully integrated with the Active Portfolio system in later steps.

# Your original SEC 4 (Summary) / Scaling Manager / Drawdown Lock logic from Sidebar:
# This was moved to sidebar in your file. I'll represent the core logic display here if it was separate.
# For now, I'm assuming the main summary parts were directly in the trade plan display (SEC 2)
# Or they were separate metrics. We will integrate these properly next.

# --- Your original Drawdown logic (from old SEC 5) ---
# This part needs to be integrated with st.session_state.acc_balance
# drawdown_today = get_today_drawdown(LOG_FILE, st.session_state.acc_balance)
# drawdown_limit_usd = -st.session_state.acc_balance * (drawdown_limit_pct / 100) # Use drawdown_limit_pct from sidebar

# if drawdown_today <= drawdown_limit_usd and drawdown_limit_usd < 0 : # Check if limit is negative (meaning loss limit)
#     st.sidebar.error(f"🚨 Trading Locked! Daily DD Limit Reached: {abs(drawdown_today):.2f} / {abs(drawdown_limit_usd):.2f}")
    # Add logic here to disable trading inputs if needed
# else:
#     st.sidebar.success(f"Daily DD: {abs(drawdown_today):.2f} / {abs(drawdown_limit_usd):.2f}")


# --- Your original Scaling Manager (from old SEC 1.x / SEC 1.5) ---
# This will be integrated with the new structure
with st.sidebar.expander("⚙️ Scaling Manager Settings (Original)", expanded=False): # As in your file
    scaling_step = st.number_input("Scaling Step (%)", min_value=0.01, max_value=1.0, value=0.25, step=0.01, format="%.2f", key="orig_scaling_step")
    min_risk_pct_scale = st.number_input("Minimum Risk % (Scaling)", min_value=0.01, max_value=100.0, value=0.5, step=0.01, format="%.2f", key="orig_min_risk")
    max_risk_pct_scale = st.number_input("Maximum Risk % (Scaling)", min_value=0.01, max_value=100.0, value=5.0, step=0.01, format="%.2f", key="orig_max_risk")
    scaling_mode_orig = st.radio("Scaling Mode (Original)", ["Manual", "Auto"], horizontal=True, key="orig_scaling_mode")

# --- Your original SEC 7: Chart Visualizer ---
with st.expander("📈 Chart Visualizer (Original)", expanded=True):
    # This is your TradingView embed logic
    plot_button_orig = st.button("Plot Plan", key="plot_plan_original")
    if plot_button_orig:
        st.components.v1.html("""
        <div class="tradingview-widget-container">
          <div id="tradingview_legendary"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({
            "width": "100%", "height": 600, "symbol": "OANDA:XAUUSD", "interval": "15",
            "timezone": "Asia/Bangkok", "theme": "dark", "style": "1", "locale": "th",
            "toolbar_bg": "#f1f3f6", "enable_publishing": true, "withdateranges": true,
            "allow_symbol_change": true, "hide_side_toolbar": false, "details": true,
            "hotlist": true, "calendar": true, "container_id": "tradingview_legendary"
          });
          </script>
        </div>
        """, height=620)
    else:
        st.info("กดปุ่ม Plot Plan เพื่อแสดงกราฟ TradingView")


# --- Your original SEC 8: AI Summary & Insight ---
with st.expander("🤖 AI Assistant (Original)", expanded=True):
    # Your original AI logic here
    st.info("Original AI Assistant content will be placed here and refactored later.")


# --- Your original SEC 7 (new SEC 4): Statement Import ---
with st.expander("📂 Statement Import (Original)", expanded=False): # Renumbered to SEC 4 conceptually
    uploaded_file_orig = st.file_uploader("Upload Statement (.xlsx) (Original)", type=["xlsx"], key="original_uploader")
    if uploaded_file_orig:
        df_stmt_orig = extract_data_from_statement(uploaded_file_orig) # Using your function
        if not df_stmt_orig.empty:
            st.dataframe(df_stmt_orig)


# --- Your original SEC 9 (new SEC 5): Dashboard ---
with st.expander("💡 Dashboard (Original)", expanded=False): # Renumbered to SEC 5 conceptually
    # Your original Dashboard logic with tabs
    st.info("Original Dashboard content will be placed here and refactored later.")


# --- Your original SEC 6: Log Viewer ---
with st.expander("📚 Trade Log Viewer (Original)", expanded=False):
    # Your original Log Viewer logic
    if os.path.exists(LOG_FILE):
        try:
            df_log_orig = pd.read_csv(LOG_FILE)
            st.dataframe(df_log_orig, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"อ่าน log ไม่ได้: {e}")
    else:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้ (Original Log Viewer)")
