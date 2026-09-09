# 文件名: option_0dte_plugin.py
# 職責: QQQ / 美股核心 0DTE 智能期權射控座艙 (5M VPA 扳機 · 2B 突破偵測 · ATM 合約推薦 · 1:2 結構風控)

import os
import json
import datetime
import pytz
import numpy as np
import pandas as pd
import streamlit as st
from data_engine import hub_engine, get_active_session_info

tz_ny = pytz.timezone("America/New_York")
tz_my = pytz.timezone("Asia/Kuala_Lumpur")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")

def load_0dte_kline_context(code: str = "US.QQQ"):
    """加載 5M 與日線數據，計算 0DTE 關鍵空間邊界"""
    clean_code = code.replace('.', '_')
    p_5m = os.path.join(DATA_DIR, f"{clean_code}_5M.csv")
    p_day = os.path.join(DATA_DIR, f"{clean_code}_DAY.csv")

    df_5m = pd.DataFrame()
    df_day = pd.DataFrame()

    if os.path.exists(p_5m):
        try:
            df = pd.read_csv(p_5m)
            df.columns = [c.lower().strip() for c in df.columns]
            t_col = 'time_key' if 'time_key' in df.columns else df.columns[0]
            df['dt'] = pd.to_datetime(df[t_col])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df_5m = df.dropna().drop_duplicates('dt').sort_values('dt').reset_index(drop=True)
        except Exception:
            pass

    if os.path.exists(p_day):
        try:
            df = pd.read_csv(p_day)
            df.columns = [c.lower().strip() for c in df.columns]
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            df_day = df.dropna().reset_index(drop=True)
        except Exception:
            pass

    return df_5m, df_day

