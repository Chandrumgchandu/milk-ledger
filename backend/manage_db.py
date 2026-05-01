import logging

from flask import Flask

from config import Config
from app.services.migration_service import check_database_ready, run_all_migrations
from app.services.runtime_logging import ist_now_iso, timed_operation, utc_now_iso


def main():
    logging.basicConfig(
        level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    logger = logging.getLogger("startup.manage_db")
    app = Flask(__name__)
    app.config.from_object(Config)
    logger.info(
        "event=manage_db_boot utc=%s ist=%s env=%s schema=%s",
        utc_now_iso(),
        ist_now_iso(),
        app.config.get("APP_ENV"),
        app.config.get("SUPABASE_SCHEMA"),
    )
    with app.app_context():
        with timed_operation(logger, "manage_db.migrate", env=app.config.get("APP_ENV")):
            run_all_migrations(reason="manual manage_db run")
        try:
            with timed_operation(logger, "manage_db.validate_schema", env=app.config.get("APP_ENV")):
                check_database_ready(auto_fix=False)
            logger.info("event=manage_db_ready utc=%s ist=%s mode=validated", utc_now_iso(), ist_now_iso())
            print("database-ready")
        except Exception as exc:
            logger.warning("Database validation unavailable in manage_db -> continuing in degraded mode: %s", exc)
            logger.info("event=manage_db_ready utc=%s ist=%s mode=degraded", utc_now_iso(), ist_now_iso())
            print("database-ready-degraded")


if __name__ == "__main__":
    main()
