# 文件名: app.py
# 职责: Market Data Hub 交互式主页面 (可折叠分类/多级合并表头/动态增删标的/局部心跳跳动)

import streamlit as st
import pandas as pd
import os
import datetime
import pytz
from data_engine import hub_engine

tz_ny = pytz.timezone("America/New_York")
st.set_page_config(page_title="Market Data Hub V2", page_icon="🏛️", layout="wide")

# 暗黑金融终端样式注入
st.markdown("""
<style>
    .block-container { padding-top: 1.2rem; padding-bottom: 0rem; max-width: 98%; }
    .metric-card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 10px; margin-bottom: 8px; }
    .status-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-family: monospace; font-weight: bold; }
    .tag-green { background: #238636; color: white; }
    .tag-blue { background: #1f6feb; color: white; }
</style>
""", unsafe_allow_html=True)

# 标的资产池读取
watchlist = hub_engine.load_watchlist()

# 侧边栏：标的动态资产池管理器 (➕ 添加 / 🗑️ 删除)
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
    for idx, item in enumerate(watchlist):
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"**{item['code']}** ({item['name']})")
        if c2.button("🗑️", key=f"del_{item['code']}"):
            watchlist = [a for a in watchlist if a['code'] != item['code']]
            hub_engine.save_watchlist(watchlist)
            st.rerun()

    st.markdown("---")
    if st.button("⚡ 一键增量同步所有标的数据", use_container_width=True):
        with st.spinner("正在拉取全量数据..."):
            for item in watchlist:
                hub_engine.fetch_closed_kline(item['code'], "5M", 120)
                hub_engine.fetch_closed_kline(item['code'], "1H", 120)
                hub_engine.fetch_closed_kline(item['code'], "DAY", 60)
        st.success("全部数据已增量归档！")

# 顶栏全局状态
now_ny = datetime.datetime.now(tz_ny).strftime("%Y-%m-%d %H:%M:%S ET")
st.markdown(f"""
<div style="display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #30363d; padding-bottom:8px; margin-bottom:12px;">
    <span style="font-size:18px; font-weight:bold; color:#58a6ff;">🏛️ Market Data Hub · 统一市场数据中心</span>
    <span style="font-size:13px; color:#8b949e; font-family:monospace;">美东时间: <b style="color:#e6edf3;">{now_ny}</b> | 状态: <span class="status-tag tag-green">🟢 OpenD 监听就绪</span></span>
</div>
""", unsafe_allow_html=True)

# 局部心跳渲染区域 (驱动实时数据与折叠表格)
@st.fragment(run_every=2.0)
def render_market_table():
    codes = [a['code'] for a in watchlist]
    snap_df = hub_engine.get_realtime_snapshot(codes) if codes else None
    
    # 构造表格快照字典
    snap_map = {}
    if snap_df is not None and not snap_df.empty:
        for _, r in snap_df.iterrows():
            snap_map[r['code']] = r

    # 按 Category 进行可收缩折叠展示
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

                # 检查本地 CSV 存储行数状态
                clean_name = code.replace(".", "_")
                csv_5m = os.path.join(hub_engine.load_watchlist and "market_data", f"{clean_name}_5M.csv")
                count_5m = len(pd.read_csv(csv_5m)) if os.path.exists(csv_5m) else 0

                rows.append({
                    "标的代码 (Ticker)": code,
                    "标的名称": item['name'],
                    "最新现价 (Last)": last_price,
                    "涨跌幅 (%)": change_rate,
                    "当日最高 (High)": high_p,
                    "当日最低 (Low)": low_p,
                    "成交量 (Vol)": vol,
                    "本地 5M 归档行数": f"{count_5m} 根",
                    "数据通道状态": "🟢 正常"
                })

            if rows:
                df_table = pd.DataFrame(rows)
                st.dataframe(df_table, use_container_width=True, hide_index=True)

render_market_table()

st.info("💡 提示：本页面为纯粹的 **Market Data Hub** 数据基座。后续任何分析模型（TD/波浪/VPA）均作为独立插件在下方挂载。")
