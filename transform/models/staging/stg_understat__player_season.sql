-- Rename and cast only. No business logic.
--
-- Two source encodings are translated here, which is what staging is for:
--
--   season   Understat writes a campaign as '2526'. Everything downstream uses
--            the year the season STARTED, matching the Transfermarkt side and
--            macros/season_of.sql, so '2526' becomes 2025.
--
--   league   Understat's own league keys are mapped onto Transfermarkt
--            competition_ids so the two sources can be joined at all. These six
--            are Understat's complete coverage.
SELECT
    player_id AS understat_player_id,
    player AS player_name,
    team AS team_name,
    league AS understat_league,
    2000 + CAST(SUBSTR(season, 1, 2) AS INTEGER) AS season,
    CASE league
        WHEN 'ENG-Premier League' THEN 'GB1'
        WHEN 'ESP-La Liga' THEN 'ES1'
        WHEN 'ITA-Serie A' THEN 'IT1'
        WHEN 'GER-Bundesliga' THEN 'L1'
        WHEN 'FRA-Ligue 1' THEN 'FR1'
        WHEN 'RUS-Premier League' THEN 'RU1'
    END AS competition_id,
    position AS position_codes,
    matches AS appearances,
    minutes AS minutes_played,
    goals,
    assists,
    np_goals,
    shots,
    key_passes,
    yellow_cards,
    red_cards,
    xg,
    np_xg,
    xa,
    xg_chain,
    xg_buildup
FROM {{ source('understat', 'understat_player_season') }}
WHERE player_id IS NOT NULL
