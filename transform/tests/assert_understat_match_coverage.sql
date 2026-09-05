-- SPEC 4.2 step 5 / CLAUDE.md: fail the build if top-5-league Transfermarkt to
-- Understat match coverage drops below the configured floor.
--
-- Coverage is the health metric for entity resolution. Names drift upstream,
-- Understat re-transliterates, a scrape half-fails - and none of that raises an
-- error on its own. It just quietly produces a shortlist scored without xG,
-- which looks exactly like a shortlist scored with it.
--
-- Scoped two ways, both deliberate:
--   * only seasons actually present in the Understat parquet. We ingest 2024
--     and 2025; measuring 2012 would report 5% coverage and fail forever.
--   * only players above a minutes floor. Fringe players who played 20 minutes
--     are frequently absent from Understat entirely, and letting them drag the
--     rate down would mean setting the threshold by noise.
WITH ingested AS (
    SELECT DISTINCT
        season,
        competition_id
    FROM {{ ref('stg_understat__player_season') }}
),

top5 AS (
    SELECT competition_id
    FROM {{ ref('league_tiers') }}
    WHERE tier = 1
),

tm AS (
    SELECT
        s.competition_id,
        s.season,
        s.player_id,
        SUM(s.minutes_played) AS mins
    FROM {{ ref('int_player_season') }} AS s
    INNER JOIN ingested AS i
        ON s.competition_id = i.competition_id AND s.season = i.season
    INNER JOIN top5 AS t ON s.competition_id = t.competition_id
    WHERE s.is_domestic_league
    GROUP BY 1, 2, 3
)

SELECT
    tm.competition_id,
    tm.season,
    COUNT(*) AS eligible_players,
    COUNT(m.player_id) AS matched_players,
    ROUND(100.0 * COUNT(m.player_id) / NULLIF(COUNT(*), 0), 1) AS coverage_pct
FROM tm
LEFT JOIN {{ ref('int_player_identity') }} AS m ON tm.player_id = m.player_id
WHERE tm.mins >= {{ var('understat_coverage_min_minutes') }}
GROUP BY 1, 2
HAVING
    ROUND(100.0 * COUNT(m.player_id) / NULLIF(COUNT(*), 0), 1)
    < {{ var('understat_coverage_min_pct') }}
