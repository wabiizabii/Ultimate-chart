# ======================= SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import openpyxl  
import numpy as np
import os
from datetime import datetime
import plotly.express as px
import google.generativeai as genai
import gspread # <--- เพิ่ม import gspread ที่นี่

st.set_page_config(page_title="Ultimate-Chart", layout="wide")
acc_balance = 10000 
log_file = "trade_log.csv"


# กำหนดชื่อ Google Sheet และ Worksheet ที่จะใช้เก็บข้อมูล Statement
GOOGLE_SHEET_NAME = "TradeLog" # **เปลี่ยนเป็นชื่อ Google Sheet ของคุณ**
GOOGLE_WORKSHEET_NAME = "Uploaded Statements" # ชื่อ Worksheet ที่จะใช้เก็บ Statement

# ฟังก์ชันสำหรับเชื่อมต่อ gspread
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

# ฟังก์ชันสำหรับอ่านข้อมูล Statement จาก Google Sheets
import pandas as pd # <-- ตรวจสอบให้แน่ใจว่ามีบรรทัดนี้อยู่ด้านบนสุดของไฟล์ main.py
import gspread     # <-- ตรวจสอบให้แน่ใจว่ามีบรรทัดนี้อยู่ด้านบนสุดของไฟล์ main.py
import streamlit as st # <-- ตรวจสอบให้แน่ใจว่ามีบรรทัดนี้อยู่ด้านบนสุดของไฟล์ main.py

@st.cache_data(ttl=3600)
def load_statement_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        return {}

    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        try:
            worksheet = sh.worksheet(GOOGLE_WORKSHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            st.info(f"✨ กำลังสร้าง Worksheet '{GOOGLE_WORKSHEET_NAME}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'...")
            worksheet = sh.add_worksheet(title=GOOGLE_WORKSHEET_NAME, rows="1", cols="1")
            return {}

        all_sheet_values = worksheet.get_all_values()

        if not all_sheet_values or len(all_sheet_values) < 2:
            st.info(f"Worksheet '{GOOGLE_WORKSHEET_NAME}' ว่างเปล่าหรือมีข้อมูลน้อยเกินไป.")
            return {}

        parser_config = {
            "positions": {
                "start_keyword": "Positions",
                "header_row_offset": 1, 
                "end_keyword": "Orders"
            },
            "orders": {
                "start_keyword": "Orders",
                "header_row_offset": 1,
                "end_keyword": "Deals"
            },
            "deals": {
                "start_keyword": "Deals",
                "header_row_offset": 1,
                "end_keyword": "Balance" 
            },
            "balance_summary": { # เพิ่มส่วนนี้ตามที่คุณต้องการ
                "start_keyword": "Balance",
                "header_row_offset": 0, # หรืออาจจะเป็น 1 ถ้าหัวตารางไม่ได้อยู่บรรทัดเดียวกับ Balance
                "end_keyword": "Drawdown"
            },
            # *** สำคัญ: คุณสามารถเพิ่มส่วนอื่นๆ ที่คุณต้องการได้ที่นี่ ***
            # โดยการดูจาก Statement ของคุณว่ามี Keyword อะไรที่ใช้ระบุส่วนนั้น
            # และหัวตารางอยู่ห่างจาก Keyword นั้นกี่บรรทัด (header_row_offset)
            # และส่วนนั้นสิ้นสุดที่ Keyword อะไร (end_keyword)
        }

        all_sections_dfs = {}
        st.write("--- กำลังแยกส่วนข้อมูล ---")

        for section_name, config in parser_config.items():
            start_row_idx = -1
            end_row_idx = -1

            for i, row in enumerate(all_sheet_values):
                # ค้นหา start_keyword ในแถว อาจจะอยู่ในคอลัมน์แรก หรือคอลัมน์อื่น
                # ใช้ " ".join(row) เพื่อรวมคอลัมน์ในแถวนั้นเป็น string เดียวแล้วค้นหา
                if config["start_keyword"] in " ".join(row): 
                    start_row_idx = i
                    break

            if start_row_idx == -1:
                st.warning(f"⚠️ ไม่พบส่วน '{section_name}' ด้วย keyword: '{config['start_keyword']}'.")
                continue

            if "end_keyword" in config and config["end_keyword"]:
                for i in range(start_row_idx + 1, len(all_sheet_values)):
                    if config["end_keyword"] in " ".join(all_sheet_values[i]):
                        end_row_idx = i
                        break

            if end_row_idx == -1:
                end_row_idx = len(all_sheet_values)

            header_row_actual_idx = start_row_idx + config["header_row_offset"]

            if header_row_actual_idx >= len(all_sheet_values):
                st.warning(f"⚠️ หัวตารางของส่วน '{section_name}' เกินขอบเขต. ข้ามส่วนนี้.")
                continue

            header = all_sheet_values[header_row_actual_idx]
            clean_header = [h for h in header if h.strip() != '']

            if not clean_header:
                st.warning(f"⚠️ ไม่พบหัวตารางที่ถูกต้องสำหรับส่วน '{section_name}'. ข้ามส่วนนี้.")
                continue

            # หาตำแหน่งของคอลัมน์ที่ไม่ว่างใน header เพื่อใช้ตัดข้อมูล
            # และตรวจสอบว่าคอลัมน์ว่างเหล่านั้นเป็นแค่ช่องว่างหรือคอลัมน์ที่ไม่มีข้อมูลจริงๆ
            col_indices = []
            for i, h_val in enumerate(header):
                if h_val.strip() != '':
                    col_indices.append(i)
                elif len(col_indices) > 0 and (i - col_indices[-1] == 1): # ถ้าเป็นคอลัมน์ว่างถัดจากคอลัมน์ที่มีข้อมูล
                    # อาจจะเกิดจากการรวมเซลล์ใน Excel
                    # ให้ลองดูว่าคอลัมน์ถัดไปเป็นส่วนหนึ่งของหัวตารางหรือไม่
                    # แต่สำหรับตอนนี้ เราจะพึ่ง clean_header ที่ไม่รวมคอลัมน์ว่างเลย
                    pass


            section_raw_data = []
            for row_idx in range(header_row_actual_idx + 1, end_row_idx):
                current_row = all_sheet_values[row_idx]
                if not any(c.strip() for c in current_row):
                    break

                # ตัดข้อมูลตามคอลัมน์ที่มีใน clean_header
                truncated_row = [current_row[idx] if idx < len(current_row) else '' for idx in col_indices]
                section_raw_data.append(truncated_row)

            if section_raw_data:
                df_section = pd.DataFrame(section_raw_data, columns=clean_header)
                df_section.replace('', pd.NA, inplace=True)
                df_section.dropna(how='all', inplace=True)

                if not df_section.empty:
                    all_sections_dfs[section_name] = df_section
                    st.success(f"โหลดข้อมูลส่วน '{section_name}' สำเร็จ ({len(df_section)} แถว).")
                else:
                    st.info(f"ส่วน '{section_name}' มีข้อมูลแต่ไม่สามารถประมวลผลเป็น DataFrame ได้.")
            else:
                st.info(f"ไม่พบข้อมูลสำหรับส่วน '{section_name}'.")

        if all_sections_dfs:
            st.success(f"โหลดข้อมูล Statement ทั้งหมดจาก Google Sheet '{GOOGLE_SHEET_NAME}/{GOOGLE_WORKSHEET_NAME}' สำเร็จ!")
        else:
            st.warning("ไม่พบข้อมูลส่วนใดๆ ใน Google Sheet. โปรดตรวจสอบไฟล์ Statement และโครงสร้าง.")

        return all_sections_dfs

    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ ไม่พบ Google Sheet ชื่อ '{GOOGLE_SHEET_NAME}'. โปรดสร้างและแชร์กับ Service Account ของคุณ")
        return {}
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการโหลดข้อมูล Statement จาก Google Sheets: {e}")
        st.exception(e)
        return {}

# ฟังก์ชันสำหรับบันทึก DataFrame ลง Google Sheets (แทนที่ข้อมูลเก่า)
# (โค้ดส่วนอื่น ๆ ของคุณอยู่เหมือนเดิม)

def save_statement_to_gsheets(df_to_save):
    if df_to_save.empty:
        st.warning("ไม่มีข้อมูลที่จะบันทึกไปยัง Google Sheets.")
        return

    gc = get_gspread_client()
    if gc is None:
        return

    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        try:
            worksheet = sh.worksheet(GOOGLE_WORKSHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            st.info(f"✨ สร้าง Worksheet '{GOOGLE_WORKSHEET_NAME}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'")
            worksheet = sh.add_worksheet(title=GOOGLE_WORKSHEET_NAME, rows="1", cols="1")

        # --- เพิ่มส่วนนี้เข้ามา ---
        df_to_save_str = df_to_save.copy()
        for col in df_to_save_str.columns:
            if pd.api.types.is_datetime64_any_dtype(df_to_save_str[col]):
                df_to_save_str[col] = df_to_save_str[col].dt.strftime('%Y-%m-%d %H:%M:%S')
        # --- สิ้นสุดส่วนที่เพิ่ม ---

        worksheet.clear()
        worksheet.update([df_to_save_str.columns.values.tolist()] + df_to_save_str.astype(str).values.tolist())
        st.success(f"บันทึกข้อมูล Statement ไปยัง Google Sheet '{GOOGLE_SHEET_NAME}/{GOOGLE_WORKSHEET_NAME}' เรียบร้อยแล้ว!")
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล Statement ไปยัง Google Sheets: {e}")
        st.exception(e) # ให้คงบรรทัดนี้ไว้ เผื่อยังมี Error อื่น
        # แต่ถ้ามี st.stop() อยู่ ให้เอา # ใส่ข้างหน้า หรือลบทิ้งครับ เช่น
        # # st.stop()

# (โค้ดส่วนอื่น ๆ ของคุณอยู่เหมือนเดิม)
# ======================= SEC 0.8: PORTFOLIO SETUP & MANAGEMENT =======================
# (วางโค้ดนี้ต่อจาก SEC 0 หรือส่วน Function Definitions ของคุณ)

PORTFOLIO_FILE = 'portfolios.csv'

# 0.8.1. Function to load portfolios
def load_portfolios():
    if os.path.exists(PORTFOLIO_FILE):
        try:
            df = pd.read_csv(PORTFOLIO_FILE)
            # ตรวจสอบว่ามีคอลัมน์ที่จำเป็นหรือไม่ ถ้าไม่มีให้สร้าง DataFrame โครงสร้างใหม่
            if not {'portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'}.issubset(df.columns):
                st.warning(f"ไฟล์ {PORTFOLIO_FILE} มีโครงสร้างไม่ถูกต้อง กำลังสร้าง DataFrame ใหม่")
                return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
            return df
        except pd.errors.EmptyDataError: # กรณีไฟล์มีอยู่แต่ว่างเปล่า
             st.info(f"ไฟล์ {PORTFOLIO_FILE} ว่างเปล่า กำลังสร้าง DataFrame ใหม่")
             return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการโหลด {PORTFOLIO_FILE}: {e}")
            return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])
    else:
        return pd.DataFrame(columns=['portfolio_id', 'portfolio_name', 'initial_balance', 'creation_date'])

