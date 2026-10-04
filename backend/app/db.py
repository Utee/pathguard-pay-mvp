from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import get_settings

settings = get_settings()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def _sqlite_additive_migrations() -> None:
    """Add only missing MVP columns to an existing SQLite database.

    This keeps existing local/Sandbox data usable after the Phase 2 schema
    expansion. It is intentionally additive; destructive migrations belong
    in Alembic once PostgreSQL is introduced.
    """
    if not settings.database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)

    migrations = {
        "payment_requests": {
            "recipient_id": "INTEGER",
        },
        "paypal_orders": {
            "payment_request_id": "INTEGER",
            "paypal_order_id": "VARCHAR(120)",
            "status": "VARCHAR(40)",
            "approval_url": "TEXT",
            "capture_id": "VARCHAR(120)",
            "captured_at": "DATETIME",
            "created_at": "DATETIME",
        },
    }

    with engine.begin() as conn:
        for table, columns in migrations.items():
            if table not in inspector.get_table_names():
                continue

            existing = {column["name"] for column in inspector.get_columns(table)}

            for column, sql_type in columns.items():
                if column not in existing:
                    conn.execute(text(
                        f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'
                    ))


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    _sqlite_additive_migrations()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
