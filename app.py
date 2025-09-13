import streamlit as st
import pandas as pd
import numpy as np
import requests

API = "https://fantasy.premierleague.com/api"

# --------------------------
# Utility functions
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
    if gw is None:
        return get_json(f"{API}/my-team/{team_id}/")
    else:
        return get_json(f"{API}/entry/{team_id}/event/{gw}/picks/")

def safe_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0

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

# map team names
team_map = dict(zip(teams.id, teams.name))
players["team_name"] = players["team"].map(team_map)

# --------------------------
# Weighted scoring
# --------------------------
def weighted_score(pid, horizon=horizon):
    row = players.loc[players["id"]==pid].iloc[0]

    ep_next = safe_float(row.get("ep_next"))
    form = safe_float(row.get("form"))
    ppg = safe_float(row.get("points_per_game"))

    # fixture difficulty (next horizon GWs)
    next_fix = fixtures_df[(fixtures_df["team_h"]==row["team"]) | (fixtures_df["team_a"]==row["team"])]
    diffs = []
    for gw in range(horizon):
        try:
            fdr = next_fix.iloc[gw]["team_h_difficulty"] if next_fix.iloc[gw]["team_h"]==row["team"] else next_fix.iloc[gw]["team_a_difficulty"]
            diffs.append(6 - safe_float(fdr))
        except Exception:
            pass
    avg_diff = np.mean(diffs) if diffs else 3.0

    return 0.5*ep_next + 0.3*form + 0.2*ppg + 0.2*avg_diff

# assign scores
if projection_mode == "Raw FPL ep_next":
    players["score"] = players["ep_next"].apply(safe_float)
else:
    players["score"] = players["id"].apply(weighted_score)

# --------------------------
# Info / Legend
# --------------------------
st.markdown("## ℹ️ How to Read the Stats")
st.write("""
- **Form** → FPL’s recent performance rating (higher = in form).
- **PPG** → Average FPL points per game this season.
- **FPL_ep_next** → Official FPL projected points for next GW.
- **OurScore** → AI’s weighted rating (ep_next + form + PPG + fixture ease).
- **Price (£m)** → Player’s current cost in millions.
""")

# --------------------------
# Debug table
# --------------------------
with st.expander("🔍 Player Projections Debug"):
    dbg = players[["web_name","team_name","element_type","now_cost","form","points_per_game","ep_next","score"]].copy()
    dbg["now_cost"] = dbg["now_cost"] / 10  # convert to £m
    dbg.rename(columns={
        "web_name":"Name",
        "team_name":"Team",
        "element_type":"Pos",
        "now_cost":"Price (£m)",
        "form":"Form",
        "points_per_game":"PPG",
        "ep_next":"FPL_ep_next",
        "score":"OurScore"
    }, inplace=True)
    st.dataframe(dbg.sort_values("OurScore", ascending=False).head(50))

# --------------------------
# Backtest helper
# --------------------------
st.sidebar.markdown("---")
gw_back = st.sidebar.number_input("Backtest: pick past GW", min_value=0, max_value=38, value=0)

if team_id and gw_back > 0:
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
# Placeholder for transfer logic
# --------------------------
st.subheader("🚧 Transfer planner logic will plug in here")
st.info("This version fixes price formatting & adds stat explanations.")
