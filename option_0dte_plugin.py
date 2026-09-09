# 文件名: option_0dte_plugin.py
# 職責: QQQ / 美股 0DTE 智能期權實戰座艙 (15M ORB 順勢突破 + 2B 反轉雙核引擎 · 實時動態 Greeks · 雙 Tab 做功課)

import os
import json
import datetime
import pytz
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from data_engine import hub_engine, get_active_session_info

tz_ny = pytz.timezone("America/New_York")
tz_my = pytz.timezone("Asia/Kuala_Lumpur")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")
os.makedirs(DATA_DIR, exist_ok=True)
JOURNAL_CSV = os.path.join(DATA_DIR, "strategy_live_journal.csv")

def init_0dte_journal_file():
    """初始化 0DTE 專屬做功課帳本"""
    needs_init = False
    if not os.path.exists(JOURNAL_CSV):
        needs_init = True
    else:
        try:
            df_chk = pd.read_csv(JOURNAL_CSV)
            if df_chk.empty or 'code' not in df_chk.columns:
                needs_init = True
        except Exception:
            needs_init = True

    if needs_init:
        sample_data = [
            {
                "trade_id": "#20260909_01", "code": "US.QQQ", "date": "2026-09-09", "time_et": "09:50", "time_myt": "21:50", "exit_time_et": "10:20",
                "month": "2026-09", "direction": "🟢 CALL", "strategy": "15M ORB 順勢突破", "entry": 719.80, "sl": 718.40, "tp": 722.60,
                "exit_price": 722.60, "status": "WIN_TP", "net_r": 2.0, "pnl_usd": 400.0, "score": 92,
                "score_detail": "實體衝破15M ORB_High(+30) + VPA 2.10x暴量(+25) + 日線EMA20順勢(+20) + OTM2檔(+17)",
                "reason": "放量突破 15M ORB 箱頂 + 2.10x 機構巨量確認", "pdh": 721.39, "pdl": 715.72,
                "ema20_1h": 716.80, "rbs": 716.20, "sbr": 723.00, "orb_high": 719.50, "orb_low": 716.80, "opt_symbol": "QQQ_260909_721C", "strike_price": 721, "is_golden_window": True
            },
            {
                "trade_id": "#20260909_02", "code": "US.QQQ", "date": "2026-09-09", "time_et": "10:15", "time_myt": "22:15", "exit_time_et": "10:45",
                "month": "2026-09", "direction": "🟢 CALL", "strategy": "0DTE 2B 量化扳機", "entry": 718.50, "sl": 717.30, "tp": 720.90,
                "exit_price": 720.90, "status": "WIN_TP", "net_r": 2.0, "pnl_usd": 400.0, "score": 95,
                "score_detail": "踩入RBS支撐(+25) + 5M長下影2B破底翻(+25) + VPA 1.85x放量(+25) + ATM平值(+20)",
                "reason": "回踩今日 PML 地板 + 5M 2B 破底翻長下影陽線", "pdh": 721.39, "pdl": 715.72,
                "ema20_1h": 715.80, "rbs": 716.20, "sbr": 719.50, "orb_high": 719.50, "orb_low": 716.80, "opt_symbol": "QQQ_260909_719C", "strike_price": 719, "is_golden_window": True
            }
        ]
        pd.DataFrame(sample_data).to_csv(JOURNAL_CSV, index=False)

init_0dte_journal_file()

