"""Phase 0: dump the real schema of every table in the downloaded dataset.

Run this FIRST against the real file and reconcile the output with the column
names the staging models assume. The staging models were written against the
schemas published in dcaribou/transfermarkt-datasets' curated dbt models, but
that project evolves - verify rather than trust.
"""

from pathlib import Path

import duckdb

DB = Path(__file__).resolve().parents[1] / "data" / "transfermarkt-datasets.duckdb"

con = duckdb.connect(str(DB), read_only=True)
for (table,) in con.execute("SHOW TABLES").fetchall():
    n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    print(f"\n{'=' * 70}\n{table}  ({n:,} rows)\n{'=' * 70}")
    for col, dtype, *_ in con.execute(f"DESCRIBE {table}").fetchall():
        print(f"  {col:45} {dtype}")
con.close()
