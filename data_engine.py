# 文件名: data_engine.py
# 職責: 獨立抓取 1,500 根 5M 與 1,000 根原生 1H 全時段數據 + 實盤持倉查詢 + 系統日誌

import os
import time
import datetime
import json
import logging
import pandas as pd
import pytz

tz_ny = pytz.timezone("America/New_York")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")
WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist.json")
LOG_PATH = os.path.join(BASE_DIR, "system_health.log")
os.makedirs(DATA_DIR, exist_ok=True)

logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8"
)

def log_event(msg: str, level: str = "INFO"):
    if level == "ERROR":
        logging.error(msg)
    elif level == "WARNING":
        logging.warning(msg)
    else:
        logging.info(msg)

def get_active_session_info():
    now_ny = datetime.datetime.now(tz_ny)
    weekday = now_ny.weekday()
    cur_t = now_ny.time()

    if weekday >= 5:
        return "CLOSED_WEEKEND", "⚪ 週末休市中", now_ny
    
    if datetime.time(4, 0) <= cur_t < datetime.time(9, 30):
        return "PREMARKET", "🟡 PREMARKET (盤前撮合中)", now_ny
    elif datetime.time(9, 30) <= cur_t < datetime.time(16, 0):
        return "REGULAR", "🟢 REGULAR (常規交易盤)", now_ny
    elif datetime.time(16, 0) <= cur_t <= datetime.time(20, 0):
        return "AFTERMARKET", "🔵 AFTERMARKET (盤後交易中)", now_ny
    else:
        return "CLOSED_NIGHT", "⚪ 夜間閉市休眠", now_ny

def safe_float(val, default=0.0):
    if val is None or pd.isna(val):
        return default
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace(",", "").replace("$", "").replace("%", "")
    if val_str.upper() in ["N/A", "NA", "NONE", "--", "NULL", ""]:
        return default
    try:
        return float(val_str)
    except Exception:
        return default