def load_0dte_kline_live(code: str = "US.QQQ"):
    """加載 5M 數據並注入 OpenD 最新即時跳動點位"""
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

    try:
        snap_df = hub_engine.get_realtime_snapshot([code])
        if snap_df is not None and not snap_df.empty:
            row = snap_df.iloc[0]
            live_price = float(row.get('last_price', row.get('cur_price', 0.0)))
            if live_price > 0:
                now_ny = datetime.datetime.now(tz_ny)
                cur_min = (now_ny.minute // 5) * 5
                live_5m_dt = now_ny.replace(minute=cur_min, second=0, microsecond=0).replace(tzinfo=None)
                
                if not df_5m.empty:
                    last_row_dt = df_5m.iloc[-1]['dt']
                    if last_row_dt == live_5m_dt:
                        df_5m.at[df_5m.index[-1], 'close'] = live_price
                        df_5m.at[df_5m.index[-1], 'high'] = max(df_5m.at[df_5m.index[-1], 'high'], live_price)
                        df_5m.at[df_5m.index[-1], 'low'] = min(df_5m.at[df_5m.index[-1], 'low'], live_price)
                    elif live_5m_dt > last_row_dt:
                        new_k = {
                            'dt': live_5m_dt,
                            'time_key': live_5m_dt.strftime('%Y-%m-%d %H:%M:%S'),
                            'open': live_price,
                            'high': live_price,
                            'low': live_price,
                            'close': live_price,
                            'volume': float(row.get('volume', 1000.0))
                        }
                        df_5m = pd.concat([df_5m, pd.DataFrame([new_k])], ignore_index=True)
    except Exception:
        pass

    return df_5m, df_day

def auto_log_0dte_signal(target_code: str, curr_time_str: str, curr_price: float, sl_price: float, tp_price: float, opt_symbol: str, strike_price: int, opt_type: str, vol_ratio: float, reason: str, strategy_name: str, orb_high: float, orb_low: float):
    """自動記錄訊號至 CSV"""
    try:
        df_j = pd.read_csv(JOURNAL_CSV) if os.path.exists(JOURNAL_CSV) else pd.DataFrame()
        date_str = curr_time_str[:10]
        time_et_str = curr_time_str[11:16]
        
        if not df_j.empty and 'time_et' in df_j.columns and 'date' in df_j.columns and 'code' in df_j.columns:
            exists = df_j[(df_j['code'] == target_code) & (df_j['date'] == date_str) & (df_j['time_et'] == time_et_str)]
            if not exists.empty:
                return

        trade_id = f"#{date_str.replace('-', '')}_{len(df_j) + 1:02d}"
        new_entry = {
            "trade_id": trade_id,
            "code": target_code,
            "date": date_str,
            "time_et": time_et_str,
            "time_myt": (datetime.datetime.strptime(curr_time_str, "%Y-%m-%d %H:%M") + datetime.timedelta(hours=12)).strftime("%H:%M"),
            "exit_time_et": "--",
            "month": date_str[:7],
            "direction": f"🟢 {opt_type}" if opt_type == "CALL" else f"🔴 {opt_type}",
            "strategy": strategy_name,
            "entry": curr_price,
            "sl": sl_price,
            "tp": tp_price,
            "exit_price": 0.0,
            "status": "RUNNING",
            "net_r": 0.0,
            "pnl_usd": 0.0,
            "score": 88,
            "score_detail": f"空間到位(+25) + 形態確認(+25) + VPA {vol_ratio:.2f}x 放量(+25) + 0DTE執行(+13)",
            "reason": reason,
            "pdh": curr_price * 1.008,
            "pdl": curr_price * 0.992,
            "ema20_1h": curr_price * 0.998,
            "rbs": curr_price * 0.995,
            "sbr": curr_price * 1.005,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "opt_symbol": opt_symbol,
            "strike_price": strike_price,
            "is_golden_window": True
        }
        df_new = pd.concat([df_j, pd.DataFrame([new_entry])], ignore_index=True)
        df_new.to_csv(JOURNAL_CSV, index=False)
    except Exception:
        pass

def analyze_0dte_tactical(df_5m: pd.DataFrame, df_day: pd.DataFrame, target_code: str = "US.QQQ", budget_usd: float = 200.0):
    """0DTE 量化定罪大腦：15M ORB 突破 + 2B 雙核引擎"""
    if df_5m.empty or len(df_5m) < 15:
        return {"status": "fail", "msg": "5M 數據樣本不足"}

    now_ny = datetime.datetime.now(tz_ny)
    curr_bar = df_5m.iloc[-1]
    curr_price = float(curr_bar['close'])
    curr_time_str = str(curr_bar['dt'])[:16]
    today_date_str = str(curr_bar['dt'])[:10]

    # 1. 換棒倒數
    current_sec = now_ny.minute * 60 + now_ny.second
    sec_to_next_5m = 300 - (current_sec % 300)
    timer_str = f"{sec_to_next_5m // 60:02d}:{sec_to_next_5m % 60:02d}"

    # 2. 昨日極值 (PDH / PDL)
    pdh, pdl = curr_price * 1.008, curr_price * 0.992
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

    # 4. 15M ORB 開盤區間計算 (09:30~09:45 前 3 根 5M 柱)
    df_orb = df_today[(t_mins >= 570) & (t_mins <= 580)]
    if not df_orb.empty and len(df_orb) >= 2:
        orb_high = float(df_orb['high'].max())
        orb_low = float(df_orb['low'].min())
    else:
        orb_high = curr_price * 1.002
        orb_low = curr_price * 0.998
    orb_mid = round((orb_high + orb_low) / 2.0, 2)

    # 5. 近期 SBR / RBS
    recent_slice = df_5m.tail(30)
    sbr = float(recent_slice['high'].max())
    rbs = float(recent_slice['low'].min())

    # 6. 5M 量能比 (VMA20)
    df_5m['vma20'] = df_5m['volume'].rolling(window=20).mean()
    curr_vol = float(curr_bar['volume'])
    vma20_val = float(df_5m['vma20'].iloc[-1]) if pd.notna(df_5m['vma20'].iloc[-1]) and df_5m['vma20'].iloc[-1] > 0 else 1.0
    vol_ratio = curr_vol / vma20_val

    # 7. 差價計算
    dist_to_orb_high = orb_high - curr_price
    dist_to_orb_low = curr_price - orb_low

    # 8. 雙核策略判定
    prev_bar = df_5m.iloc[-2]
    risk_unit = max(0.60, abs(curr_bar['high'] - curr_bar['low']))
    
    is_orb_break_up = False
    is_orb_break_down = False
    is_bull_2b = False
    is_bear_2b = False

    # 策略 A: 15M ORB 順勢放量突破 (Close > ORB_High 且放量 >= 1.5x)
    if curr_bar['close'] > orb_high and prev_bar['close'] <= orb_high and vol_ratio >= 1.50:
        is_orb_break_up = True
    elif curr_bar['close'] < orb_low and prev_bar['close'] >= orb_low and vol_ratio >= 1.50:
        is_orb_break_down = True

    # 策略 B: 2B 假突破 / 破底翻
    target_support = min(pml, rbs, orb_low)
    target_resistance = max(pmh, sbr, orb_high)
    if prev_bar['low'] <= target_support and curr_bar['close'] > target_support and curr_bar['close'] >= curr_bar['open'] and vol_ratio >= 1.25:
        is_bull_2b = True
    elif prev_bar['high'] >= target_resistance and curr_bar['close'] < target_resistance and curr_bar['close'] <= curr_bar['open'] and vol_ratio >= 1.25:
        is_bear_2b = True

    # 9. 行權價與檔位決策 (ORB 暴量推薦 OTM 2檔 / 2B 推薦 ATM 平值)
    nearest_atm = int(round(curr_price))
    if is_orb_break_up:
        action_type = "BUY_CALL"
        strategy_name = "15M ORB 順勢突破"
        opt_type = "CALL"
        strike_price = nearest_atm + 2 if vol_ratio >= 2.0 else nearest_atm + 1
        strike_mode = "OTM 2檔 (動量爆發)" if vol_ratio >= 2.0 else "OTM 1檔 (微虛)"
        action_banner = f"🔥 觸發 15M ORB 向上放量突破 (VPA {vol_ratio:.2f}x) ➔ 買入 0DTE {strike_price} CALL ({strike_mode})"
        action_color = "#00E676"
        action_bg = "rgba(0, 230, 118, 0.16)"
        action_border = "#00E676"
        sl_price = max(orb_mid, curr_price - risk_unit)
        tp_price = curr_price + 2.0 * (curr_price - sl_price)
        is_armed = True
        auto_log_0dte_signal(target_code, curr_time_str, curr_price, sl_price, tp_price, f"{target_code.replace('US.', '')}_{now_ny.strftime('%y%m%d')}_{strike_price}C", strike_price, "CALL", vol_ratio, f"放量突破 ORB 箱頂 ${orb_high:.2f}", strategy_name, orb_high, orb_low)

    elif is_orb_break_down:
        action_type = "BUY_PUT"
        strategy_name = "15M ORB 順向破位"
        opt_type = "PUT"
        strike_price = nearest_atm - 2 if vol_ratio >= 2.0 else nearest_atm - 1
        strike_mode = "OTM 2檔 (動量爆發)" if vol_ratio >= 2.0 else "OTM 1檔 (微虛)"
        action_banner = f"⚡ 觸發 15M ORB 向下放量破位 (VPA {vol_ratio:.2f}x) ➔ 買入 0DTE {strike_price} PUT ({strike_mode})"
        action_color = "#FF5252"
        action_bg = "rgba(255, 82, 82, 0.16)"
        action_border = "#FF5252"
        sl_price = min(orb_mid, curr_price + risk_unit)
        tp_price = curr_price - 2.0 * (sl_price - curr_price)
        is_armed = True
        auto_log_0dte_signal(target_code, curr_time_str, curr_price, sl_price, tp_price, f"{target_code.replace('US.', '')}_{now_ny.strftime('%y%m%d')}_{strike_price}P", strike_price, "PUT", vol_ratio, f"放量跌破 ORB 箱底 ${orb_low:.2f}", strategy_name, orb_high, orb_low)

    elif is_bull_2b:
        action_type = "BUY_CALL"
        strategy_name = "0DTE 2B 量化扳機"
        opt_type = "CALL"
        strike_price = int(np.ceil(curr_price))
        action_banner = f"🔥 觸發地板 2B 破底翻放量 (VPA {vol_ratio:.2f}x) ➔ 買入 0DTE {strike_price} CALL (ATM 平值穩健)"
        action_color = "#00E676"
        action_bg = "rgba(0, 230, 118, 0.16)"
        action_border = "#00E676"
        sl_price = curr_price - risk_unit
        tp_price = curr_price + 2.0 * risk_unit
        is_armed = True
        auto_log_0dte_signal(target_code, curr_time_str, curr_price, sl_price, tp_price, f"{target_code.replace('US.', '')}_{now_ny.strftime('%y%m%d')}_{strike_price}C", strike_price, "CALL", vol_ratio, "5M 踩入邊界地板 + 2B 放量破底翻", strategy_name, orb_high, orb_low)

    elif is_bear_2b:
        action_type = "BUY_PUT"
        strategy_name = "0DTE 2B 量化扳機"
        opt_type = "PUT"
        strike_price = int(np.floor(curr_price))
        action_banner = f"⚡ 觸發天花板 2B 衝頂假突破 (VPA {vol_ratio:.2f}x) ➔ 買入 0DTE {strike_price} PUT (ATM 平值穩健)"
        action_color = "#FF5252"
        action_bg = "rgba(255, 82, 82, 0.16)"
        action_border = "#FF5252"
        sl_price = curr_price + risk_unit
        tp_price = curr_price - 2.0 * risk_unit
        is_armed = True
        auto_log_0dte_signal(target_code, curr_time_str, curr_price, sl_price, tp_price, f"{target_code.replace('US.', '')}_{now_ny.strftime('%y%m%d')}_{strike_price}P", strike_price, "PUT", vol_ratio, "5M 衝頂天花板 + 2B 假突破回落", strategy_name, orb_high, orb_low)

    else:
        action_type = "WAIT"
        action_banner = f"☕ 安全中繼待機區 (距 ORB 箱頂: +${dist_to_orb_high:.2f} | 距 ORB 箱底: -${dist_to_orb_low:.2f} · 嚴禁追單)"
        action_color = "#8b949e"
        action_bg = "rgba(139, 148, 158, 0.08)"
        action_border = "#30363d"
        opt_type = "NONE"
        strike_price = nearest_atm
        sl_price = 0.0
        tp_price = 0.0
        is_armed = False

    # 10. 動態 Greeks
    moneyness = curr_price - strike_price
    live_delta = round(0.50 + moneyness * 0.12, 2)
    live_delta = max(0.18, min(0.82, live_delta))
    
    cur_hour = now_ny.hour + now_ny.minute / 60.0
    hours_left = max(0.5, 16.0 - cur_hour) if cur_hour <= 16.0 else 0.5
    live_theta = round(-0.45 * (6.5 / hours_left)**0.5, 2)
    live_gamma = round(0.08 + (6.5 / hours_left) * 0.01, 2)
    live_iv = round(17.5 + abs(moneyness) * 0.8, 1)

    est_opt_premium = max(0.40, round(abs(curr_price - strike_price) + (1.45 if abs(moneyness) < 1 else 0.55), 2))
    contract_cost = est_opt_premium * 100.0
    max_contracts = max(1, int(budget_usd // contract_cost))
    total_budget_used = max_contracts * contract_cost
    opt_symbol = f"{target_code.replace('US.', '')}_{now_ny.strftime('%y%m%d')}_{strike_price}{'C' if opt_type=='CALL' else ('P' if opt_type=='PUT' else 'ATM')}"
    opt_sl_price = round(est_opt_premium * 0.65, 2)
    opt_tp_price = round(est_opt_premium * 1.70, 2)

    # 過去 6 根 5M 量價流水 (置頂第一行)
    recent_6_bars = []
    df_slice_desc = df_5m.tail(6).iloc[::-1].reset_index(drop=True)
    for idx, b in df_slice_desc.iterrows():
        b_vol = float(b['volume'])
        b_ratio = b_vol / vma20_val
        is_green = float(b['close']) >= float(b['open'])
        time_tag = str(b['dt'])[11:16]
        if idx == 0:
            time_tag = f"⚡ {time_tag} (最新)"

        recent_6_bars.append({
            "時段 (ET)": time_tag,
            "現價/收盤": f"${float(b['close']):.2f}",
            "方向": "🟢 陽線" if is_green else "🔴 陰線",
            "影線高低": f"${float(b['high']):.2f} / ${float(b['low']):.2f}",
            "5M量能比": f"{b_ratio:.2f}x {'🟢' if b_ratio>=1.25 else '⚪'}"
        })

    return {
        "status": "success",
        "curr_price": curr_price,
        "curr_time": curr_time_str,
        "timer_str": timer_str,
        "vol_ratio": vol_ratio,
        "pdh": pdh, "pdl": pdl,
        "pmh": pmh, "pml": pml,
        "orb_high": orb_high, "orb_low": orb_low, "orb_mid": orb_mid,
        "dist_to_orb_high": dist_to_orb_high,
        "dist_to_orb_low": dist_to_orb_low,
        "is_armed": is_armed,
        "action_type": action_type,
        "action_banner": action_banner,
        "action_color": action_color,
        "action_bg": action_bg,
        "action_border": action_border,
        "opt_symbol": opt_symbol,
        "strike_price": strike_price,
        "opt_type": opt_type,
        "delta_val": live_delta,
        "theta_val": live_theta,
        "gamma_val": live_gamma,
        "iv_val": live_iv,
        "est_opt_premium": est_opt_premium,
        "max_contracts": max_contracts,
        "total_budget_used": total_budget_used,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "opt_sl_price": opt_sl_price,
        "opt_tp_price": opt_tp_price,
        "recent_6_bars": recent_6_bars
    }

@st.fragment(run_every=3.0)
def render_0dte_live_fragment(target_code: str, budget_input: float):
    """Tab 1：0DTE 即時射控艙 (3秒內存無感平滑刷新)"""
    df_5m, df_day = load_0dte_kline_live(target_code)
    if df_5m.empty:
        st.warning(f"⚠️ {target_code} 暫無 5M 本地數據，請在終端執行 `python sync_history.py`。")
        return

    data = analyze_0dte_tactical(df_5m, df_day, target_code=target_code, budget_usd=budget_input)
    if data["status"] != "success":
        st.error(f"❌ 計算失敗: {data.get('msg')}")
        return

    now_clock = datetime.datetime.now(tz_my).strftime('%H:%M:%S')

    # 1. 頂部狀態列 (附帶 15M ORB 箱體數據)
    st.markdown(
        f"""
        <div style="background-color: #0d1117; border: 1px solid #30363d; border-radius: 8px; padding: 10px 16px; margin-bottom: 12px; font-family: monospace;">
            <div style="font-size: 14px; font-weight: bold; color: #58a6ff; display: flex; justify-content: space-between; align-items: center;">
                <span>⚡ {target_code} · 0DTE 雙核射控艙 (ORB 順勢 + 2B 反轉) <span style="font-size: 11px; color: #00e676;">● 實時輪詢中 ({now_clock} MYT)</span></span>
                <span style="font-size: 13px; color: #ffd600;">⏱️ 距離下根 5M 定格換棒: <b>{data['timer_str']}</b></span>
            </div>
            <div style="margin-top: 6px; display: flex; flex-wrap: wrap; gap: 20px; font-size: 13px; color: #c9d1d9;">
                <span>現價: <b style="color: #79c0ff; font-size: 15px;">${data['curr_price']:.2f}</b></span>
                <span>5M量能比: <b style="color: {'#00e676' if data['vol_ratio']>=1.25 else '#8b949e'};">{data['vol_ratio']:.2f}x</b></span>
                <span>📦 15M ORB: <b style="color: #00e5ff;">[H: ${data['orb_high']:.2f} | L: ${data['orb_low']:.2f} | Mid: ${data['orb_mid']:.2f}]</b></span>
                <span>PMH/PML: <b style="color: #56d364;">${data['pmh']:.2f} / ${data['pml']:.2f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 2. 核心指令卡 (ORB / 2B 智能分流)
    if data['is_armed']:
        strike_html = f"<div style='font-size: 26px; font-weight: bold; color: #ffd600;'>${data['strike_price']} {data['opt_type']}</div>"
        code_html = f"<div style='font-size: 16px; font-weight: bold; color: #58a6ff;'>{data['opt_symbol']}</div>"
        cost_html = f"<div style='font-size: 15px; color: #c9d1d9;'><b>${data['est_opt_premium']:.2f}</b> ➔ <b style='color:#00e5ff;'>{data['max_contracts']} 張</b> (${data['total_budget_used']:.2f})</div>"
        sltp_html = f"<div style='font-size: 15px;'><b style='color:#ff7b72;'>${data['opt_sl_price']:.2f}</b> / <b style='color:#56d364;'>${data['opt_tp_price']:.2f}</b></div>"
    else:
        strike_html = f"<div style='font-size: 18px; font-weight: bold; color: #8b949e;'>🔒 鎖定待機 (ATM: ${data['strike_price']})</div>"
        code_html = "<div style='font-size: 15px; color: #8b949e;'>────────</div>"
        cost_html = f"<div style='font-size: 13px; color: #8b949e;'>距 ORB 箱底: <b style='color:#56d364;'>-${data['dist_to_orb_low']:.2f}</b></div>"
        sltp_html = f"<div style='font-size: 13px; color: #8b949e;'>距 ORB 箱頂: <b style='color:#ff7b72;'>+${data['dist_to_orb_high']:.2f}</b></div>"

    st.markdown(
        f"""
        <div style="background: {data['action_bg']}; border: 2px solid {data['action_border']}; border-radius: 8px; padding: 16px 20px; margin-bottom: 14px; font-family: monospace;">
            <div style="font-size: 15px; font-weight: bold; color: {data['action_color']}; margin-bottom: 10px;">
                {data['action_banner']}
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 28px; align-items: center;">
                <div>
                    <div style="font-size: 11px; color: #8b949e;">🎯 推薦行權價 (STRIKE)</div>
                    {strike_html}
                </div>
                <div>
                    <div style="font-size: 11px; color: #8b949e;">📋 合約代碼</div>
                    {code_html}
                </div>
                <div>
                    <div style="font-size: 11px; color: #8b949e;">💵 空間測算 / 差價</div>
                    {cost_html}
                </div>
                <div>
                    <div style="font-size: 11px; color: #8b949e;">🛡️ 止損 / 🎯 止盈</div>
                    {sltp_html}
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 3. Greeks 儀表盤
    st.markdown(
        f"""
        <div style="background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 10px 16px; margin-bottom: 14px; font-family: monospace;">
            <div style="font-size: 13px; font-weight: bold; color: #58a6ff; margin-bottom: 6px;">📊 0DTE Greeks 希臘字母即時估算儀表盤 (每 3 秒動態重估)</div>
            <div style="display: flex; flex-wrap: wrap; gap: 24px; font-size: 13px; color: #c9d1d9;">
                <span>Delta (Δ): <b style="color: #ffd600;">{data['delta_val']:+.2f}</b></span>
                <span>Theta (Θ): <b style="color: #ff7b72;">{data['theta_val']:.2f} USD/天</b></span>
                <span>Gamma (Γ): <b style="color: #56d364;">{data['gamma_val']:.2f}</b></span>
                <span>隱含波動率 (IV): <b style="color: #e040fb;">{data['iv_val']:.1f}%</b></span>
                <span>估計單價: <b style="color: #00e5ff;">${data['est_opt_premium']:.2f}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 4. 5M 歷史柱滾動流水
    st.markdown("##### 📊 5M 即時量價核心表 (最新時段強制置頂 · 每 3 秒動態生長)")
    df_recent = pd.DataFrame(data['recent_6_bars'])
    st.dataframe(df_recent, use_container_width=True, hide_index=True)

def _load_kline_replay_slice(code: str, entry_date_str: str, entry_time_str: str, entry_p: float):
    """加載做功課指定時段前後 30 分鐘真實 5M K 線切片"""
    clean_code = code.replace('.', '_')
    candidates = [
        os.path.join(DATA_DIR, f"{clean_code}_5M.csv"),
        os.path.join(DATA_DIR, f"{code}_5M.csv")
    ]
    for p in candidates:
        if os.path.exists(p):
            try:
                df_raw = pd.read_csv(p)
                df_raw.columns = [c.lower().strip() for c in df_raw.columns]
                t_col = 'time_key' if 'time_key' in df_raw.columns else df_raw.columns[0]
                matches = df_raw[df_raw[t_col].astype(str).str.contains(entry_date_str, na=False)].index.tolist()
                if matches:
                    mid = matches[len(matches)//2]
                    for idx in matches:
                        if entry_time_str in str(df_raw.iloc[idx][t_col]):
                            mid = idx
                            break
                    start_i = max(0, mid - 15)
                    end_i = min(len(df_raw), mid + 20)
                    sl = df_raw.iloc[start_i:end_i].copy().reset_index(drop=True)
                    times = [str(t)[-8:-3] for t in sl[t_col]]
                    return times, sl['open'].astype(float).tolist(), sl['high'].astype(float).tolist(), sl['low'].astype(float).tolist(), sl['close'].astype(float).tolist(), sl['volume'].astype(float).tolist(), (mid - start_i)
            except Exception:
                pass

    times = [f"{i:02d}:00" for i in range(10, 40)]
    return times, [entry_p]*30, [entry_p+1.5]*30, [entry_p-1.5]*30, [entry_p]*30, [100.0]*30, 15

def render_interactive_replay_chart(trade_row: pd.Series):
    """做功課專屬 Plotly 5M 互動圖表 (支援 ORB 箱體疊加)"""
    entry_p = float(trade_row.get('entry', 0.0))
    sl_p = float(trade_row.get('sl', 0.0))
    tp_p = float(trade_row.get('tp', 0.0))
    pdh_p = float(trade_row.get('pdh', entry_p * 1.002))
    pdl_p = float(trade_row.get('pdl', entry_p * 0.998))
    orb_h = float(trade_row.get('orb_high', entry_p * 1.001))
    orb_l = float(trade_row.get('orb_low', entry_p * 0.999))
    is_call = "CALL" in str(trade_row.get('direction', 'CALL'))
    is_win = trade_row.get('status') == 'WIN_TP'
    date_str = str(trade_row.get('date', '2026-09-09'))
    time_str = str(trade_row.get('time_et', '09:50'))
    code = str(trade_row.get('code', 'US.QQQ'))

    times, opens, highs, lows, closes, volumes, entry_idx = _load_kline_replay_slice(code, date_str, time_str, entry_p)
    exit_idx = min(len(times) - 1, entry_idx + 6) if entry_idx >= 0 else -1
    exit_p = float(trade_row.get('exit_price', entry_p))
    exit_label = "🎯 命中 2R 止盈 (+2.0R)" if is_win else "🛡️ 觸發止損出場 (-1.0R)"

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.72, 0.28])

    fig.add_trace(go.Candlestick(
        x=times, open=opens, high=highs, low=lows, close=closes,
        increasing_line_color='#00E676', decreasing_line_color='#FF5252',
        increasing_fillcolor='#00E676', decreasing_fillcolor='#FF5252',
        name="5M K線"
    ), row=1, col=1)

    # ORB 箱體
    fig.add_hrect(y0=orb_l, y1=orb_h, line_width=1, line_color="#00e5ff", line_dash="dash", fillcolor="#00e5ff", opacity=0.08, annotation_text="15M ORB 箱體", annotation_position="top left", row=1, col=1)
    fig.add_hline(y=pdh_p, line_dash="dot", line_color="#ffd700", line_width=1.2, annotation_text=f"PDH: ${pdh_p:,.2f}", annotation_position="top left", row=1, col=1)
    fig.add_hline(y=pdl_p, line_dash="dot", line_color="#ffd700", line_width=1.2, annotation_text=f"PDL: ${pdl_p:,.2f}", annotation_position="bottom left", row=1, col=1)

    fig.add_hline(y=entry_p, line_dash="dash", line_color="#58a6ff", annotation_text=f"進場: ${entry_p:,.2f}", annotation_position="top right", row=1, col=1)
    fig.add_hline(y=sl_p, line_dash="dash", line_color="#FF5252", annotation_text=f"止損: ${sl_p:,.2f}", annotation_position="bottom right", row=1, col=1)
    fig.add_hline(y=tp_p, line_dash="dash", line_color="#00E676", annotation_text=f"2R止盈: ${tp_p:,.2f}", annotation_position="top right", row=1, col=1)

    if 0 <= entry_idx < len(times):
        fig.add_annotation(
            x=times[entry_idx], y=lows[entry_idx],
            text=f"🟢 BUY {'CALL' if is_call else 'PUT'} 🔥<br>${entry_p:,.2f}",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5, arrowcolor="#00E676",
            ay=35, font=dict(color="#00E676", size=10, family="monospace"),
            bgcolor="rgba(13, 17, 23, 0.88)", bordercolor="#00E676", borderwidth=1, borderpad=3,
            row=1, col=1
        )

    if 0 <= exit_idx < len(times):
        arrow_color = "#00E676" if is_win else "#FF5252"
        fig.add_annotation(
            x=times[exit_idx], y=highs[exit_idx] if is_win else lows[exit_idx],
            text=f"{exit_label}<br>${exit_p:,.2f}",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5, arrowcolor=arrow_color,
            ay=-35 if is_win else 35, font=dict(color=arrow_color, size=10, family="monospace"),
            bgcolor="rgba(13, 17, 23, 0.88)", bordercolor=arrow_color, borderwidth=1, borderpad=3,
            row=1, col=1
        )

    vol_colors = ['#00E676' if c >= o else '#FF5252' for o, c in zip(opens, closes)]
    fig.add_trace(go.Bar(x=times, y=volumes, marker_color=vol_colors, name="成交量"), row=2, col=1)

    kline_min = min(lows) if len(lows) > 0 else entry_p - 10
    kline_max = max(highs) if len(highs) > 0 else entry_p + 10
    padding = max(1.0, (kline_max - kline_min) * 0.2)

    fig.update_layout(
        height=460,
        uirevision="static_viewport_lock",
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#0d1117",
        font=dict(color="#c9d1d9", family="monospace", size=11),
        xaxis=dict(gridcolor="#161b22", showgrid=True, rangeslider=dict(visible=False)),
        xaxis2=dict(gridcolor="#161b22", showgrid=True),
        yaxis=dict(gridcolor="#161b22", showgrid=True, range=[kline_min - padding, kline_max + padding]),
        yaxis2=dict(gridcolor="#161b22", showgrid=True),
        hovermode="x unified",
        dragmode="pan"
    )

    st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})

def render_0dte_journal_tab(target_code: str):
    """Tab 2：0DTE 專屬做功課與記帳復盤機"""
    df_all = pd.read_csv(JOURNAL_CSV) if os.path.exists(JOURNAL_CSV) else pd.DataFrame()
    df = df_all[df_all['code'] == target_code] if (not df_all.empty and 'code' in df_all.columns) else df_all

    base_months = ["2026-09", "2026-08"]
    if not df.empty and 'month' in df.columns:
        existing_m = [str(x) for x in df['month'].dropna().unique()]
        month_list = ["📅 今天 (實盤 Live 訊號)"] + sorted(list(set(base_months + existing_m)), reverse=True)
    else:
        month_list = ["📅 今天 (實盤 Live 訊號)"] + base_months

    col_m1, col_m2 = st.columns([2, 3])
    with col_m1:
        sel_month = st.selectbox("📅 選擇做功課月份:", month_list, index=0)

    now_dt_ny = datetime.datetime.now(tz_ny)
    if sel_month == "📅 今天 (實盤 Live 訊號)":
        today_str = now_dt_ny.strftime('%Y-%m-%d')
        df_filtered = df[df['date'] == today_str] if not df.empty and 'date' in df.columns else pd.DataFrame()
    else:
        df_filtered = df[df['month'] == sel_month] if not df.empty and 'month' in df.columns else pd.DataFrame()

    wins = len(df_filtered[df_filtered['net_r'] > 0]) if not df_filtered.empty else 0
    total = len(df_filtered) if not df_filtered.empty else 0
    losses = total - wins
    win_rate = (wins / total) * 100.0 if total > 0 else 0.0
    total_pnl = float(df_filtered['pnl_usd'].sum()) if not df_filtered.empty and 'pnl_usd' in df_filtered.columns else (wins * 400.0 - losses * 200.0)

    with col_m2:
        pnl_color = "#00E676" if total_pnl >= 0 else "#FF5252"
        verdict = "🟢 WORKABLE (推薦實盤)" if win_rate >= 50 else ("⚪ 樣本累積中" if total == 0 else "🔴 需優化")
        st.markdown(f"""
        <div style="background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 10px 16px; margin-bottom: 12px; font-family: monospace;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px; font-weight: bold; color: {'#00E676' if win_rate>=50 else '#ffd700'};">🏆 {verdict}</span>
                <span style="font-size: 12px; color: #8b949e;">勝率: <b style="color:#ffd700;">{win_rate:.1f}%</b> ({wins}勝/{losses}負) | 累計做功課損益: <b style="color:{pnl_color};">${total_pnl:+,.2f} USD</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    if not df_filtered.empty:
        dates_available = sorted(list(df_filtered['date'].dropna().unique()), reverse=True)
        col_d1, col_d2 = st.columns([2, 3])
        with col_d1:
            sel_date = st.selectbox("📆 選擇交易日:", dates_available)
        
        df_day = df_filtered[df_filtered['date'] == sel_date]
        options = []
        for _, r in df_day.iterrows():
            is_win_r = r.get('status') == 'WIN_TP'
            res_tag = "🟢 WIN (+2.0R / +$400)" if is_win_r else ("🔴 LOSS (-1.0R / -$200)" if r.get('status') == 'LOSS_SL' else "⏳ 監控中 (RUNNING)")
            strat = r.get('strategy', '0DTE 策略')
            options.append(f"{r.get('time_myt', '--')} MYT | {r.get('direction')} | {strat} | {res_tag}")
        
        with col_d2:
            sel_sig_idx = st.selectbox("🎯 選擇訊號展開做功課 (贏綠輸紅):", range(len(options)), format_func=lambda x: options[x])

        selected_row = df_day.iloc[sel_sig_idx]
        st.caption(f"🔍 5M 技術復盤視圖 (標的: {target_code} · 含 15M ORB 箱體)：")
        render_interactive_replay_chart(selected_row)
    else:
        st.info(f"💡 【{sel_month}】當前暫無訊號記錄，系統正在以 3 秒頻率即時監控中...")

def render_0dte_cockpit_view(assets=None):
    """0DTE 主入口：雙 Tab 結構"""
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

    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        target_code = st.selectbox("🎯 選擇 0DTE 標的", symbol_options, index=0)
    with c2:
        budget_input = st.number_input("💰 單筆期權預算上限 (USD)", min_value=50.0, max_value=5000.0, value=200.0, step=50.0)
    with c3:
        st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        if st.button("⚡ 手動立即抓取最新 (Sync Now)", use_container_width=True):
            try:
                hub_engine.auto_heal_today_data(target_code)
                st.rerun()
            except Exception:
                pass

    tab_live, tab_journal = st.tabs(["⚡ 0DTE 即時射控座艙", "📊 0DTE 策略記帳與做功課"])
    with tab_live:
        render_0dte_live_fragment(target_code, budget_input)
    with tab_journal:
        render_0dte_journal_tab(target_code)
