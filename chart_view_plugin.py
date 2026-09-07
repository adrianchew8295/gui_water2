# 文件名: chart_view_plugin.py
# 职责: TradingView Lightweight Charts 图表插件 (全时段盘前/盘后背景阴影遮罩 + 滚轮缩放 + 拖拽记忆 + 涨跌双色)

import os
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import pytz

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")
tz_ny = pytz.timezone("America/New_York")

class ChartViewPlugin:
    @staticmethod
    def render_chart(code: str, ktype: str = "5M", bar_count: int = 120):
        clean_name = code.replace(".", "_")
        csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype}.csv")

        if not os.path.exists(csv_path):
            st.warning(f"⚠️ 未检测到本地数据文件: {csv_path}，请先在侧边栏同步数据。")
            return

        try:
            df = pd.read_csv(csv_path)
            if df.empty:
                st.warning("⚠️ 数据文件为空。")
                return

            df.columns = [c.lower().strip() for c in df.columns]
            df = df.tail(bar_count).reset_index(drop=True)

            candles = []
            volumes = []
            session_ranges = []  # 记录盘前/盘后的起止时间戳，用于绘制背景阴影
            is_crypto = code.startswith("CC.")

            current_session_start = None

            for idx, row in df.iterrows():
                time_str = str(row['time_key'])
                
                # 时间戳解析与美东时区识别
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
                        # 04:00 - 09:30 (盘前) 或 16:00 - 20:00 (盘后)
                        is_extended = (4 <= hour < 9) or (hour == 9 and minute < 30) or (16 <= hour < 20)

                o = float(row['open'])
                h = float(row['high'])
                l = float(row['low'])
                c = float(row['close'])
                v = float(row.get('volume', 0))

                candles.append({"time": t_val, "open": o, "high": h, "low": l, "close": c})
                vol_color = "rgba(0, 230, 118, 0.6)" if c >= o else "rgba(255, 82, 82, 0.6)"
                volumes.append({"time": t_val, "value": v, "color": vol_color})

                # 计算盘前盘后连续区间的起止
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

            # HTML + Lightweight Charts + Canvas 背景阴影遮罩
            html_code = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8" />
                <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
                <style>
                    body {{ margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; overflow: hidden; }}
                    #wrapper {{ position: relative; width: 100%; height: 560px; }}
                    #chart_container {{ width: 100%; height: 100%; position: absolute; z-index: 2; }}
                    #shading_canvas {{ width: 100%; height: 100%; position: absolute; top: 0; left: 0; z-index: 1; pointer-events: none; }}
                </style>
            </head>
            <body>
                <div id="wrapper">
                    <canvas id="shading_canvas"></canvas>
                    <div id="chart_container"></div>
                </div>
                <script>
                    const wrapper = document.getElementById('wrapper');
                    const container = document.getElementById('chart_container');
                    const canvas = document.getElementById('shading_canvas');
                    const ctx = canvas.getContext('2d');

                    function resizeCanvas() {{
                        canvas.width = wrapper.clientWidth;
                        canvas.height = wrapper.clientHeight;
                    }}
                    resizeCanvas();

                    const chart = LightweightCharts.createChart(container, {{
                        layout: {{
                            background: {{ type: 'solid', color: 'transparent' }},
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
                            scaleMargins: {{ top: 0.1, bottom: 0.25 }},
                        }},
                        timeScale: {{
                            borderColor: '#30363d',
                            timeVisible: true,
                            secondsVisible: false,
                        }},
                        handleScroll: {{ mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true, vertTouchDrag: true }},
                        handleScale: {{ axisPressedMouseMove: true, mouseWheel: true, pinch: true }},
                    }});

                    const mainSeries = chart.addCandlestickSeries({{
                        upColor: '#00E676',
                        downColor: '#FF5252',
                        borderVisible: false,
                        wickUpColor: '#00E676',
                        wickDownColor: '#FF5252',
                    }});
                    mainSeries.setData({candles_json});

                    const volumeSeries = chart.addHistogramSeries({{
                        priceFormat: {{ type: 'volume' }},
                        priceScaleId: '',
                        scaleMargins: {{ top: 0.8, bottom: 0 }},
                    }});
                    volumeSeries.setData({volumes_json});

                    const sessionRanges = {sessions_json};

                    // 绘制盘前 / 盘后半透明阴影遮罩
                    function drawShading() {{
                        ctx.clearRect(0, 0, canvas.width, canvas.height);
                        const timeScale = chart.timeScale();
                        ctx.fillStyle = 'rgba(255, 255, 255, 0.04)';

                        for (const s of sessionRanges) {{
                            const x1 = timeScale.timeToCoordinate(s.start);
                            const x2 = timeScale.timeToCoordinate(s.end);

                            if (x1 !== null && x2 !== null) {{
                                const left = Math.min(x1, x2);
                                const width = Math.abs(x2 - x1);
                                ctx.fillRect(left, 0, width, canvas.height);
                            }}
                        }}
                    }}

                    chart.timeScale().subscribeVisibleTimeRangeChange(drawShading);
                    chart.timeScale().subscribeVisibleLogicalRangeChange(drawShading);
                    setTimeout(drawShading, 100);

                    window.addEventListener('resize', () => {{
                        resizeCanvas();
                        chart.applyOptions({{ width: wrapper.clientWidth }});
                        drawShading();
                    }});
                </script>
            </body>
            </html>
            """

            components.html(html_code, height=580)

        except Exception as e:
            st.error(f"TradingView 图表加载失败: {str(e)}")

chart_plugin = ChartViewPlugin()
