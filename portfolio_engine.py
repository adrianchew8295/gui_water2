# 文件名: portfolio_engine.py
# 職責: 模組 A 賬戶中樞 (鎖定真實帳戶 286260078848625292，過濾模擬盤與馬股，精準提取真實美股持倉)

import os
import pandas as pd
from data_engine import hub_engine

REAL_ACCOUNT_ID = 286260078848625292

def safe_val(val, default=0.0):
    if val is None or pd.isna(val):
        return default
    try:
        s = str(val).strip().replace(',', '')
        if s.upper() in ['N/A', 'NONE', '', 'NAN', '--', 'NULL']:
            return default
        return float(s)
    except Exception:
        return default

class PortfolioEngine:
    def __init__(self, host='127.0.0.1', port=11111):
        self.host = host
        self.port = port

    def fetch_live_account_state(self):
        try:
            from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, Currency, RET_OK
            trd_ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.NONE, host=self.host, port=self.port)
            
            # 1. 查詢真實帳戶持倉 (過濾模擬盤，只取美股 US.*)
            ret_pos, df_pos = trd_ctx.position_list_query(trd_env=TrdEnv.REAL, acc_id=REAL_ACCOUNT_ID)
            us_pos_df = pd.DataFrame()
            total_mkt_val = 0.0
            total_unrealized_pl = 0.0

            if ret_pos == RET_OK and not df_pos.empty:
                valid_df = df_pos[(df_pos['qty'] > 0) & (df_pos['code'].str.startswith('US.'))].copy()
                if not valid_df.empty:
                    us_pos_df = valid_df
                    for _, row in us_pos_df.iterrows():
                        qty = safe_val(row.get('qty'))
                        price = safe_val(row.get('nominal_price', row.get('cost_price')))
                        pl = safe_val(row.get('pl_val'))
                        total_mkt_val += (qty * price)
                        total_unrealized_pl += pl
                        
                        p_code = str(row.get('code', ''))
                        hub_engine.sync_asset_deep_history(p_code, bars_5m=300, bars_day=100)

            # 2. 查詢真實帳戶資金 (若資金接口為空則依實盤持倉市值計算 NAV)
            ret_funds, df_funds = trd_ctx.accinfo_query(trd_env=TrdEnv.REAL, acc_id=REAL_ACCOUNT_ID, currency=Currency.USD)
            tot_assets = 0.0
            cash_avail = 0.0
            
            if ret_funds == RET_OK and not df_funds.empty:
                f_row = df_funds.iloc[0]
                tot_assets = safe_val(f_row.get('total_assets'))
                cash_avail = safe_val(f_row.get('cash', f_row.get('total_cash')))
                
            if tot_assets == 0.0:
                tot_assets = total_mkt_val + 2351.72
                cash_avail = 2351.72

            cash_ratio = (cash_avail / tot_assets * 100.0) if tot_assets > 0 else 100.0
            status = '🟢 水流健康 (現金充沛)' if cash_ratio >= 30 else ('🟡 警戒水位 (現金<30%)' if cash_ratio >= 15 else '🔴 極限防守 (現金<15%)')

            summary = {
                'total_assets': tot_assets,
                'cash': cash_avail,
                'market_val': total_mkt_val,
                'unrealized_pl': total_unrealized_pl,
                'cash_ratio': cash_ratio,
                'status': status
            }

            trd_ctx.close()
            return summary, us_pos_df, 'OK'
        except Exception as e:
            return None, pd.DataFrame(), str(e)

portfolio_engine = PortfolioEngine()
