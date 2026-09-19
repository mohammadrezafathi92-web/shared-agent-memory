from alembic import context
from sqlalchemy import create_engine

from shared_memory.config import Settings

url = Settings().database_url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(url)
with engine.connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
