# ADR-0007: LocalExecutor, optional sources that skip, and one writer

**Date:** 2026-09-12
**Status:** Accepted
**Follows:** ADR-0005 (why Airflow at all)

## Context
ADR-0005 settled *that* we orchestrate with Airflow. This records *how*, because
three constraints in this pipeline are unusual enough that the obvious setup is
wrong.

1. DuckDB permits a **single writer**. Two concurrent `dbt build` runs fail on a
   lock.
2. The three sources are **not equally important**. Transfermarkt is the spine;
   Understat and Club Elo are enrichment.
3. Club Elo is **genuinely unreliable** — its API returned HTTP 502 for days
   during Phase 2.

## Decision

**LocalExecutor, not CeleryExecutor.** Celery distributes tasks across worker
machines. This is one laptop running a weekly job, so Celery would add Redis, a
broker and a worker container to solve a problem that does not exist.
LocalExecutor still runs tasks in parallel as subprocesses, which is all the
parallelism three concurrent downloads can use.

**`max_active_runs=1`.** The single-writer constraint is expressed in the DAG
rather than left to luck.

**Optional sources convert failure into a skip.** `AirflowSkipException`, with
`dbt_build` on `trigger_rule=NONE_FAILED`. A skip is not a failure, so the build
proceeds when Club Elo is down; a Transfermarkt failure still stops everything.

Crucially the failure is **downgraded, not swallowed**. A skip is a distinct
state in the UI, so a week where Club Elo was unavailable looks different from a
week where it worked. Catching and ignoring the error would make those two runs
identical, which is how a silently degraded pipeline goes unnoticed for months.

**Retries are per-source.** Club Elo gets 5 retries with exponential backoff to
30 minutes; Transfermarkt gets 3; Understat 2. Patience proportional to observed
flakiness rather than one global number.

**The repo is bind-mounted, not copied into the image.** A run therefore uses the
working tree, and the Streamlit app on the host reads the very DuckDB file the
pipeline just rebuilt.

**The final task fails on an empty shortlist.** A pipeline that "succeeds" and
produces nothing is worse than one that fails, because nobody investigates a
green run (CLAUDE.md rule 5).

## Consequences
- No Redis or worker containers; the stack is Postgres plus three Airflow
  services.
- Dependencies are baked into a custom image. Stable set, so resolving
  `soccerdata` on every task run would turn a two-minute pipeline into a
  ten-minute one.
- `AIRFLOW_UID` must match the host user or files written into `data/` are owned
  by root and Streamlit cannot read them. Documented in `.env.example`.
- The bind mount means a `docker compose down -v` never destroys project data —
  only Airflow's own metadata.

## Alternatives rejected
- **CeleryExecutor**, as in the owner's `airflow-zero-to-hero` course. Correct
  for that course's purpose, unnecessary here, and the extra containers would
  obscure the parts worth reading.
- **One BashOperator running a shell script.** Simpler, and it throws away
  everything Airflow is for: per-task retries, per-task logs, and a graph that
  shows which source failed.
- **`PythonVirtualenvOperator`** instead of a custom image — avoids a build step
  but re-resolves dependencies on every run.
- **Letting Club Elo failures fail the DAG.** Honest, but it means a week with no
  refresh at all because an optional enrichment source was down. The skip keeps
  the pipeline running in the degraded mode it was designed to support.
