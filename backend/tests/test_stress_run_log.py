# Tests for stress-run persistence: writing a graded batch and reading the
# latest one back, both directly against the module and through the
# /stress-runs endpoints.

from fastapi.testclient import TestClient

from app.audit import stress_run_log
from app.main import app

client = TestClient(app)

SAMPLE_SUMMARY = {"total": 3, "passed": 2, "failed": 1, "by_group": {"budget": {"total": 3, "passed": 2}}}
SAMPLE_RESULTS = [
    {"case": {"id": "a"}, "status": "passed", "reason": "ok"},
    {"case": {"id": "b"}, "status": "passed", "reason": "ok"},
    {"case": {"id": "c"}, "status": "failed", "reason": "broke through"},
]


def test_get_latest_returns_none_when_nothing_logged_yet(tmp_path, monkeypatch):
    monkeypatch.setattr(stress_run_log, "DB_PATH", tmp_path / "runs.db")
    assert stress_run_log.get_latest_stress_run() is None


def test_log_and_read_back_a_run(tmp_path, monkeypatch):
    monkeypatch.setattr(stress_run_log, "DB_PATH", tmp_path / "runs.db")

    stress_run_log.log_stress_run(SAMPLE_SUMMARY, SAMPLE_RESULTS)

    latest = stress_run_log.get_latest_stress_run()
    assert latest["total"] == 3
    assert latest["passed"] == 2
    assert latest["failed"] == 1
    assert latest["by_group"] == SAMPLE_SUMMARY["by_group"]
    assert latest["results"] == SAMPLE_RESULTS


def test_get_latest_returns_the_most_recent_of_several_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(stress_run_log, "DB_PATH", tmp_path / "runs.db")

    stress_run_log.log_stress_run({"total": 1, "passed": 1, "failed": 0, "by_group": {}}, [])
    stress_run_log.log_stress_run({"total": 5, "passed": 4, "failed": 1, "by_group": {}}, [])

    latest = stress_run_log.get_latest_stress_run()
    assert latest["total"] == 5


def test_stress_runs_endpoint_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(stress_run_log, "DB_PATH", tmp_path / "runs.db")

    post_response = client.post("/stress-runs", json={"summary": SAMPLE_SUMMARY, "results": SAMPLE_RESULTS})
    assert post_response.status_code == 200

    get_response = client.get("/stress-runs/latest")
    assert get_response.status_code == 200
    body = get_response.json()
    assert body["total"] == 3
    assert body["results"] == SAMPLE_RESULTS


def test_stress_runs_latest_endpoint_returns_null_when_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(stress_run_log, "DB_PATH", tmp_path / "runs.db")

    response = client.get("/stress-runs/latest")
    assert response.status_code == 200
    assert response.json() is None
