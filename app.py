# 文件名: app.py
# 职责: 侧边栏主导航 (QQQ 置顶) + 5 大主功能模块完整装配

import streamlit as st
from data_engine import hub_engine
import chart_view_plugin
from portfolio_manager_plugin import render_portfolio_securities, render_portfolio_analysis
from macro_radar_plugin import render_macro_radar_view
from ai_audit_plugin import render_ai_audit_view
from radar_engine import compute_radar_metrics

st.set_page_config(
    page_title="GUI Water Terminal",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 1. 侧边栏主导航
st.sidebar.markdown("### 🎛️ 主控制中枢")
main_choice = st.sidebar.radio(
    "NAVIGATION",
    [
        "👑 1. US.QQQ 纳指中枢",
        "💼 2. 我的实操持仓 (Portfolio)",
        "📡 3. 12档核心宏观雷达",
        "🌊 4. 波浪推演与走势预测",
        "📋 5. 策略记账与复盘打点"
    ],
    index=0
)

# 2. 标的资产加载
assets = hub_engine.load_watchlist()

# -------------------------------------------------------------
# MAIN 1: QQQ 纳指中枢
# -------------------------------------------------------------
if main_choice == "👑 1. US.QQQ 纳指中枢":
    st.markdown("## 👑 US.QQQ 纳指大盘总舵")
    sub_tab1, sub_tab2, sub_tab3 = st.tabs(["📈 Chart (图表穿透)", "🧭 Analysis (战区与宏观)", "📰 News & AI 审计"])
    
    with sub_tab1:
        c1, c2 = st.columns([3, 1])
        with c1:
            ktype = st.selectbox("周期切换", ["5M", "1H", "DAY"], index=0, key="qqq_ktype")
        with c2:
            bars = st.slider("显示柱数", 30, 300, 100, step=10, key="qqq_bars")
        chart_view_plugin.render_lightweight_tv_chart("US.QQQ", ktype, bars)
        
    with sub_tab2:
        st.markdown("### 🧭 QQQ 攻防阶梯与宏观状态")
        snap = hub_engine.get_realtime_snapshot(["US.QQQ"])
        cur_p = float(snap.iloc[0].get('last_price', 0.0)) if (snap is not None and not snap.empty) else 0.0
        m = compute_radar_metrics("US.QQQ", live_price=cur_p)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("⚡ QQQ 现价", f"${cur_p:,.2f}" if cur_p > 0 else "--")
        c2.metric("🔵 1H EMA20 均线", f"${m['ema20_1h']:,.2f}" if m['ema20_1h'] > 0 else "--")
        c3.metric("昨日最高 (PDH)", f"${m['pdh']:,.2f}" if m['pdh'] > 0 else "--")
        c4.metric("昨日最低 (PDL)", f"${m['pdl']:,.2f}" if m['pdl'] > 0 else "--")
        
        st.markdown("---")
        st.markdown(f"**Trend Bias 定调**: `{m['trend_bias']}` | **当前指令**: `{m['action_hint']}`")
        st.markdown(f"• **今日买入地板 (RBS / PDL)**: `{m['floor_zone']}`")
        st.markdown(f"• **向上突破阻力 (SBR / PDH)**: `{m['ceiling_zone']}`")
        
    with sub_tab3:
        render_ai_audit_view()

# -------------------------------------------------------------
# MAIN 2: 个人实操持仓 (Portfolio)
# -------------------------------------------------------------
elif main_choice == "💼 2. 我的实操持仓 (Portfolio)":
    st.markdown("## 💼 个人实操持仓与资产罗盘")
    sub_tab1, sub_tab2 = st.tabs(["📋 Securities (实盘美股持仓)", "💰 Analysis (资产与流动性分析)"])
    
    with sub_tab1:
        render_portfolio_securities()
        
    with sub_tab2:
        render_portfolio_analysis()

# -------------------------------------------------------------
# MAIN 3: 12档核心宏观雷达
# -------------------------------------------------------------
elif main_choice == "📡 3. 12档核心宏观雷达":
    st.markdown("## 📡 12档核心宏观雷达与战区")
    render_macro_radar_view(assets)

# -------------------------------------------------------------
# MAIN 4 & 5: 预留拓展模块
# -------------------------------------------------------------
else:
    st.markdown(f"## {main_choice}")
    st.info("模块持续迭代中...")
