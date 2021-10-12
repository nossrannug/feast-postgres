import contextlib
from datetime import datetime
from io import StringIO
from typing import Callable, ContextManager, Iterator, List, Optional, Union

import pandas as pd
import psycopg2
import pyarrow
import pyarrow as pa
import pyarrow.parquet
from psycopg2 import sql
from pydantic.typing import Literal

from feast.data_source import DataSource
from feast.errors import InvalidEntityType
from feast.feature_view import FeatureView
from feast.infra.offline_stores import offline_utils
from feast.infra.offline_stores.offline_store import OfflineStore, RetrievalJob
from feast.on_demand_feature_view import OnDemandFeatureView
from feast.registry import Registry
from feast.repo_config import RepoConfig

from ..postgres_config import PostgreSQLConfig
from .postgres_source import PostgreSQLSource


class PostgreSQLOfflineStoreConfig(PostgreSQLConfig):
    type: Literal[
        "feast_postgres.PostgreSQLOfflineStore"
    ] = "feast_postgres.PostgreSQLOfflineStore"


class PostgreSQLOfflineStore(OfflineStore):
    @staticmethod
    def pull_latest_from_table_or_query(
        config: RepoConfig,
        data_source: DataSource,
        join_key_columns: List[str],
        feature_name_columns: List[str],
        event_timestamp_column: str,
        created_timestamp_column: Optional[str],
        start_date: datetime,
        end_date: datetime,
    ) -> RetrievalJob:
        assert isinstance(data_source, PostgreSQLSource)
        from_expression = data_source.get_table_query_string()

        partition_by_join_key_string = ", ".join(_append_alias(join_key_columns, "a"))
        if partition_by_join_key_string != "":
            partition_by_join_key_string = (
                "PARTITION BY " + partition_by_join_key_string
            )
        timestamps = [event_timestamp_column]
        if created_timestamp_column:
            timestamps.append(created_timestamp_column)
        timestamp_desc_string = " DESC, ".join(_append_alias(timestamps, "a")) + " DESC"
        a_field_string = ", ".join(
            _append_alias(join_key_columns + feature_name_columns + timestamps, "a")
        )
        b_field_string = ", ".join(
            _append_alias(join_key_columns + feature_name_columns + timestamps, "b")
        )

        query = f"""
            SELECT
                {b_field_string}
            FROM (
                SELECT {a_field_string},
                ROW_NUMBER() OVER({partition_by_join_key_string} ORDER BY {timestamp_desc_string}) AS _feast_row
                FROM ({from_expression}) a
                WHERE a.{event_timestamp_column} BETWEEN '{start_date}'::timestamptz AND '{end_date}'::timestamptz
            ) b
            WHERE _feast_row = 1
            """

        return PostgreSQLRetrievalJob(
            query=query,
            config=config,
            full_feature_names=False,
            on_demand_feature_views=None,
        )

    @staticmethod
    def get_historical_features(
        config: RepoConfig,
        feature_views: List[FeatureView],
        feature_refs: List[str],
        entity_df: Union[pd.DataFrame, str],
        registry: Registry,
        project: str,
        full_feature_names: bool = False,
    ) -> RetrievalJob:
        @contextlib.contextmanager
        def query_generator() -> Iterator[str]:
            table_name = offline_utils.get_temp_entity_table_name()
            entity_schema = _df_to_table(config, entity_df, table_name)

            entity_df_event_timestamp_col = offline_utils.infer_event_timestamp_from_entity_df(
                entity_schema
            )

            expected_join_keys = offline_utils.get_expected_join_keys(
                project, feature_views, registry
            )

            offline_utils.assert_expected_columns_in_entity_df(
                entity_schema, expected_join_keys, entity_df_event_timestamp_col
            )

            query_context = offline_utils.get_feature_view_query_context(
                feature_refs, feature_views, registry, project,
            )

            query = offline_utils.build_point_in_time_query(
                query_context,
                left_table_query_string=table_name,
                entity_df_event_timestamp_col=entity_df_event_timestamp_col,
                query_template=MULTIPLE_FEATURE_VIEW_POINT_IN_TIME_JOIN,
                full_feature_names=full_feature_names,
            )

            try:
                yield query
            finally:
                with _get_conn(config) as conn, conn.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            """
                            DROP TABLE IF EXISTS {};
                            """
                        ).format(sql.Identifier(table_name)),
                    )

        return PostgreSQLRetrievalJob(
            query=query_generator,
            config=config,
            full_feature_names=full_feature_names,
            on_demand_feature_views=OnDemandFeatureView.get_requested_odfvs(
                feature_refs, project, registry
            ),
        )


