# 文件名: app.py
# 功能: 统一主入口 · 支持【标的与数据中枢】与【Moomoo 真实持仓/资金罗盘】顶层切换

import streamlit as st
from data_engine import hub_engine
import chart_view_plugin

# 页面基础配置
st.set_page_config(
    page_title="Market Data Hub & Portfolio", 
    page_icon="🌊", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# 顶部主导航 Tab 栏
main_tab1, main_tab2 = st.tabs([
    "📊 标的与数据中枢 (Market Data Hub)",
    "💼 个人真实持仓与资金罗盘 (Moomoo Portfolio)"
])

# -------------------------------------------------------------
# TAB 1: 标的与多周期数据管理中枢
# -------------------------------------------------------------
with main_tab1:
    assets = hub_engine.load_watchlist()
    
    # 侧边栏：标的管理
    with st.sidebar:
        st.markdown("### ⚙️ 标的管理中枢")
        with st.expander("➕ 添加新标的"):
            new_code = st.text_input("代码 (例: US.TSLA / CC.ETHUSD)", key="add_code").upper().strip()
            new_name = st.text_input("标的名称 (例: 特斯拉)", key="add_name").strip()
            new_cat = st.selectbox("分类归属", ["🚀 核心指数", "🏛️ 科技巨头", "🪙 加密资产", "📦 其他标的"], key="add_cat")
            new_type = "CRYPTO" if "CC." in new_code else "STOCK"
            
            if st.button("确认添加标的", use_container_width=True):
                if new_code and new_name:
                    if not any(a['code'] == new_code for a in assets):
                        assets.append({"code": new_code, "name": new_name, "category": new_cat, "type": new_type})
                        hub_engine.save_watchlist(assets)
                        st.success(f"已添加 {new_code}")
                        st.rerun()
                    else:
                        st.warning("该标的代码已存在")

        st.markdown("---")
        st.markdown("#### 标的清单与操作")
        for i, item in enumerate(assets):
            c1, c2 = st.columns([4, 1])
            c1.markdown(f"**{item['code']}** ({item['name']})")
            if c2.button("🗑️", key=f"del_{i}"):
                assets.pop(i)
                hub_engine.save_watchlist(assets)
                st.rerun()

    # 主区域：分组展示行情表格与归档状态
    categories = list(set([a.get('category', '📦 其他标的') for a in assets]))
    for cat in sorted(categories):
        cat_items = [a for a in assets if a.get('category') == cat]
        with st.expander(f"📁 {cat} (共 {len(cat_items)} 档)", expanded=True):
            # 获取实时快照
            codes = [a['code'] for a in cat_items]
            snap_df = hub_engine.get_realtime_snapshot(codes)
            
            table_data = []
            for item in cat_items:
                c = item['code']
                cur_p, chg = "--", "--"
                if snap_df is not None and not snap_df.empty and 'code' in snap_df.columns:
                    match = snap_df[snap_df['code'] == c]
                    if not match.empty:
                        cur_p = f"${float(match.iloc[0].get('last_price', 0.0)):,.2f}"
                        chg = f"{float(match.iloc[0].get('change_rate', 0.0)):+.2f}%"
                
                table_data.append({
                    "标的代码": c,
                    "标的名称": item['name'],
                    "最新现价": cur_p,
                    "涨跌幅": chg,
                    "通道状态": "🟢 正常"
                })
            
            if table_data:
                st.dataframe(table_data, use_container_width=True, hide_index=True)

    st.markdown("---")
    # 多周期走势图表穿透
    chart_view_plugin.render_chart_view(assets)


# -------------------------------------------------------------
# TAB 2: Moomoo 真实账户资金与持仓罗盘
# -------------------------------------------------------------
with main_tab2:
    try:
        from portfolio_manager_plugin import render_portfolio_expansion
        render_portfolio_expansion()
    except Exception as e:
        st.error(f"加载持仓插件失败: {e}")
