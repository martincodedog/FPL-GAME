import streamlit as st
import pandas as pd
import requests

# App Configuration
st.set_page_config(page_title="FPL League Calc", page_icon="⚽")

st.title("🏆 FPL League Points Calculator")
st.markdown("Calculates net scores based on point differences with all opponents.")

# Constants
LEAGUE_ID = "1133270"
IGNORE_PLAYER = "Emil Chau"

@st.cache_data(ttl=3600)  # Cache data for 1 hour to stay within API limits
def get_fpl_data(league_id):
    url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()['standings']['results']
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        return None

raw_data = get_fpl_data(LEAGUE_ID)

if raw_data:
    # 1) Filter out Emil Chau
    filtered_data = [p for p in raw_data if p['player_name'] != IGNORE_PLAYER]
    
    df = pd.DataFrame(filtered_data)
    df = df[['player_name', 'entry_name', 'total']].copy()
    
    # 2) Logic: Net score is difference vs everyone else
    total_players = len(df)
    sum_all_pts = df['total'].sum()
    
    # Calculation: (My Pts * (N-1)) - (Sum of everyone else's pts)
    df['Net Score'] = df['total'].apply(lambda x: (x * (total_players - 1)) - (sum_all_pts - x))
    
    # 3) Gain/Loss = Net Score * 2
    df['Gain/Loss'] = df['Net Score'] * 2
    
    # UI Styling
    df = df.rename(columns={
        'player_name': 'Manager', 
        'entry_name': 'Team', 
        'total': 'FPL Points'
    })

    # Display results
    st.subheader(f"Standings (Excluding {IGNORE_PLAYER})")
    
    def color_values(val):
        color = 'green' if val > 0 else 'red' if val < 0 else 'black'
        return f'color: {color}; font-weight: bold'

    st.dataframe(
        df.style.applymap(color_values, subset=['Net Score', 'Gain/Loss']),
        use_container_width=True,
        hide_index=True
    )
    
    st.success(f"Calculation complete for {total_players} managers.")
