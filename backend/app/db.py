from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

def database_engine_options(database_url: str) -> tuple:
    url = make_url(database_url)
    if url.drivername in {"postgres", "postgresql"}:
        url = url.set(drivername="postgresql+psycopg")
    if url.get_backend_name() == "sqlite":
        return url, {"connect_args": {"check_same_thread": False}}
    return url, {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5}

database_url, engine_options = database_engine_options(settings.database_url)
engine = create_engine(database_url, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _additive_migrations() -> None:
    inspector = inspect(engine)
    is_sqlite = settings.database_url.startswith("sqlite")
    timestamp_type = "DATETIME" if is_sqlite else "TIMESTAMP WITH TIME ZONE"

    migrations = {
        "payment_requests": {
            "recipient_id": "INTEGER",
            "limit_reservation_expires_at": timestamp_type,
            "user_id": 'INTEGER REFERENCES "user_accounts"(id)',
        },
        "paypal_orders": {
            "payment_request_id": "INTEGER",
            "paypal_order_id": "VARCHAR(120)",
            "status": "VARCHAR(40)",
            "approval_url": "TEXT",
            "capture_id": "VARCHAR(120)",
            "captured_at": timestamp_type,
            "created_at": timestamp_type,
        },
        "spending_limit_settings": {
            "user_id": 'INTEGER REFERENCES "user_accounts"(id)',
        },
        "paypal_wallet_connections": {
            "pending_state": "VARCHAR(128)",
        },
    }

    with engine.begin() as conn:
        table_names = set(inspector.get_table_names())
        for table, columns in migrations.items():
            if table not in table_names:
                continue

            existing = {column["name"] for column in inspector.get_columns(table)}
            for column, sql_type in columns.items():
                if column not in existing:
                    conn.execute(text(
                        f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'
                    ))
                    existing.add(column)

        if "payment_requests" in table_names:
            conn.execute(text(
                'CREATE INDEX IF NOT EXISTS "ix_payment_requests_user_id" '
                'ON "payment_requests" ("user_id")'
            ))
        if "spending_limit_settings" in table_names:
            conn.execute(text(
                'CREATE UNIQUE INDEX IF NOT EXISTS "ix_spending_limit_settings_user_id" '
                'ON "spending_limit_settings" ("user_id")'
            ))


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    _additive_migrations()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

