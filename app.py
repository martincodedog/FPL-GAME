import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端優化
st.set_page_config(page_title="FPL 量化終端 PRO", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    [data-testid="stMetricValue"] { font-size: 22px !important; font-weight: 700; }
    .player-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border-left: 5px solid #3498db;
        margin-bottom: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
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

    # 1. 核心輸贏計算
    def calc_gl(group):
        n = len(group)
        group['目前輸贏'] = (group['總分'] * (n - 1) - (group['總分'].sum() - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # 2. 量化指標與預測
    quant_list = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        pts = m_df['當週分']
        wma = np.average(pts.tail(5), weights=[1,2,3,4,5])
        ev = m_df['總分'].iloc[-1] + (wma * t)
        std = pts.std()
        margin = 1.96 * std * np.sqrt(t) if t > 0 else 0
        
        # RSI & MACD
        delta = pts.diff()
        gain = (delta.where(delta > 0, 0)).rolling(5).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(5).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        macd = (pts.ewm(span=3).mean() - pts.ewm(span=8).mean()).iloc[-1]
        sig = (pts.ewm(span=3).mean() - pts.ewm(span=8).mean()).ewm(span=3).mean().iloc[-1]

        quant_list.append({
            "經理人": manager,
            "目前輸贏": int(m_df['目前輸贏'].iloc[-1]),
            "GW38 EV": int(ev),
            "Expected Upper": int(ev + margin),
            "Expected Lower": int(ev - margin),
            "RSI": int(rsi) if not np.isnan(rsi) else 50,
            "趨勢": "🟢 轉強" if macd > sig else "🔴 走弱",
            "波動度": int(std)
        })

    res_df = pd.DataFrame(quant_list).sort_values('目前輸贏', ascending=False)
    
    # 預測輸贏對沖
    total_ev = res_df['GW38 EV'].sum()
    res_df['預測輸贏'] = ((res_df['GW38 EV'] * len(res_df) - total_ev) * 2).astype(int)

    # --- UI 呈現 ---
    
    # A. 頂部看板 (指標卡片)
    st.title("🏛️ FPL 量化博弈終端")
    c1, c2, c3 = st.columns(3)
    c1.metric("聯賽榜首", res_df.iloc[0]['經理人'])
    c2.metric("最高輸贏", f"{res_df['目前輸贏'].max()} pts")
    c3.metric("剩餘週期", f"{t} 週")

    # B. 個人狀態卡片 (iPhone 滾動式卡片)
    st.subheader("👤 經理人即時狀態卡")
    # 在手機上，我們使用 2 欄顯示卡片
    cols = st.columns(2)
    for idx, row in res_df.iterrows():
        with cols[idx % 2]:
            st.markdown(f"""
            <div class="player-card">
                <small style="color:gray;">{row['經理人']}</small><br>
                <strong style="font-size:18px;">目前：{row['目前輸贏']} pts</strong><br>
                <span style="color:{'#2ecc71' if row['預測輸贏'] > 0 else '#e74c3c'}; font-size:14px;">
                    預測季末：{row['預測輸贏']} pts
                </span><br>
                <small>動能 RSI: {row['RSI']} | {row['趨勢']}</small>
            </div>
            """, unsafe_allow_html=True)

    # C. 決算矩陣 (轉置表格)
    st.markdown("---")
    st.subheader("📊 深度量化矩陣 (Matrix)")
    matrix_df = res_df.set_index('經理人').T
    row_order = ['目前輸贏', '預測輸贏', 'GW38 EV', 'Expected Upper', 'Expected Lower', 'RSI', '趨勢', '波動度']
    st.dataframe(matrix_df.reindex(row_order), use_container_width=True)

    # D. 預測假設
    with st.expander("📝 預測模型假設 (Predict Assumption)"):
        st.markdown(f"""
        - **EV (Expected Value)**: 使用加權移動平均 (WMA) 近 5 週表現推算。
        - **Range**: 95% 信賴區間，隨剩餘週數 $\sqrt{{t}}$ 縮減。
        - **Net Score x 2**: 所有預測輸贏皆為全聯賽成員間的積分對沖結果。
        """)

    # E. 圖表
    st.markdown("---")
    t1, t2 = st.tabs(["💰 輸贏曲線", "🔮 區間對比"])
    with t1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
    with t2:
        st.write("各經理人季末總分預期區間 (EV ± Range):")
        st.dataframe(res_df[['經理人', 'Expected Lower', 'GW38 EV', 'Expected Upper']].sort_values('GW38 EV', ascending=False), use_container_width=True, hide_index=True)
        

except Exception as e:
    st.error(f"Error: {e}")

st.caption(f"Optimized for iPhone | GW {max_gw} | Powered by Gemini Analytics")
