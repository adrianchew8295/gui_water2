# 文件名: chart_view_plugin.py
# 職責: 渲染 QQQ 納指大盤中樞 (支援 TradingView 原生 Extended Hours 盤前盤後半透明遮罩 · 時段開關 · 最高歷史深度)

import os
import json
import datetime
import pytz
import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from data_engine import hub_engine

tz_ny = pytz.timezone("America/New_York")

def check_and_auto_heal(code: str):
    """安全調用後台自動補齊機制"""
    try:
        if hasattr(hub_engine, 'auto_heal_today_data'):
            hub_engine.auto_heal_today_data(code)
    except Exception:
        pass

def load_kline_safe(code: str, ktype: str = "1H", bars: int = 1500) -> pd.DataFrame:
    """
    從本地 market_data 加載數據，並識別每根 K 線所屬時段 (PREMARKET / REGULAR / AFTERMARKET)
    """
    clean_code = code.replace('.', '_')
    k_suffix = "5M" if "5" in ktype.upper() else ("1H" if "1H" in ktype.upper() or "60" in ktype.upper() else "DAY")
    
    file_candidates = [
        f"./market_data/{clean_code}_{k_suffix}.csv",
        f"./market_data/{code}_{k_suffix}.csv",
        f"./market_data/{clean_code}.csv"
    ]
    
    for p in file_candidates:
        if os.path.exists(p):
            try:
                df = pd.read_csv(p)
                df.columns = [c.lower().strip() for c in df.columns]
                
                time_col = 'time_key' if 'time_key' in df.columns else ('time_clean' if 'time_clean' in df.columns else df.columns[0])
                df['dt'] = pd.to_datetime(df[time_col])
                
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                df = df.dropna(subset=['open', 'high', 'low', 'close', 'dt'])
                df = df.drop_duplicates('dt').sort_values('dt').tail(bars).reset_index(drop=True)
                
                if not df.empty and len(df) >= 5:
                    if k_suffix == "DAY":
                        df['time_val'] = df['dt'].dt.strftime('%Y-%m-%d')
                        df['is_ext'] = False
                    else:
                        df['time_val'] = df['dt'].astype('int64') // 10**9
                        # 判定美東時間是否為盤前 (04:00~09:30) 或 盤後 (16:00~20:00)
                        hours = df['dt'].dt.hour
                        minutes = df['dt'].dt.minute
                        time_mins = hours * 60 + minutes
                        df['is_ext'] = ((time_mins >= 240) & (time_mins < 570)) | ((time_mins >= 960) & (time_mins <= 1200))
                        
                    df['time_display'] = df['dt'].dt.strftime('%Y-%m-%d %H:%M')
                    return df[['time_val', 'time_display', 'open', 'high', 'low', 'close', 'volume', 'is_ext']]
            except Exception:
                pass
                
    return pd.DataFrame()

