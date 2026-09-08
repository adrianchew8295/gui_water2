# 文件名: macro_radar_plugin.py
# 职责: 渲染 12 档核心美股宏观雷达、买卖战区大表与标的管理抽屉

import streamlit as st
import pandas as pd
from data_engine import hub_engine
from radar_engine import compute_radar_metrics
import chart_view_plugin

def render_macro_radar_view(assets):
    """渲染 12 档核心宏观雷达主模块"""
    tab_list, tab_chart, tab_manage = st.tabs([
        "📊 12档宏观雷达总表", 
        "📈 标的多周期图表穿透", 
        "🗂️ 标的池管理 (增删)"
    ])

    # ---------------------------------------------------------
    # Sub Tab 1: 12 档折叠总表
    # ---------------------------------------------------------
    with tab_list:
        st.markdown("#### 🌐 12 档核心美股宏观雷达与攻防战区")
        
        # 批量获取 Live 快照
        codes = [a['code'] for a in assets]
        snap_df = hub_engine.get_realtime_snapshot(codes)
        snap_dict = {}
        if snap_df is not None and not snap_df.empty and 'code' in snap_df.columns:
            for _, r in snap_df.iterrows():
                snap_dict[r['code']] = {
                    'price': float(r.get('last_price', 0.0) or 0.0),
                    'change': float(r.get('change_rate', 0.0) or 0.0)
                }

        # 提取 QQQ 涨跌作为强弱对照基准
        qqq_chg = snap_dict.get("US.QQQ", {}).get("change", 0.0)

        # 分类分组渲染
        categories = sorted(list(set([a.get('category', '📦 其他标的') for a in assets])))
        
        for cat in categories:
            cat_assets = [a for a in assets if a.get('category') == cat]
            with st.expander(f"📁 {cat} (共 {len(cat_assets)} 档)", expanded=True):
                rows = []
                for item in cat_assets:
                    c = item['code']
                    cur_info = snap_dict.get(c, {'price': 0.0, 'change': 0.0})
                    cur_p = cur_info['price']
                    cur_chg = cur_info['change']
                    spread_qqq = cur_chg - qqq_chg

                    # 计算宏观战区指标
                    m = compute_radar_metrics(c, live_price=cur_p)

                    rows.append({
                        "标的代码": c,
                        "标的名称": item['name'],
                        "最新现价": f"${cur_p:,.2f}" if cur_p > 0 else "--",
                        "日内涨跌": f"{cur_chg:+.2f}%",
                        "相对QQQ强弱": f"{spread_qqq:+.2f}%" if c != "US.QQQ" else "⚓ 基准",
                        "20日量比": f"{m['vol_ratio']}x",
                        "买入地板 (RBS)": m['floor_zone'],
                        "阻力天花板 (SBR)": m['ceiling_zone'],
                        "宏观方向": m['trend_bias'],
                        "操作建议": m['action_hint']
                    })

                if rows:
                    df_cat = pd.DataFrame(rows)
                    st.dataframe(df_cat, use_container_width=True, hide_index=True)

    # ---------------------------------------------------------
    # Sub Tab 2: 标的多周期图表穿透
    # ---------------------------------------------------------
    with tab_chart:
        chart_view_plugin.render_chart_view(assets)

    # ---------------------------------------------------------
    # Sub Tab 3: 标的池动态增删
    # ---------------------------------------------------------
    with tab_manage:
        st.markdown("#### ⚙️ 自选资产池管理")
        c1, c2, c3 = st.columns([3, 3, 2])
        with c1:
            new_code = st.text_input("标的代码 (例: US.TSLA)", key="manage_add_code").upper().strip()
        with c2:
            new_name = st.text_input("标的名称 (例: 特斯拉)", key="manage_add_name").strip()
        with c3:
            new_cat = st.selectbox("分类板块", ["🚀 核心指数", "🏛️ 科技巨头", "💾 先锋龙头", "🪙 加密资产", "📦 其他标的"], key="manage_add_cat")

        if st.button("➕ 确认添加到监控池", use_container_width=True):
            if new_code and new_name:
                if not any(a['code'] == new_code for a in assets):
                    assets.append({
                        "code": new_code, 
                        "name": new_name, 
                        "category": new_cat, 
                        "type": "CRYPTO" if "CC." in new_code else "STOCK"
                    })
                    hub_engine.save_watchlist(assets)
                    st.success(f"已成功添加 {new_code}")
                    st.rerun()
                else:
                    st.warning("该标的代码已存在。")

        st.markdown("---")
        st.markdown("##### 当前已加载标的清单")
        for i, item in enumerate(assets):
            col_t, col_del = st.columns([6, 1])
            col_t.write(f"**{item['code']}** - {item['name']} ({item.get('category', '默认')})")
            if col_del.button("🗑️ 移除", key=f"del_item_{i}"):
                assets.pop(i)
                hub_engine.save_watchlist(assets)
                st.rerun()
