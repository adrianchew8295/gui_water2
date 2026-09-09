# 文件名: journal_plugin.py
# 職責: 策略復盤與實盤訂單帳本 (Journal & Trade Audit Log · 支援 2B 突破 / 0DTE 復盤與勝率期望值審計)

import os
import sys
import datetime
import json
import numpy as np
import pandas as pd
import pytz
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

tz_ny = pytz.timezone("America/New_York")
tz_my = pytz.timezone("Asia/Kuala_Lumpur")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "market_data")
os.makedirs(DATA_DIR, exist_ok=True)

JOURNAL_CSV = os.path.join(DATA_DIR, "strategy_live_journal.csv")
HEALTH_LOG_FILE = os.path.join(DATA_DIR, "system_health.log")

class JournalEngine:
    def __init__(self, journal_path: str = JOURNAL_CSV):
        self.journal_path = journal_path
        self._init_journal_file()

    def _init_journal_file(self):
        """初始化帳本檔案 (若無則自動生成標準樣本數據)"""
        needs_init = False
        if not os.path.exists(self.journal_path):
            needs_init = True
        else:
            try:
                df_chk = pd.read_csv(self.journal_path)
                if df_chk.empty or 'code' not in df_chk.columns:
                    needs_init = True
            except Exception:
                needs_init = True

        if needs_init:
            sample_data = [
                {
                    "trade_id": "#20260908_01", "code": "US.QQQ", "date": "2026-09-08", "time_et": "10:15", "time_myt": "22:15", "exit_time_et": "10:45",
                    "month": "2026-09", "direction": "🟢 CALL", "strategy": "Strategy 1 (2B 破底翻)", "entry": 718.50, "sl": 717.30, "tp": 720.90,
                    "exit_price": 720.90, "status": "WIN_TP", "net_r": 2.0, "pnl_usd": 400.0, "score": 95,
                    "score_detail": "順應1H均線(+25) + 踩入RBS支撐(+25) + 2B破底翻(+25) + VPA 1.85x巨量(+20)",
                    "reason": "回踩 RBS 支撐帶 + 5M 2B 破底翻長下影線 + 1.85x 巨量共振", "pdh": 721.39, "pdl": 715.72,
                    "ema20_1h": 715.80, "rbs": 716.20, "sbr": 719.50, "is_golden_window": True
                },
                {
                    "trade_id": "#20260905_01", "code": "US.NVDA", "date": "2026-09-05", "time_et": "09:45", "time_myt": "21:45", "exit_time_et": "10:05",
                    "month": "2026-09", "direction": "🟢 CALL", "strategy": "Strategy 1 (2B 破底翻)", "entry": 224.50, "sl": 223.20, "tp": 227.10,
                    "exit_price": 227.10, "status": "WIN_TP", "net_r": 2.0, "pnl_usd": 400.0, "score": 90,
                    "score_detail": "日線通道下軌承接(+25) + 5M 破底翻(+25) + 1H EMA20 支撐(+25) + 量能放大(+15)",
                    "reason": "日線墨菲通道下軌回踩確認 + 5M 扎針反包", "pdh": 228.00, "pdl": 222.10,
                    "ema20_1h": 223.80, "rbs": 223.50, "sbr": 227.00, "is_golden_window": True
                },
                {
                    "trade_id": "#20260903_01", "code": "US.QQQ", "date": "2026-09-03", "time_et": "14:20", "time_myt": "02:20", "exit_time_et": "14:35",
                    "month": "2026-09", "direction": "🔴 PUT", "strategy": "Strategy 2 (假突破假摔)", "entry": 724.80, "sl": 725.90, "tp": 722.60,
                    "exit_price": 725.90, "status": "LOSS_SL", "net_r": -1.0, "pnl_usd": -200.0, "score": 75,
                    "score_detail": "碰觸SBR阻力(+25) + 2B頂背離(+25) + 尾盤流動性不足(-25)",
                    "reason": "摸頂 SBR 阻力帶做空，尾盤多頭強拉突破觸發紀律止損", "pdh": 726.00, "pdl": 721.50,
                    "ema20_1h": 722.10, "rbs": 721.80, "sbr": 725.00, "is_golden_window": False
                }
            ]
            pd.DataFrame(sample_data).to_csv(self.journal_path, index=False)

    def load_journal(self) -> pd.DataFrame:
        if os.path.exists(self.journal_path):
            try:
                df = pd.read_csv(self.journal_path)
                if not df.empty and 'net_r' in df.columns:
                    return df
            except Exception:
                pass
        return pd.DataFrame()

    def evaluate_metrics(self, df: pd.DataFrame) -> dict:
        default_res = {
            "total": 0, "win_rate": 0.0, "rr": 0.0, "exp": 0.0,
            "verdict": "⚪ 樣本累積中", "color": "#8b949e", "wins": 0, "losses": 0,
            "total_pnl": 0.0
        }
        if df.empty or 'net_r' not in df.columns:
            return default_res
        
        wins = len(df[df['net_r'] > 0])
        total = len(df)
        losses = total - wins
        win_rate = (wins / total) * 100.0 if total > 0 else 0.0
        avg_w = df[df['net_r'] > 0]['net_r'].mean() if wins > 0 else 2.0
        avg_l = abs(df[df['net_r'] <= 0]['net_r'].mean()) if losses > 0 else 1.0
        rr = avg_w / avg_l if avg_l > 0 else 2.0
        p_w, p_l = win_rate / 100.0, (100.0 - win_rate) / 100.0
        exp = (p_w * avg_w) - (p_l * avg_l)
        total_pnl = float(df['pnl_usd'].sum()) if 'pnl_usd' in df.columns else (wins * 400.0 - losses * 200.0)

        if exp >= 0.35 and win_rate >= 50.0:
            verdict, color = "🟢 WORKABLE (推薦實盤)", "#00E676"
        elif exp > 0.0:
            verdict, color = "🟡 NEUTRAL (觀察微調)", "#ffd700"
        else:
            verdict, color = "🔴 NON-WORKABLE (淘汰/需優化)", "#FF5252"

        return {
            "total": total, "win_rate": win_rate, "rr": rr, "exp": exp,
            "verdict": verdict, "color": color, "wins": wins, "losses": losses,
            "total_pnl": total_pnl
        }

    def _load_kline_slice(self, code: str, entry_date_str: str = None, entry_time_str: str = None):
        """加載訂單對應的 5M K 線切片"""
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
                    time_col = 'time_key' if 'time_key' in df_raw.columns else ('time_clean' if 'time_clean' in df_raw.columns else df_raw.columns[0])
                    
                    if entry_date_str and entry_time_str:
                        matches = df_raw[df_raw[time_col].astype(str).str.contains(entry_date_str, na=False)].index.tolist()
                        if matches:
                            mid = matches[len(matches)//2]
                            for idx in matches:
                                if entry_time_str in str(df_raw.iloc[idx][time_col]):
                                    mid = idx
                                    break
                            start_i = max(0, mid - 18)
                            end_i = min(len(df_raw), mid + 22)
                            sl = df_raw.iloc[start_i:end_i].copy().reset_index(drop=True)
                            times = [str(t)[-8:-3] for t in sl[time_col]]
                            return times, sl['open'].astype(float).tolist(), sl['high'].astype(float).tolist(), sl['low'].astype(float).tolist(), sl['close'].astype(float).tolist(), sl['volume'].astype(float).tolist(), (mid - start_i)
                    
                    sl = df_raw.tail(40).copy().reset_index(drop=True)
                    times = [str(t)[-8:-3] for t in sl[time_col]]
                    return times, sl['open'].astype(float).tolist(), sl['high'].astype(float).tolist(), sl['low'].astype(float).tolist(), sl['close'].astype(float).tolist(), sl['volume'].astype(float).tolist(), -1
                except Exception:
                    pass
        
        # 兜底生成連續數列
        base_p = 718.50 if "QQQ" in code else 225.00
        times = [f"{i:02d}:00" for i in range(10, 50)]
        return times, [base_p]*40, [base_p+2]*40, [base_p-2]*40, [base_p]*40, [100.0]*40, -1

    def render_interactive_chart(self, code: str, trade_row: pd.Series = None):
        """使用 Plotly 渲染復盤與實盤打點圖表"""
        if trade_row is not None:
            entry_p = float(trade_row.get('entry', 0.0))
            sl_p = float(trade_row.get('sl', 0.0))
            tp_p = float(trade_row.get('tp', 0.0))
            pdh_p = float(trade_row.get('pdh', entry_p * 1.002))
            pdl_p = float(trade_row.get('pdl', entry_p * 0.998))
            rbs_p = float(trade_row.get('rbs', entry_p * 0.999))
            sbr_p = float(trade_row.get('sbr', entry_p * 1.001))
            is_call = "CALL" in str(trade_row.get('direction', 'CALL'))
            is_win = trade_row.get('status') == 'WIN_TP'
            date_str = str(trade_row.get('date', '2026-09-08'))
            time_str = str(trade_row.get('time_et', '10:15'))
            times, opens, highs, lows, closes, volumes, entry_idx = self._load_kline_slice(code, date_str, time_str)
            exit_idx = min(len(times) - 1, entry_idx + 6) if entry_idx >= 0 else -1
            exit_p = float(trade_row.get('exit_price', entry_p))
            exit_label = "🎯 命中 2R 止盈 (+2.0R)" if is_win else "🛡️ 觸發止損出場 (-1.0R)"
        else:
            times, opens, highs, lows, closes, volumes, entry_idx = self._load_kline_slice(code)
            entry_p = closes[-1] if len(closes) > 0 else 718.50
            sl_p, tp_p = entry_p * 0.998, entry_p * 1.004
            pdh_p, pdl_p = max(highs), min(lows)
            rbs_p, sbr_p = min(lows) * 1.001, max(highs) * 0.999
            exit_idx = -1

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_heights=[0.72, 0.28])

        # 主 K 線
        fig.add_trace(go.Candlestick(
            x=times, open=opens, high=highs, low=lows, close=closes,
            increasing_line_color='#00E676', decreasing_line_color='#FF5252',
            increasing_fillcolor='#00E676', decreasing_fillcolor='#FF5252',
            name="5M K線"
        ), row=1, col=1)

        fig.add_hline(y=pdh_p, line_dash="dot", line_color="#ffd700", line_width=1.2, annotation_text=f"PDH: ${pdh_p:,.2f}", annotation_position="top left", row=1, col=1)
        fig.add_hline(y=pdl_p, line_dash="dot", line_color="#ffd700", line_width=1.2, annotation_text=f"PDL: ${pdl_p:,.2f}", annotation_position="bottom left", row=1, col=1)

        step_val = 0.4 if entry_p < 1000 else 15.0
        fig.add_hrect(y0=rbs_p - step_val * 0.3, y1=rbs_p + step_val * 0.3, line_width=0, fillcolor="#00E676", opacity=0.12, annotation_text="RBS 支撐", annotation_position="bottom left", row=1, col=1)
        fig.add_hrect(y0=sbr_p - step_val * 0.3, y1=sbr_p + step_val * 0.3, line_width=0, fillcolor="#FF5252", opacity=0.12, annotation_text="SBR 阻力", annotation_position="top left", row=1, col=1)

        # 標註進出場
        if trade_row is not None and 0 <= entry_idx < len(times):
            fig.add_hline(y=entry_p, line_dash="dash", line_color="#58a6ff", annotation_text=f"進場: ${entry_p:,.2f}", annotation_position="top right", row=1, col=1)
            fig.add_hline(y=sl_p, line_dash="dash", line_color="#FF5252", annotation_text=f"止損: ${sl_p:,.2f}", annotation_position="bottom right", row=1, col=1)
            fig.add_hline(y=tp_p, line_dash="dash", line_color="#00E676", annotation_text=f"2R止盈: ${tp_p:,.2f}", annotation_position="top right", row=1, col=1)

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

        # 成交量
        vol_colors = ['#00E676' if c >= o else '#FF5252' for o, c in zip(opens, closes)]
        fig.add_trace(go.Bar(x=times, y=volumes, marker_color=vol_colors, name="成交量"), row=2, col=1)

        kline_min = min(lows) if len(lows) > 0 else entry_p - 10
        kline_max = max(highs) if len(highs) > 0 else entry_p + 10
        padding = max(step_val * 2.5, (kline_max - kline_min) * 0.2)

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

