# 文件名: sync_history.py
# 职责: 批量拉取资产池中所有标的的深度历史基座 (2年日线 / 1年1小时 / 30天5分钟)

import time
from data_engine import hub_engine

def run_sync():
    assets = hub_engine.load_watchlist()
    print("=" * 60)
    print(f"🚀 [Market Data Hub] 开始批量同步 {len(assets)} 档标的的历史数据基座...")
    print("=" * 60)

    for item in assets:
        code = item["code"]
        name = item.get("name", code)
        print(f"\n[*] 正在同步: {code} ({name})")

        # 1. DAY 日线 (2年 = 730天)
        _, msg_day = hub_engine.fetch_deep_history(code, "DAY", 730)
        print(f"  ├── 📅 日线 (DAY 2年): {msg_day}")
        time.sleep(0.3)

        # 2. 1H 小时线 (1年 = 365天)
        _, msg_1h = hub_engine.fetch_deep_history(code, "1H", 365)
        print(f"  ├── ⏱️ 1小时 (1H 1年): {msg_1h}")
        time.sleep(0.3)

        # 3. 5M 连续线 (30天)
        _, msg_5m = hub_engine.fetch_deep_history(code, "5M", 30)
        print(f"  └── ⚡ 5分钟 (5M 30天): {msg_5m}")
        time.sleep(0.3)

    print("\n" + "=" * 60)
    print("🎉 所有标的历史数据已全部成功落盘至 market_data/ 目录！")
    print("=" * 60)

if __name__ == "__main__":
    run_sync()
