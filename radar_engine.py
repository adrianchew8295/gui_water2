# 文件名: radar_engine.py
# 职责: 纯数学计算 12 档标的的昨日极值 (PDH/PDL)、1H EMA20 动态防守线与攻防阶梯

import os
import pandas as pd
import numpy as np

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")

def calculate_ema(series: pd.Series, span: int = 20) -> pd.Series:
    """计算指数移动平均线 (EMA)"""
    return series.ewm(span=span, adjust=False).mean()

def compute_radar_metrics(code: str, live_price: float = None):
    """
    计算单个标的的宏观战区与日内攻防阶梯
    返回包含: PDH, PDL, EMA20, Trend Bias, 买入地板, 天花板阻力的字典
    """
    clean_name = code.replace(".", "_")
    day_csv = os.path.join(DATA_DIR, f"{clean_name}_DAY.csv")
    h1_csv = os.path.join(DATA_DIR, f"{clean_name}_1H.csv")

    metrics = {
        "code": code,
        "pdh": 0.0,
        "pdl": 0.0,
        "ema20_1h": 0.0,
        "trend_bias": "⚪ 整理中",
        "floor_zone": "--",
        "ceiling_zone": "--",
        "vol_ratio": 1.0,
        "action_hint": "☕ 观望待机"
    }

    # 1. 日线提取昨日极值 (PDH / PDL)
    if os.path.exists(day_csv):
        try:
            df_day = pd.read_csv(day_csv)
            df_day.columns = [c.lower().strip() for c in df_day.columns]
            if len(df_day) >= 2:
                prev_day = df_day.iloc[-2]
                metrics["pdh"] = float(prev_day.get('high', 0.0))
                metrics["pdl"] = float(prev_day.get('low', 0.0))
                
                # 计算 20 日均量比
                if 'volume' in df_day.columns and len(df_day) >= 20:
                    avg_v = df_day['volume'].tail(20).mean()
                    cur_v = df_day.iloc[-1]['volume']
                    metrics["vol_ratio"] = round(cur_v / avg_v, 2) if avg_v > 0 else 1.0
        except Exception:
            pass

    # 2. 1H 计算 EMA20 动态防守中枢
    if os.path.exists(h1_csv):
        try:
            df_1h = pd.read_csv(h1_csv)
            df_1h.columns = [c.lower().strip() for c in df_1h.columns]
            if len(df_1h) >= 20:
                df_1h['ema20'] = calculate_ema(df_1h['close'], span=20)
                metrics["ema20_1h"] = float(df_1h.iloc[-1]['ema20'])
        except Exception:
            pass

    # 3. 结合实时现价定调攻防区间与 Trend Bias
    cur_p = live_price if (live_price and live_price > 0) else metrics["ema20_1h"]
    pdh = metrics["pdh"]
    pdl = metrics["pdl"]
    ema = metrics["ema20_1h"]

    if cur_p > 0:
        # 判定 Trend Bias
        if ema > 0 and cur_p >= ema:
            metrics["trend_bias"] = "🟢 多头主攻" if cur_p >= pdh else "🟢 均线上方"
        elif ema > 0 and cur_p < ema:
            metrics["trend_bias"] = "🔴 空头承压" if cur_p <= pdl else "🔴 均线下方"

        # 战区买入地板 (RBS) 与卖出天花板 (SBR)
        rbs_low = pdl if pdl > 0 else (cur_p * 0.98)
        rbs_high = ema if (ema > 0 and ema < cur_p) else (cur_p * 0.99)
        metrics["floor_zone"] = f"${min(rbs_low, rbs_high):,.2f} ~ ${max(rbs_low, rbs_high):,.2f}"

        sbr_low = cur_p * 1.01 if cur_p >= pdh else pdh
        sbr_high = sbr_low * 1.015
        metrics["ceiling_zone"] = f"${sbr_low:,.2f} ~ ${sbr_high:,.2f}"

        # 实战指令提示
        if pdh > 0 and cur_p >= pdh:
            metrics["action_hint"] = "🔥 强势突破中"
        elif pdl > 0 and cur_p <= pdl:
            metrics["action_hint"] = "🛑 踩踏寻底中"
        elif ema > 0 and abs(cur_p - ema) / cur_p < 0.005:
            metrics["action_hint"] = "🎯 EMA20 伏击区"
        else:
            metrics["action_hint"] = "☕ 处于中继通道"

    return metrics
