# 文件名: radar_engine.py
# 職責: 提取昨日極值 (PDH/PDL)、今日盤前極值 (PMH/PML)、1H EMA20 均線及動態攻防階梯

import os
import datetime
import pandas as pd
import numpy as np
import pytz

tz_ny = pytz.timezone("America/New_York")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")

def calculate_ema(series: pd.Series, span: int = 20) -> pd.Series:
    """計算指數移動平均線 (EMA)"""
    return series.ewm(span=span, adjust=False).mean()

def extract_premarket_extremes(code: str):
    """
    從當日 5M 數據中提取美東 04:00~09:30 的盤前最高 (PMH) 與最低 (PML)
    """
    clean_name = code.replace(".", "_")
    csv_5m = os.path.join(DATA_DIR, f"{clean_name}_5M.csv")
    
    pmh, pml = 0.0, 0.0
    if not os.path.exists(csv_5m):
        return pmh, pml

    try:
        df = pd.read_csv(csv_5m)
        df.columns = [c.lower().strip() for c in df.columns]
        if df.empty or 'time_key' not in df.columns:
            return pmh, pml
            
        df['dt'] = pd.to_datetime(df['time_key'])
        
        # 獲取最新記錄日期
        latest_date = df['dt'].dt.date.max()
        df_today = df[df['dt'].dt.date == latest_date]
        
        # 過濾美東盤前時段 (04:00:00 <= time < 09:30:00)
        df_pm = df_today[(df_today['dt'].dt.time >= datetime.time(4, 0)) & 
                         (df_today['dt'].dt.time < datetime.time(9, 30))]
        
        if not df_pm.empty:
            pmh = float(df_pm['high'].max())
            pml = float(df_pm['low'].min())
    except Exception:
        pass

    return pmh, pml

def compute_radar_metrics(code: str, live_price: float = None):
    """
    計算單個標的的宏觀戰區與日內攻防階梯 (融合 PDH/PDL、PMH/PML 與 1H EMA20)
    """
    clean_name = code.replace(".", "_")
    day_csv = os.path.join(DATA_DIR, f"{clean_name}_DAY.csv")
    h1_csv = os.path.join(DATA_DIR, f"{clean_name}_1H.csv")

    metrics = {
        "code": code,
        "pdh": 0.0,
        "pdl": 0.0,
        "pmh": 0.0,
        "pml": 0.0,
        "ema20_1h": 0.0,
        "trend_bias": "⚪ 整理中",
        "floor_zone": "--",
        "ceiling_zone": "--",
        "vol_ratio": 1.0,
        "action_hint": "☕ 觀望待機",
        "session_type": "REGULAR"
    }

    # 1. 提取盤前極值 (PMH / PML)
    pmh, pml = extract_premarket_extremes(code)
    metrics["pmh"] = pmh
    metrics["pml"] = pml

    # 判斷當前美東時段
    now_ny = datetime.datetime.now(tz_ny)
    cur_time = now_ny.time()
    is_premarket = datetime.time(4, 0) <= cur_time < datetime.time(9, 30)
    metrics["session_type"] = "PREMARKET" if is_premarket else "REGULAR"

    # 2. 日線提取昨日極值 (PDH / PDL) 與 20 日均量比
    if os.path.exists(day_csv):
        try:
            df_day = pd.read_csv(day_csv)
            df_day.columns = [c.lower().strip() for c in df_day.columns]
            if len(df_day) >= 2:
                prev_day = df_day.iloc[-2]
                metrics["pdh"] = float(prev_day.get('high', 0.0))
                metrics["pdl"] = float(prev_day.get('low', 0.0))
                
                if 'volume' in df_day.columns and len(df_day) >= 20:
                    avg_v = df_day['volume'].tail(20).mean()
                    cur_v = df_day.iloc[-1]['volume']
                    metrics["vol_ratio"] = round(cur_v / avg_v, 2) if avg_v > 0 else 1.0
        except Exception:
            pass

    # 3. 1H 計算 EMA20 均線
    if os.path.exists(h1_csv):
        try:
            df_1h = pd.read_csv(h1_csv)
            df_1h.columns = [c.lower().strip() for c in df_1h.columns]
            if len(df_1h) >= 20:
                df_1h['ema20'] = calculate_ema(df_1h['close'], span=20)
                metrics["ema20_1h"] = float(df_1h.iloc[-1]['ema20'])
        except Exception:
            pass

    # 4. 戰區動態定調
    cur_p = live_price if (live_price and live_price > 0) else metrics["ema20_1h"]
    pdh = metrics["pdh"]
    pdl = metrics["pdl"]
    ema = metrics["ema20_1h"]

    if cur_p > 0:
        # 判定 Trend Bias
        if ema > 0 and cur_p >= ema:
            metrics["trend_bias"] = "🟢 多頭主攻" if (pdh > 0 and cur_p >= pdh) else "🟢 均線上主推"
        elif ema > 0 and cur_p < ema:
            metrics["trend_bias"] = "🔴 空頭承壓" if (pdl > 0 and cur_p <= pdl) else "🔴 均線下回踩"

        # RBS 地板區：若有盤前低點且處於盤前，優先參考 PML
        floor_candidates = [p for p in [pdl, pml, ema] if p > 0 and p <= cur_p]
        if floor_candidates:
            rbs_base = max(floor_candidates)
            metrics["floor_zone"] = f"${rbs_base * 0.998:,.2f} ~ ${rbs_base:,.2f}"
        else:
            metrics["floor_zone"] = f"${cur_p * 0.99:,.2f} ~ ${cur_p:,.2f}"

        # SBR 天花板區：若有盤前高點，優先參考 PMH / PDH
        ceil_candidates = [p for p in [pdh, pmh] if p > 0 and p >= cur_p]
        if ceil_candidates:
            sbr_base = min(ceil_candidates)
            metrics["ceiling_zone"] = f"${sbr_base:,.2f} ~ ${sbr_base * 1.002:,.2f}"
        else:
            metrics["ceiling_zone"] = f"${cur_p * 1.005:,.2f} ~ ${cur_p * 1.015:,.2f}"

        # 實戰操作指令提示
        if is_premarket:
            metrics["action_hint"] = "🟡 盤前撮合中 (盯緊 PMH/PML)"
        elif pmh > 0 and cur_p >= pmh:
            metrics["action_hint"] = "🔥 突破盤前高點 (多頭加速)"
        elif pml > 0 and cur_p <= pml:
            metrics["action_hint"] = "🛑 跌破盤前低點 (空頭承壓)"
        elif ema > 0 and abs(cur_p - ema) / cur_p < 0.003:
            metrics["action_hint"] = "🎯 1H EMA20 伏擊區"
        else:
            metrics["action_hint"] = "☕ 處於常規震盪區間"

    return metrics
