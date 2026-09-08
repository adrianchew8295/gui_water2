# 文件名: audit_comparator.py
# 职责: 第三方多源客观对账 (本地 CSV vs Tiingo IEX vs yfinance) 逐根验明真伪

import os
import json
import urllib.request
import datetime
import pandas as pd
import pytz
import yfinance as yf

tz_ny = pytz.timezone("America/New_York")
TIINGO_TOKEN = "bcffe3a5cf7eeef085e405cfa4a3e5691b976217"
CSV_PATH = "./market_data/US_QQQ_5M.csv"

def fetch_tiingo_5m():
    """从 Tiingo IEX 获取今日 5M 原始数据"""
    url = f"https://api.tiingo.com/iex/QQQ/prices?columns=open,high,low,close,volume&resampleFreq=5min&token={TIINGO_TOKEN}"
    try:
        req = urllib.request.Request(url, headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data:
                df = pd.DataFrame(data)
                df['time_key'] = pd.to_datetime(df['date']).dt.tz_convert(tz_ny).dt.strftime('%Y-%m-%d %H:%M:%S')
                return df[['time_key', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"⚠️ Tiingo 获取异常: {e}")
    return pd.DataFrame()

def fetch_yfinance_5m():
    """从 yfinance 获取今日 5M 原始数据"""
    try:
        df = yf.download(tickers="QQQ", period="1d", interval="5m", prepost=True, progress=False, auto_adjust=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [c[0].lower() for c in df.columns]
            else:
                df.columns = [c.lower() for c in df.columns]
            df = df.reset_index()
            dt_col = 'Datetime' if 'Datetime' in df.columns else df.columns[0]
            df['dt'] = pd.to_datetime(df[dt_col])
            if df['dt'].dt.tz is None:
                df['dt'] = df['dt'].dt.tz_localize('UTC').dt.tz_convert(tz_ny)
            else:
                df['dt'] = df['dt'].dt.tz_convert(tz_ny)
            df['time_key'] = df['dt'].dt.strftime('%Y-%m-%d %H:%M:%S')
            return df[['time_key', 'open', 'high', 'low', 'close', 'volume']]
    except Exception as e:
        print(f"⚠️ yfinance 获取异常: {e}")
    return pd.DataFrame()

def run_audit():
    print("="*80)
    print("🔍 【第三方跨源客观数据对账 (DATA INTEGRITY AUDITOR)】")
    print("="*80)
    
    if not os.path.exists(CSV_PATH):
        print("❌ 本地尚未找到 US_QQQ_5M.csv 档案！")
        return

    df_local = pd.read_csv(CSV_PATH)
    df_local.columns = [c.lower().strip() for c in df_local.columns]
    
    print(f"[*] 正在拉取 Tiingo IEX 机构通道数据 (Token: {TIINGO_TOKEN[:6]}***)...")
    df_tiin = fetch_tiingo_5m()
    
    print(f"[*] 正在拉取 yfinance 备用通道数据...")
    df_yf = fetch_yfinance_5m()
    
    # 提取本地最近 8 根 5M
    sample = df_local.tail(8).copy()
    
    print("\n" + "-"*80)
    print(f"{'美东时间 (ET)':<20} | {'本地 CSV 现价':<15} | {'Tiingo IEX':<15} | {'价差 (Diff)':<12} | {'判定结论'}")
    print("-"*80)
    
    for _, row in sample.iterrows():
        t_str = row['time_key']
        p_loc = float(row['close'])
        
        # 寻找 Tiingo 对应时间点
        p_tin = None
        if not df_tiin.empty:
            match_t = df_tiin[df_tiin['time_key'].str[:16] == t_str[:16]]
            if not match_t.empty:
                p_tin = float(match_t.iloc[0]['close'])
                
        # 寻找 yf 对应时间点
        p_yf_val = None
        if not df_yf.empty:
            match_y = df_yf[df_yf['time_key'].str[:16] == t_str[:16]]
            if not match_y.empty:
                p_yf_val = float(match_y.iloc[0]['close'])

        diff_str = "--"
        status = "🟢 100% 真实"
        
        ref_p = p_tin if p_tin is not None else p_yf_val
        if ref_p is not None:
            diff = abs(p_loc - ref_p)
            diff_str = f"${diff:.2f}"
            if diff > 0.5:
                status = f"⚠️ 偏差 ${diff:.2f}"
            else:
                status = "✅ 吻合 (偏差<0.1%)"
        else:
            status = "⚪ 第三方撮合稀疏"

        tin_str = f"${p_tin:,.2f}" if p_tin else ("$" + f"{p_yf_val:,.2f}" if p_yf_val else "无撮合")
        print(f"{t_str:<20} | ${p_loc:<14.2f} | {tin_str:<15} | {diff_str:<12} | {status}")

    print("="*80)
    print("💡 结论：若价差处于 $0.00 ~ $0.05 之间，说明本地数据为真实交易所撮合，可放心用于量化与实盘！\n")

if __name__ == "__main__":
    run_audit()
