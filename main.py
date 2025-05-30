# ===================== SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.express as px
import google.generativeai as genai
import gspread
import plotly.graph_objects as go
import yfinance as yf
import random
import csv
import io # สำคัญ: เพิ่ม import io module เพื่อใช้ io.StringIO ในการอ่าน CSV String

st.set_page_config(page_title="Ultimate-Chart", layout="wide")
acc_balance = 10000 # ยอดคงเหลือเริ่มต้นของบัญชีเทรด

# กำหนดชื่อ Google Sheet และ Worksheet ที่จะใช้เก็บข้อมูล
GOOGLE_SHEET_NAME = "TradeLog"
WORKSHEET_PORTFOLIOS = "Portfolios"
WORKSHEET_PLANNED_LOGS = "PlannedTradeLogs"
WORKSHEET_ACTUAL_TRADES = "ActualTrades"
WORKSHEET_ACTUAL_ORDERS = "ActualOrders"
WORKSHEET_ACTUAL_POSITIONS = "ActualPositions"
WORKSHEET_STATEMENT_SUMMARIES = "StatementSummaries" 

# ฟังก์ชันสำหรับเชื่อมต่อ gspread
# ใช้ st.cache_resource เพื่อให้ GSpread client object ถูกสร้างเพียงครั้งเดียว
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

# ฟังก์ชันสำหรับโหลดข้อมูล Portfolios
# ใช้ st.cache_data และกำหนด ttl (Time-To-Live) เพื่อลดการเรียก API ซ้ำซ้อน
@st.cache_data(ttl=300) # Cache ข้อมูลไว้ 5 นาที
def load_portfolios_from_gsheets():
    gc = get_gspread_client()
    if gc is None:
        return pd.DataFrame()

    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PORTFOLIOS)
        records = worksheet.get_all_records()
        
        if not records:
            return pd.DataFrame()
        
        df_portfolios = pd.DataFrame(records)
        
        cols_to_numeric = ['InitialBalance', 'ProfitTargetPercent', 'DailyLossLimitPercent', 'TotalStopoutPercent', 'ScalingProfitTargetPercent']
        for col in cols_to_numeric:
            if col in df_portfolios.columns:
                df_portfolios[col] = pd.to_numeric(df_portfolios[col], errors='coerce').fillna(0)

        return df_portfolios
    except gspread.exceptions.WorksheetNotFound:
        st.sidebar.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}' ใน Google Sheet '{GOOGLE_SHEET_NAME}'.")
        st.sidebar.info(f"กรุณาสร้าง Worksheet ชื่อ '{WORKSHEET_PORTFOLIOS}' และใส่หัวคอลัมน์พร้อมข้อมูลตัวอย่าง")
        return pd.DataFrame()
    except Exception as e:
        st.sidebar.error(f"❌ เกิดข้อผิดพลาดในการโหลด Portfolios: {e}")
        return pd.DataFrame()

# ===================== SEC 1: PORTFOLIO MANAGEMENT =======================
df_portfolios_gs = load_portfolios_from_gsheets()

st.sidebar.markdown("---")
st.sidebar.subheader("เลือกพอร์ตที่ใช้งาน (Active Portfolio)")

if 'active_portfolio_name_gs' not in st.session_state:
    st.session_state.active_portfolio_name_gs = ""
if 'active_portfolio_id_gs' not in st.session_state:
    st.session_state.active_portfolio_id_gs = None

portfolio_names_list_gs = [""]
if not df_portfolios_gs.empty and 'PortfolioName' in df_portfolios_gs.columns:
    portfolio_names_list_gs.extend(sorted(df_portfolios_gs['PortfolioName'].dropna().unique().tolist()))

if st.session_state.active_portfolio_name_gs not in portfolio_names_list_gs:
    st.session_state.active_portfolio_name_gs = portfolio_names_list_gs[0]

selected_portfolio_name_gs = st.sidebar.selectbox(
    "เลือกพอร์ต:",
    options=portfolio_names_list_gs,
    index=portfolio_names_list_gs.index(st.session_state.active_portfolio_name_gs),
    key='sb_active_portfolio_selector_gs'
)

if selected_portfolio_name_gs != "":
    st.session_state.active_portfolio_name_gs = selected_portfolio_name_gs
    selected_portfolio_row = df_portfolios_gs[df_portfolios_gs['PortfolioName'] == selected_portfolio_name_gs]
    if not selected_portfolio_row.empty and 'PortfolioID' in selected_portfolio_row.columns:
        st.session_state.active_portfolio_id_gs = selected_portfolio_row['PortfolioID'].iloc[0]
    else:
        st.session_state.active_portfolio_id_gs = None
        st.sidebar.warning("ไม่พบ PortfolioID สำหรับพอร์ตที่เลือก. กรุณาตรวจสอบข้อมูลในชีต 'Portfolios'.")
else:
    st.session_state.active_portfolio_name_gs = ""
    st.session_state.active_portfolio_id_gs = None

if st.session_state.active_portfolio_name_gs and not df_portfolios_gs.empty:
    current_portfolio_rules = df_portfolios_gs[df_portfolios_gs['PortfolioName'] == st.session_state.active_portfolio_name_gs]
    if not current_portfolio_rules.empty:
        st.sidebar.markdown(f"**💡 ข้อมูลพอร์ต '{st.session_state.active_portfolio_name_gs}'**")
        if 'InitialBalance' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Initial Balance:** {current_portfolio_rules['InitialBalance'].iloc[0]:,.2f} USD")
        if 'ProfitTargetPercent' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Profit Target:** {current_portfolio_rules['ProfitTargetPercent'].iloc[0]:.1f}%")
        if 'DailyLossLimitPercent' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Daily Loss Limit:** {current_portfolio_rules['DailyLossLimitPercent'].iloc[0]:.1f}%")
        if 'TotalStopoutPercent' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Total Stopout:** {current_portfolio_rules['TotalStopoutPercent'].iloc[0]:.1f}%")
        if 'Status' in current_portfolio_rules.columns:
            st.sidebar.write(f"- **Status:** {current_portfolio_rules['Status'].iloc[0]}")
    else:
        st.sidebar.warning("ไม่พบรายละเอียดสำหรับพอร์ตที่เลือก.")
elif df_portfolios_gs.empty:
    st.sidebar.warning("ไม่พบข้อมูล Portfolio ใน Google Sheets หรือเกิดข้อผิดพลาดในการโหลด.")
    st.sidebar.info("กรุณาเพิ่มข้อมูลในชีต 'Portfolios' และตรวจสอบการตั้งค่า Google Sheets.")

# ========== Function Utility ==========
def get_today_drawdown(log_source_df, acc_balance):
    if log_source_df.empty:
        return 0
    today_str = datetime.now().strftime("%Y-%m-%d")
    try:
        log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)

        df_today = log_source_df[log_source_df["Timestamp"].dt.strftime("%Y-%m-%d") == today_str]
        drawdown = df_today["Risk $"].sum()
        return drawdown
    except KeyError as e:
        return 0
    except Exception as e:
        return 0

def get_performance(log_source_df, mode="week"):
    if log_source_df.empty:
        return 0, 0, 0
    
    try:
        log_source_df['Timestamp'] = pd.to_datetime(log_source_df['Timestamp'], errors='coerce')
        log_source_df['Risk $'] = pd.to_numeric(log_source_df['Risk $'], errors='coerce').fillna(0)
        now = datetime.now()

        if mode == "week":
            week_start_date = now - pd.Timedelta(days=now.weekday())
            df_period = log_source_df[log_source_df["Timestamp"] >= week_start_date]
        else:  # month
            month_start_date = now.replace(day=1)
            df_period = log_source_df[log_source_df["Timestamp"] >= month_start_date]
        
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

# ===================== SEC 2: SIDEBAR - TRADE SETUP & INPUTS =======================
st.sidebar.header("🎛️ Trade Setup")

# ===================== SEC 2.1: COMMON INPUTS & MODE SELECTION =======================
drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=st.session_state.get("drawdown_limit_pct", 2.0),
    step=0.1, format="%.1f",
    key="drawdown_limit_pct"
)

mode = st.sidebar.radio("Trade Mode", ["FIBO", "CUSTOM"], horizontal=True, key="mode")

if st.sidebar.button("🔄 Reset Form"):
    risk_keep = st.session_state.get("risk_pct", 1.0)
    asset_keep = st.session_state.get("asset", "XAUUSD")
    drawdown_limit_keep = st.session_state.get("drawdown_limit_pct", 2.0)
    
    keys_to_keep = {"risk_pct", "asset", "drawdown_limit_pct", "mode", 
                    "active_portfolio_name_gs", "active_portfolio_id_gs",
                    "gcp_service_account"}

    for k in list(st.session_state.keys()):
        if k not in keys_to_keep:
            del st.session_state[k]

    st.session_state["risk_pct"] = risk_keep
    st.session_state["asset"] = asset_keep
    st.session_state["drawdown_limit_pct"] = drawdown_limit_keep
    st.session_state["fibo_flags"] = [False] * 5
    st.rerun()

# ===================== SEC 2.2: FIBO TRADE DETAILS =======================
if mode == "FIBO":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value=st.session_state.get("asset", "XAUUSD"), key="asset")
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            value=st.session_state.get("risk_pct", 1.0),
            step=0.01,
            format="%.2f",
            key="risk_pct"
        )
    with col3:
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True, key="fibo_direction")

    col4, col5 = st.sidebar.columns(2)
    with col4:
        swing_high = st.text_input("High", key="swing_high")
    with col5:
        swing_low = st.text_input("Low", key="swing_low")

    st.sidebar.markdown("**📐 Entry Fibo Levels**")
    fibos = [0.114, 0.25, 0.382, 0.5, 0.618]
    labels = [f"{l:.3f}" for l in fibos]
    cols = st.sidebar.columns(len(fibos))

    if "fibo_flags" not in st.session_state:
        st.session_state.fibo_flags = [True] * len(fibos)

    fibo_selected_flags = []
    for i, col in enumerate(cols):
        checked = col.checkbox(labels[i], value=st.session_state.fibo_flags[i], key=f"fibo_cb_{i}")
        fibo_selected_flags.append(checked)

    st.session_state.fibo_flags = fibo_selected_flags

    try:
        high_val = float(swing_high) if swing_high else 0
        low_val = float(swing_low) if swing_low else 0
        if swing_high and swing_low and high_val <= low_val:
            st.sidebar.warning("High ต้องมากกว่า Low!")
    except ValueError:
        if swing_high or swing_low:
            st.sidebar.warning("กรุณาใส่ High/Low เป็นตัวเลขที่ถูกต้อง")
    except Exception:
        pass

    if 'risk_pct' in st.session_state and st.session_state.risk_pct <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")

    st.sidebar.markdown("---")
    try:
        high_preview = float(swing_high)
        low_preview = float(swing_low)
        if high_preview > low_preview and any(st.session_state.fibo_flags):
            st.sidebar.markdown("**Preview (เบื้องต้น):**")
            first_selected_fibo_index = st.session_state.fibo_flags.index(True)
            if direction == "Long":
                preview_entry = low_preview + (high_preview - low_preview) * fibos[first_selected_fibo_index]
            else:
                preview_entry = high_preview - (high_preview - low_preview) * fibos[first_selected_fibo_index]
            st.sidebar.markdown(f"Entry แรกที่เลือก ≈ **{preview_entry:.2f}**")
            st.sidebar.caption("Lot/TP/ผลลัพธ์เต็มอยู่ด้านล่าง (ใน Strategy Summary)")
    except Exception:
        pass

    save_fibo = st.sidebar.button("💾 Save Plan (FIBO)", key="save_fibo")

