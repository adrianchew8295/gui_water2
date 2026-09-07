# 文件名: data_engine.py
# 职责: 独立 Market Data Hub 底层数据引擎 (深度历史落盘 + 换棒整点自动增量追加 + 毫秒 Forming Bar 动态合成)

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
        """单例保持 OpenD 稳定长连接"""
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

    def fetch_deep_history(self, code: str, ktype_str: str = "DAY", days_back: int = 730):
        """深度历史分页拉取并落盘"""
        ctx = self.get_context()
        if ctx is None:
            return None, "OpenD 未连线"

        try:
            from moomoo import KLType, AuType, RET_OK
            ktype_map = {
                "5M": KLType.K_5M,
                "1H": KLType.K_60M,
                "DAY": KLType.K_DAY
            }
            kl_target = ktype_map.get(ktype_str, KLType.K_DAY)
            
            now_ny = datetime.datetime.now(tz_ny)
            end_date = now_ny.strftime("%Y-%m-%d")
            start_date = (now_ny - datetime.timedelta(days=days_back)).strftime("%Y-%m-%d")

            all_dfs = []
            page_req_key = None

            while True:
                ret, data, page_req_key = ctx.request_history_kline(
                    code=code,
                    start=start_date,
                    end=end_date,
                    ktype=kl_target,
                    autype=AuType.NONE,
                    max_count=1000,
                    page_req_key=page_req_key
                )
                if ret == RET_OK and not data.empty:
                    all_dfs.append(data)
                else:
                    break
                if page_req_key is None:
                    break
                time.sleep(0.3)

            if all_dfs:
                df = pd.concat(all_dfs, ignore_index=True)
                df.columns = [c.lower() for c in df.columns]
                df = df.drop_duplicates(subset=['time_key']).sort_values('time_key').reset_index(drop=True)
                
                clean_name = code.replace(".", "_")
                csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype_str}.csv")
                df.to_csv(csv_path, index=False)
                return df, f"成功归档 {len(df)} 根 K 线"
            else:
                return None, "未获取到数据"
        except Exception as e:
            return None, str(e)

    def sync_latest_closed_bar(self, code: str, ktype_str: str = "5M"):
        """换棒时轻量同步最近 1~2 根已收盘定格柱并追加写入本地 CSV"""
        ctx = self.get_context()
        if ctx is None:
            return None

        try:
            from moomoo import KLType, AuType, SubType, RET_OK
            ktype_map = {
                "5M": (KLType.K_5M, SubType.K_5M),
                "1H": (KLType.K_60M, SubType.K_60M),
                "DAY": (KLType.K_DAY, SubType.K_DAY)
            }
            kl_target, sub_target = ktype_map.get(ktype_str, (KLType.K_5M, SubType.K_5M))
            ctx.subscribe([code], [sub_target])
            time.sleep(0.1)

            ret, df = ctx.get_cur_kline(code, 5, kl_target, AuType.NONE)
            if ret == RET_OK and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                clean_name = code.replace(".", "_")
                csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype_str}.csv")

                if os.path.exists(csv_path):
                    old_df = pd.read_csv(csv_path)
                    combined = pd.concat([old_df, df], ignore_index=True)
                    df_final = combined.drop_duplicates(subset=['time_key'], keep='last').sort_values('time_key').reset_index(drop=True)
                else:
                    df_final = df

                df_final.to_csv(csv_path, index=False)
                return df_final
        except Exception:
            pass
        return None

    def get_realtime_snapshot(self, code_list: list):
        """获取毫秒实时快照"""
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
