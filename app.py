# 文件名: app.py
# 職責: GUI Water 總裝主入口 · 全面解耦各子模組

import streamlit as st, datetime, pytz
from data_engine import hub_engine, get_active_session_info
import chart_view_plugin, macro_radar_plugin, journal_plugin, portfolio_manager_plugin, option_0dte_plugin, ai_portfolio_advisor_plugin

tz_ny = pytz.timezone("America/New_York")
tz_my = pytz.timezone("Asia/Kuala_Lumpur")

st.set_page_config(page_title="GUI WATER TERMINAL", page_icon="🌊", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
    .reportview-container { background: #0d1117; }
    .main { background: #0d1117; color: #c9d1d9; }
    div[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)

session_key, session_desc, now_ny = get_active_session_info()
now_my = datetime.datetime.now(tz_my)

c_title, c_clock = st.columns([6, 4])
with c_title:
    st.markdown(f"### 🌊 GUI WATER TERMINAL &nbsp;&nbsp; {session_desc}")
with c_clock:
    st.caption(f"美東: {now_ny.strftime('%Y-%m-%d %H:%M:%S ET')} | 馬來西亞: {now_my.strftime('%Y-%m-%d %H:%M:%S MYT')}")

menu_options = [
    "👑 1. 宏觀雷達與波段 AI 顧問 (三合一)",
    "⚡ 2. 0DTE 智能期權射控座艙",
    "📊 3. 策略復盤與實盤訂單帳本",
    "💼 4. 實盤帳戶資產與持倉管理"
]

url_tab = st.query_params.get("tab", "radar")
default_idx = 1 if url_tab == "0dte" else (2 if url_tab == "journal" else (3 if url_tab == "portfolio" else 0))

st.sidebar.markdown("### 🧭 戰略指揮導航")
menu = st.sidebar.radio("選擇核心作戰模組", menu_options, index=default_idx)

if "1. 宏觀雷達" in menu:
    st.query_params["tab"] = "radar"
elif "2. 0DTE" in menu:
    st.query_params["tab"] = "0dte"
elif "3. 策略復盤" in menu:
    st.query_params["tab"] = "journal"
elif "4. 實盤帳戶" in menu:
    st.query_params["tab"] = "portfolio"

if "1. 宏觀雷達" in menu:
    st.markdown("## 🎯 模組一：資產水流與購買力總舵 (Portfolio HUD)")
    portfolio_manager_plugin.render_portfolio_hud()
    st.markdown("---")
    st.markdown("## 📡 模組二：12 檔核心宏觀雷達與攻防戰區")
    macro_radar_plugin.render_macro_radar_view(assets=hub_engine.load_watchlist())
    st.markdown("---")
    ai_portfolio_advisor_plugin.render_ai_portfolio_advisor_view()

elif "2. 0DTE" in menu:
    st.markdown("## ⚡ 0DTE 智能期權射控座艙")
    option_0dte_plugin.render_0dte_view()

elif "3. 策略復盤" in menu:
    st.markdown("## 📊 策略復盤與實盤訂單帳本")
    journal_plugin.render_journal_view(hub_engine.load_watchlist())

elif "4. 實盤帳戶" in menu:
    st.markdown("## 💼 實盤帳戶資產與持倉管理")
    portfolio_manager_plugin.render_portfolio_analysis()
