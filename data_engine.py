# 文件名: data_engine.py
# 职责: 独立 Market Data Hub 底层数据引擎 + Moomoo 真实账户持仓与资金接口 (含 N/A 防崩清洗)

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
    """安全转换浮点数，自动过滤 'N/A'、None 或非法字符"""
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
        return [
            {"code": "US.QQQ", "name": "纳指100 ETF", "category": "🚀 核心指数", "type": "STOCK"},
            {"code": "US.SPY", "name": "标普500 ETF", "category": "🚀 核心指数", "type": "STOCK"},
            {"code": "US.NVDA", "name": "英伟达", "category": "🏛️ 科技巨头", "type": "STOCK"},
            {"code": "CC.BTCUSD", "name": "比特币现货", "category": "🪙 加密资产", "type": "CRYPTO"}
        ]

    def save_watchlist(self, assets_list):
        with open(WATCHLIST_PATH, "w", encoding="utf-8") as f:
            json.dump({"assets": assets_list}, f, ensure_ascii=False, indent=2)

    def fetch_deep_history(self, code: str, ktype_str: str = "DAY", days_back: int = 730):
        """拉取深度历史数据并落盘"""
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
        """换棒时增量同步最新定格柱"""
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

# 单例导出
hub_engine = MarketDataHub()


# -------------------------------------------------------------
# Moomoo 实盘账户与持仓接口 (含全字段 safe_float 保护)
# -------------------------------------------------------------
def get_moomoo_real_portfolio(host='127.0.0.1', port=11111):
    """
    通过 OpenD 获取当前登录账户的资金及持仓明细
    """
    try:
        from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, Currency, RET_OK
        trd_ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.NONE, host=host, port=port)
        ret_acc, acc_list = trd_ctx.get_acc_list()
        
        if ret_acc != RET_OK or acc_list.empty:
            trd_ctx.close()
            return None, None, f"获取账户列表失败: {acc_list}"
            
        real_accs = acc_list[acc_list['trd_env'] == 'REAL']
        target_acc = real_accs.iloc[0] if not real_accs.empty else acc_list.iloc[0]
        trd_env = TrdEnv.REAL if not real_accs.empty else TrdEnv.SIMULATE
        target_acc_id = int(target_acc['acc_id'])
        
        # 1. 资金 (加入 safe_float 防崩保护)
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
            
        # 2. 持仓
        ret_pos, df_pos = trd_ctx.position_list_query(trd_env=trd_env, acc_id=target_acc_id)
        pos_df = pd.DataFrame()
        if ret_pos == RET_OK and not df_pos.empty:
            pos_df = df_pos.copy()
            # 持仓中的数值列也做安全转换
            for col in ['cost_price', 'nominal_price', 'market_val', 'pl_val', 'pl_ratio', 'qty', 'can_sell_qty']:
                if col in pos_df.columns:
                    pos_df[col] = pos_df[col].apply(safe_float)
            
        trd_ctx.close()
        return fund_summary, pos_df, "OK"
    except Exception as e:
        return None, None, str(e)
