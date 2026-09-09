# 文件名: data_engine.py
# 職責: 
# 1. 導出 app.py 所需的 hub_engine, get_active_session_info, LOG_PATH, get_moomoo_real_portfolio
# 2. 抓取包含美東 04:00~20:00 全時段 5M 原始流
# 3. 本地 Pandas 100% 精準 Resample 聚合生成無斷層 1H CSV
# 4. 倒序抓取真實不截斷日線 (DAY) 數據與實盤持倉查詢

import os
import time
import datetime
import json
import logging
import pytz
import numpy as np
import pandas as pd

tz_ny = pytz.timezone("America/New_York")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")
WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist.json")
LOG_PATH = os.path.join(BASE_DIR, "system_health.log")
os.makedirs(DATA_DIR, exist_ok=True)

# 系統日誌配置
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
    """判斷當前美股時段 (盤前 / 常規 / 盤後 / 休市)"""
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

def clean_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    """標準化清洗 K 線欄位"""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [c.lower().strip() for c in df.columns]
    
    time_col = 'time_key' if 'time_key' in df.columns else ('time_clean' if 'time_clean' in df.columns else df.columns[0])
    df['time_key'] = df[time_col].astype(str)
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
    df = df.dropna(subset=['open', 'high', 'low', 'close'])
    df = df.drop_duplicates(subset=['time_key']).sort_values('time_key').reset_index(drop=True)
    return df[['time_key', 'open', 'high', 'low', 'close', 'volume']]

def resample_5m_to_1h(df_5m: pd.DataFrame) -> pd.DataFrame:
    """由 5M 原始數據聚合生成連續 1H 數據 (每日 16 根連續小時線，含盤前盤後)"""
    if df_5m is None or df_5m.empty:
        return pd.DataFrame()
    
    df = df_5m.copy()
    df['dt'] = pd.to_datetime(df['time_key'])
    df = df.set_index('dt')
    
    df_1h = df.resample('1h', closed='left', label='left').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna().reset_index()
    
    df_1h['time_key'] = df_1h['dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
    df_1h['time_clean'] = df_1h['dt'].dt.strftime('%Y-%m-%d %H:%M')
    return df_1h[['time_key', 'time_clean', 'open', 'high', 'low', 'close', 'volume']]

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
        return [
            {"code": "US.QQQ", "name": "納指100 ETF", "category": "🚀 核心指數", "type": "STOCK"},
            {"code": "US.NVDA", "name": "英偉達", "category": "🏛️ 科技巨頭", "type": "STOCK"}
        ]

    def save_watchlist(self, assets_list):
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            json.dump({"assets": assets_list}, f, ensure_ascii=False, indent=2)

    def sync_asset_deep_history(self, code: str = "US.NVDA", bars_5m: int = 1500, bars_day: int = 300):
        """核心同步管道：5M 全時段 + 1H Resample + DAY 倒序"""
        clean_code = code.replace('.', '_')
        p_5m = os.path.join(DATA_DIR, f"{clean_code}_5M.csv")
        p_1h = os.path.join(DATA_DIR, f"{clean_code}_1H.csv")
        p_day = os.path.join(DATA_DIR, f"{clean_code}_DAY.csv")

        try:
            from moomoo import OpenQuoteContext, RET_OK, KLType, AuType
            quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
            now_ny = datetime.datetime.now(tz_ny)
            end_str = now_ny.strftime("%Y-%m-%d %H:%M:%S")

            # 1. 抓取 5M 全時段 (含 04:00~20:00)
            ret_5m, df_5m_raw, _ = quote_ctx.request_history_kline(
                code=code,
                start='',
                end=end_str,
                ktype=KLType.K_5M,
                autype=AuType.QFQ,
                max_count=bars_5m,
                extended_time=True
            )

            if ret_5m == RET_OK and df_5m_raw is not None and not df_5m_raw.empty:
                df_5m = clean_kline_df(df_5m_raw)
                df_5m.to_csv(p_5m, index=False)
                # 本地 Resample 合成 1H
                df_1h = resample_5m_to_1h(df_5m)
                df_1h.to_csv(p_1h, index=False)

            # 2. 抓取日線數據
            ret_day, df_day_raw, _ = quote_ctx.request_history_kline(
                code=code,
                start='',
                end=end_str,
                ktype=KLType.K_DAY,
                autype=AuType.QFQ,
                max_count=bars_day
            )

            if ret_day == RET_OK and df_day_raw is not None and not df_day_raw.empty:
                df_day = clean_kline_df(df_day_raw)
                df_day['time_clean'] = df_day['time_key'].str.slice(0, 10)
                df_day.to_csv(p_day, index=False)

            quote_ctx.close()
            return True, "同步完成"
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

# 全域單例實例 (對接所有外掛與 app.py)
hub_engine = MarketDataHub()
data_engine = hub_engine

def get_moomoo_real_portfolio(host='127.0.0.1', port=11111):
    """查詢富途/Moomoo 實盤賬戶資金與持倉"""
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