# 0.8.2. Function to save portfolios
def save_portfolios(df):
    try:
        df.to_csv(PORTFOLIO_FILE, index=False)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการบันทึก {PORTFOLIO_FILE}: {e}")

# --- โหลดข้อมูลพอร์ตทั้งหมดที่มี ---
portfolios_df = load_portfolios()

# --- ส่วน UI สำหรับเลือก Active Portfolio (จะแสดงใน Sidebar) ---
st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

if not portfolios_df.empty:
    portfolio_names = portfolios_df['portfolio_name'].tolist()
    
    # ถ้ายังไม่มี active_portfolio_name ใน session_state หรือพอร์ตที่เคยเลือกไว้ถูกลบไปแล้ว
    # ให้เลือกพอร์ตแรกเป็น default
    current_active_portfolio = st.session_state.get('active_portfolio_name', None)
    if current_active_portfolio not in portfolio_names:
        st.session_state.active_portfolio_name = portfolio_names[0] if portfolio_names else None

    # สร้าง selectbox
    st.session_state.active_portfolio_name = st.sidebar.selectbox(
        "เลือกพอร์ต:",
        options=portfolio_names,
        index=portfolio_names.index(st.session_state.active_portfolio_name) if st.session_state.active_portfolio_name in portfolio_names else 0,
        key='sb_active_portfolio_selector'
    )
    st.sidebar.success(f"Active Portfolio: **{st.session_state.active_portfolio_name}**")
else:
    st.sidebar.info("ยังไม่มีพอร์ต กรุณาเพิ่มพอร์ตในหน้า 'จัดการพอร์ต'")
    st.session_state.active_portfolio_name = None # ตั้งเป็น None ถ้าไม่มีพอร์ตให้เลือก

