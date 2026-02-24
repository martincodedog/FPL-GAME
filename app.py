import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="FPL Tracker", layout="wide")

# Constants
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

# --- API HELPER FUNCTIONS ---
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

# --- APP UI ---
st.title("⚽ FPL Gain/Loss Tracker")

members = get_league_members(LEAGUE_ID)

# 1. Fetch data for all available weeks
with st.spinner("Analyzing history for the last 5 gameweeks..."):
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

    # 2. Calculate Gain/Loss for every manager in every GW
    def calculate_metrics(group):
        n = len(group)
        total_pts = group['Points'].sum()
        # Formula: (Points * (n-1) - sum_of_others) * 2
        group['Gain/Loss'] = group['Points'].apply(lambda x: (x * (n - 1)) - (total_pts - x)) * 2
        return group

    full_df = full_df.groupby('GW', group_keys=False).apply(calculate_metrics)

# --- TREND CHART (Last 5 GWs) ---
st.subheader("📈 Gain/Loss Trend (Last 5 GWs)")

# Filter for the last 5 weeks
max_gw = full_df['GW'].max()
min_gw = max(1, max_gw - 4)
trend_df = full_df[full_df['GW'] >= min_gw]

# Pivot data for st.line_chart: Index=GW, Columns=Managers, Values=Gain/Loss
chart_data = trend_df.pivot(index='GW', columns='Manager', values='Gain/Loss')
st.line_chart(chart_data)

# --- STANDINGS TABLE (Current GW) ---
st.subheader(f"Current Standings (GW {max_gw})")
current_gw_df = full_df[full_df['GW'] == max_gw].sort_values("Points", ascending=False)

def style_values(val):
    color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
    return f'color: {color}; font-weight: bold'

st.dataframe(
    current_gw_df[['Manager', 'Points', 'Gain/Loss']].style.applymap(style_values, subset=['Gain/Loss']),
    use_container_width=True,
    hide_index=True
)

st.caption(f"Data automatically excludes {IGNORE_PLAYER}. Chart shows cumulative trend.")
