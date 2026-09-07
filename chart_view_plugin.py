# 文件名: chart_view_plugin.py
# 职责: 独立图表视图插件 (纯前端渲染，多周期切换，暗黑金融风格，K线 + 成交量)

import os
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "market_data")

class ChartViewPlugin:
    @staticmethod
    def render_chart(code: str, ktype: str = "5M", bar_count: int = 60):
        clean_name = code.replace(".", "_")
        csv_path = os.path.join(DATA_DIR, f"{clean_name}_{ktype}.csv")

        if not os.path.exists(csv_path):
            st.warning(f"未检测到本地数据文件: {csv_path}，请先点击侧边栏同步数据。")
            return

        try:
            df = pd.read_csv(csv_path)
            if df.empty:
                st.warning("数据文件为空。")
                return

            df.columns = [c.lower() for c in df.columns]
            df = df.tail(bar_count).reset_index(drop=True)

            # 创建带成交量副图的 2 层画布
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.75, 0.25]
            )

            # 主图：K线蜡烛 (绿涨红跌)
            fig.add_trace(
                go.Candlestick(
                    x=df['time_key'],
                    open=df['open'],
                    high=df['high'],
                    low=df['low'],
                    close=df['close'],
                    name="K线",
                    increasing_line_color='#00E676',
                    decreasing_line_color='#FF5252',
                    increasing_fillcolor='#00E676',
                    decreasing_fillcolor='#FF5252'
                ),
                row=1, col=1
            )

            # 副图：成交量柱状图
            colors = ['#00E676' if df['close'].iloc[i] >= df['open'].iloc[i] else '#FF5252' for i in range(len(df))]
            fig.add_trace(
                go.Bar(
                    x=df['time_key'],
                    y=df['volume'],
                    marker_color=colors,
                    name="成交量"
                ),
                row=2, col=1
            )

            fig.update_layout(
                height=520,
                margin=dict(l=10, r=10, t=20, b=10),
                paper_bgcolor='#0d1117',
                plot_bgcolor='#0d1117',
                xaxis_rangeslider_visible=False,
                showlegend=False,
                xaxis=dict(showgrid=True, gridcolor='#21262d', type='category'),
                yaxis=dict(showgrid=True, gridcolor='#21262d', side='right'),
                xaxis2=dict(showgrid=True, gridcolor='#21262d', type='category'),
                yaxis2=dict(showgrid=True, gridcolor='#21262d', side='right')
            )

            st.plotly_chart(fig, use_container_width=True)

        except Exception as e:
            st.error(f"图表渲染异常: {str(e)}")

chart_plugin = ChartViewPlugin()
