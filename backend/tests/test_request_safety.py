from app import create_app


def test_request_preprocessing_does_not_crash_when_auto_close_fails(monkeypatch):
    monkeypatch.setattr("app.validate_database", lambda app: None)
    monkeypatch.setattr("app.services.session_service.auto_close_sessions", lambda: (_ for _ in ()).throw(RuntimeError("auto-close failed")))
    app = create_app()
    client = app.test_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.data.decode("utf-8") == "OK"
