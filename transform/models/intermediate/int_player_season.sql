-- One row per player per season per competition: the raw production totals.
--
-- EVERY competition is kept - domestic leagues, cups, European ties, the lot.
-- Nothing is filtered out here. What varies by competition is whether a row
-- belongs in a *scoring* sample, and that is a question for the model that
-- scores, not for the model that aggregates. So the competition's nature is
-- carried as attributes and the decision is made downstream.
--
-- This matters beyond tidiness: SPEC.md 5.3 makes "moved into European
-- competition" a Trajectory signal, and cup minutes are squad-role evidence for
-- the Availability axis. Dropping those rows here would silently foreclose both.
--
-- What must NOT happen is pooling cup and league appearances into one per-90
-- rate - different opposition, different rotation, wildly different sample
-- sizes, so a player's rate would depend on how far his club ran in a cup.
-- mart_player_scores restricts to is_domestic_league for exactly that reason.
--
-- Note the LEFT join and the coalesce: four competition_ids in appearances
-- (POCP, CGB, KLUB, UKRS - all cups, ~14k rows) have no row in `competitions`
-- at all, so an inner join would drop them. They are kept with a null
-- competition_type and is_domestic_league = false, and
-- tests/assert_appearance_competitions_known.sql warns if the set grows.
WITH apps AS (
    SELECT * FROM {{ ref('stg_tm__appearances') }}
),

comps AS (
    SELECT * FROM {{ ref('stg_tm__competitions') }}
)

SELECT
    a.player_id,
    a.season,
    a.competition_id,
    c.competition_type,
    c.sub_type AS competition_sub_type,
    COALESCE(c.is_first_tier_domestic_league, FALSE) AS is_domestic_league,
    COUNT(*) AS appearances,
    SUM(a.minutes_played) AS minutes_played,
    SUM(a.goals) AS goals,
    SUM(a.assists) AS assists,
    SUM(a.goals) + SUM(a.assists) AS goal_contributions,
    SUM(a.yellow_cards) AS yellow_cards,
    SUM(a.red_cards) AS red_cards,
    COUNT(*) FILTER (WHERE a.minutes_played >= 60) AS substantial_appearances,
    -- per-90 rates. Guarded: null rather than divide-by-zero, and the
    -- minutes threshold is applied downstream, not hidden here.
    CASE
        WHEN SUM(a.minutes_played) > 0
            THEN SUM(a.goals) * 90.0 / SUM(a.minutes_played)
    END AS goals_per90,
    CASE
        WHEN SUM(a.minutes_played) > 0
            THEN SUM(a.assists) * 90.0 / SUM(a.minutes_played)
    END AS assists_per90,
    CASE
        WHEN SUM(a.minutes_played) > 0
            THEN
                (SUM(a.goals) + SUM(a.assists)) * 90.0
                / SUM(a.minutes_played)
    END AS ga_per90
FROM apps AS a
LEFT JOIN comps AS c ON a.competition_id = c.competition_id
GROUP BY 1, 2, 3, 4, 5, 6
