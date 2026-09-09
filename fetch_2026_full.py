# 文件名: fetch_2026_full.py
# 职责: 开启全时段 (extended_time=True) 分页循环拉取 2026 年 1月至今完整 5M K线

import os
import time
import datetime
import pandas as pd
from moomoo import OpenQuoteContext, RET_OK, KLType, AuType, SubType

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
MARKET_DATA_DIR = os.path.join(CURRENT_DIR, 'market_data')
os.makedirs(MARKET_DATA_DIR, exist_ok=True)

def fetch_full_year_5m(code: str = "US.QQQ", start_date: str = "2026-01-01", end_date: str = "2026-09-10"):
    print(f"\n=======================================================")
    print(f"🚀 [历史数据拉取] 开始全时段分页抓取 {code} 2026 至今 5M K线...")
    print(f"=======================================================")
    
    quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
    
    # 订阅
    quote_ctx.subscribe([code], [SubType.K_5M])
    time.sleep(1.0)
    
    all_dfs = []
    page_req_key = None
    page_count = 0
    
    while True:
        page_count += 1
        print(f"[*] 正在拉取第 {page_count} 页数据 (每页 1000 根)...")
        
        ret, data, page_req_key = quote_ctx.request_history_kline(
            code=code,
            start=start_date,
            end=end_date,
            ktype=KLType.K_5M,
            autype=AuType.NONE,
            max_count=1000,
            page_req_key=page_req_key,
            extended_time=True  # 👈 核心：必须开启全时段，否则历史数据会被截断！
        )
        
        if ret == RET_OK:
            if not data.empty:
                all_dfs.append(data)
                print(f"    -> 成功获取 {len(data)} 根 K 线 (时段: {data.iloc[0]['time_key']} 至 {data.iloc[-1]['time_key']})")
            
            if page_req_key is None:
                print("[✓] 所有分页数据拉取完毕！")
                break
        else:
            print(f"[✗] 拉取结束或报错: {data}")
            break
            
        time.sleep(0.35)
        
    quote_ctx.close()
    
    if all_dfs:
        df_full = pd.concat(all_dfs, ignore_index=True)
        df_full.columns = [c.lower().strip() for c in df_full.columns]
        t_col = 'time_key' if 'time_key' in df_full.columns else df_full.columns[0]
        df_full = df_full.drop_duplicates(subset=[t_col]).sort_values(t_col).reset_index(drop=True)
        
        clean_code = code.replace('.', '_')
        save_path = os.path.join(MARKET_DATA_DIR, f"{clean_code}_5M.csv")
        df_full.to_csv(save_path, index=False)
        print(f"=======================================================")
        print(f"🎉 成功存盘！总计 {len(df_full)} 根真实 5M 柱 (最早: {df_full[t_col].iloc[0]} 最晚: {df_full[t_col].iloc[-1]})")
        print(f"=======================================================\n")
        return save_path
    else:
        print("[!] 未能获取到数据，请检查 OpenD 是否为绿色连接。")
        return None

if __name__ == "__main__":
    fetch_full_year_5m("US.QQQ")
