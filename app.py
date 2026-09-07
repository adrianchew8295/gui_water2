# 文件名: app.py
# 职责: Market Data Hub 主控制看板 (可折叠分类总表 + 多周期数据池监控 + 独立图表视图插件挂载)

import streamlit as st
import pandas as pd
import os
import datetime
import pytz
from data_engine import hub_engine
from chart_view_plugin import chart_plugin

tz_ny = pytz.timezone("America/New_York")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")

st.set_page_config(page_title="Market Data Hub V2", page_icon="🏛️", layout="wide")

# 暗黑金融终端样式
st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 0rem; max-width: 98%; }
    .status-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace; font-weight: bold; }
    .tag-green { background: #238636; color: white; }
    .tag-blue { background: #1f6feb; color: white; }
</style>
""", unsafe_allow_html=True)

watchlist = hub_engine.load_watchlist()

# 侧边栏：标的管理与一键 Fetch
with st.sidebar:
    st.header("⚙️ 标的管理中枢")
    with st.expander("➕ 添加新标的", expanded=False):
        new_code = st.text_input("标的代码 (如 US.PLTR / US.TSLA)", value="").strip().upper()
        new_name = st.text_input("标的中文简称", value="").strip()
        new_cat = st.selectbox("所属板块分类", ["🚀 核心指数", "🏛️ 科技巨头", "💾 芯片半导体", "🪙 加密资产", "📦 其它关注"])
        if st.button("确认添加标的", use_container_width=True):
            if new_code and not any(a['code'] == new_code for a in watchlist):
                asset_type = "CRYPTO" if new_code.startswith("CC.") else "STOCK"
                watchlist.append({"code": new_code, "name": new_name or new_code, "category": new_cat, "type": asset_type})
                hub_engine.save_watchlist(watchlist)
                st.success(f"已成功添加: {new_code}")
                st.rerun()

    st.markdown("---")
    st.markdown("##### 标的清单与操作")
    for item in watchlist:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"**{item['code']}** ({item['name']})")
        if c2.button("🗑️", key=f"del_{item['code']}"):
            watchlist = [a for a in watchlist if a['code'] != item['code']]
            hub_engine.save_watchlist(watchlist)
            st.rerun()

    st.markdown("---")
    if st.button("⚡ 一键增量同步全部标的 (日/1H/5M)", use_container_width=True):
        with st.spinner("正在拉取深度历史数据..."):
            for item in watchlist:
                hub_engine.fetch_deep_history(item['code'], "DAY", 730)
                hub_engine.fetch_deep_history(item['code'], "1H", 365)
                hub_engine.fetch_deep_history(item['code'], "5M", 30)
        st.success("全部数据已增量归档！")

# 顶栏全局状态
now_ny = datetime.datetime.now(tz_ny).strftime("%Y-%m-%d %H:%M:%S ET")
st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #30363d; padding-bottom:8px; margin-bottom:12px;">
    <span style="font-size:18px; font-weight:bold; color:#58a6ff;">🏛️ Market Data Hub · 统一市场数据中心</span>
    <span style="font-size:13px; color:#8b949e; font-family:monospace;">美东时间: <b style="color:#e6edf3;">{now_ny}</b> | 状态: <span class="status-tag tag-green">🟢 OpenD 监听就绪</span></span>
</div>
""", unsafe_allow_html=True)

# 区域一：可折叠数据总表 (局部心跳 3 秒刷新)
@st.fragment(run_every=3.0)
def render_market_table():
    codes = [a['code'] for a in watchlist]
    snap_df = hub_engine.get_realtime_snapshot(codes) if codes else None
    
    snap_map = {}
    if snap_df is not None and not snap_df.empty:
        for _, r in snap_df.iterrows():
            snap_map[r['code']] = r

    categories = sorted(list(set(a.get("category", "默认板块") for a in watchlist)))

    for cat in categories:
        cat_assets = [a for a in watchlist if a.get("category") == cat]
        with st.expander(f"📁 {cat} (共 {len(cat_assets)} 档)", expanded=True):
            rows = []
            for item in cat_assets:
                code = item['code']
                snap = snap_map.get(code, None)
                
                last_price = f"${snap['last_price']:,.2f}" if snap is not None and 'last_price' in snap else "--"
                change_rate = f"{snap['change_rate']:.2f}%" if snap is not None and 'change_rate' in snap else "0.00%"
                high_p = f"${snap['high_price']:,.2f}" if snap is not None and 'high_price' in snap else "--"
                low_p = f"${snap['low_price']:,.2f}" if snap is not None and 'low_price' in snap else "--"
                vol = f"{int(snap['volume']):,}" if snap is not None and 'volume' in snap else "--"

                # 本地 CSV 归档行数
                clean_name = code.replace(".", "_")
                csv_day = os.path.join(DATA_DIR, f"{clean_name}_DAY.csv")
                csv_1h = os.path.join(DATA_DIR, f"{clean_name}_1H.csv")
                csv_5m = os.path.join(DATA_DIR, f"{clean_name}_5M.csv")

                cnt_day = len(pd.read_csv(csv_day)) if os.path.exists(csv_day) else 0
                cnt_1h = len(pd.read_csv(csv_1h)) if os.path.exists(csv_1h) else 0
                cnt_5m = len(pd.read_csv(csv_5m)) if os.path.exists(csv_5m) else 0

                rows.append({
                    "标的代码": code,
                    "标的名称": item['name'],
                    "最新现价": last_price,
                    "涨跌幅": change_rate,
                    "日最高": high_p,
                    "日最低": low_p,
                    "成交量": vol,
                    "2年日线归档": f"{cnt_day} 根",
                    "1年1H归档": f"{cnt_1h} 根",
                    "30天5M归档": f"{cnt_5m} 根",
                    "通道状态": "🟢 正常"
                })

            if rows:
                df_table = pd.DataFrame(rows)
                st.dataframe(df_table, use_container_width=True, hide_index=True)

render_market_table()

st.markdown("---")

# 区域二：独立图表穿透与分析插件挂载区
st.subheader("📊 标的多周期走势穿透 (Chart View Plugin)")

col_sel1, col_sel2, col_sel3 = st.columns([2, 1, 1])
with col_sel1:
    code_options = [a['code'] for a in watchlist]
    selected_code = st.selectbox("选择要查看的标的", code_options, index=0 if code_options else 0)
with col_sel2:
    selected_ktype = st.selectbox("K线周期", ["5M", "1H", "DAY"], index=0)
with col_sel3:
    selected_count = st.slider("展示根数", min_value=30, max_value=200, value=60, step=10)

if selected_code:
    chart_plugin.render_chart(code=selected_code, ktype=selected_ktype, bar_count=selected_count)
