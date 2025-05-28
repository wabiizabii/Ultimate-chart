# ======================= SEC 0: INITIAL SETUP & ALL FUNCTION DEFINITIONS =======================
import streamlit as st
import pandas as pd
import numpy as np # เพิ่ม numpy สำหรับการจัดการค่าว่าง
import os

# --- การตั้งค่าหน้าเว็บและค่าคงที่ ---
st.set_page_config(page_title="Ultimate Trading Dashboard", layout="wide")
LOG_FILE = "trade_log.csv"

# --- การตั้งค่า st.session_state เริ่มต้นสำหรับทั้งแอป ---
def initialize_session_state():
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.portfolios = {}
        st.session_state.active_portfolio_name = None
        st.session_state.acc_balance = 0.0
        st.session_state.df_stmt_current_active_portfolio = pd.DataFrame()
        st.session_state.trade_mode = "CUSTOM"
        st.session_state.plan_data = pd.DataFrame()

initialize_session_state()


# --- นิยามฟังก์ชันทั้งหมด ---
def calculate_tp_zones(df_plan):
    tp_zones_data = []
    if not df_plan.empty:
        # ใช้ SL จากแถวแรกเป็นเกณฑ์ในการคำนวณความเสี่ยง
        # ในแผน Fibo แต่ละ entry อาจมีราคาต่างกัน แต่ SL มักจะเป็นจุดเดียวกัน
        base_sl_price = df_plan['SL'].iloc[0]

        for index, entry_row in df_plan.iterrows():
            entry_price = entry_row['Price']
            risk_per_point = abs(entry_price - base_sl_price)

            if risk_per_point > 0:
                # วนลูปสำหรับ TP1 ถึง TP5 ของแต่ละ entry
                for i in range(1, 6):
                    tp_col = f'TP{i}'
                    # ตรวจสอบว่าคอลัมน์ TP นั้นมีอยู่และมีค่าหรือไม่
                    if tp_col in entry_row and pd.notna(entry_row[tp_col]):
                        tp_price = entry_row[tp_col]
                        lot_size = entry_row['Lot']
                        
                        profit_point = abs(tp_price - entry_price)
                        # สมมติค่าตัวคูณอย่างง่าย, สามารถปรับปรุงให้ซับซ้อนขึ้นได้
                        profit_usd = profit_point * lot_size * 10
                        rr_ratio = profit_point / risk_per_point if risk_per_point > 0 else 0
                        
                        tp_zones_data.append({
                            "From Entry": entry_row['Entry'],
                            "TP Zone": f"TP{i}",
                            "Price": tp_price,
                            "Lot": lot_size,
                            "Profit ($)": f"{profit_usd:,.2f}",
                            "R:R": f"1:{rr_ratio:.2f}"
                        })
    # ใช้ set เพื่อหา TP ที่ไม่ซ้ำกัน และจัดกลุ่ม
    unique_zones = {zone['TP Zone']: zone for zone in reversed(tp_zones_data)}.values()
    return pd.DataFrame(list(unique_zones))


