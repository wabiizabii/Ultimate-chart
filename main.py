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

def save_plan(data, mode, asset, risk_pct, direction):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_save = pd.DataFrame(data)
    df_save["Mode"] = mode
    df_save["Asset"] = asset
    df_save["Risk %"] = risk_pct
    df_save["Direction"] = direction # ensure direction is always passed
    df_save["Timestamp"] = now
    if os.path.exists(log_file):
        df_old = pd.read_csv(log_file)
        df_save = pd.concat([df_old, df_save], ignore_index=True)
    df_save.to_csv(log_file, index=False)


current_direction = None
if mode == "FIBO":
    if 'direction' in locals():
        current_direction = direction
elif mode == "CUSTOM":
    current_direction = "N/A" 


if mode == "FIBO" and 'entry_data' in locals() and save_fibo and entry_data and current_direction is not None:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    else:
        try:
            save_plan(entry_data, "FIBO", asset, risk_pct, current_direction)
            st.sidebar.success("บันทึกแผน (FIBO) สำเร็จ!")
        except Exception as e:
            st.sidebar.error(f"Save ไม่สำเร็จ: {e}")

elif mode == "CUSTOM" and 'custom_entries' in locals() and save_custom and custom_entries and current_direction is not None:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    else:
        try:
            save_plan(custom_entries, "CUSTOM", asset, risk_pct, current_direction)
            st.sidebar.success("บันทึกแผน (CUSTOM) สำเร็จ!")
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
# ======================= SEC 7: Ultimate Statement Import & Auto-Mapping =======================
with st.expander("📂 SEC 7: Ultimate Statement Import & Auto-Mapping", expanded=False):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # ใช้ st.session_state เพื่อคงค่า all_statement_data และ df_stmt_current ระหว่าง rerun
    # บล็อกนี้จะถูกรันแค่ครั้งเดียวเมื่อแอปโหลดขึ้นมาครั้งแรก หรือเมื่อข้อมูลถูกล้าง
    if 'all_statement_data' not in st.session_state:
        st.session_state.all_statement_data = {} # เริ่มต้นด้วย Dictionary ว่างเปล่า
        st.session_state.df_stmt_current = pd.DataFrame() # และ df_stmt_current ว่างเปล่า
        
        st.info("กำลังโหลดข้อมูล Statement จาก Google Sheets ครั้งแรก...")
        # NOTE: load_statement_from_gsheets ควรถูก import หรือประกาศไว้ข้างบน
        # ถ้ายังไม่มีฟังก์ชันนี้ใน main.py คุณอาจต้องเพิ่มมันใน SEC 0 หรือใกล้เคียง
        # เช่น:
        # def load_statement_from_gsheets():
        #     # โค้ดสำหรับโหลดจาก Google Sheets
        #     return {} # คืนค่าเป็น dictionary เปล่าถ้ายังไม่มีการใช้งานจริง
        loaded_data = load_statement_from_gsheets()
        
        st.session_state.all_statement_data = loaded_data # เก็บผลลัพธ์ทั้งหมดใน session_state
        
        # ดึงเฉพาะส่วน 'deals' มาใส่ใน df_stmt_current
        if 'deals' in loaded_data and not loaded_data['deals'].empty:
            st.session_state.df_stmt_current = loaded_data['deals']
            st.success("โหลดข้อมูล 'Deals' สำหรับ Dashboard สำเร็จ!")
        else:
            st.info("ไม่พบข้อมูล 'Deals' จาก Google Sheets หรือกำลังโหลดครั้งแรก.")
    
    # ดึงค่าจาก session_state มาใช้งานในส่วนที่เหลือของแอป
    all_statement_data = st.session_state.all_statement_data
    df_stmt_current = st.session_state.df_stmt_current

    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement (CSV/XLSX) เพื่อประมวลผลและบันทึก")
    st.info("โปรดอัปโหลด 'ไฟล์ Statement ต้นฉบับ' ของคุณจากคอมพิวเตอร์ เพื่อให้แอปแยกส่วนต่างๆ ได้อย่างถูกต้อง")
    uploaded_files = st.file_uploader(
        "ลากและวางไฟล์ Statement ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["xlsx", "csv"], 
        accept_multiple_files=True, 
        key="sec7_upload"
    )

    # --- เพิ่ม Debug Mode Checkbox ตรงนี้ ---
    if 'debug_mode' not in st.session_state:
        st.session_state.debug_mode = False
    
    st.session_state.debug_mode = st.checkbox("⚙️ เปิดโหมด Debug สำหรับ Balance Summary (อาจมีข้อความเยอะ)", value=st.session_state.debug_mode)
    if st.session_state.debug_mode:
        st.warning("⚠️ โหมด Debug ทำงานอยู่: ข้อความแสดงผลลัพธ์จาก Excel อาจเยอะและรกตา")
    # --- สิ้นสุดการเพิ่ม Debug Mode Checkbox ---


    # --- ฟังก์ชันช่วยในการแยกส่วนข้อมูลจากไฟล์ที่อัปโหลด (ปรับปรุงแล้ว) ---
    def extract_sections_from_file(file):
        if file.name.endswith(".xlsx"):
            df_raw = pd.read_excel(file, header=None, engine='openpyxl')
        elif file.name.endswith(".csv"):
            df_raw = pd.read_csv(file, header=None)
        else:
            return {} # คืนค่า dictionary เปล่า ถ้าไม่ใช่ excel หรือ csv

        section_starts = {}
        current_section = None
        section_keywords = {
            "History": "History",
            "Open Trades": "Open Trades",
            "Exposure": "Exposure",
            "Orders": "Orders",
            "Results": "Results"
        }

        # Find start rows for main sections
        for r_idx in range(len(df_raw)):
            # Check for section headers (e.g., "History", "Open Trades", etc.)
            for col_idx in range(min(df_raw.shape[1], 15)): # Check more columns up to O (index 14)
                cell_value = str(df_raw.iloc[r_idx, col_idx]).strip()
                for key, keyword in section_keywords.items():
                    if keyword.lower() in cell_value.lower() and key not in section_starts:
                        section_starts[key] = r_idx
                        current_section = key
                        break
                if current_section:
                    break
            current_section = None # Reset for next search

        section_data = {}
        tabular_sections = ["History", "Open Trades", "Exposure", "Orders"]

        for section_name in tabular_sections:
            if section_name in section_starts:
                start_row = section_starts[section_name]
                
                # Find the header row (first non-empty row after section start)
                header_row_idx = -1
                for r_idx in range(start_row + 1, len(df_raw)):
                    if not df_raw.iloc[r_idx].isnull().all(): # Check if row is not entirely empty
                        header_row_idx = r_idx
                        break
                
                if header_row_idx != -1:
                    headers = [str(col).strip() for col in df_raw.iloc[header_row_idx] if pd.notna(col) and str(col).strip() != '']
                    
                    # Determine end row of the section
                    end_row = len(df_raw)
                    next_section_start = len(df_raw) # Default to end of file
                    for other_section_name, other_start_row in section_starts.items():
                        if other_section_name != section_name and other_start_row > start_row:
                            if other_start_row < next_section_start:
                                next_section_start = other_start_row
                    end_row = next_section_start

                    # Extract data rows for the current section
                    data_start_row = header_row_idx + 1
                    section_df = df_raw.iloc[data_start_row:end_row].copy()
                    
                    # Check if section_df is not empty before processing
                    if not section_df.empty:
                        # Drop rows where all values are NaN
                        section_df.dropna(how='all', inplace=True)
                        
                        if not section_df.empty:
                            # Re-index to make operations easier
                            section_df.reset_index(drop=True, inplace=True)

                            # Dynamically map headers to column indices
                            header_to_col_idx = {}
                            for i, col_name in enumerate(df_raw.iloc[header_row_idx]):
                                if pd.notna(col_name) and str(col_name).strip() != '':
                                    header_to_col_idx[str(col_name).strip()] = i

                            # Create a new DataFrame with correctly aligned columns
                            processed_data = []
                            for row_idx in range(len(section_df)):
                                row_values = []
                                for header in headers:
                                    original_col_idx = header_to_col_idx.get(header)
                                    if original_col_idx is not None and original_col_idx < len(df_raw.columns):
                                        # Use .loc with original DataFrame's column index
                                        # We need to use df_raw.iloc to get the value from the correct original position
                                        value = df_raw.iloc[data_start_row + row_idx, original_col_idx]
                                        row_values.append(value)
                                    else:
                                        row_values.append(np.nan) # Append NaN if header not found in original cols
                                processed_data.append(row_values)
                            
                            # Remove leading/trailing spaces from headers
                            cleaned_headers = [h.strip() for h in headers]
                            
                            temp_df = pd.DataFrame(processed_data, columns=cleaned_headers)

                            # Clean up values (remove $, comma, %)
                            for col in temp_df.columns:
                                # Apply cleaning only to columns that are likely to contain numbers
                                if temp_df[col].dtype == 'object': # Check if it's an object/string type
                                    # Ensure we don't apply regex to non-string types or if not necessary
                                    temp_df[col] = temp_df[col].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).str.replace('%', '', regex=False)
                                    # Handle parentheses for negative numbers: (123.45) -> -123.45
                                    temp_df[col] = temp_df[col].apply(lambda x: f"-{x.replace('(', '').replace(')', '').strip()}" if isinstance(x, str) and '(' in x and ')' in x else x)
                                    # Attempt conversion to numeric after cleaning
                                    temp_df[col] = pd.to_numeric(temp_df[col], errors='coerce')
                                elif pd.api.types.is_numeric_dtype(temp_df[col]):
                                    # If already numeric, ensure negative signs from parentheses are handled if any exist (unlikely but safe)
                                    # This is more for string-like numbers that are already numeric (e.g., loaded as int but had parentheses)
                                    temp_df[col] = temp_df[col].apply(lambda x: -abs(x) if isinstance(x, (str)) and '(' in str(x) and ')' in str(x) else x)


                            section_data[section_name.lower().replace(" ", "_")] = temp_df
                        else:
                            st.warning(f"Warning: No valid data rows found for section '{section_name}'.")
                    else:
                        st.warning(f"Warning: Section '{section_name}' found but no data could be extracted.")
                else:
                    st.warning(f"Warning: Could not find header row for section '{section_name}'.")

        # --- Process "Results" section (Balance Summary) ---
        results_stats = {}
        if "Results" in section_starts:
            results_start_row = section_starts["Results"]
            # Start scanning from the row *after* "Results" keyword was found
            # and limit to a reasonable number of rows.
            scan_end_row = min(len(df_raw), results_start_row + 1 + 30) # Scan up to 30 rows after "Results" start for stats
            
            # Use a dictionary for faster lookup, mapping normalized label to (original_label, expected_label_col_idx, expected_value_col_idx)
            stat_lookup_map = {}
            
            # Based on your screenshots for ReportHistory-300379.xlsx and the new file:
            # Column mapping (0-indexed Pandas):
            # C (index 2) is value for B (index 1)
            # H (index 7) is value for G (index 6)
            # N (index 13) is value for K (index 10)
            stat_definitions_for_results = [
                ("Total Net Profit", 1, 2), # Label in B, Value in C
                ("Profit Factor", 1, 2),    # Label in B, Value in C
                ("Recovery Factor", 1, 2),  # Label in B, Value in C
                ("Balance Drawdown Absolute", 1, 2), # Label in B, Value in C
                ("Total Trades", 1, 2),     # Label in B, Value in C

                ("Gross Profit", 6, 7),     # Label in G, Value in H
                ("Expected Payoff", 6, 7),  # Label in G, Value in H
                ("Sharpe Ratio", 6, 7),     # Label in G, Value in H
                ("Balance Drawdown Maximal", 6, 7), # Label in G, Value in H
                ("Short Trades (won %)", 6, 7), # Label in G, Value in H
                ("Profit Trades (% of total)", 6, 7), # Label in G, Value in H
                ("Largest profit trade", 6, 7), # Label in G, Value in H
                ("Average profit trade", 6, 7), # Label in G, Value in H
                ("Maximum consecutive wins ($)", 6, 7), # Label in G, Value in H
                ("Maximal consecutive profit (count)", 6, 7), # Label in G, Value in H
                ("Average consecutive wins", 6, 7), # Label in G, Value in H

                ("Gross Loss", 10, 13),      # Label in K, Value in N
                ("Balance Drawdown Relative", 10, 13), # Label in K, Value in N
                ("Long Trades (won %)", 10, 13), # Label in K, Value in N
                ("Loss Trades (% of total)", 10, 13), # Label in K, Value in N
                ("Largest loss trade", 10, 13), # Label in K, Value in N
                ("Average loss trade", 10, 13), # Label in K, Value in N
                ("Maximum consecutive losses ($)", 10, 13), # Label in K, Value in N
                ("Maximal consecutive loss (count)", 10, 13), # Label in K, Value in N
                ("Average consecutive losses", 10, 13) # Label in K, Value in N
            ]

            for original_label, label_col, value_col in stat_definitions_for_results:
                normalized_key = "".join(filter(str.isalnum, original_label)).lower()
                stat_lookup_map[normalized_key] = (original_label, label_col, value_col)

            # ADD THIS DEBUG PRINT: แสดงเนื้อหาของ stat_lookup_map
            if st.session_state.debug_mode:
                st.write("DEBUG Balance Summary: stat_lookup_map built:")
                st.write(stat_lookup_map)
            
            # --- NEW: Use openpyxl for reliable cell access in "Results" section ---
            # Reset file pointer to beginning for openpyxl to read
            file.seek(0)
            try:
                workbook = openpyxl.load_workbook(file)
                sheet = workbook.active # Assuming data is on the active sheet
            except Exception as e:
                st.error(f"Error loading Excel with openpyxl: {e}")
                if st.session_state.debug_mode:
                    st.write(f"DEBUG openpyxl Error: {e}")
                return section_data # Return empty if openpyxl fails

            # Iterate using openpyxl's 1-indexed row/col system
            # results_start_row is 0-indexed from Pandas, so add 1 to get openpyxl row index for "Results" keyword
            # Then add another 1 to start scanning from the row *after* "Results"
            # scan_end_row (Pandas 0-indexed) also needs to be converted to openpyxl 1-indexed for the range
            for r_idx_openpyxl in range(results_start_row + 2, scan_end_row + 1): 
                # Convert pandas 0-indexed columns to openpyxl 1-indexed columns for potential label columns
                potential_label_cols_openpyxl = [col_idx_pandas + 1 for col_idx_pandas in [1, 6, 10]] # B, G, K -> 2, 7, 11 (in openpyxl)

                for current_label_col_openpyxl in potential_label_cols_openpyxl:
                    # Get cell value directly using openpyxl
                    raw_cell_content = None
                    try:
                        cell_obj = sheet.cell(row=r_idx_openpyxl, column=current_label_col_openpyxl)
                        raw_cell_content = cell_obj.value
                    except IndexError: # If column is out of bounds for this row in openpyxl
                        if st.session_state.debug_mode:
                            st.write(f"DEBUG Balance Summary (openpyxl): Cell ({r_idx_openpyxl}, {current_label_col_openpyxl}) out of sheet bounds. Skipping.")
                        continue # Skip to next column

                    # Use pd.isna for robustness with various NaN representations
                    is_nan_val = pd.isna(raw_cell_content) 

                    if st.session_state.debug_mode:
                        st.write(f"DEBUG Balance Summary (openpyxl): Checking Label Row {r_idx_openpyxl}, Col {current_label_col_openpyxl}. Raw Cell Content: '{raw_cell_content}', Type: {type(raw_cell_content)}, Is NaN: {is_nan_val}")

                    # Check if the string representation is not empty and not the literal string 'None' (for truly empty cells)
                    string_representation = str(raw_cell_content).strip()
                    if string_representation and string_representation.lower() != 'none':
                        label_text_from_excel_raw = string_representation
                        normalized_excel_label = "".join(filter(str.isalnum, label_text_from_excel_raw)).lower()

                        if st.session_state.debug_mode:
                            st.write(f"DEBUG Balance Summary (openpyxl): Scanning (Found Text) Row {r_idx_openpyxl}, Col {current_label_col_openpyxl}: Raw Text='{label_text_from_excel_raw}', Normalized='{normalized_excel_label}'")
                        
                        if normalized_excel_label in stat_lookup_map:
                            original_stat_key, expected_label_col_pandas, expected_value_col_pandas = stat_lookup_map[normalized_excel_label]
                            
                            # Convert expected pandas 0-indexed columns to openpyxl 1-indexed columns
                            expected_label_col_openpyxl = expected_label_col_pandas + 1
                            expected_value_col_openpyxl = expected_value_col_pandas + 1
                            
                            # Double-check if the found label column matches the expected label column for this stat
                            if current_label_col_openpyxl == expected_label_col_openpyxl:
                                value_col_to_read_openpyxl = expected_value_col_openpyxl
                                
                                raw_value_content = None
                                try:
                                    value_cell_obj = sheet.cell(row=r_idx_openpyxl, column=value_col_to_read_openpyxl)
                                    raw_value_content = value_cell_obj.value
                                except IndexError: # If value column is out of bounds
                                     if st.session_state.debug_mode:
                                        st.write(f"DEBUG Balance Summary (openpyxl): Value Cell ({r_idx_openpyxl}, {value_col_to_read_openpyxl}) out of sheet bounds. Skipping.")
                                     continue # Skip to next iteration

                                if st.session_state.debug_mode:
                                    st.write(f"DEBUG Balance Summary (openpyxl): Attempting to read value for '{original_stat_key}' from Row {r_idx_openpyxl}, Value Col {value_col_to_read_openpyxl}. Raw Cell Content: '{raw_value_content}', Is NaN: {pd.isna(raw_value_content)}")
                                
                                # Process if value content is not NaN/empty
                                if pd.notna(raw_value_content) and str(raw_value_content).strip().lower() != 'none': 
                                    value = str(raw_value_content).strip()
                                    
                                    # Handle percentages like "11.46% (1 211.92)" by taking only the first part
                                    if '%' in value and '(' in value:
                                        value = value.split('%')[0].strip()
                                    # Handle negative numbers in parentheses like "(123.45)"
                                    elif '(' in value and ')' in value:
                                        value = "-" + value.replace('(', '').replace(')', '').strip()
                                    
                                    # Remove common non-numeric characters
                                    value = value.replace('$', '').replace(',', '').replace('%', '')
                                    
                                    try:
                                        value = float(value)
                                    except ValueError:
                                        try:
                                            value = int(value)
                                        except ValueError:
                                            if st.session_state.debug_mode:
                                                st.warning(f"DEBUG Balance Summary (openpyxl): Could not convert '{value}' for '{original_stat_key}' to numeric. Keeping as string.")
                                            continue # Skip to next iteration if value is not numeric
                                    
                                    results_stats[original_stat_key] = value
                                    
                                    if st.session_state.debug_mode:
                                        st.write(f"DEBUG Balance Summary (openpyxl): --- Found and extracted '{original_stat_key}' --- Value: '{value}' from Row {r_idx_openpyxl}, Label Col {current_label_col_openpyxl}, Value Col {value_col_to_read_openpyxl}")
                                else: # If value is NaN or empty string
                                     if st.session_state.debug_mode:
                                         st.write(f"DEBUG Balance Summary (openpyxl): Skipping '{original_stat_key}' - Value cell is NaN, empty, or 'None'.")
                            else: # If current_label_col_openpyxl != expected_label_col_openpyxl
                                if st.session_state.debug_mode:
                                    st.write(f"DEBUG Balance Summary (openpyxl): Mismatch label column for '{original_stat_key}'. Expected {expected_label_col_openpyxl}, got {current_label_col_openpyxl}.")
                        else: # If normalized_excel_label not in stat_lookup_map
                            if st.session_state.debug_mode:
                                st.write(f"DEBUG Balance Summary (openpyxl): '{normalized_excel_label}' (from Col {current_label_col_openpyxl}) not in stat_lookup_map.")
                    else: # If string_representation is empty or 'None'
                        if st.session_state.debug_mode:
                            st.write(f"DEBUG Balance Summary (openpyxl): Cell at Row {r_idx_openpyxl}, Col {current_label_col_openpyxl} is empty or 'None' after stripping. Skipping label check.")

            if results_stats:
                section_data["balance_summary"] = pd.DataFrame(list(results_stats.items()), columns=['Metric', 'Value'])
                if st.session_state.debug_mode:
                    st.write("DEBUG Balance Summary: Final results_stats collected:")
                    st.write(results_stats)
            else:
                st.warning("Warning: 'Results' section found but no recognizable statistics extracted for Balance Summary.")
                if st.session_state.debug_mode:
                    st.write("DEBUG Balance Summary: No stats found using current logic.")

        return section_data # <--- บรรทัดนี้คือบรรทัดสุดท้ายของฟังก์ชัน extract_sections_from_file

    # โค้ดที่ประมวลผลไฟล์ที่อัปโหลด (ต้องอยู่นอกฟังก์ชัน extract_sections_from_file)
    # แต่ยังคงอยู่ใน with st.expander("📂 SEC 7: ..."):
    if uploaded_files:
        for uploaded_file in uploaded_files:
            file_name = uploaded_file.name
            st.info(f"กำลังประมวลผลไฟล์: {file_name}")
            
            with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {file_name}..."):
                extracted_data = extract_sections_from_file(uploaded_file)
                
                if extracted_data:
                    # อัปเดตข้อมูลทั้งหมดใน session_state
                    for key, df in extracted_data.items():
                        if key not in st.session_state.all_statement_data:
                            st.session_state.all_statement_data[key] = df
                        else:
                            st.session_state.all_statement_data[key] = pd.concat([st.session_state.all_statement_data[key], df], ignore_index=True)
                            st.session_state.all_statement_data[key].drop_duplicates(inplace=True) # ป้องกันข้อมูลซ้ำซ้อน
                    
                    # อัปเดต df_stmt_current ด้วยส่วน 'history' (ซึ่งตอนนี้เปลี่ยนเป็น 'deals')
                    if 'history' in extracted_data: # ตรวจสอบ 'history' ก่อน
                        st.session_state.df_stmt_current = extracted_data['history']
                    elif 'deals' in extracted_data: # ถ้าไม่พบ 'history' ให้ใช้ 'deals'
                        st.session_state.df_stmt_current = extracted_data['deals']
                    else:
                        st.warning(f"ไม่พบส่วน 'History' หรือ 'Deals' ในไฟล์ {file_name} เพื่ออัปเดต Dashboard หลัก")
                        
                    st.success(f"ประมวลผล {file_name} สำเร็จ! พบข้อมูลในส่วน: {', '.join(extracted_data.keys())}")

                    # แสดงผล Balance Summary ถ้ามีและ Debug Mode เปิดอยู่
                    if st.session_state.debug_mode and 'balance_summary' in extracted_data:
                        st.write("### 📊 Balance Summary (จากไฟล์ที่ประมวลผล)")
                        st.dataframe(extracted_data['balance_summary'])
                    
                    # แสดงส่วนอื่นๆ ที่แยกได้ (ถ้า Debug Mode เปิดอยู่)
                    if st.session_state.debug_mode:
                        for section_key, section_df in extracted_data.items():
                            if section_key != 'balance_summary':
                                st.write(f"### 📄 ข้อมูลส่วน: {section_key.replace('_', ' ').title()}")
                                st.dataframe(section_df)
                else:
                    st.warning(f"ไม่สามารถแยกส่วนข้อมูลใดๆ จากไฟล์ {file_name} ได้ โปรดตรวจสอบรูปแบบไฟล์")
        # st.experimental_rerun() # บรรทัดนี้ถูกลบออกเพื่อแก้ AttributeError
    else:
        st.info("ยังไม่มีไฟล์ Statement อัปโหลด")

    st.markdown("---")
    st.subheader("📁 ข้อมูล Statement ที่ถูกโหลดและประมวลผลล่าสุด")
    st.info("นี่คือข้อมูล 'Deals' (หรือ History) ที่ถูกดึงมาใช้ใน Dashboard หลัก")
    st.dataframe(df_stmt_current)

    # ปุ่มล้างข้อมูลทั้งหมด
    if st.button("🗑️ ล้างข้อมูล Statement ที่โหลดทั้งหมด (รวม Google Sheets)", key="clear_all_statements"):
        st.session_state.all_statement_data = {}
        st.session_state.df_stmt_current = pd.DataFrame()
        st.success("ล้างข้อมูล Statement ทั้งหมดแล้ว")
        st.experimental_rerun() # อันนี้ยังคงอยู่
