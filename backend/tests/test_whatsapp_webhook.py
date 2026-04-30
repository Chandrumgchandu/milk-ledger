from app import create_app


def test_webhook_does_not_crash_on_database_error(monkeypatch):
    monkeypatch.setattr("app.validate_database", lambda app: None)
    monkeypatch.setattr("app.services.session_service.auto_close_sessions", lambda: 0)
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr("app.routes.whatsapp.process_message", lambda message: (_ for _ in ()).throw(RuntimeError("db failure")))

    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {
                                    "id": "wamid.test",
                                    "from": "919999999999",
                                    "text": {"body": "hi"},
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }

    response = client.post("/webhooks/whatsapp", json=payload)

    assert response.status_code == 200
