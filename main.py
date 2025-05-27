# ======================= SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime
import plotly.express as px
import google.generativeai as genai
import gspread # <--- เพิ่ม import gspread ที่นี่

st.set_page_config(page_title="Legendary RR Planner", layout="wide")
acc_balance = 10000 
log_file = "trade_log.csv"

#--- Google AI API Key ---  # <-- บรรทัดที่ 16 อาจจะเปลี่ยน comment เป็นแบบนี้
try:
    if "gemini" in st.secrets and "api_key" in st.secrets["gemini"]: # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
        genai.configure(api_key=st.secrets["gemini"]["api_key"])  # <--- บรรทัดนี้ต้องเยื้อง 8 ช่องว่าง
        st.success("Google Gemini API Key ใช้งานได้!")           # <--- บรรทัดนี้ต้องเยื้อง 8 ช่องว่าง
    else:                                                     # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
        st.error("❌ ไม่พบ Gemini API Key ใน st.secrets['gemini']['api_key'] ตรวจสอบไฟล์ .streamlit/secrets.toml ของคุณ") # <--- บรรทัดนี้ต้องเยื้อง 8 ช่องว่าง
        st.info("คุณสามารถขอ API Key ได้ที่ https://aistudio.google.com/app/apikey") # <--- บรรทัดนี้ต้องเยื้อง 8 ช่องว่าง
except Exception as e:                                    # <--- 'except' ต้องอยู่ระดับเดียวกับ 'try' (ไม่เยื้อง)
    st.error(f"❌ เกิดข้อผิดพลาดในการเรียกใช้งาน Google AI API: {e}") # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง

#--- เชื่อมต่อ Google Sheets Objects API Key และ gspread Client ---
import gspread # <--- ต้องมีบรรทัดนี้ด้วย ถ้ายังไม่มี

try:
    creds = st.secrets["gcp_service_account"]                   # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
    gc = gspread.service_account_from_dict(creds)               # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
    spreadsheet = gc.open_by_id(st.secrets["gcp_service_account"]["spreadsheet_id"]) # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
    worksheet = spreadsheet.sheet1                              # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
    st.success("เชื่อมต่อ Google Sheets สำเร็จ!")             # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
except Exception as e:                                      # <--- 'except' ต้องอยู่ระดับเดียวกับ 'try' (ไม่เยื้อง)
    st.error(f"❌ เกิดข้อผิดพลาดในการเชื่อมต่อ Google Sheets: {e}") # <--- บรรทัดนี้ต้องเยื้อง 4 ช่องว่าง
    st.warning("⚠️ โปรดตั้งค่า 'gcp_service_account' ใน .streamlit/secrets.toml เพื่อเชื่อมต่อ Google Sheets.")

