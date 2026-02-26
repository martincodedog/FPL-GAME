import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化
st.set_page_config(page_title="FPL 量化終端", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS (修正手機表格間距)
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    [data-testid="stMetricValue"] { font-size: 20px !important; font-weight: 700; }
    .stDataFrame div[data-testid="stTable"] { font-size: 12px !important; }
    .stAlert { padding: 0.5rem 0.75rem !important; }
    </style>
    """, unsafe_allow_html=True)

LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

@st.cache_data(ttl=3600)
def fetch_data(league_id):
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
    return 100 - (100 / (1 + (gain / loss)))

try:
    df = fetch_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    remaining = 38 - max_gw

    # 1. 核心輸贏計算
    def calc_gl(group):
        n = len(group)
        total = group['總分'].sum()
        group['輸贏'] = (group['總分'] * (n - 1) - (total - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # 2. 預測假設與技術指標計算
    stats = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        pts = m_df['當週分']
        
        # MACD (快3, 慢8) - 適應短賽季
        ema3, ema8 = pts.ewm(span=3).mean(), pts.ewm(span=8).mean()
        macd_val = ema3 - ema8
        sig_val = macd_val.ewm(span=3).mean()
        
        # 統計學預測 (WMA)
        recent = pts.tail(5)
        wma = np.average(recent, weights=np.arange(1, len(recent) + 1))
        ev38 = m_df['總分'].iloc[-1] + (wma * remaining)
        
        stats.append({
            "經理人": manager,
            "目前總分": int(m_df['總分'].iloc[-1]),
            "目前輸贏": int(m_df['輸贏'].iloc[-1]),
            "預測GW38總分": int(ev38),
            "RSI": int(calculate_rsi(pts).iloc[-1]) if not np.isnan(calculate_rsi(pts).iloc[-1]) else 50,
            "趨勢": "🟢 強勢" if macd_val.iloc[-1] > sig_val.iloc[-1] else "🔴 走弱",
            "波動": int(pts.std())
        })

    res_df = pd.DataFrame(stats)
    total_ev = res_df['預測GW38總分'].sum()
    n_p = len(res_df)
    res_df['預測GW38輸贏'] = ((res_df['預測GW38總分'] * (n_p - 1)) - (total_ev - res_df['預測GW38總分'])) * 2
    res_df['預測GW38輸贏'] = res_df['預測GW38輸贏'].astype(int)

    # --- UI 呈現 ---
    st.title("🏛️ FPL 決算終端")

    # 0. 預測假設 (Predict Assumption)
    st.info(f"""
    **🔍 預測邏輯假設 (Predict Assumptions):**
    1. **動態加權 (WMA)**: 考慮到 FPL 陣容會隨轉會窗與傷病變化，預測對最近 5 週表現賦予 $5:4:3:2:1$ 的加權權重，而非單純平均。
    2. **積分池平衡**: 預測的輸贏積分是基於第 38 週所有人的「預期總分」重新進行全聯賽對沖計算。
    3. **技術指標**: **RSI > 70** 代表近期表現過熱 (Overbought)；**MACD 🟢** 代表得分進入上升通道。
    """)

    # 1. 頂部看板
    c1, c2 = st.columns(2)
    c1.metric("當前贏家", res_df.loc[res_df['目前輸贏'].idxmax()]['經理人'], f"{res_df['目前輸贏'].max()} pts")
    c2.metric("預計季末贏家", res_df.loc[res_df['預測GW38輸贏'].idxmax()]['經理人'], f"{res_df['預測GW38輸贏'].max()} pts")

    # 2. 簡化後的數據表 (iPhone 優化)
    st.markdown("### 🏆 決算矩陣")
    def style_gl(val):
        return f'color: {"#2ecc71" if val > 0 else "#e74c3c"}; font-weight: bold'

    # 只顯示最核心的 5 個欄位，避免手機需要左右滑動
    display_df = res_df[['經理人', '目前輸贏', '預測GW38輸贏', 'RSI', '趨勢']].sort_values('目前輸贏', ascending=False)
    st.dataframe(
        display_df.style.applymap(style_gl, subset=['目前輸贏', '預測GW38輸贏']),
        use_container_width=True, hide_index=True
    )

    # 3. 視覺化分析
    st.markdown("### 📊 技術分析圖")
    tab1, tab2 = st.tabs(["💰 輸贏趨勢", "🔥 強弱動能"])
    
    with tab1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='輸贏'))
        
        
    with tab2:
        rsi_df = df.copy()
        rsi_df['RSI'] = rsi_df.groupby('經理人')['當週分'].transform(lambda x: calculate_rsi(x))
        st.line_chart(rsi_df.pivot(index='GW', columns='經理人', values='RSI').fillna(50))
        

except Exception as e:
    st.error(f"Error: {e}")

st.caption(f"GW {max_gw} Data | Optimized for Mobile")
