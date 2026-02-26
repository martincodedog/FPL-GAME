import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化
st.set_page_config(page_title="FPL 量化終端", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    [data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 700; color: #2c3e50; }
    .stDataFrame { border-radius: 12px; }
    </style>
    """, unsafe_allow_html=True)

LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

@st.cache_data(ttl=3600)
def fetch_fpl_quant_data(league_id):
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

def calculate_rsi(series, period=5):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

try:
    df = fetch_fpl_quant_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    remaining = 38 - max_gw

    # --- 1. 核心輸贏計算 (Net Score * 2) ---
    def calc_net_score(group):
        n = len(group)
        total = group['總分'].sum()
        group['輸贏積分'] = (group['總分'] * (n - 1) - (total - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_net_score)

    # --- 2. 技術指標與專業統計計算 ---
    quant_stats = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        points_series = m_df['當週分']
        
        # 技術指標: RSI (5週)
        m_df['RSI'] = calculate_rsi(points_series)
        
        # 技術指標: MACD (12, 26, 9)
        exp1 = points_series.ewm(span=3, adjust=False).mean() # 縮短週期適應 FPL 賽季
        exp2 = points_series.ewm(span=8, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=3, adjust=False).mean()
        
        # 統計預測: WMA 近 5 週
        recent = points_series.tail(5)
        wma_avg = np.average(recent, weights=np.arange(1, len(recent) + 1))
        ev_gw38 = m_df['總分'].iloc[-1] + (wma_avg * remaining)
        
        # 專業指標
        std_dev = points_series.std()
        drawdown = (m_df['輸贏積分'] - m_df['輸贏積分'].cummax()).min()
        
        quant_stats.append({
            "經理人": manager,
            "目前總分": int(m_df['總分'].iloc[-1]),
            "輸贏積分": int(m_df['輸贏積分'].iloc[-1]),
            "GW38 EV": int(ev_gw38),
            "RSI (強弱)": int(m_df['RSI'].iloc[-1]) if not np.isnan(m_df['RSI'].iloc[-1]) else 50,
            "MACD 狀態": "🔴 走弱" if macd.iloc[-1] < signal.iloc[-1] else "🟢 轉強",
            "穩定度(σ)": int(std_dev),
            "最大回撤": int(drawdown)
        })

    stat_df = pd.DataFrame(quant_stats)
    
    # 預測平衡
    total_ev = stat_df['GW38 EV'].sum()
    n_p = len(stat_df)
    stat_df['預測GW38輸贏'] = (stat_df['GW38 EV'] * (n_p - 1) - (total_ev - stat_df['GW38 EV'])) * 2
    stat_df['預測GW38輸贏'] = stat_df['預測GW38輸贏'].astype(int)

    # --- UI 呈現 ---
    st.title("📈 FPL 量化技術分析終端")
    
    # 指標卡
    c1, c2, c3 = st.columns(3)
    c1.metric("領先經理人", stat_df.loc[stat_df['目前總分'].idxmax()]['經理人'])
    c2.metric("RSI 最強 (超買)", stat_df.loc[stat_df['RSI (強弱)'].idxmax()]['經理人'], f"{stat_df['RSI (強弱)'].max()}")
    c3.metric("MACD 金叉數", len(stat_df[stat_df['MACD 狀態'] == "🟢 轉強"]))

    # 1. 全球經理人技術矩陣
    st.markdown("---")
    st.header("🏆 聯賽量化決算表")
    
    def color_quant(val):
        if isinstance(val, int) or isinstance(val, float):
            color = '#2ecc71' if val > 0 else '#e74c3c'
            return f'color: {color}; font-weight: bold'
        return ''

    def style_rsi(val):
        if val > 70: return 'background-color: #ffcccc' # 超買
        if val < 30: return 'background-color: #ccffcc' # 超賣
        return ''

    main_display = stat_df[['經理人', '目前總分', '輸贏積分', '預測GW38輸贏', 'RSI (強弱)', 'MACD 狀態', '穩定度(σ)', '最大回撤']]
    st.dataframe(
        main_display.sort_values('目前總分', ascending=False)
        .style.applymap(color_quant, subset=['輸贏積分', '預測GW38輸贏'])
        .applymap(style_rsi, subset=['RSI (強弱)']),
        use_container_width=True, hide_index=True
    )

    # 2. 技術圖表
    st.markdown("---")
    st.header("📊 技術指標視覺化")
    
    tab1, tab2 = st.tabs(["💰 輸贏積分曲線", "🔥 RSI 動能對比"])
    
    with tab1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='輸贏積分'))
        
    
    with tab2:
        rsi_chart = df.copy()
        rsi_chart['RSI'] = rsi_chart.groupby('經理人')['當週分'].transform(lambda x: calculate_rsi(x))
        st.line_chart(rsi_chart.pivot(index='GW', columns='經理人', values='RSI').fillna(50))
        

    # 3. 說明
    with st.expander("📖 技術指標說明"):
        st.markdown("""
        - **RSI (相對強弱指數)**：0-100。數值越高代表近期得分相對於其他週數更強。>70 警惕回調，<30 期待反彈。
        - **MACD (趨勢指標)**：觀察積分的「速度」。🟢 轉強代表近期得分增速加快，斜率向上。
        - **最大回撤**：反映該玩家本賽季經歷過的最慘積分損失，測試抗壓能力。
        """)

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

st.caption("技術分析模型僅供參考。Powered by Gemini Quantitative Analytics.")
