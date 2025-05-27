# ======================= main.py (ฉบับแก้ไขสมบูรณ์ครั้งสุดท้าย) =======================
import streamlit as st
import pandas as pd
import numpy as np
import openpyxl # ยังคงต้อง import ไว้สำหรับ engine
import os # สำหรับ get_today_drawdown และ get_performance
from datetime import datetime # สำหรับ get_today_drawdown และ get_performance
import plotly.express as px # สำหรับกราฟใน Dashboard
# import google.generativeai as genai # ถ้าจะใช้ AI Assistant ค่อยเปิด
# import gspread # ถ้าจะใช้ Google Sheets ค่อยเปิด

# ======================= SEC 0: CONFIG & INITIAL SETUP =======================
# 0.1. Page Config (ควรอยู่บนสุด)
st.set_page_config(
    page_title="Ultimate Chart Dashboard",
    page_icon="📊",
    layout="wide"
)

# 0.2. Initial Variables
acc_balance = 10000 
log_file = "trade_log.csv" # ไฟล์สำหรับบันทึกแผนเทรด

# GOOGLE_SHEET_NAME = "TradeLog" 
# GOOGLE_WORKSHEET_NAME = "Uploaded Statements"

# ======================= SEC 0.5: Function Definitions (Utility & GSheets) =======================
# 0.5.1. Google Sheets Functions (ถ้าไม่ใช้ ปิด comment ไว้)
# def get_gspread_client():
#     # ... (โค้ด gspread ของคุณ) ...
#     return None

# def load_statement_from_gsheets():
#     # ... (โค้ด gspread ของคุณ) ...
#     return {'deals': pd.DataFrame()} 

# def save_statement_to_gsheets(df_to_save):
#     # ... (โค้ด gspread ของคุณ) ...
#     pass

# 0.5.2. Utility Functions
def get_today_drawdown(log_file_path, current_acc_balance):
    if not os.path.exists(log_file_path):
        return 0
    try:
        df = pd.read_csv(log_file_path)
        today_str = datetime.now().strftime("%Y-%m-%d")
        if "Timestamp" not in df.columns or "Risk $" not in df.columns:
            return 0
        # Ensure 'Risk $' is numeric, coercing errors and filling NaNs
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0)
        df_today = df[df["Timestamp"].str.startswith(today_str)]
        drawdown = df_today["Risk $"].sum() # Risk $ can be negative for losses
        return drawdown # This value will be negative if it's a loss
    except Exception as e:
        st.error(f"Error in get_today_drawdown: {e}")
        return 0

def get_performance(log_file_path, mode="week"):
    if not os.path.exists(log_file_path):
        return 0, 0, 0
    try:
        df = pd.read_csv(log_file_path)
        if "Timestamp" not in df.columns or "Risk $" not in df.columns:
            return 0, 0, 0
        
        # Ensure 'Risk $' is numeric
        df["Risk $"] = pd.to_numeric(df["Risk $"], errors='coerce').fillna(0)
            
        now = datetime.now()
        if mode == "week":
            week_start = (now - pd.Timedelta(days=now.weekday())).strftime("%Y-%m-%d")
            df_period = df[df["Timestamp"] >= week_start]
        else:  # month
            month_start = now.strftime("%Y-%m-01")
            df_period = df[df["Timestamp"] >= month_start]
        
        win = df_period[df_period["Risk $"] > 0].shape[0]
        loss = df_period[df_period["Risk $"] <= 0].shape[0] # Loss or BreakEven
        total_trades_period = win + loss
        
        winrate = (100 * win / total_trades_period) if total_trades_period > 0 else 0
        gain = df_period["Risk $"].sum()
        return winrate, gain, total_trades_period
    except Exception as e:
        st.error(f"Error in get_performance: {e}")
        return 0,0,0

# ======================= SEC 1: SIDEBAR / INPUT ZONE =======================
st.sidebar.header("🎛️ Trade Setup")

# 1.1. Drawdown Limit
drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=2.0, step=0.1, format="%.1f",
    key="sidebar_dd_limit"
)

# 1.2. Trade Mode
mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="sidebar_mode")

# 1.3. Reset Form Button
if st.sidebar.button("🔄 Reset Form", key="sidebar_reset_button"):
    # ... (โค้ด Reset Form ของคุณเหมือนเดิม) ...
    st.session_state.fibo_flags = [False] * 5 # สมมติว่ามี fibo 5 ระดับ
    st.rerun()

