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
    .player-card {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 12px;
        border-left: 6px solid #3498db;
        margin-bottom: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.07);
    }
    .val-large { font-size: 22px; font-weight: 800; color: #2c3e50; }
    .val-sub { font-size: 14px; font-weight: 600; }
    .label-mini { color: #7f8c8d; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }
    .up { color: #27ae60; }
    .down { color: #e74c3c; }
    .footer-spacer { height: 80px; }
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
    all_df = fetch_data(LEAGUE_ID)
    latest_gw = all_df['GW'].max()

    # --- 1. 全域計算函數 ---
    def process_data_for_gw(target_gw):
        df_gw = all_df[all_df['GW'] <= target_gw].copy()
        n = len(df_gw['經理人'].unique())
        
        # 計算目前輸贏 (Net Score * 2)
        def calc_net(group):
            total_sum = group['總分'].sum()
            group['目前輸贏'] = (group['總分'] * (n - 1) - (total_sum - group['總分'])) * 2
            return group
        df_gw = df_gw.groupby('GW', group_keys=False).apply(calc_net)
        
        # 準備預測數據 (WMA)
        stats = []
        for manager in df_gw['經理人'].unique():
            m_df = df_gw[df_gw['經理人'] == manager].sort_values('GW')
            curr_row = m_df.iloc[-1]
            prev_net = m_history['目前輸贏'].iloc[-2] if len(m_df) > 1 else 0
            
            # 預測 GW38 總分 (WMA)
            pts_tail = m_df['當週分'].tail(5)
            wma = np.average(pts_tail, weights=np.arange(1, len(pts_tail) + 1))
            pred_total_38 = curr_row['總分'] + (wma * (38 - target_gw))
            
            # 指標計算
            vol = m_df['當週分'].std()
            mom = m_df['當週分'].tail(3).mean() - m_df['當週分'].mean()
            
            stats.append({
                "經理人": manager,
                "目前輸贏": int(curr_row['目前輸贏']),
                "This GW Score": int(curr_row['當週分']),
                "Change": int(curr_row['目前輸贏'] - prev_net),
                "Pred Total 38": pred_total_38,
                "波動率": round(vol, 1) if not np.isnan(vol) else 0,
                "動量": round(mom, 1) if not np.isnan(mom) else 0
            })
        
        # 計算「預測 GW38 輸贏」 (基於預測總分重新對沖)
        stat_df = pd.DataFrame(stats)
        total_pred_sum = stat_df['Pred Total 38'].sum()
        stat_df['Pred Net 38'] = ((stat_df['Pred Total 38'] * (n - 1) - (total_pred_sum - stat_df['Pred Total 38'])) * 2).astype(int)
        
        return stat_df.sort_values('目前輸贏', ascending=False)

    # --- 2. 佈局 ---
    st.title("🏛️ FPL 量化博弈終端")
    
    # Placeholder 用於連動 Slider
    card_container = st.container()
    st.markdown("---")
    matrix_placeholder = st.empty()
    
    # 底部滑桿
    st.markdown('<div class="footer-spacer"></div>', unsafe_allow_html=True)
    selected_gw = st.select_slider("📅 選擇查看 Game Week", options=list(range(1, int(latest_gw) + 1)), value=int(latest_gw))

    # --- 3. 渲染數據 ---
    final_res = process_data_for_gw(selected_gw)

    with card_container:
        st.subheader(f"👤 經理人排名 (按目前輸贏)")
        cols = st.columns(2)
        for idx, row in final_res.iterrows():
            chg_cls = "up" if row['Change'] >= 0 else "down"
            chg_sign = "+" if row['Change'] >= 0 else ""
            
            with cols[idx % 2]:
                st.markdown(f"""
                <div class="player-card">
                    <div style="display: flex; justify-content: space-between;">
                        <span class="label-mini">{row['經理人']}</span>
                        <span class="val-sub {chg_cls}">{chg_sign}{row['Change']}</span>
                    </div>
                    <div style="margin: 10px 0;">
                        <span class="label-mini">目前輸贏</span><br>
                        <span class="val-large">{row['目前輸贏']} <small style="font-size:12px; color:gray;">PTS</small></span>
                    </div>
                    <div style="display: flex; justify-content: space-between; border-top: 1px dashed #eee; pt: 8px;">
                        <div>
                            <span class="label-mini">This GW</span><br>
                            <span style="font-weight:700; color:#3498db;">{row['This GW Score']}</span>
                        </div>
                        <div style="text-align: right;">
                            <span class="label-mini">GW38 Predict Net</span><br>
                            <span style="font-weight:700; color:#2c3e50;">{row['Pred Net 38']}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # 矩陣更新
    matrix_placeholder.dataframe(final_res.set_index('經理人').T, use_container_width=True)

    # 技術指標解析
    with st.expander("📖 指標說明 (Glossary)"):
        st.markdown("""
        - **目前輸贏**: 基於當前總積分的全聯賽對沖結果 `(個人總分 - 聯賽均分) * 2`。
        - **Change**: 本週「目前輸贏」與上週的差值。
        - **GW38 Predict Net**: 根據 WMA 預測第 38 週總積分後，重新進行全聯賽對沖計算出的預期最終輸贏。
        """)

except Exception as e:
    st.error(f"系統錯誤: {e}")