# โค้ดส่วนอื่นๆ ของแอปคุณจะมาต่อจากนี้# --- การตั้งค่า Google Sheets API Key และ Gspread Client ---
# กำหนดชื่อ Google Sheet และ Worksheet ที่จะใช้เก็บข้อมูล Statement
GOOGLE_SHEET_NAME = "Legendary RR Planner Statement Data" # **เปลี่ยนเป็นชื่อ Google Sheet ของคุณ**
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
@st.cache_data(ttl=3600) # แคชข้อมูล 1 ชั่วโมง เพื่อไม่ให้เรียก API บ่อยเกินไป
def load_statement_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        try:
            worksheet = sh.worksheet(GOOGLE_WORKSHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            st.info(f"✨ กำลังสร้าง Worksheet '{GOOGLE_WORKSHEET_NAME}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'...")
            worksheet = sh.add_worksheet(title=GOOGLE_WORKSHEET_NAME, rows="1", cols="1") # เริ่มต้นด้วย 1x1

        data = worksheet.get_all_records()
        if not data: # ถ้า worksheet ว่างเปล่า
            # st.info(f"Worksheet '{GOOGLE_WORKSHEET_NAME}' ว่างเปล่า.")
            return pd.DataFrame()

        df = pd.DataFrame(data)
        # ทำความสะอาดข้อมูลที่อ่านได้ (ตามที่คุณต้องการ เช่น แปลง type)
        for col in ['Profit', 'Risk $', 'Lot', 'RR', 'Entry', 'SL', 'TP', 'StopLoss']: # เพิ่มคอลัมน์ที่อาจเป็นตัวเลข
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        for col in ['Timestamp', 'Time', 'Date', 'Open Time', 'Close Time']: # เพิ่มคอลัมน์วันที่/เวลา
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')

        # st.success(f"โหลดข้อมูล Statement จาก Google Sheet '{GOOGLE_SHEET_NAME}/{GOOGLE_WORKSHEET_NAME}' สำเร็จ!")
        return df
    except gspread.exceptions.SpreadsheetNotFound:
        st.error(f"❌ ไม่พบ Google Sheet ชื่อ '{GOOGLE_SHEET_NAME}'. โปรดสร้างและแชร์กับ Service Account ของคุณ")
        return pd.DataFrame()
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการโหลดข้อมูล Statement จาก Google Sheets: {e}")
        return pd.DataFrame()

# ฟังก์ชันสำหรับบันทึก DataFrame ลง Google Sheets (แทนที่ข้อมูลเก่า)
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

        # ลบข้อมูลเก่าทิ้งก่อน
        worksheet.clear() 
        # เขียน Header และข้อมูล
        worksheet.update([df_to_save.columns.values.tolist()] + df_to_save.values.tolist())
        st.success(f"บันทึกข้อมูล Statement ไปยัง Google Sheet '{GOOGLE_SHEET_NAME}/{GOOGLE_WORKSHEET_NAME}' เรียบร้อยแล้ว!")
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกข้อมูล Statement ไปยัง Google Sheets: {e}")


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
uploaded_files = st.file_uploader(
    "📤 อัปโหลด Statement (.xlsx, .csv)", 
    type=["xlsx", "csv"], 
    accept_multiple_files=True, 
    key="sec7_upload"
)

def extract_sections_from_file(file):
    import pandas as pd

    if file.name.endswith(".xlsx"):
        df_raw = pd.read_excel(file, header=None, engine='openpyxl')
    elif file.name.endswith(".csv"):
        df_raw = pd.read_csv(file, header=None)
    else:
        return {}

    section_starts = {}
    # เพิ่มคีย์ที่อาจพบใน Statement จริงของคุณ
    section_keys = [
        "Positions", "Orders", "Deals", "Balance", "Drawdown",
        "Total Trades", "Profit Trades", "Largest profit trade", "Average profit trade",
        "History", # MT4/MT5 export often has a "History" section
        "Trades" # Some statements might use "Trades"
    ]

    for idx, row in df_raw.iterrows():
        if pd.isna(row[0]): # Skip empty first column
            continue
        for key in section_keys:
            if str(row[0]).strip().startswith(key):
                section_starts[key] = idx
                break # Found the start, move to next row

    section_data = {}

    def make_cols_unique(cols):
        counts = {}
        result = []
        for c in cols:
            if pd.isna(c) or str(c).strip() == '': # Handle NaN or empty strings in headers
                c = 'Unnamed'
            c_str = str(c)
            if c_str in counts:
                counts[c_str] += 1
                result.append(f"{c_str}_{counts[c_str]}")
            else:
                counts[c_str] = 0
                result.append(c_str)
        return result

    # Priority for sections: Deals, Trades, Positions, History
    target_sections = ["Deals", "Trades", "Positions", "History"]
    found_section_key = None
    for skey in target_sections:
        if skey in section_starts:
            found_section_key = skey
            break

    if found_section_key:
        header_row = section_starts[found_section_key] + 1
        # Find the start of the next section to define the end of the current one
        next_section_start_idx = len(df_raw) # Default to end of file

        # Find the next section in the list after the current found_section_key
        current_key_idx = section_keys.index(found_section_key)
        for i in range(current_key_idx + 1, len(section_keys)):
            next_key = section_keys[i]
            if next_key in section_starts:
                next_section_start_idx = section_starts[next_key]
                break

        # Extract the relevant rows for the data
        df_section = df_raw.iloc[header_row:next_section_start_idx].dropna(how="all")

        # Use the first row as columns, then slice the DataFrame to remove it
        if not df_section.empty:
            raw_cols = df_section.iloc[0].tolist()
            df_section = df_section[1:]
            df_section.columns = make_cols_unique(raw_cols)
            section_data[found_section_key] = df_section.reset_index(drop=True)
        else:
            st.warning(f"Warning: Section '{found_section_key}' found but no data rows underneath it.")

    # You might want to parse other stats as well, but for now focus on the main data table
    stats = {}
    for key in section_keys:
        if key not in ["Positions", "Orders", "Deals", "History", "Trades"]: # Skip table headers
            for idx, row in df_raw.iterrows():
                if str(row[0]).strip().startswith(key):
                    stats[key] = " | ".join([str(x) for x in row if pd.notnull(x)])
                    break # Found stat, move to next stat key
    if stats:
        section_data["Stats"] = stats

    return section_data

def preprocess_stmt_data(df):
    # Rename columns to a consistent format
    rename_map = {
        'Open Time': 'Timestamp',
        'Close Time': 'Timestamp', # Assuming Close Time is the primary timestamp for closed trades
        'Time': 'Timestamp',
        'Profit': 'Profit',
        'Risk $': 'Profit', # If statement uses 'Risk $' for profit/loss from closed trades
        'Symbol': 'Asset',
        'Instrument': 'Asset',
        'Lots': 'Lot',
        'Size': 'Lot',
        'Stop Loss': 'SL',
        'Take Profit': 'TP',
        'R': 'RR', # If RR is provided
        'Order': 'Trade ID', # For identifying unique trades
        'Ticket': 'Trade ID'
    }
    df.rename(columns=rename_map, inplace=True)

    # Ensure timestamp column is datetime
    if 'Timestamp' in df.columns:
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')

    # Ensure numerical columns are numeric
    numerical_cols = ['Profit', 'Lot', 'Entry', 'SL', 'TP', 'RR'] # Add more if needed
    for col in numerical_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # Filter out rows with NaN in critical columns if they indicate non-trade rows
    # Example: if Profit is NaN, it might not be a closed trade
    if 'Profit' in df.columns:
        df = df.dropna(subset=['Profit'])

    # Drop duplicate columns after renaming if any (e.g. if both 'Profit' and 'Risk $' existed and mapped to 'Profit')
    df = df.loc[:,~df.columns.duplicated()]

    return df

# เริ่มต้น df_stmt เป็น DataFrame ว่างเปล่า หรือโหลดจาก Google Sheets ถ้ามี
# ใช้ st.session_state เพื่อคงค่า df_stmt ระหว่าง rerun
if 'df_stmt_current' not in st.session_state:
    st.session_state.df_stmt_current = pd.DataFrame()
    # โหลดข้อมูล Statement เก่าจาก Google Sheets ทันทีที่แอปเริ่มทำงานครั้งแรก
    # เพื่อให้ Dashboard แสดงข้อมูลได้ทันที
    df_stmt_from_gsheets = load_statement_from_gsheets()
    if not df_stmt_from_gsheets.empty:
        st.session_state.df_stmt_current = df_stmt_from_gsheets
        st.info("โหลดข้อมูล Statement เดิมจาก Google Sheets แล้ว.")
    else:
        st.info("ยังไม่มีข้อมูล Statement ใน Google Sheets หรือกำลังโหลดครั้งแรก.")


df_stmt = st.session_state.df_stmt_current # ดึงข้อมูลปัจจุบันมาใช้

# ถ้ามีการอัปโหลดไฟล์ใหม่ ให้ประมวลผลและนำไปรวม/แทนที่
if uploaded_files: 
    processed_dfs_from_upload = []
    for file in uploaded_files:
        st.markdown(f"**กำลังประมวลผลไฟล์: {file.name}**")
        try:
            sections = extract_sections_from_file(file)
            current_df = pd.DataFrame()

            # Check for the primary data sections in order of preference
            if "Deals" in sections:
                current_df = sections["Deals"]
            elif "Trades" in sections:
                current_df = sections["Trades"]
            elif "Positions" in sections:
                current_df = sections["Positions"] # Note: Positions are usually open trades, not closed statements
            elif "History" in sections:
                current_df = sections["History"]

            if not current_df.empty:
                current_df = preprocess_stmt_data(current_df)
                processed_dfs_from_upload.append(current_df)
                st.dataframe(current_df.head(5), use_container_width=True) 
            else:
                st.warning(f"⚠︎ ไม่พบข้อมูล Positions, Deals, Trades หรือ History ในไฟล์: {file.name}")
        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการประมวลผลไฟล์ {file.name}: {e}")

    if processed_dfs_from_upload:
        st.subheader("จัดการข้อมูลที่อัปโหลด")

        # รวมข้อมูลที่อัปโหลดทั้งหมดเป็น DataFrame เดียว
        df_new_uploads = pd.concat(processed_dfs_from_upload, ignore_index=True)

        # เสนอตัวเลือกให้ผู้ใช้
        merge_option = st.radio(
            "มีข้อมูล Statement ที่อัปโหลดใหม่แล้ว ต้องการทำอย่างไร?",
            ["แทนที่ข้อมูล Statement ทั้งหมดที่มีอยู่", "รวมข้อมูลใหม่กับข้อมูลเดิม (อาจมีข้อมูลซ้ำ)"],
            index=0 # Default to replace
        )

        if merge_option == "แทนที่ข้อมูล Statement ทั้งหมดที่มีอยู่":
            st.session_state.df_stmt_current = df_new_uploads
            st.info("ข้อมูล Statement ถูกแทนที่ด้วยไฟล์ที่อัปโหลดใหม่แล้ว.")
        else: # รวมข้อมูลใหม่
            if not st.session_state.df_stmt_current.empty:
                # รวมข้อมูลเก่ากับใหม่
                df_combined = pd.concat([st.session_state.df_stmt_current, df_new_uploads], ignore_index=True)

                # ลบข้อมูลซ้ำ (ถ้ามี Trade ID หรือ Timestamp ที่สามารถใช้ระบุรายการที่ไม่ซ้ำได้)
                if 'Trade ID' in df_combined.columns and df_combined['Trade ID'].notna().any():
                    df_combined.drop_duplicates(subset=['Trade ID'], inplace=True)
                    st.info("ข้อมูลรวมและลบรายการซ้ำตาม 'Trade ID' แล้ว.")
                elif 'Timestamp' in df_combined.columns:
                    # อาจจะซับซ้อนขึ้นถ้าไม่มี Trade ID ที่ชัดเจน อาจต้องใช้ Timestamp + Profit + Lot
                    # สำหรับตอนนี้ ให้ drop duplicates ทั้งหมด
                    df_combined.drop_duplicates(inplace=True)
                    st.info("ข้อมูลรวมและลบรายการซ้ำทั้งหมดแล้ว.")
                else:
                    df_combined.drop_duplicates(inplace=True)
                    st.warning("รวมข้อมูลแล้ว แต่ไม่มีคอลัมน์ 'Trade ID' ที่ชัดเจนสำหรับการลบข้อมูลซ้ำที่แม่นยำ.")

                st.session_state.df_stmt_current = df_combined
                st.info("ข้อมูล Statement ถูกรวมกับไฟล์ที่อัปโหลดใหม่แล้ว.")
            else:
                st.session_state.df_stmt_current = df_new_uploads
                st.info("ไม่มีข้อมูล Statement เดิม จึงเพิ่มข้อมูลที่อัปโหลดใหม่เข้ามา.")

        # บันทึกข้อมูล Statement ปัจจุบัน (ที่ได้จากการโหลดเก่า หรืออัปโหลดใหม่) ไปยัง Google Sheets
        if st.button("💾 บันทึกข้อมูล Statement นี้ไปยัง Google Sheets", key="save_uploaded_stmt_to_gsheets"):
            save_statement_to_gsheets(st.session_state.df_stmt_current)
            st.cache_data.clear() # Clear cache เพื่อให้โหลดข้อมูลใหม่ในการรันหน้าต่อไป
            st.rerun() # Re-run เพื่อแสดงข้อมูลล่าสุด

    else:
        st.info("ไม่มีข้อมูล Statement ที่ถูกประมวลผลจากไฟล์ที่อัปโหลดใหม่.")

# แสดงข้อมูล Statement ปัจจุบันที่ใช้ในแอป
if not st.session_state.df_stmt_current.empty:
    st.markdown("---")
    st.subheader("ข้อมูล Statement ปัจจุบัน (สำหรับ Dashboard)")
    st.dataframe(st.session_state.df_stmt_current.head(10), use_container_width=True)
else:
    st.info("ยังไม่มีข้อมูล Statement สำหรับ Dashboard (โปรดอัปโหลดหรือตรวจสอบการโหลดจาก Google Sheets)")

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
            # ปรับปรุงการใช้คอลัมน์ "Symbol" หรือ "Asset"
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
                st.warning("ไม่พบคอลัมน์ 'Asset' หรือ 'Symbol' สำหรับการกรอง")


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
            col1, col2, col3 = st.columns(3)
            with col1:
                mode_filter = st.selectbox("Mode", ["ทั้งหมด"] + sorted(df_log["Mode"].unique().tolist()), key="log_mode_filter")
            with col2:
                asset_filter = st.selectbox("Asset", ["ทั้งหมด"] + sorted(df_log["Asset"].unique().tolist()), key="log_asset_filter")
            with col3:
                date_filter = st.text_input("ค้นหาวันที่ (YYYY-MM-DD)", value="", key="log_date_filter")
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
