# 文件名: macro_radar_plugin.py
# 職責: 渲染專業日線幾何圖表、繪圖圖層獨立 ON/OFF 開關、AI Markdown 輸出框

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
from macro_radar_engine import compute_radar_channel_and_markdown

def render_macro_radar_view(df: pd.DataFrame, ticker: str = "US.NVDA"):
    if df is None or df.empty:
        st.warning("⚠️ 當前標的暫無歷史日線數據")
        return

    # 1. 執行幾何計算
    data = compute_radar_channel_and_markdown(df, ticker=ticker)
    if data["status"] != "success":
        st.error(f"❌ 計算失敗: {data.get('msg')}")
        return

    chan = data["macro_channel"]
    curr_p = data["curr_price"]
    maj_sup = data["major_support"]
    rec_res = data["recent_res"]
    rec_sup = data["recent_sup"]

    # 2. 頂部 HUD 狀態卡 (黑底金屬風)
    st.markdown(
        f"""
        <div style="background-color: #0e1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; font-family: monospace;">
            <span style="color: #58a6ff; font-weight: bold; font-size: 15px;">📊 {ticker} · 純日線技術幾何通道 (John J. Murphy 體系)</span><br>
            <div style="margin-top: 6px; display: flex; gap: 20px; font-size: 13px; color: #c9d1d9;">
                <span>現價: <b style="color: #79c0ff;">${curr_p:.2f}</b></span>
                <span>即時阻力 (RES): <b style="color: #ff7b72;">${rec_res:.2f}</b></span>
                <span>即時支撐 (SUP): <b style="color: #56d364;">${rec_sup:.2f}</b></span>
                <span>⭐ 當前波段重大支撐: <b style="color: #00e5ff;">${maj_sup:.2f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 3. 繪圖圖層 ON/OFF 開關控制列 (人性化操作)
    st.markdown("##### 🎛️ 圖表繪圖圖層控制 (Drawing Toggles)")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        show_channel = st.checkbox("📐 趨勢通道 (Channel)", value=True)
    with c2:
        show_sr = st.checkbox("🧱 即時 S/R 水平線", value=True)
    with c3:
        show_major = st.checkbox("⭐ 重大支撐 (Major Sup)", value=True)
    with c4:
        show_pivots = st.checkbox("🏷️ 極值點錨點標籤", value=True)
    with c5:
        zoom_recent = st.checkbox("🔍 聚焦最近 120 根 K 線", value=True)

    # 4. 數據視窗剪裁（若勾選聚焦近 120 根，Y 軸將呈現最舒服的比例）
    plot_df = df.iloc[-120:].copy() if (zoom_recent and len(df) > 120) else df.copy()

    # 5. 繪製 Plotly 圖表
    fig = go.Figure()

    # K 線主體
    fig.add_trace(go.Candlestick(
        x=plot_df['time_clean'],
        open=plot_df['open'], high=plot_df['high'],
        low=plot_df['low'], close=plot_df['close'],
        name="日K線",
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ))

    # [開關 1] 繪製趨勢通道線
    if show_channel and chan:
        res_x = [p["time"] for p in chan["res_line"] if p["time"] in plot_df['time_clean'].values]
        res_y = [p["value"] for p in chan["res_line"] if p["time"] in plot_df['time_clean'].values]
        sup_x = [p["time"] for p in chan["sup_line"] if p["time"] in plot_df['time_clean'].values]
        sup_y = [p["value"] for p in chan["sup_line"] if p["time"] in plot_df['time_clean'].values]

        if res_x:
            fig.add_trace(go.Scatter(x=res_x, y=res_y, mode='lines', line=dict(color='#ffd600', width=2, dash='dash'), name="通道阻力 (Upper)"))
        if sup_x:
            fig.add_trace(go.Scatter(x=sup_x, y=sup_y, mode='lines', line=dict(color='#00e676', width=2, dash='solid'), name="通道支撐 (Lower)"))

    # [開關 2] 繪製即時 S/R
    if show_sr:
        fig.add_hline(y=rec_res, line_dash="dot", line_color="#ff5252", annotation_text=f"RES: ${rec_res:.2f}", annotation_position="top right")
        fig.add_hline(y=rec_sup, line_dash="dot", line_color="#00e676", annotation_text=f"SUP: ${rec_sup:.2f}", annotation_position="bottom right")

    # [開關 3] 繪製當前大波段 Major Support
    if show_major:
        fig.add_hline(y=maj_sup, line_dash="solid", line_width=2, line_color="#00e5ff", annotation_text=f"⭐ MAJOR SUPPORT: ${maj_sup:.2f}", annotation_position="bottom right")

    # [開關 4] 標記錨點極值標籤
    if show_pivots and chan:
        for pt, label, color in [(chan["h1"], "峰1", "#ff5252"), (chan["h2"], "峰2", "#ff5252"), (chan["l1"], "谷1", "#00e676"), (chan["l2"], "谷2", "#00e676")]:
            if pt and pt["time"] in plot_df['time_clean'].values:
                fig.add_annotation(x=pt["time"], y=pt["price"], text=f"{label}: ${pt['price']:.2f}", showarrow=True, arrowhead=2, yshift=10 if "峰" in label else -10, font=dict(color=color, size=11))

    fig.update_layout(
        template="plotly_dark",
        height=540,
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)

    # 6. 專屬 AI 分析 Markdown 導出代碼框 (一鍵複製)
    st.divider()
    st.markdown("#### 🤖 AI 策略軍師專用診斷 Markdown 日誌 (可直接複製發送給 AI)")
    st.caption("點擊下方右上角按鈕即可直接複製完整技術幾何數據，貼入 ChatGPT / Claude / Gemini 進行深度推演。")
    st.code(data["ai_markdown"], language="markdown")
