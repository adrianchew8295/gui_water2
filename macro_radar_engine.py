# 文件名: macro_radar_engine.py
# 職責: 
# 1. 約翰·墨菲 (John J. Murphy) 標準平行通道幾何與重大防守底座
# 2. 艾略特波浪理論：最新波段錨定 (Recent-Anchor)、推動浪 (⓪~⑤) 與 ABC 調整浪 (ⓐ~ⓒ) 雙軌精確打點
# 3. 輸出包含雙重共振數據的 AI 策略軍師專用 Markdown 日誌

import numpy as np
import pandas as pd
from typing import Dict, Any, List

def find_lux_zigzag_pivots(df: pd.DataFrame, left: int = 4, right: int = 1):
    """
    復刻 LuxAlgo 擺動極值算法 (ta.pivothigh / ta.pivotlow)
    左側看 left 根，右側僅需 right (1) 根即時確認，消除滯後盲區
    """
    highs = df['high'].values
    lows = df['low'].values
    times = df['time_clean'].values
    n = len(df)
    
    pivots = []
    
    for i in range(left, n - right):
        is_ph = True
        for l in range(1, left + 1):
            if highs[i] < highs[i - l]:
                is_ph = False; break
        if is_ph:
            for r in range(1, right + 1):
                if highs[i] < highs[i + r]:
                    is_ph = False; break
        if is_ph:
            pivots.append({"idx": i, "time": str(times[i])[:10], "price": float(highs[i]), "type": "high"})

        is_pl = True
        for l in range(1, left + 1):
            if lows[i] > lows[i - l]:
                is_pl = False; break
        if is_pl:
            for r in range(1, right + 1):
                if lows[i] > lows[i + r]:
                    is_pl = False; break
        if is_pl:
            pivots.append({"idx": i, "time": str(times[i])[:10], "price": float(lows[i]), "type": "low"})

    pivots = sorted(pivots, key=lambda x: x["idx"])
    clean_pivots = []
    for p in pivots:
        if not clean_pivots:
            clean_pivots.append(p)
        else:
            last_p = clean_pivots[-1]
            if last_p["type"] == p["type"]:
                if (p["type"] == "high" and p["price"] > last_p["price"]) or (p["type"] == "low" and p["price"] < last_p["price"]):
                    clean_pivots[-1] = p
            else:
                clean_pivots.append(p)
                
    return clean_pivots