class PostgreSQLRetrievalJob(RetrievalJob):
    def __init__(
        self,
        query: Union[str, Callable[[], ContextManager[str]]],
        config: RepoConfig,
        full_feature_names: bool,
        on_demand_feature_views: Optional[List[OnDemandFeatureView]],
    ):
        if not isinstance(query, str):
            self._query_generator = query
        else:

            @contextlib.contextmanager
            def query_generator() -> Iterator[str]:
                assert isinstance(query, str)
                yield query

            self._query_generator = query_generator
        self.config = config
        self.connection = _get_conn(self.config)
        self._full_feature_names = full_feature_names
        self._on_demand_feature_views = on_demand_feature_views

    @property
    def full_feature_names(self) -> bool:
        return self._full_feature_names

    @property
    def on_demand_feature_views(self) -> Optional[List[OnDemandFeatureView]]:
        return self._on_demand_feature_views

    def _to_df_internal(self) -> pd.DataFrame:
        with self._query_generator() as query:
            with self.connection:
                return pd.read_sql_query(query, self.connection)

    def to_sql(self) -> str:
        with self._query_generator() as query:
            return query

    def _to_arrow_internal(self) -> pyarrow.Table:
        return pa.Table.from_pandas(self._to_df_internal())


def _get_connection_config(config: PostgreSQLOfflineStoreConfig):
    db_config = {
        "dbname": config.database,
        "host": config.host,
        "port": int(config.port),
        "user": config.user,
        "password": config.password,
    }
    if config.db_schema:
        db_config["options"] = f"-c search_path={config.db_schema}"

    return db_config


def _get_conn(config: RepoConfig):
    assert config.offline_store.type == "feast_postgres.PostgreSQLOfflineStore"
    return psycopg2.connect(**_get_connection_config(config.offline_store))


def _append_alias(field_names: List[str], alias: str) -> List[str]:
    return [f"{alias}.{field_name}" for field_name in field_names]


def _df_to_table(config: RepoConfig, entity_df: Union[pd.DataFrame, str], table: str):
    with _get_conn(config) as conn, conn.cursor() as cursor:
        if isinstance(entity_df, pd.DataFrame):
            cursor.execute(pd.io.sql.get_schema(entity_df, table))
            buffer = StringIO()
            entity_df.to_csv(buffer, header=False, index=False, na_rep="\\N")
            buffer.seek(0)
            cursor.copy_from(buffer, table, sep=",")
            df = entity_df

        elif isinstance(entity_df, str):
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE {} AS ({})
                    """
                ).format(sql.Identifier(table), sql.Literal(entity_df),),
            )
            df = PostgreSQLRetrievalJob(
                f"SELECT * FROM {table} LIMIT 0", config, False, None,
            ).to_df()

        else:
            raise InvalidEntityType(type(entity_df))

    return dict(zip(df.columns, df.dtypes))


# Copied from the Feast Redshift offline store implementation
# Note: Keep this in sync with sdk/python/feast/infra/offline_stores/redshift.py:
# MULTIPLE_FEATURE_VIEW_POINT_IN_TIME_JOIN
# https://github.com/feast-dev/feast/blob/master/sdk/python/feast/infra/offline_stores/redshift.py

MULTIPLE_FEATURE_VIEW_POINT_IN_TIME_JOIN = """
/*
 Compute a deterministic hash for the `left_table_query_string` that will be used throughout
 all the logic as the field to GROUP BY the data
*/
WITH entity_dataframe AS (
    SELECT *,
        {{entity_df_event_timestamp_col}} AS entity_timestamp
        {% for featureview in featureviews %}
            {% if featureview.entities %}
            ,(
                {% for entity in featureview.entities %}
                    CAST({{entity}} as VARCHAR) ||
                {% endfor %}
                CAST({{entity_df_event_timestamp_col}} AS VARCHAR)
            ) AS {{featureview.name}}__entity_row_unique_id
            {% else %}
            ,CAST({{entity_df_event_timestamp_col}} AS VARCHAR) AS {{featureview.name}}__entity_row_unique_id
            {% endif %}
        {% endfor %}
    FROM {{ left_table_query_string }}
),

{% for featureview in featureviews %}

{{ featureview.name }}__entity_dataframe AS (
    SELECT
        {{ featureview.entities | join(', ')}}{% if featureview.entities %},{% else %}{% endif %}
        entity_timestamp,
        {{featureview.name}}__entity_row_unique_id
    FROM entity_dataframe
    GROUP BY
        {{ featureview.entities | join(', ')}}{% if featureview.entities %},{% else %}{% endif %}
        entity_timestamp,
        {{featureview.name}}__entity_row_unique_id
),

