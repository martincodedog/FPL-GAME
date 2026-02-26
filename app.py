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
    [data-testid="stMetricValue"] { font-size: 20px !important; font-weight: 700; }
    .player-card {
        background-color: #ffffff;
        padding: 12px;
        border-radius: 12px;
        border-left: 6px solid #3498db;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.07);
    }
    .mom-up { color: #2ecc71; font-weight: bold; }
    .mom-down { color: #e74c3c; font-weight: bold; }
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
        
        # WMA 預測 & Range
        wma = np.average(pts.tail(5), weights=[1,2,3,4,5])
        ev = m_df['總分'].iloc[-1] + (wma * t)
        std = pts.std()
        margin = 1.96 * std * np.sqrt(t) if t > 0 else 0
        
        # RSI
        delta = pts.diff()
        gain = (delta.where(delta > 0, 0)).rolling(5).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(5).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        # MACD
        macd = (pts.ewm(span=3).mean() - pts.ewm(span=8).mean()).iloc[-1]
        sig = (pts.ewm(span=3).mean() - pts.ewm(span=8).mean()).ewm(span=3).mean().iloc[-1]
        
        # Momentum (近3週平均 vs 賽季平均)
        mom = pts.tail(3).mean() - pts.mean()

        quant_list.append({
            "經理人": manager,
            "目前輸贏": int(m_df['目前輸贏'].iloc[-1]),
            "GW38 EV": int(ev),
            "Expected Upper": int(ev + margin),
            "Expected Lower": int(ev - margin),
            "RSI": int(rsi) if not np.isnan(rsi) else 50,
            "趨勢": "🟢 轉強" if macd > sig else "🔴 走弱",
            "動量": round(mom, 1)
        })

    res_df = pd.DataFrame(quant_list).sort_values('目前輸贏', ascending=False)
    
    # 預測輸贏對沖
    total_ev = res_df['GW38 EV'].sum()
    res_df['預測輸贏'] = ((res_df['GW38 EV'] * len(res_df) - total_ev) * 2).astype(int)

    # --- UI 呈現 ---
    st.title("🏛️ FPL 量化博弈終端")
    
    # A. 頂部總覽
    c1, c2, c3 = st.columns(3)
    c1.metric("領先經理人", res_df.iloc[0]['經理人'])
    c2.metric("最大輸贏額", f"{res_df['目前輸贏'].max()} pts")
    c3.metric("剩餘賽事", f"{t} 週")

    # B. 個人狀態卡片 (含 Momentum)
    st.subheader("👤 經理人實時卡片")
    cols = st.columns(2)
    for idx, row in res_df.iterrows():
        mom_class = "mom-up" if row['動量'] > 0 else "mom-down"
        mom_icon = "↑" if row['動量'] > 0 else "↓"
        
        with cols[idx % 2]:
            st.markdown(f"""
            <div class="player-card">
                <div style="display: flex; justify-content: space-between;">
                    <small style="color:gray;">{row['經理人']}</small>
                    <span class="{mom_class}">{mom_icon} {abs(row['動量'])}</span>
                </div>
                <div style="margin: 8px 0;">
                    <strong style="font-size:20px;">{row['目前輸贏']} pts</strong>
                </div>
                <div style="font-size:13px; color:#555;">
                    預測季末：<b style="color:{'#2ecc71' if row['預測輸贏'] > 0 else '#e74c3c'}">{row['預測輸贏']}</b><br>
                    RSI: {row['RSI']} | {row['趨勢']}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # C. 深度量化矩陣 (轉置)
    st.markdown("---")
    st.subheader("📊 決算矩陣 (Settlement Matrix)")
    matrix_df = res_df.set_index('經理人').T
    row_order = ['目前輸贏', '預測輸贏', 'GW38 EV', 'Expected Upper', 'Expected Lower', 'RSI', '動量', '趨勢']
    st.dataframe(matrix_df.reindex(row_order), use_container_width=True)

    # D. 視覺化分析
    st.markdown("---")
    t1, t2 = st.tabs(["💰 輸贏曲線", "🔮 預測區間對比"])
    with t1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
    with t2:
        st.write("GW38 分數落點區間 (EV ± Range):")
        range_view = res_df[['經理人', 'Expected Lower', 'GW38 EV', 'Expected Upper']].sort_values('GW38 EV', ascending=False)
        st.dataframe(range_view, use_container_width=True, hide_index=True)
        

except Exception as e:
    st.error(f"Error: {e}")

st.caption(f"iPhone Optimized | GW {max_gw} | Momentum = Recent 3 Avg - Season Avg")
