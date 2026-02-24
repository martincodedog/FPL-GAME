import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="FPL League Tracker", layout="wide")

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

# --- DATA PROCESSING ---
st.title("⚽ FPL League Manager & History")

try:
    members = get_league_members(LEAGUE_ID)

    with st.spinner("Processing full season data..."):
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

        # Logic: (My Pts * (n-1) - sum_of_others) * 2
        def calculate_metrics(group):
            n = len(group)
            total_pts = group['Points'].sum()
            group['Gain/Loss'] = group['Points'].apply(lambda x: (x * (n - 1)) - (total_pts - x)) * 2
            return group

        full_df = full_df.groupby('GW', group_keys=False).apply(calculate_metrics)
        max_gw = full_df['GW'].max()

    # --- SIDEBAR SELECTOR ---
    selected_gw = st.sidebar.select_slider(
        "Select Gameweek to view Standings:",
        options=sorted(full_df['GW'].unique().tolist()),
        value=max_gw
    )
    st.sidebar.markdown(f"**Viewing: GW {selected_gw}**")

    # --- 1. SELECTED STANDINGS ---
    st.header(f"🏆 Standings: End of Gameweek {selected_gw}")
    
    view_df = full_df[full_df['GW'] == selected_gw].sort_values("Points", ascending=False)
    
    def style_positive_negative(val):
        color = '#2ecc71' if val > 0 else '#e74c3c' if val < 0 else '#95a5a6'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        view_df[['Manager', 'Points', 'Gain/Loss']].style.applymap(style_positive_negative, subset=['Gain/Loss']),
        use_container_width=True,
        hide_index=True
    )

    st.markdown("---")

    # --- 2. GAIN/LOSS TREND (ALL TIME) ---
    st.header("📈 Season Progress: Gain/Loss Trend")
    st.write("Cumulative movement across all gameweeks.")

    # Pivot data for st.line_chart
    chart_data = full_df.pivot(index='GW', columns='Manager', values='Gain/Loss')
    st.line_chart(chart_data)

except Exception as e:
    st.error(f"Error: {e}")

st.caption(f"Filtering: {IGNORE_PLAYER} removed. Requirements: streamlit, pandas, requests.")
