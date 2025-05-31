# ======================= SEC 0: IMPORT & CONFIG =======================
import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime

st.set_page_config(page_title="Legendary RR Planner", layout="wide")
acc_balance = 10000  # FIX
log_file = "trade_log.csv"

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
st.sidebar.header("🗂️ Trade Planner")

drawdown_limit_pct = st.sidebar.number_input(
    "Drawdown Limit ต่อวัน (%)",
    min_value=0.1, max_value=20.0,
    value=2.0, step=0.1, format="%.1f"
)

mode = st.sidebar.radio("เลือกโหมด", ["FIBO", "CUSTOM"], horizontal=True)

if st.sidebar.button("Clear (รีเซ็ตฟอร์ม)"):
    st.experimental_rerun()

# -- Input Zone (แยก FIBO/CUSTOM) --
# ======================= SEC 1: SIDEBAR / INPUT ZONE (FIBO) =======================
if mode == "FIBO":
    col1, col2, col3 = st.sidebar.columns([2, 2, 2])
    with col1:
        asset = st.text_input("Asset", value="XAUUSD")
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
        direction = st.radio("Direction", ["Long", "Short"], horizontal=True)

    col4, col5 = st.sidebar.columns(2)
    with col4:
        swing_high = st.text_input("High", value="2365.00")
    with col5:
        swing_low = st.text_input("Low", value="2355.00")
    
    st.sidebar.markdown("**เลือก Fibo Level:**")
    fibos = [0.114, 0.25, 0.382, 0.5, 0.618]
    labels = [f"{l:.3f}" for l in fibos]
    cols = st.sidebar.columns(len(fibos))
    fibo_selected = []
    for i, col in enumerate(cols):
        fibo_selected.append(col.checkbox(labels[i], value=True, key=f"fibo_{labels[i]}"))

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
        asset = st.text_input("Asset", value="XAUUSD")
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
                if 'direction' in locals() and direction == "Long":
                    tp_rr3 = entry_val + 3 * stop
                else:
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
st.sidebar.markdown("### 🧮 Summary")

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
            st.markdown("### 📋 Entry Table")
            if entry_data:
                entry_df = pd.DataFrame(entry_data)
                st.dataframe(entry_df, hide_index=True, use_container_width=True)
        with col2:
            st.markdown("### 🎯 TP Table ")
            try:
                high = float(swing_high)
                low = float(swing_low)
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
            except Exception:
                st.warning("กรุณากรอก High/Low ให้ถูกต้องเพื่อแสดงตาราง TP")
    elif mode == "CUSTOM":
        st.markdown("### 📋 Entry Table ")
        if custom_entries:
            entry_df = pd.DataFrame(custom_entries)
            st.dataframe(entry_df, hide_index=True, use_container_width=True)
            # แจ้งเตือน RR
            for i, row in enumerate(custom_entries):
                try:
                    rr = float(row["RR"])
                    if rr < 2:
                        st.warning(f"ไม้ {i+1} RR ต่ำ! ({rr:.2f}) ควรปรับ TP หรือ SL ใหม่")
                except:
                    pass

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
    df_save["Direction"] = direction
    df_save["Timestamp"] = now
    if os.path.exists(log_file):
        df_old = pd.read_csv(log_file)
        df_save = pd.concat([df_old, df_save], ignore_index=True)
    df_save.to_csv(log_file, index=False)

if mode == "FIBO" and 'entry_data' in locals() and save_fibo and entry_data:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    else:
        try:
            save_plan(entry_data, "FIBO", asset, risk_pct, direction)
            st.sidebar.success("บันทึกแผน (FIBO) สำเร็จ!")
        except Exception as e:
            st.sidebar.error(f"Save ไม่สำเร็จ: {e}")

elif mode == "CUSTOM" and 'custom_entries' in locals() and save_custom and custom_entries:
    if drawdown_today <= drawdown_limit:
        st.sidebar.error(
            f"หยุดเทรด! ขาดทุนรวมวันนี้ {abs(drawdown_today):,.2f} เกินลิมิต {abs(drawdown_limit):,.2f} ({drawdown_limit_pct:.1f}%)"
        )
    else:
        try:
            save_plan(custom_entries, "CUSTOM", asset, risk_pct, direction)
            st.sidebar.success("บันทึกแผน (CUSTOM) สำเร็จ!")
        except Exception as e:
            st.sidebar.error(f"Save ไม่สำเร็จ: {e}")

# ======================= SEC 7: VISUALIZER (เหลือแต่กราฟ) =======================
st.markdown("## 🟢 SEC 7: Visualizer (แสดงกราฟเท่านั้น)")

# ไม่ต้องใช้ col1/col2 สองฝั่งแล้ว เอาแต่ col เดียวหรือเต็มแถวก็ได้
plot = st.button("Plot Plan", key="plot_plan")