def render_lightweight_tv_chart(code: str = "US.QQQ", ktype: str = "1H", bars: int = 1500):
    """
    QQQ 納指中樞主圖入口
    """
    check_and_auto_heal(code)
    
    c1, c2 = st.columns([3, 7])
    with c1:
        k_choice = st.radio("⏱️ 選擇時間週期", ["1H (全時段小時線)", "5M (高頻戰區)", "DAY (日線宏觀)"], index=0, horizontal=True)
        
    actual_ktype = "1H" if "1H" in k_choice else ("5M" if "5M" in k_choice else "DAY")
    max_bars = 1500 if actual_ktype in ["5M", "1H"] else 500
    
    df = load_kline_safe(code, ktype=actual_ktype, bars=max_bars)
    
    if df.empty or len(df) < 5:
        st.warning(f"⚠️ {code} 暫無足夠 {actual_ktype} 歷史數據，請先在終端執行 `python sync_history.py`。")
        return

    curr_close = float(df['close'].iloc[-1])
    curr_vol = float(df['volume'].iloc[-1])
    time_last = str(df['time_display'].iloc[-1])
    
    ema20 = float(df['close'].ewm(span=20).mean().iloc[-1])
    recent_high = float(df['high'].tail(24).max())
    recent_low = float(df['low'].tail(24).min())

    # 頂部 HUD 狀態卡
    st.markdown(
        f"""
        <div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; font-family: monospace;">
            <div style="font-size: 15px; font-weight: bold; color: #58a6ff; display: flex; justify-content: space-between; align-items: center;">
                <span>👑 {code} · {actual_ktype} 核心戰區 (全時段 Extended Hours 已對齊 · 滿載 {len(df)} 根)</span>
                <span style="font-size: 12px; color: #8b949e;">最新時間: {time_last} ET</span>
            </div>
            <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 20px; font-size: 13px; color: #c9d1d9;">
                <span>現價: <b style="color: #79c0ff;">${curr_close:.2f}</b></span>
                <span>EMA20 生命線: <b style="color: #ffd600;">${ema20:.2f}</b></span>
                <span>近期阻力 (SBR): <b style="color: #ff7b72;">${recent_high:.2f}</b></span>
                <span>近期支撐 (RBS): <b style="color: #56d364;">${recent_low:.2f}</b></span>
                <span>當根量能: <b style="color: #e040fb;">{curr_vol:,.0f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 繪圖開關 (新增 Extended Hours 遮罩開關)
    t1, t2, t3, t4 = st.columns(4)
    with t1:
        show_ext = st.checkbox("🌙 盤前盤後遮罩 (Extended Hours)", value=True)
    with t2:
        show_ema = st.checkbox("🟡 EMA20 生命線", value=True)
    with t3:
        show_sbr_rbs = st.checkbox("🧱 近期 SBR/RBS 攻防帶", value=True)
    with t4:
        show_vol = st.checkbox("📊 成交量副圖 (Volume)", value=True)

    candles_data = []
    volume_data = []
    ema_data = []
    ext_ranges = [] # 提取連續的 Extended Hours 區間
    
    df['ema20'] = df['close'].ewm(span=20).mean()
    
    in_ext = False
    ext_start = None
    
    for idx, row in df.iterrows():
        t_val = row['time_val']
        is_e = bool(row['is_ext'])
        
        candles_data.append({
            "time": t_val,
            "open": float(row['open']),
            "high": float(row['high']),
            "low": float(row['low']),
            "close": float(row['close'])
        })
        volume_data.append({
            "time": t_val,
            "value": float(row['volume']),
            "color": "rgba(0, 230, 118, 0.45)" if float(row['close']) >= float(row['open']) else "rgba(255, 82, 82, 0.45)"
        })
        if not np.isnan(row['ema20']):
            ema_data.append({
                "time": t_val,
                "value": round(float(row['ema20']), 2)
            })

        # 區間聚合
        if is_e and not in_ext:
            in_ext = True
            ext_start = t_val
        elif not is_e and in_ext:
            in_ext = False
            ext_ranges.append({"start": ext_start, "end": df.iloc[idx-1]['time_val']})
            
    if in_ext:
        ext_ranges.append({"start": ext_start, "end": df.iloc[-1]['time_val']})

    candles_json = json.dumps(candles_data)
    volume_json = json.dumps(volume_data)
    ema_json = json.dumps(ema_data)
    ext_ranges_json = json.dumps(ext_ranges)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body {{ margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; position: relative; }}
            #tv_chart_container {{ width: 100%; height: 560px; position: relative; }}
            #shading_canvas {{ position: absolute; top: 0; left: 0; width: 100%; height: 560px; pointer-events: none; z-index: 1; }}
        </style>
    </head>
    <body>
        <div id="tv_chart_container">
            <canvas id="shading_canvas"></canvas>
        </div>
        <script>
            const container = document.getElementById('tv_chart_container');
            const shadingCanvas = document.getElementById('shading_canvas');
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
                    scaleMargins: {{ top: 0.1, bottom: {0.25 if show_vol else 0.1} }},
                }},
                timeScale: {{
                    borderColor: '#30363d',
                    timeVisible: true,
                    secondsVisible: false,
                }},
                handleScroll: {{ mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }},
                handleScale: {{ axisPressedMouseMove: true, mouseWheel: true, pinch: true }},
            }});

            const candleSeries = chart.addCandlestickSeries({{
                upColor: '#00E676',
                downColor: '#FF5252',
                borderVisible: false,
                wickUpColor: '#00E676',
                wickDownColor: '#FF5252',
            }});
            candleSeries.setData({candles_json});

            if ({str(show_vol).lower()}) {{
                const volumeSeries = chart.addHistogramSeries({{
                    priceFormat: {{ type: 'volume' }},
                    priceScaleId: '',
                    scaleMargins: {{ top: 0.8, bottom: 0 }},
                }});
                volumeSeries.setData({volume_json});
            }}

            if ({str(show_ema).lower()}) {{
                const emaSeries = chart.addLineSeries({{
                    color: '#FFD600',
                    lineWidth: 2,
                    title: 'EMA20',
                }});
                emaSeries.setData({ema_json});
            }}

            if ({str(show_sbr_rbs).lower()}) {{
                candleSeries.createPriceLine({{
                    price: {recent_high},
                    color: '#FF5252',
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: 'SBR 阻力',
                }});
                candleSeries.createPriceLine({{
                    price: {recent_low},
                    color: '#00E676',
                    lineWidth: 1,
                    lineStyle: LightweightCharts.LineStyle.Dashed,
                    axisLabelVisible: true,
                    title: 'RBS 支撐',
                }});
            }}

            // 繪製 Extended Hours 盤前/盤後半透明灰框遮罩 (TradingView 原生質感)
            const extRanges = {ext_ranges_json};
            const showExt = {str(show_ext).lower()};

            function drawExtendedHoursShading() {{
                const ctx = shadingCanvas.getContext('2d');
                shadingCanvas.width = container.clientWidth;
                shadingCanvas.height = container.clientHeight;
                ctx.clearRect(0, 0, shadingCanvas.width, shadingCanvas.height);

                if (!showExt || extRanges.length === 0) return;

                const timeScale = chart.timeScale();
                ctx.fillStyle = 'rgba(255, 255, 255, 0.04)';

                extRanges.forEach(rng => {{
                    const x1 = timeScale.timeToCoordinate(rng.start);
                    const x2 = timeScale.timeToCoordinate(rng.end);
                    if (x1 !== null && x2 !== null) {{
                        const left = Math.min(x1, x2) - 6;
                        const width = Math.abs(x2 - x1) + 12;
                        ctx.fillRect(left, 0, width, shadingCanvas.height);
                    }} else if (x1 !== null) {{
                        ctx.fillRect(x1 - 6, 0, 18, shadingCanvas.height);
                    }}
                }});
            }}

            chart.timeScale().subscribeVisibleTimeRangeChange(drawExtendedHoursShading);
            setTimeout(drawExtendedHoursShading, 100);

            window.addEventListener('resize', () => {{
                chart.applyOptions({{ width: container.clientWidth }});
                drawExtendedHoursShading();
            }});
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=580)

def render_chart_view(assets=None):
    default_code = "US.QQQ"
    if isinstance(assets, list) and len(assets) > 0:
        if isinstance(assets[0], dict) and 'code' in assets[0]:
            default_code = assets[0]['code']
        elif isinstance(assets[0], str):
            default_code = assets[0]
    render_lightweight_tv_chart(code=default_code)
