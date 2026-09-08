# 文件名: macro_radar_engine.py
# 職責: 依據 John J. Murphy 原著算法提取局部波段樞紐、動態有效趨勢線、平行通道與波浪狀態

import numpy as np
import pandas as pd

def find_swing_pivots(df: pd.DataFrame, window: int = 4):
    """
    依據 Murphy 第 4 章：提取客觀擺動高點 (Swing Highs) 與擺動低點 (Swing Lows)
    """
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    
    p_highs = []
    p_lows = []
    
    for i in range(window, n - window):
        # 局部高點：高於前後 window 根
        if highs[i] == max(highs[i - window : i + window + 1]):
            p_highs.append((i, df['time_key'].iloc[i], highs[i]))
        # 局部低點：低於前後 window 根
        if lows[i] == min(lows[i - window : i + window + 1]):
            p_lows.append((i, df['time_key'].iloc[i], lows[i]))
            
    return p_highs, p_lows

def compute_murphy_technicals(df_daily: pd.DataFrame):
    """
    計算精準 Murphy 幾何特徵 (Active Channel, S/R, Major Support, Elliott Wave)
    """
    if df_daily is None or len(df_daily) < 30:
        return {}
    
    df = df_daily.copy().reset_index(drop=True)
    n = len(df)
    current_price = float(df['close'].iloc[-1])
    
    p_highs, p_lows = find_swing_pivots(df, window=4)
    
    # 1. 提取關鍵 S/R 與 Major Support
    res_candidates = [h[2] for h in p_highs if h[2] > current_price]
    immediate_resistance = min(res_candidates) if res_candidates else float(df['high'].max())
    
    sup_candidates = [l[2] for l in p_lows if l[2] < current_price]
    immediate_support = max(sup_candidates) if sup_candidates else float(df['low'].min())
    
    # Major Support: 過去 300 根的歷史強支撐底線
    major_support = float(df['low'].tail(300).min())
    
    # 2. 局部有效趨勢線與平行通道 (只保留當前未破位的活躍通道)
    trend_lines = []
    channel_lines = []
    trend_type = "SIDEWAYS"
    
    if len(p_lows) >= 2 and len(p_highs) >= 2:
        # 取最近的兩個主要低點
        l1 = p_lows[-1]
        l2 = p_lows[-2]
        h1 = p_highs[-1]
        h2 = p_highs[-2]
        
        # 判定上升趨勢通道 (低點抬高 Higher Lows)
        if l1[2] > l2[2] and l1[0] > l2[0]:
            slope = (l1[2] - l2[2]) / (l1[0] - l2[0])
            # 計算延伸至當前的趨勢線價格
            curr_line_val = l2[2] + slope * (n - 1 - l2[0])
            
            # 若現價仍在趨勢線上方或附近，判定為活躍上升趨勢
            if current_price >= curr_line_val * 0.96:
                trend_type = "UPTREND"
                # 基礎上升趨勢線 (支撐軌道 - 從 l2 起點畫到當前)
                trend_lines.append({
                    "from_time": l2[1].split(' ')[0],
                    "to_time": df['time_key'].iloc[-1].split(' ')[0],
                    "from_price": l2[2],
                    "to_price": curr_line_val,
                    "color": "#00E676"
                })
                # 平行通道線 (從夾在中間或最高峰引出平行線)
                peak_between = max([h[2] for h in p_highs if h[0] >= l2[0]] or [h1[2]])
                # 基準在起點的垂直偏移量
                peak_idx = [h[0] for h in p_highs if h[2] == peak_between][0]
                base_at_peak = l2[2] + slope * (peak_idx - l2[0])
                offset = max(peak_between - base_at_peak, (l1[2] - l2[2]) * 0.5)
                
                channel_lines.append({
                    "from_time": l2[1].split(' ')[0],
                    "to_time": df['time_key'].iloc[-1].split(' ')[0],
                    "from_price": l2[2] + offset,
                    "to_price": curr_line_val + offset,
                    "color": "#FACC15"
                })

        # 判定下降趨勢通道 (高點降低 Lower Highs)
        elif h1[2] < h2[2] and h1[0] > h2[0]:
            slope = (h1[2] - h2[2]) / (h1[0] - h2[0])
            curr_line_val = h2[2] + slope * (n - 1 - h2[0])
            
            if current_price <= curr_line_val * 1.04:
                trend_type = "DOWNTREND"
                # 基礎下降趨勢線 (阻力軌道 - 從 h2 起點畫到當前)
                trend_lines.append({
                    "from_time": h2[1].split(' ')[0],
                    "to_time": df['time_key'].iloc[-1].split(' ')[0],
                    "from_price": h2[2],
                    "to_price": curr_line_val,
                    "color": "#FF5252"
                })
                # 平行通道線
                trough_between = min([l[2] for l in p_lows if l[0] >= h2[0]] or [l1[2]])
                trough_idx = [l[0] for l in p_lows if l[2] == trough_between][0]
                base_at_trough = h2[2] + slope * (trough_idx - h2[0])
                offset = min(trough_between - base_at_trough, (h1[2] - h2[2]) * 0.5)
                
                channel_lines.append({
                    "from_time": h2[1].split(' ')[0],
                    "to_time": df['time_key'].iloc[-1].split(' ')[0],
                    "from_price": h2[2] + offset,
                    "to_price": curr_line_val + offset,
                    "color": "#FACC15"
                })

    # 3. 艾略特波浪狀態推演 (Murphy Chapter 13)
    if trend_type == "UPTREND":
        if current_price >= immediate_resistance * 0.985:
            wave_label = "🌊 艾略特浪型: 第 ⑤ 浪衝頂末段 (注意通道上沿拋壓)"
        else:
            wave_label = "🌊 艾略特浪型: 第 ③ 浪主升推進 (通道內穩健運行)"
    elif trend_type == "DOWNTREND":
        wave_label = "🌊 艾略特浪型: 第 (C) 浪主跌探底中"
    else:
        wave_label = "🌊 艾略特浪型: 第 ④ 浪 (A)-(B)-(C) 矩形箱體修復"

    return {
        "trend_type": trend_type,
        "immediate_resistance": immediate_resistance,
        "immediate_support": immediate_support,
        "major_support": major_support,
        "trend_lines": trend_lines,
        "channel_lines": channel_lines,
        "wave_label": wave_label
    }
