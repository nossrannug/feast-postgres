from tests.integration.feature_repos.integration_test_repo_config import IntegrationTestRepoConfig
from tests.postgres_data_source import PostgreSQLDataSourceCreator

POSTGRES_ONLINE_CONFIG={
    "type": "feast_postgres.PostgreSQLOnlineStore",
    "host": "localhost",
    "port": "5432",
    "database": "postgres",
    "db_schema": "feature_store",
    "user": "postgres",
    "password": "docker",
}

FULL_REPO_CONFIGS = [
    IntegrationTestRepoConfig(
        provider="local",
        offline_store_creator=PostgreSQLDataSourceCreator,
        online_store=POSTGRES_ONLINE_CONFIG,
    ),
]
