# 文件名: macro_radar_engine.py
# 職責: 依據 John J. Murphy 標準幾何構建平行通道 (Parallel Channel)、人性化防守位與 AI 審計日誌

import numpy as np
import pandas as pd
from typing import Dict, Any, List

def find_swing_pivots(df: pd.DataFrame, window: int = 8):
    """提取客觀波段擺動極值點 (Swing Pivots)"""
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
    計算標準平行通道 (John J. Murphy 體系) 與結構化審計報告
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

    # 2. 人性化 Major Support（鎖定近 120 根 K 線的關鍵結構起漲平台）
    active_lookback = min(n, 120)
    recent_low_slice = lows[-active_lookback:]
    major_support_val = float(np.percentile(recent_low_slice, 10))
    if sw_lows:
        valid_candidates = [p["price"] for p in sw_lows if p["idx"] >= (n - active_lookback)]
        if valid_candidates:
            major_support_val = min(valid_candidates)

    # 3. 即時 S/R 水平線 (取最近一個波峰與波谷)
    recent_res = float(sw_highs[-1]["price"]) if sw_highs else float(highs[-20:].max())
    recent_sup = float(sw_lows[-1]["price"]) if sw_lows else float(lows[-20:].min())

    # 4. 標準平行通道構建 (Murphy Parallel Channel)
    macro_channel = None
    curr_res_val, curr_sup_val = recent_res, recent_sup
    h1, h2, l1, l2 = None, None, None, None

    if len(sw_lows) >= 2 and len(sw_highs) >= 1:
        # 以最新兩個波谷為基線 (Baseline Support)
        l1, l2 = sw_lows[-2], sw_lows[-1]
        dx_l = max(1, l2["idx"] - l1["idx"])
        slope = (l2["price"] - l1["price"]) / dx_l  # 通道主斜率

        # 在 l1 與 last_idx 之間尋找最高波峰作為通道頂寬度 (Channel Height)
        relevant_highs = highs[l1["idx"]:]
        channel_height = max(10.0, float(np.max(relevant_highs) - np.min(lows[l1["idx"]:])))
        
        # 尋找最近的代表性波峰錨點
        h2 = sw_highs[-1] if sw_highs else {"idx": last_idx, "time": str(times[last_idx]), "price": curr_price}
        h1 = sw_highs[-2] if len(sw_highs) >= 2 else h2

        # 向上平移生成平行上軌 (Upper Channel = Lower Channel + Height)
        start_idx = l1["idx"]
        sup_line = []
        res_line = []
        for i in range(start_idx, n):
            base_sup = float(l1["price"] + slope * (i - l1["idx"]))
            base_res = float(base_sup + channel_height)
            sup_line.append({"time": str(times[i]), "value": round(base_sup, 2)})
            res_line.append({"time": str(times[i]), "value": round(base_res, 2)})

        curr_sup_val = l1["price"] + slope * (last_idx - l1["idx"])
        curr_res_val = curr_sup_val + channel_height

        trend_type = "🟢 上升通道 (Bullish Channel)" if slope > 0 else ("🔴 下降通道 (Bearish Channel)" if slope < 0 else "⚪ 箱體通道 (Horizontal Channel)")

        macro_channel = {
            "trend_type": trend_type,
            "res_line": res_line,
            "sup_line": sup_line,
            "curr_res_val": round(curr_res_val, 2),
            "curr_sup_val": round(curr_sup_val, 2),
            "channel_height": round(channel_height, 2),
            "h1": h1, "h2": h2, "l1": l1, "l2": l2,
            "slope": round(slope, 3)
        }

    # 5. 生成嚴謹的 AI 分析 Markdown 日誌
    h1_str = f"{h1['time']} (${h1['price']:.2f})" if h1 else "--"
    h2_str = f"{h2['time']} (${h2['price']:.2f})" if h2 else "--"
    l1_str = f"{l1['time']} (${l1['price']:.2f})" if l1 else "--"
    l2_str = f"{l2['time']} (${l2['price']:.2f})" if l2 else "--"
    h_span = abs(curr_res_val - curr_sup_val)

    # 計算現價處於通道內的百分比位置 (0% = 下軌, 100% = 上軌)
    channel_pos_pct = ((curr_price - curr_sup_val) / max(0.01, h_span)) * 100.0

    ai_markdown = f"""### 📊 【{ticker} 日線技術幾何與趨勢通道審計報告】
**審計基準日期**: {times[-1]} | **最新收盤現價**: ${curr_price:.2f} | **數據樣本總跨度**: {times[0]} 至 {times[-1]} (共 {n} 根日K)

#### 1. 當前波段幾何戰區 (John J. Murphy 標準平行通道體系)
- **通道形態判定**: {macro_channel['trend_type'] if macro_channel else '區間箱體整理'} (每日斜率推升: +${macro_channel['slope']:.2f} USD)
- **通道幾何高度**: **${h_span:.2f} USD**
- **動態阻力上軌 (Upper Channel)**:
  - 基準連線: 由波谷基線平行投射至主要波峰 [{h2_str}]
  - 當前動態阻力天花板: **${curr_res_val:.2f}**
- **動態支撐下軌 (Lower Channel)**:
  - 錨點連線: 起點 P1 [{l1_str}] ➔ 終點 P2 [{l2_str}]
  - 當前動態支撐地板: **${curr_sup_val:.2f}**
- **現價相對通道位置**: **{channel_pos_pct:.1f}%** (0% = 踩下軌, 100% = 摸上軌, >100% = 向上突破)
- **近端水平即時攻防**:
  - 即時阻力 (RES): ${recent_res:.2f} | 即時支撐 (SUP): ${recent_sup:.2f}
- **⭐ 當前大波段 MAJOR SUPPORT (核心結構防守底座)**: **${major_support_val:.2f}** (已排除遠古噪點)

#### 2. 空間目標推演 (Fibonacci Extension)
- 上方突破 Target 1 (0.618x 通道擴展): **${(curr_res_val + h_span * 0.618):.2f}**
- 上方極限 Target 2 (1.000x 通道對稱翻倍): **${(curr_res_val + h_span * 1.000):.2f}**
- 下方破位防守 Target (下軌跌破 0.618x): **${(curr_sup_val - h_span * 0.618):.2f}**

---
#### 3. 給 AI 策略軍師的診斷指令 (Direct Prompt):
1. **通道位置審計**：現價 ${curr_price:.2f} 處於通道（阻力 ${curr_res_val:.2f} / 支撐 ${curr_sup_val:.2f}）的 {channel_pos_pct:.1f}% 分位，多頭是否面臨通道上軌壓制？
2. **多空動能評估**：當前 K 線結構是在回踩動態下軌尋求承接，還是在測試上軌形成突破/頂背離？
3. **風控邊界**：若失守當前動態支撐 ${curr_sup_val:.2f}，距離 Major Support (${major_support_val:.2f}) 的盈虧空間是否支持防守？
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
