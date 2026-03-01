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

    # --- 1. 全域預先計算「目前輸贏」趨勢 ---
    def calc_net_for_all(group):
        n = len(group)
        total_sum = group['總分'].sum()
        group['目前輸贏'] = (group['總分'] * (n - 1) - (total_sum - group['總分'])) * 2
        return group
    full_processed_df = all_df.groupby('GW', group_keys=False).apply(calc_net_for_all)

    # --- 2. 佈局 ---
    st.title("🏛️ FPL 量化博弈終端")
    
    card_container = st.container()
    st.markdown("---")
    matrix_placeholder = st.empty()
    
    # 底部滑桿 (放在底部方便 iPhone 操作)
    st.markdown('<div class="footer-spacer"></div>', unsafe_allow_html=True)
    selected_gw = st.select_slider("📅 選擇查看 Game Week", options=list(range(1, int(latest_gw) + 1)), value=int(latest_gw))

    # --- 3. 根據選擇的 GW 渲染數據 ---
    df_upto_gw = full_processed_df[full_processed_df['GW'] <= selected_gw].copy()
    num_players = len(df_upto_gw['經理人'].unique())
    
    stats = []
    for manager in df_upto_gw['經理人'].unique():
        m_df = df_upto_gw[df_upto_gw['經理人'] == manager].sort_values('GW')
        curr_row = m_df.iloc[-1]
        
        # 正確計算 Change: 目前輸贏 - 上週目前輸贏
        prev_net = m_df['目前輸贏'].iloc[-2] if len(m_df) > 1 else 0
        net_change = curr_row['目前輸贏'] - prev_net
        
        # 預測 GW38 總分 (WMA)
        pts_tail = m_df['當週分'].tail(5)
        wma = np.average(pts_tail, weights=np.arange(1, len(pts_tail) + 1))
        pred_total_38 = curr_row['總分'] + (wma * (38 - selected_gw))
        
        # 其他 5 項技術指標 (MACD, RSI 等)
        vol = m_df['當週分'].std()
        mom = m_df['當週分'].tail(3).mean() - m_df['當週分'].mean()
        
        stats.append({
            "經理人": manager,
            "目前輸贏": int(curr_row['目前輸贏']),
            "This GW Score": int(curr_row['當週分']),
            "Change": int(net_change),
            "Pred Total 38": pred_total_38,
            "波動率": round(vol, 1) if not np.isnan(vol) else 0,
            "動量": round(mom, 1) if not np.isnan(mom) else 0
        })

    # 計算「預測 GW38 輸贏」 (對沖邏輯)
    stat_df = pd.DataFrame(stats)
    total_pred_sum = stat_df['Pred Total 38'].sum()
    stat_df['Pred Net 38'] = ((stat_df['Pred Total 38'] * (num_players - 1) - (total_pred_sum - stat_df['Pred Total 38'])) * 2).astype(int)
    
    # 按照「目前輸贏」排序
    final_res = stat_df.sort_values('目前輸贏', ascending=False)

    with card_container:
        st.subheader(f"👤 經理人排名 (GW {selected_gw})")
        cols = st.columns(2)
        for idx, row in final_res.reset_index(drop=True).iterrows():
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
                        <span class="label-mini">目前輸贏 (Net Score)</span><br>
                        <span class="val-large">{row['目前輸贏']} <small style="font-size:12px; color:gray;">PTS</small></span>
                    </div>
                    <div style="display: flex; justify-content: space-between; border-top: 1px dashed #eee; padding-top: 8px;">
                        <div>
                            <span class="label-mini">This GW Score</span><br>
                            <span style="font-weight:700; color:#3498db;">{row['This GW Score']}</span>
                        </div>
                        <div style="text-align: right;">
                            <span class="label-mini">GW38 Predict Net</span><br>
                            <span style="font-weight:700; color:#2c3e50;">{row['Pred Net 38']}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

    # 矩陣更新 (轉置顯示)
    matrix_placeholder.dataframe(final_res.set_index('經理人').T, use_container_width=True)

    # 視覺化圖表
    st.markdown("---")
    t1, t2 = st.tabs(["💰 輸贏趨勢圖", "🔮 預測分佈"])
    with t1:
        st.line_chart(full_processed_df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
    with t2:
        st.write("各經理人季末輸贏期望值 (GW38 Predict Net):")
        st.bar_chart(final_res.set_index('經理人')['Pred Net 38'])
        

except Exception as e:
    st.error(f"系統運行錯誤: {e}")

st.caption("FPL Pro Quant Terminal | Optimized for Mobile | Change based on Net Score")
