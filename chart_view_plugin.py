# 文件名: chart_view_plugin.py
# 职责: 渲染 TradingView 风格图表 (含 Extended Hours 盘前盘后暗色遮罩绘制 + 完整日期时间格式化 + 攻防线)

import os
import datetime
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import pytz
from radar_engine import compute_radar_metrics
from data_engine import hub_engine, get_active_session_info

tz_ny = pytz.timezone("America/New_York")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")

def check_and_auto_heal(code: str):
    clean_name = code.replace(".", "_")
    csv_5m = os.path.join(DATA_DIR, f"{clean_name}_5M.csv")
    session_id, _, now_ny = get_active_session_info()
    
    if session_id in ["CLOSED_WEEKEND", "CLOSED_NIGHT"]:
        return

    need_heal = False
    if not os.path.exists(csv_5m):
        need_heal = True
    else:
        try:
            df = pd.read_csv(csv_5m)
            if df.empty or 'time_key' not in df.columns:
                need_heal = True
            else:
                last_time_str = df.iloc[-1]['time_key']
                last_dt = pd.to_datetime(last_time_str).tz_localize(tz_ny)
                gap_minutes = (now_ny - last_dt).total_seconds() / 60.0
                if gap_minutes > 5.5:
                    need_heal = True
        except Exception:
            need_heal = True

    if need_heal:
        hub_engine.auto_heal_today_data(code)

