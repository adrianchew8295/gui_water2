# 文件名: chart_view_plugin.py
# 职责: TradingView 原生 Lightweight Charts 渲染插件 (Canvas 硬件加速 / 滚轮缩放 / 视口拖拽 / 双图联动)

import os
import json
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")

class ChartViewPlugin:
    @staticmethod
    def render_chart(code: str, ktype: str = "5M", bar_count: int = 100):
        clean_name = code.replace(".", "_")
        csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype}.csv")

        if not os.path.exists(csv_path):
            st.warning(f"⚠️ 未检测到本地数据文件: {csv_path}，请先点击侧边栏同步数据。")
            return

        try:
            df = pd.read_csv(csv_path)
            if df.empty:
                st.warning("⚠️ 数据文件为空。")
                return

            df.columns = [c.lower().strip() for c in df.columns]
            df = df.tail(bar_count).reset_index(drop=True)

            # 数据序列化为 TradingView 原生格式
            candles = []
            volumes = []

            for _, row in df.iterrows():
                time_str = str(row['time_key'])
                # 日线使用 YYYY-MM-DD，分钟线使用 Unix 时间戳
                if ktype == "DAY":
                    t_val = time_str[:10]
                else:
                    try:
                        t_val = int(pd.to_datetime(time_str).timestamp())
                    except Exception:
                        t_val = time_str

                o = float(row['open'])
                h = float(row['high'])
                l = float(row['low'])
                c = float(row['close'])
                v = float(row.get('volume', 0))

                candles.append({"time": t_val, "open": o, "high": h, "low": l, "close": c})
                vol_color = "rgba(0, 230, 118, 0.5)" if c >= o else "rgba(255, 82, 82, 0.5)"
                volumes.append({"time": t_val, "value": v, "color": vol_color})

            candles_json = json.dumps(candles)
            volumes_json = json.dumps(volumes)

            # 嵌入 TradingView 原生 Lightweight Charts HTML
            html_code = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8" />
                <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
                <style>
                    body {{ margin: 0; padding: 0; background-color: #0d1117; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
                    #chart_container {{ width: 100%; height: 560px; }}
                </style>
            </head>
            <body>
                <div id="chart_container"></div>
                <script>
                    const chartContainer = document.getElementById('chart_container');
                    const chart = LightweightCharts.createChart(chartContainer, {{
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

                    // 1. 主图：K 线蜡烛图 (原生 TradingView 绿涨红跌)
                    const mainSeries = chart.addCandlestickSeries({{
                        upColor: '#00E676',
                        downColor: '#FF5252',
                        borderVisible: false,
                        wickUpColor: '#00E676',
                        wickDownColor: '#FF5252',
                    }});
                    mainSeries.setData({candles_json});

                    // 2. 副图：底部成交量直方图
                    const volumeSeries = chart.addHistogramSeries({{
                        priceFormat: {{ type: 'volume' }},
                        priceScaleId: '',
                        scaleMargins: {{ top: 0.8, bottom: 0 }},
                    }});
                    volumeSeries.setData({volumes_json});

                    // 窗口自适应大小调整
                    window.addEventListener('resize', () => {{
                        chart.applyOptions({{ width: chartContainer.clientWidth }});
                    }});
                </script>
            </body>
            </html>
            """

            components.html(html_code, height=580)

        except Exception as e:
            st.error(f"TradingView 图表加载失败: {str(e)}")

chart_plugin = ChartViewPlugin()
