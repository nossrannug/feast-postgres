from io import StringIO
import pandas as pd
import yaml
import sqlalchemy

from feast_postgres import PostgreSQLOfflineStoreConfig

df = pd.read_parquet("./data/driver_stats.parquet")
with open("feature_store.yaml", "r") as stream:
    try:
        config = yaml.safe_load(stream)
    except yaml.YAMLError as exc:
        print(exc)

offline_config = config["offline_store"]
del offline_config["type"]
offline_config = PostgreSQLOfflineStoreConfig(**offline_config)

def get_sqlalchemy_engine(config: PostgreSQLOfflineStoreConfig):
    url = f"postgresql+psycopg2://{config.user}:{config.password}@{config.host}:{config.port}/{config.database}"
    print(url)
    print(config.db_schema)
    return sqlalchemy.create_engine(url, client_encoding='utf8', connect_args={'options': '-c search_path={}'.format(config.db_schema)})

con = get_sqlalchemy_engine(offline_config)

table = "driver_stats"
con.execute("DROP TABLE IF EXISTS " + table)
create_table_sql = pd.io.sql.get_schema(df, table, con=con)
con.execute(create_table_sql)
buffer = StringIO()
df.to_csv(buffer, header=False, index=False, na_rep="\\N")
buffer.seek(0)
raw_con = con.raw_connection()
with raw_con.cursor() as cursor:
    cursor.copy_from(buffer, table, sep=",")
raw_con.commit()