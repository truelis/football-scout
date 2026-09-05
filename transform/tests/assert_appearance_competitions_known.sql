-- Referential integrity: every competition_id in appearances should exist in
-- the competitions dimension.
--
-- It currently does NOT hold upstream - POCP (Taça da Liga), CGB (EFL Cup),
-- KLUB (Club World Cup) and UKRS (Ukrainian Super Cup) appear in ~14k
-- appearance rows with no `competitions` row at all. All four are cups, so
-- none belongs in the scoring sample, and int_player_season's positive
-- `is_first_tier_domestic_league` filter already excludes them.
--
-- This test is therefore a WATCHDOG, not a bug: it is warn-severity and exists
-- so that a NEW orphan - which might be a league we want - gets noticed instead
-- of being silently dropped by that same filter.
{{ config(severity = 'warn') }}

select
    a.competition_id,
    count(*) as appearance_rows
from {{ ref('stg_tm__appearances') }} a
left join {{ ref('stg_tm__competitions') }} c using (competition_id)
where c.competition_id is null
group by 1
