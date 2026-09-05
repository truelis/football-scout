"""Player drill-down. Phase 1 version: enough to interrogate a ranking.

Phase 4 expands this with percentile bars against a proper peer group and
nearest-neighbour comparables.
"""

from pathlib import Path

import duckdb
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

DB = Path(__file__).resolve().parents[2] / "data" / "scout.duckdb"
st.set_page_config(page_title="Scout — Player", page_icon="⚽", layout="wide")


@st.cache_data(ttl=300)
def q(sql: str, params: list | None = None):
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return con.execute(sql, params or []).df()
    finally:
        con.close()


players = q(
    "SELECT player_id, player_name, current_club_name, league_name "
    "FROM mart_shortlist ORDER BY composite_score DESC"
)
if players.empty:
    st.warning("Shortlist is empty — run `dbt build` first.")
    st.stop()

# league_name comes from the player's CURRENT club, which may sit outside the
# seeded leagues even though he was scored on minutes inside them - so it can be
# null. Render that as "league unknown" rather than a bare "(nan)".
labels = {
    int(r.player_id): f"{r.player_name} — {r.current_club_name} "
    f"({r.league_name if pd.notna(r.league_name) else 'league unknown'})"
    for r in players.itertuples()
}
pid = st.selectbox("Player", list(labels), format_func=lambda k: labels[k])

row = q("SELECT * FROM mart_shortlist WHERE player_id = ?", [pid]).iloc[0]

st.title(row["player_name"])
c = st.columns(6)
c[0].metric("Age", f"{row['age']:.1f}")
c[1].metric("Position", row["sub_position"] or row["position_group"])
c[2].metric("Value", f"€{row['current_market_value_eur'] / 1e6:.2f}m")
c[3].metric("Est. fee", f"€{row['estimated_fee_eur'] / 1e6:.2f}m")
# pd.notna, NOT the `x == x` NaN idiom: contract_months_remaining arrives as a
# nullable Int64, so a null is pd.NA, and `pd.NA == pd.NA` is pd.NA - truthiness
# on which raises. 37% of players upstream have no contract_expiration_date, so
# this crashed the page for 16 of the 216 shortlisted.
c[4].metric(
    "Contract",
    f"{row['contract_months_remaining']:.0f}m"
    if pd.notna(row["contract_months_remaining"])
    else "—",
)
c[5].metric("Score", f"{row['composite_score']:.1f}")

if row["confidence"] == "low":
    st.warning(
        "Low confidence: Phase 1 scores defenders on attacking output only. "
        "There are no defensive metrics in this dataset yet."
    )

# ---- score decomposition: why is he ranked here ----
st.subheader("Score decomposition")
fig = go.Figure(
    go.Bar(
        x=[
            row["performance_score"],
            row["trajectory_score"],
            row["availability_score"],
        ],
        y=["Performance", "Trajectory", "Availability"],
        orientation="h",
        text=[
            f"{row[k]:.0f}" for k in ["performance_score", "trajectory_score", "availability_score"]
        ],
    )
)
fig.update_layout(height=220, xaxis_range=[0, 100], margin={"l": 0, "r": 0, "t": 10, "b": 10})
st.plotly_chart(fig, use_container_width=True)

# ---- market value history ----
st.subheader("Market value history")
hist = q(
    "SELECT valuation_date, market_value_eur FROM fct_player_valuations "
    "WHERE player_id = ? ORDER BY valuation_date",
    [pid],
)
if len(hist) > 1:
    st.line_chart(hist.set_index("valuation_date")["market_value_eur"])
else:
    st.caption("Not enough valuation history.")

# ---- season-by-season ----
st.subheader("Season by season")
st.dataframe(
    q(
        """SELECT season, league_name, appearances, minutes_played, goals, assists,
                round(ga_per90, 2) AS ga_per90
         FROM fct_player_season WHERE player_id = ? ORDER BY season DESC""",
        [pid],
    ),
    hide_index=True,
    use_container_width=True,
)