# --- ส่วน UI สำหรับจัดการพอร์ต (แสดงเป็น Expander หรือหน้าแยกก็ได้) ---
with st.expander("💼 จัดการพอร์ต (เพิ่ม/ดูพอร์ต)"):
    st.subheader("พอร์ตทั้งหมดของคุณ")
    if portfolios_df.empty:
        st.info("ยังไม่มีการสร้างพอร์ต โปรดเพิ่มพอร์ตใหม่ด้านล่าง")
    else:
        st.dataframe(portfolios_df, use_container_width=True, hide_index=True)

    st.subheader("➕ เพิ่มพอร์ตใหม่")
    with st.form("new_portfolio_form", clear_on_submit=True):
        new_portfolio_name = st.text_input("ชื่อพอร์ต (เช่น My Personal, FTMO Challenge)")
        new_initial_balance = st.number_input("บาลานซ์เริ่มต้น ($)", min_value=0.0, value=10000.0, step=100.0, format="%.2f")
        
        submitted_add_portfolio = st.form_submit_button("💾 บันทึกพอร์ตใหม่")
        
        if submitted_add_portfolio:
            if not new_portfolio_name:
                st.warning("กรุณาใส่ชื่อพอร์ต")
            elif new_portfolio_name in portfolios_df['portfolio_name'].values:
                st.error(f"ชื่อพอร์ต '{new_portfolio_name}' มีอยู่แล้ว กรุณาใช้ชื่ออื่น")
            else:
                if portfolios_df.empty or 'portfolio_id' not in portfolios_df.columns or portfolios_df['portfolio_id'].empty:
                    new_id = 1
                else:
                    new_id = portfolios_df['portfolio_id'].max() + 1 if pd.notna(portfolios_df['portfolio_id'].max()) else 1

                
                new_portfolio_data = pd.DataFrame([{
                    'portfolio_id': int(new_id),
                    'portfolio_name': new_portfolio_name,
                    'initial_balance': new_initial_balance,
                    'creation_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }])
                
                updated_portfolios_df = pd.concat([portfolios_df, new_portfolio_data], ignore_index=True)
                save_portfolios(updated_portfolios_df)
                st.success(f"เพิ่มพอร์ต '{new_portfolio_name}' สำเร็จ!")
                # อัปเดต active_portfolio_name เป็นพอร์ตที่เพิ่งสร้าง ถ้ายังไม่มีพอร์ตอื่น
                if st.session_state.active_portfolio_name is None:
                    st.session_state.active_portfolio_name = new_portfolio_name
                st.rerun()

# ========== Function Utility ==========
def get_today_drawdown(log_file, acc_balance):
    if not os.path.exists(log_file):
        return 0
    df = pd.read_csv(log_file)
    today_str = datetime.now().strftime("%Y-%m-%d")
    if "Timestamp" not in df.columns or "Risk $" not in df.columns:
        return 0
    df_today = df[df["Timestamp"].str.startswith(today_str)]
    try:
        drawdown = df_today["Risk $"].astype(float).sum()
    except Exception:
        drawdown = 0
    return drawdown

def get_performance(log_file, mode="week"):
    if not os.path.exists(log_file):
        return 0, 0, 0
    df = pd.read_csv(log_file)
    if "Timestamp" not in df.columns or "Risk $" not in df.columns:
        return 0, 0, 0
    now = datetime.now()
    if mode == "week":
        week_start = (now - pd.Timedelta(days=now.weekday())).strftime("%Y-%m-%d")
        df_period = df[df["Timestamp"] >= week_start]
    else:  # month
        month_start = now.strftime("%Y-%m-01")
        df_period = df[df["Timestamp"] >= month_start]
    win = df_period[df_period["Risk $"].astype(float) > 0].shape[0]
    loss = df_period[df_period["Risk $"].astype(float) <= 0].shape[0]
    total = win + loss if (win + loss) > 0 else 1
    winrate = 100 * win / total
    gain = df_period["Risk $"].astype(float).sum()
    return winrate, gain, total

# ======================= SEC 1: SIDEBAR / INPUT ZONE =======================

st.sidebar.header("🎛️ Trade Setup")

drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=2.0, step=0.1, format="%.1f"
)

mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")


if st.sidebar.button("🔄 Reset Form"):
    risk_keep = st.session_state.get("risk_pct", 1.0)
    asset_keep = st.session_state.get("asset", "XAUUSD")

    # เคลียร์ทุก key ยกเว้น risk_pct กับ asset
    keys_to_keep = {"risk_pct", "asset"}
    keys_to_delete = [k for k in list(st.session_state.keys()) if k not in keys_to_keep]

    for k in keys_to_delete:
        del st.session_state[k]

    st.session_state["risk_pct"] = risk_keep
    st.session_state["asset"] = asset_keep

    # 👇 ส่วนที่เพิ่มเข้าไปเพื่อ “ล้าง FIBO checkbox”
    st.session_state["fibo_flags"] = [False, False, False, False, False]

    st.rerun()


# -- Input Zone (แยก FIBO/CUSTOM) --
# ======================= SEC 1: SIDEBAR / INPUT ZONE (FIBO) =======================
if mode == "FIBO":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            step=0.01,
            format="%.2f",
            key="risk_pct"
        )
    with col3:
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True)

    col4, col5 = st.sidebar.columns(2)
    with col4:
        swing_high = st.text_input("High", key="swing_high")
    with col5:
        swing_low = st.text_input("Low", key="swing_low")

    # 📐 Entry Fibo Levels (ใช้ร่วมกับ Reset Form ได้)
    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibos = [0.114, 0.25, 0.382, 0.5, 0.618]
    labels = [f"{l:.3f}" for l in fibos]
    cols = st.sidebar.columns(len(fibos))

    # ตั้งค่า flags ถ้ายังไม่มี
    if "fibo_flags" not in st.session_state:
        st.session_state.fibo_flags = [True] * len(fibos)

    fibo_selected = []
    for i, col in enumerate(cols):
        checked = col.checkbox(labels[i], value=st.session_state.fibo_flags[i])
        fibo_selected.append(checked)

    st.session_state.fibo_flags = fibo_selected

    try:
        high = float(swing_high)
        low = float(swing_low)
        if high <= low:
            st.sidebar.warning("High ต้องมากกว่า Low!")
    except Exception:
        pass

    if risk_pct <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")

    st.sidebar.markdown("---")
    try:
        high = float(swing_high)
        low = float(swing_low)
        if high > low:
            st.sidebar.markdown("**Preview (เบื้องต้น):**")
            if direction == "Long":
                preview_entry = low + (high - low) * fibos[0]
            else:
                preview_entry = high - (high - low) * fibos[0]
            st.sidebar.markdown(f"Entry แรกที่เลือก ≈ **{preview_entry:.2f}**")
            st.sidebar.caption("Lot/TP/ผลลัพธ์เต็มอยู่ด้านล่าง")
    except Exception:
        pass

    save_fibo = st.sidebar.button("Save Plan", key="save_fibo")



# ======================= SEC 1: SIDEBAR / INPUT ZONE (CUSTOM) =======================
elif mode == "CUSTOM":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value="XAUUSD", key="asset")
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            value=1.00,
            step=0.01,
            format="%.2f"
        )
    with col3:
        n_entry = st.number_input(
            "จำนวนไม้",
            min_value=1,
            max_value=10,
            value=2,
            step=1
        )

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")
    custom_inputs = []
    risk_per_trade = risk_pct / 100
    risk_dollar_total = acc_balance * risk_per_trade
    risk_dollar_per_entry = risk_dollar_total / n_entry if n_entry > 0 else 0
    for i in range(int(n_entry)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e, col_s, col_t = st.sidebar.columns(3)
        with col_e:
            entry = st.text_input(f"Entry {i+1}", value="0.00", key=f"custom_entry_{i}")
        with col_s:
            sl = st.text_input(f"SL {i+1}", value="0.00", key=f"custom_sl_{i}")
        with col_t:
            tp = st.text_input(f"TP {i+1}", value="0.00", key=f"custom_tp_{i}")
        try:
            entry_val = float(entry)
            sl_val = float(sl)
            stop = abs(entry_val - sl_val)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            lot_display = f"Lot: {lot:.2f}"
            risk_per_entry_display = f"Risk$ ต่อไม้: {risk_dollar_per_entry:.2f}"
        except Exception:
            lot_display = "Lot: -"
            risk_per_entry_display = "Risk$ ต่อไม้: -"
            stop = None
        try:
            if stop is not None and stop > 0:
                if 'direction' in locals() and direction == "Long": # This 'direction' would come from FIBO mode
                    tp_rr3 = entry_val + 3 * stop
                else: # Defaulting to Short if direction is not explicitly Long or not defined
                    tp_rr3 = entry_val - 3 * stop
                tp_rr3_display = f"TP ที่ RR=3: {tp_rr3:.2f}"
            else:
                tp_rr3_display = "TP ที่ RR=3: -"
        except Exception:
            tp_rr3_display = "TP ที่ RR=3: -"
        st.sidebar.caption(lot_display + " | " + risk_per_entry_display + " | " + tp_rr3_display)
        custom_inputs.append({"entry": entry, "sl": sl, "tp": tp})
    if risk_pct <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")
    save_custom = st.sidebar.button("Save Plan", key="save_custom")

# ======================= SEC 4: SUMMARY (ย้ายไป Sidebar) =======================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")

if mode == "FIBO":
    # FIBO Table Logic (คืนสูตร)
    try:
        high = float(swing_high)
        low = float(swing_low)
        selected_fibo_levels = [fibos[i] for i, sel in enumerate(fibo_selected) if sel]
        n = len(selected_fibo_levels)
        risk_per_trade = risk_pct / 100
        risk_dollar_total = acc_balance * risk_per_trade
        risk_dollar_per_entry = risk_dollar_total / n if n > 0 else 0
        entry_data = []
        for idx, fibo in enumerate(selected_fibo_levels):
            if direction == "Long":
                entry = low + (high - low) * fibo
                if abs(fibo - 0.5) < 1e-4:
                    sl = low + (high - low) * ((0.25 + 0.382)/2)
                elif abs(fibo - 0.618) < 1e-4:
                    sl = low + (high - low) * ((0.382 + 0.5)/2)
                else:
                    sl = low
            else:
                entry = high - (high - low) * fibo
                if abs(fibo - 0.5) < 1e-4:
                    sl = high - (high - low) * ((0.25 + 0.382)/2)
                elif abs(fibo - 0.618) < 1e-4:
                    sl = high - (high - low) * ((0.382 + 0.5)/2)
                else:
                    sl = high
            stop = abs(entry - sl)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            risk_val = round(stop * lot, 2)
            entry_data.append({
                "Fibo Level": f"{fibo:.3f}",
                "Entry": f"{entry:.2f}",
                "SL": f"{sl:.2f}",
                "Lot": f"{lot:.2f}",
                "Risk $": f"{risk_val:.2f}",
            })
        if entry_data:
            entry_df = pd.DataFrame(entry_data)
            st.sidebar.write(f"**Total Lots:** {np.sum(entry_df['Lot'].astype(float)):.2f}")
            st.sidebar.write(f"**Total Risk $:** {np.sum(entry_df['Risk $'].astype(float)):.2f}")
    except Exception:
        entry_data = []
elif mode == "CUSTOM":
    try:
        n_entry = int(n_entry)
        risk_per_trade = risk_pct / 100
        risk_dollar_total = acc_balance * risk_per_trade
        risk_dollar_per_entry = risk_dollar_total / n_entry if n_entry > 0 else 0
        custom_entries = []
        rr_list = []
        for i in range(n_entry):
            entry_val = float(custom_inputs[i]["entry"])
            sl_val = float(custom_inputs[i]["sl"])
            tp_val = float(custom_inputs[i]["tp"])
            stop = abs(entry_val - sl_val)
            target = abs(tp_val - entry_val)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            rr = (target / stop) if stop > 0 else 0
            rr_list.append(rr)
            custom_entries.append({
                "Entry": f"{entry_val:.2f}",
                "SL": f"{sl_val:.2f}",
                "TP": f"{tp_val:.2f}",
                "Lot": f"{lot:.2f}",
                "Risk $": f"{risk_dollar_per_entry:.2f}",
                "RR": f"{rr:.2f}"
            })
        if custom_entries:
            entry_df = pd.DataFrame(custom_entries)
            st.sidebar.write(f"**Total Lots:** {np.sum(entry_df['Lot'].astype(float)):.2f}")
            st.sidebar.write(f"**Total Risk $:** {np.sum(entry_df['Risk $'].astype(float)):.2f}")
            avg_rr = np.mean(rr_list) if len(rr_list) > 0 else None
            if avg_rr:
                st.sidebar.write(f"**Average RR:** {avg_rr:.2f}")
    except Exception:
        custom_entries = []

# ======================= SEC 1.x: SCALING MANAGER SETTINGS (EXPANDER, ท้าย SIDEBAR) =======================
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    scaling_step = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=1.0, value=0.25, step=0.01, format="%.2f"
    )
    min_risk_pct = st.number_input(
        "Minimum Risk %", min_value=0.01, max_value=100.0, value=0.5, step=0.01, format="%.2f"
    )
    max_risk_pct = st.number_input(
        "Maximum Risk %", min_value=0.01, max_value=100.0, value=5.0, step=0.01, format="%.2f"
    )
    scaling_mode = st.radio(
        "Scaling Mode", ["Manual", "Auto"], horizontal=True
    )

