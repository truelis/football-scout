{% macro season_of(date_col) %}
    -- European season convention: a match in Jul-Dec belongs to that year's
    -- season; Jan-Jun belongs to the season that started the previous year.
    case when extract(month from {{ date_col }}) >= 7
         then extract(year from {{ date_col }})
         else extract(year from {{ date_col }}) - 1
    end
{% endmacro %}
