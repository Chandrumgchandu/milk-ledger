from flask import Flask

from app.services import migration_service
from app.services.supabase_service import SafeQueryProxy


def test_check_database_ready_auto_fixes_missing_tables(monkeypatch):
    app = Flask(__name__)
    app.config["SUPABASE_URL"] = "https://example.supabase.co"
    app.config["SUPABASE_SCHEMA"] = "public"

    calls = {"runs": 0}
    sequence = [["missing table: session_closures"], []]

    monkeypatch.setattr(migration_service, "list_schema_issues", lambda: sequence.pop(0))

    def fake_run_all_migrations(reason="manual"):
        calls["runs"] += 1

    monkeypatch.setattr(migration_service, "run_all_migrations", fake_run_all_migrations)

    with app.app_context():
        migration_service.check_database_ready(auto_fix=True)

    assert calls["runs"] == 1


def test_safe_query_proxy_retries_once_after_self_heal(monkeypatch):
    class DummyBuilder:
        def __init__(self):
            self.calls = 0

        def execute(self):
            self.calls += 1
            if self.calls == 1:
                raise Exception("Could not find the table 'session_closures' in the schema cache")
            return {"ok": True}

    monkeypatch.setattr("app.services.supabase_service.attempt_database_self_heal", lambda error, table_name=None: True)

    builder = DummyBuilder()
    result = SafeQueryProxy(builder, table_name="session_closures").execute()

    assert result == {"ok": True}
    assert builder.calls == 2


def test_list_schema_issues_returns_empty_when_postgrest_is_temporarily_unreachable(monkeypatch):
    app = Flask(__name__)
    app.config["SUPABASE_URL"] = "https://example.supabase.co"
    app.config["SUPABASE_SCHEMA"] = "public"
    app.config["SUPABASE_DB_URL"] = ""

    monkeypatch.setattr(migration_service, "_schema_issues_via_admin", lambda: [])
    monkeypatch.setattr(migration_service, "_schema_issues_via_postgrest", lambda: (_ for _ in ()).throw(Exception("[Errno 11001] getaddrinfo failed")))

    with app.app_context():
        assert migration_service.list_schema_issues() == []


def test_connectivity_error_detects_windows_socket_block():
    assert migration_service.is_connectivity_error(Exception("[WinError 10013] An attempt was made to access a socket in a way forbidden by its access permissions"))
