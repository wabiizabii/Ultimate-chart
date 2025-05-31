import os
import csv
import json
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import streamlit.components.v1 as components

# ─── Configuration ────────────────────────────────────────────────
BALANCE  = 10000.0           # ค่าเริ่มต้นถ้ายังไม่ได้ผูก MT5
LOG_FILE = "trade_log.csv"   # ไฟล์เก็บ Log

# ─── Page Config ─────────────────────────────────────────────────
st.set_page_config(layout="wide")

# ─── Sidebar: Input Form ───────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Trade Plan Input")

    # 1) Mode selector
    mode = st.radio("Mode", ["FIBO", "CUSTOM"], horizontal=True)

    # 2) FIBO Mode
    if mode == "FIBO":
        # เลือกระดับ Fibo ที่จะใช้งาน
        all_levels   = [0.114, 0.25, 0.382, 0.5, 0.618]
        all_labels   = [f"{lvl*100:.1f}%" for lvl in all_levels]
        sel_labels   = st.multiselect(
            "Select Fibo Levels", all_labels, default=all_labels[:3]
        )
        levels       = [all_levels[all_labels.index(lbl)] for lbl in sel_labels]

        # Inputs
        swing_high   = st.number_input("Swing High", format="%.5f")
        swing_low    = st.number_input("Swing Low",  format="%.5f")
        risk_pct     = st.number_input("Risk %", 0.0, 100.0, 1.0, step=0.1)/100
        direction    = st.selectbox("Direction", ["Long", "Short"])

    # 3) CUSTOM Mode
    else:
        # จำนวน Leg
        num_legs     = st.number_input("จำนวนไม้ (Legs)", 1, 5, 1, step=1)
        entry_prices = []
        sl_prices    = []
        for i in range(int(num_legs)):
            entry_prices.append(
                st.number_input(f"Entry Price {i+1}", format="%.5f", key=f"e{i}")
            )
            sl_prices.append(
                st.number_input(f"SL Price   {i+1}", format="%.5f", key=f"s{i}")
            )
        risk_pct     = st.number_input("Risk %", 0.0, 100.0, 1.0, step=0.1)/100
        direction    = st.selectbox("Direction", ["Long", "Short"])

    # ปุ่ม Refresh (เข้าใจว่าใช้เมื่อต้องการค้างฟอร์ม)
    st.button("🔄 Refresh Inputs")

    # ปุ่มสำรอง (Copy / Send / Save)
    copy_plan_btn = st.button("📋 Copy Plan")
    send_mt5_btn  = st.button("➡️ Send to MT5 (Mock)")
    save_plan_btn = st.button("💾 Save Plan")

# ─── Embed TradingView Chart ────────────────────────────────────────
components.html(
    """
    <div class="tradingview-widget-container">
      <div id="tv_chart"></div>
      <script src="https://s3.tradingview.com/tv.js"></script>
      <script>
      new TradingView.widget({
        "container_id":"tv_chart","width":"100%","height":350,
        "symbol":"FX:EURUSD","interval":"60","timezone":"Asia/Bangkok",
        "theme":"dark","style":"1","toolbar_bg":"#f1f3f6",
        "hide_top_toolbar":false,"withdateranges":true,
        "allow_symbol_change":true
      });
      </script>
    </div>
    """,
    height=370,
    scrolling=True,
)

# ─── Calculation ────────────────────────────────────────────────────
# 1) Entry prices & stop_loss per leg
if mode == "FIBO":
    entry_prices = []
    for lvl in levels:
        if direction == "Long":
            entry_prices.append(swing_high - (swing_high - swing_low)*lvl)
        else:
            entry_prices.append(swing_low + (swing_high - swing_low)*lvl)
    stop_loss = abs(entry_prices[0] - (swing_low if direction=="Long" else swing_high))
else:
    stop_loss = abs(entry_prices[0] - sl_prices[0])

# 2) Lot distribution (equal)
risk_amount = BALANCE * risk_pct
total_lot   = risk_amount / stop_loss if stop_loss>0 else 0
n_legs      = len(entry_prices)
lot_sizes   = [total_lot/n_legs]*n_legs

# 3) TP calculation (from same Fibo line)
tp_mult    = [1.618, 2.618, 4.236]
tp_prices  = []
for i, ep in enumerate(entry_prices):
    m = tp_mult[min(i, len(tp_mult)-1)]
    base = (swing_low if mode=="FIBO" else sl_prices[0]) if direction=="Long" \
           else (swing_high if mode=="FIBO" else sl_prices[0])
    if direction=="Long":
        tp_prices.append(ep + (ep - base)*(m-1))
    else:
        tp_prices.append(ep - ((base - ep)*(m-1)))

# 4) RR ratios & Profits
rr_ratios  = [(tp - ep)/stop_loss for ep, tp in zip(entry_prices, tp_prices)]
profits    = [ls*(tp - ep) for ep, ls, tp in zip(entry_prices, lot_sizes, tp_prices)]

# prepare payload
plan_payload = {
    "timestamp":     datetime.now().isoformat(),
    "mode":          mode,
    "direction":     direction,
    "risk_pct":      risk_pct,
    "entry_prices":  entry_prices,
    "sl_pp":         stop_loss,
    "lot_sizes":     lot_sizes,
    "tp_prices":     tp_prices,
    "rr_ratios":     rr_ratios,
    "profits":       profits,
}

# ─── Copy / Send / Save ──────────────────────────────────────────────
if copy_plan_btn:
    st.sidebar.code(json.dumps(plan_payload, indent=2))
    st.sidebar.success("Copied JSON payload")

if send_mt5_btn:
    st.sidebar.json(plan_payload)
    st.sidebar.info("Mock sent to MT5")

if save_plan_btn:
    df_row = pd.DataFrame([plan_payload])
    df_row.to_csv(
        LOG_FILE, mode="a",
        header=not os.path.exists(LOG_FILE),
        index=False, quoting=csv.QUOTE_NONNUMERIC
    )
    st.sidebar.success(f"Saved to {LOG_FILE}")

# ─── Display Results ─────────────────────────────────────────────────
# Entry & TP inline table
df_display = pd.DataFrame({
    "Entry":  [f"{x:.5f}" for x in entry_prices],
    "Lot":    [f"{x:.2f}" for x in lot_sizes],
    "TP":     [f"{x:.5f}" for x in tp_prices],
    "RR":     [f"{x:.2f}" for x in rr_ratios],
    "Profit": [f"{x:.2f}" for x in profits],
})
st.markdown("## ⭐ Entry Plan + TP + RR + Profit")
st.dataframe(df_display, use_container_width=True)

# Trade Summary
total_lots = sum(lot_sizes)
total_risk = total_lots * stop_loss
st.markdown("## 📊 Trade Summary")
st.write(f"- **Total Lots:** {total_lots:.2f}")
st.write(f"- **Total Risk $:** {total_risk:.2f}")

# ─── Dashboard ────────────────────────────────────────────────────────
st.markdown("## 🔄 Dashboard")
if os.path.exists(LOG_FILE):
    df_log = pd.read_csv(LOG_FILE)
    df_log["timestamp"] = pd.to_datetime(df_log["timestamp"])
    st.dataframe(df_log)
else:
    st.info("No trades logged yet.")
