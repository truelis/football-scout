-- Player x season production, joined to league context. The grain the
-- scoring model reads from.
SELECT
    s.player_id,
    s.season,
    s.competition_id,
    s.competition_type,
    s.competition_sub_type,
    s.is_domestic_league,
    lt.league_name,
    lt.tier,
    lt.strength_coef,
    d.position_group,
    d.age - (DATE_PART('year', DATE '{{ var("as_of_date") }}') - s.season) AS age_in_season,
    s.appearances,
    s.substantial_appearances,
    s.minutes_played,
    s.goals,
    s.assists,
    s.goal_contributions,
    s.goals_per90,
    s.assists_per90,
    s.ga_per90,
    -- league-adjusted output: the core Phase 1 comparability fix.
    -- Null for cup and European rows, which have no league coefficient.
    s.ga_per90 * lt.strength_coef AS ga_per90_adj,

    -- ---- Understat, top five leagues + Russia only ----
    -- NULL here means "not measured", never zero. Most rows have no xG because
    -- Understat does not cover their league at all.
    x.np_xg,
    x.xa,
    x.shots,
    x.key_passes,
    x.xg_chain,
    x.xg_buildup,
    x.np_xg_per90,
    x.xa_per90,
    x.npxg_xa_per90,
    x.shots_per90,
    x.key_passes_per90,
    x.xg_chain_per90,
    x.xg_buildup_per90,
    x.np_goals_minus_npxg,
    x.understat_minutes,
    x.npxg_xa_per90 * lt.strength_coef AS npxg_xa_per90_adj,
    x.player_id IS NOT NULL AS has_xg
FROM {{ ref('int_player_season') }} AS s
LEFT JOIN {{ ref('league_tiers') }} AS lt ON s.competition_id = lt.competition_id
LEFT JOIN {{ ref('dim_player') }} AS d USING (player_id)
LEFT JOIN {{ ref('int_player_season_xg') }} AS x
    ON
        s.player_id = x.player_id
        AND s.season = x.season
        AND s.competition_id = x.competition_id
-- No filter at all here, deliberately. This model is the full player x season
-- x competition record: cups and European ties included, each carrying
-- is_domestic_league so a consumer can choose its own sample.
--
-- tier and strength_coef are therefore null for cup rows, which is correct - a
-- cup has no league strength. The invariant worth testing is narrower: every
-- DOMESTIC row must have a tier. tests/assert_every_scored_league_has_a_tier
-- enforces that, so a league with data but no seed row fails the build instead
-- of being silently dropped - which is exactly how RU1 and UKR1 went unnoticed.
