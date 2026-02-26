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
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 12px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
    .player-card {
        background-color: #ffffff;
        padding: 12px;
        border-radius: 12px;
        border-left: 6px solid #3498db;
        margin-bottom: 15px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.07);
    }
    .mom-up { color: #2ecc71; font-weight: bold; }
    .mom-down { color: #e74c3c; font-weight: bold; }
    .exp-box { background-color: #e8f4f8; padding: 10px; border-radius: 8px; font-size: 0.9em; margin-bottom: 15px; }
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

    # 1. 核心輸贏計算 (Net Score * 2)
    def calc_gl(group):
        n = len(group)
        group['目前輸贏'] = (group['總分'] * (n - 1) - (group['總分'].sum() - group['總分'])) * 2
        return group
    df = df.groupby('GW', group_keys=False).apply(calc_gl)

    # 2. 5 項技術指標與預測模型計算
    quant_list = []
    for manager in df['經理人'].unique():
        m_df = df[df['經理人'] == manager].sort_values('GW')
        pts = m_df['當週分']
        
        # --- 預測模型 ---
        wma = np.average(pts.tail(5), weights=[1,2,3,4,5])
        ev = m_df['總分'].iloc[-1] + (wma * t)
        std = pts.std()
        margin = 1.96 * std * np.sqrt(t) if t > 0 else 0
        
        # --- 5 項技術指標 ---
        # 1. RSI (相對強弱): 近 5 週動能
        delta = pts.diff()
        gain = (delta.where(delta > 0, 0)).rolling(5).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(5).mean()
        rsi = 100 - (100 / (1 + (gain / loss))).iloc[-1]
        
        # 2. MACD (趨勢): 指數平滑異同移動平均
        macd = (pts.ewm(span=3).mean() - pts.ewm(span=8).mean()).iloc[-1]
        sig = (pts.ewm(span=3).mean() - pts.ewm(span=8).mean()).ewm(span=3).mean().iloc[-1]
        
        # 3. Momentum (動量): 近 3 週 vs 全賽季均值
        mom = pts.tail(3).mean() - pts.mean()
        
        # 4. Bollinger %B (布林位置): 衡量當前分數在波動區間的高低
        ma5 = pts.rolling(5).mean()
        std5 = pts.rolling(5).std()
        b_perc = (pts.iloc[-1] - (ma5.iloc[-1] - 2*std5.iloc[-1])) / (4*std5.iloc[-1]) if std5.iloc[-1] != 0 else 0.5
        
        # 5. Volatility (波動率): 得分穩定性 (標準差)
        vol = pts.std()

        quant_list.append({
            "經理人": manager,
            "目前輸贏": int(m_df['目前輸贏'].iloc[-1]),
            "GW38 EV": int(ev),
            "Expected Upper": int(ev + margin),
            "Expected Lower": int(ev - margin),
            "RSI 動能": int(rsi) if not np.isnan(rsi) else 50,
            "趨勢 MACD": "🟢 轉強" if macd > sig else "🔴 走弱",
            "動量 Mom": round(mom, 1),
            "布林帶 %B": round(b_perc, 2),
            "波動率 σ": round(vol, 1)
        })

    res_df = pd.DataFrame(quant_list).sort_values('目前輸贏', ascending=False)
    total_ev = res_df['GW38 EV'].sum()
    res_df['預測輸贏'] = ((res_df['GW38 EV'] * len(res_df) - total_ev) * 2).astype(int)

    # --- UI 呈現 ---
    st.title("🏛️ FPL 量化博弈終端 PRO")
    
    # 頂部看板
    c1, c2, c3 = st.columns(3)
    c1.metric("領先者", res_df.iloc[0]['經理人'])
    c2.metric("最高淨值", f"{res_df['目前輸贏'].max()} pts")
    c3.metric("剩餘賽事", f"{t} 週")

    # A. 預測假設說明
    st.markdown("""
    ### 📝 核心假設與說明 (Assumptions)
    > **預測邏輯**: 我們不假設未來得分與過去相等。**EV** 採用 **WMA (加權移動平均)**，最近週數的表現對未來預測影響力越大 (權重 5:4:3:2:1)。
    > **Range (區間)**: 基於 **95% 信賴區間**。若剩餘週數多，區間則寬；隨賽季接近結束，區間將收斂。
    > **輸贏結算**: 採計 `(個人總分 - 聯賽平均總分) * 2`。
    """)

    # B. 個人狀態卡片
    st.subheader("👤 經理人實時卡片")
    cols = st.columns(2)
    for idx, row in res_df.iterrows():
        mom_icon = "↑" if row['動量 Mom'] > 0 else "↓"
        mom_class = "mom-up" if row['動量 Mom'] > 0 else "mom-down"
        with cols[idx % 2]:
            st.markdown(f"""
            <div class="player-card">
                <div style="display: flex; justify-content: space-between;">
                    <small style="color:gray;">{row['經理人']}</small>
                    <span class="{mom_class}">{mom_icon} {abs(row['動量 Mom'])}</span>
                </div>
                <div style="margin: 8px 0;">
                    <strong style="font-size:20px;">{row['目前輸贏']} pts</strong>
                </div>
                <div style="font-size:12px; color:#555;">
                    預測季末：<b style="color:{'#2ecc71' if row['預測輸贏'] > 0 else '#e74c3c'}">{row['預測輸贏']}</b><br>
                    RSI: {row['RSI 動能']} | {row['趨勢 MACD']}
                </div>
            </div>
            """, unsafe_allow_html=True)

    # C. 決算矩陣 (轉置)
    st.markdown("---")
    st.subheader("📊 深度量化矩陣 (Matrix)")
    matrix_df = res_df.set_index('經理人').T
    st.dataframe(matrix_df, use_container_width=True)

    # D. 5 項技術指標說明
    with st.expander("🔬 技術指標深度解析 (Indicators Explained)"):
        st.markdown("""
        1. **RSI (Relative Strength Index)**: 衡量得分動能。>70 代表近期手感極熱（警惕回歸）；<30 代表近期手感冰冷（期待反彈）。
        2. **MACD (Trend)**: 觀察「快線」與「慢線」的交叉。🟢 代表得分增速正在加快，🔴 代表得分潛力正在衰退。
        3. **Momentum (動量)**: `近3週均分 - 賽季均分`。正值代表該經理人正處於上升軌道。
        4. **Bollinger %B (布林帶位置)**: 衡量目前得分在過去 5 週波動區間的位置。>1 代表「超水準發揮」。
        5. **Volatility (波動率 σ)**: 數值越高，代表該玩家表現越「神鬼一念間」；數值低則代表表現極其穩健。
        """)

    # E. 圖表
    st.markdown("---")
    t1, t2 = st.tabs(["💰 輸贏曲線", "🔮 預測區間對比"])
    with t1:
        st.line_chart(df.pivot(index='GW', columns='經理人', values='目前輸贏'))
        
    with t2:
        st.write("GW38 分數落點區間 (EV ± Range):")
        range_view = res_df[['經理人', 'Expected Lower', 'GW38 EV', 'Expected Upper']].sort_values('GW38 EV', ascending=False)
        st.dataframe(range_view, use_container_width=True, hide_index=True)
        

except Exception as e:
    st.error(f"Error: {e}")

st.caption(f"Optimized for iPhone | Updated: GW {max_gw}")
