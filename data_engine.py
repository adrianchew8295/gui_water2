# 文件名: data_engine.py
# 职责: 完整抓取 04:00~20:00 美股全时段 5M 历史与实时数据 + 1H 本地重采样 + 持仓查询 + 状态日志

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

def resample_5m_to_1h(df_5m: pd.DataFrame) -> pd.DataFrame:
    if df_5m is None or df_5m.empty:
        return pd.DataFrame()
    df = df_5m.copy()
    df.columns = [c.lower().strip() for c in df.columns]
    df['dt'] = pd.to_datetime(df['time_key'])
    df = df.set_index('dt').sort_index()

    agg_rules = {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}
    if 'turnover' in df.columns:
        agg_rules['turnover'] = 'sum'
    if 'code' in df.columns:
        agg_rules['code'] = 'first'
        
    df_1h = df.resample('1h', label='left', closed='left').agg(agg_rules)
    df_1h = df_1h.dropna(subset=['open', 'close']).reset_index()
    df_1h['time_key'] = df_1h['dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
    df_1h = df_1h.drop(columns=['dt'])
    return df_1h

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

    def auto_heal_today_data(self, code: str):
        """拉取 04:00 至今包含盤前的全時段 5M 數據並重採樣 1H"""
        ctx = self.get_context()
        if ctx is None:
            return False, "OpenD 離線"

        try:
            from moomoo import KLType, AuType, RET_OK
            now_ny = datetime.datetime.now(tz_ny)
            start_str = (now_ny - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            end_str = now_ny.strftime("%Y-%m-%d")

            ret, df_hist, msg = ctx.request_history_kline(
                code=code,
                start=start_str,
                end=end_str,
                ktype=KLType.K_5M,
                autype=AuType.NONE,
                max_count=1000,
                extended_time=True
            )

            if ret != RET_OK or df_hist.empty:
                log_event(f"[Auto-Heal 失敗] 無法獲取 {code} 全時段數據: {msg}", "WARNING")
                return False, f"獲取失敗: {msg}"

            df_final = df_hist.copy()
            df_final.columns = [c.lower().strip() for c in df_final.columns]
            df_final = df_final.drop_duplicates(subset=['time_key']).sort_values('time_key').reset_index(drop=True)

            clean_name = code.replace(".", "_")
            csv_path_5m = os.path.join(DATA_DIR, f"{clean_name}_5M.csv")
            df_final.to_csv(csv_path_5m, index=False)

            # 重採樣生成 1H
            df_1h = resample_5m_to_1h(df_final)
            if not df_1h.empty:
                df_1h.to_csv(os.path.join(DATA_DIR, f"{clean_name}_1H.csv"), index=False)

            log_event(f"[Auto-Heal 成功] {code} 全時段 5M 與 1H 已補齊落盤 (共 {len(df_final)} 根 5M)")
            return True, f"已補齊全時段 {len(df_final)} 根 5M"

        except Exception as e:
            log_event(f"[Auto-Heal 異常] {code}: {str(e)}", "ERROR")
            return False, str(e)

    def get_realtime_snapshot(self, code_list: list):
        ctx = self.get_context()
        if ctx is None:
            return None
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