def extract_elliott_wave_pattern(df: pd.DataFrame, pivots: list) -> Dict[str, Any]:
    """
    強制錨定最新 90 根 K 線，嚴格識別：
    1. 多頭 5 浪推動 (⓪ ① ② ③ ④ ⑤)
    2. 主升第 3 浪爆發 (⓪ ① ② ③)
    3. ABC 調整浪結構 (ⓐ ⓑ ⓒ)
    """
    if len(pivots) < 3:
        return None

    n = len(df)
    # 只取最近 90 根 K 線範圍內的最新拐點，杜絕穿越到遠古歷史
    recent_pivots = [p for p in pivots if p["idx"] >= max(0, n - 90)]
    if len(recent_pivots) < 3:
        recent_pivots = pivots[-5:] if len(pivots) >= 5 else pivots

    # 1. 優先檢驗：最新波段是否為標準多頭 5 浪推動 (0 -> 1 -> 2 -> 3 -> 4 -> 5)
    if len(recent_pivots) >= 6:
        cand6 = recent_pivots[-6:]
        if [p['type'] for p in cand6] == ['low', 'high', 'low', 'high', 'low', 'high']:
            p0, p1, p2, p3, p4, p5 = cand6
            w1 = p1['price'] - p0['price']
            w3 = p3['price'] - p2['price']
            w5 = p5['price'] - p4['price']

            # 鐵律驗證：浪3非最短、浪4不破浪1頂、高點逐級抬高
            if (w1 > 0 and w3 > 0 and w5 > 0 and 
                p2['price'] > p0['price'] and 
                p4['price'] > p1['price'] and 
                p3['price'] > p1['price'] and 
                p5['price'] > p3['price'] and 
                w3 != min(w1, w3, w5)):

                return {
                    "pattern": "🟢 多頭 5 浪推動結構 (Motive 5-Wave)",
                    "stage": "第 ⑤ 浪衝頂 / 醞釀頂部結構",
                    "p0": p0, "p1": p1, "p2": p2, "p3": p3, "p4": p4, "p5": p5,
                    "w1_len": round(w1, 2), "w3_len": round(w3, 2), "w5_len": round(w5, 2),
                    "target_1": round(p4['price'] + w1, 2),
                    "target_2": round(p4['price'] + 0.618 * (w1 + w3), 2),
                    "invalidation": round(p1['price'], 2),
                    "wave_lines": [{"time": p["time"], "value": p["price"]} for p in cand6],
                    "wave_markers": [
                        {"time": p0['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "⓪"},
                        {"time": p1['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "①"},
                        {"time": p2['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "②"},
                        {"time": p3['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "③"},
                        {"time": p4['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "④"},
                        {"time": p5['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "⑤"}
                    ]
                }

    # 2. 次級檢驗：最新波段是否處於第 3 浪主升推進 (0 -> 1 -> 2 -> 3)
    if len(recent_pivots) >= 4:
        cand4 = recent_pivots[-4:]
        if [p['type'] for p in cand4] == ['low', 'high', 'low', 'high']:
            p0, p1, p2, p3 = cand4
            w1 = p1['price'] - p0['price']
            w3 = p3['price'] - p2['price']
            if w1 > 0 and w3 > 0 and p2['price'] > p0['price'] and p3['price'] > p1['price']:
                return {
                    "pattern": "🚀 處於第 ③ 浪主升推動中 (Wave 3 Impulse)",
                    "stage": "主升浪高能推進",
                    "p0": p0, "p1": p1, "p2": p2, "p3": p3, "p4": None, "p5": None,
                    "w1_len": round(w1, 2), "w3_len": round(w3, 2), "w5_len": 0.0,
                    "target_1": round(p2['price'] + 1.618 * w1, 2),
                    "target_2": round(p2['price'] + 2.618 * w1, 2),
                    "invalidation": round(p2['price'], 2),
                    "wave_lines": [{"time": p["time"], "value": p["price"]} for p in cand4],
                    "wave_markers": [
                        {"time": p0['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "⓪"},
                        {"time": p1['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "①"},
                        {"time": p2['time'], "position": "belowBar", "color": "#E040FB", "shape": "circle", "text": "②"},
                        {"time": p3['time'], "position": "aboveBar", "color": "#E040FB", "shape": "circle", "text": "③"}
                    ]
                }

    # 3. 調整浪檢驗：出現次高點 (峰2 < 峰1) ➔ 自動標註 ABC 調整浪 (ⓐ ⓑ ⓒ)
    if len(recent_pivots) >= 4:
        cand_abc = recent_pivots[-4:]
        # 結構: High0 -> Low_A -> High_B -> Low_C
        if [p['type'] for p in cand_abc] == ['high', 'low', 'high', 'low']:
            ph0, pa, pb, pc = cand_abc
            if pb['price'] < ph0['price']: # 頂部降低，形成典型 ABC 修復
                diff_a = ph0['price'] - pa['price']
                return {
                    "pattern": "🔴 ABC 調整浪修正結構 (Corrective ABC Wave)",
                    "stage": "處於 ⓒ 浪尋底或修復蓄勢階段",
                    "p0": ph0, "p1": pa, "p2": pb, "p3": pc, "p4": None, "p5": None,
                    "w1_len": round(diff_a, 2), "w3_len": round(pb['price'] - pc['price'], 2), "w5_len": 0.0,
                    "target_1": round(pb['price'] - 1.0 * diff_a, 2),
                    "target_2": round(pb['price'] - 1.618 * diff_a, 2),
                    "invalidation": round(ph0['price'], 2),
                    "wave_lines": [{"time": p["time"], "value": p["price"]} for p in cand_abc],
                    "wave_markers": [
                        {"time": ph0['time'], "position": "aboveBar", "color": "#FF7043", "shape": "circle", "text": "Top"},
                        {"time": pa['time'], "position": "belowBar", "color": "#FF7043", "shape": "circle", "text": "ⓐ"},
                        {"time": pb['time'], "position": "aboveBar", "color": "#FF7043", "shape": "circle", "text": "ⓑ"},
                        {"time": pc['time'], "position": "belowBar", "color": "#FF7043", "shape": "circle", "text": "ⓒ"}
                    ]
                }

    # 4. 兜底波段骨架：提取最近 4~5 個最新拐點標註
    recent_pts = recent_pivots[-5:] if len(recent_pivots) >= 5 else recent_pivots
    lines = [{"time": p["time"], "value": p["price"]} for p in recent_pts]
    markers = []
    for idx, p in enumerate(recent_pts):
        lbl = f"L{idx+1}" if p["type"] == "low" else f"H{idx+1}"
        pos = "belowBar" if p["type"] == "low" else "aboveBar"
        markers.append({"time": p["time"], "position": pos, "color": "#E040FB", "shape": "circle", "text": lbl})

    return {
        "pattern": "🌊 擺動波段骨架 (Swing Wave Skeleton)",
        "stage": "波段整理推進中",
        "p0": recent_pts[0], "p1": recent_pts[-1],
        "w1_len": 0.0, "w3_len": 0.0, "w5_len": 0.0,
        "target_1": round(recent_pts[-1]["price"] * 1.05, 2),
        "target_2": round(recent_pts[-1]["price"] * 1.10, 2),
        "invalidation": round(recent_pts[0]["price"], 2),
        "wave_lines": lines,
        "wave_markers": markers
    }

def compute_radar_channel_and_markdown(df: pd.DataFrame, ticker: str = "US.NVDA") -> Dict[str, Any]:
    """計算墨菲通道、波浪骨架與 AI 審計日誌"""
    if df is None or len(df) < 20:
        return {"status": "fail", "msg": "K線樣本數不足"}

    time_col = 'time_clean' if 'time_clean' in df.columns else ('time_key' if 'time_key' in df.columns else df.columns[0])
    df['time_clean'] = df[time_col].astype(str).str.slice(0, 10)
    
    times = df['time_clean'].values
    highs = df['high'].values
    lows = df['low'].values
    closes = df['close'].values
    n = len(df)
    last_idx = n - 1
    curr_price = float(closes[-1])

    # 1. 提取 LuxAlgo 擺動點
    pivots = find_lux_zigzag_pivots(df, left=4, right=1)
    if len(pivots) < 4:
        pivots = find_lux_zigzag_pivots(df, left=2, right=1)

    sw_highs = [p for p in pivots if p["type"] == "high"]
    sw_lows = [p for p in pivots if p["type"] == "low"]

    # 2. 艾略特波浪計算 (最新波段錨定)
    ew_data = extract_elliott_wave_pattern(df, pivots)

    # 3. Major Support（近 120 根結構起漲底座）
    active_lookback = min(n, 120)
    recent_low_slice = lows[-active_lookback:]
    major_support_val = float(np.percentile(recent_low_slice, 10))
    if sw_lows:
        valid_candidates = [p["price"] for p in sw_lows if p["idx"] >= (n - active_lookback)]
        if valid_candidates:
            major_support_val = min(valid_candidates)

    # 4. 即時 S/R 水平線
    recent_res = float(sw_highs[-1]["price"]) if sw_highs else float(highs[-20:].max())
    recent_sup = float(sw_lows[-1]["price"]) if sw_lows else float(lows[-20:].min())

    # 5. 墨菲標準平行通道 (Murphy Parallel Channel)
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

    # 6. 生成可審計的 Markdown 日誌
    h1_str = f"{h1['time']} (${h1['price']:.2f})" if h1 else "--"
    h2_str = f"{h2['time']} (${h2['price']:.2f})" if h2 else "--"
    l1_str = f"{l1['time']} (${l1['price']:.2f})" if l1 else "--"
    l2_str = f"{l2['time']} (${l2['price']:.2f})" if l2 else "--"
    h_span = abs(curr_res_val - curr_sup_val)
    channel_pos_pct = ((curr_price - curr_sup_val) / max(0.01, h_span)) * 100.0

    if ew_data:
        ew_section = f"""#### 2. 艾略特波浪 (Elliott Wave · 最新波段模型)
- **當前浪級形態**: **{ew_data['pattern']}** ({ew_data.get('stage', '')})
- **波浪目標與防守**:
  - 🎯 Target 1: **${ew_data['target_1']:.2f}**
  - 🎯 Target 2: **${ew_data['target_2']:.2f}**
  - 🛡️ 結構失效防守線: **${ew_data['invalidation']:.2f}**"""
    else:
        ew_section = """#### 2. 艾略特波浪 (Elliott Wave)
- **當前形態**: ⚪ 處於震盪整理中 (未觸發經典浪形)"""

    ai_markdown = f"""### 📊 【{ticker} 日線技術幾何、墨菲通道與艾略特波浪審計報告】
**審計基準日期**: {times[-1]} | **最新收盤現價**: ${curr_price:.2f} | **數據樣本總跨度**: {times[0]} 至 {times[-1]} (共 {n} 根日K)

#### 1. 當前波段幾何戰區 (John J. Murphy 標準平行通道體系)
- **通道形態判定**: {macro_channel['trend_type'] if macro_channel else '區間箱體整理'} (每日斜率推升: +${macro_channel['slope']:.2f} USD)
- **通道幾何高度**: **${h_span:.2f} USD**
- **動態阻力上軌 (Upper Channel)**: 基準連線至 [{h2_str}] ➔ 當前天花板: **${curr_res_val:.2f}**
- **動態支撐下軌 (Lower Channel)**: 錨點 P1 [{l1_str}] ➔ P2 [{l2_str}] ➔ 當前地板: **${curr_sup_val:.2f}**
- **現價相對通道位置**: **{channel_pos_pct:.1f}%**
- **即時攻防**: RES: ${recent_res:.2f} | SUP: ${recent_sup:.2f}
- **⭐ MAJOR SUPPORT (核心結構防守底座)**: **${major_support_val:.2f}**

{ew_section}

#### 3. 空間目標推演 (Fibonacci Confluence)
- 上方突破 Target 1 (0.618x 通道擴展): **${(curr_res_val + h_span * 0.618):.2f}**
- 上方極限 Target 2 (1.000x 通道對稱翻倍): **${(curr_res_val + h_span * 1.000):.2f}**
- 下方破位防守 Target (下軌跌破 0.618x): **${(curr_sup_val - h_span * 0.618):.2f}**

---
#### 4. 給 AI 策略軍師的診斷指令 (Direct Prompt):
1. **通道與波浪共振**：現價 ${curr_price:.2f} 處於通道 {channel_pos_pct:.1f}% 分位，結合當前波浪形態（{ew_data['pattern'] if ew_data else '整理'}），多頭防守力度如何？
2. **多空動能評估**：當前 K 線是在回踩動態下軌 (${curr_sup_val:.2f}) 尋求支撐，還是在構築頂部次高點回調？
3. **風控邊界**：若失守動態支撐 ${curr_sup_val:.2f}，距離 Major Support (${major_support_val:.2f}) 的盈虧比是否支持防守？
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
