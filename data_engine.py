# 文件名: data_engine.py
# 職責: 模組 A 數據中樞 (5M 全時段分頁拉取 + 今日 get_cur_kline 實時拼接 + 1H 本地重採樣聚合 + PMH/PML 戰區提取)

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

if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR, exist_ok=True)

def get_active_session_info():
    """判定美股當前時段"""
    now_ny = datetime.datetime.now(tz_ny)
    weekday = now_ny.weekday()
    if weekday >= 5:
        return "WEEKEND", "🌴 週末休市", now_ny
        
    cur_time = now_ny.time()
    if datetime.time(4, 0) <= cur_time < datetime.time(9, 30):
        return "PRE_MARKET", "🌅 美股盤前 (04:00~09:30)", now_ny
    elif datetime.time(9, 30) <= cur_time < datetime.time(12, 0):
        return "REGULAR_MORNING", "⚡ 晨盤早戰區 (09:30~12:00)", now_ny
    elif datetime.time(12, 0) <= cur_time < datetime.time(13, 30):
        return "LUNCH_LULL", "⚠️ 美東午休垃圾時間 (12:00~13:30 鎖定)", now_ny
    elif datetime.time(13, 30) <= cur_time < datetime.time(16, 0):
        return "REGULAR_AFTERNOON", "🔥 尾盤決戰區 (13:30~16:00)", now_ny
    elif datetime.time(16, 0) <= cur_time < datetime.time(20, 0):
        return "POST_MARKET", "🌙 美股盤後 (16:00~20:00)", now_ny
    else:
        return "CLOSED", "💤 夜間休市 (20:00~04:00)", now_ny


class MarketDataEngine:
    def __init__(self, host="127.0.0.1", port=11111):
        self.host = host
        self.port = port

    def load_watchlist(self):
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

    def sync_asset_deep_history(self, code: str, max_bars: int = 1500):
        """
        拉取 5M 全時段 (04:00~20:00) 歷史 + 今日實時柱，並在本地聚合為連續無斷層的 1H 與 DAY CSV
        """
        try:
            from moomoo import OpenQuoteContext, KLType, AuType, SubType, RET_OK
            quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
            now_ny = datetime.datetime.now(tz_ny)
            
            # 1. 訂閱實時行情權限
            try:
                quote_ctx.subscribe([code], [SubType.K_5M, SubType.K_DAY])
            except Exception:
                pass

            # 2. 抓取今日正在撮合的 5M 實時柱
            ret_cur, df_cur_5m = quote_ctx.get_cur_kline(code=code, num=100, ktype=KLType.K_5M, autype=AuType.NONE)

            # 3. 分頁回溯抓取近 25 天全時段 5M 歷史
            end_date_str = now_ny.strftime("%Y-%m-%d %H:%M:%S")
            start_date_5m = (now_ny - datetime.timedelta(days=25)).strftime("%Y-%m-%d")
            
            all_5m_hist = []
            page_key = None
            while True:
                ret_h, df_chunk, page_key = quote_ctx.request_history_kline(
                    code=code,
                    start=start_date_5m,
                    end=end_date_str,
                    ktype=KLType.K_5M,
                    autype=AuType.NONE,
                    max_count=1000,
                    page_req_key=page_key,
                    extended_time=True  # 開啟盤前盤後
                )
                if ret_h == RET_OK and not df_chunk.empty:
                    all_5m_hist.append(df_chunk)
                if page_key is None or len(all_5m_hist) >= 3:
                    break
                time.sleep(0.3)

            # 4. 抓取日線 DAY
            start_date_day = (now_ny - datetime.timedelta(days=365)).strftime("%Y-%m-%d")
            ret_day, df_day, _ = quote_ctx.request_history_kline(
                code=code,
                start=start_date_day,
                end=end_date_str,
                ktype=KLType.K_DAY,
                autype=AuType.NONE,
                max_count=300
            )
            quote_ctx.close()

            # 合併 5M 數據 (歷史 + 今日實時)
            frames_5m = []
            if all_5m_hist:
                frames_5m.extend(all_5m_hist)
            if ret_cur == RET_OK and not df_cur_5m.empty:
                frames_5m.append(df_cur_5m)

            if frames_5m:
                df_5m_all = pd.concat(frames_5m, ignore_index=True)
                df_5m_all["time_key"] = pd.to_datetime(df_5m_all["time_key"])
                df_5m_all = df_5m_all.sort_values("time_key").drop_duplicates(subset=["time_key"], keep="last").tail(max_bars)
                df_5m_all.to_csv(self.get_csv_path(code, "5M"), index=False)
                
                # 5. 本地重採樣生成 100% 連續包含盤前盤後的 1H CSV
                df_1h = self._resample_5m_to_1h(df_5m_all)
                if not df_1h.empty:
                    df_1h.to_csv(self.get_csv_path(code, "1H"), index=False)

            # 落盤日線
            if ret_day == RET_OK and not df_day.empty:
                df_day["time_key"] = pd.to_datetime(df_day["time_key"])
                df_day = df_day.sort_values("time_key").drop_duplicates(subset=["time_key"], keep="last")
                df_day.to_csv(self.get_csv_path(code, "DAY"), index=False)

            return True, "OK"
        except Exception as e:
            return False, str(e)

    def _resample_5m_to_1h(self, df_5m: pd.DataFrame) -> pd.DataFrame:
        """標準 60 分鐘幾何聚合：以 04:00 為起始錨點，每 12 根 5M 聚合 1 根 1H"""
        if df_5m.empty:
            return pd.DataFrame()
        df = df_5m.copy()
        df.set_index("time_key", inplace=True)
        agg_dict = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum"
        }
        if "turnover" in df.columns:
            agg_dict["turnover"] = "sum"
        return df.resample("1h", closed="left", label="left").agg(agg_dict).dropna(subset=["close"]).reset_index()

    def extract_key_levels(self, code: str) -> dict:
        levels = {"PDH": None, "PDL": None, "PDC": None, "PMH": None, "PML": None, "CUR_PRICE": None}
        df_day = self.load_local_kline(code, "DAY")
        if len(df_day) >= 2:
            prev_row = df_day.iloc[-2]
            levels["PDH"] = float(prev_row["high"])
            levels["PDL"] = float(prev_row["low"])
            levels["PDC"] = float(prev_row["close"])
            levels["CUR_PRICE"] = float(df_day.iloc[-1]["close"])

        df_5m = self.load_local_kline(code, "5M")
        if not df_5m.empty:
            latest_time = df_5m["time_key"].max()
            today_str = latest_time.strftime("%Y-%m-%d")
            df_pm = df_5m[
                (df_5m["time_key"].dt.strftime("%Y-%m-%d") == today_str) &
                (df_5m["time_key"].dt.time >= datetime.time(4, 0)) &
                (df_5m["time_key"].dt.time < datetime.time(9, 30))
            ]
            if not df_pm.empty:
                levels["PMH"] = float(df_pm["high"].max())
                levels["PML"] = float(df_pm["low"].min())
            levels["CUR_PRICE"] = float(df_5m.iloc[-1]["close"])

        return levels

hub_engine = MarketDataEngine()
