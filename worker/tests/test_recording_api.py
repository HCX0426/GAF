"""Tests for RecordingAPIClient (s45: token auth + screenshot upload)."""

from unittest import mock

from core.recording_api import RecordingAPIClient, _resolve_token


class FakeResponse:
    def __init__(self, status_code=201, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = "{}"

    def json(self):
        return self._json


def test_default_base_url_derives_from_server_url():
    client = RecordingAPIClient(server_url="ws://10.0.0.5:9001/ws/protocol/agents/")
    assert client.base_url == "http://10.0.0.5:9001/api/v2"


def test_default_base_url_falls_back():
    client = RecordingAPIClient(server_url="")
    assert client.base_url.startswith("http://127.0.0.1:8000/api/v2")


def test_token_priority_explicit_over_env(monkeypatch):
    monkeypatch.setenv("GAF_AGENT_TOKEN", "env-token")
    client = RecordingAPIClient(server_url="", token="cli-token")
    assert client.token == "cli-token"
    assert client._headers()["Authorization"] == "Token cli-token"


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("GAF_AGENT_TOKEN", "env-token")
    client = RecordingAPIClient(server_url="")
    assert client.token == "env-token"


def test_token_empty_when_unresolvable(monkeypatch):
    monkeypatch.delenv("GAF_AGENT_TOKEN", raising=False)
    client = RecordingAPIClient(server_url="")
    assert client.token == ""


def test_upload_recording_sends_token_and_payload():
    client = RecordingAPIClient(server_url="ws://127.0.0.1:8000/ws/", token="tok-123")
    with mock.patch("core.recording_api.requests.post", return_value=FakeResponse(201, {"id": 7})) as post:
        result = client.upload_recording({"name": "r", "events": []})
        assert result == {"id": 7}
        call = post.call_args
        assert call.kwargs["headers"]["Authorization"] == "Token tok-123"
        assert call.kwargs["json"] == {"name": "r", "events": []}
        assert call.args[0].endswith("/api/v2/recordings/")


def test_upload_recording_failure_returns_none():
    client = RecordingAPIClient(server_url="ws://127.0.0.1:8000/ws/", token="tok")
    with mock.patch("core.recording_api.requests.post", return_value=FakeResponse(500)):
        assert client.upload_recording({"name": "r"}) is None


def test_upload_screenshots_uploads_matching_files(tmp_path):
    shot = tmp_path / "a.png"
    shot.write_bytes(b"\x89PNG")
    events = [
        {"event_type": "click", "screenshot_path": ""},
        {"event_type": "screenshot", "screenshot_path": str(shot)},
        {"event_type": "screenshot", "screenshot_path": str(tmp_path / "missing.png")},
    ]
    client = RecordingAPIClient(server_url="ws://127.0.0.1:8000/ws/", token="tok")
    with mock.patch("core.recording_api.requests.post", return_value=FakeResponse(200)) as post:
        stats = client.upload_screenshots(7, events)
    assert stats == {"uploaded": 1, "skipped": 2, "failed": []}
    call = post.call_args
    assert "recordings/7/screenshots/" in call.args[0]
    assert call.kwargs["data"] == {"event_index": "1"}
    assert call.kwargs["headers"]["Authorization"] == "Token tok"


def test_upload_screenshots_reports_failure(tmp_path):
    shot = tmp_path / "b.png"
    shot.write_bytes(b"\x89PNG")
    events = [{"event_type": "screenshot", "screenshot_path": str(shot)}]
    client = RecordingAPIClient(server_url="ws://127.0.0.1:8000/ws/", token="tok")
    with mock.patch("core.recording_api.requests.post", return_value=FakeResponse(400)):
        stats = client.upload_screenshots(7, events)
    assert stats == {"uploaded": 0, "skipped": 0, "failed": [0]}


def test_resolve_token_store_fallback(tmp_path, monkeypatch):
    monkeypatch.delenv("GAF_AGENT_TOKEN", raising=False)
    store = tmp_path / "gaf"
    store.mkdir()
    from auth.token_store import TokenStore
    ts = TokenStore(storage_dir=store)
    ts.save_token("ws://127.0.0.1:8000/ws/", "stored-token")
    with mock.patch("auth.token_store.TokenStore", lambda: ts):
        assert _resolve_token("ws://127.0.0.1:8000/ws/") == "stored-token"
