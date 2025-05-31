import os, csv, json
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import streamlit.components.v1 as components

# ─── Configuration ────────────────────────────────────────────────
BALANCE  = 10000.0
LOG_FILE = "trade_log.csv"

# ─── Page Config ─────────────────────────────────────────────────
st.set_page_config(layout="wide")

# ─── Global CSS ───────────────────────────────────────────────────
st.markdown("""
<style>
/* ปรับ background ของ selectbox/multiselect ที่ยังไม่ถูกเลือก */
[data-baseweb="select"] > div,
[data-baseweb="multi-select"] > div > div:first-child {
  background-color: #2f2f2f !important;
}
/* tag ที่ยังไม่ถูกเลือก */
[data-baseweb="multi-select"] span[class*="tag"] {
  background-color: #444 !important;
  color: #bbb !important;
}
/* tag ที่ถูกเลือก */
[data-baseweb="multi-select"] span[class*="tag"] div {
  background-color: #007bff !important;
  color: #fff !important;
}
/* ปรับข้อความ warning/info */
.css-1t3v75u, .css-1f6uilx {
  color: #f39c12 !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Sidebar: Input Form ───────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Trade Plan Input")
    mode = st.radio("Mode", ["FIBO", "CUSTOM"], horizontal=True)

    if mode == "FIBO":
        # FIBO mode inputs
        levels_all = [0.114, 0.25, 0.382, 0.5, 0.618]
        labels_all = [f"{l*100:.1f}%" for l in levels_all]
        chosen = st.multiselect("Select Fibo Levels", labels_all, default=labels_all[:3])
        levels = [levels_all[labels_all.index(lbl)] for lbl in chosen]

        swing_high = st.number_input("Swing High", format="%.5f")
        swing_low  = st.number_input("Swing Low",  format="%.5f")
        risk_pct   = st.number_input("Risk %", 0.0, 100.0, 1.0, step=0.1)/100
        direction  = st.selectbox("Direction", ["Long", "Short"])

    else:
        # CUSTOM mode inputs
        num_legs = st.number_input("จำนวนไม้ (Legs)", 1, 5, 1, step=1)
        entry_prices, sl_prices, tp_inputs = [], [], []
        for i in range(int(num_legs)):
            st.markdown(f"---\n**Leg {i+1}**")
            ep = st.number_input(f"Entry Price {i+1}", format="%.5f", key=f"e{i}")
            sp = st.number_input(f"SL Price   {i+1}", format="%.5f", key=f"s{i}")
            tp = st.number_input(f"TP Price   {i+1}", format="%.5f", key=f"t{i}")
            entry_prices.append(ep)
            sl_prices.append(sp)
            tp_inputs.append(tp)
        risk_pct  = st.number_input("Risk %", 0.0, 100.0, 1.0, step=0.1)/100
        direction = st.selectbox("Direction", ["Long", "Short"])

    st.markdown("---")
    copy_btn = st.button("📋 Copy Plan")
    send_btn = st.button("➡️ Send to MT5 (Mock)")
    save_btn = st.button("💾 Save Plan")

# ─── TradingView Chart ─────────────────────────────────────────────
components.html("""
<div class="tradingview-widget-container">
  <div id="tv_chart"></div>
  <script src="https://s3.tradingview.com/tv.js"></script>
  <script>
    new TradingView.widget({
      "container_id":"tv_chart","width":"100%","height":300,
      "symbol":"FX:EURUSD","interval":"60","timezone":"Asia/Bangkok",
      "theme":"dark","style":"1"
    });
  </script>
</div>
""", height=320)

# ─── Calculation ────────────────────────────────────────────────────
if mode == "FIBO":
    # Entry per chosen Fibo level
    entry_prices = [
        swing_high - (swing_high - swing_low)*lvl if direction=="Long"
        else swing_low + (swing_high - swing_low)*lvl
        for lvl in levels
    ]
    # stop_loss from first leg
    stop_loss = abs(entry_prices[0] - (swing_low if direction=="Long" else swing_high))

    # Lot distribution equal per leg
    risk_amt  = BALANCE * risk_pct
    total_lot = risk_amt/stop_loss if stop_loss>0 else 0
    lot_sizes = [total_lot/len(entry_prices)]*len(entry_prices)

    # TP targets (same fibo line)
    tp_mults  = [1.618,2.618,4.236]
    base      = swing_low if direction=="Long" else swing_high
    tp_prices = [
        entry_prices[0] + (entry_prices[0]-base)*(m-1) if direction=="Long"
        else entry_prices[0] - ((base-entry_prices[0])*(m-1))
        for m in tp_mults
    ]

else:
    # CUSTOM
    stop_loss  = abs(entry_prices[0]-sl_prices[0])
    risk_amt   = BALANCE * risk_pct
    total_lot  = risk_amt/stop_loss if stop_loss>0 else 0
    lot_sizes  = [total_lot/len(entry_prices)]*len(entry_prices)
    tp_prices  = tp_inputs

# Guard for missing inputs
if mode=="FIBO" and (not levels or swing_high<=swing_low):
    st.info("🛈 กรุณากรอก Swing High > Swing Low และเลือกระดับ Fibo ก่อนดูผล")
    rr      = [None]*len(entry_prices)
    profits = [0]*len(entry_prices)
else:
    if stop_loss==0:
        st.warning("⚠️ Stop-loss = 0 — ตรวจสอบ Swing/SL อีกครั้ง")
        rr      = [None]*len(entry_prices)
        profits = [0]*len(entry_prices)
    else:
        rr      = [ (tp-entry)/stop_loss for entry,tp in zip(entry_prices, tp_prices) ]
        profits = [ ls*(tp-entry)    for entry,ls,tp in zip(entry_prices, lot_sizes, tp_prices) ]

risk_per_leg = [ ls*stop_loss for ls in lot_sizes ]

# Payload for Copy/Send/Save
payload = {
    "time":     datetime.now().isoformat(),
    "mode":     mode,
    "dir":      direction,
    "r%":       risk_pct,
    "entry":    entry_prices,
    "sl":       stop_loss,
    "lot":      lot_sizes,
    "tp":       tp_prices,
    "rr":       rr,
    "risk$":    risk_per_leg,
    "profit$":  profits
}

# Copy / Send / Save actions
if copy_btn:
    st.sidebar.code(json.dumps(payload, indent=2))
    st.sidebar.success("Copied JSON payload")

if send_btn:
    st.sidebar.json(payload)
    st.sidebar.info("Mock send to MT5")

if save_btn:
    pd.DataFrame([payload]).to_csv(
        LOG_FILE, mode="a", header=not os.path.exists(LOG_FILE),
        index=False, quoting=csv.QUOTE_NONNUMERIC
    )
    st.sidebar.success(f"Saved to {LOG_FILE}")

# ─── Display Entry Plan ─────────────────────────────────────────────
st.markdown("## ⭐ Entry Plan")
df_entry = pd.DataFrame({
    "Entry":  [f"{x:.5f}" for x in entry_prices],
    "Lot":    [f"{x:.2f}" for x in lot_sizes],
    "Risk $": [f"{x:.2f}" for x in risk_per_leg]
})
st.dataframe(df_entry, use_container_width=True)

# ─── Display TP Targets ─────────────────────────────────────────────
if mode=="FIBO":
    st.markdown("## 🎯 TP Targets")
    df_tp = pd.DataFrame({
        "Target":        ["TP1",    "TP2",    "TP3"],
        "Price":         [f"{p:.5f}" for p in tp_prices[:3]],
        "RR":            [f"{r:.2f}"   for r in rr[:3]],
        "Profit per Leg":[f"{pr:.2f}" for pr in profits[:3]],
    })
    st.table(df_tp)

# ─── Display CUSTOM RR Recommendations ──────────────────────────────
if mode=="CUSTOM":
    st.markdown("## ⚙️ CUSTOM Mode RR Recommendations")
    for i,(entry, sl, tp_i, rr_i) in enumerate(zip(entry_prices, sl_prices, tp_prices, rr), start=1):
        rec = ""
        if tp_i>0 and rr_i is not None and rr_i<3:
            rec_tp = entry + 3*abs(entry-sl)
            rec    = f" — ⚠️ RR {rr_i:.2f}<3 → แนะนำ TP ≥ {rec_tp:.5f}"
        st.write(f"- Leg {i}: Entry={entry:.5f}, SL={sl:.5f}, TP={tp_i:.5f}, RR={rr_i or 0:.2f}{rec}")

# ─── Dashboard ─────────────────────────────────────────────────────
st.markdown("## 🔄 Dashboard")
if os.path.exists(LOG_FILE):
    df_log = pd.read_csv(LOG_FILE)
    df_log["time"] = pd.to_datetime(df_log["time"])
    st.dataframe(df_log, use_container_width=True)
else:
    st.info("No trades logged yet.")
