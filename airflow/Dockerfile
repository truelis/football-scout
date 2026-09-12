# Airflow, plus this project's dependencies in a SEPARATE virtualenv.
#
# The obvious thing - pip install dbt-core alongside Airflow - breaks Airflow.
# Both pin Jinja2 hard and in incompatible ranges, so pip "resolves" the conflict
# by mangling one of them; the symptom is
#     ModuleNotFoundError: No module named 'airflow.__main__'
# which looks like a broken image rather than a dependency clash.
#
# So the project gets its own venv at /opt/venv and Airflow's environment is left
# untouched. Tasks invoke /opt/venv/bin/python and /opt/venv/bin/dbt explicitly.
# This is the standard way to run dbt under Airflow without the two fighting, and
# it keeps upgrades to either side independent.
FROM apache/airflow:3.3.1-python3.12

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/venv && chown airflow: /opt/venv

USER airflow
# Pinned deliberately: a scraper stack that silently upgrades is one that breaks
# on a Sunday. SPEC §9 says pin soccerdata; the same logic applies to the rest.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir \
        "duckdb>=1.1,<2" \
        "dbt-core>=1.9,<2" \
        "dbt-duckdb>=1.9,<2" \
        "httpx>=0.27" \
        "pandas>=2.2" \
        "pyarrow>=16" \
        "soccerdata==1.9.1" \
        "rapidfuzz>=3.0" \
        "pyyaml>=6.0"

# The container runs as the HOST uid with group 0, not the image's airflow user,
# so anything the libraries write at runtime must be group-writable. soccerdata's
# TLS backend caches a release config inside its own package directory and dies
# with [Errno 13] Permission denied otherwise - which surfaces as a skipped
# Understat ingest rather than an obvious permissions problem.
USER root
RUN chgrp -R 0 /opt/venv && chmod -R g+rwX /opt/venv
USER airflow

# Prove at BUILD time that both environments still work. A broken image should
# fail here, not three minutes into a DAG run.
RUN airflow version && /opt/venv/bin/dbt --version && /opt/venv/bin/python -c "import duckdb, soccerdata, pyarrow"
