"""Shared Postgres access for every project's ingestion/transform tasks.

Reads ANALYTICS_DATABASE_URL from the environment (set in docker-compose.yml,
pointed at the container-internal ``postgres`` service) rather than
hardcoding host/credentials, so the same code works whether it runs inside
an Airflow task container or a local `python -m` invocation with `.env`
loaded some other way.
"""
from __future__ import annotations

import os
from functools import lru_cache

import pandas as pd
from sqlalchemy import Engine, create_engine, text


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url = os.environ["ANALYTICS_DATABASE_URL"]
    return create_engine(url, pool_pre_ping=True, future=True)


def upsert_dataframe(
    df: pd.DataFrame,
    *,
    schema: str,
    table: str,
    key_columns: list[str],
) -> int:
    """Idempotent load: insert new rows, update existing ones on conflict.

    Used instead of pandas' `to_sql(if_exists="append")` because DAG reruns
    for the same logical date must replace that data, not duplicate it.
    Returns the number of rows written.
    """
    if df.empty:
        return 0

    engine = get_engine()
    columns = list(df.columns)
    update_columns = [c for c in columns if c not in key_columns]

    col_list = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    conflict_cols = ", ".join(f'"{c}"' for c in key_columns)
    update_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_columns)

    if update_clause:
        stmt = (
            f'INSERT INTO "{schema}"."{table}" ({col_list}) VALUES ({placeholders}) '
            f"ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_clause}"
        )
    else:
        stmt = (
            f'INSERT INTO "{schema}"."{table}" ({col_list}) VALUES ({placeholders}) '
            f"ON CONFLICT ({conflict_cols}) DO NOTHING"
        )

    records = df.to_dict(orient="records")
    with engine.begin() as conn:
        conn.execute(text(stmt), records)
    return len(records)


def bulk_upsert_dataframe(
    df: pd.DataFrame,
    *,
    schema: str,
    table: str,
    key_columns: list[str],
) -> int:
    """Like upsert_dataframe but for large (100k+ row) fact tables.

    Loads into a temp staging table via pandas.to_sql (libpq COPY-backed,
    far faster than one bound INSERT per row) then does a single
    INSERT ... SELECT ... ON CONFLICT from staging into the real table.
    Used by projects 2 and 4, whose real-data volumes make row-by-row
    upsert_dataframe impractically slow.
    """
    if df.empty:
        return 0

    engine = get_engine()
    columns = list(df.columns)
    update_columns = [c for c in columns if c not in key_columns]
    staging_table = f"_stage_{table}"

    col_list = ", ".join(f'"{c}"' for c in columns)
    conflict_cols = ", ".join(f'"{c}"' for c in key_columns)
    update_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in update_columns)

    with engine.begin() as conn:
        df.to_sql(
            staging_table, conn, schema=schema, if_exists="replace", index=False, method="multi", chunksize=5000,
        )
        insert_sql = f'INSERT INTO "{schema}"."{table}" ({col_list}) SELECT {col_list} FROM "{schema}"."{staging_table}"'
        if update_clause:
            insert_sql += f" ON CONFLICT ({conflict_cols}) DO UPDATE SET {update_clause}"
        else:
            insert_sql += f" ON CONFLICT ({conflict_cols}) DO NOTHING"
        conn.execute(text(insert_sql))
        conn.execute(text(f'DROP TABLE "{schema}"."{staging_table}"'))
    return len(df)


def run_sql_file(path: str) -> None:
    """Execute a .sql file (may contain multiple ; separated statements).

    Strips full-line `--` comments before splitting on ";" -- a semicolon
    inside a prose comment (e.g. "NOT a normal; see limitations doc") would
    otherwise split the file mid-comment and hand psycopg2 a comment-only
    fragment, which it rejects as "can't execute an empty query".
    """
    with open(path, "r", encoding="utf-8") as f:
        lines = [line for line in f if not line.strip().startswith("--")]
    sql = "".join(lines)
    engine = get_engine()
    with engine.begin() as conn:
        for statement in sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
