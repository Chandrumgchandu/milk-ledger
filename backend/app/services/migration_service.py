from __future__ import annotations

from pathlib import Path
from threading import Lock
import logging
import subprocess

import psycopg
from flask import current_app

from .runtime_logging import timed_operation, utc_now_iso, ist_now_iso

logger = logging.getLogger(__name__)

REQUIRED_TABLES = (
    "admins",
    "farmers",
    "rates",
    "milk_entries",
    "payments",
    "store_transactions",
    "store_transaction_items",
    "monthly_settlements",
    "payment_logs",
    "app_settings",
    "whatsapp_states",
    "processed_messages",
    "session_closures",
)

REQUIRED_COLUMNS = {
    "session_closures": {"id", "session_name", "target_date", "is_closed", "created_at"},
}

_MIGRATION_LOCK = Lock()


def migration_directory() -> Path:
    root = Path(current_app.root_path).resolve()
    for candidate in (root, *root.parents):
        migrations_dir = candidate / "supabase" / "migrations"
        if migrations_dir.exists():
            return migrations_dir
    return root / "supabase" / "migrations"


def mask_supabase_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return "<unset>"
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        head = rest[:10]
        return f"{scheme}://{head}***"
    return f"{raw[:10]}***"


def log_database_target():
    parsed_target = describe_database_admin_target()
    logger.info(
        "event=database_target utc=%s ist=%s supabase_target=%s schema=%s db_host=%s db_port=%s db_name=%s sslmode=%s",
        utc_now_iso(),
        ist_now_iso(),
        mask_supabase_url(current_app.config.get("SUPABASE_URL", "")),
        current_app.config["SUPABASE_SCHEMA"],
        parsed_target.get("host", "<unset>"),
        parsed_target.get("port", "<unset>"),
        parsed_target.get("database", "<unset>"),
        parsed_target.get("sslmode", "<unset>"),
    )


def get_database_admin_url() -> str:
    return (current_app.config.get("SUPABASE_DB_URL") or "").strip()


def describe_database_admin_target() -> dict[str, str]:
    from urllib.parse import parse_qsl, urlsplit

    raw = get_database_admin_url()
    if not raw:
        return {}
    parsed = urlsplit(raw)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    return {
        "host": parsed.hostname or "",
        "port": str(parsed.port or 5432),
        "database": parsed.path.lstrip("/") or "",
        "sslmode": query.get("sslmode", ""),
    }


def execute_admin_sql(sql: str):
    db_url = get_database_admin_url()
    if not db_url:
        raise RuntimeError("SUPABASE_DB_URL is required for migration and schema reload operations.")
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def reload_postgrest_schema():
    with timed_operation(logger, "database.reload_postgrest_schema"):
        execute_admin_sql("notify pgrst, 'reload schema';")


def run_all_migrations(reason: str = "manual"):
    migrations_dir = migration_directory()
    if not migrations_dir.exists():
        raise RuntimeError(f"Migration directory not found: {migrations_dir}")

    with _MIGRATION_LOCK:
        with timed_operation(logger, "database.run_all_migrations", reason=reason, migrations_dir=migrations_dir):
            if _try_supabase_cli_push(migrations_dir):
                reload_postgrest_schema()
                return

            db_url = get_database_admin_url()
            if not db_url:
                raise RuntimeError("SUPABASE_DB_URL is required when Supabase CLI is unavailable.")

            migration_files = sorted(migrations_dir.glob("*.sql"))
            if not migration_files:
                logger.warning("No migration files found in %s", migrations_dir)
                return

            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    for migration_file in migration_files:
                        with timed_operation(logger, "database.apply_migration_file", file_name=migration_file.name, reason=reason):
                            cur.execute(migration_file.read_text(encoding="utf-8"))

            reload_postgrest_schema()