# ======================= SEC 1: SIDEBAR CONTROLS =======================
with st.sidebar:
    st.title("Ultimate Trading Dashboard")
    st.markdown("---")

    # === SEC 1.1: Portfolio Selection & Management UI ===
    # (โค้ดส่วนนี้เหมือนเดิม)
    st.header("Portfolio Management")
    with st.container(border=True):
        st.subheader("Create New Portfolio")
        new_portfolio_name = st.text_input("New Portfolio Name", key="new_portfolio_name_input")
        initial_balance = st.number_input("Initial Balance", min_value=0.0, value=10000.0, step=1000.0, key="initial_balance_input")
        if st.button("Create Portfolio", use_container_width=True, type="primary"):
            if new_portfolio_name and new_portfolio_name not in st.session_state.portfolios:
                st.session_state.portfolios[new_portfolio_name] = {'balance': initial_balance}
                st.session_state.active_portfolio_name = new_portfolio_name
                st.success(f"Portfolio '{new_portfolio_name}' created!")
                st.rerun()
            else:
                st.error("Portfolio name cannot be empty or already exists.")
    st.markdown("---")
    portfolio_list = list(st.session_state.portfolios.keys())
    if not portfolio_list:
        st.warning("No portfolios found. Please create one above.")
    else:
        try:
            active_portfolio_index = portfolio_list.index(st.session_state.active_portfolio_name)
        except (ValueError, TypeError):
            st.session_state.active_portfolio_name = portfolio_list[0]
            active_portfolio_index = 0
        selected_portfolio = st.selectbox("Select Active Portfolio", options=portfolio_list, index=active_portfolio_index, key="portfolio_selector")
        if selected_portfolio != st.session_state.active_portfolio_name:
            st.session_state.active_portfolio_name = selected_portfolio
            st.rerun()
    if st.session_state.active_portfolio_name:
        current_balance = st.session_state.portfolios[st.session_state.active_portfolio_name].get('balance', 0.0)
        st.session_state.acc_balance = current_balance
        st.markdown("---")
        st.metric(label=f"Active Portfolio: **{st.session_state.active_portfolio_name}**", value=f"${st.session_state.acc_balance:,.2f}")
        st.markdown("---")

    # === SEC 1.2: Main Trade Setup: DD Limit, Mode, Reset ===
    st.header("Main Trade Setup")
    st.session_state.trade_mode = st.radio("Mode", ["CUSTOM", "FIBO"], index=0, key="trade_mode_selector", horizontal=True)
    
    # === SEC 1.3: FIBO Inputs & Calculation ===
    if st.session_state.trade_mode == "FIBO":
        with st.container(border=True):
            st.subheader("FIBO Inputs")
            
            fibo_asset = st.text_input("Asset", "XAUUSD", key="fibo_asset")
            fibo_direction = st.radio("Direction", ["Buy", "Sell"], horizontal=True, key="fibo_direction")
            
            col1, col2 = st.columns(2)
            with col1:
                fibo_swing_high = st.number_input("Swing High", value=2350.0, format="%.4f")
                fibo_sl = st.number_input("Stop Loss", value=2290.0, format="%.4f")
                fibo_lot = st.number_input("Lot Size", value=0.01, format="%.2f")
            with col2:
                fibo_swing_low = st.number_input("Swing Low", value=2300.0, format="%.4f")
                fibo_entry_levels = st.multiselect(
                    "Entry Levels (%)",
                    options=[23.6, 38.2, 50.0, 61.8, 78.6, 88.6],
                    default=[50.0, 61.8]
                )
                
            st.write("Take Profit Levels")
            tp_cols = st.columns(5)
            fibo_tps = []
            for i, col in enumerate(tp_cols):
                fibo_tps.append(col.number_input(f"TP{i+1}", value=2350.0 + i*10, format="%.4f", key=f"fibo_tp{i+1}"))

            if st.button("Calculate Fibo Plan", use_container_width=True, type="primary"):
                plan_entries = []
                swing_range = fibo_swing_high - fibo_swing_low
                
                if swing_range > 0 and fibo_entry_levels:
                    for i, level in enumerate(sorted(fibo_entry_levels)):
                        if fibo_direction == "Buy":
                            entry_price = fibo_swing_high - (swing_range * level / 100)
                        else: # Sell
                            entry_price = fibo_swing_low + (swing_range * level / 100)

                        plan_entry = {
                            "Entry": i + 1,
                            "Asset": fibo_asset,
                            "Lot": fibo_lot,
                            "Price": round(entry_price, 4),
                            "SL": fibo_sl,
                            "TP1": fibo_tps[0], "TP2": fibo_tps[1], "TP3": fibo_tps[2],
                            "TP4": fibo_tps[3], "TP5": fibo_tps[4]
                        }
                        plan_entries.append(plan_entry)
                    
                    st.session_state.plan_data = pd.DataFrame(plan_entries)
                    st.success("Fibo plan calculated and updated.")
                else:
                    st.error("Invalid swing range or no entry levels selected.")


    # === SEC 1.4: CUSTOM Inputs & Calculation ===
    if st.session_state.trade_mode == "CUSTOM":
        with st.container(border=True):
            st.subheader("CUSTOM Inputs")
            initial_plan_df = pd.DataFrame([
                {"Entry": 1, "Asset": "XAUUSD", "Lot": 0.01, "Price": 2300.0, "SL": 2295.0, "TP1": 2305.0, "TP2": 2310.0, "TP3": None, "TP4": None, "TP5": None},
                {"Entry": 2, "Asset": "XAUUSD", "Lot": 0.01, "Price": 2298.0, "SL": 2295.0, "TP1": 2305.0, "TP2": 2310.0, "TP3": None, "TP4": None, "TP5": None},
            ])
            st.write("Edit your custom trade plan below:")
            edited_df = st.data_editor(initial_plan_df, num_rows="dynamic", key="custom_plan_editor")
            st.session_state.plan_data = edited_df

# ======================= SEC 2: MAIN - ENTRY PLAN DETAILS =======================
with st.expander("Entry Plan Details", expanded=True):
    if 'plan_data' in st.session_state and not st.session_state.plan_data.empty:
        df_plan = st.session_state.plan_data
        st.subheader("Trade Entry Plan: Summary")
        st.dataframe(df_plan, use_container_width=True, hide_index=True)
        st.subheader("Take Profit Zone")
        df_tp_zones = calculate_tp_zones(df_plan)
        if not df_tp_zones.empty:
            st.dataframe(df_tp_zones, use_container_width=True, hide_index=True)
        else:
            st.warning("Could not calculate TP zones. Please ensure SL and TP values are set correctly.")
    else:
        st.info("No active trade plan. Please configure a plan in the sidebar.")

# ======================= SEC 3, 4, 5, 6... (โค้ดเหมือนเดิม) =======================
with st.expander("Chart Visualizer", expanded=True):
    st.info("This section will display the TradingView chart.")
with st.expander("Import Trade Statement", expanded=False):
    st.info("This section will be used to upload and process trade statements.")
with st.expander("Trading Dashboard", expanded=True):
    st.info("This section will display performance analytics based on the selected portfolio's data.")
    if st.session_state.active_portfolio_name:
        st.write(f"Displaying dashboard for portfolio: **{st.session_state.active_portfolio_name}**")
    else:
        st.warning("Please select or create a portfolio to view the dashboard.")
with st.expander("Trade Log Viewer", expanded=False):
    st.info("This section will display the saved trade plans from the log file.")
