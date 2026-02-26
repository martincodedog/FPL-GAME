import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端深度優化：強制寬屏 + 隱藏側邊欄
st.set_page_config(page_title="FPL 量化終端 PRO", layout="wide", initial_sidebar_state="collapsed")

# 專業感 CSS
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetricValue"] { font-size: 20px !important; font-weight: bold; }
    .stDataFrame { border-radius: 12px; }
    .stAlert { border-radius: 10px; border: none; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    </style>
    """, unsafe_allow_html=True)

LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

@st.cache_data(ttl=3600)
def fetch_fpl_data(league_id):
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

def calculate_rsi(series, period=5):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    return 100 - (100 / (1 + (gain / loss)))

try:
    df = fetch_fpl_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    t = 38 - max_gw # 剩餘週數

    # --- 1. 核心計算 (Net Score * 2) ---
    def calc_gl(group):
        n = len(group)
        total = group['總分'].sum()
        group['目前輸贏'] = (group['總分'] * (n - 1) - (total - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # --- 2. 專業預測模型 (EV & Range) ---
    final_stats = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        pts = m_df['當週分']
        
        # WMA 加權平均得分
        recent = pts.tail(5)
        wma = np.average(recent, weights=np.arange(1, len(recent) + 1))
        
        # EV 與 EV Range
        ev = m_df['總分'].iloc[-1] + (wma * t)
        std = pts.std()
        margin = 1.96 * std * np.sqrt(t) if t > 0 else 0
        
        # MACD (快3/慢8)
        macd = pts.ewm(span=3).mean() - pts.ewm(span=8).mean()
        sig = macd.ewm(span=3).mean()
        
        final_stats.append({
            "經理人": manager,
            "目前輸贏": int(m_df['目前輸贏'].iloc[-1]),
            "GW38 EV": int(ev),
            "EV 下限": int(ev - margin),
            "EV 上限": int(ev + margin),
            "RSI": int(calculate_rsi(pts).iloc[-1]) if not np.isnan(calculate_rsi(pts).iloc[-1]) else 50,
            "趨勢": "🟢 轉強" if macd.iloc[-1] > sig.iloc[-1] else "🔴 走弱"
        })

    res_df = pd.DataFrame(final_stats)
    
    # 預測輸贏對沖計算
    total_ev = res_df['GW38 EV'].sum()
    n_p = len(res_df)
    res_df['預測輸贏'] = ((res_df['GW38 EV'] * (n_p - 1)) - (total_ev - res_df['GW38 EV'])) * 2
    res_df['預測輸贏'] = res_df['預測輸贏'].astype(int)

    # --- UI 呈現 ---
    st.title("🏛️ FPL 專業量化決算終端")

    # 1. 預測假設說明 (iPhone 摺疊顯示)
    with st.expander("📝 查看預測模型假設 (Predict Assumptions)"):
        st.markdown(f"""
        - **EV (期望值)**：採計近 5 週得分進行 **加權移動平均 (WMA)**。
        - **EV Range**：基於 95% 信賴區間。考慮剩餘 **{t}** 週的標準差波動。
        - **量化指標**：RSI 衡量動能，MACD 衡量趨勢斜率。
        """)

    # 2. 頂部看板 (iPhone 2x2)
    top_c1, top_c2 = st.columns(2)
    with top_c1:
        st.metric("當前贏家", res_df.loc[res_df['目前輸贏'].idxmax()]['經理人'], f"{res_df['目前輸贏'].max()}")
    with top_c2:
        st.metric("預計季末贏家 (EV)", res_df.loc[res_df['預測輸贏'].idxmax()]['經理人'], f"{res_df['預測輸贏'].max()}")

    # 3. 核心數據矩陣 (iPhone 瘦身版)
    st.markdown("### 🏆 核心決算矩陣")
    def style_gl(val):
        color = '#2ecc71' if val > 0 else '#e74c3c'
        return f'color: {color}; font-weight: bold'

    # 精選 6 個最重要欄位，避免手機滑動
    display_df = res_df[['經理人', '目前輸贏', '預測輸贏', 'RSI', '趨勢', 'EV 下限', 'EV 上限']].sort_values('目前輸贏', ascending=False)
    st.dataframe(
        display_df.style.applymap(style_gl, subset=['目前輸贏', '預測輸贏']),
        use_container_width=True, hide_index=True
    )

    # 4. 專業視覺化
    st.markdown("### 📊 統計趨勢圖表")
    tab1, tab2 = st.tabs(["💰 輸贏趨勢", "🔮 EV 預測區間"])
    
    with tab1:
        # 繪製所有經理人的累計輸贏曲線
        st.line_chart(df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
        
    with tab2:
        # 使用水平條型圖展示 EV Range (Error Bar 概念)
        # iPhone 上顯示 DataFrame 模擬的區間最清晰
        st.write("下表展示 GW38 最終分數的 95% 概率落點：")
        range_df = res_df[['經理人', 'EV 下限', 'GW38 EV', 'EV 上限']].sort_values('GW38 EV', ascending=False)
        st.dataframe(range_df, use_container_width=True, hide_index=True)
        

except Exception as e:
    st.error(f"Error: {e}")

st.caption(f"FPL Data Optimized for iPhone | Current GW: {max_gw} | Powered by Gemini")