def _try_supabase_cli_push(migrations_dir: Path) -> bool:
    db_url = get_database_admin_url()
    if not db_url:
        return False

    try:
        with timed_operation(logger, "database.supabase_cli_push", migrations_dir=migrations_dir.parent):
            result = subprocess.run(
                ["supabase", "db", "push", "--db-url", db_url],
                cwd=str(migrations_dir.parent),
                capture_output=True,
                text=True,
                check=False,
                timeout=300,
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.info("Supabase CLI migration push unavailable: %s", exc)
        return False

    if result.returncode != 0:
        logger.warning("Supabase CLI migration push failed, falling back to direct SQL: %s", (result.stderr or result.stdout or "").strip())
        return False

    logger.info("Supabase CLI migration push succeeded")
    return True


def _schema_issues_via_admin() -> list[str]:
    db_url = get_database_admin_url()
    if not db_url:
        return []

    schema = current_app.config["SUPABASE_SCHEMA"]
    table_query = """
        select table_name
        from information_schema.tables
        where table_schema = %s
    """
    column_query = """
        select table_name, column_name
        from information_schema.columns
        where table_schema = %s
    """
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(table_query, (schema,))
            existing = {row[0] for row in cur.fetchall()}
            cur.execute(column_query, (schema,))
            column_rows = cur.fetchall()

    issues = [f"missing table: {table}" for table in REQUIRED_TABLES if table not in existing]
    columns_by_table: dict[str, set[str]] = {}
    for table_name, column_name in column_rows:
        columns_by_table.setdefault(table_name, set()).add(column_name)

    for table_name, required_columns in REQUIRED_COLUMNS.items():
        existing_columns = columns_by_table.get(table_name, set())
        missing_columns = sorted(required_columns - existing_columns)
        issues.extend([f"missing column: {table_name}.{column}" for column in missing_columns])
    return issues


def _schema_issues_via_postgrest() -> list[str]:
    from app.services.supabase_service import get_raw_client

    issues: list[str] = []
    client = get_raw_client()
    for table in REQUIRED_TABLES:
        try:
            logger.info("Schema validation probe: %s", table)
            client.table(table).select("*").limit(1).execute()
        except Exception as exc:
            if is_missing_table_error(exc):
                issues.append(f"missing table: {table}")
            else:
                raise
    for table_name, required_columns in REQUIRED_COLUMNS.items():
        try:
            client.table(table_name).select(",".join(sorted(required_columns))).limit(1).execute()
        except Exception as exc:
            text = str(exc).lower()
            if "column" in text and "does not exist" in text:
                for column_name in sorted(required_columns):
                    if column_name in text:
                        issues.append(f"missing column: {table_name}.{column_name}")
                        break
            else:
                raise
    return issues


def list_schema_issues() -> list[str]:
    issues = _schema_issues_via_admin()
    if issues:
        return issues
    return _schema_issues_via_postgrest()


def check_database_ready(auto_fix: bool = True):
    with timed_operation(logger, "database.check_ready", auto_fix=auto_fix):
        log_database_target()
        issues = list_schema_issues()
        if issues and auto_fix:
            logger.warning("Database schema issues detected: %s", ", ".join(issues))
            run_all_migrations(reason="startup validation")
            issues = list_schema_issues()
        if issues:
            raise RuntimeError(f"Database schema is incomplete. Issues: {', '.join(issues)}")
        logger.info("Database schema validation passed")


def is_missing_table_error(error: Exception) -> bool:
    text = str(error).lower()
    return (
        "could not find the table" in text
        or ("relation" in text and "does not exist" in text)
        or "undefinedtable" in text
    )


def attempt_database_self_heal(error: Exception, table_name: str | None = None) -> bool:
    if not is_missing_table_error(error):
        return False

    logger.warning("Detected missing-table error while accessing %s: %s", table_name or "<unknown>", error)
    try:
        run_all_migrations(reason=f"self-heal for {table_name or 'query'}")
        check_database_ready(auto_fix=False)
        return True
    except Exception:
        logger.exception("Automatic database self-heal failed")
        return False
