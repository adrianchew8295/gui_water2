# 文件名: macro_radar_engine.py
# 職責: 純日線客觀幾何計算、人性化波段防守位提取、數據自審核與 AI Markdown 日誌生成

import numpy as np
import pandas as pd
from typing import Dict, Any, List

def find_swing_pivots(df: pd.DataFrame, window: int = 8):
    """提取客觀波段頂底擺動極值點 (Swing Pivots)"""
    highs = df['high'].values
    lows = df['low'].values
    times = df['time_clean'].values
    n = len(df)
    
    swing_highs = []
    swing_lows = []
    
    for i in range(window, n - window):
        if np.all(highs[i] >= highs[i - window:i]) and np.all(highs[i] >= highs[i + 1:i + window + 1]):
            swing_highs.append({"idx": i, "time": str(times[i])[:10], "price": float(highs[i])})
        if np.all(lows[i] <= lows[i - window:i]) and np.all(lows[i] <= lows[i + 1:i + window + 1]):
            swing_lows.append({"idx": i, "time": str(times[i])[:10], "price": float(lows[i])})
            
    return swing_highs, swing_lows

def compute_radar_channel_and_markdown(df: pd.DataFrame, ticker: str = "US.NVDA") -> Dict[str, Any]:
    """
    計算宏觀通道、重大支撐與結構化審計報告
    """
    if df is None or len(df) < 20:
        return {"status": "fail", "msg": "K線樣本數不足以構建幾何模型"}

    time_col = 'time_clean' if 'time_clean' in df.columns else ('time_key' if 'time_key' in df.columns else df.columns[0])
    df['time_clean'] = df[time_col].astype(str).str.slice(0, 10)
    
    times = df['time_clean'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    n = len(df)
    last_idx = n - 1
    curr_price = float(closes[-1])

    # 1. 提取波段頂底 (自適應窗口)
    sw_highs, sw_lows = find_swing_pivots(df, window=8)
    if len(sw_highs) < 2 or len(sw_lows) < 2:
        sw_highs, sw_lows = find_swing_pivots(df, window=4)

    # 2. 人性化 Major Support（鎖定近 90~150 根 K 線的結構底座，排除遠古噪點）
    active_lookback = min(n, 120)
    recent_low_slice = lows[-active_lookback:]
    major_support_val = float(np.percentile(recent_low_slice, 10))
    if len(sw_lows) >= 2:
        candidates = [p["price"] for p in sw_lows if p["idx"] >= (n - active_lookback)]
        if candidates:
            major_support_val = min(candidates)

    # 3. 即時 S/R 水平線
    recent_res = float(sw_highs[-1]["price"]) if sw_highs else float(highs[-20:].max())
    recent_sup = float(sw_lows[-1]["price"]) if sw_lows else float(lows[-20:].min())

    # 4. 宏觀通道 (Macro Channel) 計算與坐標射線
    macro_channel = None
    h1, h2, l1, l2 = None, None, None, None
    curr_res_val, curr_sup_val = recent_res, recent_sup

    if len(sw_highs) >= 2 and len(sw_lows) >= 2:
        h1, h2 = sw_highs[-2], sw_highs[-1]
        l1, l2 = sw_lows[-2], sw_lows[-1]

        # 阻力射線
        dx_h = max(1, h2["idx"] - h1["idx"])
        slope_h = (h2["price"] - h1["price"]) / dx_h
        curr_res_val = h2["price"] + slope_h * (last_idx - h2["idx"])

        # 支撐射線
        dx_l = max(1, l2["idx"] - l1["idx"])
        slope_l = (l2["price"] - l1["price"]) / dx_l
        curr_sup_val = l2["price"] + slope_l * (last_idx - l2["idx"])

        # 生成通道點位數組
        res_line = [{"time": str(times[i]), "value": round(float(h1["price"] + slope_h * (i - h1["idx"])), 2)} for i in range(h1["idx"], n)]
        sup_line = [{"time": str(times[i]), "value": round(float(l1["price"] + slope_l * (i - l1["idx"])), 2)} for i in range(l1["idx"], n)]

        trend_type = "🟢 上升通道 (Bullish Channel)" if slope_l > 0 else ("🔴 下降通道 (Bearish Channel)" if slope_l < 0 else "⚪ 箱體震盪 (Range)")

        macro_channel = {
            "trend_type": trend_type,
            "res_line": res_line,
            "sup_line": sup_line,
            "curr_res_val": round(curr_res_val, 2),
            "curr_sup_val": round(curr_sup_val, 2),
            "h1": h1, "h2": h2, "l1": l1, "l2": l2,
            "span_bars": last_idx - min(h1["idx"], l1["idx"])
        }

    # 5. 構建數據自審核與 AI 分析 Markdown 日誌
    h1_str = f"{h1['time']} (${h1['price']:.2f})" if h1 else "--"
    h2_str = f"{h2['time']} (${h2['price']:.2f})" if h2 else "--"
    l1_str = f"{l1['time']} (${l1['price']:.2f})" if l1 else "--"
    l2_str = f"{l2['time']} (${l2['price']:.2f})" if l2 else "--"
    h_span = abs(curr_res_val - curr_sup_val)

    ai_markdown = f"""### 📊 【{ticker} 日線技術幾何與趨勢通道審計報告】
**審計基準日期**: {times[-1]} | **最新收盤現價**: ${curr_price:.2f} | **數據樣本總跨度**: {times[0]} 至 {times[-1]} (共 {n} 根日K)

#### 1. 當前波段幾何戰區 (John J. Murphy 體系)
- **通道形態判定**: {macro_channel['trend_type'] if macro_channel else '區間箱體整理'}
- **動態阻力線 (Upper Channel)**:
  - 錨點連線: 起點 P1 [{h1_str}] ➔ 終點 P2 [{h2_str}]
  - 最新動態阻力價位: **${curr_res_val:.2f}**
- **動態支撐線 (Lower Channel)**:
  - 錨點連線: 起點 P1 [{l1_str}] ➔ 終點 P2 [{l2_str}]
  - 最新動態支撐價位: **${curr_sup_val:.2f}**
- **近端水平即時攻防**:
  - 即時阻力 (RES): ${recent_res:.2f} | 即時支撐 (SUP): ${recent_sup:.2f}
- **⭐ 當前大波段 MAJOR SUPPORT (核心結構防守底座)**: **${major_support_val:.2f}** (已排除遠古噪點)

#### 2. 空間目標推演 (Fibonacci Extension)
- 上方突破 Target 1 (0.618x): **${(curr_res_val + h_span * 0.618):.2f}**
- 上方擴展 Target 2 (1.000x): **${(curr_res_val + h_span * 1.000):.2f}**
- 下方破位防守 Target (下軌破位): **${(curr_sup_val - h_span * 0.618):.2f}**

---
#### 3. 給 AI 策略軍師的診斷指令 (Direct Prompt):
1. **通道位置審計**：現價 ${curr_price:.2f} 處於通道（阻力 ${curr_res_val:.2f} / 支撐 ${curr_sup_val:.2f}）的百分之幾位置？
2. **多空動能評估**：當前 K 線結構是在回踩下軌尋求承接，還是在測試上軌面臨拋壓？
3. **風控邊界**：若跌破當前動態支撐 ${curr_sup_val:.2f}，距離 Major Support (${major_support_val:.2f}) 的防守空間是否具備合理的盈虧比？
"""

    return {
        "status": "success",
        "ticker": ticker,
        "curr_price": curr_price,
        "major_support": round(major_support_val, 2),
        "recent_res": round(recent_res, 2),
        "recent_sup": round(recent_sup, 2),
        "macro_channel": macro_channel,
        "ai_markdown": ai_markdown
    }
