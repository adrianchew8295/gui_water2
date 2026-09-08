# 文件名: macro_radar_plugin.py
# 職責: 渲染專業 Murphy 日線技術圖表 (300~500 根日 K 線 + 局部精準通道 + S/R 與 Major Support + 艾略特波浪 HUD)

import os
import json
import datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from data_engine import hub_engine
from macro_radar_engine import compute_murphy_technicals

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")

def render_murphy_daily_chart(code: str, bars_count: int = 300):
    clean_name = code.replace(".", "_")
    csv_path = os.path.join(DATA_DIR, f"{clean_name}_DAY.csv")

    if not os.path.exists(csv_path):
        st.warning(f"⚪ 正在獲取 {code} 日線歷史數據...")
        return

    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.lower().strip() for c in df.columns]
        if df.empty or 'time_key' not in df.columns:
            st.warning(f"⚪ {code} 日線數據為空。")
            return

        df['dt'] = pd.to_datetime(df['time_key'])
        df = df.sort_values('dt').tail(bars_count).copy()

        tech_res = compute_murphy_technicals(df)

        candles_data = []
        for _, row in df.iterrows():
            t_str = row['dt'].strftime('%Y-%m-%d')
            candles_data.append({
                "time": t_str,
                "open": float(row.get('open', 0.0)),
                "high": float(row.get('high', 0.0)),
                "low": float(row.get('low', 0.0)),
                "close": float(row.get('close', 0.0))
            })

        last_c = candles_data[-1] if candles_data else {}
        trend_status_str = "🟢 上升通道" if tech_res.get('trend_type') == 'UPTREND' else ("🔴 下降通道" if tech_res.get('trend_type') == 'DOWNTREND' else "⚪ 區間箱體")

        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                * {{ box-sizing: border-box; }}
                body {{
                    margin: 0; padding: 0;
                    background-color: #06090E; color: #CBD5E1;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                    overflow: hidden;
                }}
                #wrapper {{ position: relative; width: 100%; height: 600px; }}
                #hud-panel {{
                    position: absolute; top: 10px; left: 14px; z-index: 10;
                    font-size: 13px; font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
                    background: rgba(15, 23, 42, 0.92); padding: 8px 16px; border-radius: 8px;
                    border: 1px solid #1E293B; pointer-events: none; line-height: 1.6;
                }}
                #chart-container {{ position: absolute; top: 0; left: 0; width: 100%; height: 600px; z-index: 2; }}
            </style>
        </head>
        <body>
            <div id="wrapper">
                <div id="hud-panel">
                    <b>📡 {code} · 純日線技術幾何通道 (John J. Murphy 體系)</b><br/>
                    狀態: <b>{trend_status_str}</b> &nbsp;|&nbsp; <b>{tech_res.get('wave_label', '')}</b><br/>
                    現價: <b style="color:#38BDF8;">${last_c.get('close', 0.0):.2f}</b> &nbsp;|&nbsp; 
                    阻力 (Resistance): <b style="color:#FF5252;">${tech_res.get('immediate_resistance', 0.0):.2f}</b> &nbsp;|&nbsp; 
                    支撐 (Support): <b style="color:#00E676;">${tech_res.get('immediate_support', 0.0):.2f}</b>
                </div>
                <div id="chart-container"></div>
            </div>
            <script>
                const container = document.getElementById('chart-container');
                const chart = LightweightCharts.createChart(container, {{
                    layout: {{ background: {{ color: 'transparent' }}, textColor: '#94A3B8' }},
                    grid: {{ vertLines: {{ color: '#131B2E' }}, horzLines: {{ color: '#131B2E' }} }},
                    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                    rightPriceScale: {{ borderColor: '#1E293B', scaleMargins: {{ top: 0.1, bottom: 0.1 }} }},
                    timeScale: {{ borderColor: '#1E293B', fixLeftEdge: false, rightOffset: 8 }}
                }});

                const candleSeries = chart.addCandlestickSeries({{
                    upColor: '#00E676', downColor: '#FF5252', borderVisible: false,
                    wickUpColor: '#00E676', wickDownColor: '#FF5252'
                }});
                const rawCandles = {json.dumps(candles_data)};
                candleSeries.setData(rawCandles);

                // 1. 標註 Major Support (粗青色底線)
                const majorSup = {tech_res.get('major_support', 0.0)};
                if (majorSup > 0) {{
                    candleSeries.createPriceLine({{
                        price: majorSup, color: '#06B6D4', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid,
                        axisLabelVisible: true, title: `⭐ MAJOR SUPPORT: $${{majorSup.toFixed(2)}}`
                    }});
                }}

                // 2. 標註 S/R 水平線
                const immRes = {tech_res.get('immediate_resistance', 0.0)};
                const immSup = {tech_res.get('immediate_support', 0.0)};
                if (immRes > 0) {{
                    candleSeries.createPriceLine({{
                        price: immRes, color: '#FF5252', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true, title: `RES: $${{immRes.toFixed(2)}}`
                    }});
                }}
                if (immSup > 0) {{
                    candleSeries.createPriceLine({{
                        price: immSup, color: '#00E676', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true, title: `SUP: $${{immSup.toFixed(2)}}`
                    }});
                }}

                // 3. 繪製局部段落趨勢線 (從起點連至最新，絕不貫穿全屏)
                const tLines = {json.dumps(tech_res.get('trend_lines', []))};
                tLines.forEach(line => {{
                    const lineSeries = chart.addLineSeries({{
                        color: line.color, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Solid,
                        crosshairMarkerVisible: false
                    }});
                    lineSeries.setData([
                        {{ time: line.from_time, value: line.from_price }},
                        {{ time: line.to_time, value: line.to_price }}
                    ]);
                }});

                // 4. 繪製精準平行通道軌道線
                const cLines = {json.dumps(tech_res.get('channel_lines', []))};
                cLines.forEach(line => {{
                    const channelSeries = chart.addLineSeries({{
                        color: line.color, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dashed,
                        crosshairMarkerVisible: false
                    }});
                    channelSeries.setData([
                        {{ time: line.from_time, value: line.from_price }},
                        {{ time: line.to_time, value: line.to_price }}
                    ]);
                }});

                chart.timeScale().fitContent();
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=620, scrolling=False)

    except Exception as e:
        st.error(f"❌ 雷達日線渲染異常: {str(e)}")

def render_macro_radar_view(assets):
    st.markdown("### 📡 12 檔核心宏觀雷達 · 純日線技術幾何畫布")
    
    code_list = [a['code'] for a in assets]
    col1, col2 = st.columns([3, 2])
    with col1:
        sel_code = st.selectbox("🎯 選擇穿透標的", code_list, index=0, key="macro_radar_code_select")
    with col2:
        bars_count = st.slider("📅 歷史日 K 深度", min_value=100, max_value=500, value=300, step=50, key="macro_radar_bars_slider")

    render_murphy_daily_chart(sel_code, bars_count=bars_count)
