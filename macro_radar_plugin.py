# 文件名: macro_radar_plugin.py
# 職責: 12 檔核心宏觀雷達日線幾何通道、人性化波段防守、圖層 ON/OFF 開關、AI Markdown 數據導出

import os
import datetime
import pytz
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

tz_ny = pytz.timezone("America/New_York")

def fetch_daily_kline_safe(code: str, bars: int = 300) -> pd.DataFrame:
    """極速安全加載日線數據 (優先 OpenD -> 本地 CSV -> yfinance 備援)"""
    # 1. 優先嘗試 OpenD 直連
    try:
        from moomoo import OpenQuoteContext, RET_OK, KLType, AuType
        quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        today_dt = datetime.datetime.now(tz_ny).date()
        start_str = (today_dt - datetime.timedelta(days=int(bars * 1.8))).strftime("%Y-%m-%d")
        end_str = today_dt.strftime("%Y-%m-%d")
        
        ret, df_k, _ = quote_ctx.request_history_kline(
            code=code,
            start=start_str,
            end=end_str,
            ktype=KLType.K_DAY,
            autype=AuType.QFQ,
            max_count=bars
        )
        quote_ctx.close()
        if ret == RET_OK and df_k is not None and not df_k.empty:
            df = df_k.copy()
            df.columns = [c.lower() for c in df.columns]
            time_col = 'time_key' if 'time_key' in df.columns else df.columns[0]
            df['time_clean'] = df[time_col].astype(str).str.slice(0, 10)
            return df[['time_clean', 'open', 'high', 'low', 'close', 'volume']].sort_values('time_clean').reset_index(drop=True)
    except Exception:
        pass

    # 2. 備用：讀取本地 market_data CSV
    clean_code = code.replace('.', '_')
    candidates = [
        f"./market_data/{clean_code}_DAY.csv",
        f"./market_data/{code}_DAY.csv",
        f"./market_data/{clean_code}.csv"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                df = pd.read_csv(p)
                df.columns = [c.lower() for c in df.columns]
                time_col = 'time_clean' if 'time_clean' in df.columns else ('time_key' if 'time_key' in df.columns else df.columns[0])
                df['time_clean'] = df[time_col].astype(str).str.slice(0, 10)
                if not df.empty:
                    return df[['time_clean', 'open', 'high', 'low', 'close', 'volume']].sort_values('time_clean').tail(bars).reset_index(drop=True)
            except Exception:
                pass

    # 3. 備用：yfinance 網絡拉取
    try:
        import yfinance as yf
        sym = code.replace("US.", "").replace("CC.", "").replace("HK.", "")
        yf_sym = f"{sym}-USD" if "CC." in code else sym
        df_yf = yf.download(yf_sym, period="2y", interval="1d", progress=False, auto_adjust=False)
        if df_yf is not None and not df_yf.empty:
            df_yf.columns = [c[0].lower() if isinstance(c, tuple) else c.lower() for c in df_yf.columns]
            df_yf = df_yf.reset_index()
            dt_col = 'Date' if 'Date' in df_yf.columns else ('Datetime' if 'Datetime' in df_yf.columns else df_yf.columns[0])
            df_yf['time_clean'] = df_yf[dt_col].astype(str).str.slice(0, 10)
            return df_yf[['time_clean', 'open', 'high', 'low', 'close', 'volume']].dropna().sort_values('time_clean').tail(bars).reset_index(drop=True)
    except Exception:
        pass

    return pd.DataFrame()

def find_humanized_pivots(df: pd.DataFrame, window: int = 8):
    """提取波段擺動頂底極值點 (Swing Pivots)"""
    highs = df['high'].values
    lows = df['low'].values
    times = df['time_clean'].values
    n = len(df)
    
    swing_highs = []
    swing_lows = []
    
    for i in range(window, n - window):
        if np.all(highs[i] >= highs[i - window:i]) and np.all(highs[i] >= highs[i + 1:i + window + 1]):
            swing_highs.append({"idx": i, "time": str(times[i])[:10], "price": float(highs[i])})
        if np.all(lows[i] <= lows[i - window:i]) and np.all(lows[i] <= lows[i + 1:i + window + 1]):
            swing_lows.append({"idx": i, "time": str(times[i])[:10], "price": float(lows[i])})
            
    return swing_highs, swing_lows

def compute_humanized_channel(df: pd.DataFrame, ticker: str = "US.NVDA"):
    """計算人性化波段幾何、動態通道與 AI 導出日誌"""
    if df is None or len(df) < 20:
        return {"status": "fail", "msg": "K線數據不足"}

    times = df['time_clean'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    n = len(df)
    last_idx = n - 1
    curr_price = float(closes[-1])

    # 1. 尋找波段頂底
    sw_highs, sw_lows = find_humanized_pivots(df, window=8)
    if len(sw_highs) < 2 or len(sw_lows) < 2:
        sw_highs, sw_lows = find_humanized_pivots(df, window=4)

    # 2. 人性化 Major Support（鎖定近 120 根波段的結構底座，拒絕遠古噪點）
    active_lookback = min(n, 120)
    recent_low_window = lows[-active_lookback:]
    major_support_val = float(np.percentile(recent_low_window, 10))
    if len(sw_lows) >= 2:
        recent_pivots = [p["price"] for p in sw_lows if p["idx"] >= (n - active_lookback)]
        if recent_pivots:
            major_support_val = min(recent_pivots)

    # 3. 即時水平 S/R
    recent_res = sw_highs[-1]["price"] if sw_highs else float(highs[-20:].max())
    recent_sup = sw_lows[-1]["price"] if sw_lows else float(lows[-20:].min())

    # 4. 構建當前活躍軌道
    macro_channel = None
    h1, h2, l1, l2 = None, None, None, None
    curr_res_val, curr_sup_val = recent_res, recent_sup

    if len(sw_highs) >= 2 and len(sw_lows) >= 2:
        h1, h2 = sw_highs[-2], sw_highs[-1]
        l1, l2 = sw_lows[-2], sw_lows[-1]

        # 阻力射線
        dx_h = max(1, h2["idx"] - h1["idx"])
        slope_h = (h2["price"] - h1["price"]) / dx_h
        curr_res_val = h2["price"] + slope_h * (last_idx - h2["idx"])

        # 支撐射線
        dx_l = max(1, l2["idx"] - l1["idx"])
        slope_l = (l2["price"] - l1["price"]) / dx_l
        curr_sup_val = l2["price"] + slope_l * (last_idx - l2["idx"])

        res_line = [{"time": str(times[i]), "value": round(float(h1["price"] + slope_h * (i - h1["idx"])), 2)} for i in range(h1["idx"], n)]
        sup_line = [{"time": str(times[i]), "value": round(float(l1["price"] + slope_l * (i - l1["idx"])), 2)} for i in range(l1["idx"], n)]

        trend_type = "🟢 上升通道 (Bullish Channel)" if slope_l > 0 else ("🔴 下降通道 (Bearish Channel)" if slope_l < 0 else "⚪ 箱體震盪 (Range)")

        macro_channel = {
            "trend_type": trend_type,
            "res_line": res_line,
            "sup_line": sup_line,
            "curr_res_val": round(curr_res_val, 2),
            "curr_sup_val": round(curr_sup_val, 2),
            "h1": h1, "h2": h2, "l1": l1, "l2": l2
        }

    # 5. 生成標準 AI 導出 Markdown
    h1_txt = f"{h1['time']} (${h1['price']:.2f})" if h1 else "--"
    h2_txt = f"{h2['time']} (${h2['price']:.2f})" if h2 else "--"
    l1_txt = f"{l1['time']} (${l1['price']:.2f})" if l1 else "--"
    l2_txt = f"{l2['time']} (${l2['price']:.2f})" if l2 else "--"

    ai_markdown = f"""### 📊 【{ticker} 日線技術幾何與趨勢通道審計報告】
**審計基準日期**: {times[-1]} | **最新收盤現價**: ${curr_price:.2f} | **總K線樣本**: {n} 根

#### 1. 當前波段幾何戰區 (John J. Murphy 體系)
- **通道形態判定**: {macro_channel['trend_type'] if macro_channel else '區間震盪整理'}
- **動態阻力線 (Upper Channel)**:
  - 錨點連線: 起點 P1 [{h1_txt}] ➔ 終點 P2 [{h2_txt}]
  - 當前動態阻力價位: **${curr_res_val:.2f}**
- **動態支撐線 (Lower Channel)**:
  - 錨點連線: 起點 P1 [{l1_txt}] ➔ 終點 P2 [{l2_txt}]
  - 當前動態支撐價位: **${curr_sup_val:.2f}**
- **近端即時水平戰區**:
  - 即時阻力 (RES): ${recent_res:.2f}
  - 即時支撐 (SUP): ${recent_sup:.2f}
- **⭐ 當前大波段 Major Support (核心防守底座)**: **${major_support_val:.2f}** (已排除遠古失效噪點)

#### 2. 空間目標推演 (Fibonacci Extension)
- 上方突破 Target 1 (0.618x): **${(curr_res_val + abs(curr_res_val - curr_sup_val) * 0.618):.2f}**
- 下方破位 Target 2 (通道下破): **${(curr_sup_val - abs(curr_res_val - curr_sup_val) * 0.618):.2f}**

---
#### 3. 給 AI 策略軍師的診斷指令 (Direct Prompt):
1. **通道所處位置分析**：現價 ${curr_price:.2f} 處於通道（上軌 ${curr_res_val:.2f} / 下軌 ${curr_sup_val:.2f}）的哪一個百分比分位？
2. **突破/回踩策略**：當前是處於多頭推升中繼還是接近天花板頂背離？
3. **風控邊界**：若失守當前動態支撐 ${curr_sup_val:.2f}，第一回撤目標與 Major Support (${major_support_val:.2f}) 的盈虧比是否合理？
"""

    return {
        "status": "success",
        "ticker": ticker,
        "curr_price": curr_price,
        "major_support": round(major_support_val, 2),
        "recent_res": round(recent_res, 2),
        "recent_sup": round(recent_sup, 2),
        "macro_channel": macro_channel,
        "ai_markdown": ai_markdown
    }

def render_macro_radar_view(assets=None):
    """
    主入口：支援傳入 list/dict 標的池，自帶完整圖表、ON/OFF開關與 AI Markdown
    """
    # 1. 提取可選標的清單
    default_symbols = ["US.NVDA", "US.QQQ", "US.AAPL", "US.MSFT", "US.AMZN", "US.GOOGL", "US.META", "US.TSLA", "US.AVGO", "US.MU", "US.AMD", "US.WDC", "US.STX"]
    symbol_options = []
    
    if isinstance(assets, list) and len(assets) > 0:
        for a in assets:
            if isinstance(a, dict) and 'code' in a:
                symbol_options.append(a['code'])
            elif isinstance(a, str):
                symbol_options.append(a)
    elif isinstance(assets, pd.DataFrame) and not assets.empty and 'code' in assets.columns:
        symbol_options = assets['code'].tolist()
        
    if not symbol_options:
        symbol_options = default_symbols

    # 2. 標的選擇與 K 線長度控制器
    c_sel, c_bar = st.columns([3, 2])
    with c_sel:
        target_code = st.selectbox("🎯 選擇分析標的", symbol_options, index=0 if "US.NVDA" not in symbol_options else symbol_options.index("US.NVDA"))
    with c_bar:
        bars_count = st.slider("🎛️ 歷史 K 線跨度 (Bars)", min_value=60, max_value=800, value=300, step=20)

    # 3. 加載數據
    with st.spinner(f"正在加載 {target_code} 日線數據與幾何模型..."):
        df = fetch_daily_kline_safe(target_code, bars=bars_count)

    if df.empty or len(df) < 15:
        st.warning(f"⚠️ 標的 {target_code} 暫無足夠日線數據，請確認 OpenD 連線或本地數據。")
        return

    # 4. 計算通道與戰情數據
    data = compute_humanized_channel(df, ticker=target_code)
    if data["status"] != "success":
        st.error(f"❌ 通道計算失敗: {data.get('msg')}")
        return

    chan = data["macro_channel"]
    curr_p = data["curr_price"]
    maj_sup = data["major_support"]
    rec_res = data["recent_res"]
    rec_sup = data["recent_sup"]

    # 5. 頂部 HUD 狀態卡
    st.markdown(
        f"""
        <div style="background-color: #0e1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; font-family: monospace;">
            <div style="font-size: 15px; font-weight: bold; color: #58a6ff;">
                📊 {target_code} · 純日線技術幾何通道 (John J. Murphy 體系)
            </div>
            <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 18px; font-size: 13px; color: #c9d1d9;">
                <span>現價: <b style="color: #79c0ff;">${curr_p:.2f}</b></span>
                <span>即時阻力 (RES): <b style="color: #ff7b72;">${rec_res:.2f}</b></span>
                <span>即時支撐 (SUP): <b style="color: #56d364;">${rec_sup:.2f}</b></span>
                <span>⭐ 當前波段重大支撐: <b style="color: #00e5ff;">${maj_sup:.2f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 6. 繪圖圖層獨立 ON/OFF 開關
    st.markdown("##### 🎛️ 圖表繪圖圖層控制 (Drawing Toggles)")
    t1, t2, t3, t4, t5 = st.columns(5)
    with t1:
        show_channel = st.checkbox("📐 趨勢通道 (Channel)", value=True)
    with t2:
        show_sr = st.checkbox("🧱 即時 S/R 水平線", value=True)
    with t3:
        show_major = st.checkbox("⭐ 重大支撐 (Major)", value=True)
    with t4:
        show_pivots = st.checkbox("🏷️ 錨點標籤 (Pivots)", value=True)
    with t5:
        zoom_recent = st.checkbox("🔍 聚焦近 120 根 K 線", value=True)

    # 7. 視窗縮放剪裁
    plot_df = df.iloc[-120:].copy() if (zoom_recent and len(df) > 120) else df.copy()

    # 8. 繪製 Plotly 圖表
    fig = go.Figure()

    # K 線主體
    fig.add_trace(go.Candlestick(
        x=plot_df['time_clean'],
        open=plot_df['open'], high=plot_df['high'],
        low=plot_df['low'], close=plot_df['close'],
        name="日K線",
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ))

    # [開關 1] 趨勢通道
    if show_channel and chan:
        res_x = [p["time"] for p in chan["res_line"] if p["time"] in plot_df['time_clean'].values]
        res_y = [p["value"] for p in chan["res_line"] if p["time"] in plot_df['time_clean'].values]
        sup_x = [p["time"] for p in chan["sup_line"] if p["time"] in plot_df['time_clean'].values]
        sup_y = [p["value"] for p in chan["sup_line"] if p["time"] in plot_df['time_clean'].values]

        if res_x:
            fig.add_trace(go.Scatter(x=res_x, y=res_y, mode='lines', line=dict(color='#ffd600', width=2, dash='dash'), name="通道上軌 (Upper)"))
        if sup_x:
            fig.add_trace(go.Scatter(x=sup_x, y=sup_y, mode='lines', line=dict(color='#00e676', width=2, dash='solid'), name="通道下軌 (Lower)"))

    # [開關 2] 即時 S/R 水平線
    if show_sr:
        fig.add_hline(y=rec_res, line_dash="dot", line_color="#ff5252", annotation_text=f"RES: ${rec_res:.2f}", annotation_position="top right")
        fig.add_hline(y=rec_sup, line_dash="dot", line_color="#00e676", annotation_text=f"SUP: ${rec_sup:.2f}", annotation_position="bottom right")

    # [開關 3] 當前大波段 Major Support
    if show_major:
        fig.add_hline(y=maj_sup, line_dash="solid", line_width=2, line_color="#00e5ff", annotation_text=f"⭐ MAJOR SUPPORT: ${maj_sup:.2f}", annotation_position="bottom right")

    # [開關 4] 錨點標籤
    if show_pivots and chan:
        for pt, label, color in [(chan["h1"], "峰1", "#ff5252"), (chan["h2"], "峰2", "#ff5252"), (chan["l1"], "谷1", "#00e676"), (chan["l2"], "谷2", "#00e676")]:
            if pt and pt["time"] in plot_df['time_clean'].values:
                fig.add_annotation(
                    x=pt["time"], y=pt["price"],
                    text=f"{label}: ${pt['price']:.2f}",
                    showarrow=True, arrowhead=2,
                    yshift=12 if "峰" in label else -12,
                    font=dict(color=color, size=11)
                )

    fig.update_layout(
        template="plotly_dark",
        height=540,
        margin=dict(l=10, r=60, t=10, b=10),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig, use_container_width=True)

    # 9. AI 分析專用 Markdown 日誌框 (一鍵複製)
    st.divider()
    st.markdown("#### 🤖 AI 策略軍師專用診斷 Markdown 日誌 (可直接複製發送給 AI)")
    st.caption("點擊下方右上角按鈕即可直接複製完整技術幾何數據，貼入 ChatGPT / Claude / Gemini 進行深度推演。")
    st.code(data["ai_markdown"], language="markdown")
