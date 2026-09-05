"""Resolve Understat players to Transfermarkt players.

SPEC 4.2 calls this the single most annoying part of the project, and it is:
two sources with no shared key, different transliterations of the same name,
and mid-season transfers that move a player between clubs inside one season.

A Python model rather than SQL because the fuzzy step needs rapidfuzz. It sits
in the dbt DAG like any other model, so lineage and tests still apply.

Strategy, in the order SPEC 4.2 sets out - each pass only sees names the
previous passes failed to match, so a cheap confident match always wins over an
expensive uncertain one:

  1. exact match on normalised name, within league + season
  2. fuzzy match (token_set_ratio) within league + season
  3. fuzzy match on name + birth year, ignoring league - catches players who
     moved between covered leagues mid-season
  4. seeds/player_id_overrides.csv - the manual escape hatch

League + season is the constraint rather than club + season, deliberately: club
names differ between the sources ("Arsenal" vs "Arsenal FC") so constraining by
club would mean resolving clubs first - a second entity-resolution problem to
solve the first. League + season narrows the candidate pool to ~500 either way.

Output grain is one row per understat_player_id. A player appearing in two
league-seasons resolves once, on his best-scoring match.
"""


def _normalise(series):
    """Casefold, strip accents and punctuation, collapse whitespace.

    'Nicolò Zaniolo' and 'Nicolo Zaniolo' must land on the same key, or the
    exact pass fails for most of Serie A and the fuzzy pass has to clean up
    work that costs nothing to avoid here.
    """
    from unidecode import unidecode

    return (
        series.fillna("")
        .map(unidecode)
        .str.lower()
        .str.replace(r"[^a-z\s]", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def model(dbt, session):
    import pandas as pd
    from rapidfuzz import fuzz, process

    dbt.config(materialized="table", packages=["rapidfuzz", "pandas", "Unidecode"])

    threshold = dbt.config.get("fuzzy_threshold") or 90

    us = dbt.ref("stg_understat__player_season").df()
    tm_season = dbt.ref("int_player_season").df()
    tm_players = dbt.ref("stg_tm__players").df()
    overrides = dbt.ref("player_id_overrides").df()

    # The Transfermarkt candidate pool: players who actually appeared in a
    # league-season Understat also covers. Restricting to those competitions is
    # what makes the fuzzy pass tractable - matching against all 50k players
    # would be both slow and far less accurate.
    covered = us[["competition_id", "season"]].drop_duplicates()
    tm = (
        tm_season.merge(covered, on=["competition_id", "season"], how="inner")
        .groupby(["player_id", "competition_id", "season"], as_index=False)["minutes_played"]
        .sum()
        .merge(
            tm_players[["player_id", "player_name", "date_of_birth"]],
            on="player_id",
            how="left",
        )
    )
    tm["name_key"] = _normalise(tm["player_name"])
    tm["birth_year"] = pd.to_datetime(tm["date_of_birth"], errors="coerce").dt.year

    us = us.copy()
    us["name_key"] = _normalise(us["player_name"])

    matches = []

    # ---- pass 1: exact normalised name within league + season ----------------
    exact = us.merge(
        tm[["player_id", "competition_id", "season", "name_key", "birth_year"]],
        on=["name_key", "competition_id", "season"],
        how="inner",
    )
    exact = exact.assign(match_method="exact_name_league_season", match_score=100.0)
    matches.append(exact[["understat_player_id", "player_id", "match_method", "match_score"]])
    done = set(exact["understat_player_id"])

    # ---- pass 2: fuzzy name within league + season ---------------------------
    # token_set_ratio because the sources disagree on name ORDER and on how many
    # of a player's names they carry ("Vinicius Junior" vs "Vinicius Jose de
    # Oliveira Junior"); it scores on the shared token set rather than position.
    remaining = us[~us["understat_player_id"].isin(done)]
    for (comp, season), grp in remaining.groupby(["competition_id", "season"]):
        pool = tm[(tm["competition_id"] == comp) & (tm["season"] == season)]
        if pool.empty:
            continue
        choices = pool["name_key"].tolist()
        ids = pool["player_id"].tolist()
        for row in grp.itertuples():
            hit = process.extractOne(
                row.name_key, choices, scorer=fuzz.token_set_ratio, score_cutoff=threshold
            )
            if hit:
                matches.append(
                    pd.DataFrame(
                        [
                            {
                                "understat_player_id": row.understat_player_id,
                                "player_id": ids[hit[2]],
                                "match_method": "fuzzy_name_league_season",
                                "match_score": float(hit[1]),
                            }
                        ]
                    )
                )
                done.add(row.understat_player_id)

    # ---- pass 3: fuzzy name + birth year, league ignored ---------------------
    # For players who changed covered league mid-season: Understat lists them
    # under the league they played in, Transfermarkt under each. Birth year
    # replaces league as the constraint that keeps this from matching namesakes.
    still = us[~us["understat_player_id"].isin(done)]
    if not still.empty:
        pool = tm.dropna(subset=["birth_year"]).drop_duplicates("player_id")
        choices = pool["name_key"].tolist()
        ids = pool["player_id"].tolist()
        for row in still.itertuples():
            hit = process.extractOne(
                row.name_key, choices, scorer=fuzz.token_set_ratio, score_cutoff=threshold
            )
            if hit:
                matches.append(
                    pd.DataFrame(
                        [
                            {
                                "understat_player_id": row.understat_player_id,
                                "player_id": ids[hit[2]],
                                "match_method": "fuzzy_name_birth_year",
                                "match_score": float(hit[1]),
                            }
                        ]
                    )
                )

    resolved = (
        pd.concat(matches, ignore_index=True)
        if matches
        else pd.DataFrame(
            columns=["understat_player_id", "player_id", "match_method", "match_score"]
        )
    )

    # One row per Understat player: keep his best-scoring match, preferring the
    # earlier (more constrained) passes on ties.
    rank = {
        "exact_name_league_season": 0,
        "fuzzy_name_league_season": 1,
        "fuzzy_name_birth_year": 2,
    }
    resolved["_rank"] = resolved["match_method"].map(rank)
    resolved = (
        resolved.sort_values(
            ["understat_player_id", "_rank", "match_score"], ascending=[True, True, False]
        )
        .drop_duplicates("understat_player_id")
        .drop(columns="_rank")
    )

    # ---- enforce 1:1 --------------------------------------------------------
    # understat_player_id is stable per player, so two of them resolving to one
    # Transfermarkt player means at most one is right. It happens with genuine
    # namesakes - three different Roberto Fernandez in La Liga - where fuzzy
    # matching cannot tell them apart on name alone.
    #
    # Keep the best-scoring claim and leave the losers UNMATCHED. An unmatched
    # player simply has no xG and is scored on Transfermarkt data like everyone
    # outside Understat's coverage; a wrong match silently attributes another
    # man's xG and is far more expensive than the gap it fills.
    resolved = resolved.sort_values(
        ["player_id", "match_score"], ascending=[True, False]
    ).drop_duplicates("player_id")

    # ---- pass 4: manual overrides win outright ------------------------------
    if not overrides.empty:
        ov = overrides.dropna(subset=["understat_player_id", "player_id"]).copy()
        ov["match_method"] = "manual_override"
        ov["match_score"] = 100.0
        resolved = pd.concat(
            [
                ov[resolved.columns],
                resolved[~resolved["understat_player_id"].isin(ov["understat_player_id"])],
            ],
            ignore_index=True,
        )

    return resolved.astype(
        {"understat_player_id": "int64", "player_id": "int64", "match_score": "float64"}
    )
