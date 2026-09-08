# 文件名: ai_audit_plugin.py
# 职责: 自动抓取当前实盘 NAV、现金占比、美股持仓与 QQQ 宏观战区，生成标准 AI 风控日誌

import streamlit as st
import datetime
import pytz
from data_engine import get_moomoo_real_portfolio, hub_engine
from radar_engine import compute_radar_metrics

tz_ny = pytz.timezone("America/New_York")

def generate_audit_prompt():
    """聚合实盘与市场数据，生成标准化 Markdown 格式 Prompt"""
    now_str = datetime.datetime.now(tz_ny).strftime("%Y-%m-%d %H:%M:%S ET")
    
    # 1. 获取资金与实盘持仓
    fund_summary, pos_df, _ = get_moomoo_real_portfolio()
    nav = fund_summary.get('total_assets', 0.0) if fund_summary else 0.0
    cash = fund_summary.get('cash', 0.0) if fund_summary else 0.0
    cash_ratio = (cash / nav * 100) if nav > 0 else 0.0
    
    pos_lines = []
    if pos_df is not None and not pos_df.empty:
        us_pos = pos_df[pos_df['code'].astype(str).str.startswith('US.')]
        for _, r in us_pos.iterrows():
            code = r.get('code', '--')
            qty = r.get('qty', 0)
            cost = r.get('cost_price', 0.0)
            cur_p = r.get('nominal_price', 0.0)
            pl_ratio = r.get('pl_ratio', 0.0)
            pos_lines.append(f"  - 标的: {code} | 持股: {qty} | 成本: ${cost:,.2f} | 现价: ${cur_p:,.2f} | 盈亏: {pl_ratio:+.2f}%")
    
    pos_text = "\n".join(pos_lines) if pos_lines else "  - 当前无美股实盘持仓 (空仓待机)"

    # 2. 获取 QQQ 战区状态
    snap = hub_engine.get_realtime_snapshot(["US.QQQ"])
    qqq_p = float(snap.iloc[0].get('last_price', 0.0)) if (snap is not None and not snap.empty) else 0.0
    qqq_metrics = compute_radar_metrics("US.QQQ", live_price=qqq_p)

    prompt = f"""### 🛡️ 【交易系统实盘审计与风控诊断请求】
**生成时间**: {now_str}

#### 1. 账户资产与流动性状态
- 账户总净值 (NAV): ${nav:,.2f} USD
- 可用现金 (Cash): ${cash:,.2f} USD (占比: {cash_ratio:.1f}%)
- 流动性状态: {"🟢 充裕" if cash_ratio >= 15 else "⚠️ 偏低 (需警惕敞口过大)"}

#### 2. 当前实盘持仓明细
{pos_text}

#### 3. 市场大盘中枢 (US.QQQ 纳指) 战区基准
- 最新现价: ${qqq_p:,.2f}
- Trend Bias: {qqq_metrics['trend_bias']}
- 今日买入地板 (RBS/PDL): {qqq_metrics['floor_zone']}
- 今日阻力天花板 (SBR/PDH): {qqq_metrics['ceiling_zone']}
- 1H EMA20 防守中枢: ${qqq_metrics['ema20_1h']:,.2f}
- 操作状态提示: {qqq_metrics['action_hint']}

---
#### 4. 请 AI 审计官执行以下诊断指令：
1. **仓位安全性评估**：根据当前现金占比 ({cash_ratio:.1f}%) 与持仓盈亏，评估是否存在过度敞口或重仓单一标的的风险。
2. **战区匹配度审核**：结合 QQQ 纳指大盘当前处于的攻防战区与 Trend Bias，判断当前是适合继续持有、逢高止盈，还是在 RBS 地板伏击加仓？
3. **冷血风控建议**：给出明确的操作边界与强制防守线，指出最薄弱环节。
"""
    return prompt

def render_ai_audit_view():
    """渲染 AI 审计页面与一键复制功能"""
    st.markdown("#### 🤖 AI 组合风控与攻防审计日誌 (Audit Log)")
    st.caption("基于你当前账户真实持仓资金比例与 QQQ 大盘攻防阶梯，一键生成结构化诊断日誌。")

    audit_text = generate_audit_prompt()

    c1, c2 = st.columns([8, 2])
    with c2:
        if st.button("🔄 重新生成日誌", use_container_width=True):
            st.rerun()

    # 展示可一键复制的代码框
    st.code(audit_text, language="markdown")
