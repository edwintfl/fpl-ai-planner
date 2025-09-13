import streamlit as st
import pandas as pd
import numpy as np
import requests
import pulp
from collections import defaultdict

st.set_page_config(page_title="FPL AI Picker", page_icon="⚽", layout="wide")

API_BASE = "https://fantasy.premierleague.com/api"

@st.cache_data(ttl=900)
def fetch_json(url):
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=900)
def get_bootstrap():
    return fetch_json(f"{API_BASE}/bootstrap-static/")

@st.cache_data(ttl=900)
def get_fixtures():
    return fetch_json(f"{API_BASE}/fixtures/")

def gameweek_from_events(events):
    cur = [e for e in events if e.get("is_current")]
    if cur:
        return cur[0]["id"]
    nxt = [e for e in events if e.get("is_next")]
    if nxt:
        return nxt[0]["id"]
    fut = [e for e in events if not e.get("finished")]
    return fut[0]["id"] if fut else events[-1]["id"]

def diff_to_factor(diff):
    return 1.2 - (diff - 1) * (0.4 / 4.0)

def contains_any(name, patterns):
    name_l = (name or "").lower().strip()
    pats = [(p or "").lower().strip() for p in patterns if p]
    return any(p in name_l for p in pats)

st.sidebar.header("Settings")
budget = st.sidebar.number_input("Budget (£m)", min_value=95.0, max_value=110.0, value=100.0, step=0.5)
max_per_team = st.sidebar.slider("Max per team", 1, 3, 3)
lookahead = st.sidebar.slider("Fixture lookahead (GWs)", 1, 6, 3)
use_only_available = st.sidebar.checkbox("Exclude injured/suspended", value=True)

st.sidebar.subheader("Weights")
w_ep = st.sidebar.slider("Weight: Expected Points (ep_next)", 0.0, 2.0, 1.0, 0.1)
w_form = st.sidebar.slider("Weight: Form", 0.0, 2.0, 0.5, 0.1)
w_ppg = st.sidebar.slider("Weight: Points per Game", 0.0, 2.0, 0.25, 0.05)
w_fix = st.sidebar.slider("Weight: Fixture Ease", 0.0, 1.0, 0.3, 0.05)

st.sidebar.subheader("Locks & Excludes")
lock_names = st.sidebar.text_area("Lock player names (comma-separated)", value="").split(",")
exclude_names = st.sidebar.text_area("Exclude player names (comma-separated)", value="").split(",")

st.sidebar.subheader("Soft Club Bias")
bias_club = st.sidebar.text_input("Club short name (e.g., MUN, MCI, ARS)", value="")
bias_boost = st.sidebar.slider("Bias boost (0 = none)", 0.0, 0.5, 0.0, 0.01)

st.title("⚽ FPL AI Picker")
st.caption("Builds a 15-man squad and best XI using live FPL data + an optimization model.")

with st.expander("How scoring works", expanded=False):
    st.write("""
    Each player's score blends:
    - ep_next (FPL expected points next GW),
    - form (FPL rolling form),
    - points_per_game,
    - fixture ease over the next N gameweeks.
    The weights are adjustable in the sidebar. Captaincy adds the XIIth copy of their score (to simulate double points).
    """)

with st.spinner("Fetching FPL data..."):
    boot = get_bootstrap()
    fixtures = get_fixtures()

elements = pd.DataFrame(boot["elements"])
teams = pd.DataFrame(boot["teams"])[["id","name","short_name","strength","strength_attack_home","strength_attack_away","strength_defence_home","strength_defence_away"]]
types = pd.DataFrame(boot["element_types"])[["id","singular_name_short","plural_name_short"]].rename(columns={"id":"element_type"})

players = elements.merge(types, on="element_type", how="left")                  .merge(teams.rename(columns={"id":"team"}), on="team", how="left")

players["player_name"] = players["first_name"] + " " + players["second_name"]
players["team_short"] = players["short_name"]
players["pos"] = players["singular_name_short"]
players["cost"] = players["now_cost"] / 10.0
players["form"] = pd.to_numeric(players["form"], errors="coerce").fillna(0.0)
players["ppg"] = pd.to_numeric(players["points_per_game"], errors="coerce").fillna(0.0)
players["ep_next"] = pd.to_numeric(players["ep_next"], errors="coerce").fillna(0.0)
players["chance_next"] = pd.to_numeric(players["chance_of_playing_next_round"], errors="coerce").fillna(100.0) / 100.0
players["status"] = players["status"]

events = boot["events"]
current_gw = gameweek_from_events(events)
fx_df = pd.DataFrame(fixtures)
upcoming = fx_df[(fx_df["event"].notna()) & (fx_df["event"] >= current_gw)].copy()

from collections import defaultdict
team_ease = defaultdict(list)
for _, row in upcoming.iterrows():
    for side in ["h","a"]:
        t = row[f"team_{side}"]
        d = row[f"team_{side}_difficulty"]
        team_ease[t].append(diff_to_factor(d))

team_fixture_factor = {}
for t in teams["id"]:
    vals = team_ease.get(t, [])
    if len(vals) == 0:
        team_fixture_factor[t] = 1.0
    else:
        vals = vals[:lookahead]
        team_fixture_factor[t] = float(np.mean(vals))

players["fixture_factor"] = players["team"].map(team_fixture_factor).fillna(1.0)

