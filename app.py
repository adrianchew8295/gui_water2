# 文件名: app.py
# 職責: 頂部時段狀態對齊 (Active Session) + 側邊欄主導航 + 雙軌日誌黑匣子 (已解除靜態鎖)

import os
import streamlit as st
import pytz
import datetime
from data_engine import hub_engine, get_active_session_info, LOG_PATH
import chart_view_plugin
from portfolio_manager_plugin import render_portfolio_securities, render_portfolio_analysis
from macro_radar_plugin import render_macro_radar_view
from ai_audit_plugin import render_ai_audit_view
from radar_engine import compute_radar_metrics

tz_ny = pytz.timezone("America/New_York")
tz_myt = pytz.timezone("Asia/Kuala_Lumpur")

st.set_page_config(
    page_title="GUI Water Terminal",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 1. 頂部時鐘與 Active Session 狀態條
session_id, session_desc, now_ny = get_active_session_info()
now_myt = datetime.datetime.now(tz_myt)

col_t1, col_t2 = st.columns([7, 3])
with col_t1:
    st.markdown(f"### 🌊 GUI WATER TERMINAL &nbsp;&nbsp; `{session_desc}`")
with col_t2:
    st.caption(f"美東: {now_ny.strftime('%Y-%m-%d %H:%M:%S ET')} | 馬來西亞: {now_myt.strftime('%H:%M:%S MYT')}")

# 2. 側邊欄主導航
st.sidebar.markdown("### 🎛️ 主控制中樞")
main_choice = st.sidebar.radio(
    "NAVIGATION",
    [
        "👑 1. US.QQQ 納指中樞",
        "💼 2. 我的實操持倉 (Portfolio)",
        "📡 3. 12檔核心宏觀雷達",
        "🌊 4. 波浪推演與走勢預測",
        "📋 5. 策略記賬與復盤打點"
    ],
    index=0
)

# 側邊欄手動自癒按鈕
if st.sidebar.button("🔄 手動自癒補齊今日數據", use_container_width=True):
    ok, msg = hub_engine.auto_heal_today_data("US.QQQ")
    if ok:
        st.sidebar.success(msg)
        st.rerun()
    else:
        st.sidebar.error(msg)

assets = hub_engine.load_watchlist()

# -------------------------------------------------------------
# MAIN 1: QQQ 納指中樞
# -------------------------------------------------------------
if main_choice == "👑 1. US.QQQ 納指中樞":
    st.markdown("## 👑 US.QQQ 納指大盤總舵")
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["📈 Chart (圖表穿透)", "🧭 Analysis (戰區與宏觀)", "📰 News & AI 審計"])
    
    with sub_tab1:
        c1, c2 = st.columns([3, 1])
        with c1:
            ktype = st.selectbox("週期切換", ["5M", "1H", "DAY"], index=0, key="qqq_ktype")
        with c2:
            bars = st.slider("顯示柱數", 30, 300, 100, step=10, key="qqq_bars")
        chart_view_plugin.render_lightweight_tv_chart("US.QQQ", ktype, bars)
        
    with sub_tab2:
        st.markdown("### 🧭 QQQ 攻防階梯與宏觀狀態")
        snap = hub_engine.get_realtime_snapshot(["US.QQQ"])
        cur_p = float(snap.iloc[0].get('last_price', 0.0)) if (snap is not None and not snap.empty) else 0.0
        m = compute_radar_metrics("US.QQQ", live_price=cur_p)
        
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("⚡ QQQ 現價", f"${cur_p:,.2f}" if cur_p > 0 else "--")
        c2.metric("🟡 PMH (盤前高)", f"${m['pmh']:,.2f}" if m['pmh'] > 0 else "--")
        c3.metric("🟡 PML (盤前低)", f"${m['pml']:,.2f}" if m['pml'] > 0 else "--")
        c4.metric("昨日最高 (PDH)", f"${m['pdh']:,.2f}" if m['pdh'] > 0 else "--")
        c5.metric("昨日最低 (PDL)", f"${m['pdl']:,.2f}" if m['pdl'] > 0 else "--")
        
        st.markdown("---")
        st.markdown(f"**時段定調**: `{m['action_hint']}` | **Trend Bias**: `{m['trend_bias']}`")
        st.markdown(f"• **今日買入地板 (RBS / PML)**: `{m['floor_zone']}`")
        st.markdown(f"• **向上突破阻力 (SBR / PMH)**: `{m['ceiling_zone']}`")
        
    with sub_tab3:
        render_ai_audit_view()

# -------------------------------------------------------------
# MAIN 2: 實操持倉
# -------------------------------------------------------------
elif main_choice == "💼 2. 我的實操持倉 (Portfolio)":
    st.markdown("## 💼 個人實操持倉與資產羅盤")
    sub_tab1, sub_tab2 = st.tabs(["📋 Securities (實盤美股持倉)", "💰 Analysis (資產與流動性分析)"])
    with sub_tab1:
        render_portfolio_securities()
    with sub_tab2:
        render_portfolio_analysis()

# -------------------------------------------------------------
# MAIN 3: 宏觀雷達
# -------------------------------------------------------------
elif main_choice == "📡 3. 12檔核心宏觀雷達":
    st.markdown("## 📡 12檔核心宏觀雷達與戰區")
    render_macro_radar_view(assets)

# -------------------------------------------------------------
# MAIN 4 & 5: 預留模組
# -------------------------------------------------------------
else:
    st.markdown(f"## {main_choice}")
    st.info("模組持續迭代中...")

# -------------------------------------------------------------
# 底部黑匣子: 系統狀態與數據健康日誌
# -------------------------------------------------------------
st.markdown("---")
with st.expander("🔍 系統數據健康與審核日誌 (System Health Log)", expanded=False):
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            logs = f.readlines()
            st.code("".join(logs[-15:]), language="text")
    else:
        st.info("⚪ 暫無日誌記錄。")