if plot:
    st.markdown("#### กราฟ TradingView Widget (ลากเส้นได้, overlay plan จริง!)")
    st.components.v1.html("""
    <div class="tradingview-widget-container">
      <div id="tradingview_legendary"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({
        "width": "100%",
    "height": 600,
    "symbol": "OANDA:XAUUSD",         // ปรับ symbol ได้
    "interval": "15",
    "timezone": "Asia/Bangkok",
    "theme": "dark",
    "style": "1",                     // เปลี่ยนเป็น 1,2,3,4 (แท่งเทียน,เส้น,bar) ได้
    "locale": "th",
    "toolbar_bg": "#f1f3f6",
    "enable_publishing": true,        // เปิดปุ่ม share/snapshot
    "withdateranges": true,           // เปิด TF, date range
    "allow_symbol_change": true,      // เปลี่ยน symbol ได้
    "hide_side_toolbar": false,       // โชว์เครื่องมือวาดเส้น/indicator
    "details": true,                  // เพิ่มรายละเอียด symbol
    "hotlist": true,                  // เพิ่ม hotlist (หุ้น/forex/crypto)
    "calendar": true,                 // เพิ่ม economic calendar
        "container_id": "tradingview_legendary"
      });
      </script>
    </div>
    """, height=620)
    st.caption("ลาก Fibo, Line, Box, วัด RR ได้เต็มรูปแบบ")
    st.info("Overlay แผนเทรดจริงจาก input/log! (รอต่อยอด overlay เส้นอัตโนมัติใน engine ต่อไป)")
else:
    st.info("กดปุ่ม Plot Plan เพื่อแสดงกราฟ TradingView")

st.markdown("---")
st.markdown("Visualizer รับข้อมูลแผนเทรดจริง พร้อม plot overlay (ขยาย/ปรับ engine ได้ทันทีในอนาคต)")



# ======================= SEC 8: AI SUMMARY & INSIGHT =======================
with st.expander("🤖 SEC 8: AI Summary & Insight (Beta)", expanded=True):
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
                st.markdown("### สรุป AI วิเคราะห์ข้อมูลแผนเทรดล่าสุด")
                st.write(f"- **จำนวนแผนเทรด:** {total_trades:,}")
                st.write(f"- **Winrate:** {winrate:.2f}%")
                st.write(f"- **กำไร/ขาดทุนสุทธิ:** {gross_profit:,.2f} USD")
                if avg_rr is not None:
                    st.write(f"- **RR เฉลี่ย:** {avg_rr:.2f}")
                st.write(f"- **Max Drawdown:** {max_drawdown:,.2f} USD")
                st.write(f"- **วันชนะมากสุด:** {win_day}")
                st.write(f"- **วันขาดทุนมากสุด:** {loss_day}")

                # 7. Insight จุดแข็ง/จุดอ่อน (beta)
                st.markdown("### 🤖 AI Insight")
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



# ======================= SEC 9: DASHBOARD + AI ULTIMATE (Tab Template) =======================

import plotly.express as px

tab_dashboard, tab_rr, tab_lot, tab_time, tab_ai, tab_export = st.tabs([
    "📊 Dashboard", 
    "📈 RR Histogram", 
    "📉 Lot Size Evolution", 
    "🕒 Time Analysis", 
    "🤖 AI Recommendation", 
    "⬇️ Export/Report"
])

# ----------- Tab 1: Dashboard Overview -----------
with tab_dashboard:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            if df_log.empty:
                st.info("ยังไม่มีข้อมูลสำหรับ Dashboard")
            else:
                st.markdown("### 🥧 Pie Chart: Win/Loss")
                win_count = df_log[df_log["Risk $"].astype(float) > 0].shape[0]
                loss_count = df_log[df_log["Risk $"].astype(float) <= 0].shape[0]
                pie_df = pd.DataFrame({"Result": ["Win", "Loss"], "Count": [win_count, loss_count]})
                pie_chart = px.pie(pie_df, names="Result", values="Count", color="Result",
                                   color_discrete_map={"Win": "green", "Loss": "red"})
                st.plotly_chart(pie_chart, use_container_width=True)
                
                st.markdown("### 📊 Bar Chart: กำไร/ขาดทุนแต่ละวัน")
                df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce').dt.date
                bar_df = df_log.groupby("Date")["Risk $"].sum().reset_index()
                bar_chart = px.bar(bar_df, x="Date", y="Risk $", color="Risk $",
                                   color_continuous_scale=["red", "orange", "green"])
                st.plotly_chart(bar_chart, use_container_width=True)

                st.markdown("### 📈 Timeline: Balance Curve")
                df_log["Balance"] = acc_balance + df_log["Risk $"].astype(float).cumsum()
                timeline_chart = px.line(df_log, x="Date", y="Balance", markers=True)
                st.plotly_chart(timeline_chart, use_container_width=True)

                st.markdown("### 🔍 Filter Dashboard")
                asset_options = ["ทั้งหมด"] + sorted(df_log["Asset"].unique().tolist())
                selected_asset = st.selectbox("Asset", asset_options, key="asset_filter_dashboard")
                if selected_asset != "ทั้งหมด":
                    df_log = df_log[df_log["Asset"] == selected_asset]
                # เพิ่ม filter อื่นได้ที่นี่

        except Exception as e:
            st.error(f"Error loading dashboard: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Dashboard Visualization")

