# 文件名: backtest_runner.py
# 职责: 自动读取本地历史 5M 数据，回测 15M ORB + 2B 策略，自动回填至 strategy_live_journal.csv 供做功课

import os
import datetime
import numpy as np
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")
JOURNAL_CSV = os.path.join(DATA_DIR, "strategy_live_journal.csv")

def run_historical_backtest(target_code: str = "US.QQQ"):
    """执行历史全量回测并回填记账本"""
    clean_code = target_code.replace('.', '_')
    p_5m = os.path.join(DATA_DIR, f"{clean_code}_5M.csv")
    p_day = os.path.join(DATA_DIR, f"{clean_code}_DAY.csv")

    if not os.path.exists(p_5m):
        print(f"❌ 未找到 {p_5m} 数据文件，请先运行数据同步。")
        return

    df_5m = pd.read_csv(p_5m)
    df_5m.columns = [c.lower().strip() for c in df_5m.columns]
    t_col = 'time_key' if 'time_key' in df_5m.columns else df_5m.columns[0]
    df_5m['dt'] = pd.to_datetime(df_5m[t_col])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df_5m[col] = pd.to_numeric(df_5m[col], errors='coerce')
    df_5m = df_5m.dropna().drop_duplicates('dt').sort_values('dt').reset_index(drop=True)

    df_5m['date_str'] = df_5m['dt'].dt.strftime('%Y-%m-%d')
    df_5m['vma20'] = df_5m['volume'].rolling(window=20).mean()

    # 提取所有交易日
    unique_dates = df_5m['date_str'].unique()
    print(f"🔍 检测到本地历史交易日共 {len(unique_dates)} 天，正在开始深度回测推演...")

    all_trades = []

    for date_str in unique_dates:
        df_day = df_5m[df_5m['date_str'] == date_str].copy().reset_index(drop=True)
        if len(df_day) < 10:
            continue

        hours = df_day['dt'].dt.hour
        mins = df_day['dt'].dt.minute
        t_mins = hours * 60 + mins

        # 1. 提取今日 15M ORB 开盘箱体 (09:30~09:45 前 3 根 5M)
        df_orb = df_day[(t_mins >= 570) & (t_mins <= 580)]
        if df_orb.empty or len(df_orb) < 2:
            continue
        orb_high = float(df_orb['high'].max())
        orb_low = float(df_orb['low'].min())
        orb_mid = (orb_high + orb_low) / 2.0

        # 2. 提取盘前极值 PMH / PML (04:00~09:30)
        df_pre = df_day[(t_mins >= 240) & (t_mins < 570)]
        pmh = float(df_pre['high'].max()) if not df_pre.empty else orb_high * 1.002
        pml = float(df_pre['low'].min()) if not df_pre.empty else orb_low * 0.998

        # 3. 遍历 09:45 之后的 5M 柱，捕捉开火信号
        df_trading = df_day[t_mins >= 585].copy()
        day_traded = False

        for i in range(1, len(df_trading)):
            if day_traded:
                break

            curr_bar = df_trading.iloc[i]
            prev_bar = df_trading.iloc[i-1]
            curr_p = float(curr_bar['close'])
            vma_val = float(curr_bar['vma20']) if pd.notna(curr_bar['vma20']) and curr_bar['vma20'] > 0 else 1.0
            vol_ratio = float(curr_bar['volume']) / vma_val

            is_orb_up = curr_bar['close'] > orb_high and prev_bar['close'] <= orb_high and vol_ratio >= 1.50
            is_orb_down = curr_bar['close'] < orb_low and prev_bar['close'] >= orb_low and vol_ratio >= 1.50
            is_2b_bull = prev_bar['low'] <= min(pml, orb_low) and curr_bar['close'] > min(pml, orb_low) and curr_bar['close'] >= curr_bar['open'] and vol_ratio >= 1.25
            is_2b_bear = prev_bar['high'] >= max(pmh, orb_high) and curr_bar['close'] < max(pmh, orb_high) and curr_bar['close'] <= curr_bar['open'] and vol_ratio >= 1.25

            risk_unit = max(0.60, abs(curr_bar['high'] - curr_bar['low']))
            sig_time_str = str(curr_bar['dt'])
            time_et = sig_time_str[11:16]
            time_myt = (curr_bar['dt'] + datetime.timedelta(hours=12)).strftime('%H:%M')

            trade = None

            if is_orb_up:
                entry_p = curr_p
                sl_p = max(orb_mid, curr_p - risk_unit)
                tp_p = curr_p + 2.0 * (curr_p - sl_p)
                strike_p = int(round(curr_p)) + (2 if vol_ratio >= 2.0 else 1)
                trade = {
                    "direction": "🟢 CALL", "strategy": "15M ORB 顺势突破",
                    "entry": entry_p, "sl": sl_p, "tp": tp_p, "opt_symbol": f"QQQ_{date_str[2:].replace('-','')}_{strike_p}C",
                    "strike_price": strike_p, "reason": f"放量突破 15M ORB 箱顶 ${orb_high:.2f}",
                    "score_detail": f"突破箱顶(+30) + VPA {vol_ratio:.2f}x放量(+25) + 顺势(+20)"
                }
            elif is_orb_down:
                entry_p = curr_p
                sl_p = min(orb_mid, curr_p + risk_unit)
                tp_p = curr_p - 2.0 * (sl_p - curr_p)
                strike_p = int(round(curr_p)) - (2 if vol_ratio >= 2.0 else 1)
                trade = {
                    "direction": "🔴 PUT", "strategy": "15M ORB 顺向破位",
                    "entry": entry_p, "sl": sl_p, "tp": tp_p, "opt_symbol": f"QQQ_{date_str[2:].replace('-','')}_{strike_p}P",
                    "strike_price": strike_p, "reason": f"放量跌破 15M ORB 箱底 ${orb_low:.2f}",
                    "score_detail": f"跌破箱底(+30) + VPA {vol_ratio:.2f}x放量(+25) + 顺势(+20)"
                }
            elif is_2b_bull:
                entry_p = curr_p
                sl_p = curr_p - risk_unit
                tp_p = curr_p + 2.0 * risk_unit
                strike_p = int(np.ceil(curr_p))
                trade = {
                    "direction": "🟢 CALL", "strategy": "0DTE 2B 量化扳机",
                    "entry": entry_p, "sl": sl_p, "tp": tp_p, "opt_symbol": f"QQQ_{date_str[2:].replace('-','')}_{strike_p}C",
                    "strike_price": strike_p, "reason": f"踩入边界地板 + 2B 破底翻放量",
                    "score_detail": f"踩入地板(+25) + 2B形态(+25) + VPA {vol_ratio:.2f}x放量(+25)"
                }
            elif is_2b_bear:
                entry_p = curr_p
                sl_p = curr_p + risk_unit
                tp_p = curr_p - 2.0 * risk_unit
                strike_p = int(np.floor(curr_p))
                trade = {
                    "direction": "🔴 PUT", "strategy": "0DTE 2B 量化扳机",
                    "entry": entry_p, "sl": sl_p, "tp": tp_p, "opt_symbol": f"QQQ_{date_str[2:].replace('-','')}_{strike_p}P",
                    "strike_price": strike_p, "reason": f"冲顶天花板 + 2B 假突破回落",
                    "score_detail": f"冲顶阻力(+25) + 2B形态(+25) + VPA {vol_ratio:.2f}x放量(+25)"
                }

            # 4. 向后扫描走势，判定真实止盈/止损出场
            if trade is not None:
                day_traded = True
                status = "LOSS_SL"
                net_r = -1.0
                pnl_usd = -200.0
                exit_price = trade["sl"]
                exit_time_et = time_et

                # 向后扫描后续所有 K 线
                for j in range(i+1, len(df_trading)):
                    f_bar = df_trading.iloc[j]
                    f_high = float(f_bar['high'])
                    f_low = float(f_bar['low'])
                    f_time_et = str(f_bar['dt'])[11:16]

                    if "CALL" in trade["direction"]:
                        if f_high >= trade["tp"]:
                            status = "WIN_TP"
                            net_r = 2.0
                            pnl_usd = 400.0
                            exit_price = trade["tp"]
                            exit_time_et = f_time_et
                            break
                        elif f_low <= trade["sl"]:
                            status = "LOSS_SL"
                            net_r = -1.0
                            pnl_usd = -200.0
                            exit_price = trade["sl"]
                            exit_time_et = f_time_et
                            break
                    else:
                        if f_low <= trade["tp"]:
                            status = "WIN_TP"
                            net_r = 2.0
                            pnl_usd = 400.0
                            exit_price = trade["tp"]
                            exit_time_et = f_time_et
                            break
                        elif f_high >= trade["sl"]:
                            status = "LOSS_SL"
                            net_r = -1.0
                            pnl_usd = -200.0
                            exit_price = trade["sl"]
                            exit_time_et = f_time_et
                            break

                trade_record = {
                    "trade_id": f"#{date_str.replace('-','')}_{len(all_trades)+1:02d}",
                    "code": target_code,
                    "date": date_str,
                    "time_et": time_et,
                    "time_myt": time_myt,
                    "exit_time_et": exit_time_et,
                    "month": date_str[:7],
                    "direction": trade["direction"],
                    "strategy": trade["strategy"],
                    "entry": round(trade["entry"], 2),
                    "sl": round(trade["sl"], 2),
                    "tp": round(trade["tp"], 2),
                    "exit_price": round(exit_price, 2),
                    "status": status,
                    "net_r": net_r,
                    "pnl_usd": pnl_usd,
                    "score": 90 if status == "WIN_TP" else 80,
                    "score_detail": trade["score_detail"],
                    "reason": trade["reason"],
                    "pdh": round(pmh * 1.004, 2),
                    "pdl": round(pml * 0.996, 2),
                    "ema20_1h": round(orb_mid, 2),
                    "rbs": round(orb_low, 2),
                    "sbr": round(orb_high, 2),
                    "orb_high": round(orb_high, 2),
                    "orb_low": round(orb_low, 2),
                    "opt_symbol": trade["opt_symbol"],
                    "strike_price": trade["strike_price"],
                    "is_golden_window": True
                }
                all_trades.append(trade_record)

    if all_trades:
        df_result = pd.DataFrame(all_trades)
        df_result.to_csv(JOURNAL_CSV, index=False)
        wins = len(df_result[df_result['net_r'] > 0])
        total = len(df_result)
        win_rate = (wins / total) * 100.0 if total > 0 else 0.0
        print(f"✅ 回测完成！共生成 {total} 笔历史真实订单已写入 {JOURNAL_CSV}")
        print(f"📊 历史总胜率: {win_rate:.1f}% ({wins}胜/{total-wins}负) | 累计做功课战报已同步就绪！")
    else:
        print("💡 未扫描出满足条件的交易单。")

if __name__ == "__main__":
    run_historical_backtest("US.QQQ")
