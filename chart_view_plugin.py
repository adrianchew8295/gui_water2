# 文件名: chart_view_plugin.py
# 职责: TradingView Lightweight Charts 图表穿透插件 (多标的/多周期切换 + K线与成交量独立双窗格 + 实时倒计时)

import os
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import pytz
from data_engine import hub_engine

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")
tz_ny = pytz.timezone("America/New_York")

def render_lightweight_tv_chart(code: str, ktype: str = "5M", bar_count: int = 120):
    """
    基于 TradingView 原生 Lightweight Charts 渲染标的多周期 K 线
    """
    # 1. 轻量增量同步最新柱
    hub_engine.sync_latest_closed_bar(code, ktype)

    clean_name = code.replace(".", "_")
    csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype}.csv")

    if not os.path.exists(csv_path):
        st.warning(f"⚠️ 正在初始化 {code} ({ktype}) 历史数据，请稍候...")
        hub_engine.fetch_deep_history(code, ktype, 30 if ktype == "5M" else 365)

    if not os.path.exists(csv_path):
        st.info("数据归档中，请点击侧边栏同步或稍后刷新。")
        return

    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            st.warning("⚠️ 数据文件为空。")
            return

        df.columns = [c.lower().strip() for c in df.columns]
        df = df.drop_duplicates(subset=['time_key']).sort_values('time_key').tail(bar_count).reset_index(drop=True)

        # 2. 注入实时快照
        snap_df = hub_engine.get_realtime_snapshot([code])
        if snap_df is not None and not snap_df.empty:
            snap = snap_df.iloc[0]
            last_p = float(snap.get('last_price', df.iloc[-1]['close']))
            high_p = float(snap.get('high_price', df.iloc[-1]['high']))
            low_p = float(snap.get('low_price', df.iloc[-1]['low']))
            
            df.at[len(df) - 1, 'close'] = last_p
            df.at[len(df) - 1, 'high'] = max(df.iloc[-1]['high'], high_p, last_p)
            df.at[len(df) - 1, 'low'] = min(df.iloc[-1]['low'], low_p, last_p)

        candles = []
        volumes = []
        session_ranges = []
        is_crypto = code.startswith("CC.")
        current_session_start = None

        for idx, row in df.iterrows():
            time_str = str(row['time_key'])
            if ktype == "DAY":
                t_val = time_str[:10]
                is_extended = False
            else:
                dt = pd.to_datetime(time_str)
                t_val = int(dt.timestamp())
                if is_crypto:
                    is_extended = False
                else:
                    hour = dt.hour
                    minute = dt.minute
                    is_extended = (4 <= hour < 9) or (hour == 9 and minute < 30) or (16 <= hour < 20)

            o = float(row['open'])
            h = float(row['high'])
            l = float(row['low'])
            c = float(row['close'])
            v = float(row.get('volume', 0))

            candles.append({"time": t_val, "open": o, "high": h, "low": l, "close": c})
            vol_color = "#00E676" if c >= o else "#FF5252"
            volumes.append({"time": t_val, "value": v, "color": vol_color})

            if is_extended:
                if current_session_start is None:
                    current_session_start = t_val
            else:
                if current_session_start is not None:
                    session_ranges.append({"start": current_session_start, "end": t_val})
                    current_session_start = None

        if current_session_start is not None and candles:
            session_ranges.append({"start": current_session_start, "end": candles[-1]["time"]})

        candles_json = json.dumps(candles)
        volumes_json = json.dumps(volumes)
        sessions_json = json.dumps(session_ranges)

        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                body {{ margin: 0; padding: 0; background-color: #0d1117; font-family: monospace; overflow: hidden; }}
                #main_wrapper {{ position: relative; width: 100%; height: 380px; }}
                #vol_wrapper {{ position: relative; width: 100%; height: 130px; margin-top: 4px; }}
                .chart-box {{ width: 100%; height: 100%; position: absolute; z-index: 2; }}
                .shading-layer {{ width: 100%; height: 100%; position: absolute; top: 0; left: 0; z-index: 1; pointer-events: none; }}
                .chart-header {{ position: absolute; top: 6px; left: 10px; right: 10px; z-index: 10; display: flex; justify-content: space-between; align-items: center; pointer-events: none; }}
                .badge-tag {{ font-size: 11px; font-weight: bold; color: #8b949e; background: rgba(22, 27, 34, 0.85); border: 1px solid #30363d; padding: 2px 6px; border-radius: 4px; }}
                .tv-timer {{ font-size: 11px; font-family: monospace; font-weight: bold; color: #ffd700; background: rgba(22, 27, 34, 0.9); border: 1px solid #d29922; padding: 2px 8px; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div id="main_wrapper">
                <div class="chart-header">
                    <span class="badge-tag">📊 K线走势 ({code} · {ktype})</span>
                    <span id="tv_countdown" class="tv-timer">⏱️ 倒计时计算中...</span>
                </div>
                <canvas id="main_shading" class="shading-layer"></canvas>
                <div id="main_chart" class="chart-box"></div>
            </div>
            <div id="vol_wrapper">
                <div class="chart-header">
                    <span class="badge-tag">机构量能 (Volume)</span>
                </div>
                <canvas id="vol_shading" class="shading-layer"></canvas>
                <div id="vol_chart" class="chart-box"></div>
            </div>

            <script>
                const mainWrapper = document.getElementById('main_wrapper');
                const volWrapper = document.getElementById('vol_wrapper');
                const mainCanvas = document.getElementById('main_shading');
                const volCanvas = document.getElementById('vol_shading');
                const ctxMain = mainCanvas.getContext('2d');
                const ctxVol = volCanvas.getContext('2d');
                const timerEl = document.getElementById('tv_countdown');

                function resizeCanvases() {{
                    mainCanvas.width = mainWrapper.clientWidth;
                    mainCanvas.height = mainWrapper.clientHeight;
                    volCanvas.width = volWrapper.clientWidth;
                    volCanvas.height = volWrapper.clientHeight;
                }}
                resizeCanvases();

                const ktype = "{ktype}";
                function updateTimer() {{
                    const now = new Date();
                    const sec = now.getSeconds();
                    const min = now.getMinutes();

                    if (ktype === "5M") {{
                        const totalSec = min * 60 + sec;
                        const remSec = 300 - (totalSec % 300);
                        const m = Math.floor((remSec === 300 ? 0 : remSec) / 60);
                        const s = (remSec === 300 ? 0 : remSec) % 60;
                        timerEl.innerHTML = "⏱️ 下根 5M 换棒: " + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
                    }} else if (ktype === "1H") {{
                        const totalSec = min * 60 + sec;
                        const remSec = 3600 - (totalSec % 3600);
                        const m = Math.floor(remSec / 60);
                        const s = remSec % 60;
                        timerEl.innerHTML = "⏱️ 下根 1H 换棒: " + (m < 10 ? "0" : "") + m + ":" + (s < 10 ? "0" : "") + s;
                    }} else {{
                        timerEl.innerHTML = "📅 日线周期 (收盘结算)";
                    }}
                }}
                updateTimer();
                setInterval(updateTimer, 1000);

                const commonOptions = {{
                    layout: {{ background: {{ type: 'solid', color: 'transparent' }}, textColor: '#8b949e', fontSize: 11 }},
                    grid: {{ vertLines: {{ color: '#161b22' }}, horzLines: {{ color: '#161b22' }} }},
                    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                    rightPriceScale: {{ borderColor: '#30363d', autoScale: true }},
                    timeScale: {{ borderColor: '#30363d', timeVisible: true, secondsVisible: false }},
                }};

                const mainChart = LightweightCharts.createChart(document.getElementById('main_chart'), {{
                    ...commonOptions,
                    timeScale: {{ ...commonOptions.timeScale, visible: false }},
                }});
                const mainSeries = mainChart.addCandlestickSeries({{
                    upColor: '#00E676', downColor: '#FF5252', borderVisible: false, wickUpColor: '#00E676', wickDownColor: '#FF5252'
                }});
                mainSeries.setData({candles_json});

                const volChart = LightweightCharts.createChart(document.getElementById('vol_chart'), {{
                    ...commonOptions,
                    rightPriceScale: {{ borderColor: '#30363d', autoScale: true, scaleMargins: {{ top: 0.1, bottom: 0 }} }}
                }});
                const volumeSeries = volChart.addHistogramSeries({{
                    priceFormat: {{ type: 'volume' }},
                }});
                volumeSeries.setData({volumes_json});

                let isSyncing = false;
                mainChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
                    if (isSyncing || !range) return;
                    isSyncing = true;
                    volChart.timeScale().setVisibleLogicalRange(range);
                    isSyncing = false;
                    drawShadings();
                }});

                volChart.timeScale().subscribeVisibleLogicalRangeChange(range => {{
                    if (isSyncing || !range) return;
                    isSyncing = true;
                    mainChart.timeScale().setVisibleLogicalRange(range);
                    isSyncing = false;
                    drawShadings();
                }});

                const sessionRanges = {sessions_json};
                function drawShadings() {{
                    ctxMain.clearRect(0, 0, mainCanvas.width, mainCanvas.height);
                    ctxVol.clearRect(0, 0, volCanvas.width, volCanvas.height);
                    const ts = mainChart.timeScale();
                    ctxMain.fillStyle = 'rgba(255, 255, 255, 0.04)';
                    ctxVol.fillStyle = 'rgba(255, 255, 255, 0.04)';

                    for (const s of sessionRanges) {{
                        const x1 = ts.timeToCoordinate(s.start);
                        const x2 = ts.timeToCoordinate(s.end);
                        if (x1 !== null && x2 !== null) {{
                            const left = Math.min(x1, x2);
                            const width = Math.abs(x2 - x1);
                            ctxMain.fillRect(left, 0, width, mainCanvas.height);
                            ctxVol.fillRect(left, 0, width, volCanvas.height);
                        }}
                    }}
                }}
                setTimeout(drawShadings, 150);

                window.addEventListener('resize', () => {{
                    resizeCanvases();
                    mainChart.applyOptions({{ width: mainWrapper.clientWidth }});
                    volChart.applyOptions({{ width: volWrapper.clientWidth }});
                    drawShadings();
                }});
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=530)
    except Exception as e:
        st.error(f"图表渲染异常: {str(e)}")


def render_chart_view(assets):
    """
    app.py 调用的主入口
    """
    st.markdown("### 📊 标的多周期走势穿透 (Chart View)")
    
    if not assets:
        st.info("自选列表中暂无标的，请在左侧侧边栏添加。")
        return

    code_options = [f"{a['code']} ({a['name']})" for a in assets]
    
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        sel_asset_str = st.selectbox("🎯 穿透标的", code_options, index=0)
        selected_code = sel_asset_str.split(" ")[0]
    with c2:
        selected_ktype = st.selectbox("⏱️ 观察周期", ["5M", "1H", "DAY"], index=0)
    with c3:
        bar_count = st.slider("柱数限制", min_value=30, max_value=300, value=100, step=10)

    render_lightweight_tv_chart(selected_code, selected_ktype, bar_count)
