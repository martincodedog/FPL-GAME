import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化
st.set_page_config(page_title="FPL 量化終端 PRO", layout="wide", initial_sidebar_state="collapsed")

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
    .change-up { color: #2ecc71; font-weight: bold; font-size: 0.9em; }
    .change-down { color: #e74c3c; font-weight: bold; font-size: 0.9em; }
    .card-label { color: gray; font-size: 0.8em; }
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

    # --- A. 側邊欄/頂部滑桿 ---
    st.subheader("📅 選擇 Game Week 觀看歷史")
    selected_gw = st.slider("滑動查看歷史週數數據", 1, int(latest_gw), int(latest_gw))
    
    # 過濾數據至選擇的週數
    df = all_df[all_df['GW'] <= selected_gw].copy()
    remaining = 38 - selected_gw

    # 1. 核心輸贏計算
    def calc_gl(group):
        n = len(group)
        group['目前輸贏'] = (group['總分'] * (n - 1) - (group['總分'].sum() - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # 2. 技術指標與預測模型
    quant_list = []
    current_gw_data = df[df['GW'] == selected_gw]
    
    for manager in df['經理人'].unique():
        m_history = df[df['經理人'] == manager].sort_values('GW')
        pts_all = m_history['當週分']
        curr_total = m_history['總分'].iloc[-1]
        curr_gw_score = m_history['當週分'].iloc[-1]
        
        # Change from last week
        prev_total = m_history['總分'].iloc[-2] if len(m_history) > 1 else 0
        change = curr_total - prev_total
        
        # --- 技術指標 ---
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
        ma5 = pts_all.rolling(5).mean()
        std5 = pts_all.rolling(5).std()
        b_perc = (pts_all.iloc[-1] - (ma5.iloc[-1] - 2*std5.iloc[-1])) / (4*std5.iloc[-1]) if len(pts_all) >= 5 and std5.iloc[-1] != 0 else 0.5
        
        # 5. Volatility (σ)
        vol = pts_all.std()

        # 預測模型 (WMA)
        wma = np.average(pts_all.tail(5), weights=np.arange(1, len(pts_all.tail(5)) + 1))
        ev38 = curr_total + (wma * remaining)
        margin = 1.96 * vol * np.sqrt(remaining) if remaining > 0 else 0

        quant_list.append({
            "經理人": manager,
            "Final Score": int(curr_total),
            "This GW Score": int(curr_gw_score),
            "Change": int(change),
            "Predict Final": int(ev38),
            "目前輸贏": int(m_history['目前輸贏'].iloc[-1]),
            "Exp Upper": int(ev38 + margin),
            "Exp Lower": int(ev38 - margin),
            "RSI 動能": int(rsi) if not np.isnan(rsi) else 50,
            "MACD 狀態": "🟢 轉強" if macd > sig else "🔴 走弱",
            "動量 Mom": round(mom, 1),
            "布林帶 %B": round(b_perc, 2),
            "波動率 σ": round(vol, 1)
        })

    res_df = pd.DataFrame(quant_list).sort_values('Final Score', ascending=False)

    # --- UI 呈現 ---
    st.title(f"🏛️ FPL 量化終端 (GW {selected_gw})")
    
    # 📝 說明區塊
    st.markdown("""
    ### 📝 指標假設 (Assumptions)
    > **WMA 預測**: 基於近 5 週加權得分推算第 38 週。**Change**: 本週與上週總分之差。
    > **RSI/MACD**: 捕捉得分趨勢。**EV Range**: 95% 信賴區間落點。
    """)

    # B. 經理人實時卡片
    st.subheader("👤 經理人實時卡片")
    cols = st.columns(2)
    for idx, row in res_df.iterrows():
        change_style = "change-up" if row['Change'] >= 0 else "change-down"
        change_icon = "+" if row['Change'] >= 0 else ""
        
        with cols[idx % 2]:
            st.markdown(f"""
            <div class="player-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <strong style="font-size:16px;">{row['經理人']}</strong>
                    <span class="{change_style}">{change_icon}{row['Change']} (Total)</span>
                </div>
                <hr style="margin: 8px 0; border: 0.1px solid #eee;">
                <div style="display: flex; justify-content: space-between;">
                    <div>
                        <span class="card-label">Final Score</span><br>
                        <b style="font-size:18px;">{row['Final Score']}</b>
                    </div>
                    <div style="text-align: right;">
                        <span class="card-label">This GW</span><br>
                        <b style="font-size:18px; color:#3498db;">{row['This GW Score']}</b>
                    </div>
                </div>
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed #ddd;">
                    <span class="card-label">Predict Final (GW38)</span><br>
                    <b style="font-size:16px; color:#2c3e50;">{row['Predict Final']}</b>
                    <small style="color:gray; font-size:11px;"> (EV)</small>
                </div>
            </div>
            """, unsafe_allow_html=True)

    # C. 決算矩陣 (轉置)
    st.markdown("---")
    st.subheader("📊 深度量化矩陣 (Matrix)")
    matrix_df = res_df.set_index('經理人').T
    st.dataframe(matrix_df, use_container_width=True)

    # D. 技術指標解析
    with st.expander("🔬 查看 5 項技術指標定義"):
        st.markdown("""
        1. **RSI**: 5 週強弱指標。>70 警惕回調，<30 期待反彈。
        2. **MACD**: 趨勢指標。🟢 代表近期得分加速度向上。
        3. **動量 (Mom)**: 近 3 週均分與全賽季均分之差。
        4. **布林帶 %B**: 衡量本週得分在過去波動範圍中的位置。
        5. **波動率 (σ)**: 得分穩定性。
        """)

    # E. 視覺化分析
    st.markdown("---")
    tab1, tab2 = st.tabs(["💰 輸贏曲線", "🔮 預測區間"])
    with tab1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
    with tab2:
        st.write("GW38 分數落點區間 (EV ± Range):")
        range_view = res_df[['經理人', 'Exp Lower', 'Predict Final', 'Exp Upper']].sort_values('Predict Final', ascending=False)
        st.dataframe(range_view, use_container_width=True, hide_index=True)
        

except Exception as e:
    st.error(f"數據處理出錯: {e}")

st.caption(f"FPL Pro Analytics | GW {selected_gw} | Optimized for Mobile")
