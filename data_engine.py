# 文件名: data_engine.py
# 職責: 模組 A 數據中樞 (全時段 5M/1H/DAY 連續錄影 + 斷點自愈 + 關鍵位提取 + 歷史落盤)

import os
import time
import json
import datetime
import pytz
import pandas as pd
import numpy as np

tz_ny = pytz.timezone("America/New_York")
tz_my = pytz.timezone("Asia/Kuala_Lumpur")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")
WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist.json")
LOG_PATH = os.path.join(BASE_DIR, "system_audit.log")

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

def get_active_session_info():
    """判定當前美股交易時段 (盤前/常規/午休/盤後/休市)"""
    now_ny = datetime.datetime.now(tz_ny)
    weekday = now_ny.weekday() # 0-4 為週一至週五
    
    if weekday >= 5:
        return "WEEKEND", "🌴 週末休市", now_ny
        
    cur_time = now_ny.time()
    t_pre_start = datetime.time(4, 0)
    t_mkt_open = datetime.time(9, 30)
    t_lunch_start = datetime.time(12, 0)
    t_lunch_end = datetime.time(13, 30)
    t_mkt_close = datetime.time(16, 0)
    t_post_end = datetime.time(20, 0)
    
    if t_pre_start <= cur_time < t_mkt_open:
        return "PRE_MARKET", "🌅 美股盤前 (04:00~09:30)", now_ny
    elif t_mkt_open <= cur_time < t_lunch_start:
        return "REGULAR_MORNING", "⚡ 晨盤早戰區 (09:30~12:00)", now_ny
    elif t_lunch_start <= cur_time < t_lunch_end:
        return "LUNCH_LULL", "⚠️ 美東午休垃圾時間 (12:00~13:30 鎖定)", now_ny
    elif t_lunch_end <= cur_time < t_mkt_close:
        return "REGULAR_AFTERNOON", "🔥 尾盤決戰區 (13:30~16:00)", now_ny
    elif t_mkt_close <= cur_time < t_post_end:
        return "POST_MARKET", "🌙 美股盤後 (16:00~20:00)", now_ny
    else:
        return "CLOSED", "💤 夜間休市 (20:00~04:00)", now_ny


class MarketDataEngine:
    """市場全時段數據引擎"""
    def __init__(self):
        self.host = "127.0.0.1"
        self.port = 11111

    def load_watchlist(self):
        """讀取 12 檔核心監控資產"""
        if not os.path.exists(WATCHLIST_PATH):
            return []
        try:
            with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("assets", [])
        except Exception:
            return []

    def get_csv_path(self, code: str, ktype: str) -> str:
        safe_code = code.replace(".", "_")
        return os.path.join(DATA_DIR, f"{safe_code}_{ktype.upper()}.csv")

    def load_local_kline(self, code: str, ktype: str) -> pd.DataFrame:
        p = self.get_csv_path(code, ktype)
        if not os.path.exists(p):
            return pd.DataFrame()
        try:
            df = pd.read_csv(p)
            if "time_key" in df.columns:
                df["time_key"] = pd.to_datetime(df["time_key"])
                df = df.sort_values("time_key").reset_index(drop=True)
            return df
        except Exception:
            return pd.DataFrame()

    def sync_asset_deep_history(self, code: str, bars_5m: int = 1500, bars_day: int = 250):
        """全時段連續錄影與歷史對齊 (5M 全時段 + 1H 聚合 + DAY)"""
        try:
            from moomoo import OpenQuoteContext, SubType, KLType, AuType, RET_OK
            quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
            
            # 1. 抓取 5M (含盤前盤後)
            ret_5m, df_5m, _ = quote_ctx.request_history_kline(
                code=code,
                ktype=KLType.K_5M,
                autype=AuType.NONE,
                max_count=bars_5m
            )
            
            # 2. 抓取 DAY
            ret_day, df_day, _ = quote_ctx.request_history_kline(
                code=code,
                ktype=KLType.K_DAY,
                autype=AuType.NONE,
                max_count=bars_day
            )
            quote_ctx.close()

            # 落盤 5M
            if ret_5m == RET_OK and not df_5m.empty:
                df_5m["time_key"] = pd.to_datetime(df_5m["time_key"])
                df_5m = df_5m.sort_values("time_key").drop_duplicates(subset=["time_key"], keep="last")
                df_5m.to_csv(self.get_csv_path(code, "5M"), index=False)
                
                # 本地聚合 1H
                df_1h = self._resample_5m_to_1h(df_5m)
                if not df_1h.empty:
                    df_1h.to_csv(self.get_csv_path(code, "1H"), index=False)

            # 落盤 DAY
            if ret_day == RET_OK and not df_day.empty:
                df_day["time_key"] = pd.to_datetime(df_day["time_key"])
                df_day = df_day.sort_values("time_key").drop_duplicates(subset=["time_key"], keep="last")
                df_day.to_csv(self.get_csv_path(code, "DAY"), index=False)

            return True, "OK"
        except Exception as e:
            return False, str(e)

    def _resample_5m_to_1h(self, df_5m: pd.DataFrame) -> pd.DataFrame:
        """將 5M 柱線重採樣合成為精確 1H K線"""
        if df_5m.empty:
            return pd.DataFrame()
        df = df_5m.copy()
        df.set_index("time_key", inplace=True)
        agg_dict = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
            "turnover": "sum"
        }
        if "code" in df.columns:
            agg_dict["code"] = "first"
        if "name" in df.columns:
            agg_dict["name"] = "first"

        df_1h = df.resample("1h", closed="left", label="left").agg(agg_dict).dropna(subset=["close"]).reset_index()
        return df_1h

    def extract_key_levels(self, code: str) -> dict:
        """提取 PDH/PDL (昨日極值) 與 PMH/PML (盤前極值)"""
        levels = {"PDH": None, "PDL": None, "PDC": None, "PMH": None, "PML": None, "CUR_PRICE": None}
        
        # 讀取日線取昨日極值
        df_day = self.load_local_kline(code, "DAY")
        if len(df_day) >= 2:
            prev_row = df_day.iloc[-2]
            levels["PDH"] = float(prev_row["high"])
            levels["PDL"] = float(prev_row["low"])
            levels["PDC"] = float(prev_row["close"])
            levels["CUR_PRICE"] = float(df_day.iloc[-1]["close"])

        # 讀取 5M 取今日盤前極值 (美東 04:00~09:30)
        df_5m = self.load_local_kline(code, "5M")
        if not df_5m.empty:
            latest_time = df_5m["time_key"].max()
            today_str = latest_time.strftime("%Y-%m-%d")
            
            # 過濾今日盤前
            df_pm = df_5m[
                (df_5m["time_key"].dt.strftime("%Y-%m-%d") == today_str) &
                (df_5m["time_key"].dt.time >= datetime.time(4, 0)) &
                (df_5m["time_key"].dt.time < datetime.time(9, 30))
            ]
            if not df_pm.empty:
                levels["PMH"] = float(df_pm["high"].max())
                levels["PML"] = float(df_pm["low"].min())
            
            # 若有更即時的現價則更新
            levels["CUR_PRICE"] = float(df_5m.iloc[-1]["close"])

        return levels


# 全域實例化 (解耦接口)
hub_engine = MarketDataEngine()
