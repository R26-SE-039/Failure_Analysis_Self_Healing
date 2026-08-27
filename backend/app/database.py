import logging
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_MODE = os.getenv("DATABASE_MODE", "local").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL")
LOCAL_DATABASE_URL = os.getenv("LOCAL_DATABASE_URL", "sqlite:///./app.db")


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {}


def _build_engine(database_url: str):
    return create_engine(database_url, **_engine_kwargs(database_url))


def _verify_connection(candidate_engine) -> None:
    with candidate_engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def _require_neon_url() -> str:
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL is required when DATABASE_MODE is 'neon'."
        )
    return DATABASE_URL


def _select_database():
    if DATABASE_MODE == "local":
        selected_engine = _build_engine(LOCAL_DATABASE_URL)
        _verify_connection(selected_engine)
        logger.info("Using local SQLite database.")
        return selected_engine

    if DATABASE_MODE == "neon":
        selected_engine = _build_engine(_require_neon_url())
        try:
            _verify_connection(selected_engine)
        except Exception as exc:
            raise RuntimeError(
                "Unable to connect to Neon PostgreSQL during startup. "
                "Check DATABASE_URL and network access."
            ) from exc
        logger.info("Using Neon PostgreSQL database.")
        return selected_engine

    if DATABASE_MODE == "auto":
        if DATABASE_URL:
            try:
                selected_engine = _build_engine(DATABASE_URL)
                _verify_connection(selected_engine)
                logger.info("Using Neon PostgreSQL database.")
                return selected_engine
            except Exception as exc:
                logger.warning(
                    "Neon unavailable - using local SQLite fallback: %s",
                    exc.__class__.__name__,
                )
        else:
            logger.warning(
                "DATABASE_URL is not configured - using local SQLite fallback."
            )

        selected_engine = _build_engine(LOCAL_DATABASE_URL)
        _verify_connection(selected_engine)
        return selected_engine

    raise RuntimeError(
        "DATABASE_MODE must be one of: neon, local, auto."
    )


engine = _select_database()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
