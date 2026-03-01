import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化
st.set_page_config(page_title="FPL Quant Terminal", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .stMetric { background-color: #ffffff; padding: 12px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .player-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border-left: 6px solid #3498db;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.07);
    }
    .change-up { color: #2ecc71; font-weight: bold; font-size: 0.85em; }
    .change-down { color: #e74c3c; font-weight: bold; font-size: 0.85em; }
    .card-label { color: gray; font-size: 0.75em; text-transform: uppercase; }
    /* 將 Slider 區塊固定在底部的視覺引導 */
    .footer-spacer { height: 100px; }
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
            rows.append({
                "GW": gw['event'], 
                "經理人": m['player_name'], 
                "總分": gw['total_points'], 
                "當週分": gw['points']
            })
    return pd.DataFrame(rows)

try:
    all_df = fetch_data(LEAGUE_ID)
    latest_gw = all_df['GW'].max()

    # --- 頂部摘要 ---
    st.title("🏛️ FPL 量化博弈矩陣")
    
    # 邏輯計算預覽 (在選擇 GW 之前先計算全量)
    def calc_net_score_full(group):
        n = len(group)
        group['目前輸贏'] = (group['總分'] * (n - 1) - (group['總分'].sum() - group['總分'])) * 2
        return group
    full_df = all_df.groupby('GW', group_keys=False).apply(calc_net_score_full)

    # --- B. 經理人實時卡片區域 ---
    # 先建立一個 placeholder 以便在 Slider 之後填入內容
    card_container = st.container()

    # --- C. 深度量化矩陣 ---
    st.markdown("---")
    st.subheader("📊 深度量化矩陣 (Matrix)")
    matrix_placeholder = st.empty()

    # --- D. 視覺化分析 ---
    st.markdown("---")
    t1, t2 = st.tabs(["💰 輸贏曲線", "🔮 預測區間"])
    with t1:
        st.line_chart(full_df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        

    # --- E. 底部滑桿 (Sticky-like Slider) ---
    st.markdown('<div class="footer-spacer"></div>', unsafe_allow_html=True)
    st.markdown("---")
    selected_gw = st.select_slider("📅 選擇 Game Week 回顧歷史數據", options=list(range(1, int(latest_gw) + 1)), value=int(latest_gw))

    # --- 數據連動計算 ---
    df_filtered = full_df[full_df['GW'] <= selected_gw].copy()
    remaining = 38 - selected_gw
    quant_list = []

    for manager in df_filtered['經理人'].unique():
        m_history = df_filtered[df_filtered['經理人'] == manager].sort_values('GW')
        pts_all = m_history['當週分']
        curr_row = m_history.iloc[-1]
        
        # Change defined as Change of "目前輸贏"
        curr_net = curr_row['目前輸贏']
        prev_net = m_history['目前輸贏'].iloc[-2] if len(m_history) > 1 else 0
        net_change = curr_net - prev_net
        
        # 5 Technical Indicators
        # 1. RSI
        delta = pts_all.diff()
        gain = (delta.where(delta > 0, 0)).rolling(5).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(5).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1] if len(pts_all) >= 5 else 50
        # 2. MACD
        macd = (pts_all.ewm(span=3).mean() - pts_all.ewm(span=8).mean()).iloc[-1]
        sig = (pts_all.ewm(span=3).mean() - pts_all.ewm(span=8).mean()).ewm(span=3).mean().iloc[-1]
        # 3. Momentum
        mom = pts_all.tail(3).mean() - pts_all.mean()
        # 4. Bollinger %B
        ma5 = pts_all.rolling(5).mean(); std5 = pts_all.rolling(5).std()
        b_perc = (pts_all.iloc[-1] - (ma5.iloc[-1] - 2*std5.iloc[-1])) / (4*std5.iloc[-1]) if len(pts_all) >= 5 and std5.iloc[-1] != 0 else 0.5
        # 5. Volatility
        vol = pts_all.std()

        # WMA Prediction
        wma = np.average(pts_all.tail(5), weights=np.arange(1, len(pts_all.tail(5)) + 1))
        ev38 = curr_row['總分'] + (wma * remaining)

        quant_list.append({
            "經理人": manager,
            "Final Score": int(curr_row['總分']),
            "This GW Score": int(curr_row['當週分']),
            "目前輸贏": int(curr_net),
            "輸贏變動 (Net Chg)": int(net_change),
            "Predict Final": int(ev38),
            "RSI 動能": int(rsi) if not np.isnan(rsi) else 50,
            "MACD 趨勢": "🟢 轉強" if macd > sig else "🔴 走弱",
            "動量 Mom": round(mom, 1),
            "布林帶 %B": round(b_perc, 2),
            "波動率 σ": round(vol, 1)
        })

    res_df = pd.DataFrame(quant_list).sort_values('Final Score', ascending=False)

    # 填充卡片容器
    with card_container:
        st.subheader(f"👤 經理人實時狀態 (GW {selected_gw})")
        cols = st.columns(2)
        for idx, row in res_df.iterrows():
            chg_style = "change-up" if row['輸贏變動 (Net Chg)'] >= 0 else "change-down"
            chg_icon = "+" if row['輸贏變動 (Net Chg)'] >= 0 else ""
            with cols[idx % 2]:
                st.markdown(f"""
                <div class="player-card">
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <strong style="font-size:15px;">{row['經理人']}</strong>
                        <span class="{chg_style}">{chg_icon}{row['輸贏變動 (Net Chg)']} pts</span>
                    </div>
                    <div style="margin: 8px 0; display: flex; justify-content: space-between;">
                        <div>
                            <span class="card-label">Total Score</span><br>
                            <b style="font-size:18px;">{row['Final Score']}</b>
                        </div>
                        <div style="text-align: right;">
                            <span class="card-label">GW Score</span><br>
                            <b style="font-size:18px; color:#3498db;">{row['This GW Score']}</b>
                        </div>
                    </div>
                    <div style="margin-top: 5px; padding-top: 5px; border-top: 1px dashed #ddd;">
                        <span class="card-label">Predict Final GW38</span><br>
                        <b style="font-size:15px; color:#2c3e50;">{row['Predict Final']} EV</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # 填充矩陣
    matrix_placeholder.dataframe(res_df.set_index('經理人').T, use_container_width=True)
    
    with t2:
        st.write("GW38 分數落點期望值與區間:")
        st.dataframe(res_df[['經理人', 'Final Score', 'Predict Final']].sort_values('Predict Final', ascending=False), use_container_width=True, hide_index=True)
        

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

st.caption(f"GW {selected_gw} | Change = Current Net Score - Previous Net Score")
