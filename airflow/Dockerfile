# Airflow plus this project's own dependencies.
#
# The stock image cannot run our tasks: they import duckdb, soccerdata and dbt.
# Two ways to fix that - bake them into an image, or install at task runtime with
# a PythonVirtualenvOperator. Baking is chosen because the dependency set is
# stable, and resolving soccerdata's tree on every run would make a two-minute
# pipeline take ten.
FROM apache/airflow:3.3.1-python3.12

USER root
# git is needed by dbt deps; build-essential for any source-only wheels.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git build-essential \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

USER airflow
# Pinned deliberately. A scraper stack that silently upgrades is a scraper stack
# that breaks on a Sunday - SPEC §9 says pin soccerdata, so pin all of it.
RUN pip install --no-cache-dir \
    "duckdb>=1.1,<2" \
    "dbt-core>=1.9,<2" \
    "dbt-duckdb>=1.9,<2" \
    "httpx>=0.27" \
    "pandas>=2.2" \
    "soccerdata==1.9.1" \
    "rapidfuzz>=3.0" \
    "pyyaml>=6.0"
