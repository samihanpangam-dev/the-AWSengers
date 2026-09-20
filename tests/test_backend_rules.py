from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.file_tools import edit_file, inspect_file, reset_workspace, set_workspace
from backend.media_tools import compress_video, convert_media
from backend.security import CedarSecurityEngine
from backend.subscriptions import SubscriptionStore


def test_subscription_api_routes():
    client = TestClient(app)
    response = client.get("/subscription/status", headers={"X-User-ID": "api-test-user"})
    assert response.status_code == 200
    assert response.json()["trial_days"] == 30
    response = client.post("/subscription/subscribe", headers={"X-User-ID": "api-test-user"})
    assert response.status_code == 200
    assert response.json()["status"] == "active"
    assert client.post("/subscription/checkout", headers={"X-User-ID": "checkout-user"}).status_code == 200
    assert client.post("/subscription/webhook", json={}).status_code == 400


def test_file_tools_are_confined_and_edit_text(tmp_path: Path):
    source = tmp_path / "note.txt"
    source.write_text("before", encoding="utf-8")
    token = set_workspace(tmp_path)
    try:
        assert "before" in inspect_file(str(source))
        assert "Updated" in edit_file(str(source), "after")
        assert source.read_text(encoding="utf-8") == "after"
        assert "outside" in inspect_file(str(tmp_path.parent / "secret.txt")).lower()
    finally:
        reset_workspace(token)


def test_subscription_trial_and_expiry():
    store = SubscriptionStore()
    item = store.status("test-user")
    assert item.status == "trialing"
    assert item.as_dict()["price_inr"] == 99
    item.current_period_end = item.trial_started_at
    assert store.status("test-user").status == "expired"
    with pytest.raises(PermissionError):
        store.require_access("test-user")


def test_cedar_routing_denies_system_commands():
    engine = CedarSecurityEngine()
    decision = engine.classify_and_evaluate("run bash", [])
    assert decision.allowed is False
    assert "FORBID" in decision.diagnostics


def test_media_validation_is_explicit(tmp_path: Path):
    missing = tmp_path / "missing.mp4"
    with pytest.raises(ValueError, match="Input file not found"):
        convert_media(str(missing), str(tmp_path / "out.mp3"))
    source = tmp_path / "input.mp4"
    source.write_bytes(b"not media")
    with pytest.raises(ValueError, match="different"):
        compress_video(str(source), str(source))
