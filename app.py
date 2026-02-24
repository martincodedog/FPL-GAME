import streamlit as st
import requests
import pandas as pd

# App Styling
st.set_page_config(page_title="P&L Benchmark Tool", page_icon="📈")
st.title("📈 LCF: The P&L 2x Multiplier")
st.markdown("Rules: Emil Chau is ignored. P&L's Net Score is doubled.")

LEAGUE_ID = 1133270
FPL_API_BASE = "https://fantasy.premierleague.com/api/"

@st.cache_data(ttl=600)
def get_league_data():
    url = f"{FPL_API_BASE}leagues-classic/{LEAGUE_ID}/standings/"
    response = requests.get(url).json()
    all_managers = response['standings']['results']
    
    # RULE 1: Ignore Emil Chau
    return [m for m in all_managers if m['player_name'] != "Emil Chau"]

try:
    managers = get_league_data()
    
    # Identify P&L (Searching for exact match or 'P&L' in name)
    pn_l_player = next((m for m in managers if "P&L" in m['player_name']), None)
    
    if pn_l_player:
        p_l_pts = pn_l_player['total']
        
        # RULE 2: Calculate Differentials
        # Sum of (P&L - others) for everyone below him
        gains = sum([(p_l_pts - m['total']) for m in managers if m['total'] < p_l_pts])
        # Sum of (others - P&L) for everyone above him
        losses = sum([(m['total'] - p_l_pts) for m in managers if m['total'] > p_l_pts])
        
        raw_net = gains - losses
        # RULE 3: The 2x Multiplier
        final_p_l_score = raw_net * 2
        
        # --- Dashboard UI ---
        st.subheader(f"Status for: {pn_l_player['player_name']}")
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Base Points", p_l_pts)
        m2.metric("Raw Net Diff", f"{raw_net:+}")
        # Highlighting the final 2x score
        m3.metric("Final P&L Score (2x)", f"{final_p_l_score:+}", 
                  delta_color="normal" if final_p_l_score >= 0 else "inverse")

        # --- Detailed Table ---
        st.write("### The Benchmark Standings")
        
        table_data = []
        for m in managers:
            diff = p_l_pts - m['total']
            table_data.append({
                "Manager": m['player_name'],
                "Team": m['entry_name'],
                "FPL Points": m['total'],
                "Diff vs P&L": diff,
                "Contribution to P&L": diff * 2  # Showing the 2x impact per person
            })
        
        df = pd.DataFrame(table_data).sort_values("FPL Points", ascending=False)
        
        # Highlight P&L's row in the table
        def highlight_p_l(s):
            return ['background-color: #1e3a8a; color: white' if "P&L" in s.Manager else '' for _ in s]

        st.dataframe(df.style.apply(highlight_p_l, axis=1), use_container_width=True)

        st.info(f"💡 Logic: P&L is currently {'gaining' if raw_net > 0 else 'losing'} points. The total net impact of {raw_net} is doubled to {final_p_l_score}.")

    else:
        st.warning("⚠️ Manager 'P&L' not found in the current standings. Ensure the name matches exactly.")

except Exception as e:
    st.error("Could not connect to FPL API. Please try again later.")