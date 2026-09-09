# 文件名: macro_radar_engine.py
# 職責: 
# 1. 約翰·墨菲 (John J. Murphy) 標準平行通道幾何與重大防守底座
# 2. LuxAlgo / 經典艾略特波浪 (Elliott Wave) 三大鐵律驗證與浪級幾何骨架
# 3. 輸出包含雙重共振數據的 AI 策略軍師可審計 Markdown 日誌

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
            swing_highs.append({"idx": i, "time": str(times[i])[:10], "price": float(highs[i]), "type": "high"})
        if np.all(lows[i] <= lows[i - window:i]) and np.all(lows[i] <= lows[i + 1:i + window + 1]):
            swing_lows.append({"idx": i, "time": str(times[i])[:10], "price": float(lows[i]), "type": "low"})
            
    return swing_highs, swing_lows

def extract_elliott_wave_pattern(df: pd.DataFrame, swing_highs: list, swing_lows: list) -> Dict[str, Any]:
    """
    依據 LuxAlgo / 經典波浪三大鐵律識別最新 5 浪推動或 ABC 調整浪
    鐵律 1: 浪 3 絕非最短浪 (W3 != min(W1, W3, W5))
    鐵律 2: 多頭推動中浪 4 底不進入浪 1 頂 (P4_low > P1_high)
    鐵律 3: 浪 2 回撤不破浪 1 起點 (P2_low > P0_low)
    """
    times = df['time_clean'].values
    highs = df['high'].values
    lows = df['low'].values
    n = len(df)
    
    # 將所有波段點按時間順序混合排序
    all_pivots = sorted(swing_highs + swing_lows, key=lambda x: x['idx'])
    if len(all_pivots) < 5:
        return None

    ew_result = None

    # 倒序尋找符合 5 浪推進條件的最近序列
    for end_i in range(len(all_pivots), 4, -1):
        cand = all_pivots[end_i-5:end_i]
        
        # 情況 A: 多頭 5 浪 (Low0 -> High1 -> Low2 -> High3 -> Low4 -> High5)
        # 檢查序列是否呈現交替型態
        types = [p['type'] for p in cand]
        
        # 嘗試匹配 6 點多頭主浪結構 (P0 到 P5)
        if end_i >= 6:
            cand6 = all_pivots[end_i-6:end_i]
            if [p['type'] for p in cand6] == ['low', 'high', 'low', 'high', 'low', 'high']:
                p0, p1, p2, p3, p4, p5 = cand6
                w1 = p1['price'] - p0['price']
                w3 = p3['price'] - p2['price']
                w5 = p5['price'] - p4['price']
                
                # 嚴格校驗鐵律
                is_valid_bull = (
                    w1 > 0 and w3 > 0 and w5 > 0 and
                    p2['price'] > p0['price'] and
                    p4['price'] > p1['price'] and
                    p3['price'] > p1['price'] and
                    p5['price'] > p3['price'] and
                    w3 != min(w1, w3, w5)
                )
                
                if is_valid_bull:
                    # 計算費氏空間擴展目標
                    target_1 = p4['price'] + w1 # 1.0x 對稱
                    target_2 = p4['price'] + 0.618 * (w1 + w3) # 0.618x 擴展
                    invalidation_level = p1['price'] # 破浪 1 頂結構失效

                    wave_lines = [
                        {"time": p0['time'], "value": p0['price']},
                        {"time": p1['time'], "value": p1['price']},
                        {"time": p2['time'], "value": p2['price']},
                        {"time": p3['time'], "value": p3['price']},
                        {"time": p4['time'], "value": p4['price']},
                        {"time": p5['time'], "value": p5['price']}
                    ]

                    wave_markers = [
                        {"time": p0['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "⓪"},
                        {"time": p1['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "①"},
                        {"time": p2['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "②"},
                        {"time": p3['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "③"},
                        {"time": p4['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "④"},
                        {"time": p5['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "⑤"}
                    ]

                    ew_result = {
                        "pattern": "🟢 多頭 5 浪推動結構 (Motive 5-Wave Impulse)",
                        "stage": "第 ⑤ 浪衝頂階段 / 醞釀 ABC 修正",
                        "p0": p0, "p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5,
                        "w1_len": round(w1, 2), "w3_len": round(w3, 2), "w5_len": round(w5, 2),
                        "target_1": round(target_1, 2),
                        "target_2": round(target_2, 2),
                        "invalidation": round(invalidation_level, 2),
                        "wave_lines": wave_lines,
                        "wave_markers": wave_markers
                    }
                    break

    # 若未滿足完整 6 點，提取最近 4 點判斷是否處於 3 浪爆發或 4 浪回踩中
    if not ew_result and len(all_pivots) >= 4:
        cand4 = all_pivots[-4:]
        if [p['type'] for p in cand4] == ['low', 'high', 'low', 'high']:
            p0, p1, p2, p3 = cand4
            w1 = p1['price'] - p0['price']
            w3 = p3['price'] - p2['price']
            if w1 > 0 and w3 > 0 and p2['price'] > p0['price'] and p3['price'] > p1['price']:
                target_w3 = p2['price'] + 1.618 * w1
                ew_result = {
                    "pattern": "🚀 處於第 ③ 浪主升推進中 (Wave 3 Impulse)",
                    "stage": "主升推動浪推進中",
                    "p0": p0, "p1": p1, "p2": p2, "p3": p3, "p4": None, "p5": None,
                    "w1_len": round(w1, 2), "w3_len": round(w3, 2), "w5_len": 0.0,
                    "target_1": round(target_w3, 2),
                    "target_2": round(p2['price'] + 2.618 * w1, 2),
                    "invalidation": round(p2['price'], 2),
                    "wave_lines": [
                        {"time": p0['time'], "value": p0['price']},
                        {"time": p1['time'], "value": p1['price']},
                        {"time": p2['time'], "value": p2['price']},
                        {"time": p3['time'], "value": p3['price']}
                    ],
                    "wave_markers": [
                        {"time": p0['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "⓪"},
                        {"time": p1['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "①"},
                        {"time": p2['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "②"},
                        {"time": p3['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "③"}
                    ]
                }

    return ew_result

def compute_radar_channel_and_markdown(df: pd.DataFrame, ticker: str = "US.NVDA") -> Dict[str, Any]:
    """
    計算標準墨菲平行通道、重大防守底座、艾略特波浪幾何與可審計 AI Markdown
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

    # 1. 提取客觀波段極值點
    sw_highs, sw_lows = find_swing_pivots(df, window=8)
    if len(sw_highs) < 2 or len(sw_lows) < 2:
        sw_highs, sw_lows = find_swing_pivots(df, window=4)

    # 2. 艾略特波浪理論計算 (LuxAlgo / EWT 鐵律體系)
    ew_data = extract_elliott_wave_pattern(df, sw_highs, sw_lows)

    # 3. 人性化 Major Support（鎖定近 120 根 K 線的結構起漲平台）
    active_lookback = min(n, 120)
    recent_low_slice = lows[-active_lookback:]
    major_support_val = float(np.percentile(recent_low_slice, 10))
    if sw_lows:
        valid_candidates = [p["price"] for p in sw_lows if p["idx"] >= (n - active_lookback)]
        if valid_candidates:
            major_support_val = min(valid_candidates)

    # 4. 即時 S/R 水平線 (取最近一個波峰與波谷)
    recent_res = float(sw_highs[-1]["price"]) if sw_highs else float(highs[-20:].max())
    recent_sup = float(sw_lows[-1]["price"]) if sw_lows else float(lows[-20:].min())

    # 5. 標準墨菲平行通道構建 (Murphy Parallel Channel)
    macro_channel = None
    curr_res_val, curr_sup_val = recent_res, recent_sup
    h1, h2, l1, l2 = None, None, None, None

    if len(sw_lows) >= 2 and len(sw_highs) >= 1:
        l1, l2 = sw_lows[-2], sw_lows[-1]
        dx_l = max(1, l2["idx"] - l1["idx"])
        slope = (l2["price"] - l1["price"]) / dx_l

        relevant_highs = highs[l1["idx"]:]
        channel_height = max(10.0, float(np.max(relevant_highs) - np.min(lows[l1["idx"]:])))
        
        h2 = sw_highs[-1] if sw_highs else {"idx": last_idx, "time": str(times[last_idx]), "price": curr_price}
        h1 = sw_highs[-2] if len(sw_highs) >= 2 else h2

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

    # 6. 生成嚴謹可審計的 AI 專用 Markdown 日誌
    h1_str = f"{h1['time']} (${h1['price']:.2f})" if h1 else "--"
    h2_str = f"{h2['time']} (${h2['price']:.2f})" if h2 else "--"
    l1_str = f"{l1['time']} (${l1['price']:.2f})" if l1 else "--"
    l2_str = f"{l2['time']} (${l2['price']:.2f})" if l2 else "--"
    h_span = abs(curr_res_val - curr_sup_val)
    channel_pos_pct = ((curr_price - curr_sup_val) / max(0.01, h_span)) * 100.0

    # 格式化艾略特波浪描述文本
    if ew_data:
        ew_p0_str = f"{ew_data['p0']['time']} (${ew_data['p0']['price']:.2f})"
        ew_p1_str = f"{ew_data['p1']['time']} (${ew_data['p1']['price']:.2f})"
        ew_p2_str = f"{ew_data['p2']['time']} (${ew_data['p2']['price']:.2f})"
        ew_p3_str = f"{ew_data['p3']['time']} (${ew_data['p3']['price']:.2f})"
        ew_p4_str = f"{ew_data['p4']['time']} (${ew_data['p4']['price']:.2f})" if ew_data.get('p4') else "--"
        ew_p5_str = f"{ew_data['p5']['time']} (${ew_data['p5']['price']:.2f})" if ew_data.get('p5') else "--"

        ew_section = f"""#### 2. 艾略特波浪 (Elliott Wave · LuxAlgo 鐵律模型)
- **當前浪級形態**: **{ew_data['pattern']}** ({ew_data['stage']})
- **推動浪幅審核**: 浪①長度: ${ew_data['w1_len']:.2f} | 浪③長度: ${ew_data['w3_len']:.2f} | 浪⑤長度: ${ew_data['w5_len']:.2f} (✅ 滿足浪③非最短鐵律)
- **浪級錨點坐標**:
  - ⓪ 起點: [{ew_p0_str}] ➔ ① 頂: [{ew_p1_str}]
  - ② 底: [{ew_p2_str}] ➔ ③ 頂: [{ew_p3_str}]
  - ④ 底: [{ew_p4_str}] ➔ ⑤ 頂: [{ew_p5_str}]
- **波浪目標與失效邊界**:
  - 🎯 Target 1 (1.000x 對稱空間): **${ew_data['target_1']:.2f}**
  - 🎯 Target 2 (1.618x 費氏擴展): **${ew_data['target_2']:.2f}**
  - 🛡️ 鐵律防守失效線 (Invalidation SL): **${ew_data['invalidation']:.2f}** (跌破則推動浪結構遭破壞)"""
    else:
        ew_section = """#### 2. 艾略特波浪 (Elliott Wave)
- **當前浪級形態**: ⚪ 處於複雜波段整理中 (未觸發經典標準 5 浪鐵律結構)
- **備註**: 建議以約翰·墨菲平行通道與 S/R 邊界為主要進出基準。"""

    ai_markdown = f"""### 📊 【{ticker} 日線技術幾何、墨菲通道與艾略特波浪審計報告】
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

{ew_section}

#### 3. 空間目標推演 (Fibonacci Confluence 重合共振)
- 上方突破 Target 1 (0.618x 通道擴展): **${(curr_res_val + h_span * 0.618):.2f}**
- 上方極限 Target 2 (1.000x 通道對稱翻倍): **${(curr_res_val + h_span * 1.000):.2f}**
- 下方破位防守 Target (下軌跌破 0.618x): **${(curr_sup_val - h_span * 0.618):.2f}**

---
#### 4. 給 AI 策略軍師的診斷指令 (Direct Prompt):
1. **通道與波浪共振審計**：現價 ${curr_price:.2f} 處於墨菲通道的 {channel_pos_pct:.1f}% 分位，結合艾略特波浪當前狀態，多頭是處於第 ⑤ 浪衝頂還是主升浪中繼？
2. **多空動能評估**：當前 K 線是在回踩動態下軌 (${curr_sup_val:.2f}) 尋求支撐，還是在測試通道上軌 (${curr_res_val:.2f}) 醞釀突破或背離？
3. **冷血風控邊界**：若失守動態支撐 ${curr_sup_val:.2f} 或波浪失效線 (${ew_data['invalidation'] if ew_data else major_support_val:.2f})，距離 Major Support (${major_support_val:.2f}) 的盈虧比是否支持止損防守？
"""

    return {
        "status": "success",
        "ticker": ticker,
        "curr_price": curr_price,
        "major_support": round(major_support_val, 2),
        "recent_res": round(recent_res, 2),
        "recent_sup": round(recent_sup, 2),
        "macro_channel": macro_channel,
        "elliott_wave": ew_data,
        "ai_markdown": ai_markdown
    }
