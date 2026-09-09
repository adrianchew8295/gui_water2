# 文件名: chart_view_plugin.py
# 職責: 渲染 QQQ 納指大盤中樞 (TradingView 原生 Extended Hours 分區遮罩 · 消除 HTML 外漏 · 自動標註 High/Low 極值)

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

def safe_py_val(v):
    """強制轉換為 Python 原生型別，杜絕 JSON 序列化報錯"""
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return float(v)
    return str(v)

def load_kline_safe(code: str, ktype: str = "1H", bars: int = 1500) -> pd.DataFrame:
    """加載本地數據並精確標註時段屬性 (04:00~09:30 PRE / 16:00~20:00 POST)"""
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
                        df['session_type'] = 'DAY'
                    else:
                        df['time_val'] = df['dt'].astype('int64') // 10**9
                        hours = df['dt'].dt.hour
                        minutes = df['dt'].dt.minute
                        time_mins = hours * 60 + minutes
                        
                        is_pre = (time_mins >= 240) & (time_mins < 570)
                        is_post = (time_mins >= 960) & (time_mins <= 1200)
                        df['is_ext'] = is_pre | is_post
                        df['session_type'] = np.where(is_pre, 'PRE', np.where(is_post, 'POST', 'RTH'))
                        
                    df['time_display'] = df['dt'].dt.strftime('%Y-%m-%d %H:%M')
                    return df[['time_val', 'time_display', 'open', 'high', 'low', 'close', 'volume', 'is_ext', 'session_type']]
            except Exception:
                pass
                
    return pd.DataFrame()