# ----------- Tab 2: RR Histogram -----------
with tab_rr:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            rr_col = None
            for col in df_log.columns:
                if col.strip().upper() == "RR":
                    rr_col = col
                    break
            if rr_col is not None:
                rr_data = pd.to_numeric(df_log[rr_col], errors='coerce').dropna()
                if len(rr_data) == 0:
                    st.info("ยังไม่มีข้อมูล RR ที่บันทึกใน log_file")
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
                st.warning("ไม่พบคอลัมน์ RR ใน log_file")
        except Exception as e:
            st.error(f"Error loading RR Histogram: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ RR Histogram")

# ----------- Tab 3: Lot Size Evolution -----------
with tab_lot:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            if "Lot" in df_log.columns:
                df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce').dt.date
                st.markdown("#### Lot Size Evolution (การเปลี่ยนแปลง Lot Size ตามเวลา)")
                fig = px.line(
                    df_log,
                    x="Date",
                    y="Lot",
                    markers=True,
                    title="Lot Size Evolution"
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption("วิเคราะห์ Money Management/Scaling ได้ที่นี่")
            else:
                st.warning("ไม่พบคอลัมน์ Lot ใน log_file")
        except Exception as e:
            st.error(f"Error loading Lot Size Evolution: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Lot Size Evolution")

# ----------- Tab 4: Time Analysis -----------
with tab_time:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            st.markdown("#### Time Analysis (วิเคราะห์ตามวัน/เวลา)")
            df_log["Date"] = pd.to_datetime(df_log["Timestamp"], errors='coerce')
            df_log["Weekday"] = df_log["Date"].dt.day_name()
            weekday_df = df_log.groupby("Weekday")["Risk $"].sum().reindex(
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]).reset_index()
            bar_chart = px.bar(weekday_df, x="Weekday", y="Risk $", title="กำไร/ขาดทุนรวมตามวันในสัปดาห์")
            st.plotly_chart(bar_chart, use_container_width=True)
            st.caption("ดูว่าเทรดวันไหนเวิร์ค วันไหนควรหลีกเลี่ยง")
        except Exception as e:
            st.error(f"Error loading Time Analysis: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Time Analysis")

# ----------- Tab 5: AI Recommendation -----------
with tab_ai:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            # ดึง insight/AI Section SEC 8 มาใส่ในนี้ได้เลย
            # ตัวอย่างสั้น (ดึง insight จาก AI)
            st.markdown("### AI Insight & Recommendation")
            total_trades = df_log.shape[0]
            win_trades = df_log[df_log["Risk $"].astype(float) > 0].shape[0]
            loss_trades = df_log[df_log["Risk $"].astype(float) <= 0].shape[0]
            winrate = 100 * win_trades / total_trades if total_trades > 0 else 0
            st.write(f"จำนวนแผนเทรด: {total_trades}")
            st.write(f"Winrate: {winrate:.2f}%")
            insight = []
            if winrate >= 60:
                insight.append("Winrate สูง ระบบเสถียรภาพดี")
            elif winrate < 40:
                insight.append("Winrate ต่ำ ควรพิจารณากลยุทธ์ใหม่")
            if not insight:
                insight.append("ยังไม่พบความเสี่ยงสำคัญ")
            for msg in insight:
                st.info(msg)
            # ขยายเพิ่มคำแนะนำ/alert ได้
        except Exception as e:
            st.error(f"Error loading AI Recommendation: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ AI Recommendation")

# ----------- Tab 6: Export/Report -----------
with tab_export:
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            st.markdown("### Export/Download Report")
            st.download_button("Download log_file (CSV)", df_log.to_csv(index=False), file_name="log_file.csv")
            # ถ้าต้องการ export รูปภาพ chart หรือ export Excel เพิ่มเติมแจ้งได้
        except Exception as e:
            st.error(f"Error loading Export/Report: {e}")
    else:
        st.info("ยังไม่มีข้อมูล log_file สำหรับ Export/Report")



# ======================= SEC 6: LOG VIEWER (ล่างสุด + EXPANDER เดียว) =======================
with st.expander("📚 Log Viewer (คลิกเพื่อเปิด/ปิด)", expanded=False):
    if os.path.exists(log_file):
        try:
            df_log = pd.read_csv(log_file)
            col1, col2, col3 = st.columns(3)
            with col1:
                mode_filter = st.selectbox("Mode", ["ทั้งหมด"] + sorted(df_log["Mode"].unique().tolist()))
            with col2:
                asset_filter = st.selectbox("Asset", ["ทั้งหมด"] + sorted(df_log["Asset"].unique().tolist()))
            with col3:
                date_filter = st.text_input("ค้นหาวันที่ (YYYY-MM-DD)", value="")
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
