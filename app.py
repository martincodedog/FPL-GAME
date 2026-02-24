import streamlit as st
import requests
import pandas as pd

# Page setup
st.set_page_config(page_title="P&L Benchmark 2x", page_icon="⚖️", layout="wide")

st.title("⚖️ LCF: The P&L 2x Multiplier")
st.markdown("Rules: Emil Chau is excluded. P&L's Net Score = (Total of points beaten) - (Total of points lost to).")

LEAGUE_ID = 1133270
FPL_API_BASE = "https://fantasy.premierleague.com/api/"

@st.cache_data(ttl=600)
def get_league_data():
    try:
        url = f"{FPL_API_BASE}leagues-classic/{LEAGUE_ID}/standings/"
        response = requests.get(url).json()
        standings = response['standings']['results']
        
        # RULE 1: Ignore Emil Chau
        return [m for m in standings if m['player_name'].strip() != "Emil Chau"]
    except:
        return None

data = get_league_data()

if data:
    # Identify P&L (Searching Manager Name or Team Name)
    p_l_entry = next((m for m in data if "P&L" in str(m['player_name']).upper() or "P&L" in str(m['entry_name']).upper()), None)
    
    if p_l_entry:
        p_l_pts = p_l_entry['total']
        p_l_name = p_l_entry['player_name']
        
        # RULE 2: Net Score Logic
        # Difference = (My Points - Their Points)
        # Summing these gives the net score directly
        net_score = sum([(p_l_pts - m['total']) for m in data if m['entry'] != p_l_entry['entry']])
        
        # RULE 3: 2x Multiplier
        final_gain_loss = net_score * 2
        
        # --- TOP METRICS ---
        st.subheader(f"Current Status for {p_l_name}")
        c1, c2, c3 = st.columns(3)
        c1.metric("P&L Raw FPL Points", p_l_pts)
        c2.metric("Net Score (Sum of Diffs)", f"{net_score:+}")
        
        # Dynamic color for the multiplier
        color_style = "normal" if final_gain_loss >= 0 else "inverse"
        c3.metric("FINAL GAIN/LOSS (2x)", f"{final_gain_loss:+}", delta_color=color_style)

        st.divider()

        # --- RANKINGS TABLE ---
        table_list = []
        for m in data:
            diff = p_l_pts - m['total']
            table_list.append({
                "Rank": m['rank'],
                "Manager": m['player_name'],
                "Team": m['entry_name'],
                "FPL Pts": m['total'],
                "Diff vs P&L": diff,
                "2x Contribution": diff * 2
            })
        
        df = pd.DataFrame(table_list).sort_values("FPL Pts", ascending=False)

        # Highlight P&L Row
        def highlight_p_l(s):
            return ['background-color: #004d40; color: white' if "P&L" in str(s.Manager).upper() else '' for _ in s]

        st.write("### The Shame Table")
        st.dataframe(df.style.apply(highlight_p_l, axis=1), use_container_width=True, hide_index=True)
        
        # Explainer
        with st.expander("How is this calculated?"):
            st.write(f"1. We find everyone in the league except Emil Chau.")
            st.write(f"2. For every player, we do: `({p_l_pts} - Their Score)`.")
            st.write(f"3. We add all those numbers up (Net Score: {net_score}).")
            st.write(f"4. We multiply the result by 2 to get the Final Score: **{final_gain_loss}**.")
            
    else:
        st.error("⚠️ Manager 'P&L' not found. Ensure 'P&L' is in your FPL Manager name or Team name.")
        st.info("Found managers: " + ", ".join([m['player_name'] for m in data]))
else:
    st.error("Could not fetch league data. Check your League ID.")
