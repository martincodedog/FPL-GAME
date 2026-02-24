import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="LCF Shame Tool", page_icon="⚖️")
st.title("⚖️ LCF: The P&L Benchmark Tool")

LEAGUE_ID = 1133270
FPL_API_BASE = "https://fantasy.premierleague.com/api/"

@st.cache_data(ttl=300) # Refreshes every 5 minutes
def get_league_data():
    url = f"{FPL_API_BASE}leagues-classic/{LEAGUE_ID}/standings/"
    data = requests.get(url).json()
    all_managers = data['standings']['results']
    
    # RULE 1: Ignore Emil Chau
    filtered_managers = [m for m in all_managers if m['player_name'] != "Emil Chau"]
    return filtered_managers

try:
    managers = get_league_data()
    
    # Find P&L
    pn_l_player = next((m for m in managers if m['player_name'] == "P&L"), None)
    
    if pn_l_player:
        p_l_pts = pn_l_player['total']
        
        # RULE 2: P&L Logic
        # Gain points from people lower than him, lose to people higher.
        gain_from_lower = sum([(p_l_pts - m['total']) for m in managers if m['total'] < p_l_pts])
        loss_to_higher = sum([(m['total'] - p_l_pts) for m in managers if m['total'] > p_l_pts])
        
        net_pn_l_score = gain_from_lower - loss_to_higher
        
        # Display Metrics
        st.subheader(f"P&L's Survival Status")
        c1, c2, c3 = st.columns(3)
        c1.metric("P&L Raw Points", p_l_pts)
        c2.metric("Net Differential", f"{net_pn_l_score:+}")
        status = "🔥 Dominating" if net_pn_l_score > 0 else "💀 Shamed"
        c3.info(status)

        # Build the table for everyone
        table_data = []
        for m in managers:
            diff = p_l_pts - m['total']
            table_data.append({
                "Rank": m['rank'],
                "Manager": m['player_name'],
                "Team": m['entry_name'],
                "Raw Points": m['total'],
                "Diff vs P&L": diff
            })
        
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True)
        
        st.write("---")
        st.write(f"**Calculation Logic:** P&L earns points from the {len(df[df['Diff vs P&L'] > 0])} managers below him and pays out to the {len(df[df['Diff vs P&L'] < 0])} managers above him.")
        
    else:
        st.error("Manager 'P&L' not found in the league! Check the spelling in FPL.")
        st.write("Managers found:", [m['player_name'] for m in managers])

except Exception as e:
    st.error(f"Error: {e}")
