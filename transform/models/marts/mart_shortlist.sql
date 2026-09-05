-- The filtered, ranked output. This is what the app opens on.
WITH scored AS (
    SELECT
        *,
        ROUND((0.5 * age_score + 0.3 * minutes_trend_score + 0.2 * value_trend_score), 1)
            AS trajectory_score
    FROM {{ ref('mart_player_scores') }}
),

composite AS (
    SELECT
        *,
        ROUND((
            {{ var('w_performance') }} * performance_score
            + {{ var('w_trajectory') }} * trajectory_score
            + {{ var('w_availability') }} * availability_score
        ) / (
            {{ var('w_performance') }} + {{ var('w_trajectory') }}
            + {{ var('w_availability') }}
        ), 1) AS composite_score
    FROM scored
),

filtered AS (
    SELECT * FROM composite
    WHERE
        current_market_value_eur <= {{ var('max_market_value_eur') }}
        AND age <= {{ var('max_age') }}
        AND (
            minutes_played >= {{ var('min_minutes') }}
            OR (
                minutes_played >= {{ var('min_minutes_if_trending') }}
                AND minutes_played > COALESCE(prev_minutes, 0)
            )
        )
)

SELECT
    ROW_NUMBER() OVER (ORDER BY composite_score DESC) AS rank,
    -- Defenders score on attacking output only in Phase 1, so a global rank
    -- flatters attackers. Rank within position group too; the app defaults
    -- to this one.
    ROW_NUMBER() OVER (
        PARTITION BY position_group
        ORDER BY composite_score DESC
    ) AS rank_in_position,
    *
FROM filtered
ORDER BY composite_score DESC
