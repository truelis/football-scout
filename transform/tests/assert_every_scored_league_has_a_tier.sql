-- Task 2 acceptance: no competition in the fact table may lack a tier.
--
-- int_player_season admits every first-tier domestic league in the data, so a
-- league missing from seeds/league_tiers.csv would reach fct_player_season with
-- a null tier and null strength_coef - scoring its players on an unadjusted
-- rate. Previously such a league was silently filtered out instead, which is
-- how RU1 and UKR1 stayed invisible.
--
-- Fails loudly with the offending competition_id so the fix is obvious: add the
-- row to the seed.
select
    s.competition_id,
    count(*) as affected_rows
from {{ ref('int_player_season') }} s
left join {{ ref('league_tiers') }} lt on s.competition_id = lt.competition_id
where lt.competition_id is null
group by 1
