# 文件名: chart_renderer.py
# 功能: 渲染高對比度專業圖表與宏觀通道數據解析 HUD 卡片

import streamlit as st
import plotly.graph_objects as go
from trendline_engine import compute_advanced_channel

def render_channel_cockpit_chart(df: pd.DataFrame, ticker: str = "US.QQQ"):
    if df is None or df.empty:
        st.error("❌ 數據檔案為空，無法繪製通道圖")
        return

    # 1. 執行幾何計算
    analysis = compute_advanced_channel(df, macro_window=10)

    if analysis["status"] != "success":
        st.warning(f"⚠️ 通道分析提示: {analysis.get('msg', '未知狀態')}")
        return

    hud = analysis["hud_report"]
    chan = analysis["macro_channel"]
    d_sum = analysis["data_summary"]

    # 2. 渲染頂部「數據解析與幾何對照框 (HUD Box)」
    st.markdown(
        f"""
        <div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 16px; margin-bottom: 15px; font-family: monospace;">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #21262d; padding-bottom: 8px; margin-bottom: 12px;">
                <span style="font-size: 16px; font-weight: bold; color: #58a6ff;">📊 {ticker} 宏觀通道技術分析報告</span>
                <span style="background: #1f293d; color: #79c0ff; padding: 3px 8px; border-radius: 4px; font-size: 12px;">{hud['period_desc']}</span>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                <div>
                    <div style="color: #ff7b72; font-weight: bold; margin-bottom: 4px;">🔴 阻力天花板 (Resistance Trendline)</div>
                    <div style="color: #c9d1d9; font-size: 13px; line-height: 1.5;">• {hud['res_desc']}</div>
                    <div style="color: #8b949e; font-size: 12px; margin-top: 4px;">🎯 上軌向上突破第 ① 目標: <b style="color: #56d364;">${hud['target_bull']}</b></div>
                </div>
                <div>
                    <div style="color: #56d364; font-weight: bold; margin-bottom: 4px;">🟢 支撐地板 (Support Trendline)</div>
                    <div style="color: #c9d1d9; font-size: 13px; line-height: 1.5;">• {hud['sup_desc']}</div>
                    <div style="color: #8b949e; font-size: 12px; margin-top: 4px;">🛡️ 下軌向下跌破防守目標: <b style="color: #ff7b72;">${hud['target_bear']}</b></div>
                </div>
            </div>
            <div style="margin-top: 10px; padding-top: 8px; border-top: 1px dashed #21262d; display: flex; justify-content: space-between; font-size: 12px; color: #8b949e;">
                <span>形態判定: <b style="color: #f0f6fc;">{hud['title']}</b></span>
                <span>通道垂直高度: <b style="color: #f0f6fc;">${chan['channel_height']:.2f} USD</b></span>
                <span>最新收盤現價: <b style="color: #58a6ff;">${d_sum['latest_close']:.2f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 3. 繪製 Plotly 大級別走勢圖
    fig = go.Figure()

    # K 線主體
    fig.add_trace(go.Candlestick(
        x=df['time_clean'],
        open=df['open'], high=df['high'],
        low=df['low'], close=df['close'],
        name="K線",
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ))

    # 阻力趨勢線 (紅色長射線)
    res_x = [p["time"] for p in chan["res_line"]]
    res_y = [p["value"] for p in chan["res_line"]]
    fig.add_trace(go.Scatter(
        x=res_x, y=res_y,
        mode='lines+markers',
        line=dict(color='#ff5252', width=2, dash='solid'),
        marker=dict(size=4),
        name="阻力趨勢線"
    ))

    # 支撐趨勢線 (綠色長射線)
    sup_x = [p["time"] for p in chan["sup_line"]]
    sup_y = [p["value"] for p in chan["sup_line"]]
    fig.add_trace(go.Scatter(
        x=sup_x, y=sup_y,
        mode='lines+markers',
        line=dict(color='#00e676', width=2, dash='solid'),
        marker=dict(size=4),
        name="支撐趨勢線"
    ))

    # 標註關鍵極值點 P1 與 P2 錨點文字
    h1, h2 = chan["anchor_h1"], chan["anchor_h2"]
    l1, l2 = chan["anchor_l1"], chan["anchor_l2"]
    
    fig.add_annotation(x=h1["time"], y=h1["price"], text=f"峰1: ${h1['price']:.2f}", showarrow=True, arrowhead=1, yshift=10, font=dict(color="#ff5252", size=11))
    fig.add_annotation(x=h2["time"], y=h2["price"], text=f"峰2: ${h2['price']:.2f}", showarrow=True, arrowhead=1, yshift=10, font=dict(color="#ff5252", size=11))
    fig.add_annotation(x=l1["time"], y=l1["price"], text=f"谷1: ${l1['price']:.2f}", showarrow=True, arrowhead=1, yshift=-10, font=dict(color="#00e676", size=11))
    fig.add_annotation(x=l2["time"], y=l2["price"], text=f"谷2: ${l2['price']:.2f}", showarrow=True, arrowhead=1, yshift=-10, font=dict(color="#00e676", size=11))

    fig.update_layout(
        template="plotly_dark",
        height=580,
        margin=dict(l=20, r=20, t=10, b=20),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)