# ======================= SEC 1.5: SCALING SUGGESTION & CONFIRM =======================
winrate, gain, total = get_performance(log_file, mode="week")
current_risk = risk_pct

if winrate > 55 and gain > 0.02 * acc_balance:
    suggest_risk = min(current_risk + scaling_step, max_risk_pct)
    scaling_msg = f"🎉 ผลงานดี! Winrate {winrate:.1f}%, กำไร {gain:.2f} แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}"
elif winrate < 45 or gain < 0:
    suggest_risk = max(current_risk - scaling_step, min_risk_pct)
    scaling_msg = f"⚠️ ควรลด Risk%! Winrate {winrate:.1f}%, กำไร {gain:.2f} แนะนำลด Risk% เป็น {suggest_risk:.2f}"
else:
    suggest_risk = current_risk
    scaling_msg = "Risk% คงที่"

st.sidebar.info(scaling_msg)

if scaling_mode == "Manual" and suggest_risk != current_risk:
    if st.sidebar.button(f"ปรับ Risk% เป็น {suggest_risk:.2f}"):
        risk_pct = suggest_risk
elif scaling_mode == "Auto":
    risk_pct = suggest_risk

# ======================= SEC 2+3: MAIN AREA – ENTRY TABLE (FIBO/CUSTOM) =======================
with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):
    if mode == "FIBO":
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("### 🎯 Entry Levels")
            if 'entry_data' in locals() and entry_data: # Ensure entry_data is defined
                entry_df = pd.DataFrame(entry_data)
                st.dataframe(entry_df, hide_index=True, use_container_width=True)
            else:
                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level เพื่อดู Entry Levels.")
        with col2:
            st.markdown("### 🎯 Take Profit Zones")
            try:
                high = float(swing_high)
                low = float(swing_low)
                if high > low: # Ensure high is greater than low for valid calculation
                    if direction == "Long":
                        tp1 = low + (high - low) * 1.618
                        tp2 = low + (high - low) * 2.618
                        tp3 = low + (high - low) * 4.236
                    else:
                        tp1 = high - (high - low) * 1.618
                        tp2 = high - (high - low) * 2.618
                        tp3 = high - (high - low) * 4.236
                    tp_df = pd.DataFrame({
                        "TP": ["TP1", "TP2", "TP3"],
                        "Price": [f"{tp1:.2f}", f"{tp2:.2f}", f"{tp3:.2f}"]
                    })
                    st.dataframe(tp_df, hide_index=True, use_container_width=True)
                else:
                    st.warning("📌 Define High and Low correctly to unlock your TP projection.")
            except (ValueError, NameError): # Catch ValueError for float conversion and NameError if swing_high/low aren't set
                st.warning("📌 Define High and Low to unlock your TP projection.")       
    elif mode == "CUSTOM":
        st.markdown("### 🎯 Entry & Take Profit Zones ")
        if 'custom_entries' in locals() and custom_entries: # Ensure custom_entries is defined
            entry_df = pd.DataFrame(custom_entries)
            st.dataframe(entry_df, hide_index=True, use_container_width=True)
            # แจ้งเตือน RR
            for i, row in enumerate(custom_entries):
                try:
                    rr = float(row["RR"])
                    if rr < 2:
                        st.warning(f"🎯 Entry {i+1} RR is low ({rr:.2f}) — fine-tune your TP/SL for better balance."
)
                except:
                    pass
        else:
            st.info("กรอกข้อมูล Custom เพื่อดู Entry & TP Zones.")


# ======================= SEC 5: เชื่อมปุ่ม Save Plan กับ save_plan + Drawdown Lock =======================
drawdown_today = get_today_drawdown(log_file, acc_balance)
drawdown_limit = -acc_balance * (drawdown_limit_pct / 100)

# แสดงสถานะ drawdown วันนี้ใน sidebar
if drawdown_today < 0:
    st.sidebar.markdown(f"**ขาดทุนรวมวันนี้:** {drawdown_today:,.2f} USD")
else:
    st.sidebar.markdown(f"**ขาดทุนรวมวันนี้:** {drawdown_today:,.2f} USD")

# --- แก้ไขตรงนี้ ---
def save_plan(data, mode, asset, risk_pct, direction, active_portfolio_name): # <--- เพิ่ม active_portfolio_name
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_save = pd.DataFrame(data)
    df_save["Mode"] = mode
    df_save["Asset"] = asset
    df_save["Risk %"] = risk_pct
    df_save["Direction"] = direction
    df_save["Timestamp"] = now
    df_save["Portfolio"] = active_portfolio_name # <<< บรรทัดที่เพิ่มเข้ามา

    if os.path.exists(log_file):
        df_old = pd.read_csv(log_file)
        df_save = pd.concat([df_old, df_save], ignore_index=True)
    df_save.to_csv(log_file, index=False)
    # เราจะย้ายข้อความ success ไปไว้ตรงที่เรียกใช้ฟังก์ชันแทน


