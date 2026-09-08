# 文件名: data_engine.py
# 職責: 全時段 5M 歷史落盤 + 實時快照 + 1H 本地重採樣聚合 (含盤前盤後) + Moomoo 實盤持倉接口

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

def safe_float(val, default=0.0):
    """安全轉換浮點數，過濾 'N/A'、None 與異常字符"""
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
    """
    將包含全時段 (04:00~20:00) 的 5M 數據在本地重採樣聚合為 1H 連續 K 線
    """
    if df_5m is None or df_5m.empty:
        return pd.DataFrame()
    
    df = df_5m.copy()
    df.columns = [c.lower().strip() for c in df.columns]
    
    # 確保時間索引
    df['dt'] = pd.to_datetime(df['time_key'])
    df = df.set_index('dt').sort_index()
    
    # 按 1 小時聚合: Open取首, High取大, Low取小, Close取尾, Volume求和
    agg_rules = {
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }
    
    # 若有 turnover 欄位一併聚合
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
        """單例長連線 OpenD"""
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
        return [
            {"code": "US.QQQ", "name": "納指100 ETF", "category": "🚀 核心指數", "type": "STOCK"},
            {"code": "US.SPY", "name": "標普500 ETF", "category": "🚀 核心指數", "type": "STOCK"},
            {"code": "US.NVDA", "name": "英偉達", "category": "🏛️ 科技巨頭", "type": "STOCK"},
            {"code": "CC.BTCUSD", "name": "比特幣現貨", "category": "🪙 加密資產", "type": "CRYPTO"}
        ]

    def save_watchlist(self, assets_list):
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            json.dump({"assets": assets_list}, f, ensure_ascii=False, indent=2)

    def fetch_deep_history(self, code: str, ktype_str: str = "DAY", days_back: int = 730):
        """拉取全時段歷史數據並落盤，1H 採用 5M 重採樣合成"""
        ctx = self.get_context()
        if ctx is None:
            return None, "OpenD 未連線"

        try:
            from moomoo import KLType, AuType, RET_OK
            
            # 若請求 1H，底層自動拉取 60 天全時段 5M 並合成 1H
            if ktype_str == "1H":
                df_5m, msg = self.fetch_deep_history(code, ktype_str="5M", days_back=min(days_back, 60))
                if df_5m is not None and not df_5m.empty:
                    df_1h = resample_5m_to_1h(df_5m)
                    clean_name = code.replace(".", "_")
                    csv_path_1h = os.path.join(DATA_DIR, f"{clean_name}_1H.csv")
                    df_1h.to_csv(csv_path_1h, index=False)
                    return df_1h, f"成功重採樣合成 {len(df_1h)} 根全時段 1H K 線"
                return None, "5M 基礎數據不足以合成 1H"

            # 5M 或 DAY 正常歷史拉取
            kl_target = KLType.K_5M if ktype_str == "5M" else KLType.K_DAY
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
                time.sleep(0.2)

            if all_dfs:
                df = pd.concat(all_dfs, ignore_index=True)
                df.columns = [c.lower() for c in df.columns]
                df = df.drop_duplicates(subset=['time_key']).sort_values('time_key').reset_index(drop=True)
                
                clean_name = code.replace(".", "_")
                csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype_str}.csv")
                df.to_csv(csv_path, index=False)
                
                # 如果拉取的是 5M，順便自動生成對應的 1H CSV
                if ktype_str == "5M":
                    df_1h_auto = resample_5m_to_1h(df)
                    if not df_1h_auto.empty:
                        df_1h_auto.to_csv(os.path.join(DATA_DIR, f"{clean_name}_1H.csv"), index=False)
                        
                return df, f"成功歸檔 {len(df)} 根 K 線"
            else:
                return None, "未獲取到歷史數據"
        except Exception as e:
            return None, str(e)

    def sync_latest_closed_bar(self, code: str, ktype_str: str = "5M"):
        """換棒時增量同步最新柱 (全時段支持)"""
        ctx = self.get_context()
        if ctx is None:
            return None

        try:
            from moomoo import KLType, AuType, SubType, RET_OK
            
            # 統一訂閱 5M 作為基底
            ctx.subscribe([code], [SubType.K_5M])
            time.sleep(0.1)

            ret, df = ctx.get_cur_kline(code, 30, KLType.K_5M, AuType.NONE)
            if ret == RET_OK and not df.empty:
                df.columns = [c.lower() for c in df.columns]
                clean_name = code.replace(".", "_")
                csv_path_5m = os.path.join(DATA_DIR, f"{clean_name}_5M.csv")

                if os.path.exists(csv_path_5m):
                    old_df = pd.read_csv(csv_path_5m)
                    combined = pd.concat([old_df, df], ignore_index=True)
                    df_final_5m = combined.drop_duplicates(subset=['time_key'], keep='last').sort_values('time_key').reset_index(drop=True)
                else:
                    df_final_5m = df

                df_final_5m.to_csv(csv_path_5m, index=False)
                
                # 同步重採樣 1H
                df_final_1h = resample_5m_to_1h(df_final_5m)
                if not df_final_1h.empty:
                    df_final_1h.to_csv(os.path.join(DATA_DIR, f"{clean_name}_1H.csv"), index=False)

                return df_final_1h if ktype_str == "1H" else df_final_5m
        except Exception:
            pass
        return None

    def get_realtime_snapshot(self, code_list: list):
        """獲取毫秒實時快照 (包含盤前現價與成交量)"""
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

# 單例導出
hub_engine = MarketDataHub()

# -------------------------------------------------------------
# Moomoo 實盤賬戶接口 (含 safe_float 防護)
# -------------------------------------------------------------
def get_moomoo_real_portfolio(host='127.0.0.1', port=11111):
    try:
        from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, Currency, RET_OK
        trd_ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.NONE, host=host, port=port)
        ret_acc, acc_list = trd_ctx.get_acc_list()
        
        if ret_acc != RET_OK or acc_list.empty:
            trd_ctx.close()
            return None, None, f"獲取賬戶列表失敗: {acc_list}"
            
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
        return None, None, str(e)