# ===================== SEC 2.3: CUSTOM TRADE DETAILS =======================
elif mode == "CUSTOM":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value=st.session_state.get("asset", "XAUUSD"), key="asset_custom")
    with col2:
        risk_pct = st.number_input(
            "Risk %",
            min_value=0.01,
            max_value=100.0,
            value=st.session_state.get("risk_pct_custom", 1.00),
            step=0.01,
            format="%.2f",
            key="risk_pct_custom"
        )
    with col3:
        n_entry = st.number_input(
            "จำนวนไม้",
            min_value=1,
            max_value=10,
            value=st.session_state.get("n_entry_custom", 2),
            step=1,
            key="n_entry_custom"
        )

    st.sidebar.markdown("**กรอกข้อมูลแต่ละไม้**")
    custom_inputs = []
    current_custom_risk_pct = st.session_state.get("risk_pct_custom", 1.0)
    risk_per_trade = current_custom_risk_pct / 100
    risk_dollar_total = acc_balance * risk_per_trade
    num_entries_val = st.session_state.get("n_entry_custom", 1)
    risk_dollar_per_entry = risk_dollar_total / num_entries_val if num_entries_val > 0 else 0

    for i in range(int(num_entries_val)):
        st.sidebar.markdown(f"--- ไม้ที่ {i+1} ---")
        col_e, col_s, col_t = st.sidebar.columns(3)
        with col_e:
            entry = st.text_input(f"Entry {i+1}", value=st.session_state.get(f"custom_entry_{i}", "0.00"), key=f"custom_entry_{i}")
        with col_s:
            sl = st.text_input(f"SL {i+1}", value=st.session_state.get(f"custom_sl_{i}", "0.00"), key=f"custom_sl_{i}")
        with col_t:
            tp = st.text_input(f"TP {i+1}", value=st.session_state.get(f"custom_tp_{i}", "0.00"), key=f"custom_tp_{i}")
        
        try:
            entry_val = float(entry)
            sl_val = float(sl)
            stop = abs(entry_val - sl_val)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            lot_display = f"Lot: {lot:.2f}" if stop > 0 else "Lot: - (Invalid SL)"
            risk_per_entry_display = f"Risk$ ต่อไม้: {risk_dollar_per_entry:.2f}"
        except ValueError:
            lot_display = "Lot: - (Error)"
            risk_per_entry_display = "Risk$ ต่อไม้: - (Error)"
            stop = None
        except Exception:
            lot_display = "Lot: -"
            risk_per_entry_display = "Risk$ ต่อไม้: -"
            stop = None

        try:
            if stop is not None and stop > 0:
                tp_rr3_info = f"Stop: {stop:.2f}"
            else:
                tp_rr3_info = "TP (RR=3): - (SL Error)"
        except Exception:
            tp_rr3_info = "TP (RR=3): -"
        
        st.sidebar.caption(f"{lot_display} | {risk_per_entry_display} | {tp_rr3_info}")
        custom_inputs.append({"entry": entry, "sl": sl, "tp": tp})

    if current_custom_risk_pct <= 0:
        st.sidebar.warning("Risk% ต้องมากกว่า 0")
    save_custom = st.sidebar.button("💾 Save Plan (CUSTOM)", key="save_custom")

# ===================== SEC 3: SIDEBAR - CALCULATIONS, SUMMARY & ACTIONS =======================
st.sidebar.markdown("---")
st.sidebar.markdown("### 🧾 Strategy Summary")

entry_data = []
custom_entries_summary = []

if mode == "FIBO":
    try:
        current_fibo_risk_pct = st.session_state.get("risk_pct", 1.0)
        current_fibo_direction = st.session_state.get("fibo_direction", "Long")
        current_swing_high = st.session_state.get("swing_high", "")
        current_swing_low = st.session_state.get("swing_low", "")
        current_fibo_flags = st.session_state.get("fibo_flags", [False]*5)

        high = float(current_swing_high)
        low = float(current_swing_low)
        selected_fibo_levels = [fibos[i] for i, sel in enumerate(current_fibo_flags) if sel]
        n = len(selected_fibo_levels)
        risk_per_trade = current_fibo_risk_pct / 100
        risk_dollar_total = acc_balance * risk_per_trade
        risk_dollar_per_entry = risk_dollar_total / n if n > 0 else 0
        
        for idx, fibo_level_val in enumerate(selected_fibo_levels):
            if current_fibo_direction == "Long":
                entry = low + (high - low) * fibo_level_val
                sl = low
            else:
                entry = high - (high - low) * fibo_level_val
                sl = high
            
            stop = abs(entry - sl)
            lot = risk_dollar_per_entry / stop if stop > 0 else 0
            risk_val = stop * lot if stop > 0 else 0

            if stop > 0:
                if current_fibo_direction == "Long":
                    tp1 = entry + (stop * 1.618)
                else:
                    tp1 = entry - (stop * 1.618)
                tp_display = f"{tp1:.2f}"
            else:
                tp_display = "-"

            entry_data.append({
                "Fibo Level": f"{fibo_level_val:.3f}",
                "Entry": f"{entry:.2f}",
                "SL": f"{sl:.2f}",
                "TP": tp_display, 
                "Lot": f"{lot:.2f}" if stop > 0 else "0.00",
                "Risk $": f"{risk_val:.2f}" if stop > 0 else "0.00",
            })
        if entry_data:
            entry_df_summary = pd.DataFrame(entry_data)
            st.sidebar.write(f"**Total Lots:** {entry_df_summary['Lot'].astype(float).sum():.2f}")
            st.sidebar.write(f"**Total Risk $:** {entry_df_summary['Risk $'].astype(float).sum():.2f}")
    except ValueError:
        if current_swing_high or current_swing_low:
             st.sidebar.warning("กรอก High/Low ให้ถูกต้องเพื่อดู Summary")
    except Exception as e:
        pass 
elif mode == "CUSTOM":
    try:
        num_entries_val_summary = st.session_state.get("n_entry_custom", 1)
        current_custom_risk_pct_summary = st.session_state.get("risk_pct_custom", 1.0)

        risk_per_trade_summary = current_custom_risk_pct_summary / 100
        risk_dollar_total_summary = acc_balance * risk_per_trade_summary
        risk_dollar_per_entry_summary = risk_dollar_total_summary / num_entries_val_summary if num_entries_val_summary > 0 else 0
        
        rr_list = []
        for i in range(int(num_entries_val_summary)):
            entry_val_str = st.session_state.get(f"custom_entry_{i}", "0.00")
            sl_val_str = st.session_state.get(f"custom_sl_{i}", "0.00")
            tp_val_str = st.session_state.get(f"custom_tp_{i}", "0.00")

            entry_val = float(entry_val_str)
            sl_val = float(sl_val_str)
            tp_val = float(tp_val_str)

            stop = abs(entry_val - sl_val)
            target = abs(tp_val - entry_val)
            lot = risk_dollar_per_entry_summary / stop if stop > 0 else 0
            rr = (target / stop) if stop > 0 else 0
            rr_list.append(rr)
            custom_entries_summary.append({
                "Entry": f"{entry_val:.2f}",
                "SL": f"{sl_val:.2f}",
                "TP": f"{tp_val:.2f}",
                "Lot": f"{lot:.2f}" if stop > 0 else "0.00",
                "Risk $": f"{risk_dollar_per_entry_summary:.2f}" if stop > 0 else "0.00",
                "RR": f"{rr:.2f}" if stop > 0 else "0.00"
            })
        if custom_entries_summary:
            custom_df_summary = pd.DataFrame(custom_entries_summary)
            st.sidebar.write(f"**Total Lots:** {custom_df_summary['Lot'].astype(float).sum():.2f}")
            st.sidebar.write(f"**Total Risk $:** {custom_df_summary['Risk $'].astype(float).sum():.2f}")
            avg_rr = np.mean([r for r in rr_list if r > 0]) if any(r > 0 for r in rr_list) else 0
            if avg_rr > 0 :
                st.sidebar.write(f"**Average RR:** {avg_rr:.2f}")
    except ValueError:
        st.sidebar.warning("กรอก Entry/SL/TP ให้ถูกต้องเพื่อดู Summary")
    except Exception as e:
        pass

# ===================== SEC 3.1: SCALING MANAGER =======================
with st.sidebar.expander("⚙️ Scaling Manager Settings", expanded=False):
    scaling_step = st.number_input(
        "Scaling Step (%)", min_value=0.01, max_value=1.0, 
        value=st.session_state.get('scaling_step', 0.25), 
        step=0.01, format="%.2f", key='scaling_step'
    )
    min_risk_pct = st.number_input(
        "Minimum Risk %", min_value=0.01, max_value=100.0, 
        value=st.session_state.get('min_risk_pct', 0.5), 
        step=0.01, format="%.2f", key='min_risk_pct'
    )
    max_risk_pct = st.number_input(
        "Maximum Risk %", min_value=0.01, max_value=100.0, 
        value=st.session_state.get('max_risk_pct', 5.0), 
        step=0.01, format="%.2f", key='max_risk_pct'
    )
    scaling_mode = st.radio(
        "Scaling Mode", ["Manual", "Auto"], 
        index=0 if st.session_state.get('scaling_mode', 'Manual') == 'Manual' else 1,
        horizontal=True, key='scaling_mode'
    )

