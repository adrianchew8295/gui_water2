# 文件名: macro_radar_plugin.py
# 職責: 整合 TradingView Lightweight Charts 原生 Canvas 渲染、繪圖圖層開關 (含艾略特波浪)、數據自審核與 AI Markdown 日誌

import os
import json
import datetime
import pytz
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from macro_radar_engine import compute_radar_channel_and_markdown

tz_ny = pytz.timezone("America/New_York")

def fetch_daily_kline_safe(code: str, bars: int = 500) -> pd.DataFrame:
    """極速安全加載日線數據 (固定拉滿最高歷史深度)"""
    clean_code = code.replace('.', '_')
    
    # 1. 優先讀取本地 market_data CSV (已由 data_engine 深度對齊)
    candidates = [
        f"./market_data/{clean_code}_DAY.csv",
        f"./market_data/{code}_DAY.csv",
        f"./market_data/{clean_code}.csv"
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                df = pd.read_csv(p)
                df.columns = [c.lower().strip() for c in df.columns]
                time_col = 'time_clean' if 'time_clean' in df.columns else ('time_key' if 'time_key' in df.columns else df.columns[0])
                df['time_clean'] = df[time_col].astype(str).str.slice(0, 10)
                if not df.empty and len(df) >= 15:
                    return df[['time_clean', 'open', 'high', 'low', 'close', 'volume']].drop_duplicates('time_clean').sort_values('time_clean').tail(bars).reset_index(drop=True)
            except Exception:
                pass

    # 2. 備用：OpenD 直連拉取
    try:
        from moomoo import OpenQuoteContext, RET_OK, KLType, AuType
        quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
        now_ny = datetime.datetime.now(tz_ny)
        end_str = now_ny.strftime("%Y-%m-%d %H:%M:%S")
        
        ret, df_k, _ = quote_ctx.request_history_kline(
            code=code,
            start='',
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
            df = df[['time_clean', 'open', 'high', 'low', 'close', 'volume']].drop_duplicates('time_clean').sort_values('time_clean').tail(bars).reset_index(drop=True)
            
            try:
                os.makedirs("./market_data", exist_ok=True)
                df.to_csv(f"./market_data/{clean_code}_DAY.csv", index=False)
            except Exception:
                pass
            return df
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
            return df_yf[['time_clean', 'open', 'high', 'low', 'close', 'volume']].dropna().drop_duplicates('time_clean').sort_values('time_clean').tail(bars).reset_index(drop=True)
    except Exception:
        pass

    return pd.DataFrame()

def render_macro_radar_view(assets=None):
    """
    12 檔宏觀雷達主入口：支援墨菲通道、艾略特波浪圖層控制與可審計 AI 日誌
    """
    default_symbols = ["US.NVDA", "US.QQQ", "US.AAPL", "US.MSFT", "US.AMZN", "US.GOOGL", "US.META", "US.TSLA", "US.AVGO", "US.MU", "US.AMD", "US.WDC"]
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

    # 1. 標的選擇器
    target_code = st.selectbox("🎯 選擇分析標的", symbol_options, index=0 if "US.NVDA" not in symbol_options else symbol_options.index("US.NVDA"))

    # 2. 加載最高規格日線數據 (固定 500 根滿載)
    df = fetch_daily_kline_safe(target_code, bars=500)
    if df.empty or len(df) < 15:
        st.warning(f"⚠️ 標的 {target_code} 暫無足夠日線數據，請確認本地 market_data 或 OpenD 連線。")
        return

    # 3. 幾何與波浪運算
    data = compute_radar_channel_and_markdown(df, ticker=target_code)
    if data["status"] != "success":
        st.error(f"❌ 計算失敗: {data.get('msg')}")
        return

    chan = data["macro_channel"]
    ew = data.get("elliott_wave")
    curr_p = data["curr_price"]
    maj_sup = data["major_support"]
    rec_res = data["recent_res"]
    rec_sup = data["recent_sup"]

    # 4. 頂部 HUD 狀態卡
    ew_summary_str = f"<span style='color: #e040fb;'>🌊 {ew['pattern'].split('(')[0].strip()}</span>" if ew else "<span style='color: #8b949e;'>⚪ 波浪整理中</span>"
    st.markdown(
        f"""
        <div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; font-family: monospace;">
            <div style="font-size: 15px; font-weight: bold; color: #58a6ff; display: flex; justify-content: space-between; align-items: center;">
                <span>📊 {target_code} · 日線幾何通道 & 艾略特波浪共振分析</span>
                <span style="font-size: 13px;">{ew_summary_str}</span>
            </div>
            <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 20px; font-size: 13px; color: #c9d1d9;">
                <span>現價: <b style="color: #79c0ff;">${curr_p:.2f}</b></span>
                <span>即時阻力 (RES): <b style="color: #ff7b72;">${rec_res:.2f}</b></span>
                <span>即時支撐 (SUP): <b style="color: #56d364;">${rec_sup:.2f}</b></span>
                <span>⭐ 重大支撐 (Major): <b style="color: #00e5ff;">${maj_sup:.2f}</b></span>
                {f'<span>🎯 浪⑤目標: <b style="color: #e040fb;">${ew["target_1"]:.2f}</b></span>' if ew else ''}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 5. 繪圖圖層獨立 ON/OFF 開關 (5 大獨立開關)
    st.markdown("##### 🎛️ 圖表繪圖圖層控制 (Drawing Toggles)")
    t1, t2, t3, t4, t5 = st.columns(5)
    with t1:
        show_channel = st.checkbox("📐 墨菲通道", value=True)
    with t2:
        show_ew = st.checkbox("🌊 艾略特波浪", value=True)
    with t3:
        show_sr = st.checkbox("🧱 即時 S/R 水平線", value=True)
    with t4:
        show_major = st.checkbox("⭐ 重大支撐", value=True)
    with t5:
        show_markers = st.checkbox("🏷️ 極值錨點標籤", value=False)

    # 6. 序列化 TradingView 數據
    candles_data = []
    for _, row in df.iterrows():
        candles_data.append({
            "time": str(row['time_clean']),
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close'])
        })

    channel_res_data = []
    channel_sup_data = []
    ew_line_data = []
    markers_data = []

    # 墨菲通道數據
    if chan and show_channel:
        channel_res_data = chan["res_line"]
        channel_sup_data = chan["sup_line"]

    # 艾略特波浪折線與標籤數據
    if ew and show_ew:
        ew_line_data = ew["wave_lines"]
        markers_data.extend(ew["wave_markers"])

    # 墨菲通道錨點標籤
    if chan and show_markers:
        for pt, lbl, color, shape in [
            (chan["h1"], "峰1", "#ff5252", "arrowDown"),
            (chan["h2"], "峰2", "#ff5252", "arrowDown"),
            (chan["l1"], "谷1", "#00e676", "arrowUp"),
            (chan["l2"], "谷2", "#00e676", "arrowUp")
        ]:
            if pt:
                markers_data.append({
                    "time": pt["time"],
                    "position": "aboveBar" if "峰" in lbl else "belowBar",
                    "color": color,
                    "shape": shape,
                    "text": f"{lbl}: ${pt['price']:.2f}"
                })

    candles_json = json.dumps(candles_data)
    res_line_json = json.dumps(channel_res_data)
    sup_line_json = json.dumps(channel_sup_data)
    ew_line_json = json.dumps(ew_line_data)
    markers_json = json.dumps(markers_data)

    # 7. TradingView Lightweight Charts HTML/JS 畫布注入
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body {{ margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
            #tv_chart_container {{ width: 100%; height: 560px; }}
        </style>
    </head>
    <body>
        <div id="tv_chart_container"></div>
        <script>
            const container = document.getElementById('tv_chart_container');
            const chart = LightweightCharts.createChart(container, {{
                layout: {{
                    background: {{ type: 'solid', color: '#0d1117' }},
                    textColor: '#8b949e',
                    fontSize: 12,
                }},
                grid: {{
                    vertLines: {{ color: '#161b22' }},
                    horzLines: {{ color: '#161b22' }},
                }},
                crosshair: {{
                    mode: LightweightCharts.CrosshairMode.Normal,
                    vertLine: {{ color: '#58a6ff', width: 1, style: 3, labelBackgroundColor: '#1f6feb' }},
                    horzLine: {{ color: '#58a6ff', width: 1, style: 3, labelBackgroundColor: '#1f6feb' }},
                }},
                rightPriceScale: {{
                    borderColor: '#30363d',
                    autoScale: true,
                    scaleMargins: {{ top: 0.1, bottom: 0.15 }},
                }},
                timeScale: {{
                    borderColor: '#30363d',
                    timeVisible: true,
                    secondsVisible: false,
                }},
                handleScroll: {{ mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }},
                handleScale: {{ axisPressedMouseMove: true, mouseWheel: true, pinch: true }},
            }});

            // 1. K 線主圖 (綠漲紅跌)
            const candleSeries = chart.addCandlestickSeries({{
                upColor: '#00E676',
                downColor: '#FF5252',
                borderVisible: false,
                wickUpColor: '#00E676',
                wickDownColor: '#FF5252',
            }});
            candleSeries.setData({candles_json});

            // 2. 墨菲通道 - 上軌
            const resData = {res_line_json};
            if (resData.length > 0) {{
                const resSeries = chart.addLineSeries({{
                    color: '#FFD600',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    title: '通道阻力 (Upper)',
                }});
                resSeries.setData(resData);
            }}

            // 3. 墨菲通道 - 下軌
            const supData = {sup_line_json};
            if (supData.length > 0) {{
                const supSeries = chart.addLineSeries({{
                    color: '#00E676',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Solid,
                    title: '通道支撐 (Lower)',
                }});
                supSeries.setData(supData);
            }}

            // 4. 艾略特波浪骨架線 (紫色高亮折線)
            const ewData = {ew_line_json};
            if (ewData.length > 0) {{
                const ewSeries = chart.addLineSeries({{
                    color: '#E040FB',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Solid,
                    title: '艾略特波浪骨架 (EW)',
                }});
                ewSeries.setData(ewData);
            }}

            // 5. 波浪與極值點標籤
            const markers = {markers_json};
            if (markers.length > 0) {{
                candleSeries.setMarkers(markers);
            }}

            // 6. 即時 S/R 水平線
            if ({str(show_sr).lower()}) {{
                candleSeries.createPriceLine({{
                    price: {rec_res},
                    color: '#FF5252',
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible: true,
                    title: 'RES',
                }});
                candleSeries.createPriceLine({{
                    price: {rec_sup},
                    color: '#00E676',
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dotted,
                    axisLabelVisible: true,
                    title: 'SUP',
                }});
            }}

            // 7. Major Support 重大支撐線 (藍色基準線)
            if ({str(show_major).lower()}) {{
                candleSeries.createPriceLine({{
                    price: {maj_sup},
                    color: '#00E5FF',
                    lineWidth: 2,
                    lineStyle: LightweightCharts.LineStyle.Solid,
                    axisLabelVisible: true,
                    title: '⭐ MAJOR SUPPORT',
                }});
            }}

            window.addEventListener('resize', () => {{
                chart.applyOptions({{ width: container.clientWidth }});
            }});
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=580)

    # 8. AI 審計 Markdown 輸出框 (一鍵複製)
    st.divider()
    st.markdown("#### 🤖 AI 策略軍師專用診斷 Markdown 日誌 (可直接複製發送給 AI)")
    st.caption("點擊下方右上角按鈕即可直接複製完整技術幾何、墨菲通道與艾略特波浪數據，貼入外部 AI 進行深度推演。")
    st.code(data["ai_markdown"], language="markdown")
