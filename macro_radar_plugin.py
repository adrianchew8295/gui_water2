# 文件名: macro_radar_engine.py
# 職責: 依據 John J. Murphy 原著算法提取 300~500 根日線之 S/R、Major Support、Trendlines、Channels 與 Wave 狀態

import numpy as np
import pandas as pd

def extract_pivot_points(df: pd.DataFrame, window: int = 5):
    """
    依據 Murphy 第 4 章定義：提取客觀擺動波峰 (Peaks) 與波谷 (Troughs)
    """
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    
    pivot_highs = []
    pivot_lows = []
    
    for i in range(window, n - window):
        # 局部波峰判定
        if highs[i] == max(highs[i - window : i + window + 1]):
            pivot_highs.append((i, df['time_key'].iloc[i], highs[i]))
        # 局部波谷判定
        if lows[i] == min(lows[i - window : i + window + 1]):
            pivot_lows.append((i, df['time_key'].iloc[i], lows[i]))
            
    return pivot_highs, pivot_lows

def compute_murphy_technicals(df_daily: pd.DataFrame):
    """
    計算 Murphy 經典技術幾何特徵：
    1. Trendlines (上升/下降趨勢線)
    2. Trend Channels (平行通道)
    3. S/R Levels (即時支撐/阻力)
    4. Major Support (大級別重大支撐)
    5. Elliott Wave (日線浪型推演)
    """
    if df_daily is None or len(df_daily) < 30:
        return {}
    
    df = df_daily.copy().reset_index(drop=True)
    pivot_highs, pivot_lows = extract_pivot_points(df, window=5)
    
    current_price = float(df['close'].iloc[-1])
    n = len(df)
    
    # 1. 計算 S/R 與 Major Support
    # 尋找現價上方的最近有效阻力峰值
    res_candidates = [p[2] for p in pivot_highs if p[2] > current_price]
    immediate_resistance = min(res_candidates) if res_candidates else float(df['high'].max())
    
    # 尋找現價下方的最近有效支撐谷值
    sup_candidates = [p[2] for p in pivot_lows if p[2] < current_price]
    immediate_support = max(sup_candidates) if sup_candidates else float(df['low'].min())
    
    # Major Support: 過去 300 根的歷史強支撐底線 (多次觸及的低點聚合或最低點)
    major_support = float(df['low'].tail(300).min())
    
    # 2. 計算 Trendlines 與 Channels (Murphy Chapter 4)
    trend_type = "SIDEWAYS"
    trend_lines = []
    channel_lines = []
    
    if len(pivot_lows) >= 2 and len(pivot_highs) >= 2:
        last_l2 = pivot_lows[-2]
        last_l1 = pivot_lows[-1]
        last_h2 = pivot_highs[-2]
        last_h1 = pivot_highs[-1]
        
        # 上升趨勢線 (Up Trendline: 連接抬高的低點)
        if last_l1[2] > last_l2[2]:
            slope = (last_l1[2] - last_l2[2]) / (last_l1[0] - last_l2[0]) if last_l1[0] != last_l2[0] else 0
            if slope > 0:
                trend_type = "UPTREND"
                # 趨勢線端點 (延伸至當前根)
                p1_val = last_l2[2]
                curr_val = last_l2[2] + slope * (n - 1 - last_l2[0])
                trend_lines.append({
                    "type": "UP_TRENDLINE",
                    "from_time": last_l2[1],
                    "to_time": df['time_key'].iloc[-1],
                    "from_price": p1_val,
                    "to_price": curr_val,
                    "color": "#00E676"
                })
                # 平行通道線 (從中間的高點引出平行線)
                channel_high = max([h[2] for h in pivot_highs if h[0] > last_l2[0]] or [last_h1[2]])
                offset = channel_high - (last_l2[2] + slope * (last_h1[0] - last_l2[0]))
                channel_lines.append({
                    "type": "UP_CHANNEL",
                    "from_time": last_l2[1],
                    "to_time": df['time_key'].iloc[-1],
                    "from_price": p1_val + offset,
                    "to_price": curr_val + offset,
                    "color": "#FACC15"
                })
                
        # 下降趨勢線 (Down Trendline: 連接降低的高點)
        elif last_h1[2] < last_h2[2]:
            slope = (last_h1[2] - last_h2[2]) / (last_h1[0] - last_h2[0]) if last_h1[0] != last_h2[0] else 0
            if slope < 0:
                trend_type = "DOWNTREND"
                p1_val = last_h2[2]
                curr_val = last_h2[2] + slope * (n - 1 - last_h2[0])
                trend_lines.append({
                    "type": "DOWN_TRENDLINE",
                    "from_time": last_h2[1],
                    "to_time": df['time_key'].iloc[-1],
                    "from_price": p1_val,
                    "to_price": curr_val,
                    "color": "#FF5252"
                })
                # 下降平行通道線
                channel_low = min([l[2] for l in pivot_lows if l[0] > last_h2[0]] or [last_l1[2]])
                offset = channel_low - (last_h2[2] + slope * (last_l1[0] - last_h2[0]))
                channel_lines.append({
                    "type": "DOWN_CHANNEL",
                    "from_time": last_h2[1],
                    "to_time": df['time_key'].iloc[-1],
                    "from_price": p1_val + offset,
                    "to_price": curr_val + offset,
                    "color": "#FACC15"
                })

    # 3. 艾略特波浪推演 (Murphy Chapter 13)
    wave_label = "🌊 艾略特狀態: 結構整固蓄勢中"
    if trend_type == "UPTREND":
        if current_price >= immediate_resistance * 0.98:
            wave_label = "🌊 艾略特形態: 第 ⑤ 浪衝頂突破推進中"
        else:
            wave_label = "🌊 艾略特形態: 第 ③ 浪主升浪強勢運行"
    elif trend_type == "DOWNTREND":
        wave_label = "🌊 艾略特形態: 第 (C) 浪主跌/深度調整結構"
    else:
        wave_label = "🌊 艾略特形態: 第 ④ 浪 (A)-(B)-(C) 寬幅箱體修復"

    return {
        "trend_type": trend_type,
        "immediate_resistance": immediate_resistance,
        "immediate_support": immediate_support,
        "major_support": major_support,
        "trend_lines": trend_lines,
        "channel_lines": channel_lines,
        "wave_label": wave_label
    }
