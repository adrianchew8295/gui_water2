# 文件名: app.py
# 职责: 侧边栏主导航 (QQQ 置顶) + 右侧多子 Tab 容器装载

import streamlit as st
from data_engine import hub_engine
import chart_view_plugin
from portfolio_manager_plugin import render_portfolio_securities, render_portfolio_analysis

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
        st.info("💡 阶梯战区计算模块将于 Step 3 挂载（PDH/PDL、1H EMA20 动态通道）。")
        
    with sub_tab3:
        st.markdown("### 📰 宏观动态与 AI 诊断反馈")
        st.info("💡 AI 审计 Prompt 生成器将于 Step 4 接入。")

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
    st.markdown("## 📡 12档核心宏观雷达")
    st.info("💡 宏观雷达全景总表将于 Step 3 注入。")

# -------------------------------------------------------------
# MAIN 4 & 5: 预留模块
# -------------------------------------------------------------
else:
    st.markdown(f"## {main_choice}")
    st.info("模块构建中...")
