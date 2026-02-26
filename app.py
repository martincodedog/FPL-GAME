import streamlit as st
import pandas as pd
import requests
import numpy as np

# 針對 iPhone 優化佈局
st.set_page_config(page_title="FPL 數據終端", layout="wide", initial_sidebar_state="collapsed")

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
st.title("📊 FPL 聯賽決算預測")

try:
    members = get_league_members(LEAGUE_ID)
    
    with st.spinner("系統正在計算..."):
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

        # 輸贏積分核心邏輯 (Net Score * 2)
        def calculate_gl(group):
            n = len(group)
            total_pts = group['目前總分'].sum()
            group['輸贏積分'] = (group['目前總分'] * (n - 1) - (total_pts - group['目前總分'])) * 2
            return group

        full_df = full_df.groupby('週數', group_keys=False).apply(calculate_gl)
        max_gw = full_df['週數'].max()
        
        # --- 預測邏輯計算 ---
        prediction_list = []
        current_gw_data = full_df[full_df['週數'] == max_gw]
        
        for m_name in full_df['經理人'].unique():
            m_history = full_df[full_df['經理人'] == m_name].sort_values('週數')
            recent_avg = m_history.tail(5)['當週得分'].mean()
            remaining_wks = 38 - max_gw
            
            pred_total_points = m_history['目前總分'].iloc[-1] + (recent_avg * remaining_wks)
            prediction_list.append({
                "經理人": m_name, 
                "預測總分": int(pred_total_points),
                "近期均分": int(recent_avg),
                "總分標準差": int(m_history['當週得分'].std())
            })
        
        pred_df = pd.DataFrame(prediction_list)
        n_players = len(pred_df)
        total_pred_pts = pred_df['預測總分'].sum()
        
        # 計算預測的輸贏積分 (GW38)
        pred_df['預測GW38輸贏'] = (pred_df['預測總分'] * (n_players - 1) - (total_pred_pts - pred_df['預測總分'])) * 2
        pred_df['預測GW38輸贏'] = pred_df['預測GW38輸贏'].astype(int)

    # --- 3. 頂部看板 (iPhone 優化：使用 2x2 佈局) ---
    top_current = current_gw_data.loc[current_gw_data['輸贏積分'].idxmax()]
    top_predicted = pred_df.loc[pred_df['預測GW38輸贏'].idxmax()]

    # 在手機上，4 欄會太擠，改為兩組兩欄
    r1_col1, r1_col2 = st.columns(2)
    r1_col1.metric("當前最高輸贏", f"{int(top_current['輸贏積分'])}")
    r1_col2.metric("預測最高輸贏", f"{int(top_predicted['預測GW38輸贏'])}")

    r2_col1, r2_col2 = st.columns(2)
    r2_col1.metric("聯賽波動", f"±{int(current_gw_data['輸贏積分'].abs().mean())}")
    r2_col2.metric("剩餘週數", f"{38 - max_gw}")

    # --- 4. 預測模型說明 (修正 LaTeX 錯誤) ---
    with st.expander("📝 查看預測模型計算說明"):
        # 這裡將中文字移出 $ 符號，避免 name error
        st.write(f"**1. 數據基準**：以目前第 {max_gw} 週總分為準。")
        st.write(f"**2. 近期趨勢**：採計最近 5 週平均得分。")
        st.latex(r"Total_{pred} = Total_{current} + (Avg_{recent} \times Weeks_{left})")

    # --- 5. 詳細數據表格 ---
    st.markdown("---")
    display_df = current_gw_data[['經理人', '目前總分', '輸贏積分']].merge(
        pred_df[['經理人', '預測GW38輸贏', '近期均分']], on='經理人'
    ).sort_values('目前總分', ascending=False)
    
    display_df['輸贏積分'] = display_df['輸贏積分'].astype(int)

    st.subheader(f"🏆 積分結算 (GW {max_gw})")
    
    def color_gl(val):
        color = '#2ecc71' if val > 0 else '#e74c3c' if val < 0 else '#95a5a6'
        return f'color: {color}; font-weight: bold'

    # iPhone 優化：隱藏不必要的欄位減少捲動
    st.dataframe(
        display_df.style.applymap(color_gl, subset=['輸贏積分', '預測GW38輸贏']),
        use_container_width=True, hide_index=True
    )

    # --- 6. 趨勢圖表 ---
    st.markdown("---")
    st.subheader("📈 輸贏趨勢圖")
    chart_data = full_df.pivot(index='週數', columns='經理人', values='輸贏積分')
    st.line_chart(chart_data)

    # --- 7. 專業統計摘要 ---
    st.markdown("---")
    st.subheader("📊 專業統計摘要")
    
    # 手機上改用垂直排列
    st.write("🎯 **穩定度領先** (波動率最小):")
    low_vol = pred_df.sort_values("總分標準差").iloc[0]
    st.write(f"- {low_vol['經理人']} (±{low_vol['總分標準差']} pts)")

    st.write("🚀 **潛力黑馬** (預計成長最多):")
    current_gl_map = current_gw_data.set_index('經理人')['輸贏積分']
    pred_df['成長幅度'] = pred_df['預測GW38輸贏'] - pred_df['經理人'].map(current_gl_map)
    high_pot = pred_df.sort_values("成長幅度", ascending=False).iloc[0]
    st.write(f"- {high_pot['經理人']} (+{int(high_pot['成長幅度'])} pts)")

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

st.caption(f"App Optimized for iOS/Android | Powered by Gemini")
