import streamlit as st
import pandas as pd
import requests
import numpy as np

st.set_page_config(page_title="FPL 聯賽數據終端", layout="wide")

# 常數設定
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

# --- 1. API 數據獲取 ---
@st.cache_data(ttl=3600)
def get_league_members(league_id):
    url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return [p for p in r.json()['standings']['results'] if p['player_name'] != IGNORE_PLAYER]

@st.cache_data(ttl=3600)
def get_history_data(entry_id):
    url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return r.json()['current']

# --- 2. 數據核心計算 ---
st.title("📊 FPL 聯賽決算預測終端")

try:
    members = get_league_members(LEAGUE_ID)
    
    with st.spinner("正在執行數據建模與趨勢預估..."):
        all_data = []
        for m in members:
            history = get_history_data(m['entry'])
            for h in history:
                all_data.append({
                    "週數": h['event'],
                    "經理人": m['player_name'],
                    "目前總分": h['total_points'],
                    "當週得分": h['points']
                })

        full_df = pd.DataFrame(all_data)

        # 核心邏輯函數：計算 Net Score * 2
        def calculate_gl(group):
            n = len(group)
            total_pts = group['目前總分'].sum()
            # 公式: (個人分 * (n-1) - 其他人總分和) * 2
            group['輸贏積分'] = group['目前總分'].apply(lambda x: (x * (n - 1)) - (total_pts - x)) * 2
            return group

        full_df = full_df.groupby('週數', group_keys=False).apply(calculate_gl)
        max_gw = full_df['週數'].max()
        
        # --- 預測邏輯 (GW 38) ---
        prediction_list = []
        current_gw_data = full_df[full_df['週數'] == max_gw]
        
        for manager in members:
            m_name = manager['player_name']
            m_history = full_df[full_df['經理人'] == m_name].sort_values('週數')
            
            # 趨勢分析：近 5 週平均表現
            recent_performance = m_history.tail(5)['當週得分'].mean()
            remaining_weeks = 38 - max_gw
            
            # 預測 GW38 總得分
            pred_total_points = m_history['目前總分'].iloc[-1] + (recent_performance * remaining_weeks)
            prediction_list.append({"經理人": m_name, "預測總分": pred_total_points})
        
        pred_df = pd.DataFrame(prediction_list)
        n_players = len(pred_df)
        total_pred_pts = pred_df['預測總分'].sum()
        
        # 計算預測的輸贏積分
        pred_df['預測GW38輸贏'] = pred_df['預測總分'].apply(lambda x: (x * (n_players - 1)) - (total_pred_pts - x)) * 2

    # --- 3. 頂部看板 (Highlight Cards) ---
    st.subheader("💡 核心數據摘要")
    
    # 找出目前表現最好與預測最好的人
    top_current = current_gw_data.loc[current_gw_data['輸贏積分'].idxmax()]
    top_predicted = pred_df.loc[pred_df['預測GW38輸贏'].idxmax()]

    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("當前最高輸贏", f"{int(top_current['輸贏積分'])} pts", f"由 {top_current['經理人']}")
    
    with col2:
        st.metric("預測賽季末最高輸贏", f"{int(top_predicted['預測GW38輸贏'])} pts", f"由 {top_predicted['經理人']}")

    with col3:
        avg_gl = current_gw_data['輸贏積分'].abs().mean()
        st.metric("聯賽平均波動", f"±{int(avg_gl)}")

    with col4:
        st.metric("剩餘賽事週數", f"{38 - max_gw} 週")

    # --- 4. 詳細數據表格 ---
    st.markdown("---")
    # 合併數據以便顯示
    display_df = current_gw_data[['經理人', '目前總分', '輸贏積分']].merge(
        pred_df[['經理人', '預測GW38輸贏']], on='經理人'
    ).sort_values('目前總分', ascending=False)

    st.header(f"🏆 積分結算與賽季末預測 (GW {max_gw})")
    
    def color_gl(val):
        color = '#2ecc71' if val > 0 else '#e74c3c' if val < 0 else '#95a5a6'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        display_df.style.applymap(color_gl, subset=['輸贏積分', '預測GW38輸贏']),
        use_container_width=True,
        hide_index=True
    )

    # --- 5. 趨勢圖表 ---
    st.markdown("---")
    st.header("📈 輸贏積分歷史趨勢")
    chart_data = full_df.pivot(index='週數', columns='經理人', values='輸贏積分')
    st.line_chart(chart_data)

except Exception as e:
    st.error(f"應用程式運行錯誤: {e}")

st.caption(f"數據更新頻率：每小時。預估模型基於玩家近 5 週平均表現。已自動剔除玩家：{IGNORE_PLAYER}。")
