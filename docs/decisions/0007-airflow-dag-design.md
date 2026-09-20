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

---

## Addendum: seven things that broke getting this running

Recorded because every one of them presented as a different problem than it was,
and because "it worked first time" is never the useful part of a build log.

1. **`ModuleNotFoundError: No module named 'airflow.__main__'`** after adding
   dbt to the image. dbt-core and Airflow pin Jinja2 in incompatible ranges, so
   pip "resolved" it by mangling Airflow. **Fix:** project dependencies live in a
   separate virtualenv at `/opt/venv`; Airflow's environment is never touched.
   This is the standard way to run dbt under Airflow.

2. **The same error again, for a completely different reason.** This repo has an
   `airflow/` directory at its root, and `PYTHONPATH=/opt/project` made
   `import airflow` resolve to *our folder* as a namespace package. **Fix:** drop
   the PYTHONPATH; tasks invoke scripts by absolute path anyway.

3. **`No module named 'airflow'` in the init container only.** It overrode
   `entrypoint: /bin/bash`, and the image's entrypoint is what wires up the
   environment when the container runs as a remapped host UID rather than the
   image's own `airflow` user. **Fix:** pass a bare subcommand (`command: db
   migrate`) like every other service does.

4. **`airflow users create` does not exist in Airflow 3.** User management moved
   to the FAB provider; the default is now SimpleAuthManager. **Fix:**
   `SIMPLE_AUTH_MANAGER_ALL_ADMINS=true` for a localhost-only stack.

5. **`httpx.ConnectError: [Errno 111] Connection refused` on every task.**
   Airflow 3 runs tasks against a Task Execution API instead of letting them
   touch the metadata DB; the default URL assumes localhost, which inside the
   scheduler container is the scheduler. **Fix:** set
   `AIRFLOW__CORE__EXECUTION_API_SERVER_URL`. Not needed in 2.x.

6. **`ServerResponseError: Invalid auth token`.** The scheduler signs a JWT that
   the task presents to that API, and each service invents its own secret at
   startup unless told otherwise. **Fix:** a shared
   `AIRFLOW__API_AUTH__JWT_SECRET`.

7. **Two failures that only showed up as a *skipped* Understat task** — which is
   the design working, and also the design hiding things. First `[Errno 13]
   Permission denied`: the container runs as the host UID with group 0, so
   anything a library writes at runtime must be group-writable, and soccerdata
   caches inside its own package directory. Then `pyarrow or fastparquet is
   required`: the host venv had pyarrow transitively, the container's did not.

   **The lesson worth keeping:** a skip is the right behaviour for an optional
   source, but it means a broken *configuration* looks identical to an
   unavailable *upstream*. Read the skip reason before believing the upstream is
   down. Both of these were our bugs, not Club Elo's.

The Dockerfile now asserts `airflow version`, `dbt --version` and the imports at
**build** time, so a broken image fails in seconds rather than three minutes into
a DAG run.

---

## Addendum 2: the stack must not be left running

Leaving the four containers up after testing cost **~87% of a CPU core,
continuously, for days** — fans audible, battery draining, for a pipeline that
does something once a week.

Measured, idle, doing nothing:

| | containers | Docker VM process |
|---|---:|---:|
| default settings | ~38% | 87% |
| after tuning below | 13% | 77% |
| stopped | 0% | **0–3%** |

Two separate causes, and the tuning only fixes the smaller one.

**Airflow's defaults assume a server.** They re-read every DAG file every 30s and
list the folder every 5 minutes, forever, so a DAG can start within seconds of
being edited. A weekly job does not need that. `MIN_FILE_PROCESS_INTERVAL`,
`DAG_DIR_LIST_INTERVAL`, `SCHEDULER_IDLE_SLEEP_TIME` and the heartbeats are now
tuned down hard, which cut container CPU by two thirds.

**The bigger cost is the bind mount, and it cannot be tuned away.** With
containers reporting 13%, the VM process still burned 77% — the gap is work the
VM does on its own behalf. The repository lives in a **Google Drive** folder, and
Docker has to bridge that FUSE filesystem into the Linux VM on every file
operation. Stopping the containers takes the VM to ~0%, so the containers cause
it, but it is not visible in their own CPU figures.

**So: run the stack only while working on it.**

```bash
cd airflow && docker compose up -d    # start
cd airflow && docker compose down     # STOP WHEN DONE
```

This is ADR-0005's admission arriving in the form of a hot laptop: cron genuinely
would suffice for this workload. Airflow is here to be learned and demonstrated,
and the right way to hold that is to start it when you want it and stop it after.

The deeper fix, if this ever becomes a daily annoyance, is to move the repository
off Google Drive to a local path. It is on GitHub now, so it can be cloned
anywhere; Drive sync is no longer the thing keeping it safe.
