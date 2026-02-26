import streamlit as st
import pandas as pd
import requests
import numpy as np

st.set_page_config(page_title="FPL Finance Terminal", layout="wide")

# Constants
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

# --- API HELPER FUNCTIONS (Kept as requested) ---
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

# --- DATA PROCESSING & STATS ---
st.title("📊 FPL League Equity Terminal")

try:
    members = get_league_members(LEAGUE_ID)

    with st.spinner("Analyzing Portfolio Performance..."):
        all_data = []
        for m in members:
            history = get_history_data(m['entry'])
            for h in history:
                all_data.append({
                    "GW": h['event'],
                    "Manager": m['player_name'],
                    "Points": h['total_points']
                })

        full_df = pd.DataFrame(all_data)

        # Basic Net Score & Gain/Loss Logic
        def calculate_metrics(group):
            n = len(group)
            total_pts = group['Points'].sum()
            group['Gain/Loss'] = group['Points'].apply(lambda x: (x * (n - 1)) - (total_pts - x)) * 2
            return group

        full_df = full_df.groupby('GW', group_keys=False).apply(calculate_metrics)
        max_gw = full_df['GW'].max()

        # --- NEW: FINANCE STATISTICAL ANALYSIS ---
        stats_rows = []
        for manager in full_df['Manager'].unique():
            m_data = full_df[full_df['Manager'] == manager].sort_values('GW')
            
            # 1. Volatility (Risk) - Std Dev of weekly Gain/Loss changes
            weekly_change = m_data['Gain/Loss'].diff().fillna(0)
            volatility = weekly_change.std()
            
            # 2. Performance Consistency (Sharpe-style)
            # Mean Gain per GW / Volatility
            consistency = m_data['Gain/Loss'].mean() / (volatility if volatility != 0 else 1)
            
            # 3. Max Drawdown (Peak to Trough)
            running_max = m_data['Gain/Loss'].cummax()
            drawdown = (m_data['Gain/Loss'] - running_max).min()
            
            stats_rows.append({
                "Manager": manager,
                "Risk (Vol)": round(volatility, 2),
                "Consistency Ratio": round(consistency, 2),
                "Max Drawdown": round(drawdown, 2)
            })
        
        stats_df = pd.DataFrame(stats_rows)

    # --- UI LAYOUT ---
    
    # 1. TOP METRICS BAR
    st.subheader("📡 Market Summary")
    kpi1, kpi2, kpi3 = st.columns(3)
    kpi1.metric("Total Managers", len(members))
    kpi2.metric("Active Gameweek", max_gw)
    kpi3.metric("League Volatility", round(stats_df['Risk (Vol)'].mean(), 2))

    # 2. CURRENT STANDINGS
    st.markdown("---")
    selected_gw = st.sidebar.select_slider("Select Reporting Period (GW):", options=sorted(full_df['GW'].unique().tolist()), value=max_gw)
    
    st.header(f"💼 Portfolio Holdings: GW {selected_gw}")
    
    current_view = full_df[full_df['GW'] == selected_gw].merge(stats_df, on="Manager")
    current_view = current_view.sort_values("Points", ascending=False)
    
    def color_finance(val):
        if isinstance(val, (int, float)):
            color = '#2ecc71' if val > 0 else '#e74c3c' if val < 0 else '#95a5a6'
            return f'color: {color}; font-weight: bold'
        return ''

    st.dataframe(
        current_view[['Manager', 'Points', 'Gain/Loss', 'Risk (Vol)', 'Consistency Ratio', 'Max Drawdown']]
        .style.applymap(color_finance, subset=['Gain/Loss', 'Consistency Ratio', 'Max Drawdown']),
        use_container_width=True, hide_index=True
    )

    # 3. TREND CHART
    st.markdown("---")
    st.header("📈 Cumulative Equity Curve")
    chart_data = full_df.pivot(index='GW', columns='Manager', values='Gain/Loss')
    st.line_chart(chart_data)

except Exception as e:
    st.error(f"System Error: {e}")

st.caption(f"Financial analysis excludes {IGNORE_PLAYER}. Terms: Volatility = Weekly fluctuation; Consistency = Return vs Risk.")
