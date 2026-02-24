import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="FPL Points Calc", layout="centered")

# Constants
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

# --- API HELPER FUNCTIONS ---
@st.cache_data(ttl=3600)
def get_league_members(league_id):
    url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    # Filter out Emil Chau immediately
    return [p for p in r.json()['standings']['results'] if p['player_name'] != IGNORE_PLAYER]

@st.cache_data(ttl=3600)
def get_manager_gw_score(entry_id, target_gw):
    url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    history = r.json()['current']
    # Find the specific gameweek data
    for gw_data in history:
        if gw_data['event'] == target_gw:
            return gw_data['total_points']
    return 0

# --- APP UI ---
st.title("⚽ FPL League Points Calculator")

# Sidebar for GW selection
members = get_league_members(LEAGUE_ID)
# Get the current GW by checking the first member's history length
sample_r = requests.get(f"https://fantasy.premierleague.com/api/entry/{members[0]['entry']}/history/", headers={"User-Agent": "Mozilla/5.0"})
max_gw = len(sample_r.json()['current'])

selected_gw = st.sidebar.slider("Select Gameweek", 1, max_gw, max_gw)

# --- CALCULATION ---
with st.spinner(f"Calculating scores for GW {selected_gw}..."):
    rows = []
    for m in members:
        pts_at_gw = get_manager_gw_score(m['entry'], selected_gw)
        rows.append({
            "Manager": m['player_name'],
            "Team": m['entry_name'],
            "FPL Total Points": pts_at_gw
        })

    df = pd.DataFrame(rows)
    n = len(df)
    sum_all_points = df['FPL Total Points'].sum()

    # Logic: (My Pts * (n-1)) - (Sum of others)
    df['Net Score'] = df['FPL Total Points'].apply(lambda x: (x * (n - 1)) - (sum_all_points - x))
    df['Gain/Loss'] = df['Net Score'] * 2

    # Formatting
    df = df.sort_values(by="FPL Total Points", ascending=False)

    st.subheader(f"Standings at end of Gameweek {selected_gw}")
    
    def color_values(val):
        color = 'green' if val > 0 else 'red' if val < 0 else 'gray'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df.style.applymap(color_values, subset=['Net Score', 'Gain/Loss']),
        use_container_width=True,
        hide_index=True
    )

st.caption(f"Excluding: {IGNORE_PLAYER} | Formula: Net Score * 2")
