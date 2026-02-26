import streamlit as st
import pandas as pd
import requests
import numpy as np

# iPhone 行動端優化：強制寬屏
st.set_page_config(page_title="FPL 量化終端 PRO", layout="wide", initial_sidebar_state="collapsed")

# 專業量化風格 CSS
st.markdown("""
    <style>
    .main { background-color: #f1f3f6; }
    [data-testid="stMetricValue"] { font-size: 18px !important; color: #0e1117; }
    .stDataFrame { border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
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
    df = fetch_data(LEAGUE_ID)
    max_gw = df['GW'].max()
    t = 38 - max_gw

    # 1. 核心決算計算 (Net Score * 2)
    def calc_gl(group):
        n = len(group)
        total = group['總分'].sum()
        group['目前輸贏'] = (group['總分'] * (n - 1) - (total - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # 2. 量化指標與 EV 模型
    final_stats = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        pts = m_df['當週分']
        
        # --- 技術指標 ---
        # RSI
        delta = pts.diff(); gain = (delta.where(delta > 0, 0)).rolling(5).mean(); loss = (-delta.where(delta < 0, 0)).rolling(5).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        # MACD
        macd = pts.ewm(span=3).mean() - pts.ewm(span=8).mean(); sig = macd.ewm(span=3).mean()
        # Momentum (3週)
        mom = pts.iloc[-1] - pts.iloc[-4] if len(pts) >= 4 else 0
        
        # --- EV & Range (95% CI) ---
        wma = np.average(pts.tail(5), weights=np.arange(1, len(pts.tail(5)) + 1))
        ev = m_df['總分'].iloc[-1] + (wma * t)
        std = pts.std()
        margin = 1.96 * std * np.sqrt(t) if t > 0 else 0
        
        final_stats.append({
            "經理人": manager,
            "目前輸贏": int(m_df['目前輸贏'].iloc[-1]),
            "GW38 EV": int(ev),
            "EV 下限": int(ev - margin),
            "EV 上限": int(ev + margin),
            "RSI 動能": int(rsi) if not np.isnan(rsi) else 50,
            "MACD 趨勢": "🟢 轉強" if macd.iloc[-1] > sig.iloc[-1] else "🔴 走弱",
            "MOM 爆發力": int(mom)
        })

    res_df = pd.DataFrame(final_stats)
    
    # 預測輸贏對沖計算
    total_ev = res_df['GW38 EV'].sum()
    n_p = len(res_df)
    res_df['預測輸贏'] = ((res_df['GW38 EV'] * (n_p - 1)) - (total_ev - res_df['GW38 EV'])) * 2

    # --- UI 呈現 ---
    st.title("⚖️ FPL 量化決算終端 PRO")

    # 預測假設
    with st.expander("🛠️ 預測模型說明"):
        st.write(f"**EV Range**: 基於 95% 信賴區間。預估剩餘 {t} 週的表現波動。")
        st.latex(r"Range = EV \pm (1.96 \cdot \sigma \cdot \sqrt{t})")

    # 1. 核心決算矩陣 (iPhone 瘦身版)
    st.subheader("🏆 聯賽決算矩陣")
    def color_gl(val):
        return f'color: {"#2ecc71" if val > 0 else "#e74c3c"}; font-weight: bold'

    st.dataframe(
        res_df[['經理人', '目前輸贏', '預測輸贏', 'RSI 動能', 'MACD 趨勢', 'MOM 爆發力']]
        .sort_values('目前輸贏', ascending=False)
        .style.applymap(color_gl, subset=['目前輸贏', '預測輸贏']),
        use_container_width=True, hide_index=True
    )

    # 2. 橫向 EV 區間圖 (iPhone 最友善視角)
    st.markdown("---")
    st.subheader("🔮 GW38 EV 期望值與區間預測")
    st.write("點代表期望值 (EV)，橫條代表 95% 概率落點。")
    
    # 建立橫向 Bar Chart 模擬 Range
    range_chart = res_df[['經理人', 'EV 下限', 'GW38 EV', 'EV 上限']].set_index('經理人').sort_values('GW38 EV')
    st.bar_chart(range_chart, x_label="玩家名稱", y_label="預測總分")
    
    

    # 3. 深度技術分析
    st.markdown("---")
    st.subheader("📈 技術指標趨勢")
    tab1, tab2 = st.tabs(["💰 累計輸贏曲線", "🌪️ RSI & 爆發力"])
    
    with tab1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
        
    with tab2:
        # 散佈圖：X 軸為 RSI，Y 軸為 MOM，氣泡大小為目前總分
        st.write("觀察誰處於超買區 (RSI > 70) 且動能持續增強：")
        st.scatter_chart(res_df, x="RSI 動能", y="MOM 爆發力", color="經理人")
        

except Exception as e:
    st.error(f"系統故障: {e}")

st.caption(f"數據自動排除：{IGNORE_PLAYER} | 預測模型：WMA + 95% CI")
