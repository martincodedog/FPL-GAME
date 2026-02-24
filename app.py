import streamlit as st
import pandas as pd
import requests
import plotly.express as px

st.set_page_config(page_title="FPL History & Trends", layout="wide")

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
def get_history_data(entry_id):
    url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    return r.json()['current']

# --- APP UI ---
st.title("⚽ FPL League History & Gain/Loss Trends")

with st.sidebar:
    st.header("Settings")
    members = get_league_members(LEAGUE_ID)
    
    # Determine max GW available
    sample_history = get_history_data(members[0]['entry'])
    max_gw = len(sample_history)
    
    selected_gw = st.slider("Select Gameweek", 1, max_gw, max_gw)
    st.info(f"Showing results for GW {selected_gw}")

# --- CALCULATION LOGIC ---
all_gw_results = []

# We fetch history for all members to build a trend chart
with st.spinner("Analyzing league history..."):
    for m in members:
        history = get_history_data(m['entry'])
        for h in history:
            all_gw_results.append({
                "GW": h['event'],
                "Manager": m['player_name'],
                "Points": h['total_points']
            })

# Convert to DataFrame
df_history = pd.DataFrame(all_gw_results)

# Calculate Net Score for EVERY GW (for the trend chart)
def calc_net_scores(group):
    n = len(group)
    total_pts = group['Points'].sum()
    group['Net Score'] = group['Points'].apply(lambda x: (x * (n - 1)) - (total_pts - x))
    group['Gain/Loss'] = group['Net Score'] * 2
    return group

df_history = df_history.groupby('GW', group_keys=False).apply(calc_net_scores)

# --- DISPLAY ---
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader(f"GW {selected_gw} Standings")
    current_df = df_history[df_history['GW'] == selected_gw].sort_values("Points", ascending=False)
    
    def color_gl(val):
        return f'color: {"green" if val > 0 else "red"}; font-weight: bold'
    
    st.dataframe(
        current_df[['Manager', 'Points', 'Net Score', 'Gain/Loss']].style.applymap(color_gl, subset=['Gain/Loss']),
        hide_index=True, use_container_width=True
    )

with col2:
    st.subheader("Season Trend: Gain/Loss")
    fig = px.line(
        df_history, 
        x="GW", y="Gain/Loss", color="Manager",
        title="Cumulative Gain/Loss Over Time",
        markers=True,
        template="plotly_white"
    )
    # Add a zero line
    fig.add_hline(y=0, line_dash="dash", line_color="black", opacity=0.5)
    st.plotly_chart(fig, use_container_width=True)

st.caption(f"Note: Data excludes {IGNORE_PLAYER}. Net Score = (My Points vs All Opponents).")
