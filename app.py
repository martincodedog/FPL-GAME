import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化
st.set_page_config(page_title="FPL 量化矩陣終端", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS
st.markdown("""
    <style>
    .main { background-color: #f4f7f6; }
    [data-testid="stMetricValue"] { font-size: 18px !important; }
    /* 強化表格在手機上的顯示 */
    .stDataFrame div[data-testid="stTable"] { font-size: 12px !important; }
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
    
    rows = []
    for m in members:
        h_url = f"https://fantasy.premierleague.com/api/entry/{m['entry']}/history/"
        h = requests.get(h_url, headers=headers).json()['current']
        for gw in h:
            rows.append({"GW": gw['event'], "經理人": m['player_name'], "總分": gw['total_points'], "當週分": gw['points']})
    return pd.DataFrame(rows)

try:
    df = fetch_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    t = 38 - max_gw

    # 1. 核心輸贏計算 (Net Score * 2)
    def calc_gl(group):
        n = len(group)
        group['目前輸贏'] = (group['總分'] * (n - 1) - (group['總分'].sum() - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # 2. 量化指標與預測模型
    quant_results = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        pts = m_df['當週分']
        
        # --- 預測模型 (WMA + Range) ---
        wma = np.average(pts.tail(5), weights=[1,2,3,4,5])
        ev = m_df['總分'].iloc[-1] + (wma * t)
        std = pts.std()
        margin = 1.96 * std * np.sqrt(t) if t > 0 else 0
        
        # --- 技術指標 ---
        # RSI (5週)
        delta = pts.diff()
        gain = (delta.where(delta > 0, 0)).rolling(5).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(5).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        # MACD (快3/慢8)
        macd = pts.ewm(span=3).mean() - pts.ewm(span=8).mean()
        signal = macd.ewm(span=3).mean()
        
        # 布林帶 %B (衡量是否處於得分紅利期)
        ma5 = pts.rolling(5).mean()
        std5 = pts.rolling(5).std()
        b_percent = (pts - (ma5 - 2*std5)) / (4*std5) if std5.iloc[-1] != 0 else 0.5
        
        # 動量指標 (Momentum)
        mom = pts.tail(3).mean() - pts.mean()

        quant_results.append({
            "經理人": manager,
            "目前輸贏": int(m_df['目前輸贏'].iloc[-1]),
            "GW38 EV": int(ev),
            "Expected Upper": int(ev + margin),
            "Expected Lower": int(ev - margin),
            "RSI (動能)": int(rsi) if not np.isnan(rsi) else 50,
            "MACD 趨勢": "🟢 轉強" if macd.iloc[-1] > signal.iloc[-1] else "🔴 走弱",
            "布林帶 %B": round(b_percent.iloc[-1], 2) if not np.isnan(b_percent.iloc[-1]) else 0.5,
            "爆發力 (Mom)": int(mom)
        })

    res_df = pd.DataFrame(quant_results)
    
    # 預計季末輸贏對沖
    total_ev = res_df['GW38 EV'].sum()
    res_df['預測輸贏'] = ((res_df['GW38 EV'] * len(res_df) - total_ev) * 2).astype(int)

    # --- UI 呈現 ---
    st.title("🏛️ FPL 量化決算矩陣終端")

    # 1. 預測假設
    with st.expander("📝 預測模型假設 (Predict Assumption)"):
        st.markdown(f"""
        - **EV (Expected Value)**: 基於近 5 週加權得分 (WMA) 推算至第 38 週。
        - **Range (Upper/Lower)**: 95% 信賴區間，考量剩餘 **{t}** 週的歷史波動率。
        - **布林帶 %B**: `> 1` 代表近期表現超常，`< 0` 代表表現低迷。
        """)

    # 2. 決算矩陣 (重點優化：經理人為 Columns)
    st.subheader("📊 決算矩陣 (Settlement Matrix)")
    # 轉置表格：將經理人變為欄位
    matrix_df = res_df.set_index('經理人').T
    
    # 重新排列 Row 順序，確保最重要的數據在最上面
    row_order = [
        '目前輸贏', '預測輸贏', 'GW38 EV', 'Expected Upper', 'Expected Lower', 
        'RSI (動能)', 'MACD 趨勢', '布林帶 %B', '爆發力 (Mom)'
    ]
    matrix_df = matrix_df.reindex(row_order)
    
    st.dataframe(matrix_df, use_container_width=True)

    # 3. 圖表分析
    st.markdown("---")
    t1, t2 = st.tabs(["💰 輸贏曲線", "🔮 預測分佈"])
    
    with t1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
        
    with t2:
        st.write("各經理人季末總分期望區間 (EV ± Range):")
        # 顯示橫向預測區間
        range_chart_df = res_df[['經理人', 'Expected Lower', 'GW38 EV', 'Expected Upper']].sort_values('GW38 EV', ascending=False)
        st.dataframe(range_chart_df, use_container_width=True, hide_index=True)
        

except Exception as e:
    st.error(f"Error: {e}")

st.caption(f"FPL Data Optimized for iPhone | Current GW: {max_gw}")
