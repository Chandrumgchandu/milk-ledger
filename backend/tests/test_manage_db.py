import manage_db


def test_manage_db_continues_when_schema_validation_fails(monkeypatch):
    monkeypatch.setattr(manage_db, "run_all_migrations", lambda reason="manual": False)
    monkeypatch.setattr(manage_db, "check_database_ready", lambda auto_fix=False: (_ for _ in ()).throw(RuntimeError("network down")))

    manage_db.main()
