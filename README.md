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
project: feature_store
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

When running `feast apply`, if `db_schema` is set then that value will be used when creating the schema, else the name of the schema will be the value in `user`. If the schema already exists then no schema is created, but the user must have privileges to create tables and indexes as well as dropping tables.

> It is important that this schema not be used by others since on `feast teardown` the schema will be dropped!
>
> `DROP SCHEMA IF EXISTS {schema_name} CASCADE;`

### Offline store:
To configure the offline store edit `feature_store.yaml`
```yaml
project: feature_store
registry: data/registry.db
provider: local
online_store:
    ...
offline_store:
    type: feast_postgres.PostgreSQLOfflineStore # MUST be this value
    host: localhost
    port: 5432              # Optional, default it 5432
    database: postgres
    db_schema: my_schema    # Optional, default is None
    user: username
    password: password
```

If no schema is supplied the users default schema will be used. The user will need to have privileges to create and drop tables since temp tables will be created when querying for historical values.
