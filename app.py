import streamlit as st
import pandas as pd
import requests
import numpy as np

st.set_page_config(page_title="FPL 數據決算終端", layout="wide")

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
    
    with st.spinner("系統正在執行數據建模與趨勢預估..."):
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
            # 公式: (個人分 * (n-1) - 其他人總分和) * 2
            group['輸贏積分'] = (group['目前總分'] * (n - 1) - (total_pts - group['目前總分'])) * 2
            return group

        full_df = full_df.groupby('週數', group_keys=False).apply(calculate_gl)
        max_gw = full_df['週數'].max()
        
        # --- 預測邏輯計算 ---
        prediction_list = []
        current_gw_data = full_df[full_df['週數'] == max_gw]
        
        for m_name in full_df['經理人'].unique():
            m_history = full_df[full_df['經理人'] == m_name].sort_values('週數')
            
            # 趨勢分析：近 5 週平均表現
            recent_avg = m_history.tail(5)['當週得分'].mean()
            remaining_weeks = 38 - max_gw
            
            # 預測 GW38 總得分
            pred_total_points = m_history['目前總分'].iloc[-1] + (recent_avg * remaining_weeks)
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

    # --- 3. 頂部看板 (指標卡片) ---
    top_current = current_gw_data.loc[current_gw_data['輸贏積分'].idxmax()]
    top_predicted = pred_df.loc[pred_df['預測GW38輸贏'].idxmax()]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("當前最高輸贏", f"{int(top_current['輸贏積分'])} pts", f"由 {top_current['經理人']}")
    c2.metric("預測賽季末最高輸贏", f"{int(top_predicted['預測GW38輸贏'])} pts", f"由 {top_predicted['經理人']}")
    c3.metric("聯賽平均波動 (±)", f"{int(current_gw_data['輸贏積分'].abs().mean())}")
    c4.metric("剩餘賽事週數", f"{38 - max_gw}")

    # --- 4. 預測模型說明 (Markdown) ---
    with st.expander("📝 查看預測模型計算說明"):
        st.markdown(f"""
        ### 🔮 第 38 週預測模型算法
        本系統採用**動態加權趨勢法**進行賽季末預測，計算步驟如下：
        1. **數據基準**：以目前第 **{max_gw}** 週的累積總分為基礎。
        2. **近期趨勢**：計算每位玩家**最近 5 週 (GW {max_gw-4} - GW {max_gw})** 的平均得分。這能更準確反映玩家當前的球隊狀態（如轉會策略、傷病影響）。
        3. **推算公式**：
           $$預測總分 = 目前累積總分 + (近期 5 週平均分 \\times {38 - max_gw} \\text{ 剩餘週數})$$
        4. **輸贏積分重新平衡**：將所有玩家的預測總分放入聯賽池中，重新計算基於第 38 週預測總分的 **Net Score × 2**。
        """)

    # --- 5. 詳細數據表格 ---
    st.markdown("---")
    display_df = current_gw_data[['經理人', '目前總分', '輸贏積分']].merge(
        pred_df[['經理人', '預測GW38輸贏', '近期均分']], on='經理人'
    ).sort_values('目前總分', ascending=False)
    
    display_df['輸贏積分'] = display_df['輸贏積分'].astype(int)

    st.header(f"🏆 積分結算與預估 (截止至 GW {max_gw})")
    
    def color_gl(val):
        color = '#2ecc71' if val > 0 else '#e74c3c' if val < 0 else '#95a5a6'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        display_df.style.applymap(color_gl, subset=['輸贏積分', '預測GW38輸贏']),
        use_container_width=True, hide_index=True
    )

    # --- 6. 趨勢圖表 ---
    st.markdown("---")
    st.header("📈 聯賽輸贏積分趨勢圖")
    chart_data = full_df.pivot(index='週數', columns='經理人', values='輸贏積分')
    st.line_chart(chart_data)

    # --- 7. 專業統計摘要 (底欄) ---
    st.markdown("---")
    st.header("📊 專業統計摘要 (Professional Summary Statistics)")
    
    stats_cols = st.columns(3)
    
    with stats_cols[0]:
        st.subheader("📌 穩定度分析")
        # 分數標準差越小，越穩定
        consistency_df = pred_df.sort_values("總分標準差").head(3)
        st.write("聯賽最穩健經理人 (Top 3):")
        for i, row in consistency_df.iterrows():
            st.write(f"- **{row['經理人']}** (波動率: ±{row['總分標準差']})")

    with stats_cols[1]:
        st.subheader("⚡ 成長潛力")
        # 預測輸贏 vs 當前輸贏 差距最大的人
        current_gl_map = current_gw_data.set_index('經理人')['輸贏積分']
        pred_df['成長幅度'] = pred_df['預測GW38輸贏'] - pred_df['經理人'].map(current_gl_map)
        potential_df = pred_df.sort_values("成長幅度", ascending=False).head(3)
        st.write("看漲經理人 (預測季末噴發):")
        for i, row in potential_df.iterrows():
            st.write(f"- **{row['經理人']}** (預計成長: +{int(row['成長幅度'])} pts)")

    with stats_cols[2]:
        st.subheader("📉 風險預警")
        # 預測輸贏大幅下降的人
        risk_df = pred_df.sort_values("成長幅度", ascending=True).head(3)
        st.write("看跌經理人 (需注意近期頹勢):")
        for i, row in risk_df.iterrows():
            st.write(f"- **{row['經理人']}** (預計衰退: {int(row['成長幅度'])} pts)")

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

st.caption(f"數據源：FPL Official API | 已自動過濾非聯賽成員：{IGNORE_PLAYER}")