/*
 This query template performs the point-in-time correctness join for a single feature set table
 to the provided entity table.

 1. We first join the current feature_view to the entity dataframe that has been passed.
 This JOIN has the following logic:
    - For each row of the entity dataframe, only keep the rows where the `event_timestamp_column`
    is less than the one provided in the entity dataframe
    - If there a TTL for the current feature_view, also keep the rows where the `event_timestamp_column`
    is higher the the one provided minus the TTL
    - For each row, Join on the entity key and retrieve the `entity_row_unique_id` that has been
    computed previously

 The output of this CTE will contain all the necessary information and already filtered out most
 of the data that is not relevant.
*/

{{ featureview.name }}__subquery AS (
    SELECT
        {{ featureview.event_timestamp_column }} as event_timestamp,
        {{ featureview.created_timestamp_column ~ ' as created_timestamp,' if featureview.created_timestamp_column else '' }}
        {{ featureview.entity_selections | join(', ')}}{% if featureview.entity_selections %},{% else %}{% endif %}
        {% for feature in featureview.features %}
            {{ feature }} as {% if full_feature_names %}{{ featureview.name }}__{{feature}}{% else %}{{ feature }}{% endif %}{% if loop.last %}{% else %}, {% endif %}
        {% endfor %}
    FROM {{ featureview.table_subquery }} sub
    WHERE {{ featureview.event_timestamp_column }} <= (SELECT MAX(entity_timestamp) FROM entity_dataframe)
    {% if featureview.ttl == 0 %}{% else %}
    AND {{ featureview.event_timestamp_column }} >= (SELECT MIN(entity_timestamp) FROM entity_dataframe) - {{ featureview.ttl }} * interval '1' second
    {% endif %}
),

{{ featureview.name }}__base AS (
    SELECT
        subquery.*,
        entity_dataframe.entity_timestamp,
        entity_dataframe.{{featureview.name}}__entity_row_unique_id
    FROM {{ featureview.name }}__subquery AS subquery
    INNER JOIN {{ featureview.name }}__entity_dataframe AS entity_dataframe
    ON TRUE
        AND subquery.event_timestamp <= entity_dataframe.entity_timestamp

        {% if featureview.ttl == 0 %}{% else %}
        AND subquery.event_timestamp >= entity_dataframe.entity_timestamp - {{ featureview.ttl }} * interval '1' second
        {% endif %}

        {% for entity in featureview.entities %}
        AND subquery.{{ entity }} = entity_dataframe.{{ entity }}
        {% endfor %}
),

/*
 2. If the `created_timestamp_column` has been set, we need to
 deduplicate the data first. This is done by calculating the
 `MAX(created_at_timestamp)` for each event_timestamp.
 We then join the data on the next CTE
*/
{% if featureview.created_timestamp_column %}
{{ featureview.name }}__dedup AS (
    SELECT
        {{featureview.name}}__entity_row_unique_id,
        event_timestamp,
        MAX(created_timestamp) as created_timestamp
    FROM {{ featureview.name }}__base
    GROUP BY {{featureview.name}}__entity_row_unique_id, event_timestamp
),
{% endif %}

/*
 3. The data has been filtered during the first CTE "*__base"
 Thus we only need to compute the latest timestamp of each feature.
*/
{{ featureview.name }}__latest AS (
    SELECT
        {{featureview.name}}__entity_row_unique_id,
        MAX(event_timestamp) AS event_timestamp
        {% if featureview.created_timestamp_column %}
            ,MAX(created_timestamp) AS created_timestamp
        {% endif %}

    FROM {{ featureview.name }}__base
    {% if featureview.created_timestamp_column %}
        INNER JOIN {{ featureview.name }}__dedup
        USING ({{featureview.name}}__entity_row_unique_id, event_timestamp, created_timestamp)
    {% endif %}

    GROUP BY {{featureview.name}}__entity_row_unique_id
),

/*
 4. Once we know the latest value of each feature for a given timestamp,
 we can join again the data back to the original "base" dataset
*/
{{ featureview.name }}__cleaned AS (
    SELECT base.*
    FROM {{ featureview.name }}__base as base
    INNER JOIN {{ featureview.name }}__latest
    USING(
        {{featureview.name}}__entity_row_unique_id,
        event_timestamp
        {% if featureview.created_timestamp_column %}
            ,created_timestamp
        {% endif %}
    )
) {% if loop.last %}{% else %}, {% endif %}


{% endfor %}
/*
 Joins the outputs of multiple time travel joins to a single table.
 The entity_dataframe dataset being our source of truth here.
 */

SELECT *
FROM entity_dataframe
{% for featureview in featureviews %}
LEFT JOIN (
    SELECT
        {{featureview.name}}__entity_row_unique_id
        {% for feature in featureview.features %}
            ,{% if full_feature_names %}{{ featureview.name }}__{{feature}}{% else %}{{ feature }}{% endif %}
        {% endfor %}
    FROM {{ featureview.name }}__cleaned
) {{featureview.name}} USING ({{featureview.name}}__entity_row_unique_id)
{% endfor %}
"""
