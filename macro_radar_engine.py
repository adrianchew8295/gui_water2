# 文件名: macro_radar_engine.py
# 職責: 依據 John J. Murphy 原著算法提取擺動極值、生成有效 Trendline、Channel、S/R 與波浪狀態

import numpy as np
import pandas as pd

def find_swing_pivots(df: pd.DataFrame, window: int = 5):
    """提取客觀擺動高點 (Swing Highs) 與擺動低點 (Swing Lows)"""
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    
    p_highs = []
    p_lows = []
    
    for i in range(window, n - window):
        if highs[i] == max(highs[i - window : i + window + 1]):
            p_highs.append((i, str(df['dt_str'].iloc[i]), float(highs[i])))
        if lows[i] == min(lows[i - window : i + window + 1]):
            p_lows.append((i, str(df['dt_str'].iloc[i]), float(lows[i])))
            
    return p_highs, p_lows

def compute_murphy_technicals(df_daily: pd.DataFrame):
    """計算 Murphy 經典技術幾何特徵"""
    if df_daily is None or len(df_daily) < 30:
        return {}
    
    df = df_daily.copy().reset_index(drop=True)
    df['dt_str'] = pd.to_datetime(df['time_key']).dt.strftime('%Y-%m-%d')
    n = len(df)
    current_price = float(df['close'].iloc[-1])
    
    p_highs, p_lows = find_swing_pivots(df, window=5)
    
    # 1. 提取關鍵 S/R 與 Major Support
    res_candidates = [h[2] for h in p_highs if h[2] > current_price]
    immediate_resistance = min(res_candidates) if res_candidates else float(df['high'].max())
    
    sup_candidates = [l[2] for l in p_lows if l[2] < current_price]
    immediate_support = max(sup_candidates) if sup_candidates else float(df['low'].min())
    
    major_support = float(df['low'].min())
    
    # 2. 趨勢線與通道生成
    trend_lines = []
    channel_lines = []
    trend_type = "SIDEWAYS"
    
    if len(p_lows) >= 2 and len(p_highs) >= 2:
        l1 = p_lows[-1]
        l2 = p_lows[-2]
        h1 = p_highs[-1]
        h2 = p_highs[-2]
        
        # 尋找最近的顯著低點連線（上升趨勢線）
        if l1[2] > l2[2] and l1[0] > l2[0]:
            slope = (l1[2] - l2[2]) / (l1[0] - l2[0])
            curr_line_val = l2[2] + slope * (n - 1 - l2[0])
            trend_type = "UPTREND"
            
            # 上升趨勢線 (支撐)
            trend_lines.append({
                "from_time": l2[1],
                "to_time": df['dt_str'].iloc[-1],
                "from_price": l2[2],
                "to_price": curr_line_val,
                "color": "#00E676"
            })
            
            # 平行通道線 (自波峰引出)
            peaks_after = [h[2] for h in p_highs if h[0] >= l2[0]]
            peak_val = max(peaks_after) if peaks_after else h1[2]
            peak_idx = [h[0] for h in p_highs if h[2] == peak_val][0] if peaks_after else h1[0]
            base_at_peak = l2[2] + slope * (peak_idx - l2[0])
            offset = max(peak_val - base_at_peak, (l1[2] - l2[2]) * 0.4)
            
            channel_lines.append({
                "from_time": l2[1],
                "to_time": df['dt_str'].iloc[-1],
                "from_price": l2[2] + offset,
                "to_price": curr_line_val + offset,
                "color": "#FACC15"
            })
            
        elif h1[2] < h2[2] and h1[0] > h2[0]:
            slope = (h1[2] - h2[2]) / (h1[0] - h2[0])
            curr_line_val = h2[2] + slope * (n - 1 - h2[0])
            trend_type = "DOWNTREND"
            
            # 下降趨勢線 (阻力)
            trend_lines.append({
                "from_time": h2[1],
                "to_time": df['dt_str'].iloc[-1],
                "from_price": h2[2],
                "to_price": curr_line_val,
                "color": "#FF5252"
            })
            
            # 下降平行通道線
            troughs_after = [l[2] for l in p_lows if l[0] >= h2[0]]
            trough_val = min(troughs_after) if troughs_after else l1[2]
            trough_idx = [l[0] for l in p_lows if l[2] == trough_val][0] if troughs_after else l1[0]
            base_at_trough = h2[2] + slope * (trough_idx - h2[0])
            offset = min(trough_val - base_at_trough, (h1[2] - h2[2]) * 0.4)
            
            channel_lines.append({
                "from_time": h2[1],
                "to_time": df['dt_str'].iloc[-1],
                "from_price": h2[2] + offset,
                "to_price": curr_line_val + offset,
                "color": "#FACC15"
            })
        else:
            # 震盪區間內：以最近的次級波段低點連線作為局部動態軌道
            slope = (l1[2] - l2[2]) / (l1[0] - l2[0]) if l1[0] != l2[0] else 0
            curr_line_val = l2[2] + slope * (n - 1 - l2[0])
            trend_lines.append({
                "from_time": l2[1],
                "to_time": df['dt_str'].iloc[-1],
                "from_price": l2[2],
                "to_price": curr_line_val,
                "color": "#38BDF8"
            })

    # 3. 波浪形態推演
    if trend_type == "UPTREND":
        wave_label = "🌊 艾略特形態: 第 ③ 浪主升推進 (通道運行中)"
    elif trend_type == "DOWNTREND":
        wave_label = "🌊 艾略特形態: 第 (C) 浪探底中"
    else:
        wave_label = "🌊 艾略特形態: 第 ④ 浪 (A)-(B)-(C) 矩形箱體修復"

    return {
        "trend_type": trend_type,
        "immediate_resistance": immediate_resistance,
        "immediate_support": immediate_support,
        "major_support": major_support,
        "trend_lines": trend_lines,
        "channel_lines": channel_lines,
        "wave_label": wave_label
    }
