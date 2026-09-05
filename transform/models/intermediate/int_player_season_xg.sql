-- Understat advanced stats, keyed to Transfermarkt player_ids.
--
-- Grain matches int_player_season: player x season x competition. Understat's
-- own grain is player x season x TEAM, so a player who changed club inside one
-- league mid-season has two rows there; they are summed here. Rates are left to
-- the consumer - summing xG and minutes then dividing is correct, averaging two
-- per-90 rates is not.
--
-- Coverage is partial BY NATURE, not by accident: Understat publishes the top
-- five leagues plus Russia and nothing else, so most of the shortlist has no
-- row here at all. Downstream must treat a missing row as "not measured",
-- never as zero.
WITH matched AS (
    SELECT
        u.season,
        u.competition_id,
        i.player_id,
        u.minutes_played,
        u.goals,
        u.assists,
        u.np_goals,
        u.shots,
        u.key_passes,
        u.xg,
        u.np_xg,
        u.xa,
        u.xg_chain,
        u.xg_buildup
    FROM {{ ref('stg_understat__player_season') }} AS u
    INNER JOIN {{ ref('int_player_identity') }} AS i
        ON u.understat_player_id = i.understat_player_id
)

SELECT
    player_id,
    season,
    competition_id,
    SUM(minutes_played) AS understat_minutes,
    SUM(goals) AS understat_goals,
    SUM(assists) AS understat_assists,
    SUM(np_goals) AS np_goals,
    SUM(shots) AS shots,
    SUM(key_passes) AS key_passes,
    SUM(xg) AS xg,
    SUM(np_xg) AS np_xg,
    SUM(xa) AS xa,
    SUM(xg_chain) AS xg_chain,
    SUM(xg_buildup) AS xg_buildup,
    -- Per-90s, guarded against a zero-minute row.
    CASE
        WHEN SUM(minutes_played) > 0
            THEN SUM(np_xg) * 90.0 / SUM(minutes_played)
    END AS np_xg_per90,
    CASE
        WHEN SUM(minutes_played) > 0
            THEN SUM(xa) * 90.0 / SUM(minutes_played)
    END AS xa_per90,
    CASE
        WHEN SUM(minutes_played) > 0
            THEN (SUM(np_xg) + SUM(xa)) * 90.0 / SUM(minutes_played)
    END AS npxg_xa_per90,
    CASE
        WHEN SUM(minutes_played) > 0
            THEN SUM(shots) * 90.0 / SUM(minutes_played)
    END AS shots_per90,
    CASE
        WHEN SUM(minutes_played) > 0
            THEN SUM(key_passes) * 90.0 / SUM(minutes_played)
    END AS key_passes_per90,
    CASE
        WHEN SUM(minutes_played) > 0
            THEN SUM(xg_chain) * 90.0 / SUM(minutes_played)
    END AS xg_chain_per90,
    CASE
        WHEN SUM(minutes_played) > 0
            THEN SUM(xg_buildup) * 90.0 / SUM(minutes_played)
    END AS xg_buildup_per90,
    -- Finishing vs npxG. SPEC 5.2 is explicit that this is NOISE over a single
    -- season, not skill. Retained because the drill-down should be able to show
    -- it; it must not be fed into a score.
    SUM(np_goals) - SUM(np_xg) AS np_goals_minus_npxg
FROM matched
GROUP BY 1, 2, 3
