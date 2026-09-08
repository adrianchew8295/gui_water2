# 文件名: chart_view_plugin.py
# 職責: 渲染 TradingView Lightweight Charts (含出圖前缺口自動探測與靜默 Auto-Heal 補齊)

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
    """
    探測本地 5M CSV 是否存在時間缺口 (落後當前美東時間超過 5 分鐘)
    若有缺口，自動觸發靜默 Auto-Heal 補齊
    """
    clean_name = code.replace(".", "_")
    csv_5m = os.path.join(DATA_DIR, f"{clean_name}_5M.csv")
    
    session_id, _, now_ny = get_active_session_info()
    
    # 非交易時段不強制報警
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
                
                # 如果距離當前時間超過 5.5 分鐘，說明少拿了最新收盤柱
                if gap_minutes > 5.5:
                    need_heal = True
        except Exception:
            need_heal = True

    if need_heal:
        hub_engine.auto_heal_today_data(code)

def render_lightweight_tv_chart(code: str, ktype_str: str = "5M", bars_count: int = 120):
    """
    渲染嵌入式 TradingView Lightweight Charts
    包含: 出圖前主動缺口修復、主圖 K 線、1H EMA20、PDH/PDL、PMH/PML 水平線、成交量副圖
    """
    # 1. 出圖前主動自癒補齊
    check_and_auto_heal(code)

    clean_name = code.replace(".", "_")
    csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype_str}.csv")

    if not os.path.exists(csv_path):
        st.warning(f"⚪ 暫無 {code} {ktype_str} 本地數據，正在嘗試抓取中...")
        return

    try:
        df = pd.read_csv(csv_path)
        df.columns = [c.lower().strip() for c in df.columns]
        if df.empty or 'time_key' not in df.columns:
            st.warning(f"⚪ {code} 數據為空。")
            return

        df['dt'] = pd.to_datetime(df['time_key'])
        df = df.sort_values('dt').tail(bars_count).copy()

        # 構建 K 線數據與成交量數據列表 (UNIX 秒級時間戳)
        candles_data = []
        volume_data = []

        for _, row in df.iterrows():
            ts = int(row['dt'].replace(tzinfo=pytz.UTC).timestamp())
            o = float(row.get('open', 0.0))
            h = float(row.get('high', 0.0))
            l = float(row.get('low', 0.0))
            c = float(row.get('close', 0.0))
            v = float(row.get('volume', 0.0))

            candles_data.append({
                "time": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c
            })

            vol_color = "rgba(0, 230, 118, 0.45)" if c >= o else "rgba(255, 82, 82, 0.45)"
            volume_data.append({
                "time": ts,
                "value": v,
                "color": vol_color
            })

        # 計算攻防線指標
        metrics = compute_radar_metrics(code, live_price=candles_data[-1]['close'] if candles_data else 0.0)

        html_code = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8" />
            <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    background-color: #06090E;
                    color: #CBD5E1;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }}
                #chart-container {{
                    width: 100%;
                    height: 520px;
                }}
            </style>
        </head>
        <body>
            <div id="chart-container"></div>
            <script>
                const container = document.getElementById('chart-container');
                const chart = LightweightCharts.createChart(container, {{
                    layout: {{
                        background: {{ color: '#06090E' }},
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
                }});

                const candleSeries = chart.addCandlestickSeries({{
                    upColor: '#00E676',
                    downColor: '#FF5252',
                    borderVisible: false,
                    wickUpColor: '#00E676',
                    wickDownColor: '#FF5252',
                }});
                const candleData = {json.dumps(candles_data)};
                candleSeries.setData(candleData);

                const volumeSeries = chart.addHistogramSeries({{
                    priceFormat: {{ type: 'volume' }},
                    priceScaleId: '',
                    scaleMargins: {{
                        top: 0.8,
                        bottom: 0,
                    }},
                }});
                const volData = {json.dumps(volume_data)};
                volumeSeries.setData(volData);

                const pmh = {metrics['pmh']};
                const pml = {metrics['pml']};
                const pdh = {metrics['pdh']};
                const pdl = {metrics['pdl']};
                const ema = {metrics['ema20_1h']};

                if (pmh > 0) {{
                    candleSeries.createPriceLine({{
                        price: pmh,
                        color: '#FACC15',
                        lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'PMH (盤前高)',
                    }});
                }}
                if (pml > 0) {{
                    candleSeries.createPriceLine({{
                        price: pml,
                        color: '#FACC15',
                        lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Dashed,
                        axisLabelVisible: true,
                        title: 'PML (盤前低)',
                    }});
                }}
                if (pdh > 0) {{
                    candleSeries.createPriceLine({{
                        price: pdh,
                        color: '#FF5252',
                        lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Solid,
                        axisLabelVisible: true,
                        title: 'PDH (昨高)',
                    }});
                }}
                if (pdl > 0) {{
                    candleSeries.createPriceLine({{
                        price: pdl,
                        color: '#00E676',
                        lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Solid,
                        axisLabelVisible: true,
                        title: 'PDL (昨低)',
                    }});
                }}
                if (ema > 0) {{
                    candleSeries.createPriceLine({{
                        price: ema,
                        color: '#38BDF8',
                        lineWidth: 1,
                        lineStyle: LightweightCharts.LineStyle.Dotted,
                        axisLabelVisible: true,
                        title: '1H EMA20',
                    }});
                }}

                chart.timeScale().fitContent();
            </script>
        </body>
        </html>
        """
        components.html(html_code, height=540, scrolling=False)

    except Exception as e:
        st.error(f"❌ 圖表渲染異常: {str(e)}")

def render_chart_view(assets):
    """供 Tab 內下拉選擇任意標的穿透圖表"""
    code_list = [a['code'] for a in assets]
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        sel_code = st.selectbox("選擇穿透標的", code_list, index=0, key="chart_plugin_code_sel")
    with c2:
        sel_ktype = st.selectbox("選擇週期", ["5M", "1H", "DAY"], index=0, key="chart_plugin_ktype_sel")
    with c3:
        sel_bars = st.slider("顯示柱數", 30, 300, 120, step=10, key="chart_plugin_bars_sel")

    render_lightweight_tv_chart(sel_code, sel_ktype, sel_bars)