# ===================== SEC 3.1.1: SCALING SUGGESTION LOGIC =======================
df_planned_logs_for_scaling = pd.DataFrame()
gc_scaling = get_gspread_client()
if gc_scaling:
    try:
        sh_scaling = gc_scaling.open(GOOGLE_SHEET_NAME)
        ws_planned_logs = sh_scaling.worksheet(WORKSHEET_PLANNED_LOGS)
        records_scaling = ws_planned_logs.get_all_records()
        if records_scaling:
            df_planned_logs_for_scaling = pd.DataFrame(records_scaling)
    except Exception as e:
        pass

winrate_perf, gain_perf, total_trades_perf = get_performance(df_planned_logs_for_scaling.copy(), mode="week")

current_risk_for_scaling = 1.0
if mode == "FIBO":
    current_risk_for_scaling = st.session_state.get("risk_pct", 1.0)
elif mode == "CUSTOM":
    current_risk_for_scaling = st.session_state.get("risk_pct_custom", 1.0)

scaling_step_val = st.session_state.get('scaling_step', 0.25)
max_risk_pct_val = st.session_state.get('max_risk_pct', 5.0)
min_risk_pct_val = st.session_state.get('min_risk_pct', 0.5)
current_scaling_mode = st.session_state.get('scaling_mode', 'Manual')

suggest_risk = current_risk_for_scaling
scaling_msg = "Risk% คงที่ (ยังไม่มีข้อมูล Performance เพียงพอ หรือ Performance อยู่ในเกณฑ์)"

if total_trades_perf > 0:
    if winrate_perf > 55 and gain_perf > 0.02 * acc_balance:
        suggest_risk = min(current_risk_for_scaling + scaling_step_val, max_risk_pct_val)
        scaling_msg = f"🎉 ผลงานดี! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f}. แนะนำเพิ่ม Risk% เป็น {suggest_risk:.2f}%"
    elif winrate_perf < 45 or gain_perf < 0:
        suggest_risk = max(current_risk_for_scaling - scaling_step_val, min_risk_pct_val)
        scaling_msg = f"⚠️ ควรลด Risk%! Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f}. แนะนำลด Risk% เป็น {suggest_risk:.2f}%"
    else:
        scaling_msg = f"Risk% คงที่ (Winrate {winrate_perf:.1f}%, กำไร {gain_perf:.2f})"

st.sidebar.info(scaling_msg)

if current_scaling_mode == "Manual" and abs(suggest_risk - current_risk_for_scaling) > 0.001:
    if st.sidebar.button(f"ปรับ Risk% เป็น {suggest_risk:.2f}%"):
        if mode == "FIBO":
            st.session_state.risk_pct = suggest_risk
        elif mode == "CUSTOM":
            st.session_state.risk_pct_custom = suggest_risk
        st.rerun()
elif current_scaling_mode == "Auto":
    if abs(suggest_risk - current_risk_for_scaling) > 0.001:
        if mode == "FIBO":
            st.session_state.risk_pct = suggest_risk
        elif mode == "CUSTOM":
            st.session_state.risk_pct_custom = suggest_risk

# ===================== SEC 3.2: SAVE PLAN ACTION & DRAWDOWN LOCK =======================
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
        expected_headers = [
            "LogID", "PortfolioID", "PortfolioName", "Timestamp", "Asset", "Mode", "Direction",
            "Risk %", "Fibo Level", "Entry", "SL", "TP", "Lot", "Risk $", "RR"
        ]
        current_headers = []
        if ws.row_count > 0:
            try:
                current_headers = ws.row_values(1)
            except Exception:
                current_headers = []
        
        if not current_headers or all(h == "" for h in current_headers) :
            ws.append_row(expected_headers, value_input_option='USER_ENTERED')
        elif set(current_headers) != set(expected_headers) and any(h!="" for h in current_headers):
            st.warning(f"Worksheet '{WORKSHEET_PLANNED_LOGS}' has incorrect headers. Please ensure headers match: {', '.join(expected_headers)}")

        for idx, plan_entry in enumerate(plan_data_list):
            log_id = f"{timestamp_now.strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}-{idx}"
            row_data = {
                "LogID": log_id,
                "PortfolioID": portfolio_id,
                "PortfolioName": portfolio_name,
                "Timestamp": timestamp_now.strftime("%Y-%m-%d %H:%M:%S"),
                "Asset": asset_name,
                "Mode": trade_mode_arg,
                "Direction": trade_direction,
                "Risk %": risk_percentage,
                "Fibo Level": plan_entry.get("Fibo Level", ""),
                "Entry": plan_entry.get("Entry", "0.00"),
                "SL": plan_entry.get("SL", "0.00"),
                "TP": plan_entry.get("TP", "0.00"),
                "Lot": plan_entry.get("Lot", "0.00"),
                "Risk $": plan_entry.get("Risk $", "0.00"),
                "RR": plan_entry.get("RR", "")
            }
            rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])

        if rows_to_append:
            ws.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            return True
        return False
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ ไม่พบ Worksheet ชื่อ '{WORKSHEET_PLANNED_LOGS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
        return False
    except Exception as e:
        st.error(f"❌ เกิดข้อผิดพลาดในการบันทึกแผนไปยัง Google Sheets: {e}")
        return False

df_drawdown_check = pd.DataFrame()
gc_drawdown = get_gspread_client()
if gc_drawdown:
    try:
        sh_drawdown = gc_drawdown.open(GOOGLE_SHEET_NAME)
        ws_planned_logs_drawdown = sh_drawdown.worksheet(WORKSHEET_PLANNED_LOGS)
        records_drawdown = ws_planned_logs_drawdown.get_all_records()
        if records_drawdown:
            df_drawdown_check = pd.DataFrame(records_drawdown)
    except Exception as e:
        pass

drawdown_today = get_today_drawdown(df_drawdown_check.copy(), acc_balance)
drawdown_limit_pct_val = st.session_state.get('drawdown_limit_pct', 2.0)
drawdown_limit_abs = -acc_balance * (drawdown_limit_pct_val / 100)

if drawdown_today < 0:
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** <font color='red'>{drawdown_today:,.2f} USD</font>", unsafe_allow_html=True)
else:
    st.sidebar.markdown(f"**ขาดทุนจากแผนวันนี้:** {drawdown_today:,.2f} USD")

active_portfolio_id = st.session_state.get('active_portfolio_id_gs', None)
active_portfolio_name = st.session_state.get('active_portfolio_name_gs', None)

asset_to_save = ""
risk_pct_to_save = 0.0
direction_to_save = "N/A"
data_to_save = []

if mode == "FIBO":
    asset_to_save = st.session_state.get("asset", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct", 1.0)
    direction_to_save = st.session_state.get("fibo_direction", "Long")
    data_to_save = entry_data
    save_button_pressed = save_fibo
elif mode == "CUSTOM":
    asset_to_save = st.session_state.get("asset_custom", "XAUUSD")
    risk_pct_to_save = st.session_state.get("risk_pct_custom", 1.0)
    direction_to_save = st.session_state.get("custom_direction_for_log", "N/A")
    data_to_save = custom_entries_summary
    save_button_pressed = save_custom

if save_button_pressed and data_to_save:
    if drawdown_today <= drawdown_limit_abs and drawdown_limit_abs < 0 :
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนจากแผนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit_abs):,.2f} ({drawdown_limit_pct_val:.1f}%)"
        )
    elif not active_portfolio_id:
        st.sidebar.error("กรุณาเลือกพอร์ตที่ใช้งานก่อนบันทึกแผน")
    else:
        try:
            if save_plan_to_gsheets(data_to_save, mode, asset_to_save, risk_pct_to_save, direction_to_save, active_portfolio_id, active_portfolio_name):
                st.sidebar.success(f"บันทึกแผน ({mode}) สำหรับพอร์ต '{active_portfolio_name}' ลง Google Sheets สำเร็จ!")
                st.balloons()
            else:
                st.sidebar.error(f"Save ({mode}) ไปยัง Google Sheets ไม่สำเร็จ.")
        except Exception as e:
            st.sidebar.error(f"Save ({mode}) ไม่สำเร็จ: {e}")

# ===================== SEC 4: MAIN AREA - ENTRY PLAN DETAILS TABLE =======================
with st.expander("📋 Entry Table (FIBO/CUSTOM)", expanded=True):
    if mode == "FIBO":
        col1_main, col2_main = st.columns(2)
        with col1_main:
            st.markdown("### 🎯 Entry Levels (FIBO)")
            if entry_data:
                entry_df_main = pd.DataFrame(entry_data)
                st.dataframe(entry_df_main, hide_index=True, use_container_width=True)
            else:
                st.info("กรอกข้อมูล High/Low และเลือก Fibo Level ใน Sidebar เพื่อดู Entry Levels.")
        with col2_main:
            st.markdown("### 🎯 Take Profit Zones (FIBO)")
            try:
                current_swing_high_tp = st.session_state.get("swing_high", "")
                current_swing_low_tp = st.session_state.get("swing_low", "")
                current_fibo_direction_tp = st.session_state.get("fibo_direction", "Long")

                high_tp = float(current_swing_high_tp)
                low_tp = float(current_swing_low_tp)

                if high_tp > low_tp:
                    if current_fibo_direction_tp == "Long":
                        tp1_main = low_tp + (high_tp - low_tp) * 1.618
                        tp2_main = low_tp + (high_tp - low_tp) * 2.618
                        tp3_main = low_tp + (high_tp - low_tp) * 4.236
                    else:
                        tp1_main = high_tp - (high_tp - low_tp) * 1.618
                        tp2_main = high_tp - (high_tp - low_tp) * 2.618
                        tp3_main = high_tp - (high_tp - low_tp) * 4.236
                    tp_df_main = pd.DataFrame({
                        "TP Zone": ["TP1 (1.618)", "TP2 (2.618)", "TP3 (4.236)"],
                        "Price": [f"{tp1_main:.2f}", f"{tp2_main:.2f}", f"{tp3_main:.2f}"]
                    })
                    st.dataframe(tp_df_main, hide_index=True, use_container_width=True)
                else:
                    if current_swing_high_tp or current_swing_low_tp :
                        st.warning("📌 High ต้องมากกว่า Low เพื่อคำนวณ TP.")
                    else:
                        st.info("📌 กรอก High/Low ใน Sidebar เพื่อดู TP.")
            except ValueError:
                 if current_swing_high_tp or current_swing_low_tp :
                    st.warning("📌 กรอก High/Low เป็นตัวเลขที่ถูกต้องเพื่อคำนวณ TP.")
                 else:
                    st.info("📌 กรอก High/Low ใน Sidebar เพื่อดู TP.")
            except Exception:
                st.info("📌 เกิดข้อผิดพลาดในการคำนวณ TP.")

    elif mode == "CUSTOM":
        st.markdown("### 🎯 Entry & Take Profit Zones (CUSTOM)")
        if custom_entries_summary:
            custom_df_main = pd.DataFrame(custom_entries_summary)
            st.dataframe(custom_df_main, hide_index=True, use_container_width=True)
            for i, row_data_dict in enumerate(custom_entries_summary):
                try:
                    rr_val_str = row_data_dict.get("RR", "0")
                    rr_val = float(rr_val_str)
                    if rr_val < 2 and rr_val > 0:
                        st.warning(f"🎯 Entry {i+1} มี RR ค่อนข้างต่ำ ({rr_val:.2f}) — ลองปรับ TP/SL เพื่อ Risk:Reward ที่ดีขึ้น")
                except ValueError:
                    pass
                except Exception:
                    pass
        else:
            st.info("กรอกข้อมูล Custom ใน Sidebar เพื่อดู Entry & TP Zones.")