current_direction = None
if mode == "FIBO":
    if 'direction' in locals():
        current_direction = direction
elif mode == "CUSTOM":
    current_direction = "N/A" 


# --- แก้ไขส่วน FIBO ---
if mode == "FIBO" and 'entry_data' in locals() and save_fibo and entry_data and current_direction is not None:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    # <<< เพิ่มเงื่อนไขตรวจสอบการเลือกพอร์ต >>>
    elif 'active_portfolio_name' not in st.session_state or not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    else:
        try:
            # <<< ส่งชื่อพอร์ตเข้าไปในฟังก์ชัน >>>
            active_port_name = st.session_state.active_portfolio_name
            save_plan(entry_data, "FIBO", asset, risk_pct, current_direction, active_port_name)
            st.sidebar.success(f"บันทึกแผน (FIBO) สำหรับพอร์ต '{active_port_name}' สำเร็จ!") # <--- อัปเดตข้อความ
        except Exception as e:
            st.sidebar.error(f"Save ไม่สำเร็จ: {e}")

# --- แก้ไขส่วน CUSTOM (ทำเหมือนกัน) ---
elif mode == "CUSTOM" and 'custom_entries' in locals() and save_custom and custom_entries and current_direction is not None:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    # <<< เพิ่มเงื่อนไขตรวจสอบการเลือกพอร์ต >>>
    elif 'active_portfolio_name' not in st.session_state or not st.session_state.active_portfolio_name:
        st.sidebar.error("กรุณาเลือกหรือสร้างพอร์ตก่อนบันทึกแผน")
    else:
        try:
            # <<< ส่งชื่อพอร์ตเข้าไปในฟังก์ชัน >>>
            active_port_name = st.session_state.active_portfolio_name
            save_plan(custom_entries, "CUSTOM", asset, risk_pct, current_direction, active_port_name)
            st.sidebar.success(f"บันทึกแผน (CUSTOM) สำหรับพอร์ต '{active_port_name}' สำเร็จ!") # <--- อัปเดตข้อความ
        except Exception as e:
            st.sidebar.error(f"Save ไม่สำเร็จ: {e}")

# ======================= SEC 7: VISUALIZER (เหลือแต่กราฟ) =======================