players["score_base"] = w_ep*players["ep_next"] + w_form*players["form"] + w_ppg*players["ppg"]
players["score"] = players["score_base"] * (1.0 - w_fix + w_fix*players["fixture_factor"]) * players["chance_next"]

if bias_club.strip() and bias_boost > 0:
    players.loc[players["team_short"] == bias_club.strip().upper(), "score"] *= (1.0 + bias_boost)

if use_only_available:
    players = players[players["status"] == "a"].copy()

if any(x.strip() for x in exclude_names):
    players = players[~players["player_name"].apply(lambda s: contains_any(s, exclude_names))].copy()

players["is_locked"] = players["player_name"].apply(lambda s: contains_any(s, lock_names))

keep_cols = ["id","player_name","team","team_short","pos","cost","score","ep_next","form","ppg","fixture_factor","chance_next","is_locked"]
players = players[keep_cols].reset_index(drop=True)

if st.button("🔮 Build my squad"):
    idx = list(players.index)
    cost = dict(zip(idx, players["cost"]))
    pos = dict(zip(idx, players["pos"]))
    team = dict(zip(idx, players["team_short"]))
    score = dict(zip(idx, players["score"]))
    locked = dict(zip(idx, players["is_locked"]))

    P = pulp.LpProblem("FPL_Squad", pulp.LpMaximize)
    x = pulp.LpVariable.dicts("pick", idx, 0, 1, cat=pulp.LpBinary)
    y = pulp.LpVariable.dicts("start", idx, 0, 1, cat=pulp.LpBinary)
    c = pulp.LpVariable.dicts("capt", idx, 0, 1, cat=pulp.LpBinary)

    P += pulp.lpSum([y[i]*score[i] for i in idx]) + pulp.lpSum([c[i]*score[i] for i in idx])

    P += pulp.lpSum([x[i]*cost[i] for i in idx]) <= budget
    P += pulp.lpSum([x[i] for i in idx]) == 15
    P += pulp.lpSum([y[i] for i in idx]) == 11
    P += pulp.lpSum([y[i] for i in idx if pos[i] == "GKP"]) == 1
    P += pulp.lpSum([y[i] for i in idx if pos[i] == "DEF"]) >= 3
    P += pulp.lpSum([y[i] for i in idx if pos[i] == "DEF"]) <= 5
    P += pulp.lpSum([y[i] for i in idx if pos[i] == "MID"]) >= 2
    P += pulp.lpSum([y[i] for i in idx if pos[i] == "MID"]) <= 5
    P += pulp.lpSum([y[i] for i in idx if pos[i] == "FWD"]) >= 1
    P += pulp.lpSum([y[i] for i in idx if pos[i] == "FWD"]) <= 3

    P += pulp.lpSum([x[i] for i in idx if pos[i] == "GKP"]) == 2
    P += pulp.lpSum([x[i] for i in idx if pos[i] == "DEF"]) == 5
    P += pulp.lpSum([x[i] for i in idx if pos[i] == "MID"]) == 5
    P += pulp.lpSum([x[i] for i in idx if pos[i] == "FWD"]) == 3

    clubs = sorted(players["team_short"].unique())
    for club in clubs:
        P += pulp.lpSum([x[i] for i in idx if team[i] == club]) <= max_per_team

    for i in idx:
        P += y[i] <= x[i]
        P += c[i] <= y[i]

    P += pulp.lpSum([c[i] for i in idx]) == 1

    for i in idx:
        if locked[i]:
            P += x[i] == 1

    _ = P.solve(pulp.PULP_CBC_CMD(msg=False))

    players["in_squad"] = [int(pulp.value(x[i])) for i in idx]
    players["in_xi"] = [int(pulp.value(y[i])) for i in idx]
    players["is_captain"] = [int(pulp.value(c[i])) for i in idx]

    squad = players[players["in_squad"]==1].copy().sort_values(["in_xi","pos","score"], ascending=[False, True, False])
    xi = players[players["in_xi"]==1].copy().sort_values(["pos","score"], ascending=[True, False])
    cap = xi[xi["is_captain"]==1].iloc[0] if (xi["is_captain"]==1).any() else None

    spent = float((squad["cost"]).sum())
    pred_points = float(xi["score"].sum() + (cap["score"] if cap is not None else 0.0))

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Budget Spent", f"£{spent:.1f}m")
    with col2:
        st.metric("Predicted XI Points (with captain)", f"{pred_points:.2f}")

    st.subheader("Best XI")
    st.dataframe(xi[["player_name","team_short","pos","cost","score","ep_next","form","ppg","fixture_factor","chance_next","is_captain"]], use_container_width=True)

    st.subheader("Full 15-man Squad")
    st.dataframe(squad[["player_name","team_short","pos","cost","score","ep_next","form","ppg","fixture_factor","chance_next","in_xi","is_captain"]], use_container_width=True)

    bench = squad[squad["in_xi"]==0].copy()
    bench_gk = bench[bench["pos"]=="GKP"]
    bench_out = bench[bench["pos"]!="GKP"].sort_values("score", ascending=True)
    bench_order = pd.concat([bench_out, bench_gk], axis=0)
    st.subheader("Bench Order Suggestion (1→4)")
    st.dataframe(bench_order[["player_name","team_short","pos","score"]], use_container_width=True)
else:
    st.info("Adjust settings in the sidebar, then click **Build my squad**.")
