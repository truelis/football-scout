"""Shortlist view - the app's landing page."""
import math
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

DB = Path(__file__).resolve().parents[1] / "data" / "scout.duckdb"

st.set_page_config(page_title="Scout — Shortlist", page_icon="⚽", layout="wide")


@st.cache_data(ttl=300)
def load() -> pd.DataFrame:
    con = duckdb.connect(str(DB), read_only=True)
    try:
        return con.execute("SELECT * FROM mart_shortlist ORDER BY composite_score DESC").df()
    finally:
        con.close()


if not DB.exists():
    st.error("No warehouse found. Run `python ingest/transfermarkt.py` then `dbt build`.")
    st.stop()

df = load()

# A player scored on minutes in a seeded league can have a current club outside
# one, leaving league_name null. Those rows would silently vanish from an
# .isin() filter built off dropna(), so name the gap and let it be selected.
df["league_name"] = df["league_name"].fillna("(unknown)")

st.title("Shortlist")
st.caption(
    f"{len(df):,} players under the budget cap. Scores are relative to positional "
    "peers, not absolute quality. Phase 1 uses Transfermarkt data only — no xG yet."
)

# ---------------------------------------------------------------- filters
with st.sidebar:
    st.header("Filters")
    positions = sorted(df["position_group"].dropna().unique())
    pos = st.multiselect("Position", positions, default=positions)
    leagues = sorted(df["league_name"].dropna().unique())
    lg = st.multiselect("League", leagues, default=leagues)
    # ceil, not int: age is fractional, so int(22.97) defaulted the slider to 22
    # and hid the 87 players between 22.01 and 22.97 - 40% of the shortlist,
    # invisible on load with no indication anything had been filtered.
    max_age = st.slider("Max age", 16, 30, math.ceil(df["age"].max()))
    max_val = st.slider("Max market value (€m)", 0.0, 10.0,
                        float(df["current_market_value_eur"].max() / 1e6), 0.25)
    min_mins = st.slider("Min minutes", 0, 3400, 900, 100)
    # Left at 900 deliberately - it is the owner's call, not a bug to fix here.
    # But it silently overrides the mart's own eligibility rule, which admits
    # 600+ when minutes are rising, so say so rather than let it hide the
    # newcomers this tool exists to find.
    st.caption(
        f"The shortlist itself admits 600+ minutes when rising. "
        f"{int((df['minutes_played'] < 900).sum())} players sit in the 600–899 band."
    )
    contract = st.multiselect("Contract status",
                              sorted(df["contract_status"].dropna().unique()),
                              default=sorted(df["contract_status"].dropna().unique()))
    st.divider()
    st.caption(
        "**Confidence**: attackers and midfielders are scored on goal "
        "contributions. Defenders have no defensive metrics in Phase 1 — their "
        "scores are marked low confidence and should not be trusted yet. "
        "Goalkeepers are excluded entirely."
    )

f = df[
    df["position_group"].isin(pos)
    & df["league_name"].isin(lg)
    & (df["age"] <= max_age)
    & (df["current_market_value_eur"] <= max_val * 1e6)
    & (df["minutes_played"] >= min_mins)
    & df["contract_status"].isin(contract)
].copy()

# ---------------------------------------------------------------- summary
c1, c2, c3, c4 = st.columns(4)
c1.metric("Players", f"{len(f):,}")
c2.metric("Median age", f"{f['age'].median():.1f}" if len(f) else "—")
c3.metric("Median value", f"€{f['current_market_value_eur'].median()/1e6:.2f}m" if len(f) else "—")
c4.metric("Expiring ≤12m", f"{(f['contract_status'] == 'expiring').sum():,}")

# ---------------------------------------------------------------- one-line read
def tag(r) -> str:
    bits = [f"{r['age']:.0f}"]
    if pd.notna(r["prev_minutes"]) and r["prev_minutes"] > 0:
        g = r["minutes_played"] / r["prev_minutes"] - 1
        if g > 0.25:
            bits.append("minutes rising")
    if r["contract_status"] == "expiring":
        bits.append(f"{r['contract_months_remaining']:.0f}m left")
    elif r["contract_status"] == "leverage":
        bits.append("contract leverage")
    if pd.notna(r["ga_per90"]) and r["ga_per90"] > 0.5:
        bits.append(f"{r['ga_per90']:.2f} G+A/90")
    return ", ".join(bits)


if len(f):
    f["read"] = f.apply(tag, axis=1)

cols = ["rank_in_position", "player_name", "age", "position_group", "current_club_name",
        "league_name", "current_market_value_eur", "estimated_fee_eur",
        "contract_months_remaining", "minutes_played", "ga_per90",
        "performance_score", "trajectory_score", "availability_score",
        "composite_score", "confidence", "read"]

st.dataframe(
    f[cols],
    hide_index=True,
    use_container_width=True,
    column_config={
        "rank_in_position": st.column_config.NumberColumn("#", width="small"),
        "player_name": "Player",
        "age": st.column_config.NumberColumn("Age", format="%.1f"),
        "position_group": "Pos",
        "current_club_name": "Club",
        "league_name": "League",
        "current_market_value_eur": st.column_config.NumberColumn("Value", format="€%.0f"),
        "estimated_fee_eur": st.column_config.NumberColumn("Est. fee", format="€%.0f"),
        "contract_months_remaining": st.column_config.NumberColumn("Contract (m)"),
        "minutes_played": st.column_config.NumberColumn("Mins"),
        "ga_per90": st.column_config.NumberColumn("G+A/90", format="%.2f"),
        "performance_score": st.column_config.ProgressColumn("Perf", min_value=0, max_value=100, format="%.0f"),
        "trajectory_score": st.column_config.ProgressColumn("Traj", min_value=0, max_value=100, format="%.0f"),
        "availability_score": st.column_config.ProgressColumn("Avail", min_value=0, max_value=100, format="%.0f"),
        "composite_score": st.column_config.NumberColumn("Score", format="%.1f"),
        "confidence": "Conf.",
        "read": "Read",
    },
)

st.download_button("Download CSV", f[cols].to_csv(index=False),
                   "shortlist.csv", "text/csv")