def render_lightweight_tv_chart(code: str = "US.QQQ", ktype: str = "1H", bars: int = 1500):
    """QQQ 納指中樞主圖入口"""
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
    last_session = str(df['session_type'].iloc[-1])
    
    ema20 = float(df['close'].ewm(span=20).mean().iloc[-1])
    recent_high = float(df['high'].tail(30).max())
    recent_low = float(df['low'].tail(30).min())

    pmh_val, pml_val = None, None
    if last_session == 'PRE':
        today_date = time_last[:10]
        df_today_pre = df[(df['time_display'].str.startswith(today_date)) & (df['session_type'] == 'PRE')]
        if not df_today_pre.empty:
            pmh_val = float(df_today_pre['high'].max())
            pml_val = float(df_today_pre['low'].min())

    session_badge = "<span style='color:#ffd600;'>🟡 PREMARKET (盤前)</span>" if last_session == 'PRE' else ("<span style='color:#00e5ff;'>🔵 AFTERMARKET (盤後)</span>" if last_session == 'POST' else "<span style='color:#00e676;'>🟢 REGULAR (常規盤)</span>")
    
    # 嚴格無縮排 HTML 字串，徹底杜絕程式碼外漏
    pmh_str = f"<span>🟡 PMH: <b style='color:#ffd600;'>${pmh_val:.2f}</b> | PML: <b style='color:#ffd600;'>${pml_val:.2f}</b></span>" if pmh_val else ""
    hud_html = (
        f'<div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; font-family: monospace;">'
        f'<div style="font-size: 15px; font-weight: bold; color: #58a6ff; display: flex; justify-content: space-between; align-items: center;">'
        f'<span>👑 {code} · {actual_ktype} 核心戰區 (全時段 Extended Hours 已對齊 · 滿載 {len(df)} 根)</span>'
        f'<span style="font-size: 13px;">時段: {session_badge} | 最新: {time_last} ET</span>'
        f'</div>'
        f'<div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 20px; font-size: 13px; color: #c9d1d9;">'
        f'<span>現價: <b style="color: #79c0ff;">${curr_close:.2f}</b></span>'
        f'<span>EMA20 生命線: <b style="color: #ffd600;">${ema20:.2f}</b></span>'
        f'<span>近期阻力 (SBR): <b style="color: #ff7b72;">${recent_high:.2f}</b></span>'
        f'<span>近期支撐 (RBS): <b style="color: #56d364;">${recent_low:.2f}</b></span>'
        f'{pmh_str}'
        f'<span>當根量能: <b style="color: #e040fb;">{curr_vol:,.0f}</b></span>'
        f'</div></div>'
    )
    st.markdown(hud_html, unsafe_allow_html=True)

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
    ext_ranges = []
    
    df['ema20'] = df['close'].ewm(span=20).mean()
    
    in_ext = False
    ext_start = None
    ext_type = None
    
    for idx, row in df.iterrows():
        t_val = safe_py_val(row['time_val'])
        is_e = bool(row['is_ext'])
        s_type = str(row['session_type'])
        
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

        if is_e and not in_ext:
            in_ext = True
            ext_start = t_val
            ext_type = "PRE" if s_type == "PRE" else "POST"
        elif not is_e and in_ext:
            in_ext = False
            prev_val = safe_py_val(df.iloc[idx - 1]['time_val'])
            ext_ranges.append({"start": ext_start, "end": prev_val, "type": ext_type})
            
    if in_ext and ext_start is not None:
        last_val = safe_py_val(df.iloc[-1]['time_val'])
        ext_ranges.append({"start": ext_start, "end": last_val, "type": ext_type})

    # 計算最近視窗的最高/最低點打點 (對齊 TradingView 原生 High/Low Marker)
    markers_data = []
    if len(df) >= 10:
        recent_slice = df.tail(60).reset_index(drop=True)
        max_idx = recent_slice['high'].idxmax()
        min_idx = recent_slice['low'].idxmin()
        
        row_max = recent_slice.iloc[max_idx]
        row_min = recent_slice.iloc[min_idx]
        
        markers_data.append({
            "time": safe_py_val(row_max['time_val']),
            "position": "aboveBar",
            "color": "#818cf8",
            "shape": "arrowDown",
            "text": f"High: ${float(row_max['high']):.2f}"
        })
        markers_data.append({
            "time": safe_py_val(row_min['time_val']),
            "position": "belowBar",
            "color": "#818cf8",
            "shape": "arrowUp",
            "text": f"Low: ${float(row_min['low']):.2f}"
        })

    candles_json = json.dumps(candles_data, default=safe_py_val)
    volume_json = json.dumps(volume_data, default=safe_py_val)
    ema_json = json.dumps(ema_data, default=safe_py_val)
    ext_ranges_json = json.dumps(ext_ranges, default=safe_py_val)
    markers_json = json.dumps(markers_data, default=safe_py_val)

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8" />
        <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
        <style>
            body {{ margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
            #chart_wrapper {{ position: relative; width: 100%; height: 560px; background-color: #0d1117; overflow: hidden; }}
            #bg_canvas {{ position: absolute; top: 0; left: 0; width: 100%; height: 560px; z-index: 0; pointer-events: none; }}
            #tv_chart_container {{ position: absolute; top: 0; left: 0; width: 100%; height: 560px; z-index: 1; }}
        </style>
    </head>
    <body>
        <div id="chart_wrapper">
            <canvas id="bg_canvas"></canvas>
            <div id="tv_chart_container"></div>
        </div>
        <script>
            const container = document.getElementById('tv_chart_container');
            const bgCanvas = document.getElementById('bg_canvas');
            
            // 核心：將圖表畫布設為透明 (transparent)，底層的 Extended Hours 遮罩才能 100% 顯現
            const chart = LightweightCharts.createChart(container, {{
                layout: {{
                    background: {{ type: 'solid', color: 'transparent' }},
                    textColor: '#8b949e',
                    fontSize: 12,
                }},
                grid: {{
                    vertLines: {{ color: 'rgba(255, 255, 255, 0.03)' }},
                    horzLines: {{ color: 'rgba(255, 255, 255, 0.03)' }},
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

            // 標註最高價與最低價極值點
            const markers = {markers_json};
            if (markers.length > 0) {{
                candleSeries.setMarkers(markers);
            }}

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

            {f"""
            candleSeries.createPriceLine({{
                price: {pmh_val},
                color: '#FFD600',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: 'PMH (盤前高)',
            }});
            candleSeries.createPriceLine({{
                price: {pml_val},
                color: '#FFD600',
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dotted,
                axisLabelVisible: true,
                title: 'PML (盤前低)',
            }});
            """ if pmh_val else ""}

            // 繪製 TradingView 原生風格 Extended Hours 遮罩 (底層畫布注入)
            const extRanges = {ext_ranges_json};
            const showExt = {str(show_ext).lower()};

            function drawExtendedHoursBackdrop() {{
                const ctx = bgCanvas.getContext('2d');
                const w = container.clientWidth;
                const h = container.clientHeight;
                bgCanvas.width = w;
                bgCanvas.height = h;

                // 1. 常規交易盤純黑底色
                ctx.fillStyle = '#0d1117';
                ctx.fillRect(0, 0, w, h);

                if (!showExt || !extRanges || extRanges.length === 0) return;

                const timeScale = chart.timeScale();
                const visibleRange = timeScale.getVisibleRange();

                extRanges.forEach(rng => {{
                    let x1 = timeScale.timeToCoordinate(rng.start);
                    let x2 = timeScale.timeToCoordinate(rng.end);

                    if (visibleRange) {{
                        if (rng.end < visibleRange.from || rng.start > visibleRange.to) {{
                            return;
                        }}
                        if (x1 === null) x1 = 0;
                        if (x2 === null) x2 = w;
                    }}

                    if (x1 !== null && x2 !== null) {{
                        const left = Math.max(0, Math.min(x1, x2) - 3);
                        const width = Math.min(w - left, Math.abs(x2 - x1) + 6);

                        // 2. 鋪設清晰可見的淺藍灰透明遮罩 (對齊 TradingView)
                        ctx.fillStyle = 'rgba(56, 189, 248, 0.06)';
                        ctx.fillRect(left, 0, width, h);

                        // 3. 繪製時段邊界垂直虛線
                        ctx.strokeStyle = 'rgba(56, 189, 248, 0.22)';
                        ctx.lineWidth = 1;
                        ctx.setLineDash([4, 4]);
                        ctx.beginPath();
                        ctx.moveTo(left, 0); ctx.lineTo(left, h);
                        ctx.moveTo(left + width, 0); ctx.lineTo(left + width, h);
                        ctx.stroke();
                        ctx.setLineDash([]);

                        // 4. 時段頂部文字徽章
                        ctx.fillStyle = 'rgba(56, 189, 248, 0.75)';
                        ctx.font = 'bold 11px monospace';
                        const lbl = rng.type === 'PRE' ? '🌙 PRE-MARKET' : '🌙 POST-MARKET';
                        ctx.fillText(lbl, left + 8, 20);
                    }}
                }});
            }}

            chart.timeScale().subscribeVisibleTimeRangeChange(drawExtendedHoursBackdrop);
            setTimeout(drawExtendedHoursBackdrop, 60);

            window.addEventListener('resize', () => {{
                chart.applyOptions({{ width: container.clientWidth }});
                drawExtendedHoursBackdrop();
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
