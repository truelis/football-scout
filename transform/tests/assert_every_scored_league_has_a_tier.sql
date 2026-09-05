-- Task 2 acceptance: no DOMESTIC LEAGUE competition may lack a tier.
--
-- int_player_season keeps every competition, so cup and European rows reach
-- fct_player_season with a null tier - correct, a cup has no league strength.
-- The real invariant is narrower: any row flagged is_domestic_league must have
-- a seeds/league_tiers.csv entry, or its players would be scored on an
-- unadjusted rate. Previously such a league was silently filtered out instead,
-- which is how RU1 and UKR1 stayed invisible.
--
-- Fails loudly naming the competition_id, so the fix is obvious: seed it.
SELECT
    s.competition_id,
    COUNT(*) AS affected_rows
FROM {{ ref('int_player_season') }} AS s
LEFT JOIN {{ ref('league_tiers') }} AS lt ON s.competition_id = lt.competition_id
WHERE
    s.is_domestic_league
    AND lt.competition_id IS NULL
GROUP BY 1