def analyze_0dte_signals(df_5m: pd.DataFrame, df_day: pd.DataFrame, target_code: str = "US.QQQ", budget_usd: float = 200.0):
    """
    0DTE 量化決策大腦：
    1. 計算昨日極值 PDH/PDL、今日盤前極值 PMH/PML、即時 SBR/RBS
    2. 判定最新 5M 是否觸發 2B 假突破或放量突破
    3. 輸出最佳 0DTE ATM 期權合約、開倉張數與 1:2 止損止盈執行價
    """
    if df_5m.empty or len(df_5m) < 20:
        return {"status": "fail", "msg": "5M 數據樣本不足"}

    # 1. 提取現價與最新時段
    curr_bar = df_5m.iloc[-1]
    curr_price = float(curr_bar['close'])
    curr_time_str = str(curr_bar['dt'])[:16]
    today_date_str = str(curr_bar['dt'])[:10]

    # 2. 昨日極值 (PDH / PDL)
    pdh = curr_price * 1.008
    pdl = curr_price * 0.992
    if not df_day.empty and len(df_day) >= 2:
        prev_day = df_day.iloc[-2]
        pdh = float(prev_day['high'])
        pdl = float(prev_day['low'])

    # 3. 今日盤前極值 (PMH / PML)
    df_today = df_5m[df_5m['dt'].dt.strftime('%Y-%m-%d') == today_date_str]
    hours = df_today['dt'].dt.hour
    mins = df_today['dt'].dt.minute
    t_mins = hours * 60 + mins
    df_pre = df_today[(t_mins >= 240) & (t_mins < 570)]

    if not df_pre.empty:
        pmh = float(df_pre['high'].max())
        pml = float(df_pre['low'].min())
    else:
        pmh = curr_price * 1.004
        pml = curr_price * 0.996

    # 4. 近期 SBR / RBS
    recent_slice = df_5m.tail(30)
    sbr = float(recent_slice['high'].max())
    rbs = float(recent_slice['low'].min())

    # 5. 5M 量能均線 (VMA20)
    df_5m['vma20'] = df_5m['volume'].rolling(window=20).mean()
    curr_vol = float(curr_bar['volume'])
    vma20_val = float(df_5m['vma20'].iloc[-1]) if pd.notna(df_5m['vma20'].iloc[-1]) and df_5m['vma20'].iloc[-1] > 0 else 1.0
    vol_ratio = curr_vol / vma20_val

    # 6. 2B 形態與扳機定罪
    is_bull_2b = False
    is_bear_2b = False
    prev_bar = df_5m.iloc[-2]

    # 多頭 2B 破底翻：前一根刺穿 PML/RBS，當前根強勢收回上方
    if prev_bar['low'] <= min(pml, rbs) and curr_bar['close'] > min(pml, rbs) and curr_bar['close'] >= curr_bar['open']:
        is_bull_2b = True

    # 空頭 2B 衝頂假突破：前一根衝破 PMH/SBR，當前根回落跌破下方
    if prev_bar['high'] >= max(pmh, sbr) and curr_bar['close'] < max(pmh, sbr) and curr_bar['close'] <= curr_bar['open']:
        is_bear_2b = True

    # 7. 戰術狀態與決策生成
    action_type = "WAIT"
    action_text = "⚪ 區間震盪蓄勢中 (未觸發 0DTE 邊界扳機 · 嚴禁半山腰追單)"
    action_color = "#8b949e"
    opt_type = "CALL"
    strike_price = round(curr_price)
    
    # 止損距離 (ATR 或影線邊界)
    risk_unit = max(0.60, abs(curr_bar['high'] - curr_bar['low']))
    
    if is_bull_2b and vol_ratio >= 1.25:
        action_type = "BUY_CALL"
        action_text = f"🔥 觸發多頭 2B 破底翻放量 (VPA {vol_ratio:.2f}x) ➔ 建議買入 0DTE ATM CALL"
        action_color = "#00E676"
        opt_type = "CALL"
        strike_price = int(np.ceil(curr_price))
        sl_price = curr_price - risk_unit
        tp_price = curr_price + 2.0 * risk_unit
    elif is_bear_2b and vol_ratio >= 1.25:
        action_type = "BUY_PUT"
        action_text = f"⚡ 觸發空頭 2B 衝頂假突破 (VPA {vol_ratio:.2f}x) ➔ 建議買入 0DTE ATM PUT"
        action_color = "#FF5252"
        opt_type = "PUT"
        strike_price = int(np.floor(curr_price))
        sl_price = curr_price + risk_unit
        tp_price = curr_price - 2.0 * risk_unit
    else:
        sl_price = curr_price - 1.0
        tp_price = curr_price + 2.0

    # 8. 期權合約定價推演 (0DTE Greeks 簡化模型)
    # 估算平值 ATM 0DTE 權利金單價 (通常在 $1.20 ~ $2.50 區間)
    est_opt_premium = max(1.10, round(abs(curr_price - strike_price) + 1.35, 2))
    contract_cost = est_opt_premium * 100.0 # 1 張期權 = 100 股
    max_contracts = max(1, int(budget_usd // contract_cost))
    total_budget_used = max_contracts * contract_cost

    opt_symbol = f"{target_code.replace('US.', '')}_{datetime.datetime.now(tz_ny).strftime('%y%m%d')}_{strike_price}{opt_type[0]}"
    
    # 期權止損止盈方案 (1:2 結構)
    opt_sl_price = round(est_opt_premium * 0.65, 2) # 虧損 -35% 硬止損
    opt_tp_price = round(est_opt_premium * 1.70, 2) # 獲利 +70% 止盈 (1:2 盈虧比)

    # 9. 過去 6 根 5M 量價數據表
    recent_6_bars = []
    for _, b in df_5m.tail(6).iterrows():
        b_vol = float(b['volume'])
        b_ratio = b_vol / vma20_val
        recent_6_bars.append({
            "time": str(b['dt'])[11:16],
            "open": f"${float(b['open']):.2f}",
            "high": f"${float(b['high']):.2f}",
            "low": f"${float(b['low']):.2f}",
            "close": f"${float(b['close']):.2f}",
            "vol_ratio": f"{b_ratio:.2f}x"
        })

    # 10. AI 0DTE 專用審計日誌
    ai_audit_md = f"""### ⚡ 【{target_code} 0DTE 日內期權戰術射控與風控日誌】
**審計基準時戳**: {curr_time_str} ET | **正股現價**: ${curr_price:.2f} | **單筆預算上限**: ${budget_usd:.2f} USD

#### 1. 當前空間戰區與極值邊界
- **昨日極值 (Prior Day)**: PDH (天花板): ${pdh:.2f} | PDL (地板): ${pdl:.2f}
- **今日盤前極值 (Pre-Market)**: PMH: ${pmh:.2f} | PML: ${pml:.2f}
- **近期水平攻防帶 (SBR/RBS)**: SBR: ${sbr:.2f} | RBS: ${rbs:.2f}
- **5M 即時量能比 (VPA Ratio)**: **{vol_ratio:.2f}x** (基準門禁 ≥ 1.25x)

#### 2. 0DTE 戰術指令與期權推薦
- **當前射控狀態**: **{action_text}**
- **推薦合約代碼**: `{opt_symbol}` (Strike: ${strike_price} | 方向: {opt_type})
- **估算權利金單價**: **${est_opt_premium:.2f}** (單張合約成本: ${contract_cost:.2f} USD)
- **頭寸管理**: 建議開倉 **{max_contracts}** 張 | 總動用資金: **${total_budget_used:.2f} USD**

#### 3. 1:2 結構止損止盈執行清單
- **正股錨定點位**: 入場: ${curr_price:.2f} | 止損: ${sl_price:.2f} | 2R止盈: ${tp_price:.2f}
- **0DTE 期權執行**:
  - 🛡️ 期權止損線 (-35% SL): **${opt_sl_price:.2f}**
  - 🎯 期權止盈線 (+70% TP): **${opt_tp_price:.2f}** (嚴格鎖定 1:2 盈虧比)

---
#### 4. 給 AI 軍師的 0DTE 診斷指令 (Prompt):
1. 正股現價 ${curr_price:.2f} 與最近的支撐/阻力邊界差價是多少？當前進場勝率幾何？
2. 5M 量能比 {vol_ratio:.2f}x 是否支持突破延續，還是有 Theta 快速磨損的風險？
"""

    return {
        "status": "success",
        "curr_price": curr_price,
        "curr_time": curr_time_str,
        "vol_ratio": vol_ratio,
        "pdh": pdh, "pdl": pdl,
        "pmh": pmh, "pml": pml,
        "sbr": sbr, "rbs": rbs,
        "action_type": action_type,
        "action_text": action_text,
        "action_color": action_color,
        "opt_symbol": opt_symbol,
        "strike_price": strike_price,
        "opt_type": opt_type,
        "est_opt_premium": est_opt_premium,
        "max_contracts": max_contracts,
        "total_budget_used": total_budget_used,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "opt_sl_price": opt_sl_price,
        "opt_tp_price": opt_tp_price,
        "recent_6_bars": recent_6_bars,
        "ai_audit_md": ai_audit_md
    }

def render_0dte_cockpit_view(assets=None):
    """0DTE 射控座艙 UI 入口"""
    default_symbols = ["US.QQQ", "US.NVDA", "US.TSLA", "US.AAPL", "US.AMD", "US.MSFT", "US.AMZN", "US.META"]
    symbol_options = []
    if isinstance(assets, list) and len(assets) > 0:
        for a in assets:
            if isinstance(a, dict) and 'code' in a:
                symbol_options.append(a['code'])
            elif isinstance(a, str):
                symbol_options.append(a)
    if not symbol_options:
        symbol_options = default_symbols

    c1, c2 = st.columns([3, 2])
    with c1:
        target_code = st.selectbox("🎯 選擇 0DTE 標的", symbol_options, index=0)
    with c2:
        budget_input = st.number_input("💰 單筆期權預算上限 (USD)", min_value=50.0, max_value=5000.0, value=200.0, step=50.0)

    # 1. 讀取數據與運算
    df_5m, df_day = load_0dte_kline_context(target_code)
    if df_5m.empty:
        st.warning(f"⚠️ {target_code} 暫無 5M 本地數據，請在終端執行 `python sync_history.py` 補齊。")
        return

    data = analyze_0dte_signals(df_5m, df_day, target_code=target_code, budget_usd=budget_input)
    if data["status"] != "success":
        st.error(f"❌ 計算失敗: {data.get('msg')}")
        return

    # 2. 頂部 HUD 狀態卡
    st.markdown(
        f"""
        <div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 12px 18px; margin-bottom: 12px; font-family: monospace;">
            <div style="font-size: 15px; font-weight: bold; color: #58a6ff; display: flex; justify-content: space-between; align-items: center;">
                <span>⚡ {target_code} · 0DTE 日內期權戰術射控艙</span>
                <span style="font-size: 12px; color: #8b949e;">數據時戳: {data['curr_time']} ET</span>
            </div>
            <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 20px; font-size: 13px; color: #c9d1d9;">
                <span>正股現價: <b style="color: #79c0ff;">${data['curr_price']:.2f}</b></span>
                <span>5M量能比: <b style="color: {'#00e676' if data['vol_ratio']>=1.25 else '#8b949e'};">{data['vol_ratio']:.2f}x</b></span>
                <span>PDH/PDL: <b style="color: #ffd600;">${data['pdh']:.2f}</b> / <b style="color: #ffd600;">${data['pdl']:.2f}</b></span>
                <span>PMH/PML: <b style="color: #56d364;">${data['pmh']:.2f}</b> / <b style="color: #56d364;">${data['pml']:.2f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 3. 核心決策指令卡
    st.markdown(
        f"""
        <div style="background: #161b22; border-left: 5px solid {data['action_color']}; border-radius: 6px; padding: 14px 18px; margin-bottom: 14px; font-family: monospace;">
            <div style="font-size: 15px; font-weight: bold; color: {data['action_color']};">{data['action_text']}</div>
            <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 24px; font-size: 13px; color: #c9d1d9;">
                <span>🎯 推薦合約: <b style="color: #ffd600;">{data['opt_symbol']}</b></span>
                <span>行權價: <b>${data['strike_price']} {data['opt_type']}</b></span>
                <span>估計單價: <b>${data['est_opt_premium']:.2f}</b></span>
                <span>推薦張數: <b style="color: #00e5ff;">{data['max_contracts']} 張</b> (動用: ${data['total_budget_used']:.2f})</span>
                <span>🛡️ 期權止損 (-35%): <b style="color: #ff7b72;">${data['opt_sl_price']:.2f}</b></span>
                <span>🎯 期權止盈 (+70%): <b style="color: #56d364;">${data['opt_tp_price']:.2f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 4. 5M 滾動量價即時監控表
    st.markdown("##### 📊 5M 即時量價核心表 (黃金滾動窗口)")
    df_bars = pd.DataFrame(data['recent_6_bars'])
    st.table(df_bars)

    # 5. AI 審計日誌
    st.divider()
    st.markdown("#### 🤖 AI 策略軍師 0DTE 專用審計 Markdown 日誌 (可直接複製)")
    st.caption("點擊下方右上角按鈕即可直接複製完整 0DTE 數據與風控計劃，貼入外部 AI 進行深度推演。")
    st.code(data["ai_audit_md"], language="markdown")
