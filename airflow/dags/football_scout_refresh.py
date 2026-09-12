"""Weekly refresh: pull the three sources, rebuild the warehouse, run the tests.

    ingest_transfermarkt ─┐   (required)
    ingest_understat ─────┼──▶ dbt_build ──▶ report
    ingest_clubelo ───────┘   (optional)

Three design decisions worth understanding, because they are the reason this is
a DAG rather than a shell script.

1. THE INGESTS RUN IN PARALLEL, THE BUILD DOES NOT.
   The three sources are independent, so they fan out. dbt then runs alone -
   DuckDB permits a single writer, so a second concurrent `dbt build` would fail
   with a lock error. Airflow expresses that constraint in the graph itself
   rather than in a comment nobody reads.

2. NOT EVERY SOURCE IS REQUIRED.
   Transfermarkt is the spine: no market values, no contracts, no appearances,
   nothing to build. If it fails the run must stop.

   Understat and Club Elo are enrichment. Without Understat the model scores on
   goal contributions instead of xG; without Club Elo league strength falls back
   to the placeholder seed coefficients. Both are degraded, neither is broken -
   and Club Elo's API returned HTTP 502 for days during Phase 2, which is exactly
   the kind of upstream outage that must not block a weekly refresh.

   So the optional tasks convert failure into a SKIP, and `dbt_build` uses
   trigger_rule NONE_FAILED. A skip is not a failure, so the build proceeds; a
   genuine Transfermarkt failure still stops everything.

3. RETRIES ARE PER-SOURCE, NOT GLOBAL.
   A 211MB download and a flaky scraper deserve different patience. Club Elo gets
   the most retries with the longest backoff because it is the one that actually
   breaks.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta

import pendulum
from airflow.exceptions import AirflowSkipException
from airflow.sdk import dag, task
from airflow.task.trigger_rule import TriggerRule  # airflow.utils path is deprecated in 3.3

PROJECT_DIR = os.environ.get("PROJECT_DIR", "/opt/project")

# The project's dependencies live in their own virtualenv, NOT Airflow's. dbt-core
# and Airflow pin Jinja2 in incompatible ranges, and installing them together
# breaks Airflow itself. See airflow/Dockerfile.
VENV_PY = os.environ.get("PROJECT_PYTHON", "/opt/venv/bin/python")
VENV_DBT = os.environ.get("PROJECT_DBT", "/opt/venv/bin/dbt")

DEFAULT_ARGS = {
    "owner": "football-scout",
    "depends_on_past": False,
    "email_on_failure": False,
    "retry_delay": timedelta(minutes=2),
}


def _run(cmd: list[str], cwd: str) -> str:
    """Run a command, streaming its output into the task log on failure.

    Airflow shows stdout in the UI, which is where you actually debug from - so
    the whole tail goes into the exception rather than just a return code.
    """
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    print(proc.stdout[-8000:])
    if proc.returncode != 0:
        print(proc.stderr[-4000:])
        raise RuntimeError(f"{' '.join(cmd)} exited {proc.returncode}\n{proc.stderr[-2000:]}")
    return proc.stdout


def _optional_source(name: str, script: str) -> None:
    """Run an enrichment ingest; turn failure into a skip, not a stop.

    AirflowSkipException rather than a swallowed exception: a skip is visible in
    the UI as a distinct state, so a week where Club Elo was down looks different
    from a week where it worked. Swallowing the error would make the two
    identical, which is how a silently degraded pipeline goes unnoticed for
    months.
    """
    try:
        _run([VENV_PY, script], cwd=PROJECT_DIR)
    except Exception as exc:  # noqa: BLE001 - deliberate downgrade to skip
        raise AirflowSkipException(f"{name} unavailable, continuing without it: {exc}") from exc


@dag(
    dag_id="football_scout_refresh",
    description="Weekly: refresh the three sources and rebuild the DuckDB warehouse",
    schedule="0 6 * * MON",  # Monday 06:00 - upstream refreshes over the weekend
    start_date=pendulum.datetime(2026, 9, 1, tz="Europe/Athens"),
    catchup=False,  # a missed week should not replay; we only ever want latest
    max_active_runs=1,  # DuckDB has one writer. Never two builds at once.
    default_args=DEFAULT_ARGS,
    tags=["football-scout", "weekly"],
    doc_md=__doc__,
)
def football_scout_refresh():
    @task(task_id="ingest_transfermarkt", retries=3)
    def ingest_transfermarkt() -> str:
        """REQUIRED. 211MB prepared dataset; validates before swapping it in."""
        return _run([VENV_PY, "ingest/transfermarkt.py", "--force"], cwd=PROJECT_DIR)[-2000:]

    @task(task_id="ingest_understat", retries=2)
    def ingest_understat() -> None:
        """Optional. Without it the model scores on goal contributions, not xG."""
        _optional_source("Understat", "ingest/understat.py")

    @task(
        task_id="ingest_clubelo",
        retries=5,
        retry_exponential_backoff=True,
        max_retry_delay=timedelta(minutes=30),
    )
    def ingest_clubelo() -> None:
        """Optional, and the flakiest. api.clubelo.com returned 502 for days.

        Most retries and the longest backoff of any task here, because this is
        the one that genuinely fails. Without it league strength falls back to
        the placeholder coefficients in seeds/league_tiers.csv.
        """
        _optional_source("Club Elo", "ingest/clubelo.py")

    @task(task_id="dbt_build", trigger_rule=TriggerRule.NONE_FAILED, retries=1)
    def dbt_build() -> str:
        """Transform and test in one step.

        `dbt build` rather than `run` then `test`: build interleaves them, so a
        model whose test fails does not have its downstream children built on top
        of bad data. That is the whole reason CLAUDE.md insists on build.
        """
        return _run([VENV_DBT, "build"], cwd=f"{PROJECT_DIR}/transform")[-4000:]

    @task(task_id="report")
    def report() -> dict:
        """Summarise what the run produced, so the log answers 'did it work?'."""
        import sys

        sys.path.insert(0, "/opt/venv/lib/python3.12/site-packages")
        import duckdb

        con = duckdb.connect(f"{PROJECT_DIR}/data/scout.duckdb", read_only=True)
        try:
            counts = {
                t: con.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
                for t in ("mart_shortlist", "mart_player_scores", "fct_player_season")
            }
            with_xg = con.execute("SELECT count(*) FROM mart_shortlist WHERE has_xg").fetchone()[0]
        finally:
            con.close()
        summary = {
            **counts,
            "shortlist_with_xg": with_xg,
            "refreshed_at": datetime.now().isoformat(timespec="seconds"),
        }
        print(summary)
        # An empty shortlist means the pipeline "succeeded" and produced nothing,
        # which is worse than failing - fail loudly instead (CLAUDE.md rule 5).
        if counts["mart_shortlist"] == 0:
            raise ValueError(
                "shortlist is empty after a successful build - the filters or the "
                "source data changed. Do not ship this silently."
            )
        return summary

    tm = ingest_transfermarkt()
    us = ingest_understat()
    ce = ingest_clubelo()
    build = dbt_build()

    [tm, us, ce] >> build >> report()


football_scout_refresh()
