# 文件名: data_engine.py
# 職責: 
# 1. 抓取包含美東 04:00~20:00 全時段 5M 原始流
# 2. 本地 Pandas 100% 精準 Resample 聚合生成無斷層 1H CSV
# 3. 倒序抓取真實不截斷日線 (DAY) 數據
# 4. 提供本地 CSV 自動緩存與容災備援

import os
import datetime
import pytz
import numpy as np
import pandas as pd

tz_ny = pytz.timezone("America/New_York")

def clean_kline_df(df: pd.DataFrame) -> pd.DataFrame:
    """標準化清洗 K 線欄位"""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [c.lower().strip() for c in df.columns]
    
    # 識別時間欄位
    time_col = 'time_key' if 'time_key' in df.columns else ('time_clean' if 'time_clean' in df.columns else df.columns[0])
    df['time_key'] = df[time_col].astype(str)
    
    # 強制數值型別轉換
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
    
    # 標準金融 1 小時聚合規則
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

class MarketDataEngine:
    def __init__(self, data_dir: str = "./market_data"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def sync_asset_deep_history(self, code: str = "US.NVDA", bars_5m: int = 3000, bars_day: int = 300):
        """
        核心同步管道：
        1. 向 OpenD 倒序拉取最新 bars_5m 根全時段 5M 數據 -> 存入 _5M.csv
        2. 本地 Resample 生成 _1H.csv
        3. 向 OpenD 倒序拉取最新 bars_day 根日線數據 -> 存入 _DAY.csv
        """
        clean_code = code.replace('.', '_')
        p_5m = os.path.join(self.data_dir, f"{clean_code}_5M.csv")
        p_1h = os.path.join(self.data_dir, f"{clean_code}_1H.csv")
        p_day = os.path.join(self.data_dir, f"{clean_code}_DAY.csv")

        print(f"\n========================================================")
        print(f"🔗 開始深度同步 {code} 數據基座 (5M 全時段 + 1H Resample + DAY)...")
        print(f"========================================================")

        try:
            from moomoo import OpenQuoteContext, RET_OK, KLType, AuType
            quote_ctx = OpenQuoteContext(host='127.0.0.1', port=11111)
            now_ny = datetime.datetime.now(tz_ny)
            end_str = now_ny.strftime("%Y-%m-%d %H:%M:%S")

            # 1. 抓取 5M 全時段歷史 (倒序抓取最新 bars_5m 根)
            ret_5m, df_5m_raw, _ = quote_ctx.request_history_kline(
                code=code,
                start='',
                end=end_str,
                ktype=KLType.K_5M,
                autype=AuType.QFQ,
                max_count=bars_5m,
                extended_time=True # 啟用盤前盤後 04:00~20:00
            )

            if ret_5m == RET_OK and df_5m_raw is not None and not df_5m_raw.empty:
                df_5m = clean_kline_df(df_5m_raw)
                df_5m.to_csv(p_5m, index=False)
                print(f"✅ [5M 同步成功] 已寫入 {len(df_5m)} 根全時段 5M K線 -> {p_5m}")

                # 2. 本地 Resample 聚合 1H
                df_1h = resample_5m_to_1h(df_5m)
                df_1h.to_csv(p_1h, index=False)
                print(f"✅ [1H 聚合成功] 已由 5M 成功合成 {len(df_1h)} 根連續 1H K線 -> {p_1h}")
            else:
                print(f"⚠️ [5M 抓取異常] OpenD 回應: {df_5m_raw}")

            # 3. 抓取日線歷史 (倒序抓取最新 bars_day 根)
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
                print(f"✅ [DAY 同步成功] 已寫入 {len(df_day)} 根日線 K線 -> {p_day}")
            else:
                print(f"⚠️ [DAY 抓取異常] OpenD 回應: {df_day_raw}")

            quote_ctx.close()
            return True, "同步完成"

        except Exception as e:
            print(f"❌ [連接異常] 請確認 OpenD 是否已登入並監聽 11111: {str(e)}")
            return False, str(e)

data_engine = MarketDataEngine()

if __name__ == "__main__":
    # 預設直接對 US.NVDA 與 US.QQQ 進行基準測試
    data_engine.sync_asset_deep_history("US.NVDA", bars_5m=1500, bars_day=300)
    data_engine.sync_asset_deep_history("US.QQQ", bars_5m=1500, bars_day=300)
