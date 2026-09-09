# 文件名: fetch_2026_full.py
# 职责: 自动分页循环抓取 2026 全年 5M 历史数据并落盘 (遵守 API 限流，零管道阻塞)

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
    print(f"🚀 [历史数据拉取] 开始分页同步 {code} 2026 全年 5M K线...")
    print(f"=======================================================")
    
    quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
    
    # 预先订阅
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
            page_req_key=page_req_key
        )
        
        if ret == RET_OK:
            if not data.empty:
                all_dfs.append(data)
                print(f"    -> 成功获取 {len(data)} 根 K 线 (区间: {data.iloc[0]['time_key']} 至 {data.iloc[-1]['time_key']})")
            
            if page_req_key is None:
                print("[✓] 所有分页数据已全部拉取完毕！")
                break
        else:
            print(f"[✗] 拉取失败或到达终点: {data}")
            break
            
        time.sleep(0.35)  # 严格遵守 API 频控，防止封禁
        
    quote_ctx.close()
    
    if all_dfs:
        df_full = pd.concat(all_dfs, ignore_index=True)
        # 清洗与去重
        df_full.columns = [c.lower() for c in df_full.columns]
        df_full = df_full.drop_duplicates(subset=['time_key']).sort_values('time_key').reset_index(drop=True)
        
        clean_code = code.replace('.', '_')
        save_path = os.path.join(MARKET_DATA_DIR, f"{clean_code}_5M.csv")
        df_full.to_csv(save_path, index=False)
        print(f"=======================================================")
        print(f"🎉 [完成] {code} 总计 {len(df_full)} 根真实 5M 柱已安全存盘至: {save_path}")
        print(f"=======================================================\n")
        return save_path
    else:
        print(f"[!] 未能获取到 {code} 的历史数据，请确认 OpenD 是否处于连线状态。")
        return None

if __name__ == "__main__":
    # 默认拉取核心 QQQ，如需补充其他股票可在下方添加
    fetch_full_year_5m("US.QQQ")
