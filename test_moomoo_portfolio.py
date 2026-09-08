# 文件名: test_moomoo_portfolio.py
from moomoo import *
import pandas as pd

def safe_float(val, default=0.0):
    try:
        return float(val) if pd.notna(val) else default
    except Exception:
        return default

# 1. 直连 OpenD
trd_ctx = OpenSecTradeContext(
    filter_trdmarket=TrdMarket.NONE,
    host='127.0.0.1', 
    port=11111
)

print("=" * 65)
print("🔗 正在读取 Moomoo 真实账户...")
print("=" * 65)

ret_acc, acc_list = trd_ctx.get_acc_list()
if ret_acc == RET_OK and not acc_list.empty:
    real_accs = acc_list[acc_list['trd_env'] == 'REAL']
    target_acc = real_accs.iloc[0] if not real_accs.empty else acc_list.iloc[0]
    trd_env = TrdEnv.REAL if not real_accs.empty else TrdEnv.SIMULATE
    target_acc_id = int(target_acc['acc_id'])
    firm = target_acc.get('security_firm', 'FUTUMY')
    
    print(f"✅ 选定账户: ID={target_acc_id} | 环境={trd_env} | 券商={firm}")
    
    # 2. 查询资金概况
    ret_funds, df_funds = trd_ctx.accinfo_query(trd_env=trd_env, acc_id=target_acc_id, currency=Currency.USD)
    if ret_funds == RET_OK and not df_funds.empty:
        funds = df_funds.iloc[0]
        total_assets = safe_float(funds.get('total_assets'))
        cash = safe_float(funds.get('cash'))
        market_val = safe_float(funds.get('market_val'))
        unrealized_pl = safe_float(funds.get('unrealized_pl'))
        
        print("\n💰 【账户资金概况 (USD)】")
        print(f" • 账户总资产 (NAV) : ${total_assets:,.2f}")
        print(f" • 可用现金 (Cash)  : ${cash:,.2f}")
        print(f" • 证券市值 (Stock) : ${market_val:,.2f}")
        print(f" • 累计浮动盈亏     : ${unrealized_pl:,.2f}")
    
    # 3. 查询当前真实持仓
    ret_pos, df_pos = trd_ctx.position_list_query(trd_env=trd_env, acc_id=target_acc_id)
    if ret_pos == RET_OK:
        print("\n📊 【当前持仓明细 (Position List)】")
        if df_pos.empty:
            print("⚪ 当前无持仓 (空仓)")
        else:
            show_cols = ['code', 'stock_name', 'qty', 'can_sell_qty', 'cost_price', 'nominal_price', 'pl_val', 'pl_ratio', 'market_val']
            valid_cols = [c for c in show_cols if c in df_pos.columns]
            print(df_pos[valid_cols].to_string(index=False))
    else:
        print(f"❌ 获取持仓失败: {df_pos}")

trd_ctx.close()