# 1.4. Input Zone (แยก FIBO/CUSTOM)
if mode == "FIBO":
    # ... (โค้ดส่วน FIBO Inputs ของคุณเหมือนเดิม) ...
    asset = st.sidebar.text_input("Asset", value="XAUUSD", key="fibo_asset")
    risk_pct = st.sidebar.number_input("Risk %", min_value=0.01, value=1.0, step=0.01, key="fibo_risk_pct")
    direction = st.sidebar.radio("Direction", ["Long", "Short"], horizontal=True, key="fibo_direction")
    swing_high = st.sidebar.text_input("High", key="fibo_swing_high")
    swing_low = st.sidebar.text_input("Low", key="fibo_swing_low")
    
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibos = [0.114, 0.25, 0.382, 0.5, 0.618]
    if "fibo_flags" not in st.session_state:
        st.session_state.fibo_flags = [True] * len(fibos) # Default all to True
    
    cols_fibo = st.sidebar.columns(len(fibos))
    for i, col in enumerate(cols_fibo):
        st.session_state.fibo_flags[i] = col.checkbox(f"{fibos[i]:.3f}", value=st.session_state.fibo_flags[i], key=f"fibo_cb_{i}")
    
    save_fibo = st.sidebar.button("Save Plan", key="fibo_save_plan")