# ===================== SEC 5: MAIN AREA - CHART VISUALIZER =======================
with st.expander("📈 Chart Visualizer", expanded=True):
    asset_to_display = "OANDA:XAUUSD"
    current_asset_input = ""
    if mode == "FIBO":
        current_asset_input = st.session_state.get("asset", "XAUUSD")
    elif mode == "CUSTOM":
        current_asset_input = st.session_state.get("asset_custom", "XAUUSD")
    
    if current_asset_input.upper() == "XAUUSD":
        asset_to_display = "OANDA:XAUUSD"
    elif current_asset_input.upper() == "EURUSD":
        asset_to_display = "OANDA:EURUSD"
    elif current_asset_input:
        asset_to_display = current_asset_input.upper()

    if 'plot_data' in st.session_state and st.session_state['plot_data']:
        asset_from_log = st.session_state['plot_data'].get('Asset', asset_to_display)
        if asset_from_log.upper() == "XAUUSD":
            asset_to_display = "OANDA:XAUUSD"
        elif asset_from_log.upper() == "EURUSD":
            asset_to_display = "OANDA:EURUSD"
        elif asset_from_log:
            asset_to_display = asset_from_log.upper()
        st.info(f"แสดงกราฟ TradingView สำหรับ: {asset_to_display} (จาก Log Viewer)")
    else:
        st.info(f"แสดงกราฟ TradingView สำหรับ: {asset_to_display} (จาก Input ปัจจุบัน)")

    tradingview_html = f"""
    <div class="tradingview-widget-container">
      <div id="tradingview_legendary"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "width": "100%",
        "height": 600,
        "symbol": "{asset_to_display}",
        "interval": "15",
        "timezone": "Asia/Bangkok",
        "theme": "dark",
        "style": "1",
        "locale": "th",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "withdateranges": true,
        "allow_symbol_change": true,
        "hide_side_toolbar": false,
        "details": true,
        "hotlist": true,
        "calendar": true,
        "container_id": "tradingview_legendary"
      }});
      </script>
    </div>
    """
    st.components.v1.html(tradingview_html, height=620)

# ===================== SEC 6: MAIN AREA - AI ASSISTANT =======================
with st.expander("🤖 AI Assistant", expanded=True):
    df_ai_logs = pd.DataFrame()
    gc_ai = get_gspread_client()
    if gc_ai:
        try:
            sh_ai = gc_ai.open(GOOGLE_SHEET_NAME)
            ws_ai_logs = sh_ai.worksheet(WORKSHEET_PLANNED_LOGS)
            records_ai = ws_ai_logs.get_all_records()
            if records_ai:
                df_ai_logs = pd.DataFrame(records_ai)
                if 'Risk $' in df_ai_logs.columns:
                    df_ai_logs['Risk $'] = pd.to_numeric(df_ai_logs['Risk $'], errors='coerce').fillna(0)
                if 'RR' in df_ai_logs.columns:
                    df_ai_logs['RR'] = pd.to_numeric(df_ai_logs['RR'], errors='coerce')
                if 'Timestamp' in df_ai_logs.columns:
                    df_ai_logs['Timestamp'] = pd.to_datetime(df_ai_logs['Timestamp'], errors='coerce')
        except Exception as e:
            pass
            
    if df_ai_logs.empty:
        st.info("ยังไม่มีข้อมูลแผนเทรดใน Log (Google Sheets) สำหรับ AI Assistant")
    else:
        total_trades_ai = df_ai_logs.shape[0]
        win_trades_ai = df_ai_logs[df_ai_logs["Risk $"] > 0].shape[0] if "Risk $" in df_ai_logs.columns else 0
        winrate_ai = (100 * win_trades_ai / total_trades_ai) if total_trades_ai > 0 else 0
        gross_profit_ai = df_ai_logs["Risk $"].sum() if "Risk $" in df_ai_logs.columns else 0
        
        avg_rr_ai = df_ai_logs["RR"].mean() if "RR" in df_ai_logs.columns and not df_ai_logs["RR"].dropna().empty else None

        max_drawdown_ai = 0
        if "Risk $" in df_ai_logs.columns:
            df_ai_logs_sorted = df_ai_logs.sort_values(by="Timestamp") if "Timestamp" in df_ai_logs.columns else df_ai_logs
            current_balance_sim = acc_balance
            peak_balance_sim = acc_balance
            for pnl_val in df_ai_logs_sorted["Risk $"]:
                current_balance_sim += pnl_val
                if current_balance_sim > peak_balance_sim:
                    peak_balance_sim = current_balance_sim
                drawdown_val = peak_balance_sim - current_balance_sim
                if drawdown_val > max_drawdown_ai:
                    max_drawdown_ai = drawdown_val
        
        win_day_ai = "-"
        loss_day_ai = "-"
        if "Timestamp" in df_ai_logs.columns and "Risk $" in df_ai_logs.columns and not df_ai_logs["Timestamp"].isnull().all():
            df_ai_logs["Weekday"] = df_ai_logs["Timestamp"].dt.day_name()
            daily_pnl = df_ai_logs.groupby("Weekday")["Risk $"].sum()
            if not daily_pnl.empty:
                win_day_ai = daily_pnl.idxmax() if daily_pnl.max() > 0 else "-"
                loss_day_ai = daily_pnl.idxmin() if daily_pnl.min() < 0 else "-"

        st.markdown("### 🧠 AI Intelligence Report (จากข้อมูลแผนเทรด)")
        st.write(f"- **จำนวนแผนเทรดทั้งหมด:** {total_trades_ai:,}")
        st.write(f"- **Winrate (ตามแผน):** {winrate_ai:.2f}% (คำนวณจาก Risk $ > 0)")
        st.write(f"- **กำไร/ขาดทุนสุทธิ (ตามแผน):** {gross_profit_ai:,.2f} USD")
        if avg_rr_ai is not None:
            st.write(f"- **RR เฉลี่ย (ตามแผน):** {avg_rr_ai:.2f}")
        st.write(f"- **Max Drawdown (จำลองจากแผน):** {max_drawdown_ai:,.2f} USD")
        st.write(f"- **วันที่ทำกำไรดีที่สุด (ตามแผน):** {win_day_ai}")
        st.write(f"- **วันที่ขาดทุนมากที่สุด (ตามแผน):** {loss_day_ai}")

        st.markdown("### 🤖 AI Insight (จากกฎที่คุณกำหนดเอง)")
        insight_messages = []
        if winrate_ai >= 60:
            insight_messages.append("✅ Winrate (ตามแผน) สูง: ระบบการวางแผนมีแนวโน้มที่ดี")
        elif winrate_ai < 40 and total_trades_ai > 10 :
            insight_messages.append("⚠️ Winrate (ตามแผน) ต่ำ: ควรทบทวนกลยุทธ์การวางแผน")
        
        if avg_rr_ai is not None and avg_rr_ai < 1.5 and total_trades_ai > 5:
            insight_messages.append("📉 RR เฉลี่ย (ตามแผน) ต่ำกว่า 1.5: อาจต้องพิจารณาการตั้ง TP/SL เพื่อ Risk:Reward ที่เหมาะสมขึ้น")
        
        if max_drawdown_ai > acc_balance * 0.10:
            insight_messages.append("🚨 Max Drawdown (จำลองจากแผน) ค่อนข้างสูง: ควรระมัดระวังการบริหารความเสี่ยง")
        
        if not insight_messages:
            insight_messages = ["ดูเหมือนว่าข้อมูลแผนเทรดปัจจุบันยังไม่มีจุดที่น่ากังวลเป็นพิเศษตามเกณฑ์ที่ตั้งไว้"]
        
        for msg in insight_messages:
            if "✅" in msg: st.success(msg)
            elif "⚠️" in msg or "📉" in msg: st.warning(msg)
            elif "🚨" in msg: st.error(msg)
            else: st.info(msg)