class MarketDataHub:
    _instance = None
    quote_ctx = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MarketDataHub, cls).__new__(cls)
        return cls._instance

    def get_context(self):
        if self.quote_ctx is None:
            try:
                from moomoo import OpenQuoteContext
                self.quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
                log_event("成功連線本地 Moomoo OpenD (127.0.0.1:11111)")
            except Exception as e:
                log_event(f"OpenD 連線失敗: {str(e)}", "ERROR")
                self.quote_ctx = None
        return self.quote_ctx

    def load_watchlist(self):
        if os.path.exists(WATCHLIST_PATH):
            try:
                with open(WATCHLIST_PATH, "r", encoding="utf-8") as f:
                    return json.load(f).get("assets", [])
            except Exception:
                pass
        return [{"code": "US.QQQ", "name": "納指100 ETF", "category": "🚀 核心指數", "type": "STOCK"}]

    def save_watchlist(self, assets_list):
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            json.dump({"assets": assets_list}, f, ensure_ascii=False, indent=2)

    def fetch_5m_deep_history(self, code: str = "US.QQQ", target_bars: int = 1500):
        """分頁循環拉取 1,500 根全時段原生 5M 柱"""
        ctx = self.get_context()
        if ctx is None: return False, "OpenD 離線"

        try:
            from moomoo import KLType, AuType, SubType, RET_OK
            now_ny = datetime.datetime.now(tz_ny)
            end_str = now_ny.strftime("%Y-%m-%d")
            start_str = (now_ny - datetime.timedelta(days=60)).strftime("%Y-%m-%d")

            all_dfs = []
            page_req_key = None

            while True:
                ret, df_page, page_req_key = ctx.request_history_kline(
                    code=code, start=start_str, end=end_str,
                    ktype=KLType.K_5M, autype=AuType.NONE,
                    max_count=1000, extended_time=True, page_req_key=page_req_key
                )
                if ret == RET_OK and not df_page.empty:
                    all_dfs.append(df_page)
                    if sum(len(d) for d in all_dfs) >= target_bars or page_req_key is None:
                        break
                else:
                    break
                time.sleep(0.05)

            ctx.subscribe([code], [SubType.K_5M])
            ret_cur, df_cur = ctx.get_cur_kline(code, 200, KLType.K_5M, AuType.NONE)
            if ret_cur == RET_OK and not df_cur.empty:
                all_dfs.append(df_cur)

            if not all_dfs: return False, "未能獲取 5M 數據"

            df_merged = pd.concat(all_dfs, ignore_index=True)
            df_merged.columns = [c.lower().strip() for c in df_merged.columns]
            df_final = df_merged.drop_duplicates(subset=['time_key']).sort_values('time_key').tail(target_bars).reset_index(drop=True)

            clean_name = code.replace(".", "_")
            df_final.to_csv(os.path.join(DATA_DIR, f"{clean_name}_5M.csv"), index=False)
            return True, f"5M 深度同步完成 (共 {len(df_final)} 根)"
        except Exception as e:
            return False, str(e)

    def fetch_1h_deep_history(self, code: str = "US.QQQ", target_bars: int = 1000):
        """【Step 2 核心】分頁循環拉取 1,000 根原生 1H 柱 (KLType.K_60M)"""
        ctx = self.get_context()
        if ctx is None: return False, "OpenD 離線"

        try:
            from moomoo import KLType, AuType, SubType, RET_OK
            now_ny = datetime.datetime.now(tz_ny)
            end_str = now_ny.strftime("%Y-%m-%d")
            # 往前拉 120 天以滿足 1,000 根 1H 全時段柱線
            start_str = (now_ny - datetime.timedelta(days=120)).strftime("%Y-%m-%d")

            log_event(f"[*] 開始分頁拉取 {code} 原生 1H 全時段歷史 (目標: {target_bars} 根)...")

            all_dfs = []
            page_req_key = None

            while True:
                ret, df_page, page_req_key = ctx.request_history_kline(
                    code=code, start=start_str, end=end_str,
                    ktype=KLType.K_60M, autype=AuType.NONE,
                    max_count=1000, extended_time=True, page_req_key=page_req_key
                )
                if ret == RET_OK and not df_page.empty:
                    all_dfs.append(df_page)
                    if sum(len(d) for d in all_dfs) >= target_bars or page_req_key is None:
                        break
                else:
                    break
                time.sleep(0.05)

            ctx.subscribe([code], [SubType.K_60M])
            ret_cur, df_cur = ctx.get_cur_kline(code, 100, KLType.K_60M, AuType.NONE)
            if ret_cur == RET_OK and not df_cur.empty:
                all_dfs.append(df_cur)

            if not all_dfs: return False, "未能獲取 1H 數據"

            df_merged = pd.concat(all_dfs, ignore_index=True)
            df_merged.columns = [c.lower().strip() for c in df_merged.columns]
            df_final = df_merged.drop_duplicates(subset=['time_key']).sort_values('time_key').tail(target_bars).reset_index(drop=True)

            clean_name = code.replace(".", "_")
            csv_path_1h = os.path.join(DATA_DIR, f"{clean_name}_1H.csv")
            df_final.to_csv(csv_path_1h, index=False)

            msg = f"已成功獨立抓取 {code} 原生 1H 全時段數據: 共 {len(df_final)} 根"
            log_event(msg)
            return True, msg

        except Exception as e:
            log_event(f"1H 深度拉取異常: {str(e)}", "ERROR")
            return False, str(e)

    def auto_heal_today_data(self, code: str):
        clean_name = code.replace(".", "_")
        csv_path_5m = os.path.join(DATA_DIR, f"{clean_name}_5M.csv")
        csv_path_1h = os.path.join(DATA_DIR, f"{clean_name}_1H.csv")

        # 若 5M 或 1H 不足，執行全量深度拉取
        if not os.path.exists(csv_path_5m) or os.path.getsize(csv_path_5m) < 1000:
            self.fetch_5m_deep_history(code, 1500)
        if not os.path.exists(csv_path_1h) or os.path.getsize(csv_path_1h) < 1000:
            self.fetch_1h_deep_history(code, 1000)

        ctx = self.get_context()
        if ctx is None: return False, "OpenD 離線"
        try:
            from moomoo import KLType, AuType, SubType, RET_OK
            now_ny = datetime.datetime.now(tz_ny)
            start_str = (now_ny - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            end_str = now_ny.strftime("%Y-%m-%d")

            # 1. 增量補齊 5M
            ret_5m, df_hist_5m, _ = ctx.request_history_kline(code=code, start=start_str, end=end_str, ktype=KLType.K_5M, autype=AuType.NONE, max_count=1000, extended_time=True)
            ctx.subscribe([code], [SubType.K_5M])
            ret_cur_5m, df_cur_5m = ctx.get_cur_kline(code, 100, KLType.K_5M, AuType.NONE)
            dfs_5m = [pd.read_csv(csv_path_5m)] if os.path.exists(csv_path_5m) else []
            if ret_5m == RET_OK and not df_hist_5m.empty: dfs_5m.append(df_hist_5m)
            if ret_cur_5m == RET_OK and not df_cur_5m.empty: dfs_5m.append(df_cur_5m)
            if dfs_5m:
                df_all_5m = pd.concat(dfs_5m, ignore_index=True)
                df_all_5m.columns = [c.lower().strip() for c in df_all_5m.columns]
                df_final_5m = df_all_5m.drop_duplicates(subset=['time_key']).sort_values('time_key').tail(1500).reset_index(drop=True)
                df_final_5m.to_csv(csv_path_5m, index=False)

            # 2. 增量補齊原生 1H
            ret_1h, df_hist_1h, _ = ctx.request_history_kline(code=code, start=start_str, end=end_str, ktype=KLType.K_60M, autype=AuType.NONE, max_count=1000, extended_time=True)
            ctx.subscribe([code], [SubType.K_60M])
            ret_cur_1h, df_cur_1h = ctx.get_cur_kline(code, 50, KLType.K_60M, AuType.NONE)
            dfs_1h = [pd.read_csv(csv_path_1h)] if os.path.exists(csv_path_1h) else []
            if ret_1h == RET_OK and not df_hist_1h.empty: dfs_1h.append(df_hist_1h)
            if ret_cur_1h == RET_OK and not df_cur_1h.empty: dfs_1h.append(df_cur_1h)
            if dfs_1h:
                df_all_1h = pd.concat(dfs_1h, ignore_index=True)
                df_all_1h.columns = [c.lower().strip() for c in df_all_1h.columns]
                df_final_1h = df_all_1h.drop_duplicates(subset=['time_key']).sort_values('time_key').tail(1000).reset_index(drop=True)
                df_final_1h.to_csv(csv_path_1h, index=False)

            return True, f"5M 與 原生 1H 增量自癒完成"
        except Exception as e:
            return False, str(e)

    def get_realtime_snapshot(self, code_list: list):
        ctx = self.get_context()
        if ctx is None: return None
        try:
            from moomoo import RET_OK
            ret, df = ctx.get_market_snapshot(code_list)
            if ret == RET_OK and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                return df
        except Exception as e:
            log_event(f"快照獲取異常: {str(e)}", "ERROR")
        return None

hub_engine = MarketDataHub()

def get_moomoo_real_portfolio(host='127.0.0.1', port=11111):
    try:
        from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, Currency, RET_OK
        trd_ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.NONE, host=host, port=port)
        ret_acc, acc_list = trd_ctx.get_acc_list()
        if ret_acc != RET_OK or acc_list.empty:
            trd_ctx.close()
            return None, None, "獲取賬戶列表失敗"
            
        real_accs = acc_list[acc_list['trd_env'] == 'REAL']
        target_acc = real_accs.iloc[0] if not real_accs.empty else acc_list.iloc[0]
        trd_env = TrdEnv.REAL if not real_accs.empty else TrdEnv.SIMULATE
        target_acc_id = int(target_acc['acc_id'])
        
        ret_funds, df_funds = trd_ctx.accinfo_query(trd_env=trd_env, acc_id=target_acc_id, currency=Currency.USD)
        fund_summary = {}
        if ret_funds == RET_OK and not df_funds.empty:
            row = df_funds.iloc[0]
            fund_summary = {
                'total_assets': safe_float(row.get('total_assets')),
                'cash': safe_float(row.get('cash')),
                'market_val': safe_float(row.get('market_val')),
                'unrealized_pl': safe_float(row.get('unrealized_pl')),
                'acc_id': str(target_acc_id),
                'trd_env': 'REAL' if trd_env == TrdEnv.REAL else 'SIMULATE'
            }
            
        ret_pos, df_pos = trd_ctx.position_list_query(trd_env=trd_env, acc_id=target_acc_id)
        pos_df = pd.DataFrame()
        if ret_pos == RET_OK and not df_pos.empty:
            pos_df = df_pos.copy()
            for col in ['cost_price', 'nominal_price', 'market_val', 'pl_val', 'pl_ratio', 'qty', 'can_sell_qty']:
                if col in pos_df.columns:
                    pos_df[col] = pos_df[col].apply(safe_float)
            
        trd_ctx.close()
        return fund_summary, pos_df, "OK"
    except Exception as e:
        log_event(f"持倉查詢異常: {str(e)}", "ERROR")
        return None, None, str(e)
