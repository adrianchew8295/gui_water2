# 文件名: portfolio_manager_plugin.py
# 职责: 渲染美股真实持仓明细 (Securities) 与资金流动性分析 (Analysis)

import streamlit as st
import pandas as pd
from data_engine import get_moomoo_real_portfolio

def render_portfolio_securities():
    """Sub Tab 1: 实盘美股持仓列表 (自动过滤非美股)"""
    fund_summary, pos_df, msg = get_moomoo_real_portfolio()
    
    if fund_summary is None:
        st.error(f"❌ 无法读取持仓: {msg}")
        return
        
    if pos_df is None or pos_df.empty:
        st.info("⚪ 当前账户无持仓标的（处于空仓待机状态）。")
        return

    # 过滤美股标的 (US.*)
    pos_df = pos_df[pos_df['code'].astype(str).str.startswith('US.')].copy()
    
    if pos_df.empty:
        st.info("⚪ 当前暂无美股持仓标的。")
        return

    display_cols = {
        'code': '标的代码',
        'stock_name': '证券名称',
        'qty': '持仓股数',
        'can_sell_qty': '可卖股数',
        'cost_price': '成本均价',
        'nominal_price': '最新市价',
        'market_val': '当前市值 (USD)',
        'pl_val': '浮动盈亏 (USD)',
        'pl_ratio': '盈亏比例 (%)'
    }
    
    valid_cols = [c for c in display_cols.keys() if c in pos_df.columns]
    df_show = pos_df[valid_cols].copy()
    df_show.rename(columns=display_cols, inplace=True)
    
    st.dataframe(
        df_show.style.format({
            '成本均价': '${:,.2f}',
            '最新市价': '${:,.2f}',
            '当前市值 (USD)': '${:,.2f}',
            '浮动盈亏 (USD)': '${:+,.2f}',
            '盈亏比例 (%)': '{:+.2f}%'
        }),
        use_container_width=True,
        hide_index=True
    )

def render_portfolio_analysis():
    """Sub Tab 2: 资产净值与现金流动性分析"""
    fund_summary, pos_df, msg = get_moomoo_real_portfolio()
    
    if fund_summary is None:
        st.error(f"❌ 无法读取资产概况: {msg}")
        return

    nav = fund_summary.get('total_assets', 0.0)
    cash = fund_summary.get('cash', 0.0)
    mkt_val = fund_summary.get('market_val', 0.0)
    upl = fund_summary.get('unrealized_pl', 0.0)
    cash_ratio = (cash / nav * 100) if nav > 0 else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 账户总净值 (NAV)", f"${nav:,.2f} USD")
    c2.metric("💵 可用流动现金", f"${cash:,.2f} USD", f"{cash_ratio:.1f}% 现金占比")
    c3.metric("📊 证券总市值", f"${mkt_val:,.2f} USD")
    c4.metric("📈 累计浮动盈亏", f"${upl:+,.2f} USD")

    st.markdown("---")
    st.markdown("#### 🛡️ 组合健康度诊断")
    if cash_ratio < 15.0:
        st.warning("⚠️ 现金流动性低于 15%，建议控制单笔开仓头寸，保持安全冗余。")
    else:
        st.success("🟢 现金水位充裕，具备良好的回调承接与防守空间。")
