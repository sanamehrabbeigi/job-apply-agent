from job_apply_agent import cli


def test_serve_binds_localhost_and_can_skip_browser(monkeypatch):
    calls = {}

    def fake_run(app, host, port, log_level):
        calls.update(host=host, port=port, app=app)

    monkeypatch.setattr("uvicorn.run", fake_run)
    monkeypatch.setattr("job_apply_agent.web.app.create_app", lambda start_scheduler=True: ("app", start_scheduler))
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    assert cli.main(["serve", "--port", "8123", "--no-browser", "--no-schedule"]) == 0
    assert calls == {"host": "127.0.0.1", "port": 8123, "app": ("app", False)}
    assert opened == []