# ===================== SEC 7: MAIN AREA - STATEMENT IMPORT & PROCESSING =======================
with st.expander("📂 SEC 7: Ultimate Chart Dashboard Import & Processing", expanded=True):
    st.markdown("### 📊 จัดการ Statement และข้อมูลดิบ")

    # --- ฟังก์ชันสำหรับแยกข้อมูลจากเนื้อหาไฟล์ Statement (CSV) ---
    def extract_data_from_report_content(file_content):
        extracted_data = {}

        # Define raw headers from the CSV report for identification
        # ลบคอมม่าที่อยู่ท้ายสุดของ Header Template ออก
        section_raw_headers = {
            "Positions": "Time,Position,Symbol,Type,Volume,Price,S / L,T / P,Time,Price,Commission,Swap,Profit",
            "Orders": "Open Time,Order,Symbol,Type,Volume,Price,S / L,T / P,Time,State,,Comment", # ปรับให้ไม่มีคอมม่าที่เกินมา
            "Deals": "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment",
        }
        
        # Define expected clean column names for each section (Hardcoded for robust parsing)
        expected_cleaned_columns = {
            "Positions": ["Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time", "Close_Price", "Commission", "Swap", "Profit"],
            "Orders": ["Open_Time", "Order", "Symbol", "Type", "Volume", "Price", "S_L", "T_P", "Close_Time", "State", "Comment"], # ปรับให้มีแค่ Comment
            "Deals": ["Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order", "Commission", "Fee", "Swap", "Profit", "Balance", "Comment"],
        }

        lines = file_content.strip().split('\n')
        
        section_order = ["Positions", "Orders", "Deals"]
        
        # Find the start line indices for each section's header
        section_start_indices = {}
        for section_name, header_template in section_raw_headers.items():
            for i, line in enumerate(lines):
                line_stripped = line.strip()
                # ตรวจสอบการ match ของ header โดยใช้ `startswith` และความยาวที่ใกล้เคียง
                if line_stripped.startswith(header_template.split(',')[0]) and \
                   len(line_stripped.split(',')) >= (len(header_template.split(',')) - 2) and \
                   len(line_stripped.split(',')) <= (len(header_template.split(',')) + 2):
                    section_start_indices[section_name] = i
                    break
        
        dfs_output = {}
        for i, section_name in enumerate(section_order):
            section_key_lower = section_name.lower() # กำหนด section_key_lower ไว้ตั้งแต่ต้น
            
            if section_name in section_start_indices:
                header_idx = section_start_indices[section_name]
                
                end_idx = len(lines)
                for j in range(i + 1, len(section_order)):
                    next_section_name = section_order[j]
                    if next_section_name in section_start_indices:
                        end_idx = section_start_indices[next_section_name]
                        break
                
                raw_section_lines_block = lines[header_idx : end_idx]
                
                table_data_lines = []
                if raw_section_lines_block:
                    first_line_of_block = raw_section_lines_block[0]
                    
                    # Split ด้วยคอมม่าธรรมดา แทน csv.reader สำหรับบรรทัดแรกเพื่อหลีกเลี่ยง 'lo' error
                    current_line_parts_raw = first_line_of_block.split(',')
                    header_template_parts_count = len(section_raw_headers[section_name].split(','))

                    # Logic เพื่อแยก Header และ Data Row แรก
                    if len(current_line_parts_raw) >= header_template_parts_count:
                        # ถ้ายาวกว่า header template แสดงว่ามี data ติดมาด้วย
                        first_data_row_extracted = current_line_parts_raw[header_template_parts_count:]
                        # นำ data ที่ได้มา join ด้วยคอมม่า เพื่อสร้างเป็น CSV line
                        if any(p.strip() for p in first_data_row_extracted): # เช็คว่ามีข้อมูลจริงๆ ไม่ใช่แค่คอมม่าว่างๆ
                            table_data_lines.append(','.join(first_data_row_extracted))
                    
                    # เพิ่มบรรทัดข้อมูลที่เหลือ (ตั้งแต่บรรทัดที่ 2 ของ block)
                    for line_val in raw_section_lines_block[1:]:
                        line_val_stripped = line_val.strip()
                        if not line_val_stripped: continue # ข้ามบรรทัดว่าง

                        # Heuristic เพื่อหยุดการประมวลผลเมื่อเจอสรุป
                        if line_val_stripped.startswith(("Name:", "Account:", "Company:", "Date:", "Results", "Balance:", "Total Net Profit:", "Average consecutive losses")):
                            break
                        
                        # สำหรับ Orders ที่ Comment มีคอมม่าข้างใน ให้รวมทุกส่วนที่เกินมาเข้าเป็น Comment เดียว
                        if section_name == "Orders":
                            parts = list(csv.reader(io.StringIO(line_val_stripped)))[0] # ใช้ csv.reader ช่วยในการแยก
                            if len(parts) > len(expected_cleaned_columns[section_name]):
                                # ถ้ามีคอลัมน์เกินกว่าที่ expected_cleaned_columns กำหนด
                                # ส่วนที่เกินมาคือ Comment ที่มีคอมม่าข้างใน
                                comment_parts = parts[len(expected_cleaned_columns[section_name])-1:]
                                cleaned_line = ','.join(parts[:len(expected_cleaned_columns[section_name])-1]) + ',' + ' '.join(comment_parts)
                                table_data_lines.append(cleaned_line)
                            else:
                                table_data_lines.append(line_val_stripped)
                        else:
                            table_data_lines.append(line_val_stripped)

                csv_string_data_to_parse = "\n".join(table_data_lines)
                
                # DEBUG: Add this to see the CSV string being passed to pandas
                if st.session_state.get("debug_statement_processing", False):
                    st.write(f"DEBUG: CSV string for {section_name} (before pandas):")
                    st.code(csv_string_data_to_parse)

                if csv_string_data_to_parse.strip():
                    try:
                        df = pd.read_csv(io.StringIO(csv_string_data_to_parse),
                                         sep=',',
                                         names=expected_cleaned_columns[section_name],
                                         header=None,
                                         skipinitialspace=True,
                                         on_bad_lines='warn',
                                         engine='python')
                        
                        # ทำความสะอาดคอลัมน์ที่ไม่จำเป็น (เช่น 'Unnamed: X')
                        df = df.dropna(axis=1, how='all')
                        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

                        # สำหรับ Orders: ตรวจสอบและจัดการคอลัมน์ Comment ให้เหลือแค่ Comment เดียว
                        if section_name == "Orders":
                            # รวม CommentX (ถ้ามี) เข้าเป็น Comment เดียว
                            comment_cols = [col for col in df.columns if col.startswith('Comment')]
                            if comment_cols:
                                df['Comment'] = df[comment_cols].fillna('').agg(' '.join, axis=1).str.strip()
                                df.drop(columns=comment_cols, inplace=True, errors='ignore')
                            if 'Comment' not in df.columns: # ถ้ายังไม่มี Comment ก็สร้างเป็นคอลัมน์ว่าง
                                df['Comment'] = ''

                        # ตรวจสอบและปรับคอลัมน์สุดท้ายให้ตรงกับ expected_cleaned_columns
                        # หากคอลัมน์ที่ได้มาน้อยกว่าที่คาดหวัง ให้เติม NaN
                        for col_name in expected_cleaned_columns[section_name]:
                            if col_name not in df.columns:
                                df[col_name] = np.nan
                        
                        # จัดเรียงคอลัมน์ใหม่ตามที่ expected_cleaned_columns กำหนด
                        df = df[expected_cleaned_columns[section_name]]
                        
                        df.dropna(how='all', inplace=True) # ลบแถวที่ว่างเปล่าออก

                        dfs_output[section_key_lower] = df
                    except ValueError as ve:
                        st.error(f"❌ Column mismatch or data type error in {section_name}: {ve}. Expected {len(expected_cleaned_columns[section_name])} columns.")
                        dfs_output[section_key_lower] = pd.DataFrame()
                    except Exception as e:
                        st.error(f"❌ Error creating DataFrame for {section_name}: {e}")
                        dfs_output[section_key_lower] = pd.DataFrame()
                else:
                    st.warning(f"No valid data rows collected for {section_name} table in the uploaded file.")
                    dfs_output[section_key_lower] = pd.DataFrame()
            else:
                dfs_output[section_key_lower] = pd.DataFrame() # คืน DataFrame ว่างถ้าไม่พบ Section

        # --- Extract Balance Summary and Results Summary (non-table sections) ---
        balance_summary_dict = {}
        results_summary_dict = {}
        
        # ค้นหาและดึง Balance Summary
        balance_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Balance:"):
                balance_start_line_idx = i
                break

        if balance_start_line_idx != -1:
            for i in range(balance_start_line_idx, len(lines)):
                line_stripped = lines[i].strip()
                if not line_stripped or line_stripped.startswith(("Results", "Total Net Profit:")):
                    break
                
                parts = [p.strip() for p in line_stripped.split(',')]
                
                def safe_float_convert(value_str):
                    try:
                        return float(value_str.replace(" ", "").replace(",", "").replace("%", ""))
                    except ValueError:
                        return None

                for part in parts:
                    key = ""
                    value_str = ""
                    if ':' in part: # รูปแบบ Key: Value
                        key_val = part.split(':', 1)
                        key = key_val[0].strip()
                        value_str = key_val[1].strip()
                    else: # รูปแบบ Key Value (ไม่มี colon)
                        last_space_idx = part.rfind(' ')
                        if last_space_idx != -1:
                            key = part[:last_space_idx].strip()
                            value_str = part[last_space_idx+1:].strip()
                    
                    if key:
                        cleaned_key = key.replace(" ", "_").replace(".", "").strip()
                        if cleaned_key: # Ensure cleaned key is not empty
                            balance_summary_dict[cleaned_key] = safe_float_convert(value_str)

        # ค้นหาและดึง Results Summary
        results_start_line_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith("Results") or line.strip().startswith("Total Net Profit:"):
                results_start_line_idx = i
                break
        
        if results_start_line_idx != -1:
            for i in range(results_start_line_idx, len(lines)): # เริ่มจากบรรทัดที่เจอ Results เลย
                line_stripped = lines[i].strip()
                if not line_stripped or line_stripped.startswith("Average consecutive losses"):
                    break
                
                parts = [p.strip() for p in line_stripped.split(',')]
                for part in parts:
                    key = ""
                    value_str = ""
                    
                    if ':' in part:
                        key_val = part.split(':', 1)
                        key = key_val[0].strip()
                        value_str = key_val[1].strip()
                    elif ' ' in part and len(part.split()) > 1:
                        last_space_idx = part.rfind(' ')
                        if last_space_idx != -1:
                            key = part[:last_space_idx].strip()
                            value_str = part[last_space_idx+1:].strip()
                    
                    if key:
                        cleaned_key = key.replace("(", "").replace(")", "").replace("/", "_").replace("-", "_").replace(" ", "_").replace("__", "_").strip()
                        if "won %" in cleaned_key: # Specific handle "won %" in key names
                            cleaned_key = cleaned_key.replace("won %", "won_Percent")
                        
                        try:
                            results_summary_dict[cleaned_key] = safe_float_convert(value_str)
                        except Exception:
                            results_summary_dict[cleaned_key] = value_str # เก็บเป็น string ถ้า convert ไม่ได้

        dfs_output['balance_summary'] = balance_summary_dict
        dfs_output['results_summary'] = results_summary_dict

        return dfs_output

    # --- ฟังก์ชันสำหรับบันทึก Deals ลงในชีท ActualTrades ---
    def save_deals_to_actual_trades(df_deals, portfolio_id, portfolio_name, source_file_name="N/A"):
        gc = get_gspread_client()
        if not gc: return False
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
            ws = sh.worksheet(WORKSHEET_ACTUAL_TRADES)
            expected_headers = [
                "Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order",
                "Commission", "Fee", "Swap", "Profit", "Balance", "Comment",
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.append_row(expected_headers)

            rows_to_append = []
            for index, row in df_deals.iterrows():
                row_data = {
                    "Time": row.get("Time", ""),
                    "Deal": row.get("Deal", ""),
                    "Symbol": row.get("Symbol", ""),
                    "Type": row.get("Type", ""),
                    "Direction": row.get("Direction", ""),
                    "Volume": row.get("Volume", ""),
                    "Price": row.get("Price", ""),
                    "Order": row.get("Order", ""),
                    "Commission": row.get("Commission", ""),
                    "Fee": row.get("Fee", ""),
                    "Swap": row.get("Swap", ""),
                    "Profit": row.get("Profit", ""),
                    "Balance": row.get("Balance", ""),
                    "Comment": row.get("Comment", ""),
                    "PortfolioID": portfolio_id,
                    "PortfolioName": portfolio_name,
                    "SourceFile": source_file_name
                }
                rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])
            if rows_to_append: ws.append_rows(rows_to_append, value_input_option='USER_ENTERED'); return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_TRADES}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Deals: {e}"); return False

    # --- ฟังก์ชันสำหรับบันทึก Positions ลงในชีท ActualPositions ---
    def save_positions_to_gsheets(df_positions, portfolio_id, portfolio_name, source_file_name="N/A"):
        gc = get_gspread_client()
        if not gc: return False
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
            ws = sh.worksheet(WORKSHEET_ACTUAL_POSITIONS)
            expected_headers = [
                "Time", "Position", "Symbol", "Type", "Volume", "Price", "S_L", "T_P",
                "Close_Time", "Close_Price", "Commission", "Swap", "Profit",
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.append_row(expected_headers)

            rows_to_append = []
            for index, row in df_positions.iterrows():
                row_data = {
                    "Time": row.get("Time", ""),
                    "Position": row.get("Position", ""),
                    "Symbol": row.get("Symbol", ""),
                    "Type": row.get("Type", ""),
                    "Volume": row.get("Volume", ""),
                    "Price": row.get("Price", ""),
                    "S_L": row.get("S_L", ""),
                    "T_P": row.get("T_P", ""),
                    "Close_Time": row.get("Close_Time", ""),
                    "Close_Price": row.get("Close_Price", ""),
                    "Commission": row.get("Commission", ""),
                    "Swap": row.get("Swap", ""),
                    "Profit": row.get("Profit", ""),
                    "PortfolioID": portfolio_id,
                    "PortfolioName": portfolio_name,
                    "SourceFile": source_file_name
                }
                rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])
            if rows_to_append: ws.append_rows(rows_to_append, value_input_option='USER_ENTERED'); return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_POSITIONS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Positions: {e}"); return False

    # --- ฟังก์ชันสำหรับบันทึก Orders ลงในชีท ActualOrders ---
    def save_orders_to_gsheets(df_orders, portfolio_id, portfolio_name, source_file_name="N/A"):
        gc = get_gspread_client()
        if not gc: return False
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
            ws = sh.worksheet(WORKSHEET_ACTUAL_ORDERS)
            expected_headers = [
                "Open_Time", "Order", "Symbol", "Type", "Volume", "Price", "S_L", "T_P",
                "Close_Time", "State", "Comment",
                "PortfolioID", "PortfolioName", "SourceFile"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.append_row(expected_headers)

            rows_to_append = []
            for index, row in df_orders.iterrows():
                row_data = {
                    "Open_Time": row.get("Open_Time", ""),
                    "Order": row.get("Order", ""),
                    "Symbol": row.get("Symbol", ""),
                    "Type": row.get("Type", ""),
                    "Volume": row.get("Volume", ""),
                    "Price": row.get("Price", ""),
                    "S_L": row.get("S_L", ""),
                    "T_P": row.get("T_P", ""),
                    "Close_Time": row.get("Close_Time", ""),
                    "State": row.get("State", ""),
                    "Comment": row.get("Comment", ""),
                    "PortfolioID": portfolio_id,
                    "PortfolioName": portfolio_name,
                    "SourceFile": source_file_name
                }
                rows_to_append.append([str(row_data.get(h, "")) for h in expected_headers])
            if rows_to_append: ws.append_rows(rows_to_append, value_input_option='USER_ENTERED'); return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_ACTUAL_ORDERS}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Orders: {e}"); return False

    # --- ฟังก์ชันสำหรับบันทึก Results Summary ลงในชีท StatementSummaries ---
    def save_results_summary_to_gsheets(summary_dict, portfolio_id, portfolio_name, source_file_name="N/A"):
        gc = get_gspread_client()
        if not gc: return False
        try:
            sh = gc.open(GOOGLE_SHEET_NAME)
            ws = sh.worksheet(WORKSHEET_STATEMENT_SUMMARIES)
            
            expected_headers = [
                "Timestamp", "PortfolioID", "PortfolioName", "SourceFile", 
                "Total_Net_Profit", "Gross_Profit", "Gross_Loss", "Profit_Factor", 
                "Expected_Payoff", "Recovery_Factor", "Sharpe_Ratio", 
                "Balance_Drawdown_Absolute", "Balance_Drawdown_Maximal", 
                "Balance_Drawdown_Maximal_Percent", "Balance_Drawdown_Relative", 
                "Balance_Drawdown_Relative_Percent", "Total_Trades", 
                "Short_Trades", "Short_Trades_won_Percent", "Long_Trades", 
                "Long_Trades_won_Percent", "Profit_Trades", "Profit_Trades_Percent_of_total", 
                "Loss_Trades", "Loss_Trades_Percent_of_total", "Largest_profit_trade", 
                "Largest_loss_trade", "Average_profit_trade", "Average_loss_trade", 
                "Maximum_consecutive_wins_Count", "Maximum_consecutive_wins_Profit", 
                "Maximum_consecutive_losses_Count", "Maximum_consecutive_losses_Profit",
                "Maximal_consecutive_profit_Count", "Maximal_consecutive_profit_Amount",
                "Maximal_consecutive_loss_Count", "Maximal_consecutive_loss_Amount",
                "Average_consecutive_wins", "Average_consecutive_losses"
            ]
            
            current_headers = []
            if ws.row_count > 0: current_headers = ws.row_values(1)
            if not current_headers or all(h == "" for h in current_headers): ws.append_row(expected_headers)

            rows_to_append = []
            row_data = {
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "PortfolioID": portfolio_id,
                "PortfolioName": portfolio_name,
                "SourceFile": source_file_name
            }
            for key, value in summary_dict.items():
                cleaned_key = key.replace(" ", "_").replace("%", "Percent").replace("(won_%)", "won_Percent").replace("__", "_").strip()
                if "TotalNetProfit" in cleaned_key: cleaned_key = "Total_Net_Profit"

                if cleaned_key in expected_headers:
                    row_data[cleaned_key] = value
            
            final_row_data = [str(row_data.get(h, "")) for h in expected_headers]

            rows_to_append.append(final_row_data)
            
            if rows_to_append: ws.append_rows(rows_to_append, value_input_option='USER_ENTERED'); return True
            return False
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"❌ ไม่พบ Worksheet '{WORKSHEET_STATEMENT_SUMMARIES}'. กรุณาสร้างและใส่ Headers: {', '.join(expected_headers)}")
            return False
        except Exception as e: st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก Statement Summaries: {e}"); return False


    st.markdown("---")
    st.subheader("📤 อัปโหลด Statement Report (CSV) เพื่อประมวลผลและบันทึก")
    
    uploaded_file_statement = st.file_uploader( 
        "ลากและวางไฟล์ Statement Report (CSV) ที่นี่ หรือคลิกเพื่อเลือกไฟล์",
        type=["csv"],
        key="full_stmt_uploader"
    )

    st.checkbox("⚙️ เปิดโหมด Debug (แสดงข้อมูลที่แยกได้)", key="debug_statement_processing")
    
    active_portfolio_id_for_actual = st.session_state.get('active_portfolio_id_gs', None)
    active_portfolio_name_for_actual = st.session_state.get('active_portfolio_name_gs', None)

    if uploaded_file_statement:
        file_name_for_saving = uploaded_file_statement.name
        
        file_content_str = uploaded_file_statement.getvalue().decode("utf-8")
        
        st.info(f"กำลังประมวลผลไฟล์: {uploaded_file_statement.name}")
        with st.spinner(f"กำลังแยกส่วนข้อมูลจาก {uploaded_file_statement.name}..."):
            extracted_sections = extract_data_from_report_content(file_content_str)
            
            if st.session_state.get("debug_statement_processing", False):
                st.subheader("📄 ข้อมูลที่แยกได้ (Debug)")
                for section_name, data_item in extracted_sections.items():
                    st.write(f"#### {section_name.replace('_',' ').title()}")
                    if isinstance(data_item, pd.DataFrame):
                        if not data_item.empty:
                            st.dataframe(data_item)
                        else:
                            st.info(f"DataFrame for {section_name.replace('_',' ').title()} is empty.")
                    else:
                        st.json(data_item)

            if not active_portfolio_id_for_actual:
                st.error("กรุณาเลือกพอร์ตที่ใช้งาน (Active Portfolio) ใน Sidebar ก่อนประมวลผล Statement.")
            else:
                st.markdown("---")
                st.subheader("💾 กำลังบันทึกข้อมูลไปยัง Google Sheets...")
                
                if not extracted_sections.get('deals', pd.DataFrame()).empty:
                    if save_deals_to_actual_trades(extracted_sections['deals'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success(f"บันทึก Deals จำนวน {len(extracted_sections['deals'])} รายการ ไปยังชีต 'ActualTrades' สำเร็จ!")
                        st.session_state.df_stmt_deals = extracted_sections['deals'].copy()
                    else: st.error("บันทึก Deals ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Deals ใน Statement.")

                if not extracted_sections.get('orders', pd.DataFrame()).empty:
                    if save_orders_to_gsheets(extracted_sections['orders'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success(f"บันทึก Orders จำนวน {len(extracted_sections['orders'])} รายการ ไปยังชีต 'ActualOrders' สำเร็จ!")
                    else: st.error("บันทึก Orders ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Orders ใน Statement.")
                
                if not extracted_sections.get('positions', pd.DataFrame()).empty:
                    if save_positions_to_gsheets(extracted_sections['positions'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success(f"บันทึก Positions จำนวน {len(extracted_sections['positions'])} รายการ ไปยังชีต 'ActualPositions' สำเร็จ!")
                    else: st.error("บันทึก Positions ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Positions ใน Statement.")

                if extracted_sections.get('results_summary'):
                    if save_results_summary_to_gsheets(extracted_sections['results_summary'], active_portfolio_id_for_actual, active_portfolio_name_for_actual, file_name_for_saving):
                        st.success("บันทึก Results Summary ไปยังชีท 'StatementSummaries' สำเร็จ!")
                    else: st.error("บันทึก Results Summary ไม่สำเร็จ.")
                else: st.warning("ไม่พบข้อมูล Results Summary ใน Statement.")

    else:
        st.info("โปรดอัปโหลดไฟล์ Statement Report (CSV) เพื่อเริ่มต้นประมวลผล.")

    st.markdown("---")

# ===================== SEC 8: MAIN AREA - PERFORMANCE DASHBOARD =======================
# ฟังก์ชันโหลดข้อมูลสำหรับแดชบอร์ด ถูกปรับให้รับ source_option จาก selectbox ด้านนอก
def load_data_for_dashboard(source_option_param):
    df_dashboard_data = pd.DataFrame()
    if source_option_param == "Planned Trades (Google Sheets)":
        gc_dash = get_gspread_client()
        if gc_dash:
            try:
                sh_dash = gc_dash.open(GOOGLE_SHEET_NAME)
                ws_dash_logs = sh_dash.worksheet(WORKSHEET_PLANNED_LOGS)
                records_dash = ws_dash_logs.get_all_records()
                if records_dash:
                    df_dashboard_data = pd.DataFrame(records_dash)
                    if 'Risk $' in df_dashboard_data.columns:
                        df_dashboard_data['Profit'] = pd.to_numeric(df_dashboard_data['Risk $'], errors='coerce').fillna(0)
                    if 'Timestamp' in df_dashboard_data.columns:
                        df_dashboard_data['Time'] = pd.to_datetime(df_dashboard_data['Timestamp'], errors='coerce')
                    if 'RR' in df_dashboard_data.columns:
                         df_dashboard_data['RR'] = pd.to_numeric(df_dashboard_data['RR'], errors='coerce')
                    if 'Lot' in df_dashboard_data.columns:
                         df_dashboard_data['Lot'] = pd.to_numeric(df_dashboard_data['Lot'], errors='coerce')
                    if 'Asset' in df_dashboard_data.columns:
                        df_dashboard_data.rename(columns={'Asset': 'Symbol'}, inplace=True)

            except Exception as e:
                st.warning(f"ไม่สามารถโหลด Planned Trades สำหรับ Dashboard: {e}")
        st.caption("ข้อมูลจากชีต 'PlannedTradeLogs'")

    else: # Actual Trades (Statement Import)
        df_dashboard_data = st.session_state.get('df_stmt_deals', pd.DataFrame()).copy()
        if not df_dashboard_data.empty:
            rename_map = {} 
            for col in df_dashboard_data.columns:
                col_lower = col.lower()
                if 'profit' in col_lower and 'Profit' not in rename_map.values(): rename_map[col] = 'Profit'
                if 'time' in col_lower and 'open time' not in col_lower and 'Time' not in rename_map.values(): rename_map[col] = 'Time'
                if 'open time' in col_lower and 'Open Time' not in rename_map.values(): rename_map[col] = 'Open Time'
                if 'symbol' in col_lower and 'Symbol' not in rename_map.values(): rename_map[col] = 'Symbol'
                if 'volume' in col_lower or 'lots' in col_lower and 'Lot' not in rename_map.values(): rename_map[col] = 'Lot'

            df_dashboard_data.rename(columns=rename_map, inplace=True)

            if 'Profit' in df_dashboard_data.columns:
                df_dashboard_data['Profit'] = pd.to_numeric(df_dashboard_data['Profit'], errors='coerce').fillna(0)
            if 'Time' in df_dashboard_data.columns:
                df_dashboard_data['Time'] = pd.to_datetime(df_dashboard_data['Time'], errors='coerce')
            elif 'Open Time' in df_dashboard_data.columns:
                 df_dashboard_data['Time'] = pd.to_datetime(df_dashboard_data['Open Time'], errors='coerce')
            if 'Lot' in df_dashboard_data.columns:
                df_dashboard_data['Lot'] = pd.to_numeric(df_dashboard_data['Lot'], errors='coerce').fillna(0)

        st.caption("ข้อมูลจากไฟล์ Statement ที่อัปโหลด (Deals)")
        
    return df_dashboard_data


with st.expander("📊 Performance Dashboard", expanded=True):
    # ย้าย st.selectbox มาไว้ที่นี่ (นอกฟังก์ชัน load_data_for_dashboard)
    source_option = st.selectbox(
        "เลือกแหล่งข้อมูลสำหรับแดชบอร์ด:",
        ["Planned Trades (Google Sheets)", "Actual Trades (Statement Import)"],
        index=0,
        key="dashboard_source_selector" # ต้องมี key ที่ไม่ซ้ำ
    )
    
    df_data_dash = load_data_for_dashboard(source_option) # ส่ง source_option ที่เลือกเข้าไป

    if df_data_dash.empty:
        st.info("ยังไม่มีข้อมูลสำหรับ Dashboard หรือไม่สามารถโหลดข้อมูลได้")
    else:
        required_cols_present = True
        if 'Profit' not in df_data_dash.columns:
            st.warning("ไม่พบคอลัมน์ 'Profit' ในข้อมูลสำหรับ Dashboard")
            required_cols_present = False
        if 'Time' not in df_data_dash.columns:
            st.warning("ไม่พบคอลัมน์ 'Time' (หรือเทียบเท่า) ในข้อมูลสำหรับ Dashboard")
            required_cols_present = False
        
        if not required_cols_present:
            st.stop()

        st.markdown("#### ⚙️ Filters")
        col_filter1, col_filter2 = st.columns(2)

        with col_filter1:
            portfolio_col_name = None
            if "Portfolio" in df_data_dash.columns and df_data_dash["Portfolio"].notna().any():
                portfolio_col_name = "Portfolio"
            elif "PortfolioName" in df_data_dash.columns and df_data_dash["PortfolioName"].notna().any():
                portfolio_col_name = "PortfolioName"
            
            if portfolio_col_name:
                portfolio_list_dash = ["ทั้งหมด"] + sorted(df_data_dash[portfolio_col_name].dropna().unique().tolist())
                selected_portfolio_dash = st.selectbox(
                    "📂 Filter by Portfolio", portfolio_list_dash, key="dash_portfolio_filter"
                )
                if selected_portfolio_dash != "ทั้งหมด":
                    df_data_dash = df_data_dash[df_data_dash[portfolio_col_name] == selected_portfolio_dash]
            else:
                st.selectbox("📂 Filter by Portfolio", ["- (ไม่มีข้อมูลพอร์ต)"], disabled=True, key="dash_portfolio_filter_disabled")
        
        with col_filter2:
            symbol_col_name = None
            if "Symbol" in df_data_dash.columns and df_data_dash["Symbol"].notna().any():
                symbol_col_name = "Symbol"
            
            if symbol_col_name:
                asset_list_dash = ["ทั้งหมด"] + sorted(df_data_dash[symbol_col_name].dropna().unique().tolist())
                selected_asset_dash = st.selectbox(
                    f"🎯 Filter by {symbol_col_name}", asset_list_dash, key="dash_asset_filter"
                )
                if selected_asset_dash != "ทั้งหมด":
                    df_data_dash = df_data_dash[df_data_dash[symbol_col_name] == selected_asset_dash]
            else:
                st.selectbox("🎯 Filter by Asset/Symbol", ["- (ไม่มีข้อมูล Symbol)"], disabled=True, key="dash_asset_filter_disabled")
        
        st.markdown("---")

        tab_names = ["📊 Dashboard", "📈 RR Analysis", "📉 Lot Size", "🕒 Time Analysis", "🤖 AI Insight", "⬇️ Export"]
        # Conditionally remove RR tab if RR column not present or not relevant for 'Actual Trades'
        if 'RR' not in df_data_dash.columns and source_option == "Actual Trades (Statement Import)":
            if "📈 RR Analysis" in tab_names: tab_names.remove("📈 RR Analysis")
        
        tabs = st.tabs(tab_names)
        
        with tabs[0]:
            st.markdown("### ⚖️ Win/Loss Ratio")
            win_count_dash = df_data_dash[df_data_dash['Profit'] > 0].shape[0]
            loss_count_dash = df_data_dash[df_data_dash['Profit'] <= 0].shape[0]
            if win_count_dash + loss_count_dash > 0:
                pie_df_dash = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count_dash, loss_count_dash]})
                pie_chart_dash = px.pie(pie_df_dash, names="Result", values="Count", color="Result",
                                        color_discrete_map={"Win": "mediumseagreen", "Loss": "indianred"}, title="Win vs Loss Trades")
                st.plotly_chart(pie_chart_dash, use_container_width=True)
            else:
                st.info("ไม่มีข้อมูล Win/Loss เพียงพอสำหรับ Pie Chart")

            st.markdown("### 🗓️ Daily Profit/Loss")
            df_data_dash['TradeDate'] = df_data_dash['Time'].dt.date
            daily_pnl_df = df_data_dash.groupby("TradeDate")['Profit'].sum().reset_index(name="Daily P/L")
            daily_bar_chart = px.bar(daily_pnl_df, x="TradeDate", y="Daily P/L", 
                                     color="Daily P/L", title="กำไร/ขาดทุนรายวัน",
                                     color_continuous_scale=["indianred", "lightgrey", "mediumseagreen"])
            st.plotly_chart(daily_bar_chart, use_container_width=True)

            st.markdown("### 📉 Balance Curve (Equity Timeline)")
            df_data_dash_sorted = df_data_dash.sort_values(by="Time")
            df_data_dash_sorted["Balance"] = acc_balance + df_data_dash_sorted['Profit'].cumsum()
            balance_curve_chart = px.line(df_data_dash_sorted, x="Time", y="Balance", markers=True, title="Balance Curve")
            balance_curve_chart.update_traces(line_color='deepskyblue')
            st.plotly_chart(balance_curve_chart, use_container_width=True)

        rr_tab_index = -1
        if "📈 RR Analysis" in tab_names:
            rr_tab_index = tab_names.index("📈 RR Analysis")
        
        if rr_tab_index != -1:
            with tabs[rr_tab_index]:
                if 'RR' in df_data_dash.columns and not df_data_dash['RR'].dropna().empty:
                    rr_data_dash = df_data_dash['RR'].dropna()
                    st.markdown("#### Risk:Reward Ratio (RR) Histogram")
                    rr_hist = px.histogram(rr_data_dash, nbins=20, title="RR Distribution", labels={'value': 'RR Ratio'}, opacity=0.8)
                    rr_hist.update_layout(bargap=0.1, xaxis_title='Risk:Reward Ratio', yaxis_title='จำนวนเทรด')
                    rr_hist.update_traces(marker_color='cornflowerblue')
                    st.plotly_chart(rr_hist, use_container_width=True)
                    st.caption("วิเคราะห์การกระจายตัวของ RR. RR ที่สูงกว่า 1.5 หรือ 2 ถือว่าดี.")
                else:
                    st.info("ไม่พบข้อมูล RR หรือข้อมูลไม่เพียงพอสำหรับ Histogram นี้.")
        
        lot_tab_index = tab_names.index("📉 Lot Size")
        with tabs[lot_tab_index]:
            if 'Lot' in df_data_dash.columns and not df_data_dash['Lot'].dropna().empty:
                st.markdown("#### Lot Size Over Time")
                lot_df_sorted = df_data_dash.dropna(subset=['Lot', 'Time']).sort_values(by="Time")
                lot_line_chart = px.line(lot_df_sorted, x="Time", y="Lot", markers=True, title="Lot Size Evolution")
                lot_line_chart.update_traces(line_color='goldenrod')
                st.plotly_chart(lot_line_chart, use_container_width=True)
                st.caption("ติดตามการเปลี่ยนแปลงของ Lot Size เพื่อวิเคราะห์ Money Management และ Scaling.")
            else:
                st.info("ไม่พบข้อมูล Lot Size หรือข้อมูลไม่เพียงพอ.")

        time_analysis_tab_index = tab_names.index("🕒 Time Analysis")
        with tabs[time_analysis_tab_index]:
            st.markdown("#### Performance by Day of Week")
            df_data_dash['Weekday'] = df_data_dash['Time'].dt.day_name()
            weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            weekday_pnl = df_data_dash.groupby("Weekday")['Profit'].sum().reindex(weekday_order).reset_index()
            weekday_chart = px.bar(weekday_pnl, x="Weekday", y="Profit", title="Total P/L by Day of Week", color="Profit",
                                   color_continuous_scale=["tomato", "lightgoldenrodyellow", "lightgreen"])
            st.plotly_chart(weekday_chart, use_container_width=True)
            st.caption("ดูว่าวันไหนในสัปดาห์ที่มักทำกำไรหรือขาดทุน.")

        ai_insight_tab_index = tab_names.index("🤖 AI Insight")
        with tabs[ai_insight_tab_index]:
            st.markdown("### AI Insight & Recommendation (Dashboard Data)")
            total_trades_dash_ai = df_data_dash.shape[0]
            winrate_dash_ai = (win_count_dash / total_trades_dash_ai * 100) if total_trades_dash_ai > 0 else 0
            gross_profit_dash_ai = df_data_dash['Profit'].sum()
            
            st.write(f"Trades in current view: {total_trades_dash_ai}")
            st.write(f"Winrate: {winrate_dash_ai:.2f}%")
            st.write(f"Net Profit: {gross_profit_dash_ai:,.2f} USD")
            
            try:
                if "google_api" in st.secrets and "GOOGLE_API_KEY" in st.secrets.google_api:
                    genai.configure(api_key=st.secrets.google_api.GOOGLE_API_KEY)
                    model_gemini = genai.GenerativeModel('gemini-pro')
                    prompt_text_dash = (
                        f"Analyze this trading performance: Total trades: {total_trades_dash_ai}, "
                        f"Winrate: {winrate_dash_ai:.2f}%, Net Profit/Loss: {gross_profit_dash_ai:,.2f} USD. "
                        f"Provide concise trading insights and recommendations for improvement. "
                        f"What are potential strengths and weaknesses? Focus on practical advice. Respond in Thai."
                    )
                    with st.spinner("🤖 Gemini AI กำลังวิเคราะห์ข้อมูล Dashboard..."):
                        response_gemini = model_gemini.generate_content(prompt_text_dash)
                    st.markdown("---")
                    st.markdown("**มุมมองจาก Gemini AI:**")
                    st.write(response_gemini.text)
                else:
                    st.info("โปรดตั้งค่า Google API Key ใน `secrets.toml` (ใต้ `[google_api]`) เพื่อเปิดใช้งาน AI Assistant จาก Gemini.")
            except Exception as e_gemini:
                st.error(f"❌ เกิดข้อผิดพลาดในการเรียกใช้ Gemini AI: {e_gemini}")

        export_tab_index = tab_names.index("⬇️ Export")
        with tabs[export_tab_index]:
            st.markdown("### 📄 Export Filtered Data")
            if not df_data_dash.empty:
                csv_export = df_data_dash.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Data as CSV",
                    data=csv_export,
                    file_name=f"dashboard_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                )
            else:
                st.info("ไม่มีข้อมูลที่กรองไว้สำหรับ Export.")

# ===================== SEC 9: MAIN AREA - TRADE LOG VIEWER =======================
@st.cache_data(ttl=120)
def load_planned_trades_from_gsheets_for_viewer():
    gc = get_gspread_client()
    if gc is None: return pd.DataFrame()
    try:
        sh = gc.open(GOOGLE_SHEET_NAME)
        worksheet = sh.worksheet(WORKSHEET_PLANNED_LOGS)
        records = worksheet.get_all_records()
        if not records: return pd.DataFrame()
        
        df_logs_viewer = pd.DataFrame(records)
        if 'Timestamp' in df_logs_viewer.columns:
            df_logs_viewer['Timestamp'] = pd.to_datetime(df_logs_viewer['Timestamp'], errors='coerce')
        
        cols_to_numeric_log_viewer = ['Risk %', 'Entry', 'SL', 'TP', 'Lot', 'Risk $', 'RR']
        for col_viewer in cols_to_numeric_log_viewer:
            if col_viewer in df_logs_viewer.columns:
                # แก้ไข: แทนที่จะ replace '' เป็น 'NaN' แล้วค่อยแปลงเป็นตัวเลข
                # ให้แปลงเป็นตัวเลขโดยตรง แล้ว nan() จะเป็นค่า default ถ้าแปลงไม่ได้
                df_logs_viewer[col_viewer] = pd.to_numeric(df_logs_viewer[col_viewer], errors='coerce')
        
        return df_logs_viewer.sort_values(by="Timestamp", ascending=False) if 'Timestamp' in df_logs_viewer.columns else df_logs_viewer
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"❌ Log Viewer: ไม่พบ Worksheet '{WORKSHEET_PLANNED_LOGS}'.")
        return pd.DataFrame()
    except Exception as e_log_viewer:
        st.error(f"❌ Log Viewer: เกิดข้อผิดพลาดในการโหลด Log - {e_log_viewer}")
        return pd.DataFrame()

with st.expander("📚 Trade Log Viewer (แผนเทรดจาก Google Sheets)", expanded=False):
    df_log_viewer_gs = load_planned_trades_from_gsheets_for_viewer()

    if df_log_viewer_gs.empty:
        st.info("ยังไม่มีข้อมูลแผนที่บันทึกไว้ใน Google Sheets หรือ Worksheet 'PlannedTradeLogs' ว่างเปล่า.")
    else:
        df_show_log_viewer = df_log_viewer_gs.copy()

        log_filter_cols = st.columns(4)
        with log_filter_cols[0]:
            portfolios_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["PortfolioName"].dropna().unique().tolist()) if "PortfolioName" in df_show_log_viewer else ["ทั้งหมด"]
            portfolio_filter_log = st.selectbox("Portfolio", portfolios_in_log, key="log_viewer_portfolio_filter")
        with log_filter_cols[1]:
            modes_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["Mode"].dropna().unique().tolist()) if "Mode" in df_show_log_viewer else ["ทั้งหมด"]
            mode_filter_log = st.selectbox("Mode", modes_in_log, key="log_viewer_mode_filter")
        with log_filter_cols[2]:
            assets_in_log = ["ทั้งหมด"] + sorted(df_show_log_viewer["Asset"].dropna().unique().tolist()) if "Asset" in df_show_log_viewer else ["ทั้งหมด"]
            asset_filter_log = st.selectbox("Asset", assets_in_log, key="log_viewer_asset_filter")
        with log_filter_cols[3]:
            date_filter_log = None
            if 'Timestamp' in df_show_log_viewer.columns and not df_show_log_viewer['Timestamp'].isnull().all():
                 date_filter_log = st.date_input("ค้นหาวันที่ (Log)", value=None, key="log_viewer_date_filter", help="เลือกวันที่เพื่อกรอง Log")


        if portfolio_filter_log != "ทั้งหมด" and "PortfolioName" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["PortfolioName"] == portfolio_filter_log]
        if mode_filter_log != "ทั้งหมด" and "Mode" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Mode"] == mode_filter_log]
        if asset_filter_log != "ทั้งหมด" and "Asset" in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Asset"] == asset_filter_log]
        if date_filter_log and 'Timestamp' in df_show_log_viewer:
            df_show_log_viewer = df_show_log_viewer[df_show_log_viewer["Timestamp"].dt.date == date_filter_log]
        
        st.markdown("---")
        st.markdown("**Log Details & Actions:**")
        
        cols_to_display = {
            "Timestamp": "Timestamp", "PortfolioName": "Portfolio", "Asset": "Asset",
            "Mode": "Mode", "Direction": "Direction", "Entry": "Entry", "SL": "SL", "TP": "TP",
            "Lot": "Lot", "Risk $": "Risk $" , "RR": "RR"
        }
        actual_cols_to_display = {k:v for k,v in cols_to_display.items() if k in df_show_log_viewer.columns}
        
        num_display_cols = len(actual_cols_to_display)
        header_display_cols = st.columns(num_display_cols + 1)

        for i, (col_key, col_name) in enumerate(actual_cols_to_display.items()):
            header_display_cols[i].markdown(f"**{col_name}**")
        header_display_cols[num_display_cols].markdown(f"**Action**")


        for index_log, row_log in df_show_log_viewer.iterrows():
            row_display_cols = st.columns(num_display_cols + 1)
            for i, col_key in enumerate(actual_cols_to_display.keys()):
                val = row_log.get(col_key, "-")
                if isinstance(val, float):
                    row_display_cols[i].write(f"{val:.2f}" if not np.isnan(val) else "-")
                elif isinstance(val, pd.Timestamp):
                    row_display_cols[i].write(val.strftime("%Y-%m-%d %H:%M") if pd.notnull(val) else "-")
                else:
                    row_display_cols[i].write(str(val) if pd.notnull(val) and str(val).strip() != "" else "-")

            if row_display_cols[num_display_cols].button(f"📈 Plot", key=f"plot_log_{row_log.get('LogID', index_log)}"):
                st.session_state['plot_data'] = row_log.to_dict()
                st.success(f"เลือกข้อมูลเทรด '{row_log.get('Asset', '-')}' ที่ Entry '{row_log.get('Entry', '-')}' เตรียมพร้อมสำหรับ Plot บน Chart Visualizer!")
                st.rerun()
        
        if 'plot_data' in st.session_state and st.session_state['plot_data']:
            st.sidebar.success(f"ข้อมูลพร้อม Plot: {st.session_state['plot_data'].get('Asset')} @ {st.session_state['plot_data'].get('Entry')}")
            st.sidebar.json(st.session_state['plot_data'], expanded=False)
