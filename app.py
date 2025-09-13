import streamlit as st
import pandas as pd
import numpy as np
import requests
from datetime import datetime

API = "https://fantasy.premierleague.com/api"

# --------------------------
# Utility
# --------------------------
@st.cache_data(ttl=900)
def get_json(url):
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()

def bootstrap():
    return get_json(f"{API}/bootstrap-static/")

def fixtures():
    return get_json(f"{API}/fixtures/")

def get_team(team_id, gw=None):
    # current picks
    if gw is None:
        return get_json(f"{API}/my-team/{team_id}/")
    else:
        return get_json(f"{API}/entry/{team_id}/event/{gw}/picks/")

# --------------------------
# Sidebar controls
# --------------------------
st.sidebar.title("⚙️ Settings")

team_id = st.sidebar.text_input("Your FPL Team ID", "")
horizon = st.sidebar.slider("GW horizon (weighted)", 1, 3, 3)
projection_mode = st.sidebar.radio("Projection mode", ["Weighted (default)", "Raw FPL ep_next"])
free_transfers = st.sidebar.selectbox("Free transfers available", [1,2], index=0)
allow_hits = st.sidebar.checkbox("Allow -4 hits?", True)

# --------------------------
# Load data
# --------------------------
boot = bootstrap()
players = pd.DataFrame(boot["elements"])
teams = pd.DataFrame(boot["teams"])
fixtures_df = pd.DataFrame(fixtures())

# merge team names
team_map = dict(zip(teams.id, teams.name))
players["team"] = players["team"].map(team_map)

# --------------------------
# Projection logic
# --------------------------
def weighted_score(pid, horizon=horizon):
    row = players.loc[players["id"]==pid].iloc[0]
    ep_next = row["ep_next"]
    form = float(row["form"])
    ppg = float(row["points_per_game"])
    # ...
    return 0.5*ep_next + 0.3*form + 0.2*ppg + 0.2*avg_diff


if projection_mode=="Raw FPL ep_next":
    players["score"] = players["ep_next"]
else:
    players["score"] = players["id"].apply(weighted_score)

# --------------------------
# Show debug table
# --------------------------
with st.expander("🔍 Player Projections Debug"):
    dbg = players[["web_name","team","element_type","form","points_per_game","ep_next","score"]].copy()
    dbg.rename(columns={
        "web_name":"Name","team":"Team","element_type":"Pos",
        "form":"Form","points_per_game":"PPG","ep_next":"FPL_ep_next","score":"OurScore"
    }, inplace=True)
    st.dataframe(dbg.sort_values("OurScore", ascending=False).head(50))

# --------------------------
# Backtest helper
# --------------------------
st.sidebar.markdown("---")
gw_back = st.sidebar.number_input("Backtest: pick past GW", min_value=1, max_value=38, value=0)

if team_id and gw_back>0:
    try:
        hist = get_team(team_id, gw_back)
        picks = pd.DataFrame(hist["picks"])
        st.subheader(f"📊 Backtest GW{gw_back}")
        st.write("Predicted vs Actual points for your XI (approximate)")
        merged = picks.merge(players, left_on="element", right_on="id", how="left")
        merged["Predicted"] = merged["score"]
        merged["Actual"] = merged["total_points"]
        st.dataframe(merged[["web_name","Predicted","Actual"]])
    except Exception as e:
        st.warning(f"Could not load backtest data: {e}")

# --------------------------
# Future: transfer planner (placeholder)
# --------------------------
st.subheader("🚧 Transfer planner logic here (uses score column)")
st.info("Your existing transfer logic will plug in here — this version adds debug + toggle + backtest.")
