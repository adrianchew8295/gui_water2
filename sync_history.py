# 文件名: sync_history.py
# 職責: 依據 watchlist.json 一鍵批量深度同步 12 檔標的數據基座 (5M 全時段 + 1H Resample + DAY)

import os
import json
import time
from data_engine import hub_engine

def run_batch_sync():
    watchlist_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.json")
    if not os.path.exists(watchlist_path):
        print("❌ 找不到 watchlist.json，請先確認配置檔案存在！")
        return

    try:
        with open(watchlist_path, "r", encoding="utf-8") as f:
            assets = json.load(f).get("assets", [])
    except Exception as e:
        print(f"❌ 讀取 watchlist.json 失敗: {e}")
        return

    total = len(assets)
    print("=" * 65)
    print(f"🚀 [Market Data Hub] 開始批量深度同步全體 {total} 檔標的數據基座...")
    print("=" * 65)

    for i, item in enumerate(assets):
        code = item["code"]
        name = item.get("name", code)
        print(f"\n[*] 正在同步 [{i+1:02d}/{total:02d}]: {code} ({name})")
        
        success, msg = hub_engine.sync_asset_deep_history(code=code, bars_5m=1500, bars_day=300)
        if success:
            print(f"  └── 🟢 {code} 數據同步成功 (5M 全時段 + 1H 聚合 + DAY 歷史)")
        else:
            print(f"  └── 🔴 {code} 同步失敗: {msg}")
        
        time.sleep(0.3)

    print("\n" + "=" * 65)
    print("🎉 全部 12 檔標的數據基座深度對齊完畢！")
    print("=" * 65)

if __name__ == "__main__":
    run_batch_sync()