elif mode == "CUSTOM":
    # ... (โค้ดส่วน CUSTOM Inputs ของคุณเหมือนเดิม) ...
    asset = st.sidebar.text_input("Asset", value="XAUUSD", key="custom_asset")
    risk_pct = st.sidebar.number_input("Risk %", min_value=0.01, value=1.0, step=0.01, key="custom_risk_pct")
    n_entry = st.sidebar.number_input("จำนวนไม้", min_value=1, value=1, step=1, key="custom_n_entry")
    custom_inputs_data = []
    for i in range(int(n_entry)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        # ... (โค้ดกรอก Entry, SL, TP แต่ละไม้) ...
    save_custom = st.sidebar.button("Save Plan", key="custom_save_plan")


# ======================= SEC 4: SUMMARY (ย้ายไป Sidebar) =======================
# ... (โค้ดคำนวณและแสดง Summary ใน Sidebar ของคุณเหมือนเดิม) ...

# ======================= SEC 1.x: SCALING MANAGER SETTINGS (ท้าย SIDEBAR) =======================
# ... (โค้ด Scaling Manager ของคุณเหมือนเดิม) ...

# ======================= SEC 1.5: SCALING SUGGESTION & CONFIRM =======================
# ... (โค้ด Scaling Suggestion ของคุณเหมือนเดิม) ...

# ======================= SEC 2+3: MAIN AREA – ENTRY TABLE (FIBO/CUSTOM) =======================
# ... (โค้ดแสดง Entry Table ใน Main Area ของคุณเหมือนเดิม) ...

# ======================= SEC 5: SAVE PLAN & DRAWDOWN LOCK =======================
# ... (โค้ด Save Plan และ Drawdown Lock ของคุณเหมือนเดิม) ...

# ======================= SEC 6: LOG VIEWER (แผนเทรด) =======================
# ... (โค้ด Log Viewer ของคุณเหมือนเดิม) ...


# ======================= SEC 7: Ultimate Statement Import & Auto-Mapping =======================
with st.expander("📂 SEC 7: Ultimate Statement Import & Auto-Mapping", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # 7.1. Session State Initialization
    if 'all_statement_data' not in st.session_state:
        st.session_state.all_statement_data = {}
        st.session_state.df_stmt_current = pd.DataFrame()

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement (CSV/XLSX) เพื่อประมวลผลและบันทึก")
    
    uploaded_files = st.file_uploader(
        "ลากและวางไฟล์ Statement ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["xlsx", "csv"],
        accept_multiple_files=True,
        key="sec7_file_uploader" # เปลี่ยน key เพื่อไม่ให้ซ้ำกับ uploader อื่น
    )

    # 7.2. Debug Mode Checkbox
    if 'sec7_debug_mode' not in st.session_state: # ใช้ key แยกสำหรับ debug mode ส่วนนี้
        st.session_state.sec7_debug_mode = False
    st.session_state.sec7_debug_mode = st.checkbox("⚙️ เปิดโหมด Debug (SEC 7)", value=st.session_state.sec7_debug_mode, key="sec7_debug_checkbox")
    
    # 7.3. Data Extraction Function
    def extract_data_from_report(file_buffer, stat_definitions_arg):
        df_raw = None
        try:
            file_buffer.seek(0)
            if file_buffer.name.endswith('.csv'):
                df_raw = pd.read_csv(file_buffer, header=None, low_memory=False)
            elif file_buffer.name.endswith('.xlsx'):
                df_raw = pd.read_excel(file_buffer, header=None, engine='openpyxl')
        except Exception as e:
            st.error(f"SEC 7: เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
            return None

        if df_raw is None or df_raw.empty:
            st.warning("SEC 7: ไม่สามารถอ่านข้อมูลจากไฟล์ได้ หรือไฟล์ว่างเปล่า")
            return None

        section_starts = {}
        section_keywords = ["Positions", "Orders", "Deals", "History", "Results"]
        for keyword in section_keywords:
            if keyword not in section_starts:
                for r_idx, row in df_raw.iterrows():
                    if row.astype(str).str.contains(keyword, case=False, regex=False).any():
                        actual_key = "Deals" if keyword == "History" else keyword
                        if actual_key not in section_starts:
                            section_starts[actual_key] = r_idx
                        break
        
        extracted_data = {}
        sorted_sections = sorted(section_starts.items(), key=lambda x: x[1])

        tabular_keywords = ["Positions", "Orders", "Deals"]
        for i, (section_name, start_row) in enumerate(sorted_sections):
            if section_name not in tabular_keywords:
                continue
            header_row_idx = start_row + 1
            while header_row_idx < len(df_raw) and df_raw.iloc[header_row_idx].isnull().all():
                header_row_idx += 1
            if header_row_idx < len(df_raw):
                headers = [str(h).strip() for h in df_raw.iloc[header_row_idx] if pd.notna(h) and str(h).strip() != '']
                data_start_row = header_row_idx + 1
                end_row = len(df_raw)
                if i + 1 < len(sorted_sections):
                    end_row = sorted_sections[i+1][1]
                df_section = df_raw.iloc[data_start_row:end_row].copy().dropna(how='all')
                if not df_section.empty:
                    num_data_cols = df_section.shape[1]
                    final_headers = headers[:num_data_cols]
                    if len(final_headers) < num_data_cols:
                        final_headers.extend([f'Unnamed:{j}' for j in range(len(final_headers), num_data_cols)])
                    df_section.columns = final_headers
                    extracted_data[section_name.lower()] = df_section

        if "Results" in section_starts:
            results_stats = {}
            start_row = section_starts["Results"]
            results_df = df_raw.iloc[start_row : start_row + 15] # Scan 15 rows
            for _, row in results_df.iterrows():
                for c_idx, cell in enumerate(row):
                    if pd.notna(cell):
                        label = str(cell).strip().replace(':', '')
                        if label in stat_definitions_arg: # ใช้ stat_definitions_arg ที่รับมา
                            for k in range(1, 4):
                                if (c_idx + k) < len(row):
                                    value = row.iloc[c_idx + k]
                                    if pd.notna(value) and str(value).strip() != "":
                                        clean_value = str(value).split('(')[0].strip() # Clean "123 (xxx)"
                                        results_stats[label] = clean_value
                                        break 
                            break 
            if results_stats:
                extracted_data["balance_summary"] = pd.DataFrame(list(results_stats.items()), columns=['Metric', 'Value'])
        return extracted_data

    # 7.4. Define stat_definitions (Moved outside loop, before function call)
    stat_definitions = {
        "Total Net Profit", "Gross Profit", "Gross Loss", "Profit Factor", "Expected Payoff", "Recovery Factor",
        "Sharpe Ratio", "Balance Drawdown Absolute", "Balance Drawdown Maximal", "Balance Drawdown Relative",
        "Total Trades", "Short Trades (won %)", "Long Trades (won %)", "Profit Trades (% of total)", 
        "Loss Trades (% of total)", "Largest profit trade", "Largest loss trade", "Average profit trade", 
        "Average loss trade", "Maximum consecutive wins ($)", "Maximal consecutive profit (count)",
        "Average consecutive wins", "Maximum consecutive losses ($)", "Maximal consecutive loss (count)", 
        "Average consecutive losses"
    }

    # 7.5. Process Uploaded Files
    if uploaded_files:
        for uploaded_file_item in uploaded_files: # เปลี่ยนชื่อตัวแปรไม่ให้ซ้ำ
            st.info(f"กำลังประมวลผลไฟล์: {uploaded_file_item.name}")
            with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {uploaded_file_item.name}..."):
                extracted_data = extract_data_from_report(uploaded_file_item, stat_definitions)
                
                if extracted_data:
                    st.success(f"ประมวลผลสำเร็จ! พบข้อมูลในส่วน: {', '.join(extracted_data.keys())}")

                    if 'deals' in extracted_data:
                        st.session_state.df_stmt_current = extracted_data['deals'].copy()
                    
                    for key, df_item in extracted_data.items(): # เปลี่ยนชื่อตัวแปร
                        st.session_state.all_statement_data[key] = df_item.copy()

                    if 'balance_summary' in extracted_data:
                        st.write("### 📊 Balance Summary (SEC 7)")
                        st.dataframe(extracted_data['balance_summary'])
                    
                    if st.session_state.sec7_debug_mode:
                        for section_key, section_df_item in extracted_data.items(): # เปลี่ยนชื่อตัวแปร
                            if section_key != 'balance_summary':
                                st.write(f"### 📄 ข้อมูลส่วน (SEC 7): {section_key.replace('_', ' ').title()}")
                                st.dataframe(section_df_item)
                else:
                    st.warning(f"ไม่สามารถแยกส่วนข้อมูลใดๆ จากไฟล์ {uploaded_file_item.name} ได้")
    else:
        st.info("ยังไม่มีไฟล์ Statement อัปโหลด (SEC 7)")

    # 7.6. Display Current Statement & Clear Button
    st.markdown("---")
    st.subheader("📁 ข้อมูล Statement ที่ถูกโหลดและประมวลผลล่าสุด (Deals - SEC 7)")
    st.dataframe(st.session_state.df_stmt_current)

    if st.button("🗑️ ล้างข้อมูล Statement ที่โหลดทั้งหมด (SEC 7)", key="sec7_clear_button"):
        st.session_state.all_statement_data = {}
        st.session_state.df_stmt_current = pd.DataFrame()
        st.success("ล้างข้อมูล Statement ทั้งหมดแล้ว (SEC 7)")
        st.rerun()


# ======================= SEC 8: AI SUMMARY & INSIGHT =======================
# ... (โค้ด AI Assistant ของคุณ โดยมีการ clean data คล้าย SEC 9) ...

# ======================= SEC 9: DASHBOARD + AI ULTIMATE =======================
# 9.1. Data Loading Function for Dashboard
def load_data_for_dashboard():
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด",
        ["Log File (แผน)", "Statement Import (ของจริง)"],
        index=0, # Default to Log File
        key="dashboard_source_select"
    )
    if source_option == "Log File (แผน)":
        if os.path.exists(log_file):
            try:
                df_dashboard_data = pd.read_csv(log_file)
            except Exception as e:
                st.error(f"SEC 9: ไม่สามารถโหลด Log File: {e}")
                df_dashboard_data = pd.DataFrame()
        else:
            st.info("SEC 9: ไม่พบ Log File สำหรับ Dashboard.")
            df_dashboard_data = pd.DataFrame()
    else: # Statement Import (ของจริง)
        df_dashboard_data = st.session_state.get('df_stmt_current', pd.DataFrame())
        if df_dashboard_data.empty:
            st.info("SEC 9: ไม่มีข้อมูล Statement สำหรับ Dashboard (โปรดอัปโหลดใน SEC 7).")
    return df_dashboard_data

with st.expander("📊 Performance Dashboard (SEC 9)", expanded=True):
    df_data = load_data_for_dashboard()

    # 9.2. Dashboard Tabs
    tab_dashboard, tab_rr, tab_lot, tab_time, tab_ai_dash, tab_export = st.tabs([
        "📊 Dashboard", "📈 RR", "📉 Lot Size", "🕒 Time", "🤖 AI", "⬇️ Export"
    ])

    # --- Utility function for cleaning data within dashboard tabs ---
    def clean_dashboard_data(df_input, profit_col_name='Profit', risk_col_name='Risk $', rr_col_name='RR', lot_col_name='Lot'):
        df = df_input.copy()
        # Identify actual profit/risk column
        actual_profit_col = None
        if profit_col_name in df.columns:
            actual_profit_col = profit_col_name
        elif risk_col_name in df.columns:
            actual_profit_col = risk_col_name
        
        if actual_profit_col:
            df[actual_profit_col] = pd.to_numeric(df[actual_profit_col], errors='coerce').fillna(0)

        if rr_col_name in df.columns:
            df[rr_col_name] = pd.to_numeric(df[rr_col_name], errors='coerce').fillna(0)
        if lot_col_name in df.columns:
            df[lot_col_name] = pd.to_numeric(df[lot_col_name], errors='coerce').fillna(0)
        return df, actual_profit_col

    if df_data.empty:
        st.info("SEC 9: ยังไม่มีข้อมูลสำหรับ Dashboard")
    else:
        df_data, identified_profit_col = clean_dashboard_data(df_data)

        with tab_dashboard:
            # 9.2.1. Asset Filter
            asset_col_options = [col for col in ["Asset", "Symbol"] if col in df_data.columns]
            if asset_col_options:
                selected_asset_col = asset_col_options[0]
                unique_assets = ["ทั้งหมด"] + sorted(df_data[selected_asset_col].dropna().unique())
                selected_asset = st.selectbox(
                    f"🎯 Filter by {selected_asset_col}", 
                    unique_assets, 
                    key="dashboard_asset_filter"
                )
                if selected_asset != "ทั้งหมด":
                    df_data_filtered = df_data[df_data[selected_asset_col] == selected_asset]
                else:
                    df_data_filtered = df_data
            else:
                st.warning("SEC 9: ไม่พบคอลัมน์ 'Asset' หรือ 'Symbol' สำหรับการกรอง")
                df_data_filtered = df_data # Use unfiltered data if no asset column

            if identified_profit_col:
                st.markdown("### 🥧 Pie Chart: Win/Loss")
                win_count = df_data_filtered[df_data_filtered[identified_profit_col] > 0].shape[0]
                loss_count = df_data_filtered[df_data_filtered[identified_profit_col] <= 0].shape[0]
                pie_df = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count, loss_count]})
                if win_count > 0 or loss_count > 0:
                    pie_chart = px.pie(pie_df, names="Result", values="Count", color="Result",
                                    color_discrete_map={"Win": "green", "Loss": "red"})
                    st.plotly_chart(pie_chart, use_container_width=True)
                else:
                    st.info("SEC 9: ไม่มีข้อมูล Win/Loss สำหรับ Pie Chart.")

                st.markdown("### 📊 Bar Chart: กำไร/ขาดทุนแต่ละวัน")
                date_col_options = [col for col in ["Timestamp", "Date", "Open Time", "Close Time"] if col in df_data_filtered.columns]
                if date_col_options:
                    date_col = date_col_options[0]
                    df_bar = df_data_filtered.copy()
                    df_bar["TradeDate"] = pd.to_datetime(df_bar[date_col], errors='coerce').dt.date
                    bar_df_grouped = df_bar.groupby("TradeDate")[identified_profit_col].sum().reset_index(name="Profit/Loss")
                    if not bar_df_grouped.empty:
                        bar_chart = px.bar(bar_df_grouped, x="TradeDate", y="Profit/Loss", 
                                           color="Profit/Loss", color_continuous_scale=["red", "orange", "green"])
                        st.plotly_chart(bar_chart, use_container_width=True)
                    else:
                        st.info("SEC 9: ไม่มีข้อมูลสำหรับ Bar Chart หลังจากการ Group by.")
                else:
                    st.warning("SEC 9: ไม่พบคอลัมน์วันที่/เวลาสำหรับ Bar Chart")

                st.markdown("### 📈 Timeline: Balance Curve")
                if date_col_options: # Assuming date_col is defined from above
                    date_col = date_col_options[0]
                    df_balance = df_data_filtered.copy()
                    df_balance["TradeDateFull"] = pd.to_datetime(df_balance[date_col], errors='coerce')
                    df_balance = df_balance.sort_values(by="TradeDateFull")
                    df_balance["Balance"] = acc_balance + df_balance[identified_profit_col].cumsum()
                    if not df_balance.empty:
                        timeline_chart = px.line(df_balance, x="TradeDateFull", y="Balance", markers=True, title="Balance Curve")
                        st.plotly_chart(timeline_chart, use_container_width=True)
                    else:
                        st.info("SEC 9: ไม่มีข้อมูลสำหรับ Balance Curve.")
                else:
                     st.warning("SEC 9: ไม่พบคอลัมน์วันที่/เวลาสำหรับ Balance Curve")
            else:
                st.warning("SEC 9 Dashboard: ไม่พบคอลัมน์ Profit หรือ Risk $ ที่จะใช้คำนวณ")
        
        with tab_rr:
            if "RR" in df_data.columns:
                rr_data_numeric = pd.to_numeric(df_data["RR"], errors='coerce').dropna()
                if not rr_data_numeric.empty:
                    st.markdown("#### RR Histogram")
                    fig_rr = px.histogram(rr_data_numeric, nbins=20, title="RR Distribution")
                    st.plotly_chart(fig_rr, use_container_width=True)
                else:
                    st.info("SEC 9: ไม่มีข้อมูล RR ที่ถูกต้องสำหรับ Histogram")
            else:
                st.warning("SEC 9: ไม่พบคอลัมน์ 'RR' ในข้อมูล")

        with tab_lot:
            if "Lot" in df_data.columns and date_col_options:
                date_col = date_col_options[0]
                df_lot = df_data.copy()
                df_lot["TradeDateFull"] = pd.to_datetime(df_lot[date_col], errors='coerce')
                df_lot = df_lot.sort_values(by="TradeDateFull")
                lot_data_numeric = pd.to_numeric(df_lot["Lot"], errors='coerce').dropna()

                if not lot_data_numeric.empty and not df_lot["TradeDateFull"].dropna().empty:
                    st.markdown("#### Lot Size Evolution")
                    fig_lot = px.line(df_lot.dropna(subset=["TradeDateFull", "Lot"]), 
                                      x="TradeDateFull", y="Lot", markers=True, title="Lot Size Over Time")
                    st.plotly_chart(fig_lot, use_container_width=True)
                else:
                    st.info("SEC 9: ไม่มีข้อมูล Lot หรือ วันที่ ที่ถูกต้องสำหรับกราฟ")
            else:
                st.warning("SEC 9: ไม่พบคอลัมน์ 'Lot' หรือคอลัมน์วันที่ในข้อมูล")
        
        with tab_time:
            if date_col_options and identified_profit_col:
                date_col = date_col_options[0]
                df_time = df_data.copy()
                df_time["TradeDateFull"] = pd.to_datetime(df_time[date_col], errors='coerce')
                df_time["Weekday"] = df_time["TradeDateFull"].dt.day_name()
                weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                weekday_profit = df_time.groupby("Weekday")[identified_profit_col].sum().reindex(weekday_order).reset_index()
                if not weekday_profit.empty:
                    st.markdown("#### Profit/Loss by Weekday")
                    fig_weekday = px.bar(weekday_profit, x="Weekday", y=identified_profit_col, title="Total Profit/Loss by Weekday")
                    st.plotly_chart(fig_weekday, use_container_width=True)
                else:
                    st.info("SEC 9: ไม่มีข้อมูลสำหรับวิเคราะห์ตามวัน")
            else:
                st.warning("SEC 9: ไม่พบคอลัมน์วันที่ หรือ Profit/Risk $ สำหรับวิเคราะห์ตามวัน")

        with tab_ai_dash: # Changed tab key to avoid conflict
            st.markdown("### 🤖 AI Recommendation (Dashboard)")
            if identified_profit_col:
                total_trades_dash = df_data.shape[0]
                win_trades_dash = df_data[df_data[identified_profit_col] > 0].shape[0]
                winrate_dash = (100 * win_trades_dash / total_trades_dash) if total_trades_dash > 0 else 0
                gross_profit_dash = df_data[identified_profit_col].sum()
                st.write(f"Total Trades: {total_trades_dash}, Winrate: {winrate_dash:.2f}%, Gross P/L: {gross_profit_dash:,.2f}")
                # ... (ส่วน AI Insight และ Gemini API call ถ้าจะใช้) ...
            else:
                st.warning("SEC 9 AI: ไม่พบคอลัมน์ Profit หรือ Risk $")

        with tab_export:
            st.markdown("### ⬇️ Export/Download Report")
            if not df_data.empty:
                csv_export = df_data.to_csv(index=False).encode('utf-8')
                st.download_button("Download Report (CSV)", csv_export, "dashboard_report.csv", "text/csv")
            else:
                st.info("SEC 9: ไม่มีข้อมูลสำหรับ Export")

# หมายเหตุ: โค้ดส่วนอื่นๆ เช่น SEC 8 (AI Assistant เดิม) ไม่ได้ถูกรวมไว้ในนี้
# ถ้าคุณมี SEC อื่นๆ ที่ต้องการให้ผมดู สามารถส่งมาเพิ่มเติมได้ครับ
