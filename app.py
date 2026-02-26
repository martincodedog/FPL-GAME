import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化
st.set_page_config(page_title="FPL 數據分析終端", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    [data-testid="stMetricValue"] { font-size: 26px !important; font-weight: 700; color: #2c3e50; }
    .stDataFrame { border-radius: 12px; overflow: hidden; }
    h1, h2, h3 { color: #1a1a1a; font-family: 'Helvetica Neue', sans-serif; }
    </style>
    """, unsafe_allow_html=True)

LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

@st.cache_data(ttl=3600)
def fetch_fpl_pro_data(league_id):
    headers = {"User-Agent": "Mozilla/5.0"}
    l_url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    r = requests.get(l_url, headers=headers).json()
    members = [p for p in r['standings']['results'] if p['player_name'] != IGNORE_PLAYER]
    
    all_history = []
    for m in members:
        h_url = f"https://fantasy.premierleague.com/api/entry/{m['entry']}/history/"
        h_data = requests.get(h_url, headers=headers).json()['current']
        for gw in h_data:
            all_history.append({
                "GW": gw['event'],
                "經理人": m['player_name'],
                "總分": gw['total_points'],
                "當週分": gw['points']
            })
    return pd.DataFrame(all_history)

try:
    df = fetch_fpl_pro_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    remaining = 38 - max_gw

    # --- 1. 核心輸贏計算 (Net Score * 2) ---
    def calc_net_score(group):
        n = len(group)
        total = group['總分'].sum()
        group['輸贏積分'] = (group['總分'] * (n - 1) - (total - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_net_score)

    # --- 2. 深度統計學預測與分析 (EV / Beta / Sharpe) ---
    league_avg_per_gw = df.groupby('GW')['當週分'].mean()
    pro_stats = []
    
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        m_weekly = m_df['當週分']
        
        # 1. 穩定度 (標準差)
        std_dev = m_weekly.std()
        
        # 2. 期望值 (WMA 近 5 週加權)
        recent = m_weekly.tail(5)
        wma_avg = np.average(recent, weights=np.arange(1, len(recent) + 1))
        ev_gw38 = m_df['總分'].iloc[-1] + (wma_avg * remaining)
        
        # 3. 預測區間 (95% CI)
        margin = 1.96 * std_dev * np.sqrt(remaining) if remaining > 0 else 0
        
        # 4. 貝塔係數 Beta (相關性)
        covariance = np.cov(m_weekly, league_avg_per_gw[:len(m_weekly)])[0][1]
        variance = np.var(league_avg_per_gw[:len(m_weekly)])
        beta = covariance / variance if variance != 0 else 1
        
        # 5. 夏普得分比 (回報/風險)
        sharpe = (m_weekly.mean() - 40) / (std_dev if std_dev > 0 else 1) # 假設 40 分為無風險基準
        
        # 6. 最大回撤 (Max Drawdown)
        gl_history = m_df['輸贏積分']
        drawdown = (gl_history - gl_history.cummax()).min()
        
        pro_stats.append({
            "經理人": manager,
            "目前總分": int(m_df['總分'].iloc[-1]),
            "目前輸贏": int(m_df['輸贏積分'].iloc[-1]),
            "GW38 EV": int(ev_final := ev_gw38),
            "預測上限": int(ev_final + margin),
            "預測下限": int(ev_final - margin),
            "穩定度(σ)": int(std_dev),
            "貝塔係數(β)": round(beta, 2),
            "夏普比率": round(sharpe, 2),
            "最大回撤": int(drawdown)
        })

    stat_df = pd.DataFrame(pro_stats)
    
    # 預測輸贏重新平衡
    total_ev = stat_df['GW38 EV'].sum()
    n_p = len(stat_df)
    stat_df['預測GW38輸贏'] = (stat_df['GW38 EV'] * (n_p - 1) - (total_ev - stat_df['GW38 EV'])) * 2
    stat_df['預測GW38輸贏'] = stat_df['預測GW38輸贏'].astype(int)

    # --- UI 呈現 ---
    st.title("🏛️ FPL 專業統計數據總站")
    
    # 頂部關鍵指標
    c1, c2, c3 = st.columns(3)
    top_curr = stat_df.loc[stat_df['目前輸贏'].idxmax()]
    top_pred = stat_df.loc[stat_df['預測GW38輸贏'].idxmax()]
    c1.metric("當前贏家", top_curr['經理人'], f"{top_curr['目前輸贏']} pts")
    c2.metric("預測季末贏家", top_pred['經理人'], f"{top_pred['預測GW38輸贏']} pts")
    c3.metric("剩餘週期", f"{remaining} 週")

    # 1. 核心結算與預估 (全體玩家)
    st.markdown("---")
    st.header("🏆 聯賽核心決算矩陣")
    
    def color_gl(val):
        color = '#2ecc71' if val > 0 else '#e74c3c'
        return f'color: {color}; font-weight: bold'

    main_display = stat_df[['經理人', '目前總分', '目前輸贏', 'GW38 EV', '預測GW38輸贏', '預測下限', '預測上限']]
    st.dataframe(main_display.sort_values('目前總分', ascending=False).style.applymap(color_gl, subset=['目前輸贏', '預測GW38輸贏']), use_container_width=True, hide_index=True)

    # 2. 專業統計摘要 (所有玩家數據)
    st.markdown("---")
    st.header("📊 專業統計摘要 (Professional Analytics)")
    st.write("這部分展示所有玩家的深度統計數據，用於評估風險與得分效率。")
    
    pro_display = stat_df[['經理人', '夏普比率', '貝塔係數(β)', '穩定度(σ)', '最大回撤']].sort_values('夏普比率', ascending=False)
    st.dataframe(pro_display, use_container_width=True, hide_index=True)

    # 3. 視覺化分析圖表
    st.markdown("---")
    st.header("📈 多維度分析圖表")
    
    tab1, tab2 = st.tabs(["💰 累計輸贏趨勢", "🎯 期望值預測區間"])
    
    with tab1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='輸贏積分'))
    
    with tab2:
        # 使用水平條形圖模擬區間
        chart_df = stat_df.sort_values('GW38 EV')
        st.bar_chart(chart_df.set_index('經理人')[['預測下限', 'GW38 EV', '預測上限']])

    # 4. 統計模型與術語說明
    with st.expander("📖 專業統計術語與模型說明"):
        st.markdown(f"""
        - **夏普比率 (Sharpe Ratio)**: 數值越高，代表你在同樣的得分波動下，獲取積分的能力越強（效率越高）。
        - **貝塔係數 (Beta)**: 衡量你與聯賽整體的同步性。
            - `> 1.0`: 激進型，陣容充滿冷門球員 (Differentials)。
            - `< 1.0`: 穩健型，跟隨主流大部隊。
        - **GW38 EV (期望值)**: 使用 **加權移動平均 (WMA)** 推算。對最近 5 週的表現給予 $5:4:3:2:1$ 的權重，捕捉當前轉會窗的球隊強度。
        - **預測區間 (Prediction Range)**: 基於隨機過程理論。公式為 $EV \pm (1.96 \times \sigma \times \sqrt{{t}})$。這代表有 95% 的概率，你的最終分數會落在此區間。
        """)

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

st.caption(f"FPL League ID: {LEAGUE_ID} | Powered by Gemini Analytics | 排除玩家: {IGNORE_PLAYER}")
