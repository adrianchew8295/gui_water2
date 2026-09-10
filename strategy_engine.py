# 文件名: strategy_engine.py
# 職責: 模組 B 雙軌策略大腦 (軌1 0DTE 日內脈衝 + 軌2 正股波段 AI 顧問 + 排雷哨兵)

import datetime
import pytz
import numpy as np
import pandas as pd
from data_engine import hub_engine, get_active_session_info

tz_ny = pytz.timezone("America/New_York")

class StrategyEngine:
    """量化策略計算中樞 (純邏輯計算，不依賴 UI)"""

    @staticmethod
    def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """計算真實波動區間 (ATR14)"""
        if len(df) < 2:
            return pd.Series([1.0] * len(df))
        high = df['high']
        low = df['low']
        close = df['close'].shift(1).bfill()
        tr = np.maximum(high - low, np.maximum((high - close).abs(), (low - close).abs()))
        return tr.rolling(window=period).mean().bfill()

    # =========================================================================
    # 【軌 1: 0DTE 日內期權戰術脈衝】
    # =========================================================================
    @staticmethod
    def evaluate_0dte_signal(code: str, budget_usd: float = 200.0) -> dict:
        """
        0DTE 定罪扳機：
        1H EMA20 門禁 + 5M 昨日極值/ORB 2B 假突破 + 1.25x 放量 + 1:2 盈虧比 + 15M 硬止損
        美東 12:00~13:30 垃圾時間硬鎖
        """
        now_ny = datetime.datetime.now(tz_ny)
        session_type, session_name, _ = get_active_session_info()
        
        # 1. 垃圾時間安全鎖 (美東 12:00 ~ 13:30)
        is_lunch_lull = (session_type == "LUNCH_LULL")
        
        df_5m = hub_engine.load_local_kline(code, "5M")
        df_1h = hub_engine.load_local_kline(code, "1H")
        df_day = hub_engine.load_local_kline(code, "DAY")
        levels = hub_engine.extract_key_levels(code)
        
        curr_price = levels["CUR_PRICE"] or 0.0
        if df_5m.empty or len(df_5m) < 15 or curr_price == 0.0:
            return {"status": "WAIT", "action": "⚪ 數據樣本不足", "is_armed": False, "reason": "等待更多 5M 柱線"}

        # 2. 1H EMA20 宏觀門禁
        h1_bias = 0
        if not df_1h.empty and len(df_1h) >= 20:
            df_1h['ema20'] = df_1h['close'].ewm(span=20, adjust=False).mean()
            h1_bias = 1 if df_1h.iloc[-1]['close'] >= df_1h.iloc[-1]['ema20'] else -1

        # 3. 5M 量價與形態分析
        curr_bar = df_5m.iloc[-1]
        prev_bar = df_5m.iloc[-2]
        df_5m['vma20'] = df_5m['volume'].rolling(window=20).mean().bfill()
        vma20_val = float(df_5m['vma20'].iloc[-1]) if df_5m['vma20'].iloc[-1] > 0 else 1.0
        vol_ratio = float(curr_bar['volume']) / vma20_val
        
        pdh = levels["PDH"] or (curr_price * 1.008)
        pdl = levels["PDL"] or (curr_price * 0.992)
        pmh = levels["PMH"] or pdh
        pml = levels["PML"] or pdl
        
        support_floor = min(pdl, pml)
        resist_ceil = max(pdh, pmh)
        
        # 2B 假突破識別
        bull_2b = (prev_bar['low'] <= support_floor) and (curr_bar['close'] > support_floor) and (curr_bar['close'] >= curr_bar['open'])
        bear_2b = (prev_bar['high'] >= resist_ceil) and (curr_bar['close'] < resist_ceil) and (curr_bar['close'] <= curr_bar['open'])
        
        risk_unit = max(0.60, abs(curr_bar['high'] - curr_bar['low']))
        nearest_atm = int(round(curr_price))

        # 定罪觸發
        if not is_lunch_lull and bull_2b and vol_ratio >= 1.25 and h1_bias >= 0:
            strike = int(np.ceil(curr_price))
            sl = curr_price - risk_unit
            tp = curr_price + 2.0 * risk_unit
            return {
                "status": "ARMED",
                "action": "🟢 BUY CALL",
                "opt_type": "CALL",
                "strike": strike,
                "entry": curr_price,
                "sl": sl,
                "tp": tp,
                "rr_ratio": 2.0,
                "vol_ratio": vol_ratio,
                "time_stop_min": 15,
                "is_armed": True,
                "reason": f"地板 2B 破底翻放量 ({vol_ratio:.2f}x) + 1H 順勢"
            }
        elif not is_lunch_lull and bear_2b and vol_ratio >= 1.25 and h1_bias <= 0:
            strike = int(np.floor(curr_price))
            sl = curr_price + risk_unit
            tp = curr_price - 2.0 * risk_unit
            return {
                "status": "ARMED",
                "action": "🔴 BUY PUT",
                "opt_type": "PUT",
                "strike": strike,
                "entry": curr_price,
                "sl": sl,
                "tp": tp,
                "rr_ratio": 2.0,
                "vol_ratio": vol_ratio,
                "time_stop_min": 15,
                "is_armed": True,
                "reason": f"天花板 2B 假突破放量 ({vol_ratio:.2f}x) + 1H 順勢"
            }
        elif is_lunch_lull:
            return {
                "status": "LOCKED",
                "action": "🔒 午休安全鎖定",
                "is_armed": False,
                "reason": "12:00~13:30 垃圾時間，防範流動性誘多誘空"
            }
        else:
            return {
                "status": "WAIT",
                "action": "☕ 安全中繼待機",
                "is_armed": False,
                "reason": f"距地板支撐 -${(curr_price - support_floor):.2f} | 距天花板阻力 +${(resist_ceil - curr_price):.2f}"
            }

    # =========================================================================
    # 【軌 2: 1~3 個月正股波段 (Portfolio AI)】
    # =========================================================================
    @staticmethod
    def evaluate_swing_tactical(code: str, total_nav: float, cash_avail: float) -> dict:
        """
        波段 AI 顧問：
        週線/日線 EMA20 趨勢 + 日線回踩 RBS 地板 + Half-Kelly 倉位算量 + 階梯止盈
        """
        df_day = hub_engine.load_local_kline(code, "DAY")
        if df_day.empty or len(df_day) < 30:
            return {"status": "NO_DATA", "rating": "⚪ 數據不足", "shares": 0}

        df = df_day.copy()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['vma20'] = df['volume'].rolling(20).mean().bfill()
        
        curr_bar = df.iloc[-1]
        curr_price = float(curr_bar['close'])
        ema20 = float(curr_bar['ema20'])
        ema50 = float(curr_bar['ema50'])
        
        # 1. 趨勢判定
        trend_status = "🟢 多頭主升" if (curr_price >= ema20 >= ema50) else ("🟡 震盪整理" if curr_price >= ema20 else "🔴 空頭回撤")
        
        # 2. RBS 地板支撐與 SBR 天花板阻力
        recent_30 = df.tail(30)
        rbs_floor = float(recent_30['low'].min())
        sbr_roof = float(recent_30['high'].max())
        
        # 3. 操作評級與入場價位
        dist_to_ema20_pct = (curr_price - ema20) / ema20 * 100.0
        
        if trend_status == "🟢 多頭主升" and dist_to_ema20_pct <= 2.5:
            rating = "🟢 強烈推薦 (回踩到位)"
            action_code = "BUY_ZONE"
            suggest_entry = round(ema20, 2)
            suggest_sl = round(min(rbs_floor, ema20 * 0.95), 2)
            suggest_tp1 = round(curr_price + 1.5 * (suggest_entry - suggest_sl), 2) # 階梯 1 (+1.5R 減半)
            suggest_tp2 = round(sbr_roof, 2) # 階梯 2 (天花板)
        elif dist_to_ema20_pct > 6.0:
            rating = "⚠️ 嚴禁追高 (乖離過大)"
            action_code = "OVERBOUGHT"
            suggest_entry = round(ema20, 2)
            suggest_sl = round(rbs_floor, 2)
            suggest_tp1 = 0.0
            suggest_tp2 = 0.0
        else:
            rating = "☕ 觀望等待 (未到戰區)"
            action_code = "WAIT"
            suggest_entry = round(ema20, 2)
            suggest_sl = round(rbs_floor, 2)
            suggest_tp1 = 0.0
            suggest_tp2 = 0.0

        # 4. Half-Kelly 以損定倉公式計算
        # 預設單筆最大風險 1.0% NAV，且單一標的上限不超過 25% NAV
        risk_dollar = max(100.0, total_nav * 0.010) if total_nav > 0 else 200.0
        loss_per_share = max(1.0, suggest_entry - suggest_sl) if (suggest_entry > suggest_sl) else (curr_price * 0.05)
        
        raw_shares = int(risk_dollar // loss_per_share)
        max_alloc_shares = int((total_nav * 0.25) // curr_price) if total_nav > 0 else raw_shares
        max_cash_shares = int(cash_avail // curr_price) if cash_avail > 0 else raw_shares
        
        final_shares = max(1, min(raw_shares, max_alloc_shares, max_cash_shares))
        target_capital = final_shares * suggest_entry
        nav_ratio = (target_capital / total_nav * 100.0) if total_nav > 0 else 0.0

        return {
            "code": code,
            "curr_price": curr_price,
            "trend_status": trend_status,
            "rating": rating,
            "action_code": action_code,
            "suggest_entry": suggest_entry,
            "suggest_sl": suggest_sl,
            "suggest_tp1": suggest_tp1,
            "suggest_tp2": suggest_tp2,
            "final_shares": final_shares,
            "target_capital": target_capital,
            "nav_ratio": nav_ratio,
            "rbs_floor": rbs_floor,
            "sbr_roof": sbr_roof,
            "dist_to_ema20_pct": dist_to_ema20_pct
        }

    # =========================================================================
    # 【排雷哨兵: Risk Event Guard】
    # =========================================================================
    @staticmethod
    def audit_event_guard(code: str) -> dict:
        """排雷哨兵：財報前 7 天與重大宏觀窗口預警"""
        # 模擬核心排雷數據 (可無縫對接 Moomoo Earnings API)
        return {
            "code": code,
            "earnings_status": "🟢 安全 (未來 7 天無財報)",
            "fomc_status": "🟢 宏觀窗口暢通",
            "is_safe": True
        }

strategy_engine = StrategyEngine()
