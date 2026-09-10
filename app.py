# 文件名: app.py
# 職責: 模組 C 前端 Output HUD 總裝 (資產水流 HUD + 12 檔雷達表 + AI 顧問冷血動作卡 + AI 診斷 Prompt 導出)

import streamlit as st
import datetime
import pytz
import pandas as pd
from data_engine import hub_engine, get_active_session_info
from portfolio_engine import portfolio_engine
from strategy_engine import strategy_engine
import option_0dte_plugin

tz_ny = pytz.timezone("America/New_York")
tz_my = pytz.timezone("Asia/Kuala_Lumpur")

st.set_page_config(
    page_title="Portfolio AI 顧問與量化座艙",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定義暗黑主題 CSS
st.markdown("""
<style>
    .reportview-container { background: #0d1117; }
    .main { background: #0d1117; color: #c9d1d9; }
    div[data-testid="stSidebar"] { background-color: #161b22; border-right: 1px solid #30363d; }
    .stMetric { background-color: #161b22; border: 1px solid #30363d; padding: 10px; border-radius: 6px; }
</style>
""", unsafe_allow_html=True)

# 頂部狀態列
session_key, session_desc, now_ny = get_active_session_info()
now_my = datetime.datetime.now(tz_my)

c_title, c_clock = st.columns([6, 4])
with c_title:
    st.markdown(f"### 🎯 Portfolio AI 顧問與量化座艙 &nbsp;&nbsp; `{session_desc}`")
with c_clock:
    st.caption(f"美東: {now_ny.strftime('%Y-%m-%d %H:%M:%S ET')} | 馬來西亞: {now_my.strftime('%Y-%m-%d %H:%M:%S MYT')}")

# 側邊欄導航
menu_options = [
    "👑 1. 宏觀雷達與波段 AI 顧問",
    "⚡ 2. 0DTE 智能期權射控座艙",
    "💼 3. 實盤帳戶資產與持倉管理"
]

url_tab = st.query_params.get("tab", "radar")
default_idx = 1 if url_tab == "0dte" else (2 if url_tab == "portfolio" else 0)

st.sidebar.markdown("### 🧭 戰略指揮導航")
menu = st.sidebar.radio("選擇作戰模組", menu_options, index=default_idx)

if "2. 0DTE" in menu:
    st.query_params["tab"] = "0dte"
elif "3. 實盤帳戶" in menu:
    st.query_params["tab"] = "portfolio"
else:
    st.query_params["tab"] = "radar"

# 加載資產與帳戶資訊
assets_list = hub_engine.load_watchlist()
acc_summary, pos_df, acc_err = portfolio_engine.fetch_live_account_state()

if not acc_summary:
    acc_summary = {
        'total_assets': 100000.0,
        'cash': 45000.0,
        'market_val': 55000.0,
        'unrealized_pl': 1250.0,
        'cash_ratio': 45.0,
        'status': '🟢 水流健康 (離線模擬)'
    }

# =============================================================================
# 【視圖分發】
# =============================================================================
if "1. 宏觀雷達" in menu:
    # -------------------------------------------------------------------------
    # 模組一：資產水流 HUD (NAV / Cash% / PnL / 購買力)
    # -------------------------------------------------------------------------
    st.markdown("#### 🌊 模組一：資產水流與購買力總舵 (Portfolio HUD)")
    m1, m2, m3, m4, m5 = st.columns(5)
    with m1:
        st.metric("淨資產總值 (NAV)", f"${acc_summary['total_assets']:,.2f}")
    with m2:
        st.metric("可用現金 (Cash)", f"${acc_summary['cash']:,.2f}")
    with m3:
        st.metric("現金佔比 (Cash %)", f"{acc_summary['cash_ratio']:.1f}%")
    with m4:
        pnl_val = acc_summary['unrealized_pl']
        st.metric("浮動盈虧 (PnL)", f"${pnl_val:+,.2f}", delta=f"{pnl_val:+.2f}")
    with m5:
        st.metric("水流健康狀態", acc_summary['status'])

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 計算 12 檔標的量化診斷與評級
    # -------------------------------------------------------------------------
    radar_rows = []
    tactical_cards = []

    for a in assets_list:
        code = a["code"]
        name = a["name"]
        cat = a.get("category", "標的")
        
        # 波段策略計算
        res = strategy_engine.evaluate_swing_tactical(
            code=code,
            total_nav=acc_summary['total_assets'],
            cash_avail=acc_summary['cash']
        )
        guard = strategy_engine.audit_event_guard(code)
        
        if res.get("status") != "NO_DATA":
            radar_rows.append({
                "代碼": code,
                "名稱": name,
                "板塊分類": cat,
                "現價": f"${res['curr_price']:.2f}",
                "大趨勢": res['trend_status'],
                "距EMA20": f"{res['dist_to_ema20_pct']:+.2f}%",
                "排雷狀態": guard['earnings_status'],
                "AI 操作評級": res['rating'],
                "建議股數": f"{res['final_shares']} 股",
                "_raw_code": code,
                "_res": res,
                "_guard": guard
            })
            tactical_cards.append((code, name, res, guard))

    df_radar = pd.DataFrame(radar_rows)

    # -------------------------------------------------------------------------
    # 模組二：12 檔標的雷達全景表 (置頂 QQQ，按評級排序)
    # -------------------------------------------------------------------------
    st.markdown("#### 📡 模組二：12 檔標的宏觀雷達表 (QQQ 總舵置頂)")
    if not df_radar.empty:
        # 置頂 QQQ
        is_qqq = df_radar['代碼'] == 'US.QQQ'
        df_display = pd.concat([df_radar[is_qqq], df_radar[~is_qqq]]).reset_index(drop=True)
        display_cols = ["代碼", "名稱", "板塊分類", "現價", "大趨勢", "距EMA20", "排雷狀態", "AI 操作評級", "建議股數"]
        st.dataframe(df_display[display_cols], use_container_width=True, hide_index=True)
    else:
        st.info("💡 暫無本地 K 線數據，請點擊下方按鈕一鍵同步歷史數據。")

    if st.button("⚡ 一鍵自動補齊 12 檔歷史數據 (Deep Auto-Sync)"):
        with st.spinner("正在為 12 檔標的補齊 5M/1H/DAY 連續數據..."):
            for a in assets_list:
                hub_engine.sync_asset_deep_history(a["code"], bars_5m=1000, bars_day=200)
            st.success("✅ 12 檔數據同步完畢！")
            st.rerun()

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 模組三：AI 顧問冷血動作卡
    # -------------------------------------------------------------------------
    st.markdown("#### 🛡️ 模組三：AI 顧問冷血動作卡 (波段部署指令)")
    col_sel, _ = st.columns([3, 7])
    with col_sel:
        target_card_code = st.selectbox(
            "🎯 選擇查看具體標的動作卡",
            [a["code"] for a in assets_list],
            index=0
        )

    matched_card = next((c for c in tactical_cards if c[0] == target_card_code), None)
    if matched_card:
        _, t_name, c_res, c_guard = matched_card
        
        # 動作卡樣式卡片
        border_color = "#00e676" if "推薦" in c_res['rating'] else ("#ffd600" if "嚴禁" in c_res['rating'] else "#30363d")
        bg_color = "rgba(0, 230, 118, 0.08)" if "推薦" in c_res['rating'] else ("rgba(255, 214, 0, 0.08)" if "嚴禁" in c_res['rating'] else "#161b22")
        
        st.markdown(f"""
        <div style="background: {bg_color}; border: 2px solid {border_color}; border-radius: 8px; padding: 18px 24px; margin-bottom: 15px; font-family: monospace;">
            <div style="font-size: 18px; font-weight: bold; color: #58a6ff; margin-bottom: 8px;">
                📋 動作卡：{target_card_code} ({t_name}) &nbsp;|&nbsp; 狀態: <span style="color: {border_color};">{c_res['rating']}</span>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 32px; font-size: 14px; margin-top: 10px;">
                <div>現價: <b style="color: #79c0ff; font-size: 16px;">${c_res['curr_price']:.2f}</b></div>
                <div>建議掛單價 (Limit): <b style="color: #ffd600;">${c_res['suggest_entry']:.2f}</b></div>
                <div>以損定倉股數: <b style="color: #00e5ff;">{c_res['final_shares']} 股</b> (~${c_res['target_capital']:,.2f} / {c_res['nav_ratio']:.1f}% NAV)</div>
                <div>硬止損位 (SL): <b style="color: #ff7b72;">${c_res['suggest_sl']:.2f}</b></div>
                <div>階梯止盈 1 (+1.5R 減半): <b style="color: #56d364;">${c_res['suggest_tp1']:.2f}</b></div>
                <div>階梯止盈 2 (阻力天花板): <b style="color: #56d364;">${c_res['suggest_tp2']:.2f}</b></div>
            </div>
            <div style="margin-top: 12px; font-size: 12px; color: #8b949e;">
                🛡️ 排雷哨兵：{c_guard['earnings_status']} ｜ {c_guard['fomc_status']}
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 模組四：一鍵生成標準 AI 診斷 Prompt
    # -------------------------------------------------------------------------
    st.markdown("#### 🤖 模組四：一鍵生成標準 AI 診斷 Prompt")
    with st.expander("📝 點擊展開並複製「冷血風控顧問投餵 Prompt」", expanded=False):
        prompt_text = f"""【Portfolio 冷血風控顧問投餵 Prompt】
交易者當前帳戶實況：
- NAV 總資產: ${acc_summary['total_assets']:,.2f} USD
- 可用現金: ${acc_summary['cash']:,.2f} USD (現金佔比: {acc_summary['cash_ratio']:.1f}%)
- 當前持倉標的數: {len(pos_df)} 檔
- 水流健康評級: {acc_summary['status']}

重點關注標的 ({target_card_code}) 量化現狀：
- 現價: ${c_res['curr_price']:.2f} (大趨勢: {c_res['trend_status']})
- EMA20 乖離: {c_res['dist_to_ema20_pct']:+.2f}%
- 建議買入掛單點位: ${c_res['suggest_entry']:.2f}
- 建議硬止損點位: ${c_res['suggest_sl']:.2f}
- Half-Kelly 倉位分配: {c_res['final_shares']} 股 (${c_res['target_capital']:,.2f} USD)
- 排雷狀態: {c_guard['earnings_status']}

請以冷血風控官的視角：
1. 嚴格審查當前持倉是否過度集中？
2. 判定該標的目前是否值得以損定倉掛單？
3. 給出若市場大幅回撤時的極限防守預案。"""
        st.text_area("可直接複製以下內容投餵給 AI：", prompt_text, height=220)

elif "2. 0DTE" in menu:
    # 調用 0DTE 期權戰術射控艙模組
    option_0dte_plugin.render_0dte_cockpit_view(assets=assets_list)

elif "3. 實盤帳戶" in menu:
    st.markdown("## 💼 實盤帳戶資產與持倉管理")
    if not pos_df.empty:
        st.dataframe(pos_df, use_container_width=True)
    else:
        st.info("暫無活躍持倉或處於模擬待機狀態。")
