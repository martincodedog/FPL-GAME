import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端優化：預設縮起側邊欄，使用寬屏佈局
st.set_page_config(page_title="FPL 數據決算終端", layout="wide", initial_sidebar_state="collapsed")

# 自定義 CSS 優化手機閱讀體驗
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetricValue"] { font-size: 22px !important; color: #1f77b4; }
    .stDataFrame { border: 1px solid #e6e9ef; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# 常數設定
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

@st.cache_data(ttl=3600)
def fetch_all_fpl_data(league_id):
    headers = {"User-Agent": "Mozilla/5.0"}
    # 1. 獲取聯賽成員
    league_url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    r = requests.get(league_url, headers=headers).json()
    members = [p for p in r['standings']['results'] if p['player_name'] != IGNORE_PLAYER]
    
    # 2. 獲取每位成員的歷史得分
    all_history = []
    for m in members:
        h_url = f"https://fantasy.premierleague.com/api/entry/{m['entry']}/history/"
        h_data = requests.get(h_url, headers=headers).json()['current']
        for gw in h_data:
            all_history.append({
                "GW": gw['event'],
                "經理人": m['player_name'],
                "累積總分": gw['total_points'],
                "當週得分": gw['points']
            })
    return pd.DataFrame(all_history)

try:
    df = fetch_all_fpl_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    remaining_gws = 38 - max_gw

    # --- 核心計算：輸贏積分 (Net Score * 2) ---
    def calculate_net_points(group):
        n = len(group)
        total_sum = group['累積總分'].sum()
        group['輸贏積分'] = (group['累積總分'] * (n - 1) - (total_sum - group['累積總分'])) * 2
        return group
    
    df = df.groupby('GW', group_keys=False).apply(calculate_net_points)

    # --- 統計學預測：GW38 EV & Range ---
    prediction_results = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        current_total = m_df['累積總分'].iloc[-1]
        
        # 近 5 週加權平均 (WMA)
        recent_scores = m_history = m_df.tail(5)['當週得分']
        weights = np.arange(1, len(recent_scores) + 1)
        wma_avg = np.average(recent_scores, weights=weights)
        
        # GW38 期望值 (EV)
        ev_final = current_total + (wma_avg * remaining_gws)
        
        # 波動區間計算 (標準差)
        std_dev = m_df['當週得分'].std()
        # 95% 信賴區間: 1.96 * sigma * sqrt(t)
        interval = 1.96 * std_dev * np.sqrt(remaining_gws) if remaining_gws > 0 else 0
        
        prediction_results.append({
            "經理人": manager,
            "目前總分": int(current_total),
            "目前輸贏": int(m_df['輸贏積分'].iloc[-1]),
            "GW38_EV": int(ev_final),
            "預測下限": int(ev_final - interval),
            "預測上限": int(ev_final + interval),
            "穩定度(σ)": round(std_dev, 1)
        })

    pred_df = pd.DataFrame(prediction_results)
    
    # 預計 GW38 輸贏平衡計算
    n_p = len(pred_df)
    total_ev = pred_df['GW38_EV'].sum()
    pred_df['預測GW38輸贏'] = (pred_df['GW38_EV'] * (n_p - 1) - (total_ev - pred_df['GW38_EV'])) * 2
    pred_df['預測GW38輸贏'] = pred_df['預測GW38輸贏'].astype(int)

    # --- APP 介面佈局 ---
    st.title("📊 FPL 聯賽專業決算分析")
    
    # 頂部數據指標 (iPhone 2x2 佈局)
    m1, m2 = st.columns(2)
    with m1:
        st.metric("目前榜首", df[df['GW']==max_gw].sort_values('累積總分').iloc[-1]['經理人'])
    with m2:
        top_pred = pred_df.loc[pred_df['預測GW38輸贏'].idxmax()]
        st.metric("預測季末贏家", top_pred['經理人'], f"預計 {top_pred['預測GW38輸贏']} pts")

    # 1. 核心結算表
    st.subheader(f"🏆 聯賽即時決算 (GW {max_gw})")
    main_table = pred_df[['經理人', '目前總分', '目前輸贏', '預測GW38輸贏']].sort_values('目前總分', ascending=False)
    
    def highlight_gl(val):
        color = '#2ecc71' if val > 0 else '#e74c3c'
        return f'color: {color}; font-weight: bold'
    
    st.dataframe(main_table.style.applymap(highlight_gl, subset=['目前輸贏', '預測GW38輸贏']), use_container_width=True, hide_index=True)

    # 2. 預測區間圖 (Range Visualization)
    st.markdown("---")
    st.subheader("🔮 GW38 期望值與 95% 波動範圍")
    st.write("橫條代表數學預估的最終分數範圍，點為期望值 (EV)。範圍重疊代表排名仍有變動可能。")
    # iPhone 優化：使用 DataFrame 表達範圍，因手機繪製複雜圖表易跑位
    range_view = pred_df[['經理人', '預測下限', 'GW38_EV', '預測上限']].sort_values('GW38_EV', ascending=False)
    st.dataframe(range_view, use_container_width=True, hide_index=True)
    

    # 3. 歷史趨勢圖
    st.markdown("---")
    st.subheader("📈 聯賽輸贏積分趨勢曲線")
    trend_data = df.pivot(index='GW', columns='經理人', values='輸贏積分')
    st.line_chart(trend_data)
    

    # 4. 專業統計摘要
    st.markdown("---")
    st.subheader("🔬 專業統計摘要")
    s1, s2 = st.columns(2)
    with s1:
        st.write("**🎯 穩定度領先者 (Low Vol)**")
        st.table(pred_df.sort_values('穩定度(σ)').head(3)[['經理人', '穩定度(σ)']])
    with s2:
        st.write("**🚀 高潛力黑馬 (EV 增幅)**")
        pred_df['成長潛力'] = pred_df['GW38_EV'] - pred_df['目前總分']
        st.table(pred_df.sort_values('成長潛力', ascending=False).head(3)[['經理人', 'GW38_EV']])

    # 5. 說明文檔
    with st.expander("📖 統計模型與計算說明"):
        st.markdown(f"""
        - **核心公式**：採計當前累積總分，計算每位玩家與聯賽其他成員的積分差額總和後乘與 2 ($Net Score \\times 2$)。
        - **期望值 (EV)**：結合當前得分與**加權移動平均 (WMA)**。近期 5 週的表現權重更高，用以捕捉當前競技狀態。
        - **信賴區間 (Range)**：基於歷史得分標準差 $\\sigma$，考慮剩餘週數 $t$ 的隨機性。
        - **預測平衡**：所有玩家的季末預測總分會重新進行聯賽平衡計算，得出最終輸贏積分預測。
        """)

except Exception as e:
    st.error(f"數據加載錯誤: {e}")
    st.info("提示：請確保您的網路環境可以訪問 FPL API。")

st.caption(f"數據自動排除：{IGNORE_PLAYER} | 已針對 iOS/Android 顯示優化")
