import streamlit as st
import pandas as pd
import requests
import numpy as np
import scipy.stats as stats

# iPhone 行動端優化設定
st.set_page_config(page_title="FPL 數據終端", layout="wide", initial_sidebar_state="collapsed")

# 自定義 CSS 讓 iPhone 顯示更美觀
st.markdown("""
    <style>
    .main { background-color: #f5f7f9; }
    .stMetric { background-color: #ffffff; padding: 10px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    [data-testid="stMetricValue"] { font-size: 24px !important; }
    </style>
    """, unsafe_allow_html=True)

# 常數
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

@st.cache_data(ttl=3600)
def get_fpl_data(league_id):
    headers = {"User-Agent": "Mozilla/5.0"}
    # 獲取成員
    league_url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    r = requests.get(league_url, headers=headers).json()
    members = [p for p in r['standings']['results'] if p['player_name'] != IGNORE_PLAYER]
    
    all_rows = []
    for m in members:
        h_url = f"https://fantasy.premierleague.com/api/entry/{m['entry']}/history/"
        h = requests.get(h_url, headers=headers).json()['current']
        for gw in h:
            all_rows.append({
                "GW": gw['event'],
                "經理人": m['player_name'],
                "總分": gw['total_points'],
                "當週分": gw['points']
            })
    return pd.DataFrame(all_rows)

try:
    df = get_fpl_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    remaining = 38 - max_gw

    # --- 1. 核心輸贏計算 (Net Score * 2) ---
    def calc_gl(group):
        n = len(group)
        total = group['總分'].sum()
        group['輸贏積分'] = (group['總分'] * (n - 1) - (total - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # --- 2. 統計學 GW38 預測 (EV & Range) ---
    predict_stats = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        current_pts = m_df['總分'].iloc[-1]
        
        # 算出近期加權平均 (近期週數權重更高)
        weights = np.arange(1, len(m_df) + 1)
        wma_pts = np.average(m_df['當週分'], weights=weights)
        
        # 期望值 (EV)
        ev_final = current_pts + (wma_pts * remaining)
        
        # 計算波動區間 (使用標準差)
        std_dev = m_df['當週分'].std()
        # 95% 信賴區間公式: 1.96 * std * sqrt(剩餘週數)
        margin = 1.96 * std_dev * np.sqrt(remaining) if remaining > 0 else 0
        
        predict_stats.append({
            "經理人": manager,
            "當前總分": current_pts,
            "當前輸贏": int(m_df['輸贏積分'].iloc[-1]),
            "GW38_EV": int(ev_final),
            "最低預期": int(ev_final - margin),
            "最高預期": int(ev_final + margin),
            "穩定度": round(std_dev, 1)
        })

    pred_df = pd.DataFrame(predict_stats)
    
    # 重新平衡預測的輸贏積分
    n_p = len(pred_df)
    total_ev = pred_df['GW38_EV'].sum()
    pred_df['預測GW38輸贏'] = (pred_df['GW38_EV'] * (n_p - 1) - (total_ev - pred_df['GW38_EV'])) * 2
    pred_df['預測GW38輸贏'] = pred_df['預測GW38輸贏'].astype(int)

    # --- UI 顯示 ---
    st.title("⚽ FPL 專業統計數據終端")
    
    # iPhone 頂部卡片
    c1, c2 = st.columns(2)
    top_m = pred_df.loc[pred_df['預測GW38輸贏'].idxmax()]
    c1.metric("當前榜首", df[df['GW']==max_gw].sort_values('總分').iloc[-1]['經理人'])
    c2.metric("預計季末贏家", top_m['經理人'], f"{top_m['預測GW38輸贏']} pts")

    st.markdown("---")
    
    # 1. 核心決算表
    st.subheader(f"🏆 聯賽決算表 (GW {max_gw})")
    display_tab = pred_df[['經理人', '當前總分', '當前輸贏', '預測GW38輸贏']].sort_values('當前總分', ascending=False)
    
    def color_gl(val):
        return f'color: {"#2ecc71" if val > 0 else "#e74c3c"}; font-weight: bold'
    st.dataframe(display_tab.style.applymap(color_gl, subset=['當前輸贏', '預測GW38輸贏']), use_container_width=True, hide_index=True)

    # 2. 預測區間圖 (Range Plot)
    st.markdown("---")
    st.subheader("🔮 GW38 總分期望值與波動區間")
    st.write("橫條代表 95% 概率下的最終分數範圍，點為期望值 (EV)。")
    # 使用 st.bar_chart 模擬區間或直接用 dataframe 展示
    st.dataframe(pred_df[['經理人', '最低預期', 'GW38_EV', '最高預期']].sort_values('GW38_EV', ascending=False), use_container_width=True)

    # 3. 專業趨勢圖
    st.markdown("---")
    st.subheader("📈 全賽季輸贏積分曲線")
    chart_data = df.pivot(index='GW', columns='經理人', values='輸贏積分')
    st.line_chart(chart_data)

    # 4. 統計學摘要
    st.markdown("---")
    st.subheader("📊 專業統計摘要 (Summary Stats)")
    col_a, col_b = st.columns(2)
    
    with col_a:
        st.write("**🎯 穩定性指標 (低波動)**")
        st.table(pred_df.sort_values('穩定度').head(3)[['經理人', '穩定度']])
        
    with col_b:
        st.write("**🔥 近期動能 (WMA 領先)**")
        # 計算 WMA 與 賽季平均的差值
        st.table(pred_df.sort_values('GW38_EV', ascending=False).head(3)[['經理人', 'GW38_EV']])

    # 預測邏輯說明
    with st.expander("📖 統計模型說明 (Markdown)"):
        st.markdown(f"""
        1. **加權移動平均 (WMA)**: 我們對最近的 GW 給予更高的權重，公式為 $\\sum (Score_i \\times w_i) / \\sum w_i$。
        2. **信賴區間 (Range)**: 基於玩家歷史得分標準差 $\\sigma$，預測區間隨時間 $\\sqrt{{t}}$ 擴大。
        3. **EV 輸贏**: 將所有玩家預測總分放入 $Net Score \\times 2$ 公式中重新平衡。
        """)

except Exception as e:
    st.error(f"數據加載失敗: {e}")