journal_engine_instance = JournalEngine()

def render_journal_view(assets=None):
    """主入口：渲染策略復盤與實盤訂單帳本"""
    st.markdown("""
    <style>
    .metric-banner { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 10px 16px; margin-bottom: 12px; font-family: monospace; }
    .win-tag { color: #00E676; font-weight: bold; background: rgba(0, 230, 118, 0.12); padding: 2px 6px; border-radius: 4px; }
    .loss-tag { color: #FF5252; font-weight: bold; background: rgba(255, 82, 82, 0.12); padding: 2px 6px; border-radius: 4px; }
    </style>
    """, unsafe_allow_html=True)

    default_symbols = ["US.QQQ", "US.NVDA", "US.AAPL", "US.MSFT", "US.AMZN", "US.TSLA"]
    symbol_options = []
    if isinstance(assets, list) and len(assets) > 0:
        for a in assets:
            if isinstance(a, dict) and 'code' in a:
                symbol_options.append(a['code'])
            elif isinstance(a, str):
                symbol_options.append(a)
    elif isinstance(assets, pd.DataFrame) and not assets.empty and 'code' in assets.columns:
        symbol_options = assets['code'].tolist()
    if not symbol_options:
        symbol_options = default_symbols

    c_sel, c_stat = st.columns([2, 3])
    with c_sel:
        target_code = st.selectbox("🎯 選擇復盤標的", symbol_options, index=0)

    df_all = journal_engine_instance.load_journal()
    df = df_all[df_all['code'] == target_code] if (not df_all.empty and 'code' in df_all.columns) else df_all

    base_months = ["2026-09", "2026-08", "2026-07"]
    if not df.empty and 'month' in df.columns:
        existing_m = [str(x) for x in df['month'].dropna().unique()]
        month_list = ["📅 今天 (實盤 Live)"] + sorted(list(set(base_months + existing_m)), reverse=True)
    else:
        month_list = ["📅 今天 (實盤 Live)"] + base_months

    col_m1, col_m2 = st.columns([2, 3])
    with col_m1:
        sel_month = st.selectbox("📅 選擇復盤月份:", month_list, index=0)

    now_dt_ny = datetime.datetime.now(tz_ny)
    if sel_month == "📅 今天 (實盤 Live)":
        today_str = now_dt_ny.strftime('%Y-%m-%d')
        df_filtered = df[df['date'] == today_str] if not df.empty and 'date' in df.columns else pd.DataFrame()
    else:
        df_filtered = df[df['month'] == sel_month] if not df.empty and 'month' in df.columns else pd.DataFrame()

    m = journal_engine_instance.evaluate_metrics(df_filtered)

    with col_m2:
        pnl_color = "#00E676" if m['total_pnl'] >= 0 else "#FF5252"
        st.markdown(f"""
        <div class="metric-banner">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 13px; font-weight: bold; color: {m['color']};">🏆 {m['verdict']}</span>
                <span style="font-size: 12px; color: #8b949e;">勝率: <b style="color:#ffd700;">{m['win_rate']:.1f}%</b> ({m['wins']}勝/{m['losses']}負) | 盈虧比: <b style="color:#ffd700;">1:{m['rr']:.2f}</b> | 累計: <b style="color:{pnl_color};">${m['total_pnl']:+,.2f} USD</b></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    selected_row = None
    if sel_month != "📅 今天 (實盤 Live)" and not df_filtered.empty:
        dates_available = sorted(list(df_filtered['date'].dropna().unique()), reverse=True)
        col_d1, col_d2 = st.columns([2, 3])
        with col_d1:
            sel_date = st.selectbox("📆 選擇交易日:", dates_available)
        
        df_day = df_filtered[df_filtered['date'] == sel_date]
        options = []
        for _, r in df_day.iterrows():
            is_win_r = r.get('status') == 'WIN_TP'
            res_tag = f"🟢 WIN (+2.0R / +$400)" if is_win_r else f"🔴 LOSS (-1.0R / -$200)"
            win_star = "⭐ [黃金時段]" if r.get('is_golden_window', False) else "⚪ [常規]"
            options.append(f"{win_star} {r.get('time_myt', '--')} MYT | {r.get('direction')} | {res_tag} | 評分: {r.get('score', 0)}分")
        
        with col_d2:
            sel_sig_idx = st.selectbox("🎯 選擇訂單做功課 (贏綠輸紅):", range(len(options)), format_func=lambda x: options[x])

        selected_row = df_day.iloc[sel_sig_idx]

    st.caption(f"🔍 5M 即時/復盤技術視圖 (標的: {target_code} · 支援滾輪縮放與無限拖拽)：")
    journal_engine_instance.render_interactive_chart(target_code, selected_row)

    if selected_row is not None:
        is_win_sel = selected_row.get('status') == 'WIN_TP'
        badge_html = '<span class="win-tag">🟢 WIN 止盈 (+2.0R / +$400 USD)</span>' if is_win_sel else '<span class="loss-tag">🔴 LOSS 止損 (-1.0R / -$200 USD)</span>'
        score_num = selected_row.get('score', 0)
        score_color = "#00E676" if score_num >= 80 else "#ffd700"

        st.markdown(f"""
        <div style="background: #161b22; border-left: 4px solid {'#00E676' if is_win_sel else '#FF5252'}; padding: 10px 14px; border-radius: 4px; font-size: 13px; font-family: monospace; color: #c9d1d9; margin-bottom: 10px;">
            <div style="margin-bottom: 6px;">{badge_html} | 訂單編號: <b>{selected_row.get('trade_id')}</b> | 客觀評分: <b style="color:{score_color};">{score_num} 分</b> (門檻 ≥75分)</div>
            <div style="color: #8b949e; margin-bottom: 4px;">• <b>4維評分拆解</b>: {selected_row.get('score_detail', '客觀4維加總')}</div>
            <div>• <b>實戰攻防</b>: 入場價 <b>${float(selected_row.get('entry', 0)):,.2f}</b> | 止損價 <b>${float(selected_row.get('sl', 0)):,.2f}</b> | 2R目標 <b>${float(selected_row.get('tp', 0)):,.2f}</b> | 出場價 <b>${float(selected_row.get('exit_price', 0)):,.2f}</b></div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.info(f"💡 【{sel_month}】當前監控中，最新 5M 走勢已呈現在上方圖表中。")

    # 策略審核日誌 (一鍵複製)
    if selected_row is not None:
        is_win = selected_row.get('status') == 'WIN_TP'
        res_text = "🟢 WIN 止盈成功 (+2.0R / 獲利 +$400.00 USD)" if is_win else "🔴 LOSS 觸發止損 (-1.0R / 虧損 -$200.00 USD)"
        audit_log = f"""=== 癸水 · 策略復盤與審核日誌 (TRADE AUDIT LOG) ===
[1. 訂單時序] 日期: {selected_row.get('date', '--')} | 入場: {selected_row.get('time_myt', '--')} MYT ({selected_row.get('time_et', '--')} ET) ➔ 出場: {selected_row.get('exit_time_et', '--')} ET
[2. 交易決策] 標的: {target_code} | 方向: {selected_row.get('direction', '--')} | 開倉成本: ${float(selected_row.get('entry', 0)):,.2f}
[3. 進場依據]
  • 形態與戰區: {selected_row.get('reason', '--')}
  • 客觀評分: {selected_row.get('score', 0)} 分
  • 打分拆解: {selected_row.get('score_detail', '--')}
[4. 最終結果] {res_text}
  • 止損防守: ${float(selected_row.get('sl', 0)):,.2f} | 止盈目標: ${float(selected_row.get('tp', 0)):,.2f} | 實際出場: ${float(selected_row.get('exit_price', 0)):,.2f}
=================================================="""
    else:
        audit_log = f"""=== 癸水 · 策略復盤日誌 (TRADE AUDIT LOG) ===
• 標的: {target_code} | 當前狀態: 實盤監控中 (尚未產生平倉訂單)
• 5M 即時走勢已對齊本地數據庫。
============================================"""

    with st.expander("📋 [策略專用] 訂單審核日誌 (Trade Audit Log · 供 AI 診斷)", expanded=False):
        st.caption("點擊右上角按鈕一鍵複製完整訂單審核日誌，貼入 AI 進行策略勝率歸因：")
        st.code(audit_log, language="text")

# 兼容類別導出
JournalPlugin = JournalEngine
