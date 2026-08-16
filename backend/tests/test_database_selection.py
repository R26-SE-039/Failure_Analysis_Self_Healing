import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import database


class DatabaseSelectionTests(unittest.TestCase):
    def test_local_mode_selects_sqlite_database(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "local.db"
            with (
                patch.object(database, "DATABASE_MODE", "local"),
                patch.object(
                    database,
                    "LOCAL_DATABASE_URL",
                    f"sqlite:///{db_path.as_posix()}",
                ),
            ):
                engine = database._select_database()

            try:
                self.assertEqual(engine.dialect.name, "sqlite")
            finally:
                engine.dispose()

    def test_neon_mode_requires_database_url(self):
        with (
            patch.object(database, "DATABASE_MODE", "neon"),
            patch.object(database, "DATABASE_URL", None),
        ):
            with self.assertRaises(RuntimeError):
                database._select_database()

    def test_auto_mode_falls_back_to_local_when_neon_is_unavailable(self):
        local_engine = database._build_engine("sqlite:///:memory:")
        neon_engine = object()

        def fake_build_engine(database_url):
            if database_url.startswith("postgresql"):
                return neon_engine
            return local_engine

        def fake_verify_connection(candidate_engine):
            if candidate_engine is neon_engine:
                raise ConnectionError("unavailable")

        with (
            patch.object(database, "DATABASE_MODE", "auto"),
            patch.object(
                database,
                "DATABASE_URL",
                "postgresql://user:password@host/self_healing_db?sslmode=require",
            ),
            patch.object(database, "LOCAL_DATABASE_URL", "sqlite:///:memory:"),
            patch.object(database, "_build_engine", side_effect=fake_build_engine),
            patch.object(
                database,
                "_verify_connection",
                side_effect=fake_verify_connection,
            ),
        ):
            selected_engine = database._select_database()

        try:
            self.assertIs(selected_engine, local_engine)
        finally:
            local_engine.dispose()


if __name__ == "__main__":
    unittest.main()
