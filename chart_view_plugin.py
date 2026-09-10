# 文件名: chart_view_plugin.py
# 職責: 專業 TradingView 互動圖表渲染 (雙窗格 K線75% + Volume 25% + 盤前盤後遮罩 + 縮放拖拽 + 全參數相容)

import os
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import pytz

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")
tz_ny = pytz.timezone("America/New_York")

def render_lightweight_tv_chart(code: str, ktype_str: str = "DAY", bars_count: int = 150):
    """底層 TradingView 渲染核心"""
    clean_name = str(code).replace(".", "_")
    csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype_str.upper()}.csv")

    if not os.path.exists(csv_path):
        st.warning(f"⚠️ 本地缺少數據: `{csv_path}`，請點擊上方按鈕一鍵補齊數據！")
        return

    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            st.warning("⚠️ 數據文件為空。")
            return

        df.columns = [c.lower().strip() for c in df.columns]
        if 'time_key' not in df.columns:
            st.warning("⚠️ 缺少 time_key 欄位。")
            return

        df = df.drop_duplicates(subset=['time_key']).sort_values('time_key').tail(bars_count).reset_index(drop=True)

        candles = []
        volumes = []
        session_ranges = []
        is_crypto = str(code).startswith("CC.")
        current_session_start = None

        for idx, row in df.iterrows():
            time_str = str(row['time_key'])
            
            if ktype_str.upper() == "DAY":
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

            o = float(row.get('open', 0.0))
            h = float(row.get('high', 0.0))
            l = float(row.get('low', 0.0))
            c = float(row.get('close', 0.0))
            v = float(row.get('volume', 0.0))

            candles.append({"time": t_val, "open": o, "high": h, "low": l, "close": c})
            vol_color = "rgba(0, 230, 118, 0.65)" if c >= o else "rgba(255, 82, 82, 0.65)"
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
                body {{ margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; overflow: hidden; }}
                #main_wrapper {{ position: relative; width: 100%; height: 380px; }}
                #vol_wrapper {{ position: relative; width: 100%; height: 130px; margin-top: 4px; }}
                .chart-box {{ width: 100%; height: 100%; position: absolute; z-index: 2; }}
                .shading-layer {{ width: 100%; height: 100%; position: absolute; top: 0; left: 0; z-index: 1; pointer-events: none; }}
                .chart-header {{ position: absolute; top: 6px; left: 10px; right: 10px; z-index: 10; display: flex; justify-content: space-between; align-items: center; pointer-events: none; }}
                .badge-tag {{ font-size: 11px; font-weight: bold; color: #8b949e; background: rgba(22, 27, 34, 0.85); border: 1px solid #30363d; padding: 3px 8px; border-radius: 4px; }}
            </style>
        </head>
        <body>
            <div id="main_wrapper">
                <div class="chart-header">
                    <span class="badge-tag">📊 K線走勢 ({code} · {ktype_str.upper()})</span>
                </div>
                <canvas id="main_shading" class="shading-layer"></canvas>
                <div id="main_chart" class="chart-box"></div>
            </div>
            <div id="vol_wrapper">
                <div class="chart-header">
                    <span class="badge-tag">機構量能 (Volume)</span>
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

                function resizeCanvases() {{
                    mainCanvas.width = mainWrapper.clientWidth;
                    mainCanvas.height = mainWrapper.clientHeight;
                    volCanvas.width = volWrapper.clientWidth;
                    volCanvas.height = volWrapper.clientHeight;
                }}
                resizeCanvases();

                const commonOptions = {{
                    layout: {{ background: {{ type: 'solid', color: 'transparent' }}, textColor: '#8b949e', fontSize: 11 }},
                    grid: {{ vertLines: {{ color: '#161b22' }}, horzLines: {{ color: '#161b22' }} }},
                    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                    rightPriceScale: {{ borderColor: '#30363d', autoScale: true }},
                    timeScale: {{ borderColor: '#30363d', timeVisible: true, secondsVisible: false }},
                    handleScroll: {{ mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }},
                    handleScale: {{ axisPressedMouseMove: true, mouseWheel: true, pinch: true }}
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
        components.html(html_code, height=540)

    except Exception as e:
        st.error(f"❌ TradingView 圖表加載異常: {str(e)}")


def render_chart_view(*args, **kwargs):
    """
    智能全相容入口：
    無論 app.py 傳入 (code, ktype) 還是傳入 (assets) 均能自動精確解構
    """
    if len(args) >= 2:
        code = str(args[0])
        ktype = str(args[1])
        render_lightweight_tv_chart(code, ktype)
    elif len(args) == 1:
        first_arg = args[0]
        if isinstance(first_arg, list):
            code_list = [a['code'] if isinstance(a, dict) else str(a) for a in first_arg]
            c1, c2, c3 = st.columns([3, 2, 2])
            with c1:
                sel_code = st.selectbox("選擇穿透標的", code_list, index=0, key="chart_plugin_code_sel")
            with c2:
                sel_ktype = st.selectbox("選擇週期", ["5M", "1H", "DAY"], index=0, key="chart_plugin_ktype_sel")
            with c3:
                sel_bars = st.slider("顯示柱數", 30, 300, 120, step=10, key="chart_plugin_bars_sel")
            render_lightweight_tv_chart(sel_code, sel_ktype, sel_bars)
        elif isinstance(first_arg, str):
            render_lightweight_tv_chart(first_arg, kwargs.get("ktype", "DAY"))
    else:
        code = kwargs.get("code", "US.QQQ")
        ktype = kwargs.get("ktype", "DAY")
        render_lightweight_tv_chart(code, ktype)
