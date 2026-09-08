# 文件名: trendline_engine.py
# 功能: 計算宏觀波段通道 (Macro Channel) 與德馬克微觀趨勢線，生成結構化圖表解析報告

from typing import Dict, Any, List
import numpy as np
import pandas as pd

def find_swing_pivots(df: pd.DataFrame, window: int = 15):
    """提取大級別宏觀波段極值點 (用於畫出覆蓋全局的主通道)"""
    highs = df['high'].values
    lows = df['low'].values
    times = df['time_clean'].values if 'time_clean' in df.columns else df.index.values
    
    swing_highs = []
    swing_lows = []
    n = len(df)
    
    for i in range(window, n - window):
        if np.all(highs[i] >= highs[i - window:i]) and np.all(highs[i] >= highs[i + 1:i + window + 1]):
            swing_highs.append({"idx": i, "time": str(times[i]), "price": float(highs[i])})
        if np.all(lows[i] <= lows[i - window:i]) and np.all(lows[i] <= lows[i + 1:i + window + 1]):
            swing_lows.append({"idx": i, "time": str(times[i]), "price": float(lows[i])})
            
    return swing_highs, swing_lows

def compute_advanced_channel(df: pd.DataFrame, macro_window: int = 12, micro_window: int = 4) -> Dict[str, Any]:
    """
    計算最高規格通道矩陣：
    1. 宏觀主通道 (覆蓋中長週期幾何)
    2. 微觀 TD 攻擊線
    3. 全景數據文字解析報告 (哪裡畫到哪裡、覆蓋天數、起止坐標)
    """
    if df is None or len(df) < (macro_window * 2 + 5):
        return {"status": "fail", "msg": "數據量不足以構建宏觀幾何通道"}

    time_col = 'time_clean' if 'time_clean' in df.columns else ('time_key' if 'time_key' in df.columns else df.columns[0])
    df['time_clean'] = df[time_col].astype(str)
    times = df['time_clean'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    last_idx = len(df) - 1

    # 1. 提取大級別波段極值點
    sw_highs, sw_lows = find_swing_pivots(df, window=macro_window)
    
    # 若大級別點位不足，降級採用中級別
    if len(sw_highs) < 2 or len(sw_lows) < 2:
        sw_highs, sw_lows = find_swing_pivots(df, window=max(5, macro_window // 2))

    res = {
        "status": "success",
        "data_summary": {
            "start_time": str(times[0]),
            "end_time": str(times[-1]),
            "total_bars": len(df),
            "latest_close": float(closes[-1])
        },
        "macro_channel": None,
        "hud_report": {}
    }

    if len(sw_highs) >= 2 and len(sw_lows) >= 2:
        # 取跨度較大的主要錨點
        h1, h2 = sw_highs[-2], sw_highs[-1]
        l1, l2 = sw_lows[-2], sw_lows[-1]

        # 阻力軌道計算
        dx_h = h2["idx"] - h1["idx"]
        slope_h = (h2["price"] - h1["price"]) / dx_h if dx_h != 0 else 0
        curr_res = h2["price"] + slope_h * (last_idx - h2["idx"])

        # 支撐軌道計算
        dx_l = l2["idx"] - l1["idx"]
        slope_l = (l2["price"] - l1["price"]) / dx_l if dx_l != 0 else 0
        curr_sup = l2["price"] + slope_l * (last_idx - l2["idx"])

        res_line = [{"time": str(times[i]), "value": round(float(h1["price"] + slope_h * (i - h1["idx"])), 2)} for i in range(h1["idx"], last_idx + 1)]
        sup_line = [{"time": str(times[i]), "value": round(float(l1["price"] + slope_l * (i - l1["idx"])), 2)} for i in range(l1["idx"], last_idx + 1)]

        # 幾何形態判定
        channel_height = abs(curr_res - curr_sup)
        trend_direction = "🟢 上升通道 (Bullish Channel)" if slope_l > 0 and slope_h > 0 else (
            "🔴 下降通道 (Bearish Channel)" if slope_l < 0 and slope_h < 0 else "⚪ 收斂/擴散三角形態 (Consolidation)"
        )

        res["macro_channel"] = {
            "trend_type": trend_direction,
            "res_line": res_line,
            "sup_line": sup_line,
            "curr_res_val": round(curr_res, 2),
            "curr_sup_val": round(curr_sup, 2),
            "channel_height": round(channel_height, 2),
            "anchor_h1": h1,
            "anchor_h2": h2,
            "anchor_l1": l1,
            "anchor_l2": l2
        }

        # 結構化文字報告
        res["hud_report"] = {
            "title": f"{trend_direction}",
            "period_desc": f"數據涵蓋: {times[0][:10]} 至 {times[-1][:10]} (共 {len(df)} 根 K 線)",
            "res_desc": f"阻力軌道: 從 {h1['time'][:10]} (${h1['price']:.2f}) 連接至 {h2['time'][:10]} (${h2['price']:.2f})，跨越 {dx_h} 根 K 線，當前動態阻力: ${curr_res:.2f}",
            "sup_desc": f"支撐軌道: 從 {l1['time'][:10]} (${l1['price']:.2f}) 連接至 {l2['time'][:10]} (${l2['price']:.2f})，跨越 {dx_l} 根 K 線，當前動態支撐: ${curr_sup:.2f}",
            "target_bull": round(curr_res + channel_height * 0.618, 2),
            "target_bear": round(curr_sup - channel_height * 0.618, 2)
        }
    else:
        res["status"] = "fail"
        res["msg"] = "無法識別足夠的波段極值點"

    return res