def render_lightweight_tv_chart(code: str, ktype_str: str = "5M", bars_count: int = 120):
    check_and_auto_heal(code)

    clean_name = code.replace(".", "_")
    csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype_str}.csv")

    if not os.path.exists(csv_path):
        st.warning(f"⚪ 暂无 {code} {ktype_str} 本地数据，正在同步中...")
        return

    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.lower().strip() for c in df.columns]
        if df.empty or 'time_key' not in df.columns:
            st.warning(f"⚪ {code} 数据为空。")
            return

        df['dt'] = pd.to_datetime(df['time_key'])
        df = df.sort_values('dt').tail(bars_count).copy()

        candles_data = []
        volume_data = []

        for _, row in df.iterrows():
            ts = int(row['dt'].replace(tzinfo=pytz.UTC).timestamp())
            o = float(row.get('open', 0.0))
            h = float(row.get('high', 0.0))
            l = float(row.get('low', 0.0))
            c = float(row.get('close', 0.0))
            v = float(row.get('volume', 0.0))

            t_ny = row['dt'].time()
            is_ext = (datetime.time(4, 0) <= t_ny < datetime.time(9, 30)) or (datetime.time(16, 0) <= t_ny <= datetime.time(20, 0))

            candles_data.append({
                "time": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "is_ext": is_ext
            })

            # 盘前盘后量能柱颜色稍暗区分，常规盘明亮
            if is_ext:
                vol_color = "rgba(0, 200, 100, 0.25)" if c >= o else "rgba(220, 50, 50, 0.25)"
            else:
                vol_color = "rgba(0, 230, 118, 0.6)" if c >= o else "rgba(255, 82, 82, 0.6)"

            volume_data.append({
                "time": ts,
                "value": v,
                "color": vol_color
            })

        metrics = compute_radar_metrics(code, live_price=candles_data[-1]['close'] if candles_data else 0.0)

        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                * {{ box-sizing: border-box; }}
                body {{
                    margin: 0;
                    padding: 0;
                    background-color: #06090E;
                    color: #CBD5E1;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    overflow: hidden;
                }}
                #wrapper {{
                    position: relative;
                    width: 100%;
                    height: 540px;
                }}
                #shading-canvas {{
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 540px;
                    pointer-events: none;
                    z-index: 1;
                }}
                #chart-container {{
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 540px;
                    z-index: 2;
                }}
            </style>
        </head>
        <body>
            <div id="wrapper">
                <canvas id="shading-canvas"></canvas>
                <div id="chart-container"></div>
            </div>
            <script>
                const container = document.getElementById('chart-container');
                const canvas = document.getElementById('shading-canvas');
                const ctx = canvas.getContext('2d');

                function resizeCanvas() {{
                    canvas.width = container.clientWidth;
                    canvas.height = container.clientHeight;
                }}
                resizeCanvas();

                const chart = LightweightCharts.createChart(container, {{
                    layout: {{
                        background: {{ color: 'transparent' }},
                        textColor: '#94A3B8',
                    }},
                    grid: {{
                        vertLines: {{ color: '#131B2E' }},
                        horzLines: {{ color: '#131B2E' }},
                    }},
                    crosshair: {{
                        mode: LightweightCharts.CrosshairMode.Normal,
                    }},
                    rightPriceScale: {{
                        borderColor: '#1E293B',
                        scaleMargins: {{
                            top: 0.1,
                            bottom: 0.25,
                        }},
                    }},
                    timeScale: {{
                        borderColor: '#1E293B',
                        timeVisible: true,
                        secondsVisible: false,
                    }},
                    localization: {{
                        timeFormatter: (ts) => {{
                            const d = new Date(ts * 1000);
                            const pad = (n) => String(n).padStart(2, '0');
                            return `${{d.getUTCFullYear()}}-${{pad(d.getUTCMonth()+1)}}-${{pad(d.getUTCDate())}} ${{pad(d.getUTCHours())}}:${{pad(d.getUTCMinutes())}}`;
                        }}
                    }}
                }});

                const candleSeries = chart.addCandlestickSeries({{
                    upColor: '#00E676',
                    downColor: '#FF5252',
                    borderVisible: false,
                    wickUpColor: '#00E676',
                    wickDownColor: '#FF5252',
                }});
                const rawCandles = {json.dumps(candles_data)};
                candleSeries.setData(rawCandles);

                const volumeSeries = chart.addHistogramSeries({{
                    priceFormat: {{ type: 'volume' }},
                    priceScaleId: '',
                    scaleMargins: {{
                        top: 0.8,
                        bottom: 0,
                    }},
                }});
                const rawVolumes = {json.dumps(volume_data)};
                volumeSeries.setData(rawVolumes);

                // 攻防线
                const pmh = {metrics['pmh']};
                const pml = {metrics['pml']};
                const pdh = {metrics['pdh']};
                const pdl = {metrics['pdl']};
                const ema = {metrics['ema20_1h']};

                if (pmh > 0) candleSeries.createPriceLine({{ price: pmh, color: '#FACC15', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'PMH (盘前高)' }});
                if (pml > 0) candleSeries.createPriceLine({{ price: pml, color: '#FACC15', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, axisLabelVisible: true, title: 'PML (盘前低)' }});
                if (pdh > 0) candleSeries.createPriceLine({{ price: pdh, color: '#FF5252', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'PDH (昨高)' }});
                if (pdl > 0) candleSeries.createPriceLine({{ price: pdl, color: '#00E676', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: true, title: 'PDL (昨低)' }});
                if (ema > 0) candleSeries.createPriceLine({{ price: ema, color: '#38BDF8', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true, title: '1H EMA20' }});

                // 绘制 Extended Hours (盘前盘后) 专属半透明背景遮罩
                function drawExtendedShading() {{
                    resizeCanvas();
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                    const timeScale = chart.timeScale();
                    
                    let extStartIdx = null;
                    for (let i = 0; i < rawCandles.length; i++) {{
                        const c = rawCandles[i];
                        if (c.is_ext) {{
                            if (extStartIdx === null) extStartIdx = i;
                        }} else {{
                            if (extStartIdx !== null) {{
                                fillShade(extStartIdx, i - 1);
                                extStartIdx = null;
                            }}
                        }}
                    }}
                    if (extStartIdx !== null) {{
                        fillShade(extStartIdx, rawCandles.length - 1);
                    }}

                    function fillShade(fromIdx, toIdx) {{
                        const x1 = timeScale.timeToCoordinate(rawCandles[fromIdx].time);
                        const x2 = timeScale.timeToCoordinate(rawCandles[toIdx].time);
                        if (x1 !== null && x2 !== null) {{
                            const startX = Math.min(x1, x2) - 3;
                            const width = Math.abs(x2 - x1) + 6;
                            ctx.fillStyle = 'rgba(255, 255, 255, 0.04)';
                            ctx.fillRect(startX, 0, width, canvas.height - 30);
                            ctx.fillStyle = 'rgba(148, 163, 184, 0.4)';
                            ctx.font = '10px monospace';
                            ctx.fillText('EXT HOURS', startX + 5, 18);
                        }}
                    }}
                }}

                chart.timeScale().fitContent();
                setTimeout(drawExtendedShading, 100);
                chart.timeScale().subscribeVisibleTimeRangeChange(drawExtendedShading);
                window.addEventListener('resize', drawExtendedShading);
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=560, scrolling=False)

    except Exception as e:
        st.error(f"❌ 图表渲染异常: {str(e)}")

def render_chart_view(assets):
    code_list = [a['code'] for a in assets]
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        sel_code = st.selectbox("选择穿透标的", code_list, index=0, key="chart_plugin_code_sel")
    with c2:
        sel_ktype = st.selectbox("选择周期", ["5M", "1H", "DAY"], index=0, key="chart_plugin_ktype_sel")
    with c3:
        sel_bars = st.slider("显示柱数", 30, 300, 120, step=10, key="chart_plugin_bars_sel")

    render_lightweight_tv_chart(sel_code, sel_ktype, sel_bars)
