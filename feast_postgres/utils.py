from typing import Dict

import pandas as pd
import psycopg2
import pyarrow as pa
from psycopg2 import sql

from feast_postgres.postgres_config import PostgreSQLConfig
from feast_postgres.type_map import arrow_to_pg_type


def _get_conn(config: PostgreSQLConfig):
    conn = psycopg2.connect(
        dbname=config.database,
        host=config.host,
        port=int(config.port),
        user=config.user,
        password=config.password,
        options="-c search_path={}".format(
            config.db_schema if config.db_schema else config.user
        ),
    )
    return conn


def df_to_create_table_sql(entity_df, table_name) -> str:
    pa_table = pa.Table.from_pandas(entity_df)
    columns = [
        f""""{f.name}" {arrow_to_pg_type(str(f.type))}""" for f in pa_table.schema
    ]
    return f"""
        CREATE TABLE "{table_name}" (
            {", ".join(columns)}
        );
        """


def df_to_postgres_table(
    config: PostgreSQLConfig, df: pd.DataFrame, table_name: str
) -> Dict[str, str]:
    """
    Create a table for the data frame, insert all the values, and return the table schema
    """
    with _get_conn(config) as conn, conn.cursor() as cur:
        cur.execute(df_to_create_table_sql(df, table_name))
        psycopg2.extras.execute_values(
            cur,
            f"""
            INSERT INTO {table_name}
            VALUES %s
            """,
            df.to_numpy(),
        )
        return df


def sql_to_postgres_table(
    config: PostgreSQLConfig, sql_query: str, table_name: str
) -> Dict[str, str]:
    """
    Create a table for the sql statement and return the table schema
    """
    with _get_conn(config) as conn, conn.cursor() as cur:
        cur.execute(
            sql.SQL(
                """
                CREATE TABLE {} AS ({});
                """
            ).format(sql.Identifier(table_name), sql.Literal(sql_query),),
        )
        df = pd.read_sql(f"SELECT * FROM {table_name} LIMIT 1", conn,)
        return dict(zip(df.columns, df.dtypes))