with st.expander("📈 Chart Visualizer", expanded=True):
    plot = st.button("Plot Plan", key="plot_plan")

    if plot:
        st.components.v1.html("""
        <div class="tradingview-widget-container">
          <div id="tradingview_legendary"></div>
          <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
          <script type="text/javascript">
          new TradingView.widget({
            "width": "100%",
            "height": 600,
            "symbol": "OANDA:XAUUSD",      // ปรับ symbol ได้
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
    else:
        st.info("กดปุ่ม Plot Plan เพื่อแสดงกราฟ TradingView")

# ======================= SEC 8: AI SUMMARY & INSIGHT =======================
with st.expander("	🤖 AI Assistant", expanded=True):
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            if df_log.empty:
                st.info("ยังไม่มีข้อมูลแผนเทรดใน log")
            else:
                # 1. Winrate (รวม/แยก Mode)
                total_trades = df_log.shape[0]
                win_trades = df_log[df_log["Risk $"].astype(float) > 0].shape[0]
                loss_trades = df_log[df_log["Risk $"].astype(float) <= 0].shape[0]
                winrate = 100 * win_trades / total_trades if total_trades > 0 else 0

                # 2. กำไร/ขาดทุนสุทธิ
                gross_profit = df_log["Risk $"].astype(float).sum()

                # 3. RR เฉลี่ย
                rr_list = []
                if "RR" in df_log.columns:
                    rr_list = pd.to_numeric(df_log["RR"], errors='coerce').dropna().tolist()
                avg_rr = np.mean(rr_list) if len(rr_list) > 0 else None

                # 4. Drawdown (แบบง่าย)
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

                # 5. วัน/ช่วงเวลาที่ win/loss สูงสุด
                df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce')
                if not df_log["Date"].isnull().all():
                    df_log["Weekday"] = df_log["Date"].dt.day_name()
                    win_day = df_log[df_log["Risk $"].astype(float) > 0]["Weekday"].mode()[0] if not df_log[df_log["Risk $"].astype(float) > 0].empty else "-"
                    loss_day = df_log[df_log["Risk $"].astype(float) <= 0]["Weekday"].mode()[0] if not df_log[df_log["Risk $"].astype(float) <= 0].empty else "-"
                else:
                    win_day = loss_day = "-"

                # 6. ข้อมูลสรุป/Insight
                st.markdown("### 🧠 AI Intelligence Report")
                st.write(f"- **จำนวนแผนเทรด:** {total_trades:,}")
                st.write(f"- **Winrate:** {winrate:.2f}%")
                st.write(f"- **กำไร/ขาดทุนสุทธิ:** {gross_profit:,.2f} USD")
                if avg_rr is not None:
                    st.write(f"- **RR เฉลี่ย:** {avg_rr:.2f}")
                st.write(f"- **Max Drawdown:** {max_drawdown:,.2f} USD")
                st.write(f"- **วันชนะมากสุด:** {win_day}")
                st.write(f"- **วันขาดทุนมากสุด:** {loss_day}")

                # 7. Insight จุดแข็ง/จุดอ่อน (beta)
                st.markdown("### 🤖 AI Insight (จากกฎที่คุณกำหนดเอง)")
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
# ======================= SEC 7: Ultimate Statement Import & Auto-Mapping (Final Version) =======================
with st.expander("📂 SEC 7: Ultimate Statement Import & Auto-Mapping", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # --- ส่วนจัดการ Session State ---
    if 'all_statement_data' not in st.session_state:
        st.session_state.all_statement_data = {}
        st.session_state.df_stmt_current = pd.DataFrame()

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement (CSV/XLSX) เพื่อประมวลผลและบันทึก")
    
    uploaded_files = st.file_uploader(
        "ลากและวางไฟล์ Statement ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["xlsx", "csv"],
        accept_multiple_files=True,
        key="sec7_final_upload"
    )

    st.checkbox("⚙️ เปิดโหมด Debug (แสดงตารางข้อมูลทั้งหมดที่แยกได้)", key="debug_mode_final")
    
    # --- ฟังก์ชันหลัก (ไม่มีการเปลี่ยนแปลง) ---
   # --- อยู่ใน SEC 7 ---
    
    # --- ฟังก์ชันหลัก (แก้ไขเวอร์ชันนี้) ---
    def extract_data_from_report(file_buffer, stat_definitions_arg):
        # --- เพิ่มส่วนกำหนดค่า Keyword ---
        # !!! สำคัญ: คุณอาจจะต้องเปลี่ยนคำนี้ให้ตรงกับในไฟล์ Statement ของคุณ !!!
        # เช่น อาจจะเป็น "Login", "Account", "บัญชี"
        ACCOUNT_KEYWORD = "Account:" 
        
        df_raw = None
        try:
            file_buffer.seek(0)
            if file_buffer.name.endswith('.csv'):
                df_raw = pd.read_csv(file_buffer, header=None, low_memory=False)
            elif file_buffer.name.endswith('.xlsx'):
                df_raw = pd.read_excel(file_buffer, header=None, engine='openpyxl')
        except Exception as e:
            st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
            return None

        if df_raw is None or df_raw.empty:
            st.warning("ไม่สามารถอ่านข้อมูลจากไฟล์ได้ หรือไฟล์ว่างเปล่า")
            return None

        # --- เพิ่ม Logic การค้นหาเลขบัญชี ---
        account_number = f"File-{file_buffer.name[:10]}" # fallback name
        found_account = False
        # วนลูปหาใน 20 แถวแรกเพื่อประสิทธิภาพ
        for r_idx, row in df_raw.head(20).iterrows():
            for c_idx, cell in enumerate(row):
                cell_str = str(cell)
                if ACCOUNT_KEYWORD in cell_str:
                    # ถ้าเจอ Keyword ลองหาค่าในเซลล์เดียวกันก่อน (เช่น "Account: 1234567")
                    try:
                        potential_account = cell_str.split(ACCOUNT_KEYWORD)[1].strip()
                        if potential_account:
                            account_number = potential_account
                            found_account = True
                            break
                    except:
                        pass
                    
                    # ถ้าไม่เจอในเซลล์เดียวกัน ให้หาในเซลล์ถัดไปทางขวา
                    if (c_idx + 1) < len(row):
                        next_cell_val = row.iloc[c_idx + 1]
                        if pd.notna(next_cell_val) and str(next_cell_val).strip():
                            account_number = str(next_cell_val).strip()
                            found_account = True
                            break
            if found_account:
                break
        
        st.info(f"🔎 พบเลขบัญชี/พอร์ต: **{account_number}**")
        # --- จบส่วน Logic ค้นหาเลขบัญชี ---


        section_starts = {}
        section_keywords = ["Positions", "Orders", "Deals", "History", "Results"]
        # ... (โค้ดส่วนที่เหลือเหมือนเดิม) ...
        # ...
        
        extracted_data = {}
        sorted_sections = sorted(section_starts.items(), key=lambda x: x[1])

        tabular_keywords = ["Positions", "Orders", "Deals"]
        for i, (section_name, start_row) in enumerate(sorted_sections):
            # ... (โค้ดใน loop เหมือนเดิม) ...
            # ...
            if not df_section.empty:
                num_data_cols = df_section.shape[1]
                final_headers = headers[:num_data_cols]
                if len(final_headers) < num_data_cols:
                    final_headers.extend([f'Unnamed:{i}' for i in range(len(final_headers), num_data_cols)])
                df_section.columns = final_headers
                
                # --- เพิ่มคอลัมน์ Portfolio ที่นี่ ---
                df_section['Portfolio'] = account_number
                
                extracted_data[section_name.lower()] = df_section
        
        # ... (โค้ดส่วนที่เหลือของฟังก์ชันเหมือนเดิม) ...
        return extracted_data

    # --- ส่วนที่เรียกใช้ฟังก์ชันและแสดงผล ---
    
    # <<< จุดแก้ไขสำคัญที่แก้ NameError >>>
    # ย้าย stat_definitions ออกมาสร้างไว้ข้างนอกก่อนเสมอ
    stat_definitions = {
        "Total Net Profit", "Gross Profit", "Gross Loss", "Profit Factor", "Expected Payoff", "Recovery Factor",
        "Sharpe Ratio", "Balance Drawdown Absolute", "Balance Drawdown Maximal", "Balance Drawdown Relative",
        "Total Trades", "Short Trades (won %)", "Long Trades (won %)", "Profit Trades (% of total)", 
        "Loss Trades (% of total)", "Largest profit trade", "Largest loss trade", "Average profit trade", 
        "Average loss trade", "Maximum consecutive wins ($)", "Maximal consecutive profit (count)",
        "Average consecutive wins", "Maximum consecutive losses ($)", "Maximal consecutive loss (count)", 
        "Average consecutive losses"
    }

    if uploaded_files:
        for uploaded_file in uploaded_files:
            st.info(f"กำลังประมวลผลไฟล์: {uploaded_file.name}")
            with st.spinner(f"กำลังแยกส่วนข้อมูล..."):
                # ส่ง stat_definitions เข้าไปในฟังก์ชันตรงๆ
                extracted_data = extract_data_from_report(uploaded_file, stat_definitions)
                
                if extracted_data:
                    st.success(f"ประมวลผลสำเร็จ! พบข้อมูลในส่วน: {', '.join(extracted_data.keys())}")

                    if 'deals' in extracted_data:
                        st.session_state.df_stmt_current = extracted_data['deals'].copy()
                    
                    for key, df in extracted_data.items():
                        st.session_state.all_statement_data[key] = df.copy()

                    if 'balance_summary' in extracted_data:
                        st.write("### 📊 Balance Summary")
                        st.dataframe(extracted_data['balance_summary'])
                    
                    if st.session_state.debug_mode_final:
                        for section_key, section_df in extracted_data.items():
                            if section_key != 'balance_summary':
                                st.write(f"### 📄 ข้อมูลส่วน: {section_key.replace('_', ' ').title()}")
                                st.dataframe(section_df)
                else:
                    st.warning(f"ไม่สามารถแยกส่วนข้อมูลใดๆ จากไฟล์ {uploaded_file.name} ได้")
    else:
        st.info("ยังไม่มีไฟล์ Statement อัปโหลด")

    st.markdown("---")
    st.subheader("📁 ข้อมูล Statement ที่ถูกโหลดและประมวลผลล่าสุด (Deals)")
    st.dataframe(st.session_state.df_stmt_current)

    if st.button("🗑️ ล้างข้อมูล Statement ที่โหลดทั้งหมด", key="clear_all_statements_final"):
        st.session_state.all_statement_data = {}
        st.session_state.df_stmt_current = pd.DataFrame()
        st.success("ล้างข้อมูล Statement ทั้งหมดแล้ว")
        st.rerun()
# ======================= SEC 9: DASHBOARD + AI ULTIMATE =======================
# ปรับปรุง load_data_for_dashboard()
def load_data_for_dashboard():
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด",
        ["Log File (แผน)", "Statement Import (ของจริง)"],
        index=0,
        key="dashboard_source_select"
    )
    if source_option == "Log File (แผน)":
        if os.path.exists(log_file):
            df_data = pd.read_csv(log_file)
        else:
            df_data = pd.DataFrame()
    else: # Statement Import (ของจริง)
        # เราใช้ st.session_state.df_stmt_current ซึ่งถูกโหลด/อัปเดตจาก SEC 7 แล้ว
        return st.session_state.df_stmt_current 
    return df_data

with st.expander("📊 Performance Dashboard", expanded=True):
    df_data = load_data_for_dashboard()

    tab_dashboard, tab_rr, tab_lot, tab_time, tab_ai, tab_export = st.tabs([
        "📊 Dashboard",
        "📈 RR Histogram",
        "📉 Lot Size Evolution",
        "🕒 Time Analysis",
        "🤖 AI Recommendation", 
        "⬇️ Export/Report"
    ])

    with tab_dashboard:
        if df_data.empty:
            st.info("ยังไม่มีข้อมูลสำหรับ Dashboard")
        else:
            # --- จัดการส่วน Filter ด้านบน ---
            st.markdown("#### ⚙️ Filters")
            col1, col2 = st.columns(2)

            with col1:
                # Filter by Portfolio (ทำงานเมื่อมีคอลัมน์ Portfolio)
                if "Portfolio" in df_data.columns and df_data["Portfolio"].notna().any():
                    portfolio_list = ["ทั้งหมด"] + sorted(df_data["Portfolio"].dropna().unique().tolist())
                    selected_portfolio = st.selectbox(
                        "📂 Filter by Portfolio",
                        portfolio_list,
                        key="dashboard_portfolio_filter"
                    )
                    if selected_portfolio != "ทั้งหมด":
                        df_data = df_data[df_data["Portfolio"] == selected_portfolio]
                else:
                    st.info("ℹ️ เลือกแหล่งข้อมูล 'Log File' และบันทึกแผนเทรดพร้อมพอร์ตเพื่อเปิดใช้งาน Filter นี้")


            with col2:
                # Filter by Asset/Symbol
                column_for_asset_filter = None
                if "Asset" in df_data.columns and df_data["Asset"].notna().any():
                    column_for_asset_filter = "Asset"
                elif "Symbol" in df_data.columns and df_data["Symbol"].notna().any():
                    column_for_asset_filter = "Symbol"

                if column_for_asset_filter:
                    selected_asset = st.selectbox(
                        f"🎯 Filter by {column_for_asset_filter}",
                        ["ทั้งหมด"] + sorted(df_data[column_for_asset_filter].dropna().unique()),
                        key="dashboard_asset_filter"
                    )
                    if selected_asset != "ทั้งหมด":
                        df_data = df_data[df_data[column_for_asset_filter] == selected_asset]
                else:
                    st.selectbox("🎯 Filter by Asset/Symbol", ["-"], disabled=True)
            
            st.markdown("---") # เพิ่มเส้นคั่นเพื่อความสวยงาม

            # --- ส่วนแสดงกราฟ (ใช้ df_data ที่ผ่านการกรองแล้ว) ---
            st.markdown("### 🥧 Pie Chart: Win/Loss")
            # ... โค้ดส่วนที่เหลือสำหรับแสดงกราฟ (ไม่ต้องแก้ไข) ...


            st.markdown("### 🥧 Pie Chart: Win/Loss")
            profit_col = None
            if "Profit" in df_data.columns:
                profit_col = "Profit"
            elif "Risk $" in df_data.columns: # Fallback for log file
                profit_col = "Risk $"

            if profit_col:
                win_count = df_data[df_data[profit_col].astype(float) > 0].shape[0]
                loss_count = df_data[df_data[profit_col].astype(float) <= 0].shape[0]
                pie_df = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count, loss_count]})
                pie_chart = px.pie(pie_df, names="Result", values="Count", color="Result",
                                color_discrete_map={"Win": "green", "Loss": "red"})
                st.plotly_chart(pie_chart, use_container_width=True)
            else:
                st.warning("ไม่พบคอลัมน์กำไร/ขาดทุน (Profit หรือ Risk $) สำหรับ Pie Chart")


            st.markdown("### 📊 Bar Chart: กำไร/ขาดทุนแต่ละวัน")
            date_col = None
            if "Timestamp" in df_data.columns:
                date_col = "Timestamp"
            elif "Date" in df_data.columns:
                date_col = "Date"
            elif "Open Time" in df_data.columns:
                date_col = "Open Time" # Assuming Open Time is the relevant date for daily sums
            elif "Close Time" in df_data.columns:
                date_col = "Close Time" # Assuming Close Time is the relevant date for daily sums

            if date_col and profit_col:
                df_data_copy = df_data.copy() # Make a copy to avoid SettingWithCopyWarning
                df_data_copy["TradeDate"] = pd.to_datetime(df_data_copy[date_col], errors='coerce').dt.date
                bar_df = df_data_copy.groupby("TradeDate")[profit_col].sum().reset_index(name="Profit/Loss")
                bar_chart = px.bar(bar_df, x="TradeDate", y="Profit/Loss", color="Profit/Loss",
                                color_continuous_scale=["red", "orange", "green"])
                st.plotly_chart(bar_chart, use_container_width=True)
            else:
                st.warning("ไม่พบคอลัมน์วันที่/เวลา หรือ กำไร/ขาดทุน สำหรับ Bar Chart")


            st.markdown("### 📈 Timeline: Balance Curve")
            if profit_col and date_col:
                df_data_copy = df_data.copy()
                df_data_copy["Balance"] = 10000 + df_data_copy[profit_col].astype(float).cumsum()
                df_data_copy["TradeDate"] = pd.to_datetime(df_data_copy[date_col], errors='coerce') # Use full datetime for timeline x-axis

                # Sort by date for correct balance curve
                df_data_copy = df_data_copy.sort_values(by="TradeDate")

                timeline_chart = px.line(df_data_copy, x="TradeDate", y="Balance", markers=True)
                st.plotly_chart(timeline_chart, use_container_width=True)
            else:
                st.warning("ไม่พบคอลัมน์วันที่/เวลา หรือ กำไร/ขาดทุน สำหรับ Balance Curve")

    with tab_rr:
        if df_data.empty:
            st.info("ยังไม่มีข้อมูลสำหรับ RR Histogram")
        else:
            rr_col = None
            for col in df_data.columns:
                if col.strip().upper() == "RR":
                    rr_col = col
                    break
            if rr_col:
                rr_data = pd.to_numeric(df_data[rr_col], errors='coerce').dropna()
                if rr_data.empty:
                    st.info("ยังไม่มีข้อมูล RR ที่บันทึกในข้อมูล")
                else:
                    st.markdown("#### RR Histogram (แจกแจง Risk:Reward)")
                    fig = px.histogram(
                        rr_data,
                        nbins=20,
                        title="RR Histogram",
                        labels={'value': 'RR'},
                        opacity=0.75
                    )
                    fig.update_layout(bargap=0.1, xaxis_title='Risk Reward Ratio', yaxis_title='จำนวนไม้')
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("ดูว่า RR ส่วนใหญ่อยู่โซนไหน ถ้ามี RR < 2 เยอะ = เสี่ยง/หลุดวินัย")
            else:
                st.warning("ไม่พบคอลัมน์ RR ในข้อมูล")

    with tab_lot:
        if df_data.empty:
            st.info("ยังไม่มีข้อมูลสำหรับ Lot Size Evolution")
        else:
            if "Lot" in df_data.columns:
                df_data_copy = df_data.copy()
                df_data_copy["TradeDate"] = pd.to_datetime(df_data_copy["Timestamp"] if "Timestamp" in df_data_copy.columns else (df_data_copy["Date"] if "Date" in df_data_copy.columns else (df_data_copy["Open Time"] if "Open Time" in df_data_copy.columns else None)), errors='coerce')
                df_data_copy = df_data_copy.dropna(subset=['TradeDate']) # Remove rows with invalid dates
                df_data_copy = df_data_copy.sort_values(by="TradeDate") # Sort for correct timeline

                if not df_data_copy.empty:
                    st.markdown("#### Lot Size Evolution (การเปลี่ยนแปลง Lot Size ตามเวลา)")
                    fig = px.line(
                        df_data_copy,
                        x="TradeDate",
                        y="Lot",
                        markers=True,
                        title="Lot Size Evolution"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption("วิเคราะห์ Money Management/Scaling ได้ที่นี่")
                else:
                    st.warning("ไม่พบข้อมูล Lot ที่ถูกต้อง หรือข้อมูลวันที่ไม่สมบูรณ์")
            else:
                st.warning("ไม่พบคอลัมน์ Lot ในข้อมูล")

    with tab_time:
        if df_data.empty:
            st.info("ยังไม่มีข้อมูลสำหรับ Time Analysis")
        else:
            st.markdown("#### Time Analysis (วิเคราะห์ตามวัน/เวลา)")

            date_col_for_time = None
            if "Timestamp" in df_data.columns:
                date_col_for_time = "Timestamp"
            elif "Date" in df_data.columns:
                date_col_for_time = "Date"
            elif "Open Time" in df_data.columns:
                date_col_for_time = "Open Time"
            elif "Close Time" in df_data.columns:
                date_col_for_time = "Close Time"

            if date_col_for_time and profit_col:
                df_data_copy = df_data.copy()
                df_data_copy["TradeDateFull"] = pd.to_datetime(df_data_copy[date_col_for_time], errors='coerce')
                df_data_copy = df_data_copy.dropna(subset=['TradeDateFull']) # Remove rows with invalid dates

                df_data_copy["Weekday"] = df_data_copy["TradeDateFull"].dt.day_name()

                weekday_df = df_data_copy.groupby("Weekday")[profit_col].sum().reindex(
                    ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                ).reset_index(name="Profit/Loss")
                bar_chart = px.bar(weekday_df, x="Weekday", y="Profit/Loss", title="กำไร/ขาดทุนรวมตามวันในสัปดาห์")
                st.plotly_chart(bar_chart, use_container_width=True)
                st.caption("ดูว่าเทรดวันไหนเวิร์ค วันไหนควรหลีกเลี่ยง")
            else:
                st.warning("ไม่พบคอลัมน์วันที่/เวลา หรือ กำไร/ขาดทุน สำหรับ Time Analysis")

    with tab_ai:
        if df_data.empty:
            st.info("ยังไม่มีข้อมูลสำหรับ AI Recommendation")
        else:
            st.markdown("### AI Insight & Recommendation")
            total_trades = df_data.shape[0]
            profit_col_ai = None
            if "Profit" in df_data.columns:
                profit_col_ai = "Profit"
            elif "Risk $" in df_data.columns:
                profit_col_ai = "Risk $"

            if profit_col_ai:
                win_trades = df_data[df_data[profit_col_ai].astype(float) > 0].shape[0]
                loss_trades = df_data[df_data[profit_col_ai].astype(float) <= 0].shape[0]
                winrate_ai = 100 * win_trades / total_trades if total_trades > 0 else 0
                gross_profit_ai = df_data[profit_col_ai].astype(float).sum()
            else:
                win_trades = 0
                loss_trades = 0
                winrate_ai = 0
                gross_profit_ai = 0
                st.warning(f"ไม่พบคอลัมน์กำไร/ขาดทุน (Profit หรือ Risk $) ในข้อมูลสำหรับ AI.")

            st.write(f"จำนวนแผนเทรด: {total_trades}")
            st.write(f"Winrate: {winrate_ai:.2f}%")
            st.write(f"กำไร/ขาดทุนสุทธิ: {gross_profit_ai:,.2f} USD")

            try:
                if "GOOGLE_API_KEY" in st.secrets.get("google_api", {}):
                    model = genai.GenerativeModel('gemini-pro')

                    prompt_text = (
                        f"Based on this trading data: Total trades: {total_trades}, "
                        f"Winrate: {winrate_ai:.2f}%, Gross Profit/Loss: {gross_profit_ai:,.2f} USD. "
                        f"If this is a trading performance report, analyze it and provide a concise trading insight "
                        f"and recommendation for improvement. What are the strengths and weaknesses of this trading performance? "
                        f"Focus on practical advice for a trader. Respond in Thai."
                    )

                    with st.spinner("AI กำลังวิเคราะห์ข้อมูล..."):
                        response = model.generate_content(prompt_text)
                    st.markdown("---")
                    st.markdown("**จาก Gemini AI:**")
                    st.write(response.text)
                    st.markdown("---")
                else:
                    st.info("โปรดตั้งค่า Google API Key ใน `.streamlit/secrets.toml` เพื่อเปิดใช้งาน AI Assistant")
            except Exception as e:
                st.error(f"❌ เกิดข้อผิดพลาดในการเรียกใช้ Google AI: {e}")
                st.info("โปรดตรวจสอบว่าได้ตั้งค่า GOOGLE_API_KEY ถูกต้อง และมีโควต้าการใช้งาน AI เพียงพอ หรือ Generative Language API ถูกเปิดใช้งานใน Google Cloud Console แล้ว.")

            st.markdown("### 🤖 AI Insight (จากกฎที่คุณกำหนดเอง)")
            insight = []
            if winrate_ai >= 60:
                insight.append("Winrate สูง ระบบเสถียรภาพดี")
            elif winrate_ai < 40:
                insight.append("Winrate ต่ำ ควรพิจารณากลยุทธ์ใหม่")

            rr_list_ai_tab = []
            if "RR" in df_data.columns:
                rr_list_ai_tab = pd.to_numeric(df_data["RR"], errors='coerce').dropna().tolist()
            avg_rr_ai_tab = np.mean(rr_list_ai_tab) if len(rr_list_ai_tab) > 0 else None
            if avg_rr_ai_tab is not None and avg_rr_ai_tab < 2:
                insight.append("RR ต่ำกว่าค่าเฉลี่ยตลาด (<2) อาจเสี่ยงเกินไป")

            current_balance_ai_tab = acc_balance
            max_balance_ai_tab = current_balance_ai_tab
            drawdowns_ai_tab = []
            if profit_col_ai in df_data.columns:
                for profit_val in df_data[profit_col_ai].astype(float):
                    current_balance_ai_tab += profit_val
                    if current_balance_ai_tab > max_balance_ai_tab:
                        max_balance_ai_tab = current_balance_ai_tab
                    drawdown = max_balance_ai_tab - current_balance_ai_tab
                    drawdowns_ai_tab.append(drawdown)
                max_drawdown_ai_tab = max(drawdowns_ai_tab) if drawdowns_ai_tab else 0
                if max_drawdown_ai_tab > acc_balance * 0.05:
                    insight.append("Drawdown สูงกว่าปลอดภัย (5%) ควรควบคุม Money Management")

            if not insight:
                insight.append("ยังไม่พบความเสี่ยงสำคัญ")
            for msg in insight:
                st.info(msg)


    with tab_export:
        if df_data.empty:
            st.info("ยังไม่มีข้อมูลสำหรับ Export/Report")
        else:
            st.markdown("### Export/Download Report")
            st.download_button("Download Report (CSV)", df_data.to_csv(index=False), file_name="report.csv")


# ======================= SEC 6: LOG VIEWER (ล่างสุด + EXPANDER เดียว) =======================
with st.expander("📚 Trade Log Viewer (แผนเทรด)", expanded=False):
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            df_show = df_log.copy() # <--- ย้าย copy มาไว้ข้างบน

            # --- ส่วนจัดการ Filter ---
            # เพิ่มการตรวจสอบว่ามีคอลัมน์ Portfolio หรือไม่ เพื่อรองรับ log เก่า
            if "Portfolio" in df_log.columns:
                col1, col2, col3, col4 = st.columns(4) # <--- เปลี่ยนเป็น 4 คอลัมน์
                with col1:
                    # Filter สำหรับ Portfolio ที่เพิ่มเข้ามาใหม่
                    portfolio_list = ["ทั้งหมด"] + sorted(df_log["Portfolio"].dropna().unique().tolist())
                    portfolio_filter = st.selectbox("Portfolio", portfolio_list, key="log_portfolio_filter")
                with col2:
                    mode_filter = st.selectbox("Mode", ["ทั้งหมด"] + sorted(df_log["Mode"].unique().tolist()), key="log_mode_filter")
                with col3:
                    asset_filter = st.selectbox("Asset", ["ทั้งหมด"] + sorted(df_log["Asset"].unique().tolist()), key="log_asset_filter")
                with col4:
                    date_filter = st.text_input("ค้นหาวันที่ (YYYY-MM-DD)", value="", key="log_date_filter")
            else:
                # ถ้าไม่มีคอลัมน์ Portfolio ให้ใช้ layout เดิม
                col1, col2, col3 = st.columns(3)
                with col1:
                    mode_filter = st.selectbox("Mode", ["ทั้งหมด"] + sorted(df_log["Mode"].unique().tolist()), key="log_mode_filter")
                with col2:
                    asset_filter = st.selectbox("Asset", ["ทั้งหมด"] + sorted(df_log["Asset"].unique().tolist()), key="log_asset_filter")
                with col3:
                    date_filter = st.text_input("ค้นหาวันที่ (YYYY-MM-DD)", value="", key="log_date_filter")

            # --- ส่วนประมวลผลการกรอง ---
            if "Portfolio" in df_log.columns and portfolio_filter != "ทั้งหมด":
                df_show = df_show[df_show["Portfolio"] == portfolio_filter]
            if mode_filter != "ทั้งหมด":
                df_show = df_show[df_show["Mode"] == mode_filter]
            if asset_filter != "ทั้งหมด":
                df_show = df_show[df_show["Asset"] == asset_filter]
            if date_filter:
                # เพิ่ม .astype(str) เพื่อความปลอดภัยในการค้นหา
                df_show = df_show[df_show["Timestamp"].astype(str).str.contains(date_filter)]

            st.dataframe(df_show, use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"อ่าน log ไม่ได้: {e}")
    else:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้")
