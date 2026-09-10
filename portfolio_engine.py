# 文件名: portfolio_engine.py
# 職責: 模組 A 賬戶與持倉中樞 (直連 OpenD 讀取真實 NAV / Cash / 持倉 + 新股 Auto-Fetch)

import os
import pandas as pd
from data_engine import hub_engine

class PortfolioEngine:
    def __init__(self, host="127.0.0.1", port=11111):
        self.host = host
        self.port = port

    def fetch_live_account_state(self):
        """
        獲取真實實盤賬戶資訊與持倉明細
        包含 NAV、可用現金、持倉列表、各標的佔比與新股 Auto-Fetch
        """
        try:
            from moomoo import OpenSecTradeContext, TrdMarket, TrdEnv, Currency, RET_OK
            trd_ctx = OpenSecTradeContext(filter_trdmarket=TrdMarket.NONE, host=self.host, port=self.port)
            ret_acc, acc_list = trd_ctx.get_acc_list()
            
            if ret_acc != RET_OK or acc_list.empty:
                trd_ctx.close()
                return None, pd.DataFrame(), f"獲取賬戶列表失敗: {acc_list}"
                
            real_accs = acc_list[acc_list['trd_env'] == 'REAL']
            target_acc = real_accs.iloc[0] if not real_accs.empty else acc_list.iloc[0]
            trd_env = TrdEnv.REAL if not real_accs.empty else TrdEnv.SIMULATE
            target_acc_id = int(target_acc['acc_id'])
            
            # 1. 資金總額
            ret_funds, df_funds = trd_ctx.accinfo_query(trd_env=trd_env, acc_id=target_acc_id, currency=Currency.USD)
            summary = {
                'total_assets': 0.0,
                'cash': 0.0,
                'market_val': 0.0,
                'unrealized_pl': 0.0,
                'cash_ratio': 100.0,
                'status': '🟢 健康 (綠燈)'
            }
            if ret_funds == RET_OK and not df_funds.empty:
                row = df_funds.iloc[0]
                tot = float(row.get('total_assets', 0.0) or 0.0)
                csh = float(row.get('cash', 0.0) or 0.0)
                mkt = float(row.get('market_val', 0.0) or 0.0)
                upl = float(row.get('unrealized_pl', 0.0) or 0.0)
                
                ratio = (csh / tot * 100.0) if tot > 0 else 100.0
                status = "🟢 水流健康 (現金充沛)" if ratio >= 30 else ("🟡 警戒水位 (現金<30%)" if ratio >= 15 else "🔴 極限防守 (現金<15%)")
                
                summary = {
                    'total_assets': tot,
                    'cash': csh,
                    'market_val': mkt,
                    'unrealized_pl': upl,
                    'cash_ratio': ratio,
                    'status': status
                }
                
            # 2. 持倉明細
            ret_pos, df_pos = trd_ctx.position_list_query(trd_env=trd_env, acc_id=target_acc_id)
            pos_df = pd.DataFrame()
            if ret_pos == RET_OK and not df_pos.empty:
                pos_df = df_pos.copy()
                
                # Auto-Fetch 檢測新買入股票
                known_assets = [a["code"] for a in hub_engine.load_watchlist()]
                for _, p_row in pos_df.iterrows():
                    p_code = str(p_row.get("code", ""))
                    if p_code and p_code not in known_assets:
                        hub_engine.sync_asset_deep_history(p_code, bars_5m=500, bars_day=150)
                
            trd_ctx.close()
            return summary, pos_df, "OK"
        except Exception as e:
            return None, pd.DataFrame(), str(e)


portfolio_engine = PortfolioEngine()
