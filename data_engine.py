# 文件名: data_engine.py
# 职责: 独立 Market Data Hub 底层数据引擎 (OpenD 单例常驻 + 5M/1H/Daily 增量落盘 + 频控保护)

import os
import time
import datetime
import json
import pandas as pd
import pytz

tz_ny = pytz.timezone("America/New_York")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")
WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist.json")
os.makedirs(DATA_DIR, exist_ok=True)

class MarketDataHub:
    _instance = None
    quote_ctx = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MarketDataHub, cls).__new__(cls)
        return cls._instance

    def get_context(self):
        """单例保持 OpenD 稳定长连接，防止频繁创建导致额度锁死"""
        if self.quote_ctx is None:
            try:
                from moomoo import OpenQuoteContext
                self.quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
            except Exception:
                self.quote_ctx = None
        return self.quote_ctx

    def load_watchlist(self):
        if os.path.exists(WATCHLIST_PATH):
            try:
                with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                    return json.load(f).get("assets", [])
            except Exception:
                pass
        return []

    def save_watchlist(self, assets_list):
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            json.dump({"assets": assets_list}, f, ensure_ascii=False, indent=2)

    def fetch_closed_kline(self, code: str, ktype_str: str = "5M", req_count: int = 120):
        """抓取官方已收盘定格 K 线并去重增量存盘 (Upsert)"""
        ctx = self.get_context()
        if ctx is None:
            return None, "OpenD 未连线"

        try:
            from moomoo import KLType, AuType, SubType, RET_OK
            ktype_map = {
                "5M": (KLType.K_5M, SubType.K_5M),
                "1H": (KLType.K_60M, SubType.K_60M),
                "DAY": (KLType.K_DAY, SubType.K_DAY)
            }
            kl_target, sub_target = ktype_map.get(ktype_str, (KLType.K_5M, SubType.K_5M))
            ctx.subscribe([code], [sub_target])
            time.sleep(0.2)

            ret, df = ctx.get_cur_kline(code, req_count, kl_target, AuType.NONE)
            if ret == RET_OK and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                clean_name = code.replace(".", "_")
                csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype_str}.csv")

                # 如果本地已有数据，做时间戳 Upsert 智能合并去重
                if os.path.exists(csv_path):
                    try:
                        old_df = pd.read_csv(csv_path)
                        combined = pd.concat([old_df, df], ignore_index=True)
                        df = combined.drop_duplicates(subset=['time_key'], keep='last').sort_values('time_key').reset_index(drop=True)
                    except Exception:
                        pass

                df.to_csv(csv_path, index=False)
                return df, "OK"
            else:
                return None, f"获取失败 ret: {ret}"
        except Exception as e:
            return None, str(e)

    def get_realtime_snapshot(self, code_list: list):
        """获取毫秒实时快照，驱动页面跳动"""
        ctx = self.get_context()
        if ctx is None:
            return None
        try:
            from moomoo import RET_OK
            ret, df = ctx.get_market_snapshot(code_list)
            if ret == RET_OK and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                return df
        except Exception:
            pass
        return None

hub_engine = MarketDataHub()
