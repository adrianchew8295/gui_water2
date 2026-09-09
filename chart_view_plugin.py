# 文件名: chart_view_plugin.py
# 職責: 渲染 QQQ 納指大盤中樞與多週期穿透圖表 (TradingView 原生 Canvas · 固定拉滿最高歷史深度 · 無滑桿干擾)

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
    從本地 market_data 加載已由 5M Resample 聚合與深度對齊的 K 線數據
    固定拉滿最高歷史深度 (5M/1H 預設 1500 根，DAY 預設 500 根)
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
                
                # 自動適配時間欄位
                time_col = 'time_clean' if 'time_clean' in df.columns else ('time_key' if 'time_key' in df.columns else df.columns[0])
                
                if k_suffix == "DAY":
                    df['time_plot'] = df[time_col].astype(str).str.slice(0, 10)
                else:
                    df['time_plot'] = df[time_col].astype(str).str.slice(0, 16)
                    
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                        
                df = df.dropna(subset=['open', 'high', 'low', 'close'])
                df = df.drop_duplicates('time_plot').sort_values('time_plot').tail(bars).reset_index(drop=True)
                
                if not df.empty and len(df) >= 5:
                    return df[['time_plot', 'open', 'high', 'low', 'close', 'volume']]
            except Exception:
                pass
                
    return pd.DataFrame()

def render_lightweight_tv_chart(code: str = "US.QQQ", ktype: str = "1H", bars: int = 1500):
    """
    QQQ 納指中樞主圖入口：移除顯示柱數滑桿，直接滿格渲染
    """
    check_and_auto_heal(code)
    
    # 週期選擇器 (單行緊湊呈現，不放多餘滑桿)
    c1, c2 = st.columns([3, 7])
    with c1:
        k_choice = st.radio("⏱️ 選擇時間週期", ["1H (全時段小時線)", "5M (高頻戰區)", "DAY (日線宏觀)"], index=0, horizontal=True)
        
    actual_ktype = "1H" if "1H" in k_choice else ("5M" if "5M" in k_choice else "DAY")
    max_bars = 1500 if actual_ktype in ["5M", "1H"] else 500
    
    df = load_kline_safe(code, ktype=actual_ktype, bars=max_bars)
    
    if df.empty or len(df) < 5:
        st.warning(f"⚠️ {code} 暫無足夠 {actual_ktype} 歷史數據，請確認本地 market_data 或執行 `python sync_history.py`。")
        return

    curr_close = float(df['close'].iloc[-1])
    curr_high = float(df['high'].iloc[-1])
    curr_low = float(df['low'].iloc[-1])
    curr_vol = float(df['volume'].iloc[-1])
    time_last = str(df['time_plot'].iloc[-1])
    
    # 計算 1H/5M 關鍵攻防點 (SBR 天花板 / RBS 地板 / EMA20)
    ema20 = float(df['close'].ewm(span=20).mean().iloc[-1])
    recent_high = float(df['high'].tail(24).max())
    recent_low = float(df['low'].tail(24).min())

    # 頂部 HUD 狀態卡
    st.markdown(
        f"""
        <div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; font-family: monospace;">
            <div style="font-size: 15px; font-weight: bold; color: #58a6ff; display: flex; justify-content: space-between; align-items: center;">
                <span>👑 {code} · {actual_ktype} 核心戰區分析 (全時段數據已對齊 · 滿載 {len(df)} 根)</span>
                <span style="font-size: 12px; color: #8b949e;">最新時間: {time_last}</span>
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

    # 繪圖開關
    t1, t2, t3 = st.columns(3)
    with t1:
        show_ema = st.checkbox("🟡 EMA20 生命線", value=True)
    with t2:
        show_sbr_rbs = st.checkbox("🧱 近期 SBR/RBS 攻防帶", value=True)
    with t3:
        show_vol = st.checkbox("📊 成交量副圖 (Volume)", value=True)

    # 序列化 K 線數據
    candles_data = []
    volume_data = []
    ema_data = []
    
    df['ema20'] = df['close'].ewm(span=20).mean()
    
    for _, row in df.iterrows():
        t_val = str(row['time_plot'])
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
            "color": "rgba(0, 230, 118, 0.4)" if float(row['close']) >= float(row['open']) else "rgba(255, 82, 82, 0.4)"
        })
        if not np.isnan(row['ema20']):
            ema_data.append({
                "time": t_val,
                "value": round(float(row['ema20']), 2)
            })

    candles_json = json.dumps(candles_data)
    volume_json = json.dumps(volume_data)
    ema_json = json.dumps(ema_data)

    # TradingView Lightweight Charts HTML5 畫布
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

            // 1. 主 K 線 Series
            const candleSeries = chart.addCandlestickSeries({{
                upColor: '#00E676',
                downColor: '#FF5252',
                borderVisible: false,
                wickUpColor: '#00E676',
                wickDownColor: '#FF5252',
            }});
            candleSeries.setData({candles_json});

            // 2. 成交量副圖 (可開關)
            if ({str(show_vol).lower()}) {{
                const volumeSeries = chart.addHistogramSeries({{
                    priceFormat: {{ type: 'volume' }},
                    priceScaleId: '',
                    scaleMargins: {{ top: 0.8, bottom: 0 }},
                }});
                volumeSeries.setData({volume_json});
            }}

            // 3. EMA20 生命線 (可開關)
            if ({str(show_ema).lower()}) {{
                const emaSeries = chart.addLineSeries({{
                    color: '#FFD600',
                    lineWidth: 2,
                    title: 'EMA20',
                }});
                emaSeries.setData({ema_json});
            }}

            // 4. SBR / RBS 水平戰區線 (可開關)
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

            window.addEventListener('resize', () => {{
                chart.applyOptions({{ width: container.clientWidth }});
            }});
        </script>
    </body>
    </html>
    """

    components.html(html_code, height=580)

def render_chart_view(assets=None):
    """相容多週期穿透調用入口"""
    default_code = "US.QQQ"
    if isinstance(assets, list) and len(assets) > 0:
        if isinstance(assets[0], dict) and 'code' in assets[0]:
            default_code = assets[0]['code']
        elif isinstance(assets[0], str):
            default_code = assets[0]
    render_lightweight_tv_chart(code=default_code)
