# 文件名: portfolio_manager_plugin.py
# 功能: 直连 Moomoo OpenD 真实账户资金概况与持仓监控表格

import streamlit as st
import pandas as pd
from data_engine import get_moomoo_real_portfolio

def render_portfolio_expansion(price_dict=None):
    """
    渲染 Moomoo 真实账户持仓与资金罗盘
    """
    # 1. 顶部操作栏
    c_btn1, c_btn2 = st.columns([2, 8])
    with c_btn1:
        if st.button("🔄 刷新 Moomoo 账户真实数据", use_container_width=True):
            st.rerun()

    # 2. 从 data_engine 获取真实账户资金与持仓
    fund_summary, pos_df, msg = get_moomoo_real_portfolio()

    if fund_summary is None:
        st.error(f"❌ 无法连接 Moomoo OpenD: {msg}")
        st.info("💡 请确认本地 Moomoo OpenD 客户端已登录且监听 11111 端口。")
        return

    # 3. 核心资产指标看板 (NAV / Cash / Market Value / PnL)
    nav = fund_summary.get('total_assets', 0.0)
    cash = fund_summary.get('cash', 0.0)
    mkt_val = fund_summary.get('market_val', 0.0)
    upl = fund_summary.get('unrealized_pl', 0.0)
    acc_id = fund_summary.get('acc_id', '--')
    env_str = fund_summary.get('trd_env', 'REAL')

    # 计算现金占比与健康度
    cash_ratio = (cash / nav * 100) if nav > 0 else 0.0

    st.markdown(f"""
    <div style="background: rgba(14, 20, 32, 0.85); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 10px 14px; margin-bottom: 12px; font-family: monospace;">
        <span style="color: #58a6ff; font-weight: bold;">👤 账户 ID: {acc_id}</span> | 
        <span style="color: #00E676; font-weight: bold;">环境: {env_str}</span> | 
        <span style="color: #94A3B8;">现金仓位比: <b>{cash_ratio:.1f}%</b> ({'🟢 充裕' if cash_ratio >= 20 else '🟡 偏低'})</span>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("💰 账户总净值 (NAV)", f"${nav:,.2f} USD")
    m2.metric("💵 可用现金 (Cash)", f"${cash:,.2f} USD", f"{cash_ratio:.1f}% 现金占比")
    m3.metric("📊 证券总市值 (Stock)", f"${mkt_val:,.2f} USD")
    m4.metric(
        "📈 累计浮动盈亏", 
        f"${upl:+,.2f} USD", 
        delta=f"{(upl / (nav - upl) * 100):+.2f}%" if (nav - upl) > 0 else None
    )

    st.markdown("---")
    st.markdown("#### 📊 当前真实持仓与浮盈明细 (Position List)")

    # 4. 持仓明细表格
    if pos_df is None or pos_df.empty:
        st.info("⚪ 当前账户暂无持仓股票或期权（当前处于空仓保本金状态）。")
    else:
        # 整理展示列
        display_cols = {
            'code': '标的代码',
            'stock_name': '证券名称',
            'qty': '持仓股数',
            'can_sell_qty': '可卖股数',
            'cost_price': '持仓成本',
            'nominal_price': '最新市价',
            'market_val': '当前市值 (USD)',
            'pl_val': '浮动盈亏 (USD)',
            'pl_ratio': '盈亏比例 (%)'
        }
        
        # 过滤存在的列
        valid_cols = [c for c in display_cols.keys() if c in pos_df.columns]
        df_show = pos_df[valid_cols].copy()
        
        # 数值类型安全转换
        for num_col in ['cost_price', 'nominal_price', 'market_val', 'pl_val', 'pl_ratio']:
            if num_col in df_show.columns:
                df_show[num_col] = pd.to_numeric(df_show[num_col], errors='coerce').fillna(0.0)

        # 重命名表头
        df_show.rename(columns=display_cols, inplace=True)

        # 样式渲染：盈利绿色、亏损红色
        def style_positions(row):
            styles = [""] * len(row)
            if '浮动盈亏 (USD)' in df_show.columns:
                p_idx = df_show.columns.get_loc('浮动盈亏 (USD)')
                val = row['浮动盈亏 (USD)']
                if val > 0:
                    styles[p_idx] = "color: #00E676; font-weight: bold;"
                elif val < 0:
                    styles[p_idx] = "color: #FF5252; font-weight: bold;"
            if '盈亏比例 (%)' in df_show.columns:
                r_idx = df_show.columns.get_loc('盈亏比例 (%)')
                val_r = row['盈亏比例 (%)']
                if val_r > 0:
                    styles[r_idx] = "color: #00E676; font-weight: bold;"
                elif val_r < 0:
                    styles[r_idx] = "color: #FF5252; font-weight: bold;"
            return styles

        st.dataframe(
            df_show.style.apply(style_positions, axis=1).format({
                '持仓成本': '${:,.2f}',
                '最新市价': '${:,.2f}',
                '当前市值 (USD)': '${:,.2f}',
                '浮动盈亏 (USD)': '${:+,.2f}',
                '盈亏比例 (%)': '{:+.2f}%'
            }),
            use_container_width=True,
            hide_index=True
        )