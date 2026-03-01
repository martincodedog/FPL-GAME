import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化
st.set_page_config(page_title="FPL Quant PRO", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    .player-card {
        background-color: #ffffff;
        padding: 24px;
        border-radius: 18px;
        border-left: 10px solid #3498db;
        margin-bottom: 25px;
        box-shadow: 0 8px 16px rgba(0,0,0,0.1);
    }
    .val-large { font-size: 36px !important; font-weight: 900; color: #2c3e50; line-height: 1.1; }
    .val-sub { font-size: 20px !important; font-weight: 800; }
    .label-mini { color: #7f8c8d; font-size: 14px; text-transform: uppercase; font-weight: 600; }
    .rank-badge { background-color: #2c3e50; color: white; padding: 4px 10px; border-radius: 6px; font-size: 14px; margin-right: 10px; vertical-align: middle; }
    .up { color: #27ae60; }
    .down { color: #e74c3c; }
    .footer-spacer { height: 120px; }
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

    # 1. 計算全賽季目前的 Net Score
    def calc_net_full(group):
        n = len(group)
        total_sum = group['總分'].sum()
        group['目前輸贏'] = (group['總分'] * (n - 1) - (total_sum - group['總分'])) * 2
        return group
    full_processed_df = all_df.groupby('GW', group_keys=False).apply(calc_net_full)

    # 2. UI 容器
    st.title("🏛️ FPL 量化博弈終端")
    card_placeholder = st.container()
    st.markdown("---")
    
    # 底部滑桿
    st.markdown('<div class="footer-spacer"></div>', unsafe_allow_html=True)
    selected_gw = st.select_slider("📅 選擇 Game Week", options=list(range(1, int(latest_gw) + 1)), value=int(latest_gw))

    # 3. 數據計算
    df_filtered = full_processed_df[full_processed_df['GW'] <= selected_gw].copy()
    num_players = len(df_filtered['經理人'].unique())
    
    stats_list = []
    for manager in df_filtered['經理人'].unique():
        m_df = df_filtered[df_filtered['經理人'] == manager].sort_values('GW')
        curr_row = m_df.iloc[-1]
        prev_net = m_df['目前輸贏'].iloc[-2] if len(m_df) > 1 else 0
        net_change = curr_row['目前輸贏'] - prev_net
        
        pts_recent = m_df['當週分'].tail(5)
        wma = np.average(pts_recent, weights=np.arange(1, len(pts_recent) + 1))
        pred_total_38 = curr_row['總分'] + (wma * (38 - selected_gw))
        
        stats_list.append({
            "經理人": manager,
            "目前輸贏": int(curr_row['目前輸贏']),
            "This GW": int(curr_row['當週分']),
            "Net Chg": int(net_change),
            "Pred Total 38": pred_total_38
        })

    res_df = pd.DataFrame(stats_list)
    total_pred = res_df['Pred Total 38'].sum()
    res_df['GW38 Pred Net'] = ((res_df['Pred Total 38'] * (num_players - 1) - (total_pred - res_df['Pred Total 38'])) * 2).astype(int)
    
    # 按照目前輸贏排序
    res_df = res_df.sort_values('目前輸贏', ascending=False).reset_index(drop=True)

    with card_placeholder:
        st.subheader(f"🏆 經理人排名 (GW {selected_gw})")
        for idx, row in res_df.iterrows():
            color_cls = "up" if row['Net Chg'] >= 0 else "down"
            sign = "+" if row['Net Chg'] >= 0 else ""
            
            # 使用 f-string 並確保 HTML 標籤連續，避免 Markdown 解析錯誤
            card_html = f"""
            <div class="player-card">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div><span class="rank-badge">#{idx+1}</span><span style="font-size: 22px; font-weight: 800;">{row['經理人']}</span></div>
                    <div class="{color_cls}" style="text-align: right;">
                        <span class="val-sub">{sign}{row['Net Chg']}</span><br>
                        <span style="font-size: 11px; color: gray;">Net score change</span>
                    </div>
                </div>
                <div style="margin: 20px 0;">
                    <span class="label-mini">目前輸贏 (Current Net)</span><br>
                    <span class="val-large">{row['目前輸贏']} <small style="font-size:16px; color:gray;">PTS</small></span>
                </div>
                <div style="display: flex; justify-content: space-between; border-top: 2px solid #f8f9fa; padding-top: 15px;">
                    <div>
                        <span class="label-mini">This GW Score</span><br>
                        <span style="font-size: 24px; font-weight: 800; color: #3498db;">{row['This GW']}</span>
                    </div>
                    <div style="text-align: right;">
                        <span class="label-mini">GW38 Predicted Net</span><br>
                        <span style="font-size: 24px; font-weight: 800; color: #2c3e50;">{row['GW38 Pred Net']}</span>
                    </div>
                </div>
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)

    # 矩陣與圖表
    st.subheader("📊 決算矩陣 (Settlement Matrix)")
    st.dataframe(res_df.set_index('經理人').T, use_container_width=True)
    
    st.subheader("📈 輸贏趨勢追蹤")
    st.line_chart(full_processed_df.pivot(index='GW', columns='經理人', values='目前輸贏'))
    

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

st.caption(f"FPL Quant Terminal | Rank based on Net Score | Predict model: WMA(5)")
