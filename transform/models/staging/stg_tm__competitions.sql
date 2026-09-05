-- Rename and cast only. No business logic.
--
-- Upstream has no `is_major_national_league` flag (an earlier version of this
-- model selected one and failed to build). The same idea is expressed through
-- `type` and `sub_type`: `domestic_league` + `first_tier` isolates the 31
-- top-flight domestic leagues from cups, super cups and European competitions.
-- Kept as a derived boolean so downstream models get the concept, not the
-- encoding.
select
    competition_id,
    competition_code,
    name                                        as competition_name,
    country_id,
    country_name,
    type                                        as competition_type,
    sub_type,
    domestic_league_code,
    confederation,
    total_clubs,
    type = 'domestic_league'
      and sub_type = 'first_tier'               as is_first_tier_domestic_league
from {{ source('tm', 'competitions') }}
where competition_id is not null
