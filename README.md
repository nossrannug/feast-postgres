# Feast PostgreSQL Support

This repo adds PostgreSQL offline and online stores to [Feast](https://github.com/feast-dev/feast)

## Get started
### Install feast:
```shell
pip install feast
```

### Install feast-postgres:
```shell
pip install feast-postgres
```

### Create a feature repository:
```shell
feast init feature_repo
cd feature_repo
```

### Online store:
To configure the online store edit `feature_store.yaml`
```yaml
project: feature_repo
registry: data/registry.db
provider: local
online_store:
    type: feast_postgres.PostgreSQLOnlineStore # MUST be this value
    host: localhost
    port: 5432                  # Optional, default is 5432
    database: postgres
    db_schema: feature_store    # Optional, default is None
    user: username
    password: password
offline_store:
    ...
```

When running `feast apply`, if `db_schema` is set then that value will be used when creating the schema, else the name of the schema will be the value in `user`. If the schema already exists then no schema is created, but the user must have privileges to create tables and indexes as well as dropping tables and indexes.

### Offline store:
To configure the offline store edit `feature_store.yaml`
```yaml
project: feature_repo
registry: data/registry.db
provider: local
online_store:
    ...
offline_store:
    type: feast_postgres.PostgreSQLOfflineStore # MUST be this value
    host: localhost
    port: 5432              # Optional, default it 5432
    database: postgres
    db_schema: my_schema
    user: username
    password: password
```

The user will need to have privileges to create and drop tables in `db_schema` since temp tables will be created when querying for historical values.

### Registry store:
To configure the registry edit `feature_store.yaml`
```yaml
registry:
    registry_store_type: feast_postgres.PostgreSQLRegistryStore
    path: feast_registry    # This will become the table name for the registry
    host: localhost
    port: 5432              # Optional, default is 5432
    database: postgres
    db_schema: my_schema
    user: username
    password: password
```

If the schema does not exists, the user will need to have privileges to create it. If the schema exists, the user will only need privileges to create the table.

### Example
Start by setting the values in `feature_store.yaml`. Then use `copy_from_parquet_to_postgres.py` to create a table and populate it with data from the parquet file that comes with Feast.

Then `example.py` can be used for the feature_store.
```python
# This is an example feature definition file

from google.protobuf.duration_pb2 import Duration

from feast import Entity, Feature, FeatureView, ValueType

from feast_postgres import PostgreSQLSource

# Read data from parquet files. Parquet is convenient for local development mode. For
# production, you can use your favorite DWH, such as BigQuery. See Feast documentation
# for more info.
driver_hourly_stats = PostgreSQLSource(
    query="SELECT * FROM driver_stats",
    event_timestamp_column="event_timestamp",
    created_timestamp_column="created",
)

# Define an entity for the driver. You can think of entity as a primary key used to
# fetch features.
driver = Entity(name="driver_id", value_type=ValueType.INT64, description="driver id",)

# Our parquet files contain sample data that includes a driver_id column, timestamps and
# three feature column. Here we define a Feature View that will allow us to serve this
# data to our model online.
driver_hourly_stats_view = FeatureView(
    name="driver_hourly_stats",
    entities=["driver_id"],
    ttl=Duration(seconds=86400 * 1),
    features=[
        Feature(name="conv_rate", dtype=ValueType.FLOAT),
        Feature(name="acc_rate", dtype=ValueType.FLOAT),
        Feature(name="avg_daily_trips", dtype=ValueType.INT64),
    ],
    online=True,
    batch_source=driver_hourly_stats,
    tags={},
)
```

Then run:
```shell
feast apply
feast materialize-incremental $(date -u +"%Y-%m-%dT%H:%M:%S")
```

This will create the feature view table and populate if with data from the `driver_stats` table that we created in Postgres.
