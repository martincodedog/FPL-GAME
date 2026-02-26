import streamlit as st
import pandas as pd
import requests
import numpy as np

st.set_page_config(page_title="FPL 聯賽積分計算器", layout="wide")

# 常數設定
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

# --- 1. API 數據獲取函數 (保留原功能) ---
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

# --- 2. 數據處理與分析 ---
st.title("⚽ FPL 聯賽數據分析終端")

try:
    members = get_league_members(LEAGUE_ID)

    with st.spinner("正在分析全賽季數據及計算預測..."):
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

        # 計算淨分與輸贏邏輯: (個人總分 * (人數-1) - 其他人總分總和) * 2
        def calculate_metrics(group):
            n = len(group)
            total_pts = group['目前總分'].sum()
            group['輸贏積分'] = group['目前總分'].apply(lambda x: (x * (n - 1)) - (total_pts - x)) * 2
            return group

        full_df = full_df.groupby('週數', group_keys=False).apply(calculate_metrics)
        max_gw = full_df['週數'].max()

        # --- 3. 加入第 38 週預測邏輯 ---
        prediction_rows = []
        for manager in full_df['經理人'].unique():
            m_data = full_df[full_df['經理人'] == manager].sort_values('週數')
            
            # 穩定度分析 (標準差)
            volatility = m_data['當週得分'].std()
            
            # 預測邏輯：取最近 5 週平均分
            recent_avg = m_data.tail(5)['當週得分'].mean()
            remaining_gws = 38 - max_gw
            predicted_total = m_data['目前總分'].iloc[-1] + (recent_avg * remaining_gws)
            
            prediction_rows.append({
                "經理人": manager,
                "得分穩定度": round(volatility, 1),
                "近5週平均分": round(recent_avg, 1),
                "預測第38週總分": int(predicted_total)
            })
        
        stats_df = pd.DataFrame(prediction_rows)

    # --- 4. 介面佈局 ---
    
    # 頂部概覽
    st.subheader("📡 聯賽即時概況")
    k1, k2, k3 = st.columns(3)
    k1.metric("參賽人數", len(members))
    k2.metric("當前週數", f"GW {max_gw}")
    k3.metric("全聯賽平均得分", int(full_df[full_df['週數'] == max_gw]['目前總分'].mean()))

    # 當前排名表
    st.markdown("---")
    selected_gw = st.sidebar.select_slider("選擇查看週數：", options=sorted(full_df['週數'].unique().tolist()), value=max_gw)
    
    st.header(f"🏆 第 {selected_gw} 週積分結算")
    
    current_view = full_df[full_df['週數'] == selected_gw].merge(stats_df, on="經理人")
    current_view = current_view.sort_values("目前總分", ascending=False)
    
    # 數值顏色美化
    def color_values(val):
        if isinstance(val, (int, float)):
            color = '#2ecc71' if val > 0 else '#e74c3c' if val < 0 else '#95a5a6'
            return f'color: {color}; font-weight: bold'
        return ''

    st.dataframe(
        current_view[['經理人', '目前總分', '輸贏積分', '得分穩定度', '近5週平均分', '預測第38週總分']]
        .style.applymap(color_values, subset=['輸贏積分']),
        use_container_width=True, hide_index=True
    )

    # 預測排名區
    st.markdown("---")
    st.header("🔮 第 38 週最終排名預測")
    st.write("根據各玩家**最近 5 週的競技狀態**推算的賽季末預測總分。")
    
    pred_display = stats_df.sort_values("預測第38週總分", ascending=False).reset_index(drop=True)
    pred_display.index += 1
    st.table(pred_display[['經理人', '近5週平均分', '預測第38週總分']])

    # 趨勢圖
    st.markdown("---")
    st.header("📈 聯賽輸贏積分趨勢 (全賽季)")
    chart_data = full_df.pivot(index='週數', columns='經理人', values='輸贏積分')
    st.line_chart(chart_data)

except Exception as e:
    st.error(f"系統錯誤: {e}")

st.caption(f"註：所有計算已排除 {IGNORE_PLAYER}。預測僅供參考，不代表最終結果。")
