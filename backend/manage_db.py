import logging

from flask import Flask

from config import Config
from app.services.migration_service import check_database_ready, run_all_migrations


def main():
    logging.basicConfig(level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO), format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
    app = Flask(__name__)
    app.config.from_object(Config)
    with app.app_context():
        run_all_migrations(reason="manual manage_db run")
        check_database_ready(auto_fix=False)
    print("database-ready")


if __name__ == "__main__":
    main()
