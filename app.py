# 文件名: app.py
# 職責: GUI Water 總裝主入口 · 全面解耦各子模組 · 整合 QQQ、宏觀雷達、復盤帳本、實盤持倉與 0DTE 智能射控

import streamlit as st
import datetime
import pytz
from data_engine import hub_engine, get_active_session_info
import chart_view_plugin
import macro_radar_plugin
import journal_plugin
import portfolio_manager_plugin
import option_0dte_plugin

tz_ny = pytz.timezone("America/New_York")
tz_my = pytz.timezone("Asia/Kuala_Lumpur")

st.set_page_config(
    page_title="GUI WATER TERMINAL",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定義暗黑主題 CSS
st.markdown("""
<style>
    .reportview-container { background: #0d1117; }
    .main { background: #0d1117; color: #c9d1d9; }
    div[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
</style>
""", unsafe_allow_html=True)

# 頂部狀態列
session_key, session_desc, now_ny = get_active_session_info()
now_my = datetime.datetime.now(tz_my)

c_title, c_clock = st.columns([6, 4])
with c_title:
    st.markdown(f"### 🌊 GUI WATER TERMINAL &nbsp;&nbsp; {session_desc}")
with c_clock:
    st.caption(f"美東: {now_ny.strftime('%Y-%m-%d %H:%M:%S ET')} | 馬來西亞: {now_my.strftime('%Y-%m-%d %H:%M:%S MYT')}")

# 核心選單定義
menu_options = [
    "👑 1. US.QQQ 納指大盤總舵",
    "⚡ 2. 0DTE 智能期權射控座艙",
    "📡 3. 12檔核心宏觀雷達與戰區",
    "📊 4. 策略復盤與實盤訂單帳本",
    "💼 5. 實盤帳戶資產與持倉管理"
]

# URL query_params 路由持久化
url_tab = st.query_params.get("tab", "radar" if "tab" in st.query_params else "radar")
default_idx = 1 if url_tab == "0dte" else (2 if url_tab == "radar" else (3 if url_tab == "journal" else (4 if url_tab == "portfolio" else 0)))

st.sidebar.markdown("### 🧭 戰略指揮導航")
menu = st.sidebar.radio("選擇核心作戰模組", menu_options, index=default_idx)

# 將當前選中的分頁同步寫入 URL 參數
if "2. 0DTE" in menu:
    st.query_params["tab"] = "0dte"
elif "3. 12檔" in menu:
    st.query_params["tab"] = "radar"
elif "4. 策略復盤" in menu:
    st.query_params["tab"] = "journal"
elif "5. 實盤帳戶" in menu:
    st.query_params["tab"] = "portfolio"
else:
    st.query_params["tab"] = "qqq"

# 模組分發
if "1. US.QQQ" in menu:
    st.markdown("## 👑 US.QQQ 納指大盤總舵")
    t_chart, t_ana = st.tabs(["📈 Chart (圖表穿透)", "🧭 Analysis (戰區與宏觀)"])
    with t_chart:
        chart_view_plugin.render_lightweight_tv_chart(code="US.QQQ")
    with t_ana:
        macro_radar_plugin.render_macro_radar_view(assets=[{"code": "US.QQQ"}])

elif "2. 0DTE" in menu:
    st.markdown("## ⚡ 0DTE 智能期權射控座艙")
    option_0dte_plugin.render_0dte_cockpit_view(assets=hub_engine.load_watchlist())

elif "3. 12檔" in menu:
    st.markdown("## 📡 12 檔核心宏觀雷達與攻防戰區")
    portfolio_manager_plugin.render_portfolio_hud()
    st.markdown("---")
    macro_radar_plugin.render_macro_radar_view(assets=hub_engine.load_watchlist())

elif "4. 策略復盤" in menu:
    st.markdown("## 📊 策略復盤與實盤訂單帳本")
    journal_plugin.render_journal_view(hub_engine.load_watchlist())

elif "5. 實盤帳戶" in menu:
    st.markdown("## 💼 實盤帳戶資產與持倉管理")
    portfolio_manager_plugin.render_portfolio_analysis()
